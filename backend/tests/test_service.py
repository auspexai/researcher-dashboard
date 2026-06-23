"""Tests for the persistent-service manager (`service.py`).

Covers unit/plist rendering and the cross-platform command sequence with an
injected runner + tmp paths — no real launchctl/systemctl is touched, so the
tests run identically on any host.
"""

from __future__ import annotations

import plistlib
import subprocess

import pytest

from auspexai_researcher_dashboard import service as svc
from auspexai_researcher_dashboard.service import (
    LAUNCHD_LABEL,
    SYSTEMD_UNIT,
    ServiceManager,
    render_launchd_plist,
    render_systemd_unit,
)


class FakeRunner:
    """Records commands; returns a canned CompletedProcess."""

    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.calls: list[list[str]] = []
        self._rc = returncode
        self._out = stdout

    def __call__(self, cmd):
        self.calls.append(list(cmd))
        return subprocess.CompletedProcess(list(cmd), self._rc, self._out, "")

    def ran(self, *needles: str) -> bool:
        """True if some recorded command contains all the given tokens."""
        return any(all(n in c for n in needles) for c in (" ".join(x) for x in self.calls))


@pytest.fixture
def paths(tmp_path, monkeypatch):
    plist = tmp_path / "agent.plist"
    unit = tmp_path / "unit.service"
    monkeypatch.setattr(svc, "launchd_plist_path", lambda: plist)
    monkeypatch.setattr(svc, "systemd_unit_path", lambda: unit)
    monkeypatch.setattr(svc, "dashboard_executable", lambda: "/venv/bin/auspexai-dashboard")
    monkeypatch.setattr(svc, "STATE_DIR", tmp_path / "state")
    return {"plist": plist, "unit": unit}


# ---- rendering ---------------------------------------------------------------


def test_render_launchd_plist():
    spec = plistlib.loads(render_launchd_plist("/venv/bin/auspexai-dashboard", port=4321))
    assert spec["Label"] == LAUNCHD_LABEL
    assert spec["ProgramArguments"] == ["/venv/bin/auspexai-dashboard", "serve", "--no-browser"]
    assert spec["RunAtLoad"] is True
    assert spec["KeepAlive"] is True
    assert spec["EnvironmentVariables"]["PORT"] == "4321"


def test_render_systemd_unit():
    text = render_systemd_unit("/venv/bin/auspexai-dashboard", port=4321)
    assert "ExecStart=/venv/bin/auspexai-dashboard serve --no-browser" in text
    assert "Environment=PORT=4321" in text
    assert "Restart=on-failure" in text
    assert "WantedBy=default.target" in text


# ---- dispatch / install ------------------------------------------------------


def test_install_darwin_writes_plist_and_loads(paths):
    fake = FakeRunner()
    mgr = ServiceManager(run=fake, platform="darwin", port=4228)
    mgr.install()
    spec = plistlib.loads(paths["plist"].read_bytes())
    assert spec["ProgramArguments"][1:] == ["serve", "--no-browser"]
    assert fake.ran("launchctl", "load", "-w")
    assert not paths["unit"].exists()  # didn't touch the linux path


def test_install_linux_writes_unit_and_enables(paths):
    fake = FakeRunner()
    mgr = ServiceManager(run=fake, platform="linux", port=4228)
    mgr.install()
    assert "serve --no-browser" in paths["unit"].read_text()
    assert fake.ran("systemctl", "--user", "daemon-reload")
    assert fake.ran("systemctl", "--user", "enable", "--now", SYSTEMD_UNIT)
    assert not paths["plist"].exists()


def test_install_unsupported_raises(paths):
    mgr = ServiceManager(run=FakeRunner(), platform="win32")
    assert mgr.supported is False
    with pytest.raises(RuntimeError, match="not supported"):
        mgr.install()


@pytest.mark.parametrize(
    ("platform", "ok"),
    [("darwin", True), ("linux", True), ("linux2", True), ("win32", False)],
)
def test_supported(platform, ok):
    assert ServiceManager(platform=platform).supported is ok


# ---- restart / status / uninstall -------------------------------------------


def test_restart_installs_when_absent(paths):
    fake = FakeRunner()
    ServiceManager(run=fake, platform="darwin").restart()
    # No prior plist → restart falls through to install (writes + loads).
    assert paths["plist"].exists()
    assert fake.ran("launchctl", "load")


def test_restart_bounces_existing_linux(paths):
    paths["unit"].write_text("existing")
    fake = FakeRunner()
    ServiceManager(run=fake, platform="linux").restart()
    assert fake.ran("systemctl", "--user", "restart", SYSTEMD_UNIT)


def test_status_linux_returns_active(paths):
    fake = FakeRunner(stdout="active\n")
    assert ServiceManager(run=fake, platform="linux").status() == "active"


def test_uninstall_darwin_removes_plist(paths):
    paths["plist"].write_bytes(b"x")
    fake = FakeRunner()
    ServiceManager(run=fake, platform="darwin").uninstall()
    assert not paths["plist"].exists()
    assert fake.ran("launchctl", "unload")
