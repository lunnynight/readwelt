"""Narrow runtime protocol for model-backed stage candidate generation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from .contracts import ProviderKind, StageCandidate, StageRequest

JsonSchema = Mapping[str, Any]


class CandidateProvider(Protocol):
    """Generate one validated candidate without owning stage settlement."""

    @property
    def kind(self) -> ProviderKind: ...

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def generate(
        self,
        request: StageRequest,
        response_schema: JsonSchema,
    ) -> StageCandidate: ...
