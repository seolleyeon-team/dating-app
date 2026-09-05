import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it } from "node:test";

import { FieldValue, Timestamp, type Firestore } from "firebase-admin/firestore";
import { HttpsError } from "firebase-functions/v2/https";

import { respondTeamInviteCore } from "./eventTeamMembership";
import {
  EVENT_TEAM_CAPACITY,
  FRIEND_INVITE_HOST,
  FRIEND_INVITE_LEGACY_HOSTS,
  FRIEND_INVITE_PATH,
  FRIEND_INVITE_TARGET,
  INVITE_PURPOSE_FRIEND,
  INVITE_PURPOSE_TEAM,
  TEAM_INVITE_PATH,
  TEAM_INVITE_TARGET,
  acceptFriendInviteByToken,
  buildFriendInviteExecutionParams,
  buildFriendInviteUrl,
  buildFriendPairId,
  buildTeamInviteUrl,
  createFriendInviteRecord,
  createTeamInviteRecord,
  generateFriendInviteToken,
  hashInviteToken,
  isFriendInviteTokenShape,
  previewInviteByToken,
  readFriendUserEligibility,
  readInvitePurpose,
  redeemTeamInviteByToken,
  type FriendInviteParticipant,
} from "./friendInvites";

// =============================================================================
// Minimal in-memory Firestore with optimistic transactions.
//
// Only the surface friendInvites.ts touches is implemented:
//   collection().doc().get()/set(), collection().where().limit().get(),
//   runTransaction() with get()/set() and read-set conflict detection.
// A commit barrier lets tests interleave two transactions the way two
// concurrent callable invocations would.
// =============================================================================

type DocData = Record<string, unknown>;

/** Deep copy of plain data that keeps Firestore value classes (Timestamp) intact. */
function cloneData<T>(value: T): T {
  if (Array.isArray(value)) return value.map((v) => cloneData(v)) as unknown as T;
  if (value !== null && typeof value === "object") {
    const proto = Object.getPrototypeOf(value);
    if (proto === Object.prototype || proto === null) {
      const out: DocData = {};
      for (const [k, v] of Object.entries(value as DocData)) out[k] = cloneData(v);
      return out as T;
    }
  }
  return value;
}

class FakeSnapshot {
  constructor(
    readonly ref: FakeDocRef,
    private readonly value: DocData | undefined,
  ) {}
  get id(): string {
    return this.ref.id;
  }
  get exists(): boolean {
    return this.value !== undefined;
  }
  data(): DocData | undefined {
    return this.value === undefined ? undefined : cloneData(this.value);
  }
}

class FakeDocRef {
  constructor(
    readonly db: FakeDb,
    readonly path: string,
  ) {}
  get id(): string {
    const parts = this.path.split("/");
    return parts[parts.length - 1] ?? "";
  }
  collection(name: string): FakeCollectionRef {
    return new FakeCollectionRef(this.db, `${this.path}/${name}`);
  }
  async get(): Promise<FakeSnapshot> {
    return new FakeSnapshot(this, this.db.read(this.path));
  }
  async set(data: DocData, options?: { merge?: boolean }): Promise<void> {
    this.db.apply(this.path, data, options?.merge === true);
  }
}

class FakeQuery {
  constructor(
    protected readonly queryDb: FakeDb,
    protected readonly queryPath: string,
    private readonly filters: Array<[string, unknown]>,
    private readonly max: number | null,
  ) {}
  where(field: string, op: string, value: unknown): FakeQuery {
    assert.equal(op, "==");
    return new FakeQuery(this.queryDb, this.queryPath, [...this.filters, [field, value]], this.max);
  }
  limit(n: number): FakeQuery {
    return new FakeQuery(this.queryDb, this.queryPath, this.filters, n);
  }
  async get(): Promise<{ empty: boolean; docs: FakeSnapshot[] }> {
    const docs: FakeSnapshot[] = [];
    for (const [path, data] of this.queryDb.store) {
      const parent = path.slice(0, path.lastIndexOf("/"));
      if (parent !== this.queryPath) continue;
      if (this.filters.every(([f, v]) => data[f] === v)) {
        docs.push(new FakeSnapshot(new FakeDocRef(this.queryDb, path), data));
      }
      if (this.max !== null && docs.length >= this.max) break;
    }
    return { empty: docs.length === 0, docs };
  }
}

class FakeCollectionRef extends FakeQuery {
  constructor(db: FakeDb, path: string) {
    super(db, path, [], null);
  }
  doc(id?: string): FakeDocRef {
    const docId = id ?? `auto_${++this.queryDb.autoId}`;
    return new FakeDocRef(this.queryDb, `${this.queryPath}/${docId}`);
  }
}

class ConflictError extends Error {}

class FakeTransaction {
  readonly reads = new Map<string, number>();
  readonly writes: Array<{ path: string; data: DocData; merge: boolean }> = [];
  constructor(private readonly db: FakeDb) {}
  async get(ref: FakeDocRef): Promise<FakeSnapshot> {
    if (this.writes.length > 0) {
      throw new Error("Firestore transactions require all reads before writes");
    }
    this.reads.set(ref.path, this.db.versions.get(ref.path) ?? 0);
    return new FakeSnapshot(ref, this.db.read(ref.path));
  }
  set(ref: FakeDocRef, data: DocData, options?: { merge?: boolean }): void {
    this.writes.push({ path: ref.path, data, merge: options?.merge === true });
  }
  update(ref: FakeDocRef, data: DocData): void {
    if (!this.db.store.has(ref.path)) {
      throw new Error(`update() on missing document ${ref.path}`);
    }
    this.writes.push({ path: ref.path, data, merge: true });
  }
}

class FakeDb {
  readonly store = new Map<string, DocData>();
  readonly versions = new Map<string, number>();
  autoId = 0;
  commitCount = 0;
  retryCount = 0;
  beforeCommit: (() => Promise<void>) | null = null;

  collection(name: string): FakeCollectionRef {
    return new FakeCollectionRef(this, name);
  }

  read(path: string): DocData | undefined {
    const value = this.store.get(path);
    return value === undefined ? undefined : cloneData(value);
  }

  apply(path: string, data: DocData, merge: boolean): void {
    const current = merge ? (this.store.get(path) ?? {}) : {};
    const next: DocData = { ...current };
    for (const [key, raw] of Object.entries(data)) {
      next[key] = this.resolveFieldValue(raw, current[key]);
    }
    this.store.set(path, next);
    this.versions.set(path, (this.versions.get(path) ?? 0) + 1);
  }

  private resolveFieldValue(raw: unknown, previous: unknown): unknown {
    if (raw instanceof FieldValue) {
      if (raw.isEqual(FieldValue.serverTimestamp())) return Timestamp.now();
      if (raw.isEqual(FieldValue.increment(1))) {
        return (typeof previous === "number" ? previous : 0) + 1;
      }
      throw new Error("unsupported FieldValue sentinel in fake");
    }
    return raw;
  }

  async runTransaction<T>(fn: (tx: FakeTransaction) => Promise<T>): Promise<T> {
    for (let attempt = 0; attempt < 10; attempt++) {
      const tx = new FakeTransaction(this);
      const result = await fn(tx);
      if (this.beforeCommit) await this.beforeCommit();
      try {
        this.commit(tx);
        return result;
      } catch (error) {
        if (!(error instanceof ConflictError)) throw error;
        this.retryCount++;
      }
    }
    throw new Error("transaction retry budget exhausted");
  }

  private commit(tx: FakeTransaction): void {
    for (const [path, version] of tx.reads) {
      if ((this.versions.get(path) ?? 0) !== version) {
        throw new ConflictError(`conflict on ${path}`);
      }
    }
    for (const write of tx.writes) this.apply(write.path, write.data, write.merge);
    this.commitCount++;
  }

  asFirestore(): Firestore {
    return this as unknown as Firestore;
  }
}

/** Resolves once `count` participants have arrived; immediate afterwards. */
function barrier(count: number): () => Promise<void> {
  let arrived = 0;
  const waiters: Array<() => void> = [];
  return () =>
    new Promise<void>((resolveWait) => {
      arrived++;
      if (arrived >= count) {
        waiters.forEach((w) => w());
        waiters.length = 0;
        resolveWait();
      } else {
        waiters.push(resolveWait);
      }
    });
}

// =============================================================================
// Fixtures
// =============================================================================

const NOW = new Date("2026-09-03T09:00:00.000Z");

function participant(userId: string, nickname: string): FriendInviteParticipant {
  return {
    userId,
    email: `${userId}@yonsei.ac.kr`,
    profileSnapshot: { uid: userId, nickname },
  };
}

const ALICE = participant("uid_alice", "앨리스");
const BOB = participant("uid_bob", "밥");
const CAROL = participant("uid_carol", "캐롤");

function seedUser(db: FakeDb, user: FriendInviteParticipant, extra: DocData = {}): void {
  db.apply(
    `users/${user.userId}`,
    {
      studentEmail: user.email,
      isStudentVerified: true,
      onboarding: { nickname: user.profileSnapshot.nickname },
      ...extra,
    },
    false,
  );
}

async function issueInvite(
  db: FakeDb,
  inviter: FriendInviteParticipant,
  now: Date = NOW,
): Promise<string> {
  const created = await createFriendInviteRecord({
    db: db.asFirestore(),
    inviter,
    now,
  });
  return created.inviteToken;
}

function accept(
  db: FakeDb,
  token: string | null | undefined,
  acceptor: FriendInviteParticipant,
  now: Date = NOW,
) {
  return acceptFriendInviteByToken({
    db: db.asFirestore(),
    rawToken: token,
    acceptor,
    now: () => now,
  });
}

function friendsCount(db: FakeDb, userId: string): number {
  return (db.store.get(`users/${userId}`)?.friendsCount as number | undefined) ?? 0;
}

function edge(db: FakeDb, from: string, to: string): DocData | undefined {
  return db.store.get(`users/${from}/friends/${to}`);
}

function friendshipDocs(db: FakeDb): string[] {
  return [...db.store.keys()].filter((p) => p.startsWith("friendships/"));
}

function inviteDoc(db: FakeDb, token: string): DocData | undefined {
  const hash = hashInviteToken(token);
  for (const [path, data] of db.store) {
    if (path.startsWith("friendInvites/") && data.tokenHash === hash) return data;
  }
  return undefined;
}

function freshDb(): FakeDb {
  const db = new FakeDb();
  seedUser(db, ALICE);
  seedUser(db, BOB);
  seedUser(db, CAROL);
  return db;
}

/** Asserts A↔B mutual state: both edges, one friendship, counts as expected. */
function assertMutualFriendship(
  db: FakeDb,
  a: FriendInviteParticipant,
  b: FriendInviteParticipant,
  counts: { a: number; b: number },
): void {
  const pairId = buildFriendPairId(a.userId, b.userId);
  assert.deepEqual(friendshipDocs(db), [`friendships/${pairId}`]);
  const friendship = db.store.get(`friendships/${pairId}`);
  assert.deepEqual(friendship?.userIds, [a.userId, b.userId].sort());
  assert.equal(friendship?.status, "active");
  assert.equal(edge(db, a.userId, b.userId)?.friendUserId, b.userId);
  assert.equal(edge(db, b.userId, a.userId)?.friendUserId, a.userId);
  assert.equal(edge(db, a.userId, b.userId)?.pairId, pairId);
  assert.equal(edge(db, b.userId, a.userId)?.pairId, pairId);
  assert.equal(friendsCount(db, a.userId), counts.a);
  assert.equal(friendsCount(db, b.userId), counts.b);
}

// =============================================================================
// Link / token contract
// =============================================================================

describe("friend invite link contract", () => {
  it("issues a 32-byte opaque token, never a uid or sequential id", () => {
    const token = generateFriendInviteToken();
    assert.ok(isFriendInviteTokenShape(token));
    assert.notEqual(generateFriendInviteToken(), token);
  });

  it("invite URL targets the production custom domain with the token only", () => {
    const token = generateFriendInviteToken();
    const url = new URL(buildFriendInviteUrl(token));
    assert.equal(url.host, FRIEND_INVITE_HOST);
    assert.equal(url.host, "seolleyeon.com");
    assert.equal(url.pathname, FRIEND_INVITE_PATH);
    assert.equal(url.searchParams.get("token"), token);
    assert.deepEqual([...url.searchParams.keys()], ["token"]);
    assert.ok(FRIEND_INVITE_LEGACY_HOSTS.includes("seolleyeon-final.web.app"));
  });

  it("Kakao execution params carry the discriminator and the token", () => {
    const token = generateFriendInviteToken();
    assert.deepEqual(buildFriendInviteExecutionParams(token), {
      target: FRIEND_INVITE_TARGET,
      token,
    });
    assert.equal(FRIEND_INVITE_TARGET, "friend_invite");
  });

  it("rejects tampered token shapes before any Firestore access", () => {
    const token = generateFriendInviteToken();
    assert.equal(isFriendInviteTokenShape(token.slice(0, 63)), false);
    assert.equal(isFriendInviteTokenShape(token + "0"), false);
    assert.equal(isFriendInviteTokenShape(token.toUpperCase()), false);
    assert.equal(isFriendInviteTokenShape("uid_alice"), false);
    assert.equal(isFriendInviteTokenShape(""), false);
  });

  it("stored invite only holds the token hash and the inviter resolved server-side", async () => {
    const db = freshDb();
    const created = await createFriendInviteRecord({
      db: db.asFirestore(),
      inviter: ALICE,
      now: NOW,
    });
    const stored = inviteDoc(db, created.inviteToken);
    assert.ok(stored);
    assert.equal(stored.inviterUserId, ALICE.userId);
    assert.equal(stored.status, "pending");
    assert.equal(stored.tokenHash, hashInviteToken(created.inviteToken));
    assert.equal(JSON.stringify(stored).includes(created.inviteToken), false);
    assert.equal(created.inviteUrl, buildFriendInviteUrl(created.inviteToken));
    assert.deepEqual(created.executionParams, {
      target: "friend_invite",
      token: created.inviteToken,
    });
    assert.equal(
      new Date(created.expiresAt).getTime(),
      NOW.getTime() + 7 * 24 * 60 * 60 * 1000,
    );
  });
});

describe("friend user eligibility", () => {
  it("requires a live, student-verified Yonsei member", () => {
    assert.equal(readFriendUserEligibility(null), "missing");
    assert.equal(
      readFriendUserEligibility({ studentEmail: "a@yonsei.ac.kr", isStudentVerified: true }),
      "ok",
    );
    assert.equal(
      readFriendUserEligibility({
        studentEmail: "a@yonsei.ac.kr",
        isStudentVerified: true,
        isWithdrawn: true,
      }),
      "withdrawn",
    );
    assert.equal(
      readFriendUserEligibility({
        studentEmail: "a@yonsei.ac.kr",
        isStudentVerified: true,
        loginDisabled: true,
      }),
      "withdrawn",
    );
    assert.equal(
      readFriendUserEligibility({ studentEmail: "a@gmail.com", isStudentVerified: true }),
      "unverified",
    );
    assert.equal(
      readFriendUserEligibility({ studentEmail: "a@yonsei.ac.kr", isStudentVerified: false }),
      "unverified",
    );
  });
});

// =============================================================================
// Acceptance transaction
// =============================================================================

describe("acceptFriendInviteByToken", () => {
  it("valid invite creates one canonical friendship with both edges and +1 each", async () => {
    const db = freshDb();
    const token = await issueInvite(db, ALICE);

    const result = await accept(db, token, BOB);

    assert.equal(result.status, "accepted");
    assert.equal(result.otherUserId, ALICE.userId);
    assert.equal(result.otherUserName, "앨리스");
    assert.equal(result.pairId, buildFriendPairId(ALICE.userId, BOB.userId));
    assertMutualFriendship(db, ALICE, BOB, { a: 1, b: 1 });

    const invite = inviteDoc(db, token);
    assert.equal(invite?.status, "accepted");
    assert.equal(invite?.acceptedByUserId, BOB.userId);
    assert.equal(invite?.friendshipPairId, result.pairId);
    assert.equal(
      (edge(db, ALICE.userId, BOB.userId)?.friendProfileSnapshot as DocData).nickname,
      "밥",
    );
    assert.equal(
      (edge(db, BOB.userId, ALICE.userId)?.friendProfileSnapshot as DocData).nickname,
      "앨리스",
    );
  });

  it("self invite is denied without touching the graph", async () => {
    const db = freshDb();
    const token = await issueInvite(db, ALICE);

    const result = await accept(db, token, ALICE);

    assert.equal(result.status, "self_invite");
    assert.deepEqual(friendshipDocs(db), []);
    assert.equal(friendsCount(db, ALICE.userId), 0);
    assert.equal(inviteDoc(db, token)?.status, "pending");
  });

  it("expired invite is denied and marked expired", async () => {
    const db = freshDb();
    const token = await issueInvite(db, ALICE, NOW);
    const later = new Date(NOW.getTime() + 8 * 24 * 60 * 60 * 1000);

    const result = await accept(db, token, BOB, later);

    assert.equal(result.status, "expired");
    assert.deepEqual(friendshipDocs(db), []);
    assert.equal(inviteDoc(db, token)?.status, "expired");
    assert.equal(friendsCount(db, ALICE.userId), 0);
    assert.equal(friendsCount(db, BOB.userId), 0);
  });

  it("unknown, tampered, and empty tokens are invalid", async () => {
    const db = freshDb();
    const token = await issueInvite(db, ALICE);
    const flipped = (token[0] === "0" ? "1" : "0") + token.slice(1);

    for (const candidate of [flipped, token.slice(0, 40), "", null, undefined, "uid_alice"]) {
      const result = await accept(db, candidate, BOB);
      assert.equal(result.status, "invalid", `token=${String(candidate)}`);
    }
    assert.deepEqual(friendshipDocs(db), []);
    assert.equal(inviteDoc(db, token)?.status, "pending");
  });

  it("already friends → idempotent success, no second friendship, no count drift", async () => {
    const db = freshDb();
    const first = await issueInvite(db, ALICE);
    assert.equal((await accept(db, first, BOB)).status, "accepted");

    const second = await issueInvite(db, ALICE);
    const result = await accept(db, second, BOB);

    assert.equal(result.status, "already_friends");
    assert.equal(result.otherUserId, ALICE.userId);
    assertMutualFriendship(db, ALICE, BOB, { a: 1, b: 1 });
    // The second invite is consumed so a third account cannot replay it.
    assert.equal(inviteDoc(db, second)?.status, "accepted");
  });

  it("same invite accepted twice sequentially (double tap / retry) → one friendship, +1 once", async () => {
    const db = freshDb();
    const token = await issueInvite(db, ALICE);

    const r1 = await accept(db, token, BOB);
    const r2 = await accept(db, token, BOB);

    assert.equal(r1.status, "accepted");
    assert.equal(r2.status, "already_friends");
    assertMutualFriendship(db, ALICE, BOB, { a: 1, b: 1 });
  });

  it("same invite accepted concurrently from two devices → one friendship, +1 once", async () => {
    const db = freshDb();
    const token = await issueInvite(db, ALICE);
    db.beforeCommit = barrier(2);

    const [r1, r2] = await Promise.all([accept(db, token, BOB), accept(db, token, BOB)]);

    assert.deepEqual([r1.status, r2.status].sort(), ["accepted", "already_friends"]);
    assert.ok(db.retryCount >= 1, "the loser must have retried after the conflict");
    assertMutualFriendship(db, ALICE, BOB, { a: 1, b: 1 });
  });

  it("consumed one-time invite cannot be replayed by a third account", async () => {
    const db = freshDb();
    const token = await issueInvite(db, ALICE);
    assert.equal((await accept(db, token, BOB)).status, "accepted");

    const replay = await accept(db, token, CAROL);

    assert.equal(replay.status, "invalid");
    assert.deepEqual(friendshipDocs(db), [`friendships/${buildFriendPairId(ALICE.userId, BOB.userId)}`]);
    assert.equal(friendsCount(db, CAROL.userId), 0);
    assert.equal(friendsCount(db, ALICE.userId), 1);
  });

  it("A→B and B→A invites accepted concurrently → one canonical friendship, +1 each", async () => {
    const db = freshDb();
    const aliceInvite = await issueInvite(db, ALICE);
    const bobInvite = await issueInvite(db, BOB);
    db.beforeCommit = barrier(2);

    const [r1, r2] = await Promise.all([
      accept(db, aliceInvite, BOB),
      accept(db, bobInvite, ALICE),
    ]);

    assert.deepEqual([r1.status, r2.status].sort(), ["accepted", "already_friends"]);
    assert.ok(db.retryCount >= 1);
    assertMutualFriendship(db, ALICE, BOB, { a: 1, b: 1 });
    assert.equal(inviteDoc(db, aliceInvite)?.status, "accepted");
    assert.equal(inviteDoc(db, bobInvite)?.status, "accepted");
  });

  it("block in either direction denies and leaves the graph untouched", async () => {
    for (const direction of ["forward", "reverse"] as const) {
      const db = freshDb();
      const token = await issueInvite(db, ALICE);
      const [owner, target] =
        direction === "forward" ? [BOB.userId, ALICE.userId] : [ALICE.userId, BOB.userId];
      db.apply(`blocks/${owner}/targets/${target}`, { fromUserId: owner, toUserId: target }, false);

      const result = await accept(db, token, BOB);

      assert.equal(result.status, "blocked", direction);
      assert.deepEqual(friendshipDocs(db), []);
      assert.equal(edge(db, ALICE.userId, BOB.userId), undefined);
      assert.equal(edge(db, BOB.userId, ALICE.userId), undefined);
      assert.equal(friendsCount(db, ALICE.userId), 0);
      assert.equal(friendsCount(db, BOB.userId), 0);
      assert.equal(inviteDoc(db, token)?.status, "pending");
    }
  });

  it("inviter withdrawn or deleted after issuing → invalid, invite revoked, no orphan edge", async () => {
    for (const mode of ["withdrawn", "deleted", "loginDisabled"] as const) {
      const db = freshDb();
      const token = await issueInvite(db, ALICE);
      if (mode === "deleted") db.store.delete(`users/${ALICE.userId}`);
      if (mode === "withdrawn") db.apply(`users/${ALICE.userId}`, { isWithdrawn: true }, true);
      if (mode === "loginDisabled") db.apply(`users/${ALICE.userId}`, { loginDisabled: true }, true);

      const result = await accept(db, token, BOB);

      assert.equal(result.status, "invalid", mode);
      assert.deepEqual(friendshipDocs(db), [], mode);
      assert.equal(edge(db, BOB.userId, ALICE.userId), undefined, mode);
      assert.equal(friendsCount(db, BOB.userId), 0, mode);
      assert.equal(inviteDoc(db, token)?.status, "revoked", mode);
    }
  });

  it("withdrawn or login-disabled acceptor (legacy Kakao-token path) is denied without writes", async () => {
    for (const marker of [{ isWithdrawn: true }, { loginDisabled: true }, { isStudentVerified: false }]) {
      const db = freshDb();
      const token = await issueInvite(db, ALICE);
      const acceptor: FriendInviteParticipant = {
        ...BOB,
        data: { studentEmail: BOB.email, isStudentVerified: true, ...marker },
      };

      const result = await acceptFriendInviteByToken({
        db: db.asFirestore(),
        rawToken: token,
        acceptor,
        now: () => NOW,
      });

      assert.equal(result.status, "invalid", JSON.stringify(marker));
      assert.deepEqual(friendshipDocs(db), []);
      assert.equal(friendsCount(db, ALICE.userId), 0);
      assert.equal(inviteDoc(db, token)?.status, "pending");
    }
  });

  it("withdrawn inviter cannot issue an invite", async () => {
    const db = freshDb();
    await assert.rejects(
      createFriendInviteRecord({
        db: db.asFirestore(),
        inviter: {
          ...ALICE,
          data: { studentEmail: ALICE.email, isStudentVerified: true, isWithdrawn: true },
        },
        now: NOW,
      }),
      (error: unknown) => error instanceof HttpsError && error.code === "failed-precondition",
    );
    assert.equal([...db.store.keys()].some((k) => k.startsWith("friendInvites/")), false);
  });

  it("inviter identity is taken from the invite document, never from the request", async () => {
    const db = freshDb();
    const token = await issueInvite(db, ALICE);
    // Simulate an attacker who mutates nothing but hopes the acceptor's own
    // uid could be substituted: the pair is always inviter (stored) ↔ caller.
    const result = await accept(db, token, CAROL);
    assert.equal(result.status, "accepted");
    assert.equal(result.otherUserId, ALICE.userId);
    assertMutualFriendship(db, ALICE, CAROL, { a: 1, b: 1 });
    assert.equal(edge(db, BOB.userId, ALICE.userId), undefined);
  });

  it("no partial state: every acceptance leaves either zero or both edges", async () => {
    const db = freshDb();
    const tokens = await Promise.all([
      issueInvite(db, ALICE),
      issueInvite(db, BOB),
      issueInvite(db, CAROL),
    ]);
    await Promise.all([
      accept(db, tokens[0], BOB),
      accept(db, tokens[1], CAROL),
      accept(db, tokens[2], ALICE),
    ]);

    for (const [a, b] of [
      [ALICE, BOB],
      [BOB, CAROL],
      [CAROL, ALICE],
    ] as const) {
      const ab = edge(db, a.userId, b.userId) !== undefined;
      const ba = edge(db, b.userId, a.userId) !== undefined;
      assert.equal(ab, ba, `${a.userId}↔${b.userId} must be symmetric`);
      const pairExists = db.store.has(`friendships/${buildFriendPairId(a.userId, b.userId)}`);
      assert.equal(ab, pairExists);
    }
    assert.equal(friendsCount(db, ALICE.userId), 2);
    assert.equal(friendsCount(db, BOB.userId), 2);
    assert.equal(friendsCount(db, CAROL.userId), 2);
  });
});

// =============================================================================
// Structural guards on the shipped source
// =============================================================================

// =============================================================================
// Purpose isolation: FRIEND_INVITE vs TEAM_INVITE
// =============================================================================

const TEAM_ID = "team_setup_1";

function seedTeam(db: FakeDb, leader: FriendInviteParticipant, extra: DocData = {}): void {
  db.apply(
    `eventTeamSetups/${TEAM_ID}`,
    {
      leaderUserId: leader.userId,
      acceptedUserIds: [leader.userId],
      pendingInviteeIds: [],
      memberCount: 1,
      ...extra,
    },
    false,
  );
}

function seedFriendEdge(db: FakeDb, a: FriendInviteParticipant, b: FriendInviteParticipant): void {
  const pairId = buildFriendPairId(a.userId, b.userId);
  db.apply(`friendships/${pairId}`, { pairId, userIds: [a.userId, b.userId].sort(), status: "active" }, false);
  db.apply(`users/${a.userId}/friends/${b.userId}`, { friendUserId: b.userId, pairId }, false);
  db.apply(`users/${b.userId}/friends/${a.userId}`, { friendUserId: a.userId, pairId }, false);
  db.apply(`users/${a.userId}`, { friendsCount: friendsCount(db, a.userId) + 1 }, true);
  db.apply(`users/${b.userId}`, { friendsCount: friendsCount(db, b.userId) + 1 }, true);
}

async function issueTeamInvite(db: FakeDb, leader: FriendInviteParticipant, now: Date = NOW): Promise<string> {
  const created = await createTeamInviteRecord({ db: db.asFirestore(), leader, teamSetupId: TEAM_ID, now });
  return created.inviteToken;
}

function redeem(db: FakeDb, token: string | null | undefined, redeemer: FriendInviteParticipant, now: Date = NOW) {
  return redeemTeamInviteByToken({ db: db.asFirestore(), rawToken: token, redeemer, now: () => now });
}

function preview(db: FakeDb, token: string | null | undefined, viewer: FriendInviteParticipant, now: Date = NOW) {
  return previewInviteByToken({ db: db.asFirestore(), rawToken: token, viewer, now: () => now });
}

/** Serialised view of everything friendship-related, for side-effect checks. */
function friendGraphSnapshot(db: FakeDb): string {
  const entries = [...db.store.entries()]
    .filter(([path]) => path.startsWith("friendships/") || path.includes("/friends/"))
    .map(([path, data]) => [path, { ...data, createdAt: undefined }]);
  const counts = [ALICE, BOB, CAROL].map((u) => [u.userId, friendsCount(db, u.userId)]);
  return JSON.stringify({ entries, counts });
}

function teamDoc(db: FakeDb): DocData | undefined {
  return db.store.get(`eventTeamSetups/${TEAM_ID}`);
}

function teamInvites(db: FakeDb): Array<[string, DocData]> {
  return [...db.store.entries()].filter(([p]) => p.startsWith("eventTeamInvites/"));
}

describe("invite purpose", () => {
  it("is server-owned: friend records carry FRIEND_INVITE, team records TEAM_INVITE", async () => {
    const db = freshDb();
    seedTeam(db, ALICE);
    const friendToken = await issueInvite(db, ALICE);
    const teamToken = await issueTeamInvite(db, ALICE);
    assert.equal(inviteDoc(db, friendToken)?.purpose, INVITE_PURPOSE_FRIEND);
    assert.equal(inviteDoc(db, teamToken)?.purpose, INVITE_PURPOSE_TEAM);
    assert.equal(inviteDoc(db, teamToken)?.teamSetupId, TEAM_ID);
  });

  it("legacy records without a purpose read as FRIEND_INVITE; unknown values fail closed", () => {
    assert.equal(readInvitePurpose({}), INVITE_PURPOSE_FRIEND);
    assert.equal(readInvitePurpose({ purpose: null }), INVITE_PURPOSE_FRIEND);
    assert.equal(readInvitePurpose({ purpose: "TEAM_INVITE" }), INVITE_PURPOSE_TEAM);
    assert.equal(readInvitePurpose({ purpose: "friend" }), null);
    assert.equal(readInvitePurpose({ purpose: "ADMIN" }), null);
  });

  it("team invite URL and execution params are distinct from the friend ones", async () => {
    const db = freshDb();
    seedTeam(db, ALICE);
    const created = await createTeamInviteRecord({ db: db.asFirestore(), leader: ALICE, teamSetupId: TEAM_ID, now: NOW });
    const url = new URL(created.inviteUrl);
    assert.equal(url.host, "seolleyeon.com");
    assert.equal(url.pathname, TEAM_INVITE_PATH);
    assert.equal(url.pathname, "/invite/team");
    assert.equal(url.searchParams.get("token"), created.inviteToken);
    assert.deepEqual(created.executionParams, { target: TEAM_INVITE_TARGET, token: created.inviteToken });
    assert.equal(TEAM_INVITE_TARGET, "team_invite");
    assert.notEqual(TEAM_INVITE_TARGET, FRIEND_INVITE_TARGET);
    assert.notEqual(TEAM_INVITE_PATH, FRIEND_INVITE_PATH);
    assert.equal(created.inviteUrl, buildTeamInviteUrl(created.inviteToken));
    assert.equal(created.purpose, INVITE_PURPOSE_TEAM);
  });

  it("FRIEND token → team redemption is denied without touching the team", async () => {
    const db = freshDb();
    seedTeam(db, ALICE);
    seedFriendEdge(db, ALICE, BOB);
    const friendToken = await issueInvite(db, ALICE);
    const before = JSON.stringify(teamDoc(db));

    const result = await redeem(db, friendToken, BOB);

    assert.equal(result.status, "invalid");
    assert.equal(JSON.stringify(teamDoc(db)), before);
    assert.deepEqual(teamInvites(db), []);
    assert.equal(inviteDoc(db, friendToken)?.status, "pending");
  });

  it("TEAM token → friend acceptance is denied without touching the friend graph", async () => {
    const db = freshDb();
    seedTeam(db, ALICE);
    const teamToken = await issueTeamInvite(db, ALICE);
    const before = friendGraphSnapshot(db);

    const result = await accept(db, teamToken, BOB);

    assert.equal(result.status, "invalid");
    assert.equal(friendGraphSnapshot(db), before);
    assert.deepEqual(friendshipDocs(db), []);
    assert.equal(inviteDoc(db, teamToken)?.status, "pending");
  });

  it("a record whose purpose was tampered to an unknown value is rejected by every path", async () => {
    const db = freshDb();
    seedTeam(db, ALICE);
    seedFriendEdge(db, ALICE, BOB);
    const token = await issueInvite(db, ALICE);
    const path = [...db.store.keys()].find((k) => k.startsWith("friendInvites/"))!;
    db.apply(path, { purpose: "SOMETHING_ELSE" }, true);

    assert.equal((await accept(db, token, CAROL)).status, "invalid");
    assert.equal((await redeem(db, token, CAROL)).status, "invalid");
    assert.equal((await preview(db, token, CAROL)).status, "invalid");
    assert.deepEqual(friendshipDocs(db), [`friendships/${buildFriendPairId(ALICE.userId, BOB.userId)}`]);
    assert.deepEqual(teamInvites(db), []);
  });

  it("legacy friend record (no purpose field) still accepts as a friend invite", async () => {
    const db = freshDb();
    const token = await issueInvite(db, ALICE);
    const path = [...db.store.keys()].find((k) => k.startsWith("friendInvites/"))!;
    const legacy = { ...db.store.get(path)! };
    delete legacy.purpose;
    db.apply(path, legacy, false);

    const result = await accept(db, token, BOB);
    assert.equal(result.status, "accepted");
    assertMutualFriendship(db, ALICE, BOB, { a: 1, b: 1 });
  });
});

describe("previewInviteByToken (read-only)", () => {
  it("friend token: purpose + inviter display, no writes, no consumption", async () => {
    const db = freshDb();
    const token = await issueInvite(db, ALICE);
    const before = JSON.stringify([...db.store.entries()]);

    const result = await preview(db, token, BOB);

    assert.equal(result.status, "valid");
    assert.equal(result.purpose, INVITE_PURPOSE_FRIEND);
    assert.equal(result.inviterUserId, ALICE.userId);
    assert.equal(result.inviterName, "앨리스");
    assert.equal(JSON.stringify([...db.store.entries()]), before);
    assert.deepEqual(friendshipDocs(db), []);
  });

  it("team token: purpose TEAM + teamSetupId so the app routes to the team flow", async () => {
    const db = freshDb();
    seedTeam(db, ALICE);
    const token = await issueTeamInvite(db, ALICE);
    const result = await preview(db, token, BOB);
    assert.equal(result.status, "valid");
    assert.equal(result.purpose, INVITE_PURPOSE_TEAM);
    assert.equal(result.teamSetupId, TEAM_ID);
    assert.equal(result.inviterName, "앨리스");
  });

  it("team token already redeemed by the same viewer stays routable; other viewers see used", async () => {
    const db = freshDb();
    seedTeam(db, ALICE);
    seedFriendEdge(db, ALICE, BOB);
    const token = await issueTeamInvite(db, ALICE);
    assert.equal((await redeem(db, token, BOB)).status, "invited");
    const same = await preview(db, token, BOB);
    assert.equal(same.status, "valid");
    assert.equal(same.purpose, INVITE_PURPOSE_TEAM);
    assert.equal((await preview(db, token, CAROL)).status, "used");
    assert.equal((await redeem(db, token, BOB)).status, "already_invited");
  });

  it("reports self, already-friends, expired, used and invalid without mutating", async () => {
    const db = freshDb();
    const token = await issueInvite(db, ALICE);
    assert.equal((await preview(db, token, ALICE)).status, "self_invite");
    assert.equal((await preview(db, "deadbeef", BOB)).status, "invalid");
    assert.equal((await preview(db, token, BOB, new Date(NOW.getTime() + 8 * 24 * 3600 * 1000))).status, "expired");

    seedFriendEdge(db, ALICE, BOB);
    assert.equal((await preview(db, token, BOB)).status, "already_friends");

    await accept(db, token, CAROL);
    assert.equal((await preview(db, token, BOB)).status, "used");
    assert.equal((await preview(db, token, CAROL)).status, "already_friends");
    assert.equal(inviteDoc(db, token)?.acceptedByUserId, CAROL.userId);
  });
});

describe("redeemTeamInviteByToken", () => {
  it("friend of the leader → pending team invitation, zero friendship side effects", async () => {
    const db = freshDb();
    seedTeam(db, ALICE);
    seedFriendEdge(db, ALICE, BOB);
    const token = await issueTeamInvite(db, ALICE);
    const graphBefore = friendGraphSnapshot(db);

    const result = await redeem(db, token, BOB);

    assert.equal(result.status, "invited");
    assert.ok(result.teamInviteId);
    assert.equal(result.teamSetupId, TEAM_ID);
    assert.equal(result.inviterName, "앨리스");
    const [[, invite]] = teamInvites(db);
    assert.equal(invite.teamSetupId, TEAM_ID);
    assert.equal(invite.inviterUserId, ALICE.userId);
    assert.equal(invite.inviteeUserId, BOB.userId);
    assert.equal(invite.status, "pending");
    assert.equal(invite.source, "share_link");
    assert.deepEqual(teamDoc(db)?.pendingInviteeIds, [BOB.userId]);
    assert.deepEqual(teamDoc(db)?.acceptedUserIds, [ALICE.userId], "membership is NOT granted by redemption");
    assert.equal(inviteDoc(db, token)?.status, "accepted");
    assert.equal(inviteDoc(db, token)?.teamInviteId, result.teamInviteId);
    assert.equal(friendGraphSnapshot(db), graphBefore, "friend graph must be untouched");
    assert.equal(friendsCount(db, ALICE.userId), 1);
    assert.equal(friendsCount(db, BOB.userId), 1);
  });

  it("not a Seolleyeon friend → not_friends, and NO friendship is created", async () => {
    const db = freshDb();
    seedTeam(db, ALICE);
    const token = await issueTeamInvite(db, ALICE);
    const graphBefore = friendGraphSnapshot(db);

    const result = await redeem(db, token, BOB);

    assert.equal(result.status, "not_friends");
    assert.deepEqual(teamInvites(db), []);
    assert.deepEqual(teamDoc(db)?.pendingInviteeIds, []);
    assert.equal(friendGraphSnapshot(db), graphBefore);
    assert.deepEqual(friendshipDocs(db), []);
    assert.equal(inviteDoc(db, token)?.status, "pending");
  });

  it("self, already member, already invited, one-time replay, expired", async () => {
    const db = freshDb();
    seedTeam(db, ALICE, { acceptedUserIds: [ALICE.userId, CAROL.userId] });
    seedFriendEdge(db, ALICE, BOB);
    seedFriendEdge(db, ALICE, CAROL);
    const token = await issueTeamInvite(db, ALICE);

    assert.equal((await redeem(db, token, ALICE)).status, "self_invite");
    assert.equal((await redeem(db, token, CAROL)).status, "already_member");
    const first = await redeem(db, token, BOB);
    assert.equal(first.status, "invited");
    const again = await redeem(db, token, BOB);
    assert.equal(again.status, "already_invited");
    assert.equal(again.teamInviteId, first.teamInviteId);
    assert.equal(teamInvites(db).length, 1);
    assert.deepEqual(teamDoc(db)?.pendingInviteeIds, [BOB.userId]);

    // consumed token cannot be replayed by another friend
    const db2 = freshDb();
    seedTeam(db2, ALICE);
    seedFriendEdge(db2, ALICE, BOB);
    seedFriendEdge(db2, ALICE, CAROL);
    const t2 = await issueTeamInvite(db2, ALICE);
    assert.equal((await redeem(db2, t2, BOB)).status, "invited");
    assert.equal((await redeem(db2, t2, CAROL)).status, "invalid");
    assert.equal(teamInvites(db2).length, 1);

    const db3 = freshDb();
    seedTeam(db3, ALICE);
    seedFriendEdge(db3, ALICE, BOB);
    const t3 = await issueTeamInvite(db3, ALICE);
    assert.equal((await redeem(db3, t3, BOB, new Date(NOW.getTime() + 8 * 24 * 3600 * 1000))).status, "expired");
    assert.deepEqual(teamInvites(db3), []);
  });

  it("capacity is a hard postcondition under concurrent redemption", async () => {
    const db = freshDb();
    seedTeam(db, ALICE, { acceptedUserIds: [ALICE.userId, "uid_dave"] });
    seedFriendEdge(db, ALICE, BOB);
    seedFriendEdge(db, ALICE, CAROL);
    const tBob = await issueTeamInvite(db, ALICE);
    const tCarol = await issueTeamInvite(db, ALICE);
    db.beforeCommit = barrier(2);

    const [r1, r2] = await Promise.all([redeem(db, tBob, BOB), redeem(db, tCarol, CAROL)]);

    assert.deepEqual([r1.status, r2.status].sort(), ["invited", "team_full"]);
    assert.equal(teamInvites(db).length, 1);
    const pending = teamDoc(db)?.pendingInviteeIds as string[];
    assert.equal(pending.length, 1);
    assert.equal((teamDoc(db)?.acceptedUserIds as string[]).length + pending.length, EVENT_TEAM_CAPACITY);
  });

  it("only the leader can issue a team share link, and not when the team is full", async () => {
    const db = freshDb();
    seedTeam(db, ALICE);
    await assert.rejects(
      createTeamInviteRecord({ db: db.asFirestore(), leader: BOB, teamSetupId: TEAM_ID, now: NOW }),
      (e: unknown) => e instanceof HttpsError && e.code === "permission-denied",
    );
    await assert.rejects(
      createTeamInviteRecord({ db: db.asFirestore(), leader: ALICE, teamSetupId: "missing", now: NOW }),
      (e: unknown) => e instanceof HttpsError && e.code === "not-found",
    );
    db.apply(`eventTeamSetups/${TEAM_ID}`, { acceptedUserIds: [ALICE.userId, BOB.userId, CAROL.userId] }, true);
    await assert.rejects(
      createTeamInviteRecord({ db: db.asFirestore(), leader: ALICE, teamSetupId: TEAM_ID, now: NOW }),
      (e: unknown) => e instanceof HttpsError && e.code === "failed-precondition",
    );
  });
});

// =============================================================================
// Structural guards on the shipped source
// =============================================================================

describe("friendInvites source contract", () => {
  const source = readFileSync(resolve(__dirname, "../src/friendInvites.ts"), "utf8");
  const indexSource = readFileSync(resolve(__dirname, "../src/index.ts"), "utf8");

  function fnBody(name: string): string {
    const start = source.indexOf(`export async function ${name}(`);
    assert.ok(start >= 0, name);
    // Up to the function's own closing brace (column 0), excluding the doc
    // comment of whatever is declared next.
    const close = source.indexOf("\n}\n", start);
    assert.ok(close > start, name);
    return source.slice(start, close + 3);
  }

  it("each transaction performs every read before its first write", () => {
    for (const name of ["acceptFriendInviteByToken", "redeemTeamInviteByToken"]) {
      const body = fnBody(name);
      const txStart = body.indexOf("db.runTransaction(");
      assert.ok(txStart >= 0, name);
      const tx = body.slice(txStart);
      const lastRead = tx.lastIndexOf("transaction.get(");
      const firstWrite = tx.indexOf("transaction.set(");
      assert.ok(lastRead >= 0 && firstWrite >= 0, name);
      assert.ok(lastRead < firstWrite, `${name}: all transaction.get() calls must precede transaction.set()`);
    }
  });

  it("the friend path never touches team collections and the team path never touches the friend graph", () => {
    const friendBody = fnBody("acceptFriendInviteByToken");
    assert.equal(/eventTeam/.test(friendBody), false);
    const teamBody = fnBody("redeemTeamInviteByToken");
    assert.equal(/collection\("friendships"\)/.test(teamBody), false);
    assert.equal(/friendsCount/.test(teamBody), false);
    assert.equal(/acceptedUserIds:/.test(teamBody), false, "redemption must not grant membership");
    const previewBody = fnBody("previewInviteByToken");
    assert.equal(/\.set\(|runTransaction|FieldValue/.test(previewBody), false, "preview must be read-only");
  });

  it("invite callables use Firebase auth only — no Kakao access-token fallback, no uid from the body", () => {
    const names = [
      "createFriendInvite",
      "previewInviteToken",
      "acceptFriendInvite",
      "createEventTeamShareInvite",
      "redeemEventTeamShareInvite",
    ];
    for (const name of names) {
      const start = indexSource.indexOf(`export const ${name} = onCall(`);
      assert.ok(start >= 0, name);
      const end = indexSource.indexOf("\nexport const ", start + 1);
      const body = indexSource.slice(start, end);
      assert.ok(body.includes("resolveAuthedAppUser(request.auth)"), `${name} must resolve via Firebase auth`);
      assert.equal(body.includes("resolveUserForFriendCallable"), false, `${name} must not use the Kakao fallback resolver`);
      assert.equal(/kakaoAccessToken/i.test(body), false, `${name} must not read kakaoAccessToken`);
      assert.equal(/data\.(inviterUserId|inviterUid|userId|uid|inviteeUserId)\b/.test(body), false, name);
    }
    assert.equal(indexSource.includes("seolleyeon-final.web.app/invite"), false);
  });

  it("only the invite module writes friendInvites / friendships", () => {
    for (const marker of ['collection("friendships")', 'collection("friendInvites")']) {
      assert.equal(indexSource.includes(marker), false, `${marker} must live in friendInvites.ts`);
      assert.ok(source.includes(marker));
    }
  });
});

// =============================================================================
// respondEventTeamInvite core — membership commit authority
// =============================================================================

function respond(db: FakeDb, user: FriendInviteParticipant, inviteId: string | undefined, accept: boolean) {
  return respondTeamInviteCore({ db: db.asFirestore(), user, inviteId, accept });
}

function seedBlock(db: FakeDb, owner: FriendInviteParticipant, target: FriendInviteParticipant): void {
  db.apply(`blocks/${owner.userId}/targets/${target.userId}`, { fromUserId: owner.userId, toUserId: target.userId }, false);
}

describe("redeemTeamInviteByToken block protection", () => {
  it("block in either direction denies redemption: no slot, no team invite, token kept", async () => {
    for (const direction of ["leader_blocks_redeemer", "redeemer_blocks_leader"] as const) {
      const db = freshDb();
      seedTeam(db, ALICE);
      seedFriendEdge(db, ALICE, BOB);
      if (direction === "leader_blocks_redeemer") seedBlock(db, ALICE, BOB);
      else seedBlock(db, BOB, ALICE);
      const token = await issueTeamInvite(db, ALICE);
      const graphBefore = friendGraphSnapshot(db);
      const teamBefore = JSON.stringify(teamDoc(db));

      const result = await redeem(db, token, BOB);

      assert.equal(result.status, "blocked", direction);
      assert.deepEqual(teamInvites(db), [], direction);
      assert.equal(JSON.stringify(teamDoc(db)), teamBefore, direction);
      assert.equal(inviteDoc(db, token)?.status, "pending", direction);
      assert.equal(friendGraphSnapshot(db), graphBefore, direction);
    }
  });
});

describe("respondTeamInviteCore", () => {
  async function redeemedPending(db: FakeDb): Promise<string> {
    seedTeam(db, ALICE);
    seedFriendEdge(db, ALICE, BOB);
    const token = await issueTeamInvite(db, ALICE);
    const redeemed = await redeem(db, token, BOB);
    assert.equal(redeemed.status, "invited");
    return redeemed.teamInviteId!;
  }

  it("accept → membership committed, pending slot released, friend graph untouched", async () => {
    const db = freshDb();
    const inviteId = await redeemedPending(db);
    const graphBefore = friendGraphSnapshot(db);

    const result = await respond(db, BOB, inviteId, true);

    assert.deepEqual(result, { ok: true, status: "accepted" });
    assert.deepEqual(teamDoc(db)?.acceptedUserIds, [ALICE.userId, BOB.userId]);
    assert.equal(teamDoc(db)?.memberCount, 2);
    assert.deepEqual(teamDoc(db)?.pendingInviteeIds, []);
    assert.equal(db.store.get(`eventTeamInvites/${inviteId}`)?.status, "accepted");
    assert.equal(friendGraphSnapshot(db), graphBefore);
    assert.equal(friendsCount(db, ALICE.userId), 1);
    assert.equal(friendsCount(db, BOB.userId), 1);
  });

  it("decline → no membership, pending slot released", async () => {
    const db = freshDb();
    const inviteId = await redeemedPending(db);
    const result = await respond(db, BOB, inviteId, false);
    assert.deepEqual(result, { ok: true, status: "declined" });
    assert.deepEqual(teamDoc(db)?.acceptedUserIds, [ALICE.userId]);
    assert.deepEqual(teamDoc(db)?.pendingInviteeIds, []);
    assert.equal(db.store.get(`eventTeamInvites/${inviteId}`)?.status, "declined");
  });

  it("block created AFTER redemption (either direction) denies membership and releases the slot", async () => {
    for (const direction of ["leader_blocks_invitee", "invitee_blocks_leader"] as const) {
      const db = freshDb();
      const inviteId = await redeemedPending(db);
      assert.deepEqual(teamDoc(db)?.pendingInviteeIds, [BOB.userId]);
      if (direction === "leader_blocks_invitee") seedBlock(db, ALICE, BOB);
      else seedBlock(db, BOB, ALICE);

      const result = await respond(db, BOB, inviteId, true);

      assert.deepEqual(result, { ok: false, code: "blocked" }, direction);
      assert.deepEqual(teamDoc(db)?.acceptedUserIds, [ALICE.userId], direction);
      assert.deepEqual(teamDoc(db)?.pendingInviteeIds, [], `${direction}: slot must be released`);
      const invite = db.store.get(`eventTeamInvites/${inviteId}`);
      assert.equal(invite?.status, "cancelled", direction);
      assert.equal(invite?.cancelReason, "blocked", direction);
      // A second accept attempt cannot resurrect it.
      assert.deepEqual(await respond(db, BOB, inviteId, true), { ok: false, code: "already_responded" });
    }
  });

  it("friendship removed after redemption → not_friends, slot released", async () => {
    const db = freshDb();
    const inviteId = await redeemedPending(db);
    db.store.delete(`users/${ALICE.userId}/friends/${BOB.userId}`);
    db.versions.set(`users/${ALICE.userId}/friends/${BOB.userId}`, 99);

    const result = await respond(db, BOB, inviteId, true);

    assert.deepEqual(result, { ok: false, code: "not_friends" });
    assert.deepEqual(teamDoc(db)?.acceptedUserIds, [ALICE.userId]);
    assert.deepEqual(teamDoc(db)?.pendingInviteeIds, []);
  });

  it("only the invitee may respond; a stranger is rejected without writes", async () => {
    const db = freshDb();
    const inviteId = await redeemedPending(db);
    const before = JSON.stringify([...db.store.entries()]);
    await assert.rejects(
      respond(db, CAROL, inviteId, true),
      (e: unknown) => e instanceof HttpsError && e.code === "permission-denied",
    );
    assert.equal(JSON.stringify([...db.store.entries()]), before);
    assert.deepEqual(await respond(db, BOB, "missing", true), { ok: false, code: "not_found" });
    await assert.rejects(respond(db, BOB, "", true), (e: unknown) => e instanceof HttpsError);
  });

  it("duplicate accept / retry is idempotent: one membership, no count drift", async () => {
    const db = freshDb();
    const inviteId = await redeemedPending(db);
    assert.deepEqual(await respond(db, BOB, inviteId, true), { ok: true, status: "accepted" });
    assert.deepEqual(await respond(db, BOB, inviteId, true), { ok: false, code: "already_responded" });
    assert.deepEqual(teamDoc(db)?.acceptedUserIds, [ALICE.userId, BOB.userId]);
    assert.equal(teamDoc(db)?.memberCount, 2);
  });

  it("two invitees racing for the last seat → exactly one accepted, capacity invariant holds", async () => {
    const db = freshDb();
    seedTeam(db, ALICE, { acceptedUserIds: [ALICE.userId, "uid_dave"], memberCount: 2 });
    seedFriendEdge(db, ALICE, BOB);
    seedFriendEdge(db, ALICE, CAROL);
    // Both invited (pending) before the last seat is taken — mirrors two
    // in-app invitations issued while capacity counted pending slots.
    db.apply(`eventTeamInvites/inv_bob`, { teamSetupId: TEAM_ID, inviterUserId: ALICE.userId, inviteeUserId: BOB.userId, status: "pending" }, false);
    db.apply(`eventTeamInvites/inv_carol`, { teamSetupId: TEAM_ID, inviterUserId: ALICE.userId, inviteeUserId: CAROL.userId, status: "pending" }, false);
    db.apply(`eventTeamSetups/${TEAM_ID}`, { pendingInviteeIds: [BOB.userId, CAROL.userId] }, true);
    db.beforeCommit = barrier(2);

    const [r1, r2] = await Promise.all([respond(db, BOB, "inv_bob", true), respond(db, CAROL, "inv_carol", true)]);

    const outcomes = [r1, r2].map((r) => (r.ok ? r.status : r.code)).sort();
    assert.deepEqual(outcomes, ["accepted", "team_full"]);
    assert.ok(db.retryCount >= 1);
    const accepted = teamDoc(db)?.acceptedUserIds as string[];
    assert.equal(accepted.length, EVENT_TEAM_CAPACITY);
    assert.equal(teamDoc(db)?.memberCount, EVENT_TEAM_CAPACITY);
    assert.deepEqual(teamDoc(db)?.pendingInviteeIds, [], "loser's slot must be released");
  });

  it("withdrawn / login-disabled invitee cannot commit membership", async () => {
    const db = freshDb();
    const inviteId = await redeemedPending(db);
    const withdrawn: FriendInviteParticipant = {
      ...BOB,
      data: { studentEmail: BOB.email, isStudentVerified: true, isWithdrawn: true },
    };
    assert.deepEqual(await respond(db, withdrawn, inviteId, true), { ok: false, code: "ineligible" });
    assert.deepEqual(teamDoc(db)?.acceptedUserIds, [ALICE.userId]);
  });
});

describe("team membership source contract", () => {
  const indexSource = readFileSync(resolve(__dirname, "../src/index.ts"), "utf8");
  const membershipSource = readFileSync(resolve(__dirname, "../src/eventTeamMembership.ts"), "utf8");

  function callableBody(name: string): string {
    const start = indexSource.indexOf(`export const ${name} = onCall(`);
    assert.ok(start >= 0, name);
    const end = indexSource.indexOf("\nexport const ", start + 1);
    return indexSource.slice(start, end);
  }

  it("team setup/invite/membership callables use Firebase auth only — Kakao access token is never an identity", () => {
    for (const name of ["ensureEventTeamSetup", "createEventTeamInvite", "respondEventTeamInvite", "spinSeasonMeetingRoulette"]) {
      const body = callableBody(name);
      assert.ok(body.includes("resolveAuthedAppUser(request.auth)"), name);
      assert.equal(body.includes("resolveUserForFriendCallable"), false, `${name}: Kakao fallback resolver must be gone`);
      assert.equal(/kakaoAccessToken|verifyKakaoAccessToken/.test(body), false, name);
      assert.ok(/onCall\(\s*withAppCheck\(/.test(body), `${name} must enforce App Check`);
    }
    assert.equal(/kakaoAccessToken|verifyKakaoAccessToken|resolveUserForFriendCallable/.test(membershipSource), false);
    // The Kakao-token callable resolver is gone from the codebase entirely.
    assert.equal(indexSource.includes("resolveUserForFriendCallable"), false);
    for (const name of ["createTeamMeetingRequest", "respondTeamMeetingRequest", "reportAndBlockUser"]) {
      const start = indexSource.indexOf(`export const ${name} = `);
      assert.ok(start >= 0, name);
      const body = indexSource.slice(start, indexSource.indexOf(");", start));
      assert.ok(body.includes("resolveCallableUserFirebaseOnly"), `${name} must use the Firebase-only resolver`);
    }
    const respondBody = callableBody("respondEventTeamInvite");
    assert.ok(respondBody.includes('typeof data.accept !== "boolean"'), "non-boolean accept must be rejected, not treated as decline");
  });

  it("respond core performs every read before its first write and re-checks blocks at commit", () => {
    const txStart = membershipSource.indexOf("db.runTransaction(");
    assert.ok(txStart >= 0);
    const tx = membershipSource.slice(txStart);
    const lastRead = tx.lastIndexOf("tx.get(");
    const firstWrite = tx.indexOf("tx.update(");
    assert.ok(lastRead >= 0 && firstWrite >= 0 && lastRead < firstWrite);
    assert.ok(tx.includes("isBlockedEitherWay(forwardBlock, reverseBlock)"));
    assert.ok(tx.includes("inviteeBlocksInviterRef") || membershipSource.includes("inviteeBlocksInviterRef"));
    assert.equal(/collection\("friendships"\)|friendsCount/.test(membershipSource), false, "membership must never write the friend graph");
  });

  it("in-app team invitations are block-gated and the callable delegates membership to the core", () => {
    const create = callableBody("createEventTeamInvite");
    assert.ok(create.includes("assertNotBlockedEitherWay(db, inviter.userId, inviteeUserId)"));
    const respondBody = callableBody("respondEventTeamInvite");
    assert.ok(respondBody.includes("respondTeamInviteCore({"));
    assert.equal(respondBody.includes("runTransaction"), false, "the callable itself must not carry a second membership transaction");
  });
});
