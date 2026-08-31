import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../../../core/constants/app_colors.dart';
import '../../../router/route_names.dart';
import '../../../services/ai_recommendation_service.dart';
import '../../../services/ask_service.dart';
import '../../../services/contact_block_service.dart';
import '../../../services/rec_event_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../../shared/constants/photo_blur_constants.dart';
import '../../../shared/utils/privacy_log_utils.dart';
import '../../../shared/widgets/capture_protected_image.dart';
import '../../../shared/widgets/kakao_recommendation_privacy_prerequisite.dart';
import '../../shop/services/heart_economy.dart';
import '../../shop/widgets/heart_spend_confirmation.dart';
import '../../../shared/widgets/seolleyeon_bottom_navigation_bar.dart';
import '../../chat/services/chat_service.dart';
import '../../notifications/services/notification_service.dart';
import '../models/profile_card_args.dart';
import '../services/ai_preference_performance_trace.dart';

Color _postItColor(int index) =>
    const [Color(0xFFFFF1A8), Color(0xFFF7CDD9), Color(0xFFCDE9F3)][index % 3];

// Temporary: keep the locker recommendation UI visible while the feed is
// loading or empty so the in-progress surface can be reviewed in the app.
const bool _temporarilyShowLockerPreview = true;

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
  final _storageService = StorageService();
  final _chatService = ChatService();
  final _notificationService = NotificationService();
  String? _currentUserId;

  @override
  void initState() {
    super.initState();
    _loadCurrentUser();
  }

  Future<void> _loadCurrentUser() async {
    final userId = await _storageService.getKakaoUserId();
    if (mounted) setState(() => _currentUserId = userId);
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return CupertinoPageScaffold(
      backgroundColor: isDark ? AppColorsDark.background : Colors.white,
      child: Stack(
        children: [
          const _BackgroundGradients(),
          SafeArea(
            child: Column(
              children: [
                _TopBar(
                  notificationCount: _currentUserId == null
                      ? widget.notificationCount
                      : null,
                  notificationStream: _currentUserId == null
                      ? null
                      : _notificationService.unreadNotificationCountStream(
                          _currentUserId!,
                        ),
                  onAiPreference:
                      widget.onAiPreference ??
                      () {
                        AiPreferencePerformanceTrace.markLaunchTap();
                        Navigator.of(
                          context,
                          rootNavigator: true,
                        ).pushNamed(RouteNames.aiPreference);
                      },
                  onNotification:
                      widget.onNotification ??
                      () => Navigator.of(
                        context,
                        rootNavigator: true,
                      ).pushNamed(RouteNames.notifications),
                ),
                const Expanded(child: _LockerRecommendationContent()),
              ],
            ),
          ),
          _currentUserId == null
              ? SeolleyeonBottomNavPositioned(
                  currentTab: BottomNavTab.matching,
                  onTap: widget.onNavTap,
                  showChatBadge: false,
                )
              : StreamBuilder<bool>(
                  stream: _chatService.hasAnyUnreadChats(_currentUserId!),
                  builder: (context, snapshot) => SeolleyeonBottomNavPositioned(
                    currentTab: BottomNavTab.matching,
                    onTap: widget.onNavTap,
                    showChatBadge: snapshot.data == true,
                  ),
                ),
        ],
      ),
    );
  }
}

class _BackgroundGradients extends StatelessWidget {
  const _BackgroundGradients();

  @override
  Widget build(BuildContext context) {
    return const DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFFFBF8F6), Color(0xFFFAF7F5)],
        ),
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  final int? notificationCount;
  final Stream<int>? notificationStream;
  final VoidCallback onAiPreference;
  final VoidCallback onNotification;

  const _TopBar({
    this.notificationCount,
    this.notificationStream,
    required this.onAiPreference,
    required this.onNotification,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final titleColor = isDark
        ? AppColorsDark.textPrimary
        : const Color(0xFF393236);
    return StreamBuilder<int>(
      stream: notificationStream,
      builder: (context, snapshot) {
        final count = snapshot.data ?? notificationCount ?? 0;
        return Padding(
          padding: const EdgeInsets.fromLTRB(22, 12, 22, 6),
          child: Row(
            children: [
              Icon(
                CupertinoIcons.heart_fill,
                color: Theme.of(context).colorScheme.primary,
              ),
              const SizedBox(width: 8),
              Text(
                '설레연',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 21,
                  fontWeight: FontWeight.w700,
                  color: titleColor,
                ),
              ),
              const Spacer(),
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
                        : const Color(0xFFFDF2F8),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: isDark
                          ? AppColorsDark.border
                          : const Color(0xFFFCE7F3),
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
                            : const Color(0xFFEC4899),
                      ),
                      const SizedBox(width: 4),
                      Text(
                        'AI에게 내 취향 알려주기',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                          color: titleColor,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 4),
              CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: const Size(40, 40),
                onPressed: onNotification,
                child: Stack(
                  clipBehavior: Clip.none,
                  children: [
                    Icon(
                      CupertinoIcons.bell,
                      color: isDark
                          ? AppColorsDark.textSecondary
                          : const Color(0xFF6B7280),
                    ),
                    if (count > 0)
                      Positioned(
                        top: -5,
                        right: -7,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 4,
                            vertical: 1,
                          ),
                          decoration: BoxDecoration(
                            color: Theme.of(context).colorScheme.primary,
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Text(
                            count > 9 ? '9+' : '$count',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 9,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _LockerRecommendationContent extends StatefulWidget {
  const _LockerRecommendationContent();

  @override
  State<_LockerRecommendationContent> createState() =>
      _LockerRecommendationContentState();
}

class _LockerRecommendationContentState
    extends State<_LockerRecommendationContent> {
  final _storageService = StorageService();
  final _askService = AskService();
  final _userService = UserService();
  final _aiService = AiRecommendationService();
  final _contactBlockService = ContactBlockService();
  final _heartEconomyService = HeartEconomyService();
  List<AiRecommendedProfile> _profiles = [];
  String? _userId;
  String _userNickname = '회원';
  bool _isLoading = true;
  bool _isReloading = false;
  bool _reloadRequested = false;
  bool _privacyConsentRequired = false;
  bool _recommendationLoadFailed = false;
  bool _isPaidRefreshing = false;
  String? _paidRefreshError;
  bool _isSyncingPrivacy = false;
  String? _privacySyncError;
  String? _privacyWatchedUid;
  StreamSubscription<void>? _privacySubscription;
  StreamSubscription<void>? _candidateSubscription;
  Timer? _privacyReloadDebounce;
  String _watchedCandidateKey = '';

  @override
  void initState() {
    super.initState();
    _loadRecommendations();
  }

  Future<void> _loadRecommendations() async {
    if (_isReloading) {
      _reloadRequested = true;
      return;
    }
    _isReloading = true;
    _reloadRequested = false;
    try {
      final userId = await _storageService.getKakaoUserId();
      if (userId == null || userId.isEmpty) {
        throw StateError('missing_kakao_user_id');
      }
      _watchRecommendationPrivacy(userId);
      final privacyReady = await _aiService.isViewerRecommendationPrivacyReady(
        userId,
      );
      if (!privacyReady) {
        if (!mounted) return;
        setState(() {
          _userId = userId;
          _profiles = [];
          _privacyConsentRequired = true;
          _recommendationLoadFailed = false;
          _isLoading = false;
        });
        _watchCandidateEligibility(const []);
        return;
      }
      final profiles = await _aiService.fetchMysteryFeed(
        limit: 3,
        userId: userId,
      );
      final userProfile = await _userService.getUserProfile(userId);
      final onboarding = await _storageService.getOnboardingDraft(userId);
      final nickname = userProfile?['nickname']?.toString().trim();
      if (!mounted) return;
      setState(() {
        _userId = userId;
        _profiles = profiles;
        _userNickname = nickname?.isNotEmpty == true
            ? nickname!
            : (onboarding['nickname']?.toString().trim().isNotEmpty == true
                  ? onboarding['nickname'].toString().trim()
                  : '회원');
        _privacyConsentRequired = false;
        _recommendationLoadFailed = false;
        _privacySyncError = null;
        _isLoading = false;
      });
      _watchCandidateEligibility(profiles);
      for (var index = 0; index < profiles.length; index++) {
        _logEvent(profiles[index], index, 'impression');
      }
    } catch (error) {
      debugPrint(
        '[MysteryCard] load recommendations '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
      if (mounted) {
        setState(() {
          _profiles = [];
          _privacyConsentRequired = false;
          _recommendationLoadFailed = true;
          _isLoading = false;
        });
      }
    } finally {
      _isReloading = false;
      if (_reloadRequested && mounted) {
        _reloadRequested = false;
        _privacyReloadDebounce?.cancel();
        _privacyReloadDebounce = Timer(Duration.zero, _loadRecommendations);
      }
    }
  }

  Future<void> _requestKakaoConsentAndSync() async {
    if (_isSyncingPrivacy) return;
    setState(() {
      _isSyncingPrivacy = true;
      _privacySyncError = null;
    });
    try {
      final result = await _contactBlockService.syncKakaoTalkFriendBlocks(
        requestConsentIfNeeded: true,
      );
      if (!result.recommendationPrivacyReady) {
        throw StateError('recommendation_privacy_not_ready_after_sync');
      }
      if (!mounted) return;
      setState(() {
        _privacyConsentRequired = false;
        _isLoading = true;
      });
      await _loadRecommendations();
    } catch (error) {
      debugPrint(
        '[MysteryCard] Kakao privacy sync '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
      if (!mounted) return;
      setState(() {
        _privacySyncError =
            '동의를 완료하지 못했어요. 카카오 동의 화면에서 친구목록을 허용한 뒤 다시 시도해 주세요.';
      });
    } finally {
      if (mounted) setState(() => _isSyncingPrivacy = false);
    }
  }

  Future<void> _retryRecommendations() async {
    if (!mounted) return;
    setState(() {
      _isLoading = true;
      _recommendationLoadFailed = false;
    });
    await _loadRecommendations();
  }

  Future<void> _paidRefreshRecommendations() async {
    if (_isPaidRefreshing) return;

    final confirmed = await confirmHeartSpend(
      context,
      action: '정말로 추천을 새로고침하시겠습니까?',
      amount: HeartFeatureCosts.recommendationRefresh,
    );
    if (!confirmed || !mounted) return;

    setState(() {
      _isPaidRefreshing = true;
      _paidRefreshError = null;
    });
    try {
      await _heartEconomyService.spendForRecommendationRefresh();
      if (!mounted) return;
      setState(() => _isLoading = true);
      await _loadRecommendations();
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _paidRefreshError = error.toString().contains('하트가 부족')
            ? '하트가 부족해요. 충전 후 다시 시도해주세요.'
            : '새로고침을 완료하지 못했어요.';
      });
    } finally {
      if (mounted) setState(() => _isPaidRefreshing = false);
    }
  }

  void _watchCandidateEligibility(List<AiRecommendedProfile> profiles) {
    final ids = profiles.map((profile) => profile.candidateUid).toList()
      ..sort();
    final key = ids.join('|');
    if (_watchedCandidateKey == key) return;
    _candidateSubscription?.cancel();
    _watchedCandidateKey = key;
    if (ids.isEmpty) return;
    _candidateSubscription = _aiService
        .watchCandidateRecommendationChanges(ids)
        .listen(
          (_) => _invalidateAndReloadRecommendations(),
          onError: (_) => _invalidateRecommendations(),
        );
  }

  void _invalidateRecommendations() {
    if (!mounted) return;
    setState(() {
      _profiles = [];
      _isLoading = false;
    });
  }

  void _invalidateAndReloadRecommendations() {
    if (!mounted) return;
    setState(() {
      _profiles = [];
      _isLoading = true;
    });
    _privacyReloadDebounce?.cancel();
    _privacyReloadDebounce = Timer(
      const Duration(milliseconds: 150),
      _loadRecommendations,
    );
  }

  void _watchRecommendationPrivacy(String uid) {
    if (_privacyWatchedUid == uid) return;
    _privacySubscription?.cancel();
    _privacyWatchedUid = uid;
    _privacySubscription = _aiService
        .watchRecommendationPrivacyChanges(uid)
        .listen(
          (_) {
            // Remove existing cards immediately. The server-authoritative
            // reload may take a moment, but a newly excluded friend must not
            // remain tappable while it is in flight.
            _invalidateAndReloadRecommendations();
          },
          onError: (_) {
            // A listener error is privacy-sensitive: keep the surface empty
            // until a later authoritative reload succeeds.
            _invalidateRecommendations();
          },
        );
  }

  @override
  void dispose() {
    _privacyReloadDebounce?.cancel();
    _privacySubscription?.cancel();
    _candidateSubscription?.cancel();
    super.dispose();
  }

  void _logEvent(AiRecommendedProfile profile, int index, String eventType) {
    final userId = _userId;
    if (userId == null) return;
    final contextData = <String, dynamic>{
      'screen': 'mystery_card_screen',
      'position': index,
      'interaction': 'locker_post_it',
      'algorithmVersion': profile.primaryAlgo,
    };
    if (profile.rank != 999) contextData['rank'] = profile.rank;
    if (profile.sourceScores != null) {
      contextData['score'] = profile.sourceScores;
    }
    if (profile.finalScore != null) {
      contextData['finalScore'] = profile.finalScore;
    }
    RecEventService()
        .logEvent(
          userId: userId,
          targetType: 'user_profile',
          targetId: profile.candidateUid,
          candidateUserId: profile.candidateUid,
          eventType: eventType,
          surface: 'mystery_locker',
          cardVariant: 'real_profile',
          exposureId: profile.exposureId,
          context: contextData,
        )
        .catchError(
          (error) => debugPrint(
            '[RecEvent] locker event failed: ${PrivacyLogUtils.errorSummary(error)}',
          ),
        );
  }

  void _openNote(AiRecommendedProfile profile, int index) {
    HapticFeedback.mediumImpact();
    _logEvent(profile, index, 'open');
    showGeneralDialog<void>(
      context: context,
      barrierDismissible: true,
      barrierLabel: '추천 메모 닫기',
      barrierColor: Colors.black.withValues(alpha: 0.56),
      transitionDuration: const Duration(milliseconds: 280),
      pageBuilder: (dialogContext, _, __) => _LockerNoteDialog(
        profile: profile,
        colorIndex: index,
        onViewProfile: () {
          Navigator.of(dialogContext).pop();
          Navigator.of(context, rootNavigator: true).pushNamed(
            RouteNames.profileSpecificDetail,
            arguments: ProfileCardArgs.fromAi(profile),
          );
        },
      ),
      transitionBuilder: (_, animation, __, child) => FadeTransition(
        opacity: animation,
        child: SlideTransition(
          position:
              Tween<Offset>(
                begin: const Offset(0, 0.04),
                end: Offset.zero,
              ).animate(
                CurvedAnimation(parent: animation, curve: Curves.easeOutCubic),
              ),
          child: AnimatedBuilder(
            animation: animation,
            builder: (_, child) => Transform.rotate(
              angle: (1 - animation.value) * 0.026,
              child: Transform.scale(
                scale: 0.92 + animation.value * 0.08,
                child: child,
              ),
            ),
            child: child,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final textColor = isDark
        ? AppColorsDark.textPrimary
        : const Color(0xFF111827);
    final mutedColor = isDark
        ? AppColorsDark.textSecondary
        : const Color(0xFF6B7280);
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 14, 24, 0),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFFEDE9FE),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: const Text(
                        'AI CURATED',
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF7C3AED),
                        ),
                      ),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      '$_userNickname님, 새로운 쪽지가 붙어있네요!',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 20,
                        height: 1.28,
                        fontWeight: FontWeight.w700,
                        color: textColor,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      DateFormat('MMM d', 'en_US').format(DateTime.now()),
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 13,
                        color: mutedColor,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              StreamBuilder<int>(
                stream: _userId == null
                    ? null
                    : _askService.unreadReceivedCount(_userId!),
                builder: (context, snapshot) => CupertinoButton(
                  padding: EdgeInsets.zero,
                  onPressed: () => Navigator.of(
                    context,
                    rootNavigator: true,
                  ).pushNamed(RouteNames.asksInbox),
                  child: Badge(
                    isLabelVisible: (snapshot.data ?? 0) > 0,
                    child: Icon(CupertinoIcons.tray_fill, color: mutedColor),
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Expanded(
          child: _privacyConsentRequired
              ? KakaoRecommendationPrivacyPrerequisite(
                  isWorking: _isSyncingPrivacy,
                  errorMessage: _privacySyncError,
                  onConsentAndSync: _requestKakaoConsentAndSync,
                )
              : _recommendationLoadFailed
              ? RecommendationLoadFailure(onRetry: _retryRecommendations)
              : _temporarilyShowLockerPreview &&
                    (_isLoading || _profiles.isEmpty)
              ? _LockerBoard(
                  profiles: const [],
                  onOpen: _openNote,
                  showPreviewNotes: true,
                )
              : _isLoading
              ? const Center(child: CupertinoActivityIndicator())
              : _profiles.isEmpty
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        '오늘의 추천을 모두 확인했어요.',
                        style: TextStyle(color: mutedColor),
                      ),
                      const SizedBox(height: 14),
                      CupertinoButton.filled(
                        onPressed: _isPaidRefreshing
                            ? null
                            : _paidRefreshRecommendations,
                        child: _isPaidRefreshing
                            ? const CupertinoActivityIndicator(
                                color: CupertinoColors.white,
                              )
                            : Text(
                                '새로고침 · ${HeartFeatureCosts.label(HeartFeatureCosts.recommendationRefresh)}',
                              ),
                      ),
                      if (_paidRefreshError != null) ...[
                        const SizedBox(height: 10),
                        Text(
                          _paidRefreshError!,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            color: CupertinoColors.systemRed,
                            fontSize: 13,
                          ),
                        ),
                      ],
                    ],
                  ),
                )
              : _LockerBoard(profiles: _profiles, onOpen: _openNote),
        ),
        const SizedBox(height: 104),
      ],
    );
  }
}

class _LockerBoard extends StatelessWidget {
  final List<AiRecommendedProfile> profiles;
  final void Function(AiRecommendedProfile profile, int index) onOpen;
  final bool showPreviewNotes;

  const _LockerBoard({
    required this.profiles,
    required this.onOpen,
    this.showPreviewNotes = false,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = math.min(constraints.maxWidth - 40, 355.0);
        final height = width * 1.18;
        final noteWidth = width * 0.27;
        final positions = [
          _NotePosition(top: height * 0.14, left: width * 0.07, angle: -0.061),
          _NotePosition(
            bottom: height * 0.14,
            left: width * 0.36,
            angle: 0.044,
          ),
          _NotePosition(top: height * 0.40, right: width * 0.06, angle: -0.026),
        ];
        return Center(
          child: SizedBox(
            key: const Key('locker_recommendation_board'),
            width: width,
            height: height,
            child: Stack(
              clipBehavior: Clip.none,
              children: [
                const Positioned.fill(child: _LockerCabinet()),
                for (
                  var index = 0;
                  index < profiles.length && index < positions.length;
                  index++
                )
                  _positionedNote(
                    positions[index],
                    _LockerPostIt(
                      profile: profiles[index],
                      width: noteWidth,
                      angle: positions[index].angle,
                      colorIndex: index,
                      onTap: () => onOpen(profiles[index], index),
                    ),
                  ),
                if (showPreviewNotes)
                  for (var index = 0; index < positions.length; index++)
                    _positionedNote(
                      positions[index],
                      _LockerPreviewPostIt(
                        width: noteWidth,
                        angle: positions[index].angle,
                        colorIndex: index,
                      ),
                    ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _positionedNote(_NotePosition position, Widget child) => Positioned(
    top: position.top,
    bottom: position.bottom,
    left: position.left,
    right: position.right,
    child: child,
  );
}

class _NotePosition {
  final double? top;
  final double? bottom;
  final double? left;
  final double? right;
  final double angle;
  const _NotePosition({
    this.top,
    this.bottom,
    this.left,
    this.right,
    required this.angle,
  });
}

class _LockerCabinet extends StatelessWidget {
  const _LockerCabinet();

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final frame = isDark ? const Color(0xFF65565C) : const Color(0xFFE8DDE0);
    final panel = isDark ? const Color(0xFF76666C) : const Color(0xFFF7F2F3);
    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: frame,
        borderRadius: BorderRadius.circular(18),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.11),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Row(
        children: List.generate(
          3,
          (index) => Expanded(
            child: Container(
              margin: EdgeInsets.only(right: index == 2 ? 0 : 2),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(11),
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    isDark ? const Color(0xFF87767C) : const Color(0xFFFFFFFF),
                    panel,
                  ],
                ),
                border: Border.all(color: frame.withValues(alpha: 0.7)),
              ),
              child: _LockerDoor(frame: frame),
            ),
          ),
        ),
      ),
    );
  }
}

class _LockerDoor extends StatelessWidget {
  final Color frame;
  const _LockerDoor({required this.frame});

  @override
  Widget build(BuildContext context) => Stack(
    children: [
      Positioned(
        top: 18,
        left: 13,
        right: 13,
        child: Column(
          children: List.generate(
            3,
            (_) => Container(
              height: 2,
              margin: const EdgeInsets.only(bottom: 4),
              color: frame.withValues(alpha: 0.48),
            ),
          ),
        ),
      ),
      Positioned(
        top: 58,
        left: 13,
        right: 13,
        child: Container(
          height: 14,
          decoration: BoxDecoration(
            border: Border.all(color: frame.withValues(alpha: 0.48)),
            borderRadius: BorderRadius.circular(2),
          ),
        ),
      ),
      Positioned(
        top: 92,
        right: 10,
        child: Container(
          width: 7,
          height: 28,
          decoration: BoxDecoration(
            color: const Color(0xFF88767C),
            borderRadius: BorderRadius.circular(4),
          ),
        ),
      ),
      Positioned(
        top: 3,
        left: 5,
        child: Container(
          width: 26,
          height: 4,
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.18),
            borderRadius: BorderRadius.circular(4),
          ),
        ),
      ),
    ],
  );
}

class _LockerPostIt extends StatelessWidget {
  final AiRecommendedProfile profile;
  final double width;
  final double angle;
  final int colorIndex;
  final VoidCallback onTap;

  const _LockerPostIt({
    required this.profile,
    required this.width,
    required this.angle,
    required this.colorIndex,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final color = _postItColor(colorIndex);
    return Transform.rotate(
      angle: angle,
      child: _PressableScale(
        onTap: onTap,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Container(
              width: width,
              height: width * 0.86,
              padding: const EdgeInsets.fromLTRB(10, 15, 10, 10),
              decoration: BoxDecoration(
                color: color,
                borderRadius: BorderRadius.circular(5),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.12),
                    blurRadius: 7,
                    offset: const Offset(1, 4),
                  ),
                ],
              ),
              child: const Center(
                child: Text(
                  '확인하기',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF9B596B),
                  ),
                ),
              ),
            ),
            Positioned(
              top: -7,
              left: width * 0.29,
              child: Transform.rotate(
                angle: -0.018,
                child: Container(
                  width: width * 0.40,
                  height: 14,
                  color: const Color(0xFFF6E9D2).withValues(alpha: 0.66),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LockerPreviewPostIt extends StatelessWidget {
  final double width;
  final double angle;
  final int colorIndex;

  const _LockerPreviewPostIt({
    required this.width,
    required this.angle,
    required this.colorIndex,
  });

  @override
  Widget build(BuildContext context) {
    final color = _postItColor(colorIndex);
    return Transform.rotate(
      angle: angle,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Container(
            width: width,
            height: width * 0.86,
            padding: const EdgeInsets.fromLTRB(8, 15, 8, 8),
            decoration: BoxDecoration(
              color: color,
              borderRadius: BorderRadius.circular(5),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.12),
                  blurRadius: 7,
                  offset: const Offset(1, 4),
                ),
              ],
            ),
            child: const Center(
              child: Text(
                '추천 준비 중',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF9B596B),
                ),
              ),
            ),
          ),
          Positioned(
            top: -7,
            left: width * 0.29,
            child: Transform.rotate(
              angle: -0.018,
              child: Container(
                width: width * 0.40,
                height: 14,
                color: const Color(0xFFF6E9D2).withValues(alpha: 0.66),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _PressableScale extends StatefulWidget {
  final Widget child;
  final VoidCallback onTap;
  const _PressableScale({required this.child, required this.onTap});
  @override
  State<_PressableScale> createState() => _PressableScaleState();
}

class _PressableScaleState extends State<_PressableScale> {
  bool _pressed = false;
  @override
  Widget build(BuildContext context) => GestureDetector(
    onTapDown: (_) => setState(() => _pressed = true),
    onTapCancel: () => setState(() => _pressed = false),
    onTapUp: (_) => setState(() => _pressed = false),
    onTap: widget.onTap,
    child: AnimatedSlide(
      duration: Duration(milliseconds: _pressed ? 100 : 150),
      curve: Curves.easeOut,
      offset: _pressed ? const Offset(0, 0.012) : Offset.zero,
      child: AnimatedScale(
        duration: Duration(milliseconds: _pressed ? 100 : 150),
        curve: Curves.easeOut,
        scale: _pressed ? 0.975 : 1,
        child: widget.child,
      ),
    ),
  );
}

class _LockerNoteDialog extends StatelessWidget {
  final AiRecommendedProfile profile;
  final int colorIndex;
  final VoidCallback onViewProfile;
  const _LockerNoteDialog({
    required this.profile,
    required this.colorIndex,
    required this.onViewProfile,
  });

  String _greeting() {
    const greetings = [
      '안녕, 친해지고 싶어 :)',
      '안녕, 우리 친해질래? :)',
      '안녕, 같이 이야기해 보고 싶어 :)',
    ];
    return greetings[profile.candidateUid.hashCode.abs() % greetings.length];
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final memoColor = isDark
        ? const Color(0xFF352B31)
        : _postItColor(colorIndex);
    return Dialog(
      insetPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 20),
      backgroundColor: Colors.transparent,
      child: _ReferenceMemoLayout(
        profile: profile,
        memoColor: memoColor,
        isDark: isDark,
        greeting: _greeting(),
        onClose: () => Navigator.of(context).pop(),
        onViewProfile: onViewProfile,
      ),
    );
  }
}

class _ReferenceMemoLayout extends StatelessWidget {
  final AiRecommendedProfile profile;
  final Color memoColor;
  final bool isDark;
  final String greeting;
  final VoidCallback onClose;
  final VoidCallback onViewProfile;

  const _ReferenceMemoLayout({
    required this.profile,
    required this.memoColor,
    required this.isDark,
    required this.greeting,
    required this.onClose,
    required this.onViewProfile,
  });

  @override
  Widget build(BuildContext context) {
    final mainText = isDark ? const Color(0xFFF6EEF0) : const Color(0xFF55483F);
    final subText = isDark ? const Color(0xFFD5C5CA) : const Color(0xFF78685D);
    const handwriting = TextStyle(
      fontFamily: 'LeeSeoyun',
      fontSize: 20,
      height: 1.0,
    );
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 390),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Stack(
            clipBehavior: Clip.none,
            children: [
              Container(
                width: double.infinity,
                height: 390,
                clipBehavior: Clip.antiAlias,
                decoration: BoxDecoration(
                  color: memoColor,
                  borderRadius: BorderRadius.circular(5),
                  border: Border.all(
                    color: const Color(0xFFE0A041).withValues(alpha: 0.55),
                    width: 2,
                  ),
                ),
                child: Stack(
                  children: [
                    Positioned.fill(
                      child: ColorFiltered(
                        colorFilter: ColorFilter.mode(
                          memoColor,
                          BlendMode.multiply,
                        ),
                        child: Image.asset('postit.png', fit: BoxFit.cover),
                      ),
                    ),
                    Positioned.fill(
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(24, 27, 24, 22),
                        child: Column(
                          children: [
                            for (var index = 0; index < 8; index++)
                              Expanded(
                                child: Container(
                                  alignment: Alignment.centerLeft,
                                  decoration: BoxDecoration(
                                    border: Border(
                                      bottom: BorderSide(
                                        color: mainText.withValues(alpha: 0.18),
                                        width: 0.7,
                                      ),
                                    ),
                                  ),
                                  child: _HandwrittenMemoLine(
                                    text: switch (index) {
                                      0 => greeting,
                                      2 => '나는 ${profile.name}이고,',
                                      3 => '${profile.major}에 다니고 있어.',
                                      4 =>
                                        '성격: ${profile.tags.take(2).join(', ')}',
                                      _ => '',
                                    },
                                    style: handwriting.copyWith(
                                      color: index == 4 ? subText : mainText,
                                    ),
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                    ),
                    Positioned(
                      top: 12,
                      right: 12,
                      child: CupertinoButton(
                        padding: EdgeInsets.zero,
                        minimumSize: const Size(32, 32),
                        onPressed: onClose,
                        child: Icon(
                          CupertinoIcons.xmark,
                          size: 18,
                          color: subText,
                        ),
                      ),
                    ),
                    Positioned(
                      right: 20,
                      bottom: 26,
                      child: _MemoPolaroid(profile: profile),
                    ),
                  ],
                ),
              ),
              Positioned(
                top: -7,
                left: 104,
                child: Transform.rotate(
                  angle: -0.025,
                  child: Container(
                    width: 94,
                    height: 15,
                    color: const Color(0xFFF1E3CA).withValues(alpha: 0.72),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: 214,
            height: 48,
            child: CupertinoButton(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              color: isDark ? const Color(0xFF9B6575) : const Color(0xFFC8758C),
              borderRadius: BorderRadius.circular(12),
              onPressed: onViewProfile,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    '상세 프로필 보기',
                    style: handwriting.copyWith(
                      fontSize: 20,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(width: 5),
                  const Icon(
                    CupertinoIcons.chevron_right,
                    size: 15,
                    color: Colors.white,
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

class _HandwrittenMemoLine extends StatelessWidget {
  final String text;
  final TextStyle style;

  const _HandwrittenMemoLine({required this.text, required this.style});

  @override
  Widget build(BuildContext context) =>
      Text(text, maxLines: 1, overflow: TextOverflow.ellipsis, style: style);
}

class _MemoPolaroid extends StatelessWidget {
  final AiRecommendedProfile profile;
  const _MemoPolaroid({required this.profile});

  @override
  Widget build(BuildContext context) => Transform.rotate(
    angle: 0.11,
    child: Stack(
      clipBehavior: Clip.none,
      children: [
        Container(
          width: 118,
          height: 142,
          padding: const EdgeInsets.fromLTRB(7, 7, 7, 20),
          decoration: BoxDecoration(
            color: const Color(0xFFFFFEFC),
            borderRadius: BorderRadius.circular(2),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.16),
                blurRadius: 7,
                offset: const Offset(1, 4),
              ),
            ],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(2),
            child: profile.imageUrls.isEmpty
                ? Container(
                    color: const Color(0xFFE8D9B4),
                    child: const Icon(
                      CupertinoIcons.person_fill,
                      color: Colors.white,
                      size: 42,
                    ),
                  )
                : CaptureProtectedImage(
                    imageUrl: profile.imageUrls.first,
                    fit: BoxFit.cover,
                    borderRadius: 2,
                    blurEnabled: true,
                    blurSigma: kLockedProfilePhotoBlurSigma,
                    iosSecureCaptureEnabled: true,
                    backgroundColor: const Color(0xFFE8D9B4),
                    placeholderIconColor: Colors.white,
                    placeholderIconSize: 42,
                  ),
          ),
        ),
        Positioned(
          top: -8,
          left: 34,
          child: Transform.rotate(
            angle: -0.10,
            child: Container(
              width: 50,
              height: 16,
              color: const Color(0xFFDCE9F2).withValues(alpha: 0.84),
            ),
          ),
        ),
      ],
    ),
  );
}
