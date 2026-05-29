"""Smoke tests: app factory builds, the health probe responds, and static
serving degrades gracefully when no SPA bundle is built yet."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from auspexai_researcher_dashboard.config import ResearcherDashboardConfig
from auspexai_researcher_dashboard.main import create_app


def _config(tmp_path: Path, *, key: bool) -> ResearcherDashboardConfig:
    key_path = tmp_path / "maintainer_key"
    if key:
        key_path.write_text("not-a-real-key")
    return ResearcherDashboardConfig(
        coord_url="http://127.0.0.1:9",  # unreachable on purpose
        bind_host="127.0.0.1",
        bind_port=4228,
        static_dir=tmp_path / "no-static",  # absent → placeholder branch
        key_path=key_path,
        open_browser=False,
    )


def test_health_reports_version_and_phase(tmp_path: Path) -> None:
    client = TestClient(create_app(_config(tmp_path, key=False)))
    r = client.get("/api/v0/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["phase"].startswith("R-D2")
    # Coordinator unreachable → reachable is False, not an exception.
    assert body["coord"]["reachable"] is False


def test_health_reports_key_presence(tmp_path: Path) -> None:
    present = TestClient(create_app(_config(tmp_path, key=True)))
    assert present.get("/api/v0/health").json()["identity"]["key_present"] is True


def test_health_reports_key_absence(tmp_path: Path) -> None:
    absent = TestClient(create_app(_config(tmp_path, key=False)))
    body = absent.get("/api/v0/health").json()
    assert body["identity"]["key_present"] is False
    # Presence flag only — never the key material itself.
    assert "key" not in {
        k.lower() for k in body["identity"] if k != "key_path" and k != "key_present"
    }


def test_placeholder_served_when_no_static_bundle(tmp_path: Path) -> None:
    client = TestClient(create_app(_config(tmp_path, key=False)))
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "frontend bundle not present"


def test_static_dir_present_but_unbuilt_does_not_crash(tmp_path: Path) -> None:
    """Regression: the scaffold ships static/.gitkeep, so the static_dir EXISTS
    before any `vite build` — but has no index.html / _app. The app must boot
    and serve the placeholder, not raise mounting a missing _app directory."""
    static = tmp_path / "static"
    static.mkdir()
    (static / ".gitkeep").write_text("")  # dir present, no built bundle
    config = ResearcherDashboardConfig(
        coord_url="http://127.0.0.1:9",
        bind_host="127.0.0.1",
        bind_port=4228,
        static_dir=static,
        key_path=tmp_path / "maintainer_key",
        open_browser=False,
    )
    client = TestClient(create_app(config))  # must not raise
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "frontend bundle not present"
