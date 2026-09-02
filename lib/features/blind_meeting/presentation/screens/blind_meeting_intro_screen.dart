// =============================================================================
// 3:3 블라인드 취향 미팅 — 소개 / 자격 확인 화면
// 경로: lib/features/blind_meeting/presentation/screens/blind_meeting_intro_screen.dart
//
// 이미 신청했거나 매칭된 상태면 해당 단계로 자동 복구한다.
// (화면 메모리가 아니라 blindMeetingApplications/{uid} 문서가 단일 소스)
// =============================================================================

import 'package:firebase_core/firebase_core.dart';
import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/material.dart';

import '../../../../router/route_names.dart';
import '../../data/blind_meeting_analytics.dart';
import '../../data/blind_meeting_profile_snapshot.dart';
import '../../data/blind_meeting_repository.dart';
import '../../domain/blind_meeting_application.dart';
import '../../domain/blind_meeting_dna_progress.dart';
import '../../../onboarding/onboarding_route_args.dart';
import '../../../shop/services/heart_economy.dart';
import '../../../shop/widgets/heart_spend_confirmation.dart';
import '../blind_meeting_route_args.dart';
import '../theme/blind_meeting_palette.dart';
import '../widgets/blind_meeting_common.dart';
import '../widgets/blind_meeting_lifestyle_required_dialog.dart';
import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';

class BlindMeetingIntroScreen extends StatefulWidget {
  final BlindMeetingRepository? repository;
  final BlindMeetingAnalytics? analytics;

  /// AppRouter가 실제 앱에 사용할 때만 유료 DNA 진입 흐름을 켠다.
  /// 위젯 테스트·legacy 호출부는 기존 무료 진입 seam을 유지할 수 있다.
  final bool enablePaidDnaStart;

  const BlindMeetingIntroScreen({
    super.key,
    this.repository,
    this.analytics,
    this.enablePaidDnaStart = false,
  });

  @override
  State<BlindMeetingIntroScreen> createState() =>
      _BlindMeetingIntroScreenState();
}

class _BlindMeetingIntroScreenState extends State<BlindMeetingIntroScreen> {
  late final BlindMeetingRepository _repository =
      widget.repository ?? BlindMeetingRepository();
  late final BlindMeetingAnalytics _analytics =
      widget.analytics ?? BlindMeetingAnalytics();

  bool _loading = true;
  bool _openingInterestRegistration = false;
  bool _openingCampusLifeZoneRepair = false;
  bool _startingDna = false;
  String? _error;
  BlindMeetingProfileSnapshot? _profile;
  BlindMeetingApplication? _application;
  BlindMeetingDnaProgress? _dnaProgress;
  bool _campusLifeZoneEnforced = false;

  @override
  void initState() {
    super.initState();
    _analytics.log(BlindMeetingAnalyticsEvent.introViewed);
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final profile = await _repository.loadProfileSnapshot();
      // 생활권 정책이 실제로 적용됐는지는 서버가 정한다.
      final campusLifeZoneEnforced = await _repository
          .loadCampusLifeZoneEnforced();

      // 진행 중인 신청 조회는 선택 정보다. 아직 신청 이력이 없거나
      // 읽기 권한이 준비되지 않은 환경에서도 소개 화면은 열려야 하므로
      // 실패를 화면 전체 오류로 올리지 않는다.
      BlindMeetingApplication? application;
      try {
        application = await _repository.loadMyApplication();
      } on FirebaseException catch (error) {
        if (error.code != 'permission-denied') rethrow;
        debugPrint(
          '[BlindMeeting] 신청 상태를 읽을 수 없어요 (rules 배포 확인 필요): ${error.code}',
        );
        application = null;
      }

      // 결제 후 DNA 작성을 중단한 상태는 신청 문서와 별도로 저장된다.
      // 읽기 실패는 소개 화면 전체를 막지 않고 신규 작성으로 안내한다.
      BlindMeetingDnaProgress? dnaProgress;
      if (widget.enablePaidDnaStart) {
        try {
          dnaProgress = await _repository.loadMyDnaProgress();
        } catch (error) {
          debugPrint(
            '[BlindMeeting] DNA 작성 진행 상태를 읽을 수 없어요: ${PrivacyLogUtils.errorSummary(error)}',
          );
        }
      }

      if (!mounted) return;
      setState(() {
        _profile = profile;
        _application = application;
        _dnaProgress = dnaProgress;
        _campusLifeZoneEnforced = campusLifeZoneEnforced;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = '$error';
        _loading = false;
      });
    }
  }

  Future<void> _openCampusLifeZoneRepair() async {
    if (_openingCampusLifeZoneRepair) return;
    _openingCampusLifeZoneRepair = true;
    try {
      await Navigator.of(context).pushNamed(RouteNames.campusLifeZoneRepair);
      if (!mounted) return;
      // 저장 결과를 믿지 않고 Firestore 를 다시 읽어 eligibility 를 재계산한다.
      await _load();
    } finally {
      _openingCampusLifeZoneRepair = false;
    }
  }

  Future<void> _openInterestRegistration() async {
    if (_openingInterestRegistration) return;
    _openingInterestRegistration = true;
    try {
      await Navigator.of(context).pushNamed(
        RouteNames.onboardingInterestsSelection,
        arguments: const InterestsSelectionRouteArgs.prerequisiteRepair(),
      );
      if (!mounted) return;
      await _load();
    } finally {
      _openingInterestRegistration = false;
    }
  }

  Future<void> _startApplication({bool resume = false}) async {
    final profile = _profile;
    if (profile == null || _startingDna) return;

    // 유료 DNA 진입 흐름을 사용하지 않는 legacy/위젯 호출부는 기존
    // profile 인자 route를 유지한다. 실제 AppRouter에서는 서버 결제 경로만
    // 사용한다.
    if (!widget.enablePaidDnaStart) {
      _analytics.log(
        BlindMeetingAnalyticsEvent.dnaStarted,
        userId: profile.userId,
      );
      await Navigator.of(
        context,
      ).pushNamed(RouteNames.blindTasteMeetingDna, arguments: profile);
      if (mounted) await _load();
      return;
    }

    // 실제 앱은 DNA 시작 시 하트를 먼저 차감하므로, 누락된 생활정보를
    // 결제 확인창보다 앞에서 막아야 최종 신청 실패로 인한 차감을 방지한다.
    if (profile.needsLifestyleUpdate) {
      await showBlindMeetingLifestyleRequiredDialog(context);
      if (mounted) await _load();
      return;
    }

    if (resume) {
      setState(() {
        _startingDna = true;
        _error = null;
      });
      _analytics.log(
        BlindMeetingAnalyticsEvent.dnaStarted,
        userId: profile.userId,
        params: {'resumed': true},
      );
      try {
        await Navigator.of(context).pushNamed(
          RouteNames.blindTasteMeetingDna,
          arguments: BlindMeetingDnaRouteArgs(
            profile: profile,
            mode: BlindMeetingDnaMode.resumePaidDraft,
            heartCharged: true,
            persistProgress: true,
          ),
        );
        if (mounted) await _load();
      } finally {
        if (mounted) setState(() => _startingDna = false);
      }
      return;
    }

    final confirmed = await confirmHeartSpend(
      context,
      action: '정말로 미팅 DNA 작성을 시작하시겠습니까?',
      amount: HeartFeatureCosts.blindMeeting,
      chargeMessage:
          '${HeartFeatureCosts.label(HeartFeatureCosts.blindMeeting)} 하트가 먼저 차감됩니다.',
      detail: '작성을 끝내고 참가 신청하면 추가 차감 없이 이어서 처리돼요.',
    );
    if (!confirmed || !mounted) return;

    setState(() {
      _startingDna = true;
      _error = null;
    });
    try {
      final startResult = await _repository.startBlindMeetingDna();
      if (!mounted) return;
      _analytics.log(
        BlindMeetingAnalyticsEvent.dnaStarted,
        userId: profile.userId,
        params: {if (!startResult.charged) 'resumed': true},
      );
      await Navigator.of(context).pushNamed(
        RouteNames.blindTasteMeetingDna,
        arguments: BlindMeetingDnaRouteArgs(
          profile: profile,
          // 서버가 이미 진행 문서를 발견한 경우에도 답변을 잃지 않도록
          // 신규 wizard가 아니라 복구 wizard로 연다.
          mode: startResult.charged
              ? BlindMeetingDnaMode.create
              : BlindMeetingDnaMode.resumePaidDraft,
          heartCharged: true,
          persistProgress: true,
        ),
      );
      if (mounted) await _load();
    } on FirebaseFunctionsException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.code == 'resource-exhausted'
            ? '하트가 부족해요. ${HeartFeatureCosts.label(HeartFeatureCosts.blindMeeting)}가 필요해요.'
            : (error.message ?? '미팅 DNA 작성을 시작하지 못했어요.');
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = '미팅 DNA 작성을 시작하지 못했어요. 잠시 후 다시 시도해주세요.');
    } finally {
      if (mounted) setState(() => _startingDna = false);
    }
  }

  void _resume() {
    final application = _application;
    if (application == null) return;
    final meetingId = application.meetingId;
    if (meetingId != null && meetingId.isNotEmpty) {
      Navigator.of(context).pushNamed(
        RouteNames.blindTasteMeetingResult,
        arguments: BlindMeetingMeetingArgs(meetingId: meetingId),
      );
      return;
    }
    Navigator.of(context).pushNamed(RouteNames.blindTasteMeetingWaiting);
  }

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);

    return Scaffold(
      backgroundColor: palette.background,
      body: Column(
        children: [
          BlindMeetingAppBar(
            title: '블라인드 취향 미팅',
            onBack: () => Navigator.of(context).maybePop(),
          ),
          Expanded(child: _buildBody(palette)),
        ],
      ),
    );
  }

  Widget _buildBody(BlindMeetingPalette palette) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    final error = _error;
    if (error != null) {
      return SingleChildScrollView(
        padding: const EdgeInsets.only(top: 24, bottom: 40),
        child: BlindMeetingResponsiveBody(
          child: BlindMeetingErrorState(message: error, onRetry: _load),
        ),
      );
    }

    final profile = _profile;
    final application = _application;
    final dnaProgress = _dnaProgress;
    final needsInterestRepair = profile != null && profile.needsInterests;
    // 생활권이 비어 있어도 정책 적용 전이면 신청을 막지 않는다.
    final missingCampusLifeZone =
        profile != null && profile.needsCampusLifeZone;
    final needsCampusLifeZoneRepair =
        missingCampusLifeZone && _campusLifeZoneEnforced;
    final blockedReasons = <String>[
      if (profile == null) '로그인 정보를 확인할 수 없어요.',
      if (profile != null && !profile.schoolVerified) '학교 인증을 먼저 완료해주세요.',
      if (profile != null && profile.needsInterests) '온보딩에서 관심사를 먼저 등록해주세요.',
      if (needsCampusLifeZoneRepair) '생활권 설정을 먼저 완료해주세요.',
    ];

    return SingleChildScrollView(
      physics: const BouncingScrollPhysics(),
      padding: const EdgeInsets.only(top: 8, bottom: 40),
      child: BlindMeetingResponsiveBody(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '얼굴 공개 없이\n취향으로 만나는 3:3 미팅',
              style: BlindMeetingText.display(palette.ink),
            ),
            const SizedBox(height: 12),
            Text(
              '설레연이 미팅 목적, 관심사, 음주·흡연 성향과 대화 스타일을 바탕으로\n'
              '여섯 명을 두 팀으로 구성해요.',
              style: BlindMeetingText.body(palette.inkSoft),
            ),
            const SizedBox(height: 24),
            BlindMeetingCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '어떻게 진행되나요',
                    style: BlindMeetingText.sectionTitle(palette.ink),
                  ),
                  const SizedBox(height: 14),
                  for (final entry in const [
                    [
                      '1',
                      '비공개 미팅 DNA를 작성해요',
                      '대화 분위기, 대화 시작 성향, 미팅 목적, 음주·흡연 동석 선호',
                    ],
                    ['2', '가능한 날짜와 시간을 골라요', '여러 날짜를 함께 선택할 수 있어요'],
                    ['3', '설레연이 3:3 팀을 구성해요', '취향과 대화 균형을 함께 계산해요'],
                    ['4', '전원 수락과 보증금으로 확정해요', '노쇼를 막기 위한 개인별 보증금이에요'],
                    ['5', '단체 채팅에서 약속을 잡아요', '시간과 장소를 함께 정해요'],
                    ['6', '안전도장으로 만남을 확인해요', '도착 시 한 번, 종료 후 한 번'],
                    ['7', '미팅 후 비공개로 선택해요', '서로 선택한 경우에만 1:1 대화가 열려요'],
                  ])
                    Padding(
                      padding: const EdgeInsets.only(bottom: 14),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            width: 24,
                            height: 24,
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: palette.accent.withValues(alpha: 0.12),
                            ),
                            child: Text(
                              entry[0],
                              style: BlindMeetingText.caption(palette.accent),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  entry[1],
                                  style: BlindMeetingText.body(palette.ink),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  entry[2],
                                  style: BlindMeetingText.caption(
                                    palette.inkSoft,
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
            const SizedBox(height: 16),
            BlindMeetingCard(
              background: palette.surfaceMuted,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '무알코올 블라인드 취향 미팅',
                    style: BlindMeetingText.sectionTitle(palette.ink),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '술 없이 편안하게 이야기하고 싶은 대학생 여섯 명을 연결해드려요.\n'
                    '참가자 전원 비음주 선택, 카페·식당·보드게임 공간 중심, 음주 권유 없는 미팅이에요.',
                    style: BlindMeetingText.caption(palette.inkSoft),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            // 정책 적용 전에는 차단하지 않고 미리 설정하도록만 안내한다.
            if (missingCampusLifeZone && !_campusLifeZoneEnforced) ...[
              BlindMeetingCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '생활권 설정을 완료해주세요',
                      style: BlindMeetingText.sectionTitle(palette.ink),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '곧 신촌·송도 생활권을 기준으로 팀을 구성해요. '
                      '지금은 그대로 신청할 수 있고, 미리 설정해두면 준비돼요.',
                      style: BlindMeetingText.caption(palette.inkSoft),
                    ),
                    const SizedBox(height: 12),
                    BlindMeetingSecondaryButton(
                      label: '생활권 설정하러가기',
                      onPressed: _openCampusLifeZoneRepair,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
            ],
            if (blockedReasons.isNotEmpty)
              BlindMeetingCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '참가 자격 확인이 필요해요',
                      style: BlindMeetingText.sectionTitle(palette.ink),
                    ),
                    const SizedBox(height: 8),
                    for (final reason in blockedReasons)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 4),
                        child: Text(
                          '· $reason',
                          style: BlindMeetingText.caption(palette.attention),
                        ),
                      ),
                    if (needsInterestRepair) ...[
                      const SizedBox(height: 12),
                      BlindMeetingPrimaryButton(
                        label: '관심사 등록하러가기',
                        onPressed: _openInterestRegistration,
                      ),
                    ],
                    if (needsCampusLifeZoneRepair) ...[
                      const SizedBox(height: 12),
                      BlindMeetingPrimaryButton(
                        label: '생활권 설정하러가기',
                        onPressed: _openCampusLifeZoneRepair,
                      ),
                    ],
                  ],
                ),
              )
            else if (application != null && application.isActive)
              Column(
                children: [
                  BlindMeetingCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '이미 신청이 진행 중이에요',
                          style: BlindMeetingText.sectionTitle(palette.ink),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          application.stage.label,
                          style: BlindMeetingText.caption(palette.inkSoft),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  BlindMeetingPrimaryButton(
                    label: '진행 상황 보기',
                    onPressed: _resume,
                  ),
                ],
              )
            else if (dnaProgress?.isInProgress == true)
              Column(
                children: [
                  BlindMeetingCard(
                    background: palette.surfaceMuted,
                    child: Text(
                      '이미 결제한 미팅 DNA 작성이 있어요.\n작성한 내용은 그대로 보관되어 있어요.',
                      style: BlindMeetingText.caption(palette.inkSoft),
                    ),
                  ),
                  const SizedBox(height: 16),
                  BlindMeetingPrimaryButton(
                    label: '이어서 작성하기',
                    loading: _startingDna,
                    onPressed: () => _startApplication(resume: true),
                  ),
                ],
              )
            else
              Column(
                children: [
                  BlindMeetingPrimaryButton(
                    label: '미팅 DNA 작성하기',
                    loading: _startingDna,
                    onPressed: _startApplication,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '처음 시작할 때 ${HeartFeatureCosts.label(HeartFeatureCosts.blindMeeting)} 하트가 차감돼요.',
                    style: BlindMeetingText.caption(palette.inkSoft),
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }
}
