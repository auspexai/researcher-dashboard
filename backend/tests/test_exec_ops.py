"""Local SDK execution (§8 Layer 3): gates, the sync build/submit shells, and
the managed `run` lifecycle. subprocess is faked throughout — no real SDK,
network, or child process is launched."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from auspexai_researcher_dashboard import exec_ops
from auspexai_researcher_dashboard.config import ResearcherDashboardConfig
from auspexai_researcher_dashboard.exec_ops import _resolve_run_cwd
from auspexai_researcher_dashboard.main import create_app


def _config(tmp_path: Path, *, workspace: bool, exec_enabled: bool):
    ws = tmp_path / "ws"
    if workspace:
        (ws / "pkg").mkdir(parents=True)
    return ResearcherDashboardConfig(
        coord_url="http://127.0.0.1:9",
        bind_host="127.0.0.1",
        bind_port=4228,
        static_dir=tmp_path / "no-static",
        key_path=tmp_path / "maintainer_key",
        open_browser=False,
        workspace_dir=ws if workspace else None,
        local_exec_enabled=exec_enabled,
    )


def _client(tmp_path, monkeypatch, *, workspace=True, exec_enabled=True, sdk=True):
    monkeypatch.setattr(exec_ops, "_sdk_bin", lambda: "auspexai-tenant" if sdk else None)
    return TestClient(create_app(_config(tmp_path, workspace=workspace, exec_enabled=exec_enabled)))


class _FakePopen:
    """Stands in for a spawned `experiment run`. poll() is None until wait()
    (a clean stop) or _finish() sets a returncode."""

    last: _FakePopen | None = None

    def __init__(self, cmd, cwd=None, stdout=None, stderr=None, start_new_session=False):
        self.cmd, self.cwd = cmd, cwd
        self.pid = 4242
        self._rc: int | None = None
        _FakePopen.last = self

    def poll(self):
        return self._rc

    def wait(self, timeout=None):
        self._rc = 0
        return 0


# ── gates ───────────────────────────────────────────────────────────────────


def test_build_403_when_exec_disabled(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, exec_enabled=False)
    r = c.post("/api/v0/local/build")
    assert r.status_code == 403
    assert r.json()["error"]["kind"] == "exec_disabled"


def test_build_409_without_workspace(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, workspace=False)
    assert c.post("/api/v0/local/build").status_code == 409


def test_build_500_when_sdk_missing(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, sdk=False)
    r = c.post("/api/v0/local/build")
    assert r.status_code == 500
    assert "PATH" in r.json()["error"]["message"]


# ── sync build / submit ─────────────────────────────────────────────────────


def test_build_runs_sdk_and_returns_output(tmp_path, monkeypatch):
    seen = {}

    def fake_run(cmd, cwd=None, capture_output=False, text=False, timeout=None, check=False):
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        return subprocess.CompletedProcess(cmd, 0, stdout="label: x\n", stderr="")

    monkeypatch.setattr(exec_ops.subprocess, "run", fake_run)
    c = _client(tmp_path, monkeypatch)
    r = c.post("/api/v0/local/build")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["returncode"] == 0
    assert seen["cmd"][:3] == ["auspexai-tenant", "experiment", "build"]
    assert seen["cmd"][3].endswith("/ws/pkg")  # the configured pkg dir, not request input


def test_build_nonzero_exit_is_ok_false_not_http_error(tmp_path, monkeypatch):
    def fake_run(cmd, **k):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="ERROR: missing label")

    monkeypatch.setattr(exec_ops.subprocess, "run", fake_run)
    c = _client(tmp_path, monkeypatch)
    r = c.post("/api/v0/local/build")
    assert r.status_code == 200  # an expected outcome, surfaced not raised
    assert r.json()["ok"] is False
    assert "missing label" in r.json()["stderr"]


def test_submit_passes_key_path_not_material(tmp_path, monkeypatch):
    seen = {}

    def fake_run(cmd, **k):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="exp-XYZ", stderr="")

    monkeypatch.setattr(exec_ops.subprocess, "run", fake_run)
    c = _client(tmp_path, monkeypatch)
    assert c.post("/api/v0/local/submit").status_code == 200
    assert "--key" in seen["cmd"]
    key_arg = seen["cmd"][seen["cmd"].index("--key") + 1]
    assert key_arg.endswith("/maintainer_key")  # a PATH; the SDK reads the material


# ── run lifecycle ───────────────────────────────────────────────────────────


def test_run_start_status_stop(tmp_path, monkeypatch):
    monkeypatch.setattr(exec_ops.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(exec_ops.os, "killpg", lambda *a: None)  # never touch a real pgroup
    c = _client(tmp_path, monkeypatch)

    started = c.post("/api/v0/local/run")
    assert started.status_code == 200, started.text
    assert started.json()["started"] is True and started.json()["pid"] == 4242
    assert _FakePopen.last.cmd[:4] == ["auspexai-tenant", "experiment", "run", "latest"]
    assert "--doorbell" in _FakePopen.last.cmd

    status = c.get("/api/v0/local/run").json()
    assert status["present"] is True and status["running"] is True
    assert status["returncode"] is None and status["pid"] == 4242

    stop = c.post("/api/v0/local/run/stop")
    assert stop.status_code == 200
    assert stop.json()["stopped"] is True and stop.json()["returncode"] == 0


def test_run_conflicts_while_active(tmp_path, monkeypatch):
    monkeypatch.setattr(exec_ops.subprocess, "Popen", _FakePopen)
    c = _client(tmp_path, monkeypatch)
    assert c.post("/api/v0/local/run").status_code == 200
    second = c.post("/api/v0/local/run")  # first is still poll()==None
    assert second.status_code == 409
    assert second.json()["error"]["kind"] == "conflict"


def test_run_status_absent_before_any_run(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.get("/api/v0/local/run").json() == {"present": False}


def test_stop_without_run_is_404(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.post("/api/v0/local/run/stop").status_code == 404


# ── run cwd resolution ──────────────────────────────────────────────────────


def test_resolve_run_cwd_uses_driver_subdir(tmp_path):
    cfg = _config(tmp_path, workspace=True, exec_enabled=True)
    (cfg.workspace_dir / "experiment.toml").write_text('[driver]\nrun_cwd = "driver"\n')
    assert _resolve_run_cwd(cfg) == (cfg.workspace_dir / "driver").resolve()


def test_resolve_run_cwd_defaults_to_workspace(tmp_path):
    cfg = _config(tmp_path, workspace=True, exec_enabled=True)
    (cfg.workspace_dir / "experiment.toml").write_text('[experiment]\nlabel = "x"\n')
    assert _resolve_run_cwd(cfg) == cfg.workspace_dir


def test_resolve_run_cwd_rejects_traversal(tmp_path):
    cfg = _config(tmp_path, workspace=True, exec_enabled=True)
    (cfg.workspace_dir / "experiment.toml").write_text('[driver]\nrun_cwd = "../../etc"\n')
    assert _resolve_run_cwd(cfg) == cfg.workspace_dir  # escape rejected → workspace root
