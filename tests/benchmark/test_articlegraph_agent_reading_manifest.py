from __future__ import annotations

from copy import deepcopy

import pytest

from benchmarks.articlegraph_agent_reading.manifest import validate_manifest


def test_manifest_validator_requires_real_sample_size() -> None:
    with pytest.raises(ValueError, match="at least 24"):
        validate_manifest(
            {
                "schema_version": "readwelt.articlegraph-agent-reading-manifest.v1",
                "documents": [],
            }
        )


def test_manifest_validator_rejects_digest_mutation() -> None:
    manifest = _valid_manifest()
    validate_manifest(manifest)
    changed = deepcopy(manifest)
    changed["documents"][0]["tasks"][0]["question"] = "post-hoc mutation"
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_manifest(changed)


def _valid_manifest() -> dict[str, object]:
    import hashlib
    import json

    documents = []
    for category_index in range(3):
        for length in ("short", "long"):
            for quality in ("sparse_native_text", "dense_native_text"):
                for _repetition in range(2):
                    ordinal = len(documents)
                    document_id = f"d{ordinal}"
                    anchors = [
                        {"anchor_id": f"{document_id}-a{index}", "exact_text": "证据"}
                        for index in range(3)
                    ]
                    tasks = [
                        {
                            "task_id": f"{document_id}-{kind}",
                            "kind": kind,
                            "gold_anchor_id": anchors[index]["anchor_id"],
                            "rubric": {"scoring_rules": ["exact"]},
                        }
                        for index, kind in enumerate(("location", "citation", "comprehension"))
                    ]
                    documents.append(
                        {
                            "document_id": document_id,
                            "source_sha256": hashlib.sha256(document_id.encode()).hexdigest(),
                            "category": f"category-{category_index}",
                            "length_band": length,
                            "extraction_quality_band": quality,
                            "gold_anchors": anchors,
                            "tasks": tasks,
                        }
                    )
    manifest: dict[str, object] = {
        "schema_version": "readwelt.articlegraph-agent-reading-manifest.v1",
        "documents": documents,
    }
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    manifest["manifest_digest"] = "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()
    return manifest
