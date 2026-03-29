// =============================================================================
// 3:3 그룹 매칭 결과 화면 (미팅 방 잠금 상태)
// 경로: lib/features/event/screens/group_match_screen.dart
//
// HTML to Flutter 변환 구현
// - Cupertino 스타일 적용
// - Team A vs Team B 레이아웃
// - 예치금 진행률 (Promise Money)
// - 잠긴 채팅방 블러 효과
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Colors;
import 'dart:ui';

// =============================================================================
// 색상 정의
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF0426E); // #f0426e
  static const Color backgroundLight = Color(0xFFF8F6F6); // #f8f6f6
  static const Color surfaceLight = CupertinoColors.white;
  static const Color textMain = Color(0xFF0F172A); // slate-900 (approx)
  static const Color textSub = Color(0xFF64748B); // slate-500
  static const Color divider = Color(0xFFE2E8F0); // slate-200

  static const Color teamALabel = Color(0xFFF0426E);
  static const Color teamABg = Color(0xFFFCEEF2);
  static const Color teamBLabel = Color(0xFF6366F1); // indigo-500
  static const Color teamBBg = Color(0xFFEEF2FF); // indigo-50
}

// =============================================================================
// 메인 화면
// =============================================================================
class GroupMatchScreen extends StatelessWidget {
  const GroupMatchScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: _AppColors.surfaceLight.withValues(alpha: 0.8),
        border: Border(bottom: BorderSide(color: CupertinoColors.systemGrey6)),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          child: const Icon(CupertinoIcons.back, color: _AppColors.textMain),
          onPressed: () => Navigator.of(context).pop(),
        ),
        middle: const Text(
          '미팅 방',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontWeight: FontWeight.w700,
            color: _AppColors.textMain,
          ),
        ),
      ),
      child: Stack(
        children: [
          // 메인 스크롤 영역
          SafeArea(
            bottom: false,
            child: SingleChildScrollView(
              padding: const EdgeInsets.only(bottom: 160), // 하단 시트 공간 확보
              physics: const BouncingScrollPhysics(),
              child: Column(
                children: const [
                  _TeamMatchSection(),
                  _DepositProgressSection(),
                  _LockedChatSection(),
                ],
              ),
            ),
          ),
          // 하단 고정 액션 시트
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
// 섹션 1: 팀 매칭 디스플레이 (A vs B)
// =============================================================================
class _TeamMatchSection extends StatelessWidget {
  const _TeamMatchSection();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 24, 24, 8),
      child: Column(
        children: [
          // Team A (Female)
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _AvatarGroup(
                images: const [
                  'https://lh3.googleusercontent.com/aida-public/AB6AXuBmUepkm5GzVSOtdIPbrwZP6tT25XXiNJa0BKBU0fCHYrt76cK7V2EsRWGORC5HV5Bs11XEswQpxKiHZEZamcdudrb2S7-ujzip_giPw0XSRaBkqg-cEwSHFeIAdtux_D2D7nKWIT89hbr13Ht4IBymxZT0dM2MkJYHhM8xWDK4UouQnUYcVnpaly2vkFsGLAkyphtKX0P3wkie9UKQ0bUb62N1rLHvuVgA_8bCrc0UXT9wGfj_incK3ntwGTZ7ivAqA9un5ngASkY',
                  'https://lh3.googleusercontent.com/aida-public/AB6AXuBCujWz3Uyv03tV7HuV3xCarPsgWvjZYYE5g2lqn53jqSxwvJ86UoGP_f1g9X5gyRqkJl8SJ24qKUvlXMcPaoy23F06muxxzYbL7s3GzfxF-jwexeGS0t61UbGSslNUBhIXbkdaC3uJPClWVymlsxWweDDzsLAQtPEEmCXhiH2nN7Q7YnsGOGqctGS46HJjw1L-Gmfyh6wyT8CIlvdL_tanxB9XmVHqVxxMwKPkHrGlEdNJAXCZJDbvr_q9ptYq5M4Zr3tVq7jlRng',
                  'https://lh3.googleusercontent.com/aida-public/AB6AXuB-zLFP2o7kGUN56rlKsE5tZsUVrA3aaWS0qukp5mQNFMGbjSCXK87694EkrinBSISClktE6ki1xbsDcOn8MnVVrJb0HPymKz908s_3zLnA1HdzhVn1X-dv3e5Nx8iAb7hZ2ZmXxFFdJTxg78maNd1-52lo5Hy7-Lak-ldi1CYpm8pqtmKqFnWQav1TIZd02FOGUeDOnc0H4IiBS6Kb2VUgLWLVRCjfXA2n3P5lACrba_AafktVr-cYWXCXakZByF-tOmgLVhLp7yo',
                ],
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: _AppColors.teamABg,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Text(
                  'TEAM A',
                  style: TextStyle(
                    color: _AppColors.teamALabel,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          // VS Divider
          SizedBox(
            height: 24,
            child: Stack(
              alignment: Alignment.center,
              children: [
                Container(height: 1, color: _AppColors.divider),
                Container(
                  color: _AppColors.backgroundLight,
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  child: const Text(
                    'VS',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w900,
                      color: Color(0xFF94A3B8), // slate-400
                      letterSpacing: 2.0,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          // Team B (Male) - Reversed Layout in Row
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: _AppColors.teamBBg,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Text(
                  'TEAM B',
                  style: TextStyle(
                    color: _AppColors.teamBLabel,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              _AvatarGroup(
                isReversed: true,
                images: const [
                  'https://lh3.googleusercontent.com/aida-public/AB6AXuDCneDtPBpw5bnYFnVfwA77Efyz0kYeZpgQQ-ydvrBmL5Euh7hpt08dzmfjw1CsvfiZDJb_HswesD34xpjnT2QLl1OvBM0Apt6f9K1o-pT3ZM86rnQDURlB5fW4yGKq86mRcOq3afep7x_fFY8xwcY2gdeXDgcfJY5rQ24KOBZ5P49AITVP6JduZRlToSGmhoBKJ9amJWg8SuZ_XKE5CfiROCx45EmozTY1YOGBku4mch2YBC0JUeVAtsbKtdQB1qjwniBhMpxdsKU',
                  'https://lh3.googleusercontent.com/aida-public/AB6AXuALPgduR1_z_GZtilZlNsHc8rhuoQFO3X2pSBj1q6_m5eaqrRdLrvHy6AydtQ72NME4SkW3wU75BQ1XoFLIHUv1TT1jlW5cIYmX65_o3RDzvytbq4H4Gx-kdNvieOqfakZMOhozxZHJiU3GRpbbyv2fbP08IfiLj81hqxsku9NAgKHW0N8Tbd1u2dlbWZW5XM0WsiXUCZbojd7dsjeIMYmPAl6PEPct6r2xqk5qc9EvHsbxrj7LCmKnRCea3eWdAFrmKKuGItwe3g0',
                  'https://lh3.googleusercontent.com/aida-public/AB6AXuC6teTiitYB8aOpU3iCAj_XD2qJmugM6IMEbs_wLwYea3HI6MvQ-pTxUyMjDvjcs9jxzj82PQRGb2aI-VidKxida2wbF0KaUOrJjkn8DlG25B6kGEgzEY2kbNlDgTDQPTpC_vMcrrmlWRwy0vI69_LQ1sMEQBLD-inH7dP-GToa5a9K5z6yEkuz0YHOoriDXWPauN9j4JiWCdDplaRfw_pCwMJnM6IyQCULc7kTOnb1DdraXoHDrWS6LGsfu1Wi_RJVj-puPEHoDCI',
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _AvatarGroup extends StatelessWidget {
  final List<String> images;
  final bool isReversed;

  const _AvatarGroup({required this.images, this.isReversed = false});

  @override
  Widget build(BuildContext context) {
    // 겹치는 효과를 위해 Stack 또는 너비가 제한된 Row 사용
    // 여기서는 margin을 음수로 주어 구현
    List<Widget> avatars = images.asMap().entries.map((entry) {
      final index = entry.key;
      final url = entry.value;
      return Transform.translate(
        offset: Offset(index * -12.0, 0), // 왼쪽으로 12씩 겹침
        child: Container(
          width: 56,
          height: 56,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(color: Colors.white, width: 2),
            boxShadow: const [
              BoxShadow(
                color: Colors.black12,
                blurRadius: 4,
                offset: Offset(0, 2),
              ),
            ],
          ),
          child: ClipOval(
            child: Image.network(
              url,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => Container(color: Colors.grey[200]),
            ),
          ),
        ),
      );
    }).toList();

    if (isReversed) {
      avatars = avatars.reversed.toList();
      // Reverse일 때는 겹치는 방향 처리가 조금 다를 수 있으나, 간단히 구현
      return SizedBox(
        height: 56,
        // 오른쪽 정렬 + 겹침 효과를 위해 Stack으로 변경하거나 Row 방향 조정 필요
        // 간단히 Row로 하되 mainAxisSize 최소화
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: images.map((url) {
            return Align(
              widthFactor: 0.75, // 겹침 효과
              child: Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.white, width: 2),
                  boxShadow: const [
                    BoxShadow(
                      color: Colors.black12,
                      blurRadius: 4,
                      offset: Offset(0, 2),
                    ),
                  ],
                ),
                child: ClipOval(child: Image.network(url, fit: BoxFit.cover)),
              ),
            );
          }).toList(),
        ),
      );
    }

    return SizedBox(
      height: 56,
      width: (56 * 3) - (12 * 2), // 전체 너비 계산
      child: Stack(
        children: images.asMap().entries.map((entry) {
          final index = entry.key;
          return Positioned(
            left: index * 44.0, // 56 - 12 = 44
            child: Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white, width: 2),
                boxShadow: const [
                  BoxShadow(
                    color: Colors.black12,
                    blurRadius: 4,
                    offset: Offset(0, 1),
                  ),
                ],
              ),
              child: ClipOval(
                child: Image.network(entry.value, fit: BoxFit.cover),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

// =============================================================================
// 섹션 2: 예치금 진행바
// =============================================================================
class _DepositProgressSection extends StatelessWidget {
  const _DepositProgressSection();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Container(
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: _AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: CupertinoColors.systemGrey6),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.05),
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
                  text: const TextSpan(
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.textMain,
                    ),
                    children: [
                      TextSpan(text: '약속 머니 모으는 중 '),
                      TextSpan(
                        text: '(1/3)',
                        style: TextStyle(color: _AppColors.primary),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.all(6),
                  decoration: BoxDecoration(
                    color: _AppColors.primary.withValues(alpha: 0.1),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    CupertinoIcons.money_dollar,
                    color: _AppColors.primary,
                    size: 20,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            const Text(
              '안전한 만남을 위해 전원이 예치금을\n입금해야 대화방이 열려요.',
              style: TextStyle(
                fontSize: 14,
                color: _AppColors.textSub,
                height: 1.5,
              ),
            ),
            const SizedBox(height: 20),
            // Progress Bar
            Stack(
              children: [
                Container(
                  height: 12,
                  decoration: BoxDecoration(
                    color: const Color(0xFFF1F5F9), // slate-100
                    borderRadius: BorderRadius.circular(6),
                  ),
                ),
                FractionallySizedBox(
                  widthFactor: 0.33,
                  child: Container(
                    height: 12,
                    decoration: BoxDecoration(
                      color: _AppColors.primary,
                      borderRadius: BorderRadius.circular(6),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: const [
                Text(
                  '33%',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: _AppColors.primary,
                  ),
                ),
                Text(
                  '100%',
                  style: TextStyle(
                    fontSize: 12,
                    color: Color(0xFF94A3B8), // slate-400
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
// 섹션 3: 잠긴 채팅방 (블러 효과)
// =============================================================================
class _LockedChatSection extends StatelessWidget {
  const _LockedChatSection();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Container(
        height: 240,
        decoration: BoxDecoration(
          color: const Color(0xFFF9FAFB), // gray-50
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: CupertinoColors.systemGrey5),
        ),
        child: Stack(
          children: [
            // Blurred Chat Content
            Positioned.fill(
              child: ImageFiltered(
                imageFilter: ImageFilter.blur(sigmaX: 2, sigmaY: 2),
                child: Opacity(
                  opacity: 0.4,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      children: [
                        _mockChatBubble(true, 100),
                        const SizedBox(height: 16),
                        _mockChatBubble(false, 140),
                        const SizedBox(height: 16),
                        _mockChatBubble(true, 160),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            // Lock Overlay
            Positioned.fill(
              child: Container(
                decoration: BoxDecoration(
                  color: _AppColors.surfaceLight.withValues(alpha: 0.4),
                  borderRadius: BorderRadius.circular(24),
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(24),
                  child: BackdropFilter(
                    filter: ImageFilter.blur(sigmaX: 4, sigmaY: 4),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Container(
                          width: 64,
                          height: 64,
                          margin: const EdgeInsets.only(bottom: 12),
                          decoration: BoxDecoration(
                            color: _AppColors.surfaceLight,
                            shape: BoxShape.circle,
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.1),
                                blurRadius: 10,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          child: const Icon(
                            CupertinoIcons.lock_fill,
                            color: Color(0xFF94A3B8), // gray-400
                            size: 32,
                          ),
                        ),
                        const Text(
                          '대화방이 잠겨있습니다',
                          style: TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w700,
                            color: _AppColors.textMain,
                          ),
                        ),
                        const SizedBox(height: 4),
                        const Text(
                          '예치금이 모두 모이면 열려요',
                          style: TextStyle(
                            fontSize: 12,
                            color: _AppColors.textSub,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _mockChatBubble(bool isLeft, double width) {
    if (isLeft) {
      return Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Container(
            width: 32,
            height: 32,
            decoration: const BoxDecoration(
              color: Color(0xFFE2E8F0),
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 8),
          Container(
            width: width,
            height: 40,
            decoration: const BoxDecoration(
              color: _AppColors.surfaceLight,
              borderRadius: BorderRadius.only(
                topLeft: Radius.circular(16),
                topRight: Radius.circular(16),
                bottomRight: Radius.circular(16),
              ),
            ),
          ),
        ],
      );
    } else {
      return Row(
        mainAxisAlignment: MainAxisAlignment.end,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Container(
            width: width,
            height: 40,
            decoration: BoxDecoration(
              color: _AppColors.primary.withValues(alpha: 0.2),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(16),
                topRight: Radius.circular(16),
                bottomLeft: Radius.circular(16),
              ),
            ),
          ),
          const SizedBox(width: 8),
          Container(
            width: 32,
            height: 32,
            decoration: const BoxDecoration(
              color: Color(0xFFE2E8F0),
              shape: BoxShape.circle,
            ),
          ),
        ],
      );
    }
  }
}

// =============================================================================
// 하단 고정 액션 시트
// =============================================================================
class _BottomActionSheet extends StatelessWidget {
  const _BottomActionSheet();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: const BorderRadius.only(
          topLeft: Radius.circular(24),
          topRight: Radius.circular(24),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.1),
            blurRadius: 20,
            offset: const Offset(0, -5),
          ),
        ],
        border: Border(top: BorderSide(color: CupertinoColors.systemGrey6)),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // 예치금 내기 버튼
            CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: () {},
              child: Container(
                height: 56,
                decoration: BoxDecoration(
                  color: _AppColors.primary,
                  borderRadius: BorderRadius.circular(28),
                  boxShadow: [
                    BoxShadow(
                      color: _AppColors.primary.withValues(alpha: 0.3),
                      blurRadius: 10,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: const [
                    Text(
                      '예치금 내기',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    SizedBox(width: 8),
                    Icon(
                      CupertinoIcons.arrow_right,
                      color: Colors.white,
                      size: 20,
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            // 대타 구하기 버튼
            CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: () {},
              child: Container(
                height: 56,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: _AppColors.surfaceLight,
                  borderRadius: BorderRadius.circular(28),
                  border: Border.all(color: CupertinoColors.systemGrey4),
                ),
                child: const Text(
                  '대타 구하기',
                  style: TextStyle(
                    color: Color(0xFF334155), // slate-700
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 16),
            // 제휴 장소 추천 링크
            GestureDetector(
              onTap: () {},
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: const [
                  Text(
                    '제휴 장소 추천 보기',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      color: _AppColors.textSub,
                      decoration: TextDecoration.underline,
                    ),
                  ),
                  SizedBox(width: 4),
                  Icon(
                    CupertinoIcons.arrow_up_right,
                    size: 10,
                    color: _AppColors.textSub,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
