// =============================================================================
// 오늘의 인연 (미스터리 카드) 화면
// 경로: lib/features/matching/screens/mystery_card_screen.dart
//
// PageView 기반 스와이프 캐러셀 + 카드별 3D 플립 애니메이션
// 1차 탭: 미스터리 → 프로필 공개 (플립)
// 2차 탭: ai_match_card_screen으로 이동
// =============================================================================

import 'dart:math';
import 'dart:ui';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import '../../chat/services/chat_service.dart';
import '../../../router/route_names.dart';
import '../../../services/storage_service.dart';
import '../../../services/rec_event_service.dart';
import '../../../services/ai_recommendation_service.dart';

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
                  notificationCount: widget.notificationCount,
                  onAiPreference:
                      widget.onAiPreference ??
                      () => Navigator.of(
                        context,
                        rootNavigator: true,
                      ).pushNamed(RouteNames.aiPreference),
                  onNotification: widget.onNotification,
                ),
                // 메인 콘텐츠 (StatefulWidget으로 인디케이터 관리)
                Expanded(
                  child: _MainContent(
                    remainingMatches: widget.remainingMatches,
                    onSettings: widget.onSettings,
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
            child: (_currentUserId == null || _currentUserId!.isEmpty)
                ? _FloatingNavBar(onTap: widget.onNavTap, showChatBadge: false)
                : StreamBuilder<bool>(
                    stream: _chatService.hasAnyUnreadChats(_currentUserId!),
                    builder: (context, snapshot) {
                      final hasUnread = snapshot.data == true;
                      return _FloatingNavBar(
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
              color: const Color(0xFFFBCFE8).withOpacity(0.3),
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
              color: const Color(0xFFE9D5FF).withOpacity(0.3),
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
                  fontFamily: 'Noto Sans KR',
                  fontSize: 21,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.3,
                  color: _AppColors.gray900,
                ),
              ),
            ],
          ),
          // 버튼들
          Expanded(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.end,
              mainAxisSize: MainAxisSize.min,
              children: [
                // AI 취향 버튼
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  onPressed: onAiPreference,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
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
                        const SizedBox(width: 4),
                        const Flexible(
                          child: Text(
                            'AI에게 내 취향 알려주기',
                            style: TextStyle(
                              fontFamily: 'Noto Sans KR',
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              color: _AppColors.gray900,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 8),
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
                                  fontFamily: 'Noto Sans KR',
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

  @override
  void initState() {
    super.initState();
    // 뷰포트 대비 0.85 정도로 양옆 카드가 살짝 보이게
    _pageController = PageController(viewportFraction: 0.85);

    _loadRecommendations();
  }

  Future<void> _loadRecommendations() async {
    final aiService = AiRecommendationService();
    final feed = await aiService.fetchMysteryFeed(limit: 3);

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
    final uid = FirebaseAuth.instance.currentUser?.uid;
    if (uid == null) return;

    final profile = _profiles[index];

    final Map<String, dynamic> contextMetadata = {
      'screen': 'mystery_card_screen',
      'position': index,
    };
    if (profile.rank != 999) contextMetadata['rank'] = profile.rank;
    if (profile.sourceScores != null)
      contextMetadata['score'] = profile.sourceScores!;
    if (profile.finalScore != null)
      contextMetadata['finalScore'] = profile.finalScore!;
    contextMetadata['algorithmVersion'] = profile.primaryAlgo;

    RecEventService().logEvent(
      userId: uid,
      targetType: 'user_profile',
      targetId: profile.candidateUid,
      candidateUserId: profile.candidateUid,
      eventType: 'impression',
      surface: 'mystery_card',
      cardVariant: 'real_profile',
      exposureId: profile.exposureId,
      context: contextMetadata,
    );
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 0),
      child: Column(
        children: [
          const SizedBox(height: 16),
          // 타이틀 영역
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
                            color: _AppColors.purple100,
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: const Text(
                            'AI CURATED',
                            style: TextStyle(
                              fontFamily: 'Noto Sans KR',
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
                            fontFamily: 'Noto Sans KR',
                            fontSize: 12,
                            color: _AppColors.gray400,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      '오늘의 인연',
                      style: TextStyle(
                        fontFamily: 'Noto Sans KR',
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
                  onPressed: () {
                    Navigator.of(
                      context,
                      rootNavigator: true,
                    ).pushNamed(RouteNames.sentHearts);
                  },
                  child: const Icon(
                    CupertinoIcons.heart,
                    size: 24,
                    color: _AppColors.gray400,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          // ─── PageView 기반 카드 캐러셀 ───
          Expanded(
            child: _isLoading
                ? const Center(child: CupertinoActivityIndicator())
                : _profiles.isEmpty
                ? Center(
                    child: Text(
                      '오늘의 미스터리 카드가 모두 소진되었습니다.',
                      style: TextStyle(
                        color: _AppColors.gray500,
                        fontFamily: 'Noto Sans KR',
                      ),
                    ),
                  )
                : PageView.builder(
                    controller: _pageController,
                    itemCount: _profiles.length,
                    physics: const BouncingScrollPhysics(),
                    onPageChanged: (idx) {
                      setState(() => _currentIndex = idx);
                      _recordImpression(idx); // 새 카드 노출(impression)
                    },
                    itemBuilder: (context, index) {
                      final isActive = index == _currentIndex;
                      return AnimatedScale(
                        scale: isActive ? 1.0 : 0.95,
                        duration: const Duration(milliseconds: 300),
                        curve: Curves.easeOutCubic,
                        child: AnimatedOpacity(
                          opacity: isActive ? 1.0 : 0.55,
                          duration: const Duration(milliseconds: 300),
                          curve: Curves.easeOutCubic,
                          child: Center(
                            child: _MysteryCard(
                              key: ValueKey(_profiles[index].candidateUid),
                              profile: _profiles[index],
                              isActive: isActive,
                            ),
                          ),
                        ),
                      );
                    },
                  ),
          ),
          const SizedBox(height: 24),
          // ─── 동적 인디케이터 (profiles.length 기반) ───
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
                        ? _AppColors.gray900
                        : _AppColors.gray300,
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
// 미스터리 카드 (3D 플립 애니메이션)
//
// - AutomaticKeepAliveClientMixin으로 플립 상태 유지
// - 1차 탭: 미스터리 → 프로필 플립
// - 2차 탭: ai_match_card_screen 이동
// =============================================================================
class _MysteryCard extends StatefulWidget {
  final AiRecommendedProfile profile;
  final bool isActive;

  const _MysteryCard({
    super.key,
    required this.profile,
    required this.isActive,
  });

  @override
  State<_MysteryCard> createState() => _MysteryCardState();
}

class _MysteryCardState extends State<_MysteryCard>
    with SingleTickerProviderStateMixin, AutomaticKeepAliveClientMixin {
  late AnimationController _controller;
  late Animation<double> _animation;
  bool _isRevealed = false;

  // AutomaticKeepAliveClientMixin: 스와이프해도 플립 상태 유지
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
      // 2차 탭: ai_match_card_screen으로 이동
      HapticFeedback.lightImpact();
      Future.delayed(const Duration(milliseconds: 150), () {
        if (!mounted) return;
        Navigator.of(
          context,
          rootNavigator: true,
        ).pushNamed(RouteNames.profileSpecificDetail);
      });
    } else {
      // 1차 탭: 플립 애니메이션으로 프로필 공개 + recEvents open 기록
      HapticFeedback.mediumImpact();
      final uid = FirebaseAuth.instance.currentUser?.uid;
      if (uid != null) {
        final Map<String, dynamic> contextMetadata = {
          'screen': 'mystery_card_screen',
        };
        if (widget.profile.rank != 999)
          contextMetadata['rank'] = widget.profile.rank;
        if (widget.profile.sourceScores != null)
          contextMetadata['score'] = widget.profile.sourceScores!;
        if (widget.profile.finalScore != null)
          contextMetadata['finalScore'] = widget.profile.finalScore!;
        contextMetadata['algorithmVersion'] = widget.profile.primaryAlgo;

        RecEventService().logEvent(
          userId: uid,
          targetType: 'user_profile',
          targetId: widget.profile.candidateUid,
          candidateUserId: widget.profile.candidateUid,
          eventType: 'open',
          surface: 'mystery_card',
          cardVariant: 'real_profile',
          exposureId: widget.profile.exposureId,
          context: contextMetadata,
        );
      }
      _controller.forward().then((_) {
        if (mounted) setState(() => _isRevealed = true);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context); // AutomaticKeepAliveClientMixin 필수 호출
    final screenWidth = MediaQuery.of(context).size.width;
    final cardWidth = screenWidth * 0.75;
    final cardHeight = cardWidth * 1.33;

    return GestureDetector(
      onTap: _onCardTap,
      child: AnimatedBuilder(
        animation: _animation,
        builder: (context, child) {
          final angle = _animation.value * pi;
          final isBackVisible = _animation.value >= 0.5;

          return Transform(
            alignment: Alignment.center,
            transform: Matrix4.identity()
              ..setEntry(3, 2, 0.001) // perspective
              ..rotateY(angle),
            child: isBackVisible
                ? _buildBackFace(cardWidth, cardHeight)
                : _buildFrontFace(cardWidth, cardHeight),
          );
        },
      ),
    );
  }

  /// 앞면: 미스터리 '?' 카드
  Widget _buildFrontFace(double cardWidth, double cardHeight) {
    return Container(
      width: cardWidth,
      height: cardHeight,
      decoration: BoxDecoration(
        color: CupertinoColors.white,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: _AppColors.gray100),
        boxShadow: widget.isActive
            ? [
                BoxShadow(
                  color: CupertinoColors.black.withValues(alpha: 0.15),
                  blurRadius: 60,
                  offset: const Offset(0, 30),
                ),
                BoxShadow(
                  color: CupertinoColors.black.withValues(alpha: 0.04),
                  blurRadius: 20,
                  offset: const Offset(0, 10),
                ),
              ]
            : null,
      ),
      child: Stack(
        alignment: Alignment.center,
        children: [
          // 배경 원
          Container(
            width: 160,
            height: 160,
            decoration: BoxDecoration(
              color: _AppColors.primary.withValues(
                alpha: widget.isActive ? 0.1 : 0.05,
              ),
              shape: BoxShape.circle,
            ),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
              child: const SizedBox(),
            ),
          ),
          // 물음표
          Text(
            '?',
            style: TextStyle(
              fontFamily: 'Noto Sans KR',
              fontSize: 128,
              fontWeight: FontWeight.w700,
              color: widget.isActive
                  ? _AppColors.primary
                  : _AppColors.primary.withValues(alpha: 0.7),
            ),
          ),
          // 탭 힌트 (활성 카드만)
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
                        fontFamily: 'Noto Sans KR',
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

  /// 뒷면: 프로필 카드 프리뷰 (좌우 반전 보정, 프로필 데이터 사용)
  Widget _buildBackFace(double cardWidth, double cardHeight) {
    final profile = widget.profile;
    return Transform(
      alignment: Alignment.center,
      transform: Matrix4.identity()..rotateY(pi), // 거울 보정
      child: Container(
        width: cardWidth,
        height: cardHeight,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(24),
          boxShadow: [
            BoxShadow(
              color: _AppColors.primary.withValues(alpha: 0.25),
              blurRadius: 40,
              offset: const Offset(0, 20),
            ),
          ],
        ),
        clipBehavior: Clip.antiAlias,
        child: Stack(
          fit: StackFit.expand,
          children: [
            // 프로필 이미지
            widget.profile.imageUrls.isNotEmpty
                ? Image.network(
                    widget.profile.imageUrls.first,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) =>
                        Container(color: _AppColors.gray300),
                  )
                : Container(color: _AppColors.gray300),
            // 그라데이션 오버레이
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
            // 프로필 정보
            Positioned(
              left: 24,
              right: 24,
              bottom: 24,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 이름 + 매치율
                  Row(
                    children: [
                      Flexible(
                        child: Text(
                          profile.name,
                          style: const TextStyle(
                            fontFamily: 'Noto Sans KR',
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
                                fontFamily: 'Noto Sans KR',
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
                  // 학과 + 학번
                  Text(
                    "${profile.major} • ${profile.age}",
                    style: TextStyle(
                      fontFamily: 'Noto Sans KR',
                      fontSize: 14,
                      fontWeight: FontWeight.w300,
                      color: CupertinoColors.white.withValues(alpha: 0.8),
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 12),
                  // 태그 칩
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
                                fontFamily: 'Noto Sans KR',
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
      ),
    );
  }
}

// =============================================================================
// 플로팅 네비게이션
// =============================================================================
class _FloatingNavBar extends StatelessWidget {
  final Function(int index)? onTap;
  final bool showChatBadge;

  const _FloatingNavBar({this.onTap, this.showChatBadge = false});

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
      child: SizedBox(
        width: 48,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Stack(
              clipBehavior: Clip.none,
              children: [
                Icon(
                  icon,
                  size: 24,
                  color: isActive ? _AppColors.primary : _AppColors.gray400,
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
