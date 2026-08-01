from __future__ import annotations

from typing import Any, Mapping


PASS_FIELDS = ("adultQa", "privacyQa", "brandQa", "cropConsistency")
LOW_RISK_FIELDS = (
    "childlikeRisk",
    "beautificationRisk",
    "identifiabilityRisk",
    "uniqueMarkCopyRisk",
    "logoTextWatermarkRisk",
)
OPTIONAL_PASS_FIELDS = ("cropIsolationQuality",)
OPTIONAL_LOW_RISK_FIELDS = (
    "backgroundLeakageRisk",
    "secondaryFaceLeakageRisk",
    "textLogoWatermarkRisk",
)


def is_hard_reject(candidate: Mapping[str, Any]) -> bool:
    qa = qa_doc(candidate)
    return bool(qa.get("rejectReasons")) or str(
        candidate.get("status") or ""
    ).strip().lower() == "rejected"


def is_hard_pass(candidate: Mapping[str, Any]) -> bool:
    qa = qa_doc(candidate)
    status = str(candidate.get("status") or "").strip().lower()
    return status == "preview_ready" or (
        qa.get("previewAllowed") is True and qa.get("requiresHumanReview") is not True
    )


def is_soft_pass(candidate: Mapping[str, Any]) -> bool:
    qa = qa_doc(candidate)
    status = str(candidate.get("status") or "").strip().lower()
    return (
        status == "soft_pass"
        or qa.get("softPass") is True
        or qa.get("soft_pass") is True
    )


def is_needs_review(candidate: Mapping[str, Any]) -> bool:
    qa = qa_doc(candidate)
    status = str(candidate.get("status") or "").strip().lower()
    return status == "needs_review" or qa.get("requiresHumanReview") is True


def passes_absolute_preview_checks(candidate: Mapping[str, Any]) -> bool:
    if is_hard_reject(candidate):
        return False

    qa = qa_doc(candidate)
    required_pass = all(_status_is_pass(qa.get(field)) for field in PASS_FIELDS)
    required_low = all(
        _risk_is_low(qa.get(field)) for field in LOW_RISK_FIELDS
    )
    optional_pass = all(
        _status_is_pass(qa.get(field)) for field in OPTIONAL_PASS_FIELDS if field in qa
    )
    optional_low = all(
        _risk_is_low(qa.get(field)) for field in OPTIONAL_LOW_RISK_FIELDS if field in qa
    )
    return required_pass and required_low and optional_pass and optional_low


def is_preview_eligible(candidate: Mapping[str, Any]) -> bool:
    if is_needs_review(candidate):
        return False
    if not passes_absolute_preview_checks(candidate):
        return False
    return is_hard_pass(candidate) or is_soft_pass(candidate)


def qa_doc(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    qa = candidate.get("qa")
    return qa if isinstance(qa, Mapping) else {}


def _status_is_pass(value: Any) -> bool:
    return str(value or "").strip().lower() in {"pass", "passed", "ok", "low"}


def _risk_is_low(value: Any) -> bool:
    return str(value or "").strip().lower() in {"low", "none", "pass", "passed", "ok"}


__all__ = [
    "is_hard_pass",
    "is_hard_reject",
    "is_needs_review",
    "is_preview_eligible",
    "is_soft_pass",
    "passes_absolute_preview_checks",
    "qa_doc",
]
