from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.http import require_GET, require_POST

from books.repositories import BookUnavailable, WorkspaceBookRepository
from reconciliation.domain import BookId
from workspaces.middleware import workspace_access, workspace_required


@workspace_required
@require_GET
def home(request: HttpRequest) -> HttpResponse:
    get_token(request)
    return HttpResponse("Reconciliation Workbench")


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
