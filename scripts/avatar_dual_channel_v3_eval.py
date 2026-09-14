"""B3-L8 dual-channel V3 evaluator (offline, aggregate-only, decision-neutral).

Inputs are existing restricted captures: OWLv2 clean capture (B3-L5), OWLv2
challenge capture (B3-L7), Florence raw outputs (B3-L4), the local V3 Florence
challenge capture (B3-L8), the reuse audit, and the owner-designated Rater A
reference labels.  No model runs here.

Development (G1-G3) first.  Holdout (G4-G5) opens only when the frozen
criteria A-L all pass on development, once, behind v3_holdout_evaluated.lock.
Rules are never changed after a table is seen.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_dual_channel_v3 as v3  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_owlv2_challenge_v2 as v2  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402

REPORT_VERSION = "avatar_dual_channel_v3_eval_v1"
SOURCE_REUSED = "reused_exact"
SOURCE_LOCAL = "local_inference"


class MissingFlorenceRows(RuntimeError):
    pass


def _boxes(ground_truth: Sequence[Any]) -> list[list[float]]:
    """Normalize either [{'box': [...]}] (Florence captures) or [[...]] (OWLv2 capture)."""

    out = []
    for item in ground_truth or ():
        box = item["box"] if isinstance(item, Mapping) else item
        out.append([round(float(v), 3) for v in box])
    return out


def florence_index(florence_rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    out = {}
    for r in florence_rows:
        if r.get("domain") != bench.DOMAIN_AVATAR:
            continue
        if bench.TASK_OCR_WITH_REGION not in r["tasks"] or bench.TASK_OD not in r["tasks"]:
            continue
        out[r["conditionId"]] = r
    return out


def build_clean_items(clean_capture, florence_by_condition, label_artifact) -> list[dict[str, Any]]:
    labels = {row["evaluationId"]: row for row in label_artifact["labels"]}
    items = []
    for r in clean_capture["rows"]:
        if r["variant"] != "V0":
            continue
        base = florence_by_condition.get(f"{r['opaqueId']}:V0")
        if base is None:
            raise MissingFlorenceRows(f"clean Florence row missing for one base ({r.get('groupKey')})")
        items.append({
            "opaqueId": r["opaqueId"],
            "split": calib._split(r.get("groupKey")),
            "truth": sel.truth_of(labels.get(r["opaqueId"], {})),
            "canonicalAction": v3.channel_t_action(base["tasks"], base["imageSize"]),
            "owlv2Hit": v3.channel_g_hit(r["detections"]),
            "florenceSource": SOURCE_REUSED,
        })
    return items


def build_positive_rows(challenge_capture, florence_by_condition, v3_florence_rows, reuse_audit) -> list[dict[str, Any]]:
    """Actual derivative -> actual Florence output -> canonical policy. No base-action proxy."""

    local = {r["conditionId"]: r for r in v3_florence_rows}
    rows = []
    for r in challenge_capture["rows"]:
        verdict = reuse_audit["families"][r["family"]]
        if verdict["verdict"] == v3.REUSE_EXACT:
            fl = florence_by_condition.get(f"{r['opaqueId']}:{verdict['variant']}")
            source = SOURCE_REUSED
        else:
            fl = local.get(f"{r['opaqueId']}:{r['familyCode']}")
            source = SOURCE_LOCAL
        if fl is not None and _boxes(fl["groundTruth"]) != _boxes(r["groundTruth"]):
            # Same construct must mean the same injected geometry; otherwise the
            # Florence output does not belong to this condition.
            raise MissingFlorenceRows(f"provenance mismatch (injected boxes differ) for family {r['family']} [{source}]")
        rows.append({
            "opaqueId": r["opaqueId"],
            "split": calib._split(r.get("groupKey")),
            "family": r["family"],
            "familyCode": r["familyCode"],
            "owlv2Hit": v3.channel_g_hit(r["detections"]),
            "florenceSource": source,
            "canonicalAction": v3.channel_t_action(fl["tasks"], fl["imageSize"]) if fl is not None else None,
            "florenceOcrHit": v3.florence_ocr_hit(fl["tasks"], fl["imageSize"], fl["groundTruth"]) if fl is not None else None,
        })
    return rows


def _require_complete(rows: Sequence[Mapping[str, Any]], split: str) -> None:
    missing = [r for r in rows if r["canonicalAction"] is None]
    if missing:
        raise MissingFlorenceRows(f"{split}: {len(missing)} challenge rows lack an actual Florence output "
                                  f"({dict(Counter(r['family'] for r in missing))})")


def split_eval(clean_items, pos_rows, split: str) -> dict[str, Any]:
    _require_complete(pos_rows, split)
    negatives = [i for i in clean_items if i["truth"] == "negative"]
    clean = v3.clean_burden(negatives)
    families = v3.family_attribution(pos_rows)
    flagged = sum(1 for r in pos_rows if v3.v3_shadow_action(r["canonicalAction"], r["owlv2Hit"]) in v3.FLAGGED)
    overall = round(flagged / len(pos_rows), 4) if pos_rows else None
    safe = v3.safety(list(negatives) + list(pos_rows))
    eligibility = v3.eligible_v3(clean, families, overall, artifact_regressions=safe["artifactRegressions"],
                                 hard_reject_bypass=safe["hardRejectBypass"])
    transitions = Counter(f"{r['canonicalAction']}->{v3.v3_shadow_action(r['canonicalAction'], r['owlv2Hit'])}"
                          for r in list(negatives) + list(pos_rows))
    return {
        "split": split,
        "clean": {**clean, "excludedNonNegative": len(clean_items) - len(negatives)},
        "families": families,
        "overall": {"n": len(pos_rows), "v3Flagged": flagged, "actionRecall": overall,
                    "actionRecallCI": calib.wilson(flagged, len(pos_rows)) if pos_rows else None, "label": v3.RECALL_LABEL},
        "safety": safe,
        "transitions": dict(sorted(transitions.items())),
        "eligibility": eligibility,
        "florenceSources": dict(Counter(r["florenceSource"] for r in pos_rows)),
    }


def run(clean_capture, challenge_capture, florence_rows, v3_florence_rows, reuse_audit, label_artifact, private_dir: Path) -> dict[str, Any]:
    fl_index = florence_index(florence_rows)
    clean_items = build_clean_items(clean_capture, fl_index, label_artifact)
    pos_rows = build_positive_rows(challenge_capture, fl_index, v3_florence_rows, reuse_audit)
    dev_c = [i for i in clean_items if i["split"] == "development"]
    dev_p = [r for r in pos_rows if r["split"] == "development"]
    hold_c = [i for i in clean_items if i["split"] == "holdout"]
    hold_p = [r for r in pos_rows if r["split"] == "holdout"]
    assert not ({r["opaqueId"] for r in dev_p} & {r["opaqueId"] for r in hold_p}), "GROUP_LEAK"

    digest = v3.contract_digest()
    development = split_eval(dev_c, dev_p, "development")
    report: dict[str, Any] = {
        "reportVersion": REPORT_VERSION,
        "v3Version": v3.V3_VERSION,
        "evidenceLabel": v3.EVIDENCE_LABEL,
        "gateV1Status": f"{v3.GATE_V1_STATUS_FROZEN} (unchanged, not reinterpreted)",
        "gateV2Status": f"{v3.GATE_V2_STATUS_FROZEN} (unchanged, not reinterpreted)",
        "contractDigestPrefix": digest[:12],
        "channelT": {"name": v3.CHANNEL_T, "source": v3.CHANNEL_T_SOURCE, "policyVersion": v3.CHANNEL_T_POLICY_VERSION,
                     "florenceRepo": v3.FLORENCE_REPO, "florenceRevision": v3.pinned_florence_revision()},
        "channelG": {"name": v3.CHANNEL_G, "repo": v3.OWLV2_REPO, "revision": challenge_capture.get("revision"),
                     "threshold": v3.OWLV2_THRESHOLD, "thresholdAuthority": v3.OWLV2_THRESHOLD_AUTHORITY,
                     "prompts": list(v3.PROMPTS), "mode": v3.PROMPT_MODE},
        "truthAuthority": v3.TRUTH_AUTHORITY,
        "truthResolutionVersion": label_artifact.get("truthResolutionVersion"),
        "reuseAudit": {k: {"verdict": v["verdict"], "variant": v["variant"], "bitwise": v.get("bitwiseIdentityOfHistoricalCapture")}
                       for k, v in reuse_audit["families"].items()},
        "actualDerivativeActions": True,
        "proxyBaseActionsUsed": False,
        "development": development,
        "holdoutEvaluated": 0,
        "naturalPositiveLimitation": v3.NATURAL_POSITIVE_LIMITATION,
    }
    if not development["eligibility"]["eligible"]:
        report["channelGapDiagnosis"] = v3.diagnose(development["clean"], development["families"], development["eligibility"])
        report.update(v3.verdicts(False, None, True))
        report["v3Verdict"], report["h4Verdict"] = report.pop("v3"), report.pop("h4")
        return report

    v3.write_dev_pass_marker(private_dir, digest, {"eligibility": development["eligibility"], "overall": development["overall"]})
    lock = v3.holdout_guard_v3(private_dir, digest)
    holdout = split_eval(hold_c, hold_p, "holdout")
    v3.mark_holdout_evaluated_v3(lock, digest)
    report["holdoutEvaluated"] = 1
    report["holdout"] = holdout
    full = split_eval(clean_items, pos_rows, "full")
    report["full"] = full
    safe = full["safety"]["artifactRegressions"] == 0 and full["safety"]["hardRejectBypass"] == 0
    verdict = v3.verdicts(True, holdout["eligibility"]["eligible"], safe)
    report["v3Verdict"], report["h4Verdict"] = verdict["v3"], verdict["h4"]
    if not holdout["eligibility"]["eligible"]:
        report["channelGapDiagnosis"] = v3.diagnose(holdout["clean"], holdout["families"], holdout["eligibility"])
    return report


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean-capture", type=Path, required=True)
    parser.add_argument("--challenge-capture", type=Path, required=True)
    parser.add_argument("--florence-rows", type=Path, required=True)
    parser.add_argument("--v3-florence-rows", type=Path, required=True)
    parser.add_argument("--reuse-audit", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--forbidden-strings", type=Path, help="local file of strings that must not appear in the report")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    clean = json.loads(args.clean_capture.read_text(encoding="utf-8"))
    challenge = json.loads(args.challenge_capture.read_text(encoding="utf-8"))
    if challenge.get("partial"):
        raise SystemExit("CHALLENGE_CAPTURE_PARTIAL")
    if challenge.get("revision") != clean.get("revision") or challenge.get("revision") != v3.OWLV2_REVISION:
        raise SystemExit("MODEL_REVISION_DRIFT")
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    if not labels.get("complete") or labels.get("unresolvedCount"):
        raise SystemExit("BLOCKED_HUMAN_LABELS_REQUIRED")
    reuse_audit = json.loads(args.reuse_audit.read_text(encoding="utf-8"))
    report = run(clean, challenge, _jsonl(args.florence_rows), _jsonl(args.v3_florence_rows), reuse_audit, labels, args.private_dir)
    forbidden = []
    if args.forbidden_strings and args.forbidden_strings.exists():
        forbidden = [l.strip() for l in args.forbidden_strings.read_text(encoding="utf-8").splitlines() if l.strip()]
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
