// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 폭탄 돌리기 타이머 화면
// 경로: lib/features/event/meeting_icebreaker/presentation/bomb_pass_timer_screen.dart
//
// 숨겨진 시간(1~15초)은 화면이 만들어질 때 뽑고 절대 노출하지 않는다.
//   - 화면에는 항상 `??:??`
//   - progress bar로 남은 시간을 추정할 수 없다
//   - semantics는 `숨겨진 타이머`로만 읽힌다
//   - analytics·로그에도 실제 초를 남기지 않는다
//
// 앱이 완전히 종료된 뒤 알람을 울리는 기능은 만들지 않는다.
// 사용자가 이 화면에 있는 동안 진행되는 짧은 인앱 게임이다.
// =============================================================================

import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../application/bomb_pass_timer_controller.dart';
import '../data/meeting_icebreaker_analytics.dart';
import '../domain/bomb_pass_timer.dart';
import '../domain/meeting_icebreaker_prompt.dart';
import '../services/meeting_icebreaker_audio_service.dart';
import 'bomb_illustration.dart';
import 'meeting_icebreaker_keys.dart';
import 'meeting_icebreaker_palette.dart';

/// 폭탄 돌리기 화면 인자.
class BombPassTimerArgs {
  const BombPassTimerArgs({this.meetingKind});

  /// analytics용 미팅 종류. 개인정보가 아니다.
  final MeetingIcebreakerMeetingKind? meetingKind;
}

class BombPassTimerScreen extends StatefulWidget {
  const BombPassTimerScreen({
    super.key,
    this.args,
    this.audioService,
    this.analytics,
    this.random,
    this.clock,
  });

  final BombPassTimerArgs? args;

  /// 테스트에서 무음 구현을 주입한다.
  final MeetingIcebreakerAudioService? audioService;
  final MeetingIcebreakerAnalytics? analytics;

  /// 숨겨진 시간을 고정하고 싶을 때 주입한다 (테스트 전용).
  final math.Random? random;
  final BombPassClock? clock;

  @override
  State<BombPassTimerScreen> createState() => _BombPassTimerScreenState();
}

class _BombPassTimerScreenState extends State<BombPassTimerScreen>
    with TickerProviderStateMixin, WidgetsBindingObserver {
  late final BombPassTimerController _controller;
  late final MeetingIcebreakerAudioService _audio;
  late final MeetingIcebreakerAnalytics _analytics;
  late final AnimationController _fuse;
  late final AnimationController _blast;

  bool _startPressed = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);

    _analytics = widget.analytics ?? MeetingIcebreakerAnalytics();
    _audio =
        widget.audioService ??
        MeetingIcebreakerAudio.create(onFailure: _reportAudioFailure);

    _controller =
        BombPassTimerController(random: widget.random, clock: widget.clock)
          ..onTickingStart = _handleTickingStart
          ..onTickingStop = _handleTickingStop
          ..onExploded = _handleExploded;
    _controller.addListener(_onControllerChanged);

    _fuse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    _blast = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 720),
    );

    _analytics.log(
      MeetingIcebreakerAnalyticsEvent.bombTimerOpened,
      params: <String, dynamic>{
        if (widget.args?.meetingKind != null)
          'meeting_type': widget.args!.meetingKind!.wireName,
      },
    );
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller.removeListener(_onControllerChanged);
    _controller.dispose();
    _fuse.dispose();
    _blast.dispose();
    // 화면을 떠난 뒤 소리가 남지 않게 한다.
    _audio.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      // background에 있는 동안 deadline이 지났다면 즉시 폭발 상태로 전환한다.
      _controller.handleAppResumed();
      return;
    }
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive) {
      _audio.stopTicking();
    }
  }

  bool get _reduceMotion => MediaQuery.disableAnimationsOf(context);

  void _onControllerChanged() {
    if (!mounted) return;
    setState(() {});
  }

  void _reportAudioFailure(MeetingIcebreakerAudioStage stage) {
    // 실제 실패 여부만 기록한다. 성공으로 위장하지 않는다.
    _analytics.log(
      MeetingIcebreakerAnalyticsEvent.audioFailed,
      params: <String, dynamic>{'audio_stage': stage.name},
    );
  }

  void _handleTickingStart() {
    _audio.startTicking();
    if (!_reduceMotion) {
      _fuse.repeat(reverse: true);
    }
  }

  void _handleTickingStop() {
    _audio.stopTicking();
    _fuse.stop();
  }

  void _handleExploded() {
    _audio.playExplosion();
    if (!mounted) return;
    _blast
      ..reset()
      ..forward();
    HapticFeedback.heavyImpact();
    _analytics.log(
      MeetingIcebreakerAnalyticsEvent.bombTimerExploded,
      params: <String, dynamic>{
        if (widget.args?.meetingKind != null)
          'meeting_type': widget.args!.meetingKind!.wireName,
      },
    );
  }

  void _handleStart() {
    if (_startPressed || !_controller.isReady) return;
    setState(() => _startPressed = true);
    _analytics.log(
      MeetingIcebreakerAnalyticsEvent.bombTimerStarted,
      params: <String, dynamic>{
        if (widget.args?.meetingKind != null)
          'meeting_type': widget.args!.meetingKind!.wireName,
        'reduce_motion': _reduceMotion,
      },
    );
    _controller.start();
  }

  void _handleRestart() {
    _blast.reset();
    setState(() => _startPressed = false);
    // 이전 숨겨진 시간을 재사용하지 않고 새로 뽑는다.
    _controller.restart();
  }

  @override
  Widget build(BuildContext context) {
    final palette = MeetingIcebreakerPalette.of(context);
    final phase = _controller.phase;

    return PopScope(
      canPop: true,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop) _controller.stopForNavigation();
      },
      child: Scaffold(
        key: MeetingIcebreakerKeys.bombScreen,
        backgroundColor: palette.background,
        appBar: AppBar(
          backgroundColor: palette.background,
          surfaceTintColor: Colors.transparent,
          elevation: 0,
          foregroundColor: palette.ink,
          title: Text(
            '폭탄 돌리기',
            style: MeetingIcebreakerText.title(palette.ink),
          ),
        ),
        body: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(
                maxWidth: kMeetingIcebreakerMaxWidth,
              ),
              child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(
                  horizontal: 20,
                  vertical: 16,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    _buildIllustration(palette),
                    const SizedBox(height: 20),
                    _buildHiddenTimer(palette),
                    const SizedBox(height: 14),
                    _buildStatus(palette, phase),
                    const SizedBox(height: 24),
                    _buildCta(palette, phase),
                    if (_audio.lastPlaybackFailed) ...<Widget>[
                      const SizedBox(height: 12),
                      Text(
                        '소리를 재생할 수 없어 화면으로만 진행돼요.',
                        textAlign: TextAlign.center,
                        style: MeetingIcebreakerText.caption(palette.inkFaint),
                      ),
                    ],
                    const SizedBox(height: 8),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildIllustration(MeetingIcebreakerPalette palette) {
    return AnimatedBuilder(
      animation: Listenable.merge(<Listenable>[_fuse, _blast]),
      builder: (context, _) {
        final blast = _blast.value;
        final shake = (!_reduceMotion && blast > 0 && blast < 0.45)
            ? math.sin(blast * math.pi * 10) * 6 * (1 - blast / 0.45)
            : 0.0;
        return Center(
          child: BombIllustration(
            palette: palette,
            size: 176,
            fuseGlow: _controller.isRunning ? (0.35 + _fuse.value * 0.65) : 0,
            explosionProgress: blast,
            shake: shake,
          ),
        );
      },
    );
  }

  /// 실제 시간은 절대 나오지 않는다. 항상 마스킹 문자열이다.
  Widget _buildHiddenTimer(MeetingIcebreakerPalette palette) {
    return Semantics(
      key: MeetingIcebreakerKeys.bombHiddenTimer,
      label: kBombPassHiddenTimerSemanticLabel,
      // 실제 남은 시간을 value로도 노출하지 않는다.
      excludeSemantics: true,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 18),
        decoration: BoxDecoration(
          color: palette.surface,
          borderRadius: BorderRadius.circular(kMeetingIcebreakerCardRadius),
          border: Border.all(color: palette.border),
        ),
        child: Text(
          kBombPassHiddenTimerMask,
          textAlign: TextAlign.center,
          style: MeetingIcebreakerText.resultNumber(palette.accentDeep),
        ),
      ),
    );
  }

  Widget _buildStatus(MeetingIcebreakerPalette palette, BombPassPhase phase) {
    final String text;
    switch (phase) {
      case BombPassPhase.ready:
        text = '누구에게서 터질지는 아무도 몰라요!';
      case BombPassPhase.running:
        text = '폭탄을 옆 사람에게 넘겨보세요.';
      case BombPassPhase.exploded:
        text = '$kBombPassExplodedTitle $kBombPassExplodedBody';
    }

    return Semantics(
      liveRegion: true,
      child: Column(
        key: MeetingIcebreakerKeys.bombStatusText,
        children: <Widget>[
          if (phase == BombPassPhase.exploded)
            Padding(
              key: MeetingIcebreakerKeys.bombExplosion,
              padding: const EdgeInsets.only(bottom: 6),
              child: Text(
                kBombPassExplodedTitle,
                textAlign: TextAlign.center,
                style: MeetingIcebreakerText.resultTitle(palette.accentDeep),
              ),
            ),
          Text(
            phase == BombPassPhase.exploded ? kBombPassExplodedBody : text,
            textAlign: TextAlign.center,
            style: MeetingIcebreakerText.body(palette.inkSoft),
          ),
        ],
      ),
    );
  }

  Widget _buildCta(MeetingIcebreakerPalette palette, BombPassPhase phase) {
    if (phase == BombPassPhase.exploded) {
      return SizedBox(
        height: kMeetingIcebreakerCtaHeight,
        child: FilledButton(
          key: MeetingIcebreakerKeys.bombRestartButton,
          onPressed: _handleRestart,
          style: FilledButton.styleFrom(
            backgroundColor: palette.accent,
            foregroundColor: Colors.white,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(kMeetingIcebreakerCardRadius),
            ),
          ),
          child: FittedBox(
            child: Text(
              '다시 시작하기',
              style: MeetingIcebreakerText.cta(Colors.white),
            ),
          ),
        ),
      );
    }

    final running = phase == BombPassPhase.running;
    return SizedBox(
      height: kMeetingIcebreakerCtaHeight,
      child: FilledButton(
        key: MeetingIcebreakerKeys.bombStartButton,
        // 진행 중에는 비활성이라 중복 입력이 불가능하다.
        onPressed: running ? null : _handleStart,
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
            running ? '게임 진행 중…' : '게임 시작하기',
            style: MeetingIcebreakerText.cta(
              running ? palette.accentDeep : Colors.white,
            ),
          ),
        ),
      ),
    );
  }
}
