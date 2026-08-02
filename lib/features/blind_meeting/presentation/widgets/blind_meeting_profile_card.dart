// =============================================================================
// 3:3 블라인드 취향 미팅 — 공개 프로필 카드
// 경로: lib/features/blind_meeting/presentation/widgets/blind_meeting_profile_card.dart
//
// 블라인드 미팅은 얼굴을 사전 공개하지 않는다. 카드에는 실제 사진 대신
// seed로 결정되는 비식별 실루엣만 렌더링한다.
// 노출 금지: 실제 얼굴, 비공개 DNA, 음주·흡연 상세 응답, 매칭 점수,
//           연락처, 학교 이메일, 신고 정보, 내부 신뢰 점수.
// =============================================================================

import 'package:flutter/material.dart';

import '../../domain/blind_meeting_public_profile.dart';
import '../theme/blind_meeting_palette.dart';
import 'blind_meeting_common.dart';

/// seed 기반 비식별 실루엣 아바타.
class BlindMeetingSilhouetteAvatar extends StatelessWidget {
  final String seed;
  final double size;

  const BlindMeetingSilhouetteAvatar({
    super.key,
    required this.seed,
    this.size = 56,
  });

  /// seed에서 결정적으로 색을 고른다 (같은 사용자는 항상 같은 색).
  static Color tintFor(String seed, BlindMeetingPalette palette) {
    final options = [
      palette.accent,
      palette.accentDeep,
      palette.attention,
      palette.positive,
    ];
    if (seed.isEmpty) return options.first;
    var hash = 0;
    for (final unit in seed.codeUnits) {
      hash = (hash * 31 + unit) & 0x7fffffff;
    }
    return options[hash % options.length];
  }

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    final tint = tintFor(seed, palette);
    return Semantics(
      label: '얼굴이 공개되지 않는 실루엣 아바타',
      image: true,
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: tint.withValues(alpha: 0.14),
          border: Border.all(color: tint.withValues(alpha: 0.3)),
        ),
        alignment: Alignment.center,
        child: Icon(Icons.person, size: size * 0.52, color: tint),
      ),
    );
  }
}

/// 추천 결과 화면의 참가자 카드.
class BlindMeetingProfileCard extends StatelessWidget {
  final BlindMeetingPublicProfile profile;

  /// 내 카드인지 (본인 표시용).
  final bool isMe;

  const BlindMeetingProfileCard({
    super.key,
    required this.profile,
    this.isMe = false,
  });

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    final safetyBadge = profile.safetyStampSummary.badgeLabel;

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: BlindMeetingCard(
        highlighted: isMe,
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                BlindMeetingSilhouetteAvatar(seed: profile.avatarSeed),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Flexible(
                            child: Text(
                              profile.nickname,
                              overflow: TextOverflow.ellipsis,
                              style: BlindMeetingText.cardTitle(palette.ink),
                            ),
                          ),
                          if (isMe) ...[
                            const SizedBox(width: 6),
                            Text(
                              '(나)',
                              style: BlindMeetingText.caption(palette.accent),
                            ),
                          ],
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        [
                          if (profile.department != null) profile.department!,
                          if (profile.mbti != null) profile.mbti!,
                        ].join(' · '),
                        style: BlindMeetingText.caption(palette.inkSoft),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                if (profile.schoolVerified)
                  BlindMeetingBadge(
                    label: '학교 인증',
                    icon: Icons.verified_outlined,
                    color: palette.positive,
                  ),
                if (safetyBadge != null)
                  BlindMeetingBadge(
                    label: safetyBadge,
                    icon: Icons.shield_outlined,
                    color: palette.accent,
                  ),
              ],
            ),
            if (profile.topInterestIds.isNotEmpty) ...[
              const SizedBox(height: 12),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: profile.topInterestIds
                    .map(
                      (interest) => Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 5,
                        ),
                        decoration: BoxDecoration(
                          color: palette.surfaceMuted,
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Text(
                          interest,
                          style: BlindMeetingText.caption(palette.inkSoft),
                        ),
                      ),
                    )
                    .toList(),
              ),
            ],
            if (profile.oneLineIntro != null) ...[
              const SizedBox(height: 12),
              Text(
                profile.oneLineIntro!,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: BlindMeetingText.caption(palette.inkSoft),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
