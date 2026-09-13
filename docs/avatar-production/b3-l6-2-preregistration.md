# B3-L6.2 — pre-registration: threshold selection, H4-DIRECT-1, holdout one-shot

Frozen **before any adjudicated label value was used in a performance
calculation**. The two first-pass rater exports had been ingested only for
schema validation, contradiction checks and inter-rater agreement (telemetry)
when this was written; no precision, recall or threshold number had been
computed. Encoded in `scripts/avatar_owlv2_threshold_selection.py` and asserted
by `tests/test_avatar_owlv2_threshold_selection.py`.

## 1. Unchanged inputs (from B3-L6 / B3-L6.1)

| Item | Value |
|---|---|
| Threshold grid | 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50 |
| Prompts | `a logo`, `a watermark`, `a brand emblem`, `a graphic symbol` — mode `combined` |
| Development groups | G1, G2, G3 (12 images) |
| Holdout groups | G4, G5 (8 images) |
| Gate | `owlv2_provisional_shadow_gate_v1`: A ≥ 0.80, B ≤ 0.10, C = 20/20, D = 0, E = 0 |
| Detector output | the B3-L6 raw capture (40 conditions, floor 0.01) — no re-inference |

The prompt set is not tuned from labels. The B3-L6 observation that only
`a graphic symbol` found the *synthetic* injected mark is descriptive; it does
not remove any query.

## 2. Precision truth semantics

The detector-truth field is `visibleGraphicalMark`: `yes` = positive, `no` =
negative, `uncertain` = unresolved and **excluded**. `primaryLabel` is never
converted into detector truth. `markIntegration` / `markType` are secondary
analysis only. If there is no detector positive, or no human positive,
precision / recall are `NOT_ESTIMABLE` — never 0 or 1 by convention — and
criterion A cannot pass.

## 3. Selection algorithm — `OWLV2_THRESHOLD_SELECTION_V1`

On **development groups only**, a grid threshold is eligible when all of A–E
hold on development data. If several are eligible, **the lowest eligible
threshold is selected** (tie-break frozen here): among thresholds that already
satisfy the specificity and safety conditions, the lowest preserves the most
mark sensitivity. If none is eligible: `NO_THRESHOLD_SELECTED` and
`OWLV2_PILOT_GATE_FAILED_DEVELOPMENT`. Holdout is never used to choose.

The selector function takes a development table only; there is no parameter by
which holdout metrics can enter it (tested).

## 4. Criterion B semantics

A "new detector-induced review" is a human-**negative** clean avatar whose
current live watermark action is `allow` and whose H4 action is `review`. An
existing `review`/`reject` is not detector burden. Denominator = adjudicated
human-negative clean avatars. `fp` (a model metric) and this burden (a policy
metric) are reported separately.

## 5. H4-DIRECT-1 — runtime-capable shadow

```
IF   any OWLv2 combined-prompt detection has score >= SELECTED_THRESHOLD
THEN shadowAction = max(currentAction, "review")
```

* No Florence region is a prerequisite (the structural limit found in B3-L6:
  H3 flagged 10/20 injected marks that OWLv2 localized 20/20, because it could
  only escalate existing Florence regions).
* A live `reject` or `review` is never downgraded.
* Human-only fields — `primaryLabel`, `visibleGraphicalMark`, `markIntegration`,
  `markType`, `labelConfidence`, `allVisibleClasses` — are evaluation truth and
  are **rejected** as runtime inputs (tested). In particular
  `markIntegration != scene_native` is not a runtime rule.
* H3-A / H3-B are not threshold-tuned to manufacture 20/20.

## 6. Order of operations, and the one-shot holdout

1. Two-rater ingest → unresolved items → blinded third adjudication (image only,
   opaque id, neither prior vote, no detector output). The agent never adjudicates.
2. Adjudicated artifact frozen (version, rater count, third adjudicator used,
   resolved / uncertain counts). Raw per-image labels stay restricted-local.
3. Development-only selection → threshold frozen with its inputs digest.
4. Development H4-DIRECT-1 check (no re-selection afterwards).
5. Holdout G4–G5 evaluated **exactly once**, only after 3 — a lock file refuses
   a second evaluation, and evaluation without a frozen threshold is refused.
   After holdout: no threshold, prompt or rule change.
6. Full 20-image gate `owlv2_provisional_shadow_gate_v1`, criteria unchanged.

## 7. Wording

Results are `PROVISIONAL_G004_SHADOW_EVIDENCE` / `G004_CLEAN_AVATAR_PILOT_PRECISION`
on a 20-image pilot. Wilson intervals are reported; a CI lower bound is not the
gate. Prohibited: production validated / production precision proven / live
ready. Human agreement (telemetry) and model performance are reported
separately: low agreement is ground-truth uncertainty, not detector error.
