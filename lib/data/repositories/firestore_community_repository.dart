import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/foundation.dart';

import '../../services/firebase_runtime.dart';
import '../models/community/post_model.dart';
import 'community_repository.dart';

/// 대나무숲 Firestore 저장소.
///
/// P0-3 (익명성): public 글/댓글 문서에는 작성자가 없다. 이 저장소는
/// - 작성·삭제·신고를 서버 callable 로만 하고 (작성자 UID 를 보내지도 받지도 않는다),
/// - "내 글/내 댓글" 을 본인만 읽을 수 있는 비공개 매핑
///   (`bamboo_post_authors` / `bamboo_comment_authors`) 으로만 판단하며,
/// - 좋아요는 로그인한 본인의 `likes/{uid}` 문서만 읽고 쓴다.
///
/// 실명 차단 목록(blocks/{uid}/targets)으로 익명 글을 거르지 않는다. 그 필터는
/// "누군가를 차단하고 어떤 글이 사라지는지 본다" 는 방식으로 작성자를 특정하는
/// 오라클이 된다. 대신 신고한 글/댓글은 신고한 사람에게서 숨긴다
/// (`users/{uid}/bambooHiddenContent`).
class FirestoreCommunityRepository implements CommunityRepository {
  FirestoreCommunityRepository({
    FirebaseFirestore? firestore,
    FirebaseAuth? firebaseAuth,
  }) : _firestore = firestore ?? FirebaseFirestore.instance,
       _firebaseAuth = firebaseAuth ?? FirebaseAuth.instance;

  final FirebaseFirestore _firestore;
  final FirebaseAuth _firebaseAuth;
  FirebaseFunctions get _functions =>
      FirebaseFunctions.instanceFor(region: firebaseFunctionsRegion);

  static const _reviewerUid = 'play-reviewer-v1';
  static const _reviewPostsCollection = 'playReviewBambooPosts';
  static const _reviewPostAuthorsCollection = 'playReviewBambooPostAuthors';
  static const _reviewCommentAuthorsCollection =
      'playReviewBambooCommentAuthors';
  static const myPostsTab = '내가 쓴 글';

  /// Firestore `whereIn` 상한.
  static const _whereInLimit = 30;

  /// 신고 숨김 목록 상한 — 읽기를 한 번에 묶어 둔다.
  static const _hiddenContentLimit = 500;

  @visibleForTesting
  static String postsCollectionForUserId(String? userId) =>
      userId == _reviewerUid ? _reviewPostsCollection : 'bamboo_posts';

  @visibleForTesting
  static String postAuthorsCollectionForUserId(String? userId) =>
      userId == _reviewerUid
      ? _reviewPostAuthorsCollection
      : 'bamboo_post_authors';

  @visibleForTesting
  static String commentAuthorsCollectionForUserId(String? userId) =>
      userId == _reviewerUid
      ? _reviewCommentAuthorsCollection
      : 'bamboo_comment_authors';

  /// 신고 숨김 목록의 문서 키 (서버 `bambooHiddenContentKey` 와 같다).
  @visibleForTesting
  static String hiddenContentKey(String postId, [String? commentId]) =>
      commentId == null || commentId.isEmpty ? postId : '${postId}__$commentId';

  String get _uid => _firebaseAuth.currentUser?.uid.trim() ?? '';

  bool get _isPlayReviewSession => _uid == _reviewerUid;

  CollectionReference<Map<String, dynamic>> get _posts =>
      _firestore.collection(postsCollectionForUserId(_uid));

  CollectionReference<Map<String, dynamic>> get _postAuthors =>
      _firestore.collection(postAuthorsCollectionForUserId(_uid));

  CollectionReference<Map<String, dynamic>> get _commentAuthors =>
      _firestore.collection(commentAuthorsCollectionForUserId(_uid));

  // 신고 숨김 목록 캐시. 계정이 바뀌면 다시 읽는다.
  String? _hiddenFor;
  Set<String>? _hidden;

  Future<Set<String>> _hiddenKeys() async {
    final uid = _uid;
    if (uid.isEmpty) return const {};
    if (_hiddenFor == uid && _hidden != null) return _hidden!;
    try {
      final snap = await _firestore
          .collection('users')
          .doc(uid)
          .collection('bambooHiddenContent')
          .limit(_hiddenContentLimit)
          .get();
      _hidden = snap.docs.map((d) => d.id).toSet();
    } catch (_) {
      // 숨김 목록을 못 읽어도 피드는 보여 준다 (보안 경계가 아니라 편의 기능).
      _hidden = <String>{};
    }
    _hiddenFor = uid;
    return _hidden!;
  }

  @override
  Future<String> createPost({
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

    if (_uid.isEmpty) {
      throw Exception('로그인이 필요해요.');
    }
    if (trimmedContent.isEmpty) {
      throw Exception('게시글 내용이 비어 있습니다.');
    }
    if (category.trim().isEmpty) {
      throw Exception('카테고리를 선택해주세요.');
    }

    final result = await _functions
        .httpsCallable('createCommunityPost')
        .call<Map<Object?, Object?>>({
          'content': trimmedContent,
          'category': category.trim(),
          'tags': normalizedTags,
        });
    final postId = result.data['postId']?.toString() ?? '';
    if (postId.isEmpty) throw Exception('게시글을 저장하지 못했어요.');
    return postId;
  }

  Query<Map<String, dynamic>> _buildListQuery({
    required String tab,
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

    return _posts
        .where('isDeleted', isEqualTo: false)
        .where('category', isEqualTo: normalizedTab)
        .orderBy('createdAt', descending: true)
        .limit(limit);
  }

  @override
  Future<CommunityPostPage> fetchPostsPage({
    required String tab,
    int limit = 5,
    Object? cursor,
  }) async {
    if (tab.trim() == myPostsTab) {
      return _fetchMyPostsPage(limit: limit, cursor: cursor);
    }
    Query<Map<String, dynamic>> query = _buildListQuery(tab: tab, limit: limit);
    if (cursor is DocumentSnapshot<Map<String, dynamic>>) {
      query = query.startAfterDocument(cursor);
    }
    final snapshot = await query.get();
    final hidden = await _hiddenKeys();
    return CommunityPostPage(
      posts: snapshot.docs
          .map(PostModel.fromFirestore)
          .where((post) => !hidden.contains(hiddenContentKey(post.postId)))
          .toList(),
      cursor: snapshot.docs.isNotEmpty ? snapshot.docs.last : cursor,
      hasMore: snapshot.docs.length == limit,
    );
  }

  /// "내가 쓴 글": 내 비공개 매핑을 최신순으로 한 페이지 읽고, 그 글들을 한
  /// 번의 `whereIn` 으로 가져온다. 페이지당 읽기 = 매핑 limit + 글 limit.
  Future<CommunityPostPage> _fetchMyPostsPage({
    required int limit,
    Object? cursor,
  }) async {
    final uid = _uid;
    if (uid.isEmpty) {
      return const CommunityPostPage(posts: [], cursor: null, hasMore: false);
    }
    final pageSize = limit.clamp(1, _whereInLimit);
    Query<Map<String, dynamic>> mappings = _postAuthors
        .where('ownerUid', isEqualTo: uid)
        .orderBy('createdAt', descending: true)
        .limit(pageSize);
    if (cursor is DocumentSnapshot<Map<String, dynamic>>) {
      mappings = mappings.startAfterDocument(cursor);
    }
    final mappingSnap = await mappings.get();
    final ids = mappingSnap.docs.map((d) => d.id).toList();
    if (ids.isEmpty) {
      return CommunityPostPage(posts: const [], cursor: cursor, hasMore: false);
    }
    final postSnap = await _posts
        .where(FieldPath.documentId, whereIn: ids)
        .get();
    final byId = {
      for (final doc in postSnap.docs) doc.id: PostModel.fromFirestore(doc),
    };
    return CommunityPostPage(
      // 매핑 순서(작성 최신순)를 지키고, 삭제된 글은 뺀다.
      posts: [
        for (final id in ids)
          if (byId[id] != null && !byId[id]!.isDeleted) byId[id]!,
      ],
      cursor: mappingSnap.docs.last,
      hasMore: mappingSnap.docs.length == pageSize,
    );
  }

  @override
  Future<Set<String>> fetchMyPostIds(Iterable<String> postIds) async {
    final uid = _uid;
    final ids = postIds.where((id) => id.isNotEmpty).toSet().toList();
    if (uid.isEmpty || ids.isEmpty) return const {};
    final mine = <String>{};
    for (var i = 0; i < ids.length; i += _whereInLimit) {
      final chunk = ids.sublist(
        i,
        i + _whereInLimit > ids.length ? ids.length : i + _whereInLimit,
      );
      // 규칙은 ownerUid == 본인 조건이 있는 쿼리만 허용한다. 남의 매핑은
      // 결과에도, 오류에도 나타나지 않는다.
      final snap = await _postAuthors
          .where('ownerUid', isEqualTo: uid)
          .where(FieldPath.documentId, whereIn: chunk)
          .get();
      mine.addAll(snap.docs.map((d) => d.id));
    }
    return mine;
  }

  @override
  Future<Set<String>> fetchMyCommentIds(String postId) async {
    final uid = _uid;
    if (uid.isEmpty || postId.isEmpty) return const {};
    final snap = await _commentAuthors
        .where('ownerUid', isEqualTo: uid)
        .where('postId', isEqualTo: postId)
        .get();
    return snap.docs
        .map((d) => (d.data()['commentId'] ?? '').toString())
        .where((id) => id.isNotEmpty)
        .toSet();
  }

  @override
  Future<PostModel?> fetchPostDetail(String postId) async {
    final hidden = await _hiddenKeys();
    if (hidden.contains(hiddenContentKey(postId))) return null;
    final doc = await _posts.doc(postId).get();
    if (!doc.exists) return null;
    return PostModel.fromFirestore(doc);
  }

  @override
  Future<void> softDeletePost({required String postId}) async {
    await _functions.httpsCallable('deleteCommunityPost').call<Object?>({
      'postId': postId,
    });
  }

  @override
  Future<void> togglePostLike({
    required String postId,
    required String userId,
  }) async {
    if (userId.trim().isEmpty || userId.trim() != _uid) {
      throw Exception('로그인한 본인만 좋아요를 누를 수 있어요.');
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
          if (_isPlayReviewSession) 'dataPartition': 'play_review',
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
    // 좋아요 문서는 본인만 읽을 수 있다 (rules). 남의 uid 로 묻지 않는다.
    if (userId.trim().isEmpty || userId.trim() != _uid) return false;
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
    required String content,
    String? parentCommentId,
  }) async {
    final trimmedContent = content.trim();

    if (_uid.isEmpty) {
      throw Exception('로그인이 필요해요.');
    }
    if (trimmedContent.isEmpty) {
      throw Exception('댓글 내용이 비어 있습니다.');
    }

    final result = await _functions
        .httpsCallable('createCommunityComment')
        .call<Map<Object?, Object?>>({
          'postId': postId,
          'content': trimmedContent,
          if (parentCommentId != null) 'parentCommentId': parentCommentId,
        });
    final commentId = result.data['commentId']?.toString() ?? '';
    if (commentId.isEmpty) throw Exception('댓글을 저장하지 못했어요.');
    return commentId;
  }

  @override
  Future<List<CommunityCommentModel>> fetchComments(String postId) async {
    final snapshot = await _posts
        .doc(postId)
        .collection('comments')
        .where('isDeleted', isEqualTo: false)
        .orderBy('createdAt', descending: false)
        .get();

    final hidden = await _hiddenKeys();
    return snapshot.docs
        .map((doc) {
          final data = doc.data();
          return CommunityCommentModel(
            commentId: (data['commentId'] ?? doc.id).toString(),
            content: (data['content'] ?? '').toString(),
            parentCommentId: data['parentCommentId']?.toString(),
            createdAt: _parseDateTime(data['createdAt']),
            updatedAt: _parseDateTime(data['updatedAt']),
            likeCount: _parseInt(data['likeCount']),
            isDeleted: data['isDeleted'] == true,
          );
        })
        .where(
          (comment) =>
              !hidden.contains(hiddenContentKey(postId, comment.commentId)),
        )
        .toList();
  }

  @override
  Future<void> softDeleteComment({
    required String postId,
    required String commentId,
  }) async {
    await _functions.httpsCallable('deleteCommunityComment').call<Object?>({
      'postId': postId,
      'commentId': commentId,
    });
  }

  @override
  Future<void> reportContent({
    required String contentType,
    required String postId,
    String? commentId,
    required String reason,
  }) async {
    await _functions.httpsCallable('reportBambooContent').call<Object?>({
      'contentType': contentType,
      'postId': postId,
      if (commentId != null) 'commentId': commentId,
      'reason': reason,
    });
    // 서버가 숨김 목록에 넣었다. 다음 조회에서 다시 읽는다.
    _hidden = null;
  }

  @override
  Future<void> toggleCommentLike({
    required String postId,
    required String commentId,
    required String userId,
  }) async {
    if (userId.trim().isEmpty || userId.trim() != _uid) {
      throw Exception('로그인한 본인만 좋아요를 누를 수 있어요.');
    }
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
          if (_isPlayReviewSession) 'dataPartition': 'play_review',
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
    if (userId.trim().isEmpty || userId.trim() != _uid) return false;
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
