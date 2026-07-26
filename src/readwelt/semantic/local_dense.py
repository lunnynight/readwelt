"""Lazy local dense encoder backed by Sentence Transformers."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any

DEFAULT_DENSE_MODEL = "Alibaba-NLP/gte-multilingual-base"
DEFAULT_DENSE_REVISION = "087a024525fd6e2fe749cb4679d218d8bcc95bdd"


class SentenceTransformerDenseEncoder:
    """Load a pinned multilingual encoder only when dense retrieval is used."""

    provider = "sentence-transformers"

    def __init__(
        self,
        *,
        model: str = DEFAULT_DENSE_MODEL,
        revision: str = DEFAULT_DENSE_REVISION,
        dimensions: int = 768,
        cache_dir: str | Path = ".readwelt/cache/models",
        device: str = "auto",
        batch_size: int = 32,
    ) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.model = model
        self.revision = revision
        self.dimensions = dimensions
        self._cache_dir = Path(cache_dir)
        self._device = device
        self._batch_size = batch_size
        self._runtime: Any | None = None

    def encode_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return self._encode(texts, task="document")

    def encode_queries(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return self._encode(texts, task="query")

    def _encode(
        self,
        texts: tuple[str, ...],
        *,
        task: str,
    ) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        runtime = self._load()
        method = getattr(runtime, f"encode_{task}", None)
        if method is None:
            method = runtime.encode
        vectors = method(
            list(texts),
            batch_size=self._batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return tuple(
            tuple(float(value) for value in vector[: self.dimensions]) for vector in vectors
        )

    def _load(self) -> Any:
        if self._runtime is not None:
            return self._runtime
        try:
            torch = importlib.import_module("torch")
            sentence_transformers = importlib.import_module("sentence_transformers")
        except ImportError as exc:
            raise RuntimeError(
                "dense retrieval requires the optional dependency; "
                "install with `uv sync --extra dense`"
            ) from exc
        device = self._device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._runtime = sentence_transformers.SentenceTransformer(
            self.model,
            revision=self.revision,
            cache_folder=str(self._cache_dir.resolve()),
            device=device,
            trust_remote_code=True,
        )
        return self._runtime


def configured_dense_encoder(
    project_root: Path,
) -> SentenceTransformerDenseEncoder | None:
    """Build the opt-in local encoder from environment without importing Torch."""
    configured = os.getenv("READWELT_DENSE_MODEL", "").strip()
    if not configured or configured.lower() in {"0", "false", "off", "none"}:
        return None
    model = DEFAULT_DENSE_MODEL if configured.lower() in {"1", "true", "auto"} else configured
    revision = os.getenv("READWELT_DENSE_REVISION", "").strip()
    return SentenceTransformerDenseEncoder(
        model=model,
        revision=revision or DEFAULT_DENSE_REVISION,
        cache_dir=project_root / "cache" / "models",
        device=os.getenv("READWELT_DENSE_DEVICE", "auto").strip() or "auto",
    )
