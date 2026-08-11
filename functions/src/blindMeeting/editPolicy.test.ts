import assert from "node:assert/strict";
import test from "node:test";

import {
  buildBlindMeetingApplicationEditPatch,
  canEditBlindMeetingApplication,
} from "./editPolicy";

test("only an open applied or waitlisted application without a meeting is editable", () => {
  assert.equal(
    canEditBlindMeetingApplication({
      status: "applied",
      stage: "searchingCandidates",
      open: true,
      meetingId: null,
    }),
    true
  );
  assert.equal(
    canEditBlindMeetingApplication({
      status: "waitlisted",
      stage: "insufficientCandidates",
      open: true,
      meetingId: null,
    }),
    true
  );
  assert.equal(
    canEditBlindMeetingApplication({
      status: "invited",
      stage: "matched",
      open: false,
      meetingId: "m1",
    }),
    false
  );
});

test("closed, cancelled, matched, or assigned applications cannot be edited", () => {
  for (const application of [
    {
      status: "applied" as const,
      stage: "searchingCandidates" as const,
      open: false,
      meetingId: null,
    },
    {
      status: "cancelled" as const,
      stage: "cancelled" as const,
      open: false,
      meetingId: null,
    },
    {
      status: "applied" as const,
      stage: "matched" as const,
      open: true,
      meetingId: null,
    },
    {
      status: "applied" as const,
      stage: "searchingCandidates" as const,
      open: true,
      meetingId: "m1",
    },
  ]) {
    assert.equal(canEditBlindMeetingApplication(application), false);
  }
});

test("unknown matching stages fail closed", () => {
  assert.equal(
    canEditBlindMeetingApplication({
      status: "applied",
      stage: "legacyUnknownStage" as never,
      open: true,
      meetingId: null,
    }),
    false
  );
});

test("editable application patch preserves status and requeues the same application", () => {
  const patch = buildBlindMeetingApplicationEditPatch(
    {
      status: "waitlisted",
      stage: "insufficientCandidates",
      open: true,
      meetingId: null,
    },
    {
      requestedDateKeys: ["2026-08-11"],
      prefersAlcoholFree: true,
      waitlistOptIn: true,
    }
  );

  assert.deepEqual(patch, {
    status: "waitlisted",
    stage: "searchingCandidates",
    open: true,
    meetingId: null,
    requestedDateKeys: ["2026-08-11"],
    prefersAlcoholFree: true,
    waitlistOptIn: true,
  });
});

test("non-editable application has no update patch", () => {
  assert.equal(
    buildBlindMeetingApplicationEditPatch(
      {
        status: "invited",
        stage: "matched",
        open: false,
        meetingId: "m1",
      },
      {
        requestedDateKeys: ["2026-08-11"],
        prefersAlcoholFree: false,
        waitlistOptIn: true,
      }
    ),
    null
  );
});
