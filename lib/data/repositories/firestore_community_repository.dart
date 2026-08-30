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

  // SEC-04. 대나무숲 글/댓글은 익명이어야 하는데 public 문서에 raw UID 가
  // authorId 로 들어 있고 publicProfiles/{uid} 는 로그인만 하면 읽힌다. 즉
  // 지금은 join 한 번으로 작성자를 특정할 수 있다. 최종적으로는 public 에서
  // authorId 를 빼야 하고, 그때 "내가 쓴 글" 을 잃지 않도록 소유권을 여기
  // 비공개 매핑에 함께 적어 둔다. 이 단계에서는 public authorId 를 아직
  // 지우지 않으므로 구버전 앱도 그대로 동작한다.
  CollectionReference<Map<String, dynamic>> get _postAuthors =>
      _firestore.collection('bamboo_post_authors');

  CollectionReference<Map<String, dynamic>> get _commentAuthors =>
      _firestore.collection('bamboo_comment_authors');

  // 댓글은 글 하위에 있어 commentId 만으로는 유일하지 않다.
  static String commentAuthorDocId(String postId, String commentId) =>
      '${postId}__$commentId';

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

    // 글과 소유권 매핑은 반드시 함께 남아야 한다. 따로 쓰면 둘 중 하나만
    // 성공한 상태가 생기고, 그러면 나중에 public authorId 를 지울 때
    // 주인 없는 글이 된다.
    final batch = _firestore.batch();
    batch.set(docRef, {
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
    batch.set(_postAuthors.doc(docRef.id), {
      'postId': docRef.id,
      'ownerUid': authorIdStr,
      'createdAt': FieldValue.serverTimestamp(),
    });
    await batch.commit();

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
      return _posts
          .where('isDeleted', isEqualTo: false)
          .orderBy('score7d', descending: true)
          .orderBy('createdAt', descending: true)
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
      debugPrint('[FirestoreCommunity] 내가 쓴 글 결과 ${snapshot.docs.length}건');
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

      // 글과 같은 이유로 댓글도 소유권을 같은 커밋에 남긴다.
      transaction
          .set(_commentAuthors.doc(commentAuthorDocId(postId, commentRef.id)), {
            'postId': postId,
            'commentId': commentRef.id,
            'ownerUid': authorId.trim(),
            'createdAt': FieldValue.serverTimestamp(),
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
