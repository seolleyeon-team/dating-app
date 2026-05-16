// =============================================================================
// 이상형 성격 선택 화면 (이상형 설정 4/6단계)
// 경로: lib/features/onboarding/screens/ideal_type/ideal_personality_screen.dart
//
// 사용 예시 (main.dart):
// import 'package:seolleyeon/features/onboarding/screens/ideal_type/ideal_personality_screen.dart';
// ...
// home: const IdealPersonalityScreen(),
// =============================================================================

import 'package:flutter/cupertino.dart';
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
  static const Color surfaceLight = Color(0xFFF5F5F5);
  static const Color textMain = Color(0xFF111827);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color dotInactive = Color(0xFFEDE8EB);
}

// =============================================================================
// 성격 키워드 데이터
// =============================================================================
class _PersonalityData {
  static const List<String> keywords = [
    '자신감 있는',
    '아담한',
    '듬직한',
    '잘 웃는',
    '자유분방한',
    '욕 안하는',
    '목소리 좋은',
    '또라이 같은',
    '먼저 말걸어주는',
    '옷 잘입는',
    '활발한',
    '조용한',
    '애교가 많은',
    '어른스러운',
    '열정적인',
    '차분한',
    '예의 바른',
    '재치있는',
    '진지한',
  ];
}

// =============================================================================
// 메인 화면
// =============================================================================
class IdealPersonalityScreen extends StatefulWidget {
  const IdealPersonalityScreen({super.key});

  @override
  State<IdealPersonalityScreen> createState() => _IdealPersonalityScreenState();
}

class _IdealPersonalityScreenState extends State<IdealPersonalityScreen> {
  final Set<String> _selectedKeywords = {};
  static const int _maxSelection = 8;
  final StorageService _storageService = StorageService();
  final UserService _userService = UserService();
  bool _isSavingOnExit = false;
  bool _isSkipping = false;

  bool get _hasAnySelection => _selectedKeywords.isNotEmpty;

  @override
  void initState() {
    super.initState();
    _loadExistingIdealPersonality();
  }

  Future<void> _loadExistingIdealPersonality() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) return;
    final data = await _userService.getUserProfile(kakaoUserId);
    if (!mounted || data == null) return;
    final idealType = data['idealType'];
    if (idealType is! Map) return;
    final raw = idealType['preferredPersonalities'];
    if (raw is List && raw.isNotEmpty) {
      _selectedKeywords.addAll(raw.map((e) => e.toString()));
      if (mounted) setState(() {});
    }
  }

  Future<void> _saveCurrentIdealPersonality() async {
    if (_isSavingOnExit) return;
    _isSavingOnExit = true;
    try {
      await OnboardingSaveHelper.saveIdealPersonality(
        _selectedKeywords.toList(),
      );
    } finally {
      _isSavingOnExit = false;
    }
  }

  Future<void> _handleBack() async {
    await _saveCurrentIdealPersonality();
    if (!mounted) return;
    Navigator.of(context).pop();
  }

  void _toggleKeyword(String keyword) {
    setState(() {
      if (_selectedKeywords.contains(keyword)) {
        _selectedKeywords.remove(keyword);
      } else if (_selectedKeywords.length < _maxSelection) {
        _selectedKeywords.add(keyword);
      }
    });
    HapticFeedback.selectionClick();
  }

  Future<void> _onSavePressed() async {
    HapticFeedback.mediumImpact();
    await OnboardingSaveHelper.saveIdealPersonalityAndComplete(
      _selectedKeywords.toList(),
    );
    if (!mounted) return;
    Navigator.of(
      context,
      rootNavigator: true,
    ).pushReplacementNamed(RouteNames.welcomeTutorial);
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
      child: CupertinoPageScaffold(
        backgroundColor: _AppColors.backgroundLight,
        child: Stack(
          children: [
            const Positioned.fill(child: _SubtleBackgroundGradient()),
            SafeArea(
              bottom: false,
              child: Column(
                children: [
                  // 헤더
                  _Header(
                    onBackPressed: () => _handleBack(),
                    onSkipPressed: _isSkipping ? null : _skipToTutorial,
                    currentStep: 3,
                    totalSteps: 3,
                  ),
                  // 타이틀 섹션
                  const _TitleSection(),
                  // 키워드 그리드
                  Expanded(
                    child: SingleChildScrollView(
                      physics: const BouncingScrollPhysics(),
                      padding: const EdgeInsets.fromLTRB(24, 24, 24, 120),
                      child: Wrap(
                        spacing: 10,
                        runSpacing: 10,
                        children: _PersonalityData.keywords.map((keyword) {
                          final isSelected = _selectedKeywords.contains(
                            keyword,
                          );
                          return _KeywordChip(
                            label: keyword,
                            isSelected: isSelected,
                            onTap: () => _toggleKeyword(keyword),
                          );
                        }).toList(),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            // 하단 CTA 버튼
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: _BottomCTA(
                isEnabled: true,
                selectedCount: _selectedKeywords.length,
                emptyLabel: _hasAnySelection ? null : '그냥 넘어갈게요',
                onPressed: _onSavePressed,
              ),
            ),
          ],
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
            CupertinoColors.white.withValues(alpha: 0.96),
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
  final VoidCallback onBackPressed;
  final VoidCallback? onSkipPressed;
  final int currentStep;
  final int totalSteps;

  const _Header({
    required this.onBackPressed,
    this.onSkipPressed,
    required this.currentStep,
    required this.totalSteps,
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
                onPressed: onBackPressed,
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
    return const Padding(
      padding: EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '나의 이상형의\n성격은?',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 30,
              fontWeight: FontWeight.w700,
              height: 1.2,
              letterSpacing: -0.5,
              color: _AppColors.textMain,
            ),
          ),
          SizedBox(height: 8),
          Text(
            '이상형의 성격을 가장 잘 나타내는 키워드를\n8개까지 선택해 주세요.',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 16,
              fontWeight: FontWeight.w400,
              height: 1.4,
              color: _AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 키워드 칩
// =============================================================================
class _KeywordChip extends StatelessWidget {
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  const _KeywordChip({
    required this.label,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        decoration: BoxDecoration(
          color: isSelected
              ? _AppColors.backgroundLight
              : _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? _AppColors.primary : const Color(0x00000000),
            width: 1.5,
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
                fontWeight: FontWeight.w500,
                color: isSelected
                    ? _AppColors.primary
                    : _AppColors.textSecondary,
              ),
            ),
            if (isSelected) ...[
              const SizedBox(width: 6),
              const Icon(
                CupertinoIcons.checkmark,
                size: 14,
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
// 하단 CTA 버튼
// =============================================================================
class _BottomCTA extends StatelessWidget {
  final bool isEnabled;
  final int selectedCount;
  final String? emptyLabel;
  final VoidCallback onPressed;

  const _BottomCTA({
    required this.isEnabled,
    required this.selectedCount,
    this.emptyLabel,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return Container(
      padding: EdgeInsets.fromLTRB(24, 16, 24, bottomPadding + 24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            _AppColors.backgroundLight.withValues(alpha: 0),
            _AppColors.backgroundLight,
          ],
          stops: const [0.0, 0.3],
        ),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: isEnabled ? onPressed : null,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          width: double.infinity,
          height: 56,
          decoration: BoxDecoration(
            color: isEnabled
                ? _AppColors.primary
                : _AppColors.primary.withValues(alpha: 0.4),
            borderRadius: BorderRadius.circular(16),
            boxShadow: isEnabled
                ? [
                    BoxShadow(
                      color: _AppColors.primary.withValues(alpha: 0.24),
                      blurRadius: 16,
                      offset: const Offset(0, 6),
                    ),
                  ]
                : [],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                emptyLabel ??
                    (selectedCount > 0 ? '저장 ($selectedCount/8)' : '저장'),
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                  color: isEnabled
                      ? CupertinoColors.white
                      : CupertinoColors.white.withValues(alpha: 0.7),
                ),
              ),
              const SizedBox(width: 6),
              Icon(
                CupertinoIcons.arrow_right,
                size: 18,
                color: isEnabled
                    ? CupertinoColors.white
                    : CupertinoColors.white.withValues(alpha: 0.7),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
