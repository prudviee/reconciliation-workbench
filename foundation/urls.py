from django.urls import path

from foundation import views

app_name = "foundation"

urlpatterns = [
    path("", views.home, name="home"),
    path("health/ready", views.readiness, name="readiness"),
    path("books/<uuid:book_id>", views.book_detail, name="book-detail"),
    path("books/<uuid:book_id>/rename", views.book_rename, name="book-rename"),
]
