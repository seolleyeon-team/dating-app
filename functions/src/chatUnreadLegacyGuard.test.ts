/**
 * P0-2 pre-launch closure: the per-message `readBy` receipt model is retired.
 * The runtime must neither write nor read it. The only place allowed to know
 * the legacy field is the one-time migration module (and tests/docs).
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import test from "node:test";

const SRC = join(__dirname, "..", "src");
const ALLOWED = new Set(["chatUnreadLegacyMigration.ts"]);

function runtimeSources(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...runtimeSources(full));
      continue;
    }
    if (!entry.endsWith(".ts") || entry.endsWith(".test.ts") || entry.endsWith("emulator-test.ts")) continue;
    if (ALLOWED.has(entry)) continue;
    out.push(full);
  }
  return out;
}

/** Code lines only: block/line comments may still describe the history. */
function codeLines(source: string): string[] {
  const lines: string[] = [];
  let inBlock = false;
  for (const raw of source.split("\n")) {
    const line = raw.trim();
    if (inBlock) {
      if (line.includes("*/")) inBlock = false;
      continue;
    }
    if (line.startsWith("/*")) {
      if (!line.includes("*/")) inBlock = true;
      continue;
    }
    if (line.startsWith("//") || line.startsWith("*")) continue;
    lines.push(raw);
  }
  return lines;
}

test("no runtime source writes or reads the legacy readBy field", () => {
  const offenders: string[] = [];
  for (const file of runtimeSources(SRC)) {
    codeLines(readFileSync(file, "utf8")).forEach((line, i) => {
      if (/\breadBy\b/.test(line)) offenders.push(`${relative(SRC, file)}:${i + 1}: ${line.trim()}`);
    });
  }
  assert.deepEqual(offenders, []);
});

test("the accounting module carries no legacy readBy rule", () => {
  const source = readFileSync(join(SRC, "chatUnread.ts"), "utf8");
  assert.equal(source.includes("legacyMessageIsUnreadFor"), false);
  assert.equal(/\breadBy\b/.test(codeLines(source).join("\n")), false);
});

test("the rules carry no general per-message receipt branch; only the NEW-18 transitional own-uid tolerance", () => {
  const rules = readFileSync(join(__dirname, "..", "..", "firestore.rules"), "utf8");
  assert.equal(rules.includes("onlyMessageReadReceiptUpdate"), false);
  assert.equal(rules.includes("request.resource.data.readBy is list"), false);
  // Transitional tolerance for installed old builds: must stay narrow
  // (exactly [own uid]) and must carry its retirement marker.
  assert.equal(rules.includes("function legacyReadByOnCreateTolerated()"), true);
  assert.equal(rules.includes("function legacyOwnReceiptAppend()"), true);
  assert.equal((rules.match(/request\.resource\.data\.readBy == \[request\.auth\.uid\]/g) ?? []).length, 2);
  assert.equal(rules.includes("before.get('readBy', []).concat([request.auth.uid])"), true);
  assert.ok(rules.includes("NEW-18"), "the transitional rule must name its retirement item");
});
