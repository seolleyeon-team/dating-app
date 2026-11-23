/**
 * B-10 — Kakao access tokens are bound to the Seolleyeon Kakao app.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import {
  KAKAO_ACCESS_TOKEN_INFO_URL,
  KAKAO_USER_ME_URL,
  configuredKakaoAppId,
  normalizeKakaoAppId,
  verifyKakaoAccessTokenForApp,
} from "./kakaoAccessTokenVerification";

const TRUSTED_APP_ID = "1234567";
const TOKEN = "kakao-access-token-under-test";

type Call = { url: string; authorization: string | null };

function kakao(responses: {
  tokenInfo?: { status?: number; body?: unknown; throws?: boolean };
  me?: { status?: number; body?: unknown };
}) {
  const calls: Call[] = [];
  const fetchImpl = (async (input: unknown, init?: { headers?: Record<string, string> }) => {
    const url = String(input);
    calls.push({ url, authorization: init?.headers?.Authorization ?? null });
    const spec = url === KAKAO_ACCESS_TOKEN_INFO_URL ? responses.tokenInfo : url === KAKAO_USER_ME_URL ? responses.me : undefined;
    if (!spec) throw new Error(`unexpected url ${url}`);
    if ((spec as { throws?: boolean }).throws) throw new TypeError("network down");
    const status = spec.status ?? 200;
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => {
        if (spec.body === undefined) throw new SyntaxError("no body");
        return spec.body;
      },
    };
  }) as unknown as typeof fetch;
  return { fetchImpl, calls };
}

async function refusal(promise: Promise<unknown>): Promise<string> {
  try {
    await promise;
  } catch (error) {
    return String((error as { code?: string }).code);
  }
  return "ok";
}

const verify = (fetchImpl: typeof fetch, trustedAppId: string | null = TRUSTED_APP_ID) =>
  verifyKakaoAccessTokenForApp(TOKEN, { fetchImpl, trustedAppId: () => trustedAppId });

test("a token issued for the Seolleyeon app is accepted", async () => {
  const { fetchImpl, calls } = kakao({
    tokenInfo: { body: { id: 987654321, expires_in: 7199, app_id: 1234567 } },
    me: { body: { id: 987654321, kakao_account: {} } },
  });
  assert.deepEqual(await verify(fetchImpl), { userId: "987654321" });
  // token info first, then the profile; the token only ever goes to Kakao.
  assert.deepEqual(calls.map((c) => c.url), [KAKAO_ACCESS_TOKEN_INFO_URL, KAKAO_USER_ME_URL]);
  assert.ok(calls.every((c) => c.authorization === `Bearer ${TOKEN}`));
});

test("a token issued for another Kakao app is refused before the profile is read", async () => {
  const { fetchImpl, calls } = kakao({
    tokenInfo: { body: { id: 42, expires_in: 7199, app_id: 7654321 } },
    // The profile endpoint would happily answer for the foreign token.
    me: { body: { id: 42 } },
  });
  assert.equal(await refusal(verify(fetchImpl)), "unauthenticated");
  assert.deepEqual(calls.map((c) => c.url), [KAKAO_ACCESS_TOKEN_INFO_URL]);
});

test("a token-info failure is refused (HTTP error, network error, unreadable body, missing app_id)", async () => {
  const me = { body: { id: 42 } };
  for (const tokenInfo of [
    { status: 401, body: { msg: "this access token does not exist", code: -401 } },
    { status: 500, body: {} },
    { throws: true },
    { status: 200 },
    { status: 200, body: [] },
    { status: 200, body: { id: 42, expires_in: 10 } },
    { status: 200, body: { id: 42, app_id: "not-a-number" } },
    { status: 200, body: { id: 42, app_id: 0 } },
  ]) {
    const { fetchImpl, calls } = kakao({ tokenInfo, me });
    assert.equal(await refusal(verify(fetchImpl)), "unauthenticated", JSON.stringify(tokenInfo));
    assert.equal(calls.some((c) => c.url === KAKAO_USER_ME_URL), false, "profile must not be read");
  }
});

test("a missing or malformed configured app id fails closed without contacting Kakao", async () => {
  for (const configured of [null, "", "   ", "abc", "12 34", "-5", "0", "cb08e2aea50a58b7d0c5e610e0c5a644"]) {
    const { fetchImpl, calls } = kakao({
      tokenInfo: { body: { id: 42, app_id: 1234567 } },
      me: { body: { id: 42 } },
    });
    assert.equal(await refusal(verify(fetchImpl, configured)), "failed-precondition", JSON.stringify(configured));
    assert.equal(calls.length, 0, "the token must not leave the process when the app id is not configured");
  }
});

test("the app id comes from KAKAO_APP_ID and nowhere else", async () => {
  const previous = process.env.KAKAO_APP_ID;
  try {
    delete process.env.KAKAO_APP_ID;
    assert.equal(configuredKakaoAppId(), null);
    const { fetchImpl, calls } = kakao({ tokenInfo: { body: { id: 42, app_id: 1234567 } }, me: { body: { id: 42 } } });
    assert.equal(await refusal(verifyKakaoAccessTokenForApp(TOKEN, { fetchImpl })), "failed-precondition");
    assert.equal(calls.length, 0);

    process.env.KAKAO_APP_ID = " 1234567 ";
    assert.equal(configuredKakaoAppId(), "1234567");
    assert.deepEqual(await verifyKakaoAccessTokenForApp(TOKEN, { fetchImpl }), { userId: "42" });
  } finally {
    if (previous === undefined) delete process.env.KAKAO_APP_ID;
    else process.env.KAKAO_APP_ID = previous;
  }
});

test("the member number must agree between token info and profile", async () => {
  const mismatch = kakao({ tokenInfo: { body: { id: 42, app_id: 1234567 } }, me: { body: { id: 43 } } });
  assert.equal(await refusal(verify(mismatch.fetchImpl)), "unauthenticated");
  const noTokenMember = kakao({ tokenInfo: { body: { app_id: 1234567 } }, me: { body: { id: 43 } } });
  assert.equal(await refusal(verify(noTokenMember.fetchImpl)), "unauthenticated");
  const profileDown = kakao({ tokenInfo: { body: { id: 42, app_id: 1234567 } }, me: { status: 401, body: {} } });
  assert.equal(await refusal(verify(profileDown.fetchImpl)), "unauthenticated");
  const noProfileId = kakao({ tokenInfo: { body: { id: 42, app_id: 1234567 } }, me: { body: {} } });
  assert.equal(await refusal(verify(noProfileId.fetchImpl)), "unauthenticated");
});

test("app ids are compared as exact decimal strings", () => {
  assert.equal(normalizeKakaoAppId(1234567), "1234567");
  assert.equal(normalizeKakaoAppId("1234567"), "1234567");
  assert.equal(normalizeKakaoAppId("01234567"), null);
  assert.equal(normalizeKakaoAppId(1234567.5), null);
  assert.equal(normalizeKakaoAppId("1234567abc"), null);
  assert.equal(normalizeKakaoAppId(undefined), null);
});

test("every Kakao-token consumer in index.ts goes through the bound verifier; no token is logged", () => {
  const indexSource = readFileSync(resolve(__dirname, "../src/index.ts"), "utf8");
  const start = indexSource.indexOf("async function verifyKakaoAccessToken(");
  assert.notEqual(start, -1);
  const body = indexSource.slice(start, indexSource.indexOf("\n}\n", start));
  assert.match(body, /return verifyKakaoAccessTokenForApp\(accessToken\);/);
  assert.doesNotMatch(body, /fetch\(/, "index.ts must not verify a Kakao token on its own");
  assert.doesNotMatch(indexSource, /kapi\.kakao\.com\/v2\/user\/me/, "no second, unbound profile lookup");

  const moduleSource = readFileSync(resolve(__dirname, "../src/kakaoAccessTokenVerification.ts"), "utf8");
  for (const call of moduleSource.match(/logger\.(warn|error|info)\([\s\S]*?\}\);/g) ?? []) {
    assert.doesNotMatch(call, /accessToken|Authorization|tokenInfo\.|profile\./, "a log line must not carry the token or Kakao's answer");
  }
});
