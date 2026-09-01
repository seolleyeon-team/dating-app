"""Deterministic G004 threshold evidence and calibration-run evaluation.

This module consumes already-redacted scalar QA evidence.  It never loads an
image, resolves a storage reference, or emits participant identifiers.  The
CLI wrapper in ``scripts/avatar_calibration_evaluator.py`` is intentionally
thin so the same contract can be used by tests and a controlled runner.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import math
import re
from typing import Any, Iterable, Mapping, Sequence

from .calibration_artifact import (
    CalibrationArtifact,
    CalibrationArtifactError,
    canonical_artifact_sha256,
)
from .qa_contract import required_signal_failure_codes
from .analysis.watermark import resolve_watermark_qa_action


MIN_G004_PARTICIPANTS = 5
CALIBRATION_EVALUATION_VERSION = "g004_calibration_evaluation_v3_watermark_artifact_only"
RUBRIC_SCORE_FIELDS = (
    "overallQuality",
    "resemblance",
    "ageDistortionRisk",
    "consistency",
    "backgroundNaturalness",
)
RUBRIC_SAFETY_VALUES = frozenset({"approve", "needs_review", "reject"})
CLIP_RISK_KEYS = (
    "childlike",
    "sexualized",
    "beautification",
    "brand_mismatch",
    "severe_artifact",
)
CLIP_MINIMUM_KEYS = ("adult_like", "brand_fit")
_ORDINAL_PATTERN = re.compile(r"^P[0-9]{2,4}$")
_SAFE_REASON_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
_FORBIDDEN_KEY_FRAGMENTS = (
    "embedding",
    "landmark",
    "bbox",
    "signedurl",
    "sourceimage",
    "candidateimage",
    "sourcepath",
    "candidatepath",
    "privatepath",
    "rawuid",
    "sourceuid",
    "uid",
    "apikey",
    "token",
    "credential",
)
_FORBIDDEN_TEXT_MARKERS = (
    "gs://",
    "gcs://",
    "https://",
    "http://",
    "x-goog-signature",
    "x-amz-signature",
    "signedurl",
    "private-source",
    "privatebucket",
)
_FORBIDDEN_HASH_KEY_FRAGMENTS = (
    "hash",
    "digest",
    "checksum",
    "etag",
    "md5",
)
_SAFE_LABELS = frozenset({"safe", "acceptable", "pass", "negative", "low_risk"})
_RISK_LABELS = frozenset({"risk", "unsafe", "reject", "high_risk", "positive"})


def evaluate_calibration_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    artifact: CalibrationArtifact | Mapping[str, Any],
    rubric: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one consistent, already-redacted calibration run.

    ``rubric`` carries run-level evidence that must not be inferred from
    candidates: threshold snapshot, current-QA wiring, outage fail-closed
    probe, privacy scan, and human signoff.  Missing evidence fails closed.
    """

    active_artifact = _coerce_artifact(artifact)
    control = dict(rubric or {})
    raw_rows = list(rows) if isinstance(rows, Sequence) else []
    invalid_rows = 0
    consent_count = 0
    total_candidate_count = 0
    counts = {"hardPass": 0, "softPass": 0, "needsReview": 0, "hardReject": 0}
    reject_reasons: Counter[str] = Counter()
    failure_reasons: set[str] = set()
    metric_values: dict[str, list[float]] = {
        "latencyMs": [],
        "costUsd": [],
        "traitCoverage": [],
    }
    preview_violations = 0
    required_signal_unavailable = 0
    required_signal_failure_counts: Counter[str] = Counter()
    candidate_count_exceeded = False
    qa_versions: set[str] = set()
    watermark_decision_classes: Counter[str] = Counter()
    watermark_evidence_class_counts: Counter[str] = Counter()
    watermark_qa_actions: Counter[str] = Counter()
    watermark_policy_versions: set[str] = set()
    participant_ordinals: list[str] = []
    rubric_scores: dict[str, list[float]] = {field: [] for field in RUBRIC_SCORE_FIELDS}
    rubric_complete_count = 0
    slice_counts: Counter[str] = Counter()

    for raw_row in raw_rows:
        if not isinstance(raw_row, Mapping):
            invalid_rows += 1
            continue
        ordinal = _participant_ordinal(raw_row.get("participantOrdinal"))
        if ordinal is None:
            invalid_rows += 1
            continue
        consent = _mapping(raw_row.get("consent"))
        consent_valid = _consent_is_exact(consent)
        if consent_valid:
            consent_count += 1
        else:
            failure_reasons.add("exact_consent_incomplete")

        candidates = raw_row.get("candidates")
        candidate_list = list(candidates) if isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes)) else []
        if len(candidate_list) > 4:
            candidate_count_exceeded = True
        total_candidate_count += len(candidate_list)
        if not candidate_list:
            failure_reasons.add("candidate_evidence_missing")

        row_record = {
            "ordinal": ordinal,
            "consent": consent_valid,
            "candidateCount": len(candidate_list),
            "slice": _redacted_slice(raw_row.get("cohortSlice")),
        }
        participant_ordinals.append(ordinal)
        if row_record["slice"]:
            slice_counts[_slice_key(row_record["slice"])] += 1
        else:
            failure_reasons.add("cohort_slice_missing")

        human_review = _human_review_for_row(raw_row, control, ordinal)
        if _rubric_is_complete(human_review):
            rubric_complete_count += 1
            for field in RUBRIC_SCORE_FIELDS:
                rubric_scores[field].append(float(human_review[field]))
        else:
            failure_reasons.add("human_rubric_incomplete")

        for index, raw_candidate in enumerate(candidate_list, start=1):
            candidate = _mapping(raw_candidate)
            qa = _mapping(candidate.get("qa") or candidate.get("qaSignals") or candidate)
            (
                tier,
                preview_allowed,
                hard_reject,
                needs_review,
                missing_signal,
                reasons,
                signal_failures,
            ) = _classify_candidate(qa, candidate)
            counts[tier] += 1
            if missing_signal:
                required_signal_unavailable += 1
                failure_reasons.add("required_signal_unavailable")
                required_signal_failure_counts.update(signal_failures)
            if preview_allowed and tier != "hardPass":
                preview_violations += 1
                failure_reasons.add("preview_exposure_violation")
            for reason in reasons:
                if _safe_reason(reason):
                    reject_reasons[reason] += 1

            qa_version = _text(qa.get("qaVersion") or candidate.get("qaVersion"))
            if qa_version:
                qa_versions.add(qa_version)
            debug = _mapping(qa.get("debug"))
            decision_class = _safe_watermark_label(
                debug.get("watermarkDecisionClass", qa.get("watermarkDecisionClass"))
            )
            if decision_class:
                watermark_decision_classes[decision_class] += 1
            for evidence_class in _string_values(
                debug.get(
                    "watermarkEvidenceClasses",
                    qa.get("watermarkEvidenceClasses"),
                )
            ):
                safe_evidence_class = _safe_watermark_label(evidence_class)
                if safe_evidence_class:
                    watermark_evidence_class_counts[safe_evidence_class] += 1
            watermark_signal_values = (
                debug.get("watermarkQaAction", qa.get("watermarkQaAction")),
                debug.get("watermarkDecisionClass", qa.get("watermarkDecisionClass")),
                qa.get("textLogoWatermarkRisk"),
                qa.get("logoTextWatermarkRisk"),
            )
            if any(value not in (None, "") for value in watermark_signal_values):
                watermark_action = resolve_watermark_qa_action(
                    {
                        "watermarkQaAction": watermark_signal_values[0],
                        "watermarkDecisionClass": watermark_signal_values[1],
                        "visualRiskStatus": debug.get(
                            "visualRiskStatus", qa.get("visualRiskStatus")
                        ),
                        "textLogoWatermarkRisk": watermark_signal_values[2],
                        "logoTextWatermarkRisk": watermark_signal_values[3],
                    }
                )
                watermark_qa_actions[watermark_action] += 1
            policy_version = _safe_contract_version(
                debug.get("watermarkPolicyVersion", qa.get("watermarkPolicyVersion"))
            )
            if policy_version:
                watermark_policy_versions.add(policy_version)
            _collect_candidate_metrics(candidate, qa, metric_values)

    # The eligible count is derived from the ordinal/consent pass below; raw
    # participant rows are never retained in the report object.
    eligible_participant_count = sum(
        1
        for raw_row in raw_rows
        if isinstance(raw_row, Mapping)
        and _participant_ordinal(raw_row.get("participantOrdinal")) is not None
        and _consent_is_exact(_mapping(raw_row.get("consent")))
    )
    if eligible_participant_count < MIN_G004_PARTICIPANTS:
        failure_reasons.add("G004_CALIBRATION_INSUFFICIENT_COHORT")
    if invalid_rows:
        failure_reasons.add("participant_evidence_invalid")
    if candidate_count_exceeded:
        failure_reasons.add("candidate_count_exceeded")

    threshold_snapshot_match = _threshold_snapshot_matches(control.get("thresholdSnapshot"), active_artifact)
    if not threshold_snapshot_match:
        failure_reasons.add("threshold_snapshot_mismatch")
    model_version_match = _model_version_match(control.get("thresholdSnapshot"), active_artifact, raw_rows)
    if not model_version_match:
        failure_reasons.add("model_version_mismatch")

    current_qa_wiring = _truthy(control.get("currentQAWiring", control.get("currentQaWiring")))
    if not current_qa_wiring:
        failure_reasons.add("current_qa_wiring_unverified")
    single_run = _single_consistent_run(control, raw_rows)
    if not single_run:
        failure_reasons.add("calibration_run_inconsistent")
    model_outage_fail_closed = _outage_probe_passed(control.get("modelOutage") or control.get("outageProbe"))
    if not model_outage_fail_closed:
        failure_reasons.add("model_outage_not_fail_closed")
    privacy = _privacy_scan_result(control.get("privacyScan"))
    if not privacy["passed"]:
        failure_reasons.add("privacy_scan_missing_or_failed")
    if privacy["secretLeaks"] != 0:
        failure_reasons.add("secret_leak_detected")
    if privacy["privateUrlLeaks"] != 0:
        failure_reasons.add("private_url_leak_detected")
    if privacy["rawBiometricPersistence"] != 0:
        failure_reasons.add("raw_biometric_persistence_detected")
    failure_categories_recorded = total_candidate_count > 0
    if not failure_categories_recorded:
        failure_reasons.add("failure_categories_missing")

    rubric_complete = rubric_complete_count == eligible_participant_count and eligible_participant_count > 0
    if not rubric_complete:
        failure_reasons.add("human_rubric_incomplete")
    consent_complete = eligible_participant_count == len(
        [
            raw_row
            for raw_row in raw_rows
            if isinstance(raw_row, Mapping) and _participant_ordinal(raw_row.get("participantOrdinal")) is not None
        ]
    )
    if not consent_complete:
        failure_reasons.add("exact_consent_incomplete")
    slices_recorded = eligible_participant_count > 0 and len(slice_counts) > 0
    if not slices_recorded:
        failure_reasons.add("cohort_slice_missing")

    human_signoff = _human_signoff_passed(control.get("humanSignoff") or control.get("signoff"))
    machine_gates = {
        "cohort": eligible_participant_count >= MIN_G004_PARTICIPANTS,
        "consent": consent_complete,
        "currentQAWiring": current_qa_wiring,
        "singleRun": single_run,
        "thresholdSnapshot": threshold_snapshot_match,
        "modelVersion": model_version_match,
        "humanRubric": rubric_complete,
        "hardPassEvidence": counts["hardPass"] > 0,
        "hardRejectPreviewExposure": preview_violations == 0,
        "modelOutageFailClosed": model_outage_fail_closed,
        "cohortSlices": slices_recorded,
        "failureCategories": failure_categories_recorded,
        "privacyScan": privacy["passed"],
        "secretLeak": privacy["secretLeaks"] == 0,
        "privateUrlLeak": privacy["privateUrlLeaks"] == 0,
        "rawBiometricPersistence": privacy["rawBiometricPersistence"] == 0,
    }
    machine_pass = all(machine_gates.values())
    g004_pass = machine_pass and human_signoff
    if g004_pass:
        verdict = "PASS_G004_CALIBRATION"
    elif machine_pass:
        verdict = "HUMAN_REVIEW_REQUIRED"
    elif required_signal_unavailable:
        verdict = "BLOCKED_QA_SIGNAL"
    elif "G004_CALIBRATION_INSUFFICIENT_COHORT" in failure_reasons or "threshold_snapshot_mismatch" in failure_reasons:
        verdict = (
            "BLOCKED_QA_CALIBRATION_POLICY"
            if "threshold_snapshot_mismatch" in failure_reasons and eligible_participant_count >= MIN_G004_PARTICIPANTS
            else "BLOCKED_QA_CALIBRATION_DATA"
        )
    else:
        verdict = "BLOCKED_QA_CALIBRATION_DATA"

    report: dict[str, Any] = {
        "schemaVersion": CALIBRATION_EVALUATION_VERSION,
        "verdict": verdict,
        "g004Pass": bool(g004_pass),
        "machinePass": bool(machine_pass),
        "calibrationVersion": active_artifact.calibration_version,
        "participantCount": eligible_participant_count,
        "consentCount": consent_count,
        "candidateCount": total_candidate_count,
        "counts": counts,
        "previewViolations": preview_violations,
        "requiredSignalUnavailable": required_signal_unavailable,
        "requiredSignalFailureCounts": dict(sorted(required_signal_failure_counts.items())),
        "rubricComplete": rubric_complete,
        "rubric": _rubric_aggregate(rubric_scores, rubric_complete_count, eligible_participant_count),
        "humanSignoff": bool(human_signoff),
        "thresholdSnapshotMatch": bool(threshold_snapshot_match),
        "modelVersionMatch": bool(model_version_match),
        "modelOutageFailClosed": bool(model_outage_fail_closed),
        "privacyScan": privacy,
        "failureReasons": sorted(failure_reasons),
        "rejectReasonCounts": dict(sorted(reject_reasons.items())),
        "cohortSlices": dict(sorted(slice_counts.items())),
        "metrics": {name: _metric_summary(values) for name, values in metric_values.items()},
        "qaVersions": sorted(qa_versions),
        "watermarkDecisionClasses": dict(sorted(watermark_decision_classes.items())),
        "watermarkEvidenceClassCounts": dict(sorted(watermark_evidence_class_counts.items())),
        "watermarkQaActions": dict(sorted(watermark_qa_actions.items())),
        "watermarkPolicyVersions": sorted(watermark_policy_versions),
        "gates": {**machine_gates, "humanSignoff": human_signoff},
    }
    return redact_calibration_report(report)


def freeze_threshold_snapshot(
    evidence_rows: Sequence[Mapping[str, Any]],
    *,
    versions: Mapping[str, Any],
    cohort_policy_version: str,
) -> CalibrationArtifact:
    """Freeze thresholds from separated, non-live evidence only.

    A live calibration row can never influence this function.  Each required
    category needs both a safe and an unsafe labeled score with a strict
    separating boundary; otherwise the caller receives a policy blocker.
    """

    if not isinstance(evidence_rows, Sequence) or isinstance(evidence_rows, (str, bytes)) or not evidence_rows:
        raise CalibrationArtifactError("threshold evidence is missing.")
    for row in evidence_rows:
        if not isinstance(row, Mapping):
            raise CalibrationArtifactError("threshold evidence row is invalid.")
        phase = _text(row.get("phase") or row.get("evidencePhase")).lower()
        if phase in {"live", "post_live", "post-live", "calibration_run"}:
            raise CalibrationArtifactError("live threshold evidence is not allowed.")
        _reject_raw_evidence_fields(row)

    version_map = dict(versions or {})
    calibration_version = _required_text(version_map.get("calibrationVersion"), "versions.calibrationVersion")
    created_at = _required_text(version_map.get("createdAt"), "versions.createdAt")
    git_revision = _required_text(version_map.get("gitRevision"), "versions.gitRevision")
    qa_contract_version = _required_text(version_map.get("qaContractVersion"), "versions.qaContractVersion")
    model_versions = _mapping(version_map.get("modelVersions"))
    preprocessing_versions = _mapping(version_map.get("preprocessingVersions"))
    if not model_versions or not preprocessing_versions:
        raise CalibrationArtifactError("threshold evidence versions are incomplete.")
    cohort_policy = _required_text(cohort_policy_version, "cohort_policy_version")

    face_points = _evidence_points(evidence_rows, "faceSimilarity")
    face_threshold, face_margin, face_summary = _separated_threshold(face_points, "faceSimilarity", higher_is_risk=True)
    clip_thresholds: dict[str, float] = {}
    clip_summaries: list[str] = []
    for key in CLIP_RISK_KEYS:
        threshold, _, summary = _separated_threshold(
            _evidence_points(evidence_rows, "clipSafety", key),
            f"clipSafety.{key}",
            higher_is_risk=True,
        )
        clip_thresholds[key] = threshold
        clip_summaries.append(summary)
    minimum_scores: dict[str, float] = {}
    for key in CLIP_MINIMUM_KEYS:
        threshold, _, summary = _separated_threshold(
            _evidence_points(evidence_rows, "clipSafety", key),
            f"clipSafety.{key}",
            higher_is_risk=False,
        )
        minimum_scores[key] = threshold
        clip_summaries.append(summary)

    face_model = _required_text(model_versions.get("faceSimilarity"), "modelVersions.faceSimilarity")
    clip_model = _required_text(model_versions.get("clipSafety"), "modelVersions.clipSafety")
    artifact_value: dict[str, Any] = {
        "schemaVersion": "avatar_qa_calibration_v1",
        "calibrationVersion": calibration_version,
        "createdAt": created_at,
        "gitRevision": git_revision,
        "qaContractVersion": qa_contract_version,
        "cohortPolicyVersion": cohort_policy,
        "modelVersions": model_versions,
        "preprocessingVersions": preprocessing_versions,
        "faceSimilarity": {
            "model": face_model,
            "metric": "cosine",
            "semanticRole": "identity_privacy_upper_bound",
            "threshold": face_threshold,
            "thresholdDirection": "gte_review",
            "reviewMargin": face_margin,
            "evidenceSummary": face_summary,
        },
        "clipSafety": {
            "model": clip_model,
            "thresholds": clip_thresholds,
            "minimumScores": minimum_scores,
            "evidenceSummary": "; ".join(clip_summaries),
        },
        "humanReviewPolicy": {
            "rubricVersion": _text(version_map.get("rubricVersion")) or "g004-v1",
        },
    }
    artifact_value["integrity"] = {"sha256": canonical_artifact_sha256(artifact_value)}
    return CalibrationArtifact.from_mapping(artifact_value)


def redact_calibration_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shareable report containing only redacted scalar evidence."""

    if not isinstance(report, Mapping):
        return {}
    return _redact_value(report, key_path="")


def _coerce_artifact(value: CalibrationArtifact | Mapping[str, Any]) -> CalibrationArtifact:
    if isinstance(value, CalibrationArtifact):
        return value
    if isinstance(value, Mapping):
        return CalibrationArtifact.from_mapping(value)
    raise CalibrationArtifactError("calibration artifact is invalid.")


def _classify_candidate(
    qa: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> tuple[str, bool, bool, bool, bool, tuple[str, ...], tuple[str, ...]]:
    decision = _mapping(qa.get("decision") or candidate.get("decision"))
    tier = _normalize_tier(
        decision.get("selectionTier")
        or qa.get("selectionTier")
        or candidate.get("selectionTier")
    )
    preview = _strict_bool(
        decision.get("previewAllowed")
        if "previewAllowed" in decision
        else qa.get("previewAllowed", candidate.get("previewAllowed", False))
    )
    reasons = _string_values(
        decision.get("hardRejectReasons")
        or qa.get("rejectReasons")
        or candidate.get("rejectReasons")
    )
    hard_reject = tier == "hardReject" or bool(reasons)
    availability = _availability_map(qa, candidate)
    signal_failures = required_signal_failure_codes(availability)
    missing_signal = bool(signal_failures)
    requires_review = (
        tier == "needsReview"
        or _strict_bool(decision.get("requiresHumanReview"))
        or _strict_bool(qa.get("requiresHumanReview"))
        or missing_signal
    )
    if hard_reject:
        final_tier = "hardReject"
    elif requires_review or not preview and tier == "hardPass":
        final_tier = "needsReview"
    elif tier == "hardPass" and preview:
        final_tier = "hardPass"
    elif tier == "softPass":
        final_tier = "softPass"
    else:
        final_tier = "needsReview"
    return (
        final_tier,
        preview,
        hard_reject,
        requires_review,
        missing_signal,
        tuple(reasons),
        signal_failures,
    )


def _availability_map(qa: Mapping[str, Any], candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    for value in (
        qa.get("modelAvailability"),
        _mapping(_mapping(qa.get("debug")).get("modelAvailability")),
        candidate.get("modelAvailability"),
    ):
        if isinstance(value, Mapping):
            return value
    return {}


def _required_signals_available(availability: Mapping[str, Any]) -> bool:
    return not required_signal_failure_codes(availability)


def _collect_candidate_metrics(
    candidate: Mapping[str, Any],
    qa: Mapping[str, Any],
    values: dict[str, list[float]],
) -> None:
    metrics = _mapping(candidate.get("metrics"))
    for name in ("latencyMs", "costUsd"):
        number = _finite_number(metrics.get(name, candidate.get(name)))
        if number is not None and number >= 0:
            values[name].append(number)
    coverage = _finite_number(
        qa.get("traitCoverage", candidate.get("traitCoverage", metrics.get("traitCoverage")))
    )
    if coverage is not None and 0.0 <= coverage <= 1.0:
        values["traitCoverage"].append(coverage)


def _metric_summary(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "p50": None, "p95": None}
    ordered = sorted(float(value) for value in values)
    return {
        "count": len(ordered),
        "p50": _percentile(ordered, 0.50),
        "p95": _percentile(ordered, 0.95),
    }


def _percentile(values: Sequence[float], fraction: float) -> float:
    if len(values) == 1:
        return round(float(values[0]), 3)
    position = (len(values) - 1) * fraction
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return round(float(values[lower]), 3)
    weight = position - lower
    return round(float(values[lower] + (values[upper] - values[lower]) * weight), 3)


def _human_review_for_row(
    row: Mapping[str, Any],
    control: Mapping[str, Any],
    ordinal: str,
) -> Mapping[str, Any]:
    direct = row.get("humanReview")
    if isinstance(direct, Mapping):
        return direct
    by_participant = _mapping(control.get("byParticipant") or control.get("participants"))
    candidate = by_participant.get(ordinal)
    return candidate if isinstance(candidate, Mapping) else {}


def _rubric_is_complete(value: Mapping[str, Any]) -> bool:
    if not isinstance(value, Mapping) or value.get("reviewerPresent") is not True:
        return False
    for field in RUBRIC_SCORE_FIELDS:
        score = value.get(field)
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 1 <= float(score) <= 5:
            return False
    safety = _text(value.get("safety")).lower()
    if safety not in RUBRIC_SAFETY_VALUES:
        return False
    return isinstance(value.get("usableCandidate"), bool) and isinstance(value.get("regenerationNeeded"), bool)


def _rubric_aggregate(
    scores: Mapping[str, Sequence[float]],
    completed: int,
    eligible: int,
) -> dict[str, Any]:
    return {
        "completedParticipants": int(completed),
        "eligibleParticipants": int(eligible),
        "scores": {field: _metric_summary(values) for field, values in scores.items()},
    }


def _threshold_snapshot_matches(value: Any, artifact: CalibrationArtifact) -> bool:
    snapshot = _mapping(value)
    if not snapshot:
        return False
    expected_integrity = _mapping(artifact.payload.get("integrity")).get("sha256")
    actual_integrity = snapshot.get("artifactSha256") or snapshot.get("sha256")
    if _text(snapshot.get("calibrationVersion")) != artifact.calibration_version:
        return False
    if _text(actual_integrity).lower() != _text(expected_integrity).lower():
        return False
    return _mapping_equal(snapshot.get("modelVersions"), artifact.model_versions) and _mapping_equal(
        snapshot.get("preprocessingVersions"), artifact.preprocessing_versions
    )


def _model_version_match(
    snapshot_value: Any,
    artifact: CalibrationArtifact,
    rows: Sequence[Mapping[str, Any]],
) -> bool:
    if not _threshold_snapshot_matches(snapshot_value, artifact):
        return False
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        for candidate in row.get("candidates", ()) if isinstance(row.get("candidates"), Sequence) else ():
            if not isinstance(candidate, Mapping):
                continue
            candidate_versions = _mapping(candidate.get("modelVersions") or _mapping(candidate.get("qa")).get("modelVersions"))
            if candidate_versions and not _mapping_equal(candidate_versions, artifact.model_versions):
                return False
    return True


def _single_consistent_run(control: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> bool:
    if "singleRun" in control:
        return control.get("singleRun") is True
    run_ids = {
        _text(row.get("calibrationRunId") or row.get("runId"))
        for row in rows
        if isinstance(row, Mapping) and _text(row.get("calibrationRunId") or row.get("runId"))
    }
    expected = _text(control.get("calibrationRunId") or control.get("runId"))
    return bool(expected and (not run_ids or run_ids == {expected}))


def _outage_probe_passed(value: Any) -> bool:
    probe = _mapping(value)
    if not probe or probe.get("tested") is not True:
        return False
    if probe.get("failClosed") is True:
        return True
    preview = probe.get("previewAllowed")
    decision = _text(probe.get("decision") or probe.get("status")).lower()
    return preview is False and decision in {"needs_review", "review", "unavailable", "blocked"}


def _privacy_scan_result(value: Any) -> dict[str, Any]:
    scan = _mapping(value)
    counters = _mapping(scan.get("leakCounters"))
    def count(*names: str) -> int:
        for name in names:
            if name in scan:
                return _nonnegative_int(scan.get(name))
            if name in counters:
                return _nonnegative_int(counters.get(name))
        return 0

    secret_leaks = count("secretLeaks", "secretLeakCount", "secrets")
    private_url_leaks = count("privateUrlLeaks", "privateUrlLeakCount", "signedUrlLeaks")
    raw_biometrics = count("rawBiometricPersistence", "rawBiometricCount", "embeddingLeaks")
    passed = scan.get("passed") is True and secret_leaks == 0 and private_url_leaks == 0 and raw_biometrics == 0
    return {
        "passed": bool(passed),
        "secretLeaks": secret_leaks,
        "privateUrlLeaks": private_url_leaks,
        "rawBiometricPersistence": raw_biometrics,
    }


def _human_signoff_passed(value: Any) -> bool:
    if value is True:
        return True
    mapping = _mapping(value)
    return mapping.get("approved") is True or mapping.get("complete") is True


def _consent_is_exact(consent: Mapping[str, Any]) -> bool:
    if consent.get("exact") is not True:
        return False
    for key in (
        "calibrationPurpose",
        "sourceImageUse",
        "azureExternalAiProcessing",
        "qaScoring",
        "humanReview",
    ):
        if consent.get(key) is not True:
            return False
    return bool(_text(consent.get("temporaryRetention")) and _text(consent.get("calibrationVersion")))


def _participant_ordinal(value: Any) -> str | None:
    text = _text(value).upper()
    return text if _ORDINAL_PATTERN.fullmatch(text) else None


def _redacted_slice(value: Any) -> dict[str, str]:
    source = _mapping(value)
    result: dict[str, str] = {}
    for key in ("background", "eyewear", "hair", "onboardingGender"):
        text = _text(source.get(key)).lower()
        if text and _safe_dimension(text):
            result[key] = text
    return result


def _safe_dimension(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9_-]{1,40}", value))


def _slice_key(value: Mapping[str, str]) -> str:
    return "|".join(f"{key}={value[key]}" for key in ("background", "eyewear", "hair", "onboardingGender") if key in value)


def _evidence_points(rows: Sequence[Mapping[str, Any]], section: str, category: str | None = None) -> list[tuple[float, str]]:
    points: list[tuple[float, str]] = []
    for row in rows:
        container = _mapping(row.get(section))
        if category is not None:
            container = _mapping(container.get(category))
        if not container:
            continue
        score = _finite_number(container.get("score"))
        label = _text(container.get("label")).lower()
        if score is None or not 0.0 <= score <= 1.0 or label not in (_SAFE_LABELS | _RISK_LABELS):
            continue
        points.append((score, label))
    return points


def _separated_threshold(
    points: Sequence[tuple[float, str]],
    name: str,
    *,
    higher_is_risk: bool,
) -> tuple[float, float, str]:
    safe = [score for score, label in points if label in _SAFE_LABELS]
    risk = [score for score, label in points if label in _RISK_LABELS]
    if not safe or not risk:
        raise CalibrationArtifactError(f"threshold evidence is incomplete: {name}")
    if higher_is_risk:
        safe_edge = max(safe)
        risk_edge = min(risk)
    else:
        safe_edge = min(safe)
        risk_edge = max(risk)
    if higher_is_risk and not safe_edge < risk_edge:
        raise CalibrationArtifactError(f"threshold evidence overlaps: {name}")
    if not higher_is_risk and not risk_edge < safe_edge:
        raise CalibrationArtifactError(f"threshold evidence overlaps: {name}")
    threshold = (safe_edge + risk_edge) / 2.0
    margin = abs(risk_edge - safe_edge) / 2.0
    return round(threshold, 6), round(min(1.0, margin), 6), f"pre_live_n={len(points)};separated=true"


def _reject_raw_evidence_fields(value: Any, path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            normalized = key_text.replace("_", "").replace("-", "").lower()
            child_path = f"{path}.{key_text}" if path else key_text
            if any(fragment in normalized for fragment in _FORBIDDEN_KEY_FRAGMENTS):
                raise CalibrationArtifactError(f"forbidden threshold evidence field: {child_path}")
            _reject_raw_evidence_fields(child, child_path)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            _reject_raw_evidence_fields(child, f"{path}.{index}")


def _redact_value(value: Any, *, key_path: str) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            normalized = key_text.replace("_", "").replace("-", "").lower()
            if normalized == "sourceimageuse" and isinstance(child, bool):
                result[key_text] = child
                continue
            if _is_forbidden_output_key(normalized):
                continue
            result[key_text] = _redact_value(child, key_path=f"{key_path}.{key_text}" if key_path else key_text)
        return result
    if isinstance(value, (list, tuple)):
        return [_redact_value(item, key_path=key_path) for item in value]
    if isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in _FORBIDDEN_TEXT_MARKERS) or re.search(r"\buid[-_:][a-z0-9-]+", lowered):
            return "[redacted]"
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value.__class__.__name__)


def _is_forbidden_output_key(normalized: str) -> bool:
    if normalized in {"participantordinal", "candidateordinal", "calibrationversion", "modelversions", "preprocessingversions"}:
        return False
    return bool(
        any(fragment in normalized for fragment in _FORBIDDEN_KEY_FRAGMENTS)
        or any(fragment in normalized for fragment in _FORBIDDEN_HASH_KEY_FRAGMENTS)
        or normalized.startswith("sha")
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_equal(left: Any, right: Mapping[str, Any]) -> bool:
    value = _mapping(left)
    return dict(value) == dict(right)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _required_text(value: Any, name: str) -> str:
    text = _text(value)
    if not text:
        raise CalibrationArtifactError(f"{name} is required.")
    return text


def _strict_bool(value: Any) -> bool:
    return value is True


def _truthy(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() in {"true", "yes", "pass"})


def _normalize_tier(value: Any) -> str:
    normalized = _text(value).lower().replace("-", "_").replace(" ", "_")
    return {
        "hard_pass": "hardPass",
        "soft_pass": "softPass",
        "needs_review": "needsReview",
        "hard_reject": "hardReject",
    }.get(normalized, "needsReview")


def _string_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    return ()


def _safe_reason(value: str) -> bool:
    return bool(_SAFE_REASON_PATTERN.fullmatch(value))


def _safe_watermark_label(value: Any) -> str:
    normalized = _text(value).lower().replace("-", "_").replace(" ", "_")
    return normalized if _safe_reason(normalized) else ""


def _safe_contract_version(value: Any) -> str:
    normalized = _text(value).lower()
    return normalized if re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,79}", normalized) else ""


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _nonnegative_int(value: Any) -> int:
    number = _finite_number(value)
    return max(0, int(number)) if number is not None else 0


__all__ = [
    "CLIP_MINIMUM_KEYS",
    "CLIP_RISK_KEYS",
    "CALIBRATION_EVALUATION_VERSION",
    "MIN_G004_PARTICIPANTS",
    "evaluate_calibration_rows",
    "freeze_threshold_snapshot",
    "redact_calibration_report",
]
