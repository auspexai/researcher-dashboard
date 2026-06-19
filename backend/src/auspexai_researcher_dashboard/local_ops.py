"""Local-machine operations — the researcher dashboard's own trust boundary.

Everything in `api.py` PROXIES the coordinator (signed read/action; the
dashboard "is dumb on purpose"). The routes here are different in kind: they
touch the researcher's OWN machine. Two layers (§8 browser-driven stand-up,
ratified 2026-06-13), both OFF by default:

  - Layer 2 (config form): read/write the workspace `experiment.toml`. Gate:
    `config.workspace_dir` is set.
  - Layer 3 (build/submit/run): shell the tenant SDK. Gate: ALSO
    `config.local_exec_enabled` — the deliberate step up from monitor-only
    (editing config is lower-stakes than executing it).

No workspace ⇒ `/api/v0/local/*` reports `unconfigured`; the SPA shows the CLI
fallback instead of the form. Errors use the same envelope as the proxy routes:
`{"error": {"kind", "message", "coordinator_status": null}}`.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

# experiment.toml tables the config form manages, in canonical write order. Any
# OTHER table in an existing file (and any unmanaged key WITHIN these tables) is
# preserved by reading-then-merging before a write — the form never silently
# drops a tenant's bespoke knob.
_TABLE_ORDER = ("experiment", "executor", "reducer", "work_unit_source", "driver")

_HEADER = (
    "# experiment.toml — written by the AuspexAI researcher dashboard.\n"
    "# [experiment]/[executor]/[reducer]/[work_unit_source] + [driver] feed\n"
    "# `auspexai-tenant experiment launch --key <key>` (build + submit + drive).\n"
    "# Editing here regenerates the file (inline comments are not preserved)."
)


def _toml_scalar(v: Any) -> str:
    if isinstance(v, bool):  # before int — bool is an int subclass
        return "true" if v else "false"
    if isinstance(v, int | float):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)  # a valid TOML basic string
    raise ValueError(f"unsupported TOML scalar: {v!r}")


def _toml_value(v: Any) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(_toml_scalar(x) for x in v) + "]"
    return _toml_scalar(v)


def render_experiment_toml(data: dict[str, Any]) -> str:
    """Render a flat `{table: {key: scalar | list[scalar]}}` dict to TOML.

    The config-form contract is a clean round-trip: `tomllib.loads(render(d))`
    re-parses to `d`. Nested/array-of-tables values (e.g. approver_attestations)
    are outside this MVP and raise — the caller surfaces that as a 400 rather
    than writing a malformed file.
    """
    lines = [_HEADER]
    tables = [t for t in _TABLE_ORDER if t in data] + [t for t in data if t not in _TABLE_ORDER]
    for table in tables:
        body = data[table]
        if not isinstance(body, dict):
            raise ValueError(f"[{table}] must be a table, got {type(body).__name__}")
        lines.append("")
        lines.append(f"[{table}]")
        for key, value in body.items():
            if value is None:
                continue  # omit an unset key rather than writing a null
            lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


def _read_config(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _merge(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """One-level deep merge: replace the keys the form sent, keep every other
    table and every unmanaged key within a touched table."""
    merged = dict(existing)
    for table, body in incoming.items():
        if not isinstance(body, dict):
            continue
        base = dict(merged.get(table) or {})
        base.update(body)
        merged[table] = base
    return merged


def _error(kind: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"kind": kind, "message": message, "coordinator_status": None}},
    )


def build_local_router() -> APIRouter:
    router = APIRouter(prefix="/api/v0/local")

    def _cfg(request: Request):
        return request.app.state.config

    @router.get("/status")
    async def local_status(request: Request) -> JSONResponse:
        """What local capabilities are available + the workspace's current
        state. The SPA branches on this: no workspace ⇒ CLI fallback; workspace
        but no exec ⇒ config form only; exec ⇒ also the Build/Submit/Run
        buttons (Layer 3)."""
        cfg = _cfg(request)
        ws = cfg.workspace_dir
        toml_path = cfg.experiment_toml_path
        return JSONResponse(
            {
                "workspace_set": ws is not None,
                "workspace": str(ws) if ws else None,
                "workspace_exists": bool(ws and ws.is_dir()),
                "config_present": bool(toml_path and toml_path.exists()),
                "pkg_present": bool(cfg.pkg_dir and cfg.pkg_dir.is_dir()),
                "exec_enabled": cfg.local_exec_enabled,
            }
        )

    @router.get("/config")
    async def get_config(request: Request) -> JSONResponse:
        """The current experiment.toml, parsed (or `{}` when absent) — the form
        pre-fills from this."""
        cfg = _cfg(request)
        if cfg.workspace_dir is None:
            return _error("unconfigured", "no workspace configured (set WORKSPACE_DIR)", 409)
        toml_path = cfg.experiment_toml_path
        return JSONResponse(
            {"present": bool(toml_path and toml_path.exists()), "config": _read_config(toml_path)}
        )

    @router.post("/config")
    async def put_config(request: Request) -> JSONResponse:
        """Write the form's tables into experiment.toml, merged over any
        existing file so unmanaged tables/keys survive. A render failure (a
        value shape the MVP can't emit) returns 400 — the file is never left
        malformed."""
        cfg = _cfg(request)
        if cfg.workspace_dir is None:
            return _error("unconfigured", "no workspace configured (set WORKSPACE_DIR)", 409)
        try:
            body = await request.json()
        except Exception:
            return _error("bad_request", "request body must be JSON", 400)
        if not isinstance(body, dict):
            return _error("bad_request", "request body must be a JSON object of tables", 400)
        merged = _merge(_read_config(cfg.experiment_toml_path), body)
        try:
            rendered = render_experiment_toml(merged)
            tomllib.loads(rendered)  # self-check: we emitted parseable TOML
        except (ValueError, tomllib.TOMLDecodeError) as e:
            return _error("render_failed", f"could not render experiment.toml: {e}", 400)
        cfg.workspace_dir.mkdir(parents=True, exist_ok=True)
        cfg.experiment_toml_path.write_text(rendered, encoding="utf-8")
        return JSONResponse({"written": str(cfg.experiment_toml_path), "config": merged})

    return router
