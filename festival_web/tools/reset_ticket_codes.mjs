#!/usr/bin/env node
/**
 * 기존 6자리 입장 코드 계정 데이터 삭제 + 새 코드 20개 Firestore 등록
 *
 * Usage:
 *   cd festival_web/tools
 *   node reset_ticket_codes.mjs
 *
 * Requires: firebase login / GOOGLE_APPLICATION_CREDENTIALS
 */

import { randomBytes } from "crypto";
import { writeFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import admin from "firebase-admin";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ID = "seolleyeon-festival";
const CODE_LENGTH = 6;
const NEW_CODE_COUNT = 20;
const CHARSET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // 혼동 문자(I,O,0,1) 제외

const OLD_CODES = [
  "A5B6C7",
  "K9M2Q4",
  "R7T8Y2",
  "C3D4E5",
  "F6G7H8",
  "J2K3L4",
  "M5N6P7",
  "Q8R9S2",
  "T3U4V5",
  "W6X7Y8",
];

admin.initializeApp({ projectId: PROJECT_ID });
const db = admin.firestore();
const bucket = admin.storage().bucket(`${PROJECT_ID}.firebasestorage.app`);

async function deleteCollectionDocs(queryOrRef, batchSize = 400) {
  if (queryOrRef.get) {
    const snap = await queryOrRef.get();
    if (snap.empty) return 0;
    const batch = db.batch();
    snap.docs.forEach((doc) => batch.delete(doc.ref));
    await batch.commit();
    return snap.size;
  }
  return 0;
}

async function deleteSubcollection(parentRef, subcollectionName) {
  let total = 0;
  while (true) {
    const snap = await parentRef.collection(subcollectionName).limit(400).get();
    if (snap.empty) break;
    const batch = db.batch();
    snap.docs.forEach((doc) => batch.delete(doc.ref));
    await batch.commit();
    total += snap.size;
  }
  return total;
}

async function deleteModelRecs(ticketId) {
  const dailySnap = await db
    .collection("festivalModelRecs")
    .doc(ticketId)
    .collection("daily")
    .get();
  for (const dailyDoc of dailySnap.docs) {
    await deleteSubcollection(dailyDoc.ref, "sources");
    await dailyDoc.ref.delete();
  }
  await db.collection("festivalModelRecs").doc(ticketId).delete().catch(() => {});
}

async function deleteTicketData(ticketId) {
  const stats = {
    tasteSwipes: 0,
    chatRooms: 0,
    chatMembershipRooms: 0,
    sessions: 0,
    storageFiles: 0,
  };

  const ticketRef = db.collection("festivalTickets").doc(ticketId);
  stats.tasteSwipes = await deleteSubcollection(ticketRef, "tasteSwipes");

  stats.chatMembershipRooms = await deleteSubcollection(
    db.collection("festivalChatMemberships").doc(ticketId),
    "rooms"
  );
  await db.collection("festivalChatMemberships").doc(ticketId).delete().catch(() => {});

  const roomsSnap = await db
    .collection("festivalChatRooms")
    .where("participantTicketIds", "array-contains", ticketId)
    .get();
  for (const roomDoc of roomsSnap.docs) {
    stats.chatRooms += await deleteSubcollection(roomDoc.ref, "messages");
    await roomDoc.ref.delete();
    stats.chatRooms += 1;
  }

  const sessionsSnap = await db
    .collection("festivalSessions")
    .where("ticketId", "==", ticketId)
    .get();
  for (const sessionDoc of sessionsSnap.docs) {
    const uid = sessionDoc.id;
    await deleteSubcollection(
      db.collection("festivalPushTokens").doc(uid),
      "tokens"
    );
    await db.collection("festivalPushTokens").doc(uid).delete().catch(() => {});
    await sessionDoc.ref.delete();
    stats.sessions += 1;
  }

  await deleteModelRecs(ticketId);
  await db.collection("festivalProfileEmbeddings").doc(ticketId).delete().catch(() => {});
  await db.collection("festivalProfiles").doc(ticketId).delete().catch(() => {});
  await db.collection("festivalTicketEnforcement").doc(ticketId).delete().catch(() => {});
  await ticketRef.delete().catch(() => {});

  try {
    const [files] = await bucket.getFiles({ prefix: `festivalProfiles/${ticketId}/` });
    if (files.length > 0) {
      await Promise.all(files.map((file) => file.delete().catch(() => {})));
      stats.storageFiles = files.length;
    }
  } catch (_) {
    // Storage bucket may be unavailable in local env.
  }

  return stats;
}

function generateUniqueCodes(count, exclude) {
  const excludeSet = new Set(exclude);
  const codes = new Set();
  while (codes.size < count) {
    const bytes = randomBytes(CODE_LENGTH);
    let code = "";
    for (let i = 0; i < CODE_LENGTH; i++) {
      code += CHARSET[bytes[i] % CHARSET.length];
    }
    if (!excludeSet.has(code)) codes.add(code);
  }
  return [...codes];
}

async function seedTickets(codes) {
  const batch = db.batch();
  const now = admin.firestore.FieldValue.serverTimestamp();
  for (const code of codes) {
    const ref = db.collection("festivalTickets").doc(code);
    batch.set(ref, {
      code,
      status: "available",
      round: 1,
      seeded: true,
      createdAt: now,
      updatedAt: now,
    });
  }
  await batch.commit();
}

function writeSeedJson(codes) {
  const payload = {
    projectId: PROJECT_ID,
    note: "6자리 영문+숫자 입장 코드 20개. QR URL을 생성기에 넣으면 바로 인증됩니다.",
    generatedAt: new Date().toISOString(),
    tickets: codes.map((code) => ({
      code,
      normalizedCode: code,
      qrUrl: `https://seolleyeon-festival.web.app/r/${code}`,
    })),
  };
  const outPath = join(__dirname, "..", "ticket_codes_seed.json");
  writeFileSync(outPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  return outPath;
}

async function main() {
  console.log(`Project: ${PROJECT_ID}`);
  console.log(`Deleting ${OLD_CODES.length} legacy ticket codes...\n`);

  const deleteSummary = {};
  for (const code of OLD_CODES) {
    console.log(`— ${code}`);
    deleteSummary[code] = await deleteTicketData(code);
    console.log(`   ${JSON.stringify(deleteSummary[code])}`);
  }

  const newCodes = generateUniqueCodes(NEW_CODE_COUNT, OLD_CODES);
  console.log(`\nSeeding ${newCodes.length} new codes...`);
  await seedTickets(newCodes);

  const seedPath = writeSeedJson(newCodes);
  console.log(`\nUpdated: ${seedPath}`);
  console.log("\nNew codes:");
  newCodes.forEach((code, index) => {
    console.log(`${String(index + 1).padStart(2, "0")}. ${code}`);
  });

  console.log("\nDone.");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
