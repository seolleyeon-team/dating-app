import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../shared/utils/privacy_log_utils.dart';
import '../utils/phone_hash_utils.dart';

/// 연락처 차단 결과
class ContactBlockSyncResult {
  final int totalContacts;
  final int validPhoneCount;
  final int uniqueHashCount;
  final int matchedUserCount;
  final int newlyBlockedPairCount;
  final int alreadyBlockedPairCount;
  final int skippedSelfCount;
  final int invalidHashCount;

  const ContactBlockSyncResult({
    required this.totalContacts,
    required this.validPhoneCount,
    required this.uniqueHashCount,
    required this.matchedUserCount,
    required this.newlyBlockedPairCount,
    required this.alreadyBlockedPairCount,
    required this.skippedSelfCount,
    required this.invalidHashCount,
  });
}

/// Server truth for the Kakao friend avoidance surface: the user's own
/// preference plus the one-time snapshot state (kakao-friend-pairs contract
/// §3/§8). There is no reconcile/pending state anymore — the snapshot either
/// completed once or it did not.
class KakaoFriendAvoidanceStatus {
  final bool avoidanceEnabled;
  final String snapshotStatus;

  const KakaoFriendAvoidanceStatus({
    required this.avoidanceEnabled,
    required this.snapshotStatus,
  });
}

enum ContactPermissionStatus { granted, denied, permanentlyDenied }

class ContactBlockService {
  final FirebaseFunctions _functions = FirebaseFunctions.instanceFor(
    region: 'asia-northeast3',
  );
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  /// 연락처 권한 요청 및 상태 확인
  Future<ContactPermissionStatus> checkPermission() async {
    try {
      final status = await FlutterContacts.permissions.request(
        PermissionType.read,
      );
      switch (status) {
        case PermissionStatus.granted:
        case PermissionStatus.limited:
          return ContactPermissionStatus.granted;
        case PermissionStatus.permanentlyDenied:
        case PermissionStatus.restricted:
          return ContactPermissionStatus.permanentlyDenied;
        case PermissionStatus.denied:
        case PermissionStatus.notDetermined:
          return ContactPermissionStatus.denied;
      }
    } catch (e) {
      debugPrint(
        '[ContactBlock] checkPermission ${PrivacyLogUtils.errorSummary(e)}',
      );
      return ContactPermissionStatus.denied;
    }
  }

  /// 기기 연락처에서 전화번호를 읽고 정규화 + 해시
  Future<_ExtractedHashes> _extractContactHashes() async {
    final contacts = await FlutterContacts.getAll(
      properties: {ContactProperty.phone},
    );

    int totalContacts = contacts.length;
    int validCount = 0;
    final hashSet = <String>{};

    for (final contact in contacts) {
      for (final phone in contact.phones) {
        final hash = PhoneHashUtils.normalizeAndHash(phone.number);
        if (hash != null) {
          hashSet.add(hash);
          validCount++;
        }
      }
    }

    return _ExtractedHashes(
      totalContacts: totalContacts,
      validPhoneCount: validCount,
      uniqueHashes: hashSet.toList(),
    );
  }

  /// 전체 동기화 흐름: 권한 확인 → 연락처 읽기 → 해시 → 서버 전송
  Future<ContactBlockSyncResult> syncContacts() async {
    final extracted = await _extractContactHashes();

    if (extracted.uniqueHashes.isEmpty) {
      return ContactBlockSyncResult(
        totalContacts: extracted.totalContacts,
        validPhoneCount: extracted.validPhoneCount,
        uniqueHashCount: 0,
        matchedUserCount: 0,
        newlyBlockedPairCount: 0,
        alreadyBlockedPairCount: 0,
        skippedSelfCount: 0,
        invalidHashCount: 0,
      );
    }

    final callable = _functions.httpsCallable('syncContactBlocks');
    final result = await callable.call<dynamic>({
      'contactHashes': extracted.uniqueHashes,
    });

    final data = Map<String, dynamic>.from(
      (result.data as Map?)?.cast<String, dynamic>() ?? {},
    );

    return ContactBlockSyncResult(
      totalContacts: extracted.totalContacts,
      validPhoneCount: extracted.validPhoneCount,
      uniqueHashCount: extracted.uniqueHashes.length,
      matchedUserCount: (data['matchedUserCount'] as num?)?.toInt() ?? 0,
      newlyBlockedPairCount:
          (data['newlyBlockedPairCount'] as num?)?.toInt() ?? 0,
      alreadyBlockedPairCount:
          (data['alreadyBlockedPairCount'] as num?)?.toInt() ?? 0,
      skippedSelfCount: (data['skippedSelfCount'] as num?)?.toInt() ?? 0,
      invalidHashCount: (data['invalidHashCount'] as num?)?.toInt() ?? 0,
    );
  }

  /// Server truth for the avoidance toggle surface. Reads the user's own
  /// preference and the one-time snapshot state from `users/{uid}` with a
  /// forced server fetch (fail-closed: a missing snapshot field means
  /// `not_started`). This never triggers any Kakao API call or friend fetch —
  /// the legacy repeated sync callables have no client call sites anymore.
  Future<KakaoFriendAvoidanceStatus> getKakaoFriendAvoidanceStatus() async {
    final appUserId = FirebaseAuth.instance.currentUser?.uid;
    if (appUserId == null || appUserId.isEmpty) {
      return const KakaoFriendAvoidanceStatus(
        avoidanceEnabled: false,
        snapshotStatus: 'not_started',
      );
    }
    final snapshot = await _firestore
        .collection('users')
        .doc(appUserId)
        .get(const GetOptions(source: Source.server));
    final data = snapshot.data() ?? const <String, dynamic>{};
    final rawSnapshot = data['kakaoFriendSnapshot'];
    var snapshotStatus = 'not_started';
    if (rawSnapshot is Map) {
      final status = rawSnapshot['status'];
      if (status is String && status.isNotEmpty) snapshotStatus = status;
    }
    return KakaoFriendAvoidanceStatus(
      avoidanceEnabled: data['kakaoFriendAvoidanceEnabled'] == true,
      snapshotStatus: snapshotStatus,
    );
  }

  /// 현재 사용자가 차단한(blocks) 상대 UID 세트를 가져온다.
  /// 추천 필터링의 client-side defensive filter 용.
  Future<Set<String>> getBlockedUserIds() async {
    final appUserId = FirebaseAuth.instance.currentUser?.uid;
    if (appUserId == null || appUserId.isEmpty) return {};

    try {
      final snap = await _firestore
          .collection('blocks')
          .doc(appUserId)
          .collection('targets')
          .get();

      return snap.docs.map((d) => d.id).toSet();
    } catch (e) {
      debugPrint(
        '[ContactBlock] getBlockedUserIds ${PrivacyLogUtils.errorSummary(e)}',
      );
      return {};
    }
  }

  /// 마지막 연락처 동기화 시각 저장/조회
  Future<void> saveLastSyncTime() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      'contact_block_last_sync',
      DateTime.now().toIso8601String(),
    );
  }

  Future<DateTime?> getLastSyncTime() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString('contact_block_last_sync');
    if (raw == null) return null;
    return DateTime.tryParse(raw);
  }
}

class _ExtractedHashes {
  final int totalContacts;
  final int validPhoneCount;
  final List<String> uniqueHashes;

  const _ExtractedHashes({
    required this.totalContacts,
    required this.validPhoneCount,
    required this.uniqueHashes,
  });
}
