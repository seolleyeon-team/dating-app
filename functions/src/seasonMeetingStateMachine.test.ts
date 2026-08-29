import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  assertSeasonMeetingTransition,
  canTransitionSeasonMeeting,
  canTransitionTeamMeetingRequest,
} from "./seasonMeetingStateMachine";

describe("seasonMeetingStateMachine", () => {
  it("allows forming → ready → exploring → request → matched", () => {
    assert.equal(canTransitionSeasonMeeting("team_forming", "team_ready"), true);
    assert.equal(canTransitionSeasonMeeting("team_ready", "exploring"), true);
    assert.equal(canTransitionSeasonMeeting("exploring", "request_pending"), true);
    assert.equal(canTransitionSeasonMeeting("request_pending", "matched"), true);
  });

  it("rejects completed → matched and deposit_paid → team_forming", () => {
    assert.equal(canTransitionSeasonMeeting("completed", "matched"), false);
    assert.equal(canTransitionSeasonMeeting("deposit_paid", "team_forming"), false);
    assert.throws(
      () => assertSeasonMeetingTransition("completed", "matched", "server"),
      /illegal_season_transition/
    );
  });

  it("team meeting request is terminal after accept/decline", () => {
    assert.equal(canTransitionTeamMeetingRequest("pending", "accepted"), true);
    assert.equal(canTransitionTeamMeetingRequest("pending", "declined"), true);
    assert.equal(canTransitionTeamMeetingRequest("accepted", "declined"), false);
    assert.equal(canTransitionTeamMeetingRequest("declined", "accepted"), false);
  });

  it("high-risk money path cannot skip deposit", () => {
    assert.equal(canTransitionSeasonMeeting("matched", "chat_open"), false);
    assert.equal(canTransitionSeasonMeeting("matched", "deposit_pending"), true);
  });

  it("allows no-show review from matched (deposit provider disabled path)", () => {
    assert.equal(canTransitionSeasonMeeting("matched", "noshow_review"), true);
    assert.equal(canTransitionSeasonMeeting("matched", "cancelled"), true);
  });

  it("terminal phases reject further transitions", () => {
    assert.equal(canTransitionSeasonMeeting("cancelled", "matched"), false);
    assert.equal(canTransitionSeasonMeeting("cancelled", "noshow_review"), false);
    assert.equal(canTransitionSeasonMeeting("completed", "cancelled"), false);
  });
});
