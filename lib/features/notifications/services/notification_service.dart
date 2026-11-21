import 'package:cloud_firestore/cloud_firestore.dart';

import '../models/app_notification.dart';

class NotificationService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  CollectionReference<Map<String, dynamic>> _notificationsRef(String userId) {
    return _firestore
        .collection('users')
        .doc(userId)
        .collection('notifications');
  }

  Stream<List<AppNotification>> notificationsStream(String userId) {
    return _notificationsRef(userId)
        .orderBy('createdAt', descending: true)
        .snapshots()
        .map((snapshot) => snapshot.docs.map(AppNotification.fromDoc).toList());
  }

  Stream<int> unreadNotificationCountStream(String userId) {
    return _notificationsRef(userId)
        .where('isRead', isEqualTo: false)
        .snapshots()
        .map((snapshot) => snapshot.docs.length);
  }

  Future<void> markAsRead({
    required String userId,
    required String notificationId,
  }) async {
    await _notificationsRef(userId).doc(notificationId).set({
      'isRead': true,
      'readAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
  }

  Future<void> markAllAsRead(String userId) async {
    final snapshot = await _notificationsRef(
      userId,
    ).where('isRead', isEqualTo: false).get();

    // 한 batch 는 write 500개까지다. 알림은 지울 수 없어 계속 쌓이므로
    // 안 읽은 알림이 그보다 많으면 batch 하나로는 commit 이 통째로 실패한다.
    final docs = snapshot.docs;
    for (var start = 0; start < docs.length; start += _markReadBatchSize) {
      final batch = _firestore.batch();
      for (final doc in docs.skip(start).take(_markReadBatchSize)) {
        batch.set(doc.reference, {
          'isRead': true,
          'readAt': FieldValue.serverTimestamp(),
        }, SetOptions(merge: true));
      }
      await batch.commit();
    }
  }

  static const int _markReadBatchSize = 450;
}
