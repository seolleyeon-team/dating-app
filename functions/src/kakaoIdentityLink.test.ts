import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import {
  decideKakaoCallerIdentity,
  decideKakaoIdentityLink,
  kakaoIdentityHash,
  resolveFriendExclusionAppUserIds,
} from "./kakaoIdentityLink";

// ============================================================================
// kakaoIdentityHash
// ============================================================================

test("kakaoIdentityHash is deterministic sha256 of the namespaced id", () => {
  const expected = createHash("sha256")
    .update("kakao_identity:4705828086", "utf8")
    .digest("hex");
  assert.equal(kakaoIdentityHash("4705828086"), expected);
  assert.equal(kakaoIdentityHash("4705828086"), kakaoIdentityHash("4705828086"));
  assert.match(kakaoIdentityHash("4705828086"), /^[0-9a-f]{64}$/);
  assert.notEqual(kakaoIdentityHash("1"), kakaoIdentityHash("2"));
  // The namespace prefix keeps this hash space disjoint from bare-id hashes.
  assert.notEqual(
    kakaoIdentityHash("4705828086"),
    createHash("sha256").update("4705828086", "utf8").digest("hex")
  );
});

// ============================================================================
// decideKakaoIdentityLink
// ============================================================================

const HASH = kakaoIdentityHash("999");

function decideLink(overrides: Partial<Parameters<
  typeof decideKakaoIdentityLink
>[0]> = {}) {
  return decideKakaoIdentityLink({
    authUid: "app_user_1",
    verifiedKakaoUserId: "999",
    identityHash: HASH,
    existingMappingData: null,
    legacyUserDocExists: false,
    userDocData: { isStudentVerified: true },
    ...overrides,
  });
}

test("linking requires a primary-email-authenticated, verified account", () => {
  assert.deepEqual(decideLink({ userDocData: null }), {
    ok: false,
    reason: "primary_email_auth_required",
  });
  assert.deepEqual(decideLink({ userDocData: { isStudentVerified: false } }), {
    ok: false,
    reason: "primary_email_auth_required",
  });
});

test("an unmapped identity links successfully", () => {
  assert.deepEqual(decideLink(), { ok: true, alreadyLinked: false });
});

test("relinking the same pair is idempotent", () => {
  assert.deepEqual(
    decideLink({ existingMappingData: { appUserId: "app_user_1" } }),
    { ok: true, alreadyLinked: true }
  );
});

test("a mapping owned by another appUserId is an identity conflict", () => {
  assert.deepEqual(
    decideLink({ existingMappingData: { appUserId: "app_user_2" } }),
    { ok: false, reason: "identity_conflict" }
  );
  // A structurally broken mapping also fails closed.
  assert.deepEqual(
    decideLink({ existingMappingData: { appUserId: "" } }),
    { ok: false, reason: "identity_conflict" }
  );
});

test("legacy collision: users/{kakaoUserId} owned by someone else blocks the link", () => {
  assert.deepEqual(decideLink({ legacyUserDocExists: true }), {
    ok: false,
    reason: "identity_conflict",
  });
});

test("a legacy-invariant account may link its own Kakao identity", () => {
  // authUid IS the Kakao id, so users/{kakaoUserId} is the caller's own doc.
  assert.deepEqual(
    decideLink({
      authUid: "999",
      legacyUserDocExists: true,
    }),
    { ok: true, alreadyLinked: false }
  );
});

test("an account already linked to a different Kakao identity requires explicit relink", () => {
  assert.deepEqual(
    decideLink({
      userDocData: {
        isStudentVerified: true,
        kakaoFriendConnection: {
          kakaoIdentityHash: kakaoIdentityHash("other"),
        },
      },
    }),
    { ok: false, reason: "relink_required" }
  );
  // Same stored hash is fine (idempotent relink of the doc bookkeeping).
  assert.deepEqual(
    decideLink({
      userDocData: {
        isStudentVerified: true,
        kakaoFriendConnection: { kakaoIdentityHash: HASH },
      },
    }),
    { ok: true, alreadyLinked: false }
  );
});

test("blank inputs never link", () => {
  assert.deepEqual(decideLink({ authUid: "" }), {
    ok: false,
    reason: "primary_email_auth_required",
  });
  assert.deepEqual(decideLink({ verifiedKakaoUserId: " " }), {
    ok: false,
    reason: "primary_email_auth_required",
  });
});

// ============================================================================
// decideKakaoCallerIdentity (contract §5 OR-chain)
// ============================================================================

test("legacy invariant: authUid equal to the verified Kakao id is accepted", () => {
  assert.deepEqual(
    decideKakaoCallerIdentity({
      authUid: "999",
      claimedKakaoUserId: null,
      verifiedKakaoUserId: "999",
      mappingAppUserId: null,
    }),
    { ok: true, appUserId: "999" }
  );
});

test("legacy claim naming the verified Kakao id is accepted", () => {
  assert.deepEqual(
    decideKakaoCallerIdentity({
      authUid: "emaillink_uid",
      claimedKakaoUserId: "999",
      verifiedKakaoUserId: "999",
      mappingAppUserId: null,
    }),
    { ok: true, appUserId: "999" }
  );
});

test("kakaoIdentities mapping bound to the caller resolves to the appUserId", () => {
  assert.deepEqual(
    decideKakaoCallerIdentity({
      authUid: "app_user_1",
      claimedKakaoUserId: null,
      verifiedKakaoUserId: "999",
      mappingAppUserId: "app_user_1",
    }),
    { ok: true, appUserId: "app_user_1" }
  );
});

test("everything else is rejected", () => {
  // No session at all.
  assert.deepEqual(
    decideKakaoCallerIdentity({
      authUid: null,
      claimedKakaoUserId: null,
      verifiedKakaoUserId: "999",
      mappingAppUserId: null,
    }),
    { ok: false }
  );
  // Mapping owned by a different account.
  assert.deepEqual(
    decideKakaoCallerIdentity({
      authUid: "app_user_1",
      claimedKakaoUserId: null,
      verifiedKakaoUserId: "999",
      mappingAppUserId: "app_user_2",
    }),
    { ok: false }
  );
  // Claim naming a different Kakao account.
  assert.deepEqual(
    decideKakaoCallerIdentity({
      authUid: "emaillink_uid",
      claimedKakaoUserId: "111",
      verifiedKakaoUserId: "999",
      mappingAppUserId: null,
    }),
    { ok: false }
  );
});

// ============================================================================
// resolveFriendExclusionAppUserIds (contract §5 friend -> member resolution)
// ============================================================================

function resolveFriends(
  candidates: Parameters<
    typeof resolveFriendExclusionAppUserIds
  >[0]["candidates"]
) {
  return resolveFriendExclusionAppUserIds({
    callerAppUserId: "app_user_1",
    callerKakaoUserId: "111",
    candidates,
  });
}

test("legacy friends resolve to their Kakao-keyed doc id", () => {
  const result = resolveFriends([
    { kakaoUserId: "222", legacyUserDocExists: true, mappingAppUserId: null },
  ]);
  assert.deepEqual(result.targetAppUserIds, ["222"]);
  assert.equal(result.matchedUserCount, 1);
});

test("new members resolve through the kakaoIdentities mapping (fail-open fix)", () => {
  const result = resolveFriends([
    {
      kakaoUserId: "333",
      legacyUserDocExists: false,
      mappingAppUserId: "email_member_7",
    },
  ]);
  assert.deepEqual(result.targetAppUserIds, ["email_member_7"]);
  assert.equal(result.matchedUserCount, 1);
});

test("friends who are not members match nothing", () => {
  const result = resolveFriends([
    { kakaoUserId: "444", legacyUserDocExists: false, mappingAppUserId: null },
  ]);
  assert.deepEqual(result.targetAppUserIds, []);
  assert.equal(result.matchedUserCount, 0);
});

test("the caller is skipped by Kakao id and by resolved appUserId", () => {
  const result = resolveFriends([
    { kakaoUserId: "111", legacyUserDocExists: true, mappingAppUserId: null },
    {
      kakaoUserId: "555",
      legacyUserDocExists: false,
      mappingAppUserId: "app_user_1",
    },
  ]);
  assert.deepEqual(result.targetAppUserIds, []);
  assert.equal(result.matchedUserCount, 0);
  assert.equal(result.skippedSelfCount, 2);
});

test("duplicate resolutions collapse and unsafe mapped ids are ignored", () => {
  const result = resolveFriends([
    { kakaoUserId: "222", legacyUserDocExists: true, mappingAppUserId: null },
    {
      kakaoUserId: "223",
      legacyUserDocExists: false,
      mappingAppUserId: "222",
    },
    {
      kakaoUserId: "224",
      legacyUserDocExists: false,
      mappingAppUserId: "not/a/safe/segment",
    },
    { kakaoUserId: "", legacyUserDocExists: true, mappingAppUserId: null },
  ]);
  assert.deepEqual(result.targetAppUserIds, ["222"]);
  assert.equal(result.matchedUserCount, 2);
});

test("a legacy doc takes precedence over a mapping for the same friend", () => {
  const result = resolveFriends([
    {
      kakaoUserId: "666",
      legacyUserDocExists: true,
      mappingAppUserId: "somebody_else",
    },
  ]);
  assert.deepEqual(result.targetAppUserIds, ["666"]);
});
