# G004 watermark runtime-evidence-authority fix — 2026-08-31

Product decision: REVIEW_WITH_REDACTED_EVIDENCE_PARITY (approved).

## Why runtime and offline diverged

The watermark classifier derives `token_quality` from raw OCR token text.
Raw OCR is process-local by privacy contract and was never serialized, so:

- runtime (live Florence OCR) could reach the `token_quality=implausible`
  strong-overlay branch and hard-reject;
- the redacted offline/recovery evidence could never reconstruct that
  semantic, so the same candidates classified `ambiguous_text_evidence`.

SAME-20 forensic examples (evidence only, never special-cased in code):
P02_C01, P03_C02, P05_C03 — identical stored/runtime evidence bands
(single region, small, corner/edge, confidence unknown,
sourceConsistency inconsistent or not_available), runtime reject vs
offline allow.

## The fix (no thresholds touched)

1. **Derive once, serialize the category, classify everywhere.**
   `_region_evidence` now derives every raw-text-dependent semantic
   (`token_quality`, `artifact_hint`) before redaction; the policy core
   (`_decide`) consumes ONLY typed fields. Typed per-region evidence is
   serialized (`watermark_evidence_v2_token_quality_derived_v1`:
   kind / confidenceBand / areaBand / location / overlayLike /
   tokenQuality / sourceConsistent / repeated / artifactHint — all
   categorical, no text, no bbox, no coordinates), and
   `classify_watermark_evidence_document` re-classifies from the serialized
   evidence with identical results (locked by round-trip tests).
2. **Categorical policy correction.** A SINGLE, non-repeated token with
   confidence band below `high` and `token_quality=implausible` no longer
   satisfies strong-overlay hard reject — even when sourceConsistency is
   `inconsistent` or `not_available`. It falls to the existing
   `generated_text_artifact` REVIEW branch. Hard reject still requires
   strong corroboration: repetition, or high-confidence implausible /
   artifact-hint overlay evidence. Numeric thresholds: unchanged
   (HIGH/MEDIUM confidence, area bands — 0 deltas).
3. **Legacy evidence** without the typed schema is never re-classified and
   never gains a stronger rejection from field absence
   (`classify_watermark_evidence_document` returns None; consumers keep the
   stored legacy decision; missing quality maps to `unknown`).

## Versions

| Contract | Old | New |
| --- | --- | --- |
| Watermark policy | `watermark_policy_v3_generated_artifact_only_v1` | `watermark_policy_v4_runtime_evidence_parity_v1` |
| QA contract | `avatar_qa_v6_unique_mark_applicability_v1` | `avatar_qa_v7_watermark_evidence_parity_v1` |
| Watermark evidence schema | (unversioned bands) | `watermark_evidence_v2_token_quality_derived_v1` |

Calibration evaluation version unchanged
(`g004_calibration_evaluation_v3_watermark_artifact_only` — aggregation
semantics untouched).

## Fresh local SAME-20 golden (watermark v4 / QA v7)

`out/g004-watermark-evidence-authority-local-20260831-v1.json`:
**hardPass 8 / needsReview 12 / hardReject 0 / requiredSignalUnavailable 0.**

Construction: fresh offline full-QA rerun (Gap-A-fixed v7 code, same stored
v9 primitives + evaluation evidence + corrected context as the historical
golden) with the watermark axis taken from the captured attempt-#3 runtime
evidence — the exact deployed image, candidates, and model stack. The three
runtime rejects were re-classified by calling the NEW canonical classifier on
typed evidence reconstructed from the captured bands plus code-level proofs
(strong_overlay at confidence band `unknown` implies overlay_like,
non-repeated, source-inconsistent/unavailable, token_quality implausible).
All three return `generated_text_artifact` / review; the 17 allow-class
candidates are unchanged by the policy. Unrelated-axis drift vs the
historical golden: **0** (the only per-candidate change is the designed
watermark reject→review plus the `generated_text_artifact` review reason).

A local Florence re-extraction was deliberately NOT used as golden authority:
local transformers is 5.2.0 while the deployed runtime pins 4.57.6, so a
local extraction would introduce a different model-stack authority; the
captured exact-runtime evidence is the higher-fidelity local source. The
one authorized fixed-source SAME-20 runtime run re-derives all evidence on
the exact deployed stack and is the final arbiter.

Historical artifacts (v9 evidence, offline v1/v2 goldens, watermark contract
offline reports) remain immutable history; none were rewritten.
