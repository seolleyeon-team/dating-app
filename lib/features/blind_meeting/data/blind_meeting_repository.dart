// =============================================================================
// 3:3 블라인드 취향 미팅 — 데이터 레이어
// 경로: lib/features/blind_meeting/data/blind_meeting_repository.dart
//
// 읽기는 Firestore 구독, 쓰기와 상태 전환은 전부 Cloud Functions callable.
// 클라이언트는 미팅 상태·팀 배열·결제 상태·참석 상태를 직접 쓰지 않는다.
// =============================================================================

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:cloud_functions/cloud_functions.dart';

import '../../../services/auth_service.dart';
import '../../../services/storage_service.dart';
import '../domain/blind_meeting_application.dart';
import '../domain/blind_meeting_dna.dart';
import '../domain/blind_meeting_enums.dart';
import '../domain/blind_meeting_feedback.dart';
import '../domain/blind_meeting_followup.dart';
import '../domain/blind_meeting_public_profile.dart';
import '../domain/blind_meeting_session.dart';
import 'blind_meeting_profile_snapshot.dart';

/// Firestore 컬렉션 이름 (서버 구현과 동일해야 한다).
class BlindMeetingCollections {
  BlindMeetingCollections._();

  static const String meetings = 'blindMeetings';
  static const String applications = 'blindMeetingApplications';
  static const String dna = 'blindMeetingDna';
  static const String participants = 'participants';
  static const String publicProfiles = 'publicProfiles';
  static const String followUpChoices = 'followUpChoices';
  static const String replacementOffers = 'blindMeetingReplacementOffers';
  static const String feedback = 'feedback';
}

/// 보증금 결제 시도 결과.
///
/// 결제 provider가 아직 연결되지 않은 환경에서도 성공을 가짜로 만들지 않는다.
class BlindMeetingDepositIntent {
  final BlindMeetingDepositStatus status;
  final String provider;
  final int amount;

  /// 외부 결제 페이지가 필요한 경우의 URL.
  final String? checkoutUrl;

  /// sandbox/emulator 결제인지.
  final bool sandbox;

  /// 사용자에게 보여줄 안내 문구.
  final String? message;

  const BlindMeetingDepositIntent({
    required this.status,
    required this.provider,
    required this.amount,
    this.checkoutUrl,
    this.sandbox = false,
    this.message,
  });

  bool get requiresExternalCheckout =>
      checkoutUrl != null && checkoutUrl!.isNotEmpty;

  static BlindMeetingDepositIntent fromMap(Map<String, dynamic> data) {
    final amount = data['amount'];
    return BlindMeetingDepositIntent(
      status: enumFromName(
        BlindMeetingDepositStatus.values,
        data['status'],
        fallback: BlindMeetingDepositStatus.pending,
      ),
      provider: data['provider']?.toString() ?? 'unknown',
      amount: amount is num ? amount.toInt() : 0,
      checkoutUrl: _nullableString(data['checkoutUrl']),
      sandbox: data['sandbox'] == true,
      message: _nullableString(data['message']),
    );
  }
}

/// 참가 신청 제출 결과.
class BlindMeetingApplicationResult {
  final bool accepted;
  final BlindMeetingMatchingStage stage;
  final String? meetingId;
  final String? message;

  const BlindMeetingApplicationResult({
    required this.accepted,
    required this.stage,
    this.meetingId,
    this.message,
  });

  static BlindMeetingApplicationResult fromMap(Map<String, dynamic> data) {
    return BlindMeetingApplicationResult(
      accepted: data['accepted'] == true || data['ok'] == true,
      stage: enumFromName(
        BlindMeetingMatchingStage.values,
        data['stage'],
        fallback: BlindMeetingMatchingStage.searchingCandidates,
      ),
      meetingId: _nullableString(data['meetingId']),
      message: _nullableString(data['message']),
    );
  }
}

/// 블라인드 취향 미팅 저장소.
class BlindMeetingRepository {
  BlindMeetingRepository({
    FirebaseFirestore? firestore,
    FirebaseFunctions? functions,
    AuthService? authService,
    StorageService? storageService,
  }) : _firestore = firestore ?? FirebaseFirestore.instance,
       _functions = functions ?? FirebaseFunctions.instanceFor(region: _region),
       _authService = authService ?? AuthService(),
       _storageService = storageService ?? StorageService();

  static const String _region = 'asia-northeast3';

  final FirebaseFirestore _firestore;
  final FirebaseFunctions _functions;
  final AuthService _authService;
  final StorageService _storageService;

  // ---------------------------------------------------------------------------
  // 인증
  // ---------------------------------------------------------------------------

  Future<String?> currentUserId() => _storageService.getKakaoUserId();

  /// 비공개 DNA는 Firebase Auth 세션(uid == kakaoUserId)이 있어야 읽을 수 있다.
  Future<String> _requireSession() async {
    final userId = await currentUserId();
    if (userId == null || userId.isEmpty) {
      throw StateError('로그인이 필요해요.');
    }
    await _authService.ensureFirebaseSessionForKakao(userId);
    return userId;
  }

  Future<Map<String, dynamic>> _callablePayload(
    Map<String, dynamic> extra,
  ) async {
    final userId = await _requireSession();
    final token = await _authService.getKakaoAccessTokenForFunctions();
    final payload = <String, dynamic>{...extra, 'userId': userId};
    if (token != null && token.isNotEmpty) {
      payload['kakaoAccessToken'] = token;
    }
    return payload;
  }

  Future<Map<String, dynamic>> _call(
    String name,
    Map<String, dynamic> data,
  ) async {
    final payload = await _callablePayload(data);
    final result = await _functions.httpsCallable(name).call<dynamic>(payload);
    final raw = result.data;
    if (raw is Map) {
      return Map<String, dynamic>.from(raw.cast<String, dynamic>());
    }
    return <String, dynamic>{};
  }

  // ---------------------------------------------------------------------------
  // 온보딩 스냅샷
  // ---------------------------------------------------------------------------

  /// 관심사·음주·흡연·MBTI 등 기존 온보딩 값을 불러온다.
  Future<BlindMeetingProfileSnapshot?> loadProfileSnapshot() async {
    final userId = await currentUserId();
    if (userId == null || userId.isEmpty) return null;
    final snapshot = await _firestore.collection('users').doc(userId).get();
    final data = snapshot.data();
    if (data == null) return null;
    return BlindMeetingProfileSnapshot.fromUserDoc(
      userId,
      normalizeFirestoreMap(data),
    );
  }

  // ---------------------------------------------------------------------------
  // 비공개 DNA / 신청
  // ---------------------------------------------------------------------------

  /// 내 비공개 DNA 구독. 다른 사용자의 DNA는 rules에서 차단된다.
  Stream<BlindMeetingDna?> watchMyDna() {
    return _ownerDocStream(BlindMeetingCollections.dna).map((entry) {
      if (entry == null) return null;
      return BlindMeetingDna.fromMap(entry.key, entry.value);
    });
  }

  Future<BlindMeetingDna?> loadMyDna() async {
    final userId = await _requireSession();
    final snapshot = await _firestore
        .collection(BlindMeetingCollections.dna)
        .doc(userId)
        .get();
    final data = snapshot.data();
    if (data == null) return null;
    return BlindMeetingDna.fromMap(userId, normalizeFirestoreMap(data));
  }

  /// 내 신청 상태 구독 (대기 화면의 단일 소스).
  Stream<BlindMeetingApplication?> watchMyApplication() {
    return _ownerDocStream(BlindMeetingCollections.applications).map((entry) {
      if (entry == null) return null;
      return BlindMeetingApplication.fromMap(entry.key, entry.value);
    });
  }

  /// 참가 신청 제출. 서버가 DNA 검증과 후보군 분리를 수행한다.
  Future<BlindMeetingApplicationResult> submitApplication(
    BlindMeetingDna dna,
  ) async {
    final result = await _call('submitBlindMeetingApplication', {
      'dna': dna.toWritePayload(),
    });
    return BlindMeetingApplicationResult.fromMap(result);
  }

  Future<void> cancelApplication() async {
    await _call('cancelBlindMeetingApplication', const {});
  }

  /// 무알코올 조건 완화는 사용자가 직접 선택해야만 적용된다.
  Future<void> applyRelaxationChoice(
    BlindMeetingRelaxationChoice choice, {
    List<String> additionalSlotIds = const <String>[],
  }) async {
    await _call('relaxBlindMeetingConditions', {
      'choice': choice.name,
      'additionalSlotIds': additionalSlotIds,
    });
  }

  // ---------------------------------------------------------------------------
  // 미팅 세션
  // ---------------------------------------------------------------------------

  Stream<BlindMeetingSession?> watchMeeting(String meetingId) {
    if (meetingId.isEmpty) return Stream<BlindMeetingSession?>.value(null);
    return _firestore
        .collection(BlindMeetingCollections.meetings)
        .doc(meetingId)
        .snapshots()
        .map((snapshot) {
          final data = snapshot.data();
          if (data == null) return null;
          return BlindMeetingSession.fromMap(
            snapshot.id,
            normalizeFirestoreMap(data),
          );
        });
  }

  /// 추천 결과 화면 데이터 (우리 팀 / 상대 팀 분리).
  Future<BlindMeetingRecommendationView?> loadRecommendation(
    String meetingId,
  ) async {
    final userId = await currentUserId();
    if (userId == null || userId.isEmpty || meetingId.isEmpty) return null;

    final meetingRef = _firestore
        .collection(BlindMeetingCollections.meetings)
        .doc(meetingId);
    final meetingSnap = await meetingRef.get();
    final meetingData = meetingSnap.data();
    if (meetingData == null) return null;

    final session = BlindMeetingSession.fromMap(
      meetingSnap.id,
      normalizeFirestoreMap(meetingData),
    );
    final viewerTeam = session.teamOf(userId);
    if (viewerTeam == null) return null;

    final profilesSnap = await meetingRef
        .collection(BlindMeetingCollections.publicProfiles)
        .get();
    final profiles = <String, BlindMeetingPublicProfile>{};
    for (final doc in profilesSnap.docs) {
      final profile = BlindMeetingPublicProfile.fromMap({
        'userId': doc.id,
        ...normalizeFirestoreMap(doc.data()),
      });
      profiles[doc.id] = profile;
    }

    final myTeamIds = viewerTeam == BlindMeetingTeam.teamA
        ? session.teamAUserIds
        : session.teamBUserIds;
    final opponentIds = session.opponentIdsOf(userId);

    final participantSnap = await meetingRef
        .collection(BlindMeetingCollections.participants)
        .doc(userId)
        .get();
    final participantData = participantSnap.data();

    return BlindMeetingRecommendationView(
      session: session,
      viewerTeam: viewerTeam,
      myTeam: myTeamIds
          .map((id) => profiles[id])
          .whereType<BlindMeetingPublicProfile>()
          .toList(),
      opponentTeam: opponentIds
          .map((id) => profiles[id])
          .whereType<BlindMeetingPublicProfile>()
          .toList(),
      me: participantData == null
          ? null
          : BlindMeetingParticipant.fromMap(
              userId,
              normalizeFirestoreMap(participantData),
            ),
    );
  }

  Stream<BlindMeetingParticipant?> watchMyParticipant(String meetingId) async* {
    final userId = await currentUserId();
    if (userId == null || userId.isEmpty || meetingId.isEmpty) {
      yield null;
      return;
    }
    yield* _firestore
        .collection(BlindMeetingCollections.meetings)
        .doc(meetingId)
        .collection(BlindMeetingCollections.participants)
        .doc(userId)
        .snapshots()
        .map((snapshot) {
          final data = snapshot.data();
          if (data == null) return null;
          return BlindMeetingParticipant.fromMap(
            userId,
            normalizeFirestoreMap(data),
          );
        });
  }

  // ---------------------------------------------------------------------------
  // 확정 / 보증금
  // ---------------------------------------------------------------------------

  Future<void> acceptInvitation(String meetingId) async {
    await _call('acceptBlindMeetingInvitation', {'meetingId': meetingId});
  }

  Future<void> declineInvitation(String meetingId, {String? reason}) async {
    await _call('declineBlindMeetingInvitation', {
      'meetingId': meetingId,
      if (reason != null) 'reason': reason,
    });
  }

  Future<BlindMeetingDepositIntent> startDeposit(String meetingId) async {
    final result = await _call('startBlindMeetingDeposit', {
      'meetingId': meetingId,
    });
    return BlindMeetingDepositIntent.fromMap(result);
  }

  // ---------------------------------------------------------------------------
  // 일정 / 참석 / 대체
  // ---------------------------------------------------------------------------

  Future<void> voteSchedule({
    required String meetingId,
    required List<String> preferredSlotIds,
    String? preferredPlaceId,
  }) async {
    await _call('voteBlindMeetingSchedule', {
      'meetingId': meetingId,
      'preferredSlotIds': preferredSlotIds,
      if (preferredPlaceId != null) 'preferredPlaceId': preferredPlaceId,
    });
  }

  Future<void> confirmAttendance({
    required String meetingId,
    required String phase,
    required bool attending,
  }) async {
    await _call('confirmBlindMeetingAttendance', {
      'meetingId': meetingId,
      'phase': phase,
      'attending': attending,
    });
  }

  Future<void> respondReplacementOffer({
    required String offerId,
    required bool accept,
  }) async {
    await _call('respondBlindMeetingReplacementOffer', {
      'offerId': offerId,
      'accept': accept,
    });
  }

  Future<void> voteFivePersonException({
    required String meetingId,
    required bool agree,
  }) async {
    await _call('voteBlindMeetingFivePersonException', {
      'meetingId': meetingId,
      'agree': agree,
    });
  }

  Future<void> requestCancellation({
    required String meetingId,
    String? reason,
    bool emergency = false,
  }) async {
    await _call('requestBlindMeetingCancellation', {
      'meetingId': meetingId,
      if (reason != null) 'reason': reason,
      'emergency': emergency,
    });
  }

  // ---------------------------------------------------------------------------
  // 안전도장 / 만족도
  // ---------------------------------------------------------------------------

  Future<void> markSafetyStamp({
    required String meetingId,
    required String phase,
    Map<String, dynamic>? verification,
  }) async {
    await _call('markBlindMeetingSafetyStamp', {
      'meetingId': meetingId,
      'phase': phase,
      if (verification != null) 'verification': verification,
    });
  }

  Future<void> submitFeedback(BlindMeetingFeedback feedback) async {
    await _call('submitBlindMeetingFeedback', feedback.toWritePayload());
  }

  // ---------------------------------------------------------------------------
  // 후속 선택
  // ---------------------------------------------------------------------------

  /// 내 후속 선택 문서 구독. 다른 참가자의 선택은 rules에서 차단된다.
  Stream<BlindMeetingFollowUpChoice?> watchMyFollowUpChoice(
    String meetingId,
  ) async* {
    final userId = await currentUserId();
    if (userId == null || userId.isEmpty || meetingId.isEmpty) {
      yield null;
      return;
    }
    yield* _firestore
        .collection(BlindMeetingCollections.meetings)
        .doc(meetingId)
        .collection(BlindMeetingCollections.followUpChoices)
        .doc(userId)
        .snapshots()
        .map(
          (snapshot) => BlindMeetingFollowUpChoice.fromMap(
            meetingId,
            userId,
            snapshot.data() == null
                ? null
                : normalizeFirestoreMap(snapshot.data()!),
          ),
        );
  }

  Future<void> submitFollowUpChoice({
    required String meetingId,
    required List<String> selectedUids,
  }) async {
    await _call('submitBlindMeetingFollowUpChoice', {
      'meetingId': meetingId,
      'selectedUids': selectedUids,
    });
  }

  /// 상호 선택 결과 조회. 일방 선택 정보는 서버가 내려주지 않는다.
  Future<List<BlindMeetingMutualMatch>> loadMutualMatches(
    String meetingId,
  ) async {
    final result = await _call('getBlindMeetingMutualMatches', {
      'meetingId': meetingId,
    });
    final raw = result['matches'];
    if (raw is! Iterable) return const <BlindMeetingMutualMatch>[];
    return raw
        .map(BlindMeetingMutualMatch.fromMap)
        .whereType<BlindMeetingMutualMatch>()
        .toList();
  }

  // ---------------------------------------------------------------------------
  // 내부 유틸
  // ---------------------------------------------------------------------------

  Stream<MapEntry<String, Map<String, dynamic>>?> _ownerDocStream(
    String collection,
  ) async* {
    final userId = await _requireSession();
    yield* _firestore.collection(collection).doc(userId).snapshots().map((
      snapshot,
    ) {
      final data = snapshot.data();
      if (data == null) return null;
      return MapEntry(userId, normalizeFirestoreMap(data));
    });
  }
}

/// Firestore [Timestamp]를 [DateTime]으로 재귀 변환한다.
///
/// 도메인 모델이 cloud_firestore에 의존하지 않도록 경계에서 정규화한다.
Map<String, dynamic> normalizeFirestoreMap(Map<String, dynamic> data) {
  final result = <String, dynamic>{};
  data.forEach((key, value) {
    result[key] = _normalizeFirestoreValue(value);
  });
  return result;
}

Object? _normalizeFirestoreValue(Object? value) {
  if (value is Timestamp) return value.toDate();
  if (value is Map) {
    return normalizeFirestoreMap(
      Map<String, dynamic>.from(value.cast<String, dynamic>()),
    );
  }
  if (value is Iterable) {
    return value.map(_normalizeFirestoreValue).toList();
  }
  return value;
}

String? _nullableString(Object? raw) {
  final text = raw?.toString().trim() ?? '';
  return text.isEmpty ? null : text;
}
