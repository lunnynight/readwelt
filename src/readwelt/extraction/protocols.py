"""Independently replaceable linguistic and semantic extraction seams."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import BackendDescriptor, ExtractionInput, GraphExtraction


@runtime_checkable
class LinguisticBackend(Protocol):
    @property
    def descriptor(self) -> BackendDescriptor: ...

    def extract(self, inputs: tuple[ExtractionInput, ...]) -> GraphExtraction: ...


@runtime_checkable
class SemanticExtractionBackend(Protocol):
    @property
    def descriptor(self) -> BackendDescriptor: ...

    def extract(self, inputs: tuple[ExtractionInput, ...]) -> GraphExtraction: ...
