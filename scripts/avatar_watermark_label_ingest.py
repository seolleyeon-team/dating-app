"""B3-L6 Part A - ingest two independent rater exports, measure agreement, emit a repo-safe artifact.

Enforces the pre-registered contract (revised in B3-L6.2):

  * two raters with DISTINCT ids. Identical label content across distinct raters
    is NOT fraud: two real people can agree on every item. It is accepted when
    the owner attests that the passes were independent, and held otherwise;
  * duplicate or missing evaluation ids are rejected;
  * obvious within-rater contradictions block with the rater, the opaque id and
    the conflicting typed fields only -- never repaired by the tool;
  * only the allowed fields survive (no filename, UID, path, transcription,
    detector score or detector box);
  * every item must be labelled by both raters before the corpus counts as
    complete;
  * an item is UNRESOLVED when any of primaryLabel / visibleGraphicalMark /
    markIntegration / markType differs, or when the gate-relevant field
    (visibleGraphicalMark) is uncertain on either side. Two raters cannot form
    a majority, so nothing is auto-resolved: only a distinct third adjudicator's
    export resolves an item.

  python scripts/avatar_watermark_label_ingest.py --rater-a a.json --rater-b b.json \
      --owner-attests-independence --out labels.json [--adjudication c.json]
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

import avatar_florence_ceiling as bench  # noqa: E402
from avatar_watermark_label_local import (  # noqa: E402
    LABEL_CONFIDENCE,
    LABEL_SCHEMA_VERSION,
    MARK_INTEGRATION,
    MARK_TYPE,
    PRIMARY_LABELS,
    VISIBLE_GRAPHICAL_MARK,
)

INGEST_VERSION = "avatar_watermark_label_ingest_v3"
LABEL_ARTIFACT_VERSION = "b3l6_adjudicated_labels_v1"

# B3-L6.2A owner decision: for this pilot, Rater A is the designated human
# reference authority and Rater B is agreement/disagreement telemetry only. This
# is an explicit mode, never the default. It is an owner policy decision, not a
# claim that Rater A is objective truth, and it is not a three-rater consensus.
RESOLUTION_MODES = ("consensus", "owner-rater-a")
TRUTH_RESOLUTION_VERSION = "OWNER_RATER_A_RESOLUTION_V1"
TRUTH_AUTHORITY = "OWNER_DESIGNATED_RATER_A_REFERENCE_TRUTH"
ALLOWED_FIELDS = (
    "evaluationId",
    "primaryLabel",
    "allVisibleClasses",
    "visibleGraphicalMark",
    "markIntegration",
    "markType",
    "labelConfidence",
    "raterId",
    "adjudicationState",
)
COMPARED_FIELDS = ("primaryLabel", "visibleGraphicalMark", "markIntegration", "markType")
# The detector-truth field (B3-L6.1 §13). "uncertain" here leaves an item unresolved.
GATE_FIELD = "visibleGraphicalMark"
NO_MARK = "NO_VISIBLE_RELEVANT_TEXT_OR_MARK"
_VOCAB = {
    "primaryLabel": set(PRIMARY_LABELS),
    "visibleGraphicalMark": set(VISIBLE_GRAPHICAL_MARK),
    "markIntegration": set(MARK_INTEGRATION),
    "markType": set(MARK_TYPE),
    "labelConfidence": set(LABEL_CONFIDENCE),
}


def sanitize(row: Mapping[str, Any], rater: str) -> dict[str, Any]:
    if row.get("evaluationId") in (None, ""):
        raise SystemExit("MISSING_EVALUATION_ID")
    out: dict[str, Any] = {"evaluationId": str(row["evaluationId"]), "raterId": str(rater)}
    for field, vocabulary in _VOCAB.items():
        value = row.get(field)
        if value is not None:
            if str(value) not in vocabulary:
                raise SystemExit(f"INVALID_LABEL_VALUE {field}")
            out[field] = str(value)
    classes = row.get("allVisibleClasses") or []
    if not isinstance(classes, Sequence) or isinstance(classes, (str, bytes)):
        raise SystemExit("INVALID_LABEL_VALUE allVisibleClasses")
    unknown = [c for c in classes if str(c) not in set(PRIMARY_LABELS)]
    if unknown:
        raise SystemExit("INVALID_LABEL_VALUE allVisibleClasses")
    out["allVisibleClasses"] = [str(c) for c in classes]
    return out


def contradictions(row: Mapping[str, Any]) -> list[str]:
    """Obvious within-rater contradictions only. Ambiguous combinations are left alone.

    Returns field-name pairs joined by "+"; never content.
    """

    mark = row.get("visibleGraphicalMark")
    mark_type = row.get("markType")
    primary = row.get("primaryLabel")
    classes = set(row.get("allVisibleClasses") or ())
    problems = []
    if mark == "yes" and mark_type == "none":
        problems.append("visibleGraphicalMark+markType")
    if mark == "no" and mark_type in {"graphical_logo", "watermark"}:
        problems.append("visibleGraphicalMark+markType")
    if primary == NO_MARK and mark == "yes":
        problems.append("primaryLabel+visibleGraphicalMark")
    if primary == NO_MARK and (classes - {NO_MARK}):
        problems.append("primaryLabel+allVisibleClasses")
    return problems


def resolve_owner_rater_a(row_a: Mapping[str, Any], row_b: Mapping[str, Any]) -> dict[str, Any]:
    """OWNER_RATER_A_RESOLUTION_V1: A == B -> A; A != B -> A; A uncertain -> uncertain.

    Takes the two sanitized rater rows and nothing else: no detector score, no
    Florence output, no confidence can enter. Rater B never overrides A; its
    disagreement is recorded per row as telemetry only.
    """

    agree = all(row_a.get(f) == row_b.get(f) for f in COMPARED_FIELDS)
    uncertain = row_a.get(GATE_FIELD) == "uncertain"
    return {
        "evaluationId": row_a["evaluationId"],
        "primaryLabel": row_a.get("primaryLabel"),
        "visibleGraphicalMark": row_a.get("visibleGraphicalMark"),
        "markIntegration": row_a.get("markIntegration"),
        "markType": row_a.get("markType"),
        "allVisibleClasses": sorted(row_a.get("allVisibleClasses") or []),
        "adjudicationState": "owner_rater_a_reference_uncertain" if uncertain else "owner_rater_a_reference",
        "raterAgreement": agree,
        "disagreeingFields": [f for f in COMPARED_FIELDS if row_a.get(f) != row_b.get(f)],
    }


def _load(path: Path) -> tuple[str, dict[str, dict[str, Any]], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("labelSchema") != LABEL_SCHEMA_VERSION:
        raise SystemExit("LABEL_SCHEMA_MISMATCH")
    rater = str(payload.get("raterId") or "")
    if not rater:
        raise SystemExit("MISSING_RATER_ID")
    rows: dict[str, dict[str, Any]] = {}
    for row in payload.get("labels") or []:
        clean = sanitize(row, rater)
        if clean["evaluationId"] in rows:
            raise SystemExit("DUPLICATE_EVALUATION_ID")
        rows[clean["evaluationId"]] = clean
    return rater, rows, str(payload.get("adjudicationState") or "")


def _content(rows: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item: {f: v for f, v in row.items() if f != "raterId"} for item, row in rows.items()}


def _kappa(values_a: Sequence[str], values_b: Sequence[str]) -> float | None:
    n = len(values_a)
    if n == 0:
        return None
    observed = sum(1 for a, b in zip(values_a, values_b) if a == b) / n
    ca, cb = Counter(values_a), Counter(values_b)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if expected >= 1.0:
        return None  # degenerate: no variance in either rater
    return round((observed - expected) / (1 - expected), 4)


def agreement(rows_a: Mapping[str, Any], rows_b: Mapping[str, Any]) -> dict[str, Any]:
    """Quality telemetry only. Never a gate criterion."""

    items = sorted(set(rows_a) & set(rows_b))
    exact = {}
    for field in COMPARED_FIELDS:
        agree = sum(1 for i in items if rows_a[i].get(field) == rows_b[i].get(field))
        exact[field] = {"agree": agree, "n": len(items), "rate": round(agree / len(items), 4) if items else None}
    kappa = {
        field: _kappa([rows_a[i].get(field) for i in items], [rows_b[i].get(field) for i in items])
        for field in ("primaryLabel", "visibleGraphicalMark")
    }
    return {
        "exact": exact,
        "cohenKappa": kappa,
        "kappaNote": "None means degenerate (no variance in a rater); small-sample estimate",
        "sampleSizeNote": f"N={len(items)} items; telemetry, not a pilot criterion",
    }


def ingest(
    path_a: Path,
    path_b: Path,
    expected_items: Sequence[str] | None = None,
    *,
    independence_attested: bool = False,
    adjudication: Path | None = None,
    truth_resolution: str = "consensus",
) -> dict[str, Any]:
    if truth_resolution not in RESOLUTION_MODES:
        raise SystemExit(f"UNKNOWN_TRUTH_RESOLUTION {truth_resolution}")
    owner_mode = truth_resolution == "owner-rater-a"
    rater_a, rows_a, _ = _load(path_a)
    rater_b, rows_b, _ = _load(path_b)
    if rater_a == rater_b:
        raise SystemExit("RATERS_NOT_DISTINCT")
    if owner_mode and adjudication is not None:
        raise SystemExit("ADJUDICATION_NOT_USED_IN_OWNER_RATER_A_MODE")

    blockers_a, blockers_b = [], []
    for rater, rows, sink in ((rater_a, rows_a, blockers_a), (rater_b, rows_b, blockers_b)):
        for item, row in sorted(rows.items()):
            for problem in contradictions(row):
                sink.append({"raterId": rater, "evaluationId": item, "fields": problem})
    if owner_mode:
        # A is the reference authority: its contradictions hard-block. B's are
        # telemetry only -- B does not decide truth, so it cannot block it.
        if blockers_a:
            raise SystemExit("BLOCKED_RATER_A_CORRECTION_REQUIRED " + json.dumps(blockers_a))
    elif blockers_a or blockers_b:
        raise SystemExit("BLOCKED_RATER_LABEL_CORRECTION_REQUIRED " + json.dumps(blockers_a + blockers_b))

    identical = bool(rows_a) and _content(rows_a) == _content(rows_b)
    if identical and not independence_attested:
        raise SystemExit("IDENTICAL_CONTENT_REQUIRES_INDEPENDENCE_ATTESTATION")

    third_rater, third_rows = None, {}
    if adjudication is not None:
        third_rater, third_rows, state = _load(adjudication)
        if third_rater in (rater_a, rater_b):
            raise SystemExit("ADJUDICATOR_NOT_DISTINCT")
        if state != "third_adjudication":
            raise SystemExit("ADJUDICATION_STATE_INVALID")
        for item, row in third_rows.items():
            if contradictions(row):
                raise SystemExit("BLOCKED_ADJUDICATOR_LABEL_CORRECTION_REQUIRED " + json.dumps({"evaluationId": item}))

    items = sorted(set(rows_a) | set(rows_b) | set(expected_items or ()))
    complete = [i for i in items if i in rows_a and i in rows_b]
    field_disagreements: Counter = Counter()
    resolved, unresolved_ids = [], []
    for item in complete:
        a, b = rows_a[item], rows_b[item]
        differing = [f for f in COMPARED_FIELDS if a.get(f) != b.get(f)]
        gate_uncertain = a.get(GATE_FIELD) == "uncertain" or b.get(GATE_FIELD) == "uncertain"
        for f in differing:
            field_disagreements[f] += 1
        if owner_mode:
            resolved.append(resolve_owner_rater_a(a, b))
            continue
        if not differing and not gate_uncertain:
            resolved.append(
                {
                    "evaluationId": item,
                    "primaryLabel": a.get("primaryLabel"),
                    "visibleGraphicalMark": a.get("visibleGraphicalMark"),
                    "markIntegration": a.get("markIntegration"),
                    "markType": a.get("markType"),
                    "allVisibleClasses": sorted(set(a["allVisibleClasses"]) & set(b["allVisibleClasses"])),
                    "adjudicationState": "agreed",
                }
            )
            continue
        if item in third_rows and third_rows[item].get(GATE_FIELD) != "uncertain":
            third = third_rows[item]
            resolved.append(
                {
                    "evaluationId": item,
                    "primaryLabel": third.get("primaryLabel"),
                    "visibleGraphicalMark": third.get("visibleGraphicalMark"),
                    "markIntegration": third.get("markIntegration"),
                    "markType": third.get("markType"),
                    "allVisibleClasses": sorted(third["allVisibleClasses"]),
                    "adjudicationState": "third_adjudicated",
                }
            )
            continue
        unresolved_ids.append(item)
        resolved.append(
            {
                "evaluationId": item,
                "primaryLabel": "UNCERTAIN",
                "visibleGraphicalMark": "uncertain",
                "markIntegration": "uncertain",
                "markType": "uncertain",
                "allVisibleClasses": [],
                "adjudicationState": "unresolved_disagreement" if differing else "unresolved_gate_field_uncertain",
                "unresolvedFields": differing or [GATE_FIELD],
            }
        )

    return {
        "ingestVersion": INGEST_VERSION,
        "labelArtifactVersion": LABEL_ARTIFACT_VERSION,
        "labelSchema": LABEL_SCHEMA_VERSION,
        "truthResolutionMode": truth_resolution,
        "truthResolutionVersion": TRUTH_RESOLUTION_VERSION if owner_mode else "CONSENSUS",
        "truthAuthority": TRUTH_AUTHORITY if owner_mode else "TWO_RATER_CONSENSUS_WITH_THIRD_ADJUDICATION",
        "referenceRater": rater_a if owner_mode else None,
        "raterBContradictionCount": len(blockers_b),
        "raters": sorted([rater_a, rater_b]),
        "raterCount": 2,
        "independenceProvenance": "owner_attestation" if independence_attested else "not_attested",
        "identicalContent": identical,
        "thirdAdjudicatorUsed": third_rater is not None,
        "itemsExpected": len(items),
        "itemsCompletedByBoth": len(complete),
        "complete": bool(items) and len(complete) == len(items),
        "agreement": agreement(rows_a, rows_b),
        "agreementCount": sum(1 for i in complete if all(rows_a[i].get(f) == rows_b[i].get(f) for f in COMPARED_FIELDS)),
        "disagreementFields": dict(sorted(field_disagreements.items())),
        "disagreementCount": sum(1 for i in complete if any(rows_a[i].get(f) != rows_b[i].get(f) for f in COMPARED_FIELDS)),
        "gateRelevantDisagreementCount": sum(1 for i in complete if rows_a[i].get(GATE_FIELD) != rows_b[i].get(GATE_FIELD)),
        "resolvedCount": sum(1 for r in resolved if r["adjudicationState"] in ("agreed", "third_adjudicated")),
        "unresolvedCount": len(unresolved_ids),
        "unresolvedIds": unresolved_ids,
        "uncertainCount": sum(1 for r in resolved if r["visibleGraphicalMark"] == "uncertain"),
        "primaryLabelDistribution": dict(Counter(r["primaryLabel"] for r in resolved)),
        "visibleGraphicalMarkDistribution": dict(Counter(r["visibleGraphicalMark"] for r in resolved)),
        "labels": resolved,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rater-a", type=Path, required=True)
    parser.add_argument("--rater-b", type=Path, required=True)
    parser.add_argument("--adjudication", type=Path)
    parser.add_argument("--worksheet", type=Path)
    parser.add_argument("--owner-attests-independence", action="store_true")
    parser.add_argument("--truth-resolution", choices=RESOLUTION_MODES, default="consensus")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    expected = None
    if args.worksheet:
        expected = [i["evaluationId"] for i in json.loads(args.worksheet.read_text(encoding="utf-8"))["items"]]
    report = ingest(
        args.rater_a,
        args.rater_b,
        expected,
        independence_attested=args.owner_attests_independence,
        adjudication=args.adjudication,
        truth_resolution=args.truth_resolution,
    )
    problems = bench.privacy_violations(report)
    if problems:
        raise SystemExit(f"PRIVACY_VIOLATION {problems}")
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    if not report["complete"]:
        print("BLOCKED_HUMAN_LABELS_REQUIRED", file=sys.stderr)
        return 2
    if report["unresolvedCount"] and report["truthResolutionMode"] == "consensus":
        print("BLOCKED_THIRD_ADJUDICATION_REQUIRED", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
