import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:cloud_functions/cloud_functions.dart';

enum SafetyStampFollowUpReason {
  phoneOff('phone_off'),
  forgotToStamp('forgot_to_stamp'),
  other('other');

  final String code;
  const SafetyStampFollowUpReason(this.code);

  static SafetyStampFollowUpReason? fromCode(String? code) {
    for (final value in SafetyStampFollowUpReason.values) {
      if (value.code == code) {
        return value;
      }
    }
    return null;
  }
}

class SafetyStampFollowUpDraft {
  final SafetyStampFollowUpReason? reason;
  final String otherText;
  final bool hasSubmitted;

  const SafetyStampFollowUpDraft({
    required this.reason,
    required this.otherText,
    required this.hasSubmitted,
  });
}

class SafetyStampFollowUpService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;
  final FirebaseFunctions _functions = FirebaseFunctions.instanceFor(
    region: 'asia-northeast3',
  );

  Future<SafetyStampFollowUpDraft> loadDraft({
    required String roomId,
    required String promiseId,
    required String userId,
  }) async {
    if (roomId.isEmpty || promiseId.isEmpty || userId.isEmpty) {
      return const SafetyStampFollowUpDraft(
        reason: null,
        otherText: '',
        hasSubmitted: false,
      );
    }

    final promiseDoc = await _firestore
        .collection('chat_rooms')
        .doc(roomId)
        .collection('promises')
        .doc(promiseId)
        .get();

    final data = promiseDoc.data() ?? const <String, dynamic>{};
    final safetyStampRaw = data['safetyStamp'];
    final safetyStamp = safetyStampRaw is Map
        ? Map<String, dynamic>.from(safetyStampRaw)
        : const <String, dynamic>{};
    final followUpRaw = safetyStamp['goodbyeFollowUpByUserId'];
    final followUpByUserId = followUpRaw is Map
        ? Map<String, dynamic>.from(followUpRaw)
        : const <String, dynamic>{};
    final mineRaw = followUpByUserId[userId];
    final mine = mineRaw is Map
        ? Map<String, dynamic>.from(mineRaw)
        : const <String, dynamic>{};

    return SafetyStampFollowUpDraft(
      reason: SafetyStampFollowUpReason.fromCode(
        mine['reasonCode']?.toString(),
      ),
      otherText: mine['reasonText']?.toString() ?? '',
      hasSubmitted: mine['status']?.toString() == 'submitted',
    );
  }

  /// 헤어짐 안전도장 미완료 사유를 제출한다.
  ///
  /// 이 값은 safetyStamp 맵 안에 저장되고, safetyStamp 는 서버만 쓴다.
  /// 그래서 사유 제출도 클라이언트가 Firestore 에 직접 쓰지 않고 서버에 맡긴다.
  /// 응답 주체는 서버가 auth.uid 로 정한다 (uid 파라미터가 없다).
  Future<void> submitReason({
    required String roomId,
    required String promiseId,
    required SafetyStampFollowUpReason reason,
    required String otherText,
    String? notificationId,
  }) async {
    if (roomId.isEmpty || promiseId.isEmpty) {
      throw Exception('필수 정보가 없어요.');
    }
    await _functions.httpsCallable('submitSafetyStampFollowUp').call<dynamic>({
      'roomId': roomId,
      'promiseId': promiseId,
      'reasonCode': reason.code,
      if (reason == SafetyStampFollowUpReason.other)
        'reasonText': otherText.trim(),
      if (notificationId != null && notificationId.isNotEmpty)
        'notificationId': notificationId,
    });
  }
}
