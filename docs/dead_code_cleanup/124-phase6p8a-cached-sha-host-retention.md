# Phase 6P-8A — cached SHA and host-retention status

## Read-only access results

| Surface | Status | Classification |
|---|---:|---|
| GitHub API blob endpoint at known old blob SHA | 200 | DIRECT_OLD_SHA_ACCESSIBLE |
| GitHub API commit endpoint at old first-changed SHA | 200 | DIRECT_OLD_SHA_ACCESSIBLE |
| Web commit view | 200 | CACHED_OR_WEB_VIEW_ACCESSIBLE_PARTIAL |
| Web blob view at old SHA/path | 404 | Not directly viewable in this probe |
| Raw URL at old SHA/path | 404 | Not directly viewable in this probe |

No blob or raw content was downloaded. A 200 response for an API object or commit view is not a claim that raw PII was read; it is a host-retention status signal only.

`SERVER_PHYSICAL_PURGE = NOT_YET_CONFIRMED`. Ordinary refs being clean does not establish provider-side garbage collection, cache invalidation, backup expiry, or removal from all internal retention layers. These are support questions, not actions taken in Phase 6P-8A.

See external `manifests/old-sha-access-status.json` and `manifests/cached-view-status.json`.

