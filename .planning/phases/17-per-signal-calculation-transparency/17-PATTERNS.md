# Phase 17: Per-signal Calculation Transparency — Pattern Map

**Mapped:** 2026-04-30
**Files analyzed:** 19 new symbols / 9 files touched
**Analogs found:** 18 / 19 (1 designed-from-scratch — the cookie allowlist filter has no in-repo precedent)

## File Classification

| New symbol / file | Layer | Role | Data flow | Closest analog | Match quality |
|-------------------|-------|------|-----------|----------------|---------------|
| `STATE_SCHEMA_VERSION = 5` | system_params.py | constant bump | none | `STATE_SCHEMA_VERSION = 4` (Phase 22) | exact |
| `_migrate_v4_to_v5` | state_manager.py | migration helper | dict transform | `_migrate_v3_to_v4` | exact |
| `MIGRATIONS[5]` entry | state_manager.py | dispatch wiring | dict | `MIGRATIONS[4]` (Phase 22) | exact |
| main.py signal-row writer extension | main.py | signal-row write site | state mutation | the existing block at `main.py:1273-1280` | exact |
| `_TRACE_FORMULAS` module dict | dashboard.py | constant catalogue | none | `_INSTRUMENT_DISPLAY_NAMES`, `_DEFAULT_STRATEGY_VERSION`, `_EXIT_REASON_DISPLAY` | exact |
| `_format_indicator_value(value, seed_required, bars_available) -> str` | dashboard.py | pure helper | scalar in / str out | `_fmt_currency`, `_fmt_percent_signed` | role-match (math.isnan branching is new) |
| `_resolve_trace_open_keys(state, trace_open_keys)` | dashboard.py | helper | list → set | `_resolve_strategy_version` | exact |
| `_render_trace_inputs(ohlc_window)` | dashboard.py | render helper | dict → HTML str | `_render_positions_table`, `_render_trades_table` | exact |
| `_render_trace_indicators(indicator_scalars, bars_available)` | dashboard.py | render helper | dict → HTML str | `_render_signal_cards` | exact |
| `_render_trace_vote(indicator_scalars, signal)` | dashboard.py | render helper | dict + int → HTML str | `_render_signal_cards` (badge / colour map dispatch) | exact |
| `_render_trace_panels(signal_dict, instrument_key, is_open)` | dashboard.py | orchestrator helper | composes 3 render helpers | `_render_signal_cards` body composition + `_render_header` 3-way `is_cookie_session` switch | exact |
| `render_dashboard(... trace_open_keys: list[str] = [])` signature extension | dashboard.py | signature extension | new optional kwarg | `render_dashboard(... is_cookie_session: bool \| None = None)` (Phase 16.1) | exact |
| FastAPI route cookie read + allowlist filter | web/routes/dashboard.py | request-response | request → render arg | `_is_cookie_session` (validates `tsi_session`) + Phase 16.1 placeholder substitution | role-match (allowlist filter has no in-repo precedent) |
| Cookie set in vanilla JS | dashboard.py `<script>` | browser-side write | DOM event → cookie | `_HANDLE_TRADES_ERROR_JS`, equity-chart inline `<script>` | exact |
| CSS additions (`.trace-panel`, `.trace-badge.{plus/minus/zero/pass/fail}`, `.formula-row[hidden]`, `.trace-indicator-name { cursor: pointer }`) | dashboard.py `_INLINE_CSS` | styles | none | existing `_INLINE_CSS` palette section | exact |
| Vanilla JS click + toggle handler block (≤20 lines) | dashboard.py `<script>` | browser-side handler | DOM event → state | equity-chart `(function() { ... })()` inline IIFE script | role-match (DOMContentLoaded wrapper is new) |
| `tests/test_state_manager.py::TestMigrateV4ToV5` | tests | test class | unit | `TestMigrateV3ToV4` | exact |
| `tests/test_main.py::TestRunDailyCheckPersistsTracePayload` | tests | test class | unit | `TestRunDailyCheckTagsStrategyVersion` | exact |
| `tests/test_dashboard.py::TestTracePanels` | tests | test class | unit + render | `TestRenderDashboardStrategyVersion` (golden + state-driven) + `TestGoldenSnapshot` | exact |
| `tests/fixtures/dashboard/sample_state_v5.json` | fixtures | golden state | static JSON | `tests/fixtures/dashboard/sample_state.json` | exact |

## Pattern Assignments

### `STATE_SCHEMA_VERSION = 5`

**Closest analog:** `system_params.py:121` — `STATE_SCHEMA_VERSION: int = 4`
**Why this analog:** Same constant; phase 22 just bumped it 3→4 with a trailing-comment delta. We repeat that exact one-line edit.
**Pattern to copy:**
- Single-line typed assignment with a trailing inline comment listing every phase that bumped it.
- Comment format: `bump on each schema change (STATE-04); Phase 14 → v3 ...; Phase 22 → v4 ...; Phase 17 → v5 (ohlc_window + indicator_scalars on signal rows; D-08)`.
- No dedicated section header — sits inside the existing "Phase 3 constants — state persistence" block.
**Pattern to adapt:**
- Append a new `; Phase 17 → v5 ...` clause to the inline comment.
**Hex-boundary check:** clean — system_params is the constants hex; no imports added.

---

### `_migrate_v4_to_v5(s: dict) -> dict`

**Closest analog:** `state_manager.py:157-182` — `_migrate_v3_to_v4`
**Why this analog:** Phase 22's same-shape backfill onto dict-shaped signal rows. CONTEXT D-08 explicitly mirrors its contract.
**Pattern to copy:**
- Docstring: 4 paragraphs covering (1) the phase + scope, (2) idempotency rule preserving operator-set fields, (3) skip-int-shape rule citing Phase 3 reset_state legacy + main.py D-08 upgrade branch, (4) D-15 silent migration disclaimer ("no append_warning, no log line").
- Body shape: `signals = s.get('signals', {})` → iterate `signals.values()` → `if isinstance(sig, dict) and 'field' not in sig: sig['field'] = default`.
- Returns `s` (the in-place-mutated dict). No deep copy.
**Pattern to adapt:**
- Iterate `signals.items()` (need both inst_key and sig) — Phase 22 only iterated `.values()` because the version string didn't depend on the key.
- Two field defaults instead of one: `sig['ohlc_window'] = []`, `sig['indicator_scalars'] = {}`.
- Independent `'field' not in sig` guards per field (idempotent for partial-migration scenarios — covers the case where a manual edit added one key but not the other).
**Hex-boundary check:** clean — state_manager is the I/O hex; uses only `dict` ops.

---

### `MIGRATIONS[5] = _migrate_v4_to_v5` dispatch entry

**Closest analog:** `state_manager.py:185-190` — the `MIGRATIONS: dict = {1: ..., 2: ..., 3: ..., 4: _migrate_v3_to_v4}` block
**Why this analog:** Identical pattern; just append one key.
**Pattern to copy:**
- Trailing inline comment: `# Phase NN D-XX: <one-line summary of what's backfilled>`.
- Key = the *target* schema version (the version after the migration runs), value = the migration callable.
**Pattern to adapt:**
- Add `5: _migrate_v4_to_v5,  # Phase 17 D-08: ohlc_window + indicator_scalars on signal rows` to the dict literal.
**Hex-boundary check:** clean.

---

### main.py signal-row writer extension

**Closest analog:** `main.py:1273-1280` — the existing `state['signals'][state_key] = { 'signal': new_signal, ..., 'strategy_version': system_params.STRATEGY_VERSION }` block (touched by Phase 22 VERSION-02)
**Why this analog:** Same write site; Phase 22 added one key (`strategy_version`), Phase 17 adds two (`ohlc_window`, `indicator_scalars`).
**Pattern to copy:**
- Single dict literal assigned in one statement (atomic write semantics rely on this).
- Comment block ABOVE the assignment listing every phase that contributed a field — Phase 22's "G-2 revision 2026-04-22 ... B-1 revision 2026-04-22 ... Phase 22 VERSION-02:" pattern.
- Fresh attribute access at write time (no kwarg defaults) per LEARNING 2026-04-29 ("Python kwarg defaults capture module globals at import").
- Use `system_params.STRATEGY_VERSION` (already in scope from existing line) as the canonical "fresh attribute access" example.
**Pattern to adapt:**
- Build `ohlc_window` from the same dataframe that flows into `compute_indicators` and `last_row = df.iloc[-1]` at `main.py:1184-1196`. Take the last 40 rows as `df.tail(40)`, iterate over rows, build `{'date': YYYY-MM-DD, 'open': float, 'high': float, 'low': float, 'close': float}` dicts.
- Build `indicator_scalars` from the existing `scalars = signal_engine.get_latest_indicators(df_with_indicators)` result (already computed at `main.py:1185`); the 9-key dict is a direct passthrough.
- Add a Phase-17 comment line tagging the new keys, mirroring the Phase 22 comment line format ("Phase 22 VERSION-02: tag every fresh write...").
- The `last_scalars` key MUST stay (CONTEXT D-09 backwards-compat rule for notifier).
**Hex-boundary check:** clean — main.py IS the orchestrator; importing system_params + signal_engine + sizing_engine here is allowed by design.

---

### `_TRACE_FORMULAS: dict[str, str]` module-level dict

**Closest analog:** `dashboard.py:179-188` — `_INSTRUMENT_DISPLAY_NAMES`, `_EXIT_REASON_DISPLAY` (line 972-977), `_SIGNAL_LABEL` (line 967), `_DEFAULT_STRATEGY_VERSION` (line 926)
**Why this analog:** Same module-level constant shape — typed dict / dict[str, X], used by render helpers via direct lookup. Sits in the lookup-table cluster of dashboard.py.
**Pattern to copy:**
- Place near `_SIGNAL_LABEL` / `_EXIT_REASON_DISPLAY` (around `dashboard.py:967-977`) — the existing "Render-helper lookups" header.
- Single dict literal with a one-line preceding comment naming the source (`# Phase 17 D-13: indicator formula text catalogue (presentation-only).`).
- Underscore prefix to mark "shared-implementation-detail" (matches `_DEFAULT_STRATEGY_VERSION` convention).
**Pattern to adapt:**
- Type annotation `dict[str, str]`.
- 9 keys exactly matching `indicator_scalars` keys: `tr`, `atr`, `plus_di`, `minus_di`, `adx`, `mom1`, `mom3`, `mom12`, `rvol`.
- Values are plain strings (no MathJax / KaTeX per D-13).
**Hex-boundary check:** clean — string literals only; no imports needed.

---

### `_format_indicator_value(value, seed_required, bars_available) -> str`

**Closest analog:** `dashboard.py:702-711` — `_fmt_currency`, `_fmt_percent_signed` (both at top-level helper cluster)
**Why this analog:** Pure scalar-formatting helper, returns an HTML-safe string. Sits in the same family as `_fmt_*`.
**Pattern to copy:**
- Pure function: no I/O, no clock reads, no imports beyond stdlib (`math`, already used at `dashboard.py:74`).
- Single-line return for happy path: `return f'{value:.6f}'`.
- Docstring tags the source decision: `'''D-05 + D-06 (Phase 17). Pure helper. Allowed import: math only.'''`.
- 6-decimal format string (matches Wilder accumulator precision, per CONTEXT D-05).
**Pattern to adapt:**
- Three-arg signature instead of one — `seed_required` and `bars_available` drive the NaN reason text.
- Branch order: `math.isnan(value)` first → if seed-short, return `f'n/a (need {seed_required} bars, have {bars_available})'`; else `'n/a (flat price)'`. Else fall through to `f'{value:.6f}'`.
- A1 in RESEARCH.md flags `f'{nan:.6f}'` produces literal `'nan'` (not ValueError); the isnan guard is the single safety belt — keep all callers funneled through this helper.
**Hex-boundary check:** clean — `import math` is already at top of dashboard.py.

---

### `_resolve_trace_open_keys(state, trace_open_keys: list[str]) -> set[str]`

**Closest analog:** `dashboard.py:929-964` — `_resolve_strategy_version(state)`
**Why this analog:** Same shape — read primitives off state + caller-supplied input, return the resolved value, never mutate state. Phase 22 D-06 hex-boundary precedent: caller (route layer) computes the cookie-derived primitive and passes it in.
**Pattern to copy:**
- Function signature reads from state dict primitives only.
- Defensive guard: filter input list to the known-instrument allowlist (mirrors `_resolve_strategy_version`'s "default to v1.0.0 if no row carries the field" defensiveness).
- Returns `set[str]` (immutable-ish — caller passes into render helpers).
**Pattern to adapt:**
- Filter `trace_open_keys` against `set(state.get('signals', {}).keys())` (the only legitimate keys are present in state.signals); discard anything else.
- Phase 16.1 cookie-allowlist semantics: also intersect with `{'SPI200', 'AUDUSD'}` (the canonical instrument key set) — RESEARCH.md §Security calls this out as a hardened-read step not in CONTEXT.md.
**Hex-boundary check:** clean — function reads state primitives + a list of strings; no imports.

---

### `_render_trace_inputs(ohlc_window: list[dict]) -> str`

**Closest analog:** `dashboard.py:1612-1717` — `_render_positions_table(state)` (table-shaped render helper)
**Why this analog:** Both render an HTML table from a list-of-dicts payload. Both use the same row-iteration + html.escape-at-leaf discipline.
**Pattern to copy:**
- `parts = ['<section ...>\n', '  <h... heading ...>\n', '  <table>\n', '    <thead>...</thead>\n', '    <tbody>\n']`; append per-row HTML; close with `'    </tbody>\n', '  </table>\n', '</section>\n'`. `return ''.join(parts)`.
- `html.escape(value, quote=True)` at every leaf interpolation (D-15 XSS posture, dashboard.py:984-988 comment block).
- Empty-state branch: if list is empty, render a placeholder message instead of an empty table (mirrors `_render_equity_chart_container` empty-state at `dashboard.py:1871-1879`).
**Pattern to adapt:**
- Empty-state copy: `'Awaiting first daily run — calculations will appear after the next 08:00 AWST cycle.'` (CONTEXT D-11).
- Per-row HTML uses `data-row-index="{i}"` attribute (CONTEXT verification §6 + RESEARCH §Code Examples).
- Numeric cells get `class="num"` for the right-align / tabular-nums CSS.
- 5 columns: Date | Open | High | Low | Close.
**Hex-boundary check:** clean — only stdlib `html.escape`.

---

### `_render_trace_indicators(indicator_scalars: dict, bars_available: int) -> str`

**Closest analog:** `dashboard.py:1061-1125` — `_render_signal_cards(state)` (per-instrument render dispatching scalar formatting)
**Why this analog:** Same shape — read scalars dict + branch on presence/NaN, format each, escape at leaf.
**Pattern to copy:**
- For each indicator key, read `indicator_scalars.get(key, float('nan'))`, pass to `_format_indicator_value`, escape result, emit a `<tr>`.
- Defensive `.get(...)` reads with default — never assume key presence (matches `dashboard.py:1099-1114`'s `scalars.get('adx', 0.0)` pattern).
- Hover tooltip via `title="{formula}"` attribute (REQ-02 hover contract; RESEARCH §Code Examples line 589).
**Pattern to adapt:**
- Add the per-row `<td class="trace-indicator-name" data-formula-open="false">` + paired `<tr class="formula-row" hidden><td colspan="2">{formula}</td></tr>` two-row pattern per indicator (CONTEXT D-03).
- 9 indicator rows in fixed display order: TR, ATR, +DI, -DI, ADX, Mom1, Mom3, Mom12, RVol.
- Pass `bars_available` (length of `ohlc_window`) into `_format_indicator_value` so seed-short reason text is accurate.
**Hex-boundary check:** clean — `html.escape` + `_format_indicator_value` + `_TRACE_FORMULAS` lookup, all in-module.

---

### `_render_trace_vote(indicator_scalars: dict, signal: int) -> str`

**Closest analog:** `dashboard.py:1086-1097` — the `_SIGNAL_LABEL.get(signal_int, _fmt_em_dash())` + `_SIGNAL_COLOUR.get(...)` pattern inside `_render_signal_cards`
**Why this analog:** Same dispatch shape — read int / float scalars, map to badge label + colour class via dict.get with default.
**Pattern to copy:**
- Pre-built dispatch dicts: `_SIGN_BADGE_CLASS = {1: 'plus', -1: 'minus', 0: 'zero'}` (mirror of `_SIGNAL_COLOUR`'s shape).
- `math.isnan(value)` short-circuit before sign-classifying (consistent with `_format_indicator_value`).
- Render each row as `<tr><td>{name}</td><td><span class="trace-badge {cls}">{sym}</span></td><td class="num">{val_str}</td></tr>` per RESEARCH §Pattern 6.
**Pattern to adapt:**
- Three Mom rows + one ADX gate row + one final-outcome line.
- ADX gate threshold `25.0` is duplicated as a string literal in dashboard.py (D-10 forbids `from system_params import ADX_GATE`).
- Final outcome line composed from `signal` (already an int 1/-1/0 from state) and ADX gate result; never recompute.
**Hex-boundary check:** clean.

---

### `_render_trace_panels(signal_dict, instrument_key, is_open)` orchestrator

**Closest analog:** `dashboard.py:1020-1058` — `_render_header(state, now, is_cookie_session)` (3-way switch + composes downstream helpers) + `_render_signal_cards` body composition
**Why this analog:** Same orchestrator shape — accept a primitive bool/3-way flag, compose downstream render helpers, return concatenated HTML.
**Pattern to copy:**
- Signature accepts primitive args (not a state dict + key — pass the per-instrument signal_dict directly so the helper is testable in isolation, matching `_render_header`'s primitive-bool design).
- Compose three sub-helpers: `_render_trace_inputs(...) + _render_trace_indicators(...) + _render_trace_vote(...)`.
- Wrap in `<details data-instrument="{esc}" {open_attr}><summary class="trace-summary">Show calculations</summary>...</details>` per CONTEXT D-04 + RESEARCH §Pattern 1.
**Pattern to adapt:**
- `is_open` boolean drives the literal `' open'` attr suffix vs empty string (mirrors `_render_header`'s conditional `auth_widget` shape at `dashboard.py:1042-1047`).
- Empty `ohlc_window` short-circuits to D-11 "Awaiting first daily run" copy (delegates to `_render_trace_inputs`'s empty-state branch).
- `bars_available = len(ohlc_window)` passed down to `_render_trace_indicators` for accurate seed-short reason text.
**Hex-boundary check:** clean.

---

### `render_dashboard(... trace_open_keys: list[str] = [])` signature extension

**Closest analog:** `dashboard.py:2044-2090` — `render_dashboard(state, out_path, now=None, is_cookie_session=None)` signature (Phase 16.1 added `is_cookie_session`)
**Why this analog:** Phase 16.1 precedent — added a primitive optional kwarg that the route layer computes from a cookie. Same architectural shape.
**Pattern to copy:**
- Optional kwarg with sensible default (None or empty list).
- Default = "main.py daily-loop write path emits all-collapsed" (matches the Phase 16.1 default of `is_cookie_session=None` emitting `{{SIGNOUT_BUTTON}}{{SESSION_NOTE}}` placeholders).
- Caller (web/routes/dashboard.py) computes the value and passes it down.
- Docstring documents the 3-way / default-empty semantics with the same level of detail as `_render_header`'s docstring at `dashboard.py:1029-1038`.
**Pattern to adapt:**
- **Default value gotcha:** use `trace_open_keys: list[str] | None = None` (not `[]`) to avoid the mutable-default trap. Resolve to `[]` inside the body. (LEARNING 2026-04-29 "Python kwarg defaults capture module globals at import" applies here even though strings aren't being captured — the `[]` mutable-default bug is the canonical Python pitfall.)
- Resolve to `set` inside the body via `_resolve_trace_open_keys(state, trace_open_keys or [])`; pass the set down into `_render_signal_cards` (which now takes a `trace_open: set[str]` arg) for per-instrument `is_open` decisions.
- The disk-write path: main.run_daily_check passes `trace_open_keys=None` → all panels collapsed in the on-disk dashboard.html. Web route substitutes per-request via the placeholder-substitution pattern (open question 2 in RESEARCH.md — see "Pattern to design from scratch" section below for the recommendation).
**Hex-boundary check:** clean.

---

### FastAPI route cookie read + allowlist filter

**Closest analog:** `web/routes/dashboard.py:115-128` — `_is_cookie_session(request)` (validates `tsi_session` cookie + Phase 16.1 placeholder-substitution at lines 224-248)
**Why this analog:** Same shape — read `request.cookies.get('<name>')` at handler entry, filter/validate, pass result into `render_dashboard`. Phase 16.1's `_SIGNOUT_PLACEHOLDER` / `_SESSION_NOTE_PLACEHOLDER` substitution model is the architectural precedent for per-request UI state on top of an on-disk cached HTML file.
**Pattern to copy:**
- Cookie read at handler entry: `raw = request.cookies.get('tsi_trace_open', '')`.
- Defensive parse: `keys = [k for k in raw.split(',') if k]`.
- Allowlist filter: `trace_open = frozenset(k for k in keys if k in _VALID_INSTRUMENT_KEYS)`.
- LOCAL imports inside the handler preserve the hex boundary (Phase 11 C-2 / Phase 13 D-07 — see `web/routes/dashboard.py:204-205`'s `from dashboard import render_dashboard` inside the handler).
- Module-level constant: `_VALID_INSTRUMENT_KEYS = frozenset({'SPI200', 'AUDUSD'})` (mirrors `_PLACEHOLDER`, `_SIGNOUT_PLACEHOLDER` constants at `web/routes/dashboard.py:78-83`).
**Pattern to adapt:**
- Disk-cache placeholder-substitution model (Phase 16.1 precedent at `web/routes/dashboard.py:228-248`): emit `{{TRACE_OPEN_SPI200}}` / `{{TRACE_OPEN_AUDUSD}}` placeholders inside each `<details data-instrument="...">` element at write time; substitute per-request based on cookie. Phase 17 RESEARCH open-question 2 surfaces this; the planner must commit to the placeholder-substitution path (it is the only architecture consistent with the on-disk dashboard.html cache + Phase 16.1's existing widget-substitution).
- Set-Cookie header is NOT issued by the route — the JS handler in dashboard.py owns the write, per CONTEXT D-12 (`tsi_trace_open` is JS-owned, no `HttpOnly`).
**Hex-boundary check:** clean — route layer is the FastAPI adapter; allowed to import dashboard (Phase 13 D-07) and read state via load_state (LOCAL import per Phase 11 C-2). No new forbidden imports.

---

### Cookie write JS + click-handler `<script>` block

**Closest analog:** `dashboard.py:143-178` — `_HANDLE_TRADES_ERROR_JS` (module-level JS constant) + `dashboard.py:1899-1936` — the inline `<script>(function() { ... })();</script>` block in `_render_equity_chart_container`
**Why this analog:** Both are the only existing inline-JS patterns in dashboard.py. `_HANDLE_TRADES_ERROR_JS` is a module-level constant injected via concatenation in `_render_html_shell` at line 1975; equity-chart script is built at render time.
**Pattern to copy:**
- Module-level JS constant if static (no per-render data) — matches `_HANDLE_TRADES_ERROR_JS`'s shape at `dashboard.py:143-178`.
- Wrap in `(function() { ... })();` IIFE (matches equity-chart script at `dashboard.py:1900-1935`).
- Emit inside `_render_html_shell` body via concatenation: `'  <script>\n' + _TRACE_TOGGLE_JS + '  </script>\n'` (mirrors line 1974-1976).
- Vanilla ES5 only (no arrow functions, no `const` if avoidable, no template literals — match the existing IIFE style at line 1900).
**Pattern to adapt:**
- New constant `_TRACE_TOGGLE_JS` containing the ≤20-line handler.
- Wrap with `document.addEventListener('DOMContentLoaded', function() { ... })` (Pitfall 8 in RESEARCH).
- Two `forEach` loops: one for `<details data-instrument>` toggle event, one for `.trace-indicator-name` click event.
- Cookie write attrs: `'tsi_trace_open=' + open + '; Path=/; SameSite=Lax; Max-Age=7776000; Secure'` per CONTEXT D-12 + RESEARCH A4 recommendation (add `Secure` for defence-in-depth on HTTPS-only droplet).
**Hex-boundary check:** clean — string constants in dashboard.py only.

---

### CSS additions to `_INLINE_CSS`

**Closest analog:** `dashboard.py:196-695` — the existing `_INLINE_CSS` block (esp. the section that defines `.btn-signout`, `.signout-form`, `.session-note` from Phase 16.1)
**Why this analog:** Same edit point; same f-string-with-CSS-vars shape.
**Pattern to copy:**
- Use `var(--space-X)` / `var(--color-X)` tokens where applicable (existing palette at the top of `_INLINE_CSS`).
- Class names use kebab-case with a feature prefix (`trace-` for Phase 17 mirrors `signout-` for Phase 16.1).
- Group all Phase-17 rules under a single comment header `/* Phase 17 D-03/D-04: trace panels (inputs/indicators/vote) */`.
**Pattern to adapt:**
- `.trace-indicator-name { cursor: pointer; }` is REQUIRED (RESEARCH Pitfall 1 — iOS Safari click trap).
- `.formula-row[hidden]` selector (CSS attribute selector handling the boolean `hidden` attr).
- 5 badge variants: `.trace-badge.plus / .minus / .zero / .pass / .fail` with the CSS-var palette (mirror `_COLOR_LONG`, `_COLOR_SHORT`, `_COLOR_FLAT` tokens already exported via the `:root` block).
- `font-variant-numeric: tabular-nums` + `font-family: ui-monospace, ...` fallback for OHLC numeric column alignment (RESEARCH §Pattern 5).
**Hex-boundary check:** clean — CSS strings only.

---

### `tests/test_state_manager.py::TestMigrateV4ToV5`

**Closest analog:** `tests/test_state_manager.py:1857-2020+` — `TestMigrateV3ToV4` (6 tests covering backfill, full-walker, preserves-other-fields, idempotent, int-legacy-skip, existing-field-skip + the v0→v4 walk in TestFullWalk)
**Why this analog:** Phase 22 mirror — CONTEXT D-08 explicitly says "Same migration test pattern as Phase 22 §D-05".
**Pattern to copy:**
- 6-test class layout: backfill happy path, via `_migrate` walker (schema-version assert), preserves-other-fields, idempotent, int-legacy-skip, skip-rows-with-existing-field.
- Plus the v0→v5 full-walk test in `TestFullWalkV0ToV5` (mirror of `test_full_walk_v0_to_v4_then_load_state` at line 2005).
- Direct dict construction for state inputs; no fixture loading (matches `tests/test_state_manager.py:1872-1894` pattern).
- Assertion error messages name the decision ID: `'D-08: SPI200 must be stamped ohlc_window=[] on first v1.2.x load; got ...'`.
- `from state_manager import _migrate_v4_to_v5` at the top of each test (matches `from state_manager import _migrate_v3_to_v4` at line 1871, 1901, 1926, ...).
**Pattern to adapt:**
- Two fields to backfill (`ohlc_window: []`, `indicator_scalars: {}`) instead of one — each test must assert both fields' state, doubling the assertion count.
- "Existing field preserved" test: separate sub-cases for "ohlc_window already populated", "indicator_scalars already populated", "both already populated" (idempotency on partial-prior-state).
- Schema version assertion bumps from `4` → `5`.
**Hex-boundary check:** clean — tests are not gated by the AST guard.

---

### `tests/test_main.py::TestRunDailyCheckPersistsTracePayload`

**Closest analog:** `tests/test_main.py:2926-2992` — `TestRunDailyCheckTagsStrategyVersion` (2 tests: writes-on-fresh + monkeypatch-constant-bump)
**Why this analog:** Phase 22 wrote `strategy_version` at the same write site Phase 17 extends. Same test scaffold (`monkeypatch.chdir(tmp_path)`, `_seed_fresh_state`, `_install_fixture_fetch`, `main.main(['--once'])`).
**Pattern to copy:**
- `@pytest.mark.freeze_time('2026-04-27T00:00:00+00:00')` decorator on each test method.
- `monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)` to silence logging (line 2944).
- Use `_seed_fresh_state` and `_install_fixture_fetch` helpers already in test_main.py.
- Load state with `state_manager.load_state(path=tmp_path / 'state.json')` and assert directly off the dict.
- Error messages name the decision ID + cite the LEARNING when a kwarg-default trap could regress (line 2982-2987).
**Pattern to adapt:**
- 3 test methods: `test_apply_daily_run_writes_40_entry_ohlc_window`, `test_apply_daily_run_writes_9_key_indicator_scalars`, `test_apply_daily_run_ohlc_window_matches_df_tail_40`.
- Optional 4th test: assert `ohlc_window[-1]` matches the same dict shape used by sizing_engine (`{'open', 'high', 'low', 'close', 'date'}`) — guards against drift between the persistence path and the sizing-engine input shape.
- No monkeypatch trap to guard against (Phase 22's monkeypatch test was specifically guarding the kwarg-default capture trap on `system_params.STRATEGY_VERSION`; Phase 17's writes are local dict ops, not module-attr reads).
**Hex-boundary check:** clean.

---

### `tests/test_dashboard.py::TestTracePanels`

**Closest analog:** `tests/test_dashboard.py:2194-2290` — `TestRenderDashboardStrategyVersion` (golden + state-driven render assertions) + `tests/test_dashboard.py:1067-1172` — `TestGoldenSnapshot`
**Why this analog:** Both use the same render-and-grep pattern (`dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)` → `rendered = out.read_text()` → `assert 'X' in rendered`). The golden-snapshot class mirrors the fixture-driven render approach.
**Pattern to copy:**
- `_make_state(...)` helper from `tests/test_dashboard.py:70+` (already exists; produces the v4 sample state).
- `out = tmp_path / 'd.html'` + `dashboard.render_dashboard(state, out_path=out, now=FROZEN_NOW)` + `rendered = out.read_text()` (lines 2209-2211).
- `re.search(...)` for HTML structure assertions (line 2252-2254 example).
- Assertion error messages cite the decision ID and list the rendered byte count for debugging (line 2213-2215).
**Pattern to adapt:**
- New tests:
  - `test_inputs_panel_renders_40_rows` — assert exactly 40 `<tr data-row-index="">` entries per instrument.
  - `test_inputs_panel_empty_state` — fixture with `ohlc_window: []` → "Awaiting first daily run" copy in HTML.
  - `test_all_formula_strings_present` — for each value in `_TRACE_FORMULAS`, assert `formula in rendered`.
  - `test_vote_badges_class_dispatch` — feed scalars with positive/negative/zero values, assert `class="trace-badge plus"` / `class="trace-badge minus"` / `class="trace-badge zero"` appear.
  - `test_adx_gate_badge_pass_fail` — ADX > 25 → `pass`; ADX < 25 → `fail`.
  - `test_render_does_not_mutate_state` — capture `copy.deepcopy(state)` before render, assert equal after render (matches `_render_*` purity contract; mirror of `tests/test_dashboard.py:1924+` `TestRenderDriftBanner` purity assertions).
  - `test_details_open_from_cookie_keys` — pass `trace_open_keys=['SPI200']`, assert `<details data-instrument="SPI200" open>` appears AND `<details data-instrument="AUDUSD"[^>]*>` appears WITHOUT `open` attr.
- Separate sibling class `TestFormatIndicatorValue` for the pure helper (3 tests: finite → 6-decimal, NaN+seed-short → reason text, NaN+flat-price → reason text). Mirrors `tests/test_dashboard.py:513+` `_fmt_currency` test cluster.
**Hex-boundary check:** clean.

---

### `tests/fixtures/dashboard/sample_state_v5.json`

**Closest analog:** `tests/fixtures/dashboard/sample_state.json` (existing v4 fixture used by `TestGoldenSnapshot` + `TestRenderDashboardStrategyVersion`)
**Why this analog:** Same shape; just adds the two new fields per CONTEXT D-09.
**Pattern to copy:**
- Top-level keys: `account`, `equity_history` (list of `{date, equity}`), `signals`, `positions`, `trade_log`, `warnings`, `last_run`, `schema_version`, `initial_account`, `contracts`.
- 2-space JSON indent matches `sample_state.json:1-30` shape.
- Realistic values (not zeros) so render assertions can pin meaningful numbers.
**Pattern to adapt:**
- `schema_version: 5`.
- Per-instrument signal row gets `ohlc_window` (40 entries) + `indicator_scalars` (9 keys) — populate from a known-good Phase 1 oracle output for the SC-5 hand-recalc verification.
- Mirror the file path: `tests/fixtures/dashboard/sample_state_v5.json`.
**Hex-boundary check:** N/A (data file).

---

## Pattern To Design From Scratch (no in-repo analog)

### `{{TRACE_OPEN_SPI200}}` / `{{TRACE_OPEN_AUDUSD}}` placeholder substitution

**Why no analog:** Phase 16.1's `{{SIGNOUT_BUTTON}}` / `{{SESSION_NOTE}}` placeholders substitute *complete HTML blocks* (the whole sign-out form vs the whole session-note paragraph). Phase 17's per-request injection is much narrower — a single `open` attribute on a `<details>` element. Same architectural family but no in-repo example of attribute-level (vs block-level) substitution against the on-disk cache.

**Recommendation for planner:**
- Emit `{{TRACE_OPEN_SPI200}}` / `{{TRACE_OPEN_AUDUSD}}` literal strings inside each `<details data-instrument="...">` opening tag at render-write time. Default = empty string at write (all collapsed).
- web/routes/dashboard.py substitutes the placeholder with the literal string `' open'` (with leading space) when the instrument key is in the cookie's allowlist-filtered set, else empty.
- Mirror the Phase 16.1 substitution loop at `web/routes/dashboard.py:228-248` (one `content.replace(placeholder, value)` per instrument).
- Module-level placeholder constants alongside `_PLACEHOLDER`, `_SIGNOUT_PLACEHOLDER`, `_SESSION_NOTE_PLACEHOLDER` at `web/routes/dashboard.py:78-83`.

This is the only architecture consistent with the on-disk-cache + Phase 16.1 widget-substitution discipline. Fully recompute-on-each-request would break the cache contract (D-08 staleness check at `web/routes/dashboard.py:86-102`) and change the perf profile.

---

## Shared Patterns

### XSS escape at every leaf

**Source:** `dashboard.py:984-988` (the comment block in dashboard.py describing D-15 XSS posture) + `tests/test_dashboard.py:736-843` (TestSignalAsOfXss)
**Apply to:** Every new render helper in dashboard.py (Phase 17 has 5 new render helpers + 1 orchestrator).
**Pattern:** Every state-derived string passes through `html.escape(value, quote=True)` at the LEAF interpolation site — never at intermediate concat. Date strings, indicator name strings, formula text, instrument keys.

### LOCAL imports in route layer preserve hex boundary

**Source:** `web/routes/dashboard.py:153-155, 204-205, 235` — every import of `dashboard`, `state_manager`, `sizing_engine` is INSIDE the handler function body, not at module top.
**Apply to:** The Phase 17 cookie-read + placeholder-substitution code in web/routes/dashboard.py. New `_VALID_INSTRUMENT_KEYS` and `_TRACE_OPEN_PLACEHOLDER_*` constants stay at module top (constants, not imports). Any new dashboard-helper imports must be LOCAL.

### Idempotent + additive migration with two-clause guard

**Source:** `state_manager.py:178-181` — `for sig in signals.values(): if isinstance(sig, dict) and 'strategy_version' not in sig: sig['strategy_version'] = 'v1.1.0'`
**Apply to:** `_migrate_v4_to_v5`. Adapt to two fields by using two independent `'field' not in sig` guards (NOT a combined `and` — partial-prior-state must still backfill the missing field).

### Decision-ID error messages

**Source:** `tests/test_state_manager.py:1888-1891`, `tests/test_main.py:2954-2956`, `tests/test_dashboard.py:2213-2215`
**Apply to:** Every new test assertion across the 3 new test classes. Format: `f'D-08: <what> must <expectation>; got {actual!r}'`.

---

## Hex-Boundary Spotlight (CONTEXT D-10)

Confirmed clean for every new dashboard.py symbol:

| New symbol | Imports needed | Forbidden? |
|------------|----------------|-----------|
| `_TRACE_FORMULAS` | none (string literals) | clean |
| `_format_indicator_value` | `math` (already imported at `dashboard.py:74`) | clean |
| `_resolve_trace_open_keys` | none | clean |
| `_render_trace_inputs` | `html` (already imported) | clean |
| `_render_trace_indicators` | `html`, `math` (already imported) | clean |
| `_render_trace_vote` | `html`, `math` (already imported) | clean |
| `_render_trace_panels` | none beyond above | clean |
| `_TRACE_TOGGLE_JS` | none (string constant) | clean |
| CSS additions | none (string constant) | clean |
| `render_dashboard` signature ext | none | clean |

**Risk:** A future contributor might be tempted to `from signal_engine import ATR_PERIOD` (or similar) inside `_TRACE_FORMULAS` formula text or inside `_format_indicator_value`'s seed-length lookup. The seed lengths must be a hardcoded `_SEED_LENGTHS = {...}` dict in dashboard.py (RESEARCH §Code Examples line 575-578) — not imported from signal_engine. The existing `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` AST guard at lines 762-782 walks `dashboard.py` against `FORBIDDEN_MODULES_DASHBOARD` (defined at `tests/test_signal_engine.py:556`) and stays green by construction.

Per LEARNING 2026-04-30 (G-37, this project): if a per-symbol import is suspected, use AST-based testing — not grep — for invariant enforcement. The existing AST walker is sufficient (it filters by module name, not symbol name); the hex-boundary at module level is what matters here.

---

## Metadata

**Analog search scope:**
- `dashboard.py` (2099 lines)
- `state_manager.py` (799 lines)
- `system_params.py`
- `main.py` (1718 lines)
- `web/routes/dashboard.py` (274 lines)
- `web/routes/login.py` (cookie-attrs analog)
- `web/middleware/auth.py` (cookie-name analog)
- `tests/test_state_manager.py` (TestMigrateV3ToV4 cluster)
- `tests/test_main.py` (TestRunDailyCheckTagsStrategyVersion cluster)
- `tests/test_dashboard.py` (TestRenderDashboardStrategyVersion + TestGoldenSnapshot)
- `tests/test_signal_engine.py` (forbidden-imports AST guard)
- `tests/fixtures/dashboard/` (sample_state.json shape)

**Files scanned:** 12

**Pattern extraction date:** 2026-04-30
