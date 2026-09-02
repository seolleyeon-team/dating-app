import assert from "node:assert/strict";
import test from "node:test";

import { buildSupportRoomId } from "./supportOperations";

test("support room ids are deterministic and operator-scoped", () => {
  assert.equal(
    buildSupportRoomId("operations-uid", "member-uid"),
    "support_operations-uid_member-uid",
  );
  assert.equal(
    buildSupportRoomId("operations-uid", "member-uid"),
    buildSupportRoomId("operations-uid", "member-uid"),
  );
  assert.notEqual(
    buildSupportRoomId("operations-a", "member-uid"),
    buildSupportRoomId("operations-b", "member-uid"),
  );
});
