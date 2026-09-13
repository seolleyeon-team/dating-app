# B3-L6.2A / B3-L6.3 — owner-designated Rater A truth, development selection, H4-DIRECT-1 pilot

Offline, decision-neutral. No model re-inference, no live policy change, no
detector integration, no build, no deploy. Aggregate only: no per-image label
row, image, filename, UID, path, transcription, box or identity-linked score.

**Pilot verdict: `OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT`**
**Selection: `NO_THRESHOLD_SELECTED`** · **Holdout evaluated: 0** · **H4: `H4_EVIDENCE_INSUFFICIENT`**

Under the owner-designated reference truth the 20-image pilot contains **no
human-positive graphical mark**. Precision is therefore 0.0 at every threshold
where OWLv2 fires on a clean avatar and `NOT_ESTIMABLE` at every threshold
where it does not, so gate criterion A cannot be satisfied anywhere on the
frozen grid. The frozen procedure then forbids holdout and the full gate. This
is a property of the corpus, not a detector failure and not a Rater A failure.

## 1. Truth resolution — `OWNER_RATER_A_RESOLUTION_V1`

Owner decision (B3-L6.2A), superseding the third-adjudicator path:

| Case | Final value |
|---|---|
| A == B | shared value |
| A != B | Rater A |
| A = uncertain | uncertain (excluded from detector truth) |

Recorded as `truthAuthority = OWNER_DESIGNATED_RATER_A_REFERENCE_TRUTH`,
`thirdAdjudicatorUsed = false`. Rater C was not used; its page/export were
neither opened nor parsed nor deleted. Rater B survives as telemetry only and
never overrides A.

This is an **owner policy decision**, not a claim that Rater A is objective
truth, and it is not an independent result from three raters. Wording used here:
`G004_OWNER_RESOLVED_PILOT_TRUTH` / `G004_OWNER_RATER_A_PILOT_PRECISION`.

Implemented as an explicit ingest mode (`--truth-resolution owner-rater-a`);
the default consensus mode and its third-adjudication semantics are unchanged
(tested separately). The resolver takes the two sanitized rater rows and nothing
else: no detector score, Florence output or confidence can enter (tested by
signature). TDD: 12 RED → GREEN.

## 2. Reference truth and telemetry

| | Count |
|---|---|
| Reference rows (Rater A) | 20 |
| `visibleGraphicalMark` yes / no / uncertain | **0 / 20 / 0** |
| Rater A contradictions (hard block) | 0 |
| Rater B contradictions (telemetry) | 0 |
| A/B disagreement, any compared field | 6 |
| A/B disagreement on `visibleGraphicalMark` | 1 (B saw a mark; A did not; A prevails by owner rule) |

Agreement telemetry (N = 20; not a criterion):

| Field | Exact | Cohen's κ |
|---|---|---|
| primaryLabel | 18/20 (0.90) | 0.62 |
| visibleGraphicalMark | 19/20 (0.95) | 0.00 (degenerate — A has no positives) |
| markIntegration | 16/20 (0.80) | – |
| markType | 14/20 (0.70) | – |

Human agreement and model performance are reported separately: the single
`visibleGraphicalMark` disagreement is ground-truth uncertainty, not a detector
error.

## 3. Development selection (G1–G3, 12 images) — `OWLV2_THRESHOLD_SELECTION_V1`

Frozen grid, combined prompts, unchanged gate numbers. Development human
positives: **0**. Injected recall, artifact regression and hard-reject bypass are
measured; H4-DIRECT-1 is escalate-only so the latter two are structurally 0.

| Threshold | TP / FP / FN / TN | Precision | Recall | New review on human-negatives | Injected recall | A | B | C | D | E | Eligible |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.05 | 0 / 11 / 0 / 1 | 0.00 | NOT_ESTIMABLE | 9/12 (0.75) | 12/12 | ✗ | ✗ | ✓ | ✓ | ✓ | no |
| 0.10 | 0 / 6 / 0 / 6 | 0.00 | NOT_ESTIMABLE | 6/12 (0.50) | 12/12 | ✗ | ✗ | ✓ | ✓ | ✓ | no |
| 0.15 | 0 / 3 / 0 / 9 | 0.00 | NOT_ESTIMABLE | 3/12 (0.25) | 12/12 | ✗ | ✗ | ✓ | ✓ | ✓ | no |
| 0.20 | 0 / 2 / 0 / 10 | 0.00 | NOT_ESTIMABLE | 2/12 (0.17) | 12/12 | ✗ | ✗ | ✓ | ✓ | ✓ | no |
| 0.25 | 0 / 0 / 0 / 12 | NOT_ESTIMABLE | NOT_ESTIMABLE | 0/12 (0.00) | 12/12 | ✗ | ✓ | ✓ | ✓ | ✓ | no |
| 0.30 | 0 / 0 / 0 / 12 | NOT_ESTIMABLE | NOT_ESTIMABLE | 0/12 (0.00) | 12/12 | ✗ | ✓ | ✓ | ✓ | ✓ | no |
| 0.40 | 0 / 0 / 0 / 12 | NOT_ESTIMABLE | NOT_ESTIMABLE | 0/12 (0.00) | 9/12 | ✗ | ✓ | ✗ | ✓ | ✓ | no |
| 0.50 | 0 / 0 / 0 / 12 | NOT_ESTIMABLE | NOT_ESTIMABLE | 0/12 (0.00) | 1/12 | ✗ | ✓ | ✗ | ✓ | ✓ | no |

**Selected threshold: none.** Criterion A fails everywhere. From 0.25 to 0.30
criteria B–E all pass — the detector is silent on every human-negative clean
image while still finding 12/12 injected marks — but with no human positive
there is no precision to estimate, and `NOT_ESTIMABLE` is not a pass by the
frozen rule (B3-L6.1 §20). No threshold was frozen, so **holdout G4–G5 was not
evaluated** (0 runs; no lock and no freeze file were written) and the full
20-image gate was not run. Nothing was re-selected after seeing any number.

## 4. Development H4-DIRECT-1 (descriptive; no threshold is selected)

Reported at two grid points only to characterise the rule; neither is a chosen
operating point.

| | 0.10 | 0.25 |
|---|---|---|
| Clean review burden (of 12) current → H4 | 2 → 8 | 2 → **2** |
| Human-negative new reviews | 6 | **0** |
| Injected marks flagged (of 12) current → H4 | 2 → 12 | 2 → 12 |
| Hard-reject bypass / artifact regression | 0 / 0 | 0 / 0 |

H4-DIRECT-1 requires no Florence region and never downgrades a live action
(tested per human field that it rejects as runtime input).

## 5. What this pilot establishes, and what it cannot

* The corpus has **no human-visible graphical mark** under the reference truth.
  A 20-image set of clean generated avatars simply may not contain one; that is
  plausible and is now measured.
* Consequently the pilot **cannot estimate detector precision** in the sense the
  gate requires. Every OWLv2 detection on a clean avatar is, under this truth, a
  detection on a human-negative image: 11/12 dev images at 0.05, 0/12 at ≥ 0.25.
* What *is* established: injected-mark recall 12/12 on development from 0.05 to
  0.30, and zero human-negative burden from 0.25 upward. That is
  `PROVISIONAL_G004_SHADOW_EVIDENCE` on 12–20 images, not production evidence.
* Not established: any precision, any recall, any production rate. Prohibited
  wording is not used: this is not production validation.

## 6. Verdicts

* Pilot: **`OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT`** (also, formally,
  `NO_THRESHOLD_SELECTED`). Not `PILOT_GATE_FAILED`: the gate was never
  evaluable, it did not fail on a measured number.
* H4: **`H4_EVIDENCE_INSUFFICIENT`**.
* Owner's designation of Rater A and the gate outcome are independent; the
  designation was honoured exactly and did not produce a pass.

## 7. Exact next step

The gate needs positive ground truth. Options, for the owner:

1. Extend the clean corpus until it contains human-visible marks (new images
   need the same consent authority as the 28 already authorized), then re-run
   this frozen procedure unchanged; or
2. Accept, as a separate owner decision, an **injected-positive** variant of
   criterion A for the pilot (precision on the injected-logo conditions, where
   truth exists by construction). That would be a new pre-registered gate
   version, not a re-reading of `owlv2_provisional_shadow_gate_v1`.

Neither is taken here.

## 8. Safety

Model re-inference 0 · Azure 0 · external image transmission 0 · production
writes 0 · builds/deploys 0 · live policy unchanged · 28/28 originals unchanged
(SHA-256 + mtime) · Rater C artifacts untouched.
