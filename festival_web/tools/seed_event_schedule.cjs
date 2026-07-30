#!/usr/bin/env node
/**
 * Set festival event schedule in Firestore.
 * Usage: node tools/seed_event_schedule.cjs
 * Optional env: LOCK=20:30 BATCH=20:31 REVEAL=21:00 DATE=2026-05-27
 */

const { readFileSync, existsSync } = require("fs");
const { homedir } = require("os");
const { join } = require("path");

const PROJECT_ID = "seolleyeon-festival";
const BASE = `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)/documents`;

function getAccessToken() {
  const configPath = join(homedir(), ".config/configstore/firebase-tools.json");
  const token = JSON.parse(readFileSync(configPath, "utf8"))?.tokens?.access_token;
  if (!token) throw new Error("firebase login required");
  return token;
}

function kstIso(dateStr, timeStr) {
  return `${dateStr}T${timeStr}:00+09:00`;
}

async function setSchedule(fields, token) {
  const url = `${BASE}/festivalSettings/schedule`;
  const body = { fields };
  const res = await fetch(url, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`Failed: ${res.status} ${await res.text()}`);
  }
}

async function main() {
  const date = process.env.DATE || "2026-05-27";
  const lock = process.env.LOCK || "20:30";
  const batch = process.env.BATCH || "20:31";
  const reveal = process.env.REVEAL || "21:00";

  const token = getAccessToken();
  await setSchedule(
    {
      enabled: { booleanValue: true },
      title: { stringValue: "디버그 일정" },
      profileTasteLockAt: { timestampValue: kstIso(date, lock) },
      batchRecommendationsAt: { timestampValue: kstIso(date, batch) },
      recommendationsRevealAt: { timestampValue: kstIso(date, reveal) },
      batchCompletedAt: { nullValue: null },
      batchSuccessCount: { nullValue: null },
      batchTotalCount: { nullValue: null },
      batchLastError: { nullValue: null },
      updatedAt: { timestampValue: new Date().toISOString() },
    },
    token
  );

  console.log("Schedule set:");
  console.log(`  lock profile/taste: ${date} ${lock} KST`);
  console.log(`  batch CLIP:       ${date} ${batch} KST`);
  console.log(`  reveal rec tab:   ${date} ${reveal} KST`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
