// =============================================================================
// 약속 동의 튜토리얼 화면 (안전 정책 설명)
// 경로: lib/features/tutorial/screens/promise_agreement_tutorial_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const PromiseAgreementTutorialScreen()),
// );
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import '../../../router/route_names.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF4D88);
  static const Color backgroundLight = Color(0xFFFFF5F9);
  static const Color cardLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF1F2937);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color gray50 = Color(0xFFF9FAFB);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color pink50 = Color(0xFFFDF2F8);
  static const Color pink100 = Color(0xFFFCE7F3);
  static const Color pink200 = Color(0xFFFBCFE8);
  static const Color purple50 = Color(0xFFF3E8FF);
  static const Color purple200 = Color(0xFFE9D5FF);
  static const Color purple500 = Color(0xFFA855F7);
  static const Color blue50 = Color(0xFFEFF6FF);
  static const Color blue500 = Color(0xFF3B82F6);
}

// =============================================================================
// 메인 화면
// =============================================================================
class PromiseAgreementTutorialScreen extends StatefulWidget {
  final VoidCallback? onAgree;
  final VoidCallback? onSkip;
  final VoidCallback? onBack;

  const PromiseAgreementTutorialScreen({
    super.key,
    this.onAgree,
    this.onSkip,
    this.onBack,
  });

  @override
  State<PromiseAgreementTutorialScreen> createState() =>
      _PromiseAgreementTutorialScreenState();
}

class _PromiseAgreementTutorialScreenState
    extends State<PromiseAgreementTutorialScreen>
    with SingleTickerProviderStateMixin {
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

  void _onAgree() {
    HapticFeedback.mediumImpact();
    if (widget.onAgree != null) {
      widget.onAgree!();
    } else {
      // 튜토리얼 완료 후 메인 화면으로
      Navigator.of(context).pushNamedAndRemoveUntil(RouteNames.main, (route) => false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          // 배경 그라데이션
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            height: 256,
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    _AppColors.pink200.withValues(alpha: 0.2),
                    _AppColors.backgroundLight.withValues(alpha: 0),
                  ],
                ),
              ),
            ),
          ),
          // 블러 원
          Positioned(
            bottom: -128,
            right: -128,
            child: Container(
              width: 256,
              height: 256,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: _AppColors.purple200.withValues(alpha: 0.2),
              ),
            ),
          ),
          // 메인 콘텐츠
          SafeArea(
            child: Column(
              children: [
                // 헤더
                _Header(onBack: widget.onBack, onSkip: widget.onSkip),
                // 콘텐츠
                Expanded(
                  child: SingleChildScrollView(
                    physics: const BouncingScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(24, 32, 24, 24),
                    child: Column(
                      children: [
                        // 타이틀
                        _TitleSection(pulseController: _pulseController),
                        const SizedBox(height: 32),
                        // 약속 카드
                        const _PromiseCard(),
                        const SizedBox(height: 24),
                        // 암호화 안내
                        const _SecurityNote(),
                      ],
                    ),
                  ),
                ),
                // 하단 버튼
                Container(
                  padding: EdgeInsets.fromLTRB(24, 20, 24, bottomPadding + 24),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        _AppColors.cardLight.withValues(alpha: 0),
                        _AppColors.cardLight,
                      ],
                    ),
                  ),
                  child: CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: _onAgree,
                    child: Container(
                      width: double.infinity,
                      height: 56,
                      decoration: BoxDecoration(
                        color: _AppColors.primary,
                        borderRadius: BorderRadius.circular(18),
                        boxShadow: [
                          BoxShadow(
                            color: _AppColors.primary.withValues(alpha: 0.3),
                            blurRadius: 20,
                            offset: const Offset(0, 8),
                          ),
                        ],
                      ),
                      child: const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text(
                            '우리 함께 약속해요',
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
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final VoidCallback? onBack;
  final VoidCallback? onSkip;

  const _Header({this.onBack, this.onSkip});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // 뒤로가기
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: () {
              HapticFeedback.lightImpact();
              onBack?.call();
            },
            child: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: _AppColors.cardLight,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: CupertinoColors.black.withValues(alpha: 0.05),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: const Icon(
                CupertinoIcons.back,
                size: 20,
                color: _AppColors.textSecondary,
              ),
            ),
          ),
          // 프로그레스 바
          Container(
            width: 64,
            height: 4,
            decoration: BoxDecoration(
              color: _AppColors.gray200,
              borderRadius: BorderRadius.circular(2),
            ),
            child: FractionallySizedBox(
              alignment: Alignment.centerLeft,
              widthFactor: 0.9,
              child: Container(
                decoration: BoxDecoration(
                  color: _AppColors.primary,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
          ),
          // Skip 버튼
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: () {
              HapticFeedback.lightImpact();
              onSkip?.call();
            },
            child: const Text(
              'Skip',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: _AppColors.gray400,
              ),
            ),
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
  final AnimationController pulseController;

  const _TitleSection({required this.pulseController});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // 아이콘
        AnimatedBuilder(
          animation: pulseController,
          builder: (_, child) {
            final scale = 1.0 + (0.05 * pulseController.value);
            return Transform.scale(scale: scale, child: child);
          },
          child: Container(
            width: 80,
            height: 80,
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [_AppColors.pink100, _AppColors.purple50],
              ),
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: _AppColors.primary.withValues(alpha: 0.3),
                  blurRadius: 20,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: const Icon(
              CupertinoIcons.shield_fill,
              size: 36,
              color: _AppColors.primary,
            ),
          ),
        ),
        const SizedBox(height: 24),
        // 배지
        const Text(
          'SAFETY FIRST',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 12,
            fontWeight: FontWeight.w600,
            letterSpacing: 1.5,
            color: _AppColors.primary,
          ),
        ),
        const SizedBox(height: 12),
        // 타이틀
        const Text(
          '감시가 아니라,\n서로를 배려하는 인증',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 24,
            fontWeight: FontWeight.w700,
            height: 1.3,
            color: _AppColors.textMain,
          ),
        ),
        const SizedBox(height: 12),
        // 서브타이틀
        const Text(
          '안전한 만남을 위해\n우리가 함께하는 약속입니다.',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 14,
            height: 1.5,
            color: _AppColors.textSecondary,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 약속 카드
// =============================================================================
class _PromiseCard extends StatelessWidget {
  const _PromiseCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: _AppColors.cardLight,
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: _AppColors.pink100),
        boxShadow: [
          BoxShadow(
            color: _AppColors.primary.withValues(alpha: 0.1),
            blurRadius: 20,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        children: [
          // 투명한 얼굴 공개
          const _PromiseItem(
            icon: CupertinoIcons.person_crop_circle_fill,
            iconColor: _AppColors.primary,
            iconBgColor: _AppColors.pink50,
            title: '투명한 얼굴 공개',
            description: '프로필 사진은 본인의 실제 얼굴이어야 합니다. AI 생성 이미지나 과도한 보정은 지양해주세요.',
          ),
          const _Divider(),
          // 매너 보증금 제도
          const _PromiseItem(
            icon: CupertinoIcons.money_dollar_circle_fill,
            iconColor: _AppColors.purple500,
            iconBgColor: _AppColors.purple50,
            title: '매너 보증금 제도',
            description: 'No-show 방지를 위한 약속 보증금입니다. 만남이 성사되고 확인되면 100% 환급됩니다.',
          ),
          const _Divider(),
          // 존중하는 매너
          const _PromiseItem(
            icon: CupertinoIcons.heart_fill,
            iconColor: _AppColors.blue500,
            iconBgColor: _AppColors.blue50,
            title: '존중하는 매너',
            description: '상대방에게 불쾌감을 줄 수 있는 언행이나 행동 시 서비스 이용이 제한될 수 있습니다.',
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 약속 아이템
// =============================================================================
class _PromiseItem extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final Color iconBgColor;
  final String title;
  final String description;

  const _PromiseItem({
    required this.icon,
    required this.iconColor,
    required this.iconBgColor,
    required this.title,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: iconBgColor,
            borderRadius: BorderRadius.circular(14),
          ),
          child: Icon(icon, size: 20, color: iconColor),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: _AppColors.textMain,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                description,
                style: const TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 12,
                  height: 1.5,
                  color: _AppColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 구분선
// =============================================================================
class _Divider extends StatelessWidget {
  const _Divider();

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 20),
      height: 1,
      color: _AppColors.gray100,
    );
  }
}

// =============================================================================
// 보안 안내
// =============================================================================
class _SecurityNote extends StatelessWidget {
  const _SecurityNote();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: _AppColors.gray50,
        borderRadius: BorderRadius.circular(14),
      ),
      child: const Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(CupertinoIcons.lock_fill, size: 14, color: _AppColors.gray400),
          SizedBox(width: 8),
          Text(
            '모든 정보는 안전하게 암호화되어 관리됩니다.',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 12,
              color: _AppColors.gray400,
            ),
          ),
        ],
      ),
    );
  }
}
