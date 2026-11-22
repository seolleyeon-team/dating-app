/**
 * AUD-25 — a retry of a paid recommendation refresh that already succeeded
 * must answer with the stored result, never with an error.
 *
 * evaluateRefreshPurchase puts "already purchased" before every other check,
 * but the callable ran three throwing prechecks BEFORE the transaction that
 * calls it: no active source, a regenerated source, fewer than six eligible
 * candidates. Any of them turned a successful purchase (five hearts spent)
 * into `refresh_unavailable` / `refresh_stale_feed` on the retry.
 *
 * Firestore emulator, the real callable factory with a stub user resolver
 * (the resolver is exercised by accountStateGate.emulator-test.ts).
 *
 *   npx firebase-tools@15.30.2 emulators:exec --only firestore --project demo-aud25-refresh \
 *     "node --test functions/.ci-emulator-lib/recommendationRefreshReplay.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { getFirestore, Timestamp } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}

// index.ts performs initializeApp(); only import here.
import "./index";
import {
  ONE_TO_ONE_REFRESH_COST_HEARTS,
  ONE_TO_ONE_REFRESH_PRODUCT,
  createPurchaseRecommendationRefreshFunction,
} from "./recommendationRefresh";

type Runnable = { run: (request: unknown) => Promise<unknown> };
type RefreshResponse = {
  ok: boolean;
  status: string;
  product: string;
  dateKey: string;
  algo: string;
  costHearts: number;
  remainingHearts: number;
  displayCandidateUids: string[];
};

const db = getFirestore();
let seq = 0;
const fresh = (p: string) => `${p}_${Date.now().toString(36)}_${++seq}`;

const purchase = createPurchaseRecommendationRefreshFunction(db, async (auth) => {
  if (!auth?.uid) throw new Error("unauthenticated");
  return { userId: auth.uid };
}) as unknown as Runnable;

function call(uid: string, data: Record<string, unknown>) {
  return purchase.run({ data, auth: { uid, token: {} }, rawRequest: {} }) as Promise<RefreshResponse>;
}

async function failureMessage(promise: Promise<unknown>): Promise<string> {
  try {
    await promise;
  } catch (error) {
    return String((error as { message?: string }).message ?? error);
  }
  return "ok";
}

const DATE_KEY = "20261120";
const PAID = ["cand_4", "cand_5", "cand_6"];

/** A viewer who bought the refresh for DATE_KEY and has spent hearts since. */
async function seedPurchasedViewer(balanceNow: number, entitlement: Record<string, unknown> = {}) {
  const uid = fresh("viewer");
  const viewerRef = db.collection("users").doc(uid);
  await viewerRef.set({ heartBalance: balanceNow, isActive: true, status: "active" });
  await viewerRef.collection("recommendationRefreshes").doc(DATE_KEY).set({
    product: ONE_TO_ONE_REFRESH_PRODUCT,
    dateKey: DATE_KEY,
    algo: "rrf",
    costHearts: ONE_TO_ONE_REFRESH_COST_HEARTS,
    displayCandidateUids: PAID,
    displayCandidateRanks: [4, 5, 6],
    status: "completed",
    // The balance right after the purchase; the viewer has spent since.
    heartBalanceAfter: 40,
    createdAt: Timestamp.now(),
    ...entitlement,
  });
  return { uid, viewerRef };
}

test("AUD-25: a retry after the source disappeared answers with the stored purchase and the current balance", async () => {
  // No recommendation source document exists for this viewer any more (the
  // daily set was replaced / expired): the precheck used to throw here.
  const { uid, viewerRef } = await seedPurchasedViewer(12);

  const first = await call(uid, { expectedDateKey: DATE_KEY, expectedAlgo: "rrf" });
  assert.equal(first.ok, true);
  assert.equal(first.status, "already_purchased");
  assert.equal(first.dateKey, DATE_KEY);
  assert.equal(first.algo, "rrf");
  assert.deepEqual(first.displayCandidateUids, PAID);
  // Not the 40 stored at purchase time: the balance as it is now.
  assert.equal(first.remainingHearts, 12);
  assert.equal(first.costHearts, ONE_TO_ONE_REFRESH_COST_HEARTS);

  // Replays never charge and never write a second entitlement.
  const again = await Promise.all([
    call(uid, { expectedDateKey: DATE_KEY }),
    call(uid, { expectedDateKey: DATE_KEY, expectedAlgo: "another_algo" }),
  ]);
  for (const response of again) {
    assert.equal(response.status, "already_purchased");
    assert.deepEqual(response.displayCandidateUids, PAID);
  }
  assert.equal((await viewerRef.get()).get("heartBalance"), 12);
  assert.equal((await viewerRef.collection("recommendationRefreshes").get()).size, 1);
});

test("AUD-25: the replay follows later spending — it reports the balance of the moment", async () => {
  const { uid, viewerRef } = await seedPurchasedViewer(9);
  assert.equal((await call(uid, { expectedDateKey: DATE_KEY })).remainingHearts, 9);
  await viewerRef.update({ heartBalance: 2 });
  assert.equal((await call(uid, { expectedDateKey: DATE_KEY })).remainingHearts, 2);
});

test("AUD-25: nothing is replayed without a completed, identifiable purchase", async () => {
  // No entitlement at all: the ordinary refusal stands, nothing is charged.
  const plainUid = fresh("viewer");
  await db.collection("users").doc(plainUid).set({ heartBalance: 30 });
  assert.match(await failureMessage(call(plainUid, { expectedDateKey: DATE_KEY })), /refresh_unavailable/);
  assert.equal((await db.collection("users").doc(plainUid).get()).get("heartBalance"), 30);
  assert.equal(
    (await db.collection("users").doc(plainUid).collection("recommendationRefreshes").get()).size,
    0,
  );

  // An entitlement in an unknown state is never treated as a purchase.
  const unknown = await seedPurchasedViewer(30, { status: "pending" });
  assert.match(await failureMessage(call(unknown.uid, { expectedDateKey: DATE_KEY })), /refresh_unavailable/);

  // A completed record that lost its identity is not invented from scratch.
  const hollow = await seedPurchasedViewer(30, { displayCandidateUids: [] });
  assert.match(await failureMessage(call(hollow.uid, { expectedDateKey: DATE_KEY })), /refresh_unavailable/);

  // Another day's purchase does not answer for the day the client asks about.
  const otherDay = await seedPurchasedViewer(30);
  assert.match(await failureMessage(call(otherDay.uid, { expectedDateKey: "20261121" })), /refresh_unavailable/);
});

test("AUD-25: the client-supplied date key is never used as a path", async () => {
  const { uid } = await seedPurchasedViewer(30);
  for (const hostile of [
    `${DATE_KEY}/../${DATE_KEY}`,
    `../recommendationRefreshes/${DATE_KEY}`,
    "2026-11-20",
    "20261120 ",
    "x".repeat(2000),
  ]) {
    // A trimmed "20261120 " is the valid key; every other shape is ignored
    // and the request ends in the ordinary refusal.
    const outcome = await failureMessage(call(uid, { expectedDateKey: hostile }));
    if (hostile.trim() === DATE_KEY) {
      assert.equal(outcome, "ok");
    } else {
      assert.match(outcome, /refresh_unavailable/, hostile.slice(0, 40));
    }
  }
});
