// =============================================================================
// 이상형 MBTI 선택 화면
// 경로: lib/features/onboarding/screens/ideal_type/ideal_mbti_screen.dart
//
// 사용 예시 (main.dart):
// import 'package:seolleyeon/features/onboarding/screens/ideal_type/ideal_mbti_screen.dart';
// ...
// home: const IdealMbtiScreen(),
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import '../../../../services/storage_service.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF6477E);
  static const Color primaryVibrant = Color(0xFFFF0055);
  static const Color backgroundLight = Color(0xFFF7F5F8);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF1F2937);
  static const Color textSub = Color(0xFF6B7280);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color gray400 = Color(0xFF94A3B8);
  static const Color pinkBorder = Color(0x4DFFB6C1); // rgba(255, 182, 193, 0.3)
}

// =============================================================================
// 메인 화면
// =============================================================================
class IdealMbtiScreen extends StatefulWidget {
  const IdealMbtiScreen({super.key});

  @override
  State<IdealMbtiScreen> createState() => _IdealMbtiScreenState();
}

class _IdealMbtiScreenState extends State<IdealMbtiScreen> {
  // 각 차원별 선택 (null = 선택 안함)
  final Map<String, String?> _selection = {
    'EI': 'E',
    'NS': 'N',
    'TF': 'F',
    'JP': 'J',
  };

  void _toggleSelection(String dimension, String value) {
    setState(() {
      // 같은 값 다시 누르면 해제
      if (_selection[dimension] == value) {
        _selection[dimension] = null;
      } else {
        _selection[dimension] = value;
      }
    });
    HapticFeedback.selectionClick();
  }

  void _toggleCheckbox(String dimension) {
    setState(() {
      if (_selection[dimension] != null) {
        // 체크 해제 → null
        _selection[dimension] = null;
      } else {
        // 체크 다시 → 기본값 선택
        final defaults = {'EI': 'E', 'NS': 'N', 'TF': 'F', 'JP': 'J'};
        _selection[dimension] = defaults[dimension];
      }
    });
    HapticFeedback.selectionClick();
  }

  void _onDontCare() {
    HapticFeedback.lightImpact();
    Navigator.of(context).pop();
  }

  void _onNext() {
    HapticFeedback.mediumImpact();
    () async {
      final storage = StorageService();
      final kakaoUserId = await storage.getKakaoUserId();
      if (kakaoUserId != null) {
        await storage.mergeOnboardingDraft(kakaoUserId, {
          'idealMbti': _selection,
        });
      }

      if (!mounted) return;
      Navigator.of(context).pop({'mbti': _selection});
    }();
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: SafeArea(
        child: Column(
          children: [
            // 헤더
            _Header(onBackPressed: () => Navigator.of(context).pop()),
            // 프로그레스 바
            const _ProgressBar(currentStep: 1, totalSteps: 5),
            // 컨텐츠 영역
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Column(
                  children: [
                    const SizedBox(height: 16),
                    // 타이틀
                    const _TitleSection(),
                    const SizedBox(height: 32),
                    // MBTI 그리드
                    Expanded(
                      child: Center(
                        child: _MbtiGrid(
                          selection: _selection,
                          onToggle: _toggleSelection,
                          onCheckboxToggle: _toggleCheckbox,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            // 하단 버튼
            _BottomButtons(onDontCare: _onDontCare, onNext: _onNext),
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

  const _Header({required this.onBackPressed});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: Row(
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(44, 44),
            onPressed: onBackPressed,
            child: const Icon(
              CupertinoIcons.chevron_back,
              color: _AppColors.textMain,
              size: 28,
            ),
          ),
          const Expanded(
            child: Text(
              '설레연',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 20,
                fontWeight: FontWeight.w700,
                color: _AppColors.primary,
              ),
            ),
          ),
          const SizedBox(width: 44),
        ],
      ),
    );
  }
}

// =============================================================================
// 프로그레스 바
// =============================================================================
class _ProgressBar extends StatelessWidget {
  final int currentStep;
  final int totalSteps;

  const _ProgressBar({required this.currentStep, required this.totalSteps});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
      child: Row(
        children: List.generate(totalSteps, (index) {
          final isActive = index < currentStep;
          return Expanded(
            child: Container(
              height: 4,
              margin: EdgeInsets.only(right: index < totalSteps - 1 ? 8 : 0),
              decoration: BoxDecoration(
                color: isActive ? _AppColors.primary : _AppColors.gray200,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          );
        }),
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
    return const Column(
      children: [
        Text(
          '선호하는 상대의\nMBTI를 알려주세요',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 24,
            fontWeight: FontWeight.w700,
            height: 1.3,
            color: _AppColors.textMain,
          ),
        ),
        SizedBox(height: 12),
        Text(
          '나와 잘 맞는 성향을 선택해보세요',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 14,
            fontWeight: FontWeight.w400,
            color: _AppColors.textSub,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// MBTI 그리드
// =============================================================================
class _MbtiGrid extends StatelessWidget {
  final Map<String, String?> selection;
  final void Function(String dimension, String value) onToggle;
  final void Function(String dimension) onCheckboxToggle;

  const _MbtiGrid({
    required this.selection,
    required this.onToggle,
    required this.onCheckboxToggle,
  });

  @override
  Widget build(BuildContext context) {
    final dimensions = [
      ('EI', 'E', 'I'),
      ('NS', 'N', 'S'),
      ('TF', 'F', 'T'),
      ('JP', 'J', 'P'),
    ];

    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: dimensions.map((dim) {
        final dimension = dim.$1;
        final first = dim.$2;
        final second = dim.$3;
        final selectedValue = selection[dimension];
        final isChecked = selectedValue != null;

        return Expanded(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // 체크 인디케이터 (클릭 가능)
                GestureDetector(
                  onTap: () => onCheckboxToggle(dimension),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    width: 18,
                    height: 18,
                    decoration: BoxDecoration(
                      color: isChecked
                          ? _AppColors.primaryVibrant
                          : CupertinoColors.white,
                      borderRadius: BorderRadius.circular(4),
                      border: Border.all(
                        color: isChecked
                            ? _AppColors.primaryVibrant
                            : _AppColors.gray400,
                        width: 1.5,
                      ),
                    ),
                    child: isChecked
                        ? const Icon(
                            CupertinoIcons.checkmark,
                            size: 12,
                            color: CupertinoColors.white,
                          )
                        : null,
                  ),
                ),
                const SizedBox(height: 12),
                // 컬럼 컨테이너
                AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 20,
                  ),
                  decoration: BoxDecoration(
                    color: isChecked
                        ? CupertinoColors.white.withValues(alpha: 0.4)
                        : CupertinoColors.white.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(28),
                    border: Border.all(
                      color: isChecked
                          ? _AppColors.pinkBorder
                          : _AppColors.gray200,
                    ),
                  ),
                  child: Column(
                    children: [
                      // 첫번째 버튼
                      _MbtiButton(
                        letter: first,
                        isSelected: selectedValue == first,
                        onTap: () => onToggle(dimension, first),
                      ),
                      const SizedBox(height: 12),
                      // 두번째 버튼
                      _MbtiButton(
                        letter: second,
                        isSelected: selectedValue == second,
                        onTap: () => onToggle(dimension, second),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }
}

class _MbtiButton extends StatelessWidget {
  final String letter;
  final bool isSelected;
  final VoidCallback onTap;

  const _MbtiButton({
    required this.letter,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: AspectRatio(
        aspectRatio: 1,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          decoration: BoxDecoration(
            color: _AppColors.surfaceLight,
            borderRadius: BorderRadius.circular(22),
            boxShadow: [
              BoxShadow(
                color: isSelected
                    ? _AppColors.primaryVibrant.withValues(alpha: 0.25)
                    : CupertinoColors.black.withValues(alpha: 0.04),
                blurRadius: isSelected ? 20 : 8,
                offset: Offset(0, isSelected ? 6 : 2),
              ),
            ],
          ),
          child: Center(
            child: Text(
              letter,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 26,
                fontWeight: FontWeight.w800,
                color: isSelected
                    ? _AppColors.primaryVibrant
                    : _AppColors.gray400,
              ),
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
  final VoidCallback onDontCare;
  final VoidCallback onNext;

  const _BottomButtons({required this.onDontCare, required this.onNext});

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return Padding(
      padding: EdgeInsets.fromLTRB(24, 16, 24, bottomPadding + 24),
      child: Row(
        children: [
          // 상관없어요 버튼
          Expanded(
            child: CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: onDontCare,
              child: Container(
                height: 56,
                decoration: BoxDecoration(
                  color: _AppColors.surfaceLight,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: _AppColors.gray200),
                  boxShadow: [
                    BoxShadow(
                      color: CupertinoColors.black.withValues(alpha: 0.04),
                      blurRadius: 4,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: const Center(
                  child: Text(
                    '상관없어요',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.textMain,
                    ),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
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
                    BoxShadow(
                      color: const Color(0xFFFFC0CB).withValues(alpha: 0.5),
                      blurRadius: 16,
                      offset: const Offset(0, 6),
                    ),
                  ],
                ),
                child: const Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      '다음',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 17,
                        fontWeight: FontWeight.w700,
                        color: CupertinoColors.white,
                      ),
                    ),
                    SizedBox(width: 6),
                    Icon(
                      CupertinoIcons.arrow_right,
                      size: 18,
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
