# Phase 26: Phase 25 follow-up — multi-tab market scoping fixes & post-overhaul cleanup - Context

**Gathered:** 2026-05-07
**Status:** Ready for planning
**Source:** Code review of `chore/document-nginx-sudoers` branch + main, post-Phase 25 deploy (2026-05-07).

<domain>
## Phase Boundary

Fix the bugs Phase 25 shipped and clean up the residue. Phase 25's headline value prop ("true multi-tab market preferences") is non-functional in production: every market URL renders every market's panels stacked. Forms posted from market-scoped pages 401 because `{{WEB_AUTH_SECRET}}` placeholders aren't substituted. Three tests are red. Repo root has uncommitted artifacts including a likely-real credential file.

UI-only/server-side fixes against the existing dashboard renderer + web routes. No signal/state/persistence changes. No new features.

</domain>

<scope>
## Scope — Review findings to fix

All items below are concrete findings from the 2026-05-07 reviewer-agent pass over commits `14af40c` (Phase 25), `d982334`, `18ea2c5`, `3bbbca1`, `6017a27`, `5716a60`, `d6f760b`. Each item has reproducible evidence; planner should produce one plan per BROKEN item, group RISKY into 1–2 plans, and one plan for CLEANUP.

### BROKEN (must fix — feature non-functional)

**B1. Multi-tab market scoping doesn't work — Phase 25 headline.**
- File: `dashboard.py:1961` (`_render_page_body`)
- Symptom: `/markets/SPI200/settings`, `/markets/AUDUSD/settings`, `/markets/ESM/settings` all render every market's settings forms stacked. Same for `/signals` and `/market-test`. Confirmed via reviewer Playwright pass: eyebrows = `['SPI 200 SETTINGS', 'AUD / USD SETTINGS', 'ES Mini SETTINGS', …]` for `/markets/ESM/settings`.
- Cause: `_render_page_body` ignores `ctx.active_market`. Per-market loops in `_render_signal_cards`, `render_settings_tab`, `_render_market_test_tab` iterate every market regardless.
- Fix shape: thread `ctx.active_market` into the three render functions and filter the per-market loop.
- Acceptance: each `/markets/{M}/{fn}` page renders only `M`'s panels; tests assert eyebrow text matches the URL.

**B2. Market-scoped routes leak `{{TEMPLATE}}` placeholders → 401 on form submit.**
- File: `web/routes/dashboard.py:235-284` (`_serve_market_scoped_page`)
- Symptom: `/markets/SPI200/signals` HTML contains literal `{{WEB_AUTH_SECRET}}` (×3), `{{SIGNOUT_BUTTON}}` (×1), `{{SESSION_NOTE}}` (×1). HTMX panel swap of `/markets/SPI200/settings` contains `{{WEB_AUTH_SECRET}}` (×3). PATCH from any panel-swapped form sends literal `{{WEB_AUTH_SECRET}}` and gets 401. Header renders raw `{{SIGNOUT_BUTTON}}` text inline.
- Cause: `_serve_market_scoped_page` does `body.encode()` with NO substitution of `{{WEB_AUTH_SECRET}}`, `{{SIGNOUT_BUTTON}}`, `{{SESSION_NOTE}}`, `{{TRACE_OPEN_*}}`.
- Fix shape: extract a shared `_substitute(content: str, request: Request) -> str` helper (called from both `_serve_dashboard_page` and `_serve_market_scoped_page`) that resolves all template tokens including session-state-dependent ones.
- Acceptance: every market-scoped GET response contains zero `{{…}}` markers; PATCH from a panel-swapped form succeeds with 200 (or expected 4xx for validation), never 401-from-placeholder.

**B3. Sign-out vs session-note widget never resolves on multi-tab pages.**
- File: `dashboard_renderer/components/header.py:64-69`
- Symptom: header shows both `{{SIGNOUT_BUTTON}}` and `{{SESSION_NOTE}}` placeholders inline on `/markets/{m}/{fn}` pages.
- Cause: header emits both placeholders when `is_cookie_session is None`; `render_dashboard_as_str` doesn't pass session state from the request, and `_serve_market_scoped_page` doesn't substitute them.
- Fix shape: thread `_is_cookie_session(request)` into `render_dashboard_as_str` so the correct widget is server-rendered, OR resolve via the B2 substitute helper. Pick the most-eloquent option in plan review.
- Acceptance: header shows exactly one of {sign-out button, session note} on every dashboard page, never the placeholder strings.

**B4. 3 deploy tests fail.**
- File: `tests/test_deploy_sh.py`
- Failing tests: `test_step_5_pip_install_requirements_present`, `test_order_pull_before_pip`, `test_order_pip_before_systemctl`
- Symptom: regex looks for `\.venv/bin/pip install -r requirements\.txt` but commits `5716a60` / `d6f760b` rewrote `deploy.sh` to `\.venv/bin/python -m pip install -r requirements.txt` (to bootstrap pip in venvs without `ensurepip`).
- Fix shape: relax regex to accept either form (`\.venv/bin/(?:python -m )?pip install -r requirements\.txt`).
- Acceptance: full pytest suite green.

### RISKY (fragile; confirm or harden)

**R1. Sibling cache invalidation only checks `dashboard.html`.**
- File: `web/routes/dashboard.py:74,119` (`_is_stale`)
- Risk: marker check runs against `dashboard.html` only. Sibling files (`dashboard-signals.html`, `dashboard-account.html`, `dashboard-settings.html`, `dashboard-market-test.html`) only regen on miss or when `dashboard.html` flips marker. If a deploy ships new shell HTML but `dashboard.html` already has the marker, siblings stay stale on disk.
- Fix shape: check the marker on every sibling, OR centralise the marker bump to a single deploy-time invariant.

**R2. `render_dashboard()` mixed return type.**
- File: `dashboard_renderer/api.py:58-113`
- Risk: returns `str` when `htmx_panel_only=True`, else `None`. Annotation says `-> None`. Caller `web/routes/dashboard.py:260` calls `.encode()` assuming str — flag flip silently NPEs.
- Fix shape: split into `render_dashboard_files()` (writes files, returns `None`) and `render_panel_html()` (returns `str`).

**R3. Cached page renderer never threads `active_market`.**
- File: `dashboard_renderer/api.py:143-165` (`render_dashboard_page`)
- Risk: `_build_render_context` called without `active_market` kwarg. Cached `dashboard-signals.html` etc. always default to first-market. Compounds B1.
- Fix shape: drop on-disk cache for market-scoped pages OR include `active_market` in cache key.

**R4. `nav_mode` parameter is dead code.**
- File: `dashboard.py:2050` (`_render_single_page_dashboard`), `dashboard_renderer/api.py:110`, `dashboard.py:2083` (`_render_dashboard_page_nav` — DEPRECATED)
- Risk: misleading; refactor pitfall.
- Fix shape: remove parameter and DEPRECATED function, OR wire it.

**R5. `add_market` writes `signals[id] = 0`.**
- File: `web/routes/markets.py:158`
- Risk: dict-shape mismatch with `main.run_daily_check` writes (`{signal, signal_as_of, …}`). New market shows "Signal as of never" until first scheduler tick. Renderer is defensive (`signals.py:35` int branch) but the divergence is bug-bait.
- Fix shape: write the same dict shape as `run_daily_check`, OR document the intentional sentinel and tighten the renderer's defensive branch.

**R6. `markets-strip` derives `active_function` from `Referer`.**
- File: `web/routes/dashboard.py:341-346`
- Risk: privacy-mode browsers strip Referer → tab strip rebuilds with wrong tab highlighted. Visual only, low impact.
- Fix shape: pass `active_function` as query/header param on the `hx-get`, OR derive from a hidden form field.

**R7. `selected_market` cookie sanitiser is permissive.**
- File: `web/routes/dashboard.py:228-233`
- Risk: strips `"` and `;` only. `market_id` is regex-validated upstream by Pydantic, but defense-in-depth on a server-set cookie should also reject whitespace and control chars.
- Fix shape: tighten regex on the read path to `^[A-Z0-9_]{2,20}$` mirror.

### CLEANUP

**C1. Repo root littered with untracked artifacts — `auth.json` may be a real secret.**
- Files (from `git status`): `.DS_Store`, `._debug_new_dashboard.html`, `.agents/`, `.claude-flow/`, `.codex/`, `.cowork/`, `.cursor/`, `.mcp.json`, `.playwright-mcp/`, `auth.json`, `last_email.html`, `state.json`, `backtest/.DS_Store`, `AGENTS.md`
- Action:
  1. Inspect `auth.json` — if it contains real credentials, rotate the secret and remove from disk; verify it never landed in a commit.
  2. Add the rest to `.gitignore`.
  3. Decide per-file: `state.json` is runtime data (gitignore), `AGENTS.md` is documentation (commit or move to `.planning/`), `last_email.html` is a debug artefact (gitignore).

**C2. Dead `_render_dashboard_page_nav`** at `dashboard.py:2083` — marked DEPRECATED in Phase 25 Plan 09; final removal pending.

**C3. Dead `_render_market_selector`** at `dashboard.py:770` — replaced by tab strip per D-19 #4 in Phase 25; remove and audit callers.

**C4. `25-VERIFICATION.md` stale** — says `D-14: FAILED` / `status: gaps_found`, but `25-11-gap-closure-SUMMARY.md` says all 4 gaps closed. Re-verify or supersede with a closing note.

**C5. `render_dashboard` writes 4 sibling files on every regen** — even when only `dashboard.html` was the trigger. ~5x I/O per state mutation. Optional: lazy-regen siblings on page-route hit (already half-implemented in `_serve_dashboard_page`).

</scope>

<acceptance>
## Phase Acceptance Criteria

1. All four BROKEN items (B1–B4) fixed with regression tests.
2. RISKY items (R1–R7) either fixed or explicitly accepted with rationale recorded in plan SUMMARY.
3. CLEANUP item C1 (`auth.json` audit + `.gitignore`) completed; remaining cleanup items addressed or deferred to a tracked debt list.
4. `pytest` full suite green (currently 3 red from B4).
5. Manual smoke (or Playwright) confirms `/markets/{M}/{fn}` for each market renders only that market's panels and that PATCH from a panel-swapped form succeeds.
6. `grep -rn '{{[A-Z_]\+}}' public/ web/ dashboard_renderer/ dashboard.py` returns zero matches in served HTML.
</acceptance>

<dependencies>
## Depends On

Nothing. Cleanup of Phase 25 only — no signal/state/persistence changes, no new external systems.
</dependencies>

<non_goals>
## Non-Goals

- No new features, no new endpoints (except a possible `_substitute` helper internal to the route module).
- No re-architecture of the dashboard renderer pipeline (R2 split is the largest scoped change; anything bigger gets deferred to a v1.3 phase).
- No copy or design changes to the multi-tab UX itself; Phase 25 design contract stands.
</non_goals>
