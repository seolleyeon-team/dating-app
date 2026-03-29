// =============================================================================
// 슬롯머신(3:3 블라인드 매칭) 화면
// 경로: lib/features/event/screens/slot_machine_screen.dart
//
// HTML to Flutter 변환 구현
// - Cupertino 스타일 적용
// - 섹션별 컴포넌트 분리
// - 애니메이션 효과 추가 (슬롯머신 바운스)
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Colors; // 아이콘 매핑을 위해 일부 허용
import 'dart:ui';

// =============================================================================
// 색상 정의 (HTML 기반 + Flutter 디자인 시스템 최적화)
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFE96384); // #e96384
  static const Color primarySoft = Color(0xFFFCEEF2); // #fceef2
  static const Color backgroundLight = Color(0xFFF8F6F6); // #f8f6f6

  static const Color textMain = Color(0xFF171113);
  static const Color textSub = Color(0xFF87646D);
  static const Color white = CupertinoColors.white;

  // 그라데이션용
  static const Color slotBg1 = Color(0xFFFFF1F2); // pink-100
  static const Color slotBg2 = Color(0xFFF3E8FF); // purple-100
  static const Color slotBg3 = Color(0xFFFFEDD5); // orange-100
}

// =============================================================================
// 메인 화면
// =============================================================================
class SlotMachineScreen extends StatefulWidget {
  const SlotMachineScreen({super.key});

  @override
  State<SlotMachineScreen> createState() => _SlotMachineScreenState();
}

class _SlotMachineScreenState extends State<SlotMachineScreen> {
  @override
  Widget build(BuildContext context) {
    // 하단 탭바 높이만큼 패딩 확보 (만약 탭바가 있다면)

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: _AppColors.white.withValues(alpha: 0.9),
        border: Border(bottom: BorderSide(color: CupertinoColors.systemGrey6)),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          child: const Icon(CupertinoIcons.bars, color: _AppColors.textMain),
          onPressed: () {},
        ),
        middle: const Text(
          'Seolleyeon',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontWeight: FontWeight.w700,
            color: _AppColors.textMain,
          ),
        ),
        trailing: Stack(
          alignment: Alignment.topRight,
          children: [
            CupertinoButton(
              padding: EdgeInsets.zero,
              child: const Icon(
                CupertinoIcons.bell,
                color: _AppColors.textMain,
              ),
              onPressed: () {},
            ),
            Positioned(
              top: 10,
              right: 10,
              child: Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: _AppColors.primary,
                  shape: BoxShape.circle,
                  border: Border.all(color: _AppColors.white, width: 1.5),
                ),
              ),
            ),
          ],
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: CustomScrollView(
          physics: const BouncingScrollPhysics(),
          slivers: [
            SliverToBoxAdapter(
              child: Column(
                children: const [
                  _HeroSection(),
                  _QuickSetupSection(),
                  _DividingLine(),
                  _PromiseSection(),
                  _SlotMachineSection(),
                  _MatchedPartnersSection(),
                  _StatusCardSection(),
                  _LockedChatSection(),
                  _FaqSection(),
                  SizedBox(height: 100), // 하단 여백
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
// 구분선
// =============================================================================
class _DividingLine extends StatelessWidget {
  const _DividingLine();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 8,
      width: double.infinity,
      color: const Color(0xFFF3F4F6), // slate-100 느낌
    );
  }
}

// =============================================================================
// 섹션 1: 매칭 로비 (Hero Image)
// =============================================================================
class _HeroSection extends StatelessWidget {
  const _HeroSection();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Container(
        height: 460, // aspect ratio 4/5 approximation
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(24),
          boxShadow: [
            BoxShadow(
              color: _AppColors.primary.withValues(alpha: 0.15),
              blurRadius: 20,
              offset: const Offset(0, 4),
            ),
          ],
          image: const DecorationImage(
            image: NetworkImage(
              'https://lh3.googleusercontent.com/aida-public/AB6AXuAub4z1Y8I0FRfs7ehYu5pREoEvbsd5zt3Zsf_jnZZ4_RTNi9kZonXSd50zLI-oECGypM66Wk9DnM3EPeEVY6W3XTqvmO5VSNQfWX5GEsdGkUCJCV2PiCz17mHqv1jyU_UbQUyzibWoHm3a8G1uo8N0m1zKktg9N7SNFObY9xSekuJHHHGBCyTqYvSP2vrPxWvpYwW4dkwEsc-_nY-ddKXNmxrgj3AghtiDkgvlStKo5GH2rYnyGAg8ctsfJM8xCmjDjPqhjU6NS5o',
            ),
            fit: BoxFit.cover,
          ),
        ),
        child: Stack(
          children: [
            // Gradient Overlay
            Container(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(24),
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.transparent,
                    Colors.transparent,
                    Colors.black.withValues(alpha: 0.6),
                  ],
                  stops: const [0.0, 0.5, 1.0],
                ),
              ),
            ),
            // Badge
            Positioned(
              top: 16,
              left: 16,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(20),
                child: BackdropFilter(
                  filter: ImageFilter.blur(sigmaX: 5, sigmaY: 5),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: _AppColors.white.withValues(alpha: 0.9),
                      border: Border.all(
                        color: _AppColors.primary.withValues(alpha: 0.2),
                      ),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Row(
                      children: const [
                        Icon(
                          CupertinoIcons.gift_fill,
                          color: _AppColors.primary,
                          size: 14,
                        ),
                        SizedBox(width: 4),
                        Text(
                          '1st Match Free!',
                          style: TextStyle(
                            color: _AppColors.primary,
                            fontSize: 12,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            // Content
            Positioned(
              bottom: 24,
              left: 24,
              right: 24,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '3:3 No-face\nBlind Date',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 32,
                      fontWeight: FontWeight.w800,
                      height: 1.1,
                      letterSpacing: -0.5,
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Pure excitement. Personality first.\nZero photo pressure.',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      height: 1.4,
                      shadows: [Shadow(color: Colors.black45, blurRadius: 4)],
                    ),
                  ),
                  const SizedBox(height: 20),
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () {},
                    child: Container(
                      height: 52,
                      decoration: BoxDecoration(
                        color: _AppColors.primary,
                        borderRadius: BorderRadius.circular(30),
                        boxShadow: const [
                          BoxShadow(
                            color: Colors.black26,
                            blurRadius: 10,
                            offset: Offset(0, 4),
                          ),
                        ],
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: const [
                          Text(
                            'Start Matching',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          SizedBox(width: 8),
                          Icon(
                            CupertinoIcons.arrow_right,
                            color: Colors.white,
                            size: 20,
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
      ),
    );
  }
}

// =============================================================================
// 섹션 2: 퀵 프로필 설정
// =============================================================================
class _QuickSetupSection extends StatelessWidget {
  const _QuickSetupSection();

  @override
  Widget build(BuildContext context) {
    return Container(
      color: _AppColors.white,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: const [
              Text(
                'Quick Setup',
                style: TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                  color: _AppColors.textMain,
                  letterSpacing: -0.5,
                ),
              ),
              Text(
                'Step 1/3',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: _AppColors.textSub,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          // Info Box
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: _AppColors.primarySoft,
              borderRadius: BorderRadius.circular(16),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    CupertinoIcons.eye_slash_fill,
                    color: _AppColors.primary,
                    size: 20,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: const [
                      Text(
                        'No Photo Needed',
                        style: TextStyle(
                          color: _AppColors.primary,
                          fontWeight: FontWeight.w700,
                          fontSize: 14,
                        ),
                      ),
                      SizedBox(height: 4),
                      Text(
                        'Your profile remains a mystery until you decide to reveal it.',
                        style: TextStyle(
                          color: _AppColors.textSub,
                          fontSize: 12,
                          height: 1.3,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          // Inputs
          Column(
            children: [
              _CupertinoInput(placeholder: 'Nickname'),
              const SizedBox(height: 12),
              Row(
                children: const [
                  Expanded(child: _CupertinoSelect(placeholder: 'Birth Year')),
                  SizedBox(width: 12),
                  Expanded(child: _CupertinoSelect(placeholder: 'Gender')),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _CupertinoInput extends StatelessWidget {
  final String placeholder;
  const _CupertinoInput({required this.placeholder});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 48,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: _AppColors.backgroundLight,
        borderRadius: BorderRadius.circular(24),
      ),
      alignment: Alignment.centerLeft,
      child: Text(
        placeholder,
        style: TextStyle(
          color: _AppColors.textSub.withValues(alpha: 0.5),
          fontSize: 14,
        ),
      ),
    );
  }
}

class _CupertinoSelect extends StatelessWidget {
  final String placeholder;
  const _CupertinoSelect({required this.placeholder});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 48,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: _AppColors.backgroundLight,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            placeholder,
            style: TextStyle(
              color: _AppColors.textSub.withValues(alpha: 0.5),
              fontSize: 14,
            ),
          ),
          Icon(
            CupertinoIcons.chevron_down,
            size: 14,
            color: _AppColors.textSub.withValues(alpha: 0.5),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 섹션 3: 약속 (Promise)
// =============================================================================
class _PromiseSection extends StatelessWidget {
  const _PromiseSection();

  @override
  Widget build(BuildContext context) {
    return Container(
      color: _AppColors.white,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 32),
      child: Column(
        children: [
          Container(
            width: 48,
            height: 48,
            margin: const EdgeInsets.only(bottom: 12),
            decoration: BoxDecoration(
              color: const Color(0xFFDCFCE7), // green-100
              shape: BoxShape.circle,
            ),
            child: const Icon(
              CupertinoIcons.hand_raised_fill, // handshake 대체
              color: Color(0xFF16A34A), // green-600
              size: 24,
            ),
          ),
          const Text(
            'Our Promise',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w800,
              color: _AppColors.textMain,
            ),
          ),
          const SizedBox(height: 4),
          const Text(
            'To ensure a safe and pleasant meeting',
            style: TextStyle(fontSize: 14, color: _AppColors.textSub),
          ),
          const SizedBox(height: 24),
          // Check Items
          const _PromiseItem(text: 'I will be polite and respectful.'),
          const SizedBox(height: 12),
          const _PromiseItem(text: "I will protect others' privacy."),
          const SizedBox(height: 12),
          const _PromiseItem(text: 'I will attend the meeting on time.'),
          const SizedBox(height: 24),
          // Button
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: () {},
            child: Container(
              height: 50,
              width: double.infinity,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: const Color(0xFF0F172A), // slate-900
                borderRadius: BorderRadius.circular(25),
              ),
              child: const Text(
                'I Promise',
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                  fontSize: 14,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _PromiseItem extends StatelessWidget {
  final String text;
  const _PromiseItem({required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        border: Border.all(color: CupertinoColors.systemGrey6),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          const Icon(
            CupertinoIcons.check_mark_circled_solid,
            color: _AppColors.primary,
            size: 20,
          ),
          const SizedBox(width: 12),
          Text(
            text,
            style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: _AppColors.textMain,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 섹션 4: 슬롯머신 애니메이션
// =============================================================================
class _SlotMachineSection extends StatefulWidget {
  const _SlotMachineSection();

  @override
  State<_SlotMachineSection> createState() => _SlotMachineSectionState();
}

class _SlotMachineSectionState extends State<_SlotMachineSection>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      color: _AppColors.primary.withValues(alpha: 0.05),
      padding: const EdgeInsets.symmetric(vertical: 40),
      child: Column(
        children: [
          // Pulse Text
          AnimatedBuilder(
            animation: _controller,
            builder: (context, child) {
              return Opacity(
                opacity: 0.6 + (_controller.value * 0.4),
                child: child,
              );
            },
            child: const Text(
              'Finding your perfect 3:3 match...',
              style: TextStyle(
                color: _AppColors.primary,
                fontWeight: FontWeight.w800,
                fontSize: 18,
              ),
            ),
          ),
          const SizedBox(height: 24),
          // Slots
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _SlotItem(
                bgGradient: LinearGradient(
                  begin: Alignment.bottomCenter,
                  end: Alignment.topCenter,
                  colors: [_AppColors.slotBg1, Colors.white],
                ),
                icon: CupertinoIcons.heart_fill,
                iconColor: _AppColors.primary,
                bounceDelay: 0,
              ),
              const SizedBox(width: 8),
              _SlotItem(
                bgGradient: LinearGradient(
                  begin: Alignment.bottomCenter,
                  end: Alignment.topCenter,
                  colors: [_AppColors.slotBg2, Colors.white],
                ),
                icon: CupertinoIcons.star_fill,
                iconColor: const Color(0xFFA855F7), // purple-500
                bounceDelay: 100,
              ),
              const SizedBox(width: 8),
              _SlotItem(
                bgGradient: LinearGradient(
                  begin: Alignment.bottomCenter,
                  end: Alignment.topCenter,
                  colors: [_AppColors.slotBg3, Colors.white],
                ),
                icon: CupertinoIcons.bolt_fill,
                iconColor: const Color(0xFFF97316), // orange-500
                bounceDelay: 200,
              ),
            ],
          ),
          const SizedBox(height: 16),
          const Text(
            'Analyzing 245 active profiles...',
            style: TextStyle(color: _AppColors.textSub, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _SlotItem extends StatefulWidget {
  final Gradient bgGradient;
  final IconData icon;
  final Color iconColor;
  final int bounceDelay;

  const _SlotItem({
    required this.bgGradient,
    required this.icon,
    required this.iconColor,
    required this.bounceDelay,
  });

  @override
  State<_SlotItem> createState() => _SlotItemState();
}

class _SlotItemState extends State<_SlotItem>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _animation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    );
    _animation = Tween<double>(
      begin: 0,
      end: -10,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut));

    Future.delayed(Duration(milliseconds: widget.bounceDelay), () {
      if (mounted) _controller.repeat(reverse: true);
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 80,
      height: 112,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: _AppColors.primary.withValues(alpha: 0.2),
          width: 2,
        ),
        boxShadow: const [
          BoxShadow(color: Colors.black12, blurRadius: 4, offset: Offset(0, 2)),
        ],
      ),
      child: Stack(
        alignment: Alignment.center,
        children: [
          // Background Gradient
          Container(decoration: BoxDecoration(gradient: widget.bgGradient)),
          // Bouncing Icon
          AnimatedBuilder(
            animation: _animation,
            builder: (context, child) {
              return Transform.translate(
                offset: Offset(0, _animation.value),
                child: child,
              );
            },
            child: Icon(widget.icon, size: 36, color: widget.iconColor),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 섹션 5: 매칭된 파트너 (가로 스크롤)
// =============================================================================
class _MatchedPartnersSection extends StatelessWidget {
  const _MatchedPartnersSection();

  @override
  Widget build(BuildContext context) {
    return Container(
      color: _AppColors.backgroundLight,
      padding: const EdgeInsets.only(left: 20, top: 24, bottom: 24),
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.only(right: 20, bottom: 16),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Matched Partners',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    color: _AppColors.textMain,
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: _AppColors.primary.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Text(
                    '3 Found',
                    style: TextStyle(
                      color: _AppColors.primary,
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ],
            ),
          ),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            physics: const BouncingScrollPhysics(),
            child: Row(
              children: const [
                _PartnerCard(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [Color(0xFFFF9A9E), Color(0xFFFECFEF)],
                  ),
                  age: 27,
                  location: 'Seoul',
                  job: 'Piano Teacher',
                  mbti: 'ENFP',
                  statusColor: Color(0xFF4ADE80), // green
                ),
                SizedBox(width: 16),
                _PartnerCard(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [Color(0xFFA18CD1), Color(0xFFFBC2EB)],
                  ),
                  age: 29,
                  location: 'Busan',
                  job: 'UX Designer',
                  mbti: 'INTJ',
                  statusColor: Color(0xFFD1D5DB), // gray
                ),
                SizedBox(width: 16),
                _PartnerCard(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [Color(0xFF84FAB0), Color(0xFF8FD3F4)],
                  ),
                  age: 26,
                  location: 'Seoul',
                  job: 'Startup CEO',
                  mbti: 'ENTJ',
                  statusColor: Color(0xFF4ADE80), // green
                ),
                SizedBox(width: 20),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PartnerCard extends StatelessWidget {
  final Gradient gradient;
  final String location;
  final int age;
  final String job;
  final String mbti;
  final Color statusColor;

  const _PartnerCard({
    required this.gradient,
    required this.location,
    required this.age,
    required this.job,
    required this.mbti,
    required this.statusColor,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 140,
      height: 200,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: gradient,
        borderRadius: BorderRadius.circular(20),
        boxShadow: const [
          BoxShadow(color: Colors.black12, blurRadius: 8, offset: Offset(0, 4)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: statusColor,
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.white, width: 1),
                ),
              ),
            ],
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '$location • $age',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                job,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                  height: 1.2,
                ),
              ),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  mbti,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 10,
                    fontWeight: FontWeight.bold,
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
// 섹션 6: 상태 카드
// =============================================================================
class _StatusCardSection extends StatelessWidget {
  const _StatusCardSection();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: _AppColors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: CupertinoColors.systemGrey6),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.05),
              blurRadius: 10,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: const [
                  Text(
                    'Waiting for everyone...',
                    style: TextStyle(
                      fontWeight: FontWeight.w700,
                      fontSize: 14,
                      color: _AppColors.textMain,
                    ),
                  ),
                  SizedBox(height: 2),
                  Text(
                    'Team Consensus',
                    style: TextStyle(fontSize: 12, color: _AppColors.textSub),
                  ),
                ],
              ),
            ),
            Row(
              children: [
                _dot(true),
                _dot(true),
                _dot(false),
                _dot(false),
                _dot(false),
                _dot(false),
              ],
            ),
            const SizedBox(width: 8),
            const Text(
              '2/6',
              style: TextStyle(
                color: _AppColors.primary,
                fontWeight: FontWeight.w800,
                fontSize: 12,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _dot(bool active) {
    return Container(
      width: 12,
      height: 12,
      margin: const EdgeInsets.only(left: 4),
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: active ? _AppColors.primary : const Color(0xFFE2E8F0),
      ),
    );
  }
}

// =============================================================================
// 섹션 7: 잠긴 채팅 (Promise Money)
// =============================================================================
class _LockedChatSection extends StatelessWidget {
  const _LockedChatSection();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 300,
      margin: const EdgeInsets.only(top: 16),
      decoration: const BoxDecoration(
        color: _AppColors.white,
        border: Border(top: BorderSide(color: CupertinoColors.systemGrey6)),
      ),
      child: Stack(
        children: [
          // Blurred Chat Background
          Positioned.fill(
            child: ImageFiltered(
              imageFilter: ImageFilter.blur(sigmaX: 6, sigmaY: 6),
              child: Opacity(
                opacity: 0.5,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    children: [
                      _mockChatBubble(true, Colors.purple.shade200, 100),
                      _mockChatBubble(
                        false,
                        _AppColors.primary.withValues(alpha: 0.2),
                        80,
                      ),
                      _mockChatBubble(true, Colors.green.shade200, 120),
                    ],
                  ),
                ),
              ),
            ),
          ),
          // Lock Overlay
          Positioned.fill(
            child: Container(
              color: Colors.white.withValues(alpha: 0.4),
              alignment: Alignment.center,
              padding: const EdgeInsets.all(24),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(24),
                child: BackdropFilter(
                  filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                  child: Container(
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      color: _AppColors.white.withValues(alpha: 0.95),
                      borderRadius: BorderRadius.circular(24),
                      border: Border.all(color: Colors.white),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.1),
                          blurRadius: 20,
                          offset: const Offset(0, 10),
                        ),
                      ],
                    ),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          width: 48,
                          height: 48,
                          decoration: BoxDecoration(
                            color: _AppColors.primary.withValues(alpha: 0.1),
                            shape: BoxShape.circle,
                          ),
                          child: const Icon(
                            CupertinoIcons.lock_fill,
                            color: _AppColors.primary,
                            size: 24,
                          ),
                        ),
                        const SizedBox(height: 12),
                        const Text(
                          'Promise Money Required',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w800,
                            color: _AppColors.textMain,
                          ),
                        ),
                        const SizedBox(height: 8),
                        const Text(
                          'Deposit a small amount to ensure everyone shows up. 100% refunded after the date.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 12,
                            color: _AppColors.textSub,
                            height: 1.4,
                          ),
                        ),
                        const SizedBox(height: 16),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: const [
                            Icon(
                              CupertinoIcons.money_dollar,
                              color: Colors.green,
                              size: 16,
                            ),
                            SizedBox(width: 4),
                            Text(
                              '2/6 Collected',
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.bold,
                                color: _AppColors.textMain,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        CupertinoButton(
                          padding: EdgeInsets.zero,
                          onPressed: () {},
                          child: Container(
                            height: 48,
                            width: double.infinity,
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: _AppColors.primary,
                              borderRadius: BorderRadius.circular(24),
                              boxShadow: [
                                BoxShadow(
                                  color: _AppColors.primary.withValues(
                                    alpha: 0.3,
                                  ),
                                  blurRadius: 8,
                                  offset: const Offset(0, 4),
                                ),
                              ],
                            ),
                            child: const Text(
                              'Deposit & Enter Chat',
                              style: TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w700,
                                fontSize: 14,
                              ),
                            ),
                          ),
                        ),
                      ],
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

  Widget _mockChatBubble(bool isLeft, Color color, double width) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        mainAxisAlignment: isLeft
            ? MainAxisAlignment.start
            : MainAxisAlignment.end,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (isLeft) ...[
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
            ),
            const SizedBox(width: 8),
          ],
          Container(
            width: width + 40,
            height: 40,
            decoration: BoxDecoration(
              color: isLeft
                  ? const Color(0xFFF1F5F9)
                  : color.withValues(alpha: 0.5),
              borderRadius: BorderRadius.circular(16),
            ),
          ),
          if (!isLeft) ...[
            const SizedBox(width: 8),
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
            ),
          ],
        ],
      ),
    );
  }
}

// =============================================================================
// 섹션 9: FAQ
// =============================================================================
class _FaqSection extends StatelessWidget {
  const _FaqSection();

  @override
  Widget build(BuildContext context) {
    return Container(
      color: _AppColors.backgroundLight,
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 40),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: const [
          Text(
            'What is No-face Meeting?',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w800,
              color: _AppColors.textMain,
            ),
          ),
          SizedBox(height: 24),
          _FaqItem(
            icon: CupertinoIcons.shield_fill,
            title: 'Safe & Anonymous',
            desc:
                'We verify all users through strict ID checks. Your photos are never shown publicly.',
          ),
          SizedBox(height: 20),
          _FaqItem(
            icon: CupertinoIcons.money_dollar_circle_fill,
            title: 'Promise Money System',
            desc:
                'The deposit prevents "no-shows". It is returned immediately after you verify attendance at the meeting.',
          ),
          SizedBox(height: 20),
          _FaqItem(
            icon: CupertinoIcons.group_solid,
            title: '3:3 Group Date',
            desc:
                'Less awkward than 1:1 dates. Meet new friends in a comfortable group setting.',
          ),
        ],
      ),
    );
  }
}

class _FaqItem extends StatelessWidget {
  final IconData icon;
  final String title;
  final String desc;

  const _FaqItem({required this.icon, required this.title, required this.desc});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, color: _AppColors.textSub, size: 20),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 14,
                  color: _AppColors.textMain,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                desc,
                style: const TextStyle(
                  fontSize: 12,
                  color: _AppColors.textSub,
                  height: 1.5,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
