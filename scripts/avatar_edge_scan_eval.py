"""B3-L15A evaluator (offline, aggregate-only, decision-neutral).

Stages (order enforced):
  ceiling      : frozen union OR scan proposal ceiling on l11_dev (B3-L13 broad gate A-I) and l14a_dev (B3-L14A edge gate) — no verifier
  development  : group OOF verifier scores -> table over the frozen grid (clean J1, broad J2-J12, edge gate) -> selection -> freeze
  stress       : KNOWN_CONSTRUCT_STRESS_GATE on l14a_holdout (existing detector captures + scan + new embeddings; classifier fit once on all G1-G3)
  holdout      : one-shot original B3-L11 G4-G5 + HOLDOUT_VARIANT behind the canonical visual_mark_detector_v1_holdout.lock

Only OOF scores enter the development table.  Ground truth is evaluation
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

import avatar_edge_mark_generalization as eg  # noqa: E402
import avatar_edge_scan_embed as em  # noqa: E402
import avatar_edge_scan_verifier as es  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_text_policy_shadow_eval as tpe  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402
import avatar_visual_mark_eval as ev  # noqa: E402

REPORT_VERSION = "avatar_edge_scan_eval_v1"
STAGES = ("ceiling", "development", "stress", "holdout")
COVERAGE_FAMILY = {"B": "TEXT_WATERMARK_OPAQUE", "C": "TEXT_WATERMARK_TRANSLUCENT_HIGH", "D": "TEXT_WATERMARK_TRANSLUCENT_MEDIUM", "E": "GRAPHICAL_WATERMARK_TRANSLUCENT",
                   "F": "LOGO_LIKE_EMBLEM", "G": "SMALL_CORNER_MARK", "H": "EDGE_MARK", "I": "CENTER_OVERLAY_MARK"}
BROAD_FAMILY = {"J3": "TEXT_WATERMARK_OPAQUE", "J4": "TEXT_WATERMARK_TRANSLUCENT_HIGH", "J5": "TEXT_WATERMARK_TRANSLUCENT_MEDIUM", "J6": "GRAPHICAL_WATERMARK_TRANSLUCENT",
                "J7": "LOGO_LIKE_EMBLEM", "J8": "SMALL_CORNER_MARK", "J9": "EDGE_MARK", "J10": "CENTER_OVERLAY_MARK"}
J_CRITERIA = ("J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8", "J9", "J10", "J11", "J12")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def _rate(k, n):
    return round(k / n, 4) if n else None


def _table(d: Mapping[str, list]) -> dict[str, dict[str, Any]]:
    return {k: {"k": sum(v), "n": len(v), "rate": _rate(sum(v), len(v))} for k, v in sorted(d.items())}


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ records


def capture_records(dataset: str, l11_dir: Path, l14a_dir: Path) -> list[dict[str, Any]]:
    """Proposal records straight from the detector captures (no embedding) for the ceiling stage."""

    spec = em.DATASETS[dataset]
    by_cond = em.load_rows(l11_dir if spec["dir"] == "l11" else l14a_dir, spec["prefix"], spec["split"])
    out = []
    for cid in sorted(by_cond):
        rows = by_cond[cid]
        any_row = next(iter(rows.values()))
        props = es.runtime_proposals({n: r["detections"] for n, r in rows.items()}, any_row["imageSize"])
        out.append({"conditionId": cid, "opaqueId": any_row["opaqueId"], "groupKey": any_row["groupKey"], "clean": cid.endswith(":CLEAN"), "dataset": dataset, "imageSize": any_row["imageSize"],
                    "groundTruth": any_row["groundTruth"], "meta": any_row.get("meta", {}), "proposals": [{"proposalId": f"{dataset}:{cid}#{k}", **p} for k, p in enumerate(props)]})
    return out


def embedding_records(private_dir: Path, dataset: str) -> list[dict[str, Any]]:
    return _jsonl(Path(private_dir) / f"edge_scan_embeddings_{dataset}.jsonl")


def flatten(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [{"proposalId": p["proposalId"], "opaqueId": r["opaqueId"], "groupKey": r["groupKey"], "dataset": r.get("dataset"), "label": p["label"], "embedding": p["embedding"], "source": p["source"]}
            for r in records for p in r["proposals"]]


def label_counts(flat: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"positive": sum(1 for r in flat if r["label"] == "positive"), "negative": sum(1 for r in flat if r["label"] == "negative"), "excluded": sum(1 for r in flat if r["label"] == "excluded"),
            "bySource": {s: dict(Counter(r["label"] for r in flat if r["source"] == s)) for s in sorted({r["source"] for r in flat})},
            "byDataset": {d: dict(Counter(r["label"] for r in flat if r["dataset"] == d)) for d in sorted({r["dataset"] for r in flat})}}


# ------------------------------------------------------------------ ceiling (no verifier)


def broad_ceiling(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fam: dict[str, list] = defaultdict(list)
    per_source: dict[str, Counter] = defaultdict(Counter)
    matched_by: Counter = Counter()
    gated_hits = gated_n = 0
    clean_props = []
    for rec in records:
        props = rec["proposals"]
        if rec["clean"]:
            clean_props.append(len(props))
            for p in props:
                per_source["clean"][p["source"]] += 1
            continue
        matches = [p for p in props if es.proposal_matches(p, rec["groundTruth"])]
        hit = bool(matches)
        for p in props:
            per_source["positive"][p["source"]] += 1
        if hit:
            matched_by["scan_only" if all(p["source"] == es.SCAN_SOURCE for p in matches) else ("detector_only" if all(p["source"] != es.SCAN_SOURCE for p in matches) else "both")] += 1
        m = rec["meta"]
        fam[m["family"]].append(hit)
        if not m.get("diagnostic"):
            gated_n += 1
            gated_hits += int(hit)
    fam_t = _table(fam)
    checks = {"A": gated_n > 0 and gated_hits >= ev.required_hits(gated_n, es.OVERALL_RECALL_FLOOR),
              **{c: (f in fam_t and fam_t[f]["k"] >= ev.required_hits(fam_t[f]["n"], es.FAMILY_RECALL_FLOOR) and fam_t[f]["n"] > 0) for c, f in COVERAGE_FAMILY.items()}}
    return {"overall": {"k": gated_hits, "n": gated_n, "rate": _rate(gated_hits, gated_n)}, "families": fam_t, "matchedBy": dict(matched_by),
            "cleanProposalsPerImage": {"n": len(clean_props), "total": sum(clean_props), "min": min(clean_props, default=0), "max": max(clean_props, default=0)},
            "proposalsBySource": {k: dict(v) for k, v in per_source.items()}, "criteria": checks, "pass": all(checks.values()), "failed": [k for k, v in checks.items() if not v]}


def edge_ceiling(records: Sequence[Mapping[str, Any]], variant: str) -> dict[str, Any]:
    cells: dict[str, list] = {c: [] for c in eg.cell_ids(variant)}
    matched_by: Counter = Counter()
    for rec in records:
        if rec["clean"]:
            continue
        matches = [p for p in rec["proposals"] if es.proposal_matches(p, rec["groundTruth"])]
        cells[rec["meta"]["cell"]].append(bool(matches))
        if matches:
            matched_by["scan_only" if all(p["source"] == es.SCAN_SOURCE for p in matches) else ("detector_only" if all(p["source"] != es.SCAN_SOURCE for p in matches) else "both")] += 1
    tables = eg.tables_from_hits(cells, variant)
    return {**tables, "gate": eg.gate(tables, variant), "matchedBy": dict(matched_by)}


# ------------------------------------------------------------------ verifier evaluation


def evaluate_broad(records: Sequence[Mapping[str, Any]], scores: Mapping[str, float], threshold: float, actions: Mapping[str, str], truth: Mapping[str, Optional[str]], holdout: bool = False) -> dict[str, Any]:
    order = {"allow": 0, "review": 1, "reject": 2}
    clean_rows = []
    new_review = bypass = downgrade = 0
    fam: dict[str, list] = defaultdict(list); alpha: dict[str, list] = defaultdict(list); place: dict[str, list] = defaultdict(list); size: dict[str, list] = defaultdict(list)
    gated_hits = gated_n = 0
    survivors_total = 0
    for rec in records:
        out = es.image_outcome(rec["proposals"], scores, threshold, rec["groundTruth"])
        survivors_total += out["survivors"]
        if rec["clean"]:
            if truth.get(rec["opaqueId"]) != "negative":
                continue
            canonical = actions.get(rec["opaqueId"])
            if canonical is None:
                continue
            action = es.shadow_action(canonical, out["response"])
            new_review += int(canonical == "allow" and action == "review")
            bypass += int(canonical == "reject" and action != "reject")
            downgrade += int(order[action] < order[canonical])
            clean_rows.append({"canonical": canonical, "hit": out["response"]})
            continue
        m = rec["meta"]
        fam[m["family"]].append(out["hit"]); alpha[m.get("alphaName")].append(out["hit"]); place[m.get("placementClass")].append(out["hit"]); size[m.get("sizeBand")].append(out["hit"])
        if not m.get("diagnostic"):
            gated_n += 1; gated_hits += int(out["hit"])
    n_clean = len(clean_rows)
    fam_t = _table(fam)
    j1 = n_clean > 0 and (new_review == 0 if holdout else new_review / n_clean <= es.NEW_REVIEW_CEILING)
    checks = {"J1": j1, "J2": gated_n > 0 and gated_hits >= ev.required_hits(gated_n, es.OVERALL_RECALL_FLOOR),
              **{c: (f in fam_t and fam_t[f]["n"] > 0 and fam_t[f]["k"] >= ev.required_hits(fam_t[f]["n"], es.FAMILY_RECALL_FLOOR)) for c, f in BROAD_FAMILY.items()}, "J11": bypass == 0, "J12": downgrade == 0}
    critical_min = min((fam_t[f]["rate"] for f in BROAD_FAMILY.values() if f in fam_t and fam_t[f]["rate"] is not None), default=None)
    return {"threshold": threshold, "scoreRole": es.SCORE_ROLE,
            "clean": {"n": n_clean, "canonical": dict(Counter(r["canonical"] for r in clean_rows)), "cleanImageResponse": sum(1 for r in clean_rows if r["hit"]), "newAllowToReview": new_review,
                      "newReviewRate": _rate(new_review, n_clean), "newReviewRateCI": calib.wilson(new_review, n_clean) if n_clean else None, "holdoutCleanCeiling": 0 if holdout else None,
                      "existingCanonicalBurdenNotCounted": sum(1 for r in clean_rows if r["canonical"] != "allow"), "hardRejectBypass": bypass, "downgrades": downgrade},
            "overall": {"k": gated_hits, "n": gated_n, "rate": _rate(gated_hits, gated_n), "requiredHits": ev.required_hits(gated_n, es.OVERALL_RECALL_FLOOR), "excludes": c3.LOW_VISIBILITY_FAMILY},
            "families": fam_t, "alphas": _table(alpha), "placements": _table(place), "sizes": _table(size),
            "requiredHits": {f: ev.required_hits(fam_t[f]["n"], es.FAMILY_RECALL_FLOOR) for f in BROAD_FAMILY.values() if f in fam_t},
            "lowVisibility": {"family": c3.LOW_VISIBILITY_FAMILY, "marker": c3.LOW_VISIBILITY_MARKER, **fam_t.get(c3.LOW_VISIBILITY_FAMILY, {"k": 0, "n": 0, "rate": None})},
            "survivingProposals": survivors_total, "criticalFamilyMinRecall": critical_min, "criteria": checks, "eligible": all(checks[c] for c in J_CRITERIA), "failed": [c for c in J_CRITERIA if not checks[c]]}


def evaluate_edge(records: Sequence[Mapping[str, Any]], scores: Mapping[str, float], threshold: float, variant: str) -> dict[str, Any]:
    cells: dict[str, list] = {c: [] for c in eg.cell_ids(variant)}
    survivors_total = 0
    for rec in records:
        if rec["clean"]:
            continue
        out = es.image_outcome(rec["proposals"], scores, threshold, rec["groundTruth"])
        survivors_total += out["survivors"]
        cells[rec["meta"]["cell"]].append(out["hit"])
    tables = eg.tables_from_hits(cells, variant)
    return {"threshold": threshold, **tables, "gate": eg.gate(tables, variant), "survivingProposals": survivors_total}


def development_row(threshold: float, broad: Mapping[str, Any], edge: Mapping[str, Any]) -> dict[str, Any]:
    cell_rates = [c["rate"] for c in edge["cells"].values() if c["rate"] is not None]
    fam_rates = [broad["families"][f]["rate"] for f in BROAD_FAMILY.values() if f in broad["families"] and broad["families"][f]["rate"] is not None]
    return {"threshold": threshold, "clean": broad["clean"], "criteria": broad["criteria"], "broadFamilies": broad["families"], "broadFailed": broad["failed"], "edge": edge,
            "minCriticalRecall": min(fam_rates + cell_rates, default=None), "broadOverall": broad["overall"]["rate"], "edgeOverall": edge["overall"]["rate"],
            "survivingProposals": {"broad": broad["survivingProposals"], "edge": edge["survivingProposals"]}, "eligible": bool(broad["eligible"] and edge["gate"]["pass"])}


# ------------------------------------------------------------------ final classifier (fit once on all G1-G3 after the freeze)


def final_classifier(private_dir: Path, flat: Sequence[Mapping[str, Any]], digest: str):
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    path = Path(private_dir) / es.FINAL_CLASSIFIER_NAME
    train = [r for r in flat if r["label"] in ("positive", "negative")]
    train_digest = _digest([[r["proposalId"], r["label"]] for r in train])
    if path.exists():
        rec = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("contractDigest") != digest or rec.get("trainingInputsDigest") != train_digest:
            raise es.NotFrozen("final classifier record does not match the frozen contract / development inputs")
        clf = LogisticRegression(penalty=es.CLASSIFIER["penalty"], C=es.CLASSIFIER["C"], solver=es.CLASSIFIER["solver"], class_weight=es.CLASSIFIER["class_weight"], max_iter=es.CLASSIFIER["max_iter"], random_state=es.CLASSIFIER["random_state"])
        clf.classes_ = np.asarray([0, 1]); clf.coef_ = np.asarray(rec["coef"], dtype=float); clf.intercept_ = np.asarray(rec["intercept"], dtype=float); clf.n_features_in_ = clf.coef_.shape[1]
        return clf, {"fits": 0, "trainingRows": len(train), "trainingInputsDigestPrefix": train_digest[:12], "reused": True}
    clf = es.fit_classifier([r["embedding"] for r in train], [r["label"] for r in train])
    path.write_text(json.dumps({"version": es.VERSION, "contractDigest": digest, "trainingInputsDigest": train_digest, "trainingRows": len(train), "classifier": es.CLASSIFIER,
                                "coef": [[float(v) for v in row] for row in clf.coef_], "intercept": [float(v) for v in clf.intercept_]}), encoding="utf-8")
    return clf, {"fits": 1, "trainingRows": len(train), "trainingInputsDigestPrefix": train_digest[:12], "reused": False}


# ------------------------------------------------------------------ run


def run(stage: str, private_dir: Path, l11_dir: Path, l14a_dir: Path, florence_rows, label_artifact) -> dict[str, Any]:
    digest = es.contract_digest()
    base: dict[str, Any] = {"reportVersion": REPORT_VERSION, "version": es.VERSION, "contractDigestPrefix": digest[:12], "scanDigestPrefix": es.scan_digest()[:12], "detectorSetDigestPrefix": det.contract_digest()[:12],
                            "priorStatus": es.PRIOR_STATUS, "markers": [es.SCAN_MARKER, es.ZERO_SHOT_LIMIT, es.CRITICAL_MARKER, es.STRESS_NAME], "scan": es.scan_definitions(), "generators": es.PROPOSAL_GENERATORS,
                            "thresholds": es.THRESHOLDS, "prompts": list(es.PROMPTS), "iouMatch": es.IOU_MATCH, "containmentAddedToDetectorMatch": es.CONTAINMENT_ADDED_TO_DETECTOR_MATCH,
                            "detectors": {k: {kk: vv for kk, vv in v.items() if kk != "dir"} for k, v in det.CANDIDATES.items()}, "verifier": es.VERIFIER, "crop": es.CROP, "classifier": es.CLASSIFIER,
                            "thresholdGrid": list(es.THRESHOLD_GRID), "folds": [list(f) for f in es.FOLDS], "labelsContract": {"unmatchedOnPositiveImage": es.UNMATCHED_POSITIVE_IMAGE_PROPOSALS},
                            "watermarkPolicyChanged": False, "decisionDiff": 0, "holdoutEvaluated": 0, "stressEvaluated": 0, "verifierEmbeddings": {}, "classifierFits": 0,
                            "newDetectorInference": {"development": 0, "stress": 0, "holdout": 0}, "gaps": ev.gap_markers(None), "interpretation": es.interpretation_note(), "stressDesignation": es.stress_designation(),
                            "l11HoldoutAuditNow": es.l11_holdout_unopened_audit(l11_dir, private_dir)}
    # ---- ceiling (no verifier; existing captures only)
    l11_records = capture_records("l11_dev", l11_dir, l14a_dir)
    l14a_records = capture_records("l14a_dev", l11_dir, l14a_dir)
    broad = broad_ceiling(l11_records)
    edge = edge_ceiling(l14a_records, eg.DEV_VARIANT)
    ceiling = {"broad": broad, "edge": edge, "pass": bool(broad["pass"] and edge["gate"]["pass"]), "scanTilesPerImage": len(es.scan_tiles(*l11_records[0]["imageSize"])) if l11_records else None,
               "records": {"l11_dev": len(l11_records), "l14a_dev": len(l14a_records)}}
    base["ceiling"] = ceiling
    if not ceiling["pass"]:
        base["verdict"] = es.verdict(False, None, None, None)
        base["diagnosis"] = es.diagnosis([], ceiling)
        return base
    marker = Path(private_dir) / es.CEILING_MARKER_NAME
    if not marker.exists():
        es.write_ceiling_passed(private_dir, digest, _digest([[r["conditionId"], len(r["proposals"])] for r in l11_records + l14a_records])[:12])
    if stage == "ceiling":
        base["verdict"] = "EDGE_SCAN_PROPOSAL_CEILING_PASSED_VERIFIER_PENDING"
        return base
    # ---- development (OOF)
    es.require_ceiling(ceiling)
    actions = ev.clean_actions(florence_rows)
    truth = {r["evaluationId"]: tpe.sel_truth(r) for r in label_artifact["labels"]}
    dev_l11 = embedding_records(private_dir, "l11_dev")
    dev_l14a = embedding_records(private_dir, "l14a_dev")
    if len(dev_l11) != len(l11_records) or len(dev_l14a) != len(l14a_records):
        raise SystemExit(f"DEVELOPMENT_EMBEDDINGS_INCOMPLETE l11={len(dev_l11)}/{len(l11_records)} l14a={len(dev_l14a)}/{len(l14a_records)}")
    flat = flatten(dev_l11 + dev_l14a)
    base["verifierEmbeddings"]["development"] = len(flat)
    base["development"] = {"records": {"l11_dev": len(dev_l11), "l14a_dev": len(dev_l14a)}, "labels": label_counts(flat), "leakageAudit": es.leakage_audit(flat), "evidence": es.DEVELOPMENT_EVIDENCE}
    oof = es.oof_scores(flat)
    base["classifierFits"] += len(es.FOLDS)
    table = [development_row(t, evaluate_broad(dev_l11, oof, t, actions, truth), evaluate_edge(dev_l14a, oof, t, eg.DEV_VARIANT)) for t in es.THRESHOLD_GRID]
    selection = es.select_threshold(table)
    base["development"].update({"table": table, "selection": selection})
    if selection["status"] != "SELECTED":
        base["verdict"] = es.verdict(True, False, None, None)
        base["diagnosis"] = es.diagnosis(table)
        return base
    dev_digest = _digest([[r["proposalId"], r["label"]] for r in flat])
    if (Path(private_dir) / es.SELECTED_MARKER_NAME).exists():
        frozen = es.require_selected(private_dir, digest)
        if frozen["threshold"] != selection["threshold"] or frozen["developmentInputsDigest"] != dev_digest:
            raise es.NotFrozen("selection differs from the frozen record")
    else:
        es.write_selected(private_dir, selection["threshold"], digest, dev_digest)
    base["selectedFrozen"] = {"threshold": selection["threshold"], "role": es.SELECTED_ROLE, "developmentInputsDigestPrefix": dev_digest[:12]}
    if stage == "development":
        base["verdict"] = es.verdict(True, True, None, None)
        return base
    # ---- final classifier + known-construct stress gate
    clf, fit_meta = final_classifier(private_dir, flat, digest)
    base["classifierFits"] += fit_meta["fits"]
    base["finalClassifier"] = fit_meta
    threshold = selection["threshold"]
    stress_path = Path(private_dir) / es.STRESS_RESULT_NAME
    stress_records = embedding_records(private_dir, es.STRESS_DATASET)
    need = len(eg.conditions(eg.HOLDOUT_VARIANT)) * eg.EXPECTED_BASES["holdout"]
    if len(stress_records) != need:
        raise SystemExit(f"STRESS_EMBEDDINGS_INCOMPLETE {len(stress_records)}/{need}")
    stress_flat = flatten(stress_records)
    base["verifierEmbeddings"]["stress"] = len(stress_flat)
    stress_scores = dict(zip([r["proposalId"] for r in stress_flat], es.score(clf, [r["embedding"] for r in stress_flat])))
    stress = evaluate_edge(stress_records, stress_scores, threshold, eg.HOLDOUT_VARIANT)
    stress["labels"] = label_counts(stress_flat)
    if stress_path.exists():
        prior = json.loads(stress_path.read_text(encoding="utf-8"))
        if prior.get("passed") != stress["gate"]["pass"]:
            raise es.NotFrozen("stress result differs from the recorded one-shot result")
    else:
        es.write_stress_result(private_dir, digest, passed=stress["gate"]["pass"])
    base["stressEvaluated"] = 1
    base["stress"] = stress
    if not stress["gate"]["pass"]:
        base["verdict"] = es.verdict(True, True, False, None)
        base["diagnosis"] = ["VERIFIER_REMOVES_TRUE_EDGE_MARKS"] if stress["gate"]["failed"] else []
        return base
    if stage == "stress":
        base["verdict"] = es.verdict(True, True, True, None)
        return base
    # ---- one-shot original B3-L11 holdout
    audit_path = Path(private_dir) / es.L11_AUDIT_NAME
    if not audit_path.exists():
        raise es.NotFrozen("original B3-L11 holdout requires the pre-capture unopened audit marker")
    base["l11HoldoutAuditBeforeCapture"] = json.loads(audit_path.read_text(encoding="utf-8"))["audit"]
    lock = es.holdout_guard(private_dir, l11_dir, digest)
    hold_records = embedding_records(private_dir, "l11_holdout")
    need_pos = len(c3.conditions(c3.HOLDOUT_VARIANT)) * len(c3.HOLDOUT_GROUPS)
    if sum(1 for r in hold_records if not r["clean"]) != need_pos or sum(1 for r in hold_records if r["clean"]) != 8:
        raise SystemExit("HOLDOUT_EMBEDDINGS_INCOMPLETE")
    prov = {}
    for name in es.PROPOSAL_GENERATORS:
        meta_path = l11_dir / f"run_meta_{name}_holdout.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        spec = det.CANDIDATES[name]
        prov[name] = {"revision": meta.get("revision") == spec["revision"], "variant": meta.get("variant") == c3.HOLDOUT_VARIANT, "originalsUnchanged": meta.get("originalsUnchanged") is True,
                      "constructDigest": meta.get("constructDigestPrefix") == c3.construct_digest()[:12], "detectorSetDigest": meta.get("contractDigestPrefix") == det.contract_digest()[:12]}
    if not all(all(v.values()) for v in prov.values()):
        raise SystemExit(f"HOLDOUT_CAPTURE_PROVENANCE_MISMATCH {prov}")
    hold_flat = flatten(hold_records)
    base["verifierEmbeddings"]["holdout"] = len(hold_flat)
    base["newDetectorInference"]["holdout"] = {name: need_pos + 8 for name in es.PROPOSAL_GENERATORS}
    hold_scores = dict(zip([r["proposalId"] for r in hold_flat], es.score(clf, [r["embedding"] for r in hold_flat])))
    result = evaluate_broad(hold_records, hold_scores, threshold, actions, truth, holdout=True)
    ev.mark_holdout(lock, digest)
    base["holdoutEvaluated"] = 1
    base["holdoutProvenanceExact"] = True
    base["holdout"] = result
    base["holdoutLabels"] = label_counts(hold_flat)
    base["holdoutRequiredHits"] = {"overall": result["overall"]["requiredHits"], **result["requiredHits"], "clean": "0/8"}
    base["verdict"] = es.verdict(True, True, True, result["eligible"])
    base["support"] = es.support(result["eligible"])
    base["gaps"] = ev.gap_markers({"criteria": {"C": result["criteria"]["J3"], "D": result["criteria"]["J4"], "E": result["criteria"]["J5"], "F": result["criteria"]["J6"], "G": result["criteria"]["J7"],
                                                "H": result["criteria"]["J8"], "I": result["criteria"]["J9"], "J": result["criteria"]["J10"]}} if result["eligible"] else None)
    if result["eligible"]:
        base["markers"].append(es.CEILING_CLOSED_MARKER)
    return base


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--l11-dir", type=Path, required=True)
    parser.add_argument("--l14a-dir", type=Path, required=True)
    parser.add_argument("--florence-rows", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--forbidden-strings", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    labels = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else {"labels": []}
    if args.stage != "ceiling" and (not labels.get("complete") or labels.get("unresolvedCount")):
        raise SystemExit("BLOCKED_HUMAN_LABELS_REQUIRED")
    florence = ev._jsonl(args.florence_rows) if args.florence_rows else []
    report = run(args.stage, args.private_dir, args.l11_dir, args.l14a_dir, florence, labels)
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
