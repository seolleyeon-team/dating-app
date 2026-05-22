import { getStorage } from "firebase-admin/storage";
import { type Firestore } from "firebase-admin/firestore";
import { HttpsError, onCall, type CallableRequest } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";
import { chatProfilePhotoBucket } from "./avatarMedia";

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

function safeDecodeUriComponent(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function isSafeRuntimePublicAvatarUrl(value: unknown): boolean {
  const url = asString(value);
  if (!url) return false;
  const decoded = safeDecodeUriComponent(url);
  const forbidden = [
    /^gs:\/\//i,
    /^gcs:\/\//i,
    /seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp|chat-profile-photos)/i,
    /\/source\//i,
    /\/jobs\//i,
    /\/candidates\//i,
    /X-Goog-/i,
    /GoogleAccessId/i,
    /Signature=/i,
    /Expires=/i,
    /AWSAccessKeyId/i,
    /X-Amz-/i,
  ];
  if (forbidden.some((pattern) => pattern.test(decoded))) return false;
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase();
    const bucketFromVirtualHost = host.endsWith(".storage.googleapis.com")
      ? host.replace(".storage.googleapis.com", "")
      : "";
    if (
      /seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp|chat-profile-photos)/i.test(
        bucketFromVirtualHost
      )
    ) {
      return false;
    }
  } catch {
    return false;
  }
  return true;
}

export function resolveSafeApprovedAvatarUrl(userData: Record<string, unknown>): string {
  const avatar = readMap(userData.avatar);
  const avatarStatus = asString(avatar.status).toLowerCase();
  const approvedAvatarUrl = asString(avatar.approvedAvatarUrl);
  if (avatarStatus === "approved" && isSafeRuntimePublicAvatarUrl(approvedAvatarUrl)) {
    return approvedAvatarUrl;
  }

  const onboarding = readMap(userData.onboarding);
  const avatarUrls = Array.isArray(onboarding.avatarUrls)
    ? onboarding.avatarUrls.map((item) => asString(item)).filter(Boolean)
    : [];
  const fallback = avatarUrls[0] ?? "";
  return isSafeRuntimePublicAvatarUrl(fallback) ? fallback : "";
}

function hasBlockedUser(userData: Record<string, unknown>, otherUid: string): boolean {
  const blockedUserIds = asStringArray(userData.blockedUserIds);
  if (blockedUserIds.includes(otherUid)) return true;

  const blockedUsers = userData.blockedUsers;
  if (Array.isArray(blockedUsers) && asStringArray(blockedUsers).includes(otherUid)) {
    return true;
  }
  if (isRecord(blockedUsers) && blockedUsers[otherUid] === true) {
    return true;
  }

  const blocks = userData.blocks;
  return isRecord(blocks) && blocks[otherUid] === true;
}

function isInactiveUser(userData: Record<string, unknown>): boolean {
  return (
    userData.deleted === true ||
    userData.isDeleted === true ||
    userData.suspended === true ||
    userData.isSuspended === true ||
    asString(userData.status).toLowerCase() === "deleted" ||
    asString(userData.status).toLowerCase() === "suspended"
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
  requesterUid: string;
  targetUid: string;
  requesterUserData: Record<string, unknown>;
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
  if (
    hasBlockedUser(params.requesterUserData, params.targetUid) ||
    hasBlockedUser(params.targetUserData, params.requesterUid)
  ) {
    return { kind: "deny", code: "permission-denied", message: "chat participant is blocked." };
  }
  if (isInactiveUser(params.targetUserData)) {
    return fallbackResponse(params.targetUserData, "target_inactive");
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
    },
    async (request): Promise<ChatRealProfilePhotoResponse> => {
      const requester = await resolveUser(request.auth);
      const requesterUid = requirePathSegment(requester.userId, "requesterUid");
      const data = isRecord(request.data) ? request.data : {};
      const chatRoomId = requirePathSegment(asString(data.chatRoomId), "chatRoomId");
      const targetUid = requirePathSegment(asString(data.targetUid), "targetUid");

      const roomRef = firestore.collection("chat_rooms").doc(chatRoomId);
      const requesterUserRef = firestore.collection("users").doc(requesterUid);
      const targetUserRef = firestore.collection("users").doc(targetUid);
      const privateMediaRef = firestore.collection("userPrivateMedia").doc(targetUid);
      const [roomSnap, requesterUserSnap, targetUserSnap, privateMediaSnap] = await Promise.all([
        roomRef.get(),
        requesterUserRef.get(),
        targetUserRef.get(),
        privateMediaRef.get(),
      ]);

      const targetUserData = (targetUserSnap.data() ?? {}) as Record<string, unknown>;
      const decision = evaluateChatRealPhotoAccess({
        roomExists: roomSnap.exists,
        roomData: (roomSnap.data() ?? {}) as Record<string, unknown>,
        requesterUid,
        targetUid,
        requesterUserData: (requesterUserSnap.data() ?? {}) as Record<string, unknown>,
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
