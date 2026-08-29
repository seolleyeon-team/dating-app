"""Verify pipeline results in Firestore.

Checks modelRecs/{uid}/daily/{dateKey}/sources/{algo} for each source
and reports coverage, item counts, and health status.
"""
from __future__ import annotations

import time
from typing import Optional

try:
    from google.cloud import firestore
except Exception:  # pragma: no cover - pure health tests do not need the SDK
    firestore = None


def build_policy_readiness_metrics(
    *,
    total_real_users: int,
    policy_meta: dict[str, dict],
    display_status: dict[str, dict],
    compatible_pairs: int,
) -> dict:
    """Return aggregate policy/media readiness diagnostics for verification."""
    total = int(total_real_users)
    coverage = (len(policy_meta) / total * 100.0) if total else 100.0
    active_users = sum(1 for meta in policy_meta.values() if meta.get("isActive") is True)
    complete_users = sum(
        1 for meta in policy_meta.values() if meta.get("isProfileComplete") is True
    )
    policy_eligible = {
        uid
        for uid, meta in policy_meta.items()
        if (
            meta.get("isActive") is True
            and meta.get("isVerified") is True
            and meta.get("isProfileComplete") is True
        )
    }
    media_ready = {
        str(uid)
        for uid, status in display_status.items()
        if status.get("displayReady") is True
    }
    policy_and_media = policy_eligible & media_ready
    suspicious = bool(total and media_ready and not policy_eligible)
    return {
        "policyMetadataCoverage": round(coverage, 1),
        "activeUserCount": active_users,
        "profileCompleteUserCount": complete_users,
        "policyEligibleCandidateCount": len(policy_eligible),
        "mediaReadyCandidateCount": len(media_ready),
        "policyAndMediaReadyCandidateCount": len(policy_and_media),
        "compatiblePairCount": int(compatible_pairs),
        "suspiciousPolicyReadiness": suspicious,
        "suspiciousPolicyReadinessReason": (
            "approved_media_without_policy_eligible_candidate" if suspicious else ""
        ),
    }


def evaluate_policy_provenance(
    *,
    expected_state: str,
    observed_states: dict[str, int],
) -> dict:
    """생성된 추천 문서가 의도한 생활권 정책 상태로 만들어졌는지 확인한다.

    활성화했다고 믿고 있는데 산출물이 ``off`` 로 기록돼 있으면, 그 문서에는
    cross-zone 후보가 들어 있을 수 있다. 이것을 "성공" 으로 넘기면 안 된다.
    provenance 가 아예 없는 문서(legacy)도 활성화 이후에는 실패로 본다.
    """
    mismatched = {
        state: count
        for state, count in observed_states.items()
        if state != expected_state
        and count > 0
        # 아직 켜지 않은 단계에서는 정책 이전에 만들어진 문서(provenance 없음)를
        # 허용한다. 그 시점에는 생활권으로 거른 것이 없어 섞일 위험이 없다.
        # 활성화 이후에는 legacy 문서도 실패로 본다.
        and not (state == "missing" and expected_state != "enforced")
    }
    healthy = not mismatched
    return {
        "campusLifeZoneExpectedState": expected_state,
        "campusLifeZoneObservedStates": dict(observed_states),
        "campusLifeZonePolicyProvenanceHealthy": healthy,
        "campusLifeZonePolicyMismatchCounts": mismatched,
    }


def evaluate_verify_health(
    *,
    total_real_users: int,
    eligible_actors: int,
    candidate_pool: int,
    source_stats: dict[str, dict],
    daily_stats: dict[str, int],
    compatible_pairs: int | None = None,
    policy_provenance: dict | None = None,
) -> dict:
    """Evaluate readiness with explicit degraded-versus-fatal semantics.

    Data shortage is a successful, degraded run when the daily writer covered
    every eligible actor with an empty or skipped document. Missing current-day
    artifacts or partial actor coverage remain fatal.
    """
    reasons: list[str] = []
    fatal_reasons: list[str] = []

    if int(total_real_users) <= 0:
        return {
            "healthy": True,
            "degraded": True,
            "fatal": False,
            "reasons": ["no_real_users"],
            "fatalReasons": [],
            "sourceShortageExpected": False,
        }

    if int(eligible_actors) <= 0:
        return {
            "healthy": True,
            "degraded": True,
            "fatal": False,
            "reasons": ["no_eligible_actors"],
            "fatalReasons": [],
            "sourceShortageExpected": False,
        }

    daily_covered = (
        int(daily_stats.get("ready", 0))
        + int(daily_stats.get("empty", 0))
        + int(daily_stats.get("skipped", 0))
    )
    daily_missing = int(daily_stats.get("missing", 0))
    daily_failed = int(daily_stats.get("failed", 0))
    if daily_missing or daily_failed or daily_covered < int(eligible_actors):
        fatal_reasons.append("incomplete_daily_coverage")

    expected_shortage = True
    for source_name in ("svd", "knn"):
        stats = source_stats.get(source_name, {})
        if int(stats.get("failed", 0)) > 0 or int(stats.get("missing", 0)) > 0:
            expected_shortage = False
        if (
            int(stats.get("skipped", 0)) == 0
            and int(stats.get("empty", 0)) == 0
        ):
            expected_shortage = False

    candidate_shortage = int(candidate_pool) < 2
    if candidate_shortage:
        reasons.append("insufficient_candidate_pool")

    for source_name in ("clip", "svd", "knn", "rrf"):
        stats = source_stats.get(source_name, {})
        if int(stats.get("failed", 0)) > 0:
            fatal_reasons.append(f"failed_{source_name}_source")
        if int(stats.get("missing", 0)) > 0 and not candidate_shortage:
            fatal_reasons.append(f"missing_{source_name}_source")

    if compatible_pairs is not None and int(compatible_pairs) <= 0:
        reasons.append("no_compatible_pair")

    # 활성화했다고 믿는 정책과 산출물의 provenance 가 다르면 치명적이다.
    # (예: activation ON 인데 문서는 off 로 생성 → cross-zone 이 들어있을 수 있다)
    if policy_provenance is not None and not policy_provenance.get(
        "campusLifeZonePolicyProvenanceHealthy", True
    ):
        fatal_reasons.append("campus_life_zone_policy_provenance_mismatch")

    if fatal_reasons:
        return {
            "healthy": False,
            "degraded": False,
            "fatal": True,
            "reasons": sorted(set(reasons + fatal_reasons)),
            "fatalReasons": sorted(set(fatal_reasons)),
            "sourceShortageExpected": expected_shortage,
            **(policy_provenance or {}),
        }

    if not reasons and int(daily_stats.get("ready", 0)) <= 0:
        reasons.append("no_ready_daily_feed")

    return {
        "healthy": True,
        "degraded": bool(reasons),
        "fatal": False,
        "reasons": sorted(set(reasons)),
        "fatalReasons": [],
        "sourceShortageExpected": expected_shortage,
        **(policy_provenance or {}),
    }


def run_verify(
    *,
    project: str,
    date_key: str,
    database: Optional[str] = None,
    sources: Optional[list[str]] = None,
    logger=None,
) -> dict:
    """Check current-date model sources, daily docs, and actor coverage."""
    if sources is None:
        sources = ["clip", "svd", "knn", "rrf"]
    if firestore is None:
        raise RuntimeError("google-cloud-firestore is not installed")

    from datetime import timedelta
    from recsys.jobs.daily_job import _eligible_actor_ids, _event_indexes
    from recsys.jobs.policy_audit import audit_policy_pairs
    from campus_life_zone_policy import (
        ACTIVATION_ENFORCED,
        ACTIVATION_UNKNOWN,
        CampusLifeZoneActivationUnknown,
        load_campus_life_zone_activation,
    )
    from seolleyeon_rec_common_v3 import (
        load_avatar_display_status_from_docs,
        load_events_from_firestore,
        load_policy_meta_from_firestore,
        parse_datekey_to_utc_range,
    )

    t0 = time.time()
    db = firestore.Client(project=project, database=database)
    user_docs = {
        doc.id: (doc.to_dict() or {})
        for doc in db.collection("users").stream()
    }
    total_real_users = len(user_docs)
    if not total_real_users:
        health = evaluate_verify_health(
            total_real_users=0,
            eligible_actors=0,
            candidate_pool=0,
            source_stats={},
            daily_stats={},
        )
        return {
            "total_users": 0,
            "total_real_users": 0,
            "eligible_actors": 0,
            "date_key": date_key,
            "sources": {},
            "daily": {},
            **build_policy_readiness_metrics(
                total_real_users=0,
                policy_meta={},
                display_status={},
                compatible_pairs=0,
            ),
            "elapsed_s": round(time.time() - t0, 1),
            **health,
        }

    policy_meta, meta_source = load_policy_meta_from_firestore(
        project,
        users_collection="users",
        database=database,
    )
    display_status = load_avatar_display_status_from_docs(user_docs)
    _blocks: dict[str, set[str]] = {}
    _nopes: dict[str, set[str]] = {}
    _exposure: dict[str, set[str]] = {}
    try:
        _start_of_day_utc, end_utc = parse_datekey_to_utc_range(date_key)
        events = load_events_from_firestore(
            project,
            collection="recEvents",
            start_time_utc=end_utc - timedelta(days=120),
            end_time_utc=end_utc,
            database=database,
        )
        _blocks, _nopes, _exposure, signal_actor_ids = _event_indexes(events)
    except Exception as exc:
        signal_actor_ids = set()
        if logger:
            logger.warning(f"Verify could not load recEvents actor signals: {exc}")

    eligible_actor_ids = _eligible_actor_ids(
        policy_meta,
        display_status,
        signal_actor_ids,
    )
    candidate_pool = sum(
        1
        for uid, status in display_status.items()
        if status.get("displayReady") is True
        and uid in policy_meta
        and uid in user_docs
    )
    pair_candidate_ids = sorted(
        uid
        for uid, status in display_status.items()
        if status.get("displayReady") is True and uid in policy_meta
    )
    # 지금 의도한 생활권 정책 상태. 진단 지표와 provenance 검사가 같은 값을 쓴다.
    try:
        expected_state = load_campus_life_zone_activation(db)
    except CampusLifeZoneActivationUnknown:
        expected_state = ACTIVATION_UNKNOWN

    pair_audit = audit_policy_pairs(
        eligible_actor_ids,
        pair_candidate_ids,
        policy_meta,
        active_within_days=14,
        manner_min=33.0,
        require_same_university=True,
        reciprocal=True,
        exclude_same_gender=True,
        blocked_by_actor=_blocks,
        nope_by_actor=_nopes,
        recent_exposure_by_actor=_exposure,
        # OFF 동안에는 실제 추천도 생활권으로 거르지 않는다.
        require_same_campus_life_zone=expected_state == ACTIVATION_ENFORCED,
    )

    def read_status(path: str) -> tuple[str, int, dict]:
        try:
            snap = db.document(path).get()
        except Exception:
            return "missing", 0, {}
        if not snap.exists:
            return "missing", 0, {}
        data = snap.to_dict() or {}
        if data.get("dateKey") and str(data.get("dateKey")) != date_key:
            return "failed", 0, data
        items = data.get("items", [])
        n = len(items) if isinstance(items, list) else 0
        status = str(data.get("status") or "failed")
        if status == "ready" and n > 0:
            return "ready", n, data
        if status == "empty":
            return "empty", 0, data
        if status == "skipped":
            return "skipped", 0, data
        return "failed", 0, data

    def collect_stats(path_template: str, actor_ids: list[str]) -> tuple[dict, dict[str, dict]]:
        stats = {
            "ready": 0,
            "empty": 0,
            "skipped": 0,
            "missing": 0,
            "failed": 0,
            "total_items": 0,
            "avg_items": 0,
            "min_items": 0,
            "max_items": 0,
            "coverage_pct": 0.0,
        }
        details: dict[str, dict] = {}
        item_counts: list[int] = []
        for uid in actor_ids:
            status, count, data = read_status(path_template.format(uid=uid))
            stats[status] += 1
            stats["total_items"] += count
            details[uid] = {"status": status, "items": count, "data": data}
            if status == "ready":
                item_counts.append(count)
        if item_counts:
            stats["avg_items"] = round(sum(item_counts) / len(item_counts), 1)
            stats["min_items"] = min(item_counts)
            stats["max_items"] = max(item_counts)
        if actor_ids:
            stats["coverage_pct"] = round(
                (stats["ready"] / len(actor_ids)) * 100,
                1,
            )
        return stats, details

    source_stats: dict[str, dict] = {}
    source_details: dict[str, dict[str, dict]] = {}
    for source in sources:
        source_stats[source], source_details[source] = collect_stats(
            f"modelRecs/{{uid}}/daily/{date_key}/sources/{source}",
            eligible_actor_ids,
        )

    daily_stats, daily_details = collect_stats(
        f"dailyRecs/{{uid}}/days/{date_key}",
        eligible_actor_ids,
    )
    daily_compatible_actor_count = sum(
        1
        for detail in daily_details.values()
        if int((detail.get("data") or {}).get("selection", {}).get("eligibleCount", 0)) > 0
    )
    compatible_pairs = int(pair_audit["compatiblePairs"])

    # 산출물이 어떤 생활권 정책 상태로 만들어졌는지 집계한다.
    observed_states: dict[str, int] = {}
    for detail in daily_details.values():
        data = detail.get("data") or {}
        policy = data.get("policy")
        state = (
            policy.get("campusLifeZone")
            if isinstance(policy, dict) and isinstance(policy.get("campusLifeZone"), str)
            else "missing"
        )
        observed_states[state] = observed_states.get(state, 0) + 1
    for source_detail in source_details.values():
        for detail in source_detail.values():
            data = detail.get("data") or {}
            policy = data.get("policy")
            state = (
                policy.get("campusLifeZone")
                if isinstance(policy, dict)
                and isinstance(policy.get("campusLifeZone"), str)
                else "missing"
            )
            observed_states[state] = observed_states.get(state, 0) + 1
    policy_provenance = evaluate_policy_provenance(
        expected_state=expected_state,
        observed_states=observed_states,
    )

    health = evaluate_verify_health(
        total_real_users=total_real_users,
        eligible_actors=len(eligible_actor_ids),
        candidate_pool=candidate_pool,
        source_stats=source_stats,
        daily_stats={
            key: daily_stats[key]
            for key in ("ready", "empty", "skipped", "missing", "failed")
        },
        compatible_pairs=compatible_pairs,
        policy_provenance=policy_provenance,
    )
    readiness_metrics = build_policy_readiness_metrics(
        total_real_users=total_real_users,
        policy_meta=policy_meta,
        display_status=display_status,
        compatible_pairs=compatible_pairs,
    )
    elapsed = time.time() - t0
    result = {
        "total_users": total_real_users,
        "total_real_users": total_real_users,
        "eligible_actors": len(eligible_actor_ids),
        "candidate_pool": candidate_pool,
        "policy_meta_source": meta_source,
        "date_key": date_key,
        "sources": source_stats,
        "source_details": source_details,
        "daily": daily_stats,
        "daily_details": daily_details,
        "dailyCompatibleActorCount": daily_compatible_actor_count,
        "pairAudit": pair_audit,
        **readiness_metrics,
        "elapsed_s": round(elapsed, 1),
        **health,
    }
    if logger:
        logger.info(
            f"Verify complete in {elapsed:.1f}s. Healthy={result['healthy']} "
            f"degraded={result['degraded']} fatal={result['fatal']}",
            extra={"date_key": date_key, "result": result},
        )
    return result
