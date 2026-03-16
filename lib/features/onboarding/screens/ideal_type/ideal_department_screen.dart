// =============================================================================
// 이상형 학과/계열 선택 화면 (V3 디자인)
// 경로: lib/features/onboarding/screens/ideal_type/ideal_department_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const IdealDepartmentScreen()),
// );
// =============================================================================

import 'dart:ui';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import '../../../../services/storage_service.dart';

// =============================================================================
// 색상 상수 (V3 테마)
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFEF3976);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray500 = Color(0xFF6B7280);
  static const Color gray800 = Color(0xFF1F2937);
  static const Color orange50 = Color(0xFFFFF7ED);
  static const Color blue50 = Color(0xFFEFF6FF);
  static const Color green50 = Color(0xFFF0FDF4);
  static const Color purple50 = Color(0xFFFAF5FF);
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
class IdealDepartmentScreen extends StatefulWidget {
  final int currentStep;
  final int totalSteps;
  final VoidCallback? onBack;
  final VoidCallback? onSkip;
  final Function(List<MajorType> majors)? onNext;

  const IdealDepartmentScreen({
    super.key,
    this.currentStep = 3,
    this.totalSteps = 6,
    this.onBack,
    this.onSkip,
    this.onNext,
  });

  @override
  State<IdealDepartmentScreen> createState() => _IdealDepartmentScreenState();
}

class _IdealDepartmentScreenState extends State<IdealDepartmentScreen> {
  final Set<MajorType> _selectedMajors = {};

  @override
  void initState() {
    super.initState();
    _loadSavedSelection();
  }

  MajorType? _majorFromName(String name) {
    for (final t in MajorType.values) {
      if (t.name == name) return t;
    }
    return null;
  }

  Future<void> _loadSavedSelection() async {
    final storage = StorageService();
    final kakaoUserId = await storage.getKakaoUserId();
    if (kakaoUserId == null) return;
    final draft = await storage.getOnboardingDraft(kakaoUserId);
    final idealDept = draft['idealDepartment'];
    if (!mounted) return;
    if (idealDept is List) {
      setState(() {
        _selectedMajors.clear();
        for (final e in idealDept) {
          final type = _majorFromName(e.toString());
          if (type != null) _selectedMajors.add(type);
        }
      });
    } else if (idealDept != null && idealDept.toString().isNotEmpty) {
      final type = _majorFromName(idealDept.toString());
      if (type != null) {
        setState(() => _selectedMajors.add(type));
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
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
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
                  onBack: widget.onBack ?? () => Navigator.of(context).pop(),
                ),
                // 콘텐츠
                Expanded(
                  child: SingleChildScrollView(
                    physics: const BouncingScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(24, 24, 24, 140),
                    child: Column(
                      children: [
                        // 타이틀
                        const _TitleSection(),
                        const SizedBox(height: 32),
                        // 옵션 그리드
                        _OptionsGrid(
                          options: _options,
                          selectedMajors: _selectedMajors,
                          onToggle: (major) {
                            HapticFeedback.selectionClick();
                            setState(() {
                              if (_selectedMajors.contains(major)) {
                                _selectedMajors.remove(major);
                              } else {
                                _selectedMajors.add(major);
                              }
                            });
                          },
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
          // 하단 버튼
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: _BottomButtons(
              bottomPadding: bottomPadding,
              onSkip: widget.onSkip ?? () => Navigator.of(context).pop(),
              onNext: () async {
                HapticFeedback.mediumImpact();
                final list = _selectedMajors.toList();
                if (widget.onNext != null) {
                  widget.onNext!.call(list);
                } else {
                  final storage = StorageService();
                  final kakaoUserId = await storage.getKakaoUserId();
                  if (kakaoUserId != null) {
                    await storage.mergeOnboardingDraft(kakaoUserId, {
                      'idealDepartment': list.map((m) => m.name).toList(),
                    });
                  }

                  if (!mounted) return;
                  Navigator.of(context).pop();
                }
              },
            ),
          ),
        ],
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
    return ClipRRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: Container(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
          decoration: BoxDecoration(
            color: _AppColors.backgroundLight.withValues(alpha: 0.8),
          ),
          child: Column(
            children: [
              // 네비게이션
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () {
                      HapticFeedback.lightImpact();
                      onBack?.call();
                    },
                    child: const Icon(
                      CupertinoIcons.back,
                      size: 24,
                      color: _AppColors.gray500,
                    ),
                  ),
                  const Text(
                    '설레연',
                    style: TextStyle(
                      fontFamily: 'Noto Sans KR',
                      fontSize: 20,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.primary,
                    ),
                  ),
                  const SizedBox(width: 40),
                ],
              ),
              const SizedBox(height: 16),
              // 프로그레스 바
              Row(
                children: List.generate(totalSteps, (index) {
                  final isCompleted = index < currentStep;
                  final isCurrent = index == currentStep - 1;
                  return Expanded(
                    child: Container(
                      height: 6,
                      margin: EdgeInsets.only(
                        right: index < totalSteps - 1 ? 6 : 0,
                      ),
                      decoration: BoxDecoration(
                        color: isCompleted || isCurrent
                            ? (isCurrent
                                  ? _AppColors.primary
                                  : _AppColors.primary.withValues(alpha: 0.3))
                            : _AppColors.gray200,
                        borderRadius: BorderRadius.circular(3),
                      ),
                    ),
                  );
                }),
              ),
            ],
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
      children: [
        const Text(
          '내가 선호하는 이상형의\n학과/계열은?',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: 'Noto Sans KR',
            fontSize: 24,
            fontWeight: FontWeight.w700,
            height: 1.3,
            letterSpacing: -0.5,
            color: _AppColors.gray800,
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          '여러 개 선택할 수 있어요 · 비슷한 전공의 친구를 찾을 때 도움이 돼요',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: 'Noto Sans KR',
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
  final Set<MajorType> selectedMajors;
  final Function(MajorType) onToggle;

  const _OptionsGrid({
    required this.options,
    required this.selectedMajors,
    required this.onToggle,
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
        final isSelected = selectedMajors.contains(option.type);
        return _OptionCard(
          option: option,
          isSelected: isSelected,
          onTap: () => onToggle(option.type),
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
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(0, 0),
      onPressed: onTap,
      child: Padding(
        padding: const EdgeInsets.all(6),
        child: SizedBox.expand(
          child: AnimatedContainer(
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
                  style: const TextStyle(
                    fontFamily: 'Noto Sans KR',
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.gray800,
                  ),
                ),
                const SizedBox(height: 4),
                // 서브타이틀
                Text(
                  option.subtitle,
                  style: const TextStyle(
                    fontFamily: 'Noto Sans KR',
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: _AppColors.gray400,
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
// 하단 버튼
// =============================================================================
class _BottomButtons extends StatelessWidget {
  final double bottomPadding;
  final VoidCallback? onSkip;
  final VoidCallback onNext;

  const _BottomButtons({
    required this.bottomPadding,
    this.onSkip,
    required this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(24, 24, 24, bottomPadding + 24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            _AppColors.backgroundLight.withValues(alpha: 0),
            _AppColors.backgroundLight.withValues(alpha: 0.95),
            _AppColors.backgroundLight,
          ],
        ),
      ),
      child: Row(
        children: [
          // 상관없어요 버튼
          Expanded(
            child: CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: () {
                HapticFeedback.lightImpact();
                onSkip?.call();
              },
              child: Container(
                height: 56,
                decoration: BoxDecoration(
                  color: CupertinoColors.white,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: _AppColors.gray100),
                  boxShadow: [
                    const BoxShadow(
                      color: Color(0xFFE5E7EB),
                      offset: Offset(0, 6),
                    ),
                    BoxShadow(
                      color: CupertinoColors.black.withValues(alpha: 0.05),
                      blurRadius: 10,
                      offset: const Offset(0, 10),
                    ),
                  ],
                ),
                child: const Center(
                  child: Text(
                    '상관없어요',
                    style: TextStyle(
                      fontFamily: 'Noto Sans KR',
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.gray500,
                    ),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(width: 16),
          // 다음 버튼
          Expanded(
            child: CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: onNext,
              child: Container(
                height: 56,
                decoration: BoxDecoration(
                  color: _AppColors.primary,
                  borderRadius: BorderRadius.circular(16),
                  boxShadow: [
                    const BoxShadow(
                      color: Color(0xFFD62660),
                      offset: Offset(0, 6),
                    ),
                    BoxShadow(
                      color: CupertinoColors.black.withValues(alpha: 0.1),
                      blurRadius: 10,
                      offset: const Offset(0, 10),
                    ),
                  ],
                ),
                child: const Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      '다음',
                      style: TextStyle(
                        fontFamily: 'Noto Sans KR',
                        fontSize: 17,
                        fontWeight: FontWeight.w700,
                        color: CupertinoColors.white,
                      ),
                    ),
                    SizedBox(width: 4),
                    Icon(
                      CupertinoIcons.arrow_right,
                      size: 20,
                      color: CupertinoColors.white,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
