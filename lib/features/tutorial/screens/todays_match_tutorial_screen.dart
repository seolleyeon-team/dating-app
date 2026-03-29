// =============================================================================
// 오늘의 매칭 튜토리얼 화면 (3카드 덱 비주얼)
// 경로: lib/features/tutorial/screens/todays_match_tutorial_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const TodaysMatchTutorialScreen()),
// );
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import '../../../router/route_names.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF0426E);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color textSecondary = Color(0xFF89616B);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray300 = Color(0xFFD1D5DB);
  static const Color pink50 = Color(0xFFFDF2F8);
  static const Color pink100 = Color(0xFFFCE7F3);
  static const Color pink200 = Color(0xFFFBCFE8);
}

// =============================================================================
// 메인 화면
// =============================================================================
class TodaysMatchTutorialScreen extends StatefulWidget {
  final VoidCallback? onStart;
  final VoidCallback? onSkip;
  final int currentStep;
  final int totalSteps;

  const TodaysMatchTutorialScreen({
    super.key,
    this.onStart,
    this.onSkip,
    this.currentStep = 3,
    this.totalSteps = 3,
  });

  @override
  State<TodaysMatchTutorialScreen> createState() =>
      _TodaysMatchTutorialScreenState();
}

class _TodaysMatchTutorialScreenState extends State<TodaysMatchTutorialScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _bounceController;

  @override
  void initState() {
    super.initState();
    _bounceController = AnimationController(
      duration: const Duration(milliseconds: 1000),
      vsync: this,
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _bounceController.dispose();
    super.dispose();
  }

  void _onStart() {
    HapticFeedback.mediumImpact();
    if (widget.onStart != null) {
      widget.onStart!();
    } else {
      Navigator.of(context).pushNamed(RouteNames.aiTasteButtonTutorial);
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
      child: SafeArea(
        child: Column(
          children: [
            // 헤더
            _Header(onSkip: _onSkip),
            // 콘텐츠
            Expanded(
              child: SingleChildScrollView(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    // 카드 덱
                    _CardDeck(bounceController: _bounceController),
                    const SizedBox(height: 16),
                    // 타이틀
                    const _TitleSection(),
                    const SizedBox(height: 8),
                  ],
                ),
              ),
            ),
            // 하단 버튼
            Padding(
              padding: EdgeInsets.fromLTRB(24, 0, 24, bottomPadding + 16),
              child: Column(
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
                        borderRadius: BorderRadius.circular(28),
                        boxShadow: [
                          BoxShadow(
                            color: _AppColors.primary.withValues(alpha: 0.3),
                            blurRadius: 20,
                            offset: const Offset(0, 8),
                          ),
                        ],
                      ),
                      child: const Center(
                        child: Text(
                          '설레연 시작하기',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            color: CupertinoColors.white,
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
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
  final VoidCallback onSkip;

  const _Header({required this.onSkip});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 4, 24, 0),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: onSkip,
            child: const Text(
              'Skip',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 14,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.5,
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
// 카드 덱
// =============================================================================
class _CardDeck extends StatelessWidget {
  final AnimationController bounceController;

  const _CardDeck({required this.bounceController});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 330,
      child: Stack(
        alignment: Alignment.center,
        children: [
          // 배경 글로우
          Container(
            width: 256,
            height: 256,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: _AppColors.primary.withValues(alpha: 0.1),
            ),
          ),
          // 왼쪽 카드
          Positioned(
            left: 20,
            child: Transform.rotate(
              angle: -0.2,
              child: Transform.translate(
                offset: const Offset(0, 16),
                child: const _BackCard(),
              ),
            ),
          ),
          // 오른쪽 카드
          Positioned(
            right: 20,
            child: Transform.rotate(
              angle: 0.2,
              child: Transform.translate(
                offset: const Offset(0, 16),
                child: const _BackCard(),
              ),
            ),
          ),
          // 중앙 카드
          _FrontCard(bounceController: bounceController),
        ],
      ),
    );
  }
}

// =============================================================================
// 뒤 카드
// =============================================================================
class _BackCard extends StatelessWidget {
  const _BackCard();

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: 0.6,
      child: Transform.scale(
        scale: 0.9,
        child: Container(
          width: 176,
          height: 256,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: _AppColors.surfaceLight,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: _AppColors.gray100),
            boxShadow: [
              BoxShadow(
                color: CupertinoColors.black.withValues(alpha: 0.05),
                blurRadius: 20,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Column(
            children: [
              const SizedBox(height: 24),
              // 아바타
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  color: _AppColors.gray100,
                  shape: BoxShape.circle,
                ),
                child: const Center(
                  child: Icon(
                    CupertinoIcons.person_fill,
                    size: 40,
                    color: _AppColors.gray300,
                  ),
                ),
              ),
              const SizedBox(height: 16),
              // 스켈레톤 라인
              Container(
                height: 8,
                width: 80,
                decoration: BoxDecoration(
                  color: _AppColors.gray100,
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
              const SizedBox(height: 8),
              Container(
                height: 8,
                width: 48,
                decoration: BoxDecoration(
                  color: _AppColors.gray100,
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 앞 카드
// =============================================================================
class _FrontCard extends StatelessWidget {
  final AnimationController bounceController;

  const _FrontCard({required this.bounceController});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 208,
      height: 288,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: _AppColors.pink50),
        boxShadow: [
          BoxShadow(
            color: _AppColors.primary.withValues(alpha: 0.15),
            blurRadius: 40,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        children: [
          const SizedBox(height: 12),
          // 아바타 + 하트 배지
          Stack(
            clipBehavior: Clip.none,
            children: [
              // 아바타
              Container(
                width: 96,
                height: 96,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [_AppColors.pink50, _AppColors.pink100],
                  ),
                  shape: BoxShape.circle,
                  border: Border.all(color: _AppColors.surfaceLight, width: 2),
                  boxShadow: [
                    BoxShadow(
                      color: CupertinoColors.black.withValues(alpha: 0.05),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: const Center(
                  child: Icon(
                    CupertinoIcons.person_fill,
                    size: 64,
                    color: _AppColors.pink200,
                  ),
                ),
              ),
              // 하트 배지
              Positioned(
                top: -4,
                right: -4,
                child: AnimatedBuilder(
                  animation: bounceController,
                  builder: (_, child) {
                    final bounce = -4 * bounceController.value;
                    return Transform.translate(
                      offset: Offset(0, bounce),
                      child: child,
                    );
                  },
                  child: Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(
                      color: _AppColors.primary,
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: _AppColors.surfaceLight,
                        width: 2,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: _AppColors.primary.withValues(alpha: 0.3),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: const Icon(
                      CupertinoIcons.heart_fill,
                      size: 16,
                      color: CupertinoColors.white,
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          // 스켈레톤 라인
          Container(
            height: 12,
            width: 120,
            decoration: BoxDecoration(
              color: _AppColors.gray100,
              borderRadius: BorderRadius.circular(6),
            ),
          ),
          const SizedBox(height: 12),
          Container(
            height: 12,
            width: 80,
            decoration: BoxDecoration(
              color: _AppColors.gray100,
              borderRadius: BorderRadius.circular(6),
            ),
          ),
          const Spacer(),
          // 하단 도트
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: _AppColors.primary.withValues(alpha: 0.2),
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 8),
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: _AppColors.primary.withValues(alpha: 0.4),
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 8),
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: _AppColors.primary.withValues(alpha: 0.2),
                  shape: BoxShape.circle,
                ),
              ),
            ],
          ),
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
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 40),
      child: Column(
        children: [
          RichText(
            textAlign: TextAlign.center,
            text: const TextSpan(
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 28,
                fontWeight: FontWeight.w700,
                height: 1.3,
              ),
              children: [
                TextSpan(
                  text: '하루 한 번,\n',
                  style: TextStyle(color: _AppColors.textMain),
                ),
                TextSpan(
                  text: '설레는',
                  style: TextStyle(color: _AppColors.primary),
                ),
                TextSpan(
                  text: ' 추천을 확인하세요',
                  style: TextStyle(color: _AppColors.textMain),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            '매일 도착하는 3명의 인연을\n놓치지 마세요.',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 16,
              height: 1.5,
              color: _AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}
