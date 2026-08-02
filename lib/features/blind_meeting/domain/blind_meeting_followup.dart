// =============================================================================
// 3:3 블라인드 취향 미팅 — 미팅 후 비공개 상호 선택
// 경로: lib/features/blind_meeting/domain/blind_meeting_followup.dart
//
// 규칙
//  - 선택 대상은 상대 팀 세 명뿐 (같은 팀원은 대상이 아니다)
//  - 최대 2명
//  - 선택 기간 24시간, 마감 후 수정 불가
//  - 일방 선택 사실은 상대에게 알리지 않는다
//  - 상호 선택 검사와 1:1 채팅 생성은 서버에서만 수행한다
//
// Firestore 경로: blindMeetings/{meetingId}/followUpChoices/{chooserUid}
//   각 사용자는 자신의 문서만 읽고 쓸 수 있다 (rules로 강제).
// =============================================================================

/// 후속 선택 제출 실패 사유.
enum BlindMeetingFollowUpViolation {
  /// 선택 가능 인원(2명)을 초과
  tooManySelections,

  /// 상대 팀이 아닌 사용자를 선택
  notOpponentTeam,

  /// 실제 참석하지 않았거나 교체된 사용자를 선택
  ineligibleTarget,

  /// 자기 자신을 선택
  selfSelection,

  /// 선택 기간이 지남
  windowClosed,

  /// 이미 최종 제출됨
  alreadySubmitted,

  /// 선택자가 실제 참석자가 아님
  chooserNotAttended,
}

extension BlindMeetingFollowUpViolationMessage
    on BlindMeetingFollowUpViolation {
  String get message => switch (this) {
    BlindMeetingFollowUpViolation.tooManySelections => '최대 2명까지 선택할 수 있어요.',
    BlindMeetingFollowUpViolation.notOpponentTeam => '상대 팀에서만 선택할 수 있어요.',
    BlindMeetingFollowUpViolation.ineligibleTarget => '선택할 수 없는 상대가 포함되어 있어요.',
    BlindMeetingFollowUpViolation.selfSelection => '자기 자신은 선택할 수 없어요.',
    BlindMeetingFollowUpViolation.windowClosed => '선택 기간이 끝났어요.',
    BlindMeetingFollowUpViolation.alreadySubmitted => '이미 선택을 제출했어요.',
    BlindMeetingFollowUpViolation.chooserNotAttended => '미팅에 참석한 분만 선택할 수 있어요.',
  };
}

/// 선택 가능 인원.
const int blindMeetingFollowUpMaxSelections = 2;

/// 후속 선택 문서.
class BlindMeetingFollowUpChoice {
  final String meetingId;
  final String chooserUid;
  final List<String> selectedUids;
  final DateTime? submittedAt;
  final DateTime? expiresAt;

  const BlindMeetingFollowUpChoice({
    required this.meetingId,
    required this.chooserUid,
    this.selectedUids = const <String>[],
    this.submittedAt,
    this.expiresAt,
  });

  bool get isSubmitted => submittedAt != null;

  Map<String, dynamic> toWritePayload() => {
    'meetingId': meetingId,
    'chooserUid': chooserUid,
    'selectedUids': selectedUids,
  };

  static BlindMeetingFollowUpChoice fromMap(
    String meetingId,
    String chooserUid,
    Map<String, dynamic>? data,
  ) {
    if (data == null) {
      return BlindMeetingFollowUpChoice(
        meetingId: meetingId,
        chooserUid: chooserUid,
      );
    }
    final selected = <String>[];
    final raw = data['selectedUids'];
    if (raw is Iterable) {
      for (final item in raw) {
        final text = item?.toString().trim() ?? '';
        if (text.isNotEmpty && !selected.contains(text)) selected.add(text);
      }
    }
    return BlindMeetingFollowUpChoice(
      meetingId: meetingId,
      chooserUid: chooserUid,
      selectedUids: List<String>.unmodifiable(selected),
      submittedAt: _dateTime(data['submittedAt']),
      expiresAt: _dateTime(data['expiresAt']),
    );
  }
}

/// 후속 선택 화면에 필요한 상태.
class BlindMeetingFollowUpState {
  /// 선택 가능한 상대 팀 사용자 id (참석자, 미차단, 미교체).
  final List<String> selectableUids;

  final BlindMeetingFollowUpChoice choice;
  final DateTime? closesAt;
  final bool chooserAttended;

  /// 서버가 계산한 상호 선택 결과. 상호 선택이 없으면 빈 목록.
  ///
  /// 일방 선택 정보는 절대 포함되지 않는다.
  final List<BlindMeetingMutualMatch> mutualMatches;

  const BlindMeetingFollowUpState({
    required this.selectableUids,
    required this.choice,
    this.closesAt,
    this.chooserAttended = true,
    this.mutualMatches = const <BlindMeetingMutualMatch>[],
  });

  bool isOpenAt(DateTime now) {
    final closes = closesAt;
    if (closes == null) return true;
    return now.isBefore(closes);
  }

  /// 선택 제출 검증. 비어 있으면 통과.
  List<BlindMeetingFollowUpViolation> validate(
    List<String> selection, {
    required DateTime now,
  }) {
    final violations = <BlindMeetingFollowUpViolation>[];
    if (!chooserAttended) {
      violations.add(BlindMeetingFollowUpViolation.chooserNotAttended);
    }
    if (!isOpenAt(now)) {
      violations.add(BlindMeetingFollowUpViolation.windowClosed);
    }
    if (choice.isSubmitted) {
      violations.add(BlindMeetingFollowUpViolation.alreadySubmitted);
    }
    final unique = <String>{};
    for (final uid in selection) {
      if (uid == choice.chooserUid) {
        violations.add(BlindMeetingFollowUpViolation.selfSelection);
        continue;
      }
      unique.add(uid);
      if (!selectableUids.contains(uid)) {
        violations.add(BlindMeetingFollowUpViolation.ineligibleTarget);
      }
    }
    if (unique.length > blindMeetingFollowUpMaxSelections) {
      violations.add(BlindMeetingFollowUpViolation.tooManySelections);
    }
    return violations;
  }
}

/// 상호 선택 성공 결과.
class BlindMeetingMutualMatch {
  final String partnerUid;
  final String chatRoomId;
  final DateTime? matchedAt;

  const BlindMeetingMutualMatch({
    required this.partnerUid,
    required this.chatRoomId,
    this.matchedAt,
  });

  static BlindMeetingMutualMatch? fromMap(Object? raw) {
    if (raw is! Map) return null;
    final partnerUid = raw['partnerUid']?.toString().trim() ?? '';
    final chatRoomId = raw['chatRoomId']?.toString().trim() ?? '';
    if (partnerUid.isEmpty || chatRoomId.isEmpty) return null;
    return BlindMeetingMutualMatch(
      partnerUid: partnerUid,
      chatRoomId: chatRoomId,
      matchedAt: _dateTime(raw['matchedAt']),
    );
  }
}

DateTime? _dateTime(Object? raw) {
  if (raw is DateTime) return raw;
  if (raw is num) return DateTime.fromMillisecondsSinceEpoch(raw.toInt());
  final text = raw?.toString();
  if (text == null || text.isEmpty) return null;
  return DateTime.tryParse(text);
}
