# Phase 11: Web Skeleton — FastAPI + uvicorn + systemd — Context

**Gathered:** 2026-04-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Stand up a FastAPI app on the droplet as a systemd unit, serving `GET /healthz` on `localhost:8000` via uvicorn, with an idempotent `deploy.sh`. This is scaffolding — after Phase 11 the web process survives reboots and deploys cleanly, but it's only reachable from `localhost` and has no HTTPS, no auth, no dashboard, no mutations.

**Layer in later phases:**
- **Phase 12** → nginx reverse-proxy + Let's Encrypt for HTTPS on `signals.<owned-domain>.com`
- **Phase 13** → shared-secret auth middleware + `GET /` (dashboard) + `GET /api/state` (JSON)
- **Phase 14** → `POST /trades/open|close|modify` + HTMX forms
- **Phase 15** → live calculator + sentinels

Phase 11 locks the layout pattern all subsequent web phases extend.

**Parallelizable with Phase 10** — files touched are disjoint (Phase 10 edits `state_manager.py`, `main.py`, `notifier.py`, `.github/workflows/`; Phase 11 creates new `web/` directory + new `deploy.sh` + new systemd unit files).

</domain>

<decisions>
## Implementation Decisions

### Area 1 — FastAPI app layout + structure

- **D-01: New `web/` directory at repo root.** Keeps web code visually separated from the v1.0 signal code (`signal_engine.py`, `sizing_engine.py`, `state_manager.py`, `notifier.py`, `dashboard.py`, `main.py`). Matches the "many root-level modules" CLAUDE.md flat convention while isolating the new FastAPI surface.

- **D-02: `web/app.py` exposes a `create_app() -> FastAPI` factory + a module-level `app = create_app()`.** Factory pattern enables test isolation (each test gets a fresh app instance with different config if needed). Module-level `app` is what uvicorn references on startup: `uvicorn web.app:app --host 127.0.0.1 --port 8000`.

- **D-03: Future-proof directory structure for Phases 13-15.**
  - `web/app.py` — `create_app()` factory assembles middleware + routers
  - `web/routes/` — one module per route group (`healthz.py` in Phase 11; `state.py`, `trades.py`, `dashboard.py` added in later phases)
  - `web/middleware/` — auth, logging (added Phase 13)
  - `web/__init__.py` — empty or exports `app` for convenience
  - `web/routes/__init__.py` — exports route registration functions
  - This structure is established in Phase 11 even though only `healthz.py` is populated. Phase 13+ fill in the others.

- **D-04: Shared `.venv` with the existing trading-signals service.** One venv at `/home/trader/trading-signals/.venv`, one `requirements.txt`. Both systemd units point to the same `.venv/bin/python` in their ExecStart. Rationale: web and signal code share `state_manager` (both import from it); separate venvs would require duplicating those deps and create subtle version-skew risks. One venv is simpler and safer for a single-operator app.

- **D-05: Add `fastapi`, `uvicorn[standard]`, `httpx` to `requirements.txt` with exact pinned versions.** `fastapi` and `uvicorn[standard]` are runtime deps (uvicorn's `[standard]` extras include uvloop + httptools for perf + auto-reload support we won't use in prod). `httpx` is a test dep for Phase 11 integration tests (FastAPI's TestClient uses it under the hood). Planner picks exact pins — recommend latest stable at planning time, verified via Context7. Current Phase 11 baseline (late April 2026): `fastapi==0.115.5`, `uvicorn[standard]==0.34.0`, `httpx==0.28.1`, but planner should confirm these are current at execution time.

### Area 2 — systemd unit config

- **D-06: New unit file `/etc/systemd/system/trading-signals-web.service`.** Separate from the existing `trading-signals.service` (signal loop). Each unit has a single responsibility; restarting the web process doesn't disturb the daily signal run and vice versa.

- **D-07: User=trader, Group=trader** — same OS user as the signal loop. Single user simplifies file ownership on `state.json`, log access, and deploy.sh invocation. A dedicated web user would be more isolated but overkill for a single-operator app.

- **D-08: Restart=on-failure, RestartSec=10s.** If the web process exits non-zero (crash, unhandled exception), systemd restarts it after 10 seconds. Exit 0 (clean shutdown during deploy) is NOT restarted — `deploy.sh` explicitly restarts via `systemctl restart`.

- **D-09: After=network.target, Wants=trading-signals.service (SOFT dep).**
  - `After=network.target` — don't start until the network stack is up (so uvicorn's `.bind(127.0.0.1:8000)` doesn't race)
  - `Wants=trading-signals.service` — soft dependency. Web unit starts alongside the signal unit on boot, but web does NOT fail if signal unit is down (useful scenario: signal unit is being debugged; operator still wants to view historical state via `/api/state` in Phase 13).
  - Explicitly NOT `Requires=` — that would be a hard dep that cascades failure.

- **D-10: Hardening directives matching v1.0 Phase 7 pattern:**
  ```ini
  NoNewPrivileges=true
  PrivateTmp=true
  ProtectSystem=strict
  ReadWritePaths=/home/trader/trading-signals
  ProtectHome=read-only
  ```
  `ReadWritePaths` scopes writes to the repo dir only — uvicorn can't write outside it.

- **D-11: ExecStart invokes uvicorn bound to `127.0.0.1:8000`, workers=1, log-level=info.**
  ```ini
  ExecStart=/home/trader/trading-signals/.venv/bin/uvicorn web.app:app \
            --host 127.0.0.1 \
            --port 8000 \
            --workers 1 \
            --log-level info
  WorkingDirectory=/home/trader/trading-signals
  EnvironmentFile=/home/trader/trading-signals/.env
  ```
  - `--host 127.0.0.1` — NEVER `0.0.0.0`. External access goes through nginx in Phase 12. Verified by Phase 11 SC-4: `ss -tlnp | grep 8000` shows `127.0.0.1:8000` only.
  - `--workers 1` — preserves the v1.0 `_LAST_LOADED_STATE` single-threaded assumption (Phase 8 D-07). Multi-worker support is a v1.2 candidate.

- **D-12: Logs to journald.** StandardOutput=journal + StandardError=journal (systemd defaults but worth being explicit). Operator reads via `journalctl -u trading-signals-web -f`. FastAPI's default access log goes to stdout → journald. No custom log file.

### Area 3 — `/healthz` response shape + degraded-state behavior

- **D-13: Response shape is a fixed JSON schema.**
  ```json
  {
    "status": "ok",
    "last_run": "2026-04-24T08:00:15+08:00",
    "stale": false
  }
  ```
  `status` is always the string `"ok"` when returned with HTTP 200 (see D-14). `last_run` is ISO-format string with AWST offset, or `null` if state.json is missing (first-run) or corrupt. `stale` is boolean.

- **D-14: Always HTTP 200 if the FastAPI process is alive.** Process-liveness is the contract. State-pipeline health (is the signal loop running? is state fresh?) is reported via the `stale` flag in the body, not the HTTP status code. Rationale: external monitors (UptimeRobot, Healthchecks.io) use HTTP status for uptime; we want "web process up" tracked separately from "signal pipeline healthy".

- **D-15: `last_run` derivation.** Read state.json on each request via `state_manager.load_state()`. Extract `state.get('last_run')` — already an ISO string in the existing schema. If state.json doesn't exist, `load_state` returns a fresh state with `last_run=None` → endpoint returns `"last_run": null`.

- **D-16: `stale` flag is `True` when `last_run` is older than 2 days** (reuses Phase 8 ERR-05 / SC-2 threshold; if Phase 8 semantics shift to holiday-aware in v1.2, update here too). Computed against the FastAPI process's `datetime.now(AWST)`. If `last_run` is `None`, `stale` is `False` (no point flagging "stale" when the pipeline has never run).

- **D-17: `/healthz` is exempt from auth.** WEB-07 already locks this. External monitors need to hit it unauthenticated. Phase 13 auth middleware must explicitly skip `/healthz` (first middleware declaration OR route-level exemption — planner picks).

- **D-18: State read is NOT cached.** Each `/healthz` request calls `load_state()` fresh. State.json is small (< 50 KB typical); reads are O(ms). Caching can be added later if `/healthz` QPS grows (monitors usually poll every 60-300s — no perf concern).

- **D-19: Error handling inside `/healthz`.** If `load_state()` raises (should be impossible — it always returns a state per Phase 3 corrupt-recovery branch, but defensive), return `{"status": "ok", "last_run": null, "stale": false}` with 200. Log at WARN with `[Web]` prefix. The endpoint never returns non-200 unless the FastAPI process itself is crashed.

### Area 4 — `deploy.sh` safety posture

- **D-20: Shebang `#!/usr/bin/env bash` + `set -euo pipefail`.** Strict error handling — any command failure aborts; undefined variables are errors; pipe failures propagate. Script is at repo root: `/home/trader/trading-signals/deploy.sh`, committed to the repo.

- **D-21: Script runs as `trader`.** `systemctl restart` requires root; grant passwordless sudo ONLY for the two unit names via `/etc/sudoers.d/trading-signals-deploy`:
  ```
  trader ALL=(root) NOPASSWD: /bin/systemctl restart trading-signals, /bin/systemctl restart trading-signals-web
  ```
  Scoped precisely — trader can't restart other units, only these two. Phase 11 plan includes this sudoers entry in a new `SETUP-DROPLET.md` doc (or extends Phase 10's SETUP-DEPLOY-KEY.md to cover all droplet setup).

- **D-22: Branch safety check first.** Before anything else:
  ```bash
  BRANCH=$(git rev-parse --abbrev-ref HEAD)
  if [ "$BRANCH" != "main" ]; then
    echo "[deploy] ERROR: expected branch 'main', got '$BRANCH'. Aborting." >&2
    exit 1
  fi
  ```
  Prevents accidental deploys from a feature branch or detached HEAD.

- **D-23: Deploy sequence.**
  1. Branch check (D-22)
  2. `git fetch origin main`
  3. `git pull --ff-only origin main` (fail on non-fast-forward — forces resolution before deploy, no silent merges)
  4. `.venv/bin/pip install --upgrade pip` (silent on no-change)
  5. `.venv/bin/pip install -r requirements.txt` (idempotent — pip reports "Requirement already satisfied" on no-change)
  6. `sudo systemctl restart trading-signals trading-signals-web`
  7. Smoke test: `curl -fsS --max-time 5 http://127.0.0.1:8000/healthz > /dev/null` (fail-fast if endpoint is down or returns non-2xx)
  8. Echo success + print final commit short-hash

- **D-24: Idempotent on no-op re-run.** Second consecutive invocation:
  - Branch check passes
  - `git pull` prints "Already up to date."
  - `pip install` prints "Requirement already satisfied" for every line
  - `systemctl restart` always runs (returns 0 even if service is already healthy — "restart" is idempotent in systemd)
  - `curl /healthz` returns 200
  - Exit 0
  
  Phase 11 SC-3 verifies this: run twice, assert second run completes without error and the only git output is "Already up to date."

- **D-25: NO automatic rollback in Phase 11.** User selected "set -euo pipefail + branch check + atomic restart" over the rollback variant. If a deploy step fails (pip resolution, service restart, healthz smoke test), script exits non-zero and leaves state as-is. Operator inspects logs and intervenes. Captured as v1.2 candidate if deploy failures become common.

### Claude's Discretion

- **Exact FastAPI / uvicorn / httpx pin versions (D-05)** — planner picks at execution time via Context7 or latest stable release. Baseline suggestion: `fastapi==0.115.5`, `uvicorn[standard]==0.34.0`, `httpx==0.28.1`.
- **Test strategy for `/healthz`** — recommend FastAPI's built-in `TestClient` (in-process, synchronous, uses httpx under the hood) for endpoint tests. No uvicorn-spawning integration test in Phase 11; a real-process test can be added in Phase 16 hardening phase if desired.
- **deploy.sh logging format** — `[deploy]` prefix on human-readable lines, ERROR prefix for failures, echo to stdout (captured by whatever runs the script). Planner picks final wording.
- **Whether SETUP-DROPLET.md is a new doc or extends Phase 10's SETUP-DEPLOY-KEY.md** — Recommend extending Phase 10's doc to cover ALL droplet one-time setup (deploy key + systemd unit installation + sudoers entry). One doc for the operator to follow, not two.

### Folded Todos

None — `gsd-sdk query todo.match-phase 11` returned zero matches.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before implementing.**

### Phase spec + scope
- `.planning/ROADMAP.md` §Phase 11 — goal, 4 success criteria, dependency on Phase 10
- `.planning/REQUIREMENTS.md` — WEB-01 (FastAPI systemd unit), WEB-02 (uvicorn on localhost:8000), WEB-07 (`/healthz` contract), INFRA-04 (deploy.sh idempotent)
- `.planning/PROJECT.md` — v1.1 Current Milestone architecture + Key Decisions (FastAPI+uvicorn+nginx+Let's Encrypt stack; `workers=1`; shared-secret auth deferred to Phase 13)

### Prior-phase decisions that constrain Phase 11
- `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/10-CONTEXT.md`:
  - D-14 — deploy-key is an operator task; SETUP-DEPLOY-KEY.md exists (Phase 11 extends this doc for systemd + sudoers setup)
  - D-15 — web unit is READ-ONLY on state.json; signal loop is sole writer
  - D-07..D-12 — `_push_state_to_git()` helper in main.py (Phase 10 artifact); web process never calls this
- `.planning/milestones/v1.0-phases/07-scheduler-github-actions-deployment/07-CONTEXT.md` — systemd unit hardening pattern (NoNewPrivileges, ProtectSystem, ReadWritePaths). Reuse verbatim for trading-signals-web.service.
- `.planning/milestones/v1.0-phases/08-hardening-warning-carry-over-stale-banner-crash-email-config/08-CONTEXT.md`:
  - D-07 — `_LAST_LOADED_STATE` module-level cache in main.py. Preserved by `workers=1` (D-11 this phase); multi-worker would require thread-safe refactor (v1.2).
  - ERR-05 2-day staleness threshold — reused for `/healthz` `stale` flag (D-16 this phase).

### Source files touched by Phase 11
- `web/app.py` (new) — `create_app()` factory + module-level `app`
- `web/__init__.py` (new) — empty or exports `app`
- `web/routes/__init__.py` (new) — exports route registration
- `web/routes/healthz.py` (new) — `GET /healthz` handler
- `tests/test_web_healthz.py` (new) — FastAPI TestClient-based tests for `/healthz` contract
- `requirements.txt` — add `fastapi`, `uvicorn[standard]`, `httpx` with exact pins (D-05)
- `deploy.sh` (new, at repo root) — idempotent deploy script per D-20..D-25
- `systemd/trading-signals-web.service` (new, repo path) — systemd unit file; installed to `/etc/systemd/system/` by operator during Phase 11 setup
- `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md` (extended OR companion `SETUP-DROPLET.md`) — add systemd install + sudoers entry instructions
- `tests/test_signal_engine.py::TestDeterminism` — NO change needed; `web/` is a new top-level module outside the hex core (web is an adapter, like notifier and dashboard). Confirm `FORBIDDEN_MODULES_*` blocklists in test_signal_engine.py don't need updating for the new `web/` module.

### Architectural invariants (do not break)
- `CLAUDE.md` §Architecture — hex-lite boundary. `web/app.py` is an adapter module (like `notifier.py`, `dashboard.py`). Allowed to import `state_manager` (read-only per Phase 10 D-15). NOT allowed to import `signal_engine`, `sizing_engine`, `system_params` directly — those are pure-math; if web needs any constant, it goes through `state_manager` or `main` as intermediary.
- `CLAUDE.md` §Conventions — 2-space indent, single quotes, snake_case, `[Web]` log prefix for web-process logs (new prefix for this phase). `[Signal]/[State]/[Email]/[Sched]/[Fetch]` prefixes carry forward from v1.0 for the signal-loop process.
- Version pins in `requirements.txt` stay exact (no `>=`, no `~=`) — Phase 11 adds 3 new pinned deps per CLAUDE.md pinning convention.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets
- `state_manager.load_state()` — web's `/healthz` calls this directly to get `last_run`. Already handles missing file (returns fresh state) and corrupt file (recovers via backup + reinit per Phase 3).
- `state_manager.STATE_FILE` — canonical path constant. `/healthz` uses this so the web process reads the same state.json the signal loop writes.
- v1.0 Phase 7 systemd unit file for `trading-signals.service` — template for `trading-signals-web.service`. Clone the hardening directives, change User/Group if needed (staying with `trader`), swap ExecStart.
- `.env` / `.env.example` — `RESEND_API_KEY`, `SIGNALS_EMAIL_TO` are consumed by the signal loop; Phase 11 does NOT need these. New web-specific env vars (future: `WEB_AUTH_SECRET` in Phase 13) get added to the same `.env` file.

### Established patterns
- **Local imports inside adapter functions** — v1.0 Phase 6/8 pattern (`_send_email_never_crash`, `_render_dashboard_never_crash`) uses local imports to preserve hex boundary. Phase 11's `/healthz` handler should follow the same pattern: `from state_manager import load_state` inside the handler function, not at module top.
- **ISO datetime formatting** — v1.0 uses `datetime.isoformat()` with AWST tzinfo. `/healthz` returns the same format for `last_run`.
- **Test file naming** — v1.0 uses `tests/test_<module>.py`. Phase 11 adds `tests/test_web_healthz.py` (scoped to healthz) rather than one big `tests/test_web.py` — matches the per-concern pattern and scales as Phases 13-15 add more route tests.

### Integration points
- `web/app.py::create_app()` — calls `web.routes.healthz.register(app)` in Phase 11. Phase 13 adds `web.routes.state.register(app)` + middleware. Factory pattern decouples registration order.
- systemd unit `EnvironmentFile=/home/trader/trading-signals/.env` — same env file as the signal-loop unit. Both processes inherit `RESEND_API_KEY` etc. Web doesn't use them but doesn't cost anything.
- `deploy.sh` smoke test (`curl /healthz`) — verifies the FastAPI process is live post-restart. This is the first time `/healthz` becomes a production signal; later phases (monitoring, ops) lean on it.

</code_context>

<specifics>
## Specific Ideas

- **`web/` is a new top-level module, not `src/web/` or `app/web/`.** Matches v1.0's flat layout convention (main.py, state_manager.py, etc. all at repo root). Tests in `tests/test_web_*.py` — same tests dir as v1.0.

- **Factory pattern enables middleware layering in Phase 13.** `create_app()` will take e.g. `auth_required: bool` (or read from env) so tests can build an unauthenticated app. Phase 11 factory is minimal; Phase 13 extends.

- **`/healthz` body has `stale` in it, NOT in the HTTP status.** Monitors that want "stale → alert" can parse the JSON; monitors that only care about process uptime see 200 and are happy. Separation of concerns matches single-operator observability needs (no ops team watching dashboards).

- **sudoers scope is tight.** Two unit names, nothing else. If Phase 14+ adds more units (e.g., a periodic backup task), the sudoers entry is updated explicitly.

- **Phase 11 commits a systemd unit file to `systemd/trading-signals-web.service` IN the repo, not to `/etc/systemd/system/`.** Operator copies/symlinks it to `/etc/systemd/system/` during one-time setup (documented in SETUP-DROPLET.md). Keeping it in the repo means git tracks changes to the unit definition.

- **No uvicorn `--reload` in production.** `--reload` is dev-only; it watches files and restarts. Production restart is explicit via `systemctl`.

</specifics>

<deferred>
## Deferred Ideas

- **Automatic rollback in deploy.sh (D-25 deferred).** If pip install or smoke test fails, script could auto-revert git to the pre-deploy commit and restart units. v1.2 candidate if deploy failures become common. For v1.1, fail-loud and operator intervention is the chosen trade-off.

- **State-read caching in `/healthz`.** If QPS grows (internal monitoring hits every 10s), cache `load_state()` output with 5s TTL. Current v1.1 load (one external monitor every 60-300s) doesn't warrant.

- **Real-process uvicorn integration test.** Phase 11 uses FastAPI TestClient (in-process); a separate test that spawns uvicorn and hits `127.0.0.1:8000` via real HTTP catches a different class of bugs (startup failures, port-binding issues). Candidate for Phase 16 hardening.

- **Multi-worker support.** `workers=1` is locked per PROJECT.md v1.1 decision + Phase 8 D-07 `_LAST_LOADED_STATE` assumption. v1.2 could move to `workers=2+` if traffic grows, but that requires either file-lock coordination on state.json OR moving the cache to Redis/SQLite. Big enough work to warrant a dedicated phase.

- **Health metrics beyond `last_run`.** Future `/metrics` endpoint could expose Prometheus-formatted stats (signal compute time, Resend POST latency, state.json size). v1.2 candidate if observability needs grow.

- **Separate web venv.** Rejected per D-04 for v1.1. v2.0 candidate if web deps start conflicting with signal deps (unlikely but possible long-term).

### Reviewed Todos (not folded)
None — `gsd-sdk query todo.match-phase 11` returned zero matches.

</deferred>

---

*Phase: 11-web-skeleton-fastapi-uvicorn-systemd*
*Context gathered: 2026-04-24*
