"""B3-L12A — GDINO_BOX_GEOMETRY_FILTER_V1 (pre-registered; CLEAN_DEVELOPMENT_DESIGNED).

Grounding DINO tiny at the frozen historical operating point (box 0.25 /
text 0.25, four frozen queries, B3-L11 resize and IoU contract) produced a
detection on 12/12 human-negative development avatars.  This study asks
whether a narrow, runtime-available BOX GEOMETRY rule — normalized area and
aspect ratio only, computed from the detector box and the image size —
removes those responses without removing injected marks.  No score retune,
no query change, no label predicate ("a logo" is observation only), no
location rule that hard-codes where a mark may be (corner/torso/not-center/
not-edge are all safety-critical challenge placements).

The candidate set was designed after an aggregate inventory of the 12 clean
G1-G3 boxes and before any positive box geometry or filtered recall was
read: CLEAN_DEVELOPMENT_DESIGNED.  Clean development performance is
therefore not independent; the unopened B3-L11 holdout (G4-G5 +
HOLDOUT_VARIANT) is the only independent authority.

Band edges reuse the canonical watermark evidence constants
(TINY_REGION_AREA 0.03, SMALL_REGION_AREA 0.08) plus the B3-L11 full-frame
ratio 0.50 and a coarse object-scale edge 0.20; aspect caps are 4 and 3.  No
finer geometry search is permitted.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402
import avatar_visual_mark_eval as ev  # noqa: E402

VERSION = "GDINO_BOX_GEOMETRY_FILTER_V1"
CANDIDATE_SET_VERSION = "GDINO_GEOMETRY_CANDIDATES_V1"
DESIGNATION = "CLEAN_DEVELOPMENT_DESIGNED"
DETECTOR = "grounding-dino-tiny"
OPERATING_POINT_ID = "historical_0.25"
OPERATING_POINT = {"threshold": 0.25}          # box 0.25 / text 0.25 at capture; frozen
SELECTED_ROLE = "GDINO_GEOMETRY_FILTER_CONTROLLED_SHADOW_CANDIDATE"
OR_ENSEMBLE_MARKER = "FIXED_OR_ENSEMBLE_REJECTED_BY_DEVELOPMENT_DOMINANCE"
PRIOR_STATUS = {**ev.PRIOR_STATUS, "B3_L11": "VISUAL_MARK_DETECTOR_FAILED_DEVELOPMENT", "B3_L11_HOLDOUT_OPENED": False, "B3_L11_HOLDOUT_EXECUTIONS": 0}
ALLOWED_FEATURES = ("normalizedArea", "aspectRatio")
FORBIDDEN_PREDICATE_INPUTS = frozenset({"label", "text_label", "query", "prompt", "score", "family", "familyCode", "groundTruth", "groundTruthBox", "groundTruthBoxes",
                                        "groupKey", "participantGroup", "baseOpaqueId", "opaqueId", "filename", "path", "isClean", "markPresent", "ocr", "text", "uid"}) | frozenset(sel.HUMAN_ONLY_FIELDS)
ALLOWED_AREA_EDGES = (0.03, 0.08, 0.20, 0.50)      # canonical TINY / SMALL band edges, coarse object-scale edge, B3-L11 full-frame ratio
ALLOWED_ASPECT_CAPS = (3.0, 4.0)
EPSILON_SEARCH_MARKER = "FINE_GEOMETRY_SEARCH_PROHIBITED"


def box_geometry(box: Sequence[float], image_size: Sequence[int]) -> dict[str, float]:
    """Runtime-available geometry from the detector box alone (no label, score, truth or identity)."""

    x0, y0, x1, y1 = (float(v) for v in box)
    width, height = float(image_size[0]), float(image_size[1])
    w = max(x1 - x0, 0.0)
    h = max(y1 - y0, 0.0)
    return {"normalizedArea": (w * h) / (width * height) if width and height else 0.0, "aspectRatio": w / h if h > 0 else float("inf")}


@dataclass(frozen=True)
class Candidate:
    id: str
    rank: int                       # 1 = least aggressive
    max_area: float                 # boxes with normalizedArea >= max_area are dropped
    aspect_cap: Optional[float]     # boxes with aspect >= cap or <= 1/cap are dropped (None = no shape rule)

    def __post_init__(self) -> None:
        if self.max_area not in ALLOWED_AREA_EDGES or (self.aspect_cap is not None and self.aspect_cap not in ALLOWED_ASPECT_CAPS):
            raise ValueError(EPSILON_SEARCH_MARKER)

    @property
    def predicate(self) -> str:
        shape = f" AND 1/{self.aspect_cap:g} < aspectRatio < {self.aspect_cap:g}" if self.aspect_cap else ""
        return f"keep box iff normalizedArea < {self.max_area}{shape}"

    def keeps(self, geometry: Mapping[str, float]) -> bool:
        if geometry["normalizedArea"] >= self.max_area:
            return False
        if self.aspect_cap is not None:
            ar = geometry["aspectRatio"]
            if ar >= self.aspect_cap or ar <= 1.0 / self.aspect_cap:
                return False
        return True


CANDIDATES: tuple[Candidate, ...] = (
    Candidate("G1", 1, 0.50, None),   # drop full-frame-like boxes only
    Candidate("G2", 2, 0.20, 4.0),    # drop object-scale boxes and extreme strips
    Candidate("G3", 3, 0.08, 3.0),    # keep canonical small/medium-band boxes with moderate shape
    Candidate("G4", 4, 0.03, 3.0),    # keep canonical tiny-band boxes with moderate shape (most aggressive)
)
CANDIDATE_BY_ID = {c.id: c for c in CANDIDATES}
MAX_CANDIDATES = 4


def contract_digest() -> str:
    payload = {"version": VERSION, "candidateSet": CANDIDATE_SET_VERSION, "designation": DESIGNATION, "detector": DETECTOR,
               "detectorSpec": {k: v for k, v in det.CANDIDATES[DETECTOR].items() if k != "dir"}, "operatingPoint": OPERATING_POINT, "operatingPointId": OPERATING_POINT_ID,
               "candidates": [dict(asdict(c), predicate=c.predicate) for c in CANDIDATES], "allowedFeatures": list(ALLOWED_FEATURES),
               "forbiddenPredicateInputs": sorted(FORBIDDEN_PREDICATE_INPUTS), "iouMatch": det.IOU_MATCH, "maxLongSide": det.MAX_LONG_SIDE,
               "constructDigest": c3.construct_digest(), "detectorSetDigest": det.contract_digest(), "orEnsemble": OR_ENSEMBLE_MARKER,
               "selection": "highest min critical-family recall -> highest overall recall -> lowest new clean burden -> least aggressive rank"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ runtime filter


def _refuse(mapping: Mapping[str, Any]) -> None:
    leaked = FORBIDDEN_PREDICATE_INPUTS & set(mapping)
    if leaked:
        raise ValueError(f"not a geometry predicate input: {sorted(leaked)}")


def surviving(candidate: Candidate, detections: Sequence[Mapping[str, Any]], image_size: Sequence[int], **runtime_inputs: Any) -> list[Mapping[str, Any]]:
    """Frozen 0.25 operating point + query membership (B3-L11 contract) + the geometry predicate."""

    _refuse(runtime_inputs)
    kept = det.filter_detections(DETECTOR, detections, OPERATING_POINT, image_size)
    return [d for d in kept if candidate.keeps(box_geometry(d["box"], image_size))]


def image_hit(candidate: Candidate, detections: Sequence[Mapping[str, Any]], truth: Sequence[Mapping[str, Any]], image_size: Sequence[int]) -> dict[str, Any]:
    survivors = surviving(candidate, detections, image_size)
    ious = [max((ev.bench.iou(d["box"], t["box"]) for d in survivors), default=0.0) for t in truth]
    hits = sum(1 for v in ious if v >= det.IOU_MATCH)
    return {"hit": hits > 0, "boxHits": hits, "boxes": len(truth), "bestIou": max(ious, default=0.0), "detections": len(survivors)}


def clean_response(candidate: Candidate, detections: Sequence[Mapping[str, Any]], image_size: Sequence[int]) -> bool:
    return len(surviving(candidate, detections, image_size)) > 0


shadow_action = det.shadow_action   # review-only: max(canonical, review); never reject, never downgrade


# ------------------------------------------------------------------ OR-ensemble structural rejection


def or_ensemble_min_clean_response(*component_new_review_counts: int) -> int:
    """An OR over detectors cannot respond on fewer clean images than its most responsive component."""

    return max(component_new_review_counts) if component_new_review_counts else 0


# ------------------------------------------------------------------ freeze / holdout guards


class NotFrozen(RuntimeError):
    pass


class BlindingViolation(RuntimeError):
    pass


def write_selected(private_dir: Path, candidate: Candidate, digest: str, dev_digest: str) -> Path:
    """Writes the B3-L11 selected-marker format (the holdout capture script validates detector + both digests) plus the geometry rule."""

    spec = det.CANDIDATES[DETECTOR]
    path = Path(private_dir) / det.SELECTED_MARKER_NAME
    path.write_text(json.dumps({"role": SELECTED_ROLE, "detector": DETECTOR, "repo": spec["repo"], "revision": spec["revision"], "license": spec["license"],
                                "prompts": spec["prompts"], "operatingPoint": OPERATING_POINT_ID, "params": OPERATING_POINT, "maxLongSide": det.MAX_LONG_SIDE,
                                "iouMatch": det.IOU_MATCH, "contractDigest": det.contract_digest(), "constructDigest": c3.construct_digest(),
                                "geometryFilterVersion": VERSION, "geometryCandidate": candidate.id, "geometryPredicate": candidate.predicate,
                                "geometryContractDigest": digest, "developmentInputsDigest": dev_digest, "frozenAt": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    return path


def require_selected(private_dir: Path, digest: str) -> Mapping[str, Any]:
    path = Path(private_dir) / det.SELECTED_MARKER_NAME
    if not path.exists():
        raise NotFrozen("holdout requires a frozen selected geometry filter")
    record = json.loads(path.read_text(encoding="utf-8"))
    if (record.get("geometryContractDigest") != digest or record.get("detector") != DETECTOR or record.get("geometryCandidate") not in CANDIDATE_BY_ID
            or record.get("contractDigest") != det.contract_digest() or record.get("constructDigest") != c3.construct_digest() or record.get("params") != OPERATING_POINT):
        raise NotFrozen("selected record does not match the frozen contracts (retuning refused)")
    return record


def holdout_unopened_audit(private_dir: Path) -> dict[str, Any]:
    p = Path(private_dir)
    audit = {"holdoutCaptureExists": (p / f"capture_{DETECTOR}_holdout.jsonl").exists(),
             "anyHoldoutCaptureExists": any(p.glob("capture_*_holdout.jsonl")),
             "lockExists": (p / det.HOLDOUT_LOCK_NAME).exists(),
             "selectedMarkerExists": (p / det.SELECTED_MARKER_NAME).exists()}
    audit["unopened"] = not audit["anyHoldoutCaptureExists"] and not audit["lockExists"]
    return audit


def holdout_guard(private_dir: Path, digest: str) -> Path:
    require_selected(private_dir, digest)
    lock = Path(private_dir) / det.HOLDOUT_LOCK_NAME
    if lock.exists():
        raise sel.HoldoutAlreadyEvaluated(f"detector holdout already evaluated once: {lock.name}")
    return lock


def verdict(dev_selected: bool, holdout_pass: Optional[bool]) -> dict[str, str]:
    if not dev_selected:
        return {"verdict": "GDINO_GEOMETRY_FILTER_FAILED_DEVELOPMENT", "support": "GDINO_GEOMETRY_FILTER_NOT_SUPPORTED"}
    if holdout_pass is None:
        return {"verdict": "GDINO_GEOMETRY_FILTER_DEVELOPMENT_ELIGIBLE_HOLDOUT_PENDING", "support": "GDINO_GEOMETRY_FILTER_NOT_SUPPORTED"}
    if holdout_pass:
        return {"verdict": "GDINO_GEOMETRY_FILTER_CONTROLLED_GATE_PASSED", "support": "GDINO_GEOMETRY_FILTER_SUPPORTED_FOR_CONTROLLED_SHADOW_CANARY"}
    return {"verdict": "GDINO_GEOMETRY_FILTER_HOLDOUT_FAILED", "support": "GDINO_GEOMETRY_FILTER_NOT_SUPPORTED"}


def diagnosis(table: Sequence[Mapping[str, Any]]) -> list[str]:
    """Development-failure diagnosis from the candidate table (aggregate)."""

    out = set()
    for t in table:
        c = t["criteria"]
        if not c["A"]:
            out.add("CLEAN_GEOMETRY_NOT_SEPARATING")
        if c["A"] and not all(c[k] for k in ("B", "C", "D", "E", "F", "G", "H", "I", "J")):
            out.add("POSITIVE_GEOMETRY_COLLISION")
        if not c["I"]:
            out.add("EDGE_FAMILY_STILL_UNDERDETECTED")
        if not c["F"]:
            out.add("GRAPHICAL_WATERMARK_STILL_UNDERDETECTED")
    if len(out) > 1:
        out.add("MIXED")
    return sorted(out)
