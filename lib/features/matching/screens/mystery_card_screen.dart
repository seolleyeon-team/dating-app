// =============================================================================
// 오늘의 인연 (미스터리 카드) 화면
// 경로: lib/features/matching/screens/mystery_card_screen.dart
//
// PageView 기반 스와이프 캐러셀 + 카드별 3D 플립 애니메이션
// 1차 탭: 미스터리 → 프로필 공개 (플립)
// 2차 탭: ai_match_card_screen으로 이동
// =============================================================================

import 'dart:async';
import 'dart:math';
import 'dart:ui';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../../chat/services/chat_service.dart';
import '../../notifications/services/notification_service.dart';
import '../../../router/route_names.dart';
import '../../../services/ask_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/rec_event_service.dart';
import '../../../services/ai_recommendation_service.dart';
import '../../../shared/constants/photo_blur_constants.dart';
import '../../../shared/widgets/capture_protected_image.dart';
import '../models/profile_card_args.dart';
import '../../../core/constants/app_colors.dart';
import '../../../shared/widgets/seolleyeon_bottom_navigation_bar.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF4D88);
  static const Color purple100 = Color(0xFFEDE9FE);
  static const Color purple600 = Color(0xFF9333EA);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray300 = Color(0xFFD1D5DB);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray500 = Color(0xFF6B7280);
  static const Color gray900 = Color(0xFF111827);
  static const Color pink50 = Color(0xFFFDF2F8);
  static const Color pink100 = Color(0xFFFCE7F3);
  static const Color pink500 = Color(0xFFEC4899);
}

// =============================================================================
// 메인 화면
// =============================================================================
class MysteryCardScreen extends StatefulWidget {
  final int notificationCount;
  final int remainingMatches;
  final VoidCallback? onAiPreference;
  final VoidCallback? onNotification;
  final VoidCallback? onSettings;
  final Function(int index)? onNavTap;

  const MysteryCardScreen({
    super.key,
    this.notificationCount = 1,
    this.remainingMatches = 2,
    this.onAiPreference,
    this.onNotification,
    this.onSettings,
    this.onNavTap,
  });

  @override
  State<MysteryCardScreen> createState() => _MysteryCardScreenState();
}

class _MysteryCardScreenState extends State<MysteryCardScreen> {
  final StorageService _storageService = StorageService();
  final ChatService _chatService = ChatService();
  final NotificationService _notificationService = NotificationService();

  String? _currentUserId;

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

  void _handleNotificationTap() {
    if (widget.onNotification != null) {
      widget.onNotification!();
      return;
    }

    Navigator.of(
      context,
      rootNavigator: true,
    ).pushNamed(RouteNames.notifications);
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: Theme.of(context).brightness == Brightness.dark
          ? AppColorsDark.background
          : CupertinoColors.white,
      child: Stack(
        children: [
          _BackgroundGradients(),
          SafeArea(
            child: Column(
              children: [
                if (_currentUserId == null || _currentUserId!.isEmpty)
                  _Header(
                    notificationCount: widget.notificationCount,
                    onAiPreference:
                        widget.onAiPreference ??
                        () => Navigator.of(
                          context,
                          rootNavigator: true,
                        ).pushNamed(RouteNames.aiPreference),
                    onNotification: _handleNotificationTap,
                  )
                else
                  StreamBuilder<int>(
                    stream: _notificationService.unreadNotificationCountStream(
                      _currentUserId!,
                    ),
                    builder: (context, snapshot) {
                      final unreadCount = snapshot.data ?? 0;

                      return _Header(
                        notificationCount: unreadCount,
                        onAiPreference:
                            widget.onAiPreference ??
                            () => Navigator.of(
                              context,
                              rootNavigator: true,
                            ).pushNamed(RouteNames.aiPreference),
                        onNotification: _handleNotificationTap,
                      );
                    },
                  ),
                Expanded(
                  child: _MainContent(
                    remainingMatches: widget.remainingMatches,
                    onSettings: widget.onSettings,
                  ),
                ),
              ],
            ),
          ),
          (_currentUserId == null || _currentUserId!.isEmpty)
              ? SeolleyeonBottomNavPositioned(
                  currentTab: BottomNavTab.matching,
                  onTap: widget.onNavTap,
                  showChatBadge: false,
                )
              : StreamBuilder<bool>(
                  stream: _chatService.hasAnyUnreadChats(_currentUserId!),
                  builder: (context, snapshot) {
                    final hasUnread = snapshot.data == true;
                    return SeolleyeonBottomNavPositioned(
                      currentTab: BottomNavTab.matching,
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
              shape: BoxShape.circle,
              gradient: RadialGradient(
                colors: [
                  const Color(0xFFFBCFE8).withValues(alpha: 0.32),
                  const Color(0xFFFBCFE8).withValues(alpha: 0.0),
                ],
              ),
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
              shape: BoxShape.circle,
              gradient: RadialGradient(
                colors: [
                  const Color(0xFFE9D5FF).withValues(alpha: 0.32),
                  const Color(0xFFE9D5FF).withValues(alpha: 0.0),
                ],
              ),
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
    final displayCount = notificationCount > 9 ? '9+' : '$notificationCount';
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final primary = Theme.of(context).colorScheme.primary;
    final titleColor =
        isDark ? AppColorsDark.textPrimary : _AppColors.gray900;

    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Icon(
                CupertinoIcons.heart_fill,
                size: 24,
                color: primary,
              ),
              const SizedBox(width: 8),
              Text(
                '설레연',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 21,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.3,
                  color: titleColor,
                ),
              ),
            ],
          ),
          Expanded(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.end,
              mainAxisSize: MainAxisSize.min,
              children: [
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  onPressed: onAiPreference,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: isDark
                          ? AppColorsDark.surfaceVariant
                          : _AppColors.pink50,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: isDark
                            ? AppColorsDark.border
                            : _AppColors.pink100,
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          CupertinoIcons.sparkles,
                          size: 16,
                          color: isDark
                              ? AppColorsDark.primary
                              : _AppColors.pink500,
                        ),
                        const SizedBox(width: 4),
                        Flexible(
                          child: Text(
                            'AI에게 내 취향 알려주기',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              color: titleColor,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  onPressed: onNotification,
                  child: Stack(
                    clipBehavior: Clip.none,
                    children: [
                      Icon(
                        CupertinoIcons.bell,
                        size: 24,
                        color: isDark
                            ? AppColorsDark.textSecondary
                            : _AppColors.gray500,
                      ),
                      if (notificationCount > 0)
                        Positioned(
                          top: -4,
                          right: -6,
                          child: Container(
                            constraints: const BoxConstraints(
                              minWidth: 16,
                              minHeight: 16,
                            ),
                            padding: const EdgeInsets.symmetric(horizontal: 3),
                            decoration: BoxDecoration(
                              color: primary,
                              borderRadius: BorderRadius.circular(999),
                              border: Border.all(
                                color: isDark
                                    ? AppColorsDark.background
                                    : CupertinoColors.white,
                                width: 2,
                              ),
                            ),
                            child: Center(
                              child: Text(
                                displayCount,
                                style: const TextStyle(
                                  fontFamily: 'Pretendard',
                                  fontSize: 9,
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
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 메인 콘텐츠 (StatefulWidget — 인디케이터 인덱스 관리)
// =============================================================================
class _MainContent extends StatefulWidget {
  final int remainingMatches;
  final VoidCallback? onSettings;

  const _MainContent({required this.remainingMatches, this.onSettings});

  @override
  State<_MainContent> createState() => _MainContentState();
}

class _MainContentState extends State<_MainContent> {
  late PageController _pageController;
  int _currentIndex = 0;
  List<AiRecommendedProfile> _profiles = [];
  bool _isLoading = true;
  bool _isPageInteracting = false;
  bool _isCardFlipLocked = false;
  bool _isForceSnapping = false;
  String? _kakaoUserId;
  Timer? _pageSettleTimer;
  final _storageService = StorageService();
  final _askService = AskService();

  @override
  void initState() {
    super.initState();
    _pageController = PageController(viewportFraction: 0.85);
    _loadRecommendations();
  }

  Future<void> _loadRecommendations() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (mounted) setState(() => _kakaoUserId = kakaoUserId);

    final aiService = AiRecommendationService();
    final feed = await aiService.fetchMysteryFeed(
      limit: 3,
      userId: kakaoUserId,
    );

    if (!mounted) return;
    setState(() {
      _profiles = feed;
      _isLoading = false;
    });

    if (_profiles.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _recordImpression(0);
      });
    }
  }

  void _recordImpression(int index) {
    if (index >= _profiles.length) return;
    final uid = _kakaoUserId;
    if (uid == null) return;

    final profile = _profiles[index];

    final Map<String, dynamic> contextMetadata = {
      'screen': 'mystery_card_screen',
      'position': index,
    };
    if (profile.rank != 999) contextMetadata['rank'] = profile.rank;
    if (profile.sourceScores != null) {
      contextMetadata['score'] = profile.sourceScores!;
    }
    if (profile.finalScore != null) {
      contextMetadata['finalScore'] = profile.finalScore!;
    }
    contextMetadata['algorithmVersion'] = profile.primaryAlgo;

    RecEventService()
        .logEvent(
          userId: uid,
          targetType: 'user_profile',
          targetId: profile.candidateUid,
          candidateUserId: profile.candidateUid,
          eventType: 'impression',
          surface: 'mystery_card',
          cardVariant: 'real_profile',
          exposureId: profile.exposureId,
          context: contextMetadata,
        )
        .catchError(
          (e) => debugPrint('[RecEvent] mystery_card impression failed: $e'),
        );
  }

  String _todayLabel() {
    return DateFormat('MMM d', 'en_US').format(DateTime.now());
  }

  @override
  void dispose() {
    _pageSettleTimer?.cancel();
    _pageController.dispose();
    super.dispose();
  }

  void _setPageInteracting(bool value) {
    if (!mounted || _isPageInteracting == value) return;
    setState(() => _isPageInteracting = value);
  }

  void _setCardFlipLocked(bool value) {
    if (!mounted || _isCardFlipLocked == value) return;
    setState(() => _isCardFlipLocked = value);
  }

  void _markPageMoving() {
    _pageSettleTimer?.cancel();
    _setPageInteracting(true);
  }

  Future<void> _forceSnapToNearestPage() async {
    if (!mounted || !_pageController.hasClients || _isForceSnapping) return;
    if (_profiles.isEmpty || _isCardFlipLocked) return;

    final page = _pageController.page;
    if (page == null || !page.isFinite) return;

    final targetPage = page.round().clamp(0, _profiles.length - 1);
    if ((page - targetPage).abs() < 0.001) return;

    _isForceSnapping = true;
    try {
      await _pageController.animateToPage(
        targetPage,
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOutCubic,
      );
    } finally {
      _isForceSnapping = false;
    }
  }

  void _handleScrollSettled() {
    _pageSettleTimer?.cancel();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await _forceSnapToNearestPage();
      if (!mounted) return;
      _scheduleSnapVerification();
    });
  }

  bool _isPageAligned() {
    if (!_pageController.hasClients) return true;
    final page = _pageController.page;
    if (page == null || !page.isFinite) return true;
    return (page - page.round()).abs() < 0.01;
  }

  void _scheduleSnapVerification([int retriesLeft = 2]) {
    _pageSettleTimer?.cancel();
    _pageSettleTimer = Timer(const Duration(milliseconds: 120), () async {
      if (!mounted) return;
      if (!_isPageAligned() && retriesLeft > 0) {
        await _forceSnapToNearestPage();
        if (!mounted) return;
        _scheduleSnapVerification(retriesLeft - 1);
        return;
      }
      _setPageInteracting(false);
    });
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final headlineColor =
        isDark ? AppColorsDark.textPrimary : _AppColors.gray900;
    final mutedColor =
        isDark ? const Color(0xFF7A6B76) : _AppColors.gray400;
    final primary = Theme.of(context).colorScheme.primary;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 0),
      child: Column(
        children: [
          const SizedBox(height: 16),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Row(
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
                            color: isDark
                                ? AppColorsDark.surfaceVariant
                                : _AppColors.purple100,
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            'AI CURATED',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              color: isDark
                                  ? AppColorsDark.primaryLight
                                  : _AppColors.purple600,
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          _todayLabel(),
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 12,
                            color: mutedColor,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '오늘의 인연',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 30,
                        fontWeight: FontWeight.w500,
                        letterSpacing: -0.5,
                        color: headlineColor,
                      ),
                    ),
                  ],
                ),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (_kakaoUserId != null && _kakaoUserId!.isNotEmpty)
                      StreamBuilder<int>(
                        stream: _askService.unreadReceivedCount(_kakaoUserId!),
                        builder: (context, askSnap) {
                          final hasUnread = (askSnap.data ?? 0) > 0;
                          return CupertinoButton(
                            padding: EdgeInsets.zero,
                            onPressed: () {
                              HapticFeedback.lightImpact();
                              Navigator.of(
                                context,
                                rootNavigator: true,
                              ).pushNamed(RouteNames.asksInbox);
                            },
                            child: SizedBox(
                              width: 40,
                              height: 40,
                              child: Stack(
                                clipBehavior: Clip.none,
                                children: [
                                  Center(
                                    child: Icon(
                                      CupertinoIcons.tray_fill,
                                      size: 23,
                                      color: mutedColor,
                                    ),
                                  ),
                                  if (hasUnread)
                                    Positioned(
                                      right: 4,
                                      top: 4,
                                      child: Container(
                                        width: 10,
                                        height: 10,
                                        decoration: BoxDecoration(
                                          color: primary,
                                          shape: BoxShape.circle,
                                          border: Border.all(
                                            color: isDark
                                                ? AppColorsDark.background
                                                : CupertinoColors.white,
                                            width: 1.5,
                                          ),
                                        ),
                                      ),
                                    ),
                                ],
                              ),
                            ),
                          );
                        },
                      )
                    else
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: () {
                          HapticFeedback.lightImpact();
                          Navigator.of(
                            context,
                            rootNavigator: true,
                          ).pushNamed(RouteNames.asksInbox);
                        },
                        child: SizedBox(
                          width: 40,
                          height: 40,
                          child: Center(
                            child: Icon(
                              CupertinoIcons.tray_fill,
                              size: 23,
                              color: mutedColor,
                            ),
                          ),
                        ),
                      ),
                    CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: () {
                        Navigator.of(
                          context,
                          rootNavigator: true,
                        ).pushNamed(RouteNames.sentHearts);
                      },
                      child: Icon(
                        CupertinoIcons.heart,
                        size: 24,
                        color: mutedColor,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          Expanded(
            child: _isLoading
                ? const Center(child: CupertinoActivityIndicator())
                : _profiles.isEmpty
                ? Center(
                    child: Text(
                      '오늘의 미스터리 카드가 모두 소진되었습니다.',
                      style: TextStyle(
                        color: isDark
                            ? AppColorsDark.textSecondary
                            : _AppColors.gray500,
                        fontFamily: 'Pretendard',
                      ),
                    ),
                  )
                : NotificationListener<ScrollNotification>(
                    onNotification: (notification) {
                      if (notification is ScrollStartNotification) {
                        _markPageMoving();
                      } else if (notification is ScrollUpdateNotification) {
                        _markPageMoving();
                      } else if (notification is ScrollEndNotification) {
                        _handleScrollSettled();
                      }
                      return false;
                    },
                    child: PageView.builder(
                      controller: _pageController,
                      pageSnapping: true,
                      physics: _isCardFlipLocked
                          ? const NeverScrollableScrollPhysics()
                          : const PageScrollPhysics(),
                      itemCount: _profiles.length,
                      onPageChanged: (idx) {
                        setState(() => _currentIndex = idx);
                        _recordImpression(idx);
                      },
                      itemBuilder: (context, index) {
                        final isActive = index == _currentIndex;
                        return AnimatedScale(
                          scale: isActive ? 1.0 : 0.95,
                          duration: const Duration(milliseconds: 300),
                          curve: Curves.easeOutCubic,
                          child: Center(
                            child: _MysteryCard(
                              key: ValueKey(_profiles[index].candidateUid),
                              profile: _profiles[index],
                              isActive: isActive,
                              allowSecureCapture: true,
                              onFlipLockChanged: _setCardFlipLocked,
                              kakaoUserId: _kakaoUserId,
                            ),
                          ),
                        );
                      },
                    ),
                  ),
          ),
          const SizedBox(height: 24),
          if (!_isLoading && _profiles.isNotEmpty)
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: List.generate(_profiles.length, (i) {
                return Container(
                  width: 8,
                  height: 8,
                  margin: const EdgeInsets.symmetric(horizontal: 4),
                  decoration: BoxDecoration(
                    color: i == _currentIndex
                        ? (isDark
                            ? AppColorsDark.textPrimary
                            : _AppColors.gray900)
                        : (isDark
                            ? AppColorsDark.divider
                            : _AppColors.gray300),
                    shape: BoxShape.circle,
                  ),
                );
              }),
            ),
          const SizedBox(height: 100),
        ],
      ),
    );
  }
}

// =============================================================================
// 미스터리 카드
// =============================================================================
class _MysteryCard extends StatefulWidget {
  final AiRecommendedProfile profile;
  final bool isActive;
  final bool allowSecureCapture;
  final ValueChanged<bool>? onFlipLockChanged;
  final String? kakaoUserId;

  const _MysteryCard({
    super.key,
    required this.profile,
    required this.isActive,
    required this.allowSecureCapture,
    this.onFlipLockChanged,
    this.kakaoUserId,
  });

  @override
  State<_MysteryCard> createState() => _MysteryCardState();
}

class _MysteryCardState extends State<_MysteryCard>
    with SingleTickerProviderStateMixin, AutomaticKeepAliveClientMixin {
  late AnimationController _controller;
  late Animation<double> _animation;
  bool _isRevealed = false;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 700),
      vsync: this,
    );
    _animation = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOutCubic),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onCardTap() {
    if (!widget.isActive || _controller.isAnimating) return;

    if (_isRevealed) {
      HapticFeedback.lightImpact();
      Future.delayed(const Duration(milliseconds: 150), () {
        if (!mounted) return;
        Navigator.of(context, rootNavigator: true).pushNamed(
          RouteNames.profileSpecificDetail,
          arguments: ProfileCardArgs.fromAi(widget.profile),
        );
      });
    } else {
      HapticFeedback.mediumImpact();
      widget.onFlipLockChanged?.call(true);
      final uid = widget.kakaoUserId;
      if (uid != null) {
        final Map<String, dynamic> contextMetadata = {
          'screen': 'mystery_card_screen',
        };
        if (widget.profile.rank != 999) {
          contextMetadata['rank'] = widget.profile.rank;
        }
        if (widget.profile.sourceScores != null) {
          contextMetadata['score'] = widget.profile.sourceScores!;
        }
        if (widget.profile.finalScore != null) {
          contextMetadata['finalScore'] = widget.profile.finalScore!;
        }
        contextMetadata['algorithmVersion'] = widget.profile.primaryAlgo;

        RecEventService()
            .logEvent(
              userId: uid,
              targetType: 'user_profile',
              targetId: widget.profile.candidateUid,
              candidateUserId: widget.profile.candidateUid,
              eventType: 'open',
              surface: 'mystery_card',
              cardVariant: 'real_profile',
              exposureId: widget.profile.exposureId,
              context: contextMetadata,
            )
            .catchError(
              (e) => debugPrint('[RecEvent] mystery_card open failed: $e'),
            );
      }
      _controller.forward().then((_) {
        if (mounted) {
          setState(() => _isRevealed = true);
        }
      }).whenComplete(() {
        widget.onFlipLockChanged?.call(false);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final screenWidth = MediaQuery.of(context).size.width;
    final cardWidth = screenWidth * 0.75;
    final cardHeight = cardWidth * 1.33;
    final staticBackFace = _isRevealed && !_controller.isAnimating;

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: _onCardTap,
      child: staticBackFace
          ? _buildBackFace(cardWidth, cardHeight, applyMirrorTransform: false)
          : AnimatedBuilder(
              animation: _animation,
              builder: (context, child) {
                final angle = _animation.value * pi;
                final isBackVisible = _animation.value >= 0.5;

                return Transform(
                  alignment: Alignment.center,
                  transform: Matrix4.identity()
                    ..setEntry(3, 2, 0.001)
                    ..rotateY(angle),
                  child: isBackVisible
                      ? _buildBackFace(cardWidth, cardHeight)
                      : _buildFrontFace(cardWidth, cardHeight),
                );
              },
            ),
    );
  }

  Widget _buildFrontFace(double cardWidth, double cardHeight) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardBg =
        isDark ? AppColorsDark.surface : CupertinoColors.white;
    final cardBorder =
        isDark ? AppColorsDark.border : _AppColors.gray100;

    return Container(
      width: cardWidth,
      height: cardHeight,
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: cardBorder),
        boxShadow: widget.isActive
            ? [
                BoxShadow(
                  color: CupertinoColors.black.withValues(alpha: 0.15),
                  blurRadius: 60,
                  offset: const Offset(0, 0),
                ),
                BoxShadow(
                  color: CupertinoColors.black.withValues(alpha: 0.04),
                  blurRadius: 20,
                  offset: const Offset(0, 0),
                ),
              ]
            : null,
      ),
      child: Stack(
        alignment: Alignment.center,
        children: [
          Container(
            width: 160,
            height: 160,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: RadialGradient(
                colors: [
                  _AppColors.primary.withValues(
                    alpha: widget.isActive ? 0.16 : 0.08,
                  ),
                  _AppColors.primary.withValues(alpha: 0),
                ],
              ),
              boxShadow: [
                BoxShadow(
                  color: _AppColors.primary.withValues(
                    alpha: widget.isActive ? 0.16 : 0.08,
                  ),
                  blurRadius: widget.isActive ? 36 : 22,
                  spreadRadius: widget.isActive ? 4 : 1,
                ),
              ],
            ),
          ),
          Text(
            '?',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 128,
              fontWeight: FontWeight.w700,
              color: widget.isActive
                  ? _AppColors.primary
                  : _AppColors.primary.withValues(alpha: 0.7),
            ),
          ),
          if (widget.isActive)
            Positioned(
              bottom: 24,
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 8,
                ),
                decoration: BoxDecoration(
                  color: _AppColors.primary.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      CupertinoIcons.hand_draw,
                      size: 16,
                      color: _AppColors.primary,
                    ),
                    SizedBox(width: 6),
                    Text(
                      '탭하여 확인하기',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                        color: _AppColors.primary,
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

  Widget _buildBackFace(
    double cardWidth,
    double cardHeight, {
    bool applyMirrorTransform = true,
  }) {
    final profile = widget.profile;
    final shouldUseSecureCapture =
        widget.allowSecureCapture &&
        _isRevealed &&
        !_controller.isAnimating;

    final body = Container(
        width: cardWidth,
        height: cardHeight,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(24),
          boxShadow: [
            BoxShadow(
              color: _AppColors.primary.withValues(alpha: 0.25),
              blurRadius: 40,
              offset: const Offset(0, 0),
            ),
          ],
        ),
        clipBehavior: Clip.antiAlias,
        child: Stack(
          fit: StackFit.expand,
          children: [
            widget.profile.imageUrls.isNotEmpty
                ? CaptureProtectedImage(
                    imageUrl: widget.profile.imageUrls.first,
                    fit: BoxFit.cover,
                    borderRadius: 24,
                    blurEnabled: true,
                    blurSigma: kLockedProfilePhotoBlurSigma,
                    blurBadgeText: '사진은 상세에서 채팅 후 선명하게 보여요',
                    iosSecureCaptureEnabled: shouldUseSecureCapture,
                    backgroundColor: _AppColors.gray300,
                    placeholderIconColor: CupertinoColors.white,
                    placeholderIconSize: 42,
                  )
                : Container(color: _AppColors.gray300),
            Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    CupertinoColors.black.withValues(alpha: 0),
                    CupertinoColors.black.withValues(alpha: 0.15),
                    CupertinoColors.black.withValues(alpha: 0.75),
                  ],
                  stops: const [0.0, 0.5, 1.0],
                ),
              ),
            ),
            Positioned(
              left: 24,
              right: 24,
              bottom: 24,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Flexible(
                        child: Text(
                          profile.name,
                          style: const TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 28,
                            fontWeight: FontWeight.w600,
                            color: CupertinoColors.white,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      const SizedBox(width: 10),
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
                              '${profile.sourceScores != null ? (profile.sourceScores! * 100).toInt() : 85}% Match',
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
                  ),
                  const SizedBox(height: 4),
                  Text(
                    "${profile.major} • ${profile.age}",
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 14,
                      fontWeight: FontWeight.w300,
                      color: CupertinoColors.white.withValues(alpha: 0.8),
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: profile.tags.take(3).map((tag) {
                      return ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: BackdropFilter(
                          filter: ImageFilter.blur(sigmaX: 4, sigmaY: 4),
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 10,
                              vertical: 5,
                            ),
                            decoration: BoxDecoration(
                              color: CupertinoColors.black.withValues(
                                alpha: 0.35,
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
                                fontSize: 11,
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
              ),
            ),
          ],
        ),
      );

    if (!applyMirrorTransform) {
      return body;
    }

    return Transform(
      alignment: Alignment.center,
      transform: Matrix4.identity()..rotateY(pi),
      child: body,
    );
  }
}

