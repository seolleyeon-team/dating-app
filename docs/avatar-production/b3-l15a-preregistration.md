# B3-L15A — pre-registration: DETERMINISTIC_EDGE_SCAN_WITH_CONTENT_VERIFIER_V1

Frozen **before any CLIP embedding and before any scan-verifier performance
number** (contract digest `de771758cc30…` from
`avatar_edge_scan_verifier.contract_digest()`, scan digest `1b45958a524d…`,
detector-set digest `086a32a65e05…` unchanged; checked in CI). Offline,
decision-neutral research: no live integration, no policy, worker, env,
build or deploy change. This is a **new hypothesis**; B3-L13 and B3-L14A
stay failed as recorded.

Immutable: B3-L11 `VISUAL_MARK_DETECTOR_FAILED_DEVELOPMENT`; B3-L12A
`GDINO_GEOMETRY_FILTER_FAILED_DEVELOPMENT`; B3-L13
`PROPOSAL_UNION_COVERAGE_INSUFFICIENT`; **B3-L14A
`EDGE_PROPOSAL_GENERALIZATION_HOLDOUT_FAILED`** (development 190/192,
holdout 125/128, failed cell TOP × medium × offset_bar_emblem 5/8 against
8/8, `EDGE_PROPOSAL_GAP_REPLICATED`); `EDGE_MARK_REMAINS_CRITICAL_FAMILY`;
`TEXT_POLICY_GAP` unresolved; `GRAPHICAL_DETECTOR_STUDY_REQUIRED`;
`NATURAL_POSITIVE_EVIDENCE_MISSING`.

Allowed reading of the prior misses: **`FROZEN_THREE_GENERATOR_ZERO_SHOT_EDGE_LIMIT`**
— with the current frozen OWLv2 / Grounding DINO tiny / Florence-2 phrase
grounding, thresholds, prompts and matching contract, the edge proposal gap
replicates. No generalization to other detectors or to zero-shot vision.

## 1. Hypothesis and architecture

`frozen zero-shot union` **OR** `deterministic edge-scan tiles` → proposal
crops → local CLIP content verifier → review-only shadow decision. The scan
guarantees recall by construction; the verifier removes clean edge crops.
Marker **`SCAN_CROP_COVERAGE_NOT_OBJECT_LOCALIZATION`**: the scan is not a
detector, and its match contract is not a relaxation of the detector IoU rule.

**No zero-shot retuning:** Grounding DINO 0.20 / 0.15 not adopted, OWLv2
threshold unchanged, Florence filter unchanged, no edge-specific prompt, no
query added, IoU not relaxed, no containment added to detector matching, no
new zero-shot detector, no raw-score re-search.

## 2. Frozen zero-shot generators (B3-L13 exact)

| Generator | Repository @ revision | License | Operating point |
|---|---|---|---|
| OWLv2 | `google/owlv2-base-patch16-ensemble` @ `cfd3195ba4ea9592eec887ded089f4c08eff231d` | apache-2.0 | 0.25 |
| Grounding DINO tiny | `IDEA-Research/grounding-dino-tiny` @ `a2bb814dd30d776dcf7e30523b00659f4f141c71` | apache-2.0 | box 0.25 / text 0.25 |
| Florence-2 phrase grounding | `florence-community/Florence-2-large-ft` @ `26b734a54fdfbf9c398351eedfabb7f27fc470b7` | MIT | presence, full-frame filter (area ≥ 0.50) |

Queries "a logo", "a watermark", "a brand emblem", "a graphic symbol".
Detector match: IoU ≥ 0.30, no containment. Existing development captures
(B3-L11 G1–G3 DEV_VARIANT + 12 clean; B3-L14A G1–G3 EDGE_DEV_VARIANT) and the
consumed B3-L14A G4–G5 captures are reused after exact provenance checks →
new detector inference on development and stress = 0. New detector inference
happens only for the original B3-L11 holdout (3 × 128 rows), once.

## 3. Edge scan (`EDGE_SCAN_PROPOSAL_V1`, one deterministic rule; no candidate search)

* **Prior only:** canonical max mark side M = 0.07 × min(W, H) (B3-L11 size
  bands) and the B3-L14A frozen inset envelope 0.02 × min(W, H), so a
  canonical edge mark's far edge lies within 0.09 × min(W, H) of the boundary.
  The rule was not fitted to any B3-L14A per-image box.
* **Tile:** square side S = round(0.16 × min(W, H)); outer side flush with the
  image boundary (TOP y ∈ [0, S], BOTTOM y ∈ [H−S, H], LEFT x ∈ [0, S],
  RIGHT x ∈ [W−S, W]).
* **Along-edge placement:** first and last tiles flush with the edge
  endpoints; uniform centres with adjacent spacing ≤ S − M = 0.09 × min(W, H)
  (n = ⌈(L − S) / (0.09 · min(W, H))⌉ + 1 tiles per edge); deterministic
  rounding. On a 1254 × 1254 avatar: S = 201, 11 tiles per edge, 40 distinct
  tiles after exact-duplicate removal at the corners. No NMS, no
  cross-source suppression; only exact duplicate boxes are dropped.
* **Runtime inputs:** image width and height only. Ground truth, family,
  alpha, placement, base id, human labels and known mark positions are
  refused at runtime.
* **Analytic coverage:** for any mark with side ≤ M and outer inset ≤ 0.02 ×
  min(W, H), anywhere along any edge, the spacing rule places one tile centre
  within [a + M − S/2, a + S/2] (length S − M ≥ spacing), so the mark lies
  inside that tile along the edge, and its far edge (≤ 0.09 · min) lies inside
  the tile depth (0.16 · min). Because pixel rounding can break exact
  containment by ≤ 1 px, the frozen scan match is **`GT_COVERAGE ≥ 0.95`**
  (fraction of the mark box area inside one tile). CI sweeps mark positions at
  3-px steps on three image shapes, both size bands and insets 0 / 0.01 / 0.02
  and asserts the floor; the B3-L11 edge/corner boxes and the B3-L14A edge
  boxes are asserted covered. The analytic guarantee is reported together
  with the measured construct coverage; no "100 % solved" claim.
* **`SCAN_MATCH` ≠ detector match:** a scan tile never counts under IoU and a
  detector box never under coverage.

## 4. Proposal-ceiling gate (no verifier; existing captures only)

Combined proposals = union OR scan. Development sets: (A) B3-L11 G1–G3
DEV_VARIANT — B3-L13 broad gate: overall ≥ 0.95 (≥ 160/168) and each of
TEXT_WATERMARK_OPAQUE, _TRANSLUCENT_HIGH, _TRANSLUCENT_MEDIUM,
GRAPHICAL_WATERMARK_TRANSLUCENT, LOGO_LIKE_EMBLEM, SMALL_CORNER_MARK,
EDGE_MARK, CENTER_OVERLAY_MARK ≥ 0.90; (B) B3-L14A G1–G3 EDGE_DEV_VARIANT —
overall ≥ 0.95 (≥ 183/192), each edge / size / DEV geometry ≥ 0.90, each cell
≥ 11/12. Any failure → `EDGE_SCAN_PROPOSAL_CEILING_FAILED`, STOP, no tile /
stride change, no embedding. B3-L14A's consumed G4–G5 is not development data.

## 5. Verifier (B3-L13 recipe, never run before; exact)

`openai/clip-vit-large-patch14` @ `32bd64288804d66eefd0ccbe215aa642df71cc41`
(the production clipSafety pin in the worker Dockerfile; local files only).
License authority re-verified: official openai/CLIP repository LICENSE
("MIT License, Copyright (c) 2021 OpenAI"); the Hugging Face card has no
license field and links that repository. Crop: each proposal box (detector
or scan, same function) padded 15 % of its width / height per side, clipped,
min side 8 px, CLIP processor defaults; no padding sweep, no source-specific
crop. Classifier: `LogisticRegression` l2, C 1.0, lbfgs, balanced, max_iter
1000, random_state 0 on the L2-normalized 768-d embedding, scikit-learn
1.9.1, no search; output `UNCALIBRATED_VERIFIER_SCORE`. Threshold grid 0.20 ·
0.35 · 0.50 · 0.65 · 0.80, neutral 0.50, no midpoint. Classifier input is the
crop embedding only: proposal source, detector score, box coordinates, edge
identity, family, size, geometry, alpha, ground truth, human labels and base
identity are refused as features.

## 6. Labels, folds, leakage

Positive derivative: detector proposal with IoU ≥ 0.30 or scan tile with
GT_COVERAGE ≥ 0.95 → `CONTROLLED_POSITIVE_PROPOSAL`. Clean G1–G3 avatars
(`OWNER_DESIGNATED_RATER_A_REFERENCE_TRUTH`, 12/12 negative): every runtime
proposal (union + scan) → `CONTROLLED_NEGATIVE_PROPOSAL`. Unmatched proposals
on positive derivatives: **excluded from training, scored in evaluation**
(clean originals are the negative authority). Folds: leave-one-group-out
G1/G2/G3; one base's clean proposals, B3-L11 derivatives and B3-L14A
derivatives share its fold; train/evaluation base overlap 0 (asserted). Only
OOF scores enter the development table.

## 7. Development gate and selection

Per image: proposals → crop → verifier → survivors at the threshold; ≥ 1
survivor → shadow review (`max(canonical, review)`, review-only, never reject,
never downgrade); a positive counts only when a surviving proposal matches
under its own contract. Gates at one threshold: J1 new clean allow→review ≤
0.10 → ≤ 1/12 (existing canonical review not counted; a soft needs-review UI
policy does not weaken this QA gate); J2 broad overall ≥ 0.95; J3–J10 the
eight broad families ≥ 0.90 (EDGE_MARK critical, never diagnostic); J11
bypass 0; J12 downgrade 0; **and** the B3-L14A edge gate on EDGE_DEV_VARIANT
(overall ≥ 0.95, each edge / size / geometry ≥ 0.90, each cell ≥ 11/12).
Selection among eligible thresholds: lowest clean new-review → highest minimum
recall over all broad families and edge cells → highest broad overall →
highest edge overall → closest to 0.50. None eligible →
`EDGE_SCAN_VERIFIER_FAILED_DEVELOPMENT`, STOP, diagnosis from
`CONTENT_VERIFIER_NOT_SEPARATING`, `EDGE_SCAN_CLEAN_BURDEN_TOO_HIGH`,
`VERIFIER_REMOVES_TRUE_EDGE_MARKS`, `BROAD_MARK_RECALL_REGRESSION`,
`SYNTHETIC_STYLE_NOT_SEPARATING`, `MIXED`; no scan, CLIP, crop, classifier,
threshold or zero-shot change; holdout stays closed. Pass → full recipe
frozen as `EDGE_SCAN_CLIP_VERIFIER_CONTROLLED_SHADOW_CANDIDATE` (scan, detector
set, revisions, prompts, thresholds, matching, crop, CLIP revision, classifier,
selected threshold, OOF input digest); then one classifier fit on all G1–G3.

## 8. KNOWN_CONSTRUCT_STRESS_GATE (first post-freeze gate)

B3-L14A G4–G5 EDGE_HOLDOUT_VARIANT: existing detector captures + scan + new
CLIP embeddings, frozen classifier and threshold. It is **not an independent holdout**;
its detector-level outputs were seen in B3-L14A and only the verifier outputs
are new. Gate: overall ≥ 0.95 (≥ 122/128), each edge ≥ 29/32, each
size ≥ 58/64, each holdout geometry ≥ 58/64, each cell 8/8. Fail →
`EDGE_SCAN_VERIFIER_KNOWN_CONSTRUCT_STRESS_FAILED`, STOP, B3-L11 holdout stays
unopened, no retune. Evaluated once (result recorded).

## 9. One-shot original B3-L11 holdout

Only after the stress pass and a fresh unopened audit (no G4–G5 +
HOLDOUT_VARIANT captures for any detector, no verifier embeddings, no
canonical lock, no selected marker): the frozen B3-L11 construct is generated
as is; three detector inferences (one model resident), scan, CLIP embeddings,
frozen classifier / threshold, evaluated exactly once behind
`visual_mark_detector_v1_holdout.lock`. Clean n = 8: new allow→review **must
be 0/8** (1/8 fails). Broad positives: B3-L11 arithmetic — overall ≥ 0.95
(112 → ≥ 107), critical families ≥ 0.90 (n 8 → 8/8, n 16 → ≥ 15/16),
EDGE_MARK critical. After the result nothing is retuned (scan tile, stride,
matching, CLIP, crop, classifier, threshold, zero-shot threshold, prompt,
family, gate).

## 10. Verdicts

`EDGE_SCAN_PROPOSAL_CEILING_FAILED` · `EDGE_SCAN_VERIFIER_FAILED_DEVELOPMENT`
· `EDGE_SCAN_VERIFIER_KNOWN_CONSTRUCT_STRESS_FAILED` / `_PASSED` ·
`VISUAL_MARK_EDGE_SCAN_VERIFIER_HOLDOUT_FAILED` ·
`VISUAL_MARK_EDGE_SCAN_VERIFIER_CONTROLLED_GATE_PASSED` →
`…_SUPPORTED_FOR_CONTROLLED_SHADOW_CANARY` and
`EDGE_PROPOSAL_CEILING_GAP_CLOSED_BY_DETERMINISTIC_SCAN`. Never a production,
live or natural-positive validation claim; always
`NATURAL_POSITIVE_EVIDENCE_MISSING`; canonical `TEXT_POLICY_GAP` is not
closed by this study; watermark/logo hard-reject semantics unchanged;
`approveAvatarCandidate` deployment remains a separate release blocker.

## 11. Safety

Local CPU only; detectors one at a time and unloaded before CLIP; batch size
within the memory guards (start gate 3.0 GB for CLIP, per-row 0.6 GB, never
lowered); checkpoint-resume. Originals 28/28 verified before/after (SHA-256 +
mtime). Azure / OpenAI image / external OCR / external vision / raw-image
transmission 0. Repository artifacts aggregate only (no crop, avatar,
filename, UID, private path, per-image embedding, score, proposal or
detector output).
