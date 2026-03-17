import 'package:cloud_firestore/cloud_firestore.dart';

/// 프로필 카드 인터랙션 (view / like / nope / super_like / message) 기록 서비스
///
/// Firestore 컬렉션:
///   interactions/{auto-id}   — 개별 인터랙션
///   matches/{auto-id}        — 매치 성사 기록
///   reports/{auto-id}        — 신고 기록
///   blocks/{fromUserId}/targets/{toUserId} — 차단 기록
class InteractionService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  CollectionReference<Map<String, dynamic>> get _interactionsRef =>
      _firestore.collection('interactions');

  CollectionReference<Map<String, dynamic>> get _matchesRef =>
      _firestore.collection('matches');

  CollectionReference<Map<String, dynamic>> get _reportsRef =>
      _firestore.collection('reports');

  // ---------------------------------------------------------------------------
  // 인터랙션 기록
  // ---------------------------------------------------------------------------

  /// 프로필 카드 조회 기록
  Future<void> recordView({
    required String fromUserId,
    required String toUserId,
    required String source,
  }) async {
    await _recordInteraction(
      fromUserId: fromUserId,
      toUserId: toUserId,
      action: 'view',
      source: source,
    );
  }

  /// Like 기록 + 매치 체크
  /// 매치 성사 시 matchId를 반환, 아니면 null
  Future<String?> recordLike({
    required String fromUserId,
    required String toUserId,
    required String source,
  }) async {
    await _recordInteraction(
      fromUserId: fromUserId,
      toUserId: toUserId,
      action: 'like',
      source: source,
    );

    return await _checkAndCreateMatch(
      userA: fromUserId,
      userB: toUserId,
      matchType: 'mutual_like',
    );
  }

  /// Super Like 기록 + 매치 체크
  Future<String?> recordSuperLike({
    required String fromUserId,
    required String toUserId,
    required String source,
  }) async {
    await _recordInteraction(
      fromUserId: fromUserId,
      toUserId: toUserId,
      action: 'super_like',
      source: source,
    );

    return await _checkAndCreateMatch(
      userA: fromUserId,
      userB: toUserId,
      matchType: 'mutual_like',
    );
  }

  /// Nope 기록
  Future<void> recordNope({
    required String fromUserId,
    required String toUserId,
    required String source,
  }) async {
    await _recordInteraction(
      fromUserId: fromUserId,
      toUserId: toUserId,
      action: 'nope',
      source: source,
    );
  }

  /// 메시지 전송 인터랙션 기록
  Future<void> recordMessage({
    required String fromUserId,
    required String toUserId,
    String? messagePreview,
  }) async {
    await _recordInteraction(
      fromUserId: fromUserId,
      toUserId: toUserId,
      action: 'message',
      source: 'chat',
      metadata: messagePreview != null
          ? {'messagePreview': messagePreview}
          : null,
    );
  }

  Future<void> _recordInteraction({
    required String fromUserId,
    required String toUserId,
    required String action,
    required String source,
    Map<String, dynamic>? metadata,
  }) async {
    await _interactionsRef.add({
      'fromUserId': fromUserId,
      'toUserId': toUserId,
      'action': action,
      'source': source,
      'metadata': metadata,
      'createdAt': FieldValue.serverTimestamp(),
    });
  }

  // ---------------------------------------------------------------------------
  // 매치 판정 (클라이언트 사이드 — 프로토타입용)
  // 프로덕션에서는 Cloud Function으로 이동 권장
  // ---------------------------------------------------------------------------

  Future<String?> _checkAndCreateMatch({
    required String userA,
    required String userB,
    required String matchType,
  }) async {
    final reverseQuery = await _interactionsRef
        .where('fromUserId', isEqualTo: userB)
        .where('toUserId', isEqualTo: userA)
        .where('action', whereIn: ['like', 'super_like'])
        .limit(1)
        .get();

    if (reverseQuery.docs.isEmpty) return null;

    final existingMatch = await _matchesRef
        .where('userIds', arrayContains: userA)
        .get();

    for (final doc in existingMatch.docs) {
      final ids = List<String>.from(doc.data()['userIds'] ?? []);
      if (ids.contains(userB)) {
        return doc.id;
      }
    }

    final matchRef = await _matchesRef.add({
      'userIds': [userA, userB],
      'matchType': matchType,
      'matchedAt': FieldValue.serverTimestamp(),
      'status': 'active',
      'chatRoomId': null,
    });

    return matchRef.id;
  }

  // ---------------------------------------------------------------------------
  // 조회 쿼리
  // ---------------------------------------------------------------------------

  /// 나에게 like한 유저 목록
  Future<List<Map<String, dynamic>>> getLikesReceived(String userId) async {
    final snap = await _interactionsRef
        .where('toUserId', isEqualTo: userId)
        .where('action', whereIn: ['like', 'super_like'])
        .orderBy('createdAt', descending: true)
        .get();

    return snap.docs.map((doc) => {'id': doc.id, ...doc.data()}).toList();
  }

  /// 내가 like한 유저 목록
  Future<List<Map<String, dynamic>>> getLikesSent(String userId) async {
    final snap = await _interactionsRef
        .where('fromUserId', isEqualTo: userId)
        .where('action', whereIn: ['like', 'super_like'])
        .orderBy('createdAt', descending: true)
        .get();

    return snap.docs.map((doc) => {'id': doc.id, ...doc.data()}).toList();
  }

  /// 특정 유저에게 이미 like/nope 했는지 확인 (중복 카드 방지)
  Future<bool> hasInteracted({
    required String fromUserId,
    required String toUserId,
  }) async {
    final snap = await _interactionsRef
        .where('fromUserId', isEqualTo: fromUserId)
        .where('toUserId', isEqualTo: toUserId)
        .where('action', whereIn: ['like', 'nope', 'super_like'])
        .limit(1)
        .get();

    return snap.docs.isNotEmpty;
  }

  /// 내 매치 목록
  Stream<List<Map<String, dynamic>>> myMatchesStream(String userId) {
    return _matchesRef
        .where('userIds', arrayContains: userId)
        .where('status', isEqualTo: 'active')
        .orderBy('matchedAt', descending: true)
        .snapshots()
        .map(
          (snap) =>
              snap.docs.map((doc) => {'id': doc.id, ...doc.data()}).toList(),
        );
  }

  /// 매치 해제
  Future<void> unmatch(String matchId) async {
    await _matchesRef.doc(matchId).update({
      'status': 'unmatched',
      'unmatchedAt': FieldValue.serverTimestamp(),
    });
  }

  // ---------------------------------------------------------------------------
  // 신고 및 차단
  // ---------------------------------------------------------------------------

  /// 유저 신고 및 차단
  ///
  /// 순서:
  /// 1. reports/ 컬렉션에 신고 상세 내용 저장
  /// 2. blocks/{fromUserId}/targets/{toUserId} 에 차단 기록 생성
  /// 3. 기존 매치가 있다면 해제 처리
  ///
  /// 핵심:
  /// - 신고 기록은 최우선으로 저장
  /// - 차단/매치해제가 실패해도 신고 자체는 남도록 분리
  Future<void> blockAndReportUser({
    required String fromUserId,
    required String toUserId,
    required String reason,
    String? details,
  }) async {
    if (fromUserId.trim().isEmpty) {
      throw Exception('fromUserId is empty');
    }
    if (toUserId.trim().isEmpty) {
      throw Exception('toUserId is empty');
    }
    if (reason.trim().isEmpty) {
      throw Exception('reason is empty');
    }

    // 1. 신고 기록 먼저 저장
    await _reportsRef.add({
      'reporterId': fromUserId,
      'reportedId': toUserId,
      'reason': reason.trim(),
      'details': details?.trim().isEmpty == true ? null : details?.trim(),
      'status': 'pending',
      'createdAt': FieldValue.serverTimestamp(),
    });

    // 2. 차단 기록 저장 (실패해도 신고는 이미 저장된 상태)
    try {
      await _firestore
          .collection('blocks')
          .doc(fromUserId)
          .collection('targets')
          .doc(toUserId)
          .set({
            'fromUserId': fromUserId,
            'toUserId': toUserId,
            'createdAt': FieldValue.serverTimestamp(),
          });
    } catch (_) {
      // 신고 기록은 이미 저장되었으므로 여기서는 삼킴
    }

    // 3. 기존 매치가 있다면 해제 처리 (실패해도 신고는 유지)
    try {
      final existingMatch = await _matchesRef
          .where('userIds', arrayContains: fromUserId)
          .get();

      for (final doc in existingMatch.docs) {
        final ids = List<String>.from(doc.data()['userIds'] ?? []);
        if (ids.contains(toUserId)) {
          await unmatch(doc.id);
        }
      }
    } catch (_) {
      // 신고 기록은 이미 저장되었으므로 여기서는 삼킴
    }
  }
}
