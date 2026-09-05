/**
 * 설레연 Cloud Functions
 *
 * 트리거 목록:
 *   1) onRecEventCreated         — recEvents 이벤트 로깅 + 매치 체크
 *   2) onInteractionCreated      — interactions like/super_like → 프로필 좋아요 알림 + 매치 생성 + 채팅방
 *   3) onChatMessageCreated      — 새 채팅 메시지 푸시 알림
 *   4) onBambooCommentCreated    — 대나무숲 댓글/답글 푸시 + 인앱 알림
 *   5) onBambooPostLikeCreated   — 대나무숲 글 좋아요 푸시 + 인앱 알림
 *   6) onAskCreated              — 무물(ask) 생성 시 알림 + 푸시
 *   7) onMatchUpdated            — 매치 해제 시 채팅방 비활성화
 *   8) autoCompleteExpiredGoodbyeSafetyStamps — 헤어짐 도장 24시간 초과 약속 자동 완료 + 후속 알림
 *   9) schedulePromiseReminderTask — 약속 확정 시 정확한 1시간 전 리마인더 예약
 *   10) dispatchPromiseReminder — 예약된 약속 1시간 전 푸시 실행
 *   11) sendUpcomingPromiseReminderPushes — 기존 15분 리마인더(비활성화)
 *   12) sendDailyUnreadChatDigests — 매일 오후 1시 unread chat digest 푸시 + 인앱 알림
 */

import { setGlobalOptions } from "firebase-functions/v2";
import { defineSecret, defineString } from "firebase-functions/params";
import {
  onDocumentCreated,
  onDocumentUpdated,
} from "firebase-functions/v2/firestore";
import { onCall, HttpsError } from "firebase-functions/v2/https";
import { withAppCheck } from "./appCheckPolicy";
import { loadCampusLifeZoneActivation } from "./campusLifeZoneActivation";
import { readPersistedCampusLifeZones } from "./campusLifeZones";
import "./secureSharp";

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
  FieldPath,
  DocumentReference,
  DocumentSnapshot,
  Transaction,
} from "firebase-admin/firestore";
import { createHash, randomBytes, randomUUID } from "crypto";
import { GoogleAuth } from "google-auth-library";
import { onDocumentWritten } from "firebase-functions/v2/firestore";
import {
  buildReminderScheduledForMs,
  buildUpcomingPromiseReminderTitle,
  PROMISE_REMINDER_QUEUE_PATH,
  shouldSchedulePromiseReminderTransition,
  type PromiseReminderTaskPayload,
} from "./promiseReminder";
import {
  buildNotificationIdempotencyKey,
  createInAppNotification,
  sendPushOnce,
  sendPushToUsers,
} from "./shared/notify";

// 3:3 블라인드 취향 미팅 (callables + 예약 작업)
export * from "./blindMeeting";

// 3:3 미팅 아이스브레이킹 룰렛 (조용한 15분 알림 + 진입 검증)
export * from "./meetingIcebreaker";

// 안전도장 (서버 권위 write). 클라이언트는 더 이상 도장 배열을 직접 쓰지 않는다.
export { submitSafetyStamp, submitSafetyStampFollowUp } from "./safetyStamp";
import {
  createGetCurrentAvatarGenerationStatusFunction,
  createRetryCurrentAvatarGenerationFunction,
} from "./avatarMedia";
import {
  createApproveAvatarCandidateFunction,
  createGetAvatarJobCandidatesFunction,
} from "./avatarApproval";
import { createGetChatRealProfilePhotoFunction } from "./chatRealPhoto";
import { createCleanupAvatarMediaFunction } from "./avatarCleanup";
import {
  publicProfileProjectionChanged,
  syncPublicProfileForUser,
} from "./publicProfileSync";
import {
  isProfileVisibleForRecommendationDate,
  kstDateKey,
  nextKstDateKey,
} from "./profileVisibility";
import {
  createSeasonMeetingCancelFunction,
  createSeasonMeetingClaimReplacementFunction,
  createSeasonMeetingDepositIntentFunction,
  createSeasonMeetingRefundFunction,
  createSeasonMeetingReportNoShowFunction,
} from "./seasonMeetingOperations";
import {
  createAvatarJobSourceRetentionTrigger,
  createAvatarSourceRetentionRecoveryTrigger,
  createClipEmbeddingSourceRetentionTrigger,
} from "./avatarSourceRetention";
import { createAvatarGenerationStateSyncTrigger } from "./avatarGenerationStateSync";
import { createBeginAvatarGenerationFromOnboardingPhotosFunction } from "./avatarSourceSetAdmission";
import { createReplaceAvatarGenerationFunction } from "./avatarGenerationRecovery";
import { createAvatarClipAfterSelectionTrigger } from "./avatarClipAfterSelection";
import { isSafePublicAvatarUrl } from "./publicMediaUrlPolicy";
import {
  appleAppAccountTokenForUserId,
  verifyApplePurchase,
} from "./applePurchaseVerification";
export { isSafePublicAvatarUrl as isSafePublicMediaUrl } from "./publicMediaUrlPolicy";
import {
  createRespondTeamMeetingRequestFunction,
  createTeamMeetingRequestFunction,
} from "./teamMeetingRequest";
import { createReportAndBlockUserFunction } from "./reportAndBlock";
import { createPurgeExpiredEmailLinkTokensSchedule } from "./emailLinkTokenPurge";
import { createCompleteStudentEmailLinkFunction } from "./emailLinkCompletion";
import { createAccountDeletionRetentionPurgeSchedule } from "./accountDeletionRetentionPurge";
import {
  BAMBOO_COMMENT_OWNER_COLLECTION,
  BAMBOO_POST_OWNER_COLLECTION,
  bambooCommentOwnerDocId,
  ownerUidForNotification,
  resolveBambooOwner,
} from "./bambooOwnership";
import { createUploadOnboardingPhotoFunction } from "./onboardingPhotoUpload";
import { createSupportOperationsCallables } from "./supportOperations";
import {
  buildStudentVerificationEmail,
  decideStudentVerificationRateLimit,
  normalizeYonseiEmail,
} from "./studentVerificationEmail";
import {
  buildRecommendationExclusionPairId,
  fetchKakaoFriendServiceUserIds,
  isKakaoFriendAvoidanceEnabled,
} from "./kakaoFriendRecommendationPrivacy";
import {
  buildTermsAcceptanceRecord,
  createCompletePrimaryStudentEmailAuthFunction,
  createSendPrimaryStudentEmailLinkFunction,
  evaluateTermsAcceptancePayload,
  termsAcceptanceError,
} from "./primaryEmailAuth";
import {
  createLinkKakaoFriendIdentityFunction,
  decideKakaoCallerIdentity,
  kakaoIdentityHash,
  resolveFriendExclusionAppUserIds,
  type FriendResolutionCandidate,
} from "./kakaoIdentityLink";
import {
  buildLegacyKakaoSyncFailureRevert,
  createCreateKakaoFriendPairsOnceFunction,
  createSetKakaoFriendAvoidanceEnabledFunction,
} from "./kakaoFriendPairs";
import { createDepartmentRecommendationPrivacyTrigger } from "./departmentRecommendationPrivacy";
import {
  acceptFriendInviteByToken,
  createFriendInviteRecord,
  createTeamInviteRecord,
  previewInviteByToken,
  redeemTeamInviteByToken,
} from "./friendInvites";
import {
  assertNotBlockedEitherWay,
  respondTeamInviteCore,
} from "./eventTeamMembership";

// Firebase Admin 초기화
initializeApp();
const db = getFirestore();
// 가입 허용 기준: 연 나이 20세 이상. 예를 들어 2026년에는 2006년생까지 허용한다.
const MINIMUM_SERVICE_AGE = 20;
const PORTONE_STORE_ID = "store-ec95a751-307e-4b85-97bd-7c6fa0bbe0e2";
const ADULT_VERIFICATION_PROVIDER = "kg_inicis_via_portone";
const PORTONE_API_SECRET = defineSecret("PORTONE_API_SECRET");
const RESEND_API_KEY = defineSecret("RESEND_API_KEY");
const RESEND_FROM_EMAIL = defineString("RESEND_FROM_EMAIL", { default: "" });
const RESEND_REPLY_TO = defineString("RESEND_REPLY_TO", { default: "" });
// App Store signed transaction verification uses Apple's public certificate
// chain. The app ID and bundle ID are non-secret deployment parameters.
const APPLE_IAP_BUNDLE_ID = defineString("APPLE_IAP_BUNDLE_ID", {
  default: "com.seolleyeon.app",
});
const APPLE_IAP_APPLE_ID = defineString("APPLE_IAP_APPLE_ID", {
  // App Store Connect shows this app's Apple ID as 94727223. Override the
  // parameter if a different App Store Connect app is deployed.
  default: "94727223",
});

// 전역 옵션
setGlobalOptions({
  region: "asia-northeast3",
  maxInstances: 10,
});

// =============================================================================
// 공통 헬퍼
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

function sha256Hex(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function normalizeDigits(value: string | null): string | null {
  if (!value) return null;
  const normalized = value.replace(/\D/g, "");
  return normalized.length > 0 ? normalized : null;
}

function getKstFullYear(now = new Date()): number {
  return new Date(now.getTime() + 9 * 60 * 60 * 1000).getUTCFullYear();
}

function readBirthYear(customer: Record<string, unknown>): number | null {
  const directYear = firstInteger(customer.birthYear);
  if (directYear != null && directYear >= 1900) return directYear;

  const birthDate = firstNonEmptyString(
    customer.birthDate,
    customer.birthdate,
    customer.dateOfBirth
  );
  const digits = normalizeDigits(birthDate);
  if (!digits || digits.length < 4) return null;
  const year = Number(digits.slice(0, 4));
  return Number.isFinite(year) && year >= 1900 ? year : null;
}

function isAdultByKoreanYear(birthYear: number, now = new Date()): boolean {
  return getKstFullYear(now) - birthYear >= MINIMUM_SERVICE_AGE;
}

function readPortOneCustomer(
  verification: Record<string, unknown>
): Record<string, unknown> {
  const verifiedCustomer = readMap(verification.verifiedCustomer);
  if (Object.keys(verifiedCustomer).length > 0) return verifiedCustomer;

  const customer = readMap(verification.customer);
  if (Object.keys(customer).length > 0) return customer;

  return readMap(verification.requestedCustomer);
}

function readPortOneVerificationPayload(
  body: Record<string, unknown>
): Record<string, unknown> {
  const nested = readMap(body.identityVerification);
  return Object.keys(nested).length > 0 ? nested : body;
}

function getPortOneSecret(): string {
  return PORTONE_API_SECRET.value().trim();
}

function buildDirectRoomId(userA: string, userB: string): string {
  const ids = [userA, userB].sort();
  return `dm_${ids[0]}_${ids[1]}`;
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
  /** 생활권 (users/{uid}.onboarding.campusLifeZones). 재계산하지 않는다. */
  campusLifeZones: string[];
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

function readPhotoUrl(userData: Record<string, unknown>): string | null {
  const onboarding = readMap(userData.onboarding);
  const photoUrls = normalizeStringList(onboarding.photoUrls);
  return (
    photoUrls[0] ??
    firstNonEmptyString(
      onboarding.profileImageUrl,
      onboarding.representativeImageUrl,
      userData.profileImageUrl
    )
  );
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
    photoUrl: readPhotoUrl(userData),
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
    // canonical(sinchon/songdo) 이 아닌 값은 생활권으로 인정하지 않는다.
    campusLifeZones: readPersistedCampusLifeZones(
      onboarding.campusLifeZones ?? profileData.campusLifeZones
    ),
  };
}

/**
 * 그룹 전원이 함께 만날 수 있는 공통 생활권 (교집합).
 *
 * 다수결/대표자 기준이 아니다. 한 명이라도 생활권 정보가 없으면 빈 배열
 * (fail-closed). regionId 정책과는 완전히 독립된 별도 축이다.
 */
function sharedCampusLifeZones(zoneLists: string[][]): string[] {
  if (zoneLists.length === 0) return [] as string[];
  let shared: string[] | null = null;
  for (const zones of zoneLists) {
    const normalized = zones
      .map((zone) => zone.trim())
      .filter((zone) => zone.length > 0);
    if (normalized.length === 0) return [];
    if (shared === null) {
      shared = [...new Set(normalized)];
    } else {
      const allowed = new Set(normalized);
      shared = shared.filter((zone) => allowed.has(zone));
    }
    if (shared.length === 0) return [];
  }
  return (shared ?? []).slice().sort();
}

/** 두 팀이 함께 만날 수 있는지 (양쪽 공통 생활권의 교집합이 비어있지 않은지). */
function hasCompatibleCampusLifeZones(
  left: string[],
  right: string[]
): boolean {
  if (left.length === 0 || right.length === 0) return false;
  const rightSet = new Set(right);
  return left.some((zone) => rightSet.has(zone));
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
      displayName: asString(item.displayName ?? "알 수 없는 사용자", "알 수 없는 사용자"),
      photoUrl: asStringOrNull(item.photoUrl) ?? null,
      universityId: asStringOrNull(item.universityId) ?? null,
      universityName: asStringOrNull(item.universityName) ?? null,
      mannerScore: firstNumber(item.mannerScore),
      isVerified: Boolean(item.isVerified ?? false),
      shortIntro: asStringOrNull(item.shortIntro) ?? null,
      birthYear: firstInteger(item.birthYear),
      major: asStringOrNull(item.major) ?? null,
      campusLifeZones: readPersistedCampusLifeZones(item.campusLifeZones),
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

function buildEventTeamParticipantUids(
  requestingTeam: EventTeamCandidateSnapshot,
  matchedTeam: EventTeamCandidateSnapshot
): string[] {
  return dedupeStrings([
    ...requestingTeam.membersSnapshot.map((member) => member.uid),
    ...matchedTeam.membersSnapshot.map((member) => member.uid),
  ]).sort();
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
    groupIds: [
      params.requestingTeam.groupId,
      params.matchedTeam.groupId,
    ],
    participantUids: buildEventTeamParticipantUids(
      params.requestingTeam,
      params.matchedTeam
    ),
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
    onboarding.nickname ?? data.nickname ?? "유저",
    "유저"
  );

  const avatarUrl =
    asStringOrNull(
      onboarding.profileImageUrl ??
        onboarding.representativeImageUrl ??
        data.profileImageUrl
    ) ?? null;

  return {
    nickname,
    avatarUrl,
  };
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

function buildFriendProfileSnapshot(
  userId: string,
  data: Record<string, unknown>
): Record<string, unknown> {
  const onboardingRaw = data.onboarding;
  const onboarding = isRecord(onboardingRaw) ? onboardingRaw : {};
  const photoUrlsRaw = onboarding.photoUrls;
  const photoUrls = Array.isArray(photoUrlsRaw)
    ? photoUrlsRaw.map((value) => asString(value)).filter((value) => value)
    : [];

  const profileImageUrl = asStringOrNull(
    onboarding.profileImageUrl ??
      onboarding.representativeImageUrl ??
      (photoUrls.length > 0 ? photoUrls[0] : null) ??
      data.profileImageUrl
  );
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

/**
 * Callable 인증 사용자 → Firestore users 문서.
 *
 * 오직 `users/{request.auth.uid}` 문서 ID 조회만 사용한다 (canonical session:
 * `FirebaseAuth.currentUser.uid == appUserId`, identity-contract §1).
 *
 * F9 (terms-gate-contract §0/§8): 예전에는 `users/{authUid}` 가 없으면
 * `users.where("studentEmail","==", token.email)` 로 되짚었고, `email_verified`
 * 를 전혀 확인하지 않았다. 그 결과 `@yonsei.ac.kr` email claim 만 가진 임의의
 * Firebase 세션이 남의 계정의 canonical 주체가 되어 20여 개의 특권 callable
 * (하트 지급/차감, 1:1 채팅 잠금해제, 친구 초대, 아바타/온보딩 사진,
 * 시즌 미팅 보증금·환불)을 실행할 수 있었다.
 *
 * email → appUserId 해석은 identity-contract §7 에 따라
 * `completePrimaryStudentEmailAuth` 안에서만 일어난다. 그 경로는 서버가 쓴
 * 일회용 `emailLinkTokens` 문서를 같은 트랜잭션에서 소비한다.
 * 자기 `users/{uid}` 문서가 없는 세션은 canonical 세션이 아니므로 거부한다.
 * (firestore.rules 의 `isCanonicalAppSession()` 도 동일하게 임시 email-link
 * 세션에게 모든 상호작용 표면을 이미 거부하고 있다.)
 */
async function resolveAuthedAppUser(
  auth: { uid?: string; token?: Record<string, unknown> } | null | undefined
): Promise<ResolvedAppUser> {
  const authUid = asNonEmptyString(auth?.uid);
  if (!authUid) {
    throw new HttpsError("unauthenticated", "로그인이 필요해요.");
  }

  const doc = await db.collection("users").doc(authUid).get();

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

// Support operations use a Firebase Auth custom claim plus an immutable
// server-managed admin/{uid} record.  Keeping these callables beside the
// existing auth resolver means support cases retain the same Kakao/email-link
// identity mapping as every other user action.
const supportOperations = createSupportOperationsCallables({
  firestore: db,
  resolveAppUser: resolveAuthedAppUser,
});
export const listSupportUsers = supportOperations.listSupportUsers;
export const openSupportChat = supportOperations.openSupportChat;
export const submitInquiry = supportOperations.submitInquiry;
export const submitIssueReport = supportOperations.submitIssueReport;

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

// =============================================================================
// App Store / Google Play IAP — 하트 Consumable 지급
// =============================================================================
// 가격/하트 수량은 앱 요청에서 받지 않는다. 새 상품을 추가할 때는 StoreKit
// Configuration과 이 신뢰 mapping을 함께 변경해야 한다.
const APPLE_HEART_PRODUCT_AMOUNTS: Readonly<Record<string, number>> = {
  "seolleyeon.heart.20": 20,
  "seolleyeon.heart.40": 40,
  "seolleyeon.heart.100": 100,
  "seolleyeon.heart.220": 220,
  "seolleyeon.heart.first.50": 50,
};
const GOOGLE_PLAY_HEART_PRODUCT_AMOUNTS: Readonly<Record<string, number>> = {
  "seolleyeon.heart.20": 20,
  "seolleyeon.heart.40": 40,
  "seolleyeon.heart.100": 100,
  "seolleyeon.heart.220": 220,
  "seolleyeon.heart.first.50": 50,
};
const FIRST_PURCHASE_HEART_PRODUCT_ID = "seolleyeon.heart.first.50";
const HEART_FEATURE_COSTS = Object.freeze({
  directChat: 10,
  blindMeeting: 30,
  seasonRoulette: 20,
  recommendationRefresh: 5,
});
const GOOGLE_PLAY_PACKAGE_NAME = "com.seolleyeon.app";

function heartBalanceFromSnapshot(snapshot: DocumentSnapshot): number {
  const raw = snapshot.get("heartBalance");
  return typeof raw === "number" && Number.isFinite(raw) && raw >= 0
    ? Math.floor(raw)
    : 0;
}

function debitHeartsInTransaction(params: {
  transaction: Transaction;
  userRef: DocumentReference;
  userSnap: DocumentSnapshot;
  amount: number;
  feature: string;
}): number {
  const currentBalance = heartBalanceFromSnapshot(params.userSnap);
  if (currentBalance < params.amount) {
    throw new HttpsError(
      "resource-exhausted",
      `하트가 부족해요. ${params.feature} 이용에는 ${params.amount}H가 필요해요.`
    );
  }
  const heartBalance = currentBalance - params.amount;
  params.transaction.set(
    params.userRef,
    {
      heartBalance,
      heartBalanceUpdatedAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    },
    { merge: true }
  );
  return heartBalance;
}

type IapVerificationMode = "storekit_local" | "production";
type IapPlatform = "ios" | "android";
type IapProvider = "app_store" | "google_play";

type PurchaseVerificationInput = {
  productId: string;
  platform: IapPlatform;
  transactionId: string;
  verificationData: string;
  verificationSource: string;
};

type VerifiedPurchase = {
  receiptFingerprint: string;
  environment: "storekit_local" | "production" | "sandbox" | "google_play";
  provider: IapProvider;
  needsGooglePlayConsumption: boolean;
};

interface PurchaseVerifier {
  verify(
    input: PurchaseVerificationInput,
    expectedAccountId: string
  ): Promise<VerifiedPurchase>;
  complete(
    input: PurchaseVerificationInput,
    verified: VerifiedPurchase
  ): Promise<void>;
}

/**
 * Xcode StoreKit Configuration / Firebase Emulator 전용 verifier.
 * StoreKit local receipt는 Apple production server에서 검증할 수 없으므로,
 * 이 verifier는 명시적으로 IAP_VERIFICATION_MODE=storekit_local일 때만 쓸 수 있다.
 * production Cloud Functions의 기본값은 아래 ProductionApplePurchaseVerifier다.
 */
class LocalStoreKitPurchaseVerifier implements PurchaseVerifier {
  async verify(
    input: PurchaseVerificationInput,
    _expectedAccountId: string
  ): Promise<VerifiedPurchase> {
    if (input.verificationData.length < 16) {
      throw new HttpsError(
        "failed-precondition",
        "StoreKit 테스트 transaction 데이터를 확인하지 못했어요."
      );
    }

    return {
      // receipt 원문은 Firestore/로그에 보관하지 않는다.
      receiptFingerprint: createHash("sha256")
        .update(input.verificationData)
        .digest("hex"),
      environment: "storekit_local",
      provider: "app_store",
      needsGooglePlayConsumption: false,
    };
  }

  async complete(): Promise<void> {}
}

class ProductionApplePurchaseVerifier implements PurchaseVerifier {
  async verify(
    input: PurchaseVerificationInput,
    expectedAccountToken: string
  ): Promise<VerifiedPurchase> {
    const appAppleIdRaw = APPLE_IAP_APPLE_ID.value().trim();
    if (!/^\d+$/.test(appAppleIdRaw)) {
      throw new HttpsError(
        "failed-precondition",
        "APPLE_IAP_APPLE_ID 설정이 올바르지 않아요."
      );
    }
    const appAppleId = Number(appAppleIdRaw);
    if (!Number.isSafeInteger(appAppleId) || appAppleId <= 0) {
      throw new HttpsError(
        "failed-precondition",
        "APPLE_IAP_APPLE_ID 설정이 올바르지 않아요."
      );
    }

    const verified = await verifyApplePurchase(
      {
        productId: input.productId,
        transactionId: input.transactionId,
        signedTransaction: input.verificationData,
      },
      expectedAccountToken,
      {
        bundleId: APPLE_IAP_BUNDLE_ID.value().trim(),
        appAppleId,
      }
    );
    return {
      receiptFingerprint: verified.receiptFingerprint,
      environment: verified.environment,
      provider: "app_store",
      needsGooglePlayConsumption: false,
    };
  }

  async complete(): Promise<void> {}
}

type GooglePlayProductPurchase = {
  purchaseState?: number;
  consumptionState?: number;
  productId?: string;
  quantity?: number;
  obfuscatedExternalAccountId?: string;
};

/**
 * Google Play Developer API로 serverVerificationData(purchaseToken)를 확인한다.
 * Cloud Functions의 서비스 계정에는 Play Console의 주문/구독 관리 권한을 부여해야
 * 하며, credential은 앱이나 소스 코드에 저장하지 않는다.
 */
class GooglePlayPurchaseVerifier implements PurchaseVerifier {
  async verify(
    input: PurchaseVerificationInput,
    expectedAccountId: string
  ): Promise<VerifiedPurchase> {
    const auth = new GoogleAuth({
      scopes: ["https://www.googleapis.com/auth/androidpublisher"],
    });
    try {
      const client = await auth.getClient();
      const response = await client.request<GooglePlayProductPurchase>({
        url:
          "https://androidpublisher.googleapis.com/androidpublisher/v3/" +
          `applications/${encodeURIComponent(GOOGLE_PLAY_PACKAGE_NAME)}/purchases/products/` +
          `${encodeURIComponent(input.productId)}/tokens/` +
          encodeURIComponent(input.verificationData),
      });
      if (response.data.purchaseState !== 0) {
        throw new HttpsError(
          "failed-precondition",
          "Google Play에서 완료된 구매를 확인하지 못했어요."
        );
      }
      if (
        response.data.productId !== input.productId ||
        (response.data.quantity ?? 1) !== 1
      ) {
        throw new HttpsError(
          "failed-precondition",
          "Google Play 상품 정보가 요청과 일치하지 않아요."
        );
      }
      if (response.data.obfuscatedExternalAccountId !== expectedAccountId) {
        throw new HttpsError(
          "permission-denied",
          "Google Play 구매 계정이 현재 앱 계정과 일치하지 않아요."
        );
      }

      return {
        receiptFingerprint: createHash("sha256")
          .update(input.verificationData)
          .digest("hex"),
        environment: "google_play",
        provider: "google_play",
        needsGooglePlayConsumption: response.data.consumptionState !== 1,
      };
    } catch (error) {
      if (error instanceof HttpsError) throw error;
      logger.warn("Google Play purchase verification failed", {
        productId: input.productId,
        error: error instanceof Error ? error.message : String(error),
      });
      throw new HttpsError(
        "failed-precondition",
        "Google Play 구매 검증을 완료하지 못했어요."
      );
    }
  }

  async complete(
    input: PurchaseVerificationInput,
    verified: VerifiedPurchase
  ): Promise<void> {
    if (!verified.needsGooglePlayConsumption) return;
    const auth = new GoogleAuth({
      scopes: ["https://www.googleapis.com/auth/androidpublisher"],
    });
    try {
      const client = await auth.getClient();
      await client.request({
        method: "POST",
        url:
          "https://androidpublisher.googleapis.com/androidpublisher/v3/" +
          `applications/${encodeURIComponent(GOOGLE_PLAY_PACKAGE_NAME)}/purchases/products/` +
          `${encodeURIComponent(input.productId)}/tokens/` +
          `${encodeURIComponent(input.verificationData)}:consume`,
      });
    } catch (error) {
      logger.error("Google Play purchase consumption failed", {
        productId: input.productId,
        error: error instanceof Error ? error.message : String(error),
      });
      throw new HttpsError(
        "unavailable",
        "Google Play 결제 마무리를 완료하지 못했어요."
      );
    }
  }
}

function getIapVerificationMode(): IapVerificationMode {
  const configured = (process.env.IAP_VERIFICATION_MODE ?? "production")
    .trim()
    .toLowerCase();
  if (configured === "storekit_local") return "storekit_local";
  if (configured === "production") return "production";
  throw new HttpsError(
    "failed-precondition",
    "IAP_VERIFICATION_MODE는 production 또는 storekit_local이어야 해요."
  );
}

function createPurchaseVerifier(input: PurchaseVerificationInput): PurchaseVerifier {
  // StoreKit local verifier는 Android token에 절대 적용하지 않는다. Android는
  // Play Console 상품/License Tester 여부와 관계없이 Developer API 검증이 필수다.
  if (input.platform === "android") return new GooglePlayPurchaseVerifier();
  return getIapVerificationMode() === "storekit_local"
    ? new LocalStoreKitPurchaseVerifier()
    : new ProductionApplePurchaseVerifier();
}

function readIapRequest(request: {
  data?: unknown;
  rawRequest?: { body?: unknown } | null;
}): PurchaseVerificationInput {
  const data = getCallableData(request);
  const productId = asNonEmptyString(data.productId);
  const platformValue = asNonEmptyString(data.platform) ?? "ios";
  const platform: IapPlatform | null =
    platformValue === "ios" || platformValue === "android"
      ? platformValue
      : null;
  const transactionId = asNonEmptyString(data.transactionId);
  const verificationData = asNonEmptyString(data.verificationData);
  const verificationSource = asNonEmptyString(data.verificationSource) ?? "";

  const productAmounts =
    platform === "android"
      ? GOOGLE_PLAY_HEART_PRODUCT_AMOUNTS
      : APPLE_HEART_PRODUCT_AMOUNTS;
  if (!productId || !Object.prototype.hasOwnProperty.call(productAmounts, productId)) {
    throw new HttpsError("invalid-argument", "유효하지 않은 하트 상품이에요.");
  }
  if (!transactionId || transactionId.length > 512) {
    throw new HttpsError("invalid-argument", "유효하지 않은 transaction ID예요.");
  }
  if (!verificationData || verificationData.length > 200000) {
    throw new HttpsError("invalid-argument", "구매 검증 데이터가 올바르지 않아요.");
  }

  if (!platform) {
    throw new HttpsError("invalid-argument", "유효하지 않은 결제 플랫폼이에요.");
  }

  return {
    productId,
    platform,
    transactionId,
    verificationData,
    verificationSource,
  };
}

/**
 * StoreKit/Google Play 구매를 검증하고 단 한 번만 하트를 지급한다.
 * transaction 문서와 users/{kakaoUserId}.heartBalance 변경은 하나의 Firestore
 * transaction으로 커밋되어 이벤트 재전달/앱 강제 종료에도 중복 지급되지 않는다.
 */
export const grantPurchasedHearts = onCall(withAppCheck(), async (request) => {
  const user = await resolveAuthedAppUser(request.auth);
  const purchase = readIapRequest(request);
  const verifier = createPurchaseVerifier(purchase);
  const expectedAccountId =
    purchase.platform === "ios"
      ? appleAppAccountTokenForUserId(user.userId)
      : sha256Hex(user.userId);
  const verified = await verifier.verify(purchase, expectedAccountId);
  const productAmounts =
    purchase.platform === "android"
      ? GOOGLE_PLAY_HEART_PRODUCT_AMOUNTS
      : APPLE_HEART_PRODUCT_AMOUNTS;
  const heartAmount = productAmounts[purchase.productId];

  // iOS의 기존 key는 그대로 유지해 배포 전 transaction도 재처리하지 않는다.
  // Android에는 purchaseToken과 충돌하지 않는 provider prefix를 포함한다.
  const transactionKey = createHash("sha256")
    .update(
      purchase.platform === "android"
        ? `google_play:${purchase.transactionId}`
        : purchase.transactionId
    )
    .digest("hex");
  const transactionRef = db.collection("iapTransactions").doc(transactionKey);
  const userRef = db.collection("users").doc(user.userId);

  const result = await db.runTransaction(async (transaction) => {
    const [existing, userSnap] = await Promise.all([
      transaction.get(transactionRef),
      transaction.get(userRef),
    ]);

    if (existing.exists) {
      const existingData = (existing.data() ?? {}) as Record<string, unknown>;
      if (
        existingData.uid !== user.userId ||
        existingData.productId !== purchase.productId ||
        existingData.platform !== purchase.platform
      ) {
        throw new HttpsError(
          "already-exists",
          "이미 처리된 다른 구매 transaction이에요."
        );
      }
      return {
        granted: false,
        alreadyGranted: true,
        heartBalance: Number(existingData.heartBalanceAfter ?? 0),
      };
    }

    if (!userSnap.exists) {
      throw new HttpsError("not-found", "사용자 정보를 찾을 수 없어요.");
    }

    const purchaseCountRaw = userSnap.get("iapPurchaseCount");
    const purchaseCount =
      typeof purchaseCountRaw === "number" &&
      Number.isFinite(purchaseCountRaw) &&
      purchaseCountRaw >= 0
        ? Math.floor(purchaseCountRaw)
        : 0;
    const isFirstPurchaseOffer =
      purchase.productId === FIRST_PURCHASE_HEART_PRODUCT_ID;
    if (
      isFirstPurchaseOffer &&
      userSnap.get("firstPurchaseOfferUsed") === true
    ) {
      throw new HttpsError(
        "failed-precondition",
        "50하트 특별 상품은 계정당 한 번만 구매할 수 있어요."
      );
    }

    const currentBalance = heartBalanceFromSnapshot(userSnap);
    const heartBalance = currentBalance + heartAmount;

    transaction.set(
      userRef,
      {
        heartBalance,
        iapPurchaseCount: purchaseCount + 1,
        ...(isFirstPurchaseOffer ? { firstPurchaseOfferUsed: true } : {}),
        heartBalanceUpdatedAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
    transaction.create(transactionRef, {
      uid: user.userId,
      productId: purchase.productId,
      heartAmount,
      // Google Play purchaseToken 원문은 Firestore에 보관하지 않는다. hash와
      // transactionKey로 동일 token의 재전달을 idempotent하게 처리한다.
      ...(purchase.platform === "ios"
        ? { transactionId: purchase.transactionId }
        : { purchaseTokenHash: verified.receiptFingerprint }),
      transactionKey,
      receiptFingerprint: verified.receiptFingerprint,
      verificationSource: purchase.verificationSource,
      platform: purchase.platform,
      provider: verified.provider,
      environment: verified.environment,
      status: "granted",
      heartBalanceAfter: heartBalance,
      createdAt: FieldValue.serverTimestamp(),
    });
    return { granted: true, alreadyGranted: false, heartBalance };
  });

  // Consume only after the Firestore entitlement transaction commits. On a
  // retry, the transaction is idempotent and this resumes the unfinished Play
  // completion without granting hearts again.
  await verifier.complete(purchase, verified);
  if (purchase.platform === "android") {
    try {
      await transactionRef.set(
        {
          status: "completed",
          completedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
    } catch (error) {
      // Entitlement and Play consumption are already complete. A telemetry
      // marker failure must not turn a successful customer purchase into an
      // apparent failure response.
      logger.warn("IAP completion marker write failed", {
        transactionKey,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  logger.info("IAP hearts grant processed", {
    userId: user.userId,
    productId: purchase.productId,
    transactionKey,
    granted: result.granted,
    alreadyGranted: result.alreadyGranted,
    environment: verified.environment,
  });
  return result;
});

/**
 * 독립 리소스가 없는 기능의 멱등적 하트 차감.
 * 현재는 추천 피드 새로고침만 허용한다. 채팅·미팅·룰렛은 각 서버
 * 트랜잭션에서 리소스 생성과 차감을 함께 처리한다.
 */
export const spendHearts = onCall(withAppCheck(), async (request) => {
  const user = await resolveAuthedAppUser(request.auth);
  const data = getCallableData(request);
  const feature = asNonEmptyString(data.feature);
  const operationId = asNonEmptyString(data.operationId);
  if (feature !== "recommendation_refresh") {
    throw new HttpsError("invalid-argument", "지원하지 않는 하트 사용 기능이에요.");
  }
  if (!operationId || operationId.length > 128) {
    throw new HttpsError("invalid-argument", "사용 요청 ID가 올바르지 않아요.");
  }

  const operationKey = createHash("sha256")
    .update(`${user.userId}:${feature}:${operationId}`)
    .digest("hex");
  const spendRef = db.collection("heartTransactions").doc(operationKey);
  const userRef = db.collection("users").doc(user.userId);
  return db.runTransaction(async (transaction) => {
    const [existing, userSnap] = await Promise.all([
      transaction.get(spendRef),
      transaction.get(userRef),
    ]);
    if (existing.exists) {
      if (existing.get("uid") !== user.userId || existing.get("feature") !== feature) {
        throw new HttpsError("already-exists", "이미 사용된 요청 ID예요.");
      }
      return {
        spent: false,
        alreadySpent: true,
        heartBalance: Number(existing.get("heartBalanceAfter") ?? 0),
      };
    }
    if (!userSnap.exists) {
      throw new HttpsError("not-found", "사용자 정보를 찾을 수 없어요.");
    }
    const amount = HEART_FEATURE_COSTS.recommendationRefresh;
    const heartBalance = debitHeartsInTransaction({
      transaction,
      userRef,
      userSnap,
      amount,
      feature: "새로고침",
    });
    transaction.create(spendRef, {
      uid: user.userId,
      feature,
      amount,
      operationKey,
      heartBalanceAfter: heartBalance,
      createdAt: FieldValue.serverTimestamp(),
    });
    return { spent: true, alreadySpent: false, heartBalance };
  });
});

/** 첫 1:1 채팅방을 열 때만 10H를 차감한다. 기존 방 재진입은 무료다. */
export const unlockDirectChat = onCall(withAppCheck(), async (request) => {
  const user = await resolveAuthedAppUser(request.auth);
  const data = getCallableData(request);
  const partnerId = asNonEmptyString(data.partnerId);
  if (!partnerId || partnerId === user.userId || partnerId.length > 128) {
    throw new HttpsError("invalid-argument", "채팅 상대 정보가 올바르지 않아요.");
  }

  const [partnerSnap, forwardBlock, reverseBlock] = await Promise.all([
    db.collection("users").doc(partnerId).get(),
    db.collection("blocks").doc(user.userId).collection("targets").doc(partnerId).get(),
    db.collection("blocks").doc(partnerId).collection("targets").doc(user.userId).get(),
  ]);
  if (!partnerSnap.exists) {
    throw new HttpsError("not-found", "채팅 상대를 찾을 수 없어요.");
  }
  const partnerData = (partnerSnap.data() ?? {}) as Record<string, unknown>;
  if (
    user.data.accountType === "operations" ||
    partnerData.accountType === "operations" ||
    partnerData.isWithdrawn === true ||
    partnerData.loginDisabled === true ||
    forwardBlock.exists ||
    reverseBlock.exists
  ) {
    throw new HttpsError("permission-denied", "현재 이 상대와 채팅을 시작할 수 없어요.");
  }

  const roomId = buildDirectRoomId(user.userId, partnerId);
  const roomRef = db.collection("chat_rooms").doc(roomId);
  const userRef = db.collection("users").doc(user.userId);
  const spendRef = db
    .collection("heartTransactions")
    .doc(createHash("sha256").update(`direct_chat:${roomId}`).digest("hex"));
  const currentProfile = user.profileSnapshot;
  const partnerProfile = buildFriendProfileSnapshot(partnerId, partnerData);

  return db.runTransaction(async (transaction) => {
    const [roomSnap, userSnap] = await Promise.all([
      transaction.get(roomRef),
      transaction.get(userRef),
    ]);
    if (roomSnap.exists) {
      const participantIds = normalizeStringList(roomSnap.get("participantIds"));
      if (!participantIds.includes(user.userId)) {
        throw new HttpsError("permission-denied", "채팅방에 입장할 수 없어요.");
      }
      return {
        roomId,
        charged: false,
        heartBalance: heartBalanceFromSnapshot(userSnap),
      };
    }
    if (!userSnap.exists) {
      throw new HttpsError("not-found", "사용자 정보를 찾을 수 없어요.");
    }

    const amount = HEART_FEATURE_COSTS.directChat;
    const heartBalance = debitHeartsInTransaction({
      transaction,
      userRef,
      userSnap,
      amount,
      feature: "채팅",
    });
    const participantIds = [user.userId, partnerId].sort();
    transaction.create(roomRef, {
      roomId,
      type: "one_to_one",
      status: "active",
      participantIds,
      participantInfo: {
        [user.userId]: {
          nickname: asString(currentProfile.nickname, ""),
          avatarUrl: asString(currentProfile.profileImageUrl, ""),
        },
        [partnerId]: {
          nickname: asString(partnerProfile.nickname, ""),
          avatarUrl: asString(partnerProfile.profileImageUrl, ""),
        },
      },
      unlockedBy: user.userId,
      heartCost: amount,
      createdAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
      lastMessage: "",
      lastMessageAt: null,
    });
    transaction.create(spendRef, {
      uid: user.userId,
      feature: "direct_chat",
      resourceId: roomId,
      amount,
      heartBalanceAfter: heartBalance,
      createdAt: FieldValue.serverTimestamp(),
    });
    return { roomId, charged: true, heartBalance };
  });
});

/** Firebase Auth 없이 호출될 때: 클라이언트가 검증된 카카오 액세스 토큰을 넘김 */
/**
 * Callable identity for social / team actions: Firebase canonical session
 * ONLY. The former Kakao access-token fallback was removed — a Kakao SDK
 * session must never authenticate a team, meeting, or block action.
 */
async function resolveCallableUserFirebaseOnly(request: {
  auth?: { uid?: string; token?: Record<string, unknown> } | null;
}): Promise<ResolvedAppUser> {
  return await resolveAuthedAppUser(request.auth);
}


export const uploadOnboardingPhoto = createUploadOnboardingPhotoFunction(
  resolveAuthedAppUser,
);

export const beginAvatarGenerationFromOnboardingPhotos =
  createBeginAvatarGenerationFromOnboardingPhotosFunction(
    db,
    resolveAuthedAppUser,
  );

// needs_review / terminal failure recovery: end the current logical
// generation and release the source lock so a NEW source set can be admitted.
export const replaceAvatarGeneration = createReplaceAvatarGenerationFunction(
  db,
  resolveAuthedAppUser,
);

// CLIP recommendation is decoupled from avatar admission: the embedding job
// is enqueued only once the worker has locked the selected source.
export const onAvatarClipAfterSelection =
  createAvatarClipAfterSelectionTrigger();

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

export const createSeasonMeetingDepositIntent =
  createSeasonMeetingDepositIntentFunction(db, resolveAuthedAppUser);
export const cancelSeasonMeeting =
  createSeasonMeetingCancelFunction(db, resolveAuthedAppUser);
export const reportSeasonMeetingNoShow =
  createSeasonMeetingReportNoShowFunction(db, resolveAuthedAppUser);
export const claimSeasonMeetingReplacementSeat =
  createSeasonMeetingClaimReplacementFunction(db, resolveAuthedAppUser);
export const refundSeasonMeetingDeposit =
  createSeasonMeetingRefundFunction(db, resolveAuthedAppUser);

export const purgeExpiredEmailLinkTokens =
  createPurgeExpiredEmailLinkTokensSchedule(db);

export const purgeAccountDeletionRetention =
  createAccountDeletionRetentionPurgeSchedule(db);

export const onAvatarJobSourceRetention =
  createAvatarJobSourceRetentionTrigger(db);

export const onClipEmbeddingSourceRetention =
  createClipEmbeddingSourceRetentionTrigger(db);

export const recoverAvatarSourceRetention =
  createAvatarSourceRetentionRecoveryTrigger(db);

export const onAvatarGenerationStateSync =
  createAvatarGenerationStateSyncTrigger(db);

/** Keep publicProfiles/{uid} in sync with private users/{uid}. */
export const onUserPublicProfileSync = onDocumentWritten(
  "users/{uid}",
  async (event) => {
    const uid = asString(event.params.uid ?? "", "");
    if (!uid) return;
    const after = event.data?.after?.exists
      ? ((event.data.after.data() ?? {}) as Record<string, unknown>)
      : null;
    const before = event.data?.before?.exists
      ? ((event.data.before.data() ?? {}) as Record<string, unknown>)
      : null;
    if (!publicProfileProjectionChanged(uid, before, after)) return;
    try {
      await syncPublicProfileForUser(db, uid, after);
    } catch (error) {
      logger.error("publicProfiles sync failed", {
        uidHash: createHash("sha256").update(uid).digest("hex").slice(0, 16),
        ...((error && typeof error === "object" && "message" in error)
          ? { code: "sync_failed" }
          : { code: "sync_failed" }),
      });
    }
  },
);

/**
 * Updates the candidate-side profile setting.  The effective date is assigned
 * by the server so a client cannot make a same-day recommendation rerun apply
 * a different privacy snapshot.
 */
export const updateProfileVisibility = onCall(
  withAppCheck(),
  async (request) => {
    const user = await resolveAuthedAppUser(request.auth);
    const visible = request.data?.visible;
    if (typeof visible !== "boolean") {
      throw new HttpsError("invalid-argument", "공개 여부가 올바르지 않아요.");
    }

    const ref = db.collection("users").doc(user.userId);
    const snapshot = await ref.get();
    if (!snapshot.exists) {
      throw new HttpsError("failed-precondition", "사용자 정보를 찾을 수 없어요.");
    }
    const now = new Date();
    const currentVisible = isProfileVisibleForRecommendationDate(
      (snapshot.data() ?? {}) as Record<string, unknown>,
      kstDateKey(now),
    );
    const effectiveDateKey = nextKstDateKey(now);
    await ref.update({
      profileVisible: visible,
      profileVisibleBeforeEffectiveDate: currentVisible,
      profileVisibleEffectiveDateKey: effectiveDateKey,
      profileVisibilityUpdatedAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    });

    return { visible, effectiveDateKey };
  },
);

/** Keep same-department recommendation exclusions materialized in both directions. */
export const onDepartmentRecommendationPrivacySync =
  createDepartmentRecommendationPrivacyTrigger(db);

/**
 * New accounts cannot participate in 1:1 recommendations until the Kakao
 * friend privacy reconciliation has completed. A transaction avoids racing a
 * very fast reconciliation that may finish before this trigger is delivered.
 */
export const onUserRecommendationPrivacyBootstrap = onDocumentCreated(
  "users/{uid}",
  async (event) => {
    const uid = asString(event.params.uid ?? "", "");
    if (!uid) return;
    const ref = db.collection("users").doc(uid);
    await db.runTransaction(async (transaction) => {
      const snapshot = await transaction.get(ref);
      if (!snapshot.exists) return;
      const data = snapshot.data() ?? {};
      const updates: Record<string, unknown> = {};
      if (typeof data.kakaoFriendAvoidanceEnabled !== "boolean") {
        updates.kakaoFriendAvoidanceEnabled = false;
      }
      if (typeof data.recommendationPrivacyReady !== "boolean") {
        updates.recommendationPrivacyReady = false;
      }
      if (typeof data.kakaoFriendReconcileStatus !== "string") {
        updates.kakaoFriendReconcileStatus = "pending";
      }
      if (Object.keys(updates).length > 0) {
        transaction.set(ref, updates, { merge: true });
      }
    });
  },
);

export const createTeamMeetingRequest = createTeamMeetingRequestFunction(
  db,
  resolveCallableUserFirebaseOnly
);

export const respondTeamMeetingRequest = createRespondTeamMeetingRequestFunction(
  db,
  resolveCallableUserFirebaseOnly
);

export const reportAndBlockUser = createReportAndBlockUserFunction(
  db,
  resolveCallableUserFirebaseOnly
);

// LEGACY_KAKAO_AUTH_BACKEND_STILL_REQUIRED_FOR_OLD_CLIENTS
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
  let created = false;
  if (userSnap.exists) {
    userData = (userSnap.data() ?? {}) as Record<string, unknown>;
  } else {
    // First Kakao login: minting a custom token alone is not enough — the
    // client cannot create users/{kakaoUserId} under locked-down rules, so the
    // Admin SDK creates a minimal shell here after Kakao token verification.
    await userRef.set(buildKakaoUserShell(kakaoUser.userId), { merge: true });
    userData = {};
    created = true;
    logger.info("createFirebaseCustomToken created missing user shell");
  }

  const customToken = await getAuth().createCustomToken(kakaoUser.userId, {
    kakaoUserId: kakaoUser.userId,
  });

  return {
    customToken,
    userId: kakaoUser.userId,
    created,
    isStudentVerified: userData.isStudentVerified === true,
  };
});

// Email-link completion is intentionally separate from the Kakao token bridge.
// It accepts only a Firebase-authenticated, verified Yonsei mailbox session and
// atomically consumes the binding document before minting the Kakao-backed UID.
// LEGACY_KAKAO_AUTH_BACKEND_STILL_REQUIRED_FOR_OLD_CLIENTS
export const completeStudentEmailLink = createCompleteStudentEmailLinkFunction(
  db,
  getAuth()
);

const STUDENT_VERIFICATION_TOKEN_TTL_MS = 30 * 60 * 1000;
const STUDENT_VERIFICATION_REQUEST_TTL_MS = 31 * 24 * 60 * 60 * 1000;
const SAFE_EMAIL_REQUEST_ID = /^[A-Za-z0-9_-]{16,128}$/;
const EMAIL_LINK_PAGE_VERSION = "primary-20260902-1";

function buildStudentVerificationContinueUrl(
  token: string,
  flow: "legacy" | "primary_auth" = "legacy"
): string {
  const projectId = asNonEmptyString(process.env.GCLOUD_PROJECT) ?? "";
  const origin =
    projectId === "seolleyeon-final"
      ? "https://seolleyeon-final.web.app"
      : "https://seolleyeon.web.app";
  const url = new URL("/auth/email-link", origin);
  // Mail-app browsers can retain an already-open Hosting document even when
  // the response itself is no-store. Version every newly generated link so a
  // primary-auth mail cannot execute a pre-primary legacy page from cache.
  url.searchParams.set("v", EMAIL_LINK_PAGE_VERSION);
  if (flow === "primary_auth") {
    url.searchParams.set("flow", flow);
  }
  url.searchParams.set("t", token);
  return url.toString();
}

function timestampMs(value: unknown): number | null {
  return asDate(value)?.getTime() ?? null;
}

function requireResendFromEmail(): { from: string; replyTo?: string } {
  const from = RESEND_FROM_EMAIL.value().trim();
  const replyTo = RESEND_REPLY_TO.value().trim();
  if (!from || /[\r\n]/.test(from) || /[\r\n]/.test(replyTo)) {
    throw new HttpsError(
      "failed-precondition",
      "인증 메일 발신자 설정이 완료되지 않았어요."
    );
  }
  return replyTo ? { from, replyTo } : { from };
}

async function sendStudentVerificationEmailWithResend(params: {
  apiKey: string;
  from: string;
  replyTo?: string;
  to: string;
  requestId: string;
  actionLink: string;
}): Promise<string> {
  const message = buildStudentVerificationEmail(params.actionLink);
  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${params.apiKey}`,
      "Content-Type": "application/json",
      "Idempotency-Key": `student-verification/${params.requestId}`,
    },
    body: JSON.stringify({
      from: params.from,
      to: [params.to],
      ...(params.replyTo ? { reply_to: params.replyTo } : {}),
      subject: message.subject,
      html: message.html,
      text: message.text,
    }),
  });

  let payload: Record<string, unknown> = {};
  try {
    const parsed: unknown = await response.json();
    if (isRecord(parsed)) payload = parsed;
  } catch (_) {
    // Provider responses are deliberately not logged: they can contain an
    // email address or another value derived from the bearer action link.
  }

  if (!response.ok) {
    logger.error("student verification email provider rejected request", {
      status: response.status,
    });
    throw new HttpsError(
      "internal",
      "인증 메일을 보내지 못했어요. 잠시 후 다시 시도해주세요."
    );
  }

  return asNonEmptyString(payload.id) ?? "accepted";
}

/**
 * Generates the usual Firebase email-link credential, but delivers it through
 * Resend so the user-facing subject and content are fully owned by Seolleyeon.
 *
 * The client supplies no continue URL, token, or recipient identity other than
 * the Yonsei address. The authenticated Kakao-backed Firebase uid is the sole
 * user identity, and all request/token documents are Admin-SDK-only writes.
 */
// LEGACY_KAKAO_AUTH_BACKEND_STILL_REQUIRED_FOR_OLD_CLIENTS
export const sendStudentVerificationEmail = onCall(
  withAppCheck({
    timeoutSeconds: 30,
    memory: "256MiB",
    maxInstances: 3,
    concurrency: 10,
    secrets: [RESEND_API_KEY],
  }),
  async (request) => {
    const uid = asNonEmptyString(request.auth?.uid);
    if (!uid) {
      throw new HttpsError("unauthenticated", "로그인이 필요해요.");
    }

    const data = getCallableData(request);
    const email = normalizeYonseiEmail(data.email);
    const clientRequestId = asNonEmptyString(data.requestId);
    if (!email || !clientRequestId || !SAFE_EMAIL_REQUEST_ID.test(clientRequestId)) {
      throw new HttpsError("invalid-argument", "연세 이메일 인증 요청이 올바르지 않아요.");
    }

    // An arbitrary Firebase email-link account must not become a mail-sending
    // principal. Only the Kakao session created by createFirebaseCustomToken
    // owns users/{uid} and may request a student-verification email.
    const userSnap = await db.collection("users").doc(uid).get();
    const userData = (userSnap.data() ?? {}) as Record<string, unknown>;
    if (!userSnap.exists || asNonEmptyString(userData.kakaoUserId) !== uid) {
      throw new HttpsError("permission-denied", "로그인 세션을 다시 확인해주세요.");
    }

    // Reject an incomplete mail-provider configuration before reserving an
    // action token or consuming a user's resend quota.
    const sender = requireResendFromEmail();
    const apiKey = RESEND_API_KEY.value().trim();
    if (!apiKey) {
      throw new HttpsError("failed-precondition", "인증 메일 발송 설정이 완료되지 않았어요.");
    }
    const now = new Date();
    const nowMs = now.getTime();
    const requestRef = db
      .collection("studentVerificationEmailRequests")
      .doc(sha256Hex(`request:${uid}:${clientRequestId}`));
    const emailRateRef = db
      .collection("studentVerificationEmailRateLimits")
      .doc(sha256Hex(`email:${email}`));
    const emailHash = sha256Hex(email);

    const reservation = await db.runTransaction(async (tx) => {
      const existingRequest = await tx.get(requestRef);
      if (existingRequest.exists) {
        const existing = (existingRequest.data() ?? {}) as Record<string, unknown>;
        if (
          existing.uid !== uid ||
          existing.emailHash !== emailHash ||
          existing.clientRequestId !== clientRequestId
        ) {
          throw new HttpsError("permission-denied", "인증 요청을 확인할 수 없어요.");
        }
        return {
          existing: true,
          status: asNonEmptyString(existing.status) ?? "preparing",
          actionLink: asNonEmptyString(existing.actionLink),
          token: asNonEmptyString(existing.token),
        };
      }

      const emailRateSnap = await tx.get(emailRateRef);
      const emailRate = (emailRateSnap.data() ?? {}) as Record<string, unknown>;
      const emailDecision = decideStudentVerificationRateLimit(
        {
          minuteWindowStartedAtMs: timestampMs(emailRate.minuteWindowStartedAt),
          minuteRequestCount:
            typeof emailRate.minuteRequestCount === "number"
              ? emailRate.minuteRequestCount
              : null,
          dayWindowStartedAtMs: timestampMs(emailRate.dayWindowStartedAt),
          dayRequestCount:
            typeof emailRate.dayRequestCount === "number" ? emailRate.dayRequestCount : null,
        },
        nowMs
      );
      if (!emailDecision.allowed) {
        throw new HttpsError(
          "resource-exhausted",
          "인증 메일은 잠시 후 다시 보낼 수 있어요."
        );
      }

      const token = randomUUID();
      const expiresAt = Timestamp.fromMillis(nowMs + STUDENT_VERIFICATION_TOKEN_TTL_MS);
      const rateUpdate = (decision: Extract<typeof emailDecision, { allowed: true }>) => ({
        minuteWindowStartedAt: Timestamp.fromMillis(decision.minuteWindowStartedAtMs),
        minuteRequestCount: decision.minuteRequestCount,
        dayWindowStartedAt: Timestamp.fromMillis(decision.dayWindowStartedAtMs),
        dayRequestCount: decision.dayRequestCount,
        updatedAt: Timestamp.fromMillis(nowMs),
      });

      // This keeps recipient rate-limits and the request reservation transactional.
      // No client can create these docs under Firestore rules.
      tx.set(emailRateRef, rateUpdate(emailDecision), { merge: true });
      tx.set(db.collection("emailLinkTokens").doc(token), {
        email,
        kakaoUserId: uid,
        createdAt: Timestamp.fromMillis(nowMs),
        expiresAt,
      });
      tx.set(requestRef, {
        uid,
        emailHash,
        clientRequestId,
        token,
        status: "preparing",
        createdAt: Timestamp.fromMillis(nowMs),
        expiresAt,
        purgeAt: Timestamp.fromMillis(nowMs + STUDENT_VERIFICATION_REQUEST_TTL_MS),
      });
      return { existing: false, status: "preparing", actionLink: null, token };
    });

    if (reservation.status === "sent") {
      return { accepted: true, duplicate: true };
    }
    if (!reservation.token) {
      throw new HttpsError("failed-precondition", "인증 요청이 만료됐어요. 다시 시도해주세요.");
    }

    let actionLink = reservation.actionLink;
    if (!actionLink) {
      if (reservation.existing) {
        // A simultaneous call with the same id is already generating the
        // action link. Do not generate a different link under the same Resend
        // idempotency key; the client can safely retry shortly.
        throw new HttpsError("aborted", "인증 메일을 준비 중이에요. 잠시 후 다시 시도해주세요.");
      }
      try {
        actionLink = await getAuth().generateSignInWithEmailLink(email, {
          url: buildStudentVerificationContinueUrl(reservation.token),
          handleCodeInApp: true,
          iOS: { bundleId: "com.seolleyeon.app" },
          android: {
            packageName: "com.seolleyeon.app",
            installApp: true,
            minimumVersion: "21",
          },
        });
        await requestRef.update({
          actionLink,
          status: "sending",
          updatedAt: Timestamp.fromMillis(Date.now()),
        });
      } catch (error) {
        await requestRef.set(
          { status: "generation_failed", updatedAt: Timestamp.fromMillis(Date.now()) },
          { merge: true }
        );
        logger.error("student verification Firebase action-link generation failed", {
          error: error instanceof Error ? error.name : "unknown",
        });
        throw new HttpsError(
          "internal",
          "인증 링크를 만들지 못했어요. 잠시 후 다시 시도해주세요."
        );
      }
    }

    try {
      const providerMessageId = await sendStudentVerificationEmailWithResend({
        apiKey,
        from: sender.from,
        replyTo: sender.replyTo,
        to: email,
        requestId: clientRequestId,
        actionLink,
      });
      // The bearer link is no longer needed on our server after Resend accepts
      // it. Retain only a provider id/hash for delivery troubleshooting.
      await requestRef.set(
        {
          status: "sent",
          providerMessageId,
          sentAt: Timestamp.fromMillis(Date.now()),
          updatedAt: Timestamp.fromMillis(Date.now()),
          actionLink: FieldValue.delete(),
        },
        { merge: true }
      );
      logger.info("student verification email accepted by provider", {
        requestIdHash: sha256Hex(clientRequestId).slice(0, 12),
        uidHash: sha256Hex(uid).slice(0, 12),
      });
      return { accepted: true, duplicate: false };
    } catch (error) {
      await requestRef.set(
        { status: "sending_unknown", updatedAt: Timestamp.fromMillis(Date.now()) },
        { merge: true }
      );
      if (error instanceof HttpsError) throw error;
      logger.error("student verification email provider call failed", {
        error: error instanceof Error ? error.name : "unknown",
      });
      throw new HttpsError(
        "internal",
        "인증 메일을 보내지 못했어요. 잠시 후 다시 시도해주세요."
      );
    }
  }
);

// =============================================================================
// Yonsei-email-primary auth (identity contract §4) — the new canonical flow.
// The verified mailbox is the PRIMARY credential; Kakao is friend-exclusion
// authorization only (linkKakaoFriendIdentity).
// =============================================================================

export const sendPrimaryStudentEmailLink = createSendPrimaryStudentEmailLinkFunction({
  db,
  secrets: [RESEND_API_KEY],
  requireSender: requireResendFromEmail,
  readApiKey: () => RESEND_API_KEY.value().trim(),
  generateActionLink: (email, token) =>
    getAuth().generateSignInWithEmailLink(email, {
      url: buildStudentVerificationContinueUrl(token, "primary_auth"),
      handleCodeInApp: true,
      iOS: { bundleId: "com.seolleyeon.app" },
      android: {
        packageName: "com.seolleyeon.app",
        installApp: true,
        minimumVersion: "21",
      },
    }),
  deliverEmail: sendStudentVerificationEmailWithResend,
});

export const completePrimaryStudentEmailAuth =
  createCompletePrimaryStudentEmailAuthFunction(db, getAuth());

/**
 * Re-consent for an already-signed-in canonical user whose accepted terms
 * version went stale (terms-gate contract §6). Required because
 * `users/{uid}.termsAcceptance` is server-owned: it is absent from
 * firestore.rules entirely, so the client cannot write it.
 *
 * Canonical-only: the caller must already hold a session; this endpoint never
 * creates an account and never resolves an identity from an email claim.
 * Idempotent — re-sending the same version converges on the same state.
 */
export const recordTermsAcceptance = onCall(
  withAppCheck({ timeoutSeconds: 30, memory: "256MiB" }),
  async (request) => {
    const uid =
      typeof request.auth?.uid === "string" ? request.auth.uid.trim() : "";
    if (!uid) {
      throw new HttpsError("unauthenticated", "로그인이 필요해요.");
    }

    const userRef = db.collection("users").doc(uid);
    const userSnapshot = await userRef.get();
    if (!userSnapshot.exists) {
      throw new HttpsError(
        "failed-precondition",
        "계정 정보를 확인할 수 없어요. 고객센터로 문의해주세요.",
        { detail: "identity_conflict" }
      );
    }

    // Same validator as the pre-auth path (contract §4): fail closed, optional
    // consents default to false, unknown document ids are ignored.
    const decision = evaluateTermsAcceptancePayload(request.data);
    if (!decision.ok) {
      throw termsAcceptanceError(decision.reason);
    }

    await userRef.set(
      {
        termsAcceptance: buildTermsAcceptanceRecord({
          version: decision.version,
          optionalConsents: decision.optionalConsents,
          source: "authenticated_reconsent",
        }),
      },
      { merge: true }
    );

    // Never log the acceptance payload itself.
    logger.info("recordTermsAcceptance stored", {
      uidHash: sha256Hex(uid).slice(0, 12),
      version: decision.version,
    });
    return { recorded: true, version: decision.version };
  }
);

export const linkKakaoFriendIdentity = createLinkKakaoFriendIdentityFunction({
  db,
  verifyKakaoAccessToken: (accessToken) => verifyKakaoAccessToken(accessToken),
});

async function fetchPortOneIdentityVerification(
  identityVerificationId: string,
  apiSecret: string
): Promise<Record<string, unknown>> {
  const response = await fetch(
    `https://api.portone.io/identity-verifications/${encodeURIComponent(
      identityVerificationId
    )}`,
    {
      method: "GET",
      headers: {
        "Authorization": `PortOne ${apiSecret}`,
        "Content-Type": "application/json",
      },
    }
  );

  const rawBody = await response.text();
  let parsed: unknown = {};
  if (rawBody.trim().length > 0) {
    try {
      parsed = JSON.parse(rawBody);
    } catch {
      parsed = { message: rawBody };
    }
  }

  if (!response.ok) {
    logger.warn("PortOne identity verification lookup failed", {
      status: response.status,
      identityVerificationId,
      body: parsed,
    });
    throw new HttpsError(
      "failed-precondition",
      "포트원 본인인증 결과를 확인하지 못했어요."
    );
  }

  if (!isRecord(parsed)) {
    throw new HttpsError(
      "failed-precondition",
      "포트원 본인인증 응답 형식이 올바르지 않아요."
    );
  }

  return readPortOneVerificationPayload(parsed);
}

async function assertIdentityVerificationNotReused(
  uid: string,
  identityVerificationId: string
): Promise<void> {
  const reused = await db
    .collection("userPrivateVerifications")
    .where("identityVerificationId", "==", identityVerificationId)
    .limit(1)
    .get();

  if (!reused.empty && reused.docs[0].id !== uid) {
    throw new HttpsError(
      "already-exists",
      "이미 다른 계정에 연결된 본인인증 세션입니다."
    );
  }
}

async function assertUniqueIdentityNotReused(
  uid: string,
  ciHash: string | null,
  diHash: string | null,
  uniqueKeyHash: string | null
): Promise<void> {
  const checks = [
    ["ciHash", ciHash],
    ["diHash", diHash],
    ["uniqueKeyHash", uniqueKeyHash],
  ] as const;

  for (const [field, value] of checks) {
    if (!value) continue;
    const snap = await db
      .collection("userPrivateVerifications")
      .where(field, "==", value)
      .limit(1)
      .get();
    if (!snap.empty && snap.docs[0].id !== uid) {
      throw new HttpsError(
        "already-exists",
        "이미 다른 계정에 연결된 본인인증 정보입니다."
      );
    }
  }
}

export const verifyAdultIdentityAfterLogin = onCall(
  withAppCheck({ secrets: [PORTONE_API_SECRET] }),
  async (request) => {
    const uid = request.auth?.uid;
    if (!uid) {
      throw new HttpsError("unauthenticated", "Firebase 로그인이 필요해요.");
    }

    const data = getCallableData(request);
    const identityVerificationId = asNonEmptyString(
      data.identityVerificationId
    );
    const identityVerificationTxId =
      asNonEmptyString(data.identityVerificationTxId) ?? null;

    if (!identityVerificationId) {
      throw new HttpsError(
        "invalid-argument",
        "identityVerificationId가 필요합니다."
      );
    }

    const isEmulator = process.env.FUNCTIONS_EMULATOR === "true";
    const isMock = identityVerificationId.startsWith("mock-");
    const apiSecret = getPortOneSecret();

    if (!apiSecret && !(isEmulator && isMock)) {
      throw new HttpsError(
        "failed-precondition",
        "PORTONE_API_SECRET 서버 Secret이 설정되지 않았습니다."
      );
    }

    await assertIdentityVerificationNotReused(uid, identityVerificationId);

    const verification = isEmulator && isMock
      ? {
        status: "VERIFIED",
        id: identityVerificationId,
        verifiedCustomer: {
          name: "개발용 테스트",
          phoneNumber: "01012345678",
          birthDate: "20000101",
          ci: `mock-ci-${uid}`,
          di: `mock-di-${uid}`,
        },
      }
      : await fetchPortOneIdentityVerification(identityVerificationId, apiSecret);

    const status = asString(verification.status, "");
    if (status !== "VERIFIED") {
      await db.collection("users").doc(uid).set(
        {
          adultVerified: false,
          realNameVerified: false,
          registrationStatus: "adult_verification_required",
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
      throw new HttpsError(
        "failed-precondition",
        "완료된 본인인증 결과가 아니에요."
      );
    }

    const returnedStoreId = firstNonEmptyString(
      verification.storeId,
      readMap(verification.store).id
    );
    if (returnedStoreId && returnedStoreId !== PORTONE_STORE_ID) {
      throw new HttpsError(
        "failed-precondition",
        "본인인증 상점 정보가 설레연 테스트 채널과 일치하지 않아요."
      );
    }

    const customer = readPortOneCustomer(verification);
    const name = firstNonEmptyString(customer.name, customer.fullName);
    const phoneNumber = normalizeDigits(
      firstNonEmptyString(customer.phoneNumber, customer.phone)
    );
    const birthYear = readBirthYear(customer);
    const birthDate = firstNonEmptyString(
      customer.birthDate,
      customer.birthdate,
      customer.dateOfBirth,
      birthYear == null ? null : String(birthYear)
    );
    const ci = firstNonEmptyString(customer.ci, customer.CI);
    const di = firstNonEmptyString(customer.di, customer.DI);
    const uniqueKey = firstNonEmptyString(
      customer.id,
      customer.uniqueKey,
      customer.uniqueIdentifier,
      ci,
      di
    );

    if (!name || !phoneNumber || birthYear == null || !uniqueKey) {
      throw new HttpsError(
        "failed-precondition",
        "본인인증 결과의 필수 항목을 확인하지 못했어요."
      );
    }

    const normalizedPhone = normalizeKoreanPhone(phoneNumber);
    if (!normalizedPhone) {
      throw new HttpsError(
        "failed-precondition",
        "본인인증 전화번호 형식을 확인하지 못했어요."
      );
    }

    const phoneLast4 = phoneNumber.slice(-4);
    const verifiedPhoneHash = hashPhoneNumber(normalizedPhone);
    const ciHash = ci ? sha256Hex(ci) : null;
    const diHash = di ? sha256Hex(di) : null;
    const uniqueKeyHash = sha256Hex(uniqueKey);
    const adult = isAdultByKoreanYear(birthYear);

    await assertUniqueIdentityNotReused(uid, ciHash, diHash, uniqueKeyHash);

    const userRef = db.collection("users").doc(uid);
    const privateRef = db.collection("userPrivateVerifications").doc(uid);
    const now = FieldValue.serverTimestamp();

    await db.runTransaction(async (tx) => {
      const userSnap = await tx.get(userRef);
      const previousVerificationSnap = await tx.get(privateRef);
      if (!userSnap.exists) {
        throw new HttpsError(
          "failed-precondition",
          "사용자 계정을 찾을 수 없어요."
        );
      }

      const previousPhoneHash = asNonEmptyString(
        (previousVerificationSnap.data() as Record<string, unknown> | undefined)
          ?.phoneHash
      );
      if (
        previousPhoneHash &&
        (!adult || previousPhoneHash !== verifiedPhoneHash)
      ) {
        tx.delete(verifiedPhoneHashIndexOwnerRef(previousPhoneHash, uid));
      }

      tx.set(
        privateRef,
        {
          name,
          phoneNumber,
          phoneHash: adult ? verifiedPhoneHash : FieldValue.delete(),
          birthDate,
          ciHash,
          diHash,
          uniqueKeyHash,
          provider: ADULT_VERIFICATION_PROVIDER,
          identityVerificationId,
          identityVerificationTxId,
          verificationStatus: adult ? "adult_verified" : "under_age",
          verifiedAt: now,
          createdAt: now,
          updatedAt: now,
        },
        { merge: true }
      );

      if (adult) {
        tx.set(
          verifiedPhoneHashIndexOwnerRef(verifiedPhoneHash, uid),
          {
            userId: uid,
            provider: ADULT_VERIFICATION_PROVIDER,
            updatedAt: now,
          },
          { merge: true }
        );
      }

      tx.set(
        userRef,
        {
          adultVerified: adult,
          realNameVerified: adult,
          adultVerifiedAt: adult ? now : FieldValue.delete(),
          verificationProvider: ADULT_VERIFICATION_PROVIDER,
          registrationStatus: adult
            ? "adult_verified"
            : "adult_verification_under_age",
          birthYear,
          phoneLast4,
          updatedAt: now,
        },
        { merge: true }
      );
    });

    if (!adult) {
      throw new HttpsError(
        "permission-denied",
        "설레연은 연 나이 20세 이상만 이용할 수 있어요."
      );
    }

    try {
      await reconcileVerifiedPhoneHashWithExistingContacts(uid, verifiedPhoneHash);
    } catch (error) {
      logger.error("verified phone contact reconciliation failed", {
        uidHash: createHash("sha256").update(uid).digest("hex").slice(0, 16),
        errorType: error instanceof Error ? error.name : "unknown",
      });
    }

    return {
      success: true,
      adultVerified: true,
      realNameVerified: true,
      status: "adult_verified",
      birthYear,
      phoneLast4,
    };
  }
);

// -----------------------------------------------------------------------------
// REMOVED (security): createFirebaseCustomTokenFromEmailLinkToken
//
// 이 callable 은 emailLinkTokens/{token} 문서를 bearer credential 로 취급해
// Firebase custom token 을 발급했다. 그런데 그 문서는 클라이언트가 비인증
// 상태로 직접 만들 수 있었고(firestore.rules 의 emailLinkTokens create 규칙),
// users 컬렉션은 list 가 공개였다. 따라서 공격자는
//   1. users 를 나열해 피해자의 문서 ID(kakaoUserId)와 studentEmail 을 얻고
//   2. 그 값으로 emailLinkTokens 문서를 스스로 만들고
//   3. 이 callable 을 호출해 피해자 UID 의 custom token 을 받을 수 있었다.
// payload 의 kakaoUserId/studentEmail 검증은 값이 있을 때만 수행됐고,
// expiresAt 은 Timestamp 가 아니면 무시됐으며, 토큰은 single-use 도 아니었다.
//
// 세션 복구는 createFirebaseCustomToken(카카오 액세스 토큰을 Kakao API 로
// 서버에서 검증) 또는 completeStudentEmailLink(이미 Firebase가 검증한
// Yonsei 이메일 세션 + 단일 사용 토큰을 트랜잭션으로 소비) 경로만 사용한다.
// -----------------------------------------------------------------------------

// -----------------------------------------------------------------------------
// Share-link invitations (friend / 3:3 team). See friendInvites.ts.
//
// AUTH CONTRACT: every callable below resolves the caller from the Firebase
// session only (resolveAuthedAppUser). There is deliberately NO Kakao
// access-token fallback on this path: the app's invariant is that a Kakao SDK
// session never authenticates an account, and a share link must never be able
// to bind a friendship to an identity that Firebase did not verify.
// -----------------------------------------------------------------------------

export const createFriendInvite = onCall(withAppCheck(), async (request) => {
  const requestData = getCallableData(request);
  logger.info("createFriendInvite request", {
    hasAuthUid: !!request.auth?.uid,
    dataKeys: Object.keys(requestData),
  });
  const inviter = await resolveAuthedAppUser(request.auth);
  const created = await createFriendInviteRecord({
    db,
    inviter,
    shareChannel: asStringOrNull(requestData.shareChannel),
  });
  logger.info("createFriendInvite issued", {
    inviteId: created.inviteId,
    inviterUserId: inviter.userId,
  });
  return created;
});

/**
 * Read-only preview for the in-app confirmation step. Returns the server
 * record's purpose so the app routes on it — never on the link's own hints.
 */
export const previewInviteToken = onCall(withAppCheck(), async (request) => {
  const data = getCallableData(request);
  const viewer = await resolveAuthedAppUser(request.auth);
  const preview = await previewInviteByToken({
    db,
    rawToken: asNonEmptyString(data.token),
    viewer,
  });
  logger.info("previewInviteToken", {
    viewerUserId: viewer.userId,
    status: preview.status,
    purpose: preview.purpose ?? null,
  });
  return preview;
});

export const acceptFriendInvite = onCall(withAppCheck(), async (request) => {
  const data = getCallableData(request);
  const rawToken = asNonEmptyString(data.token);
  logger.info("acceptFriendInvite invoked", {
    hasAuthUid: !!request.auth?.uid,
    dataKeys: Object.keys(data),
    hasToken: !!rawToken,
  });
  if (!rawToken) {
    return {
      status: "invalid",
      message: "친구 초대 링크가 올바르지 않아요.",
    };
  }

  // The acceptor is ALWAYS the Firebase-authenticated caller. The inviter
  // comes from the stored invite document. No uid in the request body is
  // ever trusted, and the invite must carry purpose FRIEND_INVITE.
  const acceptor = await resolveAuthedAppUser(request.auth);
  const result = await acceptFriendInviteByToken({
    db,
    rawToken,
    acceptor,
  });

  logger.info("Friend invite processed", {
    acceptorUserId: acceptor.userId,
    otherUserId: result.otherUserId ?? null,
    pairId: result.pairId ?? null,
    status: result.status,
  });

  return result;
});

/** Leader-only share link for the 3:3 team (purpose TEAM_INVITE). */
export const createEventTeamShareInvite = onCall(withAppCheck(), async (request) => {
  const data = getCallableData(request);
  const leader = await resolveAuthedAppUser(request.auth);
  const created = await createTeamInviteRecord({
    db,
    leader,
    teamSetupId: asNonEmptyString(data.teamSetupId),
    shareChannel: asStringOrNull(data.shareChannel),
  });
  logger.info("createEventTeamShareInvite issued", {
    inviteId: created.inviteId,
    leaderUserId: leader.userId,
  });
  return created;
});

/**
 * TEAM_INVITE token → canonical pending eventTeamInvites record. Membership
 * is granted only by respondEventTeamInvite after the user accepts in-app.
 * Never touches the friend graph.
 */
export const redeemEventTeamShareInvite = onCall(withAppCheck(), async (request) => {
  const data = getCallableData(request);
  const redeemer = await resolveAuthedAppUser(request.auth);
  const result = await redeemTeamInviteByToken({
    db,
    rawToken: asNonEmptyString(data.token),
    redeemer,
  });
  logger.info("redeemEventTeamShareInvite", {
    redeemerUserId: redeemer.userId,
    status: result.status,
    teamSetupId: result.teamSetupId ?? null,
  });
  return result;
});

// =============================================================================
// 이벤트 3인 팀 초대 (친구 선택 → 푸시 → 수락 시 팀 반영)
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
    title: "팀 초대가 도착했어요",
    body: `${params.inviterName}님이 3인 팀 참여를 요청했어요.`,
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
  // Team setup/membership: Firebase canonical auth only (no Kakao fallback).
  const leader = await resolveAuthedAppUser(request.auth);
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
  const inviter = await resolveAuthedAppUser(request.auth);
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
  // A block in either direction: no invitation, no pending slot.
  await assertNotBlockedEitherWay(db, inviter.userId, inviteeUserId);

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
    data: {
      type: "event_team_invite",
      inviteId,
      teamSetupId,
      inviterUserId: inviter.userId,
      inviterName: inviterInfo.nickname,
    },
  });

  logger.info("createEventTeamInvite ok", { inviteId, teamSetupId, inviteeUserId });

  return { inviteId, teamSetupId };
});

export const respondEventTeamInvite = onCall(withAppCheck(), async (request) => {
  const data = getCallableData(request);
  // Membership authority: Firebase canonical auth only. The transaction in
  // eventTeamMembership.ts re-validates friendship, blocks (both
  // directions), invite state and capacity at commit time.
  const user = await resolveAuthedAppUser(request.auth);
  if (typeof data.accept !== "boolean") {
    // Never turn a malformed request into a silent decline.
    throw new HttpsError("invalid-argument", "accept 값이 필요해요.");
  }
  const result = await respondTeamInviteCore({
    db,
    user,
    inviteId: asNonEmptyString(data.inviteId),
    accept: data.accept,
  });
  logger.info("respondEventTeamInvite", {
    userId: user.userId,
    ok: result.ok,
    outcome: result.ok ? result.status : result.code,
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

export const spinSeasonMeetingRoulette = onCall(withAppCheck(), async (request) => {
  const data = getCallableData(request);
  const user = await resolveAuthedAppUser(request.auth);
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

  // 생활권 hard filter 의 rollout activation. OFF 면 생활권 조건만 비활성이고
  // 팀 상태·중복 멤버·추천 준비 여부 등 나머지 조건은 그대로 적용된다.
  //
  // 상태를 확인하지 못하면(cold start + 조회 실패) 어느 쪽으로도 가정하지
  // 않는다. OFF 로 보면 활성화된 정책을 무시하고 다른 생활권 팀을 붙일 수
  // 있고, ON 으로 보면 준비 단계의 정상 사용자를 막는다. 재시도 가능한
  // 오류로 돌려주는 편이 안전하다.
  const campusLifeZoneActivation = await loadCampusLifeZoneActivation(db);
  if (campusLifeZoneActivation.state === "unknown") {
    logger.error("season roulette blocked: campus life zone activation unknown", {
      code: "campusLifeZoneActivationReadFailure",
      campusLifeZoneActivationState: "unknown",
    });
    throw new HttpsError(
      "unavailable",
      "지금은 룰렛을 시작할 수 없어요. 잠시 후 다시 시도해 주세요."
    );
  }
  const campusLifeZoneEnforced =
    campusLifeZoneActivation.state === "enforced";

  // 요청 팀 세 명의 공통 생활권. meetingGroups 의 파생 필드를 우선 쓰고,
  // 아직 동기화되지 않았으면 방금 만든 스냅샷에서 직접 계산한다.
  const requestingTeamZones = (() => {
    // 파생 필드도 canonical 검증을 거친다. 손상된 값이 남아 있으면 그것을
    // 생활권으로 쓰지 않고, 멤버 스냅샷에서 다시 계산한다.
    const stored = readPersistedCampusLifeZones(
      requestingGroupData.sharedCampusLifeZones
    );
    if (stored.length > 0) return stored;
    return sharedCampusLifeZones(
      requestingTeamSnapshot.membersSnapshot.map((member) =>
        readPersistedCampusLifeZones(
          (member as unknown as Record<string, unknown>).campusLifeZones
        )
      )
    );
  })();
  if (campusLifeZoneEnforced && requestingTeamZones.length === 0) {
    throw new HttpsError(
      "failed-precondition",
      "팀원들의 생활권 정보가 필요해요. 학년·학과 정보를 먼저 등록해주세요."
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
    // 생활권이 다르면 실제로 함께 만날 수 없다. 추천 점수와 무관한
    // hard eligibility 이므로 stale 추천 문서가 있어도 여기서 막는다.
    if (
      campusLifeZoneEnforced &&
      !hasCompatibleCampusLifeZones(
        requestingTeamZones,
        readPersistedCampusLifeZones(groupData.sharedCampusLifeZones)
      )
    ) {
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
    // Firestore 트랜잭션은 모든 read가 write보다 먼저 와야 한다.
    // stale lock 삭제는 여기서 바로 실행하지 않고 모아 두었다가
    // 후보 선정이 끝난 write 단계에서 일괄 처리한다.
    const staleLockRefs: DocumentReference[] = [];
    const requesterLockSnap = await tx.get(requesterLockRef);
    const payerRef = db.collection("users").doc(user.userId);
    const payerSnap = await tx.get(payerRef);
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
      staleLockRefs.push(requesterLockRef);
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
        staleLockRefs.push(candidateLockRef);
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

    if (!payerSnap.exists) {
      throw new HttpsError("not-found", "사용자 정보를 찾을 수 없어요.");
    }
    const heartAmount = HEART_FEATURE_COSTS.seasonRoulette;
    const heartBalance = debitHeartsInTransaction({
      transaction: tx,
      userRef: payerRef,
      userSnap: payerSnap,
      amount: heartAmount,
      feature: "3:3 가챠 룰렛",
    });
    const heartSpendRef = db
      .collection("heartTransactions")
      .doc(createHash("sha256").update(`season_roulette:${resultRef.id}`).digest("hex"));

    for (const staleLockRef of staleLockRefs) {
      if (
        staleLockRef.path === requesterLockRef.path ||
        staleLockRef.path === selectedCandidateLockRef.path
      ) {
        continue;
      }
      tx.delete(staleLockRef);
    }
    tx.set(resultRef, {
      ...resultPreview,
      heartCost: heartAmount,
      heartPaidBy: user.userId,
      createdAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    });
    tx.create(heartSpendRef, {
      uid: user.userId,
      feature: "season_roulette",
      resourceId: resultRef.id,
      amount: heartAmount,
      heartBalanceAfter: heartBalance,
      createdAt: FieldValue.serverTimestamp(),
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
// 1) recEvents onCreate 트리거
//    rules 기준: recEvents/{userId}/events/{eventId}
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
      userId,
      targetUserId,
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
// 2) interactions 기반 프로필 좋아요 알림 + 매치 판정 + 채팅방 생성
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

    // A forged client interaction must not turn an operations account into a
    // normal recommendation/match counterpart.  UI filtering alone is not an
    // authority boundary, so enforce the exclusion again before notifications
    // or mutual-match room creation.
    const [fromUserSnap, toUserSnap] = await Promise.all([
      db.collection("users").doc(fromUserId).get(),
      db.collection("users").doc(toUserId).get(),
    ]);
    if (
      fromUserSnap.data()?.accountType === "operations" ||
      toUserSnap.data()?.accountType === "operations"
    ) {
      return;
    }

    // -----------------------------------------------------------------------
    // 프로필 좋아요 알림: 상대방에게 인앱 알림(idempotent) + 푸시
    // -----------------------------------------------------------------------
    if (fromUserId !== toUserId) {
      const interactionId = event.params.interactionId;
      const notificationId = `like_${interactionId}`;

      const actorInfo = await getUserDisplayInfo(fromUserId);
      const title = "새로운 관심이 도착했어요";
      const body = `${actorInfo.nickname}님이 좋아요를 보냈어요`;

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
          data: {
            type: "profile_like",
            notificationId,
            deepLinkType: "received_like",
            actorUserId: fromUserId,
            sourceDocId: interactionId,
          },
        });

        logger.info("Profile like push + in-app notification sent", {
          fromUserId,
          toUserId,
          action,
          notificationId,
        });
      }
    }

    // -----------------------------------------------------------------------
    // 기존 mutual like 체크 → 매치 생성
    // -----------------------------------------------------------------------
    const reverseQuery = await db
      .collection("interactions")
      .where("fromUserId", "==", toUserId)
      .where("toUserId", "==", fromUserId)
      .where("action", "in", ["like", "super_like"])
      .limit(1)
      .get();

    if (reverseQuery.empty) return;

    const existingMatches = await db
      .collection("matches")
      .where("userIds", "array-contains", fromUserId)
      .get();

    for (const doc of existingMatches.docs) {
      const ids = (doc.data().userIds || []) as string[];
      if (ids.includes(toUserId)) {
        logger.info("Match already exists", { matchId: doc.id });
        return;
      }
    }

    const roomId = buildDirectRoomId(fromUserId, toUserId);
    const matchRef = db.collection("matches").doc();
    const roomRef = db.collection("chat_rooms").doc(roomId);

    const [userA, userB] = await Promise.all([
      getUserDisplayInfo(fromUserId),
      getUserDisplayInfo(toUserId),
    ]);

    const participantInfo = {
      [fromUserId]: {
        nickname: userA.nickname,
        avatarUrl: userA.avatarUrl,
      },
      [toUserId]: {
        nickname: userB.nickname,
        avatarUrl: userB.avatarUrl,
      },
    };

    const batch = db.batch();

    batch.set(matchRef, {
      userIds: [fromUserId, toUserId],
      matchType: "mutual_like",
      matchedAt: FieldValue.serverTimestamp(),
      status: "active",
      chatRoomId: roomId,
    });

    batch.set(
      roomRef,
      {
        roomId,
        type: "one_to_one",
        status: "active",
        participantIds: [fromUserId, toUserId],
        participantInfo,
        matchId: matchRef.id,
        createdAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
        lastMessage: "매칭이 성사되었어요! 먼저 인사해보세요 💕",
        lastMessageAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

    const msgRef = roomRef.collection("messages").doc();
    batch.set(msgRef, {
      senderId: "system",
      text: "매칭이 성사되었어요! 먼저 인사해보세요 💕",
      content: "매칭이 성사되었어요! 먼저 인사해보세요 💕",
      type: "system",
      createdAt: FieldValue.serverTimestamp(),
      readBy: [],
    });

    await batch.commit();

    logger.info("Match created", {
      matchId: matchRef.id,
      roomId,
      fromUserId,
      toUserId,
    });
  }
);

// =============================================================================
// 3) 새 채팅 메시지 → 푸시 알림
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

    const notificationId = buildNotificationIdempotencyKey([
      "chat",
      roomId,
      event.params.messageId,
    ]);
    await sendPushOnce(
      targetUserIds,
      {
        title: senderName,
        body: body || "메시지가 도착했어요.",
        data: {
          type: "chat",
          roomId,
          messageId: event.params.messageId,
          notificationId,
        },
      },
      notificationId
    );

    logger.info("Chat push sent", {
      roomId,
      senderId,
      targets: targetUserIds,
    });
  }
);

// =============================================================================
// 4) 대나무숲 댓글/답글 푸시 + 인앱 알림
// =============================================================================
// SEC-04. 소유자는 비공개 매핑을 먼저 보고, 아직 이관되지 않은 문서에 한해
// public authorId 를 임시로 인정한다. 둘이 어긋나면 알림을 보내지 않는다 —
// 잘못 고르면 남의 글 알림이 엉뚱한 사람에게 간다. 여기서 users /
// publicProfiles 를 뒤져 추측하지 않는다. 그게 없애려는 join 그 자체다.
async function resolveBambooPostOwnerUid(
  postId: string,
  legacyAuthorId: unknown
): Promise<string> {
  const mapSnap = await db
    .collection(BAMBOO_POST_OWNER_COLLECTION)
    .doc(postId)
    .get();
  const resolution = resolveBambooOwner(
    mapSnap.data()?.ownerUid,
    legacyAuthorId
  );
  if (resolution.status === "conflict") {
    logger.error("Bamboo post ownership conflict; skipping notification", {
      postId,
    });
  }
  return ownerUidForNotification(resolution);
}

async function resolveBambooCommentOwnerUid(
  postId: string,
  commentId: string,
  legacyAuthorId: unknown
): Promise<string> {
  const mapSnap = await db
    .collection(BAMBOO_COMMENT_OWNER_COLLECTION)
    .doc(bambooCommentOwnerDocId(postId, commentId))
    .get();
  const resolution = resolveBambooOwner(
    mapSnap.data()?.ownerUid,
    legacyAuthorId
  );
  if (resolution.status === "conflict") {
    logger.error("Bamboo comment ownership conflict; skipping notification", {
      postId,
      commentId,
    });
  }
  return ownerUidForNotification(resolution);
}

export const onBambooCommentCreated = onDocumentCreated(
  "bamboo_posts/{postId}/comments/{commentId}",
  async (event) => {
    const snap = event.data;
    if (!snap) return;

    const postId = event.params.postId;
    const commentId = event.params.commentId;
    const comment = snap.data();

    const authorId = await resolveBambooCommentOwnerUid(
      postId,
      commentId,
      comment.authorId
    );
    const content = asString(comment.content ?? "").trim();
    const parentCommentId = asNonEmptyString(comment.parentCommentId) ?? "";

    if (!authorId) return;

    const authorInfo = await getUserDisplayInfo(authorId);

    const postSnap = await db.collection("bamboo_posts").doc(postId).get();
    if (!postSnap.exists) return;

    const post = (postSnap.data() ?? {}) as Record<string, unknown>;
    const postAuthorId = await resolveBambooPostOwnerUid(postId, post.authorId);

    // 일반 댓글: 글 작성자에게 푸시 + 인앱 알림
    if (!parentCommentId) {
      if (postAuthorId && postAuthorId !== authorId) {
        const notificationId = buildNotificationIdempotencyKey([
          "community_comment",
          postId,
          commentId,
          postAuthorId,
        ]);
        await sendPushOnce(
          [postAuthorId],
          {
            title: "내 글에 새 댓글이 달렸어요",
            body: content || "댓글이 도착했어요.",
            data: {
              type: "community_comment",
              postId,
              commentId,
              notificationId,
            },
          },
          `push_${notificationId}`
        );

        await createInAppNotification(
          postAuthorId,
          {
            type: "community_comment",
            title: "내 글에 새 댓글이 달렸어요",
            body: content || "누군가가 회원님의 글에 댓글을 남겼습니다.",
            deeplinkType: "community_post",
            deeplinkId: postId,
            actorId: authorId,
            actorName: authorInfo.nickname,
            postId,
            commentId,
          },
          notificationId
        );

        logger.info("Community comment push + in-app notification sent", {
          postId,
          commentId,
          target: postAuthorId,
          authorId,
        });
      }
      return;
    }

    // 답글: 부모 댓글 작성자에게 푸시 + 인앱 알림
    const parentSnap = await db
      .collection("bamboo_posts")
      .doc(postId)
      .collection("comments")
      .doc(parentCommentId)
      .get();

    if (!parentSnap.exists) return;

    const parent = (parentSnap.data() ?? {}) as Record<string, unknown>;
    const parentAuthorId = await resolveBambooCommentOwnerUid(
      postId,
      parentCommentId,
      parent.authorId
    );

    const targets = [parentAuthorId].filter((uid) => uid && uid !== authorId);

    if (targets.length > 0) {
      const notificationId = buildNotificationIdempotencyKey([
        "community_reply",
        postId,
        commentId,
        parentAuthorId,
      ]);
      await sendPushOnce(
        targets,
        {
          title: "내 댓글에 답글이 달렸어요",
          body: content || "답글이 도착했어요.",
          data: {
            type: "community_reply",
            postId,
            commentId,
            notificationId,
          },
        },
        `push_${notificationId}`
      );

      await createInAppNotification(
        parentAuthorId,
        {
          type: "community_reply",
          title: "내 댓글에 답글이 달렸어요",
          body: content || "누군가가 회원님의 댓글에 답글을 남겼습니다.",
          deeplinkType: "community_post",
          deeplinkId: postId,
          actorId: authorId,
          actorName: authorInfo.nickname,
          postId,
          commentId,
        },
        notificationId
      );

      logger.info("Community reply push + in-app notification sent", {
        postId,
        commentId,
        parentCommentId,
        targets,
        authorId,
      });
    }
  }
);

// =============================================================================
// 5) 대나무숲 글 좋아요 푸시 + 인앱 알림
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
    const postAuthorId = await resolveBambooPostOwnerUid(postId, post.authorId);

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
        postAuthorId,
        likerUserId,
        existingCount,
      });
      return;
    }

    const likerInfo = await getUserDisplayInfo(likerUserId);

    await sendPushToUsers([postAuthorId], {
      title: "내 글에 좋아요가 눌렸어요",
      body: "누군가가 회원님의 글을 좋아합니다.",
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
      postAuthorId,
      likerUserId,
      existingCount: existingCount + 1,
    });
  }
);

// =============================================================================
// 6) 무물(ask) 생성 시 알림 + 푸시
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
        fromUserId,
        toUserId,
        notificationId,
      });
    }
  }
);

// =============================================================================
// 7) 매치 해제 시 채팅방 비활성화 (onMatchUpdated)
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
        chatRoomId,
      });
    }
  }
);

// =============================================================================
// 8) 헤어짐 도장 24시간 초과 약속 자동 완료 + 후속 알림
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

          // 약속 문서의 participantIds 는 클라이언트가 쓴다. 이 값으로
          // 인앱 알림과 push 가 나가므로, 서버가 소유한 채팅방 참가자로
          // 반드시 좁힌다 (dispatchPromiseReminder 와 같은 신뢰 경계).
          const autoCompleteRoomData = (roomSnap.data() ?? {}) as Record<
            string,
            unknown
          >;
          const autoCompleteRoomParticipants = new Set(
            asStringArray(autoCompleteRoomData.participantIds)
          );
          const participantIds = asStringArray(
            promiseData.participantIds
          ).filter((uid) => autoCompleteRoomParticipants.has(uid));
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
          roomId,
          promiseId,
          error,
        });
      }
    }

    logger.info("autoCompleteExpiredGoodbyeSafetyStamps finished", {
      processedCount: promisesSnap.size,
    });
  }
);

// =============================================================================
// 9) 약속 확정 시 정확한 1시간 전 리마인더 예약
// =============================================================================
export const schedulePromiseReminderTask = onDocumentWritten(
  {
    document: "chat_rooms/{roomId}/promises/{promiseId}",
    region: "asia-northeast3",
  },
  async (event) => {
    const afterData = event.data?.after.exists
      ? ((event.data.after.data() ?? {}) as Record<string, unknown>)
      : null;
    if (!afterData) {
      return;
    }
    const beforeData = event.data?.before?.exists
      ? ((event.data.before.data() ?? {}) as Record<string, unknown>)
      : null;

    const roomId = event.params.roomId;
    const promiseId = event.params.promiseId;
    const status = asString(afterData.status, "").toLowerCase();
    if (status !== "confirmed") {
      return;
    }

    const promiseDateTime = asDate(afterData.dateTime);
    if (!promiseDateTime) {
      logger.warn("Skipped exact promise reminder scheduling: invalid dateTime", {
        roomId,
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
          roomId,
          promiseId,
          scheduledForMs,
        }
      );
      return;
    }

    if (
      !shouldSchedulePromiseReminderTransition({
        beforeData,
        afterData,
        scheduledForMs,
      })
    ) return;

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
      roomId,
      promiseId,
      scheduledForMs,
    });
  }
);

// =============================================================================
// 10) 예약된 약속 1시간 전 푸시 실행
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
      logger.warn("Invalid exact promise reminder payload", { data });
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

      // 약속 문서의 participantIds 는 클라이언트가 쓴다. 그대로 믿으면
      // 참가자 한 명이 임의의 uid 목록을 넣어 무관한 사용자에게 (그리고
      // 자신이 정한 place 문구로) push 를 보낼 수 있다.
      // 수신자는 항상 서버가 소유한 채팅방 참가자로 한정한다.
      const roomParticipantIds = asStringArray(roomData.participantIds);
      const roomParticipantSet = new Set(roomParticipantIds);
      const promiseParticipantIds = asStringArray(
        promiseData.participantIds
      ).filter((uid) => roomParticipantSet.has(uid));
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
        roomId,
        promiseId,
      });
      return;
    }

    await sendPushToUsers(result.participantIds, {
      title: buildUpcomingPromiseReminderTitle(result.place),
      body: "상대방 만날 때 같이 안전도장 누르는 거 잊지 말기!",
      data: {
        type: "promise_reminder",
        roomId,
        promiseId,
      },
    });

    logger.info("Dispatched exact promise reminder push", {
      roomId,
      promiseId,
      participantCount: result.participantIds.length,
    });
  }
);

// =============================================================================
// 11) 약속 1시간 전 푸시 리마인더 (기존 15분 스케줄러 비활성화)
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
// 12) 매일 오후 1시 unread chat digest 푸시 + 인앱 알림
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
            userId,
            digestDate,
          });
          continue;
        }

        const { unreadCount, previewSenderName } =
          await getUnreadChatDigestForUser(userId);

        if (unreadCount <= 0) {
          continue;
        }

        const title = "읽지 않은 메시지가 있어요";
        const body = previewSenderName
          ? `${previewSenderName}님 외 읽지 않은 메시지가 ${unreadCount}개 있습니다.`
          : `읽지 않은 메시지가 ${unreadCount}개 있습니다.`;

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
          userId,
          unreadCount,
          digestDate,
        });
      } catch (error) {
        logger.error("Failed to send daily unread chat digest", {
          userId,
          digestDate,
          error,
        });
      }
    }

    logger.info("sendDailyUnreadChatDigests finished", { digestDate });
  }
);

// =============================================================================
// 전화번호 정규화 + 해시 (클라이언트와 동일 알고리즘)
// =============================================================================
export function readSafePhotoUrl(userData: Record<string, unknown>): string | null {
  const avatar = readMap(userData.avatar);
  const approvedAvatarUrl = asStringOrNull(avatar.approvedAvatarUrl);
  if (avatar.status === "approved" && isSafePublicAvatarUrl(approvedAvatarUrl)) {
    return approvedAvatarUrl;
  }
  return null;
}

export function isUnregisteredPushTokenError(code: string | null): boolean {
  return (
    code === "messaging/registration-token-not-registered" ||
    code === "messaging/invalid-registration-token"
  );
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

export function buildKakaoUserShell(kakaoUserId: string): Record<string, unknown> {
  return {
    kakaoUserId,
    profileImageUrl: "",
    profileImageMode: "avatar",
    createdAt: FieldValue.serverTimestamp(),
    lastLoginAt: FieldValue.serverTimestamp(),
  };
}

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

// KG Inicis/PortOne 본인인증 문서에서만 파생되는 역색인이다. 연락처 원본과
// 본인인증 원본 전화번호 모두 이 경로에는 저장하지 않는다.
const VERIFIED_PHONE_HASH_INDEX = "verifiedPhoneHashIndex";
const VERIFIED_PHONE_HASH_BACKFILL_PAGE_SIZE = 100;

function verifiedPhoneHashIndexOwnerRef(phoneHash: string, uid: string) {
  return db
    .collection(VERIFIED_PHONE_HASH_INDEX)
    .doc(phoneHash)
    .collection("owners")
    .doc(uid);
}

async function markContactHashMatchedToUsers(
  ownerUid: string,
  phoneHash: string,
  matchedUserIds: string[]
): Promise<void> {
  if (matchedUserIds.length === 0) return;
  await db
    .collection("users")
    .doc(ownerUid)
    .collection("contactBlockedHashes")
    .doc(phoneHash)
    .set(
      {
        isMatchedToAppUser: true,
        matchedUserIds: FieldValue.arrayUnion(...matchedUserIds),
        matchSource: "kg_inicis_verified_phone",
        matchedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
}

// =============================================================================
// syncContactBlocks — 연락처 차단 동기화 Callable
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

    // 3. KG이니시스 본인인증 전화번호 해시 역색인 lookup + 상호 block
    for (const phoneHash of chunk) {
      const ownersSnap = await db
        .collection(VERIFIED_PHONE_HASH_INDEX)
        .doc(phoneHash)
        .collection("owners")
        .get();
      if (ownersSnap.empty) continue;

      const matchedUserIds: string[] = [];
      for (const ownerDoc of ownersSnap.docs) {
        const matchedUid = ownerDoc.id;
        if (matchedUid === callerUid) {
          skippedSelfCount++;
          continue;
        }
        matchedUserIds.push(matchedUid);
      }
      if (matchedUserIds.length === 0) continue;

      matchedUserCount += matchedUserIds.length;
      await markContactHashMatchedToUsers(
        callerUid,
        phoneHash,
        matchedUserIds
      );

      for (const matchedUid of matchedUserIds) {
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
  }

  logger.info("syncContactBlocks completed", {
    callerUid,
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

// =============================================================================
// syncKakaoTalkFriendBlocks — server-verified mutual recommendation privacy
// =============================================================================
const KAKAO_RECOMMENDATION_SYNC_CHUNK_SIZE = 200;

function recommendationExclusionRef(ownerUid: string, targetUid: string) {
  return db
    .collection("recommendationExclusions")
    .doc(ownerUid)
    .collection("targets")
    .doc(targetUid);
}

async function reconcileRecommendationExclusionPair(
  userA: string,
  userB: string,
  verifiedNow: boolean,
): Promise<boolean> {
  if (!userA || !userB || userA === userB) return false;

  return db.runTransaction(async (transaction) => {
    const userARef = db.collection("users").doc(userA);
    const userBRef = db.collection("users").doc(userB);
    const [userASnapshot, userBSnapshot] = await transaction.getAll(
      userARef,
      userBRef,
    );
    const userATargetRef = recommendationExclusionRef(userA, userB);
    const userBTargetRef = recommendationExclusionRef(userB, userA);

    if (!userASnapshot.exists || !userBSnapshot.exists) {
      transaction.delete(userATargetRef);
      transaction.delete(userBTargetRef);
      return false;
    }

    const userAEnabled = isKakaoFriendAvoidanceEnabled(
      userASnapshot.data() ?? {},
    );
    const userBEnabled = isKakaoFriendAvoidanceEnabled(
      userBSnapshot.data() ?? {},
    );
    const payload: Record<string, unknown> = {
      pairId: buildRecommendationExclusionPairId(userA, userB),
      userIds: [userA, userB].sort(),
      source: "kakao_talk_friend",
      reason: "kakao_friend_avoidance",
      enabledBy: {
        [userA]: userAEnabled,
        [userB]: userBEnabled,
      },
      updatedAt: FieldValue.serverTimestamp(),
    };
    if (verifiedNow) payload.verifiedAt = FieldValue.serverTimestamp();

    // Reading both source-of-truth user documents in this transaction makes a
    // simultaneous preference change retry instead of overwriting newer data.
    transaction.set(userATargetRef, payload, { merge: true });
    transaction.set(userBTargetRef, payload, { merge: true });
    return userAEnabled || userBEnabled;
  });
}

async function reconcilePairsWithConcurrency(
  callerUid: string,
  targetUids: string[],
  verifiedTargetUids: Set<string>,
): Promise<Map<string, boolean>> {
  const results = new Map<string, boolean>();
  const concurrency = 20;
  for (let offset = 0; offset < targetUids.length; offset += concurrency) {
    const chunk = targetUids.slice(offset, offset + concurrency);
    const activeValues = await Promise.all(
      chunk.map((targetUid) =>
        reconcileRecommendationExclusionPair(
          callerUid,
          targetUid,
          verifiedTargetUids.has(targetUid),
        ),
      ),
    );
    chunk.forEach((targetUid, index) => {
      results.set(targetUid, activeValues[index]);
    });
  }
  return results;
}

/**
 * Rollout-compatible caller identity OR-chain (identity contract §5): the
 * verified Kakao user id is accepted iff authUid === kakaoUserId (legacy
 * invariant) OR the session claim names it (legacy claim) OR the
 * kakaoIdentities mapping binds it to the caller's appUserId (new accounts).
 * Returns the caller's RESOLVED appUserId.
 */
async function resolveKakaoCallerAppUserId(params: {
  authUid: string;
  claimedKakaoUserId: string | null;
  verifiedKakaoUserId: string;
}): Promise<string> {
  const direct = decideKakaoCallerIdentity({
    authUid: params.authUid,
    claimedKakaoUserId: params.claimedKakaoUserId,
    verifiedKakaoUserId: params.verifiedKakaoUserId,
    mappingAppUserId: null,
  });
  if (direct.ok) return direct.appUserId;
  const mappingSnapshot = await db
    .collection("kakaoIdentities")
    .doc(kakaoIdentityHash(params.verifiedKakaoUserId))
    .get();
  const mapped = decideKakaoCallerIdentity({
    authUid: params.authUid,
    claimedKakaoUserId: params.claimedKakaoUserId,
    verifiedKakaoUserId: params.verifiedKakaoUserId,
    mappingAppUserId: mappingSnapshot.exists
      ? asNonEmptyString(mappingSnapshot.data()?.appUserId)
      : null,
  });
  if (mapped.ok) return mapped.appUserId;
  throw new HttpsError(
    "permission-denied",
    "로그인한 계정과 카카오 계정이 일치하지 않아요.",
  );
}

/**
 * Closes both viewer- and candidate-side gates before the client attempts to
 * read/validate a Kakao token. If that later step fails or consent was revoked,
 * the last successful `ready` state cannot remain open indefinitely.
 *
 * @deprecated LEGACY_KAKAO_SYNC_BACKEND_STILL_REQUIRED_FOR_OLD_CLIENTS —
 * replaced by createKakaoFriendPairsOnce / setKakaoFriendAvoidanceEnabled;
 * remove after force-update.
 */
export const beginKakaoFriendRecommendationPrivacySync = onCall(
  withAppCheck(),
  async (request) => {
    const data = getCallableData(request);
    const accessToken = asNonEmptyString(data.kakaoAccessToken);
    let callerUid: string;
    if (accessToken) {
      const verifiedKakaoUserId = (await verifyKakaoAccessToken(accessToken)).userId;
      const authUid = asNonEmptyString(request.auth?.uid);
      const claimedKakaoUid = asNonEmptyString(
        (request.auth?.token as Record<string, unknown> | undefined)?.kakaoUserId,
      );
      if (authUid) {
        // Legacy sessions resolve to the Kakao-keyed doc id; new canonical
        // sessions resolve through the kakaoIdentities mapping (contract §5).
        callerUid = await resolveKakaoCallerAppUserId({
          authUid,
          claimedKakaoUserId: claimedKakaoUid,
          verifiedKakaoUserId,
        });
      } else {
        // Token-only close path for accounts registered under the legacy
        // invariant (users/{kakaoUserId}); preserved for old binaries.
        callerUid = verifiedKakaoUserId;
      }
    } else {
      callerUid = (await resolveAuthedAppUser(request.auth)).userId;
    }

    const callerRef = db.collection("users").doc(callerUid);
    const callerSnapshot = await callerRef.get();
    // Do not create a user shell before mandatory consent/onboarding. This
    // token-only path exists to close a previously registered account.
    if (!callerSnapshot.exists) {
      return { recommendationPrivacyReady: false, accountFound: false };
    }
    const pendingId = randomUUID();
    await callerRef.set(
      {
        recommendationPrivacyReady: false,
        kakaoFriendReconcileStatus: "pending",
        kakaoFriendReconcileId: pendingId,
        kakaoFriendReconcileErrorCode: FieldValue.delete(),
      },
      { merge: true },
    );
    const pendingSnapshot = await callerRef.get();
    await syncPublicProfileForUser(
      db,
      callerUid,
      pendingSnapshot.data() as Record<string, unknown> | undefined,
    );
    return { recommendationPrivacyReady: false, accountFound: true };
  },
);

/**
 * @deprecated LEGACY_KAKAO_SYNC_BACKEND_STILL_REQUIRED_FOR_OLD_CLIENTS —
 * replaced by createKakaoFriendPairsOnce / setKakaoFriendAvoidanceEnabled;
 * remove after force-update.
 */
export const syncKakaoTalkFriendBlocks = onCall(
  withAppCheck({ timeoutSeconds: 180, memory: "512MiB" }),
  async (request) => {
    const data = getCallableData(request);
    const accessToken = asNonEmptyString(data.kakaoAccessToken);
    if (!accessToken) {
      throw new HttpsError(
        "unauthenticated",
        "카카오 친구 관계를 확인하려면 다시 로그인해 주세요.",
      );
    }

    const kakaoUser = await verifyKakaoAccessToken(accessToken);
    const callerKakaoUserId = kakaoUser.userId;
    const authUid = asNonEmptyString(request.auth?.uid);
    const claimedKakaoUid = asNonEmptyString(
      (request.auth?.token as Record<string, unknown> | undefined)?.kakaoUserId,
    );
    if (!authUid) {
      throw new HttpsError(
        "unauthenticated",
        "Firebase 로그인 세션을 확인할 수 없어요.",
      );
    }
    // Contract §5 OR-chain; callerUid is the RESOLVED appUserId (for legacy
    // invariant accounts it equals the Kakao user id).
    const callerUid = await resolveKakaoCallerAppUserId({
      authUid,
      claimedKakaoUserId: claimedKakaoUid,
      verifiedKakaoUserId: callerKakaoUserId,
    });

    const callerRef = db.collection("users").doc(callerUid);
    const callerSnapshot = await callerRef.get();
    if (!callerSnapshot.exists) {
      throw new HttpsError("failed-precondition", "사용자 프로필이 필요해요.");
    }

    const currentCallerData = callerSnapshot.data() ?? {};
    const requestedPreference = data.avoidanceEnabled;
    if (
      requestedPreference !== undefined &&
      typeof requestedPreference !== "boolean"
    ) {
      throw new HttpsError(
        "invalid-argument",
        "avoidanceEnabled 값이 올바르지 않아요.",
      );
    }
    const callerEnabled =
      typeof requestedPreference === "boolean"
        ? requestedPreference
        : isKakaoFriendAvoidanceEnabled(currentCallerData);
    // GATE E (mixed old/new client): captured BEFORE the preference write so
    // a failed enabling sync can revert instead of leaving preference=true
    // with missing exclusions (the new pipeline ignores the pending gate).
    const preRequestAvoidanceEnabled =
      isKakaoFriendAvoidanceEnabled(currentCallerData);
    const reconcileId = randomUUID();

    await callerRef.set(
      {
        // Persist the requested preference before pair transactions. Each
        // transaction then reads the latest preference for both participants.
        kakaoFriendAvoidanceEnabled: callerEnabled,
        recommendationPrivacyReady: false,
        kakaoFriendReconcileStatus: "syncing",
        kakaoFriendReconcileId: reconcileId,
        kakaoFriendReconcileErrorCode: FieldValue.delete(),
      },
      { merge: true },
    );

    try {
      // Do not wait for the asynchronous users -> publicProfiles trigger to
      // close the candidate-side gate. A sync starts fail-closed immediately.
      const syncingCallerSnapshot = await callerRef.get();
      await syncPublicProfileForUser(
        db,
        callerUid,
        syncingCallerSnapshot.data() as Record<string, unknown> | undefined,
      );

      const fetchedFriendIds = await fetchKakaoFriendServiceUserIds(accessToken);
      let skippedSelfCount = 0;
      const friendUserIds = fetchedFriendIds.filter((id) => {
        if (id === callerKakaoUserId) {
          skippedSelfCount++;
          return false;
        }
        return true;
      });

      // Friend -> member resolution (contract §5): a friend matches iff the
      // legacy users/{kakaoId} doc exists OR the kakaoIdentities mapping
      // resolves it to an appUserId. Both lookups are batched per chunk.
      const resolutionCandidates: FriendResolutionCandidate[] = [];
      for (
        let offset = 0;
        offset < friendUserIds.length;
        offset += KAKAO_RECOMMENDATION_SYNC_CHUNK_SIZE
      ) {
        const candidateIds = friendUserIds.slice(
          offset,
          offset + KAKAO_RECOMMENDATION_SYNC_CHUNK_SIZE,
        );
        const userRefs = candidateIds.map((id) =>
          db.collection("users").doc(id),
        );
        const identityRefs = candidateIds.map((id) =>
          db.collection("kakaoIdentities").doc(kakaoIdentityHash(id)),
        );
        const lookupDocs = candidateIds.length > 0
          ? await db.getAll(...userRefs, ...identityRefs)
          : [];
        for (let index = 0; index < candidateIds.length; index++) {
          const friendDoc = lookupDocs[index];
          const identityDoc = lookupDocs[candidateIds.length + index];
          resolutionCandidates.push({
            kakaoUserId: candidateIds[index],
            legacyUserDocExists: friendDoc?.exists === true,
            mappingAppUserId: identityDoc?.exists
              ? asNonEmptyString(identityDoc.data()?.appUserId)
              : null,
          });
        }
      }
      const friendResolution = resolveFriendExclusionAppUserIds({
        callerAppUserId: callerUid,
        callerKakaoUserId,
        candidates: resolutionCandidates,
      });
      const matchedUserCount = friendResolution.matchedUserCount;
      const matchedTargetUids = new Set<string>(
        friendResolution.targetAppUserIds,
      );
      skippedSelfCount += friendResolution.skippedSelfCount;

      // OFF must also clear the caller's contribution from relationships that
      // were materialized by an earlier sync but are absent from today's API.
      const existingTargetSnapshot = callerEnabled
        ? null
        : await db
          .collection("recommendationExclusions")
          .doc(callerUid)
          .collection("targets")
          .get();
      const existingTargetUids = new Set(
        (existingTargetSnapshot?.docs ?? [])
          .map((doc) => doc.id)
          .filter((uid) => uid && uid !== callerUid),
      );
      const allTargetUids = new Set(matchedTargetUids);
      if (!callerEnabled) {
        for (const uid of existingTargetUids) allTargetUids.add(uid);
      }
      const pairStates = await reconcilePairsWithConcurrency(
        callerUid,
        [...allTargetUids],
        matchedTargetUids,
      );
      const activeExcludedPairCount = [...matchedTargetUids].filter(
        (uid) => pairStates.get(uid) === true,
      ).length;
      const clearedExistingPairCount = callerEnabled
        ? 0
        : existingTargetUids.size;

      let finalizedCallerData: Record<string, unknown> | null = null;
      await db.runTransaction(async (transaction) => {
        const latest = await transaction.get(callerRef);
        const latestData = (latest.data() ?? {}) as Record<string, unknown>;
        // An older request must never mark a newer ON/OFF sync ready or
        // overwrite its preference. Only the latest generation may finalize.
        if (latestData.kakaoFriendReconcileId !== reconcileId) return;
        const latestConnection = isRecord(latestData.kakaoFriendConnection)
          ? latestData.kakaoFriendConnection
          : {};
        const terminalData = {
          ...latestData,
          recommendationPrivacyReady: true,
          kakaoFriendReconcileStatus: "ready",
          kakaoFriendReconciledAt: FieldValue.serverTimestamp(),
          kakaoFriendReconcileId: FieldValue.delete(),
          kakaoFriendReconcileErrorCode: FieldValue.delete(),
          // Contract §5: the connection bookkeeping finalizes in the same
          // generation-guarded transaction as recommendationPrivacyReady.
          kakaoFriendConnection: {
            ...latestConnection,
            initialSyncComplete: true,
            lastSuccessfulSyncAt: FieldValue.serverTimestamp(),
          },
        };
        transaction.set(callerRef, terminalData, { merge: true });
        finalizedCallerData = terminalData;
      });
      if (!finalizedCallerData) {
        throw new HttpsError(
          "aborted",
          "더 최근의 친구 피하기 설정을 동기화하고 있어요.",
        );
      }
      await syncPublicProfileForUser(db, callerUid, finalizedCallerData);

      logger.info("syncKakaoTalkFriendBlocks completed", {
        callerUidHash: createHash("sha256")
          .update(callerUid)
          .digest("hex")
          .slice(0, 16),
        fetchedFriendCount: friendUserIds.length,
        matchedUserCount,
        activeExcludedPairCount,
        clearedExistingPairCount,
        skippedSelfCount,
        avoidanceEnabled: callerEnabled,
      });

      return {
        submittedFriendCount: friendUserIds.length,
        matchedUserCount,
        activeExcludedPairCount,
        clearedExistingPairCount,
        skippedSelfCount,
        avoidanceEnabled: callerEnabled,
        recommendationPrivacyReady: true,
      };
    } catch (error) {
      if (error instanceof HttpsError && error.code === "aborted") {
        throw error;
      }
      const code = error instanceof Error ? error.message.slice(0, 80) : "unknown";
      let failedCallerData: Record<string, unknown> | null = null;
      await db.runTransaction(async (transaction) => {
        const latest = await transaction.get(callerRef);
        const latestData = (latest.data() ?? {}) as Record<string, unknown>;
        // A stale failing request cannot knock a newer successful sync back to
        // failed. This is the failure-side half of the generation guard.
        if (latestData.kakaoFriendReconcileId !== reconcileId) return;
        const terminalData = {
          ...latestData,
          recommendationPrivacyReady: false,
          // GATE E: an ENABLING request that failed mid-reconcile must not
          // leave kakaoFriendAvoidanceEnabled=true with missing exclusions
          // (under-exclusion for new clients that ignore the pending gate).
          // The revert runs inside this reconcileId-guarded transaction, so a
          // stale failure never clobbers a newer sync's preference. OFF-mode
          // failure (preference=false + stale exclusions) stays unchanged.
          ...buildLegacyKakaoSyncFailureRevert({
            requestedEnabled: callerEnabled,
            preRequestAvoidanceEnabled,
          }),
          kakaoFriendReconcileStatus: "failed",
          kakaoFriendReconcileErrorCode: code,
          kakaoFriendReconcileFailedAt: FieldValue.serverTimestamp(),
          kakaoFriendReconcileId: FieldValue.delete(),
        };
        transaction.set(callerRef, terminalData, { merge: true });
        failedCallerData = terminalData;
      });
      if (!failedCallerData) {
        throw new HttpsError(
          "aborted",
          "더 최근의 친구 피하기 설정을 동기화하고 있어요.",
        );
      }
      try {
        await syncPublicProfileForUser(db, callerUid, failedCallerData);
      } catch (publicSyncError) {
        logger.error("public profile privacy gate sync failed", {
          callerUidHash: createHash("sha256")
            .update(callerUid)
            .digest("hex")
            .slice(0, 16),
          code: publicSyncError instanceof Error ? "sync_failed" : "unknown",
        });
      }
      logger.warn("syncKakaoTalkFriendBlocks failed", {
        callerUidHash: createHash("sha256")
          .update(callerUid)
          .digest("hex")
          .slice(0, 16),
        code,
      });
      throw new HttpsError(
        "failed-precondition",
        "카카오 친구 관계 확인을 완료하지 못했어요. 잠시 후 다시 시도해 주세요.",
      );
    }
  },
);

// =============================================================================
// One-time Kakao friend snapshot (kakao-friend-pairs contract v2)
// =============================================================================

export const createKakaoFriendPairsOnce =
  createCreateKakaoFriendPairsOnceFunction({
    db,
    verifyKakaoAccessToken: (accessToken) =>
      verifyKakaoAccessToken(accessToken),
    fetchFriends: (accessToken) =>
      fetchKakaoFriendServiceUserIds(accessToken),
  });

export const setKakaoFriendAvoidanceEnabled =
  createSetKakaoFriendAvoidanceEnabledFunction({ db });

/**
 * A↔B 상호 block을 blocks/{uid}/targets/{targetUid}에 생성.
 * 이미 양쪽 다 있으면 false 반환(이미 차단).
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
// KG이니시스 본인인증 전화번호 ↔ 기존 연락처 해시 상호 차단 정합성
// =============================================================================
async function reconcileVerifiedPhoneHashWithExistingContacts(
  verifiedUid: string,
  phoneHash: string
): Promise<void> {
  const ownersSnap = await db
    .collection("contactBlockedHashIndex")
    .doc(phoneHash)
    .collection("owners")
    .get();

  if (ownersSnap.empty) return;

  for (const ownerDoc of ownersSnap.docs) {
    const ownerUid = ownerDoc.id;
    if (ownerUid === verifiedUid) continue;

    await ensureMutualContactBlock(ownerUid, verifiedUid, phoneHash);
    await markContactHashMatchedToUsers(ownerUid, phoneHash, [verifiedUid]);
  }

  logger.info("verified phone contact reconciliation completed", {
    verifiedUidHash: createHash("sha256")
      .update(verifiedUid)
      .digest("hex")
      .slice(0, 16),
    ownerCount: ownersSnap.size,
  });
}

// =============================================================================
// backfillVerifiedPhoneHashIndex — 기존 KG이니시스 본인인증 문서의 파생 색인 생성
// =============================================================================
// 운영자만 페이지 단위로 호출한다. 원본 전화번호는 응답·로그에 포함하지 않는다.
export const backfillVerifiedPhoneHashIndex = onCall(
  withAppCheck({ timeoutSeconds: 120, memory: "512MiB" }),
  async (request) => {
    const callerUid = request.auth?.uid;
    const claims = request.auth?.token as Record<string, unknown> | undefined;
    if (!callerUid || claims?.admin !== true) {
      throw new HttpsError("permission-denied", "운영자 권한이 필요합니다.");
    }

    const data = getCallableData(request);
    const startAfterUid = asNonEmptyString(data.startAfterUid);
    if (startAfterUid && !/^[A-Za-z0-9_-]{1,128}$/.test(startAfterUid)) {
      throw new HttpsError("invalid-argument", "startAfterUid 형식이 올바르지 않아요.");
    }

    let query = db
      .collection("userPrivateVerifications")
      .orderBy(FieldPath.documentId())
      .limit(VERIFIED_PHONE_HASH_BACKFILL_PAGE_SIZE);
    if (startAfterUid) query = query.startAfter(startAfterUid);

    const page = await query.get();
    let indexedCount = 0;
    let skippedCount = 0;
    const reconciliations: Array<{ uid: string; phoneHash: string }> = [];
    const batch = db.batch();

    for (const verificationDoc of page.docs) {
      const verification = verificationDoc.data() as Record<string, unknown>;
      if (verification.verificationStatus !== "adult_verified") {
        skippedCount++;
        continue;
      }
      const phoneNumber = asNonEmptyString(verification.phoneNumber);
      const normalizedPhone = phoneNumber ? normalizeKoreanPhone(phoneNumber) : null;
      if (!normalizedPhone) {
        skippedCount++;
        continue;
      }

      const phoneHash = hashPhoneNumber(normalizedPhone);
      const existingPhoneHash = asNonEmptyString(verification.phoneHash);
      batch.set(
        verificationDoc.ref,
        { phoneHash, phoneHashUpdatedAt: FieldValue.serverTimestamp() },
        { merge: true }
      );
      batch.set(
        verifiedPhoneHashIndexOwnerRef(phoneHash, verificationDoc.id),
        {
          userId: verificationDoc.id,
          provider: ADULT_VERIFICATION_PROVIDER,
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
      if (existingPhoneHash && existingPhoneHash !== phoneHash) {
        batch.delete(
          verifiedPhoneHashIndexOwnerRef(existingPhoneHash, verificationDoc.id)
        );
      }
      indexedCount++;
      reconciliations.push({ uid: verificationDoc.id, phoneHash });
    }
    if (indexedCount > 0) {
      await batch.commit();
    }

    for (let i = 0; i < reconciliations.length; i += 10) {
      await Promise.all(
        reconciliations
          .slice(i, i + 10)
          .map(({ uid, phoneHash }) =>
            reconcileVerifiedPhoneHashWithExistingContacts(uid, phoneHash)
          )
      );
    }

    const lastDoc =
      page.docs.length > 0 ? page.docs[page.docs.length - 1] : undefined;
    return {
      scannedCount: page.size,
      indexedCount,
      skippedCount,
      nextStartAfterUid:
        page.size === VERIFIED_PHONE_HASH_BACKFILL_PAGE_SIZE && lastDoc
          ? lastDoc.id
          : null,
    };
  }
);

// =============================================================================
// purgeLegacyKakaoPhoneHashes — 더 이상 사용하지 않는 카카오 유래 해시 제거
// =============================================================================
// 운영자만 페이지 단위로 호출한다. 새로운 KG이니시스 기반 색인에는 영향을 주지 않는다.
export const purgeLegacyKakaoPhoneHashes = onCall(
  withAppCheck({ timeoutSeconds: 120, memory: "512MiB" }),
  async (request) => {
    const callerUid = request.auth?.uid;
    const claims = request.auth?.token as Record<string, unknown> | undefined;
    if (!callerUid || claims?.admin !== true) {
      throw new HttpsError("permission-denied", "운영자 권한이 필요합니다.");
    }

    const data = getCallableData(request);
    const startAfterUid = asNonEmptyString(data.startAfterUid);
    if (startAfterUid && !/^[A-Za-z0-9_-]{1,128}$/.test(startAfterUid)) {
      throw new HttpsError("invalid-argument", "startAfterUid 형식이 올바르지 않아요.");
    }

    let query = db
      .collection("userPrivate")
      .orderBy(FieldPath.documentId())
      .limit(VERIFIED_PHONE_HASH_BACKFILL_PAGE_SIZE);
    if (startAfterUid) query = query.startAfter(startAfterUid);

    const page = await query.get();
    const batch = db.batch();
    let purgedIndexCount = 0;
    for (const privateDoc of page.docs) {
      const phoneHash = asNonEmptyString(
        (privateDoc.data() as Record<string, unknown>).phoneHash
      );
      if (phoneHash) {
        batch.delete(db.collection("phoneHashIndex").doc(phoneHash));
        purgedIndexCount++;
      }
      batch.delete(privateDoc.ref);
    }
    if (!page.empty) {
      await batch.commit();
    }

    const lastDoc =
      page.docs.length > 0 ? page.docs[page.docs.length - 1] : undefined;
    return {
      purgedPrivateDocumentCount: page.size,
      purgedIndexCount,
      nextStartAfterUid:
        page.size === VERIFIED_PHONE_HASH_BACKFILL_PAGE_SIZE && lastDoc
          ? lastDoc.id
          : null,
    };
  }
);

// =============================================================================
// recEvents 기반 매치 체크 헬퍼
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
    logger.info("No mutual like found", { userA, userB });
    return null;
  }

  const existingMatches = await db
    .collection("matches")
    .where("userIds", "array-contains", userA)
    .get();

  for (const doc of existingMatches.docs) {
    const raw = (doc.data() as Record<string, unknown>).userIds;
    const ids = Array.isArray(raw)
      ? raw.map((v) => asString(v)).filter((v) => v.length > 0)
      : [];
    if (ids.includes(userB)) {
      logger.info("Match already exists", { matchId: doc.id });
      return doc.id;
    }
  }

  const matchRef = await db.collection("matches").add({
    userIds: [userA, userB],
    matchType,
    matchedAt: FieldValue.serverTimestamp(),
    status: "active",
    chatRoomId: null,
  });

  logger.info("Rec match created", {
    matchId: matchRef.id,
    userA,
    userB,
    matchType,
  });

  return matchRef.id;
}