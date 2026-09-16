# B3-L13 — multi-detector proposal union + local crop verifier: coverage gate result

Offline, decision-neutral research. **0 new model inference** (development
proposal captures reused from B3-L11 with exact provenance; no verifier
embedding was ever extracted; holdout never generated), no external calls,
no policy / worker / env / build / deploy change. Aggregate only. Contract
digest `f2c38dc9feaa…` frozen in
[b3-l13-preregistration.md](b3-l13-preregistration.md) before any embedding
or out-of-fold score.

**Verdict: `PROPOSAL_UNION_COVERAGE_INSUFFICIENT`** · diagnosis
`PROPOSAL_CEILING_INSUFFICIENT` + `EDGE_PROPOSAL_GAP` (`MIXED`) · verifier
stage **not started** · holdout opened **NO**, executions **0** ·
`TEXT_POLICY_GAP` unresolved · text detector controlled gap open ·
`GRAPHICAL_DETECTOR_STUDY_REQUIRED` · `NATURAL_POSITIVE_EVIDENCE_MISSING`.

Markers in force: `GDINO_GEOMETRY_FILTER_PATH_CLOSED_ON_CURRENT_CORPUS`,
`FACE_SUPPRESSION_PROHIBITED`,
`PROPOSAL_UNION_WITH_DOWNSTREAM_VERIFIER_DISTINCT_FROM_REJECTED_RAW_OR`.
B3-L11 (`VISUAL_MARK_DETECTOR_FAILED_DEVELOPMENT`) and B3-L12A
(`GDINO_GEOMETRY_FILTER_FAILED_DEVELOPMENT`) stay immutable.

## 1. The finding in one sentence

The frozen three-detector union proposes a matching box for 164 of 168
gated positives (0.976) and for every family except EDGE_MARK, where the
union reaches only 10/12 (all three generators miss the same two edge
constructs) — below the pre-registered 0.90 family floor — so the verifier,
which can only remove proposals, could never satisfy J9, and the study stops
before any embedding is extracted, exactly as the coverage gate requires.

## 2. What was frozen (unchanged)

Proposal generators = the B3-L11 baselines, exact: OWLv2 `cfd3195b…` at
0.25, Grounding DINO tiny `a2bb814d…` at 0.25/0.25, Florence-2-large-ft
`26b734a5…` phrase grounding (presence, full-frame filter); four queries
unchanged; IoU ≥ 0.30. Verifier contract (production CLIP ViT-L/14
`32bd6428…`, MIT via the official openai/CLIP repository LICENSE; 15 % padded
deterministic crop; one fixed L2 logistic regression; threshold grid
0.20–0.80; leave-one-group-out folds; ambiguous-proposal exclusion; gate
J1–J12) was frozen but **never exercised**.

## 3. Development proposal provenance and coverage (G1–G3 + DEV_VARIANT)

Provenance exact for all three captures (revision, repo, license,
detector-set digest `086a32a65e05…`, construct digest `38ec105fc597…`,
DEV_VARIANT, originals unchanged) → development proposal inference 0.

| Coverage criterion | Result | Floor | |
|---|---|---|---|
| A overall gated-positive proposal recall | **164/168 (0.976)** | ≥ 160 | ✓ |
| B TEXT_WATERMARK_OPAQUE | 24/24 | ≥ 22 | ✓ |
| C TEXT_WATERMARK_TRANSLUCENT_HIGH | 12/12 | ≥ 11 | ✓ |
| D TEXT_WATERMARK_TRANSLUCENT_MEDIUM | 11/12 | ≥ 11 | ✓ |
| E GRAPHICAL_WATERMARK_TRANSLUCENT | 11/12 | ≥ 11 | ✓ |
| F LOGO_LIKE_EMBLEM | 24/24 | ≥ 22 | ✓ |
| G SMALL_CORNER_MARK | 12/12 | ≥ 11 | ✓ |
| **H EDGE_MARK** | **10/12** | ≥ 11 | **✗** |
| I CENTER_OVERLAY_MARK | 12/12 | ≥ 11 | ✓ |

Other families (not gated): BRAND_LIKE 12/12, REPEATED_TILED 12/12,
GRAPHIC_SYMBOL 24/24, LOW alpha (diagnostic) 10/12. Clean side, descriptive:
45 union proposals on 12/12 clean images (1–10 per image; Grounding DINO 35,
Florence 10, OWLv2 0). Positive side proposals by source: Grounding DINO
1046, Florence 735, OWLv2 96.

Edge-mark contribution per generator at its baseline (from the B3-L11
aggregate): OWLv2 0/12, Grounding DINO 10/12, Florence 5/12 — the union adds
nothing beyond Grounding DINO on this family; the same two edge derivatives
are missed by all three.

## 4. Why the study stops here

The coverage gate is the pre-registered first gate precisely because a
downstream verifier cannot recover a proposal that does not exist. With
EDGE_MARK at 10/12 the pipeline ceiling on J9 is 0.83 regardless of any
verifier, so building, embedding and scoring one would be post-hoc work with
no possible pass. No classifier was fit, no crop was embedded, no threshold
was read, and the B3-L11 holdout remains unopened (no holdout captures for
any detector, no holdout embeddings, no lock).

## 5. What is and is not established

* Established (controlled, 12 bases): the frozen union's proposal ceiling is
  high everywhere except the small edge-top mark; the union does not raise
  edge recall above the best single generator.
* Not established: anything about the verifier (never run), natural
  watermarks, real logos, or production rates.

## 6. Exact next step (owner decision; none taken here)

The edge gap is now the single blocking family on the proposal side, and it
is a detector miss at a small size band (0.035) on the top edge. Two
pre-registrable options: (1) a **proposal-ceiling study on edge marks
only** — new held-out edge constructs (both size bands, several geometries)
with the frozen generators, to learn whether the miss is size-, geometry- or
placement-specific before any pipeline work; (2) if the owner accepts a
relaxed *proposal* floor for EDGE_MARK (e.g. reporting it as diagnostic like
LOW alpha), re-run this exact B3-L13 contract unchanged — the verifier stage
and the untouched B3-L11 holdout are ready. Neither changes any detector,
prompt, crop or classifier parameter. `approveAvatarCandidate` deployment
remains a separate release blocker.

## 7. Safety

Proposal inference 0 · verifier embedding 0 · Azure/external 0 · production
writes 0 · builds/deploys 0 · live decision diff 0 · originals **28/28**
unchanged · B3-L11 holdout unopened · all prior locks and Rater C artifacts
untouched.
