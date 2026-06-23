"""Export-to-disk save (Part B: the CLI≡UI download layout).

A Web-UI export saves the verified bundle to the shared runs/<label>/bundle.json
layout — the same place the CLI's `experiment export` writes — so a click and the
CLI organize downloads identically.
"""

from __future__ import annotations

import json
from pathlib import Path

from auspexai_researcher_dashboard.api import _runs_base, _save_bundle


class _Cfg:
    def __init__(self, workspace_dir: Path | None = None) -> None:
        self.workspace_dir = workspace_dir


def test_save_to_workspace_runs(tmp_path: Path) -> None:
    p = _save_bundle(_Cfg(workspace_dir=tmp_path), "drift-a1", {"x": 1})
    expected = tmp_path / "runs" / "drift-a1" / "bundle.json"
    assert p == str(expected)
    assert json.loads(expected.read_text()) == {"x": 1}


def test_save_no_workspace_uses_home_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    p = _save_bundle(_Cfg(workspace_dir=None), "lab-x", {"y": 2})
    expected = (
        tmp_path / ".local" / "share" / "auspexai-researcher" / "runs" / "lab-x" / "bundle.json"
    )
    assert p == str(expected)
    assert expected.exists()


def test_save_unsafe_label_returns_none(tmp_path: Path) -> None:
    # RunLayout rejects a traversal label → the best-effort save returns None
    # (the endpoint still returns the bundle to the browser).
    assert _save_bundle(_Cfg(workspace_dir=tmp_path), "../escape", {"z": 3}) is None


def test_runs_base_prefers_workspace(tmp_path: Path) -> None:
    assert _runs_base(_Cfg(workspace_dir=tmp_path)) == tmp_path / "runs"
