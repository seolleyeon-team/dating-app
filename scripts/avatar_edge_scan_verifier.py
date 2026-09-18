"""B3-L15A — DETERMINISTIC_EDGE_SCAN_WITH_CONTENT_VERIFIER_V1 (pre-registered, decision-neutral research).

New hypothesis (B3-L13 and B3-L14A stay failed as recorded):

    frozen zero-shot union (B3-L13 exact)  OR  deterministic edge-scan tiles (EDGE_SCAN_PROPOSAL_V1)
        -> proposal crops -> local CLIP content verifier (B3-L13 recipe, never run before)
        -> review-only shadow decision

The scan is not a detector and not object localization: it is a high-recall
crop-proposal generator built from image dimensions only
(SCAN_CROP_COVERAGE_NOT_OBJECT_LOCALIZATION).  Its match contract is GT
coverage >= 0.95 by a tile; the zero-shot detector match stays IoU >= 0.30
with no containment clause.  No zero-shot threshold, prompt, filter or
detector changes (FROZEN_THREE_GENERATOR_ZERO_SHOT_EDGE_LIMIT is the only
allowed reading of the prior edge misses).  Everything below is frozen before
any CLIP embedding or scan-verifier performance exists.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_edge_mark_generalization as eg  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_proposal_verifier as pv  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402
import avatar_visual_mark_eval as ev  # noqa: E402

VERSION = "DETERMINISTIC_EDGE_SCAN_WITH_CONTENT_VERIFIER_V1"
SCAN_VERSION = "EDGE_SCAN_PROPOSAL_V1"
SCAN_SOURCE = "edge_scan"
SCAN_MARKER = "SCAN_CROP_COVERAGE_NOT_OBJECT_LOCALIZATION"
ZERO_SHOT_LIMIT = "FROZEN_THREE_GENERATOR_ZERO_SHOT_EDGE_LIMIT"
CRITICAL_MARKER = eg.CRITICAL_MARKER
EDGE_DIAGNOSTIC_ALLOWED = False
STRESS_NAME = "KNOWN_CONSTRUCT_STRESS_GATE"
STRESS_DATASET = "l14a_holdout"
CEILING_CLOSED_MARKER = "EDGE_PROPOSAL_CEILING_GAP_CLOSED_BY_DETERMINISTIC_SCAN"
SCORE_ROLE = pv.SCORE_ROLE                                   # UNCALIBRATED_VERIFIER_SCORE
DEVELOPMENT_EVIDENCE = "GROUP_OUT_OF_FOLD"
SELECTED_ROLE = "EDGE_SCAN_CLIP_VERIFIER_CONTROLLED_SHADOW_CANDIDATE"
UNMATCHED_POSITIVE_IMAGE_PROPOSALS = "EXCLUDED_FROM_TRAINING_SCORED_IN_EVALUATION"
NEW_REVIEW_CEILING = ev.NEW_REVIEW_CEILING                   # 0.10 -> <= 1/12 development; 0/8 holdout
OVERALL_RECALL_FLOOR = ev.OVERALL_RECALL_FLOOR               # 0.95
FAMILY_RECALL_FLOOR = ev.FAMILY_RECALL_FLOOR                 # 0.90
NO_ZERO_SHOT_RETUNE = ("grounding-dino 0.20/0.15", "owlv2 threshold", "florence filter", "edge-specific prompt", "query add/remove", "IoU relaxation",
                       "containment in detector matching", "new zero-shot detector", "raw score re-search")
NO_RETUNE_AFTER_HOLDOUT = ("scan tile", "stride", "matching", "CLIP", "crop", "classifier", "threshold", "zero-shot threshold", "prompt", "family", "gate")
NEW_DETECTOR_INFERENCE_EXPECTED = {"development": 0, "stress": 0, "holdout": "B3-L11 holdout only (3 x 128)"}
PRIOR_STATUS = {**eg.PRIOR_STATUS, "B3_L14A": "EDGE_PROPOSAL_GENERALIZATION_HOLDOUT_FAILED", "B3_L14A_DEVELOPMENT": "190/192", "B3_L14A_HOLDOUT": "125/128",
                "B3_L14A_FAILED_CELL": "TOP x medium x offset_bar_emblem 5/8 (required 8/8)", "B3_L14A_INTERPRETATION": "EDGE_PROPOSAL_GAP_REPLICATED",
                "EDGE_MARK": CRITICAL_MARKER, "ZERO_SHOT_READING": ZERO_SHOT_LIMIT}

# ------------------------------------------------------------------ frozen zero-shot generators (B3-L13 exact)

PROPOSAL_GENERATORS = dict(pv.PROPOSAL_GENERATORS)
PROMPTS = det.PROMPTS
THRESHOLDS = dict(eg.THRESHOLDS)
DETECTOR_SET_DIGEST_PREFIX = eg.DETECTOR_SET_DIGEST_PREFIX
IOU_MATCH = pv.IOU_MATCH                                     # 0.30
CONTAINMENT_ADDED_TO_DETECTOR_MATCH = False
detector_proposals = pv.union_proposals

if det.contract_digest()[:12] != DETECTOR_SET_DIGEST_PREFIX or IOU_MATCH != 0.30:
    raise RuntimeError("B3-L15A requires the frozen DETECTOR_CANDIDATE_SET_V1 and the canonical IoU rule")

# ------------------------------------------------------------------ deterministic edge scan (image dimensions only)

EDGES = eg.EDGES                                             # TOP / BOTTOM / LEFT / RIGHT
TILE_REL = 0.16                                              # square tile side / min(W, H)
MAX_MARK_REL = max(c3.SIZE_BANDS.values())                   # 0.07 canonical max mark side
EDGE_INSET_REL = eg.INSET["relative"]                        # 0.02 B3-L14A frozen inset envelope
MAX_SPACING_REL = TILE_REL - MAX_MARK_REL                    # 0.09 max adjacent tile-centre spacing
SCAN_COVERAGE_FLOOR = 0.95                                   # SCAN_MATCH: GT mark area covered by one tile
ANALYTIC_GUARANTEE = {"markSideMaxRel": MAX_MARK_REL, "insetMaxRel": EDGE_INSET_REL, "farEdgeMaxRel": MAX_MARK_REL + EDGE_INSET_REL, "tileRel": TILE_REL,
                      "spacingRule": "centre spacing <= tileRel - markSideMaxRel so any along-edge interval of length <= markSideMaxRel lies inside one tile; perpendicular: farEdgeMaxRel <= tileRel",
                      "roundingTolerance": f"GT_COVERAGE >= {SCAN_COVERAGE_FLOOR} (pixel rounding may break exact containment by <= 1 px)"}


class NotFrozen(RuntimeError):
    pass


class CeilingInsufficient(RuntimeError):
    pass


def register_scan_variant(name: str, tile_rel: float) -> None:
    raise RuntimeError("EDGE_SCAN_PROPOSAL_V1 is a single frozen rule; no candidate search")


def downgrade_to_diagnostic(family: str) -> None:
    eg.downgrade_to_diagnostic(family)


def _tile_side(width: int, height: int) -> int:
    return int(round(TILE_REL * min(width, height)))


def edge_tile_centres(width: int, height: int, edge: str) -> list[float]:
    """Along-edge tile centres: first/last tiles flush with the edge endpoints, uniform spacing <= MAX_SPACING_REL x min(W, H)."""

    m = min(width, height)
    side = _tile_side(width, height)
    length = width if edge in ("TOP", "BOTTOM") else height
    if edge not in EDGES:
        raise ValueError(edge)
    span = length - side
    if span <= 0:
        return [length / 2]
    n = int(math.ceil(span / (MAX_SPACING_REL * m) - 1e-9)) + 1
    return [side / 2 + i * span / (n - 1) for i in range(n)]


def tile_count_per_edge(width: int, height: int) -> dict[str, int]:
    return {edge: len(edge_tile_centres(width, height, edge)) for edge in EDGES}


def scan_tiles(width: int, height: int) -> list[tuple[int, int, int, int]]:
    """Deterministic square tiles flush with each image edge; exact duplicate tiles (corners) removed. Uses image dimensions only."""

    side = _tile_side(width, height)
    out: list[tuple[int, int, int, int]] = []
    for edge in EDGES:
        for centre in edge_tile_centres(width, height, edge):
            start = int(round(centre - side / 2))
            if edge == "TOP":
                box = (start, 0, start + side, side)
            elif edge == "BOTTOM":
                box = (start, height - side, start + side, height)
            elif edge == "LEFT":
                box = (0, start, side, start + side)
            else:
                box = (width - side, start, width, start + side)
            if box not in out:
                out.append(box)
    return out


def gt_coverage(tile: Sequence[float], gt: Sequence[float]) -> float:
    left, top = max(tile[0], gt[0]), max(tile[1], gt[1])
    right, bottom = min(tile[2], gt[2]), min(tile[3], gt[3])
    inter = max(0.0, right - left) * max(0.0, bottom - top)
    area = (gt[2] - gt[0]) * (gt[3] - gt[1])
    return inter / area if area > 0 else 0.0


def scan_covered(tiles: Sequence[Sequence[float]], gt: Sequence[float]) -> bool:
    return max((gt_coverage(t, gt) for t in tiles), default=0.0) >= SCAN_COVERAGE_FLOOR


def scan_proposals(image_size: Sequence[int]) -> list[dict[str, Any]]:
    return [{"box": [float(v) for v in t], "source": SCAN_SOURCE} for t in scan_tiles(int(image_size[0]), int(image_size[1]))]


def runtime_proposals(detections_by_generator: Mapping[str, Sequence[Mapping[str, Any]]], image_size: Sequence[int]) -> list[dict[str, Any]]:
    """Frozen zero-shot union OR deterministic scan tiles; only exact duplicate boxes are removed (no NMS)."""

    out: list[dict[str, Any]] = []
    seen: set = set()
    for p in list(detector_proposals(detections_by_generator, image_size)) + scan_proposals(image_size):
        key = tuple(p["box"])
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


# ------------------------------------------------------------------ matching (two contracts, never mixed)


def proposal_matches(proposal: Mapping[str, Any], truth: Sequence[Mapping[str, Any]]) -> bool:
    if proposal.get("source") == SCAN_SOURCE:
        return any(gt_coverage(proposal["box"], t["box"]) >= SCAN_COVERAGE_FLOOR for t in truth)
    return any(bench.iou(proposal["box"], t["box"]) >= IOU_MATCH for t in truth)


def proposal_label(proposal: Mapping[str, Any], truth: Sequence[Mapping[str, Any]], *, clean_image: bool) -> str:
    """Evaluation authority only: clean image -> negative; matched -> positive; unmatched on a positive image -> excluded (scored, never trained on)."""

    if clean_image:
        return "negative"
    return "positive" if proposal_matches(proposal, truth) else "excluded"


# ------------------------------------------------------------------ verifier (B3-L13 recipe, exact)

VERIFIER = dict(pv.VERIFIER)
CROP = dict(pv.CROP)
CLASSIFIER = dict(pv.CLASSIFIER)
THRESHOLD_GRID = pv.THRESHOLD_GRID
NEUTRAL_THRESHOLD = pv.NEUTRAL_THRESHOLD
FOLDS = pv.FOLDS
DEVELOPMENT_GROUPS = sel.DEVELOPMENT_GROUPS
HOLDOUT_GROUPS = sel.HOLDOUT_GROUPS
FORBIDDEN_FEATURE_INPUTS = frozenset(pv.FORBIDDEN_FEATURE_INPUTS) | frozenset({"source", "proposalSource", "edge", "sizeBand", "geometry", "cell", "tileIndex", "knownMarkPosition", "humanLabel", "score", "bbox"})


def runtime_crop(box: Sequence[float], image_size: Sequence[int], **runtime_inputs: Any) -> tuple[int, int, int, int]:
    leaked = FORBIDDEN_FEATURE_INPUTS & set(runtime_inputs)
    if leaked:
        raise ValueError(f"not a runtime verifier input: {sorted(leaked)}")
    return pv.crop_box(box, image_size)


def feature_matrix(flat: Sequence[Mapping[str, Any]], include_source: bool = False):
    import numpy as np

    if include_source:
        raise ValueError("proposal source / detector identity is not a verifier feature")
    X = np.asarray([r["embedding"] for r in flat], dtype=float)
    return X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-12)


fit_classifier = pv.fit_classifier
score = pv.score
assert_group_disjoint = pv.assert_group_disjoint


def leakage_audit(flat: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out = {}
    for a, b, e in FOLDS:
        assert_group_disjoint((a, b), e, flat)
        out[f"{a}+{b}->{e}"] = {"trainBases": len({r["opaqueId"] for r in flat if r["groupKey"] in (a, b)}), "evalBases": len({r["opaqueId"] for r in flat if r["groupKey"] == e}),
                                "datasetsInEval": sorted({r.get("dataset", "?") for r in flat if r["groupKey"] == e}), "disjoint": True}
    return out


def oof_scores(flat: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """proposalId -> group out-of-fold score; excluded rows scored, never trained on."""

    out: dict[str, float] = {}
    for a, b, evaluate in FOLDS:
        assert_group_disjoint((a, b), evaluate, flat)
        train = [r for r in flat if r["groupKey"] in (a, b) and r["label"] in ("positive", "negative")]
        test = [r for r in flat if r["groupKey"] == evaluate]
        if not train or not test:
            continue
        clf = fit_classifier([r["embedding"] for r in train], [r["label"] for r in train])
        for r, s in zip(test, score(clf, [r["embedding"] for r in test])):
            out[r["proposalId"]] = s
    return out


def image_outcome(props: Sequence[Mapping[str, Any]], scores_by_id: Mapping[str, float], threshold: float, truth: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    survivors = [p for p in props if scores_by_id.get(p["proposalId"], -1.0) >= threshold]
    return {"survivors": len(survivors), "hit": any(proposal_matches(p, truth) for p in survivors), "response": len(survivors) > 0}


shadow_action = det.shadow_action    # review-only; never reject; never downgrade


def select_threshold(table: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    elig = [t for t in table if t.get("eligible") and t["threshold"] in THRESHOLD_GRID]
    if not elig:
        return {"status": "NONE", "threshold": None, "reason": "no verifier threshold satisfies the clean, broad and edge gates on OOF development"}
    best = sorted(elig, key=lambda t: (t["clean"]["newReviewRate"], -(t["minCriticalRecall"] or 0), -(t["broadOverall"] or 0), -(t["edgeOverall"] or 0), abs(t["threshold"] - NEUTRAL_THRESHOLD)))[0]
    return {"status": "SELECTED", "threshold": best["threshold"], "role": SELECTED_ROLE,
            "order": "lowest clean new-review -> highest min recall over broad families + edge cells -> highest broad overall -> highest edge overall -> closest to 0.50"}


# ------------------------------------------------------------------ digests / freeze markers / guards

SELECTED_MARKER_NAME = "edge_scan_verifier_v1_selected.json"
CEILING_MARKER_NAME = "edge_scan_verifier_v1_ceiling_passed.json"
STRESS_RESULT_NAME = "edge_scan_verifier_v1_stress_result.json"
L11_AUDIT_NAME = "edge_scan_verifier_v1_l11_holdout_audit.json"
FINAL_CLASSIFIER_NAME = "edge_scan_verifier_v1_final_classifier.json"


def scan_definitions() -> dict[str, Any]:
    return {"version": SCAN_VERSION, "source": SCAN_SOURCE, "tileRel": TILE_REL, "maxMarkRel": MAX_MARK_REL, "edgeInsetRel": EDGE_INSET_REL, "maxSpacingRel": MAX_SPACING_REL,
            "edges": list(EDGES), "coverageFloor": SCAN_COVERAGE_FLOOR, "placement": "outer tile side flush with the image boundary; first/last tiles flush with the edge endpoints; uniform centres",
            "dedup": "exact duplicate boxes only (corners); no NMS; no cross-source suppression", "runtimeInputs": ["width", "height"], "marker": SCAN_MARKER, "analyticGuarantee": ANALYTIC_GUARANTEE}


def scan_digest() -> str:
    return hashlib.sha256(json.dumps(scan_definitions(), sort_keys=True).encode("utf-8")).hexdigest()


def contract_digest() -> str:
    payload = {"version": VERSION, "scan": scan_digest(), "detectorSet": det.contract_digest(), "generators": PROPOSAL_GENERATORS, "thresholds": THRESHOLDS, "prompts": list(PROMPTS),
               "iouMatch": IOU_MATCH, "containment": CONTAINMENT_ADDED_TO_DETECTOR_MATCH, "verifier": VERIFIER, "crop": CROP, "classifier": CLASSIFIER, "thresholdGrid": list(THRESHOLD_GRID),
               "folds": [list(f) for f in FOLDS], "labels": {"positive": "detector IoU >= 0.30 or scan GT coverage >= 0.95", "negative": "every runtime proposal on a clean G1-G3 avatar",
                                                             "unmatchedOnPositiveImage": UNMATCHED_POSITIVE_IMAGE_PROPOSALS},
               "developmentDatasets": ["l11_dev (B3-L11 G1-G3 DEV_VARIANT + 12 clean)", "l14a_dev (B3-L14A G1-G3 EDGE_DEV_VARIANT)"], "stress": {"name": STRESS_NAME, "dataset": STRESS_DATASET},
               "holdout": "B3-L11 G4-G5 + HOLDOUT_VARIANT, one shot behind the canonical lock", "gates": {"cleanCeiling": NEW_REVIEW_CEILING, "overall": OVERALL_RECALL_FLOOR, "family": FAMILY_RECALL_FLOOR,
                                                                                                             "edge": "B3-L14A gate (each edge/size/geometry >= 0.90; cell 11/12 dev, 8/8 stress)", "holdoutClean": "0/8"},
               "selection": "lowest clean new-review -> highest min critical recall (broad + edge cells) -> highest broad overall -> highest edge overall -> closest to 0.50",
               "markers": [SCAN_MARKER, ZERO_SHOT_LIMIT, CRITICAL_MARKER, STRESS_NAME], "constructs": {"l11": c3.construct_digest(), "l14a": eg.construct_digest()},
               "forbiddenFeatureInputs": sorted(FORBIDDEN_FEATURE_INPUTS)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def require_ceiling(ceiling: Mapping[str, Any]) -> None:
    if not (ceiling.get("broad", {}).get("pass") and ceiling.get("edge", {}).get("gate", {}).get("pass")):
        raise CeilingInsufficient("EDGE_SCAN_PROPOSAL_CEILING_FAILED: the verifier cannot recover proposals that do not exist")


def write_ceiling_passed(private_dir: Path, digest: str, inputs_digest: str) -> Path:
    path = Path(private_dir) / CEILING_MARKER_NAME
    path.write_text(json.dumps({"version": VERSION, "contractDigest": digest, "ceilingInputsDigest": inputs_digest, "frozenAt": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    return path


def require_ceiling_passed(private_dir: Path, digest: str) -> Mapping[str, Any]:
    path = Path(private_dir) / CEILING_MARKER_NAME
    if not path.exists():
        raise NotFrozen("embeddings require the proposal-ceiling pass marker")
    r = json.loads(path.read_text(encoding="utf-8"))
    if r.get("contractDigest") != digest or r.get("version") != VERSION:
        raise NotFrozen("ceiling marker does not match the frozen contract")
    return r


def _frozen_record(threshold: float, digest: str, dev_digest: str) -> dict[str, Any]:
    return {"role": SELECTED_ROLE, "version": VERSION, "contractDigest": digest, "scanDigest": scan_digest(), "scan": scan_definitions(), "detectorSetDigest": det.contract_digest(),
            "generators": PROPOSAL_GENERATORS, "thresholds": THRESHOLDS, "prompts": list(PROMPTS), "iouMatch": IOU_MATCH, "scanCoverageFloor": SCAN_COVERAGE_FLOOR, "verifier": VERIFIER, "crop": CROP,
            "classifier": CLASSIFIER, "threshold": threshold, "thresholdGrid": list(THRESHOLD_GRID), "developmentInputsDigest": dev_digest, "frozenAt": datetime.now(timezone.utc).isoformat()}


def write_selected(private_dir: Path, threshold: float, digest: str, dev_digest: str) -> Path:
    path = Path(private_dir) / SELECTED_MARKER_NAME
    path.write_text(json.dumps(_frozen_record(threshold, digest, dev_digest), indent=2), encoding="utf-8")
    return path


def require_selected(private_dir: Path, digest: str) -> Mapping[str, Any]:
    path = Path(private_dir) / SELECTED_MARKER_NAME
    if not path.exists():
        raise NotFrozen("stress/holdout require the frozen selected verifier threshold")
    r = json.loads(path.read_text(encoding="utf-8"))
    expected = _frozen_record(r.get("threshold"), digest, r.get("developmentInputsDigest"))
    for k in ("role", "version", "contractDigest", "scanDigest", "scan", "detectorSetDigest", "generators", "thresholds", "prompts", "iouMatch", "scanCoverageFloor", "verifier", "crop", "classifier", "thresholdGrid"):
        if r.get(k) != expected[k]:
            raise NotFrozen(f"selected record differs from the frozen contract ({k}); retuning refused")
    if r.get("threshold") not in THRESHOLD_GRID:
        raise NotFrozen("selected threshold outside the frozen grid")
    return r


def write_stress_result(private_dir: Path, digest: str, *, passed: bool) -> Path:
    path = Path(private_dir) / STRESS_RESULT_NAME
    if path.exists():
        raise NotFrozen("the known-construct stress gate is evaluated once; no re-run after a result")
    require_selected(private_dir, digest)
    path.write_text(json.dumps({"name": STRESS_NAME, "dataset": STRESS_DATASET, "contractDigest": digest, "passed": bool(passed), "evaluatedAt": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    return path


def require_stress_passed(private_dir: Path, digest: str) -> Mapping[str, Any]:
    path = Path(private_dir) / STRESS_RESULT_NAME
    if not path.exists():
        raise NotFrozen("the original B3-L11 holdout requires the known-construct stress gate to have passed")
    r = json.loads(path.read_text(encoding="utf-8"))
    if r.get("contractDigest") != digest or r.get("passed") is not True:
        raise NotFrozen("stress gate not passed under this contract; the original B3-L11 holdout stays unopened")
    return r


def l11_holdout_unopened_audit(l11_dir: Path, private_dir: Optional[Path] = None) -> dict[str, Any]:
    p = Path(l11_dir)
    captures = {name: (p / f"capture_{name}_holdout.jsonl").exists() for name in PROPOSAL_GENERATORS}
    lock = (p / det.HOLDOUT_LOCK_NAME).exists()
    marker = (p / det.SELECTED_MARKER_NAME).exists() or (p / pv.SELECTED_MARKER_NAME).exists()
    embeddings = (Path(private_dir) / "edge_scan_embeddings_l11_holdout.jsonl").exists() if private_dir else False
    return {"captures": captures, "lockExists": lock, "selectedMarkerExists": marker, "verifierEmbeddingsExist": embeddings,
            "unopened": not any(captures.values()) and not lock and not marker and not embeddings}


def write_l11_union_marker(private_dir: Path, l11_dir: Path, digest: str) -> Path:
    """Union-form B3-L11 capture marker (lets the frozen B3-L11 capture script render G4-G5 + HOLDOUT_VARIANT); only after the stress pass and a clean unopened audit."""

    require_selected(private_dir, digest)
    require_stress_passed(private_dir, digest)
    audit = l11_holdout_unopened_audit(l11_dir, private_dir)
    if not audit["unopened"]:
        raise NotFrozen(f"original B3-L11 holdout is not unopened: {audit}")
    (Path(private_dir) / L11_AUDIT_NAME).write_text(json.dumps({"audit": audit, "contractDigest": digest, "auditedAt": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    path = Path(l11_dir) / det.SELECTED_MARKER_NAME
    path.write_text(json.dumps({"role": SELECTED_ROLE, "detector": "union", "detectors": list(PROPOSAL_GENERATORS), "contractDigest": det.contract_digest(), "constructDigest": c3.construct_digest(),
                                "edgeScanVerifierContractDigest": digest, "frozenAt": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    return path


def holdout_guard(private_dir: Path, l11_dir: Path, digest: str) -> Path:
    require_selected(private_dir, digest)
    require_stress_passed(private_dir, digest)
    lock = Path(l11_dir) / det.HOLDOUT_LOCK_NAME
    if lock.exists():
        raise sel.HoldoutAlreadyEvaluated(f"original B3-L11 holdout already evaluated once: {lock.name}")
    return lock


# ------------------------------------------------------------------ verdicts / interpretation


def verdict(ceiling_pass: Optional[bool], dev_selected: Optional[bool], stress_pass: Optional[bool], holdout_pass: Optional[bool]) -> str:
    if not ceiling_pass:
        return "EDGE_SCAN_PROPOSAL_CEILING_FAILED"
    if not dev_selected:
        return "EDGE_SCAN_VERIFIER_FAILED_DEVELOPMENT"
    if stress_pass is None:
        return "EDGE_SCAN_VERIFIER_DEVELOPMENT_PASSED_STRESS_PENDING"
    if not stress_pass:
        return "EDGE_SCAN_VERIFIER_KNOWN_CONSTRUCT_STRESS_FAILED"
    if holdout_pass is None:
        return "EDGE_SCAN_VERIFIER_KNOWN_CONSTRUCT_STRESS_PASSED"
    return "VISUAL_MARK_EDGE_SCAN_VERIFIER_CONTROLLED_GATE_PASSED" if holdout_pass else "VISUAL_MARK_EDGE_SCAN_VERIFIER_HOLDOUT_FAILED"


def support(passed: bool) -> str:
    return "VISUAL_MARK_EDGE_SCAN_VERIFIER_SUPPORTED_FOR_CONTROLLED_SHADOW_CANARY" if passed else "VISUAL_MARK_EDGE_SCAN_VERIFIER_NOT_SUPPORTED"


def diagnosis(table: Sequence[Mapping[str, Any]], ceiling: Optional[Mapping[str, Any]] = None) -> list[str]:
    out = set()
    if ceiling is not None and not (ceiling.get("broad", {}).get("pass") and ceiling.get("edge", {}).get("gate", {}).get("pass")):
        out.add("EDGE_SCAN_PROPOSAL_CEILING_FAILED")
    for t in table:
        c = t["criteria"]
        if not c["J1"]:
            out.add("EDGE_SCAN_CLEAN_BURDEN_TOO_HIGH")
        if c["J1"] and not t["edge"]["gate"]["pass"]:
            out.add("VERIFIER_REMOVES_TRUE_EDGE_MARKS")
        if c["J1"] and not all(c[k] for k in ("J2", "J3", "J4", "J5", "J6", "J7", "J8", "J9", "J10")):
            out.add("BROAD_MARK_RECALL_REGRESSION")
    if table and all(not t["criteria"]["J1"] for t in table) and any(t["clean"]["newReviewRate"] is not None and t["clean"]["newReviewRate"] > 0.5 for t in table):
        out.add("CONTENT_VERIFIER_NOT_SEPARATING")
    if table and all(not t["eligible"] for t in table) and any(not t["criteria"]["J1"] for t in table) and any(t["criteria"]["J1"] for t in table):
        out.add("SYNTHETIC_STYLE_NOT_SEPARATING")
    if len(out) > 1:
        out.add("MIXED")
    return sorted(out)


def interpretation_note() -> dict[str, Any]:
    return {"b3l13": "PROPOSAL_UNION_COVERAGE_INSUFFICIENT", "b3l14a": "EDGE_PROPOSAL_GENERALIZATION_HOLDOUT_FAILED", "priorFailuresReopened": False, "zeroShotReading": ZERO_SHOT_LIMIT,
            "note": "a pass is a new architecture passing a new hypothesis on synthetic marks; prior verdicts stand; NATURAL_POSITIVE_EVIDENCE_MISSING always"}


def stress_designation() -> dict[str, Any]:
    return {"name": STRESS_NAME, "dataset": STRESS_DATASET, "independentHoldout": False, "detectorOutputsPreviouslySeen": True, "verifierOutputsPreviouslySeen": False,
            "note": "B3-L14A G4-G5 EDGE_HOLDOUT_VARIANT was consumed at detector level in B3-L14A; only the CLIP verifier outputs are new"}
