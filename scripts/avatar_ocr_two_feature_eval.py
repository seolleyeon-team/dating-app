"""B3-L10B evaluator (offline, aggregate-only, decision-neutral).

Order: development table on G1-G3 (27 frozen candidates) -> selection ->
frozen rule -> feature-specific validation on G4-G5 exactly once (dual-feature
exposure audit must be clean) -> robustness challenge rows (new constructs,
local capture) evaluated with the frozen rule, never tuned.  No action is ever
computed from the features.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_florence_ceiling as bench  # noqa: E402
import avatar_ocr_score_separability as st  # noqa: E402
import avatar_ocr_score_separability_eval as ste  # noqa: E402
import avatar_ocr_two_feature as tf  # noqa: E402

REPORT_VERSION = "avatar_ocr_two_feature_eval_v1"


def _pairs(rows, group, split):
    picked = [r for r in rows if r["group"] == group and r["split"] == split and (group != "CLEAN" or r["truth"] == "negative")]
    return [tf.features(r["shadow"]) for r in picked if st.usable(r["shadow"])], picked


def split_table(rows, split: str, candidates: Sequence[tf.Candidate]) -> dict[str, Any]:
    clean, clean_rows = _pairs(rows, "CLEAN", split)
    opaque, opaque_rows = _pairs(rows, "TEXT_WATERMARK_OPAQUE", split)
    transl, transl_rows = _pairs(rows, "TEXT_WATERMARK_TRANSLUCENT", split)
    evaluated = clean_rows + opaque_rows + transl_rows
    coverage = sum(1 for r in evaluated if st.usable(r["shadow"])) / len(evaluated) if evaluated else 0.0
    calibrated = {r["shadow"].get("scoreCalibrated") for r in evaluated}
    diff = sum(1 for r in evaluated if st.usable(r["shadow"]) and
               tf.watermark_action_with_features(r["canonicalAction"], *tf.features(r["shadow"]), candidates[0]) != r["canonicalAction"])
    table = []
    for cand in candidates:
        m = tf.candidate_metrics(cand, clean, opaque, transl)
        m["eligibility"] = tf.eligible(m, coverage_rate=coverage, calibrated_flags=calibrated, decision_diff=diff)
        table.append(m)
    inv = {"clean": st.distribution([t for _, t in clean]), "opaque": st.distribution([t for _, t in opaque]), "translucent": st.distribution([t for _, t in transl])}
    return {"split": split, "n": {"clean": len(clean), "opaque": len(opaque), "translucent": len(transl)}, "coverageSingleRegion": round(coverage, 4),
            "scoreCalibratedFlags": sorted(str(c) for c in calibrated), "decisionDiff": diff, "outputTokenCountDistribution": inv, "table": table}


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def robustness_rows(capture_rows, label_by_code: Mapping[str, tuple[str, str]]):
    out = []
    for r in capture_rows:
        shadow = st.extract_shadow(r["tasks"])
        category, alpha_name = label_by_code[r["familyCode"]]
        item = {"category": category, "alphaName": alpha_name, "usable": st.usable(shadow), "scoreCalibrated": shadow.get("scoreCalibrated"),
                "canonicalAction": ste.tpe.canonical(r["tasks"], r["imageSize"])[0], "regionCount": shadow.get("regionCount")}
        if item["usable"]:
            item["score"], item["tokens"] = tf.features(shadow)
        out.append(item)
    return out


def run(rows, private_dir: Path, exposure_audit: Mapping[str, Any], robustness_capture=None) -> dict[str, Any]:
    digest = tf.contract_digest()
    dev = [r for r in rows if r["split"] == "development"]
    development = split_table(rows, "development", tf.CANDIDATES)
    selection = tf.select_candidate(development["table"])
    report: dict[str, Any] = {
        "reportVersion": REPORT_VERSION, "version": tf.VERSION, "evidenceLabel": tf.EVIDENCE_LABEL, "designation": tf.DESIGNATION,
        "contractDigestPrefix": digest[:12], "priorStatus": {k: (list(v) if isinstance(v, tuple) else v) for k, v in tf.PRIOR_STATUS.items()},
        "features": {"rawSequenceScore": {"role": tf.SCORE_FEATURE_ROLE, "scoreSource": st.SCORE_SOURCE, "scoreCalibrated": False, "direction": tf.SCORE_DIRECTION},
                     "outputTokenCount": {"role": tf.TOKEN_FEATURE_ROLE, "semantics": tf.TOKEN_COUNT_SEMANTICS, "direction": tf.TOKEN_DIRECTION}},
        "grid": {"scoreThresholds": list(tf.SCORE_THRESHOLDS), "scoreThresholdOrigin": "B3-L10A pre-registered quantile grid, reused verbatim", "tokenCaps": list(tf.TOKEN_CAPS), "candidates": len(tf.CANDIDATES)},
        "development": development, "selection": selection, "exposureAudit": dict(exposure_audit), "validationEvaluated": 0, "validationSplitName": tf.VALIDATION_SPLIT_NAME,
        "robustnessExecuted": False, "confidenceBandChanged": False, "watermarkPolicyChanged": False, "calibrationPerformed": False, "decisionDiff": development["decisionDiff"],
        "textPolicyGap": st.TEXT_POLICY_GAP_STATUS, "graphicalDetectorStudyRequired": st.GRAPHICAL_STUDY_MARKER, "naturalPositiveLimitation": st.NATURAL_POSITIVE_LIMITATION,
    }
    if selection["status"] != "SELECTED":
        report["verdict"] = tf.verdict(False, None, None, None)
        return report
    dev_inputs = _digest([[r["group"], r["canonicalAction"], r["shadow"]] for r in dev])
    if tf.frozen_path(private_dir).exists():
        frozen = tf.require_frozen(private_dir, digest)
        if frozen["selectedCandidate"] != selection["selectedCandidate"]:
            raise tf.RetuningRefused("selection differs from the frozen rule")
    else:
        tf.write_frozen(private_dir, selection, digest, dev_inputs)
        frozen = tf.require_frozen(private_dir, digest)
    cand = tf.frozen_candidate(frozen)
    report["frozenRule"] = {"candidate": cand.id, "predicate": cand.predicate, "role": tf.RULE_ROLE, "developmentInputsDigestPrefix": dev_inputs[:12], "notPolicyRule": True, "notConfidenceRule": True}
    audit_clean = exposure_audit.get("validationScoreValuesPreviouslySeen") is False and exposure_audit.get("validationTokenCountValuesPreviouslySeen") is False
    if not audit_clean:
        report["verdict"] = tf.verdict(True, False, None, None)
        return report
    result_path = Path(private_dir) / tf.VALIDATION_RESULT_NAME
    lock = Path(private_dir) / tf.VALIDATION_LOCK_NAME
    if lock.exists() and result_path.exists():
        prior = json.loads(result_path.read_text(encoding="utf-8"))
        if prior.get("contractDigest") != digest:
            raise tf.RuleNotFrozen("validation result belongs to another contract")
        validation_pass = bool(prior["validationPassed"])
        report["validation"] = prior.get("aggregate")
        report["validationEvaluated"] = 1
        report["validationReplayed"] = True
    else:
        lock = tf.validation_guard(private_dir, digest, exposure_audit)
        validation = split_table(rows, "holdout", [cand])
        tf.mark_validation_evaluated(lock, digest)
        validation_pass = bool(validation["table"][0]["eligibility"]["eligible"])
        result = tf.write_validation_result(private_dir, digest, validation_pass)
        result.write_text(json.dumps({"version": tf.VERSION, "contractDigest": digest, "validationPassed": validation_pass, "aggregate": validation}), encoding="utf-8")
        report["validation"] = validation
        report["validationEvaluated"] = 1
    report["validationVerdict"] = "FEATURE_SPECIFIC_VALIDATION_PASSED" if validation_pass else "FLORENCE_TWO_FEATURE_VALIDATION_FAILED"
    if not validation_pass or robustness_capture is None:
        report["verdict"] = tf.verdict(True, True, validation_pass, None)
        return report
    tf.require_validation_pass(private_dir, digest)
    label_by_code = {s.code: tuple(s.family.split(":")) for s in tf.robustness_specs()}
    rrows = robustness_rows(robustness_capture, label_by_code)
    usable_rows = [r for r in rrows if r["usable"]]
    diff = sum(1 for r in usable_rows if tf.watermark_action_with_features(r["canonicalAction"], r["score"], r["tokens"], cand) != r["canonicalAction"])
    rob = tf.robustness_metrics(cand, usable_rows, frozen=frozen, calibrated_flags={r["scoreCalibrated"] for r in rrows}, decision_diff=diff)
    rob["rows"] = {"captured": len(rrows), "usableSingleRegion": len(usable_rows), "regionCount": {str(k): v for k, v in sorted(Counter(r["regionCount"] for r in rrows).items())},
                   "nonSingleRegionCountedAsMiss": len(rrows) - len(usable_rows)}
    # a non-single-region row cannot satisfy the rule -> counted as a miss in the overall/category rates
    if rob["rows"]["nonSingleRegionCountedAsMiss"]:
        miss_rows = [dict(r, score=float("-inf"), tokens=10**9) for r in rrows if not r["usable"]]
        rob_all = tf.robustness_metrics(cand, usable_rows + miss_rows, frozen=frozen, calibrated_flags={r["scoreCalibrated"] for r in rrows}, decision_diff=diff)
        rob_all["rows"] = rob["rows"]
        rob = rob_all
    rob["tokenCountByCategory"] = {}
    for cat in sorted({tf.ROBUSTNESS_CATEGORY_OF.get(r["category"], r["category"]) for r in usable_rows}):
        rob["tokenCountByCategory"][cat] = st.distribution([r["tokens"] for r in usable_rows if tf.ROBUSTNESS_CATEGORY_OF.get(r["category"], r["category"]) == cat])
    rob["scoreByCategory"] = {cat: st.distribution([r["score"] for r in usable_rows if tf.ROBUSTNESS_CATEGORY_OF.get(r["category"], r["category"]) == cat]) for cat in rob["tokenCountByCategory"]}
    report["robustness"] = rob
    report["robustnessExecuted"] = True
    report["verdict"] = tf.verdict(True, True, True, rob["passed"])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--florence-rows", type=Path, required=True)
    parser.add_argument("--dev-text-rows", type=Path, required=True)
    parser.add_argument("--validation-text-rows", type=Path, required=True)
    parser.add_argument("--robustness-rows", type=Path)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--exposure-audit", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--forbidden-strings", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    if not labels.get("complete") or labels.get("unresolvedCount"):
        raise SystemExit("BLOCKED_HUMAN_LABELS_REQUIRED")
    exposure = json.loads(args.exposure_audit.read_text(encoding="utf-8"))
    rows = ste.build_rows(ste._jsonl(args.florence_rows), ste._jsonl(args.dev_text_rows), ste._jsonl(args.validation_text_rows), labels)
    robustness = ste._jsonl(args.robustness_rows) if args.robustness_rows else None
    report = run(rows, args.private_dir, exposure, robustness_capture=robustness)
    forbidden = [l.strip() for l in args.forbidden_strings.read_text(encoding="utf-8").splitlines() if l.strip()] if args.forbidden_strings and args.forbidden_strings.exists() else []
    text = json.dumps(report, indent=2, sort_keys=True)
    problems = bench.privacy_violations(report, forbidden)
    wording = [w for w in tf.FORBIDDEN_WORDING if w in text]
    if problems or wording:
        raise SystemExit(f"PRIVACY_OR_WORDING_VIOLATION {problems} {wording}")
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
