import 'package:cloud_firestore/cloud_firestore.dart';

class AskService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  CollectionReference<Map<String, dynamic>> get _asksRef =>
      _firestore.collection('asks');

  /// Maximum question length (mirrors the Firestore rule).
  static const int maxTextLength = 500;

  /// P1-10: an ask carries only the question. Sender and recipient identity
  /// are resolved by the reader from `publicProfiles/{uid}` (server-owned);
  /// the former client-written profile snapshots let a sender pick the
  /// nickname and image URL the recipient saw and are refused by the rules.
  Future<String> sendAsk({
    required String fromUserId,
    required String toUserId,
    required String text,
    String sourceScreen = 'profile_specific_detail_screen',
  }) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty || trimmed.length > maxTextLength) {
      throw ArgumentError.value(text.length, 'text', 'length out of range');
    }
    final docRef = await _asksRef.add({
      'fromUserId': fromUserId,
      'toUserId': toUserId,
      'text': trimmed,
      'status': 'sent',
      'createdAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
      'readAt': null,
      'sourceScreen': sourceScreen,
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

  /// P1-10: identity shown next to an ask comes from the server-owned public
  /// profile. Legacy documents may still carry a client-written snapshot; only
  /// its nickname is used as a text fallback, never its image URL.
  static String legacyNicknameFallback(
    Map<String, dynamic> askData, {
    required bool isReceived,
  }) {
    final key = isReceived
        ? 'fromUserProfileSnapshot'
        : 'toUserProfileSnapshot';
    final snapshot = askData[key];
    if (snapshot is! Map) return '';
    return snapshot['nickname']?.toString().trim() ?? '';
  }
}
