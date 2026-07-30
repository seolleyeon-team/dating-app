// =============================================================================
// 3:3 블라인드 취향 미팅 — 이벤트 탭 카드
// 경로: lib/features/blind_meeting/presentation/widgets/blind_meeting_event_card.dart
//
// 기존 '기타 이벤트' 탭의 랜덤 매칭 카드(슬롯머신/셔플 아이콘)를 대체한다.
// =============================================================================

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../../router/route_names.dart';
import '../../data/blind_meeting_analytics.dart';
import '../theme/blind_meeting_palette.dart';
import 'blind_meeting_common.dart';

/// 이벤트 탭에서 보여줄 블라인드 취향 미팅 소개 카드.
class BlindMeetingEventCard extends StatefulWidget {
  final BlindMeetingAnalytics? analytics;

  const BlindMeetingEventCard({super.key, this.analytics});

  static const String title = '블라인드 취향 미팅';
  static const String description =
      '얼굴 공개 없이,\n취향과 대화 성향이 잘 맞는 여섯 명을 만나보세요.\n혼자 신청해도 설레연이 3:3 팀을 구성해드려요.';
  static const String ctaLabel = '취향 미팅 참가하기';

  @override
  State<BlindMeetingEventCard> createState() => _BlindMeetingEventCardState();
}

class _BlindMeetingEventCardState extends State<BlindMeetingEventCard> {
  @override
  void initState() {
    super.initState();
    (widget.analytics ?? BlindMeetingAnalytics()).log(
      BlindMeetingAnalyticsEvent.cardViewed,
    );
  }

  void _open(BuildContext context) {
    HapticFeedback.selectionClick();
    Navigator.of(
      context,
      rootNavigator: true,
    ).pushNamed(RouteNames.blindTasteMeeting);
  }

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);

    return ColoredBox(
      color: palette.background,
      child: SingleChildScrollView(
        physics: const BouncingScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(0, 16, 0, 120),
        child: BlindMeetingResponsiveBody(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              BlindMeetingCard(
                padding: const EdgeInsets.all(22),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        BlindMeetingBadge(
                          label: '얼굴 비공개',
                          icon: Icons.visibility_off_outlined,
                          color: palette.plum,
                        ),
                        const SizedBox(width: 6),
                        BlindMeetingBadge(
                          label: '혼자 참가 가능',
                          icon: Icons.person_outline,
                          color: palette.indigo,
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    Text(
                      BlindMeetingEventCard.title,
                      style: BlindMeetingText.display(palette.ink),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      BlindMeetingEventCard.description,
                      style: BlindMeetingText.body(palette.inkSoft),
                    ),
                    const SizedBox(height: 20),
                    const _QuietVisual(),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              BlindMeetingPrimaryButton(
                label: BlindMeetingEventCard.ctaLabel,
                icon: Icons.people_outline,
                onPressed: () => _open(context),
              ),
              const SizedBox(height: 16),
              BlindMeetingCard(
                padding: const EdgeInsets.all(18),
                background: palette.surfaceMuted,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '이런 점이 달라요',
                      style: BlindMeetingText.sectionTitle(palette.ink),
                    ),
                    const SizedBox(height: 12),
                    for (final line in const [
                      '학교 인증을 마친 대학생만 참가해요',
                      '취향과 대화 성향을 반영해 설레연이 팀을 구성해요',
                      '술 없이 만나는 무알코올 미팅도 선택할 수 있어요',
                      '안전도장과 노쇼 보호로 약속을 지켜요',
                      '미팅 후 서로 선택하면 1:1 대화가 열려요',
                    ])
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(Icons.check, size: 16, color: palette.sage),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                line,
                                style: BlindMeetingText.caption(
                                  palette.inkSoft,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 슬롯머신 대신 쓰는 차분한 비주얼 (3:3 실루엣 두 줄).
class _QuietVisual extends StatelessWidget {
  const _QuietVisual();

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);

    Widget row(Color tint, String label) => Row(
      children: [
        for (var i = 0; i < 3; i++)
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: Container(
              width: 34,
              height: 34,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: tint.withValues(alpha: 0.14),
                border: Border.all(color: tint.withValues(alpha: 0.28)),
              ),
              alignment: Alignment.center,
              child: Icon(Icons.person, size: 18, color: tint),
            ),
          ),
        const SizedBox(width: 4),
        Text(label, style: BlindMeetingText.caption(palette.inkSoft)),
      ],
    );

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: palette.surfaceMuted,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          row(palette.plum, '우리 팀 3명'),
          const SizedBox(height: 12),
          Container(height: 1, color: palette.border),
          const SizedBox(height: 12),
          row(palette.indigo, '상대 팀 3명'),
        ],
      ),
    );
  }
}
