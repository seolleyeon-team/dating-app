# B3-L10A — pre-registration: FLORENCE_OCR_SEQUENCE_SCORE_STUDY_V1

Frozen **before any development score value was displayed or any threshold
metric computed** (contract digest `8092c3ea2f34…`, produced by
`avatar_ocr_score_separability.contract_digest()` and checked in CI). This is
a separability study of an **UNCALIBRATED_DISCRIMINATION_FEATURE**. It builds
no policy, no confidence band and no probability; it never changes a
watermark action.

| Item | Value |
|---|---|
| Version / evidence | `FLORENCE_OCR_SEQUENCE_SCORE_STUDY_V1` · `G004_UNCALIBRATED_OCR_SCORE_EVIDENCE` |
| Feature | `shadowOcrEvidence.rawSequenceScore` from the PR #100 shadow telemetry (`scoreSource = florence_beam_sequence_score`, `scoreCalibrated = false`) |
| Semantics | beam-search log-probability of the **whole** generated OCR string; `attributionScope = single_region` only when `regionCount == 1`, otherwise `whole_sequence`. NOT a calibrated OCR probability, NOT a per-region confidence, NOT the probability that the text is correct or that a watermark is present |
| Population | clean human-negative avatars (Rater A truth), TEXT_WATERMARK_OPAQUE, TEXT_WATERMARK_TRANSLUCENT — actual derivatives (B3-L8/L9 captures), single-region rows only |
| Development | G1–G3 (12 clean, 12 opaque, 12 translucent) |
| Validation | G4–G5 (8 / 8 / 8) = **`FEATURE_SPECIFIC_FROZEN_VALIDATION_SPLIT`** — not a globally untouched holdout (B3-L9 opened it for the geometry policy); usable once only because the exposure audit shows its score values were never displayed or analysed before this freeze |
| Validation lock | `ocr_score_v1_validation_evaluated.lock`, exactly once after `ocr_score_v1_threshold_frozen.json` |
| New inference | 0 expected: every row already carries the shadow score |

Immutable prior results: V1 `OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT`, V2
`OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT`, V3 `V3_DUAL_CHANNEL_FAILED_DEVELOPMENT`,
B3-L9 `TEXT_POLICY_SHADOW_HOLDOUT_FAILED` / `TEXT_POLICY_SHADOW_NOT_SUPPORTED`,
`TEXT_POLICY_GAP` unresolved, `GRAPHICAL_CHANNEL_GAP` unresolved
(`GRAPHICAL_DETECTOR_STUDY_REQUIRED`), `NATURAL_POSITIVE_EVIDENCE_MISSING`.
Correction to the B3-L9 report wording: the sequence score is **not** a
"probability-bearing field"; it is an uncalibrated discrimination feature until
a separate calibration study says otherwise.

## 1. PR #100 shadow contract (fresh audit, main `94d239a4`)

`florence2_visual._run_task` asks `generate(return_dict_in_generate=True,
output_scores=True)`; a runtime rejecting those kwargs falls back to plain
generation with `scoreAvailable = false` and `scoreUnavailableReason =
scores_not_supported_by_runtime` — decision-neutral. `_attach_shadow_ocr_evidence`
writes only the `shadowOcrEvidence` namespace; the parser's region confidence
comes from a `scores`/`confidences` key that is never written, so
`VisualRiskRegion.confidence` stays `None` and `confidenceBand` stays `unknown`.
Consumers (`_shadow_ocr_evidence`, `qa_signals`, `qa.py` measurements) copy the
payload by allowlist as telemetry. Decision diff 0.

## 2. Exposure audit of G4–G5 score values (before this freeze)

Searched: repo scripts/docs/tests, all local B3-L4…L9 aggregate JSON and
stdout artifacts, memory notes. `rawSequenceScore` values appear **only** inside
the raw restricted captures (`.jsonl`); no script aggregated, swept, printed or
reported them (the B3-L4/L5 documents mention only the field's existence and
semantics). The coverage check run for this study printed counts and enum
values (availability, scope, regionCount, source, calibrated flag, beams,
length penalty) and **no score value**. Conclusion: `validationScoreValuesPreviouslySeen = false`.

## 3. Frozen study contract

* **Usable row:** `scoreAvailable`, `scoreSource = florence_beam_sequence_score`,
  `scoreCalibrated = false`, `attributionScope = single_region`, `regionCount = 1`,
  finite score. Whole-sequence rows never enter as region scores.
* **Direction:** decided on development only — `positive_higher` if
  median(opaque + translucent) > median(clean), else `positive_lower`; no sign
  or scale is interpreted as a probability.
* **Candidate thresholds:** the 10 %, 20 %, …, 90 % quantile positions of the
  pooled development scores (clean + opaque + translucent). Nine candidates,
  role `SEPARABILITY_CANDIDATE_THRESHOLD`. No fine-tuning, no observed-boundary
  search, validation scores never enter.
* **Metrics per candidate (development):** clean false-escalation proxy rate,
  opaque sensitivity, translucent sensitivity, combined sensitivity, balanced
  accuracy; plus ROC AUC and average precision (rank-based, direction-aware).
  None is a production metric.
* **Gate A–F:** A clean proxy ≤ 0.10 (N = 12 → ≤ 1; N = 8 → 0) · B opaque
  ≥ 0.90 · C translucent ≥ 0.90 · D single-region coverage = 100 % of evaluated
  rows · E `scoreCalibrated = false` preserved · F decision diff = 0.
* **Selection:** among eligible candidates, lowest clean false-escalation →
  highest combined sensitivity → more conservative boundary in the observed
  direction. Frozen as `SEPARABILITY_THRESHOLD_V1` (not a policy, confidence or
  production threshold).
* **Validation:** the frozen threshold applied once to G4–G5 with the same
  A–F; nothing retuned afterwards.

## 4. Verdicts

* no eligible candidate → `FLORENCE_SEQUENCE_SCORE_NOT_SEPARATING`;
* eligible but validation values previously seen → `FLORENCE_SEQUENCE_SCORE_DEVELOPMENT_SEPARABLE_NEW_HELDOUT_REQUIRED`;
* validation pass → `FLORENCE_SEQUENCE_SCORE_SEPARABILITY_SUPPORTED` (means only: the score carries useful discrimination; a separate calibration study B3-L10B with new held-out data would follow — not implemented here);
* validation fail → `FLORENCE_SEQUENCE_SCORE_SEPARABILITY_NOT_SUPPORTED`.

Forbidden in every artifact: HIGH/MEDIUM/LOW confidence labels (use
`SCORE_INTERVAL_*` or numeric thresholds), `CONFIDENCE_CALIBRATED`,
`CONFIDENCE_BAND_VALIDATED`, `TEXT_POLICY_READY`, `PRODUCTION_VALIDATED`,
`LIVE_READY`. Every outcome keeps `TEXT_POLICY_GAP` unresolved,
`GRAPHICAL_DETECTOR_STUDY_REQUIRED` and `NATURAL_POSITIVE_EVIDENCE_MISSING`.
No worker, policy, env, build or deploy change; `approveAvatarCandidate`
deployment remains a separate release blocker.
