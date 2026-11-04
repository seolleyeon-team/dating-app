import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// P1-11 — the chat composer no longer discards a draft on failure.
void main() {
  test(
    'chat room screen routes sends through ChatSendController with restore and retry',
    () {
      final src = File(
        'lib/features/chat/screens/chat_room_screen.dart',
      ).readAsStringSync();
      final start = src.indexOf('Future<void> _handleSend() async {');
      expect(start, greaterThan(0));
      final body = src.substring(
        start,
        src.indexOf('Future<void> _retrySend()'),
      );
      expect(body, contains('_sendController.submit(text)'));
      expect(body, contains('_restoreFailedDraft()'));
      expect(body, contains('_showSendFailure('));
      expect(
        body,
        isNot(contains('_chatService.sendTextMessage(')),
        reason: 'all sends go through the controller (idempotency key)',
      );
      expect(src, contains("clientMessageId: clientMessageId,"));
      expect(
        src,
        contains(
          '_sendController.bindContext(roomId: _roomId, senderId: kakaoUserId)',
        ),
      );
      expect(src, contains("label: '다시 시도'"));
      expect(src, contains('draftToRestore('));
    },
  );
}
