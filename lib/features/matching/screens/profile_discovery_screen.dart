// =============================================================================
// 오늘의 설레연 (프로필 디스커버리) 화면
// 경로: lib/features/matching/screens/profile_discovery_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const ProfileDiscoveryScreen()),
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
  static const Color pink50 = Color(0xFFFDF2F8);
  static const Color pink100 = Color(0xFFFCE7F3);
  static const Color pink500 = Color(0xFFEC4899);
  static const Color purple100 = Color(0xFFEDE9FE);
  static const Color purple600 = Color(0xFF9333EA);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color gray300 = Color(0xFFD1D5DB);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray500 = Color(0xFF6B7280);
  static const Color gray800 = Color(0xFF1F2937);
  static const Color gray900 = Color(0xFF111827);
}

// =============================================================================
// 프로필 모델
// =============================================================================
class _DiscoveryProfile {
  final String name;
  final String major;
  final String year;
  final int matchPercent;
  final String imageUrl;
  final List<String> tags;

  const _DiscoveryProfile({
    required this.name,
    required this.major,
    required this.year,
    required this.matchPercent,
    required this.imageUrl,
    this.tags = const [],
  });
}

// =============================================================================
// 메인 화면
// =============================================================================
class ProfileDiscoveryScreen extends StatelessWidget {
  final int notificationCount;
  final int remainingMatches;
  final VoidCallback? onAiPreference;
  final VoidCallback? onNotification;
  final VoidCallback? onSettings;
  final VoidCallback? onViewProfile;
  final VoidCallback? onSendLike;
  final Function(int index)? onNavTap;

  const ProfileDiscoveryScreen({
    super.key,
    this.notificationCount = 1,
    this.remainingMatches = 2,
    this.onAiPreference,
    this.onNotification,
    this.onSettings,
    this.onViewProfile,
    this.onSendLike,
    this.onNavTap,
  });

  static const List<_DiscoveryProfile> _profiles = [
    _DiscoveryProfile(
      name: 'Ji-min',
      major: 'Business Admin',
      year: "'01",
      matchPercent: 94,
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuA-iKoOfd7mUBhLCu8omhZBXx588zQSVaTuUyPxd8tn5HGIqbofexG6xV_wpU-m1DwzanC-9eZa9On_1heZiGjjrRZfW2q-4u5XMCegZ3-FWSb_vFcW2Q-ekVQFZTaKtT8ja--_6YV71R2iJjLA0J91Y1Jnp0SbXNEjmIBvH9TIoHyXY-ErSnUZaRjEhcBVmhOpChRqBrF0r5YpiKtqSi8G8DdMop8R7kiJGLKFoChyCmRyqHE7EB-Km7q6kjBctextaAUtbZwKHDEX',
      tags: ['TRAVEL', 'COFFEE'],
    ),
    _DiscoveryProfile(
      name: 'Min',
      major: 'Computer Sci...',
      year: "'02",
      matchPercent: 88,
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuCZm5OPNQsqWRtn9Q9JRanlA3wGHr2RQpXGWBvXeoJPFMH3ceEkM35k27hOD-SdpW-emSzqFGV1iNHDuvl2-JwD7CohYcY2aC2QMqSvZs2v8obekQXSOa0AJVb9LaO0VT1Gl6rJSMo96FU8_eRYPWNo3_aDOGfEqgjj4W95XZEZIKHfzf_tQda6Qz5X-cE4oBscYXjQeAILJRSjk-xOWqPKxhKKb4_R1kiCzG_BqnVtDKzzdrAYqaJ03uY7RMGrxLqF03aL5KJQgqS_',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: CupertinoColors.white,
      child: Stack(
        children: [
          // 배경 그라데이션
          _BackgroundGradients(),
          // 메인 콘텐츠
          SafeArea(
            child: Column(
              children: [
                // 헤더
                _Header(
                  notificationCount: notificationCount,
                  onAiPreference:
                      onAiPreference ??
                      () => Navigator.of(
                        context,
                        rootNavigator: true,
                      ).pushNamed(RouteNames.aiPreference),
                  onNotification: onNotification,
                ),
                // 메인 콘텐츠
                Expanded(
                  child: _MainContent(
                    profiles: _profiles,
                    remainingMatches: remainingMatches,
                    onSettings: onSettings,
                    onViewProfile: onViewProfile,
                    onSendLike: onSendLike,
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
            child: _FloatingNavBar(onTap: onNavTap),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 배경 그라데이션
// =============================================================================
class _BackgroundGradients extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Positioned(
          top: -100,
          left: -100,
          child: Container(
            width: 400,
            height: 400,
            decoration: BoxDecoration(
              color: const Color(0xFFFBCFE8).withValues(alpha: 0.3),
              shape: BoxShape.circle,
            ),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 100, sigmaY: 100),
              child: const SizedBox(),
            ),
          ),
        ),
        Positioned(
          bottom: -100,
          right: -100,
          child: Container(
            width: 500,
            height: 500,
            decoration: BoxDecoration(
              color: const Color(0xFFE9D5FF).withValues(alpha: 0.3),
              shape: BoxShape.circle,
            ),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 100, sigmaY: 100),
              child: const SizedBox(),
            ),
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final int notificationCount;
  final VoidCallback? onAiPreference;
  final VoidCallback? onNotification;

  const _Header({
    required this.notificationCount,
    this.onAiPreference,
    this.onNotification,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // 로고
          Row(
            children: [
              const Icon(
                CupertinoIcons.heart_fill,
                size: 24,
                color: _AppColors.primary,
              ),
              const SizedBox(width: 8),
              const Text(
                '설레연',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 21,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.3,
                  color: _AppColors.gray900,
                ),
              ),
            ],
          ),
          // 버튼들
          Row(
            children: [
              // AI 취향 버튼
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: onAiPreference,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    color: _AppColors.pink50,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: _AppColors.pink100),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(
                        CupertinoIcons.sparkles,
                        size: 16,
                        color: _AppColors.pink500,
                      ),
                      const SizedBox(width: 6),
                      const Text(
                        'AI에게 내 취향 알려주기',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                          color: _AppColors.gray900,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 12),
              // 알림 버튼
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: onNotification,
                child: Stack(
                  clipBehavior: Clip.none,
                  children: [
                    const Icon(
                      CupertinoIcons.bell,
                      size: 24,
                      color: _AppColors.gray500,
                    ),
                    if (notificationCount > 0)
                      Positioned(
                        top: -4,
                        right: -4,
                        child: Container(
                          width: 16,
                          height: 16,
                          decoration: BoxDecoration(
                            color: _AppColors.primary,
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: CupertinoColors.white,
                              width: 2,
                            ),
                          ),
                          child: Center(
                            child: Text(
                              '$notificationCount',
                              style: const TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 10,
                                fontWeight: FontWeight.w700,
                                color: CupertinoColors.white,
                              ),
                            ),
                          ),
                        ),
                      ),
                  ],
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
// 메인 콘텐츠
// =============================================================================
class _MainContent extends StatelessWidget {
  final List<_DiscoveryProfile> profiles;
  final int remainingMatches;
  final VoidCallback? onSettings;
  final VoidCallback? onViewProfile;
  final VoidCallback? onSendLike;

  const _MainContent({
    required this.profiles,
    required this.remainingMatches,
    this.onSettings,
    this.onViewProfile,
    this.onSendLike,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        children: [
          const SizedBox(height: 16),
          // 타이틀 영역
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: _AppColors.purple100,
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: const Text(
                          'AI CURATED',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 12,
                            fontWeight: FontWeight.w500,
                            color: _AppColors.purple600,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      const Text(
                        'Nov 14',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 12,
                          color: _AppColors.gray400,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    '오늘의 설레연',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 30,
                      fontWeight: FontWeight.w500,
                      letterSpacing: -0.5,
                      color: _AppColors.gray900,
                    ),
                  ),
                ],
              ),
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: onSettings,
                child: const Icon(
                  CupertinoIcons.gear,
                  size: 24,
                  color: _AppColors.gray400,
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          // 프로필 캐러셀
          Expanded(child: _ProfileCarousel(profiles: profiles)),
          const SizedBox(height: 24),
          // 인디케이터
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: const BoxDecoration(
                  color: _AppColors.gray800,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 8),
              Container(
                width: 8,
                height: 8,
                decoration: const BoxDecoration(
                  color: _AppColors.gray300,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 8),
              Container(
                width: 8,
                height: 8,
                decoration: const BoxDecoration(
                  color: _AppColors.gray300,
                  shape: BoxShape.circle,
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          // 버튼들
          Row(
            children: [
              Expanded(
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  onPressed: () {
                    HapticFeedback.lightImpact();
                    onViewProfile?.call();
                  },
                  child: Container(
                    height: 56,
                    decoration: BoxDecoration(
                      color: CupertinoColors.white,
                      borderRadius: BorderRadius.circular(16),
                      boxShadow: [
                        BoxShadow(
                          color: CupertinoColors.black.withValues(alpha: 0.05),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: const Center(
                      child: Text(
                        '프로필 상세',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                          color: _AppColors.gray900,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  onPressed: () {
                    HapticFeedback.mediumImpact();
                    onSendLike?.call();
                  },
                  child: Container(
                    height: 56,
                    decoration: BoxDecoration(
                      color: _AppColors.gray900,
                      borderRadius: BorderRadius.circular(16),
                      boxShadow: [
                        BoxShadow(
                          color: _AppColors.gray900.withValues(alpha: 0.2),
                          blurRadius: 16,
                          offset: const Offset(0, 4),
                        ),
                      ],
                    ),
                    child: const Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          CupertinoIcons.heart_fill,
                          size: 16,
                          color: CupertinoColors.white,
                        ),
                        SizedBox(width: 8),
                        Text(
                          '호감 보내기',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                            color: CupertinoColors.white,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          // 남은 매치 안내
          Text(
            'You have $remainingMatches curated matches remaining today',
            style: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 12,
              fontWeight: FontWeight.w300,
              color: _AppColors.gray400,
            ),
          ),
          const SizedBox(height: 100),
        ],
      ),
    );
  }
}

// =============================================================================
// 프로필 캐러셀
// =============================================================================
class _ProfileCarousel extends StatelessWidget {
  final List<_DiscoveryProfile> profiles;

  const _ProfileCarousel({required this.profiles});

  @override
  Widget build(BuildContext context) {
    final screenWidth = MediaQuery.of(context).size.width;
    final cardWidth = screenWidth * 0.75;

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      physics: const BouncingScrollPhysics(),
      child: Row(
        children: profiles.asMap().entries.map((entry) {
          final index = entry.key;
          final profile = entry.value;
          final isActive = index == 0;

          Widget card = _ProfileCard(
            profile: profile,
            width: cardWidth,
            isActive: isActive,
          );

          // Wrap active card with Hero for transition from mystery card
          if (isActive) {
            card = Hero(tag: 'mystery_card_hero', child: card);
          }

          if (!isActive) {
            card = Transform.scale(
              scale: 0.95,
              child: Opacity(opacity: 0.6, child: card),
            );
          }

          return Padding(
            padding: EdgeInsets.only(
              right: index < profiles.length - 1 ? 16 : 0,
            ),
            child: card,
          );
        }).toList(),
      ),
    );
  }
}

class _ProfileCard extends StatelessWidget {
  final _DiscoveryProfile profile;
  final double width;
  final bool isActive;

  const _ProfileCard({
    required this.profile,
    required this.width,
    required this.isActive,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: width * 1.33,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        boxShadow: isActive
            ? [
                BoxShadow(
                  color: CupertinoColors.black.withValues(alpha: 0.08),
                  blurRadius: 40,
                  offset: const Offset(0, 10),
                ),
              ]
            : null,
      ),
      clipBehavior: Clip.antiAlias,
      child: Stack(
        fit: StackFit.expand,
        children: [
          // 이미지
          Image.network(
            profile.imageUrl,
            fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => Container(color: _AppColors.gray200),
          ),
          // 그라데이션 오버레이
          Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  CupertinoColors.black.withValues(alpha: 0),
                  CupertinoColors.black.withValues(alpha: 0.2),
                  CupertinoColors.black.withValues(alpha: 0.8),
                ],
                stops: const [0.0, 0.5, 1.0],
              ),
            ),
          ),
          // 콘텐츠
          Positioned(
            left: 24,
            right: 24,
            bottom: 24,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // 이름 & 매치
                Row(
                  children: [
                    Text(
                      profile.name,
                      style: const TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 30,
                        fontWeight: FontWeight.w600,
                        color: CupertinoColors.white,
                      ),
                    ),
                    if (profile.matchPercent > 0) ...[
                      const SizedBox(width: 12),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: BackdropFilter(
                          filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 4,
                            ),
                            decoration: BoxDecoration(
                              color: CupertinoColors.white.withValues(
                                alpha: 0.2,
                              ),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(
                                color: CupertinoColors.white.withValues(
                                  alpha: 0.1,
                                ),
                              ),
                            ),
                            child: Text(
                              '${profile.matchPercent}% Match',
                              style: const TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 12,
                                fontWeight: FontWeight.w500,
                                color: CupertinoColors.white,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 4),
                // 전공 & 년도
                Text(
                  '${profile.major} • ${profile.year}',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 14,
                    fontWeight: FontWeight.w300,
                    color: CupertinoColors.white.withValues(alpha: 0.8),
                  ),
                ),
                // 태그
                if (profile.tags.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: profile.tags.map((tag) {
                      return ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: BackdropFilter(
                          filter: ImageFilter.blur(sigmaX: 4, sigmaY: 4),
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 6,
                            ),
                            decoration: BoxDecoration(
                              color: CupertinoColors.black.withValues(
                                alpha: 0.4,
                              ),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(
                                color: CupertinoColors.white.withValues(
                                  alpha: 0.1,
                                ),
                              ),
                            ),
                            child: Text(
                              tag,
                              style: const TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 12,
                                fontWeight: FontWeight.w500,
                                color: CupertinoColors.white,
                              ),
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 플로팅 네비게이션
// =============================================================================
class _FloatingNavBar extends StatelessWidget {
  final Function(int index)? onTap;

  const _FloatingNavBar({this.onTap});

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(32),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 24),
          decoration: BoxDecoration(
            color: CupertinoColors.white.withValues(alpha: 0.95),
            borderRadius: BorderRadius.circular(32),
            border: Border.all(color: _AppColors.gray100),
            boxShadow: [
              BoxShadow(
                color: CupertinoColors.black.withValues(alpha: 0.05),
                blurRadius: 20,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _NavItem(
                icon: CupertinoIcons.heart_fill,
                label: '설레연',
                isActive: true,
                onTap: () => onTap?.call(0),
              ),
              _NavItem(
                icon: CupertinoIcons.chat_bubble,
                label: '채팅',
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
  final VoidCallback? onTap;

  const _NavItem({
    required this.icon,
    required this.label,
    this.isActive = false,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: SizedBox(
        width: 48,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              size: 24,
              color: isActive ? _AppColors.primary : _AppColors.gray400,
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 10,
                fontWeight: isActive ? FontWeight.w600 : FontWeight.w500,
                color: isActive ? _AppColors.primary : _AppColors.gray400,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
