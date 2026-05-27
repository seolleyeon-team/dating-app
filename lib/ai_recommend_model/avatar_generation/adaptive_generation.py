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
            hard_reject_fill_enabled=_read_bool_env_any(ENV_HARD_REJECT_FILL_ENABLED, False),
            needs_review_low_risk_enabled=_read_bool_env_any(
                ENV_NEEDS_REVIEW_LOW_RISK_ENABLED
            ),
        )


@dataclass(frozen=True)
class GenerationPlan:
    candidate_count: int
    existing_candidate_count: int
    safe_candidate_count: int
    max_candidate_count: int
    preview_candidate_count: int
    reason: str

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
        }


def plan_generation_round(
    existing_candidates: Optional[Sequence[Mapping[str, Any]]] = None,
    *,
    policy: Optional[AdaptiveGenerationPolicy] = None,
    regenerate_requested: bool = False,
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
        )

    if existing_count == 0:
        return _plan(
            min(active_policy.initial_candidate_count, remaining_capacity),
            existing_count,
            safe_count,
            active_policy,
            reason="initial",
        )

    if regenerate_requested:
        return _plan(
            min(active_policy.extra_candidate_count, remaining_capacity),
            existing_count,
            safe_count,
            active_policy,
            reason="regenerate_extra",
        )

    if safe_count < active_policy.min_safe_before_extra:
        return _plan(
            min(active_policy.extra_candidate_count, remaining_capacity),
            existing_count,
            safe_count,
            active_policy,
            reason="extra_insufficient_safe",
        )

    return _plan(
        0,
        existing_count,
        safe_count,
        active_policy,
        reason="enough_safe",
    )


def _plan(
    candidate_count: int,
    existing_count: int,
    safe_count: int,
    policy: AdaptiveGenerationPolicy,
    *,
    reason: str,
) -> GenerationPlan:
    return GenerationPlan(
        candidate_count=max(0, int(candidate_count)),
        existing_candidate_count=max(0, int(existing_count)),
        safe_candidate_count=max(0, int(safe_count)),
        max_candidate_count=max(0, int(policy.max_candidate_count)),
        preview_candidate_count=max(0, int(policy.preview_candidate_count)),
        reason=reason,
    )


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
    "GenerationPlan",
    "plan_generation_round",
]
