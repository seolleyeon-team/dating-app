import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const indexSrc = readFileSync(resolve(__dirname, "../src/index.ts"), "utf8");

test("adult verification requires Korean year age 20 or older", () => {
  assert.match(indexSrc, /const MINIMUM_SERVICE_AGE = 20;/);
  assert.match(
    indexSrc,
    /return getKstFullYear\(now\) - birthYear >= MINIMUM_SERVICE_AGE;/
  );
});

test("real-name verification data is stored in a server-only collection", () => {
  assert.match(indexSrc, /collection\("userPrivateVerifications"\)/);
  assert.match(indexSrc, /name,\s*\n\s*phoneNumber,\s*\n\s*birthDate,/);
});
