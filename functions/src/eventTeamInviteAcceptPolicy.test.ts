import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  canAcceptInviteIntoTeam,
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
});
