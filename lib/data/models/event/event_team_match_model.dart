import 'package:cloud_firestore/cloud_firestore.dart';

DateTime? _readDateTime(dynamic value) {
  if (value is Timestamp) return value.toDate();
  if (value is DateTime) return value;
  if (value is String && value.trim().isNotEmpty) {
    return DateTime.tryParse(value);
  }
  return null;
}

double? _readDouble(dynamic value) {
  if (value is num) return value.toDouble();
  if (value is String) return double.tryParse(value);
  return null;
}

int? _readInt(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}

Map<String, dynamic> _readMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) {
    return value.map(
      (key, item) => MapEntry(key.toString(), item),
    );
  }
  return <String, dynamic>{};
}

List<Map<String, dynamic>> _readMapList(dynamic value) {
  if (value is! List) return const <Map<String, dynamic>>[];
  return value.map(_readMap).toList();
}

class EventTeamMatchMemberSnapshot {
  final String uid;
  final String displayName;
  final String? photoUrl;
  final String? universityId;
  final String? universityName;
  final double? mannerScore;
  final bool isVerified;
  final String? shortIntro;
  final int? birthYear;
  final String? major;

  const EventTeamMatchMemberSnapshot({
    required this.uid,
    required this.displayName,
    this.photoUrl,
    this.universityId,
    this.universityName,
    this.mannerScore,
    this.isVerified = false,
    this.shortIntro,
    this.birthYear,
    this.major,
  });

  factory EventTeamMatchMemberSnapshot.fromMap(Map<String, dynamic> map) {
    final displayName = map['displayName']?.toString().trim();
    return EventTeamMatchMemberSnapshot(
      uid: map['uid']?.toString() ?? '',
      displayName: (displayName == null || displayName.isEmpty)
          ? '이름 미등록'
          : displayName,
      photoUrl: map['photoUrl']?.toString(),
      universityId: map['universityId']?.toString(),
      universityName: map['universityName']?.toString(),
      mannerScore: _readDouble(map['mannerScore']),
      isVerified: map['isVerified'] == true,
      shortIntro: map['shortIntro']?.toString(),
      birthYear: _readInt(map['birthYear']),
      major: map['major']?.toString(),
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'uid': uid,
      'displayName': displayName,
      'photoUrl': photoUrl,
      'universityId': universityId,
      'universityName': universityName,
      'mannerScore': mannerScore,
      'isVerified': isVerified,
      'shortIntro': shortIntro,
      'birthYear': birthYear,
      'major': major,
    };
  }
}

class EventTeamMatchTeamSnapshot {
  final String groupId;
  final String? sourceSetupId;
  final List<EventTeamMatchMemberSnapshot> members;
  final int memberCount;
  final double? score;
  final int? position;
  final bool isExplore;
  final List<Map<String, dynamic>> matchedPairs;

  const EventTeamMatchTeamSnapshot({
    required this.groupId,
    required this.members,
    required this.memberCount,
    this.sourceSetupId,
    this.score,
    this.position,
    this.isExplore = false,
    this.matchedPairs = const <Map<String, dynamic>>[],
  });

  factory EventTeamMatchTeamSnapshot.fromMap(Map<String, dynamic> map) {
    final memberMaps = map['membersSnapshot'] is List
        ? (map['membersSnapshot'] as List)
            .map((item) => EventTeamMatchMemberSnapshot.fromMap(_readMap(item)))
            .toList()
        : <EventTeamMatchMemberSnapshot>[];
    return EventTeamMatchTeamSnapshot(
      groupId: map['groupId']?.toString() ?? '',
      sourceSetupId: map['sourceSetupId']?.toString(),
      members: memberMaps,
      memberCount: _readInt(map['memberCount']) ?? memberMaps.length,
      score: _readDouble(map['score']),
      position: _readInt(map['position']),
      isExplore: map['isExplore'] == true,
      matchedPairs: _readMapList(map['matchedPairs']),
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'groupId': groupId,
      'sourceSetupId': sourceSetupId,
      'membersSnapshot': members.map((member) => member.toMap()).toList(),
      'memberCount': memberCount,
      'score': score,
      'position': position,
      'isExplore': isExplore,
      'matchedPairs': matchedPairs,
    };
  }
}

class EventTeamMatchResult {
  final String resultId;
  final String source;
  final String eventType;
  final String? seasonKey;
  final String dateKey;
  final String requestingEventTeamSetupId;
  final String requestingGroupId;
  final String matchedGroupId;
  final List<String> groupIds;
  final List<String> candidateGroupIds;
  final List<double> candidateScores;
  final int selectedGroupIndex;
  final String algorithm;
  final Map<String, dynamic> algorithmMeta;
  final String status;
  final EventTeamMatchTeamSnapshot? requestingTeam;
  final EventTeamMatchTeamSnapshot? matchedTeam;
  final List<EventTeamMatchTeamSnapshot> candidateTeams;
  final List<Map<String, dynamic>> matchedPairs;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  const EventTeamMatchResult({
    required this.resultId,
    required this.source,
    required this.eventType,
    required this.dateKey,
    required this.requestingEventTeamSetupId,
    required this.requestingGroupId,
    required this.matchedGroupId,
    required this.groupIds,
    required this.candidateGroupIds,
    required this.candidateScores,
    required this.selectedGroupIndex,
    required this.algorithm,
    required this.algorithmMeta,
    required this.status,
    this.seasonKey,
    this.requestingTeam,
    this.matchedTeam,
    this.candidateTeams = const <EventTeamMatchTeamSnapshot>[],
    this.matchedPairs = const <Map<String, dynamic>>[],
    this.createdAt,
    this.updatedAt,
  });

  factory EventTeamMatchResult.fromDoc(
    String id,
    Map<String, dynamic> map,
  ) {
    return EventTeamMatchResult(
      resultId: id,
      source: map['source']?.toString() ?? 'slot_machine',
      eventType: map['eventType']?.toString() ?? 'season_meeting',
      seasonKey: map['seasonKey']?.toString(),
      dateKey: map['dateKey']?.toString() ?? '',
      requestingEventTeamSetupId:
          map['requestingEventTeamSetupId']?.toString() ?? '',
      requestingGroupId: map['requestingGroupId']?.toString() ?? '',
      matchedGroupId: map['matchedGroupId']?.toString() ?? '',
      groupIds: map['groupIds'] is List
          ? (map['groupIds'] as List)
              .map((item) => item.toString())
              .where((item) => item.isNotEmpty)
              .toList()
          : <String>[],
      candidateGroupIds: map['candidateGroupIds'] is List
          ? (map['candidateGroupIds'] as List)
              .map((item) => item.toString())
              .where((item) => item.isNotEmpty)
              .toList()
          : <String>[],
      candidateScores: map['candidateScores'] is List
          ? (map['candidateScores'] as List)
              .map((item) => _readDouble(item) ?? 0)
              .toList()
          : <double>[],
      selectedGroupIndex: _readInt(map['selectedGroupIndex']) ?? 0,
      algorithm: map['algorithm']?.toString() ?? '',
      algorithmMeta: _readMap(map['algorithmMeta']),
      status: map['status']?.toString() ?? 'created',
      requestingTeam: map['requestingTeamSnapshot'] is Map
          ? EventTeamMatchTeamSnapshot.fromMap(
              _readMap(map['requestingTeamSnapshot']),
            )
          : null,
      matchedTeam: map['matchedTeamSnapshot'] is Map
          ? EventTeamMatchTeamSnapshot.fromMap(
              _readMap(map['matchedTeamSnapshot']),
            )
          : null,
      candidateTeams: map['candidateTeamsSnapshot'] is List
          ? (map['candidateTeamsSnapshot'] as List)
              .map(
                (item) => EventTeamMatchTeamSnapshot.fromMap(_readMap(item)),
              )
              .toList()
          : <EventTeamMatchTeamSnapshot>[],
      matchedPairs: _readMapList(
        map['matchedPairMeta'] ?? map['matchedPairs'],
      ),
      createdAt: _readDateTime(map['createdAt']),
      updatedAt: _readDateTime(map['updatedAt']),
    );
  }

  EventTeamMatchTeamSnapshot? counterpartForGroup(String? groupId) {
    if (groupId == null || groupId.isEmpty) {
      return matchedTeam ?? requestingTeam;
    }
    if (groupId == matchedGroupId) return requestingTeam;
    if (groupId == requestingGroupId) return matchedTeam;
    return matchedTeam ?? requestingTeam;
  }

  Map<String, dynamic> toMap() {
    return {
      'source': source,
      'eventType': eventType,
      'seasonKey': seasonKey,
      'dateKey': dateKey,
      'requestingEventTeamSetupId': requestingEventTeamSetupId,
      'requestingGroupId': requestingGroupId,
      'matchedGroupId': matchedGroupId,
      'groupIds': groupIds,
      'candidateGroupIds': candidateGroupIds,
      'candidateScores': candidateScores,
      'selectedGroupIndex': selectedGroupIndex,
      'algorithm': algorithm,
      'algorithmMeta': algorithmMeta,
      'status': status,
      'requestingTeamSnapshot': requestingTeam?.toMap(),
      'matchedTeamSnapshot': matchedTeam?.toMap(),
      'candidateTeamsSnapshot': candidateTeams.map((team) => team.toMap()).toList(),
      'matchedPairMeta': matchedPairs,
      'createdAt': createdAt,
      'updatedAt': updatedAt,
    };
  }
}

class EventTeamMatchSpinResponse {
  final EventTeamMatchResult result;
  final bool reusedExisting;
  final int selectedTeamIndex;
  final String viewerGroupId;

  const EventTeamMatchSpinResponse({
    required this.result,
    required this.reusedExisting,
    required this.selectedTeamIndex,
    required this.viewerGroupId,
  });

  factory EventTeamMatchSpinResponse.fromMap(Map<String, dynamic> map) {
    final resultMap = _readMap(map['result']);
    final resultId =
        map['resultId']?.toString() ?? resultMap['resultId']?.toString() ?? '';
    return EventTeamMatchSpinResponse(
      result: EventTeamMatchResult.fromDoc(resultId, resultMap),
      reusedExisting: map['reusedExisting'] == true,
      selectedTeamIndex: _readInt(map['selectedTeamIndex']) ?? 0,
      viewerGroupId: map['viewerGroupId']?.toString() ?? '',
    );
  }
}
