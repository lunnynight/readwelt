"""Optional non-generative encoder boundaries."""

from __future__ import annotations

from typing import Protocol

from readwelt.semantic.models import EmbeddingDescriptor, SemanticSegment


class EmbeddingAdapter(Protocol):
    """Persist embeddings and return only a versioned artifact descriptor."""

    def encode(self, segments: tuple[SemanticSegment, ...]) -> EmbeddingDescriptor: ...


class DenseEncoder(Protocol):
    """Small query/document interface implemented by local or remote encoders."""

    provider: str
    model: str
    revision: str
    dimensions: int

    def encode_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...

    def encode_queries(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...
