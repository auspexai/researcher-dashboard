"""Signed coordinator client for the researcher dashboard (R-D2).

This is the only component that touches the researcher's private key. It loads
the tenant SDK `MaintainerKey` from disk and signs every coordinator request
via RFC 9421 (`auspexai_tenant.http_signing.Rfc9421Auth`), then returns the
coordinator's JSON to the caller verbatim. It applies NO filtering of its own —
the coordinator scopes and field-filters the response server-side
(researcher_dashboard_design.md §5). Stateless: a fresh httpx client per call.

Failures are classified into a small set of `kind`s so the SPA can render the
right state (§10 Q4) rather than a generic error — in particular the
"key not recognized" (unbound / rotated) case.
"""

from __future__ import annotations

import httpx
from auspexai_tenant.http_signing import Rfc9421Auth
from auspexai_tenant.signing import MaintainerKey

from .config import ResearcherDashboardConfig


class CoordinatorError(Exception):
    """A classified failure talking to the coordinator.

    `kind` is one of: ``no_identity`` (no/invalid tenant key on disk),
    ``unauthorized`` (coordinator rejected the signature — key unbound or
    rotated), ``not_found`` (404 — absent or, under tenant-private scoping, not
    this tenant's), ``unreachable`` (transport error), ``coordinator_error``
    (any other non-2xx). `http_status` is what the dashboard backend returns to
    the SPA; `coord_status` is the coordinator's status when there was one.
    """

    def __init__(
        self,
        kind: str,
        message: str,
        *,
        http_status: int,
        coord_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.http_status = http_status
        self.coord_status = coord_status


def _classify_response(status_code: int) -> tuple[str, int, str]:
    """Map a coordinator HTTP status to (kind, dashboard_http_status, message)."""
    if status_code in (401, 403):
        return (
            "unauthorized",
            401,
            "the coordinator did not recognize this tenant key — it may not be "
            "bound yet, or may have been rotated. Rebind it via the operator "
            "console, then retry.",
        )
    if status_code == 404:
        return ("not_found", 404, "no such experiment for this tenant")
    return ("coordinator_error", 502, f"the coordinator returned HTTP {status_code}")


class CoordinatorClient:
    """Signs and forwards GETs to the coordinator. Inject `transport` in tests
    (e.g. `httpx.MockTransport`) to exercise without a live coordinator."""

    def __init__(
        self,
        config: ResearcherDashboardConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport

    def _auth(self) -> Rfc9421Auth:
        try:
            key = MaintainerKey.load(self._config.key_path)
        except FileNotFoundError as e:
            raise CoordinatorError(
                "no_identity",
                f"no tenant key found at {self._config.key_path}. Generate one with "
                "`auspexai-tenant key generate` once your tenant is approved; the "
                "dashboard reads it to sign coordinator requests.",
                http_status=400,
            ) from e
        except ValueError as e:
            raise CoordinatorError(
                "no_identity",
                f"the tenant key at {self._config.key_path} is not a valid Ed25519 private key.",
                http_status=400,
            ) from e
        return Rfc9421Auth(key)

    async def get_json(self, path: str) -> object:
        """Sign and GET `path` (a coordinator path, optionally with a query
        string) and return parsed JSON. Raises `CoordinatorError` on failure."""
        auth = self._auth()
        url = f"{self._config.coord_url.rstrip('/')}{path}"
        try:
            async with httpx.AsyncClient(
                auth=auth, transport=self._transport, timeout=10.0
            ) as client:
                response = await client.get(url)
        except httpx.HTTPError as e:
            raise CoordinatorError(
                "unreachable",
                f"could not reach the coordinator at {self._config.coord_url}: {e}",
                http_status=502,
            ) from e
        if response.status_code >= 400:
            kind, http_status, message = _classify_response(response.status_code)
            raise CoordinatorError(
                kind, message, http_status=http_status, coord_status=response.status_code
            )
        return response.json()
