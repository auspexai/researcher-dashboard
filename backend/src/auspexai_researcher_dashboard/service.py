"""Persistent local-service management for the researcher dashboard.

The dashboard is a locally-run server (uvicorn on ``127.0.0.1``); to make it
always-on — survive logout/reboot so it is simply *there* when the researcher
opens the browser — the installer (or a ``pip``-install user directly) registers
it as a per-user background service. This module is the single, cross-platform
implementation both paths call, so ``curl … | bash`` and a manual ``pip
install`` reach the *same* persistent server (the design's "installer provisions,
product manages itself" — researcher_onboarding_and_rd_surfaces_design.md §0/§1).

- **macOS** → a launchd LaunchAgent (``~/Library/LaunchAgents/<label>.plist``),
  ``RunAtLoad`` + ``KeepAlive``; LaunchAgents start at login with no linger fuss.
- **Linux** → a systemd ``--user`` unit (``~/.config/systemd/user/<name>.service``);
  surviving logout additionally needs ``loginctl enable-linger`` (the installer
  does that with the user's consent, like the worker onramp).
- **Other** → unsupported; callers fall back to a foreground ``serve``.

The unit only ever runs ``auspexai-dashboard serve --no-browser`` bound to
localhost — never network-exposed. All subprocess calls funnel through an
injectable runner so the rendering + command sequence are unit-testable without
touching the real ``launchctl`` / ``systemctl``.
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

LAUNCHD_LABEL = "network.auspexai.dashboard"
SYSTEMD_UNIT = "auspexai-dashboard.service"

# Per-user XDG state (logs); mirrors the installer's `auspexai-researcher`
# namespace. Config + key stay where the SDK puts them (~/.config/auspexai-*).
STATE_DIR = Path.home() / ".local" / "state" / "auspexai-researcher"

Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]


def _default_runner(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(cmd), capture_output=True, text=True, check=False)


def dashboard_executable() -> str:
    """Absolute path to the installed ``auspexai-dashboard`` console script.

    Prefer the script in the *same venv* as the running interpreter (the install
    venv) over a PATH lookup, so the service points at the real binary rather
    than a symlink that a later reinstall could dangle.
    """
    candidate = Path(sys.executable).parent / "auspexai-dashboard"
    if candidate.exists():
        return str(candidate)
    found = shutil.which("auspexai-dashboard")
    return found or "auspexai-dashboard"


def launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def systemd_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / SYSTEMD_UNIT


def render_launchd_plist(executable: str, *, port: int, log_dir: Path = STATE_DIR) -> bytes:
    """The LaunchAgent plist bytes. KeepAlive + RunAtLoad = always-on; stdout/err
    to the state dir so a crash loop is diagnosable."""
    out = str(log_dir / "dashboard.out.log")
    err = str(log_dir / "dashboard.err.log")
    spec = {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [executable, "serve", "--no-browser"],
        "EnvironmentVariables": {"PORT": str(port)},
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "StandardOutPath": out,
        "StandardErrorPath": err,
    }
    return plistlib.dumps(spec)


def render_systemd_unit(executable: str, *, port: int) -> str:
    """The systemd --user unit text. Restart=on-failure mirrors KeepAlive;
    journald captures logs (no explicit file)."""
    return (
        "[Unit]\n"
        "Description=AuspexAI researcher dashboard (local, tenant-scoped)\n"
        "Documentation=https://github.com/auspexai/researcher-dashboard\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"Environment=PORT={port}\n"
        f"ExecStart={executable} serve --no-browser\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


@dataclass
class ServiceManager:
    """Cross-platform per-user service control. Inject ``run`` + ``platform`` in
    tests; production uses the live subprocess runner and ``sys.platform``."""

    run: Runner = _default_runner
    platform: str = sys.platform
    port: int = 4228

    @property
    def supported(self) -> bool:
        return self.platform == "darwin" or self.platform.startswith("linux")

    def install(self) -> str:
        """Write the unit and (re)load it so the dashboard is running + persistent.
        Idempotent: an existing unit is reloaded, not duplicated. Returns a short
        human status line."""
        exe = dashboard_executable()
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if self.platform == "darwin":
            return self._install_launchd(exe)
        if self.platform.startswith("linux"):
            return self._install_systemd(exe)
        raise RuntimeError(
            f"persistent service not supported on {self.platform!r}; "
            "run `auspexai-dashboard serve` in the foreground instead"
        )

    def uninstall(self) -> str:
        if self.platform == "darwin":
            return self._uninstall_launchd()
        if self.platform.startswith("linux"):
            return self._uninstall_systemd()
        return "no service to remove on this platform"

    def restart(self) -> str:
        """Bounce the service (used on upgrade so the new code is live)."""
        if self.platform == "darwin":
            plist = launchd_plist_path()
            if not plist.exists():
                return self.install()
            self.run(["launchctl", "unload", str(plist)])
            self.run(["launchctl", "load", "-w", str(plist)])
            return "restarted (launchd)"
        if self.platform.startswith("linux"):
            if not systemd_unit_path().exists():
                return self.install()
            self.run(["systemctl", "--user", "restart", SYSTEMD_UNIT])
            return "restarted (systemd --user)"
        return "no service on this platform"

    def status(self) -> str:
        if self.platform == "darwin":
            r = self.run(["launchctl", "list", LAUNCHD_LABEL])
            return "running (launchd)" if r.returncode == 0 else "not loaded"
        if self.platform.startswith("linux"):
            r = self.run(["systemctl", "--user", "is-active", SYSTEMD_UNIT])
            return (r.stdout or "").strip() or "unknown"
        return "unsupported platform"

    # ---- launchd ----------------------------------------------------------
    def _install_launchd(self, exe: str) -> str:
        plist = launchd_plist_path()
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_bytes(render_launchd_plist(exe, port=self.port))
        # Reload cleanly: unload an old copy first (ignore failure), then load -w
        # to mark it enabled across logins.
        self.run(["launchctl", "unload", str(plist)])
        self.run(["launchctl", "load", "-w", str(plist)])
        return f"installed + loaded launchd agent ({plist})"

    def _uninstall_launchd(self) -> str:
        plist = launchd_plist_path()
        if plist.exists():
            self.run(["launchctl", "unload", str(plist)])
            plist.unlink()
            return f"removed launchd agent ({plist})"
        return "no launchd agent installed"

    # ---- systemd ----------------------------------------------------------
    def _install_systemd(self, exe: str) -> str:
        unit = systemd_unit_path()
        unit.parent.mkdir(parents=True, exist_ok=True)
        unit.write_text(render_systemd_unit(exe, port=self.port))
        self.run(["systemctl", "--user", "daemon-reload"])
        self.run(["systemctl", "--user", "enable", "--now", SYSTEMD_UNIT])
        return f"installed + started systemd --user unit ({unit})"

    def _uninstall_systemd(self) -> str:
        unit = systemd_unit_path()
        if unit.exists():
            self.run(["systemctl", "--user", "disable", "--now", SYSTEMD_UNIT])
            unit.unlink()
            self.run(["systemctl", "--user", "daemon-reload"])
            return f"removed systemd --user unit ({unit})"
        return "no systemd unit installed"
