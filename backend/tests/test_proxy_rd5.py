"""R-D5 signed-proxy tests — results delivery + offload bundle.

Same offline harness as test_proxy_rd4.py: an httpx.MockTransport on
`app.state.coord_transport` stands in for the coordinator. Verifies the two new
GET proxy routes sign the request (RFC 9421), forward to the right coordinator
path (incl. the `?include`/`?cursor` query), and return the JSON verbatim.
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


def test_results_signed_and_proxied_verbatim(tmp_path: Path) -> None:
    payload = {"results": [{"result_id": "res-1", "payload": {"answer": 42}}], "next_cursor": None}
    rec = _Recorder({"/api/v0/experiments/exp-1/results": (200, payload)})
    client, pubkey = _make_client(tmp_path, rec)

    response = client.get("/api/v0/experiments/exp-1/results")
    assert response.status_code == 200
    assert response.json() == payload
    req = rec.requests[0]
    assert "Signature" in req.headers
    assert f'keyid="{pubkey}"' in req.headers["Signature-Input"]
    assert str(req.url) == f"{COORD}/api/v0/experiments/exp-1/results"


def test_results_forwards_include_and_cursor_query(tmp_path: Path) -> None:
    rec = _Recorder({"/api/v0/experiments/exp-1/results": (200, {"results": []})})
    client, _ = _make_client(tmp_path, rec)

    response = client.get("/api/v0/experiments/exp-1/results?include=raw&cursor=c1")
    assert response.status_code == 200
    # The query rides through unsigned to the coordinator.
    req = rec.requests[0]
    assert req.url.params.get("include") == "raw"
    assert req.url.params.get("cursor") == "c1"


def test_export_signed_and_proxied_verbatim(tmp_path: Path) -> None:
    bundle = {
        "experiment_id": "exp-1",
        "consensus_results": [{"result_id": "res-1"}],
        "receipts": [{"receipt_id": "rcpt-1", "cose_b64": "AA=="}],
        "transfer": {
            "transfer_id": "xfer-1",
            "coordinator_signature": "ab",
            "result_set_root": "r",
        },
    }
    rec = _Recorder({"/api/v0/experiments/exp-1/results/export": (200, bundle)})
    client, pubkey = _make_client(tmp_path, rec)

    response = client.get("/api/v0/experiments/exp-1/results/export")
    assert response.status_code == 200
    assert response.json() == bundle
    assert f'keyid="{pubkey}"' in rec.requests[0].headers["Signature-Input"]
    assert str(rec.requests[0].url) == f"{COORD}/api/v0/experiments/exp-1/results/export"


def test_results_not_found_is_enveloped(tmp_path: Path) -> None:
    rec = _Recorder({})  # coordinator 404s → tenant-private not_found envelope
    client, _ = _make_client(tmp_path, rec)
    response = client.get("/api/v0/experiments/nope/results")
    assert response.status_code == 404
    assert response.json()["error"]["kind"] == "not_found"
