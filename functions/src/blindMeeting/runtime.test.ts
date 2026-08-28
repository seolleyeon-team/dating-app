import assert from "node:assert/strict";
import test from "node:test";

import { BLIND_MEETING_CALLABLE_OPTIONS } from "./runtime";

test("blind meeting callable dispatcher enforces App Check", () => {
  // blindMeetingAction covers deposit/cancellation/safety-stamp/follow-up
  // actions; it must not be the one callable that skips App Check.
  assert.equal(BLIND_MEETING_CALLABLE_OPTIONS.enforceAppCheck, true);
});
