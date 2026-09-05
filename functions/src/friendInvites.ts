import { createHash, randomBytes } from "crypto";
import {
  FieldValue,
  Timestamp,
  type DocumentReference,
  type Firestore,
} from "firebase-admin/firestore";
import { HttpsError } from "firebase-functions/v2/https";

// =============================================================================
// Share-link invitations → Seolleyeon friendship / 3:3 team invitation
//
// Every share link (KakaoTalk button, App Link, custom scheme) carries ONLY an
// opaque token. The server-side invite record is the sole authority for what
// the token means (`purpose`), who issued it, and whether it is still valid.
// URL paths, `target=` query params and Kakao execution params are routing
// hints for the app and are never trusted for authorization.
//
//   FRIEND_INVITE → acceptFriendInviteByToken → friendships graph
//   TEAM_INVITE   → redeemTeamInviteByToken   → eventTeamInvites (pending)
//                   → existing respondEventTeamInvite decides membership
//
// A FRIEND token can never touch a team; a TEAM token can never touch the
// friend graph. Kakao friends (kakaoFriendPairs / Kakao Friends API
// snapshots) are a separate concept and are never consulted here.
//
// Callers must be Firebase-authenticated canonical app users (resolved by
// the callable layer). No Kakao access-token fallback exists on this path.
// =============================================================================

/** Production custom domain of the Firebase Hosting site. */
export const FRIEND_INVITE_HOST = "seolleyeon.com";
/** Hosts that older invite links were issued on. Still accepted by clients. */
export const FRIEND_INVITE_LEGACY_HOSTS: readonly string[] = [
  "seolleyeon-final.web.app",
];
export const FRIEND_INVITE_PATH = "/invite/friend";
export const TEAM_INVITE_PATH = "/invite/team";
/** Kakao execution-params / custom-scheme routing hints (NOT authorization). */
export const FRIEND_INVITE_TARGET = "friend_invite";
export const TEAM_INVITE_TARGET = "team_invite";
export const FRIEND_INVITE_EXPIRY_MS = 7 * 24 * 60 * 60 * 1000;
export const FRIEND_INVITE_TOKEN_BYTES = 32;
/** Leader + 2 members. Mirrors the eventTeamSetups capacity contract. */
export const EVENT_TEAM_CAPACITY = 3;

/** Server-owned, immutable purpose of a share-link invite record. */
export const INVITE_PURPOSE_FRIEND = "FRIEND_INVITE";
export const INVITE_PURPOSE_TEAM = "TEAM_INVITE";
export type InvitePurpose =
  | typeof INVITE_PURPOSE_FRIEND
  | typeof INVITE_PURPOSE_TEAM;

const FRIEND_INVITE_TOKEN_PATTERN = /^[0-9a-f]{64}$/;

export type FriendInviteAcceptStatus =
  | "accepted"
  | "already_friends"
  | "expired"
  | "invalid"
  | "self_invite"
  | "blocked";

export interface FriendInviteAcceptResult {
  status: FriendInviteAcceptStatus;
  message?: string;
  pairId?: string;
  otherUserId?: string;
  otherUserName?: string;
}

export type InvitePreviewStatus =
  | "valid"
  | "invalid"
  | "expired"
  | "used"
  | "self_invite"
  | "already_friends";

export interface InvitePreview {
  status: InvitePreviewStatus;
  /** Server-owned purpose. Absent when the token resolves to nothing. */
  purpose?: InvitePurpose;
  message?: string;
  inviterUserId?: string;
  inviterName?: string;
  inviterImageUrl?: string | null;
  teamSetupId?: string;
}

export type TeamInviteRedeemStatus =
  | "invited"
  | "already_invited"
  | "already_member"
  | "not_friends"
  | "team_full"
  | "team_missing"
  | "expired"
  | "invalid"
  | "self_invite"
  | "blocked";

export interface TeamInviteRedeemResult {
  status: TeamInviteRedeemStatus;
  message?: string;
  /** eventTeamInvites/{id} the app opens in the existing response screen. */
  teamInviteId?: string;
  teamSetupId?: string;
  inviterUserId?: string;
  inviterName?: string;
}

/** The subset of a resolved app user the invite module needs. */
export interface FriendInviteParticipant {
  userId: string;
  email: string;
  profileSnapshot: Record<string, unknown>;
  /** The users/{uid} document, when the resolver loaded it. */
  data?: Record<string, unknown>;
}

export interface CreatedInvite {
  inviteId: string;
  inviteToken: string;
  inviteUrl: string;
  deepLinkPath: string;
  expiresAt: string;
  purpose: InvitePurpose;
  /** Kakao `androidExecutionParams` / `iosExecutionParams` payload. */
  executionParams: Record<string, string>;
}

/** @deprecated name kept for existing imports. */
export type CreatedFriendInvite = CreatedInvite;

export type FriendUserEligibility =
  | "ok"
  | "missing"
  | "withdrawn"
  | "unverified";

const MESSAGES = {
  invalidLink: "유효하지 않은 초대 링크예요.",
  invalidInvite: "초대 정보가 올바르지 않아요.",
  usedInvite: "이미 사용된 초대 링크예요.",
  expired: "초대 링크가 만료되었어요.",
  selfInvite: "내가 만든 초대 링크는 사용할 수 없어요.",
  inviterGone: "초대한 사용자를 찾을 수 없어요.",
  blocked: "지금은 이 사용자와 함께할 수 없어요.",
  callerIneligible:
    "이 기능을 사용할 수 없는 계정이에요. 학생 인증 상태를 확인해주세요.",
  notFriendInvite: "친구 초대 링크가 아니에요.",
  notTeamInvite: "3:3 팀 초대 링크가 아니에요.",
  teamMissing: "팀 정보를 찾을 수 없어요.",
  teamNotLeader: "팀 리더만 초대 링크를 만들 수 있어요.",
  teamFull: "팀 정원이 찼어요.",
  teamNotFriends: "먼저 초대한 사람과 친구로 연결되어야 팀에 참여할 수 있어요.",
  teamAlreadyMember: "이미 이 팀에 참여하고 있어요.",
} as const;

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

function asStringOrNull(v: unknown): string | null {
  return typeof v === "string" && v.trim().length > 0 ? v : null;
}

function asStringArray(v: unknown): string[] {
  return Array.isArray(v)
    ? v.map((item) => asString(item)).filter((item) => item.length > 0)
    : [];
}

export function buildFriendPairId(userA: string, userB: string): string {
  const ids = [userA, userB].sort();
  return `${ids[0]}_${ids[1]}`;
}

export function hashInviteToken(rawToken: string): string {
  return createHash("sha256").update(rawToken).digest("hex");
}

export function generateFriendInviteToken(): string {
  return randomBytes(FRIEND_INVITE_TOKEN_BYTES).toString("hex");
}

/**
 * Cheap shape check so tampered / truncated tokens never reach Firestore.
 * Every token this server has ever issued is 32 random bytes as lowercase hex.
 */
export function isFriendInviteTokenShape(rawToken: string): boolean {
  return FRIEND_INVITE_TOKEN_PATTERN.test(rawToken);
}

function buildInviteUrl(path: string, rawToken: string): string {
  const url = new URL(`https://${FRIEND_INVITE_HOST}${path}`);
  url.searchParams.set("token", rawToken);
  return url.toString();
}

export function buildFriendInviteUrl(rawToken: string): string {
  return buildInviteUrl(FRIEND_INVITE_PATH, rawToken);
}

export function buildTeamInviteUrl(rawToken: string): string {
  return buildInviteUrl(TEAM_INVITE_PATH, rawToken);
}

/**
 * Parameters KakaoTalk hands to the installed app through
 * `kakao{NATIVE_APP_KEY}://kakaolink?target=...&token=...`.
 * Without these the Kakao button can only open a web URL.
 */
export function buildFriendInviteExecutionParams(
  rawToken: string,
): Record<string, string> {
  return { target: FRIEND_INVITE_TARGET, token: rawToken };
}

export function buildTeamInviteExecutionParams(
  rawToken: string,
): Record<string, string> {
  return { target: TEAM_INVITE_TARGET, token: rawToken };
}

export function readFriendName(
  snapshot: Record<string, unknown>,
  fallback: string,
): string {
  return asString(snapshot.nickname ?? fallback, fallback);
}

/**
 * The purpose stored on an invite record. Records written before the purpose
 * field existed were all friend invites (the only kind that ever existed), so
 * an absent field reads as FRIEND_INVITE; any other value fails closed.
 */
export function readInvitePurpose(
  data: Record<string, unknown> | null | undefined,
): InvitePurpose | null {
  const raw = data?.purpose;
  if (raw === undefined || raw === null) return INVITE_PURPOSE_FRIEND;
  if (raw === INVITE_PURPOSE_FRIEND || raw === INVITE_PURPOSE_TEAM) return raw;
  return null;
}

/**
 * Whether a users/{uid} document may take part in the friend graph right now.
 * Mirrors the callable resolver (student verified + Yonsei mailbox) and adds
 * the withdrawal / login-disabled markers used by the chat gates.
 */
export function readFriendUserEligibility(
  data: Record<string, unknown> | null | undefined,
): FriendUserEligibility {
  if (!data) return "missing";
  if (data.isWithdrawn === true || data.loginDisabled === true) {
    return "withdrawn";
  }
  const studentEmail = asString(data.studentEmail).trim().toLowerCase();
  if (data.isStudentVerified !== true || !studentEmail.endsWith("@yonsei.ac.kr")) {
    return "unverified";
  }
  return "ok";
}

function assertCallerEligible(participant: FriendInviteParticipant): void {
  if (
    participant.data &&
    readFriendUserEligibility(participant.data) !== "ok"
  ) {
    throw new HttpsError("failed-precondition", MESSAGES.callerIneligible);
  }
}

function readExpiresAt(data: Record<string, unknown>): Date | null {
  const raw = data.expiresAt;
  return raw instanceof Timestamp ? raw.toDate() : null;
}

function isExpired(data: Record<string, unknown>, now: Date): boolean {
  const expiresAt = readExpiresAt(data);
  return expiresAt !== null && expiresAt.getTime() <= now.getTime();
}

// =============================================================================
// Issue
// =============================================================================

export interface CreateFriendInviteParams {
  db: Firestore;
  inviter: FriendInviteParticipant;
  shareChannel?: string | null;
  now?: Date;
}

export async function createFriendInviteRecord(
  params: CreateFriendInviteParams,
): Promise<CreatedInvite> {
  const { db, inviter } = params;
  assertCallerEligible(inviter);
  const now = params.now ?? new Date();
  const inviteRef = db.collection("friendInvites").doc();
  const inviteToken = generateFriendInviteToken();
  const expiresAt = new Date(now.getTime() + FRIEND_INVITE_EXPIRY_MS);
  const shareChannel = asStringOrNull(params.shareChannel) ?? "kakaotalk";

  await inviteRef.set({
    purpose: INVITE_PURPOSE_FRIEND,
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
    purpose: INVITE_PURPOSE_FRIEND,
    executionParams: buildFriendInviteExecutionParams(inviteToken),
  };
}

export interface CreateTeamInviteParams {
  db: Firestore;
  leader: FriendInviteParticipant;
  teamSetupId: string | null | undefined;
  shareChannel?: string | null;
  now?: Date;
}

/**
 * A share link that lets a Seolleyeon FRIEND of the leader ask to join the
 * leader's 3:3 team. Redeeming it only creates the canonical pending
 * eventTeamInvites record; membership is still decided by
 * respondEventTeamInvite, exactly as for in-app invitations.
 */
export async function createTeamInviteRecord(
  params: CreateTeamInviteParams,
): Promise<CreatedInvite> {
  const { db, leader } = params;
  assertCallerEligible(leader);
  const teamSetupId = asStringOrNull(params.teamSetupId)?.trim() ?? "";
  if (!teamSetupId) {
    throw new HttpsError("invalid-argument", "teamSetupId가 필요해요.");
  }

  const teamSnap = await db.collection("eventTeamSetups").doc(teamSetupId).get();
  if (!teamSnap.exists) {
    throw new HttpsError("not-found", MESSAGES.teamMissing);
  }
  const team = (teamSnap.data() ?? {}) as Record<string, unknown>;
  if (asString(team.leaderUserId) !== leader.userId) {
    throw new HttpsError("permission-denied", MESSAGES.teamNotLeader);
  }
  const accepted = asStringArray(team.acceptedUserIds);
  const pending = asStringArray(team.pendingInviteeIds);
  if (accepted.length + pending.length >= EVENT_TEAM_CAPACITY) {
    throw new HttpsError("failed-precondition", MESSAGES.teamFull);
  }

  const now = params.now ?? new Date();
  const inviteRef = db.collection("friendInvites").doc();
  const inviteToken = generateFriendInviteToken();
  const expiresAt = new Date(now.getTime() + FRIEND_INVITE_EXPIRY_MS);
  const shareChannel = asStringOrNull(params.shareChannel) ?? "kakaotalk";

  await inviteRef.set({
    purpose: INVITE_PURPOSE_TEAM,
    teamSetupId,
    inviterUserId: leader.userId,
    inviterProfileSnapshot: leader.profileSnapshot,
    tokenHash: hashInviteToken(inviteToken),
    status: "pending",
    shareChannel,
    createdAt: FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp(),
    expiresAt: Timestamp.fromDate(expiresAt),
    acceptedByUserId: null,
    acceptedAt: null,
    teamInviteId: null,
    metadata: {
      inviterEmail: leader.email,
    },
  });

  return {
    inviteId: inviteRef.id,
    inviteToken,
    inviteUrl: buildTeamInviteUrl(inviteToken),
    deepLinkPath: TEAM_INVITE_PATH,
    expiresAt: expiresAt.toISOString(),
    purpose: INVITE_PURPOSE_TEAM,
    executionParams: buildTeamInviteExecutionParams(inviteToken),
  };
}

// =============================================================================
// Lookup
// =============================================================================

interface LookedUpInvite {
  ref: DocumentReference;
  id: string;
  data: Record<string, unknown>;
}

async function lookupInviteByToken(
  db: Firestore,
  rawToken: string,
): Promise<LookedUpInvite | null> {
  const inviteQuery = await db
    .collection("friendInvites")
    .where("tokenHash", "==", hashInviteToken(rawToken))
    .limit(1)
    .get();
  if (inviteQuery.empty) return null;
  const doc = inviteQuery.docs[0];
  return {
    ref: doc.ref,
    id: doc.id,
    data: (doc.data() ?? {}) as Record<string, unknown>,
  };
}

function normalizeToken(raw: string | null | undefined): string | null {
  const token = asStringOrNull(raw)?.trim() ?? null;
  return token && isFriendInviteTokenShape(token) ? token : null;
}

// =============================================================================
// Preview (read-only): what the app shows BEFORE the user confirms anything
// =============================================================================

export interface PreviewInviteParams {
  db: Firestore;
  rawToken: string | null | undefined;
  viewer: FriendInviteParticipant;
  now?: () => Date;
}

/**
 * Resolves a token to the minimum the confirmation UI needs. Performs no
 * writes and never consumes the invite. The returned `purpose` is the server
 * record's purpose, which the app must use for routing instead of any hint
 * that came with the link.
 */
export async function previewInviteByToken(
  params: PreviewInviteParams,
): Promise<InvitePreview> {
  const { db, viewer } = params;
  const now = (params.now ?? (() => new Date()))();
  const rawToken = normalizeToken(params.rawToken);
  if (!rawToken) {
    return { status: "invalid", message: MESSAGES.invalidLink };
  }

  const invite = await lookupInviteByToken(db, rawToken);
  if (!invite) {
    return { status: "invalid", message: MESSAGES.invalidLink };
  }
  const purpose = readInvitePurpose(invite.data);
  const inviterUserId = asString(invite.data.inviterUserId);
  if (!purpose || !inviterUserId) {
    return { status: "invalid", message: MESSAGES.invalidInvite };
  }

  const snapshotRaw = invite.data.inviterProfileSnapshot;
  const snapshot = isRecord(snapshotRaw) ? snapshotRaw : {};
  const base: InvitePreview = {
    status: "valid",
    purpose,
    inviterUserId,
    inviterName: readFriendName(snapshot, "설레연 친구"),
    inviterImageUrl: asStringOrNull(snapshot.profileImageUrl),
  };
  if (purpose === INVITE_PURPOSE_TEAM) {
    base.teamSetupId = asString(invite.data.teamSetupId);
  }

  if (inviterUserId === viewer.userId) {
    return { ...base, status: "self_invite", message: MESSAGES.selfInvite };
  }

  const status = asString(invite.data.status, "pending");
  if (status !== "pending") {
    if (
      status === "accepted" &&
      asStringOrNull(invite.data.acceptedByUserId) === viewer.userId
    ) {
      // The same account tapping the same link again: friend → already
      // friends; team → still routable (redeem answers already_invited and
      // the app reopens the pending team invitation).
      return purpose === INVITE_PURPOSE_FRIEND
        ? { ...base, status: "already_friends" }
        : base;
    }
    if (status === "expired") {
      return { ...base, status: "expired", message: MESSAGES.expired };
    }
    return { ...base, status: "used", message: MESSAGES.usedInvite };
  }
  if (isExpired(invite.data, now)) {
    return { ...base, status: "expired", message: MESSAGES.expired };
  }

  if (purpose === INVITE_PURPOSE_FRIEND) {
    const friendshipSnap = await db
      .collection("friendships")
      .doc(buildFriendPairId(inviterUserId, viewer.userId))
      .get();
    if (friendshipSnap.exists) {
      return { ...base, status: "already_friends" };
    }
  }

  return base;
}

// =============================================================================
// FRIEND_INVITE → friendship
// =============================================================================

export interface AcceptFriendInviteParams {
  db: Firestore;
  rawToken: string | null | undefined;
  acceptor: FriendInviteParticipant;
  now?: () => Date;
}

/**
 * Consume a FRIEND_INVITE token and create the canonical A↔B friendship.
 *
 * Idempotency / concurrency contract (covered by friendInvites.test.ts):
 * - friendships/{sorted(a)_sorted(b)} is the single canonical document, so
 *   A→B and B→A invites, double taps, and retries converge on one friendship.
 * - friendsCount is incremented only in the branch that creates the
 *   friendship, inside the same transaction, so it moves by exactly one.
 * - Every transaction.get() happens before the first transaction.set().
 * - A TEAM_INVITE token is rejected before any read of the friend graph.
 */
export async function acceptFriendInviteByToken(
  params: AcceptFriendInviteParams,
): Promise<FriendInviteAcceptResult> {
  const { db, acceptor } = params;
  const nowFn = params.now ?? (() => new Date());
  const rawToken = normalizeToken(params.rawToken);

  if (!rawToken) {
    return { status: "invalid", message: MESSAGES.invalidLink };
  }

  // Same eligibility gate as the inviter: a withdrawn or login-disabled
  // account must not re-enter the friend graph through a share link.
  if (acceptor.data && readFriendUserEligibility(acceptor.data) !== "ok") {
    return { status: "invalid", message: MESSAGES.callerIneligible };
  }

  const invite = await lookupInviteByToken(db, rawToken);
  if (!invite) {
    return { status: "invalid", message: MESSAGES.invalidLink };
  }

  const inviteRef = invite.ref;
  const inviteId = invite.id;
  const inviteData = invite.data;
  const inviterUserId = asString(inviteData.inviterUserId ?? "");

  if (readInvitePurpose(inviteData) !== INVITE_PURPOSE_FRIEND) {
    return { status: "invalid", message: MESSAGES.notFriendInvite };
  }

  if (!inviterUserId) {
    return { status: "invalid", message: MESSAGES.invalidInvite };
  }

  if (inviterUserId === acceptor.userId) {
    return { status: "self_invite", message: MESSAGES.selfInvite };
  }

  const pairId = buildFriendPairId(inviterUserId, acceptor.userId);
  const friendshipRef = db.collection("friendships").doc(pairId);
  const inviterUserRef = db.collection("users").doc(inviterUserId);
  const acceptorUserRef = db.collection("users").doc(acceptor.userId);
  const inviterFriendRef = inviterUserRef
    .collection("friends")
    .doc(acceptor.userId);
  const acceptorFriendRef = acceptorUserRef
    .collection("friends")
    .doc(inviterUserId);
  const acceptorBlocksInviterRef = db
    .collection("blocks")
    .doc(acceptor.userId)
    .collection("targets")
    .doc(inviterUserId);
  const inviterBlocksAcceptorRef = db
    .collection("blocks")
    .doc(inviterUserId)
    .collection("targets")
    .doc(acceptor.userId);

  return await db.runTransaction(async (transaction) => {
    // ---- reads (all of them, before any write) ---------------------------
    const freshInviteSnap = await transaction.get(inviteRef);
    const existingFriendshipSnap = await transaction.get(friendshipRef);
    const inviterUserSnap = await transaction.get(inviterUserRef);
    const forwardBlockSnap = await transaction.get(acceptorBlocksInviterRef);
    const reverseBlockSnap = await transaction.get(inviterBlocksAcceptorRef);

    if (!freshInviteSnap.exists) {
      return { status: "invalid", message: MESSAGES.invalidLink };
    }

    const freshInvite = (freshInviteSnap.data() ?? {}) as Record<
      string,
      unknown
    >;
    if (
      asString(freshInvite.inviterUserId ?? "") !== inviterUserId ||
      readInvitePurpose(freshInvite) !== INVITE_PURPOSE_FRIEND
    ) {
      return { status: "invalid", message: MESSAGES.invalidInvite };
    }
    const currentStatus = asString(freshInvite.status ?? "pending", "pending");
    const acceptedByUserId = asStringOrNull(freshInvite.acceptedByUserId);
    const now = nowFn();

    const inviterSnapshotRaw = freshInvite.inviterProfileSnapshot;
    const inviterSnapshot = isRecord(inviterSnapshotRaw)
      ? inviterSnapshotRaw
      : {};
    const otherUserName = readFriendName(inviterSnapshot, inviterUserId);

    // Already friends: converge without touching counts. A pending invite is
    // marked consumed so it cannot be replayed by a third account later.
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
          { merge: true },
        );
      }
      return {
        status: "already_friends",
        pairId,
        otherUserId: inviterUserId,
        otherUserName,
      };
    }

    if (isExpired(freshInvite, now)) {
      if (currentStatus === "pending") {
        transaction.set(
          inviteRef,
          { status: "expired", updatedAt: FieldValue.serverTimestamp() },
          { merge: true },
        );
      }
      return { status: "expired", message: MESSAGES.expired };
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
        return { status: "expired", message: MESSAGES.expired };
      }
      return { status: "invalid", message: MESSAGES.usedInvite };
    }

    // The inviter must still be a live, verified member — otherwise the
    // friendship would be an orphan edge to a withdrawn account.
    const inviterEligibility = readFriendUserEligibility(
      inviterUserSnap.exists
        ? ((inviterUserSnap.data() ?? {}) as Record<string, unknown>)
        : null,
    );
    if (inviterEligibility !== "ok") {
      transaction.set(
        inviteRef,
        {
          status: "revoked",
          revokedReason: `inviter_${inviterEligibility}`,
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true },
      );
      return { status: "invalid", message: MESSAGES.inviterGone };
    }

    // A block in either direction must not be bypassed by a share link.
    // The invite is left pending so lifting the block later still works.
    if (forwardBlockSnap.exists || reverseBlockSnap.exists) {
      return { status: "blocked", message: MESSAGES.blocked };
    }

    // ---- writes ------------------------------------------------------------
    const sortedUserIds = [inviterUserId, acceptor.userId].sort();

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
      { merge: true },
    );

    transaction.set(
      inviterUserRef,
      {
        friendsCount: FieldValue.increment(1),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true },
    );
    transaction.set(
      acceptorUserRef,
      {
        friendsCount: FieldValue.increment(1),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true },
    );

    return {
      status: "accepted",
      pairId,
      otherUserId: inviterUserId,
      otherUserName,
    };
  });
}

// =============================================================================
// TEAM_INVITE → pending eventTeamInvites record (no membership, no friendship)
// =============================================================================

export interface RedeemTeamInviteParams {
  db: Firestore;
  rawToken: string | null | undefined;
  redeemer: FriendInviteParticipant;
  now?: () => Date;
}

/**
 * Turns a TEAM_INVITE token into the canonical pending eventTeamInvites
 * record for (team, redeemer), applying the same invariants as
 * createEventTeamInvite (leader-issued, friends only, capacity, no
 * duplicate pending invite). Membership is granted only later by
 * respondEventTeamInvite when the user explicitly accepts in the app.
 *
 * This function never reads or writes friendships, friend edges, or
 * friendsCount, and a FRIEND_INVITE token is rejected before any team read.
 */
export async function redeemTeamInviteByToken(
  params: RedeemTeamInviteParams,
): Promise<TeamInviteRedeemResult> {
  const { db, redeemer } = params;
  const nowFn = params.now ?? (() => new Date());
  const rawToken = normalizeToken(params.rawToken);
  if (!rawToken) {
    return { status: "invalid", message: MESSAGES.invalidLink };
  }
  if (redeemer.data && readFriendUserEligibility(redeemer.data) !== "ok") {
    return { status: "invalid", message: MESSAGES.callerIneligible };
  }

  const invite = await lookupInviteByToken(db, rawToken);
  if (!invite) {
    return { status: "invalid", message: MESSAGES.invalidLink };
  }
  if (readInvitePurpose(invite.data) !== INVITE_PURPOSE_TEAM) {
    return { status: "invalid", message: MESSAGES.notTeamInvite };
  }
  const leaderUserId = asString(invite.data.inviterUserId);
  const teamSetupId = asString(invite.data.teamSetupId);
  if (!leaderUserId || !teamSetupId) {
    return { status: "invalid", message: MESSAGES.invalidInvite };
  }
  if (leaderUserId === redeemer.userId) {
    return { status: "self_invite", message: MESSAGES.selfInvite };
  }
  const leaderSnapshotRaw = invite.data.inviterProfileSnapshot;
  const leaderSnapshot = isRecord(leaderSnapshotRaw) ? leaderSnapshotRaw : {};
  const inviterName = readFriendName(leaderSnapshot, leaderUserId);

  // Same dedupe as createEventTeamInvite: one pending invitation per pair.
  const pendingQuery = await db
    .collection("eventTeamInvites")
    .where("teamSetupId", "==", teamSetupId)
    .where("inviteeUserId", "==", redeemer.userId)
    .where("status", "==", "pending")
    .limit(1)
    .get();
  if (!pendingQuery.empty) {
    return {
      status: "already_invited",
      teamInviteId: pendingQuery.docs[0].id,
      teamSetupId,
      inviterUserId: leaderUserId,
      inviterName,
    };
  }

  const inviteRef = invite.ref;
  const teamRef = db.collection("eventTeamSetups").doc(teamSetupId);
  const friendEdgeRef = db
    .collection("users")
    .doc(leaderUserId)
    .collection("friends")
    .doc(redeemer.userId);
  const teamInviteRef = db.collection("eventTeamInvites").doc();
  const leaderBlocksRedeemerRef = db
    .collection("blocks")
    .doc(leaderUserId)
    .collection("targets")
    .doc(redeemer.userId);
  const redeemerBlocksLeaderRef = db
    .collection("blocks")
    .doc(redeemer.userId)
    .collection("targets")
    .doc(leaderUserId);

  return await db.runTransaction(async (transaction) => {
    // ---- reads -------------------------------------------------------------
    const freshInviteSnap = await transaction.get(inviteRef);
    const teamSnap = await transaction.get(teamRef);
    const friendEdgeSnap = await transaction.get(friendEdgeRef);
    const forwardBlockSnap = await transaction.get(leaderBlocksRedeemerRef);
    const reverseBlockSnap = await transaction.get(redeemerBlocksLeaderRef);

    if (!freshInviteSnap.exists) {
      return { status: "invalid", message: MESSAGES.invalidLink };
    }
    const freshInvite = (freshInviteSnap.data() ?? {}) as Record<
      string,
      unknown
    >;
    if (
      readInvitePurpose(freshInvite) !== INVITE_PURPOSE_TEAM ||
      asString(freshInvite.inviterUserId) !== leaderUserId ||
      asString(freshInvite.teamSetupId) !== teamSetupId
    ) {
      return { status: "invalid", message: MESSAGES.invalidInvite };
    }
    const currentStatus = asString(freshInvite.status, "pending");
    const now = nowFn();

    if (isExpired(freshInvite, now)) {
      if (currentStatus === "pending") {
        transaction.set(
          inviteRef,
          { status: "expired", updatedAt: FieldValue.serverTimestamp() },
          { merge: true },
        );
      }
      return { status: "expired", message: MESSAGES.expired };
    }
    if (currentStatus !== "pending") {
      if (
        currentStatus === "accepted" &&
        asStringOrNull(freshInvite.acceptedByUserId) === redeemer.userId
      ) {
        return {
          status: "already_invited",
          teamInviteId: asStringOrNull(freshInvite.teamInviteId) ?? undefined,
          teamSetupId,
          inviterUserId: leaderUserId,
          inviterName,
        };
      }
      if (currentStatus === "expired") {
        return { status: "expired", message: MESSAGES.expired };
      }
      return { status: "invalid", message: MESSAGES.usedInvite };
    }

    if (!teamSnap.exists) {
      return { status: "team_missing", message: MESSAGES.teamMissing };
    }
    const team = (teamSnap.data() ?? {}) as Record<string, unknown>;
    if (asString(team.leaderUserId) !== leaderUserId) {
      return { status: "invalid", message: MESSAGES.invalidInvite };
    }
    const accepted = asStringArray(team.acceptedUserIds);
    const pending = asStringArray(team.pendingInviteeIds);

    if (accepted.includes(redeemer.userId)) {
      return {
        status: "already_member",
        teamSetupId,
        inviterUserId: leaderUserId,
        inviterName,
        message: MESSAGES.teamAlreadyMember,
      };
    }
    if (pending.includes(redeemer.userId)) {
      return {
        status: "already_invited",
        teamSetupId,
        inviterUserId: leaderUserId,
        inviterName,
      };
    }
    // A block in either direction denies without consuming the token or
    // occupying a slot (respondEventTeamInvite re-checks at commit time too).
    if (forwardBlockSnap.exists || reverseBlockSnap.exists) {
      return { status: "blocked", message: MESSAGES.blocked };
    }
    // Team invitations are for Seolleyeon friends only. A share link does
    // NOT create the friendship — that needs a FRIEND_INVITE and consent.
    if (!friendEdgeSnap.exists) {
      return {
        status: "not_friends",
        teamSetupId,
        inviterUserId: leaderUserId,
        inviterName,
        message: MESSAGES.teamNotFriends,
      };
    }
    if (accepted.length + pending.length >= EVENT_TEAM_CAPACITY) {
      return { status: "team_full", message: MESSAGES.teamFull };
    }

    // ---- writes ------------------------------------------------------------
    transaction.set(teamInviteRef, {
      teamSetupId,
      inviterUserId: leaderUserId,
      inviteeUserId: redeemer.userId,
      status: "pending",
      source: "share_link",
      shareInviteId: invite.id,
      createdAt: FieldValue.serverTimestamp(),
      respondedAt: null,
    });
    transaction.set(
      teamRef,
      {
        pendingInviteeIds: [...pending, redeemer.userId],
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true },
    );
    transaction.set(
      inviteRef,
      {
        status: "accepted",
        updatedAt: FieldValue.serverTimestamp(),
        acceptedByUserId: redeemer.userId,
        acceptedAt: FieldValue.serverTimestamp(),
        teamInviteId: teamInviteRef.id,
      },
      { merge: true },
    );

    return {
      status: "invited",
      teamInviteId: teamInviteRef.id,
      teamSetupId,
      inviterUserId: leaderUserId,
      inviterName,
    };
  });
}
