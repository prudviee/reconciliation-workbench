from __future__ import annotations

import pytest

from reconciliation.domain import (
    DatasetMode,
    EnumMapping,
    FieldBinding,
    ReferenceSemantics,
)
from sources.adapters import (
    CONFIGURABLE_ADAPTER_KEY,
    COUNTERPARTY_ADAPTER_KEY,
    LEDGER_ADAPTER_KEY,
    InvalidSourceContract,
    configurable_contract,
    contract_from_payload,
    contract_to_payload,
    counterparty_contract,
    ledger_contract,
)


def configurable_bindings() -> tuple[FieldBinding, ...]:
    return (
        FieldBinding("source_record_key", source_column="record_id"),
        FieldBinding("business_reference", source_column="record_id"),
        FieldBinding("executed_at_utc", source_column="event_time"),
        FieldBinding("instrument", source_column="asset"),
        FieldBinding("side", source_column="buy_sell"),
        FieldBinding("quantity", source_column="amount"),
        FieldBinding("unit_price", source_column="rate"),
        FieldBinding("gross_amount", source_column="total_value"),
        FieldBinding("currency", source_column="ccy"),
        FieldBinding("state", source_column="record_status"),
    )


def test_predefined_contracts_capture_the_two_assignment_formats() -> None:
    ledger = ledger_contract()
    counterparty = counterparty_contract()

    assert ledger.adapter_key == LEDGER_ADAPTER_KEY
    assert counterparty.adapter_key == COUNTERPARTY_ADAPTER_KEY
    assert ledger.timestamp_format == "ISO8601"
    assert ledger.timezone_name is None
    assert counterparty.timestamp_format == "%Y-%m-%d %H:%M:%S"
    assert counterparty.timezone_name == "UTC"
    assert dict(ledger.enum_mappings[0].values) == {"BUY": "BUY", "SELL": "SELL"}
    assert dict(counterparty.enum_mappings[0].values) == {"B": "BUY", "S": "SELL"}


def test_configurable_contract_uses_only_typed_allowlisted_transformations() -> None:
    contract = configurable_contract(
        mode=DatasetMode.FULL_SNAPSHOT,
        identity_namespace="third-party-record",
        reference_semantics=ReferenceSemantics.TRUSTED_SHARED,
        timestamp_format="%d/%m/%Y %H:%M",
        timezone_name="Europe/London",
        bindings=configurable_bindings(),
        enum_mappings=(
            EnumMapping("side", (("Buy", "BUY"), ("Sell", "SELL"))),
            EnumMapping(
                "state",
                (("Complete", "SETTLED"), ("Void", "CANCELLED")),
            ),
        ),
        null_tokens=("NULL",),
    )

    assert contract.adapter_key == CONFIGURABLE_ADAPTER_KEY
    assert contract.bindings == configurable_bindings()
    assert contract.null_tokens == ("NULL",)


def test_contract_payload_round_trip_is_lossless_and_json_shaped() -> None:
    contract = counterparty_contract()

    payload = contract_to_payload(contract)

    assert contract_from_payload(payload) == contract
    assert payload["mode"] == "FULL_SNAPSHOT"
    assert isinstance(payload["bindings"], list)
    assert isinstance(payload["enum_mappings"], list)


@pytest.mark.parametrize(
    "bindings",
    [
        (FieldBinding("source_record_key", source_column="id"),),
        configurable_bindings()
        + (FieldBinding("python_expression", constant="eval(value)"),),
    ],
)
def test_configurable_contract_rejects_missing_or_unknown_canonical_fields(
    bindings: tuple[FieldBinding, ...],
) -> None:
    with pytest.raises(InvalidSourceContract):
        configurable_contract(
            mode=DatasetMode.FULL_SNAPSHOT,
            identity_namespace="invalid",
            reference_semantics=ReferenceSemantics.NONE,
            timestamp_format="ISO8601",
            timezone_name=None,
            bindings=bindings,
            enum_mappings=(
                EnumMapping("side", (("B", "BUY"),)),
                EnumMapping("state", (("S", "SETTLED"),)),
            ),
        )


def test_contract_rejects_invalid_enum_targets() -> None:
    with pytest.raises(InvalidSourceContract, match="enum"):
        configurable_contract(
            mode=DatasetMode.FULL_SNAPSHOT,
            identity_namespace="invalid-enum",
            reference_semantics=ReferenceSemantics.TRUSTED_SHARED,
            timestamp_format="ISO8601",
            timezone_name=None,
            bindings=configurable_bindings(),
            enum_mappings=(
                EnumMapping("side", (("B", "PURCHASE"),)),
                EnumMapping("state", (("S", "SETTLED"),)),
            ),
        )


def test_invalid_stored_payload_has_one_public_configuration_failure() -> None:
    with pytest.raises(InvalidSourceContract, match="stored source contract"):
        contract_from_payload({"adapter_key": "missing-everything-else"})


def test_stored_payload_cannot_select_an_unregistered_adapter() -> None:
    payload = contract_to_payload(ledger_contract())
    payload["adapter_key"] = "python-module-from-user-input"

    with pytest.raises(InvalidSourceContract, match="unsupported adapter"):
        contract_from_payload(payload)
