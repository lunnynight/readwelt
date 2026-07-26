"""Narrow, duck-typed boundary shared by CLI, HTTP, and MCP adapters."""

from __future__ import annotations

import asyncio
import importlib
import inspect
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

from .contracts import ProviderSelection, ProviderUnavailableError


@runtime_checkable
class ReadweltApplicationServicePort(Protocol):
    """The methods used by external adapters.

    Concrete domain objects and return types intentionally do not leak into this
    protocol.  Adapter projections convert dataclasses, Pydantic models, and
    mappings into JSON at the final boundary.
    """

    def import_document(self, source: str, **options: Any) -> Any: ...

    def prepare(self, document_id: str, **options: Any) -> Any: ...

    def batch_prepare(self, sources: list[str], **options: Any) -> Any: ...

    def read(self, source_or_document_id: str, **options: Any) -> Any: ...

    def get_run_status(self, run_id: str) -> Any: ...

    def pull_stage_request(self, run_id: str, stage: str) -> Any: ...

    def submit_stage_candidate(self, run_id: str, stage: str, candidate: Any) -> Any: ...


class ApplicationServiceUnavailable(RuntimeError):
    """The core application service cannot be loaded."""


def load_application_service(project_root: Path) -> ReadweltApplicationServicePort:
    """Load the application service lazily so adapter imports stay lightweight."""

    try:
        application = importlib.import_module("readwelt.application")
        service_class = application.ReadweltApplicationService
    except (AttributeError, ImportError, ModuleNotFoundError) as exc:
        raise ApplicationServiceUnavailable(
            "ReadweltApplicationService is unavailable; install the core package "
            "or inject a service instance"
        ) from exc

    open_method = getattr(service_class, "open", None)
    if callable(open_method):
        return cast(ReadweltApplicationServicePort, open_method(project_root))
    try:
        return cast(ReadweltApplicationServicePort, service_class(project_root))
    except TypeError as exc:
        raise ApplicationServiceUnavailable(
            "ReadweltApplicationService has no supported project-root constructor"
        ) from exc


async def invoke(service: object, method: str, *args: Any, **kwargs: Any) -> Any:
    """Invoke either a synchronous or asynchronous service method."""

    target = getattr(service, method, None)
    if not callable(target):
        raise ApplicationServiceUnavailable(f"application service does not implement {method}()")
    if inspect.iscoroutinefunction(target):
        return await target(*args, **kwargs)
    value = await asyncio.to_thread(target, *args, **kwargs)
    return await value if inspect.isawaitable(value) else value


async def invoke_read(
    service: object,
    source_or_document_id: str,
    selection: ProviderSelection,
) -> Any:
    """Call ``read`` while preserving compatibility with the first core facade."""

    target = getattr(service, "read", None)
    if not callable(target):
        raise ApplicationServiceUnavailable("application service does not implement read()")

    is_default = (
        selection.primary is None and not selection.candidates and selection.mode.value == "primary"
    )
    signature = inspect.signature(target)
    accepts_selection = "provider_selection" in signature.parameters or any(
        item.kind is inspect.Parameter.VAR_KEYWORD for item in signature.parameters.values()
    )
    if not accepts_selection and not is_default:
        raise ProviderUnavailableError(
            "the current application service does not support provider selection"
        )
    kwargs = {"provider_selection": selection.to_dict()} if accepts_selection else {}
    if inspect.iscoroutinefunction(target):
        return await target(source_or_document_id, **kwargs)
    value = await asyncio.to_thread(target, source_or_document_id, **kwargs)
    return await value if inspect.isawaitable(value) else value
