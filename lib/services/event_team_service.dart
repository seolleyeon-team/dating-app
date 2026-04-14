import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:cloud_functions/cloud_functions.dart';

import 'auth_service.dart';
import 'friend_service.dart';
import 'storage_service.dart';
import 'user_service.dart';

/// 이벤트 3인 팀 Firestore 문서 (`eventTeamSetups`)
class EventTeamSetupState {
  final String teamSetupId;
  final String leaderUserId;
  final List<String> acceptedUserIds;
  final List<String> pendingInviteeIds;

  const EventTeamSetupState({
    required this.teamSetupId,
    required this.leaderUserId,
    required this.acceptedUserIds,
    required this.pendingInviteeIds,
  });

  factory EventTeamSetupState.fromDoc(
    String id,
    Map<String, dynamic> data,
  ) {
    final acc = data['acceptedUserIds'];
    final pend = data['pendingInviteeIds'];
    return EventTeamSetupState(
      teamSetupId: id,
      leaderUserId: data['leaderUserId']?.toString() ?? '',
      acceptedUserIds: acc is List
          ? acc.map((e) => e.toString()).where((e) => e.isNotEmpty).toList()
          : [],
      pendingInviteeIds: pend is List
          ? pend.map((e) => e.toString()).where((e) => e.isNotEmpty).toList()
          : [],
    );
  }

  /// 본인 포함 확정 멤버 수
  int get acceptedCount => acceptedUserIds.length;

  /// 슬롯머신은 실제로 수락이 완료된 3명일 때만 활성
  bool get canStartSlotMachine => acceptedUserIds.length == 3;

  int get remainingSlots => remainingMemberSlots;

  int get remainingMemberSlots {
    final remaining = 3 - acceptedUserIds.length;
    return remaining > 0 ? remaining : 0;
  }

  int get remainingInviteSlots {
    final remaining = 3 - acceptedUserIds.length - pendingInviteeIds.length;
    return remaining > 0 ? remaining : 0;
  }

  bool containsUser(String userId) {
    if (userId.isEmpty) return false;
    return leaderUserId == userId ||
        acceptedUserIds.contains(userId) ||
        pendingInviteeIds.contains(userId);
  }
}

/// Firestore `eventTeamInvites/{id}` (앱에서 읽기 전용)
class EventTeamInviteDoc {
  final String inviteId;
  final String teamSetupId;
  final String inviterUserId;
  final String inviteeUserId;
  final String status;
  final DateTime? createdAt;

  const EventTeamInviteDoc({
    required this.inviteId,
    required this.teamSetupId,
    required this.inviterUserId,
    required this.inviteeUserId,
    required this.status,
    this.createdAt,
  });

  factory EventTeamInviteDoc.fromSnap(
    DocumentSnapshot<Map<String, dynamic>> snap,
  ) {
    final d = snap.data() ?? {};
    final ts = d['createdAt'];
    DateTime? created;
    if (ts is Timestamp) created = ts.toDate();
    return EventTeamInviteDoc(
      inviteId: snap.id,
      teamSetupId: d['teamSetupId']?.toString() ?? '',
      inviterUserId: d['inviterUserId']?.toString() ?? '',
      inviteeUserId: d['inviteeUserId']?.toString() ?? '',
      status: d['status']?.toString() ?? '',
      createdAt: created,
    );
  }
}

/// 초대 상세 응답 시트에서 보여줄 초대자 프로필
class InviterProfile {
  final String userId;
  final String name;
  final String? imageUrl;
  final String? university;
  final String? mbti;
  final bool isStudentVerified;

  const InviterProfile({
    required this.userId,
    required this.name,
    this.imageUrl,
    this.university,
    this.mbti,
    this.isStudentVerified = false,
  });
}

class EventTeamMemberProfile {
  final String userId;
  final String name;
  final String mbti;
  final String? imageUrl;
  final bool isPending;

  const EventTeamMemberProfile({
    required this.userId,
    required this.name,
    required this.mbti,
    this.imageUrl,
    this.isPending = false,
  });
}

class EventTeamService {
  EventTeamService({
    FirebaseFunctions? functions,
    AuthService? authService,
    StorageService? storageService,
    UserService? userService,
    FriendService? friendService,
  })  : _functions =
            functions ?? FirebaseFunctions.instanceFor(region: _region),
        _authService = authService ?? AuthService(),
        _storageService = storageService ?? StorageService(),
        _userService = userService ?? UserService(),
        _friendService = friendService ?? FriendService();

  static const String _region = 'asia-northeast3';
  final FirebaseFunctions _functions;
  final AuthService _authService;
  final StorageService _storageService;
  final UserService _userService;
  final FriendService _friendService;
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  Future<Map<String, dynamic>> _callablePayload(
    Map<String, dynamic> extra,
  ) async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) {
      throw StateError('로그인이 필요해요.');
    }
    await _authService.ensureFirebaseSessionForKakao(kakaoUserId);
    final token = await _authService.getKakaoAccessTokenForFunctions();
    final map = Map<String, dynamic>.from(extra);
    if (token != null && token.isNotEmpty) {
      map['kakaoAccessToken'] = token;
    }
    return map;
  }

  Future<String> ensureTeamSetup({String? existingTeamSetupId}) async {
    final data = await _callablePayload({
      if (existingTeamSetupId != null && existingTeamSetupId.isNotEmpty)
        'teamSetupId': existingTeamSetupId,
    });
    final callable = _functions.httpsCallable('ensureEventTeamSetup');
    final res = await callable.call<dynamic>(data);
    final m = Map<String, dynamic>.from(
      (res.data as Map?)?.cast<String, dynamic>() ?? {},
    );
    final id = m['teamSetupId']?.toString() ?? '';
    if (id.isEmpty) throw StateError('팀 설정을 만들지 못했어요.');
    return id;
  }

  /// Cloud Function이 일시 실패해도, 로컬에 저장된 팀 ID가 Firestore에 있고 내가 리더면 화면만 살린다.
  Future<String?> recoverTeamSetupIfLeader({
    required String kakaoUserId,
    required String savedTeamSetupId,
  }) async {
    if (savedTeamSetupId.isEmpty) return null;
    final snap = await _firestore
        .collection('eventTeamSetups')
        .doc(savedTeamSetupId)
        .get();
    if (!snap.exists || snap.data() == null) return null;
    final leader = snap.data()!['leaderUserId']?.toString() ?? '';
    if (leader != kakaoUserId) return null;
    return savedTeamSetupId;
  }

  Future<void> createInvite({
    required String teamSetupId,
    required String inviteeUserId,
  }) async {
    final data = await _callablePayload({
      'teamSetupId': teamSetupId,
      'inviteeUserId': inviteeUserId,
    });
    final callable = _functions.httpsCallable('createEventTeamInvite');
    await callable.call<dynamic>(data);
  }

  Future<Map<String, dynamic>> respondInvite({
    required String inviteId,
    required bool accept,
  }) async {
    final data = await _callablePayload({
      'inviteId': inviteId,
      'accept': accept,
    });
    final callable = _functions.httpsCallable('respondEventTeamInvite');
    final res = await callable.call<dynamic>(data);
    return Map<String, dynamic>.from(
      (res.data as Map?)?.cast<String, dynamic>() ?? {},
    );
  }

  Stream<EventTeamSetupState?> watchTeamSetup(String teamSetupId) {
    return _firestore
        .collection('eventTeamSetups')
        .doc(teamSetupId)
        .snapshots()
        .map((s) {
      if (!s.exists || s.data() == null) return null;
      return EventTeamSetupState.fromDoc(s.id, s.data()!);
    });
  }

  Future<EventTeamSetupState?> getTeamSetupOnce(String teamSetupId) async {
    final s = await _firestore
        .collection('eventTeamSetups')
        .doc(teamSetupId)
        .get();
    if (!s.exists || s.data() == null) return null;
    return EventTeamSetupState.fromDoc(s.id, s.data()!);
  }

  Stream<EventTeamInviteDoc?> watchInvite(String inviteId) {
    return _firestore
        .collection('eventTeamInvites')
        .doc(inviteId)
        .snapshots()
        .map((s) {
      if (!s.exists || s.data() == null) return null;
      return EventTeamInviteDoc.fromSnap(s);
    });
  }

  Future<EventTeamInviteDoc?> getInviteOnce(String inviteId) async {
    final s = await _firestore
        .collection('eventTeamInvites')
        .doc(inviteId)
        .get();
    if (!s.exists || s.data() == null) return null;
    return EventTeamInviteDoc.fromSnap(s);
  }

  /// 현재 유저가 받은 pending 초대 목록 실시간 스트림
  Stream<List<EventTeamInviteDoc>> watchPendingInvitesForUser(
    String userId,
  ) {
    return _firestore
        .collection('eventTeamInvites')
        .where('inviteeUserId', isEqualTo: userId)
        .where('status', isEqualTo: 'pending')
        .snapshots()
        .map((qs) {
      final invites =
          qs.docs.map((d) => EventTeamInviteDoc.fromSnap(d)).toList();
      invites.sort((a, b) {
        final createdCompare = (b.createdAt?.millisecondsSinceEpoch ?? 0)
            .compareTo(a.createdAt?.millisecondsSinceEpoch ?? 0);
        if (createdCompare != 0) {
          return createdCompare;
        }
        return b.inviteId.compareTo(a.inviteId);
      });
      return invites;
    });
  }

  /// 초대자 프로필 상세 조회 (응답 시트용)
  Future<InviterProfile> getInviterProfile(String inviterUserId) async {
    if (inviterUserId.isEmpty) {
      return const InviterProfile(userId: '', name: '친구');
    }
    final user = await _userService.getUserProfile(inviterUserId);
    if (user == null) {
      return InviterProfile(userId: inviterUserId, name: '친구');
    }
    final raw = user['onboarding'];
    final ob =
        raw is Map ? Map<String, dynamic>.from(raw) : <String, dynamic>{};
    final name = _extractName(ob, user, inviterUserId);
    final photos = ob['photoUrls'];
    String? imageUrl;
    if (photos is List && photos.isNotEmpty) {
      imageUrl = photos.first.toString();
    }
    imageUrl = imageUrl ?? user['profileImageUrl']?.toString();
    if (imageUrl != null && imageUrl.isEmpty) imageUrl = null;
    final university = (ob['university']?.toString().trim().isNotEmpty == true)
        ? ob['university'].toString()
        : _inferUniversityFromEmail(user['studentEmail']?.toString());
    final mbti = ob['mbti']?.toString().trim().isNotEmpty == true
        ? ob['mbti'].toString()
        : null;
    final verified =
        user['isStudentVerified'] == true ||
        user['isStudentVerified'] == 'true';
    return InviterProfile(
      userId: inviterUserId,
      name: name,
      imageUrl: imageUrl,
      university: university,
      mbti: mbti,
      isStudentVerified: verified,
    );
  }

  String _extractName(
    Map<String, dynamic> ob,
    Map<String, dynamic> user,
    String fallback,
  ) {
    if (ob['nickname']?.toString().trim().isNotEmpty == true) {
      return ob['nickname'].toString();
    }
    if (user['nickname']?.toString().trim().isNotEmpty == true) {
      return user['nickname'].toString();
    }
    return fallback;
  }

  String _inferUniversityFromEmail(String? email) {
    final e = email?.trim().toLowerCase() ?? '';
    if (e.endsWith('@yonsei.ac.kr')) return '연세대학교';
    return '';
  }

  /// 팀 멤버 카드용 프로필 (수락 완료 멤버만)
  Future<List<EventTeamMemberProfile>> buildMemberProfiles({
    required EventTeamSetupState state,
    required String currentUserId,
  }) async {
    final List<EventTeamMemberProfile> out = [];

    for (final uid in state.acceptedUserIds) {
      final p = await _profileForUser(uid);
      out.add(
        EventTeamMemberProfile(
          userId: uid,
          name: p.$1,
          mbti: p.$2,
          imageUrl: p.$3,
          isPending: false,
        ),
      );
    }

    out.sort((a, b) {
      if (a.userId == currentUserId) return -1;
      if (b.userId == currentUserId) return 1;
      return 0;
    });

    return out;
  }

  Future<List<EventTeamMemberProfile>> buildPendingInviteProfiles({
    required EventTeamSetupState state,
  }) async {
    final List<EventTeamMemberProfile> out = [];

    for (final uid in state.pendingInviteeIds) {
      if (state.acceptedUserIds.contains(uid)) continue;
      final p = await _profileForUser(uid);
      out.add(
        EventTeamMemberProfile(
          userId: uid,
          name: p.$1,
          mbti: p.$2,
          imageUrl: p.$3,
          isPending: true,
        ),
      );
    }

    return out;
  }

  Future<(String, String, String?)> _profileForUser(String userId) async {
    final user = await _userService.getUserProfile(userId);
    if (user == null) {
      return (userId, '-', null);
    }
    final onboardingRaw = user['onboarding'];
    final onboarding = onboardingRaw is Map
        ? Map<String, dynamic>.from(onboardingRaw)
        : <String, dynamic>{};
    final name = (onboarding['nickname']?.toString().trim().isNotEmpty ??
            false)
        ? onboarding['nickname'].toString()
        : (user['nickname']?.toString().trim().isNotEmpty ?? false)
            ? user['nickname'].toString()
            : userId;
    final mbti = onboarding['mbti']?.toString().trim().isNotEmpty == true
        ? onboarding['mbti'].toString()
        : '—';
    final photos = onboarding['photoUrls'];
    String? url;
    if (photos is List && photos.isNotEmpty) {
      url = photos.first.toString();
    }
    url = url ?? user['profileImageUrl']?.toString();
    if (url != null && url.isEmpty) url = null;
    return (name, mbti, url);
  }

  /// 초대 가능한지(정원·pending·친구 여부) 클라이언트에서 1차 가드
  Future<bool> isFriend(String a, String b) async {
    final snap = await _firestore
        .collection('users')
        .doc(a)
        .collection('friends')
        .doc(b)
        .get();
    return snap.exists;
  }

  Future<Map<String, FriendListItem>> friendItemsMap(String userId) async {
    final qs = await _firestore
        .collection('users')
        .doc(userId)
        .collection('friends')
        .get();
    final items = await _friendService.hydrateFriends(qs.docs);
    return {for (final f in items) f.friendUserId: f};
  }
}
