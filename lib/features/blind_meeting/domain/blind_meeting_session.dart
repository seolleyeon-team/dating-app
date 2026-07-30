// =============================================================================
// 3:3 블라인드 취향 미팅 — 세션 / 참가자 상태 모델
// 경로: lib/features/blind_meeting/domain/blind_meeting_session.dart
//
// Firestore 경로:
//   blindMeetings/{meetingId}
//   blindMeetings/{meetingId}/participants/{userId}
//   blindMeetings/{meetingId}/publicProfiles/{userId}
//   blindMeetings/{meetingId}/matchingResult/summary   (서버 전용)
//
// 클라이언트는 상태를 직접 바꾸지 않는다. 모든 상태 전환은 Cloud Functions가
// 수행하며, 여기 정의된 전환 표는 서버 로직과 UI 판단의 단일 기준이다.
// =============================================================================

import 'blind_meeting_enums.dart';
import 'blind_meeting_public_profile.dart';
import 'blind_meeting_slot.dart';

/// 허용된 미팅 상태 전환.
///
/// `cancelled` 는 종료 이전 어떤 상태에서도 가능하므로 별도로 처리한다.
const Map<BlindMeetingStatus, Set<BlindMeetingStatus>>
allowedMeetingTransitions = {
  BlindMeetingStatus.applicationOpen: {BlindMeetingStatus.forming},
  BlindMeetingStatus.forming: {
    BlindMeetingStatus.awaitingAcceptance,
    BlindMeetingStatus.applicationOpen,
  },
  BlindMeetingStatus.awaitingAcceptance: {
    BlindMeetingStatus.awaitingDeposits,
    BlindMeetingStatus.forming,
  },
  BlindMeetingStatus.awaitingDeposits: {
    BlindMeetingStatus.confirmed,
    BlindMeetingStatus.forming,
  },
  BlindMeetingStatus.confirmed: {BlindMeetingStatus.chatOpen},
  BlindMeetingStatus.chatOpen: {BlindMeetingStatus.scheduleConfirmed},
  BlindMeetingStatus.scheduleConfirmed: {
    BlindMeetingStatus.checkinOpen,
    BlindMeetingStatus.chatOpen,
  },
  BlindMeetingStatus.checkinOpen: {BlindMeetingStatus.inProgress},
  BlindMeetingStatus.inProgress: {BlindMeetingStatus.completed},
  BlindMeetingStatus.completed: {BlindMeetingStatus.followupOpen},
  BlindMeetingStatus.followupOpen: {BlindMeetingStatus.readOnly},
  BlindMeetingStatus.readOnly: {BlindMeetingStatus.archived},
  BlindMeetingStatus.archived: <BlindMeetingStatus>{},
  BlindMeetingStatus.cancelled: <BlindMeetingStatus>{},
};

/// 미팅 상태 전환이 허용되는지 판정한다.
bool canTransitionMeeting(BlindMeetingStatus from, BlindMeetingStatus to) {
  if (from == to) return false;
  if (from.isTerminal) return false;
  if (to == BlindMeetingStatus.cancelled) return true;
  return allowedMeetingTransitions[from]?.contains(to) ?? false;
}

/// 허용된 참가자 상태 전환.
const Map<BlindMeetingParticipantStatus, Set<BlindMeetingParticipantStatus>>
allowedParticipantTransitions = {
  BlindMeetingParticipantStatus.applied: {
    BlindMeetingParticipantStatus.waitlisted,
    BlindMeetingParticipantStatus.invited,
    BlindMeetingParticipantStatus.cancelled,
    BlindMeetingParticipantStatus.restricted,
  },
  BlindMeetingParticipantStatus.waitlisted: {
    BlindMeetingParticipantStatus.invited,
    BlindMeetingParticipantStatus.cancelled,
    BlindMeetingParticipantStatus.restricted,
  },
  BlindMeetingParticipantStatus.invited: {
    BlindMeetingParticipantStatus.accepted,
    BlindMeetingParticipantStatus.cancelled,
    BlindMeetingParticipantStatus.waitlisted,
  },
  BlindMeetingParticipantStatus.accepted: {
    BlindMeetingParticipantStatus.depositPending,
    BlindMeetingParticipantStatus.confirmed,
    BlindMeetingParticipantStatus.cancelRequested,
    BlindMeetingParticipantStatus.cancelled,
  },
  BlindMeetingParticipantStatus.depositPending: {
    BlindMeetingParticipantStatus.confirmed,
    BlindMeetingParticipantStatus.cancelRequested,
    BlindMeetingParticipantStatus.cancelled,
  },
  BlindMeetingParticipantStatus.confirmed: {
    BlindMeetingParticipantStatus.cancelRequested,
    BlindMeetingParticipantStatus.replacementPending,
    BlindMeetingParticipantStatus.attended,
    BlindMeetingParticipantStatus.noShow,
    BlindMeetingParticipantStatus.cancelled,
  },
  BlindMeetingParticipantStatus.cancelRequested: {
    BlindMeetingParticipantStatus.replacementPending,
    BlindMeetingParticipantStatus.cancelled,
    BlindMeetingParticipantStatus.confirmed,
  },
  BlindMeetingParticipantStatus.replacementPending: {
    BlindMeetingParticipantStatus.replaced,
    BlindMeetingParticipantStatus.confirmed,
    BlindMeetingParticipantStatus.cancelled,
  },
  BlindMeetingParticipantStatus.replaced: <BlindMeetingParticipantStatus>{},
  BlindMeetingParticipantStatus.cancelled: <BlindMeetingParticipantStatus>{},
  BlindMeetingParticipantStatus.noShow: {
    BlindMeetingParticipantStatus.restricted,
    BlindMeetingParticipantStatus.attended,
  },
  BlindMeetingParticipantStatus.attended: {
    BlindMeetingParticipantStatus.completed,
    BlindMeetingParticipantStatus.noShow,
  },
  BlindMeetingParticipantStatus.completed: <BlindMeetingParticipantStatus>{},
  BlindMeetingParticipantStatus.restricted: <BlindMeetingParticipantStatus>{},
};

/// 참가자 상태 전환이 허용되는지 판정한다.
bool canTransitionParticipant(
  BlindMeetingParticipantStatus from,
  BlindMeetingParticipantStatus to,
) {
  if (from == to) return false;
  return allowedParticipantTransitions[from]?.contains(to) ?? false;
}

/// 확정된 미팅 장소.
class BlindMeetingVenue {
  final String? placeId;
  final String name;
  final String? address;
  final String? category;
  final double? lat;
  final double? lng;

  /// 무알코올 미팅에 적합한 장소로 분류되었는지.
  final bool alcoholFreeFriendly;

  const BlindMeetingVenue({
    this.placeId,
    required this.name,
    this.address,
    this.category,
    this.lat,
    this.lng,
    this.alcoholFreeFriendly = false,
  });

  Map<String, dynamic> toMap() => {
    'placeId': placeId,
    'name': name,
    'address': address,
    'category': category,
    'lat': lat,
    'lng': lng,
    'alcoholFreeFriendly': alcoholFreeFriendly,
  };

  static BlindMeetingVenue? fromMap(Object? raw) {
    if (raw is! Map) return null;
    final name = raw['name']?.toString().trim() ?? '';
    if (name.isEmpty) return null;
    final lat = raw['lat'];
    final lng = raw['lng'];
    return BlindMeetingVenue(
      placeId: _nullableString(raw['placeId']),
      name: name,
      address: _nullableString(raw['address']),
      category: _nullableString(raw['category']),
      lat: lat is num ? lat.toDouble() : null,
      lng: lng is num ? lng.toDouble() : null,
      alcoholFreeFriendly: raw['alcoholFreeFriendly'] == true,
    );
  }
}

/// 참가자 상태 문서.
class BlindMeetingParticipant {
  final String userId;
  final BlindMeetingTeam team;
  final BlindMeetingParticipantStatus status;
  final BlindMeetingDepositStatus depositStatus;
  final AttendanceConfirmation attendanceConfirmation24h;
  final AttendanceConfirmation attendanceConfirmation3h;
  final bool checkedIn;
  final bool checkedOut;
  final bool isReplacement;
  final String? replacedUserId;
  final String? replacementUserId;
  final DateTime? acceptedAt;
  final DateTime? confirmedAt;
  final DateTime? cancelledAt;
  final DateTime? joinedChatAt;

  const BlindMeetingParticipant({
    required this.userId,
    required this.team,
    required this.status,
    this.depositStatus = BlindMeetingDepositStatus.notRequired,
    this.attendanceConfirmation24h = AttendanceConfirmation.pending,
    this.attendanceConfirmation3h = AttendanceConfirmation.pending,
    this.checkedIn = false,
    this.checkedOut = false,
    this.isReplacement = false,
    this.replacedUserId,
    this.replacementUserId,
    this.acceptedAt,
    this.confirmedAt,
    this.cancelledAt,
    this.joinedChatAt,
  });

  bool get holdsSeat => status.holdsChatMembership;

  /// 보증금 결제가 필요한데 아직 완료되지 않은 상태인지.
  bool get awaitsDeposit =>
      depositStatus == BlindMeetingDepositStatus.pending ||
      depositStatus == BlindMeetingDepositStatus.authorized ||
      depositStatus == BlindMeetingDepositStatus.failed;

  static BlindMeetingParticipant fromMap(
    String userId,
    Map<String, dynamic> data,
  ) {
    return BlindMeetingParticipant(
      userId: userId,
      team: enumFromName(
        BlindMeetingTeam.values,
        data['team'] ?? data['teamId'],
        fallback: BlindMeetingTeam.teamA,
      ),
      status: enumFromName(
        BlindMeetingParticipantStatus.values,
        data['status'],
        fallback: BlindMeetingParticipantStatus.applied,
      ),
      depositStatus: enumFromName(
        BlindMeetingDepositStatus.values,
        data['depositStatus'],
        fallback: BlindMeetingDepositStatus.notRequired,
      ),
      attendanceConfirmation24h: enumFromName(
        AttendanceConfirmation.values,
        data['attendanceConfirmation24h'],
        fallback: AttendanceConfirmation.pending,
      ),
      attendanceConfirmation3h: enumFromName(
        AttendanceConfirmation.values,
        data['attendanceConfirmation3h'],
        fallback: AttendanceConfirmation.pending,
      ),
      checkedIn:
          data['checkInStatus'] == 'completed' || data['checkedIn'] == true,
      checkedOut:
          data['checkOutStatus'] == 'completed' || data['checkedOut'] == true,
      isReplacement: data['isReplacement'] == true,
      replacedUserId: _nullableString(data['replacedUserId']),
      replacementUserId: _nullableString(data['replacementUserId']),
      acceptedAt: _dateTime(data['acceptedAt']),
      confirmedAt: _dateTime(data['confirmedAt']),
      cancelledAt: _dateTime(data['cancelledAt']),
      joinedChatAt: _dateTime(data['joinedChatAt']),
    );
  }
}

/// 미팅 세션 문서.
class BlindMeetingSession {
  static const int currentSchemaVersion = 2;

  final String meetingId;
  final BlindMeetingType meetingType;
  final int schemaVersion;
  final String algorithmVersion;
  final BlindMeetingStatus status;
  final BlindMeetingSlot? slot;
  final BlindMeetingVenue? venue;
  final bool isAlcoholFree;
  final List<String> teamAUserIds;
  final List<String> teamBUserIds;
  final List<String> participantIds;
  final List<String> waitlistIds;
  final String? groupChatId;
  final DateTime? scheduledStartAt;
  final DateTime? createdAt;
  final DateTime? confirmedAt;
  final DateTime? startedAt;
  final DateTime? completedAt;
  final DateTime? followupOpenedAt;
  final DateTime? followupClosesAt;
  final DateTime? archivedAt;

  /// 당일 노쇼로 5인 진행이 승인되었는지.
  final bool fivePersonExceptionApproved;

  /// 5인 진행 투표가 열려 있는지.
  final bool fivePersonVoteOpen;

  const BlindMeetingSession({
    required this.meetingId,
    this.meetingType = BlindMeetingType.blindTasteMeeting,
    this.schemaVersion = currentSchemaVersion,
    this.algorithmVersion = 'unknown',
    required this.status,
    this.slot,
    this.venue,
    this.isAlcoholFree = false,
    this.teamAUserIds = const <String>[],
    this.teamBUserIds = const <String>[],
    this.participantIds = const <String>[],
    this.waitlistIds = const <String>[],
    this.groupChatId,
    this.scheduledStartAt,
    this.createdAt,
    this.confirmedAt,
    this.startedAt,
    this.completedAt,
    this.followupOpenedAt,
    this.followupClosesAt,
    this.archivedAt,
    this.fivePersonExceptionApproved = false,
    this.fivePersonVoteOpen = false,
  });

  /// 특정 사용자가 속한 팀. 참가자가 아니면 null.
  BlindMeetingTeam? teamOf(String userId) {
    if (teamAUserIds.contains(userId)) return BlindMeetingTeam.teamA;
    if (teamBUserIds.contains(userId)) return BlindMeetingTeam.teamB;
    return null;
  }

  /// 상대 팀 구성원 목록. 참가자가 아니면 빈 목록.
  List<String> opponentIdsOf(String userId) {
    final team = teamOf(userId);
    return switch (team) {
      BlindMeetingTeam.teamA => teamBUserIds,
      BlindMeetingTeam.teamB => teamAUserIds,
      null => const <String>[],
    };
  }

  static BlindMeetingSession fromMap(
    String meetingId,
    Map<String, dynamic> data,
  ) {
    return BlindMeetingSession(
      meetingId: meetingId,
      meetingType: enumFromName(
        BlindMeetingType.values,
        data['meetingType'],
        fallback: BlindMeetingType.blindTasteMeeting,
      ),
      schemaVersion: _intOr(data['schemaVersion'], currentSchemaVersion),
      algorithmVersion: _stringOr(data['algorithmVersion'], 'unknown'),
      status: enumFromName(
        BlindMeetingStatus.values,
        data['status'],
        fallback: BlindMeetingStatus.applicationOpen,
      ),
      slot: BlindMeetingSlot.tryParse(data['slotId'] ?? data['slot']),
      venue: BlindMeetingVenue.fromMap(data['venue']),
      isAlcoholFree: data['isAlcoholFree'] == true,
      teamAUserIds: _stringList(data['teamAUserIds']),
      teamBUserIds: _stringList(data['teamBUserIds']),
      participantIds: _stringList(data['participantIds']),
      waitlistIds: _stringList(data['waitlistIds']),
      groupChatId: _nullableString(data['groupChatId']),
      scheduledStartAt: _dateTime(data['scheduledStartAt']),
      createdAt: _dateTime(data['createdAt']),
      confirmedAt: _dateTime(data['confirmedAt']),
      startedAt: _dateTime(data['startedAt']),
      completedAt: _dateTime(data['completedAt']),
      followupOpenedAt: _dateTime(data['followupOpenedAt']),
      followupClosesAt: _dateTime(data['followupClosesAt']),
      archivedAt: _dateTime(data['archivedAt']),
      fivePersonExceptionApproved: data['fivePersonExceptionApproved'] == true,
      fivePersonVoteOpen: data['fivePersonVoteOpen'] == true,
    );
  }
}

/// 추천 결과 화면에 필요한 모든 데이터 묶음.
class BlindMeetingRecommendationView {
  final BlindMeetingSession session;
  final BlindMeetingTeam viewerTeam;
  final List<BlindMeetingPublicProfile> myTeam;
  final List<BlindMeetingPublicProfile> opponentTeam;
  final BlindMeetingParticipant? me;

  const BlindMeetingRecommendationView({
    required this.session,
    required this.viewerTeam,
    required this.myTeam,
    required this.opponentTeam,
    required this.me,
  });
}

// -----------------------------------------------------------------------------
// 파싱 헬퍼
// -----------------------------------------------------------------------------

String? _nullableString(Object? raw) {
  final text = raw?.toString().trim() ?? '';
  return text.isEmpty ? null : text;
}

String _stringOr(Object? raw, String fallback) =>
    _nullableString(raw) ?? fallback;

int _intOr(Object? raw, int fallback) {
  if (raw is int) return raw;
  if (raw is num) return raw.toInt();
  return int.tryParse(raw?.toString() ?? '') ?? fallback;
}

List<String> _stringList(Object? raw) {
  if (raw is! Iterable) return const <String>[];
  final result = <String>[];
  for (final item in raw) {
    final text = item?.toString().trim() ?? '';
    if (text.isNotEmpty) result.add(text);
  }
  return List<String>.unmodifiable(result);
}

DateTime? _dateTime(Object? raw) {
  if (raw is DateTime) return raw;
  if (raw is int) return DateTime.fromMillisecondsSinceEpoch(raw);
  if (raw is num) return DateTime.fromMillisecondsSinceEpoch(raw.toInt());
  final text = raw?.toString();
  if (text == null || text.isEmpty) return null;
  return DateTime.tryParse(text);
}
