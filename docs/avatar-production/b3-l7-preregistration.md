# B3-L7 — pre-registration: positive-construct challenge set + controlled gate V2

Frozen **before any V2 performance number was computed**. Gate v1
(`owlv2_provisional_shadow_gate_v1`) is left exactly as it ended —
`OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT` — and is neither modified nor
reinterpreted. V2 is a new version with a new evidence label.

| Item | Value |
|---|---|
| Gate version | `OWLV2_CONTROLLED_CHALLENGE_GATE_V2` |
| Evidence label | `G004_CONTROLLED_MARK_CHALLENGE_EVIDENCE` |
| Recall label | `CONTROLLED_CHALLENGE_RECALL` |
| Selection | `OWLV2_THRESHOLD_SELECTION_V1` (development only, lowest eligible) |
| H4 | `H4-DIRECT-1`, runtime logic unchanged |
| Model | `google/owlv2-base-patch16-ensemble` @ `cfd3195ba4ea9592eec887ded089f4c08eff231d` |
| Grid | 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50 (unchanged) |
| Prompts | `a logo`, `a watermark`, `a brand emblem`, `a graphic symbol`, combined (unchanged) |
| Split | development G1–G3, holdout G4–G5 (unchanged, participant-group level) |
| Capture | one pass at floor 0.01; sweeps are filtering, never re-inference |

## 1. Why V2, and what each corpus measures

Under the owner-designated Rater A truth the 20 clean avatars are 20/20
human-negative. That corpus therefore measures **specificity and review burden**
and nothing else. Injected constructs have ground truth by construction and
measure **sensitivity**. V2 keeps the two sides separate and never combines them
into a single "precision". V2 is a controlled shadow feasibility gate, not
production validation.

## 2. Positive construct families (one normalized spec per family, applied identically to all 20 bases)

| Code | Family | Content | Alpha | Rel. size | Placement | Safety-critical |
|---|---|---|---|---|---|---|
| F1 | GRAPHIC_SYMBOL | circle + triangle (the existing V8 construct; capture reused, not re-rendered) | 0.90 | 0.08 | corner (top-right) | – |
| F2 | LOGO_LIKE_EMBLEM | shield + ring + chevron, no text | 0.95 | 0.10 | corner (top-left) | yes |
| F3 | TEXT_WATERMARK_OPAQUE | `SAMPLE`, outlined | 1.00 | 0.06 | center-low | yes |
| F4 | TEXT_WATERMARK_TRANSLUCENT | `SAMPLE`, same size/position as F3 | 0.35 | 0.06 | center-low | yes |
| F5 | GRAPHICAL_WATERMARK | ring + four-point star, no text | 0.35 | 0.12 | center | yes |
| F6 | BRAND_LIKE_TEXT_AND_SYMBOL | diamond + `NOVA` | 1.00 | 0.05 | corner (bottom-right) | – |
| F7 | SMALL_CORNER_MARK | small circle + triangle | 1.00 | 0.035 | corner (bottom-right) | D |
| F8 | EDGE_MARK | small circle + triangle | 1.00 | 0.035 | top edge, centred | E |
| F9 | CENTER_OVERLAY_MARK | circle + triangle | 0.85 | 0.10 | center | – |
| F10 | REPEATED_TILED_MARK | `SAMPLE` × 12 | 0.45 | 0.04 | 3×4 grid | – |

Synthetic vocabulary only (`SAMPLE`, `NOVA`); a real-trademark blocklist is
asserted by tests. Derivatives are rendered in memory; originals are never
written. Matched design: a family's ground-truth box is identical on any two
same-size bases (tested).

## 3. Gate V2 criteria (frozen)

| # | Criterion | Value |
|---|---|---|
| A | Clean human-negative new detector-induced review rate (`allow → review` only) | ≤ 0.10 |
| B | Overall controlled-positive image recall | ≥ 0.95 |
| C | Each safety-critical family (F2, F3, F4, F5) recall | ≥ 0.90 |
| D | SMALL_CORNER_MARK recall | ≥ 0.90 |
| E | EDGE_MARK recall | ≥ 0.90 |
| F | Generative-artifact safety regression | 0 |
| G | Hard-reject bypass | 0 |

Why not 100% per family: the set is wider than the single shape that scored
20/20 in B3-L6, and requiring 100% of every tiny synthetic family would over-fit
to it. Overall ≥ 0.95 with critical families ≥ 0.90 is the provisional controlled
floor. No stricter code authority was found that would override it.

## 4. Procedure

1. Development (G1–G3): clean-negative side + family recall per grid threshold.
2. Eligibility A–G on development; **lowest** eligible threshold selected. None →
   `OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT`, holdout never opened.
3. Freeze: threshold, selection version, gate version, model revision, prompts,
   input digest.
4. Holdout (G4–G5) evaluated **exactly once**, lock-guarded, only after 3. After
   it: no threshold, prompt, family or floor change.
5. Full 20-base results reported as two separate sides.

Holdout derivatives may be generated and captured ahead of time; their
performance is neither computed nor displayed before the freeze.

Current-action note: Florence is not re-run on the new derivatives, so a
challenge condition's live action is a proxy — its base clean image's live
action (F1 uses the real V8 action). H4-DIRECT-1 is escalate-only, so the proxy
can only understate H4's flagged count.

## 5. Wording

`CONTROLLED_CHALLENGE_RECALL` on `G004_CONTROLLED_MARK_CHALLENGE_EVIDENCE`.
Prohibited: production recall proven, production detector validated,
production-ready precision, `OWLV2_PRODUCTION_VALIDATED`, `H4_LIVE_POLICY_READY`.
Even a PASS leaves `NATURAL_POSITIVE_EVIDENCE_MISSING`: natural-occurring mark
precision and natural-positive recall remain unmeasured until a real
positive clean corpus exists.
