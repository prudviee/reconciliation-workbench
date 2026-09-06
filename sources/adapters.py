"""Predefined and configurable source-contract adapters."""

from __future__ import annotations

from typing import Any

from reconciliation.domain import (
    CanonicalSide,
    CanonicalState,
    DatasetMode,
    DateFoldPolicy,
    EnumMapping,
    FieldBinding,
    IngestionOperation,
    ReferenceSemantics,
    SourceContract,
)


LEDGER_ADAPTER_KEY = "atlas-ledger-v1"
COUNTERPARTY_ADAPTER_KEY = "atlas-counterparty-v1"
CONFIGURABLE_ADAPTER_KEY = "configurable-v1"
PARSER_VERSION = "1"

CANONICAL_FIELDS = frozenset(
    {
        "source_record_key",
        "business_reference",
        "executed_at_utc",
        "instrument",
        "side",
        "quantity",
        "unit_price",
        "gross_amount",
        "currency",
        "state",
    }
)
REQUIRED_CANONICAL_FIELDS = CANONICAL_FIELDS - {"business_reference"}


class InvalidSourceContract(ValueError):
    pass


def ledger_contract() -> SourceContract:
    return _validated_contract(
        SourceContract(
            adapter_key=LEDGER_ADAPTER_KEY,
            parser_version=PARSER_VERSION,
            mode=DatasetMode.FULL_SNAPSHOT,
            identity_namespace="atlas-ledger-trade",
            reference_semantics=ReferenceSemantics.TRUSTED_SHARED,
            timestamp_format="ISO8601",
            timezone_name=None,
            bindings=_bindings(
                source_record_key="trade_id",
                business_reference="trade_id",
                executed_at_utc="traded_at",
                instrument="instrument",
                side="side",
                quantity="quantity",
                unit_price="price",
                gross_amount="gross_amount",
                currency=None,
                state="state",
            ),
            enum_mappings=(
                EnumMapping("side", (("BUY", "BUY"), ("SELL", "SELL"))),
                EnumMapping(
                    "state",
                    (("SETTLED", "SETTLED"), ("CANCELLED", "CANCELLED")),
                ),
            ),
        )
    )


def counterparty_contract() -> SourceContract:
    return _validated_contract(
        SourceContract(
            adapter_key=COUNTERPARTY_ADAPTER_KEY,
            parser_version=PARSER_VERSION,
            mode=DatasetMode.FULL_SNAPSHOT,
            identity_namespace="atlas-counterparty-reference",
            reference_semantics=ReferenceSemantics.TRUSTED_SHARED,
            timestamp_format="%Y-%m-%d %H:%M:%S",
            timezone_name="UTC",
            bindings=_bindings(
                source_record_key="reference",
                business_reference="reference",
                executed_at_utc="executed_at",
                instrument="symbol",
                side="direction",
                quantity="qty",
                unit_price="unit_price",
                gross_amount="total",
                currency=None,
                state="status",
            ),
            enum_mappings=(
                EnumMapping("side", (("B", "BUY"), ("S", "SELL"))),
                EnumMapping(
                    "state",
                    (("SETTLED", "SETTLED"), ("CANCELLED", "CANCELLED")),
                ),
            ),
        )
    )


def configurable_contract(
    *,
    mode: DatasetMode,
    identity_namespace: str,
    reference_semantics: ReferenceSemantics,
    timestamp_format: str,
    timezone_name: str | None,
    bindings: tuple[FieldBinding, ...],
    enum_mappings: tuple[EnumMapping, ...],
    null_tokens: tuple[str, ...] = (),
    operation_field: str | None = None,
    operation_mapping: tuple[tuple[str, IngestionOperation], ...] = (),
    fold_policy: DateFoldPolicy = DateFoldPolicy.REJECT,
) -> SourceContract:
    return _validated_contract(
        SourceContract(
            adapter_key=CONFIGURABLE_ADAPTER_KEY,
            parser_version=PARSER_VERSION,
            mode=mode,
            identity_namespace=identity_namespace,
            reference_semantics=reference_semantics,
            timestamp_format=timestamp_format,
            timezone_name=timezone_name,
            bindings=bindings,
            enum_mappings=enum_mappings,
            null_tokens=null_tokens,
            operation_field=operation_field,
            operation_mapping=operation_mapping,
            fold_policy=fold_policy,
        )
    )


def contract_to_payload(contract: SourceContract) -> dict[str, Any]:
    _validated_contract(contract)
    return {
        "adapter_key": contract.adapter_key,
        "parser_version": contract.parser_version,
        "mode": contract.mode.value,
        "identity_namespace": contract.identity_namespace,
        "reference_semantics": contract.reference_semantics.value,
        "timestamp_format": contract.timestamp_format,
        "timezone_name": contract.timezone_name,
        "bindings": [
            {
                "canonical_field": binding.canonical_field,
                "source_column": binding.source_column,
                "constant": binding.constant,
            }
            for binding in contract.bindings
        ],
        "enum_mappings": [
            {
                "canonical_field": mapping.canonical_field,
                "values": [list(value) for value in mapping.values],
            }
            for mapping in contract.enum_mappings
        ],
        "null_tokens": list(contract.null_tokens),
        "operation_field": contract.operation_field,
        "operation_mapping": [
            [source, operation.value]
            for source, operation in contract.operation_mapping
        ],
        "fold_policy": contract.fold_policy.value,
    }


def contract_from_payload(payload: dict[str, Any]) -> SourceContract:
    try:
        contract = SourceContract(
            adapter_key=str(payload["adapter_key"]),
            parser_version=str(payload["parser_version"]),
            mode=DatasetMode(payload["mode"]),
            identity_namespace=str(payload["identity_namespace"]),
            reference_semantics=ReferenceSemantics(payload["reference_semantics"]),
            timestamp_format=str(payload["timestamp_format"]),
            timezone_name=payload.get("timezone_name"),
            bindings=tuple(
                FieldBinding(
                    canonical_field=item["canonical_field"],
                    source_column=item.get("source_column"),
                    constant=item.get("constant"),
                )
                for item in payload["bindings"]
            ),
            enum_mappings=tuple(
                EnumMapping(
                    canonical_field=item["canonical_field"],
                    values=tuple((str(source), str(target)) for source, target in item["values"]),
                )
                for item in payload.get("enum_mappings", [])
            ),
            null_tokens=tuple(str(value) for value in payload.get("null_tokens", [])),
            operation_field=payload.get("operation_field"),
            operation_mapping=tuple(
                (str(source), IngestionOperation(operation))
                for source, operation in payload.get("operation_mapping", [])
            ),
            fold_policy=DateFoldPolicy(payload.get("fold_policy", DateFoldPolicy.REJECT)),
        )
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise InvalidSourceContract("stored source contract is invalid") from error
    return _validated_contract(contract)


def _validated_contract(contract: SourceContract) -> SourceContract:
    if contract.adapter_key not in {
        LEDGER_ADAPTER_KEY,
        COUNTERPARTY_ADAPTER_KEY,
        CONFIGURABLE_ADAPTER_KEY,
    }:
        raise InvalidSourceContract("contract uses an unsupported adapter")
    fields = {binding.canonical_field for binding in contract.bindings}
    if not fields <= CANONICAL_FIELDS:
        raise InvalidSourceContract("contract contains an unsupported canonical field")
    if not REQUIRED_CANONICAL_FIELDS <= fields:
        raise InvalidSourceContract("contract is missing a required canonical field")
    if (
        contract.reference_semantics is not ReferenceSemantics.NONE
        and "business_reference" not in fields
    ):
        raise InvalidSourceContract(
            "contract reference semantics require a business-reference binding"
        )
    enum_fields = {mapping.canonical_field for mapping in contract.enum_mappings}
    if not {"side", "state"} <= enum_fields:
        raise InvalidSourceContract("contract requires side and state enum mappings")
    if not enum_fields <= {"side", "state"}:
        raise InvalidSourceContract("contract contains an unsupported enum mapping")
    enums = {mapping.canonical_field: mapping for mapping in contract.enum_mappings}
    try:
        for _, target in enums["side"].values:
            CanonicalSide(target)
        for _, target in enums["state"].values:
            CanonicalState(target)
    except ValueError as error:
        raise InvalidSourceContract("contract enum mapping has an invalid target") from error
    return contract


def _bindings(**columns: str | None) -> tuple[FieldBinding, ...]:
    return tuple(
        FieldBinding(field, constant="USD")
        if field == "currency" and column is None
        else FieldBinding(field, source_column=column)
        for field, column in columns.items()
    )
