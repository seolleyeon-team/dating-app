/**
 * 3:3 블라인드 취향 미팅 — 성비 불변식 E2E (Firestore Emulator).
 *
 * 실행 (repo root, Java 필요):
 *   npm --prefix functions run build
 *   firebase emulators:exec --only firestore --project demo-blind-gender \
 *     "node --test functions/lib/blindMeeting/genderBalance.emulator-test.js"
 *
 * 추천 알고리즘 단위 테스트만으로는 부족하다. 실제 서버 진입점
 * (runMatchingForDate) 을 돌려서 Firestore 에 **저장된** 미팅이
 * 3남 + 3녀 6인인지, 성비를 만족할 수 없을 때는 미팅·참가자 문서가
 * 하나도 생기지 않는지(부분 상태 없음)를 확인한다.
 */
import assert from "node:assert/strict";
import { test, before, beforeEach } from "node:test";

import { initializeApp } from "firebase-admin/app";
import { getFirestore, type Firestore } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error(
    "FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`."
  );
}

initializeApp({ projectId: "demo-blind-gender" });

import { runMatchingForDate } from "./orchestrator";
import { readBlindMeetingGender } from "./genderBalance";

let db: Firestore;
before(() => {
  db = getFirestore();
});

/** 신청 가능 창 안의 날짜를 매 실행마다 새로 만든다. */
function dateKeyInWindow(offsetDays: number): string {
  const base = new Date(Date.now() + offsetDays * 24 * 3600 * 1000);
  const yyyy = base.getUTCFullYear();
  const mm = String(base.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(base.getUTCDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

let runSeq = 0;

type Seed = { userId: string; gender: "male" | "female" };

/** 후보 한 명 분의 users / DNA / 신청 문서를 심는다. */
async function seedApplicant(seed: Seed, dateKey: string): Promise<void> {
  await db
    .collection("users")
    .doc(seed.userId)
    .set({
      isStudentVerified: true,
      isWithdrawn: false,
      loginDisabled: false,
      nickname: seed.userId,
      onboarding: {
        gender: seed.gender,
        campusLifeZones: ["sinchon"],
        lifestyle: { drinking: "sometimes", smoking: "nonSmoker" },
      },
    });

  await db
    .collection("blindMeetingDna")
    .doc(seed.userId)
    .set({
      userId: seed.userId,
      conversationAtmosphere: "calm",
      conversationInitiative: "adaptive",
      meetingPurpose: "both",
      alcoholCompanionPreference: "noPreference",
      smokingCompanionPreference: "noPreference",
      drinkingLevelSnapshot: "sometimes",
      smokingStatusSnapshot: "nonSmoker",
      interestIds: ["커피", "영화"],
      mbtiSnapshot: "ENFP",
      availableDateKeys: [dateKey],
    });

  await db
    .collection("blindMeetingApplications")
    .doc(seed.userId)
    .set({
      userId: seed.userId,
      open: true,
      status: "신청 완료",
      serverStatus: "applied",
      stage: "searchingCandidates",
      requestedDateKeys: [dateKey],
      meetingId: null,
      appliedAt: new Date(),
    });
}

async function seedPool(
  males: number,
  females: number,
  dateKey: string,
  tag: string
): Promise<Seed[]> {
  const seeds: Seed[] = [
    ...Array.from({ length: males }, (_, i) => ({
      userId: `${tag}_m${i + 1}`,
      gender: "male" as const,
    })),
    ...Array.from({ length: females }, (_, i) => ({
      userId: `${tag}_f${i + 1}`,
      gender: "female" as const,
    })),
  ];
  for (const seed of seeds) await seedApplicant(seed, dateKey);
  return seeds;
}

/** 저장된 미팅의 실제 성비를 authoritative users 문서로 다시 센다. */
async function persistedGenderCounts(
  participantIds: string[]
): Promise<{ male: number; female: number; unknown: number }> {
  const counts = { male: 0, female: 0, unknown: 0 };
  for (const userId of participantIds) {
    const snap = await db.collection("users").doc(userId).get();
    const gender = readBlindMeetingGender(snap.data());
    if (gender == null) counts.unknown++;
    else counts[gender]++;
  }
  return counts;
}

async function clearCollection(name: string): Promise<void> {
  const snap = await db.collection(name).get();
  await Promise.all(snap.docs.map((doc) => doc.ref.delete()));
}

beforeEach(async () => {
  await clearCollection("blindMeetingApplications");
  await clearCollection("blindMeetingDna");
});

test("3남 3녀 신청자는 3남 + 3녀 미팅으로 저장된다", async () => {
  runSeq += 1;
  const dateKey = dateKeyInWindow(3);
  const tag = `bal${runSeq}`;
  const seeds = await seedPool(3, 3, dateKey, tag);

  const created = await runMatchingForDate(dateKey);
  assert.equal(created.length, 1, "미팅 하나가 만들어져야 한다");

  const meetingSnap = await db
    .collection("blindMeetings")
    .doc(created[0])
    .get();
  assert.ok(meetingSnap.exists);
  const meeting = meetingSnap.data() ?? {};

  const participantIds = meeting.participantIds as string[];
  assert.equal(participantIds.length, 6, "참가자는 정확히 6명");
  assert.equal(new Set(participantIds).size, 6, "UID 6개 유일");

  const counts = await persistedGenderCounts(participantIds);
  assert.deepEqual(
    counts,
    { male: 3, female: 3, unknown: 0 },
    "저장된 미팅이 3남 + 3녀여야 한다"
  );

  // 두 팀은 각각 단일 성별이고 서로 다르다.
  const teamA = meeting.teamAUserIds as string[];
  const teamB = meeting.teamBUserIds as string[];
  assert.equal(teamA.length, 3);
  assert.equal(teamB.length, 3);
  const teamACounts = await persistedGenderCounts(teamA);
  const teamBCounts = await persistedGenderCounts(teamB);
  assert.ok(
    (teamACounts.male === 3 && teamBCounts.female === 3) ||
      (teamACounts.female === 3 && teamBCounts.male === 3),
    "한 팀은 남성 3명, 다른 팀은 여성 3명"
  );

  // 참가자 문서와 공개 프로필이 같은 transaction 으로 6개씩 만들어진다.
  const participantDocs = await db
    .collection("blindMeetings")
    .doc(created[0])
    .collection("participants")
    .get();
  assert.equal(participantDocs.size, 6, "참가자 문서 6개");
  const profileDocs = await db
    .collection("blindMeetings")
    .doc(created[0])
    .collection("publicProfiles")
    .get();
  assert.equal(profileDocs.size, 6, "공개 프로필 6개 (부분 상태 없음)");

  // 여섯 명 전원의 신청서가 이 미팅으로 확보된다.
  for (const seed of seeds) {
    const application = (
      await db.collection("blindMeetingApplications").doc(seed.userId).get()
    ).data();
    assert.equal(application?.meetingId, created[0]);
    assert.equal(application?.open, false);
    assert.equal(application?.stage, "matched");
  }
});

test("남5 여1 이면 어떤 미팅도 만들지 않는다 (부분 상태 없음)", async () => {
  runSeq += 1;
  const dateKey = dateKeyInWindow(4);
  const tag = `short${runSeq}`;
  const seeds = await seedPool(5, 1, dateKey, tag);

  const created = await runMatchingForDate(dateKey);
  assert.deepEqual(created, [], "점수가 높아도 6인을 만들지 않는다");

  const meetings = await db.collection("blindMeetings").get();
  const mine = meetings.docs.filter((doc) =>
    ((doc.data().participantIds as string[]) ?? []).some((id) =>
      id.startsWith(tag)
    )
  );
  assert.equal(mine.length, 0, "미팅 문서가 생기면 안 된다");

  // 신청은 그대로 열려 있어야 한다 (잠기지 않는다).
  for (const seed of seeds) {
    const application = (
      await db.collection("blindMeetingApplications").doc(seed.userId).get()
    ).data();
    assert.equal(application?.open, true);
    assert.ok(
      application?.meetingId == null || application?.meetingId === "",
      "미팅에 묶이면 안 된다"
    );
  }

  // 상대 성별이 3명을 못 채우는 쪽은 조건 완화를 제안받아야 한다.
  const maleApplication = (
    await db.collection("blindMeetingApplications").doc(`${tag}_m1`).get()
  ).data();
  assert.equal(maleApplication?.stage, "insufficientCandidates");
});

test("남6 여0 이면 6남 팀을 만들지 않는다", async () => {
  runSeq += 1;
  const dateKey = dateKeyInWindow(5);
  const tag = `allm${runSeq}`;
  await seedPool(6, 0, dateKey, tag);

  const created = await runMatchingForDate(dateKey);
  assert.deepEqual(created, []);
});

test("남5 여5 여도 정확히 3남 + 3녀만 저장된다", async () => {
  runSeq += 1;
  const dateKey = dateKeyInWindow(6);
  const tag = `big${runSeq}`;
  await seedPool(5, 5, dateKey, tag);

  const created = await runMatchingForDate(dateKey);
  assert.equal(created.length, 1);

  const meeting = (
    await db.collection("blindMeetings").doc(created[0]).get()
  ).data();
  const participantIds = meeting?.participantIds as string[];
  assert.equal(participantIds.length, 6);
  assert.deepEqual(await persistedGenderCounts(participantIds), {
    male: 3,
    female: 3,
    unknown: 0,
  });
});

test("성별이 canonical 이 아닌 신청자는 어느 팀에도 배정되지 않는다", async () => {
  runSeq += 1;
  const dateKey = dateKeyInWindow(7);
  const tag = `unk${runSeq}`;
  await seedPool(3, 2, dateKey, tag);

  // 여섯 번째 신청자는 성별이 'other' 라 canonical 이 아니다.
  const oddUserId = `${tag}_x1`;
  await seedApplicant({ userId: oddUserId, gender: "female" }, dateKey);
  await db
    .collection("users")
    .doc(oddUserId)
    .set({ onboarding: { gender: "other" } }, { merge: true });

  const created = await runMatchingForDate(dateKey);
  assert.deepEqual(
    created,
    [],
    "성별 불명 사용자를 여성 자리에 끼워 넣어 6인을 만들면 안 된다"
  );
});

test("같은 사용자가 두 미팅에 동시에 들어가지 않는다", async () => {
  runSeq += 1;
  const dateKey = dateKeyInWindow(8);
  const tag = `conc${runSeq}`;
  await seedPool(6, 6, dateKey, tag);

  // 같은 pool 을 두 worker 가 동시에 평가한다.
  const [first, second] = await Promise.all([
    runMatchingForDate(dateKey),
    runMatchingForDate(dateKey),
  ]);

  const meetingIds = [...first, ...second];
  const seen = new Set<string>();
  for (const meetingId of meetingIds) {
    const meeting = (
      await db.collection("blindMeetings").doc(meetingId).get()
    ).data();
    const participantIds = (meeting?.participantIds as string[]) ?? [];
    assert.equal(participantIds.length, 6);
    assert.deepEqual(await persistedGenderCounts(participantIds), {
      male: 3,
      female: 3,
      unknown: 0,
    });
    for (const userId of participantIds) {
      assert.equal(
        seen.has(userId),
        false,
        `${userId} 가 두 미팅에 들어갔다`
      );
      seen.add(userId);
    }
  }
});
