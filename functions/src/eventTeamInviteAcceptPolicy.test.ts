import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  canAcceptInviteIntoTeam,
  nextAcceptedUserIds,
  simulateConcurrentAcceptOverwrite,
} from "./eventTeamInviteAcceptPolicy";

describe("eventTeamInviteAcceptPolicy", () => {
  it("rejects accept when team already full", () => {
    const result = canAcceptInviteIntoTeam({
      acceptedUserIds: ["leader", "a", "b"],
      inviteeUserId: "c",
    });
    assert.equal(result.ok, false);
    if (!result.ok) assert.equal(result.reason, "team_full");
  });

  it("arrayUnion model keeps both concurrent invitees", () => {
    const sim = simulateConcurrentAcceptOverwrite({
      acceptedUserIds: ["leader"],
      inviteeA: "alice",
      inviteeB: "bob",
    });
    assert.deepEqual(sim.withReplace.sort(), ["bob", "leader"]);
    assert.deepEqual(sim.withArrayUnion.sort(), ["alice", "bob", "leader"]);
  });

  it("nextAcceptedUserIds enforces hard capacity postcondition", () => {
    const ok = nextAcceptedUserIds({
      acceptedUserIds: ["leader", "a"],
      inviteeUserId: "b",
    });
    assert.equal(ok.ok, true);
    if (ok.ok) {
      assert.deepEqual(ok.acceptedUserIds.sort(), ["a", "b", "leader"]);
      assert.equal(ok.memberCount, 3);
    }

    const full = nextAcceptedUserIds({
      acceptedUserIds: ["leader", "a", "b"],
      inviteeUserId: "c",
    });
    assert.equal(full.ok, false);
    if (!full.ok) assert.equal(full.reason, "team_full");
  });

  it("concurrent nextAccepted from same snapshot cannot both fit last seat", () => {
    const base = ["leader", "a"];
    const first = nextAcceptedUserIds({
      acceptedUserIds: base,
      inviteeUserId: "b",
    });
    const second = nextAcceptedUserIds({
      acceptedUserIds: base,
      inviteeUserId: "c",
    });
    assert.equal(first.ok, true);
    assert.equal(second.ok, true);
    // After OCC retry, the loser re-reads the winner's membership:
    const afterFirst = first.ok ? first.acceptedUserIds : base;
    const retry = nextAcceptedUserIds({
      acceptedUserIds: afterFirst,
      inviteeUserId: "c",
    });
    assert.equal(retry.ok, false);
    if (!retry.ok) assert.equal(retry.reason, "team_full");
  });
});
