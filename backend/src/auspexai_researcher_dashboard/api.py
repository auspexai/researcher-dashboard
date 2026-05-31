"""Tenant-scoped read proxy routes (R-D2).

Thin pass-through to the coordinator: sign the request → forward → return the
coordinator's JSON verbatim. No filtering happens here — the coordinator scopes
the response to the signing tenant and field-filters it server-side
(researcher_dashboard_design.md §5; the dashboard "is dumb on purpose").

A `CoordinatorError` is rendered as a stable error envelope the SPA branches on:
    {"error": {"kind": "...", "message": "...", "coordinator_status": 403 | null}}
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .coordinator import CoordinatorClient, CoordinatorError


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

    @router.get("/auth/whoami")
    async def whoami(request: Request) -> JSONResponse:
        """The *confirmed bound* identity: the coordinator resolves the signing
        key to `credential_class` + (for a researcher) their own `tenant_id` +
        `pubkey_hex`. An `unauthorized` error here means the key isn't bound /
        was rotated (R-D2.5; design §10-Q4)."""
        return await _proxy(request, "/api/v0/auth/whoami")

    return router
