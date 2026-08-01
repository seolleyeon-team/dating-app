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

export const PROJECT_ID = "seolleyeon-rules-test";

let testEnvPromise = null;

export function getTestEnv() {
  if (!testEnvPromise) {
    testEnvPromise = initializeTestEnvironment({
      projectId: PROJECT_ID,
      firestore: {
        rules: readFileSync(resolve(repoRoot, "firestore.rules"), "utf8"),
        host: "127.0.0.1",
        port: 8080,
      },
    });
  }
  return testEnvPromise;
}

export async function withClearedDb(seed) {
  const env = await getTestEnv();
  await env.clearFirestore();
  if (seed) {
    await env.withSecurityRulesDisabled((ctx) => seed(ctx.firestore()));
  }
  return env;
}

/** Unauthenticated client, as an attacker hitting the REST/SDK API directly. */
export async function anon() {
  const env = await getTestEnv();
  return env.unauthenticatedContext().firestore();
}

/**
 * Kakao-bridged app session: uid is the Kakao user id, no email claim.
 * This is what `createFirebaseCustomToken` mints.
 */
export async function kakaoSession(uid) {
  const env = await getTestEnv();
  return env.authenticatedContext(uid, { kakaoUserId: uid }).firestore();
}

/**
 * Email-link browser session: a distinct Firebase uid carrying a verified
 * Yonsei email claim. This is what `public/index.html` runs as.
 */
export async function emailLinkSession(uid, email) {
  const env = await getTestEnv();
  return env
    .authenticatedContext(uid, { email, email_verified: true })
    .firestore();
}

export { assertFails, assertSucceeds };
