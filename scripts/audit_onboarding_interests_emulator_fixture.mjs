/**
 * Emulator-only fixture runner for audit_onboarding_interests.mjs.
 *
 * This helper intentionally writes synthetic documents so the read-only audit
 * can be exercised against a real Firestore emulator. It refuses to run
 * without FIRESTORE_EMULATOR_HOST and removes only its synthetic documents.
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { auditUsers } from "./audit_onboarding_interests.mjs";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error(
    "This fixture runner requires FIRESTORE_EMULATOR_HOST and never targets production.",
  );
}

const require = createRequire(
  resolve(
    fileURLToPath(new URL("../functions/package.json", import.meta.url)),
  ),
);
const { getApp, getApps, initializeApp } = require("firebase-admin/app");
const { getFirestore } = require("firebase-admin/firestore");

const projectId = "seolleyeon-onboarding-audit-test";
const app = getApps().length
  ? getApp()
  : initializeApp({ projectId });
const db = getFirestore(app);
const fixtureDocuments = [
  {
    id: "audit-fixture-missing",
    data: { onboarding: { keywords: ["calm"] } },
  },
  {
    id: "audit-fixture-empty",
    data: { onboarding: { interests: [], keywords: ["kind"] } },
  },
  {
    id: "audit-fixture-invalid",
    data: {
      initialSetupComplete: true,
      onboarding: { interests: "not-a-list" },
    },
  },
  {
    id: "audit-fixture-good",
    data: {
      initialSetupComplete: true,
      onboarding: { interests: ["movie"], keywords: ["kind"] },
    },
  },
  {
    id: "audit-fixture-unrelated",
    data: { onboarding: { selfIntroduction: "synthetic" } },
  },
  {
    id: "audit-fixture-good-keywords",
    data: { onboarding: { interests: ["walk"], keywords: [] } },
  },
];

const refs = fixtureDocuments.map(({ id }) => db.collection("users").doc(id));
try {
  await Promise.all(
    fixtureDocuments.map(({ id, data }) =>
      db.collection("users").doc(id).set(data),
    ),
  );

  const summary = await auditUsers(db, {
    pageSize: 2,
    pageDelayMs: 0,
    sleep: async () => {},
  });
  assert.equal(summary.complete, true);
  assert.equal(summary.totalUsersScanned, fixtureDocuments.length);
  assert.equal(summary.candidateUsers, 5);
  assert.equal(summary.affectedUsers, 3);
  assert.equal(summary.missingInterests, 1);
  assert.equal(summary.emptyInterests, 1);
  assert.equal(summary.invalidInterests, 1);
  assert.equal(summary.errorCount, 0);
  assert.equal(JSON.stringify(summary).includes("audit-fixture-"), false);

  console.log(
    JSON.stringify(
      {
        emulator: true,
        fixtureDocuments: fixtureDocuments.length,
        ...summary,
      },
      null,
      2,
    ),
  );
} finally {
  await Promise.all(refs.map((ref) => ref.delete()));
}
