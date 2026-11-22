/**
 * AUD-01 — the rec-path mutual-match lookup needs a COLLECTION_GROUP index.
 *
 * `functions/src/mutualMatchCreation.ts` runs
 *   collectionGroup("events")
 *     .where("userId", "==", …).where("targetUserId", "==", …)
 *     .where("eventType", "in", […]).limit(1)
 * inside the match transaction. The emulator does not enforce indexes, so the
 * emulator suite cannot see a missing one; production answered this exact
 * query with FAILED_PRECONDITION ("The query requires an index") and named
 * the definition asserted below. This is a static contract: it needs no
 * emulator and fails when the query and firestore.indexes.json drift apart.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const indexes = JSON.parse(readFileSync(resolve(repoRoot, "firestore.indexes.json"), "utf8"));
const source = readFileSync(resolve(repoRoot, "functions/src/mutualMatchCreation.ts"), "utf8");

/** The `collectionGroup("events")` query chain of reverseLikeQuery. */
function recReverseLikeQuery() {
  const start = source.indexOf('.collectionGroup("events")');
  assert.notEqual(start, -1, "reverseLikeQuery no longer queries collectionGroup(\"events\")");
  const end = source.indexOf(";", start);
  return source.slice(start, end);
}

test("AUD-01: the rec-path reverse-like query still filters exactly userId ==, targetUserId ==, eventType in", () => {
  const chain = recReverseLikeQuery();
  const filters = [...chain.matchAll(/\.where\("([A-Za-z]+)",\s*"([^"]+)"/g)].map((m) => `${m[1]} ${m[2]}`);
  assert.deepEqual(filters.sort(), ["eventType in", "targetUserId ==", "userId =="]);
  // An orderBy would need another index definition than the one below.
  assert.equal(/\.orderBy\(/.test(chain), false);
});

test("AUD-01: firestore.indexes.json carries the COLLECTION_GROUP index production asked for", () => {
  const matching = indexes.indexes.filter(
    (index) => index.collectionGroup === "events" && index.queryScope === "COLLECTION_GROUP",
  );
  assert.equal(matching.length, 1, "exactly one collection-group index on events");
  assert.deepEqual(matching[0].fields, [
    { fieldPath: "eventType", order: "ASCENDING" },
    { fieldPath: "targetUserId", order: "ASCENDING" },
    { fieldPath: "userId", order: "ASCENDING" },
  ]);
});

test("AUD-01: every collection-group query field is covered by that index", () => {
  const chain = recReverseLikeQuery();
  const queried = [...chain.matchAll(/\.where\("([A-Za-z]+)"/g)].map((m) => m[1]).sort();
  const index = indexes.indexes.find(
    (entry) => entry.collectionGroup === "events" && entry.queryScope === "COLLECTION_GROUP",
  );
  assert.ok(index);
  assert.deepEqual(index.fields.map((field) => field.fieldPath).sort(), queried);
});

// ---------------------------------------------------------------------------
// AUD-14 / NEW-25 — the moderation deadline sweep and the open-queue read both
// run reports.where("source", "==").where("status", "==") ordered (and, for the
// sweep, range-filtered) by createdAt. Two equalities plus an inequality /
// order on a third field cannot be served by merged single-field indexes.
// The functions fall back to a slower path when the index is missing, so a
// dropped definition would not fail anything except this contract.
// ---------------------------------------------------------------------------
const moderationSource = readFileSync(
  resolve(repoRoot, "functions/src/communityModeration.ts"),
  "utf8",
);

test("AUD-14: the moderation queries still use source ==, status == and createdAt", () => {
  const chains = [...moderationSource.matchAll(
    /reports\.where\("source", "==", source\)\.where\("status", "==", status\)([\s\S]*?)(?:\.get\(\)|;)/g,
  )].map((match) => match[1]);
  assert.ok(chains.length >= 2, "expected the sweep query and the open-queue query");
  for (const chain of chains) {
    assert.match(chain, /\.orderBy\("createdAt", "asc"\)/);
    const otherFilters = [...chain.matchAll(/\.where\("([A-Za-z]+)"/g)].map((m) => m[1]);
    assert.deepEqual(
      otherFilters.filter((field) => field !== "createdAt"),
      [],
      "a filter on another field needs another index definition",
    );
  }
});

test("AUD-14: firestore.indexes.json carries reports(source, status, createdAt)", () => {
  const matching = indexes.indexes.filter(
    (index) => index.collectionGroup === "reports" && index.queryScope === "COLLECTION",
  );
  assert.equal(matching.length, 1, "exactly one composite index on reports");
  assert.deepEqual(matching[0].fields, [
    { fieldPath: "source", order: "ASCENDING" },
    { fieldPath: "status", order: "ASCENDING" },
    { fieldPath: "createdAt", order: "ASCENDING" },
  ]);
});
