---
phase: 05-dashboard
plan: 01
subsystem: ui
tags: [dashboard, html, scaffold, chartjs, sri, pytz, hex-boundary, b-1]

# Dependency graph
requires:
  - phase: 03-state-persistence-with-recovery
    provides: state_manager.load_state + reset_state (consumed by dashboard I/O hex)
  - phase: 04-end-to-end-skeleton-fetch-orchestrator-cli
    provides: main.run_daily_check signal-state dict shape (B-1 retrofit site)
provides:
  - dashboard.py module scaffold (I/O hex peer of state_manager/data_fetcher) with 9 NotImplementedError helper stubs
  - Palette constants locked (9 _COLOR_* hexes) + Chart.js 4.4.6 UMD URL + verified SRI hash
  - _INLINE_CSS :root CSS-variable seed (Wave 2 appends full stylesheet)
  - FORBIDDEN_MODULES_DASHBOARD AST blocklist — dashboard.py cannot import signal_engine, sizing_engine, data_fetcher, notifier, main, numpy, pandas, yfinance, or requests
  - tests/test_dashboard.py 6 class skeletons (TestStatsMath, TestFormatters, TestRenderBlocks, TestEmptyState, TestGoldenSnapshot, TestAtomicWrite) + _make_state fixture stub
  - tests/fixtures/dashboard/sample_state.json (mid-campaign, 60 equity rows, 5 trades, 4 distinct exit_reasons) + empty_state.json (byte-identical reset_state output)
  - tests/regenerate_dashboard_golden.py offline regenerator (NEVER in CI)
  - B-1 retrofit — main.py signal-state dict now carries `last_close: bar['close']` alongside `last_scalars`
affects: [05-02 (Wave 1 render blocks + formatters + stats math), 05-03 (Wave 2 chart + goldens + atomic write), 06-notifier (consumes signal-state last_close), Phase 6 email body renderer if reuses dashboard shell]

# Tech tracking
tech-stack:
  added:
    - pytz Australia/Perth localisation (via .localize(), NOT tzinfo=) for dashboard clock injection
    - Chart.js 4.4.6 UMD (CDN + SRI) referenced by _CHARTJS_URL + _CHARTJS_SRI constants; script-embed lands in Wave 2
  patterns:
    - I/O hex scaffold with NotImplementedError stubs against fixed public signature — enables Waves 1/2 to fill bodies against a frozen contract
    - AST blocklist enforces D-01 hex fence BEFORE any render code is written (green-from-first-commit)
    - Offline fixture + golden regenerator mirrors tests/regenerate_fetch_fixtures.py (ROOT / sys.path.insert / SCENARIOS / __main__ guard)
    - Placeholder 0-byte golden HTML files commit-present so Wave 0 is structurally complete; Wave 2 regenerates via tests/regenerate_dashboard_golden.py once render_dashboard body lands

key-files:
  created:
    - dashboard.py (I/O hex scaffold; 9 NotImplementedError helpers; palette + Chart.js SRI + _INLINE_CSS seed)
    - tests/test_dashboard.py (6 class skeletons with test_scaffold_placeholder + _make_state stub + FROZEN_NOW)
    - tests/regenerate_dashboard_golden.py (offline golden regenerator, NEVER in CI)
    - tests/fixtures/dashboard/sample_state.json (mid-campaign fixture, 60 equity rows, 5 trades, 4 exit_reasons)
    - tests/fixtures/dashboard/empty_state.json (byte-identical reset_state output)
    - tests/fixtures/dashboard/golden.html (0-byte placeholder; Wave 2 populates)
    - tests/fixtures/dashboard/golden_empty.html (0-byte placeholder; Wave 2 populates)
  modified:
    - tests/test_signal_engine.py (4 additions: 3 path constants + FORBIDDEN_MODULES_DASHBOARD + test_dashboard_no_forbidden_imports + covered_paths extension)
    - main.py:514-522 (B-1 retrofit — additive `last_close: bar['close']` key in signal-state dict write)
    - tests/test_main.py (import math + 4 new assertions inside test_orchestrator_reads_both_int_and_dict_signal_shape for-loop)

key-decisions:
  - "Chart.js 4.4.6 SRI hash: sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN — RESEARCH-verified 2026-04-21 (rejected the stale CONTEXT D-12 placeholder)"
  - "pytz timezone application via PERTH.localize(datetime(...)), NEVER via datetime(..., tzinfo=pytz.timezone(...)) — the latter yields a historical LMT offset (+07:43:24 for Perth pre-1895) instead of +08:00 AWST"
  - "B-1 retrofit is additive only — bar['close'] is already a float at main.py:449; no re-cast, no schema_version bump (matches Phase 4 G-2 precedent)"
  - "dashboard.py import allowlist: stdlib + pytz + state_manager.load_state + system_params — FORBIDDEN_MODULES_DASHBOARD enforces sibling-hex + numpy/pandas/yfinance/requests exclusion"
  - "Wave 0 commits placeholder 0-byte golden HTML files; Wave 2 regenerates them after render_dashboard body lands (keeps commit structurally complete)"
  - "Test scaffold each class has one test_scaffold_placeholder method so pytest collects and passes 6 new tests without failure blocks during Waves 1/2 development"

patterns-established:
  - "Hex-fence AST blocklist extension pattern: new path constants (module + test + regenerator) + FORBIDDEN_MODULES_<NAME> frozenset + parametrised test inside TestDeterminism + covered_paths extension for 2-space indent guard"
  - "Offline regenerator script mirror: ROOT / sys.path.insert / SCENARIOS list / regenerate_one helper / __main__ guard (matches regenerate_fetch_fixtures.py structure)"
  - "Deterministic hand-curated fixture construction via Python heredoc with json.dumps(sort_keys=True, indent=2) + '\\n' byte-stable emission"
  - "Additive state-dict retrofit pattern (B-1 style): append one key inline, update adjacent comment with revision tag, extend existing test assertion in same for-loop rather than creating new test"

requirements-completed: [DASH-01, DASH-02, DASH-05, DASH-09]

# Metrics
duration: ~25 min
completed: 2026-04-22
---

# Phase 5 Plan 01: Dashboard Wave 0 Scaffold Summary

**Dashboard I/O hex scaffold landed with 9 NotImplementedError render stubs, Chart.js 4.4.6 SRI-locked, D-01 hex fence enforced via AST blocklist from commit one, and the B-1 `last_close` retrofit shipped so UI-SPEC §Positions Current-price column has its data source.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-22T03:04Z (approximate, session start)
- **Completed:** 2026-04-22T03:29:08Z
- **Tasks:** 5 completed
- **Files created:** 7 (dashboard.py, tests/test_dashboard.py, tests/regenerate_dashboard_golden.py, 4 fixture files)
- **Files modified:** 3 (main.py, tests/test_main.py, tests/test_signal_engine.py)
- **Test count:** 319 → 326 (+7: 6 placeholder classes + 1 AST blocklist test)

## Accomplishments

- `dashboard.py` I/O hex scaffold exists at repo root with all 9 render helpers declared as `NotImplementedError` against their final signatures; Wave 1/2 fill bodies against a frozen contract.
- Palette constants locked per UI-SPEC §Color (9 `_COLOR_*` hexes); Chart.js 4.4.6 UMD URL + RESEARCH-verified SRI hash `sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN` committed verbatim.
- `_INLINE_CSS` f-string constant seeded with `:root` CSS-variable palette; Wave 2 append site marked via comment.
- AST hex fence extended — `FORBIDDEN_MODULES_DASHBOARD` (sibling hexes + numpy + pandas + yfinance + requests) + `test_dashboard_no_forbidden_imports` parametrised test passes green against Task 1's import set from the first commit.
- 2-space indent guard (`test_no_four_space_indent`) extended to cover `dashboard.py`, `tests/test_dashboard.py`, `tests/regenerate_dashboard_golden.py` — passes after Task 4 lands regenerator.
- `tests/test_dashboard.py` scaffold with 6 class skeletons + `_make_state` stub + `FROZEN_NOW = PERTH.localize(datetime(2026, 4, 22, 9, 0))` (C-1 reviews: `.localize()`, never `tzinfo=`).
- Hand-curated `sample_state.json` (60 equity rows, 5 trades, 4 distinct exit_reasons, mix of +/- net_pnl, SPI200 open LONG + AUDUSD flat, `last_close` present for both) + `empty_state.json` (byte-identical `reset_state()`).
- `tests/regenerate_dashboard_golden.py` offline regenerator (NEVER in CI) structurally mirrors `tests/regenerate_fetch_fixtures.py`.
- B-1 retrofit: `main.py:521` now emits `'last_close': bar['close']` in the signal-state dict write. `tests/test_main.py::test_orchestrator_reads_both_int_and_dict_signal_shape` gains 4 in-loop assertions (`in sig`, `isinstance(float)`, `math.isfinite`, `> 0`).
- G-S1 broader grep verified — zero `.keys() ==` or `frozenset(sig` matches across tests/.

## Task Commits

Each task was committed atomically with `--no-verify` (worktree-isolated executor per prompt contract):

1. **Task 1: Scaffold dashboard.py** — `038af29` (feat)
2. **Task 2: Scaffold tests/test_dashboard.py** — `7e79760` (test)
3. **Task 3: Extend AST blocklist + indent guard** — `2ee6fcc` (test)
4. **Task 4: Add dashboard fixtures + golden regenerator scaffold** — `21ba43f` (test)
5. **Task 5: B-1 retrofit — add last_close to signal state dict** — `57ef2b8` (feat)

_Plan metadata (SUMMARY.md) committed separately below._

## Files Created/Modified

### Created

- `dashboard.py` — Render I/O hex scaffold: 9 NotImplementedError helper stubs (`_render_header`, `_render_signal_cards`, `_render_positions_table`, `_render_trades_table`, `_render_key_stats`, `_render_footer`, `_render_equity_chart_container`, `_render_html_shell`, `render_dashboard`); palette constants; Chart.js URL + SRI; `_INLINE_CSS` :root vars; D-01-allowed imports only (stdlib + pytz + state_manager.load_state + system_params).
- `tests/test_dashboard.py` — 6 class skeletons (TestStatsMath, TestFormatters, TestRenderBlocks, TestEmptyState, TestGoldenSnapshot, TestAtomicWrite) each with `test_scaffold_placeholder`; `_make_state` NotImplementedError stub; module-level path constants + `FROZEN_NOW = PERTH.localize(datetime(2026, 4, 22, 9, 0))`.
- `tests/regenerate_dashboard_golden.py` — Offline golden regenerator (NEVER in CI) mirroring `regenerate_fetch_fixtures.py`; loads state fixtures, calls `render_dashboard(state, out_path, now=FROZEN_NOW)`, writes golden HTML; `[regen]` log prefix.
- `tests/fixtures/dashboard/sample_state.json` — Mid-campaign state: `account: 104532.18`, 60 equity_history rows (linear + deterministic oscillation, ending exactly 104532.18), 5 trades covering `{stop_hit, flat_signal, signal_reversal, adx_exit}` with net_pnls `[347.0, 197.5, -253.0, 347.5, 197.0]`, SPI200 open LONG @ 8000.0 with peak 8100.0 + atr_entry 50.0 + n_contracts 2, AUDUSD position null, both signals carry `last_close` (SPI200=8085.0, AUDUSD=0.6502) + full `last_scalars` dict. Byte-stable via `json.dumps(sort_keys=True, indent=2) + '\\n'`.
- `tests/fixtures/dashboard/empty_state.json` — Byte-identical output of `state_manager.reset_state()` (round-trips via `assert loaded == reset` in acceptance).
- `tests/fixtures/dashboard/golden.html` — 0-byte placeholder (Wave 2 regenerates).
- `tests/fixtures/dashboard/golden_empty.html` — 0-byte placeholder (Wave 2 regenerates).

### Modified

- `tests/test_signal_engine.py` — Added constants `DASHBOARD_PATH`, `TEST_DASHBOARD_PATH`, `REGENERATE_DASHBOARD_GOLDEN_PATH` (lines 471-474); added `FORBIDDEN_MODULES_DASHBOARD` frozenset after `FORBIDDEN_MODULES_MAIN` (8 entries: `signal_engine, sizing_engine, data_fetcher, notifier, main, numpy, pandas, yfinance, requests`); added `test_dashboard_no_forbidden_imports` parametrised method inside `TestDeterminism` (after `test_main_no_forbidden_imports`); extended `covered_paths` in `test_no_four_space_indent` with 3 new entries for Phase 5.
- `main.py:514-522` — B-1 retrofit additive: `'last_close': bar['close']` key appended to signal-state dict; adjacent comment gains `# B-1 revision 2026-04-22 (Phase 5 Wave 0)` traceability tag.
- `tests/test_main.py` — `import math` at line 29 (alphabetical); 4 new assertions inside `test_orchestrator_reads_both_int_and_dict_signal_shape` for-loop (immediately after the G-2 `'rvol' in sig['last_scalars']` assertion): `'last_close' in sig`, `isinstance(sig['last_close'], float)`, `math.isfinite(sig['last_close'])`, `sig['last_close'] > 0`.

## Decisions Made

- **Chart.js SRI hash source:** Used RESEARCH §Version verification hash (`sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN`), explicitly rejecting the stale CONTEXT D-12 placeholder. Browser SRI check is byte-exact; a typo silently kills the chart.
- **pytz usage discipline:** All timezone constructions use `PERTH = pytz.timezone('Australia/Perth'); PERTH.localize(datetime(...))` — never `datetime(..., tzinfo=pytz.timezone(...))`. C-1 reviews fix documented in module docstrings (dashboard.py, test_dashboard.py, regenerate_dashboard_golden.py).
- **B-1 additive retrofit:** `bar['close']` is already a float at `main.py:449` (cast via `float(last_row['Close'])`). Did NOT re-cast to `float(bar['close'])` — that would add noise with no semantic change. The B-1 retrofit is purely additive (one new dict key) with no schema_version bump, matching Phase 4 G-2 precedent.
- **Placeholder goldens:** Committed 0-byte `golden.html` + `golden_empty.html`. Wave 2 populates them via the regenerator script after `render_dashboard` body lands. This keeps Wave 0's commit structurally complete (all listed files present) while deferring the one-shot regeneration to the wave that owns the render logic.
- **Test placeholder methods:** Each of the 6 class skeletons carries one `test_scaffold_placeholder(self) -> None: assert True` so pytest collects + passes 6 new green tests. Waves 1/2 replace placeholders with real tests without wrestling pytest collection errors.
- **Fixture determinism via Python heredoc:** `sample_state.json` was generated via a one-shot Python script with deterministic equity curve (`linear + (i*7)%11 oscillation`), ensuring `sort_keys=True` + trailing `\n` byte-stability.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed 5 ruff lint errors in dashboard.py during Task 1**

- **Found during:** Task 1 acceptance check (`ruff check dashboard.py`)
- **Issue:** Initial dashboard.py draft tripped:
  - W605 invalid escape sequence `\/` inside the module docstring (docstring was a regular triple-string; ruff treated `\/` literally)
  - I001 unsorted imports (ruff isort considered `from state_manager import load_state` malformed as a single-line bare import next to parenthesised sibling)
  - E501 line too long (3 lines over 100 chars: --font-mono value, comment marker, render_dashboard NotImplementedError arg)
- **Fix:**
  - Converted module docstring to raw string (`r'''...'''`) — fixes W605 without altering semantics (no unintended raw-mode characters in prose).
  - Re-wrapped `from state_manager import load_state` across three lines via parenthesised single-name form — satisfies isort.
  - Shortened `--font-mono` fallback chain (dropped `'Liberation Mono'`, still covers macOS + Windows + Linux monospace); shortened CSS comment marker; split `render_dashboard` NotImplementedError message across two lines with trailing comma.
- **Files modified:** dashboard.py (same file being created; fixes applied before first commit)
- **Verification:** `ruff check dashboard.py` → All checks passed
- **Committed in:** `038af29` (Task 1 commit; fixes were pre-commit)

---

**Total deviations:** 1 auto-fixed (1 bug — lint-level formatting)
**Impact on plan:** Minimal. All fixes were cosmetic/lint-level; no semantic changes, no contract changes, no test impact. The plan's acceptance criteria were met verbatim after the fixes.

## Issues Encountered

- **Indent-guard ordering:** `test_no_four_space_indent` failed between Task 3 and Task 4 because `REGENERATE_DASHBOARD_GOLDEN_PATH` referenced a file that didn't yet exist (file-not-found during `read_text()`). This was anticipated in the plan's `<pitfalls>` block. Resolution: committed Task 3 with AST blocklist test already green, proceeded immediately to Task 4, and the indent-guard went green once the regenerator script was created. No code change to the indent-guard mechanism was required.

## Self-Check: PASSED

Verified all claims against disk state before finalising:

### Files exist

- dashboard.py: FOUND
- tests/test_dashboard.py: FOUND
- tests/regenerate_dashboard_golden.py: FOUND
- tests/fixtures/dashboard/sample_state.json: FOUND
- tests/fixtures/dashboard/empty_state.json: FOUND
- tests/fixtures/dashboard/golden.html: FOUND (0 bytes as planned)
- tests/fixtures/dashboard/golden_empty.html: FOUND (0 bytes as planned)

### Commits exist

- 038af29 feat(05-01): scaffold dashboard.py with palette + Chart.js SRI constants: FOUND
- 7e79760 test(05-01): scaffold tests/test_dashboard.py with 6 class skeletons: FOUND
- 2ee6fcc test(05-01): extend AST blocklist + indent guard for dashboard.py: FOUND
- 21ba43f test(05-01): add dashboard fixtures + golden regenerator scaffold: FOUND
- 57ef2b8 feat(05-01): B-1 retrofit — add last_close to signal state dict: FOUND

### Verification commands (all green at 2026-04-22T03:29Z)

- `.venv/bin/pytest tests/ -x` → 326 passed
- `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism` → 43 passed
- `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism::test_dashboard_no_forbidden_imports` → 1 passed
- `.venv/bin/pytest tests/test_main.py::TestOrchestrator::test_orchestrator_reads_both_int_and_dict_signal_shape` → 1 passed
- `.venv/bin/ruff check .` → All checks passed
- `grep -c 'raise NotImplementedError(' dashboard.py` → 9 (exactly 9 helper stubs)
- `grep -c '^class Test' tests/test_dashboard.py` → 6
- `grep -rn '\.keys() ==\|frozenset(sig' tests/ --include='*.py'` → zero matches (G-S1 clean)

## Known Stubs

Expected per plan — Wave 1/2 replaces each:

- `dashboard._render_header` (NotImplementedError, Wave 1)
- `dashboard._render_signal_cards` (NotImplementedError, Wave 1)
- `dashboard._render_positions_table` (NotImplementedError, Wave 1)
- `dashboard._render_trades_table` (NotImplementedError, Wave 1)
- `dashboard._render_key_stats` (NotImplementedError, Wave 1)
- `dashboard._render_footer` (NotImplementedError, Wave 1)
- `dashboard._render_equity_chart_container` (NotImplementedError, Wave 2)
- `dashboard._render_html_shell` (NotImplementedError, Wave 2)
- `dashboard.render_dashboard` (NotImplementedError, Wave 2 — public API)
- `tests.test_dashboard._make_state` (NotImplementedError, Wave 1 fills per UI-SPEC F-8)
- `tests/fixtures/dashboard/golden.html` (0 bytes; Wave 2 regenerates)
- `tests/fixtures/dashboard/golden_empty.html` (0 bytes; Wave 2 regenerates)

All stubs are expected-in-this-wave per the plan's `must_haves.truths` block. Wave 0's goal is structural scaffold only; Waves 1/2 convert these stubs into real behaviour.

## Next Phase Readiness

- Wave 1 (`.planning/phases/05-dashboard/05-02-PLAN.md`) can begin immediately: `render_dashboard` signature is frozen; `_make_state` has a fixed call shape; `FROZEN_NOW` constant is stable; palette constants are locked so per-block `substring in html` assertions can reference them.
- Wave 2 (`.planning/phases/05-dashboard/05-03-PLAN.md`) readiness depends on Wave 1 completing `_render_*` helpers — but the `_render_equity_chart_container` signature, `_render_html_shell` signature, and `render_dashboard(state, out_path, now)` public API are locked here.
- **B-1 retrofit live:** Any `run_daily_check` run from now on produces state.json with `state['signals'][key]['last_close']` populated. Wave 2's `_render_positions_table` can rely on this field directly (backward-compat via `.get('last_close')` required only for historical state.json files).
- **Hex fence enforced:** An accidental `import numpy` in dashboard.py by a future wave now fails loudly via `test_dashboard_no_forbidden_imports` — not a silent lint warning.

## Plan-Internal Verification Summary

| Evidence line | Result |
|-|-|
| `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism::test_dashboard_no_forbidden_imports -x` | GREEN |
| `.venv/bin/pytest tests/test_main.py::TestOrchestrator::test_orchestrator_reads_both_int_and_dict_signal_shape -x` | GREEN |
| `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism::test_no_four_space_indent -x` | GREEN |
| `.venv/bin/pytest tests/ -x` | GREEN (326 passed, +7 vs baseline 319) |
| `.venv/bin/ruff check .` | GREEN |

---

*Phase: 05-dashboard*
*Plan: 01 (Wave 0 — BLOCKING scaffold)*
*Completed: 2026-04-22*
