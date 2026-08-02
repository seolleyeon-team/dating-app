// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 테스트 지원 코드
// 경로: test/features/meeting_icebreaker/meeting_icebreaker_test_support.dart
// =============================================================================

import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/data/meeting_icebreaker_analytics.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/data/meeting_icebreaker_repository.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/domain/meeting_icebreaker_prompt.dart';

/// 주입 가능한 고정 난수. `nextInt`가 정해진 값을 순서대로 돌려준다.
class FixedRandom implements math.Random {
  FixedRandom(this.values) : assert(values.isNotEmpty);

  final List<int> values;
  int _cursor = 0;

  int get drawCount => _cursor;

  @override
  int nextInt(int max) {
    final value = values[_cursor % values.length];
    _cursor += 1;
    return value % max;
  }

  @override
  bool nextBool() => nextInt(2) == 1;

  @override
  double nextDouble() => 0.0;
}

/// 테스트에서 시간을 직접 옮기는 시계.
class FakeClock {
  FakeClock(this._now);

  DateTime _now;

  DateTime call() => _now;

  void advance(Duration delta) => _now = _now.add(delta);
}

/// analytics 전송 내용을 기록하는 sink.
class RecordingAnalyticsSink implements MeetingIcebreakerAnalyticsSink {
  final List<(String, Map<String, dynamic>)> events =
      <(String, Map<String, dynamic>)>[];

  List<String> get names => events.map((e) => e.$1).toList();

  Map<String, dynamic>? paramsFor(String name) {
    for (final event in events) {
      if (event.$1 == name) return event.$2;
    }
    return null;
  }

  @override
  Future<void> send(String event, Map<String, dynamic> params) async {
    events.add((event, params));
  }
}

/// callable을 타지 않는 가짜 저장소.
class FakeMeetingIcebreakerRepository implements MeetingIcebreakerRepository {
  FakeMeetingIcebreakerRepository({
    MeetingIcebreakerEntry? entry,
    this.optOutResult,
    this.optOutFails = false,
  }) : entry =
           entry ??
           const MeetingIcebreakerEntry(
             decision: MeetingIcebreakerEntryDecision.allowed,
             sessionId: 'blind_m1',
             meetingId: 'm1',
             meetingKind: MeetingIcebreakerMeetingKind.blindTasteMeeting,
           );

  MeetingIcebreakerEntry entry;
  bool? optOutResult;
  bool optOutFails;

  int loadEntryCalls = 0;
  int setOptOutCalls = 0;
  bool? lastOptOutRequested;

  @override
  Future<MeetingIcebreakerEntry> loadEntry({
    String? sessionId,
    String? meetingId,
    MeetingIcebreakerMeetingKind? meetingKind,
  }) async {
    loadEntryCalls += 1;
    return entry;
  }

  @override
  Future<bool> setOptOut({
    required String sessionId,
    required bool optedOut,
  }) async {
    setOptOutCalls += 1;
    lastOptOutRequested = optedOut;
    if (optOutFails) return !optedOut;
    return optOutResult ?? optedOut;
  }
}

/// 자체 Scaffold를 가진 화면용 host.
Widget icebreakerScreenHost(
  Widget child, {
  Size? size,
  double textScale = 1.0,
  bool disableAnimations = false,
  ThemeData? theme,
}) {
  return MaterialApp(
    theme: theme,
    home: MediaQuery(
      data: MediaQueryData(
        size: size ?? const Size(400, 800),
        textScaler: TextScaler.linear(textScale),
        disableAnimations: disableAnimations,
      ),
      child: child,
    ),
  );
}

/// 위젯 테스트용 host. 설레연 라이트 테마 토큰을 함께 넣는다.
Widget icebreakerHost(
  Widget child, {
  Size? size,
  double textScale = 1.0,
  bool disableAnimations = false,
  ThemeData? theme,
}) {
  return MaterialApp(
    theme: theme,
    home: MediaQuery(
      data: MediaQueryData(
        size: size ?? const Size(400, 800),
        textScaler: TextScaler.linear(textScale),
        disableAnimations: disableAnimations,
      ),
      child: Scaffold(body: child),
    ),
  );
}
