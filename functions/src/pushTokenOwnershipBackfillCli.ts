/**
 * P1-3 — one-time backfill of the FCM token ownership registry
 * (pushTokenOwners) from the existing users/{uid}/deviceTokens registrations.
 *
 * Usage (from functions/, after `npm run build`):
 *   node lib/pushTokenOwnershipBackfillCli.js --project seolleyeon-final --dry-run
 *   node lib/pushTokenOwnershipBackfillCli.js --project seolleyeon-final --apply --max-tokens 1   # canary
 *   node lib/pushTokenOwnershipBackfillCli.js --project seolleyeon-final --apply
 *   node lib/pushTokenOwnershipBackfillCli.js --project seolleyeon-final --verify
 *
 * Safety properties (see pushTokenOwnership.ts):
 *   - registrations are read page by page (collection group, by document id)
 *   - each token is reconciled in its own transaction against the CURRENT
 *     registrations and registry record, so it is safe while the
 *     onDeviceTokenWritten trigger is live: a record the trigger wrote is
 *     never overwritten, a missing one is created with `create` semantics
 *   - one owner per token: without a record the newest registration
 *     (updatedAt) wins and the other accounts' registrations are deleted —
 *     exactly the stale cross-account associations the finding is about
 *   - --dry-run runs the same decisions in read-only transactions
 *   - --max-tokens N bounds a run (canary); the rest is reported as deferred
 *   - --verify is read-only and exits 1 unless the registry is consistent
 *   - a re-run writes nothing (idempotent)
 *   - raw tokens and account ids never appear in the output (fingerprints only)
 *
 * Authentication: Application Default Credentials (gcloud auth
 * application-default login) or GOOGLE_APPLICATION_CREDENTIALS. Point
 * FIRESTORE_EMULATOR_HOST at an emulator to rehearse.
 */
import { applicationDefault, initializeApp } from "firebase-admin/app";
import { getFirestore } from "firebase-admin/firestore";

import { runTokenOwnershipBackfill, verifyTokenOwnershipRegistry } from "./pushTokenOwnership";

type Mode = "dry-run" | "apply" | "verify";

export function parseArgs(argv: string[]): { project: string; mode: Mode; maxTokens?: number } {
  let project = "";
  let mode: Mode | null = null;
  let maxTokens: number | undefined;
  const setMode = (next: Mode) => {
    if (mode !== null) fail("choose exactly one of --dry-run, --apply, --verify");
    mode = next;
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--project") project = argv[++i] ?? "";
    else if (arg === "--dry-run") setMode("dry-run");
    else if (arg === "--apply") setMode("apply");
    else if (arg === "--verify") setMode("verify");
    else if (arg === "--max-tokens") {
      const raw = argv[++i] ?? "";
      if (!/^[1-9][0-9]{0,5}$/.test(raw)) fail("--max-tokens needs a positive integer");
      maxTokens = Number(raw);
    } else fail(`unknown argument ${arg}`);
  }
  if (!project) fail("--project is required");
  if (mode === null) fail("choose exactly one of --dry-run, --apply, --verify");
  if (mode === "verify" && maxTokens !== undefined) fail("--max-tokens does not apply to --verify");
  return { project, mode: mode as Mode, maxTokens };
}

function fail(message: string): never {
  console.error(message);
  process.exit(2);
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  initializeApp({ projectId: args.project, credential: process.env.FIRESTORE_EMULATOR_HOST ? undefined : applicationDefault() });
  const db = getFirestore();
  if (args.mode === "verify") {
    const verification = await verifyTokenOwnershipRegistry(db);
    console.log(JSON.stringify({ mode: "verify", ...verification }, null, 2));
    if (!verification.ok) process.exit(1);
    return;
  }
  const result = await runTokenOwnershipBackfill(db, {
    apply: args.mode === "apply",
    maxTokens: args.maxTokens,
    log: (line) => console.log(line),
  });
  console.log(JSON.stringify({ mode: args.mode, maxTokens: args.maxTokens ?? null, ...result }, null, 2));
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
