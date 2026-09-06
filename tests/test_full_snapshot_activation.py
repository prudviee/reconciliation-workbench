from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import json
from uuid import uuid4

import pytest
from django.db import close_old_connections, connection

from books.models import BookKind, ReconciliationBook
from ingestion.activation import (
    AttemptNotReady,
    FullSnapshotActivationService,
    InvalidPreviewEvidence,
    InvalidRestoreReason,
    StalePreview,
)
from ingestion.artifacts import IntakeLimits, PrivateArtifactStore
from ingestion.models import (
    AttemptState,
    DatasetMembership,
    DatasetRevision,
    IngestionAttempt,
    LogicalTransaction,
    RawRow,
    TransactionObservation,
)
from ingestion.preview import PreviewService
from ingestion.repositories import WorkspaceIngestionRepository
from ingestion.services import ArtifactIntakeService
from reconciliation.domain import (
    BookId,
    DatasetMode,
    IngestionOperation,
    WorkspaceId,
    mapping_revision_digest,
    resolved_state_hash,
    source_contract_digest,
)
from sources.adapters import contract_to_payload, ledger_contract
from sources.models import SourceRole
from sources.repositories import WorkspaceSourceRepository
from workspaces.models import Workspace


pytestmark = pytest.mark.django_db
NOW = datetime(2026, 9, 6, 14, tzinfo=UTC)
LIMITS = IntakeLimits(100_000, 100, 20, 1_000)
HEADER = "trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
DELTA_HEADER = HEADER.rstrip("\n") + ",operation\n"


def ledger_row(
    reference: str,
    *,
    quantity: str = "1",
    price: str = "100",
    gross: str = "100",
    state: str = "SETTLED",
) -> str:
    return (
        f"{reference},2025-07-01T09:15:00Z,BTC-USD,BUY,"
        f"{quantity},{price},{gross},{state}\n"
    )


@dataclass(slots=True)
class ActivationContext:
    workspace: Workspace
    dataset: object
    contract_revision: object
    root: Path

    def preview(self, payload: str, *, filename: str) -> IngestionAttempt:
        workspace_id = WorkspaceId(self.workspace.id)
        artifact = ArtifactIntakeService(
            store=PrivateArtifactStore(self.root),
            limits=LIMITS,
            clock=lambda: NOW,
        ).ingest(
            workspace_id,
            original_filename=filename,
            content_type="text/csv",
            delimiter=",",
            chunks=(payload.encode(),),
        )
        return PreviewService(
            PrivateArtifactStore(self.root),
            LIMITS,
            clock=lambda: NOW,
        ).preview(
            workspace_id,
            artifact_id=artifact.id,
            dataset_id=self.dataset.id,
            contract_revision_id=self.contract_revision.id,
            delimiter=",",
        )


def create_context(tmp_path: Path) -> ActivationContext:
    workspace = Workspace.objects.create(
        session_digest=uuid4().hex * 2,
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )
    book = ReconciliationBook.objects.create(
        workspace=workspace,
        name="July close",
        kind=BookKind.USER,
        created_at=NOW,
    )
    workspace_id = WorkspaceId(workspace.id)
    source_repository = WorkspaceSourceRepository(workspace_id)
    ingestion_repository = WorkspaceIngestionRepository(workspace_id)
    contract = ledger_contract()
    payload = contract_to_payload(contract)
    mapping_payload = {"bindings": payload["bindings"]}
    source = source_repository.create_source(
        name="Ledger",
        adapter_key=contract.adapter_key,
        created_at=NOW,
    )
    book_source = source_repository.assign_book_source(
        book_id=BookId(book.id),
        source_id=source.id,
        role=SourceRole.LEFT,
        identity_namespace=contract.identity_namespace,
        created_at=NOW,
    )
    mapping = source_repository.create_mapping_revision(
        source_id=source.id,
        revision=1,
        mapping=mapping_payload,
        parser_version=contract.parser_version,
        digest=mapping_revision_digest(mapping_payload),
        created_at=NOW,
    )
    contract_revision = source_repository.create_contract_revision(
        source_id=source.id,
        mapping_revision_id=mapping.id,
        revision=1,
        mode=contract.mode,
        timezone_name=contract.timezone_name,
        identity_namespace=contract.identity_namespace,
        reference_semantics=contract.reference_semantics,
        contract=payload,
        digest=source_contract_digest(payload),
        created_at=NOW,
    )
    dataset = ingestion_repository.create_dataset(
        book_source_id=book_source.id,
        coverage_key="2025-07",
        created_at=NOW,
    )
    return ActivationContext(workspace, dataset, contract_revision, tmp_path)


def activation_service() -> FullSnapshotActivationService:
    return FullSnapshotActivationService(clock=lambda: NOW)


def enable_delta_contract(context: ActivationContext) -> None:
    contract = replace(
        ledger_contract(),
        mode=DatasetMode.DELTA,
        operation_field="operation",
        operation_mapping=(
            ("UPSERT", IngestionOperation.UPSERT),
            ("CANCEL", IngestionOperation.CANCEL),
            ("RETRACT", IngestionOperation.RETRACT),
        ),
    )
    payload = contract_to_payload(contract)
    context.contract_revision = WorkspaceSourceRepository(
        WorkspaceId(context.workspace.id)
    ).create_contract_revision(
        source_id=context.contract_revision.source_id,
        mapping_revision_id=context.contract_revision.mapping_revision_id,
        revision=2,
        mode=contract.mode,
        timezone_name=contract.timezone_name,
        identity_namespace=contract.identity_namespace,
        reference_semantics=contract.reference_semantics,
        contract=payload,
        digest=source_contract_digest(payload),
        created_at=NOW,
    )


def delta_row(
    reference: str,
    operation: str,
    *,
    quantity: str = "1",
    price: str = "100",
    gross: str = "100",
    state: str = "SETTLED",
) -> str:
    if operation == "RETRACT":
        return f"{reference},,,,,,,,RETRACT\n"
    return ledger_row(
        reference,
        quantity=quantity,
        price=price,
        gross=gross,
        state=state,
    ).rstrip("\n") + f",{operation}\n"


def test_first_full_snapshot_publishes_complete_materialized_membership(
    tmp_path: Path,
) -> None:
    context = create_context(tmp_path)
    attempt = context.preview(
        HEADER + ledger_row("T-1") + ledger_row("T-2", gross="200"),
        filename="first.csv",
    )

    revision = activation_service().activate(
        WorkspaceId(context.workspace.id),
        attempt_id=attempt.id,
    )

    context.dataset.refresh_from_db()
    attempt.refresh_from_db()
    memberships = list(
        DatasetMembership.objects.filter(dataset_revision=revision)
        .select_related("logical_transaction", "observation")
        .order_by("logical_transaction__source_record_key")
    )
    expected_state = resolved_state_hash(
        (
            (
                member.logical_transaction.source_record_key,
                member.observation.fingerprint,
            )
            for member in memberships
        )
    )
    assert context.dataset.current_revision_id == revision.id
    assert attempt.state == AttemptState.ACTIVATED
    assert revision.parent_revision_id is None
    assert revision.state_hash == expected_state
    assert [item.logical_transaction.source_record_key for item in memberships] == [
        "T-1",
        "T-2",
    ]
    assert TransactionObservation.objects.count() == 2


def test_next_snapshot_replaces_membership_but_preserves_prior_evidence(
    tmp_path: Path,
) -> None:
    context = create_context(tmp_path)
    first_attempt = context.preview(
        HEADER + ledger_row("T-1") + ledger_row("T-2"),
        filename="first.csv",
    )
    first_revision = activation_service().activate(
        WorkspaceId(context.workspace.id),
        attempt_id=first_attempt.id,
    )
    first_memberships = list(
        DatasetMembership.objects.filter(dataset_revision=first_revision)
        .order_by("logical_transaction__source_record_key")
        .values_list(
            "logical_transaction__source_record_key",
            "observation__gross_amount",
        )
    )
    second_attempt = context.preview(
        HEADER + ledger_row("T-1", gross="110"),
        filename="correction.csv",
    )

    second_revision = activation_service().activate(
        WorkspaceId(context.workspace.id),
        attempt_id=second_attempt.id,
    )

    current_memberships = list(
        DatasetMembership.objects.filter(dataset_revision=second_revision).values_list(
            "logical_transaction__source_record_key",
            "observation__gross_amount",
        )
    )
    assert second_revision.parent_revision_id == first_revision.id
    assert first_memberships == [("T-1", Decimal("100")), ("T-2", Decimal("100"))]
    assert current_memberships == [("T-1", Decimal("110"))]
    assert DatasetMembership.objects.filter(dataset_revision=first_revision).count() == 2
    assert LogicalTransaction.objects.count() == 2
    assert TransactionObservation.objects.count() == 3


def test_cancelled_row_activates_as_visible_ineligible_evidence(tmp_path: Path) -> None:
    context = create_context(tmp_path)
    attempt = context.preview(
        HEADER + ledger_row("T-1", state="CANCELLED"),
        filename="cancelled.csv",
    )

    revision = activation_service().activate(
        WorkspaceId(context.workspace.id),
        attempt_id=attempt.id,
    )

    member = DatasetMembership.objects.select_related("observation").get(
        dataset_revision=revision
    )
    assert member.observation.state == "CANCELLED"
    assert member.observation.eligible_for_matching is False


def test_activated_attempt_cannot_publish_a_second_revision(tmp_path: Path) -> None:
    context = create_context(tmp_path)
    attempt = context.preview(HEADER + ledger_row("T-1"), filename="once.csv")
    activation_service().activate(
        WorkspaceId(context.workspace.id),
        attempt_id=attempt.id,
    )

    with pytest.raises(AttemptNotReady):
        activation_service().activate(
            WorkspaceId(context.workspace.id),
            attempt_id=attempt.id,
        )

    assert DatasetRevision.objects.count() == 1


def test_format_equivalent_current_state_becomes_no_change(tmp_path: Path) -> None:
    context = create_context(tmp_path)
    first = context.preview(HEADER + ledger_row("T-1"), filename="first.csv")
    first_revision = activation_service().activate(
        WorkspaceId(context.workspace.id),
        attempt_id=first.id,
    )
    reformatted = (
        HEADER
        + "T-1,2025-07-01T14:45:00+05:30,BTC-USD,BUY,1.000,100.00,100.0,SETTLED\n"
    )
    retry = context.preview(reformatted, filename="format-only.csv")

    result = activation_service().activate(
        WorkspaceId(context.workspace.id),
        attempt_id=retry.id,
    )

    context.dataset.refresh_from_db()
    retry.refresh_from_db()
    assert result is None
    assert retry.state == AttemptState.NO_CHANGE
    assert context.dataset.current_revision_id == first_revision.id
    assert DatasetRevision.objects.count() == 1
    assert TransactionObservation.objects.count() == 1


def test_historical_replay_does_not_roll_back_current_correction(tmp_path: Path) -> None:
    context = create_context(tmp_path)
    original = context.preview(HEADER + ledger_row("T-1"), filename="original.csv")
    original_revision = activation_service().activate(
        WorkspaceId(context.workspace.id),
        attempt_id=original.id,
    )
    correction = context.preview(
        HEADER + ledger_row("T-1", gross="110"),
        filename="correction.csv",
    )
    correction_revision = activation_service().activate(
        WorkspaceId(context.workspace.id),
        attempt_id=correction.id,
    )
    replay = context.preview(HEADER + ledger_row("T-1"), filename="original-again.csv")

    result = activation_service().activate(
        WorkspaceId(context.workspace.id),
        attempt_id=replay.id,
    )

    context.dataset.refresh_from_db()
    replay.refresh_from_db()
    current_amount = DatasetMembership.objects.get(
        dataset_revision=correction_revision
    ).observation.gross_amount
    assert result is None
    assert replay.state == AttemptState.REPLAYED
    assert context.dataset.current_revision_id == correction_revision.id
    assert current_amount == Decimal("110")
    assert DatasetRevision.objects.count() == 2
    assert DatasetMembership.objects.filter(
        dataset_revision=original_revision
    ).exists()


def test_explicit_reason_restores_historical_values_as_a_new_revision(
    tmp_path: Path,
) -> None:
    context = create_context(tmp_path)
    original = context.preview(HEADER + ledger_row("T-1"), filename="original.csv")
    original_revision = activation_service().activate(
        WorkspaceId(context.workspace.id),
        attempt_id=original.id,
    )
    correction = context.preview(
        HEADER + ledger_row("T-1", gross="110"),
        filename="correction.csv",
    )
    correction_revision = activation_service().activate(
        WorkspaceId(context.workspace.id),
        attempt_id=correction.id,
    )
    restore = context.preview(HEADER + ledger_row("T-1"), filename="restore.csv")

    restored_revision = activation_service().activate(
        WorkspaceId(context.workspace.id),
        attempt_id=restore.id,
        restore_reason="  Counterparty confirmed the original amount.  ",
    )

    context.dataset.refresh_from_db()
    restore.refresh_from_db()
    restored_member = DatasetMembership.objects.get(
        dataset_revision=restored_revision
    )
    assert context.dataset.current_revision_id == restored_revision.id
    assert restored_revision.parent_revision_id == correction_revision.id
    assert restored_revision.state_hash == original_revision.state_hash
    assert restored_member.observation.gross_amount == Decimal("100")
    assert restore.activation_reason == "Counterparty confirmed the original amount."
    assert DatasetRevision.objects.count() == 3
    assert TransactionObservation.objects.count() == 3


def test_blank_restore_reason_cannot_bypass_historical_replay_guard(
    tmp_path: Path,
) -> None:
    context = create_context(tmp_path)
    original = context.preview(HEADER + ledger_row("T-1"), filename="original.csv")
    activation_service().activate(
        WorkspaceId(context.workspace.id),
        attempt_id=original.id,
    )
    correction = context.preview(
        HEADER + ledger_row("T-1", gross="110"),
        filename="correction.csv",
    )
    activation_service().activate(
        WorkspaceId(context.workspace.id),
        attempt_id=correction.id,
    )
    restore = context.preview(HEADER + ledger_row("T-1"), filename="restore.csv")

    with pytest.raises(InvalidRestoreReason, match="blank"):
        activation_service().activate(
            WorkspaceId(context.workspace.id),
            attempt_id=restore.id,
            restore_reason="   ",
        )

    restore.refresh_from_db()
    assert restore.state == AttemptState.READY
    assert DatasetRevision.objects.count() == 2


def test_rejected_preview_cannot_activate_any_evidence(tmp_path: Path) -> None:
    context = create_context(tmp_path)
    attempt = context.preview(
        HEADER + ledger_row("T-1") + ledger_row("T-1"),
        filename="duplicate.csv",
    )

    with pytest.raises(AttemptNotReady):
        activation_service().activate(
            WorkspaceId(context.workspace.id),
            attempt_id=attempt.id,
        )

    context.dataset.refresh_from_db()
    assert context.dataset.current_revision_id is None
    assert not DatasetRevision.objects.exists()
    assert not TransactionObservation.objects.exists()


def test_injected_mid_activation_failure_rolls_back_every_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = create_context(tmp_path)
    attempt = context.preview(
        HEADER + ledger_row("T-1") + ledger_row("T-2"),
        filename="rollback.csv",
    )
    original = WorkspaceIngestionRepository.create_memberships

    def fail_after_memberships(self, **kwargs):
        original(self, **kwargs)
        raise RuntimeError("injected activation failure")

    monkeypatch.setattr(
        WorkspaceIngestionRepository,
        "create_memberships",
        fail_after_memberships,
    )
    with pytest.raises(RuntimeError, match="injected activation failure"):
        activation_service().activate(
            WorkspaceId(context.workspace.id),
            attempt_id=attempt.id,
        )

    context.dataset.refresh_from_db()
    attempt.refresh_from_db()
    assert context.dataset.current_revision_id is None
    assert attempt.state == AttemptState.READY
    assert not DatasetRevision.objects.exists()
    assert not DatasetMembership.objects.exists()
    assert not LogicalTransaction.objects.exists()
    assert not TransactionObservation.objects.exists()


def test_tampered_canonical_preview_is_refused_without_partial_state(
    tmp_path: Path,
) -> None:
    context = create_context(tmp_path)
    attempt = context.preview(HEADER + ledger_row("T-1"), filename="tampered.csv")
    raw_row = RawRow.objects.get(attempt=attempt)
    payload = {**raw_row.canonical_preview, "gross_amount": "not-a-decimal"}
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE raw_row SET canonical_preview = %s::jsonb WHERE id = %s",
            [json.dumps(payload), raw_row.id],
        )

    with pytest.raises(InvalidPreviewEvidence, match="incomplete canonical evidence"):
        activation_service().activate(
            WorkspaceId(context.workspace.id),
            attempt_id=attempt.id,
        )

    context.dataset.refresh_from_db()
    assert context.dataset.current_revision_id is None
    assert not DatasetRevision.objects.exists()
    assert not TransactionObservation.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_two_same_base_previews_allow_exactly_one_head_advance(
    tmp_path: Path,
) -> None:
    context = create_context(tmp_path)
    first = context.preview(HEADER + ledger_row("T-1"), filename="first.csv")
    second = context.preview(
        HEADER + ledger_row("T-1", gross="110"),
        filename="second.csv",
    )

    def activate(attempt_id):
        close_old_connections()
        try:
            revision = activation_service().activate(
                WorkspaceId(context.workspace.id),
                attempt_id=attempt_id,
            )
            return "activated", revision.id
        except StalePreview:
            return "stale", None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(activate, (first.id, second.id)))

    context.dataset.refresh_from_db()
    states = sorted(result[0] for result in results)
    assert states == ["activated", "stale"]
    assert DatasetRevision.objects.count() == 1
    assert context.dataset.current_revision_id is not None
    assert IngestionAttempt.objects.filter(state=AttemptState.ACTIVATED).count() == 1
    assert IngestionAttempt.objects.filter(state=AttemptState.READY).count() == 1


def test_delta_applies_upsert_cancel_retract_and_preserves_omission(
    tmp_path: Path,
) -> None:
    context = create_context(tmp_path)
    base_attempt = context.preview(
        HEADER
        + ledger_row("T-1")
        + ledger_row("T-2")
        + ledger_row("T-3")
        + ledger_row("T-4"),
        filename="base.csv",
    )
    base = activation_service().activate(
        WorkspaceId(context.workspace.id), attempt_id=base_attempt.id
    )
    enable_delta_contract(context)
    delta = context.preview(
        DELTA_HEADER
        + delta_row("T-1", "UPSERT", gross="125")
        + delta_row("T-2", "CANCEL", state="CANCELLED")
        + delta_row("T-3", "RETRACT"),
        filename="delta.csv",
    )

    revision = activation_service().activate(
        WorkspaceId(context.workspace.id), attempt_id=delta.id
    )

    assert revision.parent_revision_id == base.id
    members = {
        item.logical_transaction.source_record_key: item.observation
        for item in DatasetMembership.objects.filter(dataset_revision=revision)
        .select_related("logical_transaction", "observation")
    }
    assert set(members) == {"T-1", "T-2", "T-4"}
    assert members["T-1"].gross_amount == Decimal("125")
    assert members["T-2"].state == "CANCELLED"
    assert members["T-2"].eligible_for_matching is False
    assert members["T-4"].raw_row.attempt_id == base_attempt.id


def test_same_delta_semantics_resolve_to_different_base_sensitive_states(
    tmp_path: Path,
) -> None:
    contexts = [create_context(tmp_path / name) for name in ("first", "second")]
    base_rows = (("T-1", "T-4"), ("T-1", "T-5"))
    attempts = []
    revisions = []
    for context, keys in zip(contexts, base_rows, strict=True):
        base_attempt = context.preview(
            HEADER + "".join(ledger_row(key) for key in keys),
            filename="base.csv",
        )
        activation_service().activate(
            WorkspaceId(context.workspace.id), attempt_id=base_attempt.id
        )
        enable_delta_contract(context)
        attempt = context.preview(
            DELTA_HEADER + delta_row("T-1", "UPSERT", gross="125"),
            filename="delta.csv",
        )
        attempts.append(attempt)
        revisions.append(
            activation_service().activate(
                WorkspaceId(context.workspace.id), attempt_id=attempt.id
            )
        )

    assert attempts[0].semantic_hash == attempts[1].semantic_hash
    assert revisions[0].state_hash != revisions[1].state_hash


def test_delta_activation_refuses_a_changed_preview_base(tmp_path: Path) -> None:
    context = create_context(tmp_path)
    base_attempt = context.preview(HEADER + ledger_row("T-1"), filename="base.csv")
    activation_service().activate(
        WorkspaceId(context.workspace.id), attempt_id=base_attempt.id
    )
    enable_delta_contract(context)
    stale = context.preview(
        DELTA_HEADER + delta_row("T-1", "UPSERT", gross="110"),
        filename="stale.csv",
    )
    winner = context.preview(
        DELTA_HEADER + delta_row("T-1", "UPSERT", gross="120"),
        filename="winner.csv",
    )
    winner_revision = activation_service().activate(
        WorkspaceId(context.workspace.id), attempt_id=winner.id
    )

    with pytest.raises(StalePreview):
        activation_service().activate(
            WorkspaceId(context.workspace.id), attempt_id=stale.id
        )

    context.dataset.refresh_from_db()
    stale.refresh_from_db()
    assert context.dataset.current_revision_id == winner_revision.id
    assert stale.state == AttemptState.READY


def test_delta_failure_rolls_back_observations_revision_and_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = create_context(tmp_path)
    base_attempt = context.preview(HEADER + ledger_row("T-1"), filename="base.csv")
    base = activation_service().activate(
        WorkspaceId(context.workspace.id), attempt_id=base_attempt.id
    )
    enable_delta_contract(context)
    delta = context.preview(
        DELTA_HEADER + delta_row("T-1", "UPSERT", gross="125"),
        filename="delta.csv",
    )
    before_observations = TransactionObservation.objects.count()

    def fail_memberships(*args, **kwargs):
        raise RuntimeError("injected delta membership failure")

    monkeypatch.setattr(
        WorkspaceIngestionRepository, "create_memberships", fail_memberships
    )
    with pytest.raises(RuntimeError, match="injected delta membership failure"):
        activation_service().activate(
            WorkspaceId(context.workspace.id), attempt_id=delta.id
        )

    context.dataset.refresh_from_db()
    delta.refresh_from_db()
    assert context.dataset.current_revision_id == base.id
    assert delta.state == AttemptState.READY
    assert TransactionObservation.objects.count() == before_observations
    assert DatasetRevision.objects.filter(dataset=context.dataset).count() == 1
