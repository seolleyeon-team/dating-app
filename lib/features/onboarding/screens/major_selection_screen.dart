// =============================================================================
// 전공/계열 선택 화면 (온보딩)
// 경로: lib/features/onboarding/screens/major_selection_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const MajorSelectionScreen()),
// );
// =============================================================================

import 'dart:ui';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../../constants/yonsei_departments.dart';
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
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray500 = Color(0xFF6B7280);
  static const Color gray800 = Color(0xFF1F2937);
  static const Color orange50 = Color(0xFFFFF7ED);
  static const Color blue50 = Color(0xFFEFF6FF);
  static const Color green50 = Color(0xFFF0FDF4);
  static const Color purple50 = Color(0xFFFAF5FF);
  static const Color progressBg = Color(0xFFE6DBDF);
}

// =============================================================================
// 전공 타입
// =============================================================================
enum MajorType { liberalArts, science, medical, artsSports }

class _MajorOption {
  final MajorType type;
  final String emoji;
  final String title;
  final String subtitle;
  final Color bgColor;

  const _MajorOption({
    required this.type,
    required this.emoji,
    required this.title,
    required this.subtitle,
    required this.bgColor,
  });
}

// =============================================================================
// 메인 화면
// =============================================================================
class MajorSelectionScreen extends StatefulWidget {
  final int currentStep;
  final int totalSteps;
  final VoidCallback? onBack;
  final VoidCallback? onSkip;
  final Function(MajorType? major)? onNext;

  const MajorSelectionScreen({
    super.key,
    this.currentStep = 4,
    this.totalSteps = 9,
    this.onBack,
    this.onSkip,
    this.onNext,
  });

  @override
  State<MajorSelectionScreen> createState() => _MajorSelectionScreenState();
}

class _MajorSelectionScreenState extends State<MajorSelectionScreen> {
  MajorType? _selectedMajor;
  final StorageService _storageService = StorageService();
  final UserService _userService = UserService();
  bool _isSavingOnExit = false;
  bool _isNavigating = false;

  @override
  void initState() {
    super.initState();
    _loadExistingMajor();
  }

  Future<void> _loadExistingMajor() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) return;
    final data = await _userService.getUserProfile(kakaoUserId);
    if (!mounted || data == null) return;
    final onboarding = data['onboarding'];
    if (onboarding is! Map) return;
    final majorStr = onboarding['major']?.toString();
    if (majorStr != null && majorStr.isNotEmpty) {
      try {
        _selectedMajor = MajorType.values.firstWhere((v) => v.name == majorStr);
      } catch (_) {}
      if (mounted) setState(() {});
    }
  }

  Future<void> _saveCurrentMajor() async {
    if (_isSavingOnExit) return;
    _isSavingOnExit = true;
    try {
      await OnboardingSaveHelper.saveMajor(_selectedMajor?.name);
    } finally {
      _isSavingOnExit = false;
    }
  }

  Future<void> _handleBack() async {
    await _saveCurrentMajor();
    if (!mounted) return;
    if (widget.onBack != null) {
      widget.onBack!();
    } else {
      Navigator.of(context).pop();
    }
  }

  Future<void> _handleMajorSelected(MajorType major) async {
    if (_isNavigating) return;

    HapticFeedback.selectionClick();
    setState(() {
      _selectedMajor = major;
      _isNavigating = true;
    });

    try {
      await _saveCurrentMajor();
      if (!mounted) return;

      if (widget.onNext != null) {
        widget.onNext!.call(_selectedMajor);
      } else {
        Navigator.of(context).pushNamed(
          RouteNames.onboardingDepartment,
          arguments: {'major': major.name},
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isNavigating = false);
      }
    }
  }

  static const List<_MajorOption> _options = [
    _MajorOption(
      type: MajorType.liberalArts,
      emoji: '📚',
      title: '문과 계열',
      subtitle: '인문 / 사회 / 상경',
      bgColor: _AppColors.orange50,
    ),
    _MajorOption(
      type: MajorType.science,
      emoji: '🧪',
      title: '이과 계열',
      subtitle: '자연 / 공학',
      bgColor: _AppColors.blue50,
    ),
    _MajorOption(
      type: MajorType.medical,
      emoji: '🏥',
      title: '메디컬 계열',
      subtitle: '의치한약수 / 간호',
      bgColor: _AppColors.green50,
    ),
    _MajorOption(
      type: MajorType.artsSports,
      emoji: '🎨',
      title: '예체능 계열',
      subtitle: '미술 / 음악 / 체육',
      bgColor: _AppColors.purple50,
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) async {
        if (didPop) return;
        await _handleBack();
      },
      child: CupertinoPageScaffold(
        backgroundColor: _AppColors.backgroundLight,
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
                    currentStep: widget.currentStep,
                    totalSteps: widget.totalSteps,
                    onBack: _handleBack,
                  ),
                  // 콘텐츠
                  Expanded(
                    child: SingleChildScrollView(
                      physics: const BouncingScrollPhysics(),
                      padding: const EdgeInsets.fromLTRB(16, 24, 16, 32),
                      child: Column(
                        children: [
                          // 타이틀
                          const _TitleSection(),
                          const SizedBox(height: 32),
                          // 옵션 그리드
                          _OptionsGrid(
                            options: _options,
                            selectedMajor: _selectedMajor,
                            onSelect: _handleMajorSelected,
                          ),
                        ],
                      ),
                    ),
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
// 배경 그라데이션
// =============================================================================
class _BackgroundGradients extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        // 전체 그라데이션
        Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topRight,
              end: Alignment.bottomLeft,
              colors: [
                const Color(0xFFE9D5FF).withValues(alpha: 0.4),
                const Color(0xFFFCE7F3).withValues(alpha: 0.2),
                const Color(0xFFFFF7ED).withValues(alpha: 0.4),
              ],
            ),
          ),
        ),
        Positioned(
          top: -100,
          right: -150,
          child: Container(
            width: 500,
            height: 500,
            decoration: BoxDecoration(
              color: _AppColors.primary.withValues(alpha: 0.05),
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
          left: -150,
          child: Container(
            width: 400,
            height: 400,
            decoration: BoxDecoration(
              color: const Color(0xFFC084FC).withValues(alpha: 0.05),
              shape: BoxShape.circle,
            ),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 80, sigmaY: 80),
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
      children: [
        const Text(
          '어느 학과/계열\n소속이신가요?',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 24,
            fontWeight: FontWeight.w700,
            height: 1.3,
            letterSpacing: -0.5,
            color: _AppColors.gray800,
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          '비슷한 전공의 친구를 찾을 때 도움이 돼요',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 14,
            color: _AppColors.gray500,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 옵션 그리드
// =============================================================================
class _OptionsGrid extends StatelessWidget {
  final List<_MajorOption> options;
  final MajorType? selectedMajor;
  final Function(MajorType) onSelect;

  const _OptionsGrid({
    required this.options,
    required this.selectedMajor,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisSpacing: 0,
        crossAxisSpacing: 0,
        childAspectRatio: 1.0,
      ),
      itemCount: options.length,
      itemBuilder: (context, index) {
        final option = options[index];
        final isSelected = selectedMajor == option.type;
        return _OptionCard(
          option: option,
          isSelected: isSelected,
          onTap: () => onSelect(option.type),
        );
      },
    );
  }
}

class _OptionCard extends StatelessWidget {
  final _MajorOption option;
  final bool isSelected;
  final VoidCallback onTap;

  const _OptionCard({
    required this.option,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final card = AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeOut,
      transform: Matrix4.translationValues(0, isSelected ? -6 : 0, 0),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(32),
        border: Border.all(
          color: isSelected
              ? _AppColors.primary
              : CupertinoColors.white.withValues(alpha: 0.6),
          width: isSelected ? 2 : 1,
        ),
        boxShadow: [
          BoxShadow(
            color: isSelected
                ? _AppColors.primary.withValues(alpha: 0.3)
                : CupertinoColors.black.withValues(alpha: 0.08),
            blurRadius: isSelected ? 40 : 30,
            offset: Offset(0, isSelected ? 15 : 12),
          ),
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.05),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          FittedBox(
            fit: BoxFit.scaleDown,
            child: SizedBox(
              width: 148,
              height: 150,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  // 이모지 아이콘
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 300),
                    width: 64,
                    height: 64,
                    transform: Matrix4.diagonal3Values(
                      isSelected ? 1.1 : 1.0,
                      isSelected ? 1.1 : 1.0,
                      1.0,
                    ),
                    decoration: BoxDecoration(
                      color: option.bgColor,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Center(
                      child: Text(
                        option.emoji,
                        style: const TextStyle(fontSize: 32),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  // 타이틀
                  Text(
                    option.title,
                    maxLines: 1,
                    overflow: TextOverflow.fade,
                    softWrap: false,
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.gray800,
                    ),
                  ),
                  const SizedBox(height: 4),
                  // 서브타이틀
                  Text(
                    option.subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.fade,
                    softWrap: false,
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      color: _AppColors.gray400,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );

    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(0, 0),
      onPressed: onTap,
      child: Padding(
        padding: const EdgeInsets.all(6),
        child: SizedBox.expand(
          child: Hero(
            tag: YonseiDepartments.heroTagFor(option.type.name),
            flightShuttleBuilder:
                (
                  flightContext,
                  animation,
                  flightDirection,
                  fromHeroContext,
                  toHeroContext,
                ) {
                  return _MajorHeroFlightCard(option: option);
                },
            child: Material(type: MaterialType.transparency, child: card),
          ),
        ),
      ),
    );
  }
}

class _MajorHeroFlightCard extends StatelessWidget {
  final _MajorOption option;

  const _MajorHeroFlightCard({required this.option});

  @override
  Widget build(BuildContext context) {
    return Material(
      type: MaterialType.transparency,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(30),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: _AppColors.surfaceLight,
            borderRadius: BorderRadius.circular(30),
            border: Border.all(color: _AppColors.primary, width: 2),
          ),
          child: FittedBox(
            fit: BoxFit.scaleDown,
            child: SizedBox(
              width: 320,
              height: 92,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 18),
                child: Row(
                  children: [
                    Container(
                      width: 58,
                      height: 58,
                      decoration: BoxDecoration(
                        color: option.bgColor,
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Center(
                        child: Text(
                          option.emoji,
                          style: const TextStyle(fontSize: 30),
                        ),
                      ),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            option.title,
                            maxLines: 1,
                            overflow: TextOverflow.fade,
                            softWrap: false,
                            style: const TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 18,
                              fontWeight: FontWeight.w700,
                              color: _AppColors.gray800,
                            ),
                          ),
                          const SizedBox(height: 5),
                          Text(
                            option.subtitle,
                            maxLines: 1,
                            overflow: TextOverflow.fade,
                            softWrap: false,
                            style: const TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                              color: _AppColors.gray400,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
