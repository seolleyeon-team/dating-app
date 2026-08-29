import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRecommendationExclusionPairId,
  fetchKakaoFriendServiceUserIds,
  hasActiveRecommendationExclusion,
  isKakaoFriendAvoidanceEnabled,
} from "./kakaoFriendRecommendationPrivacy";

function jsonResponse(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

test("pair id is stable regardless of caller direction", () => {
  assert.equal(
    buildRecommendationExclusionPairId("200", "100"),
    "100_200",
  );
  assert.equal(
    buildRecommendationExclusionPairId("100", "200"),
    "100_200",
  );
});

test("an exclusion is active when either participant enabled it", () => {
  assert.equal(hasActiveRecommendationExclusion(undefined), false);
  assert.equal(hasActiveRecommendationExclusion({ enabledBy: {} }), false);
  assert.equal(
    hasActiveRecommendationExclusion({ enabledBy: { a: false, b: true } }),
    true,
  );
});

test("avoidance preference is strict boolean true", () => {
  assert.equal(isKakaoFriendAvoidanceEnabled(undefined), false);
  assert.equal(
    isKakaoFriendAvoidanceEnabled({ kakaoFriendAvoidanceEnabled: "true" }),
    false,
  );
  assert.equal(
    isKakaoFriendAvoidanceEnabled({ kakaoFriendAvoidanceEnabled: true }),
    true,
  );
});

test("server fetches and deduplicates every Kakao friends page", async () => {
  const requested: string[] = [];
  const ids = await fetchKakaoFriendServiceUserIds(
    "secret-token",
    async (input, init) => {
      requested.push(String(input));
      assert.equal(init?.headers && (init.headers as Record<string, string>).Authorization,
        "Bearer secret-token");
      if (requested.length === 1) {
        return jsonResponse({
          elements: [{ id: 10, nickname: "ignored" }, { id: "20" }],
          after_url: "https://kapi.kakao.com/v1/api/talk/friends?offset=2&limit=100",
        });
      }
      return jsonResponse({ elements: [{ id: 20 }, { id: 30 }] });
    },
  );

  assert.deepEqual(ids, ["10", "20", "30"]);
  assert.equal(requested.length, 2);
});

test("pagination cannot leave the official Kakao friends endpoint", async () => {
  await assert.rejects(
    fetchKakaoFriendServiceUserIds("token", async () =>
      jsonResponse({
        elements: [{ id: 10 }],
        after_url: "https://attacker.example/steal",
      }),
    ),
    /unsafe_kakao_friends_pagination_url/,
  );
});
