"""Typed, privacy-safe watermark evidence and decision policy.

OCR is an evidence source, not a decision by itself.  This module deliberately
keeps raw labels process-local and emits only coarse scalar evidence for QA
documents.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
import math
import re
from typing import Any, Mapping, Optional, Sequence

from .visual_risk import KIND_LOGO, KIND_SIGN, KIND_TEXT, VisualRiskRegion


HIGH_CONFIDENCE = 0.85
MEDIUM_CONFIDENCE = 0.65
SMALL_REGION_AREA = 0.08
TINY_REGION_AREA = 0.03
WATERMARK_POLICY_VERSION = "watermark_policy_v3_generated_artifact_only_v1"

WATERMARK_QA_ACTION_ALLOW = "allow"
WATERMARK_QA_ACTION_REVIEW = "review"
WATERMARK_QA_ACTION_REJECT = "reject"
WATERMARK_QA_ACTIONS = frozenset(
    {
        WATERMARK_QA_ACTION_ALLOW,
        WATERMARK_QA_ACTION_REVIEW,
        WATERMARK_QA_ACTION_REJECT,
    }
)
_WATERMARK_RISK_BY_ACTION = {
    WATERMARK_QA_ACTION_ALLOW: "low",
    WATERMARK_QA_ACTION_REVIEW: "medium",
    WATERMARK_QA_ACTION_REJECT: "high",
}
_ARTIFACT_TOKEN_HINTS = frozenset({"watermark", "watermarks", "overlay", "overlays"})


@dataclass(frozen=True)
class WatermarkDecision:
    """Decision plus redacted evidence for one candidate image."""

    hard_reject: bool
    needs_review: bool
    decision_class: str
    evidence_classes: tuple[str, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)
    watermark_qa_action: str = WATERMARK_QA_ACTION_ALLOW

    def to_document(self) -> dict[str, Any]:
        return {
            "hardReject": bool(self.hard_reject),
            "needsReview": bool(self.needs_review),
            "decisionClass": self.decision_class,
            "evidenceClasses": list(self.evidence_classes),
            "watermarkQaAction": self.watermark_qa_action,
            "policyVersion": WATERMARK_POLICY_VERSION,
            "evidence": _redact_evidence(self.evidence or {}),
        }


@dataclass(frozen=True, repr=False)
class _RegionEvidence:
    kind: str
    confidence: Optional[float]
    area_ratio: float
    location: str
    overlay_like: bool
    token_key: str
    token_quality: str
    source_consistent: Optional[bool]
    repeated: bool


def evaluate_watermark_risk(
    candidate_regions: Sequence[VisualRiskRegion],
    *,
    source_regions: Sequence[VisualRiskRegion] = (),
    image_size: tuple[int, int] = (1, 1),
    source_image_size: tuple[int, int] | None = None,
) -> WatermarkDecision:
    """Classify watermark artifacts and map them to a product QA action.

    Text/logo presence, source mismatch, location, size, and confidence are
    evidence only.  Review/reject requires typed artifact corroboration;
    model availability is handled by the surrounding QA runtime.
    """

    width, height = _safe_image_size(image_size)
    source_width, source_height = _safe_image_size(source_image_size or image_size)
    candidates = [
        _region_evidence(region, width=width, height=height)
        for region in candidate_regions or ()
        if _is_text_like(region)
    ]
    sources = [
        _region_evidence(region, width=source_width, height=source_height)
        for region in source_regions or ()
        if _is_text_like(region)
    ]
    repeated_keys = Counter(
        item.token_key for item in candidates if item.token_key
    )
    candidates = [
        _with_repetition(item, repeated_keys.get(item.token_key, 0) > 1)
        for item in candidates
    ]
    candidates = [
        _with_source_consistency(item, sources)
        for item in candidates
    ]

    if not candidates:
        return WatermarkDecision(
            hard_reject=False,
            needs_review=False,
            decision_class="no_text_detected",
            evidence={
                "ocrDetectionCount": 0,
                "recognizedTokenCount": 0,
                "confidenceBands": {},
                "areaBands": {},
                "locationBands": {},
                "repeatedTokenCount": 0,
                "sourceConsistency": "not_applicable",
            },
            watermark_qa_action=WATERMARK_QA_ACTION_ALLOW,
        )

    hard_classes: set[str] = set()
    generated_artifact = False
    benign_count = 0
    for item in candidates:
        strong_overlay = item.overlay_like and (
            item.repeated
            or (
                item.source_consistent is not True
                and (
                    item.token_quality == "implausible"
                    or (
                        item.confidence is not None
                        and item.confidence >= HIGH_CONFIDENCE
                        and _token_has_artifact_hint(item.token_key)
                    )
                )
            )
        )
        if item.source_consistent is True and not strong_overlay:
            benign_count += 1
            continue

        if strong_overlay:
            hard_classes.add(
                "generated_overlay_logo"
                if item.kind in {KIND_LOGO, KIND_SIGN}
                else "overlay_watermark"
            )
            continue

        if item.token_quality == "implausible":
            generated_artifact = True
            continue

    if hard_classes:
        decision_class = (
            "generated_overlay_logo"
            if "generated_overlay_logo" in hard_classes
            else "overlay_watermark"
        )
        return WatermarkDecision(
            hard_reject=True,
            needs_review=False,
            decision_class=decision_class,
            evidence_classes=tuple(sorted(hard_classes)),
            evidence=_evidence_document(candidates, source_count=len(sources)),
            watermark_qa_action=WATERMARK_QA_ACTION_REJECT,
        )

    if generated_artifact:
        return WatermarkDecision(
            hard_reject=False,
            needs_review=True,
            decision_class="generated_text_artifact",
            evidence_classes=("generated_text_artifact",),
            evidence=_evidence_document(candidates, source_count=len(sources)),
            watermark_qa_action=WATERMARK_QA_ACTION_REVIEW,
        )

    if benign_count == len(candidates):
        decision_class = (
            "source_consistent_clothing_text"
            if all(item.kind == KIND_TEXT for item in candidates)
            else "source_consistent_text_or_logo"
        )
    elif all(_candidate_only_benign(item) for item in candidates):
        decision_class = "benign_text_or_logo"
    else:
        decision_class = "ambiguous_text_evidence"

    return WatermarkDecision(
        hard_reject=False,
        needs_review=False,
        decision_class=decision_class,
        evidence_classes=(decision_class,),
        evidence=_evidence_document(candidates, source_count=len(sources)),
        watermark_qa_action=WATERMARK_QA_ACTION_ALLOW,
    )


def watermark_risk_for_action(action: Any) -> str:
    """Map the typed watermark action to the compatibility risk field."""

    normalized = str(action or "").strip().lower()
    return _WATERMARK_RISK_BY_ACTION.get(normalized, "medium")


def resolve_watermark_qa_action(signals: Mapping[str, Any]) -> str:
    """Resolve a typed action, with conservative compatibility for old signals."""

    explicit = str(signals.get("watermarkQaAction") or "").strip().lower()
    visual_status = str(signals.get("visualRiskStatus") or "").strip().lower()
    visual_unavailable = visual_status in {"unavailable", "critical_unavailable"}
    for key in ("visualRiskProviderAvailable", "watermarkVisualAnalysisAvailable"):
        if signals.get(key) is False:
            visual_unavailable = True
    if visual_unavailable:
        return (
            WATERMARK_QA_ACTION_REJECT
            if explicit == WATERMARK_QA_ACTION_REJECT
            else WATERMARK_QA_ACTION_REVIEW
        )
    if explicit in WATERMARK_QA_ACTIONS:
        return explicit

    decision_class = str(signals.get("watermarkDecisionClass") or "").strip().lower()
    if decision_class in {"overlay_watermark", "generated_overlay_logo"}:
        return WATERMARK_QA_ACTION_REJECT
    if decision_class == "generated_text_artifact":
        return WATERMARK_QA_ACTION_REVIEW
    if decision_class in {
        "no_text_detected",
        "benign_text_or_logo",
        "source_consistent_text_or_logo",
        "source_consistent_clothing_text",
        "ambiguous_text_evidence",
        "text_evidence_non_blocking",
        "identifiable_brand_logo",
    }:
        return WATERMARK_QA_ACTION_ALLOW

    risks = {
        str(signals.get(key) or "").strip().lower()
        for key in ("textLogoWatermarkRisk", "logoTextWatermarkRisk")
    }
    if "high" in risks:
        return WATERMARK_QA_ACTION_REJECT
    if "medium" in risks:
        return WATERMARK_QA_ACTION_REVIEW
    return WATERMARK_QA_ACTION_ALLOW


def _region_evidence(
    region: VisualRiskRegion,
    *,
    width: int,
    height: int,
) -> _RegionEvidence:
    left, top, right, bottom = _clamp_bbox(region.bbox_xyxy, width, height)
    area_ratio = ((right - left) * (bottom - top)) / float(width * height)
    center_x = ((left + right) / 2.0) / width
    center_y = ((top + bottom) / 2.0) / height
    edge_x = center_x <= 0.15 or center_x >= 0.85
    edge_y = center_y <= 0.15 or center_y >= 0.85
    corner = edge_x and edge_y
    edge = edge_x or edge_y
    overlay_like = (
        corner and area_ratio <= SMALL_REGION_AREA
    ) or (
        edge and area_ratio <= TINY_REGION_AREA
    )
    if corner:
        location = "corner"
    elif edge:
        location = "edge"
    elif 0.45 <= center_y <= 0.85 and 0.20 <= center_x <= 0.80:
        location = "clothing_zone"
    else:
        location = "central"
    token_key = _normalize_label(getattr(region, "raw_label", None))
    return _RegionEvidence(
        kind=str(getattr(region, "kind", "") or "").strip().lower(),
        confidence=_safe_confidence(getattr(region, "confidence", None)),
        area_ratio=max(0.0, min(1.0, area_ratio)),
        location=location,
        overlay_like=overlay_like,
        token_key=token_key,
        token_quality=_token_quality(token_key),
        source_consistent=None,
        repeated=False,
    )


def _with_repetition(item: _RegionEvidence, repeated: bool) -> _RegionEvidence:
    return replace(item, repeated=repeated)


def _with_source_consistency(
    item: _RegionEvidence,
    source_regions: Sequence[_RegionEvidence],
) -> _RegionEvidence:
    if not item.token_key or not source_regions:
        consistency: Optional[bool] = None
    else:
        consistency = any(
            source.token_key == item.token_key
            and _source_kinds_compatible(item.kind, source.kind)
            for source in source_regions
        )
    return replace(item, source_consistent=consistency)


def _source_kinds_compatible(candidate_kind: str, source_kind: str) -> bool:
    """Keep source comparison within the same text-like semantic family."""

    return candidate_kind == source_kind and candidate_kind in {
        KIND_TEXT,
        KIND_LOGO,
        KIND_SIGN,
    }


def _candidate_only_benign(item: _RegionEvidence) -> bool:
    """Recognize integrated text-like content without treating presence as risk."""

    if item.token_quality == "implausible":
        return False
    if item.kind in {KIND_LOGO, KIND_SIGN}:
        return item.confidence is not None and item.confidence >= MEDIUM_CONFIDENCE
    return item.confidence is not None and item.confidence >= HIGH_CONFIDENCE


def _evidence_document(
    regions: Sequence[_RegionEvidence],
    *,
    source_count: int,
) -> dict[str, Any]:
    confidence_bands = Counter(_confidence_band(region.confidence) for region in regions)
    area_bands = Counter(_area_band(region.area_ratio) for region in regions)
    location_bands = Counter(region.location for region in regions)
    repeated_count = sum(1 for region in regions if region.repeated)
    consistency_values = {region.source_consistent for region in regions}
    if consistency_values == {True}:
        source_consistency = "consistent"
    elif True in consistency_values and False in consistency_values:
        source_consistency = "mixed"
    elif False in consistency_values:
        source_consistency = "inconsistent"
    elif source_count:
        source_consistency = "unknown"
    else:
        source_consistency = "not_available"
    return {
        "ocrDetectionCount": len(regions),
        "recognizedTokenCount": sum(1 for region in regions if region.token_key),
        "confidenceBands": dict(sorted(confidence_bands.items())),
        "areaBands": dict(sorted(area_bands.items())),
        "locationBands": dict(sorted(location_bands.items())),
        "repeatedTokenCount": repeated_count,
        "sourceConsistency": source_consistency,
    }


def _redact_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    """Allow only the fixed scalar evidence shape into persisted QA output."""

    allowed = {
        "ocrDetectionCount",
        "recognizedTokenCount",
        "confidenceBands",
        "areaBands",
        "locationBands",
        "repeatedTokenCount",
        "sourceConsistency",
    }
    result: dict[str, Any] = {}
    for key in allowed:
        child = value.get(key)
        if isinstance(child, Mapping):
            result[key] = {
                str(label): int(count)
                for label, count in child.items()
                if str(label) in {"low", "medium", "high", "unknown", "small", "medium", "large", "corner", "edge", "central", "clothing_zone"}
                and isinstance(count, int)
                and not isinstance(count, bool)
            }
        elif isinstance(child, int) and not isinstance(child, bool):
            result[key] = child
        elif isinstance(child, str) and child in {
            "consistent",
            "mixed",
            "inconsistent",
            "unknown",
            "not_available",
            "not_applicable",
        }:
            result[key] = child
    return result


def _is_text_like(region: VisualRiskRegion) -> bool:
    return str(getattr(region, "kind", "") or "").strip().lower() in {
        KIND_TEXT,
        KIND_LOGO,
        KIND_SIGN,
    }


def _normalize_label(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    return " ".join(sorted(set(tokens[:12])))


def _token_quality(token_key: str) -> str:
    if not token_key:
        return "unknown"
    tokens = token_key.split()
    # A single short word can be ordinary integrated text (for example a
    # monogram or a two-letter clothing mark). Multiple short fragments are a
    # stronger broken-generation signal and remain eligible for review.
    if len(tokens) > 1 and any(len(token) <= 2 for token in tokens):
        return "implausible"
    return "plausible"


def _token_has_artifact_hint(token_key: str) -> bool:
    return any(token in _ARTIFACT_TOKEN_HINTS for token in token_key.split())


def _confidence_band(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    if value >= HIGH_CONFIDENCE:
        return "high"
    if value >= MEDIUM_CONFIDENCE:
        return "medium"
    return "low"


def _area_band(value: float) -> str:
    if value <= TINY_REGION_AREA:
        return "small"
    if value <= SMALL_REGION_AREA:
        return "medium"
    return "large"


def _safe_confidence(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and 0.0 <= parsed <= 1.0 else None


def _safe_image_size(value: Any) -> tuple[int, int]:
    try:
        width, height = int(value[0]), int(value[1])
    except (IndexError, TypeError, ValueError):
        return (1, 1)
    return (max(1, width), max(1, height))


def _clamp_bbox(value: Any, width: int, height: int) -> tuple[float, float, float, float]:
    try:
        left, top, right, bottom = (float(item) for item in value[:4])
    except (IndexError, TypeError, ValueError):
        return (0.0, 0.0, 0.0, 0.0)
    return (
        max(0.0, min(float(width), left)),
        max(0.0, min(float(height), top)),
        max(0.0, min(float(width), right)),
        max(0.0, min(float(height), bottom)),
    )


__all__ = [
    "WATERMARK_QA_ACTION_ALLOW",
    "WATERMARK_QA_ACTION_REJECT",
    "WATERMARK_QA_ACTION_REVIEW",
    "WATERMARK_QA_ACTIONS",
    "WATERMARK_POLICY_VERSION",
    "WatermarkDecision",
    "evaluate_watermark_risk",
    "resolve_watermark_qa_action",
    "watermark_risk_for_action",
]
