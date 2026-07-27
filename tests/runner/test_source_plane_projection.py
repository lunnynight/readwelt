from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from readwelt.runner.snapshot import SectionStructure, snapshot_from_text
from readwelt.runner.xberg import XbergDocumentAdapter
from readwelt.storage import ArtifactStore, ProjectLayout


def _artifacts(tmp_path: Path) -> ArtifactStore:
    layout = ProjectLayout.resolve(tmp_path)
    layout.initialize()
    return ArtifactStore(layout)


def test_repeated_text_projects_by_occurrence_when_counts_match(tmp_path: Path) -> None:
    snapshot = snapshot_from_text(
        source=tmp_path / "source.txt",
        text="重复\n\n重复",
        source_kind="text/plain",
        artifacts=_artifacts(tmp_path),
        adapter_finding="test",
        structure=(
            SectionStructure(exact_text="重复", element_id="first", kind="paragraph"),
            SectionStructure(exact_text="重复", element_id="second", kind="paragraph"),
        ),
    )

    assert tuple(section.element_id for section in snapshot.sections) == ("first", "second")
    assert tuple(
        (element.start_offset, element.end_offset) for element in snapshot.source_elements
    ) == ((0, 2), (4, 6))


def test_partial_and_non_text_elements_remain_first_class_source_records(
    tmp_path: Path,
) -> None:
    snapshot = snapshot_from_text(
        source=tmp_path / "source.pdf",
        text="前缀中间后缀",
        source_kind="application/pdf",
        artifacts=_artifacts(tmp_path),
        adapter_finding="test",
        structure=(
            SectionStructure(
                exact_text="中间",
                element_id="partial",
                kind="inline",
            ),
            SectionStructure(
                exact_text=None,
                element_id="figure",
                kind="figure",
                raw_payload='{"image_ref":"native-1"}',
            ),
        ),
    )

    partial, figure = snapshot.source_elements
    assert (partial.start_offset, partial.end_offset) == (2, 4)
    assert partial.projection_status == "projected"
    assert figure.projection_status == "preserved"
    assert figure.raw_payload_ref is not None


def test_xberg_collects_nodes_and_elements_cumulatively() -> None:
    node = SimpleNamespace(
        content='{"text":"Node","node_type":"heading"}',
        id="node-1",
        parent=None,
        page=1,
        bbox=None,
    )
    element = SimpleNamespace(
        text="Element",
        element_type="narrative_text",
        metadata=SimpleNamespace(page_number=2, element_index=7, coordinates=None),
    )

    structure, findings = XbergDocumentAdapter._available_structure(
        SimpleNamespace(
            document=SimpleNamespace(nodes=[node]),
            elements=[element],
        )
    )

    assert tuple(item.exact_text for item in structure) == ("Node", "Element")
    assert "xberg_document_nodes_available:1" in findings
    assert "xberg_elements_available:1" in findings
