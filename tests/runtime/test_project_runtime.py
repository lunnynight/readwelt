import json
from pathlib import Path
from typing import Any

import pytest

from readwelt import ExecutionStatus, ReadweltProject
from readwelt.providers import StageRequest
from tests.interfaces.fakes import DeterministicFakeProvider


def _candidate(request: StageRequest) -> dict[str, Any]:
    anchors = request.evidence_packet["anchors"]
    count = 2 if request.stage == "stage_4_author_model" else 1
    claims = [
        {
            "claim_id": f"{request.stage}:claim:{index}",
            "text": f"{request.stage} claim {index}",
            "anchor_ids": [anchors[0]["anchor_id"]],
            "decision": "accepted",
            **(
                {"provenance": {"interpretation_id": f"lens-{index}"}}
                if request.stage == "stage_4_author_model"
                else {}
            ),
        }
        for index in range(count)
    ]
    if request.stage not in ("stage_1_mainline", "stage_2_structure"):
        for claim in claims:
            claim["source_claim_ids"] = [request.evidence_packet["upstream_claims"][0]["claim_id"]]
    return {"claims": claims, "gaps": [], "warnings": []}


def _project(tmp_path: Path) -> ReadweltProject:
    return ReadweltProject(
        base_directory=tmp_path,
        ingestion_backend="plain_text",
        candidate_providers=(DeterministicFakeProvider(_candidate),),
    )


def test_txt_creates_snapshot_and_semantic_atlas_without_a_model(tmp_path: Path) -> None:
    source = tmp_path / "article.txt"
    source.write_text("第一段。\r\n第二段。", encoding="utf-8")
    project = ReadweltProject(base_directory=tmp_path, ingestion_backend="plain_text")

    snapshot = project.import_document(source)
    atlas = project.prepare(snapshot.document_id)

    assert atlas.snapshot_id == snapshot.snapshot_id
    manifest = json.loads(
        (project.root / "documents" / snapshot.document_id / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert not Path(manifest["semantic_atlas_artifact"]["path"]).is_absolute()
    assert manifest["semantic_atlas_artifact"]["artifact_type"] == "semantic_atlas"


def test_completed_real_run_resume_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "article.txt"
    source.write_text("内容", encoding="utf-8")
    first_project = _project(tmp_path)
    run = first_project.read(source, idempotency_key="resume-test")
    events_path = first_project.root / "runs" / run.run_id / "events.jsonl"
    events_before = events_path.read_bytes()

    reopened_project = _project(tmp_path)
    resumed = reopened_project.resume(run.run_id)

    assert run.execution_status is ExecutionStatus.COMPLETED
    assert resumed == run
    assert events_path.read_bytes() == events_before


def test_resume_rejects_a_missing_cas_artifact(tmp_path: Path) -> None:
    source = tmp_path / "article.txt"
    source.write_text("可恢复内容", encoding="utf-8")
    project = _project(tmp_path)
    completed = project.read(source, idempotency_key="corruption-test")
    report = next(
        artifact
        for artifact in completed.artifacts
        if artifact.artifact_type == "reader_report_markdown"
    )
    (project.root / report.path).unlink()

    with pytest.raises(ValueError, match="missing or corrupt"):
        project.resume(completed.run_id)


def test_import_is_content_addressed_and_source_is_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "article.txt"
    original = b"\xef\xbb\xbfhello\r\nworld"
    source.write_bytes(original)
    project = ReadweltProject(
        project="state",
        base_directory=tmp_path,
        ingestion_backend="plain_text",
    )

    first = project.import_document(source)
    manifest_path = project.root / "documents" / first.document_id / "manifest.json"
    manifest_before = manifest_path.read_bytes()
    second = project.import_document(source)

    assert first.snapshot_id == second.snapshot_id
    assert first == second
    assert first.normalized_text_ref == second.normalized_text_ref
    assert manifest_path.read_bytes() == manifest_before
    assert source.read_bytes() == original
    assert (project.root / first.normalized_text_ref).read_text(encoding="utf-8") == "hello\nworld"
