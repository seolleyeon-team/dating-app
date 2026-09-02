import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

/**
 * F9 (terms-gate-contract §0/§8, identity-contract §7).
 *
 * `resolveAuthedAppUser` used to fall back to
 * `users.where("studentEmail","==", token.email).limit(1)` whenever
 * `users/{request.auth.uid}` did not exist, WITHOUT ever checking
 * `email_verified`. That turned an arbitrary Firebase session carrying an
 * `@yonsei.ac.kr` email claim into the canonical owner of somebody else's
 * account across 20+ privileged callables (grantPurchasedHearts, spendHearts,
 * unlockDirectChat, friend invites, avatar/onboarding photo, season-meeting
 * deposit/cancel/no-show/replacement/refund).
 *
 * Per identity-contract §7 the email -> appUserId resolution belongs SOLELY
 * inside primary-auth completion (`completePrimaryStudentEmailAuth`), which
 * consumes a single-use, server-written `emailLinkTokens` document inside a
 * transaction. A session whose own `users/{uid}` document does not exist is
 * not a canonical session and must be rejected.
 *
 * This is a source-contract test: `resolveAuthedAppUser` and
 * `emailFromAuthToken` are module-private to `index.ts`, and importing
 * `index.ts` would boot the whole Functions runtime.
 */
const indexSource = readFileSync(resolve(__dirname, "../src/index.ts"), "utf8");
const compactIndex = indexSource.replace(/\s+/g, " ");

function resolverBody(): string {
  const start = indexSource.indexOf("async function resolveAuthedAppUser(");
  assert.notEqual(start, -1, "resolveAuthedAppUser must exist in index.ts");
  // The next top-level `function ` declaration terminates the body.
  const end = indexSource.indexOf("\nfunction ", start);
  assert.notEqual(end, -1, "could not delimit resolveAuthedAppUser");
  return indexSource.slice(start, end);
}

test("F9: resolveAuthedAppUser never resolves a user from an email claim", () => {
  const body = resolverBody();

  assert.doesNotMatch(
    body,
    /where\(\s*"studentEmail"/,
    "resolveAuthedAppUser must not look a user up by studentEmail — the " +
      "email -> appUserId resolution belongs to completePrimaryStudentEmailAuth " +
      "(identity-contract §7)"
  );
  assert.doesNotMatch(
    body,
    /\.where\(/,
    "resolveAuthedAppUser must resolve users/{auth.uid} by document id only, " +
      "never by query"
  );
  // `studentEmail` may still be READ off the already-resolved document (the
  // verified-student postcondition) — it must never be a lookup KEY.
  assert.doesNotMatch(
    body,
    /\.limit\(/,
    "resolveAuthedAppUser must not run any collection query"
  );
  assert.doesNotMatch(
    body,
    /emailFromAuthToken|token\.email/,
    "resolveAuthedAppUser must not read the email claim at all"
  );
});

test("F9: resolveAuthedAppUser resolves strictly by users/{request.auth.uid}", () => {
  const body = resolverBody().replace(/\s+/g, " ");

  assert.match(
    body,
    /const doc = await db\.collection\("users"\)\.doc\(authUid\)\.get\(\);/,
    "the only lookup must be users/{authUid} by document id"
  );
  assert.match(
    body,
    /if \(!doc\.exists\) \{ throw new HttpsError\( "failed-precondition"/,
    "a session without its own users/{uid} document must be rejected outright"
  );
  // The verified-student postcondition must survive the change.
  assert.match(
    body,
    /if \(!isStudentVerified \|\| !studentEmail\.endsWith\("@yonsei\.ac\.kr"\)\)/,
    "the student-verification postcondition must remain"
  );
});

test("F9: the dead emailFromAuthToken helper is gone (no second email-claim path)", () => {
  assert.doesNotMatch(
    compactIndex,
    /function emailFromAuthToken\(/,
    "emailFromAuthToken existed only to feed the removed fallback; leaving it " +
      "invites a second unverified email-claim resolution path"
  );
});

test("F9: verifiedYonseiEmailFromAuthToken still enforces email_verified", () => {
  // The ONE legitimate email-claim reader must keep its email_verified gate.
  // It is intentionally untouched by this fix.
  const start = indexSource.indexOf("function verifiedYonseiEmailFromAuthToken(");
  assert.notEqual(start, -1, "verifiedYonseiEmailFromAuthToken must still exist");
  const body = indexSource.slice(start, start + 800).replace(/\s+/g, " ");

  assert.match(
    body,
    /if \(token\.email_verified !== true\) return null;/,
    "verifiedYonseiEmailFromAuthToken must require a verified mailbox claim"
  );
});
