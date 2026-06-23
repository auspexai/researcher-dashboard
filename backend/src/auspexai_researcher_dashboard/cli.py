"""Click CLI for `auspexai-dashboard`.

The launch command starts the local FastAPI server and opens the researcher's
browser to it — the locally-run-tool model from researcher_dashboard_design.md
§4. Mirrors the operator console's `serve`, minus the network-service framing
(this runs on the researcher's own machine, bound to localhost by default).
"""

from __future__ import annotations

import threading
import webbrowser

import click
import uvicorn

from . import __version__
from .config import ResearcherDashboardConfig


@click.group(help="AuspexAI researcher dashboard (locally-run, tenant-scoped).")
@click.version_option(version=__version__, prog_name="auspexai-dashboard")
def cli() -> None:
    pass


@cli.command()
@click.option("--host", default=None, help="Bind host (default: 127.0.0.1 or $HOST).")
@click.option("--port", default=None, type=int, help="Bind port (default: 4228 or $PORT).")
@click.option("--no-browser", is_flag=True, help="Do not open a browser window.")
@click.option("--reload", is_flag=True, help="Reload on source changes (dev only).")
def serve(host: str | None, port: int | None, no_browser: bool, reload: bool) -> None:
    """Run the researcher dashboard locally and open it in a browser."""
    config = ResearcherDashboardConfig.from_env()
    bind_host = host or config.bind_host
    bind_port = port or config.bind_port

    if not config.key_path.is_file():
        click.echo(
            f"Note: no tenant key found at {config.key_path}. "
            "Generate one with `auspexai-tenant key generate` once your tenant "
            "is approved; the dashboard reads it to sign coordinator requests."
        )

    if config.open_browser and not no_browser and not reload:
        url = f"http://{bind_host}:{bind_port}/"

        def _open() -> None:
            webbrowser.open(url)

        # Defer until the server has a moment to bind.
        threading.Timer(1.0, _open).start()

    uvicorn.run(
        "auspexai_researcher_dashboard.main:create_app",
        factory=True,
        host=bind_host,
        port=bind_port,
        reload=reload,
        log_level="info",
    )


@cli.group()
def service() -> None:
    """Manage the dashboard as a persistent background service.

    Registers `serve --no-browser` as a per-user service (launchd on macOS,
    systemd --user on Linux) so the dashboard is always running — the same
    command the installer calls, so a `pip install` reaches the identical setup.
    """


@service.command("install")
@click.option("--port", default=None, type=int, help="Bind port (default: 4228 or $PORT).")
def service_install(port: int | None) -> None:
    """Install + start the persistent dashboard service."""
    from .service import ServiceManager

    bind_port = port or ResearcherDashboardConfig.from_env().bind_port
    mgr = ServiceManager(port=bind_port)
    if not mgr.supported:
        click.echo(
            f"Persistent service is not supported on {mgr.platform!r}. "
            "Run `auspexai-dashboard serve` in the foreground instead.",
            err=True,
        )
        raise SystemExit(1)
    click.echo(mgr.install())
    click.echo(f"Dashboard: http://127.0.0.1:{bind_port}/")


@service.command("uninstall")
def service_uninstall() -> None:
    """Stop + remove the persistent dashboard service."""
    from .service import ServiceManager

    click.echo(ServiceManager().uninstall())


@service.command("restart")
def service_restart() -> None:
    """Restart the service (used on upgrade so the new code goes live)."""
    from .service import ServiceManager

    click.echo(ServiceManager().restart())


@service.command("status")
def service_status() -> None:
    """Report whether the persistent service is loaded/running."""
    from .service import ServiceManager

    click.echo(ServiceManager().status())


def main() -> None:
    cli(prog_name="auspexai-dashboard")


if __name__ == "__main__":
    main()
