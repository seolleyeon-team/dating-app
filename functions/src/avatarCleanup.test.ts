import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  CLEANUP_AVATAR_MEDIA_CALLABLE_OPTIONS,
  accountDeletionDocsFromParts,
  executeAvatarCleanup,
  isBlocksTargetRefPath,
  isUidBoundCleanupRef,
  planAccountDeletionPiiOperations,
  requireAvatarCleanupRequest,
  type CleanupExecutor,
  type CleanupOperation,
} from "./avatarCleanup";

const zeroAccountDeletionCounts = {
  userPrivateDeleted: 0,
  phoneHashIndexDeleted: 0,
  deviceTokensDeleted: 0,
  notificationsDeleted: 0,
  contactBlockedHashesDeleted: 0,
  contactBlockedHashIndexOwnersDeleted: 0,
  blockTargetsDeleted: 0,
  reverseBlockTargetsDeleted: 0,
  interactionsDeleted: 0,
  asksDeleted: 0,
  friendshipsDeleted: 0,
  friendEdgesDeleted: 0,
  matchesEnded: 0,
  chatRoomsClosed: 0,
  recEventsDeleted: 0,
  bambooPostsSoftDeleted: 0,
  friendInvitesScrubbed: 0,
  eventTeamMembershipsRemoved: 0,
};

function sampleExecutor() {
  const operations: CleanupOperation[] = [];
  const executor: CleanupExecutor = {
    async load() {
      return {
        userData: {
          avatar: {
            approvedAvatarStoragePath:
              "gs://seolleyeon-approved-avatars/users/u1/avatar/avatar_1.png",
            approvedAvatarUrl: "https://cdn.example/avatar.png",
          },
          onboarding: { avatarUrls: ["https://cdn.example/avatar.png"] },
        },
        privateMediaData: {
          sourcePhotos: [
            {
              gcsUri:
                "gs://seolleyeon-private-source-photos/users/u1/source/src_1.jpg",
            },
            {
              gcsUri:
                "gs://seolleyeon-private-source-photos/users/u2/source/src_2.jpg",
            },
          ],
          chatRealPhoto: {
            gcsUri:
              "gs://seolleyeon-chat-profile-photos/users/u1/chat-profile/src_1.jpg",
          },
        },
        candidateDocs: [
          {
            id: "cand_1",
            data: {
              uid: "u1",
              imageRef:
                "gs://seolleyeon-avatar-temp/users/u1/candidates/cand_1.png",
            },
          },
        ],
        jobDocs: [
          { id: "job_queued", data: { uid: "u1", status: "queued" } },
          { id: "job_done", data: { uid: "u1", status: "completed" } },
        ],
        existingRequest: null,
        accountDeletionDocs: accountDeletionDocsFromParts(),
      };
    },
    async apply(operation) {
      operations.push(operation);
    },
  };
  return { executor, operations };
}

test("cleanup callable enforces App Check", () => {
  assert.equal(CLEANUP_AVATAR_MEDIA_CALLABLE_OPTIONS.enforceAppCheck, true);
});

test("cleanup request validation requires explicit allowed reason and idempotency key", () => {
  assert.deepEqual(
    requireAvatarCleanupRequest({
      reason: "consent_withdrawal",
      clientRequestId: "cleanup_123",
    }),
    { reason: "consent_withdrawal", clientRequestId: "cleanup_123" },
  );
  assert.throws(
    () =>
      requireAvatarCleanupRequest({
        reason: "admin_delete",
        clientRequestId: "cleanup_123",
      }),
    /avatar_cleanup_reason_invalid/,
  );
  assert.throws(
    () =>
      requireAvatarCleanupRequest({
        reason: "account_deletion",
        clientRequestId: "short",
      }),
    /avatar_cleanup_request_invalid/,
  );
});

test("cleanup deletes only UID-bound allowlisted object refs", () => {
  assert.equal(
    isUidBoundCleanupRef(
      {
        bucket: "seolleyeon-private-source-photos",
        path: "users/u1/source/src.jpg",
      },
      "u1",
    ),
    true,
  );
  assert.equal(
    isUidBoundCleanupRef(
      {
        bucket: "seolleyeon-private-source-photos",
        path: "users/u2/source/src.jpg",
      },
      "u1",
    ),
    false,
  );
  assert.equal(
    isUidBoundCleanupRef(
      {
        bucket: "public",
        path: "users/u1/source/src.jpg",
      },
      "u1",
    ),
    false,
  );
});

test("cleanup marks pending before destructive work and returns sanitized counts", async () => {
  const { executor, operations } = sampleExecutor();
  const response = await executeAvatarCleanup({
    uid: "u1",
    clientRequestId: "cleanup_123",
    reason: "consent_withdrawal",
    executor,
  });

  assert.equal(operations[0].kind, "markPending");
  assert.equal(operations.some((op) => op.kind === "deleteStorage"), true);
  assert.equal(
    operations.findIndex((op) => op.kind === "markPending") <
      operations.findIndex((op) => op.kind === "deleteStorage"),
    true,
  );
  assert.deepEqual(response, {
    status: "completed",
    counts: {
      storageObjectsDeleted: 4,
      candidatesSanitized: 1,
      jobsCancelled: 1,
      privateMediaSanitized: 1,
      usersSanitized: 1,
      clipEmbeddingsDeleted: 1,
      cleanupRequestsUpdated: 1,
      publicUsersDeleted: 0,
      authUsersDeleted: 0,
      skippedUnsafeRefs: 1,
      ...zeroAccountDeletionCounts,
    },
  });
  assert.equal(JSON.stringify(response).includes("gs://"), false);
  assert.equal(JSON.stringify(response).includes("users/u1"), false);
});

test("cleanup audit operation is sanitized", async () => {
  const { executor, operations } = sampleExecutor();
  await executeAvatarCleanup({
    uid: "u1",
    clientRequestId: "cleanup_123",
    reason: "consent_withdrawal",
    executor,
  });
  const audit = operations.find((op) => op.kind === "writeAudit");
  assert.ok(audit);
  assert.equal(JSON.stringify(audit).includes("u1"), false);
  assert.equal(JSON.stringify(audit).includes("gs://"), false);
});

test("cleanup logger calls do not include raw error messages", () => {
  const source = readFileSync("src/avatarCleanup.ts", "utf8");
  assert.equal(
    source.includes("error: error instanceof Error ? error.message : String(error)"),
    false,
  );
  assert.match(source, /safeErrorLogFields\(error\)/);
});

test("completed cleanup request is idempotent and does not repeat destructive work", async () => {
  const operations: CleanupOperation[] = [];
  const executor: CleanupExecutor = {
    async load() {
      return {
        userData: {},
        privateMediaData: {},
        candidateDocs: [],
        jobDocs: [],
        existingRequest: {
          status: "completed",
          reason: "consent_withdrawal",
          response: {
            counts: {
              storageObjectsDeleted: 2,
            },
          },
        },
        accountDeletionDocs: accountDeletionDocsFromParts(),
      };
    },
    async apply(operation) {
      operations.push(operation);
    },
  };

  const response = await executeAvatarCleanup({
    uid: "u1",
    clientRequestId: "cleanup_123",
    reason: "consent_withdrawal",
    executor,
  });

  assert.equal(response.counts.storageObjectsDeleted, 2);
  assert.deepEqual(operations, []);
});

test("partial cleanup failure remains retryable for the same request id", async () => {
  let attempt = 0;
  const appliedByAttempt: CleanupOperation[][] = [];
  const executor: CleanupExecutor = {
    async load() {
      return {
        userData: {},
        privateMediaData: {
          sourcePhotos: [
            {
              gcsUri:
                "gs://seolleyeon-private-source-photos/users/u1/source/src_1.jpg",
            },
          ],
        },
        candidateDocs: [],
        jobDocs: [],
        existingRequest:
          attempt === 0
            ? null
            : { status: "pending", reason: "consent_withdrawal" },
        accountDeletionDocs: accountDeletionDocsFromParts(),
      };
    },
    async apply(operation) {
      appliedByAttempt[attempt] ??= [];
      appliedByAttempt[attempt].push(operation);
      if (attempt === 0 && operation.kind === "deleteStorage") {
        throw new Error("storage failed");
      }
    },
  };

  await assert.rejects(
    executeAvatarCleanup({
      uid: "u1",
      clientRequestId: "cleanup_123",
      reason: "consent_withdrawal",
      executor,
    }),
    /storage failed/,
  );
  attempt = 1;
  const response = await executeAvatarCleanup({
    uid: "u1",
    clientRequestId: "cleanup_123",
    reason: "consent_withdrawal",
    executor,
  });

  assert.equal(appliedByAttempt[0][0].kind, "markPending");
  assert.equal(appliedByAttempt[1][0].kind, "markPending");
  assert.equal(response.status, "completed");
});

test("account deletion removes public user and auth only after cleanup/audit", async () => {
  const { executor, operations } = sampleExecutor();
  await executeAvatarCleanup({
    uid: "u1",
    clientRequestId: "cleanup_123",
    reason: "account_deletion",
    executor,
  });

  const deletePublicUserIndex = operations.findIndex(
    (op) => op.kind === "deletePublicUser",
  );
  const deleteAuthUserIndex = operations.findIndex(
    (op) => op.kind === "deleteAuthUser",
  );
  const auditIndex = operations.findIndex((op) => op.kind === "writeAudit");
  const deleteUserPrivateIndex = operations.findIndex(
    (op) => op.kind === "deleteUserPrivate",
  );
  assert.equal(auditIndex < deleteUserPrivateIndex, true);
  assert.equal(deleteUserPrivateIndex < deletePublicUserIndex, true);
  assert.equal(auditIndex < deletePublicUserIndex, true);
  assert.equal(deletePublicUserIndex < deleteAuthUserIndex, true);
  assert.equal(operations.at(-1)?.kind, "markCompleted");
});

test("account deletion plans scoped PII cleanup operations", () => {
  const docs = accountDeletionDocsFromParts({
    phoneHash: "abc123def456",
    deviceTokenIds: ["token_a", "token_b"],
    notificationIds: ["notif_1"],
    contactBlockedHashIds: ["hash_1"],
    blockTargetIds: ["blocked_u2"],
    reverseBlockViewerUids: ["blocker_u3", "u1"],
  });

  const operations = planAccountDeletionPiiOperations({ uid: "u1", docs });

  assert.deepEqual(operations, [
    { kind: "deleteDeviceToken", tokenId: "token_a" },
    { kind: "deleteDeviceToken", tokenId: "token_b" },
    { kind: "deleteNotification", notificationId: "notif_1" },
    { kind: "deleteContactBlockedHash", phoneHash: "hash_1" },
    { kind: "deleteContactBlockedHashIndexOwner", phoneHash: "hash_1" },
    { kind: "deletePhoneHashIndex", phoneHash: "abc123def456" },
    { kind: "deleteUserPrivate" },
    { kind: "deleteBlockTarget", targetUid: "blocked_u2" },
    { kind: "deleteReverseBlockTarget", viewerUid: "blocker_u3" },
  ]);
});

test("reverse block cleanup only accepts blocks target paths", () => {
  assert.equal(
    isBlocksTargetRefPath("blocks/viewer_u3/targets/u1", "u1"),
    true,
  );
  assert.equal(
    isBlocksTargetRefPath("other/viewer_u3/targets/u1", "u1"),
    false,
  );
});

test("account deletion includes PII cleanup counts and skips PII for consent withdrawal", async () => {
  const accountDeletionExecutor: CleanupExecutor = {
    async load() {
      return {
        userData: {},
        privateMediaData: {},
        candidateDocs: [],
        jobDocs: [],
        existingRequest: null,
        accountDeletionDocs: accountDeletionDocsFromParts({
          phoneHash: "phone_hash_1",
          deviceTokenIds: ["token_1"],
          notificationIds: ["notif_1"],
          contactBlockedHashIds: ["cb_hash_1"],
          blockTargetIds: ["target_1"],
          reverseBlockViewerUids: ["viewer_1"],
        }),
      };
    },
    async apply() {},
  };

  const deletionResponse = await executeAvatarCleanup({
    uid: "u1",
    clientRequestId: "cleanup_123",
    reason: "account_deletion",
    executor: accountDeletionExecutor,
  });

  assert.deepEqual(deletionResponse.counts, {
    storageObjectsDeleted: 0,
    candidatesSanitized: 0,
    jobsCancelled: 0,
    privateMediaSanitized: 1,
    usersSanitized: 1,
    clipEmbeddingsDeleted: 1,
    cleanupRequestsUpdated: 1,
    publicUsersDeleted: 1,
    authUsersDeleted: 1,
    skippedUnsafeRefs: 0,
    userPrivateDeleted: 1,
    phoneHashIndexDeleted: 1,
    deviceTokensDeleted: 1,
    notificationsDeleted: 1,
    contactBlockedHashesDeleted: 1,
    contactBlockedHashIndexOwnersDeleted: 1,
    blockTargetsDeleted: 1,
    reverseBlockTargetsDeleted: 1,
    interactionsDeleted: 0,
    asksDeleted: 0,
    friendshipsDeleted: 0,
    friendEdgesDeleted: 0,
    matchesEnded: 0,
    chatRoomsClosed: 0,
    recEventsDeleted: 0,
    bambooPostsSoftDeleted: 0,
    friendInvitesScrubbed: 0,
    eventTeamMembershipsRemoved: 0,
  });

  const { executor, operations } = sampleExecutor();
  const consentResponse = await executeAvatarCleanup({
    uid: "u1",
    clientRequestId: "cleanup_456",
    reason: "consent_withdrawal",
    executor,
  });
  assert.deepEqual(consentResponse.counts, {
    storageObjectsDeleted: 4,
    candidatesSanitized: 1,
    jobsCancelled: 1,
    privateMediaSanitized: 1,
    usersSanitized: 1,
    clipEmbeddingsDeleted: 1,
    cleanupRequestsUpdated: 1,
    publicUsersDeleted: 0,
    authUsersDeleted: 0,
    skippedUnsafeRefs: 1,
    ...zeroAccountDeletionCounts,
  });
  assert.equal(
    operations.some((op) => op.kind === "deleteUserPrivate"),
    false,
  );
});
