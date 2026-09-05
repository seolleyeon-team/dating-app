"""Endpoint 별 quota 를 단일 authority 로 고정한다.

runtime generation / calibration / simulation 이 서로 다른 env 체인을 읽어
서로를 무시하던 문제(2026-09-05 확인)를 막는다.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.model_adapters.azure_endpoint_quota import (  # noqa: E402
    DEFAULT_ENDPOINT_RPM_LIMIT,
    AzureEndpointQuotaError,
    declared_endpoint_quota,
    resolve_endpoint_rpm,
)


def test_default_declared_quota_is_the_verified_two_rpm():
    quota = declared_endpoint_quota("primary", env={})
    assert quota.endpoint_id == "primary"
    assert quota.rpm_limit == DEFAULT_ENDPOINT_RPM_LIMIT == 2.0


def test_quota_is_declared_per_endpoint_not_globally():
    env = {"AZURE_OPENAI_ENDPOINT_QUOTAS": "kr-1=2, jp-1=6 ,us-1=10"}
    assert declared_endpoint_quota("kr-1", env=env).rpm_limit == 2.0
    assert declared_endpoint_quota("jp-1", env=env).rpm_limit == 6.0
    assert declared_endpoint_quota("us-1", env=env).rpm_limit == 10.0
    # 선언되지 않은 endpoint 는 기본값으로 떨어진다.
    assert declared_endpoint_quota("unknown", env=env).rpm_limit == 2.0


def test_every_legacy_env_alias_resolves_through_one_authority():
    for alias in (
        "AZURE_OPENAI_REQUESTS_PER_MINUTE",
        "AVATAR_AZURE_QUOTA_RPM",
        "AZURE_OPENAI_QUOTA_RPM",
        "AVATAR_PROVIDER_RPM",
    ):
        assert resolve_endpoint_rpm("primary", env={alias: "1"}) == 1.0


def test_requesting_more_than_the_declared_quota_fails_closed():
    with pytest.raises(AzureEndpointQuotaError, match="quota"):
        resolve_endpoint_rpm("primary", requested=2.01, env={})

    env = {"AZURE_OPENAI_ENDPOINT_QUOTAS": "jp-1=6"}
    assert resolve_endpoint_rpm("jp-1", requested=6.0, env=env) == 6.0
    with pytest.raises(AzureEndpointQuotaError):
        resolve_endpoint_rpm("jp-1", requested=6.5, env=env)


def test_explicit_request_beats_env_aliases():
    env = {"AVATAR_AZURE_QUOTA_RPM": "2"}
    assert resolve_endpoint_rpm("primary", requested=1.0, env=env) == 1.0


def test_non_positive_and_unparsable_values_fail_closed():
    for bad in ("0", "-1", "abc", ""):
        with pytest.raises(AzureEndpointQuotaError):
            resolve_endpoint_rpm("primary", env={"AVATAR_PROVIDER_RPM": bad})
