"""RED tests for P1.4 Firebase codebase-parameter recovery."""

from __future__ import annotations

import pytest

from parameter_contract_fixtures import (
    AUTHORITY_FUNCTIONS,
    AUTHORITY_VALUES,
    CODEBASE_PARAMETER_KEYS,
    authority_values_by_function,
    contract_module,
    discovered_string_parameters,
)


def test_zero_source_plain_env_plus_four_codebase_parameters_passes_with_exact_candidate():
    contract = contract_module()
    expected_keys = contract.expected_candidate_keys(
        source_plain_env_keys=frozenset(),
        codebase_parameter_keys=CODEBASE_PARAMETER_KEYS,
    )

    assert expected_keys == CODEBASE_PARAMETER_KEYS
    contract.validate_discovered_parameters(
        parameters=discovered_string_parameters(),
        expected_non_secret_keys=expected_keys,
    )
    contract.validate_live_parameter_authority(
        candidate_values=dict(AUTHORITY_VALUES),
        authority_values_by_function=authority_values_by_function(),
        authority_functions=AUTHORITY_FUNCTIONS,
        parameters=discovered_string_parameters(),
    )


def test_missing_one_codebase_parameter_fails_closed():
    contract = contract_module()
    candidate_values = dict(AUTHORITY_VALUES)
    candidate_values.pop("RESEND_REPLY_TO")

    with pytest.raises(Exception, match="MISSING.*RESEND_REPLY_TO"):
        contract.validate_live_parameter_authority(
            candidate_values=candidate_values,
            authority_values_by_function=authority_values_by_function(),
            authority_functions=AUTHORITY_FUNCTIONS,
            parameters=discovered_string_parameters(),
        )


def test_extra_fifth_candidate_key_fails_closed():
    contract = contract_module()
    candidate_values = dict(AUTHORITY_VALUES)
    candidate_values["UNDECLARED_FIFTH_KEY"] = "synthetic-extra"

    with pytest.raises(Exception, match="EXTRA.*UNDECLARED_FIFTH_KEY"):
        contract.validate_live_parameter_authority(
            candidate_values=candidate_values,
            authority_values_by_function=authority_values_by_function(),
            authority_functions=AUTHORITY_FUNCTIONS,
            parameters=discovered_string_parameters(),
        )


def test_differing_candidate_value_fails_without_printing_value():
    contract = contract_module()
    leaked_value = "do-not-print-this-synthetic-value"
    candidate_values = dict(AUTHORITY_VALUES)
    candidate_values["RESEND_FROM_EMAIL"] = leaked_value

    with pytest.raises(Exception) as raised:
        contract.validate_live_parameter_authority(
            candidate_values=candidate_values,
            authority_values_by_function=authority_values_by_function(),
            authority_functions=AUTHORITY_FUNCTIONS,
            parameters=discovered_string_parameters(),
        )

    message = str(raised.value)
    assert "RESEND_FROM_EMAIL" in message
    assert leaked_value not in message


def test_new_target_source_plain_env_read_expands_candidate_set_until_manifest_update():
    contract = contract_module()
    expected_keys = contract.expected_candidate_keys(
        source_plain_env_keys=frozenset({"NEW_TARGET_SOURCE_ENV"}),
        codebase_parameter_keys=CODEBASE_PARAMETER_KEYS,
    )

    assert expected_keys == CODEBASE_PARAMETER_KEYS | {"NEW_TARGET_SOURCE_ENV"}
    assert frozenset(AUTHORITY_VALUES) != expected_keys
    assert expected_keys - frozenset(AUTHORITY_VALUES) == {"NEW_TARGET_SOURCE_ENV"}


def test_unexpected_discovered_non_secret_parameter_fails_closed():
    contract = contract_module()
    parameters = discovered_string_parameters(
        {
            "name": "UNEXPECTED_RUNTIME_PARAMETER",
            "type": "string",
            "default": "synthetic-default",
            "input": "",
        }
    )

    with pytest.raises(Exception, match="UNEXPECTED_RUNTIME_PARAMETER"):
        contract.validate_discovered_parameters(
            parameters=parameters,
            expected_non_secret_keys=CODEBASE_PARAMETER_KEYS,
        )


def test_secret_parameter_type_is_not_accepted_as_plain_codebase_parameter():
    contract = contract_module()
    parameters = discovered_string_parameters(
        {
            "name": "RESEND_API_KEY",
            "type": "secret",
            "default": "",
            "input": "",
        }
    )

    with pytest.raises(Exception, match="SECRET.*RESEND_API_KEY"):
        contract.validate_discovered_parameters(
            parameters=parameters,
            expected_non_secret_keys=CODEBASE_PARAMETER_KEYS | {"RESEND_API_KEY"},
        )


def test_platform_managed_parameter_key_fails_closed():
    contract = contract_module()

    with pytest.raises(Exception, match="FUNCTION_TARGET"):
        contract.expected_candidate_keys(
            source_plain_env_keys=frozenset(),
            codebase_parameter_keys=CODEBASE_PARAMETER_KEYS | {"FUNCTION_TARGET"},
        )

    with pytest.raises(Exception, match="FUNCTION_TARGET"):
        contract.validate_discovered_parameters(
            parameters=discovered_string_parameters(
                {
                    "name": "FUNCTION_TARGET",
                    "type": "string",
                    "default": "syncMeetingIcebreakerFromPromise",
                    "input": "",
                }
            ),
            expected_non_secret_keys=CODEBASE_PARAMETER_KEYS,
        )
