# Roadmap: Trading Signals — v1.1 Interactive Trading Workstation

**Created:** 2026-04-24 (v1.1 roadmap)
**Milestone:** v1.1 Interactive Trading Workstation
**Start phase:** 10 (continuing from v1.0 which closed at Phase 9)
**Granularity:** fine
**Parallelization:** true
**Coverage:** 40/40 v1.1 requirements mapped (WEB 7, AUTH 12, TRADE 6, CALC 4, SENTINEL 3, BUG 1, INFRA 4, CHORE 3) — AUTH-04..AUTH-07 added 2026-04-27 with Phase 16.1 insertion; AUTH-08..AUTH-12 added 2026-04-29 via TOTP fold-in into Phase 16.1 (see `.planning/phases/16.1-phone-friendly-auth-ux-for-dashboard-access/16.1-CONTEXT.md` Areas E + F)

**Core Value (v1.1):** Transform the v1.0 email-only CLI into a hosted, interactive trade journal at `signals.<owned-domain>.com` — a single URL viewable from any device, POST-able for recording executed trades, with live stop-loss + pyramid guidance and position-vs-signal drift sentinels. Architecture locked: DO droplet runtime (systemd) + GitHub (source + state history via deploy-key push-back) + FastAPI + uvicorn + nginx + Let's Encrypt + HTMX (no React) + shared-secret header auth.

## Milestones

- [x] **v1.0 MVP — Mechanical Signal System** — Phases 1-9 (shipped 2026-04-24). See [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md).
- [ ] **v1.1 Interactive Trading Workstation** — Phases 10-16, plus inserted Phase 16.1 (in progress from 2026-04-24).

## Prerequisites (v1.1)

Must be resolved BEFORE the dependent phase can be planned:

| Prerequisite | Owner | Blocks |
|--------------|-------|--------|
| Operator purchases domain (e.g. `example.com`) pointing A-record at droplet IP | Operator | Phase 12+ (HTTPS / domain wiring onwards) |
| Droplet provisioned on DigitalOcean (Ubuntu LTS, systemd, public IP) | Operator | Phase 11+ (any systemd or nginx work) |
| Resend account has the new domain verified (SPF/DKIM/DMARC) with an `@<owned-domain>` sender | Operator | Phase 12 (INFRA-01 lands here) |

Phase 10 has **no** infrastructure dependencies — operator can start there immediately while the droplet + domain are being acquired.

## Phases

- [ ] **Phase 10: Foundation — v1.0 Cleanup & Deploy Key** — BUG-01 + ruff cleanup + droplet deploy key wiring + retire GHA cron; no domain needed yet
- [ ] **Phase 11: Web Skeleton — FastAPI + uvicorn + systemd** — FastAPI app serving `/healthz` behind uvicorn on localhost:8000 as a systemd unit, with an idempotent deploy.sh; no HTTPS yet
- [ ] **Phase 12: HTTPS + Domain Wiring** — nginx reverse proxy + Let's Encrypt cert + HSTS + Resend domain verification (depends on operator-purchased domain)
- [x] **Phase 13: Auth + Read Endpoints** — Shared-secret header auth, 401 handling with audit log, `GET /` (dashboard) and `GET /api/state` (JSON) behind auth (completed 2026-04-25)
- [ ] **Phase 14: Trade Journal — Mutation Endpoints** — `POST /trades/open|close|modify` with field validation, HTMX forms in the dashboard, sole-writer invariant preserved
- [ ] **Phase 15: Live Calculator + Sentinels** — Per-instrument stop + pyramid display, forward-looking peak-stop calculator, entry-target / add-target rendering, drift + reversal banners on dashboard and in email
- [ ] **Phase 16: Hardening + UAT Completion** — F1 full-chain integration test + Phase 6 HUMAN-UAT scenarios verified via hosted dashboard; final gate before milestone close

## Phase Details

### Phase 10: Foundation — v1.0 Cleanup & Deploy Key
**Goal**: Close the small v1.0 carry-over items (BUG-01 account-reset regression + ruff F401 cleanup) and prepare the droplet↔GitHub wiring for the web-layer phases, without requiring a domain yet.
**Depends on**: Nothing (can run immediately; parallelizable with Phase 11 because they touch disjoint files — Phase 10 touches `state_manager.py` + `notifier.py` + `.github/workflows/`, Phase 11 touches new files under `web/` + `systemd/`)
**Requirements**: BUG-01, CHORE-02, INFRA-02, INFRA-03
**Success Criteria** (what must be TRUE):
  1. `python main.py --reset` (CLI-flag path) and `--reset --initial-account X` (interactive-Q&A path) both leave `state['account'] == state['initial_account']`; a new regression test `test_reset_state_syncs_account_to_initial` asserts equality immediately after reset via both entry points
  2. `ruff check notifier.py` returns zero warnings (F401 cleanup complete); CI test `test_ruff_clean_notifier` asserts this so the warnings cannot reappear
  3. Droplet has a GitHub deploy key with write access to the repo; a nightly systemd timer runs `git add state.json && git commit && git push origin main` and the last 3 days' state commits are visible in the GitHub commit log authored by the deploy key
  4. `.github/workflows/daily.yml` is renamed to `daily.yml.disabled` (or equivalent no-op rename) and no cron job fires from GitHub for 2 consecutive weekdays — droplet systemd is the sole signal runner; no duplicate email arrives in the operator inbox
**Plans**: 4 plans
  - [ ] `10-01-PLAN.md` — BUG-01 defense-in-depth: `_handle_reset` one-line fix (D-01) + `state_manager.reset_state` signature extension (D-02) + TestHandleReset/TestResetState regression classes (D-03)
  - [ ] `10-02-PLAN.md` — CHORE-02 ruff F401 cleanup: remove 4 unused imports from `notifier.py` (D-04) + `test_ruff_clean_notifier` CI regression guard (D-05)
  - [ ] `10-03-PLAN.md` — INFRA-02 droplet deploy-key push: `_push_state_to_git` helper in `main.py` (D-07..D-12) + `run_daily_check` hook (D-08) + TestPushStateToGit/TestRunDailyCheckPushesState tests
  - [ ] `10-04-PLAN.md` — INFRA-03 GHA retirement: `git mv daily.yml → daily.yml.disabled` (D-16), update `TestGHAWorkflow.WORKFLOW_PATH` (D-18), author `SETUP-DEPLOY-KEY.md` (D-14), D-19 prose updates in CLAUDE.md + PROJECT.md
**Plans (wave structure)**: Wave 1 = [10-01, 10-02] parallel; Wave 2 = [10-03] after 10-01 (both append to `tests/test_main.py`); Wave 3 = [10-04] after 10-03 (SETUP-DEPLOY-KEY.md references `_push_state_to_git` helper)
**UI hint**: no

### Phase 11: Web Skeleton — FastAPI + uvicorn + systemd
**Goal**: Stand up a FastAPI app on the droplet as a systemd unit, serving `/healthz` on `localhost:8000` via uvicorn, with an idempotent deploy script. No HTTPS, no auth, no dashboard yet — just proof that the web process survives reboots and deploys cleanly.
**Depends on**: Phase 10 (needs the droplet-side deploy-key plumbing for deploy.sh to `git pull` cleanly)
**Requirements**: WEB-01, WEB-02, WEB-07, INFRA-04
**Success Criteria** (what must be TRUE):
  1. `systemctl status trading-signals-web` reports `active (running)` after a droplet reboot; the unit starts automatically without operator login
  2. `curl http://localhost:8000/healthz` on the droplet returns HTTP 200 with JSON body `{"status":"ok","last_run":"2026-04-24","stale":false}` (where `last_run` is a `YYYY-MM-DD` date string matching what `state.json` stores — `main.py:1042` writes `run_date_iso`; updated 2026-04-24 post-cross-AI review REVIEWS HIGH #1 — or `null` when state is missing); a pytest `TestHealthz` covers happy-path + missing-state-file degraded path
  3. `bash deploy.sh` run twice in a row on the droplet is idempotent — second run shows "Already up to date" from git, pip reports no changes, systemctl restarts the units without error; exit code 0 both times
  4. uvicorn runs with `workers=1` and binds only to `127.0.0.1:8000` (not `0.0.0.0`) — `ss -tlnp | grep 8000` shows `127.0.0.1:8000` only, so nothing is externally reachable before Phase 12 wires nginx
**Plans:** 4 plans
  - [ ] `11-01-PLAN.md` — WEB-07 Python scaffold: pin fastapi==0.136.1/uvicorn[standard]==0.46.0/httpx==0.28.1; create web/ package (__init__.py, app.py factory + module-level app, routes/__init__.py, routes/healthz.py); /healthz handler implements D-13..D-19 (200 always, JSON {status,last_run,stale} where last_run is a YYYY-MM-DD string or null, C-2 local state_manager import, D-19 never-crash); tests/test_web_healthz.py with 5 classes (TestHealthzHappyPath, TestHealthzMissingStatefile, TestHealthzStaleness, TestHealthzDegradedPath, TestWebHexBoundary AST guard)
  - [ ] `11-02-PLAN.md` — WEB-01/WEB-02 systemd unit: commit systemd/trading-signals-web.service to repo with locked body (D-06..D-12: User=trader, Wants=trading-signals.service soft dep, --host 127.0.0.1 + --workers 1, all 5 D-10 hardening directives, journald logs, EnvironmentFile optional prefix `-` per REVIEWS MEDIUM #5); tests/test_web_systemd_unit.py with 6 classes (configparser-based; critical test_execstart_does_not_bind_all_interfaces guards against 0.0.0.0; new test_environment_file_is_optional per MEDIUM #5; test_execstart_references_web_app_module_exactly per LOW #8)
  - [ ] `11-03-PLAN.md` — INFRA-04 deploy.sh: idempotent script at repo root (D-20 set -euo pipefail; D-22 branch-must-be-main check first; D-23 sequence: branch→fetch→pull --ff-only→pip install -r→TWO `sudo -n systemctl restart <unit>` calls (one per unit per REVIEWS HIGH #4)→curl /healthz retry loop (10 attempts @ 1s per REVIEWS HIGH #3)→commit echo; pip-upgrade line DROPPED per REVIEWS MEDIUM #7; D-25 no auto-rollback); tests/test_deploy_sh.py with 4 classes including 6 cross-step ordering checks + 3 post-REVIEWS negative assertions (no pip-upgrade, no combined-restart, no sleep-3 heuristic)
  - [ ] `11-04-PLAN.md` — Operator runbook: SETUP-DROPLET.md at repo root with 7 sections (install systemd unit, install sudoers entry scoped to TWO unit names per D-21 + passwordless-sudo verification step per REVIEWS HIGH #4, verify port binding SC-4, verify deploy.sh idempotency SC-3, verify boot persistence SC-1, troubleshooting, anti-pattern WARNINGS against NOPASSWD: ALL and 0.0.0.0; `.env` optional note per REVIEWS MEDIUM #5); tests/test_setup_droplet_doc.py with 9 classes including TestCrossArtifactDriftGuard (now with sudoers-form-matches-deploy.sh check per HIGH #4) and TestEnvFileOptional (per MEDIUM #5)
**Plans (wave structure)**: Wave 0 = [11-01] sequential (Python deps + scaffold + handler + tests); Wave 1 = [11-02, 11-03] parallel (disjoint files: systemd unit vs deploy.sh); Wave 2 = [11-04] after Wave 1 (drift guard reads both Plan 02 + Plan 03 artifacts)
**UI hint**: no

### Phase 12: HTTPS + Domain Wiring
**Goal**: Put `signals.<owned-domain>.com` on HTTPS via nginx reverse-proxy and Let's Encrypt, with HTTP→HTTPS redirect and HSTS, and switch Resend email sending to the verified operator-owned domain. After this phase the site is publicly reachable over HTTPS but still open (auth lands in Phase 13).
**Depends on**: Phase 11 (needs FastAPI on `localhost:8000` to reverse-proxy into). **Operator prerequisite:** domain purchased and A-record pointing at droplet IP; Resend domain verification (SPF/DKIM/DMARC) completed.
**Requirements**: WEB-03, WEB-04, INFRA-01
**Success Criteria** (what must be TRUE):
  1. `curl -sI https://signals.<owned-domain>.com/healthz` returns HTTP 200 with a valid Let's Encrypt cert chain (`openssl s_client -connect signals.<owned-domain>.com:443` shows Issuer `Let's Encrypt`); the certbot systemd timer is enabled and dry-run renewal succeeds
  2. `curl -sI http://signals.<owned-domain>.com/healthz` returns HTTP 301 redirect to the `https://` equivalent, and the HTTPS response header includes `Strict-Transport-Security: max-age=31536000; includeSubDomains`
  3. The daily signal email sent by the droplet-run notifier arrives from `signals@<owned-domain>` (driven by new `SIGNALS_EMAIL_FROM` env var read from droplet `.env`, not hardcoded); SPF/DKIM pass in Gmail's "show original" header view
  4. `SIGNALS_EMAIL_FROM` is a real env var honoured by `notifier.py` (with a regression test that patches the env var and asserts the Resend POST body's `from` field matches); missing env var fails the send with a clear log line, never silently falls back to `onboarding@resend.dev`
**Plans**: 4 plans
  - [ ] `12-01-PLAN.md` — WEB-03 + WEB-04 nginx config: committed `nginx/signals.conf` with 443-only server block (Mozilla Intermediate TLS, HSTS exact value no preload, rate-limit on /healthz, ACME carve-out, security headers at server scope) + `tests/test_nginx_signals_conf.py` (grep-style structural invariants, 8+ test classes)
  - [ ] `12-02-PLAN.md` — INFRA-01 notifier.py env-var refactor: remove `_EMAIL_FROM` constant (all 4 touch sites), read `SIGNALS_EMAIL_FROM` per-send in send_daily_email + send_crash_email, thread through `compose_email_body` (keyword-only) → `_render_footer_email` (3-arg signature), fail-loud missing path (log ERROR + SendStatus(ok=False, reason='missing_sender') — 2-field per research finding #2) + TestEmailFromEnvVar (3 tests) + module-level autouse fixture + regenerator pinning
  - [ ] `12-03-PLAN.md` — WEB-03 deploy.sh nginx reload hook: gated `if [ -f nginx/signals.conf ] && command -v nginx &>/dev/null` block running `sudo -n nginx -t` + `sudo -n systemctl reload nginx` AFTER retry-loop smoke test + TestNginxReloadHook (9 tests) — depends on Plan 01
  - [ ] `12-04-PLAN.md` — WEB-03/WEB-04/INFRA-01 operator runbook: `.planning/phases/12-https-domain-wiring/SETUP-HTTPS.md` with 10 sections (Prerequisites → Install → Copy/sed/symlink → Certbot → Verify → Timer → Env var → Sudoers → Troubleshooting → Rollback) + `tests/test_setup_https_doc.py` with TestCrossArtifactDriftGuard — depends on Plans 01, 02, 03
**Plans (wave structure)**: Wave 1 = [12-01, 12-02] parallel (disjoint files: nginx/ vs notifier.py); Wave 2 = [12-03] after 12-01 (deploy.sh references nginx/signals.conf path in gate); Wave 3 = [12-04] after 12-01+02+03 (cross-artifact drift guard reads all three)
**UI hint**: no

### Phase 13: Auth + Read Endpoints
**Goal**: Gate every non-healthz endpoint behind a shared-secret header, and expose the existing v1.0 dashboard (`GET /`) and state snapshot (`GET /api/state`) over HTTPS. After this phase the operator can securely browse the v1.0 dashboard from any device.
**Depends on**: Phase 12 (needs HTTPS so the shared secret isn't sent in plaintext)
**Requirements**: AUTH-01, AUTH-02, AUTH-03, WEB-05, WEB-06
**Success Criteria** (what must be TRUE):
  1. `curl -sI https://signals.<owned-domain>.com/` (no auth header) returns HTTP 401 with body `unauthorized` (plain text, no hint about the header name); `curl -H "X-Trading-Signals-Auth: <wrong>"` also returns 401 — only the correct `WEB_AUTH_SECRET` value yields 200
  2. `GET /` with correct auth returns the current `dashboard.html` bytes with `Content-Type: text/html`; if `state.json` mtime is newer than the last rendered dashboard, the endpoint regenerates before serving (verified by `test_get_root_regenerates_on_stale_dashboard`)
  3. `GET /api/state` with correct auth returns the full `state.json` with `Content-Type: application/json` and every top-level key present (`schema_version`, `account`, `last_run`, `positions`, `signals`, `trade_log`, `equity_history`, `warnings`, `contracts`)
  4. `GET /healthz` works with NO auth header (still 200) — liveness checks must never be gated; a regression test asserts `/healthz` is exempt from the auth dependency
  5. Every 401 response writes a journald log line at WARN level including source IP (`X-Forwarded-For` from nginx) and truncated User-Agent (first 120 chars); `journalctl -u trading-signals-web --since '5 min ago' | grep 'auth failure'` shows the expected entries after a test run
**Plans**: 5 plans
  - [ ] `13-01-PLAN.md` — Wave 0 scaffolding: retrofit Phase 11 healthz fixture for D-16 fail-closed, remove `dashboard` from FORBIDDEN_FOR_WEB (D-07), create skeleton test files + tests/conftest.py shared helpers, extend SETUP-DROPLET.md with "Configure auth secret" section (D-19)
  - [x] `13-02-PLAN.md` — Wave 1 factory amendment: web/app.py adds _read_auth_secret (D-16/D-17 fail-closed), passes docs_url=None + redoc_url=None + openapi_url=None (D-21 + research extension D-22), registers AuthMiddleware LAST (D-06); ships full AuthMiddleware body + route-module stubs so factory boots end-to-end + 8 TestSecretValidation/TestDocsDisabled tests
  - [ ] `13-03-PLAN.md` — Wave 2 auth middleware tests: tests/test_web_auth_middleware.py populated with 17 methods across 6 classes (TestAuthRequired, TestAuthPasses, TestExemption, TestUnauthorizedResponse, TestAuditLog, TestConstantTimeCompare) covering AUTH-01 + AUTH-02 + AUTH-03 + D-01..D-06 (XFF first-entry, UA truncation 120, %r escape, AST guard against ==)
  - [ ] `13-04-PLAN.md` — Wave 2 state route: web/routes/state.py replaces stub with D-12 strip + D-13 Cache-Control: no-store + D-14 trust load_state + D-15 compact JSON; tests/test_web_state.py populated with 7 TestStateResponse methods covering WEB-06
  - [ ] `13-05-PLAN.md` — Wave 2 dashboard route: web/routes/dashboard.py replaces stub with D-07 mtime-staleness regen + D-09 disk path + D-10 never-crash (WARN log + serve stale on render exception; 503 first-run) + D-11 concurrency posture; tests/test_web_dashboard.py populated with 12 methods across TestDashboardResponse/TestStaleness/TestRenderFailure/TestFirstRun covering WEB-05
**Plans (wave structure)**: Wave 0 = [13-01] scaffolding-only; Wave 1 = [13-02] factory amendment (also lays down full AuthMiddleware + route stubs to satisfy D-22 /openapi.json 401-without-auth contract); Wave 2 = [13-03, 13-04, 13-05] parallel — disjoint files (auth middleware tests vs state route+tests vs dashboard route+tests)
**UI hint**: yes

### Phase 14: Trade Journal — Mutation Endpoints
**Goal**: Let the operator record executed trades through the web UI — open, close, and modify positions via HTMX forms that POST to validated JSON endpoints. Every mutation flows through `state_manager.save_state()` so the v1.0 sole-writer invariant for warnings holds.
**Depends on**: Phase 13 (needs auth + HTMX-able dashboard already served)
**Requirements**: TRADE-01, TRADE-02, TRADE-03, TRADE-04, TRADE-05, TRADE-06
**Success Criteria** (what must be TRUE):
  1. `POST /trades/open` with `{instrument: "SPI200", direction: "LONG", entry_price: 7800.5, contracts: 2}` appends a new position to `state.positions`, saves via `state_manager.save_state()`, and returns an HTMX partial re-rendering the positions table with the new row
  2. `POST /trades/open` with any invalid field (e.g. `instrument: "BTC"`, `contracts: 0`, `entry_price: -1`, `entry_price: NaN`) returns HTTP 400 with a JSON body listing each offending field and reason; no mutation to `state.json` occurs
  3. `POST /trades/close` records a closed trade via `state_manager.record_trade()` — `trade_log` grows by one entry, `state.account` updates by realised P&L (respecting the Phase 2/3 D-13 half-on-close cost-split), and `state.positions` loses the closed position; a regression test compares `account_after - account_before` to manual P&L math for both LONG and SHORT exits
  4. `POST /trades/modify` can update a position's trailing stop or contract count independently (either field optional); attempts to set `new_contracts: 0` or a non-finite `new_stop` return 400
  5. Dashboard `GET /` includes three HTMX forms (open / close / modify) that POST to their endpoints and swap in the server-returned partial without a full page reload; a selenium-lite or httpx-driven test asserts the HTMX response includes a `hx-swap`-compatible fragment, not a full `<html>` document
  6. No mutation endpoint writes to `state['warnings']` directly — a regression test AST-walks the web module's handlers and asserts none of them reference `state['warnings'] =` or `.append` on that list (v1.0 sole-writer invariant preserved; only the signal orchestrator touches warnings)
**Plans**: 5 plans
  - [x] `14-01-PLAN.md` — Wave 0 scaffolding: hex-boundary update (sizing_engine + system_params promoted out of FORBIDDEN_FOR_WEB, mirroring Phase 13 D-07's dashboard promotion); v2-schema fixture state_v2_no_manual_stop.json; skeleton test classes in tests/test_web_trades.py + 2 in tests/test_state_manager.py + 1 in tests/test_sizing_engine.py + 3 in tests/test_dashboard.py; htmx_headers + client_with_state_v3 fixtures in conftest.py
  - [x] `14-02-PLAN.md` — Wave 1 state_manager: fcntl.LOCK_EX advisory lock around _atomic_write (D-13 cross-process safety); NEW mutate_state(mutator, path) helper holds lock across full read-modify-write (REVIEWS HIGH #1; T-14-01 fully mitigated); _migrate_v2_to_v3 backfilling manual_stop=None on Position dicts (D-09); STATE_SCHEMA_VERSION 2→3; Position TypedDict gains manual_stop: float | None; main.py daily loop migrated 3 save_state sites to mutate_state (W3 invariant preserved); TestFcntlLock (4) + TestMutateState (5) + TestSchemaMigrationV2ToV3 (6) = 15 new tests
  - [ ] `14-03-PLAN.md` — Wave 1 sizing_engine: get_trailing_stop honors position.manual_stop (D-09 precedence after NaN guard, before LONG/SHORT switch); defensive .get() handles pre-migration positions; TestManualStopOverride (5 tests including NaN passthrough and missing-key)
  - [ ] `14-04-PLAN.md` — Wave 2 web/routes/trades.py (NEW): three POST endpoints (open/close/modify) + three GET HTMX support endpoints (close-form/modify-form/cancel-row); Pydantic v2 models with Literal enums + Field constraints + model_validator (D-04 + D-12 model_fields_set); 422→400 remap exception handler (D-04); D-05 inline gross_pnl anti-pitfall in close handler; web/app.py registers trades_route + handler; tests/test_web_trades.py 13 classes ~50 tests including TestSoleWriterInvariant AST guard (TRADE-06)
  - [ ] `14-05-PLAN.md` — Wave 2 dashboard.py: HTMX 1.9.12 SRI vendor pin; _render_positions_table extends with Actions column + per-row IDs + manual badge (UI-SPEC §Decision 1, 2, 6); _render_open_form helper (UI-SPEC §Decision 7); _compute_trail_stop_display lockstep parity with sizing_engine.get_trailing_stop manual_stop precedence; inline handleTradesError JS (UI-SPEC §Decision 4); _INLINE_CSS extended with Phase 14 component rules; #confirmation-banner slot; TestRenderDashboardHTMXVendorPin + TestRenderPositionsTableHTMXForm + TestRenderManualStopBadge (17 tests)
**Plans (wave structure)**: Wave 0 = [14-01] sequential (test-infra scaffolding + hex-boundary update); Wave 1 = [14-02, 14-03] parallel (disjoint v1.0 hex modules: state_manager.py vs sizing_engine.py); Wave 2 = [14-04, 14-05] parallel (disjoint files: web/routes/trades.py + web/app.py vs dashboard.py)
**UI hint**: yes

### Phase 15: Live Calculator + Sentinels
**Goal**: Turn the dashboard from a passive log into an active decision-support tool — surface the current trailing stop, next pyramid-add price, forward-looking peak stop, and entry target from `sizing_engine`; flag drift when `state.positions` disagrees with today's signal on dashboard AND in the daily email.
**Depends on**: Phase 14 (needs mutations working so the operator's real positions drive the calculator display)
**Requirements**: CALC-01, CALC-02, CALC-03, CALC-04, SENTINEL-01, SENTINEL-02, SENTINEL-03
**Success Criteria** (what must be TRUE):
  1. Per-instrument row on the dashboard shows (when a position is held): current trailing stop price, distance-to-stop in absolute $ and %, and the next pyramid trigger price — all derived by importing `sizing_engine` calculators from the web layer (no re-implementation; pure-math hex boundary preserved)
  2. When `signal == LONG` and `positions[instrument]` is empty, the row shows an "entry target" block with: next-close threshold (the signal's entry price), suggested contracts (from `calc_position_size`), and the initial trailing stop — matching what the email ACTION REQUIRED block says
  3. When a position is open, the row shows a "forward-looking" line: "at current bar high Z, stop would rise to W" computed by evaluating `get_trailing_stop` against today's live high (not yesterday's); a test fixture proves the forward-stop math matches `sizing_engine.get_trailing_stop` bit-for-bit
  4. Pyramid section shows "level N active; next add at price P (+Y×ATR_entry)" and "new stop after add: S" — values equal what `check_pyramid` + `get_trailing_stop` would return on the next bar
  5. When `positions[instrument]` has an open LONG but today's signal is FLAT (or position holds LONG while signal is SHORT, or any mismatch), an amber "drift" banner on the dashboard names the instrument and the direction of mismatch; a mismatch to the *opposite* direction (LONG↔SHORT) uses a red "reversal" banner instead of amber drift
  6. The same drift/reversal banner surfaces in the daily email as a top-tier critical banner (reusing Phase 8's `_has_critical_banner` classifier via a new source key `'drift'`); a regression test injects a drifted state and asserts the email body contains the banner text and the subject carries the `[!]` critical prefix
**Plans**: 8 plans
  - [ ] `15-01-PLAN.md` — Wave 0 gate: update FORBIDDEN_MODULES_DASHBOARD to drop sizing_engine (Pitfall 2 prevention) + skeleton test classes across 6 test files (TestDetectDrift, TestClearWarningsBySource, TestRenderCalculatorRow, TestRenderDriftBanner, TestForwardStopFragment, TestSideBySideStopDisplay, TestDriftBanner, TestBannerStackOrder, TestDriftWarningLifecycle)
  - [ ] `15-02-PLAN.md` — Wave 1 sizing_engine: DriftEvent frozen+slots dataclass + detect_drift(positions, signals) -> list[DriftEvent] pure-math (D-01, D-04, D-14); 12 TestDetectDrift method bodies populated and passing
  - [ ] `15-03-PLAN.md` — Wave 1 state_manager: clear_warnings_by_source(state, source) helper (D-02); 5 TestClearWarningsBySource methods populated; sole-writer invariant preserved
  - [ ] `15-04-PLAN.md` — Wave 2 main.py: drift recompute block (clear -> detect -> append_warning loop) inserted in run_daily_check between pending_warnings flush and last_run assignment; W3 invariant preserved (no new mutate_state call); [Sched] log line per event; TestDriftWarningLifecycle (W3 mandatory)
  - [ ] `15-05-PLAN.md` — Wave 2 dashboard.py: _render_calc_row + _render_entry_target_row + _render_drift_banner helpers (CALC-01/02/04 + SENTINEL-01/02); side-by-side trail-stop cell when manual_stop set (D-10); _INLINE_CSS extended with Phase 15 rules block; sizing_engine LOCAL imports (C-2); 14 render tests
  - [ ] `15-06-PLAN.md` — Wave 3 web: forward-stop fragment branch in web/routes/dashboard.py (CALC-03, D-05/D-06/D-07); drift recompute block in each web/routes/trades.py mutator (D-02); 12 web tests including bit-identical parity test
  - [ ] `15-07-PLAN.md` — Wave 3 notifier: _has_critical_banner extension with source='drift' branch (D-03); drift banner inline-CSS block in _render_header_email between corrupt-reset and hero card (D-12, D-13); 10 email banner tests
  - [ ] `15-08-PLAN.md` — Wave 4 phase gate: enrich tests/fixtures/dashboard/sample_state.json with calc-row + side-by-side + drift fixtures; regenerate dashboard + notifier goldens (idempotent); two operator checkpoints (forward-look UX in browser + drift banner in real Gmail)
**Plans (wave structure)**: Wave 0 = [15-01] gate (FORBIDDEN_MODULES_DASHBOARD update + 9 skeleton classes); Wave 1 = [15-02, 15-03] parallel (disjoint v1.0 hex modules: sizing_engine.py vs state_manager.py); Wave 2 = [15-04, 15-05] parallel (disjoint: main.py vs dashboard.py); Wave 3 = [15-06, 15-07] parallel (disjoint: web/routes/* vs notifier.py); Wave 4 = [15-08] sequential (golden fixtures + operator checkpoints)
**UI hint**: yes

### Phase 16: Hardening + UAT Completion
**Goal**: Close the v1.0 tech-debt items that were deferred, and complete the Phase 6 HUMAN-UAT scenarios that are now verifiable via the hosted dashboard. Final gate before v1.1 milestone archive.
**Depends on**: Phase 15 (HUMAN-UAT scenarios need the full dashboard + email flow working; F1 test needs the full signal→dashboard→email chain)
**Requirements**: CHORE-01, CHORE-03
**Success Criteria** (what must be TRUE):
  1. A single `tests/test_integration_f1.py::test_full_chain_fetch_to_email` exercises yfinance fetch (mocked at the `requests.get` boundary only, not at `data_fetcher.fetch_ohlcv`) → `run_daily_check` → `state_manager.save_state` → `dashboard.render_dashboard` → `notifier.send_daily_email` (dispatch stubbed at `_post_to_resend`), and asserts that the resulting `last_email.html` contains the expected signal + positions + equity values; no internal composition is mocked
  2. The F1 integration test catches a deliberately-planted cross-module regression (e.g., rename `get_signal` → `compute_signal` without updating `main.py`) — a meta-test confirms F1 red-lights on that planted break when run locally before being reverted
  3. Phase 6 `06-HUMAN-UAT.md` has its 3 pending scenarios marked `complete` with operator-recorded notes: (a) dashboard loads correctly on mobile via the hosted URL, (b) email renders correctly in real Gmail on mobile, (c) drift banner (from Phase 15) renders correctly in both dashboard and email on at least one real weekday run
  4. `STATE.md §Deferred Items` no longer lists the three Phase 6 HUMAN-UAT items, the Phase 5 dashboard visual check, or the Phase 6 email rendering check — all moved to a Completed section with the operator's verification date
**Plans**: 5 plans
  - [ ] `16-01-PLAN.md` — Deploy Phases 13/14/15 to droplet (Wave 1; D-11 first task; operator-driven SSH + bash deploy.sh + smoke-check)
  - [ ] `16-02-PLAN.md` — F1 full-chain integration test (CHORE-01 SC-1 + SC-2; tests/test_integration_f1.py with test_full_chain_fetch_to_email + test_f1_catches_planted_regression)
  - [ ] `16-03-PLAN.md` — Create 16-HUMAN-UAT.md with 3 scenarios in D-10 5-field schema (CHORE-03; new file in Phase 16 dir, archived 06-HUMAN-UAT.md unmodified per D-09)
  - [ ] `16-04-PLAN.md` — STATE.md ## Completed Items section with 3 migrated rows linked to 16-HUMAN-UAT.md (CHORE-03 SC-4; D-14, D-15)
  - [ ] `16-05-PLAN.md` — Operator UAT verification gate (3 human-verify checkpoints — UAT-16-A mobile dashboard, UAT-16-B mobile Gmail, UAT-16-C drift banner real weekday; UAT-16-C may stay PARTIAL per D-17)
**Plans (wave structure)**: Wave 1 = [16-01, 16-02, 16-03] parallel (disjoint files: deploy is operator-side, F1 test creates tests/test_integration_f1.py, UAT scaffold creates 16-HUMAN-UAT.md); Wave 2 = [16-04] after 16-03 (STATE.md edits link into 16-HUMAN-UAT.md scenario anchors); Wave 3 = [16-05] after 16-01 + 16-03 (operator UAT needs deployed stack + UAT artifact in place)
**UI hint**: yes

## Phase Dependencies (build order)

```
Phase 10 ─┐
          │ (parallel with 11 on disjoint files)
Phase 11 ─┴─► Phase 12 ─► Phase 13 ─► Phase 14 ─► Phase 15 ─► Phase 16
```

**Parallelizable pairs** (from config `parallelization: true`):
- **Phase 10 and Phase 11 can run in parallel.** They touch disjoint files: Phase 10 modifies `state_manager.py` (BUG-01), `notifier.py` (CHORE-02 ruff), `.github/workflows/` (INFRA-03 rename); Phase 11 creates new files under `web/`, `systemd/`, and `deploy.sh`. The only shared touchpoint is `CLAUDE.md` / `.planning/` notes — resolve via non-overlapping sections or sequential commits at plan-check time.
- Phases 12–16 are strictly sequential — each needs the previous layer's capability (HTTPS → auth → mutations → calculator → UAT).

**Cut points (if time-boxed):**
- Phases 10 + 11 alone already retire the GHA duplicate-run risk and prove the droplet runtime works — a viable "beachhead" ship even if the domain is delayed.
- Phases 10–13 deliver a hosted read-only dashboard — the operator can browse v1.0 output from anywhere without mutations. Phases 14+ are the value-add.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 10. Foundation — v1.0 Cleanup & Deploy Key | v1.1 | 0/4 | Not started | - |
| 11. Web Skeleton — FastAPI + uvicorn + systemd | v1.1 | 4/4 | Complete (code); 4 operator-manual verifications pending on droplet | 2026-04-24 |
| 12. HTTPS + Domain Wiring | v1.1 | 0/4 | Not started | - |
| 13. Auth + Read Endpoints | v1.1 | 5/5 | Complete    | 2026-04-25 |
| 14. Trade Journal — Mutation Endpoints | v1.1 | 0/5 | Not started | - |
| 15. Live Calculator + Sentinels | v1.1 | 0/8 | Not started | - |
| 16. Hardening + UAT Completion | v1.1 | 0/5 | Not started | - |

Plan counts filled in by `/gsd-plan-phase <N>` as each phase is planned.

## Coverage Validation

- **Total v1.1 requirements:** 31 (WEB 7 + AUTH 3 + TRADE 6 + CALC 4 + SENTINEL 3 + BUG 1 + INFRA 4 + CHORE 3)
- **Mapped to phases:** 31/31
- **Orphans:** 0
- **Duplicates:** 0

### Coverage Map

| REQ-ID | Phase |
|--------|-------|
| BUG-01 | 10 |
| CHORE-02 | 10 |
| INFRA-02 | 10 |
| INFRA-03 | 10 |
| WEB-01 | 11 |
| WEB-02 | 11 |
| WEB-07 | 11 |
| INFRA-04 | 11 |
| WEB-03 | 12 |
| WEB-04 | 12 |
| INFRA-01 | 12 |
| AUTH-01 | 13 |
| AUTH-02 | 13 |
| AUTH-03 | 13 |
| WEB-05 | 13 |
| WEB-06 | 13 |
| TRADE-01 | 14 |
| TRADE-02 | 14 |
| TRADE-03 | 14 |
| TRADE-04 | 14 |
| TRADE-05 | 14 |
| TRADE-06 | 14 |
| CALC-01 | 15 |
| CALC-02 | 15 |
| CALC-03 | 15 |
| CALC-04 | 15 |
| SENTINEL-01 | 15 |
| SENTINEL-02 | 15 |
| SENTINEL-03 | 15 |
| CHORE-01 | 16 |
| CHORE-03 | 16 |

Per-phase counts: Phase 10 = 4, Phase 11 = 4, Phase 12 = 3, Phase 13 = 5, Phase 14 = 6, Phase 15 = 7, Phase 16 = 2. Total = 4+4+3+5+6+7+2 = **31** ✓

## Operator Decisions Baked In (v1.1)

| Decision | Reflected in |
|----------|--------------|
| DO droplet is runtime; GitHub is source + state history via deploy-key push-back | Phase 10 INFRA-02 + Phase 11 systemd unit + Phase 16 milestone close |
| FastAPI + uvicorn + nginx + Let's Encrypt on `signals.<owned-domain>.com` | Phases 11 + 12 success criteria |
| HTMX or vanilla JS (no React / SPA framework) | Phase 14 SC-5 (HTMX partial fragments, not full-page JSON swap) |
| Shared-secret header auth (not OAuth / sessions / cookies) | Phase 13 AUTH-01..03 |
| uvicorn `workers=1` — preserves v1.0 single-threaded `_LAST_LOADED_STATE` cache | Phase 11 SC-4; multi-worker deferred to v1.2+ per REQUIREMENTS.md §Future |
| Signal-only (no live trading) — carried from v1.0 | Phase 14 endpoints record hypothetical executed trades only; no broker integration |
| GHA cron retired once droplet systemd runs reliably | Phase 10 INFRA-03 + Phase 11 systemd unit |
| Domain + Resend verification are operator prerequisites, not code work | Prerequisites block above + Phase 12 entry gate |

## Carried-Forward Operator Decisions from v1.0

| Decision | Reflected in |
|----------|--------------|
| `n_contracts == 0` skips trade + warns (no `max(1,…)` floor) | Phase 14 TRADE-02 validation rejects `contracts < 1`; no silent floor |
| LONG→FLAT (and SHORT→FLAT) closes the open position | Phase 15 SENTINEL-01 amber-drift banner text matches this semantics |
| Trailing stops use intraday high/low (peak updates + hit detection) | Phase 15 CALC-03 forward-looking peak-stop math |
| Data-fetch errors (yfinance) log + exit rc=2, do NOT email | Unchanged — droplet systemd unit inherits the same behaviour |
| `_resolved_contracts` is runtime-only (underscore-prefix persistence rule) | Phase 14 TRADE-06 sole-writer invariant; `save_state` continues to strip underscore-prefix keys |

---
*Roadmap created: 2026-04-24 (v1.1 milestone kickoff)*
*Ready for: `/gsd-discuss-phase 10` (or parallel `/gsd-discuss-phase 11` once Phase 10 plans exist)*

### Phase 16.1: Phone-friendly auth UX for dashboard access (INSERTED 2026-04-27, URGENT)

**Goal**: Add an iOS-native authentication path to the dashboard so the operator can use `signals.<owned-domain>.com` from a real iPhone (Safari and Chrome) without installing a header-injection extension. Phase 13's `X-Trading-Signals-Auth` header gate stays in place and continues to work for `curl`, scripts, and Phase 14 HTMX trade-mutation forms — the new path is **additive**, not replacing. Mechanism (HTTP Basic Auth as v1.1.1 patch vs login form + cookie session as proper v1.2 UX vs Cloudflare Access vs magic link) chosen during `/gsd-discuss-phase 16.1` from the four candidates pre-documented in [.planning/todos/pending/2026-04-27-phone-friendly-auth-ux-for-dashboard-access.md](todos/pending/2026-04-27-phone-friendly-auth-ux-for-dashboard-access.md).

**Depends on**: Phase 13 (loosened from "Phase 16" per insertion-commit note: 16.1 only needs the existing `AuthMiddleware` from Phase 13 to extend; it does not need Phase 16's UAT-completion to ship). Can run in parallel with the natural weekday-gated wait for UAT-16-C closure.

**Requirements**: AUTH-04, AUTH-05, AUTH-06, AUTH-07, AUTH-08, AUTH-09, AUTH-10, AUTH-11, AUTH-12 (AUTH-08..AUTH-12 added 2026-04-29 via TOTP 2FA fold-in — see `.planning/phases/16.1-phone-friendly-auth-ux-for-dashboard-access/16.1-CONTEXT.md` Areas E + F)

**Success Criteria** (what must be TRUE):
  1. Visiting `https://signals.<owned-domain>.com/` from a real iPhone (Safari **and** Chrome, no extension installed) yields a usable rendered dashboard, not the plain-text `unauthorized` response. Verified by an operator-performed phone UAT scenario captured in `16.1-HUMAN-UAT.md` (mirrors the Phase 16 UAT pattern).
  2. The existing header path is preserved verbatim — `curl -H "X-Trading-Signals-Auth: <secret>" https://signals.<owned-domain>.com/` returns HTTP 200 + dashboard HTML; HTMX forms in `web/templates/dashboard.html` (which carry `hx-headers='{"X-Trading-Signals-Auth": "..."}'`) keep submitting trades successfully without modification. A regression test in `tests/test_web_auth.py` asserts both paths authenticate to 200 against a single endpoint.
  3. Auth strength is preserved — `WEB_AUTH_SECRET` stays in droplet `.env` only (no new database, no on-disk credential store); `hmac.compare_digest` stays on the comparison hot-path; a code-search test asserts no plaintext-comparison operator (`==`) is used against `WEB_AUTH_SECRET` anywhere in `web/`.
  4. `/healthz` stays exempt (per Phase 13 D-02 EXEMPT_PATHS) — `curl https://signals.<owned-domain>.com/healthz` returns 200 with no auth, regression test asserts. For any unauthenticated request that did NOT come through the new operator-UX path (raw `curl` without header, no cookie, no Basic Auth), the failure response is still `401 unauthorized` plain text — no body change, no header leak about the new path's existence.

**Plans:** 3 plans (regenerated 2026-04-29 per F-09 Option B; superseded prior 2 stale plans archived to `.archive/`)
  - [ ] `16.1-01-PLAN.md` — Cookie login + TOTP enrollment + TOTP verify + auth_store.py + middleware E-02 3-step sniff (E-01 Basic Auth removed, E-02, E-03, E-04, AUTH-04..09, AUTH-12)
  - [ ] `16.1-02-PLAN.md` — Trusted-device cookie (30-day) + /devices revocation page + per-device label (E-05, E-06, AUTH-09 trust-skip + AUTH-10) — depends on 16.1-01
  - [ ] `16.1-03-PLAN.md` — Magic-link reset (email via Resend, sha256-hashed tokens, 1h TTL) + rate limits (F-08) + OPERATOR_RECOVERY_EMAIL boot validation + 16.1-HUMAN-UAT.md (E-07, F-01..F-08, AUTH-11) — depends on 16.1-01
**Plans (wave structure)**: Wave 1 = [16.1-01] sequential (core auth path — middleware diff is shared state with downstream plans per .claude/LEARNINGS.md 2026-04-27 entry); Wave 2 = [16.1-02] after 16.1-01; Wave 3 = [16.1-03] after 16.1-01 (could parallelize with 16.1-02 since they touch disjoint route files, BUT both extend auth_store.py — sequential is safer and gives operator UAT-each-layer per F-09).

**UI hint**: yes — login form, TOTP enrollment page (QR code), TOTP verify page (6-digit input + trust-device checkbox), `/devices` management page, magic-link reset confirmation pages. UI design contract in `16.1-UI-SPEC.md` PRE-DATES TOTP fold-in and may need a supplementary section per `/gsd-ui-phase 16.1` re-run.
