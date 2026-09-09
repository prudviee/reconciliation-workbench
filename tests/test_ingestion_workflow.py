from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
import pytest

from books.models import ReconciliationBook
from ingestion.models import AttemptState, DatasetMembership, IngestionAttempt
from reconciliation.models import ReconciliationRun, RunPair, RunUnpaired
from resolutions.models import Decision
from workspaces.models import Workspace
from workspaces.sessions import digest_session_key


pytestmark = pytest.mark.django_db
LEDGER = (
    "trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
    "T-1001,2025-07-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000,SETTLED\n"
)
DEMO_ROOT = Path(__file__).resolve().parents[1] / "demo"


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
        assert "2025-07-01 09:15:00 UTC" in content
        assert "(allowed 1 min)" in content
        assert "timedelta_microseconds" not in content
        assert "&#x27;decimal&#x27;" not in content
        assert "&#x27;datetime&#x27;" not in content
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
        option = re.search(r'name="partner_logical_id" value="([^"]+)"', content)
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
        assert "Save manual link" not in linked.content.decode()
        assert "Accept unmatched record" not in linked.content.decode()
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


@override_settings(DEBUG=False)
def test_case_detail_accepts_genuinely_unmatched_with_reason_and_rerun(tmp_path) -> None:
    ledger = (DEMO_ROOT / "atlas-ledger.csv").read_text(encoding="utf-8")
    counterparty = (DEMO_ROOT / "atlas-counterparty.csv").read_text(
        encoding="utf-8"
    )
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        client = Client()
        book = create_book(client)
        left = upload(client, f"/books/{book.id}/sources/left/upload", ledger)
        client.post(f"/imports/{left.headers['Location'].split('/')[-2]}/activate")
        right = upload(
            client,
            f"/books/{book.id}/sources/right/upload",
            counterparty,
            adapter="counterparty",
        )
        client.post(f"/imports/{right.headers['Location'].split('/')[-2]}/activate")

        first_page = client.post(f"/books/{book.id}/runs", follow=True)
        unmatched_case = None
        for case_id in re.findall(
            r"/cases/([0-9a-f-]{36})", first_page.content.decode()
        ):
            detail = client.get(f"/books/{book.id}/cases/{case_id}")
            if "TX-1003 · left" in detail.content.decode():
                unmatched_case = case_id
                assert "Accept as genuinely unmatched" in detail.content.decode()
                break
        assert unmatched_case is not None

        missing_reason = client.post(
            f"/books/{book.id}/cases/{unmatched_case}/accept-unmatched"
        )
        assert missing_reason.status_code == 400
        assert "Provide a reason" in missing_reason.content.decode()

        accepted = client.post(
            f"/books/{book.id}/cases/{unmatched_case}/accept-unmatched",
            {"reason": "Confirmed as an internal-only transaction."},
            follow=True,
        )
        assert accepted.status_code == 200
        assert "Unmatched decision saved" in accepted.content.decode()
        assert "Accept as genuinely unmatched" not in accepted.content.decode()
        assert "Save manual link" not in accepted.content.decode()
        pending = client.get(f"/books/{book.id}/workbench")
        assert "Changes are waiting for a rerun" in pending.content.decode()

        rerun = client.post(f"/books/{book.id}/runs", follow=True)
        assert rerun.status_code == 200
        latest = (
            ReconciliationRun.objects.filter(scope__book=book)
            .order_by("-created_at")
            .first()
        )
        assert latest is not None
        assert RunUnpaired.objects.filter(
            run=latest, reason="ACCEPTED_UNMATCHED"
        ).exists()
        current_detail = client.get(
            f"/books/{book.id}/cases/{unmatched_case}"
        ).content.decode()
        assert "unchanged" in current_detail
        assert "Saved decisions" in current_detail
        assert "Accept as genuinely unmatched" not in current_detail

        decision = Decision.objects.get(
            book=book,
            current_revision__authority_kind="ACCEPT_UNMATCHED",
        )
        decision_url = f"/books/{book.id}/decisions/{decision.id}"
        decision_page = client.get(decision_url)
        decision_content = decision_page.content.decode()
        assert decision_page.status_code == 200
        assert "Affected identities and current reason" in decision_content
        assert "TX-1003" in decision_content
        assert "Confirmed as an internal-only transaction" in decision_content
        assert "Revoke decision" in decision_content

        outsider = Client()
        outsider.get("/")
        foreign = outsider.get(decision_url)
        absent = client.get(f"/books/{book.id}/decisions/{uuid4()}")
        assert foreign.status_code == absent.status_code == 404
        assert foreign.content == absent.content

        missing_reason = client.post(decision_url)
        assert missing_reason.status_code == 400
        decision.refresh_from_db()
        assert decision.current_revision.action == "ACCEPT_UNMATCHED"

        revoked = client.post(
            decision_url,
            {"reason": "The source owner supplied a replacement settlement record."},
            follow=True,
        )
        revoked_content = revoked.content.decode()
        assert revoked.status_code == 200
        assert "Decision revoked" in revoked_content
        assert "inactive" in revoked_content
        assert "Authority released" in revoked_content
        assert "The source owner supplied a replacement settlement record" in revoked_content
        assert "Revoke decision" not in revoked_content
        decision.refresh_from_db()
        assert decision.current_revision.action == "REVOKE"
        assert not decision.current_revision.active_claims.exists()
        revoked_case = client.get(
            f"/books/{book.id}/cases/{unmatched_case}"
        ).content.decode()
        assert "revoke · revision 2 · inactive" in revoked_case
        assert "Review decision history" in revoked_case
        assert "Changes are waiting for a rerun" in client.get(
            f"/books/{book.id}/workbench"
        ).content.decode()


@override_settings(DEBUG=False)
def test_decision_replacement_previews_and_supersedes_every_authority(tmp_path) -> None:
    ledger = (DEMO_ROOT / "atlas-ledger.csv").read_text(encoding="utf-8")
    counterparty = (DEMO_ROOT / "atlas-counterparty.csv").read_text(
        encoding="utf-8"
    )
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        client = Client()
        book = create_book(client)
        left = upload(client, f"/books/{book.id}/sources/left/upload", ledger)
        client.post(f"/imports/{left.headers['Location'].split('/')[-2]}/activate")
        right = upload(
            client,
            f"/books/{book.id}/sources/right/upload",
            counterparty,
            adapter="counterparty",
        )
        client.post(f"/imports/{right.headers['Location'].split('/')[-2]}/activate")
        first_page = client.post(f"/books/{book.id}/runs", follow=True)

        cases = {}
        for case_id in re.findall(
            r"/cases/([0-9a-f-]{36})", first_page.content.decode()
        ):
            detail = client.get(f"/books/{book.id}/cases/{case_id}").content.decode()
            if "TX-1003 · left" in detail:
                cases["left"] = case_id
            elif "CP-9003 · right" in detail:
                cases["right"] = case_id
        assert set(cases) == {"left", "right"}

        client.post(
            f"/books/{book.id}/cases/{cases['left']}/accept-unmatched",
            {"reason": "Ledger owner confirmed no external settlement."},
        )
        client.post(f"/books/{book.id}/runs")
        client.post(
            f"/books/{book.id}/cases/{cases['right']}/accept-unmatched",
            {"reason": "Counterparty owner confirmed an orphan statement row."},
        )
        client.post(f"/books/{book.id}/runs")

        target = Decision.objects.get(
            book=book,
            current_revision__record_logical__source_record_key="TX-1003",
        )
        conflicting = Decision.objects.get(
            book=book,
            current_revision__record_logical__source_record_key="CP-9003",
        )
        target_url = f"/books/{book.id}/decisions/{target.id}"
        preview = client.post(
            target_url,
            {
                "action": "preview-replacement",
                "left_logical_id": target.current_revision.record_logical_id,
                "right_logical_id": conflicting.current_revision.record_logical_id,
            },
        )
        preview_content = preview.content.decode()
        assert preview.status_code == 200
        assert "Review every affected authority" in preview_content
        assert "TX-1003" in preview_content
        assert "CP-9003" in preview_content
        assert "Ledger owner confirmed no external settlement" in preview_content
        assert "Counterparty owner confirmed an orphan statement row" in preview_content
        approved = (
            f"{conflicting.id}:{conflicting.current_revision_id}"
        )
        assert approved in preview_content

        book.refresh_from_db()
        replacement_payload = {
            "action": "commit-replacement",
            "target_revision_id": target.current_revision_id,
            "expected_resolution_generation": book.resolution_generation,
            "left_logical_id": target.current_revision.record_logical_id,
            "right_logical_id": conflicting.current_revision.record_logical_id,
            "approved_conflict": approved,
        }
        invalid_preview = client.post(
            target_url,
            {
                **replacement_payload,
                "target_revision_id": "",
                "reason": "This forged preview must not mutate authority.",
            },
        )
        assert invalid_preview.status_code == 400
        assert "replacement preview is invalid" in invalid_preview.content.decode()
        target.refresh_from_db()
        assert target.current_revision.action == "ACCEPT_UNMATCHED"

        missing_reason = client.post(target_url, replacement_payload)
        assert missing_reason.status_code == 400
        target.refresh_from_db()
        assert target.current_revision.action == "ACCEPT_UNMATCHED"

        replaced = client.post(
            target_url,
            {
                **replacement_payload,
                "reason": "Both source owners confirmed these records are counterparts.",
            },
            follow=True,
        )
        replaced_content = replaced.content.decode()
        assert replaced.status_code == 200
        assert "Decision replaced" in replaced_content
        assert "replace" in replaced_content
        assert "TX-1003 ↔ CP-9003" in replaced_content
        assert "Both source owners confirmed these records are counterparts" in replaced_content
        target.refresh_from_db()
        conflicting.refresh_from_db()
        assert target.current_revision.action == "REPLACE"
        assert target.current_revision.active_claims.count() == 2
        assert conflicting.current_revision.active_claims.count() == 0
        assert conflicting.current_revision.superseded_by.exists()
        assert "Changes are waiting for a rerun" in client.get(
            f"/books/{book.id}/workbench"
        ).content.decode()


@override_settings(DEBUG=False)
def test_curated_atlas_demo_completes_the_submission_journey(tmp_path) -> None:
    ledger = (DEMO_ROOT / "atlas-ledger.csv").read_text(encoding="utf-8")
    counterparty = (DEMO_ROOT / "atlas-counterparty.csv").read_text(encoding="utf-8")
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        client = Client()
        book = create_book(client)
        left = upload(client, f"/books/{book.id}/sources/left/upload", ledger)
        client.post(f"/imports/{left.headers['Location'].split('/')[-2]}/activate")
        right = upload(
            client,
            f"/books/{book.id}/sources/right/upload",
            counterparty,
            adapter="counterparty",
        )
        client.post(f"/imports/{right.headers['Location'].split('/')[-2]}/activate")

        first_page = client.post(f"/books/{book.id}/runs", follow=True)
        first_run = ReconciliationRun.objects.get(scope__book=book)
        assert first_run.result_counts["pairs"] == 2
        assert first_run.result_counts["unpaired"] == 2

        manual_case = None
        partner_logical_id = None
        for case_id in re.findall(r"/cases/([0-9a-f-]{36})", first_page.content.decode()):
            detail = client.get(f"/books/{book.id}/cases/{case_id}")
            option = re.search(
                r'name="partner_logical_id" value="([^"]+)"',
                detail.content.decode(),
            )
            if option is not None:
                manual_case = case_id
                partner_logical_id = option.group(1)
                break
        assert manual_case is not None
        assert partner_logical_id is not None

        linked = client.post(
            f"/books/{book.id}/cases/{manual_case}/link",
            {
                "partner_logical_id": partner_logical_id,
                "reason": "Confirmed against settlement statement.",
            },
            follow=True,
        )
        assert "Manual link saved" in linked.content.decode()

        second_page = client.post(f"/books/{book.id}/runs", follow=True)
        latest = ReconciliationRun.objects.filter(scope__book=book).order_by("-created_at").first()
        assert latest is not None and latest.id != first_run.id
        assert RunPair.objects.filter(run=latest, origin="MANUAL").exists()
        assert "Historical run" in second_page.content.decode()

        historical_page = client.get(
            f"/books/{book.id}/workbench", {"run": first_run.id}
        )
        historical_content = historical_page.content.decode()
        assert historical_page.status_code == 200
        assert "Cases from selected historical run" in historical_content
        assert "The current review queue remains separate below" in historical_content
        assert "historical · completed" in historical_content
        historical_case_url = (
            f"/books/{book.id}/cases/{manual_case}?run={first_run.id}"
        )
        assert historical_case_url in historical_content

        historical_detail = client.get(historical_case_url)
        detail_content = historical_detail.content.decode()
        assert historical_detail.status_code == 200
        assert "Historical occurrence" in detail_content
        assert str(first_run.id) in detail_content
        assert f"/workbench?run={first_run.id}" in detail_content
        assert "not in current review" in detail_content
        assert "Save manual link" not in detail_content
        assert "Accept unmatched record" not in detail_content
        assert client.get(
            f"/books/{book.id}/cases/{manual_case}", {"run": latest.id}
        ).status_code == 404


@override_settings(DEBUG=False)
def test_workbench_combines_search_filters_sort_and_complete_totals(tmp_path) -> None:
    ledger = (DEMO_ROOT / "atlas-ledger.csv").read_text(encoding="utf-8")
    counterparty = (DEMO_ROOT / "atlas-counterparty.csv").read_text(encoding="utf-8")
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        client = Client()
        book = create_book(client)
        left = upload(client, f"/books/{book.id}/sources/left/upload", ledger)
        client.post(f"/imports/{left.headers['Location'].split('/')[-2]}/activate")
        right = upload(
            client,
            f"/books/{book.id}/sources/right/upload",
            counterparty,
            adapter="counterparty",
        )
        client.post(f"/imports/{right.headers['Location'].split('/')[-2]}/activate")
        client.post(f"/books/{book.id}/runs")

        page = client.get(
            f"/books/{book.id}/workbench",
            {
                "q": "TX-1003",
                "kind": "unpaired",
                "review": "unreviewed",
                "sort": "newest",
            },
        )
        content = page.content.decode()
        assert page.status_code == 200
        assert "1 of 1" in content
        assert "TX-1003 · left" in content
        assert "CP-9003 · right" not in content
        assert 'value="TX-1003"' in content
        assert 'value="UNPAIRED" selected' in content
        assert 'value="newest" selected' in content

        invalid = client.get(f"/books/{book.id}/workbench", {"kind": "foreign"})
        assert invalid.status_code == 400


@override_settings(DEBUG=False)
def test_case_exports_are_explicit_precise_formula_safe_and_isolated(tmp_path) -> None:
    ledger = (
        "trade_id,traded_at,instrument,side,quantity,price,gross_amount,state\n"
        "=2+2,2026-09-01T09:15:00Z,BTC-USD,BUY,0.5,62000,31000,SETTLED\n"
    )
    counterparty = (
        "reference,executed_at,symbol,direction,qty,unit_price,total,status\n"
        "=2+2,2026-09-01 09:15:00,BTC-USD,B,0.5,62000,31000.00,SETTLED\n"
    )
    with override_settings(INGESTION_PRIVATE_ROOT=tmp_path):
        owner = Client()
        book = create_book(owner)
        left = upload(owner, f"/books/{book.id}/sources/left/upload", ledger)
        owner.post(f"/imports/{left.headers['Location'].split('/')[-2]}/activate")
        right = upload(
            owner,
            f"/books/{book.id}/sources/right/upload",
            counterparty,
            adapter="counterparty",
        )
        owner.post(f"/imports/{right.headers['Location'].split('/')[-2]}/activate")
        owner.post(f"/books/{book.id}/runs")
        run = ReconciliationRun.objects.get(scope__book=book)

        current_csv = owner.get(
            f"/books/{book.id}/exports/cases.csv",
            {"view": "current_review", "q": "=2+2"},
        )
        csv_text = current_csv.content.decode()
        assert current_csv.status_code == 200
        assert "reconciliation-current-review" in current_csv["Content-Disposition"]
        assert "current_review" in csv_text
        assert "'=2+2" in csv_text
        assert "0.500000000000" in csv_text
        assert "+00:00" in csv_text

        current_json = owner.get(
            f"/books/{book.id}/exports/cases.json",
            {"view": "current_review", "q": "=2+2"},
        ).json()
        assert current_json["view"] == "current_review"
        assert current_json["timezone"] == "UTC (+00:00)"
        assert current_json["decimal_encoding"] == "canonical decimal strings"
        assert current_json["total"] == 1
        assert current_json["rows"][0]["left_reference"] == "=2+2"
        assert current_json["rows"][0]["left_quantity"] == "0.500000000000"
        assert current_json["rows"][0]["review_health"] == "UNREVIEWED"

        facts = owner.get(
            f"/books/{book.id}/exports/cases.json",
            {"view": "run_facts", "run": str(run.id)},
        ).json()
        assert facts["view"] == "run_facts"
        assert facts["run_id"] == str(run.id)
        assert facts["rows"][0]["review_health"] == ""
        assert facts["rows"][0]["run_id"] == str(run.id)

        outsider = Client()
        create_book(outsider)
        foreign = outsider.get(
            f"/books/{book.id}/exports/cases.json",
            {"view": "run_facts", "run": str(run.id)},
        )
        assert foreign.status_code == 404
