/**
 * 블라인드 취향 미팅 매칭 골든 벡터 생성기
 * 실행: node tools/generate_matching_vectors.js
 *
 * functions/lib (tsc 산출물)의 서버 구현으로 기대값을 계산해서
 * shared/blind_meeting_matching_vectors.json 의 expected 를 채운다.
 * Dart 기준 구현과 TS 서버 구현이 같은 값을 내는지 양쪽 테스트에서 검증한다.
 */

const fs = require("fs");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..");
const matching = require(
  path.join(repoRoot, "functions", "lib", "blindMeeting", "matching.js")
);
const config = require(
  path.join(repoRoot, "functions", "lib", "blindMeeting", "matchingConfig.js")
);

const fixturePath = path.join(
  repoRoot,
  "shared",
  "blind_meeting_matching_vectors.json"
);
const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));

function hydrate(raw, slotId) {
  return {
    ...raw,
    availableSlotIds: [slotId],
    schoolVerified: true,
    eligible: true,
    blockedUserIds: [],
    recentlyMetUserIds: [],
    waitedMinutes: 0,
    mbti: raw.mbti ?? null,
  };
}

function round(value) {
  return Number(value.toFixed(10));
}

const expected = {};
for (const testCase of fixture.cases) {
  const teamA = testCase.teamA.map((c) => hydrate(c, fixture.slotId));
  const teamB = testCase.teamB.map((c) => hydrate(c, fixture.slotId));

  const internalA = matching.internalTeamScore(
    teamA,
    config.CURRENT_MATCHING_CONFIG,
    testCase.alcoholFree
  );
  const internalB = matching.internalTeamScore(
    teamB,
    config.CURRENT_MATCHING_CONFIG,
    testCase.alcoholFree
  );
  const group = matching.groupScore(
    teamA,
    teamB,
    config.CURRENT_MATCHING_CONFIG,
    testCase.alcoholFree
  );

  const participantOpponentScores = {};
  for (const [key, value] of Object.entries(group.participantOpponentScores)) {
    participantOpponentScores[key] = round(value);
  }

  expected[testCase.name] = {
    internalTeamA: round(internalA.total),
    internalTeamB: round(internalB.total),
    crossTeamScore: round(group.crossTeamScore),
    minimumParticipantScore: round(group.minimumParticipantScore),
    finalGroupScore: round(group.finalGroupScore),
    participantOpponentScores,
  };
}

fixture.expected = expected;
fs.writeFileSync(fixturePath, `${JSON.stringify(fixture, null, 2)}\n`, "utf8");
console.log(`wrote ${Object.keys(expected).length} expected vectors`);
