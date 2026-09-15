# B3-L11 — fresh visual mark detector study (VISUAL_MARK_CHALLENGE_V3, DETECTOR_CANDIDATE_SET_V1)

Offline detector-capability study, decision-neutral. Local CPU inference only
(OWLv2 192, Grounding DINO tiny 192, Florence-2 phrase grounding 192; Florence
OCR/OD 0; external 0), no live integration, no policy, worker, env, build or
deploy change. Aggregate only. Construct digest `38ec105fc597…` and
detector-set digest `086a32a65e05…` frozen in
[b3-l11-preregistration.md](b3-l11-preregistration.md) before any real-avatar
inference. Methodology marker
**`FLORENCE_TELEMETRY_TEXT_PATH_CLOSED_ON_CURRENT_CORPUS`** (G4–G5 score/token
values were not read; no lock created for them).

**Verdict: `VISUAL_MARK_DETECTOR_FAILED_DEVELOPMENT`** · holdout opened **NO**,
executions **0** · `TEXT_POLICY_GAP` unresolved (canonical policy unchanged) ·
`TEXT_DETECTOR_CONTROLLED_GAP_OPEN` · **`GRAPHICAL_DETECTOR_STUDY_REQUIRED`** ·
`NATURAL_POSITIVE_EVIDENCE_MISSING`.

Immutable prior results: V1, V2, V3, B3-L9 `TEXT_POLICY_SHADOW_HOLDOUT_FAILED`,
B3-L10A `FLORENCE_SEQUENCE_SCORE_NOT_SEPARATING`, B3-L10B
`FLORENCE_TWO_FEATURE_NOT_SEPARATING`.

## 1. The finding in one sentence

On the new constructs no frozen detector/operating point is quiet on clean
avatars *and* sensitive across the critical families: OWLv2 at its legacy
0.25 is silent on clean (0/12) but blind to text, translucent and edge marks
(overall 0.45); Grounding DINO at its historical 0.25 finds almost everything
(0.97) but fires on every clean avatar (12/12, mostly "a logo" boxes); at the
pre-registered 0.35 grid point it is nearly quiet (1/12) but loses edge and
tiled marks; Florence-2 phrase grounding lands in between (clean 4/12,
overall 0.91, edge 5/12) — so the study fails development and the holdout is
never opened.

## 2. What was frozen (unchanged after any table)

12 families × DEV/HOLDOUT variants (different synthetic strings and
geometries), alpha axis 1.00 / 0.65 / 0.35 / 0.20 (LOW =
`LOW_VISIBILITY_STRESS_CONDITION`, diagnostic), size bands 0.035 / 0.07,
placements corner / edge / center / torso / tiled; 15 conditions per base →
development 180 positives + 12 clean per detector. Candidates: OWLv2
`cfd3195b…` legacy 0.25 fixed (apache-2.0); Grounding DINO tiny `a2bb814d…`
historical box/text 0.25 fixed plus separate grid 0.15 / 0.35 / 0.45
(apache-2.0); Florence-2-large-ft `26b734a5…` `<CAPTION_TO_PHRASE_GROUNDING>`
presence with a full-frame box filter pre-registered from a blank-image smoke
(MIT). Excluded: YOLO-World (`EXCLUDED_PENDING_PRODUCT_LICENSE_DECISION`),
owlv2-large / grounding-dino-base (`EXCLUDED_LOCAL_RESOURCE_BUDGET`). Common:
CPU, one model resident, long side ≤ 2048, IoU ≥ 0.30, image-level construct
hit, one low-floor inference per image. One implementation fix before any
table: Grounding DINO's low-floor labels are phrase concatenations, so query
membership is tested by phrase containment (no query added or removed).

## 3. Development table (G1–G3 + DEV_VARIANT; 12 clean human-negative, 168 gated positives + 12 LOW)

| Detector / op. point | Role | Clean response | New allow→review | Overall (≥160/168) | min critical | Failed |
|---|---|---|---|---|---|---|
| OWLv2 legacy 0.25 | baseline | **0/12** | 0 | 76/168 (0.45) | 0.00 | B C D E F I J |
| Grounding DINO 0.25 | baseline | 12/12 | **10/12** | 163/168 (0.97) | 0.83 | A F I |
| Grounding DINO 0.15 | grid | 12/12 | 10/12 | 168/168 (1.00) | 1.00 | A |
| Grounding DINO 0.35 | grid | 1/12 | 1/12 | 137/168 (0.82) | 0.08 | B E F I |
| Grounding DINO 0.45 | grid | 1/12 | 1/12 | 44/168 (0.26) | 0.00 | B–J |
| Florence-2 grounding (presence) | new | 4/12 | 4/12 | 153/168 (0.91) | 0.42 | A B E I |

K (hard-reject bypass) and L (downgrade) are 0 everywhere (review-only
simulator on the canonical clean actions: allow 10 / review 2).

### Family recall (hits / n)

| Family | OWLv2 0.25 | GDINO 0.25 | GDINO 0.35 | Florence |
|---|---|---|---|---|
| TEXT_WATERMARK_OPAQUE (C, n 24) | 0 | 24 | 22 | 22 |
| TEXT_TRANSLUCENT_HIGH (D) | 9 | 12 | 12 | 11 |
| TEXT_TRANSLUCENT_MEDIUM (E) | 4 | 11 | 9 | 9 |
| TEXT_TRANSLUCENT_LOW (diagnostic) | 0 | 9 | 6 | 9 |
| GRAPHICAL_WATERMARK_TRANSLUCENT (F) | 0 | 10 | 10 | 11 |
| LOGO_LIKE_EMBLEM (G, n 24) | 24 | 24 | 23 | 23 |
| BRAND_LIKE_TEXT_AND_SYMBOL | 0 | 12 | 12 | 12 |
| SMALL_CORNER_MARK (H) | 12 | 12 | 12 | 12 |
| EDGE_MARK (I) | 0 | 10 | 1 | 5 |
| CENTER_OVERLAY_MARK (J) | 3 | 12 | 12 | 12 |
| REPEATED_TILED_MARK | 0 | 12 | 1 | 12 |
| GRAPHIC_SYMBOL (n 24) | 24 | 24 | 23 | 24 |

### Alpha / placement / size (hits / n)

| Axis | OWLv2 0.25 | GDINO 0.25 | GDINO 0.35 | Florence |
|---|---|---|---|---|
| alpha OPAQUE / HIGH / MEDIUM / LOW | 60/108 · 12/24 · 4/36 · 0/12 | 106/108 · 24/24 · 33/36 · 9/12 | 93/108 · 24/24 · 20/36 · 6/12 | 98/108 · 23/24 · 32/36 · 9/12 |
| placement corner / edge / center / torso / tiled | 60/72 · 0 · 3/24 · 13/60 · 0 | 72/72 · 10/12 · 22/24 · 56/60 · 12/12 | 70/72 · 1/12 · 22/24 · 49/60 · 1/12 | 71/72 · 5/12 · 23/24 · 51/60 · 12/12 |
| size small / medium | 36/72 · 40/108 | 70/72 · 102/108 | 48/72 · 95/108 | 63/72 · 99/108 |
| box recall / mean IoU on hits | 0.24 / 0.85 | 0.58 / 0.72 | 0.46 / 0.69 | 0.53 / 0.69 |

### Resources and latency (CPU, one model resident)

| Detector | peak RSS | median / p90 latency | detections per image at floor |
|---|---|---|---|
| OWLv2 | 5.72 GB | 18.5 s / 18.9 s | 20.9 (floor 0.01) |
| Grounding DINO tiny | 2.77 GB | 14.6 s / 16.9 s | 65.7 (floor 0.05); one row stalled ~5 h under host sleep/paging (anomaly, not a model property) |
| Florence-2 grounding | 3.98 GB | 20.9 s / 30.1 s | 4.6 (no score) |

Florence capture tripped the per-row 0.6 GB guard three times under host
memory pressure; each time the checkpoint was kept and resumed (0 rows lost);
the start gate blocked twice at 3.9 GB and was **not** lowered.

## 4. Why development fails, precisely

* **OWLv2 0.25** reproduces B3-L7 on new constructs: compact opaque
  geometry (emblem, symbol, small corner) 100 %, everything text-like,
  translucent, edge or tiled ≈ 0.
* **Grounding DINO** has the recall but not the specificity at its historical
  point: 33 of its 35 clean-avatar detections are "a logo" boxes on
  human-negative avatars. Its pre-registered grid shows the two sides do not
  meet: 0.35 is the first point with ≤ 1 clean response and there EDGE_MARK is
  1/12 and REPEATED_TILED_MARK 1/12 (both small marks). No finer search is
  permitted.
* **Florence-2 grounding** without a score has no operating point to move;
  its clean burden (4/12) and edge sensitivity (5/12) both miss the gate.
* The LOW-alpha diagnostic family reaches 9/12 for Grounding DINO 0.25 and
  Florence — reported, not gated.

## 5. Eligible models / selection / holdout

Eligible: **none**. Selected: **NONE**. Holdout (G4–G5 + HOLDOUT_VARIANT):
not generated, not inferred, not evaluated; no selected-freeze, no lock.
Nothing was retuned after the table.

## 6. Gap markers

* `TEXT_POLICY_GAP`: unresolved (canonical policy untouched).
* Text detector controlled gap: **open** (no eligible point passed C–E).
* Graphical detector controlled gap: **open** → `GRAPHICAL_DETECTOR_STUDY_REQUIRED`.
* `NATURAL_POSITIVE_EVIDENCE_MISSING` (synthetic constructs only).

## 7. What is and is not established

* Established (controlled, 12 bases, new constructs): Grounding DINO tiny at
  0.15–0.25 localizes text watermarks (opaque, high, medium), translucent
  icons, emblems, corner/edge/center/tiled marks at 0.97–1.00, and Florence-2
  grounding at 0.91 — sensitivity is no longer the bottleneck for these
  detectors; clean-avatar response is. OWLv2 remains a compact-opaque-mark
  detector.
* Not established: any operating point meeting both sides; anything about
  natural watermarks, real brand logos, GPU behaviour, or production rates.

## 8. Exact next step (owner decision; none taken here)

Two pre-registrable directions, neither a retune of this corpus: (1) a
**clean-response study** for Grounding DINO — what the 33 "a logo" boxes on
human-negative avatars are (typed geometry / size bands, aggregate only) and
whether a pre-registered *box-property* rule (e.g. area band, aspect) rather
than a score threshold separates them from injected marks, evaluated on new
held-out constructs with the score point kept at the historical 0.25; (2) a
detector-ensemble hypothesis (OWLv2 0.25 ∨ Grounding DINO 0.35 ∨ Florence
grounding) pre-registered as a fixed rule and tested once on the still-unused
HOLDOUT_VARIANT — only if the owner accepts that its development evidence is
this same table. `approveAvatarCandidate` deployment remains a separate
release blocker.

## 9. Safety

Florence OCR/OD 0 · Florence grounding 192 · OWLv2 192 · Grounding DINO 192
(all local CPU) · optional-candidate downloads 0 (all weights already local) ·
Azure/OpenAI/external vision/OCR 0 · user-image transmission 0 · production
writes 0 · builds/deploys 0 · live decision diff 0 · originals **28/28**
unchanged (SHA-256 + mtime) · all prior locks untouched · Rater C artifacts
untouched.
