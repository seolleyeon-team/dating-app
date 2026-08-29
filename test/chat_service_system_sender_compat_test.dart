import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String _readSource(String path) => File(path).readAsStringSync();

void main() {
  group('chat service system sender compatibility', () {
    test('legacy root chat service stays deleted', () {
      // lib/services/chat_service.dart 는 importer가 없는 dead code였고,
      // 클라이언트가 임의 matchId로 chat_rooms 문서를 만들 수 있는 유일한
      // 경로였다 (시즌 미팅 room 분류 규칙 우회). 부활하면 실패시킨다.
      expect(
        File('lib/services/chat_service.dart').existsSync(),
        isFalse,
        reason: '클라이언트 room 생성 dead code는 다시 추가하면 안 된다',
      );
    });

    test('feature chat service has no client system-message writer', () {
      final source = _readSource(
        'lib/features/chat/services/chat_service.dart',
      );

      expect(
        source,
        isNot(matches(RegExp(r'''['"]senderId['"]\s*:\s*['"]system['"]'''))),
      );
      expect(source, isNot(contains('cancelledMessageRef')));
    });
  });
}
