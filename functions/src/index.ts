/**
 * ?ㅻ젅??Cloud Functions
 *
 * Trigger list:
 *   1) onRecEventCreated         - recEvents logging + match check
 *   2) onInteractionCreated      - profile like notification + match creation + chat room
 *   3) onChatMessageCreated      - new chat message push notification
 *   4) onBambooCommentCreated    - community comment/reply push + in-app notification
 *   5) onBambooPostLikeCreated   - community post like push + in-app notification
 *   6) onAskCreated              - ask creation notification + push
 *   7) onMatchUpdated            - deactivate chat room on unmatch
 *   8) autoCompleteExpiredGoodbyeSafetyStamps - auto-complete expired goodbye safety stamps + follow-up notification
 *   9) schedulePromiseReminderTask - schedule exact one-hour promise reminder
 *   10) dispatchPromiseReminder ???덉빟???쎌냽 1?쒓컙 ???몄떆 ?ㅽ뻾
 *   11) sendUpcomingPromiseReminderPushes - legacy 15-minute reminder (disabled)
 *   12) sendDailyUnreadChatDigests - daily 1 PM unread chat digest push + in-app notification
 */

import { setGlobalOptions } from "firebase-functions/v2";
import {
  onDocumentCreated,
  onDocumentUpdated,
} from "firebase-functions/v2/firestore";
import { onCall, HttpsError } from "firebase-functions/v2/https";
import { withAppCheck } from "./appCheckPolicy";
import { ensureMutualMatch } from "./mutualMatchCreation";
import {
  createFirestorePushRecipientLoader,
  filterPushRecipientIds,
} from "./pushRecipientPolicy";
import { onSchedule } from "firebase-functions/v2/scheduler";
import { onTaskDispatched } from "firebase-functions/v2/tasks";
import * as logger from "firebase-functions/logger";
import { initializeApp } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";
import { getFunctions } from "firebase-admin/functions";
import {
  getFirestore,
  FieldValue,
  Timestamp,
  DocumentReference,
} from "firebase-admin/firestore";
import { getMessaging } from "firebase-admin/messaging";
import { createHash, randomBytes } from "crypto";
import { onDocumentWritten } from "firebase-functions/v2/firestore";
import {
  buildReminderScheduledForMs,
  buildUpcomingPromiseReminderTitle,
  PROMISE_REMINDER_QUEUE_PATH,
  type PromiseReminderTaskPayload,
} from "./promiseReminder";
import {
  createGetCurrentAvatarGenerationStatusFunction,
  createRetryCurrentAvatarGenerationFunction,
  createUploadAvatarSourcePhotoFunction,
} from "./avatarMedia";
import {
  createApproveAvatarCandidateFunction,
  createGetAvatarJobCandidatesFunction,
} from "./avatarApproval";
import { createGetChatRealProfilePhotoFunction } from "./chatRealPhoto";
import { createCleanupAvatarMediaFunction } from "./avatarCleanup";
import {
  createAvatarJobSourceRetentionTrigger,
  createAvatarSourceRetentionRecoveryTrigger,
  createClipEmbeddingSourceRetentionTrigger,
} from "./avatarSourceRetention";
import { createAvatarGenerationStateSyncTrigger } from "./avatarGenerationStateSync";
import { isSafePublicAvatarUrl } from "./publicMediaUrlPolicy";
export { isSafePublicAvatarUrl as isSafePublicMediaUrl } from "./publicMediaUrlPolicy";
import {
  createRespondTeamMeetingRequestFunction,
  createTeamMeetingRequestFunction,
} from "./teamMeetingRequest";
import { createReportAndBlockUserFunction } from "./reportAndBlock";

// Initialize Firebase Admin
initializeApp();
const db = getFirestore();
const FRIEND_INVITE_HOST = "seolleyeon.web.app";
const FRIEND_INVITE_PATH = "/invite/friend";
const FRIEND_INVITE_EXPIRY_MS = 7 * 24 * 60 * 60 * 1000;

// ?꾩뿭 ?듭뀡
setGlobalOptions({
  region: "asia-northeast3",
  maxInstances: 10,
});

// =============================================================================
// Common helpers
// =============================================================================
function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function asNonEmptyString(v: unknown): string | null {
  if (typeof v !== "string") return null;
  const s = v.trim();
  return s.length > 0 ? s : null;
}

function asString(v: unknown, fallback = ""): string {
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (v == null) return fallback;
  return fallback;
}

function asStringOrNull(v: unknown): string | null {
  const s = asString(v, "").trim();
  return s.length > 0 ? s : null;
}

function asStringArray(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.map((item) => asString(item, "").trim()).filter(Boolean);
}

function asDate(v: unknown): Date | null {
  if (v instanceof Timestamp) return v.toDate();
  if (v instanceof Date) return v;
  if (typeof v === "string" || typeof v === "number") {
    const parsed = new Date(v);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
  return null;
}

function getKstDateKey(now = new Date()): string {
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const y = kst.getUTCFullYear();
  const m = String(kst.getUTCMonth() + 1).padStart(2, "0");
  const d = String(kst.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function getKstCompactDateKey(now = new Date()): string {
  return getKstDateKey(now).replace(/-/g, "");
}

const DEFAULT_EVENT_TEAM_AVAILABILITY_SLOT_IDS = [
  "weekday_evening",
  "weekend_afternoon",
  "weekend_evening",
];
const EVENT_TEAM_MATCH_COLLECTION = "eventTeamMatches";
const EVENT_TEAM_MATCH_LOCK_COLLECTION = "eventTeamMatchLocks";
const EVENT_TEAM_MATCH_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const EVENT_TEAM_CANDIDATE_POOL_LIMIT = 8;

type EventTeamMemberSnapshot = {
  uid: string;
  displayName: string;
  photoUrl: string | null;
  universityId: string | null;
  universityName: string | null;
  mannerScore: number | null;
  isVerified: boolean;
  shortIntro: string | null;
  birthYear: number | null;
  major: string | null;
};

type EventTeamCandidateSnapshot = {
  groupId: string;
  sourceSetupId: string | null;
  membersSnapshot: EventTeamMemberSnapshot[];
  memberCount: number;
  score: number;
  position: number | null;
  isExplore: boolean;
  matchedPairs: Record<string, unknown>[];
};

type MeetingRecommendationCandidate = {
  groupId: string;
  score: number;
  position: number | null;
  isExplore: boolean;
  matchedPairs: Record<string, unknown>[];
};

type MeetingRecommendationSource = {
  algorithm: string;
  sourcePath: string;
  candidates: MeetingRecommendationCandidate[];
  skipReason: string | null;
};

function dedupeStrings(values: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const value of values) {
    const normalized = value.trim();
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    out.push(normalized);
  }
  return out;
}

function normalizeStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return dedupeStrings(
    value
      .map((item) => asString(item, "").trim())
      .filter((item) => item.length > 0)
  );
}

function readMap(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function firstNonEmptyString(...values: unknown[]): string | null {
  for (const value of values) {
    const normalized = asStringOrNull(value);
    if (normalized) return normalized;
  }
  return null;
}

function firstNumber(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === "string") {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }
  return null;
}

function firstInteger(...values: unknown[]): number | null {
  const parsed = firstNumber(...values);
  return parsed == null ? null : Math.trunc(parsed);
}

export function readSafePhotoUrl(userData: Record<string, unknown>): string | null {
  const avatar = readMap(userData.avatar);
  const approvedAvatarUrl = asStringOrNull(avatar.approvedAvatarUrl);
  if (avatar.status === "approved" && isSafePublicAvatarUrl(approvedAvatarUrl)) {
    return approvedAvatarUrl;
  }
  return null;
}

function truncateText(value: string | null, maxLength = 90): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (trimmed.length <= maxLength) return trimmed;
  return `${trimmed.slice(0, Math.max(0, maxLength - 3)).trim()}...`;
}

function readUserOnboarding(userData: Record<string, unknown>): Record<string, unknown> {
  return readMap(userData.onboarding);
}

function buildEventTeamMemberSnapshot(
  uid: string,
  userData: Record<string, unknown>,
  profileData: Record<string, unknown>
): EventTeamMemberSnapshot {
  const onboarding = readUserOnboarding(userData);
  const mannerScore = firstNumber(profileData.mannerScore, userData.mannerScore, 36.5);
  return {
    uid,
    displayName: firstNonEmptyString(onboarding.nickname, userData.nickname, uid) ?? uid,
    photoUrl: readSafePhotoUrl(userData),
    universityId: firstNonEmptyString(
      onboarding.universityId,
      userData.universityId,
      profileData.universityId,
      onboarding.university,
      userData.universityName,
      userData.university
    ),
    universityName: firstNonEmptyString(
      onboarding.university,
      userData.universityName,
      userData.university
    ),
    mannerScore,
    isVerified: Boolean(
      profileData.isVerified ?? userData.isStudentVerified ?? userData.isVerified ?? false
    ),
    shortIntro: truncateText(
      firstNonEmptyString(
        onboarding.selfIntroduction,
        onboarding.shortIntro,
        userData.shortIntro
      )
    ),
    birthYear: firstInteger(profileData.birthYear, onboarding.birthYear, userData.birthYear),
    major: firstNonEmptyString(onboarding.major, userData.major),
  };
}

function buildDeterministicAcceptedOrder(
  leaderUserId: string,
  acceptedUserIds: string[]
): string[] {
  const ordered = dedupeStrings(acceptedUserIds);
  if (!leaderUserId) return ordered;
  return dedupeStrings([
    leaderUserId,
    ...ordered.filter((uid) => uid !== leaderUserId),
  ]);
}

function pickPrimaryValue(values: Array<string | null>): string | null {
  const normalized = values.filter((value): value is string => !!value && value.trim().length > 0);
  if (normalized.length === 0) return null;
  const counts = new Map<string, number>();
  for (const value of normalized) {
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  let best: string | null = null;
  let bestCount = -1;
  for (const value of normalized) {
    const count = counts.get(value) ?? 0;
    if (count > bestCount) {
      best = value;
      bestCount = count;
    }
  }
  return best;
}

async function loadCollectionDocsByIds(
  collectionName: string,
  docIds: string[]
): Promise<Record<string, Record<string, unknown>>> {
  const uniqueIds = dedupeStrings(docIds);
  if (uniqueIds.length === 0) return {};
  const refs = uniqueIds.map((docId) => db.collection(collectionName).doc(docId));
  const snapshots = await db.getAll(...refs);
  const docs: Record<string, Record<string, unknown>> = {};
  for (const snapshot of snapshots) {
    if (!snapshot.exists) continue;
    docs[snapshot.id] = (snapshot.data() ?? {}) as Record<string, unknown>;
  }
  return docs;
}

function deriveAvailabilitySlotIds(
  teamData: Record<string, unknown>,
  userDocs: Record<string, Record<string, unknown>>
): string[] {
  const direct = normalizeStringList(teamData.availabilitySlotIds);
  if (direct.length > 0) return direct;

  const collected: string[] = [];
  for (const userData of Object.values(userDocs)) {
    const onboarding = readUserOnboarding(userData);
    collected.push(...normalizeStringList(onboarding.availabilitySlotIds));
  }
  return collected.length > 0
    ? dedupeStrings(collected)
    : [...DEFAULT_EVENT_TEAM_AVAILABILITY_SLOT_IDS];
}

function deriveVibeTagIds(
  teamData: Record<string, unknown>,
  userDocs: Record<string, Record<string, unknown>>
): string[] {
  const direct = normalizeStringList(teamData.vibeTagIds);
  if (direct.length > 0) return direct.slice(0, 8);

  const collected: string[] = [];
  for (const userData of Object.values(userDocs)) {
    const onboarding = readUserOnboarding(userData);
    collected.push(...normalizeStringList(onboarding.interests));
    collected.push(...normalizeStringList(onboarding.keywords));
    collected.push(...normalizeStringList(onboarding.vibeTagIds));
  }
  return dedupeStrings(collected).slice(0, 8);
}

function buildMeetingGroupPayload(
  teamSetupId: string,
  teamData: Record<string, unknown>,
  userDocs: Record<string, Record<string, unknown>>,
  profileDocs: Record<string, Record<string, unknown>>
): Record<string, unknown> {
  const leaderUserId = asString(teamData.leaderUserId ?? "");
  const acceptedUserIds = buildDeterministicAcceptedOrder(
    leaderUserId,
    normalizeStringList(teamData.acceptedUserIds)
  );
  const membersSnapshot = acceptedUserIds.map((uid) =>
    buildEventTeamMemberSnapshot(uid, userDocs[uid] ?? {}, profileDocs[uid] ?? {})
  );
  const memberCount = acceptedUserIds.length;
  const isEligible = memberCount === 3;
  const universityIds = dedupeStrings(
    membersSnapshot
      .map((member) => member.universityId)
      .filter((value): value is string => !!value)
  );
  const primaryUniversityId = pickPrimaryValue(
    membersSnapshot.map((member) => member.universityId)
  );
  const regionId =
    firstNonEmptyString(teamData.regionId, primaryUniversityId) ?? null;
  const expireAt = Timestamp.fromDate(
    new Date(Date.now() + EVENT_TEAM_MATCH_TTL_MS)
  );

  return {
    groupId: teamSetupId,
    sourceCollection: "eventTeamSetups",
    sourceSetupId: teamSetupId,
    captainUid: firstNonEmptyString(teamData.captainUid, leaderUserId),
    leaderUid: leaderUserId,
    memberUids: acceptedUserIds,
    membersSnapshot,
    memberCount,
    size: memberCount,
    status: isEligible ? "open" : memberCount > 0 ? "draft" : "closed",
    pendingInviteeIds: normalizeStringList(teamData.pendingInviteeIds),
    eventType: "season_meeting",
    seasonKey: getKstCompactDateKey().slice(0, 6),
    regionId,
    availabilitySlotIds: isEligible
      ? deriveAvailabilitySlotIds(teamData, userDocs)
      : [],
    vibeTagIds: deriveVibeTagIds(teamData, userDocs),
    universityIds,
    primaryUniversityId,
    createdAt: teamData.createdAt ?? FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp(),
    sourceUpdatedAt: teamData.updatedAt ?? null,
    expireAt,
    active: isEligible,
    isEligibleForMeetingRec: isEligible,
    eligibilityReason: isEligible ? "ready" : "accepted_member_count_not_3",
    syncSource: "event_team_setup",
    lastSyncedAt: FieldValue.serverTimestamp(),
  };
}

async function syncMeetingGroupFromEventTeamSetup(
  teamSetupId: string,
  teamData: Record<string, unknown> | null
): Promise<void> {
  const meetingGroupRef = db.collection("meetingGroups").doc(teamSetupId);
  if (!teamData) {
    await meetingGroupRef.set(
      {
        groupId: teamSetupId,
        sourceCollection: "eventTeamSetups",
        sourceSetupId: teamSetupId,
        status: "closed",
        active: false,
        isEligibleForMeetingRec: false,
        eligibilityReason: "source_team_deleted",
        memberUids: [],
        membersSnapshot: [],
        memberCount: 0,
        updatedAt: FieldValue.serverTimestamp(),
        lastSyncedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
    return;
  }

  const memberUids = buildDeterministicAcceptedOrder(
    asString(teamData.leaderUserId ?? ""),
    normalizeStringList(teamData.acceptedUserIds)
  );
  const userDocs = await loadCollectionDocsByIds("users", memberUids);
  const profileDocs = await loadCollectionDocsByIds("profileIndex", memberUids);
  await meetingGroupRef.set(
    buildMeetingGroupPayload(teamSetupId, teamData, userDocs, profileDocs),
    { merge: true }
  );
}

function readTeamCandidateSnapshot(
  groupId: string,
  groupData: Record<string, unknown>,
  score: number,
  position: number | null,
  isExplore: boolean,
  matchedPairs: Record<string, unknown>[]
): EventTeamCandidateSnapshot | null {
  const membersRaw = Array.isArray(groupData.membersSnapshot)
    ? groupData.membersSnapshot
    : [];
  const membersSnapshot = membersRaw
    .filter((item) => isRecord(item))
    .map((item) => ({
      uid: asString(item.uid ?? ""),
      displayName: asString(item.displayName ?? "Unknown user", "Unknown user"),
      photoUrl: asStringOrNull(item.photoUrl) ?? null,
      universityId: asStringOrNull(item.universityId) ?? null,
      universityName: asStringOrNull(item.universityName) ?? null,
      mannerScore: firstNumber(item.mannerScore),
      isVerified: Boolean(item.isVerified ?? false),
      shortIntro: asStringOrNull(item.shortIntro) ?? null,
      birthYear: firstInteger(item.birthYear),
      major: asStringOrNull(item.major) ?? null,
    }));
  if (membersSnapshot.length !== 3) return null;

  return {
    groupId,
    sourceSetupId: firstNonEmptyString(
      groupData.sourceSetupId,
      groupData.teamSetupId
    ),
    membersSnapshot,
    memberCount: firstInteger(groupData.memberCount) ?? membersSnapshot.length,
    score,
    position,
    isExplore,
    matchedPairs,
  };
}

function normalizeCandidateScores(scores: number[]): number[] {
  if (scores.length === 0) return [];
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  if (min === max) return scores.map(() => 1);
  return scores.map((score) => (score - min) / Math.max(1e-9, max - min));
}

function randomUnit(): number {
  const buffer = randomBytes(6);
  const intValue = buffer.readUIntBE(0, 6);
  return intValue / 0x1000000000000;
}

function buildWeightedCandidateOrder(
  candidates: EventTeamCandidateSnapshot[]
): EventTeamCandidateSnapshot[] {
  const scores = normalizeCandidateScores(candidates.map((candidate) => candidate.score));
  const pool = candidates.map((candidate, index) => ({
    candidate,
    weight: Math.max(0.15, scores[index] + 0.15),
  }));
  const ordered: EventTeamCandidateSnapshot[] = [];
  while (pool.length > 0) {
    const totalWeight = pool.reduce((sum, item) => sum + item.weight, 0);
    let cursor = randomUnit() * totalWeight;
    let selectedIndex = pool.length - 1;
    for (let index = 0; index < pool.length; index += 1) {
      cursor -= pool[index].weight;
      if (cursor <= 0) {
        selectedIndex = index;
        break;
      }
    }
    const [selected] = pool.splice(selectedIndex, 1);
    if (selected) {
      ordered.push(selected.candidate);
    }
  }
  return ordered;
}

function sharesAnyMember(left: string[], right: string[]): boolean {
  const rightSet = new Set(right);
  return left.some((uid) => rightSet.has(uid));
}

function sanitizeMatchedPairs(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => isRecord(item));
}

function isMeetingGroupAvailable(groupData: Record<string, unknown>): boolean {
  const memberUids = normalizeStringList(groupData.memberUids);
  const memberCount = firstInteger(groupData.memberCount, groupData.size) ?? memberUids.length;
  const status = asString(groupData.status ?? "", "");
  const active = groupData.active !== false;
  const eligible = groupData.isEligibleForMeetingRec !== false;
  return active && eligible && status === "open" && memberCount === 3;
}

function readRecommendationCandidateFromDailyItem(
  value: unknown
): MeetingRecommendationCandidate | null {
  if (!isRecord(value)) return null;
  const groupId = asString(value.groupId ?? "", "").trim();
  if (!groupId) return null;
  return {
    groupId,
    score: firstNumber(value.scoreTotal, value.score, value.positionScore, 0) ?? 0,
    position: firstInteger(value.position),
    isExplore: value.isExplore === true,
    matchedPairs: sanitizeMatchedPairs(value.matchedPairs),
  };
}

function readRecommendationCandidateFromRankerItem(
  value: unknown
): MeetingRecommendationCandidate | null {
  if (!isRecord(value)) return null;
  const groupId = asString(value.groupId ?? "", "").trim();
  if (!groupId) return null;
  return {
    groupId,
    score: firstNumber(value.score, value.scoreTotal, 0) ?? 0,
    position: firstInteger(value.rank, value.position),
    isExplore: false,
    matchedPairs: sanitizeMatchedPairs(value.matchedPairs),
  };
}

async function loadMeetingRecommendationSource(
  requestingGroupId: string,
  dateKey: string
): Promise<MeetingRecommendationSource | null> {
  const meetingDailyRef = db
    .collection("meetingDailyRecs")
    .doc(requestingGroupId)
    .collection("days")
    .doc(dateKey);
  const meetingDailySnap = await meetingDailyRef.get();
  if (meetingDailySnap.exists) {
    const dailyData = (meetingDailySnap.data() ?? {}) as Record<string, unknown>;
    if (asString(dailyData.status ?? "", "") === "ready") {
      const candidates = Array.isArray(dailyData.candidates)
        ? dailyData.candidates
            .map(readRecommendationCandidateFromDailyItem)
            .filter(
              (item): item is MeetingRecommendationCandidate => item !== null
            )
        : [];
      if (candidates.length > 0) {
        return {
          algorithm: "meeting_daily_weighted_random",
          sourcePath: meetingDailyRef.path,
          candidates,
          skipReason: null,
        };
      }
    }
  }

  const rankerRef = db
    .collection("meetingModelRecs")
    .doc(requestingGroupId)
    .collection("daily")
    .doc(dateKey)
    .collection("sources")
    .doc("group_ranker");
  const rankerSnap = await rankerRef.get();
  if (!rankerSnap.exists) {
    return null;
  }

  const rankerData = (rankerSnap.data() ?? {}) as Record<string, unknown>;
  if (asString(rankerData.status ?? "", "") !== "ready") {
    return {
      algorithm: "meeting_group_ranker_fallback",
      sourcePath: rankerRef.path,
      candidates: [],
      skipReason: asStringOrNull(rankerData.skipReason),
    };
  }

  const candidates = Array.isArray(rankerData.items)
    ? rankerData.items
        .map(readRecommendationCandidateFromRankerItem)
        .filter((item): item is MeetingRecommendationCandidate => item !== null)
    : [];
  return {
    algorithm: "meeting_group_ranker_fallback",
    sourcePath: rankerRef.path,
    candidates,
    skipReason: asStringOrNull(rankerData.skipReason),
  };
}

async function resolveEventTeamSetupForUser(
  userId: string,
  preferredTeamSetupId: string | null
): Promise<{ teamSetupId: string; data: Record<string, unknown> } | null> {
  if (preferredTeamSetupId) {
    const preferredSnap = await db
      .collection("eventTeamSetups")
      .doc(preferredTeamSetupId)
      .get();
    if (preferredSnap.exists) {
      const preferredData = (preferredSnap.data() ?? {}) as Record<string, unknown>;
      const acceptedUserIds = buildDeterministicAcceptedOrder(
        asString(preferredData.leaderUserId ?? ""),
        normalizeStringList(preferredData.acceptedUserIds)
      );
      if (acceptedUserIds.includes(userId)) {
        return {
          teamSetupId: preferredSnap.id,
          data: preferredData,
        };
      }
    }
  }

  const teamQuery = await db
    .collection("eventTeamSetups")
    .where("acceptedUserIds", "array-contains", userId)
    .get();

  const docs = [...teamQuery.docs];
  docs.sort((left, right) => {
    const leftData = (left.data() ?? {}) as Record<string, unknown>;
    const rightData = (right.data() ?? {}) as Record<string, unknown>;
    const leftAcceptedCount = buildDeterministicAcceptedOrder(
      asString(leftData.leaderUserId ?? ""),
      normalizeStringList(leftData.acceptedUserIds)
    ).length;
    const rightAcceptedCount = buildDeterministicAcceptedOrder(
      asString(rightData.leaderUserId ?? ""),
      normalizeStringList(rightData.acceptedUserIds)
    ).length;
    if (leftAcceptedCount !== rightAcceptedCount) {
      return rightAcceptedCount - leftAcceptedCount;
    }
    const leftUpdatedAt =
      leftData.updatedAt instanceof Timestamp
        ? leftData.updatedAt.toMillis()
        : 0;
    const rightUpdatedAt =
      rightData.updatedAt instanceof Timestamp
        ? rightData.updatedAt.toMillis()
        : 0;
    return rightUpdatedAt - leftUpdatedAt;
  });

  for (const doc of docs) {
    const data = (doc.data() ?? {}) as Record<string, unknown>;
    const acceptedUserIds = buildDeterministicAcceptedOrder(
      asString(data.leaderUserId ?? ""),
      normalizeStringList(data.acceptedUserIds)
    );
    if (acceptedUserIds.includes(userId)) {
      return {
        teamSetupId: doc.id,
        data,
      };
    }
  }

  return null;
}

function buildEventTeamMatchLockId(dateKey: string, groupId: string): string {
  return `${dateKey}_${groupId}`;
}

function buildEventTeamParticipantUids(
  requestingTeam: EventTeamCandidateSnapshot,
  matchedTeam: EventTeamCandidateSnapshot
): string[] {
  return dedupeStrings([
    ...requestingTeam.membersSnapshot.map((member) => member.uid),
    ...matchedTeam.membersSnapshot.map((member) => member.uid),
  ]).sort();
}

function eventTeamCandidateSnapshotToMap(
  candidate: EventTeamCandidateSnapshot
): Record<string, unknown> {
  return {
    groupId: candidate.groupId,
    sourceSetupId: candidate.sourceSetupId,
    membersSnapshot: candidate.membersSnapshot,
    memberCount: candidate.memberCount,
    score: candidate.score,
    position: candidate.position,
    isExplore: candidate.isExplore,
    matchedPairs: candidate.matchedPairs,
  };
}

export function buildEventTeamMatchResultPreview(params: {
  resultId: string;
  dateKey: string;
  requestingTeamSetupId: string;
  requestingTeam: EventTeamCandidateSnapshot;
  matchedTeam: EventTeamCandidateSnapshot;
  candidateTeams: EventTeamCandidateSnapshot[];
  algorithm: string;
  sourcePath: string;
  selectedGroupIndex: number;
  createdAtIso: string;
}): Record<string, unknown> {
  return {
    resultId: params.resultId,
    source: "slot_machine",
    eventType: "season_meeting",
    seasonKey: params.dateKey.slice(0, 6),
    dateKey: params.dateKey,
    requestingEventTeamSetupId: params.requestingTeamSetupId,
    requestingGroupId: params.requestingTeam.groupId,
    matchedGroupId: params.matchedTeam.groupId,
    participantUids: buildEventTeamParticipantUids(
      params.requestingTeam,
      params.matchedTeam
    ),
    groupIds: [
      params.requestingTeam.groupId,
      params.matchedTeam.groupId,
    ],
    candidateGroupIds: params.candidateTeams.map((team) => team.groupId),
    candidateScores: params.candidateTeams.map((team) => team.score),
    selectedGroupIndex: params.selectedGroupIndex,
    algorithm: params.algorithm,
    algorithmMeta: {
      recommendationPath: params.sourcePath,
      candidateCount: params.candidateTeams.length,
    },
    requestingTeamSnapshot: eventTeamCandidateSnapshotToMap(params.requestingTeam),
    matchedTeamSnapshot: eventTeamCandidateSnapshotToMap(params.matchedTeam),
    matchedMembersSnapshot: params.matchedTeam.membersSnapshot,
    candidateTeamsSnapshot: params.candidateTeams.map(
      eventTeamCandidateSnapshotToMap
    ),
    matchedPairMeta: params.matchedTeam.matchedPairs,
    matchedPairs: params.matchedTeam.matchedPairs,
    status: "created",
    createdAt: params.createdAtIso,
    updatedAt: params.createdAtIso,
  };
}

async function getUserDisplayInfo(userId: string): Promise<{
  nickname: string;
  avatarUrl: string | null;
}> {
  const snap = await db.collection("users").doc(userId).get();
  const data = (snap.data() ?? {}) as Record<string, unknown>;
  const onboardingRaw = data.onboarding;
  const onboarding = isRecord(onboardingRaw) ? onboardingRaw : {};

  const nickname = asString(
    onboarding.nickname ?? data.nickname ?? "\uC720\uC800",
    "\uC720\uC800"
  );

  const avatarUrl = readSafePhotoUrl(data);

  return {
    nickname,
    avatarUrl,
  };
}

/**
 * Whether a failed FCM send means the token is permanently gone.
 *
 * Deleting on any failure is wrong: a transient FCM outage or quota error would
 * unregister a working device, and the user then silently stops receiving push
 * forever with nothing in the app to indicate it. Only these two codes mean the
 * token itself is dead.
 */
export function isUnregisteredPushTokenError(code: string | null): boolean {
  return (
    code === "messaging/registration-token-not-registered" ||
    code === "messaging/invalid-registration-token"
  );
}

async function fetchUserTokens(userId: string): Promise<string[]> {
  const snap = await db
    .collection("users")
    .doc(userId)
    .collection("deviceTokens")
    .get();

  return snap.docs.map((d) => d.id).filter((t) => t.length > 0);
}

type InAppNotificationPayload = {
  type:
    | "chat_digest"
    | "community_post_like"
    | "community_comment"
    | "community_reply"
    | "profile_like"
    | "ask_received"
    | "safety_stamp_follow_up";
  title: string;
  body: string;
  deeplinkType:
    | "chat"
    | "community_post"
    | "received_like"
    | "asks_inbox"
    | "safety_stamp_follow_up";
  deeplinkId?: string;
  actorId?: string;
  actorName?: string;
  postId?: string;
  commentId?: string;
  roomId?: string;
  digestDate?: string;
};

async function createInAppNotification(
  userId: string,
  payload: InAppNotificationPayload,
  notificationId?: string
): Promise<boolean> {
  if (!userId) return false;

  const notifRef = notificationId
    ? db
        .collection("users")
        .doc(userId)
        .collection("notifications")
        .doc(notificationId)
    : db
        .collection("users")
        .doc(userId)
        .collection("notifications")
        .doc();

  if (notificationId) {
    const existing = await notifRef.get();
    if (existing.exists) {
      logger.info("Notification already exists, skipping (idempotent)", {
        userIdHash: logHashPrefix(userId),
        notificationId,
      });
      return false;
    }
  }

  await notifRef.set({
    type: payload.type,
    title: payload.title,
    body: payload.body,
    isRead: false,
    createdAt: FieldValue.serverTimestamp(),

    actorId: payload.actorId ?? null,
    actorName: payload.actorName ?? null,
    postId: payload.postId ?? null,
    commentId: payload.commentId ?? null,
    roomId: payload.roomId ?? null,
    deeplinkType: payload.deeplinkType,
    deeplinkId: payload.deeplinkId ?? null,
    digestDate: payload.digestDate ?? null,
  });

  logger.info("In-app notification created", {
    userIdHash: logHashPrefix(userId),
    notificationId: notifRef.id,
    type: payload.type,
    deeplinkType: payload.deeplinkType,
    deeplinkId: payload.deeplinkId ?? null,
  });

  return true;
}

async function countPostLikeNotificationsForPost(
  userId: string,
  postId: string
): Promise<number> {
  const snap = await db
    .collection("users")
    .doc(userId)
    .collection("notifications")
    .where("type", "==", "community_post_like")
    .where("postId", "==", postId)
    .get();

  return snap.size;
}

async function hasChatDigestForDate(
  userId: string,
  digestDate: string
): Promise<boolean> {
  const snap = await db
    .collection("users")
    .doc(userId)
    .collection("notifications")
    .where("type", "==", "chat_digest")
    .where("digestDate", "==", digestDate)
    .limit(1)
    .get();

  return !snap.empty;
}

async function sendPushToUsers(
  userIds: string[],
  payload: {
    title: string;
    body: string;
    data: Record<string, string>;
    /** When set, recipients who mutually blocked this actor are skipped. */
    actorUserId?: string;
  }
): Promise<void> {
  const uniqueUserIds = [...new Set(userIds.filter((u) => u.length > 0))];
  if (uniqueUserIds.length === 0) return;

  const actorUserId =
    asNonEmptyString(payload.actorUserId) ??
    asNonEmptyString(payload.data.actorUserId) ??
    asNonEmptyString(payload.data.inviterUserId) ??
    undefined;

  const { allowed: eligibleUserIds, skipped } = await filterPushRecipientIds(
    uniqueUserIds,
    {
      actorUserId,
      ...createFirestorePushRecipientLoader(db),
    }
  );
  if (skipped.length > 0) {
    logger.info("Push recipients filtered", {
      actorUserIdHash: actorUserId ? logHashPrefix(actorUserId) : null,
      skippedCount: skipped.length,
      skippedReasons: skipped.map((s) => s.reason),
      skippedUserIdHashes: logHashPrefixes(skipped.map((s) => s.uid)),
    });
  }
  if (eligibleUserIds.length === 0) return;

  const tokenLists = await Promise.all(eligibleUserIds.map(fetchUserTokens));
  // Keep each token bound to the user it came from. The multicast response is
  // index-aligned with this list, and a token document is only ever valid to
  // delete under its own owner.
  const tokenOwners: { uid: string; token: string }[] = [];
  tokenLists.forEach((list, index) => {
    const uid = eligibleUserIds[index];
    for (const token of list) {
      if (token) tokenOwners.push({ uid, token });
    }
  });
  const tokens = tokenOwners.map((entry) => entry.token);

  if (tokens.length === 0) {
    logger.info("No device tokens found for users", {
      userCount: eligibleUserIds.length,
      userIdHashes: logHashPrefixes(eligibleUserIds),
    });
    return;
  }

  const response = await getMessaging().sendEachForMulticast({
    tokens,
    notification: {
      title: payload.title,
      body: payload.body,
    },
    data: payload.data,
    android: {
      priority: "high",
      notification: {
        channelId: "seolleyeon_high_importance",
      },
    },
    apns: {
      headers: {
        "apns-priority": "10",
      },
      payload: {
        aps: {
          sound: "default",
        },
      },
    },
  });

  const unregistered: { uid: string; token: string }[] = [];
  response.responses.forEach((r, i) => {
    if (r.success) return;
    const owner = tokenOwners[i];
    if (!owner) return;

    const errorCode = r.error?.code ?? null;
    const drop = isUnregisteredPushTokenError(errorCode);
    if (drop) unregistered.push(owner);

    logger.warn("Push send failed", {
      tokenHash: logHashPrefix(owner.token),
      userIdHash: logHashPrefix(owner.uid),
      errorCode,
      droppingToken: drop,
    });
  });

  if (unregistered.length > 0) {
    const batch = db.batch();
    for (const { uid, token } of unregistered) {
      batch.delete(
        db.collection("users").doc(uid).collection("deviceTokens").doc(token)
      );
    }
    await batch.commit();
  }
}

function buildSafetyStampFollowUpNotificationId(
  promiseId: string,
  userId: string
): string {
  return `safety_stamp_follow_up_${promiseId}_${userId}`;
}

async function getUnreadChatDigestForUser(userId: string): Promise<{
  unreadCount: number;
  previewSenderName: string | null;
}> {
  const roomsSnap = await db
    .collection("chat_rooms")
    .where("participantIds", "array-contains", userId)
    .where("status", "==", "active")
    .get();

  let unreadCount = 0;
  let previewSenderName: string | null = null;

  for (const roomDoc of roomsSnap.docs) {
    const roomData = (roomDoc.data() ?? {}) as Record<string, unknown>;
    const participantInfoRaw = roomData.participantInfo;
    const participantInfo = isRecord(participantInfoRaw)
      ? participantInfoRaw
      : {};

    const messagesSnap = await roomDoc.ref.collection("messages").get();

    for (const msgDoc of messagesSnap.docs) {
      const msg = (msgDoc.data() ?? {}) as Record<string, unknown>;
      const senderId = asString(msg.senderId ?? "");
      if (!senderId || senderId === "system" || senderId === userId) continue;

      const readByRaw = msg.readBy;
      const readBy = Array.isArray(readByRaw)
        ? readByRaw.map((v) => asString(v)).filter((v) => v.length > 0)
        : [];

      if (!readBy.includes(userId)) {
        unreadCount += 1;

        if (!previewSenderName) {
          const senderInfo = participantInfo[senderId];
          previewSenderName = isRecord(senderInfo)
            ? asString(senderInfo.nickname ?? "", "")
            : "";
          if (!previewSenderName) {
            previewSenderName = "누군가";
          }
        }
      }
    }
  }

  return {
    unreadCount,
    previewSenderName,
  };
}

type ResolvedAppUser = {
  userId: string;
  email: string;
  data: Record<string, unknown>;
  profileSnapshot: Record<string, unknown>;
};

function buildFriendPairId(userA: string, userB: string): string {
  const ids = [userA, userB].sort();
  return `${ids[0]}_${ids[1]}`;
}

function logHashPrefix(value: unknown): string | null {
  const normalized = asStringOrNull(value);
  return normalized ? createHash("sha256").update(normalized).digest("hex").slice(0, 12) : null;
}

function logHashPrefixes(values: string[]): string[] {
  return values.map((value) => logHashPrefix(value)).filter((value): value is string => value !== null);
}

function logErrorTypeCode(error: unknown): { type: string; code: string | null } {
  const type = error instanceof Error
    ? error.name
    : error === null
      ? "null"
      : typeof error;
  const rawCode = isRecord(error) ? asStringOrNull(error.code) : null;
  const code =
    rawCode && /^[A-Za-z0-9_.:/-]{1,80}$/.test(rawCode) ? rawCode : null;
  return { type, code };
}
function hashInviteToken(rawToken: string): string {
  return createHash("sha256").update(rawToken).digest("hex");
}

function buildFriendInviteUrl(rawToken: string): string {
  const url = new URL(`https://${FRIEND_INVITE_HOST}${FRIEND_INVITE_PATH}`);
  url.searchParams.set("token", rawToken);
  return url.toString();
}

function buildFriendProfileSnapshot(
  userId: string,
  data: Record<string, unknown>
): Record<string, unknown> {
  const onboardingRaw = data.onboarding;
  const onboarding = isRecord(onboardingRaw) ? onboardingRaw : {};
  const profileImageUrl = readSafePhotoUrl(data);
  const universityName = asStringOrNull(
    onboarding.university ?? data.universityName
  );
  const major = asStringOrNull(onboarding.major ?? data.major);
  const nickname = asString(
    onboarding.nickname ?? data.nickname ?? userId,
    userId
  );

  return {
    uid: userId,
    nickname,
    profileImageUrl,
    universityName,
    major,
  };
}

async function verifyKakaoAccessToken(
  accessToken: string
): Promise<{ userId: string }> {
  const response = await fetch("https://kapi.kakao.com/v2/user/me", {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });

  if (!response.ok) {
    logger.warn("Kakao access token verification failed", {
      status: response.status,
    });
    throw new HttpsError(
      "unauthenticated",
      "카카오 로그인 세션을 확인할 수 없어요."
    );
  }

  const data = (await response.json()) as Record<string, unknown>;
  const userId = asString(data.id ?? "").trim();
  if (!userId) {
    throw new HttpsError(
      "unauthenticated",
      "카카오 사용자 정보를 확인할 수 없어요."
    );
  }

  return { userId };
}

export function verifiedYonseiEmailFromAuthToken(
  token: Record<string, unknown> | undefined
): string | null {
  if (!token) return null;
  if (token.email_verified !== true) return null;
  const raw = asNonEmptyString(token.email);
  const email = raw ? raw.toLowerCase() : null;
  return email && email.endsWith("@yonsei.ac.kr") ? email : null;
}

export type EmailLinkTokenRejection =
  | "missing"
  | "malformed"
  | "kakao-mismatch"
  | "email-mismatch"
  | "expired"
  | "mailbox-unproven"
  | "already-exchanged";

export type EmailLinkTokenDecision =
  | { ok: true; kakaoUserId: string; email: string }
  | { ok: false; reason: EmailLinkTokenRejection };

/**
 * Decides whether an emailLinkTokens document may be exchanged for a Firebase
 * custom token.
 *
 * The document itself is written by an unauthenticated-at-the-time client, so
 * its (kakaoUserId, email) pair is a *request*, not a credential. The only
 * trustworthy field is `emailVerifiedUid`/`emailVerifiedAt`, which
 * firestore.rules lets only the owner of the named mailbox write, after
 * Firebase itself verified the email link.
 */
export function evaluateEmailLinkTokenExchange(params: {
  tokenData: Record<string, unknown> | null | undefined;
  requestedKakaoUserId?: string | null;
  requestedStudentEmail?: string | null;
  now: Date;
  isTimestamp: (value: unknown) => boolean;
  toDate: (value: unknown) => Date | null;
}): EmailLinkTokenDecision {
  const { tokenData, now, isTimestamp, toDate } = params;
  if (!tokenData) return { ok: false, reason: "missing" };

  const kakaoUserId = asNonEmptyString(tokenData.kakaoUserId);
  const email = asNonEmptyString(tokenData.email)?.toLowerCase() ?? null;
  if (!kakaoUserId || !email) return { ok: false, reason: "malformed" };

  const requestedKakaoUserId = asNonEmptyString(params.requestedKakaoUserId);
  if (requestedKakaoUserId && requestedKakaoUserId !== kakaoUserId) {
    return { ok: false, reason: "kakao-mismatch" };
  }

  const requestedStudentEmail =
    asNonEmptyString(params.requestedStudentEmail)?.toLowerCase() ?? null;
  if (requestedStudentEmail && requestedStudentEmail !== email) {
    return { ok: false, reason: "email-mismatch" };
  }

  // A missing or malformed expiry previously skipped the expiry check, which
  // turned a forged document into a permanent credential.
  const expiresAt = toDate(tokenData.expiresAt);
  if (!expiresAt || expiresAt.getTime() < now.getTime()) {
    return { ok: false, reason: "expired" };
  }

  if (
    !asNonEmptyString(tokenData.emailVerifiedUid) ||
    !isTimestamp(tokenData.emailVerifiedAt)
  ) {
    return { ok: false, reason: "mailbox-unproven" };
  }

  if (tokenData.exchangedAt != null) {
    return { ok: false, reason: "already-exchanged" };
  }

  return { ok: true, kakaoUserId, email };
}

const EMAIL_LINK_TOKEN_REJECTION_CODES: Record<
  EmailLinkTokenRejection,
  "failed-precondition" | "permission-denied"
> = {
  missing: "failed-precondition",
  malformed: "failed-precondition",
  "kakao-mismatch": "permission-denied",
  "email-mismatch": "permission-denied",
  expired: "failed-precondition",
  "mailbox-unproven": "failed-precondition",
  "already-exchanged": "failed-precondition",
};

const EMAIL_LINK_TOKEN_REJECTION_MESSAGES: Record<
  EmailLinkTokenRejection,
  string
> = {
  missing: "인증 세션이 없어요. 이메일 인증 링크를 다시 보내주세요.",
  malformed: "인증 세션 정보가 올바르지 않아요. 이메일 인증을 다시 진행해주세요.",
  "kakao-mismatch": "인증 세션이 현재 계정과 일치하지 않아요.",
  "email-mismatch": "인증 세션 이메일이 현재 계정과 일치하지 않아요.",
  expired: "인증 세션이 만료되었어요. 이메일 인증 링크를 다시 보내주세요.",
  "mailbox-unproven":
    "이메일 인증이 아직 완료되지 않았어요. 인증 메일 링크를 다시 열어주세요.",
  "already-exchanged":
    "이미 사용된 인증 세션이에요. 이메일 인증 링크를 다시 보내주세요.",
};

export function buildKakaoUserShell(kakaoUserId: string): Record<string, unknown> {
  return {
    kakaoUserId,
    profileImageUrl: "",
    profileImageMode: "avatar",
    createdAt: FieldValue.serverTimestamp(),
    lastLoginAt: FieldValue.serverTimestamp(),
  };
}

/**
 * Firestore users document used for callable authentication.
 * - Custom token (UID = Kakao ID): read users/{uid} directly
 * - Email-link login (UID != Kakao ID): use JWT email to find matching studentEmail document
 */
async function resolveAuthedAppUser(
  auth: { uid?: string; token?: Record<string, unknown> } | null | undefined
): Promise<ResolvedAppUser> {
  const authUid = asNonEmptyString(auth?.uid);
  if (!authUid) {
    throw new HttpsError("unauthenticated", "로그인이 필요해요.");
  }

  const token = auth?.token as Record<string, unknown> | undefined;

  let doc = await db.collection("users").doc(authUid).get();

  if (!doc.exists) {
    const email = verifiedYonseiEmailFromAuthToken(token);
    if (email) {
      const q = await db
        .collection("users")
        .where("studentEmail", "==", email)
        .limit(1)
        .get();
      if (!q.empty) {
        doc = q.docs[0];
        logger.info(
          "resolveAuthedAppUser: matched user by studentEmail (email-link auth uid differs from kakao doc id)",
          { authUidHash: logHashPrefix(authUid), resolvedUserIdHash: logHashPrefix(doc.id) }
        );
      }
    }
  }

  if (!doc.exists) {
    throw new HttpsError(
      "failed-precondition",
      "가입 정보를 찾을 수 없어 친구 초대를 처리할 수 없어요."
    );
  }

  const userId = doc.id;
  const data = (doc.data() ?? {}) as Record<string, unknown>;
  const studentEmail = asNonEmptyString(data.studentEmail)?.toLowerCase() ?? "";
  const isStudentVerified = data.isStudentVerified === true;
  if (!isStudentVerified || !studentEmail.endsWith("@yonsei.ac.kr")) {
    throw new HttpsError(
      "failed-precondition",
      "학생 인증이 완료된 계정으로 다시 로그인해주세요."
    );
  }

  return {
    userId,
    email: studentEmail,
    data,
    profileSnapshot: buildFriendProfileSnapshot(userId, data),
  };
}

export const uploadAvatarSourcePhoto =
  createUploadAvatarSourcePhotoFunction(db, resolveAuthedAppUser);

export const getCurrentAvatarGenerationStatus =
  createGetCurrentAvatarGenerationStatusFunction(db, resolveAuthedAppUser);

export const retryCurrentAvatarGeneration =
  createRetryCurrentAvatarGenerationFunction(db, resolveAuthedAppUser);

export const getAvatarJobCandidates =
  createGetAvatarJobCandidatesFunction(db, resolveAuthedAppUser);

export const approveAvatarCandidate =
  createApproveAvatarCandidateFunction(db, resolveAuthedAppUser);

export const getChatRealProfilePhoto =
  createGetChatRealProfilePhotoFunction(db, resolveAuthedAppUser);

export const cleanupAvatarMedia =
  createCleanupAvatarMediaFunction(db, resolveAuthedAppUser);

export const onAvatarJobSourceRetention =
  createAvatarJobSourceRetentionTrigger(db);

export const onClipEmbeddingSourceRetention =
  createClipEmbeddingSourceRetentionTrigger(db);

export const recoverAvatarSourceRetention =
  createAvatarSourceRetentionRecoveryTrigger(db);

export const onAvatarGenerationStateSync =
  createAvatarGenerationStateSyncTrigger(db);

function getCallableData(request: {
  data?: unknown;
  rawRequest?: { body?: unknown } | null;
}): Record<string, unknown> {
  const direct = request.data;
  if (isRecord(direct)) {
    return direct;
  }

  const rawBody = request.rawRequest?.body;
  if (isRecord(rawBody)) {
    const nested = rawBody.data;
    if (isRecord(nested)) {
      return nested;
    }
    return rawBody;
  }

  return {};
}

/** When called without Firebase Auth, the client passes a verified Kakao access token. */
async function resolveVerifiedUserByKakaoId(
  kakaoUserId: string
): Promise<ResolvedAppUser> {
  const doc = await db.collection("users").doc(kakaoUserId).get();
  if (!doc.exists) {
    throw new HttpsError(
      "failed-precondition",
      "가입 정보를 찾을 수 없어 친구 초대를 처리할 수 없어요."
    );
  }
  const data = (doc.data() ?? {}) as Record<string, unknown>;
  const studentEmail = asNonEmptyString(data.studentEmail)?.toLowerCase() ?? "";
  const isStudentVerified = data.isStudentVerified === true;
  if (!isStudentVerified || !studentEmail.endsWith("@yonsei.ac.kr")) {
    throw new HttpsError(
      "failed-precondition",
      "학생 인증이 완료된 계정으로 다시 로그인해주세요."
    );
  }
  return {
    userId: kakaoUserId,
    email: studentEmail,
    data,
    profileSnapshot: buildFriendProfileSnapshot(kakaoUserId, data),
  };
}

/**
 * Friend invite callable: verify identity by Firebase session (request.auth) or Kakao access token
 */
async function resolveUserForFriendCallable(request: {
  auth?: { uid?: string; token?: Record<string, unknown> } | null;
  data?: unknown;
  rawRequest?: { body?: unknown } | null;
}): Promise<ResolvedAppUser> {
  if (request.auth?.uid) {
    return await resolveAuthedAppUser(request.auth);
  }
  const data = getCallableData(request);
  const accessToken = asNonEmptyString(data.kakaoAccessToken);
  logger.info("resolveUserForFriendCallable fallback auth", {
    hasAuthUid: !!request.auth?.uid,
    dataKeys: Object.keys(data),
    hasKakaoAccessToken: !!accessToken,
  });
  if (!accessToken) {
    throw new HttpsError("unauthenticated", "로그인이 필요해요.");
  }
  const kakaoUser = await verifyKakaoAccessToken(accessToken);
  return await resolveVerifiedUserByKakaoId(kakaoUser.userId);
}

function readFriendName(
  snapshot: Record<string, unknown>,
  fallback: string
): string {
  return asString(snapshot.nickname ?? fallback, fallback);
}

export const createFirebaseCustomToken = onCall(withAppCheck(), async (request) => {
  logger.info("createFirebaseCustomToken invoked", {
    hasAccessToken: !!asNonEmptyString(request.data?.accessToken),
  });
  const accessToken = asNonEmptyString(request.data?.accessToken);
  if (!accessToken) {
    throw new HttpsError("invalid-argument", "카카오 액세스 토큰이 필요해요.");
  }

  const kakaoUser = await verifyKakaoAccessToken(accessToken);
  const userRef = db.collection("users").doc(kakaoUser.userId);
  const userSnap = await userRef.get();

  let userData: Record<string, unknown>;
  if (userSnap.exists) {
    userData = (userSnap.data() ?? {}) as Record<string, unknown>;
  } else {
    await userRef.set(buildKakaoUserShell(kakaoUser.userId), { merge: true });
    userData = {};
    logger.info("createFirebaseCustomToken created missing user shell", {
      userIdHash: logHashPrefix(kakaoUser.userId),
    });
  }

  const customToken = await getAuth().createCustomToken(kakaoUser.userId, {
    kakaoUserId: kakaoUser.userId,
  });

  return {
    customToken,
    userId: kakaoUser.userId,
    isStudentVerified: userData.isStudentVerified === true,
  };
});

export const createFirebaseCustomTokenFromEmailLinkToken = onCall(
  withAppCheck(),
  async (request) => {
    const data = getCallableData(request);
    const verificationToken = asNonEmptyString(data.verificationToken);
    const requestedKakaoUserId = asNonEmptyString(data.kakaoUserId);
    const requestedStudentEmail =
      asNonEmptyString(data.studentEmail)?.toLowerCase() ?? null;

    logger.info("createFirebaseCustomTokenFromEmailLinkToken invoked", {
      hasVerificationToken: !!verificationToken,
      hasKakaoUserId: !!requestedKakaoUserId,
      hasStudentEmail: !!requestedStudentEmail,
    });

    if (!verificationToken) {
      throw new HttpsError(
        "invalid-argument",
        "\uC774\uBA54\uC77C \uC778\uC99D \uC138\uC158 \uD1A0\uD070\uC774 \uD544\uC694\uD574\uC694."
      );
    }

    const tokenRef = db.collection("emailLinkTokens").doc(verificationToken);
    const tokenSnap = await tokenRef.get();
    if (!tokenSnap.exists) {
      throw new HttpsError(
        "failed-precondition",
        "인증 세션이 없어요. 이메일 인증 링크를 다시 보내주세요."
      );
    }

    const decision = evaluateEmailLinkTokenExchange({
      tokenData: (tokenSnap.data() ?? {}) as Record<string, unknown>,
      requestedKakaoUserId,
      requestedStudentEmail,
      now: new Date(),
      isTimestamp: (value) => value instanceof Timestamp,
      toDate: (value) =>
        value instanceof Timestamp
          ? value.toDate()
          : value instanceof Date
            ? value
            : null,
    });

    if (!decision.ok) {
      logger.warn("email link token exchange rejected", {
        reason: decision.reason,
        tokenIdHash: logHashPrefix(verificationToken),
      });
      throw new HttpsError(
        EMAIL_LINK_TOKEN_REJECTION_CODES[decision.reason],
        EMAIL_LINK_TOKEN_REJECTION_MESSAGES[decision.reason]
      );
    }

    const tokenKakaoUserId = decision.kakaoUserId;
    const tokenEmail = decision.email;

    const userSnap = await db.collection("users").doc(tokenKakaoUserId).get();
    if (!userSnap.exists) {
      throw new HttpsError(
        "failed-precondition",
        "가입 정보를 찾을 수 없어요. 다시 로그인해주세요."
      );
    }

    const userData = (userSnap.data() ?? {}) as Record<string, unknown>;
    const studentEmail =
      asNonEmptyString(userData.studentEmail)?.toLowerCase() ?? "";
    const isStudentVerified = userData.isStudentVerified === true;

    if (!isStudentVerified || studentEmail != tokenEmail) {
      throw new HttpsError(
        "failed-precondition",
        "학생 인증이 아직 현재 브라우저와 연결되지 않았어요. 인증 메일 링크를 다시 열어주세요."
      );
    }

    // Claim the token atomically so two concurrent calls cannot both mint a
    // session from one mailbox proof.
    await db.runTransaction(async (tx) => {
      const fresh = await tx.get(tokenRef);
      if (!fresh.exists) {
        throw new HttpsError(
          "failed-precondition",
          "인증 세션이 없어요. 이메일 인증 링크를 다시 보내주세요."
        );
      }
      if ((fresh.data() ?? {}).exchangedAt) {
        throw new HttpsError(
          "failed-precondition",
          "이미 사용된 인증 세션이에요. 이메일 인증 링크를 다시 보내주세요."
        );
      }
      tx.update(tokenRef, {
        exchangedAt: FieldValue.serverTimestamp(),
        exchangedKakaoUserId: tokenKakaoUserId,
      });
    });

    const customToken = await getAuth().createCustomToken(tokenKakaoUserId, {
      kakaoUserId: tokenKakaoUserId,
      studentEmail,
    });

    return {
      customToken,
      userId: tokenKakaoUserId,
      isStudentVerified: true,
      studentEmail,
    };
  }
);

export const createFriendInvite = onCall(withAppCheck(), async (request) => {
  const requestData = getCallableData(request);
  logger.info("createFriendInvite request", {
    hasAuthUid: !!request.auth?.uid,
    dataKeys: Object.keys(requestData),
    hasKakaoAccessToken: !!asNonEmptyString(requestData.kakaoAccessToken),
  });
  const inviter = await resolveUserForFriendCallable(request);
  const inviteRef = db.collection("friendInvites").doc();
  const inviteToken = randomBytes(32).toString("hex");
  const expiresAt = new Date(Date.now() + FRIEND_INVITE_EXPIRY_MS);
  const shareChannel = asStringOrNull(requestData.shareChannel) ?? "kakaotalk";

  await inviteRef.set({
    inviterUserId: inviter.userId,
    inviterProfileSnapshot: inviter.profileSnapshot,
    tokenHash: hashInviteToken(inviteToken),
    status: "pending",
    shareChannel,
    createdAt: FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp(),
    expiresAt: Timestamp.fromDate(expiresAt),
    acceptedByUserId: null,
    acceptedAt: null,
    friendshipPairId: null,
    metadata: {
      inviterEmail: inviter.email,
    },
  });

  return {
    inviteId: inviteRef.id,
    inviteToken,
    inviteUrl: buildFriendInviteUrl(inviteToken),
    deepLinkPath: FRIEND_INVITE_PATH,
    expiresAt: expiresAt.toISOString(),
  };
});

export const acceptFriendInvite = onCall(withAppCheck(), async (request) => {
  const data = getCallableData(request);
  const rawToken = asNonEmptyString(data.token);
  logger.info("acceptFriendInvite invoked", {
    hasAuthUid: !!request.auth?.uid,
    dataKeys: Object.keys(data),
    hasToken: !!rawToken,
    hasKakaoAccessToken: !!asNonEmptyString(data.kakaoAccessToken),
  });
  if (!rawToken) {
    return {
      status: "invalid",
      message: "친구 초대 링크가 올바르지 않아요.",
    };
  }

  const acceptor = await resolveUserForFriendCallable(request);
  logger.info("acceptFriendInvite resolved acceptor", {
    acceptorUserIdHash: logHashPrefix(acceptor.userId),
  });
  const tokenHash = hashInviteToken(rawToken);
  const inviteQuery = await db
    .collection("friendInvites")
    .where("tokenHash", "==", tokenHash)
    .limit(1)
    .get();

  if (inviteQuery.empty) {
    return {
      status: "invalid",
      message: "유효하지 않은 친구 초대 링크예요.",
    };
  }

  const inviteRef = inviteQuery.docs[0].ref;
  const inviteId = inviteQuery.docs[0].id;
  const inviteData = (inviteQuery.docs[0].data() ?? {}) as Record<string, unknown>;
  const inviterUserId = asString(inviteData.inviterUserId ?? "");

  if (!inviterUserId) {
    return {
      status: "invalid",
      message: "친구 초대 정보가 올바르지 않아요.",
    };
  }

  if (inviterUserId === acceptor.userId) {
    return {
      status: "self_invite",
      message: "내가 만든 초대 링크로는 친구를 추가할 수 없어요.",
    };
  }

  const inviterSnapshotRaw = inviteData.inviterProfileSnapshot;
  const inviterSnapshot = isRecord(inviterSnapshotRaw)
    ? inviterSnapshotRaw
    : {};
  const otherUserName = readFriendName(inviterSnapshot, inviterUserId);
  const pairId = buildFriendPairId(inviterUserId, acceptor.userId);
  const friendshipRef = db.collection("friendships").doc(pairId);
  const inviterFriendRef = db
    .collection("users")
    .doc(inviterUserId)
    .collection("friends")
    .doc(acceptor.userId);
  const acceptorFriendRef = db
    .collection("users")
    .doc(acceptor.userId)
    .collection("friends")
    .doc(inviterUserId);

  const transactionResult = await db.runTransaction(async (transaction) => {
    const freshInviteSnap = await transaction.get(inviteRef);
    if (!freshInviteSnap.exists) {
      return {
        status: "invalid",
        message: "유효하지 않은 친구 초대 링크예요.",
      };
    }

    const freshInvite = (freshInviteSnap.data() ?? {}) as Record<string, unknown>;
    const currentStatus = asString(freshInvite.status ?? "pending", "pending");
    const acceptedByUserId = asStringOrNull(freshInvite.acceptedByUserId);
    const expiresAtRaw = freshInvite.expiresAt;
    const expiresAt =
      expiresAtRaw instanceof Timestamp ? expiresAtRaw.toDate() : null;
    const now = new Date();
    const existingFriendshipSnap = await transaction.get(friendshipRef);

    if (existingFriendshipSnap.exists) {
      if (currentStatus === "pending") {
        transaction.set(
          inviteRef,
          {
            status: "accepted",
            updatedAt: FieldValue.serverTimestamp(),
            acceptedByUserId: acceptor.userId,
            acceptedAt: FieldValue.serverTimestamp(),
            friendshipPairId: pairId,
          },
          { merge: true }
        );
      }

      return {
        status: "already_friends",
        pairId,
        otherUserId: inviterUserId,
        otherUserName,
      };
    }

    if (expiresAt && expiresAt.getTime() <= now.getTime()) {
      if (currentStatus === "pending") {
        transaction.set(
          inviteRef,
          {
            status: "expired",
            updatedAt: FieldValue.serverTimestamp(),
          },
          { merge: true }
        );
      }
      return {
        status: "expired",
        message: "친구 초대 링크가 만료되었어요.",
      };
    }

    if (currentStatus !== "pending") {
      if (currentStatus === "accepted" && acceptedByUserId === acceptor.userId) {
        return {
          status: "already_friends",
          pairId,
          otherUserId: inviterUserId,
          otherUserName,
        };
      }

      if (currentStatus === "expired") {
        return {
          status: "expired",
          message: "친구 초대 링크가 만료되었어요.",
        };
      }

      return {
        status: "invalid",
        message: "이미 사용된 친구 초대 링크예요.",
      };
    }

    const sortedUserIds = [inviterUserId, acceptor.userId].sort();
    const inviterUserRef = db.collection("users").doc(inviterUserId);
    const acceptorUserRef = db.collection("users").doc(acceptor.userId);

    transaction.set(friendshipRef, {
      pairId,
      userIds: sortedUserIds,
      createdAt: FieldValue.serverTimestamp(),
      createdFrom: "invite",
      inviteId,
      status: "active",
      createdByUserId: acceptor.userId,
    });

    transaction.set(inviterFriendRef, {
      friendUserId: acceptor.userId,
      pairId,
      createdAt: FieldValue.serverTimestamp(),
      source: "invite",
      friendProfileSnapshot: acceptor.profileSnapshot,
      inviteId,
    });

    transaction.set(acceptorFriendRef, {
      friendUserId: inviterUserId,
      pairId,
      createdAt: FieldValue.serverTimestamp(),
      source: "invite",
      friendProfileSnapshot: inviterSnapshot,
      inviteId,
    });

    transaction.set(
      inviteRef,
      {
        status: "accepted",
        updatedAt: FieldValue.serverTimestamp(),
        acceptedByUserId: acceptor.userId,
        acceptedAt: FieldValue.serverTimestamp(),
        friendshipPairId: pairId,
      },
      { merge: true }
    );

    transaction.set(
      inviterUserRef,
      {
        friendsCount: FieldValue.increment(1),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
    transaction.set(
      acceptorUserRef,
      {
        friendsCount: FieldValue.increment(1),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

    return {
      status: "accepted",
      pairId,
      otherUserId: inviterUserId,
      otherUserName,
    };
  });

  logger.info("Friend invite processed", {
    inviteId,
    inviterUserIdHash: logHashPrefix(inviterUserId),
    acceptorUserIdHash: logHashPrefix(acceptor.userId),
    pairId,
    status: transactionResult.status,
  });

  return transactionResult;
});

// =============================================================================
// Event 3-person team invite (friend selection, push, update team on acceptance)
// =============================================================================

async function assertUsersAreFriends(
  userIdA: string,
  userIdB: string
): Promise<boolean> {
  const a = await db
    .collection("users")
    .doc(userIdA)
    .collection("friends")
    .doc(userIdB)
    .get();
  return a.exists;
}

async function writeEventTeamInviteNotification(params: {
  inviteeUserId: string;
  inviterUserId: string;
  inviterName: string;
  inviteId: string;
  teamSetupId: string;
}): Promise<void> {
  const notifId = `event_team_invite_${params.inviteId}`;
  const notifRef = db
    .collection("users")
    .doc(params.inviteeUserId)
    .collection("notifications")
    .doc(notifId);
  const existing = await notifRef.get();
  if (existing.exists) return;

  await notifRef.set({
    type: "event_team_invite",
    title: "Team invite",
    body: `${params.inviterName} invited you to a 3-person team.`,
    isRead: false,
    createdAt: FieldValue.serverTimestamp(),
    actorId: params.inviterUserId,
    actorName: params.inviterName,
    deeplinkType: "event_team_invite",
    deeplinkId: params.inviteId,
    teamSetupId: params.teamSetupId,
    inviteId: params.inviteId,
  });
}

export const ensureEventTeamSetup = onCall(
  withAppCheck({
    cpu: "gcf_gen1",
    concurrency: 1,
    maxInstances: 2,
  }),
  async (request) => {
  const data = getCallableData(request);
  const leader = await resolveUserForFriendCallable(request);
  let teamSetupId = asNonEmptyString(data.teamSetupId);
  if (!teamSetupId) {
    const existingTeam = await resolveEventTeamSetupForUser(leader.userId, null);
    if (existingTeam) {
      return { teamSetupId: existingTeam.teamSetupId };
    }
  }
  if (!teamSetupId) {
    teamSetupId = randomBytes(16).toString("hex");
  }

  const ref = db.collection("eventTeamSetups").doc(teamSetupId);
  const snap = await ref.get();
  if (!snap.exists) {
    await ref.set({
      leaderUserId: leader.userId,
      acceptedUserIds: [leader.userId],
      pendingInviteeIds: [],
      updatedAt: FieldValue.serverTimestamp(),
      createdAt: FieldValue.serverTimestamp(),
    });
  } else {
    const d = (snap.data() ?? {}) as Record<string, unknown>;
    const lid = asString(d.leaderUserId ?? "");
    if (lid !== leader.userId) {
      throw new HttpsError(
        "permission-denied",
        "이 팀 설정에 접근할 수 없어요."
      );
    }
  }

  return { teamSetupId };
  }
);

export const createEventTeamInvite = onCall(withAppCheck(), async (request) => {
  const data = getCallableData(request);
  const inviter = await resolveUserForFriendCallable(request);
  const teamSetupId = asNonEmptyString(data.teamSetupId);
  const inviteeUserId = asNonEmptyString(data.inviteeUserId);
  if (!teamSetupId || !inviteeUserId) {
    throw new HttpsError(
      "invalid-argument",
      "teamSetupId와 inviteeUserId가 필요해요."
    );
  }
  if (inviteeUserId === inviter.userId) {
    throw new HttpsError("invalid-argument", "자기 자신은 초대할 수 없어요.");
  }

  const teamRef = db.collection("eventTeamSetups").doc(teamSetupId);
  const teamSnap = await teamRef.get();
  if (!teamSnap.exists) {
    throw new HttpsError("not-found", "팀 정보를 찾을 수 없어요.");
  }
  const team = (teamSnap.data() ?? {}) as Record<string, unknown>;
  const leaderUserId = asString(team.leaderUserId ?? "");
  if (leaderUserId !== inviter.userId) {
    throw new HttpsError("permission-denied", "팀 리더만 초대할 수 있어요.");
  }

  const acceptedRaw = team.acceptedUserIds;
  const acceptedUserIds = Array.isArray(acceptedRaw)
    ? acceptedRaw.map((u) => asString(u)).filter((u) => u.length > 0)
    : [];
  const pendingRaw = team.pendingInviteeIds;
  const pendingInviteeIds = Array.isArray(pendingRaw)
    ? pendingRaw.map((u) => asString(u)).filter((u) => u.length > 0)
    : [];

  if (acceptedUserIds.includes(inviteeUserId)) {
    throw new HttpsError(
      "failed-precondition",
      "이미 팀에 참여한 친구예요."
    );
  }
  if (pendingInviteeIds.includes(inviteeUserId)) {
    throw new HttpsError(
      "failed-precondition",
      "이미 초대를 보낸 친구예요."
    );
  }
  if (acceptedUserIds.length + pendingInviteeIds.length >= 3) {
    throw new HttpsError(
      "failed-precondition",
      "팀 정원이 찼어요."
    );
  }

  const friendsOk = await assertUsersAreFriends(inviter.userId, inviteeUserId);
  if (!friendsOk) {
    throw new HttpsError(
      "failed-precondition",
      "친구로 연결된 사용자만 초대할 수 있어요."
    );
  }

  const dup = await db
    .collection("eventTeamInvites")
    .where("teamSetupId", "==", teamSetupId)
    .where("inviteeUserId", "==", inviteeUserId)
    .where("status", "==", "pending")
    .limit(1)
    .get();
  if (!dup.empty) {
    throw new HttpsError(
      "failed-precondition",
      "이미 진행 중인 초대가 있어요."
    );
  }

  const inviteRef = db.collection("eventTeamInvites").doc();
  const inviteId = inviteRef.id;
  const inviterInfo = await getUserDisplayInfo(inviter.userId);

  await db.runTransaction(async (tx) => {
    const fresh = await tx.get(teamRef);
    if (!fresh.exists) {
      throw new HttpsError("not-found", "팀 정보를 찾을 수 없어요.");
    }
    const t = (fresh.data() ?? {}) as Record<string, unknown>;
    const acc = Array.isArray(t.acceptedUserIds)
      ? t.acceptedUserIds.map((u) => asString(u))
      : [];
    const pend = Array.isArray(t.pendingInviteeIds)
      ? t.pendingInviteeIds.map((u) => asString(u))
      : [];
    if (acc.length + pend.length >= 3) {
      throw new HttpsError("failed-precondition", "팀 정원이 찼어요.");
    }
    tx.set(inviteRef, {
      teamSetupId,
      inviterUserId: inviter.userId,
      inviteeUserId,
      status: "pending",
      createdAt: FieldValue.serverTimestamp(),
      respondedAt: null,
    });
    tx.update(teamRef, {
      pendingInviteeIds: FieldValue.arrayUnion(inviteeUserId),
      updatedAt: FieldValue.serverTimestamp(),
    });
  });

  await writeEventTeamInviteNotification({
    inviteeUserId,
    inviterUserId: inviter.userId,
    inviterName: inviterInfo.nickname,
    inviteId,
    teamSetupId,
  });

  await sendPushToUsers([inviteeUserId], {
    title: "팀 초대",
    body: `${inviterInfo.nickname}님이 3인 팀 참여를 요청했어요.`,
    actorUserId: inviter.userId,
    data: {
      type: "event_team_invite",
      inviteId,
      teamSetupId,
      inviterUserId: inviter.userId,
      inviterName: inviterInfo.nickname,
    },
  });

  logger.info("createEventTeamInvite ok", {
    inviteId,
    teamSetupId,
    inviteeUserIdHash: logHashPrefix(inviteeUserId),
  });

  return { inviteId, teamSetupId };
});

export const respondEventTeamInvite = onCall(withAppCheck(), async (request) => {
  const data = getCallableData(request);
  const user = await resolveUserForFriendCallable(request);
  const inviteId = asNonEmptyString(data.inviteId);
  const accept = data.accept === true;
  if (!inviteId) {
    throw new HttpsError("invalid-argument", "inviteId가 필요해요.");
  }

  const inviteRef = db.collection("eventTeamInvites").doc(inviteId);
  const invitePreview = await inviteRef.get();
  if (!invitePreview.exists) {
    return { ok: false, code: "not_found" };
  }
  const invPre = (invitePreview.data() ?? {}) as Record<string, unknown>;
  const inviterUid = asString(invPre.inviterUserId ?? "");
  const inviteeUserId = asString(invPre.inviteeUserId ?? "");
  if (inviteeUserId !== user.userId) {
    throw new HttpsError("permission-denied", "초대를 받은 본인만 응답할 수 있어요.");
  }
  let friendsStill = true;
  if (accept && inviterUid.length > 0) {
    friendsStill = await assertUsersAreFriends(inviterUid, inviteeUserId);
  }

  const result = await db.runTransaction(async (tx) => {
    const invSnap = await tx.get(inviteRef);
    if (!invSnap.exists) {
      return { ok: false as const, code: "not_found" as const };
    }
    const inv = (invSnap.data() ?? {}) as Record<string, unknown>;
    const status = asString(inv.status ?? "", "pending");
    const invitee = asString(inv.inviteeUserId ?? "");
    const teamSetupId = asString(inv.teamSetupId ?? "");

    if (invitee !== user.userId) {
      throw new HttpsError("permission-denied", "초대를 받은 본인만 응답할 수 있어요.");
    }
    if (status !== "pending") {
      return { ok: false as const, code: "already_responded" as const };
    }

    const teamRef = db.collection("eventTeamSetups").doc(teamSetupId);
    const teamSnap = await tx.get(teamRef);
    if (!teamSnap.exists) {
      return { ok: false as const, code: "team_missing" as const };
    }

    if (!accept) {
      tx.update(inviteRef, {
        status: "declined",
        respondedAt: FieldValue.serverTimestamp(),
      });
      tx.update(teamRef, {
        pendingInviteeIds: FieldValue.arrayRemove(inviteeUserId),
        updatedAt: FieldValue.serverTimestamp(),
      });
      return { ok: true as const, status: "declined" as const };
    }

    if (!friendsStill) {
      tx.update(inviteRef, {
        status: "cancelled",
        respondedAt: FieldValue.serverTimestamp(),
      });
      tx.update(teamRef, {
        pendingInviteeIds: FieldValue.arrayRemove(inviteeUserId),
        updatedAt: FieldValue.serverTimestamp(),
      });
      return { ok: false as const, code: "not_friends" as const };
    }

    const team = (teamSnap.data() ?? {}) as Record<string, unknown>;
    const acc = Array.isArray(team.acceptedUserIds)
      ? team.acceptedUserIds.map((u) => asString(u))
      : [];
    const pend = Array.isArray(team.pendingInviteeIds)
      ? team.pendingInviteeIds.map((u) => asString(u))
      : [];

    if (!pend.includes(inviteeUserId)) {
      tx.update(inviteRef, {
        status: "cancelled",
        respondedAt: FieldValue.serverTimestamp(),
      });
      return { ok: false as const, code: "stale_invite" as const };
    }

    if (acc.length >= 3) {
      tx.update(inviteRef, {
        status: "expired",
        respondedAt: FieldValue.serverTimestamp(),
      });
      tx.update(teamRef, {
        pendingInviteeIds: FieldValue.arrayRemove(inviteeUserId),
        updatedAt: FieldValue.serverTimestamp(),
      });
      return { ok: false as const, code: "team_full" as const };
    }

    if (acc.includes(inviteeUserId)) {
      tx.update(inviteRef, {
        status: "accepted",
        respondedAt: FieldValue.serverTimestamp(),
      });
      tx.update(teamRef, {
        pendingInviteeIds: FieldValue.arrayRemove(inviteeUserId),
        updatedAt: FieldValue.serverTimestamp(),
      });
      return { ok: true as const, status: "accepted" as const };
    }

    const nextAccepted = [...acc];
    if (!nextAccepted.includes(inviteeUserId)) {
      nextAccepted.push(inviteeUserId);
    }
    if (nextAccepted.length > 3) {
      tx.update(inviteRef, {
        status: "expired",
        respondedAt: FieldValue.serverTimestamp(),
      });
      tx.update(teamRef, {
        pendingInviteeIds: FieldValue.arrayRemove(inviteeUserId),
        updatedAt: FieldValue.serverTimestamp(),
      });
      return { ok: false as const, code: "team_full" as const };
    }

    tx.update(inviteRef, {
      status: "accepted",
      respondedAt: FieldValue.serverTimestamp(),
    });
    tx.update(teamRef, {
      acceptedUserIds: nextAccepted,
      pendingInviteeIds: FieldValue.arrayRemove(inviteeUserId),
      updatedAt: FieldValue.serverTimestamp(),
    });

    return { ok: true as const, status: "accepted" as const };
  });

  return result;
});

export const onEventTeamSetupWritten = onDocumentWritten(
  "eventTeamSetups/{teamSetupId}",
  async (event) => {
    const teamSetupId = asString(event.params.teamSetupId ?? "", "");
    if (!teamSetupId) {
      logger.warn("onEventTeamSetupWritten missing teamSetupId");
      return;
    }

    const afterData = event.data?.after.exists
      ? ((event.data.after.data() ?? {}) as Record<string, unknown>)
      : null;

    await syncMeetingGroupFromEventTeamSetup(teamSetupId, afterData);
  }
);

export const createTeamMeetingRequest = createTeamMeetingRequestFunction(
  db,
  resolveUserForFriendCallable
);

export const respondTeamMeetingRequest = createRespondTeamMeetingRequestFunction(
  db,
  resolveUserForFriendCallable
);

export const reportAndBlockUser = createReportAndBlockUserFunction(
  db,
  resolveUserForFriendCallable
);

export const spinSeasonMeetingRoulette = onCall(withAppCheck(), async (request) => {
  const data = getCallableData(request);
  const user = await resolveUserForFriendCallable(request);
  const requestedTeamSetupId = asNonEmptyString(data.teamSetupId);

  const resolvedTeam = await resolveEventTeamSetupForUser(
    user.userId,
    requestedTeamSetupId
  );
  if (!resolvedTeam) {
    throw new HttpsError(
      "failed-precondition",
      "현재 참여 중인 3인 팀을 찾을 수 없어요."
    );
  }

  const requestingTeamSetupId = resolvedTeam.teamSetupId;
  const requestingTeamData = resolvedTeam.data;
  const leaderUserId = asString(requestingTeamData.leaderUserId ?? "", "");
  const acceptedUserIds = buildDeterministicAcceptedOrder(
    leaderUserId,
    normalizeStringList(requestingTeamData.acceptedUserIds)
  );
  if (!acceptedUserIds.includes(user.userId)) {
    throw new HttpsError(
      "permission-denied",
      "내 팀에 속한 사용자만 룰렛을 돌릴 수 있어요."
    );
  }
  if (acceptedUserIds.length !== 3) {
    throw new HttpsError(
      "failed-precondition",
      "팀이 3명으로 완성되면 룰렛을 시작할 수 있어요."
    );
  }

  await syncMeetingGroupFromEventTeamSetup(
    requestingTeamSetupId,
    requestingTeamData
  );

  const requestingGroupRef = db
    .collection("meetingGroups")
    .doc(requestingTeamSetupId);
  const requestingGroupSnap = await requestingGroupRef.get();
  if (!requestingGroupSnap.exists || requestingGroupSnap.data() == null) {
    throw new HttpsError(
      "failed-precondition",
      "팀 추천 정보를 준비하지 못했어요. 잠시 후 다시 시도해 주세요."
    );
  }

  const requestingGroupData =
    (requestingGroupSnap.data() ?? {}) as Record<string, unknown>;
  if (!isMeetingGroupAvailable(requestingGroupData)) {
    throw new HttpsError(
      "failed-precondition",
      "현재 팀 상태로는 추천에 참여할 수 없어요."
    );
  }

  const requestingTeamSnapshot = readTeamCandidateSnapshot(
    requestingTeamSetupId,
    requestingGroupData,
    0,
    0,
    false,
    []
  );
  if (requestingTeamSnapshot == null) {
    throw new HttpsError(
      "failed-precondition",
      "팀 프로필을 아직 준비하지 못했어요. 잠시 후 다시 시도해 주세요."
    );
  }

  const dateKey = getKstCompactDateKey();
  const recommendationSource = await loadMeetingRecommendationSource(
    requestingTeamSetupId,
    dateKey
  );
  if (
    recommendationSource == null ||
    recommendationSource.candidates.length === 0
  ) {
    const skipReason = recommendationSource?.skipReason;
    throw new HttpsError(
      "failed-precondition",
      skipReason == null || skipReason.length === 0
          ? "추천 결과가 아직 준비되지 않았어요."
          : `추천 결과를 아직 사용할 수 없어요. (${skipReason})`
    );
  }

  const rawCandidates = recommendationSource.candidates.filter(
    (candidate) => candidate.groupId !== requestingTeamSetupId
  );
  const candidateGroupDocs = await loadCollectionDocsByIds(
    "meetingGroups",
    rawCandidates.map((candidate) => candidate.groupId)
  );

  const candidateTeams: EventTeamCandidateSnapshot[] = [];
  for (const candidate of rawCandidates) {
    const groupData = candidateGroupDocs[candidate.groupId];
    if (!groupData || !isMeetingGroupAvailable(groupData)) {
      continue;
    }
    const snapshot = readTeamCandidateSnapshot(
      candidate.groupId,
      groupData,
      candidate.score,
      candidate.position,
      candidate.isExplore,
      candidate.matchedPairs
    );
    if (snapshot == null || snapshot.memberCount != 3) {
      continue;
    }
    const memberUids = normalizeStringList(groupData.memberUids);
    if (sharesAnyMember(acceptedUserIds, memberUids)) {
      continue;
    }
    candidateTeams.push(snapshot);
    if (candidateTeams.length >= EVENT_TEAM_CANDIDATE_POOL_LIMIT) {
      break;
    }
  }

  if (candidateTeams.length === 0) {
    throw new HttpsError(
      "failed-precondition",
      "지금은 추천 가능한 상대 팀이 없어요."
    );
  }

  const weightedCandidateOrder = buildWeightedCandidateOrder(candidateTeams);
  const requesterLockRef = db
    .collection(EVENT_TEAM_MATCH_LOCK_COLLECTION)
    .doc(buildEventTeamMatchLockId(dateKey, requestingTeamSetupId));

  const transactionOutcome = await db.runTransaction(async (tx) => {
    const requesterLockSnap = await tx.get(requesterLockRef);
    if (requesterLockSnap.exists) {
      const requesterLockData =
        (requesterLockSnap.data() ?? {}) as Record<string, unknown>;
      const lockedResultId = asStringOrNull(requesterLockData.resultId);
      if (lockedResultId) {
        const lockedResultRef = db
          .collection(EVENT_TEAM_MATCH_COLLECTION)
          .doc(lockedResultId);
        const lockedResultSnap = await tx.get(lockedResultRef);
        if (lockedResultSnap.exists && lockedResultSnap.data() != null) {
          return {
            reusedExisting: true,
            selectedTeamIndex:
              firstInteger(lockedResultSnap.data()?.selectedGroupIndex) ?? 0,
            resultId: lockedResultSnap.id,
            result: (lockedResultSnap.data() ?? {}) as Record<string, unknown>,
          };
        }
      }
      tx.delete(requesterLockRef);
    }

    const freshRequestingGroupSnap = await tx.get(requestingGroupRef);
    if (
      !freshRequestingGroupSnap.exists ||
      freshRequestingGroupSnap.data() == null ||
      !isMeetingGroupAvailable(
        (freshRequestingGroupSnap.data() ?? {}) as Record<string, unknown>
      )
    ) {
      throw new HttpsError(
        "failed-precondition",
        "내 팀 정보가 변경되어 매칭을 진행할 수 없어요."
      );
    }

    let selectedCandidate: EventTeamCandidateSnapshot | null = null;
    let selectedCandidateLockRef: DocumentReference | null = null;

    for (const candidate of weightedCandidateOrder) {
      const candidateLockRef = db
        .collection(EVENT_TEAM_MATCH_LOCK_COLLECTION)
        .doc(buildEventTeamMatchLockId(dateKey, candidate.groupId));
      const candidateLockSnap = await tx.get(candidateLockRef);
      if (candidateLockSnap.exists) {
        const candidateLockData =
          (candidateLockSnap.data() ?? {}) as Record<string, unknown>;
        const lockedResultId = asStringOrNull(candidateLockData.resultId);
        if (lockedResultId) {
          const lockedResultSnap = await tx.get(
            db.collection(EVENT_TEAM_MATCH_COLLECTION).doc(lockedResultId)
          );
          if (lockedResultSnap.exists) {
            continue;
          }
        }
        tx.delete(candidateLockRef);
      }

      const candidateGroupRef = db
        .collection("meetingGroups")
        .doc(candidate.groupId);
      const candidateGroupSnap = await tx.get(candidateGroupRef);
      if (!candidateGroupSnap.exists || candidateGroupSnap.data() == null) {
        continue;
      }
      const candidateGroupData =
        (candidateGroupSnap.data() ?? {}) as Record<string, unknown>;
      if (!isMeetingGroupAvailable(candidateGroupData)) {
        continue;
      }
      const liveCandidate = readTeamCandidateSnapshot(
        candidate.groupId,
        candidateGroupData,
        candidate.score,
        candidate.position,
        candidate.isExplore,
        candidate.matchedPairs
      );
      if (liveCandidate == null) {
        continue;
      }

      selectedCandidate = liveCandidate;
      selectedCandidateLockRef = candidateLockRef;
      break;
    }

    if (selectedCandidate == null || selectedCandidateLockRef == null) {
      throw new HttpsError(
        "resource-exhausted",
        "이번에는 매칭 가능한 상대 팀을 찾지 못했어요."
      );
    }

    const resultRef = db.collection(EVENT_TEAM_MATCH_COLLECTION).doc();
    const selectedTeamIndex = candidateTeams.findIndex(
      (candidate) => candidate.groupId === selectedCandidate?.groupId
    );
    const createdAtIso = new Date().toISOString();
    const resultPreview = buildEventTeamMatchResultPreview({
      resultId: resultRef.id,
      dateKey,
      requestingTeamSetupId,
      requestingTeam: requestingTeamSnapshot,
      matchedTeam: selectedCandidate,
      candidateTeams,
      algorithm: recommendationSource.algorithm,
      sourcePath: recommendationSource.sourcePath,
      selectedGroupIndex: selectedTeamIndex >= 0 ? selectedTeamIndex : 0,
      createdAtIso,
    });

    tx.set(resultRef, {
      ...resultPreview,
      createdAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    });
    tx.set(requesterLockRef, {
      dateKey,
      groupId: requestingTeamSetupId,
      resultId: resultRef.id,
      peerGroupId: selectedCandidate.groupId,
      status: "locked",
      source: "slot_machine",
      algorithm: recommendationSource.algorithm,
      createdAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    });
    tx.set(selectedCandidateLockRef, {
      dateKey,
      groupId: selectedCandidate.groupId,
      resultId: resultRef.id,
      peerGroupId: requestingTeamSetupId,
      status: "locked",
      source: "slot_machine",
      algorithm: recommendationSource.algorithm,
      createdAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    });

    return {
      reusedExisting: false,
      selectedTeamIndex: selectedTeamIndex >= 0 ? selectedTeamIndex : 0,
      resultId: resultRef.id,
      result: resultPreview,
    };
  });

  return {
    ...transactionOutcome,
    viewerGroupId: requestingTeamSetupId,
  };
});

// =============================================================================
// 1) recEvents onCreate trigger
//    Rules path: recEvents/{userId}/events/{eventId}
// =============================================================================
export const onRecEventCreated = onDocumentCreated(
  "recEvents/{userId}/events/{eventId}",
  async (event) => {
    const snap = event.data;
    if (!snap) {
      logger.warn("No data in recEvent document");
      return;
    }

    const data = snap.data();
    const userId = asString(data.userId ?? event.params.userId ?? "");
    const targetUserId = asString(data.targetUserId ?? "");
    const eventType = asString(data.eventType ?? "");
    const source = asString(data.source ?? "");

    logger.info("recEvent created", {
      eventId: event.params.eventId,
      userIdHash: logHashPrefix(userId),
      targetUserIdHash: logHashPrefix(targetUserId),
      eventType,
      source,
    });

    if (!userId || !targetUserId) return;

    if (eventType === "like" || eventType === "swipe_right") {
      await checkAndCreateRecMatch(userId, targetUserId, eventType);
    }
  }
);

// =============================================================================
// 2) Profile like notification + match decision + chat room creation based on interactions
// =============================================================================
export const onInteractionCreated = onDocumentCreated(
  "interactions/{interactionId}",
  async (event) => {
    const snap = event.data;
    if (!snap) return;

    const data = snap.data();
    const fromUserId = asString(data.fromUserId ?? "");
    const toUserId = asString(data.toUserId ?? "");
    const action = asString(data.action ?? "");

    if (!fromUserId || !toUserId) return;
    if (action !== "like" && action !== "super_like") return;

    // -----------------------------------------------------------------------
    // Profile like notification: in-app notification (idempotent) + push to the other user
    // -----------------------------------------------------------------------
    if (fromUserId !== toUserId) {
      const interactionId = event.params.interactionId;
      const notificationId = `like_${interactionId}`;

      const actorInfo = await getUserDisplayInfo(fromUserId);
      const title = "New like";
      const body = `${actorInfo.nickname} liked your profile.`;

      const created = await createInAppNotification(
        toUserId,
        {
          type: "profile_like",
          title,
          body,
          deeplinkType: "received_like",
          deeplinkId: fromUserId,
          actorId: fromUserId,
          actorName: actorInfo.nickname,
        },
        notificationId
      );

      if (created) {
        await sendPushToUsers([toUserId], {
          title,
          body,
          actorUserId: fromUserId,
          data: {
            type: "profile_like",
            notificationId,
            deepLinkType: "received_like",
            actorUserId: fromUserId,
            sourceDocId: interactionId,
          },
        });

        logger.info("Profile like push + in-app notification sent", {
          fromUserIdHash: logHashPrefix(fromUserId),
          toUserIdHash: logHashPrefix(toUserId),
          action,
          notificationId,
        });
      }
    }

    // -----------------------------------------------------------------------
    // Check existing mutual like and create match
    // -----------------------------------------------------------------------
    const reverseQuery = await db
      .collection("interactions")
      .where("fromUserId", "==", toUserId)
      .where("toUserId", "==", fromUserId)
      .where("action", "in", ["like", "super_like"])
      .limit(1)
      .get();

    if (reverseQuery.empty) return;

    const [userA, userB] = await Promise.all([
      getUserDisplayInfo(fromUserId),
      getUserDisplayInfo(toUserId),
    ]);

    const systemMessage = "매칭이 성사되었어요! 먼저 인사해보세요";
    const { matchId, roomId, created } = await ensureMutualMatch(db, {
      userA: fromUserId,
      userB: toUserId,
      matchType: "mutual_like",
      chatRoom: {
        participantInfo: {
          [fromUserId]: {
            nickname: userA.nickname,
            avatarUrl: userA.avatarUrl,
          },
          [toUserId]: {
            nickname: userB.nickname,
            avatarUrl: userB.avatarUrl,
          },
        },
        systemMessage,
      },
    });

    if (!created) {
      logger.info("Match already exists", { matchId });
      return;
    }

    logger.info("Match created", {
      matchId,
      roomIdHash: roomId ? logHashPrefix(roomId) : null,
      fromUserIdHash: logHashPrefix(fromUserId),
      toUserIdHash: logHashPrefix(toUserId),
    });
  }
);

// =============================================================================
// 3) New chat message push notification
// =============================================================================
export const onChatMessageCreated = onDocumentCreated(
  "chat_rooms/{roomId}/messages/{messageId}",
  async (event) => {
    const snap = event.data;
    if (!snap) return;

    const roomId = event.params.roomId;
    const message = snap.data();

    const senderId = asString(message.senderId ?? "");
    if (!senderId || senderId === "system") return;

    const roomSnap = await db.collection("chat_rooms").doc(roomId).get();
    if (!roomSnap.exists) return;

    const room = (roomSnap.data() ?? {}) as Record<string, unknown>;
    const participantIdsRaw = room.participantIds;
    const participantIds = Array.isArray(participantIdsRaw)
      ? participantIdsRaw.map((v) => asString(v)).filter((v) => v.length > 0)
      : [];
    const targetUserIds = participantIds.filter((id) => id !== senderId);

    if (targetUserIds.length === 0) return;

    const participantInfoRaw = room.participantInfo;
    const participantInfo = isRecord(participantInfoRaw)
      ? participantInfoRaw
      : {};
    const senderInfo = participantInfo[senderId];
    const senderName = asString(
      isRecord(senderInfo) ? senderInfo.nickname : undefined,
      "새 메시지"
    );

    const body = asString(
      message.text ?? message.content ?? "메시지가 도착했어요."
    ).trim();

    await sendPushToUsers(targetUserIds, {
      title: senderName,
      body: body || "메시지가 도착했어요.",
      actorUserId: senderId,
      data: {
        type: "chat",
        roomId,
      },
    });

    logger.info("Chat push sent", {
      roomIdHash: logHashPrefix(roomId),
      senderIdHash: logHashPrefix(senderId),
      targetCount: targetUserIds.length,
    });
  }
);

// =============================================================================
// 4) Community comment/reply push + in-app notification
// =============================================================================
export const onBambooCommentCreated = onDocumentCreated(
  "bamboo_posts/{postId}/comments/{commentId}",
  async (event) => {
    const snap = event.data;
    if (!snap) return;

    const postId = event.params.postId;
    const commentId = event.params.commentId;
    const comment = snap.data();

    const authorId = asString(comment.authorId ?? "");
    const content = asString(comment.content ?? "").trim();
    const parentCommentId = asNonEmptyString(comment.parentCommentId) ?? "";

    if (!authorId) return;

    const authorInfo = await getUserDisplayInfo(authorId);

    const postSnap = await db.collection("bamboo_posts").doc(postId).get();
    if (!postSnap.exists) return;

    const post = (postSnap.data() ?? {}) as Record<string, unknown>;
    const postAuthorId = asString(post.authorId ?? "");

    // Regular comment: push + in-app notification to post author
    if (!parentCommentId) {
      if (postAuthorId && postAuthorId !== authorId) {
        await sendPushToUsers([postAuthorId], {
          title: "내 글에 새 댓글이 달렸어요",
          body: content || "\uB313\uAE00\uC774 \uB3C4\uCC29\uD588\uC5B4\uC694.",
          actorUserId: authorId,
          data: {
            type: "community_comment",
            postId,
          },
        });

        await createInAppNotification(postAuthorId, {
          type: "community_comment",
          title: "내 글에 새 댓글이 달렸어요",
          body: content || "누군가가 회원님의 글에 댓글을 남겼습니다.",
          deeplinkType: "community_post",
          deeplinkId: postId,
          actorId: authorId,
          actorName: authorInfo.nickname,
          postId,
          commentId,
        });

        logger.info("Community comment push + in-app notification sent", {
          postId,
          commentId,
          targetHash: logHashPrefix(postAuthorId),
          authorIdHash: logHashPrefix(authorId),
        });
      }
      return;
    }

    // Reply: push + in-app notification to parent comment author
    const parentSnap = await db
      .collection("bamboo_posts")
      .doc(postId)
      .collection("comments")
      .doc(parentCommentId)
      .get();

    if (!parentSnap.exists) return;

    const parent = (parentSnap.data() ?? {}) as Record<string, unknown>;
    const parentAuthorId = asString(parent.authorId ?? "");

    const targets = [parentAuthorId].filter((uid) => uid && uid !== authorId);

    if (targets.length > 0) {
      await sendPushToUsers(targets, {
        title: "내 댓글에 답글이 달렸어요",
        body: content || "답글이 도착했어요.",
        actorUserId: authorId,
        data: {
          type: "community_reply",
          postId,
        },
      });

      await createInAppNotification(parentAuthorId, {
        type: "community_reply",
        title: "내 댓글에 답글이 달렸어요",
        body: content || "누군가가 회원님의 댓글에 답글을 남겼습니다.",
        deeplinkType: "community_post",
        deeplinkId: postId,
        actorId: authorId,
        actorName: authorInfo.nickname,
        postId,
        commentId,
      });

      logger.info("Community reply push + in-app notification sent", {
        postId,
        commentId,
        parentCommentId,
        targetCount: targets.length,
        authorIdHash: logHashPrefix(authorId),
      });
    }
  }
);

// =============================================================================
// 5) Community post like push + in-app notification
// =============================================================================
export const onBambooPostLikeCreated = onDocumentCreated(
  "bamboo_posts/{postId}/likes/{userId}",
  async (event) => {
    const snap = event.data;
    if (!snap) return;

    const postId = event.params.postId;
    const likerUserId = event.params.userId;

    if (!postId || !likerUserId) return;

    const postSnap = await db.collection("bamboo_posts").doc(postId).get();
    if (!postSnap.exists) return;

    const post = (postSnap.data() ?? {}) as Record<string, unknown>;
    const postAuthorId = asString(post.authorId ?? "");

    if (!postAuthorId || postAuthorId === likerUserId) {
      return;
    }

    const existingCount = await countPostLikeNotificationsForPost(
      postAuthorId,
      postId
    );

    if (existingCount >= 5) {
      logger.info("Skipped post like notification due to 5-notification limit", {
        postId,
        postAuthorIdHash: logHashPrefix(postAuthorId),
        likerUserIdHash: logHashPrefix(likerUserId),
        existingCount,
      });
      return;
    }

    const likerInfo = await getUserDisplayInfo(likerUserId);

    await sendPushToUsers([postAuthorId], {
      title: "내 글에 좋아요가 눌렸어요",
      body: "누군가가 회원님의 글을 좋아합니다.",
      actorUserId: likerUserId,
      data: {
        type: "community_post_like",
        postId,
      },
    });

    await createInAppNotification(postAuthorId, {
      type: "community_post_like",
      title: "내 글에 좋아요가 눌렸어요",
      body: "누군가가 회원님의 글을 좋아합니다.",
      deeplinkType: "community_post",
      deeplinkId: postId,
      actorId: likerUserId,
      actorName: likerInfo.nickname,
      postId,
    });

    logger.info("Community post like push + in-app notification sent", {
      postId,
      postAuthorIdHash: logHashPrefix(postAuthorId),
      likerUserIdHash: logHashPrefix(likerUserId),
      existingCount: existingCount + 1,
    });
  }
);

// =============================================================================
// 6) Ask creation notification + push
// =============================================================================
export const onAskCreated = onDocumentCreated(
  "asks/{askId}",
  async (event) => {
    const snap = event.data;
    if (!snap) return;

    const askId = event.params.askId;
    const data = snap.data();
    const fromUserId = asString(data.fromUserId ?? "");
    const toUserId = asString(data.toUserId ?? "");

    if (!fromUserId || !toUserId || fromUserId === toUserId) return;

    const notificationId = `ask_${askId}`;
    const actorInfo = await getUserDisplayInfo(fromUserId);
    const title = "새 무물이 도착했어요";
    const body = `${actorInfo.nickname}님이 질문을 보냈어요`;

    const created = await createInAppNotification(
      toUserId,
      {
        type: "ask_received",
        title,
        body,
        deeplinkType: "asks_inbox",
        deeplinkId: askId,
        actorId: fromUserId,
        actorName: actorInfo.nickname,
      },
      notificationId
    );

    if (created) {
      await sendPushToUsers([toUserId], {
        title,
        body,
        actorUserId: fromUserId,
        data: {
          type: "ask_received",
          notificationId,
          deepLinkType: "asks_inbox",
          actorUserId: fromUserId,
          sourceDocId: askId,
        },
      });

      logger.info("Ask notification + push sent", {
        askId,
        fromUserIdHash: logHashPrefix(fromUserId),
        toUserIdHash: logHashPrefix(toUserId),
        notificationId,
      });
    }
  }
);

// =============================================================================
// 7) Deactivate chat room on unmatch (onMatchUpdated)
// =============================================================================
export const onMatchUpdated = onDocumentUpdated(
  "matches/{matchId}",
  async (event) => {
    const before = event.data?.before.data();
    const after = event.data?.after.data();

    if (!before || !after) return;

    if (before.status === "active" && after.status === "unmatched") {
      const chatRoomId = asString(
        (after as Record<string, unknown>).chatRoomId ?? ""
      );
      if (!chatRoomId) return;

      await db
        .collection("chat_rooms")
        .doc(chatRoomId)
        .set(
          {
            status: "closed",
            closedAt: FieldValue.serverTimestamp(),
            updatedAt: FieldValue.serverTimestamp(),
          },
          { merge: true }
        );

      await db
        .collection("chat_rooms")
        .doc(chatRoomId)
        .collection("messages")
        .add({
          senderId: "system",
          text: "매칭이 해제되었습니다.",
          content: "매칭이 해제되었습니다.",
          type: "system",
          readBy: [],
          createdAt: FieldValue.serverTimestamp(),
        });

      logger.info("Match closed and chat room updated", {
        matchId: event.params.matchId,
        chatRoomIdHash: logHashPrefix(chatRoomId),
      });
    }
  }
);

// =============================================================================
// 8) Auto-complete promises when goodbye safety stamp is missing for 24 hours + follow-up notification
// =============================================================================
export const autoCompleteExpiredGoodbyeSafetyStamps = onSchedule(
  {
    schedule: "every 15 minutes",
    timeZone: "Asia/Seoul",
  },
  async () => {
    const cutoff = new Date(Date.now() - 24 * 60 * 60 * 1000);
    const cutoffTimestamp = Timestamp.fromDate(cutoff);

    logger.info("autoCompleteExpiredGoodbyeSafetyStamps started", {
      cutoff: cutoff.toISOString(),
    });

    const promisesSnap = await db
      .collectionGroup("promises")
      .where("meetupCompletedAt", "<=", cutoffTimestamp)
      .get();

    for (const promiseDoc of promisesSnap.docs) {
      const roomRef = promiseDoc.ref.parent.parent;
      if (!roomRef) continue;

      const roomId = roomRef.id;
      const promiseId = promiseDoc.id;

      try {
        const result = await db.runTransaction(async (tx) => {
          const latestPromiseSnap = await tx.get(promiseDoc.ref);
          if (!latestPromiseSnap.exists) return null;
          const roomSnap = await tx.get(roomRef);

          const promiseData = (latestPromiseSnap.data() ??
            {}) as Record<string, unknown>;
          if (asString(promiseData.status, "").toLowerCase() !== "in_progress") {
            return null;
          }

          const meetupCompletedAt = asDate(promiseData.meetupCompletedAt);
          if (!meetupCompletedAt || meetupCompletedAt.getTime() > cutoff.getTime()) {
            return null;
          }

          const participantIds = asStringArray(promiseData.participantIds);
          if (participantIds.length < 2) {
            return null;
          }

          const safetyStamp = isRecord(promiseData.safetyStamp)
            ? { ...promiseData.safetyStamp }
            : {};
          const completionMode = asString(
            promiseData.completionMode ?? safetyStamp.completionMode,
            ""
          ).toLowerCase();
          if (completionMode === "auto_without_goodbye_stamp") {
            return null;
          }

          const goodbyeStampedUserIds = asStringArray(
            safetyStamp.goodbyeStampedUserIds
          );
          const missingUserIds = participantIds.filter(
            (userId) => !goodbyeStampedUserIds.includes(userId)
          );
          if (missingUserIds.length === 0) {
            return null;
          }

          const followUpByUserId = isRecord(safetyStamp.goodbyeFollowUpByUserId)
            ? { ...safetyStamp.goodbyeFollowUpByUserId }
            : {};

          for (const userId of missingUserIds) {
            const existingEntry = isRecord(followUpByUserId[userId])
              ? { ...followUpByUserId[userId] }
              : {};
            followUpByUserId[userId] = {
              ...existingEntry,
              status:
                asString(existingEntry.status, "").toLowerCase() === "submitted"
                  ? "submitted"
                  : "pending",
              notificationId:
                asStringOrNull(existingEntry.notificationId) ??
                buildSafetyStampFollowUpNotificationId(promiseId, userId),
              notificationSentAt:
                existingEntry.notificationSentAt ?? FieldValue.serverTimestamp(),
            };
          }

          const nextSafetyStamp = {
            ...safetyStamp,
            completionMode: "auto_without_goodbye_stamp",
            autoCompletedWithoutGoodbye: true,
            goodbyeAutoCompletedAt: FieldValue.serverTimestamp(),
            goodbyeFollowUpByUserId: followUpByUserId,
          };
          const completedMessageText = "헤어짐 도장이 없어 약속이 자동으로 완료되었어요";
          const messageRef = roomRef.collection("messages").doc();
          const roomData = (roomSnap.data() ?? {}) as Record<string, unknown>;
          const activePromise = isRecord(roomData.activePromise)
            ? { ...roomData.activePromise }
            : null;
          const activePromiseId = asString(activePromise?.promiseId, "");

          tx.update(promiseDoc.ref, {
            status: "completed",
            completionMode: "auto_without_goodbye_stamp",
            completedAt: FieldValue.serverTimestamp(),
            safetyStamp: nextSafetyStamp,
            updatedAt: FieldValue.serverTimestamp(),
          });

          tx.set(messageRef, {
            senderId: "system",
            text: completedMessageText,
            type: "promise_completed",
            promiseId,
            place: promiseData.place ?? null,
            placeCategory: promiseData.placeCategory ?? null,
            status: "completed",
            completionMode: "auto_without_goodbye_stamp",
            readBy: [],
            createdAt: FieldValue.serverTimestamp(),
            updatedAt: FieldValue.serverTimestamp(),
            dateTime: FieldValue.serverTimestamp(),
          });

          const roomUpdate: Record<string, unknown> = {
            lastMessage: completedMessageText,
            lastMessageAt: FieldValue.serverTimestamp(),
            updatedAt: FieldValue.serverTimestamp(),
          };

          if (activePromise && activePromiseId === promiseId) {
            roomUpdate.activePromise = {
              ...activePromise,
              status: "completed",
              completionMode: "auto_without_goodbye_stamp",
              completedAt: FieldValue.serverTimestamp(),
              safetyStamp: nextSafetyStamp,
            };
          }

          tx.set(roomRef, roomUpdate, { merge: true });

          return {
            roomId,
            promiseId,
            missingUserIds,
          };
        });

        if (!result) {
          continue;
        }

        for (const userId of result.missingUserIds) {
          const notificationId = buildSafetyStampFollowUpNotificationId(
            result.promiseId,
            userId
          );
          const title = "헤어짐 도장을 찍지 않으셨네요";
          const body = "무슨 일이 있으셨나요? 이유를 남겨주세요.";

          const created = await createInAppNotification(
            userId,
            {
              type: "safety_stamp_follow_up",
              title,
              body,
              deeplinkType: "safety_stamp_follow_up",
              deeplinkId: result.promiseId,
              roomId: result.roomId,
            },
            notificationId
          );

          if (!created) {
            continue;
          }

          await sendPushToUsers([userId], {
            title,
            body,
            data: {
              type: "safety_stamp_follow_up",
              roomId: result.roomId,
              promiseId: result.promiseId,
            },
          });
        }
      } catch (error) {
        logger.error("Failed to auto-complete expired goodbye safety stamp", {
          roomIdHash: logHashPrefix(roomId),
          promiseId,
          error: logErrorTypeCode(error),
        });
      }
    }

    logger.info("autoCompleteExpiredGoodbyeSafetyStamps finished", {
      processedCount: promisesSnap.size,
    });
  }
);

// =============================================================================
// 9) Schedule exact one-hour reminder when promise is confirmed
// =============================================================================
export const schedulePromiseReminderTask = onDocumentWritten(
  {
    document: "chat_rooms/{roomId}/promises/{promiseId}",
    region: "asia-northeast3",
  },
  async (event) => {
    const afterData = event.data?.after.data();
    if (!afterData) {
      return;
    }

    const roomId = event.params.roomId;
    const promiseId = event.params.promiseId;
    const status = asString(afterData.status, "").toLowerCase();
    if (status !== "confirmed") {
      return;
    }

    const promiseDateTime = asDate(afterData.dateTime);
    if (!promiseDateTime) {
      logger.warn("Skipped exact promise reminder scheduling: invalid dateTime", {
        roomIdHash: logHashPrefix(roomId),
        promiseId,
      });
      return;
    }

    const scheduledForMs = buildReminderScheduledForMs(
      promiseDateTime.getTime()
    );
    if (scheduledForMs <= Date.now()) {
      logger.info(
        "Skipped exact promise reminder scheduling: less than 1 hour left",
        {
          roomIdHash: logHashPrefix(roomId),
          promiseId,
          scheduledForMs,
        }
      );
      return;
    }

    const existingScheduledForMs =
      typeof afterData.exactReminderScheduledForMs === "number"
        ? afterData.exactReminderScheduledForMs
        : null;
    const existingTaskToken = asStringOrNull(afterData.exactReminderTaskToken);
    if (
      existingScheduledForMs === scheduledForMs &&
      existingTaskToken != null
    ) {
      return;
    }

    const taskToken = randomBytes(16).toString("hex");
    const payload: PromiseReminderTaskPayload = {
      roomId,
      promiseId,
      taskToken,
      scheduledForMs,
    };

    await getFunctions()
      .taskQueue(PROMISE_REMINDER_QUEUE_PATH)
      .enqueue(payload, {
        scheduleDelaySeconds: Math.max(
          0,
          Math.floor((scheduledForMs - Date.now()) / 1000)
        ),
        dispatchDeadlineSeconds: 180,
      });

    await event.data?.after.ref.set(
      {
        exactReminderScheduledForMs: scheduledForMs,
        exactReminderTaskToken: taskToken,
        exactReminderTaskCreatedAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

    logger.info("Scheduled exact promise reminder task", {
      roomIdHash: logHashPrefix(roomId),
      promiseId,
      scheduledForMs,
    });
  }
);

// =============================================================================
// 10) Dispatch scheduled one-hour-before promise push
// =============================================================================
export const dispatchPromiseReminder = onTaskDispatched(
  {
    region: "asia-northeast3",
    retryConfig: {
      maxAttempts: 3,
      minBackoffSeconds: 30,
    },
    rateLimits: {
      maxConcurrentDispatches: 20,
    },
  },
  async (request) => {
    const data = (request.data ?? {}) as Partial<PromiseReminderTaskPayload>;
    const roomId = asString(data.roomId, "");
    const promiseId = asString(data.promiseId, "");
    const taskToken = asString(data.taskToken, "");
    const scheduledForMs =
      typeof data.scheduledForMs === "number" ? data.scheduledForMs : 0;

    if (!roomId || !promiseId || !taskToken || scheduledForMs <= 0) {
      logger.warn("Invalid exact promise reminder payload", {
        hasRoomId: !!roomId,
        hasPromiseId: !!promiseId,
        hasTaskToken: !!taskToken,
        hasScheduledForMs: scheduledForMs > 0,
      });
      return;
    }

    const roomRef = db.collection("chat_rooms").doc(roomId);
    const promiseRef = roomRef.collection("promises").doc(promiseId);

    const result = await db.runTransaction(async (tx) => {
      const promiseSnap = await tx.get(promiseRef);
      if (!promiseSnap.exists) {
        return null;
      }

      const roomSnap = await tx.get(roomRef);
      const promiseData = (promiseSnap.data() ?? {}) as Record<string, unknown>;
      const roomData = (roomSnap.data() ?? {}) as Record<string, unknown>;

      if (asString(promiseData.status, "").toLowerCase() !== "confirmed") {
        return null;
      }

      if (asDate(promiseData.oneHourReminderSentAt)) {
        return null;
      }

      const currentTaskToken = asStringOrNull(promiseData.exactReminderTaskToken);
      const currentScheduledForMs =
        typeof promiseData.exactReminderScheduledForMs === "number"
          ? promiseData.exactReminderScheduledForMs
          : null;
      if (
        currentTaskToken == null ||
        currentTaskToken !== taskToken ||
        currentScheduledForMs == null ||
        currentScheduledForMs !== scheduledForMs
      ) {
        return null;
      }

      const promiseDateTime = asDate(promiseData.dateTime);
      if (!promiseDateTime) {
        return null;
      }
      if (buildReminderScheduledForMs(promiseDateTime.getTime()) !== scheduledForMs) {
        return null;
      }

      const promiseParticipantIds = asStringArray(promiseData.participantIds);
      const roomParticipantIds = asStringArray(roomData.participantIds);
      const participantIds =
        promiseParticipantIds.length > 0
          ? promiseParticipantIds
          : roomParticipantIds;
      if (participantIds.length === 0) {
        return null;
      }

      tx.update(promiseRef, {
        oneHourReminderSentAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      });

      const activePromise = isRecord(roomData.activePromise)
        ? { ...roomData.activePromise }
        : null;
      const activePromiseId = asString(activePromise?.promiseId, "");
      if (activePromise && activePromiseId === promiseId) {
        tx.set(
          roomRef,
          {
            activePromise: {
              oneHourReminderSentAt: FieldValue.serverTimestamp(),
            },
            updatedAt: FieldValue.serverTimestamp(),
          },
          { merge: true }
        );
      }

      return {
        participantIds,
        place: asStringOrNull(promiseData.place),
      };
    });

    if (!result) {
      logger.info("Skipped exact promise reminder dispatch", {
        roomIdHash: logHashPrefix(roomId),
        promiseId,
      });
      return;
    }

    await sendPushToUsers(result.participantIds, {
      title: buildUpcomingPromiseReminderTitle(result.place),
      body: "상대방 만날 때 같이 안전도장 누르는 거 잊지 말기!",
      data: {
        type: "chat",
        roomId,
        promiseId,
      },
    });

    logger.info("Dispatched exact promise reminder push", {
      roomIdHash: logHashPrefix(roomId),
      promiseId,
      participantCount: result.participantIds.length,
    });
  }
);

// =============================================================================
// 11) One-hour promise push reminder (legacy 15-minute scheduler disabled)
// =============================================================================
export const sendUpcomingPromiseReminderPushes = onSchedule(
  {
    schedule: "every 15 minutes",
    timeZone: "Asia/Seoul",
  },
  async () => {
    logger.info(
      "sendUpcomingPromiseReminderPushes skipped: exact task queue is active"
    );
  }
);

// =============================================================================
// 12) Daily 1 PM unread chat digest push + in-app notification
// =============================================================================
export const sendDailyUnreadChatDigests = onSchedule(
  {
    schedule: "0 13 * * *",
    timeZone: "Asia/Seoul",
    cpu: "gcf_gen1",
    concurrency: 1,
    maxInstances: 1,
  },
  async () => {
    const digestDate = getKstDateKey();

    logger.info("sendDailyUnreadChatDigests started", { digestDate });

    const usersSnap = await db.collection("users").get();

    for (const userDoc of usersSnap.docs) {
      const userId = userDoc.id;

      try {
        const alreadySent = await hasChatDigestForDate(userId, digestDate);
        if (alreadySent) {
          logger.info("Skipped chat digest: already sent today", {
            userIdHash: logHashPrefix(userId),
            digestDate,
          });
          continue;
        }

        const { unreadCount, previewSenderName } =
          await getUnreadChatDigestForUser(userId);

        if (unreadCount <= 0) {
          continue;
        }

        const title = "\uc77d\uc9c0 \uc54a\uc740 \uba54\uc2dc\uc9c0\uac00 \uc788\uc5b4\uc694";
        const body = previewSenderName
          ? `${previewSenderName}\ub2d8 \uc678 \uc77d\uc9c0 \uc54a\uc740 \uba54\uc2dc\uc9c0\uac00 ${unreadCount}\uac1c \uc788\uc2b5\ub2c8\ub2e4.`
          : `\uc77d\uc9c0 \uc54a\uc740 \uba54\uc2dc\uc9c0 ${unreadCount}\uac1c\uac00 \uc788\uc5b4\uc694.`;

        await sendPushToUsers([userId], {
          title,
          body,
          data: {
            type: "chat_digest",
          },
        });

        await createInAppNotification(userId, {
          type: "chat_digest",
          title,
          body,
          deeplinkType: "chat",
          digestDate,
        });

        logger.info("Daily unread chat digest sent", {
          userIdHash: logHashPrefix(userId),
          unreadCount,
          digestDate,
        });
      } catch (error) {
        logger.error("Failed to send daily unread chat digest", {
          userIdHash: logHashPrefix(userId),
          digestDate,
          error: logErrorTypeCode(error),
        });
      }
    }

    logger.info("sendDailyUnreadChatDigests finished", { digestDate });
  }
);

// =============================================================================
// Normalize and hash phone numbers (same algorithm as client)
// =============================================================================
export function normalizeKoreanPhone(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const hasPlus = trimmed.startsWith("+");
  const digits = trimmed.replace(/[^\d]/g, "");
  if (digits.length < 7) return null;

  if ((hasPlus || !digits.startsWith("0")) && digits.startsWith("82")) {
    const local = digits.substring(2);
    if (local.startsWith("10") && local.length >= 9 && local.length <= 11) {
      return `+82${local}`;
    }
    if (local.startsWith("0") && local.length >= 10 && local.length <= 12) {
      return `+82${local.substring(1)}`;
    }
    return null;
  }
  if (digits.startsWith("0")) {
    if (digits.length >= 10 && digits.length <= 11) {
      return `+82${digits.substring(1)}`;
    }
    return null;
  }
  if (digits.startsWith("10") && digits.length >= 9 && digits.length <= 11) {
    return `+82${digits}`;
  }
  return null;
}

export function hashPhoneNumber(normalized: string): string {
  return createHash("sha256").update(normalized).digest("hex");
}

// =============================================================================
// syncContactBlocks - contact block sync callable
// =============================================================================
const MAX_CONTACT_HASHES = 5000;

export const syncContactBlocks = onCall(withAppCheck(), async (request) => {
  const callerUid = request.auth?.uid;
  if (!callerUid) {
    throw new HttpsError("unauthenticated", "로그인이 필요해요.");
  }

  const data = getCallableData(request);
  const rawHashes = data.contactHashes;
  if (!Array.isArray(rawHashes)) {
    throw new HttpsError(
      "invalid-argument",
      "contactHashes 배열이 필요합니다."
    );
  }

  // dedupe + validate (64-char hex SHA-256)
  const hexPattern = /^[a-f0-9]{64}$/;
  const seen = new Set<string>();
  const validHashes: string[] = [];
  let invalidCount = 0;

  for (const h of rawHashes) {
    if (typeof h !== "string" || !hexPattern.test(h)) {
      invalidCount++;
      continue;
    }
    if (seen.has(h)) continue;
    seen.add(h);
    validHashes.push(h);
    if (validHashes.length >= MAX_CONTACT_HASHES) break;
  }

  let matchedUserCount = 0;
  let newlyBlockedPairCount = 0;
  let alreadyBlockedPairCount = 0;
  let skippedSelfCount = 0;
  const now = FieldValue.serverTimestamp();

  // process in chunks of 400 (Firestore batch limit 500)
  const CHUNK = 400;
  for (let i = 0; i < validHashes.length; i += CHUNK) {
    const chunk = validHashes.slice(i, i + CHUNK);
    const batch = db.batch();

    for (const phoneHash of chunk) {
      // 1. contactBlockedHashes/{hash}
      const cbRef = db
        .collection("users")
        .doc(callerUid)
        .collection("contactBlockedHashes")
        .doc(phoneHash);
      batch.set(
        cbRef,
        {
          phoneHash,
          source: "device_contacts",
          updatedAt: now,
          lastSeenInSyncAt: now,
        },
        { merge: true }
      );

      // 2. contactBlockedHashIndex/{hash}/owners/{uid}
      const idxRef = db
        .collection("contactBlockedHashIndex")
        .doc(phoneHash)
        .collection("owners")
        .doc(callerUid);
      batch.set(
        idxRef,
        { ownerUserId: callerUid, updatedAt: now },
        { merge: true }
      );
    }
    await batch.commit();

    // 3. phoneHashIndex lookup + mutual block
    for (const phoneHash of chunk) {
      const phiSnap = await db
        .collection("phoneHashIndex")
        .doc(phoneHash)
        .get();
      if (!phiSnap.exists) continue;

      const matchedUid = asNonEmptyString(
        (phiSnap.data() as Record<string, unknown>)?.userId
      );
      if (!matchedUid) continue;
      if (matchedUid === callerUid) {
        skippedSelfCount++;
        continue;
      }
      matchedUserCount++;

      // update contactBlockedHashes doc
      await db
        .collection("users")
        .doc(callerUid)
        .collection("contactBlockedHashes")
        .doc(phoneHash)
        .set(
          { isMatchedToAppUser: true, matchedUserId: matchedUid },
          { merge: true }
        );

      // mutual block
      const created = await ensureMutualContactBlock(
        callerUid,
        matchedUid,
        phoneHash
      );
      if (created) {
        newlyBlockedPairCount++;
      } else {
        alreadyBlockedPairCount++;
      }
    }
  }

  logger.info("syncContactBlocks completed", {
    callerUidHash: logHashPrefix(callerUid),
    submittedHashCount: rawHashes.length,
    storedHashCount: validHashes.length,
    matchedUserCount,
    newlyBlockedPairCount,
    alreadyBlockedPairCount,
    skippedSelfCount,
    invalidCount,
  });

  return {
    submittedHashCount: rawHashes.length,
    storedHashCount: validHashes.length,
    matchedUserCount,
    newlyBlockedPairCount,
    alreadyBlockedPairCount,
    skippedSelfCount,
    invalidHashCount: invalidCount,
  };
});

/**
 * Create mutual A/B block documents at blocks/{uid}/targets/{targetUid}.
 * Return false when both sides already exist (already blocked).
 */
async function ensureMutualContactBlock(
  uidA: string,
  uidB: string,
  phoneHash: string
): Promise<boolean> {
  const refAB = db
    .collection("blocks")
    .doc(uidA)
    .collection("targets")
    .doc(uidB);
  const refBA = db
    .collection("blocks")
    .doc(uidB)
    .collection("targets")
    .doc(uidA);

  const [snapAB, snapBA] = await Promise.all([refAB.get(), refBA.get()]);
  if (snapAB.exists && snapBA.exists) return false;

  const now = FieldValue.serverTimestamp();
  const batch = db.batch();
  if (!snapAB.exists) {
    batch.set(refAB, {
      fromUserId: uidA,
      toUserId: uidB,
      reason: "contact_block",
      source: "contacts",
      viaPhoneHash: true,
      createdAt: now,
    });
  }
  if (!snapBA.exists) {
    batch.set(refBA, {
      fromUserId: uidB,
      toUserId: uidA,
      reason: "contact_block",
      source: "contacts",
      viaPhoneHash: true,
      createdAt: now,
    });
  }
  await batch.commit();
  return true;
}

// =============================================================================
// onUserPhoneHashUpsert - when phoneHash is added, apply existing contact blocks mutually
// =============================================================================
export const onUserPhoneHashUpsert = onDocumentWritten(
  "userPrivate/{uid}",
  async (event) => {
    const uid = event.params.uid;
    const after = event.data?.after?.data() as
      | Record<string, unknown>
      | undefined;
    const before = event.data?.before?.data() as
      | Record<string, unknown>
      | undefined;
    if (!after) return; // deleted

    const newHash = asNonEmptyString(after.phoneHash);
    const oldHash = asNonEmptyString(before?.phoneHash);
    if (!newHash || newHash === oldHash) return;

    // 1. phoneHashIndex upsert
    await db.collection("phoneHashIndex").doc(newHash).set(
      { userId: uid, updatedAt: FieldValue.serverTimestamp() },
      { merge: true }
    );

    // 2. old hash cleanup
    if (oldHash && oldHash !== newHash) {
      await db.collection("phoneHashIndex").doc(oldHash).delete();
    }

    // 3. Find owners that have this hash in contactBlockedHashIndex
    const ownersSnap = await db
      .collection("contactBlockedHashIndex")
      .doc(newHash)
      .collection("owners")
      .get();

    if (ownersSnap.empty) return;

    for (const ownerDoc of ownersSnap.docs) {
      const ownerUid = ownerDoc.id;
      if (ownerUid === uid) continue;

      await ensureMutualContactBlock(ownerUid, uid, newHash);

      // mark matched in owner's contactBlockedHashes
      await db
        .collection("users")
        .doc(ownerUid)
        .collection("contactBlockedHashes")
        .doc(newHash)
        .set(
          { isMatchedToAppUser: true, matchedUserId: uid },
          { merge: true }
        );
    }

    logger.info("onUserPhoneHashUpsert: processed", {
      uidHash: logHashPrefix(uid),
      phoneHashPrefix: logHashPrefix(newHash),
      ownerCount: ownersSnap.size,
    });
  }
);

// =============================================================================
// saveUserPhoneHash - save phone hash after Kakao login
// =============================================================================
export const saveUserPhoneHash = onCall(withAppCheck(), async (request) => {
  const data = getCallableData(request);
  const phoneHash = asNonEmptyString(data.phoneHash);
  const phoneSource = asNonEmptyString(data.phoneSource) ?? "kakao";

  // Resolve uid from auth or kakaoAccessToken
  let uid = request.auth?.uid;
  if (!uid) {
    const accessToken = asNonEmptyString(data.kakaoAccessToken);
    if (!accessToken) {
      throw new HttpsError("unauthenticated", "로그인이 필요해요.");
    }
    const kakaoUser = await verifyKakaoAccessToken(accessToken);
    uid = kakaoUser.userId;
  }

  if (!phoneHash) {
    throw new HttpsError("invalid-argument", "phoneHash가 필요합니다.");
  }

  await db
    .collection("userPrivate")
    .doc(uid)
    .set(
      {
        phoneHash,
        phoneSource,
        phoneUpdatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

  return { success: true };
});

// =============================================================================
// Helper to check matches based on recEvents
// =============================================================================
async function checkAndCreateRecMatch(
  userA: string,
  userB: string,
  matchType: string
): Promise<string | null> {
  const reverseQuery = await db
    .collectionGroup("events")
    .where("userId", "==", userB)
    .where("targetUserId", "==", userA)
    .where("eventType", "in", ["like", "swipe_right"])
    .limit(1)
    .get();

  if (reverseQuery.empty) {
    logger.info("No mutual like found", {
      userAHash: logHashPrefix(userA),
      userBHash: logHashPrefix(userB),
    });
    return null;
  }

  const { matchId, created } = await ensureMutualMatch(db, {
    userA,
    userB,
    matchType,
  });

  if (!created) {
    logger.info("Match already exists", { matchId });
    return matchId;
  }

  logger.info("Rec match created", {
    matchId,
    userAHash: logHashPrefix(userA),
    userBHash: logHashPrefix(userB),
    matchType,
  });

  return matchId;
}
