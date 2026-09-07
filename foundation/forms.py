from __future__ import annotations

from django import forms

from reconciliation.domain import (
    DatasetMode,
    EnumMapping,
    FieldBinding,
    IngestionOperation,
    ReferenceSemantics,
)
from sources.adapters import configurable_contract


DELIMITER_CHOICES = ((",", "Comma"), (";", "Semicolon"), ("\t", "Tab"))


class UploadForm(forms.Form):
    adapter = forms.ChoiceField(
        choices=(
            ("ledger", "Atlas ledger format"),
            ("counterparty", "Atlas counterparty format"),
            ("configurable", "My saved column mapping"),
        )
    )
    delimiter = forms.ChoiceField(choices=DELIMITER_CHOICES)
    artifact = forms.FileField(
        label="CSV file",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,text/csv"}),
    )


class MappingForm(forms.Form):
    identity_namespace = forms.CharField(max_length=160, initial="custom-transaction")
    mode = forms.ChoiceField(
        choices=(("FULL_SNAPSHOT", "Full snapshot"), ("DELTA", "Delta"))
    )
    reference_semantics = forms.ChoiceField(
        choices=(("TRUSTED_SHARED", "Trusted shared reference"), ("SECONDARY", "Secondary evidence"), ("NONE", "No shared reference"))
    )
    timestamp_format = forms.CharField(initial="%Y-%m-%d %H:%M:%S")
    timezone_name = forms.CharField(initial="UTC", required=False)
    source_record_key = forms.CharField(initial="id")
    business_reference = forms.CharField(initial="reference", required=False)
    executed_at_utc = forms.CharField(initial="executed_at")
    instrument = forms.CharField(initial="instrument")
    side = forms.CharField(initial="side")
    quantity = forms.CharField(initial="quantity")
    unit_price = forms.CharField(initial="unit_price")
    gross_amount = forms.CharField(initial="gross_amount")
    currency = forms.CharField(initial="currency")
    state = forms.CharField(initial="state")
    buy_value = forms.CharField(initial="BUY")
    sell_value = forms.CharField(initial="SELL")
    settled_value = forms.CharField(initial="SETTLED")
    cancelled_value = forms.CharField(initial="CANCELLED")
    operation_field = forms.CharField(required=False, initial="operation")
    upsert_value = forms.CharField(required=False, initial="UPSERT")
    cancel_value = forms.CharField(required=False, initial="CANCEL")
    retract_value = forms.CharField(required=False, initial="RETRACT")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("mode") == DatasetMode.DELTA:
            for name in ("operation_field", "upsert_value", "cancel_value", "retract_value"):
                if not cleaned.get(name):
                    self.add_error(name, "This value is required for a delta mapping.")
        if cleaned.get("reference_semantics") != ReferenceSemantics.NONE and not cleaned.get("business_reference"):
            self.add_error("business_reference", "Map a reference column or choose no shared reference.")
        return cleaned

    def to_contract(self):
        values = self.cleaned_data
        bindings = [
            FieldBinding(name, source_column=values[name])
            for name in (
                "source_record_key",
                "executed_at_utc",
                "instrument",
                "side",
                "quantity",
                "unit_price",
                "gross_amount",
                "currency",
                "state",
            )
        ]
        if values.get("business_reference"):
            bindings.insert(1, FieldBinding("business_reference", source_column=values["business_reference"]))
        mode = DatasetMode(values["mode"])
        operation_mapping = ()
        operation_field = None
        if mode is DatasetMode.DELTA:
            operation_field = values["operation_field"]
            operation_mapping = (
                (values["upsert_value"], IngestionOperation.UPSERT),
                (values["cancel_value"], IngestionOperation.CANCEL),
                (values["retract_value"], IngestionOperation.RETRACT),
            )
        return configurable_contract(
            mode=mode,
            identity_namespace=values["identity_namespace"],
            reference_semantics=ReferenceSemantics(values["reference_semantics"]),
            timestamp_format=values["timestamp_format"],
            timezone_name=values.get("timezone_name") or None,
            bindings=tuple(bindings),
            enum_mappings=(
                EnumMapping("side", ((values["buy_value"], "BUY"), (values["sell_value"], "SELL"))),
                EnumMapping("state", ((values["settled_value"], "SETTLED"), (values["cancelled_value"], "CANCELLED"))),
            ),
            operation_field=operation_field,
            operation_mapping=operation_mapping,
        )
