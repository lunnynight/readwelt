"""Cross-process coordination for short-lived Readwelt CLI mutations."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout

DEFAULT_LOCK_TIMEOUT_SECONDS = 30.0
LOCK_TIMEOUT_ENV = "READWELT_LOCK_TIMEOUT_SECONDS"


class ProjectBusyError(RuntimeError):
    """Another process is still mutating the same Readwelt project."""

    code = "project_busy"


def configured_lock_timeout(value: float | None = None) -> float:
    if value is not None:
        timeout = value
    else:
        raw = os.environ.get(LOCK_TIMEOUT_ENV)
        timeout = DEFAULT_LOCK_TIMEOUT_SECONDS if raw is None else float(raw)
    if timeout < 0:
        raise ValueError("lock timeout must be non-negative")
    return timeout


@contextmanager
def project_mutation_lock(
    project_root: Path,
    *,
    timeout: float | None = None,
) -> Iterator[None]:
    """Serialize one bounded mutation without creating a resident process."""

    lock_directory = project_root.resolve() / ".locks"
    lock_directory.mkdir(parents=True, exist_ok=True)
    lock = FileLock(
        lock_directory / "mutation.lock",
        timeout=configured_lock_timeout(timeout),
    )
    try:
        with lock:
            yield
    except Timeout as exc:
        raise ProjectBusyError(f"Readwelt project is busy: {project_root.resolve()}") from exc
