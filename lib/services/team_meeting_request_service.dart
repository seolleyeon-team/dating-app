import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:cloud_functions/cloud_functions.dart';

import '../data/models/event/event_team_match_model.dart';
import '../data/models/event/team_meeting_match_model.dart';
import '../data/models/event/team_meeting_request_model.dart';
import 'auth_service.dart';
import 'event_match_service.dart';
import 'storage_service.dart';

class TeamMeetingRequestService {
  TeamMeetingRequestService({
    FirebaseFirestore? firestore,
    FirebaseFunctions? functions,
    AuthService? authService,
    EventMatchService? eventMatchService,
    StorageService? storageService,
  }) : _firestore = firestore ?? FirebaseFirestore.instance,
       _functions = functions ?? FirebaseFunctions.instanceFor(region: _region),
       _authService = authService ?? AuthService(),
       _eventMatchService = eventMatchService ?? EventMatchService(),
       _storageService = storageService ?? StorageService();

  static const String _region = 'asia-northeast3';
  static const String _requestsCollection = 'eventTeamMeetingRequests';
  static const String _matchesCollection = 'eventThreeVsThreeMatches';

  final FirebaseFirestore _firestore;
  final FirebaseFunctions _functions;
  final AuthService _authService;
  final EventMatchService _eventMatchService;
  final StorageService _storageService;

  Future<String> _requireFirebaseReadSession() async {
    final userId = await _storageService.getKakaoUserId();
    if (userId == null || userId.isEmpty) {
      throw StateError('?????? ??????.');
    }
    final attached = await _authService.ensureCanonicalAppSession();
    if (!attached) {
      throw StateError('???????????????? ??????. ??? ???????????');
    }
    return userId;
  }

  Future<Map<String, dynamic>> _callablePayload(
    Map<String, dynamic> extra,
  ) async {
    await _requireFirebaseReadSession();
    final token = await _authService.getKakaoAccessTokenForFunctions();
    return <String, dynamic>{
      ...extra,
      if (token != null && token.isNotEmpty) 'kakaoAccessToken': token,
    };
  }

  Future<String?> resolveCurrentTeamId() {
    return _eventMatchService.resolveCurrentGroupId(requireFullTeam: true);
  }

  Future<String> createMeetingRequest({
    required EventTeamMatchResult matchResult,
    required String viewerGroupId,
  }) async {
    try {
      final payload = await _callablePayload({
        'sourceResultId': matchResult.resultId,
        'viewerGroupId': viewerGroupId,
      });
      final callable = _functions.httpsCallable('createTeamMeetingRequest');
      final response = await callable.call<dynamic>(payload);
      final data = _responseMap(response.data);
      final requestId = data['requestId']?.toString() ?? '';
      if (requestId.isEmpty) {
        throw StateError('??? ?????????? ??????.');
      }
      return requestId;
    } on FirebaseFunctionsException catch (error) {
      throw StateError(_functionsErrorMessage(error));
    }
  }

  Future<String> acceptRequest(String requestId) async {
    try {
      final payload = await _callablePayload({
        'requestId': requestId,
        'accept': true,
      });
      final callable = _functions.httpsCallable('respondTeamMeetingRequest');
      final response = await callable.call<dynamic>(payload);
      final matchId = _responseMap(response.data)['matchId']?.toString() ?? '';
      if (matchId.isEmpty) {
        throw StateError('??? ??? ??????????? ??????.');
      }
      return matchId;
    } on FirebaseFunctionsException catch (error) {
      throw StateError(_functionsErrorMessage(error));
    }
  }

  Future<void> declineRequest(String requestId) async {
    try {
      final payload = await _callablePayload({
        'requestId': requestId,
        'accept': false,
      });
      final callable = _functions.httpsCallable('respondTeamMeetingRequest');
      await callable.call<dynamic>(payload);
    } on FirebaseFunctionsException catch (error) {
      throw StateError(_functionsErrorMessage(error));
    }
  }

  Map<String, dynamic> _responseMap(dynamic value) {
    return Map<String, dynamic>.from(
      (value as Map?)?.cast<String, dynamic>() ?? const {},
    );
  }

  String _functionsErrorMessage(FirebaseFunctionsException error) {
    switch (error.code) {
      case 'invalid-argument':
        return '??? ????? ?????? ?????';
      case 'already-exists':
        return '??? ??? ??? ??? ??????????';
      case 'not-found':
        return '??? ???????? ???????';
      case 'permission-denied':
      case 'unauthenticated':
        return '??????????????????????';
      case 'failed-precondition':
      case 'aborted':
        return '??? ????? ????????. ??? ?????????.';
      case 'resource-exhausted':
      case 'unavailable':
        return '??? ????? ?????????.';
      default:
        return '??? ??????????? ??????.';
    }
  }

  Stream<List<TeamMeetingRequestDoc>> watchReceivedRequests(String teamId) {
    return _watchTeamRequests(teamId: teamId, teamField: 'toTeamId');
  }

  Stream<List<TeamMeetingRequestDoc>> watchSentRequests(String teamId) {
    return _watchTeamRequests(teamId: teamId, teamField: 'fromTeamId');
  }

  Stream<int> watchPendingReceivedCount(String teamId) {
    return _watchTeamRequests(
      teamId: teamId,
      teamField: 'toTeamId',
      status: 'pending',
    ).map((requests) => requests.length);
  }

  Stream<List<TeamMeetingRequestDoc>> _watchTeamRequests({
    required String teamId,
    required String teamField,
    String? status,
  }) async* {
    final userId = await _requireFirebaseReadSession();
    Query<Map<String, dynamic>> query = _firestore
        .collection(_requestsCollection)
        .where('participantUids', arrayContains: userId)
        .where(teamField, isEqualTo: teamId);
    if (status != null) {
      query = query.where('status', isEqualTo: status);
    } else {
      query = query.orderBy('createdAt', descending: true);
    }
    yield* query.snapshots().map(
      (snapshot) => snapshot.docs
          .map((doc) => TeamMeetingRequestDoc.fromDoc(doc.id, doc.data()))
          .toList(),
    );
  }

  Stream<TeamMeetingRequestDoc?> watchRequest(String requestId) async* {
    await _requireFirebaseReadSession();
    yield* _firestore
        .collection(_requestsCollection)
        .doc(requestId)
        .snapshots()
        .map((snapshot) {
          final data = snapshot.data();
          return snapshot.exists && data != null
              ? TeamMeetingRequestDoc.fromDoc(snapshot.id, data)
              : null;
        });
  }

  Future<TeamMeetingMatchDoc?> getMatchOnce(String matchId) async {
    await _requireFirebaseReadSession();
    final snapshot = await _firestore
        .collection(_matchesCollection)
        .doc(matchId)
        .get();
    final data = snapshot.data();
    return snapshot.exists && data != null
        ? TeamMeetingMatchDoc.fromDoc(snapshot.id, data)
        : null;
  }

  Stream<TeamMeetingMatchDoc?> watchMatch(String matchId) async* {
    await _requireFirebaseReadSession();
    yield* _firestore
        .collection(_matchesCollection)
        .doc(matchId)
        .snapshots()
        .map((snapshot) {
          final data = snapshot.data();
          return snapshot.exists && data != null
              ? TeamMeetingMatchDoc.fromDoc(snapshot.id, data)
              : null;
        });
  }

  Future<TeamMeetingRequestDoc?> getRequestOnce(String requestId) async {
    await _requireFirebaseReadSession();
    final snapshot = await _firestore
        .collection(_requestsCollection)
        .doc(requestId)
        .get();
    final data = snapshot.data();
    return snapshot.exists && data != null
        ? TeamMeetingRequestDoc.fromDoc(snapshot.id, data)
        : null;
  }
}
