"""Run the reproducible Stanza slice of the Chinese linguistic bake-off."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from benchmarks.articlegraph.linguistic_backends import benchmark_linguistic_backend
from benchmarks.articlegraph.stanza_backend import StanzaLinguisticBackend
from readwelt.extraction import ExtractionInput
from readwelt.extraction.models import SourceReference


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    texts = (
        ("unit-1", "政策变化后，企业需要重新评估风险。"),
        ("unit-2", "北京大学发布报告，认为人工智能将改变知识工作。"),
        ("unit-3", "如果监管环境改变，这一结论可能失效。"),
    )
    inputs = tuple(
        ExtractionInput(
            document_id="linguistic-bakeoff-zh",
            snapshot_id="2026-07-27",
            unit_id=unit_id,
            text=text,
            source_references=(
                SourceReference(
                    unit_id=unit_id,
                    reference_id=f"source:{unit_id}",
                    start_offset=0,
                    end_offset=len(text),
                    exact_text=text,
                ),
            ),
        )
        for unit_id, text in texts
    )
    result = benchmark_linguistic_backend(
        StanzaLinguisticBackend(args.model_dir),
        inputs,
        must_hit_unit_ids=tuple(unit_id for unit_id, _ in texts),
    )
    payload = json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
