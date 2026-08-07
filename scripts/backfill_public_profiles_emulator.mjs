/**
 * Emulator dry-run / apply verification for publicProfiles backfill.
 * Never points at production: requires FIRESTORE_EMULATOR_HOST.
 *
 * Usage:
 *   firebase emulators:exec --only firestore --project seolleyeon-publicprofiles-migrate-test \
 *     "node scripts/backfill_public_profiles_emulator.mjs"
 *   APPLY=true ... (same command)
 */
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const functionsRequire = createRequire(
  resolve(here, "../functions/package.json"),
);
const { initializeApp } = functionsRequire("firebase-admin/app");
const { getFirestore } = functionsRequire("firebase-admin/firestore");
const { buildPublicProfileFromUser } = functionsRequire(
  "../functions/lib/publicProfileSync.js",
);

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  console.error("Refusing to run without FIRESTORE_EMULATOR_HOST");
  process.exit(2);
}

initializeApp({ projectId: "seolleyeon-publicprofiles-migrate-test" });
const db = getFirestore();
const apply = process.env.APPLY === "true";

const seeds = [
  {
    id: "active_1",
    data: {
      status: "active",
      profileVisible: true,
      isStudentVerified: true,
      nickname: "활성1",
      studentEmail: "a1@yonsei.ac.kr",
      preferenceVector: [0.1],
      loginDisabled: false,
      onboarding: { nickname: "활성1", major: "컴공", birthYear: "2003" },
      avatar: {
        status: "approved",
        approvedAvatarUrl: "https://cdn.example/a1.png",
      },
      profileImageUrl: "https://cdn.example/a1.png",
    },
  },
  {
    id: "active_2",
    data: {
      status: "active",
      profileVisible: true,
      isStudentVerified: true,
      nickname: "활성2",
      studentEmail: "a2@yonsei.ac.kr",
      onboarding: { nickname: "활성2", major: "경영", birthYear: "2002" },
    },
  },
  {
    id: "withdrawn_1",
    data: {
      status: "withdrawn",
      isWithdrawn: true,
      nickname: "탈퇴",
      studentEmail: "w@yonsei.ac.kr",
    },
  },
  {
    id: "hidden_1",
    data: {
      status: "active",
      profileVisible: false,
      nickname: "숨김",
      studentEmail: "h@yonsei.ac.kr",
    },
  },
];

for (const seed of seeds) {
  await db.collection("users").doc(seed.id).set(seed.data);
}

let scanned = 0;
let upserts = 0;
let deletes = 0;
const privateLeaks = [];

const snap = await db.collection("users").get();
for (const doc of snap.docs) {
  scanned += 1;
  const payload = buildPublicProfileFromUser(doc.id, doc.data());
  if (!payload) {
    deletes += 1;
    if (apply) await db.collection("publicProfiles").doc(doc.id).delete();
    continue;
  }
  for (const key of [
    "email",
    "studentEmail",
    "preferenceVector",
    "loginDisabled",
    "privacySettings",
    "legalConsents",
    "notificationSettings",
    "withdrawalReason",
  ]) {
    if (
      Object.prototype.hasOwnProperty.call(payload, key) &&
      payload[key] != null
    ) {
      privateLeaks.push({ uid: doc.id, key });
    }
  }
  upserts += 1;
  if (apply) {
    await db.collection("publicProfiles").doc(doc.id).set({
      ...payload,
      updatedAt: new Date(),
    });
  }
}

if (apply) {
  for (const seed of seeds) {
    const pub = await db.collection("publicProfiles").doc(seed.id).get();
    const shouldExist =
      seed.data.status === "active" && seed.data.profileVisible !== false;
    if (shouldExist && !pub.exists) {
      console.error("MISSING_PUBLIC_PROFILE", seed.id);
      process.exit(1);
    }
    if (!shouldExist && pub.exists) {
      console.error("UNEXPECTED_PUBLIC_PROFILE", seed.id);
      process.exit(1);
    }
    if (pub.exists) {
      const data = pub.data() ?? {};
      if (data.studentEmail || data.preferenceVector || data.loginDisabled) {
        console.error("PRIVATE_FIELD_LEAK", seed.id, Object.keys(data));
        process.exit(1);
      }
    }
  }
}

if (privateLeaks.length) {
  console.error("PRIVATE_FIELD_LEAKS", privateLeaks);
  process.exit(1);
}

console.log(
  JSON.stringify({
    dryRun: !apply,
    scanned,
    upserts,
    deletes,
    privateLeaks: privateLeaks.length,
    ok: true,
  }),
);
process.exit(0);
