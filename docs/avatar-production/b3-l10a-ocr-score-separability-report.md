# B3-L10A — Florence uncalibrated OCR sequence-score separability study

Offline, analysis only. **0 Florence inferences** (every analysed row already
carried the PR #100 shadow score), 0 OWLv2, 0 external calls, no policy or
confidence-band change, no worker/env/build/deploy change. Aggregate only.
Contract digest `8092c3ea2f34…` frozen in
[b3-l10a-preregistration.md](b3-l10a-preregistration.md) before any score
value was displayed.

**Verdict: `FLORENCE_SEQUENCE_SCORE_NOT_SEPARATING`** (on the frozen grid) ·
validation executed **0** (G4–G5 score values remain unseen) · confidenceBand
changed **NO** · watermark policy changed **NO** · decision diff **0** ·
`TEXT_POLICY_GAP` unresolved · `GRAPHICAL_DETECTOR_STUDY_REQUIRED` ·
`NATURAL_POSITIVE_EVIDENCE_MISSING`.

The feature under study is an **UNCALIBRATED_DISCRIMINATION_FEATURE**:
`scoreSource = florence_beam_sequence_score`, `scoreCalibrated = false`, a
beam-search log-probability of the whole generated OCR string, attributed to a
region only when `regionCount == 1`. It is not a calibrated OCR probability,
not a per-region confidence, not the probability that text is correct or that
a watermark is present. (This corrects the B3-L9 wording that called it a
field carrying probability.)

## 1. The finding in one sentence

The raw sequence score ranks injected text watermarks above clean-avatar
incidental OCR almost perfectly (development ROC AUC 0.99; opaque vs clean
1.00, translucent vs clean 0.98), but on the pre-registered nine-point quantile
grid no boundary keeps clean false-escalations ≤ 1/12 while catching ≥ 11/12
translucent watermarks — the lowest-scoring translucent rows overlap the
highest-scoring clean rows — so the frozen gate is not met and, per contract,
no finer search was made and the validation split was not opened.

## 2. Shadow contract audit (PR #100, fresh on main `94d239a4`)

Intact: scores requested with `output_scores=True`; unsupported-kwargs
fallback yields `scoreAvailable=false` and plain OCR (decision-neutral); the
score lives only in `shadowOcrEvidence`; the parser's region confidence reads
a `scores`/`confidences` key that is never written, so
`VisualRiskRegion.confidence` is `None` and `confidenceBand` is `unknown`;
consumers copy by allowlist. All verified by the new tests.

## 3. Existing capture coverage and exposure audit

| Group | development | validation | shadow present | score available | single region |
|---|---|---|---|---|---|
| Clean human-negative | 12 | 8 | 20/20 | 20/20 | 20/20 |
| TEXT_WATERMARK_OPAQUE | 12 | 8 | 20/20 | 20/20 | 20/20 |
| TEXT_WATERMARK_TRANSLUCENT | 12 | 8 | 20/20 | 20/20 | 20/20 |

All rows: `scoreSource = florence_beam_sequence_score`, `scoreCalibrated =
false`, `numBeams = 3`, `lengthPenalty = 1.0`, `attributionScope =
single_region`. New Florence inference: **0**. Exposure audit: no script,
aggregate, stdout, report or memory note had ever printed or analysed a
`rawSequenceScore` value; values existed only inside the raw restricted
captures. G4–G5 was therefore admissible as a
`FEATURE_SPECIFIC_FROZEN_VALIDATION_SPLIT` (not a globally untouched holdout:
B3-L9 opened it for the geometry policy). It was never opened here, so its
score values are still unseen.

## 4. Development inventory (G1–G3, aggregate)

| Group | n | rawSequenceScore min / Q1 / median / Q3 / max | outputTokenCount min / median / max |
|---|---|---|---|
| Clean | 12 | −1.764 / −1.527 / −1.212 / −1.123 / −0.992 | 14 / 21.5 / 54 |
| Opaque | 12 | −0.713 / −0.633 / −0.612 / −0.580 / −0.569 | 13 / 13 / 13 |
| Translucent | 12 | −1.086 / −0.837 / −0.749 / −0.700 / −0.638 | 13 / 14 / 15 |

Direction (frozen rule, development medians): **positive_higher** — injected
text scores higher than incidental clean OCR. Descriptively, the clean strings
are also longer (the score is a length-normalised sequence log-probability, so
longer hallucinated strings score lower); token count was not part of the
contract and was not evaluated as a feature.

## 5. Development threshold table (pooled quantile grid; role `SEPARABILITY_CANDIDATE_THRESHOLD`)

| Quantile | threshold | clean proxy FP | opaque | translucent | combined | balanced acc. | A–F |
|---|---|---|---|---|---|---|---|
| 0.10 | −1.4235 | 8/12 | 12/12 | 12/12 | 1.00 | 0.67 | ✗ A |
| 0.20 | −1.1394 | 5/12 | 12/12 | 12/12 | 1.00 | 0.79 | ✗ A |
| 0.30 | −1.0666 | 2/12 | 12/12 | 11/12 | 0.96 | 0.90 | ✗ A |
| 0.40 | −0.9183 | 0/12 | 12/12 | 9/12 | 0.88 | 0.94 | ✗ C |
| 0.50 | −0.7485 | 0/12 | 12/12 | 6/12 | 0.75 | 0.88 | ✗ C |
| 0.60 | −0.7007 | 0/12 | 11/12 | 4/12 | 0.63 | 0.81 | ✗ C |
| 0.70 | −0.6639 | 0/12 | 10/12 | 1/12 | 0.46 | 0.73 | ✗ B C |
| 0.80 | −0.6137 | 0/12 | 8/12 | 0/12 | 0.33 | 0.67 | ✗ B C |
| 0.90 | −0.5927 | 0/12 | 4/12 | 0/12 | 0.17 | 0.58 | ✗ B C |

Coverage D = 100 %, E `scoreCalibrated=false` preserved, F decision diff 0 at
every candidate. ROC AUC positive-vs-clean 0.99, average precision 1.00
(rank-based; small controlled evidence, not a production metric).
**Selected threshold: NONE.** No freeze record, no validation lock.

## 6. What is and is not established

* Established (controlled, 36 development rows): the uncalibrated beam score
  carries strong rank discrimination between an injected single-word watermark
  and Florence's single incidental clean-avatar OCR region; opaque watermarks
  are fully separated at the 0.40 quantile (0/12 clean, 12/12 opaque).
* Established: translucent watermarks overlap the clean tail — at any grid
  point with 0–1 clean escalations at least 3/12 translucent rows are missed;
  the pre-registered gate (≤ 0.10 clean and ≥ 0.90 on both families) is not
  met, and the contract forbids a finer boundary search on this data.
* Not established: anything about calibration, confidence bands, policy
  actions, natural watermarks (`NATURAL_POSITIVE_EVIDENCE_MISSING`), or the
  graphical channel (`GRAPHICAL_DETECTOR_STUDY_REQUIRED`).

## 7. Verdicts

* `FLORENCE_SEQUENCE_SCORE_NOT_SEPARATING` (frozen-grid gate on development).
* Validation: not executed (0); G4–G5 score values still unseen.
* `TEXT_POLICY_GAP` unresolved; no confidence-band research continues under
  this contract.

## 8. Exact next step (owner decision; none taken here)

The score is discriminative but not gate-separating on the frozen grid, and
the deficit is concentrated in translucent rows that score like clean OCR.
Two honest options, both new pre-registrations: (1) treat this as closed —
the uncalibrated score alone does not reach the pre-registered bar; (2) a new
study on **new held-out constructs** (not G1–G3 again) that pre-registers a
two-feature evidence design (sequence score together with the already
runtime-available `outputTokenCount`) and a calibration contract with
reliability assessment — the G4–G5 score values, still unseen, could serve
as one frozen validation split but not as development. No policy, confidence
band or production change follows from this study; `approveAvatarCandidate`
deployment remains a separate release blocker.

## 9. Safety

Florence 0 · OWLv2 0 · Azure/external 0 · production writes 0 · builds/deploys
0 · live decision diff 0 · originals **28/28** unchanged · V2/V3/B3-L9 locks
untouched · Rater C artifacts untouched.
