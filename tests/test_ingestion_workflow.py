from __future__ import annotations

import re

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
import pytest

from books.models import ReconciliationBook
from ingestion.models import AttemptState, DatasetMembership, IngestionAttempt
from reconciliation.models import ReconciliationRun, RunPair
from workspaces.models import Workspace
from workspaces.sessions import digest_session_key


pytestmark = pytest.mark.django_db
LEDGER = (
    "trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
    "T-1001,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000,SETTLED\n"
)


def workspace_for(client: Client) -> Workspace:
    session_key = client.session.session_key
    assert session_key is not None
    return Workspace.objects.get(session_digest=digest_session_key(session_key))


def create_book(client: Client) -> ReconciliationBook:
    client.get("/")
    client.post("/books/demo")
    return ReconciliationBook.objects.get(workspace=workspace_for(client))


def upload(client: Client, url: str, payload: str, *, adapter="ledger", delimiter=","):
    return client.post(
        url,
        {
            "adapter": adapter,
            "delimiter": delimiter,
            "artifact": SimpleUploadedFile("source.csv", payload.encode(), content_type="text/csv"),
        },
    )


@override_settings(DEBUG=False)
def test_no_javascript_upload_preview_activate_and_history_journey(tmp_path) -> None:
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        client = Client()
        book = create_book(client)
        sources = client.get(f"/books/{book.id}/sources")
        assert sources.status_code == 200
        assert "Internal ledger" in sources.content.decode()
        assert "Counterparty" in sources.content.decode()
        assert "<script" not in sources.content.decode()

        uploaded = upload(client, f"/books/{book.id}/sources/left/upload", LEDGER)
        assert uploaded.status_code == 302
        assert uploaded.headers["Location"].endswith("/preview")
        preview = client.get(uploaded.headers["Location"])
        content = preview.content.decode()
        assert preview.status_code == 200
        assert "Raw and canonical rows" in content
        assert "T-1001" in content
        assert "31000" in content
        assert "Show field lineage" in content
        assert "Confirm and activate" in content
        assert "<script" not in content

        attempt = IngestionAttempt.objects.get(workspace=workspace_for(client))
        activated = client.post(f"/imports/{attempt.id}/activate", follow=True)
        attempt.refresh_from_db()
        assert activated.status_code == 200
        assert attempt.state == AttemptState.ACTIVATED
        assert "Dataset evidence published successfully" in activated.content.decode()
        assert "Download original CSV" in activated.content.decode()
        assert DatasetMembership.objects.filter(dataset_revision=attempt.activated_revision).count() == 1

        refreshed_sources = client.get(f"/books/{book.id}/sources")
        assert "Dataset active" in refreshed_sources.content.decode()
        assert "1 retained transactions" in refreshed_sources.content.decode()


def test_configurable_third_format_maps_to_canonical_preview(tmp_path) -> None:
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        client = Client()
        book = create_book(client)
        mapping = {
            "identity_namespace": "vendor-trade",
            "mode": "FULL_SNAPSHOT",
            "reference_semantics": "TRUSTED_SHARED",
            "timestamp_format": "%d/%m/%Y %H:%M",
            "timezone_name": "UTC",
            "source_record_key": "record_id",
            "business_reference": "record_id",
            "executed_at_utc": "when",
            "instrument": "asset",
            "side": "buy_sell",
            "quantity": "amount",
            "unit_price": "rate",
            "gross_amount": "value",
            "currency": "ccy",
            "state": "record_status",
            "buy_value": "Buy",
            "sell_value": "Sell",
            "settled_value": "Complete",
            "cancelled_value": "Void",
            "operation_field": "operation",
            "upsert_value": "UPSERT",
            "cancel_value": "CANCEL",
            "retract_value": "RETRACT",
        }
        saved = client.post(f"/books/{book.id}/sources/right/mapping", mapping)
        assert saved.status_code == 302
        assert saved.headers["Location"].endswith("/upload?mapping=saved")
        custom = (
            "record_id;when;asset;buy_sell;amount;rate;value;ccy;record_status\n"
            "T-1001;01/07/2025 09:15;BTC-USD;Buy;0.50;62000;31000;USD;Complete\n"
        )
        uploaded = upload(
            client,
            f"/books/{book.id}/sources/right/upload",
            custom,
            adapter="configurable",
            delimiter=";",
        )
        preview = client.get(uploaded.headers["Location"])
        content = preview.content.decode()
        assert preview.status_code == 200
        assert "semicolon" in content
        assert "2025-07-01T09:15:00.000000Z" in content
        assert "0.5" in content and "31000" in content
        assert "vendor-trade" not in content


def test_row_errors_are_visible_and_block_activation(tmp_path) -> None:
    invalid = LEDGER.replace(",BUY,", ",HOLD,").replace(",0.5,", ",NaN,")
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        client = Client()
        book = create_book(client)
        result = upload(client, f"/books/{book.id}/sources/left/upload", invalid)
        preview = client.get(result.headers["Location"])
        content = preview.content.decode()
        attempt = IngestionAttempt.objects.get(workspace=workspace_for(client))
        assert attempt.state == AttemptState.REJECTED
        assert 'class="row-error"' in content
        assert "UNKNOWN_ENUM" in content
        assert "NON_FINITE_DECIMAL" in content
        assert "Confirm and activate" not in content


def test_large_preview_is_paginated_and_query_bounded(
    tmp_path,
    django_assert_max_num_queries,
) -> None:
    rows = "".join(
        f"T-{number},2025-07-01T09:15:00Z,BTC-USD,BUY,1,100,100,SETTLED\n"
        for number in range(1, 62)
    )
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        client = Client()
        book = create_book(client)
        result = upload(client, f"/books/{book.id}/sources/left/upload", LEDGER.split("\n", 1)[0] + "\n" + rows)
        with django_assert_max_num_queries(12):
            page = client.get(result.headers["Location"] + "?page=2")
        content = page.content.decode()
        assert page.status_code == 200
        assert "Page 2 of 2" in content
        assert "Rows 51–61 of 61" in content
        assert "T-61" in content
        assert "T-1</dd>" not in content


def test_stale_activation_returns_recovery_action(tmp_path) -> None:
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        client = Client()
        book = create_book(client)
        first = upload(client, f"/books/{book.id}/sources/left/upload", LEDGER)
        first_attempt = IngestionAttempt.objects.get(workspace=workspace_for(client))
        second_payload = LEDGER.replace("31000", "31001")
        upload(client, f"/books/{book.id}/sources/left/upload", second_payload)
        second_attempt = IngestionAttempt.objects.exclude(id=first_attempt.id).get()
        client.post(f"/imports/{second_attempt.id}/activate")

        stale = client.post(f"/imports/{first_attempt.id}/activate")

        assert stale.status_code == 409
        assert "dataset changed after this preview" in stale.content.decode()
        assert "Create a fresh preview" in stale.content.decode()


def test_foreign_and_random_import_pages_are_indistinguishable(tmp_path) -> None:
    with override_settings(DEBUG=False, INGESTION_PRIVATE_ROOT=tmp_path):
        owner = Client()
        book = create_book(owner)
        upload(owner, f"/books/{book.id}/sources/left/upload", LEDGER)
        attempt = IngestionAttempt.objects.get(workspace=workspace_for(owner))
        outsider = Client()
        outsider.get("/")
        foreign = outsider.get(f"/imports/{attempt.id}/preview")
        random = outsider.get("/imports/00000000-0000-0000-0000-000000000001/preview")
        assert foreign.status_code == random.status_code == 404
        assert foreign.content == random.content


def test_preparation_styles_include_accessible_responsive_states() -> None:
    from django.conf import settings

    css = (settings.BASE_DIR / "foundation/static/foundation/workspace.css").read_text()
    assert ".table-scroll { overflow-x: auto" in css
    assert ".row-error" in css
    assert "@media (max-width: 620px)" in css
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css


def test_workbench_context_waits_for_both_sources_and_is_idempotent(tmp_path) -> None:
    from books.models import PolicyRevision, ReconciliationScope
    from reconciliation.domain import BookId, WorkspaceId
    from reconciliation.workbench import WorkbenchNotReady, WorkbenchService

    counterparty = (
        "reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
        "T-1001,2025-07-01 09:15:00,BTC-USD,B,0.5,62000,31000,SETTLED\n"
    )
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        client = Client()
        book = create_book(client)
        workspace = workspace_for(client)
        service = WorkbenchService(clock=lambda: workspace.created_at)
        initial = service.readiness(
            WorkspaceId(workspace.id), book_id=BookId(book.id)
        )
        assert initial.ready is False
        assert initial.missing_sides == ("LEFT", "RIGHT")
        with pytest.raises(WorkbenchNotReady):
            service.ensure_run_context(
                WorkspaceId(workspace.id), book_id=BookId(book.id)
            )

        left = upload(client, f"/books/{book.id}/sources/left/upload", LEDGER)
        client.post(f"/imports/{left.headers['Location'].split('/')[-2]}/activate")
        assert service.readiness(
            WorkspaceId(workspace.id), book_id=BookId(book.id)
        ).missing_sides == ("RIGHT",)

        right = upload(
            client,
            f"/books/{book.id}/sources/right/upload",
            counterparty,
            adapter="counterparty",
        )
        client.post(f"/imports/{right.headers['Location'].split('/')[-2]}/activate")
        ready = service.readiness(
            WorkspaceId(workspace.id), book_id=BookId(book.id)
        )
        assert ready.ready is True
        assert ready.missing_sides == ()

        first = service.ensure_run_context(
            WorkspaceId(workspace.id), book_id=BookId(book.id)
        )
        second = service.ensure_run_context(
            WorkspaceId(workspace.id), book_id=BookId(book.id)
        )
        assert first.id == second.id
        assert ReconciliationScope.objects.filter(book=book).count() == 1
        assert PolicyRevision.objects.filter(book=book).count() == 1


@override_settings(DEBUG=False)
def test_no_javascript_workbench_starts_run_and_shows_results(tmp_path) -> None:
    counterparty = (
        "reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
        "T-1001,2025-07-01 09:15:00,BTC-USD,B,0.5,62000,31000.20,SETTLED\n"
    )
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        client = Client()
        book = create_book(client)
        left = upload(client, f"/books/{book.id}/sources/left/upload", LEDGER)
        client.post(f"/imports/{left.headers['Location'].split('/')[-2]}/activate")
        right = upload(
            client,
            f"/books/{book.id}/sources/right/upload",
            counterparty,
            adapter="counterparty",
        )
        client.post(f"/imports/{right.headers['Location'].split('/')[-2]}/activate")

        ready = client.get(f"/books/{book.id}/workbench")
        assert ready.status_code == 200
        assert "Sources are ready to reconcile" in ready.content.decode()
        assert "Start reconciliation" in ready.content.decode()
        assert "<script" not in ready.content.decode()

        started = client.post(f"/books/{book.id}/runs", follow=True)
        content = started.content.decode()
        assert started.status_code == 200
        assert "Reconciliation completed" in content
        assert "Pairs" in content
        assert "Current review" in content
        assert "Current run" in content
        assert "Run again" in content


@override_settings(DEBUG=False)
def test_workbench_routes_hide_foreign_and_absent_books() -> None:
    owner = Client()
    book = create_book(owner)
    outsider = Client()
    create_book(outsider)
    foreign = outsider.get(f"/books/{book.id}/workbench")
    absent = outsider.get("/books/00000000-0000-0000-0000-000000000001/workbench")
    assert foreign.status_code == absent.status_code == 404
    assert foreign.content == absent.content


def test_run_start_requires_csrf() -> None:
    setup = Client()
    book = create_book(setup)
    client = Client(enforce_csrf_checks=True)
    client.cookies = setup.cookies
    response = client.post(f"/books/{book.id}/runs")
    assert response.status_code == 403


@override_settings(DEBUG=False)
def test_case_detail_exposes_side_by_side_evidence_and_history(tmp_path) -> None:
    counterparty = (
        "reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
        "T-1001,2025-07-01 09:15:00,BTC-USD,B,0.5,62000,31000.20,SETTLED\n"
    )
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        client = Client()
        book = create_book(client)
        left = upload(client, f"/books/{book.id}/sources/left/upload", LEDGER)
        client.post(f"/imports/{left.headers['Location'].split('/')[-2]}/activate")
        right = upload(
            client,
            f"/books/{book.id}/sources/right/upload",
            counterparty,
            adapter="counterparty",
        )
        client.post(f"/imports/{right.headers['Location'].split('/')[-2]}/activate")

        result = client.post(f"/books/{book.id}/runs", follow=True)
        match = re.search(r"/cases/([0-9a-f-]{36})", result.content.decode())
        assert match is not None

        detail = client.get(f"/books/{book.id}/cases/{match.group(1)}")
        content = detail.content.decode()
        assert detail.status_code == 200
        assert "Raw and canonical values" in content
        assert "Field differences and tolerances" in content
        assert "Occurrence history" in content
        assert "Policy digest" in content
        assert "T-1001" in content
        assert "<script" not in content


@override_settings(DEBUG=False)
def test_case_detail_manual_link_requires_reason_and_marks_rerun_pending(tmp_path) -> None:
    counterparty = (
        "reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
        "T-2001,2025-07-01 09:15:00,BTC-USD,B,100,10,1000,SETTLED\n"
    )
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        client = Client()
        book = create_book(client)
        left = upload(client, f"/books/{book.id}/sources/left/upload", LEDGER)
        client.post(f"/imports/{left.headers['Location'].split('/')[-2]}/activate")
        right = upload(
            client,
            f"/books/{book.id}/sources/right/upload",
            counterparty,
            adapter="counterparty",
        )
        client.post(f"/imports/{right.headers['Location'].split('/')[-2]}/activate")

        result = client.post(f"/books/{book.id}/runs", follow=True)
        match = re.search(r"/cases/([0-9a-f-]{36})", result.content.decode())
        assert match is not None
        detail = client.get(f"/books/{book.id}/cases/{match.group(1)}")
        content = detail.content.decode()
        option = re.search(r'<option value="([^"]+)">', content)
        assert option is not None, content

        rejected = client.post(
            f"/books/{book.id}/cases/{match.group(1)}/link",
            {"partner_logical_id": option.group(1)},
        )
        assert rejected.status_code == 400
        assert "provide a reason" in rejected.content.decode()

        linked = client.post(
            f"/books/{book.id}/cases/{match.group(1)}/link",
            {"partner_logical_id": option.group(1), "reason": "Confirmed by settlement ledger."},
            follow=True,
        )
        assert linked.status_code == 200
        assert "Manual link saved" in linked.content.decode()
        pending = client.get(f"/books/{book.id}/workbench")
        assert "Changes are waiting for a rerun" in pending.content.decode()
        assert ReconciliationRun.objects.filter(scope__book=book).count() == 1
        rerun = client.post(f"/books/{book.id}/runs", follow=True)
        assert rerun.status_code == 200
        latest = ReconciliationRun.objects.filter(scope__book=book).order_by("-created_at").first()
        assert latest is not None
        assert RunPair.objects.filter(run=latest, origin="MANUAL").exists()
        history = client.get(f"/books/{book.id}/workbench")
        assert "Historical run" in history.content.decode()
