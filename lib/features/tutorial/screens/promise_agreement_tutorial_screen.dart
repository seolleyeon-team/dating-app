import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../router/route_names.dart';
import '../../chat/screens/premium_chat_list_screen.dart';

class PromiseAgreementTutorialScreen extends StatefulWidget {
  final VoidCallback? onAgree;

  const PromiseAgreementTutorialScreen({
    super.key,
    this.onAgree,
  });

  @override
  State<PromiseAgreementTutorialScreen> createState() =>
      _PromiseAgreementTutorialScreenState();
}

class _PromiseAgreementTutorialScreenState
    extends State<PromiseAgreementTutorialScreen>
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
    if (widget.onAgree != null) {
      widget.onAgree!();
      return;
    }
    Navigator.of(context).pushNamed(RouteNames.slotMachineTutorial);
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
          const IgnorePointer(child: ChatListScreen()),
          Positioned.fill(
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 2.5, sigmaY: 2.5),
              child: Container(
                color: const Color(0xC40E0A11),
              ),
            ),
          ),
          SafeArea(
            child: Padding(
              padding: EdgeInsets.fromLTRB(24, 24, 24, bottomPadding + 24),
              child: Column(
                children: [
                  FadeTransition(
                    opacity: fade,
                    child: const Column(
                      children: [
                        Text(
                          '채팅을 보내고 약속을 잡아보세요',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 28,
                            fontWeight: FontWeight.w800,
                            color: CupertinoColors.white,
                            height: 1.3,
                          ),
                        ),
                        SizedBox(height: 14),
                        Text(
                          '맘에 드는 상대와 채팅을 나누고,\n약속 잡기 기능으로 약속을 정할 수 있어요.\n약속 당일에는 안전도장으로 만남이\n정상적으로 진행되었는지도 확인해요.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 15,
                            fontWeight: FontWeight.w500,
                            color: Color(0xFFE8E4EA),
                            height: 1.65,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Spacer(),
                  FadeTransition(
                    opacity: fade,
                    child: const _ChatSafetyFlowCard(),
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

class _ChatSafetyFlowCard extends StatelessWidget {
  const _ChatSafetyFlowCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: CupertinoColors.white,
        borderRadius: BorderRadius.circular(26),
        boxShadow: const [
          BoxShadow(
            color: Color(0x26000000),
            blurRadius: 28,
            offset: Offset(0, 14),
          ),
        ],
      ),
      child: Column(
        children: const [
          _FlowStep(
            icon: CupertinoIcons.chat_bubble_2_fill,
            iconBg: Color(0xFFFFEEF4),
            iconColor: Color(0xFFF24D82),
            title: '1. 채팅 보내기',
            description: '서로 대화를 나누며\n분위기를 익혀보세요.',
          ),
          _FlowArrow(),
          _FlowStep(
            icon: CupertinoIcons.calendar_badge_plus,
            iconBg: Color(0xFFF6F0FF),
            iconColor: Color(0xFF8B67E6),
            title: '2. 약속 잡기',
            description: '약속 시간과 장소를 정하고\n만남을 준비해요.',
          ),
          _FlowArrow(),
          _FlowStep(
            icon: CupertinoIcons.check_mark_circled_solid,
            iconBg: Color(0xFFFFF3E8),
            iconColor: Color(0xFFF28C45),
            title: '3. 안전도장 확인',
            description: '약속 당일 안전도장으로\n정상적인 만남인지 확인해요.',
          ),
        ],
      ),
    );
  }
}

class _FlowStep extends StatelessWidget {
  final IconData icon;
  final Color iconBg;
  final Color iconColor;
  final String title;
  final String description;

  const _FlowStep({
    required this.icon,
    required this.iconBg,
    required this.iconColor,
    required this.title,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 52,
          height: 52,
          decoration: BoxDecoration(
            color: iconBg,
            borderRadius: BorderRadius.circular(18),
          ),
          child: Icon(icon, color: iconColor, size: 26),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF1E1820),
                ),
              ),
              const SizedBox(height: 6),
              Text(
                description,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                  color: Color(0xFF766F78),
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

class _FlowArrow extends StatelessWidget {
  const _FlowArrow();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: 10),
      child: Icon(
        CupertinoIcons.arrow_down,
        color: Color(0xFFBCB3BC),
        size: 18,
      ),
    );
  }
}
