"""Azure endpoint 별 provider quota 의 단일 authority.

runtime generation, calibration, zero-cost simulation 이 모두 이 모듈을 통해
RPM 을 해석한다. 이전에는 두 경로가 서로 다른 env 체인을 읽어 한쪽 설정이
다른 쪽에서 조용히 무시됐다(2026-09-05 확인).

endpoint 마다 (endpointId, rpmLimit) 를 선언한다. 지금은 단일 endpoint 만
배포돼 있지만, 값을 코드에 박지 않고 설정으로 선언하므로 multi-endpoint
라우터가 생겨도 같은 authority 를 그대로 쓸 수 있다.

선언 방법:
    AZURE_OPENAI_ENDPOINT_QUOTAS="kr-1=2,jp-1=6"
    AZURE_OPENAI_ENDPOINT_DEFAULT_RPM="2"
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping, Optional

DEFAULT_ENDPOINT_RPM_LIMIT = 2.0

ENV_ENDPOINT_QUOTAS = "AZURE_OPENAI_ENDPOINT_QUOTAS"
ENV_ENDPOINT_DEFAULT_RPM = "AZURE_OPENAI_ENDPOINT_DEFAULT_RPM"

# 기존 배포에 남아 있는 이름들. 모두 같은 authority 로 수렴시킨다.
LEGACY_RPM_ENV_ALIASES = (
    "AZURE_OPENAI_REQUESTS_PER_MINUTE",
    "AVATAR_AZURE_QUOTA_RPM",
    "AZURE_OPENAI_QUOTA_RPM",
    "AVATAR_PROVIDER_RPM",
)

DEFAULT_ENDPOINT_ID = "primary"


class AzureEndpointQuotaError(ValueError):
    """선언된 endpoint quota 를 넘거나 해석할 수 없는 설정."""


@dataclass(frozen=True)
class EndpointQuota:
    endpoint_id: str
    rpm_limit: float


def _env(env: Optional[Mapping[str, str]]) -> Mapping[str, str]:
    return os.environ if env is None else env


def _positive_float(raw: str, *, field: str) -> float:
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise AzureEndpointQuotaError(
            f"{field} must be a positive number, got {raw!r}"
        ) from exc
    if not value > 0 or value != value or value in (float("inf"),):
        raise AzureEndpointQuotaError(
            f"{field} must be a positive finite number, got {raw!r}"
        )
    return value


def declared_endpoint_quota(
    endpoint_id: str = DEFAULT_ENDPOINT_ID,
    *,
    env: Optional[Mapping[str, str]] = None,
) -> EndpointQuota:
    """해당 endpoint 에 대해 선언된 quota 를 돌려준다."""
    source = _env(env)
    raw_table = str(source.get(ENV_ENDPOINT_QUOTAS, "") or "").strip()
    for entry in raw_table.split(","):
        if "=" not in entry:
            continue
        name, _, value = entry.partition("=")
        if name.strip() == endpoint_id.strip():
            return EndpointQuota(
                endpoint_id=endpoint_id,
                rpm_limit=_positive_float(value, field=ENV_ENDPOINT_QUOTAS),
            )

    fallback = str(source.get(ENV_ENDPOINT_DEFAULT_RPM, "") or "").strip()
    if fallback:
        return EndpointQuota(
            endpoint_id=endpoint_id,
            rpm_limit=_positive_float(fallback, field=ENV_ENDPOINT_DEFAULT_RPM),
        )
    return EndpointQuota(
        endpoint_id=endpoint_id, rpm_limit=DEFAULT_ENDPOINT_RPM_LIMIT
    )


def resolve_endpoint_rpm(
    endpoint_id: str = DEFAULT_ENDPOINT_ID,
    *,
    requested: Optional[float] = None,
    env: Optional[Mapping[str, str]] = None,
) -> float:
    """요청 RPM 을 해석하고, 선언된 quota 를 넘으면 fail-closed 한다."""
    source = _env(env)
    quota = declared_endpoint_quota(endpoint_id, env=source)

    if requested is None:
        for alias in LEGACY_RPM_ENV_ALIASES:
            if alias in source and str(source.get(alias, "")).strip() != "":
                requested = _positive_float(source[alias], field=alias)
                break
            if alias in source:
                raise AzureEndpointQuotaError(f"{alias} must not be empty")

    if requested is None:
        return quota.rpm_limit

    value = _positive_float(requested, field="requested_rpm")
    if value > quota.rpm_limit:
        raise AzureEndpointQuotaError(
            f"requested {value:g} RPM exceeds the declared quota "
            f"{quota.rpm_limit:g} RPM for endpoint {quota.endpoint_id}"
        )
    return value
