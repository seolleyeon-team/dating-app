import '../models/community/post_model.dart';

abstract class CommunityRepository {
  /// 게시글 작성
  Future<String> createPost({
    required String authorId,
    required String content,
    required String category,
    required List<String> tags,
  });

  /// 게시글 목록 조회
  ///
  /// tab 예시:
  /// - 전체
  /// - 인기
  /// - 설렘
  /// - 고민
  /// - 일상
  /// - 질문
  Future<List<PostModel>> fetchPosts({
    required String tab,
    required String? currentUserId,
    int limit = 5,
    Object? lastItem,
  });

  /// 게시글 상세 조회
  Future<PostModel?> fetchPostDetail(String postId);

  /// 게시글 소프트 삭제
  Future<void> softDeletePost({
    required String postId,
    required String authorId,
  });

  /// 게시글 좋아요 토글
  Future<void> togglePostLike({required String postId, required String userId});

  /// 현재 유저가 게시글 좋아요 눌렀는지 확인
  Future<bool> hasLikedPost({required String postId, required String userId});

  /// 댓글 작성
  ///
  /// parentCommentId == null 이면 일반 댓글
  /// parentCommentId != null 이면 답글
  Future<String> addComment({
    required String postId,
    required String authorId,
    required String content,
    String? parentCommentId,
  });

  /// 댓글 목록 조회
  Future<List<CommunityCommentModel>> fetchComments(String postId);

  /// 댓글 삭제
  Future<void> softDeleteComment({
    required String postId,
    required String commentId,
    required String authorId,
  });

  /// 댓글 좋아요 토글
  Future<void> toggleCommentLike({
    required String postId,
    required String commentId,
    required String userId,
  });

  /// 현재 유저가 댓글 좋아요 눌렀는지 확인
  Future<bool> hasLikedComment({
    required String postId,
    required String commentId,
    required String userId,
  });
}

class CommunityCommentModel {
  final String commentId;
  final String authorId;
  final String content;
  final String? parentCommentId;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final int likeCount;
  final bool isDeleted;

  const CommunityCommentModel({
    required this.commentId,
    required this.authorId,
    required this.content,
    required this.parentCommentId,
    required this.createdAt,
    required this.updatedAt,
    required this.likeCount,
    required this.isDeleted,
  });

  CommunityCommentModel copyWith({
    String? commentId,
    String? authorId,
    String? content,
    String? parentCommentId,
    DateTime? createdAt,
    DateTime? updatedAt,
    int? likeCount,
    bool? isDeleted,
  }) {
    return CommunityCommentModel(
      commentId: commentId ?? this.commentId,
      authorId: authorId ?? this.authorId,
      content: content ?? this.content,
      parentCommentId: parentCommentId ?? this.parentCommentId,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      likeCount: likeCount ?? this.likeCount,
      isDeleted: isDeleted ?? this.isDeleted,
    );
  }

  String get relativeTimeLabel {
    if (createdAt == null) return '';

    final now = DateTime.now();
    final diff = now.difference(createdAt!);

    if (diff.inSeconds < 60) return '방금 전';
    if (diff.inMinutes < 60) return '${diff.inMinutes}분 전';
    if (diff.inHours < 24) return '${diff.inHours}시간 전';
    if (diff.inDays < 7) return '${diff.inDays}일 전';
    return '${createdAt!.month}/${createdAt!.day}';
  }
}
