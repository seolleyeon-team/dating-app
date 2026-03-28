// =============================================================================
// 라이프 스타일 선택 화면 (Step 3 of 6)
// 경로: lib/features/onboarding/screens/ideal_type/ideal_lifestyle_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const LifestyleScreen()),
// );
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../../router/route_names.dart';
import '../../../services/onboarding_save_helper.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFEF3976);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color textSub = Color(0xFF6B7280);
  static const Color chipDefault = Color(0xFFF4F0F2);
  static const Color progressBg = Color(0xFFE6DBDF);
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
/// 온보딩 단계: 라이프스타일 선택 (음주/흡연 등)
class LifestyleScreen extends StatefulWidget {
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

  const LifestyleScreen({
    super.key,
    this.currentStep = 3,
    this.totalSteps = 8,
    this.onBack,
    this.onNext,
  });

  @override
  State<LifestyleScreen> createState() => _LifestyleScreenState();
}

class _LifestyleScreenState extends State<LifestyleScreen> {
  // 초기값 설정 (HTML 예시대로)
  DrinkingFrequency? _drinking = DrinkingFrequency.sometimes;
  SmokingStatus? _smoking = SmokingStatus.nonSmoker;
  ExerciseFrequency? _exercise = ExerciseFrequency.breathingOnly;
  Religion? _religion;
  final StorageService _storageService = StorageService();
  final UserService _userService = UserService();
  bool _isSavingOnExit = false;

  @override
  void initState() {
    super.initState();
    _loadExistingLifestyle();
  }

  Future<void> _loadExistingLifestyle() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) return;
    final data = await _userService.getUserProfile(kakaoUserId);
    if (!mounted || data == null) return;
    final onboarding = data['onboarding'];
    if (onboarding is! Map) return;
    final lifestyle = onboarding['lifestyle'];
    if (lifestyle is! Map) return;
    final d = lifestyle['drinking']?.toString();
    final s = lifestyle['smoking']?.toString();
    final e = lifestyle['exercise']?.toString();
    final r = lifestyle['religion']?.toString();
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

  Future<void> _saveCurrentLifestyle() async {
    if (_isSavingOnExit) return;
    _isSavingOnExit = true;
    try {
      await OnboardingSaveHelper.saveLifestyle(
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
    await _saveCurrentLifestyle();
    if (!mounted) return;
    if (widget.onBack != null) {
      widget.onBack!();
    } else {
      Navigator.of(context).pop();
    }
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
            Column(
              children: [
                // 헤더
                _Header(
                  currentStep: widget.currentStep,
                  totalSteps: widget.totalSteps,
                  onBack: _handleBack,
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
                                isSelected: _drinking == DrinkingFrequency.none,
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
                                isSelected: _smoking == SmokingStatus.nonSmoker,
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
                                isSelected: _smoking == SmokingStatus.quitting,
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
                              _SelectionChip(
                                label: '운동 매니아',
                                isSelected:
                                    _exercise == ExerciseFrequency.mania,
                                onTap: () =>
                                    _updateExercise(ExerciseFrequency.mania),
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
                                isSelected: _religion == Religion.christianity,
                                onTap: () =>
                                    _updateReligion(Religion.christianity),
                              ),
                              _SelectionChip(
                                label: '천주교',
                                isSelected: _religion == Religion.catholic,
                                onTap: () => _updateReligion(Religion.catholic),
                              ),
                              _SelectionChip(
                                label: '불교',
                                isSelected: _religion == Religion.buddhism,
                                onTap: () => _updateReligion(Religion.buddhism),
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
                  await _saveCurrentLifestyle();
                  if (!mounted) return;
                  if (widget.onNext != null) {
                    widget.onNext!.call(
                      _drinking,
                      _smoking,
                      _exercise,
                      _religion,
                    );
                  } else {
                    Navigator.of(context).pushNamed(RouteNames.onboardingMajor);
                  }
                },
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
    setState(() => _drinking = value);
  }

  void _updateSmoking(SmokingStatus value) {
    HapticFeedback.selectionClick();
    setState(() => _smoking = value);
  }

  void _updateExercise(ExerciseFrequency value) {
    HapticFeedback.selectionClick();
    setState(() => _exercise = value);
  }

  void _updateReligion(Religion value) {
    HapticFeedback.selectionClick();
    setState(() => _religion = value);
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final int currentStep;
  final int totalSteps;
  final VoidCallback? onBack;

  const _Header({
    required this.currentStep,
    required this.totalSteps,
    this.onBack,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      color: _AppColors.backgroundLight.withValues(alpha: 0.8),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          IconButton(
            onPressed: () {
              HapticFeedback.lightImpact();
              if (onBack != null) {
                onBack!.call();
              } else {
                Navigator.of(context).pop();
              }
            },
            icon: const Icon(
              Icons.arrow_back_rounded,
              color: _AppColors.textMain,
              size: 24,
            ),
            style: IconButton.styleFrom(
              padding: const EdgeInsets.all(8),
              backgroundColor: Colors.transparent,
            ),
          ),
          // 커스텀 프로그레스 인디케이터
          Row(
            children: List.generate(totalSteps, (index) {
              final isCurrent = index == currentStep - 1;
              return AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                width: isCurrent ? 24 : 8,
                height: 8,
                margin: const EdgeInsets.symmetric(horizontal: 4),
                decoration: BoxDecoration(
                  color: isCurrent ? _AppColors.primary : _AppColors.progressBg,
                  borderRadius: BorderRadius.circular(4),
                ),
              );
            }),
          ),
          const SizedBox(width: 40), // 뒤로가기 버튼과의 균형을 위한 빈 공간
        ],
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
          'STEP 3 OF 6',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 14,
            fontWeight: FontWeight.w600,
            color: _AppColors.primary,
            letterSpacing: 1.2,
          ),
        ),
        SizedBox(height: 8),
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
          '나를 가장 잘 나타내는 라이프스타일은 뭔가요?',
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

  const _BottomButton({this.onNext});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(
        24,
        24,
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
                color: _AppColors.primary.withValues(alpha: 0.3),
                blurRadius: 12,
                offset: const Offset(0, 6),
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: const [
              Text(
                '다음',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
              SizedBox(width: 8),
              Icon(Icons.arrow_forward_rounded, color: Colors.white, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}
