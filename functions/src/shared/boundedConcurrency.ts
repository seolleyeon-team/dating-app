/**
 * Runs `worker` over `items` with at most `limit` calls in flight.
 *
 * Scheduled jobs used to await one item at a time, which ties the run time to
 * the item count; an unbounded Promise.all instead opens one Firestore
 * transaction per item at once. This keeps a fixed number in flight.
 *
 * A rejected worker rejects the whole call (remaining items are not started),
 * so callers that want per-item isolation catch inside `worker`.
 * `shouldStop` is polled before each item starts: returning true stops
 * scheduling new items and the call resolves with the number started.
 */
export async function runWithConcurrency<T>(
  items: readonly T[],
  limit: number,
  worker: (item: T, index: number) => Promise<void>,
  shouldStop: () => boolean = () => false
): Promise<number> {
  const width = Math.max(1, Math.min(Math.floor(limit) || 1, items.length));
  let next = 0;
  let started = 0;
  const lane = async (): Promise<void> => {
    for (;;) {
      if (shouldStop()) return;
      const index = next;
      if (index >= items.length) return;
      next += 1;
      started += 1;
      await worker(items[index], index);
    }
  };
  await Promise.all(Array.from({ length: width }, () => lane()));
  return started;
}
