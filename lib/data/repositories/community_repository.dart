import '../models/community/post_model.dart';

/// 한 페이지의 게시글과 다음 페이지 커서.
///
/// 커서는 탭에 따라 public 글 문서이거나 ("전체"/카테고리/"인기") 비공개 소유권
/// 매핑 문서다 ("내가 쓴 글"). 호출부는 그대로 다음 호출에 넘기기만 한다.
class CommunityPostPage {
  const CommunityPostPage({
    required this.posts,
    required this.cursor,
    required this.hasMore,
  });

  final List<PostModel> posts;
  final Object? cursor;
  final bool hasMore;
}

/// 대나무숲 (익명 게시판) 저장소.
///
/// P0-3: 작성자 UID 는 이 인터페이스 어디에도 나오지 않는다. 글/댓글 작성·삭제·
/// 신고는 서버 callable 이 처리하고, "내 글인가" 는 본인만 읽을 수 있는 비공개
/// 매핑으로만 판단한다. 좋아요는 로그인한 본인 이름으로만 쓰고 읽는다.
abstract class CommunityRepository {
  /// 게시글 작성 (서버 callable). 작성자는 서버가 로그인 세션으로 정한다.
  Future<String> createPost({
    required String content,
    required String category,
    required List<String> tags,
  });

  /// 게시글 목록 한 페이지.
  ///
  /// tab: 전체 / 인기 / 설렘 / 고민 / 일상 / 질문 / 내가 쓴 글
  /// 신고해서 숨긴 글은 빠진다.
  Future<CommunityPostPage> fetchPostsPage({
    required String tab,
    int limit = 5,
    Object? cursor,
  });

  /// 주어진 글 중 로그인한 사용자가 쓴 글의 id (비공개 매핑 조회, 1 쿼리).
  Future<Set<String>> fetchMyPostIds(Iterable<String> postIds);

  /// 이 글에서 로그인한 사용자가 쓴 댓글/답글의 id.
  Future<Set<String>> fetchMyCommentIds(String postId);

  /// 게시글 상세 조회 (신고해서 숨긴 글이면 null)
  Future<PostModel?> fetchPostDetail(String postId);

  /// 본인 게시글 삭제 (서버 callable, 비공개 매핑으로 소유 확인)
  Future<void> softDeletePost({required String postId});

  /// 게시글 좋아요 토글
  Future<void> togglePostLike({required String postId, required String userId});

  /// 현재 유저가 게시글 좋아요 눌렀는지 확인
  Future<bool> hasLikedPost({required String postId, required String userId});

  /// 댓글 작성 (서버 callable)
  ///
  /// parentCommentId == null 이면 일반 댓글
  /// parentCommentId != null 이면 답글
  Future<String> addComment({
    required String postId,
    required String content,
    String? parentCommentId,
  });

  /// 댓글 목록 조회 (신고해서 숨긴 댓글은 빠진다)
  Future<List<CommunityCommentModel>> fetchComments(String postId);

  /// 본인 댓글 삭제 (서버 callable)
  Future<void> softDeleteComment({
    required String postId,
    required String commentId,
  });

  /// 글/댓글 신고. 서버가 작성자를 비공개 매핑으로 찾아 운영 신고에 남기고,
  /// 신고한 사람에게는 그 콘텐츠를 숨긴다. 작성자 UID 는 돌려받지 않는다.
  Future<void> reportContent({
    required String contentType,
    required String postId,
    String? commentId,
    required String reason,
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
  final String content;
  final String? parentCommentId;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final int likeCount;
  final bool isDeleted;

  const CommunityCommentModel({
    required this.commentId,
    required this.content,
    required this.parentCommentId,
    required this.createdAt,
    required this.updatedAt,
    required this.likeCount,
    required this.isDeleted,
  });

  CommunityCommentModel copyWith({
    String? commentId,
    String? content,
    String? parentCommentId,
    DateTime? createdAt,
    DateTime? updatedAt,
    int? likeCount,
    bool? isDeleted,
  }) {
    return CommunityCommentModel(
      commentId: commentId ?? this.commentId,
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
