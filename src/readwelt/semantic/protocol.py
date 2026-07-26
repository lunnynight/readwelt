"""Optional non-generative encoder boundary."""

from __future__ import annotations

from typing import Protocol

from readwelt.semantic.models import EmbeddingDescriptor, SemanticSegment


class EmbeddingAdapter(Protocol):
    """Persist embeddings and return only a versioned artifact descriptor."""

    def encode(self, segments: tuple[SemanticSegment, ...]) -> EmbeddingDescriptor: ...
