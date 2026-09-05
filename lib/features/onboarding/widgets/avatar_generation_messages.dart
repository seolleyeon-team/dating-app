import 'avatar_generation_models.dart';

const avatarSourceMultiFaceMessage = '얼굴이 여러 명 감지됐어요. 혼자 나온 사진을 선택해주세요.';
const avatarSourceFaceTooSmallMessage =
    '얼굴이 너무 작게 보여요. 얼굴이 더 잘 보이는 사진을 선택해주세요.';
const avatarBackgroundTextLogoRiskMessage = '배경의 글자나 로고가 크게 보여요. 다른 사진을 권장해요.';

const avatarMinimumPhotosMessage = '사진을 2장 이상 등록해주세요.';
const avatarGenerationPausedMessage = '아바타 생성이 잠시 중단되어 있어요. 잠시 후 다시 시도해주세요.';
const avatarPrimaryPhotoMissingMessage = '대표 사진을 다시 선택해주세요.';
const avatarNoEligibleSourcePhotoMessage = '얼굴이 잘 보이는 사진을 추가하거나 변경해 주세요.';

const avatarGenericNoPreviewMessage =
    '안전한 아바타 후보를 만들지 못했어요. 같은 사진으로 다시 시도해주세요.';
const avatarGenericEmptyCandidateMessage = '아바타 후보를 받지 못했어요. 다시 시도해주세요.';
const avatarGenerationDelayedMessage = '아바타 생성이 지연되고 있어요. 잠시 후 다시 시도해주세요.';
const avatarGenerationFailedMessage = '아바타 생성에 실패했어요. 같은 사진으로 다시 시도해주세요.';

/// QA 추가 검토 상태. 생성 자체는 성공했으므로 "생성 실패"로 표현하지 않고,
/// 맹목적 재시도도 유도하지 않는다. 자동으로 해소되는 구조가 아니므로
/// 완료 시점을 약속하지 않고 실제로 가능한 행동(문의)만 안내한다.
const avatarNeedsReviewMessage = '아바타 안전 확인에 추가 검토가 필요해요. 문의하기로 알려주시면 도와드릴게요.';

/// 재시도로 해결되지 않는 최종 실패. 일시적 실패와 구분해서 안내한다.
const avatarTerminalFailureMessage =
    '이 사진으로는 아바타를 만들 수 없었어요. 다른 사진으로 다시 시작해주세요.';

/// provider 요청은 나갔지만 결과를 확인하지 못한 상태. 이미 생성된(과금된)
/// 아바타가 있을 수 있으므로 재시도도, 새 생성도 권하지 않는다.
const avatarReconciliationRequiredMessage =
    '아바타 생성 결과를 확인하고 있어요. 확인이 끝나기 전에는 다시 만들지 않아요.';

/// 서버가 사진의 source ref 를 돌려주지 않은 경우(구 백엔드/구 세션). 예전처럼
/// 첫 사진으로 몰래 생성을 시작하지 않고 명확히 멈춘다. 배포 순서로 해결한다.
const avatarBackendIncompatibleMessage =
    '아바타 생성 준비가 아직 끝나지 않았어요. 잠시 후 다시 시도해주세요.';

/// 서버가 사진 세트를 검증하지 못했다(삭제/변경/미완료 업로드). 사진 재등록 안내.
const avatarSourceSetInvalidMessage = '사진 정보를 확인하지 못했어요. 사진을 다시 등록해주세요.';

/// needs_review / 최종 실패에서 유일한 안전한 출구. 같은 generation 재시도가
/// 아니라 새 사진 세트로 새 generation 을 시작한다.
const avatarStartOverButtonLabel = '사진을 바꾸고 다시 만들기';
const avatarStartOverUnavailableMessage = '지금은 새로 만들 수 없어요. 잠시 후 다시 시도해주세요.';

String avatarGenerationFailureMessage({
  required AvatarJobStatus status,
  String errorCode = '',
}) {
  switch (errorCode.trim()) {
    case 'avatar_no_eligible_source_photo':
      return avatarNoEligibleSourcePhotoMessage;
    case 'avatar_source_multi_face':
      return avatarSourceMultiFaceMessage;
    case 'avatar_source_face_too_small':
      return avatarSourceFaceTooSmallMessage;
    case 'avatar_background_text_logo_risky':
      return avatarBackgroundTextLogoRiskMessage;
  }

  switch (status) {
    // 생성은 성공했고 자동 QA 만 통과하지 못한 상태. 생성 실패와 섞지 않는다.
    case AvatarJobStatus.needsReview:
      return avatarNeedsReviewMessage;
    case AvatarJobStatus.noPreviewableCandidates:
    case AvatarJobStatus.failed:
    case AvatarJobStatus.superseded:
    case AvatarJobStatus.cancelled:
      return avatarGenericNoPreviewMessage;
    default:
      return avatarGenerationFailedMessage;
  }
}
