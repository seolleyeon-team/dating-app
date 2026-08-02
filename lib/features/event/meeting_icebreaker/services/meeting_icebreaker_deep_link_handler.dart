// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 알림 클릭 처리 (단일 coordinator)
// 경로: lib/features/event/meeting_icebreaker/services/meeting_icebreaker_deep_link_handler.dart
//
// FirebaseMessaging의 세 흐름(onMessage / onMessageOpenedApp / getInitialMessage)이
// 같은 알림을 각각 처리해 룰렛이 두 번 열리는 것을 막는다.
//
//  - dedupe: 같은 알림(notificationId)은 한 번만 연다
//  - 단일 진입: 룰렛이 열려 있는 동안 두 번째 요청은 무시한다
//  - 초기화 race: navigator가 아직 없으면 보류했다가 준비된 뒤 재생한다
//  - 권한: payload를 믿지 않고 서버 callable로 매번 다시 검증한다
// =============================================================================

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';

import '../../../../services/navigation_service.dart';
import '../data/meeting_icebreaker_analytics.dart';
import '../data/meeting_icebreaker_repository.dart';
import '../domain/meeting_icebreaker_prompt.dart';
import '../presentation/meeting_roulette_dialog.dart';

typedef MeetingIcebreakerDialogOpener =
    Future<void> Function(
      BuildContext context,
      MeetingIcebreakerEntry entry,
      MeetingIcebreakerRepository repository,
      MeetingIcebreakerAnalytics analytics,
    );

class MeetingIcebreakerDeepLinkHandler {
  MeetingIcebreakerDeepLinkHandler._();

  static final MeetingIcebreakerDeepLinkHandler instance =
      MeetingIcebreakerDeepLinkHandler._();

  /// navigator를 기다리는 최대 시간 (앱 초기화 / 세션 복구 / 라우터 준비).
  static const Duration _navigatorRetryInterval = Duration(milliseconds: 300);
  static const int _navigatorRetryLimit = 30;

  MeetingIcebreakerRepository Function() repositoryFactory = () =>
      FirebaseMeetingIcebreakerRepository();

  MeetingIcebreakerAnalytics Function() analyticsFactory = () =>
      MeetingIcebreakerAnalytics();

  /// 테스트에서 실제 dialog 대신 다른 동작을 넣기 위한 seam.
  MeetingIcebreakerDialogOpener? dialogOpener;

  /// 안내 문구 표시 seam (기본은 SnackBar).
  void Function(BuildContext context, String message)? messagePresenter;

  final Set<String> _handledKeys = <String>{};
  bool _busy = false;
  MeetingIcebreakerPromptPayload? _pending;

  @visibleForTesting
  void resetForTest() {
    _handledKeys.clear();
    _busy = false;
    _pending = null;
    dialogOpener = null;
    messagePresenter = null;
  }

  @visibleForTesting
  bool get isBusy => _busy;

  @visibleForTesting
  bool hasHandled(String dedupeKey) => _handledKeys.contains(dedupeKey);

  /// 푸시 data map을 처리한다. 룰렛 알림이 아니면 false를 돌려준다.
  Future<bool> handleNotificationData(Map<String, dynamic> data) async {
    final payload = MeetingIcebreakerPromptPayload.tryParse(data);
    if (payload == null) return false;
    await handlePayload(payload);
    return true;
  }

  /// 앱/라우터 초기화가 끝난 뒤 호출한다. 보류된 알림이 있으면 이어서 처리한다.
  Future<void> flushPending() async {
    final pending = _pending;
    if (pending == null) return;
    _pending = null;
    await handlePayload(pending);
  }

  /// 앱 안에서 직접 룰렛을 여는 경로.
  ///
  /// 알림 권한을 거부한 사용자도 미팅 중에 룰렛을 쓸 수 있게 하기 위한 진입점이다.
  /// 알림 경로와 똑같이 서버 검증을 거치므로, 참가자가 아니거나 미팅이 끝났으면
  /// 열리지 않는다 (참가자용 기능이라는 정책을 유지한다).
  Future<void> openFromApp({
    required BuildContext context,
    String? sessionId,
    String? meetingId,
    MeetingIcebreakerMeetingKind? meetingKind,
  }) async {
    if (_busy) return;
    _busy = true;
    try {
      final repository = repositoryFactory();
      final analytics = analyticsFactory();
      final entry = await repository.loadEntry(
        sessionId: sessionId,
        meetingId: meetingId,
        meetingKind: meetingKind,
      );
      if (!context.mounted) return;
      if (!entry.allowed) {
        _presentMessage(context, entry.decision.userMessage);
        return;
      }
      final opener = dialogOpener ?? _defaultDialogOpener;
      await opener(context, entry, repository, analytics);
    } catch (error) {
      debugPrint(
        '[ICEBREAKER] in-app open failed: '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
    } finally {
      _busy = false;
    }
  }

  Future<void> handlePayload(MeetingIcebreakerPromptPayload payload) async {
    final key = payload.dedupeKey;
    if (_handledKeys.contains(key)) {
      debugPrint('[ICEBREAKER] duplicate notification ignored');
      return;
    }
    if (_busy) {
      debugPrint('[ICEBREAKER] roulette already opening, ignoring');
      return;
    }

    _busy = true;
    try {
      final context = await _waitForContext();
      if (context == null) {
        // 앱이 아직 준비되지 않았다. 나중에 다시 시도한다.
        _pending = payload;
        return;
      }

      final repository = repositoryFactory();
      final analytics = analyticsFactory();

      // 알림 payload가 아니라 서버가 판정한다.
      final entry = await repository.loadEntry(
        sessionId: payload.sessionId.isEmpty ? null : payload.sessionId,
        meetingId: payload.meetingId.isEmpty ? null : payload.meetingId,
        meetingKind: payload.meetingKind,
      );

      analytics.log(
        MeetingIcebreakerAnalyticsEvent.promptOpened,
        params: <String, dynamic>{
          'entry_decision': entry.decision.wireName,
          if (entry.meetingKind != null)
            'meeting_type': entry.meetingKind!.wireName,
          if (payload.notificationSequence > 0)
            'notification_sequence': payload.notificationSequence,
        },
      );

      // 검증하는 동안 앱이 닫혔거나 화면이 사라졌으면 아무 것도 하지 않는다.
      if (!context.mounted) return;

      if (!entry.allowed) {
        // 네트워크 오류는 다시 시도할 수 있어야 하므로 dedupe에 남기지 않는다.
        if (entry.decision != MeetingIcebreakerEntryDecision.unavailable) {
          _handledKeys.add(key);
        }
        _presentMessage(context, entry.decision.userMessage);
        return;
      }

      _handledKeys.add(key);
      final opener = dialogOpener ?? _defaultDialogOpener;
      await opener(context, entry, repository, analytics);
    } catch (error) {
      debugPrint(
        '[ICEBREAKER] deep link failed: '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
    } finally {
      _busy = false;
    }
  }

  Future<void> _defaultDialogOpener(
    BuildContext context,
    MeetingIcebreakerEntry entry,
    MeetingIcebreakerRepository repository,
    MeetingIcebreakerAnalytics analytics,
  ) {
    return showMeetingRouletteDialog(
      context: context,
      entry: entry,
      repository: repository,
      analytics: analytics,
    );
  }

  void _presentMessage(BuildContext context, String message) {
    if (message.isEmpty) return;
    final presenter = messagePresenter;
    if (presenter != null) {
      presenter(context, message);
      return;
    }
    try {
      final messenger = ScaffoldMessenger.maybeOf(context);
      if (messenger == null) {
        debugPrint('[ICEBREAKER] $message');
        return;
      }
      messenger.showSnackBar(SnackBar(content: Text(message)));
    } catch (error) {
      debugPrint(
        '[ICEBREAKER] message present failed: '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
    }
  }

  /// navigator가 준비될 때까지 기다린다.
  ///
  /// Firebase 초기화, 로그인 세션 복구, 라우터 초기화가 겹칠 수 있어
  /// 앱이 완전히 종료된 상태에서 알림으로 열린 경우를 처리한다.
  Future<BuildContext?> _waitForContext() async {
    for (var attempt = 0; attempt < _navigatorRetryLimit; attempt++) {
      final navigatorContext = NavigationService.navigatorKey.currentContext;
      if (navigatorContext != null && navigatorContext.mounted) {
        return navigatorContext;
      }
      await Future<void>.delayed(_navigatorRetryInterval);
    }
    return null;
  }
}
