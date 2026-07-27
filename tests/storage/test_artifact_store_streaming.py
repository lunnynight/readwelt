from __future__ import annotations

from pathlib import Path

import pytest

from readwelt.storage import ArtifactStore, ProjectLayout


def _store(tmp_path: Path) -> ArtifactStore:
    layout = ProjectLayout.resolve(tmp_path / "project")
    layout.initialize()
    return ArtifactStore(layout)


def test_bounded_read_does_not_materialize_complete_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    content = bytes(range(256)) * 512
    reference = store.put_bytes(content, artifact_type="large-test")

    def forbid_full_read(_path: Path) -> bytes:
        raise AssertionError("bounded reads must not call Path.read_bytes")

    monkeypatch.setattr(Path, "read_bytes", forbid_full_read)

    assert store.read_range(reference, offset=64_000, length=4_096) == content[64_000:68_096]


def test_streaming_read_is_chunk_bounded_and_digest_verified(tmp_path: Path) -> None:
    store = _store(tmp_path)
    content = b"source-plane" * 20_000
    reference = store.put_bytes(content, artifact_type="large-test")

    chunks = tuple(store.iter_bytes(reference, chunk_size=4_096))

    assert b"".join(chunks) == content
    assert max(map(len, chunks)) <= 4_096
    assert len(chunks) > 1


@pytest.mark.parametrize(
    ("offset", "length"),
    [(-1, 1), (0, -1)],
)
def test_bounded_read_rejects_negative_bounds(
    tmp_path: Path,
    offset: int,
    length: int,
) -> None:
    store = _store(tmp_path)
    reference = store.put_bytes(b"value", artifact_type="test")

    with pytest.raises(ValueError):
        store.read_range(reference, offset=offset, length=length)


def test_streaming_read_detects_corrupt_artifact_after_exhaustion(tmp_path: Path) -> None:
    store = _store(tmp_path)
    reference = store.put_bytes(b"trusted", artifact_type="test")
    path = (tmp_path / "project" / reference.path).resolve()
    path.write_bytes(b"corrupt")

    with pytest.raises(ValueError, match="artifact size mismatch|artifact digest mismatch"):
        tuple(store.iter_bytes(reference, chunk_size=2))
