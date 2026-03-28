// =============================================================================
// 네비게이션 튜토리얼 화면
// 경로: lib/features/tutorial/screens/tutorial_screen.dart
//
// 디자인: 메인 화면 배경 + Dark Overlay + Tooltips
// =============================================================================

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'dart:ui';
import '../../../router/route_names.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF4D6D); // Hot Pink
  static const Color backgroundLight = Color(0xFFF8FAFC); // Slate 50
  static const Color textMain = Color(0xFF181113);
}

// =============================================================================
// 메인 화면
// =============================================================================
class TutorialScreen extends StatefulWidget {
  const TutorialScreen({super.key});

  @override
  State<TutorialScreen> createState() => _TutorialScreenState();
}

class _TutorialScreenState extends State<TutorialScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _opacityAnimation;
  late Animation<Offset> _slideAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );

    _opacityAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOut));

    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 0.1),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOut));

    // 애니메이션 시작
    Future.delayed(const Duration(milliseconds: 300), () {
      if (mounted) _controller.forward();
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onClose() {
    HapticFeedback.lightImpact();
    // 다음 튜토리얼 화면으로 이동
    Navigator.of(context).pushNamed(RouteNames.todaysMatchTutorial);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _AppColors.backgroundLight,
      body: Stack(
        children: [
          // 1. 배경 (가상의 홈 화면) - 시각적 맥락 제공
          const _FakeHomeScreen(),

          // 2. 어두운 오버레이
          Positioned.fill(
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 2, sigmaY: 2),
              child: Container(color: Colors.black.withValues(alpha: 0.8)),
            ),
          ),

          // 3. 튜토리얼 컨텐츠 (텍스트 & 툴팁)
          SafeArea(
            child: Stack(
              children: [
                // 텍스트 영역
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 160, // 툴팁 위쪽 공간 확보
                  child: FadeTransition(
                    opacity: _opacityAnimation,
                    child: SlideTransition(
                      position: _slideAnimation,
                      child: Column(
                        children: [
                          const Text(
                            '어디로든 빠르게 이동해요',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 24,
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                              shadows: [
                                Shadow(
                                  color: Colors.black26,
                                  blurRadius: 8,
                                  offset: Offset(0, 2),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 12),
                          Text(
                            '하단 탭을 눌러 원하는 메뉴로\n바로 이동해보세요.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 14,
                              height: 1.5,
                              color: Colors.white.withValues(alpha: 0.8),
                            ),
                          ),
                          const SizedBox(height: 32),

                          // 닫기 버튼 (옵션)
                          TextButton(
                            onPressed: _onClose,
                            style: TextButton.styleFrom(
                              foregroundColor: Colors.white.withValues(
                                alpha: 0.6,
                              ),
                            ),
                            child: const Text('닫기'),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),

                // 하단: 툴팁 + 네비게이션 바 (일체형)
                Positioned(
                  left: 24,
                  right: 24,
                  bottom: 24,
                  child: FadeTransition(
                    opacity: _opacityAnimation,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        // 툴팁 라벨 행
                        // 패딩 = 네비바 border(4) + padding(12) = 16
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                          child: Row(
                            children: const [
                              Expanded(
                                child: Center(
                                  child: _TooltipItem(
                                    label: '홈',
                                    isHighlight: true,
                                    arrowColor: _AppColors.primary,
                                  ),
                                ),
                              ),
                              Expanded(
                                child: Center(child: _TooltipItem(label: '채팅')),
                              ),
                              Expanded(
                                child: Center(
                                  child: _TooltipItem(label: '이벤트'),
                                ),
                              ),
                              Expanded(
                                child: Center(
                                  child: _TooltipItem(label: '대나무숲'),
                                ),
                              ),
                              Expanded(
                                child: Center(
                                  child: _TooltipItem(label: '내 정보'),
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 8),
                        // 네비게이션 바
                        Container(
                          padding: const EdgeInsets.symmetric(
                            vertical: 12,
                            horizontal: 12,
                          ),
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(50),
                            border: Border.all(
                              color: const Color(
                                0xFFFFC2D4,
                              ).withValues(alpha: 0.3),
                              width: 4,
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: _AppColors.primary.withValues(
                                  alpha: 0.5,
                                ),
                                blurRadius: 20,
                                spreadRadius: 0,
                              ),
                            ],
                          ),
                          child: Row(
                            children: const [
                              Expanded(
                                child: _NavItem(
                                  icon: Icons.favorite,
                                  label: '설레연',
                                  color: _AppColors.primary,
                                  isSelected: true,
                                ),
                              ),
                              Expanded(
                                child: _NavItem(
                                  icon: Icons.chat_bubble_outline_rounded,
                                  label: '채팅',
                                  color: Colors.black26,
                                ),
                              ),
                              Expanded(
                                child: _NavItem(
                                  icon: Icons.calendar_today_rounded,
                                  label: '이벤트',
                                  color: Colors.black26,
                                ),
                              ),
                              Expanded(
                                child: _NavItem(
                                  icon: Icons.forest_outlined,
                                  label: '대나무숲',
                                  color: Colors.black26,
                                ),
                              ),
                              Expanded(
                                child: _NavItem(
                                  icon: Icons.person_outline_rounded,
                                  label: '내 페이지',
                                  color: Colors.black26,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
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
// 가짜 홈 화면 (배경용)
// =============================================================================
class _FakeHomeScreen extends StatelessWidget {
  const _FakeHomeScreen();

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Stack(
        children: [
          Column(
            children: [
              // 헤더
              SafeArea(
                bottom: false,
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 24,
                    vertical: 24,
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        children: const [
                          Icon(
                            Icons.favorite,
                            color: _AppColors.primary,
                            size: 28,
                          ),
                          SizedBox(width: 8),
                          Text(
                            '설레연',
                            style: TextStyle(
                              fontSize: 22,
                              fontWeight: FontWeight.bold,
                              color: _AppColors.textMain,
                              letterSpacing: -1.0,
                            ),
                          ),
                        ],
                      ),
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 4,
                            ),
                            decoration: BoxDecoration(
                              color: const Color(0xFFFFE4E6), // pink-100
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: const Text(
                              '✨ AI에게 내 취향 알려주기',
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.bold,
                                color: _AppColors.primary,
                              ),
                            ),
                          ),
                          const SizedBox(width: 16),
                          Stack(
                            children: [
                              const Icon(
                                Icons.notifications_outlined,
                                size: 28,
                                color: Colors.grey,
                              ),
                              Positioned(
                                top: 0,
                                right: 0,
                                child: Container(
                                  width: 8,
                                  height: 8,
                                  decoration: const BoxDecoration(
                                    color: _AppColors.primary,
                                    shape: BoxShape.circle,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 20),

              // 메인 콘텐츠 영역 (유저 카드)
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Column(
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: const [
                          Text(
                            '오늘의 설레연',
                            style: TextStyle(
                              fontSize: 26,
                              fontWeight: FontWeight.bold,
                              color: _AppColors.textMain,
                            ),
                          ),
                          Icon(Icons.settings, color: Colors.grey),
                        ],
                      ),
                      const SizedBox(height: 16),
                      // 카드 시뮬레이션
                      Expanded(
                        child: Container(
                          width: double.infinity,
                          decoration: BoxDecoration(
                            color: Colors.grey[300],
                            borderRadius: BorderRadius.circular(32),
                          ),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(32),
                            child: Stack(
                              fit: StackFit.expand,
                              children: [
                                // 플레이스홀더 이미지 (네트워크 이미지 사용 시 로딩 딜레이 고려)
                                Container(color: Colors.grey[200]),
                                DecoratedBox(
                                  decoration: BoxDecoration(
                                    gradient: LinearGradient(
                                      begin: Alignment.bottomCenter,
                                      end: Alignment.topCenter,
                                      colors: [
                                        Colors.black.withValues(alpha: 0.8),
                                        Colors.transparent,
                                      ],
                                      stops: const [0.0, 0.6],
                                    ),
                                  ),
                                ),
                                // 텍스트 내용 시뮬레이션
                                Positioned(
                                  left: 24,
                                  right: 24,
                                  bottom: 24,
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        children: [
                                          const Text(
                                            'Ji-min',
                                            style: TextStyle(
                                              fontSize: 32,
                                              fontWeight: FontWeight.bold,
                                              color: Colors.white,
                                            ),
                                          ),
                                          const SizedBox(width: 8),
                                          const Text(
                                            '26',
                                            style: TextStyle(
                                              fontSize: 20,
                                              color: Colors.white70,
                                            ),
                                          ),
                                          const SizedBox(width: 8),
                                          Container(
                                            padding: const EdgeInsets.symmetric(
                                              horizontal: 8,
                                              vertical: 2,
                                            ),
                                            decoration: BoxDecoration(
                                              color: Colors.white.withValues(
                                                alpha: 0.2,
                                              ),
                                              borderRadius:
                                                  BorderRadius.circular(12),
                                            ),
                                            child: const Text(
                                              '94% Match',
                                              style: TextStyle(
                                                fontSize: 10,
                                                color: Colors.white,
                                                fontWeight: FontWeight.bold,
                                              ),
                                            ),
                                          ),
                                        ],
                                      ),
                                      const SizedBox(height: 8),
                                      const Text(
                                        'Business Admin • Seoul',
                                        style: TextStyle(
                                          fontSize: 14,
                                          color: Colors.white70,
                                        ),
                                      ),
                                      const SizedBox(height: 16),
                                      Row(
                                        children: [
                                          _TagChip('TRAVEL'),
                                          const SizedBox(width: 8),
                                          _TagChip('COFFEE'),
                                          const SizedBox(width: 8),
                                          _TagChip('MUSIC'),
                                        ],
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 100), // 하단 여백
                    ],
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _TagChip extends StatelessWidget {
  final String label;
  const _TagChip(this.label);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: Colors.black45,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white10),
      ),
      child: Text(
        label,
        style: const TextStyle(fontSize: 10, color: Colors.white),
      ),
    );
  }
}

// =============================================================================
// Tooltip Item
// =============================================================================
class _TooltipItem extends StatelessWidget {
  final String label;
  final bool isHighlight;
  final Color arrowColor;

  const _TooltipItem({
    required this.label,
    this.isHighlight = false,
    this.arrowColor = Colors.white,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
            color: isHighlight ? _AppColors.primary : Colors.white,
            borderRadius: BorderRadius.circular(8),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.2),
                blurRadius: 8,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Text(
            label,
            style: TextStyle(
              // "Gowun Dodum" 폰트 대체용으로 기본 sans-serif 사용하되 스타일 매칭
              fontFamily: 'Pretendard',
              fontSize: 12,
              fontWeight: FontWeight.bold,
              color: isHighlight ? Colors.white : Colors.black87,
            ),
          ),
        ),
        // 화살표 (Triangle)
        ClipPath(
          clipper: _TriangleClipper(),
          child: Container(
            width: 12,
            height: 6,
            color: isHighlight ? _AppColors.primary : Colors.white,
          ),
        ),
      ],
    );
  }
}

class _TriangleClipper extends CustomClipper<Path> {
  @override
  Path getClip(Size size) {
    final path = Path();
    path.lineTo(size.width / 2, size.height);
    path.lineTo(size.width, 0);
    path.close();
    return path;
  }

  @override
  bool shouldReclip(covariant CustomClipper<Path> oldClipper) => false;
}

// =============================================================================
// Nav Item (Fake)
// =============================================================================
class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final bool isSelected;

  const _NavItem({
    required this.icon,
    required this.label,
    required this.color,
    this.isSelected = false,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 28, color: color),
        const SizedBox(height: 2),
        Text(
          label,
          style: TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.w600,
            color: color,
          ),
        ),
      ],
    );
  }
}
