"""Firestore orchestration for the policy-safe daily recommendation feed."""

from __future__ import annotations

import os
import sys
from datetime import timedelta
from typing import Any, Mapping, Sequence

import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_AI_MODEL_DIR = os.environ.get(
    "AI_MODEL_DIR", os.path.join(_PROJECT_ROOT, "lib", "ai_recommend_model")
)
if _AI_MODEL_DIR not in sys.path:
    sys.path.insert(0, _AI_MODEL_DIR)

try:
    from google.cloud import firestore
except Exception:  # pragma: no cover - pure orchestration tests do not need SDK
    firestore = None

from seolleyeon_rec_common_v3 import (  # noqa: E402
    assert_policy_meta_coverage,
    build_mutual_block_index,
    build_policy_meta_from_user_docs,
    load_events_from_firestore,
    load_policy_meta_from_firestore,
    load_user_documents_from_firestore,
    parse_datekey_to_utc_range,
    resolve_mutual_block_index,
)
from campus_life_zone_policy import (  # noqa: E402
    ACTIVATION_ENFORCED,
    CampusLifeZoneActivationUnknown,
    load_campus_life_zone_activation_with_version,
)
from seolleyeon_recommendation_privacy import (  # noqa: E402
    RecommendationPrivacyPolicy,
    load_recommendation_privacy_policy,
)
from recsys.jobs.daily_recommender import (  # noqa: E402
    DailySelectionConfig,
    select_daily_items,
)


def _is_policy_eligible(meta: Mapping[str, Any]) -> bool:
    return bool(
        meta.get("isActive") is True
        and meta.get("isVerified") is True
        and meta.get("isProfileComplete") is True
    )


def _rrf_status_and_items(value: Any) -> tuple[str, list[dict[str, Any]], str]:
    if isinstance(value, list):
        return "ready", [dict(item) for item in value if isinstance(item, Mapping)], ""
    if not isinstance(value, Mapping):
        return "missing", [], "missing_rrf_source"
    status = str(value.get("status") or "missing")
    items = value.get("items")
    normalized_items = [
        dict(item) for item in items
        if isinstance(item, Mapping)
    ] if isinstance(items, list) else []
    if status == "ready" and normalized_items:
        return "ready", normalized_items, ""
    if status in {"skipped", "failed"}:
        return status, [], str(value.get("reason") or f"rrf_{status}")
    if status == "empty":
        return "empty", [], str(value.get("reason") or "rrf_empty")
    return "missing", [], "missing_rrf_source"


def _eligible_actor_ids(
    policy_meta: Mapping[str, Mapping[str, Any]],
    display_status: Mapping[str, Mapping[str, Any]],
    signal_actor_ids: set[str],
) -> list[str]:
    eligible: list[str] = []
    for uid, meta in policy_meta.items():
        uid = str(uid)
        if not _is_policy_eligible(meta):
            continue
        display_ready = display_status.get(uid, {}).get("displayReady") is True
        if display_ready or uid in signal_actor_ids:
            eligible.append(uid)
    return sorted(eligible)


def _display_ready_candidate_items(
    items: Sequence[Mapping[str, Any]],
    display_status: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    ready: list[dict[str, Any]] = []
    skipped = 0
    for item in items:
        uid = str(item.get("uid") or "").strip()
        if not uid or display_status.get(uid, {}).get("displayReady") is not True:
            skipped += 1
            continue
        ready.append(dict(item))
    return ready, skipped


def _campus_zone_policy_state(cfg: DailySelectionConfig) -> str:
    """추천 문서에 기록할 생활권 정책 상태.

    클라이언트가 activation 을 독립 판단하지 않도록 서버가 문서에 남긴다.
    """
    return ACTIVATION_ENFORCED if cfg.campus_life_zone_enforced else "off"


def build_daily_documents(
    users: Mapping[str, Mapping[str, Any]],
    policy_meta: Mapping[str, Mapping[str, Any]],
    display_status: Mapping[str, Mapping[str, Any]],
    rrf_by_actor: Mapping[str, Any],
    *,
    date_key: str,
    privacy_policy: RecommendationPrivacyPolicy,
    signal_actor_ids: set[str] | None = None,
    blocked_by_actor: Mapping[str, set[str]] | None = None,
    nope_by_actor: Mapping[str, set[str]] | None = None,
    recent_exposure_by_actor: Mapping[str, set[str]] | None = None,
    config: DailySelectionConfig | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """Build one current-date daily doc for every eligible actor."""
    signal_actor_ids = {str(uid) for uid in (signal_actor_ids or set())}
    blocked_by_actor = blocked_by_actor or {}
    nope_by_actor = nope_by_actor or {}
    recent_exposure_by_actor = recent_exposure_by_actor or {}
    cfg = config or DailySelectionConfig()
    base_actor_ids = _eligible_actor_ids(
        policy_meta,
        display_status,
        signal_actor_ids,
    )
    actor_ids = [
        uid for uid in base_actor_ids if uid in privacy_policy.ready_user_ids
    ]
    candidate_pool = sum(
        1 for uid, status in display_status.items()
        if status.get("displayReady") is True
        and uid in policy_meta
        and uid in privacy_policy.ready_user_ids
    )

    docs: dict[str, dict[str, Any]] = {}
    coverage = {
        "eligibleActors": len(actor_ids),
        "ready": 0,
        "empty": 0,
        "skipped": 0,
        "missing": 0,
        "compatiblePairs": 0,
        "candidatePool": candidate_pool,
        "privacyIneligibleActors": len(base_actor_ids) - len(actor_ids),
    }

    # A same-date rerun must overwrite an older ready daily document after the
    # viewer revokes consent or privacy reconciliation becomes incomplete.
    for actor_uid in sorted(set(base_actor_ids) - set(actor_ids)):
        docs[actor_uid] = {
            "status": "skipped",
            "reason": "viewer_privacy_not_ready",
            "dateKey": date_key,
            "actorUid": actor_uid,
            "eligibleActor": False,
            "items": [],
            "topN": 0,
            "algorithmVersion": f"daily_v1_{date_key}",
            "policy": {"campusLifeZone": _campus_zone_policy_state(cfg)},
            "selection": {"inputCount": 0, "eligibleCount": 0, "rejected": {}},
        }

    for actor_uid in actor_ids:
        source_status, source_items, source_reason = _rrf_status_and_items(
            rrf_by_actor.get(actor_uid)
        )
        if source_status in {"missing", "skipped", "failed"}:
            doc = {
                "status": "skipped",
                "reason": source_reason or "missing_rrf_source",
                "dateKey": date_key,
                "actorUid": actor_uid,
                "eligibleActor": True,
                "items": [],
                "topN": 0,
                "algorithmVersion": f"daily_v1_{date_key}",
                "policy": {"campusLifeZone": _campus_zone_policy_state(cfg)},
                "selection": {"inputCount": 0, "eligibleCount": 0, "rejected": {}},
            }
            coverage["skipped"] += 1
            docs[actor_uid] = doc
            continue

        privacy_filtered_items = privacy_policy.filter_items(
            actor_uid,
            source_items,
        )
        privacy_skipped = max(0, len(source_items) - len(privacy_filtered_items))

        candidate_items, display_skipped = _display_ready_candidate_items(
            privacy_filtered_items,
            display_status,
        )
        selection = select_daily_items(
            actor_uid,
            candidate_items,
            policy_meta,
            date_key=date_key,
            candidate_docs=users,
            blocked_by_actor=blocked_by_actor.get(actor_uid, set()),
            nope_by_actor=nope_by_actor.get(actor_uid, set()),
            recent_exposure_by_actor=recent_exposure_by_actor.get(actor_uid, set()),
            config=cfg,
        )
        rejected = dict(selection.get("selection", {}).get("rejected", {}))
        if display_skipped:
            rejected["missing_approved_avatar"] = (
                int(rejected.get("missing_approved_avatar", 0)) + display_skipped
            )
        if privacy_skipped:
            rejected["kakao_friend_or_privacy_not_ready"] = (
                int(rejected.get("kakao_friend_or_privacy_not_ready", 0))
                + privacy_skipped
            )
        selection["selection"]["rejected"] = rejected

        for item in selection["items"]:
            candidate_uid = str(item.get("uid") or "")
            approved_url = str(
                display_status.get(candidate_uid, {}).get("approvedAvatarUrl") or ""
            )
            if approved_url:
                item["approvedAvatarUrl"] = approved_url

        doc = {
            **selection,
            "dateKey": date_key,
            "actorUid": actor_uid,
            "eligibleActor": True,
            "source": "rrf",
            "sourceStatus": source_status,
            "policy": {"campusLifeZone": _campus_zone_policy_state(cfg)},
        }
        docs[actor_uid] = doc
        coverage[selection["status"]] += 1
        if selection["selection"].get("eligibleCount", 0) > 0:
            coverage["compatiblePairs"] += 1

    return docs, coverage


def _load_firestore_block_edges(db, *, blocks_collection: str = "blocks") -> list[tuple[str, str]]:
    owner_targets: dict[str, list[str]] = {}
    for owner_ref in db.collection(blocks_collection).list_documents():
        owner_targets[owner_ref.id] = [
            target_ref.id for target_ref in owner_ref.collection("targets").list_documents()
        ]
    from seolleyeon_rec_common_v3 import block_edges_from_owner_targets

    return block_edges_from_owner_targets(owner_targets)


def _event_indexes(
    df: pd.DataFrame,
    *,
    date_key: str | None = None,
    recent_exposure_days: int = 7,
) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, set[str]], set[str]]:
    if df is None or df.empty:
        return {}, {}, {}, set()
    normalized = df.copy()
    for column in ("user_id", "item_id", "event"):
        normalized[column] = normalized[column].astype(str)
    blocks = build_mutual_block_index(normalized)
    nopes: dict[str, set[str]] = {}
    exposure: dict[str, set[str]] = {}
    signal_actors: set[str] = set()
    if date_key:
        _start_of_day_utc, end_utc = parse_datekey_to_utc_range(date_key)
        exposure_start = end_utc - timedelta(days=int(recent_exposure_days))
    else:
        exposure_start = None
        end_utc = None

    for row in normalized.itertuples(index=False):
        actor = str(getattr(row, "user_id"))
        target = str(getattr(row, "item_id"))
        event = str(getattr(row, "event"))
        if event == "nope":
            nopes.setdefault(actor, set()).add(target)
        if event in {"impression", "open", "detail_open", "profile_view", "view"}:
            event_ts = getattr(row, "ts", pd.NaT)
            is_recent = True
            if exposure_start is not None and end_utc is not None and pd.notna(event_ts):
                event_ts = pd.Timestamp(event_ts).to_pydatetime()
                is_recent = exposure_start <= event_ts < end_utc
            if is_recent:
                exposure.setdefault(actor, set()).add(target)
        if target.startswith(("female_", "male_")) and event in {
            "like", "nope", "match_created", "chat_first_message"
        }:
            signal_actors.add(actor)
    return blocks, nopes, exposure, signal_actors


def _write_daily_documents(db, date_key: str, docs: Mapping[str, Mapping[str, Any]]) -> None:
    if not docs:
        return
    batch = db.batch()
    pending = 0
    for uid, document in docs.items():
        payload = dict(document)
        payload["generatedAt"] = firestore.SERVER_TIMESTAMP
        ref = db.document(f"dailyRecs/{uid}/days/{date_key}")
        batch.set(ref, payload, merge=True)
        pending += 1
        if pending >= 400:
            batch.commit()
            batch = db.batch()
            pending = 0
    if pending:
        batch.commit()


def run_daily(
    *,
    project: str,
    date_key: str,
    database: str | None = None,
    users_collection: str = "users",
    profile_index_collection: str = "profileIndex",
    events_collection: str = "recEvents",
    lookback_days: int = 120,
    logger=None,
) -> dict[str, Any]:
    """Load current RRF docs, build daily docs, and persist them."""
    if firestore is None:
        raise RuntimeError("google-cloud-firestore is not installed")
    db = firestore.Client(project=project, database=database)
    privacy_policy = load_recommendation_privacy_policy(db)
    users = load_user_documents_from_firestore(
        project,
        users_collection=users_collection,
        database=database,
    )
    policy_meta, meta_source = load_policy_meta_from_firestore(
        project,
        profile_index_collection=profile_index_collection,
        users_collection=users_collection,
        database=database,
    )
    assert_policy_meta_coverage(
        policy_meta,
        users.keys(),
        min_coverage=0.9,
        source=meta_source,
    )

    from seolleyeon_rec_common_v3 import load_avatar_display_status_from_docs

    display_status = load_avatar_display_status_from_docs(users)
    candidate_actor_ids = set(policy_meta)
    rrf_by_actor: dict[str, Any] = {}
    for uid in sorted(candidate_actor_ids):
        snap = db.document(
            f"modelRecs/{uid}/daily/{date_key}/sources/rrf"
        ).get()
        if snap.exists:
            rrf_by_actor[uid] = snap.to_dict() or {}

    _start_of_day_utc, end_utc = parse_datekey_to_utc_range(date_key)
    start_utc = end_utc - timedelta(days=int(lookback_days))
    events = load_events_from_firestore(
        project,
        collection=events_collection,
        start_time_utc=start_utc,
        end_time_utc=end_utc,
        database=database,
    )
    blocks, nopes, exposure, signal_actors = _event_indexes(
        events,
        date_key=date_key,
        recent_exposure_days=7,
    )
    firestore_edges = _load_firestore_block_edges(db)
    blocks = resolve_mutual_block_index(events, firestore_block_edges=firestore_edges)

    # 생활권 hard filter 의 rollout activation 상태 (Firestore config 문서).
    # 문서가 없으면 OFF — 준비 단계에서 기존 추천 동작을 유지한다.
    #
    # 조회 자체가 실패하면(UNKNOWN) 여기서 배치를 중단한다. 활성화 여부를
    # 모른 채 추천을 새로 쓰면, 이미 켜진 정책을 무시하고 cross-zone 후보를
    # 저장할 수 있다. 하루치 배치가 한 번 실패하는 편이 안전하다.
    try:
        campus_zone_state, campus_zone_policy_version = (
            load_campus_life_zone_activation_with_version(db)
        )
    except CampusLifeZoneActivationUnknown as error:
        if logger:
            logger.error(
                "Daily recommendation aborted: campus life zone activation unknown",
                extra={
                    "campusLifeZoneActivationState": "unknown",
                    "campusLifeZoneActivationReadFailure": True,
                },
            )
        raise
    campus_zone_enforced = campus_zone_state == ACTIVATION_ENFORCED

    docs, coverage = build_daily_documents(
        users,
        policy_meta,
        display_status,
        rrf_by_actor,
        date_key=date_key,
        privacy_policy=privacy_policy,
        signal_actor_ids=signal_actors,
        blocked_by_actor=blocks,
        nope_by_actor=nopes,
        recent_exposure_by_actor=exposure,
        config=DailySelectionConfig(
            campus_life_zone_enforced=campus_zone_enforced,
        ),
    )
    _write_daily_documents(db, date_key, docs)
    result = {
        **coverage,
        "dateKey": date_key,
        "policyMetaSource": meta_source,
        "campusLifeZoneFilterEnabled": campus_zone_enforced,
        "campusLifeZoneActivationState": campus_zone_state,
        "campusLifeZonePolicyVersion": campus_zone_policy_version,
        "campusLifeZoneActivationReadFailure": False,
        "users": len(users),
        "documentsWritten": len(docs),
    }
    if logger:
        logger.info("Daily recommendation result", extra=result)
    return result


__all__ = ["build_daily_documents", "run_daily"]
