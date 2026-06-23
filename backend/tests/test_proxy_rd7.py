"""R-D inc-1 signed-proxy tests — the result-set attestation (integrity panel).

Same offline harness as test_proxy_rd5.py: an httpx.MockTransport on
`app.state.coord_transport` stands in for the coordinator. Verifies the
attestation proxy route signs the request (RFC 9421), forwards to the right
coordinator path (incl. `?checkpoint=true`), returns the JSON verbatim, and
renders the coordinator's 425 as a `not_ready` envelope rather than an error.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from auspexai_tenant.signing import TenantKey
from fastapi.testclient import TestClient

from auspexai_researcher_dashboard.config import ResearcherDashboardConfig
from auspexai_researcher_dashboard.main import create_app

COORD = "https://coord.test"

ATTESTATION = {
    "attestation_id": "att-1",
    "experiment_id": "vigiles-d6-drift-r4",
    "tenant_id": "vigiles",
    "merkle_root": "ab" * 32,
    "algorithm": "result-set/v1",
    "unit_count": 6,
    "signing_key_pubkey_hex": "cd" * 32,
    "rekor_log_index": 1785484762,
    "rekor_entry_uuid": "ef" * 40,
    "rekor_inclusion_proof": {"logIndex": 1785484762, "hashes": ["00" * 32]},
    "partial": False,
}


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
    key_path = tmp_path / "tenant_key"
    key = TenantKey.generate()
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


def test_attestation_signed_and_proxied_verbatim(tmp_path: Path) -> None:
    rec = _Recorder({"/api/v0/experiments/exp-1/attestation": (200, ATTESTATION)})
    client, pubkey = _make_client(tmp_path, rec)

    response = client.get("/api/v0/experiments/exp-1/attestation")
    assert response.status_code == 200
    # Verbatim — the Rekor anchor fields the integrity panel renders ride
    # through untouched.
    assert response.json() == ATTESTATION
    req = rec.requests[0]
    assert "Signature" in req.headers
    assert f'keyid="{pubkey}"' in req.headers["Signature-Input"]
    assert str(req.url) == f"{COORD}/api/v0/experiments/exp-1/attestation"


def test_attestation_forwards_checkpoint_query(tmp_path: Path) -> None:
    partial = dict(ATTESTATION, partial=True, rekor_log_index=None)
    rec = _Recorder({"/api/v0/experiments/exp-1/attestation": (200, partial)})
    client, _ = _make_client(tmp_path, rec)

    response = client.get("/api/v0/experiments/exp-1/attestation?checkpoint=true")
    assert response.status_code == 200
    assert response.json()["partial"] is True
    # The query rides through unsigned to the coordinator.
    assert rec.requests[0].url.params.get("checkpoint") == "true"


def test_attestation_425_is_not_ready_envelope(tmp_path: Path) -> None:
    coord_body = {
        "detail": {
            "error": {
                "code": "experiment_not_completed",
                "message": (
                    "result-set attestation is available only once the experiment "
                    "is COMPLETED (the set is final); pass ?checkpoint=true for a "
                    "partial consensus-so-far attestation"
                ),
            }
        }
    }
    rec = _Recorder({"/api/v0/experiments/exp-1/attestation": (425, coord_body)})
    client, _ = _make_client(tmp_path, rec)

    response = client.get("/api/v0/experiments/exp-1/attestation")
    assert response.status_code == 425
    err = response.json()["error"]
    assert err["kind"] == "not_ready"
    assert err["coordinator_status"] == 425
    # The coordinator's own reason rides through (it names the checkpoint
    # alternative), same surfacing rule as 409 conflicts.
    assert "checkpoint" in err["message"]


def test_attestation_not_found_is_enveloped(tmp_path: Path) -> None:
    rec = _Recorder({})  # coordinator 404s → tenant-private not_found envelope
    client, _ = _make_client(tmp_path, rec)
    response = client.get("/api/v0/experiments/nope/attestation")
    assert response.status_code == 404
    assert response.json()["error"]["kind"] == "not_found"
