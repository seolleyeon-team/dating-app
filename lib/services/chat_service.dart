import 'package:cloud_firestore/cloud_firestore.dart';

/// 채팅 Firestore 서비스 (1:1 + 그룹)
class ChatService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  CollectionReference<Map<String, dynamic>> get _roomsRef =>
      _firestore.collection('chat_rooms');

  // ---------------------------------------------------------------------------
  // 채팅방 생성
  // ---------------------------------------------------------------------------

  /// 1:1 채팅방 생성 (매치 성사 시 호출)
  Future<String> createOneToOneRoom({
    required String matchId,
    required List<Map<String, dynamic>> participants,
  }) async {
    final participantIds = participants.map((p) => p['id'] as String).toList();

    final existing = await _roomsRef
        .where('type', isEqualTo: 'one_to_one')
        .where('participantIds', isEqualTo: participantIds)
        .limit(1)
        .get();

    if (existing.docs.isNotEmpty) {
      return existing.docs.first.id;
    }

    final docRef = await _roomsRef.add({
      'type': 'one_to_one',
      'participantIds': participantIds,
      'participants': participants,
      'matchId': matchId,
      'lastMessage': null,
      'createdAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    });
    return docRef.id;
  }

  /// 그룹 채팅방 생성 (3:3 매칭 등)
  Future<String> createGroupRoom({
    required String matchId,
    required List<Map<String, dynamic>> participants,
  }) async {
    final participantIds = participants.map((p) => p['id'] as String).toList();

    final docRef = await _roomsRef.add({
      'type': 'group',
      'participantIds': participantIds,
      'participants': participants,
      'matchId': matchId,
      'lastMessage': null,
      'createdAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    });
    return docRef.id;
  }

  // ---------------------------------------------------------------------------
  // 채팅방 목록
  // ---------------------------------------------------------------------------

  /// 내 채팅방 목록 (실시간 스트림, 최근 대화순)
  Stream<List<Map<String, dynamic>>> myRoomsStream(String userId) {
    return _roomsRef
        .where('participantIds', arrayContains: userId)
        .orderBy('updatedAt', descending: true)
        .snapshots()
        .map((snap) =>
            snap.docs.map((doc) => {'id': doc.id, ...doc.data()}).toList());
  }

  /// 특정 채팅방 정보 조회
  Future<Map<String, dynamic>?> getRoom(String roomId) async {
    final doc = await _roomsRef.doc(roomId).get();
    if (!doc.exists) return null;
    return {'id': doc.id, ...doc.data()!};
  }

  // ---------------------------------------------------------------------------
  // 메시지
  // ---------------------------------------------------------------------------

  /// 메시지 전송 (batch: 메시지 추가 + 채팅방 lastMessage 갱신)
  Future<String> sendMessage({
    required String roomId,
    required String senderId,
    required String content,
    String type = 'text',
  }) async {
    final batch = _firestore.batch();

    final msgRef = _roomsRef.doc(roomId).collection('messages').doc();
    batch.set(msgRef, {
      'senderId': senderId,
      'content': content,
      'type': type,
      'readBy': [senderId],
      'createdAt': FieldValue.serverTimestamp(),
    });

    final roomRef = _roomsRef.doc(roomId);
    batch.update(roomRef, {
      'lastMessage': {
        'content': content,
        'senderId': senderId,
        'type': type,
        'createdAt': Timestamp.now(),
      },
      'updatedAt': FieldValue.serverTimestamp(),
    });

    await batch.commit();
    return msgRef.id;
  }

  /// 시스템 메시지 전송 (매치 안내 등)
  Future<void> sendSystemMessage({
    required String roomId,
    required String content,
  }) async {
    final batch = _firestore.batch();

    final msgRef = _roomsRef.doc(roomId).collection('messages').doc();
    batch.set(msgRef, {
      'senderId': 'system',
      'content': content,
      'type': 'system',
      'readBy': <String>[],
      'createdAt': FieldValue.serverTimestamp(),
    });

    final roomRef = _roomsRef.doc(roomId);
    batch.update(roomRef, {
      'lastMessage': {
        'content': content,
        'senderId': 'system',
        'type': 'system',
        'createdAt': Timestamp.now(),
      },
      'updatedAt': FieldValue.serverTimestamp(),
    });

    await batch.commit();
  }

  /// 메시지 실시간 스트림 (시간순)
  Stream<List<Map<String, dynamic>>> messagesStream(
    String roomId, {
    int limit = 50,
  }) {
    return _roomsRef
        .doc(roomId)
        .collection('messages')
        .orderBy('createdAt', descending: false)
        .limitToLast(limit)
        .snapshots()
        .map((snap) =>
            snap.docs.map((doc) => {'id': doc.id, ...doc.data()}).toList());
  }

  /// 이전 메시지 로드 (페이징)
  Future<List<Map<String, dynamic>>> loadOlderMessages({
    required String roomId,
    required DocumentSnapshot beforeDoc,
    int limit = 30,
  }) async {
    final snap = await _roomsRef
        .doc(roomId)
        .collection('messages')
        .orderBy('createdAt', descending: true)
        .startAfterDocument(beforeDoc)
        .limit(limit)
        .get();

    return snap.docs
        .map((doc) => {'id': doc.id, ...doc.data()})
        .toList()
        .reversed
        .toList();
  }

  // ---------------------------------------------------------------------------
  // 읽음 처리
  // ---------------------------------------------------------------------------

  /// 메시지 읽음 처리 (readBy 배열에 userId 추가)
  Future<void> markMessagesAsRead({
    required String roomId,
    required String userId,
  }) async {
    final unread = await _roomsRef
        .doc(roomId)
        .collection('messages')
        .where('readBy', whereNotIn: [
          [userId]
        ])
        .get();

    if (unread.docs.isEmpty) return;

    final batch = _firestore.batch();
    for (final doc in unread.docs) {
      final readBy = List<String>.from(doc.data()['readBy'] ?? []);
      if (!readBy.contains(userId)) {
        readBy.add(userId);
        batch.update(doc.reference, {'readBy': readBy});
      }
    }
    await batch.commit();
  }

  /// 안 읽은 메시지 수 스트림
  Stream<int> unreadCountStream({
    required String roomId,
    required String userId,
  }) {
    return _roomsRef
        .doc(roomId)
        .collection('messages')
        .snapshots()
        .map((snap) {
      int count = 0;
      for (final doc in snap.docs) {
        final readBy = List<String>.from(doc.data()['readBy'] ?? []);
        if (!readBy.contains(userId)) count++;
      }
      return count;
    });
  }
}
