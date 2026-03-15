// =============================================================================
// 커뮤니티(대나무숲) 메인 화면
// 경로: lib/features/community/screens/community_screen.dart
//
// 기존 디자인 최대한 유지 + Firestore/Provider 연동
// =============================================================================

import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../../data/models/community/post_model.dart';
import '../../chat/services/chat_service.dart';
import '../../../router/route_names.dart';
import '../../../services/storage_service.dart';
import '../providers/community_provider.dart';

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
class CommunityScreen extends StatefulWidget {
  final Function(int index)? onNavTap;

  const CommunityScreen({super.key, this.onNavTap});

  @override
  State<CommunityScreen> createState() => _CommunityScreenState();
}

class _CommunityScreenState extends State<CommunityScreen> {
  final ScrollController _scrollController = ScrollController();
  final StorageService _storageService = StorageService();
  final ChatService _chatService = ChatService();
  String? _currentUserId;

  @override
  void initState() {
    super.initState();

    _loadCurrentUser();

    WidgetsBinding.instance.addPostFrameCallback((_) {
      final provider = context.read<CommunityProvider>();
      provider.initialize();
    });
  }

  Future<void> _loadCurrentUser() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (!mounted) return;
    setState(() => _currentUserId = kakaoUserId);
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
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
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return Consumer<CommunityProvider>(
      builder: (context, provider, _) {
        final posts = provider.posts;
        final selectedCategory = provider.selectedTab;
        final categories = CommunityProvider.tabs;

        return Scaffold(
          backgroundColor: Colors.white,
          body: Stack(
            children: [
              const _BackgroundDecoration(),

              SafeArea(
                bottom: false,
                child: NestedScrollView(
                  controller: _scrollController,
                  headerSliverBuilder: (context, innerBoxIsScrolled) {
                    return [
                      SliverPersistentHeader(
                        pinned: true,
                        delegate: _StickyHeaderDelegate(
                          minHeight: 110,
                          maxHeight: 110,
                          child: _HeaderArea(
                            selectedCategory: selectedCategory,
                            categories: categories,
                            onCategorySelected: (category) async {
                              HapticFeedback.selectionClick();
                              await provider.changeTab(category);
                            },
                          ),
                        ),
                      ),
                    ];
                  },
                  body: provider.isLoading && posts.isEmpty
                      ? const Center(child: CupertinoActivityIndicator())
                      : RefreshIndicator.adaptive(
                          onRefresh: provider.refreshCurrentTab,
                          child: ListView(
                            padding: const EdgeInsets.fromLTRB(16, 16, 16, 120),
                            physics: const BouncingScrollPhysics(
                              parent: AlwaysScrollableScrollPhysics(),
                            ),
                            children: [
                              if (posts.isEmpty) ...[
                                const SizedBox(height: 80),
                                const _EmptyState(),
                              ] else ...[
                                for (int i = 0; i < posts.length; i++) ...[
                                  _PostCard(
                                    post: posts[i],
                                    categoryColor: _getCategoryColor(
                                      posts[i].category,
                                    ),
                                    categoryTextColor: _getCategoryTextColor(
                                      posts[i].category,
                                    ),
                                  ),
                                  if (i < posts.length - 1)
                                    const SizedBox(height: 16),
                                ],

                                const SizedBox(height: 20),

                                if (provider.isLoadingMore)
                                  const Padding(
                                    padding: EdgeInsets.symmetric(vertical: 16),
                                    child: Center(
                                      child: CupertinoActivityIndicator(),
                                    ),
                                  )
                                else if (provider.hasMore)
                                  Center(
                                    child: CupertinoButton(
                                      padding: EdgeInsets.zero,
                                      onPressed: provider.loadMore,
                                      child: Container(
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: 20,
                                          vertical: 10,
                                        ),
                                        decoration: BoxDecoration(
                                          color: Colors.white.withValues(
                                            alpha: 0.85,
                                          ),
                                          borderRadius: BorderRadius.circular(
                                            20,
                                          ),
                                          border: Border.all(
                                            color: Colors.white,
                                          ),
                                          boxShadow: [
                                            BoxShadow(
                                              color: Colors.black.withValues(
                                                alpha: 0.05,
                                              ),
                                              blurRadius: 8,
                                              offset: const Offset(0, 2),
                                            ),
                                          ],
                                        ),
                                        child: const Text(
                                          '더보기',
                                          style: TextStyle(
                                            fontFamily: 'Noto Sans KR',
                                            fontSize: 14,
                                            fontWeight: FontWeight.w700,
                                            color: _AppColors.textMain,
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                              ],
                            ],
                          ),
                        ),
                ),
              ),

              Positioned(
                left: 24,
                right: 24,
                bottom: bottomPadding + 32,
                child: (_currentUserId == null || _currentUserId!.isEmpty)
                    ? _BottomNavBar(
                        onTap: widget.onNavTap,
                        showChatBadge: false,
                      )
                    : StreamBuilder<bool>(
                        stream: _chatService.hasAnyUnreadChats(_currentUserId!),
                        builder: (context, snapshot) {
                          final hasUnread = snapshot.data == true;
                          return _BottomNavBar(
                            onTap: widget.onNavTap,
                            showChatBadge: hasUnread,
                          );
                        },
                      ),
              ),
            ],
          ),
        );
      },
    );
  }
}

// =============================================================================
// 배경 장식
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
            color: _AppColors.primary.withValues(alpha: 0.2),
            rotation: 45,
          ),
        ),
        Positioned(
          top: 160,
          right: 48,
          child: _PetalIcon(
            size: 48,
            color: _AppColors.primary.withValues(alpha: 0.1),
            rotation: -12,
          ),
        ),
        Positioned(
          bottom: 120,
          left: 32,
          child: _PetalIcon(
            size: 24,
            color: _AppColors.primary.withValues(alpha: 0.15),
            rotation: 90,
          ),
        ),
        Positioned(
          bottom: 240,
          right: 24,
          child: _PetalIcon(
            size: 40,
            color: _AppColors.primary.withValues(alpha: 0.1),
            rotation: 180,
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
// 헤더 영역
// =============================================================================
class _HeaderArea extends StatelessWidget {
  final String selectedCategory;
  final List<String> categories;
  final Function(String) onCategorySelected;

  const _HeaderArea({
    required this.selectedCategory,
    required this.categories,
    required this.onCategorySelected,
  });

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: Container(
          color: Colors.white.withValues(alpha: 0.7),
          padding: const EdgeInsets.only(bottom: 8),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 8,
                ),
                child: Row(
                  children: [
                    _CircleIconButton(
                      icon: Icons.menu,
                      onTap: () {},
                      color: Colors.black,
                    ),
                    const Expanded(
                      child: Text(
                        '대나무숲',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontFamily: 'Noto Sans KR',
                          fontSize: 20,
                          fontWeight: FontWeight.w800,
                          color: _AppColors.textMain,
                        ),
                      ),
                    ),
                    _CircleIconButton(
                      icon: Icons.edit_outlined,
                      onTap: () async {
                        final result = await Navigator.of(
                          context,
                          rootNavigator: true,
                        ).pushNamed(RouteNames.postWrite);

                        if (result == true && context.mounted) {
                          await context
                              .read<CommunityProvider>()
                              .refreshCurrentTab();
                        }
                      },
                      color: _AppColors.primary,
                      backgroundColor: _AppColors.primary.withValues(
                        alpha: 0.1,
                      ),
                    ),
                  ],
                ),
              ),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 16),
                physics: const BouncingScrollPhysics(),
                child: Row(
                  children: categories.map((category) {
                    final isSelected = selectedCategory == category;
                    return Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: GestureDetector(
                        onTap: () => onCategorySelected(category),
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 200),
                          padding: const EdgeInsets.symmetric(
                            horizontal: 16,
                            vertical: 8,
                          ),
                          decoration: BoxDecoration(
                            color: isSelected
                                ? _AppColors.textMain
                                : Colors.white.withValues(alpha: 0.8),
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(
                              color: isSelected
                                  ? Colors.transparent
                                  : Colors.white,
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: isSelected
                                    ? Colors.black.withValues(alpha: 0.2)
                                    : Colors.black.withValues(alpha: 0.05),
                                blurRadius: 4,
                                offset: const Offset(0, 2),
                              ),
                            ],
                          ),
                          child: Text(
                            category,
                            style: TextStyle(
                              fontFamily: 'Noto Sans KR',
                              fontSize: 14,
                              fontWeight: isSelected
                                  ? FontWeight.w600
                                  : FontWeight.w500,
                              color: isSelected
                                  ? Colors.white
                                  : _AppColors.textMain,
                            ),
                          ),
                        ),
                      ),
                    );
                  }).toList(),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CircleIconButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  final Color color;
  final Color? backgroundColor;

  const _CircleIconButton({
    required this.icon,
    required this.onTap,
    required this.color,
    this.backgroundColor,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        HapticFeedback.lightImpact();
        onTap();
      },
      child: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: backgroundColor ?? Colors.transparent,
        ),
        child: Icon(icon, color: color, size: 22),
      ),
    );
  }
}

// =============================================================================
// Sticky Header Delegate
// =============================================================================
class _StickyHeaderDelegate extends SliverPersistentHeaderDelegate {
  final double minHeight;
  final double maxHeight;
  final Widget child;

  _StickyHeaderDelegate({
    required this.minHeight,
    required this.maxHeight,
    required this.child,
  });

  @override
  Widget build(
    BuildContext context,
    double shrinkOffset,
    bool overlapsContent,
  ) {
    return SizedBox.expand(child: child);
  }

  @override
  double get maxExtent => maxHeight;

  @override
  double get minExtent => minHeight;

  @override
  bool shouldRebuild(_StickyHeaderDelegate oldDelegate) {
    return maxHeight != oldDelegate.maxHeight ||
        minHeight != oldDelegate.minHeight ||
        child != oldDelegate.child;
  }
}

// =============================================================================
// 게시글 카드
// =============================================================================
class _PostCard extends StatelessWidget {
  final PostModel post;
  final Color categoryColor;
  final Color categoryTextColor;

  const _PostCard({
    required this.post,
    required this.categoryColor,
    required this.categoryTextColor,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        HapticFeedback.selectionClick();
        Navigator.of(
          context,
          rootNavigator: true,
        ).pushNamed(RouteNames.postDetail, arguments: post.postId);
      },
      child: Container(
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
            // Header
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
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
                      post.relativeTimeLabel,
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        color: _AppColors.textSub,
                      ),
                    ),
                  ],
                ),
                Icon(Icons.more_horiz, color: Colors.grey[300]),
              ],
            ),
            const SizedBox(height: 16),

            // Content
            Text(
              post.content,
              style: const TextStyle(
                fontSize: 16,
                height: 1.6,
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
                children: post.tags.take(3).map((tag) {
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

            // Footer
            Row(
              children: [
                _ActionIcon(
                  icon: Icons.favorite_border_rounded,
                  count: post.likeCount,
                  color: Colors.grey[400]!,
                ),
                const SizedBox(width: 20),
                _ActionIcon(
                  icon: Icons.chat_bubble_outline_rounded,
                  count: post.commentCount,
                  color: Colors.grey[400]!,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _ActionIcon extends StatelessWidget {
  final IconData icon;
  final int count;
  final Color color;

  const _ActionIcon({
    required this.icon,
    required this.count,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 20, color: color),
        const SizedBox(width: 4),
        Text(
          '$count',
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w600,
            color: Colors.grey[500],
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// Empty
// =============================================================================
class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Column(
        children: [
          Icon(
            CupertinoIcons.leaf_arrow_circlepath,
            size: 44,
            color: _AppColors.primary,
          ),
          SizedBox(height: 12),
          Text(
            '아직 글이 없어요',
            style: TextStyle(
              fontFamily: 'Noto Sans KR',
              fontSize: 18,
              fontWeight: FontWeight.w800,
              color: _AppColors.textMain,
            ),
          ),
          SizedBox(height: 6),
          Text(
            '첫 번째 익명 글을 남겨보세요.',
            style: TextStyle(
              fontFamily: 'Noto Sans KR',
              fontSize: 14,
              color: _AppColors.textSub,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 하단 네비게이션
// =============================================================================
class _BottomNavBar extends StatelessWidget {
  final Function(int index)? onTap;
  final bool showChatBadge;

  const _BottomNavBar({this.onTap, this.showChatBadge = false});

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(32),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.95),
            borderRadius: BorderRadius.circular(32),
            border: Border.all(color: Colors.white.withValues(alpha: 0.4)),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.15),
                blurRadius: 40,
                offset: const Offset(0, 10),
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _NavItem(
                icon: CupertinoIcons.heart_fill,
                label: '설레연',
                onTap: () => onTap?.call(0),
              ),
              _NavItem(
                icon: CupertinoIcons.chat_bubble_fill,
                label: '채팅',
                showBadge: showChatBadge,
                onTap: () => onTap?.call(1),
              ),
              _NavItem(
                icon: CupertinoIcons.calendar,
                label: '이벤트',
                onTap: () => onTap?.call(2),
              ),
              _NavItem(
                icon: CupertinoIcons.tree,
                label: '대나무숲',
                isActive: true,
                onTap: () => onTap?.call(3),
              ),
              _NavItem(
                icon: CupertinoIcons.person,
                label: '내 페이지',
                onTap: () => onTap?.call(4),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool isActive;
  final bool showBadge;
  final VoidCallback? onTap;

  const _NavItem({
    required this.icon,
    required this.label,
    this.isActive = false,
    this.showBadge = false,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Stack(
            clipBehavior: Clip.none,
            children: [
              Icon(
                icon,
                size: 24,
                color:
                    isActive ? _AppColors.primary : const Color(0xFF9CA3AF),
              ),
              if (showBadge)
                Positioned(
                  right: -2,
                  top: -2,
                  child: Container(
                    width: 8,
                    height: 8,
                    decoration: const BoxDecoration(
                      color: Color(0xFF10B981),
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            label,
            style: TextStyle(
              fontFamily: 'Noto Sans KR',
              fontSize: 10,
              fontWeight: isActive ? FontWeight.w700 : FontWeight.w500,
              letterSpacing: -0.2,
              color: isActive ? _AppColors.primary : const Color(0xFF9CA3AF),
            ),
          ),
        ],
      ),
    );
  }
}
