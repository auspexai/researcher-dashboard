"""Onboarding-tracker signed-proxy tests — GET /api/v0/tenant-applications/mine.

Same offline harness as test_proxy_rd7.py: an httpx.MockTransport on
`app.state.coord_transport` stands in for the coordinator. Verifies the
applications proxy route signs the request (RFC 9421) with the LOCAL key's own
keyid — the self-keyid proof of possession the coordinator accepts for
UNREGISTERED keys, which is the whole point of this route: an applicant has no
bound credential yet — forwards to the right coordinator path, and returns the
JSON verbatim (application_id / status / resolution_reason / created_tenant_id
all ride through untouched for the Overview to branch on).
"""

from __future__ import annotations

from pathlib import Path

import httpx
from auspexai_tenant.signing import MaintainerKey
from fastapi.testclient import TestClient

from auspexai_researcher_dashboard.config import ResearcherDashboardConfig
from auspexai_researcher_dashboard.main import create_app

COORD = "https://coord.test"

# Newest first — the coordinator orders /mine by created_at DESC.
APPLICATIONS = {
    "applications": [
        {
            "application_id": "app-2",
            "status": "pending",
            "resolution_reason": None,
            "created_tenant_id": None,
        },
        {
            "application_id": "app-1",
            "status": "declined",
            "resolution_reason": "affiliation could not be verified",
            "created_tenant_id": None,
        },
    ]
}


class _Recorder:
    def __init__(self, routes: dict[str, tuple[int, object]]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status, body = self.routes.get(request.url.path, (404, {"error": {"code": "not_found"}}))
        return httpx.Response(status, json=body)


def _make_client(tmp_path: Path, recorder: _Recorder) -> tuple[TestClient, str]:
    key_path = tmp_path / "maintainer_key"
    key = MaintainerKey.generate()
    key.save(key_path)
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
    return TestClient(app), key.pubkey_hex


def test_applications_signed_with_self_keyid_and_proxied_verbatim(tmp_path: Path) -> None:
    rec = _Recorder({"/api/v0/tenant-applications/mine": (200, APPLICATIONS)})
    client, pubkey = _make_client(tmp_path, rec)

    response = client.get("/api/v0/tenant-applications/mine")
    assert response.status_code == 200
    # Verbatim — the status / resolution_reason / created_tenant_id fields the
    # onboarding tracker branches on ride through untouched.
    assert response.json() == APPLICATIONS
    req = rec.requests[0]
    assert "Signature" in req.headers
    # Self-keyid proof of possession: the signature's keyid IS the local key's
    # pubkey — the coordinator resolves an applicant by it, no binding needed.
    assert f'keyid="{pubkey}"' in req.headers["Signature-Input"]
    assert str(req.url) == f"{COORD}/api/v0/tenant-applications/mine"


def test_applications_empty_list_rides_through(tmp_path: Path) -> None:
    # A key with no application yet: the coordinator returns an empty list (200,
    # not an error) — the Overview renders its "no application found" prompt.
    rec = _Recorder({"/api/v0/tenant-applications/mine": (200, {"applications": []})})
    client, _ = _make_client(tmp_path, rec)

    response = client.get("/api/v0/tenant-applications/mine")
    assert response.status_code == 200
    assert response.json() == {"applications": []}
