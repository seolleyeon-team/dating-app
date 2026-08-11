import 'dart:math';

import '../models/ai_preference_models.dart';

class AiPreferenceDeckBuilder {
  AiPreferenceDeckBuilder({Random? random})
    : _random = random ?? Random.secure();

  static const List<List<AiPreferenceShotType>> allPermutations =
      <List<AiPreferenceShotType>>[
        <AiPreferenceShotType>[
          AiPreferenceShotType.faceCard,
          AiPreferenceShotType.vibeCard,
          AiPreferenceShotType.silhouetteCard,
        ],
        <AiPreferenceShotType>[
          AiPreferenceShotType.faceCard,
          AiPreferenceShotType.silhouetteCard,
          AiPreferenceShotType.vibeCard,
        ],
        <AiPreferenceShotType>[
          AiPreferenceShotType.vibeCard,
          AiPreferenceShotType.faceCard,
          AiPreferenceShotType.silhouetteCard,
        ],
        <AiPreferenceShotType>[
          AiPreferenceShotType.vibeCard,
          AiPreferenceShotType.silhouetteCard,
          AiPreferenceShotType.faceCard,
        ],
        <AiPreferenceShotType>[
          AiPreferenceShotType.silhouetteCard,
          AiPreferenceShotType.faceCard,
          AiPreferenceShotType.vibeCard,
        ],
        <AiPreferenceShotType>[
          AiPreferenceShotType.silhouetteCard,
          AiPreferenceShotType.vibeCard,
          AiPreferenceShotType.faceCard,
        ],
      ];

  final Random _random;
  final Map<String, List<AiPreferenceShotType>> _orderByIdentity =
      <String, List<AiPreferenceShotType>>{};
  List<AiPreferenceShotType>? _previousOrder;

  List<AiPreferenceImage> expand(AiPreferenceIdentity identity) {
    final cachedOrder = _orderByIdentity[identity.identityId];
    if (cachedOrder != null) {
      return identity.orderedBy(cachedOrder).images;
    }

    var permutationIndex = _random.nextInt(allPermutations.length);
    final candidate = allPermutations[permutationIndex];
    if (_previousOrder != null && _sameOrder(candidate, _previousOrder!)) {
      permutationIndex = (permutationIndex + 1) % allPermutations.length;
    }

    final selectedOrder = allPermutations[permutationIndex];
    _orderByIdentity[identity.identityId] = selectedOrder;
    _previousOrder = selectedOrder;
    return identity.orderedBy(selectedOrder).images;
  }

  bool _sameOrder(
    Iterable<AiPreferenceShotType> first,
    Iterable<AiPreferenceShotType> second,
  ) {
    final firstList = first.toList();
    final secondList = second.toList();
    if (firstList.length != secondList.length) {
      return false;
    }
    for (var index = 0; index < firstList.length; index++) {
      if (firstList[index] != secondList[index]) {
        return false;
      }
    }
    return true;
  }
}

class AiPreferenceDecisionCommit {
  AiPreferenceDecisionCommit({
    required this.identityId,
    required this.eventType,
    required this.position,
    required Iterable<AiPreferenceShotType> presentedShotTypes,
  }) : presentedShotTypes = List<AiPreferenceShotType>.unmodifiable(
         presentedShotTypes,
       );

  final String identityId;
  final String eventType;
  final int position;
  final List<AiPreferenceShotType> presentedShotTypes;

  int get shotCount => presentedShotTypes.length;
}

/// Terminal identity-level decision gate.
///
/// The gate deliberately accepts the complete presented shot order at
/// construction time. A single action decides the identity; the other shots
/// are evidence only and never become separate events.
class AiPreferenceIdentityDecisionGate {
  AiPreferenceIdentityDecisionGate({
    required this.identityId,
    required Iterable<AiPreferenceShotType> presentedShotTypes,
  }) : presentedShotTypes = List<AiPreferenceShotType>.unmodifiable(
         presentedShotTypes,
       ) {
    if (identityId.trim().isEmpty) {
      throw ArgumentError.value(identityId, 'identityId', 'must not be empty');
    }
    if (this.presentedShotTypes.length != aiPreferenceShotTypes.length ||
        this.presentedShotTypes.toSet().length != aiPreferenceShotTypes.length ||
        !this.presentedShotTypes.every(aiPreferenceShotTypes.contains)) {
      throw ArgumentError.value(
        presentedShotTypes,
        'presentedShotTypes',
        'must contain all three AI preference shots exactly once',
      );
    }
  }

  final String identityId;
  final List<AiPreferenceShotType> presentedShotTypes;
  bool _isTerminal = false;

  bool get isTerminal => _isTerminal;

  AiPreferenceDecisionCommit? commit({
    required String eventType,
    required int position,
  }) {
    if (eventType != 'like' && eventType != 'nope') {
      throw ArgumentError.value(eventType, 'eventType', 'must be like or nope');
    }

    if (_isTerminal) return null;
    _isTerminal = true;

    return AiPreferenceDecisionCommit(
      identityId: identityId,
      eventType: eventType,
      position: position,
      presentedShotTypes: presentedShotTypes,
    );
  }
}
