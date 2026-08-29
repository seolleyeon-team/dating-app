/**
 * 시즌 미팅(eventTeam*) / 블라인드 취향 미팅(blindMeeting*) authoritative
 * 컬렉션의 fail-closed 검증과 chat_rooms create 위조 차단 검증.
 *
 * 이전까지 이 컬렉션들은 functions/src/firestoreRules.test.ts 의
 * 문자열 검사로만 보호되었고, 실제 rules 엔진 평가는 없었다.
 */
import test from "node:test";

import {
  assertFails,
  assertSucceeds,
  getTestEnv,
  kakaoSession,
  withClearedDb,
} from "./helpers.mjs";

import { doc, getDoc, setDoc, updateDoc, deleteDoc } from "firebase/firestore";

const ALICE = "kakao_alice";
const BOB = "kakao_bob";
const MALLORY = "kakao_mallory";

const TEAM_A = "teamA";
const TEAM_B = "teamB";
const PARTICIPANTS = [ALICE, BOB, "a3", "b1", "b2", "b3"];

async function seedSeasonDocs(db) {
  await setDoc(doc(db, "eventTeamMatches", "result1"), {
    groupIds: [TEAM_A, TEAM_B],
    participantUids: PARTICIPANTS,
    status: "created",
  });
  await setDoc(doc(db, "eventTeamMeetingRequests", "req1"), {
    fromTeamId: TEAM_A,
    toTeamId: TEAM_B,
    participantUids: PARTICIPANTS,
    status: "pending",
  });
  await setDoc(doc(db, "eventThreeVsThreeMatches", "match1"), {
    leftTeamId: TEAM_A,
    rightTeamId: TEAM_B,
    participantUids: PARTICIPANTS,
    status: "active",
    seasonPhase: "matched",
  });
  await setDoc(doc(db, "eventTeamMatchLocks", "lock1"), {
    groupId: TEAM_A,
    status: "locked",
  });
  await setDoc(doc(db, "eventTeamMeetingRequestLocks", "pairlock1"), {
    requestId: "req1",
    status: "pending",
  });
}

async function seedBlindDocs(db) {
  await setDoc(doc(db, "blindMeetingApplications", ALICE), {
    userId: ALICE,
    status: "applied",
    serverStatus: "applied",
    open: true,
  });
  await setDoc(doc(db, "blindMeetings", "bm1"), {
    participantIds: PARTICIPANTS,
    status: "chatOpen",
    serverStatus: "chat_open",
  });
  await setDoc(doc(db, "blindMeetingDeposits", "dep1"), {
    userId: ALICE,
    meetingId: "bm1",
    status: "paid",
  });
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

// ---------------------------------------------------------------------------
// eventTeam* — 클라이언트 write 전면 차단, read 는 참가자 한정
// ---------------------------------------------------------------------------

test("season: participants can read match/request docs, outsiders cannot", async () => {
  await withClearedDb(seedSeasonDocs);
  const alice = await kakaoSession(ALICE);
  const mallory = await kakaoSession(MALLORY);

  await assertSucceeds(getDoc(doc(alice, "eventTeamMatches", "result1")));
  await assertSucceeds(getDoc(doc(alice, "eventTeamMeetingRequests", "req1")));
  await assertSucceeds(getDoc(doc(alice, "eventThreeVsThreeMatches", "match1")));

  await assertFails(getDoc(doc(mallory, "eventTeamMatches", "result1")));
  await assertFails(getDoc(doc(mallory, "eventTeamMeetingRequests", "req1")));
  await assertFails(getDoc(doc(mallory, "eventThreeVsThreeMatches", "match1")));
});

test("season: clients cannot forge requests, matches, results, or locks", async () => {
  await withClearedDb(seedSeasonDocs);
  const alice = await kakaoSession(ALICE);

  await assertFails(
    setDoc(doc(alice, "eventTeamMeetingRequests", "forged"), {
      fromTeamId: TEAM_A,
      toTeamId: TEAM_B,
      participantUids: PARTICIPANTS,
      status: "accepted",
    })
  );
  await assertFails(
    updateDoc(doc(alice, "eventTeamMeetingRequests", "req1"), {
      status: "accepted",
    })
  );
  await assertFails(
    setDoc(doc(alice, "eventThreeVsThreeMatches", "forgedMatch"), {
      participantUids: PARTICIPANTS,
      status: "active",
      seasonPhase: "matched",
    })
  );
  await assertFails(
    updateDoc(doc(alice, "eventThreeVsThreeMatches", "match1"), {
      seasonPhase: "chat_open",
    })
  );
  await assertFails(deleteDoc(doc(alice, "eventThreeVsThreeMatches", "match1")));
  await assertFails(
    setDoc(doc(alice, "eventTeamMatches", "forgedResult"), { groupIds: [] })
  );
  await assertFails(getDoc(doc(alice, "eventTeamMatchLocks", "lock1")));
  await assertFails(
    setDoc(doc(alice, "eventTeamMatchLocks", "lock1"), { status: "unlocked" })
  );
  await assertFails(
    setDoc(doc(alice, "eventTeamMeetingRequestLocks", "pairlock1"), {
      status: "accepted",
    })
  );
});

// ---------------------------------------------------------------------------
// blindMeeting* — 클라이언트 write 전면 차단
// ---------------------------------------------------------------------------

test("blind: owner reads own application, others cannot; nobody writes", async () => {
  await withClearedDb(seedBlindDocs);
  const alice = await kakaoSession(ALICE);
  const mallory = await kakaoSession(MALLORY);

  await assertSucceeds(getDoc(doc(alice, "blindMeetingApplications", ALICE)));
  await assertFails(getDoc(doc(mallory, "blindMeetingApplications", ALICE)));

  await assertFails(
    updateDoc(doc(alice, "blindMeetingApplications", ALICE), {
      status: "confirmed",
      meetingId: "bm1",
    })
  );
  await assertFails(
    setDoc(doc(alice, "blindMeetings", "forgedMeeting"), {
      participantIds: PARTICIPANTS,
      serverStatus: "confirmed",
    })
  );
  await assertFails(
    updateDoc(doc(alice, "blindMeetings", "bm1"), { serverStatus: "completed" })
  );
  await assertFails(getDoc(doc(alice, "blindMeetingDeposits", "dep1")));
  await assertFails(
    setDoc(doc(alice, "blindMeetingDeposits", "dep1"), { status: "refunded" })
  );
});

test("blind: participants read meeting doc, outsiders cannot", async () => {
  await withClearedDb(seedBlindDocs);
  const alice = await kakaoSession(ALICE);
  const mallory = await kakaoSession(MALLORY);
  await assertSucceeds(getDoc(doc(alice, "blindMeetings", "bm1")));
  await assertFails(getDoc(doc(mallory, "blindMeetings", "bm1")));
});

// ---------------------------------------------------------------------------
// chat_rooms create — 일반 DM 은 허용, 미팅 방/연결 필드 위조는 차단
// ---------------------------------------------------------------------------

test("chat_rooms: a participant can still create a plain DM room", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);
  await assertSucceeds(
    setDoc(doc(alice, "chat_rooms", "dm_alice_bob"), {
      roomId: "dm_alice_bob",
      participantIds: [ALICE, BOB],
      participantInfo: {},
      lastMessage: "",
    })
  );
});

test("chat_rooms: clients cannot create meeting rooms or attach match linkage", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);

  // 시즌/블라인드 roomType 위조
  await assertFails(
    setDoc(doc(alice, "chat_rooms", "forged_season"), {
      participantIds: [ALICE],
      roomType: "season_meeting_group",
    })
  );
  await assertFails(
    setDoc(doc(alice, "chat_rooms", "forged_blind"), {
      participantIds: [ALICE],
      roomType: "blind_meeting_group",
      writable: true,
    })
  );

  // 분류 우회형 위조: type/direct + match id, 임의 meetingId/matchId/eventType
  await assertFails(
    setDoc(doc(alice, "chat_rooms", "forged_link1"), {
      participantIds: [ALICE, BOB],
      type: "direct",
      threeVsThreeMatchId: "match1",
    })
  );
  await assertFails(
    setDoc(doc(alice, "chat_rooms", "forged_link2"), {
      participantIds: [ALICE, BOB],
      meetingId: "bm1",
    })
  );
  await assertFails(
    setDoc(doc(alice, "chat_rooms", "forged_link3"), {
      participantIds: [ALICE, BOB],
      type: "group",
      matchId: "match1",
    })
  );
  await assertFails(
    setDoc(doc(alice, "chat_rooms", "forged_link4"), {
      participantIds: [ALICE, BOB],
      eventType: "season_meeting",
    })
  );

  // 자기 자신이 참가자에 없는 방
  await assertFails(
    setDoc(doc(alice, "chat_rooms", "not_mine"), {
      participantIds: [BOB, MALLORY],
    })
  );
});
