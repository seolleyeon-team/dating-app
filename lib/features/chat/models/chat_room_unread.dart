/// P0-2: room-level unread state read from `chat_rooms/{roomId}`.
///
/// The server maintains `unreadCounts.{uid}` (one increment per message a
/// participant did not send, system messages included) and stamps
/// `unreadModelVersion: 1` once a room carries those counts. A room without
/// the marker is a legacy room that the backfill has not reached yet; the
/// client reports it as "no unread" rather than scanning its message history
/// — a bounded, explicit fallback (the badge may lag until the backfill runs,
/// it can never cost O(messages) again).
class ChatRoomUnread {
  const ChatRoomUnread({
    required this.roomId,
    required this.unreadCount,
    required this.hasUnreadModel,
  });

  final String roomId;

  /// Unread messages for the current user; 0 when the room has no model yet.
  final int unreadCount;

  /// True when `unreadModelVersion == 1` (server-maintained counts present).
  final bool hasUnreadModel;

  bool get hasUnread => unreadCount > 0;

  static const int modelVersion = 1;

  /// Reads the current user's unread state from a room document's data.
  static ChatRoomUnread fromRoomData(
    String roomId,
    Map<String, dynamic>? data,
    String userId,
  ) {
    final hasModel = data?['unreadModelVersion'] == modelVersion;
    if (!hasModel) {
      return ChatRoomUnread(
        roomId: roomId,
        unreadCount: 0,
        hasUnreadModel: false,
      );
    }
    final rawCounts = data?['unreadCounts'];
    int count = 0;
    if (rawCounts is Map) {
      final value = rawCounts[userId];
      if (value is num && value.isFinite && value > 0) count = value.floor();
    }
    return ChatRoomUnread(
      roomId: roomId,
      unreadCount: count,
      hasUnreadModel: true,
    );
  }
}

/// Aggregate over all of a user's rooms, exposed by `ChatUnreadProvider`.
class ChatUnreadSummary {
  const ChatUnreadSummary(this._byRoom);

  static const ChatUnreadSummary empty = ChatUnreadSummary({});

  final Map<String, ChatRoomUnread> _byRoom;

  bool get hasAnyUnread => _byRoom.values.any((room) => room.hasUnread);

  int unreadCountFor(String roomId) => _byRoom[roomId]?.unreadCount ?? 0;

  bool isRoomUnread(String roomId) => unreadCountFor(roomId) > 0;

  int get roomCount => _byRoom.length;

  static ChatUnreadSummary fromRooms(Iterable<ChatRoomUnread> rooms) {
    return ChatUnreadSummary({for (final room in rooms) room.roomId: room});
  }
}
