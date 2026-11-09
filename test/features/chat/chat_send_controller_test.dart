import 'dart:async';

import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/chat/services/chat_send_controller.dart';

/// P1-11 — a failed send never destroys the unsent text, retries are
/// idempotent, double taps are ignored, and drafts never cross rooms.
class _FakeSender {
  final List<Map<String, String>> calls = [];
  Object? nextError;
  Completer<void>? gate;

  Future<void> call({
    required String roomId,
    required String senderId,
    required String text,
    required String clientMessageId,
  }) async {
    calls.add({
      'roomId': roomId,
      'senderId': senderId,
      'text': text,
      'clientMessageId': clientMessageId,
    });
    if (gate != null) await gate!.future;
    final error = nextError;
    if (error != null) {
      nextError = null;
      throw error;
    }
  }
}

ChatSendController _controller(_FakeSender sender) {
  var seq = 0;
  final c = ChatSendController(
    send: sender.call,
    clientMessageIdFactory: () => 'cmid-${++seq}',
  );
  c.bindContext(roomId: 'dm_a_b', senderId: 'a');
  return c;
}

void main() {
  test('a successful send clears the pending attempt', () async {
    final sender = _FakeSender();
    final c = _controller(sender);
    final result = await c.submit('  안녕  ');
    expect(result.isSent, isTrue);
    expect(sender.calls.single['text'], '안녕');
    expect(sender.calls.single['clientMessageId'], 'cmid-1');
    expect(c.failedSend, isNull);
  });

  test(
    'network failure keeps the draft and restores it only into an empty composer',
    () async {
      final sender = _FakeSender()
        ..nextError = FirebaseFunctionsException(
          code: 'unavailable',
          message: 'x',
        );
      final c = _controller(sender);
      final result = await c.submit('잃어버리면 안 되는 문장');
      expect(result.isFailed, isTrue);
      expect(result.userMessage, '네트워크가 불안정해요. 다시 시도해주세요.');
      expect(c.failedSend?.text, '잃어버리면 안 되는 문장');
      expect(c.draftToRestore(currentInput: ''), '잃어버리면 안 되는 문장');
      expect(c.draftToRestore(currentInput: '   '), '잃어버리면 안 되는 문장');
      expect(
        c.draftToRestore(currentInput: '새로 쓰는 중'),
        isNull,
        reason: 'newer input is never overwritten',
      );
    },
  );

  test(
    'retry — and re-submitting the restored text — re-use the same clientMessageId (no duplicate after a timeout)',
    () async {
      final sender = _FakeSender()
        ..nextError = FirebaseFunctionsException(
          code: 'deadline-exceeded',
          message: 'timeout',
        );
      final c = _controller(sender);
      expect((await c.submit('같은 메시지')).isFailed, isTrue);
      final firstId = sender.calls.single['clientMessageId'];

      expect((await c.retry()).isSent, isTrue);
      expect(sender.calls[1]['clientMessageId'], firstId);
      expect(c.failedSend, isNull);

      // Fail again, then the user presses send on the restored draft.
      sender.nextError = FirebaseFunctionsException(
        code: 'unavailable',
        message: 'x',
      );
      expect((await c.submit('같은 메시지')).isFailed, isTrue);
      final secondId = sender.calls[2]['clientMessageId'];
      expect(
        secondId,
        isNot(firstId),
        reason: 'a new logical message gets a new id',
      );
      expect((await c.submit('같은 메시지')).isSent, isTrue);
      expect(
        sender.calls[3]['clientMessageId'],
        secondId,
        reason: 'identical restored text = same attempt',
      );

      // An edited text is a different message.
      expect((await c.submit('다른 메시지')).isSent, isTrue);
      expect(sender.calls[4]['clientMessageId'], isNot(secondId));
    },
  );

  test(
    'a double tap while a send is in flight is ignored; the second tap sends nothing',
    () async {
      final sender = _FakeSender()..gate = Completer<void>();
      final c = _controller(sender);
      final first = c.submit('한 번만');
      expect(c.isSending, isTrue);
      final second = await c.submit('한 번만');
      expect(second.status, ChatSendStatus.ignored);
      sender.gate!.complete();
      expect((await first).isSent, isTrue);
      expect(sender.calls, hasLength(1));
    },
  );

  test(
    'closed room, blocked peer and permission errors surface short user text, never backend details',
    () async {
      for (final entry in {
        'failed-precondition': '지금은 이 채팅방에 메시지를 보낼 수 없어요.',
        'permission-denied': '메시지를 보낼 권한이 없어요.',
        'not-found': '채팅방을 찾을 수 없어요.',
        'invalid-argument': '보낼 수 없는 내용이 포함되어 있어요.',
      }.entries) {
        final sender = _FakeSender()
          ..nextError = FirebaseFunctionsException(
            code: entry.key,
            message: 'internal detail uid=abc token=xyz',
          );
        final c = _controller(sender);
        final result = await c.submit('hi');
        expect(result.userMessage, entry.value);
        expect(result.userMessage, isNot(contains('token')));
      }
      expect(
        ChatSendController.describeError(StateError('raw')),
        '메시지를 보내지 못했어요. 다시 시도해주세요.',
      );
    },
  );

  test('switching room or account drops the failed draft', () async {
    final sender = _FakeSender()
      ..nextError = FirebaseFunctionsException(
        code: 'unavailable',
        message: 'x',
      );
    final c = _controller(sender);
    expect((await c.submit('방 A 의 초안')).isFailed, isTrue);
    c.bindContext(roomId: 'dm_a_c', senderId: 'a');
    expect(c.failedSend, isNull);
    expect(c.draftToRestore(currentInput: ''), isNull);
    expect((await c.retry()).status, ChatSendStatus.ignored);

    sender.nextError = FirebaseFunctionsException(
      code: 'unavailable',
      message: 'x',
    );
    expect((await c.submit('계정 A 의 초안')).isFailed, isTrue);
    c.bindContext(roomId: 'dm_a_c', senderId: 'z');
    expect(c.failedSend, isNull);
    // Same context again keeps nothing stale either.
    c.bindContext(roomId: 'dm_a_c', senderId: 'z');
    expect(c.failedSend, isNull);
  });

  test(
    'empty text and an unbound context are ignored without calling the server',
    () async {
      final sender = _FakeSender();
      final c = ChatSendController(
        send: sender.call,
        clientMessageIdFactory: () => 'x',
      );
      expect(
        (await c.submit('hello')).status,
        ChatSendStatus.ignored,
        reason: 'no room bound',
      );
      c.bindContext(roomId: 'r', senderId: 's');
      expect((await c.submit('   ')).status, ChatSendStatus.ignored);
      expect(sender.calls, isEmpty);
    },
  );
}
