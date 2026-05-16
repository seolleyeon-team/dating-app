// =============================================================================
// 이상형 라이프 스타일 선택 화면 (Step 3 of 6)
// 경로: lib/features/onboarding/screens/ideal_type/ideal_lifestyle_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const IdealLifestyleScreen()),
// );
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../../../router/route_names.dart';
import '../../../../services/onboarding_save_helper.dart';
import '../../../../services/storage_service.dart';
import '../../../../services/user_service.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF5468C);
  static const Color backgroundLight = Color(0xFFFAFAFA);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color textSub = Color(0xFF6B7280);
  static const Color chipDefault = Color(0xFFF5F5F5);
  static const Color dotInactive = Color(0xFFEDE8EB);
}

// =============================================================================
// 데이터 모델
// =============================================================================
enum DrinkingFrequency { none, sometimes, weekly1_2, often }

enum SmokingStatus { nonSmoker, smoker, quitting }

enum ExerciseFrequency { daily, sometimes, breathingOnly, mania }

enum Religion { none, christianity, catholic, buddhism, other }

// =============================================================================
// 메인 화면
// =============================================================================
class IdealLifestyleScreen extends StatefulWidget {
  final int currentStep;
  final int totalSteps;
  final VoidCallback? onBack;
  final Function(
    DrinkingFrequency? drinking,
    SmokingStatus? smoking,
    ExerciseFrequency? exercise,
    Religion? religion,
  )?
  onNext;

  const IdealLifestyleScreen({
    super.key,
    this.currentStep = 2,
    this.totalSteps = 3,
    this.onBack,
    this.onNext,
  });

  @override
  State<IdealLifestyleScreen> createState() => _IdealLifestyleScreenState();
}

class _IdealLifestyleScreenState extends State<IdealLifestyleScreen> {
  DrinkingFrequency? _drinking;
  SmokingStatus? _smoking;
  ExerciseFrequency? _exercise;
  Religion? _religion;
  final StorageService _storageService = StorageService();
  final UserService _userService = UserService();
  bool _isSavingOnExit = false;
  bool _isSkipping = false;

  bool get _hasAnySelection =>
      _drinking != null ||
      _smoking != null ||
      _exercise != null ||
      _religion != null;

  @override
  void initState() {
    super.initState();
    _loadExistingIdealLifestyle();
  }

  Future<void> _loadExistingIdealLifestyle() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) return;
    final data = await _userService.getUserProfile(kakaoUserId);
    if (!mounted || data == null) return;
    final idealType = data['idealType'];
    if (idealType is! Map) return;
    final lifestyle = idealType['preferredLifestyles'];
    if (lifestyle is! Map) return;
    final d = lifestyle['drinking']?.toString();
    final s = lifestyle['smoking']?.toString();
    final e = lifestyle['exercise']?.toString();
    final r = lifestyle['religion']?.toString();
    final isLegacyDefault =
        d == DrinkingFrequency.sometimes.name &&
        s == SmokingStatus.nonSmoker.name &&
        e == ExerciseFrequency.breathingOnly.name &&
        (r == null || r.isEmpty);
    if (isLegacyDefault) return;
    if (d != null && d.isNotEmpty) {
      try {
        _drinking = DrinkingFrequency.values.firstWhere((v) => v.name == d);
      } catch (_) {}
    }
    if (s != null && s.isNotEmpty) {
      try {
        _smoking = SmokingStatus.values.firstWhere((v) => v.name == s);
      } catch (_) {}
    }
    if (e != null && e.isNotEmpty) {
      try {
        _exercise = ExerciseFrequency.values.firstWhere((v) => v.name == e);
      } catch (_) {}
    }
    if (r != null && r.isNotEmpty) {
      try {
        _religion = Religion.values.firstWhere((v) => v.name == r);
      } catch (_) {}
    }
    if (mounted) setState(() {});
  }

  Future<void> _saveCurrentIdealLifestyle() async {
    if (_isSavingOnExit) return;
    _isSavingOnExit = true;
    try {
      await OnboardingSaveHelper.saveIdealLifestyle(
        drinking: _drinking?.name,
        smoking: _smoking?.name,
        exercise: _exercise?.name,
        religion: _religion?.name,
      );
    } finally {
      _isSavingOnExit = false;
    }
  }

  Future<void> _handleBack() async {
    await _saveCurrentIdealLifestyle();
    if (!mounted) return;
    if (widget.onBack != null) {
      widget.onBack!();
    } else {
      Navigator.of(context).pop();
    }
  }

  Future<void> _skipToTutorial() async {
    if (_isSkipping) return;
    HapticFeedback.lightImpact();
    setState(() => _isSkipping = true);
    await OnboardingSaveHelper.skipIdealType();
    if (!mounted) return;
    Navigator.of(
      context,
      rootNavigator: true,
    ).pushReplacementNamed(RouteNames.welcomeTutorial);
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) async {
        if (didPop) return;
        await _handleBack();
      },
      child: Scaffold(
        backgroundColor: _AppColors.backgroundLight,
        body: SafeArea(
          child: Stack(
            children: [
              const Positioned.fill(child: _SubtleBackgroundGradient()),
              Column(
                children: [
                  // 헤더
                  _Header(
                    currentStep: widget.currentStep,
                    totalSteps: widget.totalSteps,
                    onBack: _handleBack,
                    onSkipPressed: _isSkipping ? null : _skipToTutorial,
                  ),
                  // 메인 콘텐츠
                  Expanded(
                    child: SingleChildScrollView(
                      physics: const BouncingScrollPhysics(),
                      padding: const EdgeInsets.fromLTRB(24, 8, 24, 100),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // 타이틀 섹션
                          const _TitleSection(),
                          const SizedBox(height: 40),

                          // 음주 섹션
                          _Section(
                            title: '술은 얼마나 자주 드세요?',
                            child: Wrap(
                              spacing: 12,
                              runSpacing: 12,
                              children: [
                                _SelectionChip(
                                  label: '전혀 안 함',
                                  isSelected:
                                      _drinking == DrinkingFrequency.none,
                                  onTap: () =>
                                      _updateDrinking(DrinkingFrequency.none),
                                ),
                                _SelectionChip(
                                  label: '가끔',
                                  isSelected:
                                      _drinking == DrinkingFrequency.sometimes,
                                  onTap: () => _updateDrinking(
                                    DrinkingFrequency.sometimes,
                                  ),
                                ),
                                _SelectionChip(
                                  label: '주 1-2회',
                                  isSelected:
                                      _drinking == DrinkingFrequency.weekly1_2,
                                  onTap: () => _updateDrinking(
                                    DrinkingFrequency.weekly1_2,
                                  ),
                                ),
                                _SelectionChip(
                                  label: '자주 즐김',
                                  isSelected:
                                      _drinking == DrinkingFrequency.often,
                                  onTap: () =>
                                      _updateDrinking(DrinkingFrequency.often),
                                ),
                              ],
                            ),
                          ),

                          // 흡연 섹션
                          _Section(
                            title: '흡연',
                            child: Wrap(
                              spacing: 12,
                              runSpacing: 12,
                              children: [
                                _SelectionChip(
                                  label: '비흡연',
                                  isSelected:
                                      _smoking == SmokingStatus.nonSmoker,
                                  onTap: () =>
                                      _updateSmoking(SmokingStatus.nonSmoker),
                                ),
                                _SelectionChip(
                                  label: '흡연',
                                  isSelected: _smoking == SmokingStatus.smoker,
                                  onTap: () =>
                                      _updateSmoking(SmokingStatus.smoker),
                                ),
                                _SelectionChip(
                                  label: '금연 중',
                                  isSelected:
                                      _smoking == SmokingStatus.quitting,
                                  onTap: () =>
                                      _updateSmoking(SmokingStatus.quitting),
                                ),
                              ],
                            ),
                          ),

                          // 운동 섹션
                          _Section(
                            title: '운동 하시나요?',
                            child: Wrap(
                              spacing: 12,
                              runSpacing: 12,
                              children: [
                                _SelectionChip(
                                  label: '운동 매니아',
                                  isSelected:
                                      _exercise == ExerciseFrequency.mania,
                                  onTap: () =>
                                      _updateExercise(ExerciseFrequency.mania),
                                ),
                                _SelectionChip(
                                  label: '매일 함',
                                  isSelected:
                                      _exercise == ExerciseFrequency.daily,
                                  onTap: () =>
                                      _updateExercise(ExerciseFrequency.daily),
                                ),
                                _SelectionChip(
                                  label: '가끔 함',
                                  isSelected:
                                      _exercise == ExerciseFrequency.sometimes,
                                  onTap: () => _updateExercise(
                                    ExerciseFrequency.sometimes,
                                  ),
                                ),
                                _SelectionChip(
                                  label: '숨쉬기만 함',
                                  isSelected:
                                      _exercise ==
                                      ExerciseFrequency.breathingOnly,
                                  onTap: () => _updateExercise(
                                    ExerciseFrequency.breathingOnly,
                                  ),
                                ),
                              ],
                            ),
                          ),

                          // 종교 섹션
                          _Section(
                            title: '종교',
                            isLast: true,
                            child: Wrap(
                              spacing: 12,
                              runSpacing: 12,
                              children: [
                                _SelectionChip(
                                  label: '무교',
                                  isSelected: _religion == Religion.none,
                                  onTap: () => _updateReligion(Religion.none),
                                ),
                                _SelectionChip(
                                  label: '기독교',
                                  isSelected:
                                      _religion == Religion.christianity,
                                  onTap: () =>
                                      _updateReligion(Religion.christianity),
                                ),
                                _SelectionChip(
                                  label: '천주교',
                                  isSelected: _religion == Religion.catholic,
                                  onTap: () =>
                                      _updateReligion(Religion.catholic),
                                ),
                                _SelectionChip(
                                  label: '불교',
                                  isSelected: _religion == Religion.buddhism,
                                  onTap: () =>
                                      _updateReligion(Religion.buddhism),
                                ),
                                _SelectionChip(
                                  label: '기타',
                                  isSelected: _religion == Religion.other,
                                  onTap: () => _updateReligion(Religion.other),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
              // 하단 버튼
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: _BottomButton(
                  onNext: () async {
                    HapticFeedback.mediumImpact();
                    final navigator = Navigator.of(context);
                    await _saveCurrentIdealLifestyle();
                    if (!mounted) return;
                    if (widget.onNext != null) {
                      widget.onNext!.call(
                        _drinking,
                        _smoking,
                        _exercise,
                        _religion,
                      );
                    } else {
                      navigator.pushNamed(
                        RouteNames.onboardingIdealPersonality,
                      );
                    }
                  },
                  label: _hasAnySelection ? '다음' : '그냥 넘어갈게요',
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _updateDrinking(DrinkingFrequency value) {
    HapticFeedback.selectionClick();
    setState(() => _drinking = _drinking == value ? null : value);
  }

  void _updateSmoking(SmokingStatus value) {
    HapticFeedback.selectionClick();
    setState(() => _smoking = _smoking == value ? null : value);
  }

  void _updateExercise(ExerciseFrequency value) {
    HapticFeedback.selectionClick();
    setState(() => _exercise = _exercise == value ? null : value);
  }

  void _updateReligion(Religion value) {
    HapticFeedback.selectionClick();
    setState(() => _religion = _religion == value ? null : value);
  }
}

class _SubtleBackgroundGradient extends StatelessWidget {
  const _SubtleBackgroundGradient();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            const Color(0xFFEDE8EB).withValues(alpha: 0.16),
            _AppColors.backgroundLight,
            Colors.white.withValues(alpha: 0.96),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final int currentStep;
  final int totalSteps;
  final VoidCallback? onBack;
  final VoidCallback? onSkipPressed;

  const _Header({
    required this.currentStep,
    required this.totalSteps,
    this.onBack,
    this.onSkipPressed,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: Row(
        children: [
          SizedBox(
            width: 132,
            height: 44,
            child: Align(
              alignment: Alignment.centerLeft,
              child: CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: const Size(44, 44),
                onPressed: () {
                  HapticFeedback.lightImpact();
                  onBack?.call();
                },
                child: const Icon(
                  CupertinoIcons.back,
                  color: _AppColors.textMain,
                  size: 24,
                ),
              ),
            ),
          ),
          Expanded(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: List.generate(totalSteps, (index) {
                final isActive = index == currentStep - 1;
                return AnimatedContainer(
                  duration: const Duration(milliseconds: 300),
                  margin: const EdgeInsets.symmetric(horizontal: 4),
                  width: isActive ? 24 : 10,
                  height: 10,
                  decoration: BoxDecoration(
                    color: isActive
                        ? _AppColors.primary
                        : _AppColors.dotInactive,
                    borderRadius: BorderRadius.circular(5),
                  ),
                );
              }),
            ),
          ),
          SizedBox(
            width: 132,
            height: 44,
            child: _SkipLaterButton(onPressed: onSkipPressed),
          ),
        ],
      ),
    );
  }
}

class _SkipLaterButton extends StatefulWidget {
  final VoidCallback? onPressed;

  const _SkipLaterButton({this.onPressed});

  @override
  State<_SkipLaterButton> createState() => _SkipLaterButtonState();
}

class _SkipLaterButtonState extends State<_SkipLaterButton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<Offset> _offset;
  late final Animation<double> _opacity;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 820),
    )..repeat(reverse: true);
    final curved = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeInOut,
    );
    _offset = Tween<Offset>(
      begin: const Offset(-0.025, 0),
      end: const Offset(0.025, 0),
    ).animate(curved);
    _opacity = Tween<double>(begin: 0.68, end: 1).animate(curved);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _opacity,
      child: SlideTransition(
        position: _offset,
        child: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: widget.onPressed,
          child: Container(
            height: 34,
            padding: const EdgeInsets.symmetric(horizontal: 10),
            decoration: BoxDecoration(
              color: _AppColors.primary.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(17),
              border: Border.all(
                color: _AppColors.primary.withValues(alpha: 0.34),
              ),
            ),
            alignment: Alignment.center,
            child: const Text(
              '건너뛰고 다음에 할래요',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 11.5,
                fontWeight: FontWeight.w700,
                color: _AppColors.primary,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 타이틀 섹션
// =============================================================================
class _TitleSection extends StatelessWidget {
  const _TitleSection();

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: const [
        Text(
          '라이프 스타일',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 32,
            fontWeight: FontWeight.bold,
            color: _AppColors.textMain,
            height: 1.2,
            letterSpacing: -0.5,
          ),
        ),
        SizedBox(height: 8),
        Text(
          '당신이 선호하는 이상형의 라이프 스타일을 알려주세요.',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 16,
            color: _AppColors.textSub,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 섹션 컨테이너
// =============================================================================
class _Section extends StatelessWidget {
  final String title;
  final Widget child;
  final bool isLast;

  const _Section({
    required this.title,
    required this.child,
    this.isLast = false,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: isLast ? 0 : 40),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: _AppColors.textMain,
            ),
          ),
          const SizedBox(height: 16),
          child,
        ],
      ),
    );
  }
}

// =============================================================================
// 선택 칩
// =============================================================================
class _SelectionChip extends StatelessWidget {
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  const _SelectionChip({
    required this.label,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        decoration: BoxDecoration(
          color: isSelected
              ? _AppColors.primary.withValues(alpha: 0.1)
              : _AppColors.chipDefault,
          borderRadius: BorderRadius.circular(22),
          border: Border.all(
            color: isSelected ? _AppColors.primary : Colors.transparent,
            width: 1,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 14,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                color: isSelected ? _AppColors.primary : _AppColors.textMain,
              ),
            ),
            if (isSelected) ...[
              const SizedBox(width: 8),
              const Icon(
                Icons.check_rounded,
                size: 18,
                color: _AppColors.primary,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 하단 버튼
// =============================================================================
class _BottomButton extends StatelessWidget {
  final VoidCallback? onNext;
  final String label;

  const _BottomButton({this.onNext, required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(
        24,
        16,
        24,
        MediaQuery.of(context).padding.bottom + 24,
      ),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight.withValues(alpha: 0.9),
        border: const Border(top: BorderSide(color: Color(0xFFF3F4F6))),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onNext,
        child: Container(
          height: 56,
          decoration: BoxDecoration(
            color: _AppColors.primary,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: _AppColors.primary.withValues(alpha: 0.24),
                blurRadius: 16,
                offset: const Offset(0, 6),
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                label,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 17,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
              const SizedBox(width: 6),
              const Icon(
                Icons.arrow_forward_rounded,
                color: Colors.white,
                size: 18,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
