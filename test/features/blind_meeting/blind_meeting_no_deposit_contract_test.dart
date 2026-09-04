// 블라인드 3:3 — 보증금 없음(NO_DEPOSIT) 계약 (앱)
//
// 매칭이 commit 되면 결제 절차 없이 바로 확정되고 단체 채팅방이 열린다.
//  - enum/FSM 에 결제 대기 상태가 없다
//  - repository 에 결제 callable 호출이 없다 (하트 환불은 결제가 아니다)
//  - 사용자에게 노출되는 production 코드에 보증금/환급 문구가 없다
//  - legacy 문서 값은 crash 없이 canonical 상태로 디코드된다 (결제 화면 없음)

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_application.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_enums.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_legacy_status.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_session.dart';

final RegExp _depositPattern = RegExp(
  r'deposit|refund|보증금|환급',
  caseSensitive: false,
);

/// 보증금 환급 문맥. `refund` 는 2026-09-03 부터 매칭 전 신청 취소의 하트 환불
/// 코드(heartRefunded 등)에 정당하게 등장하므로, deposit/결제/보증금/환급 과
/// 같은 줄에 있을 때만 위반으로 본다.
final RegExp _depositRefundContext = RegExp(
  r'deposit|payment|intent|보증금|환급|결제',
  caseSensitive: false,
);

bool _isDepositOffence(String line) {
  if (!_depositPattern.hasMatch(line)) return false;
  if (RegExp(r'deposit|보증금|환급', caseSensitive: false).hasMatch(line)) {
    return true;
  }
  return _depositRefundContext.hasMatch(line);
}

/// legacy 문서 디코드 경계. 여기에만 과거 상태 문자열이 남을 수 있다.
const Set<String> _legacyAdapterFiles = {'blind_meeting_legacy_status.dart'};

Iterable<File> _blindMeetingSources() {
  final dir = Directory('lib/features/blind_meeting');
  return dir
      .listSync(recursive: true)
      .whereType<File>()
      .where((f) => f.path.endsWith('.dart'));
}

void main() {
  group('enum / FSM 에 결제 상태가 없다', () {
    test('미팅 상태 이름에 deposit 이 없다', () {
      for (final status in BlindMeetingStatus.values) {
        expect(status.name, isNot(matches(_depositPattern)));
      }
    });

    test('참가자 상태 이름에 deposit 이 없다', () {
      for (final status in BlindMeetingParticipantStatus.values) {
        expect(status.name, isNot(matches(_depositPattern)));
      }
    });

    test('legacy 수락 대기 → 확정이 유일한 전진 전환이다', () {
      expect(
        canTransitionMeeting(
          BlindMeetingStatus.awaitingAcceptance,
          BlindMeetingStatus.confirmed,
        ),
        isTrue,
      );
      expect(allowedMeetingTransitions[BlindMeetingStatus.awaitingAcceptance], {
        BlindMeetingStatus.confirmed,
        BlindMeetingStatus.forming,
      });
    });

    test('수락한 참가자는 바로 확정으로 간다', () {
      expect(
        canTransitionParticipant(
          BlindMeetingParticipantStatus.accepted,
          BlindMeetingParticipantStatus.confirmed,
        ),
        isTrue,
      );
    });
  });

  group('legacy 문서 디코드 (결제 화면 없음)', () {
    test('legacy awaitingDeposits 미팅은 수락 대기 상태로 읽힌다', () {
      for (final raw in const ['awaitingDeposits', 'awaiting_deposits']) {
        final session = BlindMeetingSession.fromMap('m1', {
          'status': raw,
          'participantIds': ['a1', 'a2', 'a3', 'b1', 'b2', 'b3'],
          'depositsOpenedAt': '2026-01-01',
          'depositAmount': 5000,
        });
        expect(session.status, BlindMeetingStatus.awaitingAcceptance);
      }
    });

    test('legacy depositPending 참가자는 수락 상태로 읽힌다', () {
      for (final raw in const ['depositPending', 'deposit_pending']) {
        final participant = BlindMeetingParticipant.fromMap('u1', {
          'status': raw,
          'team': 'teamA',
          // 과거 결제 필드는 무시된다 (crash 없음).
          'depositStatus': 'paid',
          'serverDepositStatus': 'paid',
          'refundedAmount': 5000,
        });
        expect(participant.status, BlindMeetingParticipantStatus.accepted);
      }
    });

    test('legacy depositPending 신청서는 수락 상태로 읽힌다', () {
      final application = BlindMeetingApplication.fromMap('u1', {
        'status': 'depositPending',
        'stage': 'matched',
      });
      expect(application.status, BlindMeetingParticipantStatus.accepted);
    });

    test('알 수 없는 상태는 fallback 으로 안전하게 읽힌다', () {
      expect(
        decodeBlindMeetingStatus(
          'somethingNew',
          fallback: BlindMeetingStatus.applicationOpen,
        ),
        BlindMeetingStatus.applicationOpen,
      );
      expect(
        decodeBlindMeetingParticipantStatus(
          'somethingNew',
          fallback: BlindMeetingParticipantStatus.applied,
        ),
        BlindMeetingParticipantStatus.applied,
      );
    });
  });

  group('소스 스캔 — USER_VISIBLE_BLIND_DEPOSIT_COPY=0', () {
    test('blind_meeting production 코드에 보증금/환급/deposit 이 없다', () {
      final offenders = <String>[];
      for (final file in _blindMeetingSources()) {
        final name = file.uri.pathSegments.last;
        if (_legacyAdapterFiles.contains(name)) continue;
        final lines = file.readAsLinesSync();
        for (var i = 0; i < lines.length; i++) {
          final line = lines[i];
          if (line.contains('blind_meeting_legacy_status.dart')) continue;
          if (_isDepositOffence(line)) {
            offenders.add('${file.path}:${i + 1}: ${line.trim()}');
          }
        }
      }
      expect(offenders, isEmpty, reason: offenders.join('\n'));
    });

    test('repository 는 결제 callable 을 호출하지 않는다', () {
      final source = File(
        'lib/features/blind_meeting/data/blind_meeting_repository.dart',
      ).readAsStringSync();
      expect(source, isNot(contains('startBlindMeetingDeposit')));
      expect(source, isNot(contains('startDeposit')));
      expect(source, isNot(contains('DepositIntent')));
    });

    test('ops repository 는 환급 override 를 호출하지 않는다', () {
      final source = File(
        'lib/features/blind_meeting/data/blind_meeting_ops_repository.dart',
      ).readAsStringSync();
      expect(source, isNot(contains('overrideBlindMeetingRefund')));
    });

    test('legacy 디코드 경계 파일이 존재한다', () {
      expect(
        File(
          'lib/features/blind_meeting/domain/blind_meeting_legacy_status.dart',
        ).existsSync(),
        isTrue,
      );
    });
  });
}
