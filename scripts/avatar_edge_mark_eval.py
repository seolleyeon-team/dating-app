"""B3-L14A evaluator (offline, aggregate-only, decision-neutral; no verifier).

Stages (order enforced):
  freeze      : write the construct-frozen marker (contract digest + freeze commit) — must precede `decompose`
  decompose   : descriptive audit of the twelve B3-L13 EDGE_MARK development rows (frozen categories; cannot change this contract)
  development : union proposal ceiling on G1-G3 + EDGE_DEV_VARIANT -> gate A-I + per-cell J -> development-pass freeze
  holdout     : one-shot G4-G5 + EDGE_HOLDOUT_VARIANT behind edge_proposal_generalization_v1_holdout.lock

Ground truth is evaluation authority only; detectors never receive it.
Verifier embeddings / classifier fits are zero by construction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_edge_mark_capture as ec  # noqa: E402
import avatar_edge_mark_generalization as eg  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402
import avatar_visual_mark_eval as ev  # noqa: E402

REPORT_VERSION = "avatar_edge_mark_eval_v1"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def provenance(capture_dir: Path, split: str, name: str) -> dict[str, Any]:
    meta_path = capture_dir / f"{ec.RUN_META_PREFIX}{name}_{split}.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    spec = det.CANDIDATES[name]
    checks = {"revision": meta.get("revision") == spec["revision"], "repo": meta.get("repo") == spec["repo"], "license": meta.get("license") == spec["license"],
              "contractDigest": meta.get("contractDigestPrefix") == eg.contract_digest()[:12], "constructDigest": meta.get("constructDigestPrefix") == eg.construct_digest()[:12],
              "detectorSetDigest": meta.get("detectorSetDigestPrefix") == det.contract_digest()[:12],
              "variant": meta.get("variant") == (eg.DEV_VARIANT if split == "development" else eg.HOLDOUT_VARIANT), "originalsUnchanged": meta.get("originalsUnchanged") is True}
    return {"checks": checks, "exact": all(checks.values()), "peakRssGb": meta.get("peakRssGb")}


def evaluate(capture_dir: Path, split: str) -> dict[str, Any]:
    variant = eg.DEV_VARIANT if split == "development" else eg.HOLDOUT_VARIANT
    groups = eg.DEVELOPMENT_GROUPS if split == "development" else eg.HOLDOUT_GROUPS
    prov = {name: provenance(capture_dir, split, name) for name in eg.PROPOSAL_GENERATORS}
    by_cond: dict[str, dict[str, dict]] = {}
    for name in eg.PROPOSAL_GENERATORS:
        for r in _jsonl(capture_dir / f"{ec.CAPTURE_FILE_PREFIX}{name}_{split}.jsonl"):
            if r["groupKey"] not in groups or r["meta"].get("variant") != variant:
                raise SystemExit(f"CAPTURE_SPLIT_MISMATCH {split}")
            by_cond.setdefault(r["conditionId"], {})[name] = r
    expected_rows = len(eg.conditions(variant)) * eg.EXPECTED_BASES[split]
    complete = {name: sum(1 for rows in by_cond.values() if name in rows) for name in eg.PROPOSAL_GENERATORS}
    union_cells: dict[str, list] = {c: [] for c in eg.cell_ids(variant)}
    per_det_cells: dict[str, dict[str, list]] = {name: {c: [] for c in eg.cell_ids(variant)} for name in eg.PROPOSAL_GENERATORS}
    per_source: Counter = Counter()
    bases = set()
    for cid in sorted(by_cond):
        rows = by_cond[cid]
        if set(rows) != set(eg.PROPOSAL_GENERATORS):
            continue
        any_row = next(iter(rows.values()))
        cell = any_row["meta"]["cell"]
        truth = any_row["groundTruth"]
        bases.add(any_row["opaqueId"])
        props = eg.union_proposals({n: r["detections"] for n, r in rows.items()}, any_row["imageSize"])
        for p in props:
            per_source[p["source"]] += 1
        union_cells[cell].append(eg.union_hit(props, truth))
        for name in eg.PROPOSAL_GENERATORS:
            single = eg.union_proposals({name: rows[name]["detections"]}, any_row["imageSize"])
            per_det_cells[name][cell].append(eg.union_hit(single, truth))
    tables = eg.tables_from_hits(union_cells, variant)
    g = eg.gate(tables, variant)
    return {"split": split, "variant": variant, "provenance": prov, "provenanceExact": all(p["exact"] for p in prov.values()), "bases": len(bases), "expectedBases": eg.EXPECTED_BASES[split],
            "rowsPerDetector": complete, "expectedRows": expected_rows, "complete": all(v == expected_rows for v in complete.values()) and len(bases) == eg.EXPECTED_BASES[split],
            **tables, "gate": g, "proposalsBySource": dict(per_source), "perDetector": {name: eg.tables_from_hits(per_det_cells[name], variant) for name in eg.PROPOSAL_GENERATORS},
            "inputsDigest": _digest([[cid, sorted(rows)] for cid, rows in sorted(by_cond.items())])[:12]}


def decompose(b3l11_dir: Path, private_dir: Path) -> dict[str, Any]:
    """Descriptive audit of the B3-L13 EDGE_MARK development rows (B3-L11 captures) into frozen categories.

    Runs only after the EDGE_MARK_GENERALIZATION_V1 construct is frozen and committed; its output cannot
    change the B3-L14A construct, gate, IoU rule or thresholds (it is reported, never acted on).
    """

    frozen = eg.require_construct_frozen(private_dir, eg.contract_digest())
    by_cond: dict[str, dict[str, dict]] = {}
    for name in eg.PROPOSAL_GENERATORS:
        for r in _jsonl(Path(b3l11_dir) / f"capture_{name}_development.jsonl"):
            if not r["conditionId"].endswith(":CLEAN") and r["meta"].get("family") == "EDGE_MARK":
                by_cond.setdefault(r["conditionId"], {})[name] = r
    per_det: dict[str, Counter] = {name: Counter() for name in eg.PROPOSAL_GENERATORS}
    union_cat: Counter = Counter()
    union_band: Counter = Counter()
    union_hits = 0
    for cid, rows in sorted(by_cond.items()):
        if set(rows) != set(eg.PROPOSAL_GENERATORS):
            continue
        any_row = next(iter(rows.values()))
        truth, size = any_row["groundTruth"], any_row["imageSize"]
        props = eg.union_proposals({n: r["detections"] for n, r in rows.items()}, size)
        if eg.union_hit(props, truth):
            union_hits += 1
            continue
        cats = {}
        for name in eg.PROPOSAL_GENERATORS:
            cats[name] = eg.classify_miss(name, rows[name]["detections"], truth, size)
            per_det[name][cats[name]] += 1
        # union category = most informative across detectors (frozen priority)
        priority = ("FULL_FRAME_FILTER_EFFECT", "PROPOSAL_WRONG_LABEL_ONLY", "OTHER", "LOCALIZATION_MISS_IOU_BELOW_030", "NO_RELEVANT_PROPOSAL")
        union_cat[next(c for c in priority if c in cats.values())] += 1
        best = max((bench.iou(p["box"], t["box"]) for p in props for t in truth), default=0.0)
        union_band[eg.iou_band(best)] += 1
    # per-detector misses among all 12 rows (a detector that hit contributes nothing to its counter)
    return {"rows": len(by_cond), "unionHits": union_hits, "unionMisses": sum(union_cat.values()), "unionMissCategories": dict(union_cat), "unionBestIouBandOnMisses": dict(union_band),
            "perDetectorMissCategories": {n: dict(c) for n, c in per_det.items()}, "categories": list(eg.DECOMPOSITION_CATEGORIES), "constructFrozenCommit": frozen["freezeCommit"],
            "cannotChange": ["construct", "gate", "iouMatch", "thresholds", "prompts", "inset", "sizes", "geometries"]}


def run(stage: str, capture_dir: Path, private_dir: Path, b3l11_dir: Path, freeze_commit: Optional[str] = None) -> dict[str, Any]:
    digest = eg.contract_digest()
    base: dict[str, Any] = {"reportVersion": REPORT_VERSION, "version": eg.VERSION, "contractDigestPrefix": digest[:12], "constructDigestPrefix": eg.construct_digest()[:12],
                            "detectorSetDigestPrefix": det.contract_digest()[:12], "priorStatus": eg.PRIOR_STATUS, "markers": [eg.CRITICAL_MARKER, eg.VERIFIER_PROHIBITED],
                            "construct": eg.definitions(), "generators": eg.PROPOSAL_GENERATORS, "thresholds": eg.THRESHOLDS, "prompts": list(eg.PROMPTS), "iouMatch": eg.IOU_MATCH,
                            "containmentClause": eg.CONTAINMENT_CLAUSE, "floors": {"overall": eg.OVERALL_FLOOR, "axis": eg.AXIS_FLOOR}, "expected": eg.expected_counts(eg.EXPECTED_BASES["development"], eg.EXPECTED_BASES["holdout"]),
                            "detectors": {k: {kk: vv for kk, vv in v.items() if kk != "dir"} for k, v in det.CANDIDATES.items()},
                            "verifierEmbeddings": eg.EXPECTED_VERIFIER_EMBEDDINGS, "classifierFits": eg.EXPECTED_CLASSIFIER_FITS, "watermarkPolicyChanged": False, "decisionDiff": 0,
                            "holdoutEvaluated": 0, "l11HoldoutAudit": eg.l11_holdout_untouched_audit(b3l11_dir), "gaps": ev.gap_markers(None), "nextStepIsNotRetuning": True}
    if stage == "freeze":
        if not freeze_commit:
            raise SystemExit("FREEZE_COMMIT_REQUIRED")
        eg.write_construct_frozen(private_dir, digest, freeze_commit)
        frozen = eg.require_construct_frozen(private_dir, digest)
        base["constructFrozen"] = {"freezeCommit": frozen["freezeCommit"], "contractDigestPrefix": frozen["contractDigest"][:12], "constructDigestPrefix": frozen["constructDigest"][:12], "frozenAt": frozen["frozenAt"]}
        return base
    if stage == "decompose":
        base["b3l13EdgeMissDecomposition"] = decompose(b3l11_dir, private_dir)
        return base
    dev = evaluate(capture_dir, "development")
    if not dev["complete"]:
        raise SystemExit(f"DEVELOPMENT_CAPTURE_INCOMPLETE {dev['rowsPerDetector']} bases={dev['bases']}")
    if not dev["provenanceExact"]:
        raise SystemExit("DEVELOPMENT_CAPTURE_PROVENANCE_MISMATCH")
    base["development"] = dev
    if not dev["gate"]["pass"]:
        if stage == "holdout":
            raise eg.NotFrozen("holdout inaccessible: the development gate did not pass (no retuning, STOP)")
        base["verdict"] = eg.verdict(False, None)
        base["interpretation"] = eg.interpretation(False, None, eg.sensitivity_markers(dev["gate"]))
        return base
    marker = Path(private_dir) / eg.DEV_PASS_MARKER_NAME
    if marker.exists():
        frozen = eg.require_dev_passed(private_dir, digest)
        if frozen["developmentInputsDigest"] != dev["inputsDigest"]:
            raise eg.NotFrozen("development inputs differ from the frozen record")
    else:
        eg.write_dev_passed(private_dir, digest, dev["inputsDigest"])
    base["developmentPassFrozen"] = {"developmentInputsDigestPrefix": dev["inputsDigest"]}
    if stage != "holdout":
        base["verdict"] = eg.verdict(True, None)
        base["interpretation"] = eg.interpretation(True, None)
        return base
    lock = eg.holdout_guard(private_dir, digest)
    hold = evaluate(capture_dir, "holdout")
    if not hold["complete"]:
        raise SystemExit(f"HOLDOUT_CAPTURE_INCOMPLETE {hold['rowsPerDetector']} bases={hold['bases']}")
    if not hold["provenanceExact"]:
        raise SystemExit("HOLDOUT_CAPTURE_PROVENANCE_MISMATCH")
    eg.mark_holdout(lock, digest)
    base["holdoutEvaluated"] = 1
    base["holdout"] = hold
    base["holdoutName"] = eg.HOLDOUT_NAME
    base["verdict"] = eg.verdict(True, hold["gate"]["pass"])
    base["interpretation"] = eg.interpretation(True, hold["gate"]["pass"], eg.sensitivity_markers(hold["gate"]))
    return base


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=("freeze", "decompose", "development", "holdout"))
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--b3l11-dir", type=Path, required=True)
    parser.add_argument("--freeze-commit")
    parser.add_argument("--forbidden-strings", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    report = run(args.stage, args.capture_dir, args.private_dir, args.b3l11_dir, args.freeze_commit)
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
