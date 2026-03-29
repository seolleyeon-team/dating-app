// =============================================================================
// 나를 표현하는 키워드 선택 화면 (온보딩 4/6단계)
// 경로: lib/features/onboarding/screens/keyword_screen.dart
//
// 사용 예시 (main.dart):
// import 'package:seolleyeon/features/onboarding/screens/keyword_screen.dart';
// ...
// home: const KeywordScreen(),
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import '../../../router/route_names.dart';
import '../../../services/onboarding_save_helper.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF04579);
  static const Color backgroundLight = Color(0xFFFFFFFF);
  static const Color surfaceLight = Color(0xFFF3F4F6);
  static const Color textMain = Color(0xFF111827);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color dotInactive = Color(0xFFE5E7EB);
}

// =============================================================================
// 키워드 데이터
// =============================================================================
class _KeywordData {
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
class KeywordScreen extends StatefulWidget {
  const KeywordScreen({super.key});

  @override
  State<KeywordScreen> createState() => _KeywordScreenState();
}

class _KeywordScreenState extends State<KeywordScreen> {
  final Set<String> _selectedKeywords = {};
  static const int _maxSelection = 8;
  final StorageService _storageService = StorageService();
  final UserService _userService = UserService();
  bool _isSavingOnExit = false;

  bool get _canProceed => _selectedKeywords.isNotEmpty;

  @override
  void initState() {
    super.initState();
    _loadExistingKeywords();
  }

  Future<void> _loadExistingKeywords() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) return;
    final data = await _userService.getUserProfile(kakaoUserId);
    if (!mounted || data == null) return;
    final onboarding = data['onboarding'];
    if (onboarding is! Map) return;
    final keywordsRaw = onboarding['keywords'];
    if (keywordsRaw is List && keywordsRaw.isNotEmpty) {
      _selectedKeywords.addAll(keywordsRaw.map((e) => e.toString()));
      if (mounted) setState(() {});
    }
  }

  Future<void> _saveCurrentKeywords() async {
    if (_isSavingOnExit) return;
    _isSavingOnExit = true;
    try {
      await OnboardingSaveHelper.saveKeywords(_selectedKeywords.toList());
    } finally {
      _isSavingOnExit = false;
    }
  }

  Future<void> _handleBack() async {
    await _saveCurrentKeywords();
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
    if (_canProceed) {
      HapticFeedback.mediumImpact();
      await _saveCurrentKeywords();
      if (!mounted) return;
      Navigator.of(context).pushNamed(RouteNames.onboardingIdealType);
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
      child: CupertinoPageScaffold(
        backgroundColor: _AppColors.backgroundLight,
        child: Stack(
          children: [
            SafeArea(
              bottom: false,
              child: Column(
                children: [
                  // 헤더
                  _Header(
                    onBackPressed: _handleBack,
                  currentStep: 8,
                  totalSteps: 8,
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
                      children: _KeywordData.keywords.map((keyword) {
                        final isSelected = _selectedKeywords.contains(keyword);
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
              isEnabled: _canProceed,
              selectedCount: _selectedKeywords.length,
              onPressed: _onSavePressed,
            ),
          ),
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
  final int currentStep;
  final int totalSteps;

  const _Header({
    required this.onBackPressed,
    required this.currentStep,
    required this.totalSteps,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: Row(
        children: [
          // 뒤로가기 버튼
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(44, 44),
            onPressed: onBackPressed,
            child: const Icon(
              CupertinoIcons.back,
              color: _AppColors.textMain,
              size: 24,
            ),
          ),
          // 도트 인디케이터
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
          // 우측 여백
          const SizedBox(width: 44),
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
    return const Padding(
      padding: EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '나를 표현하는 키워드',
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
            '나를 가장 잘 나타내는 키워드를 8개까지 선택해 주세요.',
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
  final VoidCallback onPressed;

  const _BottomCTA({
    required this.isEnabled,
    required this.selectedCount,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return Container(
      padding: EdgeInsets.fromLTRB(24, 16, 24, bottomPadding + 16),
      decoration: BoxDecoration(
        color: _AppColors.backgroundLight,
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
            borderRadius: BorderRadius.circular(24),
            boxShadow: isEnabled
                ? [
                    BoxShadow(
                      color: const Color(0xFFFCE7F3),
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
                selectedCount > 0 ? '저장 ($selectedCount/8)' : '저장',
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
