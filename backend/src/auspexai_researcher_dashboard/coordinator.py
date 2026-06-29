"""Signed coordinator client for the researcher dashboard (R-D2).

This is the only component that touches the researcher's private key. It loads
the tenant SDK `TenantKey` from disk and signs every coordinator request
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
from auspexai_tenant.signing import TenantKey

from .config import ResearcherDashboardConfig


class CoordinatorError(Exception):
    """A classified failure talking to the coordinator.

    `kind` is one of: ``no_identity`` (no/invalid tenant key on disk),
    ``unauthorized`` (coordinator rejected the signature — key unbound or
    rotated), ``not_found`` (404 — absent or, under tenant-private scoping, not
    this tenant's), ``conflict`` (409 — a lifecycle action is incompatible with
    the experiment's current state; carries the coordinator's own reason),
    ``not_ready`` (425 — the resource exists but isn't available yet, e.g. the
    final result-set attestation before completion; carries the coordinator's
    own reason), ``unreachable`` (transport error), ``coordinator_error`` (any
    other non-2xx).
    `http_status` is what the dashboard backend returns to the SPA;
    `coord_status` is the coordinator's status when there was one.
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


def _coord_error_message(response: httpx.Response) -> str | None:
    """Best-effort extraction of the coordinator's own error message from a
    failed response. The coordinator raises
    ``HTTPException(detail={"error": {"code", "message", "details"}})``, which
    FastAPI serializes under a top-level ``"detail"``. Returns None when the
    body isn't that shape (so the caller can fall back to a generic message)."""
    try:
        body = response.json()
    except Exception:
        return None
    detail = body.get("detail") if isinstance(body, dict) else None
    err = detail.get("error") if isinstance(detail, dict) else None
    if isinstance(err, dict) and isinstance(err.get("message"), str):
        return err["message"]
    return None


def _classify_response(
    status_code: int, conflict_message: str | None = None
) -> tuple[str, int, str]:
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
        # Prefer the coordinator's OWN message (a real experiment-not-found says
        # "no experiment with id …"); otherwise a GENERIC not-found. Do NOT
        # assume every 404 is an experiment — a non-experiment route (e.g. the
        # model catalog) 404ing was being mislabeled as a phantom missing
        # experiment.
        return (
            "not_found",
            404,
            conflict_message or "the coordinator returned 404 Not Found for this request",
        )
    if status_code == 409:
        # A lifecycle action collided with the experiment's current state
        # (invalid_status_transition / finalize_not_applicable). Surface the
        # coordinator's own reason so the UI can explain the refusal; fall back
        # to a generic line if the body wasn't the expected shape.
        return (
            "conflict",
            409,
            conflict_message or "this action conflicts with the experiment's current state",
        )
    if status_code == 425:
        # Not an error — a not-yet state (the final result-set attestation is
        # served only once the experiment is COMPLETED). The UI renders it as
        # informational, not as a failure.
        return (
            "not_ready",
            425,
            conflict_message or "not available until the experiment completes",
        )
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
            key = TenantKey.load(self._config.key_path)
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

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Raise a classified `CoordinatorError` for any non-2xx response. A 409
        or 425 carries the coordinator's own reason; a 404 prefers the
        coordinator's message (a real experiment-not-found) and otherwise falls
        back to a GENERIC not-found — see `_classify_response`."""
        if response.status_code < 400:
            return
        conflict_message = (
            _coord_error_message(response) if response.status_code in (404, 409, 425) else None
        )
        kind, http_status, message = _classify_response(response.status_code, conflict_message)
        raise CoordinatorError(
            kind, message, http_status=http_status, coord_status=response.status_code
        )

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
        self._raise_for_status(response)
        return response.json()

    async def post_json(self, path: str, body: dict | None = None) -> object:
        """Sign and POST `path` and return the parsed JSON body. Raises
        `CoordinatorError` on failure; a 409 surfaces the coordinator's own
        conflict reason. Bodyless (the lifecycle actions): the signature
        covers @method/@path/@authority. With `body` (the demand-board
        submits): `Rfc9421Auth` adds + covers Content-Digest automatically,
        matching the coordinator's RFC 9421 verification for a JSON body."""
        auth = self._auth()
        url = f"{self._config.coord_url.rstrip('/')}{path}"
        try:
            async with httpx.AsyncClient(
                auth=auth, transport=self._transport, timeout=10.0
            ) as client:
                if body is None:
                    response = await client.post(url)
                else:
                    response = await client.post(url, json=body)
        except httpx.HTTPError as e:
            raise CoordinatorError(
                "unreachable",
                f"could not reach the coordinator at {self._config.coord_url}: {e}",
                http_status=502,
            ) from e
        self._raise_for_status(response)
        return response.json()
