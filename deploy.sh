#!/usr/bin/env bash
# deploy.sh — idempotent deploy script for trading-signals droplet.
# Phase 11 D-20..D-25 (CONTEXT.md, 2026-04-24 reconciled post-REVIEWS):
#   D-20: strict mode (set -euo pipefail)
#   D-21: runs as `trader` (sudoers grants passwordless restart for two units)
#   D-22: branch safety check (must be on main)
#   D-23: sequence:
#         1) branch check  2) git fetch  3) git pull --ff-only
#         4) [DROPPED — pip-upgrade per REVIEWS MEDIUM #7]
#         5) pip install -r requirements.txt
#         6) TWO sudo -n systemctl restart calls (REVIEWS HIGH #4 —
#            combined form may not match sudoers rules; `-n` fails fast)
#         7) curl /healthz in a retry loop (REVIEWS HIGH #3 — replaces
#            `sleep 3 && curl` heuristic; 10 attempts @ 1s)
#         8) echo success + commit hash
#   D-24: idempotent on no-op re-run
#   D-25: NO auto-revert (fail-loud; D-25)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${SCRIPT_DIR}"
cd "${REPO_DIR}"

echo "[deploy] starting deploy at $(date '+%Y-%m-%d %H:%M:%S')"

# D-22: branch safety check FIRST
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "${BRANCH}" != 'main' ]; then
  echo "[deploy] ERROR: expected branch 'main', got '${BRANCH}'. Aborting." >&2
  exit 1
fi
echo "[deploy] branch: ${BRANCH} — OK"

# D-23 step 2: fetch
echo "[deploy] fetching from origin..."
git fetch origin main

# D-23 step 3: fast-forward only
echo "[deploy] pulling (ff-only)..."
git pull --ff-only origin main

# D-23 step 4 was pip-upgrade — DROPPED per REVIEWS MEDIUM #7.

# Python runtime guard/provisioning: enforce repo pin (3.13) on droplet.
if [ ! -x .venv/bin/python ]; then
  if ! command -v python3.13 > /dev/null 2>&1; then
    echo "[deploy] ERROR: python3.13 not found. Install Python 3.13 before deploy." >&2
    exit 1
  fi
  echo "[deploy] .venv missing — creating with python3.13..."
  python3.13 -m venv .venv
fi

if ! .venv/bin/python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)"; then
  echo "[deploy] ERROR: .venv is not Python 3.13. Recreate with: rm -rf .venv && python3.13 -m venv .venv" >&2
  exit 1
fi

# Some distro builds can leave a venv without the pip launcher script.
if ! .venv/bin/python -m pip --version > /dev/null 2>&1; then
  echo "[deploy] pip missing in .venv — bootstrapping ensurepip..."
  if ! .venv/bin/python -m ensurepip --upgrade > /dev/null 2>&1; then
    echo "[deploy] ERROR: could not bootstrap pip in .venv. Recreate venv after installing python3.13-venv." >&2
    exit 1
  fi
fi

# D-23 step 5: install requirements (idempotent)
echo "[deploy] installing requirements..."
.venv/bin/python -m pip install -r requirements.txt

# D-23 step 6: restart BOTH units via TWO `sudo -n` calls (REVIEWS HIGH #4)
echo "[deploy] restarting services..."
sudo -n systemctl restart trading-signals
sudo -n systemctl restart trading-signals-web

# D-23 step 7: smoke test — retry loop (REVIEWS HIGH #3)
echo "[deploy] smoke testing /healthz..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS --max-time 2 http://127.0.0.1:8000/healthz > /dev/null 2>&1; then
    echo "[deploy] /healthz OK after ${i} attempt(s)"
    break
  fi
  if [ "${i}" = "10" ]; then
    echo "[deploy] ERROR: /healthz did not respond within 10s. Check 'journalctl -u trading-signals-web -n 50'." >&2
    exit 1
  fi
  sleep 1
done

# D-20 (Phase 12): reverse-proxy config test + reload hook, gated.
# Pre-Phase-12 droplets (no reverse-proxy binary installed) skip
# silently via `command -v` — the first use of optional-feature
# gating in deploy.sh. Repo checkouts without nginx/signals.conf
# (pre-Plan-01) also skip via the file-existence check.
#
# Requires the 4-rule sudoers entry (operator sets per SETUP-HTTPS.md
# Step 8) — absolute paths for all four commands live in the sudoers
# rule itself, not in this script (REVIEWS MEDIUM: secure_path in
# /etc/sudoers resolves the PATH-relative names below).
#
# Ordering rationale (RESEARCH Open Question 5): reload AFTER
# FastAPI restart + smoke test means a failed restart aborts via
# `set -e` before we reload — no point routing traffic to a
# broken app.
if [ -f nginx/signals.conf ] && command -v nginx &>/dev/null; then
  echo "[deploy] nginx config detected — testing + reloading..."
  sudo -n nginx -t
  sudo -n systemctl reload nginx
  echo "[deploy] nginx reloaded"
fi

# D-23 step 8: success
COMMIT=$(git rev-parse --short HEAD)
echo "[deploy] deploy complete. commit=${COMMIT}"
