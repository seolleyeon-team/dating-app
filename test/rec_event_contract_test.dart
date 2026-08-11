import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/rec_event_contract.dart';

void main() {
  Map<String, dynamic> validPayload() => {
    'userId': 'kakao_a',
    'targetType': 'user_profile',
    'targetId': 'kakao_b',
    'targetUserId': 'kakao_b',
    'candidateUserId': 'kakao_b',
    'type': 'like',
    'eventType': 'like',
    'surface': 'profile_card',
    'source': 'profile_card',
    'cardVariant': 'real_profile',
    'eventTime': '2026-07-31T00:00:00.000Z',
    'createdAt': '2026-07-31T00:00:00.000Z',
    'exposureId': 'exp-1',
    'dateKey': '2026-07-31',
    'schemaVersion': RecEventContract.schemaVersion,
  };

  test('accepts schema v1 like payload', () {
    expect(RecEventContract.validatePayload(validPayload()), isNull);
  });

  test('rejects client-invented scores in context', () {
    final payload = validPayload()..['context'] = {'score': 0.99, 'note': 'x'};
    expect(RecEventContract.validatePayload(payload), 'client_score_forbidden');
  });

  test('rejects type mismatch and self target', () {
    expect(
      RecEventContract.validatePayload(
        validPayload()
          ..['type'] = 'like'
          ..['eventType'] = 'nope',
      ),
      'type_mismatch',
    );
    expect(
      RecEventContract.validatePayload(
        validPayload()
          ..['targetUserId'] = 'kakao_a'
          ..['candidateUserId'] = 'kakao_a',
      ),
      'identity',
    );
  });

  test('accepts identity-level AI decision metadata in context', () {
    final payload = validPayload()
      ..['targetType'] = 'ai_profile'
      ..['targetId'] = 'male_007'
      ..['targetUserId'] = 'male_007'
      ..['candidateUserId'] = 'male_007'
      ..['surface'] = 'ai_preference'
      ..['source'] = 'ai_preference'
      ..['cardVariant'] = 'ai_profile'
      ..['context'] = {
        'decisionScope': 'identity',
        'aiPreferenceImageCount': 3,
        'aiPreferenceSchemaVersion': 2,
      };

    expect(RecEventContract.validatePayload(payload), isNull);
  });

  test('builds a deterministic identity decision event ID', () {
    expect(
      RecEventContract.identityDecisionEventId(
        sessionId: 'session-1',
        identityId: 'male_007',
      ),
      'ai_session-1_male_007',
    );
  });

  test('rejects a shot-level identity event ID', () {
    expect(
      () => RecEventContract.identityDecisionEventId(
        sessionId: 'session-1',
        identityId: 'male_007_face_card',
      ),
      throwsArgumentError,
    );
  });
}
