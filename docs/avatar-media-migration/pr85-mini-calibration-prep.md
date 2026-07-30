# PR8.5 Mini Calibration Prep

Generated: 2026-05-27T01:54:29+09:00

Production-ready: false

## PR8.4b Baseline

- Status: `PASS_COMPLEX_BACKGROUND_LIVE_MATRIX`
- Project: `seolleyeon-final`
- Worker revision: `seolleyeon-avatar-worker-00033-8gs`
- Production project `seolleyeon`: not touched
- Positive preview_ready rate: 4/4
- Positive approval rate: 4/4
- Approved avatar lock retest: 4/4 rejected
- Privacy QA: pass
- Live report forbidden-marker grep: pass

## Matrix Outcomes

- A_SIMPLE_SINGLE_FACE: preview_ready, 4 candidates, approved, lock retest rejected
- B_COMPLEX_CLEAR_PRIMARY: preview_ready, 4 candidates, approved, lock retest rejected
- C_SMALL_BACKGROUND_FACE: preview_ready, 4 candidates, approved, secondary background face handled
- D_TWO_PRIMARY_FACES: failed safely with `avatar_source_multi_face`, 0 candidates, no approval
- E_TEXT_LOGO_RISK: preview_ready, 4 candidates, approved, QA low

## Watch Items From PR8.4b

- E text/logo fixture had `textLogoWatermarkRisk=low` but `textLogoNeutralized=false`; keep as watch item, not automatic failure.
- A had a transient deadline status before recovering to preview_ready; record retry/deadline behavior in PR8.5.
- Production-ready remains false.

## PR8.5 Input Contract Check

- Required files:
  - `mini_calibration_uid_photo_map.txt`: present
  - `mini_calibration_consent_map.txt`: present
- Row count: 10, within preferred 10-20 range
- Local photo files: 10/10 exist
- General consent: valid when read as UTF-8
- Exact UID/photo basename row match: 10/10 matched, missing 0, unexpected 0

## Current Blocker

Live mini calibration was not run because the participant UID contract failed:

- Firebase Auth UID verification: 0/10 valid
- `users/{uid}` docs found: 10/10
- Approved avatar lock detected: 10/10

These rows look like already-used staging user document IDs rather than fresh unlocked Firebase Auth UIDs. No upload, generation, candidate preview, or approval was attempted.

## Required Next Input

Provide a fresh `mini_calibration_uid_photo_map.txt` and matching `mini_calibration_consent_map.txt` where:

- each UID is a real Firebase Auth UID in `seolleyeon-final`
- each UID has no approved avatar lock
- each local photo path exists
- exact UID/photo rows are explicitly consented
- no legacy PR84/PR8.4b approved-avatar-locked rows are reused
