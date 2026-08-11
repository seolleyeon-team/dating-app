import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/matching/models/ai_preference_models.dart';
import 'package:seolleyeon/features/matching/services/ai_preference_deck.dart';
import 'package:seolleyeon/features/matching/services/ai_preference_identity_session.dart';

AiPreferenceIdentity _identity(String id) =>
    AiPreferenceIdentity.fromIdentityId(id);

void main() {
  test('one identity always exposes exactly three visual evidence shots', () {
    final session = AiPreferenceIdentitySessionController(
      identities: [_identity('male_007')],
    );

    expect(session.currentShots, hasLength(3));
    expect(
      session.currentShots.map((shot) => shot.shotType).toSet(),
      aiPreferenceShotTypes.toSet(),
    );
    expect(session.currentIdentityId, 'male_007');
  });

  test('side taps only browse shots and emit no decision event', () {
    var writeCount = 0;
    final session = AiPreferenceIdentitySessionController(
      identities: [_identity('female_123')],
      onDecision: (_) async => writeCount++,
    );

    expect(session.currentShotIndex, 0);
    expect(session.browseNextShot(), isTrue);
    expect(session.browseNextShot(), isTrue);
    expect(session.browsePreviousShot(), isTrue);
    expect(session.currentShotIndex, 1);
    expect(writeCount, 0);
    expect(session.isDecisionInFlight, isFalse);
  });

  for (final shotIndex in [0, 1, 2]) {
    test(
      'Heart on shot ${shotIndex + 1} commits one identity LIKE and advances',
      () async {
        final writes = <AiPreferenceDecisionCommit>[];
        final session = AiPreferenceIdentitySessionController(
          identities: [_identity('male_007'), _identity('female_123')],
          onDecision: (commit) async => writes.add(commit),
        );

        for (var index = 0; index < shotIndex; index++) {
          expect(session.browseNextShot(), isTrue);
        }

        final commit = session.submitDecision(eventType: 'like');
        expect(commit, isNotNull);
        expect(commit!.identityId, 'male_007');
        expect(commit.eventType, 'like');
        expect(commit.presentedShotTypes, hasLength(3));
        expect(writes, hasLength(1));

        expect(session.advanceAfterDecision('male_007'), isTrue);
        expect(session.currentIdentityId, 'female_123');
        await Future<void>.delayed(Duration.zero);
        expect(writes, hasLength(1));
      },
    );
  }

  test(
    'X commits one identity NOPE and advances without deciding remaining shots',
    () {
      final writes = <AiPreferenceDecisionCommit>[];
      final session = AiPreferenceIdentitySessionController(
        identities: [_identity('female_123'), _identity('male_007')],
        onDecision: (commit) async => writes.add(commit),
      );

      expect(session.browseNextShot(), isTrue);
      final commit = session.submitDecision(eventType: 'nope');

      expect(commit!.eventType, 'nope');
      expect(commit.shotCount, 3);
      expect(session.advanceAfterDecision('female_123'), isTrue);
      expect(session.currentIdentityId, 'male_007');
      expect(writes, hasLength(1));
    },
  );

  test(
    'duplicate buttons, swipe races, and duplicate animation callbacks commit once',
    () {
      final writes = <AiPreferenceDecisionCommit>[];
      final session = AiPreferenceIdentitySessionController(
        identities: [_identity('male_007'), _identity('female_123')],
        onDecision: (commit) async => writes.add(commit),
      );

      final first = session.submitDecision(eventType: 'like');
      final secondButton = session.submitDecision(eventType: 'like');
      final swipeRace = session.submitDecision(eventType: 'nope');
      final staleCallback = session.submitDecision(
        identityId: 'male_007',
        eventType: 'like',
      );

      expect(first, isNotNull);
      expect(secondButton, isNull);
      expect(swipeRace, isNull);
      expect(staleCallback, isNull);
      expect(writes, hasLength(1));
      expect(session.advanceAfterDecision('male_007'), isTrue);
      expect(session.advanceAfterDecision('male_007'), isFalse);
      expect(session.currentIdentityId, 'female_123');
    },
  );

  test(
    'decision is terminal and cannot be changed by browsing remaining shots',
    () {
      final session = AiPreferenceIdentitySessionController(
        identities: [_identity('male_007'), _identity('female_123')],
      );

      final commit = session.submitDecision(eventType: 'like');
      expect(commit, isNotNull);
      expect(session.browseNextShot(), isFalse);
      expect(session.browsePreviousShot(), isFalse);
      expect(session.submitDecision(eventType: 'nope'), isNull);
    },
  );

  test(
    'one identity order is stable while the next identity gets its own order',
    () {
      final builder = AiPreferenceDeckBuilder(random: _FixedRandom());
      final session = AiPreferenceIdentitySessionController(
        identities: [_identity('male_007'), _identity('female_123')],
        deckBuilder: builder,
      );

      final firstOrder = session.currentShots
          .map((shot) => shot.shotType)
          .toList();
      session.browseNextShot();
      final sameIdentityOrder = session.currentShots
          .map((shot) => shot.shotType)
          .toList();
      expect(sameIdentityOrder, firstOrder);

      session.submitDecision(eventType: 'like');
      session.advanceAfterDecision('male_007');
      final nextOrder = session.currentShots
          .map((shot) => shot.shotType)
          .toList();
      expect(nextOrder, isNot(firstOrder));
    },
  );
}

class _FixedRandom implements Random {
  @override
  bool nextBool() => false;

  @override
  double nextDouble() => 0;

  @override
  int nextInt(int max) => 0;
}
