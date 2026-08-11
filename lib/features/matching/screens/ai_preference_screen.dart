// =============================================================================
// AI 취향 알려주기 — Full-Screen Immersive 3-Shot Photo Preference UI
//
// 경로: lib/features/matching/screens/ai_preference_screen.dart
//
// 각 AI identity(face_card · vibe_card · silhouette_card)를 full-screen으로
// 보여주고, side-tap navigation / swipe or button decision으로 취향 학습.
//
// • SeolSwipeDeck은 ai_match_card_screen·profile_card_screen이 사용하므로
//   이 화면에서는 동일 animation parameter를 inline으로 사용.
// • DecisionTracker / recEvent / Storage 서비스는 기존 그대로 보존.
// =============================================================================

import 'dart:async';
import 'dart:math' as math;

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:uuid/uuid.dart';

import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_typography.dart';
import '../models/ai_preference_models.dart';
import '../services/ai_preference_deck.dart';
import '../services/ai_preference_loading_coordinator.dart';
import '../services/ai_preference_performance_trace.dart';
import '../services/ai_profile_catalog_service.dart';
import '../services/ai_profile_storage_service.dart';
import '../widgets/ai_preference_progressive_blur_surface.dart';
import '../../../services/rec_event_service.dart';
import '../../../services/rec_event_contract.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../../shared/utils/privacy_log_utils.dart';

// ─── Private swipe direction ────────────────────────────────────────────────
enum _SwipeDir { left, right }

// =============================================================================
// Widget
// =============================================================================

/// AI 취향 알려주기 화면 — Immersive 3-Shot Preference UI
class AiPreferenceScreen extends StatefulWidget {
  const AiPreferenceScreen({super.key});

  @override
  State<AiPreferenceScreen> createState() => _AiPreferenceScreenState();
}

// =============================================================================
// State
// =============================================================================

class _AiPreferenceScreenState extends State<AiPreferenceScreen>
    with TickerProviderStateMixin {
  // ═══════════════════════════════════════════════════════════════════════════
  // Constants
  // ═══════════════════════════════════════════════════════════════════════════

  // ── Swipe animation (exact match: SeolSwipeDeck) ──
  static const double _maxRotationDeg = 15.0;
  static const double _distanceThresholdRatio = 0.22;
  static const double _velocityThreshold = 800.0;
  static const Duration _flyDuration = Duration(milliseconds: 300);
  static const Duration _snapDuration = Duration(milliseconds: 400);

  // ── Tap / navigation ──
  static const double _tapDistanceThreshold = 10.0;
  static const double _leftTapZoneRatio = 0.38;
  static const double _rightTapZoneStart = 0.62;
  static const Duration _postSwipeTapCooldown = Duration(milliseconds: 300);

  // ═══════════════════════════════════════════════════════════════════════════
  // Services
  // ═══════════════════════════════════════════════════════════════════════════

  final _firestore = FirebaseFirestore.instance;
  final _rng = math.Random.secure();

  final _storageService = StorageService();
  final _aiProfileStorageService = AiProfileStorageService();
  final _aiProfileCatalogService = AiProfileCatalogService();
  final _userService = UserService();
  final _recEventService = RecEventService();
  final _uuid = const Uuid();
  late final String _aiPreferenceSessionId = _uuid.v4();
  late final AiPreferenceLoadingCoordinator _loadingCoordinator;
  late final AiPreferencePerformanceTrace _performanceTrace;

  // ═══════════════════════════════════════════════════════════════════════════
  // User / pool state
  // ═══════════════════════════════════════════════════════════════════════════

  String? _kakaoUserId;
  final Map<String, String?> _heightTagCacheById = {};
  final Map<String, String> _heightDebugCacheById = {};

  // ═══════════════════════════════════════════════════════════════════════════
  // Identity deck
  // ═══════════════════════════════════════════════════════════════════════════

  final List<_IdentityBundle> _identities = [];
  int _currentIdentityIndex = 0;

  // ═══════════════════════════════════════════════════════════════════════════
  // Shot navigation & decision state (per current identity)
  // ═══════════════════════════════════════════════════════════════════════════

  int _currentShotIndex = 0;

  // ═══════════════════════════════════════════════════════════════════════════
  // Loading state
  // ═══════════════════════════════════════════════════════════════════════════

  bool _loading = true;
  bool _loadingNextIdentity = false;
  bool _firstImageFrameReported = false;

  // ═══════════════════════════════════════════════════════════════════════════
  // Swipe animation state
  // ═══════════════════════════════════════════════════════════════════════════

  late AnimationController _flyController;
  late AnimationController _snapController;
  Animation<Offset>? _flyAnimation;
  Animation<Offset>? _snapAnimation;
  Offset _dragOffset = Offset.zero;
  bool _isAnimating = false;
  Offset? _panStartGlobal;
  double _panTotalDistance = 0;
  _SwipeDir? _pendingFlyDir;
  String? _pendingFlyIdentityId;
  DateTime? _lastSwipeTime;

  // ═══════════════════════════════════════════════════════════════════════════
  // Image provider cache (foreground + background share same provider)
  // ═══════════════════════════════════════════════════════════════════════════

  final Map<String, ImageProvider> _imageProviders = {};

  // ═══════════════════════════════════════════════════════════════════════════
  // Lifecycle
  // ═══════════════════════════════════════════════════════════════════════════

  @override
  void initState() {
    super.initState();
    _performanceTrace = AiPreferencePerformanceTrace.begin();
    _loadingCoordinator = AiPreferenceLoadingCoordinator(
      catalogService: _aiProfileCatalogService,
      storageService: _aiProfileStorageService,
      random: _rng,
      deckBuilder: AiPreferenceDeckBuilder(random: _rng),
    );
    _flyController = AnimationController(vsync: this, duration: _flyDuration);
    _snapController = AnimationController(vsync: this, duration: _snapDuration);
    _flyController.addStatusListener(_onFlyComplete);
    _snapController.addStatusListener(_onSnapComplete);
    _init();
  }

  @override
  void dispose() {
    _flyController.removeStatusListener(_onFlyComplete);
    _snapController.removeStatusListener(_onSnapComplete);
    _flyController.dispose();
    _snapController.dispose();
    super.dispose();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Initialisation
  // ═══════════════════════════════════════════════════════════════════════════

  Future<void> _init() async {
    setState(() => _loading = true);

    final kakaoUserId = await _storageService.getKakaoUserId();
    _kakaoUserId = kakaoUserId;
    debugPrint('[AI_PREF] ${PrivacyLogUtils.idFingerprint(kakaoUserId)}');

    String? gender;
    if (kakaoUserId != null && kakaoUserId.isNotEmpty) {
      final profile = await _userService.getUserProfile(kakaoUserId);
      gender = _extractGender(profile);
      gender ??= await _extractGenderFromOnboardingDraft(kakaoUserId);
    }

    if (!mounted) return;
    final targetGender = _decideTargetGender(gender);
    if (targetGender == null) {
      setState(() => _loading = false);
      return;
    }

    try {
      final catalog = await _loadingCoordinator.initialize(
        targetGender: targetGender,
      );
      _performanceTrace.logCatalog(catalog);

      final first = await _loadingCoordinator.loadNextIdentity();
      if (!mounted) return;
      _identities.clear();
      if (first != null) {
        _identities.add(_IdentityBundle.fromLoaded(first.identity));
        _performanceTrace.logFirstIdentity(first);
      }
    } catch (error) {
      debugPrint(
        '[AI_PREF] initialization failed '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
    }

    if (!mounted) return;
    setState(() => _loading = false);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Gender helpers (unchanged from original)
  // ═══════════════════════════════════════════════════════════════════════════

  String? _extractGender(Map<String, dynamic>? profile) {
    if (profile == null) return null;
    final direct = profile['gender']?.toString();
    if (direct != null && direct.trim().isNotEmpty) return direct.trim();

    final onboarding = profile['onboarding'];
    if (onboarding is Map) {
      final gAtOnboarding = onboarding['gender']?.toString();
      if (gAtOnboarding != null && gAtOnboarding.trim().isNotEmpty) {
        return gAtOnboarding.trim();
      }
      final basicInfo = onboarding['basicInfo'];
      if (basicInfo is Map) {
        final g = basicInfo['gender']?.toString();
        if (g != null && g.trim().isNotEmpty) return g.trim();
      }
    }
    return null;
  }

  Future<String?> _extractGenderFromOnboardingDraft(String kakaoUserId) async {
    final draft = await _storageService.getOnboardingDraft(kakaoUserId);
    final basicInfo = draft['basicInfo'];
    if (basicInfo is Map) {
      final g = basicInfo['gender']?.toString();
      if (g != null && g.trim().isNotEmpty) return g.trim();
    }
    final g2 = draft['gender']?.toString();
    if (g2 != null && g2.trim().isNotEmpty) return g2.trim();
    return null;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Target pool (unchanged from original)
  // ═══════════════════════════════════════════════════════════════════════════

  String? _decideTargetGender(String? userGender) {
    final raw = (userGender ?? '').trim();
    final normalized = raw.toLowerCase();
    final isMale =
        normalized == 'male' ||
        normalized == 'm' ||
        raw == '남성' ||
        raw == '남자' ||
        normalized == 'man';
    final isFemale =
        normalized == 'female' ||
        normalized == 'f' ||
        raw == '여성' ||
        raw == '여자' ||
        normalized == 'woman';

    if (isMale) {
      return 'female';
    }
    if (isFemale) {
      return 'male';
    }

    debugPrint('[AI_PREF] gender unknown — refusing random pool fallback');
    return null;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Height tag (unchanged from original)
  // ═══════════════════════════════════════════════════════════════════════════

  Future<_HeightFetchResult> _fetchHeightForProfileId(String profileId) async {
    try {
      final cached = _heightTagCacheById[profileId];
      if (cached != null) {
        return _HeightFetchResult(
          tag: cached,
          debug: _heightDebugCacheById[profileId] ?? 'cache',
        );
      }

      final snap = await _firestore
          .collection('ai_profiles')
          .doc(profileId)
          .get();
      if (!snap.exists) {
        _heightDebugCacheById[profileId] = 'not-found';
        return const _HeightFetchResult(tag: null, debug: 'not-found');
      }
      final data = snap.data();
      final metadata =
          data?['metadata'] ??
          data?['metaRaw'] ??
          data?['metaRAW'] ??
          data?['meta_raw'];

      String? rawHeight = data?['height']?.toString();
      rawHeight ??= _extractHeightFromMetadata(metadata);

      final tag = _normalizeHeightTag(rawHeight);
      if (tag != null) {
        _heightTagCacheById[profileId] = tag;
        _heightDebugCacheById[profileId] = 'ok';
        return const _HeightFetchResult(
          tag: null,
          debug: 'ok',
        ).copyWith(tag: tag);
      }

      if (metadata == null) {
        _heightDebugCacheById[profileId] = 'no-metadata';
      } else if (rawHeight == null) {
        _heightDebugCacheById[profileId] = 'no-height';
      } else {
        _heightDebugCacheById[profileId] = 'parse-fail';
      }
      return _HeightFetchResult(
        tag: null,
        debug: _heightDebugCacheById[profileId]!,
      );
    } on FirebaseException catch (e) {
      final d = 'fs-${e.code}';
      _heightDebugCacheById[profileId] = d;
      debugPrint(
        '[AI_PREF] height load failed '
        '${PrivacyLogUtils.idFingerprint(profileId)} '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
      return _HeightFetchResult(tag: null, debug: d);
    } catch (e) {
      debugPrint(
        '[AI_PREF] height parse failed '
        '${PrivacyLogUtils.idFingerprint(profileId)} '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
      _heightDebugCacheById[profileId] = 'err';
      return const _HeightFetchResult(tag: null, debug: 'err');
    }
  }

  String? _extractHeightFromMetadata(dynamic metadata) {
    if (metadata == null) return null;
    if (metadata is Map) {
      final v = metadata['height'] ?? metadata['Height'] ?? metadata['HEIGHT'];
      return v?.toString();
    }
    if (metadata is String) {
      return _extractHeightFromMetadataString(metadata);
    }
    return _extractHeightFromMetadataString(metadata.toString());
  }

  String? _extractHeightFromMetadataString(String metadata) {
    final heightDigitsFromKey = RegExp(
      r'''["']height["']\s*:\s*["']\s*([0-9]{2,3})\s*(?:cm)?''',
      caseSensitive: false,
    ).firstMatch(metadata);
    if (heightDigitsFromKey != null) return heightDigitsFromKey.group(1);

    final heightDigitsFromKeyNoQuotes = RegExp(
      r'''["']height["']\s*:\s*([0-9]{2,3})\s*(?:cm)?''',
      caseSensitive: false,
    ).firstMatch(metadata);
    if (heightDigitsFromKeyNoQuotes != null) {
      return heightDigitsFromKeyNoQuotes.group(1);
    }

    final cm = RegExp(
      r'([0-9]{2,3})\s*cm',
      caseSensitive: false,
    ).firstMatch(metadata);
    if (cm != null) return cm.group(1);

    return null;
  }

  String? _normalizeHeightTag(String? rawHeight) {
    if (rawHeight == null) return null;
    final trimmed = rawHeight.trim();
    if (trimmed.isEmpty || trimmed.toLowerCase() == 'none') return null;

    final digits = RegExp(r'(\d{2,3})').firstMatch(trimmed)?.group(1);
    final parsed = digits == null ? null : int.tryParse(digits);
    if (parsed != null) {
      return '${parsed.toString().padLeft(3, '0')}cm';
    }
    return null;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Identity loading
  // ═══════════════════════════════════════════════════════════════════════════

  void _onFirstImageFrame() {
    if (_firstImageFrameReported) return;
    _firstImageFrameReported = true;
    _performanceTrace.logFirstPaint(
      storageMetrics: _aiProfileStorageService.metrics,
      invalidIdentityCount: _loadingCoordinator.invalidIdentityCount,
    );
    unawaited(_prepareVisibleWindow());
  }

  Future<void> _prepareVisibleWindow() async {
    final current = _currentBundle;
    final tasks = <Future<void>>[];
    if (current != null) {
      tasks
        ..add(_hydrateIdentity(current))
        ..add(_hydrateHeight(current));
    }
    if (_currentIdentityIndex + 1 >= _identities.length) {
      tasks.add(_appendNextIdentity());
    }
    await Future.wait(tasks);
  }

  Future<void> _appendNextIdentity() async {
    if (_loadingNextIdentity ||
        _currentIdentityIndex + 1 < _identities.length) {
      return;
    }

    _loadingNextIdentity = true;
    if (mounted) setState(() {});
    try {
      final next = await _loadingCoordinator.loadNextIdentity();
      if (!mounted || next == null) return;
      final bundle = _IdentityBundle.fromLoaded(next.identity);
      _identities.add(bundle);
      _precacheResolvedShots(bundle);
    } catch (error) {
      debugPrint(
        '[AI_PREF] next identity load failed '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
    } finally {
      _loadingNextIdentity = false;
      if (mounted) setState(() {});
    }
  }

  Future<void> _hydrateIdentity(_IdentityBundle bundle) async {
    if (bundle.hydrationStarted) return;
    bundle.hydrationStarted = true;
    try {
      final hydrated = await _loadingCoordinator.hydrateRemaining(
        bundle.toLoadedIdentity(),
      );
      if (!mounted) return;
      bundle.applyLoadedIdentity(hydrated);
      _precacheResolvedShots(bundle);
      setState(() {});
    } catch (error) {
      bundle.hydrationStarted = false;
      debugPrint(
        '[AI_PREF] shot prefetch failed '
        '${PrivacyLogUtils.idFingerprint(bundle.identityId)} '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
    }
  }

  Future<void> _hydrateHeight(_IdentityBundle bundle) async {
    if (bundle.heightLoadStarted) return;
    bundle.heightLoadStarted = true;
    final result = await _fetchHeightForProfileId(bundle.profileId);
    if (!mounted) return;
    bundle.applyHeight(result);
    setState(() {});
  }

  Future<void> _resolveShotOnDemand(
    _IdentityBundle bundle,
    int shotIndex,
  ) async {
    final shot = bundle.shots[shotIndex];
    if (shot.imageUrl != null || !bundle.resolvingShots.add(shot.shotType)) {
      return;
    }
    try {
      final resolved = await _loadingCoordinator.resolveShot(
        bundle.toLoadedIdentity(),
        shotIndex,
      );
      if (!mounted) return;
      bundle.applyLoadedIdentity(resolved);
      final url = bundle.shots[shotIndex].imageUrl;
      if (url == null || url.isEmpty) {
        bundle.failedShots.add(shot.shotType);
      }
      setState(() {});
    } catch (error) {
      debugPrint(
        '[AI_PREF] shot load failed '
        '${PrivacyLogUtils.idFingerprint(bundle.identityId)} '
        '${PrivacyLogUtils.errorSummary(error)}',
      );
    } finally {
      bundle.resolvingShots.remove(shot.shotType);
    }
  }

  void _precacheResolvedShots(_IdentityBundle bundle) {
    if (!mounted) return;
    for (final shot in bundle.shots) {
      final url = shot.imageUrl;
      if (url != null && url.isNotEmpty) {
        unawaited(precacheImage(_getImageProvider(url), context));
      }
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Current identity helpers
  // ═══════════════════════════════════════════════════════════════════════════

  _IdentityBundle? get _currentBundle {
    if (_currentIdentityIndex >= _identities.length) return null;
    return _identities[_currentIdentityIndex];
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Shot navigation (NO decision)
  // ═══════════════════════════════════════════════════════════════════════════

  void _navigateToShot(int newIndex) {
    if (newIndex < 0 || newIndex >= 3) return;
    if (newIndex == _currentShotIndex) return;
    if (_isAnimating) return;
    final bundle = _currentBundle;
    if (bundle == null || bundle.decisionGate.isTerminal) return;
    if (_lastSwipeTime != null &&
        DateTime.now().difference(_lastSwipeTime!) < _postSwipeTapCooldown) {
      return;
    }

    setState(() => _currentShotIndex = newIndex);
    if (bundle.shots[newIndex].imageUrl == null) {
      unawaited(_resolveShotOnDemand(bundle, newIndex));
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Decision handling
  // ═══════════════════════════════════════════════════════════════════════════

  void _handleDecision(String eventType, {String? identityId}) {
    final bundle = _currentBundle;
    if (bundle == null) return;
    if (identityId != null && identityId != bundle.identityId) return;

    final shot = bundle.shots[_currentShotIndex];
    final decision = bundle.decisionGate.commit(
      eventType: eventType,
      position: _currentIdentityIndex,
    );

    if (decision != null && _kakaoUserId != null) {
      _logRecEvent(
        uid: _kakaoUserId!,
        eventType: decision.eventType,
        card: shot,
        position: decision.position,
        label: 'decision',
        decision: decision,
        sessionId: _aiPreferenceSessionId,
      );
    }

    if (decision != null) _advanceToNextIdentity(bundle.identityId);
  }

  void _advanceToNextIdentity(String identityId) {
    final bundle = _currentBundle;
    if (bundle == null || bundle.identityId != identityId) return;
    if (!bundle.decisionGate.isTerminal) return;

    _currentShotIndex = 0;
    _currentIdentityIndex++;

    // Trim old identities to prevent unbounded memory growth
    if (_currentIdentityIndex >= 15 && _identities.length > 25) {
      _identities.removeRange(0, _currentIdentityIndex);
      _currentIdentityIndex = 0;
    }

    setState(() {});

    unawaited(_prepareVisibleWindow());
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Swipe gesture handling
  // ═══════════════════════════════════════════════════════════════════════════

  void _onPanStart(DragStartDetails details) {
    if (_isAnimating) return;
    _panStartGlobal = details.globalPosition;
    _panTotalDistance = 0;
    _snapController.stop();
    _flyController.stop();
  }

  void _onPanUpdate(DragUpdateDetails details) {
    _panTotalDistance += details.delta.distance;
    if (_isAnimating) return;
    final bundle = _currentBundle;
    if (bundle != null && !bundle.decisionGate.isTerminal) {
      setState(() => _dragOffset += details.delta);
    }
  }

  void _onPanEnd(DragEndDetails details) {
    if (_isAnimating) return;

    // ── Tap detection ──
    if (_panTotalDistance < _tapDistanceThreshold) {
      _handleTap(_panStartGlobal);
      _dragOffset = Offset.zero;
      setState(() {});
      return;
    }

    final bundle = _currentBundle;
    if (bundle == null || bundle.decisionGate.isTerminal) {
      _dragOffset = Offset.zero;
      setState(() {});
      return;
    }

    // ── Swipe threshold ──
    final screenWidth = MediaQuery.of(context).size.width;
    final threshold = screenWidth * _distanceThresholdRatio;
    final velocity = details.velocity.pixelsPerSecond.dx;

    if (_dragOffset.dx.abs() > threshold ||
        velocity.abs() > _velocityThreshold) {
      final dir = _dragOffset.dx > 0 ? _SwipeDir.right : _SwipeDir.left;
      _animateFlyOff(dir);
    } else {
      _animateSnapBack();
    }
  }

  void _handleTap(Offset? pos) {
    if (pos == null) return;
    if (_lastSwipeTime != null &&
        DateTime.now().difference(_lastSwipeTime!) < _postSwipeTapCooldown) {
      return;
    }

    final w = MediaQuery.of(context).size.width;
    if (pos.dx < w * _leftTapZoneRatio) {
      _navigateToShot(_currentShotIndex - 1);
    } else if (pos.dx > w * _rightTapZoneStart) {
      _navigateToShot(_currentShotIndex + 1);
    }
    // Center zone: no action
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Swipe animations (exact match: SeolSwipeDeck)
  // ═══════════════════════════════════════════════════════════════════════════

  void _animateFlyOff(_SwipeDir dir) {
    _isAnimating = true;
    _pendingFlyDir = dir;
    _pendingFlyIdentityId = _currentBundle?.identityId;
    HapticFeedback.mediumImpact();

    final screenWidth = MediaQuery.of(context).size.width;
    final targetX = dir == _SwipeDir.right
        ? screenWidth * 1.5
        : -screenWidth * 1.5;

    _flyAnimation = Tween<Offset>(
      begin: _dragOffset,
      end: Offset(targetX, _dragOffset.dy + 80),
    ).animate(CurvedAnimation(parent: _flyController, curve: Curves.easeIn));

    _flyAnimation!.addListener(() {
      if (mounted) setState(() => _dragOffset = _flyAnimation!.value);
    });

    _flyController.forward(from: 0);
  }

  void _animateSnapBack() {
    _isAnimating = true;

    _snapAnimation = Tween<Offset>(begin: _dragOffset, end: Offset.zero)
        .animate(
          CurvedAnimation(parent: _snapController, curve: Curves.elasticOut),
        );

    _snapAnimation!.addListener(() {
      if (mounted) setState(() => _dragOffset = _snapAnimation!.value);
    });

    _snapController.forward(from: 0);
  }

  void _onFlyComplete(AnimationStatus status) {
    if (status != AnimationStatus.completed) return;

    final dir = _pendingFlyDir;
    final identityId = _pendingFlyIdentityId;
    if (dir == null || identityId == null) return;
    final eventType = dir == _SwipeDir.right ? 'like' : 'nope';

    _lastSwipeTime = DateTime.now();

    if (mounted) {
      setState(() {
        _dragOffset = Offset.zero;
        _isAnimating = false;
        _pendingFlyDir = null;
        _pendingFlyIdentityId = null;
      });
    }

    _handleDecision(eventType, identityId: identityId);
  }

  void _onSnapComplete(AnimationStatus status) {
    if (status == AnimationStatus.completed) {
      if (mounted) {
        setState(() {
          _dragOffset = Offset.zero;
          _isAnimating = false;
        });
      }
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Button handlers
  // ═══════════════════════════════════════════════════════════════════════════

  void _onLike() {
    if (_isAnimating) return;
    if (_currentBundle?.decisionGate.isTerminal ?? true) return;
    HapticFeedback.mediumImpact();
    setState(() => _dragOffset = const Offset(40, 0));
    _animateFlyOff(_SwipeDir.right);
  }

  void _onPass() {
    if (_isAnimating) return;
    if (_currentBundle?.decisionGate.isTerminal ?? true) return;
    HapticFeedback.lightImpact();
    setState(() => _dragOffset = const Offset(-40, 0));
    _animateFlyOff(_SwipeDir.left);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // RecEvent logging (preserved from original)
  // ═══════════════════════════════════════════════════════════════════════════

  Future<void> _logRecEvent({
    required String uid,
    required String eventType,
    required _AiCardData card,
    required int position,
    required String label,
    required String sessionId,
    AiPreferenceDecisionCommit? decision,
  }) async {
    try {
      await _recEventService.logEvent(
        userId: uid,
        targetType: 'ai_profile',
        targetId: card.identityId,
        candidateUserId: card.identityId,
        eventType: eventType,
        surface: 'ai_preference',
        cardVariant: 'ai_profile',
        exposureId: _uuid.v4(),
        sessionId: sessionId,
        eventId: RecEventContract.identityDecisionEventId(
          sessionId: sessionId,
          identityId: card.identityId,
        ),
        context: <String, dynamic>{
          'screen': 'ai_preference_screen',
          'position': position,
          'profileId': card.profileId,
          'folder': card.gender,
          'identityId': card.identityId,
          'decisionScope': 'identity',
          'aiPreferenceImageCount': 3,
          'aiPreferenceSchemaVersion': 2,
          // Audit which evidence shot was visible; targetId remains the
          // canonical identity and this metadata never creates a shot event.
          'shotType': aiPreferenceShotTypeName(card.shotType),
          if (decision != null) 'decisionShotCount': decision.shotCount,
          if (decision != null)
            'decisionShotTypes': decision.presentedShotTypes
                .map(aiPreferenceShotTypeName)
                .toList(growable: false),
          if (card.heightTag != null) 'heightTag': card.heightTag,
        },
      );
    } catch (e) {
      debugPrint(
        '[AI_PREF] recEvent $label failed '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Image provider cache
  // ═══════════════════════════════════════════════════════════════════════════

  ImageProvider _getImageProvider(String url) {
    return _imageProviders.putIfAbsent(url, () => NetworkImage(url));
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Build
  // ═══════════════════════════════════════════════════════════════════════════

  @override
  Widget build(BuildContext context) {
    _performanceTrace.markFirstBuild();
    if (_loading) {
      return const CupertinoPageScaffold(
        backgroundColor: CupertinoColors.black,
        child: Center(child: CupertinoActivityIndicator(radius: 14)),
      );
    }

    if (_currentIdentityIndex >= _identities.length) {
      if (_loadingNextIdentity) {
        return const CupertinoPageScaffold(
          backgroundColor: CupertinoColors.black,
          child: Center(child: CupertinoActivityIndicator(radius: 14)),
        );
      }
      return _buildEmptyState(context);
    }

    final bundle = _identities[_currentIdentityIndex];
    final shot = bundle.shots[_currentShotIndex];
    final imageUrl = shot.imageUrl;
    final hasImage = imageUrl != null && imageUrl.isNotEmpty;
    final isDecided = bundle.decisionGate.isTerminal;

    final mq = MediaQuery.of(context);
    final screenWidth = mq.size.width;

    // Swipe feedback
    final dragProgress = screenWidth > 0
        ? (_dragOffset.dx / (screenWidth * 0.5)).clamp(-1.0, 1.0)
        : 0.0;
    final rotationAngle = dragProgress * _maxRotationDeg * (math.pi / 180);

    return CupertinoPageScaffold(
      backgroundColor: CupertinoColors.black,
      child: Stack(
        fit: StackFit.expand,
        children: [
          // ── 1. Sharp base + masked progressive blur layers ──
          if (hasImage)
            Positioned.fill(
              child: AiPreferenceProgressiveBlurSurface(
                image: _getImageProvider(imageUrl),
                dragOffset: _dragOffset,
                rotationAngle: rotationAngle,
                errorBuilder: (_) => _buildImageError(),
                onFirstFrame: _onFirstImageFrame,
              ),
            ),

          if (!hasImage)
            Center(
              child: bundle.failedShots.contains(shot.shotType)
                  ? _buildImageError()
                  : const CupertinoActivityIndicator(radius: 14),
            ),

          // ── 2. Full-screen gesture layer ──
          // (below buttons in Stack → buttons have higher hit-test priority)
          Positioned.fill(
            child: GestureDetector(
              onPanStart: _onPanStart,
              onPanUpdate: _onPanUpdate,
              onPanEnd: _onPanEnd,
              behavior: HitTestBehavior.translucent,
            ),
          ),

          // ── 3. Top UI ──
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: SafeArea(bottom: false, child: _buildTopUI()),
          ),

          // ── 4. Bottom controls ──
          Positioned(
            bottom: 0,
            left: 0,
            right: 0,
            child: SafeArea(top: false, child: _buildBottomControls(isDecided)),
          ),
        ],
      ),
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Build helpers
  // ═══════════════════════════════════════════════════════════════════════════

  Widget _buildTopUI() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 4, 8, 0),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // ── Row: back · title · progress ──
          Row(
            children: [
              // Back button
              CupertinoButton(
                padding: const EdgeInsets.all(8),
                minimumSize: Size.zero,
                onPressed: () => Navigator.of(context).pop(),
                child: const Icon(
                  CupertinoIcons.chevron_left,
                  color: CupertinoColors.white,
                  size: 22,
                ),
              ),
              const SizedBox(width: 4),
              // Title + subtitle
              Expanded(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'AI에게 내 취향 알려주기',
                      style: TextStyle(
                        fontFamily: AppTypography.fontFamily,
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: CupertinoColors.white,
                        letterSpacing: -0.3,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'AI 취향 학습용',
                      style: TextStyle(
                        fontFamily: AppTypography.fontFamily,
                        fontSize: 11,
                        fontWeight: FontWeight.w400,
                        color: const Color(0x99FFFFFF),
                        letterSpacing: -0.1,
                      ),
                    ),
                  ],
                ),
              ),
              // Progress counter
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 5,
                ),
                decoration: BoxDecoration(
                  color: const Color(0x44000000),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0x22FFFFFF)),
                ),
                child: Text(
                  '${_currentIdentityIndex + 1}번째',
                  style: TextStyle(
                    fontFamily: AppTypography.fontFamily,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: const Color(0xCCFFFFFF),
                  ),
                ),
              ),
              const SizedBox(width: 8),
            ],
          ),

          const SizedBox(height: 8),

          // ── 3-shot progress capsules ──
          _buildShotProgress(),
        ],
      ),
    );
  }

  Widget _buildShotProgress() {
    return Semantics(
      label: '3장 중 ${_currentShotIndex + 1}번째 사진',
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12),
        child: Row(
          children: List.generate(3, (i) {
            final isCurrent = i == _currentShotIndex;

            return Expanded(
              child: Container(
                height: 3,
                margin: EdgeInsets.only(right: i < 2 ? 4 : 0),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(1.5),
                  color: isCurrent
                      ? CupertinoColors.white
                      : const Color(0x44FFFFFF),
                ),
              ),
            );
          }),
        ),
      ),
    );
  }

  Widget _buildBottomControls(bool isCurrentDecided) {
    final accent = AppColors.primary;

    return Padding(
      padding: const EdgeInsets.only(bottom: 12, left: 24, right: 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // ── Instruction text ──
          if (!isCurrentDecided)
            Padding(
              padding: const EdgeInsets.only(bottom: 20),
              child: Text(
                '사진을 보고 느껴지는 첫인상을 알려주세요',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: AppTypography.fontFamily,
                  fontSize: 14,
                  fontWeight: FontWeight.w400,
                  color: const Color(0xBBFFFFFF),
                  letterSpacing: -0.2,
                ),
              ),
            ),

          // ── Dislike / Like ──
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Dislike
              _ActionButton(
                icon: CupertinoIcons.xmark,
                label: '아니에요',
                size: 68,
                backgroundColor: const Color(0x55000000),
                borderColor: const Color(0x33FFFFFF),
                iconColor: CupertinoColors.white,
                onPressed: isCurrentDecided ? null : _onPass,
                semanticLabel: '마음에 들지 않아요',
              ),
              const SizedBox(width: 48),
              // Like
              _ActionButton(
                icon: CupertinoIcons.heart_fill,
                label: '끌려요',
                size: 72,
                backgroundColor: accent,
                borderColor: accent,
                iconColor: CupertinoColors.white,
                onPressed: isCurrentDecided ? null : _onLike,
                semanticLabel: '마음에 들어요',
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildImageError() {
    return Container(
      width: 120,
      height: 120,
      decoration: BoxDecoration(
        color: const Color(0x33FFFFFF),
        borderRadius: BorderRadius.circular(24),
      ),
      child: const Center(
        child: Icon(
          CupertinoIcons.exclamationmark_triangle,
          color: Color(0x88FFFFFF),
          size: 32,
        ),
      ),
    );
  }

  Widget _buildEmptyState(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: CupertinoColors.black,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: CupertinoColors.black,
        middle: Text(
          'AI에게 내 취향 알려주기',
          style: TextStyle(
            fontFamily: AppTypography.fontFamily,
            color: CupertinoColors.white,
          ),
        ),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () => Navigator.of(context).pop(),
          child: const Icon(
            CupertinoIcons.chevron_left,
            color: CupertinoColors.white,
          ),
        ),
      ),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              CupertinoIcons.heart_slash,
              size: 56,
              color: CupertinoColors.systemGrey3,
            ),
            const SizedBox(height: 16),
            Text(
              '오늘의 추천이 끝났어요',
              style: TextStyle(
                fontFamily: AppTypography.fontFamily,
                fontSize: 18,
                fontWeight: FontWeight.w600,
                color: CupertinoColors.systemGrey,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              '내일 새로운 인연을 만나보세요 💕',
              style: TextStyle(
                fontFamily: AppTypography.fontFamily,
                fontSize: 14,
                color: CupertinoColors.systemGrey2,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// Action Button (Dislike / Like)
// =============================================================================

class _ActionButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final double size;
  final Color backgroundColor;
  final Color borderColor;
  final Color iconColor;
  final VoidCallback? onPressed;
  final String semanticLabel;

  const _ActionButton({
    required this.icon,
    required this.label,
    required this.size,
    required this.backgroundColor,
    required this.borderColor,
    required this.iconColor,
    this.onPressed,
    required this.semanticLabel,
  });

  @override
  Widget build(BuildContext context) {
    final isDisabled = onPressed == null;
    final effectiveOpacity = isDisabled ? 0.4 : 1.0;

    return Semantics(
      label: semanticLabel,
      button: true,
      child: Opacity(
        opacity: effectiveOpacity,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: Size.zero,
              onPressed: onPressed,
              child: Container(
                width: size,
                height: size,
                decoration: BoxDecoration(
                  color: backgroundColor,
                  shape: BoxShape.circle,
                  border: Border.all(color: borderColor, width: 1.0),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0x22000000),
                      blurRadius: 16,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: Center(
                  child: Icon(icon, size: size * 0.42, color: iconColor),
                ),
              ),
            ),
            const SizedBox(height: 6),
            Text(
              label,
              style: TextStyle(
                fontFamily: AppTypography.fontFamily,
                fontSize: 12,
                fontWeight: FontWeight.w500,
                color: const Color(0xAAFFFFFF),
                letterSpacing: -0.2,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// Data classes
// =============================================================================

class _IdentityBundle {
  _IdentityBundle({required this.identityId, required this.shots})
    : decisionGate = AiPreferenceIdentityDecisionGate(
        identityId: identityId,
        presentedShotTypes: shots.map((shot) => shot.shotType),
      );

  factory _IdentityBundle.fromLoaded(AiPreferenceLoadedIdentity loaded) {
    return _IdentityBundle(
      identityId: loaded.identityId,
      shots: loaded.shots
          .map((image) => _AiCardData(image: image, heightDebug: 'pending'))
          .toList(growable: false),
    );
  }

  final String identityId;
  final List<_AiCardData> shots; // exactly 3, in session-shuffled order
  final AiPreferenceIdentityDecisionGate decisionGate;
  final Set<AiPreferenceShotType> resolvingShots = <AiPreferenceShotType>{};
  final Set<AiPreferenceShotType> failedShots = <AiPreferenceShotType>{};
  bool hydrationStarted = false;
  bool heightLoadStarted = false;

  String get profileId => shots.first.profileId;

  AiPreferenceLoadedIdentity toLoadedIdentity() {
    return AiPreferenceLoadedIdentity(
      identityId: identityId,
      shots: shots.map((shot) => shot.image),
    );
  }

  void applyLoadedIdentity(AiPreferenceLoadedIdentity loaded) {
    final imagesByShot = <AiPreferenceShotType, AiPreferenceImage>{
      for (final image in loaded.shots) image.shotType: image,
    };
    for (var index = 0; index < shots.length; index++) {
      final current = shots[index];
      final image = imagesByShot[current.shotType];
      if (image == null) continue;
      shots[index] = _AiCardData(
        image: image,
        heightTag: current.heightTag,
        heightDebug: current.heightDebug,
      );
      if (image.downloadUrl != null && image.downloadUrl!.isNotEmpty) {
        failedShots.remove(image.shotType);
      } else if (hydrationStarted) {
        failedShots.add(image.shotType);
      }
    }
  }

  void applyHeight(_HeightFetchResult result) {
    for (var index = 0; index < shots.length; index++) {
      final current = shots[index];
      shots[index] = _AiCardData(
        image: current.image,
        heightTag: result.tag,
        heightDebug: result.debug,
      );
    }
  }
}

class _AiCardData {
  final AiPreferenceImage image;
  final String? heightTag;
  final String heightDebug;

  const _AiCardData({
    required this.image,
    this.heightTag,
    this.heightDebug = 'init',
  });

  String get identityId => image.identityId;
  String get gender => image.gender;
  String get profileId => image.profileId;
  AiPreferenceShotType get shotType => image.shotType;
  String get storagePath => image.storagePath;
  String? get imageUrl => image.downloadUrl;
}

class _HeightFetchResult {
  final String? tag;
  final String debug;

  const _HeightFetchResult({required this.tag, required this.debug});

  _HeightFetchResult copyWith({String? tag, String? debug}) =>
      _HeightFetchResult(tag: tag ?? this.tag, debug: debug ?? this.debug);
}
