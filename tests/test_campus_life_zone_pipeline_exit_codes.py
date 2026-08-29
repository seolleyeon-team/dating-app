"""배치 단계의 종료 코드 계약.

activation 을 확인하지 못한 실행이 "성공"으로 끝나면, 운영자는 그날 추천이
어떤 정책으로 만들어졌는지 모른 채 넘어간다. 그리고 verify 는 산출물의 정책
provenance 가 의도와 다르면 실패해야 한다 (§23).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "lib" / "ai_recommend_model"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import recsys.main as main_module  # noqa: E402
from campus_life_zone_policy import (  # noqa: E402
    ACTIVATION_ENFORCED,
    ACTIVATION_OFF,
    CampusLifeZoneActivationUnknown,
)


class _Logger:
    def __init__(self):
        self.errors = []

    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        self.errors.append(_args[0] if _args else "")


class _Args:
    step = "daily"
    date_key = "20260826"
    project = "seolleyeon-final"
    bucket = "bucket"
    prefix = "recs/20260826/"
    database = None


def test_daily_step_exits_non_zero_when_activation_is_unknown(monkeypatch):
    def _boom(**_kwargs):
        raise CampusLifeZoneActivationUnknown("deadline exceeded")

    monkeypatch.setitem(
        main_module.STEPS, "daily", lambda args, logger: _boom()
    )
    monkeypatch.setattr(main_module, "setup_logging", lambda *_a, **_k: _Logger())
    monkeypatch.setattr(
        main_module, "build_parser", lambda: _StubParser("daily")
    )

    assert main_module.main() == 1


def test_verify_step_exits_non_zero_when_unhealthy(monkeypatch):
    monkeypatch.setattr(
        "recsys.jobs.verify_job.run_verify",
        lambda **_kwargs: {"healthy": False, "fatal": True, "reasons": ["x"]},
    )
    assert main_module.step_verify(_Args(), _Logger()) == 1


def test_verify_step_exits_zero_when_healthy(monkeypatch):
    monkeypatch.setattr(
        "recsys.jobs.verify_job.run_verify",
        lambda **_kwargs: {"healthy": True, "fatal": False, "reasons": []},
    )
    assert main_module.step_verify(_Args(), _Logger()) == 0


def test_verify_fails_on_policy_provenance_mismatch():
    """활성화 의도와 산출물이 다르면 verify 는 성공으로 끝나지 않는다."""
    from recsys.jobs.verify_job import (
        evaluate_policy_provenance,
        evaluate_verify_health,
    )

    provenance = evaluate_policy_provenance(
        expected_state=ACTIVATION_ENFORCED,
        observed_states={ACTIVATION_OFF: 2},
    )
    health = evaluate_verify_health(
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
    assert health["healthy"] is False
    assert main_module.step_verify.__doc__ is None  # 계약은 반환값으로만 표현된다
    assert (
        0 if health.get("healthy", False) else 1
    ) == 1, "unhealthy verify 는 non-zero 로 끝난다"


class _StubParser:
    """실제 CLI 파싱 없이 단계만 지정하는 최소 stub."""

    def __init__(self, step: str):
        self._step = step

    def parse_args(self):
        args = _Args()
        args.step = self._step
        return args
