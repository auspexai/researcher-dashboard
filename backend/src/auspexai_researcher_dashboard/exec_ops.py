"""Local SDK execution — §8 Layer 3 (the deliberate altitude step).

Where `local_ops.py` writes a config file, this SHELLS the tenant SDK on the
researcher's own machine: `build` (assemble the manifest, fast), `submit`
(sign + upload + create, seconds), and `run` (the hours-long driver loop, a
managed background process). Off unless BOTH gates are set: a workspace
(`WORKSPACE_DIR`) AND `local_exec_enabled` (`LOCAL_EXEC`) — editing config is
lower-stakes than executing it.

Two safety properties hold by construction:
  - No command injection. Every argv is FIXED; the workspace, package dir, and
    key path come from `config`, never the request body. `shell=False` always.
  - Key handling is exactly the CLI's. We pass `--key <config.key_path>`; the
    SDK loads + signs with it. The dashboard never reads private key material.

The single active run lives on `app.state.local_run` (a single-tenant dashboard
runs one experiment at a time). Its stdout+stderr stream to
`<workspace>/.auspexai/run.log`; the heart monitor polls `GET /run` for state.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

# Short shells (build/submit) are bounded; a hung network call shouldn't wedge
# the dashboard. `run` is unbounded by design (it's the long driver) and is
# managed as a background process instead.
_BUILD_TIMEOUT_S = 120
_SUBMIT_TIMEOUT_S = 300
_LOG_TAIL_BYTES = 16_384  # status returns the log's tail, not the whole file


@dataclass
class LocalRun:
    """A spawned `experiment run` and the handle needed to watch/stop it."""

    popen: subprocess.Popen
    log_path: Path
    cmd: list[str]
    cwd: str
    started_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sdk_bin() -> str | None:
    return shutil.which("auspexai-tenant")


def _error(kind: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"kind": kind, "message": message, "coordinator_status": None}},
    )


def _run_sync(cmd: list[str], cwd: Path, timeout: int) -> JSONResponse:
    """Run a short SDK command to completion; return its captured output. A
    non-zero exit is a 200 with ok=false (an expected outcome the SPA renders),
    not an HTTP error — only the harness failing to launch is a 5xx."""
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return _error("exec_timeout", f"`{' '.join(cmd[1:3])}` timed out after {timeout}s", 504)
    except OSError as e:
        return _error("exec_failed", f"could not launch the SDK: {e}", 500)
    return JSONResponse(
        {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "cmd": cmd,
        }
    )


def _read_tail(path: Path, limit: int = _LOG_TAIL_BYTES) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return data[-limit:].decode("utf-8", "replace")


def build_exec_router() -> APIRouter:
    router = APIRouter(prefix="/api/v0/local")

    def _gate(request: Request):
        """Return (config, None) when exec is allowed, else (None, error)."""
        cfg = request.app.state.config
        if cfg.workspace_dir is None:
            return None, _error("unconfigured", "no workspace configured (set WORKSPACE_DIR)", 409)
        if not cfg.local_exec_enabled:
            return None, _error(
                "exec_disabled",
                "local execution is disabled — set LOCAL_EXEC=1 to enable the "
                "Build/Submit/Run buttons (the dashboard then shells the SDK on this machine)",
                403,
            )
        if _sdk_bin() is None:
            return None, _error("exec_failed", "auspexai-tenant is not on PATH", 500)
        return cfg, None

    @router.post("/build")
    async def do_build(request: Request) -> JSONResponse:
        """`experiment build pkg/` — assemble pkg/manifest.json from
        experiment.toml. A fresh unique label each build, so a later submit
        never 409s. Local + fast; no key, no network."""
        cfg, err = _gate(request)
        if err:
            return err
        cmd = [_sdk_bin(), "experiment", "build", str(cfg.pkg_dir)]
        return _run_sync(cmd, cfg.workspace_dir, _BUILD_TIMEOUT_S)

    @router.post("/submit")
    async def do_submit(request: Request) -> JSONResponse:
        """`experiment submit pkg/ --key <key>` — sign the manifest, upload the
        package, create the experiment. The SDK signs with config.key_path."""
        cfg, err = _gate(request)
        if err:
            return err
        cmd = [
            _sdk_bin(),
            "experiment",
            "submit",
            str(cfg.pkg_dir),
            "--key",
            str(cfg.key_path),
        ]
        return _run_sync(cmd, cfg.workspace_dir, _SUBMIT_TIMEOUT_S)

    @router.post("/run")
    async def do_run(request: Request) -> JSONResponse:
        """Start `experiment run latest --key <key> --doorbell` as a managed
        background process (the driver runs for hours). Runs from
        `<workspace>/<[driver].run_cwd or .>` so the driver module imports. One
        run at a time — a second start while one is live is a 409."""
        cfg, err = _gate(request)
        if err:
            return err
        existing: LocalRun | None = getattr(request.app.state, "local_run", None)
        if existing is not None and existing.popen.poll() is None:
            return _error(
                "conflict", f"a run is already in progress (pid {existing.popen.pid})", 409
            )

        run_cwd = _resolve_run_cwd(cfg)
        log_dir = cfg.workspace_dir / ".auspexai"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "run.log"
        cmd = [
            _sdk_bin(),
            "experiment",
            "run",
            "latest",
            "--key",
            str(cfg.key_path),
            "--doorbell",
        ]
        try:
            log_fh = log_path.open("wb")
            log_fh.write(f"$ {' '.join(cmd)}  (cwd={run_cwd})\n".encode())
            log_fh.flush()
            popen = subprocess.Popen(
                cmd,
                cwd=str(run_cwd),
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # own process group → stop kills the driver's children too
            )
        except OSError as e:
            return _error("exec_failed", f"could not launch the run: {e}", 500)
        request.app.state.local_run = LocalRun(
            popen=popen, log_path=log_path, cmd=cmd, cwd=str(run_cwd), started_at=_now()
        )
        return JSONResponse({"started": True, "pid": popen.pid, "cwd": str(run_cwd)})

    @router.get("/run")
    async def run_status(request: Request) -> JSONResponse:
        """Live run state — the heart monitor's source. `running` + a growing
        log ⇒ working; `running` + a static log ⇒ idle between rounds; finished
        with rc 0 ⇒ converged/done; rc != 0 ⇒ problem."""
        run: LocalRun | None = getattr(request.app.state, "local_run", None)
        if run is None:
            return JSONResponse({"present": False})
        rc = run.popen.poll()
        log_size = run.log_path.stat().st_size if run.log_path.exists() else 0
        return JSONResponse(
            {
                "present": True,
                "running": rc is None,
                "pid": run.popen.pid,
                "returncode": rc,
                "started_at": run.started_at,
                "cwd": run.cwd,
                "log_size": log_size,
                "log_tail": _read_tail(run.log_path),
            }
        )

    @router.post("/run/stop")
    async def run_stop(request: Request) -> JSONResponse:
        """Stop the current run — SIGTERM the driver's process group, escalate
        to SIGKILL if it doesn't exit. Idempotent: stopping a finished run just
        reports its returncode."""
        run: LocalRun | None = getattr(request.app.state, "local_run", None)
        if run is None:
            return _error("not_found", "no run to stop", 404)
        rc = run.popen.poll()
        if rc is not None:
            return JSONResponse({"stopped": True, "returncode": rc, "already_exited": True})
        try:
            _terminate(run.popen)
        except OSError as e:
            return _error("exec_failed", f"could not stop the run: {e}", 500)
        return JSONResponse({"stopped": True, "returncode": run.popen.poll()})

    return router


def _resolve_run_cwd(cfg) -> Path:
    """`<workspace>/<[driver].run_cwd>` (default the workspace root). Lets a
    tenant whose driver lives in a subdir (e.g. vigiles' `driver/`) run from the
    right place without the dashboard knowing the layout. Never escapes the
    workspace."""
    import tomllib

    run_cwd = cfg.workspace_dir
    toml_path = cfg.experiment_toml_path
    if toml_path and toml_path.exists():
        try:
            driver = tomllib.loads(toml_path.read_text(encoding="utf-8")).get("driver", {})
        except (OSError, tomllib.TOMLDecodeError):
            driver = {}
        rel = driver.get("run_cwd")
        if isinstance(rel, str) and rel not in ("", "."):
            candidate = (cfg.workspace_dir / rel).resolve()
            if (
                cfg.workspace_dir.resolve() in candidate.parents
                or candidate == cfg.workspace_dir.resolve()
            ):
                run_cwd = candidate
    return run_cwd


def _terminate(popen: subprocess.Popen, grace_s: float = 5.0) -> None:
    """SIGTERM the process group, then SIGKILL after a grace period. The run was
    spawned with start_new_session=True, so its pid is the group leader and
    killing the group reaps the driver's children too."""
    try:
        os.killpg(popen.pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        popen.terminate()  # fallback if the group is already gone
    try:
        popen.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(popen.pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            popen.kill()
        popen.wait(timeout=grace_s)
