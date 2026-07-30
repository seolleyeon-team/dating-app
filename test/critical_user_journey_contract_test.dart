import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Characterization / presence contract for the core Seolleyeon journey.
///
/// Full emulator E2E is layered separately; this guard prevents silent removal
/// of critical path entrypoints before production readiness sign-off.
void main() {
  final root = Directory.current.path;

  String read(String relativePath) =>
      File('$root/$relativePath').readAsStringSync();

  test('auth → school verify → onboarding entrypoints exist', () {
    expect(File('$root/lib/providers/auth_provider.dart').existsSync(), isTrue);
    expect(
      File(
        '$root/lib/features/auth/screens/kakao_auth_screen.dart',
      ).existsSync(),
      isTrue,
    );
    expect(
      File(
        '$root/lib/features/onboarding/screens/basic_info_screen.dart',
      ).existsSync(),
      isTrue,
    );
    final router = read('lib/router/app_router.dart');
    expect(router, contains('KakaoAuthScreen'));
    expect(router, contains('BasicInfoScreen'));
  });

  test('recommendation → like → chat → report/block services exist', () {
    expect(
      File('$root/lib/services/ai_recommendation_service.dart').existsSync(),
      isTrue,
    );
    expect(
      File('$root/lib/services/rec_event_service.dart').existsSync(),
      isTrue,
    );
    expect(
      File('$root/lib/features/chat/services/chat_service.dart').existsSync(),
      isTrue,
    );
    final report = read('functions/src/reportAndBlock.ts');
    expect(report, contains('enforceAppCheck: true'));
  });

  test('account deletion orchestration modules exist', () {
    for (final path in [
      'functions/src/accountDeletionSocialCleanup.ts',
      'functions/src/accountDeletionChatLifecycle.ts',
      'functions/src/accountDeletionEventTeamCleanup.ts',
      'functions/src/accountDeletionRetentionPurge.ts',
    ]) {
      expect(File('$root/$path').existsSync(), isTrue, reason: path);
    }
  });

  test('push coordinator and season-meeting (non-blind) paths exist', () {
    final push = read('lib/services/push_notification_service.dart');
    expect(push, contains('class PushNotificationService'));
    expect(push, contains('buildOpenDedupeKey'));
    expect(
      File(
        '$root/lib/features/event/screens/season_meeting_roulette_screen.dart',
      ).existsSync(),
      isTrue,
    );
    // Protected blind UI must remain present and untouched by this contract.
    expect(
      File(
        '$root/lib/features/event/screens/random_mathcing_screen.dart',
      ).existsSync(),
      isTrue,
    );
  });
}
