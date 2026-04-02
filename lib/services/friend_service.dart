import 'package:cloud_firestore/cloud_firestore.dart';

import 'user_service.dart';

class FriendListItem {
  final String friendUserId;
  final String pairId;
  final DateTime? createdAt;
  final String name;
  final String imageUrl;
  final String universityName;
  final String major;

  const FriendListItem({
    required this.friendUserId,
    required this.pairId,
    required this.createdAt,
    required this.name,
    required this.imageUrl,
    required this.universityName,
    required this.major,
  });
}

class FriendService {
  FriendService({UserService? userService})
      : _userService = userService ?? UserService();

  final FirebaseFirestore _firestore = FirebaseFirestore.instance;
  final UserService _userService;

  Stream<QuerySnapshot<Map<String, dynamic>>> friendsStream(String userId) {
    return _firestore
        .collection('users')
        .doc(userId)
        .collection('friends')
        .orderBy('createdAt', descending: true)
        .snapshots();
  }

  Future<int> getFriendsCount(String userId) async {
    final snapshot = await _firestore
        .collection('users')
        .doc(userId)
        .collection('friends')
        .get();
    return snapshot.size;
  }

  Future<List<FriendListItem>> hydrateFriends(
    List<QueryDocumentSnapshot<Map<String, dynamic>>> docs,
  ) async {
    final items = <FriendListItem>[];

    for (final doc in docs) {
      final data = doc.data();
      final friendUserId = data['friendUserId']?.toString().trim() ?? doc.id;
      final pairId = data['pairId']?.toString() ?? '';
      final createdAt = _toDateTime(data['createdAt']);

      Map<String, dynamic> snapshot = {};
      final snapshotRaw = data['friendProfileSnapshot'];
      if (snapshotRaw is Map) {
        snapshot = Map<String, dynamic>.from(snapshotRaw);
      }

      if (_snapshotIsInsufficient(snapshot)) {
        final fallback = await _userService.getUserProfile(friendUserId);
        snapshot = _mergeSnapshotWithUser(snapshot, fallback, friendUserId);
      }

      items.add(
        FriendListItem(
          friendUserId: friendUserId,
          pairId: pairId,
          createdAt: createdAt,
          name: _readName(snapshot, fallbackUserId: friendUserId),
          imageUrl: _readImageUrl(snapshot),
          universityName: _readUniversity(snapshot),
          major: _readMajor(snapshot),
        ),
      );
    }

    return items;
  }

  bool _snapshotIsInsufficient(Map<String, dynamic> snapshot) {
    final name = snapshot['nickname']?.toString().trim() ?? '';
    final imageUrl = snapshot['profileImageUrl']?.toString().trim() ?? '';
    return name.isEmpty && imageUrl.isEmpty;
  }

  Map<String, dynamic> _mergeSnapshotWithUser(
    Map<String, dynamic> snapshot,
    Map<String, dynamic>? user,
    String userId,
  ) {
    if (user == null) return snapshot;

    final onboardingRaw = user['onboarding'];
    final onboarding = onboardingRaw is Map
        ? Map<String, dynamic>.from(onboardingRaw)
        : <String, dynamic>{};

    final photoUrls = onboarding['photoUrls'] is List
        ? List<String>.from(
            (onboarding['photoUrls'] as List).whereType<String>(),
          )
        : const <String>[];

    final merged = <String, dynamic>{...snapshot};
    merged['uid'] = snapshot['uid']?.toString().isNotEmpty == true
        ? snapshot['uid']
        : userId;
    merged['nickname'] =
        _firstNonEmpty(snapshot['nickname'], onboarding['nickname'], user['nickname']);
    merged['profileImageUrl'] = _firstNonEmpty(
      snapshot['profileImageUrl'],
      photoUrls.isNotEmpty ? photoUrls.first : null,
      user['profileImageUrl'],
      onboarding['representativeImageUrl'],
    );
    merged['universityName'] = _firstNonEmpty(
      snapshot['universityName'],
      onboarding['university'],
      _inferYonseiFromEmail(user['studentEmail']?.toString()),
    );
    merged['major'] = _firstNonEmpty(snapshot['major'], onboarding['major']);
    return merged;
  }

  DateTime? _toDateTime(dynamic value) {
    if (value is Timestamp) return value.toDate();
    if (value is DateTime) return value;
    return null;
  }

  String _readName(
    Map<String, dynamic> snapshot, {
    required String fallbackUserId,
  }) {
    final nickname = snapshot['nickname']?.toString().trim() ?? '';
    return nickname.isNotEmpty ? nickname : fallbackUserId;
  }

  String _readImageUrl(Map<String, dynamic> snapshot) {
    return snapshot['profileImageUrl']?.toString().trim() ?? '';
  }

  String _readUniversity(Map<String, dynamic> snapshot) {
    return snapshot['universityName']?.toString().trim() ?? '';
  }

  String _readMajor(Map<String, dynamic> snapshot) {
    return snapshot['major']?.toString().trim() ?? '';
  }

  String _firstNonEmpty(dynamic first, [dynamic second, dynamic third, dynamic fourth]) {
    final values = [first, second, third, fourth];
    for (final value in values) {
      final text = value?.toString().trim() ?? '';
      if (text.isNotEmpty) return text;
    }
    return '';
  }

  String _inferYonseiFromEmail(String? email) {
    final normalized = email?.trim().toLowerCase() ?? '';
    if (normalized.endsWith('@yonsei.ac.kr')) {
      return '연세대학교';
    }
    return '';
  }
}
