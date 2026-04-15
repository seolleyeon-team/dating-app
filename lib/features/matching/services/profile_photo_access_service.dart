import 'package:cloud_firestore/cloud_firestore.dart';

import '../../chat/services/chat_service.dart';

class ProfilePhotoAccessService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;
  final ChatService _chatService = ChatService();

  Future<bool> canViewUnblurredProfilePhotos({
    required String viewerUserId,
    required String targetUserId,
  }) async {
    if (viewerUserId.isEmpty || targetUserId.isEmpty) {
      return false;
    }

    if (viewerUserId == targetUserId) {
      return true;
    }

    final roomId = _chatService.buildDirectRoomId(viewerUserId, targetUserId);
    final roomRef = _firestore.collection('chat_rooms').doc(roomId);
    final roomSnap = await roomRef.get();
    if (!roomSnap.exists) {
      return false;
    }

    final roomData = roomSnap.data() ?? const <String, dynamic>{};
    if (roomData['photoBlurUnlocked'] == true) {
      return true;
    }

    final textMessageSnap = await roomRef
        .collection('messages')
        .where('type', isEqualTo: 'text')
        .limit(1)
        .get();

    if (textMessageSnap.docs.isEmpty) {
      return false;
    }

    await roomRef.set({
      'photoBlurUnlocked': true,
      'photoBlurUnlockedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
    return true;
  }
}
