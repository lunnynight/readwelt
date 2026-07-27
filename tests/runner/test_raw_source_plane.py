from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from readwelt.article_ir import unitize_snapshot
from readwelt.runner.snapshot import SectionStructure, snapshot_from_text
from readwelt.storage import ArtifactStore, ProjectLayout


def _artifacts(tmp_path: Path) -> tuple[ProjectLayout, ArtifactStore]:
    layout = ProjectLayout.resolve(tmp_path)
    layout.initialize()
    return layout, ArtifactStore(layout)


def test_extraction_empty_binary_sources_keep_distinct_raw_identities(
    tmp_path: Path,
) -> None:
    layout, artifacts = _artifacts(tmp_path)
    first_bytes = b"%PDF-image-only-one"
    second_bytes = b"%PDF-image-only-two"

    first = snapshot_from_text(
        source=tmp_path / "first.pdf",
        text="",
        source_kind="application/pdf",
        artifacts=artifacts,
        adapter_finding="empty-scanned-control",
        raw_source_content=first_bytes,
    )
    second = snapshot_from_text(
        source=tmp_path / "second.pdf",
        text="",
        source_kind="application/pdf",
        artifacts=artifacts,
        adapter_finding="empty-scanned-control",
        raw_source_content=second_bytes,
    )

    assert first.document_id != second.document_id
    assert first.snapshot_id != second.snapshot_id
    assert len(first.source_elements) == 1
    root = first.source_elements[0]
    assert root.kind == "source_document"
    assert root.projection_status == "preserved"
    assert root.raw_payload_ref is not None
    assert (layout.root / root.raw_payload_ref).read_bytes() == first_bytes
    assert first.attachments == (root.raw_payload_ref,)
    unitization = unitize_snapshot(first, "")
    assert first.sections == ()
    assert unitization.units == ()
    assert unitization.source_ranges == ()
    assert tuple(item.element_id for item in unitization.source_elements) == (root.element_id,)
    assert unitization.coverage_manifest is not None
    assert unitization.coverage_manifest.has_complete_source_reachability
    assert unitization.coverage_manifest.element_coverage[0].status == "covered"


def test_raw_source_root_owns_backend_top_level_elements(tmp_path: Path) -> None:
    _, artifacts = _artifacts(tmp_path)
    snapshot = snapshot_from_text(
        source=tmp_path / "structured.html",
        text="Heading\n\nCaption",
        source_kind="text/html",
        artifacts=artifacts,
        adapter_finding="structured-control",
        raw_source_content=b"<h1>Heading</h1><figcaption>Caption</figcaption>",
        structure=(
            SectionStructure(
                exact_text="Heading",
                element_id="heading-native",
                kind="heading",
                reading_order=0,
            ),
            SectionStructure(
                exact_text="Caption",
                element_id="caption-native",
                kind="caption",
                reading_order=1,
            ),
        ),
    )

    root, heading, caption = snapshot.source_elements
    assert root.child_element_ids == (heading.element_id, caption.element_id)
    assert heading.parent_element_id == root.element_id
    assert caption.parent_element_id == root.element_id
    assert root.next_element_id == heading.element_id
    assert heading.previous_element_id == root.element_id
    assert tuple(item.reading_order for item in snapshot.source_elements) == (0, 1, 2)


def test_source_plane_rejects_parent_cycle_even_when_links_are_reciprocal(
    tmp_path: Path,
) -> None:
    snapshot = _structured_snapshot(tmp_path)
    root, heading, caption = snapshot.source_elements
    cyclic_root = replace(root, parent_element_id=caption.element_id)
    cyclic_caption = replace(
        caption,
        child_element_ids=(*caption.child_element_ids, root.element_id),
    )

    with pytest.raises(ValueError, match="parent hierarchy cannot contain cycles"):
        replace(
            snapshot,
            source_elements=(cyclic_root, heading, cyclic_caption),
        )


def test_source_plane_rejects_element_disconnected_from_source_root(
    tmp_path: Path,
) -> None:
    snapshot = _structured_snapshot(tmp_path)
    root, heading, caption = snapshot.source_elements
    disconnected_root = replace(
        root,
        child_element_ids=(heading.element_id,),
    )
    disconnected_caption = replace(caption, parent_element_id=None)

    with pytest.raises(ValueError, match="reachable from source_document root"):
        replace(
            snapshot,
            source_elements=(disconnected_root, heading, disconnected_caption),
        )


def test_source_plane_rejects_closed_neighbor_cycle(tmp_path: Path) -> None:
    snapshot = _structured_snapshot(tmp_path)
    root, heading, caption = snapshot.source_elements
    cyclic_root = replace(root, previous_element_id=caption.element_id)
    cyclic_caption = replace(caption, next_element_id=root.element_id)

    with pytest.raises(ValueError, match="neighbor chain cannot contain cycles"):
        replace(
            snapshot,
            source_elements=(cyclic_root, heading, cyclic_caption),
        )


def _structured_snapshot(tmp_path: Path):
    _, artifacts = _artifacts(tmp_path)
    return snapshot_from_text(
        source=tmp_path / "topology.html",
        text="Heading\n\nCaption",
        source_kind="text/html",
        artifacts=artifacts,
        adapter_finding="topology-control",
        raw_source_content=b"<h1>Heading</h1><figcaption>Caption</figcaption>",
        structure=(
            SectionStructure(
                exact_text="Heading",
                element_id="heading-native",
                kind="heading",
                reading_order=0,
            ),
            SectionStructure(
                exact_text="Caption",
                element_id="caption-native",
                kind="caption",
                reading_order=1,
            ),
        ),
    )
