"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_fs_1 = require("node:fs");
const node_path_1 = require("node:path");
const node_test_1 = __importDefault(require("node:test"));
const rules = (0, node_fs_1.readFileSync)((0, node_path_1.resolve)(__dirname, "../../firestore.rules"), "utf8");
const compactRules = rules.replace(/\s+/g, " ");
function assertContains(description, expected) {
    strict_1.default.match(compactRules, new RegExp(expected.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+")), description);
}
(0, node_test_1.default)("owner private collections and app feedback rules fail closed", () => {
    assertContains("device tokens must be owner-scoped with token/doc binding", "match /deviceTokens/{token} { allow get, list: if isSelf(kakaoUserId); allow create, update: if isSelf(kakaoUserId) && request.resource.data.userId is string && request.resource.data.userId == kakaoUserId && request.resource.data.token is string && request.resource.data.token == token; allow delete: if isSelf(kakaoUserId); }");
    assertContains("notifications must be owner-readable and client read-status only", "match /notifications/{notificationId} { allow get, list: if isSelf(kakaoUserId); allow create: if false; allow update: if isSelf(kakaoUserId) && request.resource.data.diff(resource.data).changedKeys().hasOnly([ 'isRead', 'readAt' ]); allow delete: if false; }");
    assertContains("issue reports must be authenticated owner-bound create only", "match /app_issue_reports/{reportId} { allow create: if isSignedIn() && request.resource.data.reporterId is string && request.resource.data.reporterId == request.auth.uid");
    assertContains("inquiries must be authenticated owner-bound create only", "match /app_inquiries/{inquiryId} { allow create: if isSignedIn() && request.resource.data.inquirerId is string && request.resource.data.inquirerId == request.auth.uid");
});
(0, node_test_1.default)("matching and recommendation rules are participant or owner scoped", () => {
    assertContains("model recs must be readable only by the target user", "match /modelRecs/{userId}/daily/{dateKey}/sources/{algo} { allow read: if isSelf(userId); allow write: if false; }");
    assertContains("asks must be participant-readable and recipient can only mark read", "match /asks/{askId} { allow read: if isAskParticipant(resource.data); allow create: if isSignedIn() && request.resource.data.fromUserId is string && request.resource.data.fromUserId == request.auth.uid");
    assertContains("interactions must be participant-readable and from-user-bound create only", "match /interactions/{interactionId} { allow read: if isInteractionParticipant(resource.data); allow create: if isSignedIn() && request.resource.data.fromUserId is string && request.resource.data.fromUserId == request.auth.uid");
    assertContains("matches must be participant-readable and backend-created", "match /matches/{matchId} { allow read: if isMatchParticipant(resource.data); allow create: if false;");
    assertContains("matches can only be unmatched by a participant", "allow update: if isMatchParticipant(resource.data) && matchStatusOnlyMovesToUnmatched(); allow delete: if false;");
});
(0, node_test_1.default)("event team setup and invite reads are participant scoped", () => {
    assertContains("event team setups must be visible only to accepted or pending participants", "match /eventTeamSetups/{teamSetupId} { allow read: if isEventTeamSetupParticipant(resource.data); allow write: if false; }");
    assertContains("event team invites must be visible only to inviter or invitee", "match /eventTeamInvites/{inviteId} { allow read: if isEventTeamInviteParticipant(resource.data); allow write: if false; }");
});
(0, node_test_1.default)("interaction service does not create matches from the client", () => {
    const service = (0, node_fs_1.readFileSync)((0, node_path_1.resolve)(__dirname, "../../lib/services/interaction_service.dart"), "utf8");
    strict_1.default.doesNotMatch(service, /_matchesRef\.add\s*\(/);
    strict_1.default.doesNotMatch(service, /collection\(['"]matches['"]\)\.add\s*\(/);
});
