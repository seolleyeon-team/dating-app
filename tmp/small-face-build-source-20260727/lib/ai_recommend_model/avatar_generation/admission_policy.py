from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


DEFAULT_INITIAL_CANDIDATE_COUNT = 4
DEFAULT_EXTRA_CANDIDATE_COUNT = 4
DEFAULT_MAX_TOTAL_CANDIDATES = 8
DEFAULT_MAX_RETRY_ATTEMPTS = 3
DEFAULT_MIN_INITIAL_DEADLINE_SECONDS = 20.0
DEFAULT_MIN_EXTRA_DEADLINE_SECONDS = 30.0


@dataclass(frozen=True)
class CumulativeUsage:
    daily_count: int = 0
    monthly_count: int = 0
    daily_usd: float = 0.0
    monthly_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dailyCount": self.daily_count,
            "monthlyCount": self.monthly_count,
            "dailyUsd": self.daily_usd,
            "monthlyUsd": self.monthly_usd,
        }


@dataclass(frozen=True)
class AdmissionPolicy:
    initial_candidate_count: int = DEFAULT_INITIAL_CANDIDATE_COUNT
    extra_candidate_count: int = DEFAULT_EXTRA_CANDIDATE_COUNT
    max_total_candidates: int = DEFAULT_MAX_TOTAL_CANDIDATES
    max_retry_attempts: int = DEFAULT_MAX_RETRY_ATTEMPTS
    min_initial_deadline_seconds: float = DEFAULT_MIN_INITIAL_DEADLINE_SECONDS
    min_extra_deadline_seconds: float = DEFAULT_MIN_EXTRA_DEADLINE_SECONDS
    estimated_usd_per_candidate: Optional[float] = None
    hard_daily_generation_limit: int = 0
    hard_monthly_generation_limit: int = 0
    hard_daily_usd_limit: float = 0.0
    hard_monthly_usd_limit: float = 0.0
    kill_switch_enabled: bool = False
    disable_new_generation: bool = False
    gpu_worker_enabled: bool = True
    enforce_budget: bool = False
    production_like: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "AdmissionPolicy":
        return cls(
            initial_candidate_count=_env_int(env, "AVATAR_INITIAL_CANDIDATE_COUNT", DEFAULT_INITIAL_CANDIDATE_COUNT),
            extra_candidate_count=_env_int(env, "AVATAR_EXTRA_CANDIDATE_COUNT", DEFAULT_EXTRA_CANDIDATE_COUNT),
            max_total_candidates=_env_int(env, "AVATAR_MAX_TOTAL_CANDIDATES", DEFAULT_MAX_TOTAL_CANDIDATES),
            max_retry_attempts=_env_int(env, "AVATAR_MAX_RETRY_ATTEMPTS", DEFAULT_MAX_RETRY_ATTEMPTS),
            min_initial_deadline_seconds=_env_float(
                env,
                "AVATAR_MIN_INITIAL_DEADLINE_SECONDS",
                DEFAULT_MIN_INITIAL_DEADLINE_SECONDS,
            ),
            min_extra_deadline_seconds=_env_float(
                env,
                "AVATAR_MIN_EXTRA_DEADLINE_SECONDS",
                DEFAULT_MIN_EXTRA_DEADLINE_SECONDS,
            ),
            estimated_usd_per_candidate=_env_optional_float(env, "AVATAR_ESTIMATED_USD_PER_CANDIDATE"),
            hard_daily_generation_limit=_env_int(env, "AVATAR_COST_HARD_DAILY_GENERATION_LIMIT", 0),
            hard_monthly_generation_limit=_env_int(env, "AVATAR_COST_HARD_MONTHLY_GENERATION_LIMIT", 0),
            hard_daily_usd_limit=_env_float(env, "AVATAR_COST_ALERT_DAILY_USD", 0.0),
            hard_monthly_usd_limit=_env_float(env, "AVATAR_COST_ALERT_MONTHLY_USD", 0.0),
            kill_switch_enabled=_env_bool_any(env, ("AVATAR_COST_KILL_SWITCH_ENABLED", "AVATAR_KILL_SWITCH", "AVATAR_GENERATION_BUDGET_EXHAUSTED"), False),
            disable_new_generation=_env_bool_any(env, ("AVATAR_DISABLE_NEW_GENERATION", "AVATAR_GENERATION_DISABLED", "AVATAR_GENERATION_PAUSED"), False),
            gpu_worker_enabled=_env_bool(env, "AVATAR_GPU_WORKER_ENABLED", True),
            enforce_budget=_env_bool(env, "AVATAR_COST_ENFORCE_BUDGET", _is_production_like(env)),
            production_like=_is_production_like(env),
        )

    @classmethod
    def from_cost_config(
        cls,
        cost_config: Any,
        *,
        estimated_usd_per_candidate: Optional[float] = None,
        env: Mapping[str, str] = os.environ,
    ) -> "AdmissionPolicy":
        env_policy = cls.from_env(env)
        return cls(
            initial_candidate_count=env_policy.initial_candidate_count,
            extra_candidate_count=env_policy.extra_candidate_count,
            max_total_candidates=env_policy.max_total_candidates,
            max_retry_attempts=env_policy.max_retry_attempts,
            min_initial_deadline_seconds=env_policy.min_initial_deadline_seconds,
            min_extra_deadline_seconds=env_policy.min_extra_deadline_seconds,
            estimated_usd_per_candidate=estimated_usd_per_candidate,
            hard_daily_generation_limit=int(getattr(cost_config, "hard_daily_generation_limit", 0) or 0),
            hard_monthly_generation_limit=int(getattr(cost_config, "hard_monthly_generation_limit", 0) or 0),
            hard_daily_usd_limit=float(getattr(cost_config, "daily_alert_usd", 0.0) or 0.0),
            hard_monthly_usd_limit=float(getattr(cost_config, "monthly_alert_usd", 0.0) or 0.0),
            kill_switch_enabled=bool(getattr(cost_config, "kill_switch_enabled", False)) or _env_bool_any(env, ("AVATAR_COST_KILL_SWITCH_ENABLED", "AVATAR_KILL_SWITCH", "AVATAR_GENERATION_BUDGET_EXHAUSTED"), False),
            disable_new_generation=_env_bool_any(env, ("AVATAR_DISABLE_NEW_GENERATION", "AVATAR_GENERATION_DISABLED", "AVATAR_GENERATION_PAUSED"), False),
            gpu_worker_enabled=_env_bool(env, "AVATAR_GPU_WORKER_ENABLED", True),
            enforce_budget=bool(getattr(cost_config, "enforce_budget", False)),
            production_like=_is_production_like(env),
        )


@dataclass(frozen=True)
class AdmissionRequest:
    phase: str
    existing_candidate_count: int = 0
    retry_attempt: int = 0
    remaining_deadline_seconds: Optional[float] = None
    usage: Optional[CumulativeUsage] = None


@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    reason: str
    candidate_count: int = 0
    projected_daily_count: int = 0
    projected_monthly_count: int = 0
    projected_daily_usd: float = 0.0
    projected_monthly_usd: float = 0.0
    blocked_reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "candidateCount": self.candidate_count,
            "projectedDailyCount": self.projected_daily_count,
            "projectedMonthlyCount": self.projected_monthly_count,
            "projectedDailyUsd": self.projected_daily_usd,
            "projectedMonthlyUsd": self.projected_monthly_usd,
            "blockedReasons": list(self.blocked_reasons),
        }


def usage_from_cost_aggregate(aggregate: Any) -> CumulativeUsage:
    return CumulativeUsage(
        daily_count=max(0, int(getattr(aggregate, "daily_count", 0) or 0)),
        monthly_count=max(0, int(getattr(aggregate, "monthly_count", 0) or 0)),
        daily_usd=_round_money(float(getattr(aggregate, "daily_usd", 0.0) or 0.0)),
        monthly_usd=_round_money(float(getattr(aggregate, "monthly_usd", 0.0) or 0.0)),
    )


def evaluate_admission(request: AdmissionRequest, *, policy: Optional[AdmissionPolicy] = None) -> AdmissionDecision:
    active_policy = policy or AdmissionPolicy.from_env()
    base_usage = request.usage or CumulativeUsage()

    blocked = _static_block_reason(request, active_policy)
    if blocked:
        return _blocked(blocked, base_usage)

    candidate_count = _requested_candidate_count(request, active_policy)
    if candidate_count <= 0:
        return _blocked("candidate_limit_exceeded", base_usage)

    if _requires_cumulative_usage(active_policy) and request.usage is None:
        return _blocked("cumulative_guard_unavailable", base_usage)

    projected_daily_count = base_usage.daily_count + 1
    projected_monthly_count = base_usage.monthly_count + 1
    projected_candidate_count = max(0, int(request.existing_candidate_count)) + candidate_count
    projected_usd = _projected_request_usd(projected_candidate_count, active_policy)
    projected_daily_usd = _round_money(base_usage.daily_usd + projected_usd)
    projected_monthly_usd = _round_money(base_usage.monthly_usd + projected_usd)

    blocked = _cumulative_block_reason(
        active_policy,
        projected_daily_count=projected_daily_count,
        projected_monthly_count=projected_monthly_count,
        projected_daily_usd=projected_daily_usd,
        projected_monthly_usd=projected_monthly_usd,
    )
    if blocked:
        return AdmissionDecision(
            allowed=False,
            reason=blocked,
            projected_daily_count=projected_daily_count,
            projected_monthly_count=projected_monthly_count,
            projected_daily_usd=projected_daily_usd,
            projected_monthly_usd=projected_monthly_usd,
            blocked_reasons=(blocked,),
        )

    return AdmissionDecision(
        allowed=True,
        reason="admitted",
        candidate_count=candidate_count,
        projected_daily_count=projected_daily_count,
        projected_monthly_count=projected_monthly_count,
        projected_daily_usd=projected_daily_usd,
        projected_monthly_usd=projected_monthly_usd,
    )


def _static_block_reason(request: AdmissionRequest, policy: AdmissionPolicy) -> str:
    if policy.kill_switch_enabled:
        return "cost_kill_switch_enabled"
    if policy.disable_new_generation:
        return "new_generation_disabled"
    if not policy.gpu_worker_enabled:
        return "gpu_worker_disabled"
    if request.phase not in {"initial", "extra"}:
        return "invalid_generation_phase"
    if max(0, int(request.retry_attempt)) >= max(0, int(policy.max_retry_attempts)):
        return "retry_limit_exceeded"
    min_deadline = (
        policy.min_initial_deadline_seconds
        if request.phase == "initial"
        else policy.min_extra_deadline_seconds
    )
    if request.remaining_deadline_seconds is not None and request.remaining_deadline_seconds < max(0.0, min_deadline):
        return "deadline_insufficient"
    return ""


def _requested_candidate_count(request: AdmissionRequest, policy: AdmissionPolicy) -> int:
    existing_count = max(0, int(request.existing_candidate_count))
    remaining = max(0, int(policy.max_total_candidates) - existing_count)
    requested = policy.initial_candidate_count if request.phase == "initial" else policy.extra_candidate_count
    return min(max(0, int(requested)), remaining)


def _requires_cumulative_usage(policy: AdmissionPolicy) -> bool:
    if not policy.production_like:
        return False
    return True


def _cumulative_block_reason(
    policy: AdmissionPolicy,
    *,
    projected_daily_count: int,
    projected_monthly_count: int,
    projected_daily_usd: float,
    projected_monthly_usd: float,
) -> str:
    if policy.hard_daily_generation_limit > 0 and projected_daily_count > policy.hard_daily_generation_limit:
        return "daily_generation_quota_exceeded"
    if policy.hard_monthly_generation_limit > 0 and projected_monthly_count > policy.hard_monthly_generation_limit:
        return "monthly_generation_quota_exceeded"
    if not policy.enforce_budget:
        return ""
    if policy.hard_daily_usd_limit > 0 and projected_daily_usd > policy.hard_daily_usd_limit:
        return "daily_budget_exceeded"
    if policy.hard_monthly_usd_limit > 0 and projected_monthly_usd > policy.hard_monthly_usd_limit:
        return "monthly_budget_exceeded"
    return ""


def _projected_request_usd(candidate_count: int, policy: AdmissionPolicy) -> float:
    per_candidate = policy.estimated_usd_per_candidate
    if per_candidate is None or per_candidate <= 0:
        return 0.0
    return _round_money(max(0, int(candidate_count)) * per_candidate)


def _blocked(reason: str, usage: CumulativeUsage) -> AdmissionDecision:
    return AdmissionDecision(
        allowed=False,
        reason=reason,
        projected_daily_count=usage.daily_count,
        projected_monthly_count=usage.monthly_count,
        projected_daily_usd=usage.daily_usd,
        projected_monthly_usd=usage.monthly_usd,
        blocked_reasons=(reason,),
    )


def _env_optional_float(env: Mapping[str, str], name: str) -> Optional[float]:
    raw = str(env.get(name, "") or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def _env_float(env: Mapping[str, str], name: str, fallback: float) -> float:
    parsed = _env_optional_float(env, name)
    return fallback if parsed is None else parsed


def _env_int(env: Mapping[str, str], name: str, fallback: int) -> int:
    raw = str(env.get(name, "") or "").strip()
    if not raw:
        return fallback
    try:
        return max(0, int(raw))
    except ValueError:
        return fallback


def _env_bool_any(env: Mapping[str, str], names: tuple[str, ...], fallback: bool) -> bool:
    found_explicit = False
    for name in names:
        raw = env.get(name)
        if raw is None or not str(raw).strip():
            continue
        found_explicit = True
        if _env_bool(env, name, False):
            return True
    return False if found_explicit else fallback


def _env_bool(env: Mapping[str, str], name: str, fallback: bool) -> bool:
    raw = env.get(name)
    if raw is None or not str(raw).strip():
        return fallback
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return fallback


def _is_production_like(env: Mapping[str, str]) -> bool:
    environment = str(env.get("ENVIRONMENT", "") or "").strip().lower()
    node_env = str(env.get("NODE_ENV", "") or "").strip().lower()
    return environment in {"production", "prod", "production_bridge"} or node_env == "production"


def _round_money(value: float) -> float:
    return round(float(value) + 1e-12, 6)


__all__ = [
    "AdmissionDecision",
    "AdmissionPolicy",
    "AdmissionRequest",
    "CumulativeUsage",
    "evaluate_admission",
    "usage_from_cost_aggregate",
]
