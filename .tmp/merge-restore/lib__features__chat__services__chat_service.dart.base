import 'package:cloud_firestore/cloud_firestore.dart';

import '../utils/safety_stamp_availability.dart';

class ChatService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  static Map<String, dynamic> _coerceStringMap(dynamic raw) {
    if (raw is Map) {
      return Map<String, dynamic>.from(raw as Map<Object?, Object?>);
    }
    return <String, dynamic>{};
  }

  static Map<String, dynamic> _promisePlaceExtras({
    String? placeId,
    String? placeAddress,
    double? placeLat,
    double? placeLng,
  }) {
    final m = <String, dynamic>{};
    if (placeId != null && placeId.isNotEmpty) m['placeId'] = placeId;
    if (placeAddress != null && placeAddress.isNotEmpty) {
      m['placeAddress'] = placeAddress;
    }
    if (placeLat != null) m['placeLat'] = placeLat;
    if (placeLng != null) m['placeLng'] = placeLng;
    return m;
  }

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

  Future<bool> cancelExpiredIncompleteSafetyStamp({
    required String roomId,
    required String promiseId,
  }) async {
    final roomRef = _firestore.collection('chat_rooms').doc(roomId);
    final promiseRef = roomRef.collection('promises').doc(promiseId);
    final cancelledMessageRef = roomRef.collection('messages').doc();
    final now = DateTime.now();
    final cancelledMessageText = '약속이 취소되었어요 (${_formatKoreanDateTime(now)})';

    return _firestore.runTransaction((tx) async {
      final roomSnap = await tx.get(roomRef);
      if (!roomSnap.exists) return false;

      final roomData = roomSnap.data() ?? <String, dynamic>{};
      final activePromiseRaw = roomData['activePromise'];
      if (activePromiseRaw is! Map) return false;

      final activePromise = _coerceStringMap(activePromiseRaw);
      final activePromiseId = activePromise['promiseId']?.toString() ?? '';
      if (activePromiseId.isEmpty || activePromiseId != promiseId) {
        return false;
      }
      if (!isMeetupSafetyStampExpired(activePromise, now: now)) {
        return false;
      }

      final promiseSnap = await tx.get(promiseRef);
      if (!promiseSnap.exists) return false;

      final promiseData = promiseSnap.data() ?? <String, dynamic>{};
      final promiseStatus =
          promiseData['status']?.toString().toLowerCase() ?? '';
      if (promiseStatus == 'cancelled' || promiseStatus == 'completed') {
        return false;
      }

      tx.update(promiseRef, {
        'status': 'cancelled',
        'cancelledAt': FieldValue.serverTimestamp(),
        'cancelledReason': 'safety_stamp_timeout',
        'updatedAt': FieldValue.serverTimestamp(),
      });

      tx.set(cancelledMessageRef, {
        'senderId': 'system',
        'text': cancelledMessageText,
        'type': 'promise_deleted',
        'promiseId': promiseId,
        'dateTime': FieldValue.serverTimestamp(),
        'place': activePromise['place'],
        'placeCategory': activePromise['placeCategory'],
        'status': 'cancelled',
        'cancelledReason': 'safety_stamp_timeout',
        'readBy': const <String>[],
        'createdAt': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
      });

      tx.set(roomRef, {
        'activePromise': FieldValue.delete(),
        'lastMessage': cancelledMessageText,
        'lastMessageAt': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
      }, SetOptions(merge: true));

      return true;
    });
  }

  static String _formatKoreanDateTime(DateTime dateTime) {
    final local = dateTime.toLocal();
    final hour12 = local.hour == 0
        ? 12
        : (local.hour > 12 ? local.hour - 12 : local.hour);
    final minute = local.minute.toString().padLeft(2, '0');
    final period = local.hour >= 12 ? '오후' : '오전';
    return '${local.month}월 ${local.day}일 $period $hour12:$minute';
  }

  Future<void> markSafetyStamp({
    required String roomId,
    required String promiseId,
    required String userId,
    required String phase,
    Map<String, dynamic>? verification,
  }) async {
    final roomRef = _firestore.collection('chat_rooms').doc(roomId);
    final promiseRef = roomRef.collection('promises').doc(promiseId);
    final inProgressMessageRef = roomRef.collection('messages').doc();
    final completedMessageRef = roomRef.collection('messages').doc();

    await _firestore.runTransaction((tx) async {
      final roomSnap = await tx.get(roomRef);
      if (!roomSnap.exists) {
        throw Exception('채팅방이 존재하지 않습니다.');
      }

      final roomData = roomSnap.data() ?? <String, dynamic>{};
      final activePromiseRaw = roomData['activePromise'];
      if (activePromiseRaw is! Map) {
        throw Exception('활성 약속이 없습니다.');
      }

      final activePromise = Map<String, dynamic>.from(
        activePromiseRaw as Map<Object?, Object?>,
      );
      final activePromiseId = activePromise['promiseId']?.toString() ?? '';
      if (activePromiseId.isEmpty || activePromiseId != promiseId) {
        throw Exception('현재 활성 약속과 일치하지 않습니다.');
      }

      final safetyStamp = _coerceStringMap(activePromise['safetyStamp']);

      final participantIds =
          (roomData['participantIds'] as List?)
              ?.map((e) => e.toString())
              .where((e) => e.isNotEmpty)
              .toSet() ??
          <String>{};
      if (participantIds.isEmpty) {
        throw Exception('참여자 정보가 없습니다.');
      }

      final meetupStampedUserIds =
          (safetyStamp['meetupStampedUserIds'] as List?)
              ?.map((e) => e.toString())
              .where((e) => e.isNotEmpty)
              .toSet() ??
          <String>{};
      final legacyStampedUserIds =
          (safetyStamp['stampedUserIds'] as List?)
              ?.map((e) => e.toString())
              .where((e) => e.isNotEmpty)
              .toSet() ??
          <String>{};
      final effectiveMeetupStampedUserIds = meetupStampedUserIds.isNotEmpty
          ? meetupStampedUserIds
          : legacyStampedUserIds;
      final goodbyeStampedUserIds =
          (safetyStamp['goodbyeStampedUserIds'] as List?)
              ?.map((e) => e.toString())
              .where((e) => e.isNotEmpty)
              .toSet() ??
          <String>{};

      if (phase == 'goodbye') {
        if (!effectiveMeetupStampedUserIds.containsAll(participantIds)) {
          throw Exception('만남 인증이 아직 완료되지 않았습니다.');
        }
        if (!goodbyeStampedUserIds.add(userId)) {
          return;
        }
      } else {
        if (!effectiveMeetupStampedUserIds.add(userId)) {
          return;
        }
      }

      final nextSafetyStamp = <String, dynamic>{
        ...safetyStamp,
        'meetupStampedUserIds': effectiveMeetupStampedUserIds.toList(),
        'goodbyeStampedUserIds': goodbyeStampedUserIds.toList(),
      };
      if (verification != null) {
        final recordKey = phase == 'goodbye'
            ? 'goodbyeVerificationByUserId'
            : 'meetupVerificationByUserId';
        final verificationByUserId = _coerceStringMap(
          nextSafetyStamp[recordKey],
        );
        verificationByUserId[userId] = verification;
        nextSafetyStamp[recordKey] = verificationByUserId;
      }
      nextSafetyStamp.remove('stampedUserIds');

      activePromise['participantIds'] = participantIds.toList();
      activePromise['safetyStamp'] = nextSafetyStamp;

      tx.update(promiseRef, {
        'participantIds': participantIds.toList(),
        'safetyStamp': nextSafetyStamp,
        'updatedAt': FieldValue.serverTimestamp(),
      });

      if (phase != 'goodbye' &&
          effectiveMeetupStampedUserIds.containsAll(participantIds)) {
        activePromise['status'] = 'in_progress';
        activePromise['safetyStamp'] = {
          ...nextSafetyStamp,
          'meetupCompletedAt': FieldValue.serverTimestamp(),
        };

        tx.update(promiseRef, {
          'safetyStamp': activePromise['safetyStamp'],
          'status': 'in_progress',
          'meetupCompletedAt': FieldValue.serverTimestamp(),
          'updatedAt': FieldValue.serverTimestamp(),
        });

        tx.set(inProgressMessageRef, {
          'senderId': userId,
          'text': '약속을 진행중입니다',
          'type': 'promise_in_progress',
          'promiseId': promiseId,
          'dateTime': FieldValue.serverTimestamp(),
          'place': activePromise['place'],
          'placeCategory': activePromise['placeCategory'],
          'status': 'in_progress',
          'readBy': [userId],
          'createdAt': FieldValue.serverTimestamp(),
          'updatedAt': FieldValue.serverTimestamp(),
        });

        tx.update(roomRef, {
          'activePromise': activePromise,
          'lastMessage': '약속을 진행중입니다',
          'lastMessageAt': FieldValue.serverTimestamp(),
          'updatedAt': FieldValue.serverTimestamp(),
        });
        return;
      }

      if (phase == 'goodbye' &&
          goodbyeStampedUserIds.containsAll(participantIds)) {
        activePromise['status'] = 'completed';
        activePromise['safetyStamp'] = {
          ...nextSafetyStamp,
          'completedAt': FieldValue.serverTimestamp(),
        };

        tx.update(promiseRef, {
          'safetyStamp': activePromise['safetyStamp'],
          'status': 'completed',
          'completedAt': FieldValue.serverTimestamp(),
          'updatedAt': FieldValue.serverTimestamp(),
        });

        tx.set(completedMessageRef, {
          'senderId': userId,
          'text': '약속이 완료되었어요',
          'type': 'promise_completed',
          'promiseId': promiseId,
          'dateTime': FieldValue.serverTimestamp(),
          'place': activePromise['place'],
          'placeCategory': activePromise['placeCategory'],
          'status': 'completed',
          'readBy': [userId],
          'createdAt': FieldValue.serverTimestamp(),
          'updatedAt': FieldValue.serverTimestamp(),
        });

        tx.update(roomRef, {
          'activePromise': activePromise,
          'lastMessage': '약속이 완료되었어요',
          'lastMessageAt': FieldValue.serverTimestamp(),
          'updatedAt': FieldValue.serverTimestamp(),
        });
        return;
      }

      tx.update(roomRef, {
        'activePromise': activePromise,
        'updatedAt': FieldValue.serverTimestamp(),
      });
    });
  }

  Stream<int> unreadCountStream({
    required String roomId,
    required String userId,
  }) {
    return _firestore
        .collection('chat_rooms')
        .doc(roomId)
        .collection('messages')
        .snapshots()
        .map((snap) {
          int count = 0;

          for (final doc in snap.docs) {
            final data = doc.data();
            final senderId = data['senderId']?.toString() ?? '';
            final readBy = List<String>.from(data['readBy'] ?? const []);

            if (senderId == userId) continue;
            if (!readBy.contains(userId)) count++;
          }

          return count;
        });
  }

  Stream<bool> hasAnyUnreadChats(String userId) {
    return chatRoomsStream(userId).asyncMap((roomSnap) async {
      for (final room in roomSnap.docs) {
        final msgSnap = await room.reference.collection('messages').get();

        for (final msg in msgSnap.docs) {
          final data = msg.data();
          final senderId = data['senderId']?.toString() ?? '';
          final readBy = List<String>.from(data['readBy'] ?? const []);

          if (senderId != userId && !readBy.contains(userId)) {
            return true;
          }
        }
      }
      return false;
    });
  }

  Future<void> markMessagesAsRead({
    required String roomId,
    required String userId,
  }) async {
    final snap = await _firestore
        .collection('chat_rooms')
        .doc(roomId)
        .collection('messages')
        .get();

    final batch = _firestore.batch();
    bool hasUpdate = false;

    for (final doc in snap.docs) {
      final data = doc.data();
      final senderId = data['senderId']?.toString() ?? '';
      final readBy = List<String>.from(data['readBy'] ?? const []);

      if (senderId == userId) continue;
      if (readBy.contains(userId)) continue;

      batch.update(doc.reference, {
        'readBy': [...readBy, userId],
        'updatedAt': FieldValue.serverTimestamp(),
      });
      hasUpdate = true;
    }

    if (hasUpdate) {
      await batch.commit();
    }
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
      'readBy': [senderId],
      'createdAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    });

    batch.set(roomRef, {
      'lastMessage': text,
      'lastMessageAt': FieldValue.serverTimestamp(),
      'photoBlurUnlocked': true,
      'photoBlurUnlockedAt': FieldValue.serverTimestamp(),
      'photoBlurUnlockedBy': senderId,
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
    String? placeId,
    String? placeAddress,
    double? placeLat,
    double? placeLng,
  }) async {
    final roomRef = _firestore.collection('chat_rooms').doc(roomId);
    final promiseRef = roomRef.collection('promises').doc();
    final messageRef = roomRef.collection('messages').doc();

    final batch = _firestore.batch();

    final extras = _promisePlaceExtras(
      placeId: placeId,
      placeAddress: placeAddress,
      placeLat: placeLat,
      placeLng: placeLng,
    );

    batch.set(promiseRef, {
      'promiseId': promiseRef.id,
      'messageId': messageRef.id,
      'requestedBy': requestedBy,
      'requestedTo': requestedTo,
      'dateTime': Timestamp.fromDate(dateTime),
      'place': place,
      'placeCategory': placeCategory,
      ...extras,
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
      ...extras,
      'status': 'requested',
      'isEdited': false,
      'editedAt': null,
      'readBy': [requestedBy],
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
    required String editedBy,
    required DateTime dateTime,
    required String place,
    required String placeCategory,
    String? placeId,
    String? placeAddress,
    double? placeLat,
    double? placeLng,
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

      final oldRequestedBy = oldData['requestedBy']?.toString() ?? '';
      final oldRequestedTo = oldData['requestedTo']?.toString() ?? '';

      String newRequestedTo;
      if (editedBy == oldRequestedBy) {
        newRequestedTo = oldRequestedTo;
      } else if (editedBy == oldRequestedTo) {
        newRequestedTo = oldRequestedBy;
      } else {
        throw Exception('수정 권한이 없는 사용자입니다.');
      }

      final extras = _promisePlaceExtras(
        placeId: placeId,
        placeAddress: placeAddress,
        placeLat: placeLat,
        placeLng: placeLng,
      );

      tx.update(promiseRef, {
        'requestedBy': editedBy,
        'requestedTo': newRequestedTo,
        'dateTime': Timestamp.fromDate(dateTime),
        'place': place,
        'placeCategory': placeCategory,
        ...extras,
        'status': 'requested',
        'acceptedAt': null,
        'updatedAt': FieldValue.serverTimestamp(),
        'isEdited': true,
        'editedAt': FieldValue.serverTimestamp(),
      });

      if (messageRef != null) {
        tx.update(messageRef, {
          'senderId': editedBy,
          'type': 'promise_request',
          'text': '약속 요청',
          'dateTime': Timestamp.fromDate(dateTime),
          'place': place,
          'placeCategory': placeCategory,
          ...extras,
          'status': 'requested',
          'readBy': [editedBy],
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
      final roomSnap = await tx.get(roomRef);
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

      final apExtras = _promisePlaceExtras(
        placeId: data['placeId']?.toString(),
        placeAddress: data['placeAddress']?.toString(),
        placeLat: (data['placeLat'] is num)
            ? (data['placeLat'] as num).toDouble()
            : double.tryParse(data['placeLat']?.toString() ?? ''),
        placeLng: (data['placeLng'] is num)
            ? (data['placeLng'] as num).toDouble()
            : double.tryParse(data['placeLng']?.toString() ?? ''),
      );

      final activePromise = <String, dynamic>{
        'promiseId': promiseId,
        'dateTime': ts,
        'place': data['place'],
        'placeCategory': data['placeCategory'],
        'status': 'confirmed',
        'participantIds': roomSnap.data()?['participantIds'],
        ...apExtras,
      };
      final legacyThumb = data['placeThumbnailUrl']?.toString();
      if (legacyThumb != null && legacyThumb.isNotEmpty) {
        activePromise['placeThumbnailUrl'] = legacyThumb;
      }

      tx.update(roomRef, {
        'activePromise': activePromise,
        'lastMessage': '약속이 확정되었어요',
        'lastMessageAt': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
      });
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
        'readBy': [requestedBy],
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
