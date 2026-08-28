import assert from "node:assert/strict";
import test from "node:test";

import {
  isRestricted,
  loadBlockedUserIds,
  loadRecentlyMetUserIds,
} from "./store";

/**
 * 차단/제재/최근-만남 조회가 Firestore 오류를 삼키지 않고 전파하는지(fail-closed)
 * 검증한다. 오류 주입은 database seam 으로 한다.
 */

class InjectedFirestoreError extends Error {}

function throwingDb(): any {
  const thrower = () => {
    throw new InjectedFirestoreError("firestore down");
  };
  // collection().doc().collection().get() / collection().doc().get() 등
  // 어떤 체인에서도 결국 get()이 던지도록 프록시로 감싼다.
  const handler: ProxyHandler<any> = {
    get(_target, prop) {
      if (prop === "get" || prop === "where") {
        return () =>
          prop === "get"
            ? Promise.reject(new InjectedFirestoreError("firestore down"))
            : proxy;
      }
      return () => proxy;
    },
  };
  const proxy: any = new Proxy(thrower, handler);
  return proxy;
}

test("loadBlockedUserIds propagates Firestore errors (no fail-open empty list)", async () => {
  await assert.rejects(
    () => loadBlockedUserIds("u1", throwingDb()),
    InjectedFirestoreError
  );
});

test("isRestricted propagates Firestore errors (no fail-open false)", async () => {
  await assert.rejects(
    () => isRestricted("u1", throwingDb()),
    InjectedFirestoreError
  );
});

test("loadRecentlyMetUserIds propagates Firestore errors", async () => {
  await assert.rejects(
    () => loadRecentlyMetUserIds("u1", 1000, throwingDb()),
    InjectedFirestoreError
  );
});
