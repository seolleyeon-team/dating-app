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

/**
 * Department peers with only the fields the pair decision needs. A projection
 * still costs one read per peer but does not ship whole user documents.
 */
async function departmentPeers(
  firestore: Firestore,
  department: string,
  changedUid: string,
): Promise<Map<string, RecordData>> {
  const users = firestore.collection("users");
  const fields = [
    "onboarding.department",
    "department",
    "privacySettings.avoidSameDepartment",
  ];
  const [canonicalSnapshot, legacySnapshot] = await Promise.all([
    users.where("onboarding.department", "==", department).select(...fields).get(),
    users.where("department", "==", department).select(...fields).get(),
  ]);
  const peers = new Map<string, RecordData>();
  for (const snapshot of [canonicalSnapshot, legacySnapshot]) {
    for (const doc of snapshot.docs) {
      if (doc.id !== changedUid) peers.set(doc.id, doc.data() as RecordData);
    }
  }
  return peers;
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

export type DepartmentRecommendationReconcileSummary = {
  /** false: neither the department nor the preference changed; nothing read. */
  relevant: boolean;
  /** Department peers read (one projected read each). */
  peersRead: number;
  /** Pair transactions run (2 reads + 2 writes each). */
  pairsReconciled: number;
  /** Pairs proven to need no write and therefore not touched. */
  pairsSkipped: number;
};

/**
 * A pair needs no transaction when nothing could have been materialized for
 * it and nothing has to be: neither side asks for avoidance now, neither did
 * under the changed user's previous state, and no exclusion document exists.
 *
 * B-14: every department/preference change (including every sign-up, where
 * the department is set for the first time) used to run one transaction per
 * department peer — two reads and two deletes of documents that did not
 * exist. Pairs where avoidance is or was in play, and pairs that have a
 * stored exclusion, still go through the same transaction as before.
 */
export function departmentPairNeedsReconcile(params: {
  before: RecordData | null | undefined;
  after: RecordData | null | undefined;
  peer: RecordData | null | undefined;
  exclusionExists: boolean;
}): boolean {
  return (
    params.exclusionExists ||
    shouldExcludeSameDepartment(params.after, params.peer) ||
    shouldExcludeSameDepartment(params.before, params.peer)
  );
}

export async function reconcileDepartmentRecommendationPrivacy(
  firestore: Firestore,
  changedUid: string,
  before: RecordData | null | undefined,
  after: RecordData | null | undefined,
): Promise<DepartmentRecommendationReconcileSummary> {
  const summary: DepartmentRecommendationReconcileSummary = {
    relevant: false,
    peersRead: 0,
    pairsReconciled: 0,
    pairsSkipped: 0,
  };
  if (!departmentRecommendationPrivacyChanged(before, after)) return summary;

  const departments = departmentsToReconcile(before, after);
  if (departments.length === 0) return summary;
  summary.relevant = true;

  const peers = new Map<string, RecordData>();
  for (const department of departments) {
    for (const [uid, data] of await departmentPeers(
      firestore,
      department,
      changedUid,
    )) {
      peers.set(uid, data);
    }
  }
  summary.peersRead = peers.size;

  // Exclusions already stored for the changed user (ids only). A stored
  // exclusion whose peer is no longer a department peer is reconciled too.
  const existingSnapshot = await firestore
    .collection(DEPARTMENT_RECOMMENDATION_EXCLUSION_COLLECTION)
    .doc(changedUid)
    .collection("targets")
    .select()
    .get();
  const existing = new Set(existingSnapshot.docs.map((doc) => doc.id));

  const targets = [...new Set([...peers.keys(), ...existing])]
    .sort()
    .filter((targetUid) => {
      const needed = departmentPairNeedsReconcile({
        before,
        after,
        peer: peers.get(targetUid) ?? null,
        exclusionExists: existing.has(targetUid),
      });
      if (!needed) summary.pairsSkipped += 1;
      return needed;
    });

  const concurrency = 20;
  for (let offset = 0; offset < targets.length; offset += concurrency) {
    const chunk = targets.slice(offset, offset + concurrency);
    await Promise.all(
      chunk.map((targetUid) =>
        reconcileDepartmentPair(firestore, changedUid, targetUid),
      ),
    );
    summary.pairsReconciled += chunk.length;
  }
  return summary;
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
    await reconcileDepartmentRecommendationPrivacy(
      firestore,
      changedUid,
      before,
      after,
    );
  });
}
