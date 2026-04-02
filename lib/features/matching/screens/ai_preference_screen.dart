import 'dart:math' as math;

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_storage/firebase_storage.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import 'package:uuid/uuid.dart';

import '../../../router/route_names.dart';
import '../../../services/rec_event_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../../shared/widgets/seol_swipe_deck.dart';

/// AI 취향 알려주기 화면
class AiPreferenceScreen extends StatefulWidget {
  const AiPreferenceScreen({super.key});

  @override
  State<AiPreferenceScreen> createState() => _AiPreferenceScreenState();
}

class _AiPreferenceScreenState extends State<AiPreferenceScreen> {
  static const int _prefetchCount = 6;
  static const int _minBuffer = 3;

  final _deckController = SeolSwipeDeckController();
  final _firestore = FirebaseFirestore.instance;
  final _storage = FirebaseStorage.instance;
  final _rng = math.Random.secure();

  final _storageService = StorageService();
  final _userService = UserService();
  final _recEventService = RecEventService();
  final _uuid = const Uuid();

  String? _kakaoUserId;

  final Map<String, String> _urlCacheByPath = {};
  final Map<int, String?> _heightTagCacheById = {};
  final Map<int, String> _heightDebugCacheById = {};
  _TargetPool? _activePoolForIdBag;
  final List<int> _idBag = <int>[];
  int _idBagIndex = 0;

  bool _loading = true;
  String? _userGender; // 'male' | 'female' | '남성' | '여성' | null

  /// 현재 덱에 쌓인 카드 (무한에 가깝게 늘어날 수 있으니 적당히 트림)
  final List<_AiCardData> _cards = [];
  int _deckResetSeed = 0;

  @override
  void initState() {
    super.initState();
    _init();
  }

  @override
  void dispose() {
    _deckController.dispose();
    super.dispose();
  }

  Future<void> _init() async {
    setState(() => _loading = true);

    final kakaoUserId = await _storageService.getKakaoUserId();
    _kakaoUserId = kakaoUserId;
    debugPrint('[AI_PREF] kakaoUserId=$kakaoUserId');

    String? gender;
    if (kakaoUserId != null && kakaoUserId.isNotEmpty) {
      // 1) Firestore user profile 최우선
      final profile = await _userService.getUserProfile(kakaoUserId);
      gender = _extractGender(profile);

      // 2) 온보딩 드래프트(SharedPreferences) fallback
      gender ??= await _extractGenderFromOnboardingDraft(kakaoUserId);
    }

    if (!mounted) return;
    _userGender = gender;

    _cards.clear();
    await _fillCards(targetCount: _prefetchCount);

    if (!mounted) return;
    setState(() => _loading = false);

    if (_cards.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _recordImpression(0));
    }
  }

  String? _extractGender(Map<String, dynamic>? profile) {
    if (profile == null) return null;
    final direct = profile['gender']?.toString();
    if (direct != null && direct.trim().isNotEmpty) return direct.trim();

    final onboarding = profile['onboarding'];
    if (onboarding is Map) {
      // 온보딩이 { gender: 'female', ... } 형태로 저장된 경우 (saveOnboardingBasicInfo가 basicInfo 객체를 onboarding에 그대로 저장)
      final gAtOnboarding = onboarding['gender']?.toString();
      if (gAtOnboarding != null && gAtOnboarding.trim().isNotEmpty) return gAtOnboarding.trim();
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
    // draft가 flat하게 들어갔을 수도 있어 한 번 더 시도
    final g2 = draft['gender']?.toString();
    if (g2 != null && g2.trim().isNotEmpty) return g2.trim();
    return null;
  }

  _TargetPool _decideTargetPool(String? userGender) {
    final raw = (userGender ?? '').trim();
    final normalized = raw.toLowerCase();
    // 남성: male, m, 남성, 남자, man
    final isMale = normalized == 'male' ||
        normalized == 'm' ||
        raw == '남성' ||
        raw == '남자' ||
        normalized == 'man';
    // 여성: female, f, 여성, 여자, woman
    final isFemale = normalized == 'female' ||
        normalized == 'f' ||
        raw == '여성' ||
        raw == '여자' ||
        normalized == 'woman';

    if (isMale) {
      // 남자 사용자 → 여자 AI 카드만 (251~500)
      return const _TargetPool(folder: 'female', minId: 251, maxId: 500);
    }
    if (isFemale) {
      // 여자 사용자 → 남자 AI 카드만 (1~250)
      return const _TargetPool(folder: 'male', minId: 1, maxId: 250);
    }

    // 성별을 못 알면: 둘 중 랜덤 fallback
    return _rng.nextBool()
        ? const _TargetPool(folder: 'female', minId: 251, maxId: 500)
        : const _TargetPool(folder: 'male', minId: 1, maxId: 250);
  }

  void _ensureIdBagForPool(_TargetPool pool) {
    final samePool =
        _activePoolForIdBag != null &&
        _activePoolForIdBag!.folder == pool.folder &&
        _activePoolForIdBag!.minId == pool.minId &&
        _activePoolForIdBag!.maxId == pool.maxId;

    if (samePool && _idBag.isNotEmpty) return;

    _activePoolForIdBag = pool;
    _idBag
      ..clear()
      ..addAll(
        List<int>.generate(
          pool.maxId - pool.minId + 1,
          (i) => pool.minId + i,
        ),
      );
    _idBag.shuffle(_rng);
    _idBagIndex = 0;
  }

  int _nextProfileId(_TargetPool pool) {
    _ensureIdBagForPool(pool);

    if (_idBagIndex >= _idBag.length) {
      // 한 바퀴 다 돌았으면 다시 셔플
      _idBag.shuffle(_rng);
      _idBagIndex = 0;
    }

    final id = _idBag[_idBagIndex];
    _idBagIndex++;
    return id;
  }

  String _storagePathFor(String folder, int id) => 'ai_profiles/$folder/$id.png';

  /// Storage에 없을 때 사용할 플레이스홀더 (404 시)
  static const String _placeholderUrl =
      'https://placehold.co/400x600/e2e8f0/64748b?text=No+Image';

  Future<String> _getDownloadUrl(String storagePath) async {
    final cached = _urlCacheByPath[storagePath];
    if (cached != null) return cached;
    try {
      final url = await _storage.ref(storagePath).getDownloadURL();
      _urlCacheByPath[storagePath] = url;
      return url;
    } on FirebaseException catch (e) {
      if (e.code == 'object-not-found' ||
          e.code == 'storage/object-not-found' ||
          (e.message?.contains('404') ?? false) ||
          (e.message?.toLowerCase().contains('not found') ?? false)) {
        debugPrint('[AI_PREF] Storage 404: $storagePath (파일 없음)');
        _urlCacheByPath[storagePath] = _placeholderUrl;
        return _placeholderUrl;
      }
      debugPrint('[AI_PREF] Storage FirebaseException: $storagePath code=${e.code} msg=${e.message}');
      _urlCacheByPath[storagePath] = _placeholderUrl;
      return _placeholderUrl;
    } catch (e) {
      debugPrint('[AI_PREF] Storage 기타 예외: $storagePath err=$e');
      _urlCacheByPath[storagePath] = _placeholderUrl;
      return _placeholderUrl;
    }
  }

  Future<_HeightFetchResult> _fetchHeightForProfileId(int id) async {
    try {
      final cached = _heightTagCacheById[id];
      if (cached != null) {
        return _HeightFetchResult(tag: cached, debug: _heightDebugCacheById[id] ?? 'cache');
      }

      final snap = await _firestore.collection('ai_profiles').doc('$id').get();
      if (!snap.exists) {
        _heightDebugCacheById[id] = 'not-found';
        return const _HeightFetchResult(tag: null, debug: 'not-found');
      }
      final data = snap.data();
      // 프로젝트에서 metaRaw로 저장된 케이스 대응
      final metadata =
          data?['metadata'] ??
          data?['metaRaw'] ??
          data?['metaRAW'] ??
          data?['meta_raw'];

      // 1) 문서 루트에 height가 직접 있을 수 있음
      String? rawHeight = data?['height']?.toString();

      // 2) metadata 필드에서 height 추출
      rawHeight ??= _extractHeightFromMetadata(metadata);

      final tag = _normalizeHeightTag(rawHeight);
      if (tag != null) {
        _heightTagCacheById[id] = tag;
        _heightDebugCacheById[id] = 'ok';
        return const _HeightFetchResult(tag: null, debug: 'ok')
            .copyWith(tag: tag); // keep const + dynamic tag
      }

      if (metadata == null) {
        _heightDebugCacheById[id] = 'no-metadata';
      } else if (rawHeight == null) {
        _heightDebugCacheById[id] = 'no-height';
      } else {
        _heightDebugCacheById[id] = 'parse-fail';
      }
      return _HeightFetchResult(tag: null, debug: _heightDebugCacheById[id]!);
    } on FirebaseException catch (e) {
      final d = 'fs-${e.code}';
      _heightDebugCacheById[id] = d;
      debugPrint('[AI_PREF] height load failed id=$id code=${e.code} msg=${e.message}');
      return _HeightFetchResult(tag: null, debug: d);
    } catch (e) {
      debugPrint('[AI_PREF] height parse failed id=$id err=$e');
      _heightDebugCacheById[id] = 'err';
      return const _HeightFetchResult(tag: null, debug: 'err');
    }
  }

  String? _extractHeightFromMetadata(dynamic metadata) {
    if (metadata == null) return null;
    if (metadata is Map) {
      // Map<String, dynamic> 또는 Map<dynamic, dynamic> 모두 대응
      final v = metadata['height'] ?? metadata['Height'] ?? metadata['HEIGHT'];
      return v?.toString();
    }
    if (metadata is String) {
      return _extractHeightFromMetadataString(metadata);
    }
    return _extractHeightFromMetadataString(metadata.toString());
  }

  String? _extractHeightFromMetadataString(String metadata) {
    // ✅ 가장 안전한 방식: height 키의 값을 우선 파싱
    // (metadata 전체 문자열에 다른 숫자/xxcm가 있을 수 있어서, "cm 패턴"을 먼저 잡으면 오염됨)
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

    // fallback: 문자열 어디든 "000cm" 패턴이 있으면 사용 (최후의 수단)
    final cm = RegExp(r'([0-9]{2,3})\s*cm', caseSensitive: false)
        .firstMatch(metadata);
    if (cm != null) return cm.group(1);

    return null;
  }

  String? _normalizeHeightTag(String? rawHeight) {
    if (rawHeight == null) return null;
    final trimmed = rawHeight.trim();
    if (trimmed.isEmpty || trimmed.toLowerCase() == 'none') return null;

    // "173cm, ..." / "173" / "키 173cm" 등에서 숫자만 뽑아서 "000cm"로 고정 출력
    final digits = RegExp(r'(\d{2,3})').firstMatch(trimmed)?.group(1);
    final parsed = digits == null ? null : int.tryParse(digits);
    if (parsed != null) {
      return '${parsed.toString().padLeft(3, '0')}cm';
    }

    // "000cm" 형태로 만들 수 없으면 표시하지 않음
    return null;
  }

  Future<void> _fillCards({required int targetCount}) async {
    var attempts = 0;
    final maxAttempts = (targetCount * 6).clamp(30, 400);

    while (_cards.length < targetCount && attempts < maxAttempts) {
      attempts++;
      final pool = _decideTargetPool(_userGender);
      final id = _nextProfileId(pool);
      final path = _storagePathFor(pool.folder, id);

      try {
        final url = await _getDownloadUrl(path);
        final heightRes = await _fetchHeightForProfileId(id);
        _cards.add(
          _AiCardData(
            id: id,
            folder: pool.folder,
            storagePath: path,
            imageUrl: url,
            heightTag: heightRes.tag,
            heightDebug: heightRes.debug,
          ),
        );
      } catch (e, st) {
        debugPrint('[AI_PREF] _fillCards 실패 id=$id path=$path: $e');
        debugPrint('[AI_PREF] stack: $st');
      }
    }

    if (_cards.isEmpty && targetCount > 0) {
      debugPrint('[AI_PREF] Storage/Firestore에서 카드 로드 실패 → 플레이스홀더 폴백');
      _addPlaceholderFallbackCards(targetCount);
    }
  }

  void _addPlaceholderFallbackCards(int count) {
    final pool = _decideTargetPool(_userGender);
    for (var i = 0; i < count; i++) {
      final id = pool.minId + (i % (pool.maxId - pool.minId + 1));
      final path = _storagePathFor(pool.folder, id);
      _cards.add(
        _AiCardData(
          id: id,
          folder: pool.folder,
          storagePath: path,
          imageUrl: _placeholderUrl,
          heightTag: null,
          heightDebug: 'fallback',
        ),
      );
    }
  }

  Future<void> _ensureBufferAfterSwipe(int swipedIndex) async {
    final topIndexAfterSwipe = swipedIndex + 1;
    final remaining = _cards.length - topIndexAfterSwipe;
    if (remaining >= _minBuffer) return;

    final desiredTotal = topIndexAfterSwipe + _prefetchCount;
    await _fillCards(targetCount: desiredTotal);
  }

  void _onSwiped(int index, SwipeDirection direction) {
    final uid = _kakaoUserId;
    if (uid != null && index < _cards.length) {
      final card = _cards[index];
      final eventType = direction == SwipeDirection.right ? 'like' : 'nope';
      _logRecEvent(
        uid: uid,
        eventType: eventType,
        card: card,
        position: index,
        label: 'swipe',
      );
    }

    final shouldTrim = index >= 20 && _cards.length > 40;

    if (shouldTrim) {
      _cards.removeRange(0, index + 1);
      _deckResetSeed++;
      setState(() {});
    }

    _ensureBufferAfterSwipe(shouldTrim ? -1 : index).then((_) {
      if (mounted) setState(() {});
    });

    final nextIndex = shouldTrim ? 0 : index + 1;
    if (nextIndex < _cards.length) {
      _recordImpression(nextIndex);
    }
  }

  Future<void> _logRecEvent({
    required String uid,
    required String eventType,
    required _AiCardData card,
    required int position,
    required String label,
  }) async {
    try {
      await _recEventService.logEvent(
        userId: uid,
        targetType: 'ai_profile',
        targetId: '${card.folder}_${card.id}',
        eventType: eventType,
        surface: 'ai_preference',
        cardVariant: 'ai_profile',
        exposureId: _uuid.v4(),
        context: <String, dynamic>{
          'screen': 'ai_preference_screen',
          'position': position,
          'profileId': card.id,
          'folder': card.folder,
          if (card.heightTag != null) 'heightTag': card.heightTag,
        },
      );
    } catch (e) {
      debugPrint('[AI_PREF] ❌ recEvent $label 실패: $e');
    }
  }

  void _recordImpression(int index) {
    final uid = _kakaoUserId;
    if (uid == null || index >= _cards.length) return;
    _logRecEvent(
      uid: uid,
      eventType: 'impression',
      card: _cards[index],
      position: index,
      label: 'impression',
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
    return CupertinoPageScaffold(
      backgroundColor: CupertinoColors.systemGroupedBackground,
      navigationBar: CupertinoNavigationBar(
        middle: const Text('AI에게 내 취향 더 잘 알려주기'),
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () => Navigator.of(context).pop(),
          child: const Icon(CupertinoIcons.xmark, size: 20),
        ),
      ),
      child: SafeArea(
        child: _loading
            ? const Center(child: CupertinoActivityIndicator())
            : Column(
                children: [
                  // 덱
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                      child: SeolSwipeDeck(
                        key: ValueKey('ai_pref_deck_$_deckResetSeed'),
                        controller: _deckController,
                        onSwiped: _onSwiped,
                        onEmpty: () async {
                          await _fillCards(targetCount: _prefetchCount);
                          if (mounted) setState(() {});
                        },
                        cards: _cards
                            .map(
                              (c) => _AiImageCard(
                                key: ValueKey('ai_card_${c.folder}_${c.id}'),
                                imageUrl: c.imageUrl,
                                profileId: c.id,
                                storagePath: c.storagePath,
                                initialHeightTag: c.heightTag,
                                initialHeightDebug: c.heightDebug,
                                heightLoader: _fetchHeightForProfileId,
                              ),
                            )
                            .toList(),
                      ),
                    ),
                  ),
                  // 버튼
                  Padding(
                    padding: EdgeInsets.fromLTRB(
                      24,
                      16,
                      24,
                      MediaQuery.of(context).padding.bottom + 16,
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        _RoundActionButton(
                          icon: CupertinoIcons.xmark,
                          iconColor: CupertinoColors.systemGrey,
                          onPressed: _onPass,
                        ),
                        const SizedBox(width: 40),
                        _RoundActionButton(
                          icon: CupertinoIcons.heart_fill,
                          iconColor: const Color(0xFFFF4D88),
                          onPressed: _onLike,
                        ),
                      ],
                    ),
                  ),
                  // (선택) 결과 화면 라우트로 넘어갈 수도 있어 entry point를 유지
                  const SizedBox(height: 4),
                  CupertinoButton(
                    padding: const EdgeInsets.only(bottom: 10),
                    onPressed: () {
                      Navigator.of(context, rootNavigator: true).pushNamed(
                        RouteNames.aiTasteTraining,
                      );
                    },
                    child: const Text(
                      '스와이프 가이드 보기(튜토리얼)',
                      style: TextStyle(fontSize: 12),
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}

class _AiImageCard extends StatefulWidget {
  final String imageUrl;
  final int profileId;
  final String storagePath;
  final String? initialHeightTag;
  final String initialHeightDebug;
  final Future<_HeightFetchResult> Function(int profileId) heightLoader;

  const _AiImageCard({
    super.key,
    required this.imageUrl,
    required this.profileId,
    required this.storagePath,
    required this.initialHeightTag,
    required this.initialHeightDebug,
    required this.heightLoader,
  });

  @override
  State<_AiImageCard> createState() => _AiImageCardState();
}

class _AiImageCardState extends State<_AiImageCard> {
  String? _heightTag;
  late String _heightDebug;

  @override
  void initState() {
    super.initState();
    _heightTag = widget.initialHeightTag;
    _heightDebug = widget.initialHeightDebug;

    if (_heightTag == null || _heightTag!.trim().isEmpty) {
      _heightDebug = 'loading';
      widget.heightLoader(widget.profileId).then((res) {
        if (!mounted) return;
        setState(() {
          _heightTag = res.tag;
          _heightDebug = res.debug;
        });
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: CupertinoColors.black,
        borderRadius: BorderRadius.circular(28),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.12),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Stack(
        fit: StackFit.expand,
        children: [
          Image.network(
            widget.imageUrl,
            fit: BoxFit.cover,
            loadingBuilder: (context, child, progress) {
              if (progress == null) return child;
              return const Center(child: CupertinoActivityIndicator());
            },
            errorBuilder: (_, __, ___) => Container(
              color: CupertinoColors.systemGrey5,
              alignment: Alignment.center,
              child: const Icon(
                CupertinoIcons.exclamationmark_triangle,
                color: CupertinoColors.systemGrey,
                size: 28,
              ),
            ),
          ),
          // 디버깅용: 이 카드가 몇 번(id)인지 배지 표시
          Positioned(
            left: 14,
            top: 14,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: CupertinoColors.black.withValues(alpha: 0.45),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: CupertinoColors.white.withValues(alpha: 0.18),
                ),
              ),
              child: Text(
                'ID ${widget.profileId}\n${widget.storagePath}',
                style: const TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: CupertinoColors.white,
                  letterSpacing: 0.2,
                ),
              ),
            ),
          ),
          // 살짝 그라데이션
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    CupertinoColors.black.withValues(alpha: 0.05),
                    CupertinoColors.black.withValues(alpha: 0.0),
                    CupertinoColors.black.withValues(alpha: 0.35),
                  ],
                  stops: const [0.0, 0.65, 1.0],
                ),
              ),
            ),
          ),

          // height 태그 (디버깅 겸 항상 표시)
            Positioned(
              left: 14,
              bottom: 14,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: CupertinoColors.black.withValues(alpha: 0.45),
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(
                    color: CupertinoColors.white.withValues(alpha: 0.18),
                  ),
                ),
                child: Text(
                  _heightTag ?? 'HEIGHT(?)  ($_heightDebug)',
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: CupertinoColors.white,
                    letterSpacing: 0.2,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _RoundActionButton extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final VoidCallback onPressed;

  const _RoundActionButton({
    required this.icon,
    required this.iconColor,
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
          color: CupertinoColors.white,
          shape: BoxShape.circle,
          border: Border.all(color: CupertinoColors.systemGrey5),
          boxShadow: [
            BoxShadow(
              color: CupertinoColors.black.withValues(alpha: 0.06),
              blurRadius: 16,
              offset: const Offset(0, 6),
            ),
          ],
        ),
        child: Center(
          child: Icon(icon, size: 34, color: iconColor),
        ),
      ),
    );
  }
}

class _AiCardData {
  final int id;
  final String folder; // male | female
  final String storagePath;
  final String imageUrl;
  final String? heightTag;
  final String heightDebug;

  const _AiCardData({
    required this.id,
    required this.folder,
    required this.storagePath,
    required this.imageUrl,
    this.heightTag,
    this.heightDebug = 'init',
  });
}

class _HeightFetchResult {
  final String? tag;
  final String debug;

  const _HeightFetchResult({required this.tag, required this.debug});

  _HeightFetchResult copyWith({String? tag, String? debug}) => _HeightFetchResult(
        tag: tag ?? this.tag,
        debug: debug ?? this.debug,
      );
}

class _TargetPool {
  final String folder; // male | female
  final int minId;
  final int maxId;

  const _TargetPool({required this.folder, required this.minId, required this.maxId});
}
