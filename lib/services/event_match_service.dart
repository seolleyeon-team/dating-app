import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:cloud_functions/cloud_functions.dart';

import '../data/models/event/event_team_match_model.dart';
import 'auth_service.dart';
import 'event_team_service.dart';
import 'storage_service.dart';

class EventMatchService {
  EventMatchService({
    FirebaseFirestore? firestore,
    FirebaseFunctions? functions,
    AuthService? authService,
    StorageService? storageService,
  })  : _firestore = firestore ?? FirebaseFirestore.instance,
        _functions =
            functions ?? FirebaseFunctions.instanceFor(region: _region),
        _authService = authService ?? AuthService(),
        _storageService = storageService ?? StorageService();

  static const String _region = 'asia-northeast3';

  final FirebaseFirestore _firestore;
  final FirebaseFunctions _functions;
  final AuthService _authService;
  final StorageService _storageService;

  Future<Map<String, dynamic>> _callablePayload(
    Map<String, dynamic> extra,
  ) async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) {
      throw StateError('로그인이 필요해요.');
    }

    await _authService.ensureFirebaseSessionForKakao(kakaoUserId);
    final token = await _authService.getKakaoAccessTokenForFunctions();
    final payload = Map<String, dynamic>.from(extra);
    if (token != null && token.isNotEmpty) {
      payload['kakaoAccessToken'] = token;
    }
    return payload;
  }

  Future<EventTeamMatchSpinResponse> spinSeasonMeetingRoulette({
    required String teamSetupId,
  }) async {
    final payload = await _callablePayload({
      'teamSetupId': teamSetupId,
    });

    final callable = _functions.httpsCallable('spinSeasonMeetingRoulette');
    final response = await callable.call<dynamic>(payload);
    final data = Map<String, dynamic>.from(
      (response.data as Map?)?.cast<String, dynamic>() ?? const {},
    );
    return EventTeamMatchSpinResponse.fromMap(data);
  }

  Stream<EventTeamMatchResult?> watchMatchResult(String resultId) {
    return _firestore.collection('eventTeamMatches').doc(resultId).snapshots().map(
      (snapshot) {
        if (!snapshot.exists || snapshot.data() == null) {
          return null;
        }
        return EventTeamMatchResult.fromDoc(snapshot.id, snapshot.data()!);
      },
    );
  }

  Future<EventTeamMatchResult?> getMatchResultOnce(String resultId) async {
    final snapshot = await _firestore.collection('eventTeamMatches').doc(resultId).get();
    if (!snapshot.exists || snapshot.data() == null) {
      return null;
    }
    return EventTeamMatchResult.fromDoc(snapshot.id, snapshot.data()!);
  }

  Future<String?> resolveCurrentGroupId({
    String? preferredTeamSetupId,
    bool requireFullTeam = false,
  }) async {
    final state = await resolveCurrentTeamSetup(
      preferredTeamSetupId: preferredTeamSetupId,
      requireFullTeam: requireFullTeam,
    );
    return state?.teamSetupId;
  }

  Future<EventTeamSetupState?> resolveCurrentTeamSetup({
    String? preferredTeamSetupId,
    bool requireFullTeam = false,
  }) async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) {
      return null;
    }

    final preferredIds = <String>[
      if (preferredTeamSetupId != null && preferredTeamSetupId.isNotEmpty)
        preferredTeamSetupId,
      ...(await _loadSavedPreferredIds(kakaoUserId)),
    ];

    for (final teamSetupId in preferredIds) {
      final state = await _readTeamSetupIfMember(
        teamSetupId: teamSetupId,
        userId: kakaoUserId,
      );
      if (state == null) continue;
      if (!requireFullTeam || state.canStartSlotMachine) {
        return state;
      }
    }

    final query = await _firestore
        .collection('eventTeamSetups')
        .where('acceptedUserIds', arrayContains: kakaoUserId)
        .get();

    final docs = query.docs.toList()
      ..sort((a, b) {
        final left = _timestampMs(a.data()['updatedAt']);
        final right = _timestampMs(b.data()['updatedAt']);
        return right.compareTo(left);
      });

    for (final doc in docs) {
      if (doc.data().isEmpty) continue;
      final state = EventTeamSetupState.fromDoc(doc.id, doc.data());
      if (!requireFullTeam || state.canStartSlotMachine) {
        return state;
      }
    }

    return null;
  }

  Future<List<String>> _loadSavedPreferredIds(String kakaoUserId) async {
    final saved = await _storageService.getEventTeamSetupDraftId(kakaoUserId);
    if (saved == null || saved.isEmpty) return const <String>[];
    return <String>[saved];
  }

  Future<EventTeamSetupState?> _readTeamSetupIfMember({
    required String teamSetupId,
    required String userId,
  }) async {
    final snapshot =
        await _firestore.collection('eventTeamSetups').doc(teamSetupId).get();
    if (!snapshot.exists || snapshot.data() == null) {
      return null;
    }
    final state = EventTeamSetupState.fromDoc(snapshot.id, snapshot.data()!);
    return state.containsUser(userId) ? state : null;
  }

  int _timestampMs(dynamic value) {
    if (value is Timestamp) return value.millisecondsSinceEpoch;
    if (value is DateTime) return value.millisecondsSinceEpoch;
    return 0;
  }
}
