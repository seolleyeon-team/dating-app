// =============================================================================
// 3:3 시즌 미팅 인트로 튜토리얼 화면 (이벤트 배너 카드)
// 경로: lib/features/tutorial/screens/season_meeting_intro_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const SeasonMeetingIntroScreen()),
// );
// =============================================================================

import 'dart:ui';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import '../../../router/route_names.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF4D88);
  static const Color backgroundLight = Color(0xFFFFF5F8);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF1F2937);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color gray300 = Color(0xFFD1D5DB);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color pink50 = Color(0xFFFDF2F8);
  static const Color pink100 = Color(0xFFFCE7F3);
  static const Color purple100 = Color(0xFFF3E8FF);
  static const Color purple600 = Color(0xFF9333EA);
  static const Color pink300 = Color(0xFFF9A8D4);
}

// =============================================================================
// 메인 화면
// =============================================================================
class SeasonMeetingIntroScreen extends StatelessWidget {
  final VoidCallback? onApply;

  const SeasonMeetingIntroScreen({super.key, this.onApply});

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          // 상단 그라데이션
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            height: MediaQuery.of(context).size.height * 0.5,
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    _AppColors.pink100.withValues(alpha: 0.6),
                    _AppColors.backgroundLight.withValues(alpha: 0),
                  ],
                ),
              ),
            ),
          ),
          // 메인 콘텐츠
          SafeArea(
            bottom: false,
            child: Column(
              children: [
                // 헤더
                const _Header(),
                // 콘텐츠
                Expanded(
                  child: SingleChildScrollView(
                    physics: const BouncingScrollPhysics(),
                    padding: EdgeInsets.fromLTRB(
                      20,
                      16,
                      20,
                      bottomPadding + 120,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // 타이틀
                        const _TitleSection(),
                        const SizedBox(height: 24),
                        // 이벤트 카드
                        _EventCard(onApply: onApply),
                        const SizedBox(height: 32),
                        // 페이지 인디케이터
                        const _PageIndicator(),
                        const SizedBox(height: 16),
                        // 스와이프 힌트
                        const Center(
                          child: Text(
                            'Swipe left to see more upcoming events',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 12,
                              color: _AppColors.textSecondary,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
          // 하단 네비게이션
          Positioned(
            left: 20,
            right: 20,
            bottom: bottomPadding + 24,
            child: const _BottomNavBar(),
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
  const _Header();

  @override
  Widget build(BuildContext context) {
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: Container(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 12),
          color: _AppColors.backgroundLight.withValues(alpha: 0.8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              // 로고
              const Row(
                children: [
                  Icon(
                    CupertinoIcons.heart_fill,
                    color: _AppColors.primary,
                    size: 28,
                  ),
                  SizedBox(width: 8),
                  Text(
                    '설레연',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 24,
                      fontWeight: FontWeight.w900,
                      letterSpacing: -0.5,
                      color: _AppColors.textMain,
                    ),
                  ),
                ],
              ),
              // 우측 버튼
              Row(
                children: [
                  // AI 취향 분석 버튼
                  Container(
                    padding: const EdgeInsets.fromLTRB(8, 8, 14, 8),
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(
                        colors: [_AppColors.pink50, _AppColors.purple100],
                      ),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: _AppColors.pink100.withValues(alpha: 0.5),
                      ),
                    ),
                    child: const Row(
                      children: [
                        Icon(
                          CupertinoIcons.sparkles,
                          size: 14,
                          color: _AppColors.primary,
                        ),
                        SizedBox(width: 6),
                        Text(
                          'AI 취향 분석',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                            color: _AppColors.textMain,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 12),
                  // 알림
                  Stack(
                    children: [
                      const Icon(
                        CupertinoIcons.bell,
                        size: 24,
                        color: _AppColors.gray400,
                      ),
                      Positioned(
                        top: 2,
                        right: 2,
                        child: Container(
                          width: 10,
                          height: 10,
                          decoration: BoxDecoration(
                            color: _AppColors.primary,
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: _AppColors.backgroundLight,
                              width: 2,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
        ),
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
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // PREMIUM EVENT 배지
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: _AppColors.purple100,
                borderRadius: BorderRadius.circular(6),
              ),
              child: const Text(
                'PREMIUM EVENT',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1,
                  color: _AppColors.purple600,
                ),
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              '이달의 이벤트',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 28,
                fontWeight: FontWeight.w700,
                color: _AppColors.textMain,
              ),
            ),
          ],
        ),
        CupertinoButton(
          padding: const EdgeInsets.all(8),
          onPressed: () {},
          child: const Icon(
            CupertinoIcons.gear,
            size: 22,
            color: _AppColors.gray400,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 이벤트 카드
// =============================================================================
class _EventCard extends StatelessWidget {
  final VoidCallback? onApply;

  const _EventCard({this.onApply});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      height: 480,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.2),
            blurRadius: 30,
            offset: const Offset(0, 15),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(28),
        child: Stack(
          children: [
            // 배경 이미지
            Positioned.fill(
              child: Image.network(
                'https://lh3.googleusercontent.com/aida-public/AB6AXuDIzeAuIYaRUxnoZ4CYkgzsDZnHZ1lHW9heZAPx8BVDVLcP0JCvYzJZA22Ci5vSP0SYf0OZeCTnGYxz5mF1OWdQBsLENkg0PPumFiYXMsX_G1T_TWnBhzubbHrFfeBF0gDPJ7JNuctcOSYru_PHJca5noPbuS8f5l4hDFd0eNnJWR9jSll9TZVgqTcL_LUvPFhXUH6Du3vdg9ejT2nZl5-UVe6gopy7u2TEhFlzQYGsYkp_uhNnR2HukqTcCfvHIu9AMXqkLpBFuCc',
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) =>
                    Container(color: _AppColors.gray300),
              ),
            ),
            // 그라데이션
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      CupertinoColors.black.withValues(alpha: 0),
                      CupertinoColors.black.withValues(alpha: 0.4),
                      CupertinoColors.black.withValues(alpha: 0.9),
                    ],
                    stops: const [0.0, 0.5, 1.0],
                  ),
                ),
              ),
            ),
            // 상단 배지
            Positioned(
              top: 20,
              left: 20,
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 8,
                ),
                decoration: BoxDecoration(
                  color: _AppColors.surfaceLight.withValues(alpha: 0.95),
                  borderRadius: BorderRadius.circular(20),
                  boxShadow: [
                    BoxShadow(
                      color: CupertinoColors.black.withValues(alpha: 0.15),
                      blurRadius: 10,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: const Row(
                  children: [
                    Icon(
                      CupertinoIcons.ticket_fill,
                      size: 14,
                      color: _AppColors.primary,
                    ),
                    SizedBox(width: 6),
                    Text(
                      '1st Free (첫 참여 무료)',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 12,
                        fontWeight: FontWeight.w800,
                        color: _AppColors.primary,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            // 하단 콘텐츠
            Positioned(
              left: 20,
              right: 20,
              bottom: 20,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(20),
                child: BackdropFilter(
                  filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
                  child: Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: CupertinoColors.white.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: CupertinoColors.white.withValues(alpha: 0.2),
                      ),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // 타이틀
                        RichText(
                          text: const TextSpan(
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 24,
                              fontWeight: FontWeight.w700,
                              height: 1.3,
                              color: CupertinoColors.white,
                            ),
                            children: [
                              TextSpan(text: '3:3 시즌 미팅은,\n'),
                              TextSpan(
                                text: '한정판 설렘',
                                style: TextStyle(
                                  foreground: null,
                                  color: _AppColors.pink300,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 12),
                        // 설명
                        Text(
                          '친구들과 팀을 이뤄 특별한 테마의 미팅에 참여하세요.\n와인, 서핑, 독서 등 취향이 맞는 상대를 만나요.',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 14,
                            height: 1.5,
                            fontWeight: FontWeight.w300,
                            color: CupertinoColors.white.withValues(alpha: 0.9),
                          ),
                        ),
                        const SizedBox(height: 20),
                        // 신청 버튼
                        CupertinoButton(
                          padding: EdgeInsets.zero,
                          onPressed: () {
                            HapticFeedback.mediumImpact();
                            if (onApply != null) {
                              onApply!();
                            } else {
                              Navigator.of(context).pushNamed(RouteNames.teamSetup);
                            }
                          },
                          child: Container(
                            width: double.infinity,
                            height: 52,
                            decoration: BoxDecoration(
                              color: _AppColors.primary,
                              borderRadius: BorderRadius.circular(14),
                              boxShadow: [
                                BoxShadow(
                                  color: _AppColors.primary.withValues(
                                    alpha: 0.3,
                                  ),
                                  blurRadius: 20,
                                  offset: const Offset(0, 6),
                                ),
                              ],
                            ),
                            child: const Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Text(
                                  '지금 신청하기',
                                  style: TextStyle(
                                    fontFamily: 'Pretendard',
                                    fontSize: 16,
                                    fontWeight: FontWeight.w700,
                                    color: CupertinoColors.white,
                                  ),
                                ),
                                SizedBox(width: 6),
                                Icon(
                                  CupertinoIcons.arrow_right,
                                  size: 16,
                                  color: CupertinoColors.white,
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 페이지 인디케이터
// =============================================================================
class _PageIndicator extends StatelessWidget {
  const _PageIndicator();

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Container(
          width: 6,
          height: 6,
          decoration: const BoxDecoration(
            color: _AppColors.gray300,
            shape: BoxShape.circle,
          ),
        ),
        const SizedBox(width: 8),
        Container(
          width: 32,
          height: 6,
          decoration: BoxDecoration(
            color: _AppColors.primary,
            borderRadius: BorderRadius.circular(3),
          ),
        ),
        const SizedBox(width: 8),
        Container(
          width: 6,
          height: 6,
          decoration: const BoxDecoration(
            color: _AppColors.gray300,
            shape: BoxShape.circle,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 하단 네비게이션
// =============================================================================
class _BottomNavBar extends StatelessWidget {
  const _BottomNavBar();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 12),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(32),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.04),
            blurRadius: 25,
            offset: const Offset(0, -4),
          ),
        ],
        border: Border.all(
          color: CupertinoColors.black.withValues(alpha: 0.05),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          _NavItem(icon: CupertinoIcons.heart, label: '설레연', isActive: false),
          _NavItem(
            icon: CupertinoIcons.chat_bubble,
            label: '채팅',
            isActive: false,
          ),
          _CenterNavItem(),
          _NavItem(icon: CupertinoIcons.tree, label: '대나무숲', isActive: false),
          _NavItem(
            icon: CupertinoIcons.person,
            label: '내 페이지',
            isActive: false,
          ),
        ],
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool isActive;

  const _NavItem({
    required this.icon,
    required this.label,
    required this.isActive,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 48,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            icon,
            size: 24,
            color: isActive ? _AppColors.primary : _AppColors.gray300,
          ),
          const SizedBox(height: 4),
          Text(
            label,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 9,
              fontWeight: isActive ? FontWeight.w700 : FontWeight.w500,
              color: isActive ? _AppColors.primary : _AppColors.gray400,
            ),
          ),
        ],
      ),
    );
  }
}

class _CenterNavItem extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 48,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 플로팅 버튼
          Transform.translate(
            offset: const Offset(0, -28),
            child: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: _AppColors.primary,
                shape: BoxShape.circle,
                border: Border.all(color: _AppColors.backgroundLight, width: 4),
                boxShadow: [
                  BoxShadow(
                    color: _AppColors.primary.withValues(alpha: 0.3),
                    blurRadius: 20,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: const Icon(
                CupertinoIcons.calendar,
                size: 24,
                color: CupertinoColors.white,
              ),
            ),
          ),
          const Text(
            '이벤트',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 9,
              fontWeight: FontWeight.w700,
              color: _AppColors.primary,
            ),
          ),
        ],
      ),
    );
  }
}
