// =============================================================================
// 3:3 블라인드 취향 미팅 — 운영용 repository (보호됨)
// 경로: lib/features/blind_meeting/data/blind_meeting_ops_repository.dart
//
// 이 repository는 일반 앱 화면에서 사용하지 않는다.
// 모든 권한 판정은 서버에서 Firebase Auth custom claim(`admin`)으로 수행하며,
// 클라이언트 필드로 관리자 여부를 판단하지 않는다.
// 운영 절차는 docs/blind_meeting_operations.md 를 참고한다.
// =============================================================================

import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';

/// 운영 목록 항목.
class BlindMeetingOpsSummary {
  final String meetingId;
  final String serverStatus;
  final String slotId;
  final bool isAlcoholFree;
  final String algorithmVersion;
  final int participantCount;
  final String? groupChatId;
  final bool fivePersonExceptionApproved;

  const BlindMeetingOpsSummary({
    required this.meetingId,
    required this.serverStatus,
    required this.slotId,
    required this.isAlcoholFree,
    required this.algorithmVersion,
    required this.participantCount,
    this.groupChatId,
    this.fivePersonExceptionApproved = false,
  });

  static BlindMeetingOpsSummary fromMap(Map<String, dynamic> data) {
    return BlindMeetingOpsSummary(
      meetingId: data['meetingId']?.toString() ?? '',
      serverStatus: data['serverStatus']?.toString() ?? '',
      slotId: data['slotId']?.toString() ?? '',
      isAlcoholFree: data['isAlcoholFree'] == true,
      algorithmVersion: data['algorithmVersion']?.toString() ?? '',
      participantCount: (data['participantCount'] as num?)?.toInt() ?? 0,
      groupChatId: data['groupChatId']?.toString(),
      fivePersonExceptionApproved: data['fivePersonExceptionApproved'] == true,
    );
  }
}

/// 운영 전용 저장소. 관리자 claim이 없으면 서버가 permission-denied를 던진다.
class BlindMeetingOpsRepository {
  BlindMeetingOpsRepository({FirebaseFunctions? functions, FirebaseAuth? auth})
    : _functions = functions ?? FirebaseFunctions.instanceFor(region: _region),
      _auth = auth ?? FirebaseAuth.instance;

  static const String _region = 'asia-northeast3';

  final FirebaseFunctions _functions;
  final FirebaseAuth _auth;

  /// 현재 세션이 운영 권한을 갖고 있는지 (claim 기반).
  ///
  /// 이 값은 UI 편의를 위한 것이고, 실제 권한은 서버에서 다시 검증된다.
  Future<bool> hasOpsClaim() async {
    final user = _auth.currentUser;
    if (user == null) return false;
    final token = await user.getIdTokenResult(true);
    final claims = token.claims ?? const <String, dynamic>{};
    return claims['admin'] == true || claims['blindMeetingOps'] == true;
  }

  Future<Map<String, dynamic>> _call(
    String name, [
    Map<String, dynamic> data = const <String, dynamic>{},
  ]) async {
    final result = await _functions.httpsCallable(name).call<dynamic>(data);
    final raw = result.data;
    if (raw is Map) {
      return Map<String, dynamic>.from(raw.cast<String, dynamic>());
    }
    return <String, dynamic>{};
  }

  Future<List<BlindMeetingOpsSummary>> listMeetings({
    String? serverStatus,
    int limit = 50,
  }) async {
    final result = await _call('listBlindMeetingsForOps', {
      if (serverStatus != null) 'serverStatus': serverStatus,
      'limit': limit,
    });
    final raw = result['meetings'];
    if (raw is! Iterable) return const <BlindMeetingOpsSummary>[];
    return raw
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item.cast<String, dynamic>()))
        .map(BlindMeetingOpsSummary.fromMap)
        .toList();
  }

  /// 참가자, 대기자, 대체 제안, 환급, 안전 flag, 점수 요약, 알림 상태.
  Future<Map<String, dynamic>> loadDetail(String meetingId) {
    return _call('getBlindMeetingOpsDetail', {'meetingId': meetingId});
  }

  Future<int> forceRematch(String meetingId) async {
    final result = await _call('forceBlindMeetingRematch', {
      'meetingId': meetingId,
    });
    return (result['createdMeetings'] as num?)?.toInt() ?? 0;
  }

  Future<Map<String, dynamic>> overrideRefund({
    required String meetingId,
    required String userId,
    required int refundBasisPoints,
  }) {
    return _call('overrideBlindMeetingRefund', {
      'meetingId': meetingId,
      'userId': userId,
      'refundBasisPoints': refundBasisPoints,
    });
  }

  Future<void> setRestriction({
    required String userId,
    required int days,
    String reason = 'manual',
  }) async {
    await _call('setBlindMeetingRestriction', {
      'userId': userId,
      'days': days,
      'reason': reason,
    });
  }

  Future<int> triggerReplacement({
    required String meetingId,
    required String userId,
    bool urgent = false,
  }) async {
    final result = await _call('triggerBlindMeetingReplacement', {
      'meetingId': meetingId,
      'userId': userId,
      'urgent': urgent,
    });
    return (result['offered'] as num?)?.toInt() ?? 0;
  }

  Future<void> resolveOpsReview({
    required String reviewId,
    String resolution = '',
  }) async {
    await _call('resolveBlindMeetingOpsReview', {
      'reviewId': reviewId,
      'resolution': resolution,
    });
  }

  Future<List<Map<String, dynamic>>> listNotificationDispatches(
    String meetingId,
  ) async {
    final result = await _call('listBlindMeetingNotificationDispatches', {
      'meetingId': meetingId,
    });
    final raw = result['dispatches'];
    if (raw is! Iterable) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item.cast<String, dynamic>()))
        .toList();
  }
}
