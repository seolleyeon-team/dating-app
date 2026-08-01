# Avatar Metrics Contract

Version: `avatar_metrics_v2`

Metrics contain opaque hashes or aggregate labels only. They exclude image data,
source/candidate references, signed URLs, prompts, trait payloads, UID/email/phone,
room IDs, raw vectors, and landmarks.

## Per-job timing and cost

- `modelLoadSeconds`
- `faceDetectSeconds`
- `traitExtractSeconds`
- `preprocessSeconds`
- `samSeconds`
- `generationSeconds`
- `qaSeconds`
- `rerankSeconds`
- `uploadSeconds`
- `totalWorkerSeconds`
- `estimatedUsd`
- `retryCount`
- `deadlineExceededCount`
- `initialCandidateCount`, `extraCandidateCount`, `previewCount`

Invariant: `totalWorkerSeconds` is at least every included stage and their
non-overlapping sum within documented tolerance. Invalid records are reported,
not silently included in percentiles.

## Product and QA aggregates

- upload accepted/rejected by safe reason
- queue depth and oldest age
- preview-ready, approval, lock-retest and same-source retry rates
- hard pass, soft pass, review and hard reject rates
- identity, childlike, beautification, background, person and text/logo risks
- trait coverage by field and confidence
- cold/warm model-load cohorts
- live/dry-run/retry/failed/cancelled/bridge cohorts
- cost per preview-ready and approved avatar
- preview payload bytes p50/p95/max

## Initial targets

These are canary targets, not auto-tuned production thresholds:

- total worker p95 below 240 seconds
- estimated cost/job p95 below USD 0.12
- preview payload warning above 8 MB and critical above 20 MB
- queue oldest age and failure/deadline spikes alert before rollout expansion

## Cost guard inputs

Every direct task, drain, batch, retry, and extra-generation path evaluates the
same kill switch, disable-new-generation flag, daily/monthly spend, candidate
cap, retry cap, deadline, and estimated remaining round cost.

## Versioning

Every metric record names state, API, data, QA, preprocessing, trait, prompt,
model, cost, and metrics versions. Reports reject mixed cohorts unless they are
explicitly grouped by version.
