"""FastAPI app factory for the researcher dashboard.

R-D0: serves the SvelteKit-built static frontend + a small JSON health API.
The health endpoint probes the coordinator AND reports whether the
researcher's SDK key is present, so the placeholder page can show both
"backend -> coord" connectivity and "is my identity set up?" status.

No authenticated coordinator calls yet. Tenant-scoped reads (signed via the
SDK's RFC 9421 signer) land in R-D2; the tenant-scoped receipt view in R-D3.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import ResearcherDashboardConfig


def create_app(config: ResearcherDashboardConfig | None = None) -> FastAPI:
    config = config or ResearcherDashboardConfig.from_env()
    app = FastAPI(
        title="AuspexAI Researcher Dashboard",
        version=__version__,
        description="Tenant-scoped, locally-run researcher view. R-D0 placeholder.",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.config = config

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
                "phase": "R-D0 (scaffold)",
                "coord": {
                    "url": config.coord_url,
                    "reachable": coord_ok,
                    "detail": coord_detail,
                },
                "identity": {
                    # Presence only — never the key material. The researcher's
                    # key IS their tenant identity (design note §3/§5).
                    "key_path": str(config.key_path),
                    "key_present": config.key_path.is_file(),
                },
            }
        )

    if config.static_dir.is_dir():
        index_html = config.static_dir / "index.html"
        app.mount(
            "/_app",
            StaticFiles(directory=str(config.static_dir / "_app")),
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
