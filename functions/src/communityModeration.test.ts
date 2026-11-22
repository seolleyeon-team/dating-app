import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import type { Auth } from "firebase-admin/auth";
import { Timestamp, type Firestore } from "firebase-admin/firestore";
import {
  createCommunityModerationCallables,
  MODERATION_DEADLINE_SCHEDULE_OPTIONS,
  createCommunityModerationDeadlineSchedule,
  moderationAlertDeadline,
  moderationAlertId,
  moderationAlertLevel,
} from "./communityModeration";

const indexSource = readFileSync(resolve(__dirname, "../src/index.ts"), "utf8");
const moduleSource = readFileSync(resolve(__dirname, "../src/communityModeration.ts"), "utf8");
const HOUR = 3600_000;

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

test("AUD-14: alert level thresholds (20 h, 23 h, deadline) and their boundaries", () => {
  const created = Date.UTC(2026, 10, 20, 3, 0, 0);
  const deadline = created + 24 * HOUR;
  const level = (offset: number) => moderationAlertLevel(created + offset, created, deadline);
  assert.equal(level(0), "new");
  assert.equal(level(15 * 60_000), "new");
  assert.equal(level(15 * 60_000 + 1), null);
  assert.equal(level(20 * HOUR - 1), null);
  assert.equal(level(20 * HOUR), "20h");
  assert.equal(level(23 * HOUR - 1), "20h");
  assert.equal(level(23 * HOUR), "23h");
  assert.equal(level(24 * HOUR - 1), "23h");
  assert.equal(level(24 * HOUR), "overdue");
  assert.equal(level(240 * HOUR), "overdue");
  // no deadline at all: never due; no createdAt: age follows the 24 h SLA
  assert.equal(moderationAlertLevel(created, null, null), null);
  assert.equal(moderationAlertLevel(deadline - HOUR, null, deadline), "23h");
  assert.equal(moderationAlertLevel(deadline - 5 * HOUR, null, deadline), null);
});

test("AUD-14: alert ids are deterministic: one per level, one overdue reminder per clock hour", () => {
  const t = Date.UTC(2026, 10, 21, 3, 10, 0);
  assert.equal(moderationAlertId("r1", "20h", t), "r1_20h_once");
  assert.equal(moderationAlertId("r1", "23h", t + 99 * HOUR), "r1_23h_once");
  assert.equal(moderationAlertId("r1", "overdue", t), moderationAlertId("r1", "overdue", t + 49 * 60_000));
  assert.notEqual(moderationAlertId("r1", "overdue", t), moderationAlertId("r1", "overdue", t + 50 * 60_000));
  assert.notEqual(moderationAlertId("r1", "overdue", t), moderationAlertId("r2", "overdue", t));
});

test("AUD-14: the schedule keeps its cadence and has an explicit timeout and memory", () => {
  assert.deepEqual(MODERATION_DEADLINE_SCHEDULE_OPTIONS, {
    schedule: "every 15 minutes", timeZone: "Asia/Seoul", timeoutSeconds: 300, memory: "256MiB",
  });
});

test("AUD-14: the sweep only ever creates alerts (nothing that could reset read state)", () => {
  const sweep = moduleSource.slice(
    moduleSource.indexOf("export async function runCommunityModerationDeadlineSweep"),
    moduleSource.indexOf("export function createCommunityModerationDeadlineSchedule"),
  );
  assert.ok(sweep.includes("batch.create(alerts.doc(id)"));
  assert.ok(sweep.includes("alerts.doc(id).create("));
  for (const forbidden of ["batch.set(", ".doc(id).set(", ".update(", "merge: true", "reports.orderBy(\"createdAt\"", ".delete("]) {
    assert.ok(!sweep.includes(forbidden), forbidden);
  }
});

test("NEW-25: every console callable is App Check enforced and passes the operator gate first", () => {
  const callables = moduleSource.slice(
    moduleSource.indexOf("export function createCommunityModerationCallables"),
    moduleSource.indexOf("export type ModerationAlertLevel"),
  );
  assert.equal(callables.split("onCall(").length - 1, 5);
  const handlers = callables.split("onCall(withAppCheck(), async (request) => {").slice(1);
  assert.equal(handlers.length, 5);
  for (const handler of handlers) {
    assert.match(handler.trimStart().split("\n")[0], /await requireOperations\(firestore, request\.auth\);$/);
  }
  // claim + active admin record + account state (accountStatePolicy)
  assert.ok(moduleSource.includes("auth?.token?.operations !== true"));
  assert.ok(moduleSource.includes("admin.data()?.active !== true"));
  assert.ok(moduleSource.includes("throw accountStateError(state);"));
});
