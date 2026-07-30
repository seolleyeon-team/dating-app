import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Lightweight characterization for lifecycle / listener hygiene.
/// Not a full AST audit — catches known regressions in critical coordinators.
void main() {
  test('PushNotificationService guards duplicate initialize', () {
    final src = File(
      'lib/services/push_notification_service.dart',
    ).readAsStringSync();
    expect(src, contains('_initializing'));
    expect(src, contains('_initialized'));
    expect(src, contains('claimOpenHandling'));
  });

  test('AuthProvider cancels deep-link subscriptions on dispose', () {
    final src = File('lib/providers/auth_provider.dart').readAsStringSync();
    expect(src, contains('void dispose()'));
    expect(src, contains('_linkSub?.cancel()'));
    expect(src, contains('_kakaoSchemeSub?.cancel()'));
  });

  test('logout clears user-scoped session before resetting in-memory auth', () {
    final src = File('lib/providers/auth_provider.dart').readAsStringSync();
    final logoutIdx = src.indexOf('Future<void> logout()');
    expect(logoutIdx, greaterThan(0));
    final slice = src.substring(logoutIdx, logoutIdx + 900);
    expect(slice, contains('clearUserScopedSession'));
    expect(slice.indexOf('clearUserScopedSession'), lessThan(slice.indexOf('_isAuthenticated = false')));
  });
}
