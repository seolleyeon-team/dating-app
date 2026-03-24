// =============================================================================
// 미팅 신청 완료 화면 V3 (3대3 랜덤 미팅 성공)
// 경로: lib/features/event/screens/random_meeting_screen.dart
//
// HTML to Flutter 변환 구현
// - Cupertino 스타일 적용
// - V3 디자인: 글로잉 스피어(Glowing Sphere) 애니메이션 효과
// - 카드형 정보 리스트 (인원, 장소, 시간)
// - 하단 고정 버튼 (확인, 신청 취소)
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Colors, Icons;
import 'dart:ui'; // for ImageFilter

// =============================================================================
// 색상 정의
// =============================================================================
const String _kFontFamily = 'Noto Sans KR';

class _AppColors {
  static const Color primary = Color(0xFFEE2B7C); // #ee2b7c
  static const Color backgroundLight = Color(0xFFF8F6F7); // #f8f6f7
  static const Color surfaceLight = CupertinoColors.white;
  static const Color textMain = Color(0xFF181114); // #181114
  static const Color textSub = Color(0xFF896172); // #896172
  static const Color borderLight = Color(0xFFF4F0F2);
  static const Color buttonGray = Color(0xFFF4F0F2);
}

// =============================================================================
// 메인 화면
// =============================================================================
class RandomMeetingScreen extends StatelessWidget {
  const RandomMeetingScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: SafeArea(
        child: Column(
          children: [
            // 헤더
            _Header(onBack: () => Navigator.of(context).pop()),

            // 메인 컨텐츠 영역
            Expanded(
              child: SingleChildScrollView(
                physics: const BouncingScrollPhysics(),
                padding: const EdgeInsets.symmetric(
                  horizontal: 24,
                  vertical: 16,
                ),
                child: Column(
                  children: const [
                    // 상태 비주얼(글로잉 스피어) 및 텍스트
                    _StatusVisualSection(),
                    SizedBox(height: 40),

                    // 정보 카드 리스트
                    _InfoCardList(),
                    SizedBox(height: 24),
                  ],
                ),
              ),
            ),

            // 하단 액션 버튼
            const _ActionFooter(),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final VoidCallback onBack;

  const _Header({required this.onBack});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(40, 40),
            onPressed: onBack,
            child: Container(
              width: 48,
              height: 48,
              alignment: Alignment.center,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                // active color handled by button
              ),
              child: const Icon(
                CupertinoIcons.back,
                color: _AppColors.textMain,
                size: 24,
              ),
            ),
          ),
          const Text(
            '설레연',
            style: TextStyle(
              fontFamily: _kFontFamily,
              fontSize: 18,
              fontWeight: FontWeight.w700,
              color: _AppColors.textMain,
            ),
          ),
          // Right spacer to center title
          const SizedBox(width: 48),
        ],
      ),
    );
  }
}

// =============================================================================
// 상태 비주얼 섹션 (글로잉 스피어)
// =============================================================================
class _StatusVisualSection extends StatelessWidget {
  const _StatusVisualSection();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // 글로잉 스피어
        SizedBox(
          width: 200, // 컨테이너 크기 넉넉하게
          height: 180,
          child: Stack(
            alignment: Alignment.center,
            children: [
              // 글로우 효과 (Blur)
              Container(
                width: 120,
                height: 120,
                decoration: BoxDecoration(
                  color: _AppColors.primary.withValues(alpha: 0.2),
                  shape: BoxShape.circle,
                ),
                child: BackdropFilter(
                  filter: ImageFilter.blur(sigmaX: 30, sigmaY: 30),
                  child: Container(color: Colors.transparent),
                ),
              ),
              // 중앙 스피어 이미지 (URL 사용 또는 로컬 자산)
              Container(
                width: 128,
                height: 128,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.pink.shade100, // placeholder color
                  image: const DecorationImage(
                    image: NetworkImage(
                      'https://lh3.googleusercontent.com/aida-public/AB6AXuC-2Uxl5jygCD4mqegLAoRQ9jqICQ7WIDo5napJ8eitgBjrS4BielyCe0UqgDNWRnhlP1JTpKXP79oO2j36_ZvrUS6XeCZdjA1XYM4oxhcdRUSLiURr8P-mIJpWK3My-qQor56CTMZU9Nki1_SXSoNkifVavKLvF1HzV3z5yK8PvhyPVmg_esUJ_ips6oBYkSV8sWhvgUEG1TZrpQJDH37LOAJ9d0UIHJDwfahOc75zb-hZTUEn2-UH_-2prHdfBo4Ua5oqTXLcjrHT',
                    ),
                    fit: BoxFit.cover,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: _AppColors.primary.withValues(alpha: 0.3),
                      blurRadius: 30,
                      spreadRadius: 0,
                    ),
                  ],
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.2),
                    width: 4,
                  ),
                ),
              ),
            ],
          ),
        ),

        // 텍스트
        const Text(
          '매칭 진행 중',
          style: TextStyle(
            fontFamily: _kFontFamily,
            fontSize: 24,
            fontWeight: FontWeight.w700,
            color: _AppColors.textMain,
            letterSpacing: -0.5,
          ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 12),
        const Text(
          '지금 3:3 미팅 상대를 찾고 있어요.\n매칭이 완료되면 알림을 보내드릴게요.',
          style: TextStyle(
            fontFamily: _kFontFamily,
            fontSize: 14,
            fontWeight: FontWeight.w500,
            color: _AppColors.textSub,
            height: 1.5,
          ),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}

// =============================================================================
// 정보 카드 리스트
// =============================================================================
class _InfoCardList extends StatelessWidget {
  const _InfoCardList();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: _AppColors.borderLight),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.02),
            blurRadius: 10,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        children: const [
          _InfoItem(
            icon: Icons.group_rounded,
            label: '인원',
            value: '3:3 (남3, 여3)',
            hasBorder: true,
          ),
          _InfoItem(
            icon: Icons.location_on_rounded,
            label: '장소',
            value: '강남역 인근',
            hasBorder: true,
          ),
          _InfoItem(
            icon: Icons.schedule_rounded,
            label: '시간',
            value: '이번 주 금요일 19:00',
            hasBorder: false,
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 정보 아이템
// =============================================================================
class _InfoItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final bool hasBorder;

  const _InfoItem({
    required this.icon,
    required this.label,
    required this.value,
    required this.hasBorder,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: hasBorder
          ? const BoxDecoration(
              border: Border(bottom: BorderSide(color: _AppColors.borderLight)),
            )
          : null,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: _AppColors.primary.withValues(alpha: 0.1),
                  shape: BoxShape.circle,
                ),
                child: Icon(icon, color: _AppColors.primary, size: 20),
              ),
              const SizedBox(width: 12),
              Text(
                label,
                style: const TextStyle(
                  fontFamily: _kFontFamily,
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                  color: _AppColors.textSub,
                ),
              ),
            ],
          ),
          Text(
            value,
            style: const TextStyle(
              fontFamily: _kFontFamily,
              fontSize: 16,
              fontWeight: FontWeight.w600,
              color: _AppColors.textMain,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 하단 액션 버튼
// =============================================================================
class _ActionFooter extends StatelessWidget {
  const _ActionFooter();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        24,
        0,
        24,
        MediaQuery.of(context).padding.bottom + 24,
      ),
      child: Column(
        children: [
          // 확인 버튼
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: () {},
            child: Container(
              width: double.infinity,
              height: 56,
              decoration: BoxDecoration(
                color: _AppColors.primary,
                borderRadius: BorderRadius.circular(28),
                boxShadow: [
                  BoxShadow(
                    color: _AppColors.primary.withValues(alpha: 0.2),
                    blurRadius: 10,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              alignment: Alignment.center,
              child: const Text(
                '확인',
                style: TextStyle(
                  fontFamily: _kFontFamily,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: Colors.white,
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          // 신청 취소 버튼
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: () {},
            child: Container(
              width: double.infinity,
              height: 56,
              decoration: BoxDecoration(
                color: _AppColors.buttonGray,
                borderRadius: BorderRadius.circular(28),
              ),
              alignment: Alignment.center,
              child: const Text(
                '신청 취소',
                style: TextStyle(
                  fontFamily: _kFontFamily,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: _AppColors.textMain,
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          // 워터마크
          const Text(
            'WF-3V3-03',
            style: TextStyle(
              fontSize: 10,
              fontFamily: 'monospace',
              color: Color(0xFFE0E0E0),
            ),
          ),
        ],
      ),
    );
  }
}
