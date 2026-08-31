import { X509Certificate } from "crypto";
import assert from "node:assert/strict";
import { test } from "node:test";
import { HttpsError } from "firebase-functions/v2/https";
import {
  appleAppAccountTokenForUserId,
  verifyApplePurchase,
} from "./applePurchaseVerification";
import { APPLE_ROOT_CERTIFICATES } from "./appleRootCertificates";

test("bundled Apple roots are valid G2/G3 certificates", () => {
  assert.equal(APPLE_ROOT_CERTIFICATES.length, 2);
  const subjects = APPLE_ROOT_CERTIFICATES.map(
    (certificate) => new X509Certificate(certificate).subject
  );
  assert.ok(subjects.some((subject) => subject.includes("Apple Root CA - G2")));
  assert.ok(subjects.some((subject) => subject.includes("Apple Root CA - G3")));
});

test("Apple verification rejects malformed signed transactions", async () => {
  await assert.rejects(
    verifyApplePurchase(
      {
        productId: "seolleyeon.heart.20",
        transactionId: "transaction-1",
        signedTransaction: "not-a-jws",
      },
      appleAppAccountTokenForUserId("user-1"),
      { bundleId: "com.seolleyeon.app", appAppleId: 94727223 }
    ),
    (error: unknown) =>
      error instanceof HttpsError && error.code === "failed-precondition"
  );
});
