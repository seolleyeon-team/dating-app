/**
 * 안전도장 (Safe Stamp) — 서버 권위 write
 * 경로: functions/src/safetyStamp.ts
 *
 * 예전에는 클라이언트가 `chat_rooms/{roomId}/promises/{promiseId}.safetyStamp`
 * 를 직접 트랜잭션으로 갱신했다. 도장을 찍는 주체(uid)가 클라이언트 파라미터였고,
 * 기존 도장 목록을 방 문서의 `activePromise` 미러에서 읽었기 때문에
 * 미러를 조작하면 약속 문서의 도장 상태까지 흔들 수 있었다.
 *
 * 이제 도장은 서버만 쓴다.
 *
 *   auth.uid          → 도장 주인 (클라이언트가 지정할 수 없다)
 *   promise 문서      → 기존 도장 목록의 유일한 source of truth (미러 아님)
 *   participantIds    → 방 문서에서 읽는다 (약속 문서의 사본을 믿지 않는다)
 *   idempotency       → 같은 사람이 같은 단계를 다시 눌러도 side effect 1회
 *
 * 보장 범위: SERVER_AUTHENTICATED_SELF_ATTESTATION.
 * 서버는 "이 도장을 찍은 사람이 인증된 방 참가자 본인"임을 보장한다.
 * 두 사람이 실제로 같은 장소에서 만났는지는 보장하지 않는다 (근접 검증은
 * 단말에서 수행되며 서버가 재현할 수 없다). 이를 대면 증명으로 표현하지 않는다.
 */

import { FieldValue, getFirestore } from "firebase-admin/firestore";
import { HttpsError, onCall } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";

import { withAppCheck } from "./appCheckPolicy";

export type SafetyStampPhase = "meetup" | "goodbye";

export const SAFETY_STAMP_PHASES: SafetyStampPhase[] = ["meetup", "goodbye"];

/** 도장을 더 이상 받을 수 없는 약속 상태. */
export const SAFETY_STAMP_TERMINAL_PROMISE_STATUSES = [
  "cancelled",
  "canceled",
  "rejected",
  "completed",
  "expired",
];

function db() {
  return getFirestore();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asTrimmed(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function asIdSet(value: unknown): Set<string> {
  if (!Array.isArray(value)) return new Set<string>();
  const out = new Set<string>();
  for (const entry of value) {
    const id = asTrimmed(entry);
    if (id.length > 0) out.add(id);
  }
  return out;
}

export function normalizeSafetyStampPhase(value: unknown): SafetyStampPhase | null {
  const text = asTrimmed(value).toLowerCase();
  return (SAFETY_STAMP_PHASES as readonly string[]).includes(text)
    ? (text as SafetyStampPhase)
    : null;
}

/**
 * 기존 도장 목록.
 *
 * `meetupStampedUserIds` 가 비어 있으면 legacy `stampedUserIds` 를 쓴다
 * (클라이언트가 쓰던 마이그레이션 규칙과 동일하다).
 */
export function effectiveMeetupStamps(
  safetyStamp: Record<string, unknown>
): Set<string> {
  const meetup = asIdSet(safetyStamp.meetupStampedUserIds);
  return meetup.size > 0 ? meetup : asIdSet(safetyStamp.stampedUserIds);
}

/**
 * 약속 시각을 밀리초로 정규화한다 (Timestamp / Date / number 모두 허용).
 */
export function promiseDateTimeMs(value: unknown): number | null {
  if (value == null) return null;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (value instanceof Date) return value.getTime();
  const maybe = value as { toMillis?: () => number };
  if (typeof maybe.toMillis === "function") {
    const ms = maybe.toMillis();
    return Number.isFinite(ms) ? ms : null;
  }
  return null;
}

/**
 * 기존 도장이 "지금 이 약속"에 대한 것인지.
 *
 * 약속을 수정하면 시간·장소가 바뀌지만 safetyStamp 는 그대로 남는다.
 * (클라이언트가 지울 수 없고, 서버도 지우지 않는다.) 그대로 이어 쓰면
 * 예전 약속에서 찍은 도장이 새 약속의 출석으로 계산돼서, 실제로는 오지 않은
 * 사람이 참석한 것처럼 기록된다. 도장을 찍을 때 대상 약속 시각을 함께
 * 남겨두고, 시각이 달라졌으면 이전 도장을 무시한다.
 */
export function stampsMatchCurrentPromise(
  safetyStamp: Record<string, unknown>,
  promiseDateTime: unknown
): boolean {
  const stampedFor = safetyStamp.stampedForDateTimeMs;
  const current = promiseDateTimeMs(promiseDateTime);
  if (current == null) return true;
  // 예전 문서에는 이 표식이 없다. 그 경우는 기존 도장을 그대로 인정한다
  // (마이그레이션 중 정상 진행을 막지 않기 위해서다).
  if (typeof stampedFor !== "number") return true;
  return stampedFor === current;
}

export type SafetyStampResult = {
  ok: true;
  /** 이미 찍혀 있어 side effect 없이 끝난 경우. */
  alreadyStamped: boolean;
  phase: SafetyStampPhase;
  /** 이 도장으로 해당 단계가 전원 완료되었는지. */
  phaseCompleted: boolean;
};

/**
 * 안전도장을 찍는다.
 *
 * 도장 주인은 항상 호출자(auth.uid)다. 클라이언트가 대상 uid나 도장 배열
 * 전체를 보낼 수 없다.
 */
export const submitSafetyStamp = onCall(
  withAppCheck(),
  async (request): Promise<SafetyStampResult> => {
    const uid = asTrimmed(request.auth?.uid);
    if (uid.length === 0) {
      throw new HttpsError("unauthenticated", "로그인이 필요해요.");
    }

    const data = isRecord(request.data) ? request.data : {};
    const roomId = asTrimmed(data.roomId);
    const promiseId = asTrimmed(data.promiseId);
    const phase = normalizeSafetyStampPhase(data.phase);
    // 근접 검증 결과는 단말이 만든 불투명한 기록이다. 서버는 재현할 수 없으므로
    // 내용을 신뢰하지 않고, 호출자 본인 키 아래에만 그대로 보관한다.
    const verification = isRecord(data.verification) ? data.verification : null;

    if (roomId.length === 0 || promiseId.length === 0 || phase == null) {
      throw new HttpsError("invalid-argument", "요청 정보가 올바르지 않아요.");
    }

    const roomRef = db().collection("chat_rooms").doc(roomId);
    const promiseRef = roomRef.collection("promises").doc(promiseId);
    const inProgressMessageRef = roomRef.collection("messages").doc();
    const completedMessageRef = roomRef.collection("messages").doc();

    return db().runTransaction<SafetyStampResult>(async (tx) => {
      const [roomSnap, promiseSnap] = await Promise.all([
        tx.get(roomRef),
        tx.get(promiseRef),
      ]);

      if (!roomSnap.exists) {
        throw new HttpsError("not-found", "채팅방이 존재하지 않습니다.");
      }
      if (!promiseSnap.exists) {
        throw new HttpsError("not-found", "약속이 존재하지 않습니다.");
      }

      const room = roomSnap.data() ?? {};
      const promise = promiseSnap.data() ?? {};

      // 참가자 명단은 방 문서에서만 읽는다. 약속 문서의 participantIds 는
      // 예전 클라이언트가 쓰던 사본이라 신뢰하지 않는다.
      const participantIds = asIdSet(room.participantIds);
      if (!participantIds.has(uid)) {
        throw new HttpsError(
          "permission-denied",
          "이 채팅방의 참여자가 아니에요."
        );
      }
      if (participantIds.size === 0) {
        throw new HttpsError("failed-precondition", "참여자 정보가 없습니다.");
      }
      if (room.writable === false) {
        throw new HttpsError(
          "failed-precondition",
          "지금은 안전도장을 찍을 수 없어요."
        );
      }

      const promiseStatus = asTrimmed(promise.status).toLowerCase();
      if (SAFETY_STAMP_TERMINAL_PROMISE_STATUSES.includes(promiseStatus)) {
        throw new HttpsError(
          "failed-precondition",
          "이미 종료된 약속이에요."
        );
      }

      // 활성 약속과 일치하는지 확인한다 (미러를 권한 판단에 쓰지는 않는다).
      const activePromiseRaw = room.activePromise;
      const activePromise = isRecord(activePromiseRaw)
        ? { ...activePromiseRaw }
        : null;
      if (activePromise == null || asTrimmed(activePromise.promiseId) !== promiseId) {
        throw new HttpsError(
          "failed-precondition",
          "현재 활성 약속과 일치하지 않습니다."
        );
      }

      // 도장 목록의 source of truth 는 약속 문서다 (방 미러가 아니다).
      const storedStamp = isRecord(promise.safetyStamp)
        ? { ...(promise.safetyStamp as Record<string, unknown>) }
        : {};
      // 약속이 수정돼 시각이 바뀌었다면 이전 도장은 이 약속의 것이 아니다.
      const carryOver = stampsMatchCurrentPromise(storedStamp, promise.dateTime);
      const safetyStamp = carryOver ? storedStamp : {};
      if (!carryOver) {
        logger.info("safety stamps reset: promise was rescheduled", {
          roomId,
          promiseId,
        });
      }
      const meetupStamped = effectiveMeetupStamps(safetyStamp);
      const goodbyeStamped = asIdSet(safetyStamp.goodbyeStampedUserIds);

      if (phase === "goodbye") {
        for (const participantId of participantIds) {
          if (!meetupStamped.has(participantId)) {
            throw new HttpsError(
              "failed-precondition",
              "만남 인증이 아직 완료되지 않았습니다."
            );
          }
        }
      }

      const target = phase === "goodbye" ? goodbyeStamped : meetupStamped;
      if (target.has(uid)) {
        // 같은 도장을 다시 보내도 카운터가 두 번 오르지 않는다.
        return {
          ok: true as const,
          alreadyStamped: true,
          phase,
          phaseCompleted: [...participantIds].every((id) => target.has(id)),
        };
      }
      target.add(uid);

      const nextSafetyStamp: Record<string, unknown> = {
        ...safetyStamp,
        meetupStampedUserIds: [...meetupStamped].sort(),
        goodbyeStampedUserIds: [...goodbyeStamped].sort(),
      };
      const currentDateTimeMs = promiseDateTimeMs(promise.dateTime);
      if (currentDateTimeMs != null) {
        nextSafetyStamp.stampedForDateTimeMs = currentDateTimeMs;
      }
      if (verification != null) {
        const recordKey =
          phase === "goodbye"
            ? "goodbyeVerificationByUserId"
            : "meetupVerificationByUserId";
        const existing = isRecord(nextSafetyStamp[recordKey])
          ? { ...(nextSafetyStamp[recordKey] as Record<string, unknown>) }
          : {};
        // 본인 키만 쓴다. 다른 참가자의 검증 기록은 건드리지 않는다.
        // blob 안의 verifierUserId 는 클라이언트가 채운 값이므로,
        // 귀속이 어긋나지 않도록 서버가 인증된 uid 로 덮어쓴다.
        existing[uid] = { ...verification, verifierUserId: uid };
        nextSafetyStamp[recordKey] = existing;
      }
      // legacy 배열은 meetupStampedUserIds 로 흡수됐으므로 남기지 않는다.
      delete nextSafetyStamp.stampedUserIds;

      const phaseCompleted = [...participantIds].every((id) => target.has(id));

      const mirror: Record<string, unknown> = {
        ...activePromise,
        participantIds: [...participantIds].sort(),
        safetyStamp: nextSafetyStamp,
      };

      const promisePatch: Record<string, unknown> = {
        participantIds: [...participantIds].sort(),
        safetyStamp: nextSafetyStamp,
        updatedAt: FieldValue.serverTimestamp(),
      };

      if (phase === "meetup" && phaseCompleted) {
        const completedStamp = {
          ...nextSafetyStamp,
          meetupCompletedAt: FieldValue.serverTimestamp(),
        };
        mirror.status = "in_progress";
        mirror.safetyStamp = completedStamp;
        promisePatch.safetyStamp = completedStamp;
        promisePatch.status = "in_progress";
        promisePatch.meetupCompletedAt = FieldValue.serverTimestamp();

        tx.set(inProgressMessageRef, {
          senderId: uid,
          text: "약속을 진행중입니다",
          type: "promise_in_progress",
          promiseId,
          dateTime: FieldValue.serverTimestamp(),
          place: activePromise.place ?? null,
          placeCategory: activePromise.placeCategory ?? null,
          status: "in_progress",
          readBy: [uid],
          createdAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        });
      } else if (phase === "goodbye" && phaseCompleted) {
        const completedStamp = {
          ...nextSafetyStamp,
          completedAt: FieldValue.serverTimestamp(),
        };
        mirror.status = "completed";
        mirror.safetyStamp = completedStamp;
        promisePatch.safetyStamp = completedStamp;
        promisePatch.status = "completed";
        promisePatch.completedAt = FieldValue.serverTimestamp();

        tx.set(completedMessageRef, {
          senderId: uid,
          text: "약속이 완료되었어요",
          type: "promise_completed",
          promiseId,
          dateTime: FieldValue.serverTimestamp(),
          place: activePromise.place ?? null,
          placeCategory: activePromise.placeCategory ?? null,
          status: "completed",
          readBy: [uid],
          createdAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        });
      }

      tx.update(promiseRef, promisePatch);

      const roomPatch: Record<string, unknown> = {
        activePromise: mirror,
        updatedAt: FieldValue.serverTimestamp(),
      };
      if (phase === "meetup" && phaseCompleted) {
        roomPatch.lastMessage = "약속을 진행중입니다";
        roomPatch.lastMessageAt = FieldValue.serverTimestamp();
      } else if (phase === "goodbye" && phaseCompleted) {
        roomPatch.lastMessage = "약속이 완료되었어요";
        roomPatch.lastMessageAt = FieldValue.serverTimestamp();
      }
      tx.update(roomRef, roomPatch);

      logger.info("safety stamp recorded", {
        roomId,
        promiseId,
        phase,
        phaseCompleted,
      });

      return {
        ok: true as const,
        alreadyStamped: false,
        phase,
        phaseCompleted,
      };
    });
  }
);

/** 헤어짐 도장을 찍지 않은 사유. 클라이언트가 고르는 값이다. */
// lib/features/chat/services/safety_stamp_follow_up_service.dart 의
// SafetyStampFollowUpReason 과 같은 값이어야 한다.
export const SAFETY_STAMP_FOLLOW_UP_REASONS = [
  "phone_off",
  "forgot_to_stamp",
  "other",
];

export function normalizeFollowUpReason(value: unknown): string | null {
  const text = asTrimmed(value);
  return SAFETY_STAMP_FOLLOW_UP_REASONS.includes(text) ? text : null;
}

/**
 * 헤어짐 안전도장 미완료 사유를 제출한다.
 *
 * 이 값도 safetyStamp 맵 안에 살기 때문에, 도장을 서버 권위로 옮긴 뒤에도
 * 클라이언트가 safetyStamp 를 직접 쓸 수 있으면 잠금이 뚫린다.
 * 따라서 사유 제출도 서버가 받아 본인 키에만 기록한다.
 */
export const submitSafetyStampFollowUp = onCall(
  withAppCheck(),
  async (request): Promise<{ ok: true }> => {
    const uid = asTrimmed(request.auth?.uid);
    if (uid.length === 0) {
      throw new HttpsError("unauthenticated", "로그인이 필요해요.");
    }

    const data = isRecord(request.data) ? request.data : {};
    const roomId = asTrimmed(data.roomId);
    const promiseId = asTrimmed(data.promiseId);
    const reasonCode = normalizeFollowUpReason(data.reasonCode);
    const reasonText =
      reasonCode === "other" ? asTrimmed(data.reasonText).slice(0, 500) : null;
    const notificationId = asTrimmed(data.notificationId);

    if (roomId.length === 0 || promiseId.length === 0 || reasonCode == null) {
      throw new HttpsError("invalid-argument", "요청 정보가 올바르지 않아요.");
    }

    const roomRef = db().collection("chat_rooms").doc(roomId);
    const promiseRef = roomRef.collection("promises").doc(promiseId);

    await db().runTransaction(async (tx) => {
      const [roomSnap, promiseSnap] = await Promise.all([
        tx.get(roomRef),
        tx.get(promiseRef),
      ]);
      if (!roomSnap.exists || !promiseSnap.exists) {
        throw new HttpsError("not-found", "약속 정보를 찾을 수 없어요.");
      }
      const room = roomSnap.data() ?? {};
      if (!asIdSet(room.participantIds).has(uid)) {
        throw new HttpsError(
          "permission-denied",
          "이 채팅방의 참여자가 아니에요."
        );
      }
      // 사유를 남기는 것은 그 약속의 당사자뿐이다. 6인 방에서 약속과 무관한
      // 참가자가 남의 약속 문서에 기록을 만들 수 있으면 안 된다.
      const promise = promiseSnap.data() ?? {};
      if (
        asTrimmed(promise.requestedBy) !== uid &&
        asTrimmed(promise.requestedTo) !== uid
      ) {
        throw new HttpsError(
          "permission-denied",
          "이 약속의 당사자가 아니에요."
        );
      }

      const entry = {
        status: "submitted",
        reasonCode,
        reasonText,
        respondedAt: FieldValue.serverTimestamp(),
        notificationId: notificationId.length > 0 ? notificationId : null,
      };

      // 본인 키에만 merge 한다. 다른 참가자의 응답은 건드리지 않는다.
      tx.set(
        promiseRef,
        {
          safetyStamp: { goodbyeFollowUpByUserId: { [uid]: entry } },
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );

      const activePromise = isRecord(room.activePromise)
        ? (room.activePromise as Record<string, unknown>)
        : null;
      if (activePromise != null && asTrimmed(activePromise.promiseId) === promiseId) {
        tx.set(
          roomRef,
          {
            activePromise: {
              safetyStamp: { goodbyeFollowUpByUserId: { [uid]: entry } },
            },
            updatedAt: FieldValue.serverTimestamp(),
          },
          { merge: true }
        );
      }

      if (notificationId.length > 0) {
        tx.set(
          db()
            .collection("users")
            .doc(uid)
            .collection("notifications")
            .doc(notificationId),
          { isRead: true, readAt: FieldValue.serverTimestamp() },
          { merge: true }
        );
      }
    });

    return { ok: true as const };
  }
);
