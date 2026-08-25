/**
 * spinSeasonMeetingRoulette → createTeamMeetingRequest →
 * respondTeamMeetingRequest 전체 흐름의 Firestore Emulator E2E.
 *
 * 실행 (repo root, Java 필요):
 *   npm --prefix functions run build
 *   firebase emulators:exec --only firestore --project demo-season-e2e \
 *     "node --test functions/lib/seasonRoulette.emulator-test.js"
 *
 * index.ts 전체를 import하여 실제 배포되는 callable 핸들러(.run())를
 * 그대로 실행한다. 클라이언트가 match/room을 seed하는 방식이 아니다.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { getFirestore } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error(
    "FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`."
  );
}

// index.ts가 initializeApp()을 수행하므로 여기서는 import만 한다.
import {
  spinSeasonMeetingRoulette,
  createTeamMeetingRequest,
  respondTeamMeetingRequest,
} from "./index";
import { seasonMeetingChatRoomId, SEASON_MEETING_EVENT_TYPE } from "./seasonMeetingChat";

const db = getFirestore();

function kstCompactDateKey(): string {
  const kstNow = new Date(Date.now() + 9 * 60 * 60 * 1000);
  const year = kstNow.getUTCFullYear();
  const month = String(kstNow.getUTCMonth() + 1).padStart(2, "0");
  const day = String(kstNow.getUTCDate()).padStart(2, "0");
  return `${year}${month}${day}`;
}

function run(
  fn: { run: (req: never) => Promise<unknown> },
  uid: string,
  data: Record<string, unknown>
) {
  return fn.run({ data, auth: { uid }, rawRequest: {} } as never);
}

const TEAM_A = "spinTeamA";
const TEAM_B = "spinTeamB";
const A_UIDS = ["spin_a1", "spin_a2", "spin_a3"];
const B_UIDS = ["spin_b1", "spin_b2", "spin_b3"];

function membersSnapshot(uids: string[]) {
  return uids.map((uid) => ({
    uid,
    displayName: uid,
    isVerified: true,
  }));
}

async function seedSpinWorld(): Promise<void> {
  for (const uid of [...A_UIDS, ...B_UIDS]) {
    await db.collection("users").doc(uid).set({
      name: uid,
      isStudentVerified: true,
      studentEmail: `${uid}@yonsei.ac.kr`,
      onboarding: { campusLifeZones: ["sinchon"] },
    });
  }
  await db.collection("eventTeamSetups").doc(TEAM_A).set({
    leaderUserId: A_UIDS[0],
    acceptedUserIds: A_UIDS,
    status: "ready",
  });
  await db.collection("meetingGroups").doc(TEAM_B).set({
    groupId: TEAM_B,
    memberUids: B_UIDS,
    memberCount: 3,
    membersSnapshot: membersSnapshot(B_UIDS),
    status: "open",
    active: true,
    isEligibleForMeetingRec: true,
    sharedCampusLifeZones: ["sinchon"],
  });
  await db
    .collection("meetingDailyRecs")
    .doc(TEAM_A)
    .collection("days")
    .doc(kstCompactDateKey())
    .set({
      status: "ready",
      candidates: [{ groupId: TEAM_B, scoreTotal: 1.0 }],
    });
}

test("E2E: spin → request → accept ends with one match, room, and phase matched", async () => {
  await seedSpinWorld();

  // 1) 팀 A 멤버가 룰렛을 돌린다 — 서버가 후보 선정·결과·락을 만든다.
  const spin = (await run(spinSeasonMeetingRoulette, A_UIDS[0], {
    teamSetupId: TEAM_A,
  })) as Record<string, unknown>;
  assert.equal(spin.reusedExisting, false);
  const resultId = String(spin.resultId);
  assert.ok(resultId.length > 0);

  const resultSnap = await db.collection("eventTeamMatches").doc(resultId).get();
  assert.equal(resultSnap.exists, true);
  const groupIds = resultSnap.data()?.groupIds as string[];
  assert.deepEqual(new Set(groupIds), new Set([TEAM_A, TEAM_B]));

  const dateKey = kstCompactDateKey();
  const lockA = await db
    .collection("eventTeamMatchLocks")
    .doc(`${dateKey}_${TEAM_A}`)
    .get();
  const lockB = await db
    .collection("eventTeamMatchLocks")
    .doc(`${dateKey}_${TEAM_B}`)
    .get();
  assert.equal(lockA.data()?.resultId, resultId);
  assert.equal(lockB.data()?.resultId, resultId);

  // 2) 같은 날 다시 돌리면 새 match를 만들지 않고 기존 결과를 재사용한다.
  const respin = (await run(spinSeasonMeetingRoulette, A_UIDS[1], {
    teamSetupId: TEAM_A,
  })) as Record<string, unknown>;
  assert.equal(respin.reusedExisting, true);
  assert.equal(respin.resultId, resultId);

  // 3) 요청 생성 → 상대 팀 수락 → match + room.
  const created = (await run(createTeamMeetingRequest, A_UIDS[0], {
    sourceResultId: resultId,
    viewerGroupId: TEAM_A,
  })) as Record<string, unknown>;
  assert.equal(created.status, "pending");

  const responded = (await run(respondTeamMeetingRequest, B_UIDS[0], {
    requestId: String(created.requestId),
    accept: true,
  })) as Record<string, unknown>;
  assert.equal(responded.status, "accepted");
  const matchId = String(responded.matchId);

  const matchSnap = await db
    .collection("eventThreeVsThreeMatches")
    .doc(matchId)
    .get();
  assert.equal(matchSnap.exists, true);
  assert.equal(matchSnap.data()?.seasonPhase, "matched");
  assert.equal(matchSnap.data()?.eventType, SEASON_MEETING_EVENT_TYPE);

  const roomSnap = await db
    .collection("chat_rooms")
    .doc(seasonMeetingChatRoomId(matchId))
    .get();
  assert.equal(roomSnap.exists, true);
  const participantIds = roomSnap.data()?.participantIds as string[];
  assert.deepEqual(
    [...participantIds].sort(),
    [...A_UIDS, ...B_UIDS].sort()
  );
});

test("E2E: spin recovers from a stale lock whose result doc is missing", async () => {
  // 과거 회귀: stale lock 정리 경로에서 tx.delete 후 tx.get을 수행해
  // 트랜잭션 전체가 런타임 오류로 죽었다. 지금은 삭제를 write 단계로
  // 미뤄 복구가 성공해야 한다.
  const teamA = "staleTeamA";
  const teamB = "staleTeamB";
  const aUids = ["stale_a1", "stale_a2", "stale_a3"];
  const bUids = ["stale_b1", "stale_b2", "stale_b3"];
  for (const uid of [...aUids, ...bUids]) {
    await db.collection("users").doc(uid).set({
      name: uid,
      isStudentVerified: true,
      studentEmail: `${uid}@yonsei.ac.kr`,
      onboarding: { campusLifeZones: ["sinchon"] },
    });
  }
  await db.collection("eventTeamSetups").doc(teamA).set({
    leaderUserId: aUids[0],
    acceptedUserIds: aUids,
    status: "ready",
  });
  await db.collection("meetingGroups").doc(teamB).set({
    groupId: teamB,
    memberUids: bUids,
    memberCount: 3,
    membersSnapshot: bUids.map((uid) => ({ uid, displayName: uid })),
    status: "open",
    active: true,
    isEligibleForMeetingRec: true,
    sharedCampusLifeZones: ["sinchon"],
  });
  const dateKey = kstCompactDateKey();
  await db
    .collection("meetingDailyRecs")
    .doc(teamA)
    .collection("days")
    .doc(dateKey)
    .set({
      status: "ready",
      candidates: [{ groupId: teamB, scoreTotal: 1.0 }],
    });

  // 자기 팀과 후보 팀 모두에 result 문서가 사라진 stale lock을 심는다.
  await db.collection("eventTeamMatchLocks").doc(`${dateKey}_${teamA}`).set({
    dateKey,
    groupId: teamA,
    resultId: "missing_result_doc",
    status: "locked",
  });
  await db.collection("eventTeamMatchLocks").doc(`${dateKey}_${teamB}`).set({
    dateKey,
    groupId: teamB,
    resultId: "missing_result_doc",
    status: "locked",
  });

  const spin = (await run(spinSeasonMeetingRoulette, aUids[0], {
    teamSetupId: teamA,
  })) as Record<string, unknown>;
  assert.equal(spin.reusedExisting, false, "stale lock은 재사용이 아니라 복구되어야 한다");
  const resultId = String(spin.resultId);

  const lockA = await db
    .collection("eventTeamMatchLocks")
    .doc(`${dateKey}_${teamA}`)
    .get();
  const lockB = await db
    .collection("eventTeamMatchLocks")
    .doc(`${dateKey}_${teamB}`)
    .get();
  assert.equal(lockA.data()?.resultId, resultId, "stale requester lock이 새 결과로 교체되어야 한다");
  assert.equal(lockB.data()?.resultId, resultId, "stale candidate lock이 새 결과로 교체되어야 한다");
});

// -----------------------------------------------------------------------------
// 생활권 hard eligibility — 다른 생활권 팀은 추천 후보에 오르지 않는다
// -----------------------------------------------------------------------------
test("E2E: a cross-zone team is never offered as a roulette candidate", async () => {
  const teamA = "zoneTeamA";
  const sameZoneTeam = "zoneTeamSame";
  const crossZoneTeam = "zoneTeamCross";
  const aUids = ["zone_a1", "zone_a2", "zone_a3"];
  const sameUids = ["zone_s1", "zone_s2", "zone_s3"];
  const crossUids = ["zone_x1", "zone_x2", "zone_x3"];

  const seedUsers = async (uids: string[], zones: string[]) => {
    for (const uid of uids) {
      await db.collection("users").doc(uid).set({
        name: uid,
        isStudentVerified: true,
        studentEmail: `${uid}@yonsei.ac.kr`,
        onboarding: { campusLifeZones: zones },
      });
    }
  };
  const seedGroup = async (groupId: string, uids: string[], zones: string[]) => {
    await db.collection("meetingGroups").doc(groupId).set({
      groupId,
      memberUids: uids,
      memberCount: 3,
      membersSnapshot: uids.map((uid) => ({
        uid,
        displayName: uid,
        isVerified: true,
        campusLifeZones: zones,
      })),
      status: "open",
      active: true,
      isEligibleForMeetingRec: true,
      sharedCampusLifeZones: zones,
    });
  };

  await seedUsers(aUids, ["sinchon"]);
  await seedUsers(sameUids, ["sinchon"]);
  await seedUsers(crossUids, ["songdo"]);
  await db.collection("eventTeamSetups").doc(teamA).set({
    leaderUserId: aUids[0],
    acceptedUserIds: aUids,
    status: "ready",
  });
  await seedGroup(sameZoneTeam, sameUids, ["sinchon"]);
  await seedGroup(crossZoneTeam, crossUids, ["songdo"]);

  // 추천 문서에는 cross-zone 팀을 더 높은 점수로 먼저 넣는다.
  // stale/낡은 추천이 있어도 serving 단계에서 걸러져야 한다.
  await db
    .collection("meetingDailyRecs")
    .doc(teamA)
    .collection("days")
    .doc(kstCompactDateKey())
    .set({
      status: "ready",
      candidates: [
        { groupId: crossZoneTeam, scoreTotal: 9.9 },
        { groupId: sameZoneTeam, scoreTotal: 0.1 },
      ],
    });

  const spin = (await run(spinSeasonMeetingRoulette, aUids[0], {
    teamSetupId: teamA,
  })) as Record<string, unknown>;

  const result = spin.result as Record<string, unknown>;
  const matched = result.matchedTeamSnapshot as Record<string, unknown>;
  assert.equal(
    String(matched.groupId),
    sameZoneTeam,
    "생활권이 같은 팀만 매칭되어야 한다"
  );

  const candidateIds = (result.candidateGroupIds as string[]).map(String);
  assert.ok(
    candidateIds.includes(sameZoneTeam),
    "같은 생활권 팀은 후보에 남아야 한다"
  );
  assert.ok(
    !candidateIds.includes(crossZoneTeam),
    "다른 생활권 팀은 후보 목록에도 오르면 안 된다"
  );
});

test("E2E: a team without campus life zones cannot spin (fail-closed)", async () => {
  const teamA = "noZoneTeamA";
  const peerTeam = "noZonePeer";
  const aUids = ["nozone_a1", "nozone_a2", "nozone_a3"];
  const peerUids = ["nozone_p1", "nozone_p2", "nozone_p3"];

  for (const uid of aUids) {
    // 생활권 없이 학년/학과만 있는 사용자 — 추천기가 재계산하지 않는다.
    await db.collection("users").doc(uid).set({
      name: uid,
      isStudentVerified: true,
      studentEmail: `${uid}@yonsei.ac.kr`,
      onboarding: { grade: "1학년", department: "첨단융합공학부" },
    });
  }
  for (const uid of peerUids) {
    await db.collection("users").doc(uid).set({
      name: uid,
      isStudentVerified: true,
      studentEmail: `${uid}@yonsei.ac.kr`,
      onboarding: { campusLifeZones: ["songdo"] },
    });
  }
  await db.collection("eventTeamSetups").doc(teamA).set({
    leaderUserId: aUids[0],
    acceptedUserIds: aUids,
    status: "ready",
  });
  await db.collection("meetingGroups").doc(peerTeam).set({
    groupId: peerTeam,
    memberUids: peerUids,
    memberCount: 3,
    membersSnapshot: peerUids.map((uid) => ({ uid, displayName: uid })),
    status: "open",
    active: true,
    isEligibleForMeetingRec: true,
    sharedCampusLifeZones: ["songdo"],
  });
  await db
    .collection("meetingDailyRecs")
    .doc(teamA)
    .collection("days")
    .doc(kstCompactDateKey())
    .set({
      status: "ready",
      candidates: [{ groupId: peerTeam, scoreTotal: 1.0 }],
    });

  await assert.rejects(
    run(spinSeasonMeetingRoulette, aUids[0], { teamSetupId: teamA }),
    (error: { code?: string }) => error.code === "failed-precondition"
  );
});
