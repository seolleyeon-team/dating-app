import 'package:cloud_firestore/cloud_firestore.dart';

enum BlindMeetingPartyStatus { forming, locked, ready, matched, cancelled }

class BlindMeetingPartyMemberProfile {
  final String userId;
  final String nickname;
  final String profileImageUrl;
  final String mbti;

  const BlindMeetingPartyMemberProfile({
    required this.userId,
    required this.nickname,
    required this.profileImageUrl,
    required this.mbti,
  });

  factory BlindMeetingPartyMemberProfile.fromMap(
    String userId,
    Map<String, dynamic> data,
  ) => BlindMeetingPartyMemberProfile(
    userId: userId,
    nickname: data['nickname']?.toString().trim().isNotEmpty == true
        ? data['nickname'].toString().trim()
        : '친구',
    profileImageUrl: data['profileImageUrl']?.toString().trim() ?? '',
    mbti: data['mbti']?.toString().trim() ?? '',
  );
}

class BlindMeetingParty {
  final String partyId;
  final String leaderUserId;
  final List<String> acceptedUserIds;
  final List<String> pendingInviteeIds;
  final List<String> completedApplicationUserIds;
  final BlindMeetingPartyStatus status;
  final int rosterVersion;
  final String? meetingId;
  final Map<String, BlindMeetingPartyMemberProfile> memberProfiles;

  const BlindMeetingParty({
    required this.partyId,
    required this.leaderUserId,
    required this.acceptedUserIds,
    required this.pendingInviteeIds,
    required this.completedApplicationUserIds,
    required this.status,
    required this.rosterVersion,
    required this.meetingId,
    required this.memberProfiles,
  });

  bool get isForming => status == BlindMeetingPartyStatus.forming;
  bool get isLocked => const {
    BlindMeetingPartyStatus.locked,
    BlindMeetingPartyStatus.ready,
    BlindMeetingPartyStatus.matched,
  }.contains(status);
  int get memberCount => acceptedUserIds.length;
  int get remainingInviteSlots =>
      (3 - acceptedUserIds.length - pendingInviteeIds.length).clamp(0, 3);

  factory BlindMeetingParty.fromDoc(
    DocumentSnapshot<Map<String, dynamic>> snapshot,
  ) {
    final data = snapshot.data() ?? const <String, dynamic>{};
    final profiles = <String, BlindMeetingPartyMemberProfile>{};
    final rawProfiles = data['memberProfiles'];
    if (rawProfiles is Map) {
      for (final entry in rawProfiles.entries) {
        if (entry.value is Map) {
          profiles[entry.key
              .toString()] = BlindMeetingPartyMemberProfile.fromMap(
            entry.key.toString(),
            Map<String, dynamic>.from(entry.value as Map),
          );
        }
      }
    }
    return BlindMeetingParty(
      partyId: snapshot.id,
      leaderUserId: data['leaderUserId']?.toString() ?? '',
      acceptedUserIds: _strings(data['acceptedUserIds']),
      pendingInviteeIds: _strings(data['pendingInviteeIds']),
      completedApplicationUserIds: _strings(
        data['completedApplicationUserIds'],
      ),
      status: BlindMeetingPartyStatus.values.firstWhere(
        (value) => value.name == data['status']?.toString(),
        orElse: () => BlindMeetingPartyStatus.cancelled,
      ),
      rosterVersion: (data['rosterVersion'] as num?)?.toInt() ?? 1,
      meetingId: _nullableString(data['meetingId']),
      memberProfiles: profiles,
    );
  }
}

class BlindMeetingPartyInvite {
  final String inviteId;
  final String partyId;
  final String inviterUserId;
  final String inviteeUserId;
  final String status;

  const BlindMeetingPartyInvite({
    required this.inviteId,
    required this.partyId,
    required this.inviterUserId,
    required this.inviteeUserId,
    required this.status,
  });

  factory BlindMeetingPartyInvite.fromDoc(
    DocumentSnapshot<Map<String, dynamic>> snapshot,
  ) {
    final data = snapshot.data() ?? const <String, dynamic>{};
    return BlindMeetingPartyInvite(
      inviteId: snapshot.id,
      partyId: data['partyId']?.toString() ?? '',
      inviterUserId: data['inviterUserId']?.toString() ?? '',
      inviteeUserId: data['inviteeUserId']?.toString() ?? '',
      status: data['status']?.toString() ?? '',
    );
  }
}

List<String> _strings(Object? raw) => raw is Iterable
    ? raw
          .map((item) => item.toString())
          .where((item) => item.isNotEmpty)
          .toList()
    : const <String>[];

String? _nullableString(Object? raw) {
  final value = raw?.toString().trim() ?? '';
  return value.isEmpty ? null : value;
}
