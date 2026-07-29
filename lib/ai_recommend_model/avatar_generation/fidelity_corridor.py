from __future__ import annotations

import copy
import math
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence

from .fidelity_signals import (
    FIDELITY_COMPONENT_KEYS,
    FIDELITY_SCORE_KEYS,
    FidelitySignalBundle,
)


DEFAULT_CORRIDOR_MODE = "shadow"
DEFAULT_CORRIDOR_POLICY_VERSION = "avatar_corridor_policy_v1"
UNCALIBRATED_VERSION = "uncalibrated"
CORRIDOR_SCHEMA_VERSION = "avatar_fidelity_corridor_shadow_v1"

REASON_CODE_ORDER = (
    "candidate_not_resembling_source",
    "candidate_trait_mismatch",
    "candidate_generation_generic",
    "candidate_too_identifiable",
    "candidate_childlike",
    "candidate_severe_beautification",
    "candidate_privacy_leak",
    "candidate_multiple_people",
    "fidelity_signal_unavailable",
    "privacy_signal_unavailable",
    "conflicting_fidelity_signals",
    "model_unavailable_systemic",
    "unsafe_candidate_excluded_from_ranking",
)
REASON_CODE_ALLOWLIST = frozenset(REASON_CODE_ORDER)

_SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:+-]{0,127}$")
_GATE_STATUSES = frozenset({"pass", "review", "reject"})
_IDENTITY_BANDS = frozenset({"low", "medium", "high", "unavailable"})
_IDENTITY_DECISIONS = frozenset({"pass", "review", "reject"})
_UNAVAILABLE_STATES = frozenset(
    {"unavailable", "critical_unavailable", "uncalibrated", "conflict"}
)


class CorridorMode(str, Enum):
    OFF = "off"
    SHADOW = "shadow"
    ENFORCED = "enforced"

    @classmethod
    def parse(cls, value: Any) -> "CorridorMode":
        if isinstance(value, cls):
            return value
        normalized = str(value or "").strip().lower()
        try:
            return cls(normalized)
        except ValueError:
            return cls.SHADOW


class GateStatus(str, Enum):
    PASS = "pass"
    REVIEW = "review"
    REJECT = "reject"


@dataclass(frozen=True)
class CorridorPolicy:
    mode: CorridorMode = CorridorMode.SHADOW
    policy_version: str = DEFAULT_CORRIDOR_POLICY_VERSION
    calibration_version: str = UNCALIBRATED_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", CorridorMode.parse(self.mode))
        object.__setattr__(
            self,
            "policy_version",
            _safe_version(self.policy_version, DEFAULT_CORRIDOR_POLICY_VERSION),
        )
        calibration = str(self.calibration_version or "").strip()
        object.__setattr__(
            self,
            "calibration_version",
            (
                _safe_version(calibration, UNCALIBRATED_VERSION)
                if calibration
                else UNCALIBRATED_VERSION
            ),
        )

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] = os.environ,
    ) -> "CorridorPolicy":
        return cls(
            mode=CorridorMode.parse(
                env.get("AVATAR_FIDELITY_CORRIDOR_MODE", DEFAULT_CORRIDOR_MODE)
            ),
            policy_version=env.get(
                "AVATAR_FIDELITY_CORRIDOR_POLICY_VERSION",
                DEFAULT_CORRIDOR_POLICY_VERSION,
            ),
            calibration_version=env.get(
                "AVATAR_FIDELITY_CORRIDOR_CALIBRATION_VERSION",
                UNCALIBRATED_VERSION,
            ),
        )

    @property
    def calibrated(self) -> bool:
        return self.calibration_version != UNCALIBRATED_VERSION


@dataclass(frozen=True)
class GateResult:
    status: GateStatus
    reason_codes: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        normalized = str(getattr(self.status, "value", self.status)).strip().lower()
        object.__setattr__(
            self,
            "status",
            GateStatus(normalized) if normalized in _GATE_STATUSES else GateStatus.REVIEW,
        )
        object.__setattr__(
            self,
            "reason_codes",
            _ordered_reason_codes(self.reason_codes),
        )


@dataclass(frozen=True)
class IdentityPrivacySignal:
    """Calibrated identity-risk decision used only by the privacy upper bound."""

    available: bool = False
    calibrated: bool = False
    upper_bound_decision: str = "review"
    risk_band: str = "unavailable"
    model_version: Optional[str] = None
    timing_ms: Optional[float] = None

    def __post_init__(self) -> None:
        decision = str(self.upper_bound_decision or "").strip().lower()
        object.__setattr__(
            self,
            "upper_bound_decision",
            decision if decision in _IDENTITY_DECISIONS else "review",
        )
        band = str(self.risk_band or "").strip().lower()
        object.__setattr__(
            self,
            "risk_band",
            band if band in _IDENTITY_BANDS else "unavailable",
        )

    @property
    def critical_signal_available(self) -> bool:
        return bool(self.available and self.calibrated)

    def to_document(self) -> dict[str, object]:
        availability = (
            "available"
            if self.available and self.calibrated
            else ("uncalibrated" if self.available else "unavailable")
        )
        document: dict[str, object] = {
            "band": self.risk_band if self.critical_signal_available else "unavailable",
            "modelAvailability": availability,
        }
        if self.model_version is not None:
            document["modelVersion"] = _safe_version(self.model_version, "unknown")
        timing = _finite_number(self.timing_ms)
        if timing is not None:
            document["timingMs"] = round(max(0.0, timing), 3)
        return document


class SafetyGate:
    _REASON_MAP = {
        "childlike_or_teenager": "candidate_childlike",
        "sexualized_or_nightlife": "candidate_privacy_leak",
        "too_beautified": "candidate_severe_beautification",
        "too_identifiable": "candidate_too_identifiable",
        "unique_mark_copied": "candidate_privacy_leak",
        "source_candidate_identical": "candidate_privacy_leak",
        "source_candidate_near_duplicate": "candidate_privacy_leak",
        "logo_text_watermark": "candidate_privacy_leak",
        "background_leakage": "candidate_privacy_leak",
        "crop_expanded_to_unseen_body": "candidate_privacy_leak",
        "multiple_faces_generated": "candidate_multiple_people",
        "secondary_person_generated": "candidate_multiple_people",
        "secondary_face_leakage": "candidate_multiple_people",
    }

    def evaluate(self, active_qa: Mapping[str, Any]) -> GateResult:
        if not isinstance(active_qa, Mapping):
            return GateResult(
                GateStatus.REVIEW,
                ("model_unavailable_systemic",),
            )

        active_reasons = _string_sequence(active_qa.get("rejectReasons"))
        mapped_reasons = [
            self._REASON_MAP[reason]
            for reason in active_reasons
            if reason in self._REASON_MAP
        ]

        if (
            str(active_qa.get("adultQa") or "").strip().lower() == "fail"
            or str(active_qa.get("childlikeRisk") or "").strip().lower() == "high"
        ):
            mapped_reasons.append("candidate_childlike")
        if (
            str(active_qa.get("beautificationRisk") or "").strip().lower()
            == "high"
        ):
            mapped_reasons.append("candidate_severe_beautification")
        if any(
            str(active_qa.get(key) or "").strip().lower() == "high"
            for key in (
                "uniqueMarkCopyRisk",
                "logoTextWatermarkRisk",
                "textLogoWatermarkRisk",
                "backgroundLeakageRisk",
            )
        ):
            mapped_reasons.append("candidate_privacy_leak")
        if (
            str(active_qa.get("cropConsistency") or "").strip().lower() == "fail"
            or str(active_qa.get("cropIsolationQuality") or "").strip().lower()
            == "fail"
        ):
            mapped_reasons.append("candidate_privacy_leak")
        if (
            str(active_qa.get("secondaryFaceLeakageRisk") or "").strip().lower()
            == "high"
        ):
            mapped_reasons.append("candidate_multiple_people")

        if active_reasons or mapped_reasons:
            return GateResult(GateStatus.REJECT, mapped_reasons)
        if _active_model_unavailable(active_qa):
            return GateResult(
                GateStatus.REVIEW,
                ("model_unavailable_systemic",),
            )
        if active_qa.get("requiresHumanReview") is True:
            return GateResult(GateStatus.REVIEW)
        return GateResult(GateStatus.PASS)


class PrivacyUpperBoundGate:
    def evaluate(
        self,
        identity_signal: Optional[IdentityPrivacySignal],
    ) -> GateResult:
        if (
            identity_signal is None
            or not identity_signal.available
            or not identity_signal.calibrated
            or identity_signal.risk_band == "unavailable"
        ):
            return GateResult(
                GateStatus.REVIEW,
                ("privacy_signal_unavailable",),
            )
        if (
            identity_signal.upper_bound_decision == "reject"
            or identity_signal.risk_band == "high"
        ):
            return GateResult(
                GateStatus.REJECT,
                ("candidate_too_identifiable",),
            )
        if identity_signal.upper_bound_decision == "review":
            return GateResult(GateStatus.REVIEW)
        return GateResult(GateStatus.PASS)


class FidelityLowerBoundGate:
    def evaluate(
        self,
        fidelity_signals: Optional[FidelitySignalBundle],
        *,
        policy: CorridorPolicy,
    ) -> GateResult:
        if fidelity_signals is None:
            return GateResult(
                GateStatus.REVIEW,
                ("fidelity_signal_unavailable",),
            )
        if fidelity_signals.conflicting:
            return GateResult(
                GateStatus.REVIEW,
                (
                    *fidelity_signals.reason_codes,
                    "conflicting_fidelity_signals",
                ),
            )
        if fidelity_signals.trait_coverage_status == "mismatch":
            return GateResult(
                GateStatus.REVIEW,
                (
                    *fidelity_signals.reason_codes,
                    "candidate_trait_mismatch",
                ),
            )
        if fidelity_signals.trait_coverage_status == "unavailable":
            return GateResult(
                GateStatus.REVIEW,
                (
                    *fidelity_signals.reason_codes,
                    "fidelity_signal_unavailable",
                ),
            )
        if not fidelity_signals.critical_signals_available or not policy.calibrated:
            return GateResult(
                GateStatus.REVIEW,
                (
                    *fidelity_signals.reason_codes,
                    "fidelity_signal_unavailable",
                ),
            )
        if fidelity_signals.lower_bound_decision == "reject":
            reasons = tuple(fidelity_signals.reason_codes) or (
                "candidate_not_resembling_source",
            )
            return GateResult(GateStatus.REJECT, reasons)
        if fidelity_signals.lower_bound_decision == "review":
            return GateResult(
                GateStatus.REVIEW,
                fidelity_signals.reason_codes,
            )
        return GateResult(GateStatus.PASS, fidelity_signals.reason_codes)


@dataclass(frozen=True)
class CorridorDecision:
    mode: CorridorMode
    policy_version: str
    calibration_version: str
    safety: GateResult
    privacy_upper_bound: GateResult
    fidelity_lower_bound: GateResult
    critical_signals_available: bool
    scores: Mapping[str, float]
    bands: Mapping[str, str]
    model_availability: Mapping[str, str]
    model_versions: Mapping[str, str]
    timing_ms: Mapping[str, float]
    reason_codes: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", CorridorMode.parse(self.mode))
        object.__setattr__(self, "scores", MappingProxyType(dict(self.scores)))
        object.__setattr__(self, "bands", MappingProxyType(dict(self.bands)))
        object.__setattr__(
            self,
            "model_availability",
            MappingProxyType(dict(self.model_availability)),
        )
        object.__setattr__(
            self,
            "model_versions",
            MappingProxyType(dict(self.model_versions)),
        )
        object.__setattr__(self, "timing_ms", MappingProxyType(dict(self.timing_ms)))
        object.__setattr__(
            self,
            "reason_codes",
            _ordered_reason_codes(self.reason_codes),
        )

    @property
    def eligible_for_ranking(self) -> bool:
        return bool(
            self.critical_signals_available
            and self.safety.status is GateStatus.PASS
            and self.privacy_upper_bound.status is GateStatus.PASS
            and self.fidelity_lower_bound.status is GateStatus.PASS
        )

    def to_document(self) -> dict[str, object]:
        return {
            "schemaVersion": CORRIDOR_SCHEMA_VERSION,
            "mode": self.mode.value,
            "policyVersion": _safe_version(
                self.policy_version,
                DEFAULT_CORRIDOR_POLICY_VERSION,
            ),
            "calibrationVersion": _safe_version(
                self.calibration_version,
                UNCALIBRATED_VERSION,
            ),
            "criticalSignalsAvailable": bool(self.critical_signals_available),
            "gates": {
                "safety": self.safety.status.value,
                "privacyUpperBound": self.privacy_upper_bound.status.value,
                "fidelityLowerBound": self.fidelity_lower_bound.status.value,
            },
            "bands": {
                "fidelity": _band(self.bands.get("fidelity")),
                "identityRisk": _band(self.bands.get("identityRisk")),
                "traitConsistency": _band(
                    self.bands.get("traitConsistency")
                ),
                "composition": _band(self.bands.get("composition")),
            },
            "scores": {
                key: round(number, 4)
                for key in FIDELITY_SCORE_KEYS
                if (number := _finite_number(self.scores.get(key))) is not None
            },
            "reasonCodes": list(_ordered_reason_codes(self.reason_codes)),
            "modelAvailability": {
                key: _availability(value)
                for key, value in self.model_availability.items()
                if key in (*FIDELITY_COMPONENT_KEYS, "identitySimilarity", "safety")
            },
            "modelVersions": {
                key: _safe_version(value, "unknown")
                for key, value in self.model_versions.items()
                if key in (*FIDELITY_COMPONENT_KEYS, "identitySimilarity")
            },
            "timingMs": {
                key: round(max(0.0, number), 3)
                for key, value in self.timing_ms.items()
                if key
                in (
                    *FIDELITY_COMPONENT_KEYS,
                    "identitySimilarity",
                    "total",
                )
                and (number := _finite_number(value)) is not None
            },
        }


def evaluate_fidelity_corridor(
    *,
    active_qa: Mapping[str, Any],
    identity_signal: Optional[IdentityPrivacySignal],
    fidelity_signals: Optional[FidelitySignalBundle],
    policy: Optional[CorridorPolicy] = None,
) -> CorridorDecision:
    active_policy = policy or CorridorPolicy.from_env()
    if active_policy.mode is CorridorMode.OFF:
        return _off_decision(active_policy)

    safety = SafetyGate().evaluate(active_qa)
    privacy = PrivacyUpperBoundGate().evaluate(identity_signal)
    fidelity = FidelityLowerBoundGate().evaluate(
        fidelity_signals,
        policy=active_policy,
    )
    signal_document = (
        fidelity_signals.to_document()
        if fidelity_signals is not None
        else FidelitySignalBundle.unavailable().to_document()
    )
    identity_document = (
        identity_signal.to_document()
        if identity_signal is not None
        else IdentityPrivacySignal().to_document()
    )

    model_availability = {
        **dict(signal_document["modelAvailability"]),
        "identitySimilarity": identity_document["modelAvailability"],
        "safety": (
            "unavailable"
            if "model_unavailable_systemic" in safety.reason_codes
            else "available"
        ),
    }
    model_versions = dict(signal_document["modelVersions"])
    if identity_document.get("modelVersion") is not None:
        model_versions["identitySimilarity"] = identity_document["modelVersion"]
    timing_ms = dict(signal_document["timingMs"])
    if identity_document.get("timingMs") is not None:
        timing_ms["identitySimilarity"] = identity_document["timingMs"]

    critical_available = bool(
        safety.status is not GateStatus.REVIEW
        and identity_signal is not None
        and identity_signal.critical_signal_available
        and fidelity_signals is not None
        and fidelity_signals.critical_signals_available
        and not fidelity_signals.conflicting
        and active_policy.calibrated
    )
    reasons = _ordered_reason_codes(
        (
            *safety.reason_codes,
            *privacy.reason_codes,
            *fidelity.reason_codes,
        )
    )
    return CorridorDecision(
        mode=active_policy.mode,
        policy_version=active_policy.policy_version,
        calibration_version=active_policy.calibration_version,
        safety=safety,
        privacy_upper_bound=privacy,
        fidelity_lower_bound=fidelity,
        critical_signals_available=critical_available,
        scores=dict(signal_document["scores"]),
        bands={
            **dict(signal_document["bands"]),
            "identityRisk": identity_document["band"],
        },
        model_availability=model_availability,
        model_versions=model_versions,
        timing_ms=timing_ms,
        reason_codes=reasons,
    )


def attach_shadow_corridor_document(
    active_qa: Mapping[str, Any],
    decision: CorridorDecision,
) -> dict[str, Any]:
    """Return a copy with nested shadow evidence and no active-field mutation."""

    document = copy.deepcopy(dict(active_qa))
    if decision.mode is CorridorMode.SHADOW:
        document["fidelityCorridor"] = decision.to_document()
    return document


@dataclass(frozen=True)
class CorridorCandidate:
    candidate_id: str
    decision: CorridorDecision
    fidelity_signals: FidelitySignalBundle


@dataclass(frozen=True)
class SafeCandidateRankingResult:
    ranked_candidate_ids: Sequence[str]
    excluded_reason_codes_by_candidate_id: Mapping[str, Sequence[str]]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ranked_candidate_ids",
            tuple(str(value) for value in self.ranked_candidate_ids),
        )
        object.__setattr__(
            self,
            "excluded_reason_codes_by_candidate_id",
            MappingProxyType(
                {
                    str(candidate_id): _ordered_reason_codes(reasons)
                    for candidate_id, reasons in sorted(
                        self.excluded_reason_codes_by_candidate_id.items()
                    )
                }
            ),
        )

    def to_document(self) -> dict[str, object]:
        return {
            "schemaVersion": "avatar_safe_candidate_ranking_v1",
            "rankedCandidateIds": list(self.ranked_candidate_ids),
            "excludedReasonCodesByCandidateId": {
                candidate_id: list(reasons)
                for candidate_id, reasons in self.excluded_reason_codes_by_candidate_id.items()
            },
        }


class SafeCandidateRanking:
    """Deterministic ranking over broad fidelity signals only."""

    def rank(
        self,
        candidates: Sequence[CorridorCandidate],
    ) -> SafeCandidateRankingResult:
        eligible: list[CorridorCandidate] = []
        excluded: dict[str, tuple[str, ...]] = {}
        seen: set[str] = set()

        for candidate in candidates:
            candidate_id = str(candidate.candidate_id or "")
            if not candidate_id or candidate_id in seen:
                raise ValueError("Candidate IDs must be non-empty and unique.")
            seen.add(candidate_id)
            if candidate.decision.eligible_for_ranking:
                eligible.append(candidate)
                continue

            reasons = list(candidate.decision.reason_codes)
            if (
                candidate.decision.safety.status is not GateStatus.PASS
                or candidate.decision.privacy_upper_bound.status
                is GateStatus.REJECT
            ):
                reasons.append("unsafe_candidate_excluded_from_ranking")
            excluded[candidate_id] = _ordered_reason_codes(reasons)

        eligible.sort(key=_safe_rank_key)
        return SafeCandidateRankingResult(
            ranked_candidate_ids=tuple(
                candidate.candidate_id for candidate in eligible
            ),
            excluded_reason_codes_by_candidate_id=excluded,
        )


def _safe_rank_key(
    candidate: CorridorCandidate,
) -> tuple[float, float, float, float, float, float, str]:
    vector = candidate.fidelity_signals.ranking_vector()
    return (*(-value for value in vector), str(candidate.candidate_id))


def _off_decision(policy: CorridorPolicy) -> CorridorDecision:
    review = GateResult(GateStatus.REVIEW)
    return CorridorDecision(
        mode=policy.mode,
        policy_version=policy.policy_version,
        calibration_version=policy.calibration_version,
        safety=review,
        privacy_upper_bound=review,
        fidelity_lower_bound=review,
        critical_signals_available=False,
        scores={},
        bands={
            "fidelity": "unavailable",
            "identityRisk": "unavailable",
            "traitConsistency": "unavailable",
            "composition": "unavailable",
        },
        model_availability={
            **{key: "unavailable" for key in FIDELITY_COMPONENT_KEYS},
            "identitySimilarity": "unavailable",
            "safety": "unavailable",
        },
        model_versions={},
        timing_ms={},
        reason_codes=(),
    )


def _active_model_unavailable(active_qa: Mapping[str, Any]) -> bool:
    if active_qa.get("modelsUnavailable") is True:
        return True
    version = str(active_qa.get("qaVersion") or "").strip().lower()
    if "model_unavailable" in version:
        return True
    if any(
        reason == "model_unavailable" or reason.endswith("_unavailable")
        for reason in _string_sequence(active_qa.get("reviewReasons"))
    ):
        return True
    for availability in (
        active_qa.get("modelAvailability"),
        (
            active_qa.get("debug", {}).get("modelAvailability")
            if isinstance(active_qa.get("debug"), Mapping)
            else None
        ),
    ):
        if not isinstance(availability, Mapping):
            continue
        if any(
            str(value or "").strip().lower() in _UNAVAILABLE_STATES
            for value in availability.values()
        ):
            return True
    return False


def _ordered_reason_codes(values: Sequence[str]) -> tuple[str, ...]:
    present = {
        str(value or "").strip()
        for value in values
        if str(value or "").strip() in REASON_CODE_ALLOWLIST
    }
    return tuple(code for code in REASON_CODE_ORDER if code in present)


def _string_sequence(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item or "").strip() for item in value)


def _safe_version(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if (
        not text
        or len(text) > 128
        or "\\" in text
        or ".." in text
        or "://" in text
        or not _SAFE_VERSION.fullmatch(text)
    ):
        return fallback
    return text


def _band(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _IDENTITY_BANDS else "unavailable"


def _availability(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"available", "unavailable", "uncalibrated", "conflict"}:
        return normalized
    return "unavailable"


def _finite_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


__all__ = [
    "CORRIDOR_SCHEMA_VERSION",
    "DEFAULT_CORRIDOR_MODE",
    "DEFAULT_CORRIDOR_POLICY_VERSION",
    "UNCALIBRATED_VERSION",
    "CorridorCandidate",
    "CorridorDecision",
    "CorridorMode",
    "CorridorPolicy",
    "FidelityLowerBoundGate",
    "GateResult",
    "GateStatus",
    "IdentityPrivacySignal",
    "PrivacyUpperBoundGate",
    "REASON_CODE_ALLOWLIST",
    "REASON_CODE_ORDER",
    "SafeCandidateRanking",
    "SafeCandidateRankingResult",
    "SafetyGate",
    "attach_shadow_corridor_document",
    "evaluate_fidelity_corridor",
]
