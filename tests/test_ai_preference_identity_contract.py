from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "lib" / "ai_recommend_model"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from seolleyeon_rec_common_v3 import (  # noqa: E402
    DEFAULT_EVENT_WEIGHTS,
    DEFAULT_NEGATIVE_EVENTS,
    DEFAULT_STRONG_POSITIVE_EVENTS,
    PairBuildConfig,
    build_interaction_matrix_from_pairs,
    canonicalize_recommendation_target_id,
    canonicalize_ai_profile_id,
    collapse_pair_events,
    is_ai_profile,
    normalize_events_df,
    parse_ai_profile_identity,
)
from seolleyeon_rrf_export import rrf_merge  # noqa: E402


def _pair_config(*, exclude_ai_items_from_training: bool) -> PairBuildConfig:
    return PairBuildConfig(
        event_weights=dict(DEFAULT_EVENT_WEIGHTS),
        negative_events=set(DEFAULT_NEGATIVE_EVENTS),
        strong_positive_events=set(DEFAULT_STRONG_POSITIVE_EVENTS),
        half_life_days=365.0,
        max_weight_per_pair=100.0,
        exclude_ai_items_from_training=exclude_ai_items_from_training,
    )


def _events(*rows: tuple[str, str, str]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["user_id", "item_id", "event"])


def test_ai_identity_parser_is_strict_and_preserves_zero_padding():
    assert parse_ai_profile_identity("male_007") == ("male", "007")
    assert parse_ai_profile_identity("female_123") == ("female", "123")
    assert canonicalize_ai_profile_id("male_007") == "male_007"
    assert is_ai_profile("male_007") is True
    assert is_ai_profile("male_007_face_card") is False

    with pytest.raises(ValueError):
        parse_ai_profile_identity("male_007_face_card")
    with pytest.raises(ValueError):
        parse_ai_profile_identity("male_abc")


def test_legacy_shot_targets_canonicalize_to_one_identity_target():
    assert (
        canonicalize_recommendation_target_id("male_007_face_card")
        == "male_007"
    )
    assert (
        canonicalize_recommendation_target_id("female_123_silhouette_card")
        == "female_123"
    )
    assert canonicalize_recommendation_target_id("kakao-user-1") == "kakao-user-1"

    normalized = normalize_events_df(
        _events(
            ("user-1", "male_007_face_card", "like"),
            ("user-1", "male_007_vibe_card", "like"),
            ("user-1", "male_007_silhouette_card", "like"),
        )
    )
    assert normalized["item_id"].tolist() == ["male_007", "male_007", "male_007"]


def test_collapse_keeps_one_identity_pair_and_applies_final_state():
    cfg = _pair_config(exclude_ai_items_from_training=False)
    pair_df, neg_df = collapse_pair_events(
        _events(
            ("user-1", "male_007_face_card", "like"),
            ("user-1", "male_007_vibe_card", "like"),
            ("user-1", "male_007_silhouette_card", "like"),
            ("user-1", "real-user-1", "like"),
        ),
        cfg,
    )

    ai_pairs = pair_df[pair_df["item_id"] == "male_007"]
    assert len(ai_pairs) == 1
    assert len(neg_df) == 0
    assert ai_pairs.iloc[0]["positive_events"] == ["like", "like", "like"]

    pair_df, neg_df = collapse_pair_events(
        _events(
            ("user-1", "male_007", "like"),
            ("user-1", "male_007", "nope"),
            ("user-1", "real-user-1", "like"),
        ),
        cfg,
    )
    assert "male_007" not in set(pair_df["item_id"])
    assert set(neg_df["item_id"]) == {"male_007"}

    pair_df, neg_df = collapse_pair_events(
        _events(
            ("user-1", "male_007", "nope"),
            ("user-1", "male_007", "like"),
            ("user-1", "real-user-1", "like"),
        ),
        cfg,
    )
    assert set(pair_df["item_id"]) == {"male_007", "real-user-1"}
    assert neg_df.empty


def test_default_training_contract_excludes_ai_and_matrix_has_one_identity_column():
    events = _events(
        ("user-1", "male_007_face_card", "like"),
        ("user-1", "male_007_vibe_card", "like"),
        ("user-1", "male_007_silhouette_card", "like"),
        ("user-1", "real-user-1", "like"),
    )

    pair_df, _ = collapse_pair_events(
        events,
        _pair_config(exclude_ai_items_from_training=True),
    )
    assert set(pair_df["item_id"]) == {"real-user-1"}

    pair_df, neg_df = collapse_pair_events(
        events,
        _pair_config(exclude_ai_items_from_training=False),
    )
    matrix, _user2idx, idx2item, _negative_by_user, _pairs = (
        build_interaction_matrix_from_pairs(pair_df, neg_df)
    )
    assert idx2item.count("male_007") == 1
    assert matrix.shape == (1, 2)


def test_rrf_never_exports_ai_identity_candidates():
    docs = {
        "clip": {
            "status": "ready",
            "items": [
                {"uid": "male_007_face_card", "rank": 1},
                {"uid": "kakao-user-1", "rank": 2},
            ],
        },
        "svd": {
            "status": "ready",
            "items": [
                {"uid": "female_123", "rank": 1},
                {"uid": "kakao-user-1", "rank": 2},
            ],
        },
    }
    merged, _meta = rrf_merge(
        docs,
        source_names=["clip", "svd"],
        source_weights={"clip": 1.0, "svd": 0.8},
        rrf_k=60,
        max_items_per_source=20,
        max_rank_per_source=20,
        use_dynamic_confidence=False,
        min_source_confidence=0.2,
        min_effective_weight=0.05,
        topn=20,
    )
    assert [item["uid"] for item in merged] == ["kakao-user-1"]


def test_active_entrypoint_dispatches_all_model_steps_to_v3():
    from recsys.main import MODEL_SCRIPT_NAMES

    assert MODEL_SCRIPT_NAMES == {
        "clip": "seolleyeon_clip_train_export_v3.py",
        "svd": "seolleyeon_svd_train_export_v3.py",
        "knn": "seolleyeon_knn_train_export_v3.py",
    }
