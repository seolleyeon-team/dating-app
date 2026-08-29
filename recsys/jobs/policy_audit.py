"""Read-only policy provenance and pair-constraint diagnostics."""

from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import pandas as pd

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_AI_MODEL_DIR = os.environ.get(
    "AI_MODEL_DIR", os.path.join(_PROJECT_ROOT, "lib", "ai_recommend_model")
)
if _AI_MODEL_DIR not in sys.path:
    sys.path.insert(0, _AI_MODEL_DIR)

from campus_life_zone_policy import campus_life_zone_rejection  # noqa: E402


def _utc_timestamp(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        timestamp = pd.Timestamp(value)
    except Exception:
        return None
    if pd.isna(timestamp):
        return None
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _age(birth_year: Any, now_year: int) -> int | None:
    if isinstance(birth_year, bool):
        return None
    try:
        year = int(birth_year)
    except (TypeError, ValueError):
        return None
    return now_year - year + 1


def _policy_failures(
    actor_id: str,
    candidate_id: str,
    policy_meta: Mapping[str, Mapping[str, Any]],
    *,
    now: pd.Timestamp,
    active_within_days: int,
    manner_min: float,
    require_same_university: bool,
    reciprocal: bool,
    require_same_campus_life_zone: bool = True,
) -> list[str]:
    actor = policy_meta.get(actor_id)
    candidate = policy_meta.get(candidate_id)
    failures: list[str] = []

    if actor is None or candidate is None:
        return ["missing_meta"]

    if candidate.get("isActive") is not True:
        failures.append("inactive")
    if candidate.get("isVerified") is not True:
        failures.append("not_verified")
    if candidate.get("isProfileComplete") is not True:
        failures.append("profile_incomplete")
    try:
        manner = float(candidate.get("mannerScore", 36.5))
    except (TypeError, ValueError):
        manner = 36.5
    if manner < manner_min:
        failures.append("manner")

    last_active = _utc_timestamp(candidate.get("lastActiveAt"))
    if last_active is not None:
        age_days = (now - last_active).total_seconds() / (24 * 3600)
        if age_days > active_within_days:
            failures.append("inactive")

    # 생활권은 hard eligibility다. passes_policy 와 같은 조건을 여기서도
    # 재현해 감사 지표가 실제 추천 결과와 어긋나지 않게 한다.
    # 단 rollout activation 이 OFF 면 실제 추천도 거르지 않으므로 여기서도
    # 실패로 세지 않는다 (지표가 서빙과 어긋나면 진단 가치가 없다).
    if require_same_campus_life_zone:
        zone_rejection = campus_life_zone_rejection(actor, candidate)
        if zone_rejection is not None:
            failures.append(zone_rejection)

    if require_same_university:
        if not actor.get("universityId") or not candidate.get("universityId"):
            failures.append("school")
        elif actor["universityId"] != candidate["universityId"]:
            failures.append("school")

    actor_pref_gender = actor.get("prefGender", []) or []
    candidate_gender = candidate.get("gender")
    if actor_pref_gender and candidate_gender is not None and candidate_gender not in actor_pref_gender:
        failures.append("pref_gender")

    now_year = now.tz_convert("Asia/Seoul").year
    candidate_age = _age(candidate.get("birthYear"), now_year)
    if candidate_age is not None:
        if actor.get("prefAgeMin") is not None and candidate_age < int(actor["prefAgeMin"]):
            failures.append("age")
        if actor.get("prefAgeMax") is not None and candidate_age > int(actor["prefAgeMax"]):
            failures.append("age")

    if reciprocal:
        candidate_pref_gender = candidate.get("prefGender", []) or []
        actor_gender = actor.get("gender")
        if candidate_pref_gender and actor_gender is not None and actor_gender not in candidate_pref_gender:
            failures.append("reciprocal")

        actor_age = _age(actor.get("birthYear"), now_year)
        if actor_age is not None:
            if candidate.get("prefAgeMin") is not None and actor_age < int(candidate["prefAgeMin"]):
                failures.append("reciprocal")
            if candidate.get("prefAgeMax") is not None and actor_age > int(candidate["prefAgeMax"]):
                failures.append("reciprocal")

    return failures


def audit_policy_pairs(
    actor_ids: Sequence[str],
    candidate_ids: Sequence[str],
    policy_meta: Mapping[str, Mapping[str, Any]],
    *,
    now: pd.Timestamp | datetime | None = None,
    active_within_days: int = 14,
    manner_min: float = 33.0,
    require_same_university: bool = True,
    reciprocal: bool = True,
    exclude_same_gender: bool = True,
    blocked_by_actor: Mapping[str, set[str]] | None = None,
    nope_by_actor: Mapping[str, set[str]] | None = None,
    recent_exposure_by_actor: Mapping[str, set[str]] | None = None,
    require_same_campus_life_zone: bool = True,
) -> dict[str, Any]:
    """Audit first-failure and all-failure constraints without writing data."""
    timestamp = _utc_timestamp(now or datetime.now(timezone.utc))
    assert timestamp is not None
    first_failures: Counter[str] = Counter()
    all_failures: Counter[str] = Counter()
    unique_first_candidates: defaultdict[str, set[str]] = defaultdict(set)
    unique_candidates: defaultdict[str, set[str]] = defaultdict(set)
    compatible_pairs = 0
    pair_checks = 0

    blocked_by_actor = blocked_by_actor or {}
    nope_by_actor = nope_by_actor or {}
    recent_exposure_by_actor = recent_exposure_by_actor or {}

    for actor_id in actor_ids:
        actor_id = str(actor_id)
        for candidate_id in candidate_ids:
            candidate_id = str(candidate_id)
            pair_checks += 1
            failures: list[str] = []

            if actor_id == candidate_id:
                failures.append("self")
            else:
                if candidate_id in blocked_by_actor.get(actor_id, set()):
                    failures.append("blocked")
                if candidate_id in nope_by_actor.get(actor_id, set()):
                    failures.append("nope")
                if candidate_id in recent_exposure_by_actor.get(actor_id, set()):
                    failures.append("recent_exposure")
                actor_meta = policy_meta.get(actor_id)
                candidate_meta = policy_meta.get(candidate_id)
                if exclude_same_gender and actor_meta and candidate_meta:
                    if (
                        actor_meta.get("gender")
                        and candidate_meta.get("gender")
                        and actor_meta["gender"] == candidate_meta["gender"]
                    ):
                        failures.append("gender")
                failures.extend(
                    _policy_failures(
                        actor_id,
                        candidate_id,
                        policy_meta,
                        now=timestamp,
                        active_within_days=active_within_days,
                        manner_min=manner_min,
                        require_same_university=require_same_university,
                        reciprocal=reciprocal,
                        require_same_campus_life_zone=require_same_campus_life_zone,
                    )
                )

            deduped_failures = list(dict.fromkeys(failures))
            if not deduped_failures:
                compatible_pairs += 1
                continue

            first_failures[deduped_failures[0]] += 1
            unique_first_candidates[deduped_failures[0]].add(candidate_id)
            all_failures["|".join(sorted(deduped_failures))] += 1
            for reason in deduped_failures:
                unique_candidates[reason].add(candidate_id)

    return {
        "pairChecks": pair_checks,
        "compatiblePairs": compatible_pairs,
        "firstFailureHistogram": dict(sorted(first_failures.items())),
        "allFailureHistogram": dict(sorted(all_failures.items())),
        "uniqueCandidatesByFirstFailure": {
            reason: len(candidates)
            for reason, candidates in sorted(unique_first_candidates.items())
        },
        "uniqueCandidatesByFailure": {
            reason: len(candidates)
            for reason, candidates in sorted(unique_candidates.items())
        },
    }


__all__ = ["audit_policy_pairs"]
