// =============================================================================
// 팀 구성하기 화면 (친구 초대)
// 경로: lib/features/meeting/screens/team_setup_screen.dart
//
// 사용 예시 (main.dart):
// import 'package:seolleyeon/features/meeting/screens/team_setup_screen.dart';
// ...
// home: const TeamSetupScreen(),
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';

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
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color kakaoYellow = Color(0xFFFEE500);
}

// =============================================================================
// 팀원 모델
// =============================================================================
class _TeamMember {
  final String name;
  final String mbti;
  final String? imageUrl;
  final bool isMe;

  const _TeamMember({
    required this.name,
    required this.mbti,
    this.imageUrl,
    this.isMe = false,
  });
}

// =============================================================================
// 메인 화면
// =============================================================================
class TeamSetupScreen extends StatefulWidget {
  const TeamSetupScreen({super.key});

  @override
  State<TeamSetupScreen> createState() => _TeamSetupScreenState();
}

class _TeamSetupScreenState extends State<TeamSetupScreen> {
  // 팀 슬롯 (null = 빈 슬롯)
  final List<_TeamMember?> _teamSlots = [
    const _TeamMember(
      name: '지수',
      mbti: 'ESTJ',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuB1-y8FarVb1IJF9O_lHt6mDAk8MSK5DVBLV42LIBrNO3re9BfuwSFyUGSl5T1NIXay1QurKJ4kJV320TaAVrKF6KIx03mGzlqEnaVzMRu_RjoGae-qHb4VMN2xWM_dGRRdMLg2tBVm5xEnBqcKbgFiXJxN8qh0C7v3kTZ5L0BZwCp5g8WPj1Wyzcn05kxHbQcCJudv4l3gUom2OZ05TVQKKRSpTj7ewX3BGBKINbUKZ_Q4EQOuFiYzDNk7kcqt4TgRfEVybDJ-qrk',
      isMe: true,
    ),
    null, // 빈 슬롯
    null, // 빈 슬롯
  ];

  bool get _isTeamComplete => _teamSlots.every((member) => member != null);

  void _onInviteKakao() {
    HapticFeedback.lightImpact();
    // TODO: 카카오톡 초대
  }

  void _onShare() {
    HapticFeedback.lightImpact();
    SharePlus.instance.share(
      ShareParams(
        text: '설레연에서 함께 3:3 미팅해요! 🎉',
      ),
    );
  }

  void _onStartMatching() {
    if (!_isTeamComplete) return;
    HapticFeedback.mediumImpact();
    // TODO: 슬롯머신 시작
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          // 메인 콘텐츠
          SafeArea(
            bottom: false,
            child: Column(
              children: [
                // 헤더
                _Header(onBackPressed: () => Navigator.of(context).pop()),
                // 스크롤 영역
                Expanded(
                  child: SingleChildScrollView(
                    physics: const BouncingScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(24, 16, 24, 120),
                    child: Column(
                      children: [
                        // 타이틀
                        const _TitleSection(),
                        const SizedBox(height: 32),
                        // 팀 슬롯
                        _TeamSlots(
                          slots: _teamSlots,
                          onSlotTap: (index) {
                            // TODO: 초대 처리
                          },
                        ),
                        const SizedBox(height: 24),
                        // 안내 메시지
                        const _InfoChip(),
                        const SizedBox(height: 32),
                        // 초대 버튼
                        _InviteButtons(
                          onKakao: _onInviteKakao,
                          onShare: _onShare,
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
          // 하단 CTA
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: _BottomCTA(
              isEnabled: _isTeamComplete,
              onPressed: _onStartMatching,
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
  final VoidCallback onBackPressed;

  const _Header({required this.onBackPressed});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
      child: Row(
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(40, 40),
            onPressed: onBackPressed,
            child: const Icon(
              CupertinoIcons.back,
              color: _AppColors.textMain,
              size: 24,
            ),
          ),
          const Expanded(
            child: Text(
              '3명 팀으로 참여해요',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 18,
                fontWeight: FontWeight.w700,
                letterSpacing: -0.3,
                color: _AppColors.textMain,
              ),
            ),
          ),
          const SizedBox(width: 40),
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
    return const Column(
      children: [
        Text(
          '팀 구성하기',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 24,
            fontWeight: FontWeight.w700,
            color: _AppColors.textMain,
          ),
        ),
        SizedBox(height: 8),
        Text(
          '친구 2명을 초대해서 팀을 완성해보세요.',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 14,
            color: _AppColors.textSecondary,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 팀 슬롯
// =============================================================================
class _TeamSlots extends StatelessWidget {
  final List<_TeamMember?> slots;
  final void Function(int index) onSlotTap;

  const _TeamSlots({required this.slots, required this.onSlotTap});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: slots.asMap().entries.map((entry) {
        final index = entry.key;
        final member = entry.value;

        return Expanded(
          child: Padding(
            padding: EdgeInsets.only(
              left: index > 0 ? 6 : 0,
              right: index < slots.length - 1 ? 6 : 0,
            ),
            child: member != null
                ? _FilledSlot(member: member)
                : _EmptySlot(onTap: () => onSlotTap(index)),
          ),
        );
      }).toList(),
    );
  }
}

class _FilledSlot extends StatelessWidget {
  final _TeamMember member;

  const _FilledSlot({required this.member});

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 3 / 4,
      child: Container(
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: CupertinoColors.black.withValues(alpha: 0.08),
              blurRadius: 20,
              offset: const Offset(0, 5),
            ),
          ],
          border: Border.all(
            color: CupertinoColors.white.withValues(alpha: 0.5),
          ),
        ),
        child: Stack(
          children: [
            // 콘텐츠
            Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // 아바타
                Container(
                  width: 64,
                  height: 64,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: _AppColors.primary.withValues(alpha: 0.2),
                      width: 2,
                    ),
                  ),
                  child: ClipOval(
                    child: member.imageUrl != null
                        ? Image.network(
                            member.imageUrl!,
                            fit: BoxFit.cover,
                            errorBuilder: (_, __, ___) => Container(
                              color: _AppColors.gray200,
                              child: const Icon(
                                CupertinoIcons.person_fill,
                                color: _AppColors.gray400,
                                size: 32,
                              ),
                            ),
                          )
                        : Container(
                            color: _AppColors.gray200,
                            child: const Icon(
                              CupertinoIcons.person_fill,
                              color: _AppColors.gray400,
                              size: 32,
                            ),
                          ),
                  ),
                ),
                const SizedBox(height: 12),
                // 이름
                Text(
                  member.name,
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.textMain,
                  ),
                ),
                const SizedBox(height: 2),
                // MBTI
                Text(
                  member.mbti,
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 10,
                    color: _AppColors.gray400,
                  ),
                ),
              ],
            ),
            // ME 배지
            if (member.isMe)
              Positioned(
                top: 8,
                right: 8,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 3,
                  ),
                  decoration: BoxDecoration(
                    color: _AppColors.primary,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Text(
                    'ME',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      color: CupertinoColors.white,
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

class _EmptySlot extends StatelessWidget {
  final VoidCallback onTap;

  const _EmptySlot({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: AspectRatio(
        aspectRatio: 3 / 4,
        child: Container(
          decoration: BoxDecoration(
            color: _AppColors.primary.withValues(alpha: 0.05),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: _AppColors.primary.withValues(alpha: 0.3),
              width: 2,
              strokeAlign: BorderSide.strokeAlignInside,
            ),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // 아이콘
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: _AppColors.surfaceLight,
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: CupertinoColors.black.withValues(alpha: 0.05),
                      blurRadius: 4,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: const Icon(
                  CupertinoIcons.add,
                  color: _AppColors.primary,
                  size: 24,
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                '친구 초대',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: _AppColors.primary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 안내 칩
// =============================================================================
class _InfoChip extends StatelessWidget {
  const _InfoChip();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: _AppColors.gray100,
        borderRadius: BorderRadius.circular(20),
      ),
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(CupertinoIcons.info, size: 14, color: _AppColors.gray400),
          SizedBox(width: 8),
          Text(
            '3명이 모여야 매칭을 시작할 수 있어요',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: _AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 초대 버튼
// =============================================================================
class _InviteButtons extends StatelessWidget {
  final VoidCallback onKakao;
  final VoidCallback onShare;

  const _InviteButtons({required this.onKakao, required this.onShare});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        // 카카오 초대
        Expanded(
          child: CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: onKakao,
            child: Container(
              height: 48,
              decoration: BoxDecoration(
                color: _AppColors.surfaceLight,
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: _AppColors.gray100),
                boxShadow: [
                  BoxShadow(
                    color: CupertinoColors.black.withValues(alpha: 0.03),
                    blurRadius: 4,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    CupertinoIcons.chat_bubble_fill,
                    size: 18,
                    color: _AppColors.kakaoYellow,
                  ),
                  SizedBox(width: 8),
                  Text(
                    '카카오로 초대',
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
        const SizedBox(width: 12),
        // 공유하기
        Expanded(
          child: CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: onShare,
            child: Container(
              height: 48,
              decoration: BoxDecoration(
                color: _AppColors.surfaceLight,
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: _AppColors.gray100),
                boxShadow: [
                  BoxShadow(
                    color: CupertinoColors.black.withValues(alpha: 0.03),
                    blurRadius: 4,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    CupertinoIcons.square_arrow_up,
                    size: 18,
                    color: _AppColors.gray400,
                  ),
                  SizedBox(width: 8),
                  Text(
                    '공유하기',
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
    );
  }
}

// =============================================================================
// 하단 CTA
// =============================================================================
class _BottomCTA extends StatelessWidget {
  final bool isEnabled;
  final VoidCallback onPressed;

  const _BottomCTA({required this.isEnabled, required this.onPressed});

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return Container(
      padding: EdgeInsets.fromLTRB(24, 24, 24, bottomPadding + 24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            _AppColors.backgroundLight.withValues(alpha: 0),
            _AppColors.backgroundLight,
            _AppColors.backgroundLight,
          ],
          stops: const [0.0, 0.3, 1.0],
        ),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: isEnabled ? onPressed : null,
        child: Container(
          width: double.infinity,
          height: 56,
          decoration: BoxDecoration(
            color: isEnabled ? _AppColors.primary : _AppColors.gray200,
            borderRadius: BorderRadius.circular(28),
            boxShadow: isEnabled
                ? [
                    BoxShadow(
                      color: _AppColors.primary.withValues(alpha: 0.3),
                      blurRadius: 16,
                      offset: const Offset(0, 6),
                    ),
                  ]
                : null,
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                CupertinoIcons.game_controller,
                size: 22,
                color: isEnabled ? CupertinoColors.white : _AppColors.gray400,
              ),
              const SizedBox(width: 8),
              Text(
                '슬롯머신 돌리기 (1회 무료)',
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: isEnabled ? CupertinoColors.white : _AppColors.gray400,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
