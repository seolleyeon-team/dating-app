// like / nope 는 create-only 이고, 아직 없는 문서는 rules 상 읽을 수 없다.
// 그래서 "먼저 쓰고, 거부됐을 때만 이미 기록됐는지 확인"해야 한다.
// (rules 쪽 계약: rules_tests/firestore.asksinteractions.test.mjs)

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/interaction_service.dart';

FirebaseException _denied() =>
    FirebaseException(plugin: 'cloud_firestore', code: 'permission-denied');

void main() {
  test('첫 기록은 사전 조회 없이 바로 쓴다', () async {
    var creates = 0;
    var reads = 0;

    await InteractionService.writeCreateOnlyDecision(
      create: () async => creates++,
      alreadyRecorded: () async {
        reads++;
        return false;
      },
    );

    expect(creates, 1);
    expect(reads, 0);
  });

  test('이미 기록된 결정의 재시도는 조용히 끝난다', () async {
    await InteractionService.writeCreateOnlyDecision(
      create: () async => throw _denied(),
      alreadyRecorded: () async => true,
    );
  });

  test('기록된 적 없는데 거부되면 오류를 그대로 올린다', () async {
    await expectLater(
      InteractionService.writeCreateOnlyDecision(
        create: () async => throw _denied(),
        alreadyRecorded: () async => false,
      ),
      throwsA(
        isA<FirebaseException>().having(
          (error) => error.code,
          'code',
          'permission-denied',
        ),
      ),
    );
  });

  test('확인 조회까지 거부되면 원래의 거부를 올린다', () async {
    await expectLater(
      InteractionService.writeCreateOnlyDecision(
        create: () async => throw _denied(),
        alreadyRecorded: () async => throw _denied(),
      ),
      throwsA(isA<FirebaseException>()),
    );
  });

  test('권한 외의 실패는 기록 여부를 묻지 않고 올린다', () async {
    var reads = 0;

    await expectLater(
      InteractionService.writeCreateOnlyDecision(
        create: () async => throw FirebaseException(
          plugin: 'cloud_firestore',
          code: 'unavailable',
        ),
        alreadyRecorded: () async {
          reads++;
          return true;
        },
      ),
      throwsA(isA<FirebaseException>()),
    );
    expect(reads, 0);
  });
}
