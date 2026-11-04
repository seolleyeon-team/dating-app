/**
 * P1-3 — one-time backfill of the FCM token ownership registry
 * (pushTokenOwners) from the existing users/{uid}/deviceTokens registrations.
 *
 * Usage (from functions/, after `npm run build`):
 *   node lib/pushTokenOwnershipBackfillCli.js --project seolleyeon-final --dry-run
 *   node lib/pushTokenOwnershipBackfillCli.js --project seolleyeon-final --apply
 *
 * Safety properties (see pushTokenOwnership.ts):
 *   - registrations are read page by page (collection group, by document id)
 *   - one owner per token: the newest registration (updatedAt) wins; a token
 *     registered under several accounts is reported as a conflict and the
 *     losing registrations are deleted — those are exactly the stale
 *     cross-account associations the finding is about
 *   - registry records that already name the planned owner are not rewritten,
 *     so a re-run writes nothing (idempotent)
 *   - --dry-run performs the same reads and no writes
 *   - raw tokens never appear in the output (fingerprints only)
 *
 * Authentication: Application Default Credentials (gcloud auth
 * application-default login) or GOOGLE_APPLICATION_CREDENTIALS. Point
 * FIRESTORE_EMULATOR_HOST at an emulator to rehearse.
 */
import { applicationDefault, initializeApp } from "firebase-admin/app";
import { getFirestore } from "firebase-admin/firestore";

import { runTokenOwnershipBackfill } from "./pushTokenOwnership";

function parseArgs(argv: string[]): { project: string; apply: boolean } {
  let project = "";
  let apply: boolean | null = null;
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--project") project = argv[++i] ?? "";
    else if (arg === "--dry-run") apply = apply === null ? false : fail("choose exactly one of --dry-run, --apply");
    else if (arg === "--apply") apply = apply === null ? true : fail("choose exactly one of --dry-run, --apply");
    else fail(`unknown argument ${arg}`);
  }
  if (!project) fail("--project is required");
  if (apply === null) fail("choose exactly one of --dry-run, --apply");
  return { project, apply: apply as boolean };
}

function fail(message: string): never {
  console.error(message);
  process.exit(2);
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  initializeApp({ projectId: args.project, credential: process.env.FIRESTORE_EMULATOR_HOST ? undefined : applicationDefault() });
  const db = getFirestore();
  const result = await runTokenOwnershipBackfill(db, { apply: args.apply, log: (line) => console.log(line) });
  console.log(JSON.stringify({ mode: args.apply ? "apply" : "dry-run", ...result }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
