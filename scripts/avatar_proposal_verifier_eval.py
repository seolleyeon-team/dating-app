"""B3-L13 evaluator (offline, aggregate-only, decision-neutral).

Stages (order enforced):
  coverage    : frozen proposal-union ceiling on G1-G3 + DEV_VARIANT (no verifier) -> coverage gate A-I
  development : group out-of-fold verifier scores -> image-level pipeline table over the frozen threshold grid -> J1-J12 -> selection -> freeze
  holdout     : one-shot G4-G5 + HOLDOUT_VARIANT with a classifier fit once on all G1-G3 and the frozen threshold

No training-set performance is ever a gate.  Ground truth is label/evaluation
authority only.  The shadow simulator is review-only on canonical clean actions
from the B3-L4 Florence V0 rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_florence_ceiling as bench  # noqa: E402
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_proposal_verifier as pv  # noqa: E402
import avatar_text_policy_shadow_eval as tpe  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402
import avatar_visual_mark_eval as ev  # noqa: E402

REPORT_VERSION = "avatar_proposal_verifier_eval_v1"
COVERAGE_FAMILY = {"B": "TEXT_WATERMARK_OPAQUE", "C": "TEXT_WATERMARK_TRANSLUCENT_HIGH", "D": "TEXT_WATERMARK_TRANSLUCENT_MEDIUM", "E": "GRAPHICAL_WATERMARK_TRANSLUCENT",
                   "F": "LOGO_LIKE_EMBLEM", "G": "SMALL_CORNER_MARK", "H": "EDGE_MARK", "I": "CENTER_OVERLAY_MARK"}
J_FAMILY = {"J3": "TEXT_WATERMARK_OPAQUE", "J4": "TEXT_WATERMARK_TRANSLUCENT_HIGH", "J5": "TEXT_WATERMARK_TRANSLUCENT_MEDIUM", "J6": "GRAPHICAL_WATERMARK_TRANSLUCENT",
            "J7": "LOGO_LIKE_EMBLEM", "J8": "SMALL_CORNER_MARK", "J9": "EDGE_MARK", "J10": "CENTER_OVERLAY_MARK"}
J_CRITERIA = ("J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8", "J9", "J10", "J11", "J12")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def _rate(k, n):
    return round(k / n, 4) if n else None


def _table(d: Mapping[str, list]) -> dict[str, dict[str, Any]]:
    return {k: {"k": sum(v), "n": len(v), "rate": _rate(sum(v), len(v))} for k, v in sorted(d.items())}


# ------------------------------------------------------------------ coverage (no verifier)


def coverage(capture_dir: Path, split: str) -> dict[str, Any]:
    prov = {name: _provenance(capture_dir, split, name) for name in pv.PROPOSAL_GENERATORS}
    by_cond: dict[str, dict[str, dict]] = {}
    for name in pv.PROPOSAL_GENERATORS:
        for r in _jsonl(capture_dir / f"capture_{name}_{split}.jsonl"):
            by_cond.setdefault(r["conditionId"], {})[name] = r
    fam: dict[str, list] = defaultdict(list)
    per_source: dict[str, Counter] = defaultdict(Counter)
    gated_hits = gated_n = 0
    clean_props = []
    for cid, rows in by_cond.items():
        any_row = next(iter(rows.values()))
        props = pv.union_proposals({n: r["detections"] for n, r in rows.items()}, any_row["imageSize"])
        if cid.endswith(":CLEAN"):
            clean_props.append(len(props))
            for p in props:
                per_source["clean"][p["source"]] += 1
            continue
        m = any_row["meta"]
        hit = pv.coverage_hit(props, any_row["groundTruth"])
        fam[m["family"]].append(hit)
        for p in props:
            per_source["positive"][p["source"]] += 1
        if not m.get("diagnostic"):
            gated_n += 1
            gated_hits += int(hit)
    fam_t = _table(fam)
    checks = {"A": gated_n > 0 and gated_hits / gated_n >= ev.OVERALL_RECALL_FLOOR,
              **{c: (f in fam_t and fam_t[f]["rate"] is not None and fam_t[f]["rate"] >= ev.FAMILY_RECALL_FLOOR) for c, f in COVERAGE_FAMILY.items()}}
    return {"split": split, "provenance": prov, "provenanceExact": all(p["exact"] for p in prov.values()), "conditions": len(by_cond),
            "overall": {"k": gated_hits, "n": gated_n, "rate": _rate(gated_hits, gated_n)}, "families": fam_t,
            "cleanProposalsPerImage": {"n": len(clean_props), "total": sum(clean_props), "min": min(clean_props, default=0), "max": max(clean_props, default=0)},
            "proposalsBySource": {k: dict(v) for k, v in per_source.items()}, "criteria": checks, "pass": all(checks.values()), "failed": [k for k, v in checks.items() if not v]}


def _provenance(capture_dir: Path, split: str, name: str) -> dict[str, Any]:
    meta_path = capture_dir / f"run_meta_{name}_{split}.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    spec = det.CANDIDATES[name]
    checks = {"revision": meta.get("revision") == spec["revision"], "repo": meta.get("repo") == spec["repo"], "license": meta.get("license") == spec["license"],
              "detectorSetDigest": meta.get("contractDigestPrefix") == det.contract_digest()[:12], "constructDigest": meta.get("constructDigestPrefix") == c3.construct_digest()[:12],
              "variant": meta.get("variant") == (c3.DEV_VARIANT if split == "development" else c3.HOLDOUT_VARIANT), "originalsUnchanged": meta.get("originalsUnchanged") is True}
    return {"checks": checks, "exact": all(checks.values()), "peakRssGb": meta.get("peakRssGb")}


# ------------------------------------------------------------------ pipeline evaluation


def evaluate(records: Sequence[Mapping[str, Any]], scores_by_id: Mapping[str, float], threshold: float, actions: Mapping[str, str], truth: Mapping[str, Optional[str]]) -> dict[str, Any]:
    order = {"allow": 0, "review": 1, "reject": 2}
    clean_rows = []
    new_review = bypass = downgrade = 0
    fam: dict[str, list] = defaultdict(list); alpha: dict[str, list] = defaultdict(list); place: dict[str, list] = defaultdict(list); size: dict[str, list] = defaultdict(list)
    gated_hits = gated_n = 0
    survivors_total = 0
    for rec in records:
        out = pv.image_outcome(rec["proposals"], scores_by_id, threshold, rec["groundTruth"])
        survivors_total += out["survivors"]
        if rec["clean"]:
            if truth.get(rec["opaqueId"]) != "negative":
                continue
            canonical = actions.get(rec["opaqueId"])
            if canonical is None:
                continue
            action = pv.shadow_action(canonical, out["response"])
            new_review += int(canonical == "allow" and action == "review")
            bypass += int(canonical == "reject" and action != "reject")
            downgrade += int(order[action] < order[canonical])
            clean_rows.append({"canonical": canonical, "hit": out["response"]})
            continue
        m = rec["meta"]
        fam[m["family"]].append(out["hit"]); alpha[m["alphaName"]].append(out["hit"]); place[m["placementClass"]].append(out["hit"]); size[m["sizeBand"]].append(out["hit"])
        if not m.get("diagnostic"):
            gated_n += 1; gated_hits += int(out["hit"])
    n_clean = len(clean_rows)
    fam_t = _table(fam)
    checks = {"J1": n_clean > 0 and new_review / n_clean <= ev.NEW_REVIEW_CEILING, "J2": gated_n > 0 and gated_hits / gated_n >= ev.OVERALL_RECALL_FLOOR,
              **{c: (f in fam_t and fam_t[f]["rate"] is not None and fam_t[f]["rate"] >= ev.FAMILY_RECALL_FLOOR) for c, f in J_FAMILY.items()}, "J11": bypass == 0, "J12": downgrade == 0}
    critical_min = min((fam_t[f]["rate"] for f in J_FAMILY.values() if f in fam_t and fam_t[f]["rate"] is not None), default=None)
    return {"threshold": threshold, "scoreRole": pv.SCORE_ROLE,
            "clean": {"n": n_clean, "canonical": dict(Counter(r["canonical"] for r in clean_rows)), "cleanImageResponse": sum(1 for r in clean_rows if r["hit"]), "newAllowToReview": new_review,
                      "newReviewRate": _rate(new_review, n_clean), "newReviewRateCI": calib.wilson(new_review, n_clean) if n_clean else None,
                      "existingCanonicalBurdenNotCounted": sum(1 for r in clean_rows if r["canonical"] != "allow"), "hardRejectBypass": bypass, "downgrades": downgrade},
            "overall": {"k": gated_hits, "n": gated_n, "rate": _rate(gated_hits, gated_n), "requiredHits": ev.required_hits(gated_n, ev.OVERALL_RECALL_FLOOR), "excludes": c3.LOW_VISIBILITY_FAMILY},
            "families": fam_t, "alphas": _table(alpha), "placements": _table(place), "sizes": _table(size),
            "lowVisibility": {"family": c3.LOW_VISIBILITY_FAMILY, "marker": c3.LOW_VISIBILITY_MARKER, **fam_t.get(c3.LOW_VISIBILITY_FAMILY, {"k": 0, "n": 0, "rate": None})},
            "survivingProposals": survivors_total, "criticalFamilyMinRecall": critical_min, "criteria": checks, "eligible": all(checks[c] for c in J_CRITERIA), "failed": [c for c in J_CRITERIA if not checks[c]]}


def flatten(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for rec in records:
        for p in rec["proposals"]:
            out.append({"proposalId": p["proposalId"], "opaqueId": rec["opaqueId"], "groupKey": rec["groupKey"], "label": p["label"], "embedding": p["embedding"], "source": p["source"]})
    return out


def label_counts(flat: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"positive": sum(1 for r in flat if r["label"] == "positive"), "negative": sum(1 for r in flat if r["label"] == "negative"), "ambiguousExcluded": sum(1 for r in flat if r["label"] == "ambiguous"),
            "bySource": {s: dict(Counter(r["label"] for r in flat if r["source"] == s)) for s in pv.PROPOSAL_GENERATORS}}


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def leakage_audit(flat: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out = {}
    for a, b, e in pv.FOLDS:
        pv.assert_group_disjoint((a, b), e, flat)
        out[f"{a}+{b}->{e}"] = {"trainBases": len({r["opaqueId"] for r in flat if r["groupKey"] in (a, b)}), "evalBases": len({r["opaqueId"] for r in flat if r["groupKey"] == e}), "disjoint": True}
    return out


def run(stage: str, capture_dir: Path, private_dir: Path, florence_rows, label_artifact) -> dict[str, Any]:
    digest = pv.contract_digest()
    base: dict[str, Any] = {"reportVersion": REPORT_VERSION, "version": pv.VERSION, "contractDigestPrefix": digest[:12], "priorStatus": pv.PRIOR_STATUS,
                            "markers": [pv.GEOMETRY_CLOSURE, pv.UNION_MARKER, pv.FACE_SUPPRESSION], "generators": pv.PROPOSAL_GENERATORS,
                            "detectors": {k: {kk: vv for kk, vv in v.items() if kk != "dir"} for k, v in det.CANDIDATES.items()}, "verifier": pv.VERIFIER, "crop": pv.CROP, "classifier": pv.CLASSIFIER,
                            "thresholdGrid": list(pv.THRESHOLD_GRID), "folds": [list(f) for f in pv.FOLDS], "watermarkPolicyChanged": False, "decisionDiff": 0, "holdoutEvaluated": 0}
    cov = coverage(capture_dir, "development")
    base["coverage"] = cov
    if stage == "coverage" or not cov["pass"]:
        base.update(pv.verdict(cov["pass"], None, None))
        base["diagnosis"] = pv.diagnosis(cov, [])
        base["gaps"] = ev.gap_markers(None)
        return base
    pv.require_coverage(cov)
    actions = ev.clean_actions(florence_rows)
    truth = {r["evaluationId"]: tpe.sel_truth(r) for r in label_artifact["labels"]}
    dev_records = _jsonl(capture_dir / "proposal_embeddings_development.jsonl")
    if not dev_records:
        raise SystemExit("DEVELOPMENT_EMBEDDINGS_MISSING")
    flat = flatten(dev_records)
    base["development"] = {"records": len(dev_records), "labels": label_counts(flat), "leakageAudit": leakage_audit(flat)}
    oof = pv.oof_scores(flat)
    table = [evaluate(dev_records, oof, t, actions, truth) for t in pv.THRESHOLD_GRID]
    selection = pv.select_threshold(table)
    base["development"].update({"evidence": "GROUP_OUT_OF_FOLD", "table": table, "selection": selection})
    if selection["status"] != "SELECTED":
        base.update(pv.verdict(True, False, None))
        base["diagnosis"] = pv.diagnosis(cov, table)
        base["gaps"] = ev.gap_markers(None)
        return base
    dev_digest = _digest([[r["proposalId"], r["label"]] for r in flat])
    marker = Path(private_dir) / pv.SELECTED_MARKER_NAME
    if marker.exists():
        frozen = pv.require_selected(private_dir, digest)
        if frozen["threshold"] != selection["threshold"]:
            raise pv.NotFrozen("selection differs from the frozen record")
    else:
        base["holdoutUnopenedAuditAtFreeze"] = pv.holdout_unopened_audit(capture_dir)
        pv.write_selected(private_dir, selection["threshold"], digest, dev_digest)
    base["selectedFrozen"] = {"threshold": selection["threshold"], "developmentInputsDigestPrefix": dev_digest[:12]}
    if stage != "holdout":
        base.update(pv.verdict(True, True, None))
        base["gaps"] = ev.gap_markers(None)
        return base
    hold_cov = coverage(capture_dir, "holdout")
    base["holdoutProvenance"] = {k: v["exact"] for k, v in hold_cov["provenance"].items()}
    if not hold_cov["provenanceExact"]:
        raise SystemExit("HOLDOUT_CAPTURE_PROVENANCE_MISMATCH")
    hold_records = _jsonl(capture_dir / "proposal_embeddings_holdout.jsonl")
    need_pos = len(c3.conditions(c3.HOLDOUT_VARIANT)) * len(c3.HOLDOUT_GROUPS)
    if sum(1 for r in hold_records if not r["clean"]) < need_pos or sum(1 for r in hold_records if r["clean"]) < 8:
        raise SystemExit("HOLDOUT_EMBEDDINGS_INCOMPLETE")
    lock = pv.holdout_guard(private_dir, digest)
    train = [r for r in flat if r["label"] in ("positive", "negative")]
    clf = pv.fit_classifier([r["embedding"] for r in train], [r["label"] for r in train])   # fit once on all G1-G3, frozen recipe
    hold_flat = flatten(hold_records)
    scores = dict(zip([r["proposalId"] for r in hold_flat], pv.score(clf, [r["embedding"] for r in hold_flat])))
    result = evaluate(hold_records, scores, selection["threshold"], actions, truth)
    ev.mark_holdout(lock, digest)
    base["holdoutEvaluated"] = 1
    base["holdoutCoverage"] = {k: hold_cov[k] for k in ("overall", "families", "pass", "failed")}
    base["holdout"] = result
    base["holdoutLabels"] = label_counts(hold_flat)
    base["holdoutRequiredHits"] = {"overall": result["overall"]["requiredHits"], **{f: ev.required_hits(result["families"][f]["n"], ev.FAMILY_RECALL_FLOOR) for f in J_FAMILY.values() if f in result["families"]}}
    base.update(pv.verdict(True, True, result["eligible"]))
    base["gaps"] = ev.gap_markers({"criteria": {"C": result["criteria"]["J3"], "D": result["criteria"]["J4"], "E": result["criteria"]["J5"], "F": result["criteria"]["J6"], "G": result["criteria"]["J7"],
                                                "H": result["criteria"]["J8"], "I": result["criteria"]["J9"], "J": result["criteria"]["J10"]}} if result["eligible"] else None)
    return base


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=("coverage", "development", "holdout"))
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--florence-rows", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--forbidden-strings", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    labels = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else {"labels": []}
    if args.stage != "coverage" and (not labels.get("complete") or labels.get("unresolvedCount")):
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
