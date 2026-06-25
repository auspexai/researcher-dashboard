"""Signed-proxy test for the account-workers route (GET /accounts/me/workers).

Mirrors the test_proxy_rd3.py harness: an httpx.MockTransport stands in for the
coordinator, so we verify the route signs the request (RFC 9421, tenant pubkey as
keyid), forwards to the right coordinator path, and returns the JSON verbatim —
the dashboard does no filtering, the coordinator scopes it ACCOUNT_SCOPED
server-side.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from auspexai_tenant.signing import TenantKey
from fastapi.testclient import TestClient

from auspexai_researcher_dashboard.config import ResearcherDashboardConfig
from auspexai_researcher_dashboard.main import create_app

COORD = "https://coord.test"


class _Recorder:
    def __init__(self, routes: dict[str, tuple[int, object]]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status, body = self.routes.get(request.url.path, (404, {"error": {"code": "not_found"}}))
        return httpx.Response(status, json=body)


def _make_client(tmp_path: Path, recorder: _Recorder) -> tuple[TestClient, str]:
    key_path = tmp_path / "tenant_key"
    key = TenantKey.generate()
    key.save(key_path)
    config = ResearcherDashboardConfig(
        coord_url=COORD,
        bind_host="127.0.0.1",
        bind_port=4228,
        static_dir=tmp_path / "no-static",  # absent → no SPA catch-all
        key_path=key_path,
        open_browser=False,
    )
    app = create_app(config)
    app.state.coord_transport = httpx.MockTransport(recorder.handler)
    return TestClient(app), key.pubkey_hex


def test_my_workers_signed_and_proxied_verbatim(tmp_path: Path) -> None:
    payload = {
        "workers": [
            {
                "worker_id": "wkr-1",
                "pubkey_hex": "aa" * 32,
                "trust_tier": 1,
                "status": "active",
                "last_heartbeat_at": "2026-06-25T12:00:00Z",
                "result_count": 12,
            }
        ]
    }
    rec = _Recorder({"/api/v0/accounts/me/workers": (200, payload)})
    client, pubkey = _make_client(tmp_path, rec)

    response = client.get("/api/v0/accounts/me/workers")
    assert response.status_code == 200
    assert response.json() == payload

    assert len(rec.requests) == 1
    req = rec.requests[0]
    assert "Signature" in req.headers
    assert f'keyid="{pubkey}"' in req.headers["Signature-Input"]
    assert str(req.url) == f"{COORD}/api/v0/accounts/me/workers"
