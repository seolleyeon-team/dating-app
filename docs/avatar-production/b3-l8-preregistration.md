# B3-L8 — pre-registration: AVATAR_WATERMARK_DUAL_CHANNEL_V3

Frozen **before any new Florence development number was computed** (contract
digest `7e0281db982a…`, computed from every rule below by
`avatar_dual_channel_v3.contract_digest()` and checked in CI). Gate v1
(`owlv2_provisional_shadow_gate_v1` → `OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT`)
and gate V2 (`OWLV2_CONTROLLED_CHALLENGE_GATE_V2` →
`OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT`, `H4_DIRECT_SHADOW_NOT_SUPPORTED`,
`NATURAL_POSITIVE_EVIDENCE_MISSING`) are left exactly as they ended. V3 is a
separate hypothesis, not a replacement of either.

| Item | Value |
|---|---|
| Version | `AVATAR_WATERMARK_DUAL_CHANNEL_V3` |
| Evidence label | `G004_DUAL_CHANNEL_CONTROLLED_EVIDENCE_V3` |
| Recall label | `CONTROLLED_CHALLENGE_ACTION_RECALL` (controlled feasibility, not a production SLA) |
| Channel T | `CANONICAL_FLORENCE_TEXT_POLICY` — the canonical policy action, unchanged |
| Channel G | `OWLV2_GRAPHICAL_SUPPLEMENT` — OWLv2 ≥ 0.25 → review only |
| OWLv2 | `google/owlv2-base-patch16-ensemble` @ `cfd3195ba4ea9592eec887ded089f4c08eff231d` |
| OWLv2 threshold | **0.25**, authority `DEVELOPMENT_SELECTED_GRAPHICAL_SUPPLEMENT_THRESHOLD` (selected from B3-L7 development evidence for the role-split hypothesis; the unseen G4–G5 holdout is the independent evidence; not changed in V3) |
| Prompts | `a logo`, `a watermark`, `a brand emblem`, `a graphic symbol`, combined; no addition, removal, per-prompt or per-family threshold |
| Florence | `florence-community/Florence-2-large-ft` @ the Dockerfile `QA_FLORENCE_REVISION` (read fresh, `26b734a5…`), tasks `<OCR_WITH_REGION>` + `<OD>`, num_beams 3, max_new_tokens 1024 (production adapter path) |
| Truth (clean) | `OWNER_DESIGNATED_RATER_A_REFERENCE_TRUTH`, `visibleGraphicalMark` no = 20 / yes = 0 / uncertain = 0 |
| Split | development G1–G3, holdout G4–G5 (participant group, unchanged) |
| Holdout lock | `v3_holdout_evaluated.lock` (separate from the V2 lock); second attempt fails closed |

## 1. Hypothesis

B3-L7 showed that a single OWLv2 threshold cannot be both quiet on clean
avatars (≥ 0.25) and sensitive to text watermarks (≤ 0.05). V3 tests the
model-role separation as a runtime-capable, decision-neutral shadow:

* text / OCR-like watermarks → the **existing canonical Florence watermark
  policy** (`watermark_policy_v4_runtime_evidence_parity_v1`), untouched;
* graphical / logo-like marks → the OWLv2 supplement at 0.25.

Question: does the composition keep the clean review burden low while raising
controlled-positive coverage?

## 2. Channel T — exact definition (frozen, fresh provenance audit on main `802e89d5`)

Channel T is **not** "Florence OCR region exists → review". It is the
production decision:

```
regions  = avatar_generation.analysis.visual_risk.analyze_florence_visual_risk_outputs(tasks, image_size)
decision = avatar_generation.analysis.watermark.evaluate_watermark_risk(regions, source_regions=(), image_size)
textAction = decision.watermark_qa_action        # allow | review | reject
```

Provenance: `qa_signals.compute_candidate_qa_signals` → `_add_visual_signals`
→ `evaluate_watermark_risk(visual.regions, source_regions=<source visual
risk regions>, …)`. In production the worker runs in
`CANONICAL_AZURE_WORKER_MODE`, for which `_source_visual_risk_enabled` is
False, so `source_visual_risk is None` and `source_regions=()`. The primary
face bbox only relabels person regions and never reaches the text-like filter.
Channel T therefore reproduces the worker contract exactly; the B3-L4
evaluator's `_policy_row` used the same call. (The B3-L6.3/L7 pilot helper
`current_actions` additionally passed the base clean avatar's regions as
pseudo-source; V3 does **not** do that, because production does not.)

Nothing in the policy — thresholds, token logic, geometry, source logic — is
changed for V3. If the canonical policy misses a text family, that is recorded
as `MODEL DETECTED / POLICY DID NOT FLAG` (or a model miss) and is evidence for
a separate future text-policy task, never a reason to alter V3.

## 3. Channel G and composition (frozen)

```
graphicalHit    = any OWLv2 detection with score >= 0.25 and label in the combined prompt set
graphicalAction = review if graphicalHit else allow          # never reject
V3ShadowAction  = max(textAction, graphicalAction)            # allow < review < reject
```

Escalate-only: a canonical reject can never become review/allow; a canonical
review can never become allow; `hardRejectBypass` must be 0.

Forbidden runtime inputs (refused with an error): `primaryLabel`,
`visibleGraphicalMark`, `markIntegration`, `markType`, `labelConfidence`,
`allVisibleClasses`, construct family fields, ground-truth boxes. Families and
injected boxes are evaluation metadata only.

## 4. Exact Florence evidence reuse (audit before any inference)

For every B3-L7 family the B3-L4 Florence capture may be reused **only** when
(a) a B3-L4 core variant has an identical normalized rendering spec (kind,
text, alpha, relative size, anchor, repetition, stroke) and (b) both
generators produce byte-identical pixels and identical boxes on every base.
Semantic similarity ("corner text", "translucent text") never authorizes
reuse. Verdicts: `EXACT_REUSABLE` / `PARTIALLY_REUSABLE` / `NOT_REUSABLE`.
The historical capture did not record derivative digests, so even an exact
match is reported as `BITWISE_IDENTITY_UNPROVEN` for the historical pixels;
no digest is fabricated. The V3 capture records the derivative digest of
every newly inferred row.

Inference minimisation order: exact reuse → missing **development** rows only
(local Florence, production adapter path) → development evaluation → missing
**holdout** rows only if development passes → holdout once. OWLv2 new calls:
expected 0 (B3-L7 capture reused). The B3-L7 "current action = base clean
proxy" is not used for any V3 efficacy number: every positive row needs the
actual derivative → actual Florence output → canonical policy.

## 5. Clean-negative contract

20 generated avatars, all human-negative under Rater A truth. Baseline is the
actual canonical Florence action. V3 new burden counts **only** canonical
`allow` → V3 `review` caused by the OWLv2 supplement; existing canonical
reviews/rejects are not counted as V3 false-positive burden. `allow` → `reject`
must be 0 (the graphical channel cannot reject).

## 6. Development gate (G1–G3; all must pass)

| # | Criterion | Floor |
|---|---|---|
| A | OWLv2 supplement new clean-review rate | ≤ 0.10 |
| B | V3 overall controlled-positive action recall (all 10 families) | ≥ 0.95 |
| C | TEXT_WATERMARK_OPAQUE V3 action recall | ≥ 0.90 |
| D | TEXT_WATERMARK_TRANSLUCENT | ≥ 0.90 |
| E | GRAPHICAL_WATERMARK | ≥ 0.90 |
| F | LOGO_LIKE_EMBLEM | ≥ 0.90 |
| G | SMALL_CORNER_MARK | ≥ 0.90 |
| H | EDGE_MARK | ≥ 0.90 |
| I | CENTER_OVERLAY_MARK | ≥ 0.90 |
| J | REPEATED_TILED_MARK | ≥ 0.90 |
| K | generative-artifact safety regression (any V3 action below canonical) | = 0 |
| L | hard-reject bypass | = 0 |

BRAND_LIKE_TEXT_AND_SYMBOL (hybrid diagnostic) and GRAPHIC_SYMBOL (graphical
sanity) count in B only. Any failure → `V3_DUAL_CHANNEL_FAILED_DEVELOPMENT`:
holdout metrics are not opened, holdout Florence inference is not run, no
rule/threshold is tuned. Failure is diagnosed as one or more of
`TEXT_MODEL_GAP` (Florence OCR hit < 0.90 on a text family), `TEXT_POLICY_GAP`
(OCR hit ≥ 0.90 but canonical policy flag < 0.90), `GRAPHICAL_CHANNEL_GAP`,
`CLEAN_BURDEN_GAP`, `MIXED`.

## 7. Holdout (G4–G5; exactly once, only after A–L pass)

Same criteria A–L on holdout, evaluated once behind
`v3_holdout_evaluated.lock`. The holdout Florence rows are inferred only after
the development pass marker exists. After the holdout result nothing is
retuned: not 0.25, not the prompts, not the Florence policy, not the family
set, not a floor. Per-family attribution (text / graphical / both / neither)
is descriptive; runtime routing never sees the family.

## 8. Verdict vocabulary

* development + holdout + safety pass → `V3_DUAL_CHANNEL_CONTROLLED_GATE_PASSED`,
  `H4_DUAL_CHANNEL_SHADOW_SUPPORTED_FOR_CONTROLLED_CANARY` (not live-ready);
* development fail → `V3_DUAL_CHANNEL_FAILED_DEVELOPMENT`, `H4_DUAL_CHANNEL_SHADOW_NOT_SUPPORTED`;
* holdout fail → `V3_DUAL_CHANNEL_HOLDOUT_FAILED`, `H4_DUAL_CHANNEL_SHADOW_NOT_SUPPORTED`;
* resource block → `BLOCKED_LOCAL_RESOURCE_SAFETY`.

`NATURAL_POSITIVE_EVIDENCE_MISSING` remains in every outcome: controlled
synthetic positives are not natural watermarks or real brand logos. Decision
diff to live is 0 by construction (analysis only; no worker integration;
`approveAvatarCandidate` deployment stays a separate release blocker).
