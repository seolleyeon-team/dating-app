import assert from "node:assert/strict";
import test from "node:test";

import {
  auditUsers,
  classifyUserDocument,
  parseArgs,
} from "./audit_onboarding_interests.mjs";

test("classifies missing interests only when keywords or completion make it relevant", () => {
  assert.deepEqual(
    classifyUserDocument({
      onboarding: { keywords: ["calm"] },
    }),
    {
      hasKeywords: true,
      onboardingCompleted: false,
      candidate: true,
      missingInterests: true,
      emptyInterests: false,
      invalidInterests: false,
      affected: true,
    },
  );
  assert.equal(
    classifyUserDocument({ onboarding: { keywords: [] } }).affected,
    true,
  );
  assert.equal(
    classifyUserDocument({ onboarding: { interests: ["movie"] } }).affected,
    false,
  );
});

function pagedDb(data) {
  const documents = data.map((value, index) => ({
    id: `fixture-${index + 1}`,
    data: () => value,
  }));

  return {
    collection: () => ({
      select: () => {
        const query = {
          cursor: null,
          pageSize: 100,
          orderBy() {
            return query;
          },
          limit(size) {
            query.pageSize = size;
            return query;
          },
          startAfter(id) {
            query.cursor = id;
            return query;
          },
          async get() {
            const cursorIndex = query.cursor
              ? documents.findIndex((document) => document.id === query.cursor)
              : -1;
            const start = cursorIndex + 1;
            return {
              docs: documents.slice(start, start + query.pageSize),
            };
          },
        };
        return query;
      },
    }),
  };
}

test("paginates and counts empty, missing, and invalid interest records without ids", async () => {
  const db = pagedDb([
    { onboarding: { keywords: ["calm"] } },
    { onboarding: { interests: [], keywords: ["kind"] } },
    {
      initialSetupComplete: true,
      onboarding: { interests: "movie" },
    },
    {
      initialSetupComplete: true,
      onboarding: { interests: ["movie"] },
    },
  ]);

  const summary = await auditUsers(db, {
    pageSize: 2,
    pageDelayMs: 0,
    sleep: async () => {},
  });

  assert.deepEqual(summary, {
    complete: true,
    totalUsersScanned: 4,
    candidateUsers: 4,
    affectedUsers: 3,
    missingInterests: 1,
    emptyInterests: 1,
    invalidInterests: 1,
    hasKeywords: 2,
    onboardingCompleted: 2,
    pageCount: 3,
    retryCount: 0,
    errorCount: 0,
    errorCategories: {},
  });
  assert.equal(JSON.stringify(summary).includes("fixture-"), false);
});

test("retries transient page reads and reports retry counts", async () => {
  let attempts = 0;
  const db = {
    collection: () => ({
      select: () => {
        const query = {
          orderBy() {
            return query;
          },
          limit() {
            return query;
          },
          async get() {
            attempts += 1;
            if (attempts === 1) throw { code: "unavailable" };
            return { docs: [] };
          },
        };
        return query;
      },
    }),
  };

  const summary = await auditUsers(db, {
    pageDelayMs: 0,
    sleep: async () => {},
  });

  assert.equal(attempts, 2);
  assert.equal(summary.retryCount, 1);
  assert.equal(summary.errorCount, 0);
  assert.equal(summary.complete, true);
});

test("reports sanitized page errors without exposing document data", async () => {
  const db = {
    collection: () => ({
      select: () => {
        const query = {
          orderBy() {
            return query;
          },
          limit() {
            return query;
          },
          async get() {
            throw {
              code: "permission-denied",
              message: "private user-123 payload",
            };
          },
        };
        return query;
      },
    }),
  };

  const summary = await auditUsers(db, {
    pageDelayMs: 0,
    maxRetries: 2,
    sleep: async () => {},
  });

  assert.deepEqual(summary.errorCategories, { "permission-denied": 1 });
  assert.equal(summary.errorCount, 1);
  assert.equal(summary.complete, false);
  assert.equal(JSON.stringify(summary).includes("user-123"), false);
});

test("production reads require explicit project and opt-in flags", () => {
  assert.equal(parseArgs([], {}).projectId, "");
  assert.equal(
    parseArgs(["--project", "seolleyeon-final"], {}).allowProductionRead,
    false,
  );
  assert.deepEqual(
    parseArgs(
      [
        "--project",
        "seolleyeon-final",
        "--credentials",
        "service-account.json",
        "--allow-production-read",
        "--page-size",
        "25",
        "--page-delay-ms",
        "0",
        "--max-retries",
        "4",
      ],
      {},
    ),
    {
      projectId: "seolleyeon-final",
      credentialsPath: "service-account.json",
      allowProductionRead: true,
      pageSize: 25,
      pageDelayMs: 0,
      maxRetries: 4,
      help: false,
    },
  );
});
