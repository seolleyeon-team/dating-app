/**
 * P0-2 — one-time backfill of room-level unread counts for legacy rooms.
 *
 * Usage (from functions/, after `npm run build`):
 *   node lib/chatUnreadBackfillCli.js --project seolleyeon-final --dry-run
 *   node lib/chatUnreadBackfillCli.js --project seolleyeon-final --apply \
 *        --limit 200 --checkpoint p02-backfill-20261014
 *   node lib/chatUnreadBackfillCli.js --project seolleyeon-final --verify
 *
 * Safety properties (see chatUnread.ts):
 *   - rooms are paged by document id, never loaded all at once
 *   - every room is idempotent (unreadBackfilledAt) and resumable (unmarked
 *     messages only); the run is resumable through the checkpoint document
 *   - at most 400 messages per transaction (500-op limit headroom)
 *   - --dry-run performs the same reads and no writes
 *   - --verify is read-only and reports integrity issues
 *
 * Authentication: Application Default Credentials (gcloud auth
 * application-default login) or GOOGLE_APPLICATION_CREDENTIALS. Point
 * FIRESTORE_EMULATOR_HOST at an emulator to rehearse.
 */
import { applicationDefault, initializeApp } from "firebase-admin/app";
import { FieldPath, getFirestore } from "firebase-admin/firestore";

import {
  checkRoomUnreadIntegrity,
  runChatUnreadBackfill,
  type RoomIntegrityIssue,
} from "./chatUnread";

type Args = {
  project: string;
  mode: "dry-run" | "apply" | "verify";
  limit?: number;
  checkpoint?: string;
  startAfter?: string;
};

export function parseArgs(argv: string[]): Args {
  let project = "";
  let mode: Args["mode"] | null = null;
  let limit: number | undefined;
  let checkpoint: string | undefined;
  let startAfter: string | undefined;
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
        if (mode) throw new Error("choose exactly one of --dry-run, --apply, --verify");
        mode = "dry-run";
        break;
      case "--apply":
        if (mode) throw new Error("choose exactly one of --dry-run, --apply, --verify");
        mode = "apply";
        break;
      case "--verify":
        if (mode) throw new Error("choose exactly one of --dry-run, --apply, --verify");
        mode = "verify";
        break;
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
  if (!mode) throw new Error("choose exactly one of --dry-run, --apply, --verify");
  if (mode === "apply" && !checkpoint) {
    throw new Error("--apply requires --checkpoint <id> so the run can resume");
  }
  return { project, mode, limit, checkpoint, startAfter };
}

async function verify(db: FirebaseFirestore.Firestore, pageSize = 200): Promise<number> {
  let cursor: string | null = null;
  let rooms = 0;
  let withModel = 0;
  const issues: RoomIntegrityIssue[] = [];
  for (;;) {
    let query = db.collection("chat_rooms").orderBy(FieldPath.documentId()).limit(pageSize);
    if (cursor) query = query.startAfter(cursor);
    const page = await query.get();
    if (page.empty) break;
    for (const doc of page.docs) {
      rooms += 1;
      const data = (doc.data() ?? {}) as Record<string, unknown>;
      if (data.unreadModelVersion === 1) withModel += 1;
      issues.push(...checkRoomUnreadIntegrity(doc.id, data));
    }
    cursor = page.docs[page.docs.length - 1].id;
    if (page.size < pageSize) break;
  }
  console.log(`rooms=${rooms} withUnreadModel=${withModel} legacy=${rooms - withModel} issues=${issues.length}`);
  for (const issue of issues) console.log(`  ${issue.roomId}: ${issue.issue} ${issue.detail}`);
  return issues.length;
}

async function main(): Promise<number> {
  const args = parseArgs(process.argv.slice(2));
  initializeApp({ credential: applicationDefault(), projectId: args.project });
  const db = getFirestore();
  console.log(
    `chat unread backfill: project=${args.project} mode=${args.mode}` +
      `${process.env.FIRESTORE_EMULATOR_HOST ? ` emulator=${process.env.FIRESTORE_EMULATOR_HOST}` : ""}`
  );
  if (args.mode === "verify") {
    return (await verify(db)) === 0 ? 0 : 1;
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
