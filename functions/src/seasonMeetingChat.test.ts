import assert from "node:assert/strict";
import test from "node:test";

import {
  assertExistingSeasonMeetingChatRoom,
  buildSeasonMeetingChatPlan,
  resolveSeasonMeetingChatParticipants,
  seasonMeetingChatRoomId,
} from "./seasonMeetingChat";

function team(groupId: string, uids: string[]) {
  return {
    groupId,
    membersSnapshot: uids.map((uid) => ({
      uid,
      displayName: uid,
      photoUrl: `https://example.test/${uid}.png`,
      universityId: `${uid}-university`,
      universityName: `${uid} University`,
    })),
  };
}

function matchData() {
  const left = ["a1", "a2", "a3"];
  const right = ["b1", "b2", "b3"];
  return {
    requestId: "request-1",
    eventType: "season_meeting",
    seasonPhase: "matched",
    leftMemberUids: left,
    rightMemberUids: right,
    participantUids: [...left, ...right],
    leftTeamSnapshot: team("team-a", left),
    rightTeamSnapshot: team("team-b", right),
  };
}

test("season meeting chat plan is deterministic and contains exactly six members", () => {
  const plan = buildSeasonMeetingChatPlan({
    matchId: "match-1",
    matchData: matchData(),
  });

  assert.equal(seasonMeetingChatRoomId("match-1"), "season_match-1");
  assert.equal(plan.roomId, "season_match-1");
  assert.deepEqual(plan.participantIds, ["a1", "a2", "a3", "b1", "b2", "b3"]);
  assert.equal(plan.roomPayload.roomType, "season_meeting_group");
  assert.equal(plan.roomPayload.type, "group");
  assert.equal(plan.roomPayload.eventType, "season_meeting");
  assert.equal(plan.roomPayload.eventThreeVsThreeMatchId, "match-1");
  assert.equal(plan.roomPayload.status, "active");
  assert.equal(plan.roomPayload.writable, true);
  assert.equal(Object.keys(plan.participantInfo).length, 6);
});

test("season meeting chat participant resolution rejects malformed team contracts", () => {
  assert.throws(
    () => resolveSeasonMeetingChatParticipants({
      ...matchData(),
      leftMemberUids: ["a1", "a2"],
    }),
    /season_meeting_team_member_count_invalid/
  );
  assert.throws(
    () => resolveSeasonMeetingChatParticipants({
      ...matchData(),
      rightMemberUids: ["a1", "b2", "b3"],
    }),
    /season_meeting_participants_not_unique/
  );
  assert.throws(
    () => resolveSeasonMeetingChatParticipants({
      ...matchData(),
      participantUids: ["a1", "a2", "a3", "b1", "b2", "other"],
    }),
    /season_meeting_participant_source_mismatch/
  );
  assert.throws(
    () => resolveSeasonMeetingChatParticipants({
      ...matchData(),
      rightTeamSnapshot: team("team-b", ["b1", "b2"]),
    }),
    /season_meeting_participant_profile_missing/
  );
});

test("existing season meeting room must preserve the server contract", () => {
  const plan = buildSeasonMeetingChatPlan({
    matchId: "match-1",
    matchData: matchData(),
  });
  assert.doesNotThrow(() =>
    assertExistingSeasonMeetingChatRoom({
      roomData: plan.roomPayload,
      matchId: "match-1",
      participantIds: plan.participantIds,
    })
  );
  assert.throws(
    () =>
      assertExistingSeasonMeetingChatRoom({
        roomData: { ...plan.roomPayload, eventThreeVsThreeMatchId: "other" },
        matchId: "match-1",
        participantIds: plan.participantIds,
      }),
    /season_meeting_chat_match_link_conflict/
  );
  assert.throws(
    () =>
      assertExistingSeasonMeetingChatRoom({
        roomData: { ...plan.roomPayload, participantIds: ["a1"] },
        matchId: "match-1",
        participantIds: plan.participantIds,
      }),
    /season_meeting_chat_participant_conflict/
  );
  assert.throws(
    () =>
      assertExistingSeasonMeetingChatRoom({
        roomData: { ...plan.roomPayload, writable: false },
        matchId: "match-1",
        participantIds: plan.participantIds,
      }),
    /season_meeting_chat_room_state_conflict/
  );
});
