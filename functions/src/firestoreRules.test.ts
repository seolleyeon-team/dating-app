import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const rules = readFileSync(resolve(__dirname, "../../firestore.rules"), "utf8");
const compactRules = rules.replace(/\s+/g, " ");


type FirestoreIndexField = {
  fieldPath: string;
  order?: string;
  arrayConfig?: string;
};

type FirestoreIndex = {
  collectionGroup: string;
  queryScope: string;
  fields: FirestoreIndexField[];
};

function assertHasIndex(expectedFields: FirestoreIndexField[]): void {
  const config = JSON.parse(
    readFileSync(resolve(__dirname, "../../firestore.indexes.json"), "utf8")
  ) as { indexes?: FirestoreIndex[] };
  const indexes = config.indexes ?? [];
  assert.ok(
    indexes.some(
      (index) =>
        index.collectionGroup === "eventTeamMeetingRequests" &&
        index.queryScope === "COLLECTION" &&
        JSON.stringify(index.fields) === JSON.stringify(expectedFields)
    ),
    `missing eventTeamMeetingRequests index ${JSON.stringify(expectedFields)}`
  );
}
function assertContains(description: string, expected: string): void {
  assert.match(
    compactRules,
    new RegExp(expected.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+")),
    description
  );
}

test("owner private collections and app feedback rules fail closed", () => {
  assertContains(
    "device tokens must be owner-scoped with token/doc binding",
    "match /deviceTokens/{token} { allow get, list: if isSelf(kakaoUserId); allow create, update: if isSelf(kakaoUserId) && request.resource.data.userId is string && request.resource.data.userId == kakaoUserId && request.resource.data.token is string && request.resource.data.token == token; allow delete: if isSelf(kakaoUserId); }"
  );
  assertContains(
    "notifications must be owner-readable and client read-status only",
    "match /notifications/{notificationId} { allow get, list: if isSelf(kakaoUserId); allow create: if false; allow update: if isSelf(kakaoUserId) && request.resource.data.diff(resource.data).changedKeys().hasOnly([ 'isRead', 'readAt' ]); allow delete: if false; }"
  );
  assertContains(
    "issue reports must be authenticated owner-bound create only",
    "match /app_issue_reports/{reportId} { allow create: if isSignedIn() && request.resource.data.reporterId is string && request.resource.data.reporterId == request.auth.uid"
  );
  assertContains(
    "inquiries must be authenticated owner-bound create only",
    "match /app_inquiries/{inquiryId} { allow create: if isSignedIn() && request.resource.data.inquirerId is string && request.resource.data.inquirerId == request.auth.uid"
  );
});

test("blocks and user reports are server-written only", () => {
  // Clients used to write a one-directional block; that left the reporter
  // visible to the person they reported. Writes now go through
  // reportAndBlockUser / syncContactBlocks.
  assertContains(
    "block docs must deny client create/update",
    "match /blocks/{viewerUid} { allow read: if isSelf(viewerUid); allow create, update: if false; allow delete: if isSelf(viewerUid);"
  );
  assertContains(
    "block targets must deny client create/update",
    "match /targets/{targetUid} { allow read: if isSelf(viewerUid); allow create, update: if false; allow delete: if isSelf(viewerUid);"
  );
  assertContains(
    "user reports must deny every client operation",
    "match /reports/{reportId} { allow create: if false; allow read: if false; allow update: if false; allow delete: if false; }"
  );
});


test("festival avatar buckets keep private media out of public user docs", () => {
  for (const forbiddenBucket of [
    "seolleyeon-festival-private-source-photos",
    "seolleyeon-festival-avatar-temp",
    "seolleyeon-festival-chat-profile-photos",
  ]) {
    assertContains(
      `${forbiddenBucket} must be blocked by public media URL validation`,
      `!value.lower().matches('.*${forbiddenBucket}.*')`
    );
  }

  assertContains(
    "festival approved avatar storage paths must be valid display refs",
    "value.matches('^gs://seolleyeon-festival-approved-avatars/users/[^/]+/avatar/[^/]+$')"
  );
});

test("festival storage buckets preserve intended client-read boundaries", () => {
  const storageRules = readFileSync(resolve(__dirname, "../../storage.rules"), "utf8");
  const compactStorageRules = storageRules.replace(/\s+/g, " ");

  assert.match(
    compactStorageRules,
    /bucket == "seolleyeon-festival-approved-avatars"/,
    "festival approved avatars must be part of the approved public-read bucket set"
  );
  assert.match(
    compactStorageRules,
    /match \/users\/\{userId\}\/avatar\/\{avatarId\} \{ allow read: if isApprovedAvatarBucket\(\); allow write: if false; \}/,
    "approved avatar objects must be client-readable only in approved avatar buckets"
  );
  assert.match(
    compactStorageRules,
    /match \/users\/\{userId\}\/source\/\{fileName\} \{ allow read, write: if false; \}/,
    "private source objects must stay client-denied"
  );
  assert.match(
    compactStorageRules,
    /match \/users\/\{userId\}\/chat-profile\/\{fileName\} \{ allow read, write: if false; \}/,
    "chat profile objects must stay backend-authorized only"
  );
  assert.match(
    compactStorageRules,
    /match \/avatar_temp\/\{userId\}\/\{allPaths=\*\*\} \{ allow read, write: if false; \}/,
    "avatar temp objects must stay client-denied"
  );
});
test("matching and recommendation rules are participant or owner scoped", () => {
  assertContains(
    "model recs must be readable only by the target user",
    "match /modelRecs/{userId}/daily/{dateKey}/sources/{algo} { allow read: if isSelf(userId); allow write: if false; }"
  );
  assertContains(
    "asks must be participant-readable and recipient can only mark read",
    "match /asks/{askId} { allow read: if isAskParticipant(resource.data); allow create: if isSignedIn() && request.resource.data.fromUserId is string && request.resource.data.fromUserId == request.auth.uid"
  );
  assertContains(
    "interactions must be participant-readable and from-user-bound create only",
    "match /interactions/{interactionId} { allow read: if isInteractionParticipant(resource.data); allow create: if isSignedIn() && request.resource.data.fromUserId is string && request.resource.data.fromUserId == request.auth.uid"
  );
  assertContains(
    "matches must be participant-readable and backend-created",
    "match /matches/{matchId} { allow read: if isMatchParticipant(resource.data); allow create: if false;"
  );
  assertContains(
    "matches can only be unmatched by a participant",
    "allow update: if isMatchParticipant(resource.data) && matchStatusOnlyMovesToUnmatched(); allow delete: if false;"
  );
});

test("event team setup and invite reads are participant scoped", () => {
  assertContains(
    "event team setups must be visible only to accepted or pending participants",
    "match /eventTeamSetups/{teamSetupId} { allow read: if isEventTeamSetupParticipant(resource.data); allow write: if false; }"
  );
  assertContains(
    "event team invites must be visible only to inviter or invitee",
    "match /eventTeamInvites/{inviteId} { allow read: if isEventTeamInviteParticipant(resource.data); allow write: if false; }"
  );
});

test("event team match results are participant-scoped and locks are fully private", () => {
  assertContains(
    "event team match results must be readable only by participantUids",
    "match /eventTeamMatches/{matchId} { allow read: if isEventTeamMatchParticipant(resource.data); allow write: if false; }"
  );
  assertContains(
    "event team match locks must deny every client operation",
    "match /eventTeamMatchLocks/{lockId} { allow read, write: if false; }"
  );
  assertContains(
    "team meeting requests must be participant-readable and backend-written",
    "match /eventTeamMeetingRequests/{requestId} { allow read: if isEventTeamMatchParticipant(resource.data); allow write: if false; }"
  );
  assertContains(
    "three-vs-three matches must be participant-readable and backend-written",
    "match /eventThreeVsThreeMatches/{matchId} { allow read: if isEventTeamMatchParticipant(resource.data); allow write: if false; }"
  );
});

test("chat rooms keep participantIds immutable and message updates scoped", () => {
  assertContains(
    "chat room updates must keep participantIds unchanged",
    "allow update: if isChatRoomParticipant() && isChatRoomParticipantAfter() && chatRoomParticipantIdsUnchanged() && chatRoomDoesNotPersistPrivateMedia(request.resource.data);"
  );
  assertContains(
    "chat message updates must go through canUpdateChatMessage",
    "match /messages/{messageId} { allow read: if isExistingChatRoomParticipant(roomId); allow create: if isParticipantMessageAuthor(roomId); allow update: if canUpdateChatMessage(roomId); allow delete: if false; }"
  );
  assertContains(
    "plain text messages cannot be rewritten except for read receipts",
    "function onlyMessageReadReceiptUpdate() { return request.resource.data.diff(resource.data).affectedKeys() .hasOnly(['readBy', 'updatedAt']); }"
  );
});

test("recEvents are append-only with a typed whitelist", () => {
  assertContains(
    "recEvent creates must pass isValidRecEventCreate",
    "allow create: if isSelf(userId) && isValidRecEventCreate(userId);"
  );
  assertContains(
    "recEvent updates and deletes are denied",
    "allow update, delete: if false;"
  );
  assertContains(
    "recEvent types are limited to the app vocabulary",
    "function isAllowedRecEventType(eventType) { return eventType in [ 'impression', 'open', 'detail_open', 'view', 'like', 'nope', 'super_like', 'swipe_right', 'block', 'report' ]; }"
  );
});

test("team meeting request service uses callables for backend-owned writes", () => {
  const service = readFileSync(
    resolve(__dirname, "../../lib/services/team_meeting_request_service.dart"),
    "utf8"
  );

  assert.match(service, /httpsCallable\('createTeamMeetingRequest'\)/);
  assert.match(service, /httpsCallable\('respondTeamMeetingRequest'\)/);
  assert.doesNotMatch(service, /\.collection\(_requestsCollection\)\.doc\(\)\s*;[\s\S]*?\.set\s*\(/);
  assert.doesNotMatch(service, /runTransaction/);
  assert.doesNotMatch(service, /\.collection\(_matchesCollection\)\.doc\(\)/);
});

test("interaction service does not create matches from the client", () => {
  const service = readFileSync(
    resolve(__dirname, "../../lib/services/interaction_service.dart"),
    "utf8"
  );

  assert.doesNotMatch(service, /_matchesRef\.add\s*\(/);
  assert.doesNotMatch(service, /collection\(['"]matches['"]\)\.add\s*\(/);
});
test("team meeting request query indexes are declared", () => {
  assertHasIndex([
    { fieldPath: "participantUids", arrayConfig: "CONTAINS" },
    { fieldPath: "toTeamId", order: "ASCENDING" },
    { fieldPath: "createdAt", order: "DESCENDING" },
  ]);
  assertHasIndex([
    { fieldPath: "participantUids", arrayConfig: "CONTAINS" },
    { fieldPath: "fromTeamId", order: "ASCENDING" },
    { fieldPath: "createdAt", order: "DESCENDING" },
  ]);
  assertHasIndex([
    { fieldPath: "participantUids", arrayConfig: "CONTAINS" },
    { fieldPath: "toTeamId", order: "ASCENDING" },
    { fieldPath: "status", order: "ASCENDING" },
  ]);
});

test("team meeting request service maps function errors to fixed safe messages", () => {
  const service = readFileSync(
    resolve(__dirname, "../../lib/services/team_meeting_request_service.dart"),
    "utf8"
  );
  const mapperStart = service.indexOf("String _functionsErrorMessage");
  assert.notEqual(mapperStart, -1);
  const mapper = service.slice(mapperStart);

  assert.doesNotMatch(mapper, /return\s+message\s*;/);
  assert.doesNotMatch(mapper, /error\.message[^;]*\?\?/);
  assert.match(mapper, /case 'invalid-argument':/);
  assert.match(mapper, /case 'already-exists':/);
});
