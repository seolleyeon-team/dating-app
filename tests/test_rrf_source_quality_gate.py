"""§29 — RRF 소스 품질 게이트(min_sources_per_user=2)의 실제 동작.

인자 전달만이 아니라, 병합 결과가 게이트를 어떻게 통과/거부하는지 확인한다.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT, REPO_ROOT / "lib" / "ai_recommend_model"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from seolleyeon_rrf_export import (  # noqa: E402
    passes_source_quality_gate,
    rrf_merge,
)

SOURCE_NAMES = ["clip", "svd", "knn"]
SOURCE_WEIGHTS = {"clip": 1.0, "svd": 1.0, "knn": 1.0}


def _doc(uids):
    return {"items": [{"uid": uid, "rank": i + 1} for i, uid in enumerate(uids)]}


def _merge(source_docs):
    return rrf_merge(
        source_docs,
        source_names=SOURCE_NAMES,
        source_weights=SOURCE_WEIGHTS,
        rrf_k=60,
        max_items_per_source=400,
        max_rank_per_source=400,
        use_dynamic_confidence=False,
        min_source_confidence=0.0,
        min_effective_weight=0.0,
        topn=400,
    )


def test_svd_only_user_is_rejected_at_two():
    merged, meta = _merge({"svd": _doc(["u1", "u2", "u3"])})

    assert merged, "병합 자체는 성공한다"
    assert meta["usedSources"] == ["svd"]
    assert passes_source_quality_gate(meta, 2) is False
    # 게이트가 1이면 통과한다 — 즉 거부는 게이트 값 때문이지 병합 실패가 아니다.
    assert passes_source_quality_gate(meta, 1) is True


def test_clip_and_svd_user_passes_at_two():
    merged, meta = _merge(
        {"clip": _doc(["u1", "u2"]), "svd": _doc(["u2", "u3"])}
    )

    assert merged
    assert sorted(meta["usedSources"]) == ["clip", "svd"]
    assert passes_source_quality_gate(meta, 2) is True


def test_clip_only_user_is_also_rejected_at_two():
    """required_sources=clip 이어도 clip 하나만으로는 내보내지 않는다."""
    _, meta = _merge({"clip": _doc(["u1", "u2"])})

    assert meta["usedSources"] == ["clip"]
    assert passes_source_quality_gate(meta, 2) is False


def test_three_sources_pass():
    _, meta = _merge(
        {
            "clip": _doc(["u1"]),
            "svd": _doc(["u2"]),
            "knn": _doc(["u3"]),
        }
    )

    assert len(meta["usedSources"]) == 3
    assert passes_source_quality_gate(meta, 2) is True


def test_gate_is_independent_of_campus_life_zone_policy():
    """§30 — 품질 게이트 복원이 생활권 판정을 바꾸지 않는다.

    두 정책은 서로 다른 단계(소스 융합 vs 후보 자격)에서 동작한다.
    """
    import campus_life_zone_policy as policy

    _, meta = _merge({"clip": _doc(["u1"]), "svd": _doc(["u1"])})

    assert passes_source_quality_gate(meta, 2) is True
    # 생활권 판정은 소스 개수와 무관하게 동일하다.
    assert policy.has_compatible_campus_life_zone({"sinchon"}, {"sinchon"}) is True
    assert policy.has_compatible_campus_life_zone({"sinchon"}, {"songdo"}) is False
    assert policy.has_compatible_campus_life_zone({"sinchon"}, set()) is False
