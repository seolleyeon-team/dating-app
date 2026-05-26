#!/usr/bin/env node
/**
 * 기존 6자리 입장 코드 계정 데이터 삭제 + 새 코드 20개 Firestore 등록
 *
 * Usage (from festival_web/functions):
 *   node scripts/reset_ticket_codes.cjs
 *
 * Requires: `firebase login` (uses ~/.config/configstore/firebase-tools.json access token)
 */

const { randomBytes } = require("crypto");
const { existsSync, readFileSync, writeFileSync } = require("fs");
const { homedir } = require("os");
const { join } = require("path");

const PROJECT_ID = "seolleyeon-festival";
const DATABASE = "(default)";
const CODE_LENGTH = 6;
const NEW_CODE_COUNT = 20;
const CHARSET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

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

const BASE = `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/${DATABASE}/documents`;

function getAccessToken() {
  const configPath = join(homedir(), ".config/configstore/firebase-tools.json");
  if (!existsSync(configPath)) {
    throw new Error("firebase login이 필요합니다.");
  }
  const token = JSON.parse(readFileSync(configPath, "utf8"))?.tokens?.access_token;
  if (!token) throw new Error("firebase access token을 찾지 못했습니다.");
  return token;
}

async function api(path, { method = "GET", body } = {}, token) {
  const url = path.startsWith("http") ? path : `${BASE}/${path}`;
  const response = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.status === 404) return null;
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${method} ${url} failed (${response.status}): ${text}`);
  }
  if (response.status === 204) return null;
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) return null;
  return response.json();
}

async function deleteDocument(path, token) {
  await api(path, { method: "DELETE" }, token).catch((error) => {
    if (String(error).includes("404")) return;
    throw error;
  });
}

async function listCollection(collectionPath, token) {
  const docs = [];
  let pageToken = null;
  do {
    const suffix = pageToken ? `?pageToken=${pageToken}` : "";
    const result = await api(`${collectionPath}${suffix}`, {}, token);
    if (!result) break;
    if (Array.isArray(result.documents)) docs.push(...result.documents);
    pageToken = result.nextPageToken || null;
  } while (pageToken);
  return docs;
}

function docIdFromName(name) {
  return name.split("/").pop();
}

function docPathFromName(name) {
  const prefix = `projects/${PROJECT_ID}/databases/${DATABASE}/documents/`;
  return name.replace(prefix, "");
}

async function deleteCollectionRecursive(collectionPath, token) {
  const docs = await listCollection(collectionPath, token);
  for (const doc of docs) {
    const path = docPathFromName(doc.name);
    await deleteDocument(path, token);
  }
}

async function runQuery(collectionId, field, op, value, token) {
  const body = {
    structuredQuery: {
      from: [{ collectionId }],
      where: {
        fieldFilter: {
          field: { fieldPath: field },
          op,
          value:
            typeof value === "string"
              ? { stringValue: value }
              : { booleanValue: value },
        },
      },
    },
  };
  const result = await api(":runQuery", { method: "POST", body }, token);
  if (!Array.isArray(result)) return [];
  return result
    .filter((row) => row.document?.name)
    .map((row) => docPathFromName(row.document.name));
}

async function deleteTicketData(ticketId, token) {
  const stats = {
    tasteSwipes: 0,
    chatRooms: 0,
    chatMembershipRooms: 0,
    sessions: 0,
  };

  const swipeDocs = await listCollection(`festivalTickets/${ticketId}/tasteSwipes`, token);
  for (const doc of swipeDocs) {
    await deleteDocument(docPathFromName(doc.name), token);
    stats.tasteSwipes += 1;
  }

  const membershipRooms = await listCollection(
    `festivalChatMemberships/${ticketId}/rooms`,
    token
  );
  for (const doc of membershipRooms) {
    await deleteDocument(docPathFromName(doc.name), token);
    stats.chatMembershipRooms += 1;
  }
  await deleteDocument(`festivalChatMemberships/${ticketId}`, token);

  const roomPaths = await runQuery(
    "festivalChatRooms",
    "participantTicketIds",
    "ARRAY_CONTAINS",
    ticketId,
    token
  );
  for (const roomPath of roomPaths) {
    const messages = await listCollection(`${roomPath}/messages`, token);
    for (const message of messages) {
      await deleteDocument(docPathFromName(message.name), token);
    }
    await deleteDocument(roomPath, token);
    stats.chatRooms += 1;
  }

  const sessionPaths = await runQuery("festivalSessions", "ticketId", "EQUAL", ticketId, token);
  for (const sessionPath of sessionPaths) {
    const uid = docIdFromName(`projects/x/databases/x/documents/${sessionPath}`);
    const tokenDocs = await listCollection(`festivalPushTokens/${uid}/tokens`, token);
    for (const doc of tokenDocs) {
      await deleteDocument(docPathFromName(doc.name), token);
    }
    await deleteDocument(`festivalPushTokens/${uid}`, token);
    await deleteDocument(sessionPath, token);
    stats.sessions += 1;
  }

  const dailyDocs = await listCollection(`festivalModelRecs/${ticketId}/daily`, token);
  for (const daily of dailyDocs) {
    const dailyPath = docPathFromName(daily.name);
    await deleteCollectionRecursive(`${dailyPath}/sources`, token);
    await deleteDocument(dailyPath, token);
  }
  await deleteDocument(`festivalModelRecs/${ticketId}`, token);
  await deleteDocument(`festivalProfileEmbeddings/${ticketId}`, token);
  await deleteDocument(`festivalProfiles/${ticketId}`, token);
  await deleteDocument(`festivalTicketEnforcement/${ticketId}`, token);
  await deleteDocument(`festivalTickets/${ticketId}`, token);

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

async function seedTickets(codes, token) {
  const docPrefix = `projects/${PROJECT_ID}/databases/${DATABASE}/documents`;
  const writes = codes.map((code) => ({
    update: {
      name: `${docPrefix}/festivalTickets/${code}`,
      fields: {
        code: { stringValue: code },
        status: { stringValue: "available" },
        round: { integerValue: "1" },
        seeded: { booleanValue: true },
        createdAt: { timestampValue: new Date().toISOString() },
        updatedAt: { timestampValue: new Date().toISOString() },
      },
    },
  }));

  // Firestore batch write limit is 500.
  for (let i = 0; i < writes.length; i += 400) {
    const chunk = writes.slice(i, i + 400);
    await api(":commit", { method: "POST", body: { writes: chunk } }, token);
  }
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
  const outPath = join(__dirname, "..", "..", "ticket_codes_seed.json");
  writeFileSync(outPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  return outPath;
}

async function main() {
  const token = getAccessToken();
  console.log(`Project: ${PROJECT_ID}`);
  console.log(`Deleting ${OLD_CODES.length} legacy ticket codes...\n`);

  for (const code of OLD_CODES) {
    console.log(`— ${code}`);
    const stats = await deleteTicketData(code, token);
    console.log(`   ${JSON.stringify(stats)}`);
  }

  const newCodes = generateUniqueCodes(NEW_CODE_COUNT, OLD_CODES);
  console.log(`\nSeeding ${newCodes.length} new codes...`);
  await seedTickets(newCodes, token);

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
