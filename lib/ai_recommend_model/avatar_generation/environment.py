"""Shared environment classification for avatar runtime safety gates."""

from __future__ import annotations

import os
from typing import Mapping, Optional

ENVIRONMENT_ALIASES = ("AVATAR_ENVIRONMENT", "ENVIRONMENT", "APP_ENV")
PRODUCTION_LIKE_ENVIRONMENTS = frozenset(
    {"prod", "production", "production_bridge"}
)
LOCAL_OR_DEV_ENVIRONMENTS = frozenset(
    {"", "local", "dev", "development", "test"}
)


def configured_environment_names(
    environment: Optional[Mapping[str, str]] = None,
) -> tuple[str, ...]:
    values = environment if environment is not None else os.environ
    return tuple(
        value
        for name in ENVIRONMENT_ALIASES
        if (value := str(values.get(name, "")).strip().lower())
    )


def resolve_environment_name(
    environment: Optional[Mapping[str, str]] = None,
) -> str:
    """Return the first non-empty alias for display and bridge selection."""

    configured = configured_environment_names(environment)
    return configured[0] if configured else ""


def is_production_like_environment(
    environment: Optional[Mapping[str, str]] = None,
) -> bool:
    # Conflicting aliases fail closed: any production-like declaration wins.
    return any(
        value in PRODUCTION_LIKE_ENVIRONMENTS
        for value in configured_environment_names(environment)
    )


def is_local_or_dev_environment(
    environment: Optional[Mapping[str, str]] = None,
) -> bool:
    configured = configured_environment_names(environment)
    if not configured:
        return True
    return all(value in LOCAL_OR_DEV_ENVIRONMENTS for value in configured)


__all__ = [
    "ENVIRONMENT_ALIASES",
    "configured_environment_names",
    "LOCAL_OR_DEV_ENVIRONMENTS",
    "PRODUCTION_LIKE_ENVIRONMENTS",
    "is_local_or_dev_environment",
    "is_production_like_environment",
    "resolve_environment_name",
]
