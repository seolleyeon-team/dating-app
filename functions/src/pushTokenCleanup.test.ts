import assert from "node:assert/strict";
import test from "node:test";

import { classifyPushSendFailures, isUnregisteredPushTokenError } from "./shared/notify";

test("only permanently dead tokens are dropped", () => {
  assert.equal(
    isUnregisteredPushTokenError("messaging/registration-token-not-registered"),
    true
  );
  assert.equal(
    isUnregisteredPushTokenError("messaging/invalid-registration-token"),
    true
  );
});

test("transient failures never unregister a working device", () => {
  // Dropping a token on any of these would silently end push delivery for a
  // user whose device is fine, with nothing in the app to signal it.
  for (const code of [
    "messaging/internal-error",
    "messaging/server-unavailable",
    "messaging/quota-exceeded",
    "messaging/message-rate-exceeded",
    "messaging/unavailable",
    "messaging/third-party-auth-error",
    "messaging/authentication-error",
  ]) {
    assert.equal(
      isUnregisteredPushTokenError(code),
      false,
      `${code} must not drop the token`
    );
  }
});

test("an unknown or absent error code is not treated as a dead token", () => {
  assert.equal(isUnregisteredPushTokenError(null), false);
  assert.equal(isUnregisteredPushTokenError(""), false);
  assert.equal(isUnregisteredPushTokenError("something/new"), false);
});

test("a multicast failure drops only the tokens FCM reports as dead", () => {
  const failures = classifyPushSendFailures(
    ["alive", "dead", "apns-outage", "throttled"],
    [
      { success: true },
      { success: false, error: { code: "messaging/registration-token-not-registered" } },
      { success: false, error: { code: "messaging/third-party-auth-error" } },
      { success: false, error: { code: "messaging/internal-error" } },
    ]
  );

  assert.deepEqual(
    failures.map((failure) => [failure.token, failure.permanent]),
    [
      ["dead", true],
      ["apns-outage", false],
      ["throttled", false],
    ]
  );
});

test("a failure without an error code is not treated as a dead token", () => {
  assert.deepEqual(classifyPushSendFailures(["t"], [{ success: false }]), [
    { token: "t", errorCode: null, permanent: false },
  ]);
});
