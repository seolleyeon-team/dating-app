"""Privacy-safe, local-only preparation for the G004 watermark benchmark.

This module deliberately does not open candidate images, call Azure, invoke a
remote service, or import the production QA decision path.  It extracts only
the already-redacted v9 machine fields and prepares a human-label checkpoint.
The post-label metric functions are kept here so the same ordinal join is used
when the operator later resumes the benchmark.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable, Mapping, Sequence


BENCHMARK_VERSION = "g004_watermark_calibration_benchmark_v1"
WORKSHEET_SCHEMA_VERSION = "g004_watermark_human_labels_v1"
PENDING_LABEL_STATUS = "PENDING"
HUMAN_LABEL_FIELDS = (
    "candidateVisualClass",
    "sameVisibleMarkInSource",
    "overlayAppearance",
    "humanLabelConfidence",
)
OPTIONAL_HUMAN_FIELDS = ("location",)

VALID_CANDIDATE_CLASSES = {
    "no_visible_text_or_logo",
    "benign_text_or_logo",
    "clear_watermark_or_brand_overlay",
    "uncertain",
}
VALID_SOURCE_MARK_VALUES = {"yes", "no", "not_applicable", "uncertain"}
VALID_OVERLAY_VALUES = {"yes", "no", "uncertain"}
VALID_CONFIDENCE_VALUES = {"high", "medium", "low"}
VALID_LOCATIONS = {"corner", "edge", "clothing_zone", "central", "none", "uncertain"}
VALID_SOURCE_CONSISTENCY = {"consistent", "mixed", "inconsistent", "unknown", "not_available", "not_applicable"}
VALID_WATERMARK_CLASSES = {
    "no_text_detected",
    "source_consistent_clothing_text",
    "source_consistent_text_or_logo",
    "text_evidence_non_blocking",
    "benign_text_or_logo",
    "ambiguous_text_evidence",
    "overlay_watermark",
    "generated_overlay_logo",
    "identifiable_brand_logo",
    "generated_text_artifact",
}
VALID_WATERMARK_ACTIONS = {"allow", "review", "reject"}
VALID_RISK_VALUES = {"low", "medium", "high"}
VALID_TIERS = {"hard_pass", "soft_pass", "needs_review", "hard_reject", "not_previewable"}
VALID_VISUAL_STATUSES = {"available", "needs_review", "critical_unavailable", "unavailable"}

_ORDINAL_PATTERN = re.compile(r"^P[0-9]{2,}$")
_URI_PATTERN = re.compile(r"(?i)(?:https?|gs|gcs)://")
_EMAIL_PATTERN = re.compile(r"(?i)\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_SIGNED_MARKERS = ("x-goog-signature", "x-amz-signature", "sig=")
_FORBIDDEN_KEYS = {
    "uid",
    "email",
    "sourcephotoref",
    "sourceurl",
    "signedurl",
    "imagepath",
    "privatepath",
    "bbox",
    "coordinates",
    "coordinate",
    "imagebytes",
    "embedding",
    "rawlabel",
    "rawocrtext",
    "brandname",
    "schoolname",
    "personname",
}
_MACHINE_EVIDENCE_KEYS = (
    "ocrDetectionCount",
    "recognizedTokenCount",
    "repeatedTokenCount",
    "confidenceBands",
    "areaBands",
    "locationBands",
    "sourceConsistency",
)
_BAND_KEYS = {
    "low",
    "medium",
    "high",
    "unknown",
    "small",
    "large",
    "corner",
    "edge",
    "central",
    "clothing_zone",
}


class LabelValidationError(ValueError):
    """Raised when a human-label worksheet is incomplete or malformed."""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _safe_mapping_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for key, raw_count in value.items():
        label = str(key)
        count = _safe_nonnegative_int(raw_count)
        if label in _BAND_KEYS and count is not None:
            result[label] = count
    return dict(sorted(result.items()))


def _safe_enum(value: Any, allowed: set[str]) -> str | None:
    text = str(value or "").strip()
    return text if text in allowed else None


def _safe_contract_version(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text if re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,99}", text) else None


def _safe_bool(value: Any) -> bool:
    return value is True


def _participant_ordinal(value: Any) -> str:
    ordinal = str(value or "").strip()
    if not _ORDINAL_PATTERN.fullmatch(ordinal):
        raise ValueError("invalid participant ordinal")
    return ordinal


def _candidate_ordinal(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("invalid candidate ordinal")
    try:
        ordinal = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid candidate ordinal") from exc
    if ordinal < 1 or ordinal > 4:
        raise ValueError("invalid candidate ordinal")
    return ordinal


def _candidate_rows(recovery: Mapping[str, Any]) -> list[tuple[str, int, Mapping[str, Any]]]:
    qa_evaluation = _mapping(recovery.get("qaEvaluation"))
    rows = qa_evaluation.get("rows")
    if not isinstance(rows, list):
        raise ValueError("v9 qaEvaluation rows are missing")

    result: list[tuple[str, int, Mapping[str, Any]]] = []
    seen: set[tuple[str, int]] = set()
    for raw_row in rows:
        row = _mapping(raw_row)
        participant = _participant_ordinal(row.get("participantOrdinal"))
        candidates = row.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError("candidate rows are missing")
        for raw_candidate in candidates:
            candidate = _mapping(raw_candidate)
            candidate_ordinal = _candidate_ordinal(candidate.get("candidateOrdinal"))
            key = (participant, candidate_ordinal)
            if key in seen:
                raise ValueError("duplicate candidate ordinal")
            seen.add(key)
            result.append((participant, candidate_ordinal, candidate))

    if len(result) != 20 or len({participant for participant, _, _ in result}) != 5:
        raise ValueError("expected exactly five participants and twenty candidates")
    return sorted(result, key=lambda item: (item[0], item[1]))


def extract_machine_evidence(recovery: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract only redacted, ordinal-keyed machine evidence from v9."""

    machine_rows: list[dict[str, Any]] = []
    for participant, candidate_ordinal, candidate in _candidate_rows(recovery):
        qa = _mapping(candidate.get("qa"))
        debug = _mapping(qa.get("debug"))
        evidence = _mapping(debug.get("watermarkEvidence"))
        watermark_action = _safe_enum(
            debug.get("watermarkQaAction", qa.get("watermarkQaAction")),
            VALID_WATERMARK_ACTIONS,
        )
        reject_reasons = qa.get("rejectReasons")
        hard_reject = (
            isinstance(reject_reasons, list) and "logo_text_watermark" in reject_reasons
        ) or _safe_bool(debug.get("hardReject")) or watermark_action == "reject"
        machine_rows.append(
            {
                "participantOrdinal": participant,
                "candidateOrdinal": candidate_ordinal,
                "ocrDetectionCount": _safe_nonnegative_int(evidence.get("ocrDetectionCount")),
                "recognizedTokenCount": _safe_nonnegative_int(evidence.get("recognizedTokenCount")),
                "repeatedTokenCount": _safe_nonnegative_int(evidence.get("repeatedTokenCount")),
                "confidenceBands": _safe_mapping_counts(evidence.get("confidenceBands")),
                "areaBands": _safe_mapping_counts(evidence.get("areaBands")),
                "locationBands": _safe_mapping_counts(evidence.get("locationBands")),
                "sourceConsistency": _safe_enum(evidence.get("sourceConsistency"), VALID_SOURCE_CONSISTENCY),
                "watermarkDecisionClass": _safe_enum(
                    debug.get("watermarkDecisionClass"), VALID_WATERMARK_CLASSES
                ),
                "watermarkEvidenceClasses": [
                    item
                    for item in (
                        _safe_enum(value, VALID_WATERMARK_CLASSES)
                        for value in debug.get("watermarkEvidenceClasses", [])
                    )
                    if item is not None
                ],
                "watermarkQaAction": watermark_action,
                "watermarkPolicyVersion": _safe_contract_version(
                    debug.get("watermarkPolicyVersion", qa.get("watermarkPolicyVersion"))
                ),
                "hardReject": hard_reject,
                "needsReview": _safe_bool(qa.get("requiresHumanReview")),
                "textLogoWatermarkRisk": _safe_enum(
                    qa.get("textLogoWatermarkRisk"), VALID_RISK_VALUES
                ),
                "logoTextWatermarkRisk": _safe_enum(
                    qa.get("logoTextWatermarkRisk"), VALID_RISK_VALUES
                ),
                "visualRiskStatus": _safe_enum(
                    debug.get("visualRiskStatus"), VALID_VISUAL_STATUSES
                ),
                "selectionTier": _safe_enum(candidate.get("selectionTier"), VALID_TIERS),
            }
        )
    assert_privacy_safe(machine_rows)
    return machine_rows


def build_human_label_worksheet(recovery: Mapping[str, Any]) -> dict[str, Any]:
    """Build the ordinal-only worksheet; never infer a human label."""

    candidates = _candidate_rows(recovery)
    worksheet = {
        "schemaVersion": WORKSHEET_SCHEMA_VERSION,
        "benchmarkVersion": BENCHMARK_VERSION,
        "participantCount": len({participant for participant, _, _ in candidates}),
        "candidateCount": len(candidates),
        "humanLabelStatus": PENDING_LABEL_STATUS,
        "reviewerRole": "human_operator",
        "reviewAccess": "existing_authenticated_private_g004_review_boundary",
        "rows": [
            {
                "participantOrdinal": participant,
                "candidateOrdinal": candidate_ordinal,
                "candidateVisualClass": None,
                "sameVisibleMarkInSource": None,
                "overlayAppearance": None,
                "humanLabelConfidence": None,
                "location": None,
            }
            for participant, candidate_ordinal, _ in candidates
        ],
    }
    assert_privacy_safe(worksheet)
    return worksheet


def validate_label_rows(rows: Sequence[Mapping[str, Any]], *, expected_count: int = 20) -> None:
    """Validate completed human labels; ``uncertain`` remains a valid value."""

    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise LabelValidationError("label rows must be a sequence")
    if len(rows) != expected_count:
        raise LabelValidationError("label row count is incomplete")

    seen: set[tuple[str, int]] = set()
    for row_value in rows:
        row = _mapping(row_value)
        try:
            key = (_participant_ordinal(row.get("participantOrdinal")), _candidate_ordinal(row.get("candidateOrdinal")))
        except ValueError as exc:
            raise LabelValidationError("invalid ordinal") from exc
        if key in seen:
            raise LabelValidationError("duplicate ordinal")
        seen.add(key)

        candidate_class = _nonempty_label(row, "candidateVisualClass", VALID_CANDIDATE_CLASSES)
        _nonempty_label(row, "sameVisibleMarkInSource", VALID_SOURCE_MARK_VALUES)
        _nonempty_label(row, "overlayAppearance", VALID_OVERLAY_VALUES)
        _nonempty_label(row, "humanLabelConfidence", VALID_CONFIDENCE_VALUES)
        location = row.get("location")
        if location not in (None, "") and _safe_enum(location, VALID_LOCATIONS) is None:
            raise LabelValidationError("invalid location")
        if candidate_class is None:  # pragma: no cover - guarded by helper
            raise LabelValidationError("invalid candidate class")

    assert_privacy_safe(rows)


def _nonempty_label(row: Mapping[str, Any], key: str, allowed: set[str]) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip() or value.strip() not in allowed:
        raise LabelValidationError(f"invalid or empty {key}")
    return value.strip()


def wilson_interval(successes: int, trials: int, *, z: float = 1.959963984540054) -> dict[str, float | None]:
    """Return a two-sided Wilson 95% interval without inventing an acceptance threshold."""

    if isinstance(successes, bool) or isinstance(trials, bool):
        raise ValueError("counts must be integers")
    if successes < 0 or trials < 0 or successes > trials:
        raise ValueError("invalid interval counts")
    if trials == 0:
        return {"low": None, "high": None}
    n = float(trials)
    p = float(successes) / n
    z_squared = z * z
    denominator = 1.0 + z_squared / n
    center = (p + z_squared / (2.0 * n)) / denominator
    margin = z * math.sqrt((p * (1.0 - p) / n) + (z_squared / (4.0 * n * n))) / denominator
    return {
        "low": round(max(0.0, center - margin), 6),
        "high": round(min(1.0, center + margin), 6),
    }


def _metric(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": None if denominator == 0 else round(numerator / float(denominator), 6),
        "wilson95": wilson_interval(numerator, denominator),
    }


def _machine_key(row: Mapping[str, Any]) -> tuple[str, int]:
    return (_participant_ordinal(row.get("participantOrdinal")), _candidate_ordinal(row.get("candidateOrdinal")))


def _machine_bool(row: Mapping[str, Any], key: str) -> bool:
    return row.get(key) is True


def _machine_ocr_count(row: Mapping[str, Any]) -> int:
    count = _safe_nonnegative_int(row.get("ocrDetectionCount"))
    return count if count is not None else 0


def _participant_metric_rows(joined: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]]) -> dict[str, Any]:
    grouped: dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = defaultdict(list)
    for human, machine in joined:
        grouped[str(human["participantOrdinal"])].append((human, machine))
    result: dict[str, Any] = {}
    for participant in sorted(grouped):
        rows = grouped[participant]
        no_visible = [item for item in rows if item[0].get("candidateVisualClass") == "no_visible_text_or_logo"]
        benign_or_safe = [
            item
            for item in rows
            if item[0].get("candidateVisualClass") in {"no_visible_text_or_logo", "benign_text_or_logo"}
        ]
        clear = [item for item in rows if item[0].get("candidateVisualClass") == "clear_watermark_or_brand_overlay"]
        result[participant] = {
            "candidateCount": len(rows),
            "textRegionFalsePositiveRate": _metric(
                sum(_machine_ocr_count(machine) > 0 for _, machine in no_visible), len(no_visible)
            ),
            "ambiguousReviewFalsePositiveRate": _metric(
                sum(machine.get("watermarkDecisionClass") == "ambiguous_text_evidence" for _, machine in no_visible),
                len(no_visible),
            ),
            "hardRejectFalsePositiveRate": _metric(
                sum(_machine_bool(machine, "hardReject") for _, machine in benign_or_safe), len(benign_or_safe)
            ),
            "watermarkSafetyCaptureRate": _metric(
                sum(_machine_bool(machine, "hardReject") or _machine_bool(machine, "needsReview") for _, machine in clear),
                len(clear),
            ),
        }
    return result


def compute_metrics(
    human_rows: Sequence[Mapping[str, Any]],
    machine_rows: Sequence[Mapping[str, Any]],
    *,
    expected_count: int = 20,
) -> dict[str, Any]:
    """Join labels to v9 evidence and compute measurement-only metrics."""

    validate_label_rows(human_rows, expected_count=expected_count)
    machine_index = {_machine_key(row): row for row in machine_rows}
    if len(machine_index) != len(machine_rows) or len(machine_index) != expected_count:
        raise ValueError("machine evidence rows are incomplete")
    human_index = {_machine_key(row): row for row in human_rows}
    if set(human_index) != set(machine_index):
        raise ValueError("human and machine ordinals do not match")
    joined = [(human_index[key], machine_index[key]) for key in sorted(human_index)]

    no_visible = [item for item in joined if item[0].get("candidateVisualClass") == "no_visible_text_or_logo"]
    benign_or_safe = [
        item
        for item in joined
        if item[0].get("candidateVisualClass") in {"no_visible_text_or_logo", "benign_text_or_logo"}
    ]
    benign_source = [
        item
        for item in joined
        if item[0].get("candidateVisualClass") == "benign_text_or_logo"
        and item[0].get("sameVisibleMarkInSource") == "yes"
    ]
    clear_watermarks = [
        item for item in joined if item[0].get("candidateVisualClass") == "clear_watermark_or_brand_overlay"
    ]

    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for human, machine in joined:
        confusion[str(human.get("candidateVisualClass"))][
            str(machine.get("watermarkDecisionClass") or "unavailable")
        ] += 1

    source_cross_table: dict[str, Counter[str]] = defaultdict(Counter)
    source_eligible = []
    source_available = []
    for human, machine in joined:
        human_source = human.get("sameVisibleMarkInSource")
        machine_source = machine.get("sourceConsistency")
        source_cross_table[str(human_source)][str(machine_source or "unavailable")] += 1
        if human_source in {"yes", "no"}:
            source_eligible.append((human_source, machine_source))
            if machine_source in {"consistent", "inconsistent"}:
                source_available.append((human_source, machine_source))

    source_agreement_numerator = sum(
        (human_source == "yes" and machine_source == "consistent")
        or (human_source == "no" and machine_source == "inconsistent")
        for human_source, machine_source in source_available
    )
    source_consistent_true_positives = sum(
        machine.get("sourceConsistency") == "consistent" for _, machine in benign_source
    )
    benign_ambiguity = sum(
        machine.get("watermarkDecisionClass") == "ambiguous_text_evidence" for _, machine in benign_source
    )
    safety_capture = sum(
        _machine_bool(machine, "hardReject") or _machine_bool(machine, "needsReview")
        for _, machine in clear_watermarks
    )
    misses = sum(
        not _machine_bool(machine, "hardReject")
        and not _machine_bool(machine, "needsReview")
        and (
            _machine_ocr_count(machine) == 0
            or machine.get("textLogoWatermarkRisk") == "low"
            or machine.get("watermarkDecisionClass") == "no_text_detected"
        )
        for _, machine in clear_watermarks
    )

    return {
        "benchmarkVersion": BENCHMARK_VERSION,
        "candidateCount": len(joined),
        "humanClassCounts": dict(sorted(Counter(
            str(human.get("candidateVisualClass")) for human, _ in joined
        ).items())),
        "humanConfidenceCounts": dict(sorted(Counter(
            str(human.get("humanLabelConfidence")) for human, _ in joined
        ).items())),
        "uncertainHumanCount": sum(
            human.get("candidateVisualClass") == "uncertain" for human, _ in joined
        ),
        "confusionTable": {
            human_class: dict(sorted(classes.items()))
            for human_class, classes in sorted(confusion.items())
        },
        "textRegionFalsePositiveRate": _metric(
            sum(_machine_ocr_count(machine) > 0 for _, machine in no_visible), len(no_visible)
        ),
        "ambiguousReviewFalsePositiveRate": _metric(
            sum(machine.get("watermarkDecisionClass") == "ambiguous_text_evidence" for _, machine in no_visible),
            len(no_visible),
        ),
        "hardRejectFalsePositiveRate": _metric(
            sum(_machine_bool(machine, "hardReject") for _, machine in benign_or_safe), len(benign_or_safe)
        ),
        "watermarkSafetyCaptureRate": _metric(safety_capture, len(clear_watermarks)),
        "watermarkMissRate": _metric(misses, len(clear_watermarks)),
        "sourceConsistencyTruePositiveRate": _metric(source_consistent_true_positives, len(benign_source)),
        "benignSourceTextAmbiguityRate": _metric(benign_ambiguity, len(benign_source)),
        "sourceConsistencyAgreement": {
            "agreementNumerator": source_agreement_numerator,
            "eligibleDenominator": len(source_eligible),
            "availableDenominator": len(source_available),
            "coverage": (
                None
                if not source_eligible
                else round(len(source_available) / float(len(source_eligible)), 6)
            ),
            "agreementOnAvailable": (
                None
                if not source_available
                else round(source_agreement_numerator / float(len(source_available)), 6)
            ),
            "wilson95": wilson_interval(source_agreement_numerator, len(source_available)),
        },
        "sourceConsistencyCrossTable": {
            human_value: dict(sorted(values.items()))
            for human_value, values in sorted(source_cross_table.items())
        },
        "participantResults": _participant_metric_rows(joined),
    }


def assert_privacy_safe(value: Any) -> None:
    """Reject private references, raw OCR, coordinates, and binary payloads."""

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
                if normalized in _FORBIDDEN_KEYS or normalized.startswith("raw"):
                    raise ValueError("forbidden privacy field")
                walk(child)
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                walk(child)
            return
        if isinstance(node, (bytes, bytearray)):
            raise ValueError("binary payload is forbidden")
        if isinstance(node, str):
            lowered = node.lower()
            if _URI_PATTERN.search(node) or _EMAIL_PATTERN.search(node) or any(marker in lowered for marker in _SIGNED_MARKERS):
                raise ValueError("private reference is forbidden")

    walk(value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("JSON artifact could not be read") from exc
    if not isinstance(value, Mapping):
        raise ValueError("JSON artifact must be an object")
    return value


def _git_revision(repo_root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "unknown"
    if completed.returncode != 0:
        return "unknown"
    value = completed.stdout.strip()
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else "unknown"


def inspect_local_runtime(*, model_id: str = "microsoft/Florence-2-large-ft") -> dict[str, Any]:
    """Inspect installed local dependencies without loading/downloading a model."""

    runtime: dict[str, Any] = {
        "modelId": model_id,
        "processor": "Florence2Processor",
        "tasks": ["<OCR_WITH_REGION>", "<OD>"],
        "includeDetailedCaption": False,
        "localFilesOnly": True,
        "python": sys.version.split()[0],
        "pillow": None,
        "transformers": None,
        "torch": None,
        "cudaAvailable": False,
        "modelArtifactAvailable": False,
        "status": "LOCAL_RUNTIME_CONTROL_UNAVAILABLE",
    }
    try:
        import PIL  # type: ignore

        runtime["pillow"] = str(PIL.__version__)
    except Exception:
        pass
    try:
        import transformers  # type: ignore

        runtime["transformers"] = str(transformers.__version__)
    except Exception:
        pass
    try:
        import torch  # type: ignore

        runtime["torch"] = str(torch.__version__)
        runtime["cudaAvailable"] = bool(torch.cuda.is_available())
    except Exception:
        pass

    encoded_model = "models--" + model_id.replace("/", "--")
    cache_roots: list[Path] = []
    for env_name in ("HUGGINGFACE_HUB_CACHE", "TRANSFORMERS_CACHE"):
        configured = os.environ.get(env_name, "").strip()
        if configured:
            cache_roots.append(Path(configured))
    hf_home = os.environ.get("HF_HOME", "").strip()
    if hf_home:
        cache_roots.append(Path(hf_home) / "hub")
    cache_roots.append(Path.home() / ".cache" / "huggingface" / "hub")
    for root in cache_roots:
        model_cache = root / encoded_model
        snapshots = model_cache / "snapshots"
        if snapshots.is_dir() and any(path.is_dir() and any(path.iterdir()) for path in snapshots.iterdir()):
            runtime["modelArtifactAvailable"] = True
            break
    if runtime["modelArtifactAvailable"] and runtime["transformers"] and runtime["pillow"]:
        runtime["status"] = "LOCAL_RUNTIME_CONTROL_AVAILABLE"
    return runtime


def inventory_non_sensitive_fixtures(repo_root: Path) -> dict[str, Any]:
    """Inventory only conventional fixture directories; do not classify user media."""

    fixture_dirs = (
        repo_root / "tests" / "fixtures",
        repo_root / "tests" / "testdata",
        repo_root / "scripts" / "fixtures",
    )
    image_extensions = {".png", ".jpg", ".jpeg", ".webp"}
    count = 0
    for directory in fixture_dirs:
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in image_extensions:
                count += 1
    if count == 0:
        status = "NO_NON_SENSITIVE_IMAGE_FIXTURES_FOUND"
    else:
        status = "UNCLASSIFIED_FIXTURES_FOUND_REQUIRES_OPERATOR_REVIEW"
    return {
        "imageFixtureCount": count,
        "knownSafeRuntimeControls": {
            "count": 0,
            "status": "LOCAL_RUNTIME_CONTROL_UNAVAILABLE",
        },
        "benignSourceConsistentControls": {
            "count": 0,
            "status": "DEFERRED_UNTIL_LOCAL_FLORENCE_ARTIFACT_AVAILABLE",
        },
        "knownPositiveControls": {
            "count": 0,
            "status": "DEFERRED_UNTIL_LOCAL_FLORENCE_ARTIFACT_AVAILABLE",
        },
        "inventoryStatus": status,
    }


def _aggregate_machine_rows(machine_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def count_values(key: str) -> dict[str, int]:
        return dict(sorted(Counter(str(row.get(key)) for row in machine_rows if row.get(key) is not None).items()))

    def count_band(key: str) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for row in machine_rows:
            bands = row.get(key)
            if isinstance(bands, Mapping):
                counter.update({str(label): int(value) for label, value in bands.items()})
        return dict(sorted(counter.items()))

    return {
        "candidateCount": len(machine_rows),
        "watermarkDecisionClass": count_values("watermarkDecisionClass"),
        "watermarkQaAction": count_values("watermarkQaAction"),
        "watermarkPolicyVersion": count_values("watermarkPolicyVersion"),
        "textLogoWatermarkRisk": count_values("textLogoWatermarkRisk"),
        "logoTextWatermarkRisk": count_values("logoTextWatermarkRisk"),
        "ocrDetectionCount": count_values("ocrDetectionCount"),
        "sourceConsistency": count_values("sourceConsistency"),
        "confidenceBands": count_band("confidenceBands"),
        "areaBands": count_band("areaBands"),
        "locationBands": count_band("locationBands"),
        "visualRiskStatus": count_values("visualRiskStatus"),
        "selectionTier": count_values("selectionTier"),
    }


def build_benchmark_skeleton(
    recovery: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    *,
    provenance: Mapping[str, Any],
    runtime: Mapping[str, Any],
    fixture_inventory: Mapping[str, Any],
) -> dict[str, Any]:
    machine_rows = extract_machine_evidence(recovery)
    evaluation_counts = _mapping(evaluation.get("counts"))
    skeleton = {
        "schemaVersion": BENCHMARK_VERSION,
        "benchmarkVersion": BENCHMARK_VERSION,
        "phase": "PHASE_1_AUTOMATIC_PREPARATION",
        "nextState": "HUMAN_WATERMARK_LABELS_REQUIRED",
        "humanLabelStatus": PENDING_LABEL_STATUS,
        "realV9": {
            "participantCount": 5,
            "candidateCount": len(machine_rows),
            "machineEvidence": machine_rows,
            "humanLabels": "PENDING",
        },
        "v9EvaluationSnapshot": {
            "verdict": str(evaluation.get("verdict") or ""),
            "counts": {str(key): value for key, value in evaluation_counts.items()},
            "requiredSignalUnavailable": evaluation.get("requiredSignalUnavailable"),
            "rubricComplete": evaluation.get("rubricComplete"),
            "humanSignoff": evaluation.get("humanSignoff"),
        },
        "machineAggregate": _aggregate_machine_rows(machine_rows),
        "humanLabelSchema": {
            "requiredFields": list(HUMAN_LABEL_FIELDS),
            "optionalFields": list(OPTIONAL_HUMAN_FIELDS),
            "uncertainExcludedFromPrimaryMetrics": True,
        },
        "secureReviewWorkflow": {
            "status": "EXISTING_PRIVATE_G004_BUNDLE_PRESENT",
            "newViewerCreated": False,
            "newImageCopyCreated": False,
            "newSignedUrlPersisted": False,
        },
        "runtime": dict(runtime),
        "fixtureInventory": dict(fixture_inventory),
        "provenance": dict(provenance),
        "mutations": {
            "azureGenerationCalls": 0,
            "candidateRegeneration": 0,
            "cloudBuild": 0,
            "artifactRegistry": 0,
            "cloudRun": 0,
            "cloudTasks": 0,
            "productionTraffic": 0,
            "queueResume": 0,
            "productionMutation": 0,
            "humanSignoffMutation": 0,
        },
    }
    assert_privacy_safe(skeleton)
    return skeleton


def build_human_instructions() -> str:
    return """# G004 Watermark Calibration Benchmark — Human Checkpoint

Status: `HUMAN_WATERMARK_LABELS_REQUIRED`

Use the already provisioned authenticated/private G004 review boundary. Compare
each candidate with its normalized source using only the ordinal pair in the
worksheet. Do not copy images, create derivatives, export URLs, or record
paths, names, raw OCR, brands, schools, coordinates, or bounding boxes.

For every row, fill these required fields:

- `candidateVisualClass`: `no_visible_text_or_logo`, `benign_text_or_logo`,
  `clear_watermark_or_brand_overlay`, or `uncertain`
- `sameVisibleMarkInSource`: `yes`, `no`, `not_applicable`, or `uncertain`
- `overlayAppearance`: `yes`, `no`, or `uncertain`
- `humanLabelConfidence`: `high`, `medium`, or `low`

Optional `location` may be `corner`, `edge`, `clothing_zone`, `central`,
`none`, or `uncertain`.

`uncertain` is valid and is excluded from primary precision/recall
denominators. Empty required fields are not valid. This watermark label
checkpoint is separate from G004 `humanSignoff`, which remains false.
"""


def _write_create_only(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("benchmark output already exists")
    path.write_text(content, encoding="utf-8", newline="\n")


def prepare_phase1(
    *,
    recovery_path: Path,
    evaluation_path: Path,
    worksheet_path: Path,
    benchmark_path: Path,
    instructions_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    recovery = _load_json(recovery_path)
    evaluation = _load_json(evaluation_path)
    machine_rows = extract_machine_evidence(recovery)
    runtime = inspect_local_runtime()
    fixture_inventory = inventory_non_sensitive_fixtures(repo_root)
    source_hashes = {
        "v9RecoverySha256": sha256_file(recovery_path),
        "v9EvaluationSha256": sha256_file(evaluation_path),
    }
    source_files = {
        "watermarkPySha256": repo_root / "lib" / "ai_recommend_model" / "avatar_generation" / "analysis" / "watermark.py",
        "visualRiskPySha256": repo_root / "lib" / "ai_recommend_model" / "avatar_generation" / "analysis" / "visual_risk.py",
        "florence2VisualPySha256": repo_root / "lib" / "ai_recommend_model" / "avatar_generation" / "model_adapters" / "florence2_visual.py",
        "qaRuntimePySha256": repo_root / "lib" / "ai_recommend_model" / "avatar_generation" / "qa_runtime.py",
        "qaSignalsPySha256": repo_root / "lib" / "ai_recommend_model" / "avatar_generation" / "qa_signals.py",
    }
    for key, path in source_files.items():
        if path.is_file():
            source_hashes[key] = sha256_file(path)
    script_path = Path(__file__).resolve()
    source_hashes["benchmarkScriptSha256"] = sha256_file(script_path)
    provenance = {
        **source_hashes,
        "sourceSnapshotCommit": _git_revision(repo_root, "HEAD^") or "unknown",
        "offlineFixesHead": _git_revision(repo_root, "HEAD"),
        "calibrationArtifactGitRevision": str(recovery.get("gitRevision") or ""),
        "watermarkPolicyVersion": str(recovery.get("watermarkPolicyVersion") or ""),
        "qaVersion": str(recovery.get("qaVersion") or ""),
    }
    skeleton = build_benchmark_skeleton(
        recovery,
        evaluation,
        provenance=provenance,
        runtime=runtime,
        fixture_inventory=fixture_inventory,
    )
    worksheet = build_human_label_worksheet(recovery)
    _write_create_only(worksheet_path, json.dumps(worksheet, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_create_only(benchmark_path, json.dumps(skeleton, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_create_only(instructions_path, build_human_instructions())
    return skeleton


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v9-recovery", type=Path, required=True)
    parser.add_argument("--v9-evaluation", type=Path, required=True)
    parser.add_argument("--worksheet", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--instructions", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = (args.repo_root or Path(__file__).resolve().parents[1]).resolve()
    skeleton = prepare_phase1(
        recovery_path=args.v9_recovery.resolve(),
        evaluation_path=args.v9_evaluation.resolve(),
        worksheet_path=args.worksheet.resolve(),
        benchmark_path=args.benchmark.resolve(),
        instructions_path=args.instructions.resolve(),
        repo_root=repo_root,
    )
    print("status=HUMAN_WATERMARK_LABELS_REQUIRED")
    print(f"candidateCount={skeleton['realV9']['candidateCount']}")
    print(f"knownSafeRuntimeControls={skeleton['fixtureInventory']['knownSafeRuntimeControls']['count']}")
    print(f"knownPositiveControls={skeleton['fixtureInventory']['knownPositiveControls']['count']}")
    print("azureGenerationCalls=0")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
