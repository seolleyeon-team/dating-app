import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

/// 추천 학습용 이벤트 기록 (recEvents)
///
/// KNN/SVD 학습 스크립트가 읽는 구조:
///   recEvents/{userId}/events/{eventId}
class RecEventService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;
  final _uuid = const Uuid();

  CollectionReference<Map<String, dynamic>> _eventsRef(String userId) =>
      _firestore.collection('recEvents').doc(userId).collection('events');

  Future<void> logEvent({
    required String userId,
    required String targetType,
    required String targetId,
    String? candidateUserId,
    required String eventType, // type 필드
    required String surface,
    required String cardVariant,
    String? exposureId,
    String? sessionId,
    String? dateKey,
    Map<String, dynamic>? context,
  }) async {
    final nowString = DateTime.now().toUtc().toIso8601String();
    
    // dateKey가 없으면 오늘 날짜(KST) 기반으로 생성 (프론트에서 넣어주지 않은 경우)
    final dKey = dateKey ?? _generateDateKey();

    final targetUid = candidateUserId ?? targetId;
    final payload = <String, dynamic>{
      'userId': userId,
      'targetType': targetType,
      'targetId': targetId,
      'targetUserId': targetUid, // Python KNN/SVD/CLIP 스크립트 호환
      'candidateUserId': candidateUserId,
      'type': eventType,
      'eventType': eventType, // 기존 python 연동 호환을 위해 유지할 수 있음
      'surface': surface,
      'source': surface, // 기존 연동 호환
      'cardVariant': cardVariant,
      'eventTime': nowString,
      'createdAt': nowString,
      'exposureId': exposureId ?? _uuid.v4(),
      if (sessionId != null) 'sessionId': sessionId,
      'dateKey': dKey,
      if (context != null && context.isNotEmpty) 'context': context,
    };

    debugPrint('[RecEvent] 🚀 시도: $eventType | surface=$surface | target=$targetUid | userId=$userId');
    
    try {
      await _firestore.collection('recEvents').doc(userId).set({
        'lastEventAt': nowString,
      }, SetOptions(merge: true));
    } catch (e) {
      debugPrint('[RecEvent] ⚠️ 부모 문서 set 실패 (무시하고 계속): $e');
    }

    await _eventsRef(userId).add(payload);
    
    debugPrint('[RecEvent] ✅ 기록 성공: $eventType surface=$surface userId=$userId');
  }

  String _generateDateKey() {
    // 임시: 기기 한국 시간 기준 YYYY-MM-DD
    final now = DateTime.now().toUtc().add(const Duration(hours: 9));
    final y = now.year.toString().padLeft(4, '0');
    final m = now.month.toString().padLeft(2, '0');
    final d = now.day.toString().padLeft(2, '0');
    return '$y-$m-$d';
  }

  // ===========================================================================
  // 기존 레거시 호환 메서드들 
  // (이들을 호출하던 기존 로직도 점차 logEvent 직접 호출로 수정 요망)
  // ===========================================================================

  /// 프로필 열람(open) 기록
  Future<void> recordOpen({
    required String fromUserId,
    required String toUserId,
    required String source,
  }) async {
    await logEvent(
      userId: fromUserId,
      targetType: 'user_profile',
      targetId: toUserId,
      candidateUserId: toUserId,
      eventType: 'open',
      surface: source,
      cardVariant: source.contains('mystery') ? 'real_profile' : 'real_profile',
    );
  }

  /// 좋아요(like) 기록
  Future<void> recordLike({
    required String fromUserId,
    required String toUserId,
    required String source,
  }) async {
    await logEvent(
      userId: fromUserId,
      targetType: 'user_profile',
      targetId: toUserId,
      candidateUserId: toUserId,
      eventType: 'like',
      surface: source,
      cardVariant: source.contains('mystery') ? 'real_profile' : 'real_profile',
    );
  }

  /// 패스(nope) 기록
  Future<void> recordNope({
    required String fromUserId,
    required String toUserId,
    required String source,
  }) async {
    await logEvent(
      userId: fromUserId,
      targetType: 'user_profile',
      targetId: toUserId,
      candidateUserId: toUserId,
      eventType: 'nope',
      surface: source,
      cardVariant: source.contains('mystery') ? 'real_profile' : 'real_profile',
    );
  }
}
