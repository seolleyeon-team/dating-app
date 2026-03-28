// =============================================================================
// 파트너 혜택 상세 화면 (제휴 매장)
// 경로: lib/features/partner/screens/partner_benefit_detail_screen.dart
//
// 사용 예시 (main.dart):
// import 'package:seolleyeon/features/partner/screens/partner_benefit_detail_screen.dart';
// ...
// home: const PartnerBenefitDetailScreen(),
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF0426E);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF181113);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray500 = Color(0xFF6B7280);
}

// =============================================================================
// 메인 화면
// =============================================================================
class PartnerBenefitDetailScreen extends StatelessWidget {
  const PartnerBenefitDetailScreen({super.key});

  // 더미 데이터
  static const String _heroImageUrl =
      'https://lh3.googleusercontent.com/aida-public/AB6AXuCzSDRLRdJTFlfUH6zc_IOtin_rDAcujgiUHbFUUn5iE0VnWnxr2ubkRpCwv7HK39qFJe275yfzg1I562tbCnQHJvz4oTZeGXyHtdbSUu9IZNxxI9CWhWD0GIbnGuM7WrBZhtxYve31lHL_RgLz8hsCswkyAFpmckzV2eImlqWuiuQU4Yc6o1Cy8491BBhcrhQmcoK_mBMuAwujT-Y_j8uvcgTEHaMn5FHDMIztHqPdHyktLhliS4IGZfekLp6WED-9qqR2EsKckPg';

  static const String _mapImageUrl =
      'https://lh3.googleusercontent.com/aida-public/AB6AXuB7nadXD6WgBM1DVttYj3wY3GsINC-htEZfytzobJwJfsEqVov5-UaxepyVaKgzPvOxGkhl6KhWOBVQY0_lfgttyKEnZZ65d7ts9ulKFFd1rlsxFZYY0z5PUhG37LYePRokUkjpX_NDmsK1pXuXoTTzELHyV-JtGMpK4r9gGg3Hhx4xSbjhJq9U_VrezG9tk85mwAVIlDLh5tU_uxyEdffYNlac1RYwjnfh_FD8nEgDabX6zwp-OqwBsmd67pSxIAsTkp-T_LuKpzE';

  void _onVerifyStamp() {
    HapticFeedback.mediumImpact();
    // TODO: 안전 도장 확인
  }

  void _onShare() {
    HapticFeedback.lightImpact();
    // TODO: 공유하기
  }

  void _onNavigate() {
    HapticFeedback.selectionClick();
    // TODO: 길찾기 앱 열기
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.surfaceLight,
      child: Stack(
        children: [
          // 스크롤 영역
          CustomScrollView(
            physics: const BouncingScrollPhysics(),
            slivers: [
              // 히어로 이미지
              SliverToBoxAdapter(
                child: _HeroSection(
                  imageUrl: _heroImageUrl,
                  onBack: () => Navigator.of(context).pop(),
                  onShare: _onShare,
                ),
              ),
              // 혜택 상세
              const SliverToBoxAdapter(child: _BenefitDetails()),
              // 태그 칩
              const SliverToBoxAdapter(child: _TagChips()),
              // 구분선
              const SliverToBoxAdapter(child: _Divider()),
              // 위치 섹션
              SliverToBoxAdapter(
                child: _LocationSection(
                  mapImageUrl: _mapImageUrl,
                  onNavigate: _onNavigate,
                ),
              ),
              // 하단 여백
              const SliverToBoxAdapter(child: SizedBox(height: 100)),
            ],
          ),
          // 하단 CTA
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: _BottomCTA(onPressed: _onVerifyStamp),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 히어로 섹션
// =============================================================================
class _HeroSection extends StatelessWidget {
  final String imageUrl;
  final VoidCallback onBack;
  final VoidCallback onShare;

  const _HeroSection({
    required this.imageUrl,
    required this.onBack,
    required this.onShare,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        // 이미지
        AspectRatio(
          aspectRatio: 4 / 5,
          child: Container(
            margin: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(
                  color: CupertinoColors.black.withValues(alpha: 0.1),
                  blurRadius: 20,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(16),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Image.network(
                    imageUrl,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => Container(
                      color: _AppColors.gray100,
                      child: const Icon(
                        CupertinoIcons.photo,
                        size: 64,
                        color: _AppColors.gray400,
                      ),
                    ),
                  ),
                  // 그라데이션 오버레이
                  Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          const Color(0x00000000),
                          const Color(0x00000000),
                          CupertinoColors.black.withValues(alpha: 0.6),
                        ],
                        stops: const [0.0, 0.5, 1.0],
                      ),
                    ),
                  ),
                  // Partner Benefit 배지
                  Positioned(
                    top: 16,
                    left: 16,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 8,
                      ),
                      decoration: BoxDecoration(
                        color: CupertinoColors.white.withValues(alpha: 0.9),
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: const Text(
                        'PARTNER BENEFIT',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 1.2,
                          color: _AppColors.primary,
                        ),
                      ),
                    ),
                  ),
                  // 하단 텍스트
                  Positioned(
                    left: 24,
                    right: 24,
                    bottom: 24,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'OO 매장에서 설레연 이용자들을 기다립니다!',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 26,
                            fontWeight: FontWeight.w700,
                            height: 1.2,
                            color: CupertinoColors.white,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          '낭만적인 분위기의 이탈리안 비스트로',
                          style: TextStyle(
                            fontFamily: 'Pretendard',
                            fontSize: 14,
                            fontWeight: FontWeight.w500,
                            color: CupertinoColors.white.withValues(alpha: 0.9),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        // 상단 네비게이션
        Positioned(
          top: 0,
          left: 0,
          right: 0,
          child: SafeArea(
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: onBack,
                    child: Container(
                      width: 48,
                      height: 48,
                      decoration: BoxDecoration(
                        color: _AppColors.surfaceLight.withValues(alpha: 0.8),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(
                        CupertinoIcons.back,
                        color: _AppColors.textMain,
                        size: 22,
                      ),
                    ),
                  ),
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: onShare,
                    child: Container(
                      width: 48,
                      height: 48,
                      decoration: BoxDecoration(
                        color: _AppColors.surfaceLight.withValues(alpha: 0.8),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(
                        CupertinoIcons.share,
                        color: _AppColors.textMain,
                        size: 22,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 혜택 상세
// =============================================================================
class _BenefitDetails extends StatelessWidget {
  const _BenefitDetails();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Special Offer 배지
          Row(
            children: [
              const Icon(
                CupertinoIcons.checkmark_seal_fill,
                color: _AppColors.primary,
                size: 20,
              ),
              const SizedBox(width: 8),
              const Text(
                'SPECIAL OFFER',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1,
                  color: _AppColors.primary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          // 타이틀
          RichText(
            text: const TextSpan(
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 24,
                fontWeight: FontWeight.w700,
                height: 1.3,
                color: _AppColors.textMain,
              ),
              children: [
                TextSpan(text: '안전 도장 보여주면\n'),
                TextSpan(
                  text: 'OO 메뉴 무료',
                  style: TextStyle(color: _AppColors.primary),
                ),
                TextSpan(text: ' 제공'),
              ],
            ),
          ),
          const SizedBox(height: 12),
          // 설명 텍스트
          const Text(
            '매장에 방문하셔서 설레연 앱 내의 안전 도장을 직원에게 보여주세요. 테이블 당 1회 제공됩니다. 주문 시 미리 말씀해주시면 더욱 원활한 서비스가 가능합니다.',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 15,
              height: 1.6,
              color: _AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 태그 칩
// =============================================================================
class _TagChips extends StatelessWidget {
  const _TagChips();

  @override
  Widget build(BuildContext context) {
    final tags = [
      (CupertinoIcons.person_2, '도보 5분'),
      (CupertinoIcons.cart, '이탈리안'),
      (CupertinoIcons.drop, '와인'),
    ];

    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 24, 24, 0),
      child: Wrap(
        spacing: 12,
        runSpacing: 12,
        children: tags.map((tag) {
          return Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: _AppColors.backgroundLight,
              borderRadius: BorderRadius.circular(20),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(tag.$1, size: 18, color: _AppColors.gray500),
                const SizedBox(width: 8),
                Text(
                  tag.$2,
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: _AppColors.textMain,
                  ),
                ),
              ],
            ),
          );
        }).toList(),
      ),
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
      margin: const EdgeInsets.symmetric(vertical: 24),
      height: 1,
      color: _AppColors.gray100,
    );
  }
}

// =============================================================================
// 위치 섹션
// =============================================================================
class _LocationSection extends StatelessWidget {
  final String mapImageUrl;
  final VoidCallback onNavigate;

  const _LocationSection({required this.mapImageUrl, required this.onNavigate});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 헤더
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                '매장 위치',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: _AppColors.textMain,
                ),
              ),
              Text(
                '350m away',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 14,
                  color: _AppColors.gray500,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          // 지도
          Container(
            height: 180,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(
                  color: CupertinoColors.black.withValues(alpha: 0.05),
                  blurRadius: 8,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(16),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Image.network(
                    mapImageUrl,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) =>
                        Container(color: _AppColors.gray100),
                  ),
                  // 지도 핀
                  Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: _AppColors.primary,
                            shape: BoxShape.circle,
                            boxShadow: [
                              BoxShadow(
                                color: _AppColors.primary.withValues(
                                  alpha: 0.4,
                                ),
                                blurRadius: 12,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          child: const Icon(
                            CupertinoIcons.building_2_fill,
                            color: CupertinoColors.white,
                            size: 22,
                          ),
                        ),
                        Container(
                          width: 12,
                          height: 12,
                          margin: const EdgeInsets.only(top: -6),
                          decoration: const BoxDecoration(
                            color: _AppColors.primary,
                            shape: BoxShape.rectangle,
                          ),
                          transform: Matrix4.rotationZ(0.785),
                        ),
                      ],
                    ),
                  ),
                  // 길찾기 버튼
                  Positioned(
                    right: 12,
                    bottom: 12,
                    child: CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: onNavigate,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 16,
                          vertical: 10,
                        ),
                        decoration: BoxDecoration(
                          color: _AppColors.surfaceLight,
                          borderRadius: BorderRadius.circular(20),
                          boxShadow: [
                            BoxShadow(
                              color: CupertinoColors.black.withValues(
                                alpha: 0.1,
                              ),
                              blurRadius: 8,
                              offset: const Offset(0, 2),
                            ),
                          ],
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(
                              CupertinoIcons.location_fill,
                              size: 16,
                              color: _AppColors.textMain,
                            ),
                            const SizedBox(width: 6),
                            const Text(
                              '길찾기',
                              style: TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 14,
                                fontWeight: FontWeight.w700,
                                color: _AppColors.textMain,
                              ),
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
          const SizedBox(height: 16),
          // 주소
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(
                CupertinoIcons.location,
                size: 20,
                color: _AppColors.gray400,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      '서울특별시 강남구 테헤란로 123',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 15,
                        fontWeight: FontWeight.w500,
                        color: _AppColors.textMain,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'OO빌딩 1층 이탈리안 비스트로',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 13,
                        color: _AppColors.gray500,
                      ),
                    ),
                  ],
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
// 하단 CTA
// =============================================================================
class _BottomCTA extends StatelessWidget {
  final VoidCallback onPressed;

  const _BottomCTA({required this.onPressed});

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return Container(
      padding: EdgeInsets.fromLTRB(16, 16, 16, bottomPadding + 16),
      decoration: BoxDecoration(
        color: CupertinoColors.white.withValues(alpha: 0.9),
        border: const Border(top: BorderSide(color: _AppColors.gray100)),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onPressed,
        child: Container(
          width: double.infinity,
          height: 56,
          decoration: BoxDecoration(
            color: _AppColors.primary,
            borderRadius: BorderRadius.circular(28),
            boxShadow: [
              BoxShadow(
                color: _AppColors.primary.withValues(alpha: 0.3),
                blurRadius: 16,
                offset: const Offset(0, 6),
              ),
            ],
          ),
          child: const Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                CupertinoIcons.checkmark_shield_fill,
                color: CupertinoColors.white,
                size: 22,
              ),
              SizedBox(width: 8),
              Text(
                '안전 도장 확인하기',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                  color: CupertinoColors.white,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
