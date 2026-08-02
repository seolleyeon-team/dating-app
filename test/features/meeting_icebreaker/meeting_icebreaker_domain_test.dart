// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 도메인 단위 테스트
// 경로: test/features/meeting_icebreaker/meeting_icebreaker_domain_test.dart
//
// 실행: flutter test test/features/meeting_icebreaker
// =============================================================================

import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/data/meeting_icebreaker_analytics.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/domain/bomb_pass_timer.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/domain/meeting_icebreaker_game.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/domain/meeting_icebreaker_prompt.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/domain/meeting_roulette_spin.dart';

import 'meeting_icebreaker_test_support.dart';

void main() {
  group('룰렛 8개 항목', () {
    test('요청된 순서와 이름을 그대로 유지한다', () {
      final games = buildMeetingRouletteGames();

      expect(games.length, kMeetingRouletteSegmentCount);
      expect(games.map((g) => g.title).toList(), <String>[
        '귓속말게임',
        '랭킹게임',
        '이미지게임',
        '폭탄 돌리기',
        '출석부',
        '다음 게임 동안 벌주 *2잔',
        '침묵의 공공칠빵',
        '두부 게임',
      ]);
    });

    test('설명은 테스트용 번호 1부터 8까지다', () {
      final games = buildMeetingRouletteGames();
      expect(games.map((g) => g.description).toList(), <String>[
        '1',
        '2',
        '3',
        '4',
        '5',
        '6',
        '7',
        '8',
      ]);
      for (var i = 0; i < games.length; i++) {
        expect(games[i].number, i + 1);
        expect(games[i].index, i);
      }
    });

    test('enum 순서가 룰렛 칸 순서와 같다', () {
      final games = buildMeetingRouletteGames();
      expect(games.map((g) => g.type).toList(), <MeetingRouletteGameType>[
        MeetingRouletteGameType.whisper,
        MeetingRouletteGameType.ranking,
        MeetingRouletteGameType.image,
        MeetingRouletteGameType.bombPass,
        MeetingRouletteGameType.attendance,
        MeetingRouletteGameType.doubleDrinkPenalty,
        MeetingRouletteGameType.silent007,
        MeetingRouletteGameType.tofu,
      ]);
      expect(MeetingRouletteGameType.values.length, 8);
    });

    test('폭탄 돌리기만 타이머 CTA를 노출한다', () {
      final games = buildMeetingRouletteGames();
      final withTimer = games.where((g) => g.opensBombTimer).toList();
      expect(withTimer.length, 1);
      expect(withTimer.single.type, MeetingRouletteGameType.bombPass);
      expect(withTimer.single.number, 4);
    });

    test('음주 문구를 비음주 문구로 대체해도 칸 수와 순서는 유지된다', () {
      final sober = buildMeetingRouletteGames(alcoholFreeCopy: true);

      expect(sober.length, kMeetingRouletteSegmentCount);
      expect(sober[5].title, kMeetingRouletteNonAlcoholPenaltyTitle);
      expect(sober[5].type, MeetingRouletteGameType.doubleDrinkPenalty);
      expect(sober[5].number, 6);
      expect(sober[5].mentionsAlcohol, isFalse);
      expect(sober.any((g) => g.mentionsAlcohol), isFalse);
      // 나머지 칸 이름은 그대로다.
      expect(sober[0].title, '귓속말게임');
      expect(sober[7].title, '두부 게임');
    });

    test('기본 문구에서는 음주 안내가 필요한 칸이 정확히 하나다', () {
      final games = buildMeetingRouletteGames();
      expect(games.where((g) => g.mentionsAlcohol).length, 1);
      expect(games[5].mentionsAlcohol, isTrue);
    });

    test('칸 라벨은 두 줄 이하로 끊는다', () {
      for (final game in buildMeetingRouletteGames()) {
        final lines = meetingRouletteSegmentLabelLines(game);
        expect(lines, isNotEmpty);
        expect(lines.length, lessThanOrEqualTo(2));
      }
    });
  });

  group('회전 각도 계산', () {
    test('칸 하나는 45도를 차지한다', () {
      expect(kMeetingRouletteSegmentSweep, closeTo(2 * math.pi / 8, 1e-12));
    });

    test('모든 index에서 최종 각도가 그 칸을 가리킨다', () {
      for (var index = 0; index < kMeetingRouletteSegmentCount; index++) {
        final rotation = meetingRouletteTargetRotation(index: index);
        expect(
          meetingRouletteWinningIndex(rotation),
          index,
          reason: 'index $index 결과 위치 불일치',
        );
      }
    });

    test('바퀴 수를 바꿔도 같은 칸에 멈춘다 (wrap-around)', () {
      for (var turns = 1; turns <= 12; turns++) {
        for (var index = 0; index < kMeetingRouletteSegmentCount; index++) {
          final rotation = meetingRouletteTargetRotation(
            index: index,
            fullTurns: turns,
          );
          expect(meetingRouletteWinningIndex(rotation), index);
        }
      }
    });

    test('시작 각도가 남아 있어도 결과가 유지된다', () {
      // 이전 회전이 남긴 각도 위에 이어서 돌리는 상황
      for (var index = 0; index < kMeetingRouletteSegmentCount; index++) {
        for (final start in <double>[0.0, 0.7, 1.9, 3.3, 5.8]) {
          final rotation = start + meetingRouletteTargetRotation(index: index);
          // start만큼 이미 돌아간 상태에서의 상대 결과를 확인한다.
          expect(meetingRouletteWinningIndex(rotation - start), index);
        }
      }
    });

    test('음수 각도도 0~7 범위 index로 정규화된다', () {
      for (final rotation in <double>[-0.1, -1.0, -6.3, -20.0]) {
        final index = meetingRouletteWinningIndex(rotation);
        expect(index, inInclusiveRange(0, kMeetingRouletteSegmentCount - 1));
      }
    });

    test('경계 통과 수를 센다', () {
      expect(
        meetingRouletteBoundaryCrossings(fromRotation: 0, toRotation: 0),
        0,
      );
      expect(
        meetingRouletteBoundaryCrossings(
          fromRotation: 0,
          toRotation: kMeetingRouletteSegmentSweep * 0.9,
        ),
        0,
      );
      expect(
        meetingRouletteBoundaryCrossings(
          fromRotation: 0,
          toRotation: kMeetingRouletteSegmentSweep * 1.1,
        ),
        1,
      );
      expect(
        meetingRouletteBoundaryCrossings(
          fromRotation: 0,
          toRotation: kMeetingRouletteSegmentSweep * 8,
        ),
        8,
      );
      // 역방향은 세지 않는다.
      expect(
        meetingRouletteBoundaryCrossings(fromRotation: 5, toRotation: 1),
        0,
      );
    });

    test('기본 바퀴 수는 최소 요구(4바퀴) 이상이다', () {
      expect(
        kMeetingRouletteFullTurns,
        greaterThanOrEqualTo(kMeetingRouletteMinFullTurns),
      );
      expect(kMeetingRouletteSpinDuration.inMilliseconds, greaterThan(3000));
      expect(
        kMeetingRouletteSpinDuration.inMilliseconds,
        lessThanOrEqualTo(5000),
      );
    });

    test('당첨 조명은 2초 뒤 설명 창으로 이어진다', () {
      expect(kMeetingRouletteCelebrationDelay, const Duration(seconds: 2));
    });
  });

  group('당첨 index 추출', () {
    test('주입한 난수가 결과를 결정한다', () {
      final random = FixedRandom(<int>[0, 3, 7, 5]);
      expect(drawMeetingRouletteIndex(random), 0);
      expect(drawMeetingRouletteIndex(random), 3);
      expect(drawMeetingRouletteIndex(random), 7);
      expect(drawMeetingRouletteIndex(random), 5);
    });

    test('항상 0~7 범위이고 8칸 모두 나온다', () {
      final random = math.Random(20260731);
      final counts = List<int>.filled(kMeetingRouletteSegmentCount, 0);
      for (var i = 0; i < 8000; i++) {
        final index = drawMeetingRouletteIndex(random);
        expect(index, inInclusiveRange(0, 7));
        counts[index] += 1;
      }
      // 1/8 균등 분포. 느슨한 범위로만 확인한다 (flaky 방지).
      for (final count in counts) {
        expect(count, greaterThan(700));
        expect(count, lessThan(1300));
      }
    });
  });

  group('폭탄 숨겨진 시간', () {
    test('1초부터 15초 사이다', () {
      final random = math.Random(7);
      for (var i = 0; i < 3000; i++) {
        final duration = drawBombPassHiddenDuration(random);
        expect(duration.inSeconds, greaterThanOrEqualTo(1));
        expect(duration.inSeconds, lessThanOrEqualTo(15));
      }
    });

    test('최소값 1초가 포함된다', () {
      expect(drawBombPassHiddenDuration(FixedRandom(<int>[0])).inSeconds, 1);
    });

    test('최대값 15초가 포함된다', () {
      expect(drawBombPassHiddenDuration(FixedRandom(<int>[14])).inSeconds, 15);
    });

    test('1초부터 15초까지 모든 값이 나올 수 있다', () {
      final seen = <int>{};
      for (var value = 0; value < 15; value++) {
        seen.add(
          drawBombPassHiddenDuration(FixedRandom(<int>[value])).inSeconds,
        );
      }
      expect(seen.length, 15);
      expect(seen.reduce(math.min), kBombPassHiddenMinSeconds);
      expect(seen.reduce(math.max), kBombPassHiddenMaxSeconds);
    });

    test('deadline은 시작 시각 + 숨겨진 시간이다', () {
      final start = DateTime.utc(2026, 7, 31, 20, 0, 0);
      final deadline = computeBombPassDeadline(
        startedAt: start,
        hiddenDuration: const Duration(seconds: 7),
      );
      expect(deadline, DateTime.utc(2026, 7, 31, 20, 0, 7));
      expect(
        hasBombPassDeadlinePassed(
          now: DateTime.utc(2026, 7, 31, 20, 0, 6),
          deadline: deadline,
        ),
        isFalse,
      );
      expect(
        hasBombPassDeadlinePassed(now: deadline, deadline: deadline),
        isTrue,
      );
      expect(
        hasBombPassDeadlinePassed(
          now: DateTime.utc(2026, 7, 31, 20, 5, 0),
          deadline: deadline,
        ),
        isTrue,
      );
    });

    test('실제 시간이 마스킹 문자열에 드러나지 않는다', () {
      expect(kBombPassHiddenTimerMask, '??:??');
      expect(RegExp(r'\d').hasMatch(kBombPassHiddenTimerMask), isFalse);
      expect(
        RegExp(r'\d').hasMatch(kBombPassHiddenTimerSemanticLabel),
        isFalse,
      );
    });
  });

  group('알림 payload 파싱', () {
    Map<String, dynamic> payload({
      String type = kMeetingIcebreakerNotificationType,
      String sessionId = 'blind_m1',
      String meetingId = 'm1',
      String meetingType = 'blindTasteMeeting',
      String sequence = '3',
      String notificationId = 'meeting_icebreaker_blind_m1_u1_3',
    }) {
      return <String, dynamic>{
        'type': type,
        'sessionId': sessionId,
        'meetingId': meetingId,
        'meetingType': meetingType,
        'notificationSequence': sequence,
        'notificationId': notificationId,
      };
    }

    test('룰렛 알림을 복원한다', () {
      final parsed = MeetingIcebreakerPromptPayload.tryParse(payload());
      expect(parsed, isNotNull);
      expect(parsed!.sessionId, 'blind_m1');
      expect(parsed.meetingId, 'm1');
      expect(
        parsed.meetingKind,
        MeetingIcebreakerMeetingKind.blindTasteMeeting,
      );
      expect(parsed.notificationSequence, 3);
      expect(parsed.dedupeKey, 'meeting_icebreaker_blind_m1_u1_3');
    });

    test('시즌 미팅 payload도 복원한다', () {
      final parsed = MeetingIcebreakerPromptPayload.tryParse(
        payload(meetingType: 'seasonMeeting', sessionId: 'season_p1'),
      );
      expect(parsed!.meetingKind, MeetingIcebreakerMeetingKind.seasonMeeting);
    });

    test('다른 알림 타입은 무시한다', () {
      expect(
        MeetingIcebreakerPromptPayload.tryParse(payload(type: 'chat')),
        isNull,
      );
      expect(
        MeetingIcebreakerPromptPayload.tryParse(
          payload(type: 'blind_meeting_checkin'),
        ),
        isNull,
      );
      expect(MeetingIcebreakerPromptPayload.tryParse(null), isNull);
      expect(
        MeetingIcebreakerPromptPayload.tryParse(<String, dynamic>{}),
        isNull,
      );
    });

    test('식별자가 모두 없으면 무시한다', () {
      expect(
        MeetingIcebreakerPromptPayload.tryParse(
          payload(sessionId: '', meetingId: ''),
        ),
        isNull,
      );
    });

    test('notificationId가 없으면 세션+순번으로 dedupe한다', () {
      final parsed = MeetingIcebreakerPromptPayload.tryParse(
        payload(notificationId: ''),
      );
      expect(parsed!.dedupeKey, 'blind_m1#3');
    });

    test('알 수 없는 미팅 종류는 null로 둔다', () {
      final parsed = MeetingIcebreakerPromptPayload.tryParse(
        payload(meetingType: 'generalEvent'),
      );
      expect(parsed!.meetingKind, isNull);
    });
  });

  group('진입 판정', () {
    test('서버 문자열을 enum으로 매핑한다', () {
      expect(
        meetingIcebreakerEntryDecisionFromWire('allowed'),
        MeetingIcebreakerEntryDecision.allowed,
      );
      expect(
        meetingIcebreakerEntryDecisionFromWire('meeting_ended'),
        MeetingIcebreakerEntryDecision.meetingEnded,
      );
      expect(
        meetingIcebreakerEntryDecisionFromWire('not_participant'),
        MeetingIcebreakerEntryDecision.notParticipant,
      );
      expect(
        meetingIcebreakerEntryDecisionFromWire('made_up'),
        MeetingIcebreakerEntryDecision.unavailable,
      );
      expect(
        meetingIcebreakerEntryDecisionFromWire(null),
        MeetingIcebreakerEntryDecision.unavailable,
      );
    });

    test('종료된 미팅 안내 문구', () {
      expect(
        MeetingIcebreakerEntryDecision.meetingEnded.userMessage,
        '이 미팅은 이미 종료되었어요.',
      );
    });

    test('거부 사유마다 안내 문구가 있다', () {
      for (final decision in MeetingIcebreakerEntryDecision.values) {
        if (decision == MeetingIcebreakerEntryDecision.allowed) continue;
        expect(decision.userMessage, isNotEmpty, reason: decision.name);
      }
    });

    test('서버 응답을 그대로 반영한다', () {
      final entry = MeetingIcebreakerEntry.fromMap(<String, dynamic>{
        'decision': 'allowed',
        'sessionId': 'season_p1',
        'meetingId': 'p1',
        'meetingType': 'seasonMeeting',
        'alcoholFreeCopy': true,
        'optedOut': true,
        'bombPassEnabled': false,
      });
      expect(entry.allowed, isTrue);
      expect(entry.meetingKind, MeetingIcebreakerMeetingKind.seasonMeeting);
      expect(entry.alcoholFreeCopy, isTrue);
      expect(entry.optedOut, isTrue);
      expect(entry.bombPassEnabled, isFalse);
    });

    test('응답이 없으면 unavailable로 처리한다', () {
      final entry = MeetingIcebreakerEntry.fromMap(null);
      expect(entry.allowed, isFalse);
      expect(entry.decision, MeetingIcebreakerEntryDecision.unavailable);
    });
  });

  group('analytics 보호', () {
    test('허용 목록에 없는 값은 전송하지 않는다', () {
      final sanitized = MeetingIcebreakerAnalytics.sanitizeParams(
        <String, dynamic>{
          'meeting_type': 'seasonMeeting',
          'game_type': 'bombPass',
          'nickname': '민지',
          'userId': 'u1',
          'place': '홍대 카페',
          'hiddenSeconds': 7,
          'fcmToken': 'token',
          'participantIds': <String>['a', 'b'],
        },
      );

      expect(sanitized.keys.toSet(), <String>{'meeting_type', 'game_type'});
    });

    test('폭탄 숨겨진 시간 키는 차단 목록에 있다', () {
      expect(meetingIcebreakerBlockedParams, contains('hiddenSeconds'));
      expect(meetingIcebreakerBlockedParams, contains('bombSeconds'));
      expect(meetingIcebreakerBlockedParams, contains('hiddenDuration'));
      expect(meetingIcebreakerBlockedParams, contains('fcmToken'));
    });

    test('null 값은 버린다', () {
      final sanitized = MeetingIcebreakerAnalytics.sanitizeParams(
        <String, dynamic>{'meeting_type': null, 'game_type': 'tofu'},
      );
      expect(sanitized, <String, dynamic>{'game_type': 'tofu'});
    });

    test('기록 가능한 이벤트 이름이 규칙을 지킨다', () {
      final pattern = RegExp(
        r'^(meeting_icebreaker|meeting_roulette|meeting_game|bomb_timer)_[a-z0-9_]+$',
      );
      for (final event in MeetingIcebreakerAnalyticsEvent.values) {
        expect(pattern.hasMatch(event.name), isTrue, reason: event.name);
      }
    });
  });

  group('회전 시간 bucket', () {
    test('원시 값 대신 구간을 기록한다', () {
      expect(
        meetingRouletteSpinDurationBucket(const Duration(milliseconds: 600)),
        'lt_1s',
      );
      expect(
        meetingRouletteSpinDurationBucket(const Duration(milliseconds: 2500)),
        '1_3s',
      );
      expect(
        meetingRouletteSpinDurationBucket(const Duration(milliseconds: 4200)),
        '3_5s',
      );
      expect(
        meetingRouletteSpinDurationBucket(const Duration(seconds: 6)),
        'gte_5s',
      );
    });
  });
}
