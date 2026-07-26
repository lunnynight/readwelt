from dataclasses import FrozenInstanceError

import pytest

from readwelt import SpanAnchor


def test_span_anchor_is_frozen_and_round_trips_exact_text() -> None:
    anchor = SpanAnchor.create(
        snapshot_id="snapshot_1",
        section_id="section_1",
        text="prefix核心文本suffix",
        start_offset=6,
        end_offset=10,
    )

    assert anchor.exact_text == "核心文本"
    assert anchor.prefix == "prefix"
    assert anchor.suffix == "suffix"
    with pytest.raises(FrozenInstanceError):
        anchor.exact_text = "changed"  # type: ignore[misc]


def test_span_anchor_rejects_offset_drift() -> None:
    with pytest.raises(ValueError, match="offsets must span exact_text"):
        SpanAnchor(
            anchor_id="anchor_1",
            snapshot_id="snapshot_1",
            section_id="section_1",
            start_offset=0,
            end_offset=3,
            exact_text="too long",
        )
