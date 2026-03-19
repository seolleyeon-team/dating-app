// =============================================================================
// 설레연 3:3 미팅 신청 화면
// 경로: lib/features/meeting/screens/meeting_application_screen.dart
//
// HTML to Flutter 변환 구현
// - Cupertino 스타일 적용
// - 팀원 구성 리스트 (리더 + 초대 슬롯)
// - 미팅 선호 설정 (지역, 시간)
// - 신청하기 CTA
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Colors, Icons, Divider;

// =============================================================================
// 색상 정의
// =============================================================================
const String _kFontFamily = 'Noto Sans KR';

class _AppColors {
  static const Color primary = Color(0xFFE9639B); // #e9639b
  static const Color backgroundLight = Color(0xFFF8F6F7); // #f8f6f7
  static const Color surfaceLight = CupertinoColors.white;
  static const Color textMain = Color(0xFF171114); // #171114
  static const Color textSub = Color(0xFF876472); // #876472
  static const Color primaryLight = Color(0xFFFFF0F5); // light pink equivalent
  static const Color grayBorder = Color(0xFFE0E0E0);
}

// =============================================================================
// 메인 화면
// =============================================================================
class MeetingApplicationScreen extends StatelessWidget {
  const MeetingApplicationScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          SafeArea(
            child: Column(
              children: [
                // 헤더
                _Header(onBack: () => Navigator.of(context).pop()),

                // 메인 컨텐츠 (스크롤 가능)
                Expanded(
                  child: SingleChildScrollView(
                    physics: const BouncingScrollPhysics(),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 20,
                      vertical: 16,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: const [
                        // 타이틀 그룹
                        _HeadlineGroup(),
                        SizedBox(height: 32),

                        // 내 팀 구성 섹션
                        _MyTeamSection(),
                        SizedBox(height: 24),

                        // 미팅 선호 설정 섹션
                        _PreferencesSection(),
                        SizedBox(height: 32),

                        // 워터마크
                        _Watermark(),
                        SizedBox(height: 100), // 하단 여백
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),

          // 하단 고정 CTA
          Positioned(left: 0, right: 0, bottom: 0, child: const _BottomCTA()),
        ],
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
              width: 40,
              height: 40,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.05),
                shape: BoxShape.circle,
              ),
              child: const Icon(
                CupertinoIcons.arrow_left,
                color: _AppColors.textMain,
                size: 24,
              ),
            ),
          ),
          const Text(
            '설레연 3:3 미팅',
            style: TextStyle(
              fontFamily: 'Noto Sans KR',
              fontSize: 18,
              fontWeight: FontWeight.w700,
              color: _AppColors.textMain,
            ),
          ),
          // 더보기 버튼 (더미)
          Container(
            width: 40,
            height: 40,
            alignment: Alignment.center,
            // Visually hidden
            child: const Icon(Icons.more_vert, color: Colors.transparent),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 타이틀 그룹
// =============================================================================
class _HeadlineGroup extends StatelessWidget {
  const _HeadlineGroup();

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: const [
        Text(
          '설레는 새로운 인연,\n여기서 시작해보세요',
          style: TextStyle(
            fontFamily: _kFontFamily,
            fontSize: 24,
            fontWeight: FontWeight.w700,
            color: _AppColors.textMain,
            height: 1.3,
          ),
        ),
        SizedBox(height: 8),
        Text(
          '마음이 맞는 친구들과 함께 팀을 꾸려보세요.',
          style: TextStyle(
            fontFamily: _kFontFamily,
            fontSize: 14,
            fontWeight: FontWeight.w400,
            color: _AppColors.textSub,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 내 팀 구성 섹션
// =============================================================================
class _MyTeamSection extends StatelessWidget {
  const _MyTeamSection();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // 섹션 헤더
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: const [
              Text(
                '내 팀 구성',
                style: TextStyle(
                  fontFamily: _kFontFamily,
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: _AppColors.textMain,
                ),
              ),
              Text(
                '1/3명',
                style: TextStyle(
                  fontFamily: _kFontFamily,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: _AppColors.primary,
                ),
              ),
            ],
          ),
        ),

        // 팀원 카드 리스트
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: _AppColors.surfaceLight,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.04),
                blurRadius: 12,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Column(
            children: [
              // 멤버 1 (나, Leader)
              const _MemberRow(
                isLeader: true,
                name: '나 (김민지)',
                subtitle: '프로필 등록 완료',
                isVerified: true,
                // 실제 구현 시 이미지 URL 사용
              ),

              const Divider(height: 24, color: _AppColors.grayBorder),

              // 멤버 2 (초대하기)
              const _InviteRow(subtitle: '링크를 공유해보세요'),

              const Divider(height: 24, color: _AppColors.grayBorder),

              // 멤버 3 (비어있음)
              const _InviteRow(subtitle: '아직 비어있어요'),
            ],
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 멤버 행 (나)
// =============================================================================
class _MemberRow extends StatelessWidget {
  final bool isLeader;
  final String name;
  final String subtitle;
  final bool isVerified;

  const _MemberRow({
    required this.isLeader,
    required this.name,
    required this.subtitle,
    this.isVerified = false,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        // 아바타
        SizedBox(
          width: 56,
          height: 56,
          child: Stack(
            children: [
              Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.grey[200],
                  border: Border.all(color: _AppColors.primary, width: 2),
                ),
                // 임시 아이콘
                child: const Icon(
                  CupertinoIcons.person_fill,
                  color: Colors.grey,
                ),
              ),
              if (isLeader)
                Positioned(
                  bottom: 0,
                  right: 0,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 6,
                      vertical: 2,
                    ),
                    decoration: BoxDecoration(
                      color: _AppColors.primary,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: Colors.white, width: 2),
                    ),
                    child: const Text(
                      'LEADER',
                      style: TextStyle(
                        fontFamily: _kFontFamily,
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                        color: Colors.white,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(width: 16),
        // 정보
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Flexible(
                    child: Text(
                      name,
                      style: const TextStyle(
                        fontFamily: _kFontFamily,
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: _AppColors.textMain,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (isVerified) ...[
                    const SizedBox(width: 4),
                    const Icon(
                      Icons.verified,
                      color: _AppColors.primary,
                      size: 16,
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 2),
              Text(
                subtitle,
                style: const TextStyle(
                  fontFamily: _kFontFamily,
                  fontSize: 14,
                  color: _AppColors.textSub,
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
// 초대 행
// =============================================================================
class _InviteRow extends StatelessWidget {
  final String subtitle;

  const _InviteRow({required this.subtitle});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {},
      child: Row(
        children: [
          // 초대 아이콘
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFFF5F5F5),
              border: Border.all(
                color: _AppColors.grayBorder,
                style: BorderStyle.solid,
                // Dashed border effect needs custom painter, simplest is lighter solid or dashed image
                // Using solid for simplicity as standard implementation
              ),
            ),
            child: const Icon(
              Icons.person_add_alt_1_rounded,
              color: Colors.grey,
            ),
          ),
          const SizedBox(width: 16),
          // 텍스트
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '팀원 초대하기',
                  style: TextStyle(
                    fontFamily: _kFontFamily,
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: _AppColors.textMain,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: const TextStyle(
                    fontFamily: _kFontFamily,
                    fontSize: 14,
                    color: _AppColors.textSub,
                  ),
                ),
              ],
            ),
          ),
          // 화살표
          Container(
            width: 32,
            height: 32,
            decoration: const BoxDecoration(
              color: Color(0xFFF9FAFB), // gray-50
              shape: BoxShape.circle,
            ),
            child: const Icon(
              CupertinoIcons.chevron_right,
              size: 18,
              color: Colors.grey,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 미팅 선호 설정 섹션
// =============================================================================
class _PreferencesSection extends StatelessWidget {
  const _PreferencesSection();

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 4, vertical: 8),
          child: Text(
            '미팅 선호 설정',
            style: TextStyle(
              fontFamily: _kFontFamily,
              fontSize: 18,
              fontWeight: FontWeight.w700,
              color: _AppColors.textMain,
            ),
          ),
        ),

        // 지역 설정
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: _AppColors.surfaceLight,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.04),
                blurRadius: 12,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: _AppColors.primaryLight,
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(
                      Icons.location_on_rounded,
                      color: _AppColors.primary,
                      size: 20,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: const [
                      Text(
                        '선호 지역',
                        style: TextStyle(
                          fontFamily: _kFontFamily,
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                          color: _AppColors.textSub,
                        ),
                      ),
                      SizedBox(height: 2),
                      Text(
                        '서울 강남/신논현',
                        style: TextStyle(
                          fontFamily: _kFontFamily,
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: _AppColors.textMain,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
              const Icon(
                CupertinoIcons.chevron_down,
                color: Colors.grey,
                size: 20,
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),

        // 시간 설정
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: _AppColors.surfaceLight,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.04),
                blurRadius: 12,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: const [
                  Icon(
                    Icons.schedule_rounded,
                    color: _AppColors.primary,
                    size: 20,
                  ),
                  SizedBox(width: 8),
                  Text(
                    '선호 시간대',
                    style: TextStyle(
                      fontFamily: _kFontFamily,
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.textMain,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: const [
                  _TimeChip(text: '금요일 19시 ~', isSelected: true),
                  _TimeChip(text: '토요일 18시 ~', isSelected: true),
                  _TimeChip(text: '일요일 시간무관', isSelected: false),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 시간대 칩
// =============================================================================
class _TimeChip extends StatelessWidget {
  final String text;
  final bool isSelected;

  const _TimeChip({required this.text, required this.isSelected});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: isSelected ? _AppColors.primaryLight : Colors.white,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: isSelected ? _AppColors.primary : _AppColors.grayBorder,
        ),
        boxShadow: isSelected
            ? [
                BoxShadow(
                  color: _AppColors.primary.withValues(alpha: 0.2),
                  blurRadius: 4,
                  offset: const Offset(0, 2),
                ),
              ]
            : null,
      ),
      child: Text(
        text,
        style: TextStyle(
          fontFamily: _kFontFamily,
          fontSize: 14,
          fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
          color: isSelected ? _AppColors.primary : const Color(0xFF6B7280),
        ),
      ),
    );
  }
}

// =============================================================================
// 워터마크
// =============================================================================
class _Watermark extends StatelessWidget {
  const _Watermark();

  @override
  Widget build(BuildContext context) {
    return const Align(
      alignment: Alignment.centerRight,
      child: Text(
        'WF-3V3-02',
        style: TextStyle(
          fontSize: 10,
          fontFamily: 'monospace',
          color: Colors.grey,
        ),
      ),
    );
  }
}

// =============================================================================
// 하단 CTA 버튼
// =============================================================================
class _BottomCTA extends StatelessWidget {
  const _BottomCTA();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Colors.white.withValues(alpha: 0), Colors.white],
          stops: const [0.0, 0.4],
        ),
      ),
      padding: EdgeInsets.fromLTRB(
        20,
        24,
        20,
        MediaQuery.of(context).padding.bottom + 20,
      ),
      child: Container(
        height: 56,
        decoration: BoxDecoration(
          color: _AppColors.primary,
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: _AppColors.primary.withValues(alpha: 0.4),
              blurRadius: 20,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {},
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: const [
              Text(
                '신청하기',
                style: TextStyle(
                  fontFamily: _kFontFamily,
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: Colors.white,
                ),
              ),
              SizedBox(width: 8),
              Icon(CupertinoIcons.arrow_right, color: Colors.white, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}
