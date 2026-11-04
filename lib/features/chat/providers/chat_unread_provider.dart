import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models/chat_room_unread.dart';

/// Source of the user's rooms: one stream of (roomId, room data) lists.
///
/// Injected so the provider is testable without Firestore; the production
/// factory in `app.dart` maps `ChatService.chatRoomsStream(uid)`.
typedef ChatRoomsSource =
    Stream<List<MapEntry<String, Map<String, dynamic>?>>> Function(
      String userId,
    );

/// P0-2: the single app-level source of chat unread state.
///
/// Replaces the five per-tab `StreamBuilder<bool>` badge streams (each
/// re-created on every build and each scanning every message of every room). This provider subscribes ONCE to the user's
/// room documents, derives the badge and per-room counts from the room-level
/// `unreadCounts` maintained by the server, and reads no message documents.
///
/// Cost: O(rooms) documents per room-list change, independent of history.
/// Session: `bindUser(null)` (logout) cancels the subscription and clears the
/// state so nothing survives an account switch.
class ChatUnreadProvider extends ChangeNotifier {
  ChatUnreadProvider({required ChatRoomsSource roomsSource})
    : _roomsSource = roomsSource;

  final ChatRoomsSource _roomsSource;

  String? _userId;
  StreamSubscription<List<MapEntry<String, Map<String, dynamic>?>>>?
  _subscription;
  ChatUnreadSummary _summary = ChatUnreadSummary.empty;
  Object? _lastError;
  bool _disposed = false;

  String? get userId => _userId;
  ChatUnreadSummary get summary => _summary;
  bool get hasAnyUnread => _summary.hasAnyUnread;
  Object? get lastError => _lastError;

  int unreadCountFor(String roomId) => _summary.unreadCountFor(roomId);
  bool isRoomUnread(String roomId) => _summary.isRoomUnread(roomId);

  /// Binds the provider to the signed-in app user. Passing the same id is a
  /// no-op; a different id (or null) tears the previous subscription down and
  /// clears all derived state before anything new is observed.
  void bindUser(String? userId) {
    final next = (userId == null || userId.isEmpty) ? null : userId;
    if (next == _userId) return;
    _subscription?.cancel();
    _subscription = null;
    _userId = next;
    _summary = ChatUnreadSummary.empty;
    _lastError = null;
    if (next == null) {
      _notify();
      return;
    }
    _subscription = _roomsSource(next).listen(
      (rooms) {
        if (_disposed || _userId != next) return;
        _summary = ChatUnreadSummary.fromRooms(
          rooms.map(
            (entry) =>
                ChatRoomUnread.fromRoomData(entry.key, entry.value, next),
          ),
        );
        _lastError = null;
        _notify();
      },
      onError: (Object error) {
        if (_disposed || _userId != next) return;
        // Fail closed for the badge: no unread is shown on an error, and the
        // error is kept for diagnostics instead of being swallowed.
        _summary = ChatUnreadSummary.empty;
        _lastError = error;
        _notify();
      },
    );
    _notify();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _subscription?.cancel();
    _subscription = null;
    super.dispose();
  }
}
