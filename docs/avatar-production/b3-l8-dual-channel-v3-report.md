# B3-L8 — AVATAR_WATERMARK_DUAL_CHANNEL_V3: canonical Florence text policy + OWLv2 graphical supplement

Offline, decision-neutral shadow evaluation. 96 local Florence inferences
(fp32 CPU, production adapter path), 0 OWLv2 inferences (B3-L7 capture
reused), 0 external calls, no live policy change, no worker integration, no
build, no deploy. Aggregate only. Contract digest `7e0281db982a…` frozen in
[b3-l8-preregistration.md](b3-l8-preregistration.md) before any number below.

**V3 verdict: `V3_DUAL_CHANNEL_FAILED_DEVELOPMENT`** ·
**H4: `H4_DUAL_CHANNEL_SHADOW_NOT_SUPPORTED`** · holdout evaluated: **0** ·
channel-gap diagnosis: **`TEXT_POLICY_GAP` + `GRAPHICAL_CHANNEL_GAP` (MIXED)** ·
`NATURAL_POSITIVE_EVIDENCE_MISSING`.

Gate v1 (`owlv2_provisional_shadow_gate_v1` →
`OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT`) and gate V2
(`OWLV2_CONTROLLED_CHALLENGE_GATE_V2` → `OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT`,
`H4_DIRECT_SHADOW_NOT_SUPPORTED`) are unchanged and not reinterpreted.

## 1. The finding in one sentence

The role split works exactly where each model is strong — the graphical
supplement adds **zero** clean review burden and lifts the compact-mark
families to 12/12 — but the *canonical* Florence text policy flags **0/12**
opaque and **0/12** translucent single-word text watermarks even though
Florence's OCR **found all 24**, and OWLv2 at 0.25 still misses translucent
icons, edge and centre marks; so V3 reaches 70/120 (0.58) overall, far from
the 0.95 floor.

## 2. Setup (pre-registered, unchanged)

| Item | Value |
|---|---|
| Channel T | canonical `evaluate_watermark_risk` on `analyze_florence_visual_risk_outputs`, `source_regions=()` (production worker: `AVATAR_WORKER_MODE=azure_gpt_image_2`, `ENVIRONMENT=production` → source visual risk disabled), policy `watermark_policy_v4_runtime_evidence_parity_v1` |
| Florence | `florence-community/Florence-2-large-ft` @ `26b734a5…` (Dockerfile `QA_FLORENCE_REVISION`, verified against the local snapshot metadata), `<OCR_WITH_REGION>` + `<OD>`, num_beams 3 |
| Channel G | `google/owlv2-base-patch16-ensemble` @ `cfd3195b…`, combined prompts, **0.25** (`DEVELOPMENT_SELECTED_GRAPHICAL_SUPPLEMENT_THRESHOLD`), review-only |
| Composition | `max(textAction, graphicalAction)`, allow < review < reject, escalate-only |
| Clean truth | `OWNER_DESIGNATED_RATER_A_REFERENCE_TRUTH`, 20/20 human-negative |
| Split | development G1–G3 (12 bases), holdout G4–G5 (8 bases, never opened) |

## 3. Exact Florence evidence reuse audit

Reuse required an identical normalized spec **and** a byte-identical re-render
with identical boxes on every base; semantic similarity was never enough.

| Family | Verdict | Reused from | Historical pixels |
|---|---|---|---|
| GRAPHIC_SYMBOL | `EXACT_REUSABLE` | B3-L4 V8 | `BITWISE_IDENTITY_UNPROVEN` (no digest recorded in B3-L4) |
| REPEATED_TILED_MARK | `EXACT_REUSABLE` | B3-L4 V4 | `BITWISE_IDENTITY_UNPROVEN` |
| the other 8 | `NOT_REUSABLE` | — | no B3-L4 variant with an identical spec |

Development rows needed 120 · exact reused 24 · locally inferred **96** (8
families × 12 bases; every row carries the derivative pixel digest, 96 unique).
Holdout Florence rows: **0** inferred (development failed). OWLv2 new calls: 0.

The B3-L7 "current action = base clean proxy" was **not** used for any V3
number. Against the actual derivatives the canonical policy flagged 6/12
LOGO_LIKE_EMBLEM, 4/12 GRAPHICAL_WATERMARK, 3/12 EDGE_MARK, 2/12
CENTER_OVERLAY_MARK and 1/12 SMALL_CORNER_MARK as `generated_text_artifact`
reviews (Florence read the mark as fragmented text), which the proxy could not
see. Every V3 efficacy number here is actual derivative → actual Florence
output → canonical policy.

## 4. Development results (G1–G3)

### Clean human-negative avatars (12)

| | allow | review | reject |
|---|---|---|---|
| canonical Florence | 10 | 2 | 0 |
| V3 | 10 | 2 | 0 |

OWLv2 ≥ 0.25 hits: **0/12** · new `allow→review` caused by the supplement:
**0/12** (0.00, Wilson [0, 0.24]) · new `allow→reject`: 0 · existing canonical
reviews (2) not counted as V3 burden. **Criterion A passes.**

### Controlled-positive families (12 conditions each; `CONTROLLED_CHALLENGE_ACTION_RECALL`)

| Family | Florence OCR hit | canonical policy flag | OWLv2 hit | **V3 flag** | recall (CI) | crit. |
|---|---|---|---|---|---|---|
| GRAPHIC_SYMBOL (sanity) | 5 | 2 | 12 | **12** | 1.00 [0.76, 1] | B only |
| LOGO_LIKE_EMBLEM | 0 | 6 | 12 | **12** | 1.00 | F ✓ |
| SMALL_CORNER_MARK | 2 | 1 | 12 | **12** | 1.00 | G ✓ |
| REPEATED_TILED_MARK | 12 | 12 (reject) | 6 | **12** | 1.00 | J ✓ |
| BRAND_LIKE_TEXT_AND_SYMBOL (hybrid) | 12 | 0 | 8 | **8** | 0.67 [0.39, 0.86] | B only |
| TEXT_WATERMARK_TRANSLUCENT | 12 | **0** | 4 | **4** | 0.33 [0.14, 0.61] | D ✗ |
| GRAPHICAL_WATERMARK | 0 | 4 | **0** | **4** | 0.33 | E ✗ |
| EDGE_MARK | 1 | 3 | **1** | **3** | 0.25 [0.09, 0.53] | H ✗ |
| CENTER_OVERLAY_MARK | 4 | 2 | **0** | **2** | 0.17 [0.05, 0.45] | I ✗ |
| TEXT_WATERMARK_OPAQUE | 12 | **0** | 1 | **1** | 0.08 [0.01, 0.35] | C ✗ |

Overall V3 action recall **70/120 = 0.58** [0.49, 0.67] (B ✗). Channel
attribution: text-only 14, graphical-only 40, both 16, neither 50.
Transitions: `allow→review` 40, `review→review` 20, `reject→reject` 12,
`allow→allow` 60. Artifact regression **0** (K ✓), hard-reject bypass **0**
(L ✓).

### Criteria A–L

A ✓ · B ✗ · C ✗ · D ✗ · E ✗ · F ✓ · G ✓ · H ✗ · I ✗ · J ✓ · K ✓ · L ✓ →
**`V3_DUAL_CHANNEL_FAILED_DEVELOPMENT`**. Holdout metrics were not opened,
holdout Florence inference was not run, no lock or pass marker exists, and
nothing was retuned.

## 5. Channel-gap diagnosis (exact)

* **`TEXT_POLICY_GAP`** — TEXT_WATERMARK_OPAQUE and TEXT_WATERMARK_TRANSLUCENT:
  Florence OCR localized the injected word on **12/12 and 12/12** (MODEL
  DETECTED), the canonical policy returned `ambiguous_text_evidence` → allow
  on **12/12 and 12/12** (POLICY DID NOT FLAG). Under
  `watermark_policy_v4_runtime_evidence_parity_v1` a single, non-repeated,
  plausible token with confidence `unknown` cannot reach review or reject;
  only repetition does (REPEATED_TILED_MARK → 12/12 reject). This is the same
  single-overlay policy gap measured in B3-L4/L5 (H2), now confirmed on the
  actual V3 derivatives. It is evidence for a separate text-policy task, not a
  reason to change V3.
* **`GRAPHICAL_CHANNEL_GAP`** — GRAPHICAL_WATERMARK 0/12, CENTER_OVERLAY_MARK
  0/12, EDGE_MARK 1/12 OWLv2 hits at 0.25 (as in B3-L7); Florence adds only
  incidental `generated_text_artifact` reviews (4, 2, 3) when it misreads the
  mark as fragmented text. The graphical supplement covers compact corner
  marks, emblems and abstract symbols (12/12 each) and nothing else.
* Result: `MIXED`. Neither channel's gap is a threshold problem: the clean
  side is already at 0 new reviews, and lowering 0.25 was pre-registered as
  forbidden because B3-L7 showed it reintroduces clean responses.

## 6. What is and is not established

* Established (controlled, synthetic, 12 bases): the OWLv2 supplement at 0.25
  adds **no** clean review burden (0/12) while turning 12/12 of the three
  compact-mark families into reviews the canonical policy would mostly allow;
  composition is escalate-only with 0 regressions and 0 bypasses.
* Established: the canonical Florence text policy, unchanged, does **not**
  flag single-word opaque or translucent text watermarks that Florence itself
  reads (0/24), so a text-channel design that relies on the current policy
  cannot clear the text criteria.
* Not established: any production rate, any natural-positive precision or
  recall (`NATURAL_POSITIVE_EVIDENCE_MISSING`), behaviour on real brand logos
  or real watermarks. Prohibited wording is not used.

## 7. Verdicts

* `V3_DUAL_CHANNEL_FAILED_DEVELOPMENT` — diagnosed `TEXT_POLICY_GAP`,
  `GRAPHICAL_CHANNEL_GAP`, `MIXED`.
* `H4_DUAL_CHANNEL_SHADOW_NOT_SUPPORTED`.
* `NATURAL_POSITIVE_EVIDENCE_MISSING` remains.

## 8. Exact next step (owner decision; none taken here)

The text gap is a **policy** gap with full model evidence behind it (24/24 OCR
hits, 0/24 flags). The only pre-registrable candidate that is escalate-only
and needs no new inference is a text-policy shadow on the same frozen corpus:
"single overlay-like or centre text token with `unknown` confidence → review"
evaluated first on the 20 clean avatars (B3-L5 H2 already measured 3→15/20
reviews for the broad form, so the candidate must be narrower — e.g. typed
`areaBand`/`location` constraints) and only then on the text families.
Prompt or threshold changes to OWLv2 remain forbidden on this corpus; the
graphical gap (translucent icon, edge, centre) needs a different detector
study on new held-out constructs.

## 9. Safety

Florence: 96 local inferences (development only; 1 resource-guard trip with
checkpoint, 0 rows lost; median 43 s/img, one 56-min paging stall) · OWLv2 0 ·
Azure 0 · external image transmission 0 · production writes 0 · builds/deploys
0 · live decision diff 0 · originals **28/28** unchanged (SHA-256 + mtime) ·
Rater C artifacts untouched · `approveAvatarCandidate` deployment remains a
separate release blocker.
