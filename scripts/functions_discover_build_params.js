"use strict";

const path = require("node:path");
const { firebaseToolsRootFromPath } = require("./firebase_cli_package");

function parseArgs(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (!["--functions-dir", "--project", "--region", "--runtime", "--firebase-cli-version"].includes(key)) {
      throw new Error("DISCOVERY_ARGUMENT_REFUSED");
    }
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) {
      throw new Error("DISCOVERY_ARGUMENT_VALUE_REQUIRED");
    }
    options[key.slice(2)] = value;
    index += 1;
  }
  for (const key of ["functions-dir", "project", "region", "runtime", "firebase-cli-version"]) {
    if (!options[key]) throw new Error("DISCOVERY_ARGUMENT_REQUIRED");
  }
  return options;
}

function safeParameterMetadata(parameter) {
  if (!parameter || typeof parameter !== "object") {
    throw new Error("DISCOVERED_PARAMETER_SHAPE_INVALID");
  }
  if (typeof parameter.name !== "string" || typeof parameter.type !== "string") {
    throw new Error("DISCOVERED_PARAMETER_IDENTITY_INVALID");
  }

  const metadata = { name: parameter.name, type: parameter.type };
  if (parameter.type.toLowerCase() !== "secret") {
    for (const property of ["default", "input", "label", "description", "descriptionLink", "immutable", "options", "delimiter"]) {
      if (Object.hasOwn(parameter, property)) metadata[property] = parameter[property];
    }
  }
  return metadata;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const cliRoot = firebaseToolsRootFromPath(options["firebase-cli-version"]);
  const functionsDir = path.resolve(options["functions-dir"]);
  const loaderPath = path.join(
    functionsDir,
    "node_modules",
    "firebase-functions",
    "lib/runtime/loader.js",
  );
  const { loadStack } = require(loaderPath);
  const { yamlToBuild } = require(path.join(
    cliRoot,
    "lib/deploy/functions/runtimes/discovery/index.js",
  ));

  const runtimeStack = await loadStack(functionsDir);
  const build = yamlToBuild(
    runtimeStack,
    options.project,
    options.region,
    options.runtime,
  );
  if (!build || !Array.isArray(build.params)) {
    throw new Error("DISCOVERED_BUILD_PARAMETER_LIST_MISSING");
  }
  const parameters = build.params.map(safeParameterMetadata);
  const secretParameterCount = parameters.filter(
    (parameter) => parameter.type.toLowerCase() === "secret",
  ).length;
  const output = `${JSON.stringify({
      contractVersion: 1,
      firebaseToolsVersion: options["firebase-cli-version"],
      parameterCount: parameters.length,
      secretParameterCount,
      parameters,
    })}\n`;
  process.stdout.write(output, () => process.exit(0));
}

main().catch((error) => {
  const safeName = typeof error?.name === "string" ? error.name : "Error";
  process.stderr.write(`FUNCTIONS_PARAMETER_DISCOVERY_FAILED: ${safeName}\n`);
  process.exit(1);
});
