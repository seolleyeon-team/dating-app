import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../router/route_names.dart';

class WelcomeTutorialScreen extends StatelessWidget {
  final VoidCallback? onNext;
  final VoidCallback? onSkip;

  const WelcomeTutorialScreen({
    super.key,
    this.onNext,
    this.onSkip,
  });

  void _handleNext(BuildContext context) {
    HapticFeedback.mediumImpact();
    if (onNext != null) {
      onNext!.call();
      return;
    }
    Navigator.of(context).pushNamed(RouteNames.aiTasteTrainingTutorial);
  }

  void _handleSkip(BuildContext context) {
    HapticFeedback.lightImpact();
    if (onSkip != null) {
      onSkip!.call();
      return;
    }
    Navigator.of(
      context,
    ).pushNamedAndRemoveUntil(RouteNames.main, (route) => false);
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: const Color(0xFFFFFBFC),
      child: Stack(
        children: [
          Positioned(
            top: -120,
            left: -80,
            child: Container(
              width: 260,
              height: 260,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                color: Color(0x1FFFA6BF),
              ),
            ),
          ),
          Positioned(
            top: 120,
            right: -40,
            child: Container(
              width: 220,
              height: 220,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                color: Color(0x14FFD8E4),
              ),
            ),
          ),
          SafeArea(
            child: Padding(
              padding: EdgeInsets.fromLTRB(28, 8, 28, bottomPadding + 24),
              child: Column(
                children: [
                  Align(
                    alignment: Alignment.topRight,
                    child: CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: () => _handleSkip(context),
                      child: const Text(
                        '건너뛰기',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                          color: Color(0xFF8D8790),
                        ),
                      ),
                    ),
                  ),
                  Expanded(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Container(
                          width: 150,
                          height: 150,
                          padding: const EdgeInsets.all(20),
                          decoration: BoxDecoration(
                            color: CupertinoColors.white,
                            borderRadius: BorderRadius.circular(40),
                            boxShadow: const [
                              BoxShadow(
                                color: Color(0x12000000),
                                blurRadius: 28,
                                offset: Offset(0, 14),
                              ),
                            ],
                          ),
                          child: Image.asset(
                            'mainlogo.png',
                            fit: BoxFit.contain,
                          ),
                        ),
                        const SizedBox(height: 44),
                        const Text(
                          '설레연 가입을 환영해요!',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 30,
                            fontWeight: FontWeight.w800,
                            color: Color(0xFF221C22),
                            height: 1.25,
                          ),
                        ),
                        const SizedBox(height: 18),
                        const Text(
                          '캠퍼스 안에서 새로운 사람들과\n가까워질 수 있어요',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 18,
                            fontWeight: FontWeight.w500,
                            color: Color(0xFF6C6670),
                            height: 1.6,
                          ),
                        ),
                      ],
                    ),
                  ),
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () => _handleNext(context),
                    child: Container(
                      width: double.infinity,
                      height: 56,
                      decoration: BoxDecoration(
                        color: const Color(0xFFF24D82),
                        borderRadius: BorderRadius.circular(18),
                        boxShadow: [
                          BoxShadow(
                            color: const Color(0xFFF24D82).withValues(
                              alpha: 0.28,
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
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
