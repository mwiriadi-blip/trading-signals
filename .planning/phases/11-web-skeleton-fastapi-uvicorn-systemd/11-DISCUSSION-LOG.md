# Phase 11: Web Skeleton — FastAPI + uvicorn + systemd — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-24
**Phase:** 11-web-skeleton-fastapi-uvicorn-systemd
**Areas discussed:** FastAPI app layout, systemd unit config, /healthz response shape, deploy.sh safety posture

---

## FastAPI app layout + structure

| Option | Description | Selected |
|--------|-------------|----------|
| web/ dir + factory pattern (Recommended) | New `web/` directory. `web/app.py` exposes `create_app() -> FastAPI` factory + module-level `app`. Future `web/routes/`, `web/middleware/`. Shared `.venv`. `fastapi`, `uvicorn[standard]`, `httpx` pinned in requirements.txt. | ✓ |
| Single web_app.py at repo root (flat) | One file. Matches v1.0 flat layout. Harder to scale when Phases 14+ add route modules. | |
| Separate venv + requirements-web.txt | Isolates web deps. Two pip installs during deploy. Overhead not justified. | |

**User's choice:** web/ dir + factory pattern (Recommended)
**Notes:** Captured as D-01..D-05. D-01 locks the `web/` directory convention; D-02 locks the factory pattern for test isolation + uvicorn startup compatibility; D-03 pre-establishes `routes/` + `middleware/` subdirs for Phases 13-15 fill-in; D-04 locks the shared venv; D-05 defers exact version pins to planner (with baseline suggestion `fastapi==0.115.5`, `uvicorn[standard]==0.34.0`, `httpx==0.28.1`).

---

## systemd unit config — user, restart policy, dependencies

| Option | Description | Selected |
|--------|-------------|----------|
| trader user, on-failure restart, soft-dep on trading-signals (Recommended) | User/Group=trader. Restart=on-failure, RestartSec=10s. After=network.target, Wants=trading-signals.service. Hardening (NoNewPrivileges, ProtectSystem, ReadWritePaths). | ✓ |
| Dedicated tradingsignals-web user + stricter isolation | New system user, no sudo. Maximal isolation but two user accounts to manage. Overkill. | |
| trader user + always-restart + hard dep | Requires= trading-signals.service. Hard coupling — web fails if signals fails. Bad for historical-state viewing during signal debugging. | |

**User's choice:** trader user, on-failure restart, soft-dep on trading-signals (Recommended)
**Notes:** Captured as D-06..D-12. D-06 creates the separate `trading-signals-web.service` unit; D-07 reuses the `trader` user; D-08 Restart=on-failure+10s; D-09 soft Wants= dependency (web runs without signal unit for historical-state inspection); D-10 reuses v1.0 Phase 7 hardening (NoNewPrivileges, ProtectSystem strict, ReadWritePaths=/home/trader/trading-signals, ProtectHome=read-only); D-11 locks ExecStart with `127.0.0.1:8000` + workers=1 (preserves Phase 8 `_LAST_LOADED_STATE` single-threaded assumption); D-12 journald for logs.

---

## /healthz response shape + degraded-state behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Always 200 if process up; include degraded flags (Recommended) | `{"status": "ok", "last_run": "<iso-or-null>", "stale": <bool>}`. 200 when FastAPI process is alive. Stale flag reuses Phase 8 2-day threshold. Auth-exempt. | ✓ |
| 200 healthy / 503 degraded split | 503 on stale/missing state. Monitors auto-alert. Conflates process liveness with pipeline health. | |
| Minimal — just 200 OK, no body | Empty 200. Loses `last_run` context. Too minimal. | |

**User's choice:** Always 200 if process up; include degraded flags (Recommended)
**Notes:** Captured as D-13..D-19. D-13 locks the JSON schema; D-14 keeps HTTP 200 tied to process-liveness (not pipeline health); D-15 reads `state['last_run']` via `state_manager.load_state()`; D-16 locks the `stale` threshold at 2 days (reuses Phase 8 ERR-05); D-17 confirms auth exemption (WEB-07 requirement); D-18 no caching — fresh read each request (state.json is small); D-19 defensive error handling returns 200 even if state read fails (process health is the contract, not pipeline health). Rationale: separates "web up" monitoring from "signal pipeline healthy" monitoring — single-operator observability doesn't need both collapsed into one HTTP status.

---

## deploy.sh safety posture

| Option | Description | Selected |
|--------|-------------|----------|
| set -euo pipefail + branch check + atomic restart (Recommended) | Strict bash; run as trader with scoped sudoers entry for the two unit names; refuse deploy if not on main; git fetch+pull+pip install+systemctl restart+curl healthz smoke test. | ✓ |
| set -e only + no branch check | Simpler error handling; skips main-branch guard. Accepts some risk for simplicity. | |
| Add rollback-on-failure via git stash + revert | Captures pre-deploy hash; auto-reverts on any step failure. More moving parts. Overkill for v1.1. | |

**User's choice:** set -euo pipefail + branch check + atomic restart (Recommended)
**Notes:** Captured as D-20..D-25. D-20 shebang + strict flags; D-21 runs as trader with a narrow sudoers entry (`/etc/sudoers.d/trading-signals-deploy` grants passwordless sudo ONLY for `systemctl restart` on the two unit names); D-22 branch safety guard aborts if not on main; D-23 locks the 8-step sequence (branch check → git fetch → git pull --ff-only → pip upgrade → pip install → systemctl restart → curl smoke test → success echo); D-24 idempotent on no-op re-run (SC-3 verification — second run must exit 0 with "Already up to date"); D-25 explicitly defers auto-rollback to v1.2 (user picked fail-loud over auto-recovery). Phase 11 plan extends Phase 10's SETUP-DEPLOY-KEY.md (or companion SETUP-DROPLET.md) to include systemd install + sudoers entry setup.

---

## Claude's Discretion

- Exact FastAPI/uvicorn/httpx pin versions — planner picks at execution time via Context7 or latest-stable release (baseline `fastapi==0.115.5`, `uvicorn[standard]==0.34.0`, `httpx==0.28.1`).
- Test strategy — recommend FastAPI `TestClient` (in-process, httpx-based) for endpoint tests; no uvicorn-spawning integration test in Phase 11.
- deploy.sh log format — `[deploy]` prefix, human-readable, ERROR prefix on failures.
- SETUP doc consolidation — extend Phase 10's SETUP-DEPLOY-KEY.md to cover all droplet setup vs. companion SETUP-DROPLET.md. Planner picks.

## Deferred Ideas

- Automatic rollback on deploy failure (v1.2 candidate)
- State-read caching in /healthz (v1.2 if QPS grows)
- Real-process uvicorn integration test (Phase 16 hardening)
- Multi-worker support (v1.2, requires thread-safe state cache)
- `/metrics` endpoint for Prometheus-style observability (v1.2+)
- Separate web venv (v2.0 if deps conflict)
