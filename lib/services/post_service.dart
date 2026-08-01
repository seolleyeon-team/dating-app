import 'package:cloud_firestore/cloud_firestore.dart';

/// 대나무숲(커뮤니티) 게시물 Firestore 서비스
class PostService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  CollectionReference<Map<String, dynamic>> get _postsRef =>
      _firestore.collection('posts');

  // ---------------------------------------------------------------------------
  // 게시물 CRUD
  // ---------------------------------------------------------------------------

  /// 게시물 작성 → 새 문서 ID 반환
  Future<String> createPost({
    required String authorId,
    required String authorNickname,
    String? authorProfileUrl,
    required String category,
    required String title,
    required String content,
    List<String> imageUrls = const [],
  }) async {
    final docRef = await _postsRef.add({
      'authorId': authorId,
      'authorNickname': authorNickname,
      'authorProfileUrl': authorProfileUrl,
      'category': category,
      'title': title,
      'content': content,
      'imageUrls': imageUrls,
      'likeCount': 0,
      'commentCount': 0,
      'viewCount': 0,
      'likedBy': <String>[],
      'createdAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    });
    return docRef.id;
  }

  /// 게시물 수정 (작성자 본인만)
  Future<void> updatePost({
    required String postId,
    String? title,
    String? content,
    String? category,
    List<String>? imageUrls,
  }) async {
    final updates = <String, dynamic>{
      'updatedAt': FieldValue.serverTimestamp(),
    };
    if (title != null) updates['title'] = title;
    if (content != null) updates['content'] = content;
    if (category != null) updates['category'] = category;
    if (imageUrls != null) updates['imageUrls'] = imageUrls;

    await _postsRef.doc(postId).update(updates);
  }

  /// 게시물 삭제
  Future<void> deletePost(String postId) async {
    final batch = _firestore.batch();
    batch.delete(_postsRef.doc(postId));

    final comments = await _postsRef.doc(postId).collection('comments').get();
    for (final doc in comments.docs) {
      batch.delete(doc.reference);
    }

    await batch.commit();
  }

  /// 게시물 단건 조회 + 조회수 증가
  Future<Map<String, dynamic>?> getPost(String postId) async {
    final doc = await _postsRef.doc(postId).get();
    if (!doc.exists) return null;

    await _postsRef.doc(postId).update({'viewCount': FieldValue.increment(1)});

    return {'id': doc.id, ...doc.data()!};
  }

  // ---------------------------------------------------------------------------
  // 게시물 목록 (페이징)
  // ---------------------------------------------------------------------------

  /// 카테고리별 최신순 게시물 목록
  Future<List<Map<String, dynamic>>> getPosts({
    String? category,
    int limit = 20,
    DocumentSnapshot? startAfter,
  }) async {
    Query<Map<String, dynamic>> query = _postsRef
        .orderBy('createdAt', descending: true)
        .limit(limit);

    if (category != null) {
      query = _postsRef
          .where('category', isEqualTo: category)
          .orderBy('createdAt', descending: true)
          .limit(limit);
    }

    if (startAfter != null) {
      query = query.startAfterDocument(startAfter);
    }

    final snapshot = await query.get();
    return snapshot.docs.map((doc) => {'id': doc.id, ...doc.data()}).toList();
  }

  /// 실시간 게시물 스트림 (최신 20개)
  Stream<List<Map<String, dynamic>>> postsStream({
    String? category,
    int limit = 20,
  }) {
    Query<Map<String, dynamic>> query = _postsRef
        .orderBy('createdAt', descending: true)
        .limit(limit);

    if (category != null) {
      query = _postsRef
          .where('category', isEqualTo: category)
          .orderBy('createdAt', descending: true)
          .limit(limit);
    }

    return query.snapshots().map(
      (snap) => snap.docs.map((doc) => {'id': doc.id, ...doc.data()}).toList(),
    );
  }

  // ---------------------------------------------------------------------------
  // 좋아요 (트랜잭션으로 원자적 처리)
  // ---------------------------------------------------------------------------

  /// 좋아요 토글 → 현재 좋아요 상태 반환
  Future<bool> togglePostLike({
    required String postId,
    required String userId,
  }) async {
    final postRef = _postsRef.doc(postId);
    bool isNowLiked = false;

    await _firestore.runTransaction((tx) async {
      final snapshot = await tx.get(postRef);
      if (!snapshot.exists) return;

      final likedBy = List<String>.from(snapshot.data()?['likedBy'] ?? []);

      if (likedBy.contains(userId)) {
        likedBy.remove(userId);
        tx.update(postRef, {
          'likedBy': likedBy,
          'likeCount': FieldValue.increment(-1),
        });
        isNowLiked = false;
      } else {
        likedBy.add(userId);
        tx.update(postRef, {
          'likedBy': likedBy,
          'likeCount': FieldValue.increment(1),
        });
        isNowLiked = true;
      }
    });

    return isNowLiked;
  }

  // ---------------------------------------------------------------------------
  // 댓글
  // ---------------------------------------------------------------------------

  /// 댓글 작성
  Future<String> addComment({
    required String postId,
    required String authorId,
    required String authorNickname,
    String? authorProfileUrl,
    required String content,
  }) async {
    final commentRef = await _postsRef.doc(postId).collection('comments').add({
      'authorId': authorId,
      'authorNickname': authorNickname,
      'authorProfileUrl': authorProfileUrl,
      'content': content,
      'likeCount': 0,
      'likedBy': <String>[],
      'createdAt': FieldValue.serverTimestamp(),
    });

    await _postsRef.doc(postId).update({
      'commentCount': FieldValue.increment(1),
    });

    return commentRef.id;
  }

  /// 댓글 삭제
  Future<void> deleteComment({
    required String postId,
    required String commentId,
  }) async {
    await _postsRef.doc(postId).collection('comments').doc(commentId).delete();

    await _postsRef.doc(postId).update({
      'commentCount': FieldValue.increment(-1),
    });
  }

  /// 댓글 목록 스트림
  Stream<List<Map<String, dynamic>>> commentsStream(String postId) {
    return _postsRef
        .doc(postId)
        .collection('comments')
        .orderBy('createdAt', descending: false)
        .snapshots()
        .map(
          (snap) =>
              snap.docs.map((doc) => {'id': doc.id, ...doc.data()}).toList(),
        );
  }

  /// 댓글 좋아요 토글
  Future<bool> toggleCommentLike({
    required String postId,
    required String commentId,
    required String userId,
  }) async {
    final commentRef = _postsRef
        .doc(postId)
        .collection('comments')
        .doc(commentId);
    bool isNowLiked = false;

    await _firestore.runTransaction((tx) async {
      final snapshot = await tx.get(commentRef);
      if (!snapshot.exists) return;

      final likedBy = List<String>.from(snapshot.data()?['likedBy'] ?? []);

      if (likedBy.contains(userId)) {
        likedBy.remove(userId);
        tx.update(commentRef, {
          'likedBy': likedBy,
          'likeCount': FieldValue.increment(-1),
        });
        isNowLiked = false;
      } else {
        likedBy.add(userId);
        tx.update(commentRef, {
          'likedBy': likedBy,
          'likeCount': FieldValue.increment(1),
        });
        isNowLiked = true;
      }
    });

    return isNowLiked;
  }
}
