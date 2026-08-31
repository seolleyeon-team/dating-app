import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it } from "node:test";

const indexSource = readFileSync(resolve(__dirname, "../src/index.ts"), "utf8");
const blindStoreSource = readFileSync(
  resolve(__dirname, "../src/blindMeeting/store.ts"),
  "utf8"
);
const rulesSource = readFileSync(resolve(__dirname, "../../firestore.rules"), "utf8");

describe("heart economy contract", () => {
  it("trusts only the five configured store products", () => {
    for (const entry of [
      '"seolleyeon.heart.20": 20',
      '"seolleyeon.heart.40": 40',
      '"seolleyeon.heart.100": 100',
      '"seolleyeon.heart.220": 220',
      '"seolleyeon.heart.first.50": 50',
    ]) {
      assert.match(indexSource, new RegExp(entry.replace(/\./g, "\\.")));
    }
    assert.doesNotMatch(indexSource, /"seolleyeon\.heart\.(10|30)"/);
    assert.match(indexSource, /purchaseCount > 0/);
    assert.match(indexSource, /firstPurchaseOfferUsed/);
  });

  it("keeps feature costs server-authoritative", () => {
    assert.match(indexSource, /directChat:\s*10/);
    assert.match(indexSource, /seasonRoulette:\s*20/);
    assert.match(indexSource, /recommendationRefresh:\s*5/);
    assert.match(blindStoreSource, /const heartCost = 30/);
  });

  it("creates paid resources and ledger entries in transactions", () => {
    assert.match(indexSource, /export const unlockDirectChat = onCall/);
    assert.match(indexSource, /feature: "direct_chat"/);
    assert.match(indexSource, /feature: "season_roulette"/);
    assert.match(indexSource, /feature !== "recommendation_refresh"/);
    assert.match(
      blindStoreSource,
      /export async function createPaidBlindMeetingApplication/
    );
    assert.match(blindStoreSource, /feature: "blind_meeting"/);
  });

  it("denies client chat-room creation so the 10H paywall cannot be bypassed", () => {
    const chatRules = rulesSource.match(
      /match \/chat_rooms\/\{roomId\} \{([\s\S]*?)match \/messages/
    )?.[1];
    assert.ok(chatRules);
    assert.match(chatRules, /allow create: if false;/);
  });
});
