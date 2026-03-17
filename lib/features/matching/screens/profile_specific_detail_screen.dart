import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../services/ai_recommendation_service.dart';
import '../../../services/interaction_service.dart';
import '../../../services/user_service.dart';
import '../models/profile_card_args.dart';

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

  _ResolvedProfile? _profile;
  bool _isLoading = true;
  int _heroImageIndex = 0;

  @override
  void initState() {
    super.initState();
    _loadProfile();
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
              child: const Text('신고 및 차단'),
            ),
          ],
          cancelButton: CupertinoActionSheetAction(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('취소'),
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
              title: const Text('신고 및 차단'),
              content: Column(
                children: [
                  const SizedBox(height: 10),
                  const Text('이 사용자를 신고하고 추천에서 차단하시겠어요?\n사유를 간략히 적어주세요.'),
                  const SizedBox(height: 16),
                  CupertinoTextField(
                    controller: reasonController,
                    placeholder: '신고 사유 입력',
                  ),
                ],
              ),
              actions: [
                CupertinoDialogAction(
                  isDestructiveAction: true,
                  onPressed: () => Navigator.pop(ctx),
                  child: const Text('취소'),
                ),
                CupertinoDialogAction(
                  isDefaultAction: true,
                  onPressed: isSubmitting
                      ? null
                      : () async {
                          if (reasonController.text.trim().isEmpty) return;

                          setState(() => isSubmitting = true);

                          try {
                            final currentUserId =
                                FirebaseAuth.instance.currentUser?.uid;
                            if (currentUserId == null) {
                              if (ctx.mounted) Navigator.pop(ctx);
                              return;
                            }

                            await InteractionService().blockAndReportUser(
                              fromUserId: currentUserId,
                              toUserId: targetUserId,
                              reason: reasonController.text.trim(),
                            );

                            if (ctx.mounted) {
                              Navigator.pop(ctx);
                              Navigator.of(context).pop();
                            }
                          } catch (e) {
                            setState(() => isSubmitting = false);
                            debugPrint('Report error: $e');
                          }
                        },
                  child: isSubmitting
                      ? const CupertinoActivityIndicator()
                      : const Text('확인'),
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
                      style: TextStyle(fontSize: 16, color: _AppColors.textSub),
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
                onQna: widget.onQna,
                onPass: widget.onPass,
                onLike: widget.onLike,
                onMessage: widget.onMessage,
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
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: _AppColors.primary,
              ),
            ),
            TextSpan(
              text: value,
              style: const TextStyle(
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
              fontSize: 13,
              fontWeight: FontWeight.w700,
              color: _AppColors.primary,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            answer.isNotEmpty ? answer : '아직 작성한 답변이 없어요.',
            style: const TextStyle(
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

  const _BottomActionBar({
    required this.bottomPadding,
    this.onQna,
    this.onPass,
    this.onLike,
    this.onMessage,
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
            onPressed: onPass,
          ),
          _ActionButton(
            icon: CupertinoIcons.heart_fill,
            size: 80,
            iconSize: 40,
            isPrimary: true,
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

class _ActionButton extends StatelessWidget {
  final IconData icon;
  final double size;
  final double iconSize;
  final bool isPrimary;
  final bool isSecondary;
  final VoidCallback? onPressed;

  const _ActionButton({
    required this.icon,
    required this.size,
    required this.iconSize,
    this.isPrimary = false,
    this.isSecondary = false,
    this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () {
        HapticFeedback.mediumImpact();
        onPressed?.call();
      },
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: isPrimary ? _AppColors.primary : CupertinoColors.white,
          border: isSecondary ? Border.all(color: _AppColors.gray200) : null,
          boxShadow: [
            BoxShadow(
              color: isPrimary
                  ? _AppColors.primary.withValues(alpha: 0.28)
                  : CupertinoColors.black.withValues(alpha: 0.07),
              blurRadius: isPrimary ? 20 : 12,
              offset: Offset(0, isPrimary ? 8 : 4),
            ),
          ],
        ),
        child: Icon(
          icon,
          size: iconSize,
          color: isPrimary ? CupertinoColors.white : _AppColors.textSub,
        ),
      ),
    );
  }
}
