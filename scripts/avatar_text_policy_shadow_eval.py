"""B3-L9 TEXT_POLICY_SHADOW_V1 evaluator (offline, aggregate-only, decision-neutral).

Inputs (restricted local captures, never committed): B3-L4 Florence raw outputs
(clean V0 and tiled V4 rows for all 20 avatars), B3-L8 Florence challenge
capture (actual derivatives, development), B3-L9 holdout text capture (only
after the selected-candidate freeze), B3-L7 OWLv2 challenge capture and B3-L5
OWLv2 clean capture (V4 recomposition only), Rater A reference labels.

Order: aggregate feature inventory -> candidate table on development ->
strictest eligible selected and frozen -> holdout once behind
text_policy_v1_holdout_evaluated.lock -> V4 recomposition only after a holdout
pass.  Nothing is retuned after a table is seen.
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

import avatar_dual_channel_v3 as v3  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_text_policy_shadow as tp  # noqa: E402
from avatar_generation.analysis.visual_risk import analyze_florence_visual_risk_outputs  # noqa: E402
from avatar_generation.analysis.watermark import evaluate_watermark_risk  # noqa: E402

REPORT_VERSION = "avatar_text_policy_shadow_eval_v1"
TEXT_FAMILY_BY_CODE = {"F3": "TEXT_WATERMARK_OPAQUE", "F4": "TEXT_WATERMARK_TRANSLUCENT", "F6": "BRAND_LIKE_TEXT_AND_SYMBOL"}


class MissingRows(RuntimeError):
    pass


def canonical(tasks: Mapping[str, Any], image_size: Sequence[int]) -> tuple[str, dict[str, Any]]:
    """Canonical action + the typed evidence document (production contract, source_regions=())."""

    size = (int(image_size[0]), int(image_size[1]))
    analysis = analyze_florence_visual_risk_outputs(tasks, image_size=size)
    decision = evaluate_watermark_risk(analysis.regions, source_regions=(), image_size=size)
    return decision.watermark_qa_action, dict(decision.evidence or {})


def _item(row: Mapping[str, Any], group: str, family: str | None, source: str) -> dict[str, Any]:
    action, evidence = canonical(row["tasks"], row["imageSize"])
    return {"opaqueId": row.get("baseOpaqueId") or row.get("opaqueId"), "split": calib._split(group), "family": family,
            "canonicalAction": action, "evidence": evidence, "florenceSource": source}


def build_items(florence_rows, v3_rows, holdout_rows, label_artifact):
    labels = {r["evaluationId"]: r for r in label_artifact["labels"]}
    clean, tiled, text = [], [], []
    for r in florence_rows:
        if r.get("domain") != bench.DOMAIN_AVATAR or bench.TASK_OD not in r["tasks"]:
            continue
        if r["variant"] == "V0":
            item = _item(r, r.get("groupKey"), None, "reused_exact")
            item["truth"] = sel_truth(labels.get(r["baseOpaqueId"], {}))
            clean.append(item)
        elif r["variant"] == "V4":
            tiled.append(_item(r, r.get("groupKey"), "REPEATED_TILED_MARK", "reused_exact"))
    for r in v3_rows:
        if r["familyCode"] in TEXT_FAMILY_BY_CODE:
            text.append(_item(r, r["groupKey"], TEXT_FAMILY_BY_CODE[r["familyCode"]], "reused_exact_b3l8"))
    for r in holdout_rows:
        if r["familyCode"] in TEXT_FAMILY_BY_CODE:
            text.append(_item(r, r["groupKey"], TEXT_FAMILY_BY_CODE[r["familyCode"]], "local_inference_b3l9"))
    return clean, tiled, text


def sel_truth(label: Mapping[str, Any]) -> str | None:
    value = label.get("visibleGraphicalMark")
    return "positive" if value == "yes" else "negative" if value == "no" else None


# ------------------------------------------------------------------ feature inventory (aggregate)


def feature_inventory(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fields = ("kind", "location", "areaBand", "overlayLike", "textQuality", "artifactHint", "repeated", "confidenceBand")
    dist = {f: Counter() for f in fields}
    per_image = Counter()
    combo = Counter()
    actions = Counter(i["canonicalAction"] for i in items)
    for i in items:
        regions = i["evidence"].get("regionEvidence") or []
        per_image[len(regions)] += 1
        for r in regions:
            for f in fields:
                dist[f][str(r.get(f))] += 1
            combo[f"{r.get('location')}/{r.get('areaBand')}/overlay={bool(r.get('overlayLike'))}"] += 1
    return {"n": len(items), "canonicalActions": dict(actions), "regionsPerImage": {str(k): v for k, v in sorted(per_image.items())},
            "fields": {f: dict(sorted(c.items())) for f, c in dist.items()}, "locationAreaOverlay": dict(sorted(combo.items()))}


# ------------------------------------------------------------------ per-candidate evaluation


def _with_proposed(cand: tp.Candidate, items):
    return [{**i, "proposed": tp.proposed_review(cand, i["evidence"])} for i in items]


def evaluate_candidate(cand: tp.Candidate, clean, tiled, text) -> dict[str, Any]:
    negatives = _with_proposed(cand, [i for i in clean if i["truth"] == "negative"])
    tiled_rows = _with_proposed(cand, tiled)
    text_rows = _with_proposed(cand, text)
    by_family = {}
    for fam in sorted({r["family"] for r in text_rows}):
        by_family[fam] = tp.family_recall([r for r in text_rows if r["family"] == fam])
    clean_m = tp.clean_burden(negatives)
    rep = tp.repeated_preservation(tiled_rows)
    safe = tp.safety(negatives + tiled_rows + text_rows)
    recall = {fam: m["rate"] for fam, m in by_family.items()}
    elig = tp.eligible(clean_m, recall, rep["rate"], hard_reject_bypass=safe["hardRejectBypass"], artifact_regressions=safe["artifactRegressions"])
    return {"candidate": cand.id, "rank": cand.rank, "predicate": cand.predicate, "clean": {**clean_m, "excludedNonNegative": len(clean) - len(negatives)},
            "textFamilies": by_family, "repeated": rep, "safety": safe, **elig}


def split_table(clean, tiled, text, split: str) -> dict[str, Any]:
    c = [i for i in clean if i["split"] == split]
    t = [i for i in tiled if i["split"] == split]
    x = [i for i in text if i["split"] == split and i["family"] in ("TEXT_WATERMARK_OPAQUE", "TEXT_WATERMARK_TRANSLUCENT")]
    counts = Counter(i["family"] for i in x)
    if split == "holdout" and (counts.get("TEXT_WATERMARK_OPAQUE", 0) < 8 or counts.get("TEXT_WATERMARK_TRANSLUCENT", 0) < 8):
        raise MissingRows(f"holdout text rows incomplete: {dict(counts)}")
    return {cand.id: evaluate_candidate(cand, c, t, x) for cand in tp.CANDIDATES}


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ V4 recomposition (development, 10 families)


def v4_recomposition(cand: tp.Candidate, clean, v3_rows, challenge_capture, clean_capture, label_artifact) -> dict[str, Any]:
    labels = {r["evaluationId"]: r for r in label_artifact["labels"]}
    owl_clean = {r["opaqueId"]: r["detections"] for r in clean_capture["rows"] if r["variant"] == "V0"}
    owl_pos = {r["conditionId"]: r["detections"] for r in challenge_capture["rows"]}
    dev_clean = [i for i in clean if i["split"] == "development" and i["truth"] == "negative"]
    clean_rows = []
    for i in dev_clean:
        proposed = tp.proposed_review(cand, i["evidence"])
        hit = tp.v4_graphical_hit(owl_clean[i["opaqueId"]])
        clean_rows.append({"canonical": i["canonicalAction"], "v4": tp.v4_action(i["canonicalAction"], proposed_text_review=proposed, graphical_hit=hit)})
    new_review = sum(1 for r in clean_rows if r["canonical"] == "allow" and r["v4"] == "review")
    fam: dict[str, dict[str, int]] = {}
    for r in v3_rows:
        if r["split"] != "development":
            continue
        action, evidence = canonical(r["tasks"], r["imageSize"])
        proposed = tp.proposed_review(cand, evidence)
        hit = tp.v4_graphical_hit(owl_pos[f"{r['opaqueId']}:{r['familyCode']}"])
        v4 = tp.v4_action(action, proposed_text_review=proposed, graphical_hit=hit)
        f = fam.setdefault(r["family"], {"n": 0, "canonicalFlagged": 0, "v3Flagged": 0, "v4Flagged": 0})
        f["n"] += 1
        f["canonicalFlagged"] += int(action in tp.FLAGGED)
        f["v3Flagged"] += int(v3.v3_shadow_action(action, hit) in tp.FLAGGED)
        f["v4Flagged"] += int(v4 in tp.FLAGGED)
    # reused families (GRAPHIC_SYMBOL, REPEATED_TILED_MARK) come from the B3-L4 capture in the V3 evaluator; here only
    # the 8 locally captured families are recomposed, and the two reused ones are carried from V3 (12/12 each).
    total_n = sum(f["n"] for f in fam.values()) + 24
    total_v4 = sum(f["v4Flagged"] for f in fam.values()) + 24
    return {"version": tp.V4_VERSION, "owlv2Threshold": tp.V4_OWLV2_THRESHOLD, "prompts": list(tp.V4_PROMPTS), "textCandidate": cand.id,
            "scope": "development G1-G3 only; reused families GRAPHIC_SYMBOL/REPEATED_TILED_MARK carried at 12/12 from V3",
            "clean": {"n": len(clean_rows), "newAllowToReview": new_review, "newReviewRate": round(new_review / len(clean_rows), 4) if clean_rows else None},
            "families": dict(sorted(fam.items())),
            "overall": {"n": total_n, "v4Flagged": total_v4, "actionRecall": round(total_v4 / total_n, 4) if total_n else None, "label": tp.RECALL_LABEL},
            "graphicalGapFamilies": list(tp.GRAPHICAL_GAP_FAMILIES), "graphicalDetectorStudyRequired": tp.GRAPHICAL_STUDY_MARKER}


# ------------------------------------------------------------------ run


def run(florence_rows, v3_rows, holdout_rows, label_artifact, private_dir: Path, *, challenge_capture=None, clean_capture=None) -> dict[str, Any]:
    clean, tiled, text = build_items(florence_rows, v3_rows, holdout_rows, label_artifact)
    digest = tp.contract_digest()
    dev_clean = [i for i in clean if i["split"] == "development"]
    dev_text = [i for i in text if i["split"] == "development"]
    inventory = {
        "CLEAN_HUMAN_NEGATIVE": feature_inventory([i for i in dev_clean if i["truth"] == "negative"]),
        "TEXT_WATERMARK_OPAQUE": feature_inventory([i for i in dev_text if i["family"] == "TEXT_WATERMARK_OPAQUE"]),
        "TEXT_WATERMARK_TRANSLUCENT": feature_inventory([i for i in dev_text if i["family"] == "TEXT_WATERMARK_TRANSLUCENT"]),
        "BRAND_LIKE_TEXT_AND_SYMBOL(diagnostic)": feature_inventory([i for i in dev_text if i["family"] == "BRAND_LIKE_TEXT_AND_SYMBOL"]),
        "REPEATED_TILED_MARK(diagnostic)": feature_inventory([i for i in tiled if i["split"] == "development"]),
    }
    dev_table = split_table(clean, tiled, text, "development")
    selection = tp.select_candidate({k: {"eligible": v["eligible"]} for k, v in dev_table.items()})
    report: dict[str, Any] = {
        "reportVersion": REPORT_VERSION, "version": tp.VERSION, "candidateSet": tp.CANDIDATE_SET_VERSION,
        "designation": tp.DESIGNATION, "evidenceLabel": tp.EVIDENCE_LABEL, "contractDigestPrefix": digest[:12],
        "priorStatus": {k: (list(v) if isinstance(v, tuple) else v) for k, v in tp.PRIOR_STATUS.items()},
        "canonicalPolicy": {"version": tp.CANONICAL_POLICY_VERSION, "source": tp.CANONICAL_SOURCE},
        "allowedRuntimeFields": sorted(tp.ALLOWED_RUNTIME_FIELDS), "forbiddenRuntimeFields": sorted(tp.FORBIDDEN_RUNTIME_FIELDS),
        "candidates": tp.candidate_definitions(), "criteria": {"A": tp.NEW_REVIEW_CEILING, "B": tp.TEXT_RECALL_FLOOR, "C": tp.TEXT_RECALL_FLOOR, "D": tp.REPEATED_PRESERVATION, "E": 0, "F": 0},
        "truthAuthority": v3.TRUTH_AUTHORITY, "developmentFeatureInventory": inventory,
        "development": {"table": dev_table, "selection": selection,
                        "florenceSources": dict(Counter(i["florenceSource"] for i in dev_text))},
        "holdoutEvaluated": 0, "naturalPositiveLimitation": tp.NATURAL_POSITIVE_LIMITATION,
        "graphicalDetectorStudyRequired": tp.GRAPHICAL_STUDY_MARKER, "graphicalGapFamilies": list(tp.GRAPHICAL_GAP_FAMILIES),
    }
    if selection["status"] != "SELECTED":
        report.update(tp.verdicts(False, None))
        report["holdoutVerdict"] = None
        return report

    cand = tp.CANDIDATE_BY_ID[selection["selectedCandidate"]]
    dev_inputs = _digest([{k: i[k] for k in ("opaqueId", "canonicalAction", "evidence")} for i in dev_clean + dev_text + [t for t in tiled if t["split"] == "development"]])
    marker = tp.selected_marker(private_dir)
    if marker.exists():
        tp.require_selected(private_dir, digest)   # a prior freeze must match; never silently re-select
        frozen = json.loads(marker.read_text(encoding="utf-8"))
        if frozen["selectedCandidate"] != cand.id:
            raise tp.CandidateNotFrozen("selected candidate differs from the frozen record")
    else:
        tp.write_selected_marker(private_dir, cand.id, digest, dev_inputs)
    report["selectedFrozen"] = {"candidate": cand.id, "predicate": cand.predicate, "contractDigestPrefix": digest[:12], "developmentInputsDigestPrefix": dev_inputs[:12]}

    hold_text = [i for i in text if i["split"] == "holdout"]
    if len(hold_text) < 16:
        report["holdoutStatus"] = "HOLDOUT_TEXT_EVIDENCE_MISSING (selected candidate frozen; local inference may proceed)"
        report.update(tp.verdicts(True, None))
        report["verdict"] = "TEXT_POLICY_SHADOW_DEVELOPMENT_PASSED_HOLDOUT_PENDING"
        report["holdoutVerdict"] = None
        return report

    lock = tp.holdout_guard(private_dir, digest)
    hold_table = split_table(clean, tiled, text, "holdout")
    tp.mark_holdout_evaluated(lock, digest)
    report["holdoutEvaluated"] = 1
    report["holdout"] = {"selected": hold_table[cand.id], "florenceSources": dict(Counter(i["florenceSource"] for i in hold_text))}
    hold_pass = hold_table[cand.id]["eligible"]
    v = tp.verdicts(True, hold_pass)
    report.update(v)
    report["holdoutVerdict"] = v["verdict"]
    if hold_pass and challenge_capture is not None and clean_capture is not None:
        tp.require_holdout_pass(report)
        report["v4"] = v4_recomposition(cand, clean, v3_rows, challenge_capture, clean_capture, label_artifact)
    return report


def _jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--florence-rows", type=Path, required=True, help="B3-L4 raw_outputs.jsonl")
    parser.add_argument("--v3-florence-rows", type=Path, required=True, help="B3-L8 florence_challenge_capture.jsonl")
    parser.add_argument("--holdout-rows", type=Path, help="B3-L9 holdout text capture (only after freeze)")
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--challenge-capture", type=Path, help="B3-L7 OWLv2 capture (V4 only)")
    parser.add_argument("--clean-capture", type=Path, help="B3-L5 OWLv2 clean capture (V4 only)")
    parser.add_argument("--forbidden-strings", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    if not labels.get("complete") or labels.get("unresolvedCount"):
        raise SystemExit("BLOCKED_HUMAN_LABELS_REQUIRED")
    challenge = json.loads(args.challenge_capture.read_text(encoding="utf-8")) if args.challenge_capture else None
    clean_cap = json.loads(args.clean_capture.read_text(encoding="utf-8")) if args.clean_capture else None
    if challenge is not None and challenge.get("revision") != v3.OWLV2_REVISION:
        raise SystemExit("MODEL_REVISION_DRIFT")
    report = run(_jsonl(args.florence_rows), _jsonl(args.v3_florence_rows), _jsonl(args.holdout_rows), labels, args.private_dir,
                 challenge_capture=challenge, clean_capture=clean_cap)
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
