# Phase 26: Pattern Map — Multi-tab fix + cleanup

**Mapped:** 2026-05-07
**Files Phase 26 will touch:** 8
**Analogs found:** 8 / 8 (every fix has prior-art in repo)

Caveman terse. Quote anchors. Copy where stated; invent only where flagged.

---

## File Classification

| Phase 26 target | Role | Data flow | Closest analog | Match |
|---|---|---|---|---|
| `dashboard.py:1961` `_render_page_body` | renderer-dispatcher | request→ctx→html | `dashboard.py:2047` `_render_single_page_dashboard` (already threads `ctx.active_market`) | exact |
| `dashboard_renderer/components/signals.py:6` `render_signal_cards` | per-market loop | state→html | `dashboard_renderer/components/nav.py:107` market loop using `markets.keys()` | role-match |
| `dashboard_renderer/components/settings.py:6` `render_settings_tab` | per-market loop | state→html | same | role-match |
| `dashboard_renderer/components/settings.py:117` `render_market_test_tab` | first-market form | state→html | settings.py:128 already uses `next(iter(display_names), None)` | exact |
| `web/routes/dashboard.py:235-284` `_serve_market_scoped_page` | route handler | request→bytes | `web/routes/dashboard.py:500-562` `_serve_dashboard_content` (canonical substituter) | exact |
| `dashboard_renderer/api.py:58-113` `render_dashboard` mixed return | renderer API | flag→str-or-None | `render_dashboard_as_str` (str-only) + `render_dashboard` (file-only) — split already exists, just leaks via `htmx_panel_only` | role-match |
| `dashboard_renderer/api.py:143-165` `render_dashboard_page` | renderer API | state→file | `api.py:22-43` `_build_render_context` already takes `active_market` kwarg | exact |
| `dashboard_renderer/components/header.py:64-69` session widget | sub-component | bool-or-None→html | `web/routes/dashboard.py:511-524` `_render_signout_button`/`_render_session_note` substitution | exact |
| `web/routes/dashboard.py:74,119` `_is_stale` | cache marker | mtime+marker→bool | self (only one stale check; no analog for sibling sweep) | partial — invent |
| `web/routes/dashboard.py:228-233` `_set_market_cookie` sanitiser | cookie writer | str→str | `markets.py:20` Pydantic `^[A-Z0-9_]{2,20}$` regex (write-side) | role-match |
| `web/routes/dashboard.py:341-346` referer-derived `active_function` | fragment route | request→html | `web/routes/dashboard.py:336` `request.cookies.get('selected_market')` (cookie-driven) | role-match |
| `web/routes/markets.py:158` `add_market` `signals[id] = 0` | state writer | dict→state | `main.py:1489` `state['signals'][state_key] = {…full dict…}` | exact |
| `tests/test_deploy_sh.py:93,129,133` regex | shell-grep test | text→regex | self — relax regex | exact |
| `.gitignore` | config | text | self — extend | exact |

---

## B1. `_render_page_body` ignores `ctx.active_market`

**Analog:** `dashboard.py:2047-2080` `_render_single_page_dashboard` already does it right.
- Reads `getattr(ctx, 'active_market', None)` at line 2063.
- Falls back to `_first_market_id(ctx.state)` at line 2065 (imported from `dashboard_renderer.components.nav`).
- Special-cases `account` (no market wrapper) at line 2064 + 2077.

**Copy this fallback shape into the three render-function leaves.** Currently `_render_page_body` calls `_render_signal_cards(state)`, `_render_settings_tab(state)`, `_render_market_test_tab(state)` — passing only `state`, not `active_market`. Need to:

1. Extend `_render_page_body(ctx, page)` to forward `ctx.active_market` to each lambda.
2. Add `active_market: str | None = None` parameter to:
   - `dashboard_renderer/components/signals.py:6` `render_signal_cards`
   - `dashboard_renderer/components/settings.py:6` `render_settings_tab`
   - `dashboard_renderer/components/settings.py:117` `render_market_test_tab`
3. Inside each, when `active_market` is set, filter `d._display_names(state)` to `{active_market: display}` only.

**First-market fallback pattern (copy verbatim from `nav.py:19-26`):**
```python
def _first_market_id(state: dict) -> str:
    markets = state.get('markets', {}) or {}
    if not markets:
        return ''
    return next(iter(markets))
```
Already used identically in `settings.py:128` (`next(iter(display_names), None)`) — same idiom.

**No invention needed.** Pure thread + filter.

---

## B2. `_serve_market_scoped_page` skips placeholder substitution

**Analog (canonical):** `web/routes/dashboard.py:500-562` `_serve_dashboard_content`. This is the **single existing substitution helper**. It handles all 5 placeholder kinds:

| Placeholder | Resolved at | Lines |
|---|---|---|
| `{{WEB_AUTH_SECRET}}` | `os.environ.get('WEB_AUTH_SECRET','')` | 504-505 |
| `{{SIGNOUT_BUTTON}}` / `{{SESSION_NOTE}}` | `_is_cookie_session(request)` branch | 511-524 |
| `{{TRACE_OPEN_SPI200}}` / `{{TRACE_OPEN_AUDUSD}}` | `_resolve_trace_open(request)` cookie | 526-537 |

`_serve_market_scoped_page` (235-284) builds `body` via `render_dashboard_as_str` → `body.encode()` and **never calls `_serve_dashboard_content`**. That's the bug.

**Fix shape (most eloquent — copy `_serve_dashboard_content` discipline):**

Refactor `_serve_dashboard_content` to take `content: bytes` (already does). Both `_serve_dashboard_root` and `_serve_dashboard_page` already funnel through it. Make `_serve_market_scoped_page` do the same:

```python
# instead of: return Response(content=body.encode('utf-8'), …)
return _serve_dashboard_content(
    request=request,
    content=body.encode('utf-8'),
    fragment=None,    # market-scoped path doesn't support ?fragment=
)
# then set cookie + cache-control headers on the returned Response
```

But `_serve_dashboard_content` currently handles `fragment`-extraction and returns the Response itself, which conflicts with cookie-setting. Two clean options:

**(A) Most eloquent — extract `_substitute(content: bytes, request: Request) -> bytes`** out of `_serve_dashboard_content` (the lines 504-537 block). Then both `_serve_dashboard_content` and `_serve_market_scoped_page` call it. Locality of behaviour: substitution rule lives in one place, returned as bytes; response-shaping (fragment extraction, cookies, cache-control) stays per-route.

**(B) Pragmatic — call `_serve_dashboard_content(fragment=None)` from market-scoped, then mutate returned response headers.** Shorter diff but couples cookie-setting to a downstream return.

**Recommend (A).** Single private helper at module scope; tested once via `TestAuthSecretPlaceholderSubstitution`-style tests against the helper directly.

**Copy:** Lines 504-537 verbatim into a new `_substitute(content, request) -> bytes` private function. `_serve_dashboard_content` becomes ~5 lines (call helper, then fragment extraction).

---

## B3. Header session-widget placeholder leak

**Analog:** `dashboard_renderer/components/header.py:64-69`:
```python
if is_cookie_session is None:
    auth_widget = '{{SIGNOUT_BUTTON}}{{SESSION_NOTE}}'  # punt to web layer
elif is_cookie_session:
    auth_widget = d._render_signout_button()
else:
    auth_widget = d._render_session_note()
```

The `is_cookie_session is None` branch is the "let the web layer substitute later" path. It works for `dashboard.html` (file-on-disk → `_serve_dashboard_content` substitutes). It **fails for `_serve_market_scoped_page`** because nothing substitutes.

**Two paths, B3 dissolves into B2:**

- **If B2 fix (A) lands** (extract `_substitute` helper called from market-scoped path), B3 disappears — the same substitution applies. Zero extra work.
- **If B2 fix (B) lands** (cookie-mutate downstream), still works because `_serve_dashboard_content` does the substitution.

**Most eloquent:** B2 fix (A) eats B3 for free. Recommend it.

**Alt path (riskier):** Plumb `is_cookie_session` from `request` through `render_dashboard_as_str` → `_render_header_and_body(is_cookie_session=…)`. This requires `dashboard_renderer/api.py:135-140` (currently passes `is_cookie_session=None`) to take a real bool. But that requires importing/calling `_is_cookie_session` from inside the renderer — which violates the **hex-lite boundary** noted in `LEARNINGS.md` 2026-04-27: "Hex-boundary check: passing session-aware bool to dashboard.py is OK; cookie-decoding inside dashboard.py is NOT". Cookie validation must stay in `web/routes/`. So this alt path means: caller (`_serve_market_scoped_page`) computes the bool via `_is_cookie_session(request)` and passes it as kwarg.

**Recommend the substitute helper (B2-A).** It keeps the existing punt-to-web pattern intact rather than threading new kwargs through 3 functions.

---

## B4. Three deploy_sh tests fail

**Analog:** Same file, same regex idiom — just relax the pattern.

- `tests/test_deploy_sh.py:94`: `r'\.venv/bin/pip install -r requirements\.txt'`
- `tests/test_deploy_sh.py:129`: same
- `tests/test_deploy_sh.py:133`: same

**Fix (verbatim):** `r'\.venv/bin/(?:python -m )?pip install -r requirements\.txt'` per CONTEXT B4.

**Copy nothing — invent only the regex tweak.** Three call sites in one file.

---

## R1. `_is_stale` only checks `dashboard.html`

**Analog:** `web/routes/dashboard.py:74` `_REQUIRED_DASHBOARD_MARKER` + `:101-123` `_is_stale`. The marker pattern works for `dashboard.html` only.

**No existing pattern for sibling-sweep.** This is **invention territory.**

Two-design choice (planner picks, label most eloquent):

- **(α)** `_is_stale_for(page_output: str) -> bool` — same body, parameterised by path. Each `_serve_dashboard_page` calls `_is_stale_for(page_output)`. Marker check runs against *each* sibling. **Most eloquent — locality of staleness rule on a per-file basis, no implicit coupling between `dashboard.html` and siblings.**
- **(β)** Bump marker once globally; on `dashboard.html` regen, force-regen all 4 siblings. Today's behaviour, but only on `dashboard.html` cache miss. Cheaper diff but keeps the tight coupling.

Recommend α. Sibling regen path already exists in `api.py:106-112` (loop writing 4 siblings) — α just gates each on its own marker.

---

## R2. `render_dashboard()` mixed return type

**Analog:** `dashboard_renderer/api.py:116-140` `render_dashboard_as_str` already does the str-return shape correctly. `render_dashboard` (58-113) is the file-write shape correctly — *except* the `htmx_panel_only=True` branch at line 85-89 which returns `str` instead.

**Fix shape (CONTEXT R2 says):** split into:
- `render_dashboard_files(state, …) -> None` — pure file-write (strip `htmx_panel_only` arg).
- `render_panel_html(state, …) -> str` — wraps `render_panel_only(ctx)` from `dashboard_renderer/pages.py:20-37` (which already exists and returns str).

**Caller update:** `web/routes/dashboard.py:259-266` currently calls `render_dashboard(htmx_panel_only=True)`. Switch to `render_panel_html(state, …)`.

**Copy:** existing `render_panel_only` in `pages.py:20-37` is the body of the new `render_panel_html`; just promote to `api.py` as a public name.

---

## R3. `render_dashboard_page` never threads `active_market`

**Analog:** `api.py:22-43` `_build_render_context` **already accepts `active_market` kwarg** (line 28). Caller `render_dashboard_page` at line 153-157 just doesn't forward it. Trivial.

**Fix:**
```python
def render_dashboard_page(
    state, page, out_path=Path('dashboard.html'),
    now=None, is_cookie_session=None, trace_open_keys=None,
    *, active_market: str | None = None,   # ADD
) -> None:
    ctx = _build_render_context(
        state=state, now=now, trace_open_keys=trace_open_keys,
        active_function=page,                # also missing — page IS the active function
        active_market=active_market,
    )
```

**But the cache key isn't market-keyed** — `_PAGE_OUTPUTS` writes to a single path per page. CONTEXT R3 explicitly flags: "drop on-disk cache for market-scoped pages OR include `active_market` in cache key."

**Most eloquent:** drop the cache for market-scoped pages — `_serve_market_scoped_page` already does in-memory `render_dashboard_as_str` per-request with `Cache-Control: no-store`. The on-disk siblings (`dashboard-signals.html` etc) only serve `/signals`, `/settings`, `/market-test` (no `/markets/{m}/…` prefix). Those routes call `_serve_dashboard_page` and use the first-market fallback. Add `active_market=_first_market_id(state)` at line 372 when calling `dashboard.render_dashboard_page` so the fallback is explicit.

---

## R4. `nav_mode` dead code + dead `_render_dashboard_page_nav` + dead `_render_market_selector`

**Analog (deprecation pattern):** `.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-03-SUMMARY.md:78`:

> "`_render_dashboard_page_nav`: marked deprecated (definition retained for Plan 25-09 cleanup)"

Phase 25 staged: mark DEPRECATED docstring → leave body → remove in cleanup phase. Phase 26 IS that cleanup phase.

**Callers audit (already done — copy verdict):**
- `_render_market_selector` (`dashboard.py:770`): grep confirms 0 non-self callers (only the comment at line 1975 mentions removal).
- `_render_dashboard_page_nav` (`dashboard.py:2083`): grep confirms 0 callers; `nav.py:129` docstring says "Replaces dashboard._render_dashboard_page_nav".
- `nav_mode` parameter on `_render_single_page_dashboard` (line 2050) and `render_dashboard_page` (api.py): only ever passed `'web'` or `'file'`; both branches actually used in `api.py:106-112` sibling loop (`nav_mode='file'`). NOT dead — just under-tested. Keep.

**Fix:** Delete `_render_market_selector` (770-782) and `_render_dashboard_page_nav` (2083-end-of-fn, ~30 lines). `nav_mode` stays — `nav.py` consumes it via `render_two_axis_nav`? Actually no — `render_two_axis_nav` doesn't take `nav_mode`. Re-audit: `_render_single_page_dashboard:2050` accepts `nav_mode` but never uses it (line 2052-2080 doesn't reference). Likely dead inside that function but live in the legacy `_render_dashboard_page_nav`. Removing `_render_dashboard_page_nav` orphans `nav_mode` everywhere. **Drop the param.**

**Copy:** Phase 25's deprecation→cleanup precedent. No new pattern.

---

## R5. `add_market` writes `signals[id] = 0`

**Analog:** `main.py:1489-1499` — the canonical signal-write shape:
```python
state['signals'][state_key] = {
    'signal': new_signal,
    'signal_as_of': signal_as_of,
    'as_of_run': run_date_iso,
    'last_scalars': scalars,
    'last_close': bar['close'],
    'strategy_version': system_params.STRATEGY_VERSION,
    'ohlc_window': ohlc_window,
    # …
}
```

`web/routes/markets.py:158` writes `state.setdefault('signals', {})[req.market_id] = 0` — int sentinel, doesn't match.

**Two options:**
- **(α)** Write the same dict shape with sentinel-zero values: `{'signal': 0, 'signal_as_of': None, 'as_of_run': None, 'last_scalars': {}, 'last_close': None, 'strategy_version': system_params.STRATEGY_VERSION}`. Then renderer's defensive int branch (`signals.py:35-39`) becomes unreachable for newly-added markets.
- **(β)** Document the int-sentinel as intentional and tighten `signals.py:35` defensive branch to assert/log on int.

**Most eloquent:** α. Locality of contract — `add_market` produces shape `run_daily_check` consumes; no cross-module sentinel agreement. Compose naturally because every other write site uses the dict shape. Renderer's int-fallback becomes dead code (delete in same plan).

---

## R6. `markets-strip` derives `active_function` from Referer

**Analog:** Same handler reads `selected_market` via `request.cookies.get('selected_market', '')` at line 336. Cookie-driven, not header-driven. Mirror that pattern for `active_function`.

**Fix shape (most eloquent):** the `hx-get="/markets-strip"` is emitted from `nav.py:104-105` on the strip itself. Pass active_function as a query param:

```python
# nav.py:104-105 strip element
hx-get="/markets-strip?active_function={active_function}"  # explicit
```

Then `web/routes/dashboard.py:341` reads `request.query_params.get('active_function', 'signals')` — drop the Referer fallback.

**Copy:** `_resolve_trace_open` cookie pattern at `web/routes/dashboard.py:151-163` (allowlist-validate then use). Apply same allowlist to `active_function`: `{'signals', 'account', 'settings', 'market-test'}`.

---

## R7. `selected_market` cookie sanitiser too permissive

**Analog (write side):** `web/routes/markets.py:20` Pydantic `Field(pattern=r'^[A-Z0-9_]{2,20}$')`. This is the canonical market_id regex.

**Fix shape:** mirror exactly on the read path. Replace `web/routes/dashboard.py:228-233`:

```python
import re
_MARKET_ID_RE = re.compile(r'^[A-Z0-9_]{2,20}$')

def _set_market_cookie(response, market_id):
    if not market_id or not _MARKET_ID_RE.fullmatch(market_id):
        return
    response.headers['Set-Cookie'] = f'selected_market={market_id}{_MARKET_COOKIE_ATTRS}'
```

**Also tighten the read site:** `web/routes/dashboard.py:336` reads `request.cookies.get('selected_market', '')` and only checks `active_market not in markets`. Add the regex match before lookup so a malformed cookie is dropped, not used to query state.

**Copy:** `_resolve_trace_open:151-163` allowlist-validation pattern (already in this file).

---

## C1. `.gitignore` cleanup + `auth.json` audit

**Analog (current `.gitignore`):**
```
state.json
auth.json
dashboard.html, dashboard-*.html
last_email.html
.env, .venv/, __pycache__/, *.pyc, .pytest_cache/, .ruff_cache/
.planning/backtests/data/
```

`auth.json` is **already gitignored** (line 2). Audit means: `git log --all --full-history -- auth.json` to confirm it was never committed. If clean → just rotate any real secret it might contain on disk. CONTEXT C1 mandates this audit step.

**Untracked artifacts to add to .gitignore (extending existing pattern groups):**

| Add | Group | Rationale |
|---|---|---|
| `.DS_Store` | OS junk | macOS finder metadata; appears in `backtest/.DS_Store` too — use `**/.DS_Store` |
| `_debug_new_dashboard.html` | runtime debug | matches `last_email.html` rationale |
| `.agents/` | agent tool dirs | Ruflo/Claude-Flow runtime |
| `.claude-flow/` | agent tool dirs | same |
| `.codex/` | agent tool dirs | same |
| `.cowork/` | agent tool dirs | same |
| `.cursor/` | agent tool dirs | same |
| `.mcp.json` | agent config | per-machine MCP server registration |
| `.playwright-mcp/` | agent tool dirs | same |

**Decide-per-file:**
- `state.json` — already ignored line 1.
- `AGENTS.md` — CONTEXT says "documentation; commit or move to `.planning/`". Move to `.planning/AGENTS.md` (matches `.planning/`-as-process-docs convention) **OR** commit at root if it's instructions. Defer to operator.
- `last_email.html` — already ignored line 12.

**Copy:** existing comment style at lines 3-6 (multi-line rationale) and lines 20-21 (Phase-tagged comment).

---

## C2/C3. Dead code removal

See R4 above. Same pattern as Phase 25 → Plan 25-03 → Plan 25-09 staging: deprecation marker → callers audited via grep → final delete in cleanup phase. Phase 26 is the cleanup phase.

**Grep verifier (copy from LEARNINGS pattern):**
```bash
grep -rn "_render_market_selector\|_render_dashboard_page_nav" --include="*.py" .
# expected: 0 matches after cleanup
```

---

## C4. `25-VERIFICATION.md` stale

**Analog:** Phase 25 closing convention. `25-11-gap-closure-SUMMARY.md` exists and asserts gaps closed. Either:
- Re-run `gsd-verifier` against current main → produces fresh `25-VERIFICATION.md`. **Most eloquent — single source of truth, no narrative drift.**
- Append a "Superseded by 25-11 gap closure" section. Cheaper, but leaves contradictory sections in one file.

Recommend re-verify.

**Copy:** `.planning/phases/*/25-VERIFICATION.md` structure (already in repo).

---

## Test patterns (cross-cutting, applies to B1, B2, B3, R5, R7)

**Analog:** `tests/test_web_dashboard.py` `TestAuthSecretPlaceholderSubstitution:407-499` — gold standard.

Pattern in this repo:
1. `client_with_dashboard` fixture (`tests/test_web_dashboard.py:58-94`) — `monkeypatch.chdir(tmp_path)`, stub `state_manager.load_state`, stub `dashboard.render_dashboard` to track calls + write deterministic body.
2. `auth_headers` fixture (`tests/test_web_dashboard.py:47-55`) — `{AUTH_HEADER_NAME: VALID_SECRET}` with `VALID_SECRET = 'a' * 32`.
3. Per test: write a synthetic `dashboard.html` with the placeholder (`(tmp / 'dashboard.html').write_text(...)`), then `client.get(url, headers=auth_headers)`, then assert.
4. Negative-leak assertion: `assert '{{WEB_AUTH_SECRET}}' not in r.text`.

**For B1 (eyebrow per market):**
```python
def test_market_settings_eyebrow_is_only_active_market(self, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('WEB_AUTH_SECRET', VALID_SECRET)
    monkeypatch.setenv('WEB_AUTH_USERNAME', 'marc')
    from web.app import create_app
    client = TestClient(create_app())
    resp = client.get('/markets/AUDUSD/settings', headers={AUTH_HEADER_NAME: VALID_SECRET})
    assert resp.status_code == 200
    assert 'AUD / USD SETTINGS' in resp.text
    assert 'SPI 200 SETTINGS' not in resp.text   # the bug
    assert 'ES MINI SETTINGS' not in resp.text
```
This is the **acceptance test for B1**. Mirror for `/markets/SPI200/signals`, `/markets/ESM/market-test`.

**For B2 (zero placeholder leak):**
```python
def test_market_scoped_response_has_no_template_markers(self, monkeypatch, tmp_path):
    # … same setup …
    resp = client.get('/markets/SPI200/signals', headers=auth_headers)
    import re
    assert resp.status_code == 200
    assert not re.search(r'\{\{[A-Z_]+\}\}', resp.text), \
        f"placeholder leak: {re.findall(r'\\{\\{[A-Z_]+\\}\\}', resp.text)}"
```

This matches CONTEXT acceptance #6: `grep -rn '{{[A-Z_]\+}}' …` returns zero.

**Pre-existing market-route test scaffold:** `tests/test_web_app_factory.py:388-505` (`TestPhase25MarketRoutes`, `TestPhase25SelectedMarketCookie`). Same fixture setup, same `monkeypatch.chdir(tmp_path)` pattern. **Add new B1/B2 test classes alongside.**

---

## Shared patterns (apply across plans)

### Hex-boundary discipline (LEARNINGS 2026-04-27)
`dashboard.py` and `dashboard_renderer/` may NOT import from `web/middleware/`, `itsdangerous`, or read auth cookies. All session-aware state arrives as primitives (bool, str). The `_serve_market_scoped_page` fix (B2) computes `_is_cookie_session(request)` in the route layer; renderer layer remains primitive-only.

### Local imports inside route handlers
**Source:** `web/routes/dashboard.py:414-417, 244, 259, 269, 308, 332`. Convention: `import dashboard`, `import state_manager`, `from dashboard_renderer.api import …` are LOCAL (inside the function), enforced by `tests/test_web_healthz.py::TestWebHexBoundary::test_web_adapter_imports_are_local_not_module_top`. Apply to the new `_substitute` helper if it imports `dashboard._render_signout_button`.

### Atomic file write
**Source:** `dashboard_renderer/api.py:98, 112` `d._atomic_write_html`. Already used. New code that touches sibling files (R1) must reuse it, not raw `path.write_text`.

### Logging prefix
**Source:** `web/routes/dashboard.py:374` `'[Web] dashboard regen failed for page=%s, …'`. New WARN logs in this file: `[Web]` prefix.

---

## No analog found (planner must invent)

| Concern | Why no analog |
|---|---|
| Per-sibling marker check (R1) | Marker pattern was single-file from Phase 14; multi-file sweep is new. CONTEXT R1 sketches both shapes — planner picks. |

---

## Metadata

**Analog search scope:** `web/routes/`, `dashboard_renderer/`, `dashboard.py`, `tests/`, `.planning/phases/25-*/`, `main.py` (signal write only).
**Files scanned:** 14 (Read), plus grep across `tests/`, `web/`, `dashboard_renderer/`.
**No source files modified.** Read-only pass.
**Pattern extraction date:** 2026-05-07
