// =============================================================================
// 슬롯머신 튜토리얼 화면 (3인 매칭 릴 애니메이션)
// 경로: lib/features/tutorial/screens/slot_machine_tutorial_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const SlotMachineTutorialScreen()),
// );
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import '../../../router/route_names.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF4D7D);
  static const Color backgroundLight = Color(0xFFFFF5F8);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color slotFrameLight = Color(0xFFF5E6EA);
  static const Color textMain = Color(0xFF1F2937);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color gray300 = Color(0xFFD1D5DB);
  static const Color gray600 = Color(0xFF4B5563);
  static const Color purple300 = Color(0xFFC4B5FD);
}

// =============================================================================
// 메인 화면
// =============================================================================
class SlotMachineTutorialScreen extends StatefulWidget {
  final VoidCallback? onStart;
  final VoidCallback? onSkip;
  final int currentStep;
  final int totalSteps;

  const SlotMachineTutorialScreen({
    super.key,
    this.onStart,
    this.onSkip,
    this.currentStep = 3,
    this.totalSteps = 3,
  });

  @override
  State<SlotMachineTutorialScreen> createState() =>
      _SlotMachineTutorialScreenState();
}

class _SlotMachineTutorialScreenState extends State<SlotMachineTutorialScreen>
    with TickerProviderStateMixin {
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      duration: const Duration(seconds: 2),
      vsync: this,
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  void _onStart() {
    HapticFeedback.mediumImpact();
    if (widget.onStart != null) {
      widget.onStart!();
    } else {
      Navigator.of(context).pushNamed(RouteNames.promiseAgreementTutorial);
    }
  }

  void _onSkip() {
    HapticFeedback.lightImpact();
    if (widget.onSkip != null) {
      widget.onSkip!();
    } else {
      Navigator.of(
        context,
      ).pushNamedAndRemoveUntil(RouteNames.main, (route) => false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          // 배경 블러 원
          Positioned(
            top: -80,
            left: -100,
            child: AnimatedBuilder(
              animation: _pulseController,
              builder: (_, child) {
                return Opacity(
                  opacity: 0.4 + (0.2 * _pulseController.value),
                  child: child,
                );
              },
              child: Container(
                width: 400,
                height: 400,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: _AppColors.primary.withValues(alpha: 0.2),
                ),
              ),
            ),
          ),
          Positioned(
            bottom: -80,
            right: -60,
            child: Container(
              width: 320,
              height: 320,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: _AppColors.purple300.withValues(alpha: 0.2),
              ),
            ),
          ),
          // 메인 콘텐츠
          SafeArea(
            child: Padding(
              padding: EdgeInsets.fromLTRB(24, 0, 24, bottomPadding + 16),
              child: Column(
                children: [
                  // 헤더
                  _Header(onSkip: _onSkip),
                  // 콘텐츠
                  Expanded(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        // 슬롯머신
                        const _SlotMachine(),
                        const SizedBox(height: 40),
                        // 타이틀
                        const _TitleSection(),
                      ],
                    ),
                  ),
                  // 하단 버튼
                  Column(
                    children: [
                      // 시작 버튼
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: _onStart,
                        child: Container(
                          width: double.infinity,
                          height: 56,
                          decoration: BoxDecoration(
                            color: _AppColors.primary,
                            borderRadius: BorderRadius.circular(18),
                            boxShadow: [
                              BoxShadow(
                                color: _AppColors.primary.withValues(
                                  alpha: 0.15,
                                ),
                                blurRadius: 20,
                                offset: const Offset(0, 10),
                              ),
                            ],
                          ),
                          child: const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(
                                '시작하기',
                                style: TextStyle(
                                  fontFamily: 'Pretendard',
                                  fontSize: 18,
                                  fontWeight: FontWeight.w700,
                                  color: CupertinoColors.white,
                                ),
                              ),
                              SizedBox(width: 8),
                              Icon(
                                CupertinoIcons.arrow_right,
                                size: 20,
                                color: CupertinoColors.white,
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final VoidCallback onSkip;

  const _Header({required this.onSkip});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // 로고
          const Row(
            children: [
              Icon(
                CupertinoIcons.heart_fill,
                color: _AppColors.primary,
                size: 28,
              ),
              SizedBox(width: 8),
              Text(
                '설레연',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 20,
                  fontWeight: FontWeight.w700,
                  color: _AppColors.textMain,
                ),
              ),
            ],
          ),
          // Skip 버튼
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: onSkip,
            child: const Text(
              'Skip',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: _AppColors.textSecondary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 슬롯머신
// =============================================================================
class _SlotMachine extends StatelessWidget {
  const _SlotMachine();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: CupertinoColors.white.withValues(alpha: 0.5)),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.1),
            blurRadius: 25,
            offset: const Offset(0, 20),
          ),
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.04),
            blurRadius: 10,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          // 그라데이션 오버레이
          Positioned.fill(
            child: Container(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(20),
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    CupertinoColors.white.withValues(alpha: 0.4),
                    CupertinoColors.white.withValues(alpha: 0),
                  ],
                ),
              ),
            ),
          ),
          // 릴 3개
          Row(
            children: List.generate(3, (index) {
              return Expanded(
                child: Padding(
                  padding: EdgeInsets.only(
                    left: index == 0 ? 0 : 6,
                    right: index == 2 ? 0 : 6,
                  ),
                  child: _SlotReel(reelIndex: index),
                ),
              );
            }),
          ),
          // 레버 (오른쪽)
          Positioned(
            right: -12,
            top: 0,
            bottom: 0,
            child: Center(
              child: Container(
                width: 12,
                height: 64,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [_AppColors.gray200, _AppColors.gray300],
                  ),
                  borderRadius: const BorderRadius.only(
                    topRight: Radius.circular(8),
                    bottomRight: Radius.circular(8),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: CupertinoColors.black.withValues(alpha: 0.1),
                      blurRadius: 4,
                      offset: const Offset(2, 2),
                    ),
                  ],
                ),
              ),
            ),
          ),
          // Matching 배지
          Positioned(
            left: 0,
            right: 0,
            bottom: -50,
            child: Center(
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 8,
                ),
                decoration: BoxDecoration(
                  color: _AppColors.primary.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(
                    color: _AppColors.primary.withValues(alpha: 0.2),
                  ),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      CupertinoIcons.sparkles,
                      size: 14,
                      color: _AppColors.primary,
                    ),
                    SizedBox(width: 6),
                    Text(
                      'Matching...',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: _AppColors.primary,
                      ),
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

// =============================================================================
// 슬롯 릴
// =============================================================================
class _SlotReel extends StatelessWidget {
  final int reelIndex;

  const _SlotReel({required this.reelIndex});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 256,
      decoration: BoxDecoration(
        color: _AppColors.slotFrameLight,
        borderRadius: BorderRadius.circular(18),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.05),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: ShaderMask(
        shaderCallback: (bounds) {
          return LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              CupertinoColors.black.withValues(alpha: 0),
              CupertinoColors.black,
              CupertinoColors.black,
              CupertinoColors.black.withValues(alpha: 0),
            ],
            stops: const [0.0, 0.2, 0.8, 1.0],
          ).createShader(bounds);
        },
        blendMode: BlendMode.dstIn,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // 상단 블러 아이템
            _ReelItem(isActive: false, size: 64),
            const SizedBox(height: 16),
            // 중앙 활성 아이템
            _ReelItem(isActive: true, size: 80),
            const SizedBox(height: 16),
            // 하단 블러 아이템
            _ReelItem(isActive: false, size: 64),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 릴 아이템
// =============================================================================
class _ReelItem extends StatelessWidget {
  final bool isActive;
  final double size;

  const _ReelItem({required this.isActive, required this.size});

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 400),
      curve: Curves.easeOut,
      width: size,
      height: size,
      transform: Matrix4.diagonal3Values(
        isActive ? 1.05 : 1.0,
        isActive ? 1.05 : 1.0,
        1.0,
      ),
      transformAlignment: Alignment.center,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: isActive
            ? _AppColors.primary.withValues(alpha: 0.1)
            : _AppColors.gray300,
        border: isActive
            ? Border.all(color: _AppColors.primary, width: 2)
            : null,
        boxShadow: isActive
            ? [
                BoxShadow(
                  color: _AppColors.primary.withValues(alpha: 0.25),
                  blurRadius: 12,
                  offset: const Offset(0, 4),
                ),
              ]
            : null,
      ),
      child: ClipOval(
        child: isActive
            ? Container(
                padding: const EdgeInsets.all(2),
                child: Container(
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: _AppColors.surfaceLight,
                  ),
                  child: const Center(
                    child: Icon(
                      CupertinoIcons.person_fill,
                      size: 32,
                      color: _AppColors.textSecondary,
                    ),
                  ),
                ),
              )
            : Container(
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: _AppColors.gray300.withValues(alpha: 0.7),
                ),
                child: const Center(
                  child: Icon(
                    CupertinoIcons.person_fill,
                    size: 24,
                    color: _AppColors.gray600,
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
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        children: [
          RichText(
            textAlign: TextAlign.center,
            text: const TextSpan(
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 24,
                fontWeight: FontWeight.w700,
                height: 1.3,
              ),
              children: [
                TextSpan(
                  text: '두근거림은 랜덤에서 오지만,\n',
                  style: TextStyle(color: _AppColors.textMain),
                ),
                TextSpan(
                  text: '경험은 안전해요',
                  style: TextStyle(color: _AppColors.primary),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          const Text(
            '게임 같은 재미와 프리미엄한 신뢰를 동시에.\n검증된 회원들과 설레는 매칭을 시작해보세요.',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              height: 1.6,
              fontWeight: FontWeight.w300,
              color: _AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}
