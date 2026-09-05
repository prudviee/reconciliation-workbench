from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from django.conf import settings
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext

from books.repositories import WorkspaceBookRepository
from reconciliation.domain import WorkspaceId
from workspaces.models import Workspace
from workspaces.sessions import digest_session_key


pytestmark = pytest.mark.django_db


def workspace_for(client: Client) -> Workspace:
    session_key = client.session.session_key
    assert session_key is not None
    return Workspace.objects.get(session_digest=digest_session_key(session_key))


def test_first_page_rotates_session_and_stores_only_digest() -> None:
    client = Client()
    seeded_session = client.session
    seeded_session["visitor_preference"] = "compact"
    seeded_session.save()
    unbound_key = seeded_session.session_key

    response = client.get("/")

    assert response.status_code == 200
    bound_key = client.session.session_key
    assert bound_key is not None
    assert bound_key != unbound_key
    assert client.session["visitor_preference"] == "compact"
    workspace = workspace_for(client)
    assert workspace.session_digest == digest_session_key(bound_key)
    assert workspace.session_digest != bound_key
    assert len(workspace.session_digest) == 64


def test_refresh_reuses_the_same_workspace_with_one_workspace_lookup() -> None:
    client = Client()
    client.get("/")
    original = workspace_for(client)

    with CaptureQueriesContext(connection) as queries:
        response = client.get("/")

    workspace_queries = [
        query for query in queries.captured_queries if 'FROM "workspace"' in query["sql"]
    ]
    assert response.status_code == 200
    assert workspace_for(client).id == original.id
    assert Workspace.objects.count() == 1
    assert len(workspace_queries) == 1


def test_independent_clients_receive_independent_workspaces() -> None:
    first = Client()
    second = Client()

    first.get("/")
    second.get("/")

    assert workspace_for(first).id != workspace_for(second).id
    assert Workspace.objects.count() == 2


def test_readiness_does_not_create_a_visitor_workspace() -> None:
    response = Client().get("/health/ready")

    assert response.status_code == 200
    assert Workspace.objects.count() == 0


def test_owner_can_read_book_but_foreign_and_random_ids_are_indistinguishable() -> None:
    owner_client = Client()
    outsider_client = Client()
    owner_client.get("/")
    outsider_client.get("/")
    owner = workspace_for(owner_client)
    book = WorkspaceBookRepository(WorkspaceId(owner.id)).create_user_book(
        name="Private statement",
        created_at=datetime(2026, 9, 5, tzinfo=UTC),
    )

    owner_response = owner_client.get(f"/books/{book.id}")
    foreign_response = outsider_client.get(f"/books/{book.id}")
    random_response = outsider_client.get(f"/books/{uuid4()}")

    assert owner_response.status_code == 200
    assert owner_response.json()["name"] == "Private statement"
    assert foreign_response.status_code == 404
    assert foreign_response.content == random_response.content
    assert foreign_response.headers["Content-Type"] == random_response.headers[
        "Content-Type"
    ]


def test_rename_requires_csrf_and_remains_workspace_scoped() -> None:
    owner_client = Client(enforce_csrf_checks=True)
    outsider_client = Client(enforce_csrf_checks=True)
    owner_client.get("/")
    outsider_client.get("/")
    owner = workspace_for(owner_client)
    book = WorkspaceBookRepository(WorkspaceId(owner.id)).create_user_book(
        name="Original",
        created_at=datetime(2026, 9, 5, tzinfo=UTC),
    )

    rejected = owner_client.post(
        f"/books/{book.id}/rename",
        {"name": "No token"},
    )
    owner_token = owner_client.cookies[settings.CSRF_COOKIE_NAME].value
    accepted = owner_client.post(
        f"/books/{book.id}/rename",
        {"name": "Owner rename"},
        HTTP_X_CSRFTOKEN=owner_token,
    )
    outsider_token = outsider_client.cookies[settings.CSRF_COOKIE_NAME].value
    foreign = outsider_client.post(
        f"/books/{book.id}/rename",
        {"name": "Foreign rename"},
        HTTP_X_CSRFTOKEN=outsider_token,
    )
    random = outsider_client.post(
        f"/books/{uuid4()}/rename",
        {"name": "Random rename"},
        HTTP_X_CSRFTOKEN=outsider_token,
    )

    assert rejected.status_code == 403
    assert accepted.status_code == 200
    assert foreign.status_code == 404
    assert foreign.content == random.content
    book.refresh_from_db()
    assert book.name == "Owner rename"


@override_settings(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
def test_session_cookie_has_production_security_attributes() -> None:
    client = Client()

    response = client.get("/", secure=True)

    cookie = response.cookies[settings.SESSION_COOKIE_NAME]
    assert cookie["secure"] is True
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Lax"


def clean_settings_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("DJANGO_") and key != "DATABASE_URL"
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def test_production_settings_require_explicit_security_and_database_values() -> None:
    environment = clean_settings_environment()
    environment["DJANGO_ENV"] = "production"

    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        cwd=settings.BASE_DIR,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    for setting_name in (
        "DJANGO_SECRET_KEY",
        "DJANGO_ALLOWED_HOSTS",
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "DATABASE_URL",
    ):
        assert setting_name in result.stderr


def test_complete_production_settings_enable_https_and_secure_cookies() -> None:
    environment = clean_settings_environment()
    environment.update(
        {
            "DJANGO_ENV": "production",
            "DJANGO_SECRET_KEY": "production-test-key-with-sufficient-entropy",
            "DJANGO_ALLOWED_HOSTS": "reconcile.example",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://reconcile.example",
            "DATABASE_URL": "postgresql://app:secret@db.example:5433/workbench",
        }
    )
    script = """
import json
from config import settings
print(json.dumps({
    "debug": settings.DEBUG,
    "allowed_hosts": settings.ALLOWED_HOSTS,
    "trusted_origins": settings.CSRF_TRUSTED_ORIGINS,
    "session_secure": settings.SESSION_COOKIE_SECURE,
    "session_httponly": settings.SESSION_COOKIE_HTTPONLY,
    "session_samesite": settings.SESSION_COOKIE_SAMESITE,
    "csrf_secure": settings.CSRF_COOKIE_SECURE,
    "ssl_redirect": settings.SECURE_SSL_REDIRECT,
    "hsts": settings.SECURE_HSTS_SECONDS,
    "database_name": settings.DATABASES["default"]["NAME"],
    "database_host": settings.DATABASES["default"]["HOST"],
    "database_port": settings.DATABASES["default"]["PORT"],
}))
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=settings.BASE_DIR,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    configured = json.loads(result.stdout)

    assert configured["debug"] is False
    assert configured["allowed_hosts"] == ["reconcile.example"]
    assert configured["trusted_origins"] == ["https://reconcile.example"]
    assert configured["session_secure"] is True
    assert configured["session_httponly"] is True
    assert configured["session_samesite"] == "Lax"
    assert configured["csrf_secure"] is True
    assert configured["ssl_redirect"] is True
    assert configured["hsts"] == 31_536_000
    assert configured["database_name"] == "workbench"
    assert configured["database_host"] == "db.example"
    assert configured["database_port"] == "5433"


def test_production_settings_reject_weak_security_values() -> None:
    environment = clean_settings_environment()
    environment.update(
        {
            "DJANGO_ENV": "production",
            "DJANGO_DEBUG": "true",
            "DJANGO_SECRET_KEY": "too-short",
            "DJANGO_ALLOWED_HOSTS": "*",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "http://reconcile.example",
            "DATABASE_URL": "postgresql://app:secret@db.example/workbench",
        }
    )

    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        cwd=settings.BASE_DIR,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "DJANGO_DEBUG must be false" in result.stderr
    assert "at least 32 characters" in result.stderr
    assert "must not contain a wildcard" in result.stderr
    assert "must use HTTPS" in result.stderr
