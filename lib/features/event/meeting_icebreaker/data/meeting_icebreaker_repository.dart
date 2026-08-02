// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 저장소
// 경로: lib/features/event/meeting_icebreaker/data/meeting_icebreaker_repository.dart
//
// 룰렛을 열 권한은 클라이언트가 판단하지 않는다.
// 알림 payload에 들어 있는 meetingId를 그대로 신뢰하지 않고
// callable(`meetingIcebreakerAction`)이 원본 문서를 다시 읽어 판정한다.
// =============================================================================

import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/foundation.dart';
import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';

import '../../../../services/auth_service.dart';
import '../../../../services/storage_service.dart';
import '../domain/meeting_icebreaker_prompt.dart';

/// 룰렛 진입 검증과 알림 opt-out을 담당한다.
abstract class MeetingIcebreakerRepository {
  /// 룰렛을 열어도 되는지 서버에 확인한다.
  Future<MeetingIcebreakerEntry> loadEntry({
    String? sessionId,
    String? meetingId,
    MeetingIcebreakerMeetingKind? meetingKind,
  });

  /// 이번 미팅의 룰렛 알림만 끄거나 다시 켠다.
  ///
  /// 채팅·안전 알림 등 다른 알림에는 영향을 주지 않는다.
  Future<bool> setOptOut({required String sessionId, required bool optedOut});
}

class FirebaseMeetingIcebreakerRepository
    implements MeetingIcebreakerRepository {
  FirebaseMeetingIcebreakerRepository({
    FirebaseFunctions? functions,
    AuthService? authService,
    StorageService? storageService,
  }) : _functions = functions ?? FirebaseFunctions.instanceFor(region: _region),
       _authService = authService ?? AuthService(),
       _storageService = storageService ?? StorageService();

  static const String _region = 'asia-northeast3';
  static const String _dispatcher = 'meetingIcebreakerAction';

  final FirebaseFunctions _functions;
  final AuthService _authService;
  final StorageService _storageService;

  /// 카카오 로그인 상태를 Firebase Auth 세션으로 승격한다.
  ///
  /// callable은 request.auth.uid만 신뢰하므로 세션이 없으면 호출하지 않는다.
  Future<bool> _ensureSession() async {
    try {
      final userId = await _storageService.getKakaoUserId();
      if (userId == null || userId.isEmpty) return false;
      return await _authService.ensureFirebaseSessionForKakao(userId);
    } catch (error) {
      debugPrint(
        '[ICEBREAKER] session attach failed: '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
      return false;
    }
  }

  Future<Map<String, dynamic>> _call(
    String action,
    Map<String, dynamic> data,
  ) async {
    final result = await _functions.httpsCallable(_dispatcher).call<dynamic>({
      ...data,
      'action': action,
    });
    final raw = result.data;
    if (raw is Map) {
      return Map<String, dynamic>.from(raw.cast<String, dynamic>());
    }
    return <String, dynamic>{};
  }

  @override
  Future<MeetingIcebreakerEntry> loadEntry({
    String? sessionId,
    String? meetingId,
    MeetingIcebreakerMeetingKind? meetingKind,
  }) async {
    if (!await _ensureSession()) {
      return const MeetingIcebreakerEntry.denied(
        MeetingIcebreakerEntryDecision.unauthenticated,
      );
    }

    try {
      final payload = await _call('getMeetingIcebreakerEntry', {
        if (sessionId != null && sessionId.isNotEmpty) 'sessionId': sessionId,
        if (meetingId != null && meetingId.isNotEmpty) 'meetingId': meetingId,
        if (meetingKind != null) 'meetingType': meetingKind.wireName,
      });
      return MeetingIcebreakerEntry.fromMap(payload);
    } on FirebaseFunctionsException catch (error) {
      debugPrint('[ICEBREAKER] entry check failed: ${error.code}');
      if (error.code == 'unauthenticated') {
        return const MeetingIcebreakerEntry.denied(
          MeetingIcebreakerEntryDecision.unauthenticated,
        );
      }
      return const MeetingIcebreakerEntry.denied(
        MeetingIcebreakerEntryDecision.unavailable,
      );
    } catch (error) {
      debugPrint(
        '[ICEBREAKER] entry check error: '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
      return const MeetingIcebreakerEntry.denied(
        MeetingIcebreakerEntryDecision.unavailable,
      );
    }
  }

  @override
  Future<bool> setOptOut({
    required String sessionId,
    required bool optedOut,
  }) async {
    if (!await _ensureSession()) return false;
    try {
      final payload = await _call('setMeetingIcebreakerOptOut', {
        'sessionId': sessionId,
        'optedOut': optedOut,
      });
      return payload['optedOut'] == true;
    } catch (error) {
      debugPrint(
        '[ICEBREAKER] opt-out failed: '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
      // 실패했으면 이전 상태를 유지한다 (낙관적 반영 금지).
      return !optedOut;
    }
  }
}
