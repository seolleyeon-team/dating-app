/// 앱 재시작/화면 재진입 시 서버 상태를 권위로 삼아 복구 동작을 결정한다.
///
/// 화면 로컬 사진 개수는 복구 권위가 될 수 없다. 생성이 진행 중이면 슬롯에는
/// 합성 토큰 1개만 남고, 그 값으로 "다음" 버튼을 막으면 사용자가 화면에서
/// 빠져나갈 수 없는 교착이 생긴다.
library;

import '../widgets/avatar_generation_messages.dart';

/// `getCurrentAvatarGenerationStatus` 응답의 클라이언트 표현.
///
/// 서버가 허용한 안전 상태 어휘만 담으며 내부 저장 경로/사유는 포함하지 않는다.
class AvatarGenerationStatusSnapshot {
  const AvatarGenerationStatusSnapshot({
    required this.sourceLocked,
    required this.jobId,
    required this.sourceSelectionVersion,
    required this.status,
    required this.candidateAvailability,
    required this.retryAllowed,
    required this.approved,
  });

  final bool sourceLocked;
  final String jobId;
  final int sourceSelectionVersion;
  final String status;
  final String candidateAvailability;
  final bool retryAllowed;
  final bool approved;

  bool get hasPreviewSafeCandidates => candidateAvailability == 'preview_safe';

  static AvatarGenerationStatusSnapshot fromMap(Map<String, dynamic> map) {
    return AvatarGenerationStatusSnapshot(
      sourceLocked: map['sourceLocked'] == true,
      jobId: map['jobId']?.toString().trim() ?? '',
      sourceSelectionVersion:
          int.tryParse(map['sourceSelectionVersion']?.toString() ?? '') ?? 0,
      status: map['status']?.toString().trim().toLowerCase() ?? '',
      candidateAvailability:
          map['candidateAvailability']?.toString().trim().toLowerCase() ?? '',
      retryAllowed: map['retryAllowed'] == true,
      approved: map['approved'] == true,
    );
  }
}

enum AvatarResumeAction {
  /// 진행 중인 아바타 작업이 없다. 평범한 사진 업로드 화면.
  none,

  /// 서버 작업이 살아 있다. 로딩 화면으로 복귀하고 폴링을 잇는다.
  resumeGenerating,

  /// 후보가 준비됐다. 후보 선택 화면으로 복귀한다.
  resumePreview,

  /// 승인이 끝났다. 다음 온보딩 단계로 진행한다.
  resumeApproved,

  /// 서버가 재시도를 허용한 실패.
  showRetryable,

  /// 생성은 됐지만 자동 안전 검사를 통과하지 못했다. 같은 generation 재시도는
  /// 하지 않고, 사용자가 명시적으로 새 사진 세트로 새 generation 을 시작한다.
  showNeedsReview,

  /// provider 로 요청이 나간 뒤 결과를 잃었다. 유료 생성이 이미 존재할 수
  /// 있으므로 재조정 전에는 재시도도 새 generation 도 허용하지 않는다.
  showReconciliation,

  /// 재시도가 불가능한 최종 실패.
  showTerminal,

  /// 서버 상태를 읽지 못했다. 로컬 상태를 그대로 둔다.
  unavailable,
}

class AvatarResumePlan {
  const AvatarResumePlan({
    required this.action,
    this.jobId = '',
    this.retryAllowed = false,
    this.allowsNewGeneration = false,
    this.blocksPhotoEditing = false,
    this.message = '',
  });

  final AvatarResumeAction action;
  final String jobId;

  /// 같은 logical generation 을 서버가 다시 시도해도 되는가.
  final bool retryAllowed;

  /// 사용자가 새 사진 세트로 완전히 새로운 generation 을 시작해도 되는가.
  /// 재시도와 다른 축이며, 재조정 대기 중에는 둘 다 false 다.
  final bool allowsNewGeneration;

  final bool blocksPhotoEditing;
  final String message;
}

/// 서버 상태 하나로부터 복구 계획을 만든다. 부수효과 없음.
AvatarResumePlan planAvatarResume(AvatarGenerationStatusSnapshot? snapshot) {
  if (snapshot == null) {
    return const AvatarResumePlan(action: AvatarResumeAction.unavailable);
  }

  if (snapshot.status == 'approved' || snapshot.approved) {
    return AvatarResumePlan(
      action: AvatarResumeAction.resumeApproved,
      jobId: snapshot.jobId,
      blocksPhotoEditing: true,
    );
  }

  if (!snapshot.sourceLocked) {
    return const AvatarResumePlan(action: AvatarResumeAction.none);
  }

  switch (snapshot.status) {
    case 'queued':
    // 서버가 2~6장 중 최적 소스를 고르는 중(two-phase admission 의 Phase B).
    case 'source_selecting':
    case 'running':
    case 'qa_pending':
    case 'approval_copying':
      return AvatarResumePlan(
        action: AvatarResumeAction.resumeGenerating,
        jobId: snapshot.jobId,
        blocksPhotoEditing: true,
      );
    case 'preview_ready':
      // 후보가 아직 안전하게 노출 가능하지 않으면 계속 기다린다.
      // 여기서 실패로 확정하면 서버가 정상 진행 중인데 UI만 실패가 된다.
      return AvatarResumePlan(
        action: snapshot.hasPreviewSafeCandidates
            ? AvatarResumeAction.resumePreview
            : AvatarResumeAction.resumeGenerating,
        jobId: snapshot.jobId,
        blocksPhotoEditing: true,
      );
    case 'needs_review':
      return AvatarResumePlan(
        action: AvatarResumeAction.showNeedsReview,
        jobId: snapshot.jobId,
        // 같은 generation 재시도는 금지. 새 사진으로 새 generation 은 허용.
        allowsNewGeneration: true,
        blocksPhotoEditing: true,
        message: avatarNeedsReviewMessage,
      );
    case 'reconciliation_required':
      return AvatarResumePlan(
        action: AvatarResumeAction.showReconciliation,
        jobId: snapshot.jobId,
        blocksPhotoEditing: true,
        message: avatarReconciliationRequiredMessage,
      );
    case 'retryable_failed':
    case 'no_previewable_candidates':
      return AvatarResumePlan(
        action: AvatarResumeAction.showRetryable,
        jobId: snapshot.jobId,
        // 재시도 가능 여부의 권위는 서버다. 서버가 거부할 재시도를
        // UI가 제안하면 사용자는 반드시 실패하는 버튼을 누르게 된다.
        retryAllowed: snapshot.retryAllowed,
        allowsNewGeneration: true,
        blocksPhotoEditing: true,
        message: avatarGenericNoPreviewMessage,
      );
    case 'terminal_failed':
      return AvatarResumePlan(
        action: AvatarResumeAction.showTerminal,
        jobId: snapshot.jobId,
        allowsNewGeneration: true,
        blocksPhotoEditing: true,
        message: avatarTerminalFailureMessage,
      );
    default:
      return const AvatarResumePlan(action: AvatarResumeAction.unavailable);
  }
}
