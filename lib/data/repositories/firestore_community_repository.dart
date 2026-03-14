import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/foundation.dart';

import '../models/community/post_model.dart';
import 'community_repository.dart';

class FirestoreCommunityRepository implements CommunityRepository {
  FirestoreCommunityRepository({FirebaseFirestore? firestore})
    : _firestore = firestore ?? FirebaseFirestore.instance;

  final FirebaseFirestore _firestore;

  CollectionReference<Map<String, dynamic>> get _posts =>
      _firestore.collection('bamboo_posts');

  @override
  Future<String> createPost({
    required String authorId,
    required String content,
    required String category,
    required List<String> tags,
  }) async {
    final trimmedContent = content.trim();
    final normalizedTags = tags
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toSet()
        .toList();

    if (authorId.trim().isEmpty) {
      throw Exception('authorId가 비어 있습니다.');
    }
    if (trimmedContent.isEmpty) {
      throw Exception('게시글 내용이 비어 있습니다.');
    }
    if (category.trim().isEmpty) {
      throw Exception('카테고리를 선택해주세요.');
    }

    final docRef = _posts.doc();
    // authorId는 항상 문자열로 저장 (Firestore 숫자 vs 문자열 불일치 방지)
    final authorIdStr = authorId.trim().toString();
    debugPrint('[FirestoreCommunity] createPost authorId="$authorIdStr"');

    await docRef.set({
      'postId': docRef.id,
      'authorId': authorIdStr,
      'content': trimmedContent,
      'category': category,
      'tags': normalizedTags,
      'createdAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
      'likeCount': 0,
      'commentCount': 0,
      'score7d': 0,
      'isDeleted': false,
    });

    return docRef.id;
  }

  Query<Map<String, dynamic>> _buildListQuery({
    required String tab,
    required String? currentUserId,
    int limit = 5,
  }) {
    final normalizedTab = tab.trim();

    if (normalizedTab == '전체') {
      return _posts
          .where('isDeleted', isEqualTo: false)
          .orderBy('createdAt', descending: true)
          .limit(limit);
    }

    if (normalizedTab == '인기') {
      final sevenDaysAgo = Timestamp.fromDate(
        DateTime.now().subtract(const Duration(days: 7)),
      );

      return _posts
          .where('isDeleted', isEqualTo: false)
          .where('createdAt', isGreaterThanOrEqualTo: sevenDaysAgo)
          .orderBy('createdAt', descending: true)
          .orderBy('score7d', descending: true)
          .limit(limit);
    }

    if (normalizedTab == '내가 쓴 글') {
      // currentUserId와 Firestore authorId 형식 일치: 항상 문자열로 정규화
      final uid = (currentUserId ?? '').trim().toString();
      if (uid.isEmpty) {
        return _posts.where('authorId', isEqualTo: '__none__').limit(limit);
      }

      return _posts
          .where('isDeleted', isEqualTo: false)
          .where('authorId', isEqualTo: uid)
          .orderBy('createdAt', descending: true)
          .limit(limit);
    }

    return _posts
        .where('isDeleted', isEqualTo: false)
        .where('category', isEqualTo: normalizedTab)
        .orderBy('createdAt', descending: true)
        .limit(limit);
  }

  @override
  Future<List<PostModel>> fetchPosts({
    required String tab,
    required String? currentUserId,
    int limit = 5,
    Object? lastItem,
  }) async {
    Query<Map<String, dynamic>> query = _buildListQuery(
      tab: tab,
      currentUserId: currentUserId,
      limit: limit,
    );

    if (lastItem != null) {
      if (lastItem is! DocumentSnapshot<Map<String, dynamic>>) {
        throw Exception(
          'lastItem은 DocumentSnapshot<Map<String, dynamic>> 여야 합니다.',
        );
      }
      query = query.startAfterDocument(lastItem);
    }

    final snapshot = await query.get();
    return snapshot.docs.map(PostModel.fromFirestore).toList();
  }

  Future<QuerySnapshot<Map<String, dynamic>>> fetchPostsSnapshot({
    required String tab,
    required String? currentUserId,
    int limit = 5,
    DocumentSnapshot<Map<String, dynamic>>? lastDocument,
  }) async {
    if (tab.trim() == '내가 쓴 글') {
      debugPrint(
        '[FirestoreCommunity] 내가 쓴 글 쿼리 currentUserId="$currentUserId"',
      );
    }

    Query<Map<String, dynamic>> query = _buildListQuery(
      tab: tab,
      currentUserId: currentUserId,
      limit: limit,
    );

    if (lastDocument != null) {
      query = query.startAfterDocument(lastDocument);
    }

    final snapshot = await query.get();
    if (tab.trim() == '내가 쓴 글') {
      debugPrint(
        '[FirestoreCommunity] 내가 쓴 글 결과 ${snapshot.docs.length}건',
      );
      if (snapshot.docs.isNotEmpty) {
        final first = snapshot.docs.first.data();
        debugPrint(
          '[FirestoreCommunity] 첫글 authorId="${first['authorId']}"',
        );
      }
    }
    return snapshot;
  }

  @override
  Future<PostModel?> fetchPostDetail(String postId) async {
    final doc = await _posts.doc(postId).get();
    if (!doc.exists) return null;
    return PostModel.fromFirestore(doc);
  }

  @override
  Future<void> softDeletePost({
    required String postId,
    required String authorId,
  }) async {
    final postRef = _posts.doc(postId);
    final snapshot = await postRef.get();

    if (!snapshot.exists) {
      throw Exception('게시글이 존재하지 않습니다.');
    }

    final data = snapshot.data();
    final writerId = data?['authorId']?.toString() ?? '';

    if (writerId != authorId) {
      throw Exception('작성자만 삭제할 수 있습니다.');
    }

    await postRef.update({
      'isDeleted': true,
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  @override
  Future<void> togglePostLike({
    required String postId,
    required String userId,
  }) async {
    if (userId.trim().isEmpty) {
      throw Exception('userId가 비어 있습니다.');
    }

    final postRef = _posts.doc(postId);
    final likeRef = postRef.collection('likes').doc(userId);

    await _firestore.runTransaction((transaction) async {
      final postSnap = await transaction.get(postRef);
      if (!postSnap.exists) {
        throw Exception('게시글이 존재하지 않습니다.');
      }

      final likeSnap = await transaction.get(likeRef);

      if (likeSnap.exists) {
        transaction.delete(likeRef);
        transaction.update(postRef, {
          'likeCount': FieldValue.increment(-1),
          'score7d': FieldValue.increment(-1),
          'updatedAt': FieldValue.serverTimestamp(),
        });
      } else {
        transaction.set(likeRef, {
          'userId': userId,
          'createdAt': FieldValue.serverTimestamp(),
        });
        transaction.update(postRef, {
          'likeCount': FieldValue.increment(1),
          'score7d': FieldValue.increment(1),
          'updatedAt': FieldValue.serverTimestamp(),
        });
      }
    });
  }

  @override
  Future<bool> hasLikedPost({
    required String postId,
    required String userId,
  }) async {
    final likeSnap = await _posts
        .doc(postId)
        .collection('likes')
        .doc(userId)
        .get();

    return likeSnap.exists;
  }

  @override
  Future<String> addComment({
    required String postId,
    required String authorId,
    required String content,
    String? parentCommentId,
  }) async {
    final trimmedContent = content.trim();

    if (authorId.trim().isEmpty) {
      throw Exception('authorId가 비어 있습니다.');
    }
    if (trimmedContent.isEmpty) {
      throw Exception('댓글 내용이 비어 있습니다.');
    }

    final postRef = _posts.doc(postId);
    final commentRef = postRef.collection('comments').doc();

    await _firestore.runTransaction((transaction) async {
      final postSnap = await transaction.get(postRef);

      if (!postSnap.exists) {
        throw Exception('게시글이 존재하지 않습니다.');
      }

      transaction.set(commentRef, {
        'commentId': commentRef.id,
        'authorId': authorId,
        'content': trimmedContent,
        'parentCommentId': parentCommentId,
        'createdAt': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
        'likeCount': 0,
        'isDeleted': false,
      });

      transaction.update(postRef, {
        'commentCount': FieldValue.increment(1),
        'score7d': FieldValue.increment(1),
        'updatedAt': FieldValue.serverTimestamp(),
      });
    });

    return commentRef.id;
  }

  @override
  Future<List<CommunityCommentModel>> fetchComments(String postId) async {
    final snapshot = await _posts
        .doc(postId)
        .collection('comments')
        .where('isDeleted', isEqualTo: false)
        .orderBy('createdAt', descending: false)
        .get();

    return snapshot.docs.map((doc) {
      final data = doc.data();
      return CommunityCommentModel(
        commentId: (data['commentId'] ?? doc.id).toString(),
        authorId: (data['authorId'] ?? '').toString(),
        content: (data['content'] ?? '').toString(),
        parentCommentId: data['parentCommentId']?.toString(),
        createdAt: _parseDateTime(data['createdAt']),
        updatedAt: _parseDateTime(data['updatedAt']),
        likeCount: _parseInt(data['likeCount']),
        isDeleted: data['isDeleted'] == true,
      );
    }).toList();
  }

  @override
  Future<void> softDeleteComment({
    required String postId,
    required String commentId,
    required String authorId,
  }) async {
    final postRef = _posts.doc(postId);
    final commentRef = postRef.collection('comments').doc(commentId);

    await _firestore.runTransaction((transaction) async {
      final commentSnap = await transaction.get(commentRef);

      if (!commentSnap.exists) {
        throw Exception('댓글이 존재하지 않습니다.');
      }

      final data = commentSnap.data();
      final writerId = data?['authorId']?.toString() ?? '';

      if (writerId != authorId) {
        throw Exception('작성자만 삭제할 수 있습니다.');
      }

      final alreadyDeleted = data?['isDeleted'] == true;
      if (alreadyDeleted) return;

      transaction.update(commentRef, {
        'isDeleted': true,
        'updatedAt': FieldValue.serverTimestamp(),
      });

      transaction.update(postRef, {
        'commentCount': FieldValue.increment(-1),
        'updatedAt': FieldValue.serverTimestamp(),
      });
    });
  }

  @override
  Future<void> toggleCommentLike({
    required String postId,
    required String commentId,
    required String userId,
  }) async {
    final commentRef = _posts.doc(postId).collection('comments').doc(commentId);
    final likeRef = commentRef.collection('likes').doc(userId);

    await _firestore.runTransaction((transaction) async {
      final commentSnap = await transaction.get(commentRef);

      if (!commentSnap.exists) {
        throw Exception('댓글이 존재하지 않습니다.');
      }

      final likeSnap = await transaction.get(likeRef);

      if (likeSnap.exists) {
        transaction.delete(likeRef);
        transaction.update(commentRef, {
          'likeCount': FieldValue.increment(-1),
          'updatedAt': FieldValue.serverTimestamp(),
        });
      } else {
        transaction.set(likeRef, {
          'userId': userId,
          'createdAt': FieldValue.serverTimestamp(),
        });
        transaction.update(commentRef, {
          'likeCount': FieldValue.increment(1),
          'updatedAt': FieldValue.serverTimestamp(),
        });
      }
    });
  }

  @override
  Future<bool> hasLikedComment({
    required String postId,
    required String commentId,
    required String userId,
  }) async {
    final likeSnap = await _posts
        .doc(postId)
        .collection('comments')
        .doc(commentId)
        .collection('likes')
        .doc(userId)
        .get();

    return likeSnap.exists;
  }

  static int _parseInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return 0;
  }

  static DateTime? _parseDateTime(dynamic value) {
    if (value == null) return null;
    if (value is Timestamp) return value.toDate();
    if (value is DateTime) return value;
    return null;
  }
}
