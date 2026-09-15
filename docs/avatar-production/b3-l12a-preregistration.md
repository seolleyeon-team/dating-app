# B3-L12A — pre-registration: GDINO_BOX_GEOMETRY_FILTER_V1 (GDINO_GEOMETRY_CANDIDATES_V1)

Frozen **after the aggregate inventory of the 12 clean G1–G3 Grounding DINO
boxes and before any positive box geometry or filtered recall was read**
(contract digest `3e615dd3b443…` from
`avatar_gdino_geometry_filter.contract_digest()`, checked in CI). Designation:
**`CLEAN_DEVELOPMENT_DESIGNED`** — the rules were designed from the clean
development boxes, so clean development performance is hypothesis
confirmation, not validation; the only independent authority is the still
unopened B3-L11 holdout (G4–G5 + HOLDOUT_VARIANT, `DETECTOR_SPECIFIC_FROZEN_HOLDOUT`).

Immutable: B3-L11 `VISUAL_MARK_DETECTOR_FAILED_DEVELOPMENT`, holdout opened NO
(executions 0), Grounding DINO 0.25 development clean response 12/12, new
clean allow→review 10/12, overall 163/168, gaps in GRAPHICAL_WATERMARK_TRANSLUCENT
and EDGE_MARK; `TEXT_POLICY_GAP` unresolved; `GRAPHICAL_DETECTOR_STUDY_REQUIRED`;
`NATURAL_POSITIVE_EVIDENCE_MISSING`. Premise: clean response is the dominant
bottleneck, but positive sensitivity is not "solved" — a filter must not make
the critical families worse.

**`FIXED_OR_ENSEMBLE_REJECTED_BY_DEVELOPMENT_DOMINANCE`** — an OR over OWLv2
0.25 / Grounding DINO 0.35 / Florence grounding cannot respond on fewer clean
images than its most responsive component (Florence 4/12), so it cannot meet
A ≤ 1/12; it is not run and the holdout is not spent on it.

## 1. Detector and operating point (frozen; fresh authority)

`IDEA-Research/grounding-dino-tiny` @ `a2bb814dd30d776dcf7e30523b00659f4f141c71`,
Apache-2.0 (official model card). Box threshold 0.25 / text threshold 0.25
(historical B3-L11 point, fixed; no new threshold, grid, calibration or
per-query threshold). Queries "a logo", "a watermark", "a brand emblem",
"a graphic symbol", joined exactly as in B3-L11. Resize long side ≤ 2048, IoU
≥ 0.30, image-level construct hit. "a logo" dominance on clean avatars is an
observation only; the query label is **not** a predicate input.

## 2. Development capture provenance (exact reuse → 0 new development inference)

B3-L11 `capture_grounding-dino-tiny_development.jsonl`: revision, repository,
license, detector-set digest `086a32a65e05…`, construct digest `38ec105fc597…`,
DEV_VARIANT, floor 0.05 ≤ 0.25, originals unchanged — all verified. Every
operating point is a filter over the stored low-floor output.

## 3. Clean box inventory (12 clean G1–G3 avatars, Grounding DINO 0.25; aggregate)

35 boxes on 12/12 images (1–6 per image, median 3). Normalized area min /
Q1 / median / Q3 / max = 0.0004 / 0.0027 / 0.0092 / 0.0437 / 0.7377; width
0.018–0.99, height 0.020–0.92; aspect 0.80–5.52; centre x 0.37–0.62, centre y
0.38–0.96. Bands: area < 0.01 **18**, 0.01–0.03 **4**, 0.03–0.08 **8**,
0.08–0.20 0, 0.20–0.50 4, ≥ 0.50 1; aspect 1/3–3: 23, 3–4: 8, ≥ 4: 4. Border
touch 0, near-border (5 %) 19, full-frame-like 1. Three structures: (a) 18
tiny mid-image boxes (all centre-x mid, 16 at centre-y 0.3–0.6, sizes
0.02–0.12 wide, square-ish or ≈2.2 aspect) on 9/12 images; (b) 12 wide strips
at the bottom band (centre-y 0.92–0.96, aspect 2.7–5.5, width 0.34–0.44);
(c) 5 object-scale boxes (area 0.27–0.74). Images by tiny-box count: 0 → 3,
1 → 1, 2 → 7, 3 → 1.

Design consequence, stated before any positive is read: structure (a) sits at
the same scale as the injected marks and is not separable by scale/shape; a
"not mid-image" rule would be a mark-location rule (CENTER_OVERLAY_MARK and
torso text are safety-critical placements) and is therefore **not** a
candidate. The pre-registered expectation is that no scale/shape candidate
meets A; the study nevertheless runs to measure the positive side and to
diagnose precisely.

## 4. Candidate set (frozen; least → most aggressive; scale/shape only)

Features: `normalizedArea` and `aspectRatio` from the detector box and image
size. Band edges are the canonical watermark-evidence constants (TINY 0.03,
SMALL 0.08), a coarse object-scale edge 0.20 and the B3-L11 full-frame ratio
0.50; aspect caps 3 and 4. No finer geometry search is permitted
(`FINE_GEOMETRY_SEARCH_PROHIBITED`, enforced in code).

| Rank | ID | Predicate (box kept iff …) |
|---|---|---|
| 1 | G1 | keep box iff normalizedArea < 0.5 |
| 2 | G2 | keep box iff normalizedArea < 0.2 AND 1/4 < aspectRatio < 4 |
| 3 | G3 | keep box iff normalizedArea < 0.08 AND 1/3 < aspectRatio < 3 |
| 4 | G4 | keep box iff normalizedArea < 0.03 AND 1/3 < aspectRatio < 3 |

Forbidden predicate inputs: query label, score (beyond the frozen 0.25),
human labels, construct family, ground-truth boxes, participant group, base
id, filename, clean/positive flag, OCR text, identity. Shadow action =
`max(canonicalAction, review)` when a surviving box exists — review-only,
never reject, never downgrade.

## 5. Gate, selection, holdout

Gate A–L identical to B3-L11 (A ≤ 0.10 → ≤ 1/12 on development, 0/8 on
holdout; B ≥ 160/168 development, ≥ 107/112 holdout; C–J ≥ 0.90 per family
with holdout arithmetic n = 8 → 8/8, n = 16 → ≥ 15/16; K/L = 0). A soft
needs-review UI policy does not weaken this QA evidence gate. Selection among
eligible: highest minimum critical-family recall → highest overall recall →
lowest new clean burden → least aggressive rank. No eligible candidate →
`GDINO_GEOMETRY_FILTER_FAILED_DEVELOPMENT` with diagnosis
(`CLEAN_GEOMETRY_NOT_SEPARATING` / `POSITIVE_GEOMETRY_COLLISION` /
`EDGE_FAMILY_STILL_UNDERDETECTED` / `GRAPHICAL_WATERMARK_STILL_UNDERDETECTED` /
`MIXED`); no fifth candidate, no geometry or score adjustment, no holdout.
Otherwise the selected predicate, revision, prompts, thresholds, resize, IoU,
both B3-L11 digests and the development-input digest are frozen as
`GDINO_GEOMETRY_FILTER_CONTROLLED_SHADOW_CANDIDATE`, the B3-L11 holdout is
audited unopened, the HOLDOUT_VARIANT derivatives are generated and inferred
(Grounding DINO only, 120 + 8 rows), and evaluated once behind
`visual_mark_detector_v1_holdout.lock`; afterwards nothing is retuned.

Verdicts: `GDINO_GEOMETRY_FILTER_CONTROLLED_GATE_PASSED` →
`GDINO_GEOMETRY_FILTER_SUPPORTED_FOR_CONTROLLED_SHADOW_CANARY` (not production,
not natural-watermark, not live-integration validated); `…_HOLDOUT_FAILED`;
`…_FAILED_DEVELOPMENT`. Gap markers as in B3-L11; always
`NATURAL_POSITIVE_EVIDENCE_MISSING`. No worker/policy/env/build/deploy change;
`approveAvatarCandidate` deployment remains a separate release blocker.
