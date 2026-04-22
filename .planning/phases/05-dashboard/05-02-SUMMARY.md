---
phase: 05-dashboard
plan: 02
subsystem: ui
tags: [dashboard, stats-math, formatters, renderers, xss-escape, hex-boundary, pytz, b-1, c-5]

# Dependency graph
requires:
  - phase: 05-dashboard
    provides: 05-01 Wave 0 scaffold (9 NotImplementedError stubs + palette + Chart.js SRI + _INLINE_CSS seed + test-class skeletons + B-1 retrofit + hex-fence AST blocklist)
  - phase: 02-sizing
    provides: sizing_engine.compute_unrealised_pnl (parity reference for dashboard._compute_unrealised_pnl_display)
  - phase: 03-state-persistence-with-recovery
    provides: state.json schema (account, positions, signals, equity_history, trade_log, warnings)
  - phase: 04-end-to-end-skeleton-fetch-orchestrator-cli
    provides: state['signals'][key] dict shape (last_scalars 8-key dict + signal + signal_as_of + B-1 last_close float)
provides:
  - dashboard._fmt_em_dash / _fmt_currency / _fmt_percent_signed / _fmt_percent_unsigned / _fmt_pnl_with_colour / _fmt_last_updated (6 formatters, UI-SPEC §Format Helper Contracts)
  - dashboard._compute_sharpe / _compute_max_drawdown / _compute_win_rate / _compute_total_return (4 stats helpers, CONTEXT D-07..D-10)
  - dashboard._compute_trail_stop_display / _compute_unrealised_pnl_display (2 inline display-math helpers, hex-fence-safe re-implementation of sizing_engine formulas per D-01)
  - dashboard._render_header / _render_signal_cards / _render_positions_table / _render_trades_table / _render_key_stats / _render_footer (6 per-block renderers, UI-SPEC §Copywriting)
  - dashboard._SIGNAL_LABEL / _SIGNAL_COLOUR / _EXIT_REASON_DISPLAY lookup maps
  - TestStatsMath (20 tests incl. sizing_engine parity via pytest.approx), TestFormatters (17 tests incl. naive-datetime rejection), TestRenderBlocks (19 tests incl. 3 C-5 per-surface XSS coverage tests)
  - _make_state fixture helper body (tests/test_dashboard.py) populated with authoritative 12-field trade schema (UI-SPEC F-8)
affects:
  - 05-03 (Wave 2 fills the last 3 stubs: _render_equity_chart_container + _render_html_shell + render_dashboard + _atomic_write_html; consumes all Wave 1 block renderers verbatim via concatenation)
  - 06-notifier (Phase 6 email renderer reuses _fmt_* + palette + _INSTRUMENT_DISPLAY_NAMES + _EXIT_REASON_DISPLAY per UI-SPEC §Phase 6 Reuse Notes)

# Tech tracking
tech-stack:
  added:
    - stdlib html.escape at every state-derived leaf interpolation (D-15 XSS posture)
    - stdlib statistics.stdev + math.log + math.sqrt for Sharpe (stdlib-only per D-01)
    - pytz.timezone('Australia/Perth').astimezone(...) for _fmt_last_updated (D-15 naive-datetime guard)
  patterns:
    - Leaf-level html.escape(value, quote=True) on every state-derived interpolation (45 call sites across dashboard.py — well above the 8-minimum acceptance)
    - Inline hex-boundary re-implementation of sibling-hex math with test-only parity check (sizing_engine imported in test, NOT in dashboard.py)
    - Em-dash forward-reference: _fmt_em_dash placed at top of formatter block so _compute_* can reference it for empty-state fallbacks
    - Signed-percent zero locks to '+0.0%' per Python +.1f format (UI-SPEC)
    - Naive-datetime rejection as early-exit ValueError (RESEARCH Pitfall 9 golden-snapshot drift guard)
    - Lookup-table pattern for enum-to-display mapping (_SIGNAL_LABEL, _SIGNAL_COLOUR, _EXIT_REASON_DISPLAY) with html.escape at leaf on unknown keys

key-files:
  created: []
  modified:
    - dashboard.py (Wave 0 scaffold → Wave 1 body: 12 new helpers + 3 lookup constants + updated module docstring)
    - tests/test_dashboard.py (_make_state body filled + TestStatsMath/TestFormatters/TestRenderBlocks populated with 56 real tests)

key-decisions:
  - "sizing_engine import is a TEST dependency, NOT a dashboard.py dependency — kept inside the test function body per hex-fence AST blocklist; the blocklist only scans dashboard.py"
  - "_fmt_em_dash placed BEFORE _compute_* helpers in file order so reader can trace forward from the em-dash to its callers (Option A from plan ordering rule)"
  - "_fmt_pnl_with_colour zero case: body='$0.00' (no +/- prefix) + muted colour; belt-and-braces html.escape on both colour and body per D-15"
  - "Positions table Current column sources state['signals'][state_key]['last_close'] (B-1 retrofit); em-dash when None"
  - "Trades table uses trade['net_pnl'] for P&L (UI-SPEC F-8 authoritative schema); gross_pnl is NOT the column source"
  - "_render_header signature takes `state` as first arg (currently unused; reserved for schema_version surfacing); # noqa: ARG001 added"
  - "Total Return tile colour via parsed-string heuristic: em-dash → muted, leading '-' → short, '+0.0%' → muted, else → long"

# Metrics
duration: ~15 min
completed: 2026-04-22
---

# Phase 5 Plan 02: Dashboard Wave 1 Stats Math + Formatters + Per-Block Renderers Summary

**Wave 1 filled the pure-math + HTML-string-building layer of `dashboard.py` with 4 stats helpers, 2 inline display-math helpers (hex-fence-safe re-implementations of sizing_engine formulas with a bit-identical parity test), 6 formatters (all stdlib + pytz; naive-datetime rejection locks golden-snapshot byte stability), and 6 per-block renderers (every state-derived leaf escaped via `html.escape(value, quote=True)` including three new C-5 per-surface XSS coverage tests for signal_as_of, unknown exit_reason, and positions display fallback). After this plan, dashboard.py has exactly 3 `raise NotImplementedError` statements remaining — the Wave 2 targets `_render_equity_chart_container`, `_render_html_shell`, and `render_dashboard`.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-22 (Wave 1 session)
- **Completed:** 2026-04-22
- **Tasks:** 3 completed atomically
- **Files modified:** 2 (dashboard.py, tests/test_dashboard.py)
- **Test count:** 326 → 379 (+53 new: 20 stats + 17 formatters + 19 renderers − 3 scaffold placeholders removed)

## Accomplishments

### Wave 1 helper checklist — all filled

**Formatters (6 of 6 — UI-SPEC §Format Helper Contracts):**

- [x] `dashboard._fmt_em_dash` — dashboard.py:172 (single call site for U+2014 empty-value token)
- [x] `dashboard._fmt_currency` — dashboard.py:177 (`$1,234.56` / `-$567.89` / `$0.00`; always 2dp, leading `-$` not parentheses)
- [x] `dashboard._fmt_percent_signed` — dashboard.py:187 (`+5.3%` / `-12.5%` / `+0.0%`; signed zero locked by +.1f)
- [x] `dashboard._fmt_percent_unsigned` — dashboard.py:195 (`58.3%` / `12.5%`)
- [x] `dashboard._fmt_pnl_with_colour` — dashboard.py:200 (LONG-green positive, SHORT-red negative, muted zero; belt-and-braces html.escape on colour + body)
- [x] `dashboard._fmt_last_updated` — dashboard.py:225 (`YYYY-MM-DD HH:MM AWST`; raises ValueError on naive datetime per Pitfall 9)

**Stats math (4 of 4 — CONTEXT D-07..D-10):**

- [x] `dashboard._compute_sharpe` — dashboard.py:245 (daily log-returns × √252; guards: <30 samples, any non-positive equity (Pitfall 4), <2 log-returns (Pitfall 3), std_r==0)
- [x] `dashboard._compute_max_drawdown` — dashboard.py:266 (peak-to-trough %; guards: empty history, running_max==0 (Pitfall 5))
- [x] `dashboard._compute_win_rate` — dashboard.py:282 (closed trades with `gross_pnl > 0` per D-09 "win before costs" convention; guards: empty trade_log)
- [x] `dashboard._compute_total_return` — dashboard.py:294 (signed +.1f%; falls back to `state['account']` when equity_history empty)

**Inline display math (2 of 2 — UI-SPEC §Positions table Derived calculations):**

- [x] `dashboard._compute_trail_stop_display` — dashboard.py:313 (LONG: peak - 3×atr_entry; SHORT: trough + 2×atr_entry; fallback to entry_price when peak/trough None)
- [x] `dashboard._compute_unrealised_pnl_display` — dashboard.py:328 (direction_mult × price_diff × n_contracts × multiplier − opening-half cost; returns None when current_close is None)

**Per-block renderers (6 of 6 — UI-SPEC §Copywriting):**

- [x] `dashboard._render_header` — dashboard.py:377 (H1 "Trading Signals" + subtitle `SPI 200 &amp; AUD/USD mechanical system` + Last-updated AWST)
- [x] `dashboard._render_signal_cards` — dashboard.py:398 (2 cards SPI200 + AUDUSD; LONG=green / SHORT=red / FLAT=gold chip; scalar line with U+00B7 middots; empty state: em-dash chip + "Signal as of never")
- [x] `dashboard._render_positions_table` — dashboard.py:454 (8 cols; Current column reads `state['signals'][key]['last_close']` per B-1; colspan="8" empty state per F-4; <th scope="col">)
- [x] `dashboard._render_trades_table` — dashboard.py:534 (7 cols; `state['trade_log'][-20:][::-1]` for last-20 newest-first; `_EXIT_REASON_DISPLAY` mapping; colspan="7" empty state)
- [x] `dashboard._render_key_stats` — dashboard.py:603 (4 tiles Total Return / Sharpe / Max Drawdown / Win Rate; Tile 1 coloured by sign)
- [x] `dashboard._render_footer` — dashboard.py:657 ("Signal-only system. Not financial advice." — exact UI-SPEC copy)

**Test population:**

- TestStatsMath — 20 tests (5 Sharpe + 3 MaxDD + 3 WinRate + 4 TotalReturn + 2 UnrealisedP&L (incl. `test_unrealised_pnl_matches_sizing_engine` parity) + 3 trail stop)
- TestFormatters — 17 tests (5 currency + 3 percent signed + 2 percent unsigned + 3 P&L colour + 1 em-dash + 3 last-updated incl. naive-datetime rejection + UTC→AWST)
- TestRenderBlocks — 19 tests (2 header + 5 signal cards incl. `test_signal_card_escapes_signal_as_of` C-5 + 4 positions incl. `test_positions_table_escapes_display_fallback` C-5 + 5 trades incl. `test_trades_table_escapes_unknown_exit_reason` C-5 + `test_escape_applied_to_exit_reason` + 2 key stats + 1 footer)
- `_make_state` helper body populated — tests/test_dashboard.py:73-162 — produces mid-campaign state with authoritative 12-field trade schema and all required positions/signals/equity fields

### Parity test confirmation

`tests/test_dashboard.py::TestStatsMath::test_unrealised_pnl_matches_sizing_engine` — GREEN. Tests both LONG and SHORT cases against `sizing_engine.compute_unrealised_pnl(position, current_close, SPI_MULT, SPI_COST_AUD / 2)` via `pytest.approx` equality. The `sizing_engine` import lives inside the test function body — the hex-fence AST blocklist (`tests/test_signal_engine.py::TestDeterminism::test_dashboard_no_forbidden_imports`) only scans `dashboard.py`, so dashboard's fence remains intact.

### UI-SPEC copy deviations

**None.** Every verbatim string from UI-SPEC §Copywriting was preserved exactly: H1, H2 headings, subtitle, Last-updated label, empty-state phrases (`— No open positions —`, `— No closed trades yet —`), signal-card scalar delimiter (U+00B7 middle dot), trades table Entry → Exit arrow (U+2192), exit-reason display map (`Signal flat`, `Reversal`, `Stop hit`, `ADX drop`), and footer disclaimer (`Signal-only system. Not financial advice.`).

### Remaining Wave 2 stubs

Exactly **3** `raise NotImplementedError` statements remain in `dashboard.py` — Wave 2 (05-03) fills these:

- `_render_equity_chart_container` — dashboard.py:666 (Chart.js canvas + inline script per UI-SPEC §Chart Component + RESEARCH §Pattern 2)
- `_render_html_shell` — dashboard.py:671 (`<!DOCTYPE>` + `<head>` + Chart.js script + inline CSS + `<body>`)
- `render_dashboard` — dashboard.py:681 (public API; concatenates body blocks + `_render_html_shell` + `_atomic_write_html`)

No surprise stubs, no leftover Wave 1 work. Wave 2 has exactly one file (`dashboard.py`) to finish, plus populating TestEmptyState / TestGoldenSnapshot / TestAtomicWrite.

## Task Commits

Each task was committed atomically with `--no-verify` (worktree-isolated executor per prompt contract):

1. **Task 1: stats math + display-math helpers with parity tests** — `350c1fb` (feat)
2. **Task 2: numeric + timestamp formatters with naive-datetime guard** — `d1f053f` (feat)
3. **Task 3: 6 per-block renderers with XSS escape discipline** — `658788b` (feat)

_Plan metadata (SUMMARY.md) committed separately below._

## Files Created/Modified

### Modified

- `dashboard.py` — Wave 1 body fill: added `_fmt_em_dash` + 5 formatters (Task 2) + 4 stats helpers + 2 display-math helpers (Task 1) + 6 per-block renderers (Task 3) + 3 lookup constants (`_SIGNAL_LABEL`, `_SIGNAL_COLOUR`, `_EXIT_REASON_DISPLAY`). Updated module docstring to reflect Wave 1 completion. 3 NotImplementedError stubs remain (Wave 2 targets).
- `tests/test_dashboard.py` — Imports expanded with `math`, `re`, `unittest.mock.patch` (lands early for Wave 2), `import dashboard`, `from dashboard import _fmt_em_dash`. `_make_state` helper body populated. TestStatsMath (20 tests), TestFormatters (17 tests), TestRenderBlocks (19 tests) replaced scaffold placeholders with real bodies. TestEmptyState / TestGoldenSnapshot / TestAtomicWrite retain scaffold placeholders (Wave 2 populates).

## Decisions Made

- **sizing_engine import scope:** The parity test `TestStatsMath::test_unrealised_pnl_matches_sizing_engine` imports `sizing_engine` **inside the test function body** (lazy import). This keeps the import out of `tests/test_dashboard.py`'s module-level import set, even though the hex-fence AST blocklist only scans `dashboard.py`. The lazy import also signals intent: sizing_engine is a test dependency, not a fixture.
- **`_fmt_em_dash` placement:** Moved to the top of the formatter block (before `_compute_*` helpers) per plan ordering rule Option A — aids file-reader flow by letting the reader trace forward from the leaf helper to its callers.
- **Total Return colour heuristic:** Implemented as a 4-branch string-parse: em-dash → muted, leading `-` → short, `+0.0%` (or `-0.0%`) → muted, else → long. This avoids re-running the raw `(current - INITIAL_ACCOUNT) / INITIAL_ACCOUNT` comparison and keeps `_render_key_stats` dependent only on the already-formatted string output of `_compute_total_return`.
- **`_render_header` unused `state` argument:** Kept the documented signature `_render_header(state, now)` (per Wave 0 stub) for API symmetry with the other `_render_*` helpers. Added `# noqa: ARG001` comment with "state reserved for future" rationale (e.g. schema_version surfacing). Changing the signature in Wave 1 would have required updating Wave 0 docstring + Wave 2 caller — deferred until there's a concrete use case.
- **C-5 per-surface XSS tests (3 new):** Populated all three — `test_signal_card_escapes_signal_as_of` (payload: `<script>alert(1)</script>` into `signal_as_of`), `test_trades_table_escapes_unknown_exit_reason` (payload: `<img src=x onerror=alert(1)>` into an unknown exit_reason, hits display-map miss branch), `test_positions_table_escapes_display_fallback` (payload: `<img src=x onerror=alert(1)>` into `pyramid_level` — the nearest leaf-escape surface since `_INSTRUMENT_DISPLAY_NAMES` is a locked constant without a user-controlled fallback path).
- **`_make_state` trade schema:** Matches the 12-field authoritative schema per UI-SPEC F-8 (`instrument/direction/entry_date/exit_date/entry_price/exit_price/gross_pnl/n_contracts/exit_reason/multiplier/cost_aud/net_pnl`). Includes representatives of all 4 mapped exit reasons (`flat_signal`, `signal_reversal`, `stop_hit`, `adx_exit`) for downstream use by TestRenderBlocks.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed 2 ruff lint errors on first acceptance check for Task 1**

- **Found during:** Task 1 acceptance (`.venv/bin/ruff check dashboard.py tests/test_dashboard.py`)
- **Issue:**
  - `dashboard.py:211` E501 line-too-long (104 > 100) in `_compute_win_rate` docstring (`"'''CONTEXT D-09: closed trades with gross_pnl > 0 (NOT realised/net — industry "win before costs").'''"`)
  - `tests/test_dashboard.py:31` I001 unsorted import block (the new `import dashboard` + `from dashboard import ...` line between stdlib/third-party/local groups triggered isort)
- **Fix:**
  - Split the single-line docstring into a 3-line form with a blank descriptive paragraph between purpose + convention note.
  - Ran `ruff check --fix` to auto-format the isort block — wrapped the `from dashboard import ...` line as a parenthesised multi-name import (`from dashboard import (\n  _fmt_em_dash,\n  render_dashboard,\n)`).
- **Files modified:** dashboard.py (same Task 1 file), tests/test_dashboard.py (auto-fixed by ruff)
- **Verification:** `.venv/bin/ruff check dashboard.py tests/test_dashboard.py` → All checks passed
- **Committed in:** `350c1fb` (Task 1 commit; fixes were pre-commit)

### Minor Acceptance-Heuristic Note

**Plan acceptance said `grep -c 'sizing_engine' dashboard.py` returns 0.** Actual count is 8 — but all 8 are in **comments and docstrings**, NOT imports (verified via `grep -n`). The semantic acceptance (no imports of sizing_engine) is enforced by the AST blocklist test `tests/test_signal_engine.py::TestDeterminism::test_dashboard_no_forbidden_imports` — GREEN. The literal grep count is a stale heuristic that would fail for any helpful cross-reference docstring (e.g. `'mirror of sizing_engine.compute_unrealised_pnl exactly'` in `_compute_unrealised_pnl_display`); the AST blocklist is the authoritative gate. No action taken — docstring cross-references aid reader comprehension and the hex fence is intact.

**Plan acceptance said `grep -c 'raise NotImplementedError' dashboard.py` returns exactly 3.** After Task 3 it returned 4 because of a stale Wave 0 docstring mention (`'all 9 helpers raise NotImplementedError'`). Fixed pre-commit by updating the module docstring to reflect Wave 1 completion — now returns 3 (the three actual raise statements).

**Total deviations:** 1 auto-fixed (2 ruff lint errors) + 1 pre-commit docstring update for stub-count heuristic. No contract deviations.

## Issues Encountered

- None blocking. Pre-commit ruff + stub-count docstring adjustments described above.

## Self-Check: PASSED

Verified all claims against disk state before finalising:

### Files exist

- dashboard.py: FOUND (modified — Wave 0 scaffold filled with Wave 1 bodies)
- tests/test_dashboard.py: FOUND (modified — scaffold placeholders replaced with 56 real tests)

### Commits exist

- 350c1fb feat(05-02): implement stats math + display-math helpers with parity tests: FOUND
- d1f053f feat(05-02): implement numeric + timestamp formatters with naive-datetime guard: FOUND
- 658788b feat(05-02): implement 6 per-block renderers with XSS escape discipline: FOUND

### Verification commands (all green at 2026-04-22 session close)

- `.venv/bin/pytest tests/test_dashboard.py::TestStatsMath -x` → 20 passed
- `.venv/bin/pytest tests/test_dashboard.py::TestFormatters -x` → 17 passed
- `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks -x` → 19 passed
- `.venv/bin/pytest tests/test_dashboard.py::TestStatsMath::test_unrealised_pnl_matches_sizing_engine -x` → 1 passed (parity GREEN)
- `.venv/bin/pytest tests/test_dashboard.py::TestFormatters::test_fmt_last_updated_awst -x` → 1 passed (VALIDATION row 05-02-T2 AWST)
- `.venv/bin/pytest tests/test_dashboard.py::TestFormatters::test_fmt_last_updated_rejects_naive_datetime -x` → 1 passed (Pitfall 9)
- `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_signal_card_colours -x` → 1 passed (VALIDATION row 05-02-T3)
- `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_positions_table_columns_and_values -x` → 1 passed (VALIDATION row 05-02-T3)
- `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_trades_table_slice_and_order -x` → 1 passed (VALIDATION row 05-02-T3)
- `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_key_stats_block -x` → 1 passed (VALIDATION row 05-02-T3)
- `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_escape_applied_to_exit_reason -x` → 1 passed (VALIDATION row 05-02-T2 XSS)
- `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_signal_card_escapes_signal_as_of -x` → 1 passed (C-5 per-surface XSS)
- `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_trades_table_escapes_unknown_exit_reason -x` → 1 passed (C-5 per-surface XSS)
- `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_positions_table_escapes_display_fallback -x` → 1 passed (C-5 per-surface XSS)
- `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism::test_dashboard_no_forbidden_imports -x` → 1 passed (hex fence intact)
- `.venv/bin/pytest tests/ -q` → 379 passed (+53 vs Wave 0 baseline 326)
- `.venv/bin/ruff check dashboard.py tests/test_dashboard.py` → All checks passed
- `grep -c 'def _compute_' dashboard.py` → 6 (4 stats + 2 display math)
- `grep -c 'def _fmt_' dashboard.py` → 6 (all formatters)
- `grep -c 'def _render_' dashboard.py` → 8 (6 filled + 2 Wave 2 stubs + render_dashboard)
- `grep -c 'raise NotImplementedError' dashboard.py` → 3 (exactly the 3 Wave 2 targets)
- `grep -c 'html.escape' dashboard.py` → 45 (far above 8-minimum acceptance)

## Known Stubs

Expected per plan — Wave 2 fills:

- `dashboard._render_equity_chart_container` (NotImplementedError, Wave 2 — dashboard.py:666)
- `dashboard._render_html_shell` (NotImplementedError, Wave 2 — dashboard.py:671)
- `dashboard.render_dashboard` (NotImplementedError, Wave 2 public API — dashboard.py:681)
- `TestEmptyState.test_scaffold_placeholder` (tests/test_dashboard.py — Wave 2 populates)
- `TestGoldenSnapshot.test_scaffold_placeholder` (tests/test_dashboard.py — Wave 2 populates)
- `TestAtomicWrite.test_scaffold_placeholder` (tests/test_dashboard.py — Wave 2 populates)
- `tests/fixtures/dashboard/golden.html` (0 bytes; Wave 2 regenerates via `render_dashboard` body)
- `tests/fixtures/dashboard/golden_empty.html` (0 bytes; Wave 2 regenerates)

All stubs are expected-in-this-wave per plan's `must_haves.truths` block. Wave 2's goal is Chart.js container + HTML shell + atomic write + golden snapshots.

## Next Phase Readiness

- **Wave 2 (05-03) can begin immediately.** All 6 per-block renderers are body-complete and unit-tested; Wave 2 concatenates their outputs via `render_dashboard(state, out_path, now)` and wraps in `_render_html_shell`. The `_render_equity_chart_container` signature is locked in Wave 0 and uses the same palette constants + Chart.js SRI committed in Wave 0.
- **Parity contract locked:** `dashboard._compute_unrealised_pnl_display(pos, 'SPI200', current_close)` == `sizing_engine.compute_unrealised_pnl(pos, current_close, SPI_MULT, SPI_COST_AUD / 2)` — drift surfaces as a red test in CI.
- **XSS escape discipline proven:** 45 `html.escape` call sites in dashboard.py; 3 C-5 per-surface XSS coverage tests green (signal_as_of, unknown exit_reason, positions pyramid fallback).
- **Hex fence enforced:** An accidental `import sizing_engine` (or numpy / pandas / yfinance / requests / main / notifier / signal_engine / data_fetcher) in dashboard.py by Wave 2 would now fail loudly via `test_dashboard_no_forbidden_imports` — not a silent lint warning.
- **`_make_state` ready for Wave 2:** Knobs `with_positions=False, with_trades=0, with_equity=0, with_signals=False` produce a near-empty-state dict that Wave 2 can pass to `render_dashboard(reset_state())` byte-identity tests.

## Plan-Internal Verification Summary

| Evidence line | Result |
|-|-|
| `.venv/bin/pytest tests/test_dashboard.py::TestStatsMath -x` | GREEN (20 passed) |
| `.venv/bin/pytest tests/test_dashboard.py::TestFormatters -x` | GREEN (17 passed) |
| `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks -x` | GREEN (19 passed) |
| `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism::test_dashboard_no_forbidden_imports -x` | GREEN |
| `.venv/bin/pytest tests/ -x` | GREEN (379 passed, +53 vs Wave 0 baseline) |
| `.venv/bin/ruff check dashboard.py tests/test_dashboard.py` | GREEN |
| `grep -c 'raise NotImplementedError' dashboard.py` | 3 (exactly the 3 Wave 2 targets) |
| `grep -c 'def _compute_'` | 6 |
| `grep -c 'def _fmt_'` | 6 |
| `grep -c 'html.escape'` | 45 |

---

*Phase: 05-dashboard*
*Plan: 02 (Wave 1 — stats math + formatters + per-block renderers)*
*Completed: 2026-04-22*
