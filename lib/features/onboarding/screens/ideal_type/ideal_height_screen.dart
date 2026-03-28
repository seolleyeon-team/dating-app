// =============================================================================
// 이상형 키 범위 선택 화면
// 경로: lib/features/onboarding/screens/ideal_type/ideal_height_screen.dart
//
// 사용 예시 (main.dart):
// import 'package:seolleyeon/features/onboarding/screens/ideal_type/ideal_height_screen.dart';
// ...
// home: const IdealHeightScreen(),
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import '../../../../services/storage_service.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF8FA3);
  static const Color backgroundLight = Color(0xFFFFF5F7);
  static const Color cardLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF333333);
  static const Color textSub = Color(0xFF999999);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color pinkHighlight = Color(0xFFFFF0F3);
}

// =============================================================================
// 메인 화면
// =============================================================================
class IdealHeightScreen extends StatefulWidget {
  const IdealHeightScreen({super.key});

  @override
  State<IdealHeightScreen> createState() => _IdealHeightScreenState();
}

class _IdealHeightScreenState extends State<IdealHeightScreen> {
  // 키 범위: 140cm ~ 200cm
  static const int _minHeight = 140;
  static const int _maxHeight = 200;

  int? _selectedMinHeight;
  int? _selectedMaxHeight;
  bool _isSelectingMin = true;
  int _currentPickerHeight = 170; // 현재 피커 위치 추적

  late FixedExtentScrollController _scrollController;

  @override
  void initState() {
    super.initState();
    // 기본값: 170cm
    final initialIndex = 170 - _minHeight;
    _scrollController = FixedExtentScrollController(initialItem: initialIndex);
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _onHeightSelected(int index) {
    final height = _minHeight + index;
    setState(() {
      _currentPickerHeight = height;
      if (_isSelectingMin) {
        _selectedMinHeight = height;
      } else {
        // maxHeight는 minHeight 이상만 허용
        if (_selectedMinHeight != null && height < _selectedMinHeight!) {
          _selectedMaxHeight = _selectedMinHeight;
        } else {
          _selectedMaxHeight = height;
        }
      }
    });
    HapticFeedback.selectionClick();
  }

  void _onDontCarePressed() {
    HapticFeedback.lightImpact();
    // 상태, 모드 초기화
    setState(() {
      _selectedMinHeight = null;
      _selectedMaxHeight = null;
      _isSelectingMin = true;
      _currentPickerHeight = 170;
    });
    Navigator.of(context).pop();
  }

  void _onNextPressed() {
    HapticFeedback.mediumImpact();
    if (_isSelectingMin) {
      // 1단계: minHeight 저장 → maxHeight 선택으로 전환
      setState(() {
        _selectedMinHeight = _currentPickerHeight;
        _isSelectingMin = false;
      });
      // 피커를 minHeight + 5 위치로 이동
      final nextIndex = (_currentPickerHeight - _minHeight) + 5;
      Future.delayed(const Duration(milliseconds: 200), () {
        if (!mounted) return;
        _scrollController.animateToItem(
          nextIndex.clamp(0, _maxHeight - _minHeight),
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      });
    } else {
      // 2단계: maxHeight 저장 (minHeight 이상 보장)
      final maxH = _currentPickerHeight < (_selectedMinHeight ?? 0)
          ? _selectedMinHeight
          : _currentPickerHeight;
      () async {
        final minH = _selectedMinHeight;
        final storage = StorageService();
        final kakaoUserId = await storage.getKakaoUserId();
        if (kakaoUserId != null) {
          await storage.mergeOnboardingDraft(kakaoUserId, {
            'idealHeight': {'min': minH, 'max': maxH},
          });
        }

        if (!mounted) return;
        Navigator.of(
          context,
        ).pop({'minHeight': minH, 'maxHeight': maxH});
      }();
    }
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          // 배경 그라데이션 블러
          const _BackgroundDecoration(),
          // 메인 컨텐츠
          SafeArea(
            child: Center(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: _CardContainer(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const SizedBox(height: 32),
                      // 타이틀
                      _Title(isSelectingMin: _isSelectingMin),
                      const SizedBox(height: 32),
                      // 휠 피커
                      _HeightPicker(
                        controller: _scrollController,
                        minHeight: _minHeight,
                        maxHeight: _maxHeight,
                        onSelectedItemChanged: _onHeightSelected,
                      ),
                      const SizedBox(height: 24),
                      // 선택 표시
                      _SelectionDisplay(
                        minHeight: _selectedMinHeight,
                        maxHeight: _selectedMaxHeight,
                        isSelectingMin: _isSelectingMin,
                      ),
                      const SizedBox(height: 40),
                      // 버튼들
                      _ActionButtons(
                        onDontCare: _onDontCarePressed,
                        onNext: _onNextPressed,
                        canProceed: true,
                      ),
                      const SizedBox(height: 16),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 배경 장식
// =============================================================================
class _BackgroundDecoration extends StatelessWidget {
  const _BackgroundDecoration();

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Positioned(
          top: -50,
          left: -50,
          child: Container(
            width: 200,
            height: 200,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFFFFC0CB).withValues(alpha: 0.2),
            ),
          ),
        ),
        Positioned(
          bottom: -80,
          right: -80,
          child: Container(
            width: 250,
            height: 250,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFFFFE4E8).withValues(alpha: 0.3),
            ),
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 카드 컨테이너
// =============================================================================
class _CardContainer extends StatelessWidget {
  final Widget child;

  const _CardContainer({required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      constraints: const BoxConstraints(maxWidth: 360),
      decoration: BoxDecoration(
        color: _AppColors.cardLight,
        borderRadius: BorderRadius.circular(32),
        boxShadow: [
          BoxShadow(
            color: _AppColors.primary.withValues(alpha: 0.15),
            blurRadius: 40,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24),
        child: child,
      ),
    );
  }
}

// =============================================================================
// 타이틀
// =============================================================================
class _Title extends StatelessWidget {
  final bool isSelectingMin;

  const _Title({required this.isSelectingMin});

  @override
  Widget build(BuildContext context) {
    return Text(
      isSelectingMin ? '이상형의 최소 키를\n선택해주세요' : '이상형의 최대 키를\n선택해주세요',
      textAlign: TextAlign.center,
      style: const TextStyle(
        fontFamily: 'Pretendard',
        fontSize: 24,
        fontWeight: FontWeight.w700,
        height: 1.3,
        color: _AppColors.textMain,
      ),
    );
  }
}

// =============================================================================
// 키 휠 피커
// =============================================================================
class _HeightPicker extends StatelessWidget {
  final FixedExtentScrollController controller;
  final int minHeight;
  final int maxHeight;
  final ValueChanged<int> onSelectedItemChanged;

  const _HeightPicker({
    required this.controller,
    required this.minHeight,
    required this.maxHeight,
    required this.onSelectedItemChanged,
  });

  @override
  Widget build(BuildContext context) {
    final itemCount = maxHeight - minHeight + 1;

    return SizedBox(
      height: 200,
      child: Stack(
        children: [
          // 선택 영역 하이라이트
          Center(
            child: Container(
              height: 48,
              decoration: BoxDecoration(
                color: _AppColors.pinkHighlight,
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
          // 휠 피커
          CupertinoPicker(
            scrollController: controller,
            itemExtent: 40,
            diameterRatio: 1.5,
            selectionOverlay: const SizedBox.shrink(),
            onSelectedItemChanged: onSelectedItemChanged,
            children: List.generate(itemCount, (index) {
              final height = minHeight + index;
              return Center(
                child: Text(
                  '$height cm',
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 18,
                    fontWeight: FontWeight.w500,
                    color: _AppColors.textMain,
                  ),
                ),
              );
            }),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 선택 표시
// =============================================================================
class _SelectionDisplay extends StatelessWidget {
  final int? minHeight;
  final int? maxHeight;
  final bool isSelectingMin;

  const _SelectionDisplay({
    required this.minHeight,
    required this.maxHeight,
    required this.isSelectingMin,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        // 최소 키
        _HeightDisplay(
          value: minHeight != null ? '$minHeight' : '',
          isActive: isSelectingMin,
          suffix: '에서',
        ),
        const SizedBox(width: 12),
        // 최대 키
        _HeightDisplay(
          value: maxHeight != null ? '$maxHeight' : '',
          isActive: !isSelectingMin && minHeight != null,
          suffix: '정도까지',
        ),
      ],
    );
  }
}

class _HeightDisplay extends StatelessWidget {
  final String value;
  final bool isActive;
  final String suffix;

  const _HeightDisplay({
    required this.value,
    required this.isActive,
    required this.suffix,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          constraints: const BoxConstraints(minWidth: 48),
          padding: const EdgeInsets.only(bottom: 4),
          decoration: BoxDecoration(
            border: Border(
              bottom: BorderSide(
                color: isActive ? _AppColors.primary : _AppColors.gray200,
                width: 2,
              ),
            ),
          ),
          child: Text(
            value,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 20,
              fontWeight: FontWeight.w700,
              color: value.isNotEmpty
                  ? _AppColors.textMain
                  : _AppColors.textSub,
            ),
          ),
        ),
        const SizedBox(width: 4),
        Text(
          suffix,
          style: const TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 16,
            fontWeight: FontWeight.w400,
            color: _AppColors.textMain,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 액션 버튼들
// =============================================================================
class _ActionButtons extends StatelessWidget {
  final VoidCallback onDontCare;
  final VoidCallback onNext;
  final bool canProceed;

  const _ActionButtons({
    required this.onDontCare,
    required this.onNext,
    required this.canProceed,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        // 상관없어요 버튼
        Expanded(
          child: CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: onDontCare,
            child: Container(
              height: 56,
              decoration: BoxDecoration(
                color: CupertinoColors.white,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: _AppColors.gray200),
              ),
              child: const Center(
                child: Text(
                  '상관없어요',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 16,
                    fontWeight: FontWeight.w500,
                    color: _AppColors.textSub,
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
            onPressed: canProceed ? onNext : null,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              height: 56,
              decoration: BoxDecoration(
                color: canProceed
                    ? _AppColors.primary
                    : _AppColors.primary.withValues(alpha: 0.5),
                borderRadius: BorderRadius.circular(16),
                boxShadow: canProceed
                    ? [
                        BoxShadow(
                          color: _AppColors.primary.withValues(alpha: 0.35),
                          blurRadius: 12,
                          offset: const Offset(0, 4),
                        ),
                      ]
                    : [],
              ),
              child: const Center(
                child: Text(
                  '다음',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: CupertinoColors.white,
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
