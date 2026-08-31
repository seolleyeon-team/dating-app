"""Recompute the G004 watermark contribution from redacted v9 evidence only.

The report intentionally does not load images, read the private review bundle,
call Azure, or rerun the full QA stack.  It applies the current typed watermark
action contract to the already extracted machine evidence and keeps the
existing non-watermark QA outcome explicitly separate.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
_AI_MODEL_DIR = _REPO_ROOT / "lib" / "ai_recommend_model"
if str(_AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_MODEL_DIR))

from avatar_generation.analysis.watermark import (
    WATERMARK_POLICY_VERSION,
    WATERMARK_QA_ACTION_ALLOW,
    WATERMARK_QA_ACTION_REJECT,
    WATERMARK_QA_ACTION_REVIEW,
    resolve_watermark_qa_action,
    watermark_risk_for_action,
)


OFFLINE_REPORT_VERSION = "g004_watermark_artifact_only_offline_v1"
CURRENT_QA_CONTRACT_VERSION = "avatar_qa_v4_watermark_artifact_only_v1"
_ORDINAL_PATTERN = re.compile(r"^P[0-9]{2,4}$")
_VALID_ACTIONS = {
    WATERMARK_QA_ACTION_ALLOW,
    WATERMARK_QA_ACTION_REVIEW,
    WATERMARK_QA_ACTION_REJECT,
}
_VALID_DECISION_CLASSES = {
    "no_text_detected",
    "source_consistent_clothing_text",
    "source_consistent_text_or_logo",
    "text_evidence_non_blocking",
    "ambiguous_text_evidence",
    "benign_text_or_logo",
    "overlay_watermark",
    "generated_overlay_logo",
    "generated_text_artifact",
    "identifiable_brand_logo",
}
_VALID_SOURCE_CONSISTENCY = {
    "consistent",
    "mixed",
    "inconsistent",
    "unknown",
    "not_available",
    "not_applicable",
}
_VALID_RISKS = {"low", "medium", "high"}
_VALID_VISUAL_STATUSES = {"available", "needs_review", "critical_unavailable", "unavailable"}
_VALID_TIERS = {"hard_pass", "soft_pass", "needs_review", "hard_reject", "not_previewable"}
_FORBIDDEN_KEY_PARTS = (
    "raw",
    "label",
    "bbox",
    "coordinate",
    "uid",
    "email",
    "path",
    "url",
    "embedding",
    "imagebytes",
)
_FORBIDDEN_EXACT_KEYS = {
    "tokenkey",
    "rawtoken",
    "rawocrtext",
    "ocrtext",
}
_FORBIDDEN_TEXT_MARKERS = (
    "gs://",
    "gcs://",
    "http://",
    "https://",
    "x-goog-signature",
    "x-amz-signature",
)
_REMOTE_MUTATIONS = {
    "azureGenerationCalls": 0,
    "newImages": 0,
    "candidateRegeneration": 0,
    "cloudBuild": 0,
    "artifactRegistry": 0,
    "cloudRun": 0,
    "cloudTasks": 0,
    "remoteRecovery": 0,
    "trafficMutation": 0,
    "productionMutation": 0,
    "queueResume": 0,
    "humanSignoffMutation": 0,
}


def build_offline_contract_report(
    machine_rows: Sequence[Mapping[str, Any]],
    *,
    evaluation_snapshot: Mapping[str, Any] | None = None,
    corrected_stack_context: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a privacy-safe before/after contribution report for exactly 20 rows."""

    rows = _normalize_machine_rows(machine_rows)
    matrix: list[dict[str, Any]] = []
    before_rows: list[dict[str, Any]] = []
    after_rows: list[dict[str, Any]] = []
    for row in rows:
        before_action = _legacy_watermark_action(row)
        after_action = resolve_watermark_qa_action(
            {
                "watermarkQaAction": row.get("watermarkQaAction"),
                "watermarkDecisionClass": row.get("watermarkDecisionClass"),
                "visualRiskStatus": row.get("visualRiskStatus"),
                "textLogoWatermarkRisk": row.get("textLogoWatermarkRisk"),
                "logoTextWatermarkRisk": row.get("logoTextWatermarkRisk"),
            }
        )
        before_risk = _legacy_risk(row, before_action)
        after_risk = watermark_risk_for_action(after_action)
        before_rows.append(
            {
                **row,
                "watermarkQaAction": before_action,
                "textLogoWatermarkRisk": before_risk,
                "logoTextWatermarkRisk": before_risk,
                "runtimeNeedsReviewFromWatermark": before_action == WATERMARK_QA_ACTION_REVIEW,
                "visualRiskStatusContribution": _visual_status_contribution(
                    row["visualRiskStatus"], before_action
                ),
                "candidateQASignalNeedsReviewFromWatermark": before_action == WATERMARK_QA_ACTION_REVIEW,
            }
        )
        after_rows.append(
            {
                **row,
                "watermarkQaAction": after_action,
                "textLogoWatermarkRisk": after_risk,
                "logoTextWatermarkRisk": after_risk,
                "runtimeNeedsReviewFromWatermark": after_action == WATERMARK_QA_ACTION_REVIEW,
                "visualRiskStatusContribution": _visual_status_contribution(
                    row["visualRiskStatus"], after_action
                ),
                "candidateQASignalNeedsReviewFromWatermark": after_action == WATERMARK_QA_ACTION_REVIEW,
            }
        )
        matrix.append(
            {
                "participantOrdinal": row["participantOrdinal"],
                "candidateOrdinal": row["candidateOrdinal"],
                "watermarkDecisionClass": row["watermarkDecisionClass"],
                "watermarkDecisionClassBefore": row["watermarkDecisionClass"],
                "watermarkDecisionClassAfter": row["watermarkDecisionClass"],
                "watermarkQaAction": after_action,
                "watermarkQaActionBefore": before_action,
                "watermarkQaActionAfter": after_action,
                "textLogoWatermarkRisk": after_risk,
                "textLogoWatermarkRiskBefore": before_risk,
                "textLogoWatermarkRiskAfter": after_risk,
                "logoTextWatermarkRisk": after_risk,
                "logoTextWatermarkRiskBefore": before_risk,
                "logoTextWatermarkRiskAfter": after_risk,
                "sourceConsistency": row["sourceConsistency"],
                "evidenceClasses": list(row["watermarkEvidenceClasses"]),
                "visualRiskStatus": row["visualRiskStatus"],
                "visualRiskStatusContribution": _visual_status_contribution(
                    row["visualRiskStatus"], after_action
                ),
                "runtimeNeedsReviewFromWatermark": after_action == WATERMARK_QA_ACTION_REVIEW,
                "runtimeNeedsReviewFromWatermarkBefore": before_action == WATERMARK_QA_ACTION_REVIEW,
                "candidateQASignalNeedsReviewFromWatermark": after_action == WATERMARK_QA_ACTION_REVIEW,
                "candidateQASignalNeedsReviewFromWatermarkBefore": before_action == WATERMARK_QA_ACTION_REVIEW,
                "selectionTier": row["selectionTier"],
            }
        )

    snapshot = _mapping(evaluation_snapshot)
    before_aggregate = _aggregate(before_rows)
    after_aggregate = _aggregate(after_rows)
    before_aggregate["qaOutcome"] = _qa_outcome(snapshot, rows, basis="v9_evaluation_snapshot")
    after_aggregate["qaOutcome"] = _qa_outcome(
        snapshot,
        rows,
        basis="existing_v9_selection_tier_non_watermark_gates_not_rerun",
    )

    context = _safe_corrected_stack_context(corrected_stack_context)
    report = {
        "schemaVersion": OFFLINE_REPORT_VERSION,
        "mode": "offline_same_20_watermark_contribution_recompute",
        "runId": "G004-AZURE-CAL-20260824-001",
        "participantCount": len({row["participantOrdinal"] for row in rows}),
        "candidateCount": len(rows),
        "v9EvidenceContract": {
            "qaVersion": _safe_version(_mapping(provenance).get("v9EvidenceQaVersion")),
            "watermarkPolicyVersion": _safe_version(
                _mapping(provenance).get("v9EvidenceWatermarkPolicyVersion")
            ),
        },
        "offlineContract": {
            "qaVersion": CURRENT_QA_CONTRACT_VERSION,
            "watermarkPolicyVersion": WATERMARK_POLICY_VERSION,
        },
        "before": before_aggregate,
        "after": after_aggregate,
        "rows": matrix,
        "causalReviewAfter": {
            "watermarkArtifactReview": sum(
                row["watermarkQaAction"] == WATERMARK_QA_ACTION_REVIEW for row in matrix
            ),
            "watermarkHardReject": sum(
                row["watermarkQaAction"] == WATERMARK_QA_ACTION_REJECT for row in matrix
            ),
            "watermarkCausalBlocker": sum(
                row["watermarkQaAction"] != WATERMARK_QA_ACTION_ALLOW for row in matrix
            ),
            "otherTypedBlockers": list(context.get("remainingBlockers", [])),
            "genericQaSignalUncertain": 0,
        },
        "regressionChecks": {
            "backgroundLeakageRisk": context.get("backgroundLeakageRisk", {"status": "not_provided"}),
            "identifiabilityRisk": context.get("identifiabilityRisk", {"status": "not_provided"}),
            "privacyQa": context.get("privacyQa", {"status": "not_provided"}),
        },
        "requiredRunState": {
            "humanSignoff": context.get("humanSignoff", snapshot.get("humanSignoff") is True),
            "rubricComplete": snapshot.get("rubricComplete") is True,
            "requiredSignalUnavailable": _safe_count(
                snapshot.get("requiredSignalUnavailable")
            ),
            "overallG004Verdict": str(snapshot.get("verdict") or "BLOCKED_QA_CALIBRATION_DATA"),
            "nextAction": "TRAIT_POLICY_CONTRACT_RESOLUTION",
        },
        "provenance": _safe_provenance(provenance),
        "mutations": dict(_REMOTE_MUTATIONS),
    }
    _assert_privacy_safe(report)
    return report


def load_machine_rows(value: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Load rows from either the benchmark skeleton or a direct row list."""

    if isinstance(value, Mapping):
        real_v9 = _mapping(value.get("realV9"))
        rows = real_v9.get("machineEvidence")
    else:
        rows = value
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError("machine evidence rows are missing")
    return [row for row in rows if isinstance(row, Mapping)]


def _normalize_machine_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError("machine evidence rows are invalid")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ValueError("machine evidence row is invalid")
        participant = str(raw.get("participantOrdinal") or "").strip().upper()
        if _ORDINAL_PATTERN.fullmatch(participant) is None:
            raise ValueError("participant ordinal is invalid")
        candidate_value = raw.get("candidateOrdinal")
        if isinstance(candidate_value, bool):
            raise ValueError("candidate ordinal is invalid")
        try:
            candidate = int(candidate_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("candidate ordinal is invalid") from exc
        if candidate not in {1, 2, 3, 4} or (participant, candidate) in seen:
            raise ValueError("candidate ordinals are invalid or duplicated")
        seen.add((participant, candidate))
        normalized.append(
            {
                "participantOrdinal": participant,
                "candidateOrdinal": candidate,
                "watermarkDecisionClass": _safe_enum(
                    raw.get("watermarkDecisionClass"), _VALID_DECISION_CLASSES
                )
                or "no_text_detected",
                "watermarkEvidenceClasses": _safe_enum_list(
                    raw.get("watermarkEvidenceClasses"), _VALID_DECISION_CLASSES
                ),
                "sourceConsistency": _safe_enum(
                    raw.get("sourceConsistency"), _VALID_SOURCE_CONSISTENCY
                )
                or "not_available",
                "textLogoWatermarkRisk": _safe_enum(raw.get("textLogoWatermarkRisk"), _VALID_RISKS),
                "logoTextWatermarkRisk": _safe_enum(raw.get("logoTextWatermarkRisk"), _VALID_RISKS),
                "watermarkQaAction": _safe_enum(raw.get("watermarkQaAction"), _VALID_ACTIONS),
                "visualRiskStatus": _safe_enum(raw.get("visualRiskStatus"), _VALID_VISUAL_STATUSES)
                or "needs_review",
                "hardReject": raw.get("hardReject") is True,
                "needsReview": raw.get("needsReview") is True,
                "selectionTier": _safe_enum(raw.get("selectionTier"), _VALID_TIERS)
                or "needs_review",
            }
        )
    participants = {row["participantOrdinal"] for row in normalized}
    if len(normalized) != 20 or len(participants) != 5:
        raise ValueError("expected exactly five participants and twenty candidates")
    return sorted(normalized, key=lambda row: (row["participantOrdinal"], row["candidateOrdinal"]))


def _legacy_watermark_action(row: Mapping[str, Any]) -> str:
    decision_class = row.get("watermarkDecisionClass")
    risks = {row.get("textLogoWatermarkRisk"), row.get("logoTextWatermarkRisk")}
    if row.get("hardReject") is True or "high" in risks or decision_class in {
        "overlay_watermark",
        "generated_overlay_logo",
        "generated_text_artifact",
        "identifiable_brand_logo",
    }:
        return WATERMARK_QA_ACTION_REJECT
    if row.get("needsReview") is True or "medium" in risks or decision_class == "ambiguous_text_evidence":
        return WATERMARK_QA_ACTION_REVIEW
    return WATERMARK_QA_ACTION_ALLOW


def _legacy_risk(row: Mapping[str, Any], action: str) -> str:
    for key in ("textLogoWatermarkRisk", "logoTextWatermarkRisk"):
        risk = row.get(key)
        if risk in _VALID_RISKS:
            return str(risk)
    return watermark_risk_for_action(action)


def _aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def count_values(key: str) -> dict[str, int]:
        return dict(sorted(Counter(str(row.get(key)) for row in rows if row.get(key) is not None).items()))

    return {
        "watermarkDecisionClass": count_values("watermarkDecisionClass"),
        "watermarkQaActions": count_values("watermarkQaAction"),
        "textLogoWatermarkRisk": count_values("textLogoWatermarkRisk"),
        "logoTextWatermarkRisk": count_values("logoTextWatermarkRisk"),
        "sourceConsistency": count_values("sourceConsistency"),
        "watermarkEvidenceClasses": _class_list_counts(rows),
        "visualRiskStatus": count_values("visualRiskStatus"),
        "visualRiskStatusContribution": count_values("visualRiskStatusContribution"),
        "runtimeNeedsReviewFromWatermark": _boolean_counts(rows, "runtimeNeedsReviewFromWatermark"),
        "candidateQASignalNeedsReviewFromWatermark": _boolean_counts(
            rows, "candidateQASignalNeedsReviewFromWatermark"
        ),
        "selectionTier": count_values("selectionTier"),
    }


def _qa_outcome(
    snapshot: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    basis: str,
) -> dict[str, Any]:
    counts = _mapping(snapshot.get("counts"))
    if all(key in counts for key in ("hardPass", "softPass", "needsReview", "hardReject")):
        values = {
            key: _safe_count(counts.get(key))
            for key in ("hardPass", "softPass", "needsReview", "hardReject")
        }
    else:
        tier_counts = Counter(str(row.get("selectionTier")) for row in rows)
        values = {
            "hardPass": tier_counts.get("hard_pass", 0),
            "softPass": tier_counts.get("soft_pass", 0),
            "needsReview": tier_counts.get("needs_review", 0),
            "hardReject": tier_counts.get("hard_reject", 0),
        }
    values["basis"] = basis
    return values


def _boolean_counts(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    counter = Counter("true" if row.get(key) is True else "false" for row in rows)
    return dict(sorted(counter.items()))


def _class_list_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        for value in row.get("watermarkEvidenceClasses", []):
            counter[str(value)] += 1
    return dict(sorted(counter.items()))


def _visual_status_contribution(status: str, action: str) -> str:
    if status in {"unavailable", "critical_unavailable"}:
        return "fail_closed_review"
    if action == WATERMARK_QA_ACTION_REJECT:
        return "artifact_reject"
    if action == WATERMARK_QA_ACTION_REVIEW:
        return "artifact_review"
    return "diagnostic_only"


def _safe_corrected_stack_context(value: Mapping[str, Any] | None) -> dict[str, Any]:
    source = _mapping(value)
    result: dict[str, Any] = {}
    for key in ("backgroundLeakageRisk", "identifiabilityRisk", "privacyQa"):
        section = _mapping(source.get(key))
        if not section:
            continue
        safe_section: dict[str, Any] = {}
        for phase in ("before", "after"):
            counts = _safe_count_mapping(section.get(phase))
            if counts:
                safe_section[phase] = counts
        regression_count = section.get("regressionCount")
        if isinstance(regression_count, int) and not isinstance(regression_count, bool) and regression_count >= 0:
            safe_section["regressionCount"] = regression_count
        if safe_section:
            result[key] = safe_section
    blockers = source.get("remainingBlockers")
    if isinstance(blockers, Sequence) and not isinstance(blockers, (str, bytes)):
        result["remainingBlockers"] = [
            value
            for value in (str(item).strip() for item in blockers)
            if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value)
        ]
    if isinstance(source.get("humanSignoff"), bool):
        result["humanSignoff"] = source["humanSignoff"]
    return result


def _safe_provenance(value: Mapping[str, Any] | None) -> dict[str, Any]:
    source = _mapping(value)
    allowed = (
        "sourceSnapshotCommit",
        "offlineFixesHead",
        "v9RecoverySha256",
        "v9EvaluationSha256",
        "v9EvidenceQaVersion",
        "v9EvidenceWatermarkPolicyVersion",
    )
    result: dict[str, Any] = {}
    for key in allowed:
        text = str(source.get(key) or "").strip().lower()
        if re.fullmatch(r"[a-z0-9_.:-]{1,128}", text):
            result[key] = text
    result["offlineEvaluatorVersion"] = OFFLINE_REPORT_VERSION
    result["qaContractVersion"] = CURRENT_QA_CONTRACT_VERSION
    result["watermarkPolicyVersion"] = WATERMARK_POLICY_VERSION
    return result


def _safe_count_mapping(value: Any) -> dict[str, int]:
    source = _mapping(value)
    result: dict[str, int] = {}
    for key, raw_count in source.items():
        label = str(key).strip().lower()
        if not re.fullmatch(r"[a-z0-9_-]{1,40}", label):
            continue
        count = _safe_count(raw_count)
        if count >= 0:
            result[label] = count
    return dict(sorted(result.items()))


def _safe_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed >= 0 else 0


def _safe_enum(value: Any, allowed: set[str]) -> str | None:
    text = str(value or "").strip().lower()
    return text if text in allowed else None


def _safe_enum_list(value: Any, allowed: set[str]) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return sorted({item for item in (_safe_enum(child, allowed) for child in value) if item is not None})


def _safe_version(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if re.fullmatch(r"[a-z0-9_.-]{1,100}", text) else "unknown"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _assert_privacy_safe(value: Any) -> None:
    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
                if normalized in _FORBIDDEN_EXACT_KEYS or any(
                    part in normalized for part in _FORBIDDEN_KEY_PARTS
                ):
                    raise ValueError("forbidden privacy field")
                walk(child)
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)
        elif isinstance(node, str):
            lowered = node.lower()
            if any(marker in lowered for marker in _FORBIDDEN_TEXT_MARKERS):
                raise ValueError("private reference is forbidden")
        elif isinstance(node, (bytes, bytearray)):
            raise ValueError("binary payload is forbidden")

    walk(value)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("JSON artifact could not be read") from exc


def _git_revision(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "unknown"
    value = completed.stdout.strip().lower()
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else "unknown"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine-evidence", type=Path, required=True)
    parser.add_argument("--offline-context", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    machine_artifact = _load_json(args.machine_evidence.resolve())
    context = _load_json(args.offline_context.resolve())
    machine_rows = load_machine_rows(machine_artifact)
    source_provenance = (
        _mapping(machine_artifact.get("provenance"))
        if isinstance(machine_artifact, Mapping)
        else {}
    )
    provenance = {
        **source_provenance,
        "v9EvidenceQaVersion": source_provenance.get("qaVersion"),
        "v9EvidenceWatermarkPolicyVersion": source_provenance.get(
            "watermarkPolicyVersion"
        ),
    }
    provenance = {
        **provenance,
        "offlineFixesHead": _git_revision((args.repo_root or Path(__file__).resolve().parents[1]).resolve()),
    }
    report = build_offline_contract_report(
        machine_rows,
        evaluation_snapshot=_mapping(machine_artifact.get("v9EvaluationSnapshot"))
        if isinstance(machine_artifact, Mapping)
        else {},
        corrected_stack_context=context if isinstance(context, Mapping) else {},
        provenance=provenance,
    )
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.resolve().write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"schemaVersion={report['schemaVersion']}")
    print(f"candidateCount={report['candidateCount']}")
    print(f"watermarkQaActionsAfter={report['after']['watermarkQaActions']}")
    print("azureGenerationCalls=0")
    return 0


__all__ = [
    "CURRENT_QA_CONTRACT_VERSION",
    "OFFLINE_REPORT_VERSION",
    "build_offline_contract_report",
    "load_machine_rows",
    "main",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
