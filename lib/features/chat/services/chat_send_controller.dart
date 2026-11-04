import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/foundation.dart';

import '../../../shared/utils/privacy_log_utils.dart';
import 'chat_service.dart';

/// One attempted text send: the text, the room/account it belongs to and the
/// sender-scoped idempotency key the server derives the message id from
/// (P1-2). A retry re-uses the key, so an attempt that timed out AFTER the
/// server committed cannot become a second message.
class PendingChatSend {
  PendingChatSend({
    required this.roomId,
    required this.senderId,
    required this.text,
    required this.clientMessageId,
  });

  final String roomId;
  final String senderId;
  final String text;
  final String clientMessageId;
  int attempts = 0;
  String? lastErrorMessage;
}

enum ChatSendStatus { sent, failed, ignored }

class ChatSendResult {
  const ChatSendResult._(this.status, {this.userMessage, this.pending});

  const ChatSendResult.sent() : this._(ChatSendStatus.sent);
  const ChatSendResult.ignored() : this._(ChatSendStatus.ignored);
  const ChatSendResult.failed({
    required String userMessage,
    required PendingChatSend pending,
  }) : this._(
         ChatSendStatus.failed,
         userMessage: userMessage,
         pending: pending,
       );

  final ChatSendStatus status;
  final String? userMessage;
  final PendingChatSend? pending;

  bool get isSent => status == ChatSendStatus.sent;
  bool get isFailed => status == ChatSendStatus.failed;
}

typedef ChatTextSender =
    Future<void> Function({
      required String roomId,
      required String senderId,
      required String text,
      required String clientMessageId,
    });

/// P1-11 — send-failure draft recovery for the chat composer.
///
/// Before: `_handleSend` cleared the input before awaiting the callable and
/// had no error path, so a network failure, a closed room or a block silently
/// destroyed what the user had typed.
///
/// Contract:
///   * one send in flight at a time — a double tap is [ChatSendStatus.ignored];
///   * a failed attempt is kept as [failedSend]; [retry] re-sends it with the
///     SAME clientMessageId, and submitting the identical text again (the
///     restored draft) also re-uses it, so a timeout after a server commit
///     never duplicates the message;
///   * [draftToRestore] returns the failed text only when the input is still
///     empty — newer typing is never overwritten;
///   * [bindContext] drops a pending attempt when the room or the account
///     changes, so a draft never leaks into another conversation;
///   * [describeError] maps server errors to short, user-facing Korean text and
///     never exposes backend exception details.
class ChatSendController {
  ChatSendController({
    required ChatTextSender send,
    String Function()? clientMessageIdFactory,
  }) : _send = send,
       _newId = clientMessageIdFactory ?? ChatService.newClientMessageId;

  final ChatTextSender _send;
  final String Function() _newId;

  bool _inFlight = false;
  PendingChatSend? _pending;
  String _roomId = '';
  String _senderId = '';

  bool get isSending => _inFlight;

  /// The last attempt that failed and has not been sent since, if any.
  PendingChatSend? get failedSend => _inFlight ? null : _pending;

  /// Called whenever the composer's room or account is (re)resolved.
  void bindContext({required String roomId, required String senderId}) {
    if (roomId != _roomId || senderId != _senderId) {
      _pending = null;
    }
    _roomId = roomId;
    _senderId = senderId;
  }

  Future<ChatSendResult> submit(String rawText) async {
    final text = rawText.trim();
    if (text.isEmpty || _roomId.isEmpty || _senderId.isEmpty) {
      return const ChatSendResult.ignored();
    }
    if (_inFlight) return const ChatSendResult.ignored();

    final previous = _pending;
    final attempt =
        previous != null &&
            previous.text == text &&
            previous.roomId == _roomId &&
            previous.senderId == _senderId
        ? previous
        : PendingChatSend(
            roomId: _roomId,
            senderId: _senderId,
            text: text,
            clientMessageId: _newId(),
          );
    return _run(attempt);
  }

  Future<ChatSendResult> retry() async {
    final pending = _pending;
    if (pending == null || _inFlight) return const ChatSendResult.ignored();
    return _run(pending);
  }

  /// Text to put back into the composer after a failure, or null when the
  /// user has typed something new in the meantime.
  String? draftToRestore({required String currentInput}) {
    final pending = _pending;
    if (pending == null || currentInput.trim().isNotEmpty) return null;
    return pending.text;
  }

  /// The user discarded the failed text (edited it away or left the room).
  void discardFailedSend() {
    if (!_inFlight) _pending = null;
  }

  Future<ChatSendResult> _run(PendingChatSend attempt) async {
    _inFlight = true;
    _pending = attempt;
    attempt.attempts += 1;
    try {
      await _send(
        roomId: attempt.roomId,
        senderId: attempt.senderId,
        text: attempt.text,
        clientMessageId: attempt.clientMessageId,
      );
      if (identical(_pending, attempt)) _pending = null;
      return const ChatSendResult.sent();
    } catch (error) {
      debugPrint('[ChatSend] failed ${PrivacyLogUtils.errorSummary(error)}');
      final message = describeError(error);
      attempt.lastErrorMessage = message;
      return ChatSendResult.failed(userMessage: message, pending: attempt);
    } finally {
      _inFlight = false;
    }
  }

  /// User-facing text only; backend messages and codes are never shown raw.
  static String describeError(Object error) {
    if (error is FirebaseFunctionsException) {
      switch (error.code) {
        case 'failed-precondition':
          return '지금은 이 채팅방에 메시지를 보낼 수 없어요.';
        case 'permission-denied':
          return '메시지를 보낼 권한이 없어요.';
        case 'not-found':
          return '채팅방을 찾을 수 없어요.';
        case 'invalid-argument':
          return '보낼 수 없는 내용이 포함되어 있어요.';
        case 'unauthenticated':
          return '다시 로그인한 뒤 시도해주세요.';
        case 'deadline-exceeded':
        case 'unavailable':
          return '네트워크가 불안정해요. 다시 시도해주세요.';
      }
    }
    return '메시지를 보내지 못했어요. 다시 시도해주세요.';
  }
}
