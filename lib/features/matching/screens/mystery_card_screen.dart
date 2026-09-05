import 'dart:async';
import 'dart:math' as math;

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../../../core/constants/app_colors.dart';
import '../../../router/route_names.dart';
import '../../../services/ai_recommendation_service.dart';
import '../../../services/ask_service.dart';
import '../../../services/rec_event_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../../shared/constants/photo_blur_constants.dart';
import '../../../shared/utils/privacy_log_utils.dart';
import '../../../shared/widgets/capture_protected_image.dart';
import '../../../shared/widgets/campus_life_zone_prerequisite.dart';
import '../../../shared/widgets/recommendation_load_failure.dart';
import '../../../shared/widgets/seolleyeon_bottom_navigation_bar.dart';
import '../../chat/services/chat_service.dart';
import '../../notifications/services/notification_service.dart';
import '../models/profile_card_args.dart';
import '../services/ai_preference_performance_trace.dart';
import '../services/recommendation_refresh_service.dart';
import '../widgets/recommendation_refresh_dialog.dart';

Color _postItColor(int index) =>
    const [Color(0xFFFFF1A8), Color(0xFFF7CDD9), Color(0xFFCDE9F3)][index % 3];

class MysteryCardScreen extends StatefulWidget {
  final int notificationCount;
  final int remainingMatches;
  final int heartBalance;
  final VoidCallback? onAiPreference;
  final VoidCallback? onNotification;
  final VoidCallback? onSettings;
  final Function(int index)? onNavTap;

  const MysteryCardScreen({
    super.key,
    this.notificationCount = 1,
    this.remainingMatches = 2,
    this.heartBalance = 0,
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
                  heartBalance: widget.heartBalance,
                  heartBalanceStream: _currentUserId == null
                      ? null
                      : FirebaseFirestore.instance
                            .collection('users')
                            .doc(_currentUserId!)
                            .snapshots()
                            .map(
                              (snapshot) =>
                                  (snapshot.data()?['heartBalance'] as num?)
                                      ?.toInt() ??
                                  0,
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
  final int heartBalance;
  final Stream<int>? heartBalanceStream;
  final VoidCallback onAiPreference;
  final VoidCallback onNotification;

  const _TopBar({
    this.notificationCount,
    this.notificationStream,
    required this.heartBalance,
    this.heartBalanceStream,
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
              StreamBuilder<int>(
                stream: heartBalanceStream,
                initialData: heartBalance,
                builder: (context, heartSnapshot) {
                  final balance = heartSnapshot.data ?? heartBalance;
                  return Semantics(
                    label: '보유 하트 $balance개',
                    child: SizedBox(
                      width: 42,
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          CupertinoButton(
                            padding: EdgeInsets.zero,
                            minimumSize: const Size(40, 32),
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
                                        color: Theme.of(
                                          context,
                                        ).colorScheme.primary,
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
                          Transform.translate(
                            offset: const Offset(0, -3),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(
                                  CupertinoIcons.heart_fill,
                                  size: 11,
                                  color: Theme.of(context).colorScheme.primary,
                                ),
                                const SizedBox(width: 2),
                                Text(
                                  '$balance',
                                  key: const Key('main_heart_balance'),
                                  style: TextStyle(
                                    fontFamily: 'Pretendard',
                                    fontSize: 11,
                                    fontWeight: FontWeight.w700,
                                    color: isDark
                                        ? AppColorsDark.textSecondary
                                        : const Color(0xFF6B7280),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                },
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
  final _refreshService = RecommendationRefreshService();

  /// 필터 통과한 후보 rank 순 (최대 window 2개 분량 = 6명).
  List<AiRecommendedProfile> _eligibleProfiles = [];
  List<AiRecommendedProfile> _profiles = [];
  bool _isRefreshedWindow = false;
  bool _isPurchasingRefresh = false;
  String? _feedDateKey;
  String? _userId;
  String _userNickname = '회원';
  bool _isLoading = true;
  bool _isReloading = false;
  bool _reloadRequested = false;
  bool _recommendationLoadFailed = false;
  RecommendationFeedStatus _feedStatus = RecommendationFeedStatus.notGenerated;
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
      final firebaseUserId = FirebaseAuth.instance.currentUser?.uid.trim();
      final cachedUserId = (await _storageService.getKakaoUserId())?.trim();
      if (firebaseUserId == null || firebaseUserId.isEmpty) {
        if (!mounted) return;
        setState(() {
          _profiles = [];
          _eligibleProfiles = [];
          _feedDateKey = null;
          _feedStatus = RecommendationFeedStatus.signedOut;
          _recommendationLoadFailed = false;
          _isLoading = false;
        });
        return;
      }
      // SharedPreferences는 UX 캐시일 뿐 인증 근거가 아니다. 오래된 캐시가
      // 남아 있더라도 Firebase Auth uid를 canonical id로 사용한다.
      if (cachedUserId != firebaseUserId) {
        await _storageService.saveAppUserId(firebaseUserId);
      }
      final userId = firebaseUserId;
      _watchRecommendationPrivacy(userId);
      // initial(1~3위)과 refreshed(4~6위) window 를 한 번에 hydrate 한다.
      final feedResult = await _aiService.fetchMysteryFeedResult(
        limit: RecommendationRefreshService.windowSize * 2,
        userId: userId,
      );
      final eligibleProfiles = feedResult.profiles;
      // 유료 새로고침 자격은 서버(entitlement 문서)가 source of truth 다.
      // 앱을 껐다 켜도 같은 dateKey 면 결제 시점에 확정된 3명이 복원된다.
      final dateKey = feedResult.dateKey;
      final entitlement = dateKey != null
          ? await _refreshService.fetchEntitlement(userId, dateKey)
          : null;
      final refreshed = entitlement?.completed == true;
      final purchasedUids = refreshed
          ? entitlement!.displayCandidateUids
          : const <String>[];
      final profiles =
          RecommendationRefreshService.selectDisplayedRecommendations(
            eligibleProfiles,
            refreshed: refreshed,
            purchasedCandidateUids: purchasedUids,
          );
      final displayStatus =
          profiles.isEmpty &&
              feedResult.status == RecommendationFeedStatus.ready
          ? RecommendationFeedStatus.noEligibleCandidates
          : feedResult.status;
      final userProfile = await _userService.getUserProfile(userId);
      final onboarding = await _storageService.getOnboardingDraft(userId);
      final nickname = userProfile?['nickname']?.toString().trim();
      if (!mounted) return;
      setState(() {
        _userId = userId;
        _eligibleProfiles = eligibleProfiles;
        _profiles = profiles;
        _isRefreshedWindow = refreshed;
        _feedDateKey = dateKey;
        _feedStatus = displayStatus;
        _userNickname = nickname?.isNotEmpty == true
            ? nickname!
            : (onboarding['nickname']?.toString().trim().isNotEmpty == true
                  ? onboarding['nickname'].toString().trim()
                  : '회원');
        _recommendationLoadFailed = false;
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
          _eligibleProfiles = [];
          _feedDateKey = null;
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

  Future<void> _retryRecommendations() async {
    if (!mounted) return;
    setState(() {
      _isLoading = true;
      _recommendationLoadFailed = false;
    });
    await _loadRecommendations();
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
      _eligibleProfiles = [];
      _feedDateKey = null;
      _feedStatus = RecommendationFeedStatus.noEligibleCandidates;
      _isLoading = false;
    });
  }

  void _invalidateAndReloadRecommendations() {
    if (!mounted) return;
    setState(() {
      _profiles = [];
      _eligibleProfiles = [];
      _feedDateKey = null;
      _feedStatus = RecommendationFeedStatus.notGenerated;
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
    // 새로고침 구매 자체는 취향 신호가 아니므로 recEvents 에 남기지 않는다.
    // 노출된 카드의 impression/open 은 기존 흐름 그대로 기록한다.
    //
    // position semantics (기존 계약 유지 + 명시 필드 추가):
    //  - position:     0-based 화면 슬롯. 이 화면의 기존 의미 그대로다
    //                  (recsys/훈련 export 는 context 를 읽지 않는 것을 확인함).
    //  - displaySlot:  position 과 같은 값. 이름으로 의미를 못박는다.
    //  - eligibleIndex: 필터 통과 후보 순서에서의 위치 (initial 0~2,
    //                  refreshed 는 보통 3~5).
    //  - rank:         아래에서 추가되는 원본 model rank (재번호 없음).
    final eligibleIndex = _eligibleProfiles.indexWhere(
      (candidate) => candidate.candidateUid == profile.candidateUid,
    );
    final contextData = <String, dynamic>{
      'screen': 'mystery_card_screen',
      'position': index,
      'displaySlot': index,
      if (eligibleIndex >= 0) 'eligibleIndex': eligibleIndex,
      'recommendationWindow': _isRefreshedWindow ? 'refreshed' : 'initial',
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

  Future<void> _onRefreshPressed() async {
    if (_isPurchasingRefresh) return;
    HapticFeedback.selectionClick();
    if (_isRefreshedWindow) {
      // v1: 하루 추천 세트당 1회. 두 번째 결제 CTA 는 노출하지 않는다.
      await _showRefreshNotice(
        '오늘의 추천을 이미 새로고침했어요.',
        '다음 추천이 준비되면 다시 이용할 수 있어요.',
      );
      return;
    }
    final dateKey = _feedDateKey;
    if (dateKey == null ||
        _eligibleProfiles.length <
            RecommendationRefreshService.windowSize * 2) {
      // UX precheck: 표시 가능한 후보가 6명(1~3위 + 4~6위) 미만이면 결제 UI
      // 자체를 열지 않는다. 단 이 검사는 authoritative 하지 않다 — 실제 결제
      // 가부는 서버가 결제 commit 트랜잭션 안에서 3명의 eligibility 를
      // 재검증해 최종 결정한다.
      await _showRefreshNotice(
        '새로고침 안내',
        '새로고침할 추천을 준비하지 못했어요. 잠시 후 다시 시도해주세요.',
      );
      return;
    }
    final result =
        await showCupertinoDialog<RecommendationRefreshPurchaseResult>(
          context: context,
          builder: (_) => RecommendationRefreshDialog(
            onPurchase: () => _purchaseRefresh(dateKey),
          ),
        );
    if (!mounted || result == null) return;
    await _handleRefreshPurchaseResult(result);
  }

  Future<RecommendationRefreshPurchaseResult> _purchaseRefresh(
    String dateKey,
  ) async {
    setState(() => _isPurchasingRefresh = true);
    try {
      // Heart 차감/자격 발급은 전부 서버 트랜잭션. optimistic UI 금지 —
      // 화면 전환은 서버 성공 응답 이후에만 일어난다.
      return await _refreshService.purchaseRefresh(
        expectedDateKey: dateKey,
        expectedAlgo: _eligibleProfiles.isNotEmpty
            ? _eligibleProfiles.first.primaryAlgo
            : null,
      );
    } finally {
      if (mounted) setState(() => _isPurchasingRefresh = false);
    }
  }

  Future<void> _handleRefreshPurchaseResult(
    RecommendationRefreshPurchaseResult result,
  ) async {
    switch (result.status) {
      case RecommendationRefreshStatus.purchased:
      case RecommendationRefreshStatus.alreadyPurchased:
        _applyRefreshedWindow(result.displayCandidateUids);
      case RecommendationRefreshStatus.insufficientHearts:
        await _showInsufficientHeartsDialog();
      case RecommendationRefreshStatus.staleFeed:
        // 결제 시점에 추천 세트가 교체됐다(차감 없음). 새 세트를 다시 불러온다.
        await _showRefreshNotice('새로고침 안내', '추천이 새로 준비되어 화면을 다시 불러왔어요.');
        if (mounted) _invalidateAndReloadRecommendations();
      case RecommendationRefreshStatus.staleEligibility:
        // 결제 commit 직전 서버 재검증에서 유료 노출 후보의 상태 변경이
        // 감지됐다(차감 없음). 피드를 다시 불러와 구매 가능 여부를 재계산한다.
        await _showRefreshNotice(
          '새로고침 안내',
          '추천 상태가 방금 바뀌어 결제를 진행하지 않았어요. 최신 추천을 다시 불러올게요.',
        );
        if (mounted) _invalidateAndReloadRecommendations();
      case RecommendationRefreshStatus.unavailable:
        await _showRefreshNotice(
          '새로고침 안내',
          '새로고침할 추천을 준비하지 못했어요. 잠시 후 다시 시도해주세요.',
        );
    }
  }

  void _applyRefreshedWindow(List<String> purchasedCandidateUids) {
    final profiles =
        RecommendationRefreshService.selectDisplayedRecommendations(
          _eligibleProfiles,
          refreshed: true,
          purchasedCandidateUids: purchasedCandidateUids,
        );
    setState(() {
      _isRefreshedWindow = true;
      _profiles = profiles;
    });
    _watchCandidateEligibility(profiles);
    for (var index = 0; index < profiles.length; index++) {
      _logEvent(profiles[index], index, 'impression');
    }
  }

  Future<void> _showInsufficientHeartsDialog() async {
    if (!mounted) return;
    await showCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text('하트가 부족해요'),
        content: Text(
          '추천 새로고침에는 하트 '
          '${RecommendationRefreshService.costHearts}개가 필요해요.',
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('취소'),
          ),
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () {
              Navigator.of(dialogContext).pop();
              // 기존 하트 충전 flow 재사용. 충전 후 다시 새로고침을 시도할 수
              // 있다.
              Navigator.of(
                context,
                rootNavigator: true,
              ).pushNamed(RouteNames.heartCharge);
            },
            child: const Text('하트 충전하기'),
          ),
        ],
      ),
    );
  }

  Future<void> _showRefreshNotice(String title, String message) async {
    if (!mounted) return;
    await showCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('확인'),
          ),
        ],
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
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  CupertinoButton(
                    key: const Key('one_to_one_refresh_button'),
                    padding: EdgeInsets.zero,
                    minimumSize: const Size(40, 40),
                    onPressed: _onRefreshPressed,
                    child: Semantics(
                      label: '오늘의 추천 새로고침',
                      button: true,
                      child: Icon(
                        CupertinoIcons.arrow_clockwise,
                        color: _isRefreshedWindow
                            ? mutedColor.withValues(alpha: 0.35)
                            : mutedColor,
                      ),
                    ),
                  ),
                  const SizedBox(width: 2),
                  Semantics(
                    label: '받은 하트',
                    button: true,
                    child: CupertinoButton(
                      padding: EdgeInsets.zero,
                      minimumSize: const Size(40, 40),
                      onPressed: () {
                        HapticFeedback.lightImpact();
                        Navigator.of(
                          context,
                          rootNavigator: true,
                        ).pushNamed(RouteNames.receivedHearts);
                      },
                      child: Icon(
                        CupertinoIcons.heart_fill,
                        size: 22,
                        color: Theme.of(context).colorScheme.primary,
                      ),
                    ),
                  ),
                  const SizedBox(width: 2),
                  StreamBuilder<int>(
                    stream: _userId == null
                        ? null
                        : _askService.unreadReceivedCount(_userId!),
                    builder: (context, snapshot) => Semantics(
                      label: '무물함',
                      button: true,
                      child: CupertinoButton(
                        padding: EdgeInsets.zero,
                        minimumSize: const Size(40, 40),
                        onPressed: () => Navigator.of(
                          context,
                          rootNavigator: true,
                        ).pushNamed(RouteNames.asksInbox),
                        child: Badge(
                          isLabelVisible: (snapshot.data ?? 0) > 0,
                          child: Icon(
                            CupertinoIcons.tray_fill,
                            color: mutedColor,
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
        const SizedBox(height: 12),
        Expanded(
          child: _recommendationLoadFailed
              ? RecommendationLoadFailure(onRetry: _retryRecommendations)
              : _isLoading
              ? const Center(child: CupertinoActivityIndicator())
              : _profiles.isEmpty
              ? _RecommendationEmptyState(
                  status: _feedStatus,
                  mutedColor: mutedColor,
                  onRetry: _retryRecommendations,
                  onCampusLifeZoneCompleted: _retryRecommendations,
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
  const _LockerBoard({required this.profiles, required this.onOpen});

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

class _RecommendationEmptyState extends StatelessWidget {
  const _RecommendationEmptyState({
    required this.status,
    required this.mutedColor,
    required this.onRetry,
    required this.onCampusLifeZoneCompleted,
  });

  final RecommendationFeedStatus status;
  final Color mutedColor;
  final Future<void> Function() onRetry;
  final Future<void> Function() onCampusLifeZoneCompleted;

  @override
  Widget build(BuildContext context) {
    if (status == RecommendationFeedStatus.campusLifeZoneRequired) {
      return CampusLifeZonePrerequisite(onCompleted: onCampusLifeZoneCompleted);
    }

    final (title, description, showRetry) = switch (status) {
      RecommendationFeedStatus.signedOut => (
        '로그인이 필요해요.',
        '다시 로그인하면 오늘의 추천을 확인할 수 있어요.',
        false,
      ),
      RecommendationFeedStatus.notGenerated => (
        '오늘의 추천을 준비하고 있어요.',
        '추천 생성이 완료되면 이곳에 새로운 쪽지가 도착해요.',
        true,
      ),
      RecommendationFeedStatus.noEligibleCandidates => (
        '오늘 소개할 수 있는 인연을 찾지 못했어요.',
        '새로운 인연이 준비되면 다시 알려드릴게요.',
        true,
      ),
      _ => ('오늘의 추천을 확인할 수 없어요.', '잠시 후 다시 시도해주세요.', true),
    };

    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              title,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: mutedColor,
                fontSize: 16,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              description,
              textAlign: TextAlign.center,
              style: TextStyle(color: mutedColor, height: 1.5),
            ),
            if (showRetry) ...[
              const SizedBox(height: 16),
              CupertinoButton(onPressed: onRetry, child: const Text('다시 확인')),
            ],
          ],
        ),
      ),
    );
  }
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
