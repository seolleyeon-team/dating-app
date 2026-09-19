# B3-L15A — deterministic edge scan + frozen union + local CLIP verifier: development result

Offline, decision-neutral research on a **new hypothesis**
(`DETERMINISTIC_EDGE_SCAN_WITH_CONTENT_VERIFIER_V1`, contract
`de771758cc30…`, scan `1b45958a524d…`, detector set `086a32a65e05…`
unchanged), frozen in commit `092d5910` before any CLIP embedding or
scan-verifier number ([b3-l15a-preregistration.md](b3-l15a-preregistration.md)).
No new detector inference (development captures reused with exact
provenance), no external calls, no policy / worker / env / build / deploy
change. Aggregate only.

**Verdict: `EDGE_SCAN_VERIFIER_FAILED_DEVELOPMENT`** · proposal ceiling
**passed** (broad 166/168 with EDGE_MARK 12/12; edge 192/192) · no verifier
threshold eligible on OOF development · diagnosis
`BROAD_MARK_RECALL_REGRESSION` + `EDGE_SCAN_CLEAN_BURDEN_TOO_HIGH` +
`SYNTHETIC_STYLE_NOT_SEPARATING` (`MIXED`) · known-construct stress **not
executed** · original B3-L11 holdout **unopened** · B3-L13
`PROPOSAL_UNION_COVERAGE_INSUFFICIENT` and B3-L14A
`EDGE_PROPOSAL_GENERALIZATION_HOLDOUT_FAILED` unchanged ·
`FROZEN_THREE_GENERATOR_ZERO_SHOT_EDGE_LIMIT` · `TEXT_POLICY_GAP` unresolved
· `GRAPHICAL_DETECTOR_STUDY_REQUIRED` · `NATURAL_POSITIVE_EVIDENCE_MISSING`.

## 1. The finding in one sentence

The deterministic edge scan closes the proposal ceiling that B3-L13 and
B3-L14A could not (every EDGE_MARK and every B3-L14A edge cell now has a
matching proposal, the two B3-L13 misses are recovered by scan tiles alone),
and the CLIP verifier keeps every edge cell at 12/12 at every threshold; but
on the twelve clean avatars the verifier lets 2 images through at 0.50 and
0.65 (ceiling 1/12) and only reaches 1/12 at 0.80, where medium translucent
text (5/12), high translucent text (8/12) and EDGE_MARK (9/12) fall below
their floors — so no single threshold satisfies clean, broad and edge gates
together.

## 2. Proposal ceiling (no verifier; existing captures; 40 scan tiles per 1254-px image)

| Set | Criterion | Result | Required | |
|---|---|---|---|---|
| B3-L11 G1–G3 DEV | A overall gated recall | **166/168 (0.988)** | ≥ 160 | ✓ |
| | EDGE_MARK (H) | **12/12** (B3-L13: 10/12) | ≥ 11 | ✓ |
| | other seven critical families | 24/24 · 12/12 · 11/12 · 11/12 · 24/24 · 12/12 · 12/12 | ≥ 0.90 | ✓ |
| B3-L14A G1–G3 EDGE_DEV | overall | **192/192** (B3-L14A union: 190/192) | ≥ 183 | ✓ |
| | each edge / size / geometry / cell | all 48/48 · 96/96 · 96/96 · 12/12 | ≥ 0.90 / 11/12 | ✓ |

Analytic guarantee (CI): any mark with side ≤ 0.07·min(W,H) and inset ≤
0.02·min(W,H) is covered at GT_COVERAGE ≥ 0.95 by one tile anywhere along any
edge; measured: matched by scan only 2 (B3-L11 dev) + 2 (B3-L14A dev), by
detector only 92, by both 82 (B3-L11 dev). Clean side: 525 runtime proposals
on 12 clean images (scan 480, Grounding DINO 35, Florence 10). Two
non-edge misses remain (one MEDIUM translucent text, one translucent
graphical watermark) — outside the scan's remit.

## 3. Verifier development (group OOF; 19,607 proposal embeddings; 3 fold fits)

Labels: positive 3,353 (scan 336, Grounding DINO 1,662, Florence 1,211, OWLv2
144), clean negative 525, excluded (unmatched on positive images; scored,
never trained on) 15,729. Leakage audit: every fold trains on 8 bases and
evaluates 4 disjoint bases; a base's clean, B3-L11 and B3-L14A proposals share
its fold.

| Threshold | Clean new allow→review (≤ 1/12) | Broad overall (≥ 160/168) | Broad failed | Edge gate (192/192, cells 11/12) | Eligible |
|---|---|---|---|---|---|
| 0.20 | 10/12 | 166 | J1 | ✓ | ✗ |
| 0.35 | 9/12 | 166 | J1 | ✓ | ✗ |
| 0.50 | **2/12** | 166 | J1 | ✓ | ✗ |
| 0.65 | 2/12 | 162 | J1, J5 (MEDIUM 8/12) | ✓ | ✗ |
| 0.80 | 1/12 | 153 | J2, J4 (HIGH 8/12), J5 (MEDIUM 5/12), J9 (EDGE 9/12) | ✓ | ✗ |

Bypass 0, downgrade 0 at every threshold. Selection: NONE.

Descriptive (same OOF scores): at 0.50 the clean survivors are 7 scan tiles
on 2 images, 7 Grounding DINO boxes on 2 images and 4 Florence boxes on 1
image; the scan channel's clean tiles are mostly far from the boundary (421
of 480 below 0.20) while the detector clean boxes carry the persistent hard
negatives (Grounding DINO 13 of 35 in 0.35–0.50, 7 above 0.50). On the
positive side the verifier scores matched proposals high (≥ 0.80: scan 239
of 336, Grounding DINO 1,550 of 1,662, Florence 1,131 of 1,211), so the
recall loss at 0.65–0.80 is concentrated in translucent text, whose matched
boxes sit in the 0.50–0.80 band.

## 4. What is and is not established

* Established (controlled, 12 bases): a deterministic 0.16·min edge scan
  removes the edge proposal ceiling on both synthetic edge constructs
  without touching any zero-shot detector; the B3-L13 CLIP verifier recipe
  separates opaque synthetic edge emblems from clean edge crops well, but
  does not separate the union's clean hard negatives and translucent text
  marks at one threshold on this corpus.
* Not established: anything about natural marks, real logos, production
  rates, other verifier recipes, or other scan geometries (none were tried).

## 5. Why the study stops here

The pre-registered rule is one threshold satisfying clean ≤ 1/12, broad
J2–J12 and the edge gate together; none does. No scan tile, stride, crop,
CLIP, classifier, threshold or zero-shot change was made; the
known-construct stress gate and the original B3-L11 holdout were not run
(no G4–G5 embeddings, no B3-L11 holdout captures, no lock, no marker).

## 6. Exact next step (owner decision; none taken here)

The scan side is settled; the open problem is now the verifier's clean
separation at a recall-preserving threshold. Pre-registrable candidates:
(1) verifier recipe study with the proposal-ceiling contract held fixed —
e.g. one fixed non-linear head or a different frozen embedding — on the same
OOF folds; (2) per-source analysis is not allowed as a feature, but a
pre-registered decision to evaluate the scan channel *alone* (scan tiles
only, no zero-shot union) against the same gates would test whether the
clean burden is a detector-proposal artefact; (3) supervised logo/watermark
detector data design. Any of these needs a new owner-approved hypothesis.
`approveAvatarCandidate` deployment remains a separate release blocker.

## 7. Safety

New detector inference 0 · CLIP embeddings 19,607 (development only) ·
classifier fits 3 (OOF folds; no final fit) · Azure/external 0 · production
writes 0 · builds/deploys 0 · live decision diff 0 · originals **28/28**
unchanged · original B3-L11 holdout unopened · B3-L14A G4–G5 verifier
outputs never generated · Rater C artifacts untouched.
