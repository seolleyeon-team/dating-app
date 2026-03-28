// =============================================================================
// 내가 보낸 호감 목록 화면
// 경로: lib/features/profile/screens/sent_hearts_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const SentHeartsScreen()),
// );
// =============================================================================

import 'dart:ui';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFEC3C68);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textPrimary = Color(0xFF1B0E11);
  static const Color textSecondary = Color(0xFF994D60);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color gray300 = Color(0xFFD1D5DB);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray500 = Color(0xFF6B7280);
}

// =============================================================================
// 프로필 모델
// =============================================================================
class _SentHeartProfile {
  final String id;
  final String name;
  final String imageUrl;
  final String department;
  final int age;
  final List<String> tags;
  final String date;
  final bool isNew;
  final bool isOld;

  const _SentHeartProfile({
    required this.id,
    required this.name,
    required this.imageUrl,
    required this.department,
    required this.age,
    required this.tags,
    required this.date,
    this.isNew = false,
    this.isOld = false,
  });
}

// =============================================================================
// 메인 화면
// =============================================================================
class SentHeartsScreen extends StatelessWidget {
  final VoidCallback? onBack;
  final VoidCallback? onFilter;
  final Function(String profileId)? onProfileTap;
  final Function(int navIndex)? onNavTap;

  const SentHeartsScreen({
    super.key,
    this.onBack,
    this.onFilter,
    this.onProfileTap,
    this.onNavTap,
  });

  static const List<_SentHeartProfile> _profiles = [
    _SentHeartProfile(
      id: '1',
      name: '민서',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuB01NVcGnmx0p3QRi4cO-sjcCeUVSZNcPH19qreL2uvpX83xhk97PvwUwJ5O7mBu-MYqs4gQrtdMETWXSrdT2a-6xF3LO5w3V7qPlNULCTmMuIUVK84Fd8VKDrqTDy4thMHcQXK0GRrpARXhCB2-62Wly4Q-IhF4RTbNj1hYME4A8lqGT-JuG0zTbyiGg33iIWhvSC1mbyrf9uSJrNfNozULNFXBcHj6DA2aGKIdTkG9glXL4oByppoGa0g_jWOPvSrHbprjgvww0dp',
      department: '건축학과',
      age: 24,
      tags: ['#사진', '#와인', '#감성카페'],
      date: '3월 5일',
      isNew: true,
    ),
    _SentHeartProfile(
      id: '2',
      name: '지안',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuDjy7VJPvI6Ptr-agtqCxOopkqKQaDn6-NJ99y8AuhtGYNPbrSJ5eUHV--GKxiNX9biFpB77mk8WI6R0yoKi1wgCfGSbO_K6YDWAssAY9Anq8kCY81tdfQXS-6Acsoz01GpLxsNZGzfxgE96ChBM6L8dDJZRBRzesDa9Hr-H-LPWgaQHzhtAPn3YeANa65W_1AGQFqdaNJXgaQ05pVizF8BDK_yAcnO_KALK5JToW4FSK7EpbTHt3qRuzVl1fEfVQmAYFg1VUSvwm5U',
      department: '시각디자인',
      age: 23,
      tags: ['#전시회', '#베이킹'],
      date: '3월 4일',
    ),
    _SentHeartProfile(
      id: '3',
      name: '서준',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuAUM9BjJS9QZdQnaMZ3Anf4rblS81gVXBFYZ6U3RaTim6YmgF3rwfG8oxrMssqJ6X1cQQ80kw_GHVshY1nvU22E8eI2bglD1lvhdCAXUAkmYFz3JAjR4tqfCN9R3x6Mo-pi39A0khd_nwW_3qatnYI_5i-Yfpnlfh6Tce5RlXVZxN10DBEx1fAuLYZ8r8Jue_1oeMksJTwpvrVDgxbc8kLIlGA9tRo_Q3I5SzXxyLp97JeGkfRHAAM-NgY3AdZqDRel0hlLU1YLdYtF',
      department: '컴퓨터공학',
      age: 25,
      tags: ['#코딩', '#게임', '#드라이브'],
      date: '3월 3일',
    ),
    _SentHeartProfile(
      id: '4',
      name: '유진',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuBlmoYjM7uj_XwCaIm6QtFxjDlPA_FmXCq_1EHCS9w492RtWFGaBYCW5ZVKVQATnd05aK94qQwGopAg3BeElbneEA8yyB3hBSA4nwt56tvVuJj9yng4eIdcY0zJBVSOUFp3l6HWvJ00CNKMveLgxpQXZ801TAu0c5EMBDealyzsmszEWuElfeF9v7Uua9RTjpHFK61QWW6i2Qc6C-LdZWmy3b8il6eTbtpcTUXW4lQ5R3JB3nkJTEiQsZlq3ZKK5jQfphVTtnwylVG4',
      department: '경영학과',
      age: 22,
      tags: ['#맛집탐방', '#여행'],
      date: '2월 28일',
      isOld: true,
    ),
    _SentHeartProfile(
      id: '5',
      name: '민호',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuCdsxCS0JD-Ib3HmjAuXSHms9qf3gtyvLYYlY7uA2VS6P4K6Ey0hDw2M5WDcVBiE6iv1EtbDZ-ic-EIUaXHg90mwp9eS4-czMajn2KPQfB7JzayMh1jL4MKPHz8kqr7pXFys4Hj4lbBJxDwa6JV7T6YV56dFpdSNm_1dm99Fp2z5OUjLKw_Uo5v6NjU1V48XXC0ESXC-ImXWVDfD5Z6UXkRsluH28kpyi6m4cKHigkm96mTOBAXn5BlMOPA-cdhbhNAIZ7s0sjls_V1',
      department: '체육교육과',
      age: 26,
      tags: ['#운동', '#축구'],
      date: '2월 15일',
    ),
  ];

  /// 이전 내역 구분선 앞에 있는 프로필 수 (유진까지)
  static const int _recentCount = 4;

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          // 배경 글로우
          Positioned(
            top: -60,
            left: 0,
            right: 0,
            child: Center(
              child: Container(
                width: MediaQuery.of(context).size.width * 1.4,
                height: 300,
                decoration: BoxDecoration(
                  gradient: RadialGradient(
                    colors: [
                      _AppColors.primary.withValues(alpha: 0.06),
                      _AppColors.primary.withValues(alpha: 0),
                    ],
                  ),
                ),
              ),
            ),
          ),
          // 메인 콘텐츠
          CustomScrollView(
            physics: const BouncingScrollPhysics(),
            slivers: [
              // 헤더
              SliverToBoxAdapter(
                child: _Header(onBack: onBack, onFilter: onFilter),
              ),
              // 리스트 아이템들 (이전 내역 구분선 전)
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                sliver: SliverList(
                  delegate: SliverChildBuilderDelegate(
                    (context, index) => Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: _ProfileListItem(
                        profile: _profiles[index],
                        onTap: () => onProfileTap?.call(_profiles[index].id),
                      ),
                    ),
                    childCount: _recentCount,
                  ),
                ),
              ),
              // 이전 내역 구분선
              const SliverToBoxAdapter(child: _SectionDivider(text: '이전 내역')),
              // 이전 내역 리스트 아이템들
              SliverPadding(
                padding: EdgeInsets.fromLTRB(16, 0, 16, bottomPadding + 120),
                sliver: SliverList(
                  delegate: SliverChildBuilderDelegate((context, index) {
                    final i = _recentCount + index;
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: _ProfileListItem(
                        profile: _profiles[i],
                        onTap: () => onProfileTap?.call(_profiles[i].id),
                      ),
                    );
                  }, childCount: _profiles.length - _recentCount),
                ),
              ),
            ],
          ),
          // 하단 그라데이션
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            height: 96,
            child: IgnorePointer(
              child: Container(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      _AppColors.backgroundLight.withValues(alpha: 0),
                      _AppColors.backgroundLight,
                    ],
                  ),
                ),
              ),
            ),
          ),
          // 하단 네비게이션
          Positioned(
            left: 24,
            right: 24,
            bottom: bottomPadding + 32,
            child: _FloatingNavBar(onTap: onNavTap),
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
  final VoidCallback? onBack;
  final VoidCallback? onFilter;

  const _Header({this.onBack, this.onFilter});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      bottom: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        decoration: BoxDecoration(
          color: _AppColors.backgroundLight.withValues(alpha: 0.95),
          border: Border(
            bottom: BorderSide(
              color: _AppColors.primary.withValues(alpha: 0.05),
            ),
          ),
        ),
        child: Stack(
          alignment: Alignment.center,
          children: [
            // 뒤로가기
            Align(
              alignment: Alignment.centerLeft,
              child: CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: () {
                  HapticFeedback.lightImpact();
                  if (onBack != null) {
                    onBack!();
                  } else {
                    Navigator.of(context).pop();
                  }
                },
                child: Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: CupertinoColors.black.withValues(alpha: 0.05),
                  ),
                  child: const Icon(
                    CupertinoIcons.back,
                    size: 20,
                    color: _AppColors.textPrimary,
                  ),
                ),
              ),
            ),
            // 타이틀
            const Text(
              '내가 보낸 호감',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: _AppColors.textPrimary,
              ),
            ),
            // 필터
            Align(
              alignment: Alignment.centerRight,
              child: CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: () {
                  HapticFeedback.lightImpact();
                  onFilter?.call();
                },
                child: Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: CupertinoColors.black.withValues(alpha: 0.05),
                  ),
                  child: const Icon(
                    CupertinoIcons.slider_horizontal_3,
                    size: 20,
                    color: _AppColors.textPrimary,
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
// 프로필 리스트 아이템
// =============================================================================
class _ProfileListItem extends StatelessWidget {
  final _SentHeartProfile profile;
  final VoidCallback? onTap;

  const _ProfileListItem({required this.profile, this.onTap});

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () {
        HapticFeedback.selectionClick();
        onTap?.call();
      },
      child: Opacity(
        opacity: profile.isOld ? 0.7 : 1.0,
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: _AppColors.surfaceLight,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: CupertinoColors.black.withValues(alpha: 0.03),
                blurRadius: 10,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Row(
            children: [
              // 프로필 이미지
              _ProfileAvatar(
                imageUrl: profile.imageUrl,
                isNew: profile.isNew,
                isOld: profile.isOld,
              ),
              const SizedBox(width: 16),
              // 콘텐츠
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    // 이름 + 날짜
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Flexible(
                          child: Text(
                            profile.name,
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                              color: profile.isOld
                                  ? _AppColors.gray500
                                  : _AppColors.textPrimary,
                            ),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        const SizedBox(width: 8),
                        _DateBadge(date: profile.date, isNew: profile.isNew),
                      ],
                    ),
                    const SizedBox(height: 4),
                    // 학과 + 나이
                    Text(
                      '${profile.department} • ${profile.age}세',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 12,
                        color: profile.isOld
                            ? _AppColors.gray400
                            : _AppColors.textSecondary,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 8),
                    // 태그
                    _TagRow(tags: profile.tags, isOld: profile.isOld),
                  ],
                ),
              ),
              const SizedBox(width: 4),
              // 화살표
              Icon(
                CupertinoIcons.chevron_right,
                size: 20,
                color: profile.isOld ? _AppColors.gray200 : _AppColors.gray300,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 프로필 아바타
// =============================================================================
class _ProfileAvatar extends StatelessWidget {
  final String imageUrl;
  final bool isNew;
  final bool isOld;

  const _ProfileAvatar({
    required this.imageUrl,
    this.isNew = false,
    this.isOld = false,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 80,
      height: 80,
      child: Stack(
        children: [
          // 이미지
          Container(
            width: 80,
            height: 80,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(
                color: isOld
                    ? _AppColors.gray200
                    : _AppColors.primary.withValues(alpha: 0.1),
                width: 2,
              ),
            ),
            clipBehavior: Clip.antiAlias,
            child: isOld
                ? ColorFiltered(
                    colorFilter: const ColorFilter.mode(
                      CupertinoColors.systemGrey,
                      BlendMode.saturation,
                    ),
                    child: Stack(
                      children: [
                        Positioned.fill(
                          child: Image.network(imageUrl, fit: BoxFit.cover),
                        ),
                        // 읽음/이전 오버레이
                        Positioned.fill(
                          child: Container(
                            decoration: BoxDecoration(
                              color: CupertinoColors.white.withValues(
                                alpha: 0.3,
                              ),
                              shape: BoxShape.circle,
                            ),
                          ),
                        ),
                      ],
                    ),
                  )
                : Image.network(imageUrl, fit: BoxFit.cover),
          ),
          // NEW 배지
          if (isNew)
            Positioned(
              bottom: 0,
              right: 0,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: _AppColors.primary,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: CupertinoColors.white, width: 1.5),
                  boxShadow: [
                    BoxShadow(
                      color: _AppColors.primary.withValues(alpha: 0.3),
                      blurRadius: 4,
                    ),
                  ],
                ),
                child: const Text(
                  'NEW',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    color: CupertinoColors.white,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

// =============================================================================
// 날짜 배지
// =============================================================================
class _DateBadge extends StatelessWidget {
  final String date;
  final bool isNew;

  const _DateBadge({required this.date, this.isNew = false});

  @override
  Widget build(BuildContext context) {
    if (isNew) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: _AppColors.primary.withValues(alpha: 0.05),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Text(
          date,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 12,
            fontWeight: FontWeight.w500,
            color: _AppColors.primary.withValues(alpha: 0.8),
          ),
        ),
      );
    }
    return Text(
      date,
      style: const TextStyle(
        fontFamily: 'Pretendard',
        fontSize: 12,
        fontWeight: FontWeight.w500,
        color: _AppColors.gray400,
      ),
    );
  }
}

// =============================================================================
// 태그 Row
// =============================================================================
class _TagRow extends StatelessWidget {
  final List<String> tags;
  final bool isOld;

  const _TagRow({required this.tags, this.isOld = false});

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 6,
      runSpacing: 4,
      children: tags.map((tag) {
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            color: isOld
                ? _AppColors.gray100.withValues(alpha: 0.5)
                : _AppColors.primary.withValues(alpha: 0.05),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Text(
            tag,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 10,
              fontWeight: FontWeight.w500,
              color: isOld ? _AppColors.gray400 : _AppColors.primary,
            ),
          ),
        );
      }).toList(),
    );
  }
}

// =============================================================================
// 섹션 구분선
// =============================================================================
class _SectionDivider extends StatelessWidget {
  final String text;

  const _SectionDivider({required this.text});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
      child: Row(
        children: [
          Expanded(child: Container(height: 1, color: _AppColors.gray200)),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Text(
              text,
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 12,
                fontWeight: FontWeight.w500,
                color: _AppColors.gray400,
              ),
            ),
          ),
          Expanded(child: Container(height: 1, color: _AppColors.gray200)),
        ],
      ),
    );
  }
}

// =============================================================================
// 하단 플로팅 네비게이션
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
                icon: CupertinoIcons.heart,
                label: '설레연',
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

// =============================================================================
// 네비게이션 아이템
// =============================================================================
class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback? onTap;

  const _NavItem({required this.icon, required this.label, this.onTap});

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 24, color: _AppColors.gray400),
          const SizedBox(height: 4),
          Text(
            label,
            style: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 10,
              fontWeight: FontWeight.w500,
              letterSpacing: -0.2,
              color: _AppColors.gray400,
            ),
          ),
        ],
      ),
    );
  }
}
