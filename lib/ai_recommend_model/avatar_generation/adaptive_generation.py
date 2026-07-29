from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Mapping, Optional, Sequence

from avatar_generation.preview_policy import (
    is_hard_reject,
    is_preview_eligible,
    is_soft_pass,
)


DEFAULT_INITIAL_CANDIDATE_COUNT = 4
DEFAULT_EXTRA_CANDIDATE_COUNT = 4
DEFAULT_MAX_CANDIDATE_COUNT = 8
DEFAULT_PREVIEW_CANDIDATE_COUNT = 4
DEFAULT_MIN_SAFE_BEFORE_EXTRA = 2
DEFAULT_MIN_PREVIEW_CANDIDATE_COUNT = 1

ENV_INITIAL_CANDIDATES = "AVATAR_INITIAL_CANDIDATE_COUNT"
ENV_EXTRA_CANDIDATES = "AVATAR_EXTRA_CANDIDATE_COUNT"
ENV_MAX_CANDIDATES = "AVATAR_MAX_TOTAL_CANDIDATES"
ENV_PREVIEW_CANDIDATES = "AVATAR_PREVIEW_COUNT"
ENV_MIN_PREVIEW_CANDIDATES = "AVATAR_MIN_PREVIEW_CANDIDATES"
ENV_MIN_SAFE_BEFORE_EXTRA = "AVATAR_MIN_SAFE_CANDIDATES_BEFORE_EXTRA"
ENV_PREVIEW_REQUIRE_FOUR = "AVATAR_PREVIEW_REQUIRE_FOUR"
ENV_SOFT_PASS_FILL_ENABLED = "AVATAR_PREVIEW_FILL_WITH_SOFT_PASS"
ENV_HARD_REJECT_FILL_ENABLED = "AVATAR_PREVIEW_FILL_HARD_REJECT"
ENV_NEEDS_REVIEW_LOW_RISK_ENABLED = "AVATAR_PREVIEW_FILL_WITH_NEEDS_REVIEW_LOW_RISK"

LEGACY_ENV_ALIASES = {
    ENV_INITIAL_CANDIDATES: ("AVATAR_ADAPTIVE_INITIAL_CANDIDATES",),
    ENV_EXTRA_CANDIDATES: ("AVATAR_ADAPTIVE_EXTRA_CANDIDATES",),
    ENV_MAX_CANDIDATES: ("AVATAR_ADAPTIVE_MAX_CANDIDATES",),
    ENV_PREVIEW_CANDIDATES: ("AVATAR_ADAPTIVE_PREVIEW_CANDIDATES",),
    ENV_MIN_PREVIEW_CANDIDATES: ("AVATAR_ADAPTIVE_MIN_PREVIEW_CANDIDATES",),
    ENV_MIN_SAFE_BEFORE_EXTRA: ("AVATAR_ADAPTIVE_MIN_SAFE_BEFORE_EXTRA",),
    ENV_SOFT_PASS_FILL_ENABLED: ("AVATAR_ADAPTIVE_SOFT_PASS_FILL_ENABLED",),
    ENV_NEEDS_REVIEW_LOW_RISK_ENABLED: ("AVATAR_ADAPTIVE_NEEDS_REVIEW_LOW_RISK_ENABLED",),
}


@dataclass(frozen=True)
class AdaptiveGenerationPolicy:
    initial_candidate_count: int = DEFAULT_INITIAL_CANDIDATE_COUNT
    extra_candidate_count: int = DEFAULT_EXTRA_CANDIDATE_COUNT
    max_candidate_count: int = DEFAULT_MAX_CANDIDATE_COUNT
    preview_candidate_count: int = DEFAULT_PREVIEW_CANDIDATE_COUNT
    min_preview_candidate_count: int = DEFAULT_MIN_PREVIEW_CANDIDATE_COUNT
    min_safe_before_extra: int = DEFAULT_MIN_SAFE_BEFORE_EXTRA
    require_four_preview: bool = False
    soft_pass_fill_enabled: bool = True
    hard_reject_fill_enabled: bool = False
    needs_review_low_risk_enabled: bool = False

    @classmethod
    def from_env(cls) -> "AdaptiveGenerationPolicy":
        return cls(
            initial_candidate_count=_read_int_env_any(
                ENV_INITIAL_CANDIDATES,
                DEFAULT_INITIAL_CANDIDATE_COUNT,
            ),
            extra_candidate_count=_read_int_env_any(
                ENV_EXTRA_CANDIDATES,
                DEFAULT_EXTRA_CANDIDATE_COUNT,
            ),
            max_candidate_count=_read_int_env_any(
                ENV_MAX_CANDIDATES,
                DEFAULT_MAX_CANDIDATE_COUNT,
            ),
            preview_candidate_count=_read_int_env_any(
                ENV_PREVIEW_CANDIDATES,
                DEFAULT_PREVIEW_CANDIDATE_COUNT,
            ),
            min_preview_candidate_count=_read_int_env_any(
                ENV_MIN_PREVIEW_CANDIDATES,
                DEFAULT_MIN_PREVIEW_CANDIDATE_COUNT,
            ),
            min_safe_before_extra=_read_int_env_any(
                ENV_MIN_SAFE_BEFORE_EXTRA,
                DEFAULT_MIN_SAFE_BEFORE_EXTRA,
            ),
            require_four_preview=_read_bool_env_any(ENV_PREVIEW_REQUIRE_FOUR, False),
            soft_pass_fill_enabled=_read_bool_env_any(ENV_SOFT_PASS_FILL_ENABLED, True),
            hard_reject_fill_enabled=False,
            needs_review_low_risk_enabled=_read_bool_env_any(
                ENV_NEEDS_REVIEW_LOW_RISK_ENABLED
            ),
        )


@dataclass(frozen=True)
class GenerationBudget:
    remaining_deadline_seconds: Optional[float] = None
    min_extra_round_seconds: float = 0
    remaining_candidate_budget: Optional[int] = None
    remaining_usd: Optional[float] = None
    estimated_usd_per_candidate: Optional[float] = None


@dataclass(frozen=True)
class GenerationPlan:
    candidate_count: int
    existing_candidate_count: int
    safe_candidate_count: int
    max_candidate_count: int
    preview_candidate_count: int
    reason: str
    blocked_reasons: tuple[str, ...] = ()

    @property
    def should_generate(self) -> bool:
        return self.candidate_count > 0

    @property
    def total_after_generation(self) -> int:
        return self.existing_candidate_count + self.candidate_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidateCount": self.candidate_count,
            "existingCandidateCount": self.existing_candidate_count,
            "safeCandidateCount": self.safe_candidate_count,
            "maxCandidateCount": self.max_candidate_count,
            "previewCandidateCount": self.preview_candidate_count,
            "shouldGenerate": self.should_generate,
            "totalAfterGeneration": self.total_after_generation,
            "reason": self.reason,
            "blockedReasons": list(self.blocked_reasons),
        }


def plan_generation_round(
    existing_candidates: Optional[Sequence[Mapping[str, Any]]] = None,
    *,
    policy: Optional[AdaptiveGenerationPolicy] = None,
    budget: Optional[GenerationBudget] = None,
    regenerate_requested: bool = False,
    retry_attempt: int = 0,
    adaptive_retry_enabled: bool = False,
) -> GenerationPlan:
    active_policy = policy or AdaptiveGenerationPolicy.from_env()
    candidates = list(existing_candidates or [])
    existing_count = len(candidates)
    safe_count = sum(
        1 for candidate in candidates if _counts_as_safe(candidate, active_policy)
    )
    remaining_capacity = max(0, active_policy.max_candidate_count - existing_count)

    if remaining_capacity <= 0:
        return _plan(
            0,
            existing_count,
            safe_count,
            active_policy,
            reason="max_total_reached",
            blocked_reasons=("max_total_reached",),
        )

    if existing_count == 0:
        candidate_count, blocked_reasons = _apply_budget_constraints(
            min(active_policy.initial_candidate_count, remaining_capacity),
            budget,
            require_extra_round_time=False,
        )
        return _plan(
            candidate_count,
            existing_count,
            safe_count,
            active_policy,
            reason="initial" if candidate_count > 0 else "budget_blocked",
            blocked_reasons=blocked_reasons,
        )

    systemic_unavailable_reason = _uniform_systemic_unavailable_reason(candidates)
    if systemic_unavailable_reason:
        return _plan(
            0,
            existing_count,
            safe_count,
            active_policy,
            reason="extra_suppressed_systemic_unavailable",
            blocked_reasons=(systemic_unavailable_reason,),
        )

    if retry_attempt >= 1 and (
        regenerate_requested or safe_count < active_policy.min_safe_before_extra
    ):
        return _plan(
            0,
            existing_count,
            safe_count,
            active_policy,
            reason="retry_limit_reached",
            blocked_reasons=("retry_limit_reached",),
        )

    if regenerate_requested:
        candidate_count, blocked_reasons = _apply_budget_constraints(
            min(active_policy.extra_candidate_count, remaining_capacity),
            budget,
            require_extra_round_time=True,
        )
        return _plan(
            candidate_count,
            existing_count,
            safe_count,
            active_policy,
            reason="regenerate_extra" if candidate_count > 0 else "budget_blocked",
            blocked_reasons=blocked_reasons,
        )

    adaptive_retry_reason = (
        _uniform_adaptive_retry_reason(candidates) if adaptive_retry_enabled else ""
    )
    if adaptive_retry_reason:
        candidate_count, blocked_reasons = _apply_budget_constraints(
            min(active_policy.extra_candidate_count, remaining_capacity),
            budget,
            require_extra_round_time=True,
        )
        return _plan(
            candidate_count,
            existing_count,
            safe_count,
            active_policy,
            reason=adaptive_retry_reason if candidate_count > 0 else "budget_blocked",
            blocked_reasons=blocked_reasons,
        )

    if safe_count < active_policy.min_safe_before_extra:
        candidate_count, blocked_reasons = _apply_budget_constraints(
            min(active_policy.extra_candidate_count, remaining_capacity),
            budget,
            require_extra_round_time=True,
        )
        return _plan(
            candidate_count,
            existing_count,
            safe_count,
            active_policy,
            reason="extra_insufficient_safe" if candidate_count > 0 else "budget_blocked",
            blocked_reasons=blocked_reasons,
        )

    return _plan(
        0,
        existing_count,
        safe_count,
        active_policy,
        reason="enough_safe",
    )


def _apply_budget_constraints(
    requested_count: int,
    budget: Optional[GenerationBudget],
    *,
    require_extra_round_time: bool,
) -> tuple[int, tuple[str, ...]]:
    candidate_count = max(0, int(requested_count))
    if budget is None or candidate_count <= 0:
        return candidate_count, ()

    blocked_reasons: list[str] = []

    if (
        require_extra_round_time
        and budget.remaining_deadline_seconds is not None
        and budget.remaining_deadline_seconds < max(0, budget.min_extra_round_seconds)
    ):
        blocked_reasons.append("deadline_insufficient")

    if budget.remaining_candidate_budget is not None:
        remaining_candidates = max(0, int(budget.remaining_candidate_budget))
        if remaining_candidates <= 0:
            blocked_reasons.append("candidate_budget_exhausted")
        else:
            candidate_count = min(candidate_count, remaining_candidates)

    if (
        budget.remaining_usd is not None
        and budget.estimated_usd_per_candidate is not None
        and budget.estimated_usd_per_candidate > 0
    ):
        affordable_count = int(
            max(0, budget.remaining_usd) // budget.estimated_usd_per_candidate
        )
        if affordable_count <= 0:
            blocked_reasons.append("cost_budget_insufficient")
        else:
            candidate_count = min(candidate_count, affordable_count)

    if blocked_reasons:
        return 0, tuple(blocked_reasons)
    return candidate_count, ()


def _plan(
    candidate_count: int,
    existing_count: int,
    safe_count: int,
    policy: AdaptiveGenerationPolicy,
    *,
    reason: str,
    blocked_reasons: Sequence[str] = (),
) -> GenerationPlan:
    return GenerationPlan(
        candidate_count=max(0, int(candidate_count)),
        existing_candidate_count=max(0, int(existing_count)),
        safe_candidate_count=max(0, int(safe_count)),
        max_candidate_count=max(0, int(policy.max_candidate_count)),
        preview_candidate_count=max(0, int(policy.preview_candidate_count)),
        reason=reason,
        blocked_reasons=tuple(blocked_reasons),
    )


FIDELITY_RETRY_REASONS = frozenset(
    {
        "candidate_not_resembling_source",
        "candidate_trait_mismatch",
        "candidate_generation_generic",
    }
)
PRIVACY_RETRY_REASONS = frozenset({"candidate_too_identifiable", "too_identifiable"})


def _uniform_adaptive_retry_reason(
    candidates: Sequence[Mapping[str, Any]],
) -> str:
    if not candidates:
        return ""
    reasons_by_candidate = [
        _candidate_retry_reasons(candidate) for candidate in candidates
    ]
    if any(not reasons for reasons in reasons_by_candidate):
        return ""
    if all(reasons <= FIDELITY_RETRY_REASONS for reasons in reasons_by_candidate):
        return "fidelity_adjusted_retry"
    if all(reasons <= PRIVACY_RETRY_REASONS for reasons in reasons_by_candidate):
        return "privacy_strengthened_retry"
    return ""


def _candidate_retry_reasons(candidate: Mapping[str, Any]) -> set[str]:
    qa = candidate.get("qa")
    qa_doc = qa if isinstance(qa, Mapping) else {}
    reasons: set[str] = set()
    for key in ("rejectReasons", "reviewReasons", "blockedReasons"):
        reasons.update(_normalized_reason_codes(qa_doc.get(key)))
    fidelity_corridor = qa_doc.get("fidelityCorridor")
    if isinstance(fidelity_corridor, Mapping):
        reasons.update(_normalized_reason_codes(fidelity_corridor.get("reasonCodes")))
    return reasons


def _normalized_reason_codes(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value.strip().lower()} if value.strip() else set()
    if isinstance(value, Mapping):
        return set()
    try:
        iterator = iter(value or ())
    except TypeError:
        return set()
    return {
        str(reason or "").strip().lower()
        for reason in iterator
        if str(reason or "").strip()
    }


def _uniform_systemic_unavailable_reason(
    candidates: Sequence[Mapping[str, Any]],
) -> str:
    if not candidates:
        return ""
    reasons = [_systemic_unavailable_reason(candidate) for candidate in candidates]
    if any(not reason for reason in reasons) or len(set(reasons)) != 1:
        return ""
    if any(is_hard_reject(candidate) or is_preview_eligible(candidate) for candidate in candidates):
        return ""
    return next(iter(reasons))


def _systemic_unavailable_reason(candidate: Mapping[str, Any]) -> str:
    qa = candidate.get("qa")
    qa_doc = qa if isinstance(qa, Mapping) else {}
    qa_version = str(qa_doc.get("qaVersion") or "").strip().lower()
    if "policy_unavailable" in qa_version:
        return "qa_policy_unavailable"
    if "model_unavailable" in qa_version:
        return "qa_critical_model_unavailable"
    for reason in qa_doc.get("reviewReasons") or ():
        lowered = str(reason or "").strip().lower()
        if lowered in {"model_unavailable", "qa_model_signal_review"}:
            return "qa_critical_model_unavailable"
        if lowered == "policy_unavailable" or lowered.endswith("policy_unavailable"):
            return "qa_policy_unavailable"
        if lowered.endswith("_unavailable"):
            return "qa_critical_model_unavailable"
    debug = qa_doc.get("debug")
    if not isinstance(debug, Mapping):
        return ""
    model_availability = debug.get("modelAvailability")
    if not isinstance(model_availability, Mapping):
        return ""
    unavailable = {"unavailable", "critical_unavailable", "uncalibrated"}
    for key, value in model_availability.items():
        if str(value or "").strip().lower() not in unavailable:
            continue
        lowered_key = str(key or "").strip().lower()
        if "policy" in lowered_key:
            return "qa_policy_unavailable"
        return "qa_critical_model_unavailable"
    return ""


def _counts_as_safe(
    candidate: Mapping[str, Any],
    policy: AdaptiveGenerationPolicy,
) -> bool:
    if is_hard_reject(candidate):
        return False
    if is_preview_eligible(candidate) and (
        not is_soft_pass(candidate) or policy.soft_pass_fill_enabled
    ):
        return True
    return False


def _read_int_env(name: str, fallback: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    try:
        value = int(raw)
    except ValueError:
        return fallback
    return value if value >= 0 else fallback


def _read_int_env_any(name: str, fallback: int) -> int:
    names = (name, *LEGACY_ENV_ALIASES.get(name, ()))
    for candidate in names:
        if os.environ.get(candidate) is not None:
            return _read_int_env(candidate, fallback)
    return fallback


def _read_bool_env_any(name: str, fallback: bool = False) -> bool:
    names = (name, *LEGACY_ENV_ALIASES.get(name, ()))
    for candidate in names:
        raw = os.environ.get(candidate)
        if raw is None:
            continue
        normalized = raw.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return fallback


__all__ = [
    "DEFAULT_EXTRA_CANDIDATE_COUNT",
    "DEFAULT_INITIAL_CANDIDATE_COUNT",
    "DEFAULT_MAX_CANDIDATE_COUNT",
    "DEFAULT_MIN_SAFE_BEFORE_EXTRA",
    "DEFAULT_MIN_PREVIEW_CANDIDATE_COUNT",
    "DEFAULT_PREVIEW_CANDIDATE_COUNT",
    "AdaptiveGenerationPolicy",
    "GenerationBudget",
    "GenerationPlan",
    "plan_generation_round",
]
