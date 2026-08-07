import test from "node:test";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} from "@firebase/rules-unit-testing";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "..");
const PROJECT_ID = "seolleyeon-storage-rules-test";

const rules = readFileSync(resolve(repoRoot, "storage.rules"), "utf8");

let testEnv;

async function getEnv() {
  if (!testEnv) {
    testEnv = await initializeTestEnvironment({
      projectId: PROJECT_ID,
      storage: {
        rules,
        host: "127.0.0.1",
        port: 9199,
      },
    });
  }
  return testEnv;
}

test.before(async () => {
  await getEnv();
});

test.after(async () => {
  if (testEnv) await testEnv.cleanup();
});

async function seedBytes(path, content = "fake-image-bytes") {
  const env = await getEnv();
  await env.withSecurityRulesDisabled(async (ctx) => {
    await ctx.storage().ref(path).putString(content);
  });
}

test("SEC-STORAGE-IDOR: User A cannot read User B private source photo", async () => {
  const path = "users/victim_uid/source/photo1.jpg";
  await seedBytes(path);
  const env = await getEnv();
  const attacker = env.authenticatedContext("attacker_uid").storage();
  await assertFails(attacker.ref(path).getDownloadURL());
});

test("SEC-STORAGE-IDOR: User A cannot upload into User B source path", async () => {
  const env = await getEnv();
  const attacker = env.authenticatedContext("attacker_uid").storage();
  await assertFails(
    attacker.ref("users/victim_uid/source/evil.jpg").putString("evil")
  );
});

test("SEC-STORAGE: private_source_photos path deny read/write for clients", async () => {
  const path = "private_source_photos/victim_uid/raw.jpg";
  await seedBytes(path);
  const env = await getEnv();
  const attacker = env.authenticatedContext("attacker_uid").storage();
  await assertFails(attacker.ref(path).getDownloadURL());
  await assertFails(attacker.ref(path).putString("x"));
});

test("SEC-STORAGE: avatar_temp deny read/write", async () => {
  const path = "avatar_temp/victim_uid/tmp.png";
  await seedBytes(path);
  const env = await getEnv();
  const user = env.authenticatedContext("victim_uid").storage();
  await assertFails(user.ref(path).getDownloadURL());
  await assertFails(user.ref(path).putString("x"));
});

test("SEC-STORAGE: client cannot write approved avatar even on own uid", async () => {
  const env = await getEnv();
  const user = env.authenticatedContext("victim_uid").storage();
  await assertFails(
    user.ref("users/victim_uid/avatar/av1.png").putString("x")
  );
});

test("SEC-STORAGE: path traversal style object names stay denied", async () => {
  const env = await getEnv();
  const user = env.authenticatedContext("attacker_uid").storage();
  await assertFails(
    user.ref("users/attacker_uid/source/../../victim_uid/source/x.jpg").putString("x")
  );
  await assertFails(
    user.ref("users/../private_source_photos/victim_uid/x.jpg").putString("x")
  );
});

test("SEC-STORAGE: unauthenticated cannot read private user paths", async () => {
  const path = "users/victim_uid/chat-profile/cp.jpg";
  await seedBytes(path);
  const env = await getEnv();
  const anon = env.unauthenticatedContext().storage();
  await assertFails(anon.ref(path).getDownloadURL());
});

test("SEC-STORAGE: catch-all denies arbitrary object writes", async () => {
  const env = await getEnv();
  const user = env.authenticatedContext("any_uid").storage();
  await assertFails(user.ref("random/path/file.bin").putString("x"));
});
