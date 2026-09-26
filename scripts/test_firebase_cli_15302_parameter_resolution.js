"use strict";

const path = require("node:path");
const { firebaseToolsRootFromPath } = require("./firebase_cli_package");

const EXPECTED_FIREBASE_TOOLS_VERSION = "15.30.2";
const PARAMETER_NAMES = [
  "APPLE_IAP_APPLE_ID",
  "APPLE_IAP_BUNDLE_ID",
  "RESEND_FROM_EMAIL",
  "RESEND_REPLY_TO",
];

async function main() {
  const cliRoot = firebaseToolsRootFromPath(EXPECTED_FIREBASE_TOOLS_VERSION);
  const { resolveParams } = require(path.join(
    cliRoot,
    "lib/deploy/functions/params.js",
  ));
  const prompt = require(path.join(cliRoot, "lib/prompt.js"));
  let sourceDefaultPromptReached = false;
  prompt.input = async () => {
    sourceDefaultPromptReached = true;
    throw new Error("SOURCE_DEFAULT_PROMPT_REACHED");
  };

  const parameters = PARAMETER_NAMES.map((name) => ({
    name,
    type: "string",
    default: `synthetic-default-${name}`,
    input: { text: {} },
  }));
  const commonOptions = {
    params: parameters,
    firebaseConfig: { projectId: "p1-4-synthetic-project" },
    codebase: "p1-4-synthetic-codebase",
    nonInteractive: true,
    isEmulator: true,
  };

  let missingParameterBlocked = false;
  try {
    await resolveParams({
      ...commonOptions,
      userEnvs: {
        APPLE_IAP_BUNDLE_ID: "synthetic-bundle-id",
        RESEND_FROM_EMAIL: "synthetic-sender@example.invalid",
        RESEND_REPLY_TO: "synthetic-reply@example.invalid",
      },
    });
  } catch (error) {
    missingParameterBlocked =
      /non-interactive mode/i.test(String(error.message)) &&
      String(error.message).includes("APPLE_IAP_APPLE_ID");
  }
  if (!missingParameterBlocked || sourceDefaultPromptReached) {
    throw new Error("missing parameter did not fail before the source-default prompt");
  }

  sourceDefaultPromptReached = false;
  const complete = {
    APPLE_IAP_APPLE_ID: "synthetic-apple-id",
    APPLE_IAP_BUNDLE_ID: "synthetic-bundle-id",
    RESEND_FROM_EMAIL: "synthetic-sender@example.invalid",
    RESEND_REPLY_TO: "synthetic-reply@example.invalid",
  };
  const resolved = await resolveParams({
    ...commonOptions,
    userEnvs: complete,
  });
  if (
    sourceDefaultPromptReached ||
    PARAMETER_NAMES.some((name) => !Object.hasOwn(resolved.paramValues, name))
  ) {
    throw new Error("complete candidate did not resolve all non-secret parameters");
  }
  process.stdout.write(
    "PINNED_FIREBASE_CLI_PARAMETER_RESOLUTION_PASS\n",
    () => process.exit(0),
  );
}

main().catch((error) => {
  process.stderr.write(`${error.name}: ${error.message}\n`);
  process.exit(1);
});
