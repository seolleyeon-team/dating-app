// =============================================================================
// 채팅 목록 탭 분류 (1:1 / 3:3)
// 경로: lib/features/chat/utils/chat_room_tab.dart
//
// 채팅 목록의 1:1 / 3:3 탭은 목업이 아니라 실제 room 문서의 discriminator 로
// 나눈다. 새 필드를 만들지 않고 서버가 이미 쓰는 값만 읽는다:
//   - roomType  : 'blind_meeting_group' (3:3 블라인드 취향 미팅, 서버 생성),
//                 'season_meeting_group' / 'event_season_meeting_group' /
//                 'three_vs_three_group' (시즌 미팅), 'blind_meeting_direct'
//                 (블라인드 후속 1:1), 'support', ...
//   - type      : 'group' / 'three_vs_three' / 'event_team_group' (시즌 미팅 legacy)
//   - eventType : 'season_meeting'
// firestore.rules 의 blindMeetingRoomTypes / seasonMeetingRoomTypes /
// seasonMeetingRoomGroupKinds 와 같은 기준이다.
//
// 멤버십 자체는 서버가 authoritative 하다: 목록 쿼리는
// where('participantIds', arrayContains: uid) 이고 rules 가 같은 조건으로
// 읽기를 제한하므로, 여기서는 "내가 참가 중인 방" 중에서 탭만 가른다.
// =============================================================================

enum ChatRoomTab { direct, group }

extension ChatRoomTabLabel on ChatRoomTab {
  String get label => switch (this) {
    ChatRoomTab.direct => '1:1',
    ChatRoomTab.group => '3:3',
  };

  int get index => switch (this) {
    ChatRoomTab.direct => 0,
    ChatRoomTab.group => 1,
  };

  static ChatRoomTab fromIndex(int index) =>
      index == 1 ? ChatRoomTab.group : ChatRoomTab.direct;

  /// 실제 방이 하나도 없을 때의 안내 문구.
  String get emptyMessage => switch (this) {
    ChatRoomTab.direct => '아직 1:1 대화가 없어요',
    ChatRoomTab.group => '아직 3:3 미팅 채팅이 없어요',
  };
}

/// 3:3 블라인드 취향 미팅 단체 채팅방 (서버 생성, 매칭 즉시).
const String kBlindMeetingGroupRoomType = 'blind_meeting_group';

/// 3:3 로 분류되는 roomType (블라인드 취향 미팅 + 시즌 미팅).
const Set<String> kGroupRoomTypes = {
  kBlindMeetingGroupRoomType,
  'season_meeting_group',
  'event_season_meeting_group',
  'three_vs_three_group',
};

/// 3:3 로 분류되는 legacy `type` 값 (시즌 미팅 문서).
const Set<String> kGroupRoomKinds = {'group', 'three_vs_three', 'event_team_group'};

/// room 문서의 discriminator 만 보고 탭을 정한다.
///
/// 3:3 = 서버가 만든 단체방(roomType/type/eventType 기준). 그 외(direct,
/// blind_meeting_direct, support, 필드 없는 legacy 1:1 방)는 모두 1:1 이다.
/// participantIds 인원수는 판정에 쓰지 않는다 — 탈퇴로 줄어든 3:3 방이
/// 1:1 로 새거나, 잘못 만들어진 방이 3:3 로 새는 것을 막기 위함이다.
ChatRoomTab classifyChatRoom(Map<String, dynamic> data) {
  final roomType = data['roomType']?.toString() ?? '';
  if (kGroupRoomTypes.contains(roomType)) return ChatRoomTab.group;
  if (roomType.isNotEmpty) return ChatRoomTab.direct;
  final kind = data['type']?.toString() ?? '';
  final eventType = data['eventType']?.toString() ?? '';
  if (kGroupRoomKinds.contains(kind) &&
      (eventType == 'season_meeting' ||
          data['threeVsThreeMatchId'] is String ||
          data['seasonMeetingMatchId'] is String ||
          data['eventThreeVsThreeMatchId'] is String)) {
    return ChatRoomTab.group;
  }
  return ChatRoomTab.direct;
}

/// 3:3 블라인드 취향 미팅 방인지 (매칭 즉시 서버가 만든 6인 방).
bool isBlindMeetingGroupRoom(Map<String, dynamic> data) =>
    data['roomType']?.toString() == kBlindMeetingGroupRoomType;

/// 탭에 속하는 room 문서만 남긴다 (순수 함수, 순서 유지).
List<T> filterRoomsForTab<T>(
  Iterable<T> rooms,
  ChatRoomTab tab,
  Map<String, dynamic> Function(T room) dataOf,
) {
  return rooms.where((room) => classifyChatRoom(dataOf(room)) == tab).toList();
}

/// 3:3 방의 목록 표시 이름.
///
/// 블라인드 미팅은 얼굴·실명을 공개하지 않으므로 방 이름은 미팅 종류로
/// 보여주고, 시즌 미팅 방은 문서의 name/title 을 우선 쓴다.
String groupRoomDisplayName(Map<String, dynamic> data) {
  final explicit = (data['name'] ?? data['title'])?.toString().trim() ?? '';
  if (explicit.isNotEmpty) return explicit;
  if (isBlindMeetingGroupRoom(data)) {
    return data['isAlcoholFree'] == true ? '무알코올 3:3 블라인드 미팅' : '3:3 블라인드 취향 미팅';
  }
  return '3:3 시즌 미팅';
}

/// 3:3 방의 부제 (참가 인원 요약). 닉네임만 쓰고 사진은 쓰지 않는다.
String groupRoomMemberSummary(
  Map<String, dynamic> data,
  String currentUserId,
) {
  final participantIds = List<String>.from(data['participantIds'] ?? const []);
  final info = Map<String, dynamic>.from(data['participantInfo'] ?? const {});
  final names = <String>[];
  for (final id in participantIds) {
    if (id == currentUserId) continue;
    final entry = info[id];
    final nickname = entry is Map ? entry['nickname']?.toString().trim() : null;
    if (nickname != null && nickname.isNotEmpty) names.add(nickname);
  }
  final count = participantIds.length;
  if (names.isEmpty) return '참가자 $count명';
  final shown = names.take(3).join(', ');
  return names.length > 3 ? '$shown 외 ${names.length - 3}명 · 총 $count명' : '$shown · 총 $count명';
}
