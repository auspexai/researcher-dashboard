"""R-D3 signed-proxy tests — receipts list + activity rollup.

Same harness as test_proxy_rd2.py: an httpx.MockTransport on
`app.state.coord_transport` stands in for the coordinator, so we verify the two
new proxy routes sign the request (RFC 9421, tenant pubkey as keyid), forward to
the right coordinator path, and return the JSON verbatim (the dashboard does no
filtering — the coordinator scopes server-side).
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


def _make_client(tmp_path: Path, recorder: _Recorder) -> tuple[TestClient, str]:
    """Build a dashboard app whose coordinator transport is the recorder.
    Returns (client, pubkey_hex)."""
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


def test_receipts_signed_and_proxied_verbatim(tmp_path: Path) -> None:
    payload = {"receipts": [{"receipt_id": "rcpt-1", "experiment_id": "exp-1"}]}
    rec = _Recorder({"/api/v0/experiments/exp-1/receipts": (200, payload)})
    client, pubkey = _make_client(tmp_path, rec)

    response = client.get("/api/v0/experiments/exp-1/receipts")
    assert response.status_code == 200
    assert response.json() == payload

    assert len(rec.requests) == 1
    req = rec.requests[0]
    assert "Signature" in req.headers
    assert f'keyid="{pubkey}"' in req.headers["Signature-Input"]
    assert str(req.url) == f"{COORD}/api/v0/experiments/exp-1/receipts"


def test_activity_signed_and_proxied_verbatim(tmp_path: Path) -> None:
    payload = {
        "experiment_id": "exp-1",
        "active_contributor_count": 3,
        "total_work_units": 10,
        "work_unit_counts": {"completed": 7, "pending": 3},
        "completions_total": 21,
        "replication_target_total": 30,
    }
    rec = _Recorder({"/api/v0/experiments/exp-1/activity": (200, payload)})
    client, pubkey = _make_client(tmp_path, rec)

    response = client.get("/api/v0/experiments/exp-1/activity")
    assert response.status_code == 200
    assert response.json() == payload

    req = rec.requests[0]
    assert f'keyid="{pubkey}"' in req.headers["Signature-Input"]
    assert str(req.url) == f"{COORD}/api/v0/experiments/exp-1/activity"


def test_activity_own_workers_passed_through_verbatim(tmp_path: Path) -> None:
    """R-D3 own-worker enrichment: the coordinator may include `own_workers`
    (the tenant's own-account workers, non-anonymized). The proxy is dumb — it
    forwards the field verbatim; the coordinator already gated it ACCOUNT_SCOPED
    and stripped third-party identities server-side."""
    payload = {
        "experiment_id": "exp-1",
        "active_contributor_count": 4,
        "total_work_units": 3,
        "work_unit_counts": {"completed": 2, "pending": 1},
        "completions_total": 6,
        "replication_target_total": 9,
        "own_workers": [
            {
                "worker_id": "w-own-1",
                "worker_pubkey_hex": "aa" * 32,
                "result_count": 2,
                "trust_tier": 1,
                "last_activity_at": "2026-05-30T12:01:00Z",
            }
        ],
    }
    rec = _Recorder({"/api/v0/experiments/exp-1/activity": (200, payload)})
    client, _ = _make_client(tmp_path, rec)

    response = client.get("/api/v0/experiments/exp-1/activity")
    assert response.status_code == 200
    assert response.json() == payload


def test_receipts_not_found_is_enveloped(tmp_path: Path) -> None:
    rec = _Recorder({})  # coordinator 404s → tenant-private not_found envelope
    client, _ = _make_client(tmp_path, rec)
    response = client.get("/api/v0/experiments/nope/receipts")
    assert response.status_code == 404
    assert response.json()["error"]["kind"] == "not_found"


def test_activity_not_found_is_enveloped(tmp_path: Path) -> None:
    rec = _Recorder({})
    client, _ = _make_client(tmp_path, rec)
    response = client.get("/api/v0/experiments/nope/activity")
    assert response.status_code == 404
    assert response.json()["error"]["kind"] == "not_found"
