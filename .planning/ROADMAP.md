# Roadmap: Trading Signals

**Production:** `https://signals.mwiriadi.me` (DigitalOcean droplet, systemd, nginx + Let's Encrypt, daily 08:00 Sydney signal cycle).

## Milestones

- ✅ **v1.0 MVP — Mechanical Signal System** — Phases 1–9 (shipped 2026-04-24). See [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md).
- ✅ **v1.1 Interactive Trading Workstation** — Phases 10–16 + 16.1 (shipped 2026-04-30). See [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md).
- ✅ **v1.2 Trader-Grade Transparency & Validation** — Phases 17, 19, 20, 22, 23, 24, 25, 26, 27 (shipped 2026-05-10). See [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md).
- 🟢 **v1.3 Multi-Tenant Friends & Family** — Phases 28–40 (planning, started 2026-05-10).
- 🔵 **v1.4 Domain Models** — Phase 41 (planned).

---

## v1.3 Multi-Tenant Friends & Family

**Goal:** Open the system to invite-only friends-and-family with full per-user state isolation, per-user 08:00 Sydney emails, news context, and a guided UI — while closing v1.2 deferred UAT debt and retroactively wrapping post-v1.2 polish commits as v1.2.1.

**Granularity:** fine.
**Phase numbering:** continues from v1.2 (last phase 27). v1.3 starts at **Phase 28**.
**Coverage:** 30/30 v1.3 requirements mapped, 0 orphans, 0 duplicates.

### Hard Constraints (inherited; non-negotiable)

- Signal-only — no live trading. F&F inherit the same constraint.
- File-based persistence — no DB.
- HTMX only — no SPA.
- Resend HTTPS API only — no SMTP.
- Hex-lite AST guard preserved (`signal_engine`, `sizing_engine`, `system_params`, `backtest/` stay pure-math).
- Atomic-write contract on `state.json` preserved.
- Production source files capped at 500 LOC (D-09).

### Cross-Phase Quality Gates

These gates run on every phase that touches per-user data, not just at milestone close:

1. **Privacy gate — `TestTenantIsolation` test class** (introduced in Phase 36, applies to Phases 36–40):
   - Fixture user holding 5 paper trades produces zero `(entry_price|n_contracts|"direction":\s*"(LONG|SHORT)")` matches in admin user-list HTML, log lines, crash-email body, or any other user's served pages.
   - `PublicUserSummary` Pydantic model + `RedactStateFilter` enforce redaction.
   - Every entity-ID route has paired `test_<route>_returns_404_for_other_users_entity`.
2. **AST hex boundary** — extended in Phase 30 to block any v1.3-introduced I/O module (`news_fetcher`, `news_filter`, `auth_store` extensions, `web/*`) from leaking into pure-math hex.
3. **Atomic-write + per-user `flock`** — Phase 36 onwards; `mutate_user_state` composes with the existing `mutate_state` chokepoint, never forks it.
4. **`state/users/` gitignore + CI gate** — Phase 33 onwards; `git ls-files | grep '^state/users/'` returns nothing.

### Phases

- [ ] **Phase 28: v1.2 UAT Closure** — verify 8 deferred operator-facing v1.2 UAT scenarios end-to-end; produce `VERIFICATION.md`.
- [ ] **Phase 29: v1.2.1 Retroactive Patch Wrap + Validation Sweep** — formalise 5 ad-hoc post-ship polish commits; backfill Nyquist `VALIDATION.md` + `SECURITY.md` for v1.2 phases 17/19/20/22/23/24/25/26; fix `.planning/backtests` CWD-relative path.
- [x] **Phase 30: File-Size Pre-Split** — behaviour-preserving splits of pre-existing 500-LOC violators (`web/routes/trades.py` 746, `dashboard.py` 644, `totp.py` 614, `login.py` 608, `paper_trades.py` 493) before any per-user `user_id` injection; extend AST hex blocklist for v1.3 I/O peers.
- [x] **Phase 31: Core Module Split** — behaviour-preserving split of `state_manager.py` (1,293 LOC) into `state_manager/` package and `sizing_engine.py` (820 LOC) into `sizing_engine/` package before any per-user `user_id` injection.
- [ ] **Phase 32: Dashboard Legacy Retirement** — confirm `dashboard_renderer/` as sole canonical renderer; retire `dashboard_legacy/`; thin `dashboard.py` to a route-through shim; eliminate the three-surface split that caused the layout-drift issue.
- [x] **Phase 33: Schema Migration v11→v12 + Admin Namespace + Backup + Gitignore** — atomic build-then-validate-then-save migration; auto-backup `state.json.v11-backup-<ts>`; round-trip fixtures; `state/users/` gitignore + CI gate + off-droplet (rclone-to-B2) daily backup with 48h-stale alert.
- [x] **Phase 34: User Registry + Invite-Token Storage** — `auth_store.users[]` + `pending_invites[]` co-located in `auth.json`; `secrets.token_urlsafe(32)` mint, sha256 hash store, `hmac.compare_digest` verify, 7-day expiry, single-use guaranteed by `flock` on consume.
- [ ] **Phase 35: Cookie + `Depends(current_user)` + Sub-Router Admin Gate** — cookie payload extends to `{"uid": ...}`; `web/dependencies.py` introduces `current_user_id` and `require_admin`; `APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])` sub-router locked Day 1; startup invariant test walks `app.routes`. Admin remains the only user — observable behaviour identical at this phase boundary.
- [ ] **Phase 36: Per-Route User-ID Scoping + Privacy Boundary + Per-User Flock** — centralized `load_X_for_user()` loaders; `PublicUserSummary` + `RedactStateFilter`; `TestTenantIsolation` quality gate introduced; per-user `fcntl.flock`; pyramid/exit semantics shift to fan-out.
- [ ] **Phase 37: Per-User Email Fan-Out + Admin Invite/Disable Routes + Invite-Acceptance Flow** — `per_user_fanout.py` orchestrator seam; per-user crash boundary; admin end-of-cycle summary; `/healthz/last-cycle`; `asyncio.Semaphore(2)` Resend throttle; RFC 8058 `List-Unsubscribe`; per-user enable/disable + pause-until.
- [ ] **Phase 38: News Integration** — `news_fetcher.py` (I/O peer) + `news_filter.py` (pure, AST-hex eligible); pre-0.2.55 + post-0.2.55 yfinance schemas normalised; word-boundary regex with multi-keyword threshold + dampener allowlist; per-user dismiss; per-market daily cache; XSS-safe render.
- [ ] **Phase 39: Guide UI — Tour + Tooltips** — Shepherd.js v14.5.1 (license-verified) + Microtip 0.2.2, both CDN/SRI; tour DOM portal-mounted at `<body>`; tour state per-user in `state.json` (NOT localStorage); `htmx:afterSwap` re-validation; `role="dialog"` + Esc-closes + focus-trap + replay-from-help.
- [ ] **Phase 40: Milestone Close Audit (Codemoot + Nyquist Gate)** — codemoot review + Nyquist coverage gate; verify findings against current code (false-positive sweep); resolutions in `.planning/REVIEWS.md`; backfill any v1.3 phase missing `VALIDATION.md`/`SECURITY.md`.

### Parallelization

After Phase 37 lands (per-user state + fan-out stable), Phases 38 (NEWS) and 39 (GUIDE UI) are **independent and can run in parallel** on disjoint files:

- Phase 38 touches `news_fetcher.py`, `news_filter.py`, `web/routes/news.py`, dashboard news-panel render.
- Phase 39 touches `dashboard_legacy/tour_panel.py`, `web/routes/tour.py`, `tooltip_data.py`, dashboard CDN tags.

Phase 40 (milestone close audit) requires both 38 and 39 complete.

---

## Phase Details

### Phase 28: v1.2 UAT Closure

**Goal:** Operator can verify all 8 deferred v1.2 UAT scenarios end-to-end against production droplet + browser/phone, and sign them off in `VERIFICATION.md` so v1.2 closes cleanly before v1.3 substance lands.
**Depends on:** Nothing (v1.2 shipped)
**Requirements:** DEBT-01
**Success Criteria** (what must be TRUE):
  1. Operator records hand-recalc of ATR(14) on a v1.2 dashboard signal to 1e-6 tolerance against the production trace panel.
  2. Operator confirms iOS Safari tap-to-toggle on the trace panel works and the cookie persists across one browser reload.
  3. Operator runs `python -m backtest --years 5` against live yfinance and confirms the cumulative-return >100% gate produces a clean rc=0; operator opens `/backtest` in browser and visually confirms the report renders with no template-leak artefacts.
  4. Operator runs the cold-start smoke + multi-tab market-scoping walkthrough on the production droplet; all 6 UAT-26-N scenarios are signed `verified` in a single `VERIFICATION.md`.
**Plans:** 6 plans
**Plan list:**
- [x] 28-01-PLAN.md — Persisted UAT substrate: pyproject uat marker + pytest-playwright dev dep + tests/uat/ conftest
- [x] 28-02-PLAN.md — Phase 17 UAT-1 ATR(14) hand-recalc Playwright spec
- [x] 28-03-PLAN.md — Phase 17 UAT-3 cookie-persistence Playwright spec
- [x] 28-04-PLAN.md — Phase 23 UAT-2 /backtest visual-smoke Playwright spec
- [x] 28-05-PLAN.md — Phase 26 UAT-1..6 cold-start + multi-tab Playwright specs
- [ ] 28-06-PLAN.md — Live evidence pass + 28-VERIFICATION.md (autonomous=false; iOS Safari operator checkpoint)
**Plan-time verification:** none (mechanical UAT closure).

### Phase 29: v1.2.1 Retroactive Patch Wrap + Validation Sweep

**Goal:** The 5 ad-hoc post-v1.2 polish commits (scheduler tz, signal status ladder, v1.1 backtested defaults, trace vote_params, market tab refresh) are formalised as a single v1.2.1 patch phase, every v1.2 phase has a `VALIDATION.md` + `SECURITY.md`, and the `.planning/backtests` CWD-relative path is fixed.
**Depends on:** Phase 28
**Requirements:** DEBT-02, DEBT-03, DEBT-04, OPS-02
**Success Criteria** (what must be TRUE):
  1. `MILESTONES.md` has a v1.2.1 patch-phase entry naming each of the 5 commits with a one-line behaviour note and a regression test pointer.
  2. Every v1.2 phase directory (17, 19, 20, 22, 23, 24, 25, 26) contains a Nyquist-format `VALIDATION.md` matching the format established by Phase 23 + 27.
  3. Every v1.2 phase directory (17, 19, 20, 22, 23, 24, 25, 26) contains a `SECURITY.md` matching the threat-model + mitigations format established by Phase 27.
  4. `python -m backtest` and the `/backtest` route resolve `.planning/backtests/` from project root regardless of caller CWD; one regression test runs both from `/tmp` and asserts identical output paths.
**Plans:** 14 plans
**Plan list:**
- [x] 29-01-OPS-02-BACKTESTS-PATH-FIX-PLAN.md — Anchor `.planning/backtests/` paths to project root via `Path(__file__).resolve().parents[N]` + subprocess CWD-invariance test
- [x] 29-02-UAT-26-1-COLDSTART-JS-FIX-PLAN.md — Brace-rebalance equityChart inline JS at section_renderers.py:218-220 + UAT pageerror regression test
- [x] 29-03-DEBT-02-V1-2-1-PATCH-WRAP-PLAN.md — MILESTONES.md v1.2.1 sub-section + scheduler tz / status ladder / trace vote_params regression tests
- [x] 29-04-VALIDATION-SECURITY-PHASE-17-PLAN.md — Phase 17 VALIDATION.md + SECURITY.md retrofit (mechanical)
- [x] 29-05-VALIDATION-SECURITY-PHASE-19-PLAN.md — Phase 19 VALIDATION.md + SECURITY.md retrofit (mechanical)
- [x] 29-06-VALIDATION-SECURITY-PHASE-20-PLAN.md — Phase 20 VALIDATION.md + SECURITY.md retrofit (mechanical)
- [x] 29-07-VALIDATION-SECURITY-PHASE-22-PLAN.md — Phase 22 VALIDATION.md + SECURITY.md retrofit (mechanical)
- [x] 29-08-VALIDATION-SECURITY-PHASE-24-PLAN.md — Phase 24 VALIDATION.md + SECURITY.md retrofit (mechanical)
- [x] 29-09-VALIDATION-SECURITY-PHASE-25-PLAN.md — Phase 25 VALIDATION.md + SECURITY.md retrofit (mechanical)
- [x] 29-10-VALIDATION-SECURITY-PHASE-26-PLAN.md — Phase 26 VALIDATION.md + SECURITY.md retrofit (mechanical)
- [ ] 29-11-UAT-17-1-ATR-SEED-EXPOSURE-PLAN.md — Expose engine Wilder ATR seed in trace panel + 1e-6 hand-recalc convergence test
- [ ] 29-12-UAT-17-2-IOS-SAFARI-DETAILS-OPEN-PLAN.md — Server-side `<details open>` from `tsi_trace_open` cookie + integration test (depends on 29-11)
- [ ] 29-13-UAT-23-1-YFINANCE-SPIKE-PLAN.md — Time-boxed yfinance regression spike (≤1d) with TIGHT inline fix OR WIDE escape to Phase 29.5 (autonomous=false)
- [ ] 29-14-PHASE-28-VERIFICATION-CLOSURE-PLAN.md — Append PASS rows to 28-VERIFICATION.md + Phase 29 Closure section (autonomous=false; iOS Safari operator checkpoint)
**Plan-time verification:** none (debt closure / docs-only / single bug fix).

### Phase 29.5: yfinance Regression Fix — COMPLETE

**Goal:** Wire `settings=system_params.default_settings_for_market(instrument)` into `backtest/cli.py::_run_one_instrument` to close UAT-23-1 (SPI200 0-trades bug caused by `one_contract_floor=False` default).
**Depends on:** Phase 29 (plan 29-13 escape to autonomous fix)
**Requirements:** UAT-23-1
**Plans:** 1 plan, 1 wave, autonomous
**Plan list:**
- [x] 29-5-01-SETTINGS-WIRING-PLAN.md — Wire settings= into _run_one_instrument; add TestSettingsWiring regression guard; acceptance gate (commits eea89ba, 4b08e81)
**Result:** SPI200 67 trades, AUDUSD 40 trades. Combined +79.90% (FAIL threshold — strategy performance, not code defect). UAT-23-1 closed.

### Phase 30: File-Size Pre-Split

**Goal:** All pre-existing 500-LOC violators are split behaviour-preservingly under D-09 cap before any v1.3 multi-tenant change touches their semantics, so later `user_id` injection diffs stay clean and merge-safe; AST hex blocklist is extended to cover v1.3 I/O modules.
**Depends on:** Phase 29
**Requirements:** OPS-01, OPS-03
**Success Criteria** (what must be TRUE):
  1. Every daughter file produced by splitting `web/routes/trades.py` (746), `web/routes/dashboard.py` (644), `web/routes/totp.py` (614), `web/routes/login.py` (608), and `web/routes/paper_trades.py` (493) is ≤500 LOC.
  2. Full route + template + test parity is preserved — every existing route URL resolves to the same handler signature; full test suite is green; rendered HTML is byte-identical for the dashboard route on a fixture state.
  3. AST blocklist test (`tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent`) is extended so `signal_engine`, `sizing_engine`, `system_params`, and `backtest/` cannot import any of `news_fetcher`, `news_filter`, `auth_store` extensions, `web/*`, or any other v1.3-introduced I/O module.
**Plans:** 7 plans
**Plan list:**
- [x] 30-01-PLAN.md — OPS-03: Extend FORBIDDEN_MODULES with v1.3 I/O module names (web, news_fetcher, news_filter, auth_store)
- [x] 30-02-PLAN.md — OPS-01: Split web/routes/trades.py (746 LOC) into trades/ package (__init__, _models, _renderers)
- [x] 30-03-PLAN.md — OPS-01: Split web/routes/dashboard.py (650 LOC) into dashboard/ package (__init__, _renderers — closures stay in register())
- [x] 30-04-PLAN.md — OPS-01: Split web/routes/totp.py (614 LOC) into totp/ package (__init__, _renderers)
- [x] 30-05-PLAN.md — OPS-01: Split web/routes/login.py (608 LOC) into login/ package (__init__, _renderers — re-exports _is_safe_next for sibling totp)
- [x] 30-06-PLAN.md — OPS-01: Split web/routes/paper_trades.py (493 LOC) into paper_trades/ package (__init__, _models, _renderers — re-exports _D09_KEYS, _MULTIPLIER, _COST_AUD)
- [x] 30-07-PLAN.md — Final integration gate (depends on 30-01..30-06): full suite + LOC audit + AST guard + ruff
**Plan-time verification:** none (mechanical splits + AST blocklist extension).
**UI hint:** yes

### Phase 31: Core Module Split

**Goal:** `state_manager.py` (1,293 LOC) and `sizing_engine.py` (820 LOC) are split into focused submodule packages before any v1.3 multi-tenant `user_id` injection touches their semantics, so later per-user diffs are reviewable at the submodule level.
**Depends on:** Phase 30
**Requirements:** OPS-05
**Success Criteria** (what must be TRUE):
  1. `state_manager/` package exposes the same public surface as the current `state_manager.py`; internally split into `migrations.py` (schema upgrade chain), `validation.py` (Pydantic validators + schema-version guards), `io.py` (atomic-write + `fcntl.flock` layer), and `trades.py` (trade-record helpers); every daughter file ≤500 LOC.
  2. `sizing_engine/` package exposes the same public surface as the current `sizing_engine.py`; internally split into `sizing.py` (position-size calculation), `stops.py` (stop-loss logic), `pyramid.py` (pyramid add/exit logic), and `close.py` (close-position helpers); every daughter file ≤500 LOC.
  3. Full test suite is green; all existing import paths resolve without change (public API exposed via package `__init__.py` re-exports); no external callers import implementation submodules directly.
  4. AST hex boundary still passes: `signal_engine`, `data_fetcher`, and `web/*` cannot import `sizing_engine` internals directly (must go via the package surface).
**Plans:** 3 plans
**Plan list:**
- [ ] 31-01-PLAN.md — state_manager/ package: scaffold + io.py + validation.py + trades.py + migrations.py + __init__.py; delete state_manager.py (Wave 1)
- [ ] 31-02-PLAN.md — sizing_engine/ package: scaffold + _models.py + sizing.py + stops.py + pyramid.py + close.py + __init__.py; delete sizing_engine.py (Wave 1)
- [ ] 31-03-PLAN.md — Integration gate: full suite + LOC audit + caller import check + hex boundary + deadlock invariant (Wave 2)
**Plan-time verification:** none (mechanical splits, public API preserved by `__init__.py` re-exports).

### Phase 32: Dashboard Legacy Retirement

**Goal:** `dashboard_renderer/` is confirmed as the sole canonical dashboard renderer; `dashboard_legacy/` is retired (deleted or quarantined with an `ImportError` stub); `dashboard.py` shim is thinned to route-through only; the three-surface split that caused the recent layout-drift issue is eliminated.
**Depends on:** Phase 31
**Requirements:** OPS-06
**Success Criteria** (what must be TRUE):
  1. No live code path imports from `dashboard_legacy/`; `git grep "dashboard_legacy"` returns zero matches outside of test quarantine markers and this ROADMAP.
  2. `dashboard_legacy/` is either deleted entirely or replaced by a single `__init__.py` that raises `ImportError("dashboard_legacy retired — use dashboard_renderer")` to catch accidental re-introduction.
  3. `dashboard.py` is ≤100 LOC and acts solely as a shim delegating to `dashboard_renderer`; no rendering logic lives in it.
  4. Full test suite is green; rendered HTML from `dashboard_renderer` is byte-identical on fixture state vs pre-Phase 32 baseline (confirms no behaviour regression from the retirement).
**Plans:** 4 plans
**Plan list:**
- [x] 32-01-PLAN.md — Port render_helpers / section_renderers / page_body unique content into dashboard_renderer/{formatters,stats,shell,components/header} (Wave 1)
- [x] 32-02-PLAN.md — Create components/{trace,calc_rows,account}.py + absorb positions_section + paper_trades_section into components/{positions,paper_trades}.py (Wave 2)
- [x] 32-03-PLAN.md — Eliminate `import dashboard as d` in dashboard_renderer/{api,pages,components/positions}.py; confirm acyclic package import (Wave 3)
- [x] 32-04-PLAN.md — Thin dashboard.py to ≤100 LOC shim + retire dashboard_legacy stub + update all callers/tests + integration gate (Wave 4)
**Plan-time verification:** audit each module in `dashboard_legacy/` against `dashboard_renderer/` to confirm coverage before deleting; if a unique capability is found in `dashboard_legacy/`, port it first.

### Phase 33: Schema Migration v11→v12 + Admin Namespace + Backup + Gitignore

**Goal:** `state.json` migrates from `STATE_SCHEMA_VERSION = 11` to v12 by build-then-validate-then-save with auto-backup; admin's existing paper-trade history moves losslessly into `state['users']['admin_<uid>']`; per-user state paths are gitignored with CI enforcement + off-droplet daily backup.
**Depends on:** Phase 32
**Requirements:** TENANT-01, TENANT-04
**Success Criteria** (what must be TRUE):
  1. Migration runs as a single `_migrate_v11_to_v12(old: dict) -> dict` that builds a fresh dict, Pydantic-validates the v12 shape, and only then saves; auto-backup `state.json.v11-backup-<isoformat>` is written before the save.
  2. Round-trip test on 5 fixtures (empty, max trade_log, mid-pyramid, mid-alert APPROACHING, naive-datetime legacy) is lossless: every v11 field that maps to v12 is present with identical value in the migrated output; the v12 result passes Pydantic StateV12 validation.
  3. Migration-chain contiguity assert at module load + `load_state()` entry passes for the new chain ending at v12.
  4. `state/users/` is gitignored; `git ls-files | grep '^state/users/'` returns zero rows; CI fails the build if any per-user state path enters tracked files.
  5. Off-droplet backup (rclone-to-B2 or equivalent) runs daily; admin receives an alert email if backup is older than 48h.
**Plans:** 4 plans
**Plan list:**
- [x] 33-01-PLAN.md — Migration core: _migrate_v11_to_v12, STATE_SCHEMA_VERSION=12, MIGRATIONS[12], _REQUIRED_STATE_KEYS v12, StateV12 Pydantic model, reset_state() v12 shape, backup+validate in load_state() (Wave 1)
- [x] 33-02-PLAN.md — Round-trip fixtures + tests: 5 v11 fixture files + test_state_migration_v12.py (Wave 2, depends on 33-01)
- [x] 33-03-PLAN.md — Gitignore + CI gate: state/users/ entries in .gitignore + tests/test_gitignore_gate.py (Wave 2, depends on 33-01)
- [x] 33-04-PLAN.md — rclone-to-B2 backup + 48h stale alert: scripts/backup_state.sh + scripts/check_backup_age.py + systemd units + send_backup_stale_email + docs (Wave 2, depends on 33-01)

### Phase 34: User Registry + Invite-Token Storage

**Goal:** `auth.json` holds the user list and pending invites alongside trusted_devices (single transactional file); invite tokens are minted with `secrets.token_urlsafe(32)`, stored as sha256 hashes only, verified via `hmac.compare_digest`, expire in 7 days, and consume single-use under `flock`. No routes yet — pure storage layer.
**Depends on:** Phase 33
**Requirements:** RBAC-03 (storage half — acceptance flow lands in Phase 37)
**Success Criteria** (what must be TRUE):
  1. `auth_store.users[]` + `auth_store.pending_invites[]` arrays exist; user-create + invite-consume are one transactional `mutate(auth)` call (no cross-file race window where invite is consumed but user is not created).
  2. Invite tokens are stored ONLY as `sha256:<hex>` hashes in `auth.json`; raw plaintext token never appears in any persisted file (grep gate over `auth.json` and `state.json` returns zero matches for any issued token).
  3. Two parallel `consume(token)` calls produce exactly one winner (single-use guaranteed by `flock` on the auth-file lock companion); the loser raises `InviteAlreadyConsumed`.
  4. Token expiry is 7 days from issue; `expired` and `revoked` consume paths return distinct typed errors.
**Plans:** 2 plans
**Plan list:**
- [x] 34-01-PLAN.md — auth_store/ package split + schema v2 TypedDicts + v1->v2 migration + TestForbiddenImports update (Wave 1)
- [x] 34-02-PLAN.md — _users.py (create_user, mint_invite_token, consume_and_create_user, get_user, list_users, set_user_disabled) + tests/test_auth_store_users.py (Wave 2)
**Plan-time verification:** none (stdlib-stable patterns).

### Phase 35: Cookie + Depends(current_user) + Sub-Router Admin Gate

**Goal:** Authenticated user has `user_id` declaratively available via `Depends(current_user)` in every route; admin-only routes are mounted under a sub-router with `require_admin` baked in at mount time; admin remains the only user with no observable behaviour change at this phase boundary, so all v1.2 routes survive untouched semantically.
**Depends on:** Phase 34
**Requirements:** RBAC-01, RBAC-02
**Success Criteria** (what must be TRUE):
  1. Cookie session payload extends to `{"uid": "<user_id>"}`; `web/middleware/auth.py` sets `request.state.user_id`; backward-compat shim accepts cookies without `uid` and treats them as admin during migration grace.
  2. `web/dependencies.py` exposes `current_user_id` and `require_admin` factories; every authenticated route receives `user_id` via `Depends(current_user_id)`, no route reads `request.cookies` directly.
  3. `web/routes/admin/` is an `APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])` sub-router; new admin routes registered on it inherit the gate.
  4. Startup invariant test walks `app.routes` and asserts every `/admin/*` path has `require_admin` somewhere in its dependency chain; parametrized non-admin-gets-403 sweep covers every admin path.
  5. Admin's existing observable behaviour is unchanged: full v1.2 dashboard, paper-trade entry, signal display — all routes return identical bytes vs pre-Phase 35 fixtures.
**Plans:** 5 plans
**Plan list:**
- [x] 35-01-PLAN.md — auth_store get_user_by_email helper + re-export + unit tests (Wave 1)
- [x] 35-02-PLAN.md — _make_session_cookie uid extension + AuthMiddleware sets request.state.user_id with D-04 shim (Wave 2)
- [x] 35-03-PLAN.md — web/dependencies.py current_user_id + require_admin factories + Wave-0 test stub (Wave 2)
- [x] 35-04-PLAN.md — web/routes/admin/ sub-router with APIRouter(prefix='/admin', dependencies=[Depends(require_admin)]) + GET /admin/ping (Wave 3)
- [x] 35-05-PLAN.md — web/app.py include_router(admin_router) wiring + startup invariant + 403-sweep + happy-path tests (Wave 4)
**Plan-time verification:** none (FastAPI patterns canonical).

### Phase 36: Per-Route User-ID Scoping + Privacy Boundary + Per-User Flock

**Goal:** Every per-user route reads SHARED signals + writes PER-USER positions/trades/alerts/journal/equity through `mutate_user_state(uid, mutator)` with per-user `fcntl.flock`; `PublicUserSummary` + `RedactStateFilter` enforce the privacy boundary; `TestTenantIsolation` is introduced as the milestone-wide quality gate.
**Depends on:** Phase 35
**Requirements:** TENANT-02, TENANT-03, RBAC-04
**Success Criteria** (what must be TRUE):
  1. `mutate_user_state(user_id, mutator)` is a thin wrapper over the existing `mutate_state` chokepoint; per-user `fcntl.flock(state/users/{uid}.lock, LOCK_EX)` serializes daily fan-out vs HTMX writes; lock is held across the full read-modify-write window.
  2. `TestTenantIsolation` test class is green: fixture user A holding 5 paper trades produces zero `(entry_price|n_contracts|"direction":\s*"(LONG|SHORT)")` matches in admin user-list HTML, in any log line during a fan-out cycle, in the crash-email body, or in user B's served dashboard.
  3. Every entity-ID route (paper-trade close, trade modify, journal patch, alert ack) has a paired `test_<route>_returns_404_for_other_users_entity` test that creates user A's row, authenticates as user B, and asserts 404.
  4. `PublicUserSummary` Pydantic model carries only `{user_id, display_name, status, last_seen_date, has_active_position: bool}`; admin `/admin/users` view returns `list[PublicUserSummary]` only — no `state[]`, no trade content, no equity figures.
  5. `RedactStateFilter` is installed at app startup; structured field-name allowlist (`event`, `user_id`, `signal_as_of`, `rc`) — `paper_trades`/`equity_history`/`entry_price`/`n_contracts`/`journal` are replaced with `<redacted>` in log records.
  6. Admin can reversibly disable any non-admin user from `/admin/users`; disabled users cannot log in; their data is preserved (re-enable restores everything); terminal delete is explicitly NOT shipped (deferred to v1.3.x).
**Plans:** 3 plans
Plans:

**Wave 1**
- [x] 36-01-PLAN.md — Foundation (mutate_user_state, load_user_state, record_trade uid param, PublicUserSummary model, conftest v12 fixtures, test stubs)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 36-02-PLAN.md — Route Migration (paper_trades + trades migrate to mutate_user_state, admin GET /users + PATCH /users/{uid}/disable)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 36-03-PLAN.md — Test Coverage (TestMutateUserState, 9 entity-ID 404 tests, TestTenantIsolation isolation assertion)

**Cross-cutting constraints:**
- All routes must navigate `state['users'][user_id]` sub-dict for per-user data (not top-level state)
- All `mutate_user_state` calls acquire per-user flock before delegating to `mutate_state`
- `response_model=list[PublicUserSummary]` is the sole privacy enforcement mechanism in Phase 36
**Plan-time verification (research-flagged):**
- **State layout flock interaction:** confirm the `flock(LOCK_EX)`-across-read-modify-write pattern composes cleanly with existing `mutate_state` semantics under simulated 50-thread stress before locking the single-file `users{}` map choice; if friction-laden, fall back to the sharded-directory option (Stack research's Option A). Per-user flock itself is non-negotiable either way.

### Phase 37: Per-User Email Fan-Out + Admin Invite/Disable Routes + Invite-Acceptance Flow

**Goal:** F&F users receive their own 08:00 Sydney email with their stop-loss alerts, paper P&L, and the shared signal block; signal compute happens once per market per day; per-user crash boundary + admin summary email survive partial failures; admin can issue/revoke invites and disable users from the UI; invitee can accept the link, set a password, enrol TOTP, and join.
**Depends on:** Phase 36
**Requirements:** RBAC-03 (acceptance flow), UMAIL-01, UMAIL-02, UMAIL-03, UMAIL-04
**Success Criteria** (what must be TRUE):
  1. `per_user_fanout.py` orchestrator seam (top-level, NOT inside `daily_run.py`) batches all per-user alert updates into a single terminal `mutate_state` call so the W3 invariant (exactly two saves per cycle) survives; yfinance fetch count remains exactly 2 per cycle (one per market) regardless of user count.
  2. Per-user `try/except` crash boundary wraps each user's pass; one user's broken state cannot abort the cycle for any other user; admin receives an end-of-cycle summary email naming successes + per-user failures; `/healthz/last-cycle` endpoint reports per-user outcomes.
  3. `asyncio.Semaphore(2)` (or equivalent under the documented Resend rate limit ÷ 2) throttles outbound Resend calls; RFC 8058 `List-Unsubscribe` + `List-Unsubscribe-Post` headers are present on every per-user email; no session token, no invite token, no other secret appears in any email body or URL.
  4. User can toggle daily email enable/disable and set `pause-until-YYYY-MM-DD` from the dashboard; preference persists in their per-user state; fan-out skips paused/disabled users without burning a Resend quota; admin's email is unaffected by F&F preferences.
  5. Admin can issue an invite from `/admin/users`, view invite-pending status, and revoke unaccepted invites; invitee clicks link, sets password, enrols TOTP, confirms trusted device, and lands on a dashboard scoped to their per-user state.
  6. Performance test with 50 mocked users completes within 30s, throttled, with no 429s; `Müller`-style Unicode display name round-trips via `email.utils.formataddr` (RFC 2047).
**Plans:** TBD
**Plan-time verification (research-flagged):**
- **Resend rate limit threshold:** re-verify documented current rate limit (older accounts 2 req/sec, newer 5 req/sec) before locking the semaphore constant; confirm batch-send API availability is unchanged.
**UI hint:** yes

### Phase 38: News Integration

**Goal:** Each market dashboard shows top 5 yfinance headlines per market with a critical-event heuristic banner; news fetch is shared per-market per-day (one fetch, all users see the same items); per-user dismiss state isolates the view; XSS + SSRF closed; signal compute remains AST-isolated from news input.
**Depends on:** Phase 37 (parallelizable with Phase 39)
**Requirements:** NEWS-01, NEWS-02, NEWS-03, NEWS-04
**Success Criteria** (what must be TRUE):
  1. User sees top 5 latest `yfinance.Ticker.news` headlines per market on `/markets/{m}` route, deduplicated by title hash, cached daily (one fetch per market per day shared across users), Jinja2 `autoescape=True`, outbound links carry `rel="noopener noreferrer"`.
  2. News-fetch adapter (`news_fetcher.py`) normalises both pre-0.2.55 flat-list yfinance shape and post-0.2.55 nested `content` envelope into one internal model; both-shape fixtures pass; `<script>alert(1)</script>` headline renders as escaped text; no server-side prefetch of headline links (SSRF-closed by render-time-only escape).
  3. Critical-event banner fires from a hand-curated word-boundary regex classifier (per-market keyword list with allowlist dampener like `first-rate`, `second-rate`); banner copy explicitly labels the heuristic ("Possible market-moving news — operator review recommended"); classifier achieves precision ≥0.7 and recall ≥0.9 against a 30-headline labelled fixture committed to the repo.
  4. User can dismiss a headline; dismiss state persists in `state['users'][uid]['news_dismissed']`; admin's dismiss does not affect any F&F user's view, and vice versa.
  5. AST hex boundary still passes: `signal_engine` cannot import `news_fetcher` or `news_filter`; `news_filter.py` is in `_HEX_PATHS_STDLIB_ONLY` (pure module); `news_fetcher.py` is an I/O peer of `data_fetcher.py` with its own no-forbidden-imports test.
**Plans:** TBD
**Plan-time verification (research-flagged):**
- **yfinance fresh fixtures:** capture both pre-0.2.55 and post-0.2.55 news payload fixtures from the pinned yfinance version at plan time (library schema drift across 0.2.40 → 0.2.55 → 1.x is real); commit fixtures to the repo.
**UI hint:** yes

### Phase 39: Guide UI — Tour + Tooltips

**Goal:** New F&F users see a 3-step first-run tour on first dashboard load (covering navigation, the v1.2 trace-panel differentiator, and paper-trade entry); inline tooltips on every panel survive HTMX swaps with no JS rebind; tour state persists per-user server-side; tour is keyboard-accessible and replayable from `/help`.
**Depends on:** Phase 37 (parallelizable with Phase 38)
**Requirements:** GUIDE-01, GUIDE-02, GUIDE-03, GUIDE-04
**Success Criteria** (what must be TRUE):
  1. User hovers or focuses any panel header / control on the dashboard and sees an inline tooltip (Microtip-based, pure-CSS, survives HTMX swaps with no JS rebind) with WAI-ARIA `role="tooltip"`, ≥16px font on mobile, unique `aria-describedby` ID; tooltip count adds zero new tab stops on inactive market panels and zero new axe-core violations vs the Phase 25 baseline.
  2. New F&F user sees a 3-step first-run tour on first dashboard load (Step 1 — dashboard navigation, Step 2 — Inputs/Indicators/Vote trace panel, Step 3 — paper-trade entry); tour state is server-side per-user (`state['users'][uid]['tour_completed']`, NOT localStorage); tour DOM is portal-mounted at `<body>` level (NOT inside any HTMX swap target); tour overlay survives `htmx:afterSwap` of `#main` via re-validation.
  3. User can press Esc to dismiss the tour, click "Skip tour", or complete the tour — all three paths set `tour_completed: true` in their per-user state; tour modal is `role="dialog"` with focus-trap; keyboard-only flow (Tab cycles dialog buttons, Esc closes) is verified by a Playwright keyboard-only test.
  4. User can click a persistent "Restart tour" link in the dashboard header (or `/help` route) to replay the tour from step 1; this clears `tour_completed` server-side and reruns the tour; second click after completion works idempotently (no stale Shepherd.js state).
**Plans:** TBD
**Plan-time verification (research-flagged):**
- **Shepherd.js license:** verify license terms at install time (was AGPL through some 2024 versions, then relaxed); switch to Driver.js (MIT) if AGPL-blocked. CDN/SRI hashes generated and pinned at install.
**UI hint:** yes

### Phase 40: Milestone Close Audit (Codemoot + Nyquist Gate)

**Goal:** Operator runs codemoot + Nyquist coverage gate against the full v1.3 surface, verifies findings against current code (codemoot has ~40-50% false-positive rate), records resolutions in `.planning/REVIEWS.md`, backfills any v1.3 phase missing `VALIDATION.md`/`SECURITY.md`, and closes the milestone with no unresolved critical findings.
**Depends on:** Phase 38 AND Phase 39
**Requirements:** OPS-04
**Success Criteria** (what must be TRUE):
  1. `codemoot review --focus all` is run on the full v1.3 changeset; every finding is verified against current code by spawning an exploration agent to confirm at the exact file:line; resolutions are recorded in `.planning/REVIEWS.md`.
  2. Every v1.3 phase directory (28–39) contains a Nyquist-format `VALIDATION.md` and a `SECURITY.md`; gaps from earlier phases are backfilled here.
  3. Zero critical (security or correctness) codemoot findings remain unresolved at milestone close; INFO/WARNING findings are logged as known debt with a triage note.
  4. Full test suite is green; AST hex boundary passes; `TestTenantIsolation` passes; `git ls-files | grep '^state/users/'` returns nothing; off-droplet backup is current (<48h old).
**Plans:** TBD
**Plan-time verification:** none (process step).

---

## v1.4 Domain Models

**Goal:** Replace dict-shaped market config and strategy settings with typed Pydantic models so schema mistakes are caught at construction time, `dict.get(...)` defensive patterns disappear at call sites, and future per-user market customisation has a stable contract to extend.

**Granularity:** fine.
**Phase numbering:** continues from v1.3 (last phase 40). v1.4 starts at **Phase 41**.

### Hard Constraints (inherited; non-negotiable)

- Hex-lite AST guard preserved — `signal_engine`, `sizing_engine`, `system_params`, `backtest/` stay pure-math.
- File-based persistence unchanged — no schema migration in this milestone (Pydantic models are used in-process; serialisation format stays `state.json` dict-compatible).
- HTMX-only, no SPA.

### Phases

- [ ] **Phase 41: Domain Models — Pydantic Market Config + Strategy Settings** — `MarketConfig` and `StrategySettings` Pydantic models replace `dict[str, dict]` shapes in `system_params.py`; `SignalSnapshot` Pydantic model replaces ad-hoc dict construction in `signal_engine.py`; `Position` TypedDict upgraded to Pydantic `BaseModel`; all call-site `dict.get(...)` replaced with attribute access; import-time validation catches schema mistakes.

---

### Phase 41: Domain Models — Pydantic Market Config + Strategy Settings

**Goal:** `DEFAULT_MARKETS` and `DEFAULT_STRATEGY_SETTINGS_BY_MARKET` in `system_params.py` are backed by `MarketConfig` and `StrategySettings` Pydantic models; `signal_engine.py` emits a typed `SignalSnapshot`; `Position` TypedDict is upgraded to a Pydantic `BaseModel`; all call-site `dict.get(key, default)` patterns at the domain boundary are replaced with typed attribute access.
**Depends on:** Phase 40
**Requirements:** DOMAIN-01, DOMAIN-02, DOMAIN-03
**Success Criteria** (what must be TRUE):
  1. `MarketConfig` Pydantic model covers all fields currently in `DEFAULT_MARKETS` dict entries (`ticker`, `display_name`, `contract_type`, `financing_rate_annual_pct`, etc.); `DEFAULT_MARKETS` values validate at import time; any unknown or missing field raises `ValidationError` at startup, not silently at call-site.
  2. `StrategySettings` Pydantic model covers all fields in `DEFAULT_STRATEGY_SETTINGS` / `DEFAULT_STRATEGY_SETTINGS_BY_MARKET`; validators enforce domain invariants (e.g. ATR period > 0, risk fraction ∈ (0, 1], pyramid levels ≥ 1); `default_settings_for_market()` returns `StrategySettings`; callers use `settings.atr_period` not `settings.get("atr_period")`.
  3. `SignalSnapshot` Pydantic model captures signal state at validation time (vote result, ATR, entry price, stop distance, etc.); replaces ad-hoc dict construction in `signal_engine.py`; `state_manager` and `dashboard_renderer` access fields via attribute, not `.get()`.
  4. `Position` TypedDict is upgraded to a Pydantic `BaseModel`; round-trip serialisation `Position.model_dump()` / `Position.model_validate(d)` is lossless on all existing `state.json` fixtures; no raw dict is constructed for Position at any call site.
  5. Full test suite is green; AST hex boundary still passes; ruff clean; no `dict.get(` usage remains inside `system_params.py`, `signal_engine.py`, or `state_manager/` for domain model fields (grep gate).
  6. Serialisation format is unchanged: `model.model_dump()` produces a dict byte-compatible with existing `state.json` schemas; no migration is required.
**Plans:** TBD
**Plan-time verification (research-flagged):**
- **Position round-trip:** confirm all existing `state.json` Position fixtures validate cleanly via `Position.model_validate()` before adding validators; fix any field name or type discrepancy first to avoid a silent data migration.
- **Hex boundary:** confirm Pydantic is already an allowed import in `system_params.py` (it is a stdlib-adjacent dep); if not, add it to the allowed-imports list in the AST guard before writing models.

---

## Coverage Map (v1.3)

| Requirement | Phase |
|-------------|-------|
| DEBT-01 | 28 |
| DEBT-02 | 29 |
| DEBT-03 | 29 |
| DEBT-04 | 29 |
| OPS-01 | 30 |
| OPS-02 | 29 |
| OPS-03 | 30 |
| OPS-04 | 40 |
| OPS-05 | 31 |
| OPS-06 | 32 |
| TENANT-01 | 33 |
| TENANT-02 | 36 |
| TENANT-03 | 36 |
| TENANT-04 | 33 |
| RBAC-01 | 35 |
| RBAC-02 | 35 |
| RBAC-03 | 34 (storage) + 37 (acceptance flow) |
| RBAC-04 | 36 |
| UMAIL-01 | 37 |
| UMAIL-02 | 37 |
| UMAIL-03 | 37 |
| UMAIL-04 | 37 |
| NEWS-01 | 38 |
| NEWS-02 | 38 |
| NEWS-03 | 38 |
| NEWS-04 | 38 |
| GUIDE-01 | 39 |
| GUIDE-02 | 39 |
| GUIDE-03 | 39 |
| GUIDE-04 | 39 |

**Total:** 30/30 v1.3 requirements mapped. RBAC-03 is split across the storage layer (Phase 34) and the user-visible acceptance flow (Phase 37) — same requirement, two phase deliverables. No orphans, no duplicates of any other REQ-ID.

---

## Archived Milestones

<details>
<summary>✅ v1.2 Trader-Grade Transparency & Validation (Phases 17, 19, 20, 22-27) — SHIPPED 2026-05-10</summary>

- [x] Phase 17: Per-signal calculation transparency (1/1 plans) — completed 2026-04-30
- [x] Phase 19: Paper-trade ledger (1/1 plans) — completed 2026-04-30
- [x] Phase 20: Stop-loss monitoring & alerts (1/1 plans) — completed 2026-04-30
- [x] Phase 22: Strategy versioning & audit trail (1/1 plans) — completed 2026-04-29
- [x] Phase 23: 5-year backtest validation gate (7/7 plans) — completed 2026-05-01
- [x] Phase 24: v1.2 codemoot fix phase (1/1 plans) — completed 2026-05-01
- [x] Phase 25: Dashboard UI/UX overhaul (12/12 plans) — completed 2026-05-07
- [x] Phase 26: Phase 25 follow-up scoping fixes (8/8 plans) — completed 2026-05-08
- [x] Phase 27: Code-quality correctness sweep (16/16 plans) — completed 2026-05-10

Phase dirs archived to [milestones/v1.2-phases/](milestones/v1.2-phases/).

</details>

<details>
<summary>✅ v1.1 Interactive Trading Workstation (Phases 10-16 + 16.1) — SHIPPED 2026-04-30</summary>

Phase artifacts still in [phases/](phases/). Roadmap: [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md).

</details>

<details>
<summary>✅ v1.0 MVP Mechanical Signal System (Phases 1-9) — SHIPPED 2026-04-24</summary>

Phase dirs archived to [milestones/v1.0-phases/](milestones/v1.0-phases/). Roadmap: [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md).

</details>

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 17. TRACE | v1.2 | 1/1 | Complete | 2026-04-30 |
| 19. LEDGER | v1.2 | 1/1 | Complete | 2026-04-30 |
| 20. ALERT | v1.2 | 1/1 | Complete | 2026-04-30 |
| 22. VERSION | v1.2 | 1/1 | Complete | 2026-04-29 |
| 23. BACKTEST | v1.2 | 7/7 | Complete | 2026-05-01 |
| 24. codemoot fix | v1.2 | 1/1 | Complete | 2026-05-01 |
| 25. UI overhaul | v1.2 | 12/12 | Complete | 2026-05-07 |
| 26. 25-followup | v1.2 | 8/8 | Complete | 2026-05-08 |
| 27. quality sweep | v1.2 | 16/16 | Complete | 2026-05-10 |
| 28. v1.2 UAT closure | v1.3 | 5/6 | In Progress|  |
| 29. v1.2.1 patch wrap + validation sweep | v1.3 | 10/14 | In Progress|  |
| 30. file-size pre-split | v1.3 | 7/7 | Complete | 2026-05-11 |
| 31. core module split | v1.3 | 0/0 | Not started | - |
| 32. dashboard legacy retirement | v1.3 | 5/4 | Complete    | 2026-05-12 |
| 33. schema v11→v12 + backup | v1.3 | 0/0 | Not started | - |
| 34. user registry + invite-token storage | v1.3 | 2/2 | Complete   | 2026-05-12 |
| 35. cookie + Depends + sub-router admin gate | v1.3 | 5/5 | Complete    | 2026-05-13 |
| 36. per-user scoping + privacy + flock | v1.3 | 3/3 | Complete   | 2026-05-13 |
| 37. per-user email fan-out + admin routes | v1.3 | 0/0 | Not started | - |
| 38. news integration | v1.3 | 0/0 | Not started | - |
| 39. guide UI — tour + tooltips | v1.3 | 0/0 | Not started | - |
| 40. milestone close audit | v1.3 | 0/0 | Not started | - |
| 41. domain models — Pydantic market config | v1.4 | 0/0 | Not started | - |

---

*Last updated: 2026-05-12 — Phases 31 (core module split) and 32 (dashboard legacy retirement) inserted from Codex audit recommendations; old Phases 31–38 renumbered to 33–40; OPS-05 and OPS-06 added to coverage map; requirement count updated to 30/30. v1.4 Domain Models milestone added (Phase 41, DOMAIN-01..03).*
