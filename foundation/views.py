from django.db import connection
from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from books.repositories import BookUnavailable, WorkspaceBookRepository
from foundation.forms import MappingForm, UploadForm
from ingestion.activation import AttemptNotReady, FullSnapshotActivationService, StalePreview
from ingestion.artifacts import ArtifactIntakeError
from ingestion.models import AttemptState, Dataset, DatasetRevision, IngestionAttempt, RawRow
from ingestion.preview import PreviewService
from ingestion.repositories import (
    IngestionResourceUnavailable,
    WorkspaceIngestionRepository,
)
from ingestion.services import ArtifactIntakeService, configured_artifact_store
from ingestion.workflow import SourcePreparationService
from reconciliation.domain import BookId, QuotaExceeded, QuotaResource
from sources.adapters import counterparty_contract, ledger_contract
from sources.models import BookSource, SourceContractRevision, SourceRole
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
@require_GET
def artifact_download(request: HttpRequest, artifact_id: object) -> HttpResponse:
    access = workspace_access(request)
    try:
        artifact = WorkspaceIngestionRepository(access.workspace_id).get_artifact(
            artifact_id
        )
        stream = configured_artifact_store().resolve(artifact.storage_key).open("rb")
    except (IngestionResourceUnavailable, FileNotFoundError, OSError, ValueError):
        raise Http404 from None
    response = FileResponse(
        stream,
        as_attachment=True,
        filename=artifact.original_filename,
        content_type=artifact.content_type,
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _owned_book(request: HttpRequest, book_id: object):
    try:
        return WorkspaceBookRepository(workspace_access(request).workspace_id).get(
            BookId.parse(str(book_id))
        )
    except (BookUnavailable, ValueError):
        raise Http404 from None


def _source_role(side: str) -> SourceRole:
    try:
        return SourceRole(side.upper())
    except ValueError:
        raise Http404 from None


@workspace_required
@require_GET
def book_sources(request: HttpRequest, book_id: object) -> HttpResponse:
    access = workspace_access(request)
    book = _owned_book(request, book_id)
    source_rows = {
        item.role: item
        for item in BookSource.objects.owned_by(access.workspace_id)
        .filter(book=book)
        .select_related("source")
    }
    sides = []
    for role, label in ((SourceRole.LEFT, "Internal ledger"), (SourceRole.RIGHT, "Counterparty")):
        book_source = source_rows.get(role)
        dataset = None
        latest_attempt = None
        if book_source is not None:
            dataset = (
                Dataset.objects.owned_by(access.workspace_id)
                .filter(book_source=book_source, coverage_key="default")
                .select_related("current_revision")
                .first()
            )
            if dataset is not None:
                latest_attempt = (
                    IngestionAttempt.objects.owned_by(access.workspace_id)
                    .filter(dataset=dataset)
                    .order_by("-created_at")
                    .first()
                )
        sides.append(
            {
                "role": role.lower(),
                "label": label,
                "book_source": book_source,
                "dataset": dataset,
                "latest_attempt": latest_attempt,
            }
        )
    return render(
        request,
        "foundation/sources.html",
        {"book": book, "sides": sides},
    )


@workspace_required
@require_http_methods(["GET", "POST"])
def source_upload(request: HttpRequest, book_id: object, side: str) -> HttpResponse:
    access = workspace_access(request)
    book = _owned_book(request, book_id)
    role = _source_role(side)
    default_adapter = "ledger" if role == SourceRole.LEFT else "counterparty"
    form = UploadForm(
        request.POST or None,
        request.FILES or None,
        initial={"adapter": default_adapter, "delimiter": ","},
    )
    if request.method == "POST" and form.is_valid():
        adapter = form.cleaned_data["adapter"]
        try:
            if adapter == "configurable":
                existing = (
                    BookSource.objects.owned_by(access.workspace_id)
                    .filter(book=book, role=role)
                    .first()
                )
                contract_revision = (
                    SourceContractRevision.objects.owned_by(access.workspace_id)
                    .filter(source=existing.source, contract__adapter_key="configurable-v1")
                    .order_by("-revision")
                    .first()
                    if existing is not None
                    else None
                )
                if contract_revision is None:
                    form.add_error(None, "Save a custom mapping for this side before uploading.")
                    raise LookupError
                dataset = Dataset.objects.owned_by(access.workspace_id).get(
                    book_source=existing,
                    coverage_key="default",
                )
            else:
                contract = ledger_contract() if adapter == "ledger" else counterparty_contract()
                prepared = SourcePreparationService(access.workspace_id).prepare(
                    book_id=BookId(book.id), role=role, contract=contract
                )
                contract_revision = prepared.contract_revision
                dataset = prepared.dataset
            uploaded = form.cleaned_data["artifact"]
            artifact = ArtifactIntakeService().ingest(
                access.workspace_id,
                original_filename=uploaded.name,
                content_type=uploaded.content_type or "application/octet-stream",
                delimiter=form.cleaned_data["delimiter"],
                chunks=uploaded.chunks(),
            )
            attempt = PreviewService.configured().preview(
                access.workspace_id,
                artifact_id=artifact.id,
                dataset_id=dataset.id,
                contract_revision_id=contract_revision.id,
                delimiter=form.cleaned_data["delimiter"],
            )
            return redirect("foundation:import-preview", attempt_id=attempt.id)
        except LookupError:
            pass
        except ArtifactIntakeError as error:
            form.add_error(None, f"The CSV could not be accepted: {error.code.value}.")
        except (QuotaExceeded, ValueError):
            form.add_error(None, "The upload could not be prepared. Check the selected format and workspace capacity.")
    return render(
        request,
        "foundation/upload.html",
        {"book": book, "side": role.lower(), "side_label": role.label, "form": form},
        status=400 if request.method == "POST" and form.errors else 200,
    )


@workspace_required
@require_http_methods(["GET", "POST"])
def source_mapping(request: HttpRequest, book_id: object, side: str) -> HttpResponse:
    access = workspace_access(request)
    book = _owned_book(request, book_id)
    role = _source_role(side)
    form = MappingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            contract = form.to_contract()
            SourcePreparationService(access.workspace_id).prepare(
                book_id=BookId(book.id), role=role, contract=contract
            )
        except ValueError as error:
            form.add_error(None, str(error))
        else:
            return redirect(
                f"{request.path.rsplit('/mapping', 1)[0]}/upload?mapping=saved"
            )
    return render(
        request,
        "foundation/mapping.html",
        {"book": book, "side": role.lower(), "side_label": role.label, "form": form},
        status=400 if request.method == "POST" and form.errors else 200,
    )


def _render_attempt(
    request: HttpRequest,
    attempt: IngestionAttempt,
    *,
    status: int = 200,
    message: str | None = None,
) -> HttpResponse:
    rows = RawRow.objects.owned_by(workspace_access(request).workspace_id).filter(
        attempt=attempt
    ).order_by("row_number")
    page = Paginator(rows, 50).get_page(request.GET.get("page", 1))
    operations: dict[str, int] = {}
    for value in rows.values_list("canonical_preview__operation", flat=True):
        label = value or "UNRESOLVED"
        operations[label] = operations.get(label, 0) + 1
    revisions = (
        DatasetRevision.objects.owned_by(workspace_access(request).workspace_id)
        .filter(dataset=attempt.dataset)
        .select_related("attempt")
        .order_by("-created_at")[:20]
    )
    attempt.refresh_from_db()
    stale = attempt.dataset.current_revision_id != attempt.expected_base_id and attempt.state == AttemptState.READY
    return render(
        request,
        "foundation/preview.html",
        {
            "attempt": attempt,
            "book": attempt.dataset.book_source.book,
            "side": attempt.dataset.book_source.role.lower(),
            "page": page,
            "operations": operations,
            "revisions": revisions,
            "stale": stale,
            "message": message,
        },
        status=status,
    )


@workspace_required
@require_GET
def import_preview(request: HttpRequest, attempt_id: object) -> HttpResponse:
    try:
        attempt = WorkspaceIngestionRepository(
            workspace_access(request).workspace_id
        ).get_attempt(attempt_id)
    except IngestionResourceUnavailable:
        raise Http404 from None
    return _render_attempt(request, attempt)


@workspace_required
@require_POST
def import_activate(request: HttpRequest, attempt_id: object) -> HttpResponse:
    access = workspace_access(request)
    try:
        attempt = WorkspaceIngestionRepository(access.workspace_id).get_attempt(attempt_id)
        FullSnapshotActivationService().activate(
            access.workspace_id,
            attempt_id=attempt.id,
            restore_reason=request.POST.get("restore_reason") or None,
        )
    except IngestionResourceUnavailable:
        raise Http404 from None
    except StalePreview:
        return _render_attempt(
            request,
            attempt,
            status=409,
            message="The dataset changed after this preview. Upload again to review against the current base.",
        )
    except AttemptNotReady:
        return _render_attempt(
            request,
            attempt,
            status=409,
            message="This import cannot be activated in its current state.",
        )
    return redirect(f"/imports/{attempt.id}?activated=1")


@workspace_required
@require_GET
def import_detail(request: HttpRequest, attempt_id: object) -> HttpResponse:
    try:
        attempt = WorkspaceIngestionRepository(
            workspace_access(request).workspace_id
        ).get_attempt(attempt_id)
    except IngestionResourceUnavailable:
        raise Http404 from None
    message = "Dataset evidence published successfully." if request.GET.get("activated") else None
    return _render_attempt(request, attempt, message=message)


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
