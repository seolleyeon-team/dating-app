"""B3-L6.3 - OWLv2 pilot evaluation: development selection, H4-DIRECT-1, one-shot holdout, gate.

Offline. Runs no model: reads the B3-L6 raw OWLv2 capture, the stored B3-L4
Florence outputs (for the current live watermark action per image) and the
human reference-label artifact. Executes, in the frozen order:

  1. development (G1-G3) metrics per grid threshold under the frozen eligibility
  2. OWLV2_THRESHOLD_SELECTION_V1  (lowest eligible; none -> stop, no holdout)
  3. threshold freeze with inputs digest
  4. development H4-DIRECT-1 check (no re-selection afterwards)
  5. holdout (G4-G5) EXACTLY ONCE, guarded by the lock file
  6. full 20-image gate owlv2_provisional_shadow_gate_v1 (numbers unchanged)

Truth is visibleGraphicalMark only (yes/no; uncertain excluded). Whatever the
label artifact's truthResolutionVersion says is recorded verbatim; this script
never re-resolves labels.

Per-image rows stay in the restricted directory. The --out report is aggregate.
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
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
from avatar_detector_assisted_shadow import boxes_match  # noqa: E402
from avatar_generation.analysis.visual_risk import analyze_florence_visual_risk_outputs  # noqa: E402
from avatar_generation.analysis.watermark import evaluate_watermark_risk  # noqa: E402

REPORT_VERSION = "avatar_owlv2_pilot_evaluation_v1"
PILOT_PRECISION_LABEL = "G004_OWNER_RATER_A_PILOT_PRECISION"
_FLAGGED = {"review", "reject"}


# ---------------------------------------------------------------- inputs


def current_actions(florence_rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Live watermark action per condition id, from the stored Florence outputs."""

    conditions = calib._florence_conditions(florence_rows)
    clean_regions: dict[str, Any] = {}
    for record in conditions.values():
        if record["variant"] == "V0":
            size = (int(record["imageSize"][0]), int(record["imageSize"][1]))
            clean_regions[record["baseOpaqueId"]] = (analyze_florence_visual_risk_outputs(record["tasks"], image_size=size).regions, size)
    out = {}
    for cid, record in conditions.items():
        size = (int(record["imageSize"][0]), int(record["imageSize"][1]))
        analysis = analyze_florence_visual_risk_outputs(record["tasks"], image_size=size)
        base = clean_regions.get(record["baseOpaqueId"])
        use_source = record["variant"] != "V0" and base is not None
        decision = evaluate_watermark_risk(
            analysis.regions,
            source_regions=base[0] if use_source else (),
            source_image_size=base[1] if use_source else None,
            image_size=size,
        )
        out[cid] = decision.watermark_qa_action
    return out


def build_items(capture: Mapping[str, Any], actions: Mapping[str, str], labels: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for row in capture["rows"]:
        items.append(
            {
                "conditionId": row["conditionId"],
                "opaqueId": row["opaqueId"],
                "variant": row["variant"],
                "split": calib._split(row.get("groupKey")),
                "detections": row["detections"],
                "groundTruth": row.get("groundTruth") or [],
                "currentAction": actions.get(row["conditionId"], "allow"),
                "truth": sel.truth_of(labels.get(row["opaqueId"], {})) if row["variant"] == "V0" else None,
            }
        )
    return items


# ---------------------------------------------------------------- metrics


def _injected_recall(items: Sequence[Mapping[str, Any]], threshold: float) -> dict[str, Any]:
    injected = [i for i in items if i["variant"] == "V8"]
    hits = 0
    for item in injected:
        picked = [d for d in item["detections"] if d["score"] >= threshold and d["label"] in sel.PROMPTS]
        if any(boxes_match(truth, d["box"]) for truth in item["groundTruth"] for d in picked):
            hits += 1
    return {"n": len(injected), "hits": hits, "rate": round(hits / len(injected), 4) if injected else None}


def _h4_rows(items: Sequence[Mapping[str, Any]], threshold: float) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        hit = sel.detector_hit(item["detections"], threshold)
        rows.append({**{k: item[k] for k in ("conditionId", "variant", "split", "truth", "currentAction")}, "hit": hit,
                     "h4Action": sel.h4_direct_action(item["currentAction"], hit)})
    return rows


def split_metrics(items: Sequence[Mapping[str, Any]], threshold: float) -> dict[str, Any]:
    rows = _h4_rows(items, threshold)
    clean = [r for r in rows if r["variant"] == "V0"]
    confusion = sel.confusion(clean)
    injected = _injected_recall(items, threshold)
    transitions: Counter = Counter()
    for r in rows:
        transitions["same" if r["currentAction"] == r["h4Action"] else f"{r['currentAction']}->{r['h4Action']}"] += 1
    # Escalate-only makes both structurally zero; measured anyway.
    artifact_regressions = sum(1 for r in rows if r["currentAction"] in _FLAGGED and r["h4Action"] == "allow")
    bypass = sum(1 for r in rows if r["currentAction"] == "reject" and r["h4Action"] != "reject")
    tp, fp, fn = confusion["tp"], confusion["fp"], confusion["fn"]
    return {
        "threshold": threshold,
        "confusion": confusion,
        "precisionCI": calib.wilson(tp, tp + fp) if tp + fp else {"status": "NOT_ESTIMABLE"},
        "recallCI": calib.wilson(tp, tp + fn) if tp + fn else {"status": "NOT_ESTIMABLE"},
        "newReviewRateCI": calib.wilson(confusion["newDetectorInducedReviews"], confusion["humanNegatives"]) if confusion["humanNegatives"] else None,
        "injectedRecall": injected,
        "h4": {
            "cleanReviewBurden": {"current": sum(1 for r in clean if r["currentAction"] in _FLAGGED), "h4": sum(1 for r in clean if r["h4Action"] in _FLAGGED), "n": len(clean)},
            "injectedFlagged": {"current": sum(1 for r in rows if r["variant"] == "V8" and r["currentAction"] in _FLAGGED), "h4": sum(1 for r in rows if r["variant"] == "V8" and r["h4Action"] in _FLAGGED)},
            "humanPositiveResponse": sum(1 for r in clean if r["truth"] == "positive" and r["hit"]),
            "humanNegativeNewReview": confusion["newDetectorInducedReviews"],
            "transitions": dict(sorted(transitions.items())),
        },
        "artifactRegressions": artifact_regressions,
        "hardRejectBypass": bypass,
        "eligibility": sel.eligible(confusion, injected_recall=injected["rate"] or 0.0, artifact_regressions=artifact_regressions, hard_reject_bypass=bypass),
    }


# ---------------------------------------------------------------- pipeline


def run(capture, florence_rows, label_artifact, private_dir: Path) -> dict[str, Any]:
    labels = {row["evaluationId"]: row for row in label_artifact["labels"]}
    actions = current_actions(florence_rows)
    items = build_items(capture, actions, labels)
    dev = [i for i in items if i["split"] == "development"]
    hold = [i for i in items if i["split"] == "holdout"]

    dev_table = {t: split_metrics(dev, t) for t in sel.THRESHOLD_GRID}
    selection = sel.select_threshold({t: m["eligibility"] for t, m in dev_table.items()})
    dev_positives = sum(1 for i in dev if i["variant"] == "V0" and i["truth"] == "positive")
    all_positives = sum(1 for i in items if i["variant"] == "V0" and i["truth"] == "positive")

    report: dict[str, Any] = {
        "reportVersion": REPORT_VERSION,
        "evidenceLabel": calib.PILOT_EVIDENCE_LABEL,
        "precisionLabel": PILOT_PRECISION_LABEL,
        "truthResolutionVersion": label_artifact.get("truthResolutionVersion"),
        "truthAuthority": label_artifact.get("truthAuthority"),
        "thirdAdjudicatorUsed": bool(label_artifact.get("thirdAdjudicatorUsed")),
        "selectionVersion": sel.SELECTION_VERSION,
        "h4Version": sel.H4_VERSION,
        "referenceTruthCounts": {
            "all": dict(Counter(labels[o]["visibleGraphicalMark"] for o in labels)),
            "developmentPositives": dev_positives,
            "allPositives": all_positives,
        },
        "developmentTable": {f"{t:.2f}": {k: v for k, v in m.items() if k != "h4"} | {"h4": m["h4"]} for t, m in dev_table.items()},
        "selection": selection,
        "holdoutEvaluated": 0,
    }

    if selection["status"] != "SELECTED":
        report["pilotVerdict"] = (
            "OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT" if dev_positives == 0 else "OWLV2_PILOT_GATE_FAILED_DEVELOPMENT"
        )
        report["developmentFailureReason"] = (
            "no development human positive under the reference truth: precision is 0 wherever the detector fires and NOT_ESTIMABLE elsewhere, so criterion A cannot pass at any threshold"
            if dev_positives == 0
            else "no grid threshold satisfies A-E on development"
        )
        report["h4Verdict"] = "H4_EVIDENCE_INSUFFICIENT" if dev_positives == 0 else "H4_DIRECT_SHADOW_NOT_SUPPORTED"
        report["gate"] = {"gateVersion": calib.GATE_VERSION, "status": "NOT_EVALUATED_NO_SELECTED_THRESHOLD"}
        return report

    threshold = selection["selectedThreshold"]
    digest = hashlib.sha256(json.dumps({"capture": capture["rows"], "labels": labels}, sort_keys=True).encode()).hexdigest()
    frozen = sel.freeze_record(selection, digest)
    (private_dir / "threshold_frozen.json").write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    report["frozen"] = {k: v for k, v in frozen.items() if k != "inputsDigest"} | {"inputsDigestPrefix": digest[:12]}
    report["developmentH4"] = dev_table[threshold]["h4"]

    lock = sel.holdout_guard(private_dir, frozen)
    holdout = split_metrics(hold, threshold)
    sel.mark_holdout_evaluated(lock, frozen)
    report["holdoutEvaluated"] = 1
    report["holdout"] = holdout

    full = split_metrics(items, threshold)
    report["full20"] = full
    conf = full["confusion"]
    report["gate"] = calib.evaluate_provisional_gate(
        precision=conf["precision"],
        clean_negative_total=conf["humanNegatives"],
        clean_negative_new_reviews=conf["newDetectorInducedReviews"],
        injected_recall=full["injectedRecall"]["rate"],
        generative_artifact_regressions=full["artifactRegressions"],
        hard_reject_bypass=full["hardRejectBypass"],
    )
    passed = report["gate"]["status"] == "PILOT_GATE_PASSED"
    report["pilotVerdict"] = "OWLV2_PROVISIONAL_PILOT_GATE_PASSED" if passed else "OWLV2_PROVISIONAL_PILOT_GATE_FAILED"
    report["h4Verdict"] = "H4_DIRECT_SHADOW_SUPPORTED_FOR_CONTROLLED_CANARY" if passed else "H4_DIRECT_SHADOW_NOT_SUPPORTED"
    (private_dir / "pilot_rows.jsonl").write_text("\n".join(json.dumps(r) for r in _h4_rows(items, threshold)) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--florence-rows", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    capture = json.loads(args.capture.read_text(encoding="utf-8"))
    florence_rows = [json.loads(l) for l in args.florence_rows.read_text(encoding="utf-8").splitlines() if l.strip()]
    label_artifact = json.loads(args.labels.read_text(encoding="utf-8"))
    if not label_artifact.get("complete"):
        raise SystemExit("BLOCKED_HUMAN_LABELS_REQUIRED")
    if label_artifact.get("unresolvedCount"):
        raise SystemExit("BLOCKED_UNRESOLVED_LABELS")
    report = run(capture, florence_rows, label_artifact, args.private_dir)
    problems = bench.privacy_violations(report)
    if problems:
        raise SystemExit(f"PRIVACY_VIOLATION {problems}")
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
