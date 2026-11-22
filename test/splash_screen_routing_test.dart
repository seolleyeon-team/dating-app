import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart' hide AuthProvider;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:seolleyeon/features/splash/splash_screen.dart';
import 'package:seolleyeon/providers/auth_provider.dart';
import 'package:seolleyeon/router/route_names.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/fake_auth_session.dart';

// B-17 / AUD-16: Splash routes only after AuthProvider's first resolution,
// and a signed-in user is never sent to the login funnel by a transient
// launch failure.

class _FakeSplashEnvironment implements SplashEnvironment {
  _FakeSplashEnvironment(this._session);

  final FakeSession _session;
  Uri? initialUri;
  String nextRoute = RouteNames.main;
  Object? routeError;
  Object? restrictionError;
  bool restricted = false;
  int routeResolutions = 0;

  @override
  Future<Uri?> readInitialUri() async => initialUri;

  @override
  bool isEmailLinkEntryPoint(Uri? uri) =>
      uri != null && uri.toString().contains('oobCode=');

  @override
  bool get hasFirebaseSession => _session.user != null;

  @override
  Future<bool> handleRejoinRestriction() async {
    final error = restrictionError;
    if (error != null) throw error;
    return restricted;
  }

  @override
  Future<String> resolveSetupRoute() async {
    routeResolutions += 1;
    final error = routeError;
    if (error != null) throw error;
    return nextRoute;
  }
}

Widget _app(AuthProvider provider, SplashEnvironment environment) {
  Widget page(String name) => Scaffold(body: Text('route:$name'));
  return ChangeNotifierProvider<AuthProvider>.value(
    value: provider,
    child: MaterialApp(
      home: SplashScreen(environment: environment),
      routes: {
        RouteNames.terms: (_) => page(RouteNames.terms),
        RouteNames.main: (_) => page(RouteNames.main),
        RouteNames.studentVerification: (_) =>
            page(RouteNames.studentVerification),
        RouteNames.onboardingBasicInfo: (_) =>
            page(RouteNames.onboardingBasicInfo),
      },
    ),
  );
}

/// Advances past the splash hold and lets the route transition finish. The
/// splash artwork animates forever, so `pumpAndSettle` cannot be used.
Future<void> _advance(WidgetTester tester, Duration duration) async {
  await tester.pump(duration);
  for (var i = 0; i < 8; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('signed out: terms', (tester) async {
    final h = AuthHarness();
    final env = _FakeSplashEnvironment(h.session);
    await tester.pumpWidget(_app(h.start(), env));
    await _advance(tester, const Duration(milliseconds: 1500));

    expect(find.text('route:${RouteNames.terms}'), findsOneWidget);
    expect(env.routeResolutions, 0);
    h.provider.dispose();
  });

  testWidgets('signed in: the setup ladder decides', (tester) async {
    final h = AuthHarness()..signedInAs('u1');
    final env = _FakeSplashEnvironment(h.session);
    await tester.pumpWidget(_app(h.start(), env));
    await _advance(tester, const Duration(milliseconds: 1500));

    expect(find.text('route:${RouteNames.main}'), findsOneWidget);
    expect(h.provider.isAuthenticated, isTrue);
    h.provider.dispose();
  });

  testWidgets('email-link launch goes to student verification before any '
      'session gate', (tester) async {
    final h = AuthHarness()..signedInAs('u1');
    final env = _FakeSplashEnvironment(h.session)
      ..initialUri = Uri.parse('https://x.test/__/auth/links?oobCode=abc');
    await tester.pumpWidget(_app(h.start(), env));
    await _advance(tester, const Duration(milliseconds: 1500));

    expect(
      find.text('route:${RouteNames.studentVerification}'),
      findsOneWidget,
    );
    expect(env.routeResolutions, 0);
    h.provider.dispose();
  });

  testWidgets('B-17: Splash waits for the provider instead of routing on a '
      'session the provider is about to sign out', (tester) async {
    // A temporary (non-canonical) email-link session is attached. The
    // provider signs it out, but only after a slow token refresh.
    final h = AuthHarness()..signedInAs('temp');
    h.session.claims = {'email': 'someone@yonsei.ac.kr'};
    h.session.refreshGate = Completer<void>();
    final env = _FakeSplashEnvironment(h.session);
    await tester.pumpWidget(_app(h.start(), env));

    await _advance(tester, const Duration(milliseconds: 3000));
    expect(
      env.routeResolutions,
      0,
      reason: 'the old splash routed at 1.5s on the doomed session',
    );
    expect(find.byType(SplashScreen), findsOneWidget);

    h.session.refreshGate!.complete();
    await _advance(tester, const Duration(milliseconds: 100));

    expect(h.auth.signOutCalls, 1);
    expect(find.text('route:${RouteNames.terms}'), findsOneWidget);
    expect(env.routeResolutions, 0);
    h.provider.dispose();
  });

  testWidgets('a provider that never settles does not block the splash '
      'forever', (tester) async {
    final h = AuthHarness()..signedInAs('u1');
    h.session.refreshGate = Completer<void>();
    final env = _FakeSplashEnvironment(h.session);
    await tester.pumpWidget(_app(h.start(), env));

    await _advance(tester, SplashScreen.bootstrapWaitLimit);
    expect(find.text('route:${RouteNames.main}'), findsOneWidget);
    h.session.refreshGate!.complete();
    await _advance(tester, const Duration(milliseconds: 100));
    h.provider.dispose();
  });

  testWidgets('AUD-16: an unresolved session shows retry, not the login '
      'funnel, and continues by itself when the retry succeeds', (
    tester,
  ) async {
    final h = AuthHarness()..signedInAs('u1');
    h.auth.profileError = FirebaseException(
      plugin: 'cloud_firestore',
      code: 'unavailable',
    );
    final env = _FakeSplashEnvironment(h.session);
    await tester.pumpWidget(
      _app(h.start(retryDelays: const [Duration(seconds: 30)]), env),
    );
    await _advance(tester, const Duration(milliseconds: 1500));

    expect(find.byKey(const ValueKey('splash-retry')), findsOneWidget);
    expect(find.text('route:${RouteNames.terms}'), findsNothing);
    expect(env.routeResolutions, 0);
    expect(h.auth.signOutCalls, 0);

    // The provider's own bounded retry succeeds: Splash follows.
    h.auth.profileError = null;
    await _advance(tester, const Duration(seconds: 30));

    expect(find.text('route:${RouteNames.main}'), findsOneWidget);
    expect(h.auth.signOutCalls, 0);
    h.provider.dispose();
  });

  testWidgets('the retry button resolves the session and routes', (
    tester,
  ) async {
    final h = AuthHarness()..signedInAs('u1');
    h.auth.profileError = StateError('boom');
    final env = _FakeSplashEnvironment(h.session);
    await tester.pumpWidget(_app(h.start(retryDelays: const []), env));
    await _advance(tester, const Duration(milliseconds: 1500));
    expect(find.byKey(const ValueKey('splash-retry')), findsOneWidget);

    // Still failing: the retry state comes back, nobody is signed out.
    await tester.tap(find.byKey(const ValueKey('splash-retry')));
    await _advance(tester, const Duration(milliseconds: 100));
    expect(find.byKey(const ValueKey('splash-retry')), findsOneWidget);
    expect(h.auth.signOutCalls, 0);

    h.auth.profileError = null;
    await tester.tap(find.byKey(const ValueKey('splash-retry')));
    await _advance(tester, const Duration(milliseconds: 100));
    expect(find.text('route:${RouteNames.main}'), findsOneWidget);
    h.provider.dispose();
  });

  testWidgets('a routing failure with a session attached shows retry '
      '(the old splash sent the user to terms)', (tester) async {
    final h = AuthHarness()..signedInAs('u1');
    final env = _FakeSplashEnvironment(h.session)
      ..restrictionError = FirebaseException(
        plugin: 'cloud_firestore',
        code: 'unavailable',
      );
    await tester.pumpWidget(_app(h.start(), env));
    await _advance(tester, const Duration(milliseconds: 1500));

    expect(find.byKey(const ValueKey('splash-retry')), findsOneWidget);
    expect(find.text('route:${RouteNames.terms}'), findsNothing);

    env.restrictionError = null;
    await tester.tap(find.byKey(const ValueKey('splash-retry')));
    await _advance(tester, const Duration(milliseconds: 100));
    expect(find.text('route:${RouteNames.main}'), findsOneWidget);
    h.provider.dispose();
  });

  testWidgets('"verify your email again" for an account the server just '
      'reported verified is a failed read: retry', (tester) async {
    final h = AuthHarness()..signedInAs('u1');
    final env = _FakeSplashEnvironment(h.session)
      ..nextRoute = RouteNames.studentVerification;
    await tester.pumpWidget(_app(h.start(), env));
    await _advance(tester, const Duration(milliseconds: 1500));

    expect(find.byKey(const ValueKey('splash-retry')), findsOneWidget);
    expect(find.text('route:${RouteNames.studentVerification}'), findsNothing);
    h.provider.dispose();
  });

  testWidgets('an unverified account is still sent to verification', (
    tester,
  ) async {
    final h = AuthHarness()
      ..signedInAs('u1', profile: const {'isStudentVerified': false});
    final env = _FakeSplashEnvironment(h.session)
      ..nextRoute = RouteNames.studentVerification;
    await tester.pumpWidget(_app(h.start(), env));
    await _advance(tester, const Duration(milliseconds: 1500));

    expect(
      find.text('route:${RouteNames.studentVerification}'),
      findsOneWidget,
    );
    h.provider.dispose();
  });

  testWidgets('a rejoin-restricted account still goes to terms', (
    tester,
  ) async {
    final h = AuthHarness()..signedInAs('u1');
    final env = _FakeSplashEnvironment(h.session)..restricted = true;
    await tester.pumpWidget(_app(h.start(), env));
    await _advance(tester, const Duration(milliseconds: 1500));

    expect(find.text('route:${RouteNames.terms}'), findsOneWidget);
    h.provider.dispose();
  });

  testWidgets('the retry state has an explicit sign-out exit', (tester) async {
    final h = AuthHarness()..signedInAs('u1');
    h.auth.profileError = StateError('boom');
    final env = _FakeSplashEnvironment(h.session);
    await tester.pumpWidget(_app(h.start(retryDelays: const []), env));
    await _advance(tester, const Duration(milliseconds: 1500));

    await tester.tap(find.byKey(const ValueKey('splash-sign-out')));
    await _advance(tester, const Duration(milliseconds: 100));

    expect(h.auth.signOutCalls, 1);
    expect(find.text('route:${RouteNames.terms}'), findsOneWidget);
    h.provider.dispose();
  });
}
