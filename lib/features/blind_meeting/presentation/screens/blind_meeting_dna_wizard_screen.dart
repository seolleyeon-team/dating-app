// =============================================================================
// 3:3 블라인드 취향 미팅 — 비공개 DNA 작성 wizard
// 경로: lib/features/blind_meeting/presentation/screens/blind_meeting_dna_wizard_screen.dart
//
// 1/4 대화 분위기
// 2/4 대화 시작 성향
// 3/4 미팅 목적
// 4/4 음주·흡연 동석 선호 확인
//
// 관심사·음주 정도·흡연 여부·MBTI는 온보딩 데이터를 불러오고 다시 묻지 않는다.
// =============================================================================

import 'package:flutter/material.dart';

import '../../../../router/route_names.dart';
import '../../data/blind_meeting_profile_snapshot.dart';
import '../../domain/blind_meeting_enums.dart';
import '../blind_meeting_route_args.dart';
import '../theme/blind_meeting_palette.dart';
import '../widgets/blind_meeting_common.dart';

class BlindMeetingDnaWizardScreen extends StatefulWidget {
  final BlindMeetingProfileSnapshot profile;

  const BlindMeetingDnaWizardScreen({super.key, required this.profile});

  @override
  State<BlindMeetingDnaWizardScreen> createState() =>
      _BlindMeetingDnaWizardScreenState();
}

class _BlindMeetingDnaWizardScreenState
    extends State<BlindMeetingDnaWizardScreen> {
  static const int _totalSteps = 4;

  int _step = 1;
  ConversationAtmosphere? _atmosphere;
  ConversationInitiative? _initiative;
  MeetingPurpose? _purpose;
  AlcoholCompanionPreference? _alcohol;
  SmokingCompanionPreference? _smoking;

  bool get _canGoNext => switch (_step) {
    1 => _atmosphere != null,
    2 => _initiative != null,
    3 => _purpose != null,
    4 => _alcohol != null && _smoking != null,
    _ => false,
  };

  /// 전원 비음주는 프로필상 비음주인 경우에만 선택할 수 있다.
  bool get _canChooseAllSober => widget.profile.drinkingLevel?.isSober ?? false;

  void _next() {
    if (!_canGoNext) return;
    if (_step < _totalSteps) {
      setState(() => _step++);
      return;
    }
    final draft = BlindMeetingDnaDraft(
      profile: widget.profile,
      atmosphere: _atmosphere!,
      initiative: _initiative!,
      purpose: _purpose!,
      alcoholPreference: _alcohol!,
      smokingPreference: _smoking!,
    );
    Navigator.of(
      context,
    ).pushNamed(RouteNames.blindTasteMeetingSchedule, arguments: draft);
  }

  void _back() {
    if (_step > 1) {
      setState(() => _step--);
      return;
    }
    Navigator.of(context).maybePop();
  }

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);

    return Scaffold(
      backgroundColor: palette.background,
      body: Column(
        children: [
          BlindMeetingAppBar(title: '미팅 DNA', onBack: _back),
          Expanded(
            child: SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              padding: const EdgeInsets.only(top: 8, bottom: 32),
              child: BlindMeetingResponsiveBody(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    BlindMeetingStepProgress(
                      step: _step,
                      totalSteps: _totalSteps,
                    ),
                    const SizedBox(height: 24),
                    ..._buildStep(palette),
                  ],
                ),
              ),
            ),
          ),
          SafeArea(
            top: false,
            child: BlindMeetingResponsiveBody(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
              child: BlindMeetingPrimaryButton(
                label: _step < _totalSteps ? '다음' : '일정 선택하기',
                onPressed: _canGoNext ? _next : null,
              ),
            ),
          ),
        ],
      ),
    );
  }

  List<Widget> _buildStep(BlindMeetingPalette palette) {
    switch (_step) {
      case 1:
        return [
          _question('어떤 분위기의 대화를 선호하나요?', palette),
          for (final option in ConversationAtmosphere.values)
            BlindMeetingOptionTile(
              label: option.label,
              selected: _atmosphere == option,
              onTap: () => setState(() => _atmosphere = option),
            ),
        ];
      case 2:
        return [
          _question('새로운 사람 앞에서 먼저 이야기를 시작하는 편인가요?', palette),
          for (final option in ConversationInitiative.values)
            BlindMeetingOptionTile(
              label: option.label,
              selected: _initiative == option,
              onTap: () => setState(() => _initiative = option),
            ),
        ];
      case 3:
        return [
          _question('이번 미팅에서 어떤 만남을 기대하나요?', palette),
          for (final option in MeetingPurpose.values)
            BlindMeetingOptionTile(
              label: option.label,
              selected: _purpose == option,
              onTap: () => setState(() => _purpose = option),
            ),
          const SizedBox(height: 8),
          Text(
            '연애만 원하는 분과 친구만 원하는 분은 같은 미팅에 배정하지 않아요.',
            style: BlindMeetingText.caption(palette.inkSoft),
          ),
        ];
      default:
        return [
          _profileSummary(palette),
          const SizedBox(height: 20),
          _question('함께 만나는 사람들이 술을 마셔도 괜찮나요?', palette),
          for (final option in AlcoholCompanionPreference.values)
            BlindMeetingOptionTile(
              label: option.label,
              description:
                  option == AlcoholCompanionPreference.allSober &&
                      !_canChooseAllSober
                  ? '내 프로필의 음주 정도가 \'전혀 안 함\'일 때 선택할 수 있어요.'
                  : null,
              selected: _alcohol == option,
              enabled:
                  option != AlcoholCompanionPreference.allSober ||
                  _canChooseAllSober,
              onTap: () => setState(() => _alcohol = option),
            ),
          const SizedBox(height: 20),
          _question('흡연자와 같은 미팅에 배정되어도 괜찮나요?', palette),
          for (final option in SmokingCompanionPreference.values)
            BlindMeetingOptionTile(
              label: option.label,
              selected: _smoking == option,
              onTap: () => setState(() => _smoking = option),
            ),
        ];
    }
  }

  Widget _question(String text, BlindMeetingPalette palette) => Padding(
    padding: const EdgeInsets.only(bottom: 16),
    child: Text(text, style: BlindMeetingText.title(palette.ink)),
  );

  Widget _profileSummary(BlindMeetingPalette palette) {
    final profile = widget.profile;
    final missing = profile.needsLifestyleUpdate;

    return BlindMeetingCard(
      background: palette.surfaceMuted,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '이미 등록한 프로필을 사용해요',
            style: BlindMeetingText.sectionTitle(palette.ink),
          ),
          const SizedBox(height: 10),
          _summaryRow(palette, '음주 정도', profile.drinkingLevel?.label ?? '미입력'),
          _summaryRow(palette, '흡연 여부', profile.smokingStatus?.label ?? '미입력'),
          _summaryRow(palette, 'MBTI', profile.mbti ?? '미입력'),
          _summaryRow(
            palette,
            '관심사',
            profile.interests.isEmpty
                ? '미입력'
                : profile.interests.take(5).join(', '),
          ),
          if (missing) ...[
            const SizedBox(height: 12),
            Text(
              '음주·흡연 정보가 없으면 조건 필터를 적용할 수 없어요. 프로필에서 먼저 보완해주세요.',
              style: BlindMeetingText.caption(palette.mutedRose),
            ),
            const SizedBox(height: 10),
            BlindMeetingSecondaryButton(
              label: '라이프스타일 수정하기',
              onPressed: () => Navigator.of(
                context,
              ).pushNamed(RouteNames.onboardingLifestyle),
            ),
          ],
        ],
      ),
    );
  }

  Widget _summaryRow(BlindMeetingPalette palette, String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 72,
            child: Text(
              label,
              style: BlindMeetingText.caption(palette.inkFaint),
            ),
          ),
          Expanded(
            child: Text(value, style: BlindMeetingText.caption(palette.ink)),
          ),
        ],
      ),
    );
  }
}
