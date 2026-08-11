import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/matching/models/ai_preference_models.dart';
import 'package:seolleyeon/features/matching/services/ai_preference_deck.dart';

void main() {
  group('AI preference shot deck', () {
    test('defines all six valid permutations', () {
      final permutations = AiPreferenceDeckBuilder.allPermutations;

      expect(permutations, hasLength(6));
      expect(permutations.map(_permutationKey).toSet(), hasLength(6));
      for (final permutation in permutations) {
        expect(permutation, hasLength(3));
        expect(permutation.toSet(), hasLength(3));
        expect(permutation.toSet(), equals(aiPreferenceShotTypes.toSet()));
      }
    });

    test('keeps one identity order stable within a session', () {
      final builder = AiPreferenceDeckBuilder(random: Random(7));
      final identity = AiPreferenceIdentity.fromIdentityId('female_207');

      final first = builder.expand(identity);
      final second = builder.expand(identity);

      expect(
        first.map((image) => image.shotType).toList(),
        second.map((image) => image.shotType).toList(),
      );
      expect(
        first,
        everyElement(
          predicate<AiPreferenceImage>(
            (image) => image.identityId == 'female_207',
          ),
        ),
      );
    });

    test('does not repeat the adjacent newly selected permutation', () {
      final builder = AiPreferenceDeckBuilder(random: _AlwaysZeroRandom());
      final identities = <AiPreferenceIdentity>[
        AiPreferenceIdentity.fromIdentityId('female_1'),
        AiPreferenceIdentity.fromIdentityId('female_2'),
        AiPreferenceIdentity.fromIdentityId('female_3'),
      ];

      final orders = identities
          .map(
            (identity) => identity
                .imagesFor(builder)
                .map((image) => image.shotType)
                .toList(),
          )
          .toList();

      expect(_permutationKey(orders[0]), isNot(_permutationKey(orders[1])));
      expect(_permutationKey(orders[1]), isNot(_permutationKey(orders[2])));
    });

    test('expands each identity into a contiguous three-image group', () {
      final builder = AiPreferenceDeckBuilder(random: Random(17));
      final identities = <AiPreferenceIdentity>[
        AiPreferenceIdentity.fromIdentityId('male_123'),
        AiPreferenceIdentity.fromIdentityId('male_124'),
      ];

      final flattened = identities
          .expand((identity) => identity.imagesFor(builder))
          .toList();

      expect(flattened, hasLength(6));
      expect(
        flattened.take(3).map((image) => image.identityId),
        everyElement('male_123'),
      );
      expect(
        flattened.skip(3).map((image) => image.identityId),
        everyElement('male_124'),
      );
    });
  });
}

extension on AiPreferenceIdentity {
  List<AiPreferenceImage> imagesFor(AiPreferenceDeckBuilder builder) {
    return builder.expand(this);
  }
}

String _permutationKey(Iterable<AiPreferenceShotType> permutation) {
  return permutation.map((shotType) => shotType.name).join('|');
}

class _AlwaysZeroRandom implements Random {
  @override
  bool nextBool() => false;

  @override
  double nextDouble() => 0;

  @override
  int nextInt(int max) => 0;
}
