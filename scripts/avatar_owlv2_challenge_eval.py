"""B3-L7 - V2 controlled challenge evaluation: dev selection, freeze, one-shot holdout, gate V2.

Offline; runs no model. Inputs: the clean capture (B3-L6, variant V0 rows), the
V2 challenge capture, the stored B3-L4 Florence outputs (live watermark action
per clean image) and the owner-resolved reference labels. Order is frozen:

  1. development (G1-G3): clean-negative specificity + family recall per grid threshold
  2. eligibility under gate V2 criteria A-G, OWLV2_THRESHOLD_SELECTION_V1 (lowest eligible)
  3. freeze (threshold, versions, model revision, prompts, input digest)
  4. holdout (G4-G5) EXACTLY ONCE via the lock in this stage's private dir
  5. full 20-base results, both sides reported separately

Current-action note: Florence was not re-run on the new derivatives, so a
challenge condition's live action is a PROXY = its base clean image's live
action (F1 reuses the real V8 action). H4-DIRECT-1 is escalate-only, so the
proxy can only understate H4's flagged count, never overstate it.
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
import avatar_owlv2_challenge_v2 as v2  # noqa: E402
import avatar_owlv2_pilot_evaluation as pilot  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
from avatar_detector_assisted_shadow import boxes_match  # noqa: E402

REPORT_VERSION = "avatar_owlv2_challenge_eval_v1"
_FLAGGED = {"review", "reject"}


def _hit(row: Mapping[str, Any], threshold: float) -> bool:
    return sel.detector_hit(row["detections"], threshold)


def _box_hit(row: Mapping[str, Any], threshold: float) -> tuple[int, int, bool]:
    picked = [d for d in row["detections"] if d["score"] >= threshold and d["label"] in v2.PROMPTS]
    hits = sum(1 for t in row["groundTruth"] if any(boxes_match(t, d["box"]) for d in picked))
    return hits, len(row["groundTruth"]), hits > 0


def _prompts_that_hit(row: Mapping[str, Any], threshold: float) -> set[str]:
    out = set()
    for d in row["detections"]:
        if d["score"] >= threshold and d["label"] in v2.PROMPTS and any(boxes_match(t, d["box"]) for t in row["groundTruth"]):
            out.add(d["label"])
    return out


def clean_side(clean_rows: Sequence[Mapping[str, Any]], threshold: float) -> dict[str, Any]:
    items = [{"truth": r["truth"], "hit": _hit(r, threshold), "currentAction": r["currentAction"]} for r in clean_rows]
    conf = sel.confusion(items)
    h4 = [sel.h4_direct_action(i["currentAction"], i["hit"]) for i in items]
    return {
        "n": len(items),
        "detectorResponseRate": round(sum(1 for i in items if i["hit"]) / len(items), 4) if items else None,
        "falsePositiveImages": conf["fp"],
        "trueNegativeImages": conf["tn"],
        "excludedUnresolved": conf["excludedUnresolved"],
        "currentReviewBurden": sum(1 for i in items if i["currentAction"] in _FLAGGED),
        "h4ReviewBurden": sum(1 for a in h4 if a in _FLAGGED),
        "newDetectorInducedReviews": conf["newDetectorInducedReviews"],
        "humanNegatives": conf["humanNegatives"],
        "newReviewRate": conf["newReviewRate"],
        "newReviewRateCI": calib.wilson(conf["newDetectorInducedReviews"], conf["humanNegatives"]) if conf["humanNegatives"] else None,
        "confusion": conf,
    }


def positive_side(rows: Sequence[Mapping[str, Any]], threshold: float) -> dict[str, Any]:
    by_family: dict[str, list] = {}
    for r in rows:
        by_family.setdefault(r["family"], []).append(r)
    families = {}
    total_hit = 0
    for family, frows in sorted(by_family.items()):
        image_hits = box_hits = boxes = 0
        prompt_counter: Counter = Counter()
        current_flag = h4_flag = 0
        for r in frows:
            h, n, ih = _box_hit(r, threshold)
            box_hits += h
            boxes += n
            image_hits += int(ih)
            for p in _prompts_that_hit(r, threshold):
                prompt_counter[p] += 1
            current_flag += int(r["currentAction"] in _FLAGGED)
            h4_flag += int(sel.h4_direct_action(r["currentAction"], _hit(r, threshold)) in _FLAGGED)
        total_hit += image_hits
        families[family] = {
            "n": len(frows),
            "imageHits": image_hits,
            "rate": round(image_hits / len(frows), 4),
            "rateCI": calib.wilson(image_hits, len(frows)),
            "regionRecall": round(box_hits / boxes, 4) if boxes else None,
            "modelMisses": len(frows) - image_hits,
            "policyMisses": sum(1 for r in frows if _box_hit(r, threshold)[2] and sel.h4_direct_action(r["currentAction"], True) == "allow"),
            "currentPolicyFlagged": current_flag,
            "h4Flagged": h4_flag,
            "promptsThatHit": dict(sorted(prompt_counter.items())),
        }
    return {
        "label": v2.RECALL_LABEL,
        "conditions": len(rows),
        "overallImageRecall": round(total_hit / len(rows), 4) if rows else None,
        "overallCI": calib.wilson(total_hit, len(rows)) if rows else None,
        "families": families,
    }


def _safety(rows: Sequence[Mapping[str, Any]], threshold: float) -> dict[str, int]:
    h4 = [(r["currentAction"], sel.h4_direct_action(r["currentAction"], _hit(r, threshold))) for r in rows]
    return {
        "artifactRegressions": sum(1 for c, h in h4 if c in _FLAGGED and h == "allow"),
        "hardRejectBypass": sum(1 for c, h in h4 if c == "reject" and h != "reject"),
        "transitions": dict(sorted(Counter("same" if c == h else f"{c}->{h}" for c, h in h4).items())),
    }


def split_eval(clean_rows, pos_rows, threshold: float) -> dict[str, Any]:
    clean = clean_side(clean_rows, threshold)
    positive = positive_side(pos_rows, threshold)
    safety = _safety(list(clean_rows) + list(pos_rows), threshold)
    return {
        "threshold": threshold,
        "cleanNegative": clean,
        "controlledPositive": positive,
        "safety": safety,
        "eligibility": v2.eligible_v2(clean["confusion"], positive["families"], positive["overallImageRecall"],
                                      artifact_regressions=safety["artifactRegressions"], hard_reject_bypass=safety["hardRejectBypass"]),
    }


def build_rows(clean_capture, challenge_capture, florence_rows, label_artifact):
    labels = {row["evaluationId"]: row for row in label_artifact["labels"]}
    actions = pilot.current_actions(florence_rows)
    clean_rows = []
    for r in clean_capture["rows"]:
        if r["variant"] != "V0":
            continue
        clean_rows.append({**r, "split": calib._split(r.get("groupKey")), "currentAction": actions.get(r["conditionId"], "allow"),
                           "truth": sel.truth_of(labels.get(r["opaqueId"], {}))})
    pos_rows = []
    for r in challenge_capture["rows"]:
        reused = r.get("reusedFrom")
        proxy_key = f"{r['opaqueId']}:{reused}" if reused else f"{r['opaqueId']}:V0"
        pos_rows.append({**r, "split": calib._split(r.get("groupKey")), "currentAction": actions.get(proxy_key, "allow"),
                         "currentActionSource": "florence_v8" if reused else "proxy_base_clean"})
    return clean_rows, pos_rows


def run(clean_capture, challenge_capture, florence_rows, label_artifact, private_dir: Path) -> dict[str, Any]:
    clean_rows, pos_rows = build_rows(clean_capture, challenge_capture, florence_rows, label_artifact)
    dev_c = [r for r in clean_rows if r["split"] == "development"]
    dev_p = [r for r in pos_rows if r["split"] == "development"]
    hold_c = [r for r in clean_rows if r["split"] == "holdout"]
    hold_p = [r for r in pos_rows if r["split"] == "holdout"]
    # dev/holdout isolation: no base opaque id in both
    assert not ({r["opaqueId"] for r in dev_p} & {r["opaqueId"] for r in hold_p}), "GROUP_LEAK"

    dev_table = {t: split_eval(dev_c, dev_p, t) for t in v2.THRESHOLD_GRID}
    selection = sel.select_threshold({t: m["eligibility"] for t, m in dev_table.items()})
    report: dict[str, Any] = {
        "reportVersion": REPORT_VERSION,
        "gateVersion": v2.GATE_VERSION,
        "gateV1Status": "OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT (unchanged, not reinterpreted)",
        "evidenceLabel": v2.EVIDENCE_LABEL,
        "selectionVersion": sel.SELECTION_VERSION,
        "h4Version": v2.H4_VERSION,
        "modelRevision": challenge_capture.get("revision"),
        "prompts": list(v2.PROMPTS),
        "truthResolutionVersion": label_artifact.get("truthResolutionVersion"),
        "families": [{"code": f.code, "family": f.family, "safetyCritical": f.safety_critical, "reused": bool(f.reuse_variant)} for f in v2.FAMILIES],
        "conditionsPerFamily": dict(sorted(Counter(r["family"] for r in pos_rows).items())),
        "currentActionNote": "challenge rows use the base clean image's live action as a proxy (Florence not re-run); F1 uses the real V8 action",
        "developmentTable": {f"{t:.2f}": m for t, m in dev_table.items()},
        "selection": selection,
        "holdoutEvaluated": 0,
        "naturalPositiveLimitation": "NATURAL_POSITIVE_EVIDENCE_MISSING",
    }
    if selection["status"] != "SELECTED":
        report["v2Verdict"] = "OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT"
        report["h4Verdict"] = "H4_DIRECT_SHADOW_NOT_SUPPORTED"
        return report

    threshold = selection["selectedThreshold"]
    digest = hashlib.sha256(json.dumps({"clean": clean_capture["rows"], "challenge": challenge_capture["rows"],
                                        "labels": label_artifact["labels"]}, sort_keys=True).encode()).hexdigest()
    frozen = sel.freeze_record(selection, digest)
    frozen.update(gateVersion=v2.GATE_VERSION, modelRevision=challenge_capture.get("revision"))
    (private_dir / "threshold_frozen_v2.json").write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    report["frozen"] = {k: v for k, v in frozen.items() if k != "inputsDigest"} | {"inputsDigestPrefix": digest[:12]}

    lock = sel.holdout_guard(private_dir, frozen)
    holdout = split_eval(hold_c, hold_p, threshold)
    sel.mark_holdout_evaluated(lock, frozen)
    report["holdoutEvaluated"] = 1
    report["holdout"] = holdout

    full = split_eval(clean_rows, pos_rows, threshold)
    report["full"] = full
    passed = full["eligibility"]["eligible"]
    report["v2Verdict"] = "OWLV2_CONTROLLED_CHALLENGE_GATE_PASSED" if passed else "OWLV2_CONTROLLED_CHALLENGE_GATE_FAILED"
    report["h4Verdict"] = "H4_DIRECT_SHADOW_SUPPORTED_FOR_CONTROLLED_CANARY" if passed else "H4_DIRECT_SHADOW_NOT_SUPPORTED"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean-capture", type=Path, required=True)
    parser.add_argument("--challenge-capture", type=Path, required=True)
    parser.add_argument("--florence-rows", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    clean = json.loads(args.clean_capture.read_text(encoding="utf-8"))
    challenge = json.loads(args.challenge_capture.read_text(encoding="utf-8"))
    if challenge.get("partial"):
        raise SystemExit("CHALLENGE_CAPTURE_PARTIAL")
    if challenge.get("revision") != clean.get("revision"):
        raise SystemExit("MODEL_REVISION_DRIFT")
    florence_rows = [json.loads(l) for l in args.florence_rows.read_text(encoding="utf-8").splitlines() if l.strip()]
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    if not labels.get("complete") or labels.get("unresolvedCount"):
        raise SystemExit("BLOCKED_HUMAN_LABELS_REQUIRED")
    report = run(clean, challenge, florence_rows, labels, args.private_dir)
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
