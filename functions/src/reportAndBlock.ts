/**
 * reportAndBlockUser — account reports with mutual blocks.
 *
 * NEW-20 source authority (2026-11-11). The live revision
 * reportandblockuser-00009-dak (deployed 2026-09-21) was built from a tree
 * that exists in no git ref. Compared symbol by symbol against this file:
 *   preserved from live  server-derived 24 h `deadlineAt`, `reportKind`,
 *                        review fixtures in the same `pending` queue,
 *                        the suspended-account gate in resolveAuthedAppUser
 *   rejected from live   Bamboo post/comment reports through this callable
 *                        (client-supplied author uid checked against the
 *                        post = authorship oracle, `contentSnapshot.authorId`,
 *                        a real-name mutual block revealing the reporter) —
 *                        P0-3 moved those to reportBambooContent; the
 *                        "moderation fixture" second review login
 *   added here           content references refused before any read (no
 *                        account-existence oracle), bounded `source`, one
 *                        open report per reporter→reported pair, report and
 *                        both blocks in one transaction
 * Drift from now on: the guarded deploy compares the live archive with the
 * reviewed tree before any redeploy (docs/audits/…/06-p1-13-new-20.md).
 */
import { createHash } from "node:crypto";

import {
  FieldValue,
  Timestamp,
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
/** Operations review SLA (communityModeration deadline alerts use the same 24 h). */
export const REPORT_REVIEW_DEADLINE_MS = 24 * 60 * 60 * 1000;
/** Screen tokens the app sends (profile, chat, profile_specific_detail_screen, …). */
const REPORT_SOURCE = /^[a-z][a-z0-9_]{0,63}$/;
const OPEN_REPORT_STATUSES = new Set(["pending", "reviewing"]);

/**
 * Moderation / account state that refuses every app callable (shared by
 * resolveAuthedAppUser). Mirrors decideCommunityReport's suspend/ban writes.
 */
export function isSuspendedAccountData(data: Record<string, unknown>): boolean {
  const status = typeof data.status === "string" ? data.status.trim().toLowerCase() : "";
  return data.loginDisabled === true ||
    data.isActive === false ||
    ["banned", "blocked", "deleted", "suspended", "withdrawn"].includes(status);
}

/** Deterministic id of the open account report of one reporter → reported pair. */
export function accountReportId(reporterUid: string, reportedUid: string): string {
  return "account_" + createHash("sha256")
    .update(`account_report_v1\u0000${reporterUid}\u0000${reportedUid}`)
    .digest("hex").slice(0, 40);
}

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

export function isBambooContentReport(contentType: unknown, source: unknown): boolean {
  const values = [contentType, source].map((v) => (typeof v === "string" ? v.trim() : ""));
  return values.some((v) => v.startsWith("bamboo"));
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

      // P0-3: 대나무숲 콘텐츠는 익명이다. 여기서 "클라이언트가 보낸 UID 가 이 글의
      // 작성자인가" 를 검사하면 그 자체가 작성자 확인 오라클이 되고, 이 callable
      // 이 만드는 양방향 차단 문서는 신고자에게 작성자 UID 를, 작성자에게 신고자
      // UID 를 알려 준다. 대나무숲 신고는 reportBambooContent 만 받는다. 어떤
      // 조회보다 먼저 거부해 응답으로 아무것도 시험할 수 없게 한다.
      if (isBambooContentReport(data.contentType, data.source)) {
        throw new HttpsError(
          "failed-precondition",
          "대나무숲 신고는 앱을 업데이트한 뒤 다시 시도해주세요."
        );
      }

      // NEW-20: any content reference is refused BEFORE any read. The only
      // content reports this callable ever verified were Bamboo posts/comments
      // (now reportBambooContent); an unknown or oddly spelled content type
      // must not reach a lookup whose outcome (not-found vs accepted) could be
      // observed.
      if (
        data.contentType != null ||
        data.contentId != null ||
        data.parentContentId != null
      ) {
        throw new HttpsError("invalid-argument", "unsupported content report.");
      }
      if (data.source !== undefined && data.source !== null && !REPORT_SOURCE.test(String(data.source))) {
        throw new HttpsError("invalid-argument", "source is invalid.");
      }

      const plan = buildReportAndBlockPlan({
        reporterUid: user.userId,
        reportedUid: data.reportedUserId,
        reason: data.reason,
        details: data.details,
        source: data.source,
      });

      const reporterPartition = dataPartitionOf(user.data);
      const reportedRef = firestore.collection("users").doc(plan.reportedUid);
      // One open report per (reporter, reported) pair: a retry or a repeated
      // report while moderation is still open returns the same report.
      const openReportRef = firestore
        .collection("reports")
        .doc(accountReportId(plan.reporterUid, plan.reportedUid));

      return firestore.runTransaction(async (tx) => {
        const [reportedSnap, openSnap] = await Promise.all([
          tx.get(reportedRef),
          tx.get(openReportRef),
        ]);
        if (!reportedSnap.exists) {
          throw new HttpsError("not-found", "신고할 사용자를 찾을 수 없어요.");
        }
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
        const openStatus = openSnap.exists ? String(openSnap.get("status") ?? "") : "";
        const reportRef = !openSnap.exists
          ? openReportRef
          : OPEN_REPORT_STATUSES.has(openStatus)
            ? null
            : firestore.collection("reports").doc();
        const now = FieldValue.serverTimestamp();
        if (reportRef) {
          // Production schema of the live moderation contract (recovered from
          // reportandblockuser-00009-dak): server-derived 24 h review deadline,
          // report kind, and the same operations queue for review fixtures
          // (the partition keeps them isolated). Never a content snapshot here.
          tx.create(reportRef, {
            ...plan.reportData,
            status: "pending",
            reportKind: "profile",
            contentSnapshot: null,
            deadlineAt: Timestamp.fromMillis(Date.now() + REPORT_REVIEW_DEADLINE_MS),
            dataPartition: reporterPartition,
            reviewFixture: reporterPartition === "play_review",
            createdAt: now,
          });
        }
        // The report and both blocks commit together or not at all.
        for (const write of plan.blockWrites) {
          tx.set(
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
        return {
          reportId: (reportRef ?? openReportRef).id,
          blockedBothDirections: true,
          ...(reportRef ? {} : { duplicate: true }),
        };
      });
    }
  );
}
