# PR8.5 blur v1 / candidate comparison

Date: 2026-07-28

The filename retains the PR8.5 `v2` deliverable name for compatibility. The
candidate actually evaluated is `avatar_face_blur_multimetric_v3` under the
`pr85_v3_shadow` policy, with calibration status `uncalibrated_candidate`.

## Decision

- Status: `BLOCKED_BY_MORE_CALIBRATION`
- Production ready: false
- Active gate changed: no
- Live upload: 0
- Cloud, deployment, App Check, IAM, or FLUX mutation: none

## Aggregate

| Measure | Active v1 | v3 shadow |
| --- | ---: | ---: |
| Pass | 7 | 7 |
| Reject | 3 | 0 |
| Review | 0 | 3 |

- Total rows: 10
- False-positive corrections: 0
- Active-v1 blur rejections retained: 3
- v3-confirmed true blur: 0
- Low-resolution reclassified: 0
- Low-light reclassified: 0
- Unresolved: 3

Rows 4, 5, and 9 have adequate native face resolution, normal exposure, low
compression risk, one full-image detection, and no tile fallback. Their native
and canonical sharpness evidence conflicts. The shadow policy therefore does
not call them clear and does not claim an optical subtype; it returns review
and preserves the active v1 rejection.

## Anonymous row comparison

| rowIndex | old | new | disagreement | disposition |
| ---: | --- | --- | --- | --- |
| 1 | pass | pass | none | no action |
| 2 | pass | pass | none | no action |
| 3 | pass | pass | none | no action |
| 4 | reject: blur | review: uncertain | v1 reject / v3 review | retain active rejection |
| 5 | reject: blur | review: uncertain | v1 reject / v3 review | retain active rejection |
| 6 | pass | pass | none | no action |
| 7 | pass | pass | none | no action |
| 8 | pass | pass | none | no action |
| 9 | reject: blur | review: uncertain | v1 reject / v3 review | retain active rejection |
| 10 | pass | pass | none | no action |

The sanitized JSON contains the allowed hashes needed to correlate these rows
without disclosing original identifiers or source references.

## Added CPU overhead

`BlurAssessor.assess` was measured locally on one deterministic synthetic
768 x 768 image with a 384-pixel synthetic face region. After 10 warm-up calls,
100 calls produced:

- p50: 254.869 ms
- p95: 356.387 ms
- minimum: 158.081 ms
- maximum: 699.327 ms

This is a single Windows CPU microbenchmark. It excludes detector time, model
startup, image decoding, and I/O, so it is evidence for the added assessment
cost only, not a production capacity claim. Pipeline observation is explicitly
opt-in and defaults to disabled, so this cost is not added to the default active
v1 path. An enabled shadow failure is isolated as sanitized `unavailable` and
cannot change the v1 result. The configuration snapshot SHA-256
is `cc11820c5ab0d42595119b88058e36efc01ce9656c97bfe00e3f5d1e50a0cc25`.

## Activation blockers

Activation requires a labeled dataset independent of this ten-row cohort,
false-pass and false-reject measurements across source sizes and camera
pipelines, canonical-scale stability tests, border-contact calibration,
compression phase validation, explicit rollback criteria, and an approved
shadow duration. Until then v3 remains shadow-only.
