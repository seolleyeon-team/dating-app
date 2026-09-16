# B3-L13 — pre-registration: VISUAL_MARK_PROPOSAL_VERIFIER_V1 (multi-detector proposal union + local crop verifier)

Frozen **before any verifier feature was extracted and before any
out-of-fold score was seen** (contract digest `f2c38dc9feaa…` from
`avatar_proposal_verifier.contract_digest()`, checked in CI). Offline,
decision-neutral research: no live integration, no policy, worker, env,
build or deploy change.

Immutable: B3-L11 `VISUAL_MARK_DETECTOR_FAILED_DEVELOPMENT` (holdout opened
NO, executions 0); B3-L12A `GDINO_GEOMETRY_FILTER_FAILED_DEVELOPMENT`
(`CLEAN_GEOMETRY_NOT_SEPARATING`, `EDGE_FAMILY_STILL_UNDERDETECTED`,
`GRAPHICAL_WATERMARK_STILL_UNDERDETECTED`, `MIXED`); `TEXT_POLICY_GAP`
unresolved; `GRAPHICAL_DETECTOR_STUDY_REQUIRED`; `NATURAL_POSITIVE_EVIDENCE_MISSING`.

Methodology markers:
* **`GDINO_GEOMETRY_FILTER_PATH_CLOSED_ON_CURRENT_CORPUS`** — no further
  area / aspect / coarse-location / hand-written geometry rules or threshold
  refinement on G1–G3 (no G5/G6 candidates, no 0.025/0.027 search, no
  per-box exclusions).
* **`FACE_SUPPRESSION_PROHIBITED`** — no "box inside primaryFaceBBox → ignore"
  and no face-detector feature in the verifier: it would create a
  deterministic blind spot for marks over the face unless the owner decides
  otherwise.
* **`PROPOSAL_UNION_WITH_DOWNSTREAM_VERIFIER_DISTINCT_FROM_REJECTED_RAW_OR`** —
  B3-L12A rejected raw OR → review; here the union only generates proposals
  and the verifier can remove them, so the "clean burden ≥ noisiest
  component" argument does not apply to the final pipeline.

## 1. Frozen proposal generators (B3-L11 baselines, exact)

| Generator | Repository @ revision | License | Operating point | Queries |
|---|---|---|---|---|
| OWLv2 | `google/owlv2-base-patch16-ensemble` @ `cfd3195ba4ea9592eec887ded089f4c08eff231d` | apache-2.0 | legacy 0.25 fixed | B3-L11 four queries |
| Grounding DINO tiny | `IDEA-Research/grounding-dino-tiny` @ `a2bb814dd30d776dcf7e30523b00659f4f141c71` | apache-2.0 | box 0.25 / text 0.25 fixed | same, joined as B3-L11 |
| Florence-2 phrase grounding | `florence-community/Florence-2-large-ft` @ `26b734a54fdfbf9c398351eedfabb7f27fc470b7` | MIT | presence, full-frame filter (area ≥ 0.50) | same four phrases |

No detector retuning of any kind (thresholds, prompts, per-query
thresholds, new detector, calibration, fine-tuning). Development proposal
inference = 0: the B3-L11 development captures are reused after an exact
provenance audit (revision, repo, license, detector-set digest
`086a32a65e05…`, construct digest `38ec105fc597…`, DEV_VARIANT, originals
unchanged). Match rule: IoU ≥ 0.30 (the B3-L11 contract has no containment
clause).

## 2. Coverage gate (computed first, without any verifier)

Union proposal ceiling on G1–G3 + DEV_VARIANT: A overall gated-positive
proposal recall ≥ 0.95 (≥ 160/168); B–I per family ≥ 0.90 for
TEXT_WATERMARK_OPAQUE, TEXT_WATERMARK_TRANSLUCENT_HIGH / _MEDIUM,
GRAPHICAL_WATERMARK_TRANSLUCENT, LOGO_LIKE_EMBLEM, SMALL_CORNER_MARK,
EDGE_MARK, CENTER_OVERLAY_MARK (LOW alpha diagnostic). Any failure →
`PROPOSAL_UNION_COVERAGE_INSUFFICIENT` and STOP (a verifier cannot recover
missing proposals).

## 3. Verifier (existing local production model; frozen)

`openai/clip-vit-large-patch14` @ `32bd64288804d66eefd0ccbe215aa642df71cc41`
— the production QA `LocalClipRiskScorer` (clipSafety) model pinned in the
worker Dockerfile; local HF cache at exactly that revision; transformers
`CLIPModel` / `CLIPProcessor` with `local_files_only`; preprocessing resize
shortest side 224, centre crop 224, CLIP mean/std; `get_image_features`,
L2-normalized, 768-d. **License authority:** the official openai/CLIP
repository LICENSE (MIT License, Copyright (c) 2021 OpenAI); the Hugging Face
model card links that repository and carries no license field of its own.
Local inference only. No optional second verifier was needed.

**Crop contract (deterministic, one rule):** each proposal box padded by
15 % of its own width (x) and height (y) on every side, clipped to the image,
minimum side 8 px, then the CLIP processor defaults. No padding sweep, no
family/detector/label-specific crop.

**Classifier recipe (frozen):** `sklearn.linear_model.LogisticRegression`,
penalty l2, C = 1.0, solver lbfgs, class_weight balanced, max_iter 1000,
random_state 0, on the L2-normalized embedding; scikit-learn 1.9.1 pinned;
no hyperparameter search. Output role **`UNCALIBRATED_VERIFIER_SCORE`** — the
sigmoid output is never called a calibrated probability and no confidence
band is derived from it.

**Threshold grid (frozen):** 0.20 · 0.35 · 0.50 · 0.65 · 0.80; neutral 0.50;
no midpoint search.

## 4. Labels, folds, leakage

* Clean G1–G3 avatars (`OWNER_DESIGNATED_RATER_A_REFERENCE_TRUTH`, 12/12
  negative): every union proposal = `CONTROLLED_NEGATIVE_PROPOSAL`.
* Positive derivatives: proposal IoU ≥ 0.30 with a known box =
  `CONTROLLED_POSITIVE_PROPOSAL`; IoU ≤ 0.05 and no centre containment either
  way = safe negative; otherwise `AMBIGUOUS_EXCLUDED` (scored, never trained
  on). Ground-truth boxes are label/evaluation authority only.
* Runtime verifier input: the proposal crop only. Refused as features:
  ground truth, family, alpha, placement, variant, base identity, human
  labels, clean/positive flag, detector score, face boxes.
* Folds: leave-one-group-out over G1 / G2 / G3 (train G1+G2 → G3, G1+G3 → G2,
  G2+G3 → G1); a base avatar's clean proposals and all its derivative
  proposals share its group, so train/evaluation bases are disjoint by
  construction (asserted in code). Only out-of-fold scores enter the
  development table; in-sample training performance is never a gate.

## 5. Image-level pipeline, gate, selection

Per image: frozen union proposals → deterministic crop → verifier score →
survivors at the threshold → shadow review if any survivor
(`max(canonicalAction, review)`, review-only, never reject, never downgrade);
a positive counts only when a **surviving** proposal matches a known box.
Gate J1–J12 = the B3-L11 gate (J1 new clean allow→review ≤ 0.10 → ≤ 1/12
development, 0/8 holdout; J2 overall ≥ 0.95; J3–J10 per family ≥ 0.90
with holdout arithmetic n = 8 → 8/8, n = 16 → ≥ 15/16; J11/J12 = 0). A soft
needs-review UI policy does not weaken this QA gate. Selection among eligible
thresholds: lowest clean new-review → highest minimum critical-family recall
→ highest overall recall → closest to 0.50. No eligible threshold →
`PROPOSAL_VERIFIER_FAILED_DEVELOPMENT` with diagnosis
(`PROPOSAL_CEILING_INSUFFICIENT`, `CONTENT_VERIFIER_NOT_SEPARATING`,
`CLEAN_HARD_NEGATIVES_NOT_SEPARATING`, `EDGE_PROPOSAL_GAP`,
`TRANSLUCENT_GRAPHIC_PROPOSAL_GAP`, `VERIFIER_REMOVES_TRUE_MARKS`, `MIXED`),
and no classifier, crop, threshold, detector or prompt change.

## 6. Holdout (existing B3-L11 contract, one shot)

Only after a development pass and freeze of the full recipe
(`VISUAL_MARK_PROPOSAL_VERIFIER_CONTROLLED_SHADOW_CANDIDATE`): audit that the
B3-L11 holdout is unopened (no holdout derivatives/captures for any detector,
no holdout embeddings, no `visual_mark_detector_v1_holdout.lock`); generate
G4–G5 + HOLDOUT_VARIANT; run the three frozen generators (one model resident
at a time), then the verifier embedding; fit the frozen recipe once on all
G1–G3; apply the frozen threshold; evaluate exactly once behind the canonical
B3-L11 lock. Afterwards nothing is retuned.

Verdicts: `VISUAL_MARK_PROPOSAL_VERIFIER_CONTROLLED_GATE_PASSED` →
`…_SUPPORTED_FOR_CONTROLLED_SHADOW_CANARY` (not production, not
natural-positive, not live-integration validated); `…_HOLDOUT_FAILED`;
`PROPOSAL_VERIFIER_FAILED_DEVELOPMENT`; `PROPOSAL_UNION_COVERAGE_INSUFFICIENT`.
Gap markers as in B3-L11; always `NATURAL_POSITIVE_EVIDENCE_MISSING`.
`approveAvatarCandidate` deployment remains a separate release blocker.
