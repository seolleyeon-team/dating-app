const fs = require('fs');
const path = 'functions/src/teamMeetingRequest.ts';
let content = fs.readFileSync(path, 'utf8');

function replaceExactly(pattern, replacement, count, label) {
  const matches = content.match(pattern) ?? [];
  if (matches.length !== count) throw new Error(`${label}: expected ${count}, found ${matches.length}`);
  content = content.replace(pattern, replacement);
}

replaceExactly(
  /type CreatePlan = \{\r?\n  requestId: string;/,
  'type CreatePlan = {\n  requestId: string;\n  pairLockId: string;',
  1,
  'CreatePlan pair lock field'
);

replaceExactly(
  /export function teamMeetingRequestId\([\s\S]*?\n\}\n\nexport function teamMeetingMatchId/,
  `export function teamMeetingRequestId(
  sourceResultId: string,
  leftTeamId: string,
  rightTeamId: string
): string {
  const pair = [leftTeamId, rightTeamId].sort().join("|");
  return stableHashId("tmr", \`\${sourceResultId}|\${pair}\`);
}

export function teamMeetingPairLockId(
  leftTeamId: string,
  rightTeamId: string
): string {
  const pair = [leftTeamId, rightTeamId].sort().join("|");
  return stableHashId("tmpl", pair);
}

export function teamMeetingMatchId`,
  1,
  'pair lock id helper'
);

replaceExactly(
  /return \{\r?\n    requestId: teamMeetingRequestId\(sourceResultId, viewerGroupId, otherTeamId\),\r?\n    responseStatus: "pending",\r?\n    requestData: \{/,
  'return {\n    requestId: teamMeetingRequestId(sourceResultId, viewerGroupId, otherTeamId),\n    pairLockId: teamMeetingPairLockId(viewerGroupId, otherTeamId),\n    responseStatus: "pending",\n    requestData: {\n      pairLockId: teamMeetingPairLockId(viewerGroupId, otherTeamId),',
  1,
  'plan pair lock data'
);

replaceExactly(
  /      const response = await firestore\.runTransaction\(async \(tx: Transaction\) => \{[\s\S]*?\n      return response;/,
  `      const response = await firestore.runTransaction(async (tx: Transaction) => {
        const resultSnap = await tx.get(resultRef);
        if (!resultSnap.exists || resultSnap.data() == null) {
          throw new HttpsError("not-found", "\uB9E4\uCE6D \uACB0\uACFC\uB97C \uCC3E\uC744 \uC218 \uC5C6\uC5B4\uC694.");
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
          if (asString(lockedRequest.status) === "pending") {
            return {
              requestId: lockedRequestSnap.id,
              status: "pending",
              matchId: asString(lockedRequest.matchId) || undefined,
            };
          }
        }

        if (existingSnap.exists) {
          const existing = (existingSnap.data() ?? {}) as Record<string, unknown>;
          const existingStatus = asString(existing.status) || "pending";
          if (existingStatus === "pending") {
            tx.set(pairLockRef, {
              requestId: requestRef.id,
              status: "pending",
              fromTeamId: plan.requestData.fromTeamId,
              toTeamId: plan.requestData.toTeamId,
              sourceResultId,
              updatedAt: FieldValue.serverTimestamp(),
            });
          }
          return {
            requestId: requestRef.id,
            status: existingStatus,
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

      return response;`,
  1,
  'create transaction pair lock'
);

replaceExactly(
  /        const plan = buildRespondTeamMeetingRequestPlan\(\{\r?\n          requestId,\r?\n          requestData: \(requestSnap\.data\(\) \?\? \{\}\) as Record<string, unknown>,\r?\n          callerUid: user\.userId,\r?\n          accept,\r?\n        \}\);\r?\n        if \(plan\.requestUpdate\) \{/,
  `        const requestData = (requestSnap.data() ?? {}) as Record<string, unknown>;
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
        if (plan.requestUpdate) {`,
  1,
  'respond pair lock read'
);

replaceExactly(
  /          tx\.update\(requestRef, \{\r?\n            \.\.\.plan\.requestUpdate,\r?\n            respondedAt: FieldValue\.serverTimestamp\(\),\r?\n            updatedAt: FieldValue\.serverTimestamp\(\),\r?\n          \}\);\r?\n        \}/,
  `          tx.update(requestRef, {
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
        }`,
  1,
  'respond pair lock update'
);

fs.writeFileSync(path, content);
