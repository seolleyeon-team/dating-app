/**
 * Client-supplied values used as ONE Firestore document id.
 *
 * `collection("users").doc(value)` resolves a value containing `/` as a nested
 * path: `"A/notifications/n1"` reads `users/A/notifications/n1`. A callable
 * that then answers differently for "exists" and "missing" becomes an
 * existence oracle for documents the caller may not read, and a callable that
 * writes creates documents at a path of the caller's choosing. A document id
 * can never contain `/`, so refusing it loses nothing.
 */
export function isSingleDocumentId(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    !value.includes("/") &&
    value !== "." &&
    value !== ".."
  );
}
