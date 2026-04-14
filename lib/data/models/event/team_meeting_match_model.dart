import 'package:cloud_firestore/cloud_firestore.dart';

import 'event_team_match_model.dart';

// =============================================================================
// 3:3 팀 매칭 결과 Firestore 모델
// 컬렉션: eventThreeVsThreeMatches
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

class TeamMeetingMatchDoc {
  final String matchId;
  final String requestId;
  final String leftTeamId;
  final String rightTeamId;
  final EventTeamMatchTeamSnapshot? leftTeamSnapshot;
  final EventTeamMatchTeamSnapshot? rightTeamSnapshot;
  final List<String> leftMemberUids;
  final List<String> rightMemberUids;
  final String status;
  final String? acceptedByUserId;
  final String source;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  const TeamMeetingMatchDoc({
    required this.matchId,
    required this.requestId,
    required this.leftTeamId,
    required this.rightTeamId,
    this.leftTeamSnapshot,
    this.rightTeamSnapshot,
    required this.leftMemberUids,
    required this.rightMemberUids,
    required this.status,
    this.acceptedByUserId,
    required this.source,
    this.createdAt,
    this.updatedAt,
  });

  factory TeamMeetingMatchDoc.fromDoc(String id, Map<String, dynamic> data) {
    return TeamMeetingMatchDoc(
      matchId: id,
      requestId: data['requestId']?.toString() ?? '',
      leftTeamId: data['leftTeamId']?.toString() ?? '',
      rightTeamId: data['rightTeamId']?.toString() ?? '',
      leftTeamSnapshot: data['leftTeamSnapshot'] is Map
          ? EventTeamMatchTeamSnapshot.fromMap(_readMap(data['leftTeamSnapshot']))
          : null,
      rightTeamSnapshot: data['rightTeamSnapshot'] is Map
          ? EventTeamMatchTeamSnapshot.fromMap(_readMap(data['rightTeamSnapshot']))
          : null,
      leftMemberUids: _readStringList(data['leftMemberUids']),
      rightMemberUids: _readStringList(data['rightMemberUids']),
      status: data['status']?.toString() ?? 'active',
      acceptedByUserId: data['acceptedByUserId']?.toString(),
      source: data['source']?.toString() ?? 'team_request_accept',
      createdAt: _readDateTime(data['createdAt']),
      updatedAt: _readDateTime(data['updatedAt']),
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'requestId': requestId,
      'leftTeamId': leftTeamId,
      'rightTeamId': rightTeamId,
      'leftTeamSnapshot': leftTeamSnapshot?.toMap(),
      'rightTeamSnapshot': rightTeamSnapshot?.toMap(),
      'leftMemberUids': leftMemberUids,
      'rightMemberUids': rightMemberUids,
      'status': status,
      'acceptedByUserId': acceptedByUserId,
      'source': source,
      'createdAt': createdAt ?? FieldValue.serverTimestamp(),
      'updatedAt': updatedAt ?? FieldValue.serverTimestamp(),
    };
  }

  /// 현재 사용자가 어느 팀에 속하는지 확인하여 "내 팀" / "상대 팀" 결정
  bool isLeftTeamMember(String userId) => leftMemberUids.contains(userId);
  bool isRightTeamMember(String userId) => rightMemberUids.contains(userId);

  /// 현재 사용자 기준 내 팀 snapshot
  EventTeamMatchTeamSnapshot? myTeamSnapshot(String userId) {
    if (isLeftTeamMember(userId)) return leftTeamSnapshot;
    if (isRightTeamMember(userId)) return rightTeamSnapshot;
    return null;
  }

  /// 현재 사용자 기준 상대 팀 snapshot
  EventTeamMatchTeamSnapshot? opponentTeamSnapshot(String userId) {
    if (isLeftTeamMember(userId)) return rightTeamSnapshot;
    if (isRightTeamMember(userId)) return leftTeamSnapshot;
    return null;
  }
}
