import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/foundation.dart';

import '../data/models/event/event_team_match_model.dart';
import '../data/models/event/team_meeting_match_model.dart';
import '../data/models/event/team_meeting_request_model.dart';
import 'event_match_service.dart';
import 'storage_service.dart';

// =============================================================================
// 팀 대 팀 미팅 요청 서비스
// Firestore collections: eventTeamMeetingRequests, eventThreeVsThreeMatches
// =============================================================================

class TeamMeetingRequestService {
  TeamMeetingRequestService({
    FirebaseFirestore? firestore,
    EventMatchService? eventMatchService,
    StorageService? storageService,
  })  : _firestore = firestore ?? FirebaseFirestore.instance,
        _eventMatchService = eventMatchService ?? EventMatchService(),
        _storageService = storageService ?? StorageService();

  final FirebaseFirestore _firestore;
  final EventMatchService _eventMatchService;
  final StorageService _storageService;

  static const String _requestsCollection = 'eventTeamMeetingRequests';
  static const String _matchesCollection = 'eventThreeVsThreeMatches';

  // ===========================================================================
  // 헬퍼: 현재 사용자 ID
  // ===========================================================================

  Future<String> _requireCurrentUserId() async {
    final uid = await _storageService.getKakaoUserId();
    if (uid == null || uid.isEmpty) {
      throw StateError('로그인이 필요해요.');
    }
    return uid;
  }

  // ===========================================================================
  // 현재 사용자의 팀 ID resolve
  // ===========================================================================

  Future<String?> resolveCurrentTeamId() async {
    return _eventMatchService.resolveCurrentGroupId(requireFullTeam: true);
  }

  // ===========================================================================
  // 미팅 요청 생성 (슬롯 결과 → request doc)
  // ===========================================================================

  /// 슬롯 머신 결과에서 상대 팀에 미팅 요청을 전송한다.
  /// 동일 팀 쌍에 대해 pending request가 이미 있으면 중복 생성을 방지한다.
  Future<String> createMeetingRequest({
    required EventTeamMatchResult matchResult,
    required String viewerGroupId,
  }) async {
    final currentUserId = await _requireCurrentUserId();

    final myTeamId = viewerGroupId;
    final counterpart = matchResult.counterpartForGroup(myTeamId);
    if (counterpart == null) {
      throw StateError('상대 팀 정보를 찾을 수 없어요.');
    }
    final otherTeamId = counterpart.groupId;

    if (myTeamId.isEmpty || otherTeamId.isEmpty) {
      throw StateError('팀 정보가 올바르지 않아요.');
    }

    // 팀 snapshot 결정
    final myTeamSnapshot =
        matchResult.requestingGroupId == myTeamId
            ? matchResult.requestingTeam
            : matchResult.matchedTeam;

    final otherTeamSnapshot = counterpart;

    // 중복 pending 체크
    final existing = await _firestore
        .collection(_requestsCollection)
        .where('fromTeamId', isEqualTo: myTeamId)
        .where('toTeamId', isEqualTo: otherTeamId)
        .where('status', isEqualTo: 'pending')
        .limit(1)
        .get();

    if (existing.docs.isNotEmpty) {
      throw StateError('이미 이 팀에 보낸 대기 중인 요청이 있어요.');
    }

    // 역방향 pending 체크
    final reverse = await _firestore
        .collection(_requestsCollection)
        .where('fromTeamId', isEqualTo: otherTeamId)
        .where('toTeamId', isEqualTo: myTeamId)
        .where('status', isEqualTo: 'pending')
        .limit(1)
        .get();

    if (reverse.docs.isNotEmpty) {
      throw StateError('상대 팀에서 이미 요청을 보냈어요. 받은 요청을 확인해 주세요.');
    }

    final myMemberUids = myTeamSnapshot?.members.map((m) => m.uid).toList() ?? <String>[];
    final otherMemberUids = otherTeamSnapshot.members.map((m) => m.uid).toList();

    final docRef = _firestore.collection(_requestsCollection).doc();
    final now = FieldValue.serverTimestamp();

    await docRef.set({
      'source': 'slot_result',
      'sourceResultId': matchResult.resultId,
      'fromTeamId': myTeamId,
      'toTeamId': otherTeamId,
      'fromTeamMemberUids': myMemberUids,
      'toTeamMemberUids': otherMemberUids,
      'fromTeamSnapshot': myTeamSnapshot?.toMap(),
      'toTeamSnapshot': otherTeamSnapshot.toMap(),
      'createdByUserId': currentUserId,
      'status': 'pending',
      'respondedByUserId': null,
      'respondedAt': null,
      'matchId': null,
      'createdAt': now,
      'updatedAt': now,
    });

    return docRef.id;
  }

  // ===========================================================================
  // 요청 수락 (Firestore Transaction)
  // ===========================================================================

  /// 팀 미팅 요청을 수락한다.
  /// transaction으로 race condition을 방지하고, match doc을 원자적으로 생성한다.
  Future<String> acceptRequest(String requestId) async {
    final currentUserId = await _requireCurrentUserId();

    final matchId = await _firestore.runTransaction<String>((tx) async {
      final reqRef = _firestore.collection(_requestsCollection).doc(requestId);
      final reqSnap = await tx.get(reqRef);

      if (!reqSnap.exists || reqSnap.data() == null) {
        throw StateError('요청 문서를 찾을 수 없어요.');
      }

      final data = reqSnap.data()!;
      final status = data['status']?.toString() ?? '';

      if (status != 'pending') {
        throw StateError('이미 처리된 요청이에요. (현재: $status)');
      }

      final toMemberUids = List<String>.from(data['toTeamMemberUids'] ?? []);
      if (!toMemberUids.contains(currentUserId)) {
        throw StateError('이 요청에 응답할 권한이 없어요.');
      }

      // 매치 doc 생성
      final matchRef = _firestore.collection(_matchesCollection).doc();
      final now = FieldValue.serverTimestamp();

      tx.update(reqRef, {
        'status': 'accepted',
        'respondedByUserId': currentUserId,
        'respondedAt': now,
        'matchId': matchRef.id,
        'updatedAt': now,
      });

      tx.set(matchRef, {
        'requestId': requestId,
        'leftTeamId': data['fromTeamId'],
        'rightTeamId': data['toTeamId'],
        'leftTeamSnapshot': data['fromTeamSnapshot'],
        'rightTeamSnapshot': data['toTeamSnapshot'],
        'leftMemberUids': data['fromTeamMemberUids'],
        'rightMemberUids': data['toTeamMemberUids'],
        'status': 'active',
        'acceptedByUserId': currentUserId,
        'source': 'team_request_accept',
        'createdAt': now,
        'updatedAt': now,
      });

      return matchRef.id;
    });

    return matchId;
  }

  // ===========================================================================
  // 요청 거절 (Firestore Transaction)
  // ===========================================================================

  /// 팀 미팅 요청을 거절한다.
  Future<void> declineRequest(String requestId) async {
    final currentUserId = await _requireCurrentUserId();

    await _firestore.runTransaction((tx) async {
      final reqRef = _firestore.collection(_requestsCollection).doc(requestId);
      final reqSnap = await tx.get(reqRef);

      if (!reqSnap.exists || reqSnap.data() == null) {
        throw StateError('요청 문서를 찾을 수 없어요.');
      }

      final data = reqSnap.data()!;
      final status = data['status']?.toString() ?? '';

      if (status != 'pending') {
        throw StateError('이미 처리된 요청이에요. (현재: $status)');
      }

      final toMemberUids = List<String>.from(data['toTeamMemberUids'] ?? []);
      if (!toMemberUids.contains(currentUserId)) {
        throw StateError('이 요청에 응답할 권한이 없어요.');
      }

      final now = FieldValue.serverTimestamp();
      tx.update(reqRef, {
        'status': 'declined',
        'respondedByUserId': currentUserId,
        'respondedAt': now,
        'updatedAt': now,
      });
    });
  }

  // ===========================================================================
  // 스트림: 받은 요청 목록
  // ===========================================================================

  Stream<List<TeamMeetingRequestDoc>> watchReceivedRequests(String teamId) {
    return _firestore
        .collection(_requestsCollection)
        .where('toTeamId', isEqualTo: teamId)
        .orderBy('createdAt', descending: true)
        .snapshots()
        .map((qs) {
      return qs.docs
          .map((d) => TeamMeetingRequestDoc.fromDoc(d.id, d.data()))
          .toList();
    });
  }

  // ===========================================================================
  // 스트림: 보낸 요청 목록
  // ===========================================================================

  Stream<List<TeamMeetingRequestDoc>> watchSentRequests(String teamId) {
    return _firestore
        .collection(_requestsCollection)
        .where('fromTeamId', isEqualTo: teamId)
        .orderBy('createdAt', descending: true)
        .snapshots()
        .map((qs) {
      return qs.docs
          .map((d) => TeamMeetingRequestDoc.fromDoc(d.id, d.data()))
          .toList();
    });
  }

  // ===========================================================================
  // 스트림: pending 받은 요청 개수 (badge용)
  // ===========================================================================

  Stream<int> watchPendingReceivedCount(String teamId) {
    return _firestore
        .collection(_requestsCollection)
        .where('toTeamId', isEqualTo: teamId)
        .where('status', isEqualTo: 'pending')
        .snapshots()
        .map((qs) => qs.docs.length);
  }

  // ===========================================================================
  // 단건 요청 실시간 감시
  // ===========================================================================

  Stream<TeamMeetingRequestDoc?> watchRequest(String requestId) {
    return _firestore
        .collection(_requestsCollection)
        .doc(requestId)
        .snapshots()
        .map((s) {
      if (!s.exists || s.data() == null) return null;
      return TeamMeetingRequestDoc.fromDoc(s.id, s.data()!);
    });
  }

  // ===========================================================================
  // 매치 doc 조회
  // ===========================================================================

  Future<TeamMeetingMatchDoc?> getMatchOnce(String matchId) async {
    final snap = await _firestore.collection(_matchesCollection).doc(matchId).get();
    if (!snap.exists || snap.data() == null) return null;
    return TeamMeetingMatchDoc.fromDoc(snap.id, snap.data()!);
  }

  Stream<TeamMeetingMatchDoc?> watchMatch(String matchId) {
    return _firestore
        .collection(_matchesCollection)
        .doc(matchId)
        .snapshots()
        .map((s) {
      if (!s.exists || s.data() == null) return null;
      return TeamMeetingMatchDoc.fromDoc(s.id, s.data()!);
    });
  }

  // ===========================================================================
  // 단건 요청 조회
  // ===========================================================================

  Future<TeamMeetingRequestDoc?> getRequestOnce(String requestId) async {
    try {
      final snap =
          await _firestore.collection(_requestsCollection).doc(requestId).get();
      if (!snap.exists || snap.data() == null) return null;
      return TeamMeetingRequestDoc.fromDoc(snap.id, snap.data()!);
    } catch (e) {
      debugPrint('getRequestOnce error: $e');
      return null;
    }
  }
}
