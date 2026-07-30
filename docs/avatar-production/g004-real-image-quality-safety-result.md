# G004 Real Image Quality/Safety Result

Date: 2026-07-22

## Decision

- G004 repository implementation gate: `PASS`
- Code review: `APPROVE`
- Architecture review: `CLEAR`
- `QUALITY_QA_PRODUCTION_READY=false`
- Overall `production-ready=false`
- Public rollout: unauthorized and not executed

G004 closes the repository-level real-image quality and safety implementation
checkpoint. It does not prove production avatar quality. Production quality
readiness remains blocked until a fresh exact-consent calibration cohort passes
with the current real-QA wiring.

## Implementation Evidence

- Implementation tests: 449 passed, 6 skipped.
- Focused quality suite: 69 passed.
- Independent review suite: 85 passed.
- `compileall`: pass.
- Privacy QA: pass; 359 client files scanned, all leak counters zero.
- `git diff --check`: clean except CRLF warnings.
- Code review: `APPROVE`.
- Architecture review: `CLEAR`.

## Resolved Quality Issues

| Issue | Result | Evidence |
| --- | --- | --- |
| `QA-001` | resolved implementation | Secondary face geometry reaches preprocessing as process-local data. |
| `QA-002` | resolved implementation | `production` and `production_bridge` ignore caller-supplied `qaSignals` and force actual runtime signals. |
| `QA-003` | resolved implementation | `production_bridge` follows production-like preprocessing and privacy fail-closed behavior. |
| `QA-004` | resolved implementation | Trait extraction uses the neutralized analysis reference instead of the raw full source. |
| `QA-005` | resolved implementation | Region traits and parser behavior are covered by focused tests. |
| `QA-006` | resolved implementation | Real visual risk, OCR/logo/background, adaptive generation, and hard-reject preview behavior are wired. |
| `QA-008` | resolved implementation | Primary source bbox is removed from persisted `SourceAnalysisResult`; exact bbox remains process-local only. |
| `QA-009` | resolved implementation | Supplied `qaSignals` cannot bypass production or `production_bridge` QA. |

## Runtime Safety Notes

- Source exact bbox is no longer persisted in `SourceAnalysisResult`.
- Source exact bbox may remain in process-local memory for preprocessing and
  neutralized reference creation.
- Production and `production_bridge` ignore caller-provided `qaSignals`.
- Production and `production_bridge` require actual runtime QA signals.
- Model or signal outage produces `needs_review`, not a previewable pass.
- Hard rejects do not preview.
- Split refs, real visual risk, region traits, and adaptive generation are
  covered by repository tests and review evidence.

## Project Guard

- Active account observed for this closeout: `seolleyeon.official@gmail.com`.
- Active gcloud project observed: `seolleyeon-festival`.
- Expected staging project for live calibration: `seolleyeon-final`.
- `firebase use` errored because the account lacked `update-config`
  permission.
- No live mutation, staging calibration, deploy, IAM change, or cloud write was
  performed.

## Calibration Evidence Boundary

The existing PR8.5 historical report is useful only as historical calibration
shape evidence:

- Participants: 8.
- `softPass`: 32.
- `hardPass`: 0.
- Trait coverage: average 0.3667, p50 0.3333, p95 0.4.
- Total duration: p50 81.103 sec, p95 86.927 sec.
- Cost: p50 USD 0.032011, p95 USD 0.03431.
- Retry/deadline: one observed retry/deadline event.
- Payload size: p50 100590 bytes, p95 119022 bytes.

That report predates the current real-QA wiring. It cannot prove current
production quality, threshold adequacy, or hard-pass behavior.

## Remaining Blocker

`QA-007` remains `blocked_external_evidence`: fresh exact-consent calibration is
still required.

Minimum next gate:

- 10-20 fresh current-QA participants.
- Exact UID/photo consent for every row.
- Current production-like QA wiring.
- Nonzero hard-pass evidence.
- Versioned threshold snapshot.
- Human rubric review.

Broader release calibration remains 50-100 participants after the 10-20 gate.