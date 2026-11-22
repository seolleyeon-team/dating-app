/**
 * AUD-11 — ownership documents (adultIdentityOwners) for the verification
 * records written before they existed.
 *
 * Usage (from functions/, after `npm run build`):
 *   node lib/adultIdentityOwnershipBackfillCli.js --project seolleyeon-final --audit     # read-only
 *   node lib/adultIdentityOwnershipBackfillCli.js --project seolleyeon-final --dry-run   # read-only plan
 *   node lib/adultIdentityOwnershipBackfillCli.js --project seolleyeon-final --apply     # separate, reviewed step
 *
 * --audit    counts records, expected / existing / missing ownership documents
 *            and identity keys held by more than one account; exits 1 unless
 *            every record is backed and no identity is shared
 * --dry-run  the apply decisions in read-only transactions
 * --apply    creates the missing ownership documents (`create` semantics, one
 *            transaction per record, idempotent). It never touches a users
 *            document or a verification record and never resolves a shared
 *            identity — those are reported for manual review.
 *
 * The callable does not depend on this backfill: until it has run, the claim
 * transaction also looks the identity up on the records themselves.
 *
 * Output is counts only; no account id or identity hash is printed.
 * Authentication: Application Default Credentials or
 * GOOGLE_APPLICATION_CREDENTIALS; FIRESTORE_EMULATOR_HOST to rehearse.
 */
import { applicationDefault, initializeApp } from "firebase-admin/app";
import { getFirestore } from "firebase-admin/firestore";

import {
  auditAdultIdentityOwnership,
  backfillAdultIdentityOwnership,
} from "./adultIdentityOwnership";

type Mode = "audit" | "dry-run" | "apply";

function fail(message: string): never {
  console.error(message);
  process.exit(2);
}

export function parseArgs(argv: string[]): { project: string; mode: Mode } {
  let project = "";
  let mode: Mode | null = null;
  const setMode = (next: Mode) => {
    if (mode !== null) fail("choose exactly one of --audit, --dry-run, --apply");
    mode = next;
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--project") project = argv[++i] ?? "";
    else if (arg === "--audit") setMode("audit");
    else if (arg === "--dry-run") setMode("dry-run");
    else if (arg === "--apply") setMode("apply");
    else fail(`unknown argument ${arg}`);
  }
  if (!project) fail("--project is required");
  if (mode === null) fail("choose exactly one of --audit, --dry-run, --apply");
  return { project, mode: mode as Mode };
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  initializeApp({
    projectId: args.project,
    credential: process.env.FIRESTORE_EMULATOR_HOST ? undefined : applicationDefault(),
  });
  const db = getFirestore();
  if (args.mode === "audit") {
    const audit = await auditAdultIdentityOwnership(db);
    console.log(JSON.stringify({ mode: "audit", ...audit }, null, 2));
    if (!audit.ok) process.exit(1);
    return;
  }
  const result = await backfillAdultIdentityOwnership(db, { apply: args.mode === "apply" });
  console.log(JSON.stringify({ mode: args.mode, ...result }, null, 2));
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.name : "error");
    process.exit(1);
  });
}
