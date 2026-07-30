import assert from "node:assert/strict";
import test from "node:test";

import * as functionsIndex from "./index";

type EventTeamCandidateSnapshotForTest = {
  groupId: string;
  sourceSetupId: string | null;
  membersSnapshot: Array<{ uid: string }>;
  memberCount: number;
  score: number;
  position: number | null;
  isExplore: boolean;
  matchedPairs: Record<string, unknown>[];
};

function candidate(
  groupId: string,
  memberUids: string[]
): EventTeamCandidateSnapshotForTest {
  return {
    groupId,
    sourceSetupId: `${groupId}-setup`,
    membersSnapshot: memberUids.map((uid) => ({ uid })),
    memberCount: memberUids.length,
    score: 1,
    position: 1,
    isExplore: false,
    matchedPairs: [],
  };
}

test("event team match preview always includes deterministic deduped participantUids", () => {
  const maybeBuildEventTeamMatchResultPreview = (
    functionsIndex as unknown as {
      buildEventTeamMatchResultPreview?: (params: Record<string, unknown>) => Record<string, unknown>;
    }
  ).buildEventTeamMatchResultPreview;

  assert.equal(typeof maybeBuildEventTeamMatchResultPreview, "function");
  const buildEventTeamMatchResultPreview = maybeBuildEventTeamMatchResultPreview as (
    params: Record<string, unknown>
  ) => Record<string, unknown>;

  const requestingTeam = candidate("requesting-team", ["user-c", "user-a", "user-c"]);
  const matchedTeam = candidate("matched-team", ["user-b", "user-a", "user-d"]);
  const result = buildEventTeamMatchResultPreview({
    resultId: "result-1",
    dateKey: "20260720",
    requestingTeamSetupId: "requesting-team",
    requestingTeam,
    matchedTeam,
    candidateTeams: [matchedTeam],
    algorithm: "test-algorithm",
    sourcePath: "meetingDailyRecs/requesting-team/days/20260720",
    selectedGroupIndex: 0,
    createdAtIso: "2026-07-20T00:00:00.000Z",
  });

  assert.deepEqual(result.participantUids, [
    "user-a",
    "user-b",
    "user-c",
    "user-d",
  ]);
});