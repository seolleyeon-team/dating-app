// =============================================================================
// 3:3 블라인드 취향 미팅 — legacy 상태 디코드 경계 (LEGACY_STATE_NORMALIZATION)
// 경로: lib/features/blind_meeting/domain/blind_meeting_legacy_status.dart
//
// 블라인드 미팅에는 보증금도, 매칭 후 수락 단계도 없다. 매칭이 commit 되면
// 결제 절차 없이 바로 미팅이 확정되고 단체 채팅방이 열린다.
//
// 이 파일은 그 변경 이전에 서버가 저장한 문서 값(결제 대기 상태)을 앱이
// crash 없이 canonical 상태로 읽어 들이는 **유일한** 자리다. 서버 스케줄러가
// 같은 문서를 곧 canonical 상태로 정규화하므로 앱은 결제 화면을 띄우지 않고
// 수락 대기 화면을 보여주기만 한다. 여기 밖의 UI/비즈니스 코드는 legacy 상태를
// 알지 못한다.
// =============================================================================

import 'blind_meeting_enums.dart';

/// 과거 서버가 저장하던 미팅 상태 문자열 (앱 표기 / 서버 표기).
const Set<String> _legacyAwaitingDepositsStatuses = {
  'awaitingDeposits',
  'awaiting_deposits',
};

/// 과거 서버가 저장하던 참가자 상태 문자열 (앱 표기 / 서버 표기).
const Set<String> _legacyDepositPendingStatuses = {
  'depositPending',
  'deposit_pending',
};

/// Firestore 미팅 status 를 디코드한다. legacy 결제 대기 상태는
/// "매칭은 끝났지만 아직 확정 전" 이므로 LEGACY_COMPATIBILITY_ONLY 상태인
/// [BlindMeetingStatus.awaitingAcceptance] 로 읽는다 (수락/거절 UI 없음, 서버가
/// 곧 확정하거나 운영 검토로 보낸다).
BlindMeetingStatus decodeBlindMeetingStatus(
  Object? raw, {
  required BlindMeetingStatus fallback,
}) {
  final name = raw?.toString().trim();
  if (name != null && _legacyAwaitingDepositsStatuses.contains(name)) {
    return BlindMeetingStatus.awaitingAcceptance;
  }
  return enumFromName(BlindMeetingStatus.values, raw, fallback: fallback);
}

/// Firestore 참가자/신청 status 를 디코드한다. legacy 결제 대기 참가자는
/// 초대를 수락한 사람이므로 [BlindMeetingParticipantStatus.accepted] 로 읽는다.
BlindMeetingParticipantStatus decodeBlindMeetingParticipantStatus(
  Object? raw, {
  required BlindMeetingParticipantStatus fallback,
}) {
  final name = raw?.toString().trim();
  if (name != null && _legacyDepositPendingStatuses.contains(name)) {
    return BlindMeetingParticipantStatus.accepted;
  }
  return enumFromName(
    BlindMeetingParticipantStatus.values,
    raw,
    fallback: fallback,
  );
}
