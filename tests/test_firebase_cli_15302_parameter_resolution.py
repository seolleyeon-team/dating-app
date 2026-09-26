"""Local regression for Firebase CLI 15.30.2 parameter resolution."""

from __future__ import annotations

import pytest

from parameter_contract_fixtures import (
    AUTHORITY_VALUES,
    FirebaseCli15302ParameterFixture,
    contract_module,
)


def test_absent_dotenv_parameter_fails_before_source_default_prompt_path():
    contract_module()
    fixture = FirebaseCli15302ParameterFixture()
    candidate_values = dict(AUTHORITY_VALUES)
    candidate_values.pop("APPLE_IAP_APPLE_ID")

    with pytest.raises(Exception) as raised:
        fixture.resolve_noninteractive(candidate_values)

    message = str(raised.value)
    assert "APPLE_IAP_APPLE_ID" in message
    assert fixture.prompt_sentinel not in message


def test_every_non_secret_parameter_value_allows_noninteractive_resolution_to_proceed():
    fixture = FirebaseCli15302ParameterFixture()

    fixture.resolve_noninteractive(dict(AUTHORITY_VALUES))
