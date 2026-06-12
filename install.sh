#!/usr/bin/env bash
# AuspexAI researcher onramp — installs the SDK + dashboard into a dedicated
# venv and puts the commands on your PATH (with consent). Mirrors the worker
# installer's conventions: idempotent (re-run = upgrade), consent-gated shell
# edits, loud about every step. Usage:
#   curl -fsSL https://raw.githubusercontent.com/auspexai/researcher-dashboard/main/install.sh | bash
set -euo pipefail

APP_DIR="${AUSPEXAI_RESEARCHER_HOME:-$HOME/.local/share/auspexai-researcher}"
BIN_DIR="$HOME/.local/bin"
COMMANDS=(auspexai-tenant auspexai-dashboard)

say()  { printf '\033[1m[auspexai]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[auspexai]\033[0m %s\n' "$*" >&2; exit 1; }

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
  say "existing environment at $APP_DIR (upgrading in place)"
fi
"$APP_DIR/bin/pip" install --quiet --upgrade pip
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

# ── done ─────────────────────────────────────────────────────────────────────
say "installed: $("$APP_DIR/bin/auspexai-dashboard" --version 2>/dev/null || echo auspexai-dashboard) ✓"
say "installed: $("$APP_DIR/bin/auspexai-tenant" --version 2>/dev/null || echo auspexai-tenant) ✓"
cat <<'NEXT'

Next steps (full guide: https://github.com/auspexai/.github/blob/main/ONBOARDING.md):
  auspexai-tenant apply        # apply for a research tenant (GitHub sign-in)
  auspexai-dashboard serve     # your local dashboard, once approved
NEXT
