// =============================================================================
// 매칭 결과 화면 (3:3 미팅 상대팀)
// 경로: lib/features/matching/screens/match_result_screen.dart
//
// 사용 예시 (main.dart):
// import 'package:seolleyeon/features/matching/screens/match_result_screen.dart';
// ...
// home: const MatchResultScreen(),
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF0426E);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color textSecondary = Color(0xFF89616B);
  static const Color greenSuccess = Color(0xFF22C55E);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray400 = Color(0xFF9CA3AF);
}

// =============================================================================
// 프로필 데이터 모델
// =============================================================================
class _MatchProfile {
  final String name;
  final String birthYear;
  final String job;
  final String company;
  final String badge;
  final List<String> tags;
  final String imageUrl;

  const _MatchProfile({
    required this.name,
    required this.birthYear,
    required this.job,
    required this.company,
    required this.badge,
    required this.tags,
    required this.imageUrl,
  });
}

// =============================================================================
// 메인 화면
// =============================================================================
class MatchResultScreen extends StatefulWidget {
  const MatchResultScreen({super.key});

  @override
  State<MatchResultScreen> createState() => _MatchResultScreenState();
}

class _MatchResultScreenState extends State<MatchResultScreen> {
  final PageController _pageController = PageController(viewportFraction: 0.85);
  int _currentPage = 0;
  int _remainingRefresh = 1;

  // 더미 데이터
  final List<_MatchProfile> _profiles = const [
    _MatchProfile(
      name: '김지민',
      birthYear: '96년생',
      job: '마케팅',
      company: '스타트업',
      badge: '96% 매칭',
      tags: ['#등산', '#카페투어', '#강아지'],
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuARBjUdx7wRImXw_Y0JJ2j9owd1JzKqIvea5wW9fnQ2gU0Lhv9ek99-HrIkxuNTv_GaIUskhLi1yB6KaBsIFGmGbvzq_LxLbAUg6gECW11DLk95-kvv6EcJZib_J91lzH-6gDEL4o87JslANUuVxBlBqOqF6XWDSytCiIZQnW_k7EVHyhVMqMtL6Zd-VGj_8Iofk0R0jaFqyT3Uuj4T4E-I864VcERhw_ET9EnBh30_jrOMqGltMGa37br-KpjMxnmZezPQjZNtY6c',
    ),
    _MatchProfile(
      name: '이수진',
      birthYear: '98년생',
      job: 'UI/UX 디자인',
      company: 'IT기업',
      badge: 'New',
      tags: ['#영화', '#와인', '#전시회'],
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuAX7RWYNyEO33MEW2-LJMSnC-BuTgE25PEKMqflEwqutYGR0dzSIeqkuxvh5gOEeA4vJLkJflewaXPI0hfe2pK-VXJR067l_5QFLXz6Ucnh1C79wqeh_IVVUI24t_ux3a4jc3iLQoND-YaRICWcF__ylHITBEB8xhDPRwHaZ3IxGO5ssKv_TbHxZTLYrw5FYSJcVz1-6jFnkLqrGwqaSTDQFYgu0SPadiBSp1BB1dxgQHksodatVXJOe8oFxTzysyZE_UQq7BVJxbE',
    ),
    _MatchProfile(
      name: '박민지',
      birthYear: '95년생',
      job: 'HR',
      company: '대기업',
      badge: '인기',
      tags: ['#여행', '#맛집탐방'],
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuD9TtQ5CwBk6HIPHKGkgR8rKnHQL2xXhC8223ufnsU6rPPAnvo-i9wj8u2E7qSSyMe7wf8hDpjl0owjxf6qERa6igPkkXmjjtNrTR_lhah5EbGw8TCurxaZJ39n7JodJiMm8LKnCqJnqO8w-X-ju3k-W_QLAyB_dOs4JUEdMhu0r5QXtekERbxJwZWzglYadCj1QTO0oshbZ9pYA3Qt49FQhh9ARkCP3XzxvssTq1ZGiVBdPBssCLsZO0ntfAqKvrpOQhs2lfFn6zI',
    ),
  ];

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  void _onSendRequest() {
    HapticFeedback.mediumImpact();
    // TODO: 미팅 요청 보내기
  }

  void _onRefresh() {
    if (_remainingRefresh > 0) {
      HapticFeedback.lightImpact();
      setState(() => _remainingRefresh--);
      // TODO: 다시 돌리기 로직
    }
  }

  void _onSafetyTap() {
    HapticFeedback.selectionClick();
    // TODO: 안전 만남 안내 시트
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          SafeArea(
            bottom: false,
            child: Column(
              children: [
                // 헤더
                _Header(onBackPressed: () => Navigator.of(context).pop()),
                // 스크롤 영역
                Expanded(
                  child: SingleChildScrollView(
                    physics: const BouncingScrollPhysics(),
                    child: Column(
                      children: [
                        // 타이틀 섹션
                        const _TitleSection(),
                        const SizedBox(height: 24),
                        // 프로필 캐러셀
                        SizedBox(
                          height: 480,
                          child: PageView.builder(
                            controller: _pageController,
                            itemCount: _profiles.length,
                            onPageChanged: (index) {
                              setState(() => _currentPage = index);
                            },
                            itemBuilder: (context, index) {
                              return _ProfileCard(profile: _profiles[index]);
                            },
                          ),
                        ),
                        const SizedBox(height: 16),
                        // 페이지 인디케이터
                        _PageIndicator(
                          total: _profiles.length,
                          current: _currentPage,
                        ),
                        const SizedBox(height: 24),
                        // 안전 칩
                        _SafetyChip(onTap: _onSafetyTap),
                        const SizedBox(height: 140),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
          // 하단 CTA
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: _BottomCTA(
              onSend: _onSendRequest,
              onRefresh: _onRefresh,
              remainingRefresh: _remainingRefresh,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final VoidCallback onBackPressed;

  const _Header({required this.onBackPressed});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(44, 44),
            onPressed: onBackPressed,
            child: const Icon(
              CupertinoIcons.back,
              color: _AppColors.textMain,
              size: 24,
            ),
          ),
          const Expanded(
            child: Text(
              '매칭 결과',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: _AppColors.textMain,
                letterSpacing: -0.3,
              ),
            ),
          ),
          const SizedBox(width: 44),
        ],
      ),
    );
  }
}

// =============================================================================
// 타이틀 섹션
// =============================================================================
class _TitleSection extends StatelessWidget {
  const _TitleSection();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        children: [
          // 배지
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: _AppColors.primary.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  CupertinoIcons.game_controller,
                  size: 14,
                  color: _AppColors.primary,
                ),
                const SizedBox(width: 6),
                const Text(
                  '매칭 결과 3 / 3',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: _AppColors.primary,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          // 타이틀
          const Text(
            '오늘의 3:3\n매칭 상대팀입니다',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 24,
              fontWeight: FontWeight.w700,
              height: 1.3,
              letterSpacing: -0.5,
              color: _AppColors.textMain,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            '설레는 만남을 위해 정성껏 매칭했어요',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              fontWeight: FontWeight.w400,
              color: _AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 프로필 카드
// =============================================================================
class _ProfileCard extends StatelessWidget {
  final _MatchProfile profile;

  const _ProfileCard({required this.profile});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: Container(
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: CupertinoColors.white.withValues(alpha: 0.5),
          ),
          boxShadow: [
            BoxShadow(
              color: CupertinoColors.black.withValues(alpha: 0.08),
              blurRadius: 40,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // 이미지 영역
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(24),
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      // 이미지
                      Image.network(
                        profile.imageUrl,
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => Container(
                          color: _AppColors.gray100,
                          child: const Icon(
                            CupertinoIcons.person_fill,
                            size: 64,
                            color: _AppColors.gray400,
                          ),
                        ),
                      ),
                      // 그라데이션 오버레이
                      Container(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [
                              const Color(0x00000000),
                              CupertinoColors.black.withValues(alpha: 0.4),
                            ],
                            stops: const [0.5, 1.0],
                          ),
                        ),
                      ),
                      // 배지
                      Positioned(
                        left: 12,
                        bottom: 12,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 12,
                            vertical: 6,
                          ),
                          decoration: BoxDecoration(
                            color: CupertinoColors.white.withValues(alpha: 0.2),
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(
                              color: CupertinoColors.white.withValues(
                                alpha: 0.2,
                              ),
                            ),
                          ),
                          child: Text(
                            profile.badge,
                            style: const TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              color: CupertinoColors.white,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              // 프로필 정보
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          profile.name,
                          style: const TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 20,
                            fontWeight: FontWeight.w700,
                            color: _AppColors.textMain,
                          ),
                        ),
                        Text(
                          profile.birthYear,
                          style: const TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 14,
                            fontWeight: FontWeight.w400,
                            color: _AppColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${profile.job} · ${profile.company}',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                        color: _AppColors.textMain.withValues(alpha: 0.8),
                      ),
                    ),
                    const SizedBox(height: 12),
                    // 태그
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: profile.tags.map((tag) {
                        return Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 12,
                            vertical: 6,
                          ),
                          decoration: BoxDecoration(
                            color: _AppColors.backgroundLight,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: Text(
                            tag,
                            style: const TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              color: _AppColors.textSecondary,
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 페이지 인디케이터
// =============================================================================
class _PageIndicator extends StatelessWidget {
  final int total;
  final int current;

  const _PageIndicator({required this.total, required this.current});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(total, (index) {
        final isActive = index == current;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 300),
          margin: const EdgeInsets.symmetric(horizontal: 4),
          width: isActive ? 24 : 8,
          height: 8,
          decoration: BoxDecoration(
            color: isActive ? _AppColors.primary : _AppColors.gray100,
            borderRadius: BorderRadius.circular(4),
          ),
        );
      }),
    );
  }
}

// =============================================================================
// 안전 칩
// =============================================================================
class _SafetyChip extends StatelessWidget {
  final VoidCallback onTap;

  const _SafetyChip({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: _AppColors.gray100),
          boxShadow: [
            BoxShadow(
              color: CupertinoColors.black.withValues(alpha: 0.04),
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              CupertinoIcons.shield_fill,
              size: 18,
              color: _AppColors.greenSuccess,
            ),
            const SizedBox(width: 8),
            Text(
              '안전 만남 보장 · 예치금/안전 안내',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 12,
                fontWeight: FontWeight.w500,
                color: _AppColors.textMain.withValues(alpha: 0.7),
              ),
            ),
            const SizedBox(width: 4),
            const Icon(
              CupertinoIcons.chevron_right,
              size: 16,
              color: _AppColors.gray400,
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 하단 CTA
// =============================================================================
class _BottomCTA extends StatelessWidget {
  final VoidCallback onSend;
  final VoidCallback onRefresh;
  final int remainingRefresh;

  const _BottomCTA({
    required this.onSend,
    required this.onRefresh,
    required this.remainingRefresh,
  });

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return Container(
      padding: EdgeInsets.fromLTRB(20, 16, 20, bottomPadding + 16),
      decoration: BoxDecoration(
        color: CupertinoColors.white.withValues(alpha: 0.9),
        border: Border(top: BorderSide(color: _AppColors.gray100)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 메인 버튼
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: onSend,
            child: Container(
              width: double.infinity,
              height: 56,
              decoration: BoxDecoration(
                color: _AppColors.primary,
                borderRadius: BorderRadius.circular(16),
                boxShadow: [
                  BoxShadow(
                    color: _AppColors.primary.withValues(alpha: 0.3),
                    blurRadius: 20,
                    offset: const Offset(0, 6),
                  ),
                ],
              ),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    '팀 전체에게 미팅 요청 보내기',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                      color: CupertinoColors.white,
                    ),
                  ),
                  SizedBox(width: 8),
                  Icon(
                    CupertinoIcons.paperplane_fill,
                    size: 18,
                    color: CupertinoColors.white,
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          // 다시 돌리기 버튼
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: remainingRefresh > 0 ? onRefresh : null,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  CupertinoIcons.refresh,
                  size: 18,
                  color: remainingRefresh > 0
                      ? _AppColors.textSecondary
                      : _AppColors.gray400,
                ),
                const SizedBox(width: 6),
                Text(
                  '다시 돌리기 ($remainingRefresh회 남음)',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: remainingRefresh > 0
                        ? _AppColors.textSecondary
                        : _AppColors.gray400,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
