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


def _sync_client(tmp_path: Path) -> TestClient:
    """A client that scores benchmarks INLINE rather than in a background task, so a
    test sees the materialize outcome in a single request (production backgrounds it
    and the frontend polls)."""
    app = create_app(_config(tmp_path))
    app.state.sync_materialize = True
    return TestClient(app)


def _saved_report(tmp_path: Path, label: str, ref: str, peak: float, at: str) -> None:
    _saved_report_at(tmp_path / "runs", label, ref, peak, at)


def _saved_report_at(base: Path, label: str, ref: str, peak: float, at: str) -> None:
    d = base / label
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


def _declaration(tmp_path: Path, label: str, exp_id: str, ref: str) -> None:
    d = tmp_path / "runs" / label
    d.mkdir(parents=True, exist_ok=True)
    (d / "benchmark_reference.json").write_text(
        json.dumps(
            {
                "schema": "auspexai-benchmark-declaration/v0",
                "mode": "fixed_reference",
                "experiment_id": exp_id,
                "label": label,
                "reference_experiment_id": ref,
            }
        )
    )


def test_declared_but_uncollectable_reports_why_not_a_score(tmp_path: Path) -> None:
    # A declared reference with an unreachable coordinator: the endpoint says
    # WHY it could not materialize — never a fabricated score, never a 500.
    _declaration(tmp_path, "run-a", "exp-run-a", "exp-baseline")
    client = _sync_client(tmp_path)
    r = client.get("/api/v0/experiments/exp-run-a/benchmarks")
    assert r.status_code == 200
    body = r.json()
    assert body["benchmarks"] == []
    assert body["declaration"]["reference_experiment_id"] == "exp-baseline"
    assert "could not collect" in (body["materialize_error"] or "")


def test_saved_score_needs_no_recompute_and_no_declaration(tmp_path: Path) -> None:
    _saved_report(tmp_path, "run-a", "exp-ref", 6.67, "2026-07-03T10:00:00+00:00")
    client = TestClient(create_app(_config(tmp_path)))
    r = client.get("/api/v0/experiments/exp-run-a/benchmarks")
    body = r.json()
    assert body["benchmarks"][0]["report"]["peak_eu"] == 6.67
    assert body["declaration"] is None
    assert body["materialize_error"] is None


def test_baseline_sees_its_track(tmp_path: Path) -> None:
    # The flip side: the reference experiment's page shows the runs scored
    # against it — the drift series (the shape the public board publishes).
    _saved_report(tmp_path, "run-a", "exp-baseline", 6.67, "2026-07-03T10:00:00+00:00")
    _saved_report(tmp_path, "run-b", "exp-baseline", 0.0, "2026-07-03T12:00:00+00:00")
    client = TestClient(create_app(_config(tmp_path)))
    r = client.get("/api/v0/experiments/exp-baseline/benchmarks")
    body = r.json()
    assert body["benchmarks"] == []  # the baseline itself scores against nothing
    track = body["track"]
    assert [row["observation"]["experiment_id"] for row in track] == ["exp-run-b", "exp-run-a"]
    assert track[1]["peak_eu"] == 6.67


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


def _self_declaration(tmp_path: Path, label: str, exp_id: str, k: int = 5) -> None:
    d = tmp_path / "runs" / label
    d.mkdir(parents=True, exist_ok=True)
    (d / "benchmark_reference.json").write_text(
        json.dumps(
            {
                "schema": "auspexai-benchmark-declaration/v0",
                "mode": "self_baseline",
                "experiment_id": exp_id,
                "label": label,
                "baseline_rounds": k,
                "calibrate_envelope": False,
            }
        )
    )


def test_self_baseline_declaration_does_not_ask_for_experiment_none(tmp_path: Path) -> None:
    # Regression: a self_baseline run has NO reference experiment. The endpoint must
    # not str()-wrap the absent reference id into "None" and ask the coordinator for
    # experiment 'None'. With an unreachable coordinator it reports the collect
    # failure for THIS run's own bundle — never "no experiment with id 'None'".
    _self_declaration(tmp_path, "run-self", "exp-run-self", k=5)
    client = _sync_client(tmp_path)
    body = client.get("/api/v0/experiments/exp-run-self/benchmarks").json()
    assert body["benchmarks"] == []
    assert body["declaration"]["mode"] == "self_baseline"
    err = body["materialize_error"] or ""
    assert "could not collect the evidence bundle" in err
    assert "None" not in err  # the old bug surfaced as "no experiment with id 'None'"


def test_self_baseline_first_view_scores_in_the_background(tmp_path: Path) -> None:
    # Production path (no sync flag): the first view KICKS OFF a background score and
    # returns materializing:true immediately — never a minute-long block on a bare
    # spinner. The frontend polls until the score lands (or an error is reported).
    _self_declaration(tmp_path, "run-bg", "exp-run-bg", k=5)
    client = TestClient(create_app(_config(tmp_path)))
    body = client.get("/api/v0/experiments/exp-run-bg/benchmarks").json()
    assert body["benchmarks"] == []
    assert body["materializing"] is True
    assert body["materialize_error"] is None  # still running — no fabricated error/score


def test_self_baseline_zero_k_reports_why_not_a_score(tmp_path: Path) -> None:
    # baseline_rounds=0 → no baseline window to self-reference; say so, don't crash.
    _self_declaration(tmp_path, "run-self0", "exp-run-self0", k=0)
    client = _sync_client(tmp_path)
    body = client.get("/api/v0/experiments/exp-run-self0/benchmarks").json()
    assert body["benchmarks"] == []
    assert "baseline_rounds is 0" in (body["materialize_error"] or "")


def _saved_self_report(tmp_path: Path, label: str, exp_id: str, peak: float, at: str) -> None:
    d = tmp_path / "runs" / label
    d.mkdir(parents=True, exist_ok=True)
    (d / "benchmark_self.json").write_text(
        json.dumps(
            {
                "schema": "auspexai-drift-benchmark-report/v0",
                "computed_at": at,
                "observation": {"experiment_id": exp_id, "label": label},
                "reference": {"self_baseline": {"baseline_rounds": 5}},
                "report": {
                    "peak_eu": peak,
                    "breadth": 0.1,
                    "byte_divergence_rate": 0.0,
                    "diverged_units_total": None,
                    "probes": [{"key": "p-a"}],
                },
            }
        )
    )


def test_saved_self_baseline_report_aggregated_and_no_recompute(tmp_path: Path) -> None:
    # A saved benchmark_self.json is scanned like a benchmark_vs_* one, shows on the
    # run's tab, and — being already saved — is not recomputed (materialize_error None).
    _saved_self_report(tmp_path, "run-self", "exp-run-self", 2.5, "2026-07-15T10:00:00+00:00")
    _self_declaration(tmp_path, "run-self", "exp-run-self", k=5)
    client = TestClient(create_app(_config(tmp_path)))
    body = client.get("/api/v0/experiments/exp-run-self/benchmarks").json()
    assert body["benchmarks"][0]["report"]["peak_eu"] == 2.5
    assert body["benchmarks"][0]["reference"]["self_baseline"]["baseline_rounds"] == 5
    assert body["materialize_error"] is None  # saved → no recompute against a dead coord
    rows = client.get("/api/v0/benchmarks").json()["benchmarks"]
    assert any(r["observation"]["experiment_id"] == "exp-run-self" for r in rows)


def test_reads_union_of_bases_including_env_runs_dir(tmp_path: Path, monkeypatch) -> None:
    # The 2026-07-03 live bug: launch wrote beside the run in the CLI's runs
    # dir; the dashboard scanned only its own base and reported "no benchmark"
    # for a scored run. Reads now union every candidate base.
    cli_base = tmp_path / "cli-runs"
    _saved_report_at(cli_base, "run-a", "exp-ref", 6.67, "2026-07-03T10:00:00+00:00")
    monkeypatch.setenv("AUSPEXAI_RUNS_DIR", str(cli_base))
    client = TestClient(create_app(_config(tmp_path)))
    r = client.get("/api/v0/experiments/exp-run-a/benchmarks")
    assert r.status_code == 200
    assert r.json()["benchmarks"][0]["report"]["peak_eu"] == 6.67
