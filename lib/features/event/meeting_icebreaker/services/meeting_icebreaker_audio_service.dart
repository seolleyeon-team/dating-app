// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 효과음 서비스
// 경로: lib/features/event/meeting_icebreaker/services/meeting_icebreaker_audio_service.dart
//
// 규칙
//  - 로컬 asset만 재생한다 (네트워크 다운로드 없음)
//  - 사용자가 `게임 시작하기`를 누른 뒤에만 재생한다
//    (Flutter Web의 autoplay 제한 때문에도 이 순서가 필요하다)
//  - 폭발 순간 / 화면 이탈 / dispose 시 즉시 중단한다
//  - player를 두 개 이상 겹쳐 만들지 않는다
//  - 재생 실패가 crash로 이어지지 않고, 시각적 게임은 그대로 진행된다
//  - 실패는 PII 없이 telemetry로만 남긴다
// =============================================================================

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';

/// 효과음 asset 경로 (pubspec assets에 등록되어 있어야 한다).
const String kBombTickLoopAsset = 'assets/audio/bomb_tick_loop.wav';
const String kBombExplosionAsset = 'assets/audio/bomb_explosion.wav';

/// 실패 지점 (analytics의 audio_stage 값).
enum MeetingIcebreakerAudioStage { ticking, explosion, dispose }

typedef MeetingIcebreakerAudioFailureReporter =
    void Function(MeetingIcebreakerAudioStage stage);

/// 폭탄 게임 효과음 인터페이스.
///
/// 위젯 테스트에서는 [SilentMeetingIcebreakerAudioService]를 주입해
/// 플랫폼 채널 없이 동작을 검증한다.
abstract class MeetingIcebreakerAudioService {
  Future<void> startTicking();

  Future<void> stopTicking();

  Future<void> playExplosion();

  Future<void> dispose();

  /// 마지막 재생 시도가 실패했는지. UI에서 안내 문구를 바꾸는 데 쓴다.
  bool get lastPlaybackFailed;
}

/// 소리를 내지 않는 구현 (테스트 / 오디오 비활성 환경).
class SilentMeetingIcebreakerAudioService
    implements MeetingIcebreakerAudioService {
  SilentMeetingIcebreakerAudioService({this.failing = false});

  /// true면 모든 재생이 실패한 것처럼 동작한다 (fallback 경로 테스트용).
  final bool failing;

  int startTickingCalls = 0;
  int stopTickingCalls = 0;
  int explosionCalls = 0;
  int disposeCalls = 0;

  @override
  bool get lastPlaybackFailed => failing;

  @override
  Future<void> startTicking() async {
    startTickingCalls += 1;
  }

  @override
  Future<void> stopTicking() async {
    stopTickingCalls += 1;
  }

  @override
  Future<void> playExplosion() async {
    explosionCalls += 1;
  }

  @override
  Future<void> dispose() async {
    disposeCalls += 1;
  }
}

/// audioplayers 기반 구현.
class AudioPlayersMeetingIcebreakerAudioService
    implements MeetingIcebreakerAudioService {
  AudioPlayersMeetingIcebreakerAudioService({
    AudioPlayer? tickPlayer,
    AudioPlayer? explosionPlayer,
    this.onFailure,
  }) : _tickPlayer = tickPlayer ?? AudioPlayer(playerId: 'icebreaker_tick'),
       _explosionPlayer =
           explosionPlayer ?? AudioPlayer(playerId: 'icebreaker_boom');

  final AudioPlayer _tickPlayer;
  final AudioPlayer _explosionPlayer;
  final MeetingIcebreakerAudioFailureReporter? onFailure;

  bool _disposed = false;
  bool _lastFailed = false;

  @override
  bool get lastPlaybackFailed => _lastFailed;

  void _reportFailure(MeetingIcebreakerAudioStage stage, Object error) {
    _lastFailed = true;
    // 실패 내용에 사용자 정보가 없다. 단계만 기록한다.
    debugPrint(
      '[ICEBREAKER][audio] ${stage.name} failed: '
      '${PrivacyLogUtils.errorSummary(error)}',
    );
    onFailure?.call(stage);
  }

  @override
  Future<void> startTicking() async {
    if (_disposed) return;
    try {
      await _tickPlayer.setReleaseMode(ReleaseMode.loop);
      await _tickPlayer.stop();
      await _tickPlayer.play(AssetSource(_assetKey(kBombTickLoopAsset)));
      _lastFailed = false;
    } catch (error) {
      _reportFailure(MeetingIcebreakerAudioStage.ticking, error);
    }
  }

  @override
  Future<void> stopTicking() async {
    if (_disposed) return;
    try {
      await _tickPlayer.stop();
    } catch (error) {
      _reportFailure(MeetingIcebreakerAudioStage.ticking, error);
    }
  }

  @override
  Future<void> playExplosion() async {
    if (_disposed) return;
    try {
      await _explosionPlayer.setReleaseMode(ReleaseMode.stop);
      await _explosionPlayer.stop();
      await _explosionPlayer.play(AssetSource(_assetKey(kBombExplosionAsset)));
      _lastFailed = false;
    } catch (error) {
      _reportFailure(MeetingIcebreakerAudioStage.explosion, error);
    }
  }

  @override
  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    try {
      await _tickPlayer.stop();
      await _explosionPlayer.stop();
      await _tickPlayer.dispose();
      await _explosionPlayer.dispose();
    } catch (error) {
      _reportFailure(MeetingIcebreakerAudioStage.dispose, error);
    }
  }

  /// audioplayers의 AssetSource는 `assets/` 접두어를 스스로 붙인다.
  static String _assetKey(String path) {
    const prefix = 'assets/';
    return path.startsWith(prefix) ? path.substring(prefix.length) : path;
  }
}

/// 화면이 사용할 오디오 서비스 생성 지점.
///
/// 테스트에서 [factory]를 바꿔 플랫폼 채널을 피할 수 있다.
class MeetingIcebreakerAudio {
  MeetingIcebreakerAudio._();

  static MeetingIcebreakerAudioService Function({
    MeetingIcebreakerAudioFailureReporter? onFailure,
  })
  factory = ({MeetingIcebreakerAudioFailureReporter? onFailure}) =>
      AudioPlayersMeetingIcebreakerAudioService(onFailure: onFailure);

  static MeetingIcebreakerAudioService create({
    MeetingIcebreakerAudioFailureReporter? onFailure,
  }) => factory(onFailure: onFailure);

  /// 테스트에서 기본 구현으로 되돌린다.
  @visibleForTesting
  static void resetFactory() {
    factory = ({MeetingIcebreakerAudioFailureReporter? onFailure}) =>
        AudioPlayersMeetingIcebreakerAudioService(onFailure: onFailure);
  }
}
