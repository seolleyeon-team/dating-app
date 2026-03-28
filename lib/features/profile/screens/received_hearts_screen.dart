// =============================================================================
// 받은 하트 목록 화면 (블라인드 하트 그리드)
// 경로: lib/features/hearts/screens/received_hearts_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const ReceivedHeartsScreen()),
// );
// =============================================================================

import 'dart:ui';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF0426E);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color gray400 = Color(0xFF9CA3AF);
}

// =============================================================================
// 하트 모델
// =============================================================================
class _HeartProfile {
  final String id;
  final String imageUrl;
  final String occupation;
  final String location;
  final int age;
  final String detail;
  final int heartCount;

  const _HeartProfile({
    required this.id,
    required this.imageUrl,
    required this.occupation,
    required this.location,
    required this.age,
    required this.detail,
    required this.heartCount,
  });
}

// =============================================================================
// 메인 화면
// =============================================================================
class ReceivedHeartsScreen extends StatefulWidget {
  final VoidCallback? onBack;
  final Function(String)? onReveal;
  final int? selectedNavIndex;
  final Function(int)? onNavTap;

  const ReceivedHeartsScreen({
    super.key,
    this.onBack,
    this.onReveal,
    this.selectedNavIndex,
    this.onNavTap,
  });

  @override
  State<ReceivedHeartsScreen> createState() => _ReceivedHeartsScreenState();
}

class _ReceivedHeartsScreenState extends State<ReceivedHeartsScreen> {
  int _selectedFilter = 0;
  final List<String> _filters = ['All', 'Recent', 'Online', 'Super Likes'];

  final List<_HeartProfile> _profiles = const [
    _HeartProfile(
      id: '1',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuDqbAjGqwEHMkww26UMXmCnBcmHFyOeYy-7szhHZJqS-RvLsPcVJaSQav-OdLe1OcFh9HWNMKo01ojE3jI8bvbZZDUXXnj8Y6T6YCpxcUowu18YtlkSjpyd62GZHo7rKEPfiYKNxOHAGJVfJHrCYzsr9Ux-69OyhhOTufLtmMvmXGibH3y_SLVOC7W-pX1CyWYwlafzKKVttVpf3y1M_8-kZYOslrOB28QG9ycPozHJXOaWlMVRsprWAlCeUqhPUdhn9VE21qorV_k',
      occupation: 'Architect',
      location: 'Seoul',
      age: 24,
      detail: '168cm',
      heartCount: 3,
    ),
    _HeartProfile(
      id: '2',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuA0ov9riqLEBQ-BsFNvPd7ZaopIz6d6lP_9mC7ETfON39sAotnU1jq97F-5mq6nq7ad0tZomixODhHFeD-oEdXWBHJ8Ze9REBH3Yg1PX_PsNjGYXtsGdqwAN_sD87gozsHoZ4r1F1eXV9O6LdAavEvKRIGTOLHOZEqn2lw073zly55jYixHlO6ThMfAbTL2T0UBh1bel4j8Kr9D5yI8xTfiSn9xGLegJax946KRrzvo26uy_TZgS_uDRqJ1dA2bx1g1sj0tOQv0sFE',
      occupation: 'Musician',
      location: '5km',
      age: 27,
      detail: 'Nearby',
      heartCount: 1,
    ),
    _HeartProfile(
      id: '3',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuBdrOhfLj3oJ8bPuscFoUkZUw3uF8P9it7vqnbF7e-3DJ9VGO35QuImRqrqGk7FXvhQib-C0m4i10XNS4zFVco2YywVEZXJSBLTJQfW3rUizEzUVL_jOY8_JGbWH9Z7SkU-D1gfcXsH1IBu-DdHU3dlMN3Cxm-tsJ2tj0imYkftHWi_br_jJzFgieTl813MiJMMdMr1qFE0-S0aGTz0P-QP2lQx0sUf0CW2qTd6yRTF-crE09YnOVD6zOgzkZZcOJS1JWbrNcMkDnw',
      occupation: 'Designer',
      location: '2km',
      age: 22,
      detail: 'Student',
      heartCount: 5,
    ),
    _HeartProfile(
      id: '4',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuC_dagyNZkbZbiP_zRl16tyoJA9ukJEwtMNCGv03v6dlAbsgNImQe8S0BQ-80D5F_gnxWMgCZHgFW-1AIrVcKU7T7PWAu1J-HkoY9vll9fuRE5RY8TVx6qB1rA9XoqStqPIvyRraTMVOCYPBEJRSXlZRBkr-8SUhTuL8nL-lYfRQO1dD7SO4BqpMxgvpF5qmLWXAzmddHGmMVShOU1krULJCa_r5Jphl4YQpomd0ujrPzRcYdOfVhnGlescr_1eyXa-NlgxyYuHv-A',
      occupation: 'Model',
      location: '10km',
      age: 25,
      detail: 'Freelance',
      heartCount: 2,
    ),
    _HeartProfile(
      id: '5',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuAGnjWH2aEm5YNed5rwIeIz06qDUdM9VegwVuNH7rzD673sR3Zg-010IAeWiuCkhhf1XMyNZppa74KuDDZ8lCvd4a3xAFpeCz_gEgvaeoOSsPS5j4LpyQzCLz2n1LdFfSqyEvWPItscminPyz-1e4BCGJnQRrdn41zNkTnq5dK5KkHDJBMWUPsOpRtBU6tew2AC1EHNYKvHwwY0r2hHtfKWrfHM3sq1T--8YJZ7SiRg5Dgl3D2v3jNsbgTT_4Yj119YXvYG0gmuIK8',
      occupation: 'Engineer',
      location: 'Nearby',
      age: 29,
      detail: 'Tech',
      heartCount: 8,
    ),
    _HeartProfile(
      id: '6',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuB1PyvYdPGZC5X88Kja1nbS1VSTqR8DpkpJQlNYH9vFFNcAGq_gXomcXJcvCaweR6WOvOZyYLDyJMaJYsXLYPw1xsSOrJVLdFd9-1qAFaMdZAtLkTCsG37_C84TzZrOUsFGXgWeEA-GdZMy7RjZH2z0RZfdKwyAtDqZfT9zSJYrYy1IBiddz6KiMpr1viljqkueHAEJBg9BF1aedjlFJW7Yg2vVf6PH-hWMgo0gqk7wXkH4Zm6TkghAJyZFQtaAYIecsb_RcTW-8RI',
      occupation: 'Writer',
      location: '1km',
      age: 26,
      detail: 'Arts',
      heartCount: 1,
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.surfaceLight,
      child: Stack(
        children: [
          // 배경 그라데이션
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            height: 256,
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    _AppColors.primary.withValues(alpha: 0.1),
                    CupertinoColors.white.withValues(alpha: 0),
                  ],
                ),
              ),
            ),
          ),
          // 메인 콘텐츠
          CustomScrollView(
            physics: const BouncingScrollPhysics(),
            slivers: [
              // 헤더
              _StickyHeader(
                onBack: widget.onBack,
                profileCount: _profiles.length,
                filters: _filters,
                selectedFilter: _selectedFilter,
                topPadding: MediaQuery.of(context).padding.top,
                onFilterChanged: (index) {
                  setState(() => _selectedFilter = index);
                },
              ),
              // 그리드
              SliverPadding(
                padding: const EdgeInsets.all(16),
                sliver: SliverGrid(
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 2,
                    mainAxisSpacing: 16,
                    crossAxisSpacing: 16,
                    childAspectRatio: 1,
                  ),
                  delegate: SliverChildBuilderDelegate(
                    (context, index) => _HeartCard(
                      profile: _profiles[index],
                      onReveal: () =>
                          widget.onReveal?.call(_profiles[index].id),
                    ),
                    childCount: _profiles.length,
                  ),
                ),
              ),
              // 하단 메시지
              SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.fromLTRB(16, 32, 16, bottomPadding + 16),
                  child: Column(
                    children: [
                      const Text(
                        "That's all for now!",
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 14,
                          color: _AppColors.gray400,
                        ),
                      ),
                      const SizedBox(height: 8),
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: () {},
                        child: const Text(
                          'Boost your profile',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                            color: _AppColors.primary,
                          ),
                        ),
                      ),
                    ],
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

// =============================================================================
// 스티키 헤더
// =============================================================================
class _StickyHeader extends StatelessWidget {
  final VoidCallback? onBack;
  final int profileCount;
  final List<String> filters;
  final int selectedFilter;
  final double topPadding;
  final ValueChanged<int> onFilterChanged;

  const _StickyHeader({
    this.onBack,
    required this.profileCount,
    required this.filters,
    required this.selectedFilter,
    required this.topPadding,
    required this.onFilterChanged,
  });

  @override
  Widget build(BuildContext context) {
    return SliverPersistentHeader(
      pinned: true,
      delegate: _StickyHeaderDelegate(
        onBack: onBack,
        profileCount: profileCount,
        filters: filters,
        selectedFilter: selectedFilter,
        topPadding: topPadding,
        onFilterChanged: onFilterChanged,
      ),
    );
  }
}

class _StickyHeaderDelegate extends SliverPersistentHeaderDelegate {
  final VoidCallback? onBack;
  final int profileCount;
  final List<String> filters;
  final int selectedFilter;
  final double topPadding;
  final ValueChanged<int> onFilterChanged;

  _StickyHeaderDelegate({
    this.onBack,
    required this.profileCount,
    required this.filters,
    required this.selectedFilter,
    required this.topPadding,
    required this.onFilterChanged,
  });

  @override
  double get minExtent => 110 + topPadding;

  @override
  double get maxExtent => 110 + topPadding;

  @override
  bool shouldRebuild(covariant _StickyHeaderDelegate oldDelegate) {
    return oldDelegate.selectedFilter != selectedFilter;
  }

  @override
  Widget build(
    BuildContext context,
    double shrinkOffset,
    bool overlapsContent,
  ) {
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: Container(
          decoration: BoxDecoration(
            color: _AppColors.surfaceLight.withValues(alpha: 0.8),
            border: Border(
              bottom: BorderSide(color: _AppColors.gray100, width: 1),
            ),
          ),
          child: SafeArea(
            bottom: false,
            child: Column(
              children: [
                // 타이틀 바
                Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 8,
                  ),
                  child: Row(
                    children: [
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: () {
                          HapticFeedback.lightImpact();
                          if (onBack != null) {
                            onBack!.call();
                          } else {
                            Navigator.of(context).pop();
                          }
                        },
                        child: Container(
                          width: 40,
                          height: 40,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: CupertinoColors.black.withValues(
                              alpha: 0.05,
                            ),
                          ),
                          child: const Icon(
                            CupertinoIcons.back,
                            size: 20,
                            color: _AppColors.textMain,
                          ),
                        ),
                      ),
                      Expanded(
                        child: Text(
                          'Received Hearts ($profileCount)',
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            letterSpacing: -0.3,
                            color: _AppColors.textMain,
                          ),
                        ),
                      ),
                      const SizedBox(width: 40),
                    ],
                  ),
                ),
                // 필터 칩
                SizedBox(
                  height: 36,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    itemCount: filters.length,
                    separatorBuilder: (_, __) => const SizedBox(width: 12),
                    itemBuilder: (context, index) {
                      final isSelected = selectedFilter == index;
                      return CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: () => onFilterChanged(index),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 20),
                          decoration: BoxDecoration(
                            color: isSelected
                                ? _AppColors.primary
                                : _AppColors.surfaceLight,
                            borderRadius: BorderRadius.circular(18),
                            border: isSelected
                                ? null
                                : Border.all(color: _AppColors.gray200),
                            boxShadow: isSelected
                                ? [
                                    BoxShadow(
                                      color: _AppColors.primary.withValues(
                                        alpha: 0.3,
                                      ),
                                      blurRadius: 8,
                                      offset: const Offset(0, 2),
                                    ),
                                  ]
                                : null,
                          ),
                          child: Center(
                            child: Text(
                              filters[index],
                              style: TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 14,
                                fontWeight: isSelected
                                    ? FontWeight.w600
                                    : FontWeight.w500,
                                color: isSelected
                                    ? CupertinoColors.white
                                    : _AppColors.textMain,
                              ),
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 하트 카드
// =============================================================================
class _HeartCard extends StatelessWidget {
  final _HeartProfile profile;
  final VoidCallback? onReveal;

  const _HeartCard({required this.profile, this.onReveal});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: _AppColors.gray100,
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.05),
            blurRadius: 10,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Stack(
        fit: StackFit.expand,
        children: [
          // 블러 이미지
          Transform.scale(
            scale: 1.1,
            child: ImageFiltered(
              imageFilter: ImageFilter.blur(sigmaX: 15, sigmaY: 15),
              child: Image.network(
                profile.imageUrl,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) =>
                    Container(color: _AppColors.gray100),
              ),
            ),
          ),
          // 그라데이션
          Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  CupertinoColors.black.withValues(alpha: 0),
                  CupertinoColors.black.withValues(alpha: 0.2),
                  CupertinoColors.black.withValues(alpha: 0.7),
                ],
                stops: const [0.0, 0.5, 1.0],
              ),
            ),
          ),
          // 콘텐츠
          Positioned(
            left: 12,
            right: 12,
            bottom: 12,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // 정보
                Text(
                  '${profile.occupation} • ${profile.location}',
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: CupertinoColors.white,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '${profile.age} • ${profile.detail}',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: CupertinoColors.white.withValues(alpha: 0.8),
                  ),
                ),
                const SizedBox(height: 12),
                // 액션 row
                Row(
                  children: [
                    // 하트 배지
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 6,
                      ),
                      decoration: BoxDecoration(
                        color: CupertinoColors.white.withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(
                            CupertinoIcons.heart_fill,
                            size: 14,
                            color: _AppColors.primary,
                          ),
                          const SizedBox(width: 4),
                          Text(
                            '${profile.heartCount}',
                            style: const TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 12,
                              fontWeight: FontWeight.w700,
                              color: CupertinoColors.white,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    // Reveal 버튼
                    Expanded(
                      child: CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: () {
                          HapticFeedback.mediumImpact();
                          onReveal?.call();
                        },
                        child: Container(
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          decoration: BoxDecoration(
                            color: _AppColors.primary,
                            borderRadius: BorderRadius.circular(16),
                            boxShadow: [
                              BoxShadow(
                                color: _AppColors.primary.withValues(
                                  alpha: 0.3,
                                ),
                                blurRadius: 8,
                                offset: const Offset(0, 2),
                              ),
                            ],
                          ),
                          child: const Center(
                            child: Text(
                              'Reveal',
                              style: TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 12,
                                fontWeight: FontWeight.w700,
                                color: CupertinoColors.white,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
