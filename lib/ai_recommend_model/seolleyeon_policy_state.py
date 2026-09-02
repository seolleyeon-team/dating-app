"""Canonical policy-state normalization shared by recommendation jobs.

The Flutter client treats onboarding completion and account availability as
separate concepts.  This module keeps that distinction explicit and exposes
only category-level provenance for audits and structured diagnostics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


_BLOCKED_ACCOUNT_STATUSES = {"blocked", "deleted", "suspended"}


def profile_completion_provenance(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize completion using the same precedence as the Flutter client."""
    explicit = doc.get("isProfileComplete")
    if isinstance(explicit, bool):
        return {
            "value": explicit,
            "source": "users.isProfileComplete",
            "reason": "explicit_true" if explicit else "explicit_false",
        }

    initial_setup = doc.get("initialSetupComplete")
    if isinstance(initial_setup, bool):
        return {
            "value": initial_setup,
            "source": "users.initialSetupComplete",
            "reason": "canonical_true" if initial_setup else "canonical_false",
        }

    return {
        "value": None,
        "source": "none",
        "reason": "missing_completion_fields",
    }


def account_active_provenance(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize account availability without using recency as ``isActive``."""
    # Operations staff can use chat but are never recommendation actors or
    # candidates.  This is intentionally before generic status/active flags:
    # provisioning an active staff account must not accidentally enter a batch.
    if str(doc.get("accountType") or "").strip().lower() == "operations":
        return {
            "value": False,
            "source": "users.accountType",
            "reason": "operations_account",
        }
    status_field = "status" if doc.get("status") is not None else "accountStatus"
    status = str(doc.get(status_field) or "").strip().lower()
    if status in _BLOCKED_ACCOUNT_STATUSES:
        return {
            "value": False,
            "source": f"users.{status_field}",
            "reason": "blocked_status",
        }

    if doc.get("isDeleted") is True:
        return {
            "value": False,
            "source": "users.isDeleted",
            "reason": "explicit_deleted",
        }
    if doc.get("isSuspended") is True:
        return {
            "value": False,
            "source": "users.isSuspended",
            "reason": "explicit_suspended",
        }

    explicit_active = doc.get("isActive")
    if isinstance(explicit_active, bool):
        return {
            "value": explicit_active,
            "source": "users.isActive",
            "reason": "explicit_true" if explicit_active else "explicit_false",
        }

    if status:
        return {
            "value": True,
            "source": f"users.{status_field}",
            "reason": "enabled_status",
        }

    return {
        "value": True,
        "source": "users.account_status",
        "reason": "no_blocking_status",
    }


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    to_datetime = getattr(value, "to_pydatetime", None)
    if callable(to_datetime):
        converted = to_datetime()
        if isinstance(converted, datetime):
            return converted
    return None


def activity_provenance(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve recency from fields written by the actual login/app paths.

    ``lastActiveAt`` remains the newest explicit/legacy source.  The current
    Kakao login path writes ``lastActivePlatformUpdatedAt`` on every login;
    ``lastLoginAt`` covers older account generations.  Onboarding/update
    timestamps are retained only as legacy fallbacks.
    """
    sources = (
        ("lastActiveAt", "users.lastActiveAt", "explicit_activity"),
        (
            "lastActivePlatformUpdatedAt",
            "users.lastActivePlatformUpdatedAt",
            "login_activity",
        ),
        ("lastLoginAt", "users.lastLoginAt", "login_activity_legacy"),
        ("onboardingUpdatedAt", "users.onboardingUpdatedAt", "onboarding_activity_legacy"),
        ("updatedAt", "users.updatedAt", "generic_update_legacy"),
    )
    for field, source, reason in sources:
        value = _as_datetime(doc.get(field))
        if value is not None:
            return {"value": value, "source": source, "reason": reason}

    return {"value": None, "source": "none", "reason": "missing_activity_fields"}


def policy_state_from_user_doc(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Return normalized values plus internal-only provenance categories."""
    profile = profile_completion_provenance(doc)
    active = account_active_provenance(doc)
    activity = activity_provenance(doc)
    return {
        "isActive": active["value"] is True,
        "isProfileComplete": profile["value"] is True,
        "activeSource": active["source"],
        "activeReason": active["reason"],
        "profileCompleteSource": profile["source"],
        "profileCompleteReason": profile["reason"],
        "lastActiveAt": activity["value"],
        "activitySource": activity["source"],
        "activityReason": activity["reason"],
    }


__all__ = [
    "account_active_provenance",
    "activity_provenance",
    "policy_state_from_user_doc",
    "profile_completion_provenance",
]
