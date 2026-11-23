import { getStorage } from "firebase-admin/storage";
import { type Firestore } from "firebase-admin/firestore";
import { HttpsError, onCall, type CallableRequest } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";
import { isRestrictedAccountData } from "./accountStatePolicy";
import { chatProfilePhotoBucket } from "./avatarMedia";
import { isSafePublicAvatarUrl } from "./publicMediaUrlPolicy";

type ChatRealPhotoAuth = CallableRequest<unknown>["auth"];

export type ResolvedChatRealPhotoUser = {
  userId: string;
  email: string;
  data: Record<string, unknown>;
};

type ResolveChatRealPhotoUser = (
  auth: ChatRealPhotoAuth
) => Promise<ResolvedChatRealPhotoUser>;

export type ChatRealProfilePhotoResponse = {
  displayMode: "real_photo" | "avatar";
  imageUrl: string;
  approvedAvatarUrl?: string;
  expiresAt?: string;
  reason?: string;
};

export type ChatRealPhotoDecision =
  | {
      kind: "deny";
      code: "permission-denied" | "not-found";
      message: string;
    }
  | {
      kind: "fallback";
      reason: string;
      approvedAvatarUrl: string;
    }
  | {
      kind: "real_photo";
      storageBucket: string;
      storagePath: string;
      approvedAvatarUrl: string;
    };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readMap(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => asString(item)).filter(Boolean);
}

function requirePathSegment(value: string, label: string): string {
  const normalized = value.trim();
  if (!/^[A-Za-z0-9_-]+$/.test(normalized)) {
    throw new HttpsError("invalid-argument", `${label} is not a safe path segment.`);
  }
  return normalized;
}

export function resolveSafeApprovedAvatarUrl(userData: Record<string, unknown>): string {
  const avatar = readMap(userData.avatar);
  const avatarStatus = asString(avatar.status).toLowerCase();
  const approvedAvatarUrl = asString(avatar.approvedAvatarUrl);
  if (avatarStatus === "approved" && isSafePublicAvatarUrl(approvedAvatarUrl)) {
    return approvedAvatarUrl;
  }

  const onboarding = readMap(userData.onboarding);
  const avatarUrls = Array.isArray(onboarding.avatarUrls)
    ? onboarding.avatarUrls.map((item) => asString(item)).filter(Boolean)
    : [];
  const fallback = avatarUrls[0] ?? "";
  return isSafePublicAvatarUrl(fallback) ? fallback : "";
}

// Statuses under which an account's real photograph must not be served. The
// moderation decision writes `banned` / `suspended` together with
// `isActive: false` (communityModeration.ts); withdrawal writes `withdrawn` /
// `isWithdrawn`. Same set as the public-profile projection
// (publicProfileSync.ts), which removes the profile for these accounts.
const INACTIVE_ACCOUNT_STATUSES = new Set([
  "banned",
  "blocked",
  "deleted",
  "restricted_rejoin",
  "suspended",
  "withdrawn",
]);

function isInactiveUser(userData: Record<string, unknown>): boolean {
  return (
    userData.deleted === true ||
    userData.isDeleted === true ||
    userData.suspended === true ||
    userData.isSuspended === true ||
    userData.isWithdrawn === true ||
    userData.isActive === false ||
    INACTIVE_ACCOUNT_STATUSES.has(asString(userData.status).toLowerCase()) ||
    // AUD-22: the shared classifier adds what this list missed (a deletion in
    // progress, `accountStatus`, isBanned).
    isRestrictedAccountData(userData)
  );
}

function isActiveChatRoom(roomData: Record<string, unknown>): boolean {
  const status = asString(roomData.status).toLowerCase();
  if (!status) return true;
  if (["active", "open", "created"].includes(status)) return true;
  return false;
}

function fallbackResponse(
  userData: Record<string, unknown>,
  reason: string
): ChatRealPhotoDecision {
  return {
    kind: "fallback",
    reason,
    approvedAvatarUrl: resolveSafeApprovedAvatarUrl(userData),
  };
}

export function evaluateChatRealPhotoAccess(params: {
  roomExists: boolean;
  roomData: Record<string, unknown>;
  /// A real photo is disclosed only after either participant has actually
  /// sent a text message. This is supplied from the authoritative room
  /// subcollection by the callable, rather than trusting any room metadata.
  hasTextMessage?: boolean;
  requesterUid: string;
  targetUid: string;
  /// Whether a block exists in either direction between the two participants,
  /// read from the authoritative store `blocks/{uid}/targets/{otherUid}`
  /// (reportAndBlockUser and contact blocks write both directions). Required:
  /// this used to be derived from `users/{uid}.blockedUserIds`, a field
  /// nothing writes, so the check never fired and a blocked participant
  /// could still fetch the other's real photograph.
  blockedBetweenParticipants: boolean;
  targetUserData: Record<string, unknown>;
  privateMediaData: Record<string, unknown>;
  chatBucket?: string;
}): ChatRealPhotoDecision {
  if (!params.roomExists) {
    return { kind: "deny", code: "not-found", message: "chat room was not found." };
  }

  if (params.requesterUid === params.targetUid) {
    return { kind: "deny", code: "permission-denied", message: "self real-photo access is not allowed." };
  }

  const participantIds = asStringArray(params.roomData.participantIds);
  if (!participantIds.includes(params.requesterUid)) {
    return { kind: "deny", code: "permission-denied", message: "requester is not a chat participant." };
  }
  if (!participantIds.includes(params.targetUid)) {
    return { kind: "deny", code: "permission-denied", message: "target is not a chat participant." };
  }
  if (!isActiveChatRoom(params.roomData)) {
    return { kind: "deny", code: "permission-denied", message: "chat room is not active." };
  }
  // Fail closed: anything other than an explicit "no block" is a block.
  if (params.blockedBetweenParticipants !== false) {
    return { kind: "deny", code: "permission-denied", message: "chat participant is blocked." };
  }
  if (isInactiveUser(params.targetUserData)) {
    return fallbackResponse(params.targetUserData, "target_inactive");
  }
  if (params.hasTextMessage !== true) {
    return fallbackResponse(params.targetUserData, "no_text_message");
  }

  const photoConsent = readMap(params.privateMediaData.photoConsent);
  if (photoConsent.chatPartnerRealPhotoDisclosure !== true) {
    return fallbackResponse(params.targetUserData, "no_chat_real_photo_consent");
  }

  const chatRealPhoto = readMap(params.privateMediaData.chatRealPhoto);
  if (chatRealPhoto.enabled !== true) {
    return fallbackResponse(params.targetUserData, "no_chat_real_photo");
  }

  const storageBucket = asString(chatRealPhoto.storageBucket);
  const storagePath = asString(chatRealPhoto.storagePath);
  const requiredBucket = params.chatBucket ?? chatProfilePhotoBucket();
  if (storageBucket !== requiredBucket || !storagePath.startsWith(`users/${params.targetUid}/chat-profile/`)) {
    return fallbackResponse(params.targetUserData, "invalid_chat_real_photo_asset");
  }

  return {
    kind: "real_photo",
    storageBucket,
    storagePath,
    approvedAvatarUrl: resolveSafeApprovedAvatarUrl(params.targetUserData),
  };
}

function signedUrlExpiresAt(): Date {
  const raw = Number(process.env.CHAT_REAL_PHOTO_SIGNED_URL_TTL_SECONDS ?? 300);
  const ttlSeconds = Number.isFinite(raw) ? Math.max(30, Math.min(raw, 300)) : 300;
  return new Date(Date.now() + ttlSeconds * 1000);
}

export function createGetChatRealProfilePhotoFunction(
  firestore: Firestore,
  resolveUser: ResolveChatRealPhotoUser
) {
  return onCall(
    {
      timeoutSeconds: 30,
      memory: "256MiB",
      enforceAppCheck: true,
    },
    async (request): Promise<ChatRealProfilePhotoResponse> => {
      const requester = await resolveUser(request.auth);
      const requesterUid = requirePathSegment(requester.userId, "requesterUid");
      const data = isRecord(request.data) ? request.data : {};
      const chatRoomId = requirePathSegment(asString(data.chatRoomId), "chatRoomId");
      const targetUid = requirePathSegment(asString(data.targetUid), "targetUid");

      const roomRef = firestore.collection("chat_rooms").doc(chatRoomId);
      const blockRef = (ownerUid: string, blockedUid: string) =>
        firestore.collection("blocks").doc(ownerUid).collection("targets").doc(blockedUid);
      const targetUserRef = firestore.collection("users").doc(targetUid);
      const privateMediaRef = firestore.collection("userPrivateMedia").doc(targetUid);
      const textMessageQuery = roomRef
        .collection("messages")
        .where("type", "==", "text")
        .limit(1);
      const [
        roomSnap,
        requesterBlockSnap,
        targetBlockSnap,
        targetUserSnap,
        privateMediaSnap,
        textMessageSnap,
      ] = await Promise.all([
        roomRef.get(),
        blockRef(requesterUid, targetUid).get(),
        blockRef(targetUid, requesterUid).get(),
        targetUserRef.get(),
        privateMediaRef.get(),
        textMessageQuery.get(),
      ]);

      const targetUserData = (targetUserSnap.data() ?? {}) as Record<string, unknown>;
      const decision = evaluateChatRealPhotoAccess({
        roomExists: roomSnap.exists,
        roomData: (roomSnap.data() ?? {}) as Record<string, unknown>,
        hasTextMessage: !textMessageSnap.empty,
        requesterUid,
        targetUid,
        blockedBetweenParticipants: requesterBlockSnap.exists || targetBlockSnap.exists,
        targetUserData,
        privateMediaData: (privateMediaSnap.data() ?? {}) as Record<string, unknown>,
      });

      if (decision.kind === "deny") {
        throw new HttpsError(decision.code, decision.message);
      }

      if (decision.kind === "fallback") {
        return {
          displayMode: "avatar",
          imageUrl: decision.approvedAvatarUrl,
          approvedAvatarUrl: decision.approvedAvatarUrl,
          reason: decision.reason,
        };
      }

      const expiresAt = signedUrlExpiresAt();
      const [imageUrl] = await getStorage()
        .bucket(decision.storageBucket)
        .file(decision.storagePath)
        .getSignedUrl({
          version: "v4",
          action: "read",
          expires: expiresAt,
        });

      logger.info("Issued chat real profile photo runtime URL", {
        chatRoomId,
        requesterUid,
        targetUid,
        displayMode: "real_photo",
      });

      return {
        displayMode: "real_photo",
        imageUrl,
        approvedAvatarUrl: decision.approvedAvatarUrl,
        expiresAt: expiresAt.toISOString(),
      };
    }
  );
}
