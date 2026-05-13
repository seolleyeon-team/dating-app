import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../constants/yonsei_departments.dart';
import '../../../router/route_names.dart';
import '../../../services/onboarding_save_helper.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';

class _AppColors {
  static const Color primary = Color(0xFFEF3976);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray500 = Color(0xFF6B7280);
  static const Color gray800 = Color(0xFF1F2937);
  static const Color progressBg = Color(0xFFE6DBDF);
  static const Color noticeBg = Color(0xFFFFF1F6);
}

/// 계열 선택 이후 세부 학과를 고르는 온보딩 화면.
class DepartmentScreen extends StatefulWidget {
  final int currentStep;
  final int totalSteps;
  final String? initialMajor;
  final VoidCallback? onBack;
  final Function(String department)? onNext;

  const DepartmentScreen({
    super.key,
    this.currentStep = 5,
    this.totalSteps = 9,
    this.initialMajor,
    this.onBack,
    this.onNext,
  });

  @override
  State<DepartmentScreen> createState() => _DepartmentScreenState();
}

class _DepartmentScreenState extends State<DepartmentScreen> {
  final StorageService _storageService = StorageService();
  final UserService _userService = UserService();

  String? _selectedMajor;
  String? _selectedDepartment;
  bool _isLoading = true;
  bool _isSavingOnExit = false;

  List<String> get _departments {
    return YonseiDepartments.departmentsFor(_selectedMajor);
  }

  bool get _canProceed {
    return _selectedMajor != null &&
        _selectedDepartment != null &&
        _selectedDepartment!.trim().isNotEmpty;
  }

  @override
  void initState() {
    super.initState();
    if (YonseiDepartments.hasMajor(widget.initialMajor)) {
      _selectedMajor = widget.initialMajor;
      _isLoading = false;
    }
    _loadExistingSelection();
  }

  Future<void> _loadExistingSelection() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) {
      if (mounted) setState(() => _isLoading = false);
      return;
    }

    final data = await _userService.getUserProfile(kakaoUserId);
    if (!mounted) return;

    final onboarding = data?['onboarding'];
    if (onboarding is! Map) {
      setState(() => _isLoading = false);
      return;
    }

    final major = onboarding['major']?.toString();
    final resolvedMajor = YonseiDepartments.hasMajor(major)
        ? major
        : _selectedMajor;
    final department = onboarding['department']?.toString();
    final departments = YonseiDepartments.departmentsFor(resolvedMajor);

    setState(() {
      _selectedMajor = resolvedMajor;
      _selectedDepartment = departments.contains(department)
          ? department
          : null;
      _isLoading = false;
    });
  }

  Future<void> _saveCurrentDepartment() async {
    if (_isSavingOnExit || _selectedDepartment == null) return;
    _isSavingOnExit = true;
    try {
      await OnboardingSaveHelper.saveDepartment(_selectedDepartment!.trim());
    } finally {
      _isSavingOnExit = false;
    }
  }

  Future<void> _handleBack() async {
    await _saveCurrentDepartment();
    if (!mounted) return;

    if (widget.onBack != null) {
      widget.onBack!();
    } else {
      Navigator.of(context).pop();
    }
  }

  void _showRequiredMessage() {
    HapticFeedback.heavyImpact();
    showCupertinoDialog<void>(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: const Text('학과를 선택해주세요'),
        content: const Text('추천 풀과 과 피하기 기능을 위해 세부 학과가 필요해요.'),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
  }

  Future<void> _handleNext() async {
    if (_selectedMajor == null) {
      Navigator.of(context).pushReplacementNamed(RouteNames.onboardingMajor);
      return;
    }
    if (!_canProceed) {
      _showRequiredMessage();
      return;
    }

    HapticFeedback.mediumImpact();
    await _saveCurrentDepartment();
    if (!mounted) return;

    if (widget.onNext != null) {
      widget.onNext!.call(_selectedDepartment!.trim());
    } else {
      Navigator.of(context).pushNamed(RouteNames.onboardingPhoto);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

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
            _BackgroundGradients(),
            SafeArea(
              bottom: false,
              child: Column(
                children: [
                  _Header(
                    currentStep: widget.currentStep,
                    totalSteps: widget.totalSteps,
                    onBack: _handleBack,
                  ),
                  Expanded(
                    child: _isLoading
                        ? const Center(child: CupertinoActivityIndicator())
                        : _selectedMajor == null
                        ? _MissingMajorState(
                            onTap: () {
                              Navigator.of(context).pushReplacementNamed(
                                RouteNames.onboardingMajor,
                              );
                            },
                          )
                        : SingleChildScrollView(
                            physics: const BouncingScrollPhysics(),
                            padding: const EdgeInsets.fromLTRB(16, 24, 16, 140),
                            child: Column(
                              children: [
                                _TitleSection(selectedMajor: _selectedMajor!),
                                const SizedBox(height: 14),
                                const _PrivacyNotice(),
                                const SizedBox(height: 20),
                                _DepartmentList(
                                  departments: _departments,
                                  selectedDepartment: _selectedDepartment,
                                  onSelect: (department) {
                                    HapticFeedback.selectionClick();
                                    setState(() {
                                      _selectedDepartment = department;
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
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: _BottomButton(
                bottomPadding: bottomPadding,
                isEnabled: !_isLoading,
                label: _selectedMajor == null ? '계열 선택하기' : '다음',
                onPressed: _handleNext,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BackgroundGradients extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topRight,
              end: Alignment.bottomLeft,
              colors: [
                const Color(0xFFE9D5FF).withValues(alpha: 0.35),
                const Color(0xFFFCE7F3).withValues(alpha: 0.2),
                const Color(0xFFFFF7ED).withValues(alpha: 0.35),
              ],
            ),
          ),
        ),
        Positioned(
          top: -120,
          right: -160,
          child: Container(
            width: 480,
            height: 480,
            decoration: BoxDecoration(
              color: _AppColors.primary.withValues(alpha: 0.05),
              shape: BoxShape.circle,
            ),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 90, sigmaY: 90),
              child: const SizedBox(),
            ),
          ),
        ),
      ],
    );
  }
}

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
              onBack?.call();
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
          const SizedBox(width: 40),
        ],
      ),
    );
  }
}

class _TitleSection extends StatelessWidget {
  final String selectedMajor;

  const _TitleSection({required this.selectedMajor});

  @override
  Widget build(BuildContext context) {
    return Column(children: [_SelectedMajorHeroCard(major: selectedMajor)]);
  }
}

class _SelectedMajorHeroCard extends StatelessWidget {
  final String major;

  const _SelectedMajorHeroCard({required this.major});

  Color get _iconBgColor {
    switch (major) {
      case 'liberalArts':
        return const Color(0xFFFFF7ED);
      case 'science':
        return const Color(0xFFEFF6FF);
      case 'medical':
        return const Color(0xFFF0FDF4);
      case 'artsSports':
        return const Color(0xFFFAF5FF);
      default:
        return const Color(0xFFF3F4F6);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Hero(
      tag: YonseiDepartments.heroTagFor(major),
      flightShuttleBuilder:
          (
            flightContext,
            animation,
            flightDirection,
            fromHeroContext,
            toHeroContext,
          ) {
            return _SelectedMajorFlightCard(
              major: major,
              iconBgColor: _iconBgColor,
            );
          },
      child: Material(
        type: MaterialType.transparency,
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(18, 18, 12, 18),
          decoration: BoxDecoration(
            color: _AppColors.surfaceLight,
            borderRadius: BorderRadius.circular(30),
            border: Border.all(color: _AppColors.primary, width: 2),
            backgroundBlendMode: BlendMode.srcOver,
            boxShadow: [
              BoxShadow(
                color: _AppColors.primary.withValues(alpha: 0.22),
                blurRadius: 32,
                offset: const Offset(0, 16),
              ),
              BoxShadow(
                color: CupertinoColors.black.withValues(alpha: 0.05),
                blurRadius: 12,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          clipBehavior: Clip.hardEdge,
          child: Row(
            children: [
              Container(
                width: 58,
                height: 58,
                decoration: BoxDecoration(
                  color: _iconBgColor,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Center(
                  child: Text(
                    YonseiDepartments.emojiFor(major),
                    style: const TextStyle(fontSize: 30),
                  ),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      YonseiDepartments.labelFor(major),
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
                      YonseiDepartments.subtitleFor(major),
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
    );
  }
}

class _SelectedMajorFlightCard extends StatelessWidget {
  final String major;
  final Color iconBgColor;

  const _SelectedMajorFlightCard({
    required this.major,
    required this.iconBgColor,
  });

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
                        color: iconBgColor,
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Center(
                        child: Text(
                          YonseiDepartments.emojiFor(major),
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
                            YonseiDepartments.labelFor(major),
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
                            YonseiDepartments.subtitleFor(major),
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

class _PrivacyNotice extends StatelessWidget {
  const _PrivacyNotice();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _AppColors.noticeBg,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: _AppColors.primary.withValues(alpha: 0.12)),
      ),
      child: const Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            CupertinoIcons.lock_shield_fill,
            color: _AppColors.primary,
            size: 20,
          ),
          SizedBox(width: 10),
          Expanded(
            child: Text(
              '선택한 과는 다른 사람에게 드러나지 않습니다. '
              '캠퍼스 생활권 추천과 과 피하기 기능을 더 정확하게 만드는 데만 활용돼요.',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 13,
                height: 1.45,
                fontWeight: FontWeight.w600,
                color: _AppColors.textMain,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _DepartmentList extends StatelessWidget {
  final List<String> departments;
  final String? selectedDepartment;
  final ValueChanged<String> onSelect;

  const _DepartmentList({
    required this.departments,
    required this.selectedDepartment,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: departments.map((department) {
        final isSelected = department == selectedDepartment;
        return _DepartmentTile(
          department: department,
          isSelected: isSelected,
          onTap: () => onSelect(department),
        );
      }).toList(),
    );
  }
}

class _DepartmentTile extends StatelessWidget {
  final String department;
  final bool isSelected;
  final VoidCallback onTap;

  const _DepartmentTile({
    required this.department,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: const Size(0, 0),
        onPressed: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
          decoration: BoxDecoration(
            color: _AppColors.surfaceLight,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: isSelected
                  ? _AppColors.primary
                  : CupertinoColors.white.withValues(alpha: 0.6),
              width: isSelected ? 2 : 1,
            ),
            boxShadow: [
              BoxShadow(
                color: isSelected
                    ? _AppColors.primary.withValues(alpha: 0.18)
                    : CupertinoColors.black.withValues(alpha: 0.06),
                blurRadius: isSelected ? 22 : 16,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  department,
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 16,
                    fontWeight: isSelected ? FontWeight.w700 : FontWeight.w600,
                    color: _AppColors.gray800,
                  ),
                ),
              ),
              AnimatedContainer(
                duration: const Duration(milliseconds: 180),
                width: 24,
                height: 24,
                decoration: BoxDecoration(
                  color: isSelected ? _AppColors.primary : Colors.transparent,
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: isSelected ? _AppColors.primary : _AppColors.gray400,
                    width: 2,
                  ),
                ),
                child: isSelected
                    ? const Icon(
                        CupertinoIcons.check_mark,
                        color: CupertinoColors.white,
                        size: 15,
                      )
                    : null,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MissingMajorState extends StatelessWidget {
  final VoidCallback onTap;

  const _MissingMajorState({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              '먼저 계열을 선택해주세요',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 22,
                fontWeight: FontWeight.w700,
                color: _AppColors.gray800,
              ),
            ),
            const SizedBox(height: 10),
            const Text(
              '계열을 기준으로 세부 학과 목록을 보여드릴게요.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 14,
                height: 1.5,
                color: _AppColors.gray500,
              ),
            ),
            const SizedBox(height: 22),
            CupertinoButton(
              padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 12),
              color: _AppColors.primary,
              borderRadius: BorderRadius.circular(16),
              onPressed: onTap,
              child: const Text(
                '계열 선택하기',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontWeight: FontWeight.w700,
                  color: CupertinoColors.white,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BottomButton extends StatelessWidget {
  final double bottomPadding;
  final bool isEnabled;
  final String label;
  final VoidCallback onPressed;

  const _BottomButton({
    required this.bottomPadding,
    required this.isEnabled,
    required this.label,
    required this.onPressed,
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
      child: SizedBox(
        width: double.infinity,
        child: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: isEnabled ? onPressed : null,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            height: 56,
            decoration: BoxDecoration(
              color: isEnabled ? _AppColors.primary : _AppColors.gray400,
              borderRadius: BorderRadius.circular(16),
              boxShadow: isEnabled
                  ? [
                      const BoxShadow(
                        color: Color(0xFFD62660),
                        offset: Offset(0, 6),
                      ),
                      BoxShadow(
                        color: CupertinoColors.black.withValues(alpha: 0.1),
                        blurRadius: 10,
                        offset: const Offset(0, 10),
                      ),
                    ]
                  : null,
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  label,
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 17,
                    fontWeight: FontWeight.w700,
                    color: CupertinoColors.white,
                  ),
                ),
                const SizedBox(width: 4),
                const Icon(
                  CupertinoIcons.arrow_right,
                  size: 20,
                  color: CupertinoColors.white,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
