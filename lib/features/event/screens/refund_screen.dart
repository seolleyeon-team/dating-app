// =============================================================================
// 매칭 취소 및 환불 화면
// 경로: lib/features/event/screens/refund_screen.dart
//
// HTML to Flutter 변환 구현
// - Cupertino 스타일 적용
// - 매칭 취소 안내 및 환불 금액 표시
// - 홈으로 돌아가기 버튼
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Colors, Icons;

// =============================================================================
// 색상 정의
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF4081); // #FF4081
  static const Color backgroundLight = CupertinoColors.white;
  static const Color surfaceLight = Color(0xFFF4F4F5); // zinc-100
  static const Color textMain = Color(0xFF111827); // gray-900 equivalent
  static const Color textSub = Color(0xFF6B7280); // gray-500
  static const Color buttonBlack = Color(0xFF1C1C1E);
}

// =============================================================================
// 메인 화면
// =============================================================================
class RefundScreen extends StatelessWidget {
  const RefundScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      // 상태바 영역 텍스트 색상 대응을 위해 SafeArea + Column 구조 사용
      child: SafeArea(
        child: Column(
          children: [
            // 커스텀 상태바 (시간 및 아이콘) - 실제 앱에서는 시스템 상태바를 사용하므로 생략하거나
            // 디자인 요구사항에 맞춰 헤더 영역만 간단히 구현
            const _Header(),

            // 메인 컨텐츠 (중앙 정렬)
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: const [
                    // 아이콘
                    _StatusIcon(),
                    SizedBox(height: 32),

                    // 타이틀 및 메시지
                    Text(
                      '매칭이 취소되었어요',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 24,
                        fontWeight: FontWeight.w700,
                        color: _AppColors.textMain,
                        letterSpacing: -0.5,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    SizedBox(height: 12),
                    Text(
                      '아쉽게도 일부 참가자가\n참여하지 않아 매칭이 취소되었습니다.',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 14,
                        color: _AppColors.textSub,
                        height: 1.5,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    SizedBox(height: 40),

                    // 환불 정보 카드
                    _RefundInfoCard(),
                  ],
                ),
              ),
            ),

            // 하단 버튼
            const _BottomButton(),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 헤더 (시스템 상태바 영역 대체용 여백 또는 간단한 아이콘)
// =============================================================================
class _Header extends StatelessWidget {
  const _Header();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
      // 실제 구현에서는 네비게이션 동작이 필요할 수 있음
      alignment: Alignment.centerLeft,
      child: const SizedBox(height: 44), // iOS 표준 네비게이션 높이 확보
    );
  }
}

// =============================================================================
// 상태 아이콘
// =============================================================================
class _StatusIcon extends StatelessWidget {
  const _StatusIcon();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 96,
      height: 96,
      decoration: const BoxDecoration(
        color: _AppColors.surfaceLight,
        shape: BoxShape.circle,
      ),
      child: const Icon(
        Icons.sentiment_dissatisfied_rounded,
        size: 48,
        color: Color(0xFF9CA3AF), // gray-400
      ),
    );
  }
}

// =============================================================================
// 환불 정보 카드
// =============================================================================
class _RefundInfoCard extends StatelessWidget {
  const _RefundInfoCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: CupertinoColors.white,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: const Color(0xFFF3F4F6)), // gray-100
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: const [
          Text(
            '환불 예정 금액',
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: Color(0xFF4B5563), // gray-600
            ),
          ),
          _RefundAmount(),
        ],
      ),
    );
  }
}

// =============================================================================
// 환불 금액 표시
// =============================================================================
class _RefundAmount extends StatelessWidget {
  const _RefundAmount();

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: const [
        Text(
          '3 하트',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 18,
            fontWeight: FontWeight.w700,
            color: _AppColors.primary,
          ),
        ),
        SizedBox(width: 4),
        Icon(CupertinoIcons.heart_fill, size: 14, color: _AppColors.primary),
      ],
    );
  }
}

// =============================================================================
// 하단 버튼
// =============================================================================
class _BottomButton extends StatelessWidget {
  const _BottomButton();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        24,
        0,
        24,
        MediaQuery.of(context).padding.bottom + 24,
      ),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: () {
          // 홈으로 이동 로직 (Navigator.pop 등)
          Navigator.of(context).pop();
        },
        child: Container(
          width: double.infinity,
          height: 56,
          decoration: BoxDecoration(
            color: _AppColors.buttonBlack,
            borderRadius: BorderRadius.circular(100), // pill shape
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.1),
                blurRadius: 10,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          alignment: Alignment.center,
          child: const Text(
            '홈으로 돌아가기',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w700,
              color: Colors.white,
            ),
          ),
        ),
      ),
    );
  }
}
