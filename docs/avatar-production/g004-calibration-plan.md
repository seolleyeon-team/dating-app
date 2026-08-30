# G004 Calibration Plan

Date: 2026-07-22
Authority updated: 2026-08-30 — the production-readiness gate is now the
5+ exact-consent cohort contract below (cohort policy `g004-5plus-v1`).
The original mandatory 10-20 → 50-100 sequence is SUPERSEDED and larger
cohorts are optional follow-up. Historical evidence artifacts are unchanged.

## Status

- Current gate: `QA-007 blocked_external_evidence`
- `QUALITY_QA_PRODUCTION_READY=false`
- Overall `production-ready=false`
- Live calibration run: not executed

This plan defines the evidence required after the G004 repository implementation
gate. It is not a record of completed production calibration.

## Production Readiness Gate: 5+ Current-QA Calibration Cohort

Run this calibration gate before any production-quality claim. A single successful calibration run with at least 5 fresh exact-consent participants is sufficient to make the G004 quality gate eligible for production-ready status.

Requirements:

- At least 5 fresh participants.
- Exact UID/photo consent for every row.
- Real Firebase Auth UIDs in the expected project.
- No reused approved-avatar-locked rows.
- Current production-like QA wiring.
- Versioned threshold snapshot before the run.
- Human rubric review for each participant result.
- No persisted source exact bbox in reports or exports.
- Privacy export scan before sharing any report.

Required outcome:

- The calibration run itself passes the current QA calibration criteria.
- Nonzero hard-pass evidence.
- No hard reject appears in preview.
- Outage or missing required model signal becomes `needs_review`.
- Trait coverage and failure categories are recorded by cohort slice.
- No privacy leak in client files, reports, logs, or exported feedback.
- Calibrated thresholds have documented evaluation evidence and human signoff.

Production-readiness rule:

- If one current-QA calibration run with at least 5 exact-consent participants passes all requirements and required outcomes above, the G004 quality gate may set `QUALITY_QA_PRODUCTION_READY=true` and may be considered `production-ready=true` for the G004 quality/calibration scope.
- A separate 10-20 or 50-100 participant calibration run is not required as a blocking prerequisite for G004 production readiness.
- Larger cohorts may still be run after readiness for additional confidence, monitoring, recalibration, or post-release validation, but they are non-blocking unless a later incident or model/threshold change explicitly reopens calibration.

## Optional Larger-Cohort Validation

After the production-readiness gate passes, a larger exact-consent cohort may be run when additional statistical confidence is useful. This is optional and does not block production readiness.

Recommended controls:

- Keep the same threshold version unless a new threshold snapshot is explicitly created.
- Use the same human rubric.
- Apply the same privacy scan and report redaction rules.
- Record cost, latency, retry, payload, failure, and calibration metrics.
- Any material model, preprocessing, QA-contract, or threshold change should create a new calibration version and may require the production-readiness gate to be rerun.

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
quality or satisfy the current 5+ participant production-readiness calibration gate.
