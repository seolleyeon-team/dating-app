import 'dart:io';

import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/chat/utils/expired_safety_stamp_cancel_gate.dart';
import 'package:seolleyeon/features/chat/utils/safety_stamp_submit_failure.dart';

// The server now judges safety-stamp timing by its own clock:
//  - firestore.rules refuses the client's "expired promise" cancel until
//    server time has passed the window (permission-denied on a fast phone);
//  - submitSafetyStamp refuses with failed-precondition + details.reason.
// Neither may crash, spam the backend, or leave the user without an answer.

FirebaseFunctionsException _refusal(String reason) =>
    FirebaseFunctionsException(
      code: 'failed-precondition',
      message: 'refused',
      details: {'reason': reason},
    );

void main() {
  group('ExpiredSafetyStampCancelGate', () {
    late DateTime now;
    late ExpiredSafetyStampCancelGate gate;

    setUp(() {
      now = DateTime(2026, 11, 21, 12);
      gate = ExpiredSafetyStampCancelGate(now: () => now);
    });

    test(
      'a refused cancel is swallowed and not repeated on every tick',
      () async {
        var calls = 0;
        Future<void> refused() async {
          calls += 1;
          throw FirebaseException(
            plugin: 'cloud_firestore',
            code: 'permission-denied',
          );
        }

        expect(await gate.run('p1', refused), isFalse);
        expect(calls, 1);

        // One-second timer ticks and room snapshots keep asking.
        for (var i = 0; i < 120; i++) {
          now = now.add(const Duration(seconds: 1));
          expect(await gate.run('p1', refused), isFalse);
        }
        expect(calls, 1, reason: 'backed off for retryAfter');

        // After the back-off the server clock may have caught up: one retry.
        now = now.add(gate.retryAfter);
        expect(await gate.run('p1', () async => calls += 1), isTrue);
        expect(calls, 2);
      },
    );

    test('any failure is contained (offline, unexpected)', () async {
      expect(
        await gate.run('p1', () async => throw StateError('offline')),
        isFalse,
      );
      expect(gate.shouldAttempt('p1'), isFalse);
    });

    test('a different promise is not held back by another one', () async {
      await gate.run('p1', () async => throw StateError('refused'));
      var called = false;
      expect(await gate.run('p2', () async => called = true), isTrue);
      expect(called, isTrue);
    });

    test('only one request is in flight', () async {
      var calls = 0;
      Future<void> slow() async {
        calls += 1;
        await Future<void>.delayed(const Duration(milliseconds: 10));
      }

      final first = gate.run('p1', slow);
      expect(await gate.run('p1', slow), isFalse);
      expect(await first, isTrue);
      expect(calls, 1);
    });

    test('success clears the back-off and an empty id is never sent', () async {
      await gate.run('p1', () async => throw StateError('refused'));
      now = now.add(gate.retryAfter);
      expect(await gate.run('p1', () async {}), isTrue);
      expect(gate.shouldAttempt('p1'), isTrue);
      expect(gate.shouldAttempt(''), isFalse);
    });
  });

  group('describeSafetyStampSubmitFailure', () {
    test('each server refusal has its own actionable message', () {
      final seen = <String>{};
      for (final reason in [
        'too_early',
        'too_late',
        'promise_time_missing',
        'meetup_not_completed',
      ]) {
        final notice = describeSafetyStampSubmitFailure(_refusal(reason));
        expect(notice.reason, reason);
        expect(notice.title, isNotEmpty);
        expect(notice.message, isNotEmpty);
        expect(
          notice.message,
          isNot(contains('잠시 후 다시 시도')),
          reason: '$reason is a decision, not a transient error',
        );
        seen.add('${notice.title}|${notice.message}');
      }
      expect(seen, hasLength(4));
    });

    test('a closed window does not invite a retry', () {
      final notice = describeSafetyStampSubmitFailure(_refusal('too_late'));
      expect(notice.message, isNot(contains('다시 시도')));
    });

    test(
      'unknown reasons and other failures fall back to a generic notice',
      () {
        for (final error in <Object>[
          _refusal('something_new'),
          FirebaseFunctionsException(code: 'failed-precondition', message: 'x'),
          FirebaseFunctionsException(code: 'internal', message: 'x'),
          StateError('boom'),
        ]) {
          final notice = describeSafetyStampSubmitFailure(error);
          expect(notice.reason, isNull);
          expect(notice.title, '도장을 찍지 못했어요');
          expect(notice.message, isNotEmpty);
        }
      },
    );

    test('a network failure says so', () {
      final notice = describeSafetyStampSubmitFailure(
        FirebaseFunctionsException(code: 'unavailable', message: 'x'),
      );
      expect(notice.message, contains('네트워크'));
    });
  });

  group('screens', () {
    final stampScreen = File(
      'lib/features/chat/screens/safety_stamp_screen.dart',
    ).readAsStringSync();
    final chatRoom = File(
      'lib/features/chat/screens/chat_room_screen.dart',
    ).readAsStringSync();

    test('both callers cancel through the gate, never bare', () {
      for (final source in [stampScreen, chatRoom]) {
        final call = source.indexOf('cancelExpiredIncompleteSafetyStamp(');
        expect(call, isNonNegative);
        expect(
          RegExp(
            r'_expiredPromiseCancelGate\.run\(\s*[\w.]+,\s*\(\) => '
            r'_chatService\.cancelExpiredIncompleteSafetyStamp\(',
          ).hasMatch(source),
          isTrue,
        );
        expect(
          RegExp(
            'cancelExpiredIncompleteSafetyStamp\\(',
          ).allMatches(source).length,
          1,
        );
      }
    });

    test('a refused stamp is explained with the server reason', () {
      expect(stampScreen, contains('describeSafetyStampSubmitFailure(e)'));
      expect(stampScreen, contains('Text(notice.title)'));
      expect(stampScreen, contains('Text(notice.message)'));
    });

    test('AUD-06: the stamp screen holds and completes the presence', () {
      expect(stampScreen, contains('_verificationService.startPresence('));
      expect(stampScreen, contains('_verificationService.completePresence()'));
      final dispose = stampScreen.substring(
        stampScreen.indexOf('void dispose() {'),
        stampScreen.indexOf('void _subscribeToSafetyStamp()'),
      );
      expect(
        dispose,
        isNot(contains('completePresence')),
        reason: 'the partner may still need to find this device',
      );
    });
  });
}
