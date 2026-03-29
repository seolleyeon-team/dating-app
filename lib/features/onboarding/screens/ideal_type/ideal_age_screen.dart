// =============================================================================
// 이상형 나이대 선택 화면
// 경로: lib/features/onboarding/screens/ideal_type/ideal_age_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const IdealAgeScreen()),
// );
// =============================================================================

import 'dart:ui';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart'; // RangeSlider 사용을 위해 필요
import 'package:flutter/services.dart';
import '../../../../services/storage_service.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFEF3976);
  static const Color backgroundLight = Color(0xFFFBF8F9);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray500 = Color(0xFF6B7280);
  static const Color gray600 = Color(0xFF4B5563);
  static const Color gray800 = Color(0xFF1F2937);
  static const Color gray900 = Color(0xFF111827);
}

// =============================================================================
// 메인 화면
// =============================================================================
class IdealAgeScreen extends StatefulWidget {
  final int currentStep;
  final int totalSteps;
  final VoidCallback? onBack;
  final VoidCallback? onSkip;
  final Function(RangeValues ageRange)? onNext;

  const IdealAgeScreen({
    super.key,
    this.currentStep = 4,
    this.totalSteps = 6,
    this.onBack,
    this.onSkip,
    this.onNext,
  });

  @override
  State<IdealAgeScreen> createState() => _IdealAgeScreenState();
}

class _IdealAgeScreenState extends State<IdealAgeScreen> {
  RangeValues _currentRangeValues = const RangeValues(23, 28);
  static const double _minAge = 18;
  static const double _maxAge = 30;

  @override
  Widget build(BuildContext context) {
    // Material SliderTheme 적용을 위한 Theme 설정
    final theme = Theme.of(context).copyWith(
      sliderTheme: SliderThemeData(
        activeTrackColor: _AppColors.primary,
        inactiveTrackColor: _AppColors.gray200,
        thumbColor: _AppColors.primary,
        overlayColor: _AppColors.primary.withValues(alpha: 0.1),
        trackHeight: 4,
        rangeThumbShape: const RoundRangeSliderThumbShape(
          enabledThumbRadius: 12,
          elevation: 4,
          pressedElevation: 6,
        ),
        trackShape: const RoundedRectSliderTrackShape(),
        overlayShape: const RoundSliderOverlayShape(overlayRadius: 24),
      ),
    );

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
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        // 타이틀
                        const _TitleSection(),
                        const SizedBox(height: 60),
                        // 슬라이더
                        Material(
                          color: Colors.transparent,
                          child: Theme(
                            data: theme,
                            child: RangeSlider(
                              values: _currentRangeValues,
                              min: _minAge,
                              max: _maxAge,
                              divisions: (_maxAge - _minAge).toInt(),
                              labels: RangeLabels(
                                '${_currentRangeValues.start.round()}',
                                '${_currentRangeValues.end.round()}',
                              ),
                              onChanged: (RangeValues values) {
                                HapticFeedback.selectionClick();
                                setState(() {
                                  _currentRangeValues = values;
                                });
                              },
                            ),
                          ),
                        ),
                        const SizedBox(height: 20),
                        // 범위 텍스트 표시
                        _AgeRangeDisplay(rangeValues: _currentRangeValues),
                      ],
                    ),
                  ),
                ),
                // 하단 버튼
                _BottomButtons(
                  onSkip: () {
                    HapticFeedback.lightImpact();
                    Navigator.of(context).pop();
                  },
                  onNext: () {
                    HapticFeedback.mediumImpact();
                    widget.onNext?.call(_currentRangeValues);
                    () async {
                      final minAge = _currentRangeValues.start.round();
                      final maxAge = _currentRangeValues.end.round();

                      final storage = StorageService();
                      final kakaoUserId = await storage.getKakaoUserId();
                      if (kakaoUserId != null) {
                        await storage.mergeOnboardingDraft(kakaoUserId, {
                          'idealAge': {'min': minAge, 'max': maxAge},
                        });
                      }

                      if (!context.mounted) return;
                      Navigator.of(context).pop({'minAge': minAge, 'maxAge': maxAge});
                    }();
                  },
                ),
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
        // 상단 그라데이션
        Positioned(
          top: 0,
          left: 0,
          right: 0,
          height: MediaQuery.of(context).size.height * 0.5,
          child: Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  _AppColors.primary.withValues(alpha: 0.05),
                  Colors.transparent,
                ],
              ),
            ),
          ),
        ),
        // 우상단 블러 원
        Positioned(
          top: -80,
          right: -80,
          child: Container(
            width: 256,
            height: 256,
            decoration: BoxDecoration(
              color: _AppColors.primary.withValues(alpha: 0.1),
              shape: BoxShape.circle,
            ),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 80, sigmaY: 80),
              child: const SizedBox(),
            ),
          ),
        ),
        // 좌중간 블러 원 (파랑)
        Positioned(
          top: 160,
          left: -80,
          child: Container(
            width: 320,
            height: 320,
            decoration: BoxDecoration(
              color: const Color(0xFFBFDBFE).withValues(alpha: 0.2), // blue-100
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
                      fontFamily: 'Pretendard',
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
          '내 이상형의 나이대를\n알려주세요',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 28,
            fontWeight: FontWeight.w700,
            height: 1.3,
            letterSpacing: -0.5,
            color: _AppColors.gray900,
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          '선호하는 연령대의 이성을 매칭해드릴게요',
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
// 나이 범위 표시 텍스트
// =============================================================================
class _AgeRangeDisplay extends StatelessWidget {
  final RangeValues rangeValues;

  const _AgeRangeDisplay({required this.rangeValues});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        // 시작 나이
        Column(
          children: [
            Text(
              '${rangeValues.start.round()}살',
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 24,
                fontWeight: FontWeight.w500,
                color: _AppColors.gray800,
              ),
            ),
            const SizedBox(height: 4),
            Container(
              width: 60,
              height: 2,
              decoration: BoxDecoration(
                color: _AppColors.primary.withValues(alpha: 0.6),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ],
        ),
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 16),
          child: Text(
            '~',
            style: TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.w300,
              color: _AppColors.gray400,
            ),
          ),
        ),
        // 끝 나이
        Column(
          children: [
            Text(
              '${rangeValues.end.round()}살',
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 24,
                fontWeight: FontWeight.w500,
                color: _AppColors.gray800,
              ),
            ),
            const SizedBox(height: 4),
            Container(
              width: 60,
              height: 2,
              decoration: BoxDecoration(
                color: _AppColors.primary.withValues(alpha: 0.6), // 활성화된 상태로 표시
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

// =============================================================================
// 하단 버튼
// =============================================================================
class _BottomButtons extends StatelessWidget {
  final VoidCallback? onSkip;
  final VoidCallback onNext;

  const _BottomButtons({this.onSkip, required this.onNext});

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
            flex: 1,
            child: CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: () {
                HapticFeedback.lightImpact();
                onSkip?.call();
              },
              child: Container(
                height: 56,
                decoration: BoxDecoration(
                  color: _AppColors.gray200,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Center(
                  child: Text(
                    '상관없어요',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.gray600,
                    ),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          // 선택 버튼
          Expanded(
            flex: 2,
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
                      blurRadius: 10,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: const Center(
                  child: Text(
                    '선택',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                      color: CupertinoColors.white,
                    ),
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
