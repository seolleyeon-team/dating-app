/**
 * Community (Bamboo) moderation console + deadline alerts.
 *
 * NEW-25 source authority (2026-11-21). The five functions deployed 2026-09-17
 * (getCommunityModerationAccess, listCommunityModerationReports,
 * setCommunityReportReviewing, restoreCommunityAccount,
 * checkCommunityModerationDeadlines) serve two images whose Cloud Build inputs
 * are still in the source bucket; `src/communityModeration.ts` of that archive
 * is byte-identical to git 94f6b0b8 (PR #146), the ancestor of this file.
 *   preserved from live  operations claim + admin/{uid}.active gate, queue view
 *                        and its fields, reviewing transition, restore + audit
 *                        record, alert ids / fields, partition scope
 *   changed since        P0-3 hide path through the private owner mappings,
 *                        dismissal of owner-less reports, defined alert
 *                        deadline (AUD-14 first half)
 *   added 2026-11-21     restricted operator refused; reviewing / decision /
 *                        restore re-check state inside a transaction; restore
 *                        refuses a withdrawn account; Auth enforcement of a
 *                        sanction can be retried; open queue and deadline sweep
 *                        query only open Bamboo reports and page through all of
 *                        them; an alert is created once and never reset
 */
import { FieldPath, FieldValue, Timestamp, type DocumentReference, type Firestore, type QueryDocumentSnapshot } from "firebase-admin/firestore";
import type { Auth } from "firebase-admin/auth";
import * as logger from "firebase-functions/logger";
import { HttpsError, onCall, type CallableRequest } from "firebase-functions/v2/https";
import { onSchedule } from "firebase-functions/v2/scheduler";
import { accountStateError, classifyAccountState } from "./accountStatePolicy";
import { withAppCheck } from "./appCheckPolicy";

type AuthContext = { uid?: string; token?: Record<string, unknown> } | null | undefined;
type Partition = "production" | "play_review";
type Scope = "all" | Partition;
type ReportStatus = "pending" | "reviewing" | "actioned" | "dismissed";

type Dependencies = {
  firestore: Firestore;
  auth: Auth;
};

const MAX_ACTION_REASON_LENGTH = 2000;
const MAX_REPORTS = 150;
const HOUR_MS = 60 * 60 * 1000;
/** The only reports the console handles (reportBambooContent writes them). */
const QUEUE_SOURCES = ["bamboo_post", "bamboo_comment"] as const;
const OPEN_STATUSES = ["pending", "reviewing"] as const;
const CLOSED_STATUSES = ["actioned", "dismissed"];
/** First deadline alert: 20 h after the report, i.e. 4 h before the 24 h SLA. */
const FIRST_ALERT_AGE_MS = 20 * HOUR_MS;
const DEADLINE_PAGE_SIZE = 200;
/** Stop paging well before the schedule timeout; the next run continues. */
const DEADLINE_SWEEP_BUDGET_MS = 240 * 1000;
export const MODERATION_DEADLINE_SCHEDULE_OPTIONS = {
  schedule: "every 15 minutes",
  timeZone: "Asia/Seoul",
  // The 60 s default was the only bound of an unpaged scan.
  timeoutSeconds: 300,
  memory: "256MiB",
} as const;

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function text(value: unknown, maxLength = 4000): string {
  return typeof value === "string" ? value.trim().slice(0, maxLength) : "";
}

function requestData(request: CallableRequest<unknown>): Record<string, unknown> {
  return record(request.data);
}

function safeUid(value: unknown, field = "userId"): string {
  const uid = text(value, 128);
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(uid)) {
    throw new HttpsError("invalid-argument", `${field} is invalid.`);
  }
  return uid;
}

function partition(value: unknown): Partition {
  if (value === "play_review") return "play_review";
  return "production";
}

function scope(value: unknown): Scope {
  if (value === "all" || value === "production" || value === "play_review") return value;
  return "all";
}

function postCollection(dataPartition: Partition): string {
  return dataPartition === "play_review" ? "playReviewBambooPosts" : "bamboo_posts";
}

// P0-3: public Bamboo documents carry no author; ownership lives only in these
// server/owner-readable mappings.
function postOwnerCollection(dataPartition: Partition): string {
  return dataPartition === "play_review" ? "playReviewBambooPostAuthors" : "bamboo_post_authors";
}

function commentOwnerCollection(dataPartition: Partition): string {
  return dataPartition === "play_review" ? "playReviewBambooCommentAuthors" : "bamboo_comment_authors";
}

async function requireOperations(firestore: Firestore, auth: AuthContext): Promise<string> {
  const uid = text(auth?.uid, 128);
  if (!uid) throw new HttpsError("unauthenticated", "로그인이 필요해요.");
  if (auth?.token?.operations !== true) {
    throw new HttpsError("permission-denied", "운영팀 권한이 필요해요.");
  }
  const [admin, account] = await Promise.all([
    firestore.collection("admin").doc(uid).get(),
    firestore.collection("users").doc(uid).get(),
  ]);
  if (!admin.exists || admin.data()?.active !== true) {
    throw new HttpsError("permission-denied", "활성 운영팀 계정을 확인할 수 없어요.");
  }
  // An operator is a promoted app account (provision_operations_account.js).
  // A moderation sanction or withdrawal on that account ends its console
  // access even while the claim and the admin record are still in place.
  const state = classifyAccountState(account.exists ? record(account.data()) : null);
  if (state === "suspended" || state === "banned" || state === "withdrawn") {
    throw accountStateError(state);
  }
  return uid;
}

function isMissingIndex(error: unknown): boolean {
  const code = (error as { code?: unknown } | null)?.code;
  return code === 9 || code === "failed-precondition";
}

function isAlreadyExists(error: unknown): boolean {
  const code = (error as { code?: unknown } | null)?.code;
  return code === 6 || code === "already-exists";
}

function isQueueSource(value: unknown): boolean {
  return (QUEUE_SOURCES as readonly string[]).includes(text(value, 80));
}

function timestampMs(value: unknown): number | null {
  if (value instanceof Timestamp) return value.toMillis();
  return null;
}

function reportView(id: string, data: Record<string, unknown>) {
  const createdAt = timestampMs(data.createdAt);
  const deadlineAt = timestampMs(data.deadlineAt) ?? (createdAt == null ? null : createdAt + 24 * HOUR_MS);
  const status = text(data.status, 40) as ReportStatus;
  return {
    reportId: id,
    reporterId: text(data.reporterId, 128),
    reportedId: text(data.reportedId, 128),
    reason: text(data.reason, 500),
    details: text(data.details, 2000) || null,
    source: text(data.source, 80),
    contentType: text(data.contentType, 80) || null,
    contentId: text(data.contentId, 128) || null,
    parentContentId: text(data.parentContentId, 128) || null,
    dataPartition: partition(data.dataPartition),
    reviewFixture: data.reviewFixture === true,
    status: ["pending", "reviewing", "actioned", "dismissed"].includes(status) ? status : "pending",
    createdAt,
    deadlineAt,
    contentSnapshot: record(data.contentSnapshot),
    actionType: text(data.actionType, 40) || null,
    actionReason: text(data.actionReason, MAX_ACTION_REASON_LENGTH) || null,
    actionedAt: timestampMs(data.actionedAt),
    actionedBy: text(data.actionedBy, 128) || null,
    dismissalReason: text(data.dismissalReason, MAX_ACTION_REASON_LENGTH) || null,
    dismissedAt: timestampMs(data.dismissedAt),
    dismissedBy: text(data.dismissedBy, 128) || null,
  };
}

async function accountSummary(firestore: Firestore, uid: string) {
  const [account, previous] = await Promise.all([
    firestore.collection("users").doc(uid).get(),
    firestore.collection("reports").where("reportedId", "==", uid).limit(100).get(),
  ]);
  const data = record(account.data());
  const onboarding = record(data.onboarding);
  return {
    nickname: text(data.nickname, 80) || text(onboarding.nickname, 80) || "이름 미설정",
    status: text(data.status, 80) || "active",
    previousReportCount: previous.size,
    previousActionCount: previous.docs.filter((doc) => doc.data().status === "actioned").length,
  };
}

async function hideAuthorCommunityContent(params: {
  firestore: Firestore;
  partition: Partition;
  authorId: string;
  moderatorId: string;
  reportId: string;
}) {
  const { firestore, partition: dataPartition, authorId, moderatorId, reportId } = params;
  const root = firestore.collection(postCollection(dataPartition));
  // The author's content is found through the private ownership mappings (P0-3
  // removed the public authorId). The legacy authorId queries stay as a union so
  // a document the migration has not reached yet is still covered.
  const [postMappings, commentMappings, legacyPosts, legacyComments] = await Promise.all([
    firestore.collection(postOwnerCollection(dataPartition)).where("ownerUid", "==", authorId).get(),
    firestore.collection(commentOwnerCollection(dataPartition)).where("ownerUid", "==", authorId).get(),
    root.where("authorId", "==", authorId).get(),
    firestore.collectionGroup("comments").where("authorId", "==", authorId).get(),
  ]);
  const postRefs = new Map<string, DocumentReference>();
  const commentRefs = new Map<string, DocumentReference>();
  for (const mapping of postMappings.docs) {
    const postId = text(mapping.get("postId"), 128) || mapping.id;
    const ref = root.doc(postId);
    postRefs.set(ref.path, ref);
  }
  for (const mapping of commentMappings.docs) {
    const postId = text(mapping.get("postId"), 128);
    const commentId = text(mapping.get("commentId"), 128);
    if (!postId || !commentId) continue;
    const ref = root.doc(postId).collection("comments").doc(commentId);
    commentRefs.set(ref.path, ref);
  }
  legacyPosts.docs.forEach((doc) => postRefs.set(doc.ref.path, doc.ref));
  legacyComments.docs
    .filter((doc) => doc.ref.path.startsWith(`${postCollection(dataPartition)}/`))
    .forEach((doc) => commentRefs.set(doc.ref.path, doc.ref));
  // A mapping can outlive its document; never create a stub by writing to it.
  const existing = async (refs: DocumentReference[]) =>
    refs.length === 0 ? [] : (await firestore.getAll(...refs)).filter((snap) => snap.exists).map((snap) => snap.ref);
  const [postWrites, commentWrites] = await Promise.all([
    existing([...postRefs.values()]),
    existing([...commentRefs.values()]),
  ]);
  const posts = { size: postWrites.length };
  const writes = [...postWrites, ...commentWrites];
  const update = {
    isDeleted: true,
    moderationHidden: true,
    moderationReportId: reportId,
    moderationActionedBy: moderatorId,
    moderationActionedAt: FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp(),
  };
  for (let index = 0; index < writes.length; index += 400) {
    const batch = firestore.batch();
    for (const ref of writes.slice(index, index + 400)) batch.set(ref, update, { merge: true });
    await batch.commit();
  }
  return { hiddenPosts: posts.size, hiddenComments: writes.length - posts.size };
}

export function createCommunityModerationCallables(deps: Dependencies) {
  const { firestore, auth } = deps;

  const getCommunityModerationAccess = onCall(withAppCheck(), async (request) => {
    const operatorId = await requireOperations(firestore, request.auth);
    return { allowed: true, operatorId };
  });

  const listCommunityModerationReports = onCall(withAppCheck(), async (request) => {
    await requireOperations(firestore, request.auth);
    const requestedScope = scope(requestData(request).scope);
    // Include recent legacy reports that predate deadlineAt, while preserving
    // a deadline-first order for the active operations queue.
    // The two unfiltered reads used to be the whole queue: 150 reports of any
    // kind, so account reports could push open Bamboo reports out of it. The
    // open queue is now read by source and status (oldest first) in addition
    // to them; the unfiltered reads keep processed history and legacy
    // documents visible exactly as before.
    const reports = firestore.collection("reports");
    let open: QueryDocumentSnapshot[] = [];
    try {
      const pages = await Promise.all(QUEUE_SOURCES.flatMap((source) => OPEN_STATUSES.map((status) =>
        reports.where("source", "==", source).where("status", "==", status)
          .orderBy("createdAt", "asc").limit(MAX_REPORTS).get())));
      open = pages.flatMap((snapshot) => snapshot.docs);
    } catch (error) {
      if (!isMissingIndex(error)) throw error;
      // reports(source, status, createdAt) is not deployed yet: previous reads only.
      logger.error("communityModeration.list: composite index missing, using the unfiltered queue", { error: String(error) });
    }
    const [byDeadline, recent] = await Promise.all([
      reports.orderBy("deadlineAt", "asc").limit(MAX_REPORTS).get(),
      reports.orderBy("createdAt", "desc").limit(MAX_REPORTS).get(),
    ]);
    const queue = [...new Map([...open, ...byDeadline.docs, ...recent.docs]
      .map((doc) => [doc.id, doc])).values()]
      .map((doc) => reportView(doc.id, record(doc.data())))
      .filter((item) => item.source === "bamboo_post" || item.source === "bamboo_comment")
      .filter((item) => requestedScope === "all" || item.dataPartition === requestedScope)
      .sort((a, b) => (a.deadlineAt ?? Number.MAX_SAFE_INTEGER) - (b.deadlineAt ?? Number.MAX_SAFE_INTEGER));
    const accountIds = [...new Set(queue.map((item) => item.reportedId).filter(Boolean))];
    const summaries = new Map(await Promise.all(accountIds.map(async (uid) => [uid, await accountSummary(firestore, uid)] as const)));
    return {
      serverNow: Date.now(),
      reports: queue.map((item) => ({ ...item, account: summaries.get(item.reportedId) ?? null })),
    };
  });

  const setCommunityReportReviewing = onCall(withAppCheck(), async (request) => {
    const operatorId = await requireOperations(firestore, request.auth);
    const reportId = safeUid(requestData(request).reportId, "reportId");
    const ref = firestore.collection("reports").doc(reportId);
    // Read and write in one transaction: a decision committed in between must
    // not be overwritten back to "reviewing".
    await firestore.runTransaction(async (transaction) => {
      const report = await transaction.get(ref);
      if (!report.exists || !isQueueSource(report.get("source"))) {
        throw new HttpsError("not-found", "신고를 찾을 수 없어요.");
      }
      if (CLOSED_STATUSES.includes(text(report.get("status"), 40))) {
        throw new HttpsError("failed-precondition", "이미 처리된 신고예요.");
      }
      transaction.set(ref, { status: "reviewing", reviewingBy: operatorId, reviewingAt: FieldValue.serverTimestamp() }, { merge: true });
    });
    return { ok: true };
  });

  const decideCommunityReport = onCall(withAppCheck(), async (request) => {
    const operatorId = await requireOperations(firestore, request.auth);
    const input = requestData(request);
    const reportId = safeUid(input.reportId, "reportId");
    const decision = text(input.decision, 40);
    const reason = text(input.reason, MAX_ACTION_REASON_LENGTH);
    if (!reason) throw new HttpsError("invalid-argument", "처리 사유를 입력해주세요.");
    if (!["dismiss", "suspend", "ban"].includes(decision)) {
      throw new HttpsError("invalid-argument", "decision is invalid.");
    }
    const reportRef = firestore.collection("reports").doc(reportId);
    const reportSnap = await reportRef.get();
    if (!reportSnap.exists) throw new HttpsError("not-found", "신고를 찾을 수 없어요.");
    const report = record(reportSnap.data());
    if (!["bamboo_post", "bamboo_comment"].includes(text(report.source, 80))) {
      throw new HttpsError("failed-precondition", "대나무숲 신고만 처리할 수 있어요.");
    }
    const actionType = decision === "ban" ? "permanent_ban" : "indefinite_suspension";
    const alreadyClosed = () => new HttpsError("failed-precondition", "이미 처리된 신고예요.");
    // The sign-in block (Auth disable + token revocation) runs after the
    // sanction is stored and cannot share its transaction. When it failed, the
    // report was already "actioned" and refused every retry, leaving the
    // account sanctioned in Firestore but enabled in Auth. The same decision
    // on such a report now only repeats the Auth step.
    const enforceSignInBlock = async (uid: string) => {
      try {
        await auth.updateUser(uid, { disabled: true });
        await auth.revokeRefreshTokens(uid);
      } catch (error) {
        logger.error("communityModeration.decide: sign-in block failed after the sanction was stored", {
          reportId, decision, error: String(error),
        });
        throw new HttpsError("unavailable", "제재는 기록됐지만 로그인 차단을 완료하지 못했어요. 같은 처리를 다시 시도해주세요.");
      }
      await reportRef.set({ authEnforcedAt: FieldValue.serverTimestamp() }, { merge: true });
    };
    if (CLOSED_STATUSES.includes(text(report.status, 40))) {
      const sanctionedId = text(report.reportedId, 128);
      if (
        decision === "dismiss" || text(report.status, 40) !== "actioned" ||
        text(report.actionType, 40) !== actionType || report.authEnforcedAt instanceof Timestamp ||
        !sanctionedId
      ) {
        throw alreadyClosed();
      }
      // Only while the account still carries this sanction (not restored since).
      const sanctioned = record((await firestore.collection("users").doc(safeUid(sanctionedId, "reportedId")).get()).data());
      const state = classifyAccountState(sanctioned);
      if (text(sanctioned.moderationActionType, 40) !== actionType || (state !== "suspended" && state !== "banned")) {
        throw alreadyClosed();
      }
      await enforceSignInBlock(sanctionedId);
      return { ok: true, decision, signInBlockRetried: true };
    }
    const dataPartition = partition(report.dataPartition);
    // The decision is written only if the report is still open at commit time
    // (two operators, or a decision racing the reviewing transition).
    const dismiss = () => firestore.runTransaction(async (transaction) => {
      const current = await transaction.get(reportRef);
      if (!current.exists || CLOSED_STATUSES.includes(text(current.get("status"), 40))) throw alreadyClosed();
      transaction.set(reportRef, {
        status: "dismissed", dismissalReason: reason, dismissedBy: operatorId,
        dismissedAt: FieldValue.serverTimestamp(), updatedAt: FieldValue.serverTimestamp(),
      }, { merge: true });
    });
    // P0-3: a Bamboo report on content whose historical owner could not be
    // proven carries reportedId null. It can still be dismissed; an account
    // action needs a resolved owner.
    if (decision === "dismiss" && !text(report.reportedId, 128)) {
      await dismiss();
      return { ok: true, decision };
    }
    const reportedId = safeUid(report.reportedId, "reportedId");
    const accountRef = firestore.collection("users").doc(reportedId);
    const account = await accountRef.get();
    if (!account.exists) throw new HttpsError("not-found", "피신고 계정을 찾을 수 없어요.");
    if (partition(record(account.data()).dataPartition) !== dataPartition) {
      throw new HttpsError("failed-precondition", "신고와 계정의 데이터 풀이 일치하지 않아요.");
    }

    if (decision === "dismiss") {
      await dismiss();
      return { ok: true, decision };
    }

    const hidden = await hideAuthorCommunityContent({ firestore, partition: dataPartition, authorId: reportedId, moderatorId: operatorId, reportId });
    await firestore.runTransaction(async (transaction) => {
      const current = await transaction.get(reportRef);
      if (!current.exists || CLOSED_STATUSES.includes(text(current.get("status"), 40))) throw alreadyClosed();
      transaction.set(accountRef, {
        status: decision === "ban" ? "banned" : "suspended",
        loginDisabled: true, isActive: false,
        moderationActionType: actionType, moderationActionReason: reason,
        moderationActionedBy: operatorId, moderationActionedAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      }, { merge: true });
      transaction.set(reportRef, {
        status: "actioned", actionType, actionReason: reason, actionedBy: operatorId,
        actionedAt: FieldValue.serverTimestamp(), removedContent: hidden,
        updatedAt: FieldValue.serverTimestamp(),
      }, { merge: true });
      transaction.set(firestore.collection("moderation_audit_logs").doc(), {
        type: actionType, reportId, reportedId, dataPartition, reason, actorId: operatorId,
        createdAt: FieldValue.serverTimestamp(), removedContent: hidden,
      });
    });
    await enforceSignInBlock(reportedId);
    return { ok: true, decision, ...hidden };
  });

  const restoreCommunityAccount = onCall(withAppCheck(), async (request) => {
    const operatorId = await requireOperations(firestore, request.auth);
    const input = requestData(request);
    const userId = safeUid(input.userId);
    const reason = text(input.reason, MAX_ACTION_REASON_LENGTH);
    if (!reason) throw new HttpsError("invalid-argument", "해제 사유를 입력해주세요.");
    const userRef = firestore.collection("users").doc(userId);
    // The state check, the account update and the audit record commit together
    // (the audit record used to be written last and was lost when the Auth
    // call failed). Auth is re-enabled afterwards; a failure there leaves the
    // account restored in Firestore and the call can simply be repeated.
    await firestore.runTransaction(async (transaction) => {
      const user = await transaction.get(userRef);
      if (!user.exists) throw new HttpsError("not-found", "계정을 찾을 수 없어요.");
      const data = record(user.data());
      const state = classifyAccountState(data);
      if (state === "banned") {
        throw new HttpsError("failed-precondition", "영구 정지는 별도 운영 절차로 검토해주세요.");
      }
      // A withdrawn / deleted account is not a suspension: lifting it would
      // bring a deleted account back (P1-5).
      if (state === "withdrawn") {
        throw new HttpsError("failed-precondition", "탈퇴한 계정은 정지 해제 대상이 아니에요.");
      }
      transaction.set(userRef, {
        status: "active", loginDisabled: false, isActive: true,
        moderationRestoredBy: operatorId, moderationRestoredAt: FieldValue.serverTimestamp(),
        moderationRestoreReason: reason, updatedAt: FieldValue.serverTimestamp(),
      }, { merge: true });
      transaction.set(firestore.collection("moderation_audit_logs").doc(), {
        type: "suspension_lifted", userId, reason, actorId: operatorId,
        dataPartition: partition(data.dataPartition),
        createdAt: FieldValue.serverTimestamp(),
      });
    });
    await auth.updateUser(userId, { disabled: false });
    return { ok: true };
  });

  return { getCommunityModerationAccess, listCommunityModerationReports, setCommunityReportReviewing, decideCommunityReport, restoreCommunityAccount };
}

// The deadline stored on an alert. A legacy report has no `deadlineAt`; its
// deadline is derived (createdAt + 24 h) a few lines below, but the alert used
// to copy the raw field. Firestore refuses `undefined`, so one such pending
// report threw inside the batch and every alert of that run was lost, again
// on each 15-minute run while the report stayed overdue.
export function moderationAlertDeadline(storedDeadlineAt: unknown, deadlineMs: number): Timestamp {
  return storedDeadlineAt instanceof Timestamp ? storedDeadlineAt : Timestamp.fromMillis(deadlineMs);
}

export type ModerationAlertLevel = "overdue" | "23h" | "20h" | "new";

/**
 * Alert level of an open report (the 2026-09-17 rule, unchanged): overdue at
 * the deadline, otherwise by age. `createdAt` is absent only on malformed
 * documents; their age is then taken from the deadline (24 h SLA).
 */
export function moderationAlertLevel(
  nowMs: number,
  createdAtMs: number | null,
  deadlineMs: number | null,
): ModerationAlertLevel | null {
  if (deadlineMs == null) return null;
  if (nowMs >= deadlineMs) return "overdue";
  const ageMs = nowMs - (createdAtMs ?? deadlineMs - 24 * HOUR_MS);
  if (ageMs >= 23 * HOUR_MS) return "23h";
  if (ageMs >= FIRST_ALERT_AGE_MS) return "20h";
  return ageMs <= 15 * 60 * 1000 ? "new" : null;
}

/**
 * Alert document id (unchanged): one alert per report and level; an overdue
 * report gets one reminder per clock hour while it stays open.
 */
export function moderationAlertId(reportId: string, level: ModerationAlertLevel, nowMs: number): string {
  return `${reportId}_${level}_${level === "overdue" ? Math.floor(nowMs / HOUR_MS) : "once"}`;
}

export type ModerationDeadlineSweepStats = {
  /** Report documents read. */
  scanned: number;
  /** Reports that are due for an alert at `now`. */
  due: number;
  /** Alert documents created by this run. */
  created: number;
  /** Alerts that already existed and were left untouched. */
  existing: number;
  pages: number;
  /** True when the composite index was missing and the status-only scan ran. */
  usedFallback: boolean;
  /** True when the time budget ended the run before the last page. */
  truncated: boolean;
};

/**
 * One deadline sweep (AUD-14).
 *
 * The previous run read the newest 150 reports of any kind, so an open Bamboo
 * report older than the 150 newest documents never got its deadline alert, and
 * it rewrote every alert it touched (`unread: true`, `createdAt`) every
 * 15 minutes. Now:
 *  - only open Bamboo reports old enough for the first deadline alert are
 *    read, by source and status, oldest first, page after page until none is
 *    left. Every writer sets `deadlineAt = createdAt + 24 h`, so the age bound
 *    is the "20 h" alert of that deadline; a legacy report without
 *    `deadlineAt` is covered by the same query.
 *  - an alert is created only when it does not exist yet (`create`, never
 *    `set`): the admin app's read state is never touched and two overlapping
 *    runs cannot produce two alerts or reset one.
 * The "new" alert is written by reportBambooContent in the report's own
 * transaction; a report that young is not read here.
 */
export async function runCommunityModerationDeadlineSweep(
  firestore: Firestore,
  options: { nowMs?: number; pageSize?: number; budgetMs?: number } = {},
): Promise<ModerationDeadlineSweepStats> {
  const nowMs = options.nowMs ?? Date.now();
  const pageSize = options.pageSize ?? DEADLINE_PAGE_SIZE;
  const budgetMs = options.budgetMs ?? DEADLINE_SWEEP_BUDGET_MS;
  const startedAt = Date.now();
  const reports = firestore.collection("reports");
  const alerts = firestore.collection("moderation_alerts");
  const cutoff = Timestamp.fromMillis(nowMs - FIRST_ALERT_AGE_MS);
  const stats: ModerationDeadlineSweepStats = {
    scanned: 0, due: 0, created: 0, existing: 0, pages: 0, usedFallback: false, truncated: false,
  };

  const alertPage = async (docs: QueryDocumentSnapshot[]) => {
    stats.pages += 1;
    stats.scanned += docs.length;
    const wanted = new Map<string, Record<string, unknown>>();
    for (const doc of docs) {
      const data = record(doc.data());
      if (!isQueueSource(data.source)) continue;
      if (!(OPEN_STATUSES as readonly string[]).includes(text(data.status, 40))) continue;
      const createdAt = timestampMs(data.createdAt);
      const deadline = timestampMs(data.deadlineAt) ?? (createdAt == null ? null : createdAt + 24 * HOUR_MS);
      const level = moderationAlertLevel(nowMs, createdAt, deadline);
      if (level == null || level === "new" || deadline == null) continue;
      wanted.set(moderationAlertId(doc.id, level, nowMs), {
        reportId: doc.id, level, dataPartition: partition(data.dataPartition),
        deadlineAt: moderationAlertDeadline(data.deadlineAt, deadline),
        createdAt: FieldValue.serverTimestamp(), unread: true,
      });
    }
    stats.due += wanted.size;
    if (wanted.size === 0) return;
    const present = await firestore.getAll(...[...wanted.keys()].map((id) => alerts.doc(id)));
    const missing = present.filter((snapshot) => !snapshot.exists).map((snapshot) => snapshot.id);
    stats.existing += wanted.size - missing.length;
    if (missing.length === 0) return;
    const batch = firestore.batch();
    for (const id of missing) batch.create(alerts.doc(id), wanted.get(id) as Record<string, unknown>);
    try {
      await batch.commit();
      stats.created += missing.length;
    } catch (error) {
      if (!isAlreadyExists(error)) throw error;
      // An overlapping run created some of them first: keep its documents.
      for (const id of missing) {
        try {
          await alerts.doc(id).create(wanted.get(id) as Record<string, unknown>);
          stats.created += 1;
        } catch (inner) {
          if (!isAlreadyExists(inner)) throw inner;
          stats.existing += 1;
        }
      }
    }
  };

  const outOfTime = () => {
    if (Date.now() - startedAt < budgetMs) return false;
    stats.truncated = true;
    return true;
  };

  // Primary: reports(source ASC, status ASC, createdAt ASC).
  const sweepIndexed = async () => {
    for (const source of QUEUE_SOURCES) {
      for (const status of OPEN_STATUSES) {
        let cursor: QueryDocumentSnapshot | null = null;
        for (;;) {
          if (outOfTime()) return;
          let query = reports.where("source", "==", source).where("status", "==", status)
            .where("createdAt", "<=", cutoff).orderBy("createdAt", "asc").limit(pageSize);
          if (cursor) query = query.startAfter(cursor);
          const page = await query.get();
          if (page.empty) break;
          await alertPage(page.docs);
          cursor = page.docs[page.docs.length - 1];
          if (page.size < pageSize) break;
        }
      }
    }
  };

  // Fallback while that index is not deployed: every open report by status
  // (single-field index), filtered in memory. More reads, same alerts.
  const sweepByStatus = async () => {
    for (const status of OPEN_STATUSES) {
      let cursor: string | null = null;
      for (;;) {
        if (outOfTime()) return;
        let query = reports.where("status", "==", status).orderBy(FieldPath.documentId()).limit(pageSize);
        if (cursor) query = query.startAfter(cursor);
        const page = await query.get();
        if (page.empty) break;
        await alertPage(page.docs);
        cursor = page.docs[page.docs.length - 1].id;
        if (page.size < pageSize) break;
      }
    }
  };

  try {
    await sweepIndexed();
  } catch (error) {
    if (!isMissingIndex(error)) throw error;
    logger.error("communityModeration.deadlines: composite index reports(source,status,createdAt) missing, scanning by status", {
      error: String(error),
    });
    stats.usedFallback = true;
    await sweepByStatus();
  }
  return stats;
}

// The schedule persists queue alerts for the admin app. It never makes an
// automated moderation decision: reports remain human-reviewed.
export function createCommunityModerationDeadlineSchedule(firestore: Firestore) {
  return onSchedule(MODERATION_DEADLINE_SCHEDULE_OPTIONS, async () => {
    const stats = await runCommunityModerationDeadlineSweep(firestore);
    if (stats.truncated) {
      logger.error("communityModeration.deadlines: time budget reached before the last page", stats);
    } else {
      logger.info("communityModeration.deadlines: sweep finished", stats);
    }
  });
}
