import { createHash } from "crypto";
import {
  Environment,
  NotificationTypeV2,
  SignedDataVerifier,
  Type,
  VerificationException,
  VerificationStatus,
  type JWSTransactionDecodedPayload,
} from "@apple/app-store-server-library";
import { HttpsError } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";
import { APPLE_ROOT_CERTIFICATES } from "./appleRootCertificates";

const APP_ACCOUNT_TOKEN_NAMESPACE = "seolleyeon:apple-app-account:v1:";

export type ApplePurchaseVerificationInput = {
  productId: string;
  transactionId: string;
  signedTransaction: string;
};

export type AppleVerifiedPurchase = {
  receiptFingerprint: string;
  environment: "production" | "sandbox";
};

export type ApplePurchaseVerificationConfig = {
  bundleId: string;
  appAppleId: number;
};

export type AppleRefundNotification = {
  notificationId: string;
  notificationType: "REFUND" | "REFUND_REVERSED";
  transactionId: string;
  productId: string;
  revocationPercentage: number | null;
  environment: "production" | "sandbox";
};

/**
 * Creates the stable UUID passed to StoreKit as applicationUserName. Apple
 * echoes it back as appAccountToken in the signed transaction, allowing the
 * backend to bind a purchase to the authenticated app account.
 */
export function appleAppAccountTokenForUserId(userId: string): string {
  const digest = createHash("sha256")
    .update(`${APP_ACCOUNT_TOKEN_NAMESPACE}${userId}`, "utf8")
    .digest();
  const bytes = Buffer.from(digest.subarray(0, 16));

  // UUID version 5/variant bits keep the value in the UUID format Apple
  // requires while retaining deterministic account mapping.
  bytes[6] = (bytes[6] & 0x0f) | 0x50;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = bytes.toString("hex");
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20, 32),
  ].join("-");
}

function createVerifier(
  environment: Environment,
  config: ApplePurchaseVerificationConfig
): SignedDataVerifier {
  return new SignedDataVerifier(
    [...APPLE_ROOT_CERTIFICATES],
    true,
    environment,
    config.bundleId,
    environment === Environment.PRODUCTION ? config.appAppleId : undefined
  );
}

async function verifySignedTransaction(
  signedTransaction: string,
  config: ApplePurchaseVerificationConfig
): Promise<{
  payload: JWSTransactionDecodedPayload;
  environment: "production" | "sandbox";
}> {
  const productionVerifier = createVerifier(Environment.PRODUCTION, config);
  try {
    return {
      payload: await productionVerifier.verifyAndDecodeTransaction(
        signedTransaction
      ),
      environment: "production",
    };
  } catch (error) {
    // TestFlight and App Store sandbox transactions are signed by Apple too,
    // but their payload environment is Sandbox. Only that specific result is
    // allowed to fall through to the sandbox verifier; malformed signatures,
    // wrong bundle IDs, and certificate failures remain hard failures.
    if (
      !(error instanceof VerificationException) ||
      error.status !== VerificationStatus.INVALID_ENVIRONMENT
    ) {
      throw error;
    }
  }

  const sandboxVerifier = createVerifier(Environment.SANDBOX, config);
  return {
    payload: await sandboxVerifier.verifyAndDecodeTransaction(signedTransaction),
    environment: "sandbox",
  };
}

async function verifySignedRefundNotification(
  signedPayload: string,
  config: ApplePurchaseVerificationConfig
): Promise<{
  notification: Awaited<ReturnType<SignedDataVerifier["verifyAndDecodeNotification"]>>;
  transaction: JWSTransactionDecodedPayload;
  environment: "production" | "sandbox";
}> {
  const verifyInEnvironment = async (
    environment: Environment,
    name: "production" | "sandbox"
  ) => {
    const verifier = createVerifier(environment, config);
    const notification = await verifier.verifyAndDecodeNotification(signedPayload);
    const signedTransaction = notification.data?.signedTransactionInfo;
    if (!signedTransaction) {
      throw new Error("apple_refund_notification_missing_transaction");
    }
    return {
      notification,
      transaction: await verifier.verifyAndDecodeTransaction(signedTransaction),
      environment: name,
    };
  };

  try {
    return await verifyInEnvironment(Environment.PRODUCTION, "production");
  } catch (error) {
    if (
      !(error instanceof VerificationException) ||
      error.status !== VerificationStatus.INVALID_ENVIRONMENT
    ) {
      throw error;
    }
  }

  return verifyInEnvironment(Environment.SANDBOX, "sandbox");
}

function validateDecodedTransaction(
  payload: JWSTransactionDecodedPayload,
  input: ApplePurchaseVerificationInput,
  expectedAccountToken: string
): void {
  if (payload.transactionId !== input.transactionId) {
    throw new HttpsError(
      "failed-precondition",
      "Apple transaction ID가 요청과 일치하지 않아요."
    );
  }
  if (payload.productId !== input.productId) {
    throw new HttpsError(
      "failed-precondition",
      "Apple 상품 정보가 요청과 일치하지 않아요."
    );
  }
  if (payload.type !== Type.CONSUMABLE) {
    throw new HttpsError(
      "failed-precondition",
      "Apple 상품 유형이 소모성 하트 상품이 아니에요."
    );
  }
  if (payload.quantity !== undefined && payload.quantity !== 1) {
    throw new HttpsError(
      "failed-precondition",
      "한 번에 하나의 하트 상품만 지급할 수 있어요."
    );
  }
  if (payload.revocationDate !== undefined) {
    throw new HttpsError(
      "failed-precondition",
      "환불 또는 취소된 Apple transaction은 지급할 수 없어요."
    );
  }

  const receivedAccountToken = payload.appAccountToken?.trim().toLowerCase();
  if (
    !receivedAccountToken ||
    receivedAccountToken !== expectedAccountToken.toLowerCase()
  ) {
    throw new HttpsError(
      "permission-denied",
      "Apple 구매 계정이 현재 앱 계정과 일치하지 않아요."
    );
  }
}

/**
 * Verifies Apple's signed transaction locally using Apple's official
 * certificate-chain verifier. No receipt/JWS content is persisted.
 */
export async function verifyApplePurchase(
  input: ApplePurchaseVerificationInput,
  expectedAccountToken: string,
  config: ApplePurchaseVerificationConfig
): Promise<AppleVerifiedPurchase> {
  if (!config.bundleId.trim() || !Number.isSafeInteger(config.appAppleId)) {
    throw new HttpsError(
      "failed-precondition",
      "Apple IAP 앱 설정이 올바르지 않아요."
    );
  }

  try {
    const verified = await verifySignedTransaction(
      input.signedTransaction,
      config
    );
    validateDecodedTransaction(
      verified.payload,
      input,
      expectedAccountToken
    );
    return {
      receiptFingerprint: createHash("sha256")
        .update(input.signedTransaction, "utf8")
        .digest("hex"),
      environment: verified.environment,
    };
  } catch (error) {
    if (error instanceof HttpsError) throw error;
    logger.warn("Apple purchase verification failed", {
      productId: input.productId,
      transactionIdHash: createHash("sha256")
        .update(input.transactionId, "utf8")
        .digest("hex")
        .slice(0, 16),
      error: error instanceof Error ? error.message : String(error),
    });
    throw new HttpsError(
      "failed-precondition",
      "Apple 구매 검증을 완료하지 못했어요."
    );
  }
}

/**
 * Verifies an App Store Server Notifications V2 payload and extracts only the
 * refund states that can affect an already-issued consumable entitlement.
 * The nested signed transaction is verified with the same environment-bound
 * verifier; a notification body alone is never trusted.
 */
export async function verifyAppleRefundNotification(
  signedPayload: string,
  config: ApplePurchaseVerificationConfig
): Promise<AppleRefundNotification | null> {
  if (!config.bundleId.trim() || !Number.isSafeInteger(config.appAppleId)) {
    throw new Error("apple_iap_configuration_invalid");
  }
  if (!signedPayload || signedPayload.length > 200000) {
    throw new Error("apple_refund_notification_payload_invalid");
  }

  const verified = await verifySignedRefundNotification(signedPayload, config);
  const type = verified.notification.notificationType;
  if (
    type !== NotificationTypeV2.REFUND &&
    type !== NotificationTypeV2.REFUND_REVERSED
  ) {
    return null;
  }

  const notificationId = verified.notification.notificationUUID?.trim();
  const transactionId = verified.transaction.transactionId?.trim();
  const productId = verified.transaction.productId?.trim();
  if (!notificationId || !transactionId || !productId) {
    throw new Error("apple_refund_notification_identifiers_missing");
  }
  if (verified.transaction.type !== Type.CONSUMABLE) {
    return null;
  }

  const percentage = verified.transaction.revocationPercentage;
  return {
    notificationId,
    notificationType:
      type === NotificationTypeV2.REFUND ? "REFUND" : "REFUND_REVERSED",
    transactionId,
    productId,
    revocationPercentage:
      typeof percentage === "number" && Number.isFinite(percentage)
        ? percentage
        : null,
    environment: verified.environment,
  };
}
