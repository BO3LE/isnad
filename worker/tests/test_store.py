"""What SqlRunStore records about a file it saves."""

from __future__ import annotations

from worker.store import SqlRunStore


def _store(tmp_path=None):
    return SqlRunStore(session_factory=None, storage_root=str(tmp_path) if tmp_path else None)  # type: ignore[arg-type]


def test_a_saved_file_is_described_by_type_and_size(tmp_path):
    written = tmp_path / "artifacts" / "videos" / "abc"
    written.mkdir(parents=True)
    (written / "video.mp4").write_bytes(b"x" * 4036)

    mime, size = _store(tmp_path)._describe_file("artifacts/videos/abc/video.mp4")

    assert mime == "video/mp4"
    assert size == 4036


def test_a_file_that_is_not_where_we_expect_still_reports_its_type(tmp_path):
    mime, size = _store(tmp_path)._describe_file("artifacts/images/gone/image-1.png")
    assert mime == "image/png"
    assert size is None


def test_an_unknown_extension_is_not_guessed_at():
    mime, size = _store()._describe_file("artifacts/odd/thing.zzz")
    assert mime is None
    assert size is None
