const fs = require('fs');

function read(path) {
  return fs.readFileSync(path, 'utf8');
}

function write(path, content) {
  fs.writeFileSync(path, content);
}

function replaceExactly(content, pattern, replacement, expected, label) {
  const matches = content.match(pattern) ?? [];
  if (matches.length !== expected) {
    throw new Error(`${label}: expected ${expected} matches, found ${matches.length}`);
  }
  return content.replace(pattern, replacement);
}

const chatPath = 'lib/features/chat/services/chat_service.dart';
let chat = read(chatPath);
chat = replaceExactly(
  chat,
  /^    final cancelledMessageRef = roomRef\.collection\('messages'\)\.doc\(\);\r?\n/mg,
  '',
  1,
  'cancelled message reference'
);
chat = replaceExactly(
  chat,
  /^      tx\.set\(cancelledMessageRef, \{\r?\n[\s\S]*?^      \}\);\r?\n\r?\n/mg,
  '',
  1,
  'cancelled system message write'
);
write(chatPath, chat);

const resolverPath = 'lib/shared/utils/profile_display_image_resolver.dart';
let resolver = read(resolverPath);
resolver = replaceExactly(
  resolver,
  /seolleyeon\(\?:-final\)\?/g,
  'seolleyeon(?:-final|-festival)?',
  2,
  'private bucket regex'
);
write(resolverPath, resolver);

const chatTestPath = 'test/chat_service_system_sender_compat_test.dart';
const chatTest = `import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String _readSource(String path) => File(path).readAsStringSync();

void main() {
  group('chat service system sender compatibility', () {
    test('root chat service has no legacy client system-message writer', () {
      final source = _readSource('lib/services/chat_service.dart');

      expect(source, isNot(contains('sendSystemMessage')));
      expect(source, isNot(contains("'senderId': 'system'")));
    });

    test('feature chat service has no client system-message writer', () {
      final source = _readSource('lib/features/chat/services/chat_service.dart');

      expect(source, isNot(contains("'senderId': 'system'")));
      expect(source, isNot(contains('cancelledMessageRef')));
    });
  });
}
`;
write(chatTestPath, chatTest);

const resolverTestPath = 'test/profile_display_image_resolver_test.dart';
let resolverTest = read(resolverTestPath);
const existing = "      'https://seolleyeon-final-chat-profile-photos.storage.googleapis.com/users/u/chat/photo.jpg',";
const expanded = `${existing}\n      'https://seolleyeon-festival-private-source-photos.storage.googleapis.com/users/u/source/src.jpg',\n      'https://seolleyeon-festival-avatar-temp.storage.googleapis.com/users/u/jobs/j/candidates/c.png',\n      'https://seolleyeon-festival-chat-profile-photos.storage.googleapis.com/users/u/chat/photo.jpg',`;
resolverTest = replaceExactly(
  resolverTest,
  new RegExp(existing.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'),
  expanded,
  1,
  'festival private bucket test cases'
);
write(resolverTestPath, resolverTest);
