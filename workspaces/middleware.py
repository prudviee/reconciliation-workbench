"""Attach an authorized anonymous workspace to protected Django views."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from reconciliation.domain import WorkspaceAccess

from .models import Workspace
from .repositories import WorkspaceUnavailable
from .sessions import WorkspaceSessionResolver


View = TypeVar("View", bound=Callable[..., HttpResponse])


def workspace_required(view: View) -> View:
    setattr(view, "workspace_required", True)
    return view


def workspace_access(request: HttpRequest) -> WorkspaceAccess:
    access = getattr(request, "workspace_access", None)
    if not isinstance(access, WorkspaceAccess):
        raise RuntimeError("The view requires WorkspaceMiddleware")
    return access


def workspace_record(request: HttpRequest) -> Workspace:
    record = getattr(request, "workspace_record", None)
    if not isinstance(record, Workspace):
        raise RuntimeError("The view requires WorkspaceMiddleware")
    return record


class WorkspaceMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.resolver = WorkspaceSessionResolver()

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_view(
        self,
        request: HttpRequest,
        view_func: Callable[..., HttpResponse],
        view_args: tuple[Any, ...],
        view_kwargs: dict[str, Any],
    ) -> HttpResponse | None:
        del view_args, view_kwargs
        if not getattr(view_func, "workspace_required", False):
            return None
        try:
            resolved = self.resolver.resolve(request.session)  # type: ignore[attr-defined]
            request.workspace_access = resolved.access  # type: ignore[attr-defined]
            request.workspace_record = resolved.record  # type: ignore[attr-defined]
        except WorkspaceUnavailable:
            request.session.flush()  # type: ignore[attr-defined]
            return HttpResponseRedirect("/workspace/unavailable")
        return None
