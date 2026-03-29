import 'package:cloud_firestore/cloud_firestore.dart';

class AskService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  CollectionReference<Map<String, dynamic>> get _asksRef =>
      _firestore.collection('asks');

  Future<String> sendAsk({
    required String fromUserId,
    required String toUserId,
    required String text,
    String sourceScreen = 'profile_specific_detail_screen',
    Map<String, dynamic>? fromUserSnapshot,
    Map<String, dynamic>? toUserSnapshot,
  }) async {
    final docRef = await _asksRef.add({
      'fromUserId': fromUserId,
      'toUserId': toUserId,
      'text': text,
      'status': 'sent',
      'createdAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
      'readAt': null,
      'sourceScreen': sourceScreen,
      if (fromUserSnapshot != null) 'fromUserProfileSnapshot': fromUserSnapshot,
      if (toUserSnapshot != null) 'toUserProfileSnapshot': toUserSnapshot,
    });
    return docRef.id;
  }

  Stream<QuerySnapshot<Map<String, dynamic>>> receivedAsksStream(
    String userId,
  ) {
    return _asksRef
        .where('toUserId', isEqualTo: userId)
        .orderBy('createdAt', descending: true)
        .snapshots();
  }

  Stream<QuerySnapshot<Map<String, dynamic>>> sentAsksStream(String userId) {
    return _asksRef
        .where('fromUserId', isEqualTo: userId)
        .orderBy('createdAt', descending: true)
        .snapshots();
  }

  Future<void> markAsRead(String askId) async {
    await _asksRef.doc(askId).update({
      'status': 'read',
      'readAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  Stream<int> unreadReceivedCount(String userId) {
    return _asksRef
        .where('toUserId', isEqualTo: userId)
        .where('status', isEqualTo: 'sent')
        .snapshots()
        .map((snap) => snap.size);
  }

  Map<String, dynamic> buildProfileSnapshot({
    required String uid,
    String? nickname,
    String? profileImageUrl,
    String? universityName,
  }) {
    return {
      'uid': uid,
      'nickname': nickname ?? '',
      'profileImageUrl': profileImageUrl ?? '',
      'universityName': universityName ?? '',
    };
  }
}
