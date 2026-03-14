import 'package:cloud_firestore/cloud_firestore.dart';

class ChatService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  String buildDirectRoomId(String userA, String userB) {
    final ids = [userA, userB]..sort();
    return 'dm_${ids[0]}_${ids[1]}';
  }

  Stream<QuerySnapshot<Map<String, dynamic>>> chatRoomsStream(String userId) {
    return _firestore
        .collection('chat_rooms')
        .where('participantIds', arrayContains: userId)
        .orderBy('updatedAt', descending: true)
        .snapshots();
  }

  Stream<QuerySnapshot<Map<String, dynamic>>> messagesStream(String roomId) {
    return _firestore
        .collection('chat_rooms')
        .doc(roomId)
        .collection('messages')
        .orderBy('createdAt', descending: false)
        .snapshots();
  }

  Stream<QuerySnapshot<Map<String, dynamic>>> promisesStream(String roomId) {
    return _firestore
        .collection('chat_rooms')
        .doc(roomId)
        .collection('promises')
        .orderBy('createdAt', descending: false)
        .snapshots();
  }

  Stream<DocumentSnapshot<Map<String, dynamic>>> roomStream(String roomId) {
    return _firestore.collection('chat_rooms').doc(roomId).snapshots();
  }

  Future<void> ensureDirectRoom({
    String? roomId,
    required String currentUserId,
    required String partnerId,
    required String currentUserName,
    required String partnerName,
    String? currentUserAvatarUrl,
    String? partnerAvatarUrl,
  }) async {
    final resolvedRoomId = roomId?.isNotEmpty == true
        ? roomId!
        : buildDirectRoomId(currentUserId, partnerId);

    final roomRef = _firestore.collection('chat_rooms').doc(resolvedRoomId);
    final participantIds = [currentUserId, partnerId]..sort();

    final payload = {
      'roomId': resolvedRoomId,
      'participantIds': participantIds,
      'updatedAt': FieldValue.serverTimestamp(),
      'participantInfo': {
        currentUserId: {
          'nickname': currentUserName,
          'avatarUrl': currentUserAvatarUrl ?? '',
        },
        partnerId: {
          'nickname': partnerName,
          'avatarUrl': partnerAvatarUrl ?? '',
        },
      },
    };

    final snap = await roomRef.get();

    if (!snap.exists) {
      await roomRef.set({
        ...payload,
        'createdAt': FieldValue.serverTimestamp(),
        'lastMessage': '',
        'lastMessageAt': null,
      });
      return;
    }

    await roomRef.set(payload, SetOptions(merge: true));
  }

  Future<void> sendTextMessage({
    required String roomId,
    required String senderId,
    required String text,
  }) async {
    final roomRef = _firestore.collection('chat_rooms').doc(roomId);
    final msgRef = roomRef.collection('messages').doc();

    final batch = _firestore.batch();

    batch.set(msgRef, {
      'senderId': senderId,
      'text': text,
      'type': 'text',
      'createdAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    });

    batch.set(roomRef, {
      'lastMessage': text,
      'lastMessageAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));

    await batch.commit();
  }

  Future<String> createPromise({
    required String roomId,
    required String requestedBy,
    required String requestedTo,
    required DateTime dateTime,
    required String place,
    required String placeCategory,
  }) async {
    final roomRef = _firestore.collection('chat_rooms').doc(roomId);
    final promiseRef = roomRef.collection('promises').doc();
    final messageRef = roomRef.collection('messages').doc();

    final batch = _firestore.batch();

    batch.set(promiseRef, {
      'promiseId': promiseRef.id,
      'messageId': messageRef.id,
      'requestedBy': requestedBy,
      'requestedTo': requestedTo,
      'dateTime': Timestamp.fromDate(dateTime),
      'place': place,
      'placeCategory': placeCategory,
      'status': 'requested',
      'createdAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
      'isEdited': false,
      'editedAt': null,
      'acceptedAt': null,
    });

    batch.set(messageRef, {
      'senderId': requestedBy,
      'text': '약속 요청',
      'type': 'promise_request',
      'promiseId': promiseRef.id,
      'dateTime': Timestamp.fromDate(dateTime),
      'place': place,
      'placeCategory': placeCategory,
      'status': 'requested',
      'isEdited': false,
      'editedAt': null,
      'createdAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    });

    batch.set(roomRef, {
      'lastMessage': '약속 요청',
      'lastMessageAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));

    await batch.commit();
    return promiseRef.id;
  }

  Future<void> updatePromise({
    required String roomId,
    required String promiseId,
    required DateTime dateTime,
    required String place,
    required String placeCategory,
  }) async {
    final roomRef = _firestore.collection('chat_rooms').doc(roomId);
    final promiseRef = roomRef.collection('promises').doc(promiseId);

    await _firestore.runTransaction((tx) async {
      final promiseSnap = await tx.get(promiseRef);
      if (!promiseSnap.exists) {
        throw Exception('약속이 존재하지 않습니다.');
      }

      final oldData = promiseSnap.data()!;
      final messageId = oldData['messageId']?.toString();
      final messageRef = messageId != null && messageId.isNotEmpty
          ? roomRef.collection('messages').doc(messageId)
          : null;

      tx.update(promiseRef, {
        'dateTime': Timestamp.fromDate(dateTime),
        'place': place,
        'placeCategory': placeCategory,
        'status': 'requested',
        'acceptedAt': null,
        'updatedAt': FieldValue.serverTimestamp(),
        'isEdited': true,
        'editedAt': FieldValue.serverTimestamp(),
      });

      if (messageRef != null) {
        tx.update(messageRef, {
          'type': 'promise_request',
          'text': '약속 요청',
          'dateTime': Timestamp.fromDate(dateTime),
          'place': place,
          'placeCategory': placeCategory,
          'status': 'requested',
          'updatedAt': FieldValue.serverTimestamp(),
          'isEdited': true,
          'editedAt': FieldValue.serverTimestamp(),
        });
      }

      tx.set(roomRef, {
        'activePromise': FieldValue.delete(),
        'lastMessage': '약속이 수정되었어요',
        'lastMessageAt': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
      }, SetOptions(merge: true));
    });
  }

  Future<void> acceptPromise({
    required String roomId,
    required String promiseId,
  }) async {
    final roomRef = _firestore.collection('chat_rooms').doc(roomId);
    final promiseRef = roomRef.collection('promises').doc(promiseId);

    await _firestore.runTransaction((tx) async {
      final promiseSnap = await tx.get(promiseRef);
      if (!promiseSnap.exists) {
        throw Exception('약속이 존재하지 않습니다.');
      }

      final data = promiseSnap.data()!;
      final messageId = data['messageId']?.toString();
      final messageRef = messageId != null && messageId.isNotEmpty
          ? roomRef.collection('messages').doc(messageId)
          : null;

      final ts = data['dateTime'] as Timestamp?;

      tx.update(promiseRef, {
        'status': 'confirmed',
        'acceptedAt': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
      });

      if (messageRef != null) {
        tx.update(messageRef, {
          'type': 'promise_confirmed',
          'text': '약속이 확정되었어요',
          'status': 'confirmed',
          'updatedAt': FieldValue.serverTimestamp(),
        });
      }

      tx.set(roomRef, {
        'activePromise': {
          'promiseId': promiseId,
          'dateTime': ts,
          'place': data['place'],
          'placeCategory': data['placeCategory'],
          'status': 'confirmed',
        },
        'lastMessage': '약속이 확정되었어요',
        'lastMessageAt': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
      }, SetOptions(merge: true));
    });
  }

  Future<void> rejectPromise({
    required String roomId,
    required String promiseId,
  }) async {
    final roomRef = _firestore.collection('chat_rooms').doc(roomId);
    final promiseRef = roomRef.collection('promises').doc(promiseId);

    await _firestore.runTransaction((tx) async {
      final promiseSnap = await tx.get(promiseRef);
      if (!promiseSnap.exists) {
        throw Exception('약속이 존재하지 않습니다.');
      }

      final data = promiseSnap.data()!;
      final messageId = data['messageId']?.toString();
      final messageRef = messageId != null && messageId.isNotEmpty
          ? roomRef.collection('messages').doc(messageId)
          : null;

      tx.update(promiseRef, {
        'status': 'rejected',
        'updatedAt': FieldValue.serverTimestamp(),
      });

      if (messageRef != null) {
        tx.update(messageRef, {
          'status': 'rejected',
          'updatedAt': FieldValue.serverTimestamp(),
        });
      }

      tx.set(roomRef, {
        'lastMessage': '약속 요청이 거절되었어요',
        'lastMessageAt': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
      }, SetOptions(merge: true));
    });
  }

  Future<void> cancelPromise({
    required String roomId,
    required String promiseId,
  }) async {
    final roomRef = _firestore.collection('chat_rooms').doc(roomId);
    final promiseRef = roomRef.collection('promises').doc(promiseId);
    final deleteMessageRef = roomRef.collection('messages').doc();

    await _firestore.runTransaction((tx) async {
      final promiseSnap = await tx.get(promiseRef);
      if (!promiseSnap.exists) {
        throw Exception('약속이 존재하지 않습니다.');
      }

      final data = promiseSnap.data()!;
      final messageId = data['messageId']?.toString();
      final originalMessageRef = messageId != null && messageId.isNotEmpty
          ? roomRef.collection('messages').doc(messageId)
          : null;

      final requestedBy = data['requestedBy']?.toString() ?? '';
      final promiseDateTime = data['dateTime'];
      final promisePlace = data['place'];
      final promiseCategory = data['placeCategory'];

      tx.update(promiseRef, {
        'status': 'cancelled',
        'updatedAt': FieldValue.serverTimestamp(),
      });

      if (originalMessageRef != null) {
        tx.update(originalMessageRef, {
          'status': 'cancelled',
          'updatedAt': FieldValue.serverTimestamp(),
        });
      }

      tx.set(roomRef, {
        'activePromise': FieldValue.delete(),
        'lastMessage': '약속이 삭제되었어요',
        'lastMessageAt': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
      }, SetOptions(merge: true));

      tx.set(deleteMessageRef, {
        'senderId': requestedBy,
        'type': 'promise_deleted',
        'text': '약속이 삭제되었어요',
        'promiseId': promiseId,
        'dateTime': promiseDateTime,
        'place': promisePlace,
        'placeCategory': promiseCategory,
        'status': 'cancelled',
        'createdAt': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
      });
    });
  }

  Future<DocumentSnapshot<Map<String, dynamic>>?> getUserProfileDoc(
    String userId,
  ) async {
    try {
      return await _firestore.collection('users').doc(userId).get();
    } catch (_) {
      return null;
    }
  }
}
