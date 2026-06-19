"""Tenant-scoped read proxy routes (R-D2).

Thin pass-through to the coordinator: sign the request → forward → return the
coordinator's JSON verbatim. No filtering happens here — the coordinator scopes
the response to the signing tenant and field-filters it server-side
(researcher_dashboard_design.md §5; the dashboard "is dumb on purpose").

A `CoordinatorError` is rendered as a stable error envelope the SPA branches on:
    {"error": {"kind": "...", "message": "...", "coordinator_status": 403 | null}}
"""

from __future__ import annotations

from typing import Any

from auspexai_tenant.evidence import BundleVerification, verify_bundle
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .coordinator import CoordinatorClient, CoordinatorError


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
    async def export_experiment_results(request: Request, experiment_id: str) -> JSONResponse:
        """Collect the evidence bundle (EB-1: consensus payloads + work-unit
        inputs + worker signatures + receipts + manifest + the result-set
        attestation with its Rekor anchor + a signed custody record), THEN verify
        it locally — the SDK's `verify_bundle` runs on THIS machine — so the click
        runs the whole attestation chain (signatures, attestation, root unify,
        completeness, worker sigs), not just the download. Returns
        {bundle, verification}; the saved bundle is the coordinator's verbatim, so
        `auspexai-tenant bundle verify` reproduces this independently. Collecting
        stamps `results_collected_at` and transfers data custody. A 409
        (`conflict`) is the verify-on-export tamper alarm (coordinator refused to
        re-sign custody over a changed set)."""
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
        return JSONResponse(content={"bundle": bundle, "verification": verification})

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

    async def _proxy_post_body(request: Request, path: str) -> JSONResponse:
        # Demand-board submits: signed POST WITH a JSON body (Rfc9421Auth adds
        # + covers Content-Digest). The body passes through verbatim — the
        # coordinator validates the shape (422) and owns authorization.
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
        return JSONResponse(content=data)

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

    return router
