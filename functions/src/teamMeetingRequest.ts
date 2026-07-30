import { createHash } from "crypto";
import {
  FieldValue,
  type Firestore,
  type Transaction,
} from "firebase-admin/firestore";
import {
  HttpsError,
  onCall,
  type CallableOptions,
  type CallableRequest,
} from "firebase-functions/v2/https";

import { canTransitionTeamMeetingRequest } from "./seasonMeetingStateMachine";

export const CREATE_TEAM_MEETING_REQUEST_CALLABLE_OPTIONS: CallableOptions = {
  timeoutSeconds: 30,
  memory: "256MiB",
  invoker: "public",
  enforceAppCheck: true,
};

export const RESPOND_TEAM_MEETING_REQUEST_CALLABLE_OPTIONS: CallableOptions = {
  timeoutSeconds: 30,
  memory: "256MiB",
  invoker: "public",
  enforceAppCheck: true,
};

type ResolvedCallableUser = {
  userId: string;
};

type ResolveCallableUser = (
  request: CallableRequest<unknown>
) => Promise<ResolvedCallableUser>;

type TeamMeetingRequestStatus = "pending" | "accepted" | "declined";

type CreatePlan = {
  requestId: string;
  pairLockId: string;
  responseStatus: TeamMeetingRequestStatus;
  requestData: Record<string, unknown>;
};

type RespondPlan = {
  status: TeamMeetingRequestStatus;
  matchId?: string;
  requestUpdate?: Record<string, unknown>;
  matchData?: Record<string, unknown>;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

const SAFE_PATH_SEGMENT = /^[A-Za-z0-9_-]{1,128}$/;

function requireSafePathSegment(value: unknown, fieldName: string): string {
  const segment = asString(value);
  if (!SAFE_PATH_SEGMENT.test(segment)) {
    throw new HttpsError("invalid-argument", `${fieldName} is invalid.`);
  }
  return segment;
}

function requireBoolean(value: unknown, fieldName: string): boolean {
  if (typeof value !== "boolean") {
    throw new HttpsError("invalid-argument", `${fieldName} must be a boolean.`);
  }
  return value;
}

function readStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map(asString).filter((item) => item.length > 0);
}

function dedupeSorted(values: string[]): string[] {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))].sort();
}

function stableHashId(prefix: string, value: string): string {
  return `${prefix}_${createHash("sha256").update(value).digest("hex").slice(0, 32)}`;
}

export function teamMeetingRequestId(
  sourceResultId: string,
  leftTeamId: string,
  rightTeamId: string
): string {
  const pair = [leftTeamId, rightTeamId].sort().join("|");
  return stableHashId("tmr", `${sourceResultId}|${pair}`);
}

export function teamMeetingPairLockId(
  leftTeamId: string,
  rightTeamId: string
): string {
  const pair = [leftTeamId, rightTeamId].sort().join("|");
  return stableHashId("tmpl", pair);
}

export function teamMeetingMatchId(requestId: string): string {
  return stableHashId("tmm", requestId);
}

export function isPendingTeamPairRequest(
  requestData: Record<string, unknown>,
  leftTeamId: string,
  rightTeamId: string
): boolean {
  if (asString(requestData.status) !== "pending") return false;
  const expectedPair = [leftTeamId, rightTeamId].sort().join("|");
  const requestPair = [
    asString(requestData.fromTeamId),
    asString(requestData.toTeamId),
  ].sort().join("|");
  return requestPair === expectedPair;
}

export function buildPendingPairRepair(params: {
  requestId: string;
  pairLockId: string;
  fromTeamId: string;
  toTeamId: string;
  sourceResultId: string;
}): {
  requestUpdate: Record<string, unknown>;
  pairLockData: Record<string, unknown>;
} {
  return {
    requestUpdate: { pairLockId: params.pairLockId },
    pairLockData: {
      requestId: params.requestId,
      status: "pending",
      fromTeamId: params.fromTeamId,
      toTeamId: params.toTeamId,
      sourceResultId: params.sourceResultId,
    },
  };
}

function readTeamSnapshot(
  matchResultData: Record<string, unknown>,
  groupId: string
): Record<string, unknown> | null {
  const requesting = isRecord(matchResultData.requestingTeamSnapshot)
    ? matchResultData.requestingTeamSnapshot
    : null;
  const matched = isRecord(matchResultData.matchedTeamSnapshot)
    ? matchResultData.matchedTeamSnapshot
    : null;

  if (asString(requesting?.groupId) === groupId) return requesting;
  if (asString(matched?.groupId) === groupId) return matched;
  return null;
}

function memberUidsFromSnapshot(snapshot: Record<string, unknown>): string[] {
  const members = Array.isArray(snapshot.membersSnapshot)
    ? snapshot.membersSnapshot
    : [];
  return dedupeSorted(
    members
      .filter(isRecord)
      .map((member) => asString(member.uid))
  );
}

function requirePendingTargetMember(
  requestData: Record<string, unknown>,
  callerUid: string
): void {
  const toTeamMemberUids = readStringList(requestData.toTeamMemberUids);
  if (!toTeamMemberUids.includes(callerUid)) {
    throw new HttpsError(
      "permission-denied",
      "받은 팀 구성원만 응답할 수 있어요."
    );
  }
}

export function buildCreateTeamMeetingRequestPlan(params: {
  sourceResultId: string;
  viewerGroupId: string;
  callerUid: string;
  matchResultData: Record<string, unknown>;
}): CreatePlan {
  const sourceResultId = requireSafePathSegment(params.sourceResultId, "sourceResultId");
  const viewerGroupId = requireSafePathSegment(params.viewerGroupId, "viewerGroupId");

  const participantUids = readStringList(params.matchResultData.participantUids);
  if (!participantUids.includes(params.callerUid)) {
    throw new HttpsError("permission-denied", "매칭 참여자만 요청할 수 있어요.");
  }

  const groupIds = readStringList(params.matchResultData.groupIds);
  if (!groupIds.includes(viewerGroupId) || groupIds.length < 2) {
    throw new HttpsError("failed-precondition", "매칭 팀 정보를 확인할 수 없어요.");
  }

  const otherTeamId = groupIds.find((groupId) => groupId !== viewerGroupId) ?? "";
  const fromTeamSnapshot = readTeamSnapshot(params.matchResultData, viewerGroupId);
  const toTeamSnapshot = readTeamSnapshot(params.matchResultData, otherTeamId);
  if (!otherTeamId || fromTeamSnapshot == null || toTeamSnapshot == null) {
    throw new HttpsError("failed-precondition", "상대 팀 정보를 찾을 수 없어요.");
  }

  const fromTeamMemberUids = memberUidsFromSnapshot(fromTeamSnapshot);
  const toTeamMemberUids = memberUidsFromSnapshot(toTeamSnapshot);
  if (!fromTeamMemberUids.includes(params.callerUid)) {
    throw new HttpsError("permission-denied", "내 팀에 속한 사용자만 요청할 수 있어요.");
  }
  if (fromTeamMemberUids.length !== 3 || toTeamMemberUids.length !== 3) {
    throw new HttpsError("failed-precondition", "3인 팀끼리만 요청할 수 있어요.");
  }

  const pairLockId = teamMeetingPairLockId(viewerGroupId, otherTeamId);
  return {
    requestId: teamMeetingRequestId(sourceResultId, viewerGroupId, otherTeamId),
    pairLockId,
    responseStatus: "pending",
    requestData: {
      pairLockId,
      source: "slot_result",
      sourceResultId,
      fromTeamId: viewerGroupId,
      toTeamId: otherTeamId,
      fromTeamMemberUids,
      toTeamMemberUids,
      fromTeamSnapshot,
      toTeamSnapshot,
      participantUids: dedupeSorted([...fromTeamMemberUids, ...toTeamMemberUids]),
      createdByUserId: params.callerUid,
      status: "pending",
      respondedByUserId: null,
      respondedAt: null,
      matchId: null,
    },
  };
}

export function buildRespondTeamMeetingRequestPlan(params: {
  requestId: string;
  requestData: Record<string, unknown>;
  callerUid: string;
  accept: unknown;
}): RespondPlan {
  const requestId = requireSafePathSegment(params.requestId, "requestId");
  const accept = requireBoolean(params.accept, "accept");
  requirePendingTargetMember(params.requestData, params.callerUid);

  const status = asString(params.requestData.status) || "pending";
  if (status === "accepted") {
    const matchId = asString(params.requestData.matchId);
    if (!matchId) {
      throw new HttpsError("failed-precondition", "이미 처리된 요청 상태가 올바르지 않아요.");
    }
    return { status: "accepted", matchId };
  }
  if (status === "declined") {
    return { status: "declined" };
  }
  if (status !== "pending") {
    throw new HttpsError("failed-precondition", "이미 처리된 요청이에요.");
  }

  const participantUids = dedupeSorted([
    ...readStringList(params.requestData.fromTeamMemberUids),
    ...readStringList(params.requestData.toTeamMemberUids),
  ]);
  if (participantUids.length !== 6) {
    throw new HttpsError("failed-precondition", "요청 팀 정보가 올바르지 않아요.");
  }

  if (!accept) {
    if (!canTransitionTeamMeetingRequest("pending", "declined")) {
      throw new HttpsError("failed-precondition", "이미 처리된 요청이에요.");
    }
    return {
      status: "declined",
      requestUpdate: {
        status: "declined",
        respondedByUserId: params.callerUid,
      },
    };
  }

  if (!canTransitionTeamMeetingRequest("pending", "accepted")) {
    throw new HttpsError("failed-precondition", "이미 처리된 요청이에요.");
  }

  const matchId = teamMeetingMatchId(requestId);
  return {
    status: "accepted",
    matchId,
    requestUpdate: {
      status: "accepted",
      respondedByUserId: params.callerUid,
      matchId,
    },
    matchData: {
      requestId,
      leftTeamId: params.requestData.fromTeamId,
      rightTeamId: params.requestData.toTeamId,
      leftTeamSnapshot: params.requestData.fromTeamSnapshot,
      rightTeamSnapshot: params.requestData.toTeamSnapshot,
      leftMemberUids: readStringList(params.requestData.fromTeamMemberUids),
      rightMemberUids: readStringList(params.requestData.toTeamMemberUids),
      participantUids,
      status: "active",
      acceptedByUserId: params.callerUid,
      source: "team_request_accept",
    },
  };
}

function getCallableData(request: CallableRequest<unknown>): Record<string, unknown> {
  return isRecord(request.data) ? request.data : {};
}

export function createTeamMeetingRequestFunction(
  firestore: Firestore,
  resolveUser: ResolveCallableUser
) {
  return onCall(
    CREATE_TEAM_MEETING_REQUEST_CALLABLE_OPTIONS,
    async (request): Promise<Record<string, unknown>> => {
      const user = await resolveUser(request);
      const data = getCallableData(request);
      const sourceResultId = requireSafePathSegment(
        data.sourceResultId,
        "sourceResultId"
      );
      const viewerGroupId = requireSafePathSegment(data.viewerGroupId, "viewerGroupId");
      const resultRef = firestore.collection("eventTeamMatches").doc(sourceResultId);

      const response = await firestore.runTransaction(async (tx: Transaction) => {
        const resultSnap = await tx.get(resultRef);
        if (!resultSnap.exists || resultSnap.data() == null) {
          throw new HttpsError("not-found", "매칭 결과를 찾을 수 없어요.");
        }
        const plan = buildCreateTeamMeetingRequestPlan({
          sourceResultId,
          viewerGroupId,
          callerUid: user.userId,
          matchResultData: (resultSnap.data() ?? {}) as Record<string, unknown>,
        });
        const requests = firestore.collection("eventTeamMeetingRequests");
        const requestRef = requests.doc(plan.requestId);
        const pairLockRef = firestore
          .collection("eventTeamMeetingRequestLocks")
          .doc(plan.pairLockId);
        const pairLockSnap = await tx.get(pairLockRef);
        const pairLockData = (pairLockSnap.data() ?? {}) as Record<string, unknown>;
        const lockedRequestId = asString(pairLockData.status) === "pending"
          ? requireSafePathSegment(pairLockData.requestId, "lockedRequestId")
          : "";
        const lockedRequestRef = lockedRequestId
          ? requests.doc(lockedRequestId)
          : null;
        const lockedRequestSnap = lockedRequestRef
          ? await tx.get(lockedRequestRef)
          : null;
        const existingSnap =
          lockedRequestRef?.id === requestRef.id && lockedRequestSnap != null
            ? lockedRequestSnap
            : await tx.get(requestRef);

        if (lockedRequestSnap?.exists) {
          const lockedRequest = (lockedRequestSnap.data() ?? {}) as Record<string, unknown>;
          if (isPendingTeamPairRequest(
            lockedRequest,
            asString(plan.requestData.fromTeamId),
            asString(plan.requestData.toTeamId)
          )) {
            const repair = buildPendingPairRepair({
              requestId: lockedRequestSnap.id,
              pairLockId: plan.pairLockId,
              fromTeamId: asString(lockedRequest.fromTeamId),
              toTeamId: asString(lockedRequest.toTeamId),
              sourceResultId: asString(lockedRequest.sourceResultId) || sourceResultId,
            });
            tx.set(
              lockedRequestSnap.ref,
              {
                ...repair.requestUpdate,
                updatedAt: FieldValue.serverTimestamp(),
              },
              { merge: true }
            );
            tx.set(
              pairLockRef,
              {
                ...repair.pairLockData,
                updatedAt: FieldValue.serverTimestamp(),
              },
              { merge: true }
            );
            return {
              requestId: lockedRequestSnap.id,
              status: "pending",
              matchId: asString(lockedRequest.matchId) || undefined,
            };
          }
        }

        if (existingSnap.exists) {
          const existing = (existingSnap.data() ?? {}) as Record<string, unknown>;
          if (isPendingTeamPairRequest(
            existing,
            asString(plan.requestData.fromTeamId),
            asString(plan.requestData.toTeamId)
          )) {
            const repair = buildPendingPairRepair({
              requestId: requestRef.id,
              pairLockId: plan.pairLockId,
              fromTeamId: asString(plan.requestData.fromTeamId),
              toTeamId: asString(plan.requestData.toTeamId),
              sourceResultId,
            });
            tx.set(
              requestRef,
              {
                ...repair.requestUpdate,
                updatedAt: FieldValue.serverTimestamp(),
              },
              { merge: true }
            );
            tx.set(
              pairLockRef,
              {
                ...repair.pairLockData,
                updatedAt: FieldValue.serverTimestamp(),
              },
              { merge: true }
            );
            return {
              requestId: requestRef.id,
              status: "pending",
              matchId: asString(existing.matchId) || undefined,
            };
          }
        }

        const fromTeamId = asString(plan.requestData.fromTeamId);
        const toTeamId = asString(plan.requestData.toTeamId);
        const pendingForward = requests
          .where("fromTeamId", "==", fromTeamId)
          .where("toTeamId", "==", toTeamId)
          .where("status", "==", "pending")
          .limit(1);
        const pendingReverse = requests
          .where("fromTeamId", "==", toTeamId)
          .where("toTeamId", "==", fromTeamId)
          .where("status", "==", "pending")
          .limit(1);
        const [pendingForwardSnap, pendingReverseSnap] = await Promise.all([
          tx.get(pendingForward),
          tx.get(pendingReverse),
        ]);
        const legacyPendingSnap = [
          ...pendingForwardSnap.docs,
          ...pendingReverseSnap.docs,
        ].find((doc) =>
          isPendingTeamPairRequest(
            (doc.data() ?? {}) as Record<string, unknown>,
            fromTeamId,
            toTeamId
          )
        );

        if (legacyPendingSnap) {
          const legacyData = (legacyPendingSnap.data() ?? {}) as Record<string, unknown>;
          tx.set(
            legacyPendingSnap.ref,
            {
              pairLockId: plan.pairLockId,
              updatedAt: FieldValue.serverTimestamp(),
            },
            { merge: true }
          );
          tx.set(
            pairLockRef,
            {
              requestId: legacyPendingSnap.id,
              status: "pending",
              fromTeamId: legacyData.fromTeamId,
              toTeamId: legacyData.toTeamId,
              sourceResultId: asString(legacyData.sourceResultId) || sourceResultId,
              updatedAt: FieldValue.serverTimestamp(),
            },
            { merge: true }
          );
          return {
            requestId: legacyPendingSnap.id,
            status: "pending",
            matchId: asString(legacyData.matchId) || undefined,
          };
        }

        if (existingSnap.exists) {
          const existing = (existingSnap.data() ?? {}) as Record<string, unknown>;
          return {
            requestId: requestRef.id,
            status: asString(existing.status) || "pending",
            matchId: asString(existing.matchId) || undefined,
          };
        }
        tx.set(requestRef, {
          ...plan.requestData,
          createdAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        });
        tx.set(pairLockRef, {
          requestId: requestRef.id,
          status: "pending",
          fromTeamId: plan.requestData.fromTeamId,
          toTeamId: plan.requestData.toTeamId,
          sourceResultId,
          createdAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        });
        return { requestId: requestRef.id, status: plan.responseStatus };
      });

      return response;
    }
  );
}

export function createRespondTeamMeetingRequestFunction(
  firestore: Firestore,
  resolveUser: ResolveCallableUser
) {
  return onCall(
    RESPOND_TEAM_MEETING_REQUEST_CALLABLE_OPTIONS,
    async (request): Promise<Record<string, unknown>> => {
      const user = await resolveUser(request);
      const data = getCallableData(request);
      const requestId = requireSafePathSegment(data.requestId, "requestId");
      const accept = requireBoolean(data.accept, "accept");
      const requestRef = firestore.collection("eventTeamMeetingRequests").doc(requestId);

      return firestore.runTransaction(async (tx: Transaction) => {
        const requestSnap = await tx.get(requestRef);
        if (!requestSnap.exists || requestSnap.data() == null) {
          throw new HttpsError("not-found", "요청 문서를 찾을 수 없어요.");
        }
        const requestData = (requestSnap.data() ?? {}) as Record<string, unknown>;
        const plan = buildRespondTeamMeetingRequestPlan({
          requestId,
          requestData,
          callerUid: user.userId,
          accept,
        });
        const rawPairLockId = asString(requestData.pairLockId);
        const pairLockRef = rawPairLockId
          ? firestore
              .collection("eventTeamMeetingRequestLocks")
              .doc(requireSafePathSegment(rawPairLockId, "pairLockId"))
          : null;
        const pairLockSnap = pairLockRef ? await tx.get(pairLockRef) : null;
        if (plan.requestUpdate) {
          tx.update(requestRef, {
            ...plan.requestUpdate,
            respondedAt: FieldValue.serverTimestamp(),
            updatedAt: FieldValue.serverTimestamp(),
          });
          const pairLockData = (pairLockSnap?.data() ?? {}) as Record<string, unknown>;
          if (pairLockRef && asString(pairLockData.requestId) === requestId) {
            tx.set(
              pairLockRef,
              {
                status: plan.status,
                updatedAt: FieldValue.serverTimestamp(),
              },
              { merge: true }
            );
          }
        }
        if (plan.matchId && plan.matchData) {
          tx.set(
            firestore.collection("eventThreeVsThreeMatches").doc(plan.matchId),
            {
              ...plan.matchData,
              createdAt: FieldValue.serverTimestamp(),
              updatedAt: FieldValue.serverTimestamp(),
            },
            { merge: false }
          );
        }
        return plan.matchId
          ? { status: plan.status, matchId: plan.matchId }
          : { status: plan.status };
      });
    }
  );
}