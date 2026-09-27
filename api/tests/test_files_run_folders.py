"""Development `/files` serves the per-run folders the worker writes (`{user_id}/{run_id}/...`)."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import create_app
from api.settings import ApiSettings


def test_a_file_in_a_run_folder_is_served(tmp_path):
    user_id, run_id = uuid4(), uuid4()
    folder = tmp_path / str(user_id) / str(run_id) / "videos" / "ab12"
    folder.mkdir(parents=True)
    (folder / "video.mp4").write_bytes(b"mp4")
    app = create_app(ApiSettings(environment="test", storage_root=str(tmp_path)))

    response = TestClient(app).get(f"/files/{user_id}/{run_id}/videos/ab12/video.mp4")

    assert response.status_code == 200
    assert response.content == b"mp4"
