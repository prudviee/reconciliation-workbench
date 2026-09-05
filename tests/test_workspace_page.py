from __future__ import annotations

from datetime import UTC, datetime

import pytest
from django.conf import settings
from django.test import Client, override_settings

from books.models import BookKind
from books.repositories import WorkspaceBookRepository
from reconciliation.domain import WorkspaceId
from workspaces.models import Workspace
from workspaces.sessions import digest_session_key


pytestmark = pytest.mark.django_db


def workspace_for(client: Client) -> Workspace:
    session_key = client.session.session_key
    assert session_key is not None
    return Workspace.objects.get(session_digest=digest_session_key(session_key))


def test_workspace_page_discloses_expiry_privacy_recovery_export_and_delete() -> None:
    client = Client()

    response = client.get("/")
    workspace = workspace_for(client)
    content = response.content.decode()

    assert response.status_code == 200
    assert "Good evidence makes" in content
    assert workspace.expires_at.isoformat() in content
    assert workspace.expires_at.strftime("%d %B %Y at %H:%M UTC") in content
    assert "Activity does not extend the expiry time" in content
    assert "Clearing this browser’s site data permanently loses access" in content
    assert "There is no account or recovery link" in content
    assert "Uploaded files and results are isolated to this workspace" in content
    assert "Export results from each completed run before the expiry" in content
    assert "Delete workspace" in content


def test_workspace_page_is_accessible_without_javascript() -> None:
    response = Client().get("/")
    content = response.content.decode()

    assert '<a class="skip-link" href="#main-content">' in content
    assert '<main id="main-content" tabindex="-1">' in content
    assert '<form method="post" action="/books/demo">' in content
    assert 'name="csrfmiddlewaretoken"' in content
    assert "<script" not in content
    assert 'aria-labelledby="workspace-heading"' in content
    assert 'aria-label="Workspace usage"' in content


def test_demo_creation_preserves_existing_and_creates_independent_books() -> None:
    client = Client()
    client.get("/")
    workspace = workspace_for(client)
    repository = WorkspaceBookRepository(WorkspaceId(workspace.id))
    existing = repository.create_user_book(
        name="August upload",
        created_at=datetime(2026, 9, 5, tzinfo=UTC),
    )

    first_response = client.post("/books/demo", follow=True)
    second_response = client.post("/books/demo", follow=True)
    books = repository.list()

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert "A new demo reconciliation was added" in second_response.content.decode()
    assert len(books) == 3
    assert books[0].id == existing.id
    assert books[0].name == "August upload"
    assert [book.kind for book in books] == [
        BookKind.USER,
        BookKind.DEMO,
        BookKind.DEMO,
    ]
    assert len({book.id for book in books}) == 3


def test_two_sessions_keep_demo_books_and_counts_independent() -> None:
    first = Client()
    second = Client()
    first.get("/")
    second.get("/")

    first.post("/books/demo")
    first.post("/books/demo")
    second.post("/books/demo")

    first_workspace = workspace_for(first)
    second_workspace = workspace_for(second)
    first_workspace.refresh_from_db()
    second_workspace.refresh_from_db()
    assert first_workspace.book_count == 2
    assert second_workspace.book_count == 1
    assert WorkspaceBookRepository(WorkspaceId(first_workspace.id)).count() == 2
    assert WorkspaceBookRepository(WorkspaceId(second_workspace.id)).count() == 1


@override_settings(WORKSPACE_BOOK_LIMIT=1)
def test_demo_quota_error_is_clear_and_preserves_existing_book() -> None:
    client = Client()
    client.get("/")
    first = client.post("/books/demo")

    refused = client.post("/books/demo")
    workspace = workspace_for(client)
    books = WorkspaceBookRepository(WorkspaceId(workspace.id)).list()

    assert first.status_code == 302
    assert refused.status_code == 409
    content = refused.content.decode()
    assert 'role="alert"' in content
    assert "reached its limit of 1 reconciliation books" in content
    assert "Your existing work is unchanged" in content
    assert len(books) == 1


def test_demo_creation_rejects_missing_csrf_proof() -> None:
    client = Client(enforce_csrf_checks=True)
    client.get("/")

    response = client.post("/books/demo")

    assert response.status_code == 403


def test_workspace_styles_cover_focus_reduced_motion_and_narrow_screens() -> None:
    stylesheet = (
        settings.BASE_DIR / "foundation" / "static" / "foundation" / "workspace.css"
    ).read_text(encoding="utf-8")

    assert ":focus-visible" in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert "@media (max-width: 620px)" in stylesheet
    assert "font-variant-numeric: tabular-nums" in stylesheet
