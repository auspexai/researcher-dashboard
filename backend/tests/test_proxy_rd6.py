"""R-D6 signed-proxy tests — the demand-board push surface (§9 #46).

Same offline harness as test_proxy_rd4.py. Verifies the catalog/model-request/
software-request routes sign the request, the POSTs carry the JSON body WITH a
covered Content-Digest (the body-bearing signature shape the coordinator
verifies), and coordinator errors map to the stable envelope.
"""

from __future__ import annotations

import json
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


def test_software_requests_list_signed_and_verbatim(tmp_path: Path) -> None:
    canned = {"requests": [{"request_id": "swr-1", "status": "assessed", "title": "x"}]}
    rec = _Recorder({"/api/v0/software-requests": (200, canned)})
    client, pubkey = _make_client(tmp_path, rec)

    r = client.get("/api/v0/software-requests")
    assert r.status_code == 200
    assert r.json() == canned
    sent = rec.requests[0]
    assert "Signature" in sent.headers
    assert f'keyid="{pubkey}"' in sent.headers["Signature-Input"]


def test_create_software_request_posts_body_with_content_digest(tmp_path: Path) -> None:
    rec = _Recorder(
        {"/api/v0/software-requests": (201, {"request_id": "swr-9", "status": "pending"})}
    )
    client, _ = _make_client(tmp_path, rec)

    body = {"title": "Ollama inference serving", "description": "d", "reason": "r"}
    r = client.post("/api/v0/software-requests", json=body)
    assert r.status_code == 200  # proxy normalizes to the JSON envelope
    assert r.json()["request_id"] == "swr-9"
    sent = rec.requests[0]
    assert sent.method == "POST"
    assert json.loads(sent.content) == body
    # Body-bearing signature shape: Content-Digest present AND covered.
    assert "Content-Digest" in sent.headers
    assert "content-digest" in sent.headers["Signature-Input"].lower()


def test_create_model_request_posts_body(tmp_path: Path) -> None:
    rec = _Recorder({"/api/v0/model-requests": (201, {"request_id": "mrq-3", "status": "pending"})})
    client, _ = _make_client(tmp_path, rec)

    r = client.post(
        "/api/v0/model-requests", json={"model_id": "gemma-3-1b-it-q4", "reason": "drift"}
    )
    assert r.status_code == 200
    assert r.json()["request_id"] == "mrq-3"
    assert json.loads(rec.requests[0].content)["model_id"] == "gemma-3-1b-it-q4"


def test_catalog_proxies(tmp_path: Path) -> None:
    canned = {"models": [{"model_id": "m", "worker_count": 2}], "total_active_workers": 2}
    rec = _Recorder({"/api/v0/models/catalog": (200, canned)})
    client, _ = _make_client(tmp_path, rec)
    r = client.get("/api/v0/catalog")
    assert r.status_code == 200
    assert r.json() == canned


def test_coordinator_403_maps_to_error_envelope(tmp_path: Path) -> None:
    rec = _Recorder({"/api/v0/software-requests": (403, {"detail": "researcher required"})})
    client, _ = _make_client(tmp_path, rec)
    r = client.post(
        "/api/v0/software-requests", json={"title": "t", "description": "d", "reason": "r"}
    )
    assert r.status_code in (401, 403)
    assert r.json()["error"]["kind"]


def test_non_json_body_is_rejected_locally(tmp_path: Path) -> None:
    rec = _Recorder({})
    client, _ = _make_client(tmp_path, rec)
    r = client.post(
        "/api/v0/software-requests",
        content=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400
    assert rec.requests == []  # never reached the coordinator
