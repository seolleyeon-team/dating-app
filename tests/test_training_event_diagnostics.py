"""학습 데이터가 비었을 때 어느 필터에서 비었는지 알 수 있어야 한다.

production 에서 SVD/KNN 이 매일 "No usable events after filtering known events
/ AI profiles." 만 남기고 죽었다. 그 메시지로는 다음 셋을 구분할 수 없다.

    - recEvents 자체가 없다
    - 이벤트 이름이 allowlist 와 어긋난다 (schema drift)
    - 상호작용이 전부 AI 취향 카드 대상이었다 (실제 원인이었다)

필터 로직 자체는 바꾸지 않는다. 진단만 붙인다.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "lib" / "ai_recommend_model"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from seolleyeon_rec_common_v3 import (  # noqa: E402
    DEFAULT_EVENT_WEIGHTS,
    DEFAULT_NEGATIVE_EVENTS,
    NoUsableTrainingEvents,
    PairBuildConfig,
    collapse_pair_events,
)


def _cfg(exclude_ai=True):
    return PairBuildConfig(
        event_weights=dict(DEFAULT_EVENT_WEIGHTS),
        negative_events=set(DEFAULT_NEGATIVE_EVENTS),
        strong_positive_events={"like"},
        half_life_days=30.0,
        max_weight_per_pair=10.0,
        allow_open_only_pairs=False,
        exclude_ai_items_from_training=exclude_ai,
    )


def _events(rows):
    return pd.DataFrame(
        [{"user_id": u, "item_id": i, "event": e, "ts": None} for u, i, e in rows]
    )


def test_all_ai_targets_reports_the_ai_stage():
    """production 에서 실제로 일어난 경우: like/nope 이 전부 AI 카드 대상."""
    df = _events(
        [
            ("1111111111", "male_3", "like"),
            ("1111111111", "female_7", "nope"),
            ("2222222222", "male_1", "like"),
        ]
    )

    with pytest.raises(NoUsableTrainingEvents) as excinfo:
        collapse_pair_events(df, _cfg())

    error = excinfo.value
    assert error.stages["normalized"] == 3
    assert error.stages["known_event"] == 3
    assert error.stages["non_ai_item"] == 0
    assert error.event_counts == {"like": 2, "nope": 1}
    # 메시지만 봐도 "AI 대상이라 비었다" 를 알 수 있어야 한다.
    assert "non_ai_item=0" in str(error)
    assert "known_event=3" in str(error)


def test_schema_drift_reports_the_known_event_stage():
    """이벤트 이름이 어긋나면 known_event 단계에서 0 이 된다."""
    df = _events(
        [
            ("1111111111", "2222222222", "profile_like"),
            ("1111111111", "3333333333", "swipe_right"),
        ]
    )

    with pytest.raises(NoUsableTrainingEvents) as excinfo:
        collapse_pair_events(df, _cfg())

    error = excinfo.value
    assert error.stages["known_event"] == 0
    # 어떤 이름이 들어왔는지 보여야 drift 를 알아챌 수 있다.
    assert error.event_counts == {"profile_like": 1, "swipe_right": 1}
    assert "profile_like" in str(error)


def test_impression_only_traffic_is_reported():
    """노출만 있고 선택이 없는 상태 (allowlist 밖)."""
    df = _events([("1111111111", "2222222222", "impression")] * 5)

    with pytest.raises(NoUsableTrainingEvents) as excinfo:
        collapse_pair_events(df, _cfg())

    assert excinfo.value.stages["known_event"] == 0
    assert excinfo.value.event_counts == {"impression": 5}


def test_human_interactions_still_train_normally():
    """사람 간 상호작용이 있으면 기존대로 동작한다 (필터를 약화하지 않았다)."""
    df = _events(
        [
            ("1111111111", "2222222222", "like"),
            ("1111111111", "3333333333", "nope"),
            ("2222222222", "1111111111", "like"),
        ]
    )

    pairs, negatives = collapse_pair_events(df, _cfg())

    assert len(pairs) == 2
    assert len(negatives) == 1


def test_ai_targets_are_still_excluded_when_humans_are_present():
    """AI 카드는 계속 제외된다 — 진단 추가가 정책을 바꾸지 않았다."""
    df = _events(
        [
            ("1111111111", "2222222222", "like"),
            ("1111111111", "male_3", "like"),
        ]
    )

    pairs, _negatives = collapse_pair_events(df, _cfg())

    assert len(pairs) == 1
    assert "male_3" not in set(pairs["item_id"])


def test_error_message_contains_no_user_identifiers():
    df = _events([("kakao-9998887776", "male_3", "like")])

    with pytest.raises(NoUsableTrainingEvents) as excinfo:
        collapse_pair_events(df, _cfg())

    message = str(excinfo.value)
    assert "kakao-9998887776" not in message
    assert "male_3" not in message


def test_error_is_still_a_valueerror_for_existing_callers():
    """기존 호출부의 except ValueError 를 깨지 않는다."""
    df = _events([("1111111111", "male_3", "like")])
    with pytest.raises(ValueError):
        collapse_pair_events(df, _cfg())
