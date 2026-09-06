from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from books.models import BookKind, ReconciliationBook
from ingestion.artifacts import IntakeLimits, PrivateArtifactStore
from ingestion.models import AttemptState, IngestionAttempt, RawRow
from ingestion.preview import PreviewService, interpret_csv
from ingestion.repositories import WorkspaceIngestionRepository
from ingestion.services import ArtifactIntakeService
from reconciliation.domain import (
    BookId,
    DatasetMode,
    EnumMapping,
    FieldBinding,
    ReferenceSemantics,
    RowErrorCode,
    SourceContract,
    WorkspaceId,
)
from sources.adapters import (
    configurable_contract,
    contract_to_payload,
    counterparty_contract,
    ledger_contract,
)
from sources.models import SourceRole
from sources.repositories import WorkspaceSourceRepository
from workspaces.models import Workspace


pytestmark = pytest.mark.django_db
NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)
LIMITS = IntakeLimits(10_000, 100, 20, 1_000)
LEDGER_HEADER = (
    "trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
)
LEDGER_ROW = "T-1001,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000,SETTLED\n"
COUNTERPARTY_HEADER = (
    "reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
)
COUNTERPARTY_ROW = (
    "T-1001,2025-07-01 09:15:00,BTC-USD,B,0.500,62000.00,31000.0,SETTLED\n"
)


def write_csv(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8", newline="")
    return path


def comparable_values(row) -> tuple[object, ...]:
    assert row.canonical is not None
    canonical = row.canonical
    return (
        canonical.source_record_key,
        canonical.business_reference,
        canonical.executed_at_utc,
        canonical.instrument,
        canonical.side,
        canonical.quantity,
        canonical.unit_price,
        canonical.gross_amount,
        canonical.currency,
        canonical.state,
        canonical.eligible_for_matching,
    )


def configurable_preview_contract() -> SourceContract:
    return configurable_contract(
        mode=DatasetMode.FULL_SNAPSHOT,
        identity_namespace="custom-id",
        reference_semantics=ReferenceSemantics.TRUSTED_SHARED,
        timestamp_format="%d/%m/%Y %H:%M",
        timezone_name="UTC",
        bindings=(
            FieldBinding("source_record_key", source_column="record_id"),
            FieldBinding("business_reference", source_column="record_id"),
            FieldBinding("executed_at_utc", source_column="when"),
            FieldBinding("instrument", source_column="asset"),
            FieldBinding("side", source_column="buy_sell"),
            FieldBinding("quantity", source_column="amount"),
            FieldBinding("unit_price", source_column="rate"),
            FieldBinding("gross_amount", source_column="value"),
            FieldBinding("currency", source_column="ccy"),
            FieldBinding("state", source_column="record_status"),
        ),
        enum_mappings=(
            EnumMapping("side", (("Buy", "BUY"), ("Sell", "SELL"))),
            EnumMapping(
                "state",
                (("Complete", "SETTLED"), ("Void", "CANCELLED")),
            ),
        ),
    )


def test_two_assignment_adapters_and_configurable_mapping_have_canonical_parity(
    tmp_path: Path,
) -> None:
    ledger = interpret_csv(
        write_csv(tmp_path, "ledger.csv", LEDGER_HEADER + LEDGER_ROW),
        delimiter=",",
        limits=LIMITS,
        contract=ledger_contract(),
    )
    counterparty = interpret_csv(
        write_csv(
            tmp_path,
            "counterparty.csv",
            COUNTERPARTY_HEADER + COUNTERPARTY_ROW,
        ),
        delimiter=",",
        limits=LIMITS,
        contract=counterparty_contract(),
    )
    custom = interpret_csv(
        write_csv(
            tmp_path,
            "custom.csv",
            "record_id;when;asset;buy_sell;amount;rate;value;ccy;record_status\n"
            "T-1001;01/07/2025 09:15;BTC-USD;Buy;0.50;62000;31000;USD;Complete\n",
        ),
        delimiter=";",
        limits=LIMITS,
        contract=configurable_preview_contract(),
    )

    assert ledger.error_count == counterparty.error_count == custom.error_count == 0
    assert comparable_values(ledger.rows[0]) == comparable_values(counterparty.rows[0])
    assert comparable_values(ledger.rows[0]) == comparable_values(custom.rows[0])
    assert ledger.rows[0].canonical.provenance_by_field["currency"].source_column is None
    assert custom.rows[0].canonical.provenance_by_field["currency"].source_column == "ccy"


def test_preview_collects_independent_typed_field_errors(tmp_path: Path) -> None:
    result = interpret_csv(
        write_csv(
            tmp_path,
            "invalid.csv",
            LEDGER_HEADER
            + "T-1,not-a-date,BTC-USD,HOLD,NaN,62000,1.1234567890123,SETTLED\n",
        ),
        delimiter=",",
        limits=LIMITS,
        contract=ledger_contract(),
    )

    issues = result.rows[0].issues
    assert {issue.code for issue in issues} == {
        RowErrorCode.INVALID_DATETIME,
        RowErrorCode.UNKNOWN_ENUM,
        RowErrorCode.NON_FINITE_DECIMAL,
        RowErrorCode.UNSUPPORTED_PRECISION,
    }
    assert {issue.row_number for issue in issues} == {2}
    assert {issue.original_value for issue in issues} >= {
        "not-a-date",
        "HOLD",
        "NaN",
        "1.1234567890123",
    }
    assert result.rows[0].canonical is None
    assert result.rows[0].canonical_preview["source_record_key"] == "T-1"
    assert result.rows[0].canonical_preview["instrument"] == "BTC-USD"
    assert result.rows[0].canonical_preview["complete"] is False


def test_missing_duplicate_and_extra_columns_are_explainable(tmp_path: Path) -> None:
    missing = interpret_csv(
        write_csv(tmp_path, "missing.csv", "trade_id,trade_id\nT-1,T-1,extra\n"),
        delimiter=",",
        limits=LIMITS,
        contract=ledger_contract(),
    )

    assert RowErrorCode.DUPLICATE_HEADER in {issue.code for issue in missing.issues}
    assert RowErrorCode.MISSING_COLUMN in {issue.code for issue in missing.issues}
    assert missing.rows[0].canonical is None
    assert missing.rows[0].raw_values[-1] == {
        "column": "__extra_1",
        "kind": "VALUE",
        "original": "extra",
    }


def test_duplicate_source_keys_mark_every_involved_row(tmp_path: Path) -> None:
    result = interpret_csv(
        write_csv(
            tmp_path,
            "duplicate.csv",
            LEDGER_HEADER + LEDGER_ROW + LEDGER_ROW,
        ),
        delimiter=",",
        limits=LIMITS,
        contract=ledger_contract(),
    )

    assert result.error_count == 2
    assert [row.row_number for row in result.rows] == [2, 3]
    assert all(row.canonical is None for row in result.rows)
    assert all(
        row.issues[0].code is RowErrorCode.DUPLICATE_SOURCE_KEY
        for row in result.rows
    )


def test_duplicate_identity_is_reported_even_when_rows_have_other_errors(
    tmp_path: Path,
) -> None:
    invalid = LEDGER_ROW.replace(",0.5,", ",NaN,")
    result = interpret_csv(
        write_csv(
            tmp_path,
            "duplicate-invalid.csv",
            LEDGER_HEADER + invalid + invalid,
        ),
        delimiter=",",
        limits=LIMITS,
        contract=ledger_contract(),
    )

    assert all(
        {issue.code for issue in row.issues}
        == {
            RowErrorCode.NON_FINITE_DECIMAL,
            RowErrorCode.DUPLICATE_SOURCE_KEY,
        }
        for row in result.rows
    )


def test_raw_preview_distinguishes_missing_null_empty_and_value(tmp_path: Path) -> None:
    contract = configurable_preview_contract()
    contract = replace(contract, null_tokens=("NULL",))
    result = interpret_csv(
        write_csv(
            tmp_path,
            "tags.csv",
            "record_id;when;asset;buy_sell;amount;rate;value;ccy;record_status\n"
            "T-1;01/07/2025 09:15;;Buy;NULL;62000;31000\n",
        ),
        delimiter=";",
        limits=LIMITS,
        contract=contract,
    )

    tags = {item["column"]: item["kind"] for item in result.rows[0].raw_values}
    assert tags["record_id"] == "VALUE"
    assert tags["asset"] == "EMPTY"
    assert tags["amount"] == "NULL"
    assert tags["record_status"] == "MISSING"


def create_workspace() -> Workspace:
    return Workspace.objects.create(
        session_digest=uuid4().hex * 2,
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )


def prepare_persistent_preview(
    tmp_path: Path,
    *,
    payload: bytes,
    contract: SourceContract | None = None,
) -> tuple[Workspace, PreviewService, dict[str, object]]:
    workspace = create_workspace()
    book = ReconciliationBook.objects.create(
        workspace=workspace,
        name="July reconciliation",
        kind=BookKind.USER,
        created_at=NOW,
    )
    source_repository = WorkspaceSourceRepository(WorkspaceId(workspace.id))
    ingestion_repository = WorkspaceIngestionRepository(WorkspaceId(workspace.id))
    selected_contract = contract or ledger_contract()
    source = source_repository.create_source(
        name="Input source",
        adapter_key=selected_contract.adapter_key,
        created_at=NOW,
    )
    book_source = source_repository.assign_book_source(
        book_id=BookId(book.id),
        source_id=source.id,
        role=SourceRole.LEFT,
        identity_namespace=selected_contract.identity_namespace,
        created_at=NOW,
    )
    contract_payload = contract_to_payload(selected_contract)
    mapping = source_repository.create_mapping_revision(
        source_id=source.id,
        revision=1,
        mapping={"bindings": contract_payload["bindings"]},
        parser_version=selected_contract.parser_version,
        digest="a" * 64,
        created_at=NOW,
    )
    contract_revision = source_repository.create_contract_revision(
        source_id=source.id,
        mapping_revision_id=mapping.id,
        revision=1,
        mode=selected_contract.mode,
        timezone_name=selected_contract.timezone_name,
        identity_namespace=selected_contract.identity_namespace,
        reference_semantics=selected_contract.reference_semantics,
        contract=contract_payload,
        digest="b" * 64,
        created_at=NOW,
    )
    dataset = ingestion_repository.create_dataset(
        book_source_id=book_source.id,
        coverage_key="2025-07",
        created_at=NOW,
    )
    intake = ArtifactIntakeService(
        store=PrivateArtifactStore(tmp_path),
        limits=LIMITS,
        clock=lambda: NOW,
    )
    artifact = intake.ingest(
        WorkspaceId(workspace.id),
        original_filename="input.csv",
        content_type="text/csv",
        delimiter=",",
        chunks=(payload,),
    )
    preview_service = PreviewService(
        PrivateArtifactStore(tmp_path),
        LIMITS,
        clock=lambda: NOW,
    )
    return workspace, preview_service, {
        "artifact": artifact,
        "dataset": dataset,
        "contract": contract_revision,
    }


def run_preview(
    workspace: Workspace,
    preview_service: PreviewService,
    graph: dict[str, object],
) -> IngestionAttempt:
    return preview_service.preview(
        WorkspaceId(workspace.id),
        artifact_id=graph["artifact"].id,
        dataset_id=graph["dataset"].id,
        contract_revision_id=graph["contract"].id,
        delimiter=",",
    )


def test_ready_preview_persists_complete_raw_canonical_and_provenance(
    tmp_path: Path,
) -> None:
    workspace, preview_service, graph = prepare_persistent_preview(
        tmp_path,
        payload=(LEDGER_HEADER + LEDGER_ROW).encode(),
    )

    attempt = run_preview(workspace, preview_service, graph)
    row = RawRow.objects.get(attempt=attempt)

    assert attempt.state == AttemptState.READY
    assert attempt.row_count == 1
    assert attempt.error_count == 0
    assert attempt.validation == []
    assert row.row_number == 2
    assert row.raw_values[0]["original"] == "T-1001"
    assert row.canonical_preview["gross_amount"] == "31000"
    assert row.canonical_preview["eligible_for_matching"] is True
    assert len(row.canonical_preview["provenance"]) == 10


def test_rejected_preview_persists_all_rows_and_duplicate_errors(
    tmp_path: Path,
) -> None:
    workspace, preview_service, graph = prepare_persistent_preview(
        tmp_path,
        payload=(LEDGER_HEADER + LEDGER_ROW + LEDGER_ROW).encode(),
    )

    attempt = run_preview(workspace, preview_service, graph)
    rows = list(RawRow.objects.filter(attempt=attempt).order_by("row_number"))

    assert attempt.state == AttemptState.REJECTED
    assert attempt.row_count == 2
    assert attempt.error_count == 2
    assert [row.validation[0]["code"] for row in rows] == [
        "DUPLICATE_SOURCE_KEY",
        "DUPLICATE_SOURCE_KEY",
    ]
    assert all(row.canonical_preview["complete"] is False for row in rows)
    assert all(row.canonical_preview["source_record_key"] == "T-1001" for row in rows)


def test_header_failures_are_persisted_once_at_attempt_level(tmp_path: Path) -> None:
    workspace, preview_service, graph = prepare_persistent_preview(
        tmp_path,
        payload=b"trade_id\nT-1001\n",
    )

    attempt = run_preview(workspace, preview_service, graph)
    row = RawRow.objects.get(attempt=attempt)

    assert attempt.state == AttemptState.REJECTED
    assert attempt.error_count == len(attempt.validation)
    assert {issue["code"] for issue in attempt.validation} == {"MISSING_COLUMN"}
    assert row.canonical_preview is None
    assert row.validation == []


def test_rejected_row_persists_successful_fields_and_provenance(tmp_path: Path) -> None:
    invalid = LEDGER_ROW.replace(",BUY,", ",UNKNOWN,")
    workspace, preview_service, graph = prepare_persistent_preview(
        tmp_path,
        payload=(LEDGER_HEADER + invalid).encode(),
    )

    attempt = run_preview(workspace, preview_service, graph)
    row = RawRow.objects.get(attempt=attempt)

    assert attempt.state == AttemptState.REJECTED
    assert row.canonical_preview["complete"] is False
    assert row.canonical_preview["source_record_key"] == "T-1001"
    assert row.canonical_preview["gross_amount"] == "31000"
    assert "side" not in row.canonical_preview
    assert row.validation[0]["original_value"] == "UNKNOWN"
    assert len(row.canonical_preview["provenance"]) == 9


def test_cancelled_preview_remains_visible_and_ineligible(tmp_path: Path) -> None:
    cancelled = LEDGER_ROW.replace("SETTLED", "CANCELLED")
    workspace, preview_service, graph = prepare_persistent_preview(
        tmp_path,
        payload=(LEDGER_HEADER + cancelled).encode(),
    )

    attempt = run_preview(workspace, preview_service, graph)
    row = RawRow.objects.get(attempt=attempt)

    assert attempt.state == AttemptState.READY
    assert row.canonical_preview["state"] == "CANCELLED"
    assert row.canonical_preview["eligible_for_matching"] is False


def test_preview_persistence_rolls_back_if_any_raw_row_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, preview_service, graph = prepare_persistent_preview(
        tmp_path,
        payload=(
            LEDGER_HEADER
            + LEDGER_ROW
            + LEDGER_ROW.replace("T-1001", "T-1002")
        ).encode(),
    )
    original = WorkspaceIngestionRepository.create_raw_rows

    def fail_after_insert(self, **kwargs):
        original(self, **kwargs)
        raise RuntimeError("injected row persistence failure")

    monkeypatch.setattr(
        WorkspaceIngestionRepository,
        "create_raw_rows",
        fail_after_insert,
    )
    with pytest.raises(RuntimeError, match="injected row persistence failure"):
        run_preview(workspace, preview_service, graph)

    assert not IngestionAttempt.objects.exists()
    assert not RawRow.objects.exists()
