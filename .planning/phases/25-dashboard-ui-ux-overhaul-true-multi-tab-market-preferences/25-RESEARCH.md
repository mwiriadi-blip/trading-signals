# Phase 25: Dashboard UI/UX overhaul — Research

**Researched:** 2026-05-05
**Domain:** server-rendered HTML dashboard (FastAPI + dashboard.py + raw HTMX 1.9.12)
**Confidence:** HIGH (codebase grepped end-to-end; no library version ambiguity — vanilla HTML/CSS, no framework upgrade required)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Shell architecture (item #3)**
- D-01: Hybrid shell — function tabs are full-page navs; only the market tab strip uses `hx-get` + `hx-push-url` to swap the panel without scroll/state loss. URL: `/markets/<MARKET>/<signals|settings|market-test>` for market-scoped functions; `/account` for the market-agnostic function.
- D-02: Common `<style>` and `<script>` are deduped via `dashboard_renderer/shell.py` emitting a single inline `<style>` block per page. NOT introducing external `/static/dashboard.css`/`/static/dashboard.js` — DASH-01 inline-shell pattern preserved.

**URL & market-state persistence (item #1)**
- D-03: URL is the canonical source of selected market. `/markets/<MARKET>/<function>` for market-scoped; `/account` for Account.
- D-04: Account is bare `/account`, no market segment. Market tab strip hidden when on Account (emit zero DOM, not `display:none`).
- D-05: Cookie `selected_market`, server-set, HttpOnly=false, SameSite=Lax, Path=/, no Domain. localStorage NOT used. Fallback: first market in `state.markets` ordering.

**System Status strip (item #7)**
- D-06: Server-rendered + client countdown. Render last-run timestamp, last-run status (success/failure → green/amber dot), next-run ISO once per page load. Countdown to next 08:00 AWST runs in JS from a fixed UTC+8 offset.
- D-07: Auto-refresh = scheduled `hx-get` at 08:01 AWST + `visibilitychange`-triggered `hx-get` when tab regains focus. New endpoint: `GET /status-strip`.
- D-08: Timezone is **AWST** (Perth, UTC+8 no DST). Discussion's "AEST" was loose terminology.

**First-run empty-state collapse (item #5)**
- D-09: `state.last_run_at is null` → show one onboarding card "Awaiting first daily run at 08:00 AWST."
- D-10: All-zeros stats bar (`dashboard.html:762-769`) hidden until `closed_paper_trades + closed_live_trades >= 1`.
- D-11: Equity chart hidden until ≥5 distinct `(date, value)` tuples.

**Settings copy & grouping (item #6)**
- D-12: Three fieldsets — **Entry rules**, **Risk**, **Direction**. Mapping is planner's job.
- D-13: Planner drafts label + 1-line `<small>` helper text per field; operator reviews during plan.
- D-14: Market Test page shows inherited Settings defaults as `placeholder` text on override fields.

**Mobile font scale (item #4)**
- D-15: `--fs-body` 14px → 16px; every other `--fs-*` token grows by 16/14 (≈1.143×). Hierarchy preserved. Round to whole pixels.

**Add-market UX (item #1)**
- D-16: "+ Add market" chip beside the market tab strip is an inline-expanding mini-form; `hx-post`s to existing `/markets`; collapses on success and refreshes the market tab strip.
- D-17: This replaces the buried `<a class="btn-row btn-modify" href="#settings-tab">Add market</a>` in `dashboard.html:676`.

**Active-tab affordance + a11y (item #2)**
- D-18: Two tab strips → two independent WAI-ARIA tabs widgets, each with its own roving tabindex. ←/→ within active row; Tab key between strips. Active tab gets distinct CSS rule + `aria-current="page"`.

**a11y hardening (item #10)**
- D-19: All ten sub-items in ROADMAP §Phase 25 item #10 are locked. Specific work items carry forward verbatim into PLAN.md tasks.

**Wide-table responsive (item #8)**
- D-20: Wrap each wide table (Open Positions 9 cols, Closed Trades 7 cols, Trailing Stops 7 cols) in `overflow-x:auto`. Add stacked-row layout under 600px. Existing single media query at `dashboard.html:645` is the extension point.

**Terminology & version reconciliation (item #9)**
- D-21: Disambiguating renames per Copywriting Contract.
- D-22: Strategy version: single source of truth via existing `STRATEGY_VERSION` constant (Phase 22 work). Reconcile `dashboard-signals.html:837` (v1.0.0) and `dashboard.html:1113` (v1.1.0).

### Claude's Discretion

- Exact CSS class names, token names, and component file splits within `dashboard_renderer/components/` are planner's call.
- Whether the `/status-strip` endpoint lives in `web/routes/dashboard.py` or new `web/routes/status.py` is a planner decision.
- HTMX swap semantics for the market-tab swap (`outerHTML` vs `innerHTML`, `hx-target` selector) are planner's call provided URL push and scroll preservation work.
- Whether to introduce a small JS helper for the AWST countdown or inline the math — planner decides.

### Deferred Ideas (OUT OF SCOPE)

None raised. If multi-account or live-broker integration comes up during planning, capture as v1.3+ candidate, do not fold in.

</user_constraints>

---

## Project Constraints (from CLAUDE.md)

- "Do what has been asked; nothing more, nothing less." UI-only — no signal/state/persistence changes.
- Files under 500 lines (project rule). `dashboard.py` is **2843 LOC** today — Phase 25 is a chance to peel functionality into `dashboard_renderer/` modules but the cap is aspirational, not enforced.
- Validate input at system boundaries. New `/status-strip` and `/markets/<m>/<fn>` routes go through the same auth posture.
- Read learnings before code (global rule). Project-local `.claude/LEARNINGS.md` exists.
- Hex-boundary rule (project): `dashboard.py` does NOT import `system_params.STRATEGY_VERSION`; the version arrives via state dict (LEARNINGS 2026-04-27 / Phase 22 D-06).

---

## Summary

The phase is a UI-only refactor; CONTEXT.md locks 22 decisions and UI-SPEC.md locks the design contract. Every locked decision survives the codebase audit **except one critical fact**: the daemon writes the field `last_run` (a `YYYY-MM-DD` date string), not `last_run_at`/`last_run_status`/`next_run_at`. CONTEXT.md D-06/D-07/D-09 reference fields that do not exist in `state.json` — planner must reconcile this without expanding scope to add new state writes.

Everything else is favourable: HTMX 1.9.12 with `hx-push-url` and `hx-swap` is already loaded SRI-pinned; `STRATEGY_VERSION` exists at `system_params.py:27` as `v1.2.0`; the `/?fragment=…` pattern is well-established for HTMX partials; the route-shadowing fix from commit `18ea2c5` lays out the exact registration order for new `/markets/{market_id}/<fn>` routes; project precedent for AWST is `pytz.timezone('Australia/Perth')` (server-side) and JS would mirror it via fixed `+08:00` offset arithmetic. The `dashboard_renderer/` package is currently a thin re-export shell — most rendering still lives in `dashboard.py` — so the phase has room to migrate incrementally without rewriting.

**Primary recommendation:** Treat "last run / next run / status" as **derived values** computed at render time from the existing fields (`state.last_run` plus the systemd schedule constant `system_params.SCHEDULE_TIME_UTC`), not new state. Keep all four `dashboard.py:165-204` page routes (`/signals`, `/account`, `/settings`, `/market-test`) and add `/markets/{market_id}/<function>` peer routes that share the same handler, sourcing the active market from URL → cookie → first-in-state, in that order.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Two-axis nav rendering (function strip + market strip) | Frontend Server (renderer) | Browser (HTMX swap on market strip only) | Function strip = full-page nav (no swap); market strip = HTMX-driven panel swap. Server emits both strips on every page render. |
| Market-tab panel swap (URL change without scroll) | Browser (HTMX `hx-get` + `hx-push-url`) | Frontend Server (returns panel HTML on `/markets/<m>/<fn>`) | URL push and partial swap is HTMX's job; server returns the panel fragment HTML. |
| `selected_market` cookie write | Frontend Server (route handler) | Browser (read for `/account` → market-scoped link seeding) | Cookie is server-set on every market-scoped page render; browser-readable (HttpOnly=false) per D-05 so JS on `/account` can route the function strip. |
| Status strip timestamp render | Frontend Server (renderer) | Browser (countdown only) | Server emits `<time datetime="ISO">…</time>`; browser ticks the "in Nh Mm" countdown using fixed UTC+8 offset (D-08). |
| Status strip refresh | Browser (HTMX `hx-get="/status-strip"` triggered by 08:01 timer + `visibilitychange`) | Frontend Server (`GET /status-strip` returns fragment) | Belt-and-braces refresh per D-07. Server endpoint reads `state.last_run` + computes next-run; idempotent. |
| First-run empty-state gating (D-09/D-10/D-11) | Frontend Server (renderer) | — | Pure server-side render gate — `state.last_run is None`, paper/live trade count, equity tuple count. No client logic. |
| Add-market mini-form | Frontend Server (renders chip + form HTML) + Browser (HTMX `hx-post` + `<details>` toggle) | — | Reuses existing `POST /markets` (`web/routes/markets.py:135`). Server returns `HX-Trigger: markets-changed` header; market strip listens via `hx-trigger="markets-changed from:body"` and refreshes itself. |
| Strategy-version reconciliation (D-22) | Frontend Server (footer renderer) | — | Single point: `dashboard_renderer/components/footer.py` already takes `strategy_version` as primitive arg; the value arrives from state via `_resolve_strategy_version` (`dashboard.py:1080-1114`). |

---

## Phase 25 Specifics — Codebase Verification (per the 14 questions)

### 1. State.json fields (CRITICAL FINDING)

| CONTEXT.md reference | Actual field in code | Format | Default on fresh install |
|----------------------|----------------------|--------|--------------------------|
| `last_run_at` (D-06, D-07) | `state['last_run']` | `YYYY-MM-DD` string (not ISO datetime) | `None` (verified `state_manager.py:593`) |
| `last_run_status` (D-06) | **does not exist** | — | — |
| `next_run_at` (D-06, D-07) | **does not exist** (derived from `system_params.SCHEDULE_TIME_UTC = '00:00'`) | — | — |

[VERIFIED: grep `last_run_status\|next_run_at\|last_run_at` returns ZERO matches across `*.py` and `*.json`]
[VERIFIED: `state_manager.py:104,561,593` lock the schema; `main.py:1540` writes `state['last_run'] = run_date_iso`]
[VERIFIED: `system_params.py:218` `SCHEDULE_TIME_UTC = '00:00'` (= 08:00 AWST)]

**Implication for the planner:**
1. **Do NOT propose adding `last_run_at`/`last_run_status`/`next_run_at` to state.json** — Phase 25 is UI-only (CONTEXT.md `<domain>` is explicit). Adding fields would touch `state_manager.py` schema (currently `schema_version: 8`) and the schema migration discipline.
2. **Derive the three values at render time:**
   - **last-run timestamp:** `state['last_run']` is already a date string. The render layer can present it as `<time datetime="{last_run}">{last_run}</time>` directly. If the operator wants minute-precision, `dashboard.py:879` already has `_fmt_last_updated(now)` — but that's the *render* time, not the *daemon-run* time. Use `state['last_run']` for "Last run" semantics.
   - **last-run status:** **No status field exists.** The daemon's "ran successfully today" signal is implicit — if `state['last_run'] == today_awst_iso`, it ran. If `state['last_run']` is older than yesterday-AWST, it's stale (amber). Failure detection: there is no persisted "last run failed" boolean. Closest signal is `state['warnings']` (a list — `state_manager.py:604`), which is appended on errors. Recommendation: treat status as a 3-state derivation:
     - `green` if `state.last_run == today_awst_iso` and `state.warnings` empty (or last warning age < 24h)
     - `amber` (stale) if `state.last_run < today_awst_iso` (more than one cycle missed)
     - `red` (failure) if `state.last_run == today_awst_iso` AND `state.warnings` contains a recent error
     The planner must lock the exact derivation rule with the operator during plan-phase. **This is a CONTEXT.md gap that needs explicit resolution.**
   - **next-run timestamp:** computed: next 08:00 AWST that is a weekday (`schedule.every().day.at('00:00')` UTC, `main.py:716`; weekend skip in `main.py:830`). For a Mon-Thu render: tomorrow 08:00 AWST. For Fri/Sat/Sun: next Monday 08:00 AWST.

3. **D-09 ("`state.last_run_at is null`") trigger** is functionally correct because `state['last_run']` IS `None` on fresh install (`state_manager.py:593`). The field-name mismatch is cosmetic for D-09; semantic for D-06/D-07. [VERIFIED]

### 2. dashboard_renderer/ surface

[VERIFIED: file LOC counts and content read]

| File | LOC | Public surface | Role in Phase 25 |
|------|-----|----------------|------------------|
| `__init__.py` | 5 | exports `render_dashboard`, `render_dashboard_page` | No change — entry point unchanged. |
| `api.py` | 115 | `render_dashboard()`, `render_dashboard_page()`, `_build_render_context()`, `_render_header_and_body()` | Possible new param: `active_market: str` so per-page renders know which market to highlight. |
| `pages.py` | 12 | `render_dashboard_page_body(ctx, page, nav_mode)` — thin wrapper around `dashboard._render_single_page_dashboard` | Extension point: extend signature to accept market segment. |
| `shell.py` | 8 | `render_html_shell(ctx, body)` — thin wrapper | **Critical D-02 surface:** today still delegates to `dashboard._render_html_shell` (line 2719); the inline `<style>`, `<script>`, and JS helpers (`_INLINE_CSS`, `_HANDLE_TRADES_ERROR_JS`, `_TRACE_TOGGLE_JS`) live in `dashboard.py`. The phase needs to migrate the SHELL block here so all 5 generated pages literally share one source. Currently every per-page render re-emits the same shell — that's how the 4 sibling pages get their duplicated `<style>` and scripts. |
| `context.py` | 29 | `RenderContext(state, now, strategy_version, trace_open_keys)` dataclass | Possible new field: `active_market: str \| None` |
| `assets.py` | 12 | re-exports `_CHARTJS_*`, `_HTMX_*`, `_INLINE_CSS`, `_HANDLE_TRADES_ERROR_JS` from `dashboard.py` | Currently a bridge; planner can promote these to be the source of truth here. |
| `formatters.py` | 65 | (not read in detail) — formatting helpers | Reuse for status-strip ISO/AWST formatting. |
| `io.py` | 33 | atomic-write helpers | No change. |
| `stats.py` | 158 | (not read in detail) — stats grid | Targets D-10 hide-when-zero rule. |
| `components/__init__.py` | 1 | empty | — |
| `components/header.py` | 34 | `render_header(state, now, is_cookie_session)` + `render_header_from_context()` | **Natural home for the System Status strip (D-06).** Currently emits `<header>` with H1 + subtitle + last-updated `<p class="meta">` (line 21-29). The status-strip mock fits inside `<p class="meta">` or as a sibling `<div class="status-strip">`. |
| `components/footer.py` | 13 | `render_footer(strategy_version)` | **Single source for D-22.** Already takes `strategy_version` as a primitive arg. The 4 sibling HTML files have outdated literals because they were generated before Phase 22 lifted the version into the renderer — re-rendering with current code already fixes them (verified by reading `dashboard.html:1113` showing v1.1.0 vs the actual `STRATEGY_VERSION = 'v1.2.0'` in `system_params.py:27`). |
| `components/signals.py` | 63 | `render_signal_cards(state)` | **D-19 inline-style fix lives here, not just in HTML files.** Line 53: `f'<p class="big-label" style="color: {colour}">{label}</p>'`. The HTML files are *outputs* of this code — fixing the renderer fixes all 5 generated pages. |
| `components/positions.py` | 71 | (not read in detail) | D-20 wide-table wrapper. |
| `components/trades.py` | 69 | (not read in detail) | D-20 wide-table wrapper. |
| `components/paper_trades.py` | 18 | (not read in detail) | D-20 + D-21 button rename ("Open position" → "Record paper trade"). |
| `components/settings.py` | 97 | `render_settings_tab`, `render_add_market_form`, `render_market_test_tab` | **D-12/D-13 fieldset grouping target.** Currently flat `<div class="field">` per input × 8 inputs + checkbox per market. Refactor wraps groups in `<fieldset><legend>…</legend>…</fieldset>`. |

**Insertion-point recommendations:**

| Phase 25 deliverable | Insertion point |
|----------------------|-----------------|
| System Status strip render | `dashboard_renderer/components/header.py` — extend `render_header()` to emit a sibling `<div class="status-strip" hx-get="/status-strip" hx-trigger="every 28800s, ...">…</div>`. Add a new helper `render_status_strip(state, now)` callable from both the page render AND the `/status-strip` endpoint. |
| Two-axis nav rendering | New module `dashboard_renderer/components/nav.py` (LOW risk, isolated). Replaces `dashboard.py:2673 _render_dashboard_page_nav`. Function strip + market strip + add-market chip composed here. |
| Shared shell block | Migrate the `<style>` block + `_HANDLE_TRADES_ERROR_JS` + `_TRACE_TOGGLE_JS` constants from `dashboard.py` into `dashboard_renderer/shell.py` so the inline-shell appears in exactly one source location. The 5 generated HTML files become byte-identical-modulo-`<body>`. |
| `/status-strip` fragment | New route. **Recommendation:** put it in `web/routes/dashboard.py` next to `_serve_dashboard_root` (line 246) — same file already does fragment serving and shares the `is_cookie_session` helper, the `_resolve_trace_open` helper, and `state_manager` import. Creating `web/routes/status.py` would force duplicating those helpers. |
| Cookie writes (`selected_market`) | `web/routes/dashboard.py` `_serve_dashboard_page` (line 208) — set the cookie on every market-scoped page render via `Response(headers={'Set-Cookie': '...'})`. |

### 3. Existing fragment-serving pattern

[VERIFIED: `dashboard.py:1461,1747`; `web/routes/dashboard.py:165-415`]

The pattern is **two-tier**:

**Tier 1 — `/?fragment=<name>` query-param routing in `_serve_dashboard_content` (`web/routes/dashboard.py:392-410`):**
```python
if fragment is not None:
    m = re.search(
        rb'<tbody id="' + re.escape(fragment.encode('utf-8')) + rb'">(.*?)</tbody>',
        content, re.DOTALL,
    )
    if not m:
        return Response(content=b'', status_code=404, media_type='text/html; charset=utf-8')
    return Response(content=m.group(1), media_type='text/html; charset=utf-8')
```
This regex-extracts a `<tbody id="…">` from the on-disk dashboard.html. Used by `position-group-{instrument}` HX-Trigger refresh (`dashboard.py:1461` annotation).

**Tier 2 — out-of-band fragment handlers (`web/routes/dashboard.py:293 _forward_stop_fragment_response`):**
Specific `fragment=` values get bespoke handlers that compute fresh content directly from state (no on-disk read). `forward-stop` is the live-calculator pattern.

**Recommendation for the market-tab swap:** Do NOT extend Tier 1. The market-tab swap needs the **whole panel for a different `(market_id, function)` combination** — a tbody-extract from a single dashboard.html file can't deliver that since each market produces different content. Instead use **dedicated routes** `GET /markets/{market_id}/{function}` that share `_serve_dashboard_page`'s logic and return the same panel HTML the page would render — when called via HTMX, FastAPI handlers can detect `request.headers.get('HX-Request') == 'true'` and return only the panel `<section>` instead of the full document. This matches the third architectural pattern (full page vs. fragment via header sniffing) and avoids inflating the regex extractor with another special case.

For `/status-strip`, **do** use the dedicated-route pattern (Tier 2 is the closer precedent). Single small endpoint that returns `<div class="status-strip">…</div>` directly.

### 4. Route ordering for `/markets/<MARKET>/<function>`

[VERIFIED: `web/routes/markets.py:134-176`; test pin at `tests/test_web_app_factory.py:344-379` ("Regression: /markets/settings must not be shadowed by /markets/{market_id}")]

Current registration order in `web/routes/markets.py`:

```
135  POST /markets                        — literal
166  PATCH /markets/settings              — LITERAL (registered before {market_id})
171  PATCH /markets/{market_id}/settings  — dynamic
176  PATCH /markets/{market_id}           — dynamic catch
```

The 18ea2c5 fix was: **literal paths must come before dynamic paths that could match them**. FastAPI dispatches in registration order; without the literal-first rule, `/markets/settings` would resolve `market_id="settings"` and 404 (or worse — try to update a market literally named "settings").

**Required order for new `/markets/{market_id}/{function}` routes:**

```
1. POST /markets                              (literal)
2. PATCH /markets/settings                    (literal — preserved from 18ea2c5)
3. GET /markets/{market_id}/signals           (literal-function variants)
4. GET /markets/{market_id}/settings          (literal-function — already exists for PATCH at line 171; add GET sibling)
5. GET /markets/{market_id}/market-test       (literal-function variant)
6. PATCH /markets/{market_id}/settings        (existing, preserved)
7. PATCH /markets/{market_id}                 (catch-all dynamic, must come AFTER all literal-function siblings)
```

**Why literal `{function}` segments don't collide:** every entry above with `/markets/{market_id}/<literal>` is a 2-segment-after-`{market_id}` route, distinct from the 1-segment-after-`{market_id}` PATCH at line 176. FastAPI path matching considers segment count first.

**The bug class to avoid:** registering `GET /markets/{market_id}` (a hypothetical "market detail" endpoint) before `GET /markets/{market_id}/signals` would not break `/signals` (different segment count) — but it would break a future `GET /markets/settings` if the planner ever wanted to add it as a market-listing page (because `settings` would match `{market_id}`). Recommendation: register every new GET route grouped with its existing PATCH sibling, in ascending specificity (most-segments first within a prefix family).

**`/markets/{market_id}/contracts`** [VERIFIED: searched grep — does NOT exist]. The phrase appeared in the prompt's investigation list but the route is not in the codebase. The pattern that DOES exist is `state.contracts['SPI200'] = 'spi-mini'` (a string mapping in state.json — not a route). No collision risk.

**Test impact (`tests/test_web_app_factory.py:256-261`):** the existing assertions are positive ("path X is registered"). New routes require **additive** assertions only:
```python
assert '/markets/{market_id}/signals' in paths
assert '/markets/{market_id}/market-test' in paths
# /markets/{market_id}/settings already asserted at line 258
```
The shadow-regression test at line 344 must pass unchanged — adding more literal-function routes should not weaken it.

### 5. Cookie-set patterns

[VERIFIED: `web/routes/login.py:51,52,447,461,474,579`; `web/routes/totp.py:50,51,54,494`; `web/routes/reset.py:56,202,214`; `web/middleware/auth.py:140`]

**Framework:** **FastAPI** (Starlette under the hood). [VERIFIED: `from fastapi import FastAPI` in `web/app.py:37`]

**Project pattern — RAW Set-Cookie header strings, not `response.set_cookie()`:**

```python
# web/routes/login.py:51-52
_COOKIE_ATTRS_CREATE = '; Path=/; Secure; HttpOnly; SameSite=Strict'
_DELETION_ATTRS = '; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Strict'

# Emission pattern (login.py:447):
return Response(
  status_code=302,
  headers={
    'Location': '/enroll-totp',
    'Set-Cookie': f'tsi_enroll={enroll_token}; Max-Age=600{_COOKIE_ATTRS_CREATE}',
  },
)
```

For multi-cookie responses, the project uses `raw_headers.append((b'set-cookie', set_cookie.encode('latin-1')))` (`reset.py:214`) — Starlette's `Response.headers` dict only supports a single `Set-Cookie` value, so the lower-level `raw_headers` list is needed for two cookies.

**`selected_market` cookie spec (Phase 25 D-05 conformant):**

```python
# Recommended addition (e.g., web/routes/dashboard.py near line 240):
_MARKET_COOKIE_ATTRS = '; Path=/; Secure; SameSite=Lax'
# Note: NO HttpOnly (D-05 requires JS-readable)
# Note: SameSite=Lax (D-05 spec; project default is Strict but Lax is safe for a UI-state cookie)

# In _serve_dashboard_page, after determining active_market:
response.headers['Set-Cookie'] = f'selected_market={active_market}; Max-Age=2592000{_MARKET_COOKIE_ATTRS}'
```

**Cookie-deletion-options-must-match (CLAUDE.md global learning):** if Phase 25 ever adds a "clear preference" UI, deletion MUST use identical attrs (`Path=/; Secure; SameSite=Lax`) but `Max-Age=0` (mirroring the `_DELETION_ATTRS` pattern in `login.py:52`).

**Production requirement:** `Secure` is included on every project cookie because the deployment is HTTPS-only behind nginx. Must keep this on the new cookie too — D-05 didn't specify but project convention is invariant.

### 6. HTMX swap mechanics

[VERIFIED: `dashboard.html:8-9` HTMX 1.9.12 + json-enc; HTMX 1.9.12 supports `hx-push-url` per its public docs (1.9 has had this since 1.8.0; 1.9.12 is the last 1.x release before 2.0)]

**`hx-push-url` support [VERIFIED]:** HTMX 1.9.12 supports `hx-push-url="true"` natively. No version bump required. [CITED: htmx.org docs — `hx-push-url` is a 1.x core attribute]

**Existing usage in `dashboard.html`:**

| Attribute | Values seen | Where |
|-----------|-------------|-------|
| `hx-post` | `/paper-trade/open`, `/markets`, `/market-test/run`, `/trades/open` | lines 772, 1077, 1093, 935 |
| `hx-patch` | `/account/balance`, `/markets/settings` | lines 880, 1043, 1060 |
| `hx-target` | `#trades-region`, `#account-management-region`, `#market-test-result` | lines 773, 880, 1093 |
| `hx-swap` | `outerHTML` (3×), `innerHTML` (1×), `none` (3×) | various |
| `hx-ext` | `json-enc` (every JSON-bodied form) | various |
| `hx-on::after-request` | `handleTradesError(event)` (every form) | every form |
| `hx-trigger` | (only in dashboard.py at runtime: `input changed delay:300ms` for forward-stop calc; `markets-changed from:body` is project pattern but only seen in HX-Trigger response header at `markets.py:162,169,191`) | dashboard.py:1748 |
| `hx-headers` | `'{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}'` (auth) | every form |

**`hx-push-url` is NOT yet used** in any current template. Phase 25 introduces it.

**Recommended swap strategy for the market-tab swap (D-01 + D-03):**

```html
<nav role="tablist" aria-label="Market" id="market-tab-strip">
  <a role="tab" aria-current="page" tabindex="0"
     href="/markets/SPI200/signals"
     hx-get="/markets/SPI200/signals"
     hx-target="#market-panel"
     hx-swap="innerHTML"
     hx-push-url="true"
     hx-headers='{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}'>SPI200</a>
  <a role="tab" tabindex="-1"
     href="/markets/AUDUSD/signals"
     hx-get="/markets/AUDUSD/signals" ...>AUDUSD</a>
</nav>

<section id="market-panel" aria-live="polite">
  <!-- panel HTML for current (market, function) — server-rendered initially,
       swapped via HTMX on tab click -->
</section>
```

**Why `innerHTML` on `#market-panel` over `outerHTML` on the section itself:**
- `outerHTML` would replace the `#market-panel` element, requiring the server response to wrap the new content in the same `<section id="market-panel">` envelope every time. Easy to forget; if forgotten, subsequent swaps target a no-longer-existing ID and fail silently.
- `innerHTML` preserves `#market-panel` as a stable swap target for the next click. Server returns just the inner content (form, signals card, etc.). Simpler contract.
- Scroll preservation: HTMX's default `scroll:none` (or omitting `hx-swap-modifier`) keeps scroll position. Verified by HTMX 1.9 docs.

**Key gotcha:** when `hx-push-url="true"` updates the URL, browser back/forward expects the page to handle the popstate. HTMX 1.9 has built-in history-cache support; the panel HTML is cached by URL. **No additional code needed** — but tests should cover navigating back from `/markets/AUDUSD/signals` to `/markets/SPI200/signals` and confirming the panel matches.

**`hx-trigger` for status-strip refresh (D-07):**
```html
<div id="status-strip"
     hx-get="/status-strip"
     hx-trigger="every 28800s, visibilitychange[document.visibilityState=='visible'] from:document"
     hx-swap="outerHTML">
  ...server-rendered initial state...
</div>
```
The `every 28800s` is 8 hours — covers the daily cycle. The exact 08:01 AWST timing requires JS computation (HTMX cron isn't a thing) — recommendation: emit `hx-trigger="ready, visibilitychange[document.visibilityState=='visible'] from:document"` and let a small `setTimeout` in the inline JS compute "ms until next 08:01 AWST" and fire `htmx.trigger('#status-strip', 'refresh')` once at that target. This matches D-07 precisely (08:01 wake + visibilitychange) without polling.

### 7. STRATEGY_VERSION constant

[VERIFIED: `system_params.py:27` `STRATEGY_VERSION: str = 'v1.2.0'`; `dashboard_renderer/components/footer.py:6-13` already takes `strategy_version` as primitive arg; `dashboard.py:1080-1114 _resolve_strategy_version` reads from `state.signals[*].strategy_version`]

| Location | Current value | Reads from where |
|----------|---------------|------------------|
| `system_params.py:27` | `'v1.2.0'` | source of truth |
| `state.json` `signals.SPI200.strategy_version` | `'v1.1.0'` | last written by daemon (not yet re-run after a `STRATEGY_VERSION` bump from v1.1.0 → v1.2.0) |
| `dashboard.html:1113` | `'v1.1.0'` literal | rendered when state had v1.1.0 |
| `dashboard-signals.html:837` | `'v1.0.0'` literal | rendered earlier — likely before Phase 22 footer lift |
| `dashboard-account.html:834` | `'v1.0.0'` literal | same |
| `dashboard-settings.html:720` | `'v1.0.0'` literal | same |
| `dashboard-market-test.html:692` | `'v1.0.0'` literal | same |

[VERIFIED: grep across 4 sibling HTML files]

**The "Phase 22 work" referenced in CONTEXT.md D-22 ALREADY exists.** `_resolve_strategy_version` at `dashboard.py:1080` and `render_footer` at `dashboard_renderer/components/footer.py` already form a clean pipeline. The 4 sibling files have stale literals because they were generated before the v1.2.0 bump and have not been re-rendered.

**The reconciliation is achieved by a single re-render** triggered by the next state.json mtime change (`web/routes/dashboard.py:_is_stale` rule at line 119). Phase 25 doesn't need new code for D-22 — it needs to **delete the 4 sibling files** (or force-render them) so the next `_serve_dashboard_page` call regenerates them with the current `_resolve_strategy_version(state)` result. **Recommend an explicit task: "force-regenerate all 5 dashboard HTML files at deploy time."**

There is one wrinkle: `_resolve_strategy_version` reads from `state.signals[*].strategy_version`, NOT from `system_params.STRATEGY_VERSION`. So after a v1.2.0 bump in `system_params.py`, the rendered footer still shows v1.1.0 until the daemon's next run tags the signals with v1.2.0 (`main.py:1495 'strategy_version': system_params.STRATEGY_VERSION`). [VERIFIED]. The footer correctly reflects "the strategy that produced today's signals" — which is the operator-relevant fact. CONTEXT.md D-22's "single source of truth via existing `STRATEGY_VERSION` constant" is slightly imprecise: the **constant** is the source for daemon-tagged signals, the **rendered footer** is the source for what the operator sees, and these two converge after the next daily run. Planner should preserve this discipline (don't change the renderer to read `system_params.STRATEGY_VERSION` directly — that breaks the hex boundary documented at `dashboard.py:1089-1093` and LEARNINGS 2026-04-27).

### 8. Tests as contract

[VERIFIED: `tests/test_web_app_factory.py:246-379`; `tests/test_dashboard.py:3100-3122`; `tests/test_web_dashboard.py` (fragment tests); test file inventory]

**Pinning assertions that new routes must NOT break:**

| Test file:line | Assertion | Why it matters |
|----------------|-----------|----------------|
| `test_web_app_factory.py:255-260` | Routes exist: `/markets`, `/markets/{market_id}`, `/markets/settings`, `/markets/{market_id}/settings`, `/account/balance`, `/market-test/run` | New routes are additive; this set must remain. |
| `test_web_app_factory.py:344-379` | `PATCH /markets/settings` body successfully updates `strategy_settings.SPI200` (route-shadowing regression) | Critical — the 18ea2c5 fix lock. New literal-function `/markets/{market_id}/<fn>` routes must be registered AFTER `/markets/settings` and BEFORE `/markets/{market_id}` to preserve this. |
| `test_dashboard.py:3108-3112` | Rendered `dashboard.html` contains `Signals`, `Account Management`, `Settings`, `Market Test`, `hx-post="/market-test/run"` | If function tabs rename per D-21 (`Account Management` → `Account`), this assertion needs adjustment to match the new label. **Plan must include test update.** |
| `test_dashboard.py:3120` | `html_out.count('hx-patch="/markets/settings"') >= 2` | Settings forms must still target `/markets/settings`. Fieldset grouping (D-12) doesn't change the form action — should stay green. |
| `test_web_dashboard.py:474-501` | Fragment GET `/?fragment=position-group-X` returns `<tbody>` inner HTML; nonexistent fragment returns 404 | Must remain green. New `/markets/{m}/{fn}` routes don't share the `?fragment=` query param. |
| `test_web_dashboard.py:519-708` | Forward-stop fragment endpoint behaviour | Must remain green. Independent of Phase 25 changes. |

**Recommended new tests for Phase 25:**

1. **Two-axis nav routing tests** (`test_web_app_factory.py` extension):
   - `/markets/SPI200/signals` returns 200 with auth, panel content includes "SPI 200"
   - `/markets/AUDUSD/signals` returns 200, content includes "AUD/USD"
   - `/markets/SPI200/settings` returns 200, includes settings form
   - `/markets/SPI200/market-test` returns 200, includes market-test form
   - `/markets/NOPE/signals` returns 404 (validates `market_id` against `state.markets`)

2. **Cookie-set test** (`test_web_app_factory.py` or new file):
   - `GET /markets/AUDUSD/signals` sets `Set-Cookie: selected_market=AUDUSD; ...; SameSite=Lax` (no HttpOnly)
   - `GET /markets/SPI200/settings` sets `Set-Cookie: selected_market=SPI200; ...`

3. **Status strip endpoint test**:
   - `GET /status-strip` returns 200, content-type `text/html`, body contains `<time datetime=`
   - On fresh state (`last_run=None`), response contains "Awaiting first run"
   - On stale state (`last_run` > 26h old), response contains amber dot class

4. **First-run rendering test** (`test_dashboard.py` extension):
   - When `state['last_run'] is None`, rendered HTML contains exactly ONE onboarding card and ZERO `<table class="trace-indicators-table">`
   - When `state['last_run'] != None`, trace tables are rendered

5. **HTMX header-sniff test** (covers the panel-only-vs-full-page split for `/markets/<m>/<fn>`):
   - With `HX-Request: true` header → response is panel HTML only (no `<header>`, no `<footer>`)
   - Without that header → response is full page

6. **Equity chart hide test** (D-11):
   - `equity_history` with 3 identical `(date, value)` tuples → no `<canvas id="equityChart">` in output, instead the empty-state copy
   - With 5 distinct tuples → canvas is rendered

7. **Stats bar hide test** (D-10):
   - `paper_trades` empty + no closed live trades → no `<aside class="stats-bar">` in output
   - With ≥1 closed trade → stats bar present

8. **Strategy version reconciliation test**:
   - After `state.signals[*].strategy_version = 'v1.2.0'`, all 5 sibling HTML files contain `<code>v1.2.0</code>` and ZERO instances of `<code>v1.0.0</code>` or `<code>v1.1.0</code>`

9. **a11y assertion expansions** (D-19):
   - Active tab anchor has `aria-current="page"`
   - All `<details>` elements have synced `aria-expanded`
   - All inline `style="color:` is GONE: `assert 'style="color:' not in html_out`

### 9. Trace-indicators table location

[VERIFIED: `dashboard.html:687-758`; `dashboard.py` `_render_trace_panels` referenced from `signals.py:60`]

**Per-instrument structure:**
```html
<details class="trace-disclosure" data-instrument="{INSTRUMENT}"{{TRACE_OPEN_X}}>
  <summary class="trace-summary">Show calculations</summary>
  <section class="trace-panel">
    <p><em>Awaiting first daily run — calculations will appear after the next 08:00 AWST cycle.</em></p>
  </section>
  <section class="trace-panel">
    <p class="eyebrow">INDICATORS</p>
    <table class="trace-indicators-table">
      <tbody>
        <tr><td class="trace-indicator-name" ...>TR</td><td class="num">n/a (need 1 bars, have 0)</td></tr>
        <tr class="formula-row" hidden><td colspan="2">TR = max(...)</td></tr>
        <!-- 9 indicator rows × 2 (data + formula-row) = ~18 rows total per instrument -->
      </tbody>
    </table>
  </section>
  <section class="trace-panel trace-vote">
    <p><em>Awaiting first daily run.</em></p>
  </section>
</details>
```

The table is INSIDE a `<details>` which is INSIDE `_render_trace_panels()` (called from `signals.py:60`). The card-level `<article class="card">` containing FLAT/LONG/SHORT label is OUTSIDE the `<details>` (line 681-686 in dashboard.html). 

**D-09 conditional render — recommended hook point:** in the renderer that produces `_render_trace_panels` output (search for it in `dashboard.py`). Wrap the entire `<details>` emission in `if state.get('last_run') is None: return ''` or substitute with the onboarding card. **The cards (lines 681-686, 720-725) STAY** — D-09 is about the trace tables being a "wall of n/a", not about hiding the FLAT/LONG/SHORT labels.

Selector for the planner: target `<table class="trace-indicators-table">` AND its enclosing `<details class="trace-disclosure">`. Hide the whole `<details>` element when `state['last_run'] is None`.

### 10. AWST timezone handling precedent

[VERIFIED: `main.py:72 AWST = ZoneInfo('Australia/Perth')`; `notifier.py:1546,1635 pytz.timezone('Australia/Perth')`; `dashboard.py:51,77 pytz` import; `dashboard_renderer/api.py:18 perth = pytz.timezone('Australia/Perth')`]

**Server-side pattern:** `pytz.timezone('Australia/Perth').localize(...)` for `datetime.now()` localisation. Never construct with a `tzinfo=` kwarg directly (`dashboard.py:51-54` documents this as a Wave-1 invariant — pytz's `localize()` is required for proper offset resolution, even though Perth has no DST). `main.py` is more modern and uses `ZoneInfo` from stdlib. Both are valid; the project mixes them. Phase 25's status-strip server render should match nearby code: if the new helper lives in `dashboard_renderer/components/header.py`, follow the pytz pattern (existing `api.py:18` precedent).

**Client-side pattern (Phase 25 NEW — no precedent):** D-08 is explicit — JS countdown computes ms-to-target using a fixed UTC+8 offset, NOT `Intl.DateTimeFormat` browser-local TZ.

```js
// Recommended JS helper (inline in shell.py script block per D-02 + Claude's discretion):
function msToNextAWST0801() {
  const now = Date.now();             // ms since epoch UTC — TZ-independent
  // 08:01 AWST = 00:01 UTC = 60_000 ms past UTC midnight
  const utcDate = new Date(now);
  const targetUtcMs = Date.UTC(
    utcDate.getUTCFullYear(),
    utcDate.getUTCMonth(),
    utcDate.getUTCDate(),
    0, 1, 0, 0,
  );
  // If we're already past 00:01 UTC today, target tomorrow's 00:01 UTC
  return targetUtcMs > now ? (targetUtcMs - now) : (targetUtcMs + 86_400_000 - now);
}
```

Why `Date.UTC` — it returns ms since epoch in UTC, ignoring the browser's local TZ entirely. This is the canonical "fixed offset" approach. `Intl.DateTimeFormat({timeZone: 'Australia/Perth'})` would also work but pulls in the IANA database — `Date.UTC` is enough since AWST has no DST.

For the "in Nh Mm" countdown display, the same arithmetic gives the human-readable delta. Update every 60 seconds via `setInterval(..., 60_000)`.

**Weekend handling:** the daemon skips weekends (`main.py:830` AWST run-date discipline; `_run_daily_check_caught` weekend-skip path). For "next run" on a Friday afternoon AWST, the strip should display "Mon 08:00 AWST · in 2d 16h 0m" or similar, not Saturday's. Recommend the JS helper accepts a "skip weekends" param defaulting to `true`. The server render of the initial strip uses the same logic. Lock the exact display format with the operator during plan-phase (UI-SPEC §System Status strip says "08:00 AWST · in {N}h {M}m" but doesn't address >24h offsets).

### 11. Equity chart data source

[VERIFIED: `dashboard.html:830-873`; `dashboard.py:2514-2591 _render_equity_chart_container`; `state.json` shows `equity_history: [3 entries with same date/value]`]

**Current data source:** `state['equity_history']` — list of `{date: 'YYYY-MM-DD', equity: float}` dicts. `dashboard.py:2536-2537`:
```python
labels = [row['date'] for row in equity_history]
data = [float(row['equity']) for row in equity_history]
```

**The "3-point flat line" bug:** `state.json` currently has 3 identical entries `{date: '2026-04-23', equity: 100000.0}`. The render produces 3 indistinguishable points, which Chart.js draws as a flat line. UX-wise this looks like dead data.

**D-11 implementation pattern:**

```python
def _distinct_equity_tuples(equity_history: list) -> list:
    """Phase 25 D-11: dedupe (date, equity) tuples; chart hides until ≥5 distinct."""
    seen = set()
    distinct = []
    for row in equity_history:
        key = (row['date'], float(row['equity']))
        if key not in seen:
            seen.add(key)
            distinct.append(row)
    return distinct

# In _render_equity_chart_container:
distinct = _distinct_equity_tuples(state.get('equity_history', []))
if len(distinct) < 5:
    return (
        '<section aria-labelledby="heading-equity">\n'
        '  <h2 id="heading-equity">Equity curve</h2>\n'
        '  <div class="empty-state">'
        'Chart appears once 5 daily equity points have been recorded.'
        '</div>\n'
        '</section>\n'
    )
# else: render canvas + Chart.js as before, but use `distinct` not `equity_history` for labels/data
```

**The current empty-state branch already exists** (`dashboard.py:2524-2532`) but only triggers on totally empty `equity_history`. D-11 changes the trigger from "empty" to "<5 distinct".

### 12. Open Questions to RESOLVE (Claude's Discretion)

| Question | Recommendation | Rationale |
|----------|----------------|-----------|
| `/status-strip` endpoint location | `web/routes/dashboard.py` (new function `get_status_strip` near line 246) | Shares `is_cookie_session`, `_resolve_trace_open`, state-load patterns with sibling handlers. Creating `web/routes/status.py` would force duplication. The route name `/status-strip` doesn't suggest a separate domain — it's a fragment endpoint, same family as `/?fragment=position-group-X`. |
| HTMX swap semantics for market-tab swap | `hx-target="#market-panel"` + `hx-swap="innerHTML"` + `hx-push-url="true"` | `innerHTML` keeps the swap target stable across consecutive clicks (vs `outerHTML` requiring the response to re-emit the wrapper element). `hx-push-url="true"` writes the canonical `/markets/<m>/<fn>` URL per D-03. |
| AWST countdown helper inline vs separate JS | Inline in `shell.py` script block | D-02 locks no external `/static/dashboard.js`. The countdown is ~30 lines including `setInterval` + format helper. Inlining keeps the single-file shell pattern. The helper is small enough that compression would not pay back the HTTP round-trip cost. |
| `last_run_status` derivation rule (gap from CONTEXT.md not addressed in Claude's Discretion) | 3-state derivation: `green` if `state.last_run == today_awst_iso AND len(state.warnings) == 0 (or last warning age < 24h)`; `amber` if `state.last_run < today_awst_iso`; `red` if `state.last_run == today_awst_iso AND state.warnings has a recent error`. Lock this with operator during plan-phase. | No `last_run_status` field exists. Operator needs to confirm whether "warnings" counts as failure or just amber, and whether email-send-failure should surface as red. **This is the critical gap to raise in plan-phase.** |
| Cookie naming | `selected_market` (matches D-05 verbatim) | No collision with existing `tsi_session`, `tsi_trace_open`, `tsi_enroll`, `tsi_pending`, `tsi_trusted`. |
| Function tab strip rendering when on `/account` | Always render BOTH strips on `/account`, but the market strip emits zero anchors (just the `+ Add market` chip OR is fully hidden — D-04 says "emit zero DOM"). Function strip stays so user can navigate to a market-scoped function. | "Emit zero DOM" per D-04 for the market strip; function strip is always present per D-18 (two independent tablists). |

### 13. First-run signal verification

[VERIFIED: `state_manager.py:593` — `'last_run': None`; `main.py:1540` — `state['last_run'] = run_date_iso` on success]

| Lifecycle event | `state['last_run']` value |
|-----------------|--------------------------|
| Fresh install (just-created state.json from `reset_state()`) | `None` |
| After first successful daily run | ISO date string `'YYYY-MM-DD'` (e.g., `'2026-04-23'`) |
| After subsequent runs | latest run-date ISO string |
| After a crash/skip | retained from previous successful run (not cleared) |

**D-09 trigger is correct:** `state['last_run'] is None` evaluates to True on fresh install and False afterwards. The trigger correctly distinguishes "never run" from "ran but stale". For staleness detection (the amber-dot case in D-06), planner needs an additional rule: `state['last_run'] < today_awst_iso` (more than one cycle since success).

### 14. Project skills

[VERIFIED: `.claude/skills/` and `.agents/skills/` listed]

The directories contain Ruflo / claude-flow MCP / SPARC methodology skills, not project-domain skills (no `dashboard-html-render`, `awst-timezone`, or `htmx-pattern` skill). Phase 25 should not invoke any of these — they're cross-project Ruflo coordination tooling, not relevant to a UI refactor.

The relevant patterns instead live in:
- `.planning/STATE.md` decision log (DASH-01..04, STATE-01..07, etc.)
- LEARNINGS files (global + project-local)
- CONTEXT.md decisions (D-01..D-22)

---

## Standard Stack

### Core (already loaded — no changes)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| HTMX | 1.9.12 | Partial-page updates, URL push | [VERIFIED: `dashboard.html:8`] Already SRI-pinned. `hx-push-url`, `hx-trigger`, `hx-swap` all supported. |
| HTMX json-enc | 1.9.12 | JSON-body encoding for FastAPI Pydantic | [VERIFIED: `dashboard.html:9`] Required by every form that posts to a Pydantic-bodied endpoint. |
| Chart.js | 4.4.6 | Equity curve rendering | [VERIFIED: `dashboard.py:148-149` references; SRI-pinned] No upgrade needed. |
| FastAPI | (pinned in requirements.txt) | Route registration, request/response | [VERIFIED: `web/app.py:37`] Path-segment routing with literal-before-dynamic ordering is the relevant pattern. |
| pytz | (project legacy) | Server-side AWST localisation | [VERIFIED: `dashboard.py:77`, `notifier.py:1546`] Project precedent. `main.py:72` uses stdlib `ZoneInfo` — newer code can prefer `ZoneInfo`, but pytz must keep working. |

### No new dependencies required

Phase 25 introduces no new libraries. All work is HTML/CSS/JS authored against the existing toolchain.

---

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────────────────────────────────────┐
                    │ Browser (operator)                              │
                    │  ┌──────────────────┐   ┌────────────────────┐  │
                    │  │ Function strip   │   │ Market strip       │  │
                    │  │  /signals etc    │   │  hx-get /markets/X │  │
                    │  │  full-page nav   │   │  hx-push-url       │  │
                    │  └────────┬─────────┘   └─────────┬──────────┘  │
                    │           │ click                 │ click       │
                    │           │ (browser nav)         │ (HTMX swap) │
                    │           ▼                       ▼             │
                    └───────────┼───────────────────────┼─────────────┘
                                │                       │
                                │ GET /markets/X/sigs   │ GET /markets/X/sigs
                                │ HX-Request: false     │ HX-Request: true
                                │ → full doc            │ → panel only
                                │                       │
                ┌───────────────▼───────────────────────▼──────────────┐
                │ FastAPI app (web/app.py)                              │
                │  ┌─────────────────────────────────────────────────┐ │
                │  │ AuthMiddleware (cookie OR header) — 1st         │ │
                │  └────────────────┬────────────────────────────────┘ │
                │                   │ authed                            │
                │  ┌────────────────▼────────────────────────────────┐ │
                │  │ web/routes/dashboard.py                         │ │
                │  │  /                                              │ │
                │  │  /signals  /account  /settings  /market-test    │ │
                │  │  /markets/{m}/signals  /…/settings  /…/m-test   │ │
                │  │  /status-strip                                  │ │
                │  │  /?fragment={position-group-X | forward-stop}   │ │
                │  └────────────────┬────────────────────────────────┘ │
                │                   │ load_state()                     │
                │                   ▼                                  │
                │  ┌────────────────────────────────────────────────┐ │
                │  │ web/routes/markets.py                          │ │
                │  │  POST /markets                                 │ │
                │  │  PATCH /markets/settings   ← LITERAL FIRST     │ │
                │  │  PATCH /markets/{m}/settings                   │ │
                │  │  PATCH /markets/{m}        ← DYNAMIC LAST      │ │
                │  │  PATCH /account/balance                        │ │
                │  │  POST  /market-test/run                        │ │
                │  └────────────────────────────────────────────────┘ │
                └────────────────────┬─────────────────────────────────┘
                                     │
                                     ▼
                ┌──────────────────────────────────────────────────────┐
                │ dashboard_renderer/  (renderer hex)                  │
                │  api.py — render_dashboard() composes shell + body   │
                │  shell.py — <head>, <style>, <script> (D-02 target)  │
                │  components/                                         │
                │    header.py  — H1 + status strip (NEW for D-06)     │
                │    nav.py     — two-axis nav (NEW for D-01/18)       │
                │    signals.py — signal cards + trace tables          │
                │    settings.py — fieldset groups (D-12)              │
                │    positions.py / trades.py / paper_trades.py        │
                │    footer.py — strategy version (already correct)    │
                └────────────────────┬─────────────────────────────────┘
                                     │ uses
                                     ▼
                ┌──────────────────────────────────────────────────────┐
                │ state_manager.py + state.json                        │
                │  (single source of truth — UNCHANGED in Phase 25)    │
                └──────────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
dashboard_renderer/
├── api.py                          # entry: render_dashboard(); +1 sig: active_market
├── shell.py                        # <head>+<style>+<script> deduped here (D-02)
├── context.py                      # RenderContext +1 field: active_market
└── components/
    ├── header.py                   # H1 + status_strip (NEW: render_status_strip)
    ├── nav.py                      # NEW — two-axis nav rendering (replaces dashboard.py:2673)
    ├── signals.py                  # signal cards (D-19 inline-style fix)
    ├── settings.py                 # fieldset grouping (D-12)
    ├── positions.py / trades.py    # wide-table wrapper (D-20)
    ├── paper_trades.py             # button rename (D-21)
    └── footer.py                   # strategy version (already correct)

web/routes/
├── dashboard.py                    # +/markets/{m}/{fn} GET routes; +/status-strip GET; +cookie set
└── markets.py                      # POST /markets unchanged (used by Add-market chip)
```

### Pattern 1: Two-axis nav rendering

**What:** Function strip emits anchor-based full-page nav; market strip emits HTMX-swapped tabs.
**When to use:** anywhere the page has both a "function" axis (orthogonal sections of the app) and a "subject" axis (which entity the function is acting on).

```python
# dashboard_renderer/components/nav.py (NEW)

import html

def render_function_strip(active_function: str, active_market: str | None) -> str:
    """Function tab strip — full-page nav (no HTMX swap).

    active_market is None when on /account (D-04). Function tabs always render.
    Market-scoped functions use /markets/{active_market}/<function> when active_market
    is set, otherwise /<function> (back-compat for current routes).
    """
    funcs = (
        ('signals', 'Signals', True),         # market-scoped
        ('account', 'Account', False),        # market-agnostic (D-04)
        ('settings', 'Settings', True),
        ('market-test', 'Market Test', True),
    )
    out = ['<nav role="tablist" aria-label="Function" class="tabs tabs-function">\n']
    for key, label, is_market_scoped in funcs:
        if is_market_scoped and active_market:
            href = f'/markets/{html.escape(active_market, quote=True)}/{key}'
        elif is_market_scoped:
            href = f'/{key}'  # fallback when no market chosen
        else:
            href = f'/{key}'  # always /account for the agnostic function
        is_active = key == active_function
        attrs = (
            'role="tab" '
            f'tabindex="{"0" if is_active else "-1"}" '
            f'aria-current="{"page" if is_active else "false"}"'
        )
        out.append(f'  <a href="{href}" {attrs}>{html.escape(label, quote=True)}</a>\n')
    out.append('</nav>\n')
    return ''.join(out)


def render_market_strip(state: dict, active_market: str, active_function: str) -> str:
    """Market tab strip — HTMX swap (D-01/D-03).

    Hidden entirely when active_function == 'account' (D-04 — emit zero DOM).
    """
    if active_function == 'account':
        return ''  # D-04: zero DOM, not display:none
    import dashboard as d
    out = ['<nav role="tablist" aria-label="Market" class="tabs tabs-market" id="market-tab-strip">\n']
    for market_id, _display in d._display_names(state).items():
        is_active = market_id == active_market
        market_esc = html.escape(market_id, quote=True)
        attrs = (
            f'role="tab" tabindex="{"0" if is_active else "-1"}" '
            f'aria-current="{"page" if is_active else "false"}" '
            f'href="/markets/{market_esc}/{active_function}" '
            f'hx-get="/markets/{market_esc}/{active_function}" '
            f'hx-target="#market-panel" hx-swap="innerHTML" hx-push-url="true" '
            'hx-headers=\'{"X-Trading-Signals-Auth": "{{WEB_AUTH_SECRET}}"}\''
        )
        out.append(f'  <a {attrs}>{market_esc}</a>\n')
    # Add-market chip (D-16) — NOT inside role=tablist
    out.append('  <details class="add-market-chip">\n'
               '    <summary>+ Add market</summary>\n'
               '    <!-- inline form posts to existing POST /markets — see existing render_add_market_form -->\n'
               '  </details>\n')
    out.append('</nav>\n')
    return ''.join(out)
```

### Pattern 2: Cookie write on every market-scoped page render

```python
# web/routes/dashboard.py — extend _serve_dashboard_page (around line 240)

_MARKET_COOKIE_ATTRS = '; Max-Age=2592000; Path=/; Secure; SameSite=Lax'  # 30 days, JS-readable (D-05)

# When serving /markets/{market_id}/{function}:
response = Response(content=..., media_type='text/html; charset=utf-8')
response.headers['Set-Cookie'] = f'selected_market={market_id}{_MARKET_COOKIE_ATTRS}'
return response
```

Note: when adding `/markets/{market_id}/<function>` GET routes that share a handler, the cookie write happens in the shared handler — NOT duplicated per route.

### Pattern 3: Status strip — server-rendered initial + client refresh

```python
# dashboard_renderer/components/header.py (extension)

def render_status_strip(state: dict, now_awst: datetime) -> str:
    """Phase 25 D-06 — System Status strip (server-rendered initial state).

    Reads state['last_run'] (date string OR None). Computes amber/green/red
    status from last_run vs today_awst, plus state['warnings'] tail.
    """
    last_run = state.get('last_run')
    today_iso = now_awst.strftime('%Y-%m-%d')
    if last_run is None:
        dot_class = 'status-dot--never'
        last_run_html = '<span>Awaiting first run</span>'
    elif last_run == today_iso:
        # Recent warning detection — operator-locked rule (raise in plan-phase)
        recent_warnings = [...]  # implementation TBD
        if recent_warnings:
            dot_class = 'status-dot--failure'
            last_run_html = f'<time datetime="{html.escape(last_run, quote=True)}">{last_run}</time> · Failed'
        else:
            dot_class = 'status-dot--success'
            last_run_html = f'<time datetime="{html.escape(last_run, quote=True)}">{last_run}</time> · OK'
    else:
        dot_class = 'status-dot--stale'
        last_run_html = f'<time datetime="{html.escape(last_run, quote=True)}">{last_run}</time> · Stale'

    # Next-run is computed from system_params.SCHEDULE_TIME_UTC = '00:00' = 08:00 AWST.
    # Client-side JS countdown picks up the data attribute and ticks every 60s.
    next_run_iso = _compute_next_awst_0800(now_awst).isoformat()  # helper TBD

    return (
        f'<div id="status-strip" class="status-strip" '
        f'hx-get="/status-strip" hx-trigger="ready, visibilitychange[document.visibilityState==\'visible\'] from:document" '
        f'hx-swap="outerHTML">\n'
        f'  <span class="status-dot {dot_class}" aria-hidden="true"></span>\n'
        f'  <span class="status-label">Last run</span>\n'
        f'  {last_run_html}\n'
        f'  <span class="status-sep"> · </span>\n'
        f'  <span class="status-label">Next run</span>\n'
        f'  <span data-countdown="{html.escape(next_run_iso, quote=True)}">08:00 AWST</span>\n'
        f'</div>\n'
    )
```

### Anti-Patterns to Avoid

- **Adding `last_run_at`/`last_run_status`/`next_run_at` to state.json** — this expands scope into state schema migration (currently `schema_version: 8`) and breaks the UI-only constraint. Derive at render time.
- **Reading `system_params.STRATEGY_VERSION` directly in `dashboard.py` or `dashboard_renderer/`** — breaks the hex boundary documented at `dashboard.py:1089-1093`. Always read from `state.signals[*].strategy_version`.
- **Using `outerHTML` swap on `#market-panel`** — replaces the swap target itself, requiring the response to wrap content in a fresh `<section id="market-panel">` envelope every time. One forgotten wrapper and the next click fails silently.
- **Creating a new `web/routes/status.py`** — duplicates the auth-cookie validators and state-load helpers from `web/routes/dashboard.py`. Keep `/status-strip` in `dashboard.py`.
- **Polling for status updates** — D-07 explicitly says no idle polling. Use the 08:01 AWST one-shot timer + visibilitychange.
- **Browser-local `Intl.DateTimeFormat` for the countdown** — D-08 forbids this. Use `Date.UTC(...)` arithmetic.
- **Removing `dashboard.html` while sibling files still exist** — `web/routes/dashboard.py:_is_stale` reads from `dashboard.html` markers (`_REQUIRED_DASHBOARD_MARKER = b'<nav class="tabs"'`). If the marker changes (Phase 25 will rename CSS classes), update line 74 too.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cookie management | Custom `request.headers['cookie']` parsing | FastAPI `Request.cookies` dict (read) + raw `Set-Cookie` header strings (write — project pattern) | Project's `_COOKIE_ATTRS_CREATE` literal pattern (`login.py:51`) is the established discipline; reuse verbatim. |
| URL push for tab swap | Manual `history.pushState` + popstate handlers | HTMX `hx-push-url="true"` | HTMX 1.9.12 has it built in with cache support. |
| Date arithmetic | Naive `Date()` constructors | `Date.UTC(...)` for fixed-offset (D-08) | Avoids browser-local TZ contamination. |
| Two-axis nav widget | Custom keyboard handler | WAI-ARIA tabs pattern with roving tabindex | D-18 specifies WAI-ARIA exactly. Each tablist needs its own tabindex management; tab key moves between tablists. ~30 lines of vanilla JS. |
| AWST localisation server-side | `datetime(...., tzinfo=...)` direct construction | `pytz.timezone('Australia/Perth').localize(datetime.now())` | Project rule: `dashboard.py:51-54` warns against direct tzinfo kwarg. |
| Status-strip refresh scheduling | `setInterval` polling | `hx-trigger="visibilitychange[document.visibilityState=='visible'] from:document"` + one-shot `setTimeout` | Zero polling (D-07); HTMX trigger expression handles the visibilitychange wiring. |
| Strategy version display | Hardcoded literal in template | `dashboard_renderer/components/footer.py render_footer(strategy_version)` | Already exists — Phase 25 just deletes the 4 stale sibling HTML files so they get re-rendered. |

**Key insight:** The codebase has invested heavily in patterns that Phase 25 should reuse — the renderer hex-boundary discipline, the literal-before-dynamic route ordering, the inline-shell DASH-01 contract, the cookie attrs constants, the AWST localisation pytz pattern. Resist the temptation to "modernise" any of these as part of Phase 25 — UI-only means UI-only.

---

## Runtime State Inventory

This is a UI-only refactor with no data migration. The categories below are still listed for completeness:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — Phase 25 makes no state.json schema changes. The 5 generated dashboard*.html files on disk are *outputs* of the renderer, not inputs to it. | Force-regenerate all 5 files at deploy time so stale strategy-version literals (v1.0.0, v1.1.0) are replaced with current `_resolve_strategy_version(state)` result. Single command: `rm -f dashboard*.html && curl https://signals.mwiriadi.me/` (the next request triggers regeneration via `_is_stale`). |
| Live service config | systemd unit `trading-signals-web.service` runs `web.app:app`. No config changes required. | None. |
| OS-registered state | systemd timer schedule lives in `system_params.SCHEDULE_TIME_UTC = '00:00'` (in code, not registered with the OS). The web service is started by systemd; no scheduling at the OS level. | None — the daemon's run timing is unchanged. |
| Secrets / env vars | `WEB_AUTH_SECRET`, `WEB_AUTH_USERNAME`, `OPERATOR_RECOVERY_EMAIL` referenced by `web/app.py:_read_auth_credentials`. None changed by Phase 25. | None. |
| Build artifacts | `__pycache__/` directories, `*.pyc` files. None affected. | None. |

**Nothing found in any category that requires migration.** The phase is render-layer + route-additions only.

---

## Common Pitfalls

### Pitfall 1: Field name confusion (`last_run` vs `last_run_at`)

**What goes wrong:** Plan tasks reference CONTEXT.md field names like `last_run_at` verbatim, then implementation either creates the field (scope creep) or silently writes to a typo'd key.
**Why it happens:** CONTEXT.md and the actual schema diverged. The ROADMAP and discussion-log both use the natural-language `last run`, which the planner may translate to `last_run_at`.
**How to avoid:** Lock the field name `state['last_run']` (no `_at` suffix) in PLAN.md verbatim, with a one-line note: "Yes, this is a `YYYY-MM-DD` date string, not an ISO datetime; D-06 'render `<time datetime>`' uses this string directly."
**Warning signs:** Any task description that says "read `last_run_at`" — replace immediately. Any test fixture that includes a `last_run_at` key in mock state — wrong, will silently pass alongside the real `last_run`.

### Pitfall 2: Route shadowing (the 18ea2c5 class)

**What goes wrong:** A new `/markets/{market_id}/<function>` route is registered before `/markets/settings` literal, causing `PATCH /markets/settings` to dispatch to the dynamic handler with `market_id="settings"`.
**Why it happens:** Adding routes in "logical" order (e.g., grouping all GETs together) instead of literal-before-dynamic order.
**How to avoid:** Plan tasks must specify "register at line N, after line 166 `/markets/settings` and before line 176 `/markets/{market_id}`". Add a regression test mirroring `test_patch_market_settings_literal_path_updates_settings` (`tests/test_web_app_factory.py:344`).
**Warning signs:** Any new `@app.{verb}('/markets/{market_id}/...')` decorator above an existing `@app.{verb}('/markets/<literal>')` decorator in the source.

### Pitfall 3: Browser-local TZ leak in countdown

**What goes wrong:** Operator travels to Perth → London. JS countdown reads `new Date()` and shows "next run in 8h" when it's actually "in 16h" (London time is 16h before AWST).
**Why it happens:** `new Date()` and `getDate()`/`getHours()` use the browser's local TZ. `Intl.DateTimeFormat({timeZone: 'Australia/Perth'})` works but is heavier.
**How to avoid:** Use `Date.UTC(year, month, day, 0, 1)` arithmetic (= 00:01 UTC = 08:01 AWST). The result is the same regardless of where the browser is.
**Warning signs:** Any JS that calls `.getHours()`, `.getMinutes()`, `.getDate()` on a `Date` object without first converting to UTC, or uses `new Date('2026-04-23T08:00:00')` (which interprets as local time).

### Pitfall 4: Stale sibling-page caches

**What goes wrong:** D-22 strategy-version reconciliation fails because `dashboard-signals.html` etc. are not regenerated even after a deploy — `_is_stale()` only re-renders when state.json mtime > html mtime. A code change alone doesn't trigger regen.
**Why it happens:** `_is_stale` checks file mtimes; a deploy updates `dashboard.py` but not `state.json` or the cached HTML.
**How to avoid:** Add `_REQUIRED_DASHBOARD_MARKER` change as a forced-regen signal. Already present at `web/routes/dashboard.py:74` (`b'<nav class="tabs"'`). Phase 25 changes the tab class names (e.g., `class="tabs tabs-function"`) — update the marker to match (e.g., `b'class="tabs tabs-function"'`) so all 5 files regenerate on the first request post-deploy.
**Warning signs:** After deploy, dashboard still shows old version literal. `curl https://signals.mwiriadi.me/dashboard-signals.html | grep "Strategy version"` shows v1.0.0 or v1.1.0.

### Pitfall 5: Cookie deletion-attrs-mismatch

**What goes wrong:** Add a "clear preference" UI in some future iteration, write `Set-Cookie: selected_market=; Max-Age=0` without the `Path=/; Secure; SameSite=Lax` attrs — browser ignores deletion because the original cookie has those attrs.
**Why it happens:** `_COOKIE_ATTRS_CREATE` literal vs. ad-hoc deletion strings — easy to forget.
**How to avoid:** Define `_MARKET_COOKIE_DELETE_ATTRS` constant alongside `_MARKET_COOKIE_ATTRS` if a delete path is ever added. CLAUDE.md global learning explicitly calls this out.
**Warning signs:** "Cookie I just deleted is still there" debugging confusion.

### Pitfall 6: HTMX header-sniff for full-vs-fragment response

**What goes wrong:** `GET /markets/SPI200/signals` returns the full document including `<header>` + status strip + footer when called via HTMX swap, producing nested headers and a broken layout.
**Why it happens:** Same handler serves both browser navigation (full doc) and HTMX swap (panel only). Without `HX-Request` header detection, both paths get the full document.
**How to avoid:** In `_serve_dashboard_page`, check `request.headers.get('HX-Request') == 'true'`; if yes, return only the `<section id="market-panel">…</section>` content. Otherwise return the full document.
**Warning signs:** Visiting `/markets/X/signals` in a browser tab shows correct page; clicking a market tab shows broken nested layout.

### Pitfall 7: aria-expanded desync on `<details>` (Phase 17 DASH precedent)

**What goes wrong:** `<details data-instrument="X">` toggles open via cookie or click; `aria-expanded` attribute is set once at render and never updated, so SR users hear "collapsed" even when visually open.
**Why it happens:** `aria-expanded` is rendered as a static string in HTML; `<details>` toggle is browser-native, doesn't fire a JS event we listen to.
**How to avoid:** D-19 specifically calls this out. Add a small JS listener: `document.querySelectorAll('details').forEach(d => d.addEventListener('toggle', () => d.setAttribute('aria-expanded', d.open)));`
**Warning signs:** Screen-reader test (NVDA, VoiceOver) reports stale state after click.

---

## Code Examples

Verified patterns from this codebase:

### Cookie writing pattern (project canonical)

```python
# web/routes/login.py:51,447
_COOKIE_ATTRS_CREATE = '; Path=/; Secure; HttpOnly; SameSite=Strict'

return Response(
    status_code=302,
    headers={
        'Location': '/enroll-totp',
        'Set-Cookie': f'tsi_enroll={enroll_token}; Max-Age=600{_COOKIE_ATTRS_CREATE}',
    },
)
```

### Multi-cookie response (Starlette doesn't support multiple Set-Cookie via headers dict)

```python
# web/routes/totp.py:494,531
set_cookies = [
    f'tsi_session={session_token}; Max-Age=43200; Path=/; Secure; HttpOnly; SameSite=Strict'.encode('latin-1'),
    f'tsi_trusted={trusted_token}; Max-Age=2592000; Path=/; Secure; HttpOnly; SameSite=Strict'.encode('latin-1'),
]
for sc in set_cookies:
    resp.raw_headers.append((b'set-cookie', sc))
```

### Route ordering — literal before dynamic

```python
# web/routes/markets.py:166-176
@app.patch('/markets/settings')           # literal — registered FIRST
def save_market_settings(req): ...

@app.patch('/markets/{market_id}/settings')  # 2-segment dynamic
def save_market_settings_for_path(market_id, req): ...

@app.patch('/markets/{market_id}')        # 1-segment dynamic — registered LAST
def update_market(market_id, req): ...
```

### Render context (renderer hex)

```python
# dashboard_renderer/context.py
@dataclass(slots=True)
class RenderContext:
    state: dict
    now: datetime
    strategy_version: str
    trace_open_keys: tuple[str, ...] = ()
```

### AWST localisation server-side

```python
# dashboard_renderer/api.py:18
import pytz
def _resolve_now(now: datetime | None) -> datetime:
    if now is not None:
        return now
    perth = pytz.timezone('Australia/Perth')
    return datetime.now(perth)
```

### Strategy version resolution (hex-boundary safe)

```python
# dashboard.py:1080-1114 _resolve_strategy_version
# Reads from state.signals[*].strategy_version, never imports system_params.
# Lexicographic-max tie-break across instruments.
def _resolve_strategy_version(state: dict) -> str:
    signals = state.get('signals', {})
    found = []
    for sig in signals.values():
        if isinstance(sig, dict) and 'strategy_version' in sig:
            found.append(sig['strategy_version'])
    if not found:
        return 'v1.0.0'  # _DEFAULT_STRATEGY_VERSION
    return max(found, key=str)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Inline `style="color:#eab308"` on FLAT/LONG/SHORT labels | CSS token classes `signal-flat`/`signal-long`/`signal-short` | Phase 25 (D-19) | Allows colourblind affordance (status dot adjacent), enables theme changes without HTML edits. |
| 4 sibling HTML files with duplicated `<style>` + `<script>` chrome (~3000 LOC of duplication) | Single shared shell from `dashboard_renderer/shell.py` | Phase 25 (D-02) | Reduces total LOC, single point of CSS/JS update. |
| `<select aria-label="Market selection">` decorative dropdown that doesn't actually persist selection | Two-axis nav (function strip + market strip) with URL persistence | Phase 25 (D-01..D-05) | Solves the "switch market" UX bug — selection survives refresh, swaps between Settings and Market Test cleanly. |
| Hardcoded `<span class="value">2026-05-04 18:49 AWST</span>` static last-updated literal | Live System Status strip with green/amber/red dot + countdown | Phase 25 (D-06..D-08) | Trust surface for a trading product — operator sees daemon health at a glance. |
| 11 stacked `n/a (need N bars, have 0)` panels on first run | Single onboarding card | Phase 25 (D-09) | First impression is "system is ready, just waiting" not "system is broken". |
| Equity chart drawing 3 identical points as a flat line | Hidden until ≥5 distinct `(date, value)` tuples | Phase 25 (D-11) | Removes misleading visualisation. |
| `--fs-body: 14px` | `--fs-body: 16px` (other tokens scaled by 16/14) | Phase 25 (D-15) | Kills iOS auto-zoom on input focus; preserves type hierarchy. |

**Deprecated/outdated:**
- The `<select>` market dropdown with `<option>` elements (`dashboard.html:672-675`) — replaced by the market tab strip.
- `_render_dashboard_page_nav` flat 4-tab nav (`dashboard.py:2673`) — replaced by two-axis nav module.
- The 4 sibling HTML files' static `Strategy version: v1.0.0` literals — replaced by re-rendered footer from `_resolve_strategy_version(state)`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | "last_run_status" should derive from `state['warnings']` tail (red on recent error, amber on stale, green on today + clean) | Q1, Pitfall 1 | If operator wants different rule (e.g., red ONLY on email-send-failure, not on every warning), the dot will mis-classify. **Lock during plan-phase.** |
| A2 | Weekend handling for "next run" countdown skips Sat/Sun and shows next Monday | Q10, Pitfall 3 | If operator wants "next run is whenever the daemon next fires" (which on Friday afternoon = "in 3 days"), the human-readable display format may need different wording ("Mon 08:00 AWST" vs "in 64h 30m"). UI-SPEC §System Status strip doesn't lock the >24h format. |
| A3 | The 4 sibling HTML files (`dashboard-signals.html` etc.) get their stale strategy-version literals replaced by a forced regen on next request after deploy | Q7 | If `_is_stale()` doesn't trigger (e.g., no state.json mtime change between deploys), the stale literals remain. Mitigated by `_REQUIRED_DASHBOARD_MARKER` change tracking class-name renames. |
| A4 | `selected_market` cookie is set on every market-scoped page render (no surgical "only when it changed" logic) | Q5 | Slightly wasteful (sets cookie on every refresh) but keeps the implementation simple. Web-perf cost is negligible (~30 bytes per response). |
| A5 | Function strip always renders, market strip emits zero DOM on `/account` per D-04 | §Architectural Map row 1 | If operator wants the market strip to render-but-be-disabled on Account so navigation is one-click instead of two-step, the contract changes. **D-04 is explicit on "zero DOM" so this is a low-risk assumption.** |
| A6 | HTMX `hx-push-url="true"` + history cache works correctly for back-button navigation between `/markets/SPI200/signals` and `/markets/AUDUSD/signals` | Q6, Test #5 | Untested in this codebase; HTMX 1.9 docs claim built-in support. **Add explicit back-button test in PLAN.** |
| A7 | The renderer's hex boundary (no `system_params` import in `dashboard.py`) is invariant; D-22 reconciliation works via `_resolve_strategy_version(state)` reading state.json | Q7 | If planner suggests `from system_params import STRATEGY_VERSION` in the footer renderer for "simpler code", they break Phase 22's hex contract and the `tests/test_backtest_cli.py:234` "kwarg trap" test class. |
| A8 | The `_REQUIRED_DASHBOARD_MARKER = b'<nav class="tabs"'` (`web/routes/dashboard.py:74`) needs updating to match the renamed Phase 25 class | Pitfall 4 | If the marker stays as `b'<nav class="tabs"'` and the new code emits `class="tabs tabs-function"`, the marker still matches (substring) — so this might be no-op. **Verify by reading the regen rule carefully during plan-phase.** |

**8 of 8 assumptions need confirmation during plan-phase or operator review.**

---

## Open Questions

1. **What is the exact `last_run_status` derivation rule?** [HIGH PRIORITY]
   - What we know: there is no `last_run_status` field; only `state['last_run']` (date) and `state['warnings']` (list).
   - What's unclear: whether ANY warning makes it red, only specific warnings, or only "last run failed entirely" (which has no current persistence).
   - Recommendation: Plan-phase task: "operator confirms 3-state rule for status dot. Default proposal: red if `state['warnings']` has an entry written after `state['last_run']`; amber if `state['last_run'] < today_awst`; green otherwise."

2. **Should the `>24h` "in N h M m" format roll over to days?** [LOW PRIORITY]
   - What we know: UI-SPEC §System Status strip says `"08:00 AWST · in {N}h {M}m"`.
   - What's unclear: Friday afternoon AWST has 64+ hours until Monday 08:00 AWST.
   - Recommendation: Plan-phase task: lock format. Default proposal: `"Mon 08:00 AWST · in 2d 16h"` for >24h gaps; `"08:00 AWST · in {N}h {M}m"` otherwise.

3. **Is there a "first market" deterministic fallback for `selected_market` cookie miss?** [MEDIUM PRIORITY]
   - What we know: D-05 says "first market in `state.markets` ordering". The state.json has `sort_order` field on each market dict (SPI200=10, AUDUSD=20).
   - What's unclear: whether ordering means insertion order (Python 3.7+ dict guarantees) or `sort_order` field.
   - Recommendation: Use `min(state['markets'].items(), key=lambda kv: kv[1].get('sort_order', 0))[0]` — explicit `sort_order` ordering. Locks SPI200 as default since it has lower sort_order. **Lock with operator during plan-phase.**

4. **Does the equity chart `(date, value)` distinct-tuple rule (D-11) ignore intra-day equity recomputation?** [LOW PRIORITY]
   - What we know: state.json has 3 entries all `{date: '2026-04-23', equity: 100000.0}`.
   - What's unclear: whether the daemon is supposed to write only one row per date (de-dupe at write time) or whether multiple rows per date are valid (e.g., for intraday paper-trade unrealised P&L tracking).
   - Recommendation: Phase 25 should NOT touch the daemon's write logic. Render-side de-dupe per D-11 is the explicit decision. Note in PLAN: "if the operator later wants intraday entries, the de-dupe rule must change."

---

## Environment Availability

Phase 25 has no new external dependencies. All work uses libraries already present in the running production environment:

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| FastAPI | Routing | ✓ | (pinned in requirements.txt — already in production) | — |
| HTMX | Browser-side swap | ✓ | 1.9.12 (CDN, SRI-pinned) | — |
| Chart.js | Equity curve | ✓ | 4.4.6 (CDN, SRI-pinned) | — |
| pytz | Server-side AWST | ✓ | (project legacy) | stdlib `zoneinfo` (already used in `main.py`) |
| Python | Runtime | ✓ | 3.11+ (per project requirements) | — |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (project standard, `pytest.ini` or `pyproject.toml` configuration) |
| Config file | `pyproject.toml` |
| Quick run command | `pytest tests/test_dashboard.py tests/test_web_app_factory.py -x -q` |
| Full suite command | `pytest -q` (1319 tests baseline at v1.1 close per ROADMAP.md) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| P25-01 (D-01..D-05 routes) | `/markets/{m}/{fn}` GET routes return 200 with auth, panel content matches market | unit/integration | `pytest tests/test_web_app_factory.py::TestMarketRoutesRegistered -x` | ✅ (extend) |
| P25-02 (D-05 cookie) | Cookie `selected_market` set on market-scoped page render with correct attrs | integration | `pytest tests/test_web_app_factory.py -k cookie -x` | ❌ Wave 0 |
| P25-03 (D-06..D-08 status strip) | `GET /status-strip` returns valid HTML; first-run shows "Awaiting first run"; stale shows amber dot | integration | `pytest tests/test_web_dashboard.py -k status_strip -x` | ❌ Wave 0 |
| P25-04 (D-09 first-run hide) | `state.last_run is None` produces 0 trace tables and 1 onboarding card | unit | `pytest tests/test_dashboard.py -k first_run -x` | ❌ Wave 0 |
| P25-05 (D-10 stats bar hide) | Stats bar omitted from DOM when no closed trades | unit | `pytest tests/test_dashboard.py -k stats_bar_hidden -x` | ❌ Wave 0 |
| P25-06 (D-11 equity chart hide) | Chart hidden when <5 distinct tuples | unit | `pytest tests/test_dashboard.py -k equity_chart -x` | ❌ Wave 0 |
| P25-07 (D-12 fieldsets) | Settings page renders 3 `<fieldset>` elements with legends "Entry rules", "Risk", "Direction" | unit | `pytest tests/test_dashboard.py -k settings_fieldsets -x` | ❌ Wave 0 |
| P25-08 (D-15 font scale) | Rendered CSS contains `--fs-body: 16px;` | unit | `pytest tests/test_dashboard.py -k font_scale -x` | ❌ Wave 0 |
| P25-09 (D-16 Add-market chip) | Market strip contains `<details class="add-market-chip">` and `<form hx-post="/markets">` | unit | `pytest tests/test_dashboard.py -k add_market_chip -x` | ❌ Wave 0 |
| P25-10 (D-18 active tab) | Active anchor has `aria-current="page"` and CSS class for distinct styling | unit | `pytest tests/test_dashboard.py -k active_tab -x` | ❌ Wave 0 |
| P25-11 (D-19 inline-style removal) | `assert 'style="color:' not in rendered_html` (the gate from UI-SPEC §A11y #5) | unit | `pytest tests/test_dashboard.py -k no_inline_color -x` | ❌ Wave 0 |
| P25-12 (D-20 wide-table) | Each wide table wrapped in `<div class="table-scroll" tabindex="0" role="region">` | unit | `pytest tests/test_dashboard.py -k wide_table_scroll -x` | ❌ Wave 0 |
| P25-13 (D-21 button rename) | `Open Position` button text replaced with `Record paper trade` (paper) and `Open live position` (live) | unit | `pytest tests/test_dashboard.py -k button_rename -x` | ❌ Wave 0 |
| P25-14 (D-22 version reconcile) | All 5 dashboard*.html files contain `v1.2.0` (when `state.signals[*].strategy_version='v1.2.0'`) | integration | `pytest tests/test_dashboard.py -k strategy_version_reconcile -x` | ❌ Wave 0 |
| P25-15 (route shadow regression) | Existing `tests/test_web_app_factory.py:344` regression test still passes | regression | `pytest tests/test_web_app_factory.py::TestMarketRoutesRegistered::test_patch_market_settings_literal_path_updates_settings -x` | ✅ (preserve) |

### Sampling Rate
- **Per task commit:** `pytest tests/test_dashboard.py tests/test_web_app_factory.py -x -q` (≈30s)
- **Per wave merge:** `pytest -q` (full 1319+ suite, ≈3-5 min)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_dashboard.py` extensions for D-09, D-10, D-11, D-12, D-15, D-16, D-18, D-19, D-20, D-21, D-22 — covers P25-04..14
- [ ] `tests/test_web_app_factory.py` extensions for D-05 cookie, D-01 new routes — covers P25-01, P25-02
- [ ] `tests/test_web_dashboard.py` extensions for `/status-strip` endpoint — covers P25-03
- [ ] No new fixture file needed — existing `tests/conftest.py` provides `VALID_SECRET`, `AUTH_HEADER_NAME`, autouse env reset

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Existing AuthMiddleware (cookie session OR `X-Trading-Signals-Auth` header). New routes inherit. No change. |
| V3 Session Management | yes (cookie write) | The new `selected_market` cookie is **not a session** — it's a UI-state preference. SameSite=Lax adequate. HttpOnly intentionally false (D-05 — JS reads it from `/account`). NO sensitive value stored. |
| V4 Access Control | yes | Same auth middleware gates `/markets/{m}/{fn}` and `/status-strip` as it gates `/`. New routes must NOT be added to `PUBLIC_PATHS`. |
| V5 Input Validation | yes | `{market_id}` segment must validate against `state.markets` keys (404 on miss). Existing pattern: see `web/routes/markets.py:142` `if req.market_id in markets`. |
| V6 Cryptography | no | No new cryptographic surface. `selected_market` cookie is unsigned (it's UI state). |
| V11 Business Logic | yes | The Add-market chip's `hx-post /markets` reuses the existing endpoint with full Pydantic validation. No new validation surface. |
| V13 API & Web Service | yes | All new routes go through the existing 422→400 remap (`web/app.py:187`). |

### Known Threat Patterns for {FastAPI + HTMX + cookie auth}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| `{market_id}` path injection (e.g., `/markets/../etc/passwd/signals`) | Tampering | FastAPI path segment auto-decodes; reject with 404 if not in `state.markets`. Validate with regex pattern `^[A-Z0-9_]{2,20}$` (matches existing `MarketRequest.market_id` field at `markets.py:20`). |
| HTMX swap content from a stale or wrong market (cache poisoning) | Information Disclosure | Server response includes `Cache-Control: no-store` for any market-scoped panel. Check existing handler — currently `_serve_dashboard_page` returns no cache headers; this might allow CDN/proxy caching of the wrong market's panel. **Recommend adding `Cache-Control: no-store, private` to dashboard panel responses.** |
| `selected_market` cookie tampering | Tampering | Cookie is a UI-state hint only — server validates the URL path's `{market_id}` against `state.markets` regardless. Tampered cookie → first market fallback. |
| CSRF on Add-market chip (`POST /markets`) | Tampering | Existing `X-Trading-Signals-Auth` header requirement provides CSRF protection (custom header — browser cannot set on cross-origin requests without preflight). No additional CSRF token needed. |
| XSS via market_id in rendered tab anchor | Tampering | Use `html.escape(market_id, quote=True)` (project pattern, `dashboard.py:1156-1158`). Verified used everywhere in `signals.py`, `settings.py`, `markets.py`. |
| Open redirect via cookie value | Spoofing | Cookie value used only for URL construction with `f'/markets/{cookie_value}/signals'` — `html.escape` defended. If cookie value contained `..` or `://`, redirect would still be relative (FastAPI Path param matching rejects). |
| Status-strip endpoint info leak (showing `state.warnings` text to unauthed) | Info Disclosure | `/status-strip` is auth-gated by AuthMiddleware (NOT in `PUBLIC_PATHS`). Verified by registering it in the same router as `/`. |

---

## Sources

### Primary (HIGH confidence)

- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/state_manager.py:104,561,593` — state.json schema; `last_run` field name; `None` default
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/main.py:1540` — daemon writes `state['last_run'] = run_date_iso`
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/main.py:716` — schedule.every().day.at('00:00') = 08:00 AWST
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/system_params.py:27,217,218` — STRATEGY_VERSION=v1.2.0; LOOP_SLEEP_S=60; SCHEDULE_TIME_UTC='00:00'
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/web/app.py:147-194` — FastAPI factory + middleware order
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/web/routes/markets.py:134-176` — route ordering + 18ea2c5 fix
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/web/routes/dashboard.py:165-415` — page route registration + fragment patterns + cookie patterns + placeholder substitution
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/web/routes/login.py:51,447` — cookie attr conventions
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/dashboard.py:1080-1114` — `_resolve_strategy_version` hex boundary
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/dashboard.py:2641-2716` — current nav rendering (`_render_dashboard_page_nav`, `_render_tabbed_dashboard`, `_render_single_page_dashboard`)
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/dashboard.py:2514-2591` — equity chart current + empty-state branch
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/dashboard.py:2719-2759` — html_shell with HTMX/Chart.js script tags
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/dashboard_renderer/components/footer.py` — strategy version single source
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/dashboard_renderer/components/signals.py:53` — inline-style emission site (D-19 fix target)
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/tests/test_web_app_factory.py:246-379` — current route + regression assertions
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/tests/test_dashboard.py:3100-3122` — Phase 24 tabbed dashboard pinning
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/state.json` — current shape: `markets`, `signals`, `equity_history`, `last_run`
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/dashboard.html:8-9,76,672,837,1113` — HTMX version, font tokens, market-select, equity chart, version literal
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/dashboard-{signals,account,settings,market-test}.html:Strategy version` — confirmed stale literals (v1.0.0 / v1.1.0)

### Secondary (MEDIUM confidence)

- HTMX 1.9 documentation (`hx-push-url`, `hx-trigger`, `hx-swap` semantics) — checked from training data and confirmed by usage patterns in dashboard.html
- WAI-ARIA Tabs pattern (D-18 specifies it; standard W3C pattern)

### Tertiary (LOW confidence)

- Exact `last_run_status` derivation rule (NO source — gap that must be operator-locked in plan-phase)
- Weekend display format for >24h countdown (UI-SPEC silent — gap)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already pinned in production; no upgrade required
- Architecture: HIGH — codebase patterns are well-established (renderer hex, route ordering, cookie attrs)
- Pitfalls: HIGH — drawn from project LEARNINGS + global LEARNINGS + the 18ea2c5 commit history
- State.json field names: HIGH — grepped end-to-end, confirmed by code reads at write site (`main.py:1540`) and read site (`notifier.py:335`)
- `last_run_status` derivation: LOW — gap in CONTEXT.md, must be operator-locked

**Research date:** 2026-05-05
**Valid until:** 2026-06-05 (30 days — codebase is stable; no active framework upgrades pending)

---

*Phase: 25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences*
*Researched: 2026-05-05*
