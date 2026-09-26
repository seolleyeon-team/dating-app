"""Local fixtures for the P1.4 codebase-parameter recovery tests."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


CODEBASE_PARAMETER_KEYS = frozenset(
    {
        "APPLE_IAP_APPLE_ID",
        "APPLE_IAP_BUNDLE_ID",
        "RESEND_FROM_EMAIL",
        "RESEND_REPLY_TO",
    }
)

AUTHORITY_FUNCTIONS = (
    "sendStudentVerificationEmail",
    "appStoreServerNotifications",
    "cleanupAvatarMedia",
)

AUTHORITY_VALUES = {
    "APPLE_IAP_APPLE_ID": "94727223",
    "APPLE_IAP_BUNDLE_ID": "com.seolleyeon.app",
    "RESEND_FROM_EMAIL": "noreply@example.invalid",
    "RESEND_REPLY_TO": "support@example.invalid",
}


def contract_module():
    return importlib.import_module("functions_codebase_parameter_contract")


def discovered_string_parameters(*extra: Mapping[str, str]) -> list[dict[str, str]]:
    parameters = [
        {
            "name": "APPLE_IAP_APPLE_ID",
            "type": "string",
            "default": "94727223",
            "input": "",
        },
        {
            "name": "APPLE_IAP_BUNDLE_ID",
            "type": "string",
            "default": "com.seolleyeon.app",
            "input": "",
        },
        {
            "name": "RESEND_FROM_EMAIL",
            "type": "string",
            "default": "",
            "input": "",
        },
        {
            "name": "RESEND_REPLY_TO",
            "type": "string",
            "default": "",
            "input": "",
        },
    ]
    parameters.extend(dict(item) for item in extra)
    return parameters


def authority_values_by_function(
    overrides: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, dict[str, str]]:
    values = {function: dict(AUTHORITY_VALUES) for function in AUTHORITY_FUNCTIONS}
    if overrides:
        for function, function_overrides in overrides.items():
            values.setdefault(function, dict(AUTHORITY_VALUES)).update(function_overrides)
    return values
