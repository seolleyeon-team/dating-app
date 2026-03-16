// =============================================================================
// 커뮤니티(대나무숲) 게시글 상세 화면
// 경로: lib/features/community/screens/post_detail_screen.dart
//
// postId 기반 Firestore 상세 조회 + 댓글/답글/좋아요
// =============================================================================

import 'dart:ui';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../data/models/community/post_model.dart';
import '../../../data/repositories/firestore_community_repository.dart';
import '../../../data/repositories/community_repository.dart';
import '../../../services/storage_service.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF0428B);
  static const Color softPink = Color(0xFFFFE4E6);
  static const Color softLavender = Color(0xFFE9D5FF);

  static const Color textMain = Color(0xFF181114);
  static const Color textSub = Color(0xFF9CA3AF);
  static const Color cardBg = Color(0xE6FFFFFF);
}

// =============================================================================
// 메인 화면
// =============================================================================
class PostDetailScreen extends StatefulWidget {
  final String postId;

  const PostDetailScreen({super.key, required this.postId});

  @override
  State<PostDetailScreen> createState() => _PostDetailScreenState();
}

class _PostDetailScreenState extends State<PostDetailScreen> {
  final FirestoreCommunityRepository _repository =
      FirestoreCommunityRepository();
  final StorageService _storageService = StorageService();
  final TextEditingController _commentController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  Map<String, bool> _likedComments = {};

  PostModel? _post;
  List<CommunityCommentModel> _comments = [];

  bool _isLoading = true;
  bool _isSubmittingComment = false;
  bool _isPostLiked = false;

  String? _currentUserId;
  String? _replyTargetCommentId;
  String? _replyTargetPreview;

  @override
  void initState() {
    super.initState();
    _initialize();
  }

  @override
  void dispose() {
    _commentController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _initialize() async {
    try {
      final userId = await _storageService.getKakaoUserId();
      final post = await _repository.fetchPostDetail(widget.postId);

      if (post == null) {
        throw Exception('게시글을 찾을 수 없습니다.');
      }

      final comments = await _repository.fetchComments(widget.postId);
      bool isLiked = false;
      final likedComments = <String, bool>{};

      if (userId != null && userId.isNotEmpty) {
        isLiked = await _repository.hasLikedPost(
          postId: widget.postId,
          userId: userId,
        );

        for (final comment in comments) {
          final liked = await _repository.hasLikedComment(
            postId: widget.postId,
            commentId: comment.commentId,
            userId: userId,
          );
          likedComments[comment.commentId] = liked;
        }
      }

      if (!mounted) return;

      setState(() {
        _currentUserId = userId;
        _post = post;
        _comments = comments;
        _isPostLiked = isLiked;
        _likedComments = likedComments;
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        _isLoading = false;
      });

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('게시글을 불러오지 못했어요: $e')));
    }
  }

  Future<void> _refreshDetail() async {
    final post = await _repository.fetchPostDetail(widget.postId);
    final comments = await _repository.fetchComments(widget.postId);

    bool isLiked = _isPostLiked;
    if (_currentUserId != null && _currentUserId!.isNotEmpty) {
      isLiked = await _repository.hasLikedPost(
        postId: widget.postId,
        userId: _currentUserId!,
      );
    }

    final likedComments = <String, bool>{};

    if (_currentUserId != null && _currentUserId!.isNotEmpty) {
      for (final comment in comments) {
        final liked = await _repository.hasLikedComment(
          postId: widget.postId,
          commentId: comment.commentId,
          userId: _currentUserId!,
        );
        likedComments[comment.commentId] = liked;
      }
    }

    if (!mounted) return;
    setState(() {
      _post = post;
      _comments = comments;
      _isPostLiked = isLiked;
      _likedComments = likedComments;
    });
  }

  Future<void> _togglePostLike() async {
    if (_currentUserId == null || _currentUserId!.isEmpty || _post == null) {
      return;
    }

    HapticFeedback.lightImpact();

    final previousPost = _post!;
    final previousLiked = _isPostLiked;
    final willLike = !_isPostLiked;

    final nextLikeCount = willLike
        ? previousPost.likeCount + 1
        : (previousPost.likeCount > 0 ? previousPost.likeCount - 1 : 0);

    final nextScore7d = willLike
        ? previousPost.score7d + 1
        : (previousPost.score7d > 0 ? previousPost.score7d - 1 : 0);

    setState(() {
      _isPostLiked = willLike;
      _post = previousPost.copyWith(
        likeCount: nextLikeCount,
        score7d: nextScore7d,
        updatedAt: DateTime.now(),
      );
    });

    try {
      await _repository.togglePostLike(
        postId: previousPost.postId,
        userId: _currentUserId!,
      );
    } catch (e) {
      if (!mounted) return;

      setState(() {
        _isPostLiked = previousLiked;
        _post = previousPost;
      });

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('좋아요 처리에 실패했어요: $e')));
    }
  }

  Future<void> _submitComment() async {
    final text = _commentController.text.trim();
    if (text.isEmpty || _isSubmittingComment) return;
    if (_currentUserId == null || _currentUserId!.isEmpty) return;

    setState(() {
      _isSubmittingComment = true;
    });

    try {
      await _repository.addComment(
        postId: widget.postId,
        authorId: _currentUserId!,
        content: text,
        parentCommentId: _replyTargetCommentId,
      );

      _commentController.clear();

      if (!mounted) return;
      setState(() {
        _replyTargetCommentId = null;
        _replyTargetPreview = null;
      });

      await _refreshDetail();

      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!_scrollController.hasClients) return;
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      });
    } catch (e) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('댓글 등록에 실패했어요: $e')));
    } finally {
      if (!mounted) return;
      setState(() {
        _isSubmittingComment = false;
      });
    }
  }

  Future<void> _toggleCommentLike(String commentId) async {
    if (_currentUserId == null || _currentUserId!.isEmpty) return;

    final previousLikedMap = Map<String, bool>.from(_likedComments);
    final previousComments = List<CommunityCommentModel>.from(_comments);

    final isCurrentlyLiked = _likedComments[commentId] ?? false;
    final willLike = !isCurrentlyLiked;

    final targetIndex = _comments.indexWhere((c) => c.commentId == commentId);
    if (targetIndex == -1) return;

    final targetComment = _comments[targetIndex];
    final nextLikeCount = willLike
        ? targetComment.likeCount + 1
        : (targetComment.likeCount > 0 ? targetComment.likeCount - 1 : 0);

    final nextComments = List<CommunityCommentModel>.from(_comments);
    nextComments[targetIndex] = targetComment.copyWith(
      likeCount: nextLikeCount,
      updatedAt: DateTime.now(),
    );

    setState(() {
      _likedComments[commentId] = willLike;
      _comments = nextComments;
    });

    try {
      await _repository.toggleCommentLike(
        postId: widget.postId,
        commentId: commentId,
        userId: _currentUserId!,
      );
    } catch (e) {
      if (!mounted) return;

      setState(() {
        _likedComments = previousLikedMap;
        _comments = previousComments;
      });

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('댓글 좋아요 처리에 실패했어요: $e')));
    }
  }

  void _startReply(CommunityCommentModel comment) {
    HapticFeedback.selectionClick();
    setState(() {
      _replyTargetCommentId = comment.commentId;
      _replyTargetPreview = comment.content;
    });
  }

  void _cancelReply() {
    setState(() {
      _replyTargetCommentId = null;
      _replyTargetPreview = null;
    });
  }

  List<CommunityCommentModel> _rootComments(List<CommunityCommentModel> all) {
    return all.where((c) => c.parentCommentId == null).toList();
  }

  List<CommunityCommentModel> _childComments(
    List<CommunityCommentModel> all,
    String parentId,
  ) {
    return all.where((c) => c.parentCommentId == parentId).toList();
  }

  String _timeAgo(DateTime? dateTime) {
    if (dateTime == null) return '';
    final diff = DateTime.now().difference(dateTime);
    if (diff.inMinutes < 1) return '방금 전';
    if (diff.inMinutes < 60) return '${diff.inMinutes}분 전';
    if (diff.inHours < 24) return '${diff.inHours}시간 전';
    if (diff.inDays < 7) return '${diff.inDays}일 전';
    return '${dateTime.month}/${dateTime.day}';
  }

  Color _getCategoryColor(String category) {
    switch (category) {
      case '설렘':
        return const Color(0xFFFCE7F3);
      case '고민':
        return const Color(0xFFF3F4F6);
      case '일상':
        return const Color(0xFFF3E8FF);
      case '질문':
        return const Color(0xFFFEF3C7);
      case '인기':
        return const Color(0xFFFFEDD5);
      default:
        return const Color(0xFFF3F4F6);
    }
  }

  Color _getCategoryTextColor(String category) {
    switch (category) {
      case '설렘':
        return const Color(0xFFEC4899);
      case '고민':
        return const Color(0xFF4B5563);
      case '일상':
        return const Color(0xFF9333EA);
      case '질문':
        return const Color(0xFFD97706);
      case '인기':
        return const Color(0xFFEA580C);
      default:
        return const Color(0xFF4B5563);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;
    final bottomSafe = MediaQuery.of(context).padding.bottom;

    return Scaffold(
      backgroundColor: Colors.white,
      body: Stack(
        children: [
          const _BackgroundDecoration(),
          SafeArea(
            bottom: false,
            child: Column(
              children: [
                _Header(onBack: () => Navigator.of(context).pop()),
                Expanded(
                  child: _isLoading
                      ? const Center(child: CupertinoActivityIndicator())
                      : _post == null
                      ? const Center(
                          child: Text(
                            '게시글을 찾을 수 없어요',
                            style: TextStyle(
                              fontFamily: 'Noto Sans KR',
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                              color: _AppColors.textMain,
                            ),
                          ),
                        )
                      : RefreshIndicator.adaptive(
                          onRefresh: _refreshDetail,
                          child: ListView(
                            controller: _scrollController,
                            physics: const BouncingScrollPhysics(
                              parent: AlwaysScrollableScrollPhysics(),
                            ),
                            padding: EdgeInsets.fromLTRB(
                              16,
                              12,
                              16,
                              bottomInset + bottomSafe + 120,
                            ),
                            children: [
                              _DetailPostCard(
                                post: _post!,
                                categoryColor: _getCategoryColor(
                                  _post!.category,
                                ),
                                categoryTextColor: _getCategoryTextColor(
                                  _post!.category,
                                ),
                                isLiked: _isPostLiked,
                                onLikeTap: _togglePostLike,
                                timeAgo: _timeAgo(_post!.createdAt),
                              ),
                              const SizedBox(height: 18),
                              _CommentHeader(count: _comments.length),
                              const SizedBox(height: 12),
                              if (_comments.isEmpty)
                                const _EmptyCommentState()
                              else
                                ..._buildCommentWidgets(),
                            ],
                          ),
                        ),
                ),
              ],
            ),
          ),

          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: _CommentInputBar(
              controller: _commentController,
              isSubmitting: _isSubmittingComment,
              replyPreview: _replyTargetPreview,
              onCancelReply: _cancelReply,
              onSubmit: _submitComment,
            ),
          ),
        ],
      ),
    );
  }

  List<Widget> _buildCommentWidgets() {
    final roots = _rootComments(_comments);
    final widgets = <Widget>[];

    for (final root in roots) {
      widgets.add(
        _CommentCard(
          comment: root,
          timeAgo: _timeAgo(root.createdAt),
          onReplyTap: () => _startReply(root),
          onLikeTap: () => _toggleCommentLike(root.commentId),
          isLiked: _likedComments[root.commentId] ?? false,
          indent: 0,
        ),
      );

      final children = _childComments(_comments, root.commentId);
      for (final child in children) {
        widgets.add(const SizedBox(height: 10));
        widgets.add(
          _CommentCard(
            comment: child,
            timeAgo: _timeAgo(child.createdAt),
            onReplyTap: () => _startReply(root),
            onLikeTap: () => _toggleCommentLike(child.commentId),
            isLiked: _likedComments[child.commentId] ?? false,
            indent: 20,
            isReply: true,
          ),
        );
      }

      widgets.add(const SizedBox(height: 14));
    }

    return widgets;
  }
}

// =============================================================================
// 배경
// =============================================================================
class _BackgroundDecoration extends StatelessWidget {
  const _BackgroundDecoration();

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                _AppColors.softPink,
                Colors.white,
                _AppColors.softLavender,
              ],
            ),
          ),
        ),
        Positioned(
          top: 80,
          left: 40,
          child: _PetalIcon(
            size: 32,
            color: _AppColors.primary.withValues(alpha: 0.18),
            rotation: 45,
          ),
        ),
        Positioned(
          top: 170,
          right: 36,
          child: _PetalIcon(
            size: 44,
            color: _AppColors.primary.withValues(alpha: 0.10),
            rotation: -18,
          ),
        ),
      ],
    );
  }
}

class _PetalIcon extends StatelessWidget {
  final double size;
  final Color color;
  final double rotation;

  const _PetalIcon({
    required this.size,
    required this.color,
    required this.rotation,
  });

  @override
  Widget build(BuildContext context) {
    return Transform.rotate(
      angle: rotation * math.pi / 180,
      child: Icon(CupertinoIcons.drop_fill, size: size, color: color),
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final VoidCallback onBack;

  const _Header({required this.onBack});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
      child: Row(
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            minSize: 40,
            onPressed: () {
              HapticFeedback.lightImpact();
              onBack();
            },
            child: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.75),
                shape: BoxShape.circle,
              ),
              child: const Icon(
                CupertinoIcons.back,
                color: _AppColors.textMain,
                size: 20,
              ),
            ),
          ),
          const Expanded(
            child: Text(
              '대나무숲',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: 'Noto Sans KR',
                fontSize: 18,
                fontWeight: FontWeight.w800,
                color: _AppColors.textMain,
              ),
            ),
          ),
          const SizedBox(width: 40),
        ],
      ),
    );
  }
}

// =============================================================================
// 게시글 카드
// =============================================================================
class _DetailPostCard extends StatelessWidget {
  final PostModel post;
  final Color categoryColor;
  final Color categoryTextColor;
  final bool isLiked;
  final VoidCallback onLikeTap;
  final String timeAgo;

  const _DetailPostCard({
    required this.post,
    required this.categoryColor,
    required this.categoryTextColor,
    required this.isLiked,
    required this.onLikeTap,
    required this.timeAgo,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: _AppColors.cardBg,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white, width: 1.5),
        boxShadow: [
          BoxShadow(
            color: _AppColors.primary.withValues(alpha: 0.05),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: categoryColor,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  post.category,
                  style: TextStyle(
                    fontFamily: 'Noto Sans KR',
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: categoryTextColor,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                timeAgo,
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                  color: _AppColors.textSub,
                ),
              ),
              const Spacer(),
              const Text(
                '익명',
                style: TextStyle(
                  fontFamily: 'Noto Sans KR',
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: _AppColors.textMain,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            post.content,
            style: const TextStyle(
              fontSize: 16,
              height: 1.65,
              fontWeight: FontWeight.w500,
              color: _AppColors.textMain,
              letterSpacing: -0.2,
            ),
          ),
          if (post.tags.isNotEmpty) ...[
            const SizedBox(height: 14),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: post.tags.map((tag) {
                return Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 5,
                  ),
                  decoration: BoxDecoration(
                    color: _AppColors.primary.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    tag,
                    style: const TextStyle(
                      fontFamily: 'Noto Sans KR',
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.primary,
                    ),
                  ),
                );
              }).toList(),
            ),
          ],
          const SizedBox(height: 16),
          Divider(color: Colors.grey[100], height: 1),
          const SizedBox(height: 12),
          Row(
            children: [
              GestureDetector(
                onTap: onLikeTap,
                child: Row(
                  children: [
                    Icon(
                      isLiked ? Icons.favorite : Icons.favorite_border_rounded,
                      size: 20,
                      color: isLiked ? _AppColors.primary : Colors.grey[400],
                    ),
                    const SizedBox(width: 4),
                    Text(
                      '${post.likeCount}',
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color: isLiked ? _AppColors.primary : Colors.grey[500],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 20),
              Row(
                children: [
                  Icon(
                    Icons.chat_bubble_outline_rounded,
                    size: 19,
                    color: Colors.grey[400],
                  ),
                  const SizedBox(width: 4),
                  Text(
                    '${post.commentCount}',
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      color: Colors.grey[500],
                    ),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 댓글 헤더
// =============================================================================
class _CommentHeader extends StatelessWidget {
  final int count;

  const _CommentHeader({required this.count});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const Text(
          '댓글',
          style: TextStyle(
            fontFamily: 'Noto Sans KR',
            fontSize: 17,
            fontWeight: FontWeight.w800,
            color: _AppColors.textMain,
          ),
        ),
        const SizedBox(width: 6),
        Text(
          '$count',
          style: const TextStyle(
            fontFamily: 'Noto Sans KR',
            fontSize: 15,
            fontWeight: FontWeight.w700,
            color: _AppColors.primary,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 댓글 카드
// =============================================================================
class _CommentCard extends StatelessWidget {
  final CommunityCommentModel comment;
  final String timeAgo;
  final VoidCallback onReplyTap;
  final VoidCallback onLikeTap;
  final double indent;
  final bool isReply;
  final bool isLiked;

  const _CommentCard({
    required this.comment,
    required this.timeAgo,
    required this.onReplyTap,
    required this.onLikeTap,
    this.indent = 0,
    this.isReply = false,
    required this.isLiked,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(left: indent),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.86),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: Colors.white),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                if (isReply)
                  const Padding(
                    padding: EdgeInsets.only(right: 6),
                    child: Icon(
                      CupertinoIcons.arrow_turn_down_right,
                      size: 14,
                      color: _AppColors.primary,
                    ),
                  ),
                const Text(
                  '익명',
                  style: TextStyle(
                    fontFamily: 'Noto Sans KR',
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    color: _AppColors.textMain,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  timeAgo,
                  style: const TextStyle(
                    fontFamily: 'Noto Sans KR',
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: _AppColors.textSub,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              comment.content,
              style: const TextStyle(
                fontFamily: 'Noto Sans KR',
                fontSize: 14,
                height: 1.55,
                color: _AppColors.textMain,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                GestureDetector(
                  onTap: onReplyTap,
                  child: Text(
                    '답글',
                    style: TextStyle(
                      fontFamily: 'Noto Sans KR',
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: Colors.grey[600],
                    ),
                  ),
                ),
                const SizedBox(width: 16),
                GestureDetector(
                  onTap: onLikeTap,
                  child: Row(
                    children: [
                      Icon(
                        isLiked
                            ? Icons.favorite
                            : Icons.favorite_border_rounded,
                        size: 16,
                        color: isLiked ? _AppColors.primary : Colors.grey[500],
                      ),
                      const SizedBox(width: 4),
                      Text(
                        '${comment.likeCount}',
                        style: TextStyle(
                          fontFamily: 'Noto Sans KR',
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: isLiked
                              ? _AppColors.primary
                              : Colors.grey[600],
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 댓글 비어있음
// =============================================================================
class _EmptyCommentState extends StatelessWidget {
  const _EmptyCommentState();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 28),
      alignment: Alignment.center,
      child: const Text(
        '첫 댓글을 남겨보세요.',
        style: TextStyle(
          fontFamily: 'Noto Sans KR',
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: _AppColors.textSub,
        ),
      ),
    );
  }
}

// =============================================================================
// 입력창
// =============================================================================
class _CommentInputBar extends StatelessWidget {
  final TextEditingController controller;
  final bool isSubmitting;
  final String? replyPreview;
  final VoidCallback onCancelReply;
  final VoidCallback onSubmit;

  const _CommentInputBar({
    required this.controller,
    required this.isSubmitting,
    required this.replyPreview,
    required this.onCancelReply,
    required this.onSubmit,
  });

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;
    final bottomSafe = MediaQuery.of(context).padding.bottom;

    return Container(
      padding: EdgeInsets.fromLTRB(
        12,
        10,
        12,
        bottomInset > 0 ? bottomInset + 10 : bottomSafe + 10,
      ),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.92),
        border: Border(
          top: BorderSide(color: Colors.white.withValues(alpha: 0.8)),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (replyPreview != null)
            Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: _AppColors.primary.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      '답글 작성 중: $replyPreview',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontFamily: 'Noto Sans KR',
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        color: _AppColors.primary,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  GestureDetector(
                    onTap: onCancelReply,
                    child: const Icon(
                      CupertinoIcons.xmark_circle_fill,
                      size: 18,
                      color: _AppColors.primary,
                    ),
                  ),
                ],
              ),
            ),
          Row(
            children: [
              Expanded(
                child: Container(
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(22),
                    border: Border.all(
                      color: _AppColors.primary.withValues(alpha: 0.15),
                    ),
                  ),
                  child: CupertinoTextField(
                    controller: controller,
                    minLines: 1,
                    maxLines: 4,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 12,
                    ),
                    placeholder: '댓글을 남겨보세요',
                    placeholderStyle: const TextStyle(
                      fontFamily: 'Noto Sans KR',
                      fontSize: 14,
                      color: _AppColors.textSub,
                    ),
                    style: const TextStyle(
                      fontFamily: 'Noto Sans KR',
                      fontSize: 14,
                      color: _AppColors.textMain,
                    ),
                    decoration: null,
                    onSubmitted: (_) => onSubmit(),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              GestureDetector(
                onTap: isSubmitting ? null : onSubmit,
                child: Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: _AppColors.primary,
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: _AppColors.primary.withValues(alpha: 0.25),
                        blurRadius: 10,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: Center(
                    child: isSubmitting
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Icon(
                            CupertinoIcons.arrow_up,
                            color: Colors.white,
                            size: 20,
                          ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
