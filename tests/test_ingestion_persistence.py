from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from django.db import IntegrityError, connection, transaction

from books.models import BookKind, ReconciliationBook
from ingestion.models import (
    AttemptState,
    Dataset,
    DatasetMembership,
    DatasetRevision,
    FileArtifact,
    IngestionAttempt,
    LogicalTransaction,
    RawRow,
    TransactionObservation,
)
from ingestion.repositories import (
    IngestionResourceUnavailable,
    WorkspaceIngestionRepository,
)
from reconciliation.domain import BookId, DatasetMode, ReferenceSemantics, WorkspaceId
from sources.models import (
    BookSource,
    ImmutableEvidenceError,
    MappingRevision,
    SourceContractRevision,
    SourceRole,
    SourceSystem,
)
from sources.repositories import SourceUnavailable, WorkspaceSourceRepository
from workspaces.models import Workspace


pytestmark = pytest.mark.django_db
NOW = datetime(2026, 9, 6, 8, tzinfo=UTC)


def create_workspace() -> Workspace:
    return Workspace.objects.create(
        session_digest=uuid4().hex * 2,
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )


def create_book(workspace: Workspace, name: str = "August close") -> ReconciliationBook:
    return ReconciliationBook.objects.create(
        workspace=workspace,
        name=name,
        kind=BookKind.USER,
        created_at=NOW,
    )


def create_source_graph(workspace: Workspace, book: ReconciliationBook) -> dict[str, object]:
    source_repository = WorkspaceSourceRepository(WorkspaceId(workspace.id))
    ingestion_repository = WorkspaceIngestionRepository(WorkspaceId(workspace.id))
    source = source_repository.create_source(
        name="Internal ledger",
        adapter_key="ledger-v1",
        created_at=NOW,
    )
    book_source = source_repository.assign_book_source(
        book_id=BookId(book.id),
        source_id=source.id,
        role=SourceRole.LEFT,
        identity_namespace="ledger-trade",
        created_at=NOW,
    )
    mapping = source_repository.create_mapping_revision(
        source_id=source.id,
        revision=1,
        mapping={"source_record_key": "trade_id"},
        parser_version="1",
        digest="a" * 64,
        created_at=NOW,
    )
    contract = source_repository.create_contract_revision(
        source_id=source.id,
        mapping_revision_id=mapping.id,
        revision=1,
        mode=DatasetMode.FULL_SNAPSHOT,
        timezone_name="UTC",
        identity_namespace="ledger-trade",
        reference_semantics=ReferenceSemantics.TRUSTED_SHARED,
        contract={"timestamp_format": "ISO8601", "currency": "USD"},
        digest="b" * 64,
        created_at=NOW,
    )
    dataset = ingestion_repository.create_dataset(
        book_source_id=book_source.id,
        coverage_key="2025-07",
        created_at=NOW,
    )
    artifact = ingestion_repository.create_artifact(
        storage_key=f"private/{workspace.id}/{uuid4()}",
        physical_hash="c" * 64,
        original_filename="ledger.csv",
        content_type="text/csv",
        byte_size=128,
        created_at=NOW,
    )
    attempt = ingestion_repository.create_attempt(
        artifact_id=artifact.id,
        dataset_id=dataset.id,
        contract_revision_id=contract.id,
        expected_base_id=None,
        state=AttemptState.READY,
        physical_hash=artifact.physical_hash,
        semantic_hash="d" * 64,
        delimiter=",",
        row_count=1,
        error_count=0,
        created_at=NOW,
        completed_at=NOW,
    )
    raw_row = ingestion_repository.create_raw_row(
        attempt_id=attempt.id,
        row_number=2,
        raw_values={"trade_id": {"kind": "VALUE", "original": "T-1001"}},
        canonical_preview={"source_record_key": "T-1001"},
        validation=[],
    )
    logical = ingestion_repository.create_logical_transaction(
        book_source_id=book_source.id,
        source_record_key="T-1001",
        created_at=NOW,
    )
    observation = ingestion_repository.create_observation(
        logical_transaction_id=logical.id,
        raw_row_id=raw_row.id,
        business_reference="T-1001",
        executed_at_utc=datetime(2025, 7, 1, 9, 15, tzinfo=UTC),
        instrument="BTC-USD",
        side="BUY",
        quantity=Decimal("0.500000000000"),
        unit_price=Decimal("62000.000000000000"),
        gross_amount=Decimal("31000.000000000000"),
        currency="USD",
        state="SETTLED",
        eligible_for_matching=True,
        provenance={"source_record_key": {"column": "trade_id"}},
        fingerprint="e" * 64,
        created_at=NOW,
    )
    revision = ingestion_repository.create_revision(
        dataset_id=dataset.id,
        attempt_id=attempt.id,
        parent_revision_id=None,
        state_hash="f" * 64,
        created_at=NOW,
    )
    membership = ingestion_repository.create_membership(
        revision_id=revision.id,
        logical_transaction_id=logical.id,
        observation_id=observation.id,
    )
    Dataset.objects.filter(id=dataset.id).update(current_revision=revision)
    dataset.refresh_from_db()
    return {
        "source": source,
        "book_source": book_source,
        "mapping": mapping,
        "contract": contract,
        "dataset": dataset,
        "artifact": artifact,
        "attempt": attempt,
        "raw_row": raw_row,
        "logical": logical,
        "observation": observation,
        "revision": revision,
        "membership": membership,
    }


def test_complete_ingestion_graph_is_workspace_owned_and_linked() -> None:
    workspace = create_workspace()
    graph = create_source_graph(workspace, create_book(workspace))

    assert graph["dataset"].current_revision_id == graph["revision"].id
    assert graph["membership"].observation_id == graph["observation"].id
    assert graph["observation"].logical_transaction_id == graph["logical"].id
    assert graph["raw_row"].attempt_id == graph["attempt"].id
    assert {value.workspace_id for value in graph.values()} == {workspace.id}


def test_owner_can_resolve_every_source_and_ingestion_resource() -> None:
    workspace = create_workspace()
    graph = create_source_graph(workspace, create_book(workspace))
    source_repository = WorkspaceSourceRepository(WorkspaceId(workspace.id))
    ingestion_repository = WorkspaceIngestionRepository(WorkspaceId(workspace.id))

    assert source_repository.get_source(graph["source"].id).id == graph["source"].id
    assert source_repository.get_book_source(graph["book_source"].id).id == graph["book_source"].id
    assert source_repository.get_mapping(graph["mapping"].id).id == graph["mapping"].id
    assert source_repository.get_contract(graph["contract"].id).id == graph["contract"].id
    assert ingestion_repository.get_dataset(graph["dataset"].id).id == graph["dataset"].id
    assert ingestion_repository.get_artifact(graph["artifact"].id).id == graph["artifact"].id
    assert ingestion_repository.get_attempt(graph["attempt"].id).id == graph["attempt"].id
    assert ingestion_repository.get_raw_row(graph["raw_row"].id).id == graph["raw_row"].id
    assert ingestion_repository.get_logical_transaction(graph["logical"].id).id == graph["logical"].id
    assert ingestion_repository.get_observation(graph["observation"].id).id == graph["observation"].id
    assert ingestion_repository.get_revision(graph["revision"].id).id == graph["revision"].id
    assert ingestion_repository.get_membership(graph["membership"].id).id == graph["membership"].id


def test_foreign_and_random_ids_have_identical_repository_failures() -> None:
    owner = create_workspace()
    outsider = create_workspace()
    graph = create_source_graph(owner, create_book(owner))
    source_repository = WorkspaceSourceRepository(WorkspaceId(outsider.id))
    ingestion_repository = WorkspaceIngestionRepository(WorkspaceId(outsider.id))

    source_calls = (
        lambda value: source_repository.get_source(value),
        lambda value: source_repository.get_book_source(value),
        lambda value: source_repository.get_mapping(value),
        lambda value: source_repository.get_contract(value),
    )
    ingestion_calls = (
        lambda value: ingestion_repository.get_dataset(value),
        lambda value: ingestion_repository.get_artifact(value),
        lambda value: ingestion_repository.get_attempt(value),
        lambda value: ingestion_repository.get_raw_row(value),
        lambda value: ingestion_repository.get_logical_transaction(value),
        lambda value: ingestion_repository.get_observation(value),
        lambda value: ingestion_repository.get_revision(value),
    )
    for call, key in zip(source_calls, ("source", "book_source", "mapping", "contract"), strict=True):
        for identifier in (graph[key].id, uuid4()):
            with pytest.raises(SourceUnavailable):
                call(identifier)
    for call, key in zip(
        ingestion_calls,
        ("dataset", "artifact", "attempt", "raw_row", "logical", "observation", "revision"),
        strict=True,
    ):
        for identifier in (graph[key].id, uuid4()):
            with pytest.raises(IngestionResourceUnavailable):
                call(identifier)
    for identifier in (graph["membership"].id, graph["membership"].id + 1000):
        with pytest.raises(IngestionResourceUnavailable):
            ingestion_repository.get_membership(identifier)


def test_relationship_factories_refuse_cross_workspace_parents() -> None:
    first = create_workspace()
    second = create_workspace()
    first_book = create_book(first)
    second_book = create_book(second)
    first_source = SourceSystem.objects.create(
        workspace=first, name="First", adapter_key="ledger-v1", created_at=NOW
    )

    with pytest.raises(SourceUnavailable):
        WorkspaceSourceRepository(WorkspaceId(second.id)).assign_book_source(
            book_id=BookId(second_book.id),
            source_id=first_source.id,
            role=SourceRole.LEFT,
            identity_namespace="first",
            created_at=NOW,
        )
    first_book_source = WorkspaceSourceRepository(WorkspaceId(first.id)).assign_book_source(
        book_id=BookId(first_book.id),
        source_id=first_source.id,
        role=SourceRole.LEFT,
        identity_namespace="first",
        created_at=NOW,
    )
    with pytest.raises(IngestionResourceUnavailable):
        WorkspaceIngestionRepository(WorkspaceId(second.id)).create_dataset(
            book_source_id=first_book_source.id,
            coverage_key="2025-07",
            created_at=NOW,
        )
    assert BookSource.objects.count() == 1
    assert Dataset.objects.count() == 0


def test_all_repository_factories_refuse_foreign_parent_ids() -> None:
    owner = create_workspace()
    outsider = create_workspace()
    graph = create_source_graph(owner, create_book(owner))
    source_repository = WorkspaceSourceRepository(WorkspaceId(outsider.id))
    ingestion_repository = WorkspaceIngestionRepository(WorkspaceId(outsider.id))

    with pytest.raises(SourceUnavailable):
        source_repository.create_mapping_revision(
            source_id=graph["source"].id,
            revision=2,
            mapping={},
            parser_version="1",
            digest="1" * 64,
            created_at=NOW,
        )
    with pytest.raises(SourceUnavailable):
        source_repository.create_contract_revision(
            source_id=graph["source"].id,
            mapping_revision_id=graph["mapping"].id,
            revision=2,
            mode=DatasetMode.FULL_SNAPSHOT,
            timezone_name="UTC",
            identity_namespace="foreign",
            reference_semantics=ReferenceSemantics.NONE,
            contract={},
            digest="2" * 64,
            created_at=NOW,
        )
    with pytest.raises(IngestionResourceUnavailable):
        ingestion_repository.create_attempt(
            artifact_id=graph["artifact"].id,
            dataset_id=graph["dataset"].id,
            contract_revision_id=graph["contract"].id,
            expected_base_id=None,
            state=AttemptState.RECEIVED,
            physical_hash="3" * 64,
            semantic_hash=None,
            delimiter=",",
            row_count=0,
            error_count=0,
            created_at=NOW,
            completed_at=None,
        )
    with pytest.raises(IngestionResourceUnavailable):
        ingestion_repository.create_raw_row(
            attempt_id=graph["attempt"].id,
            row_number=3,
            raw_values={},
            canonical_preview=None,
            validation=[],
        )
    with pytest.raises(IngestionResourceUnavailable):
        ingestion_repository.create_logical_transaction(
            book_source_id=graph["book_source"].id,
            source_record_key="foreign",
            created_at=NOW,
        )
    with pytest.raises(IngestionResourceUnavailable):
        ingestion_repository.create_observation(
            logical_transaction_id=graph["logical"].id,
            raw_row_id=graph["raw_row"].id,
            business_reference=None,
            executed_at_utc=NOW,
            instrument="BTC-USD",
            side="BUY",
            quantity=Decimal("1"),
            unit_price=Decimal("1"),
            gross_amount=Decimal("1"),
            currency="USD",
            state="SETTLED",
            eligible_for_matching=True,
            provenance={},
            fingerprint="4" * 64,
            created_at=NOW,
        )
    with pytest.raises(IngestionResourceUnavailable):
        ingestion_repository.create_revision(
            dataset_id=graph["dataset"].id,
            attempt_id=graph["attempt"].id,
            parent_revision_id=None,
            state_hash="5" * 64,
            created_at=NOW,
        )


def test_repository_factories_refuse_inconsistent_same_workspace_graphs() -> None:
    workspace = create_workspace()
    first = create_source_graph(workspace, create_book(workspace, "First"))
    second = create_source_graph(workspace, create_book(workspace, "Second"))
    source_repository = WorkspaceSourceRepository(WorkspaceId(workspace.id))
    ingestion_repository = WorkspaceIngestionRepository(WorkspaceId(workspace.id))

    with pytest.raises(SourceUnavailable):
        source_repository.create_contract_revision(
            source_id=first["source"].id,
            mapping_revision_id=second["mapping"].id,
            revision=2,
            mode=DatasetMode.FULL_SNAPSHOT,
            timezone_name="UTC",
            identity_namespace="mismatch",
            reference_semantics=ReferenceSemantics.NONE,
            contract={},
            digest="6" * 64,
            created_at=NOW,
        )
    with pytest.raises(IngestionResourceUnavailable):
        ingestion_repository.create_attempt(
            artifact_id=first["artifact"].id,
            dataset_id=first["dataset"].id,
            contract_revision_id=second["contract"].id,
            expected_base_id=None,
            state=AttemptState.RECEIVED,
            physical_hash="7" * 64,
            semantic_hash=None,
            delimiter=",",
            row_count=0,
            error_count=0,
            created_at=NOW,
            completed_at=None,
        )
    with pytest.raises(IngestionResourceUnavailable):
        ingestion_repository.create_attempt(
            artifact_id=first["artifact"].id,
            dataset_id=first["dataset"].id,
            contract_revision_id=first["contract"].id,
            expected_base_id=second["revision"].id,
            state=AttemptState.RECEIVED,
            physical_hash="8" * 64,
            semantic_hash=None,
            delimiter=",",
            row_count=0,
            error_count=0,
            created_at=NOW,
            completed_at=None,
        )
    with pytest.raises(IngestionResourceUnavailable):
        ingestion_repository.create_observation(
            logical_transaction_id=first["logical"].id,
            raw_row_id=second["raw_row"].id,
            business_reference=None,
            executed_at_utc=NOW,
            instrument="BTC-USD",
            side="BUY",
            quantity=Decimal("1"),
            unit_price=Decimal("1"),
            gross_amount=Decimal("1"),
            currency="USD",
            state="SETTLED",
            eligible_for_matching=True,
            provenance={},
            fingerprint="9" * 64,
            created_at=NOW,
        )
    with pytest.raises(IngestionResourceUnavailable):
        ingestion_repository.create_revision(
            dataset_id=first["dataset"].id,
            attempt_id=second["attempt"].id,
            parent_revision_id=None,
            state_hash="0" * 64,
            created_at=NOW,
        )
    with pytest.raises(IngestionResourceUnavailable):
        ingestion_repository.create_revision(
            dataset_id=first["dataset"].id,
            attempt_id=first["attempt"].id,
            parent_revision_id=second["revision"].id,
            state_hash="0" * 64,
            created_at=NOW,
        )


def test_membership_factory_refuses_mismatched_logical_or_observation() -> None:
    workspace = create_workspace()
    book = create_book(workspace)
    first = create_source_graph(workspace, book)
    second_source = SourceSystem.objects.create(
        workspace=workspace, name="Other", adapter_key="counterparty-v1", created_at=NOW
    )
    second_book_source = WorkspaceSourceRepository(WorkspaceId(workspace.id)).assign_book_source(
        book_id=BookId(book.id), source_id=second_source.id, role=SourceRole.RIGHT,
        identity_namespace="counterparty", created_at=NOW,
    )
    other_logical = LogicalTransaction.objects.create(
        workspace=workspace, book_source=second_book_source,
        source_record_key="C-9001", created_at=NOW,
    )
    repository = WorkspaceIngestionRepository(WorkspaceId(workspace.id))

    with pytest.raises(IngestionResourceUnavailable):
        repository.create_membership(
            revision_id=first["revision"].id,
            logical_transaction_id=other_logical.id,
            observation_id=first["observation"].id,
        )


@pytest.mark.parametrize("key", ["mapping", "contract", "artifact", "raw_row", "logical", "observation", "revision", "membership"])
def test_evidence_models_refuse_update_and_instance_delete(key: str) -> None:
    workspace = create_workspace()
    value = create_source_graph(workspace, create_book(workspace))[key]

    with pytest.raises(ImmutableEvidenceError):
        value.save()
    with pytest.raises(ImmutableEvidenceError):
        value.delete()
    with pytest.raises(ImmutableEvidenceError):
        type(value).objects.filter(id=value.id).update(workspace_id=workspace.id)
    with pytest.raises(ImmutableEvidenceError):
        type(value).objects.filter(id=value.id).delete()


def test_database_enforces_core_revision_and_membership_uniqueness() -> None:
    workspace = create_workspace()
    graph = create_source_graph(workspace, create_book(workspace))

    with pytest.raises(IntegrityError), transaction.atomic():
        MappingRevision.objects.create(
            workspace=workspace,
            source=graph["source"],
            revision=1,
            mapping={}, parser_version="1", digest="1" * 64, created_at=NOW,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        RawRow.objects.create(
            workspace=workspace,
            attempt=graph["attempt"],
            row_number=2,
            raw_values={}, validation=[],
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        DatasetMembership.objects.create(
            workspace=workspace,
            dataset_revision=graph["revision"],
            logical_transaction=graph["logical"],
            observation=graph["observation"],
        )


def test_database_enforces_choice_and_cancellation_invariants() -> None:
    workspace = create_workspace()
    graph = create_source_graph(workspace, create_book(workspace))

    with pytest.raises(IntegrityError), transaction.atomic():
        BookSource.objects.filter(id=graph["book_source"].id).update(role="OTHER")
    with pytest.raises(IntegrityError), transaction.atomic():
        IngestionAttempt.objects.filter(id=graph["attempt"].id).update(state="UNKNOWN")
    with pytest.raises(IntegrityError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE transaction_observation
                SET state = %s, eligible_for_matching = %s
                WHERE id = %s
                """,
                ["CANCELLED", True, graph["observation"].id],
            )


def test_ingestion_schema_contains_workspace_and_candidate_indexes() -> None:
    with connection.cursor() as cursor:
        observation_constraints = connection.introspection.get_constraints(
            cursor, "transaction_observation"
        )
        membership_constraints = connection.introspection.get_constraints(
            cursor, "dataset_membership"
        )

    assert observation_constraints["obs_ws_logical_idx"]["index"] is True
    assert observation_constraints["observation_candidate_idx"]["index"] is True
    assert membership_constraints["membership_ws_revision_idx"]["index"] is True
    assert membership_constraints["membership_revision_logical_unique"]["unique"] is True


def test_candidate_input_boundary_excludes_cancelled_memberships() -> None:
    workspace = create_workspace()
    graph = create_source_graph(workspace, create_book(workspace))
    repository = WorkspaceIngestionRepository(WorkspaceId(workspace.id))
    cancelled_raw = repository.create_raw_row(
        attempt_id=graph["attempt"].id,
        row_number=3,
        raw_values={"trade_id": {"kind": "VALUE", "original": "T-1002"}},
        canonical_preview={"source_record_key": "T-1002"},
        validation=[],
    )
    cancelled_logical = repository.create_logical_transaction(
        book_source_id=graph["book_source"].id,
        source_record_key="T-1002",
        created_at=NOW,
    )
    cancelled = repository.create_observation(
        logical_transaction_id=cancelled_logical.id,
        raw_row_id=cancelled_raw.id,
        business_reference="T-1002",
        executed_at_utc=NOW,
        instrument="BTC-USD",
        side="BUY",
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
        gross_amount=Decimal("100"),
        currency="USD",
        state="CANCELLED",
        eligible_for_matching=False,
        provenance={},
        fingerprint="1" * 64,
        created_at=NOW,
    )
    repository.create_membership(
        revision_id=graph["revision"].id,
        logical_transaction_id=cancelled_logical.id,
        observation_id=cancelled.id,
    )

    eligible = repository.list_eligible_memberships(graph["revision"].id)

    assert [item.observation_id for item in eligible] == [graph["observation"].id]
    assert TransactionObservation.objects.filter(id=cancelled.id).exists()


def test_candidate_input_boundary_hides_foreign_and_random_revisions() -> None:
    owner = create_workspace()
    outsider = create_workspace()
    graph = create_source_graph(owner, create_book(owner))
    repository = WorkspaceIngestionRepository(WorkspaceId(outsider.id))

    for revision_id in (graph["revision"].id, uuid4()):
        with pytest.raises(IngestionResourceUnavailable):
            repository.list_eligible_memberships(revision_id)
