// =============================================================================
// 요청 거절 안내 화면
// 경로: lib/features/event/screens/team_request_declined_screen.dart
//
// 상대 팀 사용자에게만 표시되는 화면.
// 공격적이지 않은 차분한 톤: "이번 요청은 이어지지 않았어요"
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

import '../../../data/models/event/event_team_match_model.dart';
import '../models/event_team_route_args.dart';

class _AppColors {
  static const Color backgroundLight = Color(0xFFF7F3F8);
  static const Color textMain = Color(0xFF2E243F);
  static const Color textSub = Color(0xFF776886);
  static const Color primary = Color(0xFFB44AC0);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray400 = Color(0xFF9CA3AF);
}

class TeamRequestDeclinedScreen extends StatelessWidget {
  final TeamRequestDeclinedArgs? args;

  const TeamRequestDeclinedScreen({super.key, this.args});

  @override
  Widget build(BuildContext context) {
    final otherTeam = args?.otherTeamSnapshot;
    final members = otherTeam?.members ?? const <EventTeamMatchMemberSnapshot>[];

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: SafeArea(
        child: Stack(
          children: [
            Column(
              children: [
                _Header(onBack: () => Navigator.of(context).pop()),
                Expanded(
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 32),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          // 아이콘
                          Container(
                            width: 80,
                            height: 80,
                            decoration: BoxDecoration(
                              color: _AppColors.primary.withValues(alpha: 0.06),
                              shape: BoxShape.circle,
                            ),
                            child: Icon(
                              CupertinoIcons.heart_slash,
                              color: _AppColors.primary.withValues(alpha: 0.4),
                              size: 36,
                            ),
                          ),
                          const SizedBox(height: 28),

                          // 메인 메시지
                          const Text(
                            '이번 요청은\n이어지지 않았어요',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 24,
                              fontWeight: FontWeight.w800,
                              height: 1.35,
                              color: _AppColors.textMain,
                            ),
                          ),
                          const SizedBox(height: 12),

                          const Text(
                            '아쉽지만 다음 기회를 기다려 볼까요?\n더 좋은 만남이 기다리고 있을 거예요.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 14,
                              fontWeight: FontWeight.w500,
                              height: 1.55,
                              color: _AppColors.textSub,
                            ),
                          ),

                          // 상대 팀 미니 프리뷰 (있으면)
                          if (members.isNotEmpty) ...[
                            const SizedBox(height: 32),
                            Container(
                              padding: const EdgeInsets.all(16),
                              decoration: BoxDecoration(
                                color: CupertinoColors.white,
                                borderRadius: BorderRadius.circular(20),
                                border: Border.all(
                                  color: _AppColors.primary.withValues(alpha: 0.06),
                                ),
                              ),
                              child: Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  for (var i = 0; i < members.length && i < 3; i++) ...[
                                    if (i > 0) const SizedBox(width: 10),
                                    _MiniAvatar(
                                      photoUrl: members[i].photoUrl,
                                      name: members[i].displayName,
                                    ),
                                  ],
                                ],
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),

            // 하단 확인 버튼
            Positioned(
              left: 20,
              right: 20,
              bottom: 20 + MediaQuery.of(context).padding.bottom,
              child: CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: () {
                  HapticFeedback.lightImpact();
                  Navigator.of(context).pop();
                },
                child: Container(
                  height: 56,
                  decoration: BoxDecoration(
                    color: _AppColors.textMain,
                    borderRadius: BorderRadius.circular(18),
                    boxShadow: [
                      BoxShadow(
                        color: _AppColors.textMain.withValues(alpha: 0.15),
                        blurRadius: 16,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                  alignment: Alignment.center,
                  child: const Text(
                    '확인',
                    style: TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                      color: CupertinoColors.white,
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
}

class _Header extends StatelessWidget {
  final VoidCallback onBack;

  const _Header({required this.onBack});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(44, 44),
            onPressed: onBack,
            child: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: CupertinoColors.white.withValues(alpha: 0.9),
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Icon(
                CupertinoIcons.back,
                color: _AppColors.textMain,
                size: 22,
              ),
            ),
          ),
          const Spacer(),
          const SizedBox(width: 44),
        ],
      ),
    );
  }
}

class _MiniAvatar extends StatelessWidget {
  final String? photoUrl;
  final String name;

  const _MiniAvatar({required this.photoUrl, required this.name});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(
              color: _AppColors.gray100,
              width: 2,
            ),
          ),
          clipBehavior: Clip.antiAlias,
          child: photoUrl != null && photoUrl!.isNotEmpty
              ? Image.network(
                  photoUrl!,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => _placeholder(),
                )
              : _placeholder(),
        ),
        const SizedBox(height: 6),
        SizedBox(
          width: 56,
          child: Text(
            name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 11,
              fontWeight: FontWeight.w600,
              color: _AppColors.textSub,
            ),
          ),
        ),
      ],
    );
  }

  Widget _placeholder() {
    return Container(
      color: _AppColors.gray100,
      child: const Icon(
        CupertinoIcons.person_fill,
        size: 22,
        color: _AppColors.gray400,
      ),
    );
  }
}
