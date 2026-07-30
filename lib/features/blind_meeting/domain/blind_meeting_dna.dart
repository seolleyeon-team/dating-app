// =============================================================================
// 3:3 블라인드 취향 미팅 — 비공개 미팅 DNA
// 경로: lib/features/blind_meeting/domain/blind_meeting_dna.dart
//
// 이 데이터는 다른 참가자에게 절대 노출되지 않는다.
// Firestore 경로: blindMeetingDna/{userId}  (본인만 read/write, rules로 강제)
// 공개용 스냅샷은 BlindMeetingPublicProfile 로 분리해서 저장한다.
// =============================================================================

import 'blind_meeting_enums.dart';
import 'blind_meeting_slot.dart';

/// 비공개 DNA 검증 실패 사유.
enum BlindMeetingDnaViolation {
  /// 전원 비음주를 선택했지만 본인 프로필이 비음주가 아님
  allSoberRequiresSoberProfile,

  /// 가능한 날짜/시간을 선택하지 않음
  missingAvailability,

  /// 관심사가 비어 있음 (온보딩 데이터 필요)
  missingInterests,
}

extension BlindMeetingDnaViolationMessage on BlindMeetingDnaViolation {
  String get message => switch (this) {
    BlindMeetingDnaViolation.allSoberRequiresSoberProfile =>
      '전원 비음주 미팅은 내 프로필의 음주 정도가 \'전혀 안 함\'일 때 선택할 수 있어요.',
    BlindMeetingDnaViolation.missingAvailability =>
      '가능한 날짜와 시간을 한 개 이상 선택해주세요.',
    BlindMeetingDnaViolation.missingInterests => '관심사를 먼저 등록해주세요.',
  };
}

/// 비공개 미팅 DNA.
class BlindMeetingDna {
  /// 현재 스키마 버전. 필드를 추가/변경하면 올린다.
  static const int currentSchemaVersion = 1;

  final String userId;
  final int schemaVersion;

  final ConversationAtmosphere conversationAtmosphere;
  final ConversationInitiative conversationInitiative;
  final MeetingPurpose meetingPurpose;
  final AlcoholCompanionPreference alcoholCompanionPreference;
  final SmokingCompanionPreference smokingCompanionPreference;

  /// 온보딩 관심사 스냅샷 (라벨 문자열).
  final List<String> interestIds;

  final DrinkingLevel drinkingLevelSnapshot;
  final SmokingStatus smokingStatusSnapshot;
  final String? mbtiSnapshot;

  final List<BlindMeetingSlot> availableSlots;

  /// 정원이 차지 않았을 때 대기자로 참여할지 여부.
  final bool waitlistOptIn;

  final DateTime? createdAt;
  final DateTime? updatedAt;

  const BlindMeetingDna({
    required this.userId,
    this.schemaVersion = currentSchemaVersion,
    required this.conversationAtmosphere,
    required this.conversationInitiative,
    required this.meetingPurpose,
    required this.alcoholCompanionPreference,
    required this.smokingCompanionPreference,
    required this.interestIds,
    required this.drinkingLevelSnapshot,
    required this.smokingStatusSnapshot,
    this.mbtiSnapshot,
    required this.availableSlots,
    this.waitlistOptIn = true,
    this.createdAt,
    this.updatedAt,
  });

  /// 무알코올 전용 후보군으로 분리되어야 하는지.
  ///
  /// 본인이 비음주이고 동석 선호가 `allSober`인 경우에만 true.
  bool get belongsToAlcoholFreePool =>
      alcoholCompanionPreference == AlcoholCompanionPreference.allSober &&
      drinkingLevelSnapshot.isSober;

  /// 제출 가능한 상태인지 검증한다. 비어 있으면 통과.
  List<BlindMeetingDnaViolation> validate() {
    final violations = <BlindMeetingDnaViolation>[];
    if (alcoholCompanionPreference == AlcoholCompanionPreference.allSober &&
        !drinkingLevelSnapshot.isSober) {
      violations.add(BlindMeetingDnaViolation.allSoberRequiresSoberProfile);
    }
    if (availableSlots.isEmpty) {
      violations.add(BlindMeetingDnaViolation.missingAvailability);
    }
    if (interestIds.isEmpty) {
      violations.add(BlindMeetingDnaViolation.missingInterests);
    }
    return violations;
  }

  bool get isValid => validate().isEmpty;

  BlindMeetingDna copyWith({
    ConversationAtmosphere? conversationAtmosphere,
    ConversationInitiative? conversationInitiative,
    MeetingPurpose? meetingPurpose,
    AlcoholCompanionPreference? alcoholCompanionPreference,
    SmokingCompanionPreference? smokingCompanionPreference,
    List<String>? interestIds,
    DrinkingLevel? drinkingLevelSnapshot,
    SmokingStatus? smokingStatusSnapshot,
    String? mbtiSnapshot,
    List<BlindMeetingSlot>? availableSlots,
    bool? waitlistOptIn,
  }) {
    return BlindMeetingDna(
      userId: userId,
      schemaVersion: schemaVersion,
      conversationAtmosphere:
          conversationAtmosphere ?? this.conversationAtmosphere,
      conversationInitiative:
          conversationInitiative ?? this.conversationInitiative,
      meetingPurpose: meetingPurpose ?? this.meetingPurpose,
      alcoholCompanionPreference:
          alcoholCompanionPreference ?? this.alcoholCompanionPreference,
      smokingCompanionPreference:
          smokingCompanionPreference ?? this.smokingCompanionPreference,
      interestIds: interestIds ?? this.interestIds,
      drinkingLevelSnapshot:
          drinkingLevelSnapshot ?? this.drinkingLevelSnapshot,
      smokingStatusSnapshot:
          smokingStatusSnapshot ?? this.smokingStatusSnapshot,
      mbtiSnapshot: mbtiSnapshot ?? this.mbtiSnapshot,
      availableSlots: availableSlots ?? this.availableSlots,
      waitlistOptIn: waitlistOptIn ?? this.waitlistOptIn,
      createdAt: createdAt,
      updatedAt: updatedAt,
    );
  }

  /// 클라이언트가 쓰기 허용된 필드만 담은 payload.
  ///
  /// 내부 매칭 점수 등 서버 전용 필드는 절대 포함하지 않는다.
  Map<String, dynamic> toWritePayload() => {
    'userId': userId,
    'schemaVersion': schemaVersion,
    'conversationAtmosphere': conversationAtmosphere.name,
    'conversationInitiative': conversationInitiative.name,
    'meetingPurpose': meetingPurpose.name,
    'alcoholCompanionPreference': alcoholCompanionPreference.name,
    'smokingCompanionPreference': smokingCompanionPreference.name,
    'interestIds': interestIds,
    'drinkingLevelSnapshot': drinkingLevelSnapshot.name,
    'smokingStatusSnapshot': smokingStatusSnapshot.name,
    'mbtiSnapshot': mbtiSnapshot,
    'availableSlots': availableSlots.map((s) => s.slotId).toList(),
    'availableSlotIds': availableSlots.map((s) => s.slotId).toList(),
    'waitlistOptIn': waitlistOptIn,
  };

  static BlindMeetingDna? fromMap(String userId, Map<String, dynamic>? data) {
    if (data == null || data.isEmpty) return null;
    final atmosphere = enumFromNameOrNull(
      ConversationAtmosphere.values,
      data['conversationAtmosphere'],
    );
    final initiative = enumFromNameOrNull(
      ConversationInitiative.values,
      data['conversationInitiative'],
    );
    final purpose = enumFromNameOrNull(
      MeetingPurpose.values,
      data['meetingPurpose'],
    );
    if (atmosphere == null || initiative == null || purpose == null) {
      return null;
    }
    return BlindMeetingDna(
      userId: userId,
      schemaVersion: _asInt(data['schemaVersion']) ?? currentSchemaVersion,
      conversationAtmosphere: atmosphere,
      conversationInitiative: initiative,
      meetingPurpose: purpose,
      alcoholCompanionPreference: enumFromName(
        AlcoholCompanionPreference.values,
        data['alcoholCompanionPreference'],
        fallback: AlcoholCompanionPreference.noPreference,
      ),
      smokingCompanionPreference: enumFromName(
        SmokingCompanionPreference.values,
        data['smokingCompanionPreference'],
        fallback: SmokingCompanionPreference.noPreference,
      ),
      interestIds: _asStringList(data['interestIds']),
      drinkingLevelSnapshot: enumFromName(
        DrinkingLevel.values,
        data['drinkingLevelSnapshot'],
        fallback: DrinkingLevel.sometimes,
      ),
      smokingStatusSnapshot: enumFromName(
        SmokingStatus.values,
        data['smokingStatusSnapshot'],
        fallback: SmokingStatus.nonSmoker,
      ),
      mbtiSnapshot: _asTrimmedStringOrNull(data['mbtiSnapshot']),
      availableSlots: BlindMeetingSlot.parseList(
        data['availableSlots'] ?? data['availableSlotIds'],
      ),
      waitlistOptIn: data['waitlistOptIn'] != false,
      createdAt: _asDateTime(data['createdAt']),
      updatedAt: _asDateTime(data['updatedAt']),
    );
  }
}

int? _asInt(Object? raw) {
  if (raw is int) return raw;
  if (raw is num) return raw.toInt();
  return int.tryParse(raw?.toString() ?? '');
}

String? _asTrimmedStringOrNull(Object? raw) {
  final text = raw?.toString().trim() ?? '';
  return text.isEmpty ? null : text;
}

List<String> _asStringList(Object? raw) {
  if (raw is! Iterable) return const <String>[];
  final seen = <String>{};
  final result = <String>[];
  for (final item in raw) {
    final text = item?.toString().trim() ?? '';
    if (text.isEmpty) continue;
    if (seen.add(text)) result.add(text);
  }
  return List<String>.unmodifiable(result);
}

DateTime? _asDateTime(Object? raw) {
  if (raw is DateTime) return raw;
  // cloud_firestore Timestamp는 toDate()를 갖는다. 도메인 레이어가 Firestore에
  // 의존하지 않도록 dynamic 호출 대신 문자열/밀리초만 처리한다.
  if (raw is int) return DateTime.fromMillisecondsSinceEpoch(raw);
  final text = raw?.toString();
  if (text == null || text.isEmpty) return null;
  return DateTime.tryParse(text);
}
