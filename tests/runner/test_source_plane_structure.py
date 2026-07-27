from __future__ import annotations

from pathlib import Path

from readwelt.article_ir import unitize_snapshot
from readwelt.runner.snapshot import SectionStructure, snapshot_from_text
from readwelt.storage import ArtifactStore, ProjectLayout


def _artifacts(tmp_path: Path) -> ArtifactStore:
    layout = ProjectLayout.resolve(tmp_path)
    layout.initialize()
    return ArtifactStore(layout)


def test_source_elements_materialize_navigation_and_structural_relations(
    tmp_path: Path,
) -> None:
    text = "Title\n\nTable\n\nFigure\n\nCaption"
    snapshot = snapshot_from_text(
        source=tmp_path / "source.pdf",
        text=text,
        source_kind="application/pdf",
        artifacts=_artifacts(tmp_path),
        adapter_finding="test",
        structure=(
            SectionStructure(
                exact_text="Title",
                element_id="heading",
                kind="heading",
                child_element_ids=("table", "figure", "caption"),
                reading_order=0,
                raw_payload='{"id":"heading"}',
            ),
            SectionStructure(
                exact_text="Table",
                element_id="table",
                kind="table",
                parent_element_id="heading",
                structural_relations=(("caption", "caption"),),
                heading_trail=("Title",),
                reading_order=2,
            ),
            SectionStructure(
                exact_text="Figure",
                element_id="figure",
                kind="figure",
                parent_element_id="heading",
                structural_relations=(("caption", "caption"),),
                heading_trail=("Title",),
                reading_order=1,
            ),
            SectionStructure(
                exact_text="Caption",
                element_id="caption",
                kind="caption",
                parent_element_id="heading",
                reading_order=3,
            ),
        ),
    )

    by_id = {element.element_id: element for element in snapshot.source_elements}
    assert tuple(element.element_id for element in snapshot.source_elements) == (
        "heading",
        "figure",
        "table",
        "caption",
    )
    assert tuple(element.reading_order for element in snapshot.source_elements) == (
        0,
        1,
        2,
        3,
    )
    assert by_id["heading"].child_element_ids == ("figure", "table", "caption")
    assert by_id["figure"].previous_element_id == "heading"
    assert by_id["figure"].next_element_id == "table"
    assert by_id["table"].structural_relations == (("caption", "caption"),)
    assert by_id["figure"].structural_relations == (("caption", "caption"),)
    assert by_id["heading"].raw_payload_ref is not None

    unitization = unitize_snapshot(snapshot, text)
    units_by_element = {unit.source_references[0].element_id: unit for unit in unitization.units}
    assert units_by_element["table"].parent_unit_id == units_by_element["heading"].unit_id
    assert units_by_element["figure"].structural_path[:-1] == ("heading", "figure")


def test_unknown_structure_references_fail_empty_with_diagnostics(
    tmp_path: Path,
) -> None:
    snapshot = snapshot_from_text(
        source=tmp_path / "source.pdf",
        text="Body",
        source_kind="application/pdf",
        artifacts=_artifacts(tmp_path),
        adapter_finding="test",
        structure=(
            SectionStructure(
                exact_text="Body",
                element_id="body",
                kind="paragraph",
                parent_element_id="missing-parent",
                child_element_ids=("missing-child",),
                structural_relations=(("caption", "missing-caption"),),
                raw_payload='{"id":"body"}',
            ),
        ),
    )

    element = snapshot.source_elements[0]
    assert element.parent_element_id is None
    assert element.child_element_ids == ()
    assert element.structural_relations == ()
    assert element.raw_payload_ref is not None
    assert "source_element_parent_unresolved:1" in snapshot.parse_findings
    assert "source_element_children_unresolved:1" in snapshot.parse_findings
    assert "source_element_relations_unresolved:1" in snapshot.parse_findings


def test_source_plane_coverage_manifest_separates_dimensions(tmp_path: Path) -> None:
    text = "First\n\nSecond"
    snapshot = snapshot_from_text(
        source=tmp_path / "source.txt",
        text=text,
        source_kind="text/plain",
        artifacts=_artifacts(tmp_path),
        adapter_finding="test",
        structure=(
            SectionStructure(
                exact_text="missing from normalized text",
                element_id="unresolved",
                kind="caption",
            ),
        ),
        structure_findings=("xberg_relationships_unsupported:not_exposed",),
    )

    result = unitize_snapshot(snapshot, text)
    manifest = result.coverage_manifest

    assert manifest is not None
    assert manifest.schema_version == "source-plane-coverage.v1"
    assert manifest.has_complete_source_reachability
    assert {record.scope for record in manifest.range_coverage} == {"source_range"}
    assert {record.scope for record in manifest.element_coverage} == {"element"}
    assert {record.scope for record in manifest.structure_coverage} == {"structure"}
    assert {record.scope for record in manifest.capability_coverage} == {"capability"}
    assert manifest.element_coverage[0].status == "unsupported"
    assert any(
        record.status == "unsupported"
        and record.reason == "xberg_relationships_unsupported:not_exposed"
        for record in manifest.capability_coverage
    )
