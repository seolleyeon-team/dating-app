#!/usr/bin/env node
// Kakao friend pairs migration — READ-ONLY dry-run counter (contract: docs/auth-rearchitecture/kakao-friend-pairs-contract.md).
//
// Reports the population sizes needed to plan the one-time-snapshot migration.
// This script NEVER writes. Production execution of any migration remains a
// separately-approved step; per-user migration itself happens organically in
// the client migration gate (spec §30) via createKakaoFriendPairsOnce.
//
// Usage:
//   node scripts/kakao_friend_pairs_migration_dryrun.mjs [--json out.json]
// Env:
//   GOOGLE_APPLICATION_CREDENTIALS or FIRESTORE_EMULATOR_HOST (+ GCLOUD_PROJECT)
//
// Counts produced:
//   usersTotal                    - all users docs
//   usersWithCompletedSnapshot    - kakaoFriendSnapshot.status == "completed"
//   usersRequiringSnapshot        - users without a completed snapshot (migration gate population)
//   usersWithKakaoConnection      - kakaoFriendConnection.connected == true (identity already linked)
//   usersAvoidanceOn              - kakaoFriendAvoidanceEnabled == true
//   legacyExclusionDocs           - recommendationExclusions targets with source == "kakao_talk_friend"
//   newPairExclusionDocs          - targets with source == "kakao_friend_pair"
//   otherSourceExclusionDocs      - targets with any other source (should be 0 today)
//   kakaoIdentityMappings         - kakaoIdentities docs (email-primary linked identities)
//   friendPairDocs                - kakaoFriendPairs docs (post-migration growth metric)
//   activeFriendPairDocs          - kakaoFriendPairs with avoidanceActive == true
//   canonicalPairDocs             - kakaoFriendPairs doc id is the canonical 64-hex sha256 pairId
//   oldFormatPairDocs             - kakaoFriendPairs doc id is NOT 64-hex (joined legacy format).
//                                   The feature has never been deployed, so this MUST be 0 in every
//                                   environment before the collision-safe pairId rollout (blocker #2).
//   potentialIdentityConflicts    - kakaoIdentities whose appUserId has no users doc

import { initializeApp, applicationDefault } from "firebase-admin/app";
import { getFirestore } from "firebase-admin/firestore";
import { writeFileSync } from "node:fs";

const jsonOutIdx = process.argv.indexOf("--json");
const jsonOut = jsonOutIdx >= 0 ? process.argv[jsonOutIdx + 1] : null;

initializeApp({ credential: applicationDefault() });
const db = getFirestore();

async function main() {
  const counts = {
    generatedAt: new Date().toISOString(),
    usersTotal: 0,
    usersWithCompletedSnapshot: 0,
    usersRequiringSnapshot: 0,
    usersWithKakaoConnection: 0,
    usersAvoidanceOn: 0,
    legacyExclusionDocs: 0,
    newPairExclusionDocs: 0,
    otherSourceExclusionDocs: 0,
    kakaoIdentityMappings: 0,
    friendPairDocs: 0,
    activeFriendPairDocs: 0,
    canonicalPairDocs: 0,
    oldFormatPairDocs: 0,
    potentialIdentityConflicts: 0,
  };

  // Mirrors isCanonicalKakaoFriendPairId (functions/src/kakaoFriendPairs.ts).
  const CANONICAL_PAIR_ID_RE = /^[0-9a-f]{64}$/;

  // Users sweep (paged; no PII retained in memory beyond ids for the conflict check).
  let last = null;
  const appUserIds = new Set();
  for (;;) {
    let q = db.collection("users").orderBy("__name__").limit(500);
    if (last) q = q.startAfter(last);
    const snap = await q.get();
    if (snap.empty) break;
    for (const doc of snap.docs) {
      counts.usersTotal += 1;
      appUserIds.add(doc.id);
      const d = doc.data() ?? {};
      const snapshot = d.kakaoFriendSnapshot;
      const completed =
        snapshot && typeof snapshot === "object" && snapshot.status === "completed";
      if (completed) counts.usersWithCompletedSnapshot += 1;
      else counts.usersRequiringSnapshot += 1;
      const conn = d.kakaoFriendConnection;
      if (conn && typeof conn === "object" && conn.connected === true) {
        counts.usersWithKakaoConnection += 1;
      }
      if (d.kakaoFriendAvoidanceEnabled === true) counts.usersAvoidanceOn += 1;
    }
    last = snap.docs[snap.docs.length - 1];
    if (snap.size < 500) break;
  }

  // Exclusion docs by source (collection group).
  let lastEx = null;
  for (;;) {
    let q = db.collectionGroup("targets").orderBy("__name__").limit(500);
    if (lastEx) q = q.startAfter(lastEx);
    const snap = await q.get();
    if (snap.empty) break;
    for (const doc of snap.docs) {
      if (!doc.ref.path.startsWith("recommendationExclusions/")) continue;
      const source = (doc.data() ?? {}).source;
      if (source === "kakao_talk_friend") counts.legacyExclusionDocs += 1;
      else if (source === "kakao_friend_pair") counts.newPairExclusionDocs += 1;
      else counts.otherSourceExclusionDocs += 1;
    }
    lastEx = snap.docs[snap.docs.length - 1];
    if (snap.size < 500) break;
  }

  // Identity mappings + conflicts.
  let lastId = null;
  for (;;) {
    let q = db.collection("kakaoIdentities").orderBy("__name__").limit(500);
    if (lastId) q = q.startAfter(lastId);
    const snap = await q.get();
    if (snap.empty) break;
    for (const doc of snap.docs) {
      counts.kakaoIdentityMappings += 1;
      const appUserId = (doc.data() ?? {}).appUserId;
      if (typeof appUserId !== "string" || !appUserIds.has(appUserId)) {
        counts.potentialIdentityConflicts += 1;
      }
    }
    lastId = snap.docs[snap.docs.length - 1];
    if (snap.size < 500) break;
  }

  // Friend pairs.
  let lastPair = null;
  for (;;) {
    let q = db.collection("kakaoFriendPairs").orderBy("__name__").limit(500);
    if (lastPair) q = q.startAfter(lastPair);
    const snap = await q.get();
    if (snap.empty) break;
    for (const doc of snap.docs) {
      counts.friendPairDocs += 1;
      if ((doc.data() ?? {}).avoidanceActive === true) counts.activeFriendPairDocs += 1;
      // Predeploy invariant (blocker #2): every pair doc id must already be the
      // canonical hash; oldFormatPairDocs > 0 blocks the rollout for review.
      if (CANONICAL_PAIR_ID_RE.test(doc.id)) counts.canonicalPairDocs += 1;
      else counts.oldFormatPairDocs += 1;
    }
    lastPair = snap.docs[snap.docs.length - 1];
    if (snap.size < 500) break;
  }

  const report = JSON.stringify(counts, null, 2);
  console.log(report);
  if (jsonOut) writeFileSync(jsonOut, report + "\n");
}

main().catch((err) => {
  console.error("dry-run failed:", err?.message ?? err);
  process.exitCode = 1;
});
