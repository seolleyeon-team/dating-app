from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


DEFAULT_GPU_USD_PER_SECOND = 0.0001867
DEFAULT_CPU_USD_PER_VCPU_SECOND = 0.000018
DEFAULT_MEMORY_USD_PER_GIB_SECOND = 0.000002
DEFAULT_VCPU = 4.0
DEFAULT_MEMORY_GIB = 16.0
DEFAULT_PRICING_VERSION = "cloud_run_l4_2026_05"
DEFAULT_DAILY_ALERT_USD = 10.0
DEFAULT_MONTHLY_ALERT_USD = 200.0
DEFAULT_HARD_DAILY_GENERATION_LIMIT = 500
DEFAULT_HARD_MONTHLY_GENERATION_LIMIT = 10000
DEFAULT_SCENARIO_USERS = 1000
DEFAULT_SCENARIO_CANDIDATES_PER_USER = 4

GENERATED_STATUSES = {"preview_ready", "approved", "needs_review", "failed", "no_previewable_candidates"}


@dataclass(frozen=True)
class AvatarCostConfig:
    gpu_usd_per_second: float = DEFAULT_GPU_USD_PER_SECOND
    cpu_usd_per_vcpu_second: float = DEFAULT_CPU_USD_PER_VCPU_SECOND
    memory_usd_per_gib_second: float = DEFAULT_MEMORY_USD_PER_GIB_SECOND
    gpu_zonal_redundancy: bool = False
    vcpu: float = DEFAULT_VCPU
    memory_gib: float = DEFAULT_MEMORY_GIB
    pricing_version: str = DEFAULT_PRICING_VERSION
    daily_alert_usd: float = DEFAULT_DAILY_ALERT_USD
    monthly_alert_usd: float = DEFAULT_MONTHLY_ALERT_USD
    hard_daily_generation_limit: int = DEFAULT_HARD_DAILY_GENERATION_LIMIT
    hard_monthly_generation_limit: int = DEFAULT_HARD_MONTHLY_GENERATION_LIMIT
    kill_switch_enabled: bool = False
    enforce_budget: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "AvatarCostConfig":
        return cls(
            gpu_usd_per_second=_env_float(env, "CLOUD_RUN_L4_GPU_USD_PER_SECOND", DEFAULT_GPU_USD_PER_SECOND),
            cpu_usd_per_vcpu_second=_env_float(
                env,
                "CLOUD_RUN_CPU_USD_PER_VCPU_SECOND",
                DEFAULT_CPU_USD_PER_VCPU_SECOND,
            ),
            memory_usd_per_gib_second=_env_float(
                env,
                "CLOUD_RUN_MEMORY_USD_PER_GIB_SECOND",
                DEFAULT_MEMORY_USD_PER_GIB_SECOND,
            ),
            gpu_zonal_redundancy=_env_bool(env, "CLOUD_RUN_GPU_ZONAL_REDUNDANCY", False),
            vcpu=_env_float(env, "CLOUD_RUN_VCPU", DEFAULT_VCPU),
            memory_gib=_env_float(env, "CLOUD_RUN_MEMORY_GIB", DEFAULT_MEMORY_GIB),
            pricing_version=_env_text(env, "CLOUD_RUN_PRICING_VERSION", DEFAULT_PRICING_VERSION),
            daily_alert_usd=_env_float(env, "AVATAR_COST_ALERT_DAILY_USD", DEFAULT_DAILY_ALERT_USD),
            monthly_alert_usd=_env_float(env, "AVATAR_COST_ALERT_MONTHLY_USD", DEFAULT_MONTHLY_ALERT_USD),
            hard_daily_generation_limit=_env_int(
                env,
                "AVATAR_COST_HARD_DAILY_GENERATION_LIMIT",
                DEFAULT_HARD_DAILY_GENERATION_LIMIT,
            ),
            hard_monthly_generation_limit=_env_int(
                env,
                "AVATAR_COST_HARD_MONTHLY_GENERATION_LIMIT",
                DEFAULT_HARD_MONTHLY_GENERATION_LIMIT,
            ),
            kill_switch_enabled=_env_bool(env, "AVATAR_COST_KILL_SWITCH_ENABLED", False),
            enforce_budget=_env_bool(
                env,
                "AVATAR_COST_ENFORCE_BUDGET",
                _is_production_env(env),
            ),
        )


@dataclass(frozen=True)
class AvatarJobCost:
    duration_seconds: float
    usd: float
    pricing_version: str
    breakdown: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "durationSeconds": self.duration_seconds,
            "usd": self.usd,
            "pricingVersion": self.pricing_version,
            "breakdown": dict(self.breakdown),
        }


@dataclass(frozen=True)
class AvatarBatchCost:
    job_count: int
    candidate_count: int
    total_cost: AvatarJobCost
    unbatched_cost: AvatarJobCost
    savings_usd: float
    savings_ratio: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jobCount": self.job_count,
            "candidateCount": self.candidate_count,
            "totalCost": self.total_cost.to_dict(),
            "unbatchedCost": self.unbatched_cost.to_dict(),
            "savingsUsd": self.savings_usd,
            "savingsRatio": self.savings_ratio,
        }


@dataclass(frozen=True)
class AvatarCostAggregate:
    generated_count: int
    candidate_count: int
    total_usd: float
    daily_count: int
    daily_usd: float
    monthly_count: int
    monthly_usd: float
    pricing_version: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generatedCount": self.generated_count,
            "candidateCount": self.candidate_count,
            "totalUsd": self.total_usd,
            "dailyCount": self.daily_count,
            "dailyUsd": self.daily_usd,
            "monthlyCount": self.monthly_count,
            "monthlyUsd": self.monthly_usd,
            "pricingVersion": self.pricing_version,
        }


@dataclass(frozen=True)
class AvatarCostGuardResult:
    allowed: bool
    reason: str = ""
    aggregate: AvatarCostAggregate = field(default_factory=lambda: AvatarCostAggregate(0, 0, 0.0, 0, 0.0, 0, 0.0, "unset"))
    alerts: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "aggregate": self.aggregate.to_dict(),
            "alerts": [dict(alert) for alert in self.alerts],
        }


def estimate_job_cost(
    *,
    duration_seconds: float,
    config: Optional[AvatarCostConfig] = None,
) -> AvatarJobCost:
    config = config or AvatarCostConfig.from_env()
    seconds = max(0.0, float(duration_seconds))
    gpu_multiplier = 2.0 if config.gpu_zonal_redundancy else 1.0
    gpu_usd = seconds * config.gpu_usd_per_second * gpu_multiplier
    cpu_usd = seconds * config.vcpu * config.cpu_usd_per_vcpu_second
    memory_usd = seconds * config.memory_gib * config.memory_usd_per_gib_second
    total = _round_money(gpu_usd + cpu_usd + memory_usd)
    return AvatarJobCost(
        duration_seconds=_round_seconds(seconds),
        usd=total,
        pricing_version=config.pricing_version,
        breakdown={
            "gpuUsd": _round_money(gpu_usd),
            "cpuUsd": _round_money(cpu_usd),
            "memoryUsd": _round_money(memory_usd),
            "gpuZonalRedundancy": bool(config.gpu_zonal_redundancy),
            "vcpu": config.vcpu,
            "memoryGib": config.memory_gib,
        },
    )


def estimate_batch_cost(
    jobs: Iterable[Mapping[str, Any]],
    *,
    duration_seconds: float,
    config: Optional[AvatarCostConfig] = None,
) -> AvatarBatchCost:
    config = config or AvatarCostConfig.from_env()
    job_list = [dict(job) for job in jobs]
    total_cost = estimate_job_cost(duration_seconds=duration_seconds, config=config)
    unbatched_seconds = sum(_duration_seconds(job) or float(duration_seconds) for job in job_list)
    unbatched_cost = estimate_job_cost(duration_seconds=unbatched_seconds, config=config)
    savings = max(0.0, unbatched_cost.usd - total_cost.usd)
    ratio = (savings / unbatched_cost.usd) if unbatched_cost.usd > 0 else 0.0
    return AvatarBatchCost(
        job_count=len(job_list),
        candidate_count=sum(_candidate_count(job) for job in job_list),
        total_cost=total_cost,
        unbatched_cost=unbatched_cost,
        savings_usd=_round_money(savings),
        savings_ratio=round(ratio, 6),
    )


def build_job_cost_document(
    *,
    duration_seconds: float,
    config: Optional[AvatarCostConfig] = None,
    estimated_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    cost = estimate_job_cost(duration_seconds=duration_seconds, config=config)
    document = cost.to_dict()
    if estimated_at is not None:
        document["estimatedAt"] = estimated_at
    return {
        "costEstimateUsd": cost.usd,
        "costEstimate": document,
    }


def build_batch_cost_document(
    jobs: Iterable[Mapping[str, Any]],
    *,
    duration_seconds: float,
    config: Optional[AvatarCostConfig] = None,
    estimated_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    batch = estimate_batch_cost(jobs, duration_seconds=duration_seconds, config=config)
    document = batch.to_dict()
    document["pricingVersion"] = batch.total_cost.pricing_version
    if estimated_at is not None:
        document["estimatedAt"] = estimated_at
    return {
        "batchCostEstimateUsd": batch.total_cost.usd,
        "batchCostEstimate": document,
    }


def aggregate_avatar_job_costs(
    jobs: Iterable[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
    config: Optional[AvatarCostConfig] = None,
    report_date: Optional[date] = None,
    report_month: Optional[Tuple[int, int]] = None,
) -> AvatarCostAggregate:
    config = config or AvatarCostConfig.from_env()
    current = _normalize_datetime(now or datetime.now(tz=timezone.utc))
    day_start, day_end = _day_bounds(report_date or current.date())
    month_start, month_end = _month_bounds(report_month or (current.year, current.month))

    generated_count = 0
    candidate_count = 0
    total_usd = 0.0
    daily_count = 0
    daily_usd = 0.0
    monthly_count = 0
    monthly_usd = 0.0

    for job in jobs:
        if not _is_generated_job(job):
            continue
        created_at = _job_timestamp(job)
        cost_usd = _job_cost_usd(job, config=config)
        generated_count += 1
        candidate_count += _candidate_count(job)
        total_usd += cost_usd
        if created_at is not None and day_start <= created_at < day_end:
            daily_count += 1
            daily_usd += cost_usd
        if created_at is not None and month_start <= created_at < month_end:
            monthly_count += 1
            monthly_usd += cost_usd

    return AvatarCostAggregate(
        generated_count=generated_count,
        candidate_count=candidate_count,
        total_usd=_round_money(total_usd),
        daily_count=daily_count,
        daily_usd=_round_money(daily_usd),
        monthly_count=monthly_count,
        monthly_usd=_round_money(monthly_usd),
        pricing_version=config.pricing_version,
    )


def evaluate_cost_guard(
    firestore_client: Any,
    *,
    now: Optional[datetime] = None,
    config: Optional[AvatarCostConfig] = None,
) -> AvatarCostGuardResult:
    config = config or AvatarCostConfig.from_env()
    if config.kill_switch_enabled:
        return AvatarCostGuardResult(
            allowed=False,
            reason="cost_kill_switch_enabled",
            aggregate=AvatarCostAggregate(0, 0, 0.0, 0, 0.0, 0, 0.0, config.pricing_version),
        )

    aggregate = aggregate_avatar_job_costs(_stream_avatar_jobs(firestore_client), now=now, config=config)
    alerts = build_cost_alerts(aggregate, config=config)
    if config.hard_daily_generation_limit > 0 and aggregate.daily_count >= config.hard_daily_generation_limit:
        return AvatarCostGuardResult(
            allowed=False,
            reason="daily_generation_quota_exceeded",
            aggregate=aggregate,
            alerts=alerts,
        )
    if config.hard_monthly_generation_limit > 0 and aggregate.monthly_count >= config.hard_monthly_generation_limit:
        return AvatarCostGuardResult(
            allowed=False,
            reason="monthly_generation_quota_exceeded",
            aggregate=aggregate,
            alerts=alerts,
        )
    if config.enforce_budget:
        for alert in alerts:
            if alert.get("severity") == "error":
                return AvatarCostGuardResult(
                    allowed=False,
                    reason=str(alert.get("reason") or "budget_exceeded"),
                    aggregate=aggregate,
                    alerts=alerts,
                )
    return AvatarCostGuardResult(allowed=True, aggregate=aggregate, alerts=alerts)


def build_cost_alerts(
    aggregate: AvatarCostAggregate,
    *,
    config: AvatarCostConfig,
) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    if config.daily_alert_usd > 0 and aggregate.daily_usd >= config.daily_alert_usd:
        alerts.append(
            {
                "severity": "error" if config.enforce_budget else "warning",
                "metric": "dailyCostUsd",
                "value": aggregate.daily_usd,
                "limit": config.daily_alert_usd,
                "reason": "daily_budget_exceeded",
            }
        )
    if config.monthly_alert_usd > 0 and aggregate.monthly_usd >= config.monthly_alert_usd:
        alerts.append(
            {
                "severity": "error" if config.enforce_budget else "warning",
                "metric": "monthlyCostUsd",
                "value": aggregate.monthly_usd,
                "limit": config.monthly_alert_usd,
                "reason": "monthly_budget_exceeded",
            }
        )
    return alerts


def build_default_scenario_report(
    *,
    config: Optional[AvatarCostConfig] = None,
    users: int = DEFAULT_SCENARIO_USERS,
    candidates_per_user: int = DEFAULT_SCENARIO_CANDIDATES_PER_USER,
    seconds_per_user: float = 120.0,
) -> Dict[str, Any]:
    config = config or AvatarCostConfig.from_env()
    users = max(0, int(users))
    candidates_per_user = max(1, int(candidates_per_user))
    total_seconds = users * max(0.0, float(seconds_per_user))
    cost = estimate_job_cost(duration_seconds=total_seconds, config=config)
    return {
        "users": users,
        "candidatesPerUser": candidates_per_user,
        "candidateCount": users * candidates_per_user,
        "secondsPerUser": _round_seconds(seconds_per_user),
        "totalDurationSeconds": _round_seconds(total_seconds),
        "estimatedCost": cost.to_dict(),
    }


def parse_report_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(value)


def parse_report_month(value: Optional[str]) -> Optional[Tuple[int, int]]:
    if not value:
        return None
    parsed = datetime.strptime(value, "%Y-%m")
    return parsed.year, parsed.month


def _stream_avatar_jobs(firestore_client: Any) -> List[Dict[str, Any]]:
    collection = firestore_client.collection("avatarJobs")
    return [_snapshot_to_dict(snapshot) for snapshot in collection.stream()]


def _snapshot_to_dict(snapshot: Any) -> Dict[str, Any]:
    data = snapshot.to_dict() if hasattr(snapshot, "to_dict") else {}
    if not isinstance(data, Mapping):
        data = {}
    doc = dict(data)
    doc_id = getattr(snapshot, "id", None)
    if doc_id and "jobId" not in doc:
        doc["jobId"] = str(doc_id)
    return doc


def _job_cost_usd(job: Mapping[str, Any], *, config: AvatarCostConfig) -> float:
    for key in ("costEstimateUsd", "estimatedUsd", "generationCostUsd", "costUsd"):
        parsed = _optional_float(job.get(key))
        if parsed is not None:
            return _round_money(parsed)
    cost = job.get("cost")
    if isinstance(cost, Mapping):
        for key in ("estimatedUsd", "costEstimateUsd", "generationCostUsd", "costUsd"):
            parsed = _optional_float(cost.get(key))
            if parsed is not None:
                return _round_money(parsed)
    processing = job.get("processing")
    if isinstance(processing, Mapping):
        for key in ("costEstimateUsd", "estimatedUsd", "generationCostUsd", "costUsd"):
            parsed = _optional_float(processing.get(key))
            if parsed is not None:
                return _round_money(parsed)
    duration = _duration_seconds(job)
    return estimate_job_cost(duration_seconds=duration or 0.0, config=config).usd


def _duration_seconds(job: Mapping[str, Any]) -> Optional[float]:
    for key in ("durationSeconds", "totalWorkerSeconds", "total_worker_seconds", "runtimeSeconds", "gpuSeconds"):
        parsed = _optional_float(job.get(key))
        if parsed is not None:
            return max(0.0, parsed)
    cost = job.get("cost")
    if isinstance(cost, Mapping):
        for key in ("totalWorkerSeconds", "total_worker_seconds", "durationSeconds", "runtimeSeconds", "gpuSeconds"):
            parsed = _optional_float(cost.get(key))
            if parsed is not None:
                return max(0.0, parsed)
        seconds_by_stage = cost.get("secondsByStage")
        if isinstance(seconds_by_stage, Mapping):
            for key in ("total_worker_seconds", "totalWorkerSeconds", "total_seconds", "total"):
                parsed = _optional_float(seconds_by_stage.get(key))
                if parsed is not None:
                    return max(0.0, parsed)
    processing = job.get("processing")
    if isinstance(processing, Mapping):
        for key in ("durationSeconds", "totalWorkerSeconds", "total_worker_seconds", "runtimeSeconds", "gpuSeconds"):
            parsed = _optional_float(processing.get(key))
            if parsed is not None:
                return max(0.0, parsed)
    started = _parse_datetime(_nested_get(job, "processing.startedAt") or job.get("startedAt"))
    finished = _parse_datetime(
        _nested_get(job, "processing.completedAt")
        or job.get("completedAt")
        or job.get("updatedAt")
    )
    if started is not None and finished is not None and finished >= started:
        return (finished - started).total_seconds()
    return None


def _is_generated_job(job: Mapping[str, Any]) -> bool:
    return str(job.get("status") or "").strip().lower() in GENERATED_STATUSES


def _candidate_count(job: Mapping[str, Any]) -> int:
    value = _optional_int(job.get("candidateCount"))
    return value if value is not None and value > 0 else DEFAULT_SCENARIO_CANDIDATES_PER_USER


def _job_timestamp(job: Mapping[str, Any]) -> Optional[datetime]:
    for key in ("completedAt", "updatedAt", "createdAt"):
        parsed = _parse_datetime(job.get(key))
        if parsed is not None:
            return parsed
    return None


def _nested_get(data: Mapping[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _day_bounds(value: date) -> Tuple[datetime, datetime]:
    start = datetime.combine(value, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def _month_bounds(value: Tuple[int, int]) -> Tuple[datetime, datetime]:
    year, month = value
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _normalize_datetime(value)
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number = number / 1000.0
        return datetime.fromtimestamp(number, tz=timezone.utc)
    if isinstance(value, Mapping):
        seconds = value.get("seconds") or value.get("_seconds")
        nanos = value.get("nanos") or value.get("_nanoseconds") or 0
        if seconds is None:
            return None
        return datetime.fromtimestamp(float(seconds) + float(nanos) / 1_000_000_000, tz=timezone.utc)
    if hasattr(value, "to_datetime"):
        return _normalize_datetime(value.to_datetime())
    if hasattr(value, "timestamp") and not isinstance(value, str):
        return datetime.fromtimestamp(value.timestamp(), tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        return _normalize_datetime(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _optional_float(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _env_text(env: Mapping[str, str], name: str, fallback: str) -> str:
    value = str(env.get(name, "") or "").strip()
    return value if value else fallback


def _env_float(env: Mapping[str, str], name: str, fallback: float) -> float:
    parsed = _optional_float(env.get(name))
    return max(0.0, parsed) if parsed is not None else fallback


def _env_int(env: Mapping[str, str], name: str, fallback: int) -> int:
    parsed = _optional_int(env.get(name))
    return max(0, parsed) if parsed is not None else fallback


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


def _is_production_env(env: Mapping[str, str]) -> bool:
    environment = str(env.get("ENVIRONMENT", "") or "").strip().lower()
    node_env = str(env.get("NODE_ENV", "") or "").strip().lower()
    return environment in {"production", "prod", "production_bridge"} or node_env == "production"


def _round_money(value: float) -> float:
    return round(float(value), 6)


def _round_seconds(value: float) -> float:
    return round(float(value), 3)
