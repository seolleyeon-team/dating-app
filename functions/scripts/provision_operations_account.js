/**
 * Promotes an existing Kakao-bridged Firebase Auth account to operations
 * without ever exposing an admin credential to a Flutter client. It defaults
 * to dry-run. The account gets both `operations: true` and a server-only
 * Firestore `admin/{uid}` record; support callables require both.
 *
 * Usage:
 *   node scripts/provision_operations_account.js --project seolleyeon-final \
 *     --uid 4705818223
 *   node scripts/provision_operations_account.js --project seolleyeon-final \
 *     --uid 4705818223 --apply
 *
 * Run with an operator-owned service-account/ADC session only. Do not commit
 * the UID. The mobile app continues to authenticate this account with the
 * existing Kakao/custom-token flow, then receives the refreshed claim.
 */
const admin = require("firebase-admin");

const args = process.argv.slice(2);
const option = (name) => {
  const index = args.indexOf("--" + name);
  return index >= 0 ? String(args[index + 1] || "").trim() : "";
};
const hasFlag = (name) => args.includes("--" + name);
const projectId = option("project") || process.env.GCLOUD_PROJECT;
const uid = option("uid");
const apply = hasFlag("apply");

if (!projectId || !uid || !/^[^/]{1,128}$/.test(uid)) {
  console.error("--project and a valid --uid are required");
  process.exit(2);
}

admin.initializeApp({ projectId });
const auth = admin.auth();
const db = admin.firestore();

async function main() {
  const user = await auth.getUser(uid);
  if (!apply) {
    console.log(JSON.stringify({ projectId, uid: user.uid, mode: "dry-run" }));
    return;
  }

  await auth.setCustomUserClaims(user.uid, {
    ...(user.customClaims || {}),
    operations: true,
  });
  await db.collection("admin").doc(user.uid).set({
    accountType: "operations",
    active: true,
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
    updatedAt: admin.firestore.FieldValue.serverTimestamp(),
  }, { merge: true });
  await db.collection("users").doc(user.uid).set({
    kakaoUserId: user.uid,
    nickname: "운영팀",
    accountType: "operations",
    isActive: true,
    status: "active",
    initialSetupComplete: false,
    isStudentVerified: false,
    updatedAt: admin.firestore.FieldValue.serverTimestamp(),
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
  }, { merge: true });
  console.log(JSON.stringify({ projectId, uid: user.uid, mode: "applied" }));
}

main().catch((error) => {
  console.error(error && error.message ? error.message : "provision failed");
  process.exit(1);
});
