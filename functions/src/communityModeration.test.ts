import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import type { Auth } from "firebase-admin/auth";
import { Timestamp, type Firestore } from "firebase-admin/firestore";
import {
  createCommunityModerationCallables,
  createCommunityModerationDeadlineSchedule,
  moderationAlertDeadline,
} from "./communityModeration";

const indexSource = readFileSync(resolve(__dirname, "../src/index.ts"), "utf8");

test("moderation factories expose the six production handler contracts", () => {
  const callables = createCommunityModerationCallables({
    firestore: {} as Firestore,
    auth: {} as Auth,
  });

  assert.deepEqual(Object.keys(callables).sort(), [
    "decideCommunityReport",
    "getCommunityModerationAccess",
    "listCommunityModerationReports",
    "restoreCommunityAccount",
    "setCommunityReportReviewing",
  ]);
  for (const handler of Object.values(callables)) {
    assert.equal(typeof handler, "function");
  }
  assert.equal(typeof createCommunityModerationDeadlineSchedule({} as Firestore), "function");
});

test("index registers each recovered moderation function export", () => {
  for (const name of [
    "getCommunityModerationAccess",
    "listCommunityModerationReports",
    "setCommunityReportReviewing",
    "decideCommunityReport",
    "restoreCommunityAccount",
  ]) {
    assert.match(indexSource, new RegExp(`export const ${name} = communityModeration\\.`));
  }
  assert.match(
    indexSource,
    /export const checkCommunityModerationDeadlines = createCommunityModerationDeadlineSchedule\(db\);/,
  );
});

test("a deadline alert never carries an undefined deadline (legacy reports have none stored)", () => {
  const derivedMs = Date.UTC(2026, 8, 18, 3, 0, 0);
  const derived = moderationAlertDeadline(undefined, derivedMs);
  assert.ok(derived instanceof Timestamp);
  assert.equal(derived.toMillis(), derivedMs);

  const stored = Timestamp.fromMillis(Date.UTC(2026, 8, 20));
  assert.equal(moderationAlertDeadline(stored, derivedMs), stored);
  // A non-timestamp leftover is not trusted either.
  assert.equal(moderationAlertDeadline("2026-09-20", derivedMs).toMillis(), derivedMs);
});
