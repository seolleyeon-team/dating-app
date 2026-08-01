import {
  FieldValue,
  type Firestore,
} from "firebase-admin/firestore";
import {
  HttpsError,
  onCall,
  type CallableOptions,
  type CallableRequest,
} from "firebase-functions/v2/https";

export const REPORT_AND_BLOCK_USER_CALLABLE_OPTIONS: CallableOptions = {
  timeoutSeconds: 30,
  memory: "256MiB",
  invoker: "public",
  enforceAppCheck: true,
};

export const MAX_REPORT_REASON_LENGTH = 500;
export const MAX_REPORT_DETAILS_LENGTH = 2000;

type ResolvedCallableUser = {
  userId: string;
};

type ResolveCallableUser = (
  request: CallableRequest<unknown>
) => Promise<ResolvedCallableUser>;

export type BlockWrite = {
  ownerUid: string;
  targetUid: string;
  data: Record<string, unknown>;
};

export type ReportAndBlockPlan = {
  reporterUid: string;
  reportedUid: string;
  reportData: Record<string, unknown>;
  blockWrites: BlockWrite[];
};

const SAFE_PATH_SEGMENT = /^[A-Za-z0-9_-]{1,128}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function requireSafePathSegment(value: unknown, fieldName: string): string {
  const segment = asString(value);
  if (!SAFE_PATH_SEGMENT.test(segment)) {
    throw new HttpsError("invalid-argument", `${fieldName} is invalid.`);
  }
  return segment;
}

function requireBoundedText(
  value: unknown,
  fieldName: string,
  maxLength: number
): string {
  const text = asString(value);
  if (!text) {
    throw new HttpsError("invalid-argument", `${fieldName} is required.`);
  }
  if (text.length > maxLength) {
    throw new HttpsError(
      "invalid-argument",
      `${fieldName} must be at most ${maxLength} characters.`
    );
  }
  return text;
}

function readOptionalBoundedText(
  value: unknown,
  fieldName: string,
  maxLength: number
): string | null {
  if (value === undefined || value === null) return null;
  const text = asString(value);
  if (!text) return null;
  if (text.length > maxLength) {
    throw new HttpsError(
      "invalid-argument",
      `${fieldName} must be at most ${maxLength} characters.`
    );
  }
  return text;
}

/**
 * Plan the writes for a user report.
 *
 * Blocking is mutual: a report that only hides the reported user from the
 * reporter still leaves the reporter visible to the person they reported, who
 * can keep viewing and liking them. Contact-based blocking already writes both
 * directions, so report-based blocking matches it.
 */
export function buildReportAndBlockPlan(params: {
  reporterUid: string;
  reportedUid: unknown;
  reason: unknown;
  details?: unknown;
  source?: unknown;
}): ReportAndBlockPlan {
  const reporterUid = requireSafePathSegment(params.reporterUid, "reporterUid");
  const reportedUid = requireSafePathSegment(params.reportedUid, "reportedUid");
  if (reporterUid === reportedUid) {
    throw new HttpsError("invalid-argument", "자기 자신은 신고할 수 없어요.");
  }

  const reason = requireBoundedText(params.reason, "reason", MAX_REPORT_REASON_LENGTH);
  const details = readOptionalBoundedText(
    params.details,
    "details",
    MAX_REPORT_DETAILS_LENGTH
  );
  const source = asString(params.source) || "profile";

  return {
    reporterUid,
    reportedUid,
    reportData: {
      reporterId: reporterUid,
      reportedId: reportedUid,
      reason,
      details,
      source,
      status: "pending",
    },
    blockWrites: [
      {
        ownerUid: reporterUid,
        targetUid: reportedUid,
        data: {
          fromUserId: reporterUid,
          toUserId: reportedUid,
          reason: "user_report",
          source: "report",
        },
      },
      {
        ownerUid: reportedUid,
        targetUid: reporterUid,
        data: {
          fromUserId: reportedUid,
          toUserId: reporterUid,
          reason: "user_report",
          source: "report_mutual",
        },
      },
    ],
  };
}

function getCallableData(request: CallableRequest<unknown>): Record<string, unknown> {
  return isRecord(request.data) ? request.data : {};
}

export function createReportAndBlockUserFunction(
  firestore: Firestore,
  resolveUser: ResolveCallableUser
) {
  return onCall(
    REPORT_AND_BLOCK_USER_CALLABLE_OPTIONS,
    async (request): Promise<Record<string, unknown>> => {
      const user = await resolveUser(request);
      const data = getCallableData(request);

      const plan = buildReportAndBlockPlan({
        reporterUid: user.userId,
        reportedUid: data.reportedUserId,
        reason: data.reason,
        details: data.details,
        source: data.source,
      });

      const now = FieldValue.serverTimestamp();
      const reportRef = firestore.collection("reports").doc();
      const batch = firestore.batch();

      batch.set(reportRef, { ...plan.reportData, createdAt: now });
      for (const write of plan.blockWrites) {
        batch.set(
          firestore
            .collection("blocks")
            .doc(write.ownerUid)
            .collection("targets")
            .doc(write.targetUid),
          { ...write.data, createdAt: now },
          { merge: true }
        );
      }
      await batch.commit();

      return { reportId: reportRef.id, blockedBothDirections: true };
    }
  );
}
