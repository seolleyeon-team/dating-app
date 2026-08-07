/**
 * Read-only audit for onboarding records whose interests may have been lost.
 *
 * The script never writes, updates, or deletes Firestore data. It refuses to
 * connect to a non-emulator unless the caller explicitly opts into a
 * production read with --allow-production-read and an explicit service-account
 * credential path.
 *
 * Emulator usage:
 *   firebase emulators:exec --only firestore \
 *     --project seolleyeon-onboarding-audit-test \
 *     "node scripts/audit_onboarding_interests.mjs --project seolleyeon-onboarding-audit-test"
 *
 * Explicit production read-only usage:
 *   node scripts/audit_onboarding_interests.mjs \
 *     --project seolleyeon-final \
 *     --credentials C:\\path\\service-account.json \
 *     --allow-production-read
 */
import { createRequire } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

function parsePositiveInteger(value, optionName, { allowZero = false } = {}) {
  const parsed = Number(value);
  const minimum = allowZero ? 0 : 1;
  if (!Number.isInteger(parsed) || parsed < minimum) {
    throw new Error(`${optionName} must be an integer >= ${minimum}`);
  }
  return parsed;
}

export function parseArgs(argv, env = process.env) {
  const options = {
    projectId: "",
    credentialsPath: env.GOOGLE_APPLICATION_CREDENTIALS ?? "",
    allowProductionRead: false,
    pageSize: 100,
    pageDelayMs: 50,
    maxRetries: 3,
    help: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--help" || argument === "-h") {
      options.help = true;
      continue;
    }
    if (argument === "--allow-production-read") {
      options.allowProductionRead = true;
      continue;
    }
    if (
      argument === "--project" ||
      argument === "--credentials" ||
      argument === "--page-size" ||
      argument === "--page-delay-ms" ||
      argument === "--max-retries"
    ) {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) {
        throw new Error(`${argument} requires a value`);
      }
      if (argument === "--project") options.projectId = value;
      if (argument === "--credentials") options.credentialsPath = value;
      if (argument === "--page-size") {
        options.pageSize = parsePositiveInteger(value, "--page-size");
      }
      if (argument === "--page-delay-ms") {
        options.pageDelayMs = parsePositiveInteger(value, "--page-delay-ms", {
          allowZero: true,
        });
      }
      if (argument === "--max-retries") {
        options.maxRetries = parsePositiveInteger(value, "--max-retries");
      }
      index += 1;
      continue;
    }
    throw new Error(`Unknown argument: ${argument}`);
  }

  return options;
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function classifyUserDocument(data) {
  const user = isRecord(data) ? data : {};
  const onboarding = isRecord(user.onboarding) ? user.onboarding : {};
  const hasKeywords = Object.prototype.hasOwnProperty.call(
    onboarding,
    "keywords",
  );
  const onboardingCompleted = user.initialSetupComplete === true;
  const candidate = hasKeywords || onboardingCompleted;
  const hasInterestsField = Object.prototype.hasOwnProperty.call(
    onboarding,
    "interests",
  );
  const interests = onboarding.interests;
  const missingInterests = !hasInterestsField || interests == null;
  const emptyInterests = Array.isArray(interests) && interests.length === 0;
  const invalidInterests =
    hasInterestsField && !missingInterests && !Array.isArray(interests);

  return {
    hasKeywords,
    onboardingCompleted,
    candidate,
    missingInterests,
    emptyInterests,
    invalidInterests,
    affected:
      candidate &&
      (missingInterests || emptyInterests || invalidInterests),
  };
}

function errorCategory(error) {
  const code = typeof error?.code === "string" ? error.code : "";
  if (code) return code.replace(/[^A-Za-z0-9_-]/g, "_").slice(0, 48);
  const name = typeof error?.name === "string" ? error.name : "";
  if (name) return name.replace(/[^A-Za-z0-9_-]/g, "_").slice(0, 48);
  return "unknown";
}

function isRetryable(error) {
  const code = typeof error?.code === "string" ? error.code : "";
  return new Set([
    "aborted",
    "deadline-exceeded",
    "internal",
    "resource-exhausted",
    "unavailable",
  ]).has(code) || Number(error?.status) >= 500;
}

function sleep(milliseconds) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, milliseconds));
}

async function readPageWithRetry(query, options, summary) {
  for (let attempt = 0; attempt < options.maxRetries; attempt += 1) {
    try {
      return await query.get();
    } catch (error) {
      if (!isRetryable(error) || attempt + 1 >= options.maxRetries) {
        summary.errorCount += 1;
        const category = errorCategory(error);
        summary.errorCategories[category] =
          (summary.errorCategories[category] ?? 0) + 1;
        return null;
      }
      summary.retryCount += 1;
      await options.sleep(
        Math.min(1000, 100 * 2 ** attempt),
      );
    }
  }
  return null;
}

function createSummary() {
  return {
    complete: true,
    totalUsersScanned: 0,
    candidateUsers: 0,
    affectedUsers: 0,
    missingInterests: 0,
    emptyInterests: 0,
    invalidInterests: 0,
    hasKeywords: 0,
    onboardingCompleted: 0,
    pageCount: 0,
    retryCount: 0,
    errorCount: 0,
    errorCategories: {},
  };
}

export async function auditUsers(
  db,
  {
    pageSize = 100,
    pageDelayMs = 50,
    maxRetries = 3,
    sleep: sleepFn = sleep,
    documentIdField = "__name__",
  } = {},
) {
  const summary = createSummary();
  const collection = db.collection("users");
  let lastDocumentId = null;

  while (true) {
    if (summary.pageCount > 0 && pageDelayMs > 0) {
      await sleepFn(pageDelayMs);
    }

    let query = collection
      .select("onboarding", "initialSetupComplete")
      .orderBy(documentIdField)
      .limit(pageSize);
    if (lastDocumentId !== null) {
      query = query.startAfter(lastDocumentId);
    }

    const snapshot = await readPageWithRetry(
      query,
      { maxRetries, sleep: sleepFn },
      summary,
    );
    if (snapshot === null) {
      summary.complete = false;
      break;
    }

    const documents = Array.isArray(snapshot.docs) ? snapshot.docs : [];
    summary.pageCount += 1;
    for (const document of documents) {
      summary.totalUsersScanned += 1;
      const result = classifyUserDocument(document.data());
      if (result.hasKeywords) summary.hasKeywords += 1;
      if (result.onboardingCompleted) summary.onboardingCompleted += 1;
      if (!result.candidate) continue;

      summary.candidateUsers += 1;
      if (result.affected) summary.affectedUsers += 1;
      if (result.missingInterests) summary.missingInterests += 1;
      if (result.emptyInterests) summary.emptyInterests += 1;
      if (result.invalidInterests) summary.invalidInterests += 1;
    }

    if (documents.length < pageSize) break;
    const nextDocumentId = documents.at(-1)?.id;
    if (!nextDocumentId || nextDocumentId === lastDocumentId) {
      summary.complete = false;
      summary.errorCount += 1;
      summary.errorCategories.pagination = 1;
      break;
    }
    lastDocumentId = nextDocumentId;
  }

  return summary;
}

export function usage() {
  return [
    "Read-only onboarding interests audit",
    "",
    "Emulator:",
    "  firebase emulators:exec --only firestore --project seolleyeon-onboarding-audit-test \\",
    "    \"node scripts/audit_onboarding_interests.mjs --project seolleyeon-onboarding-audit-test\"",
    "",
    "Production read-only (explicit opt-in and explicit Admin credential):",
    "  node scripts/audit_onboarding_interests.mjs --project seolleyeon-final \\",
    "    --credentials C:\\path\\service-account.json --allow-production-read",
    "",
    "Options: --page-size N --page-delay-ms N --max-retries N",
  ].join("\n");
}

function loadServiceAccount(credentialsPath) {
  if (!credentialsPath || !existsSync(credentialsPath)) {
    throw new Error(
      "Production reads require --credentials or GOOGLE_APPLICATION_CREDENTIALS pointing to an existing service-account file.",
    );
  }
  try {
    return JSON.parse(readFileSync(credentialsPath, "utf8"));
  } catch {
    throw new Error("The explicit Admin credential file is not valid JSON.");
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    console.log(usage());
    return;
  }

  const emulatorHost = process.env.FIRESTORE_EMULATOR_HOST;
  const usingEmulator = Boolean(emulatorHost);
  if (!options.projectId) {
    throw new Error("A project id is required. Pass --project.");
  }
  if (!usingEmulator && !options.allowProductionRead) {
    throw new Error(
      "Refusing non-emulator access. Use FIRESTORE_EMULATOR_HOST or explicitly pass --allow-production-read.",
    );
  }

  const functionsRequire = createRequire(resolve(here, "../functions/package.json"));
  const { cert, getApp, getApps, initializeApp } = functionsRequire(
    "firebase-admin/app",
  );
  const { FieldPath, getFirestore } = functionsRequire(
    "firebase-admin/firestore",
  );

  const app = getApps().length
    ? getApp()
    : initializeApp({
        projectId: options.projectId,
        ...(usingEmulator
          ? {}
          : { credential: cert(loadServiceAccount(options.credentialsPath)) }),
      });
  const db = getFirestore(app);
  const summary = await auditUsers(db, {
    pageSize: options.pageSize,
    pageDelayMs: options.pageDelayMs,
    maxRetries: options.maxRetries,
    documentIdField: FieldPath.documentId(),
  });

  console.log(
    JSON.stringify(
      {
        mode: "dry-run",
        readOnly: true,
        emulator: usingEmulator,
        projectId: options.projectId,
        ...summary,
      },
      null,
      2,
    ),
  );
  if (!summary.complete) process.exitCode = 1;
}

const isMain =
  process.argv[1] &&
  resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url));
if (isMain) {
  main().catch((error) => {
    console.error(
      `Audit failed: ${error instanceof Error ? error.message : "unknown"}`,
    );
    process.exitCode = 1;
  });
}
