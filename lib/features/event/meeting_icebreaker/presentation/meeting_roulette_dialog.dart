// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 팝업
// 경로: lib/features/event/meeting_icebreaker/presentation/meeting_roulette_dialog.dart
//
// 구성
//   제목        어색할 땐 룰렛 한 번!
//   설명        여섯 명이 함께 할 게임을 골라드려요.
//   룰렛        고정 바늘 + 8칸 + 외곽 전구 + 중앙 허브
//   안전 안내    모든 게임은 자율 참여예요...
//   CTA         룰렛 돌리기
//
// 회전 중에는 실수로 닫히지 않게 막고, 회전이 끝나면 2초 뒤 설명 창을 연다.
// =============================================================================

import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';

import '../application/meeting_roulette_controller.dart';
import '../data/meeting_icebreaker_analytics.dart';
import '../data/meeting_icebreaker_repository.dart';
import '../domain/meeting_icebreaker_game.dart';
import '../domain/meeting_icebreaker_prompt.dart';
import '../domain/meeting_roulette_spin.dart';
import '../services/meeting_icebreaker_audio_service.dart';
import 'bomb_pass_timer_screen.dart';
import 'meeting_game_result_sheet.dart';
import 'meeting_icebreaker_keys.dart';
import 'meeting_icebreaker_palette.dart';
import 'meeting_roulette_wheel.dart';

/// 룰렛 팝업을 띄운다.
///
/// [entry]는 서버 검증을 통과한 결과여야 한다. 검증 없이 호출하지 않는다.
Future<void> showMeetingRouletteDialog({
  required BuildContext context,
  required MeetingIcebreakerEntry entry,
  MeetingIcebreakerRepository? repository,
  MeetingIcebreakerAnalytics? analytics,
  math.Random? random,
  MeetingIcebreakerAudioService? audioService,
}) {
  return showDialog<void>(
    context: context,
    // 바깥을 눌러 닫을 수 있지만, 회전 중에는 PopScope가 막는다.
    barrierDismissible: true,
    builder: (dialogContext) => MeetingRouletteDialog(
      entry: entry,
      repository: repository,
      analytics: analytics,
      random: random,
      audioService: audioService,
    ),
  );
}

class MeetingRouletteDialog extends StatefulWidget {
  const MeetingRouletteDialog({
    super.key,
    required this.entry,
    this.repository,
    this.analytics,
    this.random,
    this.audioService,
  });

  final MeetingIcebreakerEntry entry;
  final MeetingIcebreakerRepository? repository;
  final MeetingIcebreakerAnalytics? analytics;

  /// 테스트에서 당첨 칸을 고정하기 위해 주입한다.
  final math.Random? random;

  /// 폭탄 화면에 그대로 전달한다 (테스트에서 무음 구현 주입).
  final MeetingIcebreakerAudioService? audioService;

  @override
  State<MeetingRouletteDialog> createState() => _MeetingRouletteDialogState();
}

class _MeetingRouletteDialogState extends State<MeetingRouletteDialog>
    with TickerProviderStateMixin {
  MeetingRouletteController? _controller;
  late final AnimationController _hubPulse;
  late final MeetingIcebreakerAnalytics _analytics;
  late List<MeetingRouletteGame> _games;

  DateTime? _lastTickAt;
  bool _resultSheetOpen = false;
  bool _optedOut = false;
  bool _optOutBusy = false;
  bool _blockedDismissHintVisible = false;

  @override
  void initState() {
    super.initState();
    _analytics = widget.analytics ?? MeetingIcebreakerAnalytics();
    _optedOut = widget.entry.optedOut;
    _games = buildMeetingRouletteGames(
      alcoholFreeCopy: widget.entry.alcoholFreeCopy,
    );
    _hubPulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    );

    _analytics.log(
      MeetingIcebreakerAnalyticsEvent.rouletteShown,
      params: <String, dynamic>{
        if (widget.entry.meetingKind != null)
          'meeting_type': widget.entry.meetingKind!.wireName,
        'alcohol_free_copy': widget.entry.alcoholFreeCopy,
      },
    );
  }

  /// reduce motion 값은 MediaQuery가 필요해서 첫 build 시점에 controller를 만든다.
  ///
  /// 같은 AnimationController를 두 번 만들지 않도록 null 검사를 둔다.
  MeetingRouletteController _ensureController(BuildContext context) {
    final existing = _controller;
    if (existing != null) return existing;

    final controller =
        MeetingRouletteController(
            vsync: this,
            games: _games,
            random: widget.random,
            reduceMotion: MediaQuery.disableAnimationsOf(context),
          )
          ..onSegmentTick = _handleSegmentTick
          ..onRevealReady = _handleRevealReady;
    controller.addListener(_onControllerChanged);
    _controller = controller;
    return controller;
  }

  @override
  void dispose() {
    _controller?.removeListener(_onControllerChanged);
    _controller?.dispose();
    _hubPulse.dispose();
    super.dispose();
  }

  void _onControllerChanged() {
    if (!mounted) return;
    final controller = _controller;
    if (controller != null) {
      if (controller.isHighlighting && !_hubPulse.isAnimating) {
        _hubPulse.repeat(reverse: true);
      } else if (!controller.isHighlighting && _hubPulse.isAnimating) {
        _hubPulse.stop();
        _hubPulse.value = 0;
      }
    }
    setState(() {});
  }

  /// 회전 시작·종료와 당첨 결과를 screen reader에 알린다.
  void _announce(String message) {
    if (!mounted) return;
    SemanticsService.sendAnnouncement(
      View.of(context),
      message,
      Directionality.of(context),
    );
  }

  /// 칸 경계를 지날 때 아주 짧은 tick haptic. 과도한 진동은 쓰지 않는다.
  void _handleSegmentTick() {
    final now = DateTime.now();
    final last = _lastTickAt;
    if (last != null && now.difference(last).inMilliseconds < 45) return;
    _lastTickAt = now;
    HapticFeedback.selectionClick();
  }

  void _handleSpin() {
    final controller = _controller;
    if (controller == null || !controller.canSpin) return;
    _blockedDismissHintVisible = false;
    controller.spin();
    _announce('룰렛이 돌아가요.');
    _analytics.log(
      MeetingIcebreakerAnalyticsEvent.rouletteSpinStarted,
      params: <String, dynamic>{
        if (widget.entry.meetingKind != null)
          'meeting_type': widget.entry.meetingKind!.wireName,
        'reduce_motion': controller.reduceMotion,
      },
    );
  }

  /// 회전이 끝나고 2초 뒤에 호출된다.
  ///
  /// 화면이 이미 닫혔으면 dialog를 열지 않는다.
  Future<void> _handleRevealReady(MeetingRouletteGame game) async {
    if (!mounted) return;
    if (_resultSheetOpen) return;

    _announce('${game.title} 당첨.');
    _analytics.log(
      MeetingIcebreakerAnalyticsEvent.rouletteSpinCompleted,
      params: <String, dynamic>{
        'game_type': game.type.name,
        'spin_duration_bucket': meetingRouletteSpinDurationBucket(
          _controller?.spinDuration ?? kMeetingRouletteSpinDuration,
        ),
      },
    );

    _analytics.log(
      MeetingIcebreakerAnalyticsEvent.gameResultShown,
      params: <String, dynamic>{'game_type': game.type.name},
    );

    _resultSheetOpen = true;
    final palette = MeetingIcebreakerPalette.of(context);
    final action = await showMeetingGameResultSheet(
      context: context,
      game: game,
      palette: palette,
      bombPassEnabled: widget.entry.bombPassEnabled,
    );
    _resultSheetOpen = false;
    if (!mounted) return;

    switch (action) {
      case MeetingGameResultAction.openBombTimer:
        await _openBombTimer();
      case MeetingGameResultAction.spinAgain:
        _controller?.reset();
      case MeetingGameResultAction.close:
        if (mounted) Navigator.of(context).pop();
      case null:
        // sheet를 스와이프로 닫은 경우: 룰렛으로 돌아간다.
        _controller?.reset();
    }
  }

  Future<void> _openBombTimer() async {
    if (!mounted) return;
    await Navigator.of(context, rootNavigator: true).push(
      MaterialPageRoute<void>(
        builder: (_) => BombPassTimerScreen(
          args: BombPassTimerArgs(meetingKind: widget.entry.meetingKind),
          audioService: widget.audioService,
          analytics: _analytics,
        ),
      ),
    );
    if (!mounted) return;
    _controller?.reset();
  }

  Future<void> _toggleOptOut() async {
    final sessionId = widget.entry.sessionId;
    final repository = widget.repository;
    if (sessionId == null || repository == null || _optOutBusy) return;

    setState(() => _optOutBusy = true);
    final next = !_optedOut;
    final applied = await repository.setOptOut(
      sessionId: sessionId,
      optedOut: next,
    );
    if (!mounted) return;
    setState(() {
      _optedOut = applied;
      _optOutBusy = false;
    });

    if (applied == next && next) {
      _analytics.log(
        MeetingIcebreakerAnalyticsEvent.promptOptedOut,
        params: <String, dynamic>{
          if (widget.entry.meetingKind != null)
            'meeting_type': widget.entry.meetingKind!.wireName,
        },
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final palette = MeetingIcebreakerPalette.of(context);
    final controller = _ensureController(context);
    final winner = controller.winningGame;
    final showAlcoholNotice = _games.any((game) => game.mentionsAlcohol);

    return PopScope(
      // 회전 중에는 실수로 닫히지 않게 한다.
      canPop: !controller.isSpinning,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop || !mounted) return;
        setState(() => _blockedDismissHintVisible = true);
      },
      child: Dialog(
        key: MeetingIcebreakerKeys.rouletteDialog,
        backgroundColor: palette.surface,
        insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(kMeetingIcebreakerDialogRadius),
          side: BorderSide(color: palette.border),
        ),
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            maxWidth: kMeetingIcebreakerMaxWidth,
          ),
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(20, 22, 20, 18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Text(
                  '어색할 땐 룰렛 한 번!',
                  textAlign: TextAlign.center,
                  style: MeetingIcebreakerText.title(palette.ink),
                ),
                const SizedBox(height: 6),
                Text(
                  '여섯 명이 함께 할 게임을 골라드려요.',
                  textAlign: TextAlign.center,
                  style: MeetingIcebreakerText.body(palette.inkSoft),
                ),
                const SizedBox(height: 16),
                _buildWheel(palette, controller),
                const SizedBox(height: 12),
                _buildSegmentLegend(palette, controller),
                const SizedBox(height: 10),
                _buildWinnerBanner(palette, controller, winner),
                const SizedBox(height: 12),
                _buildNotice(
                  palette: palette,
                  text: kMeetingRouletteParticipationNotice,
                  muted: false,
                ),
                if (showAlcoholNotice) ...<Widget>[
                  const SizedBox(height: 8),
                  _buildNotice(
                    key: MeetingIcebreakerKeys.alcoholNotice,
                    palette: palette,
                    text: kMeetingRouletteAlcoholNotice,
                    muted: true,
                  ),
                ],
                if (_blockedDismissHintVisible && controller.isSpinning) ...[
                  const SizedBox(height: 8),
                  Text(
                    '회전이 끝나면 닫을 수 있어요.',
                    textAlign: TextAlign.center,
                    style: MeetingIcebreakerText.caption(palette.accentDeep),
                  ),
                ],
                const SizedBox(height: 16),
                _buildSpinButton(palette, controller),
                if (widget.entry.sessionId != null &&
                    widget.repository != null) ...<Widget>[
                  const SizedBox(height: 6),
                  _buildOptOutButton(palette),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildWheel(
    MeetingIcebreakerPalette palette,
    MeetingRouletteController controller,
  ) {
    final semanticsLabel = <String>[
      '아이스브레이킹 룰렛. 칸 8개.',
      for (final game in _games) '${game.number}번 ${game.title}.',
    ].join(' ');

    final stateLabel = switch (controller.phase) {
      MeetingRoulettePhase.idle => '돌릴 준비가 됐어요.',
      MeetingRoulettePhase.spinning => '룰렛이 돌아가고 있어요.',
      MeetingRoulettePhase.celebrating || MeetingRoulettePhase.revealed =>
        '${controller.winningGame?.title ?? ''} 당첨.',
    };

    return Semantics(
      key: MeetingIcebreakerKeys.rouletteWheel,
      label: semanticsLabel,
      value: stateLabel,
      liveRegion: true,
      child: LayoutBuilder(
        builder: (context, constraints) {
          // 작은 화면에서도 잘리지 않게 가로 폭에 맞춘다.
          final diameter = math.min(
            constraints.maxWidth.isFinite ? constraints.maxWidth : 268.0,
            268.0,
          );
          return AnimatedBuilder(
            animation: Listenable.merge(<Listenable>[controller, _hubPulse]),
            builder: (context, _) {
              final rotation = controller.rotation;
              // 바늘의 미세한 흔들림: 칸 경계를 지날 때 살짝 튕긴다.
              final fraction = (rotation / kMeetingRouletteSegmentSweep) % 1.0;
              final nudge = controller.isSpinning && !controller.reduceMotion
                  ? math.sin(fraction * 2 * math.pi) * 0.045
                  : 0.0;
              return Center(
                child: MeetingRouletteWheel(
                  games: _games,
                  rotation: rotation,
                  palette: palette,
                  winningIndex: controller.winningIndex,
                  isHighlighting: controller.isHighlighting,
                  hubPulse: _hubPulse.value,
                  pointerNudge: nudge,
                  diameter: diameter,
                ),
              );
            },
          );
        },
      ),
    );
  }

  /// 8칸 번호 표시.
  ///
  /// 색만으로 결과를 알리지 않기 위해 번호와 semantic label을 함께 제공한다.
  Widget _buildSegmentLegend(
    MeetingIcebreakerPalette palette,
    MeetingRouletteController controller,
  ) {
    return Wrap(
      alignment: WrapAlignment.center,
      spacing: 6,
      runSpacing: 6,
      children: <Widget>[
        for (final game in _games)
          Semantics(
            key: MeetingIcebreakerKeys.segmentSemantics(game.index),
            label: '${game.number}번 ${game.title}',
            selected:
                controller.isHighlighting &&
                controller.winningIndex == game.index,
            // 번호 텍스트가 label 뒤에 다시 읽히지 않게 한다.
            excludeSemantics: true,
            child: Container(
              width: 28,
              height: 28,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color:
                    controller.isHighlighting &&
                        controller.winningIndex == game.index
                    ? palette.accent
                    : palette.surfaceMuted,
                shape: BoxShape.circle,
                border: Border.all(color: palette.border),
              ),
              child: Text(
                '${game.number}',
                style: MeetingIcebreakerText.caption(
                  controller.isHighlighting &&
                          controller.winningIndex == game.index
                      ? Colors.white
                      : palette.inkSoft,
                ),
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildWinnerBanner(
    MeetingIcebreakerPalette palette,
    MeetingRouletteController controller,
    MeetingRouletteGame? winner,
  ) {
    if (!controller.isHighlighting || winner == null) {
      return const SizedBox(height: 4);
    }
    return Container(
      key: MeetingIcebreakerKeys.winnerBanner,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: palette.surfaceMuted,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: palette.accent.withValues(alpha: 0.45)),
      ),
      child: Text(
        '당첨 ${winner.number}번 · ${winner.title}',
        textAlign: TextAlign.center,
        style: MeetingIcebreakerText.body(palette.accentDeep),
      ),
    );
  }

  Widget _buildNotice({
    Key? key,
    required MeetingIcebreakerPalette palette,
    required String text,
    required bool muted,
  }) {
    return Container(
      key: key,
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      decoration: BoxDecoration(
        color: muted ? palette.surfaceMuted : palette.sage,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Text(
        text,
        style: MeetingIcebreakerText.caption(
          muted ? palette.accentDeep : palette.inkSoft,
        ),
      ),
    );
  }

  Widget _buildSpinButton(
    MeetingIcebreakerPalette palette,
    MeetingRouletteController controller,
  ) {
    final enabled = controller.canSpin;
    return SizedBox(
      height: kMeetingIcebreakerCtaHeight,
      child: FilledButton(
        key: MeetingIcebreakerKeys.spinButton,
        // 회전 중에는 비활성이라 중복 tap이 들어오지 않는다.
        onPressed: enabled ? _handleSpin : null,
        style: FilledButton.styleFrom(
          backgroundColor: palette.accent,
          foregroundColor: Colors.white,
          disabledBackgroundColor: palette.rim,
          disabledForegroundColor: palette.accentDeep,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(kMeetingIcebreakerCardRadius),
          ),
        ),
        child: FittedBox(
          child: Text(
            controller.isSpinning ? '돌아가고 있어요…' : '룰렛 돌리기',
            style: MeetingIcebreakerText.cta(
              enabled ? Colors.white : palette.accentDeep,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildOptOutButton(MeetingIcebreakerPalette palette) {
    return TextButton(
      key: MeetingIcebreakerKeys.optOutButton,
      onPressed: _optOutBusy ? null : _toggleOptOut,
      style: TextButton.styleFrom(foregroundColor: palette.inkFaint),
      child: Column(
        children: <Widget>[
          Text(
            _optedOut
                ? kMeetingIcebreakerOptInLabel
                : kMeetingIcebreakerOptOutLabel,
            textAlign: TextAlign.center,
            style: MeetingIcebreakerText.caption(palette.inkFaint),
          ),
          Text(
            kMeetingIcebreakerOptOutHint,
            textAlign: TextAlign.center,
            style: MeetingIcebreakerText.caption(
              palette.inkFaint.withValues(alpha: 0.8),
            ),
          ),
        ],
      ),
    );
  }
}
