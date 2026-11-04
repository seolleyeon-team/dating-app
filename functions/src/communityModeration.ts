import { FieldValue, Timestamp, type Firestore } from "firebase-admin/firestore";
import type { Auth } from "firebase-admin/auth";
import { HttpsError, onCall, type CallableRequest } from "firebase-functions/v2/https";
import { onSchedule } from "firebase-functions/v2/scheduler";
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

async function requireOperations(firestore: Firestore, auth: AuthContext): Promise<string> {
  const uid = text(auth?.uid, 128);
  if (!uid) throw new HttpsError("unauthenticated", "로그인이 필요해요.");
  if (auth?.token?.operations !== true) {
    throw new HttpsError("permission-denied", "운영팀 권한이 필요해요.");
  }
  const admin = await firestore.collection("admin").doc(uid).get();
  if (!admin.exists || admin.data()?.active !== true) {
    throw new HttpsError("permission-denied", "활성 운영팀 계정을 확인할 수 없어요.");
  }
  return uid;
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
  const posts = await firestore.collection(postCollection(dataPartition))
    .where("authorId", "==", authorId).get();
  const comments = await firestore.collectionGroup("comments")
    .where("authorId", "==", authorId).get();
  const writes = [
    ...posts.docs.map((doc) => doc.ref),
    ...comments.docs
      .filter((doc) => doc.ref.path.startsWith(`${postCollection(dataPartition)}/`))
      .map((doc) => doc.ref),
  ];
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
    const [byDeadline, recent] = await Promise.all([
      firestore.collection("reports").orderBy("deadlineAt", "asc").limit(MAX_REPORTS).get(),
      firestore.collection("reports").orderBy("createdAt", "desc").limit(MAX_REPORTS).get(),
    ]);
    const queue = [...new Map([...byDeadline.docs, ...recent.docs]
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
    const report = await ref.get();
    if (!report.exists || !["bamboo_post", "bamboo_comment"].includes(text(report.get("source"), 80))) {
      throw new HttpsError("not-found", "신고를 찾을 수 없어요.");
    }
    if (["actioned", "dismissed"].includes(text(report.get("status"), 40))) {
      throw new HttpsError("failed-precondition", "이미 처리된 신고예요.");
    }
    await ref.set({ status: "reviewing", reviewingBy: operatorId, reviewingAt: FieldValue.serverTimestamp() }, { merge: true });
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
    if (["actioned", "dismissed"].includes(text(report.status, 40))) {
      throw new HttpsError("failed-precondition", "이미 처리된 신고예요.");
    }
    const reportedId = safeUid(report.reportedId, "reportedId");
    const dataPartition = partition(report.dataPartition);
    const accountRef = firestore.collection("users").doc(reportedId);
    const account = await accountRef.get();
    if (!account.exists) throw new HttpsError("not-found", "피신고 계정을 찾을 수 없어요.");
    if (partition(record(account.data()).dataPartition) !== dataPartition) {
      throw new HttpsError("failed-precondition", "신고와 계정의 데이터 풀이 일치하지 않아요.");
    }

    if (decision === "dismiss") {
      await reportRef.set({
        status: "dismissed", dismissalReason: reason, dismissedBy: operatorId,
        dismissedAt: FieldValue.serverTimestamp(), updatedAt: FieldValue.serverTimestamp(),
      }, { merge: true });
      return { ok: true, decision };
    }

    const actionType = decision === "ban" ? "permanent_ban" : "indefinite_suspension";
    const hidden = await hideAuthorCommunityContent({ firestore, partition: dataPartition, authorId: reportedId, moderatorId: operatorId, reportId });
    await firestore.runTransaction(async (transaction) => {
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
    await auth.updateUser(reportedId, { disabled: true });
    await auth.revokeRefreshTokens(reportedId);
    return { ok: true, decision, ...hidden };
  });

  const restoreCommunityAccount = onCall(withAppCheck(), async (request) => {
    const operatorId = await requireOperations(firestore, request.auth);
    const input = requestData(request);
    const userId = safeUid(input.userId);
    const reason = text(input.reason, MAX_ACTION_REASON_LENGTH);
    if (!reason) throw new HttpsError("invalid-argument", "해제 사유를 입력해주세요.");
    const userRef = firestore.collection("users").doc(userId);
    const user = await userRef.get();
    if (!user.exists) throw new HttpsError("not-found", "계정을 찾을 수 없어요.");
    if (text(user.get("status"), 40) === "banned") {
      throw new HttpsError("failed-precondition", "영구 정지는 별도 운영 절차로 검토해주세요.");
    }
    await userRef.set({
      status: "active", loginDisabled: false, isActive: true,
      moderationRestoredBy: operatorId, moderationRestoredAt: FieldValue.serverTimestamp(),
      moderationRestoreReason: reason, updatedAt: FieldValue.serverTimestamp(),
    }, { merge: true });
    await auth.updateUser(userId, { disabled: false });
    await firestore.collection("moderation_audit_logs").add({
      type: "suspension_lifted", userId, reason, actorId: operatorId,
      createdAt: FieldValue.serverTimestamp(),
    });
    return { ok: true };
  });

  return { getCommunityModerationAccess, listCommunityModerationReports, setCommunityReportReviewing, decideCommunityReport, restoreCommunityAccount };
}

// The schedule persists queue alerts for the admin app. It never makes an
// automated moderation decision: reports remain human-reviewed.
export function createCommunityModerationDeadlineSchedule(firestore: Firestore) {
  return onSchedule({ schedule: "every 15 minutes", timeZone: "Asia/Seoul" }, async () => {
    const now = Date.now();
    const reports = await firestore.collection("reports").orderBy("createdAt", "desc").limit(MAX_REPORTS).get();
    const batch = firestore.batch();
    for (const doc of reports.docs) {
      const data = record(doc.data());
      if (!["bamboo_post", "bamboo_comment"].includes(text(data.source, 80))) continue;
      if (!["pending", "reviewing"].includes(text(data.status, 40))) continue;
      const createdAt = timestampMs(data.createdAt);
      const deadline = timestampMs(data.deadlineAt) ?? (createdAt == null ? null : createdAt + 24 * HOUR_MS);
      if (deadline == null) continue;
      const ageMs = now - (createdAt ?? now);
      const level = now >= deadline ? "overdue" : ageMs >= 23 * HOUR_MS ? "23h" : ageMs >= 20 * HOUR_MS ? "20h" : ageMs <= 15 * 60 * 1000 ? "new" : null;
      if (level == null) continue;
      const alertRef = firestore.collection("moderation_alerts").doc(`${doc.id}_${level}_${level === "overdue" ? Math.floor(now / HOUR_MS) : "once"}`);
      batch.set(alertRef, {
        reportId: doc.id, level, dataPartition: partition(data.dataPartition), deadlineAt: data.deadlineAt,
        createdAt: FieldValue.serverTimestamp(), unread: true,
      }, { merge: true });
    }
    await batch.commit();
  });
}
