from django.urls import path

from foundation import views

app_name = "foundation"

urlpatterns = [
    path("", views.home, name="home"),
    path("health/ready", views.readiness, name="readiness"),
]
