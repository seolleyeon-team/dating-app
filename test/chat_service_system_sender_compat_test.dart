import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String _readSource(String path) => File(path).readAsStringSync();

void main() {
  group('chat service system sender compatibility', () {
    test('root chat service has no legacy client system-message writer', () {
      final source = _readSource('lib/services/chat_service.dart');

      expect(source, isNot(contains('sendSystemMessage')));
      expect(
        source,
        isNot(matches(RegExp(r'''['"]senderId['"]\s*:\s*['"]system['"]'''))),
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
