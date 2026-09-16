# B3-L14A — pre-registration: EDGE_MARK_GENERALIZATION_V1 (edge-mark proposal ceiling of the frozen zero-shot union)

Frozen **before any new detector inference and before any box-level audit of
the two B3-L13 EDGE_MARK misses** (contract digest `c11ffa3eaabf…` from
`avatar_edge_mark_generalization.contract_digest()`, construct digest
`e03ca29115b2…`, detector-set digest `086a32a65e05…` unchanged; all checked
in CI). Offline, decision-neutral research: no live integration, no policy,
worker, env, build or deploy change.

Immutable: B3-L11 `VISUAL_MARK_DETECTOR_FAILED_DEVELOPMENT`; B3-L12A
`GDINO_GEOMETRY_FILTER_FAILED_DEVELOPMENT`; **B3-L13
`PROPOSAL_UNION_COVERAGE_INSUFFICIENT`** (union 164/168, EDGE_MARK 10/12,
verifier NOT STARTED, holdout NOT OPENED); `TEXT_POLICY_GAP` unresolved;
`GRAPHICAL_DETECTOR_STUDY_REQUIRED`; `NATURAL_POSITIVE_EVIDENCE_MISSING`.
Whatever this study finds, B3-L13 stays as recorded: new evidence answers a
new hypothesis and never retroactively passes the old one.

Markers:
* **`EDGE_MARK_REMAINS_CRITICAL_FAMILY`** — EDGE_MARK is never treated as a
  diagnostic family the way the LOW-alpha text family is; 10/12 is a failure;
  the EDGE gate is not deleted and B3-L13 is not re-run with a changed gate.
* **`VERIFIER_STAGE_PROHIBITED_IN_B3_L14A`** — no crop embedding, no
  classifier fit, no out-of-fold scoring, no verifier threshold, no
  continuation of the B3-L13 verifier stage. Expected verifier embeddings 0,
  classifier fits 0.
* `GDINO_GEOMETRY_FILTER_PATH_CLOSED_ON_CURRENT_CORPUS`,
  `FACE_SUPPRESSION_PROHIBITED` remain in force.

## 1. Question

Does the FROZEN three-generator union (B3-L13 exact) give a sufficient
proposal ceiling on **new** synthetic edge marks, and if not, is the miss
placement-, size- or geometry-specific, or a structural zero-shot limit? The
study asks nothing about clean response, verifiers or policy.

## 2. Frozen proposal generators (B3-L13 exact; nothing retuned)

| Generator | Repository @ revision | License | Operating point |
|---|---|---|---|
| OWLv2 | `google/owlv2-base-patch16-ensemble` @ `cfd3195ba4ea9592eec887ded089f4c08eff231d` | apache-2.0 | 0.25 fixed |
| Grounding DINO tiny | `IDEA-Research/grounding-dino-tiny` @ `a2bb814dd30d776dcf7e30523b00659f4f141c71` | apache-2.0 | box 0.25 / text 0.25 fixed |
| Florence-2 phrase grounding | `florence-community/Florence-2-large-ft` @ `26b734a54fdfbf9c398351eedfabb7f27fc470b7` | MIT | presence, full-frame filter (area ≥ 0.50) |

Queries frozen: "a logo", "a watermark", "a brand emblem", "a graphic
symbol" — no edge-specific query, no addition/removal, no per-query threshold,
no prompt rewrite. No new detector. One low-floor inference per derivative
per detector; the operating point is a filter over the stored output. Match
rule: IoU ≥ 0.30, **no containment clause** (B3-L13 had none; none added);
`UNION_PROPOSAL_HIT` = at least one generator proposes a box with IoU ≥ 0.30
to the known mark box. Ground truth is evaluation authority only.

## 3. Construct contract (`EDGE_MARK_GENERALIZATION_V1`)

* **Bases:** the 20 owner-authorized generated avatars (originals never
  written; derivatives in memory / restricted scratch). Development G1–G3
  (12 bases); holdout G4–G5 (8 bases).
* **Edge axis:** TOP · BOTTOM · LEFT · RIGHT. Corners are excluded (they
  belong to SMALL_CORNER_MARK).
* **Inset (one rule):** square mark box of side `round(size × min(W, H))`
  whose outer side sits `round(0.02 × min(W, H))` px inside the touching
  image edge, centred at 0.50 along that edge.
* **Size axis:** the B3-L11 canonical bands, reused: small 0.035 · medium
  0.07 (mark side / min(W, H)); no intermediate size search.
* **Alpha:** OPAQUE 1.00 only (transparency is not mixed into the edge
  question).
* **Geometries (synthetic PIL primitives; real trademarks refused by
  blocklist; none of the B3-L11 geometries reused):**
  * DEV_G1 `open_hexagon_emblem` — hexagon outline with one side omitted,
    thick stroke, filled centre dot.
  * DEV_G2 `paired_chevron_emblem` — two stacked filled chevrons in two
    contrasting colours.
  * HOLDOUT_G1 `broken_ring_emblem` — ring arc with a 60° gap, thick stroke,
    small filled square at the centre.
  * HOLDOUT_G2 `offset_bar_emblem` — two horizontal bars offset diagonally
    with a filled disc between them.
  DEV and HOLDOUT geometries are distinct by name and by rendered pixels
  (CI-tested), and were fixed here before any performance number.
* **Matrix:** 4 edges × 2 sizes × 2 geometries = 16 conditions per base.
  Development 16 × 12 = **192** positive derivatives; holdout 16 × 8 =
  **128**. No clean rows (proposal-ceiling study only).

## 4. Development gate (pre-registered; union proposal recall)

| Criterion | Floor | n | Required |
|---|---|---|---|
| A overall | ≥ 0.95 | 192 | ≥ 183 |
| B TOP · C BOTTOM · D LEFT · E RIGHT | ≥ 0.90 each | 48 | ≥ 44 |
| F small · G medium | ≥ 0.90 each | 96 | ≥ 87 |
| H DEV_G1 · I DEV_G2 | ≥ 0.90 each | 96 | ≥ 87 |
| J each edge × size × geometry cell (16) | ≥ 0.90 | 12 | ≥ **11/12** |

Any failure → `EDGE_PROPOSAL_GENERALIZATION_FAILED_DEVELOPMENT` and STOP: no
geometry, size, edge, threshold, prompt, IoU or detector change. All pass →
`EDGE_PROPOSAL_GENERALIZATION_DEVELOPMENT_PASSED`, frozen as a marker
(contract digest, detector-set digest, revisions, prompts, thresholds, sizes,
edges, inset, DEV/HOLDOUT geometry ids, IoU, development-input digest); only
then may holdout derivatives be generated. Individual-detector recalls are
reported descriptively on the same axes.

## 5. Holdout (`EDGE_CONSTRUCT_SPECIFIC_FROZEN_HOLDOUT`, one shot)

G4–G5 + HOLDOUT geometries, generated / inferred / evaluated exactly once
behind `edge_proposal_generalization_v1_holdout.lock` (a second evaluation
fails closed; no further holdout inference after the lock). The bases were
used by earlier feature studies, so this holdout is **not globally unseen**;
what is unseen before performance is the holdout geometries, their
derivatives and the detector outputs on them. Same gate structure: overall ≥
0.95 (n 128 → ≥ **122**); each edge ≥ 0.90 (n 32 → ≥ 29); each size ≥ 0.90
(n 64 → ≥ 58); each holdout geometry ≥ 0.90 (n 64 → ≥ 58); each cell ≥ 0.90
(n 8 → **8/8**). After the result nothing is retuned (threshold, prompt,
geometry, size, inset, matching, detector set).

The original B3-L11 holdout (G4–G5 + HOLDOUT_VARIANT of
VISUAL_MARK_CHALLENGE_V3) is a different artifact and is never generated,
inspected, inferred or evaluated here; its canonical lock is not created.

## 6. Interpretation (pre-registered)

Development or holdout failure → `EDGE_PROPOSAL_GAP_REPLICATED` with
sensitivity markers from the failed criteria: `EDGE_PLACEMENT_SENSITIVE`
(some edges fail while others pass), `EDGE_SIZE_SENSITIVE` (one size band
fails, the other passes), `EDGE_GEOMETRY_SENSITIVE` (one geometry fails, the
other passes), `EDGE_ZERO_SHOT_GENERALIZATION_LIMIT` (failure not attributable
to one axis: every edge, every size or every geometry fails, or no single-axis
pattern), `MIXED` when more than one applies. Development and holdout pass →
`EDGE_PROPOSAL_GAP_NOT_REPLICATED_ON_NEW_CONSTRUCTS`, read strictly as: the
frozen union generalized on the new edge constructs, while the B3-L13
construct keeps its unresolved misses. A pass does not unlock the B3-L13
verifier; a continuation needs a new owner-approved hypothesis (proposal
augmentation, new detector, supervised detector, or a new independently
justified matching architecture). If the gap replicates, the next step is a
deterministic edge-scan proposal channel + content verifier, or supervised
detector data design — not zero-shot threshold retuning.

## 7. Old-miss decomposition (descriptive, after the freeze)

Only after this construct is frozen and committed (marker with the freeze
commit is required by the evaluator) are the twelve B3-L13 EDGE_MARK
development rows audited, aggregate-only, into the frozen categories
`NO_RELEVANT_PROPOSAL` · `PROPOSAL_WRONG_LABEL_ONLY` ·
`LOCALIZATION_MISS_IOU_BELOW_030` · `FULL_FRAME_FILTER_EFFECT` · `OTHER`
(query-labelled matching box present at the capture floor but below the
frozen operating point). The result cannot change this construct, gate,
match rule (a diagnostic IoU near 0.30 never lowers the rule) or thresholds.

## 8. Safety

CPU only, one model resident, B3-L11 resource guards unchanged (start gate
per model kind; per-row hard guard 0.6 GB never lowered), checkpoint-resume.
Originals 28/28 verified before/after (SHA-256 + mtime). Azure / external
vision / external OCR / raw-image transmission 0. Repository artifacts are
aggregate only (no derivative, filename, UID, private path, per-image
detector row, box or score). A soft needs-review UI policy does not weaken any
QA gate; the canonical watermark policy is untouched.
`approveAvatarCandidate` deployment remains a separate release blocker.
