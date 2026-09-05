import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import test from "node:test";

const GIF_1X1_BASE64 =
  "R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";

const FUNCTIONS_RUNTIME_ENTRYPOINT = "./lib/index.js";

test("the Functions runtime blocks the vulnerable GIF decoder", () => {
    const childScript = `
const sharp = require("sharp");
try {
  require(${JSON.stringify(FUNCTIONS_RUNTIME_ENTRYPOINT)});
} catch (error) {
  console.error("module import failed", error);
  process.exit(3);
}
const input = Buffer.from(${JSON.stringify(GIF_1X1_BASE64)}, "base64");
sharp(input).metadata().then(
  () => {
    console.error("vulnerable GIF decoder accepted attacker-controlled input");
    process.exit(2);
  },
  (error) => {
    const message = String(error?.message ?? error);
    if (!message.includes("unsupported image format")) {
      console.error("unexpected decoder failure", message);
      process.exit(4);
    }
  },
);
`;
    const result = spawnSync(process.execPath, ["-e", childScript], {
      cwd: resolve(__dirname, ".."),
      encoding: "utf8",
    });

    assert.equal(
      result.status,
      0,
      result.stderr || result.stdout || `child exited ${result.status}`,
    );
});
