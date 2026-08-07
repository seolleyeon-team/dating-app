# publicProfiles Backfill (EXTERNAL)

Deploy order for SEC-P0-USER-DOC-IDOR:

1. Deploy Functions including `onUserPublicProfileSync`.
2. Run Admin SDK backfill (below) against the target project (**staging first**).
3. Deploy tightened `firestore.rules` (`users` get = self only).
4. Ship client that reads `publicProfiles` for cross-user profiles.

## Dry-run backfill (Node Admin)

```js
// scripts/backfill_public_profiles.mjs — run with GOOGLE_APPLICATION_CREDENTIALS
import { initializeApp, applicationDefault } from "firebase-admin/app";
import { getFirestore } from "firebase-admin/firestore";
import { buildPublicProfileFromUser } from "../functions/lib/publicProfileSync.js";

initializeApp({ credential: applicationDefault() });
const db = getFirestore();
const dryRun = process.env.DRY_RUN !== "false";

let scanned = 0;
let upserts = 0;
let deletes = 0;
const snap = await db.collection("users").get();
for (const doc of snap.docs) {
  scanned += 1;
  const payload = buildPublicProfileFromUser(doc.id, doc.data());
  if (!payload) {
    deletes += 1;
    if (!dryRun) await db.collection("publicProfiles").doc(doc.id).delete();
    continue;
  }
  upserts += 1;
  if (!dryRun) {
    await db.collection("publicProfiles").doc(doc.id).set({
      ...payload,
      updatedAt: new Date(),
    });
  }
}
console.log({ dryRun, scanned, upserts, deletes });
```

Success criteria: every active visible user has `publicProfiles/{uid}`; withdrawn/banned have none.
Rollback: redeploy previous rules that allow signed-in `users` get (temporary only).
