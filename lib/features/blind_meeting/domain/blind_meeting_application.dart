// =============================================================================
// 3:3 블라인드 취향 미팅 — 참가 신청 상태
// 경로: lib/features/blind_meeting/domain/blind_meeting_application.dart
//
// Firestore 경로: blindMeetingApplications/{userId}
//   본인만 읽을 수 있고, 쓰기는 Cloud Functions만 수행한다.
//   화면 메모리가 아니라 이 문서가 대기 상태의 단일 소스이므로
//   새로고침·앱 종료·재로그인 후에도 정확히 복구된다.
// =============================================================================

import 'blind_meeting_enums.dart';
import 'blind_meeting_slot.dart';

/// 매칭 대기 화면에 표시할 단계.
enum BlindMeetingMatchingStage {
  /// 조건에 맞는 참가자를 찾고 있어요
  searchingCandidates,

  /// 우리 팀을 구성하고 있어요
  formingOwnTeam,

  /// 상대 팀과의 취향 연결을 확인하고 있어요
  checkingCrossTeam,

  /// 참가자 확정을 기다리고 있어요
  awaitingConfirmation,

  /// 구성 완료
  matched,

  /// 조건에 맞는 참가자가 아직 충분하지 않음
  insufficientCandidates,

  /// 신청이 취소됨
  cancelled,
}

extension BlindMeetingMatchingStageLabel on BlindMeetingMatchingStage {
  String get label => switch (this) {
    BlindMeetingMatchingStage.searchingCandidates => '조건에 맞는 참가자를 찾고 있어요',
    BlindMeetingMatchingStage.formingOwnTeam => '우리 팀을 구성하고 있어요',
    BlindMeetingMatchingStage.checkingCrossTeam => '상대 팀과의 취향 연결을 확인하고 있어요',
    BlindMeetingMatchingStage.awaitingConfirmation => '참가자 확정을 기다리고 있어요',
    BlindMeetingMatchingStage.matched => '미팅 구성이 완료됐어요',
    BlindMeetingMatchingStage.insufficientCandidates =>
      '아직 조건에 맞는 참가자가 충분하지 않아요',
    BlindMeetingMatchingStage.cancelled => '신청이 취소됐어요',
  };

  /// 진행률 표시용 순서 (0부터). 종료 단계는 -1.
  int get stepIndex => switch (this) {
    BlindMeetingMatchingStage.searchingCandidates => 0,
    BlindMeetingMatchingStage.formingOwnTeam => 1,
    BlindMeetingMatchingStage.checkingCrossTeam => 2,
    BlindMeetingMatchingStage.awaitingConfirmation => 3,
    _ => -1,
  };

  static const int totalSteps = 4;
}

/// 무알코올 조건 완화 선택지.
enum BlindMeetingRelaxationChoice {
  /// 다음 무알코올 미팅까지 기다릴게요
  waitForAlcoholFree,

  /// 다른 날짜도 괜찮아요
  openToOtherDates,

  /// 다른 사람의 가벼운 음주는 괜찮도록 조건을 변경할게요
  allowLightDrinking,
}

extension BlindMeetingRelaxationChoiceLabel on BlindMeetingRelaxationChoice {
  String get label => switch (this) {
    BlindMeetingRelaxationChoice.waitForAlcoholFree => '다음 무알코올 미팅까지 기다릴게요',
    BlindMeetingRelaxationChoice.openToOtherDates => '다른 날짜도 괜찮아요',
    BlindMeetingRelaxationChoice.allowLightDrinking =>
      '다른 사람의 가벼운 음주는 괜찮도록 조건을 변경할게요',
  };
}

/// 참가 신청 상태 문서.
class BlindMeetingApplication {
  final String userId;
  final BlindMeetingParticipantStatus status;
  final BlindMeetingMatchingStage stage;
  final List<BlindMeetingSlot> requestedSlots;
  final bool prefersAlcoholFree;
  final bool waitlistOptIn;

  /// 매칭된 미팅 id. 아직 없으면 null.
  final String? meetingId;

  final DateTime? appliedAt;
  final DateTime? updatedAt;

  /// 서버가 계산한 대기 시간(분).
  final int waitedMinutes;

  const BlindMeetingApplication({
    required this.userId,
    required this.status,
    required this.stage,
    this.requestedSlots = const <BlindMeetingSlot>[],
    this.prefersAlcoholFree = false,
    this.waitlistOptIn = true,
    this.meetingId,
    this.appliedAt,
    this.updatedAt,
    this.waitedMinutes = 0,
  });

  bool get isActive =>
      status != BlindMeetingParticipantStatus.cancelled &&
      stage != BlindMeetingMatchingStage.cancelled;

  bool get needsRelaxationChoice =>
      stage == BlindMeetingMatchingStage.insufficientCandidates;

  static BlindMeetingApplication fromMap(
    String userId,
    Map<String, dynamic> data,
  ) {
    return BlindMeetingApplication(
      userId: userId,
      status: enumFromName(
        BlindMeetingParticipantStatus.values,
        data['status'],
        fallback: BlindMeetingParticipantStatus.applied,
      ),
      stage: enumFromName(
        BlindMeetingMatchingStage.values,
        data['stage'],
        fallback: BlindMeetingMatchingStage.searchingCandidates,
      ),
      requestedSlots: BlindMeetingSlot.parseList(
        data['requestedSlotIds'] ?? data['requestedSlots'],
      ),
      prefersAlcoholFree: data['prefersAlcoholFree'] == true,
      waitlistOptIn: data['waitlistOptIn'] != false,
      meetingId: _nullableString(data['meetingId']),
      appliedAt: _dateTime(data['appliedAt']),
      updatedAt: _dateTime(data['updatedAt']),
      waitedMinutes: _intOr(data['waitedMinutes'], 0),
    );
  }
}

String? _nullableString(Object? raw) {
  final text = raw?.toString().trim() ?? '';
  return text.isEmpty ? null : text;
}

int _intOr(Object? raw, int fallback) {
  if (raw is int) return raw;
  if (raw is num) return raw.toInt();
  return int.tryParse(raw?.toString() ?? '') ?? fallback;
}

DateTime? _dateTime(Object? raw) {
  if (raw is DateTime) return raw;
  if (raw is num) return DateTime.fromMillisecondsSinceEpoch(raw.toInt());
  final text = raw?.toString();
  if (text == null || text.isEmpty) return null;
  return DateTime.tryParse(text);
}
