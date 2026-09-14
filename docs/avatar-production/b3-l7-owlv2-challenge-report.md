# B3-L7 — OWLv2 positive-construct challenge set, gate V2, H4-DIRECT-1 controlled evaluation

Offline, decision-neutral. 180 local OWLv2 inferences (one capture at floor
0.01; sweeps are filtering), 0 Florence inferences, 0 external calls, no live
policy change, no build, no deploy. Aggregate only.

**V2 verdict: `OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT`** · selection:
`NO_THRESHOLD_SELECTED` · holdout evaluated: **0** · **H4: `H4_DIRECT_SHADOW_NOT_SUPPORTED`**
· `NATURAL_POSITIVE_EVIDENCE_MISSING`.

Gate v1 status is unchanged and not reinterpreted:
`OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT`.

## 1. The finding in one sentence

On this grid there is **no threshold where OWLv2 is both quiet on clean avatars
and sensitive to text watermarks**: the clean side is clean only from 0.25
upward, and at 0.25 every text-watermark family is 0/12 — the detector's
high-score band with these generic prompts contains compact geometric marks
(symbol, emblem, small corner mark) and nothing else.

## 2. Setup (pre-registered, unchanged)

Model `google/owlv2-base-patch16-ensemble` @ `cfd3195b…`, prompts unchanged,
grid unchanged, dev G1–G3 / holdout G4–G5, truth `OWNER_RATER_A_RESOLUTION_V1`
(20/20 human-negative clean avatars). Ten construct families × 20 bases = 200
positive conditions (F1 reused from the existing V8 capture; 180 fresh). Same
normalized spec on every base; synthetic words only; originals untouched
(28/28 SHA-256 + mtime).

## 3. Development table (G1–G3: 12 clean, 120 positive conditions)

Clean side = specificity; positive side = `CONTROLLED_CHALLENGE_RECALL`. Never
merged into one precision.

| Thr | Clean detector response | New `allow→review` on human-neg | Overall recall (CI) | A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.05 | 11/12 | **9/12** (0.75) | **120/120** (1.00 [0.97, 1.0]) | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0.10 | 6/12 | 6/12 (0.50) | 99/120 (0.825) | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ |
| 0.15 | 3/12 | 3/12 (0.25) | 77/120 (0.642) | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ |
| 0.20 | 2/12 | 2/12 (0.17) | 56/120 (0.467) | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ |
| **0.25** | 0/12 | **0/12** (0.00) | 44/120 (0.367) | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ |
| 0.30 | 0/12 | 0/12 | 38/120 (0.317) | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ |
| 0.40 | 0/12 | 0/12 | 23/120 (0.192) | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ |
| 0.50 | 0/12 | 0/12 | 5/120 (0.042) | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ |

No threshold is eligible. F (artifact regression) and G (hard-reject bypass)
are 0 everywhere; transitions are `allow→review` only.

### Family image recall on development (hits / 12)

| Family | 0.05 | 0.10 | 0.15 | 0.20 | 0.25 | 0.30 | 0.40 | 0.50 |
|---|---|---|---|---|---|---|---|---|
| GRAPHIC_SYMBOL (F1) | 12 | 12 | 12 | 12 | **12** | 12 | 9 | 1 |
| LOGO_LIKE_EMBLEM (F2, critical) | 12 | 12 | 12 | 12 | **12** | 12 | 12 | 4 |
| SMALL_CORNER_MARK (F7, D) | 12 | 12 | 12 | 12 | **12** | 12 | 2 | 0 |
| TEXT_WATERMARK_OPAQUE (F3, critical) | 12 | 6 | 4 | 1 | **0** | 0 | 0 | 0 |
| TEXT_WATERMARK_TRANSLUCENT (F4, critical) | 12 | 6 | 3 | 1 | **0** | 0 | 0 | 0 |
| GRAPHICAL_WATERMARK (F5, critical) | 12 | 11 | 7 | 3 | **0** | 0 | 0 | 0 |
| BRAND_LIKE_TEXT_AND_SYMBOL (F6) | 12 | 12 | 9 | 4 | 1 | 0 | 0 | 0 |
| EDGE_MARK (F8, E) | 12 | 9 | 5 | 3 | **1** | 0 | 0 | 0 |
| CENTER_OVERLAY_MARK (F9) | 12 | 7 | 2 | 0 | 0 | 0 | 0 | 0 |
| REPEATED_TILED_MARK (F10) | 12 | 12 | 11 | 8 | 6 | 2 | 0 | 0 |

Region recall (boxes matched / boxes) equals image recall for single-box
families; the tiled family's region recall is 0.76 at 0.10 and 0.10 at 0.25.
**Policy misses are 0 at every threshold**: every detector hit becomes a review
under H4-DIRECT-1. Everything above is a **model miss**.

### Which prompt produced the hits (descriptive telemetry, no prompt change)

At 0.05, text families are found mostly by `a watermark` (translucent 10/12,
brand-like 12/12, tiled 12/12) with `a graphic symbol` second; geometric
families are found by `a graphic symbol` (12/12 each). At ≥ 0.25 the only query
still producing matches is `a graphic symbol` (plus `a logo` 2× on the small
corner mark and `a watermark` on some tiles). No query was added or removed.

## 4. Why development fails, precisely

* The lowest threshold at which criterion A holds is **0.25** (0/12 new reviews;
  Wilson [0, 0.24]).
* The highest threshold at which criteria B–E hold is **0.05** (all families
  12/12), where A is 9/12.
* Between them the clean response and the text/translucent/edge sensitivity
  fall together: they are the same score band. At 0.25, LOGO_LIKE_EMBLEM,
  GRAPHIC_SYMBOL and SMALL_CORNER_MARK are still 12/12, but
  TEXT_WATERMARK_OPAQUE, TEXT_WATERMARK_TRANSLUCENT and GRAPHICAL_WATERMARK are
  0/12 and EDGE_MARK 1/12, so C and E fail.

So the gap is not a threshold-tuning problem. With the frozen generic prompts,
OWLv2's confident band is a *compact-graphical-mark* band; text watermarks and
translucent icons never reach it. Lowering the threshold to reach them brings
back the clean-avatar responses that gate v1 already showed are all on
human-negative images.

## 5. Holdout and full results

Not evaluated: no threshold was selected, so the frozen procedure forbids it.
No lock, no freeze record. Holdout G4–G5 detector performance was never
computed or displayed.

## 6. H4-DIRECT-1

Runtime rule unchanged; no Florence prerequisite; human fields rejected as
inputs; escalate-only (F = 0, G = 0 at every threshold). It faithfully turns
every detector hit into a review — the shortfall is upstream of it. Current
actions on challenge rows are a proxy (base clean image's live action; F1 uses
its real V8 action), which can only understate H4's flagged count.

Descriptively, at 0.25 H4 changes the clean development burden 2 → 2 while
flagging 12/12 of each geometric family; at 0.05 it changes it 2 → 11.

## 7. What is and is not established

* Established (controlled, synthetic, 12–20 bases): OWLv2 localizes compact
  geometric marks — abstract symbol, text-free emblem, small corner mark — at
  100% on development across 0.05–0.30 with zero clean-avatar response from
  0.25. That is `G004_CONTROLLED_MARK_CHALLENGE_EVIDENCE`.
* Established: at clean-safe scores it does **not** detect text watermarks
  (opaque or translucent), translucent icon watermarks, edge or center marks,
  or brand-like text+symbol, with these prompts.
* Not established: any production rate, any natural-positive precision or
  recall (`NATURAL_POSITIVE_EVIDENCE_MISSING`), behaviour on real brand logos.
  Prohibited wording is not used.

## 8. Verdicts

* `OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT`
* `H4_DIRECT_SHADOW_NOT_SUPPORTED` — not because H4 misbehaves, but because no
  threshold exists under which the detector it relies on satisfies V2.

## 9. Exact next step (owner decision; none taken here)

B3-L4 already measured that Florence OCR finds injected **text** overlays at or
near ceiling on these same avatars (corner/edge/center text 1.0, translucent
0.95), while OWLv2 at 0.25 covers exactly the **graphical** families Florence
misses. The evidence therefore points to a role-split rather than a better
single threshold:

1. Pre-register a V3 shadow design in which OWLv2 (≥ 0.25, graphical-mark
   families) and Florence OCR (text families) are separate evidence channels
   with separate, pre-registered family floors, and evaluate it on this same
   frozen corpus and split. Requires no new inference.
2. Any prompt-set change is a separate study on **new** held-out constructs,
   never selected on this data.

## 10. Safety

Model inference: 180 OWLv2 calls, local only · Florence 0 · Azure 0 · external
image transmission 0 · production writes 0 · builds/deploys 0 · live policy
unchanged · originals 28/28 unchanged · Rater C artifacts untouched.
