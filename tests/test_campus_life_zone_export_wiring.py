"""1:1 소스 모델 export 가 생활권 정책을 activation 에 맞춰 적용하는지.

클라이언트 1:1 피드는 ``modelRecs/{uid}/daily/{date}/sources/{algo}`` 를 읽는다.
이 문서를 만드는 clip/svd/knn export 가 activation 과 무관하게 생활권을 항상
강제하면, 준비 단계(config 문서 없음 = OFF)에서도 생활권이 없는 기존 사용자가
후보에서 사라져 staged rollout 자체가 성립하지 않는다.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "lib" / "ai_recommend_model"
for path in (ROOT, MODEL_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

EXPORTS = {
    "clip": MODEL_DIR / "seolleyeon_clip_train_export_v3.py",
    "svd": MODEL_DIR / "seolleyeon_svd_train_export_v3.py",
    "knn": MODEL_DIR / "seolleyeon_knn_train_export_v3.py",
}


def _source(name: str) -> str:
    return EXPORTS[name].read_text(encoding="utf-8")


@pytest.mark.parametrize("algo", sorted(EXPORTS))
def test_passes_policy_receives_the_activation_state(algo):
    src = _source(algo)
    calls = re.findall(r"passes_policy\((?:[^()]|\([^()]*\))*\)", src)
    assert calls, f"{algo}: passes_policy 호출을 찾지 못했다"
    for call in calls:
        assert "require_same_campus_life_zone=campus_zone_enforced" in call, (
            f"{algo}: 생활권 강제 여부가 activation 과 연결돼 있지 않다. "
            "기본값(True)에 의존하면 준비 단계에서도 hard filter 가 걸린다."
        )


@pytest.mark.parametrize("algo", sorted(EXPORTS))
def test_activation_is_resolved_from_config_or_explicit_override(algo):
    src = _source(algo)
    assert "resolve_campus_life_zone_activation(" in src, algo
    assert "--enforce_campus_life_zone" in src, algo
    assert "--no_enforce_campus_life_zone" in src, algo


@pytest.mark.parametrize("algo", sorted(EXPORTS))
def test_exported_documents_record_policy_provenance(algo):
    src = _source(algo)
    assert "policy_provenance" in src, algo
    assert 'payload["policy"] = policy_provenance' in src, algo
    assert "campus_life_zone_policy_provenance(" in src, algo


def test_rrf_export_records_provenance_and_skips_stale_sources():
    src = (MODEL_DIR / "seolleyeon_rrf_export.py").read_text(encoding="utf-8")
    assert "load_campus_life_zone_activation_with_version" in src
    assert '"policy": policy_provenance' in src
    # 활성화 이후에는 off/legacy 소스 문서를 융합하지 않는다.
    assert "source_policy_state(raw) != ACTIVATION_ENFORCED" in src


def test_resolve_helper_prefers_explicit_override():
    from seolleyeon_rec_common_v3 import resolve_campus_life_zone_activation

    assert resolve_campus_life_zone_activation(True, "proj") == ("enforced", 0)
    assert resolve_campus_life_zone_activation(False, "proj") == ("off", 0)


def test_resolve_helper_propagates_unknown(monkeypatch):
    """config 를 읽어야 하는데 실패하면 예외가 올라가 배치가 멈춘다."""
    import seolleyeon_rec_common_v3 as common
    from campus_life_zone_policy import CampusLifeZoneActivationUnknown

    def _boom(_project, database=None):
        raise CampusLifeZoneActivationUnknown("deadline exceeded")

    monkeypatch.setattr(
        common, "load_campus_life_zone_activation_for_project", _boom
    )
    with pytest.raises(CampusLifeZoneActivationUnknown):
        common.resolve_campus_life_zone_activation(None, "proj")


def test_policy_provenance_payload_shape():
    from seolleyeon_rec_common_v3 import campus_life_zone_policy_provenance

    assert campus_life_zone_policy_provenance("enforced", 2) == {
        "campusLifeZone": "enforced",
        "campusLifeZonePolicyVersion": 2,
    }
    assert campus_life_zone_policy_provenance("off", 0) == {
        "campusLifeZone": "off",
        "campusLifeZonePolicyVersion": 0,
    }
