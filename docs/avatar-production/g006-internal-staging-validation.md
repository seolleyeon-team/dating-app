# G006 Internal Staging Validation

Date: 2026-07-28

## Guard

| Check | Expected | Actual | Result |
| --- | --- | --- | --- |
| Account | `seolleyeon.official@gmail.com` | matched | pass |
| gcloud project | `seolleyeon-final` | matched | pass |
| Firebase active project | `seolleyeon-final` | matched | pass |
| Exact consent | 10+ exact rows | 10/10 matched, 0 missing, 0 unexpected | pass |
| Fresh unlocked eligibility | analyzer and account gate | 7 eligible, 3 low-quality blocked | partial |
| Callable App Check | valid internal token | 403 | block |

## Executed Staging Mutation

Only the user-approved selective staging deployment was attempted:

- `storage.rules`: compiled and released.
- `firestore.indexes.json`: deployed to the default Firestore database.
- Functions: not deployed.
- Worker: not redeployed; revision `seolleyeon-avatar-worker-00047-9qx` remains the
  validated staging worker.
- Production and source project `seolleyeon`: not touched.

Firebase CLI printed `Deploy complete`. Its final process status was nonzero because
local credential/update-check state could not be written and a reauthentication
warning was emitted. The successful release lines are retained as command evidence;
a separate CLI readback could not open the local gcloud credential database in the
restricted execution environment.

## Avatar Live Boundary

The exact-consent gate passed and local full-range detection accepted 7 of 10 rows.
No row was uploaded in G006 because App Check remained 403. No hard-blocked row was
forced, no QA threshold was bypassed, and no approved-avatar lock was reset.

The existing authenticated worker `/readyz=200`, unauthenticated `/readyz=403`,
small-face parity, release inventory, observability, and rollback evidence from G004
and G005 remains applicable to revision 00047.

## Privacy Result

- `qa_media_privacy.py --dry_run --fail_on_warning`: pass over 238 files.
- Exact runtime log scanner: zero findings.
- Functions response/rules tests: 120/120 pass.
- Evidence contains hashes/counts only; no UID rows, source paths, private GCS refs,
  signed URLs, raw landmarks, or embeddings.

## Next Authorized Validation

1. Repair or provision an authorized staging App Check token path without disabling
   enforcement.
2. Rerun the seven eligible rows and collect sanitized job, QA, timing, payload,
   approval, and lock evidence.
3. Rerun Flutter full tests after the external SDK lock is released.

Production ready remains false.