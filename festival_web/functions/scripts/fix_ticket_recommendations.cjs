#!/usr/bin/env node
/**
 * Single-ticket CLIP recommendation fix (ops).
 * Usage: node scripts/fix_ticket_recommendations.cjs 2XJBR9
 */
const admin = require("firebase-admin");

const PROJECT_ID = "seolleyeon-festival";
const ticketId = (process.argv[2] || "").trim().toUpperCase();

if (!ticketId) {
  console.error("Usage: node scripts/fix_ticket_recommendations.cjs <TICKET_ID>");
  process.exit(1);
}

admin.initializeApp({ projectId: PROJECT_ID });
const { generateRecommendationsForTicket } = require("../lib/festival_recommendations");
const db = admin.firestore();

async function main() {
  const ticketRef = db.collection("festivalTickets").doc(ticketId);
  const ticketSnap = await ticketRef.get();
  if (!ticketSnap.exists) {
    throw new Error(`Ticket not found: ${ticketId}`);
  }

  const swipes = await ticketRef.collection("tasteSwipes").get();
  let likedCount = 0;
  for (const doc of swipes.docs) {
    if (doc.data().liked === true) likedCount += 1;
  }

  if (ticketSnap.data()?.tasteCompleted !== true) {
    await ticketRef.set(
      {
        tasteCompleted: true,
        tasteCompletedAt: admin.firestore.FieldValue.serverTimestamp(),
        tasteLikedCount: likedCount,
        tasteTotalCount: swipes.size,
        updatedAt: admin.firestore.FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
    console.log(`Set tasteCompleted=true (${swipes.size} swipes, ${likedCount} likes)`);
  }

  const result = await generateRecommendationsForTicket(ticketId, "manual_ops_fix");
  console.log(JSON.stringify(result, null, 2));

  if (!result.success && result.recommendations.length === 0) {
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
