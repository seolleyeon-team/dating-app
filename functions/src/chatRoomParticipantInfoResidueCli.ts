/**
 * P1-5 — historical residue of the dotted-key participantInfo write.
 *
 * Before the fix, closing a deleted member's room wrote
 * `set({ ["participantInfo.<uid>"]: {...} }, { merge: true })`, which under
 * Firestore's set-merge semantics created a LITERAL top-level field named
 * "participantInfo.<uid>" and left the member's real nested nickname / avatar
 * untouched. This CLI finds such rooms and, with --apply, moves the deleted
 * placeholder into the nested map and removes the literal field.
 *
 * Usage (from functions/, after `npm run build`):
 *   node lib/chatRoomParticipantInfoResidueCli.js --project seolleyeon-final --audit
 *   node lib/chatRoomParticipantInfoResidueCli.js --project seolleyeon-final --apply
 *
 * Safety: --audit is read-only; rooms are paged by document id; each repair is
 * one room-level write that only touches the literal field(s) and the nested
 * entries they name; re-running finds nothing (idempotent). Output carries
 * room ids and uid fingerprints only.
 */
import { createHash } from "node:crypto";

import { applicationDefault, initializeApp } from "firebase-admin/app";
import { FieldPath, FieldValue, getFirestore, type Firestore } from "firebase-admin/firestore";

import { DELETED_USER_DISPLAY_NAME } from "./accountDeletionConstants";

const LITERAL_KEY = /^participantInfo\.([A-Za-z0-9_-]+)$/;

export type ResidueRepair = {
  /** Literal top-level keys to delete. */
  literalKeys: string[];
  /** uids whose nested entry becomes the deleted placeholder. */
  uids: string[];
};

/** Pure: what a repair of this room document would change (null = clean). */
export function planParticipantInfoResidueRepair(room: Record<string, unknown>): ResidueRepair | null {
  const literalKeys = Object.keys(room).filter((key) => LITERAL_KEY.test(key)).sort();
  if (literalKeys.length === 0) return null;
  const uids = literalKeys.map((key) => key.match(LITERAL_KEY)![1]);
  return { literalKeys, uids };
}

/**
 * The update as (FieldPath, value) pairs: delete each literal field and write
 * the deleted placeholder into the nested map. update() with FieldPath never
 * reinterprets dots, so the repair cannot recreate the defect.
 */
export function buildResidueRepairUpdate(repair: ResidueRepair): Array<[FieldPath, unknown]> {
  const pairs: Array<[FieldPath, unknown]> = [];
  for (const key of repair.literalKeys) pairs.push([new FieldPath(key), FieldValue.delete()]);
  for (const uid of repair.uids) {
    pairs.push([
      new FieldPath("participantInfo", uid),
      { nickname: DELETED_USER_DISPLAY_NAME, avatarUrl: null, accountDeleted: true },
    ]);
  }
  pairs.push([new FieldPath("updatedAt"), FieldValue.serverTimestamp()]);
  return pairs;
}

export async function runParticipantInfoResidueScan(
  db: Firestore,
  options: { apply: boolean; pageSize?: number; log?: (line: string) => void }
): Promise<{ roomsScanned: number; roomsWithResidue: number; repaired: number }> {
  const pageSize = options.pageSize ?? 300;
  const log = options.log ?? (() => undefined);
  let roomsScanned = 0, roomsWithResidue = 0, repaired = 0;
  let last: string | null = null;
  for (;;) {
    let query = db.collection("chat_rooms").orderBy(FieldPath.documentId()).limit(pageSize);
    if (last) query = query.startAfter(last);
    const page = await query.get();
    for (const doc of page.docs) {
      roomsScanned += 1;
      const repair = planParticipantInfoResidueRepair(doc.data());
      if (!repair) continue;
      roomsWithResidue += 1;
      log(`residue room=${doc.id} uids=${repair.uids.map((u) => createHash("sha256").update(u).digest("hex").slice(0, 10)).join(",")}`);
      if (options.apply) {
        const [first, ...rest] = buildResidueRepairUpdate(repair);
        await doc.ref.update(first[0], first[1], ...rest.flat());
        repaired += 1;
      }
    }
    if (page.size < pageSize) break;
    last = page.docs[page.docs.length - 1].id;
  }
  return { roomsScanned, roomsWithResidue, repaired };
}

function fail(message: string): never {
  console.error(message);
  process.exit(2);
}

async function main(): Promise<void> {
  const argv = process.argv.slice(2);
  let project = "";
  let apply: boolean | null = null;
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--project") project = argv[++i] ?? "";
    else if (argv[i] === "--audit") apply = apply === null ? false : fail("choose one of --audit, --apply");
    else if (argv[i] === "--apply") apply = apply === null ? true : fail("choose one of --audit, --apply");
    else fail(`unknown argument ${argv[i]}`);
  }
  if (!project) fail("--project is required");
  if (apply === null) fail("choose one of --audit, --apply");
  initializeApp({ projectId: project, credential: process.env.FIRESTORE_EMULATOR_HOST ? undefined : applicationDefault() });
  const result = await runParticipantInfoResidueScan(getFirestore(), { apply: apply as boolean, log: (line) => console.log(line) });
  console.log(JSON.stringify({ mode: apply ? "apply" : "audit", ...result }, null, 2));
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
