"""B3-L14A — EDGE_MARK_GENERALIZATION_V1 (pre-registered, decision-neutral research).

Question: do the FROZEN B3-L13 proposal generators (OWLv2 0.25, Grounding DINO
0.25/0.25, Florence-2 phrase grounding presence; four frozen queries; IoU >=
0.30, no containment) give a sufficient proposal ceiling on NEW synthetic edge
marks?  Axes: edge side (TOP / BOTTOM / LEFT / RIGHT) x size band (small /
medium, reused from B3-L11) x synthetic geometry (two DEV, two distinct
HOLDOUT); alpha OPAQUE only.  This construct was frozen BEFORE any box-level
audit of the two B3-L13 EDGE_MARK misses so that the new challenge is not
designed around them.

Immutable: B3-L13 = PROPOSAL_UNION_COVERAGE_INSUFFICIENT (union 164/168,
EDGE_MARK 10/12, verifier NOT STARTED, holdout NOT OPENED).  A pass here is
evidence for a NEW hypothesis and never reopens B3-L13.

EDGE_MARK_REMAINS_CRITICAL_FAMILY: EDGE_MARK is never downgraded to a
diagnostic family; 10/12 is a failure.  VERIFIER_STAGE_PROHIBITED_IN_B3_L14A:
no crop embedding, no classifier fit, no verifier threshold.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_florence_ceiling as bench  # noqa: E402
import avatar_owlv2_challenge_v2 as v2  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_proposal_verifier as pv  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402
import avatar_visual_mark_eval as ev  # noqa: E402

VERSION = "EDGE_MARK_GENERALIZATION_V1"
GENERATOR_VERSION = "avatar_edge_mark_generalization_generator_v1"
CRITICAL_MARKER = "EDGE_MARK_REMAINS_CRITICAL_FAMILY"
VERIFIER_PROHIBITED = "VERIFIER_STAGE_PROHIBITED_IN_B3_L14A"
EDGE_DIAGNOSTIC_ALLOWED = False
EXPECTED_VERIFIER_EMBEDDINGS = 0
EXPECTED_CLASSIFIER_FITS = 0
PRIOR_STATUS = {**pv.PRIOR_STATUS, "B3_L13": "PROPOSAL_UNION_COVERAGE_INSUFFICIENT", "B3_L13_UNION_OVERALL": "164/168", "B3_L13_EDGE_MARK": "10/12",
                "B3_L13_VERIFIER": "NOT_STARTED", "B3_L13_HOLDOUT": "NOT_OPENED", "TEXT_POLICY_GAP": "unresolved",
                "GRAPHICAL_DETECTOR": "GRAPHICAL_DETECTOR_STUDY_REQUIRED", "NATURAL_POSITIVE": "NATURAL_POSITIVE_EVIDENCE_MISSING"}
NO_RETUNE = ("threshold", "prompt", "geometry", "size", "inset", "matching", "detector set")

# ------------------------------------------------------------------ frozen generators (B3-L13 exact; nothing retuned)

PROPOSAL_GENERATORS = dict(pv.PROPOSAL_GENERATORS)          # owlv2 legacy_0.25 / gdino historical_0.25 / florence presence
PROMPTS = det.PROMPTS                                        # ("a logo", "a watermark", "a brand emblem", "a graphic symbol")
THRESHOLDS = {"owlv2-base-patch16-ensemble": 0.25, "grounding-dino-tiny": {"box": 0.25, "text": 0.25}, "florence2-phrase-grounding": "presence"}
DETECTOR_SET_DIGEST_PREFIX = "086a32a65e05"
IOU_MATCH = pv.IOU_MATCH                                     # 0.30 canonical
CONTAINMENT_CLAUSE = False                                   # B3-L13 had none; none added
union_proposals = pv.union_proposals
union_hit = pv.coverage_hit


def _verify_frozen_generators() -> None:
    if det.contract_digest()[:12] != DETECTOR_SET_DIGEST_PREFIX:
        raise RuntimeError("detector set changed: B3-L14A requires the frozen DETECTOR_CANDIDATE_SET_V1")
    if det.CANDIDATES["owlv2-base-patch16-ensemble"]["operatingPoints"]["legacy_0.25"]["threshold"] != THRESHOLDS["owlv2-base-patch16-ensemble"]:
        raise RuntimeError("owlv2 threshold changed")
    if det.CANDIDATES["grounding-dino-tiny"]["operatingPoints"]["historical_0.25"]["threshold"] != THRESHOLDS["grounding-dino-tiny"]["box"]:
        raise RuntimeError("grounding-dino threshold changed")
    if tuple(det.PROMPTS) != ("a logo", "a watermark", "a brand emblem", "a graphic symbol"):
        raise RuntimeError("prompts changed")
    if IOU_MATCH != 0.30:
        raise RuntimeError("IoU rule changed")


_verify_frozen_generators()

# ------------------------------------------------------------------ construct axes (frozen)

DEV_VARIANT = "EDGE_DEV_VARIANT"
HOLDOUT_VARIANT = "EDGE_HOLDOUT_VARIANT"
DEVELOPMENT_GROUPS = sel.DEVELOPMENT_GROUPS                  # G1-G3
HOLDOUT_GROUPS = sel.HOLDOUT_GROUPS                          # G4-G5
HOLDOUT_NAME = "EDGE_CONSTRUCT_SPECIFIC_FROZEN_HOLDOUT"      # bases reused by earlier studies: never "globally unseen"
EXPECTED_BASES = {"development": 12, "holdout": 8}
EDGES = ("TOP", "BOTTOM", "LEFT", "RIGHT")                   # corners excluded (SMALL_CORNER_MARK is a different family)
SIZE_BANDS = dict(c3.SIZE_BANDS)                             # {"small": 0.035, "medium": 0.07} — B3-L11 canonical, reused, no intermediate search
ALPHA_NAME = "OPAQUE"
ALPHA = c3.ALPHAS[ALPHA_NAME]                                # 1.00 only: transparency is not mixed into the edge question
INSET = {"relative": 0.02, "basis": "min(W, H)", "rule": "square mark box of side round(size x min(W,H)); its outer side sits round(0.02 x min(W,H)) px inside the touching image edge; centred at 0.50 along that edge"}
DEV_GEOMETRIES = ("open_hexagon_emblem", "paired_chevron_emblem")
HOLDOUT_GEOMETRIES = ("broken_ring_emblem", "offset_bar_emblem")
GEOMETRY_DESCRIPTIONS = {
    "open_hexagon_emblem": "hexagon outline with one side omitted (open), thick stroke, filled centre dot",
    "paired_chevron_emblem": "two stacked filled chevrons (V shapes) in two contrasting colours",
    "broken_ring_emblem": "ring arc with a 60-degree gap, thick stroke, small filled square at the centre",
    "offset_bar_emblem": "two horizontal filled bars offset diagonally with a filled disc between them",
}
TRADEMARK_BLOCKLIST = tuple(v2.REAL_TRADEMARK_BLOCKLIST) + tuple(c3.EXTRA_TRADEMARK_BLOCKLIST)

# gate (reuses the B3-L11 floors; no new number)
OVERALL_FLOOR = ev.OVERALL_RECALL_FLOOR                      # 0.95
AXIS_FLOOR = ev.FAMILY_RECALL_FLOOR                          # 0.90 per edge / size / geometry / cell
GATE_AXES = {"B": ("edge", "TOP"), "C": ("edge", "BOTTOM"), "D": ("edge", "LEFT"), "E": ("edge", "RIGHT"), "F": ("size", "small"), "G": ("size", "medium")}
SENSITIVITY_MARKERS = ("EDGE_PLACEMENT_SENSITIVE", "EDGE_SIZE_SENSITIVE", "EDGE_GEOMETRY_SENSITIVE", "EDGE_ZERO_SHOT_GENERALIZATION_LIMIT", "MIXED")
DECOMPOSITION_CATEGORIES = ("NO_RELEVANT_PROPOSAL", "PROPOSAL_WRONG_LABEL_ONLY", "LOCALIZATION_MISS_IOU_BELOW_030", "FULL_FRAME_FILTER_EFFECT", "OTHER")

CONSTRUCT_FROZEN_MARKER_NAME = "edge_proposal_generalization_v1_construct_frozen.json"
DEV_PASS_MARKER_NAME = "edge_proposal_generalization_v1_dev_passed.json"
HOLDOUT_LOCK_NAME = "edge_proposal_generalization_v1_holdout.lock"


class NotFrozen(RuntimeError):
    pass


class DowngradeProhibited(RuntimeError):
    pass


class VerifierProhibited(RuntimeError):
    pass


def downgrade_to_diagnostic(family: str) -> None:
    raise DowngradeProhibited(f"{CRITICAL_MARKER}: {family} cannot be treated as a diagnostic family (10/12 is a failure)")


def verifier_prohibited() -> None:
    raise VerifierProhibited(f"{VERIFIER_PROHIBITED}: no embedding, no classifier fit, no verifier threshold in B3-L14A")


def no_real_trademark_geometry(name: str) -> bool:
    lowered = name.lower()
    return not any(token in lowered for token in TRADEMARK_BLOCKLIST)


def register_geometry(name: str, drawer: Callable) -> None:
    raise RuntimeError("EDGE_MARK_GENERALIZATION_V1 geometries are frozen; none may be added after inference")


# ------------------------------------------------------------------ conditions


@dataclass(frozen=True)
class EdgeCondition:
    edge: str
    size_band: str
    geometry: str
    variant: str

    @property
    def rel_size(self) -> float:
        return SIZE_BANDS[self.size_band]

    @property
    def alpha(self) -> float:
        return ALPHA

    @property
    def code(self) -> str:
        return f"E:{self.edge}:{self.size_band}:{self.geometry}:{'D' if self.variant == DEV_VARIANT else 'H'}"

    @property
    def cell(self) -> str:
        return f"{self.edge}|{self.size_band}|{self.geometry}"


def _geometries(variant: str) -> tuple[str, ...]:
    if variant == DEV_VARIANT:
        return DEV_GEOMETRIES
    if variant == HOLDOUT_VARIANT:
        return HOLDOUT_GEOMETRIES
    raise ValueError(variant)


def conditions(variant: str) -> list[EdgeCondition]:
    out = []
    for geometry in _geometries(variant):
        if not no_real_trademark_geometry(geometry) or geometry not in GEOMETRY_DESCRIPTIONS:
            raise ValueError(f"unknown or trademark-like geometry {geometry}")
        for edge in EDGES:
            for size in SIZE_BANDS:
                out.append(EdgeCondition(edge, size, geometry, variant))
    return out


def cell_ids(variant: str) -> list[str]:
    return [c.cell for c in conditions(variant)]


def expected_counts(dev_bases: int, holdout_bases: int) -> dict[str, Any]:
    per_base = len(EDGES) * len(SIZE_BANDS) * len(DEV_GEOMETRIES)
    return {"conditionsPerBase": per_base, "developmentPositives": per_base * dev_bases, "holdoutPositives": per_base * holdout_bases,
            "cellN": {"development": dev_bases, "holdout": holdout_bases},
            "edgeN": {"development": dev_bases * len(SIZE_BANDS) * len(DEV_GEOMETRIES), "holdout": holdout_bases * len(SIZE_BANDS) * len(HOLDOUT_GEOMETRIES)},
            "sizeN": {"development": dev_bases * len(EDGES) * len(DEV_GEOMETRIES), "holdout": holdout_bases * len(EDGES) * len(HOLDOUT_GEOMETRIES)},
            "geometryN": {"development": dev_bases * len(EDGES) * len(SIZE_BANDS), "holdout": holdout_bases * len(EDGES) * len(SIZE_BANDS)}}


# ------------------------------------------------------------------ placement + rendering (deterministic; base never mutated)


def edge_box(width: int, height: int, edge: str, size: int) -> tuple[int, int, int, int]:
    inset = int(round(INSET["relative"] * min(width, height)))
    if edge == "TOP":
        left, top = int(round(width / 2 - size / 2)), inset
    elif edge == "BOTTOM":
        left, top = int(round(width / 2 - size / 2)), height - inset - size
    elif edge == "LEFT":
        left, top = inset, int(round(height / 2 - size / 2))
    elif edge == "RIGHT":
        left, top = width - inset - size, int(round(height / 2 - size / 2))
    else:
        raise ValueError(f"not an edge side: {edge}")
    return (left, top, left + size, top + size)


def _draw_geometry(name: str, draw: ImageDraw.ImageDraw, box, alpha: int) -> None:
    left, top, right, bottom = box
    w, h = right - left, bottom - top
    cx, cy = (left + right) / 2, (top + bottom) / 2
    stroke = max(2, w // 8)
    if name == "open_hexagon_emblem":
        pts = [(cx + w / 2 * math.cos(math.pi / 3 * i - math.pi / 6), cy + h / 2 * math.sin(math.pi / 3 * i - math.pi / 6)) for i in range(6)]
        for i in range(5):                                            # sixth side omitted -> open hexagon
            draw.line([pts[i], pts[i + 1]], fill=(255, 255, 255, alpha), width=stroke)
        draw.ellipse((cx - w * 0.12, cy - h * 0.12, cx + w * 0.12, cy + h * 0.12), fill=(255, 140, 40, alpha))
    elif name == "paired_chevron_emblem":
        draw.polygon([(left, top + h * 0.1), (cx, top + h * 0.45), (right, top + h * 0.1), (right, top + h * 0.3), (cx, top + h * 0.65), (left, top + h * 0.3)], fill=(240, 240, 240, alpha))
        draw.polygon([(left, top + h * 0.45), (cx, top + h * 0.8), (right, top + h * 0.45), (right, top + h * 0.65), (cx, bottom), (left, top + h * 0.65)], fill=(60, 160, 220, alpha))
    elif name == "broken_ring_emblem":
        draw.arc(box, start=30, end=330, fill=(255, 255, 255, alpha), width=stroke)   # 60-degree gap
        draw.rectangle((cx - w * 0.12, cy - h * 0.12, cx + w * 0.12, cy + h * 0.12), fill=(230, 60, 90, alpha))
    elif name == "offset_bar_emblem":
        draw.rectangle((left, top, left + w * 0.7, top + h * 0.22), fill=(250, 220, 60, alpha))
        draw.rectangle((left + w * 0.3, bottom - h * 0.22, right, bottom), fill=(40, 40, 60, alpha))
        draw.ellipse((cx - w * 0.16, cy - h * 0.16, cx + w * 0.16, cy + h * 0.16), fill=(255, 255, 255, alpha))
    else:
        raise ValueError(name)


def render(base: Image.Image, cond: EdgeCondition) -> tuple[Image.Image, list[dict[str, Any]]]:
    """Deterministic derivative + ground-truth box (pixel xyxy). Never mutates base."""

    if not no_real_trademark_geometry(cond.geometry) or cond.geometry not in GEOMETRY_DESCRIPTIONS:
        raise ValueError(f"unknown or trademark-like geometry {cond.geometry}")
    image = base.convert("RGB")
    width, height = image.size
    size = int(round(cond.rel_size * min(width, height)))
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    box = edge_box(width, height, cond.edge, size)
    _draw_geometry(cond.geometry, ImageDraw.Draw(layer), box, int(round(255 * cond.alpha)))
    out = Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")
    return out, [{"box": [float(v) for v in box], "text": None}]


def image_digest(image: Image.Image) -> str:
    return hashlib.sha256(image.tobytes()).hexdigest()


def manifest_row(cond: EdgeCondition, base_opaque_id: str, group_key: Optional[str], boxes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"constructVersion": VERSION, "conditionId": f"{base_opaque_id}:{cond.code}", "baseOpaqueId": base_opaque_id, "participantGroup": group_key, "family": "EDGE_MARK",
            "edge": cond.edge, "sizeBand": cond.size_band, "relativeSize": cond.rel_size, "geometry": cond.geometry, "variant": cond.variant, "alphaName": ALPHA_NAME, "alpha": cond.alpha,
            "cell": cond.cell, "markPresent": True, "critical": True, "diagnostic": False, "groundTruthBoxes": [list(b["box"]) for b in boxes]}


def definitions() -> dict[str, Any]:
    return {"version": VERSION, "generatorVersion": GENERATOR_VERSION, "criticalMarker": CRITICAL_MARKER, "edges": list(EDGES), "sizeBands": SIZE_BANDS, "alpha": {ALPHA_NAME: ALPHA},
            "inset": INSET, "devGeometries": list(DEV_GEOMETRIES), "holdoutGeometries": list(HOLDOUT_GEOMETRIES), "geometryDescriptions": GEOMETRY_DESCRIPTIONS,
            "conditionsPerBase": len(conditions(DEV_VARIANT)), "split": {"development": list(DEVELOPMENT_GROUPS), "holdout": list(HOLDOUT_GROUPS)},
            "holdout": {"name": HOLDOUT_NAME, "globallyUnseen": False, "unseenBeforePerformance": ["holdout geometries", "holdout derivatives", "holdout detector outputs"]},
            "trademarkBlocklist": list(TRADEMARK_BLOCKLIST)}


def construct_digest() -> str:
    return hashlib.sha256(json.dumps(definitions(), sort_keys=True).encode("utf-8")).hexdigest()


def contract_digest() -> str:
    payload = {"version": VERSION, "construct": construct_digest(), "detectorSet": det.contract_digest(), "generators": PROPOSAL_GENERATORS, "thresholds": THRESHOLDS,
               "prompts": list(PROMPTS), "iouMatch": IOU_MATCH, "containmentClause": CONTAINMENT_CLAUSE, "overallFloor": OVERALL_FLOOR, "axisFloor": AXIS_FLOOR,
               "gateAxes": {k: list(v) for k, v in GATE_AXES.items()}, "expectedBases": EXPECTED_BASES, "expected": expected_counts(EXPECTED_BASES["development"], EXPECTED_BASES["holdout"]),
               "markers": [CRITICAL_MARKER, VERIFIER_PROHIBITED], "sensitivityMarkers": list(SENSITIVITY_MARKERS), "decompositionCategories": list(DECOMPOSITION_CATEGORIES),
               "noRetune": list(NO_RETUNE), "verifierEmbeddings": EXPECTED_VERIFIER_EMBEDDINGS, "classifierFits": EXPECTED_CLASSIFIER_FITS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ gate arithmetic


def required(n: int, floor: float = AXIS_FLOOR) -> int:
    return ev.required_hits(n, floor)


def _rate(k: int, n: int) -> Optional[float]:
    return round(k / n, 4) if n else None


def _table(hits: Sequence[bool]) -> dict[str, Any]:
    return {"k": sum(1 for h in hits if h), "n": len(hits), "rate": _rate(sum(1 for h in hits if h), len(hits))}


def tables_from_hits(cell_hits: Mapping[str, Sequence[bool]], variant: str) -> dict[str, Any]:
    """cell_hits: cell id -> per-base hit list. Builds overall / edge / size / geometry / cell tables."""

    edges: dict[str, list] = {e: [] for e in EDGES}
    sizes: dict[str, list] = {s: [] for s in SIZE_BANDS}
    geoms: dict[str, list] = {g: [] for g in _geometries(variant)}
    overall: list = []
    cells: dict[str, Any] = {}
    for cond in conditions(variant):
        hits = list(cell_hits.get(cond.cell, []))
        cells[cond.cell] = {**_table(hits), "required": required(len(hits))}
        edges[cond.edge].extend(hits); sizes[cond.size_band].extend(hits); geoms[cond.geometry].extend(hits); overall.extend(hits)
    return {"overall": _table(overall), "edges": {k: _table(v) for k, v in edges.items()}, "sizes": {k: _table(v) for k, v in sizes.items()},
            "geometries": {k: _table(v) for k, v in geoms.items()}, "cells": cells}


def _meets(t: Mapping[str, Any], floor: float) -> bool:
    return t["n"] > 0 and t["k"] >= required(t["n"], floor)


def gate(tables: Mapping[str, Any], variant: str) -> dict[str, Any]:
    geoms = _geometries(variant)
    checks = {"A": _meets(tables["overall"], OVERALL_FLOOR)}
    for key, (axis, value) in GATE_AXES.items():
        checks[key] = _meets(tables["edges" if axis == "edge" else "sizes"][value], AXIS_FLOOR)
    checks["H"] = _meets(tables["geometries"][geoms[0]], AXIS_FLOOR)
    checks["I"] = _meets(tables["geometries"][geoms[1]], AXIS_FLOOR)
    for cell in cell_ids(variant):
        checks[f"J:{cell}"] = _meets(tables["cells"][cell], AXIS_FLOOR)
    return {"criteria": checks, "pass": all(checks.values()), "failed": [k for k, v in checks.items() if not v],
            "required": {"overall": required(tables["overall"]["n"], OVERALL_FLOOR), "edge": {e: required(tables["edges"][e]["n"]) for e in EDGES},
                         "size": {s: required(tables["sizes"][s]["n"]) for s in SIZE_BANDS}, "geometry": {g: required(tables["geometries"][g]["n"]) for g in geoms},
                         "cell": {c: required(tables["cells"][c]["n"]) for c in cell_ids(variant)}}}


# ------------------------------------------------------------------ interpretation (pre-registered)


def sensitivity_markers(result: Mapping[str, Any]) -> list[str]:
    c = result["criteria"]
    if result.get("pass", all(c.values())):
        return []
    edges = [c["B"], c["C"], c["D"], c["E"]]
    sizes = [c["F"], c["G"]]
    geoms = [c["H"], c["I"]]
    out = []
    if any(not e for e in edges) and any(edges):
        out.append("EDGE_PLACEMENT_SENSITIVE")
    if sizes[0] != sizes[1]:
        out.append("EDGE_SIZE_SENSITIVE")
    if geoms[0] != geoms[1]:
        out.append("EDGE_GEOMETRY_SENSITIVE")
    if not out or not any(edges) or not any(sizes) or not any(geoms):
        out.append("EDGE_ZERO_SHOT_GENERALIZATION_LIMIT")
    if len(out) > 1:
        out.append("MIXED")
    return out


def verdict(dev_pass: Optional[bool], holdout_pass: Optional[bool]) -> str:
    if not dev_pass:
        return "EDGE_PROPOSAL_GENERALIZATION_FAILED_DEVELOPMENT"
    if holdout_pass is None:
        return "EDGE_PROPOSAL_GENERALIZATION_DEVELOPMENT_PASSED"
    return "EDGE_PROPOSAL_GENERALIZATION_HOLDOUT_PASSED" if holdout_pass else "EDGE_PROPOSAL_GENERALIZATION_HOLDOUT_FAILED"


def interpretation(dev_pass: Optional[bool], holdout_pass: Optional[bool], markers: Sequence[str] = ()) -> dict[str, Any]:
    if dev_pass and holdout_pass:
        status = "EDGE_PROPOSAL_GAP_NOT_REPLICATED_ON_NEW_CONSTRUCTS"
    elif dev_pass and holdout_pass is None:
        status = "HOLDOUT_PENDING"
    else:
        status = "EDGE_PROPOSAL_GAP_REPLICATED"
    return {"status": status, "markers": list(markers), "b3l13": "PROPOSAL_UNION_COVERAGE_INSUFFICIENT", "b3l13Reopened": False, "b3l13EdgeMark": "10/12 (unresolved misses on the original construct)",
            "b3l13VerifierContinuationAllowed": False, "criticalMarker": CRITICAL_MARKER,
            "note": "a pass is evidence for a new hypothesis on new edge constructs only; the B3-L13 failure on its construct stands; any continuation needs a new owner-approved hypothesis"}


# ------------------------------------------------------------------ old-miss decomposition (descriptive; frozen categories)


def classify_miss(name: str, detections: Sequence[Mapping[str, Any]], truth: Sequence[Mapping[str, Any]], image_size: Sequence[int]) -> str:
    """Category for one (missed image, detector) pair from its stored low-floor capture. Raises if the detector actually hit at its frozen operating point."""

    spec = det.CANDIDATES[name]
    op = spec["operatingPoints"][PROPOSAL_GENERATORS[name]]
    kept = det.filter_detections(name, detections, op, image_size)
    if any(bench.iou(d["box"], t["box"]) >= IOU_MATCH for d in kept for t in truth):
        raise ValueError("not a miss at the frozen operating point")
    area = float(image_size[0]) * float(image_size[1])
    raw_matches = [d for d in detections if any(bench.iou(d["box"], t["box"]) >= IOU_MATCH for t in truth)]
    if spec["boxFilter"] and any(((d["box"][2] - d["box"][0]) * (d["box"][3] - d["box"][1])) / area >= spec["boxFilter"]["dropFullFrameAreaRatio"]
                                 and det._label_is_query(spec, str(d.get("label", ""))) for d in detections):
        # a full-frame box was dropped by the filter; it cannot match a small mark (so the category is diagnostic only)
        return "FULL_FRAME_FILTER_EFFECT"
    if raw_matches:
        if any(not det._label_is_query(spec, str(d.get("label", ""))) for d in raw_matches) and not any(det._label_is_query(spec, str(d.get("label", ""))) for d in raw_matches):
            return "PROPOSAL_WRONG_LABEL_ONLY"
        return "OTHER"          # query-labelled matching box exists at the capture floor but below the frozen operating point (reported, never used to retune)
    if any(0.0 < bench.iou(d["box"], t["box"]) < IOU_MATCH for d in kept for t in truth):
        return "LOCALIZATION_MISS_IOU_BELOW_030"
    return "NO_RELEVANT_PROPOSAL"


def iou_band(value: float) -> str:
    if value <= 0.0:
        return "0"
    if value < 0.10:
        return "(0,0.10)"
    if value < 0.20:
        return "[0.10,0.20)"
    if value < IOU_MATCH:
        return "[0.20,0.30)"
    return ">=0.30"


# ------------------------------------------------------------------ freeze markers / holdout guards


def write_construct_frozen(private_dir: Path, digest: str, commit: str) -> Path:
    path = Path(private_dir) / CONSTRUCT_FROZEN_MARKER_NAME
    path.write_text(json.dumps({"version": VERSION, "contractDigest": digest, "constructDigest": construct_digest(), "freezeCommit": commit, "frozenAt": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    return path


def require_construct_frozen(private_dir: Path, digest: str) -> Mapping[str, Any]:
    path = Path(private_dir) / CONSTRUCT_FROZEN_MARKER_NAME
    if not path.exists():
        raise NotFrozen("the EDGE_MARK_GENERALIZATION_V1 construct must be frozen (committed) before any box-level audit of the B3-L13 misses")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("contractDigest") != digest or record.get("constructDigest") != construct_digest() or record.get("version") != VERSION or not record.get("freezeCommit"):
        raise NotFrozen("construct freeze record does not match the current contract")
    return record


def write_dev_passed(private_dir: Path, digest: str, dev_digest: str) -> Path:
    path = Path(private_dir) / DEV_PASS_MARKER_NAME
    path.write_text(json.dumps({"role": "EDGE_PROPOSAL_GENERALIZATION_DEVELOPMENT_PASSED", "version": VERSION, "contractDigest": digest, "constructDigest": construct_digest(),
                                "detectorSetDigest": det.contract_digest(), "generators": PROPOSAL_GENERATORS, "thresholds": THRESHOLDS, "prompts": list(PROMPTS), "iouMatch": IOU_MATCH,
                                "sizeBands": SIZE_BANDS, "edges": list(EDGES), "inset": INSET, "devGeometries": list(DEV_GEOMETRIES), "holdoutGeometries": list(HOLDOUT_GEOMETRIES),
                                "developmentInputsDigest": dev_digest, "frozenAt": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    return path


def require_dev_passed(private_dir: Path, digest: str) -> Mapping[str, Any]:
    path = Path(private_dir) / DEV_PASS_MARKER_NAME
    if not path.exists():
        raise NotFrozen("holdout requires the frozen development-pass record")
    r = json.loads(path.read_text(encoding="utf-8"))
    expected = {"contractDigest": digest, "constructDigest": construct_digest(), "detectorSetDigest": det.contract_digest(), "generators": PROPOSAL_GENERATORS, "thresholds": THRESHOLDS,
                "prompts": list(PROMPTS), "iouMatch": IOU_MATCH, "sizeBands": SIZE_BANDS, "edges": list(EDGES), "inset": INSET, "devGeometries": list(DEV_GEOMETRIES),
                "holdoutGeometries": list(HOLDOUT_GEOMETRIES), "version": VERSION}
    if any(r.get(k) != v for k, v in expected.items()):
        raise NotFrozen("development-pass record does not match the frozen contract (retuning refused)")
    return r


def holdout_guard(private_dir: Path, digest: str) -> Path:
    require_dev_passed(private_dir, digest)
    lock = Path(private_dir) / HOLDOUT_LOCK_NAME
    if lock.exists():
        raise sel.HoldoutAlreadyEvaluated(f"edge holdout already evaluated once: {lock.name}")
    return lock


def mark_holdout(lock: Path, digest: str) -> None:
    lock.write_text(json.dumps({"contractDigest": digest, "evaluatedAt": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")


def l11_holdout_untouched_audit(b3l11_dir: Path) -> dict[str, Any]:
    p = Path(b3l11_dir)
    captures = {name: (p / f"capture_{name}_holdout.jsonl").exists() for name in PROPOSAL_GENERATORS}
    lock = (p / det.HOLDOUT_LOCK_NAME).exists()
    selected = (p / det.SELECTED_MARKER_NAME).exists() or (p / pv.SELECTED_MARKER_NAME).exists()
    return {"captures": captures, "lockExists": lock, "selectedMarkerExists": selected, "untouched": not any(captures.values()) and not lock and not selected}
