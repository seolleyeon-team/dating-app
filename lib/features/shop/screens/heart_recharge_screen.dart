// =============================================================================
// 하트 충전 화면 (인앱 결제)
// 경로: lib/features/shop/screens/heart_recharge_screen.dart
//
// 사용 예시 (main.dart):
// import 'package:seolleyeon/features/shop/screens/heart_recharge_screen.dart';
// ...
// home: const HeartRechargeScreen(),
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF4081);
  static const Color backgroundLight = Color(0xFFF8F9FA);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color cardLight = Color(0xFFFFFFFF);
  static const Color textPrimary = Color(0xFF1A1A1A);
  static const Color textSecondary = Color(0xFF8E8E93);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color pink50 = Color(0xFFFDF2F8);
  static const Color pink100 = Color(0xFFFCE7F3);
  static const Color purple100 = Color(0xFFF3E8FF);
}

// =============================================================================
// 상품 데이터 모델
// =============================================================================
class _HeartPackage {
  final int hearts;
  final int pricePerHeart;
  final int originalPrice;
  final int salePrice;
  final int? discountPercent;
  final bool isPopular;

  const _HeartPackage({
    required this.hearts,
    required this.pricePerHeart,
    required this.originalPrice,
    required this.salePrice,
    this.discountPercent,
    this.isPopular = false,
  });
}

// =============================================================================
// 메인 화면
// =============================================================================
class HeartRechargeScreen extends StatefulWidget {
  const HeartRechargeScreen({super.key});

  @override
  State<HeartRechargeScreen> createState() => _HeartRechargeScreenState();
}

class _HeartRechargeScreenState extends State<HeartRechargeScreen> {
  final int _currentHearts = 20;

  final List<_HeartPackage> _packages = const [
    _HeartPackage(
      hearts: 6,
      pricePerHeart: 250,
      originalPrice: 1500,
      salePrice: 1500,
    ),
    _HeartPackage(
      hearts: 18,
      pricePerHeart: 245,
      originalPrice: 4500,
      salePrice: 4400,
      discountPercent: 2,
    ),
    _HeartPackage(
      hearts: 43,
      pricePerHeart: 231,
      originalPrice: 10750,
      salePrice: 9900,
      discountPercent: 7,
      isPopular: true,
    ),
    _HeartPackage(
      hearts: 120,
      pricePerHeart: 209,
      originalPrice: 30000,
      salePrice: 25000,
      discountPercent: 16,
    ),
  ];

  void _onPackageTap(_HeartPackage package) {
    HapticFeedback.selectionClick();
    // TODO: 결제 처리
  }

  void _onCouponTap() {
    HapticFeedback.lightImpact();
    // TODO: 쿠폰 등록 화면
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Column(
        children: [
          // 상단 섹션 (카드 배경)
          Container(
            decoration: BoxDecoration(
              color: _AppColors.surfaceLight,
              borderRadius: const BorderRadius.only(
                bottomLeft: Radius.circular(28),
                bottomRight: Radius.circular(28),
              ),
              boxShadow: [
                BoxShadow(
                  color: CupertinoColors.black.withValues(alpha: 0.04),
                  blurRadius: 8,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: SafeArea(
              bottom: false,
              child: Column(
                children: [
                  // 헤더
                  _Header(onClose: () => Navigator.of(context).pop()),
                  // 현재 하트
                  _CurrentHearts(hearts: _currentHearts),
                  // 안내 배너
                  _InfoBanner(onCouponTap: _onCouponTap),
                  const SizedBox(height: 24),
                ],
              ),
            ),
          ),
          // 상품 목록
          Expanded(
            child: ListView(
              physics: const BouncingScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 100),
              children: [
                ..._packages.map(
                  (pkg) => Padding(
                    padding: const EdgeInsets.only(bottom: 16),
                    child: _PackageCard(
                      package: pkg,
                      onTap: () => _onPackageTap(pkg),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                const _FooterNote(),
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
      padding: const EdgeInsets.fromLTRB(24, 12, 16, 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          const Text(
            '하트 충전',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 24,
              fontWeight: FontWeight.w700,
              color: _AppColors.textPrimary,
              letterSpacing: -0.5,
            ),
          ),
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(44, 44),
            onPressed: onClose,
            child: const Icon(
              CupertinoIcons.xmark,
              color: _AppColors.textPrimary,
              size: 24,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 현재 하트
// =============================================================================
class _CurrentHearts extends StatelessWidget {
  final int hearts;

  const _CurrentHearts({required this.hearts});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          const Text(
            '현재 보유 하트',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              color: _AppColors.textSecondary,
            ),
          ),
          Text(
            '$hearts하트',
            style: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: _AppColors.primary,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 안내 배너
// =============================================================================
class _InfoBanner extends StatelessWidget {
  final VoidCallback onCouponTap;

  const _InfoBanner({required this.onCouponTap});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 24),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [_AppColors.pink100, _AppColors.purple100],
        ),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Stack(
        children: [
          // 배경 블러 원
          Positioned(
            top: -40,
            right: -40,
            child: Container(
              width: 100,
              height: 100,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: _AppColors.primary.withValues(alpha: 0.2),
              ),
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: CupertinoColors.white,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: CupertinoColors.black.withValues(alpha: 0.05),
                          blurRadius: 8,
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
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          '다양한 활동엔 하트가 필요해요!',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            color: _AppColors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          '친구 초대, 좋아요 보내기 등\n더 많은 연결을 위해 하트를 충전해보세요.',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 12,
                            height: 1.5,
                            color: _AppColors.textPrimary.withValues(
                              alpha: 0.7,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Align(
                alignment: Alignment.centerRight,
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  onPressed: onCouponTap,
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        '쿠폰 등록',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: _AppColors.primary,
                        ),
                      ),
                      Icon(
                        CupertinoIcons.chevron_right,
                        size: 14,
                        color: _AppColors.primary,
                      ),
                    ],
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
// 패키지 카드
// =============================================================================
class _PackageCard extends StatelessWidget {
  final _HeartPackage package;
  final VoidCallback onTap;

  const _PackageCard({required this.package, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: _AppColors.cardLight,
          borderRadius: BorderRadius.circular(20),
          border: package.isPopular
              ? Border.all(
                  color: _AppColors.primary.withValues(alpha: 0.2),
                  width: 2,
                )
              : null,
          boxShadow: [
            BoxShadow(
              color: CupertinoColors.black.withValues(alpha: 0.04),
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            // POPULAR 배지
            if (package.isPopular)
              Positioned(
                top: -8,
                right: -8,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: _AppColors.primary.withValues(alpha: 0.1),
                    borderRadius: const BorderRadius.only(
                      topRight: Radius.circular(18),
                      bottomLeft: Radius.circular(12),
                    ),
                  ),
                  child: const Text(
                    'POPULAR',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.primary,
                    ),
                  ),
                ),
              ),
            Row(
              children: [
                // 하트 아이콘
                Container(
                  width: 48,
                  height: 48,
                  decoration: BoxDecoration(
                    color: _AppColors.pink50,
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
                // 하트 수량
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${package.hearts}하트',
                        style: const TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: _AppColors.textPrimary,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '1하트당 ${package.pricePerHeart}원',
                        style: const TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 12,
                          color: _AppColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                // 가격
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    if (package.discountPercent != null) ...[
                      Row(
                        children: [
                          Text(
                            _formatPrice(package.originalPrice),
                            style: const TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 12,
                              color: _AppColors.gray400,
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
                              color: _AppColors.pink100,
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              '${package.discountPercent}% 할인',
                              style: const TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 10,
                                fontWeight: FontWeight.w700,
                                color: _AppColors.primary,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                    ],
                    Text(
                      '₩${_formatPrice(package.salePrice)}',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: package.isPopular ? 22 : 20,
                        fontWeight: FontWeight.w700,
                        color: _AppColors.textPrimary,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _formatPrice(int price) {
    return price.toString().replaceAllMapped(
      RegExp(r'(\d{1,3})(?=(\d{3})+(?!\d))'),
      (m) => '${m[1]},',
    );
  }
}

// =============================================================================
// 하단 안내문
// =============================================================================
class _FooterNote extends StatelessWidget {
  const _FooterNote();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Text(
        '구매 내역은 설정 > 결제 내역에서 확인 가능합니다.',
        style: TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 12,
          color: _AppColors.textSecondary,
        ),
      ),
    );
  }
}
