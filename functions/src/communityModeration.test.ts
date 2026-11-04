import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import type { Auth } from "firebase-admin/auth";
import type { Firestore } from "firebase-admin/firestore";
import {
  createCommunityModerationCallables,
  createCommunityModerationDeadlineSchedule,
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
