"use strict";

const fs = require("node:fs");
const path = require("node:path");

function firebaseToolsRootFromPath(expectedVersion) {
  const pathEntries = (process.env.PATH || "").split(path.delimiter);
  for (const entry of pathEntries) {
    if (!entry) continue;
    const candidate = path.resolve(entry, "..", "firebase-tools");
    const packageJson = path.join(candidate, "package.json");
    if (!fs.existsSync(packageJson)) continue;

    let metadata;
    try {
      metadata = JSON.parse(fs.readFileSync(packageJson, "utf8"));
    } catch {
      continue;
    }
    if (metadata.version !== expectedVersion) {
      throw new Error("NPM_EXEC_FIREBASE_CLI_VERSION_MISMATCH");
    }
    return candidate;
  }
  throw new Error("NPM_EXEC_PINNED_FIREBASE_CLI_NOT_ON_PATH");
}

module.exports = { firebaseToolsRootFromPath };
