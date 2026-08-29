"""모델 상태 문서에도 생활권 정책 provenance 가 남아야 한다.

SVD/KNN 이 학습 데이터 부족으로 건너뛴 날에도 그 문서는 "어떤 정책 세대에서
만들어졌는지" 를 말할 수 있어야 한다. 데이터가 없다는 것과 정책이 무엇이었는지는
서로 다른 정보이고, 활성화 이후의 검증은 provenance 없는 문서를 신뢰하지 않는다.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "lib" / "ai_recommend_model"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from recsys.jobs import model_status  # noqa: E402
from recsys.jobs.verify_job import (  # noqa: E402
    evaluate_policy_provenance,
    evaluate_verify_health,
)


class _Batch:
    def __init__(self, sink):
        self._sink = sink

    def set(self, ref, payload, merge=False):
        self._sink.append((ref, payload, merge))

    def commit(self):
        return None


class _FakeDb:
    """write_source_status 가 만드는 payload 만 들여다보는 stub."""

    def __init__(self):
        self.writes = []

    def batch(self):
        return _Batch(self.writes)

    def document(self, path):
        return path

    def collection(self, _name):
        return self

    def list_documents(self):
        return []


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()

    class _FirestoreModule:
        SERVER_TIMESTAMP = "<server-timestamp>"

        @staticmethod
        def Client(project=None, database=None):  # noqa: N802 - SDK 이름을 따른다
            return db

    monkeypatch.setattr(model_status, "firestore", _FirestoreModule)
    return db


def _write(fake_db, *, status, reason, provenance):
    return model_status.write_source_status(
        project="p",
        date_key="20260826",
        source="svd",
        status=status,
        reason=reason,
        user_ids=["u1", "u2"],
        policy_provenance=provenance,
    )


def test_skipped_status_records_off_provenance(fake_db):
    count = _write(
        fake_db,
        status="skipped",
        reason="insufficient_signal",
        provenance={"campusLifeZone": "off", "campusLifeZonePolicyVersion": 0},
    )

    assert count == 2
    for _ref, payload, _merge in fake_db.writes:
        assert payload["status"] == "skipped"
        assert payload["reason"] == "insufficient_signal"
        assert payload["policy"] == {
            "campusLifeZone": "off",
            "campusLifeZonePolicyVersion": 0,
        }


def test_skipped_status_records_enforced_provenance(fake_db):
    _write(
        fake_db,
        status="skipped",
        reason="insufficient_signal",
        provenance={"campusLifeZone": "enforced", "campusLifeZonePolicyVersion": 1},
    )

    for _ref, payload, _merge in fake_db.writes:
        assert payload["policy"]["campusLifeZone"] == "enforced"
        assert payload["policy"]["campusLifeZonePolicyVersion"] == 1


def test_provenance_is_optional_for_existing_callers(fake_db):
    model_status.write_source_status(
        project="p",
        date_key="20260826",
        source="knn",
        status="skipped",
        reason="insufficient_signal",
        user_ids=["u1"],
    )

    _ref, payload, _merge = fake_db.writes[0]
    assert "policy" not in payload


def test_data_scarcity_does_not_remove_the_policy_epoch(fake_db):
    """§35 — 데이터가 없다고 정책 기록을 생략하지 않는다."""
    _write(
        fake_db,
        status="skipped",
        reason="insufficient_signal",
        provenance={"campusLifeZone": "enforced", "campusLifeZonePolicyVersion": 2},
    )

    for _ref, payload, _merge in fake_db.writes:
        assert payload["topN"] == 0
        assert payload["items"] == []
        assert payload["policy"]["campusLifeZone"] == "enforced"


# ------------------------------------------------------------------- verify


def _health(provenance):
    return evaluate_verify_health(
        total_real_users=10,
        eligible_actors=4,
        candidate_pool=8,
        source_stats={
            name: {"ready": 4, "empty": 0, "skipped": 0, "missing": 0, "failed": 0}
            for name in ("clip", "svd", "knn", "rrf")
        },
        daily_stats={"ready": 4, "empty": 0, "skipped": 0, "missing": 0, "failed": 0},
        compatible_pairs=6,
        policy_provenance=provenance,
    )


def test_enforced_run_accepts_skipped_documents_with_enforced_provenance():
    """활성화 이후 학습 데이터가 없어도, provenance 가 맞으면 검증은 통과한다."""
    provenance = evaluate_policy_provenance(
        expected_state="enforced",
        observed_states={"enforced": 162},
    )

    assert provenance["campusLifeZonePolicyProvenanceHealthy"] is True
    assert _health(provenance)["fatal"] is False


def test_enforced_run_rejects_skipped_documents_written_while_off():
    """정책이 켜진 뒤에 off 로 기록된 산출물은 세대가 어긋난 것이다."""
    provenance = evaluate_policy_provenance(
        expected_state="enforced",
        observed_states={"enforced": 100, "off": 62},
    )

    assert provenance["campusLifeZonePolicyProvenanceHealthy"] is False
    assert _health(provenance)["fatal"] is True


def test_enforced_run_rejects_skipped_documents_without_provenance():
    provenance = evaluate_policy_provenance(
        expected_state="enforced",
        observed_states={"missing": 162},
    )

    assert provenance["campusLifeZonePolicyProvenanceHealthy"] is False


def test_preparation_run_accepts_off_skipped_documents():
    provenance = evaluate_policy_provenance(
        expected_state="off",
        observed_states={"off": 162},
    )

    assert provenance["campusLifeZonePolicyProvenanceHealthy"] is True
    assert _health(provenance)["fatal"] is False


def test_unknown_activation_never_writes_normal_output(monkeypatch):
    """§32 — UNKNOWN 을 off 로 적지 않는다. 배치가 아예 중단된다."""
    import campus_life_zone_policy as policy
    import recsys.main as main_module

    class _Args:
        project = "p"
        database = None

    def _boom(_db):
        raise policy.CampusLifeZoneActivationUnknown("deadline exceeded")

    monkeypatch.setattr(
        policy, "load_campus_life_zone_activation_with_version", _boom
    )
    monkeypatch.setattr(
        main_module,
        "AI_MODEL_DIR",
        str(ROOT / "lib" / "ai_recommend_model"),
        raising=False,
    )

    class _FirestoreModule:
        @staticmethod
        def Client(project=None, database=None):  # noqa: N802
            return object()

    import google.cloud

    monkeypatch.setattr(google.cloud, "firestore", _FirestoreModule, raising=False)

    with pytest.raises(policy.CampusLifeZoneActivationUnknown):
        main_module._campus_zone_policy_provenance(_Args())
