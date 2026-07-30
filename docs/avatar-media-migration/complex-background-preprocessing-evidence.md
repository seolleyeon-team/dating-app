# Complex Background Avatar Preprocessing Evidence

Status: implementation complete, staging deployment completed, live matrix upload blocked by fixture/account lock.

Production-ready: false

## Implementation Summary

The avatar generation pipeline now accepts complex-background source photos when there is one clear primary face and the background can be safely neutralized before generation. The backend selects a primary face/person, crops to a head-and-shoulders reference, neutralizes the background, removes small secondary/background face regions from the foreground mask, and keeps FLUX and trait extraction on the privacy-processed reference rather than the original complex source image.

The source analyzer no longer rejects every `faceCount > 1` image. It scores face candidates by detection confidence, relative face area, centrality, quality/occlusion, and border clearance. Primary-like secondary faces still hard reject; small background faces can pass only when neutralization is required.

Trait extraction is constrained to broad, non-identifying visible cues from the primary crop. Background objects, locations, school names, brands, signs, posters, and logos are risk context only and must not enter the trait card.

FLUX prompting now explicitly asks for a simple neutral background and not to preserve or recreate the original background.

## Tests Passed Before Staging Deployment

- Python source/preprocess/trait/QA tests: 72 passed.
- Avatar worker integration tests: 49 passed.
- Flutter avatar generation flow tests: 23 passed.
- Functions tests: 39 passed.
- Dart analyze on touched Flutter avatar files: no issues found.
- `scripts/qa_media_privacy.py --dry_run --fail_on_warning`: passed.
- Complex-background local canary smoke: PASS.
- Scoped `git diff --check`: passed.

## New `sourceAnalysis` Fields

- `primaryFaceBbox`: coarse normalized primary face box, rounded and not raw landmarks.
- `secondaryFaceCount`: count of non-primary detected faces.
- `largeSecondaryFaceCount`: count of secondary faces considered primary-like or too large.
- `backgroundFaceRisk`: `none`, `secondary_background_face`, `large_secondary_face`, or `ambiguous_primary_face`.
- `primaryFaceConfidence`: detector confidence for the selected primary face when available.
- `primaryFaceScore`: primary selection score.
- `primaryFaceScoreMargin`: margin between selected primary and next candidate.
- `backgroundNeutralizationRequired`: true when background/secondary face handling is required.
- `broadTraitHints`: coarse bins only, with no raw landmarks or embeddings.

## New `referencePreprocess` Fields

- `primaryCropApplied`
- `cropType`
- `cropRisk`
- `backgroundNeutralized`
- `backgroundNeutralization.enabled`
- `backgroundNeutralization.mode`
- `backgroundNeutralization.neutralColor`
- `backgroundNeutralization.backgroundBlurRadius`
- `backgroundNeutralization.backgroundDesaturate`
- `backgroundNeutralization.secondaryFaceBlurRadius`
- `backgroundNeutralization.secondaryFaceCount`
- `backgroundNeutralization.secondaryFaceAction`
- `backgroundNeutralization.textLogoBlurEnabled`
- `backgroundNeutralization.textLogoRiskDetected`
- `backgroundNeutralization.textLogoAction`
- `backgroundNeutralization.foregroundMaskCoverage`

## New QA Fields

- `backgroundLeakageRisk`
- `secondaryFaceLeakageRisk`
- `textLogoWatermarkRisk`
- `cropIsolationQuality`
- `primaryFaceConfidence`

QA hard rejects generated candidates that include multiple faces, secondary people, original complex-background leakage, text/logo/school/campus signs, or crop expansion into unseen full body or extra people. Preview selection excludes hard rejects and candidates that still require human review.

## Privacy Notes

- Flutter receives sanitized job/candidate responses only.
- Functions expose sanitized `errorCode` for user-facing guidance.
- Raw private source references, storage object identifiers, private bucket names, temporary access links, and model embedding payloads must not be exposed to Flutter.
- Raw face geometry and embedding payloads are not stored in analysis, trait cards, QA docs, or matrix smoke reports.

## Remaining Blockers

- Live matrix upload could not run because all exact PR84 staging UID/photo pairs are approved-avatar locked.
- Prepare fresh unlocked staging UID/photo pairs with explicit consent before PR8.5 mini calibration or broader canary.
- Calibrate OCR/logo/sign risk behavior on deployed staging model availability.
- Confirm timing/cost after background neutralization and optional SAM behavior on staging.
- Confirm no production project or source project is touched.
- Do not mark production-ready until staging matrix and broader canary pass.
