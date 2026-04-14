import 'package:cloud_firestore/cloud_firestore.dart';

import 'event_team_match_model.dart';

// =============================================================================
// 팀 대 팀 미팅 요청 Firestore 모델
// 컬렉션: eventTeamMeetingRequests
// =============================================================================

DateTime? _readDateTime(dynamic value) {
  if (value is Timestamp) return value.toDate();
  if (value is DateTime) return value;
  if (value is String && value.trim().isNotEmpty) return DateTime.tryParse(value);
  return null;
}

Map<String, dynamic> _readMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return value.map((k, v) => MapEntry(k.toString(), v));
  return <String, dynamic>{};
}

List<String> _readStringList(dynamic value) {
  if (value is List) {
    return value.map((e) => e.toString()).where((e) => e.isNotEmpty).toList();
  }
  return <String>[];
}

/// 미팅 요청 상태
enum TeamMeetingRequestStatus {
  pending,
  accepted,
  declined;

  static TeamMeetingRequestStatus fromString(String? value) {
    switch (value) {
      case 'accepted':
        return TeamMeetingRequestStatus.accepted;
      case 'declined':
        return TeamMeetingRequestStatus.declined;
      default:
        return TeamMeetingRequestStatus.pending;
    }
  }
}

class TeamMeetingRequestDoc {
  final String requestId;
  final String source;
  final String? sourceResultId;
  final String fromTeamId;
  final String toTeamId;
  final List<String> fromTeamMemberUids;
  final List<String> toTeamMemberUids;
  final EventTeamMatchTeamSnapshot? fromTeamSnapshot;
  final EventTeamMatchTeamSnapshot? toTeamSnapshot;
  final String createdByUserId;
  final TeamMeetingRequestStatus status;
  final String? respondedByUserId;
  final String? matchId;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? respondedAt;

  const TeamMeetingRequestDoc({
    required this.requestId,
    required this.source,
    this.sourceResultId,
    required this.fromTeamId,
    required this.toTeamId,
    required this.fromTeamMemberUids,
    required this.toTeamMemberUids,
    this.fromTeamSnapshot,
    this.toTeamSnapshot,
    required this.createdByUserId,
    required this.status,
    this.respondedByUserId,
    this.matchId,
    this.createdAt,
    this.updatedAt,
    this.respondedAt,
  });

  factory TeamMeetingRequestDoc.fromDoc(String id, Map<String, dynamic> data) {
    return TeamMeetingRequestDoc(
      requestId: id,
      source: data['source']?.toString() ?? 'slot_result',
      sourceResultId: data['sourceResultId']?.toString(),
      fromTeamId: data['fromTeamId']?.toString() ?? '',
      toTeamId: data['toTeamId']?.toString() ?? '',
      fromTeamMemberUids: _readStringList(data['fromTeamMemberUids']),
      toTeamMemberUids: _readStringList(data['toTeamMemberUids']),
      fromTeamSnapshot: data['fromTeamSnapshot'] is Map
          ? EventTeamMatchTeamSnapshot.fromMap(_readMap(data['fromTeamSnapshot']))
          : null,
      toTeamSnapshot: data['toTeamSnapshot'] is Map
          ? EventTeamMatchTeamSnapshot.fromMap(_readMap(data['toTeamSnapshot']))
          : null,
      createdByUserId: data['createdByUserId']?.toString() ?? '',
      status: TeamMeetingRequestStatus.fromString(data['status']?.toString()),
      respondedByUserId: data['respondedByUserId']?.toString(),
      matchId: data['matchId']?.toString(),
      createdAt: _readDateTime(data['createdAt']),
      updatedAt: _readDateTime(data['updatedAt']),
      respondedAt: _readDateTime(data['respondedAt']),
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'source': source,
      'sourceResultId': sourceResultId,
      'fromTeamId': fromTeamId,
      'toTeamId': toTeamId,
      'fromTeamMemberUids': fromTeamMemberUids,
      'toTeamMemberUids': toTeamMemberUids,
      'fromTeamSnapshot': fromTeamSnapshot?.toMap(),
      'toTeamSnapshot': toTeamSnapshot?.toMap(),
      'createdByUserId': createdByUserId,
      'status': status.name,
      'respondedByUserId': respondedByUserId,
      'matchId': matchId,
      'createdAt': createdAt ?? FieldValue.serverTimestamp(),
      'updatedAt': updatedAt ?? FieldValue.serverTimestamp(),
      'respondedAt': respondedAt,
    };
  }

  /// 지정된 userId가 받는 팀(receiver)에 속하는지 확인
  bool isReceiverMember(String userId) => toTeamMemberUids.contains(userId);

  /// 지정된 userId가 보낸 팀(sender)에 속하는지 확인
  bool isSenderMember(String userId) => fromTeamMemberUids.contains(userId);

  /// 현재 요청이 pending 상태인지 확인
  bool get isPending => status == TeamMeetingRequestStatus.pending;

  /// 지정된 teamId에 대한 상대 팀 snapshot 반환
  EventTeamMatchTeamSnapshot? counterpartSnapshotFor(String teamId) {
    if (teamId == fromTeamId) return toTeamSnapshot;
    if (teamId == toTeamId) return fromTeamSnapshot;
    return null;
  }

  /// 지정된 teamId에 대한 자기 팀 snapshot 반환
  EventTeamMatchTeamSnapshot? ownSnapshotFor(String teamId) {
    if (teamId == fromTeamId) return fromTeamSnapshot;
    if (teamId == toTeamId) return toTeamSnapshot;
    return null;
  }
}
