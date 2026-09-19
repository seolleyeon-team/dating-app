# B3-L16A — frozen edge-scan + union proposals with a DINOv2-base verifier: development result

Offline, decision-neutral research on the single hypothesis
`DINOv2_FROZEN_VISUAL_REPRESENTATION_VERIFIER_V1` (contract `b6a22d71eb0e…`;
B3-L15A proposal contract `de771758cc30…` and scan `1b45958a524d…`
unchanged), frozen in commit `232c2a08` before any DINOv2 embedding
([b3-l16a-preregistration.md](b3-l16a-preregistration.md)). No new detector
inference (B3-L15A proposal identity reused and verified exact on every
record), no external image calls, no policy / worker / env / build / deploy
change. Aggregate only.

**Verdict: `DINOV2_VERIFIER_FAILED_DEVELOPMENT`** · no verifier threshold
eligible on OOF development · diagnosis
`FROZEN_VISUAL_REPRESENTATION_NOT_SEPARATING` +
`CLEAN_HARD_NEGATIVES_NOT_SEPARATING` + `BROAD_MARK_RECALL_REGRESSION` +
`EDGE_MARK_RECALL_REGRESSION` (`MIXED`) · known-construct stress **not
executed** · original B3-L11 holdout **unopened** ·
**`FROZEN_VERIFIER_REPRESENTATION_SEARCH_STOP_RULE` applied → next research
step `SUPERVISED_WATERMARK_LOGO_DATA_DESIGN`** · B3-L13, B3-L14A and B3-L15A
unchanged · `EDGE_SCAN_PROPOSAL_CONTRACT_FROZEN_AFTER_B3_L15A` ·
`SCAN_ONLY_CURRENT_REPRESENTATION_DOMINATED_BY_EXISTING_EVIDENCE` ·
`TEXT_POLICY_GAP` unresolved · `NATURAL_POSITIVE_EVIDENCE_MISSING`.

## 1. The finding in one sentence

Swapping the CLIP ViT-L/14 embedding for DINOv2-base under the identical
frozen proposal architecture, crops, labels, folds, linear recipe and grid
does not produce a linear separation at any threshold: the B3-L14A edge
gate passes throughout, but new clean review is 10 / 10 / 8 / 5 / 0 of 12
across 0.20–0.80 (worse than CLIP's 10 / 9 / 2 / 2 / 1 except at 0.80),
and the only clean-passing threshold, 0.80, loses broad recall (154/168,
medium translucent text 6/12, translucent graphical watermark 10/12,
EDGE_MARK 8/12).

## 2. What was frozen and what was reused

* Proposal architecture: B3-L15A exact — frozen union (OWLv2 0.25 /
  Grounding DINO 0.25/0.25 / Florence-2 presence) OR `EDGE_SCAN_PROPOSAL_V1`
  (0.16·min tiles, spacing ≤ 0.09·min, GT coverage ≥ 0.95); no NMS, no face
  feature, no threshold, prompt, IoU or scan change. The proposal ceiling
  was re-verified from the same captures and is identical to B3-L15A (B3-L11
  dev 166/168 with EDGE_MARK 12/12; B3-L14A dev 192/192).
* Scan-only hypothesis: rejected on existing evidence (B3-L15A: scan-tile
  clean survivor images 2 at 0.50 and 2 at 0.65 against a 1/12 ceiling; at
  0.80 the combined union already misses EDGE_MARK 9/12 and scan-only recall
  cannot exceed it). No embedding was spent on it.
* Verifier: `facebook/dinov2-base` @ `f9e44c81…` (apache-2.0 per the
  official card and API), official BitImageProcessor defaults (RGB → shortest
  edge 256 bicubic → centre crop 224 → ImageNet mean/std), `pooler_output`
  (final-LayerNorm [CLS]) 768-d, L2-normalized; the only candidate; same 15 %
  crop, same `LogisticRegression` recipe, same grid, same leave-one-group-out
  folds (8 train / 4 evaluation bases per fold, base leakage 0).
* Embeddings: 19,607 (l11_dev 9,602 + l14a_dev 10,005), proposal identity
  exact against B3-L15A on 192 + 192 records; labels positive 3,353 / clean
  negative 525 / excluded 15,729 (identical to B3-L15A by construction);
  classifier fits 3 (OOF folds only; no final fit); peak RSS 1.3 GB; no guard
  trips; detectors never loaded.

## 3. OOF development table

| Threshold | Clean new allow→review (≤ 1/12) | Broad overall (≥ 160/168) | Broad failed | B3-L14A edge gate | Eligible |
|---|---|---|---|---|---|
| 0.20 | 10/12 | 166 | J1 | ✓ (192/192) | ✗ |
| 0.35 | 10/12 | 165 | J1 | ✓ | ✗ |
| 0.50 | 8/12 | 164 | J1, J9 (EDGE 10/12) | ✓ | ✗ |
| 0.65 | 5/12 | 164 | J1, J9 (EDGE 10/12) | ✓ (191/192, min cell 11/12) | ✗ |
| 0.80 | **0/12** | 154 | J2, J5 (MEDIUM 6/12), J6 (graphical 10/12), J9 (EDGE 8/12) | ✓ (187/192, min cell 11/12) | ✗ |

Bypass 0, downgrade 0 at every threshold. Selection: NONE.

Descriptive (same OOF scores): clean survivors at 0.50 come from Grounding
DINO boxes on 8 clean images, Florence boxes on 3 and scan tiles on 5; the
persistent clean hard negatives are again the Grounding DINO boxes (one
survives even at 0.80). Compared with CLIP, DINOv2 scores positive scan tiles
lower (151 of 336 at ≥ 0.80 vs 239) and clean scan tiles slightly higher (414
of 480 below 0.20 vs 421), so the representation swap moved both sides in the
wrong direction for this task; matched detector positives remain high
(Grounding DINO 1,569 of 1,662 and Florence 1,141 of 1,211 at ≥ 0.80).

## 4. What is and is not established

* Established (controlled, 12 bases, one frozen representation each): under
  the frozen proposal architecture neither the CLIP ViT-L/14 nor the
  DINOv2-base embedding with a fixed linear head separates the union's clean
  hard negatives from controlled marks at a recall-preserving threshold on
  this corpus. This is a statement about these two frozen representations and
  this recipe on this corpus, not about visual verification in general.
* Not established: natural marks, real logos, production rates, other
  representations or heads (none tried, by the stop rule).

## 5. Why the study stops here, and what the stop rule closes

No threshold satisfies clean ≤ 1/12, broad J2–J12 and the edge gate together.
No second representation, non-linear head, crop, classifier, threshold or
proposal change was made; the known-construct stress gate and the original
B3-L11 holdout were not run (no G4–G5 DINOv2 embeddings, no B3-L11 holdout
captures, no lock, no marker). By
`FROZEN_VERIFIER_REPRESENTATION_SEARCH_STOP_RULE`, B3 verifier shopping ends:
SigLIP, OpenCLIP, DINOv2-large, new heads, thresholds and crops are not tried.

## 6. Exact next step (owner decision; none taken here)

`SUPERVISED_WATERMARK_LOGO_DATA_DESIGN`: a pre-registered data-design study
for a supervised watermark/logo detector or verifier — label schema, source
policy for natural positives (the standing `NATURAL_POSITIVE_EVIDENCE_MISSING`
gap), clean-negative authority beyond the 12/20 owner-labelled avatars,
base-disjoint splits and the same review-only gate structure — with the
deterministic edge scan kept as the frozen proposal channel. Canonical
`TEXT_POLICY_GAP` stays open. Historical note: approval deployment was a
blocker in earlier B3 reports, but the separate backend rollout
(`approveAvatarCandidate`, `getAvatarJobCandidates`,
`getCurrentAvatarGenerationStatus`; soft needs_review) was completed
before/independently of this evidence correction; it is not a current
B3-L16A research blocker.

## 7. Safety

New detector inference 0 · DINOv2 embeddings 19,607 (development only) ·
classifier fits 3 · model/license metadata downloads only; raw image
transmission, Azure, OpenAI image and external vision 0 · production writes 0
· builds/deploys 0 · live decision diff 0 · originals **28/28** unchanged ·
original B3-L11 holdout unopened · Rater C artifacts untouched.

## 8. Provenance-only metadata correction (post-merge; `PROVENANCE_ONLY_METADATA_CORRECTION`)

Classification `RESULT_METADATA_COPY_FORWARD_ERROR`. The merged aggregate's
`classifier.input` read "L2-normalized CLIP image embedding" although the same
artifact's verifier block records `facebook/dinov2-base`, `pooler_output`,
768-d, L2-normalized; the string came from the shared frozen recipe dict
(identical hyperparameters across B3-L13/B3-L15A/B3-L16A by contract) whose
descriptive label named CLIP. Corrected value: "L2-normalized DINOv2
pooler_output image embedding". The recipe module is untouched, so the
contract digest `b6a22d71eb0e…` and the freeze commit are unchanged. No
performance recomputation, no embedding re-run, no classifier refit, no
inference, no contract change, no verdict change (still
`DINOV2_VERIFIER_FAILED_DEVELOPMENT`, selected threshold NONE, stress not
executed, holdout unopened). The stale "separate release blocker" wording in
section 6 was replaced by the historical note above; the pre-registration
document keeps its original text as a frozen record and the note applies to it.
