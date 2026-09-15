# B3-L12A — Grounding DINO clean-response geometry filter study (fixed 0.25 operating point)

Offline, decision-neutral. **0 new model inference** (development reused the
B3-L11 Grounding DINO capture with exact provenance; holdout never generated),
no external calls, no policy / worker / env / build / deploy change. Aggregate
only. Contract digest `3e615dd3b443…` frozen in
[b3-l12a-preregistration.md](b3-l12a-preregistration.md) after the clean-only
inventory and before any positive box was read (`CLEAN_DEVELOPMENT_DESIGNED`).

**Verdict: `GDINO_GEOMETRY_FILTER_FAILED_DEVELOPMENT`** · diagnosis
`CLEAN_GEOMETRY_NOT_SEPARATING` + `EDGE_FAMILY_STILL_UNDERDETECTED` +
`GRAPHICAL_WATERMARK_STILL_UNDERDETECTED` (`MIXED`) · holdout opened **NO**,
executions **0** · `FIXED_OR_ENSEMBLE_REJECTED_BY_DEVELOPMENT_DOMINANCE` ·
`TEXT_POLICY_GAP` unresolved · text detector controlled gap open ·
`GRAPHICAL_DETECTOR_STUDY_REQUIRED` · `NATURAL_POSITIVE_EVIDENCE_MISSING`.

B3-L11 stays immutable: `VISUAL_MARK_DETECTOR_FAILED_DEVELOPMENT`, holdout
opened NO, executions 0.

## 1. The finding in one sentence

Grounding DINO's clean-avatar responses are not object-scale noise a box
geometry rule can strip: 18 of its 35 clean boxes are tiny mid-image boxes at
exactly the scale of the injected marks (on 9/12 clean images), so even the
most aggressive scale/shape candidate leaves 9/12 clean images responding
(A ≤ 1/12 fails everywhere), while the shape caps already start removing wide
long-word watermark boxes — and no filter can add back the edge and
translucent-icon misses.

## 2. What was frozen

Detector `IDEA-Research/grounding-dino-tiny` @ `a2bb814d…` (Apache-2.0,
official card), box/text 0.25 fixed, four queries fixed, B3-L11 resize/IoU,
"a logo" label used as observation only. Four coarse candidates on
`normalizedArea` / `aspectRatio` from the box alone (edges 0.50 / 0.20 / 0.08 /
0.03 = B3-L11 full-frame ratio, object-scale edge, canonical SMALL/TINY
constants; aspect caps 4 / 3), least → most aggressive:

| Rank | ID | Keep box iff |
|---|---|---|
| 1 | G1 | area < 0.50 |
| 2 | G2 | area < 0.20 ∧ 1/4 < aspect < 4 |
| 3 | G3 | area < 0.08 ∧ 1/3 < aspect < 3 |
| 4 | G4 | area < 0.03 ∧ 1/3 < aspect < 3 |

No location rule (corner / torso / not-centre / not-edge are safety-critical
placements), no label, human, family or ground-truth input; fine geometry
search refused in code. The OR ensemble (OWLv2 0.25 ∨ Grounding DINO 0.35 ∨
Florence grounding) was rejected structurally: it cannot respond on fewer
clean images than Florence grounding alone (4/12 > 1/12).

## 3. Development provenance and clean inventory (12 clean G1–G3, aggregate)

Reuse checks all exact (revision, repo, license, detector-set and construct
digests, DEV_VARIANT, floor 0.05 ≤ 0.25, originals unchanged) → **0 new
development inference**.

35 boxes on 12/12 images (median 3 per image). Area min / Q1 / median / Q3 /
max 0.0004 / 0.0027 / 0.0092 / 0.0437 / 0.7377; aspect 0.80–5.52; centre x
0.37–0.62; centre y 0.38–0.96; border touch 0, near-border 19, full-frame-like
1. Bands: area < 0.01 **18**, 0.01–0.03 4, 0.03–0.08 8, 0.20–0.50 4, ≥ 0.50 1;
aspect 1/3–3: 23, 3–4: 8, ≥ 4: 4. Structure: (a) 18 tiny mid-image boxes
(0.02–0.12 wide; square-ish or ≈ 2.2 aspect; on 9/12 images: 1 → 1, 2 → 7,
3 → 1), (b) 12 wide bottom-band strips (centre-y 0.92–0.96, aspect 2.7–5.5),
(c) 5 object-scale boxes. Pre-registered expectation before opening
positives: (a) is inseparable by scale/shape and a "not mid-image" rule is a
forbidden mark-location rule.

## 4. Development candidate table (12 clean, 168 gated positives)

| Cand. | clean response | new allow→review | overall (≥ 160) | min critical | failed |
|---|---|---|---|---|---|
| G1 | 12/12 | 10/12 | 163/168 (0.97) | 0.83 | A F I |
| G2 | 12/12 | 10/12 | 150/168 (0.89) | 0.08 | A B D E F I |
| G3 | 10/12 | 8/12 | 141/168 (0.84) | 0.08 | A B D E F I |
| G4 | 9/12 | 7/12 | 140/168 (0.83) | 0.00 | A B D E F I |

Family recalls (G1 · G2 · G3 · G4): opaque text 24/24 all; translucent HIGH
12 · **1** · 1 · 0 /12; MEDIUM 11 · 9 · 1 · 1; LOW (diag.) 9 · 9 · 8 · 8;
graphical watermark 10/12 all; emblem 24/24 all; brand-like 12/12 all; small
corner 12/12 all; edge 10/12 all; centre 12/12 all; tiled 12 · 12 · 11 · 11;
symbol 24/24 all. K/L = 0 everywhere. Selected: **NONE**.

## 5. Why, precisely

* **`CLEAN_GEOMETRY_NOT_SEPARATING`** — the scale/shape caps remove the five
  object-scale boxes and the bottom strips, but the tiny mid-image boxes
  survive every candidate; clean response only falls 12 → 9 images.
* **Positive shape collision** — the aspect cap ≥ 4 in G2 removes the wide
  11-character HIGH watermark boxes (12 → 1), and the area cap 0.08 in G3
  removes the two-word MEDIUM boxes (9 → 1): the long/two-word text
  constructs are wide at the medium size band. This is not the selection
  criterion (A already fails) but it shows that shape caps trade directly
  against text-watermark recall.
* **`EDGE_FAMILY_STILL_UNDERDETECTED` / `GRAPHICAL_WATERMARK_STILL_UNDERDETECTED`**
  — 10/12 each are model misses at 0.25; a filter can only remove boxes.

## 6. Holdout

Audited unopened (no holdout capture for any detector, no lock, no selected
marker) and left unopened: not generated, not inferred, not evaluated.

## 7. What is and is not established

* Established (controlled, 12 bases): on these avatars Grounding DINO's
  clean responses are dominated by mark-scale mid-image boxes; a
  geometry-only filter at the fixed 0.25 point cannot reach A without a
  location rule that would also suppress safety-critical centre/torso marks.
* Not established: anything about natural watermarks, real logos, GPU
  behaviour, or production rates.

## 8. Exact next step (owner decision; none taken here)

The clean bottleneck is now precisely located: small boxes in the face/upper-
torso band on human-negative avatars. Two honest options, both new
pre-registrations: (1) a **face-anchored exclusion study** — production QA
already runs a primary-face detector, so "box inside the primary face bbox
(runtime-available)" is not a mark-location rule in the forbidden sense; it
needs a face-bbox capture for the corpus, an explicit decision about
CENTER_OVERLAY_MARK (whose centre may fall inside the face box), and new
held-out constructs; (2) close the Grounding DINO path at this operating
point and treat the remaining gaps as a training/finetuning question outside
the zero-shot detector family. `approveAvatarCandidate` deployment remains a
separate release blocker.

## 9. Safety

Grounding DINO 0 (development reused, holdout not run) · OWLv2 0 · Florence 0
· Azure/external 0 · production writes 0 · builds/deploys 0 · live decision
diff 0 · originals **28/28** unchanged · all prior locks untouched · Rater C
artifacts untouched.
