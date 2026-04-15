import 'package:cloud_firestore/cloud_firestore.dart';

enum SafetyStampFollowUpReason {
  phoneOff('phone_off'),
  forgotToStamp('forgot_to_stamp'),
  other('other');

  final String code;
  const SafetyStampFollowUpReason(this.code);

  static SafetyStampFollowUpReason? fromCode(String? code) {
    for (final value in SafetyStampFollowUpReason.values) {
      if (value.code == code) {
        return value;
      }
    }
    return null;
  }
}

class SafetyStampFollowUpDraft {
  final SafetyStampFollowUpReason? reason;
  final String otherText;
  final bool hasSubmitted;

  const SafetyStampFollowUpDraft({
    required this.reason,
    required this.otherText,
    required this.hasSubmitted,
  });
}

class SafetyStampFollowUpService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  Future<SafetyStampFollowUpDraft> loadDraft({
    required String roomId,
    required String promiseId,
    required String userId,
  }) async {
    if (roomId.isEmpty || promiseId.isEmpty || userId.isEmpty) {
      return const SafetyStampFollowUpDraft(
        reason: null,
        otherText: '',
        hasSubmitted: false,
      );
    }

    final promiseDoc = await _firestore
        .collection('chat_rooms')
        .doc(roomId)
        .collection('promises')
        .doc(promiseId)
        .get();

    final data = promiseDoc.data() ?? const <String, dynamic>{};
    final safetyStampRaw = data['safetyStamp'];
    final safetyStamp = safetyStampRaw is Map
        ? Map<String, dynamic>.from(safetyStampRaw)
        : const <String, dynamic>{};
    final followUpRaw = safetyStamp['goodbyeFollowUpByUserId'];
    final followUpByUserId = followUpRaw is Map
        ? Map<String, dynamic>.from(followUpRaw)
        : const <String, dynamic>{};
    final mineRaw = followUpByUserId[userId];
    final mine = mineRaw is Map
        ? Map<String, dynamic>.from(mineRaw)
        : const <String, dynamic>{};

    return SafetyStampFollowUpDraft(
      reason: SafetyStampFollowUpReason.fromCode(
        mine['reasonCode']?.toString(),
      ),
      otherText: mine['reasonText']?.toString() ?? '',
      hasSubmitted: mine['status']?.toString() == 'submitted',
    );
  }

  Future<void> submitReason({
    required String roomId,
    required String promiseId,
    required String userId,
    required SafetyStampFollowUpReason reason,
    required String otherText,
    String? notificationId,
  }) async {
    if (roomId.isEmpty || promiseId.isEmpty || userId.isEmpty) {
      throw Exception('필수 정보가 없어요.');
    }

    final roomRef = _firestore.collection('chat_rooms').doc(roomId);
    final promiseRef = roomRef.collection('promises').doc(promiseId);
    final payload = <String, dynamic>{
      'status': 'submitted',
      'reasonCode': reason.code,
      'reasonText': reason == SafetyStampFollowUpReason.other
          ? otherText.trim()
          : null,
      'respondedAt': FieldValue.serverTimestamp(),
      'notificationId': notificationId,
    };

    await _firestore.runTransaction((tx) async {
      final roomSnap = await tx.get(roomRef);
      final promiseSnap = await tx.get(promiseRef);

      if (!promiseSnap.exists) {
        throw Exception('약속 정보를 찾을 수 없어요.');
      }

      tx.set(promiseRef, {
        'safetyStamp': {
          'goodbyeFollowUpByUserId': {userId: payload},
        },
        'updatedAt': FieldValue.serverTimestamp(),
      }, SetOptions(merge: true));

      final roomData = roomSnap.data() ?? const <String, dynamic>{};
      final activePromiseRaw = roomData['activePromise'];
      if (activePromiseRaw is Map) {
        final activePromise = Map<String, dynamic>.from(
          activePromiseRaw as Map<Object?, Object?>,
        );
        final activePromiseId = activePromise['promiseId']?.toString() ?? '';
        if (activePromiseId == promiseId) {
          tx.set(roomRef, {
            'activePromise': {
              'safetyStamp': {
                'goodbyeFollowUpByUserId': {userId: payload},
              },
            },
            'updatedAt': FieldValue.serverTimestamp(),
          }, SetOptions(merge: true));
        }
      }

      if (notificationId != null && notificationId.isNotEmpty) {
        tx.set(
          _firestore
              .collection('users')
              .doc(userId)
              .collection('notifications')
              .doc(notificationId),
          {'isRead': true, 'readAt': FieldValue.serverTimestamp()},
          SetOptions(merge: true),
        );
      }
    });
  }
}
