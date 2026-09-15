"""B3-L11 evaluator (offline, aggregate-only, decision-neutral).

Reads the low-floor captures (one per detector per split), applies every
pre-registered operating point as a filter, computes the development table
(G1-G3 + DEV_VARIANT), gate A-L, selection, freeze, and — only after the
freeze and behind visual_mark_detector_v1_holdout.lock — the one-shot holdout
(G4-G5 + HOLDOUT_VARIANT) for the selected detector/operating point.

Clean canonical actions come from the B3-L4 Florence V0 rows (production
contract).  The shadow simulator is review-only: max(canonical, review).  For
positive constructs the primary metric is the image-level construct hit; the
canonical action of a derivative is not captured here (that would need a
Florence OCR run per derivative), so bypass/downgrade are proven structurally
and measured on the clean rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_florence_ceiling as bench  # noqa: E402
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_text_policy_shadow_eval as tpe  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402

REPORT_VERSION = "avatar_visual_mark_eval_v1"
NEW_REVIEW_CEILING = 0.10
OVERALL_RECALL_FLOOR = 0.95
FAMILY_RECALL_FLOOR = 0.90
GATE_FAMILY = {"C": "TEXT_WATERMARK_OPAQUE", "D": "TEXT_WATERMARK_TRANSLUCENT_HIGH", "E": "TEXT_WATERMARK_TRANSLUCENT_MEDIUM", "F": "GRAPHICAL_WATERMARK_TRANSLUCENT",
               "G": "LOGO_LIKE_EMBLEM", "H": "SMALL_CORNER_MARK", "I": "EDGE_MARK", "J": "CENTER_OVERLAY_MARK"}
CRITERIA = ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L")
PRIOR_STATUS = {"V1": "OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT", "V2": "OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT", "V3": "V3_DUAL_CHANNEL_FAILED_DEVELOPMENT",
                "B3_L9": "TEXT_POLICY_SHADOW_HOLDOUT_FAILED", "B3_L10A": "FLORENCE_SEQUENCE_SCORE_NOT_SEPARATING", "B3_L10B": "FLORENCE_TWO_FEATURE_NOT_SEPARATING",
                "TEXT_POLICY_GAP": "unresolved", "GRAPHICAL_CHANNEL_GAP": "unresolved", "NATURAL_POSITIVE": "NATURAL_POSITIVE_EVIDENCE_MISSING",
                "FLORENCE_TELEMETRY": c3.FLORENCE_TELEMETRY_CLOSURE}


def required_hits(n: int, floor: float) -> int:
    import math

    return int(math.ceil(floor * n - 1e-9))


def _rate(k: int, n: int) -> Optional[float]:
    return round(k / n, 4) if n else None


# ------------------------------------------------------------------ rows


def clean_actions(florence_rows) -> dict[str, str]:
    out = {}
    for r in florence_rows:
        if r.get("domain") == bench.DOMAIN_AVATAR and r.get("variant") == "V0" and bench.TASK_OD in r["tasks"]:
            out[r["baseOpaqueId"]] = tpe.canonical(r["tasks"], r["imageSize"])[0]
    return out


def evaluate(name: str, op_id: str, op: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], actions: Mapping[str, str], truth: Mapping[str, Optional[str]]) -> dict[str, Any]:
    clean = [r for r in rows if r["conditionId"].endswith(":CLEAN") and truth.get(r["opaqueId"]) == "negative"]
    positives = [r for r in rows if not r["conditionId"].endswith(":CLEAN")]
    clean_rows = []
    new_review = bypass = downgrade = 0
    for r in clean:
        canonical = actions.get(r["opaqueId"])
        if canonical is None:
            continue
        hit = det.clean_response(name, r["detections"], op, r["imageSize"])
        action = det.shadow_action(canonical, hit)
        if canonical == "allow" and action == "review":
            new_review += 1
        if canonical == "reject" and action != "reject":
            bypass += 1
        if {"allow": 0, "review": 1, "reject": 2}[action] < {"allow": 0, "review": 1, "reject": 2}[canonical]:
            downgrade += 1
        clean_rows.append({"canonical": canonical, "hit": hit})
    n_clean = len(clean_rows)
    response = sum(1 for r in clean_rows if r["hit"])
    fam: dict[str, list] = defaultdict(list)
    alpha: dict[str, list] = defaultdict(list)
    place: dict[str, list] = defaultdict(list)
    size: dict[str, list] = defaultdict(list)
    length: dict[str, list] = defaultdict(list)
    box_hits = box_total = 0
    ious = []
    gated_hits = gated_n = 0
    for r in positives:
        m = r["meta"]
        h = det.image_hit(name, r["detections"], r["groundTruth"], op, r["imageSize"])
        fam[m["family"]].append(h["hit"])
        alpha[m["alphaName"]].append(h["hit"])
        place[m["placementClass"]].append(h["hit"])
        size[m["sizeBand"]].append(h["hit"])
        if m.get("textLengthClass"):
            length[m["textLengthClass"]].append(h["hit"])
        box_hits += h["boxHits"]
        box_total += h["boxes"]
        if h["hit"]:
            ious.append(h["bestIou"])
        if not m.get("diagnostic"):
            gated_n += 1
            gated_hits += int(h["hit"])
    def table(d):
        return {k: {"k": sum(v), "n": len(v), "rate": _rate(sum(v), len(v))} for k, v in sorted(d.items())}
    fam_t = table(fam)
    latencies = sorted(r["seconds"] for r in rows)
    checks = {
        "A": n_clean > 0 and new_review / n_clean <= NEW_REVIEW_CEILING,
        "B": gated_n > 0 and gated_hits / gated_n >= OVERALL_RECALL_FLOOR,
        **{c: (f in fam_t and fam_t[f]["rate"] is not None and fam_t[f]["rate"] >= FAMILY_RECALL_FLOOR) for c, f in GATE_FAMILY.items()},
        "K": bypass == 0,
        "L": downgrade == 0,
    }
    critical_min = min((fam_t[f]["rate"] for f in GATE_FAMILY.values() if f in fam_t and fam_t[f]["rate"] is not None), default=None)
    return {
        "detector": name, "operatingPoint": op_id, "params": dict(op), "role": "BASELINE" if op_id in det.CANDIDATES[name]["operatingPoints"] else "PRE_REGISTERED_GRID",
        "clean": {"n": n_clean, "canonical": dict(Counter(r["canonical"] for r in clean_rows)), "cleanImageResponse": response, "newAllowToReview": new_review,
                  "newReviewRate": _rate(new_review, n_clean), "newReviewRateCI": calib.wilson(new_review, n_clean) if n_clean else None,
                  "existingCanonicalBurdenNotCounted": sum(1 for r in clean_rows if r["canonical"] != "allow"), "hardRejectBypass": bypass, "downgrades": downgrade},
        "overall": {"k": gated_hits, "n": gated_n, "rate": _rate(gated_hits, gated_n), "requiredHits": required_hits(gated_n, OVERALL_RECALL_FLOOR), "excludes": c3.LOW_VISIBILITY_FAMILY},
        "families": fam_t, "alphas": table(alpha), "placements": table(place), "sizes": table(size), "textLengthClasses": table(length),
        "lowVisibility": {"family": c3.LOW_VISIBILITY_FAMILY, "marker": c3.LOW_VISIBILITY_MARKER, **fam_t.get(c3.LOW_VISIBILITY_FAMILY, {"k": 0, "n": 0, "rate": None})},
        "boxRecall": {"k": box_hits, "n": box_total, "rate": _rate(box_hits, box_total)}, "meanIouOnHits": round(statistics.mean(ious), 4) if ious else None,
        "latencySeconds": {"median": round(statistics.median(latencies), 2) if latencies else None, "p90": round(latencies[int(0.9 * len(latencies)) - 1], 2) if latencies else None, "device": det.DEVICE},
        "criticalFamilyMinRecall": critical_min, "criteria": checks, "eligible": all(checks[c] for c in CRITERIA), "failed": [c for c in CRITERIA if not checks[c]],
    }


def select(table: Sequence[Mapping[str, Any]], resources: Mapping[str, float]) -> dict[str, Any]:
    """Development table only: lowest new clean burden -> highest min critical recall -> highest overall -> lower peak RSS -> lower median latency."""

    elig = [t for t in table if t["eligible"]]
    if not elig:
        return {"status": "NONE", "detector": None, "operatingPoint": None, "reason": "no detector/operating point satisfies A-L on development"}
    best = sorted(elig, key=lambda t: (t["clean"]["newReviewRate"], -(t["criticalFamilyMinRecall"] or 0), -(t["overall"]["rate"] or 0),
                                       resources.get(t["detector"], 1e9), t["latencySeconds"]["median"] or 1e9))[0]
    return {"status": "SELECTED", "detector": best["detector"], "operatingPoint": best["operatingPoint"], "params": best["params"], "role": det.SELECTED_ROLE,
            "reason": "lowest new clean burden -> highest minimum critical-family recall -> highest overall recall -> lower peak RSS -> lower median latency"}


# ------------------------------------------------------------------ freeze / holdout guards


class NotFrozen(RuntimeError):
    pass


def write_selected(private_dir: Path, selection: Mapping[str, Any], digest: str, cdigest: str, dev_digest: str) -> Path:
    spec = det.CANDIDATES[selection["detector"]]
    path = Path(private_dir) / det.SELECTED_MARKER_NAME
    path.write_text(json.dumps({"role": det.SELECTED_ROLE, "detector": selection["detector"], "repo": spec["repo"], "revision": spec["revision"], "license": spec["license"],
                                "prompts": spec["prompts"], "operatingPoint": selection["operatingPoint"], "params": selection["params"], "maxLongSide": det.MAX_LONG_SIDE,
                                "iouMatch": det.IOU_MATCH, "contractDigest": digest, "constructDigest": cdigest, "developmentInputsDigest": dev_digest,
                                "frozenAt": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    return path


def require_selected(private_dir: Path, digest: str, cdigest: str) -> Mapping[str, Any]:
    path = Path(private_dir) / det.SELECTED_MARKER_NAME
    if not path.exists():
        raise NotFrozen("holdout requires a frozen selected detector")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("contractDigest") != digest or record.get("constructDigest") != cdigest or record.get("detector") not in det.CANDIDATES:
        raise NotFrozen("selected record does not match the frozen contracts")
    if record.get("operatingPoint") not in det.operating_points(record["detector"]):
        raise NotFrozen("operating point outside the frozen set (retuning refused)")
    return record


def holdout_guard(private_dir: Path, digest: str, cdigest: str) -> Path:
    require_selected(private_dir, digest, cdigest)
    lock = Path(private_dir) / det.HOLDOUT_LOCK_NAME
    if lock.exists():
        raise sel.HoldoutAlreadyEvaluated(f"detector holdout already evaluated once: {lock.name}")
    return lock


def mark_holdout(lock: Path, digest: str) -> None:
    lock.write_text(json.dumps({"contractDigest": digest, "evaluatedAt": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")


def verdict(dev_selected: bool, holdout_pass: Optional[bool]) -> dict[str, str]:
    if not dev_selected:
        return {"verdict": "VISUAL_MARK_DETECTOR_FAILED_DEVELOPMENT", "support": "VISUAL_MARK_DETECTOR_NOT_SUPPORTED"}
    if holdout_pass is None:
        return {"verdict": "VISUAL_MARK_DETECTOR_DEVELOPMENT_ELIGIBLE_HOLDOUT_PENDING", "support": "VISUAL_MARK_DETECTOR_NOT_SUPPORTED"}
    if holdout_pass:
        return {"verdict": "VISUAL_MARK_DETECTOR_CONTROLLED_GATE_PASSED", "support": "VISUAL_MARK_DETECTOR_SUPPORTED_FOR_CONTROLLED_SHADOW_CANARY"}
    return {"verdict": "VISUAL_MARK_DETECTOR_HOLDOUT_FAILED", "support": "VISUAL_MARK_DETECTOR_NOT_SUPPORTED"}


def gap_markers(result: Optional[Mapping[str, Any]]) -> dict[str, str]:
    text = graphical = False
    if result:
        c = result["criteria"]
        text = c["C"] and c["D"] and c["E"]
        graphical = c["F"] and c["G"] and c["H"] and c["I"] and c["J"]
    return {"textPolicyGap": "TEXT_POLICY_GAP_UNRESOLVED (canonical policy unchanged)",
            "textDetector": "TEXT_DETECTOR_CONTROLLED_GAP_CLOSED" if text else "TEXT_DETECTOR_CONTROLLED_GAP_OPEN",
            "graphicalDetector": "GRAPHICAL_DETECTOR_CONTROLLED_GAP_CLOSED" if graphical else "GRAPHICAL_DETECTOR_STUDY_REQUIRED",
            "naturalPositive": "NATURAL_POSITIVE_EVIDENCE_MISSING"}


# ------------------------------------------------------------------ run


def _jsonl(path: Path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def load_captures(capture_dir: Path, split: str, reuse_clean: Optional[Path] = None) -> dict[str, list]:
    caps = {}
    for name in det.CANDIDATES:
        rows = _jsonl(capture_dir / f"capture_{name}_{split}.jsonl")
        if name == "owlv2-base-patch16-ensemble" and reuse_clean and reuse_clean.exists() and not any(r["conditionId"].endswith(":CLEAN") for r in rows):
            cap = json.load(open(reuse_clean, encoding="utf-8"))
            if cap.get("revision") == det.CANDIDATES[name]["revision"] and cap.get("floorScore") == det.CANDIDATES[name]["floor"] and list(cap.get("prompts", [])) == det.CANDIDATES[name]["prompts"]:
                groups = c3.DEVELOPMENT_GROUPS if split == "development" else c3.HOLDOUT_GROUPS
                for r in cap["rows"]:
                    if r["variant"] == "V0" and r["groupKey"] in groups:
                        rows.append({"conditionId": f"{r['opaqueId']}:CLEAN", "opaqueId": r["opaqueId"], "groupKey": r["groupKey"], "imageSize": r["imageSize"],
                                     "meta": {"family": None}, "groundTruth": [], "detections": r["detections"], "seconds": r["seconds"], "reusedFrom": "b3l5 owlv2_raw_capture (exact original pixels, same floor/prompts/revision)"})
        if rows:
            caps[name] = rows
    return caps


def run(capture_dir: Path, private_dir: Path, florence_rows, label_artifact, resources: Mapping[str, float], reuse_clean: Optional[Path] = None) -> dict[str, Any]:
    digest, cdigest = det.contract_digest(), c3.construct_digest()
    actions = clean_actions(florence_rows)
    truth = {r["evaluationId"]: tpe.sel_truth(r) for r in label_artifact["labels"]}
    dev_caps = load_captures(capture_dir, "development", reuse_clean)
    table = []
    expected = len(c3.conditions(c3.DEV_VARIANT)) * len(c3.DEVELOPMENT_GROUPS) * 4 // 4
    for name, rows in dev_caps.items():
        for op_id, op in det.operating_points(name).items():
            table.append(evaluate(name, op_id, op, rows, actions, truth))
    selection = select(table, resources)
    report: dict[str, Any] = {
        "reportVersion": REPORT_VERSION, "challengeVersion": c3.CHALLENGE_VERSION, "candidateSetVersion": det.CANDIDATE_SET_VERSION,
        "contractDigestPrefix": digest[:12], "constructDigestPrefix": cdigest[:12], "priorStatus": PRIOR_STATUS, "closureMarker": c3.FLORENCE_TELEMETRY_CLOSURE,
        "constructs": c3.definitions(), "candidates": {k: {kk: vv for kk, vv in v.items() if kk != "dir"} for k, v in det.CANDIDATES.items()}, "excluded": det.EXCLUDED,
        "criteria": {"A": NEW_REVIEW_CEILING, "B": OVERALL_RECALL_FLOOR, "C-J": FAMILY_RECALL_FLOOR, "K": 0, "L": 0, "gateFamilies": GATE_FAMILY},
        "development": {"capturedDetectors": sorted(dev_caps), "rowsPerDetector": {k: len(v) for k, v in dev_caps.items()}, "table": table, "selection": selection, "resources": dict(resources)},
        "holdoutEvaluated": 0, "holdoutName": c3.HOLDOUT_NAME, "decisionDiff": 0, "watermarkPolicyChanged": False,
    }
    if selection["status"] != "SELECTED":
        report.update(verdict(False, None))
        report["gaps"] = gap_markers(None)
        return report
    dev_digest = _digest([[name, r["conditionId"], r["detections"]] for name, rows in dev_caps.items() for r in rows])
    marker = Path(private_dir) / det.SELECTED_MARKER_NAME
    if marker.exists():
        frozen = require_selected(private_dir, digest, cdigest)
        if frozen["detector"] != selection["detector"] or frozen["operatingPoint"] != selection["operatingPoint"]:
            raise NotFrozen("selection differs from the frozen record")
    else:
        write_selected(private_dir, selection, digest, cdigest, dev_digest)
    report["selectedFrozen"] = {"detector": selection["detector"], "operatingPoint": selection["operatingPoint"], "params": selection["params"], "developmentInputsDigestPrefix": dev_digest[:12]}
    hold_caps = load_captures(capture_dir, "holdout", reuse_clean)
    rows = hold_caps.get(selection["detector"], [])
    need = len(c3.conditions(c3.HOLDOUT_VARIANT)) * len(c3.HOLDOUT_GROUPS)
    if sum(1 for r in rows if not r["conditionId"].endswith(":CLEAN")) < need or sum(1 for r in rows if r["conditionId"].endswith(":CLEAN")) < len(c3.HOLDOUT_GROUPS) * 4 // 4:
        report["holdoutStatus"] = "HOLDOUT_CAPTURE_MISSING (selected candidate frozen; capture may proceed)"
        report.update(verdict(True, None))
        report["gaps"] = gap_markers(None)
        return report
    lock = holdout_guard(private_dir, digest, cdigest)
    result = evaluate(selection["detector"], selection["operatingPoint"], selection["params"], rows, actions, truth)
    mark_holdout(lock, digest)
    report["holdoutEvaluated"] = 1
    report["holdout"] = result
    report["holdoutRequiredHits"] = {"overall": result["overall"]["requiredHits"], **{f: required_hits(result["families"][f]["n"], FAMILY_RECALL_FLOOR) for f in GATE_FAMILY.values() if f in result["families"]}}
    report.update(verdict(True, result["eligible"]))
    report["gaps"] = gap_markers(result if result["eligible"] else None)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--florence-rows", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--reuse-owlv2-clean", type=Path)
    parser.add_argument("--forbidden-strings", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    if not labels.get("complete") or labels.get("unresolvedCount"):
        raise SystemExit("BLOCKED_HUMAN_LABELS_REQUIRED")
    resources = {}
    for name in det.CANDIDATES:
        meta = args.capture_dir / f"run_meta_{name}_development.json"
        if meta.exists():
            resources[name] = float(json.loads(meta.read_text(encoding="utf-8")).get("peakRssGb", 0.0))
    report = run(args.capture_dir, args.private_dir, _jsonl(args.florence_rows), labels, resources, args.reuse_owlv2_clean)
    forbidden = [l.strip() for l in args.forbidden_strings.read_text(encoding="utf-8").splitlines() if l.strip()] if args.forbidden_strings and args.forbidden_strings.exists() else []
    problems = bench.privacy_violations(report, forbidden)
    if problems:
        raise SystemExit(f"PRIVACY_VIOLATION {problems}")
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
