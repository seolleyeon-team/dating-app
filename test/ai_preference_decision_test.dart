import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/matching/models/ai_preference_models.dart';
import 'package:seolleyeon/features/matching/services/ai_preference_deck.dart';

void main() {
  test('identity decision gate commits LIKE once from any presented shot', () {
    final identity = AiPreferenceIdentity.fromIdentityId('female_007');
    final gate = AiPreferenceIdentityDecisionGate(
      identityId: identity.identityId,
      presentedShotTypes: identity.images.map((image) => image.shotType),
    );

    final commit = gate.commit(eventType: 'like', position: 2);

    expect(commit, isNotNull);
    expect(commit!.identityId, 'female_007');
    expect(commit.eventType, 'like');
    expect(commit.position, 2);
    expect(commit.presentedShotTypes, hasLength(3));
    expect(gate.isTerminal, isTrue);
  });

  test(
    'identity decision gate rejects duplicate and conflicting submissions',
    () {
      final gate = AiPreferenceIdentityDecisionGate(
        identityId: 'male_123',
        presentedShotTypes: aiPreferenceShotTypes,
      );

      expect(gate.commit(eventType: 'nope', position: 0), isNotNull);
      expect(gate.commit(eventType: 'nope', position: 0), isNull);
      expect(gate.commit(eventType: 'like', position: 0), isNull);
    },
  );

  test('identity decision gate validates event type before terminal lock', () {
    final gate = AiPreferenceIdentityDecisionGate(
      identityId: 'male_123',
      presentedShotTypes: aiPreferenceShotTypes,
    );

    expect(
      () => gate.commit(eventType: 'impression', position: 0),
      throwsArgumentError,
    );
    expect(gate.isTerminal, isFalse);
  });
}
