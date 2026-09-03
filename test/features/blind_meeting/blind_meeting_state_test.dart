import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_dna.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_enums.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_followup.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_session.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_slot.dart';

void main() {
  group('미팅 상태 머신', () {
    test('정상 파이프라인 전환이 모두 허용된다', () {
      const pipeline = [
        BlindMeetingStatus.applicationOpen,
        BlindMeetingStatus.forming,
        BlindMeetingStatus.awaitingAcceptance,
        BlindMeetingStatus.confirmed,
        BlindMeetingStatus.chatOpen,
        BlindMeetingStatus.scheduleConfirmed,
        BlindMeetingStatus.checkinOpen,
        BlindMeetingStatus.inProgress,
        BlindMeetingStatus.completed,
        BlindMeetingStatus.followupOpen,
        BlindMeetingStatus.readOnly,
        BlindMeetingStatus.archived,
      ];
      for (var i = 0; i < pipeline.length - 1; i++) {
        expect(
          canTransitionMeeting(pipeline[i], pipeline[i + 1]),
          isTrue,
          reason: '${pipeline[i].name} → ${pipeline[i + 1].name}',
        );
      }
    });

    test('단계를 건너뛰는 전환은 거부된다', () {
      expect(
        canTransitionMeeting(
          BlindMeetingStatus.forming,
          BlindMeetingStatus.confirmed,
        ),
        isFalse,
      );
      expect(
        canTransitionMeeting(
          BlindMeetingStatus.applicationOpen,
          BlindMeetingStatus.chatOpen,
        ),
        isFalse,
      );
    });

    test('종료 상태에서는 어떤 전환도 불가', () {
      for (final status in BlindMeetingStatus.values) {
        expect(
          canTransitionMeeting(BlindMeetingStatus.archived, status),
          isFalse,
        );
        expect(
          canTransitionMeeting(BlindMeetingStatus.cancelled, status),
          isFalse,
        );
      }
    });

    test('취소는 종료 이전 어떤 상태에서도 가능', () {
      expect(
        canTransitionMeeting(
          BlindMeetingStatus.awaitingAcceptance,
          BlindMeetingStatus.cancelled,
        ),
        isTrue,
      );
      expect(
        canTransitionMeeting(
          BlindMeetingStatus.scheduleConfirmed,
          BlindMeetingStatus.cancelled,
        ),
        isTrue,
      );
    });

    test('채팅 쓰기 허용 단계가 명확하다', () {
      expect(BlindMeetingStatus.chatOpen.allowsGroupChatWrite, isTrue);
      expect(BlindMeetingStatus.followupOpen.allowsGroupChatWrite, isTrue);
      expect(BlindMeetingStatus.readOnly.allowsGroupChatWrite, isFalse);
      expect(BlindMeetingStatus.archived.allowsGroupChatWrite, isFalse);
      expect(
        BlindMeetingStatus.awaitingAcceptance.allowsGroupChatWrite,
        isFalse,
      );
    });
  });

  group('참가자 상태 머신', () {
    test('신청 → 초대 → 수락 → 확정 흐름 (결제 단계 없음)', () {
      const pipeline = [
        BlindMeetingParticipantStatus.applied,
        BlindMeetingParticipantStatus.invited,
        BlindMeetingParticipantStatus.accepted,
        BlindMeetingParticipantStatus.confirmed,
      ];
      for (var i = 0; i < pipeline.length - 1; i++) {
        expect(canTransitionParticipant(pipeline[i], pipeline[i + 1]), isTrue);
      }
    });

    test('교체된 참가자는 더 이상 상태가 바뀌지 않는다', () {
      for (final status in BlindMeetingParticipantStatus.values) {
        expect(
          canTransitionParticipant(
            BlindMeetingParticipantStatus.replaced,
            status,
          ),
          isFalse,
        );
      }
    });

    test('신청 상태에서 곧바로 확정될 수 없다', () {
      expect(
        canTransitionParticipant(
          BlindMeetingParticipantStatus.applied,
          BlindMeetingParticipantStatus.confirmed,
        ),
        isFalse,
      );
    });

    test('교체된 참가자는 채팅 멤버십을 갖지 않는다', () {
      expect(
        BlindMeetingParticipantStatus.replaced.holdsChatMembership,
        isFalse,
      );
      expect(
        BlindMeetingParticipantStatus.cancelled.holdsChatMembership,
        isFalse,
      );
      expect(
        BlindMeetingParticipantStatus.confirmed.holdsChatMembership,
        isTrue,
      );
    });
  });

  group('세션 팀 조회', () {
    final session = BlindMeetingSession(
      meetingId: 'm1',
      status: BlindMeetingStatus.chatOpen,
      teamAUserIds: const ['a1', 'a2', 'a3'],
      teamBUserIds: const ['b1', 'b2', 'b3'],
      participantIds: const ['a1', 'a2', 'a3', 'b1', 'b2', 'b3'],
    );

    test('참가자의 팀을 찾는다', () {
      expect(session.teamOf('a2'), BlindMeetingTeam.teamA);
      expect(session.teamOf('b3'), BlindMeetingTeam.teamB);
      expect(session.teamOf('zz'), isNull);
    });

    test('상대 팀만 후속 선택 대상이 된다', () {
      expect(session.opponentIdsOf('a1'), ['b1', 'b2', 'b3']);
      expect(session.opponentIdsOf('b1'), ['a1', 'a2', 'a3']);
      expect(session.opponentIdsOf('zz'), isEmpty);
    });
  });

  group('슬롯 파싱', () {
    test('slotId 왕복 변환', () {
      const slot = BlindMeetingSlot(
        dateKey: '2026-08-01',
        timeBlock: BlindMeetingTimeBlock.evening,
      );
      expect(slot.slotId, '2026-08-01#evening');
      expect(BlindMeetingSlot.tryParse(slot.slotId), slot);
    });

    test('잘못된 값은 null', () {
      expect(BlindMeetingSlot.tryParse('20260801#evening'), isNull);
      expect(BlindMeetingSlot.tryParse('2026-08-01#none'), isNull);
      expect(BlindMeetingSlot.tryParse(null), isNull);
    });

    test('리스트는 정렬·중복 제거된다', () {
      final slots = BlindMeetingSlot.parseList([
        '2026-08-02#lunch',
        '2026-08-01#evening',
        '2026-08-01#evening',
        '2026-08-01#lunch',
      ]);
      expect(slots.map((s) => s.slotId).toList(), [
        '2026-08-01#lunch',
        '2026-08-01#evening',
        '2026-08-02#lunch',
      ]);
    });
  });

  group('비공개 DNA 검증', () {
    BlindMeetingDna dna({
      AlcoholCompanionPreference alcohol =
          AlcoholCompanionPreference.noPreference,
      DrinkingLevel drinking = DrinkingLevel.sometimes,
      List<String> dateKeys = const ['2026-08-01'],
      List<String> interests = const ['커피'],
    }) {
      return BlindMeetingDna(
        userId: 'u1',
        conversationAtmosphere: ConversationAtmosphere.calm,
        conversationInitiative: ConversationInitiative.adaptive,
        meetingPurpose: MeetingPurpose.both,
        alcoholCompanionPreference: alcohol,
        smokingCompanionPreference: SmokingCompanionPreference.noPreference,
        interestIds: interests,
        drinkingLevelSnapshot: drinking,
        smokingStatusSnapshot: SmokingStatus.nonSmoker,
        availableDateKeys: dateKeys,
      );
    }

    test('전원 비음주는 본인이 비음주일 때만 선택 가능', () {
      final invalid = dna(
        alcohol: AlcoholCompanionPreference.allSober,
        drinking: DrinkingLevel.sometimes,
      );
      expect(
        invalid.validate(),
        contains(BlindMeetingDnaViolation.allSoberRequiresSoberProfile),
      );

      final valid = dna(
        alcohol: AlcoholCompanionPreference.allSober,
        drinking: DrinkingLevel.none,
      );
      expect(valid.isValid, isTrue);
      expect(valid.belongsToAlcoholFreePool, isTrue);
    });

    test('가능한 날짜가 없으면 제출 불가', () {
      expect(
        dna(dateKeys: const []).validate(),
        contains(BlindMeetingDnaViolation.missingAvailability),
      );
    });

    test('날짜는 중복 제거 후 오름차순으로 저장된다', () {
      final payload = dna(
        dateKeys: const ['2026-08-05', '2026-08-01', '2026-08-05'],
      ).toWritePayload();
      expect(payload['availableDateKeys'], ['2026-08-01', '2026-08-05']);
      expect(payload['availabilityMode'], 'date_only');
      expect(payload['scheduleSelectionVersion'], 2);
    });

    test('write payload에 시간대 필드가 없다', () {
      final payload = dna().toWritePayload();
      expect(payload.keys, isNot(contains('availableSlots')));
      expect(payload.keys, isNot(contains('availableSlotIds')));
    });

    test('legacy 슬롯 문서에서 날짜만 복원한다', () {
      final restored = BlindMeetingDna.fromMap('u1', {
        'conversationAtmosphere': 'calm',
        'conversationInitiative': 'adaptive',
        'meetingPurpose': 'both',
        'alcoholCompanionPreference': 'noPreference',
        'smokingCompanionPreference': 'noPreference',
        'interestIds': ['커피'],
        'drinkingLevelSnapshot': 'sometimes',
        'smokingStatusSnapshot': 'nonSmoker',
        'availableSlotIds': [
          '2026-08-05#lunch',
          '2026-08-01#evening',
          '2026-08-01#lateEvening',
        ],
      });
      expect(restored!.availableDateKeys, ['2026-08-01', '2026-08-05']);
    });

    test('관심사가 없으면 제출 불가', () {
      expect(
        dna(interests: const []).validate(),
        contains(BlindMeetingDnaViolation.missingInterests),
      );
    });

    test('write payload에 내부 점수 필드가 없다', () {
      final payload = dna().toWritePayload();
      expect(payload.keys, isNot(contains('finalGroupScore')));
      expect(payload.keys, isNot(contains('crossTeamScore')));
      expect(payload['userId'], 'u1');
    });

    test('Firestore 왕복 변환', () {
      final original = dna(
        alcohol: AlcoholCompanionPreference.lightOkay,
        drinking: DrinkingLevel.none,
      );
      final restored = BlindMeetingDna.fromMap('u1', original.toWritePayload());
      expect(restored, isNotNull);
      expect(
        restored!.alcoholCompanionPreference,
        AlcoholCompanionPreference.lightOkay,
      );
      expect(restored.drinkingLevelSnapshot, DrinkingLevel.none);
      expect(restored.availableDateKeys, ['2026-08-01']);
    });
  });

  group('후속 선택 규칙', () {
    final now = DateTime.utc(2026, 8, 1, 22);
    BlindMeetingFollowUpState state({
      List<String> selectable = const ['b1', 'b2', 'b3'],
      DateTime? closesAt,
      bool attended = true,
      DateTime? submittedAt,
    }) {
      return BlindMeetingFollowUpState(
        selectableUids: selectable,
        choice: BlindMeetingFollowUpChoice(
          meetingId: 'm1',
          chooserUid: 'a1',
          submittedAt: submittedAt,
        ),
        closesAt: closesAt ?? now.add(const Duration(hours: 20)),
        chooserAttended: attended,
      );
    }

    test('최대 2명까지 선택 가능', () {
      expect(state().validate(['b1', 'b2'], now: now), isEmpty);
      expect(
        state().validate(['b1', 'b2', 'b3'], now: now),
        contains(BlindMeetingFollowUpViolation.tooManySelections),
      );
      expect(blindMeetingFollowUpMaxSelections, 2);
    });

    test('상대 팀 밖의 사용자는 선택 불가', () {
      expect(
        state().validate(['a2'], now: now),
        contains(BlindMeetingFollowUpViolation.ineligibleTarget),
      );
    });

    test('자기 자신은 선택 불가', () {
      expect(
        state().validate(['a1'], now: now),
        contains(BlindMeetingFollowUpViolation.selfSelection),
      );
    });

    test('마감 이후에는 제출 불가', () {
      final closed = state(closesAt: now.subtract(const Duration(minutes: 1)));
      expect(
        closed.validate(['b1'], now: now),
        contains(BlindMeetingFollowUpViolation.windowClosed),
      );
    });

    test('이미 제출했으면 다시 제출 불가', () {
      final submitted = state(submittedAt: now);
      expect(
        submitted.validate(['b1'], now: now),
        contains(BlindMeetingFollowUpViolation.alreadySubmitted),
      );
    });

    test('실제 참석자만 선택할 수 있다', () {
      expect(
        state(attended: false).validate(['b1'], now: now),
        contains(BlindMeetingFollowUpViolation.chooserNotAttended),
      );
    });

    test('선택 안 함(0명 제출)도 허용된다', () {
      expect(state().validate(const [], now: now), isEmpty);
    });

    test('신고·차단된 사용자가 목록에서 빠지면 선택할 수 없다', () {
      final filtered = state(selectable: const ['b1', 'b3']);
      expect(
        filtered.validate(['b2'], now: now),
        contains(BlindMeetingFollowUpViolation.ineligibleTarget),
      );
    });
  });
}
