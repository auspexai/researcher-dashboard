"""The Drift Benchmark surfaces (D16.4 exposure): the per-run report persists
to the shared runs/ layout and the /benchmarks pane aggregates every saved
report — the internal precursor of the eventual public board."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from auspexai_researcher_dashboard.config import ResearcherDashboardConfig
from auspexai_researcher_dashboard.main import create_app


def _config(tmp_path: Path) -> ResearcherDashboardConfig:
    return ResearcherDashboardConfig(
        coord_url="http://127.0.0.1:9",  # unreachable on purpose
        bind_host="127.0.0.1",
        bind_port=4228,
        static_dir=tmp_path / "no-static",
        key_path=tmp_path / "tenant_key",
        open_browser=False,
        workspace_dir=tmp_path,
    )


def _saved_report(tmp_path: Path, label: str, ref: str, peak: float, at: str) -> None:
    d = tmp_path / "runs" / label
    d.mkdir(parents=True, exist_ok=True)
    (d / f"benchmark_vs_{ref}.json").write_text(
        json.dumps(
            {
                "schema": "auspexai-drift-benchmark-report/v0",
                "computed_at": at,
                "observation": {"experiment_id": f"exp-{label}", "label": label},
                "reference": {"experiment_id": ref, "label": "calibration"},
                "report": {
                    "peak_eu": peak,
                    "breadth": 0.33,
                    "byte_divergence_rate": 0.77,
                    "diverged_units_total": None,
                    "probes": [{"key": "p-a"}],
                },
            }
        )
    )


def test_benchmarks_pane_aggregates_saved_reports(tmp_path: Path) -> None:
    _saved_report(tmp_path, "run-a", "exp-ref", 6.67, "2026-07-03T10:00:00+00:00")
    _saved_report(tmp_path, "run-b", "exp-ref", 0.0, "2026-07-03T12:00:00+00:00")
    client = TestClient(create_app(_config(tmp_path)))
    r = client.get("/api/v0/benchmarks")
    assert r.status_code == 200
    rows = r.json()["benchmarks"]
    assert len(rows) == 2
    # Newest first; every row remains traceable to its evidence pair.
    assert rows[0]["observation"]["experiment_id"] == "exp-run-b"
    assert rows[1]["peak_eu"] == 6.67
    assert rows[1]["reference"]["experiment_id"] == "exp-ref"


def test_benchmarks_pane_empty_and_garbage_tolerant(tmp_path: Path) -> None:
    d = tmp_path / "runs" / "run-x"
    d.mkdir(parents=True)
    (d / "benchmark_vs_bad.json").write_text("{not json")
    client = TestClient(create_app(_config(tmp_path)))
    r = client.get("/api/v0/benchmarks")
    assert r.status_code == 200
    assert r.json()["benchmarks"] == []


def test_benchmark_endpoint_refuses_unreachable_coordinator(tmp_path: Path) -> None:
    # The compute path fails LOUDLY when bundles can't be collected — never a
    # fabricated score. (Full happy-path scoring is covered by the SDK's own
    # bundle tests; here we pin the endpoint's error envelope.)
    client = TestClient(create_app(_config(tmp_path)))
    r = client.get("/api/v0/experiments/exp-a/benchmark?reference=exp-b")
    assert r.status_code >= 400


def test_experiment_benchmarks_lists_only_its_own(tmp_path: Path) -> None:
    # The tab's primary content: THIS experiment's saved reports — not a picker.
    _saved_report(tmp_path, "run-a", "exp-ref", 6.67, "2026-07-03T10:00:00+00:00")
    _saved_report(tmp_path, "run-a", "exp-ref2", 1.1, "2026-07-03T11:00:00+00:00")
    _saved_report(tmp_path, "run-b", "exp-ref", 0.0, "2026-07-03T12:00:00+00:00")
    client = TestClient(create_app(_config(tmp_path)))
    r = client.get("/api/v0/experiments/exp-run-a/benchmarks")
    assert r.status_code == 200
    rows = r.json()["benchmarks"]
    assert len(rows) == 2
    assert all(row["observation"]["experiment_id"] == "exp-run-a" for row in rows)
    # Newest first; the full report rides along (no second fetch to expand).
    assert rows[0]["reference"]["experiment_id"] == "exp-ref2"
    assert rows[0]["report"]["peak_eu"] == 1.1
