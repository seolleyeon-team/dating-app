"""B3-L16A evaluator (offline, aggregate-only, decision-neutral).

Stages: freeze (marker with the freeze commit) -> development (OOF over the frozen grid, B3-L15A gates and selection)
        -> stress (KNOWN_CONSTRUCT_STRESS_GATE on l14a_holdout, final classifier fit once) -> holdout (one-shot original B3-L11).
The proposal ceiling is the immutable B3-L15A result and is re-verified from the same captures for provenance only.
Broad / edge evaluators are the B3-L15A functions unchanged; only the embedding files differ.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_dinov2_verifier as dv  # noqa: E402
import avatar_edge_mark_generalization as eg  # noqa: E402
import avatar_edge_scan_eval as se  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_text_policy_shadow_eval as tpe  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402
import avatar_visual_mark_eval as ev  # noqa: E402

REPORT_VERSION = "avatar_dinov2_eval_v1"
STAGES = ("freeze", "development", "stress", "holdout")
BROAD_FAMILY = se.BROAD_FAMILY
evaluate_broad = se.evaluate_broad
evaluate_edge = se.evaluate_edge
development_row = se.development_row
flatten = se.flatten
label_counts = se.label_counts


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def embedding_records(private_dir: Path, dataset: str) -> list[dict[str, Any]]:
    return _jsonl(Path(private_dir) / f"{dv.EMBEDDINGS_PREFIX}{dataset}.jsonl")


def final_classifier(private_dir: Path, flat: Sequence[Mapping[str, Any]], digest: str):
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    path = Path(private_dir) / dv.FINAL_CLASSIFIER_NAME
    train = [r for r in flat if r["label"] in ("positive", "negative")]
    train_digest = _digest([[r["proposalId"], r["label"]] for r in train])
    if path.exists():
        rec = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("contractDigest") != digest or rec.get("trainingInputsDigest") != train_digest:
            raise dv.NotFrozen("final classifier record does not match the frozen contract / development inputs")
        clf = LogisticRegression(penalty=dv.CLASSIFIER["penalty"], C=dv.CLASSIFIER["C"], solver=dv.CLASSIFIER["solver"], class_weight=dv.CLASSIFIER["class_weight"], max_iter=dv.CLASSIFIER["max_iter"], random_state=dv.CLASSIFIER["random_state"])
        clf.classes_ = np.asarray([0, 1]); clf.coef_ = np.asarray(rec["coef"], dtype=float); clf.intercept_ = np.asarray(rec["intercept"], dtype=float); clf.n_features_in_ = clf.coef_.shape[1]
        return clf, {"fits": 0, "trainingRows": len(train), "trainingInputsDigestPrefix": train_digest[:12], "reused": True}
    clf = dv.fit_classifier([r["embedding"] for r in train], [r["label"] for r in train])
    path.write_text(json.dumps({"version": dv.VERSION, "contractDigest": digest, "trainingInputsDigest": train_digest, "trainingRows": len(train), "classifier": dv.CLASSIFIER,
                                "coef": [[float(v) for v in row] for row in clf.coef_], "intercept": [float(v) for v in clf.intercept_]}), encoding="utf-8")
    return clf, {"fits": 1, "trainingRows": len(train), "trainingInputsDigestPrefix": train_digest[:12], "reused": False}


def run(stage: str, private_dir: Path, l11_dir: Path, l14a_dir: Path, l15a_aggregate: Mapping[str, Any], florence_rows, label_artifact, freeze_commit: Optional[str] = None) -> dict[str, Any]:
    digest = dv.contract_digest()
    base: dict[str, Any] = {"reportVersion": REPORT_VERSION, "version": dv.VERSION, "contractDigestPrefix": digest[:12], "proposalContractDigestPrefix": dv.PROPOSAL_CONTRACT_DIGEST_PREFIX,
                            "scanDigestPrefix": dv.SCAN_DIGEST_PREFIX, "detectorSetDigestPrefix": det.contract_digest()[:12], "priorStatus": dv.PRIOR_STATUS,
                            "markers": [dv.PROPOSAL_FREEZE_MARKER, dv.SCAN_ONLY_REJECT, dv.STOP_RULE, dv.CRITICAL_MARKER, dv.STRESS_NAME], "scanOnlyRejection": dv.scan_only_dominance(l15a_aggregate),
                            "verifier": dv.VERIFIER, "preprocessing": dv.PREPROCESSING, "crop": dv.CROP, "classifier": dv.CLASSIFIER, "thresholdGrid": list(dv.THRESHOLD_GRID), "folds": [list(f) for f in dv.FOLDS],
                            "candidates": list(dv.REPRESENTATION_CANDIDATES), "nonLinearHeadsProhibited": list(dv.NON_LINEAR_HEADS_PROHIBITED), "noSearch": list(dv.NO_SEARCH),
                            "proposalCeiling": {"source": "B3-L15A immutable", "broadOverall": l15a_aggregate["ceiling"]["broad"]["overall"], "edgeMark": l15a_aggregate["ceiling"]["broad"]["families"]["EDGE_MARK"],
                                                "edgeOverall": l15a_aggregate["ceiling"]["edge"]["overall"], "pass": l15a_aggregate["ceiling"]["pass"]},
                            "watermarkPolicyChanged": False, "decisionDiff": 0, "holdoutEvaluated": 0, "stressEvaluated": 0, "verifierEmbeddings": {}, "classifierFits": 0,
                            "newDetectorInference": {"development": 0, "stress": 0, "holdout": 0}, "gaps": ev.gap_markers(None), "interpretation": dv.interpretation_note(),
                            "stressDesignation": dv.stress_designation(), "failureEscalation": dv.failure_escalation(), "l11HoldoutAuditNow": dv.l11_holdout_unopened_audit(l11_dir, private_dir)}
    if stage == "freeze":
        if not freeze_commit:
            raise SystemExit("FREEZE_COMMIT_REQUIRED")
        dv.write_frozen(private_dir, digest, freeze_commit)
        f = dv.require_frozen(private_dir, digest)
        base["frozen"] = {"freezeCommit": f["freezeCommit"], "contractDigestPrefix": f["contractDigest"][:12], "frozenAt": f["frozenAt"]}
        base["verdict"] = "DINOV2_VERIFIER_FROZEN_EMBEDDING_PENDING"
        return base
    dv.require_frozen(private_dir, digest)
    # proposal ceiling re-verified from the same captures (provenance only; immutable B3-L15A result)
    l11_records = se.capture_records("l11_dev", l11_dir, l14a_dir)
    l14a_records = se.capture_records("l14a_dev", l11_dir, l14a_dir)
    broad = se.broad_ceiling(l11_records)
    edge = se.edge_ceiling(l14a_records, eg.DEV_VARIANT)
    base["proposalCeiling"]["reVerified"] = {"broadOverall": broad["overall"], "edgeMark": broad["families"]["EDGE_MARK"], "edgeOverall": edge["overall"],
                                             "identicalToB3L15A": broad["overall"] == l15a_aggregate["ceiling"]["broad"]["overall"] and edge["overall"] == l15a_aggregate["ceiling"]["edge"]["overall"]}
    if not base["proposalCeiling"]["reVerified"]["identicalToB3L15A"]:
        raise SystemExit("PROPOSAL_CEILING_DRIFT")
    actions = ev.clean_actions(florence_rows)
    truth = {r["evaluationId"]: tpe.sel_truth(r) for r in label_artifact["labels"]}
    dev_l11 = embedding_records(private_dir, "l11_dev")
    dev_l14a = embedding_records(private_dir, "l14a_dev")
    if len(dev_l11) != len(l11_records) or len(dev_l14a) != len(l14a_records):
        raise SystemExit(f"DEVELOPMENT_EMBEDDINGS_INCOMPLETE l11={len(dev_l11)}/{len(l11_records)} l14a={len(dev_l14a)}/{len(l14a_records)}")
    if not all(r.get("proposalProvenanceExact") for r in dev_l11 + dev_l14a):
        raise SystemExit("PROPOSAL_PROVENANCE_NOT_EXACT")
    flat = flatten(dev_l11 + dev_l14a)
    base["verifierEmbeddings"]["development"] = len(flat)
    base["development"] = {"records": {"l11_dev": len(dev_l11), "l14a_dev": len(dev_l14a)}, "proposalProvenance": "B3-L15A exact (ids, sources, boxes, labels)", "labels": label_counts(flat),
                           "leakageAudit": dv.leakage_audit(flat), "evidence": dv.DEVELOPMENT_EVIDENCE, "embeddingDim": len(flat[0]["embedding"]) if flat else None}
    oof = dv.oof_scores(flat)
    base["classifierFits"] += len(dv.FOLDS)
    table = [development_row(t, evaluate_broad(dev_l11, oof, t, actions, truth), evaluate_edge(dev_l14a, oof, t, eg.DEV_VARIANT)) for t in dv.THRESHOLD_GRID]
    selection = dv.select_threshold(table)
    base["development"].update({"table": table, "selection": selection})
    if selection["status"] != "SELECTED":
        base["verdict"] = dv.verdict(False, None, None)
        base["diagnosis"] = dv.diagnosis(table)
        base["stopRuleApplied"] = dv.failure_escalation()
        return base
    dev_digest = _digest([[r["proposalId"], r["label"]] for r in flat])
    if (Path(private_dir) / dv.SELECTED_MARKER_NAME).exists():
        frozen = dv.require_selected(private_dir, digest)
        if frozen["threshold"] != selection["threshold"] or frozen["developmentInputsDigest"] != dev_digest:
            raise dv.NotFrozen("selection differs from the frozen record")
    else:
        dv.write_selected(private_dir, selection["threshold"], digest, dev_digest)
    base["selectedFrozen"] = {"threshold": selection["threshold"], "role": dv.SELECTED_ROLE, "developmentInputsDigestPrefix": dev_digest[:12]}
    if stage == "development":
        base["verdict"] = dv.verdict(True, None, None)
        return base
    clf, fit_meta = final_classifier(private_dir, flat, digest)
    base["classifierFits"] += fit_meta["fits"]
    base["finalClassifier"] = fit_meta
    threshold = selection["threshold"]
    stress_records = embedding_records(private_dir, dv.STRESS_DATASET)
    need = len(eg.conditions(eg.HOLDOUT_VARIANT)) * eg.EXPECTED_BASES["holdout"]
    if len(stress_records) != need:
        raise SystemExit(f"STRESS_EMBEDDINGS_INCOMPLETE {len(stress_records)}/{need}")
    stress_flat = flatten(stress_records)
    base["verifierEmbeddings"]["stress"] = len(stress_flat)
    stress_scores = dict(zip([r["proposalId"] for r in stress_flat], dv.score(clf, [r["embedding"] for r in stress_flat])))
    stress = evaluate_edge(stress_records, stress_scores, threshold, eg.HOLDOUT_VARIANT)
    stress["labels"] = label_counts(stress_flat)
    stress_path = Path(private_dir) / dv.STRESS_RESULT_NAME
    if stress_path.exists():
        if json.loads(stress_path.read_text(encoding="utf-8")).get("passed") != stress["gate"]["pass"]:
            raise dv.NotFrozen("stress result differs from the recorded one-shot result")
    else:
        dv.write_stress_result(private_dir, digest, passed=stress["gate"]["pass"])
    base["stressEvaluated"] = 1
    base["stress"] = stress
    if not stress["gate"]["pass"]:
        base["verdict"] = dv.verdict(True, False, None)
        return base
    if stage == "stress":
        base["verdict"] = dv.verdict(True, True, None)
        return base
    audit_path = Path(private_dir) / dv.L11_AUDIT_NAME
    if not audit_path.exists():
        raise dv.NotFrozen("original B3-L11 holdout requires the pre-capture unopened audit marker")
    base["l11HoldoutAuditBeforeCapture"] = json.loads(audit_path.read_text(encoding="utf-8"))["audit"]
    lock = dv.holdout_guard(private_dir, l11_dir, digest)
    hold_records = embedding_records(private_dir, "l11_holdout")
    need_pos = len(c3.conditions(c3.HOLDOUT_VARIANT)) * len(c3.HOLDOUT_GROUPS)
    if sum(1 for r in hold_records if not r["clean"]) != need_pos or sum(1 for r in hold_records if r["clean"]) != 8:
        raise SystemExit("HOLDOUT_EMBEDDINGS_INCOMPLETE")
    prov = {}
    for name in dv.runtime_proposals.__globals__["PROPOSAL_GENERATORS"]:
        meta_path = l11_dir / f"run_meta_{name}_holdout.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        spec = det.CANDIDATES[name]
        prov[name] = {"revision": meta.get("revision") == spec["revision"], "variant": meta.get("variant") == c3.HOLDOUT_VARIANT, "originalsUnchanged": meta.get("originalsUnchanged") is True,
                      "constructDigest": meta.get("constructDigestPrefix") == c3.construct_digest()[:12], "detectorSetDigest": meta.get("contractDigestPrefix") == det.contract_digest()[:12]}
    if not all(all(v.values()) for v in prov.values()):
        raise SystemExit(f"HOLDOUT_CAPTURE_PROVENANCE_MISMATCH {prov}")
    hold_flat = flatten(hold_records)
    base["verifierEmbeddings"]["holdout"] = len(hold_flat)
    base["newDetectorInference"]["holdout"] = {name: need_pos + 8 for name in prov}
    hold_scores = dict(zip([r["proposalId"] for r in hold_flat], dv.score(clf, [r["embedding"] for r in hold_flat])))
    result = evaluate_broad(hold_records, hold_scores, threshold, actions, truth, holdout=True)
    ev.mark_holdout(lock, digest)
    base["holdoutEvaluated"] = 1
    base["holdoutProvenanceExact"] = True
    base["holdout"] = result
    base["holdoutLabels"] = label_counts(hold_flat)
    base["holdoutRequiredHits"] = {"overall": result["overall"]["requiredHits"], **result["requiredHits"], "clean": "0/8"}
    base["verdict"] = dv.verdict(True, True, result["eligible"])
    base["support"] = dv.support(result["eligible"])
    base["gaps"] = ev.gap_markers({"criteria": {"C": result["criteria"]["J3"], "D": result["criteria"]["J4"], "E": result["criteria"]["J5"], "F": result["criteria"]["J6"], "G": result["criteria"]["J7"],
                                                "H": result["criteria"]["J8"], "I": result["criteria"]["J9"], "J": result["criteria"]["J10"]}} if result["eligible"] else None)
    if result["eligible"]:
        base["markers"].append("EDGE_PROPOSAL_CEILING_GAP_CLOSED_BY_DETERMINISTIC_SCAN")
    return base


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--l11-dir", type=Path, required=True)
    parser.add_argument("--l14a-dir", type=Path, required=True)
    parser.add_argument("--l15a-aggregate", type=Path, required=True)
    parser.add_argument("--florence-rows", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--freeze-commit")
    parser.add_argument("--forbidden-strings", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    labels = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else {"labels": []}
    if args.stage != "freeze" and (not labels.get("complete") or labels.get("unresolvedCount")):
        raise SystemExit("BLOCKED_HUMAN_LABELS_REQUIRED")
    florence = ev._jsonl(args.florence_rows) if args.florence_rows else []
    l15a = json.loads(args.l15a_aggregate.read_text(encoding="utf-8"))
    report = run(args.stage, args.private_dir, args.l11_dir, args.l14a_dir, l15a, florence, labels, args.freeze_commit)
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
