/**
 * In-memory Firestore double for unit tests.
 *
 * Supports the subset the avatar admission/recovery code uses:
 * collection().doc().get/set/update, where("field","==",v).get(),
 * runTransaction with tx.get/set/update, FieldValue.delete() and
 * FieldValue.serverTimestamp() sentinels, and dotted-path updates.
 *
 * Test-only. Not bundled into any deployed function.
 */
import { FieldValue, Timestamp } from "firebase-admin/firestore";

export type Doc = Record<string, unknown>;
export type Db = Map<string, Doc>;

function isRecord(value: unknown): value is Doc {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const DELETE_SENTINEL = FieldValue.delete();
const SERVER_TIMESTAMP_SENTINEL = FieldValue.serverTimestamp();

function isDeleteSentinel(value: unknown): boolean {
  return value instanceof FieldValue && DELETE_SENTINEL.isEqual(value);
}

function isServerTimestampSentinel(value: unknown): boolean {
  return value instanceof FieldValue && SERVER_TIMESTAMP_SENTINEL.isEqual(value);
}

function materialize(value: unknown): unknown {
  if (isServerTimestampSentinel(value)) return Timestamp.now();
  if (Array.isArray(value)) return value.map(materialize);
  if (isRecord(value)) {
    const out: Doc = {};
    for (const [key, entry] of Object.entries(value)) {
      if (isDeleteSentinel(entry)) continue;
      out[key] = materialize(entry);
    }
    return out;
  }
  return value;
}

function setDotted(target: Doc, path: string, value: unknown): void {
  const segments = path.split(".");
  let cursor: Doc = target;
  for (const segment of segments.slice(0, -1)) {
    const next = cursor[segment];
    if (!isRecord(next)) cursor[segment] = {};
    cursor = cursor[segment] as Doc;
  }
  const last = segments[segments.length - 1];
  if (isDeleteSentinel(value)) {
    delete cursor[last];
  } else {
    cursor[last] = materialize(value);
  }
}

export function mergeInto(existing: Doc, update: Doc): Doc {
  const out: Doc = JSON.parse(JSON.stringify(existing));
  for (const [key, value] of Object.entries(update)) {
    if (key.includes(".")) {
      setDotted(out, key, value);
      continue;
    }
    if (isDeleteSentinel(value)) {
      delete out[key];
      continue;
    }
    if (isRecord(value) && isRecord(out[key])) {
      out[key] = mergeInto(out[key] as Doc, value);
      continue;
    }
    out[key] = materialize(value);
  }
  return out;
}

function clone(value: Doc): Doc {
  return JSON.parse(JSON.stringify(value));
}

export class FakeFirestore {
  readonly writes: Array<{ op: string; path: string }> = [];
  // Real Firestore serializes conflicting transactions via optimistic retry:
  // the loser re-runs and observes the winner's commit. Model that outcome by
  // running transactions strictly one after another.
  private chain: Promise<unknown> = Promise.resolve();

  constructor(readonly db: Db) {}

  collection(name: string) {
    const self = this;
    return {
      doc(id: string) {
        const path = `${name}/${id}`;
        return {
          path,
          async get() {
            const data = self.db.get(path);
            return {
              exists: data !== undefined,
              data: () => (data ? clone(data) : undefined),
              get: (field: string) => (data ? data[field] : undefined),
            };
          },
          async set(data: Doc, options?: { merge?: boolean }) {
            self.writes.push({ op: "set", path });
            const existing = self.db.get(path) ?? {};
            self.db.set(
              path,
              options?.merge ? mergeInto(existing, data) : (materialize(data) as Doc),
            );
          },
          async update(data: Doc) {
            self.writes.push({ op: "update", path });
            if (!self.db.has(path)) {
              throw new Error(`NOT_FOUND: ${path}`);
            }
            self.db.set(path, mergeInto(self.db.get(path) ?? {}, data));
          },
        };
      },
      where(field: string, operator: string, value: unknown) {
        return {
          async get() {
            const docs = Array.from(self.db.entries())
              .filter(([path]) => path.startsWith(`${name}/`))
              .filter(([, data]) => operator === "==" && data[field] === value)
              .map(([path, data]) => ({
                id: path.slice(name.length + 1),
                data: () => clone(data),
                ref: self.collection(name).doc(path.slice(name.length + 1)),
              }));
            return { docs, empty: docs.length === 0 };
          },
        };
      },
    };
  }

  async runTransaction<T>(
    fn: (tx: {
      get(ref: { get(): Promise<unknown> }): Promise<unknown>;
      set(ref: { set(data: Doc, options?: { merge?: boolean }): Promise<unknown> }, data: Doc, options?: { merge?: boolean }): void;
      update(ref: { update(data: Doc): Promise<unknown> }, data: Doc): void;
    }) => Promise<T>,
  ): Promise<T> {
    const run = async (): Promise<T> => {
      const pending: Array<() => Promise<unknown>> = [];
      const result = await fn({
        get: (ref) => ref.get(),
        set: (ref, data, options) => {
          pending.push(() => ref.set(data, options));
        },
        update: (ref, data) => {
          pending.push(() => ref.update(data));
        },
      });
      for (const write of pending) await write();
      return result;
    };
    const next = this.chain.then(run, run);
    this.chain = next.catch(() => undefined);
    return next;
  }
}
