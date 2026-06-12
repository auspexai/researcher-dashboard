"""R-D4 signed-proxy tests — lifecycle action POSTs.

Same offline harness as test_proxy_rd3.py: an httpx.MockTransport on
`app.state.coord_transport` stands in for the coordinator. We verify the four
action routes (pause/resume/finalize-submissions/abort) sign the request
(RFC 9421, tenant pubkey as keyid), POST to the right coordinator path, and
return the coordinator's JSON verbatim — plus that a coordinator 409 comes back
as a `conflict`-kind envelope carrying the coordinator's own reason.
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


def _assert_signed_post(req: httpx.Request, pubkey: str, coord_path: str) -> None:
    assert req.method == "POST"
    assert "Signature" in req.headers
    assert f'keyid="{pubkey}"' in req.headers["Signature-Input"]
    assert str(req.url) == f"{COORD}{coord_path}"


def test_pause_signed_and_proxied_verbatim(tmp_path: Path) -> None:
    updated = {"experiment_id": "exp-1", "status": "paused"}
    rec = _Recorder({"/api/v0/experiments/exp-1/actions/pause": (200, updated)})
    client, pubkey = _make_client(tmp_path, rec)

    response = client.post("/api/v0/experiments/exp-1/actions/pause")
    assert response.status_code == 200
    assert response.json() == updated
    _assert_signed_post(rec.requests[0], pubkey, "/api/v0/experiments/exp-1/actions/pause")


def test_resume_signed_and_proxied_verbatim(tmp_path: Path) -> None:
    updated = {"experiment_id": "exp-1", "status": "approved"}
    rec = _Recorder({"/api/v0/experiments/exp-1/actions/resume": (200, updated)})
    client, pubkey = _make_client(tmp_path, rec)

    response = client.post("/api/v0/experiments/exp-1/actions/resume")
    assert response.status_code == 200
    assert response.json() == updated
    _assert_signed_post(rec.requests[0], pubkey, "/api/v0/experiments/exp-1/actions/resume")


def test_finalize_signed_and_proxied_verbatim(tmp_path: Path) -> None:
    updated = {"experiment_id": "exp-1", "status": "approved", "submissions_finalized": True}
    rec = _Recorder({"/api/v0/experiments/exp-1/actions/finalize-submissions": (200, updated)})
    client, pubkey = _make_client(tmp_path, rec)

    response = client.post("/api/v0/experiments/exp-1/actions/finalize-submissions")
    assert response.status_code == 200
    assert response.json() == updated
    _assert_signed_post(
        rec.requests[0], pubkey, "/api/v0/experiments/exp-1/actions/finalize-submissions"
    )


def test_abort_signed_and_proxied_verbatim(tmp_path: Path) -> None:
    updated = {"experiment_id": "exp-1", "status": "aborted"}
    rec = _Recorder({"/api/v0/experiments/exp-1/actions/abort": (200, updated)})
    client, pubkey = _make_client(tmp_path, rec)

    response = client.post("/api/v0/experiments/exp-1/actions/abort")
    assert response.status_code == 200
    assert response.json() == updated
    _assert_signed_post(rec.requests[0], pubkey, "/api/v0/experiments/exp-1/actions/abort")


def test_conflict_surfaces_coordinator_reason(tmp_path: Path) -> None:
    """A coordinator 409 (e.g. aborting an already-completed experiment) comes
    back as a `conflict`-kind envelope carrying the coordinator's own message,
    not the generic coordinator_error line — this is the R-D4 decision to
    surface the real reason."""
    coord_body = {
        "detail": {
            "error": {
                "code": "invalid_status_transition",
                "message": "cannot transition from 'completed' to 'aborted'",
                "details": {"current_status": "completed", "requested_status": "aborted"},
            }
        }
    }
    rec = _Recorder({"/api/v0/experiments/exp-1/actions/abort": (409, coord_body)})
    client, _ = _make_client(tmp_path, rec)

    response = client.post("/api/v0/experiments/exp-1/actions/abort")
    assert response.status_code == 409
    err = response.json()["error"]
    assert err["kind"] == "conflict"
    assert err["message"] == "cannot transition from 'completed' to 'aborted'"
    assert err["coordinator_status"] == 409


def test_conflict_without_envelope_falls_back_to_generic(tmp_path: Path) -> None:
    """If a 409 body isn't the expected error envelope, the kind is still
    `conflict` but the message falls back to a generic line."""
    rec = _Recorder({"/api/v0/experiments/exp-1/actions/finalize-submissions": (409, {"oops": 1})})
    client, _ = _make_client(tmp_path, rec)

    response = client.post("/api/v0/experiments/exp-1/actions/finalize-submissions")
    assert response.status_code == 409
    err = response.json()["error"]
    assert err["kind"] == "conflict"
    assert "current state" in err["message"]
