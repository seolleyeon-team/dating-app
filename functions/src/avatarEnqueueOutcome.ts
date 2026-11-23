/**
 * AUD-09 — recording "the generation task was enqueued" without overwriting
 * the worker.
 *
 * Both admission paths (source-set admission and retry) used to finish with an
 * unconditional
 *
 *   jobRef.set({ status: "queued", errorCode: delete, ... }, { merge: true })
 *
 * after the Cloud Task was created. The task can be delivered before that
 * write lands: a warm worker that refuses the job at once (for example the
 * lifetime candidate cap) writes its terminal state first, and the late write
 * then put the job back to `queued` with its error code erased — and with no
 * task left to move it again, a job that stays queued forever.
 *
 * The write is now a transaction that changes `status` / `errorCode` /
 * `retryable` only while the job is still in a state Functions itself wrote
 * (waiting for dispatch, or a previous dispatch failure). Once the worker owns
 * the job, only the queue bookkeeping fields are recorded.
 */
import {
  FieldValue,
  type DocumentReference,
  type Firestore,
} from "firebase-admin/firestore";

/** Error codes Functions writes when it could not create the task. */
export const AVATAR_DISPATCH_FAILURE_CODES: ReadonlySet<string> = new Set([
  "avatar_queue_dispatch_failed",
  "avatar_queue_enqueue_failed",
]);

/** Job states written by Functions before the worker has seen the job. */
const WAITING_FOR_DISPATCH_STATUSES: ReadonlySet<string> = new Set([
  "pending",
  "queued",
]);

export type AvatarEnqueueOutcome = "queued" | "worker_owned" | "missing";

/**
 * True while the job document is still in a state only Functions writes:
 * waiting for dispatch, or marked with a dispatch failure of its own.
 */
export function isDispatchOwnedAvatarJobState(
  data: Record<string, unknown> | null | undefined,
): boolean {
  if (!data) return false;
  const status = typeof data.status === "string" ? data.status : "";
  if (WAITING_FOR_DISPATCH_STATUSES.has(status)) return true;
  return (
    status === "retryable_failed" &&
    typeof data.errorCode === "string" &&
    AVATAR_DISPATCH_FAILURE_CODES.has(data.errorCode)
  );
}

export async function recordAvatarEnqueueSuccess(
  firestore: Firestore,
  jobRef: DocumentReference,
  queue: { queueMode: unknown; queueStatus: unknown },
  options: { stampQueuedAt?: boolean } = {},
): Promise<AvatarEnqueueOutcome> {
  return firestore.runTransaction(async (transaction) => {
    const snapshot = await transaction.get(jobRef);
    // The admission transaction always creates the job first. A missing
    // document is never created from here (the old merge-set would have).
    if (!snapshot.exists) return "missing";

    const bookkeeping = {
      queueMode: queue.queueMode,
      queueStatus: queue.queueStatus,
      queueUpdatedAt: FieldValue.serverTimestamp(),
    };
    const current = (snapshot.data() ?? {}) as Record<string, unknown>;
    if (!isDispatchOwnedAvatarJobState(current)) {
      // The worker already moved the job (running, provider in flight, a
      // terminal state): its status, error code and timestamps stand.
      transaction.set(jobRef, bookkeeping, { merge: true });
      return "worker_owned";
    }
    transaction.set(
      jobRef,
      {
        ...bookkeeping,
        status: "queued",
        errorCode: FieldValue.delete(),
        retryable: FieldValue.delete(),
        ...(options.stampQueuedAt
          ? { queuedAt: FieldValue.serverTimestamp() }
          : {}),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true },
    );
    return "queued";
  });
}
