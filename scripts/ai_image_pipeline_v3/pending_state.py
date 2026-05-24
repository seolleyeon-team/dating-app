from __future__ import annotations

from typing import Any, Mapping


RESOLVED_PENDING_STATUSES = {"resolved", "cleared"}
ACTIVE_PENDING_STATUSES = {"pending_imagegen", "imagegen_started", "imagegen_process_returned"}


def pending_status(payload: Mapping[str, Any] | None) -> str:
    if not payload:
        return ""
    return str(payload.get("status") or "").strip()


def pending_is_resolved(payload: Mapping[str, Any] | None) -> bool:
    if not payload:
        return True
    if payload.get("resolved") is True:
        return True
    return pending_status(payload) in RESOLVED_PENDING_STATUSES


def pending_requires_recovery(payload: Mapping[str, Any] | None) -> bool:
    return bool(payload and pending_status(payload) in ACTIVE_PENDING_STATUSES and not pending_is_resolved(payload))


def pending_is_unresolved(payload: Mapping[str, Any] | None) -> bool:
    return bool(payload and not pending_is_resolved(payload))


def pending_unresolved_reason(payload: Mapping[str, Any] | None) -> str:
    if not payload:
        return ""
    return str(payload.get("pendingInvalidReason") or payload.get("reason") or payload.get("assetId") or pending_status(payload) or "pending-imagegen.json")


def resolved_pending_payload(payload: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    out = dict(payload)
    out.update(extra)
    out["status"] = "resolved"
    out["resolved"] = True
    return out
