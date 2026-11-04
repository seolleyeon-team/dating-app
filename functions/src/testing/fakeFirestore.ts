/**
 * In-memory Firestore double for unit tests.
 *
 * Supports the subset the avatar admission/recovery code uses:
 * collection().doc().get/set/update/delete, where("field","=="|"in",v)
 * [.limit(n)].get(), runTransaction with tx.get/set/update, FieldValue.delete()
 * and FieldValue.serverTimestamp() sentinels, dotted-path updates, and
 * Timestamp values that survive reads (instanceof checks keep working).
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

/// FieldValue.arrayUnion(...) — modelled as a set-union with the stored array.
function arrayUnionElements(value: unknown): unknown[] | null {
  if (!(value instanceof FieldValue)) return null;
  const candidate = value as unknown as { constructor: { name: string }; elements?: unknown };
  if (candidate.constructor.name !== "ArrayUnionTransform" || !Array.isArray(candidate.elements)) return null;
  return candidate.elements;
}

function unionInto(existing: unknown, elements: unknown[]): unknown[] {
  const base = Array.isArray(existing) ? [...existing] : [];
  for (const element of elements) {
    if (!base.some((item) => JSON.stringify(item) === JSON.stringify(element))) base.push(element);
  }
  return base;
}

function materialize(value: unknown): unknown {
  if (isServerTimestampSentinel(value)) return Timestamp.now();
  if (value instanceof Timestamp) return value;
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

function deepClone<T>(value: T): T {
  if (value instanceof Timestamp || value instanceof FieldValue) return value;
  if (Array.isArray(value)) return value.map((entry) => deepClone(entry)) as unknown as T;
  if (isRecord(value)) {
    const out: Doc = {};
    for (const [key, entry] of Object.entries(value)) out[key] = deepClone(entry);
    return out as T;
  }
  return value;
}

/// update() semantics: a dotted key is a nested field path.
export function mergeInto(existing: Doc, update: Doc): Doc {
  const out: Doc = deepClone(existing);
  for (const [key, value] of Object.entries(update)) {
    if (key.includes(".")) {
      setDotted(out, key, value);
      continue;
    }
    if (isDeleteSentinel(value)) {
      delete out[key];
      continue;
    }
    const union = arrayUnionElements(value);
    if (union) {
      out[key] = unionInto(out[key], union);
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

/// set(..., {merge:true}) semantics: keys are field NAMES, never paths. A key
/// containing a dot becomes a literal top-level field and leaves the nested map
/// alone — this is what wrote "avatar.status" beside the real avatar map in
/// production while avatar.status itself stayed stale. Nested maps merge by
/// object structure instead.
export function mergeSetData(existing: Doc, data: Doc): Doc {
  const out: Doc = deepClone(existing);
  for (const [key, value] of Object.entries(data)) {
    if (isDeleteSentinel(value)) {
      delete out[key];
      continue;
    }
    const union = arrayUnionElements(value);
    if (union) {
      out[key] = unionInto(out[key], union);
      continue;
    }
    if (isRecord(value) && isRecord(out[key])) {
      out[key] = mergeSetData(out[key] as Doc, value);
      continue;
    }
    out[key] = materialize(value);
  }
  return out;
}

function clone(value: Doc): Doc {
  return deepClone(value);
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
          /// Subcollections: users/{uid}/deviceTokens, blindMeetings/{id}/publicProfiles …
          collection(sub: string) {
            return self.collection(`${path}/${sub}`);
          },
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
              options?.merge ? mergeSetData(existing, data) : (materialize(data) as Doc),
            );
          },
          async update(data: Doc) {
            self.writes.push({ op: "update", path });
            if (!self.db.has(path)) {
              throw new Error(`NOT_FOUND: ${path}`);
            }
            self.db.set(path, mergeInto(self.db.get(path) ?? {}, data));
          },
          async delete() {
            self.writes.push({ op: "delete", path });
            self.db.delete(path);
          },
        };
      },
      where(field: string, operator: string, value: unknown) {
        const matches = (data: Doc): boolean => {
          if (operator === "==") return data[field] === value;
          if (operator === "in") return Array.isArray(value) && value.includes(data[field]);
          throw new Error(`FakeFirestore: unsupported operator ${operator}`);
        };
        const query = (max: number | null) => ({
          limit(n: number) {
            return query(n);
          },
          async get() {
            let docs = Array.from(self.db.entries())
              .filter(([path]) => path.startsWith(`${name}/`))
              .filter(([, data]) => matches(data))
              .map(([path, data]) => ({
                id: path.slice(name.length + 1),
                data: () => clone(data),
                ref: self.collection(name).doc(path.slice(name.length + 1)),
              }));
            if (max !== null) docs = docs.slice(0, max);
            return { docs, empty: docs.length === 0, size: docs.length };
          },
        });
        return query(null);
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
