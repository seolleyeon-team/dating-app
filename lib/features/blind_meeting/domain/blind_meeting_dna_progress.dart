// =============================================================================
// 3:3 블라인드 취향 미팅 — 결제된 DNA 작성 진행 상태
// 경로: lib/features/blind_meeting/domain/blind_meeting_dna_progress.dart
//
// 최종 신청(blindMeetingApplications)과 분리된 문서다. 30H를 차감한 뒤
// wizard를 중단한 사용자를 식별하고, 다음 진입에서 답변을 복원하는 데 쓴다.
// =============================================================================

import 'blind_meeting_enums.dart';

class BlindMeetingDnaProgress {
  static const String statusInProgress = 'in_progress';

  final String userId;
  final String status;
  final int heartCost;
  final int heartChargeCount;
  final ConversationAtmosphere? atmosphere;
  final ConversationInitiative? initiative;
  final MeetingPurpose? purpose;
  final AlcoholCompanionPreference? alcoholPreference;
  final SmokingCompanionPreference? smokingPreference;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  const BlindMeetingDnaProgress({
    required this.userId,
    this.status = statusInProgress,
    this.heartCost = 30,
    this.heartChargeCount = 0,
    this.atmosphere,
    this.initiative,
    this.purpose,
    this.alcoholPreference,
    this.smokingPreference,
    this.createdAt,
    this.updatedAt,
  });

  /// 결제가 완료된 미완성 작성 상태인지 여부.
  bool get isInProgress => status == statusInProgress && heartChargeCount > 0;

  /// 답변을 하나라도 저장했는지 여부. 결제 직후에는 false일 수 있다.
  bool get hasStarted =>
      atmosphere != null ||
      initiative != null ||
      purpose != null ||
      alcoholPreference != null ||
      smokingPreference != null;

  static BlindMeetingDnaProgress? fromMap(
    String userId,
    Map<String, dynamic>? data,
  ) {
    if (data == null || data.isEmpty) return null;
    return BlindMeetingDnaProgress(
      userId: userId,
      status: _stringOr(data['status'], statusInProgress),
      heartCost: _nonNegativeInt(data['heartCost'], 30),
      heartChargeCount: _nonNegativeInt(data['heartChargeCount'], 0),
      atmosphere: enumFromNameOrNull(
        ConversationAtmosphere.values,
        data['conversationAtmosphere'],
      ),
      initiative: enumFromNameOrNull(
        ConversationInitiative.values,
        data['conversationInitiative'],
      ),
      purpose: enumFromNameOrNull(
        MeetingPurpose.values,
        data['meetingPurpose'],
      ),
      alcoholPreference: enumFromNameOrNull(
        AlcoholCompanionPreference.values,
        data['alcoholCompanionPreference'],
      ),
      smokingPreference: enumFromNameOrNull(
        SmokingCompanionPreference.values,
        data['smokingCompanionPreference'],
      ),
      createdAt: _dateTime(data['createdAt']),
      updatedAt: _dateTime(data['updatedAt']),
    );
  }
}

String _stringOr(Object? raw, String fallback) {
  final value = raw?.toString().trim() ?? '';
  return value.isEmpty ? fallback : value;
}

int _nonNegativeInt(Object? raw, int fallback) {
  final value = raw is num ? raw.toInt() : int.tryParse('$raw');
  return value == null || value < 0 ? fallback : value;
}

DateTime? _dateTime(Object? raw) {
  if (raw is DateTime) return raw;
  if (raw is num) return DateTime.fromMillisecondsSinceEpoch(raw.toInt());
  final value = raw?.toString();
  if (value == null || value.isEmpty) return null;
  return DateTime.tryParse(value);
}
