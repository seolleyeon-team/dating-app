// =============================================================================
// 이벤트 탭 홈 화면 (3:3 시즌 미팅)
// 경로: lib/features/event/screens/event_screen.dart
//
// 사용 예시 (main.dart):
// import 'package:seolleyeon/features/event/screens/event_screen.dart';
// ...
// home: const EventScreen(),
// =============================================================================

import 'dart:ui';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import '../../chat/services/chat_service.dart';
import '../../../router/route_names.dart';
import '../../../services/event_team_service.dart';
import '../../../services/storage_service.dart';
import '../widgets/pending_team_invite_card.dart';
import '../widgets/team_invite_response_sheet.dart';
import 'package:flutter/material.dart';
import '../../../core/constants/app_colors.dart';
import '../../../shared/widgets/seolleyeon_bottom_navigation_bar.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color backgroundLight = Color(0xFFFFF5F8);
  static const Color border = Color(0xFFE6DBDE);
}

// =============================================================================
// 메인 화면
// =============================================================================
class EventScreen extends StatefulWidget {
  final Function(int index)? onNavTap;

  const EventScreen({super.key, this.onNavTap});

  @override
  State<EventScreen> createState() => _EventScreenState();
}

class _EventScreenState extends State<EventScreen> {
  int _selectedTabIndex = 0;
  final StorageService _storageService = StorageService();
  final ChatService _chatService = ChatService();
  final EventTeamService _eventTeamService = EventTeamService();
  String? _currentUserId;

  /// "나중에 보기" 눌렀을 때 세션 내 일시 dismiss
  String? _dismissedInviteId;

  @override
  void initState() {
    super.initState();
    _loadCurrentUser();
  }

  Future<void> _loadCurrentUser() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (!mounted) return;
    setState(() => _currentUserId = kakaoUserId);
  }

  void _onTabChanged(int index) {
    setState(() => _selectedTabIndex = index);
    HapticFeedback.selectionClick();
  }

  void _onStartPressed() {
    HapticFeedback.mediumImpact();
    Navigator.of(context, rootNavigator: true).pushNamed(RouteNames.teamSetup);
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;
    final handleBack = widget.onNavTap != null
        ? () => widget.onNavTap!.call(0)
        : () => Navigator.of(context).pop();

    return CupertinoPageScaffold(
      backgroundColor: Theme.of(context).brightness == Brightness.dark
          ? AppColorsDark.background
          : _AppColors.backgroundLight,
      child: Stack(
        children: [
          // 메인 콘텐츠
          Column(
            children: [
              // 상단 앱 바
              _TopAppBar(onBackPressed: handleBack),
              // Pending 팀 초대 배너 — 이벤트 탭 전체(세그먼트 무관)에서 표시
              if (_currentUserId != null && _currentUserId!.isNotEmpty)
                StreamBuilder<List<EventTeamInviteDoc>>(
                  stream: _eventTeamService.watchPendingInvitesForUser(
                    _currentUserId!,
                  ),
                  builder: (context, invSnap) {
                    if (invSnap.hasError) {
                      return const SizedBox.shrink();
                    }
                    final invites = invSnap.data ?? [];
                    if (invites.isEmpty) {
                      return const SizedBox.shrink();
                    }
                    final visibleInvite = invites.first;
                    if (_dismissedInviteId == visibleInvite.inviteId) {
                      return const SizedBox.shrink();
                    }
                    return PendingTeamInviteCard(
                      pendingInvites: invites,
                      onDismiss: () {
                        HapticFeedback.lightImpact();
                        setState(
                          () => _dismissedInviteId = visibleInvite.inviteId,
                        );
                      },
                      onConfirm: () {
                        HapticFeedback.mediumImpact();
                        showTeamInviteResponseSheet(
                          context,
                          invite: visibleInvite,
                        );
                      },
                    );
                  },
                ),
              // 세그먼트 컨트롤
              _SegmentedControl(
                selectedIndex: _selectedTabIndex,
                onChanged: _onTabChanged,
              ),
              // 스크롤 영역
              Expanded(
                child: _selectedTabIndex == 0
                    ? SingleChildScrollView(
                        physics: const BouncingScrollPhysics(),
                        padding: const EdgeInsets.fromLTRB(0, 16, 0, 120),
                        child: Column(
                          children: [
                            // ━━━ 기존 콘텐츠 ━━━
                            Padding(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 16,
                              ),
                              child: Column(
                                children: [
                                  // 히어로 카드 (슬롯머신)
                                  const _HeroCard(),
                                  const SizedBox(height: 16),
                                  // 상태 표시줄
                                  const _StatusStrip(),
                                  const SizedBox(height: 16),
                                  // CTA 버튼
                                  _PrimaryCTA(onPressed: _onStartPressed),
                                  const SizedBox(height: 24),
                                  // 구분선
                                  const _Divider(),
                                  const SizedBox(height: 24),
                                  // 제휴 장소 섹션
                                  const _PartnerVenueSection(),
                                ],
                              ),
                            ),
                          ],
                        ),
                      )
                    : const _RandomMatchingContent(),
              ),
            ],
          ),
          // 하단 네비게이션
          if (_currentUserId == null || _currentUserId!.isEmpty)
            SeolleyeonBottomNavPositioned(
              currentTab: BottomNavTab.event,
              onTap: widget.onNavTap,
              showChatBadge: false,
            )
          else
            StreamBuilder<bool>(
              stream: _chatService.hasAnyUnreadChats(_currentUserId!),
              builder: (context, snapshot) {
                final hasUnread = snapshot.data == true;
                return SeolleyeonBottomNavPositioned(
                  currentTab: BottomNavTab.event,
                  onTap: widget.onNavTap,
                  showChatBadge: hasUnread,
                );
              },
            ),
        ],
      ),
    );
  }
}

// =============================================================================
// 상단 앱 바
// =============================================================================
class _TopAppBar extends StatelessWidget {
  final VoidCallback onBackPressed;

  const _TopAppBar({required this.onBackPressed});

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final textColor = seol.gray800;

    return SafeArea(
      bottom: false,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Row(
          children: [
            CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: const Size(48, 48),
              onPressed: onBackPressed,
              child: Icon(CupertinoIcons.back, color: textColor, size: 24),
            ),
            Expanded(
              child: Text(
                'Event',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: textColor,
                  letterSpacing: -0.3,
                ),
              ),
            ),
            const SizedBox(width: 48),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 세그먼트 컨트롤
// =============================================================================
class _SegmentedControl extends StatelessWidget {
  final int selectedIndex;
  final ValueChanged<int> onChanged;

  const _SegmentedControl({
    required this.selectedIndex,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Container(
        height: 48,
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(
          color: seol.gray100,
          borderRadius: BorderRadius.circular(24),
        ),
        child: Row(
          children: [
            _SegmentTab(
              label: '3:3 시즌 미팅',
              isSelected: selectedIndex == 0,
              onTap: () => onChanged(0),
            ),
            _SegmentTab(
              label: '기타 이벤트',
              isSelected: selectedIndex == 1,
              onTap: () => onChanged(1),
            ),
          ],
        ),
      ),
    );
  }
}

class _SegmentTab extends StatelessWidget {
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  const _SegmentTab({
    required this.label,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final primary = Theme.of(context).colorScheme.primary;

    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          decoration: BoxDecoration(
            color: isSelected ? seol.cardSurface : Colors.transparent,
            borderRadius: BorderRadius.circular(20),
            boxShadow: isSelected
                ? [
                    BoxShadow(
                      color: CupertinoColors.black.withValues(alpha: 0.06),
                      blurRadius: 4,
                      offset: const Offset(0, 2),
                    ),
                  ]
                : [],
          ),
          child: Center(
            child: Text(
              label,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 14,
                fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                color: isSelected ? primary : seol.sectionTitle,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 히어로 카드 (슬롯머신)
// =============================================================================
class _HeroCard extends StatelessWidget {
  const _HeroCard();

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final primary = Theme.of(context).colorScheme.primary;

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: seol.cardSurface,
        borderRadius: BorderRadius.circular(32),
        boxShadow: [
          BoxShadow(
            color: primary.withValues(alpha: 0.12),
            blurRadius: 30,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        children: [
          // Safe Matching 배지
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: primary.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: primary.withValues(alpha: 0.1)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(CupertinoIcons.shield_fill, size: 14, color: primary),
                const SizedBox(width: 4),
                Text(
                  'SAFE MATCHING',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.8,
                    color: primary,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          // 타이틀
          Text(
            '두근두근 3:3 시즌 미팅',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 22,
              fontWeight: FontWeight.w700,
              color: seol.gray800,
              letterSpacing: -0.3,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            '검증된 회원들과 안전하고 설레는 만남',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: seol.sectionTitle,
            ),
          ),
          const SizedBox(height: 28),
          // 슬롯머신 비주얼
          const _SlotMachineVisual(),
        ],
      ),
    );
  }
}

// =============================================================================
// 슬롯머신 비주얼
// =============================================================================
class _SlotMachineVisual extends StatelessWidget {
  const _SlotMachineVisual();

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final primary = Theme.of(context).colorScheme.primary;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: seol.pink50,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: primary.withValues(alpha: 0.05)),
      ),
      child: Stack(
        alignment: Alignment.center,
        children: [
          // 가로 라인
          Container(
            height: 2,
            margin: const EdgeInsets.symmetric(horizontal: 24),
            decoration: BoxDecoration(
              color: primary.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(1),
            ),
          ),
          // 슬롯 릴
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _SlotReel(isActive: false),
              const SizedBox(width: 12),
              _SlotReel(isActive: true),
              const SizedBox(width: 12),
              _SlotReel(isActive: false),
            ],
          ),
        ],
      ),
    );
  }
}

class _SlotReel extends StatelessWidget {
  final bool isActive;

  const _SlotReel({required this.isActive});

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final primary = Theme.of(context).colorScheme.primary;

    return Transform.scale(
      scale: isActive ? 1.1 : 1.0,
      child: Container(
        width: 64,
        height: 80,
        decoration: BoxDecoration(
          color: seol.cardSurface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isActive ? primary.withValues(alpha: 0.3) : seol.gray200,
            width: isActive ? 2 : 1,
          ),
          boxShadow: isActive
              ? [
                  BoxShadow(
                    color: primary.withValues(alpha: 0.2),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ]
              : [
                  BoxShadow(
                    color: CupertinoColors.black.withValues(alpha: 0.04),
                    blurRadius: 4,
                    offset: const Offset(0, 2),
                  ),
                ],
        ),
        child: Center(
          child: Icon(
            CupertinoIcons.heart_fill,
            size: 36,
            color: isActive ? primary : seol.gray300,
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 상태 표시줄
// =============================================================================
class _StatusStrip extends StatelessWidget {
  const _StatusStrip();

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final primary = Theme.of(context).colorScheme.primary;
    final borderColor = Theme.of(context).brightness == Brightness.dark
        ? AppColorsDark.border
        : _AppColors.border;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      decoration: BoxDecoration(
        color: seol.cardSurface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: borderColor.withValues(alpha: 0.5)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(CupertinoIcons.tickets_fill, size: 16, color: primary),
                    const SizedBox(width: 6),
                    Text(
                      '오늘 1회 무료',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: seol.gray800,
                      ),
                    ),
                  ],
                ),
                Padding(
                  padding: const EdgeInsets.only(left: 22, top: 2),
                  child: Text(
                    '추가 돌리기 3,000원',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 12,
                      fontWeight: FontWeight.w400,
                      color: seol.sectionTitle,
                    ),
                  ),
                ),
              ],
            ),
          ),
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: seol.gray100,
              borderRadius: BorderRadius.circular(16),
            ),
            child: Icon(CupertinoIcons.refresh, size: 18, color: primary),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// CTA 버튼
// =============================================================================
class _PrimaryCTA extends StatelessWidget {
  final VoidCallback onPressed;

  const _PrimaryCTA({required this.onPressed});

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onPressed,
      child: Container(
        width: double.infinity,
        height: 56,
        decoration: BoxDecoration(
          color: primary,
          borderRadius: BorderRadius.circular(28),
          boxShadow: [
            BoxShadow(
              color: primary.withValues(alpha: 0.35),
              blurRadius: 16,
              offset: const Offset(0, 6),
            ),
          ],
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(
              CupertinoIcons.person_3_fill,
              size: 20,
              color: CupertinoColors.white,
            ),
            const SizedBox(width: 8),
            const Text(
              '팀 만들고 시작하기',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 17,
                fontWeight: FontWeight.w700,
                color: CupertinoColors.white,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 구분선
// =============================================================================
class _Divider extends StatelessWidget {
  const _Divider();

  @override
  Widget build(BuildContext context) {
    final borderColor = Theme.of(context).brightness == Brightness.dark
        ? AppColorsDark.border
        : _AppColors.border;

    return Container(
      height: 1,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [Colors.transparent, borderColor, Colors.transparent],
        ),
      ),
    );
  }
}

// =============================================================================
// 제휴 장소 섹션
// =============================================================================
class _PartnerVenueSection extends StatelessWidget {
  const _PartnerVenueSection();

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 헤더
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                '제휴 장소 추천',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: seol.gray800,
                ),
              ),
              CupertinoButton(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                minimumSize: Size.zero,
                onPressed: () {},
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    color: seol.cardSurface,
                    borderRadius: BorderRadius.circular(8),
                    boxShadow: [
                      BoxShadow(
                        color: CupertinoColors.black.withValues(alpha: 0.04),
                        blurRadius: 4,
                      ),
                    ],
                  ),
                  child: Text(
                    '전체보기',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: seol.sectionTitle,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        // 장소 카드
        const _VenueCard(
          name: '강남 라운지 X',
          location: '강남',
          description: '프라이빗한 공간에서 즐기는 3:3 미팅. 웰컴 드링크 1잔 무료.',
          imageUrl:
              'https://lh3.googleusercontent.com/aida-public/AB6AXuBtvmev_6t45GCM8ifRK7JHB3Jts49eSYRaVG98Kr63pP1YJOAHd6hzyQW-fd-XFdQcYVQA1CK7K7teKt3nS2_Qtcaarb1EIOL6vWnPo2rq8escNrPvD9OXf3-YCBzIPalNb4wTFtAXzz8QJZbIQBLEg-TJ3VsrUo1kMw_CI-9l5UwfK5wZQzzmFPYnoz4wibIvDZJWMKqDYA4oXmw4KX3bIdHZJP6FWzYk0QTEOBcq7RH0INHTIjQKn_YVwO8SCzN6OWUluydMjsI',
        ),
      ],
    );
  }
}

// =============================================================================
// 장소 카드
// =============================================================================
class _VenueCard extends StatelessWidget {
  final String name;
  final String location;
  final String description;
  final String imageUrl;

  const _VenueCard({
    required this.name,
    required this.location,
    required this.description,
    required this.imageUrl,
  });

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final primary = Theme.of(context).colorScheme.primary;
    final borderColor = Theme.of(context).brightness == Brightness.dark
        ? AppColorsDark.border
        : _AppColors.border;

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: seol.cardSurface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: borderColor.withValues(alpha: 0.6)),
      ),
      child: Row(
        children: [
          // 이미지
          ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: Stack(
              children: [
                Container(
                  width: 88,
                  height: 88,
                  color: const Color(0xFFE2E8F0),
                  child: Image.network(
                    imageUrl,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => const Center(
                      child: Icon(
                        CupertinoIcons.photo,
                        size: 32,
                        color: Color(0xFF94A3B8),
                      ),
                    ),
                  ),
                ),
                // 위치 배지
                Positioned(
                  top: 4,
                  left: 4,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 6,
                      vertical: 2,
                    ),
                    decoration: BoxDecoration(
                      color: CupertinoColors.black.withValues(alpha: 0.6),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(
                          CupertinoIcons.location_solid,
                          size: 10,
                          color: CupertinoColors.white,
                        ),
                        const SizedBox(width: 2),
                        Text(
                          location,
                          style: const TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 9,
                            fontWeight: FontWeight.w500,
                            color: CupertinoColors.white,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 16),
          // 정보
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                    color: seol.gray800,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  description,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    fontWeight: FontWeight.w400,
                    color: seol.sectionTitle,
                    height: 1.4,
                  ),
                ),
                const SizedBox(height: 8),
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  onPressed: () {},
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: primary.withValues(alpha: 0.05),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          '혜택 보기',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: primary,
                          ),
                        ),
                        Icon(
                          CupertinoIcons.chevron_right,
                          size: 12,
                          color: primary,
                        ),
                      ],
                    ),
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

// =============================================================================
// 랜덤 매칭 콘텐츠 (기타 이벤트 탭)
// =============================================================================
class _RandomMatchingContent extends StatelessWidget {
  const _RandomMatchingContent();

  @override
  Widget build(BuildContext context) {
    final seol = Theme.of(context).extension<SeolThemeColors>()!;
    final primary = Theme.of(context).colorScheme.primary;

    return SingleChildScrollView(
      physics: const BouncingScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 120),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 랜덤 매칭 카드
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: seol.cardSurface,
              borderRadius: BorderRadius.circular(32),
              boxShadow: [
                BoxShadow(
                  color: primary.withValues(alpha: 0.12),
                  blurRadius: 30,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            child: Column(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    color: primary.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(CupertinoIcons.shuffle, size: 14, color: primary),
                      const SizedBox(width: 4),
                      Text(
                        'RANDOM MATCHING',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0.8,
                          color: primary,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  '3:3 랜덤 매칭',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                    color: seol.gray800,
                    letterSpacing: -0.3,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '같은 관심사를 가진 분들과 무작위로 매칭됩니다.',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: seol.sectionTitle,
                  ),
                ),
                const SizedBox(height: 28),
                // 매칭 비주얼
                Container(
                  padding: const EdgeInsets.all(24),
                  decoration: BoxDecoration(
                    color: seol.pink50,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: primary.withValues(alpha: 0.05)),
                  ),
                  child: Icon(
                    CupertinoIcons.person_2_fill,
                    size: 48,
                    color: primary.withValues(alpha: 0.8),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          // CTA 버튼
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: () {
              HapticFeedback.mediumImpact();
              Navigator.of(
                context,
                rootNavigator: true,
              ).pushNamed(RouteNames.randomMatching);
            },
            child: Container(
              width: double.infinity,
              height: 56,
              decoration: BoxDecoration(
                color: primary,
                borderRadius: BorderRadius.circular(28),
                boxShadow: [
                  BoxShadow(
                    color: primary.withValues(alpha: 0.35),
                    blurRadius: 16,
                    offset: const Offset(0, 6),
                  ),
                ],
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(
                    CupertinoIcons.shuffle,
                    size: 20,
                    color: CupertinoColors.white,
                  ),
                  const SizedBox(width: 8),
                  const Text(
                    'Start matching',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                      color: CupertinoColors.white,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

