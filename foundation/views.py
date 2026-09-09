import logging
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.paginator import Paginator
from django.db import connection
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from books.repositories import BookUnavailable, WorkspaceBookRepository
from cases.exports import CaseExportService
from cases.queries import CaseQueryService
from foundation.forms import MappingForm, UploadForm
from ingestion.activation import AttemptNotReady, FullSnapshotActivationService, StalePreview
from ingestion.artifacts import ArtifactIntakeError
from ingestion.models import AttemptState, Dataset, DatasetRevision, IngestionAttempt, RawRow
from ingestion.preview import PreviewService, execute_claimed_import
from ingestion.repositories import (
    IngestionResourceUnavailable,
    WorkspaceIngestionRepository,
)
from ingestion.services import ArtifactIntakeService, configured_artifact_store
from ingestion.workflow import SourcePreparationService
from jobs.models import WorkerHeartbeat
from jobs.services import claim_and_execute, enqueue
from reconciliation.domain import (
    BookId,
    DecisionAction,
    DecisionAuthority,
    DecisionCommand,
    ExpectedDecisionRevision,
    JobKind,
    QuotaExceeded,
    QuotaResource,
    RecordSide,
    RetryPolicy,
)
from reconciliation.querying import (
    ReviewCursorError,
    ReviewFilterError,
    ReviewPageSizeError,
    ReviewQueryUnavailable,
)
from reconciliation.services import ReconciliationRunService, RunUnavailable, execute_claimed_run
from resolutions.services import (
    DecisionCommandService,
    DecisionMutationConflict,
    DecisionMutationUnavailable,
)
from resolutions.queries import DecisionQueryService
from reconciliation.workbench import WorkbenchNotReady, WorkbenchService, WorkbenchUnavailable
from sources.adapters import counterparty_contract, ledger_contract
from sources.models import BookSource, SourceContractRevision, SourceRole
from workspaces.middleware import workspace_access, workspace_record, workspace_required
from workspaces.lifecycle import WorkspaceLifecycleService


logger = logging.getLogger("reconciliation.runs")


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
        database_ready = True
    except Exception:
        database_ready = False

    latest_heartbeat = WorkerHeartbeat.objects.order_by("-updated_at").first()
    if latest_heartbeat is None:
        worker_status = "unknown"
        worker_heartbeat_age_seconds = None
    else:
        age_seconds = (timezone.now() - latest_heartbeat.updated_at).total_seconds()
        worker_heartbeat_age_seconds = round(age_seconds, 3)
        worker_status = (
            "healthy" if age_seconds <= settings.JOBS_WORKER_STALE_SECONDS else "stale"
        )

    payload = {
        "status": "ready" if database_ready else "unavailable",
        "database": "ready" if database_ready else "unavailable",
        "worker_status": worker_status,
        "worker_heartbeat_age_seconds": worker_heartbeat_age_seconds,
    }
    return JsonResponse(payload, status=200 if database_ready else 503)


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
            attempt = PreviewService.configured().create_shell(
                access.workspace_id,
                artifact_id=artifact.id,
                dataset_id=dataset.id,
                contract_revision_id=contract_revision.id,
                delimiter=form.cleaned_data["delimiter"],
            )
            work_item = enqueue(
                access.workspace_id,
                JobKind.IMPORT_VALIDATION,
                max_attempts=settings.JOBS_IMPORT_MAX_ATTEMPTS,
                now=timezone.now(),
                import_attempt=attempt,
            )
            try:
                claim_and_execute(
                    JobKind.IMPORT_VALIDATION,
                    now=timezone.now(),
                    lease_duration=timedelta(seconds=settings.JOBS_IMPORT_LEASE_SECONDS),
                    retry_policy=RetryPolicy(
                        max_attempts=settings.JOBS_IMPORT_MAX_ATTEMPTS,
                        backoff=timedelta(seconds=settings.JOBS_IMPORT_BACKOFF_SECONDS),
                    ),
                    executor=execute_claimed_import,
                    work_item_id=work_item.id,
                )
            except Exception:
                logger.exception(
                    "import_validation_failed",
                    extra={"attempt_id": str(attempt.id)},
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
@workspace_required
@require_GET
def reconciliation_workbench(request: HttpRequest, book_id: object) -> HttpResponse:
    access = workspace_access(request)
    book = _owned_book(request, book_id)
    filters = {
        "q": request.GET.get("q", "").strip(),
        "kind": request.GET.get("kind", "").strip().upper(),
        "review": request.GET.get("review", "").strip().upper(),
        "sort": request.GET.get("sort", "oldest").strip().lower(),
    }
    try:
        snapshot = WorkbenchService().snapshot(
            access.workspace_id,
            book_id=BookId(book.id),
            selected_run_id=request.GET.get("run"),
            case_cursor=request.GET.get("cursor"),
            case_search=filters["q"],
            case_kind=filters["kind"],
            case_review=filters["review"],
            case_sort=filters["sort"],
            selected_case_cursor=request.GET.get("run_cursor"),
        )
    except WorkbenchUnavailable:
        raise Http404 from None
    except (ReviewCursorError, ReviewFilterError, ReviewPageSizeError):
        return HttpResponse("Invalid workbench page request", status=400)
    retained_params = {key: value for key, value in filters.items() if value}
    if snapshot.selected_run is not None:
        retained_params["run"] = str(snapshot.selected_run.run_id)
    selected_run_query = urlencode(
        {"run": str(snapshot.selected_run.run_id)}
        if snapshot.selected_run is not None
        else {}
    )
    current_export_params = {"view": "current_review", **filters}
    current_export_params = {
        key: value for key, value in current_export_params.items() if value
    }
    run_export_params = {"view": "run_facts"}
    if snapshot.selected_run is not None:
        run_export_params["run"] = str(snapshot.selected_run.run_id)
    return render(
        request,
        "foundation/workbench.html",
        {
            "book": book,
            "snapshot": snapshot,
            "filters": filters,
            "next_query": urlencode(retained_params),
            "selected_run_query": selected_run_query,
            "current_export_query": urlencode(current_export_params),
            "run_export_query": urlencode(run_export_params),
            "message": (
                "Reconciliation completed. The immutable result is now available."
                if request.GET.get("completed")
                else None
            ),
            "error": (
                "The latest run failed. The previous successful result remains available, and the failed run can be retried."
                if request.GET.get("failed")
                else None
            ),
        },
    )


@workspace_required
@require_GET
def reconciliation_case_export(
    request: HttpRequest,
    book_id: object,
    file_format: str,
) -> HttpResponse:
    if file_format not in {"csv", "json"}:
        raise Http404
    access = workspace_access(request)
    book = _owned_book(request, book_id)
    readiness_state = WorkbenchService().readiness(
        access.workspace_id,
        book_id=BookId(book.id),
    )
    if readiness_state.scope_id is None:
        raise Http404
    try:
        document = CaseExportService().build(
            access.workspace_id,
            book_id=BookId(book.id),
            scope_id=readiness_state.scope_id,
            view=request.GET.get("view", ""),
            run_id=request.GET.get("run"),
            search=request.GET.get("q"),
            kind=request.GET.get("kind"),
            review=request.GET.get("review"),
            sort=request.GET.get("sort", "oldest"),
        )
    except (ReviewFilterError, ReviewQueryUnavailable):
        raise Http404 from None
    label = "current-review" if document.view == "current_review" else "run-facts"
    filename = f"reconciliation-{label}-{document.run_id[:8]}.{file_format}"
    if file_format == "json":
        response = JsonResponse(
            document.json_payload(),
            json_dumps_params={"ensure_ascii": False},
        )
    else:
        response = HttpResponse(
            document.csv_text(),
            content_type="text/csv; charset=utf-8",
        )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@workspace_required
@require_POST
def reconciliation_run_start(request: HttpRequest, book_id: object) -> HttpResponse:
    access = workspace_access(request)
    book = _owned_book(request, book_id)
    workbench = WorkbenchService()
    try:
        scope = workbench.ensure_run_context(
            access.workspace_id,
            book_id=BookId(book.id),
        )
        runner = ReconciliationRunService()
        frozen = runner.create_run_manifest(access.workspace_id, scope.id)
    except WorkbenchNotReady:
        snapshot = workbench.snapshot(access.workspace_id, book_id=BookId(book.id))
        return render(
            request,
            "foundation/workbench.html",
            {
                "book": book,
                "snapshot": snapshot,
                "error": "Activate both source datasets before starting reconciliation.",
            },
            status=409,
        )
    except (WorkbenchUnavailable, RunUnavailable):
        raise Http404 from None
    try:
        records = claim_and_execute(
            JobKind.RECONCILIATION_RUN,
            now=timezone.now(),
            lease_duration=timedelta(seconds=settings.JOBS_RUN_LEASE_SECONDS),
            retry_policy=RetryPolicy(
                max_attempts=settings.JOBS_RUN_MAX_ATTEMPTS,
                backoff=timedelta(seconds=settings.JOBS_RUN_BACKOFF_SECONDS),
            ),
            executor=execute_claimed_run,
            work_item_id=frozen.work_item_id,
        )
    except Exception:
        logger.exception(
            "reconciliation_run_failed",
            extra={"run_id": str(frozen.run_id)},
        )
        return _run_failed_redirect(book, scope)
    if not records:
        return redirect(f"/books/{book.id}/workbench")
    if not records[0].succeeded:
        return _run_failed_redirect(book, scope)
    return redirect(f"/books/{book.id}/workbench?run={frozen.run_id}&completed=1")


def _run_failed_redirect(book, scope) -> HttpResponse:
    scope.refresh_from_db(fields=["current_run"])
    query = "?failed=1"
    if scope.current_run_id is not None:
        query = f"?run={scope.current_run_id}&failed=1"
    return redirect(f"/books/{book.id}/workbench{query}")


@workspace_required
@require_GET
def reconciliation_case_detail(request: HttpRequest, book_id: object, case_id: object) -> HttpResponse:
    access = workspace_access(request)
    book = _owned_book(request, book_id)
    readiness = WorkbenchService().readiness(
        access.workspace_id, book_id=BookId(book.id)
    )
    if readiness.scope_id is None:
        raise Http404
    try:
        evidence = CaseQueryService().get_case_evidence(
            access.workspace_id,
            book_id=BookId(book.id),
            scope_id=readiness.scope_id,
            case_id=case_id,
            run_id=request.GET.get("run"),
        )
    except ReviewQueryUnavailable:
        raise Http404 from None
    record_ids = tuple(record.logical_transaction_id for record in evidence.records)
    try:
        decisions = DecisionQueryService().list_for_records(
            access.workspace_id,
            book_id=BookId(book.id),
            scope_id=readiness.scope_id,
            record_ids=record_ids,
        )
    except ReviewQueryUnavailable:
        raise Http404 from None
    return render(
        request,
        "foundation/case_detail.html",
        {
            "book": book,
            "evidence": evidence,
            "decisions": decisions,
            "pending_changes": (
                evidence.current_review is not None
                and evidence.occurrence.timeline_label == "CURRENT"
                and book.resolution_generation
                != evidence.current_review.applied_resolution_generation
            ),
            "workbench_query": urlencode(
                {"run": str(evidence.occurrence.run_id)}
                if evidence.occurrence.timeline_label != "CURRENT"
                else {}
            ),
            "message": (
                "Manual link saved. Run reconciliation again to publish it into a new immutable result."
                if request.GET.get("linked")
                else (
                    "Unmatched decision saved. Run reconciliation again to publish it into a new immutable result."
                    if request.GET.get("accepted")
                    else None
                )
            ),
        },
    )


@workspace_required
@require_POST
def reconciliation_case_link(request: HttpRequest, book_id: object, case_id: object) -> HttpResponse:
    access = workspace_access(request)
    book = _owned_book(request, book_id)
    readiness = WorkbenchService().readiness(
        access.workspace_id, book_id=BookId(book.id)
    )
    if readiness.scope_id is None:
        raise Http404
    try:
        evidence = CaseQueryService().get_case_evidence(
            access.workspace_id,
            book_id=BookId(book.id),
            scope_id=readiness.scope_id,
            case_id=case_id,
        )
    except ReviewQueryUnavailable:
        raise Http404 from None
    reason = str(request.POST.get("reason", "")).strip()
    partner_logical_id = str(request.POST.get("partner_logical_id", "")).strip()
    option = next(
        (item for item in evidence.link_options if str(item["partner_logical_id"]) == partner_logical_id),
        None,
    )
    own = evidence.left or evidence.right
    if own is None or option is None or not reason:
        return render(
            request,
            "foundation/case_detail.html",
            {"book": book, "evidence": evidence, "error": "Choose an available counterpart and provide a reason."},
            status=400,
        )
    if evidence.left is not None:
        authority = DecisionAuthority.link(
            str(evidence.left.logical_transaction_id), partner_logical_id
        )
    else:
        authority = DecisionAuthority.link(
            partner_logical_id, str(evidence.right.logical_transaction_id)
        )
    expected_generation = (
        evidence.current_review.applied_resolution_generation
        if evidence.current_review is not None
        else book.resolution_generation
    )
    command = DecisionCommand(
        action=DecisionAction.LINK,
        reason=reason,
        actor="showcase-reviewer",
        expected_resolution_generation=expected_generation,
        authority=authority,
        reviewed_observation_ids=(
            str(own.observation_id), str(option["partner_observation_id"])
        ),
    )
    try:
        DecisionCommandService().commit_initial(
            access.workspace_id, book_id=BookId(book.id), command=command
        )
    except DecisionMutationConflict as error:
        return render(
            request,
            "foundation/case_detail.html",
            {"book": book, "evidence": evidence, "error": str(error)},
            status=409,
        )
    except (DecisionMutationUnavailable, ValueError):
        raise Http404 from None
    return redirect(f"/books/{book.id}/cases/{case_id}?linked=1")


@workspace_required
@require_POST
def reconciliation_case_accept_unmatched(
    request: HttpRequest, book_id: object, case_id: object
) -> HttpResponse:
    access = workspace_access(request)
    book = _owned_book(request, book_id)
    readiness = WorkbenchService().readiness(
        access.workspace_id, book_id=BookId(book.id)
    )
    if readiness.scope_id is None:
        raise Http404
    try:
        evidence = CaseQueryService().get_case_evidence(
            access.workspace_id,
            book_id=BookId(book.id),
            scope_id=readiness.scope_id,
            case_id=case_id,
        )
    except ReviewQueryUnavailable:
        raise Http404 from None
    reason = str(request.POST.get("reason", "")).strip()
    own = evidence.left or evidence.right
    can_accept = (
        own is not None
        and evidence.occurrence.result_kind == "UNPAIRED"
        and own.canonical_values.get("state") != "CANCELLED"
    )
    if not can_accept or not reason:
        return render(
            request,
            "foundation/case_detail.html",
            {
                "book": book,
                "evidence": evidence,
                "error": "Provide a reason before accepting this record as genuinely unmatched.",
            },
            status=400,
        )
    side = RecordSide.LEFT if evidence.left is not None else RecordSide.RIGHT
    expected_generation = (
        evidence.current_review.applied_resolution_generation
        if evidence.current_review is not None
        else book.resolution_generation
    )
    command = DecisionCommand(
        action=DecisionAction.ACCEPT_UNMATCHED,
        reason=reason,
        actor="showcase-reviewer",
        expected_resolution_generation=expected_generation,
        authority=DecisionAuthority.accept_unmatched(
            str(own.logical_transaction_id), side
        ),
        reviewed_observation_ids=(str(own.observation_id),),
    )
    try:
        DecisionCommandService().commit_initial(
            access.workspace_id, book_id=BookId(book.id), command=command
        )
    except DecisionMutationConflict as error:
        return render(
            request,
            "foundation/case_detail.html",
            {"book": book, "evidence": evidence, "error": str(error)},
            status=409,
        )
    except (DecisionMutationUnavailable, ValueError):
        raise Http404 from None
    return redirect(f"/books/{book.id}/cases/{case_id}?accepted=1")


@workspace_required
@require_http_methods(["GET", "POST"])
def reconciliation_decision_detail(
    request: HttpRequest, book_id: object, decision_id: object
) -> HttpResponse:
    access = workspace_access(request)
    book = _owned_book(request, book_id)
    readiness = WorkbenchService().readiness(
        access.workspace_id, book_id=BookId(book.id)
    )
    if readiness.scope_id is None:
        raise Http404
    query = DecisionQueryService()
    try:
        history = query.get_decision_history(
            access.workspace_id,
            book_id=BookId(book.id),
            scope_id=readiness.scope_id,
            decision_id=decision_id,
        )
    except ReviewQueryUnavailable:
        raise Http404 from None
    current = next(
        item for item in history.revisions if item.revision_id == history.current_revision_id
    )
    error = None
    status = 200
    if request.method == "POST":
        reason = str(request.POST.get("reason", "")).strip()
        if not reason:
            error = "Provide a reason before revoking this decision."
            status = 400
        elif not current.authority_active:
            error = "This decision no longer has an active authority to revoke."
            status = 409
        else:
            command = DecisionCommand(
                action=DecisionAction.REVOKE,
                target=ExpectedDecisionRevision(
                    str(history.decision_id), str(history.current_revision_id)
                ),
                reason=reason,
                actor="showcase-reviewer",
                expected_resolution_generation=history.resolution_generation,
            )
            try:
                DecisionCommandService().commit_change(
                    access.workspace_id,
                    book_id=BookId(book.id),
                    command=command,
                )
            except DecisionMutationConflict as conflict:
                error = str(conflict)
                status = 409
            except (DecisionMutationUnavailable, ValueError):
                raise Http404 from None
            else:
                return redirect(
                    f"/books/{book.id}/decisions/{decision_id}?revoked=1"
                )
    return render(
        request,
        "foundation/decision_detail.html",
        {
            "book": book,
            "history": history,
            "current": current,
            "error": error,
            "message": (
                "Decision revoked. Run reconciliation again to publish the change."
                if request.GET.get("revoked")
                else None
            ),
        },
        status=status,
    )
