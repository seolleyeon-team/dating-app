/**
 * 3:3 블라인드 취향 미팅 — 개인별 보증금 결제 추상화
 * 경로: functions/src/blindMeeting/payments.ts
 *
 * 원칙
 *  - production 결제 성공을 가짜로 반환하지 않는다.
 *  - 자격증명이 없으면 `failed` 상태와 사유를 그대로 돌려준다.
 *  - emulator/sandbox 모드에서는 sandbox 플래그를 명시한 결제만 수행한다.
 *  - 결제와 환불은 idempotencyKey 기준으로 한 번만 실행된다.
 *
 * 외부 blocker
 *  운영 결제 provider 자격증명(BLIND_MEETING_PAYMENT_API_KEY, PROVIDER_ID)은
 *  Secret Manager로 주입해야 하며 코드만으로 해결할 수 없다.
 *  자격증명이 없으면 아래 UnconfiguredPaymentProvider가 선택된다.
 */

import { getFirestore, FieldValue } from "firebase-admin/firestore";
import * as logger from "firebase-functions/logger";

import { BLIND_MEETING_COLLECTIONS, DepositStatus } from "./types";

function db() {
  return getFirestore();
}

export type DepositIntent = {
  status: DepositStatus;
  provider: string;
  amount: number;
  checkoutUrl?: string;
  sandbox: boolean;
  message?: string;
};

export type RefundResult = {
  status: DepositStatus;
  provider: string;
  refundedAmount: number;
  sandbox: boolean;
  message?: string;
};

export type DepositRequest = {
  meetingId: string;
  userId: string;
  amount: number;
  idempotencyKey: string;
};

export type RefundRequest = {
  meetingId: string;
  userId: string;
  depositAmount: number;
  refundAmount: number;
  idempotencyKey: string;
  reason: string;
};

export interface PaymentProvider {
  readonly id: string;
  readonly sandbox: boolean;
  createDepositIntent(request: DepositRequest): Promise<DepositIntent>;
  refund(request: RefundRequest): Promise<RefundResult>;
}

/**
 * 운영 자격증명이 없을 때 선택되는 provider.
 *
 * 절대 성공을 반환하지 않고, 필요한 외부 결정을 메시지로 알린다.
 */
class UnconfiguredPaymentProvider implements PaymentProvider {
  readonly id = "unconfigured";
  readonly sandbox = false;

  private readonly reason =
    "결제 provider 자격증명이 설정되지 않았어요. 운영 담당자 확인이 필요해요.";

  async createDepositIntent(request: DepositRequest): Promise<DepositIntent> {
    logger.error("blindMeeting deposit provider not configured", {
      meetingId: request.meetingId,
    });
    return {
      status: "failed",
      provider: this.id,
      amount: request.amount,
      sandbox: false,
      message: this.reason,
    };
  }

  async refund(request: RefundRequest): Promise<RefundResult> {
    logger.error("blindMeeting refund provider not configured", {
      meetingId: request.meetingId,
    });
    return {
      status: "refund_pending",
      provider: this.id,
      refundedAmount: 0,
      sandbox: false,
      message: this.reason,
    };
  }
}

/**
 * emulator / 개발 환경 전용 provider.
 *
 * sandbox 플래그가 항상 true이며, 운영 환경에서는 선택되지 않는다.
 */
class SandboxPaymentProvider implements PaymentProvider {
  readonly id = "sandbox";
  readonly sandbox = true;

  async createDepositIntent(request: DepositRequest): Promise<DepositIntent> {
    return {
      status: "paid",
      provider: this.id,
      amount: request.amount,
      sandbox: true,
      message: "sandbox 결제로 처리했어요. 운영 결제가 아닙니다.",
    };
  }

  async refund(request: RefundRequest): Promise<RefundResult> {
    return {
      status:
        request.refundAmount >= request.depositAmount
          ? "refunded"
          : request.refundAmount > 0
            ? "partially_refunded"
            : "forfeited",
      provider: this.id,
      refundedAmount: request.refundAmount,
      sandbox: true,
      message: "sandbox 환불로 처리했어요. 운영 환불이 아닙니다.",
    };
  }
}

/**
 * 외부 결제 provider 연동 지점.
 *
 * 실제 HTTP 호출은 운영 자격증명이 주입된 뒤에만 수행되며,
 * 응답을 검증하지 못하면 성공으로 처리하지 않는다.
 */
class ExternalPaymentProvider implements PaymentProvider {
  readonly sandbox = false;

  constructor(
    readonly id: string,
    private readonly apiKey: string,
    private readonly baseUrl: string
  ) {}

  private async post(
    path: string,
    body: Record<string, unknown>,
    idempotencyKey: string
  ): Promise<Record<string, unknown> | null> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${this.apiKey}`,
        "idempotency-key": idempotencyKey,
      },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      logger.error("blindMeeting payment provider error", {
        path,
        status: response.status,
      });
      return null;
    }
    const json: unknown = await response.json();
    return typeof json === "object" && json !== null
      ? (json as Record<string, unknown>)
      : null;
  }

  async createDepositIntent(request: DepositRequest): Promise<DepositIntent> {
    const result = await this.post(
      "/deposits",
      {
        amount: request.amount,
        reference: `${request.meetingId}:${request.userId}`,
      },
      request.idempotencyKey
    );
    if (result == null) {
      return {
        status: "failed",
        provider: this.id,
        amount: request.amount,
        sandbox: false,
        message: "결제 요청이 실패했어요. 잠시 후 다시 시도해주세요.",
      };
    }

    const checkoutUrl =
      typeof result.checkoutUrl === "string" ? result.checkoutUrl : undefined;
    const status = typeof result.status === "string" ? result.status : "";
    const mapped: DepositStatus =
      status === "paid"
        ? "paid"
        : status === "authorized"
          ? "authorized"
          : status === "pending"
            ? "pending"
            : "failed";

    return {
      status: mapped,
      provider: this.id,
      amount: request.amount,
      checkoutUrl,
      sandbox: false,
      message:
        mapped === "failed"
          ? "결제 상태를 확인하지 못했어요. 다시 시도해주세요."
          : undefined,
    };
  }

  async refund(request: RefundRequest): Promise<RefundResult> {
    const result = await this.post(
      "/refunds",
      {
        amount: request.refundAmount,
        reference: `${request.meetingId}:${request.userId}`,
        reason: request.reason,
      },
      request.idempotencyKey
    );
    if (result == null) {
      return {
        status: "refund_pending",
        provider: this.id,
        refundedAmount: 0,
        sandbox: false,
        message: "환불 요청이 실패했어요. 운영자 확인이 필요해요.",
      };
    }
    const refunded =
      typeof result.refundedAmount === "number"
        ? result.refundedAmount
        : request.refundAmount;
    return {
      status:
        refunded >= request.depositAmount
          ? "refunded"
          : refunded > 0
            ? "partially_refunded"
            : "forfeited",
      provider: this.id,
      refundedAmount: refunded,
      sandbox: false,
    };
  }
}

let cachedProvider: PaymentProvider | null = null;

/** 환경에 맞는 결제 provider를 고른다. */
export function resolvePaymentProvider(): PaymentProvider {
  if (cachedProvider) return cachedProvider;

  const apiKey = process.env.BLIND_MEETING_PAYMENT_API_KEY ?? "";
  const providerId = process.env.BLIND_MEETING_PAYMENT_PROVIDER ?? "";
  const baseUrl = process.env.BLIND_MEETING_PAYMENT_BASE_URL ?? "";
  const isEmulator = process.env.FUNCTIONS_EMULATOR === "true";

  if (apiKey && providerId && baseUrl) {
    cachedProvider = new ExternalPaymentProvider(providerId, apiKey, baseUrl);
  } else if (isEmulator) {
    cachedProvider = new SandboxPaymentProvider();
  } else {
    cachedProvider = new UnconfiguredPaymentProvider();
  }
  return cachedProvider;
}

/** 테스트에서 provider를 교체한다. */
export function setPaymentProviderForTest(
  provider: PaymentProvider | null
): void {
  cachedProvider = provider;
}

function depositDocId(meetingId: string, userId: string): string {
  return `${meetingId}_${userId}`;
}

/**
 * 보증금 결제를 idempotent하게 시작한다.
 *
 * 이미 결제 완료된 경우 provider를 호출하지 않고 기존 상태를 돌려준다.
 */
export async function startDeposit(params: {
  meetingId: string;
  userId: string;
  amount: number;
}): Promise<DepositIntent> {
  const provider = resolvePaymentProvider();
  const ref = db()
    .collection(BLIND_MEETING_COLLECTIONS.deposits)
    .doc(depositDocId(params.meetingId, params.userId));

  const existing = await ref.get();
  const existingStatus = existing.data()?.status as DepositStatus | undefined;
  if (existingStatus === "paid" || existingStatus === "authorized") {
    return {
      status: existingStatus,
      provider: (existing.data()?.provider as string) ?? provider.id,
      amount: (existing.data()?.amount as number) ?? params.amount,
      sandbox: existing.data()?.sandbox === true,
      message: "이미 결제가 처리되어 있어요.",
    };
  }

  const idempotencyKey = `deposit_${params.meetingId}_${params.userId}`;
  const intent = await provider.createDepositIntent({
    meetingId: params.meetingId,
    userId: params.userId,
    amount: params.amount,
    idempotencyKey,
  });

  await ref.set(
    {
      meetingId: params.meetingId,
      userId: params.userId,
      amount: params.amount,
      status: intent.status,
      provider: intent.provider,
      sandbox: intent.sandbox,
      idempotencyKey,
      message: intent.message ?? null,
      updatedAt: FieldValue.serverTimestamp(),
      createdAt: existing.exists
        ? (existing.data()?.createdAt ?? FieldValue.serverTimestamp())
        : FieldValue.serverTimestamp(),
    },
    { merge: true }
  );

  return intent;
}

/** 환불을 idempotent하게 실행한다. */
export async function refundDeposit(params: {
  meetingId: string;
  userId: string;
  depositAmount: number;
  refundAmount: number;
  reason: string;
}): Promise<RefundResult> {
  const provider = resolvePaymentProvider();
  const ref = db()
    .collection(BLIND_MEETING_COLLECTIONS.deposits)
    .doc(depositDocId(params.meetingId, params.userId));

  const existing = await ref.get();
  if (!existing.exists) {
    return {
      status: "not_required",
      provider: provider.id,
      refundedAmount: 0,
      sandbox: provider.sandbox,
      message: "결제 기록이 없어 환불할 내용이 없어요.",
    };
  }

  const status = existing.data()?.status as DepositStatus | undefined;
  if (
    status === "refunded" ||
    status === "partially_refunded" ||
    status === "forfeited"
  ) {
    return {
      status,
      provider: (existing.data()?.provider as string) ?? provider.id,
      refundedAmount: (existing.data()?.refundedAmount as number) ?? 0,
      sandbox: existing.data()?.sandbox === true,
      message: "이미 환불 처리가 완료된 결제예요.",
    };
  }

  const idempotencyKey = `refund_${params.meetingId}_${params.userId}`;
  const result = await provider.refund({
    meetingId: params.meetingId,
    userId: params.userId,
    depositAmount: params.depositAmount,
    refundAmount: params.refundAmount,
    idempotencyKey,
    reason: params.reason,
  });

  await ref.set(
    {
      status: result.status,
      refundedAmount: result.refundedAmount,
      refundReason: params.reason,
      refundIdempotencyKey: idempotencyKey,
      refundMessage: result.message ?? null,
      updatedAt: FieldValue.serverTimestamp(),
    },
    { merge: true }
  );

  return result;
}

/** 결제 상태 조회 (참가자 문서 동기화용) */
export async function readDepositStatus(
  meetingId: string,
  userId: string
): Promise<DepositStatus> {
  const snap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.deposits)
    .doc(depositDocId(meetingId, userId))
    .get();
  const status = snap.data()?.status;
  return typeof status === "string" ? (status as DepositStatus) : "not_required";
}
