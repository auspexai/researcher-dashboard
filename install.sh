#!/usr/bin/env bash
# AuspexAI researcher onramp — provisions the SDK + dashboard into a dedicated
# venv, puts the commands on your PATH (with consent), and registers the
# dashboard as an always-on local service. The installer PROVISIONS; the
# dashboard UI ONBOARDS (apply → run Vigiles) — so this script stays thin and a
# plain `pip install` reaches the identical guided setup via `auspexai-dashboard
# service install`. Mirrors the worker installer's conventions: idempotent
# (re-run = graceful upgrade), consent-gated shell edits, loud about every step.
# Usage:
#   curl -fsSL https://getresearcher.auspexai.network | bash
set -euo pipefail

APP_DIR="${AUSPEXAI_RESEARCHER_HOME:-$HOME/.local/share/auspexai-researcher}"
BIN_DIR="$HOME/.local/bin"
COMMANDS=(auspexai-tenant auspexai-dashboard)
DASH_PORT="${AUSPEXAI_DASHBOARD_PORT:-4228}"
LAUNCHD_LABEL="network.auspexai.dashboard"
SYSTEMD_UNIT="auspexai-dashboard.service"

say()  { printf '\033[1m[auspexai]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[auspexai]\033[0m %s\n' "$*" >&2; exit 1; }

# Fresh install vs update: an existing dashboard binary in the venv ⇒ update.
# Updates stop the service before overwriting binaries and skip the welcome;
# fresh installs open the dashboard so the product can onboard the researcher.
UPDATING=0
[ -x "$APP_DIR/bin/auspexai-dashboard" ] && UPDATING=1

# Stop a running service before overwriting binaries. Platform-direct (not via
# the CLI) because the INSTALLED binary may predate the `service` command.
stop_service() {
  case "$(uname -s)" in
    Darwin) launchctl unload "$HOME/Library/LaunchAgents/${LAUNCHD_LABEL}.plist" 2>/dev/null || true ;;
    Linux)  systemctl --user stop "$SYSTEMD_UNIT" 2>/dev/null || true ;;
  esac
}

# ── python ≥ 3.11 ────────────────────────────────────────────────────────────
PY=""
for cand in python3.13 python3.12 python3.11 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
      PY="$cand"; break
    fi
  fi
done
[ -n "$PY" ] || fail "needs Python >= 3.11 (none found). Install one, then re-run."
say "using $($PY --version 2>&1)"

# ── dedicated venv (never touches system or user site-packages) ─────────────
if [ ! -x "$APP_DIR/bin/pip" ]; then
  say "creating environment at $APP_DIR"
  "$PY" -m venv "$APP_DIR"
else
  say "existing install at $APP_DIR — upgrading gracefully"
  stop_service
fi
"$APP_DIR/bin/pip" install --quiet --upgrade pip
# pip overlays without cleaning: stale .py from a prior version survives an
# upgrade-in-place. Wipe both packages' dirs first so the new version is clean.
if [ "$UPDATING" = "1" ]; then
  say "clearing previous package files (pip overlay)"
  rm -rf "$APP_DIR"/lib/python*/site-packages/auspexai_tenant* \
         "$APP_DIR"/lib/python*/site-packages/auspexai_researcher_dashboard* 2>/dev/null || true
fi
say "installing auspexai-researcher-dashboard + auspexai-tenant from PyPI"
# Both named explicitly: pip's only-if-needed strategy would otherwise leave
# an already-satisfied SDK on an old version when only the dashboard moved.
"$APP_DIR/bin/pip" install --quiet --upgrade auspexai-researcher-dashboard auspexai-tenant

# ── expose the commands ──────────────────────────────────────────────────────
mkdir -p "$BIN_DIR"
for cmd in "${COMMANDS[@]}"; do
  [ -x "$APP_DIR/bin/$cmd" ] || fail "$cmd missing from the installed package (bug — please report)"
  ln -sf "$APP_DIR/bin/$cmd" "$BIN_DIR/$cmd"
done
say "linked: ${COMMANDS[*]} -> $BIN_DIR"

# ── PATH (consent-gated, tty-aware — the worker installer convention) ───────
case ":$PATH:" in
  *":$BIN_DIR:"*)
    ON_PATH=1 ;;
  *)
    ON_PATH=0 ;;
esac
if [ "$ON_PATH" = "0" ]; then
  RC=""
  case "${SHELL:-}" in
    */zsh)  RC="$HOME/.zshrc" ;;
    */bash) RC="$HOME/.bashrc" ;;
  esac
  PATH_LINE="export PATH=\"\$PATH:$BIN_DIR\""
  if [ -n "$RC" ] && (exec </dev/tty) 2>/dev/null; then
    printf '\033[1m[auspexai]\033[0m %s is not on your PATH. Append to %s? [Y/n] ' "$BIN_DIR" "$RC"
    read -r reply </dev/tty || reply="n"
    case "$reply" in
      n|N|no|NO) say "skipped — add it yourself:  $PATH_LINE" ;;
      *)
        if ! grep -qF "$BIN_DIR" "$RC" 2>/dev/null; then
          printf '\n# added by the AuspexAI researcher installer\n%s\n' "$PATH_LINE" >> "$RC"
        fi
        say "added to $RC — takes effect in new shells (or: source $RC)" ;;
    esac
  else
    say "NOTE: $BIN_DIR is not on your PATH. Add it:  $PATH_LINE"
  fi
fi

# ── persistent service (curl ≡ pip: the SAME command a pip user runs) ────────
# Registers `serve --no-browser` as a per-user service (launchd on macOS,
# systemd --user on Linux) so the dashboard is always on. Idempotent — it
# (re)writes + (re)loads the unit, which also restarts it after this upgrade.
if "$APP_DIR/bin/auspexai-dashboard" service install --port "$DASH_PORT" >/dev/null 2>&1; then
  say "dashboard running as a background service → http://127.0.0.1:$DASH_PORT/"
else
  say "NOTE: could not register a background service on this platform —"
  say "      run it yourself when needed:  auspexai-dashboard serve"
fi

# Survive logout (Linux only; macOS LaunchAgents already start at login).
if [ "$(uname -s)" = "Linux" ] && command -v loginctl >/dev/null 2>&1; then
  if [ "$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null)" != "yes" ]; then
    say "to keep it running after logout:  sudo loginctl enable-linger $(id -un)"
  fi
fi

# ── done ─────────────────────────────────────────────────────────────────────
say "installed: $("$APP_DIR/bin/auspexai-dashboard" --version 2>/dev/null || echo auspexai-dashboard) ✓"
say "installed: $("$APP_DIR/bin/auspexai-tenant" --version 2>/dev/null || echo auspexai-tenant) ✓"

URL="http://127.0.0.1:$DASH_PORT/"
if [ "$UPDATING" = "1" ]; then
  say "update complete — your dashboard is back up at $URL"
else
  # Fresh install: open the dashboard once. The product onboards from here
  # (the Overview tracks your application and goes green on approval).
  if (exec </dev/tty) 2>/dev/null; then
    case "$(uname -s)" in
      Darwin) open "$URL" 2>/dev/null || true ;;
      Linux)  command -v xdg-open >/dev/null 2>&1 && xdg-open "$URL" 2>/dev/null || true ;;
    esac
  fi
  cat <<NEXT

You're set up. Your dashboard is open at $URL.
Next:
  1. Apply for a research tenant:  auspexai-tenant apply   (GitHub sign-in)
  2. The dashboard tracks your application — it goes green on approval.
  3. Once approved, run the Vigiles starter to see your first results.

Full guide: https://github.com/auspexai/.github/blob/main/ONBOARDING.md
NEXT
fi
