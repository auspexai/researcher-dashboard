"""Tier-1 connect: POST /accounts/bind is signed + forwarded verbatim."""

from __future__ import annotations

from pathlib import Path

import httpx
from auspexai_tenant.signing import TenantKey
from fastapi.testclient import TestClient

from auspexai_researcher_dashboard.config import ResearcherDashboardConfig
from auspexai_researcher_dashboard.main import create_app

COORD = "https://coord.test"


class _Recorder:
    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def handler(self, request):
        self.requests.append(request)
        status, body = self.routes.get(request.url.path, (404, {"error": {"code": "x"}}))
        return httpx.Response(status, json=body)


def _make_client(tmp_path, recorder):
    key_path = tmp_path / "tenant_key"
    TenantKey.generate().save(key_path)
    config = ResearcherDashboardConfig(
        coord_url=COORD,
        bind_host="127.0.0.1",
        bind_port=4228,
        static_dir=tmp_path / "no-static",
        key_path=key_path,
        open_browser=False,
    )
    app = create_app(config)
    app.state.coord_transport = httpx.MockTransport(recorder.handler)
    return TestClient(app)


def test_account_bind_signed_and_forwarded(tmp_path: Path) -> None:
    rec = _Recorder(
        {"/api/v0/accounts/bind": (200, {"account_id": "acct-x", "is_new_account": True})}
    )
    client = _make_client(tmp_path, rec)
    r = client.post("/api/v0/accounts/bind", json={"idp": "orcid", "access_token": "tok"})
    assert r.status_code == 200, r.text
    assert r.json()["account_id"] == "acct-x"
    req = rec.requests[0]
    assert "Signature" in req.headers
    assert str(req.url) == f"{COORD}/api/v0/accounts/bind"
