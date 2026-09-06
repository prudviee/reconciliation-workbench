from django.urls import path

from foundation import views

app_name = "foundation"

urlpatterns = [
    path("", views.home, name="home"),
    path("health/ready", views.readiness, name="readiness"),
    path("books/<uuid:book_id>", views.book_detail, name="book-detail"),
    path("books/<uuid:book_id>/rename", views.book_rename, name="book-rename"),
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
