# Roadmap: Trading Signals — v1.2 Trader-Grade Transparency & Validation

**Created:** 2026-04-30 (`/gsd-new-milestone` after v1.1 close)
**Milestone:** v1.2 Trader-Grade Transparency & Validation
**Granularity:** fine
**Parallelization:** true
**Coverage:** 22/22 v1.2 requirements mapped (TRACE 5, LEDGER 6, ALERT 4, VERSION 3, BACKTEST 4)

**Core Value (v1.2):** Make every signal *reproducible by hand* and every paper trade *measurable*. Lift the v1.1 hosted dashboard from "tells you what to do" → "shows you exactly why and tracks how it played out". Validate the strategy ships with a 5-year backtest gate before any future logic change. Multi-user, news, and hygiene cleanups deferred to v1.3+.

## Milestones

- [x] **v1.0 MVP — Mechanical Signal System** — Phases 1–9, shipped 2026-04-24. See [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md).
- [x] **v1.1 Interactive Trading Workstation** — Phases 10–16 + 16.1, shipped 2026-04-30. See [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md).
- [ ] **v1.2 Trader-Grade Transparency & Validation** — Phases 17, 19, 20, 22, 23 (in progress from 2026-04-30).

## Prerequisites (v1.2)

None operator-blocked. All v1.2 prerequisites land within phases:
- DigitalOcean droplet (already running, v1.1 infra)
- `mwiriadi.me` domain + Resend SPF/DKIM/DMARC (already verified, v1.1)
- 1319-test suite green baseline (v1.1 close)

## Phases

- [x] **Phase 17: Per-signal calculation transparency** — Dashboard renders Inputs / Indicators / Vote panels per instrument so the operator can re-derive the signal by hand (completed 2026-04-30)
- [x] **Phase 19: Paper-trade ledger** — Web form for manual trade entry, per-trade open/closed history, mark-to-market unrealised P&L, aggregate stats (skipping Phase 18 multi-user — single-operator model from v1.1) (completed 2026-04-30)
- [x] **Phase 20: Stop-loss monitoring & alerts** — Daily approaching (within 0.5×ATR) AND hit detection per open paper trade, dedup'd email alerts with state-transition logic (completed 2026-04-30)
- [x] **Phase 22: Strategy versioning & audit trail** — `STRATEGY_VERSION` constant in `system_params.py`, every signal/trade row tagged so historical state stays interpretable across logic changes (completed 2026-04-29)
- [x] **Phase 23: 5-year backtest validation gate** — Walk-forward backtest over 5y of yfinance data, `>100% cumulative return` pass criterion, `/backtest` route on dashboard with metrics + pass/fail badge (completed 2026-05-01)
- [x] **Phase 24: v1.2 codemoot fix phase** — Fix 3 verified bugs + cleanup 7 code-quality items from post-milestone codemoot review (completed 2026-05-01)
- [x] **Phase 25: Dashboard UI/UX overhaul — true multi-tab market preferences and first-run polish** — Convert decorative market dropdown + stacked Settings forms into real two-axis nav (market × function); fix 10 priority items from /ui-ux-pro-max review 2026-05-05
- [ ] **Phase 26: Phase 25 follow-up — multi-tab market scoping fixes & post-overhaul cleanup** — Fix 4 BROKEN items (multi-tab scoping non-functional, template placeholder leak → 401s, header session widget unresolved, 3 red deploy tests), 7 RISKY items (cache invalidation, mixed return types, dead nav params, etc.), and 5 CLEANUP items (incl. `auth.json` audit + `.gitignore`) from 2026-05-07 review

## Phase Details

### Phase 17: Per-signal calculation transparency
**Goal:** Make today's signal reproducible from the dashboard alone — operator can plug numbers into Excel/Bloomberg/IG and re-derive identical indicator values without reading source code.
**Depends on:** Nothing (read-only dashboard refactor; can run in parallel with Phase 22).
**Requirements:** TRACE-01, TRACE-02, TRACE-03, TRACE-04, TRACE-05
**Success Criteria** (what must be TRUE):
1. Three new panels (Inputs / Indicators / Vote) render per instrument on `https://signals.mwiriadi.me/`
2. The Inputs panel displays the OHLC bars used by ATR(14), ADX(20), Mom-12 (today + prior 19 bars at minimum)
3. The Indicators panel displays TR, ATR, +DI, -DI, ADX, Mom1/3/12, RVol with formula + numeric result
4. The Vote panel shows the 2-of-3 momentum vote breakdown + ADX gate (with actual ADX numeric)
5. Operator can manually re-derive ATR(14) from the displayed OHLC values and match the displayed ATR result to 1e-6 tolerance
6. No new I/O or state mutation introduced — the panels are pure render from existing state + indicator recompute
7. Forbidden-imports AST guard extended for the new dashboard.py code paths

### Phase 19: Paper-trade ledger
**Goal:** Operator records the trades they've actually placed (or plan to), tracks open positions with live mark-to-market P&L, and sees a closed-trade history with realised P&L and aggregate stats.
**Depends on:** Phase 22 (paper trade rows must include `strategy_version` per VERSION-03; if 22 lands first, ledger writes the field on entry; if 19 lands first, migrate the field on Phase 22 deploy).
**Requirements:** LEDGER-01, LEDGER-02, LEDGER-03, LEDGER-04, LEDGER-05, LEDGER-06
**Success Criteria** (what must be TRUE):
1. POST `/paper-trade/open` form on dashboard accepts {instrument, side, entry_dt, entry_price, contracts, stop_price?} → validated server-side → appended to `state.paper_trades`
2. POST `/paper-trade/close` form accepts {trade_id, exit_dt, exit_price} → server computes realised P&L → flips `status=open` to `status=closed`
3. Closed rows are immutable (no edit form rendered, server returns 405 to PUT/PATCH)
4. "Open Paper Trades" table renders all `status=open` rows with current price + unrealised P&L (mark-to-market using today's close)
5. "Closed Paper Trades" table renders all `status=closed` rows sortable by exit date desc
6. Aggregate stats line displays total realised P&L, total unrealised P&L, win count, loss count, win rate %
7. Atomic-write contract preserved — `paper_trades` writes go through the same `state_manager._atomic_write` as positions/equity_history

### Phase 20: Stop-loss monitoring & alerts
**Goal:** When a paper trade with a stop price approaches or hits the stop, the operator gets a dedicated email alert (separate from the daily signal email) at most once per state transition.
**Depends on:** Phase 19 (needs `paper_trades` array with `stop_price` and `last_alert_state` fields).
**Requirements:** ALERT-01, ALERT-02, ALERT-03, ALERT-04
**Success Criteria** (what must be TRUE):
1. On every daily run, for each open paper trade with non-null `stop_price`, the system computes one of {CLEAR, APPROACHING, HIT}
2. State transition `CLEAR → APPROACHING` or `* → HIT` triggers a `[!stop]`-prefixed email to `OPERATOR_RECOVERY_EMAIL` (with daily-signal-email-style fallback if missing)
3. Same state on consecutive days does NOT re-trigger the email (deduplication via `last_alert_state` field)
4. Dashboard "Alerts" pane renders each open trade's current alert state with green/amber/red color
5. APPROACHING threshold uses 0.5 × current ATR(14); HIT detection uses today's High (for SHORT stops) and today's Low (for LONG stops) per the existing intraday-H/L exit pattern from Phase 2
6. Alert-send failures NEVER crash the daily run (existing never-crash pattern from notifier.py)

### Phase 22: Strategy versioning & audit trail
**Goal:** Every signal output and paper trade row carries a `strategy_version` tag, so historical results stay interpretable when the signal logic changes (e.g., Mom thresholds, ADX gate cutoff).
**Depends on:** Nothing (standalone, can land in parallel with Phase 17).
**Requirements:** VERSION-01, VERSION-02, VERSION-03
**Success Criteria** (what must be TRUE):
1. `STRATEGY_VERSION = 'v1.2.0'` constant added to `system_params.py`
2. `state.signals[<instrument>].strategy_version` field populated on every write (matching the constant at write-time)
3. `state.paper_trades[].strategy_version` field populated on every entry (matching the constant at entry datetime)
4. Migration on first v1.2 deploy: existing signal rows stamped `v1.1.0`; existing paper_trades rows (if Phase 19 already shipped) stamped `v1.1.0` retroactively
5. `docs/STRATEGY-CHANGELOG.md` created with v1.0.0 / v1.1.0 / v1.2.0 entries explaining what each version represents
6. Bumping `STRATEGY_VERSION` does NOT mutate historical rows — closed paper trades retain the version they were entered under

### Phase 23: 5-year backtest validation gate
**Goal:** Validate the strategy ships every change with a 5-year walk-forward backtest. Pass criterion is `cumulative return > 100% over 5y`. Operator views report on `/backtest` route; failures block the strategy change socially (operator expected to revert).
**Depends on:** Phase 22 (results tagged with `strategy_version`).
**Requirements:** BACKTEST-01, BACKTEST-02, BACKTEST-03, BACKTEST-04
**Success Criteria** (what must be TRUE):
1. New `backtest/` module — pure compute, hex-boundary respected (no `state_manager`, no `notifier`, no I/O outside its own bound CLI entry)
2. Walks 5y of OHLCV per instrument from yfinance, applies live `signal_engine.compute_indicators` + `get_signal`, simulates open/close per signal change with trailing stops + pyramid rules from `sizing_engine`
3. Aggregates per-instrument and combined: cumulative return %, Sharpe (daily), max drawdown, win rate, expectancy, total trades
4. `/backtest` route renders equity curve (Chart.js, same lib as Phase 5 dashboard), metrics table, **pass/fail badge** (`PASS` if cumulative return > 100%, `FAIL` otherwise)
5. CLI: `python -m backtest --years 5` re-runs the backtest, prints summary, persists JSON to `.planning/backtests/<strategy_version>-<timestamp>.json`
6. Result tagged with `strategy_version` from VERSION-01; multiple backtest runs across versions visible in `/backtest?history=true` view

**Plans:** 7/7 plans complete

Plans:
- [x] 23-01-wave0-scaffolding-PLAN.md — Wave 0 scaffolding: pyarrow pin, backtest/ skeleton, AST guard extension, golden fixture, test skeletons
- [x] 23-02-data-fetcher-PLAN.md — Wave 1A backtest/data_fetcher.py (yfinance + parquet cache + <5y bail)
- [x] 23-03-simulator-PLAN.md — Wave 1B backtest/simulator.py (bar-by-bar replay reusing signal_engine + sizing_engine)
- [x] 23-04-metrics-PLAN.md — Wave 1C backtest/metrics.py (Sharpe / max DD / win rate / expectancy / cum return)
- [x] 23-05-render-PLAN.md — Wave 2A backtest/render.py (3-tab HTML report + history + override form)
- [x] 23-06-cli-PLAN.md — Wave 2B backtest/cli.py (argparse + JSON write + exit codes + log lines)
- [x] 23-07-web-routes-PLAN.md — Wave 2C web/routes/backtest.py (4 routes + path-traversal + cookie auth)


## Phase Dependencies (build order)

```
                  Wave 1 (parallel)
                  ┌────────────┐  ┌────────────┐
                  │ Phase 17   │  │ Phase 22   │
                  │ TRACE      │  │ VERSION    │
                  └─────┬──────┘  └─────┬──────┘
                        │               │
                        │   Wave 2     │
                        │   ┌──────────▼─┐
                        │   │ Phase 19   │
                        │   │ LEDGER     │
                        │   └─────┬──────┘
                        │         │
                        │   Wave 3│
                        │   ┌─────▼──────┐
                        │   │ Phase 20   │
                        │   │ ALERT      │
                        │   └────────────┘
                        │
                        │   Wave 4 (depends on 22)
                        │   ┌────────────┐
                        └──>│ Phase 23   │
                            │ BACKTEST   │
                            └────────────┘
```

**Wave 1 (parallel):** Phase 17 (TRACE) + Phase 22 (VERSION). Disjoint files (Phase 17 = dashboard.py + indicator-trace; Phase 22 = system_params.py + state_manager.py migration). Can land same day.

**Wave 2:** Phase 19 (LEDGER). Needs `STRATEGY_VERSION` constant from Phase 22 to stamp paper trade rows. Touches state.json schema (add `paper_trades` array).

**Wave 3:** Phase 20 (ALERT). Needs `paper_trades` schema from Phase 19 (specifically `stop_price` + `last_alert_state` fields).

**Wave 4 (parallel with Wave 2/3 from Phase 22 onwards):** Phase 23 (BACKTEST). Needs `STRATEGY_VERSION` for tagging; otherwise standalone (own `backtest/` module). Largest single phase — likely the longest in v1.2.

## Progress

[░░░░░░░░░░░░░░░░] 0% (0/5 phases complete)

## Coverage Validation

| REQ-ID | Phase | Mapped |
|--------|-------|--------|
| TRACE-01..05 | 17 | ✓ (5/5) |
| LEDGER-01..06 | 19 | ✓ (6/6) |
| ALERT-01..04 | 20 | ✓ (4/4) |
| VERSION-01..03 | 22 | ✓ (3/3) |
| BACKTEST-01..04 | 23 | ✓ (4/4) |

**Total:** 22/22 mapped, 0 orphans, 0 duplicates.

## Operator Decisions Baked In (v1.2)

- **D-01:** Skip Phase 18 multi-user — single-operator model from v1.1 sufficient through v1.2; revisit at v1.3 if friends-and-family demand emerges.
- **D-02:** Skip Phase 21 news integration — defer to v1.3+ as supplemental feature; operator focus stays on calc transparency + measurement.
- **D-03:** Skip Phase 23.5 hygiene — defer to v1.3+ when v1.2 functional surface stabilizes; current backup story (git-tracked state.json + droplet snapshot) acceptable.
- **D-04:** Backtest pass criterion = `cumulative return > 100% over 5y` — strict ledger-style threshold per SPEC.md operator brainstorm 2026-04-29; Sharpe / drawdown / win rate displayed but not gating.
- **D-05:** `STRATEGY_VERSION` semver — bumped on signal-logic change only (Mom thresholds, ADX gate, sizing weights). Bumped to `v1.2.0` at v1.2 launch.

## Carried-Forward Operator Decisions from v1.0/v1.1

- **Signal-only.** No broker API, ever (hard constraint).
- **Daily cadence only.** No intraday data; stop-loss alerts fire on next daily run.
- **Python.** Locked.
- **DO droplet hosting.** No serverless, no container orchestration.
- **Hex-boundary architecture.** Pure-math modules cannot import adapters.
- **Atomic state writes.** tempfile + fsync + os.replace, contention-guarded.
- **Email never-crash.** Resend failures logged, never abort daily run.

### Phase 25: Dashboard UI/UX overhaul — true multi-tab market preferences and first-run polish

**Goal:** Trader switches market once and every panel (Signals, Settings, Market Test) reflects that selection across page navs and refreshes; first-run UX shows ~1 empty card, not 11 stacked "n/a" panels; Settings page is scannable, not a wall of inputs; system trust surface (next-run countdown + last-run health) visible above the fold.

**Depends on:** Nothing (UI-only refactor; no signal/state/persistence changes).

**Source:** `/ui-ux-pro-max` review 2026-05-05. All 10 priority items folded into this phase.

**Scope — 10 priority items:**

1. **Two-axis navigation (HEADLINE).** Convert the four anchor-link tabs (`dashboard-signals.html`, `dashboard-account.html`, `dashboard-settings.html`, `dashboard-market-test.html`) into a market-tab strip × function-tab strip. URL pattern: `/markets/<MARKET>/<signals|account|settings|market-test>`. Selected market persists in URL + cookie/localStorage so refresh and tab switch preserve context. `+ Add market` chip beside the market tabs (replaces buried `<a class="btn-row btn-modify" href="#settings-tab">Add market</a>` in `dashboard.html:676`). Account tab is the only market-agnostic function.

2. **Active-tab affordance + a11y.** Style `.tabs a.active` distinctly (currently has no CSS rule — visually identical to inactive); add `aria-current="page"` on the active anchor for SR users; implement WAI-ARIA tabs ←/→ keyboard navigation pattern.

3. **Consolidate the 4 dashboard HTML files.** Today: 4216 LOC across `dashboard.html` (1117), `dashboard-signals.html` (841), `dashboard-account.html` (838), `dashboard-settings.html` (724), `dashboard-market-test.html` (696) — duplicated `<style>`, scripts, header chrome. Target: single htmx-driven shell with `hx-get`+`hx-push-url` panel swaps OR multipage with shared `/static/dashboard.css` + `/static/dashboard.js`. Pick whichever the renderer in `dashboard_renderer/` supports more naturally.

4. **Mobile body font ≥16px.** Current `--fs-body: 14px` (`dashboard.html:76`) triggers iOS auto-zoom on every input focus. Bump body to 16px; rebalance heading/label scale tokens.

5. **First-run empty-state collapse.** Hide the per-instrument trace-indicators tables (`<table class="trace-indicators-table">` × 11 rows of `n/a (need N bars, have 0)`) when there's no data; show ONE onboarding card: "Awaiting first daily run at 08:00 AWST. Calculations and equity curve will populate after the first cycle." Hide the all-zeros stats bar (`dashboard.html:762-769`) until ≥1 trade exists. Hide equity chart until ≥5 distinct points (currently renders a misleading flat line from 3 identical data points at `dashboard.html:837`).

6. **Settings page fieldset grouping + helper text.** Today: 18 numeric inputs in two stacked forms (`dashboard.html:1041-1074`) with no grouping or helper text. Group into `<fieldset>`s: **Entry rules** (ADX gate, momentum votes), **Risk** (long/short ATR stop, long/short risk %, contract cap), **Direction** (mode, 1-contract floor). Add `<small>` helper for each cryptic field (ADX, "Momentum votes", "ATR stop"). On Market Test page, show inherited Settings defaults as `placeholder` on the override fields (currently empty inputs give no hint).

7. **System Status strip in header.** Replace the static `<span class="value">2026-05-04 18:49 AWST</span>` literal (`dashboard.html:658`) with a live status strip: green/amber dot + `<time datetime="…">` last-run timestamp + countdown to next 08:00 AWST cycle + run health (success/failure of latest run). This is the trust surface for a trading product.

8. **Wide-table responsive handling.** Open Positions (9 cols), Closed Trades (7 cols), Trailing Stops (7 cols) overflow on mobile with no handling (single media query at `max-width:600px` in `dashboard.html:645` only adjusts `.stats-bar-item`). Wrap each table in `overflow-x:auto` container; add stacked-row layout under 600px.

9. **Button / eyebrow / terminology consistency.** Add `class="btn-primary"` to paper-trade `<button type="submit">Open position</button>` (`dashboard.html:800`). Rename "Open position" (paper) vs "Open Position" (live) to disambiguate (e.g. "Record paper trade" vs "Open live position"). Pick one term across **Account Management** (tab) / **Account Baseline** (form) / **Account balance** (field) — three names for one concept. Reconcile strategy-version footer: `dashboard-signals.html:837` shows v1.0.0, `dashboard.html:1113` shows v1.1.0 — single source.

10. **Accessibility hardening.** Sync `aria-expanded` with the cookie-driven `details[data-instrument]` toggle state (currently SR users miss state changes). Add visible focus rings to `<summary>` elements (currently only browser default). Add a status dot/glyph beside the FLAT/LONG/SHORT colour-only labels (`dashboard.html:683` etc.) so colourblind users have a non-colour cue. Fix `<select aria-label="Market selection">` (`dashboard.html:672`) — add `id`/`for` pairing to the visible "Market" `<h2>`. Replace inline `style="color:#eab308"` on signal big-labels with `--color-flat` / `--color-long` / `--color-short` tokens.

**Plans:** 10 plans

Plans:
- [x] 25-01-test-scaffolding-PLAN.md — Wave 1: Failing-by-design xfail test classes (14 classes across 3 test files) for every Phase 25 acceptance gate.
- [x] 25-02-renderer-consolidation-PLAN.md — Wave 1: Migrate inline shell constants into shared assets.py + shell.py; create nav.py stubs; bump _REQUIRED_DASHBOARD_MARKER to force regen.
- [x] 25-03-two-axis-nav-PLAN.md — Wave 2: Implement render_function_strip / render_market_strip with WAI-ARIA roving tabindex; thread active_function/active_market through RenderContext.
- [x] 25-04-routes-cookie-PLAN.md — Wave 2: Register GET /markets/{m}/{fn} routes; selected_market cookie write; HX-Request panel-vs-full sniff.
- [x] 25-05-add-market-chip-PLAN.md — Wave 3: Inline-expanding + Add market chip; HX-Trigger markets-changed wiring; remove buried settings-tab link.
- [x] 25-06-status-strip-PLAN.md — Wave 3: render_status_strip with OR-01 status-dot derivation + OR-02 countdown format; /status-strip endpoint; 08:01 AWST refresh timer.
- [x] 25-07-empty-state-collapse-PLAN.md — Wave 3: D-09 first-run onboarding card; D-10 stats-bar gate; D-11 equity chart distinct-tuple gate.
- [x] 25-08-settings-fieldsets-PLAN.md — Wave 3: 3 fieldsets (Entry rules / Risk / Direction) + helper text; Market Test inherited-defaults placeholders.
- [x] 25-09-mobile-a11y-PLAN.md — Wave 4: D-15 font token rebalance; D-19 a11y (signal classes, status dots, focus rings, aria-expanded sync); D-20 wide-table wrappers.
- [x] 25-09b-component-a11y-wiring-PLAN.md — Wave 4: D-19 component wiring — replace inline color styles with semantic classes, wrap wide tables, status-dot glyphs, aria-expanded sync JS, label-for audit.
- [x] 25-10-terminology-version-PLAN.md — Wave 4: D-21 button copy renames + Account terminology unification; D-22 strategy version regen across 5 sibling HTMLs.
- [x] 25-11-gap-closure-PLAN.md — Wave 5: Gap closure — wire D-14 Market Test placeholders + repair 3 D-11-broken tests (XSS defense, copy drift, golden snapshot). 313 pass / 0 fail.

### Phase 26: Phase 25 follow-up — multi-tab market scoping fixes & post-overhaul cleanup

**Goal:** Fix the regressions Phase 25 shipped (multi-tab scoping non-functional, template placeholder leaks → 401 on form submit, broken deploy tests) and clean up the residue (dead code, stale verification doc, leaked artifacts in repo root).

**Depends on:** Nothing (cleanup only; no signal/state/persistence changes).

**Source:** Reviewer-agent pass over `chore/document-nginx-sudoers` branch + main on 2026-05-07. Full evidence in `.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-CONTEXT.md`.

**Scope:**

- **BROKEN (4 items):**
  1. **B1 — Multi-tab scoping ignores `active_market`.** `dashboard.py:1961` `_render_page_body`. Every `/markets/{M}/{fn}` renders every market's panels stacked. Phase 25 headline value prop is non-functional.
  2. **B2 — `{{TEMPLATE}}` placeholders leak in market-scoped routes.** `web/routes/dashboard.py:235-284` `_serve_market_scoped_page` skips substitution. Forms 401 on PATCH because `{{WEB_AUTH_SECRET}}` ships literally to the client.
  3. **B3 — Header session widget shows `{{SIGNOUT_BUTTON}}` / `{{SESSION_NOTE}}`.** `dashboard_renderer/components/header.py:64-69`. `is_cookie_session` not threaded through `render_dashboard_as_str`.
  4. **B4 — 3 deploy tests red.** `tests/test_deploy_sh.py` regex didn't follow the `python -m pip` rewrite from `5716a60`/`d6f760b`.

- **RISKY (7 items):**
  - R1 — Sibling cache invalidation only checks `dashboard.html` (`web/routes/dashboard.py:74,119`).
  - R2 — `render_dashboard()` mixed return type / wrong annotation (`dashboard_renderer/api.py:58-113`); split into two functions.
  - R3 — Cached `render_dashboard_page` never threads `active_market` (`dashboard_renderer/api.py:143-165`); compounds B1.
  - R4 — Dead `nav_mode` param + DEPRECATED `_render_dashboard_page_nav`.
  - R5 — `add_market` writes `signals[id] = 0` — dict-shape mismatch with `run_daily_check`.
  - R6 — `markets-strip` derives active_function from `Referer` (privacy-mode breaks tab highlight).
  - R7 — `selected_market` cookie sanitiser permissive; tighten to `^[A-Z0-9_]{2,20}$` mirror.

- **CLEANUP (5 items):**
  - C1 — Repo root littered with untracked artifacts; **`auth.json` may be real creds — audit + rotate + `.gitignore` first**.
  - C2 — Remove DEPRECATED `_render_dashboard_page_nav` (`dashboard.py:2083`).
  - C3 — Remove dead `_render_market_selector` (`dashboard.py:770`).
  - C4 — Resolve stale `25-VERIFICATION.md` vs `25-11-gap-closure-SUMMARY.md` (says FAILED vs all gaps closed).
  - C5 — `render_dashboard` writes 4 sibling files every regen; consider lazy-regen on page-route hit.

**Acceptance:** All 4 BROKEN fixed with regression tests; RISKY items fixed or explicitly accepted; C1 done; full pytest green; `grep -rn '{{[A-Z_]\+}}' public/ web/ dashboard_renderer/ dashboard.py` zero matches in served HTML.

**Plans:** 8 plans

Plans:
- [ ] 26-01-secret-audit-and-gitignore-PLAN.md - Wave 0: Audit auth.json (real TOTP secret); rotate or accept-as-is; extend .gitignore for OS junk + agent runtime dirs; decide AGENTS.md placement.
- [ ] 26-02-deploy-test-regex-fix-PLAN.md - Wave 1 (parallel with 03): Relax tests/test_deploy_sh.py regex to accept `(?:python -m )?pip install` form (B4).
- [ ] 26-03-failing-test-scaffolding-PLAN.md - Wave 1 (parallel with 02): xfail(strict=True) test classes for B1 (TestPhase26MarketScoping), B2/B3 (TestPhase26PlaceholderLeak / HeaderSessionWidget / PanelPatchSurvives). TDD-style.
- [ ] 26-04-template-substitute-helper-PLAN.md - Wave 2 (depends on 03): Extract _substitute(content, request) helper in web/routes/dashboard.py; both _serve_dashboard_content and _serve_market_scoped_page call it. Closes B2 + B3.
- [ ] 26-05-active-market-scoping-PLAN.md - Wave 2 (depends on 03): Thread ctx.active_market into _render_signal_cards / render_settings_tab / _render_market_test_tab; forward through render_dashboard_page -> _build_render_context. Closes B1 + R3.
- [ ] 26-06-renderer-api-cleanup-PLAN.md - Wave 3 (depends on 04 + 05): Split render_dashboard into render_dashboard_files (None) + render_panel_html (str); drop nav_mode dead param; delete DEPRECATED _render_dashboard_page_nav. Closes R2 + R4 + C2.
- [ ] 26-07-cache-and-cookie-hardening-PLAN.md - Wave 3 (parallel with 06): _is_stale_for per-file (R1); add_market writes dict-shape signal (R5); markets-strip reads active_function from query param (R6); selected_market cookie regex tighten (R7).
- [ ] 26-08-dead-code-and-doc-cleanup-PLAN.md - Wave 4 (depends on 06 + 07): Delete _render_market_selector (C3); resolve 25-VERIFICATION.md staleness (C4); document C5 lazy-regen as v1.3 debt.
