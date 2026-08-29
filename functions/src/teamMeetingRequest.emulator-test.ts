/**
 * 시즌 미팅 request/accept 경로의 Firestore Emulator 통합 테스트.
 *
 * 실행 (repo root, Java 필요):
 *   npm --prefix functions run build
 *   firebase emulators:exec --only firestore --project demo-season-e2e \
 *     "node --test functions/lib/teamMeetingRequest.emulator-test.js"
 *
 * 일반 `npm test`(mock unit test)와 달리 실제 callable 핸들러(.run())를
 * 에뮬레이터 Firestore 트랜잭션 위에서 실행한다. 파일명이 *.test.js 가 아닌
 * *.emulator-test.js 로 컴파일되므로 기본 test glob에는 포함되지 않는다.
 */
import assert from "node:assert/strict";
import { test, before } from "node:test";

import { initializeApp } from "firebase-admin/app";
import { getFirestore, type Firestore } from "firebase-admin/firestore";
import { HttpsError, type CallableRequest } from "firebase-functions/v2/https";

import {
  createTeamMeetingRequestFunction,
  createRespondTeamMeetingRequestFunction,
  teamMeetingMatchId,
  teamMeetingPairLockId,
  teamMeetingRequestId,
} from "./teamMeetingRequest";
import { seasonMeetingChatRoomId } from "./seasonMeetingChat";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error(
    "FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`."
  );
}

let db: Firestore;

const resolveUser = async (request: CallableRequest<unknown>) => {
  const uid = request.auth?.uid;
  if (!uid) throw new HttpsError("unauthenticated", "auth required");
  return { userId: uid };
};

function callableRequest(uid: string, data: Record<string, unknown>) {
  return { data, auth: { uid }, rawRequest: {} } as unknown as CallableRequest<unknown>;
}

type TeamSpec = { teamId: string; memberUids: string[] };

function teamSnapshot(team: TeamSpec): Record<string, unknown> {
  return {
    groupId: team.teamId,
    membersSnapshot: team.memberUids.map((uid) => ({ uid, nickname: uid })),
  };
}

async function seedGroup(team: TeamSpec): Promise<void> {
  await db.collection("meetingGroups").doc(team.teamId).set({
    memberUids: team.memberUids,
    memberCount: team.memberUids.length,
    active: true,
    status: "open",
  });
}

async function seedSpinResult(
  resultId: string,
  requesting: TeamSpec,
  matched: TeamSpec
): Promise<void> {
  await db.collection("eventTeamMatches").doc(resultId).set({
    dateKey: "20260818",
    groupIds: [requesting.teamId, matched.teamId],
    participantUids: [...requesting.memberUids, ...matched.memberUids],
    requestingTeamSnapshot: teamSnapshot(requesting),
    matchedTeamSnapshot: teamSnapshot(matched),
    status: "created",
  });
}

function uniqueTeams(prefix: string): { a: TeamSpec; b: TeamSpec; c: TeamSpec } {
  return {
    a: { teamId: `${prefix}A`, memberUids: [`${prefix}a1`, `${prefix}a2`, `${prefix}a3`] },
    b: { teamId: `${prefix}B`, memberUids: [`${prefix}b1`, `${prefix}b2`, `${prefix}b3`] },
    c: { teamId: `${prefix}C`, memberUids: [`${prefix}c1`, `${prefix}c2`, `${prefix}c3`] },
  };
}

async function countMatchesForTeam(teamId: string): Promise<number> {
  const [left, right] = await Promise.all([
    db.collection("eventThreeVsThreeMatches").where("leftTeamId", "==", teamId).get(),
    db.collection("eventThreeVsThreeMatches").where("rightTeamId", "==", teamId).get(),
  ]);
  const active = new Set<string>();
  for (const doc of [...left.docs, ...right.docs]) {
    const status = String(doc.data().status ?? "").toLowerCase();
    if (!["cancelled", "canceled", "expired"].includes(status)) {
      active.add(doc.id);
    }
  }
  return active.size;
}

before(() => {
  initializeApp({ projectId: "demo-season-e2e" });
  db = getFirestore();
});

// -----------------------------------------------------------------------------
// Happy path: request 생성 → 상대 팀 수락 → match + room + lock 생성
// -----------------------------------------------------------------------------
test("E2E: create → accept produces exactly one match, room, and locks", async () => {
  const { a, b } = uniqueTeams("hp");
  await Promise.all([seedGroup(a), seedGroup(b)]);
  await seedSpinResult("hp_result", a, b);

  const createFn = createTeamMeetingRequestFunction(db, resolveUser);
  const respondFn = createRespondTeamMeetingRequestFunction(db, resolveUser);

  const created = (await createFn.run(
    callableRequest(a.memberUids[0], {
      sourceResultId: "hp_result",
      viewerGroupId: a.teamId,
    })
  )) as Record<string, unknown>;
  assert.equal(created.status, "pending");
  const requestId = String(created.requestId);
  assert.equal(requestId, teamMeetingRequestId("hp_result", a.teamId, b.teamId));

  const responded = (await respondFn.run(
    callableRequest(b.memberUids[1], { requestId, accept: true })
  )) as Record<string, unknown>;
  assert.equal(responded.status, "accepted");
  const matchId = String(responded.matchId);
  assert.equal(matchId, teamMeetingMatchId(requestId));

  const matchSnap = await db
    .collection("eventThreeVsThreeMatches")
    .doc(matchId)
    .get();
  assert.equal(matchSnap.exists, true);
  assert.equal(matchSnap.data()?.seasonPhase, "matched");
  assert.equal(matchSnap.data()?.chatRoomId, seasonMeetingChatRoomId(matchId));

  const roomSnap = await db
    .collection("chat_rooms")
    .doc(seasonMeetingChatRoomId(matchId))
    .get();
  assert.equal(roomSnap.exists, true);
  const participants = roomSnap.data()?.participantIds as string[];
  assert.equal(new Set(participants).size, 6);

  const lockSnap = await db
    .collection("eventTeamMeetingRequestLocks")
    .doc(teamMeetingPairLockId(a.teamId, b.teamId))
    .get();
  assert.equal(lockSnap.data()?.status, "accepted");

  assert.equal(await countMatchesForTeam(a.teamId), 1);
});

// -----------------------------------------------------------------------------
// 동일 request 이중 accept (동시)
// -----------------------------------------------------------------------------
test("race: double accept of the same request is idempotent (1 match, 1 room)", async () => {
  const { a, b } = uniqueTeams("da");
  await Promise.all([seedGroup(a), seedGroup(b)]);
  await seedSpinResult("da_result", a, b);

  const createFn = createTeamMeetingRequestFunction(db, resolveUser);
  const respondFn = createRespondTeamMeetingRequestFunction(db, resolveUser);
  const created = (await createFn.run(
    callableRequest(a.memberUids[0], {
      sourceResultId: "da_result",
      viewerGroupId: a.teamId,
    })
  )) as Record<string, unknown>;
  const requestId = String(created.requestId);

  const [r1, r2] = await Promise.all([
    respondFn.run(callableRequest(b.memberUids[0], { requestId, accept: true })),
    respondFn.run(callableRequest(b.memberUids[1], { requestId, accept: true })),
  ]);
  const results = [r1, r2] as Record<string, unknown>[];
  for (const result of results) {
    assert.equal(result.status, "accepted");
    assert.equal(result.matchId, teamMeetingMatchId(requestId));
  }

  assert.equal(await countMatchesForTeam(a.teamId), 1);
  const roomSnap = await db
    .collection("chat_rooms")
    .doc(seasonMeetingChatRoomId(teamMeetingMatchId(requestId)))
    .get();
  assert.equal(roomSnap.exists, true);
});

// -----------------------------------------------------------------------------
// A-B / A-C 동시 accept: 팀 A는 하나의 활성 match만 가질 수 있다
// -----------------------------------------------------------------------------
test("race: concurrent A-B and A-C accepts create exactly one active match for team A", async () => {
  const { a, b, c } = uniqueTeams("ac");
  await Promise.all([seedGroup(a), seedGroup(b), seedGroup(c)]);
  await seedSpinResult("ac_result_ab", a, b);
  await seedSpinResult("ac_result_ac", a, c);

  const createFn = createTeamMeetingRequestFunction(db, resolveUser);
  const respondFn = createRespondTeamMeetingRequestFunction(db, resolveUser);

  const createdAb = (await createFn.run(
    callableRequest(a.memberUids[0], {
      sourceResultId: "ac_result_ab",
      viewerGroupId: a.teamId,
    })
  )) as Record<string, unknown>;
  const createdAc = (await createFn.run(
    callableRequest(a.memberUids[1], {
      sourceResultId: "ac_result_ac",
      viewerGroupId: a.teamId,
    })
  )) as Record<string, unknown>;
  const requestAb = String(createdAb.requestId);
  const requestAc = String(createdAc.requestId);
  assert.notEqual(requestAb, requestAc);

  const outcomes = await Promise.allSettled([
    respondFn.run(callableRequest(b.memberUids[0], { requestId: requestAb, accept: true })),
    respondFn.run(callableRequest(c.memberUids[0], { requestId: requestAc, accept: true })),
  ]);

  const fulfilled = outcomes.filter((o) => o.status === "fulfilled");
  const rejected = outcomes.filter((o) => o.status === "rejected");
  assert.equal(fulfilled.length, 1, "정확히 하나의 accept만 성공해야 한다");
  assert.equal(rejected.length, 1, "다른 하나는 deterministic failure여야 한다");
  const rejection = (rejected[0] as PromiseRejectedResult).reason as HttpsError;
  assert.equal(rejection.code, "failed-precondition");

  assert.equal(
    await countMatchesForTeam(a.teamId),
    1,
    "팀 A의 활성 match는 정확히 1개"
  );
});

// -----------------------------------------------------------------------------
// A→B / B→A 양방향 request 동시 accept (legacy: pairLockId 없는 두 번째 요청)
// -----------------------------------------------------------------------------
test("race: bidirectional requests for the same pair yield exactly one match", async () => {
  const { a, b } = uniqueTeams("bi");
  await Promise.all([seedGroup(a), seedGroup(b)]);
  await seedSpinResult("bi_result_1", a, b);

  const createFn = createTeamMeetingRequestFunction(db, resolveUser);
  const respondFn = createRespondTeamMeetingRequestFunction(db, resolveUser);

  const createdAb = (await createFn.run(
    callableRequest(a.memberUids[0], {
      sourceResultId: "bi_result_1",
      viewerGroupId: a.teamId,
    })
  )) as Record<string, unknown>;
  const requestAb = String(createdAb.requestId);

  // pairLockId가 없는 legacy 형태의 역방향 pending request를 직접 seed한다
  // (정상 create 경로는 pair lock으로 이미 dedupe되므로, 우회 시나리오 검증).
  const legacyReverseId = teamMeetingRequestId("bi_result_2", b.teamId, a.teamId);
  await db.collection("eventTeamMeetingRequests").doc(legacyReverseId).set({
    source: "legacy_test",
    sourceResultId: "bi_result_2",
    fromTeamId: b.teamId,
    toTeamId: a.teamId,
    fromTeamMemberUids: b.memberUids,
    toTeamMemberUids: a.memberUids,
    fromTeamSnapshot: teamSnapshot(b),
    toTeamSnapshot: teamSnapshot(a),
    participantUids: [...a.memberUids, ...b.memberUids].sort(),
    createdByUserId: b.memberUids[0],
    status: "pending",
    respondedByUserId: null,
    respondedAt: null,
    matchId: null,
  });

  const outcomes = await Promise.allSettled([
    respondFn.run(callableRequest(b.memberUids[0], { requestId: requestAb, accept: true })),
    respondFn.run(
      callableRequest(a.memberUids[0], { requestId: legacyReverseId, accept: true })
    ),
  ]);

  const fulfilled = outcomes.filter((o) => o.status === "fulfilled");
  assert.equal(fulfilled.length, 1, "같은 pair에 match는 하나만 성사되어야 한다");
  assert.equal(await countMatchesForTeam(a.teamId), 1);
  assert.equal(await countMatchesForTeam(b.teamId), 1);
});

// -----------------------------------------------------------------------------
// accept / decline race: 정확히 하나의 terminal outcome
// -----------------------------------------------------------------------------
test("race: concurrent accept and decline settle into one terminal outcome", async () => {
  const { a, b } = uniqueTeams("ad");
  await Promise.all([seedGroup(a), seedGroup(b)]);
  await seedSpinResult("ad_result", a, b);

  const createFn = createTeamMeetingRequestFunction(db, resolveUser);
  const respondFn = createRespondTeamMeetingRequestFunction(db, resolveUser);
  const created = (await createFn.run(
    callableRequest(a.memberUids[0], {
      sourceResultId: "ad_result",
      viewerGroupId: a.teamId,
    })
  )) as Record<string, unknown>;
  const requestId = String(created.requestId);

  const outcomes = await Promise.allSettled([
    respondFn.run(callableRequest(b.memberUids[0], { requestId, accept: true })),
    respondFn.run(callableRequest(b.memberUids[1], { requestId, accept: false })),
  ]);
  for (const outcome of outcomes) {
    assert.equal(outcome.status, "fulfilled", "레이스의 양쪽 모두 무작위 internal error가 아니어야 한다");
  }

  const requestSnap = await db
    .collection("eventTeamMeetingRequests")
    .doc(requestId)
    .get();
  const terminalStatus = String(requestSnap.data()?.status);
  assert.ok(["accepted", "declined"].includes(terminalStatus));

  const matchCount = await countMatchesForTeam(a.teamId);
  if (terminalStatus === "accepted") {
    assert.equal(matchCount, 1, "accept가 이겼으면 match가 보존되어야 한다");
  } else {
    assert.equal(matchCount, 0, "decline이 이겼으면 match가 없어야 한다");
  }
});

// -----------------------------------------------------------------------------
// 차단 관계 재검증: 요청 생성 시점에 상대 팀에 차단된 사용자가 있으면 거부
// -----------------------------------------------------------------------------
test("blocked pair: request creation fails when any cross-team block exists", async () => {
  const { a, b } = uniqueTeams("bl");
  await Promise.all([seedGroup(a), seedGroup(b)]);
  await seedSpinResult("bl_result", a, b);
  await db
    .collection("blocks")
    .doc(a.memberUids[2])
    .collection("targets")
    .doc(b.memberUids[0])
    .set({ createdAt: new Date().toISOString() });

  const createFn = createTeamMeetingRequestFunction(db, resolveUser);
  await assert.rejects(
    createFn.run(
      callableRequest(a.memberUids[0], {
        sourceResultId: "bl_result",
        viewerGroupId: a.teamId,
      })
    ),
    (error: HttpsError) => error.code === "failed-precondition"
  );
});

// -----------------------------------------------------------------------------
// 차단 관계 재검증: 요청 이후 생긴 차단은 accept 시점에 걸러진다
// -----------------------------------------------------------------------------
test("blocked pair: accept fails when a block was created after the request", async () => {
  const { a, b } = uniqueTeams("b2");
  await Promise.all([seedGroup(a), seedGroup(b)]);
  await seedSpinResult("b2_result", a, b);

  const createFn = createTeamMeetingRequestFunction(db, resolveUser);
  const respondFn = createRespondTeamMeetingRequestFunction(db, resolveUser);
  const created = (await createFn.run(
    callableRequest(a.memberUids[0], {
      sourceResultId: "b2_result",
      viewerGroupId: a.teamId,
    })
  )) as Record<string, unknown>;
  const requestId = String(created.requestId);

  await db
    .collection("blocks")
    .doc(b.memberUids[2])
    .collection("targets")
    .doc(a.memberUids[1])
    .set({ createdAt: new Date().toISOString() });

  await assert.rejects(
    respondFn.run(callableRequest(b.memberUids[0], { requestId, accept: true })),
    (error: HttpsError) => error.code === "failed-precondition"
  );
  assert.equal(await countMatchesForTeam(a.teamId), 0);
});

// -----------------------------------------------------------------------------
// 권위 팀 재검증: 수락 시점에 팀 구성이 바뀌었으면 거부
// -----------------------------------------------------------------------------
test("team drift: accept fails when authoritative team membership changed", async () => {
  const { a, b } = uniqueTeams("td");
  await Promise.all([seedGroup(a), seedGroup(b)]);
  await seedSpinResult("td_result", a, b);

  const createFn = createTeamMeetingRequestFunction(db, resolveUser);
  const respondFn = createRespondTeamMeetingRequestFunction(db, resolveUser);
  const created = (await createFn.run(
    callableRequest(a.memberUids[0], {
      sourceResultId: "td_result",
      viewerGroupId: a.teamId,
    })
  )) as Record<string, unknown>;
  const requestId = String(created.requestId);

  // 팀 A 구성원이 교체됨 (권위 문서만 변경)
  await db.collection("meetingGroups").doc(a.teamId).set(
    { memberUids: [a.memberUids[0], a.memberUids[1], "td_newcomer"] },
    { merge: true }
  );

  await assert.rejects(
    respondFn.run(callableRequest(b.memberUids[0], { requestId, accept: true })),
    (error: HttpsError) => error.code === "failed-precondition"
  );
  assert.equal(await countMatchesForTeam(a.teamId), 0);
});

// -----------------------------------------------------------------------------
// 같은 pair 재요청 방지: 활성 match가 살아 있는 동안 새 spin 결과로도 불가
// -----------------------------------------------------------------------------
test("duplicate pair: new request for an already-matched pair is rejected across dateKeys", async () => {
  const { a, b } = uniqueTeams("dp");
  await Promise.all([seedGroup(a), seedGroup(b)]);
  await seedSpinResult("dp_result_1", a, b);

  const createFn = createTeamMeetingRequestFunction(db, resolveUser);
  const respondFn = createRespondTeamMeetingRequestFunction(db, resolveUser);
  const created = (await createFn.run(
    callableRequest(a.memberUids[0], {
      sourceResultId: "dp_result_1",
      viewerGroupId: a.teamId,
    })
  )) as Record<string, unknown>;
  await respondFn.run(
    callableRequest(b.memberUids[0], {
      requestId: String(created.requestId),
      accept: true,
    })
  );
  assert.equal(await countMatchesForTeam(a.teamId), 1);

  // 다음 날 새 spin 결과 → 같은 pair 재요청 시도
  await seedSpinResult("dp_result_2", a, b);
  await assert.rejects(
    createFn.run(
      callableRequest(a.memberUids[0], {
        sourceResultId: "dp_result_2",
        viewerGroupId: a.teamId,
      })
    ),
    (error: HttpsError) => error.code === "failed-precondition"
  );
  assert.equal(await countMatchesForTeam(a.teamId), 1);
});
