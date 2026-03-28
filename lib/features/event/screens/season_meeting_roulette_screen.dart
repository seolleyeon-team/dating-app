// =============================================================================
// 3:3 시즌 미팅 룰렛 화면
// 경로: lib/features/event/screens/season_meeting_roulette_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const SeasonMeetingRouletteScreen()),
// );
// =============================================================================

import 'dart:ui';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color purpleSoft = Color(0xFFCE93D8);
  static const Color lavenderLight = Color(0xFFE9E4F0);
}

// =============================================================================
// 메인 화면
// =============================================================================
class SeasonMeetingRouletteScreen extends StatefulWidget {
  final VoidCallback? onBack;
  final VoidCallback? onSpin;
  final int ticketCount;

  const SeasonMeetingRouletteScreen({
    super.key,
    this.onBack,
    this.onSpin,
    this.ticketCount = 5,
  });

  @override
  State<SeasonMeetingRouletteScreen> createState() =>
      _SeasonMeetingRouletteScreenState();
}

class _SeasonMeetingRouletteScreenState
    extends State<SeasonMeetingRouletteScreen> {
  final List<String> _userImages = const [
    'https://lh3.googleusercontent.com/aida-public/AB6AXuBB6gR7HwWsX820iMKBagWyZdo6br52VDqEa0Wvv94n7MomuY8tkKpEdLBplHZawCLddd32ng-rzbCIJ754_xKDg0m4fX5k8UL-jW_80g-RuS4Wx3gPBal3rhJQC-WdMqyVeMUmfA_pFbImDrvK9xjzt69Csft3CGBaohikkG7HIf0o2At2REBn0PZNcRt54N69eQqJWi6aZU88t8EyDx-5xssGJsW4wH0OE3_HHlYyOszNnLbCn0tNJGgQG88znoQ_IOWUpGbeU97w',
    'https://lh3.googleusercontent.com/aida-public/AB6AXuBAGGszvoYIhORd33FJ05aTBC53DEisuY0kJiQiQnoBYfWs6OyX18OvUC3vzLUaOMP40jnOF3LEJCPErp8xxpcuWUxSxE5q_5FTW5V4w2kdho9RNbLDA4zYdO1wrKpzOsa5HkbQB_tH0mpWdhlS9plTGUXFuoHRFniRDXUk-phLB58XjmffthqlWVbEJfICCSXkYcDxxbu7QZqqJuJgqk8dnhFSwjxkDAtK3yCssGwF95EldLSIvXkomEj74KJVGG6K1ryVhl82k0cA',
    'https://lh3.googleusercontent.com/aida-public/AB6AXuDOsB-jftWq1FVAsGDIsjHXP10d9sm4rNZTLFJeMPRlqginqDtiAQKWWBa_JV43t3sI4ljWgZ7wJQJBbAOC_ykcqJqyIewkvr_BVg8Plrg8Y0Gvd9JBTi2fpsMfLzMLNpRjRWCG2JQF6LITla3NhZHNqoGYjKKzc2EQ60mZzxazLohSR_oz9EOBv6bcYYTBYh-xb3S3bkAKoj4dt4FG_vS_U7bDC_1oS8pXbpKXLca-413_bwWiU3bJWw7tCHgiWqMf0wPMCV9qsYY0',
  ];

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.lavenderLight,
      child: Stack(
        children: [
          // 배경 그라데이션
          _BackgroundGlow(),
          // 메인 콘텐츠
          SafeArea(
            child: Column(
              children: [
                // 헤더
                _Header(onBack: widget.onBack, ticketCount: widget.ticketCount),
                // 타이틀
                const _TitleSection(),
                // 슬롯 머신
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: _SlotMachine(userImages: _userImages),
                  ),
                ),
                // 스핀 버튼
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
                  child: _SpinButton(onPressed: widget.onSpin),
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
// 배경 글로우
// =============================================================================
class _BackgroundGlow extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        // 메인 배경
        Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Color(0xFFD1C4E9), Color(0xFFEDE7F6)],
            ),
          ),
        ),
        // 오른쪽 상단 글로우
        Positioned(
          top: -250,
          right: -100,
          child: Container(
            width: 500,
            height: 500,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFFE1BEE7).withValues(alpha: 0.4),
            ),
          ),
        ),
        // 왼쪽 하단 글로우
        Positioned(
          bottom: -150,
          left: -100,
          child: Container(
            width: 400,
            height: 400,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFFFCE4EC).withValues(alpha: 0.4),
            ),
          ),
        ),
        // 중앙 글로우
        Positioned(
          top: MediaQuery.of(context).size.height * 0.4,
          left: MediaQuery.of(context).size.width * 0.3,
          child: Container(
            width: 300,
            height: 300,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: CupertinoColors.white.withValues(alpha: 0.2),
            ),
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final VoidCallback? onBack;
  final int ticketCount;

  const _Header({this.onBack, required this.ticketCount});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
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
            child: ClipRRect(
              borderRadius: BorderRadius.circular(20),
              child: BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
                child: Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: CupertinoColors.white.withValues(alpha: 0.6),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: CupertinoColors.white.withValues(alpha: 0.4),
                    ),
                  ),
                  child: const Icon(
                    CupertinoIcons.back,
                    size: 20,
                    color: Color(0xFF64748B),
                  ),
                ),
              ),
            ),
          ),
          // 타이틀
          const Text(
            '3:3 시즌 미팅',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 18,
              fontWeight: FontWeight.w700,
              color: Color(0xFF1E293B),
            ),
          ),
          // 티켓 카운터
          ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 8,
                ),
                decoration: BoxDecoration(
                  color: CupertinoColors.white.withValues(alpha: 0.6),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: CupertinoColors.white.withValues(alpha: 0.4),
                  ),
                ),
                child: Row(
                  children: [
                    const Icon(
                      CupertinoIcons.ticket,
                      size: 18,
                      color: _AppColors.purpleSoft,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      '$ticketCount',
                      style: const TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF334155),
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

// =============================================================================
// 타이틀 섹션
// =============================================================================
class _TitleSection extends StatelessWidget {
  const _TitleSection();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Column(
        children: [
          Text(
            '3:3 시즌 미팅',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 30,
              fontWeight: FontWeight.w700,
              color: CupertinoColors.white,
              shadows: [
                Shadow(
                  color: CupertinoColors.black.withValues(alpha: 0.15),
                  offset: const Offset(0, 2),
                  blurRadius: 4,
                ),
              ],
            ),
          ),
          const SizedBox(height: 4),
          Text(
            '한 번뿐인 랜덤 매칭',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: CupertinoColors.white.withValues(alpha: 0.8),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 슬롯 머신
// =============================================================================
class _SlotMachine extends StatelessWidget {
  final List<String> userImages;

  const _SlotMachine({required this.userImages});

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        // 글래스 패널
        ClipRRect(
          borderRadius: BorderRadius.circular(40),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
            child: Container(
              decoration: BoxDecoration(
                color: CupertinoColors.white.withValues(alpha: 0.45),
                borderRadius: BorderRadius.circular(40),
                border: Border.all(
                  color: CupertinoColors.white.withValues(alpha: 0.7),
                  width: 2,
                ),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF64508C).withValues(alpha: 0.1),
                    blurRadius: 40,
                    offset: const Offset(0, 20),
                  ),
                ],
              ),
              padding: const EdgeInsets.all(16),
              child: _SlotFrame(userImages: userImages),
            ),
          ),
        ),
        // 레버
        Positioned(
          right: -8,
          top: 0,
          bottom: 0,
          child: Center(child: _Lever()),
        ),
      ],
    );
  }
}

// =============================================================================
// 슬롯 프레임
// =============================================================================
class _SlotFrame extends StatelessWidget {
  final List<String> userImages;

  const _SlotFrame({required this.userImages});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFFF3E5F5), Color(0xFFFFFFFF), Color(0xFFE1BEE7)],
        ),
        borderRadius: BorderRadius.circular(32),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.white.withValues(alpha: 0.8),
            offset: const Offset(0, 2),
            blurRadius: 4,
          ),
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.05),
            offset: const Offset(0, 10),
            blurRadius: 20,
          ),
        ],
      ),
      padding: const EdgeInsets.all(12),
      child: Stack(
        children: [
          // 슬롯 릴
          Container(
            height: 260,
            decoration: BoxDecoration(
              color: CupertinoColors.white.withValues(alpha: 0.8),
              borderRadius: BorderRadius.circular(24),
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF644078).withValues(alpha: 0.15),
                  offset: const Offset(0, 4),
                  blurRadius: 8,
                ),
              ],
            ),
            clipBehavior: Clip.antiAlias,
            child: Row(
              children: List.generate(3, (colIndex) {
                return Expanded(
                  child: Container(
                    decoration: BoxDecoration(
                      border: colIndex < 2
                          ? Border(
                              right: BorderSide(
                                color: const Color(
                                  0xFFE2E8F0,
                                ).withValues(alpha: 0.5),
                                width: 1,
                              ),
                            )
                          : null,
                    ),
                    child: Column(
                      children: [
                        // 상단 이미지 (블러)
                        Expanded(
                          child: _SlotImage(
                            imageUrl: userImages[colIndex % userImages.length],
                            isBlurred: true,
                          ),
                        ),
                        // 하단 이미지 (선명)
                        Expanded(
                          child: _SlotImage(
                            imageUrl:
                                userImages[(colIndex + 1) % userImages.length],
                            isBlurred: false,
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              }),
            ),
          ),
          // 중앙 구분선
          Positioned(
            left: 0,
            right: 0,
            top: 130,
            child: Container(
              height: 1,
              decoration: BoxDecoration(
                color: CupertinoColors.white.withValues(alpha: 0.4),
                boxShadow: [
                  BoxShadow(
                    color: CupertinoColors.black.withValues(alpha: 0.05),
                    offset: const Offset(0, 1),
                    blurRadius: 2,
                  ),
                ],
              ),
            ),
          ),
          // 상단 그라데이션 마스크
          Positioned(
            left: 0,
            right: 0,
            top: 0,
            height: 30,
            child: Container(
              decoration: BoxDecoration(
                borderRadius: const BorderRadius.vertical(
                  top: Radius.circular(24),
                ),
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    CupertinoColors.white,
                    CupertinoColors.white.withValues(alpha: 0),
                  ],
                ),
              ),
            ),
          ),
          // 하단 그라데이션 마스크
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            height: 30,
            child: Container(
              decoration: BoxDecoration(
                borderRadius: const BorderRadius.vertical(
                  bottom: Radius.circular(24),
                ),
                gradient: LinearGradient(
                  begin: Alignment.bottomCenter,
                  end: Alignment.topCenter,
                  colors: [
                    CupertinoColors.white,
                    CupertinoColors.white.withValues(alpha: 0),
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

// =============================================================================
// 슬롯 이미지
// =============================================================================
class _SlotImage extends StatelessWidget {
  final String imageUrl;
  final bool isBlurred;

  const _SlotImage({required this.imageUrl, required this.isBlurred});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      color: const Color(0xFFF1F5F9).withValues(alpha: 0.5),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: ImageFiltered(
          imageFilter: isBlurred
              ? ImageFilter.blur(sigmaX: 1, sigmaY: 1)
              : ImageFilter.blur(sigmaX: 0, sigmaY: 0),
          child: Opacity(
            opacity: isBlurred ? 0.8 : 1.0,
            child: Image.network(
              imageUrl,
              fit: BoxFit.cover,
              width: double.infinity,
              height: double.infinity,
              errorBuilder: (_, __, ___) =>
                  Container(color: _AppColors.lavenderLight),
            ),
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 레버
// =============================================================================
class _Lever extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 40,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 루비 볼
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: const RadialGradient(
                center: Alignment(-0.3, -0.3),
                colors: [
                  Color(0xFFFFF5F5),
                  Color(0xFFFF1744),
                  Color(0xFFB71C1C),
                  Color(0xFF500000),
                ],
                stops: [0.0, 0.3, 0.7, 1.0],
              ),
              border: Border.all(
                color: CupertinoColors.white.withValues(alpha: 0.3),
              ),
              boxShadow: [
                BoxShadow(
                  color: CupertinoColors.black.withValues(alpha: 0.6),
                  offset: const Offset(-2, -2),
                  blurRadius: 6,
                ),
                BoxShadow(
                  color: CupertinoColors.white.withValues(alpha: 0.8),
                  offset: const Offset(2, 2),
                  blurRadius: 8,
                ),
                BoxShadow(
                  color: const Color(0xFFB71C1C).withValues(alpha: 0.6),
                  blurRadius: 15,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Stack(
              children: [
                // 하이라이트
                Positioned(
                  top: 4,
                  left: 4,
                  child: Container(
                    width: 12,
                    height: 8,
                    decoration: BoxDecoration(
                      color: CupertinoColors.white,
                      borderRadius: BorderRadius.circular(6),
                    ),
                  ),
                ),
              ],
            ),
          ),
          // 크롬 샤프트
          Container(
            width: 8,
            height: 64,
            margin: const EdgeInsets.only(top: -6),
            decoration: BoxDecoration(
              borderRadius: const BorderRadius.vertical(
                bottom: Radius.circular(4),
              ),
              gradient: const LinearGradient(
                colors: [
                  Color(0xFF3F3F46),
                  Color(0xFFE4E4E7),
                  Color(0xFFA1A1AA),
                  Color(0xFFFFFFFF),
                  Color(0xFFA1A1AA),
                  Color(0xFFE4E4E7),
                  Color(0xFF3F3F46),
                ],
                stops: [0.0, 0.15, 0.35, 0.5, 0.65, 0.85, 1.0],
              ),
              boxShadow: [
                BoxShadow(
                  color: CupertinoColors.black.withValues(alpha: 0.2),
                  blurRadius: 4,
                ),
              ],
            ),
          ),
          // 베이스
          Container(
            width: 20,
            height: 48,
            decoration: BoxDecoration(
              borderRadius: const BorderRadius.horizontal(
                right: Radius.circular(8),
              ),
              gradient: const LinearGradient(
                colors: [
                  Color(0xFF9CA3AF),
                  Color(0xFFF1F5F9),
                  Color(0xFF6B7280),
                ],
              ),
              border: Border.all(
                color: CupertinoColors.white.withValues(alpha: 0.5),
              ),
              boxShadow: [
                BoxShadow(
                  color: CupertinoColors.black.withValues(alpha: 0.1),
                  blurRadius: 4,
                  offset: const Offset(0, 2),
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
// 스핀 버튼
// =============================================================================
class _SpinButton extends StatelessWidget {
  final VoidCallback? onPressed;

  const _SpinButton({this.onPressed});

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () {
        HapticFeedback.heavyImpact();
        onPressed?.call();
      },
      child: Container(
        width: double.infinity,
        height: 56,
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFFAB47BC), Color(0xFFCE93D8)],
          ),
          borderRadius: BorderRadius.circular(28),
          border: Border.all(
            color: CupertinoColors.white.withValues(alpha: 0.2),
          ),
          boxShadow: [
            const BoxShadow(color: Color(0xFF9575CD), offset: Offset(0, 8)),
            BoxShadow(
              color: CupertinoColors.black.withValues(alpha: 0.15),
              offset: const Offset(0, 15),
              blurRadius: 20,
            ),
          ],
        ),
        child: Center(
          child: Text(
            '이상형 룰렛 돌리기',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 18,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.5,
              color: CupertinoColors.white,
              shadows: [
                Shadow(
                  color: CupertinoColors.black.withValues(alpha: 0.2),
                  offset: const Offset(0, 1),
                  blurRadius: 2,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
