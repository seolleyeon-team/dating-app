import assert from "node:assert/strict";
import test from "node:test";

import { isUnregisteredPushTokenError } from "./index";

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
