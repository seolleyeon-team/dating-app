"""B3-L12A evaluator (offline, aggregate-only, decision-neutral).

Order (blinding enforced by --stage):
  clean-inventory : reads ONLY the 12 clean development rows -> aggregate geometry inventory (hypothesis generation)
  development     : applies the frozen candidates to clean + positive development rows -> table, gate A-L, selection, freeze
  holdout         : one-shot G4-G5 + HOLDOUT_VARIANT evaluation of the frozen candidate (existing B3-L11 lock)

Inputs are the B3-L11 Grounding DINO captures (development reused with exact
provenance; holdout captured only after the freeze).  Clean canonical actions
come from the B3-L4 Florence V0 rows.  The shadow simulator is review-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_florence_ceiling as bench  # noqa: E402
import avatar_gdino_geometry_filter as gf  # noqa: E402
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_text_policy_shadow_eval as tpe  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402
import avatar_visual_mark_eval as ev  # noqa: E402

REPORT_VERSION = "avatar_gdino_geometry_eval_v1"


def _rows(path: Path, *, clean_only: bool) -> list[dict[str, Any]]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if clean_only and not row["conditionId"].endswith(":CLEAN"):
            continue          # positive rows are never parsed at the inventory stage
        out.append(row)
    return out


def provenance(capture_dir: Path, split: str) -> dict[str, Any]:
    meta_path = capture_dir / f"run_meta_{gf.DETECTOR}_{split}.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    spec = det.CANDIDATES[gf.DETECTOR]
    checks = {"revision": meta.get("revision") == spec["revision"], "repo": meta.get("repo") == spec["repo"], "license": meta.get("license") == spec["license"],
              "detectorSetDigest": meta.get("contractDigestPrefix") == det.contract_digest()[:12], "constructDigest": meta.get("constructDigestPrefix") == c3.construct_digest()[:12],
              "floorSufficient": float(spec["floor"]) <= gf.OPERATING_POINT["threshold"], "variant": meta.get("variant") == (c3.DEV_VARIANT if split == "development" else c3.HOLDOUT_VARIANT),
              "originalsUnchanged": meta.get("originalsUnchanged") is True}
    return {"split": split, "checks": checks, "exact": all(checks.values()), "peakRssGb": meta.get("peakRssGb"), "device": meta.get("device")}


def _q(values: Sequence[float]) -> Optional[dict[str, float]]:
    v = sorted(values)
    if not v:
        return None
    def qq(p):
        pos = (len(v) - 1) * p
        lo, hi = int(pos), min(int(pos) + 1, len(v) - 1)
        return round(v[lo] + (v[hi] - v[lo]) * (pos - lo), 4)
    return {"min": round(v[0], 4), "q1": qq(0.25), "median": qq(0.5), "q3": qq(0.75), "max": round(v[-1], 4)}


def clean_inventory(clean_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    feats: dict[str, list] = defaultdict(list)
    per_image = []
    loc = Counter()
    border = near = full = 0
    for r in clean_rows:
        W, H = r["imageSize"]
        kept = det.filter_detections(gf.DETECTOR, r["detections"], gf.OPERATING_POINT, r["imageSize"])
        per_image.append(len(kept))
        for d in kept:
            g = gf.box_geometry(d["box"], r["imageSize"])
            x0, y0, x1, y1 = d["box"]
            cx, cy = (x0 + x1) / 2 / W, (y0 + y1) / 2 / H
            feats["normalizedArea"].append(g["normalizedArea"]); feats["aspectRatio"].append(g["aspectRatio"])
            feats["normalizedWidth"].append((x1 - x0) / W); feats["normalizedHeight"].append((y1 - y0) / H); feats["centerX"].append(cx); feats["centerY"].append(cy)
            border += int(x0 <= 2 or y0 <= 2 or x1 >= W - 2 or y1 >= H - 2)
            near += int(x0 / W < 0.05 or y0 / H < 0.05 or x1 / W > 0.95 or y1 / H > 0.95)
            full += int(g["normalizedArea"] >= 0.5)
            ex, ey = cx <= 0.15 or cx >= 0.85, cy <= 0.15 or cy >= 0.85
            loc["corner" if ex and ey else "edge" if ex or ey else "clothing_zone" if 0.45 <= cy <= 0.85 and 0.2 <= cx <= 0.8 else "central"] += 1
    area = feats["normalizedArea"]
    return {"n": len(clean_rows), "boxes": len(area), "imagesWithBoxes": sum(1 for p in per_image if p), "detectionsPerImage": _q(per_image),
            "features": {k: _q(v) for k, v in feats.items()}, "locationBand": dict(loc), "borderTouch": border, "nearBorder5pct": near, "fullFrameLike": full,
            "areaBands": {b: sum(1 for a in area if lo <= a < hi) for b, (lo, hi) in {"<0.01": (0, .01), "0.01-0.03": (.01, .03), "0.03-0.08": (.03, .08), "0.08-0.20": (.08, .2), "0.20-0.50": (.2, .5), ">=0.50": (.5, 9)}.items()},
            "aspectBands": {b: sum(1 for a in feats["aspectRatio"] if lo <= a < hi) for b, (lo, hi) in {"<1/3": (0, 1 / 3), "1/3-3": (1 / 3, 3), "3-4": (3, 4), ">=4": (4, 999)}.items()},
            "imagesByTinyBoxCount": {str(k): v for k, v in sorted(Counter(sum(1 for d in det.filter_detections(gf.DETECTOR, r["detections"], gf.OPERATING_POINT, r["imageSize"]) if gf.box_geometry(d["box"], r["imageSize"])["normalizedArea"] < 0.01) for r in clean_rows).items())},
            "candidateCleanSurvivalPreview": {c.id: sum(1 for r in clean_rows if gf.clean_response(c, r["detections"], r["imageSize"])) for c in gf.CANDIDATES}}


def evaluate(candidate: gf.Candidate, rows: Sequence[Mapping[str, Any]], actions: Mapping[str, str], truth: Mapping[str, Optional[str]]) -> dict[str, Any]:
    clean = [r for r in rows if r["conditionId"].endswith(":CLEAN") and truth.get(r["opaqueId"]) == "negative"]
    positives = [r for r in rows if not r["conditionId"].endswith(":CLEAN")]
    clean_rows = []
    new_review = bypass = downgrade = 0
    order = {"allow": 0, "review": 1, "reject": 2}
    for r in clean:
        canonical = actions.get(r["opaqueId"])
        if canonical is None:
            continue
        hit = gf.clean_response(candidate, r["detections"], r["imageSize"])
        action = gf.shadow_action(canonical, hit)
        new_review += int(canonical == "allow" and action == "review")
        bypass += int(canonical == "reject" and action != "reject")
        downgrade += int(order[action] < order[canonical])
        clean_rows.append({"canonical": canonical, "hit": hit})
    n_clean = len(clean_rows)
    fam: dict[str, list] = defaultdict(list); alpha: dict[str, list] = defaultdict(list); place: dict[str, list] = defaultdict(list); size: dict[str, list] = defaultdict(list)
    gated_hits = gated_n = box_hits = box_total = 0
    ious = []
    for r in positives:
        m = r["meta"]
        h = gf.image_hit(candidate, r["detections"], r["groundTruth"], r["imageSize"])
        fam[m["family"]].append(h["hit"]); alpha[m["alphaName"]].append(h["hit"]); place[m["placementClass"]].append(h["hit"]); size[m["sizeBand"]].append(h["hit"])
        box_hits += h["boxHits"]; box_total += h["boxes"]
        if h["hit"]:
            ious.append(h["bestIou"])
        if not m.get("diagnostic"):
            gated_n += 1; gated_hits += int(h["hit"])
    def table(d):
        return {k: {"k": sum(v), "n": len(v), "rate": round(sum(v) / len(v), 4) if v else None} for k, v in sorted(d.items())}
    fam_t = table(fam)
    checks = {"A": n_clean > 0 and new_review / n_clean <= ev.NEW_REVIEW_CEILING, "B": gated_n > 0 and gated_hits / gated_n >= ev.OVERALL_RECALL_FLOOR,
              **{c: (f in fam_t and fam_t[f]["rate"] is not None and fam_t[f]["rate"] >= ev.FAMILY_RECALL_FLOOR) for c, f in ev.GATE_FAMILY.items()}, "K": bypass == 0, "L": downgrade == 0}
    critical_min = min((fam_t[f]["rate"] for f in ev.GATE_FAMILY.values() if f in fam_t and fam_t[f]["rate"] is not None), default=None)
    return {"candidate": candidate.id, "rank": candidate.rank, "predicate": candidate.predicate,
            "clean": {"n": n_clean, "canonical": dict(Counter(r["canonical"] for r in clean_rows)), "cleanImageResponse": sum(1 for r in clean_rows if r["hit"]), "newAllowToReview": new_review,
                      "newReviewRate": round(new_review / n_clean, 4) if n_clean else None, "newReviewRateCI": calib.wilson(new_review, n_clean) if n_clean else None,
                      "existingCanonicalBurdenNotCounted": sum(1 for r in clean_rows if r["canonical"] != "allow"), "hardRejectBypass": bypass, "downgrades": downgrade},
            "overall": {"k": gated_hits, "n": gated_n, "rate": round(gated_hits / gated_n, 4) if gated_n else None, "requiredHits": ev.required_hits(gated_n, ev.OVERALL_RECALL_FLOOR), "excludes": c3.LOW_VISIBILITY_FAMILY},
            "families": fam_t, "alphas": table(alpha), "placements": table(place), "sizes": table(size),
            "lowVisibility": {"family": c3.LOW_VISIBILITY_FAMILY, "marker": c3.LOW_VISIBILITY_MARKER, **fam_t.get(c3.LOW_VISIBILITY_FAMILY, {"k": 0, "n": 0, "rate": None})},
            "boxRecall": {"k": box_hits, "n": box_total, "rate": round(box_hits / box_total, 4) if box_total else None}, "meanIouOnHits": round(statistics.mean(ious), 4) if ious else None,
            "criticalFamilyMinRecall": critical_min, "criteria": checks, "eligible": all(checks[c] for c in ev.CRITERIA), "failed": [c for c in ev.CRITERIA if not checks[c]]}


def select(table: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    elig = [t for t in table if t["eligible"]]
    if not elig:
        return {"status": "NONE", "candidate": None, "reason": "no geometry candidate satisfies A-L on development"}
    best = sorted(elig, key=lambda t: (-(t["criticalFamilyMinRecall"] or 0), -(t["overall"]["rate"] or 0), t["clean"]["newReviewRate"], t["rank"]))[0]
    return {"status": "SELECTED", "candidate": best["candidate"], "predicate": best["predicate"], "role": gf.SELECTED_ROLE,
            "reason": "highest minimum critical-family recall -> highest overall recall -> lowest new clean burden -> least aggressive pre-registered rule"}


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def run(stage: str, capture_dir: Path, private_dir: Path, florence_rows, label_artifact) -> dict[str, Any]:
    digest = gf.contract_digest()
    base: dict[str, Any] = {"reportVersion": REPORT_VERSION, "version": gf.VERSION, "candidateSet": gf.CANDIDATE_SET_VERSION, "designation": gf.DESIGNATION,
                            "contractDigestPrefix": digest[:12], "priorStatus": gf.PRIOR_STATUS, "orEnsemble": gf.OR_ENSEMBLE_MARKER,
                            "detector": {k: v for k, v in det.CANDIDATES[gf.DETECTOR].items() if k != "dir"}, "operatingPoint": gf.OPERATING_POINT,
                            "candidates": [dict(id=c.id, rank=c.rank, maxArea=c.max_area, aspectCap=c.aspect_cap, predicate=c.predicate) for c in gf.CANDIDATES],
                            "developmentProvenance": provenance(capture_dir, "development"), "watermarkPolicyChanged": False, "decisionDiff": 0, "holdoutEvaluated": 0}
    dev_path = capture_dir / f"capture_{gf.DETECTOR}_development.jsonl"
    if stage == "clean-inventory":
        base["cleanInventory"] = clean_inventory(_rows(dev_path, clean_only=True))
        base["positiveRowsOpened"] = False
        return base
    if not base["developmentProvenance"]["exact"]:
        raise SystemExit("DEVELOPMENT_CAPTURE_PROVENANCE_MISMATCH")
    actions = ev.clean_actions(florence_rows)
    truth = {r["evaluationId"]: tpe.sel_truth(r) for r in label_artifact["labels"]}
    rows = _rows(dev_path, clean_only=False)
    table = [evaluate(c, rows, actions, truth) for c in gf.CANDIDATES]
    selection = select(table)
    base.update({"development": {"rows": len(rows), "table": table, "selection": selection}, "developmentInferenceCalls": 0})
    if selection["status"] != "SELECTED":
        base.update(gf.verdict(False, None))
        base["diagnosis"] = gf.diagnosis(table)
        base["gaps"] = ev.gap_markers(None)
        return base
    cand = gf.CANDIDATE_BY_ID[selection["candidate"]]
    dev_digest = _digest([[r["conditionId"], r["detections"]] for r in rows])
    marker = Path(private_dir) / det.SELECTED_MARKER_NAME
    if marker.exists():
        frozen = gf.require_selected(private_dir, digest)
        if frozen["geometryCandidate"] != cand.id:
            raise gf.NotFrozen("selection differs from the frozen record")
    else:
        base["holdoutUnopenedAuditAtFreeze"] = gf.holdout_unopened_audit(private_dir)
        gf.write_selected(private_dir, cand, digest, dev_digest)
    base["selectedFrozen"] = {"candidate": cand.id, "predicate": cand.predicate, "developmentInputsDigestPrefix": dev_digest[:12]}
    if stage != "holdout":
        base.update(gf.verdict(True, None))
        base["gaps"] = ev.gap_markers(None)
        return base
    hold_prov = provenance(capture_dir, "holdout")
    base["holdoutProvenance"] = hold_prov
    if not hold_prov["exact"]:
        raise SystemExit("HOLDOUT_CAPTURE_PROVENANCE_MISMATCH")
    hold_rows = _rows(capture_dir / f"capture_{gf.DETECTOR}_holdout.jsonl", clean_only=False)
    need_pos = len(c3.conditions(c3.HOLDOUT_VARIANT)) * len(c3.HOLDOUT_GROUPS)
    if sum(1 for r in hold_rows if not r["conditionId"].endswith(":CLEAN")) < need_pos or sum(1 for r in hold_rows if r["conditionId"].endswith(":CLEAN")) < len(c3.HOLDOUT_GROUPS) * 4 // 4:
        raise SystemExit("HOLDOUT_CAPTURE_INCOMPLETE")
    lock = gf.holdout_guard(private_dir, digest)
    result = evaluate(cand, hold_rows, actions, truth)
    ev.mark_holdout(lock, digest)
    base["holdoutEvaluated"] = 1
    base["holdout"] = result
    base["holdoutRequiredHits"] = {"overall": result["overall"]["requiredHits"], **{f: ev.required_hits(result["families"][f]["n"], ev.FAMILY_RECALL_FLOOR) for f in ev.GATE_FAMILY.values() if f in result["families"]}}
    base.update(gf.verdict(True, result["eligible"]))
    base["gaps"] = ev.gap_markers(result if result["eligible"] else None)
    return base


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=("clean-inventory", "development", "holdout"))
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--florence-rows", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--forbidden-strings", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    labels = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else {"labels": []}
    if args.stage != "clean-inventory" and (not labels.get("complete") or labels.get("unresolvedCount")):
        raise SystemExit("BLOCKED_HUMAN_LABELS_REQUIRED")
    florence = ev._jsonl(args.florence_rows) if args.florence_rows else []
    report = run(args.stage, args.capture_dir, args.private_dir, florence, labels)
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
