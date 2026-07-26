from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from readwelt.article_ir import unitize_snapshot
from readwelt.runner.snapshot import SectionStructure, snapshot_from_text
from readwelt.runner.xberg import XbergDocumentAdapter
from readwelt.storage import ArtifactStore, ProjectLayout


def _artifacts(tmp_path: Path) -> ArtifactStore:
    layout = ProjectLayout.resolve(tmp_path)
    layout.initialize()
    return ArtifactStore(layout)


def test_snapshot_projects_only_exact_unambiguous_xberg_structure(tmp_path: Path) -> None:
    snapshot = snapshot_from_text(
        source=tmp_path / "source.pdf",
        text="Heading\n\nBody",
        source_kind="application/pdf",
        artifacts=_artifacts(tmp_path),
        adapter_finding="test",
        structure=(
            SectionStructure(
                exact_text="Body",
                kind="paragraph",
                parent_element_id="heading-1",
                heading_trail=("Heading",),
                element_id="paragraph-1",
                page=2,
                bounding_box=(1.0, 2.0, 3.0, 4.0),
            ),
        ),
    )

    body = next(section for section in snapshot.sections if section.anchor.exact_text == "Body")
    assert body.kind == "paragraph"
    assert body.parent_element_id == "heading-1"
    assert body.heading_trail == ("Heading",)
    assert body.element_id == "paragraph-1"
    assert body.page == 2
    assert body.bounding_box == (1.0, 2.0, 3.0, 4.0)

    result = unitize_snapshot(snapshot, "Heading\n\nBody")
    unit = next(unit for unit in result.units if unit.exact_text == "Body")
    assert unit.kind == "paragraph"
    assert unit.heading_trail == ("Heading",)
    assert unit.source_references[0].element_id == "paragraph-1"
    assert unit.source_references[0].bounding_box == (1.0, 2.0, 3.0, 4.0)


def test_xberg_reports_structure_gap_when_document_exposes_none() -> None:
    structure, findings = XbergDocumentAdapter._available_structure(
        SimpleNamespace(document=None, elements=None)
    )

    assert structure == ()
    assert findings == ("xberg_structure_unsupported:not_exposed_for_document",)


def test_xberg_element_projection_uses_only_emitted_fields() -> None:
    element = SimpleNamespace(
        text="Body",
        element_type="narrative_text",
        metadata=SimpleNamespace(
            page_number=3,
            element_index=7,
            coordinates=SimpleNamespace(x0=1, y0=2, x1=3, y1=4),
        ),
    )

    structure, findings = XbergDocumentAdapter._available_structure(
        SimpleNamespace(document=None, elements=[element])
    )

    assert structure == (
        SectionStructure(
            exact_text="Body",
            kind="narrative_text",
            element_id="7",
            page=3,
            bounding_box=(1.0, 2.0, 3.0, 4.0),
        ),
    )
    assert findings == ("xberg_elements_available:1",)
