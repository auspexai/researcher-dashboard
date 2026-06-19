"""verify-on-collect: the export endpoint runs verify_bundle locally and shapes
the result for the UI. These cover the shaping helpers (the new logic); the
verification itself is the SDK's, tested there.
"""

from __future__ import annotations

from auspexai_tenant.evidence import BundleVerification, WorkerSignatureReport

from auspexai_researcher_dashboard.api import _rekor_status, _shape_verification


def _ws(verified: int = 3, failed: list[str] | None = None) -> WorkerSignatureReport:
    return WorkerSignatureReport(
        verified=verified,
        failed=failed or [],
        skipped_aged_off=0,
        skipped_missing_fields=0,
    )


def _bv(**over) -> BundleVerification:
    base = dict(
        transfer_signature_valid=True,
        transfer_signer_authorized=True,
        attestation=None,
        root_unified=True,
        completeness_ok=True,
        inputs_bound_ok=True,
        worker_signatures=_ws(),
        footprint_ok=True,
        signer_pin_mode="known",
    )
    base.update(over)
    return BundleVerification(**base)


def test_rekor_status_anchored_vs_pending() -> None:
    assert _rekor_status({"attestation": {"rekor_log_index": 12345}}) == {
        "state": "anchored",
        "log_index": 12345,
    }
    assert _rekor_status({"attestation": {"rekor_log_index": None}})["state"] == "pending"
    assert _rekor_status({})["state"] == "pending"  # no attestation block yet


def test_shape_verification_passing() -> None:
    out = _shape_verification(_bv(), {"attestation": {"rekor_log_index": 99}})
    assert out["ok"] is True
    states = {c["name"]: c["state"] for c in out["checks"]}
    assert states["Custody signature"] == "pass"
    assert states["Worker signatures"] == "pass"
    assert states["Attestation"] == "na"  # attestation=None → not applicable
    assert out["rekor"] == {"state": "anchored", "log_index": 99}


def test_shape_verification_surfaces_the_failing_check() -> None:
    out = _shape_verification(
        _bv(
            transfer_signature_valid=False,
            root_unified=None,
            worker_signatures=_ws(verified=0, failed=["res-bad"]),
        ),
        {},
    )
    assert out["ok"] is False
    states = {c["name"]: c["state"] for c in out["checks"]}
    assert states["Custody signature"] == "fail"
    assert states["Worker signatures"] == "fail"  # a non-empty failed list
    assert states["Root unification"] == "na"  # None → not applicable, never a fail
    assert out["rekor"]["state"] == "pending"
