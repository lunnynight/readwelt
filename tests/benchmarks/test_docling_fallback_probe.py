from __future__ import annotations

import json
from pathlib import Path


def test_real_docling_probe_records_native_structure_and_scan_ocr() -> None:
    payload = json.loads(
        Path("reports/docling-structural-fallback-probe-2026-07-27.json").read_text(
            encoding="utf-8"
        )
    )

    assert payload["docling_package_version"] == "2.114.0"
    assert payload["required_docling_package_version"] == "2.114.0"
    assert payload["model_artifact_mode"] == "configured_local_artifacts"
    assert payload["implicit_model_download_allowed"] is False
    assert payload["dependency_versions"]["onnxruntime"] == "1.28.0"
    assert payload["model_artifacts"]["file_count"] == 45
    assert payload["model_artifacts"]["total_bytes"] == 633_340_087
    assert payload["model_artifacts"]["tree_digest"].startswith("sha256:")
    assert {item["label"] for item in payload["results"]} == {
        "native_pdf",
        "scanned_pdf",
    }
    native, scanned = payload["results"]
    assert native["label"] == "native_pdf"
    assert native["status"] == "structure_available"
    assert native["source_pages"] == 50
    assert native["text_characters"] == 143_851
    assert native["structure_records"] == 865
    assert native["geometry_records"] == 841
    assert native["content_layers"] == {"body": 822, "furniture": 43}
    assert native["structural_reference_closure"]["anonymous_records"] == 0
    assert native["structural_reference_closure"]["unresolved_parent_references"] == []
    assert native["structural_reference_closure"]["unresolved_child_references"] == []
    assert native["structural_reference_closure"]["unresolved_relation_references"] == []
    assert "docling_fallback_conversion_status:success" in native["findings"]

    assert scanned["label"] == "scanned_pdf"
    assert scanned["status"] == "structure_available"
    assert scanned["source_pages"] == 1
    assert scanned["source_text_layer_characters"] == 0
    assert scanned["ocr_observed"] is True
    assert scanned["text_characters"] == 1_619
    assert scanned["structure_records"] == 40
    assert scanned["geometry_records"] == 33
    assert scanned["content_layers"] == {"body": 39, "furniture": 1}
    assert scanned["structural_reference_closure"]["anonymous_records"] == 0
    assert scanned["structural_reference_closure"]["unresolved_parent_references"] == []
    assert scanned["structural_reference_closure"]["unresolved_child_references"] == []
    assert scanned["structural_reference_closure"]["unresolved_relation_references"] == []
    assert "docling_fallback_conversion_status:success" in scanned["findings"]
