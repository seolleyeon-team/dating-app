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

import 'dart:async';

import 'package:flutter/material.dart';

import '../../../../router/route_names.dart';
import '../../data/blind_meeting_analytics.dart';
import '../../data/blind_meeting_profile_snapshot.dart';
import '../../data/blind_meeting_repository.dart';
import '../../domain/blind_meeting_enums.dart';
import '../blind_meeting_route_args.dart';
import '../theme/blind_meeting_palette.dart';
import '../widgets/blind_meeting_common.dart';

class BlindMeetingDnaWizardScreen extends StatefulWidget {
  final BlindMeetingProfileSnapshot profile;
  final BlindMeetingDnaMode mode;
  final bool heartCharged;
  final bool persistProgress;
  final BlindMeetingRepository? repository;
  final BlindMeetingAnalytics? analytics;

  const BlindMeetingDnaWizardScreen({
    super.key,
    required this.profile,
    this.mode = BlindMeetingDnaMode.create,
    this.heartCharged = false,
    this.persistProgress = false,
    this.repository,
    this.analytics,
  });

  @override
  State<BlindMeetingDnaWizardScreen> createState() =>
      _BlindMeetingDnaWizardScreenState();
}

class _BlindMeetingDnaWizardScreenState
    extends State<BlindMeetingDnaWizardScreen> {
  static const int _totalSteps = 4;

  late final BlindMeetingRepository _repository =
      widget.repository ?? BlindMeetingRepository();

  int _step = 1;
  ConversationAtmosphere? _atmosphere;
  ConversationInitiative? _initiative;
  MeetingPurpose? _purpose;
  AlcoholCompanionPreference? _alcohol;
  SmokingCompanionPreference? _smoking;
  bool _loadingExistingDna = false;
  String? _existingDnaError;

  @override
  void initState() {
    super.initState();
    if (widget.mode == BlindMeetingDnaMode.editExistingApplication) {
      _restoreExistingDna();
    } else if (widget.mode == BlindMeetingDnaMode.resumePaidDraft) {
      _restorePaidDraft();
    }
  }

  bool get _shouldPersistProgress =>
      widget.persistProgress &&
      widget.heartCharged &&
      widget.mode != BlindMeetingDnaMode.editExistingApplication;

  bool get _canGoNext => switch (_step) {
    1 =>
      !_loadingExistingDna && _existingDnaError == null && _atmosphere != null,
    2 =>
      !_loadingExistingDna && _existingDnaError == null && _initiative != null,
    3 => !_loadingExistingDna && _existingDnaError == null && _purpose != null,
    4 =>
      !_loadingExistingDna &&
          _existingDnaError == null &&
          _alcohol != null &&
          _smoking != null,
    _ => false,
  };

  /// 전원 비음주는 프로필상 비음주인 경우에만 선택할 수 있다.
  bool get _canChooseAllSober => widget.profile.drinkingLevel?.isSober ?? false;

  Future<void> _restoreExistingDna() async {
    if (_loadingExistingDna) return;
    setState(() {
      _loadingExistingDna = true;
      _existingDnaError = null;
    });
    try {
      final dna = await _repository.loadMyDna();
      if (!mounted) return;
      if (dna == null) {
        throw StateError('기존 미팅 DNA를 불러오지 못했어요.');
      }
      setState(() {
        _atmosphere = dna.conversationAtmosphere;
        _initiative = dna.conversationInitiative;
        _purpose = dna.meetingPurpose;
        _alcohol = dna.alcoholCompanionPreference;
        _smoking = dna.smokingCompanionPreference;
        _loadingExistingDna = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loadingExistingDna = false;
        _existingDnaError = '기존 미팅 DNA를 불러오지 못했어요. 다시 시도해주세요.';
      });
    }
  }

  Future<void> _restorePaidDraft() async {
    if (_loadingExistingDna) return;
    setState(() {
      _loadingExistingDna = true;
      _existingDnaError = null;
    });
    try {
      final progress = await _repository.loadMyDnaProgress();
      if (!mounted) return;
      if (progress == null || !progress.isInProgress) {
        throw StateError('진행 중인 미팅 DNA를 찾을 수 없어요.');
      }
      setState(() {
        _atmosphere = progress.atmosphere;
        _initiative = progress.initiative;
        _purpose = progress.purpose;
        _alcohol = progress.alcoholPreference;
        _smoking = progress.smokingPreference;
        _loadingExistingDna = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loadingExistingDna = false;
        _existingDnaError = '작성 중인 미팅 DNA를 불러오지 못했어요. 다시 시도해주세요.';
      });
    }
  }

  void _persistProgressField(String key, String value) {
    if (!_shouldPersistProgress) return;
    unawaited(
      _repository.saveBlindMeetingDnaDraft({key: value}).catchError((error) {
        // 최종 제출은 전체 답변을 다시 보내므로 일시적인 진행 저장
        // 실패가 작성 화면을 막지는 않는다.
        debugPrint('[BlindMeeting] DNA 진행 저장 실패: $error');
      }),
    );
  }

  void _next() {
    if (!_canGoNext) return;
    if (_step < _totalSteps) {
      setState(() => _step++);
      return;
    }
    (widget.analytics ?? BlindMeetingAnalytics()).log(
      BlindMeetingAnalyticsEvent.dnaCompleted,
      userId: widget.profile.userId,
    );
    final draft = BlindMeetingDnaDraft(
      profile: widget.profile,
      mode: widget.mode,
      atmosphere: _atmosphere!,
      initiative: _initiative!,
      purpose: _purpose!,
      alcoholPreference: _alcohol!,
      smokingPreference: _smoking!,
      heartCharged: widget.heartCharged,
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
                    if (_loadingExistingDna)
                      const Center(child: CircularProgressIndicator())
                    else if (_existingDnaError != null)
                      BlindMeetingErrorState(
                        message: _existingDnaError!,
                        onRetry:
                            widget.mode == BlindMeetingDnaMode.resumePaidDraft
                            ? _restorePaidDraft
                            : _restoreExistingDna,
                      )
                    else
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
              onTap: () {
                setState(() => _atmosphere = option);
                _persistProgressField('conversationAtmosphere', option.name);
              },
            ),
        ];
      case 2:
        return [
          _question('새로운 사람 앞에서 먼저 이야기를 시작하는 편인가요?', palette),
          for (final option in ConversationInitiative.values)
            BlindMeetingOptionTile(
              label: option.label,
              selected: _initiative == option,
              onTap: () {
                setState(() => _initiative = option);
                _persistProgressField('conversationInitiative', option.name);
              },
            ),
        ];
      case 3:
        return [
          _question('이번 미팅에서 어떤 만남을 기대하나요?', palette),
          for (final option in MeetingPurpose.values)
            BlindMeetingOptionTile(
              label: option.label,
              selected: _purpose == option,
              onTap: () {
                setState(() => _purpose = option);
                _persistProgressField('meetingPurpose', option.name);
              },
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
              onTap: () {
                setState(() => _alcohol = option);
                _persistProgressField(
                  'alcoholCompanionPreference',
                  option.name,
                );
              },
            ),
          const SizedBox(height: 20),
          _question('흡연자와 같은 미팅에 배정되어도 괜찮나요?', palette),
          for (final option in SmokingCompanionPreference.values)
            BlindMeetingOptionTile(
              label: option.label,
              selected: _smoking == option,
              onTap: () {
                setState(() => _smoking = option);
                _persistProgressField(
                  'smokingCompanionPreference',
                  option.name,
                );
              },
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
              style: BlindMeetingText.caption(palette.attention),
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
