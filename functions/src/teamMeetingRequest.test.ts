import assert from "node:assert/strict";
import test from "node:test";

import {
  CREATE_TEAM_MEETING_REQUEST_CALLABLE_OPTIONS,
  RESPOND_TEAM_MEETING_REQUEST_CALLABLE_OPTIONS,
  buildCreateTeamMeetingRequestPlan,
  buildRespondTeamMeetingRequestPlan,
  teamMeetingMatchId,
  teamMeetingRequestId,
} from "./teamMeetingRequest";

function team(groupId: string, uids: string[]) {
  return {
    groupId,
    sourceSetupId: `${groupId}-setup`,
    membersSnapshot: uids.map((uid) => ({ uid, displayName: uid })),
    memberCount: uids.length,
    score: 1,
    position: 1,
    isExplore: false,
    matchedPairs: [],
  };
}

const matchResult = {
  resultId: "result-1",
  requestingGroupId: "team-a",
  matchedGroupId: "team-b",
  groupIds: ["team-a", "team-b"],
  participantUids: ["a1", "a2", "a3", "b1", "b2", "b3"],
  requestingTeamSnapshot: team("team-a", ["a1", "a2", "a3"]),
  matchedTeamSnapshot: team("team-b", ["b1", "b2", "b3"]),
};

test("team meeting request callables enforce App Check", () => {
  assert.equal(CREATE_TEAM_MEETING_REQUEST_CALLABLE_OPTIONS.enforceAppCheck, true);
  assert.equal(RESPOND_TEAM_MEETING_REQUEST_CALLABLE_OPTIONS.enforceAppCheck, true);
});

test("create request plan derives snapshots, members, participants, and deterministic id", () => {
  const plan = buildCreateTeamMeetingRequestPlan({
    sourceResultId: "result-1",
    viewerGroupId: "team-a",
    callerUid: "a2",
    matchResultData: matchResult,
  });

  assert.equal(plan.requestId, teamMeetingRequestId("result-1", "team-a", "team-b"));
  assert.equal(plan.responseStatus, "pending");
  assert.deepEqual(plan.requestData.fromTeamMemberUids, ["a1", "a2", "a3"]);
  assert.deepEqual(plan.requestData.toTeamMemberUids, ["b1", "b2", "b3"]);
  assert.deepEqual(plan.requestData.participantUids, ["a1", "a2", "a3", "b1", "b2", "b3"]);
  assert.equal(plan.requestData.createdByUserId, "a2");
});

test("create request plan rejects callers outside the selected team", () => {
  assert.throws(
    () => buildCreateTeamMeetingRequestPlan({
      sourceResultId: "result-1",
      viewerGroupId: "team-a",
      callerUid: "b1",
      matchResultData: matchResult,
    }),
    (error) => {
      assert.equal((error as { code?: string }).code, "permission-denied");
      assert.match(String((error as Error).message), /요청할 수/);
      return true;
    }
  );
});

test("respond request plan is idempotent after accepted request and creates participant-scoped match", () => {
  const pending = {
    fromTeamId: "team-a",
    toTeamId: "team-b",
    fromTeamMemberUids: ["a1", "a2", "a3"],
    toTeamMemberUids: ["b1", "b2", "b3"],
    fromTeamSnapshot: team("team-a", ["a1", "a2", "a3"]),
    toTeamSnapshot: team("team-b", ["b1", "b2", "b3"]),
    status: "pending",
  };

  const accepted = buildRespondTeamMeetingRequestPlan({
    requestId: "request-1",
    requestData: pending,
    callerUid: "b2",
    accept: true,
  });
  assert.equal(accepted.status, "accepted");
  assert.equal(accepted.matchId, teamMeetingMatchId("request-1"));
  assert.deepEqual(accepted.matchData?.participantUids, [
    "a1",
    "a2",
    "a3",
    "b1",
    "b2",
    "b3",
  ]);

  const replay = buildRespondTeamMeetingRequestPlan({
    requestId: "request-1",
    requestData: { ...pending, status: "accepted", matchId: accepted.matchId },
    callerUid: "b3",
    accept: true,
  });
  assert.deepEqual(replay, { status: "accepted", matchId: accepted.matchId });
});
test("respond request plan rejects nonparticipants before terminal status details", () => {
  const requestData = {
    fromTeamMemberUids: ["a1", "a2", "a3"],
    toTeamMemberUids: ["b1", "b2", "b3"],
    status: "accepted",
    matchId: "match-secret",
  };

  for (const status of ["pending", "accepted", "declined"] as const) {
    assert.throws(
      () => buildRespondTeamMeetingRequestPlan({
        requestId: "request-1",
        requestData: { ...requestData, status },
        callerUid: "outsider",
        accept: true,
      }),
      (error) => {
        assert.equal((error as { code?: string }).code, "permission-denied");
        return true;
      }
    );
  }
});

test("respond request plan requires accept to be boolean", () => {
  for (const accept of [undefined, null, "false", 0] as unknown[]) {
    assert.throws(
      () => buildRespondTeamMeetingRequestPlan({
        requestId: "request-1",
        requestData: {
          fromTeamMemberUids: ["a1", "a2", "a3"],
          toTeamMemberUids: ["b1", "b2", "b3"],
          status: "pending",
        },
        callerUid: "b1",
        accept: accept as boolean,
      }),
      (error) => {
        assert.equal((error as { code?: string }).code, "invalid-argument");
        return true;
      }
    );
  }
});

test("team meeting request plans reject unsafe Firestore path segments", () => {
  for (const sourceResultId of ["../result", "result/1", ".", ""]) {
    assert.throws(
      () => buildCreateTeamMeetingRequestPlan({
        sourceResultId,
        viewerGroupId: "team-a",
        callerUid: "a1",
        matchResultData: matchResult,
      }),
      (error) => {
        assert.equal((error as { code?: string }).code, "invalid-argument");
        return true;
      }
    );
  }

  for (const viewerGroupId of ["../team-a", "team/a", ".", ""]) {
    assert.throws(
      () => buildCreateTeamMeetingRequestPlan({
        sourceResultId: "result-1",
        viewerGroupId,
        callerUid: "a1",
        matchResultData: matchResult,
      }),
      (error) => {
        assert.equal((error as { code?: string }).code, "invalid-argument");
        return true;
      }
    );
  }

  for (const requestId of ["../request", "request/1", ".", ""]) {
    assert.throws(
      () => buildRespondTeamMeetingRequestPlan({
        requestId,
        requestData: {
          fromTeamMemberUids: ["a1", "a2", "a3"],
          toTeamMemberUids: ["b1", "b2", "b3"],
          status: "pending",
        },
        callerUid: "b1",
        accept: false,
      }),
      (error) => {
        assert.equal((error as { code?: string }).code, "invalid-argument");
        return true;
      }
    );
  }
});
