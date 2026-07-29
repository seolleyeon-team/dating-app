# G004 Calibration Plan

Date: 2026-07-22

## Status

- Current gate: `QA-007 blocked_external_evidence`
- `QUALITY_QA_PRODUCTION_READY=false`
- Overall `production-ready=false`
- Live calibration run: not executed

This plan defines the evidence required after the G004 repository implementation
gate. It is not a record of completed production calibration.

## Gate 1: 10-20 Current-QA Mini Cohort

Run this gate before any production-quality claim.

Requirements:

- 10-20 fresh participants.
- Exact UID/photo consent for every row.
- Real Firebase Auth UIDs in the expected project.
- No reused approved-avatar-locked rows.
- Current production-like QA wiring.
- Versioned threshold snapshot before the run.
- Human rubric review for each participant result.
- No persisted source exact bbox in reports or exports.
- Privacy export scan before sharing any report.

Required outcome:

- Nonzero hard-pass evidence.
- No hard reject appears in preview.
- Outage or missing required model signal becomes `needs_review`.
- Trait coverage and failure categories are recorded by cohort slice.

## Gate 2: 50-100 Cohort

Run only after Gate 1 passes.

Requirements:

- 50-100 exact-consent participants.
- Same threshold version unless a new threshold snapshot is explicitly created.
- Same human rubric.
- Same privacy scan and report redaction rules.
- Cost, latency, retry, payload, and failure metrics recorded.

Required outcome:

- Stable hard-pass rate by cohort slice.
- No privacy leak in client files, reports, logs, or exported feedback.
- Calibrated thresholds have documented precision/recall tradeoffs and human
  signoff.

## Cohort Slices

Track each participant against these non-sensitive calibration dimensions:

- Background: simple, complex, crowded, text/logo risk.
- Eyewear: none, glasses, sunglasses, reflective lenses.
- Hair: short, long, tied, covered, dyed/light/dark.
- Onboarding gender: explicit user-provided presentation guidance only.

Do not infer or store sensitive traits from images.

## Human Rubric

Each reviewer scores only the generated avatar result, not the raw private
source photo export.

Rubric:

- Overall avatar quality, 1-5.
- Person resemblance without identity overexposure, 1-5.
- Over-beautification or age distortion risk, 1-5.
- Hair, eyewear, clothing, and background consistency, 1-5.
- Background cleanup naturalness, 1-5.
- Safety result: approve, needs review, reject.
- Whether at least one of four candidates is usable.
- Whether regeneration is needed.
- Free-text notes with no source path, URL, landmark, embedding, or raw private
  identifier.

## Metrics

Record these metrics per run and per cohort slice:

- `hardPass`, `softPass`, `needsReview`, `hardReject`.
- Previewable candidate count.
- Reject reason distribution.
- Trait coverage average, p50, p95.
- Total latency p50 and p95.
- Cost p50 and p95.
- Retry/deadline count.
- Payload size p50 and p95.
- Human score average, p50, p95.
- Human override count.

## Threshold Snapshot and Versioning

Before each run, write a threshold snapshot with:

- QA contract version.
- Threshold version.
- Model/signal provider versions.
- Environment and project guard.
- Commit or source revision.
- Cohort ID.
- Date.

Do not compare cohorts as equivalent if threshold or provider versions changed.

## Privacy Rules

- Store only redacted participant labels or UID hashes in feedback exports.
- Do not export source photo paths, private bucket refs, signed URLs, raw
  landmarks, exact bboxes, embeddings, or model debug payloads.
- Confirm `qa_media_privacy` passes before circulating reports.
- Keep exact consent records separate from public or shareable calibration
  summaries.

## Historical PR8.5 Boundary

The existing PR8.5 report had 8 participants, 32 soft passes, 0 hard passes,
trait coverage average 0.3667, p50 0.3333, p95 0.4, total duration p50 81.103
sec and p95 86.927 sec, cost p50 USD 0.032011 and p95 USD 0.03431, one
retry/deadline event, and payload p50/p95 100590/119022 bytes.

That report predates current real-QA wiring. It cannot prove current production
quality or satisfy Gate 1.