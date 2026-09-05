/**
 * 아바타 작업 재조정(reconciliation) 분류기.
 *
 * 두 종류의 고아 상태를 "절대" 같은 방식으로 다루지 않는다.
 *
 * 1. QUEUED_NOT_DISPATCHED
 *    Cloud Task 가 한 번도 dispatch 되지 않아 provider 호출이 0임을 증명할 수
 *    있는 상태. 유료 모호성이 없다. 다만 큐가 PAUSED 여서 대기 중인 것을
 *    사용자 실패로 바꾸면 안 된다.
 *
 * 2. PROVIDER_OUTCOME_UNKNOWN
 *    Azure 로 요청이 나간 뒤 응답을 잃은 상태. 이미 과금된 이미지가 존재할 수
 *    있으므로 자동 재시도/failover 를 절대 하지 않는다.
 *
 * 이 모듈은 순수 분류만 한다. Firestore 를 읽거나 쓰지 않는다.
 */

type RecordData = Record<string, unknown>;

function readMap(value: unknown): RecordData {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as RecordData)
    : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

/** 워커가 "요청은 나갔고 결과를 모른다"를 기록할 때 쓰는 오류 코드들. */
export const PROVIDER_OUTCOME_UNKNOWN_ERROR_CODES = [
  "azure_unknown_post_send_outcome",
] as const;

/** 이미 provider 호출이 일어났음을 증명하는 필드들. */
function hasProviderCallEvidence(jobData: RecordData): boolean {
  if (Object.keys(readMap(jobData.providerUsage)).length > 0) return true;
  if (Object.keys(readMap(jobData.generationClaim)).length > 0) return true;
  return false;
}

export type AvatarJobReconciliationClass =
  | "queued_not_dispatched"
  | "provider_outcome_unknown"
  | "active"
  | "terminal"
  | "insufficient_evidence";

export type AvatarJobReconciliationVerdict = {
  classification: AvatarJobReconciliationClass;
  /** true 면 유료 생성이 이미 발생했을 가능성을 배제할 수 없다. */
  providerCallPossible: boolean;
  /** 새 provider 호출을 유발하는 재큐잉이 안전한가. */
  safeToRequeue: boolean;
  publicStatus: string;
  reasonCode: string | null;
};

const ACTIVE_WORKER_STATUSES = new Set([
  "running",
  "provider_inflight",
  "generated",
  "persisted",
  "qa_pending",
]);

export function classifyAvatarJobForReconciliation(params: {
  jobData: unknown;
  queuePaused: boolean;
  /** Cloud Tasks dispatchCount. 모르면 null — 절대 0으로 가정하지 않는다. */
  taskDispatchCount: number | null;
  taskExists: boolean | null;
}): AvatarJobReconciliationVerdict {
  const jobData = readMap(params.jobData);
  const status = asString(jobData.status).toLowerCase();
  const errorCode = asString(jobData.errorCode).toLowerCase();
  const claimState = asString(readMap(jobData.generationClaim).state)
    .toLowerCase();

  // 1) 유료 모호성이 최우선이다. 다른 어떤 분류보다 먼저 판정한다.
  const unknownOutcome = (
    PROVIDER_OUTCOME_UNKNOWN_ERROR_CODES as readonly string[]
  ).includes(errorCode);
  if (unknownOutcome) {
    return {
      classification: "provider_outcome_unknown",
      providerCallPossible: true,
      safeToRequeue: false,
      publicStatus: "reconciliation_required",
      reasonCode: "avatar_provider_outcome_unknown",
    };
  }

  // 2) 워커가 아직 붙들고 있는 작업.
  if (ACTIVE_WORKER_STATUSES.has(status) || claimState === "active") {
    return {
      classification: "active",
      providerCallPossible: true,
      safeToRequeue: false,
      publicStatus: status || "running",
      reasonCode: null,
    };
  }

  if (status === "queued") {
    // dispatch 증거가 없으면 "호출 0"이라고 결론내지 않는다.
    if (params.taskDispatchCount === null) {
      return {
        classification: "insufficient_evidence",
        providerCallPossible: true,
        safeToRequeue: false,
        publicStatus: "queued",
        reasonCode: null,
      };
    }
    if (params.taskDispatchCount > 0 || hasProviderCallEvidence(jobData)) {
      return {
        classification: "insufficient_evidence",
        providerCallPossible: true,
        safeToRequeue: false,
        publicStatus: "queued",
        reasonCode: null,
      };
    }
    // provider 호출 0이 증명된다. 그래도 큐가 멈춰 있으면 재큐잉은 무의미하고,
    // 사용자에게는 실패가 아니라 대기로 보여야 한다.
    return {
      classification: "queued_not_dispatched",
      providerCallPossible: false,
      safeToRequeue: !params.queuePaused,
      publicStatus: "queued",
      reasonCode: params.queuePaused ? "avatar_generation_paused" : null,
    };
  }

  return {
    classification: "terminal",
    providerCallPossible: hasProviderCallEvidence(jobData) || status !== "",
    safeToRequeue: false,
    publicStatus: status,
    reasonCode: errorCode || null,
  };
}
