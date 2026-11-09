import assert from "node:assert/strict";
import test from "node:test";

import { FieldPath } from "firebase-admin/firestore";

import { buildResidueRepairUpdate, planParticipantInfoResidueRepair } from "./chatRoomParticipantInfoResidueCli";

test("P1-5 residue: a room with the literal dotted key is detected; clean rooms are not", () => {
  assert.equal(planParticipantInfoResidueRepair({ participantInfo: { a: { nickname: "x" } } }), null);
  assert.equal(planParticipantInfoResidueRepair({}), null);
  const repair = planParticipantInfoResidueRepair({
    participantInfo: { alice: { nickname: "앨리스" }, bob: { nickname: "밥" } },
    "participantInfo.alice": { nickname: "탈퇴한 사용자", avatarUrl: null },
    "participantInfo.carol": { nickname: "탈퇴한 사용자", avatarUrl: null },
    "something.else": 1,
  });
  assert.deepEqual(repair, { literalKeys: ["participantInfo.alice", "participantInfo.carol"], uids: ["alice", "carol"] });
});

test("P1-5 residue: the repair deletes the literal fields and writes nested placeholders through FieldPath", () => {
  const pairs = buildResidueRepairUpdate({ literalKeys: ["participantInfo.alice"], uids: ["alice"] });
  assert.equal(pairs.length, 3);
  assert.ok(pairs[0][0].isEqual(new FieldPath("participantInfo.alice")), "the literal single-segment field");
  assert.ok(pairs[1][0].isEqual(new FieldPath("participantInfo", "alice")), "the nested two-segment path");
  assert.equal((pairs[1][1] as { nickname: string }).nickname, "탈퇴한 사용자");
});
