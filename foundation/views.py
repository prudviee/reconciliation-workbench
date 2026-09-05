from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse


def home(request: HttpRequest) -> HttpResponse:
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
