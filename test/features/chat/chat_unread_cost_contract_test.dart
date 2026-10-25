import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// P0-2 static guard: the history-scanning unread/read paths must not come
/// back. Behaviour and cost are proven against the Firestore emulator in
/// functions/src/chatUnread.emulator-test.ts; this test pins the client
/// source so a refactor cannot quietly reintroduce an O(messages) path.
void main() {
  final chatService = File(
    'lib/features/chat/services/chat_service.dart',
  ).readAsStringSync();
  final roomScreen = File(
    'lib/features/chat/screens/chat_room_screen.dart',
  ).readAsStringSync();
  final libFiles = Directory('lib')
      .listSync(recursive: true)
      .whereType<File>()
      .where((f) => f.path.endsWith('.dart'))
      .toList();

  test(
    'the legacy history-scanning unread APIs no longer exist in the client',
    () {
      for (final symbol in [
        'hasAnyUnreadChats(',
        'unreadCountStream(',
        'markMessagesAsRead(',
        'Stream<QuerySnapshot<Map<String, dynamic>>> messagesStream(',
      ]) {
        for (final file in libFiles) {
          final source = file.readAsStringSync();
          // Doc comments may mention the old names; call sites may not.
          final calls = RegExp(
            r'\.' + RegExp.escape(symbol),
          ).allMatches(source);
          expect(calls, isEmpty, reason: '${file.path} still calls $symbol');
        }
      }
    },
  );

  test('the legacy per-message readBy field is neither written nor read', () {
    for (final file in libFiles) {
      final source = file.readAsStringSync();
      expect(
        source.contains("'readBy'") || source.contains('"readBy"'),
        isFalse,
        reason: '${file.path} still references the retired readBy field',
      );
    }
  });

  test('message history is read in bounded pages with a cursor', () {
    expect(chatService, contains('static const int messagePageSize = 50;'));
    expect(chatService, contains('.limit(limit).snapshots()'));
    expect(
      chatService,
      contains('.startAfterDocument(startAfter).limit(limit).get()'),
    );
    // No unbounded message listener anywhere in the service.
    final unbounded = RegExp(
      r"collection\('messages'\)\s*\.orderBy\([^)]*\)\s*\.snapshots\(\)",
    );
    expect(unbounded.hasMatch(chatService), isFalse);
  });

  test('marking a room read is one room-level write of the caller keys', () {
    expect(chatService, contains("FieldPath(['unreadCounts', userId]): 0"));
    expect(
      chatService,
      contains(
        "FieldPath(['lastReadAt', userId]): FieldValue.serverTimestamp()",
      ),
    );
    expect(chatService, isNot(contains('batch.update(doc.reference')));
  });

  test(
    'the room screen owns its streams outside build and gates mark-read on the newest message',
    () {
      expect(
        roomScreen,
        contains(
          '_roomStream = _chatService.roomStream(_roomId).asBroadcastStream();',
        ),
      );
      expect(
        roomScreen,
        contains(
          '_liveMessagesStream = _chatService.latestMessagesStream(_roomId);',
        ),
      );
      expect(
        roomScreen,
        isNot(contains('stream: _chatService.roomStream(_roomId)')),
      );
      expect(
        roomScreen,
        contains('if (newestMessageId == _lastReadMarkedMessageId) return;'),
      );
    },
  );

  test(
    'no screen creates its own unread stream: the provider is the single source',
    () {
      var providerUsers = 0;
      for (final file in libFiles) {
        final source = file.readAsStringSync();
        if (RegExp(
          r'context\s*\.watch<ChatUnreadProvider>\(\)',
        ).hasMatch(source)) {
          providerUsers++;
        }
        expect(
          source.contains('StreamBuilder<bool>(') &&
              source.contains('showChatBadge'),
          isFalse,
          reason: '${file.path} still builds a per-screen unread stream',
        );
      }
      expect(providerUsers, greaterThanOrEqualTo(5));
    },
  );
}
