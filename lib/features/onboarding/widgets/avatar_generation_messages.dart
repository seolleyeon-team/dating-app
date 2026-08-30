import 'avatar_generation_models.dart';

const avatarSourceMultiFaceMessage = '얼굴이 여러 명 감지됐어요. 혼자 나온 사진을 선택해주세요.';
const avatarSourceFaceTooSmallMessage =
    '얼굴이 너무 작게 보여요. 얼굴이 더 잘 보이는 사진을 선택해주세요.';
const avatarBackgroundTextLogoRiskMessage = '배경의 글자나 로고가 크게 보여요. 다른 사진을 권장해요.';

const avatarMinimumPhotosMessage = '사진을 2장 이상 등록해주세요.';
const avatarGenerationPausedMessage =
    '아바타 생성이 잠시 중단되어 있어요. 잠시 후 다시 시도해주세요.';
const avatarPrimaryPhotoMissingMessage = '대표 사진을 다시 선택해주세요.';

const avatarGenericNoPreviewMessage =
    '안전한 아바타 후보를 만들지 못했어요. 같은 사진으로 다시 시도해주세요.';
const avatarGenericEmptyCandidateMessage = '아바타 후보를 받지 못했어요. 다시 시도해주세요.';
const avatarGenerationDelayedMessage = '아바타 생성이 지연되고 있어요. 잠시 후 다시 시도해주세요.';
const avatarGenerationFailedMessage = '아바타 생성에 실패했어요. 같은 사진으로 다시 시도해주세요.';

String avatarGenerationFailureMessage({
  required AvatarJobStatus status,
  String errorCode = '',
}) {
  switch (errorCode.trim()) {
    case 'avatar_source_multi_face':
      return avatarSourceMultiFaceMessage;
    case 'avatar_source_face_too_small':
      return avatarSourceFaceTooSmallMessage;
    case 'avatar_background_text_logo_risky':
      return avatarBackgroundTextLogoRiskMessage;
  }

  switch (status) {
    case AvatarJobStatus.noPreviewableCandidates:
    case AvatarJobStatus.needsReview:
    case AvatarJobStatus.failed:
    case AvatarJobStatus.superseded:
    case AvatarJobStatus.cancelled:
      return avatarGenericNoPreviewMessage;
    default:
      return avatarGenerationFailedMessage;
  }
}
