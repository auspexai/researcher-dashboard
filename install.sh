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
warn() { printf '\033[1;33m[auspexai]\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31m[auspexai]\033[0m %s\n' "$*" >&2; exit 1; }

# ── supply-chain verification (cosign keyless signatures; best-effort) ────────
# The AuspexAI release wheels are cosign-signed (keyless OIDC). We verify the
# signature when cosign is obtainable — a BAD signature ABORTS the install — and
# otherwise fall back to a sha256 check against the release SHA256SUMS with a
# loud warning rather than blocking the install. A bare `pip install <pkg>` from
# PyPI does no such check; this fetches + verifies the signed GitHub-release
# wheels for both AuspexAI packages (deps still resolve from PyPI).
COSIGN_VERSION="v2.5.0"
COSIGN_BIN=""

_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'; fi
}

ensure_cosign() {
  [ -n "$COSIGN_BIN" ] && return 0
  if command -v cosign >/dev/null 2>&1; then COSIGN_BIN="cosign"; return 0; fi
  local osname os arch bin tmp want got
  osname="$(uname -s)"
  if [ "$osname" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
    brew install cosign >/dev/null 2>&1 && command -v cosign >/dev/null 2>&1 && { COSIGN_BIN="cosign"; return 0; }
  fi
  case "$osname" in Darwin) os="darwin" ;; *) os="linux" ;; esac
  case "$(uname -m)" in arm64 | aarch64) arch="arm64" ;; x86_64 | amd64) arch="amd64" ;; *) return 1 ;; esac
  bin="cosign-${os}-${arch}"; tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/cosign" "https://github.com/sigstore/cosign/releases/download/${COSIGN_VERSION}/${bin}" 2>/dev/null || return 1
  curl -fsSL -o "$tmp/sums" "https://github.com/sigstore/cosign/releases/download/${COSIGN_VERSION}/cosign_checksums.txt" 2>/dev/null || return 1
  want="$(grep " ${bin}\$" "$tmp/sums" 2>/dev/null | awk '{print $1}')"
  got="$(_sha256 "$tmp/cosign")"
  [ -n "$want" ] && [ "$want" = "$got" ] || return 1
  chmod +x "$tmp/cosign" && COSIGN_BIN="$tmp/cosign" && return 0
  return 1
}

verify_artifact() { # local-path  download-url
  local path="$1" url="$2"
  if ensure_cosign; then
    curl -fsSL -o "${path}.sig" "${url}.sig" 2>/dev/null || true
    curl -fsSL -o "${path}.cert" "${url}.cert" 2>/dev/null || true
    if [ -s "${path}.sig" ] && [ -s "${path}.cert" ]; then
      say "verifying $(basename "$path") (cosign) …"
      if "$COSIGN_BIN" verify-blob \
        --certificate-identity-regexp='^https://github\.com/auspexai/.+/\.github/workflows/.+@.+$' \
        --certificate-oidc-issuer='https://token.actions.githubusercontent.com' \
        --signature "${path}.sig" --certificate "${path}.cert" "$path" >/dev/null 2>&1; then
        say "✓ $(basename "$path") — signature verified (AuspexAI Maintainer OIDC identity)"
        return 0
      fi
      fail "SIGNATURE VERIFICATION FAILED for $(basename "$path") — refusing to install. The artifact may be tampered."
    fi
    warn "could not fetch the signature for $(basename "$path"); falling back to a checksum"
  fi
  _verify_sha256 "$path" "$url"
}

_verify_sha256() { # local-path  download-url
  local path="$1" url="$2" base sums want got
  base="$(basename "$path")"
  sums="$(curl -fsSL "${url%/*}/SHA256SUMS" 2>/dev/null)" || {
    warn "⚠ SIGNATURE NOT VERIFIED (cosign unavailable) and SHA256SUMS unreachable — proceeding on transport trust only."
    return 0
  }
  want="$(printf '%s\n' "$sums" | grep " ${base}\$" | awk '{print $1}')"
  got="$(_sha256 "$path")"
  if [ -n "$want" ] && [ "$want" = "$got" ]; then
    warn "⚠ $base signature NOT verified (cosign unavailable) — integrity confirmed against SHA256SUMS only. Install cosign for full verification."
    return 0
  fi
  [ -n "$want" ] && fail "CHECKSUM MISMATCH for $base — refusing to install."
  warn "⚠ SIGNATURE NOT VERIFIED and $base absent from SHA256SUMS — proceeding on transport trust only."
}

# Fetch a URL with bounded retries. Transient blips (residential networks,
# GitHub's edge) are NORMAL — one must not kill an install — and a GitHub API
# rate-limit must SAY so instead of hiding behind a generic "could not reach".
# Echoes the response body; exit 0 = ok, 3 = rate-limited (403/429) after the
# budget, 1 = other failure after the budget.
_fetch_with_retry() { # url
  local url="$1" out http i rc=1
  for i in 1 2 3; do
    [ "$i" -gt 1 ] && sleep "$i"
    out="$(curl -sSL -w '\n%{http_code}' "$url" 2>/dev/null)" || { rc=1; continue; }
    http="${out##*$'\n'}"
    case "$http" in
      2*)
        printf '%s' "${out%$'\n'*}"
        return 0
        ;;
      403 | 429) rc=3 ;;
      *) rc=1 ;;
    esac
  done
  return "$rc"
}

# Resolve the latest signed release wheel for a repo, download + verify it.
VERIFIED_WHL=""
fetch_verified_wheel() { # display-name  github-repo -> sets VERIFIED_WHL
  local name="$1" repo="$2" meta tag whl url rc i
  meta="$(_fetch_with_retry "https://api.github.com/repos/auspexai/$repo/releases/latest")"
  rc=$?
  if [ "$rc" = "3" ]; then
    fail "GitHub API rate limit hit fetching the latest $name release (60/hr per IP, unauthenticated) — wait a few minutes and re-run"
  elif [ "$rc" != "0" ]; then
    fail "could not reach GitHub for the latest $name release (after 3 attempts) — check your network and re-run"
  fi
  tag="$(printf '%s' "$meta" | sed -nE 's/.*"tag_name": *"([^"]+)".*/\1/p' | head -1)"
  whl="$(printf '%s' "$meta" | grep -oE '"name": *"[^"]+\.whl"' | head -1 | sed -E 's/.*"([^"]+\.whl)".*/\1/')"
  [ -n "$tag" ] && [ -n "$whl" ] || fail "no signed wheel in the latest $name release"
  url="https://github.com/auspexai/$repo/releases/download/$tag/$whl"
  for i in 1 2 3; do
    [ "$i" -gt 1 ] && sleep "$i"
    if curl -fsSL -o "$WHEELS_TMP/$whl" "$url"; then break; fi
    [ "$i" = 3 ] && fail "could not download $whl (after 3 attempts) — check your network and re-run"
  done
  verify_artifact "$WHEELS_TMP/$whl" "$url"
  VERIFIED_WHL="$WHEELS_TMP/$whl"
}

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
say "fetching + verifying the signed release wheels (dashboard + SDK) …"
WHEELS_TMP="$(mktemp -d)"
fetch_verified_wheel "researcher-dashboard" researcher-dashboard
RD_WHL="$VERIFIED_WHL"
fetch_verified_wheel "tenant-sdk" tenant-sdk
SDK_WHL="$VERIFIED_WHL"
# Install the two VERIFIED AuspexAI wheels; their other deps resolve from PyPI.
# Both named explicitly so pip's only-if-needed strategy can't leave a stale SDK
# when only the dashboard moved.
say "installing the verified wheels …"
"$APP_DIR/bin/pip" install --quiet --upgrade "$RD_WHL" "$SDK_WHL"
rm -rf "$WHEELS_TMP"

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
