// 채팅 목록 1:1 / 3:3 탭 분류 — 실제 room discriminator 기준 (목업 아님).

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/chat/utils/chat_room_tab.dart';

void main() {
  Map<String, dynamic> direct(String id) => {
    'roomId': id,
    'participantIds': ['me', 'other'],
    'participantInfo': {
      'other': {'nickname': '하늘'},
    },
  };

  Map<String, dynamic> blindGroup(String id, {bool alcoholFree = false}) => {
    'roomId': id,
    'roomType': 'blind_meeting_group',
    'meetingId': 'm1',
    'isAlcoholFree': alcoholFree,
    'participantIds': ['me', 'a2', 'a3', 'b1', 'b2', 'b3'],
    'participantInfo': {
      'a2': {'nickname': '수현'},
      'a3': {'nickname': '지우'},
      'b1': {'nickname': '하늘'},
      'b2': {'nickname': '태오'},
      'b3': {'nickname': '유진'},
    },
  };

  group('classifyChatRoom', () {
    test('direct / blind direct / support 방은 1:1', () {
      expect(classifyChatRoom(direct('dm_me_other')), ChatRoomTab.direct);
      expect(
        classifyChatRoom({'roomType': 'blind_meeting_direct'}),
        ChatRoomTab.direct,
      );
      expect(classifyChatRoom({'roomType': 'support'}), ChatRoomTab.direct);
      expect(classifyChatRoom({'roomType': 'direct'}), ChatRoomTab.direct);
    });

    test('블라인드 취향 미팅 단체방(서버 생성)은 3:3', () {
      expect(classifyChatRoom(blindGroup('blind_m1')), ChatRoomTab.group);
      expect(isBlindMeetingGroupRoom(blindGroup('blind_m1')), isTrue);
    });

    test('시즌 미팅 단체방(roomType / legacy type)은 3:3', () {
      for (final roomType in const [
        'season_meeting_group',
        'event_season_meeting_group',
        'three_vs_three_group',
      ]) {
        expect(classifyChatRoom({'roomType': roomType}), ChatRoomTab.group);
      }
      expect(
        classifyChatRoom({'type': 'group', 'eventType': 'season_meeting'}),
        ChatRoomTab.group,
      );
      expect(
        classifyChatRoom({'type': 'three_vs_three', 'threeVsThreeMatchId': 'x'}),
        ChatRoomTab.group,
      );
    });

    test('인원수만으로는 3:3 이 되지 않는다 (discriminator 없는 legacy 1:1)', () {
      expect(
        classifyChatRoom({
          'participantIds': ['a', 'b', 'c', 'd', 'e', 'f'],
        }),
        ChatRoomTab.direct,
      );
      expect(classifyChatRoom({'type': 'group'}), ChatRoomTab.direct);
    });
  });

  group('filterRoomsForTab', () {
    final rooms = [
      direct('D'),
      blindGroup('G'),
      {'roomId': 'S', 'roomType': 'season_meeting_group'},
    ];

    test('1:1 탭은 direct 만', () {
      final result = filterRoomsForTab(rooms, ChatRoomTab.direct, (r) => r);
      expect(result.map((r) => r['roomId']), ['D']);
    });

    test('3:3 탭은 단체방만 (블라인드 매칭 직후 생성된 방 포함)', () {
      final result = filterRoomsForTab(rooms, ChatRoomTab.group, (r) => r);
      expect(result.map((r) => r['roomId']), ['G', 'S']);
    });
  });

  group('3:3 표시', () {
    test('블라인드 방 이름과 참가자 요약 (사진 없음)', () {
      final data = blindGroup('G');
      expect(groupRoomDisplayName(data), '3:3 블라인드 취향 미팅');
      expect(
        groupRoomDisplayName(blindGroup('G', alcoholFree: true)),
        '무알코올 3:3 블라인드 미팅',
      );
      expect(groupRoomMemberSummary(data, 'me'), '수현, 지우, 하늘 외 2명 · 총 6명');
    });

    test('빈 상태 문구는 탭별로 다르다', () {
      expect(ChatRoomTab.direct.emptyMessage, '아직 1:1 대화가 없어요');
      expect(ChatRoomTab.group.emptyMessage, '아직 3:3 미팅 채팅이 없어요');
      expect(ChatRoomTabLabel.fromIndex(1), ChatRoomTab.group);
      expect(ChatRoomTabLabel.fromIndex(0), ChatRoomTab.direct);
    });
  });
}
