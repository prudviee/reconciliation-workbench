from django.urls import path

from foundation import views

app_name = "foundation"

urlpatterns = [
    path("", views.home, name="home"),
    path("health/ready", views.readiness, name="readiness"),
    path("books/<uuid:book_id>", views.book_detail, name="book-detail"),
    path("books/<uuid:book_id>/sources", views.book_sources, name="book-sources"),
    path(
        "books/<uuid:book_id>/workbench",
        views.reconciliation_workbench,
        name="workbench",
    ),
    path(
        "books/<uuid:book_id>/runs",
        views.reconciliation_run_start,
        name="run-start",
    ),
    path(
        "books/<uuid:book_id>/exports/cases.<str:file_format>",
        views.reconciliation_case_export,
        name="case-export",
    ),
    path(
        "books/<uuid:book_id>/cases/<uuid:case_id>",
        views.reconciliation_case_detail,
        name="case-detail",
    ),
    path(
        "books/<uuid:book_id>/cases/<uuid:case_id>/link",
        views.reconciliation_case_link,
        name="case-link",
    ),
    path(
        "books/<uuid:book_id>/cases/<uuid:case_id>/accept-unmatched",
        views.reconciliation_case_accept_unmatched,
        name="case-accept-unmatched",
    ),
    path(
        "books/<uuid:book_id>/cases/<uuid:case_id>/reject-candidate",
        views.reconciliation_case_reject_candidate,
        name="case-reject-candidate",
    ),
    path(
        "books/<uuid:book_id>/decisions/<uuid:decision_id>",
        views.reconciliation_decision_detail,
        name="decision-detail",
    ),
    path(
        "books/<uuid:book_id>/sources/<str:side>/upload",
        views.source_upload,
        name="source-upload",
    ),
    path(
        "books/<uuid:book_id>/sources/<str:side>/mapping",
        views.source_mapping,
        name="source-mapping",
    ),
    path("books/<uuid:book_id>/rename", views.book_rename, name="book-rename"),
    path(
        "artifacts/<uuid:artifact_id>/download",
        views.artifact_download,
        name="artifact-download",
    ),
    path("imports/<uuid:attempt_id>/preview", views.import_preview, name="import-preview"),
    path("imports/<uuid:attempt_id>/activate", views.import_activate, name="import-activate"),
    path("imports/<uuid:attempt_id>", views.import_detail, name="import-detail"),
    path("books/demo", views.create_demo_book, name="book-demo-create"),
    path(
        "workspace/delete",
        views.workspace_delete_confirm,
        name="workspace-delete-confirm",
    ),
    path("workspace/delete/confirm", views.workspace_delete, name="workspace-delete"),
    path("workspace/deleted", views.workspace_deleted, name="workspace-deleted"),
    path(
        "workspace/unavailable",
        views.workspace_unavailable,
        name="workspace-unavailable",
    ),
]
