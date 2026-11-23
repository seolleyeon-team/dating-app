/**
 * AUD-22 — duplicated helpers with one contract each.
 *
 * Four helper families had several private copies: id / path-segment
 * validators, display-image resolution, inactive-account predicates and KST
 * date keys. Where the copies really diverged (account predicates, image
 * fields) they now share one implementation; where they were equivalent the
 * contract is pinned here so that a new copy cannot silently differ.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import test from "node:test";

import {
  classifyAccountState,
  isActiveAccountData,
  isRestrictedAccountData,
} from "./accountStatePolicy";
import { isInactivePushRecipient } from "./pushRecipientPolicy";
import { kstDateKey } from "./profileVisibility";
import { kstDateKeyOf } from "./recommendationRefresh";
import { isSingleDocumentId } from "./shared/docId";
import { KST_OFFSET_MS, kstDateKeyCompact, kstDateKeyDashed } from "./shared/kstDate";

const SRC = resolve(__dirname, "../src");

function productionSources(dir = SRC): Array<{ file: string; text: string }> {
  const out: Array<{ file: string; text: string }> = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "testing") continue;
      out.push(...productionSources(full));
    } else if (
      entry.endsWith(".ts") &&
      !entry.endsWith(".test.ts") &&
      !entry.endsWith(".emulator-test.ts") &&
      !entry.endsWith(".d.ts")
    ) {
      out.push({
        file: relative(SRC, full).replace(/\\/g, "/"),
        text: readFileSync(full, "utf8"),
      });
    }
  }
  return out;
}

const SOURCES = productionSources();

// ---------------------------------------------------------------------------
// 1. KST date keys
// ---------------------------------------------------------------------------

test("KST day key: the day turns at 15:00 UTC, including month, year and leap-day boundaries", () => {
  const cases: Array<[string, string]> = [
    ["2026-11-20T14:59:59.999Z", "2026-11-20"],
    ["2026-11-20T15:00:00.000Z", "2026-11-21"],
    ["2026-11-30T15:00:00.000Z", "2026-12-01"],
    ["2026-12-31T14:59:59.999Z", "2026-12-31"],
    ["2026-12-31T15:00:00.000Z", "2027-01-01"],
    ["2028-02-28T15:00:00.000Z", "2028-02-29"],
    ["2028-02-29T15:00:00.000Z", "2028-03-01"],
    ["2027-02-28T15:00:00.000Z", "2027-03-01"],
  ];
  for (const [instant, expected] of cases) {
    const at = new Date(instant);
    assert.equal(kstDateKeyDashed(at), expected, instant);
    assert.equal(kstDateKeyCompact(at), expected.replace(/-/g, ""), instant);
    // Every delegating copy answers the same.
    assert.equal(kstDateKey(at), expected.replace(/-/g, ""), `profileVisibility ${instant}`);
    assert.equal(kstDateKeyOf(at), expected.replace(/-/g, ""), `recommendationRefresh ${instant}`);
  }
  assert.equal(KST_OFFSET_MS, 9 * 60 * 60 * 1000);
});

test("KST day key does not depend on the process time zone", () => {
  const original = process.env.TZ;
  const instant = new Date("2026-11-20T15:30:00.000Z");
  try {
    for (const zone of ["UTC", "America/Los_Angeles", "Asia/Seoul", "Pacific/Kiritimati"]) {
      process.env.TZ = zone;
      assert.equal(kstDateKeyDashed(instant), "2026-11-21", zone);
    }
  } finally {
    if (original === undefined) delete process.env.TZ;
    else process.env.TZ = original;
  }
});

test("no module re-implements the KST day arithmetic", () => {
  // A day key built from the 9 h offset by hand is a private copy. Other uses
  // of the offset (windows, deadlines) are fine and are not matched here.
  const privateCopy =
    /function\s+\w*(?:[kK]st|KST)\w*(?:Date|Day)Key\w*\s*\([^)]*\)[^{]*\{(?:(?!\n\})[\s\S])*?9\s*\*\s*60\s*\*\s*60\s*\*\s*1000/;
  const offenders = SOURCES.filter(
    ({ file, text }) => file !== "shared/kstDate.ts" && privateCopy.test(text),
  ).map(({ file }) => file);
  assert.deepEqual(offenders, []);

  // No day key from process-local calendar getters next to a KST helper name.
  const localGetter =
    /function\s+\w*(?:[kK]st|KST)\w*(?:Date|Day)Key\w*\s*\([^)]*\)[^{]*\{(?:(?!\n\})[\s\S])*?\.get(?:FullYear|Month|Date)\(\)/;
  assert.deepEqual(
    SOURCES.filter(({ text }) => localGetter.test(text)).map(({ file }) => file),
    [],
  );
});

// ---------------------------------------------------------------------------
// 2. Inactive / restricted account predicates
// ---------------------------------------------------------------------------

/** Account documents exactly as the server writers produce them. */
const WRITTEN_STATES = {
  suspended: {
    status: "suspended",
    loginDisabled: true,
    isActive: false,
    moderationActionType: "indefinite_suspension",
  },
  banned: {
    status: "banned",
    loginDisabled: true,
    isActive: false,
    moderationActionType: "permanent_ban",
  },
  deletionInProgress: {
    status: "deleting",
    isWithdrawn: true,
    loginDisabled: true,
    canRejoin: false,
  },
} as const;

test("restricted = a sanction or a deletion in progress; a review fixture is not restricted", () => {
  for (const [name, data] of Object.entries(WRITTEN_STATES)) {
    assert.equal(isRestrictedAccountData(data), true, name);
    assert.equal(isActiveAccountData(data), false, name);
  }
  assert.equal(isRestrictedAccountData({ status: "active", isActive: true }), false);
  assert.equal(isRestrictedAccountData({}), false);
  assert.equal(isRestrictedAccountData(null), false);

  // Play review fixtures can never sign in but must stay visible as
  // candidates inside the review partition.
  const reviewFixture = { loginDisabled: true, dataPartition: "play_review" };
  assert.equal(classifyAccountState(reviewFixture), "inactive");
  assert.equal(isRestrictedAccountData(reviewFixture), false);
  assert.equal(isActiveAccountData(reviewFixture), false);

  // Legacy spellings other readers still honour.
  assert.equal(isRestrictedAccountData({ accountStatus: "Suspended" }), true);
  assert.equal(isRestrictedAccountData({ isBanned: true }), true);
  assert.equal(isRestrictedAccountData({ isDeleted: true }), true);
});

test("push recipients: every written restricted state is refused (banned and deleting were missed)", () => {
  for (const [name, data] of Object.entries(WRITTEN_STATES)) {
    assert.equal(isInactivePushRecipient({ ...data }), true, name);
  }
  assert.equal(isInactivePushRecipient({ status: "active" }), false);
});

test("every visibility predicate includes the shared restricted-account check", () => {
  const required: Record<string, RegExp> = {
    "chatRealPhoto.ts": /function isInactiveUser\([\s\S]*?isRestrictedAccountData\(userData\)/,
    "pushRecipientPolicy.ts": /function isInactivePushRecipient\([\s\S]*?isRestrictedAccountData\(userDoc\)/,
    "recommendationRefresh.ts": /function isAccountActive\([\s\S]*?isRestrictedAccountData\(profile\)/,
    "supportOperations.ts": /function userIsInactive\([\s\S]*?isRestrictedAccountData\(data\)/,
    "publicProfileSync.ts": /const isInactive =[\s\S]*?isRestrictedAccountData\(userData\)/,
  };
  for (const [file, marker] of Object.entries(required)) {
    const source = SOURCES.find((entry) => entry.file === file);
    assert.ok(source, `${file} is missing`);
    assert.match(source.text, marker, `${file} lost the shared restricted-account check`);
  }
  // A candidate-side predicate must not start excluding on loginDisabled:
  // that is what keeps review fixtures visible.
  const recommendation = SOURCES.find((entry) => entry.file === "recommendationRefresh.ts");
  const body = /function isAccountActive\([\s\S]*?\n\}/.exec(recommendation?.text ?? "")?.[0] ?? "";
  assert.ok(body.length > 0);
  assert.equal(/\bprofile\.loginDisabled\b/.test(body), false);
});

// ---------------------------------------------------------------------------
// 3. Display image fields
// ---------------------------------------------------------------------------

test("no server path reads the onboarding image fields a client could write", () => {
  // B-07: onboarding.profileImageUrl / onboarding.representativeImageUrl were
  // client-writable and no server code ever wrote them. publicProfileSync is
  // the one reader left: it projects the value only when it equals an image
  // the server itself stored for that user.
  const field = /onboarding\s*(?:\??\.\s*|\[\s*["'])(?:profileImageUrl|representativeImageUrl)\b/;
  const readers = SOURCES.filter(({ text }) =>
    text
      .split("\n")
      .some((line) => field.test(line) && !/^\s*(?:\/\/|\*)/.test(line)),
  ).map(({ file }) => file);
  assert.deepEqual(readers, ["publicProfileSync.ts"]);
});

// ---------------------------------------------------------------------------
// 4. Id and path-segment validators
// ---------------------------------------------------------------------------

test("a single document id never carries a path", () => {
  for (const good of ["abc", "A_b-1", "kakao:123", "한글"]) {
    assert.equal(isSingleDocumentId(good), true, good);
  }
  for (const bad of ["", "a/b", "/", ".", "..", "users/A/notifications/n1", 1, null, undefined]) {
    assert.equal(isSingleDocumentId(bad), false, String(bad));
  }
});

test("every id allow-list is anchored at both ends and admits no separator, dot or Unicode", () => {
  // All validator copies share one character class; the only thing that may
  // differ is the length bound. An unanchored or wider class is the defect
  // this test exists for (a `/` would turn an id into a nested path).
  const idClass = /\/(\^?)((?:\[[^\]\n]*\]|\\\/|[^\/\n])*?\[A-Za-z0-9_-\](?:\[[^\]\n]*\]|\\\/|[^\/\n])*?)(\$?)\/[a-z]*/g;
  const unanchored: string[] = [];
  const widened: string[] = [];
  let seen = 0;
  for (const { file, text } of SOURCES) {
    for (const line of text.split("\n")) {
      if (/^\s*(?:\/\/|\*)/.test(line)) continue;
      for (const match of line.matchAll(idClass)) {
        seen += 1;
        const [literal, start, body, end] = match;
        if (start !== "^" || end !== "$") unanchored.push(`${file}: ${literal}`);
        // `.` outside a class, or `\S` / `\w` / `.+`, would admit more than the class.
        const outsideClasses = body.replace(/\[[^\]]*\]/g, "");
        if (/(?<!\\)\.|\\[SWDw]/.test(outsideClasses)) widened.push(`${file}: ${literal}`);
      }
    }
  }
  assert.ok(seen >= 30, `expected to find the validator literals, saw ${seen}`);
  assert.deepEqual(unanchored, []);
  assert.deepEqual(widened, []);
});
