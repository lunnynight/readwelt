"""Small deterministic registries for optional extraction backends."""

from __future__ import annotations

from collections.abc import Iterable

from .models import BackendCapability, BackendDescriptor
from .protocols import LinguisticBackend, SemanticExtractionBackend


class BackendAlreadyRegisteredError(ValueError):
    pass


class BackendNotFoundError(LookupError):
    pass


class _BackendRegistry[BackendT: (LinguisticBackend, SemanticExtractionBackend)]:
    def __init__(self, backends: Iterable[BackendT] = ()) -> None:
        self._backends: dict[str, BackendT] = {}
        for backend in backends:
            self.register(backend)

    def register(self, backend: BackendT, *, replace: bool = False) -> None:
        backend_id = backend.descriptor.backend_id
        if backend_id in self._backends and not replace:
            raise BackendAlreadyRegisteredError(f"backend already registered: {backend_id}")
        self._backends[backend_id] = backend

    def get(self, backend_id: str) -> BackendT:
        try:
            return self._backends[backend_id]
        except KeyError as error:
            raise BackendNotFoundError(f"backend is not registered: {backend_id}") from error

    def descriptors(self) -> tuple[BackendDescriptor, ...]:
        return tuple(self._backends[backend_id].descriptor for backend_id in sorted(self._backends))

    def supporting(self, capability: BackendCapability) -> tuple[BackendT, ...]:
        return tuple(
            self._backends[backend_id]
            for backend_id in sorted(self._backends)
            if capability in self._backends[backend_id].descriptor.supported_capabilities
        )

    def __contains__(self, backend_id: object) -> bool:
        return backend_id in self._backends

    def __len__(self) -> int:
        return len(self._backends)


class LinguisticBackendRegistry(_BackendRegistry[LinguisticBackend]):
    pass


class SemanticExtractionBackendRegistry(_BackendRegistry[SemanticExtractionBackend]):
    pass
