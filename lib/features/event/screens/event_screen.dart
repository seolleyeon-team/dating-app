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

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF0426E);
  static const Color backgroundLight = Color(0xFFFFF5F8);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color textSecondary = Color(0xFF89616B);
  static const Color chipBg = Color(0xFFEDE8E9);
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
      backgroundColor: _AppColors.backgroundLight,
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
          Positioned(
            left: 24,
            right: 24,
            bottom: bottomPadding + 32,
            child: (_currentUserId == null || _currentUserId!.isEmpty)
                ? _BottomNavBar(onTap: widget.onNavTap, showChatBadge: false)
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
              child: const Icon(
                CupertinoIcons.back,
                color: _AppColors.textMain,
                size: 24,
              ),
            ),
            const Expanded(
              child: Text(
                'Event',
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
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Container(
        height: 48,
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(
          color: _AppColors.chipBg,
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
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          decoration: BoxDecoration(
            color: isSelected ? _AppColors.surfaceLight : Colors.transparent,
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
                color: isSelected
                    ? _AppColors.primary
                    : _AppColors.textSecondary,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// Material Colors placeholder
class Colors {
  static const Color transparent = Color(0x00000000);
}

// =============================================================================
// 히어로 카드 (슬롯머신)
// =============================================================================
class _HeroCard extends StatelessWidget {
  const _HeroCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(32),
        boxShadow: [
          BoxShadow(
            color: _AppColors.primary.withValues(alpha: 0.12),
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
              color: _AppColors.primary.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: _AppColors.primary.withValues(alpha: 0.1),
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  CupertinoIcons.shield_fill,
                  size: 14,
                  color: _AppColors.primary,
                ),
                const SizedBox(width: 4),
                const Text(
                  'SAFE MATCHING',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.8,
                    color: _AppColors.primary,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          // 타이틀
          const Text(
            '두근두근 3:3 시즌 미팅',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 22,
              fontWeight: FontWeight.w700,
              color: _AppColors.textMain,
              letterSpacing: -0.3,
            ),
          ),
          const SizedBox(height: 4),
          const Text(
            '검증된 회원들과 안전하고 설레는 만남',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: _AppColors.textSecondary,
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
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF9FA),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: _AppColors.primary.withValues(alpha: 0.05)),
      ),
      child: Stack(
        alignment: Alignment.center,
        children: [
          // 가로 라인
          Container(
            height: 2,
            margin: const EdgeInsets.symmetric(horizontal: 24),
            decoration: BoxDecoration(
              color: _AppColors.primary.withValues(alpha: 0.1),
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
    return Transform.scale(
      scale: isActive ? 1.1 : 1.0,
      child: Container(
        width: 64,
        height: 80,
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isActive
                ? _AppColors.primary.withValues(alpha: 0.3)
                : const Color(0xFFF1F5F9),
            width: isActive ? 2 : 1,
          ),
          boxShadow: isActive
              ? [
                  BoxShadow(
                    color: _AppColors.primary.withValues(alpha: 0.2),
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
            color: isActive ? _AppColors.primary : const Color(0xFFFFCDD2),
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
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: _AppColors.border.withValues(alpha: 0.5)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      CupertinoIcons.tickets_fill,
                      size: 16,
                      color: _AppColors.primary,
                    ),
                    const SizedBox(width: 6),
                    const Text(
                      '오늘 1회 무료',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: _AppColors.textMain,
                      ),
                    ),
                  ],
                ),
                const Padding(
                  padding: EdgeInsets.only(left: 22, top: 2),
                  child: Text(
                    '추가 돌리기 3,000원',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 12,
                      fontWeight: FontWeight.w400,
                      color: _AppColors.textSecondary,
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
              color: const Color(0xFFF8F6F6),
              borderRadius: BorderRadius.circular(16),
            ),
            child: const Icon(
              CupertinoIcons.refresh,
              size: 18,
              color: _AppColors.primary,
            ),
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
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onPressed,
      child: Container(
        width: double.infinity,
        height: 56,
        decoration: BoxDecoration(
          color: _AppColors.primary,
          borderRadius: BorderRadius.circular(28),
          boxShadow: [
            BoxShadow(
              color: _AppColors.primary.withValues(alpha: 0.35),
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
    return Container(
      height: 1,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [Colors.transparent, _AppColors.border, Colors.transparent],
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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 헤더
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                '제휴 장소 추천',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: _AppColors.textMain,
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
                    color: _AppColors.surfaceLight,
                    borderRadius: BorderRadius.circular(8),
                    boxShadow: [
                      BoxShadow(
                        color: CupertinoColors.black.withValues(alpha: 0.04),
                        blurRadius: 4,
                      ),
                    ],
                  ),
                  child: const Text(
                    '전체보기',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: _AppColors.textSecondary,
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
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: _AppColors.border.withValues(alpha: 0.6)),
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
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.textMain,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  description,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    fontWeight: FontWeight.w400,
                    color: _AppColors.textSecondary,
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
                      color: _AppColors.primary.withValues(alpha: 0.05),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Text(
                          '혜택 보기',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: _AppColors.primary,
                          ),
                        ),
                        const Icon(
                          CupertinoIcons.chevron_right,
                          size: 12,
                          color: _AppColors.primary,
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
              color: _AppColors.surfaceLight,
              borderRadius: BorderRadius.circular(32),
              boxShadow: [
                BoxShadow(
                  color: _AppColors.primary.withValues(alpha: 0.12),
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
                    color: _AppColors.primary.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        CupertinoIcons.shuffle,
                        size: 14,
                        color: _AppColors.primary,
                      ),
                      const SizedBox(width: 4),
                      const Text(
                        'RANDOM MATCHING',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0.8,
                          color: _AppColors.primary,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  '3:3 랜덤 매칭',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.textMain,
                    letterSpacing: -0.3,
                  ),
                ),
                const SizedBox(height: 4),
                const Text(
                  '같은 관심사를 가진 분들과 무작위로 매칭됩니다.',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: _AppColors.textSecondary,
                  ),
                ),
                const SizedBox(height: 28),
                // 매칭 비주얼
                Container(
                  padding: const EdgeInsets.all(24),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFF9FA),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: _AppColors.primary.withValues(alpha: 0.05),
                    ),
                  ),
                  child: Icon(
                    CupertinoIcons.person_2_fill,
                    size: 48,
                    color: _AppColors.primary.withValues(alpha: 0.8),
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
                color: _AppColors.primary,
                borderRadius: BorderRadius.circular(28),
                boxShadow: [
                  BoxShadow(
                    color: _AppColors.primary.withValues(alpha: 0.35),
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
            color: CupertinoColors.white.withValues(alpha: 0.95),
            borderRadius: BorderRadius.circular(32),
            border: Border.all(
              color: CupertinoColors.white.withValues(alpha: 0.4),
            ),
            boxShadow: [
              BoxShadow(
                color: CupertinoColors.black.withValues(alpha: 0.15),
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
                isActive: true,
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
              fontFamily: 'Pretendard',
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
