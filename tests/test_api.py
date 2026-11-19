from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ingest import IngestError, check_url_safe
from app.main import app

SAMPLE = Path(__file__).parent / "data" / "squat_1.mp4"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_exercises(client):
    names = [e["name"] for e in client.get("/api/exercises").json()]
    assert "squat" in names


def test_index(client):
    assert "Rep Counter" in client.get("/").text


def test_sample_video_counts_one_squat(client):
    with SAMPLE.open("rb") as f:
        r = client.post("/api/count", data={"exercise": "squat"},
                        files={"file": ("squat.mp4", f, "video/mp4")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1
    rep = body["reps"][0]
    assert rep["start_s"] < rep["bottom_s"] < rep["end_s"]


def test_needs_exactly_one_input(client):
    assert client.post("/api/count", data={"exercise": "squat"}).status_code == 422


def test_unknown_exercise(client):
    r = client.post("/api/count", data={"exercise": "burpee", "url": "https://x.y/a.mp4"})
    assert r.status_code == 422


def test_rejects_non_video(client):
    r = client.post("/api/count", data={"exercise": "squat"},
                    files={"file": ("a.mp4", b"not a video", "video/mp4")})
    assert r.status_code == 400


@pytest.mark.parametrize("url", [
    "ftp://example.com/a.mp4", "http://127.0.0.1/a.mp4", "http://localhost/a.mp4",
    "http://10.0.0.5/a.mp4", "http://169.254.169.254/latest", "http://[::1]/a.mp4",
])
def test_ssrf_guard(url):
    with pytest.raises(IngestError):
        check_url_safe(url)


def test_url_blocked_via_api(client):
    r = client.post("/api/count", data={"exercise": "squat", "url": "http://127.0.0.1:8000/x"})
    assert r.status_code == 400
