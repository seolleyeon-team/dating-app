"""Pure policy functions for production 3:3 meeting verification.

Firestore access stays in the v1 verification script. Keeping the policy
pure makes the strict failure contract testable without credentials or a live
database.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


VALID_OUTPUT_STATUSES = frozenset({"ready", "empty", "skipped"})


def _value(record: Any, key: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(key, default)
    return getattr(record, key, default)


def _status_counts(records: Mapping[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for record in records.values():
        counts[str(_value(record, "index_status", "unknown") or "unknown")] += 1
    return counts


def _append_skip_reason(reason_counts: Counter[str], value: Any) -> None:
    if isinstance(value, str) and value.strip():
        reason_counts[value.strip()] += 1


def _summarize_output_documents(
    group_ids: Sequence[str],
    docs: Mapping[str, Any],
    *,
    item_field: str,
) -> tuple[dict[str, Any], Counter[str], dict[str, str]]:
    status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    algorithm_versions: dict[str, str] = {}
    missing = 0
    malformed = 0
    malformed_reasons: Counter[str] = Counter()

    for group_id in group_ids:
        if group_id not in docs:
            missing += 1
            continue

        doc = docs[group_id]
        if not isinstance(doc, Mapping):
            malformed += 1
            malformed_reasons["document_not_map"] += 1
            continue

        status = doc.get("status")
        if status not in VALID_OUTPUT_STATUSES:
            malformed += 1
            malformed_reasons["invalid_status"] += 1
            continue

        status_counts[str(status)] += 1
        _append_skip_reason(reason_counts, doc.get("skipReason"))

        algorithm_version = doc.get("algorithmVersion")
        if isinstance(algorithm_version, str) and algorithm_version.strip():
            algorithm_versions[group_id] = algorithm_version.strip()

        items = doc.get(item_field)
        if not isinstance(items, list):
            malformed += 1
            malformed_reasons[f"{item_field}_not_list"] += 1
            continue
        if status == "ready" and not items:
            malformed += 1
            malformed_reasons[f"ready_{item_field}_empty"] += 1

    result = {
        "ready": status_counts.get("ready", 0),
        "empty": status_counts.get("empty", 0),
        "skipped": status_counts.get("skipped", 0),
        "missing": missing,
        "malformed": malformed,
        "malformedReasons": dict(malformed_reasons),
    }
    return result, reason_counts, algorithm_versions


def evaluate_meeting_verification(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the production failure policy to a verification summary."""

    ready_groups = int(summary.get("readyGroups", 0) or 0)
    if ready_groups == 0:
        return {
            "status": "no_input",
            "healthy": True,
            "failureReasons": [],
        }

    failure_reasons: list[str] = []
    for output_name in ("meetingModelRecs", "meetingDailyRecs"):
        output = summary.get(output_name, {}) or {}
        if int(output.get("missing", 0) or 0) > 0:
            failure_reasons.append(f"{output_name}:missing")
        if int(output.get("malformed", 0) or 0) > 0:
            failure_reasons.append(f"{output_name}:malformed")

    return {
        "status": "healthy" if not failure_reasons else "failed",
        "healthy": not failure_reasons,
        "failureReasons": failure_reasons,
    }


def build_meeting_verification_summary(
    date_key: str,
    group_records: Mapping[str, Any],
    model_docs: Mapping[str, Any],
    daily_docs: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a JSON-safe summary and evaluate it.

    Only ``ready`` group-index records are required to have daily outputs.
    Skipped groups are reported for observability but are not treated as
    infrastructure failures.
    """

    group_status_counts = _status_counts(group_records)
    ready_group_ids = sorted(
        group_id
        for group_id, record in group_records.items()
        if _value(record, "index_status", "unknown") == "ready"
    )

    reason_counts: Counter[str] = Counter()
    for record in group_records.values():
        _append_skip_reason(reason_counts, _value(record, "skip_reason"))

    model_summary, model_reasons, model_versions = _summarize_output_documents(
        ready_group_ids,
        model_docs,
        item_field="items",
    )
    daily_summary, daily_reasons, daily_versions = _summarize_output_documents(
        ready_group_ids,
        daily_docs,
        item_field="candidates",
    )
    reason_counts.update(model_reasons)
    reason_counts.update(daily_reasons)

    summary: dict[str, Any] = {
        "dateKey": date_key,
        "inputGroups": len(group_records),
        "readyGroups": len(ready_group_ids),
        "skippedGroups": max(0, len(group_records) - len(ready_group_ids)),
        "meetingGroupIndex": {
            "ready": group_status_counts.get("ready", 0),
            "skipped": group_status_counts.get("skipped", 0),
            "unknown": group_status_counts.get("unknown", 0),
            "total": len(group_records),
        },
        "meetingModelRecs": model_summary,
        "meetingDailyRecs": daily_summary,
        # Top-level counters keep the operational contract easy to query in
        # Cloud Logging and in meetingVerifyRuns without unpacking nested maps.
        "modelReady": model_summary["ready"],
        "modelEmpty": model_summary["empty"],
        "modelSkipped": model_summary["skipped"],
        "modelMissing": model_summary["missing"],
        "modelMalformed": model_summary["malformed"],
        "dailyReady": daily_summary["ready"],
        "dailyEmpty": daily_summary["empty"],
        "dailySkipped": daily_summary["skipped"],
        "dailyMissing": daily_summary["missing"],
        "dailyMalformed": daily_summary["malformed"],
        "algorithmVersion": {
            "meetingModelRecs": sorted(set(model_versions.values())),
            "meetingDailyRecs": sorted(set(daily_versions.values())),
        },
        "algorithmVersions": {
            "meetingModelRecs": sorted(set(model_versions.values())),
            "meetingDailyRecs": sorted(set(daily_versions.values())),
        },
        "skipReasonHistogram": dict(reason_counts),
    }
    summary.update(evaluate_meeting_verification(summary))
    return summary

