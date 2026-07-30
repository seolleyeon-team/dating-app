// =============================================================================
// 하트 충전 화면
// 경로: lib/features/profile/screens/heart_charge_screen.dart
//
// HTML to Flutter 변환 구현
// - Cupertino 스타일 적용
// - 그라데이션 배너 및 애니메이션 효과
// - 하트 상품 리스트 UI
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Colors;
import 'package:flutter/services.dart';
import 'package:seolleyeon/shared/utils/in_app_purchase_policy.dart';

// =============================================================================
// 색상 정의
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF4081); // Pinkish accent
  static const Color backgroundLight = Color(0xFFF8F9FA);
  static const Color surfaceLight = CupertinoColors.white;
  static const Color textPrimary = Color(0xFF1A1A1A);
  static const Color textSecondary = Color(0xFF8E8E93);
}

// =============================================================================
// 메인 화면
// =============================================================================
class HeartChargeScreen extends StatelessWidget {
  const HeartChargeScreen({super.key});

  void _showPurchaseUnavailable(BuildContext context) {
    HapticFeedback.selectionClick();
    showCupertinoDialog<void>(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: const Text('하트 충전'),
        content: Text(InAppPurchasePolicy.unavailableMessage),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          SafeArea(
            child: Column(
              children: [
                // 상단 고정 영역 (헤더 + 현재 보유 하트)
                Container(
                  color: _AppColors.surfaceLight,
                  child: Column(
                    children: [
                      _Header(onClose: () => Navigator.of(context).pop()),
                      const _CurrentBalance(balance: 20),
                      const SizedBox(height: 16),
                    ],
                  ),
                ),
                // 스크롤 가능한 상품 리스트
                Expanded(
                  child: ListView(
                    physics: const BouncingScrollPhysics(),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 20,
                      vertical: 16,
                    ),
                    children: [
                      _ProductCard(
                        hearts: 6,
                        price: 1500,
                        unitPrice: 250,
                        onTap: () {
                          if (!InAppPurchasePolicy.allowPurchaseUi) {
                            _showPurchaseUnavailable(context);
                          }
                        },
                      ),
                      const SizedBox(height: 16),
                      _ProductCard(
                        hearts: 18,
                        price: 4400,
                        originalPrice: 4500,
                        unitPrice: 245,
                        discountPercent: 2,
                        onTap: () {
                          if (!InAppPurchasePolicy.allowPurchaseUi) {
                            _showPurchaseUnavailable(context);
                          }
                        },
                      ),
                      const SizedBox(height: 16),
                      _ProductCard(
                        hearts: 43,
                        price: 9900,
                        originalPrice: 10750,
                        unitPrice: 231,
                        discountPercent: 7,
                        isPopular: true,
                        onTap: () {
                          if (!InAppPurchasePolicy.allowPurchaseUi) {
                            _showPurchaseUnavailable(context);
                          }
                        },
                      ),
                      const SizedBox(height: 16),
                      _ProductCard(
                        hearts: 120,
                        price: 25000,
                        originalPrice: 30000,
                        unitPrice: 209,
                        discountPercent: 16,
                        onTap: () {
                          if (!InAppPurchasePolicy.allowPurchaseUi) {
                            _showPurchaseUnavailable(context);
                          }
                        },
                      ),
                      const SizedBox(height: 24),
                      const _FooterNote(),
                      const SizedBox(height: 100), // 하단 여백
                    ],
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
  final VoidCallback onClose;

  const _Header({required this.onClose});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 16, 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          const Text(
            '하트 충전',
            style: TextStyle(
              fontFamily: 'NanumSquareRound',
              fontSize: 24,
              fontWeight: FontWeight.w700,
              color: _AppColors.textPrimary,
              letterSpacing: -0.5,
            ),
          ),
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(40, 40),
            onPressed: onClose,
            child: Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: _AppColors.backgroundLight,
                shape: BoxShape.circle,
              ),
              child: const Icon(
                CupertinoIcons.xmark,
                color: Color(0xFF424242),
                size: 20,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 현재 보유 하트
// =============================================================================
class _CurrentBalance extends StatelessWidget {
  final int balance;

  const _CurrentBalance({required this.balance});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          const Text(
            '현재 보유 하트',
            style: TextStyle(
              fontSize: 14,
              color: _AppColors.textSecondary,
              fontWeight: FontWeight.w500,
            ),
          ),
          Text(
            '$balance하트',
            style: const TextStyle(
              fontSize: 14,
              color: _AppColors.primary,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 상품 카드
// =============================================================================
class _ProductCard extends StatelessWidget {
  final int hearts;
  final int price;
  final int? originalPrice;
  final int unitPrice;
  final int? discountPercent;
  final bool isPopular;
  final VoidCallback onTap;

  const _ProductCard({
    required this.hearts,
    required this.price,
    this.originalPrice,
    required this.unitPrice,
    this.discountPercent,
    this.isPopular = false,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Stack(
        children: [
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: _AppColors.surfaceLight,
              borderRadius: BorderRadius.circular(16),
              border: isPopular
                  ? Border.all(
                      color: _AppColors.primary.withValues(alpha: 0.1),
                      width: 2,
                    )
                  : Border.all(color: Colors.transparent),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.04),
                  blurRadius: 8,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                // 좌측 아이콘 및 정보
                Row(
                  children: [
                    Container(
                      width: 48,
                      height: 48,
                      decoration: BoxDecoration(
                        color: const Color(0xFFFCE4EC), // pink-50
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: _AppColors.primary.withValues(alpha: 0.3),
                            blurRadius: 10,
                            spreadRadius: 0,
                          ),
                        ],
                      ),
                      child: const Icon(
                        CupertinoIcons.heart_fill,
                        color: _AppColors.primary,
                        size: 24,
                      ),
                    ),
                    const SizedBox(width: 16),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '$hearts하트',
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            color: _AppColors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '1하트당 $unitPrice원',
                          style: const TextStyle(
                            fontSize: 12,
                            color: _AppColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
                // 우측 가격 정보
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    if (originalPrice != null && discountPercent != null)
                      Row(
                        children: [
                          Text(
                            '$originalPrice',
                            style: const TextStyle(
                              fontSize: 12,
                              color: Color(0xFFBDBDBD),
                              decoration: TextDecoration.lineThrough,
                            ),
                          ),
                          const SizedBox(width: 6),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 6,
                              vertical: 2,
                            ),
                            decoration: BoxDecoration(
                              color: const Color(0xFFFCE4EC), // pink-100
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              '$discountPercent% 할인',
                              style: const TextStyle(
                                fontSize: 10,
                                fontWeight: FontWeight.w700,
                                color: _AppColors.primary,
                              ),
                            ),
                          ),
                        ],
                      ),
                    const SizedBox(height: 2),
                    Text(
                      '₩$price',
                      style: TextStyle(
                        fontSize: isPopular ? 20 : 18,
                        fontWeight: FontWeight.w700,
                        color: _AppColors.textPrimary,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          if (isPopular)
            Positioned(
              top: 0,
              right: 0,
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: _AppColors.primary.withValues(alpha: 0.1),
                  borderRadius: const BorderRadius.only(
                    topRight: Radius.circular(14), // Border width 고려 살짝 줄임
                    bottomLeft: Radius.circular(12),
                  ),
                ),
                child: const Text(
                  'POPULAR',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w800,
                    color: _AppColors.primary,
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
// 하단 안내 문구
// =============================================================================
class _FooterNote extends StatelessWidget {
  const _FooterNote();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Text(
        '구매 내역은 설정 > 결제 내역에서 확인 가능합니다.',
        style: TextStyle(fontSize: 12, color: _AppColors.textSecondary),
      ),
    );
  }
}
