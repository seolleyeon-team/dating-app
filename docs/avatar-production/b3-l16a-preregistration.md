# B3-L16A — pre-registration: DINOv2_FROZEN_VISUAL_REPRESENTATION_VERIFIER_V1

Frozen **before any DINOv2 crop embedding** (contract digest `b6a22d71eb0e…`
from `avatar_dinov2_verifier.contract_digest()`; the B3-L15A proposal
contract `de771758cc30…` and scan `1b45958a524d…` are unchanged and checked;
CI-tested). Offline, decision-neutral research: no live integration, no
policy, worker, env, build or deploy change.

Immutable: B3-L13 `PROPOSAL_UNION_COVERAGE_INSUFFICIENT`; B3-L14A
`EDGE_PROPOSAL_GENERALIZATION_HOLDOUT_FAILED`; **B3-L15A
`EDGE_SCAN_VERIFIER_FAILED_DEVELOPMENT`** with its proposal ceiling PASS
(B3-L11 dev 166/168, EDGE_MARK 12/12; B3-L14A dev 192/192, all cells 12/12),
known-construct stress NOT EXECUTED, original B3-L11 holdout UNOPENED;
`EDGE_MARK_REMAINS_CRITICAL_FAMILY`; `TEXT_POLICY_GAP` unresolved;
`NATURAL_POSITIVE_EVIDENCE_MISSING`.

## 1. Proposal research closed for this task

**`EDGE_SCAN_PROPOSAL_CONTRACT_FROZEN_AFTER_B3_L15A`** — no scan tile, stride
or scan-matching change; no detector threshold, prompt or detector-set change;
IoU unchanged; no proposal suppression or NMS; no face feature. Runtime
proposals are the B3-L15A exact frozen union OR `EDGE_SCAN_PROPOSAL_V1`, and
their identity (ids, sources, boxes, labels) is verified against the B3-L15A
embedding records before any DINOv2 embedding is written. New detector
inference on development and stress: 0.

**`SCAN_ONLY_CURRENT_REPRESENTATION_DOMINATED_BY_EXISTING_EVIDENCE`** — no
scan-only experiment is run. The B3-L15A aggregate already shows scan-tile
clean survivor images = 2 at 0.50 and 2 at 0.65 (ceiling ≤ 1/12), and at
0.80 even the combined union misses the EDGE_MARK floor (9/12); scan-only
recall cannot exceed the combined union, so no grid threshold could pass.

## 2. The single new hypothesis

Same proposals, same 15 % crops, same labels (positive / clean negative /
excluded), same base-disjoint folds, same linear classifier recipe, same
threshold grid — **only** the CLIP ViT-L/14 embedding is replaced by one
orthogonal frozen visual representation, **facebook/dinov2-base**. Exactly one
candidate: no SigLIP, no OpenCLIP, no DINOv2 size grid, no CLIP variant
comparison, no ensemble. No non-linear head (no RBF SVM, kernel search, random
forest, boosting, MLP, neural classifier, polynomial features).

## 3. Model authority (fetched fresh before the freeze)

| Item | Frozen value |
|---|---|
| Repository | `facebook/dinov2-base` |
| Revision (immutable) | `f9e44c814b77203eaa57a6bdbbd535f21ede1415` (Hugging Face API `sha`; branch names refused) |
| License | apache-2.0 (README front matter and API `cardData.license`) |
| Architecture | ViT-B/14 self-supervised DINOv2, `Dinov2Model`, hidden 768, 12 layers, patch 14, ~86 M parameters, `model.safetensors` ~346 MB |
| Library | transformers 4.57.6, `AutoImageProcessor` + `Dinov2Model`, local files only |
| Preprocessing (official `preprocessor_config.json`, `BitImageProcessor`) | convert RGB → resize shortest edge **256** (bicubic, resample 3) → centre crop **224 × 224** → rescale 1/255 → normalize mean [**0.485**, 0.456, 0.406], std [0.229, 0.224, 0.225]; no override |
| Embedding semantics | `pooler_output` = the [CLS] token of the final LayerNorm output (audited in the installed `Dinov2Model.forward`: `sequence_output = layernorm(...)`, `pooled_output = sequence_output[:, 0, :]`); identical to `last_hidden_state[:, 0]`; **no mean pooling, no layer search, no patch pooling, no multi-layer concat** |
| Dimension | **768**, L2-normalized before the classifier |

## 4. Frozen pipeline (B3-L15A exact)

Crop: proposal box + 15 % width/height padding per side, clipped, min side
8 px, then the official DINOv2 processor; no padding sweep, no
source/edge-specific crop, no larger-context experiment. Classifier input is
the crop embedding only (source, detector score, box, edge, family, size,
geometry, alpha, ground truth, clean/positive flag, base id, human label
refused). `LogisticRegression` l2, C 1.0, lbfgs, balanced, max_iter 1000,
random_state 0, scikit-learn 1.9.1, no search; output
`UNCALIBRATED_VERIFIER_SCORE`. Grid 0.20 · 0.35 · 0.50 · 0.65 · 0.80, no
midpoint, no source/family threshold. Folds leave-one-group-out G1/G2/G3; a
base's clean, B3-L11 and B3-L14A proposals share its fold; base leakage 0.
Development data: B3-L11 G1–G3 DEV + 12 clean and B3-L14A G1–G3 EDGE_DEV; no
new data. Only OOF predictions select or evaluate.

## 5. Gates and selection (B3-L15A exact)

J1 new clean allow→review ≤ 1/12 (existing canonical review not counted; a
soft needs-review UI policy does not weaken this QA gate); J2 broad overall ≥
0.95; J3–J10 opaque text, high / medium translucent text, translucent
graphical watermark, logo-like emblem, small corner, **EDGE_MARK**, centre
overlay ≥ 0.90 (LOW diagnostic); J11 bypass 0; J12 downgrade 0; **and**
B3-L14A DEV overall ≥ 0.95, each edge / size / geometry ≥ 0.90, each cell ≥
11/12. Selection: lowest clean new-review → highest minimum critical
family/cell recall → highest broad overall → highest edge overall → closest
to 0.50. None eligible → `DINOV2_VERIFIER_FAILED_DEVELOPMENT`, STOP: no
second representation, non-linear head, crop, classifier, threshold or
proposal change; no stress; no B3-L11 holdout. Diagnosis from
`FROZEN_VISUAL_REPRESENTATION_NOT_SEPARATING`,
`CLEAN_HARD_NEGATIVES_NOT_SEPARATING`, `BROAD_MARK_RECALL_REGRESSION`,
`EDGE_MARK_RECALL_REGRESSION`, `MIXED`; no causal claims about synthetic style
or about embeddings in general.

## 6. After a development pass

Full recipe frozen (`DINOV2_VERIFIER_CONTROLLED_SHADOW_CANDIDATE`: model
revision, preprocessing, embedding semantics, crop, proposal digest,
classifier, folds, grid, selected threshold, OOF input digest); then exactly
one linear fit on all G1–G3 training proposals. **KNOWN_CONSTRUCT_STRESS_GATE**
on the consumed B3-L14A G4–G5 EDGE_HOLDOUT_VARIANT (existing detector
captures, deterministic scan, new DINOv2 embeddings only); it is
**not an independent holdout**; gate: overall ≥ 0.95, each edge / size / holdout
geometry ≥ 0.90, each cell 8/8; fail →
`DINOV2_VERIFIER_KNOWN_CONSTRUCT_STRESS_FAILED`, STOP, B3-L11 holdout
untouched. Pass → fresh unopened audit of the original B3-L11 holdout (no
derivatives, no OWLv2 / Grounding DINO / Florence holdout inference, no
DINOv2 holdout embeddings, no canonical lock, no selected marker), then the
frozen B3-L11 G4–G5 + HOLDOUT_VARIANT exactly once behind the canonical lock:
clean 0/8 (1/8 fails), overall ≥ 0.95 (112 → ≥ 107), critical families ≥ 0.90
(n 8 → 8/8, n 16 → ≥ 15/16), EDGE_MARK critical. After the result nothing
changes (DINO revision, preprocessing, embedding semantics, crop, classifier,
threshold, scan, detectors, prompts, matching, family floors).

## 7. Verdicts and the stop rule

`DINOV2_VERIFIER_FAILED_DEVELOPMENT` · `DINOV2_VERIFIER_KNOWN_CONSTRUCT_STRESS_FAILED`
/ `_PASSED` · `DINOV2_VISUAL_MARK_VERIFIER_HOLDOUT_FAILED` ·
`DINOv2_VISUAL_MARK_VERIFIER_CONTROLLED_GATE_PASSED` →
`EDGE_PROPOSAL_CEILING_GAP_CLOSED_BY_DETERMINISTIC_SCAN`,
`VISUAL_MARK_EDGE_SCAN_VERIFIER_SUPPORTED_FOR_CONTROLLED_SHADOW_CANARY`; never
a production, live or natural-positive validation claim.
**`FROZEN_VERIFIER_REPRESENTATION_SEARCH_STOP_RULE`**: a DINOv2 development
failure ends B3 verifier shopping (no SigLIP, OpenCLIP, DINOv2-large, new
head, threshold or crop); the next research step is
`SUPERVISED_WATERMARK_LOGO_DATA_DESIGN`. Canonical `TEXT_POLICY_GAP` is not
closed by this study; watermark/logo hard-reject semantics unchanged; decision
diff 0; `approveAvatarCandidate` deployment remains a separate release blocker.

## 8. Safety

Local CPU only; DINOv2 the only resident model; detectors never loaded for
development or stress; guards start 3.0 GB / per-row 0.6 GB (never lowered);
batch 16; checkpoint-resume. Originals 28/28 verified before/after. Model
and license metadata downloads only; Azure / OpenAI image / external vision
/ raw-image transmission 0. Repository artifacts aggregate only.
