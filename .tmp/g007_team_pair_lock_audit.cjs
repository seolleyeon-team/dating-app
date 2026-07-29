const { initializeApp, applicationDefault } = require("firebase-admin/app");
const { getFirestore } = require("firebase-admin/firestore");
const crypto = require("crypto");
initializeApp({ credential: applicationDefault(), projectId: "seolleyeon-final" });
(async () => {
  const snapshot = await getFirestore()
    .collection("eventTeamMeetingRequests")
    .where("status", "==", "pending")
    .get();
  const pairs = new Map();
  let missingPairLockIdCount = 0;
  for (const doc of snapshot.docs) {
    const data = doc.data();
    const pair = [String(data.fromTeamId || ""), String(data.toTeamId || "")]
      .sort()
      .join("|");
    const hash = crypto.createHash("sha256").update(pair).digest("hex").slice(0, 12);
    pairs.set(hash, (pairs.get(hash) || 0) + 1);
    if (!data.pairLockId) missingPairLockIdCount += 1;
  }
  const duplicatePairCount = [...pairs.values()].filter((count) => count > 1).length;
  process.stdout.write(JSON.stringify({
    project: "seolleyeon-final",
    pendingCount: snapshot.size,
    missingPairLockIdCount,
    duplicatePairCount,
  }));
})().catch((error) => {
  process.stderr.write(String(error.code || error.name || "audit_failed"));
  process.exitCode = 1;
});