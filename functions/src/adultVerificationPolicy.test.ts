import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const indexSrc = readFileSync(resolve(__dirname, "../src/index.ts"), "utf8");

test("adult verification requires Korean year age 20 or older", () => {
  assert.match(indexSrc, /const MINIMUM_SERVICE_AGE = 20;/);
  assert.match(
    indexSrc,
    /return getKstFullYear\(now\) - birthYear >= MINIMUM_SERVICE_AGE;/
  );
});

test("real-name verification data is stored in a server-only collection", () => {
  assert.match(indexSrc, /collection\("userPrivateVerifications"\)/);
  assert.match(
    indexSrc,
    /name,\s*\n\s*phoneNumber,\s*\n\s*phoneHash: adult \? verifiedPhoneHash.*\n\s*birthDate,/,
  );
  assert.match(indexSrc, /phoneHash: adult \? verifiedPhoneHash/);
  assert.match(indexSrc, /verifiedPhoneHashIndexOwnerRef\(verifiedPhoneHash, uid\)/);
});

function adultVerificationCallable(): string {
  const start = indexSrc.indexOf("export const verifyAdultIdentityAfterLogin");
  assert.notEqual(start, -1);
  return indexSrc.slice(start, indexSrc.indexOf("\nexport const ", start + 1));
}

test("AUD-11: the duplicate-identity decision is made inside the verification transaction", () => {
  const callable = adultVerificationCallable();
  const txStart = callable.indexOf("await db.runTransaction(async (tx) => {");
  assert.notEqual(txStart, -1);
  const beforeTransaction = callable.slice(0, txStart);
  const transaction = callable.slice(txStart);

  // No lookup of another account's verification record outside the transaction.
  assert.doesNotMatch(beforeTransaction, /userPrivateVerifications"\)\s*\.where\(/);
  assert.doesNotMatch(indexSrc, /assertUniqueIdentityNotReused|assertIdentityVerificationNotReused/);
  // Claim planned (reads) before the first write, applied with the record.
  const plan = transaction.indexOf("await planAdultIdentityClaim(db, tx, {");
  const apply = transaction.indexOf("identityClaim.apply(tx);");
  const firstWrite = transaction.search(/tx\.(set|delete|update|create)\(/);
  assert.ok(plan !== -1 && apply !== -1 && firstWrite !== -1);
  assert.ok(plan < firstWrite, "the claim must be read before any write");
  assert.ok(apply < transaction.indexOf("tx.set(\n        privateRef"), "claim and record are written together");
  assert.match(transaction, /next: \{ ciHash, diHash, uniqueKeyHash, identityVerificationId \}/);
});

test("AUD-11: an incomplete verification cannot downgrade an account", () => {
  const callable = adultVerificationCallable();
  assert.doesNotMatch(callable, /adultVerified: false/, "no unconditional adultVerified:false write");
  assert.match(
    callable,
    /if \(status !== "VERIFIED"\) \{[\s\S]{0,400}?await recordIncompleteAdultVerification\(db, uid\);\s*throw new HttpsError\(/,
  );
});

test("AUD-11: identity values and the provider response are not logged", () => {
  const start = indexSrc.indexOf("async function fetchPortOneIdentityVerification(");
  const helper = indexSrc.slice(start, indexSrc.indexOf("\n}\n", start));
  assert.doesNotMatch(helper, /body: parsed|identityVerificationId,\n/);
  for (const call of adultVerificationCallable().match(/logger\.\w+\([\s\S]*?\);/g) ?? []) {
    assert.doesNotMatch(call, /\b(ci|di|customer|phoneNumber|birthDate|ciHash|diHash|uniqueKeyHash|uniqueKey|verifiedPhoneHash|identityVerificationId)\b/);
  }
  const ownership = readFileSync(resolve(__dirname, "../src/adultIdentityOwnership.ts"), "utf8");
  assert.doesNotMatch(ownership, /logger\.|console\./, "the ownership module logs nothing");
});

test("contact avoidance uses KG Inicis verification hashes, not Kakao phone data", () => {
  const contactStart = indexSrc.indexOf("export const syncContactBlocks");
  const contactEnd = indexSrc.indexOf(
    "// =============================================================================\n// syncKakaoTalkFriendBlocks",
    contactStart,
  );
  const contactCallable = indexSrc.slice(contactStart, contactEnd);

  assert.match(contactCallable, /collection\(VERIFIED_PHONE_HASH_INDEX\)/);
  assert.match(contactCallable, /markContactHashMatchedToUsers\(/);
  assert.match(indexSrc, /matchSource: "kg_inicis_verified_phone"/);
  assert.doesNotMatch(contactCallable, /phoneHashIndex/);
  assert.doesNotMatch(indexSrc, /saveUserPhoneHash/);
});
