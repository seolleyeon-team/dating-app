import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../router/route_names.dart';

class SlotMachineTutorialScreen extends StatefulWidget {
  final VoidCallback? onStart;
  final VoidCallback? onSkip;

  const SlotMachineTutorialScreen({
    super.key,
    this.onStart,
    this.onSkip,
  });

  @override
  State<SlotMachineTutorialScreen> createState() =>
      _SlotMachineTutorialScreenState();
}

class _SlotMachineTutorialScreenState extends State<SlotMachineTutorialScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 700),
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _controller.forward();
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _goNext() {
    HapticFeedback.mediumImpact();
    if (widget.onStart != null) {
      widget.onStart!();
      return;
    }
    Navigator.of(context).pushNamed(RouteNames.bambooForestWriteTutorial);
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;
    final fade = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOutCubic,
    );

    return CupertinoPageScaffold(
      backgroundColor: const Color(0xFFFFF6F9),
      child: Stack(
        children: [
          Positioned(
            top: -110,
            left: -90,
            child: Container(
              width: 260,
              height: 260,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: const Color(0xFFFF4D82).withValues(alpha: 0.08),
              ),
            ),
          ),
          Positioned(
            bottom: -120,
            right: -90,
            child: Container(
              width: 240,
              height: 240,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: const Color(0xFFC4B5FD).withValues(alpha: 0.14),
              ),
            ),
          ),
          SafeArea(
            child: Padding(
              padding: EdgeInsets.fromLTRB(24, 24, 24, bottomPadding + 24),
              child: Column(
                children: [
                  const Spacer(),
                  FadeTransition(
                    opacity: fade,
                    child: Column(
                      children: [
                        const _SlotMachine(),
                        const SizedBox(height: 38),
                        const Text(
                          '3:3 랜덤 미팅\n원하는 상대가 나올 때까지\n룰렛을 돌리세요',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 28,
                            fontWeight: FontWeight.w800,
                            color: Color(0xFF1F2937),
                            height: 1.35,
                          ),
                        ),
                        const SizedBox(height: 14),
                        const Text(
                          '이벤트 탭에서 팀을 만들고,\n룰렛처럼 새로운 상대를 만나볼 수 있어요.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 15,
                            fontWeight: FontWeight.w500,
                            color: Color(0xFF6B7280),
                            height: 1.6,
                          ),
                        ),
                        const SizedBox(height: 18),
                        const _TutorialNavBar(
                          selectedIndex: 2,
                          selectedLabel: '이벤트 탭',
                        ),
                      ],
                    ),
                  ),
                  const Spacer(),
                  FadeTransition(
                    opacity: fade,
                    child: CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: _goNext,
                      child: Container(
                        width: double.infinity,
                        height: 56,
                        decoration: BoxDecoration(
                          color: const Color(0xFFF24D82),
                          borderRadius: BorderRadius.circular(18),
                          boxShadow: [
                            BoxShadow(
                              color: const Color(0xFFF24D82).withValues(
                                alpha: 0.22,
                              ),
                              blurRadius: 18,
                              offset: const Offset(0, 10),
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
                            SizedBox(width: 8),
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
            ),
          ),
        ],
      ),
    );
  }
}

class _SlotMachine extends StatelessWidget {
  const _SlotMachine();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(22, 22, 22, 34),
      decoration: BoxDecoration(
        color: CupertinoColors.white,
        borderRadius: BorderRadius.circular(28),
        boxShadow: const [
          BoxShadow(
            color: Color(0x14000000),
            blurRadius: 24,
            offset: Offset(0, 14),
          ),
        ],
      ),
      child: Stack(
        clipBehavior: Clip.none,
        children: [
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
                    colors: [Color(0xFFE5E7EB), Color(0xFFD1D5DB)],
                  ),
                  borderRadius: const BorderRadius.only(
                    topRight: Radius.circular(8),
                    bottomRight: Radius.circular(8),
                  ),
                ),
              ),
            ),
          ),
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
                  color: const Color(0xFFFFEEF4),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: const Color(0xFFFFD3E1)),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      CupertinoIcons.sparkles,
                      size: 14,
                      color: Color(0xFFF24D82),
                    ),
                    SizedBox(width: 6),
                    Text(
                      'Matching...',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFFF24D82),
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

class _SlotReel extends StatelessWidget {
  final int reelIndex;

  const _SlotReel({required this.reelIndex});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 240,
      decoration: BoxDecoration(
        color: const Color(0xFFF7EAEF),
        borderRadius: BorderRadius.circular(18),
        boxShadow: const [
          BoxShadow(
            color: Color(0x0A000000),
            blurRadius: 10,
            offset: Offset(0, 4),
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
        child: const Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            _ReelItem(isActive: false, size: 64),
            SizedBox(height: 16),
            _ReelItem(isActive: true, size: 80),
            SizedBox(height: 16),
            _ReelItem(isActive: false, size: 64),
          ],
        ),
      ),
    );
  }
}

class _ReelItem extends StatelessWidget {
  final bool isActive;
  final double size;

  const _ReelItem({required this.isActive, required this.size});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: isActive ? const Color(0x1AF24D82) : const Color(0xFFD1D5DB),
        border: isActive
            ? Border.all(color: const Color(0xFFF24D82), width: 2)
            : null,
        boxShadow: isActive
            ? [
                BoxShadow(
                  color: const Color(0xFFF24D82).withValues(alpha: 0.2),
                  blurRadius: 12,
                  offset: const Offset(0, 4),
                ),
              ]
            : null,
      ),
      child: ClipOval(
        child: Container(
          padding: isActive ? const EdgeInsets.all(3) : EdgeInsets.zero,
          child: Container(
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isActive ? CupertinoColors.white : const Color(0xFFE5E7EB),
            ),
            child: Center(
              child: Icon(
                CupertinoIcons.person_fill,
                size: isActive ? 32 : 24,
                color: isActive
                    ? const Color(0xFF6B7280)
                    : const Color(0xFF9CA3AF),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _TutorialNavBar extends StatelessWidget {
  final int selectedIndex;
  final String selectedLabel;

  const _TutorialNavBar({
    required this.selectedIndex,
    required this.selectedLabel,
  });

  @override
  Widget build(BuildContext context) {
    const labels = ['홈', '채팅', '이벤트', '대나무숲', '내 정보'];
    const icons = [
      CupertinoIcons.heart_fill,
      CupertinoIcons.chat_bubble_2_fill,
      CupertinoIcons.calendar,
      CupertinoIcons.leaf_arrow_circlepath,
      CupertinoIcons.person_fill,
    ];

    return Column(
      children: [
        Text(
          selectedLabel,
          style: const TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 13,
            fontWeight: FontWeight.w700,
            color: Color(0xFFF24D82),
          ),
        ),
        const SizedBox(height: 10),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
          decoration: BoxDecoration(
            color: CupertinoColors.white,
            borderRadius: BorderRadius.circular(999),
            boxShadow: const [
              BoxShadow(
                color: Color(0x12000000),
                blurRadius: 18,
                offset: Offset(0, 10),
              ),
            ],
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: List.generate(labels.length, (index) {
              final selected = index == selectedIndex;
              return Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 34,
                      height: 34,
                      decoration: BoxDecoration(
                        color: selected
                            ? const Color(0xFFFFEEF4)
                            : const Color(0xFFF4F4F5),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Icon(
                        icons[index],
                        size: 18,
                        color: selected
                            ? const Color(0xFFF24D82)
                            : const Color(0xFF9CA3AF),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      labels[index],
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 11,
                        fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                        color: selected
                            ? const Color(0xFFF24D82)
                            : const Color(0xFF8F8A92),
                      ),
                    ),
                  ],
                ),
              );
            }),
          ),
        ),
      ],
    );
  }
}
