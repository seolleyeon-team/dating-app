# Phase 6P-8A — affected PR map

## Result

Three visible PR heads are affected. All three PRs are closed and merged, so the applicable impact class is `AFFECTED_CLOSED_OR_MERGED_PR`; no open affected PR was observed.

| PR | State | Base | Head | Head classification | Merge-tree classification | Ordinary relation |
|---:|---|---|---|---|---|---|
| 51 | closed / merged | `main` | `kakao-message` | AFFECTED | AFFECTED_AT_MERGE_TREE | closed/merged PR |
| 52 | closed / merged | `main` | `audit/p0-authz-hardening` | AFFECTED | AFFECTED_AT_MERGE_TREE | closed/merged PR |
| 53 | closed / merged | `main` | `dowon0803` | AFFECTED | AFFECTED_AT_MERGE_TREE | closed/merged PR |

The head and merge SHA metadata, author login, timestamps, commit counts, changed-file counts, and exact SHA values are in the companion CSV and external machine-readable map. PR 53's merge object was not present in the local advertised ref fetch, but its API commit/tree metadata was available and its merge tree was independently classified as affected. It is therefore not unresolved.

The PR text/comment/review scan found zero exact matches for the target path, known blob SHA, old first-changed SHA, and email-like patterns in the scanned text. Attachment exposure remains `UNKNOWN`; no attachment was downloaded. Raw PR text and raw PII were not copied into evidence.

## Required consequence

No PR was closed, rebased, updated, commented on, or otherwise mutated. The support packet requests GitHub-side review of affected closed/merged PR refs and merge trees. Submission is deferred to Phase 6P-8B approval.

See `121-phase6p8a-affected-pr-map.csv` and the external `maps/affected-pr-map.csv`.

