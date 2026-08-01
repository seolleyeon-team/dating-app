# PR8.5 small-face staging rerun result

## Status

- Result: `PASS_PARTIAL_SMALL_FACE_RERUN`
- Project: `seolleyeon-final`
- Production project touched: no
- Production ready: no
- Live source upload executed: no

## Deployment

- Cloud Build: `b7aff0e3-d0ca-4b69-bcfb-beba04eca4cb`
- Image tag: `small-face-fix-20260727-200522`
- Image digest: `sha256:4cef2b72c96c01be65f9e9f0f45b87d4de07ca0a211a9c78eae2f38343eb4f27`
- Worker revision: `seolleyeon-avatar-worker-00047-9qx`
- Region: `asia-southeast1`
- Traffic: 100 percent
- Authenticated `/readyz`: 200
- Unauthenticated `/readyz`: 403
- Preserved runtime: L4 GPU 1, CPU 8, memory 32 GiB, concurrency 1, max scale 1, timeout 1800 seconds

## Ten-image analyzer parity

- Participant fixtures: 10
- Face detected: 10/10
- Small-face pipeline usable: 7/10
- Source analyzer accepted: 7/10
- Pipeline/analyzer contract conflicts: 0
- Tile fallback used: 0
- Quality blocked: 3/10
- Quality blocker: `avatar_source_face_too_blurry`
- Legacy relative-area override conflicts: 0

The three blocked fixtures were detected successfully. They were rejected by the independent blur quality gate, not by no-face or face-too-small detection.

## Consent and eligibility

- General consent valid: true
- Exact UID/photo rows: 10/10
- Missing exact rows: 0
- Unexpected exact rows: 0
- Firebase Auth credential match: 10/10
- Staging user documents verified: 10/10
- Approved-avatar lock: 0/10
- Analyzer-approved eligible rows: 7/10

## Live runner

- Dry run: ready for 7 analyzer-approved rows
- Guarded apply: blocked before upload
- Blocker: App Check debug-token exchange returned HTTP 403
- Uploads: 0
- Jobs created: 0
- Candidates/approvals/lock retests: 0
- App Check enforcement was not disabled or bypassed.
- App Check Admin debug-token listing also returned HTTP 403, so no IAM or App Check configuration mutation was attempted.

## Verification

- Python: 526 passed, 6 skipped
- Small-face/QA focused regression: 163 passed
- Avatar Functions contract: 34 passed
- Required Flutter avatar tests: 35 passed
- Flutter analyze: no issues
- Privacy QA: pass before final evidence refresh
- Sanitized report forbidden-marker scan: 0 findings

## Remaining blockers

1. An authorized operator must register the local staging App Check debug token for the Android app, or provide a valid short-lived App Check token.
2. Rerun guarded apply for the seven analyzer-approved rows only.
3. Replace or improve the three blur-blocked fixtures before a 10/10 live mini calibration.
4. Do not change the blur threshold based on this cohort alone.

This result verifies the repaired small-face detection and analyzer contract in staging, but it does not constitute a completed live mini calibration or production readiness.