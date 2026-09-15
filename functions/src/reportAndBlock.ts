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
  data?: Record<string, unknown>;
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

function dataPartitionOf(data: Record<string, unknown> | undefined): string {
  const value = data?.dataPartition;
  return value === undefined || value === null ? "production" : asString(value);
}

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
  contentType?: unknown;
  contentId?: unknown;
  parentContentId?: unknown;
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
  const contentType = readOptionalBoundedText(params.contentType, "contentType", 80);
  const contentId = params.contentId == null
    ? null
    : requireSafePathSegment(params.contentId, "contentId");
  const parentContentId = params.parentContentId == null
    ? null
    : requireSafePathSegment(params.parentContentId, "parentContentId");
  if ((contentType == null) !== (contentId == null)) {
    throw new HttpsError("invalid-argument", "contentType and contentId must be provided together.");
  }

  return {
    reporterUid,
    reportedUid,
    reportData: {
      reporterId: reporterUid,
      reportedId: reportedUid,
      reason,
      details,
      source,
      contentType,
      contentId,
      parentContentId,
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
        contentType: data.contentType,
        contentId: data.contentId,
        parentContentId: data.parentContentId,
      });

      const reportedSnap = await firestore
        .collection("users")
        .doc(plan.reportedUid)
        .get();
      if (!reportedSnap.exists) {
        throw new HttpsError("not-found", "신고할 사용자를 찾을 수 없어요.");
      }
      const reporterPartition = dataPartitionOf(user.data);
      const reportedPartition = dataPartitionOf(
        reportedSnap.data() as Record<string, unknown> | undefined,
      );
      if (
        !["production", "play_review"].includes(reporterPartition) ||
        reporterPartition !== reportedPartition
      ) {
        throw new HttpsError(
          "permission-denied",
          "Account partitions do not match.",
        );
      }

      // A content report must identify real content belonging to the reported
      // account. This prevents a caller from attaching an unrelated post or
      // comment ID to make operations evidence misleading.
      const source = plan.reportData.source;
      const contentType = plan.reportData.contentType;
      const contentId = plan.reportData.contentId;
      const parentContentId = plan.reportData.parentContentId;
      if (contentType === "bamboo_post" && source === "bamboo_post") {
        const posts = reporterPartition === "play_review"
          ? "playReviewBambooPosts" : "bamboo_posts";
        const content = await firestore.collection(posts).doc(String(contentId)).get();
        if (!content.exists || content.get("authorId") !== plan.reportedUid) {
          throw new HttpsError("not-found", "신고할 게시글을 찾을 수 없어요.");
        }
      } else if (contentType === "bamboo_comment" && source === "bamboo_comment") {
        if (!parentContentId) {
          throw new HttpsError("invalid-argument", "postId is required for a comment report.");
        }
        const posts = reporterPartition === "play_review"
          ? "playReviewBambooPosts" : "bamboo_posts";
        const content = await firestore.collection(posts).doc(String(parentContentId))
          .collection("comments").doc(String(contentId)).get();
        if (!content.exists || content.get("authorId") !== plan.reportedUid) {
          throw new HttpsError("not-found", "신고할 댓글을 찾을 수 없어요.");
        }
      } else if (contentType != null || contentId != null) {
        throw new HttpsError("invalid-argument", "unsupported content report.");
      }

      const now = FieldValue.serverTimestamp();
      const reportRef = firestore.collection("reports").doc();
      const batch = firestore.batch();

      batch.set(reportRef, {
        ...plan.reportData,
        status: reporterPartition === "play_review" ? "test_only" : "pending",
        dataPartition: reporterPartition,
        reviewFixture: reporterPartition === "play_review",
        createdAt: now,
      });
      for (const write of plan.blockWrites) {
        batch.set(
          firestore
            .collection("blocks")
            .doc(write.ownerUid)
            .collection("targets")
            .doc(write.targetUid),
          {
            ...write.data,
            dataPartition: reporterPartition,
            reviewFixture: reporterPartition === "play_review",
            createdAt: now,
          },
          { merge: true }
        );
      }
      await batch.commit();

      return { reportId: reportRef.id, blockedBothDirections: true };
    }
  );
}
