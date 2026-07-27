from __future__ import annotations

import json
from pathlib import Path

from benchmarks.articlegraph.linguistic_backends import LinguisticBenchmarkResult


def _manifest() -> dict[str, object]:
    path = Path("benchmarks/articlegraph/linguistic_backend_manifest.json")
    return json.loads(path.read_text(encoding="utf-8"))


def test_bakeoff_manifest_keeps_heavy_backends_out_of_the_default_path() -> None:
    manifest = _manifest()

    assert manifest["schema_version"] == "linguistic-backend-bakeoff-manifest.v1"
    assert manifest["default_backend_decision"] == "readwelt.linguistic.regex"


def test_every_runtime_candidate_has_an_explicit_gate_decision() -> None:
    manifest = _manifest()
    candidates = manifest["candidates"]

    assert isinstance(candidates, list)
    assert {candidate["backend_id"] for candidate in candidates} == {
        "hanlp.zh",
        "paddlenlp",
        "stanza.zh-hans",
        "ltp.zh",
        "deepke",
    }
    for candidate in candidates:
        assert isinstance(candidate["gate_passed"], bool)
        assert candidate["decision"]
        if not candidate["gate_passed"]:
            assert candidate["gate_failures"]


def test_only_measured_stanza_smoke_candidate_passes_the_focused_gate() -> None:
    manifest = _manifest()
    candidates = {candidate["backend_id"]: candidate for candidate in manifest["candidates"]}

    assert candidates["stanza.zh-hans"]["gate_passed"]
    assert candidates["stanza.zh-hans"]["decision"] == "benchmark_only_optional_candidate"
    for backend_id in {"hanlp.zh", "paddlenlp", "ltp.zh", "deepke"}:
        assert not candidates[backend_id]["gate_passed"]


def test_stanza_record_retains_the_harness_schema_and_digest() -> None:
    path = Path("reports/linguistic-backend-bakeoff-2026-07-27.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    result = LinguisticBenchmarkResult(**payload)

    assert result.backend_id == "stanza.zh-hans"
    assert result.gate_passed
    assert result.offset_recovery_rate == 1.0
