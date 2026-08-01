import 'package:cloud_firestore/cloud_firestore.dart';

/// AI 취향 학습 (사진 30장 like/nope 스와이프) Firestore 서비스
///
/// Firestore 구조:
///   users/{userId}/ai_swipes/{auto-id}  — 개별 스와이프 기록
///   users/{userId}.preferenceVector     — 학습 완료 후 벡터
class AiSwipeService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  // ---------------------------------------------------------------------------
  // 스와이프 기록
  // ---------------------------------------------------------------------------

  /// 개별 스와이프 기록 (like 또는 nope)
  Future<void> recordSwipe({
    required String userId,
    required String targetPhotoUrl,
    required String action,
    required String sessionId,
    int? responseTimeMs,
  }) async {
    await _firestore
        .collection('users')
        .doc(userId)
        .collection('ai_swipes')
        .add({
          'targetPhotoUrl': targetPhotoUrl,
          'action': action,
          'sessionId': sessionId,
          'responseTimeMs': responseTimeMs,
          'swipedAt': FieldValue.serverTimestamp(),
        });
  }

  /// 세션의 전체 스와이프 기록 조회
  Future<List<Map<String, dynamic>>> getSessionSwipes({
    required String userId,
    required String sessionId,
  }) async {
    final snap = await _firestore
        .collection('users')
        .doc(userId)
        .collection('ai_swipes')
        .where('sessionId', isEqualTo: sessionId)
        .orderBy('swipedAt')
        .get();

    return snap.docs.map((doc) => {'id': doc.id, ...doc.data()}).toList();
  }

  /// 세션의 like/nope URL 분리 추출
  Future<({List<String> likeUrls, List<String> nopeUrls})> getSessionResults({
    required String userId,
    required String sessionId,
  }) async {
    final swipes = await getSessionSwipes(userId: userId, sessionId: sessionId);

    final likeUrls = <String>[];
    final nopeUrls = <String>[];

    for (final swipe in swipes) {
      final url = swipe['targetPhotoUrl'] as String? ?? '';
      if (swipe['action'] == 'like') {
        likeUrls.add(url);
      } else if (swipe['action'] == 'nope') {
        nopeUrls.add(url);
      }
    }

    return (likeUrls: likeUrls, nopeUrls: nopeUrls);
  }

  // ---------------------------------------------------------------------------
  // Preference Vector 저장/조회
  // ---------------------------------------------------------------------------

  /// CLIP embedder가 계산한 preference vector 저장
  Future<void> savePreferenceVector({
    required String userId,
    required List<double> vector,
    required int dims,
    required String modelId,
    required int likeCount,
    required int nopeCount,
    required String sessionId,
  }) async {
    await _firestore.collection('users').doc(userId).set({
      'preferenceVector': {
        'vector': vector,
        'dims': dims,
        'modelId': modelId,
        'likeCount': likeCount,
        'nopeCount': nopeCount,
        'sessionId': sessionId,
        'computedAt': FieldValue.serverTimestamp(),
      },
    }, SetOptions(merge: true));
  }

  /// Preference vector 조회
  Future<Map<String, dynamic>?> getPreferenceVector(String userId) async {
    final doc = await _firestore.collection('users').doc(userId).get();
    if (!doc.exists) return null;
    return doc.data()?['preferenceVector'] as Map<String, dynamic>?;
  }

  /// Preference vector 존재 여부
  Future<bool> hasPreferenceVector(String userId) async {
    final doc = await _firestore.collection('users').doc(userId).get();
    if (!doc.exists) return false;
    return doc.data()?['preferenceVector'] != null;
  }

  // ---------------------------------------------------------------------------
  // 프로필 임베딩 저장 (각 유저 사진의 CLIP 벡터)
  // ---------------------------------------------------------------------------

  /// 유저 프로필 사진의 CLIP 임베딩 벡터 저장
  Future<void> saveProfileEmbedding({
    required String userId,
    required List<double> vector,
    required int dims,
    required String modelId,
  }) async {
    await _firestore.collection('embeddings').doc(userId).set({
      'userId': userId,
      'vector': vector,
      'dims': dims,
      'modelId': modelId,
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  /// 유저 프로필 임베딩 조회
  Future<Map<String, dynamic>?> getProfileEmbedding(String userId) async {
    final doc = await _firestore.collection('embeddings').doc(userId).get();
    if (!doc.exists) return null;
    return doc.data();
  }

  // ---------------------------------------------------------------------------
  // 학습 세션 관리
  // ---------------------------------------------------------------------------

  /// 새 학습 세션 ID 생성
  String createSessionId() {
    final now = DateTime.now();
    final timestamp =
        '${now.year}-${_pad(now.month)}-${_pad(now.day)}'
        '_${_pad(now.hour)}${_pad(now.minute)}${_pad(now.second)}';
    return 'session_$timestamp';
  }

  /// 학습 세션 메타데이터 저장
  Future<void> saveSessionMeta({
    required String userId,
    required String sessionId,
    required int totalPhotos,
    required int likeCount,
    required int nopeCount,
  }) async {
    await _firestore
        .collection('users')
        .doc(userId)
        .collection('ai_sessions')
        .doc(sessionId)
        .set({
          'sessionId': sessionId,
          'totalPhotos': totalPhotos,
          'likeCount': likeCount,
          'nopeCount': nopeCount,
          'completedAt': FieldValue.serverTimestamp(),
        });
  }

  /// 학습 세션 목록 조회
  Future<List<Map<String, dynamic>>> getSessions(String userId) async {
    final snap = await _firestore
        .collection('users')
        .doc(userId)
        .collection('ai_sessions')
        .orderBy('completedAt', descending: true)
        .get();

    return snap.docs.map((doc) => {'id': doc.id, ...doc.data()}).toList();
  }

  String _pad(int n) => n.toString().padLeft(2, '0');
}
