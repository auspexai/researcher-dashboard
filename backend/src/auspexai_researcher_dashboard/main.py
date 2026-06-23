"""FastAPI app factory for the researcher dashboard.

Serves the SvelteKit-built static frontend + a small JSON API:
- `/api/v0/health` probes the coordinator AND reports whether the researcher's
  SDK key is present ("backend -> coord" connectivity + "is my identity set up?").
- the R-D2 tenant-scoped read proxy (`/api/v0/experiments[...]`, see api.py),
  which signs each coordinator request with the SDK's RFC 9421 signer.

The tenant-scoped receipt view lands in R-D3.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from auspexai_tenant.signing import TenantKey
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import build_api_router
from .config import ResearcherDashboardConfig
from .exec_ops import build_exec_router
from .local_ops import build_local_router


def _local_pubkey_hex(config: ResearcherDashboardConfig) -> str | None:
    """The PUBLIC key of the local tenant key, or None if absent/invalid.

    Safe to surface (it's public, and it's what a researcher submits during
    onboarding). Never exposes the private material beyond loading it to derive
    the pubkey. The confirmed *bound* identity comes from the coordinator's
    /auth/whoami; this is the "what key is on disk" half of the comparison.
    """
    try:
        return TenantKey.load(config.key_path).pubkey_hex
    except (FileNotFoundError, ValueError, OSError):
        return None


def create_app(config: ResearcherDashboardConfig | None = None) -> FastAPI:
    config = config or ResearcherDashboardConfig.from_env()
    app = FastAPI(
        title="AuspexAI Researcher Dashboard",
        version=__version__,
        description="Tenant-scoped, locally-run researcher view.",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.config = config

    # Tenant-scoped read proxy (R-D2). Registered before the SPA catch-all
    # below so /api/v0/* resolves here, not to the index.html fallback.
    app.include_router(build_api_router())
    # Local-operations (§8): config editor (Layer 2) + SDK exec (Layer 3). The
    # routers are always mounted; each route gates on config.workspace_dir /
    # local_exec_enabled and reports `unconfigured` / `exec_disabled` when off,
    # so the SPA renders the right state without a separate capability probe.
    app.include_router(build_local_router())
    app.include_router(build_exec_router())

    @app.get("/api/v0/health")
    async def health() -> JSONResponse:
        """Health + coord-connectivity + key-presence probe. Local; read-only."""
        now = datetime.now(UTC).isoformat()
        coord_ok: bool | None = None
        coord_detail: str | None = None
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{config.coord_url}/api/v0/health/public")
                coord_ok = r.status_code == 200
                coord_detail = r.json().get("status") if coord_ok else f"HTTP {r.status_code}"
        except httpx.HTTPError as e:
            coord_ok = False
            coord_detail = f"error: {e!s}"

        return JSONResponse(
            {
                "status": "ok",
                "version": __version__,
                "server_time": now,
                "phase": "R-D7 inc-1 (integrity panel + evidence bundle)",
                "coord": {
                    "url": config.coord_url,
                    "reachable": coord_ok,
                    "detail": coord_detail,
                },
                "identity": {
                    # Presence + the PUBLIC key only — never the private key
                    # material. The researcher's key IS their tenant identity
                    # (design note §3/§5). pubkey_hex is None if no/invalid key.
                    "key_path": str(config.key_path),
                    "key_present": config.key_path.is_file(),
                    "pubkey_hex": _local_pubkey_hex(config),
                },
            }
        )

    # Serve the SPA only when an actual built bundle is present. Gate on
    # index.html (the build's entrypoint), not merely the directory existing —
    # the scaffold ships a static/.gitkeep, so `static_dir.is_dir()` is true
    # even before any `vite build`, which would make the /_app mount raise at
    # startup. In source/dev the placeholder branch runs until the SPA is built.
    index_html = config.static_dir / "index.html"
    app_assets = config.static_dir / "_app"
    if index_html.is_file():
        if app_assets.is_dir():
            app.mount(
                "/_app",
                StaticFiles(directory=str(app_assets)),
                name="static-assets",
            )

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str) -> FileResponse:
            # Serve a real file if it exists (robots.txt, etc.), otherwise fall
            # back to index.html for SvelteKit client-side routing.
            candidate = config.static_dir / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index_html)
    else:

        @app.get("/")
        async def placeholder() -> JSONResponse:
            return JSONResponse(
                {
                    "status": "frontend bundle not present",
                    "expected_at": str(config.static_dir),
                    "hint": "Run pnpm install + pnpm build in the frontend/ dir and copy the built bundle.",
                }
            )

    return app
