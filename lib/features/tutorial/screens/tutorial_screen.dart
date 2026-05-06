import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Icons;
import 'package:flutter/services.dart';

import '../../../router/route_names.dart';
import '../../matching/screens/mystery_card_screen.dart';

class TutorialScreen extends StatefulWidget {
  const TutorialScreen({super.key});

  @override
  State<TutorialScreen> createState() => _TutorialScreenState();
}

class _TutorialScreenState extends State<TutorialScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _fade;
  late final Animation<Offset> _slide;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 700),
    );
    _fade = CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic);
    _slide = Tween<Offset>(
      begin: const Offset(0, 0.06),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic));

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
    HapticFeedback.lightImpact();
    Navigator.of(context).pushNamed(RouteNames.aiTasteTrainingTutorial);
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      child: Stack(
        children: [
          const IgnorePointer(
            child: MysteryCardScreen(
              notificationCount: 1,
              remainingMatches: 2,
            ),
          ),
          Positioned.fill(
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 1.5, sigmaY: 1.5),
              child: Container(
                color: const Color(0xAA0F0B10),
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
                    opacity: _fade,
                    child: SlideTransition(
                      position: _slide,
                      child: Column(
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 14,
                              vertical: 8,
                            ),
                            decoration: BoxDecoration(
                              color: CupertinoColors.white.withValues(
                                alpha: 0.12,
                              ),
                              borderRadius: BorderRadius.circular(999),
                              border: Border.all(
                                color: CupertinoColors.white.withValues(
                                  alpha: 0.14,
                                ),
                              ),
                            ),
                            child: const Text(
                              '홈 화면 둘러보기',
                              style: TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: CupertinoColors.white,
                              ),
                            ),
                          ),
                          const SizedBox(height: 18),
                          const Text(
                            '하단 탭으로 원하는 기능으로\n빠르게 이동할 수 있어요',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 26,
                              fontWeight: FontWeight.w800,
                              color: CupertinoColors.white,
                              height: 1.35,
                            ),
                          ),
                          const SizedBox(height: 12),
                          Text(
                            '지금 보이는 홈 화면에서 채팅, 이벤트, 대나무숲까지\n바로 이동할 수 있어요.',
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
                          const SizedBox(height: 28),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 18,
                              vertical: 12,
                            ),
                            decoration: BoxDecoration(
                              color: const Color(0xFFF24D82),
                              borderRadius: BorderRadius.circular(20),
                              boxShadow: [
                                BoxShadow(
                                  color: const Color(0xFFF24D82).withValues(
                                    alpha: 0.25,
                                  ),
                                  blurRadius: 20,
                                  offset: const Offset(0, 10),
                                ),
                              ],
                            ),
                            child: const Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  Icons.touch_app_rounded,
                                  size: 16,
                                  color: CupertinoColors.white,
                                ),
                                SizedBox(width: 8),
                                Text(
                                  '탭을 눌러 기능을 이동해요',
                                  style: TextStyle(
                                    fontFamily: 'Pretendard',
                                    fontSize: 14,
                                    fontWeight: FontWeight.w700,
                                    color: CupertinoColors.white,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const Spacer(),
                  FadeTransition(
                    opacity: _fade,
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
