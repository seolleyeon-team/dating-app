// =============================================================================
// 3:3 미팅 아이스브레이킹 룰렛 — 클라이언트/서버 계약 일치 테스트
// 경로: test/features/meeting_icebreaker/meeting_icebreaker_parity_test.dart
//
// 알림 타입, 조용한 채널 id, 주기, 진입 판정 문자열이 서버와 어긋나면
// 알림이 오지 않거나 룰렛이 열리지 않는다. 문자열 계약을 테스트로 고정한다.
// =============================================================================

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/data/meeting_icebreaker_analytics.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/domain/meeting_icebreaker_game.dart';
import 'package:seolleyeon/features/event/meeting_icebreaker/domain/meeting_icebreaker_prompt.dart';

String read(String path) {
  final file = File(path);
  if (!file.existsSync()) {
    throw StateError('$path 없음 (테스트는 저장소 루트에서 실행해야 한다)');
  }
  return file.readAsStringSync();
}

/// `export const NAME = "value";` 형태에서 값을 뽑는다.
String? stringConst(String source, String name) {
  final match = RegExp(
    'export const $name\\s*=\\s*"([^"]*)"',
  ).firstMatch(source);
  return match?.group(1);
}

/// `key: 123,` 형태에서 숫자를 뽑는다.
int? numberField(String source, String key) {
  final match = RegExp('$key:\\s*(\\d+)').firstMatch(source);
  final raw = match?.group(1);
  return raw == null ? null : int.parse(raw);
}

void main() {
  final notifyTs = read('functions/src/shared/notify.ts');
  final typesTs = read('functions/src/meetingIcebreaker/types.ts');
  final policyTs = read('functions/src/meetingIcebreaker/policy.ts');
  final notificationsTs = read(
    'functions/src/meetingIcebreaker/notifications.ts',
  );
  final tasksTs = read('functions/src/meetingIcebreaker/tasks.ts');
  final functionsTs = read('functions/src/meetingIcebreaker/functions.ts');
  final rules = read('firestore.rules');

  group('알림 계약', () {
    test('알림 타입 문자열이 같다', () {
      expect(
        stringConst(notificationsTs, 'MEETING_ICEBREAKER_NOTIFICATION_TYPE'),
        kMeetingIcebreakerNotificationType,
      );
      expect(
        stringConst(notificationsTs, 'MEETING_ICEBREAKER_DEEPLINK_TYPE'),
        kMeetingIcebreakerNotificationType,
      );
    });

    test('조용한 채널 id가 같다', () {
      expect(
        stringConst(notifyTs, 'QUIET_PUSH_CHANNEL_ID'),
        kMeetingIcebreakerQuietChannelId,
      );
    });

    test('알림 제목과 본문이 같다', () {
      expect(
        stringConst(notificationsTs, 'MEETING_ICEBREAKER_PROMPT_TITLE'),
        kMeetingIcebreakerPromptTitle,
      );
      expect(
        stringConst(notificationsTs, 'MEETING_ICEBREAKER_PROMPT_BODY'),
        kMeetingIcebreakerPromptBody,
      );
    });

    test('서버가 알림 타입을 이벤트 카테고리로 매핑한다', () {
      expect(notifyTs, contains('case "meeting_icebreaker_roulette":'));
      expect(notifyTs, contains('"meeting_icebreaker_roulette"'));
    });

    test('조용한 알림은 소리·진동을 끈다', () {
      expect(notifyTs, contains('defaultSound: false'));
      expect(notifyTs, contains('defaultVibrateTimings: false'));
      expect(notifyTs, contains('interruption-level'));
      // data-only silent push로 대체하지 않는다 (notification 블록을 유지).
      expect(notifyTs, contains('notification: {'));
    });
  });

  group('미팅 유형 계약', () {
    test('시즌 미팅 / 블라인드 미팅 문자열이 같다', () {
      expect(
        stringConst(typesTs, 'SEASON_MEETING_TYPE'),
        MeetingIcebreakerMeetingKind.seasonMeeting.wireName,
      );
      expect(
        stringConst(typesTs, 'BLIND_TASTE_MEETING_TYPE'),
        MeetingIcebreakerMeetingKind.blindTasteMeeting.wireName,
      );
    });

    test('3:3 인원 수가 6명으로 고정되어 있다', () {
      expect(
        RegExp(
          r'MEETING_ICEBREAKER_PARTICIPANT_COUNT\s*=\s*(\d+)',
        ).firstMatch(typesTs)?.group(1),
        '6',
      );
    });

    test('서버 진입 판정 값이 클라이언트 enum과 일치한다', () {
      final decisionBlock = RegExp(
        r'export type MeetingIcebreakerEntryDecision =([\s\S]*?);',
      ).firstMatch(typesTs)?.group(1);
      expect(decisionBlock, isNotNull);

      final serverValues = RegExp(
        '"([a-z_]+)"',
      ).allMatches(decisionBlock!).map((m) => m.group(1)!).toSet();

      final clientValues = MeetingIcebreakerEntryDecision.values
          .where(
            // unavailable은 네트워크 오류용 클라이언트 전용 값이다.
            (d) => d != MeetingIcebreakerEntryDecision.unavailable,
          )
          .map((d) => d.wireName)
          .toSet();

      expect(serverValues, clientValues);
    });
  });

  group('알림 주기 정책', () {
    test('15분 주기 기본값이 같다', () {
      expect(
        numberField(policyTs, 'promptIntervalMinutes'),
        kMeetingIcebreakerPromptIntervalMinutes,
      );
      expect(
        numberField(policyTs, 'firstPromptDelayMinutes'),
        kMeetingIcebreakerPromptIntervalMinutes,
      );
    });

    test('최대 지속 시간 기본값이 같다', () {
      expect(
        numberField(policyTs, 'maxPromptDurationHours'),
        kMeetingIcebreakerMaxPromptDurationHours,
      );
    });

    test('15분이라는 숫자를 정책 한 곳에서만 관리한다', () {
      // 다른 서버 파일에서 15분을 다시 하드코딩하지 않는다.
      for (final path in <String>[
        'functions/src/meetingIcebreaker/session.ts',
        'functions/src/meetingIcebreaker/notifications.ts',
      ]) {
        expect(
          read(path).contains('15 * 60 * 1000'),
          isFalse,
          reason: '$path 에 15분이 하드코딩되어 있다',
        );
      }
    });

    test('feature flag가 정책에 정의되어 있다', () {
      expect(policyTs, contains('rouletteEnabled'));
      expect(policyTs, contains('notificationsEnabled'));
      expect(policyTs, contains('bombPassEnabled'));
      expect(policyTs, contains('alcoholFreeCopyForced'));
    });
  });

  group('Cloud Tasks 계약', () {
    test('queue 경로가 실제 함수 이름과 같다', () {
      final queueName = stringConst(tasksTs, 'MEETING_ICEBREAKER_QUEUE');
      final queuePath = stringConst(tasksTs, 'MEETING_ICEBREAKER_QUEUE_PATH');
      expect(queueName, 'dispatchMeetingIcebreakerPrompt');
      expect(queuePath, endsWith('/$queueName'));
      expect(
        functionsTs,
        contains('export const dispatchMeetingIcebreakerPrompt'),
      );
    });

    test('서버 예약 함수가 모두 export 되어 있다', () {
      expect(
        functionsTs,
        contains('export const syncMeetingIcebreakerFromPromise'),
      );
      expect(
        functionsTs,
        contains('export const meetingIcebreakerReconcileTick'),
      );
      expect(functionsTs, contains('export const meetingIcebreakerAction'));
    });

    test('반복 알림을 Timer.periodic으로 구현하지 않는다', () {
      expect(
        read(
          'lib/features/event/meeting_icebreaker/services/'
          'meeting_icebreaker_deep_link_handler.dart',
        ).contains('Timer.periodic'),
        isFalse,
      );
    });
  });

  group('Firestore 규칙', () {
    test('알림 상태는 서버만 쓴다', () {
      expect(rules, contains('match /meetingIcebreakerSessions/{sessionId}'));
      expect(rules, contains('match /promptParticipants/{userId}'));
      expect(rules, contains('allow create, update, delete: if false;'));
    });

    test('analytics 규칙이 모든 이벤트 이름을 허용한다', () {
      final pattern = RegExp(
        r"matches\('(\^\([a-z_|]+\)_\[a-z0-9_\]\+\$)'\)",
      ).firstMatch(rules)?.group(1);
      expect(pattern, isNotNull);

      final allow = RegExp(pattern!);
      for (final event in MeetingIcebreakerAnalyticsEvent.values) {
        expect(
          allow.hasMatch(event.name),
          isTrue,
          reason: '${event.name} 이 규칙에서 차단된다',
        );
      }
    });

    test('폭탄 숨겨진 시간 키가 규칙에서 차단된다', () {
      expect(
        rules,
        contains("!('hiddenSeconds' in request.resource.data.params)"),
      );
      expect(
        rules,
        contains("!('bombSeconds' in request.resource.data.params)"),
      );
      expect(rules, contains("!('fcmToken' in request.resource.data.params)"));
    });
  });

  group('룰렛 항목 계약', () {
    test('칸 수는 8개로 고정이다', () {
      expect(kMeetingRouletteSegmentCount, 8);
      expect(buildMeetingRouletteGames().length, 8);
      expect(buildMeetingRouletteGames(alcoholFreeCopy: true).length, 8);
    });

    test('collection group index가 등록되어 있다', () {
      final indexes = read('firestore.indexes.json');
      expect(indexes, contains('"collectionGroup": "promptParticipants"'));
      expect(indexes, contains('"queryScope": "COLLECTION_GROUP"'));
      expect(indexes, contains('"fieldPath": "nextPromptAt"'));
    });
  });
}
