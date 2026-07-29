"""Frozen matched-condition protocol primitives for the product A/B evaluation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

PROTOCOL_SCHEMA = "readwelt.articlegraph-agent-reading-protocol.v1"
OFFICIAL_CLAUDE = Path(
    r"C:\Users\Administrator\AppData\Roaming\npm\claude.cmd"
)


@dataclass(frozen=True)
class MatchedConfig:
    """Every setting that may affect model behavior or metered cost."""

    model: str
    effort: str
    max_turns: int
    max_budget_usd: float
    agent_timeout_seconds: int
    system_prompt_sha256: str
    response_schema_sha256: str
    execution_policy: str

    @property
    def fingerprint(self) -> str:
        return digest_json(asdict(self))


@dataclass(frozen=True)
class Condition:
    id: Literal["baseline", "treatment"]
    articlegraph_enabled: bool


BASELINE = Condition(id="baseline", articlegraph_enabled=False)
TREATMENT = Condition(id="treatment", articlegraph_enabled=True)


def assert_matched_configs(baseline: MatchedConfig, treatment: MatchedConfig) -> None:
    """Fail before execution if any behavior/cost setting differs."""
    if baseline != treatment:
        differences = [
            field
            for field, value in asdict(baseline).items()
            if asdict(treatment)[field] != value
        ]
        raise ValueError(f"unmatched condition configuration: {', '.join(differences)}")


def digest_json(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def file_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


__all__ = [
    "BASELINE",
    "OFFICIAL_CLAUDE",
    "PROTOCOL_SCHEMA",
    "TREATMENT",
    "Condition",
    "MatchedConfig",
    "assert_matched_configs",
    "digest_json",
    "file_digest",
]
