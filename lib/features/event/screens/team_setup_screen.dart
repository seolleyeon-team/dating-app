// =============================================================================
// 팀 구성(3명) 화면
// 경로: lib/features/event/screens/team_setup_screen.dart
//
// HTML to Flutter 변환 구현
// - Cupertino 스타일 적용
// - 3인 팀 슬롯 UI
// - 친구 초대 및 링크 복사 버튼
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Colors, Icons;
import 'package:flutter/services.dart';
import '../../../router/route_names.dart';

// =============================================================================
// 색상 정의
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF0426E); // #f0426e
  static const Color backgroundLight = Color(0xFFF8F6F6); // #f8f6f6
  static const Color surfaceLight = CupertinoColors.white;
  static const Color textMain = Color(0xFF181113); // #181113
  static const Color textSub = Color(0xFF9E9E9E);
  static const Color gray200 = Color(0xFFEEEEEE);
  static const Color gray400 = Color(0xFFBDBDBD);
  static const Color kakaoYellow = Color(0xFFFEE500);
}

// =============================================================================
// 메인 화면
// =============================================================================
class TeamSetupScreen extends StatelessWidget {
  const TeamSetupScreen({super.key});

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
                      horizontal: 24,
                      vertical: 16,
                    ),
                    child: Column(
                      children: const [
                        // 타이틀 그룹
                        _HeadlineGroup(),
                        SizedBox(height: 32),

                        // 슬롯 컨테이너 (그리드)
                        _TeamSlots(),
                        SizedBox(height: 32),

                        // 도움말 텍스트
                        _HelperText(),
                        SizedBox(height: 32),

                        // 초대 버튼 그룹
                        _InviteButtons(),
                        SizedBox(height: 100), // 하단 여백
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),

          // 하단 고정 CTA
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: const _BottomCTA(isDisabled: true), // 초기 상태는 비활성화
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
                CupertinoIcons.back,
                color: _AppColors.textMain,
                size: 24,
              ),
            ),
          ),
          const Text(
            '3명 팀으로 참여해요',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 18,
              fontWeight: FontWeight.w700,
              color: _AppColors.textMain,
            ),
          ),
          const SizedBox(width: 40), // 센터링을 위한 여백
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
      children: const [
        Text(
          '팀 구성하기',
          style: TextStyle(
            fontSize: 24,
            fontWeight: FontWeight.w700,
            color: _AppColors.textMain,
          ),
        ),
        SizedBox(height: 8),
        Text(
          '친구 2명을 초대해서 팀을 완성해보세요.',
          style: TextStyle(
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
// 팀 슬롯 (그리드)
// =============================================================================
class _TeamSlots extends StatelessWidget {
  const _TeamSlots();

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: const [
        Expanded(
          child: _UserSlot(name: '지수', mbti: 'ESTJ', isMe: true),
        ),
        SizedBox(width: 12),
        Expanded(child: _InviteSlot()),
        SizedBox(width: 12),
        Expanded(child: _InviteSlot()),
      ],
    );
  }
}

// =============================================================================
// 유저 슬롯
// =============================================================================
class _UserSlot extends StatelessWidget {
  final String name;
  final String mbti;
  final bool isMe;

  const _UserSlot({required this.name, required this.mbti, this.isMe = false});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(24), // 2xl
        border: Border.all(color: Colors.white.withValues(alpha: 0.5)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.08),
            blurRadius: 40,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: AspectRatio(
        aspectRatio: 3 / 4,
        child: Stack(
          children: [
            Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  // 아바타
                  Container(
                    width: 64,
                    height: 64,
                    margin: const EdgeInsets.only(bottom: 12),
                    decoration: BoxDecoration(
                      color: _AppColors.gray200,
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: _AppColors.primary.withValues(alpha: 0.2),
                        width: 2,
                      ),
                    ),
                    clipBehavior: Clip.antiAlias,
                    child: const Icon(
                      CupertinoIcons.person_fill,
                      color: Colors.white,
                      size: 40,
                    ),
                  ),
                  // 이름
                  Text(
                    name,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.textMain,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  // MBTI
                  Text(
                    mbti,
                    style: const TextStyle(
                      fontSize: 10,
                      color: _AppColors.gray400,
                    ),
                  ),
                ],
              ),
            ),
            // ME 뱃지
            if (isMe)
              Positioned(
                top: 8,
                right: 8,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 2,
                  ),
                  decoration: BoxDecoration(
                    color: _AppColors.primary,
                    borderRadius: BorderRadius.circular(10),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.1),
                        blurRadius: 2,
                      ),
                    ],
                  ),
                  child: const Text(
                    'ME',
                    style: TextStyle(
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
    );
  }
}

// =============================================================================
// 초대 슬롯 (빈 슬롯)
// =============================================================================
class _InviteSlot extends StatelessWidget {
  const _InviteSlot();

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () {},
      child: Container(
        decoration: BoxDecoration(
          color: _AppColors.primary.withValues(alpha: 0.05),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(
            color: _AppColors.primary.withValues(alpha: 0.3),
            width: 2,
            style: BorderStyle
                .solid, // dashed effect is hard in native flutter without custom painter, using solid for now or could implement dashed
          ),
        ),
        child: AspectRatio(
          aspectRatio: 3 / 4,
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Container(
                  width: 48,
                  height: 48,
                  margin: const EdgeInsets.only(bottom: 12),
                  decoration: const BoxDecoration(
                    color: _AppColors.surfaceLight,
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black12,
                        blurRadius: 4,
                        offset: Offset(0, 2),
                      ),
                    ],
                  ),
                  child: const Icon(
                    Icons.add_rounded,
                    color: _AppColors.primary,
                    size: 24,
                  ),
                ),
                const Text(
                  '친구 초대',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.primary,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 도움말 텍스트
// =============================================================================
class _HelperText extends StatelessWidget {
  const _HelperText();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: const [
          Icon(Icons.info_outline_rounded, color: _AppColors.gray400, size: 16),
          SizedBox(width: 8),
          Text(
            '3명이 모여야 매칭을 시작할 수 있어요',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: _AppColors.textSub,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 초대 버튼 그룹
// =============================================================================
class _InviteButtons extends StatelessWidget {
  const _InviteButtons();

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        // 카카오로 초대
        Expanded(
          child: CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: () {},
            child: Container(
              height: 48,
              decoration: BoxDecoration(
                color: _AppColors.surfaceLight,
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: _AppColors.gray200),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.03),
                    blurRadius: 4,
                  ),
                ],
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: const [
                  Icon(
                    CupertinoIcons.chat_bubble_fill,
                    color: _AppColors.kakaoYellow,
                    size: 20,
                  ),
                  SizedBox(width: 8),
                  Text(
                    '카카오로 초대',
                    style: TextStyle(
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
        const SizedBox(width: 12),
        // 링크 복사
        Expanded(
          child: CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: () {},
            child: Container(
              height: 48,
              decoration: BoxDecoration(
                color: _AppColors.surfaceLight,
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: _AppColors.gray200),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.03),
                    blurRadius: 4,
                  ),
                ],
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: const [
                  Icon(
                    CupertinoIcons.link,
                    color: _AppColors.gray400,
                    size: 20,
                  ),
                  SizedBox(width: 8),
                  Text(
                    '링크 복사',
                    style: TextStyle(
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
    );
  }
}

// =============================================================================
// 하단 CTA 버튼
// =============================================================================
class _BottomCTA extends StatelessWidget {
  final bool isDisabled;

  const _BottomCTA({this.isDisabled = false});

  void _onPressed(BuildContext context) {
    if (!isDisabled) {
      HapticFeedback.mediumImpact();
      Navigator.of(context).pushNamed(RouteNames.seasonMeetingRoulette);
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => _onPressed(context),
      child: Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            _AppColors.backgroundLight.withValues(alpha: 0),
            _AppColors.backgroundLight,
          ],
          stops: const [0.0, 0.4],
        ),
      ),
      padding: EdgeInsets.fromLTRB(
        24,
        24,
        24,
        MediaQuery.of(context).padding.bottom + 24,
      ),
      child: Container(
        height: 56,
        decoration: BoxDecoration(
          color: isDisabled ? _AppColors.gray200 : _AppColors.primary,
          borderRadius: BorderRadius.circular(28),
          boxShadow: isDisabled
              ? null
              : [
                  BoxShadow(
                    color: _AppColors.primary.withValues(alpha: 0.3),
                    blurRadius: 16,
                    offset: const Offset(0, 6),
                  ),
                ],
        ),
        alignment: Alignment.center,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              CupertinoIcons.game_controller_solid, // casino icon replacement
              color: isDisabled ? _AppColors.gray400 : Colors.white,
              size: 24,
            ),
            const SizedBox(width: 8),
            Text(
              '슬롯머신 돌리기 (1회 무료)',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: isDisabled ? _AppColors.gray400 : Colors.white,
              ),
            ),
          ],
        ),
      ),
    ));
  }
}
