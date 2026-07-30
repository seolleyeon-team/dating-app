# Avatar QA Contract

Version: `avatar_qa_v2`

## Environment rule

`production` and `production_bridge` are identical safety environments. Both
require privacy preprocessing, real required QA signals, authenticated worker
invocation, no dry-run, and no heuristic-only preview.

## Source analysis

The detector evaluates all bounded face candidates and scores confidence,
relative area, centrality, border distance, and available quality. It selects a
primary only when the margin is sufficient. Small secondary background faces
may proceed only when their in-memory boxes reach preprocessing and are removed.
No face, two primary-sized faces, unclear primary, too-small face, severe
occlusion, or unsafe source is rejected before generation.

Persist only decisions, counts, version, and coarse backend processing metadata.
Do not persist raw landmarks, raw vectors, or secondary-face geometry.

## Two-reference contract

1. Analysis crop: primary head/shoulders crop with neutralized background and
   enough hair, eyewear, facial hair, and clothing detail for trait extraction.
2. Generation reference: privacy-reduced face and style resolution with neutral
   background, passed to FLUX instead of the original source.

The original complex background is never passed to FLUX. Trait extraction does
not use the raw full frame and does not use a reference blurred enough to destroy
required broad traits.

## Preprocessing actions

Secondary-face, OCR/text/logo, person-background, crop, and neutralization fields
describe actual pixel operations. A metadata flag alone is not neutralization.
SAM is optional, but low-confidence fallback isolation produces review rather
than a synthetic pass.

## Trait card

Traits are enum-only and confidence-aware. Onboarding supplies presentation
gender; image models cannot override or infer it. Hair and clothing colors use
their respective regions and lighting-aware confidence. Specific color phrases
are evaluated before generic phrases. Background objects, brands, school names,
locations, unique marks, sensitive traits, and exact geometry are excluded.

## Candidate QA cascade

Lightweight first pass for every candidate:

- decode/dimensions/artifacts
- face and person count
- OCR/text/logo
- NSFW/sexualized and adult/childlike risk
- crop/background leakage
- broad hair, eyewear, facial-hair and clothing consistency

Heavy models run only for uncertain candidates:

- reliable source-candidate identity risk
- DINO/CLIP broad consistency
- detailed trait or segmentation checks
- beautification/idealization and brand-fit review

Raw embeddings are process-local and never persisted.

## Decisions

| Decision | Preview | Rule |
| --- | --- | --- |
| `hard_pass` | yes | all required signals available and within thresholds |
| `soft_pass` | yes, bounded fill only | all absolute safety signals pass; only noncritical quality uncertainty remains |
| `needs_review` | no | critical model unavailable, conflicting signal, or unresolved risk |
| `hard_reject` | never | absolute safety/privacy/identity failure |

Hard rejects include multiple faces/person leakage, readable sensitive text,
childlike or sexualized result, high reliable identity similarity, exact clone,
serious crop/body invention, severe artifact, or high-confidence hard trait
contradiction. pHash or crop similarity alone is not a biometric identity test.

## Generation and preview

Generate four initial candidates. Generate up to four more only when fewer than
two acceptable candidates remain and deadline and budget allow. Maximum total is
eight; maximum preview is four. Fewer safe candidates are preferable to unsafe
fill. Hard reject fill is always disabled.

## Calibration gate

Production QA requires realistic consented cohorts, nonzero hard passes, model
outage-to-review tests, OCR and secondary-face fixtures, glasses/no-glasses,
hair-color, complex-background, two-primary, childlike/sexualized, and identity
negative fixtures. Threshold version and false-positive evidence are mandatory.
