/**
 * P0-2 — one-time backfill of room-level unread counts for legacy rooms.
 *
 * Usage (from functions/, after `npm run build`):
 *   node lib/chatUnreadBackfillCli.js --project seolleyeon-final --dry-run
 *   node lib/chatUnreadBackfillCli.js --project seolleyeon-final --apply \
 *        --limit 200 --checkpoint p02-backfill-20261014
 *   node lib/chatUnreadBackfillCli.js --project seolleyeon-final --verify
 *   node lib/chatUnreadBackfillCli.js --project seolleyeon-final --repair \
 *        --checkpoint p02-repair-20261022 [--grace-seconds 300]
 *
 * Safety properties (see chatUnread.ts):
 *   - rooms are paged by document id, never loaded all at once
 *   - every room is idempotent (unreadBackfilledAt) and resumable (unmarked
 *     messages only); the run is resumable through the checkpoint document
 *   - at most 400 messages per transaction (500-op limit headroom)
 *   - --dry-run performs the same reads and no writes
 *   - --verify is read-only: structural checks on every room document plus
 *     the strict invariant (counter == messages newer than the user's
 *     lastReadAt; legacy readBy rule for users who never marked read on a
 *     new client). Messages younger than --grace-seconds may still be in the
 *     trigger queue and are never reported as lost.
 *   - --repair verifies the same way and fixes each room in ONE transaction
 *     that re-checks the room first (see reconcileRoomUnread); rooms that
 *     moved are skipped and reported, never half-written
 *
 * Authentication: Application Default Credentials (gcloud auth
 * application-default login) or GOOGLE_APPLICATION_CREDENTIALS. Point
 * FIRESTORE_EMULATOR_HOST at an emulator to rehearse.
 */
import { applicationDefault, initializeApp } from "firebase-admin/app";
import { FieldPath, FieldValue, getFirestore } from "firebase-admin/firestore";

import {
  checkRoomUnreadIntegrity,
  reconcileRoomUnread,
  runChatUnreadBackfill,
  RECONCILE_DEFAULT_GRACE_MS,
  type RoomIntegrityIssue,
  type RoomReconcileResult,
} from "./chatUnread";

type Args = {
  project: string;
  mode: "dry-run" | "apply" | "verify" | "repair";
  limit?: number;
  checkpoint?: string;
  startAfter?: string;
  graceMs: number;
};

const MODE_ERROR = "choose exactly one of --dry-run, --apply, --verify, --repair";

export function parseArgs(argv: string[]): Args {
  let project = "";
  let mode: Args["mode"] | null = null;
  let limit: number | undefined;
  let checkpoint: string | undefined;
  let startAfter: string | undefined;
  let graceMs = RECONCILE_DEFAULT_GRACE_MS;
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = () => {
      const value = argv[i + 1];
      if (value === undefined || value.startsWith("--")) {
        throw new Error(`${arg} requires a value`);
      }
      i += 1;
      return value;
    };
    switch (arg) {
      case "--project":
        project = next();
        break;
      case "--dry-run":
        if (mode) throw new Error(MODE_ERROR);
        mode = "dry-run";
        break;
      case "--apply":
        if (mode) throw new Error(MODE_ERROR);
        mode = "apply";
        break;
      case "--verify":
        if (mode) throw new Error(MODE_ERROR);
        mode = "verify";
        break;
      case "--repair":
        if (mode) throw new Error(MODE_ERROR);
        mode = "repair";
        break;
      case "--grace-seconds": {
        const parsed = Number.parseInt(next(), 10);
        if (!Number.isInteger(parsed) || parsed < 0) throw new Error("--grace-seconds must be a non-negative integer");
        graceMs = parsed * 1000;
        break;
      }
      case "--limit": {
        const parsed = Number.parseInt(next(), 10);
        if (!Number.isInteger(parsed) || parsed <= 0) throw new Error("--limit must be a positive integer");
        limit = parsed;
        break;
      }
      case "--checkpoint":
        checkpoint = next();
        if (!/^[A-Za-z0-9_-]{1,64}$/.test(checkpoint)) throw new Error("--checkpoint id is invalid");
        break;
      case "--start-after":
        startAfter = next();
        break;
      default:
        throw new Error(`unknown argument: ${arg}`);
    }
  }
  if (!/^[a-z][a-z0-9-]{4,29}$/.test(project)) throw new Error("--project <firebase-project-id> is required");
  if (!mode) throw new Error(MODE_ERROR);
  if ((mode === "apply" || mode === "repair") && !checkpoint) {
    throw new Error(`--${mode} requires --checkpoint <id> so the run can resume and be audited`);
  }
  return { project, mode, limit, checkpoint, startAfter, graceMs };
}

/**
 * Walks every room (paged by id). `repair: false` is read-only. Returns the
 * number of problems still present after the run (0 = clean).
 */
async function verifyOrRepair(
  db: FirebaseFirestore.Firestore,
  options: { repair: boolean; graceMs: number; limit?: number; startAfter?: string; checkpointId?: string; pageSize?: number }
): Promise<number> {
  const pageSize = options.pageSize ?? 200;
  const checkpointRef = options.checkpointId ? db.collection("chatUnreadBackfillRuns").doc(options.checkpointId) : null;
  let cursor: string | null = options.startAfter ?? null;
  if (checkpointRef && !cursor) {
    const cp = await checkpointRef.get();
    const stored = cp.exists ? (cp.data() as Record<string, unknown>).lastRoomId : null;
    if (typeof stored === "string" && stored.length > 0) cursor = stored;
  }
  let rooms = 0;
  let withModel = 0;
  let messagesRead = 0;
  let repaired = 0;
  const issues: RoomIntegrityIssue[] = [];
  const mismatches: RoomReconcileResult["mismatches"] = [];
  const unverifiable: string[] = [];
  const skipped: string[] = [];
  const limit = options.limit ?? Number.POSITIVE_INFINITY;
  outer: for (;;) {
    let query = db.collection("chat_rooms").orderBy(FieldPath.documentId()).limit(pageSize);
    if (cursor) query = query.startAfter(cursor);
    const page = await query.get();
    if (page.empty) break;
    for (const doc of page.docs) {
      if (rooms >= limit) break outer;
      rooms += 1;
      const data = (doc.data() ?? {}) as Record<string, unknown>;
      if (data.unreadModelVersion === 1) withModel += 1;
      issues.push(...checkRoomUnreadIntegrity(doc.id, data));
      const result = await reconcileRoomUnread(db, doc.id, { dryRun: !options.repair, graceMs: options.graceMs });
      messagesRead += result.messagesRead;
      repaired += result.repaired;
      for (const uid of result.unverifiable) unverifiable.push(`${doc.id}/${uid}`);
      if (result.skipped) skipped.push(`${doc.id}:${result.skipped}`);
      if (result.mismatches.length > 0) {
        mismatches.push(...result.mismatches);
        for (const m of result.mismatches) {
          console.log(
            `  ${options.repair && result.repaired > 0 ? "[repaired] " : ""}${m.roomId} ${m.uid}: ${m.kind} actual=${m.actual} expected=${m.expected} basis=${m.basis} pending=${m.pendingMessageIds.length}`
          );
        }
      }
      cursor = doc.id;
      if (checkpointRef && options.repair) {
        await checkpointRef.set({ lastRoomId: doc.id, mode: "repair", updatedAt: FieldValue.serverTimestamp() }, { merge: true });
      }
    }
    if (page.size < pageSize) break;
  }
  const remaining = mismatches.length - (options.repair ? repaired : 0);
  console.log(
    `rooms=${rooms} withUnreadModel=${withModel} legacy=${rooms - withModel} structuralIssues=${issues.length} ` +
      `mismatches=${mismatches.length} repaired=${repaired} remaining=${remaining} unverifiable=${unverifiable.length} ` +
      `skipped=${skipped.length} messagesRead=${messagesRead} graceSeconds=${options.graceMs / 1000}`
  );
  for (const issue of issues) console.log(`  ${issue.roomId}: ${issue.issue} ${issue.detail}`);
  for (const u of unverifiable) console.log(`  unverifiable: ${u}`);
  for (const s of skipped) console.log(`  skipped: ${s}`);
  return issues.length + remaining + unverifiable.length + skipped.length;
}

async function main(): Promise<number> {
  const args = parseArgs(process.argv.slice(2));
  initializeApp({ credential: applicationDefault(), projectId: args.project });
  const db = getFirestore();
  console.log(
    `chat unread backfill: project=${args.project} mode=${args.mode}` +
      `${process.env.FIRESTORE_EMULATOR_HOST ? ` emulator=${process.env.FIRESTORE_EMULATOR_HOST}` : ""}`
  );
  if (args.mode === "verify" || args.mode === "repair") {
    const problems = await verifyOrRepair(db, {
      repair: args.mode === "repair",
      graceMs: args.graceMs,
      limit: args.limit,
      startAfter: args.startAfter,
      checkpointId: args.checkpoint,
    });
    return problems === 0 ? 0 : 1;
  }
  const summary = await runChatUnreadBackfill(db, {
    dryRun: args.mode === "dry-run",
    limitRooms: args.limit,
    checkpointId: args.checkpoint,
    startAfterRoomId: args.startAfter,
    log: (line) => console.log(line),
  });
  console.log(JSON.stringify(summary, null, 2));
  return 0;
}

if (require.main === module) {
  main()
    .then((code) => process.exit(code))
    .catch((error) => {
      console.error("chat unread backfill failed:", error instanceof Error ? error.message : error);
      process.exit(2);
    });
}
