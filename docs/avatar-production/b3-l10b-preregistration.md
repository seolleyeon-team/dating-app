# B3-L10B — pre-registration: FLORENCE_OCR_TWO_FEATURE_STUDY_V1 + TEXT_CONSTRUCT_ROBUSTNESS_V1

Frozen **before any two-feature candidate metric was computed and before any
G4–G5 feature value was read** (contract digest `390251927491…`, produced by
`avatar_ocr_two_feature.contract_digest()` and checked in CI). Designation:
**`DEVELOPMENT_DESIGNED`** — the G1–G3 distributions of both features were
published in B3-L10A (clean tokens 14 / 21.5 / 54, opaque 13, translucent
13–15; score medians −1.21 / −0.61 / −0.75), so nothing here is a discovery
and G1–G3 performance is not validation.

| Item | Value |
|---|---|
| Version / evidence | `FLORENCE_OCR_TWO_FEATURE_STUDY_V1` · `G004_UNCALIBRATED_OCR_TWO_FEATURE_EVIDENCE` |
| Features (only these two) | `rawSequenceScore` = `UNCALIBRATED_DISCRIMINATION_FEATURE` (`scoreSource = florence_beam_sequence_score`, `scoreCalibrated = false`, single-region rows only) · `outputTokenCount` = `UNCALIBRATED_AUXILIARY_FEATURE` |
| Rule form | `rawSequenceScore >= SCORE_THRESHOLD AND outputTokenCount <= TOKEN_CAP` — monotonic 2D only; no classifier, no fit, no per-family thresholds |
| Directions (frozen) | score `positive_higher`, tokens `positive_shorter` (B3-L10A development evidence + semantics audit) |
| Score thresholds | the nine B3-L10A pre-registered quantile values, **verbatim**: −1.42351, −1.13944, −1.066554, −0.918332, −0.748467, −0.700672, −0.663906, −0.613713, −0.592678. No new score threshold; the single-score hypothesis is closed and not refined |
| Token caps | **16, 24, 32** (coarse; never densified) |
| Candidates | 9 × 3 = 27 |
| Gate A–F | A clean proxy ≤ 0.10 (N = 12 → ≤ 1/12; N = 8 → 0/8) · B opaque ≥ 0.90 (≥ 11/12; 8/8) · C translucent ≥ 0.90 · D single-region coverage 100 % · E `scoreCalibrated = false` · F decision diff 0 |
| Selection | lowest clean false-escalation → highest min(opaque, translucent) → less restrictive (larger) token cap → more permissive (lower) score threshold; frozen as `TWO_FEATURE_SEPARABILITY_RULE_V1` (not a policy, confidence or production rule) |
| Validation | G4–G5 = `FEATURE_SPECIFIC_FROZEN_VALIDATION_SPLIT_V2`, once, behind `ocr_two_feature_v1_validation.lock`, only if the dual-feature exposure audit is clean for **both** features; otherwise `BLOCKED_NEW_HELDOUT_REQUIRED` |
| Robustness | `TEXT_CONSTRUCT_ROBUSTNESS_V1` after a validation pass only; rule unchanged; new constructs below; local Florence inference on the 8 G4–G5 bases |

Immutable prior results: V1, V2, V3, B3-L9 `TEXT_POLICY_SHADOW_HOLDOUT_FAILED`,
B3-L10A `FLORENCE_SEQUENCE_SCORE_NOT_SEPARATING` (validation executions 0,
G4–G5 score values unseen), `TEXT_POLICY_GAP` unresolved,
`GRAPHICAL_DETECTOR_STUDY_REQUIRED`, `NATURAL_POSITIVE_EVIDENCE_MISSING`.

## 1. `outputTokenCount` exact semantics (fresh audit, main `0719d411`, transformers 4.57.6)

`florence2_visual._run_task` calls `Florence2ForConditionalGeneration.generate`
(BART encoder–decoder text backbone; `is_encoder_decoder = true`) and reads
`generated.sequences`; `_output_token_count` returns `len(sequences[0])`, the
**top beam's decoder output length**. It includes the decoder start token
(id 2), the forced BOS token (id 0) and the EOS token (id 2) from the pinned
`generation_config`; encoder/prompt tokens are **not** counted; the upper bound
is `max_new_tokens (1024) + 1`. The value is a generation-length feature bound
to the pinned model/revision — not confidence, not probability, not OCR
correctness. (Consistency check on the known development rows: one 6-letter
word + 8 location tokens + 3 special tokens ≈ 13.)

## 2. Dual-feature exposure audit of G4–G5 (before this freeze)

Searched repo docs/scripts/tests, every local B3-L4…L10A aggregate JSON /
stdout / stderr, PR bodies and memory notes for `rawSequenceScore` and
`outputTokenCount` values. B3-L10A's evaluator loaded the validation rows but
computed and printed inventories for **development only** (its report has no
`validation` key; selection was NONE so `split_eval(holdout)` never ran); the
B3-L10A coverage check printed counts/enums only; B3-L9 printed typed geometry
fields for G4–G5, never a score or token count. Values exist only inside the
raw restricted captures, which is not "seen". Conclusion:
`validationScoreValuesPreviouslySeen = false` and
`validationTokenCountValuesPreviouslySeen = false` → the split is admissible
once.

## 3. Overfit risk named up front

The controlled positives are short fixed synthetic strings (`SAMPLE`, 13–15
tokens). A cap that passes on them may be learning *synthetic word length*,
not a watermark property. That is why (a) caps are coarse, (b) selection
prefers the **less** restrictive cap, and (c) a G4–G5 pass yields only
`SUPPORTED_ON_EXISTING_FIXED_TEXT_CONSTRUCT` until the robustness challenge
below is met with the rule unchanged.

## 4. TEXT_CONSTRUCT_ROBUSTNESS_V1 (frozen before any inference)

Renderer: `avatar_owlv2_challenge_v2.render_family` text kind (PIL default
font), rel size 0.06, centre anchor (0.50, 0.62) — the F3/F4 geometry;
opaque = alpha 1.00 with stroke, translucent = alpha 0.35 without. Bases: the
8 G4–G5 avatars (rule already frozen; no selection). All strings pass the
real-trademark blocklist; `SAMPLE`/`NOVA` are not reused.

| Code | Category | Length / words |
|---|---|---|
| R1 | A_SHORT_ONE_WORD | 5 chars |
| R2 | B_LONG_ONE_WORD | 11 chars |
| R3 | C_TWO_WORD_PHRASE | 2 words |
| R4 | D_SHORT_ALPHANUMERIC | 5 chars, letters + digits |
| R5 / R6 | E_CHARACTER_WIDTHS (wide / narrow glyphs) | 6 chars each |

12 conditions × 8 bases = 96 `ROBUSTNESS_CHALLENGE` rows. Criteria: A overall
sensitivity ≥ 0.90 · B each required category ≥ 0.80 · C opaque ≥ 0.90 · D
translucent ≥ 0.90 · E rule unchanged · F `scoreCalibrated = false` · G
decision diff 0. Rows whose OCR is not single-region cannot satisfy the rule
and count as misses. Clean burden authority stays the G4–G5 validation result;
no threshold or cap is revisited.

## 5. Verdicts

`FLORENCE_TWO_FEATURE_NOT_SEPARATING` (no eligible development candidate) ·
`BLOCKED_NEW_HELDOUT_REQUIRED` (audit not clean) ·
`FLORENCE_TWO_FEATURE_VALIDATION_FAILED` · `FLORENCE_TWO_FEATURE_CONSTRUCT_OVERFIT`
(validation pass, robustness fail — a normal, important failure) ·
`FLORENCE_TWO_FEATURE_SEPARABILITY_ROBUSTNESS_SUPPORTED` (all three pass; still
not calibrated, not policy, not production) · `BLOCKED_LOCAL_RESOURCE_SAFETY`.

Forbidden in every artifact (enforced in code and CI): high/medium/low
confidence labels, any calibration (logistic, temperature, isotonic, Platt),
any claim that confidence is calibrated, that a confidence band is validated,
that the text policy or production is ready or validated. No worker, policy,
env, build or deploy change; graphical workstream untouched
(`GRAPHICAL_DETECTOR_STUDY_REQUIRED`); `approveAvatarCandidate` deployment
remains a separate release blocker.
