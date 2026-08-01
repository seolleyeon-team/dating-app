from __future__ import annotations

import re
from typing import Any, Dict

from .config import DEFAULT_REDACTED_GCS_SOURCE_REF, DEFAULT_REDACTED_URL_SOURCE_REF

PRIVATE_SOURCE_BUCKET_PATTERN = re.compile(
    r"seolleyeon(?:-final)?-private-source-photos",
    re.IGNORECASE,
)
GCS_REF_PATTERN = re.compile(r"g(?:s|cs)://[^\s\"']+", re.IGNORECASE)
URL_REF_PATTERN = re.compile(r"https?://[^\s\"']+", re.IGNORECASE)
SIGNED_URL_MARKERS = (
    "x-goog-signature",
    "x-goog-credential",
    "x-goog-expires",
    "googleaccessid",
    "signature=",
    "signedurl",
    "getsignedurl",
    "x-amz-signature",
    "x-amz-credential",
    "x-amz-expires",
)


def _contains_private_source_bucket(value: str) -> bool:
    return PRIVATE_SOURCE_BUCKET_PATTERN.search(value) is not None


def _contains_signed_marker(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in SIGNED_URL_MARKERS)


def _redact_text(value: str) -> str:
    if GCS_REF_PATTERN.fullmatch(value) and _contains_private_source_bucket(value):
        return DEFAULT_REDACTED_GCS_SOURCE_REF
    if URL_REF_PATTERN.fullmatch(value) and (
        _contains_private_source_bucket(value) or _contains_signed_marker(value)
    ):
        return DEFAULT_REDACTED_URL_SOURCE_REF

    redacted = GCS_REF_PATTERN.sub(
        lambda match: (
            DEFAULT_REDACTED_GCS_SOURCE_REF
            if _contains_private_source_bucket(match.group(0))
            else match.group(0)
        ),
        value,
    )
    redacted = URL_REF_PATTERN.sub(
        lambda match: (
            DEFAULT_REDACTED_URL_SOURCE_REF
            if (
                _contains_private_source_bucket(match.group(0))
                or _contains_signed_marker(match.group(0))
            )
            else match.group(0)
        ),
        redacted,
    )
    return redacted


def redact_source_ref(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {
            str(key): redact_source_ref(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [redact_source_ref(child) for child in value]
    if isinstance(value, tuple):
        return tuple(redact_source_ref(child) for child in value)
    return value


def redacted_source_ref(value: str) -> str:
    redacted = redact_source_ref(value)
    return redacted if isinstance(redacted, str) else DEFAULT_REDACTED_GCS_SOURCE_REF


__all__ = ["redact_source_ref", "redacted_source_ref"]
