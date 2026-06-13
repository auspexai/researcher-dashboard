"""Local-operations foundation (§8 Layer 2): the experiment.toml config editor.

Covers the TOML renderer's round-trip contract and the status/config routes —
including the gates (no workspace ⇒ unconfigured) and the merge that keeps a
tenant's unmanaged tables/keys across a form save.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from fastapi.testclient import TestClient

from auspexai_researcher_dashboard.config import ResearcherDashboardConfig
from auspexai_researcher_dashboard.local_ops import render_experiment_toml
from auspexai_researcher_dashboard.main import create_app


def _config(tmp_path: Path, *, workspace: bool, exec_enabled: bool = False):
    return ResearcherDashboardConfig(
        coord_url="http://127.0.0.1:9",
        bind_host="127.0.0.1",
        bind_port=4228,
        static_dir=tmp_path / "no-static",
        key_path=tmp_path / "maintainer_key",
        open_browser=False,
        workspace_dir=(tmp_path / "ws") if workspace else None,
        local_exec_enabled=exec_enabled,
    )


# ── renderer ───────────────────────────────────────────────────────────────


def test_render_round_trips_through_tomllib():
    data = {
        "experiment": {
            "label": "lab-x",
            "tenant_id": "lab",
            "contact": "you@lab.org",
            "model_id": "gemma-3-1b",
            "local_weights_required": True,
            "replication": 1,
            "duration_hours": 1.0,
            "research_goal": 'A goal with "quotes", a backslash \\, and an em-dash —.',
            "sensitive_content_flags": [],
        },
        "executor": {"command": ["python", "executor.py"]},
        "reducer": {"kind": "builtin_hash_agreement"},
        "driver": {"entrypoint": "drift_driver:build", "round_interval_seconds": 300},
    }
    rendered = render_experiment_toml(data)
    assert tomllib.loads(rendered) == data  # exact round-trip
    # canonical table order: [experiment] before [driver]
    assert rendered.index("[experiment]") < rendered.index("[driver]")
    # bool/list emitted as TOML, not Python literals
    assert "local_weights_required = true" in rendered
    assert "sensitive_content_flags = []" in rendered


def test_render_omits_none_values():
    rendered = render_experiment_toml({"experiment": {"label": "x", "journal": None}})
    assert "journal" not in rendered
    assert tomllib.loads(rendered)["experiment"] == {"label": "x"}


# ── status ─────────────────────────────────────────────────────────────────


def test_status_unconfigured_without_workspace(tmp_path: Path):
    client = TestClient(create_app(_config(tmp_path, workspace=False)))
    body = client.get("/api/v0/local/status").json()
    assert body["workspace_set"] is False
    assert body["workspace"] is None
    assert body["exec_enabled"] is False


def test_status_reports_workspace_and_exec_gate(tmp_path: Path):
    ws = tmp_path / "ws"
    (ws / "pkg").mkdir(parents=True)
    (ws / "experiment.toml").write_text('[experiment]\nlabel = "x"\n')
    client = TestClient(create_app(_config(tmp_path, workspace=True, exec_enabled=True)))
    body = client.get("/api/v0/local/status").json()
    assert body["workspace_set"] is True
    assert body["workspace"].endswith("/ws")
    assert body["workspace_exists"] is True
    assert body["config_present"] is True
    assert body["pkg_present"] is True
    assert body["exec_enabled"] is True


# ── config GET/POST ─────────────────────────────────────────────────────────


def test_get_config_empty_when_absent(tmp_path: Path):
    client = TestClient(create_app(_config(tmp_path, workspace=True)))
    body = client.get("/api/v0/local/config").json()
    assert body["present"] is False
    assert body["config"] == {}


def test_config_requires_workspace(tmp_path: Path):
    client = TestClient(create_app(_config(tmp_path, workspace=False)))
    assert client.get("/api/v0/local/config").status_code == 409
    assert client.post("/api/v0/local/config", json={"experiment": {}}).status_code == 409
    assert client.get("/api/v0/local/config").json()["error"]["kind"] == "unconfigured"


def test_post_config_writes_and_reads_back(tmp_path: Path):
    client = TestClient(create_app(_config(tmp_path, workspace=True)))
    payload = {
        "experiment": {"label": "lab-y", "tenant_id": "lab", "model_id": "m"},
        "executor": {"command": ["python", "executor.py"]},
    }
    r = client.post("/api/v0/local/config", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["written"].endswith("/ws/experiment.toml")
    # the written file parses and the GET round-trips it
    back = client.get("/api/v0/local/config").json()
    assert back["present"] is True
    assert back["config"]["experiment"]["label"] == "lab-y"
    assert back["config"]["executor"]["command"] == ["python", "executor.py"]


def test_post_config_merge_preserves_unmanaged(tmp_path: Path):
    """A form save touching [experiment] must not drop a tenant's [driver]
    table nor an unmanaged key inside [experiment]."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "experiment.toml").write_text(
        '[experiment]\nlabel = "old"\ncustom_knob = 7\n'
        '[driver]\nentrypoint = "drift_driver:build"\nround_interval_seconds = 300\n'
    )
    client = TestClient(create_app(_config(tmp_path, workspace=True)))
    r = client.post("/api/v0/local/config", json={"experiment": {"label": "new"}})
    assert r.status_code == 200, r.text
    cfg = client.get("/api/v0/local/config").json()["config"]
    assert cfg["experiment"]["label"] == "new"  # updated
    assert cfg["experiment"]["custom_knob"] == 7  # unmanaged key kept
    assert cfg["driver"]["entrypoint"] == "drift_driver:build"  # unmanaged table kept
    assert cfg["driver"]["round_interval_seconds"] == 300
