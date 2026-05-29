"""Runtime configuration for the researcher dashboard.

Unlike the operator console, this is a *locally-run, per-researcher* tool:
no session cookies, no OAuth, no passphrase factor. The researcher's identity
is their Ed25519 keypair from the tenant SDK; each request to the coordinator
is signed with it (RFC 9421), which lands in R-D1/R-D2. A dashboard instance
is single-tenant by construction — it holds exactly one key, so it can only
ever see one tenant's data (researcher_dashboard_design.md §3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# The tenant SDK's default key location. Kept in sync with
# auspexai_tenant.signing.DEFAULT_KEY_PATH; resolved dynamically when the SDK
# is importable, with this literal as the fallback for environments where it
# is not yet installed.
_SDK_DEFAULT_KEY_PATH = Path.home() / ".config" / "auspexai-tenant" / "maintainer_key"


def _default_key_path() -> Path:
    try:
        from auspexai_tenant.signing import DEFAULT_KEY_PATH  # type: ignore

        return Path(DEFAULT_KEY_PATH)
    except Exception:
        return _SDK_DEFAULT_KEY_PATH


@dataclass(frozen=True)
class ResearcherDashboardConfig:
    """Loaded configuration. Env-only; everything is either a compile-time
    default or a per-machine path."""

    coord_url: str
    bind_host: str
    bind_port: int
    static_dir: Path
    key_path: Path
    open_browser: bool

    @classmethod
    def from_env(cls) -> ResearcherDashboardConfig:
        return cls(
            coord_url=os.environ.get("COORD_URL", "https://coord.auspexai.network"),
            bind_host=os.environ.get("HOST", "127.0.0.1"),
            bind_port=int(os.environ.get("PORT", "4228")),
            static_dir=Path(
                os.environ.get(
                    "STATIC_DIR",
                    str(Path(__file__).parent / "static"),
                )
            ),
            key_path=Path(os.environ.get("AUSPEXAI_TENANT_KEY", str(_default_key_path()))),
            open_browser=os.environ.get("OPEN_BROWSER", "true").lower() in ("1", "true", "yes"),
        )
