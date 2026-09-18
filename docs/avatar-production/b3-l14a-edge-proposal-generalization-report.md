# B3-L14A — edge-mark proposal generalization of the frozen zero-shot union: result

Offline, decision-neutral research on new synthetic edge constructs
(`EDGE_MARK_GENERALIZATION_V1`, contract `c11ffa3eaabf…`, construct
`e03ca29115b2…`, detector set `086a32a65e05…` unchanged), frozen in commit
`cef1b5be` before any inference and before any box-level audit of the B3-L13
misses ([b3-l14a-preregistration.md](b3-l14a-preregistration.md)). No
verifier stage (embeddings 0, classifier fits 0), no external calls, no
policy / worker / env / build / deploy change. Aggregate only.

**Verdict: `EDGE_PROPOSAL_GENERALIZATION_HOLDOUT_FAILED`** · development
`EDGE_PROPOSAL_GENERALIZATION_DEVELOPMENT_PASSED` (190/192) · holdout opened
once (125/128; one cell 5/8) · **`EDGE_PROPOSAL_GAP_REPLICATED`** with the
pre-registered marker `EDGE_ZERO_SHOT_GENERALIZATION_LIMIT` ·
`EDGE_MARK_REMAINS_CRITICAL_FAMILY` · B3-L13
`PROPOSAL_UNION_COVERAGE_INSUFFICIENT` immutable · `TEXT_POLICY_GAP`
unresolved · `GRAPHICAL_DETECTOR_STUDY_REQUIRED` ·
`NATURAL_POSITIVE_EVIDENCE_MISSING`.

## 1. The finding in one sentence

On new opaque edge marks the frozen three-generator union proposes a matching
box for 190/192 development and 125/128 holdout derivatives, passing every
marginal criterion (overall, each of the four edges, both sizes, both
geometries) on both splits, but it fails the pre-registered per-cell floor
once on holdout — TOP edge × medium size × offset-bar emblem at 5/8 against
a required 8/8 — so the edge proposal gap is replicated on a new construct,
now as a placement × size × geometry interaction rather than a marginal
edge, size or geometry effect.

## 2. What was frozen (unchanged)

Generators exactly as B3-L13: OWLv2 `cfd3195b…` at 0.25, Grounding DINO
tiny `a2bb814d…` at 0.25/0.25, Florence-2-large-ft `26b734a5…` phrase
grounding (presence, full-frame filter); four queries; IoU ≥ 0.30, no
containment. Construct: edges TOP/BOTTOM/LEFT/RIGHT; sizes 0.035/0.07
(B3-L11 canonical); OPAQUE only; inset 0.02 × min(W, H); DEV geometries
`open_hexagon_emblem`, `paired_chevron_emblem`; HOLDOUT geometries
`broken_ring_emblem`, `offset_bar_emblem`; 16 conditions per base.

## 3. Development (G1–G3, 12 bases, 192 derivatives; inference 192 × 3)

Provenance exact for all three captures (revision, repo, license, contract /
construct / detector-set digests, `EDGE_DEV_VARIANT`, originals unchanged).

| Criterion | Result | Required | |
|---|---|---|---|
| A overall union proposal recall | **190/192 (0.990)** | ≥ 183 | ✓ |
| B TOP | 47/48 | ≥ 44 | ✓ |
| C BOTTOM | 47/48 | ≥ 44 | ✓ |
| D LEFT | 48/48 | ≥ 44 | ✓ |
| E RIGHT | 48/48 | ≥ 44 | ✓ |
| F small | 94/96 | ≥ 87 | ✓ |
| G medium | 96/96 | ≥ 87 | ✓ |
| H open_hexagon_emblem | 94/96 | ≥ 87 | ✓ |
| I paired_chevron_emblem | 96/96 | ≥ 87 | ✓ |
| J 16 cells | 14 × 12/12, **TOP·small·hexagon 11/12, BOTTOM·small·hexagon 11/12** | ≥ 11/12 each | ✓ |

Individual generators (descriptive): Grounding DINO 189/192 (TOP 46, BOTTOM
47, LEFT 48, RIGHT 48); Florence grounding 170/192 (TOP 42, BOTTOM 43, LEFT
44, RIGHT 41; small 79, medium 91); **OWLv2 68/192 (TOP 3/48, LEFT 11,
RIGHT 19, BOTTOM 35)**. Proposals by source: Grounding DINO 1287, Florence
965, OWLv2 73. Development-pass marker frozen (development-input digest
`fc62c69fc5c1…`); only then were holdout derivatives generated.

## 4. Holdout (`EDGE_CONSTRUCT_SPECIFIC_FROZEN_HOLDOUT`; G4–G5, 8 bases, 128 derivatives; opened exactly once)

Provenance exact; `EDGE_HOLDOUT_VARIANT`; lock
`edge_proposal_generalization_v1_holdout.lock` written; no retuning after.

| Criterion | Result | Required | |
|---|---|---|---|
| A overall | **125/128 (0.977)** | ≥ 122 | ✓ |
| B TOP | 29/32 | ≥ 29 | ✓ (at floor) |
| C BOTTOM | 32/32 | ≥ 29 | ✓ |
| D LEFT | 32/32 | ≥ 29 | ✓ |
| E RIGHT | 32/32 | ≥ 29 | ✓ |
| F small | 64/64 | ≥ 58 | ✓ |
| G medium | 61/64 | ≥ 58 | ✓ |
| H broken_ring_emblem | 64/64 | ≥ 58 | ✓ |
| I offset_bar_emblem | 61/64 | ≥ 58 | ✓ |
| **J TOP · medium · offset_bar_emblem** | **5/8** | 8/8 | **✗** |
| J other 15 cells | 8/8 each | 8/8 | ✓ |

Individual generators (descriptive): Grounding DINO 125/128 — identical to
the union on every axis (the union adds nothing beyond it); Florence 111/128
(TOP 23/32; offset_bar 48/64); **OWLv2 9/128 (0.07)**. Proposals by source:
Grounding DINO 660, Florence 555, OWLv2 9.

## 5. Interpretation (pre-registered rules applied)

* `EDGE_PROPOSAL_GAP_REPLICATED`: the frozen union fails a pre-registered
  criterion on a new construct.
* Sensitivity marker from the frozen rule set: no edge, size or geometry
  criterion failed, so the failure has no single-axis pattern →
  `EDGE_ZERO_SHOT_GENERALIZATION_LIMIT`. Descriptively the three misses
  share one cell (TOP × medium × offset-bar); TOP is the only edge with
  misses on both splits (47/48, 29/32) and was also the B3-L13 EDGE_MARK
  placement — reported as an observation, not as a re-reading of the marker.
* B3-L13 stays `PROPOSAL_UNION_COVERAGE_INSUFFICIENT` with its unresolved
  10/12; the development pass here is evidence about the new construct only
  and does not unlock the B3-L13 verifier.

## 6. B3-L13 EDGE_MARK miss decomposition (descriptive; after the freeze)

Twelve B3-L11 development EDGE_MARK rows, union hits 10, misses 2; on both
misses the best union IoU band at the operating points is 0. Per generator
on the misses: OWLv2 `NO_RELEVANT_PROPOSAL` 2; **Grounding DINO `OTHER` 2**
(a query-labelled box matching the mark exists at the 0.05 capture floor but
below the frozen 0.25 threshold); Florence `FULL_FRAME_FILTER_EFFECT` 1
(diagnostic: a dropped full-frame box could not have matched a small mark),
`NO_RELEVANT_PROPOSAL` 1. Per the contract this changes nothing: the IoU
rule, thresholds and construct are not retuned from a diagnostic; a lower
Grounding DINO threshold is a separate future hypothesis with its own clean
cost (B3-L11: 12/12 clean response already at 0.25).

## 7. What is and is not established

* Established (controlled, 20 bases): the frozen union's edge proposal
  ceiling on opaque synthetic edge marks is high on average (≥ 0.97 both
  splits) and is carried entirely by Grounding DINO; it is not reliable per
  cell — one holdout cell misses 3/8 — and OWLv2 contributes almost nothing on
  edges.
* Not established: anything about translucent edge marks, natural marks,
  real logos, clean-response cost, verifiers, or production rates.

## 8. Exact next step (owner decision; none taken here)

Because the gap replicates, the next step is not zero-shot threshold
retuning. Pre-registrable candidates: (1) a deterministic edge-scan proposal
channel (fixed strips along the four edges as proposals) feeding a content
verifier, evaluated with the same union coverage gate first; (2) supervised
logo/watermark detector data design. Any continuation of the B3-L13 verifier
needs a new owner-approved hypothesis. `approveAvatarCandidate` deployment
remains a separate release blocker.

## 9. Safety

Inference: development 576 + holdout 384 rows, CPU, one model resident;
resource guards unchanged (start gate 4.0/3.0/4.0 GB, per-row 0.6 GB; 83 +
7 guard-triggered retries with checkpoint-resume, guards never lowered).
Verifier embeddings 0 · classifier fits 0 · Azure/external 0 · production
writes 0 · builds/deploys 0 · live decision diff 0 · originals **28/28**
unchanged (SHA-256 + mtime before/after) · original B3-L11 holdout untouched
(no captures, no lock, no selected marker) · Rater C artifacts untouched.
