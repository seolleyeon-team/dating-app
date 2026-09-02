import {
  FieldValue,
  type Firestore,
} from "firebase-admin/firestore";
import { onDocumentWritten } from "firebase-functions/v2/firestore";

import { buildRecommendationExclusionPairId } from "./kakaoFriendRecommendationPrivacy";

export const DEPARTMENT_RECOMMENDATION_EXCLUSION_COLLECTION =
  "departmentRecommendationExclusions";

type RecordData = Record<string, unknown>;

function isRecord(value: unknown): value is RecordData {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function readMap(value: unknown): RecordData {
  return isRecord(value) ? value : {};
}

/** Returns the stored department value without exposing any other user data. */
export function normalizeDepartment(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

/** Canonical department field with compatibility for old flattened user docs. */
export function departmentOfUser(
  data: RecordData | null | undefined,
): string | null {
  const onboarding = readMap(data?.onboarding);
  return (
    normalizeDepartment(onboarding.department) ??
    normalizeDepartment(data?.department)
  );
}

export function isAvoidSameDepartmentEnabled(
  data: RecordData | null | undefined,
): boolean {
  return readMap(data?.privacySettings).avoidSameDepartment === true;
}

/**
 * Same-department avoidance is bilateral: either person's preference hides the
 * pair from both recommendation directions.
 */
export function shouldExcludeSameDepartment(
  userA: RecordData | null | undefined,
  userB: RecordData | null | undefined,
): boolean {
  const departmentA = departmentOfUser(userA);
  const departmentB = departmentOfUser(userB);
  if (!departmentA || !departmentB || departmentA !== departmentB) return false;
  return (
    isAvoidSameDepartmentEnabled(userA) ||
    isAvoidSameDepartmentEnabled(userB)
  );
}

export function departmentRecommendationPrivacyChanged(
  before: RecordData | null | undefined,
  after: RecordData | null | undefined,
): boolean {
  return (
    departmentOfUser(before) !== departmentOfUser(after) ||
    isAvoidSameDepartmentEnabled(before) !== isAvoidSameDepartmentEnabled(after)
  );
}

export function departmentsToReconcile(
  before: RecordData | null | undefined,
  after: RecordData | null | undefined,
): string[] {
  return [departmentOfUser(before), departmentOfUser(after)].filter(
    (value, index, values): value is string =>
      value !== null && values.indexOf(value) === index,
  );
}

export function buildDepartmentRecommendationExclusionPayload(
  userA: string,
  userB: string,
): RecordData {
  return {
    pairId: buildRecommendationExclusionPairId(userA, userB),
    userIds: [userA, userB].sort(),
    source: "same_department",
    reason: "same_department_avoidance",
    active: true,
    updatedAt: FieldValue.serverTimestamp(),
  };
}

function departmentRecommendationExclusionRef(
  firestore: Firestore,
  ownerUid: string,
  targetUid: string,
) {
  return firestore
    .collection(DEPARTMENT_RECOMMENDATION_EXCLUSION_COLLECTION)
    .doc(ownerUid)
    .collection("targets")
    .doc(targetUid);
}

async function userIdsWithDepartment(
  firestore: Firestore,
  department: string,
  changedUid: string,
): Promise<string[]> {
  const users = firestore.collection("users");
  const [canonicalSnapshot, legacySnapshot] = await Promise.all([
    users.where("onboarding.department", "==", department).get(),
    users.where("department", "==", department).get(),
  ]);
  const userIds = new Set<string>();
  for (const snapshot of [canonicalSnapshot, legacySnapshot]) {
    for (const doc of snapshot.docs) {
      if (doc.id !== changedUid) userIds.add(doc.id);
    }
  }
  return [...userIds].sort();
}

async function reconcileDepartmentPair(
  firestore: Firestore,
  userA: string,
  userB: string,
): Promise<boolean> {
  if (!userA || !userB || userA === userB) return false;

  return firestore.runTransaction(async (transaction) => {
    const userARef = firestore.collection("users").doc(userA);
    const userBRef = firestore.collection("users").doc(userB);
    const [userASnapshot, userBSnapshot] = await transaction.getAll(
      userARef,
      userBRef,
    );
    const userAData = userASnapshot.exists
      ? (userASnapshot.data() as RecordData)
      : null;
    const userBData = userBSnapshot.exists
      ? (userBSnapshot.data() as RecordData)
      : null;
    const userATargetRef = departmentRecommendationExclusionRef(
      firestore,
      userA,
      userB,
    );
    const userBTargetRef = departmentRecommendationExclusionRef(
      firestore,
      userB,
      userA,
    );

    if (!shouldExcludeSameDepartment(userAData, userBData)) {
      transaction.delete(userATargetRef);
      transaction.delete(userBTargetRef);
      return false;
    }

    const payload = buildDepartmentRecommendationExclusionPayload(
      userA,
      userB,
    );
    // Both directions are written in one transaction so a preference change
    // cannot leave only one side protected from the recommendation feed.
    transaction.set(userATargetRef, payload, { merge: true });
    transaction.set(userBTargetRef, payload, { merge: true });
    return true;
  });
}

/**
 * Materializes only pair IDs, never departments or preference values, into a
 * server-owned collection. The app can then remove stale model ranks without
 * reading another user's private users/{uid} document.
 */
export function createDepartmentRecommendationPrivacyTrigger(
  firestore: Firestore,
) {
  return onDocumentWritten("users/{uid}", async (event) => {
    const changedUid = String(event.params.uid ?? "").trim();
    if (!changedUid) return;

    const before = event.data?.before?.exists
      ? (event.data.before.data() as RecordData)
      : null;
    const after = event.data?.after?.exists
      ? (event.data.after.data() as RecordData)
      : null;
    if (!departmentRecommendationPrivacyChanged(before, after)) return;

    const departments = departmentsToReconcile(before, after);
    if (departments.length === 0) return;

    const targetUids = new Set<string>();
    for (const department of departments) {
      for (const uid of await userIdsWithDepartment(
        firestore,
        department,
        changedUid,
      )) {
        targetUids.add(uid);
      }
    }

    const targets = [...targetUids].sort();
    const concurrency = 20;
    for (let offset = 0; offset < targets.length; offset += concurrency) {
      const chunk = targets.slice(offset, offset + concurrency);
      await Promise.all(
        chunk.map((targetUid) =>
          reconcileDepartmentPair(firestore, changedUid, targetUid),
        ),
      );
    }
  });
}
