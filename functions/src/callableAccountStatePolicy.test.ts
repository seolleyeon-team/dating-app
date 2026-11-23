/**
 * NEW-24 — every HTTPS endpoint has a declared account-state policy, and the
 * gates implemented in this change are really in the source.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import {
  accountStateError,
  assertActiveAccountState,
  classifyAccountState,
  isActiveAccountData,
} from "./accountStatePolicy";
import {
  CALLABLE_ACCOUNT_STATE_POLICY,
  type CallableAccountGate,
} from "./callableAccountStatePolicy";
import { decidePrimaryEmailAccountResolution } from "./primaryEmailAuth";

process.env.GCLOUD_PROJECT ??= "demo-callable-policy";
// index.ts performs initializeApp(); loading it touches no network.
// eslint-disable-next-line @typescript-eslint/no-var-requires
const index = require("./index") as Record<string, unknown>;

const src = (name: string) => readFileSync(resolve(__dirname, "../src", name), "utf8");
const indexSource = src("index.ts");

type Endpoint = { callableTrigger?: unknown; httpsTrigger?: unknown };

function httpsEndpointNames(): string[] {
  return Object.entries(index)
    .filter(([, value]) => {
      if (typeof value !== "function") return false;
      const endpoint = (value as { __endpoint?: Endpoint }).__endpoint;
      return !!endpoint && (endpoint.callableTrigger !== undefined || endpoint.httpsTrigger !== undefined);
    })
    .map(([name]) => name)
    .sort();
}

test("account states are told apart the way the data model writes them", () => {
  assert.equal(classifyAccountState({}), "active");
  assert.equal(classifyAccountState({ status: "active", loginDisabled: false, isActive: true }), "active");
  // decideCommunityReport
  assert.equal(classifyAccountState({ status: "suspended", loginDisabled: true, isActive: false }), "suspended");
  assert.equal(classifyAccountState({ status: "banned", loginDisabled: true, isActive: false }), "banned");
  // lockAccountForDeletion (also when it overwrote a moderation status)
  assert.equal(classifyAccountState({ status: "deleting", isWithdrawn: true, loginDisabled: true }), "withdrawn");
  assert.equal(classifyAccountState({ status: "deleting", isWithdrawn: true, loginDisabled: true, isActive: false }), "withdrawn");
  // review fixtures / bare flags
  assert.equal(classifyAccountState({ loginDisabled: true }), "inactive");
  assert.equal(classifyAccountState({ isActive: false }), "inactive");
  // legacy vocabulary other modules still read
  assert.equal(classifyAccountState({ status: " Suspended " }), "suspended");
  assert.equal(classifyAccountState({ status: "blocked" }), "suspended");
  assert.equal(classifyAccountState({ isSuspended: true }), "suspended");
  assert.equal(classifyAccountState({ isBanned: true }), "banned");
  assert.equal(classifyAccountState({ accountStatus: "banned" }), "banned");
  assert.equal(classifyAccountState({ status: "withdrawn" }), "withdrawn");
  assert.equal(classifyAccountState({ status: "deleted" }), "withdrawn");
  assert.equal(classifyAccountState({ isDeleted: true }), "withdrawn");
  assert.equal(classifyAccountState({ isWithdrawn: true }), "withdrawn");
  assert.equal(classifyAccountState({ status: "restricted_rejoin" }), "inactive");
  // a restored account (restoreCommunityAccount keeps moderationActionType)
  assert.equal(
    classifyAccountState({ status: "active", loginDisabled: false, isActive: true, moderationActionType: "indefinite_suspension" }),
    "active",
  );
  // truthy look-alikes are not state
  assert.equal(classifyAccountState({ loginDisabled: "true", isWithdrawn: 1, isActive: null }), "active");
});

test("the refusal is permission-denied with a state detail and no moderation reason", () => {
  for (const state of ["suspended", "banned", "withdrawn", "inactive"] as const) {
    const error = accountStateError(state);
    assert.equal(error.code, "permission-denied");
    assert.deepEqual(error.details, { detail: `account_${state}` });
  }
  assert.match(accountStateError("suspended").message, /이용이 정지된 계정이에요/);
  assert.throws(
    () => assertActiveAccountState({ status: "banned", moderationActionReason: "secret reason" }),
    (error: unknown) => !JSON.stringify([(error as Error).message, (error as { details?: unknown }).details]).includes("secret reason"),
  );
  assert.doesNotThrow(() => assertActiveAccountState({ status: "active" }));
  assert.equal(isActiveAccountData(null), true);
});

test("every HTTPS endpoint exported from index.ts has a declared account-state policy", () => {
  const exported = httpsEndpointNames();
  assert.ok(exported.length >= 60, `expected the full callable surface, found ${exported.length}`);
  const declared = Object.keys(CALLABLE_ACCOUNT_STATE_POLICY).sort();
  const undeclared = exported.filter((name) => !declared.includes(name));
  const stale = declared.filter((name) => !exported.includes(name));
  assert.deepEqual(
    undeclared,
    [],
    "a callable without an entry in callableAccountStatePolicy.ts: decide whether a suspended / " +
      "banned / withdrawn account may call it and declare the gate",
  );
  assert.deepEqual(stale, [], "policy entries for exports that no longer exist");
  for (const [name, policy] of Object.entries(CALLABLE_ACCOUNT_STATE_POLICY)) {
    assert.ok(policy.reason.trim().length >= 10, `${name} needs a reason`);
  }
});

function exportStatement(name: string): string {
  const start = indexSource.search(new RegExp(`\\nexport const ${name}\\b`));
  assert.notEqual(start, -1, `${name} is not declared with "export const" in index.ts`);
  const next = indexSource.indexOf("\nexport const ", start + 1);
  return indexSource.slice(start, next === -1 ? undefined : next);
}

/** `export const x = factoryObject.member;` → the statement that built factoryObject. */
function wiring(name: string): string {
  const statement = exportStatement(name);
  const alias = /^\nexport const \w+\s*=\s*(\w+)\.\w+;/.exec(statement);
  if (!alias) return statement;
  const start = indexSource.indexOf(`\nconst ${alias[1]} = `);
  assert.notEqual(start, -1, `${alias[1]} is not built in index.ts`);
  return indexSource.slice(start, indexSource.indexOf("\nexport const ", start));
}

const SOURCE_MARKERS: Partial<Record<CallableAccountGate, RegExp>> = {
  app_user: /resolveAuthedAppUser|resolveCallableUserFirebaseOnly/,
  review_capable: /resolveReviewCapableAppUser/,
};

/** account_state gates whose check lives in the factory module, not index.ts. */
const ACCOUNT_STATE_MODULE: Record<string, [file: string, marker: RegExp]> = {
  linkKakaoFriendIdentity: ["kakaoIdentityLink.ts", /assertActiveAccountState\(/],
  completePrimaryStudentEmailAuth: ["primaryEmailAuth.ts", /!isActiveAccountData\(userData\)/],
  completeStudentEmailLink: ["emailLinkCompletion.ts", /assertActiveAccountState\(userData\)/],
  createKakaoFriendPairsOnce: [
    "kakaoFriendPairs.ts",
    /primary_email_auth_required"\);\s*\}\s*(?:\/\/.*\s*)*assertActiveAccountState\(userData\)/,
  ],
  setKakaoFriendAvoidanceEnabled: [
    "kakaoFriendPairs.ts",
    /assertActiveAccountState\(userData\);\s*const started = buildAvoidanceMutationStart/,
  ],
  meetingIcebreakerAction: [
    "meetingIcebreaker/functions.ts",
    /const uid = requireUid\(request\);\s*(?:\/\/.*\s*)*await requireActiveAccount\(db\(\), uid\)/,
  ],
  submitSafetyStamp: [
    "safetyStamp.ts",
    /export const submitSafetyStamp = onCall\([\s\S]{0,400}?await requireActiveAccount\(db\(\), uid\)/,
  ],
  submitSafetyStampFollowUp: [
    "safetyStamp.ts",
    /export const submitSafetyStampFollowUp = onCall\([\s\S]{0,400}?await requireActiveAccount\(db\(\), uid\)/,
  ],
};

test("declared gates are in the source", () => {
  for (const [name, policy] of Object.entries(CALLABLE_ACCOUNT_STATE_POLICY)) {
    const marker = SOURCE_MARKERS[policy.gate];
    if (marker) {
      assert.match(wiring(name), marker, `${name} is declared ${policy.gate} but is not wired to that resolver`);
    } else if (policy.gate === "account_state") {
      const external = ACCOUNT_STATE_MODULE[name];
      if (external) {
        assert.match(src(external[0]), external[1], `${name}: ${external[0]} lost its account-state check`);
      } else {
        assert.match(
          exportStatement(name),
          /assertActiveAccountState\(|requireActiveAccount\(|requireAdultVerificationAccount\(/,
          `${name} is declared account_state but its handler has no account-state check`,
        );
      }
    }
  }
});

test("the shared resolvers apply the shared classifier", () => {
  const resolverStart = indexSource.indexOf("async function resolveAuthedAppUser(");
  const resolver = indexSource.slice(resolverStart, indexSource.indexOf("\n}\n", resolverStart));
  assert.match(resolver, /assertActiveAccountState\(data\);/);
  // The state check precedes the student-verification postcondition, so a
  // suspended account is told it is suspended, not asked to re-verify.
  assert.ok(resolver.indexOf("assertActiveAccountState(data)") < resolver.indexOf("isStudentVerified"));
  assert.doesNotMatch(resolver, /auth\?\.token|token\./, "account state must never be read from the ID token");

  const reviewStart = indexSource.indexOf("async function resolveReviewCapableAppUser(");
  const review = indexSource.slice(reviewStart, indexSource.indexOf("\n}\n", reviewStart));
  assert.match(review, /return resolveAuthedAppUser\(auth\);/);

  const play = src("playReviewAccess.ts");
  const playStart = play.indexOf("export async function resolvePlayReviewUser(");
  assert.match(play.slice(playStart, play.indexOf("\n}\n", playStart)), /assertActiveAccountState\(data\);/);
});

test("account deletion stays an owner-lifecycle action for every account state", () => {
  const deletion = src("accountDeletionAuthorization.ts");
  assert.doesNotMatch(deletion, /accountStatePolicy|assertActiveAccountState|loginDisabled/);
});

test("primary email sign-in: no restricted state re-enters, in any spelling", () => {
  const decide = (userData: Record<string, unknown>) =>
    decidePrimaryEmailAccountResolution({
      authUid: "email-link-uid",
      normalizedEmail: "a@yonsei.ac.kr",
      bindingData: { appUserId: "app-1", status: "confirmed" },
      bindingUserData: { studentEmail: "a@yonsei.ac.kr", isStudentVerified: true, ...userData },
      legacyCandidates: [],
    });
  assert.equal(decide({}).ok, true);
  assert.equal(decide({ status: "active", isActive: true, loginDisabled: false }).ok, true);
  for (const restricted of [
    { status: "suspended" },
    { status: "banned" },
    { status: "deleting" },
    { isWithdrawn: true },
    { loginDisabled: true },
    // newly covered by the shared classifier
    { isActive: false },
    { status: "Suspended" },
    { status: "deleted" },
    { isBanned: true },
    { isSuspended: true },
    { isDeleted: true },
  ]) {
    const decision = decide(restricted);
    assert.deepEqual(decision, { ok: false, reason: "rejoin_restricted" }, JSON.stringify(restricted));
  }
});
