import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/kakao_login_coordinator.dart';

void main() {
  test(
    'coalesces concurrent Kakao login operations into one SDK call',
    () async {
      final completer = Completer<Map<String, dynamic>>();
      var operationCount = 0;

      final first = KakaoLoginCoordinator.run(() {
        operationCount += 1;
        return completer.future;
      });
      final second = KakaoLoginCoordinator.run(() {
        operationCount += 1;
        return Future.value(<String, dynamic>{'id': 'unexpected'});
      });

      expect(operationCount, 1);
      completer.complete(<String, dynamic>{'id': 'kakao-user'});

      expect(await first, <String, dynamic>{'id': 'kakao-user'});
      expect(await second, <String, dynamic>{'id': 'kakao-user'});
    },
  );

  test('releases the Kakao login gate after a failed operation', () async {
    var operationCount = 0;

    Future<Map<String, dynamic>> operation() async {
      operationCount += 1;
      if (operationCount == 1) {
        throw StateError('login failed');
      }
      return <String, dynamic>{'id': 'retry-success'};
    }

    await expectLater(KakaoLoginCoordinator.run(operation), throwsStateError);
    expect(await KakaoLoginCoordinator.run(operation), {'id': 'retry-success'});
    expect(operationCount, 2);
  });
}
