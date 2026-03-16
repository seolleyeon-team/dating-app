import 'package:cloud_firestore/cloud_firestore.dart';

class AppNotification {
  final String id;
  final String type;
  final String title;
  final String body;
  final bool isRead;
  final DateTime createdAt;

  final String? actorId;
  final String? actorName;
  final String? postId;
  final String? commentId;
  final String? roomId;
  final String? deeplinkType;
  final String? deeplinkId;

  const AppNotification({
    required this.id,
    required this.type,
    required this.title,
    required this.body,
    required this.isRead,
    required this.createdAt,
    this.actorId,
    this.actorName,
    this.postId,
    this.commentId,
    this.roomId,
    this.deeplinkType,
    this.deeplinkId,
  });

  factory AppNotification.fromDoc(
    QueryDocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data();

    final createdAtTs = data['createdAt'];
    final createdAt = createdAtTs is Timestamp
        ? createdAtTs.toDate()
        : DateTime.fromMillisecondsSinceEpoch(0);

    return AppNotification(
      id: doc.id,
      type: (data['type'] ?? '').toString(),
      title: (data['title'] ?? '').toString(),
      body: (data['body'] ?? '').toString(),
      isRead: data['isRead'] == true,
      createdAt: createdAt,
      actorId: data['actorId']?.toString(),
      actorName: data['actorName']?.toString(),
      postId: data['postId']?.toString(),
      commentId: data['commentId']?.toString(),
      roomId: data['roomId']?.toString(),
      deeplinkType: data['deeplinkType']?.toString(),
      deeplinkId: data['deeplinkId']?.toString(),
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'type': type,
      'title': title,
      'body': body,
      'isRead': isRead,
      'createdAt': Timestamp.fromDate(createdAt),
      'actorId': actorId,
      'actorName': actorName,
      'postId': postId,
      'commentId': commentId,
      'roomId': roomId,
      'deeplinkType': deeplinkType,
      'deeplinkId': deeplinkId,
    };
  }
}
