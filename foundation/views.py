from django.db import connection
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from books.repositories import BookUnavailable, WorkspaceBookRepository
from reconciliation.domain import BookId, QuotaExceeded, QuotaResource
from workspaces.middleware import workspace_access, workspace_record, workspace_required
from workspaces.lifecycle import WorkspaceLifecycleService


@workspace_required
@require_GET
def home(request: HttpRequest) -> HttpResponse:
    get_token(request)
    return render_workspace(request)


def readiness(request: HttpRequest) -> JsonResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse(
            {"status": "unavailable", "database": "unavailable"}, status=503
        )
    return JsonResponse({"status": "ready", "database": "ready"})


@workspace_required
@require_GET
def book_detail(request: HttpRequest, book_id: object) -> JsonResponse:
    access = workspace_access(request)
    repository = WorkspaceBookRepository(access.workspace_id)
    try:
        book = repository.get(BookId.parse(str(book_id)))
    except BookUnavailable:
        return JsonResponse({"detail": "Not found"}, status=404)
    return JsonResponse({"id": str(book.id), "name": book.name, "kind": book.kind})


@workspace_required
@require_POST
def book_rename(request: HttpRequest, book_id: object) -> JsonResponse:
    name = request.POST.get("name", "").strip()
    if not name:
        return JsonResponse({"detail": "A name is required"}, status=400)
    access = workspace_access(request)
    repository = WorkspaceBookRepository(access.workspace_id)
    try:
        book = repository.rename(BookId.parse(str(book_id)), name=name)
    except BookUnavailable:
        return JsonResponse({"detail": "Not found"}, status=404)
    return JsonResponse({"id": str(book.id), "name": book.name})


@workspace_required
@require_POST
def create_demo_book(request: HttpRequest) -> HttpResponse:
    access = workspace_access(request)
    repository = WorkspaceBookRepository(access.workspace_id)
    next_number = repository.count() + 1
    try:
        repository.create_demo_book(
            name=f"Card settlement demo {next_number}",
            sample_template_version="2026.09-v1",
            created_at=timezone.now(),
        )
    except QuotaExceeded as error:
        return render_workspace(request, error=quota_message(error), status=409)
    return redirect("/?created=demo")


def render_workspace(
    request: HttpRequest,
    *,
    error: str | None = None,
    status: int = 200,
) -> HttpResponse:
    access = workspace_access(request)
    workspace = workspace_record(request)
    books = WorkspaceBookRepository(access.workspace_id).list()
    context = {
        "workspace": workspace,
        "workspace_short_id": str(workspace.id).split("-")[0].upper(),
        "expires_iso": access.expires_at.isoformat(),
        "expires_display": access.expires_at.strftime("%d %B %Y at %H:%M UTC"),
        "books": books,
        "book_limit": settings.WORKSPACE_BOOK_LIMIT,
        "storage_limit_mb": settings.WORKSPACE_RETAINED_BYTES_LIMIT // (1024 * 1024),
        "active_job_limit": settings.WORKSPACE_ACTIVE_JOB_LIMIT,
        "demo_created": request.GET.get("created") == "demo",
        "error": error,
    }
    return render(request, "foundation/workspace.html", context, status=status)


def quota_message(error: QuotaExceeded) -> str:
    labels = {
        QuotaResource.RETAINED_BYTES: "retained storage",
        QuotaResource.BOOKS: "reconciliation books",
        QuotaResource.ACTIVE_JOBS: "active jobs",
    }
    label = labels[error.resource]
    return (
        f"This workspace has reached its limit of {error.limit} {label}. "
        "Your existing work is unchanged."
    )


@workspace_required
@require_GET
def workspace_delete_confirm(request: HttpRequest) -> HttpResponse:
    access = workspace_access(request)
    return render(
        request,
        "foundation/workspace_delete.html",
        {
            "expires_display": access.expires_at.strftime(
                "%d %B %Y at %H:%M UTC"
            )
        },
    )


@workspace_required
@require_POST
def workspace_delete(request: HttpRequest) -> HttpResponse:
    access = workspace_access(request)
    WorkspaceLifecycleService().delete(access.workspace_id, now=timezone.now())
    request.session.flush()
    return redirect("foundation:workspace-deleted")


@require_GET
def workspace_deleted(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "foundation/workspace_message.html",
        {
            "eyebrow": "Deletion requested",
            "title": "Workspace access revoked",
            "message": (
                "This browser can no longer access that workspace. "
                "Its private data is queued for cleanup."
            ),
            "action": "Start a new workspace",
        },
    )


@require_GET
def workspace_unavailable(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "foundation/workspace_message.html",
        {
            "eyebrow": "Workspace unavailable",
            "title": "This workspace has ended",
            "message": (
                "It may have expired, been deleted, or become unavailable. "
                "There is no recovery path for an anonymous workspace."
            ),
            "action": "Create a new workspace",
        },
        status=410,
    )
