import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
// ignore: depend_on_referenced_packages
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/constants/profile_options.dart';
import 'package:seolleyeon/features/onboarding/screens/keyword_screen.dart';
import 'package:seolleyeon/features/onboarding/screens/lifestyle_screen.dart';
import 'package:seolleyeon/features/onboarding/screens/profile_qa_screen.dart';
import 'package:seolleyeon/features/onboarding/services/onboarding_step_save_guard.dart';
import 'package:seolleyeon/router/route_names.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Hosts an onboarding step above a root page and records every named route
/// the step pushes.
class _Host {
  final navigatorKey = GlobalKey<NavigatorState>();
  final pushed = <String>[];

  Widget app() {
    return MaterialApp(
      navigatorKey: navigatorKey,
      home: const Scaffold(body: Text('root page')),
      onGenerateRoute: (settings) {
        pushed.add(settings.name ?? '');
        return MaterialPageRoute<void>(
          settings: settings,
          builder: (_) => Scaffold(body: Text('route ${settings.name}')),
        );
      },
    );
  }

  Future<void> open(WidgetTester tester, Widget step) async {
    await tester.pumpWidget(app());
    unawaited(
      navigatorKey.currentState!.push(
        MaterialPageRoute<void>(builder: (_) => step),
      ),
    );
    await _settle(tester);
  }
}

/// The step screens run no infinite animation, but a bounded pump keeps a
/// regression from holding the test until its timeout.
Future<void> _settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 600));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    setupFirebaseCoreMocks();
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp();
    }
  });

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('OnboardingStepSaveGuard', () {
    test('a second run while one is in flight does not save again', () async {
      final guard = OnboardingStepSaveGuard();
      final gate = Completer<void>();
      var saves = 0;
      Future<void> save() {
        saves += 1;
        return gate.future;
      }

      final first = guard.run(save, tag: 'test');
      expect(guard.inFlight, isTrue);
      expect(
        await guard.run(save, tag: 'test'),
        OnboardingStepSaveOutcome.alreadyRunning,
      );
      gate.complete();
      expect(await first, OnboardingStepSaveOutcome.saved);
      expect(saves, 1);
      expect(guard.inFlight, isFalse);
    });

    test('a failed save releases the guard', () async {
      final guard = OnboardingStepSaveGuard();
      expect(
        await guard.run(() async => throw StateError('denied'), tag: 'test'),
        OnboardingStepSaveOutcome.failed,
      );
      expect(guard.inFlight, isFalse);
      expect(
        await guard.run(() async {}, tag: 'test'),
        OnboardingStepSaveOutcome.saved,
      );
    });

    test('a save that never finishes is reported as failed', () async {
      final guard = OnboardingStepSaveGuard(
        timeout: const Duration(milliseconds: 20),
      );
      expect(
        await guard.run(() => Completer<void>().future, tag: 'test'),
        OnboardingStepSaveOutcome.failed,
      );
      expect(guard.inFlight, isFalse);
    });
  });

  group('keyword step', () {
    final keyword = profileKeywordOptions.first;

    testWidgets('a second tap during the save neither saves nor navigates '
        'again', (tester) async {
      final host = _Host();
      final gate = Completer<void>();
      var saves = 0;
      await host.open(
        tester,
        KeywordScreen(
          saveKeywords: (_) {
            saves += 1;
            return gate.future;
          },
        ),
      );

      await tester.tap(find.text(keyword));
      await tester.pump();
      await tester.tap(find.text('저장 (1/8)'));
      await tester.pump();
      await tester.tap(find.text('저장 (1/8)'), warnIfMissed: false);
      await tester.pump();

      expect(saves, 1);
      expect(host.pushed, isEmpty, reason: 'no navigation before the save');

      gate.complete();
      await _settle(tester);

      expect(saves, 1);
      expect(host.pushed, [RouteNames.onboardingIdealType]);
    });

    testWidgets('a failed save is reported and the button works again', (
      tester,
    ) async {
      final host = _Host();
      var saves = 0;
      await host.open(
        tester,
        KeywordScreen(
          saveKeywords: (_) async {
            saves += 1;
            if (saves == 1) throw StateError('permission-denied');
          },
        ),
      );

      await tester.tap(find.text(keyword));
      await tester.pump();
      await tester.tap(find.text('저장 (1/8)'));
      await _settle(tester);

      expect(find.text('저장하지 못했어요'), findsOneWidget);
      expect(host.pushed, isEmpty);

      await tester.tap(find.text('확인'));
      await _settle(tester);
      await tester.tap(find.text('저장 (1/8)'));
      await _settle(tester);

      expect(saves, 2);
      expect(host.pushed, [RouteNames.onboardingIdealType]);
    });

    testWidgets('a save that never completes releases the button', (
      tester,
    ) async {
      final host = _Host();
      var saves = 0;
      await host.open(
        tester,
        KeywordScreen(
          saveKeywords: (_) {
            saves += 1;
            return Completer<void>().future;
          },
        ),
      );

      await tester.tap(find.text(keyword));
      await tester.pump();
      await tester.tap(find.text('저장 (1/8)'));
      await tester.pump(const Duration(seconds: 16));
      await _settle(tester);

      expect(find.text('저장하지 못했어요'), findsOneWidget);
      expect(host.pushed, isEmpty);

      await tester.tap(find.text('확인'));
      await _settle(tester);
      await tester.tap(find.text('저장 (1/8)'));
      await tester.pump();
      expect(saves, 2);

      // Let the second save time out too so no timer outlives the test.
      await tester.pump(const Duration(seconds: 16));
      await _settle(tester);
    });

    testWidgets('a save finishing after the screen is gone does nothing', (
      tester,
    ) async {
      final host = _Host();
      final gate = Completer<void>();
      await host.open(tester, KeywordScreen(saveKeywords: (_) => gate.future));

      await tester.tap(find.text(keyword));
      await tester.pump();
      await tester.tap(find.text('저장 (1/8)'));
      await tester.pump();

      await tester.pumpWidget(const SizedBox.shrink());
      gate.complete();
      await _settle(tester);

      expect(tester.takeException(), isNull);
      expect(host.pushed, isEmpty);
    });

    testWidgets('back still leaves the step when the save fails', (
      tester,
    ) async {
      final host = _Host();
      await host.open(
        tester,
        KeywordScreen(
          saveKeywords: (_) async => throw StateError('permission-denied'),
        ),
      );
      expect(find.text('root page'), findsNothing);

      await tester.binding.handlePopRoute();
      await _settle(tester);

      expect(tester.takeException(), isNull);
      expect(find.text('root page'), findsOneWidget);
    });
  });

  group('profile Q&A step', () {
    testWidgets('a second tap during the save neither saves nor navigates '
        'again', (tester) async {
      final host = _Host();
      final gate = Completer<void>();
      var saves = 0;
      await host.open(
        tester,
        ProfileQaScreen(
          saveProfileQa: (_) {
            saves += 1;
            return gate.future;
          },
        ),
      );

      final next = find.text('그냥 넘어갈게요');
      await tester.ensureVisible(next);
      await tester.pump();
      await tester.tap(next);
      await tester.pump();
      await tester.tap(next, warnIfMissed: false);
      await tester.pump();

      expect(saves, 1);
      expect(host.pushed, isEmpty, reason: 'no navigation before the save');

      gate.complete();
      await _settle(tester);

      expect(saves, 1);
      expect(host.pushed, [RouteNames.onboardingKeywords]);
    });

    testWidgets('a failed save is reported and the button works again', (
      tester,
    ) async {
      final host = _Host();
      var saves = 0;
      await host.open(
        tester,
        ProfileQaScreen(
          saveProfileQa: (_) async {
            saves += 1;
            if (saves == 1) throw StateError('permission-denied');
          },
        ),
      );

      final next = find.text('그냥 넘어갈게요');
      await tester.ensureVisible(next);
      await tester.pump();
      await tester.tap(next);
      await _settle(tester);

      expect(find.text('저장하지 못했어요'), findsOneWidget);
      expect(host.pushed, isEmpty);

      await tester.tap(find.text('확인'));
      await _settle(tester);
      await tester.tap(next);
      await _settle(tester);

      expect(saves, 2);
      expect(host.pushed, [RouteNames.onboardingKeywords]);
    });
  });

  group('lifestyle step', () {
    testWidgets('a second tap during the save neither saves nor navigates '
        'again', (tester) async {
      final host = _Host();
      final gate = Completer<void>();
      var saves = 0;
      await host.open(
        tester,
        LifestyleScreen(
          saveLifestyle:
              ({
                required drinking,
                required smoking,
                required exercise,
                required religion,
              }) {
                saves += 1;
                return gate.future;
              },
        ),
      );

      final next = find.text('다음');
      await tester.tap(next);
      await tester.pump();
      await tester.tap(next, warnIfMissed: false);
      await tester.pump();

      expect(saves, 1);
      expect(host.pushed, isEmpty, reason: 'no navigation before the save');

      gate.complete();
      await _settle(tester);

      expect(saves, 1);
      expect(host.pushed, [RouteNames.onboardingMajor]);
    });

    testWidgets('a failed save is reported and the button works again', (
      tester,
    ) async {
      final host = _Host();
      var saves = 0;
      await host.open(
        tester,
        LifestyleScreen(
          saveLifestyle:
              ({
                required drinking,
                required smoking,
                required exercise,
                required religion,
              }) async {
                saves += 1;
                if (saves == 1) throw StateError('permission-denied');
              },
        ),
      );

      final next = find.text('다음');
      await tester.tap(next);
      await _settle(tester);

      expect(find.text('저장하지 못했어요'), findsOneWidget);
      expect(host.pushed, isEmpty);

      await tester.tap(find.text('확인'));
      await _settle(tester);
      await tester.tap(next);
      await _settle(tester);

      expect(saves, 2);
      expect(host.pushed, [RouteNames.onboardingMajor]);
    });
  });
}
