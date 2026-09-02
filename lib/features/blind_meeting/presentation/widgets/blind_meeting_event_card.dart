// =============================================================================
// 3:3 블라인드 취향 미팅 — 이벤트 탭 카드
// 경로: lib/features/blind_meeting/presentation/widgets/blind_meeting_event_card.dart
//
// 이벤트 탭의 '3:3 시즌 미팅' 세그먼트와 같은 디자인 시스템을 쓴다.
//   히어로 카드(radius 32, 핑크 섀도) → 메인 CTA(pill) → 구분선 → 보조 정보 카드
// 색·형태 값은 BlindMeetingPalette / kEvent* 상수에서만 가져온다.
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

  /// 하단 보조 카드에 쓰는 차별점 문구.
  static const List<String> differences = [
    '학교 인증을 마친 대학생만 참가해요',
    '취향과 대화 성향을 반영해 설레연이 팀을 구성해요',
    '술 없이 만나는 무알코올 미팅도 선택할 수 있어요',
    '안전도장과 노쇼 보호로 약속을 지켜요',
    '미팅 후 서로 선택하면 1:1 대화가 열려요',
  ];

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
    ).pushNamed(RouteNames.blindTasteMeetingParty);
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
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const _IntroHeroCard(),
              const SizedBox(height: 16),
              BlindMeetingPrimaryButton(
                label: BlindMeetingEventCard.ctaLabel,
                icon: Icons.people_outline,
                onPressed: () => _open(context),
              ),
              const SizedBox(height: 24),
              const BlindMeetingSectionDivider(),
              const SizedBox(height: 24),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4),
                child: Text(
                  '이런 점이 달라요',
                  style: BlindMeetingText.sectionTitle(palette.ink),
                ),
              ),
              const SizedBox(height: 12),
              const _DifferenceCard(),
            ],
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 히어로 카드 — 시즌 미팅 슬롯머신 카드와 같은 구성
// =============================================================================
class _IntroHeroCard extends StatelessWidget {
  const _IntroHeroCard();

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);

    return BlindMeetingCard(
      padding: const EdgeInsets.all(24),
      radius: kEventHeroRadius,
      bordered: false,
      child: Column(
        children: [
          // 정보성 pill 2개 (SAFE MATCHING 배지와 같은 계열)
          Wrap(
            alignment: WrapAlignment.center,
            spacing: 6,
            runSpacing: 6,
            children: [
              BlindMeetingBadge(
                label: '얼굴 비공개',
                icon: Icons.visibility_off_outlined,
                color: palette.accent,
              ),
              BlindMeetingBadge(
                label: '혼자 참가 가능',
                icon: Icons.person_outline,
                color: palette.accentDeep,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            BlindMeetingEventCard.title,
            textAlign: TextAlign.center,
            style: BlindMeetingText.display(palette.ink),
          ),
          const SizedBox(height: 6),
          Text(
            BlindMeetingEventCard.description,
            textAlign: TextAlign.center,
            style: BlindMeetingText.body(palette.inkSoft),
          ),
          const SizedBox(height: 24),
          const _TeamCompositionPanel(),
        ],
      ),
    );
  }
}

// =============================================================================
// 우리 팀 3명 / 상대 팀 3명 패널 — 시즌 미팅 슬롯 박스와 같은 연핑크 서브패널
// =============================================================================
class _TeamCompositionPanel extends StatelessWidget {
  const _TeamCompositionPanel();

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: palette.surfaceMuted,
        borderRadius: BorderRadius.circular(kEventCardRadius),
        border: Border.all(color: palette.accent.withValues(alpha: 0.08)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _TeamRow(label: '우리 팀 3명', tint: palette.accent),
          const SizedBox(height: 14),
          const _MatchupDivider(),
          const SizedBox(height: 14),
          _TeamRow(label: '상대 팀 3명', tint: palette.accentDeep),
        ],
      ),
    );
  }
}

class _TeamRow extends StatelessWidget {
  final String label;
  final Color tint;

  const _TeamRow({required this.label, required this.tint});

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: BlindMeetingText.label(palette.ink)),
        const SizedBox(height: 8),
        Row(
          children: [
            for (var i = 0; i < 3; i++)
              Padding(
                padding: const EdgeInsets.only(right: 8),
                child: Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: tint.withValues(alpha: 0.12),
                    border: Border.all(color: tint.withValues(alpha: 0.28)),
                  ),
                  alignment: Alignment.center,
                  child: Icon(Icons.person, size: 18, color: tint),
                ),
              ),
          ],
        ),
      ],
    );
  }
}

/// 두 팀 사이의 hairline + 3 : 3 표시.
class _MatchupDivider extends StatelessWidget {
  const _MatchupDivider();

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);

    return Row(
      children: [
        Expanded(
          child: Container(
            height: 1,
            color: palette.accent.withValues(alpha: 0.12),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
            decoration: BoxDecoration(
              color: palette.surface,
              borderRadius: BorderRadius.circular(999),
              border: Border.all(color: palette.accent.withValues(alpha: 0.14)),
            ),
            child: Text('3 : 3', style: BlindMeetingText.label(palette.accent)),
          ),
        ),
        Expanded(
          child: Container(
            height: 1,
            color: palette.accent.withValues(alpha: 0.12),
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 하단 보조 카드 — 시즌 미팅 하단 정보 카드와 같은 톤
// =============================================================================
class _DifferenceCard extends StatelessWidget {
  const _DifferenceCard();

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);

    return BlindMeetingCard(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (var i = 0; i < BlindMeetingEventCard.differences.length; i++)
            Padding(
              padding: EdgeInsets.only(
                bottom: i == BlindMeetingEventCard.differences.length - 1
                    ? 0
                    : 12,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 20,
                    height: 20,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: palette.accent.withValues(alpha: 0.1),
                    ),
                    alignment: Alignment.center,
                    child: Icon(Icons.check, size: 13, color: palette.accent),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      BlindMeetingEventCard.differences[i],
                      style: BlindMeetingText.caption(palette.inkSoft),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
