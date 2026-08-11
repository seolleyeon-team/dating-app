import 'dart:async';

import '../models/ai_preference_models.dart';
import 'ai_preference_deck.dart';

typedef AiPreferenceDecisionSink = Future<void> Function(
  AiPreferenceDecisionCommit commit,
);

/// Owns the identity-level state for the AI preference flow.
///
/// Browsing changes only [currentShotIndex]. A decision terminally locks the
/// current identity before any asynchronous Firestore work starts, so a
/// second button/swipe/animation callback cannot create another commit.
class AiPreferenceIdentitySessionController {
  AiPreferenceIdentitySessionController({
    required Iterable<AiPreferenceIdentity> identities,
    AiPreferenceDeckBuilder? deckBuilder,
    this.onDecision,
  }) : _identities = _buildRuntimes(
         identities,
         deckBuilder ?? AiPreferenceDeckBuilder(),
       ) {
    if (_identities.isEmpty) {
      throw ArgumentError.value(identities, 'identities', 'must not be empty');
    }
  }

  final List<_IdentityRuntime> _identities;
  final AiPreferenceDecisionSink? onDecision;
  int _identityIndex = 0;
  Future<void> _pendingWrite = Future<void>.value();

  static List<_IdentityRuntime> _buildRuntimes(
    Iterable<AiPreferenceIdentity> identities,
    AiPreferenceDeckBuilder deckBuilder,
  ) {
    return identities
        .map(
          (identity) => _IdentityRuntime(
            identity: identity,
            shots: deckBuilder.expand(identity),
          ),
        )
        .toList(growable: false);
  }

  AiPreferenceIdentity get currentIdentity => _current.identity;

  String get currentIdentityId => _current.identity.identityId;

  List<AiPreferenceImage> get currentShots => _current.shots;

  int get currentShotIndex => _current.currentShotIndex;

  AiPreferenceImage get currentShot => _current.shots[currentShotIndex];

  bool get isDecisionInFlight => _current.decisionInFlight;

  bool get isExhausted => _identityIndex >= _identities.length - 1;

  Future<void> get pendingDecisionWrite => _pendingWrite;

  _IdentityRuntime get _current => _identities[_identityIndex];

  bool browseNextShot() {
    if (_current.decisionInFlight || currentShotIndex >= 2) return false;
    _current.currentShotIndex++;
    return true;
  }

  bool browsePreviousShot() {
    if (_current.decisionInFlight || currentShotIndex <= 0) return false;
    _current.currentShotIndex--;
    return true;
  }

  /// Attempts one terminal decision for [identityId].
  ///
  /// When [identityId] is omitted, the current identity is used. Callers
  /// handling an animation should pass the identity captured when the action
  /// started; stale callbacks then safely return null after the deck advances.
  AiPreferenceDecisionCommit? submitDecision({
    required String eventType,
    String? identityId,
  }) {
    if (eventType != 'like' && eventType != 'nope') {
      throw ArgumentError.value(eventType, 'eventType', 'must be like or nope');
    }
    if (identityId != null && identityId != currentIdentityId) return null;

    final commit = _current.tryCommit(
      eventType: eventType,
      position: _identityIndex,
    );
    if (commit == null) return null;

    final sink = onDecision;
    if (sink != null) {
      _pendingWrite = Future<void>.sync(() => sink(commit)).catchError((_) {});
    }
    return commit;
  }

  /// Completes the visual fly-off and moves to the next identity once.
  bool advanceAfterDecision(String identityId) {
    if (identityId != currentIdentityId || !_current.decisionInFlight) {
      return false;
    }
    if (isExhausted) return false;
    _identityIndex++;
    return true;
  }
}

class _IdentityRuntime {
  _IdentityRuntime({required this.identity, required Iterable<AiPreferenceImage> shots})
    : shots = List<AiPreferenceImage>.unmodifiable(shots),
      decisionGate = AiPreferenceIdentityDecisionGate(
        identityId: identity.identityId,
        presentedShotTypes: shots.map((shot) => shot.shotType),
      );

  final AiPreferenceIdentity identity;
  final List<AiPreferenceImage> shots;
  final AiPreferenceIdentityDecisionGate decisionGate;
  int currentShotIndex = 0;

  bool get decisionInFlight => decisionGate.isTerminal;

  AiPreferenceDecisionCommit? tryCommit({
    required String eventType,
    required int position,
  }) {
    return decisionGate.commit(
      eventType: eventType,
      position: position,
    );
  }
}
