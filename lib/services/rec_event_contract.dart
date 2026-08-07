/// Versioned client contract for `recEvents/{uid}/events` appends.
///
/// Keep aligned with `firestore.rules` `isValidRecEventCreate` and
/// `rules_tests/firestore.recevents.test.mjs`.
class RecEventContract {
  RecEventContract._();

  static const int schemaVersion = 1;

  static const Set<String> allowedEventTypes = {
    'impression',
    'open',
    'detail_open',
    'view',
    'like',
    'nope',
    'super_like',
    'swipe_right',
    'block',
    'report',
  };

  /// Keys clients may write (must match rules whitelist + schemaVersion).
  static const Set<String> allowedKeys = {
    'userId',
    'targetType',
    'targetId',
    'targetUserId',
    'candidateUserId',
    'type',
    'eventType',
    'surface',
    'source',
    'cardVariant',
    'eventTime',
    'createdAt',
    'exposureId',
    'sessionId',
    'dateKey',
    'context',
    'schemaVersion',
  };

  /// Context keys that look like client-invented ranking scores — rejected.
  static const Set<String> forbiddenContextScoreKeys = {
    'score',
    'rrfScore',
    'clipScore',
    'svdScore',
    'knnScore',
    'rankScore',
    'modelScore',
  };

  static bool isAllowedEventType(String eventType) =>
      allowedEventTypes.contains(eventType);

  static String? validatePayload(Map<String, dynamic> payload) {
    final unknown = payload.keys
        .where((k) => !allowedKeys.contains(k))
        .toList();
    if (unknown.isNotEmpty) {
      return 'unknown_keys:${unknown.join(",")}';
    }

    final schema = payload['schemaVersion'];
    if (schema is! int || schema != schemaVersion) {
      return 'schema_version';
    }

    final type = payload['type']?.toString() ?? '';
    final eventType = payload['eventType']?.toString() ?? '';
    if (type.isEmpty || type != eventType) {
      return 'type_mismatch';
    }
    if (!isAllowedEventType(eventType)) {
      return 'event_type';
    }

    final userId = payload['userId']?.toString() ?? '';
    final targetUserId = payload['targetUserId']?.toString() ?? '';
    if (userId.isEmpty || targetUserId.isEmpty || userId == targetUserId) {
      return 'identity';
    }

    final context = payload['context'];
    if (context is Map) {
      for (final key in context.keys) {
        if (forbiddenContextScoreKeys.contains(key.toString())) {
          return 'client_score_forbidden';
        }
      }
    }

    return null;
  }
}
