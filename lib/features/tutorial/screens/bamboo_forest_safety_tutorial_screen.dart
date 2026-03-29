// =============================================================================
// 대나무숲 튜토리얼 (Safety) 화면
// 경로: lib/features/tutorial/screens/bamboo_forest_safety_tutorial_screen.dart
//
// 디자인: 대나무숲 메인 화면 + 신고/차단 팝업 스포트라이트 + 안전 가이드 모달
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'dart:ui';
import '../../../router/route_names.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF4438F); // Hot pink
  static const Color backgroundLight = Color(0xFFFFF5F9);
  static const Color textMain = Color(0xFF1F2937);
  static const Color textSub = Color(0xFF6B7280);
}

// =============================================================================
// 메인 화면
// =============================================================================
class BambooForestSafetyTutorialScreen extends StatefulWidget {
  const BambooForestSafetyTutorialScreen({super.key});

  @override
  State<BambooForestSafetyTutorialScreen> createState() =>
      _BambooForestSafetyTutorialScreenState();
}

class _BambooForestSafetyTutorialScreenState
    extends State<BambooForestSafetyTutorialScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    );

    _fadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOut));

    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 0.05),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOut));

    Future.delayed(const Duration(milliseconds: 200), () {
      if (mounted) _controller.forward();
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // 스포트라이트 타겟 위치 (신고 메뉴 버튼 위치 추정)
    // HTML 디자인상 카드 우측 상단 'more_horiz' 아이콘 근처
    final screenWidth = MediaQuery.of(context).size.width;
    final targetOffset = Offset(screenWidth - 40, 260); // 대략적인 위치

    return Scaffold(
      backgroundColor: _AppColors.backgroundLight,
      body: Stack(
        children: [
          // 1. 배경 (대나무숲 메인 화면 시뮬레이션)
          const _FakeBambooForestScreen(),

          // 2. 어두운 오버레이 + 스포트라이트
          Positioned.fill(
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: CustomPaint(
                painter: _SpotlightPainter(
                  spotlightCenter: targetOffset,
                  spotlightRadius: 40,
                ),
              ),
            ),
          ),

          // 3. 팝업 메뉴 시뮬레이션
          Positioned(
            top: 260,
            right: 28,
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: SlideTransition(
                position: _slideAnimation, // 위에서 아래로 떨어지는 느낌
                child: const _SimulatedPopupMenu(),
              ),
            ),
          ),

          // 4. 하단 튜토리얼 모달
          Positioned(
            left: 16,
            right: 16,
            bottom: 32,
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: SlideTransition(
                position: _slideAnimation,
                child: const _SafetyGuideModal(),
              ),
            ),
          ),

          // 5. 장식 이모지 (Floating Emojis)
          Positioned(
            top: MediaQuery.of(context).size.height * 0.25,
            left: 32,
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: const Text('🛡️', style: TextStyle(fontSize: 32)),
            ),
          ),
          Positioned(
            top: MediaQuery.of(context).size.height * 0.35,
            right: 48,
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: const Text('✨', style: TextStyle(fontSize: 24)),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 안전 가이드 모달
// =============================================================================
class _SafetyGuideModal extends StatelessWidget {
  const _SafetyGuideModal();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white, // background-light
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.2),
            blurRadius: 30,
            offset: const Offset(0, 10),
          ),
        ],
        border: Border.all(color: Colors.white.withValues(alpha: 0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '안전하고 깨끗한\n대나무숲 만들기',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                  color: _AppColors.textMain,
                  height: 1.3,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: Colors.grey[100],
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Text(
                  '6/6',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: _AppColors.textSub,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            '불쾌한 글은 신고/숨김할 수 있어요.\n설레는 분위기를 해치는 글은 노출이 줄어들 수 있어요.',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              color: _AppColors.textSub,
              height: 1.5,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            '✨ 서로 배려하는 따뜻한 공간을 만들어주세요.',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: _AppColors.primary,
            ),
          ),
          const SizedBox(height: 24),
          Row(
            children: [
              // 뒤로가기 버튼
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: Colors.grey[100],
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Material(
                  color: Colors.transparent,
                  child: InkWell(
                    borderRadius: BorderRadius.circular(16),
                    onTap: () => Navigator.of(context).pop(), // 이전 단계로
                    child: const Icon(
                      Icons.arrow_back_rounded,
                      color: Colors.grey,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              // 시작하기 버튼
              Expanded(
                child: SizedBox(
                  height: 48,
                  child: CupertinoButton(
                    color: _AppColors.primary,
                    padding: EdgeInsets.zero,
                    borderRadius: BorderRadius.circular(16),
                    onPressed: () {
                      // 튜토리얼 완료 후 메인 화면으로
                      Navigator.of(context).pushNamedAndRemoveUntil(RouteNames.main, (route) => false);
                    },
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: const [
                        Text(
                          '시작하기',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                          ),
                        ),
                        SizedBox(width: 8),
                        Icon(
                          Icons.arrow_forward_rounded,
                          color: Colors.white,
                          size: 18,
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
    );
  }
}

// =============================================================================
// 시뮬레이션된 팝업 메뉴
// =============================================================================
class _SimulatedPopupMenu extends StatelessWidget {
  const _SimulatedPopupMenu();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 160,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.1),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
        border: Border.all(color: Colors.grey[100]!),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildMenuItem(
            Icons.report_gmailerrorred_rounded,
            '신고하기',
            Colors.red,
            isFirst: true,
          ),
          const Divider(height: 1, thickness: 1, color: Color(0xFFF3F4F6)),
          _buildMenuItem(Icons.block_rounded, '차단하기', _AppColors.textMain),
          _buildMenuItem(
            Icons.visibility_off_rounded,
            '숨기기',
            _AppColors.textMain,
            isLast: true,
          ),
        ],
      ),
    );
  }

  Widget _buildMenuItem(
    IconData icon,
    String label,
    Color color, {
    bool isFirst = false,
    bool isLast = false,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.vertical(
          top: isFirst ? const Radius.circular(16) : Radius.zero,
          bottom: isLast ? const Radius.circular(16) : Radius.zero,
        ),
      ),
      child: Row(
        children: [
          Icon(
            icon,
            size: 18,
            color: color == Colors.red ? color : Colors.grey[400],
          ),
          const SizedBox(width: 8),
          Text(
            label,
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 스포트라이트 Painter
// =============================================================================
class _SpotlightPainter extends CustomPainter {
  final Offset spotlightCenter;
  final double spotlightRadius;

  _SpotlightPainter({
    required this.spotlightCenter,
    required this.spotlightRadius,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color.fromRGBO(0, 0, 0, 0.6); // Overlay color

    // 전체 화면 경로
    final backgroundPath = Path()
      ..addRect(Rect.fromLTWH(0, 0, size.width, size.height));

    // 스포트라이트 구멍 경로
    final spotlightPath = Path()
      ..addOval(
        Rect.fromCircle(center: spotlightCenter, radius: spotlightRadius),
      );

    // 차집합 (구멍 뚫기)
    final path = Path.combine(
      PathOperation.difference,
      backgroundPath,
      spotlightPath,
    );

    canvas.drawPath(path, paint);

    // 타겟 지점 하이라이트 링 (선택적)
    final ringPaint = Paint()
      ..color = _AppColors.primary.withValues(alpha: 0.5)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;

    canvas.drawCircle(spotlightCenter, spotlightRadius + 4, ringPaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

// =============================================================================
// 가짜 대나무숲 화면 (배경용 - Intro와 동일한 구조)
// =============================================================================
class _FakeBambooForestScreen extends StatelessWidget {
  const _FakeBambooForestScreen();

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Column(
        children: [
          // 헤더
          SafeArea(
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Icon(
                    Icons.menu_rounded,
                    size: 28,
                    color: Colors.black87,
                  ),
                  const Text(
                    '대나무숲',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                      color: _AppColors.textMain,
                    ),
                  ),
                  Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(
                      color: _AppColors.primary.withValues(alpha: 0.2),
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(
                      Icons.edit_rounded,
                      color: _AppColors.primary,
                      size: 16,
                    ),
                  ),
                ],
              ),
            ),
          ),

          // 칩 리스트
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
            child: Row(
              children: [
                _buildChip('전체', isSelected: true),
                const SizedBox(width: 8),
                _buildChip('인기'),
                const SizedBox(width: 8),
                _buildChip('설렘'),
              ],
            ),
          ),

          // 피드 리스트 (흐릿하게 처리)
          Expanded(
            child: Opacity(
              opacity: 0.5,
              child: Stack(
                // 블러 처리를 위해 Stack 사용 가능하지만, 여기선 Opacity만 적용
                children: [
                  ListView(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 20,
                      vertical: 8,
                    ),
                    children: [
                      _buildPostCard(
                        category: '짝사랑',
                        time: '10 mins ago',
                        content:
                            'Is it weird that I still think about the coffee we had yesterday? I barely slept because my heart was racing so fast.',
                        likes: 24,
                        comments: 5,
                        color: _AppColors.primary,
                      ),
                      const SizedBox(height: 16),
                      _buildPostCard(
                        category: '첫만남',
                        time: '35 mins ago',
                        content:
                            'Meeting someone from the app for the first time in Gangnam tonight. Wish me luck! Does this outfit look okay? 🌸',
                        likes: 156,
                        comments: 32,
                        color: Colors.purple,
                      ),
                    ],
                  ),
                  // 전체 블러 효과 (Optional)
                  Positioned.fill(
                    child: BackdropFilter(
                      filter: ImageFilter.blur(sigmaX: 1, sigmaY: 1),
                      child: Container(color: Colors.transparent),
                    ),
                  ),
                ],
              ),
            ),
          ),

          // 하단 바 (Fake)
          Container(
            height: 80,
            decoration: const BoxDecoration(
              color: Colors.white,
              border: Border(top: BorderSide(color: Color(0xFFF3F4F6))),
            ),
            padding: const EdgeInsets.only(bottom: 20),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: const [
                Icon(Icons.home_outlined, color: Colors.grey),
                Icon(Icons.forest_rounded, color: _AppColors.primary),
                // 가운데 FAB 자리
                SizedBox(width: 48),
                Icon(Icons.chat_bubble_outline_rounded, color: Colors.grey),
                Icon(Icons.person_outline_rounded, color: Colors.grey),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildChip(String label, {bool isSelected = false}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      decoration: BoxDecoration(
        color: isSelected ? _AppColors.textMain : Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: isSelected ? null : Border.all(color: Colors.grey[300]!),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: isSelected ? Colors.white : Colors.grey[600],
          fontSize: 14,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  Widget _buildPostCard({
    required String category,
    required String time,
    required String content,
    required int likes,
    required int comments,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.grey[100]!),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 10,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 2,
                    ),
                    decoration: BoxDecoration(
                      color: color.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      '[$category]',
                      style: TextStyle(
                        color: color,
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    time,
                    style: const TextStyle(color: Colors.grey, fontSize: 12),
                  ),
                ],
              ),
              const Icon(Icons.more_horiz_rounded, color: Colors.grey),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            content,
            style: const TextStyle(
              fontSize: 14,
              color: Color(0xFF1F2937),
              height: 1.5,
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Icon(Icons.favorite_rounded, color: _AppColors.textSub, size: 16),
              const SizedBox(width: 4),
              Text(
                '$likes',
                style: const TextStyle(color: Colors.grey, fontSize: 12),
              ),
              const SizedBox(width: 16),
              const Icon(
                Icons.chat_bubble_rounded,
                color: Colors.grey,
                size: 16,
              ),
              const SizedBox(width: 4),
              Text(
                '$comments',
                style: const TextStyle(color: Colors.grey, fontSize: 12),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
