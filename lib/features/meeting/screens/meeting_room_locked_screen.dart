// =============================================================================
// 미팅 방 잠금 화면 (예치금 대기)
// 경로: lib/features/meeting/screens/meeting_room_locked_screen.dart
//
// 사용 예시 (main.dart):
// import 'package:seolleyeon/features/meeting/screens/meeting_room_locked_screen.dart';
// ...
// home: const MeetingRoomLockedScreen(),
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF0426E);
  static const Color indigo500 = Color(0xFF6366F1);
  static const Color indigo50 = Color(0xFFEEF2FF);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF1E293B);
  static const Color textSecondary = Color(0xFF64748B);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color gray300 = Color(0xFFD1D5DB);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray500 = Color(0xFF6B7280);
  static const Color gray700 = Color(0xFF374151);
}

// =============================================================================
// 팀원 데이터
// =============================================================================
class _TeamMember {
  final String imageUrl;
  const _TeamMember(this.imageUrl);
}

// =============================================================================
// 메인 화면
// =============================================================================
class MeetingRoomLockedScreen extends StatelessWidget {
  const MeetingRoomLockedScreen({super.key});

  // 더미 데이터
  static const List<_TeamMember> _teamA = [
    _TeamMember(
      'https://lh3.googleusercontent.com/aida-public/AB6AXuBmUepkm5GzVSOtdIPbrwZP6tT25XXiNJa0BKBU0fCHYrt76cK7V2EsRWGORC5HV5Bs11XEswQpxKiHZEZamcdudrb2S7-ujzip_giPw0XSRaBkqg-cEwSHFeIAdtux_D2D7nKWIT89hbr13Ht4IBymxZT0dM2MkJYHhM8xWDK4UouQnUYcVnpaly2vkFsGLAkyphtKX0P3wkie9UKQ0bUb62N1rLHvuVgA_8bCrc0UXT9wGfj_incK3ntwGTZ7ivAqA9un5ngASkY',
    ),
    _TeamMember(
      'https://lh3.googleusercontent.com/aida-public/AB6AXuBCujWz3Uyv03tV7HuV3xCarPsgWvjZYYE5g2lqn53jqSxwvJ86UoGP_f1g9X5gyRqkJl8SJ24qKUvlXMcPaoy23F06muxxzYbL7s3GzfxF-jwexeGS0t61UbGSslNUBhIXbkdaC3uJPClWVymlsxWweDDzsLAQtPEEmCXhiH2nN7Q7YnsGOGqctGS46HJjw1L-Gmfyh6wyT8CIlvdL_tanxB9XmVHqVxxMwKPkHrGlEdNJAXCZJDbvr_q9ptYq5M4Zr3tVq7jlRng',
    ),
    _TeamMember(
      'https://lh3.googleusercontent.com/aida-public/AB6AXuB-zLFP2o7kGUN56rlKsE5tZsUVrA3aaWS0qukp5mQNFMGbjSCXK87694EkrinBSISClktE6ki1xbsDcOn8MnVVrJb0HPymKz908s_3zLnA1HdzhVn1X-dv3e5Nx8iAb7hZ2ZmXxFFdJTxg78maNd1-52lo5Hy7-Lak-ldi1CYpm8pqtmKqFnWQav1TIZd02FOGUeDOnc0H4IiBS6Kb2VUgLWLVRCjfXA2n3P5lACrba_AafktVr-cYWXCXakZByF-tOmgLVhLp7yo',
    ),
  ];

  static const List<_TeamMember> _teamB = [
    _TeamMember(
      'https://lh3.googleusercontent.com/aida-public/AB6AXuDCneDtPBpw5bnYFnVfwA77Efyz0kYeZpgQQ-ydvrBmL5Euh7hpt08dzmfjw1CsvfiZDJb_HswesD34xpjnT2QLl1OvBM0Apt6f9K1o-pT3ZM86rnQDURlB5fW4yGKq86mRcOq3afep7x_fFY8xwcY2gdeXDgcfJY5rQ24KOBZ5P49AITVP6JduZRlToSGmhoBKJ9amJWg8SuZ_XKE5CfiROCx45EmozTY1YOGBku4mch2YBC0JUeVAtsbKtdQB1qjwniBhMpxdsKU',
    ),
    _TeamMember(
      'https://lh3.googleusercontent.com/aida-public/AB6AXuALPgduR1_z_GZtilZlNsHc8rhuoQFO3X2pSBj1q6_m5eaqrRdLrvHy6AydtQ72NME4SkW3wU75BQ1XoFLIHUv1TT1jlW5cIYmX65_o3RDzvytbq4H4Gx-kdNvieOqfakZMOhozxZHJiU3GRpbbyv2fbP08IfiLj81hqxsku9NAgKHW0N8Tbd1u2dlbWZW5XM0WsiXUCZbojd7dsjeIMYmPAl6PEPct6r2xqk5qc9EvHsbxrj7LCmKnRCea3eWdAFrmKKuGItwe3g0',
    ),
    _TeamMember(
      'https://lh3.googleusercontent.com/aida-public/AB6AXuC6teTiitYB8aOpU3iCAj_XD2qJmugM6IMEbs_wLwYea3HI6MvQ-pTxUyMjDvjcs9jxzj82PQRGb2aI-VidKxida2wbF0KaUOrJjkn8DlG25B6kGEgzEY2kbNlDgTDQPTpC_vMcrrmlWRwy0vI69_LQ1sMEQBLD-inH7dP-GToa5a9K5z6yEkuz0YHOoriDXWPauN9j4JiWCdDplaRfw_pCwMJnM6IyQCULc7kTOnb1DdraXoHDrWS6LGsfu1Wi_RJVj-puPEHoDCI',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          Column(
            children: [
              // 헤더
              _Header(onBackPressed: () => Navigator.of(context).pop()),
              // 스크롤 영역
              Expanded(
                child: SingleChildScrollView(
                  physics: const BouncingScrollPhysics(),
                  padding: const EdgeInsets.only(bottom: 220),
                  child: Column(
                    children: [
                      // 팀 매칭 표시
                      _TeamMatchDisplay(teamA: _teamA, teamB: _teamB),
                      const SizedBox(height: 16),
                      // 예치금 진행 상태
                      const _DepositProgress(current: 1, total: 3),
                      const SizedBox(height: 16),
                      // 잠긴 채팅방
                      const _LockedChatPlaceholder(),
                    ],
                  ),
                ),
              ),
            ],
          ),
          // 하단 액션 버튼
          const Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: _BottomActionSheet(),
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
    return Container(
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight.withValues(alpha: 0.9),
        border: const Border(bottom: BorderSide(color: _AppColors.gray100)),
      ),
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          child: Row(
            children: [
              CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: const Size(44, 44),
                onPressed: onBackPressed,
                child: const Icon(
                  CupertinoIcons.back,
                  color: _AppColors.textMain,
                  size: 24,
                ),
              ),
              const Expanded(
                child: Text(
                  '미팅 방',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.textMain,
                  ),
                ),
              ),
              const SizedBox(width: 44),
            ],
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 팀 매칭 표시
// =============================================================================
class _TeamMatchDisplay extends StatelessWidget {
  final List<_TeamMember> teamA;
  final List<_TeamMember> teamB;

  const _TeamMatchDisplay({required this.teamA, required this.teamB});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 24, 24, 0),
      child: Column(
        children: [
          // Team A
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _AvatarStack(members: teamA, isReversed: false),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: _AppColors.primary.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Text(
                  'TEAM A',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: _AppColors.primary,
                  ),
                ),
              ),
            ],
          ),
          // VS 구분선
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 20),
            child: Row(
              children: [
                Expanded(
                  child: Container(height: 1, color: _AppColors.gray200),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: Text(
                    'VS',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 2,
                      color: _AppColors.gray400,
                    ),
                  ),
                ),
                Expanded(
                  child: Container(height: 1, color: _AppColors.gray200),
                ),
              ],
            ),
          ),
          // Team B
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: _AppColors.indigo50,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Text(
                  'TEAM B',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: _AppColors.indigo500,
                  ),
                ),
              ),
              _AvatarStack(members: teamB, isReversed: true),
            ],
          ),
        ],
      ),
    );
  }
}

class _AvatarStack extends StatelessWidget {
  final List<_TeamMember> members;
  final bool isReversed;

  const _AvatarStack({required this.members, required this.isReversed});

  @override
  Widget build(BuildContext context) {
    final displayMembers = isReversed ? members.reversed.toList() : members;

    return SizedBox(
      width: 56 + (members.length - 1) * 40,
      height: 56,
      child: Stack(
        children: displayMembers.asMap().entries.map((entry) {
          final index = entry.key;
          final member = entry.value;
          final offset = isReversed
              ? (members.length - 1 - index) * 40.0
              : index * 40.0;

          return Positioned(
            left: offset,
            child: Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: _AppColors.surfaceLight, width: 2),
                boxShadow: [
                  BoxShadow(
                    color: CupertinoColors.black.withValues(alpha: 0.08),
                    blurRadius: 4,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: ClipOval(
                child: Image.network(
                  member.imageUrl,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => Container(
                    color: _AppColors.gray200,
                    child: const Icon(
                      CupertinoIcons.person_fill,
                      color: _AppColors.gray400,
                      size: 28,
                    ),
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

// =============================================================================
// 예치금 진행 상태
// =============================================================================
class _DepositProgress extends StatelessWidget {
  final int current;
  final int total;

  const _DepositProgress({required this.current, required this.total});

  double get _progress => current / total;
  int get _percent => (_progress * 100).round();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Container(
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: _AppColors.gray100),
          boxShadow: [
            BoxShadow(
              color: CupertinoColors.black.withValues(alpha: 0.05),
              blurRadius: 20,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                RichText(
                  text: TextSpan(
                    children: [
                      const TextSpan(
                        text: '약속 머니 모으는 중 ',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: _AppColors.textMain,
                        ),
                      ),
                      TextSpan(
                        text: '($current/$total)',
                        style: const TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: _AppColors.primary,
                        ),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: _AppColors.primary.withValues(alpha: 0.1),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    CupertinoIcons.money_dollar_circle,
                    color: _AppColors.primary,
                    size: 20,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            const Text(
              '안전한 만남을 위해 전원이 예치금을\n입금해야 대화방이 열려요.',
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 14,
                height: 1.5,
                color: _AppColors.textSecondary,
              ),
            ),
            const SizedBox(height: 20),
            // 프로그레스 바
            Container(
              height: 12,
              decoration: BoxDecoration(
                color: _AppColors.gray100,
                borderRadius: BorderRadius.circular(6),
              ),
              child: FractionallySizedBox(
                alignment: Alignment.centerLeft,
                widthFactor: _progress,
                child: Container(
                  decoration: BoxDecoration(
                    color: _AppColors.primary,
                    borderRadius: BorderRadius.circular(6),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  '$_percent%',
                  style: const TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.primary,
                  ),
                ),
                const Text(
                  '100%',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    color: _AppColors.gray400,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 잠긴 채팅방 플레이스홀더
// =============================================================================
class _LockedChatPlaceholder extends StatelessWidget {
  const _LockedChatPlaceholder();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Container(
        height: 240,
        decoration: BoxDecoration(
          color: _AppColors.gray100.withValues(alpha: 0.5),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: _AppColors.gray200),
        ),
        child: Stack(
          children: [
            // 블러 처리된 가짜 채팅
            Opacity(
              opacity: 0.4,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    _FakeChatBubble(isMe: false),
                    const SizedBox(height: 16),
                    _FakeChatBubble(isMe: true),
                    const SizedBox(height: 16),
                    _FakeChatBubble(isMe: false),
                  ],
                ),
              ),
            ),
            // 잠금 오버레이
            Container(
              decoration: BoxDecoration(
                color: CupertinoColors.white.withValues(alpha: 0.4),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: _AppColors.surfaceLight,
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: CupertinoColors.black.withValues(alpha: 0.1),
                            blurRadius: 12,
                            offset: const Offset(0, 4),
                          ),
                        ],
                      ),
                      child: const Icon(
                        CupertinoIcons.lock_fill,
                        color: _AppColors.gray400,
                        size: 32,
                      ),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      '대화방이 잠겨있습니다',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color: _AppColors.gray700,
                      ),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      '예치금이 모두 모이면 열려요',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 12,
                        color: _AppColors.gray500,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FakeChatBubble extends StatelessWidget {
  final bool isMe;

  const _FakeChatBubble({required this.isMe});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: isMe ? MainAxisAlignment.end : MainAxisAlignment.start,
      children: [
        if (!isMe) ...[
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: _AppColors.gray300,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 8),
        ],
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: isMe
                ? _AppColors.primary.withValues(alpha: 0.2)
                : _AppColors.surfaceLight,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: isMe ? 80 : 96,
                height: 8,
                decoration: BoxDecoration(
                  color: _AppColors.gray200,
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
              if (!isMe) ...[
                const SizedBox(height: 6),
                Container(
                  width: 64,
                  height: 8,
                  decoration: BoxDecoration(
                    color: _AppColors.gray200,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              ],
            ],
          ),
        ),
        if (isMe) ...[
          const SizedBox(width: 8),
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: _AppColors.gray300,
              shape: BoxShape.circle,
            ),
          ),
        ],
      ],
    );
  }
}

// =============================================================================
// 하단 액션 시트
// =============================================================================
class _BottomActionSheet extends StatelessWidget {
  const _BottomActionSheet();

  void _onDeposit() {
    HapticFeedback.mediumImpact();
    // TODO: 예치금 내기
  }

  void _onFindSubstitute() {
    HapticFeedback.lightImpact();
    // TODO: 대타 구하기
  }

  void _onViewPartnerPlaces() {
    HapticFeedback.selectionClick();
    // TODO: 제휴 장소 추천 보기
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return Container(
      padding: EdgeInsets.fromLTRB(20, 20, 20, bottomPadding + 20),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: const BorderRadius.only(
          topLeft: Radius.circular(24),
          topRight: Radius.circular(24),
        ),
        border: const Border(top: BorderSide(color: _AppColors.gray100)),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.05),
            blurRadius: 20,
            offset: const Offset(0, -4),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 예치금 내기 버튼
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: _onDeposit,
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
                  Text(
                    '예치금 내기',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                      color: CupertinoColors.white,
                    ),
                  ),
                  SizedBox(width: 6),
                  Icon(
                    CupertinoIcons.arrow_right,
                    size: 18,
                    color: CupertinoColors.white,
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          // 대타 구하기 버튼
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: _onFindSubstitute,
            child: Container(
              width: double.infinity,
              height: 56,
              decoration: BoxDecoration(
                color: _AppColors.surfaceLight,
                borderRadius: BorderRadius.circular(28),
                border: Border.all(color: _AppColors.gray200),
              ),
              child: const Center(
                child: Text(
                  '대타 구하기',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 17,
                    fontWeight: FontWeight.w600,
                    color: _AppColors.gray700,
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),
          // 제휴 장소 링크
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: _onViewPartnerPlaces,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  '제휴 장소 추천 보기',
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: _AppColors.gray400,
                    decoration: TextDecoration.underline,
                    decorationColor: _AppColors.gray300,
                  ),
                ),
                const SizedBox(width: 4),
                const Icon(
                  CupertinoIcons.arrow_up_right_square,
                  size: 14,
                  color: _AppColors.gray400,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
