"""Tenant-scoped read proxy routes (R-D2).

Thin pass-through to the coordinator: sign the request → forward → return the
coordinator's JSON verbatim. No filtering happens here — the coordinator scopes
the response to the signing tenant and field-filters it server-side
(researcher_dashboard_design.md §5; the dashboard "is dumb on purpose").

A `CoordinatorError` is rendered as a stable error envelope the SPA branches on:
    {"error": {"kind": "...", "message": "...", "coordinator_status": 403 | null}}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from auspexai_tenant.evidence import BundleVerification, verify_bundle
from auspexai_tenant.github_device_flow import default_client_id, request_device_code
from auspexai_tenant.runs import RunLayout
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .coordinator import CoordinatorClient, CoordinatorError


def _runs_base(cfg) -> Path:
    """Where the dashboard WRITES run artifacts: the configured workspace's
    `runs/` when set, else the SDK's stable per-user base — the same path a
    fresh CLI context resolves, so both surfaces converge without config."""
    if getattr(cfg, "workspace_dir", None):
        return cfg.workspace_dir / "runs"
    from auspexai_tenant.runs import stable_runs_base

    return stable_runs_base()


def _runs_bases(cfg) -> list[Path]:
    """Every base the dashboard READS, in precedence order. The 2026-07-03 live
    lesson (a launch-scored run showed "no benchmark" in the dashboard): the CLI
    and the dashboard resolved DIFFERENT runs dirs, and each surface saw only
    its own. Reads now union: the workspace base, $AUSPEXAI_RUNS_DIR, the SDK's
    stable per-user base, and this app's pre-fix legacy dir (where reports
    computed before the unification live)."""
    import os

    bases: list[Path] = [_runs_base(cfg)]
    env = os.environ.get("AUSPEXAI_RUNS_DIR")
    if env:
        bases.append(Path(env).expanduser())
    from auspexai_tenant.runs import stable_runs_base

    bases.append(stable_runs_base())
    bases.append(Path.home() / ".local" / "share" / "auspexai-researcher" / "runs")
    seen: set[Path] = set()
    return [b for b in bases if not (b in seen or seen.add(b))]


def _save_bundle(cfg, key: str, bundle: dict[str, Any]) -> str | None:
    """Save the verified bundle to the shared `runs/<label>/bundle.json` layout —
    the single source of truth the CLI uses (design §8) — so a click and the CLI
    organize downloads identically. Best-effort: a write failure never fails the
    export (the browser still receives the bundle for display/download)."""
    try:
        layout = RunLayout(key, base=_runs_base(cfg)).ensure()
        path = layout.bundle_path()
        path.write_text(json.dumps(bundle, indent=2))
        return str(path)
    except (OSError, ValueError):
        return None


def _scan_benchmark_records(bases: Path | list[Path]) -> list[dict[str, Any]]:
    """Every saved drift-benchmark record under the given runs base(s) (full
    records, with their path), newest first, de-duplicated by (observation,
    reference). Garbage-tolerant: an unreadable file is skipped."""
    records: list[dict[str, Any]] = []
    candidates: list[Path] = []
    for base in [bases] if isinstance(bases, Path) else bases:
        try:
            candidates.extend(sorted(base.glob("*/benchmark_vs_*.json")))
        except OSError:
            continue
    for path in candidates:
        try:
            rec = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict):
            rec["path"] = str(path)
            records.append(rec)
    records.sort(key=lambda r: r.get("computed_at") or "", reverse=True)
    seen: set[tuple] = set()
    deduped = []
    for r in records:
        key = (
            (r.get("observation") or {}).get("experiment_id"),
            (r.get("reference") or {}).get("experiment_id"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped


def _find_benchmark_declaration(
    bases: Path | list[Path], experiment_id: str
) -> dict[str, Any] | None:
    """The run's benchmark declaration (written at launch beside the run) —
    runs/*/benchmark_reference.json with a matching experiment_id, searched
    across every readable base."""
    candidates: list[Path] = []
    for base in [bases] if isinstance(bases, Path) else bases:
        try:
            candidates.extend(sorted(base.glob("*/benchmark_reference.json")))
        except OSError:
            continue
    for path in candidates:
        try:
            rec = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and rec.get("experiment_id") == experiment_id:
            return rec
    return None


def _rekor_status(bundle: dict[str, Any]) -> dict[str, Any]:
    """The attestation's transparency-log anchor, read straight from the bundle —
    `pending` until the coordinator's hourly Rekor sweep anchors it, so a fresh
    run reads as 'pending', not 'failed'."""
    att = bundle.get("attestation")
    if isinstance(att, dict):
        idx = att.get("rekor_log_index") or (att.get("rekor") or {}).get("log_index")
        if idx:
            return {"state": "anchored", "log_index": idx}
    return {"state": "pending"}


def _shape_verification(v: BundleVerification, bundle: dict[str, Any]) -> dict[str, Any]:
    """Shape an SDK `BundleVerification` (run locally, on this machine) for the UI:
    overall verdict + a named-check list. Verification is OFFLINE by design so a
    not-yet-anchored attestation never reads as a failure; the Rekor anchor is
    surfaced separately as status."""

    def tri(x: bool | None) -> str:
        return "na" if x is None else ("pass" if x else "fail")

    att = v.attestation
    ws = v.worker_signatures
    checks: list[dict[str, Any]] = [
        {"name": "Custody signature", "state": tri(v.transfer_signature_valid)},
        {
            "name": "Custody signer",
            "state": tri(v.transfer_signer_authorized),
            "detail": v.signer_pin_mode
            + ("" if v.signer_grounded else " · not externally grounded"),
        },
        {"name": "Attestation", "state": tri(att.ok if att is not None else None)},
        {"name": "Root unification", "state": tri(v.root_unified)},
        {"name": "Completeness", "state": tri(v.completeness_ok)},
        {"name": "Input binding", "state": tri(v.inputs_bound_ok)},
        {"name": "Apparatus footprint", "state": tri(v.footprint_ok)},
        # C7 Inc 4: tolerance units' attested representative hashes recompute
        # from the bundled evidence (n/a when the bundle has no tolerance units).
        {"name": "Tolerance evidence", "state": tri(v.tolerance_evidence_ok)},
        {
            "name": "Worker signatures",
            "state": "pass" if ws.ok else "fail",
            "detail": f"{ws.verified} verified"
            + (f" · {len(ws.failed)} FAILED" if ws.failed else ""),
        },
    ]
    return {"ok": v.ok, "checks": checks, "rekor": _rekor_status(bundle)}


def build_api_router() -> APIRouter:
    router = APIRouter(prefix="/api/v0")

    def _envelope(e: CoordinatorError) -> JSONResponse:
        return JSONResponse(
            status_code=e.http_status,
            content={
                "error": {
                    "kind": e.kind,
                    "message": e.message,
                    "coordinator_status": e.coord_status,
                }
            },
        )

    def _client(request: Request) -> CoordinatorClient:
        # Test seam: production leaves this unset (real network); tests set an
        # httpx.MockTransport on app.state to exercise the signed proxy offline.
        transport = getattr(request.app.state, "coord_transport", None)
        return CoordinatorClient(request.app.state.config, transport=transport)

    async def _proxy(request: Request, path: str) -> JSONResponse:
        # Forward any query string (e.g. work-units ?status_filter=...). The
        # coordinator's RFC 9421 signature covers @path only, not @query, so the
        # query is safe to pass through unsigned.
        query = request.url.query
        full_path = f"{path}?{query}" if query else path
        try:
            data = await _client(request).get_json(full_path)
        except CoordinatorError as e:
            return _envelope(e)
        return JSONResponse(content=data)

    async def _proxy_post(request: Request, path: str) -> JSONResponse:
        # Lifecycle actions (R-D4): signed POST, no body/query. The coordinator
        # owns authorization (own-tenant researcher) + transition validity; a
        # 409 comes back as a `conflict`-kind envelope carrying the coordinator's
        # own reason (invalid_status_transition / finalize_not_applicable).
        try:
            data = await _client(request).post_json(path)
        except CoordinatorError as e:
            return _envelope(e)
        return JSONResponse(content=data)

    @router.post("/accounts/orcid/start")
    async def orcid_link_start(request: Request) -> JSONResponse:
        """Begin linking the researcher's ORCID (D8): a signed POST to the
        coordinator returns the ORCID authorize URL the SPA opens. A 503 envelope
        means ORCID isn't configured on the coordinator yet."""
        return await _proxy_post(request, "/api/v0/accounts/orcid/start")

    @router.post("/accounts/bind")
    async def account_bind(request: Request) -> JSONResponse:
        """Tier-1 connect: bind this dashboard's key DIRECTLY to an account (no
        tenant, no approval — like a worker connecting). The body carries the
        verified IdP token {idp, access_token}; the local key signs the request
        (proof of possession) and forwards to the coordinator, which binds the
        key → a CredentialClass.ACCOUNT credential."""
        return await _proxy_post_body(request, "/api/v0/accounts/bind", status_code=200)

    @router.post("/accounts/github/device/start")
    async def github_device_start() -> JSONResponse:
        """Begin GitHub's device flow (Tier-1 connect via GitHub). Returns the
        user_code + verification_uri to show + the device_code to poll. Brokered
        server-side — GitHub's device endpoints are not browser-CORS-friendly."""
        try:
            code = await run_in_threadpool(request_device_code, client_id=default_client_id())
        except Exception as e:
            return JSONResponse(
                status_code=502,
                content={
                    "error": {
                        "kind": "unreachable",
                        "message": f"GitHub device-code request failed: {e}",
                        "coordinator_status": None,
                    }
                },
            )
        return JSONResponse(
            content={
                "user_code": code.user_code,
                "verification_uri": code.verification_uri,
                "device_code": code.device_code,
                "interval": code.interval,
            }
        )

    @router.post("/accounts/github/device/poll")
    async def github_device_poll(request: Request) -> JSONResponse:
        """Poll GitHub's token endpoint ONCE for the device flow. Returns
        {access_token} when authorized, else {status: 'pending', error}."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        device_code = (body or {}).get("device_code")
        if not device_code:
            return JSONResponse(
                status_code=422,
                content={
                    "error": {
                        "kind": "client_error",
                        "message": "device_code required",
                        "coordinator_status": None,
                    }
                },
            )

        def _poll() -> dict:
            with httpx.Client(timeout=10.0) as c:
                r = c.post(
                    "https://github.com/login/oauth/access_token",
                    data={
                        "client_id": default_client_id(),
                        "device_code": device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                    headers={"Accept": "application/json"},
                )
                return r.json()

        try:
            payload = await run_in_threadpool(_poll)
        except Exception as e:
            return JSONResponse(
                status_code=502,
                content={
                    "error": {
                        "kind": "unreachable",
                        "message": f"GitHub token poll failed: {e}",
                        "coordinator_status": None,
                    }
                },
            )
        if payload.get("access_token"):
            return JSONResponse(content={"access_token": payload["access_token"]})
        return JSONResponse(content={"status": "pending", "error": payload.get("error")})

    @router.post("/tenant-applications")
    async def submit_tenant_application(request: Request) -> JSONResponse:
        """Submit a tenant application (ORCID-rooted onboarding). The body carries
        the ORCID implicit-flow access token (`orcid_access_token`) + the
        application metadata; the local key signs it (proof of possession). The
        coordinator verifies the token via ORCID userinfo, roots the account on
        ORCID, and creates the pending application."""
        return await _proxy_post_body(request, "/api/v0/tenant-applications", status_code=201)

    @router.get("/experiments")
    async def list_experiments(request: Request) -> JSONResponse:
        """My experiments — tenant-scoped list."""
        return await _proxy(request, "/api/v0/experiments")

    @router.get("/experiments/{experiment_id}")
    async def get_experiment(request: Request, experiment_id: str) -> JSONResponse:
        """My experiment — detail."""
        return await _proxy(request, f"/api/v0/experiments/{experiment_id}")

    @router.get("/experiments/{experiment_id}/work-units")
    async def list_work_units(request: Request, experiment_id: str) -> JSONResponse:
        """Per-status work-unit progress for one of my experiments."""
        return await _proxy(request, f"/api/v0/experiments/{experiment_id}/work-units")

    @router.get("/experiments/{experiment_id}/receipts")
    async def list_experiment_receipts(request: Request, experiment_id: str) -> JSONResponse:
        """Receipts issued for one of my experiments to the volunteers who ran it
        (R-D3, consumes coordinator R-D1b). Worker identity is stripped
        coordinator-side — the tenant sees that receipts exist, not who earned
        them (volunteer-anonymity rule)."""
        return await _proxy(request, f"/api/v0/experiments/{experiment_id}/receipts")

    @router.get("/experiments/{experiment_id}/activity")
    async def get_experiment_activity(request: Request, experiment_id: str) -> JSONResponse:
        """Anonymized liveness rollup for one of my experiments (R-D3):
        active-contributor count, work-unit status breakdown, last-activity
        timestamp, replication fill. Aggregates only — no worker identities."""
        return await _proxy(request, f"/api/v0/experiments/{experiment_id}/activity")

    # ── Results delivery (R-D5, consumes coordinator M-Results) ───────────────

    @router.get("/experiments/{experiment_id}/results")
    async def list_experiment_results(request: Request, experiment_id: str) -> JSONResponse:
        """The researcher's actual computed outputs (R-D5). Default = the T-C
        consensus payload per unit; `?include=raw` adds replicas; paginated via
        `?cursor=`. Worker identity is stripped coordinator-side (ACCOUNT_SCOPED);
        the science (payload + semantic_hash) is tenant-scoped. The query string
        is forwarded by `_proxy`."""
        return await _proxy(request, f"/api/v0/experiments/{experiment_id}/results")

    @router.get("/experiments/{experiment_id}/results/export")
    async def export_experiment_results(
        request: Request, experiment_id: str, label: str | None = None
    ) -> JSONResponse:
        """Collect the evidence bundle (EB-1: consensus payloads + work-unit
        inputs + worker signatures + receipts + manifest + the result-set
        attestation with its Rekor anchor + a signed custody record), THEN verify
        it locally — the SDK's `verify_bundle` runs on THIS machine — so the click
        runs the whole attestation chain (signatures, attestation, root unify,
        completeness, worker sigs), not just the download. Returns
        {bundle, verification, saved_path}; the verified bundle is also written to
        the shared `runs/<label>/bundle.json` layout (the same place the CLI's
        `experiment export` writes — `saved_path` is where it landed), so a click
        and the CLI organize downloads identically. The saved bundle is the
        coordinator's verbatim, so `auspexai-tenant bundle verify` reproduces this
        independently. Collecting stamps `results_collected_at` and transfers data
        custody. A 409 (`conflict`) is the verify-on-export tamper alarm
        (coordinator refused to re-sign custody over a changed set).

        `label` (the tenant_experiment_label, supplied by the SPA) keys the local
        folder so it reads like the CLI's; absent, the experiment id is used.
        """
        try:
            bundle = await _client(request).get_json(
                f"/api/v0/experiments/{experiment_id}/results/export"
            )
        except CoordinatorError as e:
            return _envelope(e)
        try:
            v = await run_in_threadpool(verify_bundle, bundle)
            verification = _shape_verification(v, bundle)
        except Exception as e:  # a malformed/newer bundle is itself a failed verify
            verification = {
                "ok": False,
                "error": str(e),
                "checks": [],
                "rekor": _rekor_status(bundle),
            }
        saved_path = _save_bundle(request.app.state.config, label or experiment_id, bundle)
        return JSONResponse(
            content={"bundle": bundle, "verification": verification, "saved_path": saved_path}
        )

    async def _compute_benchmark(
        request: Request,
        experiment_id: str,
        reference: str,
        label: str | None,
        reference_label: str | None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Collect + verify both bundles, score, persist beside the run.
        Returns (record, None) or (None, why-it-could-not-score)."""
        from datetime import UTC, datetime

        from auspexai_tenant.benchmark import drift_benchmark_bundles

        client = _client(request)
        try:
            bundle = await client.get_json(f"/api/v0/experiments/{experiment_id}/results/export")
            ref_bundle = await client.get_json(f"/api/v0/experiments/{reference}/results/export")
        except CoordinatorError as e:
            return None, f"could not collect the evidence bundles: {e}"
        for side, blob in (("observation", bundle), ("reference", ref_bundle)):
            try:
                v = await run_in_threadpool(verify_bundle, blob)
                ok = bool(v.ok)
            except Exception:
                ok = False
            if not ok:
                return None, (
                    f"the {side} bundle failed verification — the benchmark scores "
                    "only custody-verified evidence"
                )
        report = await run_in_threadpool(drift_benchmark_bundles, bundle, ref_bundle)
        record: dict[str, Any] = {
            "schema": "auspexai-drift-benchmark-report/v0",
            "computed_at": datetime.now(UTC).isoformat(),
            "observation": {
                "experiment_id": experiment_id,
                "label": label or (bundle.get("manifest") or {}).get("experiment_id"),
            },
            "reference": {
                "experiment_id": reference,
                "label": reference_label or (ref_bundle.get("manifest") or {}).get("experiment_id"),
            },
            "report": report.to_dict(),
        }
        try:
            layout = RunLayout(label or experiment_id, base=_runs_base(request.app.state.config))
            layout.ensure()
            path = layout.bundle_path().parent / f"benchmark_vs_{reference}.json"
            path.write_text(json.dumps(record, indent=2))
            record["path"] = str(path)
        except (OSError, ValueError):
            pass
        return record, None

    @router.get("/experiments/{experiment_id}/benchmarks")
    async def experiment_benchmarks(
        request: Request, experiment_id: str, label: str | None = None
    ) -> JSONResponse:
        """This run's Drift Benchmark, AUTO-MATERIALIZED (no choosing): the
        reference was declared at launch ([benchmark].reference, recorded beside
        the run — the pre-registration posture), so a completed run's score
        simply exists. Returns:
        - benchmarks: this run's saved reports (newest first) — computed here on
          first view when the declaration exists and no report does yet;
        - declaration: the run's declared reference, if any;
        - track: the flip side — runs scored AGAINST this run (this run as the
          baseline), the drift series the eventual public board publishes;
        - materialize_error: why the declared score could not be computed (kept
          out of `benchmarks` — never a fabricated score).
        Ad-hoc scoring against an arbitrary reference is a CLI capability
        (`auspexai-tenant benchmark drift`), deliberately not a dashboard one."""
        records = _scan_benchmark_records(_runs_bases(request.app.state.config))
        mine = [
            r for r in records if (r.get("observation") or {}).get("experiment_id") == experiment_id
        ]
        declaration = _find_benchmark_declaration(
            _runs_bases(request.app.state.config), experiment_id
        )
        materialize_error: str | None = None
        if declaration and not any(
            (r.get("reference") or {}).get("experiment_id")
            == declaration.get("reference_experiment_id")
            for r in mine
        ):
            record, materialize_error = await _compute_benchmark(
                request,
                experiment_id,
                str(declaration.get("reference_experiment_id")),
                label or declaration.get("label"),
                None,
            )
            if record is not None:
                mine = [record, *mine]
        track = [
            {
                "computed_at": r.get("computed_at"),
                "observation": r.get("observation"),
                "peak_eu": (r.get("report") or {}).get("peak_eu"),
                "breadth": (r.get("report") or {}).get("breadth"),
                "byte_divergence_rate": (r.get("report") or {}).get("byte_divergence_rate"),
                "diverged_units_total": (r.get("report") or {}).get("diverged_units_total"),
            }
            for r in records
            if (r.get("reference") or {}).get("experiment_id") == experiment_id
        ]
        return JSONResponse(
            content={
                "benchmarks": mine,
                "declaration": declaration,
                "track": track,
                "materialize_error": materialize_error,
            }
        )

    @router.get("/benchmarks")
    async def list_benchmarks(request: Request) -> JSONResponse:
        """Summary rows for every saved drift-benchmark report, newest first —
        the data source for the experiments list's benchmark column (and, later,
        the G5 publisher). Not a navigation surface of its own."""
        rows: list[dict[str, Any]] = []
        for rec in _scan_benchmark_records(_runs_bases(request.app.state.config)):
            rep = rec.get("report") or {}
            rows.append(
                {
                    "computed_at": rec.get("computed_at"),
                    "observation": rec.get("observation"),
                    "reference": rec.get("reference"),
                    "peak_eu": rep.get("peak_eu"),
                    "breadth": rep.get("breadth"),
                    "byte_divergence_rate": rep.get("byte_divergence_rate"),
                    "diverged_units_total": rep.get("diverged_units_total"),
                    "probes": len(rep.get("probes") or []),
                    "path": rec.get("path"),
                }
            )
        return JSONResponse(content={"benchmarks": rows})

    @router.get("/experiments/{experiment_id}/raw-content")
    async def raw_content(request: Request, experiment_id: str) -> JSONResponse:
        """D20: collect the run's buffered raw model outputs (R3-only, audited,
        live — the coordinator enforces the gate and never stores raw). The
        driver is the primary collector during a run; this exposes the same
        R3-gated pull to the dashboard."""
        return await _proxy(request, f"/api/v0/experiments/{experiment_id}/raw-content")

    @router.get("/experiments/{experiment_id}/publications")
    async def experiment_publications(request: Request, experiment_id: str) -> JSONResponse:
        """G6: the experiment's publication records (benchmark authorizations +
        DOI facts) — feeds the buttons' state + the published-facts display."""
        return await _proxy(request, f"/api/v0/experiments/{experiment_id}/publications")

    @router.post("/experiments/{experiment_id}/actions/mint-doi")
    async def mint_doi(request: Request, experiment_id: str) -> JSONResponse:
        """G6/F4: forwards the R3-gated mint to the coordinator (which enforces
        the full gate chain and types every refusal). The frontend button shows
        a confirm-before-send preview; this fires only on Confirm."""
        return await _proxy_post_body(
            request, f"/api/v0/experiments/{experiment_id}/actions/mint-doi", status_code=200
        )

    @router.post("/experiments/{experiment_id}/publish-benchmark")
    async def publish_benchmark(request: Request, experiment_id: str) -> JSONResponse:
        """G6: the one-command publish, server-side (this backend holds the
        tenant key) — authorization request (R1+ gate, audited) → signed entry
        → board submission. Composed from SDK library pieces; fires only after
        the frontend's confirm."""
        import os
        from datetime import UTC, datetime

        from auspexai_tenant.benchmark_entry import build_entry, verify_entry
        from auspexai_tenant.evidence import verify_bundle
        from auspexai_tenant.experiment import Experiment

        cfg = request.app.state.config
        client = _client(request)
        try:
            await client.get_json(f"/api/v0/experiments/{experiment_id}")
            # The saved report (the Benchmark tab's data) names the reference.
            records = [
                r
                for r in _scan_benchmark_records(_runs_bases(cfg))
                if (r.get("observation") or {}).get("experiment_id") == experiment_id
            ]
            if not records:
                return JSONResponse(
                    status_code=409,
                    content={
                        "error": {
                            "code": "no_saved_report",
                            "message": "score the run first (Benchmark tab)",
                        }
                    },
                )
            record = records[0]
            reference_id = record["reference"]["experiment_id"]
            obs_bundle = await client.get_json(
                f"/api/v0/experiments/{experiment_id}/results/export"
            )
            ref_bundle = await client.get_json(f"/api/v0/experiments/{reference_id}/results/export")
            for side, blob in (("observation", obs_bundle), ("reference", ref_bundle)):
                v = await run_in_threadpool(verify_bundle, blob)
                if not v.ok:
                    return JSONResponse(
                        status_code=409,
                        content={
                            "error": {
                                "code": "bundle_unverified",
                                "message": f"the {side} bundle failed verification",
                            }
                        },
                    )
            from auspexai_tenant.signing import TenantKey

            tkey = TenantKey.load(cfg.key_path)
            rep = record.get("report") or {}
            authorization = None
            resp = Experiment(cfg.coord_url, tkey, experiment_id)._post(
                f"/api/v0/experiments/{experiment_id}/actions/authorize-benchmark-publication",
                json={
                    "reference_experiment_id": reference_id,
                    "peak_eu": rep.get("peak_eu"),
                    "breadth": rep.get("breadth"),
                    "byte_divergence_rate": rep.get("byte_divergence_rate"),
                },
            )
            if resp.status_code == 200:
                authorization = resp.json()["authorization"]
            elif resp.status_code == 403:
                detail = resp.json().get("detail", {}).get("error", {})
                return JSONResponse(status_code=403, content={"error": detail})
            entry = build_entry(
                record=record,
                observation_bundle=obs_bundle,
                reference_bundle=ref_bundle,
                tenant_id=(obs_bundle.get("manifest") or {}).get("tenant_id"),
                key=tkey,
                authorization=authorization,
            )
            assert verify_entry(entry) is not None
            import httpx as _httpx

            submit_url = os.environ.get(
                "AUSPEXAI_BOARD_SUBMIT_URL", "https://board.auspexai.network/submit"
            )
            sresp = await run_in_threadpool(lambda: _httpx.post(submit_url, json=entry, timeout=30))
            body = (
                sresp.json()
                if sresp.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            return JSONResponse(
                content={
                    "status": body.get("status") or f"http-{sresp.status_code}",
                    "pr": body.get("pr"),
                    "authorized": authorization is not None,
                    "submitted_at": datetime.now(UTC).isoformat(),
                }
            )
        except CoordinatorError as e:
            return _envelope(e)

    @router.get("/experiments/{experiment_id}/events/recent")
    async def experiment_events_recent(request: Request, experiment_id: str) -> JSONResponse:
        """UI fix C: the coordinator's replay ring — the activity trace
        rehydrates on mount instead of losing history to navigation."""
        return await _proxy(request, f"/api/v0/experiments/{experiment_id}/events/recent")

    @router.get("/experiments/{experiment_id}/attestation")
    async def get_experiment_attestation(request: Request, experiment_id: str) -> JSONResponse:
        """The result-set attestation for one of my experiments (integrity
        panel, R-D inc-1): the COSE-signed in-toto statement over the merkle
        root of the consensus set, plus its Rekor anchor (log index / entry
        uuid / inclusion proof) once the hourly sweep has anchored it. The
        final attestation is persisted + canonical; `?checkpoint=true`
        (forwarded by `_proxy`) returns a partial consensus-so-far attestation
        for a not-yet-completed experiment. A 425 comes back as a `not_ready`
        envelope, not an error."""
        return await _proxy(request, f"/api/v0/experiments/{experiment_id}/attestation")

    @router.get("/experiments/{experiment_id}/citation")
    async def get_experiment_citation(request: Request, experiment_id: str) -> JSONResponse:
        """The citation / acknowledgment block for one of my completed experiments
        (System B, D): the producing tenant (PI) + the volunteers who opted into
        public attribution by name, everyone else aggregated anonymously, plus a
        ready-to-paste acknowledgment. The researcher uses it when ready to publish —
        separate from collection; a DOI anchors it later."""
        return await _proxy(request, f"/api/v0/experiments/{experiment_id}/citation")

    # ── Lifecycle actions (R-D4) ─────────────────────────────────────────────
    # The four researcher-actionable transitions. approve/archive stay
    # maintainer-only (operator console), so they are deliberately absent here.

    @router.post("/experiments/{experiment_id}/actions/pause")
    async def pause_experiment(request: Request, experiment_id: str) -> JSONResponse:
        """Soft-pause my experiment (approved → paused): stop new assignments,
        keep accepting in-flight results."""
        return await _proxy_post(request, f"/api/v0/experiments/{experiment_id}/actions/pause")

    @router.post("/experiments/{experiment_id}/actions/resume")
    async def resume_experiment(request: Request, experiment_id: str) -> JSONResponse:
        """Resume my paused experiment (paused → approved)."""
        return await _proxy_post(request, f"/api/v0/experiments/{experiment_id}/actions/resume")

    @router.post("/experiments/{experiment_id}/actions/finalize-submissions")
    async def finalize_submissions(request: Request, experiment_id: str) -> JSONResponse:
        """Finalize submissions: no more work units, and arm auto-complete once
        the outstanding units finish. One-way (no un-finalize) — the SPA
        confirm-gates it."""
        return await _proxy_post(
            request, f"/api/v0/experiments/{experiment_id}/actions/finalize-submissions"
        )

    @router.post("/experiments/{experiment_id}/actions/abort")
    async def abort_experiment(request: Request, experiment_id: str) -> JSONResponse:
        """Abort my experiment (→ aborted). Terminal — the SPA confirm-gates it."""
        return await _proxy_post(request, f"/api/v0/experiments/{experiment_id}/actions/abort")

    # ── Demand board: model + software requests (R-D6, §9 #46) ───────────────
    # The researcher's "push" surface: signal demand the network can't meet
    # (a model nobody serves; a worker-baseline capability that doesn't exist)
    # and track each request through assessment → resolution → release. The
    # coordinator tenant-scopes the GET lists to the signing credential.

    async def _proxy_post_body(
        request: Request, path: str, *, status_code: int = 200
    ) -> JSONResponse:
        # Bodied signed POST (demand-board submits, the ORCID apply, the Tier-1
        # connect/bind). Rfc9421Auth adds + covers Content-Digest; the body passes
        # through verbatim — the coordinator validates the shape (422) and owns
        # authorization. status_code lets a create return 201 / a bind return 200.
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "kind": "bad_request",
                        "message": "request body must be JSON",
                        "coordinator_status": None,
                    }
                },
            )
        try:
            data = await _client(request).post_json(path, body=body)
        except CoordinatorError as e:
            return _envelope(e)
        return JSONResponse(content=data, status_code=status_code)

    @router.get("/catalog")
    async def get_catalog(request: Request) -> JSONResponse:
        """The network's bottom-up model catalog (what active workers can run)."""
        return await _proxy(request, "/api/v0/models/catalog")

    @router.get("/model-requests")
    async def list_model_requests(request: Request) -> JSONResponse:
        """My model requests (tenant-scoped coordinator-side)."""
        return await _proxy(request, "/api/v0/model-requests")

    @router.post("/model-requests")
    async def create_model_request(request: Request) -> JSONResponse:
        """Signal demand for a model (BYOM): {model_id, reason, hf_repo?}."""
        return await _proxy_post_body(request, "/api/v0/model-requests")

    @router.get("/software-requests")
    async def list_software_requests(request: Request) -> JSONResponse:
        """My software requests, incl. assessment + resolution + the fulfilling
        release_version (tenant-scoped coordinator-side)."""
        return await _proxy(request, "/api/v0/software-requests")

    @router.post("/software-requests")
    async def create_software_request(request: Request) -> JSONResponse:
        """Signal demand for a worker-baseline capability (code plane):
        {title, description, reason}. Always enters the maintainer review queue."""
        return await _proxy_post_body(request, "/api/v0/software-requests")

    @router.get("/tenant-applications/mine")
    async def list_my_tenant_applications(request: Request) -> JSONResponse:
        """My tenant applications (the Overview's onboarding tracker). Unlike
        every other proxy route this works for an UNREGISTERED key: the
        coordinator verifies the RFC 9421 signature against the request's own
        keyid (self-keyid proof of possession — until approval binds it, the
        applying key IS the identity). So the dashboard can show
        pending/declined application status before whoami ever succeeds."""
        return await _proxy(request, "/api/v0/tenant-applications/mine")

    @router.get("/auth/whoami")
    async def whoami(request: Request) -> JSONResponse:
        """The *confirmed bound* identity: the coordinator resolves the signing
        key to `credential_class` + (for a researcher) their own `tenant_id` +
        `pubkey_hex`. An `unauthorized` error here means the key isn't bound /
        was rotated (R-D2.5; design §10-Q4)."""
        return await _proxy(request, "/api/v0/auth/whoami")

    @router.get("/accounts/me/workers")
    async def my_workers(request: Request) -> JSONResponse:
        """The caller's OWN-account workers + derived liveness, for the Overview
        "Your workers" panel. Account-scoped server-side: the coordinator resolves
        the signing key to its account and returns only that account's currently
        bound workers; a caller with no account gets an empty list."""
        return await _proxy(request, "/api/v0/accounts/me/workers")

    return router
