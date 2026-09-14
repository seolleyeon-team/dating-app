# B3-L9 — pre-registration: TEXT_POLICY_SHADOW_V1 (narrow single-text watermark shadow)

Frozen **before any candidate performance metric was computed** (contract
digest `89514d712ad8…`, produced by `avatar_text_policy_shadow.contract_digest()`
and checked in CI). Designation: **`DEVELOPMENT_DESIGNED`** — the candidate
set was designed after an aggregate typed-feature inventory of G1–G3, which
has already served as development evidence in B3-L6.3/L7/L8; G1–G3 performance
is therefore *not* independent validation. The only independent authority is
the still-unopened G4–G5 holdout.

| Item | Value |
|---|---|
| Version | `TEXT_POLICY_SHADOW_V1` · candidate set `TEXT_POLICY_CANDIDATES_V1` · evidence `G004_TEXT_POLICY_SHADOW_EVIDENCE_V1` |
| Target | B3-L8 `TEXT_POLICY_GAP` only (opaque/translucent single-text watermark: Florence OCR 24/24, canonical flag 0/24) |
| Out of scope | `GRAPHICAL_CHANNEL_GAP`: OWLv2 model/threshold 0.25/prompts, GRAPHICAL_WATERMARK / EDGE_MARK / CENTER_OVERLAY_MARK handling → `GRAPHICAL_DETECTOR_STUDY_REQUIRED` |
| Canonical policy | `watermark_policy_v4_runtime_evidence_parity_v1`, `evaluate_watermark_risk` over `analyze_florence_visual_risk_outputs`, `source_regions=()` (production Azure worker mode) — unchanged |
| Composition | `shadowAction = max(canonicalAction, review if predicate else allow)` — review-only supplement; canonical review/reject never downgraded; repeated and generated-artifact paths untouched |
| Holdout lock | `text_policy_v1_holdout_evaluated.lock` (separate from V2/V3 locks); exactly once after `text_policy_v1_selected.json` is frozen |

Immutable prior results: V1 `OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT`, V2
`OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT`, V3 `V3_DUAL_CHANNEL_FAILED_DEVELOPMENT`,
`H4_DUAL_CHANNEL_SHADOW_NOT_SUPPORTED`, diagnosis `TEXT_POLICY_GAP` /
`GRAPHICAL_CHANNEL_GAP` / `MIXED`, `NATURAL_POSITIVE_EVIDENCE_MISSING`.

## 1. Canonical schema audit (fresh source, main `fc28646b`)

`analysis/watermark.py::_typed_region_document` per text-like region:
`kind` ∈ {text, logo, sign}; `location` ∈ {corner, edge, central,
clothing_zone} (corner = centre within 15 % of both borders; edge = one
border; clothing_zone = centre y ∈ [0.45, 0.85] and x ∈ [0.20, 0.80];
otherwise central); `areaBand` ∈ {small ≤ 0.03, medium ≤ 0.08, large};
`overlayLike` = (corner ∧ area ≤ 0.08) ∨ (edge ∧ area ≤ 0.03); `repeated`;
`artifactHint`; `textQuality` ∈ {plausible, implausible, unknown};
`confidenceBand` ∈ {high, medium, low, unknown}; `sourceConsistent`.
Per image (`_evidence_document`): `ocrDetectionCount`, `recognizedTokenCount`,
band counters, `repeatedTokenCount`, `sourceConsistency`.

**Allowed runtime fields:** `kind`, `location`, `areaBand`, `overlayLike`,
`repeated`, `artifactHint`, `textQuality`, `ocrDetectionCount`.
**Not admissible:** `confidenceBand` (Florence gives no calibrated per-region
probability; it is always `unknown` in production and "unknown" is not "low"),
`sourceConsistent` (inert with `source_regions=()`), raw OCR text
(token keys, transcribed labels, region quads), human labels, construct family,
ground-truth boxes, base/group/split identifiers, filenames.

## 2. Development feature inventory (G1–G3, aggregate; computed before the candidates)

| Group | regions/img | location | areaBand | overlayLike | textQuality | canonical |
|---|---|---|---|---|---|---|
| Clean human-negative (12) | 1 on 12/12 | corner 8, edge 3, clothing_zone 1 | small 11, medium 1 | True 10, False 2 | plausible 10, implausible 2 | allow 10, review 2 |
| TEXT_WATERMARK_OPAQUE (12) | 1 on 12/12 | clothing_zone 12 | small 12 | False 12 | plausible 12 | allow 12 |
| TEXT_WATERMARK_TRANSLUCENT (12) | 1 on 12/12 | clothing_zone 12 | small 12 | False 12 | plausible 12 | allow 12 |
| BRAND_LIKE_TEXT_AND_SYMBOL (diag., 12) | 1 | corner 12 | small 12 | True 12 | plausible 12 | allow 12 |
| REPEATED_TILED_MARK (diag., 12) | 6–12 | edge 66, central 46, clothing_zone 12, corner 1 | small 125 | True 67, False 58 | plausible 125 | reject 12 |

`confidenceBand` = unknown on every region; `artifactHint` = False on every
region. Two facts drive the design: (a) clean avatars carry exactly one small
*overlay-like corner/edge* text region on 10/12 images — the classic overlay
signature is the clean signature here; (b) the injected single-word watermark
is typed *clothing_zone / small / not overlay-like / single region* (the
family anchor y = 0.62 falls in the canonical torso band). Any rule that
escalates it is, by construction, a "small isolated non-overlay text in the
centre/torso band" rule, and integrated garment text (2/20 avatars carry a
`GARMENT_TEXT` primary label under Rater A) is exactly what the clean holdout
must expose.

## 3. Candidate set (frozen; strict → broad; rank 1 = strictest)

All candidates additionally require a text-like region; a bare "OCR region
exists" never triggers.

| Rank | ID | Predicate (on the canonical evidence document) |
|---|---|---|
| 1 | T1 STRICT | region.kind text-like ∧ location ∈ {corner, edge} ∧ areaBand = small ∧ overlayLike = True |
| 2 | T2 | text-like ∧ location = central ∧ areaBand = small ∧ overlayLike = False ∧ ocrDetectionCount = 1 |
| 3 | T3 | text-like ∧ location ∈ {central, clothing_zone} ∧ areaBand = small ∧ overlayLike = False ∧ ocrDetectionCount = 1 |
| 4 | T4 BROAD | text-like ∧ any location ∧ areaBand ∈ {small, medium} ∧ ocrDetectionCount = 1 |

No raw token, no word list, no confidence band, no family, no box. No
candidate is added, removed or re-thresholded after any table is seen.

## 4. Criteria A–F (identical on development and holdout)

| # | Criterion | Floor | Holdout arithmetic (N = 8) |
|---|---|---|---|
| A | new clean `allow → review` rate | ≤ 0.10 | only 0/8 passes (1/8 = 0.125 fails) |
| B | TEXT_WATERMARK_OPAQUE shadow action recall | ≥ 0.90 | 8/8 required |
| C | TEXT_WATERMARK_TRANSLUCENT shadow action recall | ≥ 0.90 | 8/8 required |
| D | REPEATED_TILED_MARK canonical reject preserved | 100 % | exact B3-L4 V4 rows reused |
| E | hard-reject bypass | = 0 | |
| F | generative-artifact safety regression (any shadow action below canonical) | = 0 | |

Development N = 12: A allows at most 1 new clean review; B/C need ≥ 11/12.

## 5. Selection, freeze, holdout

Selection = lowest rank among candidates satisfying A–F on development;
higher recall never justifies a broader candidate (minimum sufficient
escalation). No eligible candidate → `TEXT_POLICY_SHADOW_FAILED_DEVELOPMENT`,
holdout stays closed, no candidate is added and no geometry is adjusted.
Selected candidate, predicate, contract digest and development-input digest
are written to `text_policy_v1_selected.json`; holdout Florence inference for
the 16 text derivatives (8 opaque + 8 translucent) runs only after that
freeze; clean holdout (8) and tiled holdout (8) reuse the exact B3-L4 rows.
Holdout is evaluated exactly once; afterwards nothing is retuned.

## 6. Verdicts

* development + holdout pass → `TEXT_POLICY_SHADOW_CONTROLLED_GATE_PASSED`,
  `TEXT_POLICY_SHADOW_SUPPORTED_FOR_CONTROLLED_CANARY` (not a production
  claim); only then `AVATAR_WATERMARK_DUAL_CHANNEL_V4` = max(textAction,
  OWLv2 ≥ 0.25 review) may be recomposed offline (development, 10 families),
  with the graphical gap expected to remain;
* development fail → `TEXT_POLICY_SHADOW_FAILED_DEVELOPMENT`;
* holdout fail → `TEXT_POLICY_SHADOW_HOLDOUT_FAILED`;
* resources → `BLOCKED_LOCAL_RESOURCE_SAFETY`.

Every outcome keeps `NATURAL_POSITIVE_EVIDENCE_MISSING` and
`GRAPHICAL_DETECTOR_STUDY_REQUIRED`. Decision diff to live = 0 (analysis only;
no worker integration; `approveAvatarCandidate` deployment stays a separate
release blocker).
