# B3-L11 — pre-registration: VISUAL_MARK_CHALLENGE_V3 + DETECTOR_CANDIDATE_SET_V1

Frozen **before any detector inference on a real avatar** (construct digest
`38ec105fc597…` from `avatar_visual_mark_challenge_v3.construct_digest()`,
detector-set digest `086a32a65e05…` from
`avatar_visual_mark_detectors.contract_digest()`; both checked in CI). This
is a detector-capability study, offline shadow only: no live integration, no
policy semantics, no worker/env/build/deploy change.

**Methodology marker: `FLORENCE_TELEMETRY_TEXT_PATH_CLOSED_ON_CURRENT_CORPUS`** —
on the current G004 controlled corpus no further feature engineering of
`rawSequenceScore`, `outputTokenCount`, typed geometry or their already
evaluated combinations. It does not say Florence is useless or that OCR is
removed; it says the current corpus is exhausted for that path. The G4–G5
score/token values left unseen by B3-L10A/B are not read here and no lock is
created for them.

Immutable prior results: V1 `OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT`, V2
`OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT`, V3 `V3_DUAL_CHANNEL_FAILED_DEVELOPMENT`,
B3-L9 `TEXT_POLICY_SHADOW_HOLDOUT_FAILED`, B3-L10A
`FLORENCE_SEQUENCE_SCORE_NOT_SEPARATING`, B3-L10B
`FLORENCE_TWO_FEATURE_NOT_SEPARATING`, `TEXT_POLICY_GAP` and
`GRAPHICAL_CHANNEL_GAP` unresolved, `NATURAL_POSITIVE_EVIDENCE_MISSING`.

## 1. Construct contract (`VISUAL_MARK_CHALLENGE_V3`)

* **Bases:** the 20 owner-authorized generated avatars; clean truth
  `OWNER_DESIGNATED_RATER_A_REFERENCE_TRUTH` (20 human-negative). Originals
  never written; derivatives rendered in memory / restricted scratch.
* **Split:** development G1–G3 (12 bases) + `DEV_VARIANT`; holdout G4–G5 (8
  bases) + `HOLDOUT_VARIANT` = **`DETECTOR_SPECIFIC_FROZEN_HOLDOUT`** (the
  bases were used by earlier feature studies; the detector outputs and the
  holdout constructs do not yet exist — never "globally unseen").
* **Alpha axis (PIL RGBA, normalized):** OPAQUE 1.00 · HIGH 0.65 · MEDIUM 0.35
  · LOW 0.20. LOW is a `LOW_VISIBILITY_STRESS_CONDITION` (diagnostic; no human
  visibility authority exists for it): reported, never gated.
* **Size bands:** small 0.035 · medium 0.07 (mark height / min(W, H)).
* **Placements:** corner (tl / tr / br), edge (top), center, torso
  (0.50, 0.62), tiled 3 × 4.

| Code | Family | Kind | Alpha | Placement | Sizes | DEV_VARIANT → HOLDOUT_VARIANT | Gate |
|---|---|---|---|---|---|---|---|
| F1 | TEXT_WATERMARK_OPAQUE | text (stroke) | OPAQUE | torso | small, medium | short word → short word | C |
| F2 | TEXT_WATERMARK_TRANSLUCENT_HIGH | text | HIGH | torso | medium | long word → long word | D |
| F3 | TEXT_WATERMARK_TRANSLUCENT_MEDIUM | text | MEDIUM | torso | medium | two-word → two-word | E |
| F4 | TEXT_WATERMARK_TRANSLUCENT_LOW | text | LOW | torso | medium | alphanumeric → alphanumeric | diagnostic |
| F5 | GRAPHICAL_WATERMARK_TRANSLUCENT | graphic | MEDIUM | center | medium | ring+star icon → asymmetric icon | F |
| F6 | LOGO_LIKE_EMBLEM | graphic | OPAQUE | corner tl | small, medium | shield emblem → crest emblem | G |
| F7 | BRAND_LIKE_TEXT_AND_SYMBOL | text+symbol | OPAQUE | corner br | medium | word+diamond → word+hexagon | overall only |
| F8 | SMALL_CORNER_MARK | graphic | OPAQUE | corner br | small | circle+triangle → monogram squares | H |
| F9 | EDGE_MARK | graphic | OPAQUE | edge top | small | line emblem → asymmetric icon | I |
| F10 | CENTER_OVERLAY_MARK | graphic | HIGH | center | medium | badge+ring → crest emblem | J |
| F11 | REPEATED_TILED_MARK | tiled text | MEDIUM | tiled | small | short word → short word | overall only |
| F12 | GRAPHIC_SYMBOL | graphic | OPAQUE | corner tr | small, medium | circle+triangle → hexagon+bar | overall only |

15 conditions per base → development 180 positives + 12 clean; holdout 120
positives + 8 clean. Synthetic strings only (a DEV and a different HOLDOUT
string per text family; length classes short / long / two-word /
alphanumeric present on both sides); real-trademark blocklist enforced
(including the product's own name). Noted confound: within one text family
the alpha level and the string length class co-vary (budget-driven); the
alpha axis is read across F1–F4 and the length class is reported as a
descriptive breakdown.

## 2. Detector candidate set (`DETECTOR_CANDIDATE_SET_V1`)

| Role | Detector | Repository @ revision | License (authority) | Queries | Operating point(s) | Notes |
|---|---|---|---|---|---|---|
| BASELINE A | owlv2-base-patch16-ensemble | `google/owlv2-base-patch16-ensemble` @ `cfd3195ba4ea9592eec887ded089f4c08eff231d` | apache-2.0 (official model card) | "a logo", "a watermark", "a brand emblem", "a graphic symbol" | **legacy 0.25 fixed** | not retuned; floor capture 0.01 |
| BASELINE B | grounding-dino-tiny | `IDEA-Research/grounding-dino-tiny` @ `a2bb814dd30d776dcf7e30523b00659f4f141c71` | apache-2.0 (official model card) | same four, joined "a logo. a watermark. …" | **historical box 0.25 / text 0.25 fixed**; separate pre-registered coarse grid 0.15 / 0.35 / 0.45 reported apart | floor capture 0.05 |
| NEW C | florence2-phrase-grounding | `florence-community/Florence-2-large-ft` @ `26b734a54fdfbf9c398351eedfabb7f27fc470b7` | MIT (official model card README; license_link microsoft/Florence-2-large LICENSE) | `<CAPTION_TO_PHRASE_GROUNDING>` with caption "a logo. a watermark. a brand emblem. a graphic symbol." | **presence** (no score) | full-frame boxes (area ≥ 0.50 of image) dropped — filter pre-registered from a pure-synthetic blank-image smoke that returned a full-frame "a watermark" box; num_beams 3, max_new_tokens 256 |

Common: CPU only (no GPU claim), one model resident at a time, input long
side ≤ 2048 (LANCZOS, avatars untouched), IoU match ≥ 0.30 (canonical since
B3-L4), image-level construct hit = ≥ 1 detection whose label is one of the
four queries and which matches a known box; unmatched detections never count
as recall. Scores are model-internal and never compared across models as
probabilities. One low-floor inference per image; every operating point is a
filter over the stored output.

**Excluded:** Ultralytics YOLO-World — `EXCLUDED_PENDING_PRODUCT_LICENSE_DECISION`
(AGPL-3.0 obligations are an owner decision; not downloaded, not evaluated,
no legality claim); `google/owlv2-large-patch14-ensemble` and
`IDEA-Research/grounding-dino-base` — `EXCLUDED_LOCAL_RESOURCE_BUDGET` (5.3 GB
free disk, 16 GB RAM CPU box). Any candidate whose license cannot be read
from the official card/repository is `EXCLUDED_LICENSE_UNVERIFIED`.

## 3. Gate A–L (development G1–G3 + DEV_VARIANT; identical on holdout)

A new clean `allow→review` ≤ 0.10 (12 → ≤ 1; 8 → 0) · B overall
controlled-positive image recall ≥ 0.95 excluding the diagnostic LOW family
(168 → ≥ 160; 112 → ≥ 107) · C F1 · D F2 · E F3 · F F5 · G F6 · H F8 · I F9 ·
J F10 each ≥ 0.90 (n = 12 → ≥ 11; n = 24 → ≥ 22; holdout n = 8 → 8/8, n = 16
→ ≥ 15) · K hard-reject bypass 0 · L decision downgrade 0. Shadow simulator:
`max(canonicalAction, review)` with the canonical clean action from the
B3-L4 Florence rows (production contract); existing canonical reviews are not
new burden. Clean detection on a human-negative avatar is
`CLEAN_IMAGE_RESPONSE`, never a production false-positive rate.

**Selection** among `DEVELOPMENT_ELIGIBLE` detector/operating points: lowest
new clean burden → highest minimum critical-family recall → highest overall
recall → lower peak RSS → lower median latency. Frozen as
`CONTROLLED_SHADOW_DETECTOR_CANDIDATE` (model, revision, license, prompts,
threshold, resize, matching rule, both digests, development-input digest).
Holdout (G4–G5 + HOLDOUT_VARIANT) is generated, inferred and evaluated only
after that freeze, exactly once behind `visual_mark_detector_v1_holdout.lock`;
afterwards no threshold, prompt, resize, model, family, alpha or matching
change.

## 4. Verdicts and markers

`VISUAL_MARK_DETECTOR_FAILED_DEVELOPMENT` · `VISUAL_MARK_DETECTOR_HOLDOUT_FAILED`
· `VISUAL_MARK_DETECTOR_CONTROLLED_GATE_PASSED` →
`VISUAL_MARK_DETECTOR_SUPPORTED_FOR_CONTROLLED_SHADOW_CANARY` ·
`BLOCKED_LOCAL_RESOURCE_SAFETY`. Gap markers: text gate (C–E) passed →
`TEXT_DETECTOR_CONTROLLED_GAP_CLOSED` (the canonical `TEXT_POLICY_GAP` itself
remains; a detector supplement may cover it); graphical gate (F–J) passed →
`GRAPHICAL_DETECTOR_CONTROLLED_GAP_CLOSED`, otherwise
`GRAPHICAL_DETECTOR_STUDY_REQUIRED`. Always `NATURAL_POSITIVE_EVIDENCE_MISSING`.
Forbidden wording: production validated / precision proven / live ready /
watermark policy ready. `approveAvatarCandidate` deployment remains a separate
release blocker.

## 5. Inference order (frozen)

source audit → this freeze → tests green → clean + development derivatives →
development capture (one model at a time; pre-load RAM/disk, peak RSS,
latency recorded; per-row guard never lowered) → development evaluation →
selected freeze → only then holdout generation / capture / evaluation.
