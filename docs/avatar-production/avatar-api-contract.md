> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** The current Azure-only, source-set architecture is defined in [avatar-production/CURRENT_ARCHITECTURE.md](CURRENT_ARCHITECTURE.md).
>

# Avatar API Contract

Version: `avatar_api_v2`

All callables require Firebase Auth. Production and `production_bridge` also
require valid App Check. Requests and responses must never contain private
storage references, signed URLs, private collection snapshots, raw landmarks,
or embeddings.

## `uploadAvatarSourcePhoto`

Request:

```json
{
  "imageBase64": "<runtime bytes>",
  "contentType": "image/jpeg|image/png|image/webp",
  "clientRequestId": "safe idempotency id",
  "consentVersion": "versioned source and recommendation consent"
}
```

The callable normalizes the image, then atomically claims an unlocked user. It
creates one private source and one current job. A second or concurrent upload
creates no object/job/task. A partial private state fails closed.

Safe response:

```json
{
  "photoId": "opaque id",
  "jobId": "opaque id",
  "avatarStatus": "queued",
  "sourceLocked": true,
  "sourceSelectionVersion": 1,
  "queueStatus": "enqueued"
}
```

## `getCurrentAvatarGenerationStatus`

Request: no user-supplied UID and no private reference.

Safe response:

```json
{
  "sourceLocked": true,
  "jobId": "opaque current id or null",
  "sourceSelectionVersion": 1,
  "status": "queued|running|qa_pending|preview_ready|needs_review|no_previewable_candidates|retryable_failed|terminal_failed|approved",
  "candidateAvailability": "none|preview_safe",
  "retryAllowed": false,
  "approved": false,
  "safeReasonCode": null
}
```

This endpoint is the authority for refresh, app restart, and uncertain upload
recovery. Public user fields and browser session storage are hints only.

## `retryCurrentAvatarGeneration`

Request:

```json
{
  "clientRequestId": "safe idempotency id"
}
```

No image bytes, photo ID, storage reference, or arbitrary job ID are accepted.
The server uses the authenticated user's current contract, enforces retry and
budget limits, and returns the safe status schema above.

## `getAvatarJobCandidates`

Request: current opaque `jobId` only. The server verifies ownership and the
current source/job/version contract. Stale, cancelled, superseded, and hard
reject candidates are never returned.

Response contains at most four items:

```json
{
  "status": "preview_ready|queued|running|qa_pending|needs_review|no_previewable_candidates|retryable_failed|terminal_failed|approved",
  "candidates": [
    {
      "candidateId": "opaque id",
      "previewImageBase64": "bounded runtime JPEG",
      "qaSummary": "sanitized decision summary"
    }
  ],
  "retryAllowed": false,
  "safeReasonCode": null
}
```

The response must cap candidate count, individual bytes, total bytes, and
execution time. It never returns source or candidate storage locations.

## `approveAvatarCandidate`

Request: current `jobId` and returned `candidateId`. The server verifies current
ownership, preview eligibility, approval race, and safe approved destination.
The response returns only approval status and a safe public avatar URL.

## Compatibility

Root `functions/src` is canonical. Mobile and festival web consume the same
contract and error taxonomy. Any festival-specific adapter may translate auth
or navigation concerns but may not fork backend state or safety semantics.
