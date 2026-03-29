// =============================================================================
// 이상형 키 범위 선택 화면 (V3 디자인)
// 경로: lib/features/onboarding/screens/ideal_height_range_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const IdealHeightRangeScreen()),
// );
// =============================================================================

import 'dart:ui';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수 (V3 테마)
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF5E78); // Romantic pink
  static const Color backgroundLight = Color(0xFFFAFAFA);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color gray300 = Color(0xFFD1D5DB);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray500 = Color(0xFF6B7280);
  static const Color gray600 = Color(0xFF4B5563);
  static const Color gray800 = Color(0xFF1F2937);
  static const Color gray900 = Color(0xFF111827);
}

// =============================================================================
// 메인 화면
// =============================================================================
class IdealHeightRangeScreen extends StatefulWidget {
  final int initialMinHeight;
  final int minHeight;
  final int maxHeight;
  final VoidCallback? onBack;
  final VoidCallback? onSkip;
  final Function(int minHeight, int? maxHeight)? onNext;

  const IdealHeightRangeScreen({
    super.key,
    this.initialMinHeight = 175,
    this.minHeight = 140,
    this.maxHeight = 200,
    this.onBack,
    this.onSkip,
    this.onNext,
  });

  @override
  State<IdealHeightRangeScreen> createState() => _IdealHeightRangeScreenState();
}

class _IdealHeightRangeScreenState extends State<IdealHeightRangeScreen> {
  late FixedExtentScrollController _scrollController;
  late int _selectedHeight;

  @override
  void initState() {
    super.initState();
    _selectedHeight = widget.initialMinHeight;
    _scrollController = FixedExtentScrollController(
      initialItem: widget.initialMinHeight - widget.minHeight,
    );
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
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
                  onBack: widget.onBack ?? () => Navigator.of(context).pop(),
                ),
                // 콘텐츠
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        _SelectionCard(
                          selectedHeight: _selectedHeight,
                          minHeight: widget.minHeight,
                          maxHeight: widget.maxHeight,
                          scrollController: _scrollController,
                          onHeightChanged: (height) {
                            setState(() => _selectedHeight = height);
                          },
                          onSkip: widget.onSkip,
                          onNext: () {
                            HapticFeedback.mediumImpact();
                            widget.onNext?.call(_selectedHeight, null);
                          },
                        ),
                        const SizedBox(height: 32),
                        // 안내 문구
                        const Text(
                          '프로필에 표시될 키 정보를 입력해주세요.',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 12,
                            color: _AppColors.gray400,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 20),
              ],
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
        Positioned(
          top: -50,
          left: -50,
          child: Container(
            width: 384,
            height: 384,
            decoration: BoxDecoration(
              color: _AppColors.primary.withValues(alpha: 0.15),
              shape: BoxShape.circle,
            ),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 80, sigmaY: 80),
              child: const SizedBox(),
            ),
          ),
        ),
        Positioned(
          bottom: -50,
          right: -50,
          child: Container(
            width: 384,
            height: 384,
            decoration: BoxDecoration(
              color: const Color(0xFFC084FC).withValues(alpha: 0.15),
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
  final VoidCallback? onBack;

  const _Header({this.onBack});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 16),
      child: Stack(
        alignment: Alignment.center,
        children: [
          Row(
            children: [
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: () {
                  HapticFeedback.lightImpact();
                  if (onBack != null) {
                    onBack!.call();
                  } else {
                    Navigator.of(context).pop();
                  }
                },
                child: const Icon(
                  CupertinoIcons.back,
                  size: 24,
                  color: _AppColors.gray400,
                ),
              ),
            ],
          ),
          const Text(
            '설레연',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 20,
              fontWeight: FontWeight.w700,
              letterSpacing: -0.3,
              color: _AppColors.gray800,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 선택 카드
// =============================================================================
class _SelectionCard extends StatelessWidget {
  final int selectedHeight;
  final int minHeight;
  final int maxHeight;
  final FixedExtentScrollController scrollController;
  final Function(int height) onHeightChanged;
  final VoidCallback? onSkip;
  final VoidCallback onNext;

  const _SelectionCard({
    required this.selectedHeight,
    required this.minHeight,
    required this.maxHeight,
    required this.scrollController,
    required this.onHeightChanged,
    this.onSkip,
    required this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(32),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
        child: Container(
          padding: const EdgeInsets.all(32),
          decoration: BoxDecoration(
            color: _AppColors.surfaceLight.withValues(alpha: 0.8),
            borderRadius: BorderRadius.circular(32),
            border: Border.all(
              color: CupertinoColors.white.withValues(alpha: 0.4),
            ),
            boxShadow: [
              BoxShadow(
                color: CupertinoColors.black.withValues(alpha: 0.08),
                blurRadius: 40,
                offset: const Offset(0, 20),
              ),
              BoxShadow(
                color: CupertinoColors.black.withValues(alpha: 0.03),
                blurRadius: 10,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // 타이틀
              const Text(
                '이상형 키 범위를 알려주세요',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 24,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.5,
                  color: _AppColors.gray800,
                ),
              ),
              const SizedBox(height: 32),
              // 피커 영역
              SizedBox(
                height: 192, // h-48 equivalent
                child: _HeightPicker(
                  minHeight: minHeight,
                  maxHeight: maxHeight,
                  scrollController: scrollController,
                  onHeightChanged: onHeightChanged,
                ),
              ),
              const SizedBox(height: 32),
              // 선택된 범위 표시
              _RangeDisplay(selectedHeight: selectedHeight),
              const SizedBox(height: 40),
              // 버튼들
              Row(
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
                          color: _AppColors.gray100,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: _AppColors.gray200),
                        ),
                        child: const Center(
                          child: Text(
                            '상관없어요',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
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
                            BoxShadow(
                              color: _AppColors.primary.withValues(alpha: 0.3),
                              blurRadius: 16,
                              offset: const Offset(0, 4),
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
                                fontSize: 16,
                                fontWeight: FontWeight.w700,
                                color: CupertinoColors.white,
                              ),
                            ),
                            SizedBox(width: 4),
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
            ],
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 범위 표시
// =============================================================================
class _RangeDisplay extends StatelessWidget {
  final int selectedHeight;

  const _RangeDisplay({required this.selectedHeight});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        // 선택된 값
        Container(
          decoration: const BoxDecoration(
            border: Border(
              bottom: BorderSide(color: _AppColors.primary, width: 2),
            ),
          ),
          padding: const EdgeInsets.only(bottom: 2),
          child: Text(
            '$selectedHeight',
            style: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 18,
              fontWeight: FontWeight.w600,
              color: _AppColors.gray600,
            ),
          ),
        ),
        const SizedBox(width: 8),
        const Text(
          '에서',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 18,
            color: _AppColors.gray600,
          ),
        ),
        const SizedBox(width: 12),
        // 구분선 (Dash 대신 실선으로 깔끔하게)
        Container(width: 40, height: 2, color: _AppColors.gray300),
        const SizedBox(width: 12),
        const Text(
          '정도까지',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 18,
            color: _AppColors.gray600,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 키 피커
// =============================================================================
class _HeightPicker extends StatelessWidget {
  final int minHeight;
  final int maxHeight;
  final FixedExtentScrollController scrollController;
  final Function(int height) onHeightChanged;

  const _HeightPicker({
    required this.minHeight,
    required this.maxHeight,
    required this.scrollController,
    required this.onHeightChanged,
  });

  @override
  Widget build(BuildContext context) {
    final itemCount = maxHeight - minHeight + 1;

    return Stack(
      children: [
        // 중앙 하이라이트 박스
        Center(
          child: Container(
            height: 48,
            margin: const EdgeInsets.symmetric(horizontal: 16),
            decoration: BoxDecoration(
              color: _AppColors.gray100,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: _AppColors.gray200),
            ),
          ),
        ),
        // 피커
        ShaderMask(
          shaderCallback: (Rect bounds) {
            return const LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                Color(0x00FFFFFF),
                Color(0xFFFFFFFF),
                Color(0xFFFFFFFF),
                Color(0x00FFFFFF),
              ],
              stops: [0.0, 0.35, 0.65, 1.0],
            ).createShader(bounds);
          },
          blendMode: BlendMode.dstIn,
          child: CupertinoPicker(
            scrollController: scrollController,
            itemExtent: 44, // compact item height
            diameterRatio: 1.8, // flatter curve
            squeeze: 1.0,
            selectionOverlay: const SizedBox(), // hide default overlay
            onSelectedItemChanged: (index) {
              HapticFeedback.selectionClick();
              onHeightChanged(minHeight + index);
            },
            children: List.generate(itemCount, (index) {
              final height = minHeight + index;
              return Center(
                child: Text(
                  '$height cm',
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 26,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.5,
                    color: _AppColors.gray900,
                  ),
                ),
              );
            }),
          ),
        ),
      ],
    );
  }
}
