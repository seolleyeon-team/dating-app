import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Colors, Icons;
import 'package:flutter/services.dart';

import '../../../router/route_names.dart';
import '../../community/screens/community_screen.dart';

class BambooForestWriteTutorialScreen extends StatefulWidget {
  const BambooForestWriteTutorialScreen({super.key});

  @override
  State<BambooForestWriteTutorialScreen> createState() =>
      _BambooForestWriteTutorialScreenState();
}

class _BambooForestWriteTutorialScreenState
    extends State<BambooForestWriteTutorialScreen>
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
    Navigator.of(context).pushNamed(RouteNames.bambooForestSafetyTutorial);
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;
    final fade = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOutCubic,
    );

    return CupertinoPageScaffold(
      child: Stack(
        children: [
          const IgnorePointer(child: CommunityScreen()),
          Positioned.fill(
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 2, sigmaY: 2),
              child: Container(color: const Color(0xB80E0A11)),
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
                        const Text(
                          '짝사랑, 썸 관련 고민을 털어놓거나\n다른 사람들의 썰이 궁금하다면?',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 27,
                            fontWeight: FontWeight.w800,
                            color: CupertinoColors.white,
                            height: 1.35,
                          ),
                        ),
                        const SizedBox(height: 16),
                        Text(
                          '대나무숲에서 익명으로 글을 읽고,\n직접 고민이나 이야기를 남길 수 있어요.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 15,
                            fontWeight: FontWeight.w500,
                            color: CupertinoColors.white.withValues(
                              alpha: 0.82,
                            ),
                            height: 1.6,
                          ),
                        ),
                        const SizedBox(height: 24),
                        const _TutorialNavBar(
                          selectedIndex: 3,
                          selectedLabel: '대나무숲 탭',
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
                          color: CupertinoColors.white,
                          borderRadius: BorderRadius.circular(18),
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
                                color: Color(0xFF211A21),
                              ),
                            ),
                            SizedBox(width: 8),
                            Icon(
                              CupertinoIcons.arrow_right,
                              size: 18,
                              color: Color(0xFF211A21),
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
      Icons.favorite,
      Icons.chat_bubble_outline_rounded,
      Icons.calendar_today_rounded,
      Icons.forest_outlined,
      Icons.person_outline_rounded,
    ];

    return Column(
      children: [
        Text(
          selectedLabel,
          style: const TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 13,
            fontWeight: FontWeight.w700,
            color: Color(0xFFF43F85),
          ),
        ),
        const SizedBox(height: 10),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(999),
            boxShadow: const [
              BoxShadow(
                color: Color(0x26000000),
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
                            ? const Color(0xFFFFEAF2)
                            : const Color(0xFFF4F4F5),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Icon(
                        icons[index],
                        size: 18,
                        color: selected
                            ? const Color(0xFFF43F85)
                            : const Color(0xFFA0A0AA),
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
                            ? const Color(0xFFF43F85)
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
