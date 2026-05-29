"""R-D2 tests: the signed coordinator read proxy.

Verify the backend (1) signs every coordinator request with the SDK's RFC 9421
signer, (2) proxies list / detail / work-units responses verbatim, and (3) maps
coordinator failures to the classified error envelope the SPA branches on.

Offline: an httpx.MockTransport is injected on app.state.coord_transport, so no
live coordinator is needed. The mock also lets us inspect the outgoing request
to prove it was actually signed.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from auspexai_tenant.signing import MaintainerKey
from fastapi.testclient import TestClient

from auspexai_researcher_dashboard.config import ResearcherDashboardConfig
from auspexai_researcher_dashboard.main import create_app

COORD = "https://coord.test"


class _Recorder:
    """Records outgoing requests and serves canned responses by path."""

    def __init__(self, routes: dict[str, tuple[int, object]]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status, body = self.routes.get(
            request.url.path, (404, {"error": {"code": "experiment_not_found"}})
        )
        return httpx.Response(status, json=body)


def _make_client(
    tmp_path: Path, recorder: _Recorder, *, key: bool = True
) -> tuple[TestClient, str]:
    """Build a dashboard app whose coordinator transport is the recorder.
    Returns (client, pubkey_hex). pubkey_hex is '' when key=False."""
    key_path = tmp_path / "maintainer_key"
    pubkey_hex = ""
    if key:
        k = MaintainerKey.generate()
        k.save(key_path)
        pubkey_hex = k.pubkey_hex
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
    return TestClient(app), pubkey_hex


def test_list_is_signed_and_proxied_verbatim(tmp_path: Path) -> None:
    rec = _Recorder({"/api/v0/experiments": (200, {"experiments": [{"experiment_id": "exp-1"}]})})
    client, pubkey = _make_client(tmp_path, rec)

    response = client.get("/api/v0/experiments")
    assert response.status_code == 200
    # Returned verbatim — no filtering on the dashboard side.
    assert response.json() == {"experiments": [{"experiment_id": "exp-1"}]}

    assert len(rec.requests) == 1
    req = rec.requests[0]
    # Genuinely RFC 9421-signed, with this tenant's pubkey as keyid.
    assert "Signature" in req.headers
    assert "Signature-Input" in req.headers
    assert f'keyid="{pubkey}"' in req.headers["Signature-Input"]
    assert str(req.url) == f"{COORD}/api/v0/experiments"


def test_detail_proxied(tmp_path: Path) -> None:
    rec = _Recorder(
        {"/api/v0/experiments/exp-1": (200, {"experiment_id": "exp-1", "status": "approved"})}
    )
    client, _ = _make_client(tmp_path, rec)
    response = client.get("/api/v0/experiments/exp-1")
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert rec.requests[0].url.path == "/api/v0/experiments/exp-1"


def test_work_units_forwards_query(tmp_path: Path) -> None:
    rec = _Recorder(
        {"/api/v0/experiments/exp-1/work-units": (200, {"work_units": [], "counts_by_status": {}})}
    )
    client, _ = _make_client(tmp_path, rec)
    response = client.get("/api/v0/experiments/exp-1/work-units?status_filter=pending")
    assert response.status_code == 200
    # Query string forwarded to the coordinator.
    assert rec.requests[0].url.params.get("status_filter") == "pending"


def test_unauthorized_maps_to_key_not_recognized(tmp_path: Path) -> None:
    rec = _Recorder({"/api/v0/experiments": (403, {"detail": "bad sig"})})
    client, _ = _make_client(tmp_path, rec)
    response = client.get("/api/v0/experiments")
    assert response.status_code == 401
    err = response.json()["error"]
    assert err["kind"] == "unauthorized"
    assert err["coordinator_status"] == 403
    assert "rotated" in err["message"]


def test_not_found_maps(tmp_path: Path) -> None:
    rec = _Recorder({})  # unknown path → 404 from the recorder
    client, _ = _make_client(tmp_path, rec)
    response = client.get("/api/v0/experiments/nope")
    assert response.status_code == 404
    assert response.json()["error"]["kind"] == "not_found"


def test_no_key_maps_to_no_identity_without_calling_coord(tmp_path: Path) -> None:
    rec = _Recorder({"/api/v0/experiments": (200, {"experiments": []})})
    client, _ = _make_client(tmp_path, rec, key=False)
    response = client.get("/api/v0/experiments")
    assert response.status_code == 400
    assert response.json()["error"]["kind"] == "no_identity"
    # Failed before signing — no coordinator request was made.
    assert rec.requests == []


def test_unreachable_coordinator_maps(tmp_path: Path) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    key_path = tmp_path / "maintainer_key"
    MaintainerKey.generate().save(key_path)
    config = ResearcherDashboardConfig(
        coord_url=COORD,
        bind_host="127.0.0.1",
        bind_port=4228,
        static_dir=tmp_path / "no-static",
        key_path=key_path,
        open_browser=False,
    )
    app = create_app(config)
    app.state.coord_transport = httpx.MockTransport(boom)
    client = TestClient(app)

    response = client.get("/api/v0/experiments")
    assert response.status_code == 502
    assert response.json()["error"]["kind"] == "unreachable"


def test_whoami_signed_and_proxied(tmp_path: Path) -> None:
    rec = _Recorder(
        {
            "/api/v0/auth/whoami": (
                200,
                {"credential_class": "researcher", "tenant_id": "t1", "pubkey_hex": "ab" * 32},
            )
        }
    )
    client, pubkey = _make_client(tmp_path, rec)
    response = client.get("/api/v0/auth/whoami")
    assert response.status_code == 200
    assert response.json()["tenant_id"] == "t1"
    req = rec.requests[0]
    assert req.url.path == "/api/v0/auth/whoami"
    assert "Signature" in req.headers
    assert f'keyid="{pubkey}"' in req.headers["Signature-Input"]


def test_whoami_unauthorized_maps_to_key_not_recognized(tmp_path: Path) -> None:
    rec = _Recorder({"/api/v0/auth/whoami": (401, {"detail": "bad sig"})})
    client, _ = _make_client(tmp_path, rec)
    response = client.get("/api/v0/auth/whoami")
    assert response.status_code == 401
    assert response.json()["error"]["kind"] == "unauthorized"
