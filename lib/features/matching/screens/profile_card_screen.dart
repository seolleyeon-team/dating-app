// =============================================================================
// 프로필 카드 화면 (스와이프 카드 + 하단 버튼)
// 경로: lib/features/matching/screens/profile_card_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const ProfileCardScreen()),
// );
// =============================================================================

import 'dart:async';
import 'dart:ui';
import '../../../services/campus_life_zone_repair_service.dart';
import '../../../services/contact_block_service.dart';
import '../../../shared/widgets/campus_life_zone_prerequisite.dart';
import '../../../shared/widgets/kakao_recommendation_privacy_prerequisite.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import '../../../services/storage_service.dart';
import '../../../services/interaction_service.dart';
import '../../../services/rec_event_service.dart';
import '../../../services/ai_recommendation_service.dart';
import '../../../shared/utils/privacy_log_utils.dart';
import '../../../shared/widgets/profile_photo_blur.dart';
import '../../../shared/widgets/seol_swipe_deck.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color backgroundLight = Color(0xFFF9FAFB);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color lavender50 = Color(0xFFF5F3FF);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray300 = Color(0xFFD1D5DB);
  static const Color gray500 = Color(0xFF6B7280);
  static const Color pink500 = Color(0xFFEC4899);
  static const Color rose500 = Color(0xFFF43F5E);
}

// =============================================================================
// 메인 화면
// =============================================================================
class ProfileCardScreen extends StatefulWidget {
  final VoidCallback? onLike;
  final VoidCallback? onPass;
  final VoidCallback? onShare;

  const ProfileCardScreen({super.key, this.onLike, this.onPass, this.onShare});

  @override
  State<ProfileCardScreen> createState() => _ProfileCardScreenState();
}

class _ProfileCardScreenState extends State<ProfileCardScreen>
    with TickerProviderStateMixin {
  late AnimationController _pulseController;
  final _deckController = SeolSwipeDeckController();
  final _storageService = StorageService();
  final _aiService = AiRecommendationService();
  final _contactBlockService = ContactBlockService();

  List<AiRecommendedProfile> _profiles = [];
  bool _isLoading = true;
  bool _isReloading = false;
  bool _reloadRequested = false;
  bool _needsCampusLifeZone = false;
  bool _campusLifeZoneEnforced = false;
  bool _privacyConsentRequired = false;
  bool _recommendationLoadFailed = false;
  bool _isSyncingPrivacy = false;
  String? _privacySyncError;
  String? _kakaoUserId;
  String? _privacyWatchedUid;
  StreamSubscription<void>? _privacySubscription;
  StreamSubscription<void>? _candidateSubscription;
  Timer? _privacyReloadDebounce;
  String _watchedCandidateKey = '';

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      duration: const Duration(seconds: 1),
      vsync: this,
    )..repeat(reverse: true);
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
      final kakaoUserId = await _storageService.getKakaoUserId();
      debugPrint('[ProfileCard] ${PrivacyLogUtils.idFingerprint(kakaoUserId)}');
      if (mounted) setState(() => _kakaoUserId = kakaoUserId);

      if (kakaoUserId == null || kakaoUserId.isEmpty) {
        throw StateError('missing_kakao_user_id');
      }
      _watchRecommendationPrivacy(kakaoUserId);

      final privacyReady = await _aiService.isViewerRecommendationPrivacyReady(
        kakaoUserId,
      );
      if (!privacyReady) {
        if (!mounted) return;
        setState(() {
          _profiles = [];
          _privacyConsentRequired = true;
          _recommendationLoadFailed = false;
          _isLoading = false;
        });
        _watchCandidateEligibility(const []);
        return;
      }

      final feed = await _aiService.fetchProfileFeed(
        limit: 10,
        userId: kakaoUserId,
      );
      debugPrint('[ProfileCard] 프로필 ${feed.length}개 로드 완료');

      // 생활권 정책의 rollout 상태는 서버가 정한다. 클라이언트는 따르기만 한다.
      final repairService = CampusLifeZoneRepairService();
      // 안내를 차단으로 보여줄지 정하는 값이다. 상태를 모르면(unknown)
      // 차단하지 않는다 — 실제 후보 필터링은 피드 생성 경로가
      // 문서 metadata 까지 보고 따로 판정한다.
      final enforced = await repairService.isEnforcementEnabled(
        unknownAs: false,
      );

      // ON: 피드가 비었을 때만 원인을 확인한다 (정상 피드에는 추가 read 없음).
      // OFF: 차단하지 않고 미리 설정하도록 안내만 하므로 상태를 확인한다.
      var needsZone = false;
      if (feed.isEmpty || !enforced) {
        final status = await repairService.loadStatus();
        needsZone = status?.needsRepair ?? false;
      }

      if (!mounted) return;
      setState(() {
        _profiles = feed;
        _needsCampusLifeZone = needsZone;
        _campusLifeZoneEnforced = enforced;
        _privacyConsentRequired = false;
        _recommendationLoadFailed = false;
        _privacySyncError = null;
        _isLoading = false;
      });
      _watchCandidateEligibility(feed);

      if (_profiles.isNotEmpty) {
        WidgetsBinding.instance.addPostFrameCallback(
          (_) => _recordImpressionAndOpenForTopCard(0),
        );
      }
    } catch (e) {
      debugPrint(
        '[ProfileCard] load recommendations ${PrivacyLogUtils.errorSummary(e)}',
      );
      if (mounted) {
        setState(() {
          _profiles = [];
          _recommendationLoadFailed = true;
          _privacyConsentRequired = false;
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
        '[ProfileCard] Kakao privacy sync '
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
            _invalidateAndReloadRecommendations();
          },
          onError: (_) {
            _invalidateRecommendations();
          },
        );
  }

  @override
  void dispose() {
    _privacyReloadDebounce?.cancel();
    _privacySubscription?.cancel();
    _candidateSubscription?.cancel();
    _pulseController.dispose();
    _deckController.dispose();
    super.dispose();
  }

  void _onSwiped(int index, SwipeDirection direction) {
    final uid = _kakaoUserId;
    debugPrint(
      '[ProfileCard] _onSwiped index=$index dir=$direction '
      '${PrivacyLogUtils.idFingerprint(uid)} profiles=${_profiles.length}',
    );

    if (uid == null) {
      debugPrint('[ProfileCard] ⚠️ _kakaoUserId가 null — recEvent 기록 건너뜀');
    }
    if (uid != null && index < _profiles.length) {
      final profile = _profiles[index];
      final eventType = direction == SwipeDirection.right ? 'like' : 'nope';

      final Map<String, dynamic> contextMetadata = {
        'screen': 'profile_card_screen',
        'position': index,
      };

      if (profile.rank != 999) {
        contextMetadata['rank'] = profile.rank;
      }
      if (profile.sourceScores != null) {
        contextMetadata['score'] = profile.sourceScores!;
      }
      if (profile.finalScore != null) {
        contextMetadata['finalScore'] = profile.finalScore!;
      }
      contextMetadata['algorithmVersion'] = profile.primaryAlgo;

      _logRecEvent(
        uid: uid,
        eventType: eventType,
        profile: profile,
        contextMetadata: contextMetadata,
        label: 'swipe',
      );

      final nextIndex = index + 1;
      if (nextIndex < _profiles.length) {
        _recordImpressionAndOpenForTopCard(nextIndex);
      }
    }
    if (direction == SwipeDirection.right) {
      widget.onLike?.call();
    } else {
      widget.onPass?.call();
    }
  }

  Future<void> _logRecEvent({
    required String uid,
    required String eventType,
    required AiRecommendedProfile profile,
    required Map<String, dynamic> contextMetadata,
    required String label,
  }) async {
    try {
      await RecEventService().logEvent(
        userId: uid,
        targetType: 'user_profile',
        targetId: profile.candidateUid,
        candidateUserId: profile.candidateUid,
        eventType: eventType,
        surface: 'profile_card',
        cardVariant: 'ai_profile',
        exposureId: profile.exposureId,
        context: contextMetadata,
      );
    } catch (e) {
      debugPrint(
        '[ProfileCard] recEvent $label ${PrivacyLogUtils.errorSummary(e)}',
      );
    }
  }

  void _recordImpressionAndOpenForTopCard(int cardIndex) {
    final uid = _kakaoUserId;
    if (uid == null || cardIndex >= _profiles.length) return;

    final profile = _profiles[cardIndex];

    final Map<String, dynamic> contextMetadata = {
      'screen': 'profile_card_screen',
      'position': cardIndex,
    };
    if (profile.rank != 999) {
      contextMetadata['rank'] = profile.rank;
    }
    if (profile.sourceScores != null) {
      contextMetadata['score'] = profile.sourceScores!;
    }
    if (profile.finalScore != null) {
      contextMetadata['finalScore'] = profile.finalScore!;
    }
    contextMetadata['algorithmVersion'] = profile.primaryAlgo;

    _logRecEvent(
      uid: uid,
      eventType: 'impression',
      profile: profile,
      contextMetadata: contextMetadata,
      label: 'impression',
    );
    _logRecEvent(
      uid: uid,
      eventType: 'open',
      profile: profile,
      contextMetadata: contextMetadata,
      label: 'open',
    );
  }

  void _onLike() {
    HapticFeedback.mediumImpact();
    _deckController.swipeRight();
  }

  void _onPass() {
    HapticFeedback.lightImpact();
    _deckController.swipeLeft();
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Column(
        children: [
          // 프로필 카드 스와이프 덱
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [_AppColors.lavender50, _AppColors.surfaceLight],
                ),
              ),
              child: SafeArea(
                bottom: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                  child: _isLoading
                      ? const Center(child: CupertinoActivityIndicator())
                      : _privacyConsentRequired
                      ? KakaoRecommendationPrivacyPrerequisite(
                          isWorking: _isSyncingPrivacy,
                          errorMessage: _privacySyncError,
                          onConsentAndSync: _requestKakaoConsentAndSync,
                        )
                      : _recommendationLoadFailed
                      ? RecommendationLoadFailure(
                          onRetry: _retryRecommendations,
                        )
                      : _profiles.isEmpty
                      ? (_needsCampusLifeZone && _campusLifeZoneEnforced
                            // 생활권 미설정이면 빈 화면 대신 해결 경로를 준다.
                            // (정책이 적용된 상태에서만 이게 원인이다)
                            ? CampusLifeZonePrerequisite(
                                onCompleted: _loadRecommendations,
                              )
                            : Center(
                                child: Text(
                                  '오늘의 추천이 모두 소진되었습니다.',
                                  style: TextStyle(
                                    color: _AppColors.gray500,
                                    fontFamily: 'Pretendard',
                                  ),
                                ),
                              ))
                      : Column(
                          children: [
                            // 정책 적용 전에는 추천을 막지 않고 안내만 덧붙인다.
                            if (_needsCampusLifeZone &&
                                !_campusLifeZoneEnforced)
                              CampusLifeZoneAdvisoryBanner(
                                onCompleted: _loadRecommendations,
                              ),
                            Expanded(
                              child: SeolSwipeDeck(
                                controller: _deckController,
                                onSwiped: _onSwiped,
                                cards: _profiles
                                    .map(
                                      (p) => _ProfileCard(
                                        profile: p,
                                        pulseController: _pulseController,
                                        onShare: widget.onShare,
                                        onMoreOptions: () =>
                                            _showMoreOptions(context, p),
                                      ),
                                    )
                                    .toList(),
                              ),
                            ),
                          ],
                        ),
                ),
              ),
            ),
          ),
          // 하단 액션 버튼
          Container(
            padding: EdgeInsets.fromLTRB(32, 16, 32, bottomPadding + 40),
            color: _AppColors.surfaceLight,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // Pass 버튼
                _ActionButton(
                  icon: CupertinoIcons.xmark,
                  iconColor: _AppColors.gray300,
                  hoverColor: _AppColors.rose500,
                  onPressed: _onPass,
                ),
                const SizedBox(width: 40),
                // Like 버튼
                _ActionButton(
                  icon: CupertinoIcons.heart_fill,
                  iconColor: _AppColors.pink500,
                  hoverColor: _AppColors.pink500,
                  onPressed: _onLike,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  void _showMoreOptions(BuildContext context, AiRecommendedProfile profile) {
    // 상세 프로필 팝업 / 옵션 클릭 시 detail_open 기록
    final uid = _kakaoUserId;
    if (uid != null) {
      final Map<String, dynamic> contextMetadata = {
        'screen': 'profile_card_screen',
      };
      if (profile.rank != 999) {
        contextMetadata['rank'] = profile.rank;
      }
      if (profile.sourceScores != null) {
        contextMetadata['score'] = profile.sourceScores!;
      }
      if (profile.finalScore != null) {
        contextMetadata['finalScore'] = profile.finalScore!;
      }
      contextMetadata['algorithmVersion'] = profile.primaryAlgo;

      _logRecEvent(
        uid: uid,
        eventType: 'detail_open',
        profile: profile,
        contextMetadata: contextMetadata,
        label: 'detail_open',
      );
    }

    showCupertinoModalPopup(
      context: context,
      builder: (BuildContext ctx) {
        return CupertinoActionSheet(
          actions: <CupertinoActionSheetAction>[
            CupertinoActionSheetAction(
              isDestructiveAction: true,
              onPressed: () {
                Navigator.pop(ctx);
                _showReportDialog(context, profile.candidateUid);
              },
              child: const Text(
                '신고 및 차단',
                style: TextStyle(fontFamily: 'Pretendard'),
              ),
            ),
          ],
          cancelButton: CupertinoActionSheetAction(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('취소', style: TextStyle(fontFamily: 'Pretendard')),
          ),
        );
      },
    );
  }

  void _showReportDialog(BuildContext context, String targetUserId) {
    final TextEditingController reasonController = TextEditingController();
    showCupertinoDialog(
      context: context,
      builder: (ctx) {
        bool isSubmitting = false;
        return StatefulBuilder(
          builder: (context, setState) {
            return CupertinoAlertDialog(
              title: const Text(
                '신고 및 차단',
                style: TextStyle(fontFamily: 'Pretendard'),
              ),
              content: Column(
                children: [
                  const SizedBox(height: 10),
                  const Text(
                    '이 사용자를 신고하고 추천에서 차단하시겠습니까?\n사유를 간략히 적어주세요.',
                    style: TextStyle(fontFamily: 'Pretendard'),
                  ),
                  const SizedBox(height: 16),
                  CupertinoTextField(
                    controller: reasonController,
                    placeholder: '신고 사유 입력',
                    style: const TextStyle(fontFamily: 'Pretendard'),
                    placeholderStyle: TextStyle(
                      fontFamily: 'Pretendard',
                      color: CupertinoColors.placeholderText,
                    ),
                  ),
                ],
              ),
              actions: [
                CupertinoDialogAction(
                  isDestructiveAction: true,
                  onPressed: () => Navigator.pop(ctx),
                  child: const Text(
                    '취소',
                    style: TextStyle(fontFamily: 'Pretendard'),
                  ),
                ),
                CupertinoDialogAction(
                  isDefaultAction: true,
                  onPressed: isSubmitting
                      ? null
                      : () async {
                          if (reasonController.text.isEmpty) return;
                          setState(() => isSubmitting = true);
                          try {
                            final currentUserId = _kakaoUserId;
                            if (currentUserId == null) {
                              if (ctx.mounted) Navigator.pop(ctx);
                              return;
                            }

                            await InteractionService().blockAndReportUser(
                              fromUserId: currentUserId,
                              toUserId: targetUserId,
                              reason: reasonController.text,
                            );

                            if (ctx.mounted) {
                              Navigator.pop(ctx);
                            }
                          } catch (e) {
                            setState(() => isSubmitting = false);
                            debugPrint(
                              '[ProfileCard] report ${PrivacyLogUtils.errorSummary(e)}',
                            );
                          }
                        },
                  child: isSubmitting
                      ? const CupertinoActivityIndicator()
                      : const Text(
                          '확인',
                          style: TextStyle(fontFamily: 'Pretendard'),
                        ),
                ),
              ],
            );
          },
        );
      },
    );
  }
}

// =============================================================================
// 프로필 카드
// =============================================================================
class _ProfileCard extends StatelessWidget {
  final AiRecommendedProfile profile;
  final AnimationController pulseController;
  final VoidCallback? onShare;
  final VoidCallback? onMoreOptions;

  const _ProfileCard({
    required this.profile,
    required this.pulseController,
    this.onShare,
    this.onMoreOptions,
  });

  @override
  Widget build(BuildContext context) {
    final imageUrl = profile.imageUrls.isNotEmpty
        ? profile.imageUrls.first
        : '';

    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: CupertinoColors.black,
        borderRadius: BorderRadius.circular(32),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.15),
            blurRadius: 25,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(32),
        child: Stack(
          children: [
            // 배경 이미지
            Positioned.fill(
              child: ProfilePhotoBlur(
                enabled: true,
                badgeText: '사진은 상세에서 채팅 후 선명하게 보여요',
                child: imageUrl.isNotEmpty
                    ? Image.network(
                        imageUrl,
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) =>
                            Container(color: _AppColors.gray300),
                      )
                    : Container(color: _AppColors.gray300),
              ),
            ),
            // 그라데이션 오버레이
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      CupertinoColors.black.withValues(alpha: 0.05),
                      CupertinoColors.black.withValues(alpha: 0),
                      CupertinoColors.black.withValues(alpha: 0.1),
                      CupertinoColors.black.withValues(alpha: 0.6),
                      CupertinoColors.black.withValues(alpha: 0.95),
                    ],
                    stops: const [0.0, 0.25, 0.5, 0.75, 1.0],
                  ),
                ),
              ),
            ),
            // 상단 인디케이터
            Positioned(
              top: 20,
              left: 20,
              right: 20,
              child: Row(
                children: [
                  Expanded(
                    child: Container(
                      height: 4,
                      decoration: BoxDecoration(
                        color: CupertinoColors.white,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Container(
                      height: 4,
                      decoration: BoxDecoration(
                        color: CupertinoColors.white.withValues(alpha: 0.4),
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Container(
                      height: 4,
                      decoration: BoxDecoration(
                        color: CupertinoColors.white.withValues(alpha: 0.4),
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            // 하단 콘텐츠
            Positioned(
              left: 20,
              right: 20,
              bottom: 24,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 이름 & 나이 & 공유 버튼
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.baseline,
                        textBaseline: TextBaseline.alphabetic,
                        children: [
                          Text(
                            profile.name,
                            style: const TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 32,
                              fontWeight: FontWeight.w700,
                              color: CupertinoColors.white,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            '${profile.age}',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 24,
                              fontWeight: FontWeight.w300,
                              color: CupertinoColors.white.withValues(
                                alpha: 0.95,
                              ),
                            ),
                          ),
                        ],
                      ),
                      Row(
                        children: [
                          CupertinoButton(
                            padding: EdgeInsets.zero,
                            onPressed: onShare,
                            child: ClipRRect(
                              borderRadius: BorderRadius.circular(20),
                              child: BackdropFilter(
                                filter: ImageFilter.blur(
                                  sigmaX: 12,
                                  sigmaY: 12,
                                ),
                                child: Container(
                                  padding: const EdgeInsets.all(10),
                                  decoration: BoxDecoration(
                                    color: CupertinoColors.black.withValues(
                                      alpha: 0.2,
                                    ),
                                    shape: BoxShape.circle,
                                    border: Border.all(
                                      color: CupertinoColors.white.withValues(
                                        alpha: 0.2,
                                      ),
                                    ),
                                  ),
                                  child: const Icon(
                                    CupertinoIcons.share,
                                    size: 20,
                                    color: CupertinoColors.white,
                                  ),
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          CupertinoButton(
                            padding: EdgeInsets.zero,
                            onPressed: onMoreOptions,
                            child: ClipRRect(
                              borderRadius: BorderRadius.circular(20),
                              child: BackdropFilter(
                                filter: ImageFilter.blur(
                                  sigmaX: 12,
                                  sigmaY: 12,
                                ),
                                child: Container(
                                  padding: const EdgeInsets.all(10),
                                  decoration: BoxDecoration(
                                    color: CupertinoColors.black.withValues(
                                      alpha: 0.2,
                                    ),
                                    shape: BoxShape.circle,
                                    border: Border.all(
                                      color: CupertinoColors.white.withValues(
                                        alpha: 0.2,
                                      ),
                                    ),
                                  ),
                                  child: const Icon(
                                    CupertinoIcons.ellipsis,
                                    size: 20,
                                    color: CupertinoColors.white,
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  // 라벨
                  Row(
                    children: [
                      Icon(
                        CupertinoIcons.tag,
                        size: 14,
                        color: CupertinoColors.white.withValues(alpha: 0.9),
                      ),
                      const SizedBox(width: 4),
                      Text(
                        '기본 정보 및 라이프스타일',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                          letterSpacing: 0.5,
                          color: CupertinoColors.white.withValues(alpha: 0.9),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  // 태그들
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: profile.tags.take(4).map((tag) {
                      return ClipRRect(
                        borderRadius: BorderRadius.circular(20),
                        child: BackdropFilter(
                          filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 8,
                            ),
                            decoration: BoxDecoration(
                              color: CupertinoColors.black.withValues(
                                alpha: 0.5,
                              ),
                              borderRadius: BorderRadius.circular(20),
                              border: Border.all(
                                color: CupertinoColors.white.withValues(
                                  alpha: 0.1,
                                ),
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  CupertinoIcons.tag,
                                  size: 14,
                                  color: CupertinoColors.white.withValues(
                                    alpha: 0.9,
                                  ),
                                ),
                                const SizedBox(width: 6),
                                Text(
                                  tag,
                                  style: const TextStyle(
                                    fontFamily: 'Pretendard',
                                    fontSize: 12,
                                    fontWeight: FontWeight.w500,
                                    color: CupertinoColors.white,
                                  ),
                                ),
                              ],
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
// 액션 버튼
// =============================================================================
class _ActionButton extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final Color hoverColor;
  final VoidCallback onPressed;

  const _ActionButton({
    required this.icon,
    required this.iconColor,
    required this.hoverColor,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onPressed,
      child: Container(
        width: 72,
        height: 72,
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          shape: BoxShape.circle,
          border: Border.all(color: _AppColors.gray100),
          boxShadow: [
            BoxShadow(
              color: CupertinoColors.black.withValues(alpha: 0.08),
              blurRadius: 20,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Center(child: Icon(icon, size: 36, color: iconColor)),
      ),
    );
  }
}
