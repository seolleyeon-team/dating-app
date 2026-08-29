import assert from "node:assert/strict";
import test from "node:test";

import { MEETING_ICEBREAKER_CALLABLE_OPTIONS } from "./runtime";

test("meeting icebreaker callable dispatcher enforces App Check", () => {
  assert.equal(MEETING_ICEBREAKER_CALLABLE_OPTIONS.enforceAppCheck, true);
});
