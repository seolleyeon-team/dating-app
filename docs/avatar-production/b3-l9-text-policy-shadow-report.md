# B3-L9 — TEXT_POLICY_SHADOW_V1: narrow single-text watermark shadow, development selection, one-shot holdout

Offline, decision-neutral. 16 local Florence inferences (holdout text
derivatives only, after the selected-candidate freeze), 0 OWLv2 inferences,
0 external calls, no live policy change, no worker integration, no build, no
deploy. Aggregate only. Contract digest `89514d712ad8…` frozen in
[b3-l9-preregistration.md](b3-l9-preregistration.md) before any candidate
metric. Designation: **`DEVELOPMENT_DESIGNED`**.

**Verdict: `TEXT_POLICY_SHADOW_HOLDOUT_FAILED`** · support:
`TEXT_POLICY_SHADOW_NOT_SUPPORTED` · holdout evaluated: **exactly 1** · V4
recomposition: **not executed** (requires a holdout pass) ·
`TEXT_POLICY_GAP`: **unresolved** · `GRAPHICAL_CHANNEL_GAP`: unresolved,
out of scope → **`GRAPHICAL_DETECTOR_STUDY_REQUIRED`** ·
`NATURAL_POSITIVE_EVIDENCE_MISSING`.

Immutable prior results: V1 `OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT`, V2
`OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT`, V3 `V3_DUAL_CHANNEL_FAILED_DEVELOPMENT`,
`H4_DUAL_CHANNEL_SHADOW_NOT_SUPPORTED`.

## 1. The finding in one sentence

At the typed-evidence level the canonical policy exposes in production, the
injected single-word watermark (one small, non-overlay-like text region in the
torso band) is **indistinguishable from what Florence reports on clean
avatars that carry no visible text at all**: the only candidate that catches
24/24 development and 16/16 holdout watermarks also turns 3 of 8 human-negative
holdout avatars into new reviews (0.375 ≫ 0.10), and every one of those three
is labelled `NO_VISIBLE_RELEVANT_TEXT_OR_MARK` by the reference rater.

## 2. What was frozen (unchanged after any table)

Four candidates, strict → broad, on runtime typed fields only (`kind`,
`location`, `areaBand`, `overlayLike`, `ocrDetectionCount`); `confidenceBand`
(always `unknown`, not a probability), `sourceConsistent` (inert with
`source_regions=()`), raw text, human labels, families, boxes and identifiers
are refused as inputs. Composition `max(canonicalAction, review if predicate)`.
Criteria A ≤ 0.10 new clean review, B/C ≥ 0.90 text recall, D tiled reject
preserved 100 %, E bypass 0, F regression 0; strictest eligible wins; holdout
once behind `text_policy_v1_holdout_evaluated.lock`.

## 3. Development (G1–G3; 12 clean, 12 opaque, 12 translucent, 12 tiled; Florence inference 0)

| Cand. | Predicate (short) | clean canonical | new allow→review | opaque | translucent | tiled reject | E/F | A–F |
|---|---|---|---|---|---|---|---|---|
| T1 | corner/edge ∧ small ∧ overlayLike | 10/2/0 | **8/12** (0.67) | 0/12 | 0/12 | 12/12 | 0/0 | ✗ A B C |
| T2 | central ∧ small ∧ ¬overlay ∧ single | 10/2/0 | 0/12 | 0/12 | 0/12 | 12/12 | 0/0 | ✗ B C |
| **T3** | central∨clothing_zone ∧ small ∧ ¬overlay ∧ single | 10/2/0 | **1/12** (0.083) | **12/12** | **12/12** | 12/12 | 0/0 | **✓** |
| T4 | any location ∧ small/medium ∧ single | 10/2/0 | **10/12** (0.83) | 12/12 | 12/12 | 12/12 | 0/0 | ✗ A |

Selected: **T3** (strictest eligible; T1/T2 not eligible). Frozen to
`text_policy_v1_selected.json` with the contract digest and the development
input digest `e24e4421a94a…`. T1 shows that the classic overlay signature is
the *clean* signature on these avatars (8/12 clean carry a small overlay-like
corner/edge text region); T4 shows that "one isolated small text region"
alone is present on 10/12 clean images.

## 4. Holdout (G4–G5; exactly once; 8 clean, 8 opaque, 8 translucent, 8 tiled)

Holdout text rows: 16 locally inferred (production adapter path, fp32 CPU,
median 37 s/img; first attempt segfaulted at model load with 0 rows, second
attempt completed; per-row guard never lowered). Clean and tiled holdout rows:
exact reuse of the B3-L4 capture.

| Criterion | Result | |
|---|---|---|
| A new clean allow→review | **3/8 = 0.375** (Wilson [0.14, 0.69]) | ✗ |
| B opaque recall | 8/8 | ✓ |
| C translucent recall | 8/8 | ✓ |
| D tiled reject preserved | 8/8 | ✓ |
| E hard-reject bypass | 0 | ✓ |
| F safety regression | 0 | ✓ |

Holdout clean canonical: allow 7 / review 1 / reject 0. **Verdict:
`TEXT_POLICY_SHADOW_HOLDOUT_FAILED`.** Nothing was retuned afterwards.

### Why (descriptive, computed after the one-shot holdout)

Holdout clean typed inventory: every avatar has exactly one text region;
location corner 4 / edge 1 / **clothing_zone 3**; all small; overlayLike
5 / 3; textQuality plausible 5, implausible 1, unknown 2. The three
`clothing_zone / small / not overlay-like / single` regions are the three new
reviews, and all three avatars are `NO_VISIBLE_RELEVANT_TEXT_OR_MARK` under
the owner-designated Rater A truth — Florence reports a small plausible text
region in the torso band on avatars that show no text. On all 20 clean
avatars the T3 profile occurs on 4/20 (development 1/12 was the lucky end of
that distribution). The two `GARMENT_TEXT` avatars are *not* among the flagged
ones. The holdout text derivatives are 16/16 the same typed profile
(`clothing_zone / small / overlay=False / single`), so recall is 16/16 by the
same token that clean specificity fails: the typed schema carries no field
that separates them.

## 5. What is and is not established

* Established: the canonical typed evidence document (`location`, `areaBand`,
  `overlayLike`, `ocrDetectionCount`, `textQuality`) does not contain a
  signal that separates a single injected text watermark from Florence's
  single incidental text region on clean avatars; every narrow rule on those
  fields either misses the watermark (T1, T2) or floods clean avatars (T3 on
  holdout, T4). The gap cannot be closed by policy geometry on the current
  evidence schema.
* Established: repeated-text reject and generated-artifact review paths are
  untouched (D 20/20, E/F 0 on both splits); the shadow never downgrades.
* Not established: any production rate, natural-watermark behaviour
  (`NATURAL_POSITIVE_EVIDENCE_MISSING`), anything about the graphical channel
  (`GRAPHICAL_DETECTOR_STUDY_REQUIRED` for GRAPHICAL_WATERMARK, EDGE_MARK,
  CENTER_OVERLAY_MARK; OWLv2 0.25 and prompts untouched).

## 6. Verdicts

* `TEXT_POLICY_SHADOW_HOLDOUT_FAILED` → `TEXT_POLICY_SHADOW_NOT_SUPPORTED`.
* `AVATAR_WATERMARK_DUAL_CHANNEL_V4`: not recomposed.
* `TEXT_POLICY_GAP`: unresolved. `GRAPHICAL_CHANNEL_GAP`: unresolved (out of scope).

## 7. Exact next step (owner decision; none taken here)

The text gap needs **new evidence**, not a new predicate: the region-level
signal that could separate an overlaid word from incidental/garment text is
absent from the typed schema (confidence is always `unknown`; there is no
contrast/opacity/edge-alignment feature). Two pre-registrable directions, both
evidence studies rather than rule changes: (1) make the beam-search sequence
score the adapter already requests (`output_scores=True`) reach the evidence
document as a real `confidenceBand`, then repeat this exact protocol
(candidates may then include a confidence band because it would be a
probability-bearing field); (2) a detector study on new held-out constructs
covering both the text watermark and the graphical gap families. Neither
touches the live policy; `approveAvatarCandidate` deployment remains a
separate release blocker.

## 8. Safety

Florence 16 local (holdout text only) · OWLv2 0 · Azure 0 · external image
transmission 0 · production writes 0 · builds/deploys 0 · live decision diff 0
· originals **28/28** unchanged (SHA-256 + mtime) · Rater C artifacts untouched
· V2/V3 locks untouched.
