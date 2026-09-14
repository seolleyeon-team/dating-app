"""B3-L10A evaluator: Florence beam sequence score separability (offline, aggregate-only).

Inputs are the existing restricted captures (B3-L4 clean V0 rows, B3-L8
development text rows, B3-L9 validation text rows) which already carry the
PR #100 shadow telemetry -> 0 new inference.  Order: development inventory ->
frozen quantile grid -> development table -> selection -> frozen threshold ->
feature-specific validation exactly once, only if the exposure audit says the
validation score values were never displayed or analysed before the freeze.
No watermark action is ever computed from the score.
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
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_text_policy_shadow_eval as tpe  # noqa: E402

REPORT_VERSION = "avatar_ocr_score_separability_eval_v1"
FAMILY_BY_CODE = {"F3": "TEXT_WATERMARK_OPAQUE", "F4": "TEXT_WATERMARK_TRANSLUCENT"}


def build_rows(florence_rows, dev_text_rows, val_text_rows, label_artifact):
    labels = {r["evaluationId"]: r for r in label_artifact["labels"]}
    rows = []
    for r in florence_rows:
        if r.get("domain") != bench.DOMAIN_AVATAR or r.get("variant") != "V0":
            continue
        rows.append({"group": "CLEAN", "split": calib._split(r.get("groupKey")), "truth": tpe.sel_truth(labels.get(r["baseOpaqueId"], {})),
                     "shadow": st.extract_shadow(r["tasks"]), "canonicalAction": tpe.canonical(r["tasks"], r["imageSize"])[0]})
    for src in (dev_text_rows, val_text_rows):
        for r in src:
            if r["familyCode"] not in FAMILY_BY_CODE:
                continue
            rows.append({"group": FAMILY_BY_CODE[r["familyCode"]], "split": r["split"], "truth": "positive",
                         "shadow": st.extract_shadow(r["tasks"]), "canonicalAction": tpe.canonical(r["tasks"], r["imageSize"])[0]})
    return rows


def _scores(rows, group, split):
    picked = [r for r in rows if r["group"] == group and r["split"] == split and (group != "CLEAN" or r["truth"] == "negative")]
    return [st.score_of(r["shadow"]) for r in picked if st.usable(r["shadow"])], picked


def split_eval(rows, split: str, direction: str, thresholds: Sequence[float]) -> dict[str, Any]:
    clean, clean_rows = _scores(rows, "CLEAN", split)
    opaque, opaque_rows = _scores(rows, "TEXT_WATERMARK_OPAQUE", split)
    transl, transl_rows = _scores(rows, "TEXT_WATERMARK_TRANSLUCENT", split)
    evaluated = clean_rows + opaque_rows + transl_rows
    coverage = sum(1 for r in evaluated if st.usable(r["shadow"])) / len(evaluated) if evaluated else 0.0
    calibrated = {r["shadow"].get("scoreCalibrated") for r in evaluated}
    # decision neutrality: the study returns the canonical action for every row regardless of score
    diff = sum(1 for r in evaluated if st.usable(r["shadow"]) and
               st.watermark_action_with_score(r["canonicalAction"], st.score_of(r["shadow"]), thresholds[0] if thresholds else 0.0, direction) != r["canonicalAction"])
    table = []
    for t in thresholds:
        m = st.threshold_metrics(t, direction, clean, opaque, transl)
        m["eligibility"] = st.eligible(m, coverage_rate=coverage, calibrated_flags=calibrated, decision_diff=diff)
        table.append(m)
    return {"split": split, "n": {"clean": len(clean), "opaque": len(opaque), "translucent": len(transl)},
            "coverageSingleRegion": round(coverage, 4), "scoreCalibratedFlags": sorted(str(c) for c in calibrated), "decisionDiff": diff,
            "aucRoc": {"positiveVsClean": st._auc_roc(clean, opaque + transl, direction), "opaqueVsClean": st._auc_roc(clean, opaque, direction),
                       "translucentVsClean": st._auc_roc(clean, transl, direction)},
            "averagePrecision": st._average_precision(clean, opaque + transl, direction), "table": table}


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def run(rows, private_dir: Path, exposure_audit: Mapping[str, Any]) -> dict[str, Any]:
    digest = st.contract_digest()
    dev = [r for r in rows if r["split"] == "development"]
    inv = {g: st.inventory([r for r in dev if r["group"] == g and (g != "CLEAN" or r["truth"] == "negative")]) for g in ("CLEAN",) + st.POSITIVE_FAMILIES}
    clean, _ = _scores(rows, "CLEAN", "development")
    opaque, _ = _scores(rows, "TEXT_WATERMARK_OPAQUE", "development")
    transl, _ = _scores(rows, "TEXT_WATERMARK_TRANSLUCENT", "development")
    direction = st.direction(clean, opaque + transl)
    thresholds = st.candidate_thresholds(clean + opaque + transl)
    development = split_eval(rows, "development", direction, thresholds)
    selection = st.select_threshold(development["table"], direction)
    report: dict[str, Any] = {
        "reportVersion": REPORT_VERSION, "version": st.VERSION, "evidenceLabel": st.EVIDENCE_LABEL, "featureName": st.FEATURE_NAME,
        "contractDigestPrefix": digest[:12], "priorStatus": {k: (list(v) if isinstance(v, tuple) else v) for k, v in st.PRIOR_STATUS.items()},
        "scoreSemantics": {"scoreSource": st.SCORE_SOURCE, "scoreCalibrated": st.SCORE_CALIBRATED, "rawSequenceScore": "whole generated sequence beam log-probability",
                           "attributionScope": "single_region only when regionCount == 1, otherwise whole_sequence", "notA": ["calibrated OCR probability", "per-region confidence", "probability text is correct", "probability watermark is present"]},
        "thresholdGenerationContract": {"grid": list(st.QUANTILE_GRID), "basis": "pooled development scores (clean + opaque + translucent)", "direction": direction,
                                        "directionRule": "median(positive dev) vs median(clean dev)"},
        "developmentInventory": inv, "development": development, "selection": selection,
        "exposureAudit": dict(exposure_audit), "validationEvaluated": 0, "validationSplitName": st.VALIDATION_SPLIT_NAME,
        "confidenceBandChanged": False, "watermarkPolicyChanged": False, "decisionDiff": development["decisionDiff"],
        "textPolicyGap": st.TEXT_POLICY_GAP_STATUS, "graphicalDetectorStudyRequired": st.GRAPHICAL_STUDY_MARKER,
        "naturalPositiveLimitation": st.NATURAL_POSITIVE_LIMITATION,
    }
    if selection["status"] != "SELECTED":
        report["verdict"] = st.verdict(False, None, None)
        return report
    dev_inputs = _digest([[r["group"], r["canonicalAction"], r["shadow"]] for r in dev])
    if st.frozen_path(private_dir).exists():
        st.require_frozen(private_dir, digest)
    else:
        st.write_frozen(private_dir, selection, digest, dev_inputs)
    report["frozen"] = {"threshold": selection["selectedThreshold"], "direction": direction, "role": st.SELECTED_ROLE,
                        "notPolicyThreshold": True, "notConfidenceThreshold": True, "developmentInputsDigestPrefix": dev_inputs[:12]}
    if exposure_audit.get("validationScoreValuesPreviouslySeen") is not False:
        report["verdict"] = st.verdict(True, False, None)
        return report
    lock = st.validation_guard(private_dir, digest, exposure_audit)
    validation = split_eval(rows, "holdout", direction, [selection["selectedThreshold"]])
    st.mark_validation_evaluated(lock, digest)
    report["validationEvaluated"] = 1
    report["validation"] = validation
    report["verdict"] = st.verdict(True, True, validation["table"][0]["eligibility"]["eligible"])
    return report


def _jsonl(path: Path | None):
    if path is None or not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--florence-rows", type=Path, required=True)
    parser.add_argument("--dev-text-rows", type=Path, required=True)
    parser.add_argument("--validation-text-rows", type=Path)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--exposure-audit", type=Path, required=True, help="JSON: validationScoreValuesPreviouslySeen + evidence")
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--forbidden-strings", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    if not labels.get("complete") or labels.get("unresolvedCount"):
        raise SystemExit("BLOCKED_HUMAN_LABELS_REQUIRED")
    exposure = json.loads(args.exposure_audit.read_text(encoding="utf-8"))
    rows = build_rows(_jsonl(args.florence_rows), _jsonl(args.dev_text_rows), _jsonl(args.validation_text_rows), labels)
    report = run(rows, args.private_dir, exposure)
    forbidden = [l.strip() for l in args.forbidden_strings.read_text(encoding="utf-8").splitlines() if l.strip()] if args.forbidden_strings and args.forbidden_strings.exists() else []
    problems = bench.privacy_violations(report, forbidden)
    text = json.dumps(report, indent=2, sort_keys=True)
    wording = [w for w in st.FORBIDDEN_WORDING if w in text]
    if problems or wording:
        raise SystemExit(f"PRIVACY_OR_WORDING_VIOLATION {problems} {wording}")
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
