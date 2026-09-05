> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** The current Azure-only, source-set architecture is defined in [avatar-production/CURRENT_ARCHITECTURE.md](CURRENT_ARCHITECTURE.md).
>

# PR8.5 Blur Root-Cause Plan

Date: 2026-07-28

## Safety boundary

- Scope: local diagnosis, code, tests, sanitized artifacts, and documentation.
- Cloud upload, avatar job creation, FLUX invocation, deployment, App Check
  mutation, IAM mutation, queue mutation, and production rollout are forbidden.
- Project `seolleyeon` must not be touched.
- The global blur threshold must not be lowered to obtain 10/10.
- Exact-consent images remain local. Reports must omit raw UID, source filename
  or path, object references, bbox coordinates, landmarks, image bytes, and
  credentials.

## Evidence baseline

- Staging worker evidence: `seolleyeon-avatar-worker-00047-9qx`.
- Ten rows: 10/10 detected, 7/10 accepted, 3/10 quality-rejected.
- The three rejected rows used one full-image detection each, no tile fallback,
  no primary ambiguity, and no applied EXIF transform.
- Live upload and job creation remain zero because App Check token exchange
  returned 403.
- Archived revision-00047 `geometry.py` and blur configuration are byte-identical
  to the current working tree. Other pipeline/analyzer code has later local
  drift and must not be described as fully deployed.

## Exact decision path

```text
source bytes or PIL image
  -> ImageOrientationNormalizer
     -> decode/load
     -> ImageOps.exif_transpose
     -> strip EXIF by copying RGB pixels
  -> FullRangeFaceDetector
     -> BlazeFace full-range detector on normalized full image
     -> normalized xywh to clamped native PixelBox
     -> enrich_detection
        -> native detector-bbox short side and area
        -> native detector-bbox FIND_EDGES mean / 40 sharpness score
  -> optional OverlappingTileDetector
     -> tile detection
     -> map tile box to normalized original coordinates
     -> re-enrich against the normalized original image
  -> cross-pass NMS
  -> PrimaryFaceSelector
     -> confidence, area, center, border and current sharpness score
  -> native face short-side usability gate
  -> fixed single-metric blur gate: sharpness_score < 0.12
  -> HeadShouldersCropper
     -> expanded square crop
     -> optional neutral padding
     -> resize to 512/768 with LANCZOS
  -> CropFaceLandmarker
  -> SecondaryFaceNeutralizer
  -> analysis reference
  -> source analyzer acceptance
  -> worker privacy reference and generation
```

The active blur decision occurs before the head-and-shoulders crop, padding,
resize, crop landmarker, secondary neutralization, analysis reference, privacy
reference, and FLUX. The worker rejects the source before any GPU generation.

## Current metric contract

| Item | Current behavior | Finding |
| --- | --- | --- |
| ROI | clamped native detector bbox | face-local, but not a dedicated quality ROI |
| Metric | grayscale `PIL.ImageFilter.FIND_EDGES` mean divided by 40 | not Laplacian variance |
| Normalization | clamp to `[0, 1]` | not normalized for ROI size, luminance, or filter boundary |
| Decision | one fixed `< 0.12` threshold | single-metric, resolution-dependent |
| Size policy | native short side `< 64` rejects first | correct precedence exists, but blur has no size-aware policy |
| Exposure/compression | not measured | low light, noise, and JPEG damage can collapse into blur |
| Landmarks | executed after blur | cannot cause the current three blur results |
| Public reason | internal blur maps to `face_too_small` | classification is lost at analyzer/worker boundary |

## Reproduced implementation defects

1. Scale-only changes reverse the decision. An identical synthetic face fell
   from `0.943` at 64 px to `0.085` at 384 px.
2. Filter-boundary energy is included. A constant smooth crop changed from
   `0.308` at 64 px to `0.052` at 384 px despite containing no detail.
3. Luminance changes reverse the decision. A sharp 192 px sample at 25 percent
   luminance scored `0.062`, while blurred noise scored `0.129`.
4. The same rejected native ROI crossed from `0.0652` at 873 px to `0.1525`
   when resized to 384 px without gaining information.
5. The current metric also contributes 10 percent to primary selection, so its
   defect can affect both selection and rejection in multi-face cases.
6. Blur-rejected rows omit `primaryFaceSizeBucket` because the early return
   occurs before that metric is added.
7. Internal `avatar_source_face_too_blurry` is persisted and returned as
   `face_too_small` / `avatar_source_face_too_small`.

The existing `0.12` threshold is coupled to the defective metric and must not be
reused for a canonical or replacement metric.

## Provisional anonymous root-cause table

This table authorizes implementation of the metric/classification defect. It
does not authorize passing any of the three rows. Final taxonomy is written by
the sanitized diagnostic command and independent CV review.

| rowIndex | Native face short side | Independent evidence | Provisional primary category | Secondary contributor | Proposed decision |
| --- | ---: | --- | --- | --- | --- |
| 4 | 567 px | Laplacian variance `8.85`; Tenengrad `14.30`; nested insets remain low | `TRUE_DEFOCUS_BLUR` or `TRUE_MOTION_BLUR` | unresolved | `reject_true_blur` |
| 5 | 804 px | Laplacian variance `11.20`; Tenengrad `10.11`; local contrast `17.21` | `MULTIPLE_CONTRIBUTORS` | low contrast | `reject_true_blur` |
| 9 | 873 px | Laplacian variance `7.29`; Tenengrad `15.42`; nested insets remain low | `TRUE_DEFOCUS_BLUR` or `TRUE_MOTION_BLUR` | unresolved | `reject_true_blur` |

The weakest accepted row still measured Laplacian variance `79.91` and
Tenengrad `27.23`. All three blocked rows have ample native face pixels,
normal-range mean luminance, no differentiating JPEG quantization, and no
stronger blocking artifact than accepted rows. Low native resolution, severe
underexposure, and differential JPEG damage are therefore not supported as
their primary causes.

## Hypothesis disposition

| Hypothesis | Disposition | Evidence |
| --- | --- | --- |
| H1 global-image dominance | Rejected for current path | decision reads detector face bbox, not full frame |
| H2 loose generation crop | Rejected for current three | crop is created after blur return |
| H3 upscale suppression | Rejected for current three | blur is native; later transforms are downscales |
| H4 low face resolution | Rejected for current three | native short sides are all at least 567 px |
| H5 padding contamination | Rejected for current gate | padding is introduced after blur return |
| H6 wrong ROI/transform | Not supported | single full-image face, no tile/EXIF transform, aligned detector evidence |
| H7 low light/noise | Not primary; metric defect confirmed | fixture exposure is usable, but current metric is luminance/noise-confounded |
| H8 JPEG damage | Not supported | no differentiating quantization or block-risk evidence |
| H9 landmark collapse | Rejected as cause; reason contract defect remains | landmarker runs after blur; public mappings still collapse categories |
| H10 fixed resolution-dependent threshold | Confirmed general defect | scale and boundary probes reverse decisions |

## Approved remediation boundary

Implement a modular `BlurAssessment` v2 with:

- a dedicated native primary-face quality ROI;
- a valid-pixel mask and no neutral-padding contribution;
- downscale-only canonical normalization for cross-size metrics;
- low native resolution classified before blur;
- at least Laplacian variance, Tenengrad, edge density, local contrast, and
  exposure/clipping signals;
- optional compression risk only if bounded by tests;
- true blur requiring agreement between at least two sharpness signals;
- conflicting evidence producing `borderline` or `needs_review`, never pass;
- versioned typed configuration and shadow mode;
- explicit public separation of blur, low resolution, exposure, invalid ROI,
  landmark instability, and analysis uncertainty;
- one shared implementation used by analyzer/preflight and worker.

No production threshold will be claimed from this ten-row cohort. The initial
policy is a conservative shadow comparison backed by synthetic positives and
negatives, with the three current rows remaining rejected unless independent
evidence disproves true blur.

## Required implementation and verification

1. Build the privacy-safe ten-row diagnostic and final taxonomy.
2. Add failing tests for ROI/mask/canonical normalization and metric invariance.
3. Add synthetic sharp, defocus, motion, low-resolution, exposure, JPEG,
   invalid-ROI, crop, and landmark cases.
4. Implement v2 behind a versioned policy without fixture-specific logic.
5. Run v1/v2 shadow comparison and measure CPU p50/p95.
6. Run independent CV and privacy/security review.
7. Run the full Python, privacy, and any changed Functions/Flutter contracts.
8. Keep live uploads/jobs at zero and leave App Check/IAM/deployment unchanged.
