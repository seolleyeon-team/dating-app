// =============================================================================
// 관심사 선택 화면
// 경로: lib/features/onboarding/screens/interests_selection_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const InterestsSelectionScreen()),
// );
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../onboarding_route_args.dart';
import '../../../router/route_names.dart';
import '../../../services/onboarding_save_helper.dart';
import '../../../services/storage_service.dart';
import '../../../constants/interest_taxonomy.dart';
import '../../../services/user_service.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF5468C);
  static const Color backgroundLight = Color(0xFFFAFAFA);
  static const Color surfaceLight = Color(0xFFF8F9FA);
  static const Color textMain = Color(0xFF1A1A1A);
  static const Color textSub = Color(0xFF6B7280);
  static const Color chipBg = Color(0xFFF3F4F6);
  static const Color chipSelected = Color(0xFFF5468C);
  static const Color border = Color(0xFFE5E7EB);
  static const Color progressBg = Color(0xFFEDE8EB);
}

// =============================================================================
// 데이터 모델 (관심사 taxonomy는 lib/constants/interest_taxonomy.dart 공유)
// =============================================================================
const List<InterestCategory> _categories = interestCategories;

// =============================================================================
// 메인 화면
// =============================================================================
class InterestsSelectionScreen extends StatefulWidget {
  final VoidCallback? onClose;
  final VoidCallback? onComplete;
  final VoidCallback? onBack;
  final InterestsSelectionMode mode;
  final Future<List<String>> Function()? loadInterests;
  final Future<void> Function(List<String> interests)? saveInterests;
  final int maxSelection;
  final int currentStep;
  final int totalSteps;

  const InterestsSelectionScreen({
    super.key,
    this.onClose,
    this.onComplete,
    this.onBack,
    this.mode = InterestsSelectionMode.onboarding,
    this.loadInterests,
    this.saveInterests,
    this.maxSelection = 10,
    this.currentStep = 2,
    this.totalSteps = 9,
  });

  @override
  State<InterestsSelectionScreen> createState() =>
      _InterestsSelectionScreenState();
}

class _InterestsSelectionScreenState extends State<InterestsSelectionScreen> {
  final Set<String> _selectedInterests = {};
  final StorageService _storageService = StorageService();
  late final UserService _userService = UserService();
  bool _isLoadingExistingInterests = true;
  bool _isSavingOnExit = false;
  bool _isHandlingBack = false;
  String? _repairError;

  bool get _isPrerequisiteRepair =>
      widget.mode == InterestsSelectionMode.prerequisiteRepair;

  @override
  void initState() {
    super.initState();
    _loadExistingInterests();
  }

  Future<void> _loadExistingInterests() async {
    try {
      final interests = widget.loadInterests != null
          ? await widget.loadInterests!()
          : await _loadInterestsFromFirestore();
      if (!mounted) return;
      setState(() {
        _selectedInterests
          ..clear()
          ..addAll(interests.take(widget.maxSelection));
        _isLoadingExistingInterests = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _isLoadingExistingInterests = false;
        if (_isPrerequisiteRepair) {
          _repairError = '관심사를 불러오지 못했어요. 다시 시도해주세요.';
        }
      });
    }
  }

  Future<List<String>> _loadInterestsFromFirestore() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) {
      return const <String>[];
    }
    final data = await _userService.getUserProfile(kakaoUserId);
    if (data == null) return const <String>[];
    final onboarding = data['onboarding'];
    if (onboarding is! Map) return const <String>[];
    final interestsRaw = onboarding['interests'];
    if (interestsRaw is! Iterable) return const <String>[];
    return interestsRaw
        .map((e) => e.toString().trim())
        .where((interest) => interest.isNotEmpty)
        .toList(growable: false);
  }

  Future<void> _saveCurrentInterests() async {
    if (_isSavingOnExit) return;
    _isSavingOnExit = true;
    try {
      await _saveInterests(_selectedInterests.toList());
    } finally {
      _isSavingOnExit = false;
    }
  }

  Future<bool> _saveInterests(List<String> interests) async {
    final saveInterests = widget.saveInterests;
    if (saveInterests != null) {
      await saveInterests(List<String>.unmodifiable(interests));
      return true;
    }
    return OnboardingSaveHelper.saveInterests(interests);
  }

  Future<void> _handleBack() async {
    if (_isHandlingBack || _isSavingOnExit) return;
    _isHandlingBack = true;
    try {
      if (_isPrerequisiteRepair) {
        if (!mounted) return;
        if (widget.onBack != null) {
          widget.onBack!();
        } else {
          Navigator.of(context).pop();
        }
        return;
      }

      await _saveCurrentInterests();
      if (!mounted) return;
      if (widget.onBack != null) {
        widget.onBack!();
      } else {
        Navigator.of(context).pop();
      }
    } finally {
      _isHandlingBack = false;
    }
  }

  Future<void> _completePrerequisiteRepair() async {
    if (_isSavingOnExit || _isLoadingExistingInterests) return;
    if (_selectedInterests.isEmpty) {
      setState(() {
        _repairError = '관심사를 1개 이상 선택해주세요.';
      });
      return;
    }

    setState(() {
      _isSavingOnExit = true;
      _repairError = null;
    });

    var didPopWithSuccess = false;
    try {
      final saved = await _saveInterests(_selectedInterests.toList());
      if (!mounted) return;
      if (!saved) {
        setState(() {
          _isSavingOnExit = false;
          _repairError = '관심사를 저장하지 못했어요. 다시 시도해주세요.';
        });
        return;
      }

      didPopWithSuccess = true;
      Navigator.of(context).pop(true);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _isSavingOnExit = false;
        _repairError = '관심사를 저장하지 못했어요. 다시 시도해주세요.';
      });
    } finally {
      if (!didPopWithSuccess && mounted && _isSavingOnExit) {
        setState(() {
          _isSavingOnExit = false;
        });
      }
    }
  }

  void _toggleInterest(String interest) {
    if (_isSavingOnExit ||
        (_isPrerequisiteRepair && _isLoadingExistingInterests)) {
      return;
    }
    HapticFeedback.lightImpact();
    setState(() {
      if (_selectedInterests.contains(interest)) {
        _selectedInterests.remove(interest);
      } else {
        if (_selectedInterests.length < widget.maxSelection) {
          _selectedInterests.add(interest);
        } else {
          // 최대 선택 개수 초과 시 피드백
          HapticFeedback.mediumImpact();
        }
      }
    });
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
                    showProgress: !_isPrerequisiteRepair,
                    onBack: _handleBack,
                  ),
                  // 메인 콘텐츠
                  Expanded(
                    child: SingleChildScrollView(
                      physics: const BouncingScrollPhysics(),
                      padding: const EdgeInsets.fromLTRB(20, 0, 20, 100),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const SizedBox(height: 16),
                          // 타이틀 및 카운터
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              const Text(
                                '관심사',
                                style: TextStyle(
                                  fontFamily: 'NanumSquareRound',
                                  fontSize: 28,
                                  fontWeight: FontWeight.bold,
                                  color: _AppColors.textMain,
                                  letterSpacing: -0.5,
                                ),
                              ),
                              Padding(
                                padding: const EdgeInsets.only(bottom: 4),
                                child: Text(
                                  '${_selectedInterests.length}/${widget.maxSelection}',
                                  style: const TextStyle(
                                    fontFamily: 'NanumSquareRound',
                                    fontSize: 14,
                                    fontWeight: FontWeight.w500,
                                    color: _AppColors.textSub,
                                  ),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 24),
                          if (_isPrerequisiteRepair && _repairError != null)
                            Padding(
                              padding: const EdgeInsets.only(bottom: 16),
                              child: Text(
                                _repairError!,
                                style: const TextStyle(
                                  fontFamily: 'NanumSquareRound',
                                  color: _AppColors.primary,
                                  fontSize: 14,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          // 선택된 관심사 칩 영역
                          if (_selectedInterests.isNotEmpty)
                            Padding(
                              padding: const EdgeInsets.only(bottom: 24),
                              child: Wrap(
                                spacing: 8,
                                runSpacing: 8,
                                children: _selectedInterests.map((interest) {
                                  return _SelectedChip(
                                    label: interest,
                                    onDeleted: () => _toggleInterest(interest),
                                  );
                                }).toList(),
                              ),
                            ),
                          // 검색창
                          const _SearchBar(),
                          const SizedBox(height: 32),
                          // 카테고리별 섹션
                          ..._categories.map(
                            (category) => _CategorySection(
                              category: category,
                              selectedInterests: _selectedInterests,
                              onToggle: _toggleInterest,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
              // 하단 플로팅 버튼 (다음 클릭 → lifestyle_screen)
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: _BottomFloatingArea(
                  label: _isPrerequisiteRepair ? '관심사 등록 완료' : '다음',
                  enabled: _isPrerequisiteRepair
                      ? _selectedInterests.isNotEmpty &&
                            !_isLoadingExistingInterests &&
                            !_isSavingOnExit
                      : true,
                  loading: _isPrerequisiteRepair && _isSavingOnExit,
                  onNext: _isPrerequisiteRepair
                      ? _completePrerequisiteRepair
                      : widget.onComplete ??
                            () async {
                              final navigator = Navigator.of(context);
                              await _saveCurrentInterests();
                              if (!mounted) return;
                              navigator.pushNamed(
                                RouteNames.onboardingLifestyle,
                              );
                            },
                ),
              ),
            ],
          ),
        ),
      ),
    );
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
            const Color(0xFFEDE8EB).withValues(alpha: 0.14),
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
  final bool showProgress;
  final VoidCallback? onBack;

  const _Header({
    required this.currentStep,
    required this.totalSteps,
    this.showProgress = true,
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
          if (showProgress)
            Row(
              key: const ValueKey('interests-selection-progress'),
              children: List.generate(totalSteps, (index) {
                final isCurrent = index == currentStep - 1;
                return AnimatedContainer(
                  duration: const Duration(milliseconds: 300),
                  width: isCurrent ? 24 : 8,
                  height: 8,
                  margin: const EdgeInsets.symmetric(horizontal: 4),
                  decoration: BoxDecoration(
                    color: isCurrent
                        ? _AppColors.primary
                        : _AppColors.progressBg,
                    borderRadius: BorderRadius.circular(4),
                  ),
                );
              }),
            )
          else
            const SizedBox(width: 40),
          const SizedBox(width: 40),
        ],
      ),
    );
  }
}

// =============================================================================
// 선택된 관심사 칩
// =============================================================================
class _SelectedChip extends StatelessWidget {
  final String label;
  final VoidCallback onDeleted;

  const _SelectedChip({required this.label, required this.onDeleted});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: _AppColors.chipSelected,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.1),
            blurRadius: 4,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: Colors.white,
            ),
          ),
          const SizedBox(width: 4),
          GestureDetector(
            onTap: onDeleted,
            child: const Icon(
              Icons.close_rounded,
              color: Colors.white70,
              size: 16,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 검색창
// =============================================================================
class _SearchBar extends StatelessWidget {
  const _SearchBar();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: TextField(
        style: const TextStyle(fontFamily: 'NanumSquareRound'),
        decoration: InputDecoration(
          filled: true,
          fillColor: _AppColors.surfaceLight,
          hintText: '검색',
          hintStyle: const TextStyle(
            fontFamily: 'NanumSquareRound',
            color: _AppColors.textSub,
          ),
          prefixIcon: const Icon(
            Icons.search_rounded,
            color: _AppColors.textSub,
          ),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(16),
            borderSide: BorderSide.none,
          ),
          contentPadding: const EdgeInsets.symmetric(vertical: 16),
        ),
      ),
    );
  }
}

// =============================================================================
// 카테고리 섹션
// =============================================================================
class _CategorySection extends StatefulWidget {
  final InterestCategory category;
  final Set<String> selectedInterests;
  final Function(String) onToggle;

  const _CategorySection({
    required this.category,
    required this.selectedInterests,
    required this.onToggle,
  });

  @override
  State<_CategorySection> createState() => _CategorySectionState();
}

class _CategorySectionState extends State<_CategorySection> {
  bool _isExpanded = false;

  // 2줄에 해당하는 높이 (칩 높이 약 40 + runSpacing 10) * 2
  static const double _collapsedHeight = 90.0;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 섹션 헤더
          Row(
            children: [
              Text(widget.category.emoji, style: const TextStyle(fontSize: 24)),
              const SizedBox(width: 8),
              Text(
                widget.category.title,
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: _AppColors.textMain,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          // 칩 목록 (확장 상태에 따라 높이 제한)
          AnimatedCrossFade(
            duration: const Duration(milliseconds: 300),
            crossFadeState: _isExpanded
                ? CrossFadeState.showSecond
                : CrossFadeState.showFirst,
            firstChild: SizedBox(
              height: _collapsedHeight,
              child: ClipRect(
                child: Wrap(
                  spacing: 8,
                  runSpacing: 10,
                  children: widget.category.items.map((item) {
                    final isSelected = widget.selectedInterests.contains(item);
                    return _InterestOptionChip(
                      label: item,
                      isSelected: isSelected,
                      onTap: () => widget.onToggle(item),
                    );
                  }).toList(),
                ),
              ),
            ),
            secondChild: Wrap(
              spacing: 8,
              runSpacing: 10,
              children: widget.category.items.map((item) {
                final isSelected = widget.selectedInterests.contains(item);
                return _InterestOptionChip(
                  label: item,
                  isSelected: isSelected,
                  onTap: () => widget.onToggle(item),
                );
              }).toList(),
            ),
          ),
          // 더 보기 / 접기 버튼
          const SizedBox(height: 24),
          GestureDetector(
            onTap: () {
              HapticFeedback.lightImpact();
              setState(() {
                _isExpanded = !_isExpanded;
              });
            },
            child: Row(
              children: [
                Expanded(child: Container(height: 1, color: _AppColors.border)),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: Row(
                    children: [
                      Text(
                        _isExpanded ? '접기' : '더 보기',
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w500,
                          color: _AppColors.textMain,
                        ),
                      ),
                      AnimatedRotation(
                        turns: _isExpanded ? 0.5 : 0,
                        duration: const Duration(milliseconds: 300),
                        child: const Icon(
                          Icons.expand_more_rounded,
                          size: 16,
                          color: _AppColors.textMain,
                        ),
                      ),
                    ],
                  ),
                ),
                Expanded(child: Container(height: 1, color: _AppColors.border)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _InterestOptionChip extends StatelessWidget {
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  const _InterestOptionChip({
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
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: isSelected ? Colors.white : _AppColors.chipBg,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? _AppColors.primary : Colors.transparent,
            width: isSelected ? 2 : 1,
          ),
          boxShadow: isSelected
              ? [
                  BoxShadow(
                    color: _AppColors.primary.withValues(alpha: 0.2),
                    blurRadius: 8,
                    offset: const Offset(0, 4),
                  ),
                ]
              : [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.02),
                    blurRadius: 2,
                    offset: const Offset(0, 1),
                  ),
                ],
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 14,
            fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
            color: isSelected ? _AppColors.primary : _AppColors.textSub,
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 하단 플로팅 영역
// =============================================================================
class _BottomFloatingArea extends StatelessWidget {
  final VoidCallback? onNext;
  final String label;
  final bool enabled;
  final bool loading;

  const _BottomFloatingArea({
    this.onNext,
    this.label = '다음',
    this.enabled = true,
    this.loading = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
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
      padding: EdgeInsets.fromLTRB(
        24,
        16,
        24,
        MediaQuery.of(context).padding.bottom + 24,
      ),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: enabled && !loading
            ? () {
                HapticFeedback.mediumImpact();
                onNext?.call();
              }
            : null,
        child: Container(
          height: 56,
          width: double.infinity,
          decoration: BoxDecoration(
            color: enabled ? _AppColors.primary : _AppColors.border,
            borderRadius: BorderRadius.circular(16),
            boxShadow: enabled
                ? [
                    BoxShadow(
                      color: _AppColors.primary.withValues(alpha: 0.24),
                      blurRadius: 16,
                      offset: const Offset(0, 6),
                    ),
                  ]
                : const [],
          ),
          child: loading
              ? const Center(
                  child: SizedBox(
                    width: 22,
                    height: 22,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  ),
                )
              : Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      label,
                      style: TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.bold,
                        color: enabled ? Colors.white : _AppColors.textSub,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Icon(
                      Icons.arrow_forward_rounded,
                      color: enabled ? Colors.white : _AppColors.textSub,
                      size: 18,
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}
