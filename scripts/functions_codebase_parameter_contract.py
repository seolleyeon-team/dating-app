"""Pure validation for Firebase Functions codebase-wide parameter inputs.

This module deliberately handles parameter names and compares values in
memory; it never includes candidate or live values in an exception message.
Secret parameters are classified, but are never treated as dotenv values.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from functions_source_env_contract import ENV_KEY_PATTERN, PLATFORM_MANAGED_KEYS


SOURCE_DEFAULT_AUTHORITY_KEYS = frozenset(
    {"APPLE_IAP_APPLE_ID", "APPLE_IAP_BUNDLE_ID"}
)
NONEMPTY_REQUIRED_PARAMETER_KEYS = frozenset({"RESEND_FROM_EMAIL"})


class ParameterContractError(RuntimeError):
    """The discovered Functions parameter contract is not safe to deploy."""


def _validated_keys(values: Iterable[str], *, label: str) -> frozenset[str]:
    if isinstance(values, (str, bytes)):
        raise ParameterContractError(f"{label} must be a collection of parameter names")
    try:
        items = list(values)
    except TypeError as error:
        raise ParameterContractError(
            f"{label} must be a collection of parameter names"
        ) from error
    if any(not isinstance(item, str) for item in items):
        raise ParameterContractError(f"{label} contains a non-string parameter name")
    if len(items) != len(set(items)):
        raise ParameterContractError(f"{label} contains duplicate parameter names")

    invalid = sorted(item for item in items if not ENV_KEY_PATTERN.fullmatch(item))
    if invalid:
        raise ParameterContractError(
            f"{label} contains invalid parameter name(s): {', '.join(invalid)}"
        )
    managed = sorted(set(items) & PLATFORM_MANAGED_KEYS)
    if managed:
        raise ParameterContractError(
            f"PLATFORM_MANAGED_PARAMETER_REFUSED: {', '.join(managed)}"
        )
    return frozenset(items)


def expected_candidate_keys(
    source_plain_env_keys: Iterable[str], codebase_parameter_keys: Iterable[str]
) -> frozenset[str]:
    """Return the exact dotenv key set for source reads plus string params."""

    source_keys = _validated_keys(source_plain_env_keys, label="source plain env keys")
    codebase_keys = _validated_keys(
        codebase_parameter_keys, label="codebase parameter keys"
    )
    return _validated_keys(
        source_keys | codebase_keys, label="candidate parameter keys"
    )


def _parameter_records(
    parameters: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], frozenset[str], frozenset[str]]:
    if isinstance(parameters, (str, bytes)) or not isinstance(parameters, Sequence):
        raise ParameterContractError("discovered parameters must be a list")

    records: dict[str, Mapping[str, Any]] = {}
    non_secret: set[str] = set()
    secrets: set[str] = set()
    for index, parameter in enumerate(parameters):
        if not isinstance(parameter, Mapping):
            raise ParameterContractError(
                f"discovered parameter at index {index} is not an object"
            )
        name = parameter.get("name")
        kind = parameter.get("type")
        if not isinstance(name, str) or not ENV_KEY_PATTERN.fullmatch(name):
            raise ParameterContractError(
                f"discovered parameter at index {index} has an invalid name"
            )
        if not isinstance(kind, str) or not kind.strip():
            raise ParameterContractError(
                f"discovered parameter {name} has no valid type"
            )
        if name in records:
            raise ParameterContractError(
                f"DUPLICATE_DISCOVERED_PARAMETER: {name}"
            )
        if name in PLATFORM_MANAGED_KEYS:
            raise ParameterContractError(
                f"PLATFORM_MANAGED_PARAMETER_REFUSED: {name}"
            )
        records[name] = parameter
        (secrets if kind.casefold() == "secret" else non_secret).add(name)
    return records, frozenset(non_secret), frozenset(secrets)


def validate_discovered_parameters(
    parameters: Sequence[Mapping[str, Any]],
    expected_non_secret_keys: Iterable[str],
    *,
    expected_types: Mapping[str, str] | None = None,
    expected_secret_keys: Iterable[str] | None = None,
) -> frozenset[str]:
    """Require the complete discovered non-secret key set to match the manifest."""

    expected = _validated_keys(
        expected_non_secret_keys, label="expected codebase parameter keys"
    )
    records, non_secret, secrets = _parameter_records(parameters)
    secret_in_candidate = sorted(expected & secrets)
    if secret_in_candidate:
        raise ParameterContractError(
            "SECRET_PARAMETER_IN_CANDIDATE_CONTRACT: "
            + ", ".join(secret_in_candidate)
        )
    missing = sorted(expected - non_secret)
    unexpected = sorted(non_secret - expected)
    if missing:
        raise ParameterContractError(
            "MISSING_DISCOVERED_PARAMETER: " + ", ".join(missing)
        )
    if unexpected:
        raise ParameterContractError(
            "UNEXPECTED_DISCOVERED_PARAMETER: " + ", ".join(unexpected)
        )
    if expected_types is not None:
        if not isinstance(expected_types, Mapping):
            raise ParameterContractError("expected parameter types must be a mapping")
        type_keys = _validated_keys(
            expected_types.keys(), label="expected codebase parameter type keys"
        )
        if type_keys != expected:
            raise ParameterContractError(
                "CODEBASE_PARAMETER_TYPE_MANIFEST_MISMATCH"
            )
        for key, expected_type in expected_types.items():
            if not isinstance(expected_type, str) or expected_type.casefold() not in {
                "string",
                "int",
                "boolean",
                "list",
            }:
                raise ParameterContractError(
                    f"INVALID_EXPECTED_CODEBASE_PARAMETER_TYPE: {key}"
                )
            actual_type = records[key].get("type")
            if (
                not isinstance(actual_type, str)
                or actual_type.casefold() != expected_type.casefold()
            ):
                raise ParameterContractError(
                    f"CODEBASE_PARAMETER_TYPE_MISMATCH: {key}"
                )
    if expected_secret_keys is not None:
        expected_secrets = _validated_keys(
            expected_secret_keys, label="expected codebase secret parameter names"
        )
        if expected_secrets & expected:
            raise ParameterContractError(
                "SECRET_PARAMETER_IN_CANDIDATE_CONTRACT: "
                + ", ".join(sorted(expected_secrets & expected))
            )
        missing_secrets = sorted(expected_secrets - secrets)
        unexpected_secrets = sorted(secrets - expected_secrets)
        if missing_secrets or unexpected_secrets:
            details = []
            if missing_secrets:
                details.append("missing=" + ",".join(missing_secrets))
            if unexpected_secrets:
                details.append("unexpected=" + ",".join(unexpected_secrets))
            raise ParameterContractError(
                "CODEBASE_SECRET_PARAMETER_SET_MISMATCH: " + "; ".join(details)
            )
    return non_secret


def validate_candidate_key_set(
    candidate_values: Mapping[str, str], expected_candidate_key_set: Iterable[str]
) -> None:
    """Require the dotenv key set to equal source reads plus codebase parameters."""

    if not isinstance(candidate_values, Mapping):
        raise ParameterContractError("candidate dotenv values must be a mapping")
    expected = _validated_keys(
        expected_candidate_key_set, label="expected candidate parameter keys"
    )
    observed = _validated_keys(candidate_values.keys(), label="candidate dotenv keys")
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)
    if missing:
        raise ParameterContractError(
            "MISSING_CANDIDATE_PARAMETER: " + ", ".join(missing)
        )
    if extra:
        raise ParameterContractError("EXTRA_CANDIDATE_PARAMETER: " + ", ".join(extra))
    for key in sorted(observed):
        if not isinstance(candidate_values.get(key), str):
            raise ParameterContractError(f"INVALID_CANDIDATE_PARAMETER_VALUE: {key}")


def validate_live_parameter_authority(
    candidate_values: Mapping[str, str],
    authority_values_by_function: Mapping[str, Mapping[str, str]],
    authority_functions: Sequence[str],
    parameters: Sequence[Mapping[str, Any]],
    source_plain_env_keys: Iterable[str] = (),
) -> None:
    """Compare dotenv values with every approved live authority, without logging values."""

    records, expected_keys, secret_keys = _parameter_records(parameters)
    if not isinstance(candidate_values, Mapping):
        raise ParameterContractError("candidate dotenv values must be a mapping")
    if not isinstance(authority_values_by_function, Mapping):
        raise ParameterContractError("live parameter authorities must be a mapping")
    source_keys = _validated_keys(
        source_plain_env_keys, label="source plain env keys"
    )
    candidate_key_set = expected_candidate_keys(source_keys, expected_keys)
    candidate_keys = _validated_keys(
        candidate_values.keys(), label="candidate dotenv keys"
    )
    if candidate_keys & secret_keys:
        raise ParameterContractError(
            "SECRET_PARAMETER_IN_CANDIDATE_CONTRACT: "
            + ", ".join(sorted(candidate_keys & secret_keys))
        )
    validate_candidate_key_set(candidate_values, candidate_key_set)
    for key in sorted(NONEMPTY_REQUIRED_PARAMETER_KEYS & candidate_key_set):
        if not candidate_values[key].strip():
            raise ParameterContractError(f"REQUIRED_PARAMETER_VALUE_EMPTY: {key}")

    if isinstance(authority_functions, (str, bytes)):
        raise ParameterContractError("live parameter authorities must be a collection")
    authorities = list(authority_functions)
    if not authorities or any(not isinstance(name, str) or not name for name in authorities):
        raise ParameterContractError("LIVE_PARAMETER_AUTHORITIES_REQUIRED")
    if len(authorities) != len(set(authorities)):
        raise ParameterContractError("DUPLICATE_LIVE_PARAMETER_AUTHORITY")

    for function in authorities:
        live_values = authority_values_by_function.get(function)
        if not isinstance(live_values, Mapping):
            raise ParameterContractError(
                f"MISSING_LIVE_PARAMETER_AUTHORITY: {function}"
            )
        missing_live = sorted(candidate_key_set - set(live_values))
        if missing_live:
            raise ParameterContractError(
                f"INCOMPLETE_LIVE_PARAMETER_AUTHORITY: {function}: "
                + ", ".join(missing_live)
            )
        for key in sorted(candidate_key_set):
            live_value = live_values[key]
            if not isinstance(live_value, str) or candidate_values[key] != live_value:
                raise ParameterContractError(
                    f"LIVE_PARAMETER_VALUE_MISMATCH: {function}: {key}"
                )

    for key in sorted(SOURCE_DEFAULT_AUTHORITY_KEYS & expected_keys):
        source_default = records[key].get("default")
        if not isinstance(source_default, str) or not source_default:
            raise ParameterContractError(f"MISSING_SOURCE_PARAMETER_DEFAULT: {key}")
        if candidate_values[key] != source_default:
            raise ParameterContractError(f"LIVE_SOURCE_DEFAULT_MISMATCH: {key}")
