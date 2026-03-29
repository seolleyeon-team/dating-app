import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart'
    show showModalBottomSheet, RoundedRectangleBorder;
import 'package:flutter/services.dart';

import '../../../services/ask_service.dart';
import '../../../services/interaction_service.dart';
import '../../../services/rec_event_service.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';
import '../../chat/models/chat_room_data.dart';
import '../../chat/services/chat_service.dart';
import '../../../router/route_names.dart';
import '../models/profile_card_args.dart';

const String _kFontFamily = 'Noto Sans KR';

class _AppColors {
  static const Color primary = Color(0xFFFF5A7E);
  static const Color backgroundLight = Color(0xFFFFF7F9);
  static const Color blush = Color(0xFFFFF1F4);
  static const Color cardSurface = Color(0xFFFFFCFD);
  static const Color textMain = Color(0xFF1E1A1C);
  static const Color textSub = Color(0xFF6A6367);
  static const Color titleLight = Color(0xFFA39AA0);
  static const Color softPink = Color(0xFFE4E7EB);
  static const Color softRose = Color(0xFFDDE2E7);
  static const Color chipBg = Color(0xFFFFFFFF);
  static const Color chipBg2 = Color(0xFFFFFFFF);
  static const Color gray100 = Color(0xFFF8F1F4);
  static const Color gray200 = Color(0xFFF1E1E7);
  static const Color gray300 = Color(0xFFE8D3DB);
}

class _ResolvedProfile {
  final String id;
  final String name;
  final int? age;
  final String birthYearText;
  final String university;
  final String major;
  final int matchPercent;
  final String aboutMe;
  final List<String> imageUrls;
  final List<String> interests;
  final List<String> keywords;
  final String mbti;
  final String heightText;
  final String relationship;
  final String drinking;
  final String smoking;
  final String exercise;
  final List<String> loveLanguages;
  final List<Map<String, String>> profileQa;

  const _ResolvedProfile({
    required this.id,
    required this.name,
    required this.age,
    required this.birthYearText,
    required this.university,
    required this.major,
    required this.matchPercent,
    required this.aboutMe,
    required this.imageUrls,
    required this.interests,
    required this.keywords,
    required this.mbti,
    required this.heightText,
    required this.relationship,
    required this.drinking,
    required this.smoking,
    required this.exercise,
    required this.loveLanguages,
    required this.profileQa,
  });

  List<String> get chips {
    final merged = <String>[...interests, ...keywords];
    return merged.where((e) => e.trim().isNotEmpty).toSet().toList();
  }
}

class AiMatchProfileScreen extends StatefulWidget {
  final ProfileCardArgs? args;
  final VoidCallback? onBack;
  final VoidCallback? onMore;
  final VoidCallback? onQna;
  final VoidCallback? onPass;
  final VoidCallback? onLike;
  final VoidCallback? onMessage;

  const AiMatchProfileScreen({
    super.key,
    this.args,
    this.onBack,
    this.onMore,
    this.onQna,
    this.onPass,
    this.onLike,
    this.onMessage,
  });

  @override
  State<AiMatchProfileScreen> createState() => _AiMatchProfileScreenState();
}

class _AiMatchProfileScreenState extends State<AiMatchProfileScreen> {
  final UserService _userService = UserService();
  final StorageService _storageService = StorageService();
  final InteractionService _interactionService = InteractionService();
  final RecEventService _recEventService = RecEventService();
  final AskService _askService = AskService();
  final ChatService _chatService = ChatService();

  _ResolvedProfile? _profile;
  bool _isLoading = true;
  int _heroImageIndex = 0;

  // --- 상태 ---
  String? _currentUserId;
  late final DateTime _entryTime;
  bool _isLikeInFlight = false;
  bool _isNopeInFlight = false;
  bool _hasLiked = false;
  bool _hasNoped = false;

  @override
  void initState() {
    super.initState();
    _entryTime = DateTime.now();
    _loadProfile();
    _loadCurrentUser();
  }

  Future<void> _loadCurrentUser() async {
    final uid = await _storageService.getKakaoUserId();
    if (!mounted) return;
    setState(() => _currentUserId = uid);
    // detail_open recEvent
    if (uid != null && uid.isNotEmpty) {
      final targetId =
          widget.args?.userId ?? widget.args?.aiProfile?.candidateUid ?? '';
      if (targetId.isNotEmpty) {
        _recEventService
            .logEvent(
              userId: uid,
              targetType: 'user_profile',
              targetId: targetId,
              candidateUserId: targetId,
              eventType: 'open',
              surface: 'profile_card',
              cardVariant: 'real_profile',
              exposureId: widget.args?.aiProfile?.exposureId,
              dateKey: widget.args?.aiProfile?.dateKey,
              context: _buildRecContext(button: 'detail_open'),
            )
            .catchError((e) => debugPrint('[RecEvent] detail_open failed: $e'));
      }
    }
  }

  // ---------------------------------------------------------------------------
  // recEvents context 빌더
  // ---------------------------------------------------------------------------
  Map<String, dynamic> _buildRecContext({required String button}) {
    final ai = widget.args?.aiProfile;
    return {
      'screen': 'profile_specific_detail_screen',
      'ui': {
        'button': button,
        'detailOpened': true,
        'dwellMs': DateTime.now().difference(_entryTime).inMilliseconds,
      },
      if (ai != null) ...{
        if (ai.primaryAlgo.isNotEmpty) 'algorithmVersion': ai.primaryAlgo,
        if (ai.sourceScores != null) 'sourceRanks': ai.sourceScores,
        if (ai.finalScore != null) 'scoreTotal': ai.finalScore,
        if (ai.dateKey.isNotEmpty) 'recDateKey': ai.dateKey,
        'position': ai.rank,
      },
    };
  }

  // ---------------------------------------------------------------------------
  // Overlay 기반 Cupertino 스타일 토스트
  // ---------------------------------------------------------------------------
  void _showToast(String message, {bool isError = false}) {
    if (!mounted) return;
    final overlay = Overlay.of(context, rootOverlay: true);
    late final OverlayEntry entry;
    entry = OverlayEntry(
      builder: (ctx) => _ToastOverlay(
        message: message,
        isError: isError,
        onDismiss: () => entry.remove(),
      ),
    );
    overlay.insert(entry);
  }

  // ---------------------------------------------------------------------------
  // [1] Like 핸들러
  // ---------------------------------------------------------------------------
  Future<void> _handleLike() async {
    if (_isLikeInFlight || _hasLiked || _hasNoped) return;
    setState(() => _isLikeInFlight = true);

    HapticFeedback.mediumImpact();

    final uid = _currentUserId;
    final targetId = _profile?.id ?? '';
    if (uid == null || uid.isEmpty || targetId.isEmpty) {
      _showToast('로그인 정보를 확인할 수 없어요', isError: true);
      setState(() => _isLikeInFlight = false);
      return;
    }

    try {
      // 1) 비즈니스 로직 — like + match check
      final matchId = await _interactionService.recordLike(
        fromUserId: uid,
        toUserId: targetId,
        source: 'profile_specific_detail_screen',
      );

      // 2) recEvents — AI 학습 로그
      await _recEventService.logEvent(
        userId: uid,
        targetType: 'user_profile',
        targetId: targetId,
        candidateUserId: targetId,
        eventType: 'like',
        surface: 'profile_card',
        cardVariant: 'real_profile',
        exposureId: widget.args?.aiProfile?.exposureId,
        dateKey: widget.args?.aiProfile?.dateKey,
        context: _buildRecContext(button: 'like'),
      );

      if (!mounted) return;
      HapticFeedback.heavyImpact();

      // 매칭 성사 시 메시지 차별화
      if (matchId != null) {
        _showToast('서로 좋아요! 매칭되었어요 💕');
      } else {
        _showToast('좋아요를 보냈어요 💕');
      }

      // 콜백이 있으면 호출 (상위 화면 연동)
      widget.onLike?.call();
      if (mounted) setState(() => _hasLiked = true);
    } catch (e) {
      debugPrint('[Like] error: $e');
      if (!mounted) return;
      HapticFeedback.heavyImpact();
      _showToast('좋아요를 보내지 못했어요. 다시 시도해주세요.', isError: true);
    } finally {
      if (mounted) setState(() => _isLikeInFlight = false);
    }
  }

  // ---------------------------------------------------------------------------
  // [2] Nope 핸들러
  // ---------------------------------------------------------------------------
  Future<void> _handleNope() async {
    if (_isNopeInFlight || _hasNoped || _hasLiked) return;
    setState(() => _isNopeInFlight = true);

    HapticFeedback.lightImpact();

    final uid = _currentUserId;
    final targetId = _profile?.id ?? '';
    if (uid == null || uid.isEmpty || targetId.isEmpty) {
      _showToast('로그인 정보를 확인할 수 없어요', isError: true);
      setState(() => _isNopeInFlight = false);
      return;
    }

    try {
      await _interactionService.recordNope(
        fromUserId: uid,
        toUserId: targetId,
        source: 'profile_specific_detail_screen',
      );

      await _recEventService.logEvent(
        userId: uid,
        targetType: 'user_profile',
        targetId: targetId,
        candidateUserId: targetId,
        eventType: 'nope',
        surface: 'profile_card',
        cardVariant: 'real_profile',
        exposureId: widget.args?.aiProfile?.exposureId,
        dateKey: widget.args?.aiProfile?.dateKey,
        context: _buildRecContext(button: 'nope'),
      );

      if (!mounted) return;
      _showToast('이번 인연은 넘길게요');
      widget.onPass?.call();
      if (mounted) setState(() => _hasNoped = true);

      // 이전 화면으로
      await Future.delayed(const Duration(milliseconds: 350));
      if (!mounted) return;
      Navigator.of(context, rootNavigator: true).pop();
    } catch (e) {
      debugPrint('[Nope] error: $e');
      if (!mounted) return;
      HapticFeedback.heavyImpact();
      _showToast('처리하지 못했어요. 다시 시도해주세요.', isError: true);
    } finally {
      if (mounted) setState(() => _isNopeInFlight = false);
    }
  }

  // ---------------------------------------------------------------------------
  // [3] 무물(Ask) 핸들러
  // ---------------------------------------------------------------------------
  void _handleAsk() {
    HapticFeedback.selectionClick();
    final uid = _currentUserId;
    final targetId = _profile?.id ?? '';

    if (uid == null || uid.isEmpty || targetId.isEmpty) {
      _showToast('로그인 정보를 확인할 수 없어요', isError: true);
      return;
    }

    _recEventService
        .logEvent(
          userId: uid,
          targetType: 'user_profile',
          targetId: targetId,
          candidateUserId: targetId,
          eventType: 'open',
          surface: 'profile_card',
          cardVariant: 'real_profile',
          exposureId: widget.args?.aiProfile?.exposureId,
          dateKey: widget.args?.aiProfile?.dateKey,
          context: {
            ..._buildRecContext(button: 'ask'),
            'ui': {
              ..._buildRecContext(button: 'ask')['ui'] as Map<String, dynamic>,
              'action': 'ask_button_tap',
            },
          },
        )
        .catchError(
          (e) => debugPrint('[RecEvent] ask_button_tap failed: $e'),
        );

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: CupertinoColors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      builder: (sheetCtx) => _AskBottomSheet(
        targetName: _profile?.name ?? '상대방',
        onSend: (question) async {
          final myProfile = await _userService.getUserProfile(uid);
          final myOnboarding = myProfile?['onboarding'] is Map
              ? Map<String, dynamic>.from(myProfile!['onboarding'] as Map)
              : <String, dynamic>{};
          final myPhotoUrls = myOnboarding['photoUrls'] is List
              ? (myOnboarding['photoUrls'] as List)
                  .whereType<String>()
                  .toList()
              : <String>[];

          final fromSnapshot = _askService.buildProfileSnapshot(
            uid: uid,
            nickname: myOnboarding['nickname']?.toString(),
            profileImageUrl:
                myPhotoUrls.isNotEmpty ? myPhotoUrls.first : null,
            universityName: myOnboarding['university']?.toString(),
          );

          final toSnapshot = _askService.buildProfileSnapshot(
            uid: targetId,
            nickname: _profile?.name,
            profileImageUrl:
                _profile?.imageUrls.isNotEmpty == true
                    ? _profile!.imageUrls.first
                    : null,
            universityName: _profile?.university,
          );

          await _askService.sendAsk(
            fromUserId: uid,
            toUserId: targetId,
            text: question,
            fromUserSnapshot: fromSnapshot,
            toUserSnapshot: toSnapshot,
          );

          _recEventService
              .logEvent(
                userId: uid,
                targetType: 'user_profile',
                targetId: targetId,
                candidateUserId: targetId,
                eventType: 'open',
                surface: 'profile_card',
                cardVariant: 'real_profile',
                exposureId: widget.args?.aiProfile?.exposureId,
                dateKey: widget.args?.aiProfile?.dateKey,
                context: {
                  ..._buildRecContext(button: 'ask'),
                  'ui': {
                    ..._buildRecContext(button: 'ask')['ui']
                        as Map<String, dynamic>,
                    'action': 'ask_submit',
                  },
                  'questionLength': question.length,
                },
              )
              .catchError(
                (e) => debugPrint('[RecEvent] ask_submit failed: $e'),
              );

          widget.onQna?.call();
        },
        onSuccess: () {
          if (!mounted) return;
          _showToast('질문을 보냈어요 💌');
        },
        onError: (e) {
          debugPrint('[Ask] send failed: $e');
          if (!mounted) return;
          _showToast('질문을 보내지 못했어요', isError: true);
        },
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // [4] 메시지 핸들러
  // ---------------------------------------------------------------------------
  void _handleMessage() {
    HapticFeedback.selectionClick();
    final uid = _currentUserId;
    final targetId = _profile?.id ?? '';

    if (uid == null || uid.isEmpty || targetId.isEmpty) {
      _showToast('로그인 정보를 확인할 수 없어요', isError: true);
      return;
    }

    _recEventService
        .logEvent(
          userId: uid,
          targetType: 'user_profile',
          targetId: targetId,
          candidateUserId: targetId,
          eventType: 'open',
          surface: 'profile_card',
          cardVariant: 'real_profile',
          exposureId: widget.args?.aiProfile?.exposureId,
          dateKey: widget.args?.aiProfile?.dateKey,
          context: {
            ..._buildRecContext(button: 'message'),
            'ui': {
              ..._buildRecContext(button: 'message')['ui']
                  as Map<String, dynamic>,
              'action': 'message_button_tap',
            },
          },
        )
        .catchError(
          (e) => debugPrint('[RecEvent] message_button_tap failed: $e'),
        );

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: CupertinoColors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      builder: (sheetCtx) => _MessageBottomSheet(
        targetName: _profile?.name ?? '상대방',
        onSend: (messageText) async {
          final myProfile = await _userService.getUserProfile(uid);
          final myOnboarding = myProfile?['onboarding'] is Map
              ? Map<String, dynamic>.from(myProfile!['onboarding'] as Map)
              : <String, dynamic>{};
          final myPhotoUrls = myOnboarding['photoUrls'] is List
              ? (myOnboarding['photoUrls'] as List)
                  .whereType<String>()
                  .toList()
              : <String>[];

          final roomId = _chatService.buildDirectRoomId(uid, targetId);

          await _chatService.ensureDirectRoom(
            roomId: roomId,
            currentUserId: uid,
            partnerId: targetId,
            currentUserName: myOnboarding['nickname']?.toString() ?? '',
            partnerName: _profile?.name ?? '',
            currentUserAvatarUrl:
                myPhotoUrls.isNotEmpty ? myPhotoUrls.first : null,
            partnerAvatarUrl: _profile?.imageUrls.isNotEmpty == true
                ? _profile!.imageUrls.first
                : null,
          );

          await _chatService.sendTextMessage(
            roomId: roomId,
            senderId: uid,
            text: messageText,
          );

          _recEventService
              .logEvent(
                userId: uid,
                targetType: 'user_profile',
                targetId: targetId,
                candidateUserId: targetId,
                eventType: 'open',
                surface: 'profile_card',
                cardVariant: 'real_profile',
                exposureId: widget.args?.aiProfile?.exposureId,
                dateKey: widget.args?.aiProfile?.dateKey,
                context: {
                  ..._buildRecContext(button: 'message'),
                  'ui': {
                    ..._buildRecContext(button: 'message')['ui']
                        as Map<String, dynamic>,
                    'action': 'message_sent',
                  },
                },
              )
              .catchError(
                (e) => debugPrint('[RecEvent] message_sent failed: $e'),
              );

          widget.onMessage?.call();
        },
        onSuccess: () {
          if (!mounted) return;
          _showToast('메시지를 보냈어요 💬');
          final tId = _profile?.id ?? '';
          if (tId.isNotEmpty && _currentUserId != null) {
            final roomId =
                _chatService.buildDirectRoomId(_currentUserId!, tId);
            Navigator.of(context, rootNavigator: true).pushNamed(
              RouteNames.chatRoom,
              arguments: ChatRoomData(
                chatRoomId: roomId,
                partnerId: tId,
                partnerName: _profile?.name ?? '',
                partnerUniversity: _profile?.university ?? '',
                partnerAvatarUrl: _profile?.imageUrls.isNotEmpty == true
                    ? _profile!.imageUrls.first
                    : null,
              ),
            );
          }
        },
        onError: (e) {
          if (!mounted) return;
          _showToast('메시지를 보내지 못했어요', isError: true);
        },
      ),
    );
  }

  String _mapRelationship(String raw) {
    switch (raw) {
      case 'open':
        return '열린 만남도 괜찮아요';
      case 'serious':
        return '진지한 연애를 원해요';
      case 'casual':
      case 'friend':
        return '가볍게 알아가고 싶어요';
      case 'friendship':
        return '친구처럼 편하게 시작하고 싶어요';
      default:
        return raw;
    }
  }

  String _mapLifestyleValue(String raw) {
    switch (raw) {
      case 'nonSmoker':
        return '비흡연';
      case 'smoker':
        return '흡연';
      case 'sometimes':
        return '가끔 해요';
      case 'often':
        return '자주 해요';
      case 'never':
      case 'none':
        return '안 해요';
      case 'breathingOnly':
        return '거의 안 해요';
      case 'light':
        return '가볍게 해요';
      case 'regular':
        return '꾸준히 해요';
      case 'daily':
        return '매일 해요';
      case 'weekly1_2':
        return '주 1-2회';
      case 'quitting':
        return '금연 중';
      case 'mania':
        return '운동 매니아';
      default:
        return raw;
    }
  }

  String _mapMajor(String raw) {
    switch (raw) {
      case 'science':
        return '이과계열';
      case 'humanities':
      case 'liberalArts':
        return '문과계열';
      case 'arts':
      case 'artsSports':
        return '예체능계열';
      case 'engineering':
        return '공학계열';
      case 'business':
        return '상경계열';
      case 'education':
        return '교육계열';
      case 'medicine':
      case 'medical':
        return '의약계열';
      default:
        return raw;
    }
  }

  String _birthYearText({required dynamic birthYearRaw, required int? age}) {
    if (birthYearRaw != null) {
      final parsed = int.tryParse(birthYearRaw.toString());
      if (parsed != null && parsed > 1900) {
        final yy = (parsed % 100).toString().padLeft(2, '0');
        return '$yy년생';
      }
    }

    if (age != null) {
      final now = DateTime.now();
      final birthYear = now.year - age + 1;
      final yy = (birthYear % 100).toString().padLeft(2, '0');
      return '$yy년생';
    }

    return '';
  }

  Future<void> _loadProfile() async {
    final args = widget.args;
    final seed = args?.aiProfile;
    final targetUserId = args?.userId ?? seed?.candidateUid ?? '';

    if (targetUserId.isEmpty) {
      if (!mounted) return;
      setState(() {
        _profile = const _ResolvedProfile(
          id: '',
          name: '프로필',
          age: null,
          birthYearText: '',
          university: '',
          major: '',
          matchPercent: 0,
          aboutMe: '',
          imageUrls: [],
          interests: [],
          keywords: [],
          mbti: '',
          heightText: '',
          relationship: '',
          drinking: '',
          smoking: '',
          exercise: '',
          loveLanguages: [],
          profileQa: [],
        );
        _isLoading = false;
      });
      return;
    }

    try {
      final user = await _userService.getUserProfile(targetUserId);

      final onboardingRaw = user?['onboarding'];
      final onboarding = onboardingRaw is Map
          ? Map<String, dynamic>.from(onboardingRaw)
          : <String, dynamic>{};

      final override = args?.onboardingOverride;
      if (override != null) {
        for (final entry in override.entries) {
          onboarding[entry.key] = entry.value;
        }
      }

      final lifestyleRaw = onboarding['lifestyle'];
      final lifestyle = lifestyleRaw is Map
          ? Map<String, dynamic>.from(lifestyleRaw)
          : <String, dynamic>{};

      final photoUrlsRaw = onboarding['photoUrls'];
      final photoUrls = photoUrlsRaw is List
          ? photoUrlsRaw.whereType<String>().where((e) => e.isNotEmpty).toList()
          : <String>[];

      final interestRaw = onboarding['interests'];
      final interests = interestRaw is List
          ? interestRaw.whereType<String>().where((e) => e.isNotEmpty).toList()
          : <String>[];

      final keywordRaw = onboarding['keywords'];
      final keywords = keywordRaw is List
          ? keywordRaw.whereType<String>().where((e) => e.isNotEmpty).toList()
          : <String>[];

      final loveRaw = onboarding['loveLanguages'];
      final loveLanguages = loveRaw is List
          ? loveRaw.whereType<String>().where((e) => e.isNotEmpty).toList()
          : <String>[];

      final qaRaw = onboarding['profileQa'];
      final profileQa = <Map<String, String>>[];
      if (qaRaw is List) {
        for (final item in qaRaw) {
          if (item is Map) {
            final mapped = item.map(
              (k, v) => MapEntry(k.toString(), v?.toString() ?? ''),
            );

            if (mapped.containsKey('question') ||
                mapped.containsKey('answer')) {
              profileQa.add({
                'question': mapped['question'] ?? '',
                'answer': mapped['answer'] ?? '',
              });
            } else if (mapped.isNotEmpty) {
              profileQa.add(Map<String, String>.from(mapped));
            }
          }
        }
      }

      int? age = seed?.age;
      final onboardingAge = onboarding['age'];
      if (onboardingAge is num) {
        age = onboardingAge.toInt();
      } else if (onboardingAge != null) {
        age = int.tryParse(onboardingAge.toString()) ?? age;
      }

      final birthYearRaw = onboarding['birthYear'] ?? user?['birthYear'];

      final heightValue = onboarding['height'];
      final heightText = heightValue == null || '$heightValue'.isEmpty
          ? ''
          : '${heightValue.toString()}cm';

      final onboardingMajor = onboarding['major']?.toString() ?? '';
      final seedMajor = seed?.major ?? '';
      final rawMajor = onboardingMajor.isNotEmpty ? onboardingMajor : seedMajor;

      final onboardingNickname = onboarding['nickname']?.toString() ?? '';
      final onboardingIntro = onboarding['selfIntroduction']?.toString() ?? '';
      final onboardingUniversity = onboarding['university']?.toString() ?? '';

      final resolved = _ResolvedProfile(
        id: targetUserId,
        name: onboardingNickname.isNotEmpty
            ? onboardingNickname
            : (seed?.name ?? '프로필'),
        age: age,
        birthYearText: _birthYearText(birthYearRaw: birthYearRaw, age: age),
        university: onboardingUniversity.isNotEmpty
            ? onboardingUniversity
            : (seed?.university ?? ''),
        major: _mapMajor(rawMajor),
        matchPercent: seed?.sourceScores != null
            ? (seed!.sourceScores!.toDouble() * 100).round().clamp(0, 99)
            : (seed?.finalScore != null
                  ? (seed!.finalScore!.toDouble() * 100).round().clamp(0, 99)
                  : 0),
        aboutMe: onboardingIntro.isNotEmpty
            ? onboardingIntro
            : (seed?.bio ?? ''),
        imageUrls: photoUrls.isNotEmpty
            ? photoUrls
            : (seed?.imageUrls ?? const []),
        interests: interests,
        keywords: keywords,
        mbti: onboarding['mbti']?.toString() ?? '',
        heightText: heightText,
        relationship: _mapRelationship(
          onboarding['relationship']?.toString() ?? '',
        ),
        drinking: _mapLifestyleValue(lifestyle['drinking']?.toString() ?? ''),
        smoking: _mapLifestyleValue(lifestyle['smoking']?.toString() ?? ''),
        exercise: _mapLifestyleValue(lifestyle['exercise']?.toString() ?? ''),
        loveLanguages: loveLanguages,
        profileQa: profileQa,
      );

      if (!mounted) return;
      setState(() {
        _profile = resolved;
        _isLoading = false;
      });
    } catch (e) {
      debugPrint('AiMatchProfileScreen load profile error: $e');

      if (!mounted) return;
      setState(() {
        _profile = _ResolvedProfile(
          id: targetUserId,
          name: seed?.name ?? '프로필',
          age: seed?.age,
          birthYearText: _birthYearText(birthYearRaw: null, age: seed?.age),
          university: seed?.university ?? '',
          major: _mapMajor(seed?.major ?? ''),
          matchPercent: 0,
          aboutMe: seed?.bio ?? '',
          imageUrls: seed?.imageUrls ?? const [],
          interests: seed?.tags ?? const [],
          keywords: const [],
          mbti: '',
          heightText: '',
          relationship: '',
          drinking: '',
          smoking: '',
          exercise: '',
          loveLanguages: const [],
          profileQa: const [],
        );
        _isLoading = false;
      });
    }
  }

  void _showMoreOptions(BuildContext context) {
    final targetUserId = _profile?.id ?? '';
    if (targetUserId.isEmpty) return;

    showCupertinoModalPopup(
      context: context,
      builder: (BuildContext ctx) {
        return CupertinoActionSheet(
          actions: <CupertinoActionSheetAction>[
            CupertinoActionSheetAction(
              isDestructiveAction: true,
              onPressed: () {
                Navigator.pop(ctx);
                _showReportDialog(context, targetUserId);
              },
              child: const Text(
                '신고 및 차단',
                style: TextStyle(fontFamily: _kFontFamily),
              ),
            ),
          ],
          cancelButton: CupertinoActionSheetAction(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('취소', style: TextStyle(fontFamily: _kFontFamily)),
          ),
        );
      },
    );
  }

  void _showReportDialog(BuildContext parentContext, String targetUserId) {
    final TextEditingController reasonController = TextEditingController();

    showCupertinoDialog(
      context: parentContext,
      builder: (dialogCtx) {
        bool isSubmitting = false;

        return StatefulBuilder(
          builder: (context, setState) {
            return CupertinoAlertDialog(
              title: const Text(
                '신고 및 차단',
                style: TextStyle(fontFamily: _kFontFamily),
              ),
              content: Column(
                children: [
                  const SizedBox(height: 10),
                  const Text(
                    '이 사용자를 신고하고 추천에서 차단하시겠어요?\n사유를 간략히 적어주세요.',
                    style: TextStyle(fontFamily: _kFontFamily),
                  ),
                  const SizedBox(height: 16),
                  CupertinoTextField(
                    controller: reasonController,
                    placeholder: '신고 사유 입력',
                    style: const TextStyle(fontFamily: _kFontFamily),
                    placeholderStyle: TextStyle(
                      fontFamily: _kFontFamily,
                      color: CupertinoColors.placeholderText,
                    ),
                  ),
                ],
              ),
              actions: [
                CupertinoDialogAction(
                  isDestructiveAction: true,
                  onPressed: () => Navigator.pop(dialogCtx),
                  child: const Text(
                    '취소',
                    style: TextStyle(fontFamily: _kFontFamily),
                  ),
                ),
                CupertinoDialogAction(
                  isDefaultAction: true,
                  onPressed: isSubmitting
                      ? null
                      : () async {
                          final reason = reasonController.text.trim();
                          if (reason.isEmpty) return;

                          setState(() => isSubmitting = true);

                          try {
                            final currentUserId = await _storageService
                                .getKakaoUserId();

                            if (currentUserId == null ||
                                currentUserId.trim().isEmpty) {
                              throw Exception('Kakao user id not found');
                            }

                            await InteractionService().blockAndReportUser(
                              fromUserId: currentUserId,
                              toUserId: targetUserId,
                              reason: reason,
                            );

                            if (!mounted) return;

                            if (dialogCtx.mounted) {
                              Navigator.pop(dialogCtx);
                            }

                            showCupertinoDialog(
                              context: parentContext,
                              builder: (successCtx) => CupertinoAlertDialog(
                                title: const Text(
                                  '신고 완료',
                                  style: TextStyle(fontFamily: _kFontFamily),
                                ),
                                content: const Text(
                                  '신고가 접수되었습니다.',
                                  style: TextStyle(fontFamily: _kFontFamily),
                                ),
                                actions: [
                                  CupertinoDialogAction(
                                    isDefaultAction: true,
                                    onPressed: () {
                                      Navigator.pop(successCtx);
                                      if (mounted) {
                                        Navigator.of(parentContext).pop();
                                      }
                                    },
                                    child: const Text(
                                      '확인',
                                      style: TextStyle(
                                        fontFamily: _kFontFamily,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            );
                          } catch (e) {
                            debugPrint('Report error: $e');

                            if (dialogCtx.mounted) {
                              setState(() => isSubmitting = false);
                            }

                            showCupertinoDialog(
                              context: parentContext,
                              builder: (errorCtx) => CupertinoAlertDialog(
                                title: const Text(
                                  '신고 실패',
                                  style: TextStyle(fontFamily: _kFontFamily),
                                ),
                                content: const Text(
                                  '신고를 저장하지 못했어요. 다시 시도해주세요.',
                                  style: TextStyle(fontFamily: _kFontFamily),
                                ),
                                actions: [
                                  CupertinoDialogAction(
                                    onPressed: () => Navigator.pop(errorCtx),
                                    child: const Text(
                                      '확인',
                                      style: TextStyle(
                                        fontFamily: _kFontFamily,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            );
                          }
                        },
                  child: isSubmitting
                      ? const CupertinoActivityIndicator()
                      : const Text(
                          '확인',
                          style: TextStyle(fontFamily: _kFontFamily),
                        ),
                ),
              ],
            );
          },
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;
    final profile = _profile;

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.blush,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: _AppColors.blush.withValues(alpha: 0.95),
        border: null,
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {
            HapticFeedback.lightImpact();
            if (widget.onBack != null) {
              widget.onBack!();
            } else {
              Navigator.of(context, rootNavigator: true).pop();
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
              CupertinoIcons.chevron_down,
              size: 28,
              color: _AppColors.textMain,
            ),
          ),
        ),
        middle: Text(
          widget.args?.isPreview == true
              ? '미리보기'
              : (widget.args?.aiProfile != null ? '프로필 상세' : '프로필'),
          style: TextStyle(
            fontFamily: _kFontFamily,
            fontSize: 14,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.2,
            color: _AppColors.primary.withValues(alpha: 0.9),
          ),
        ),
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: widget.args?.isPreview == true
              ? null
              : (widget.onMore ?? () => _showMoreOptions(context)),
          child: Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: CupertinoColors.black.withValues(alpha: 0.05),
            ),
            child: Icon(
              CupertinoIcons.ellipsis,
              size: 24,
              color: widget.args?.isPreview == true
                  ? _AppColors.textSub.withValues(alpha: 0.5)
                  : _AppColors.textMain,
            ),
          ),
        ),
      ),
      child: Stack(
        children: [
          SafeArea(
            child: _isLoading
                ? const Center(child: CupertinoActivityIndicator())
                : profile == null
                ? const Center(
                    child: Text(
                      '프로필을 불러올 수 없어요',
                      style: TextStyle(
                        fontFamily: _kFontFamily,
                        fontSize: 16,
                        color: _AppColors.textSub,
                      ),
                    ),
                  )
                : SingleChildScrollView(
                    physics: const BouncingScrollPhysics(),
                    padding: EdgeInsets.fromLTRB(
                      16,
                      16,
                      16,
                      bottomPadding +
                          ((widget.args?.showActions ?? true) ? 140 : 32),
                    ),
                    child: _ProfileCard(
                      profile: profile,
                      heroImageIndex: _heroImageIndex,
                      onHeroImageChanged: (index) {
                        setState(() {
                          _heroImageIndex = index;
                        });
                      },
                    ),
                  ),
          ),
          if (widget.args?.showActions != false)
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: _BottomActionBar(
                bottomPadding: bottomPadding,
                onQna: _handleAsk,
                onPass: _handleNope,
                onLike: _handleLike,
                onMessage: _handleMessage,
                isLikeInFlight: _isLikeInFlight,
                isNopeInFlight: _isNopeInFlight,
              ),
            ),
        ],
      ),
    );
  }
}

class _ProfileCard extends StatelessWidget {
  final _ResolvedProfile profile;
  final int heroImageIndex;
  final ValueChanged<int> onHeroImageChanged;

  const _ProfileCard({
    required this.profile,
    required this.heroImageIndex,
    required this.onHeroImageChanged,
  });

  @override
  Widget build(BuildContext context) {
    final identityParts = <String>[
      if (profile.university.isNotEmpty) profile.university,
    ];

    return Container(
      decoration: BoxDecoration(
        color: _AppColors.cardSurface,
        borderRadius: BorderRadius.circular(40),
        boxShadow: [
          BoxShadow(
            color: _AppColors.primary.withValues(alpha: 0.10),
            blurRadius: 36,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _HeroImage(
            imageUrls: profile.imageUrls,
            currentIndex: heroImageIndex,
            onPageChanged: onHeroImageChanged,
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 12, 24, 40),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  profile.name,
                  style: const TextStyle(
                    fontFamily: _kFontFamily,
                    fontSize: 36,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.5,
                    color: _AppColors.textMain,
                  ),
                ),
                const SizedBox(height: 6),
                if (identityParts.isNotEmpty)
                  Row(
                    children: [
                      const Icon(
                        CupertinoIcons.building_2_fill,
                        size: 18,
                        color: _AppColors.textSub,
                      ),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          identityParts.join(' • '),
                          style: const TextStyle(
                            fontFamily: _kFontFamily,
                            fontSize: 16,
                            fontWeight: FontWeight.w500,
                            color: _AppColors.textSub,
                          ),
                        ),
                      ),
                    ],
                  ),
                const SizedBox(height: 24),
                if (profile.mbti.isNotEmpty ||
                    profile.heightText.isNotEmpty ||
                    profile.relationship.isNotEmpty ||
                    profile.birthYearText.isNotEmpty ||
                    profile.major.isNotEmpty) ...[
                  const _SectionTitle(text: '기본 정보'),
                  const SizedBox(height: 10),
                  _SectionCard(
                    child: Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      children: [
                        if (profile.birthYearText.isNotEmpty)
                          _InfoChip(label: '출생', value: profile.birthYearText),
                        if (profile.mbti.isNotEmpty)
                          _InfoChip(label: 'MBTI', value: profile.mbti),
                        if (profile.heightText.isNotEmpty)
                          _InfoChip(label: '키', value: profile.heightText),
                        if (profile.major.isNotEmpty)
                          _InfoChip(label: '계열', value: profile.major),
                        if (profile.relationship.isNotEmpty)
                          _InfoChip(label: '연애관', value: profile.relationship),
                      ],
                    ),
                  ),
                  const SizedBox(height: 18),
                ],
                if (profile.aboutMe.isNotEmpty) ...[
                  const _SectionTitle(text: '저는 이런 사람이에요!'),
                  const SizedBox(height: 10),
                  _SectionCard(
                    child: Text(
                      profile.aboutMe,
                      style: const TextStyle(
                        fontFamily: _kFontFamily,
                        fontSize: 16,
                        height: 1.65,
                        color: _AppColors.textSub,
                      ),
                    ),
                  ),
                  const SizedBox(height: 18),
                ],
                if (profile.chips.isNotEmpty) ...[
                  const _SectionTitle(text: '요즘 관심 있는 것들!'),
                  const SizedBox(height: 10),
                  _SectionCard(
                    child: Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      children: profile.chips.map((interest) {
                        return _TagChip(text: interest);
                      }).toList(),
                    ),
                  ),
                  const SizedBox(height: 18),
                ],
                if (profile.drinking.isNotEmpty ||
                    profile.smoking.isNotEmpty ||
                    profile.exercise.isNotEmpty) ...[
                  const _SectionTitle(text: '평소에는...'),
                  const SizedBox(height: 10),
                  _SectionCard(
                    child: Column(
                      children: [
                        if (profile.drinking.isNotEmpty)
                          _LifestyleRow(label: '음주', value: profile.drinking),
                        if (profile.drinking.isNotEmpty &&
                            (profile.smoking.isNotEmpty ||
                                profile.exercise.isNotEmpty))
                          const SizedBox(height: 10),
                        if (profile.smoking.isNotEmpty)
                          _LifestyleRow(label: '흡연', value: profile.smoking),
                        if (profile.smoking.isNotEmpty &&
                            profile.exercise.isNotEmpty)
                          const SizedBox(height: 10),
                        if (profile.exercise.isNotEmpty)
                          _LifestyleRow(label: '운동', value: profile.exercise),
                      ],
                    ),
                  ),
                  if (profile.profileQa.isNotEmpty) ...[
                    const SizedBox(height: 14),
                    _SectionCard(
                      child: Column(
                        children: profile.profileQa.map((item) {
                          final question = item['question'] ?? '';
                          final answer = item['answer'] ?? '';

                          return Padding(
                            padding: EdgeInsets.only(
                              bottom: item == profile.profileQa.last ? 0 : 16,
                            ),
                            child: _QaItem(question: question, answer: answer),
                          );
                        }).toList(),
                      ),
                    ),
                  ],
                  const SizedBox(height: 18),
                ],
                if (profile.loveLanguages.isNotEmpty) ...[
                  const _SectionTitle(text: '사랑의 언어'),
                  const SizedBox(height: 10),
                  _SectionCard(
                    child: Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      children: profile.loveLanguages.map((item) {
                        return _TagChip(text: item);
                      }).toList(),
                    ),
                  ),
                  const SizedBox(height: 18),
                ],
                if (profile.imageUrls.isNotEmpty) ...[
                  const _SectionTitle(text: '나의 모습!'),
                  const SizedBox(height: 10),
                  _SectionCard(
                    child: _MyGallerySlider(imageUrls: profile.imageUrls),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _HeroImage extends StatelessWidget {
  final List<String> imageUrls;
  final int currentIndex;
  final ValueChanged<int> onPageChanged;

  const _HeroImage({
    required this.imageUrls,
    required this.currentIndex,
    required this.onPageChanged,
  });

  @override
  Widget build(BuildContext context) {
    final safeImages = imageUrls.isNotEmpty ? imageUrls : [''];

    return SizedBox(
      height: 520,
      width: double.infinity,
      child: Stack(
        fit: StackFit.expand,
        children: [
          PageView.builder(
            itemCount: safeImages.length,
            onPageChanged: onPageChanged,
            itemBuilder: (context, index) {
              final imageUrl = safeImages[index];
              if (imageUrl.isEmpty) {
                return Container(
                  color: _AppColors.gray100,
                  child: const Center(
                    child: Icon(
                      CupertinoIcons.person_fill,
                      size: 72,
                      color: _AppColors.gray300,
                    ),
                  ),
                );
              }

              return Image.network(
                imageUrl,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => Container(
                  color: _AppColors.gray100,
                  child: const Center(
                    child: Icon(
                      CupertinoIcons.person_fill,
                      size: 72,
                      color: _AppColors.gray300,
                    ),
                  ),
                ),
              );
            },
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            height: 220,
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    _AppColors.cardSurface.withValues(alpha: 0),
                    _AppColors.cardSurface.withValues(alpha: 0.25),
                    _AppColors.cardSurface.withValues(alpha: 0.94),
                  ],
                ),
              ),
            ),
          ),
          if (safeImages.length > 1)
            Positioned(
              left: 0,
              right: 0,
              bottom: 86,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(safeImages.length, (index) {
                  final isActive = index == currentIndex;
                  return AnimatedContainer(
                    duration: const Duration(milliseconds: 180),
                    width: isActive ? 20 : 8,
                    height: 8,
                    margin: const EdgeInsets.symmetric(horizontal: 4),
                    decoration: BoxDecoration(
                      color: isActive
                          ? _AppColors.primary
                          : _AppColors.primary.withValues(alpha: 0.28),
                      borderRadius: BorderRadius.circular(999),
                    ),
                  );
                }),
              ),
            ),
        ],
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  final String text;

  const _SectionTitle({required this.text});

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        fontFamily: _kFontFamily,
        fontSize: 16,
        fontWeight: FontWeight.w700,
        color: _AppColors.titleLight,
        letterSpacing: -0.1,
      ),
    );
  }
}

class _SectionCard extends StatelessWidget {
  final Widget child;

  const _SectionCard({required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: CupertinoColors.white,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: _AppColors.gray200),
        boxShadow: [
          BoxShadow(
            color: _AppColors.primary.withValues(alpha: 0.06),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: child,
    );
  }
}

class _InfoChip extends StatelessWidget {
  final String label;
  final String value;

  const _InfoChip({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [_AppColors.chipBg, _AppColors.chipBg2],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: _AppColors.softPink),
        boxShadow: [
          BoxShadow(
            color: _AppColors.primary.withValues(alpha: 0.04),
            blurRadius: 8,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: RichText(
        text: TextSpan(
          children: [
            TextSpan(
              text: '$label  ',
              style: const TextStyle(
                fontFamily: _kFontFamily,
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: _AppColors.primary,
              ),
            ),
            TextSpan(
              text: value,
              style: const TextStyle(
                fontFamily: _kFontFamily,
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: _AppColors.textMain,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TagChip extends StatelessWidget {
  final String text;

  const _TagChip({required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [_AppColors.chipBg, _AppColors.chipBg2],
        ),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: _AppColors.softPink),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.035),
            blurRadius: 6,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Text(
        text,
        style: const TextStyle(
          fontFamily: _kFontFamily,
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: _AppColors.textMain,
        ),
      ),
    );
  }
}

class _LifestyleRow extends StatelessWidget {
  final String label;
  final String value;

  const _LifestyleRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Text(
          label,
          style: const TextStyle(
            fontFamily: _kFontFamily,
            fontSize: 14,
            fontWeight: FontWeight.w700,
            color: _AppColors.primary,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            value,
            style: const TextStyle(
              fontFamily: _kFontFamily,
              fontSize: 15,
              height: 1.4,
              color: _AppColors.textSub,
            ),
          ),
        ),
      ],
    );
  }
}

class _QaItem extends StatelessWidget {
  final String question;
  final String answer;

  const _QaItem({required this.question, required this.answer});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [CupertinoColors.white, _AppColors.backgroundLight],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: _AppColors.gray200),
        boxShadow: [
          BoxShadow(
            color: _AppColors.primary.withValues(alpha: 0.05),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            question,
            style: const TextStyle(
              fontFamily: _kFontFamily,
              fontSize: 13,
              fontWeight: FontWeight.w700,
              color: _AppColors.primary,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            answer.isNotEmpty ? answer : '아직 작성한 답변이 없어요.',
            style: const TextStyle(
              fontFamily: _kFontFamily,
              fontSize: 14,
              height: 1.55,
              color: _AppColors.textMain,
            ),
          ),
        ],
      ),
    );
  }
}

class _MyGallerySlider extends StatelessWidget {
  final List<String> imageUrls;

  const _MyGallerySlider({required this.imageUrls});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 210,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        physics: const BouncingScrollPhysics(),
        itemCount: imageUrls.length,
        separatorBuilder: (_, __) => const SizedBox(width: 12),
        itemBuilder: (context, index) {
          final url = imageUrls[index];
          return Container(
            width: 150,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(22),
              color: _AppColors.gray100,
              boxShadow: [
                BoxShadow(
                  color: _AppColors.primary.withValues(alpha: 0.08),
                  blurRadius: 14,
                  offset: const Offset(0, 6),
                ),
              ],
            ),
            clipBehavior: Clip.antiAlias,
            child: Image.network(
              url,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => const Center(
                child: Icon(
                  CupertinoIcons.person_fill,
                  size: 38,
                  color: _AppColors.gray300,
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _BottomActionBar extends StatelessWidget {
  final double bottomPadding;
  final VoidCallback? onQna;
  final VoidCallback? onPass;
  final VoidCallback? onLike;
  final VoidCallback? onMessage;
  final bool isLikeInFlight;
  final bool isNopeInFlight;

  const _BottomActionBar({
    required this.bottomPadding,
    this.onQna,
    this.onPass,
    this.onLike,
    this.onMessage,
    this.isLikeInFlight = false,
    this.isNopeInFlight = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(24, 16, 24, bottomPadding + 24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            _AppColors.blush.withValues(alpha: 0),
            _AppColors.blush.withValues(alpha: 0.95),
            _AppColors.blush,
          ],
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          _ActionButton(
            icon: CupertinoIcons.chat_bubble_text,
            size: 56,
            iconSize: 26,
            isSecondary: true,
            onPressed: onQna,
          ),
          _ActionButton(
            icon: CupertinoIcons.xmark,
            size: 64,
            iconSize: 32,
            isSecondary: true,
            isInFlight: isNopeInFlight,
            onPressed: onPass,
          ),
          _ActionButton(
            icon: CupertinoIcons.heart_fill,
            size: 80,
            iconSize: 40,
            isPrimary: true,
            isInFlight: isLikeInFlight,
            onPressed: onLike,
          ),
          _ActionButton(
            icon: CupertinoIcons.paperplane_fill,
            size: 56,
            iconSize: 26,
            isSecondary: true,
            onPressed: onMessage,
          ),
        ],
      ),
    );
  }
}

class _ActionButton extends StatefulWidget {
  final IconData icon;
  final double size;
  final double iconSize;
  final bool isPrimary;
  final bool isSecondary;
  final bool isInFlight;
  final VoidCallback? onPressed;

  const _ActionButton({
    required this.icon,
    required this.size,
    required this.iconSize,
    this.isPrimary = false,
    this.isSecondary = false,
    this.isInFlight = false,
    this.onPressed,
  });

  @override
  State<_ActionButton> createState() => _ActionButtonState();
}

class _ActionButtonState extends State<_ActionButton>
    with SingleTickerProviderStateMixin {
  double _scale = 1.0;

  void _onTapDown(TapDownDetails _) {
    setState(() => _scale = 0.92);
  }

  void _onTapUp(TapUpDetails _) {
    setState(() => _scale = 1.0);
    widget.onPressed?.call();
  }

  void _onTapCancel() {
    setState(() => _scale = 1.0);
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: _onTapDown,
      onTapUp: _onTapUp,
      onTapCancel: _onTapCancel,
      child: AnimatedScale(
        scale: _scale,
        duration: const Duration(milliseconds: 120),
        curve: Curves.easeOutCubic,
        child: AnimatedOpacity(
          opacity: widget.isInFlight ? 0.5 : 1.0,
          duration: const Duration(milliseconds: 200),
          child: Container(
            width: widget.size,
            height: widget.size,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: widget.isPrimary
                  ? _AppColors.primary
                  : CupertinoColors.white,
              border: widget.isSecondary
                  ? Border.all(color: _AppColors.gray200)
                  : null,
              boxShadow: [
                BoxShadow(
                  color: widget.isPrimary
                      ? _AppColors.primary.withValues(alpha: 0.28)
                      : CupertinoColors.black.withValues(alpha: 0.07),
                  blurRadius: widget.isPrimary ? 20 : 12,
                  offset: Offset(0, widget.isPrimary ? 8 : 4),
                ),
              ],
            ),
            child: widget.isInFlight
                ? const CupertinoActivityIndicator()
                : Icon(
                    widget.icon,
                    size: widget.iconSize,
                    color: widget.isPrimary
                        ? CupertinoColors.white
                        : _AppColors.textSub,
                  ),
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// Overlay 기반 토스트 (쿠퍼티노 스타일)
// =============================================================================
class _ToastOverlay extends StatefulWidget {
  final String message;
  final bool isError;
  final VoidCallback onDismiss;

  const _ToastOverlay({
    required this.message,
    required this.isError,
    required this.onDismiss,
  });

  @override
  State<_ToastOverlay> createState() => _ToastOverlayState();
}

class _ToastOverlayState extends State<_ToastOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _opacity;
  late final Animation<Offset> _slide;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _opacity = CurvedAnimation(parent: _controller, curve: Curves.easeOut);
    _slide = Tween<Offset>(
      begin: const Offset(0, 0.3),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic));
    _controller.forward();

    Future.delayed(const Duration(seconds: 2), () {
      if (!mounted) return;
      _controller.reverse().then((_) {
        if (mounted) widget.onDismiss();
      });
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;
    return Positioned(
      left: 24,
      right: 24,
      bottom: bottomPadding + 140,
      child: SlideTransition(
        position: _slide,
        child: FadeTransition(
          opacity: _opacity,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
            decoration: BoxDecoration(
              color: widget.isError
                  ? const Color(0xFF4A2020)
                  : const Color(0xFF1E1A1C),
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(
                  color: CupertinoColors.black.withValues(alpha: 0.18),
                  blurRadius: 20,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            child: Row(
              children: [
                Icon(
                  widget.isError
                      ? CupertinoIcons.exclamationmark_circle_fill
                      : CupertinoIcons.checkmark_circle_fill,
                  color: widget.isError
                      ? const Color(0xFFFF6B6B)
                      : _AppColors.primary,
                  size: 22,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    widget.message,
                    style: const TextStyle(
                      fontFamily: _kFontFamily,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      color: CupertinoColors.white,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 무물(Ask) 바텀시트
// =============================================================================
class _AskBottomSheet extends StatefulWidget {
  final String targetName;
  final Future<void> Function(String question) onSend;
  final VoidCallback onSuccess;
  final void Function(dynamic error) onError;

  const _AskBottomSheet({
    required this.targetName,
    required this.onSend,
    required this.onSuccess,
    required this.onError,
  });

  @override
  State<_AskBottomSheet> createState() => _AskBottomSheetState();
}

class _AskBottomSheetState extends State<_AskBottomSheet> {
  final TextEditingController _controller = TextEditingController();
  bool _isSending = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final text = _controller.text.trim();
    if (text.isEmpty || _isSending) return;
    setState(() => _isSending = true);

    try {
      await widget.onSend(text);
      if (!mounted) return;
      Navigator.pop(context);
      widget.onSuccess();
    } catch (e) {
      if (!mounted) return;
      setState(() => _isSending = false);
      widget.onError(e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottomInsets = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.only(bottom: bottomInsets),
      child: Container(
        constraints: const BoxConstraints(maxHeight: 420),
        padding: const EdgeInsets.fromLTRB(24, 20, 24, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 드래그 핸들
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: _AppColors.softPink,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 20),
            Text(
              '무물하기 💌',
              style: const TextStyle(
                fontFamily: _kFontFamily,
                fontSize: 20,
                fontWeight: FontWeight.w700,
                color: _AppColors.textMain,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              '${widget.targetName}님에게 궁금한 것을 물어보세요',
              style: const TextStyle(
                fontFamily: _kFontFamily,
                fontSize: 14,
                color: _AppColors.textSub,
              ),
            ),
            const SizedBox(height: 16),
            Flexible(
              child: CupertinoTextField(
                controller: _controller,
                placeholder: '예) 주말에 보통 뭐 하며 보내세요?',
                maxLines: 5,
                minLines: 3,
                maxLength: 200,
                style: const TextStyle(
                  fontFamily: _kFontFamily,
                  fontSize: 15,
                  color: _AppColors.textMain,
                ),
                placeholderStyle: TextStyle(
                  fontFamily: _kFontFamily,
                  fontSize: 15,
                  color: _AppColors.textSub.withValues(alpha: 0.5),
                ),
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: _AppColors.gray100,
                  borderRadius: BorderRadius.circular(16),
                ),
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: CupertinoButton(
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    color: _AppColors.gray100,
                    borderRadius: BorderRadius.circular(14),
                    onPressed: () => Navigator.pop(context),
                    child: const Text(
                      '취소',
                      style: TextStyle(
                        fontFamily: _kFontFamily,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        color: _AppColors.textSub,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CupertinoButton(
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    color: _AppColors.primary,
                    borderRadius: BorderRadius.circular(14),
                    onPressed: _isSending ? null : _submit,
                    child: _isSending
                        ? const CupertinoActivityIndicator(
                            color: CupertinoColors.white,
                          )
                        : const Text(
                            '보내기',
                            style: TextStyle(
                              fontFamily: _kFontFamily,
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                              color: CupertinoColors.white,
                            ),
                          ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 메시지 보내기 바텀시트
// =============================================================================
class _MessageBottomSheet extends StatefulWidget {
  final String targetName;
  final Future<void> Function(String message) onSend;
  final VoidCallback onSuccess;
  final void Function(dynamic error) onError;

  const _MessageBottomSheet({
    required this.targetName,
    required this.onSend,
    required this.onSuccess,
    required this.onError,
  });

  @override
  State<_MessageBottomSheet> createState() => _MessageBottomSheetState();
}

class _MessageBottomSheetState extends State<_MessageBottomSheet> {
  final TextEditingController _controller = TextEditingController();
  bool _isSending = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final text = _controller.text.trim();
    if (text.isEmpty || _isSending) return;
    setState(() => _isSending = true);

    try {
      await widget.onSend(text);
      if (!mounted) return;
      Navigator.pop(context);
      widget.onSuccess();
    } catch (e) {
      if (!mounted) return;
      setState(() => _isSending = false);
      widget.onError(e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottomInsets = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.only(bottom: bottomInsets),
      child: Container(
        constraints: const BoxConstraints(maxHeight: 420),
        padding: const EdgeInsets.fromLTRB(24, 20, 24, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: _AppColors.softPink,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              '메시지 보내기',
              style: TextStyle(
                fontFamily: _kFontFamily,
                fontSize: 20,
                fontWeight: FontWeight.w700,
                color: _AppColors.textMain,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              '${widget.targetName}님에게 첫 메시지를 보내보세요',
              style: const TextStyle(
                fontFamily: _kFontFamily,
                fontSize: 14,
                color: _AppColors.textSub,
              ),
            ),
            const SizedBox(height: 16),
            Flexible(
              child: CupertinoTextField(
                controller: _controller,
                placeholder: '예) 안녕하세요! 프로필 보고 관심이 생겼어요 :)',
                maxLines: 5,
                minLines: 3,
                maxLength: 500,
                style: const TextStyle(
                  fontFamily: _kFontFamily,
                  fontSize: 15,
                  color: _AppColors.textMain,
                ),
                placeholderStyle: TextStyle(
                  fontFamily: _kFontFamily,
                  fontSize: 15,
                  color: _AppColors.textSub.withValues(alpha: 0.5),
                ),
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: _AppColors.gray100,
                  borderRadius: BorderRadius.circular(16),
                ),
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: CupertinoButton(
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    color: _AppColors.gray100,
                    borderRadius: BorderRadius.circular(14),
                    onPressed: () => Navigator.pop(context),
                    child: const Text(
                      '취소',
                      style: TextStyle(
                        fontFamily: _kFontFamily,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        color: _AppColors.textSub,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CupertinoButton(
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    color: _AppColors.primary,
                    borderRadius: BorderRadius.circular(14),
                    onPressed: _isSending ? null : _submit,
                    child: _isSending
                        ? const CupertinoActivityIndicator(
                            color: CupertinoColors.white,
                          )
                        : const Text(
                            '보내기',
                            style: TextStyle(
                              fontFamily: _kFontFamily,
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                              color: CupertinoColors.white,
                            ),
                          ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
