import { FieldPath, FieldValue, type Firestore } from "firebase-admin/firestore";
import { HttpsError, onCall } from "firebase-functions/v2/https";

import { withAppCheck } from "./appCheckPolicy";

type AuthContext = {
  uid?: string;
  token?: Record<string, unknown>;
} | null | undefined;

type ResolvedAppUser = {
  userId: string;
  data: Record<string, unknown>;
  profileSnapshot: Record<string, unknown>;
};

type CallableRequestLike = {
  auth?: AuthContext;
  data?: unknown;
  rawRequest?: { body?: unknown } | null;
};

type SupportOperationsDependencies = {
  firestore: Firestore;
  resolveAppUser: (auth: AuthContext) => Promise<ResolvedAppUser>;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asText(value: unknown, maxLength = 4000): string {
  return typeof value === "string" ? value.trim().slice(0, maxLength) : "";
}

function callableData(request: CallableRequestLike): Record<string, unknown> {
  if (request.data && typeof request.data === "object" && !Array.isArray(request.data)) {
    return request.data as Record<string, unknown>;
  }
  const body = request.rawRequest?.body;
  return body && typeof body === "object" && !Array.isArray(body)
    ? asRecord(asRecord(body).data)
    : {};
}

function isOperationsAccount(data: Record<string, unknown>): boolean {
  return data.accountType === "operations";
}

function userIsInactive(data: Record<string, unknown>): boolean {
  const status = asText(data.status, 80).toLowerCase();
  return data.isDeleted === true ||
    data.isWithdrawn === true ||
    data.loginDisabled === true ||
    data.isActive === false ||
    ["banned", "blocked", "deleted", "suspended", "withdrawn"].includes(status);
}

function displayProfile(uid: string, data: Record<string, unknown>) {
  const onboarding = asRecord(data.onboarding);
  const nickname = asText(data.nickname, 80) || asText(onboarding.nickname, 80) || "이름 미설정";
  const university = asText(data.university, 100) || asText(onboarding.university, 100);
  const avatar = asText(data.profileImageUrl, 2048) || asText(onboarding.representativeImageUrl, 2048);
  return {
    userId: uid,
    nickname,
    university,
    avatarUrl: avatar || null,
  };
}

export function buildSupportRoomId(operatorId: string, userId: string): string {
  return `support_${operatorId}_${userId}`;
}

async function requireOperations(
  firestore: Firestore,
  auth: AuthContext,
): Promise<string> {
  const uid = asText(auth?.uid, 128);
  if (!uid) throw new HttpsError("unauthenticated", "로그인이 필요해요.");
  if (auth?.token?.operations !== true) {
    throw new HttpsError("permission-denied", "운영팀 권한이 필요해요.");
  }
  const adminSnap = await firestore.collection("admin").doc(uid).get();
  if (!adminSnap.exists || adminSnap.data()?.active !== true) {
    throw new HttpsError("permission-denied", "운영팀 계정을 확인할 수 없어요.");
  }
  return uid;
}

async function resolveActiveOperator(firestore: Firestore): Promise<string> {
  const snapshot = await firestore
    .collection("admin")
    .where("active", "==", true)
    .limit(2)
    .get();
  if (snapshot.size !== 1) {
    throw new HttpsError(
      "failed-precondition",
      "활성 운영팀 계정이 정확히 하나여야 해요.",
    );
  }
  return snapshot.docs[0].id;
}

async function createOrReuseSupportRoom(params: {
  firestore: Firestore;
  operatorId: string;
  userId: string;
  userData: Record<string, unknown>;
  initialMessage?: Record<string, unknown>;
  latestCaseField?: "latestInquiryId" | "latestIssueReportId";
  latestCaseId?: string;
}): Promise<string> {
  const roomId = buildSupportRoomId(params.operatorId, params.userId);
  const roomRef = params.firestore.collection("chat_rooms").doc(roomId);
  const operatorRef = params.firestore.collection("users").doc(params.operatorId);

  await params.firestore.runTransaction(async (transaction) => {
    const [roomSnap, operatorSnap] = await Promise.all([
      transaction.get(roomRef),
      transaction.get(operatorRef),
    ]);
    if (!operatorSnap.exists || !isOperationsAccount(asRecord(operatorSnap.data()))) {
      throw new HttpsError("failed-precondition", "운영팀 프로필을 찾을 수 없어요.");
    }

    const participantIds = [params.operatorId, params.userId].sort();
    const roomBase = {
      roomId,
      roomType: "support",
      type: "support",
      status: "active",
      supportStatus: "open",
      participantIds,
      userId: params.userId,
      operatorId: params.operatorId,
      participantInfo: {
        [params.operatorId]: displayProfile(params.operatorId, asRecord(operatorSnap.data())),
        [params.userId]: displayProfile(params.userId, params.userData),
      },
      updatedAt: FieldValue.serverTimestamp(),
    };

    if (!roomSnap.exists) {
      transaction.create(roomRef, {
        ...roomBase,
        createdAt: FieldValue.serverTimestamp(),
        lastMessage: "",
        lastMessageAt: null,
      });
    } else {
      const existingIds = roomSnap.data()?.participantIds;
      if (!Array.isArray(existingIds) || existingIds.join("|") !== participantIds.join("|")) {
        throw new HttpsError("failed-precondition", "지원 채팅방 정보가 올바르지 않아요.");
      }
      transaction.set(roomRef, roomBase, { merge: true });
    }

    if (params.initialMessage) {
      const messageRef = roomRef.collection("messages").doc();
      const text = asText(params.initialMessage.text, 4000);
      transaction.create(messageRef, {
        ...params.initialMessage,
        text,
        senderId: "system",
        readBy: [],
        createdAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      });
      transaction.set(roomRef, {
        lastMessage: text.slice(0, 180),
        lastMessageAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
        ...(params.latestCaseField && params.latestCaseId
          ? { [params.latestCaseField]: params.latestCaseId }
          : {}),
      }, { merge: true });
    }
  });
  return roomId;
}

export function createSupportOperationsCallables(deps: SupportOperationsDependencies) {
  const { firestore } = deps;

  const listSupportUsers = onCall(withAppCheck(), async (request) => {
    await requireOperations(firestore, request.auth);
    const data = callableData(request);
    const pageSize = Math.min(Math.max(Number(data.pageSize) || 30, 1), 50);
    const pageToken = asText(data.pageToken, 256);
    const search = asText(data.search, 80).toLowerCase();
    const users: ReturnType<typeof displayProfile>[] = [];
    let cursor = pageToken;
    let exhausted = false;
    // Filtering is server-side because `users/{uid}` is private. Continue
    // scanning until a display page is full, so inactive/staff documents do
    // not make later users disappear from pagination.
    while (users.length < pageSize && !exhausted) {
      let query = firestore.collection("users").orderBy(FieldPath.documentId()).limit(200);
      if (cursor) query = query.startAfter(cursor);
      const snapshot = await query.get();
      if (snapshot.empty) {
        exhausted = true;
        break;
      }
      for (const doc of snapshot.docs) {
        const value = asRecord(doc.data());
        cursor = doc.id;
        if (isOperationsAccount(value) || userIsInactive(value)) continue;
        const profile = displayProfile(doc.id, value);
        if (search && !profile.nickname.toLowerCase().includes(search)) continue;
        users.push(profile);
        if (users.length >= pageSize) break;
      }
      exhausted = snapshot.size < 200;
    }
    return {
      users,
      nextPageToken: exhausted ? null : cursor || null,
    };
  });

  const openSupportChat = onCall(withAppCheck(), async (request) => {
    const operatorId = await requireOperations(firestore, request.auth);
    const userId = asText(callableData(request).userId, 128);
    if (!userId || userId === operatorId) {
      throw new HttpsError("invalid-argument", "사용자 정보가 올바르지 않아요.");
    }
    const userSnap = await firestore.collection("users").doc(userId).get();
    if (!userSnap.exists || isOperationsAccount(asRecord(userSnap.data())) || userIsInactive(asRecord(userSnap.data()))) {
      throw new HttpsError("not-found", "채팅을 시작할 수 있는 사용자를 찾지 못했어요.");
    }
    const roomId = await createOrReuseSupportRoom({
      firestore,
      operatorId,
      userId,
      userData: asRecord(userSnap.data()),
    });
    return { roomId, user: displayProfile(userId, asRecord(userSnap.data())) };
  });

  async function submitSupportCase(
    request: CallableRequestLike,
    kind: "inquiry" | "issue_report",
  ) {
    const user = await deps.resolveAppUser(request.auth);
    const data = callableData(request);
    const category = asText(data.category, 100);
    const content = asText(data.content, 4000);
    const allowOperationsFollowUp = data.allowOperationsFollowUp === true;
    if (!category || !content) {
      throw new HttpsError("invalid-argument", "문의 종류와 내용을 입력해주세요.");
    }

    const collection = kind === "inquiry" ? "app_inquiries" : "app_issue_reports";
    const ownerField = kind === "inquiry" ? "inquirerId" : "reporterId";
    const caseRef = firestore.collection(collection).doc();
    const operatorId = allowOperationsFollowUp
      ? await resolveActiveOperator(firestore)
      : null;
    const roomId = operatorId
      ? buildSupportRoomId(operatorId, user.userId)
      : null;
    const roomRef = roomId ? firestore.collection("chat_rooms").doc(roomId) : null;

    await firestore.runTransaction(async (transaction) => {
      const operatorRef = operatorId ? firestore.collection("users").doc(operatorId) : null;
      const [operatorSnap, roomSnap] = operatorRef && roomRef
        ? await Promise.all([transaction.get(operatorRef), transaction.get(roomRef)])
        : [null, null];
      if (operatorId && (!operatorSnap?.exists || !isOperationsAccount(asRecord(operatorSnap.data())))) {
        throw new HttpsError("failed-precondition", "운영팀 프로필을 찾을 수 없어요.");
      }

      transaction.create(caseRef, {
        [ownerField]: user.userId,
        category,
        content,
        allowContact: allowOperationsFollowUp,
        allowOperationsFollowUp,
        sourceScreen: asText(data.sourceScreen, 100) || `settings_${kind}`,
        platform: asText(data.platform, 40) || "unknown",
        status: "pending",
        createdAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      });

      if (!operatorId || !roomRef || !operatorSnap) return;
      const participantIds = [operatorId, user.userId].sort();
      const roomBase = {
        roomId,
        roomType: "support",
        type: "support",
        status: "active",
        supportStatus: "open",
        participantIds,
        userId: user.userId,
        operatorId,
        participantInfo: {
          [operatorId]: displayProfile(operatorId, asRecord(operatorSnap.data())),
          [user.userId]: displayProfile(user.userId, user.data),
        },
        updatedAt: FieldValue.serverTimestamp(),
      };
      if (!roomSnap?.exists) {
        transaction.create(roomRef, {
          ...roomBase,
          createdAt: FieldValue.serverTimestamp(),
          lastMessage: "",
          lastMessageAt: null,
        });
      } else {
        const existingIds = roomSnap.data()?.participantIds;
        if (!Array.isArray(existingIds) || existingIds.join("|") !== participantIds.join("|")) {
          throw new HttpsError("failed-precondition", "지원 채팅방 정보가 올바르지 않아요.");
        }
        transaction.set(roomRef, roomBase, { merge: true });
      }

      const messageText = kind === "inquiry"
        ? `[문의] ${category}\n${content}`
        : `[문제 신고] ${category}\n${content}`;
      transaction.create(roomRef.collection("messages").doc(), {
        senderId: "system",
        type: kind === "inquiry" ? "support_inquiry" : "support_issue_report",
        messageType: kind === "inquiry" ? "support_inquiry" : "support_issue_report",
        text: messageText,
        supportCase: {
          caseId: caseRef.id,
          kind,
          category,
          content,
          submittedBy: user.userId,
          submittedAt: FieldValue.serverTimestamp(),
        },
        readBy: [],
        createdAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      });
      transaction.set(roomRef, {
        lastMessage: messageText.slice(0, 180),
        lastMessageAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
        [kind === "inquiry" ? "latestInquiryId" : "latestIssueReportId"]: caseRef.id,
      }, { merge: true });
    });

    return { caseId: caseRef.id, supportRoomId: roomId };
  }

  const submitInquiry = onCall(withAppCheck(), (request) => submitSupportCase(request, "inquiry"));
  const submitIssueReport = onCall(withAppCheck(), (request) => submitSupportCase(request, "issue_report"));

  return { listSupportUsers, openSupportChat, submitInquiry, submitIssueReport };
}
