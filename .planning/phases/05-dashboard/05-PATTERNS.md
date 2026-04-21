# Phase 5: Dashboard — Pattern Map

**Mapped:** 2026-04-21
**Files analyzed:** 8 (3 new modules + 4 new fixtures + 4 modified files)
**Analogs found:** 7 / 8 strong matches; 1 module constant (`_INLINE_CSS`) has no direct analog (first inline-CSS-in-Python module in this repo) — guidance below.

---

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `dashboard.py` (NEW) | I/O hex (HTML render + atomic file write) | transform → file-I/O (state dict in → HTML out → atomic replace) | `state_manager.py` (atomic write + hex fence + module docstring) + `data_fetcher.py` (module logger + custom nothing-but-narrow-catch + I/O hex fence) | **exact** (structural twin of state_manager for write pattern; twin of data_fetcher for logger + narrow-catch posture) |
| `tests/test_dashboard.py` (NEW) | test (class-per-concern) | unit + golden snapshot | `tests/test_state_manager.py` | **exact** (same skeleton: module-level `_PATH` constants → `_make_state` fixture helper → one class per concern, mirror D-13 organisation) |
| `tests/regenerate_dashboard_golden.py` (NEW) | offline regenerator script | batch (fixtures → rendered goldens committed) | `tests/regenerate_goldens.py` (Phase 1) + `tests/regenerate_fetch_fixtures.py` (Phase 4 peer) | **exact** (both have ROOT → sys.path.insert → imports after path shim → `[regen]` logging → `if __name__ == '__main__': main()` → never-in-CI contract) |
| `tests/fixtures/dashboard/sample_state.json` + `empty_state.json` (NEW) | fixture (committed JSON) | read-only input | `tests/fixtures/fetch/axjo_400d.json` + `tests/fixtures/phase2/*.json` | **role-match** (same "committed JSON fixture, hand-curated once, regenerated deliberately" posture; shape is new because it mirrors `state_manager.reset_state()` output) |
| `tests/fixtures/dashboard/golden.html` + `golden_empty.html` (NEW) | fixture (committed rendered output) | read-only input; git-diff is review surface | `tests/determinism/snapshot.json` + `tests/oracle/goldens/axjo_400bar_indicators.csv` | **role-match** (same "regenerator writes, test diffs, PR-review on the diff" pattern; format differs — HTML text vs SHA + CSV) |
| `main.py` (MODIFIED — B-1 retrofit at 514-519 + D-06 post-save_state call) | orchestrator adapter | request-response (CLI → run → render → exit) | current `main.py:514-519` (G-2 dict-shape signal write) + `main.py:556-563` (save_state success logging) | **exact** (B-1 retrofit is a 1-line additive key; D-06 integration sits as Step 9.5 between save_state and footer) |
| `tests/test_main.py` (MODIFIED — extend D-08 test + 2 new D-06 tests) | test (extension) | unit + integration | `tests/test_main.py::TestOrchestrator::test_orchestrator_reads_both_int_and_dict_signal_shape` (existing G-2 test at line 393) | **exact** (extension of an existing test + peer tests using the same `_install_fixture_fetch` + `_seed_fresh_state` helpers) |
| `tests/test_signal_engine.py` (MODIFIED — AST blocklist + indent guard) | test (architectural guard) | static-analysis | `FORBIDDEN_MODULES_STATE_MANAGER` + `FORBIDDEN_MODULES_DATA_FETCHER` + `FORBIDDEN_MODULES_MAIN` blocks at lines 494-541 | **exact** (drop-in parallel at the same file, same constant-naming discipline, same parametrised test) |
| `.gitignore` (MODIFIED) | config | — | existing `dashboard.html` line already present on line 2 | **n/a — already done** (grep confirms `.gitignore` already contains `dashboard.html` on line 2, same precedent as `state.json` on line 1; Wave 0 scaffold should no-op if already present or skip this task) |

---

## Pattern Assignments

### `dashboard.py` (NEW — I/O hex, transform + file-I/O)

**Analogs:** `state_manager.py` (primary — atomic write) + `data_fetcher.py` (secondary — module logger + narrow-catch).

#### Imports + module docstring pattern

**Copy from `state_manager.py` lines 1-53.**

Docstring structure: public API summary → requirement refs (REQUIREMENTS.md DASH-01..09) → locked decisions (CONTEXT D-01..D-16 + UI-SPEC revisions) → architecture note (hex-lite: MUST NOT import signal_engine/sizing_engine/data_fetcher/main/notifier/numpy/pandas) → clock-injection rule (`now=None` default + Perth timezone) → failure-mode posture (never crashes orchestrator, logs at WARNING).

Concrete import block for `dashboard.py` (synthesise from CONTEXT D-01 allowlist + state_manager.py:34-53 style):

```python
'''Dashboard — static HTML renderer (single self-contained file + Chart.js CDN).

DASH-01..09 (REQUIREMENTS.md §Dashboard). Owns dashboard.html at the repo
root and exposes one public function:
  render_dashboard(state, out_path=Path('dashboard.html'), now=None) -> None.

Block-builder rendering per CONTEXT D-02: 7 per-section _render_* helpers
return HTML strings; _render_html_shell wraps in <!DOCTYPE> + inline CSS +
Chart.js <script>; render_dashboard concatenates + calls _atomic_write_html.

Atomic write via tempfile + fsync(file) + os.replace + fsync(parent dir) —
mirrors state_manager._atomic_write (D-04 Phase 3). Never overwrites the
prior dashboard.html on mid-write crash.

Architecture (hexagonal-lite, CLAUDE.md): I/O hex. Reads state dict
(plain-dict, caller-supplied) + renders HTML + writes to disk. Must NOT
import signal_engine, sizing_engine, data_fetcher, main, notifier, numpy,
or pandas. AST blocklist in tests/test_signal_engine.py::TestDeterminism
enforces this via FORBIDDEN_MODULES_DASHBOARD.

XSS posture (D-15): every state-derived string passes through
html.escape(value, quote=True) at the leaf. JSON payloads injected into
inline <script> pass through json.dumps(...).replace('</', '<\\/') to
prevent </script> break-out.

Never crash the orchestrator (D-06): main.py wraps render_dashboard in
try/except Exception and logs at WARNING. State is already saved by then;
cosmetic failures do not abort the run.
'''
import html
import json
import logging
import math
import os
import statistics
import tempfile
from datetime import datetime
from pathlib import Path

import pytz

from state_manager import load_state  # noqa: F401 — CLI convenience path; production uses caller-supplied state
from system_params import (
  AUDUSD_COST_AUD,
  AUDUSD_NOTIONAL,
  INITIAL_ACCOUNT,
  SPI_COST_AUD,
  SPI_MULT,
)

logger = logging.getLogger(__name__)
```

#### Atomic write pattern — copy verbatim from `state_manager.py:88-133`

Concrete excerpt to mirror in `dashboard.py::_atomic_write_html`:

```python
# Source: state_manager.py lines 88-133 (_atomic_write). Copy VERBATIM with rename.
def _atomic_write_html(data: str, path: Path) -> None:
  '''tempfile + fsync(file) + os.replace + fsync(parent dir).

  Durability sequence (mirrors state_manager._atomic_write D-17 ordering):
    1. write data to tempfile in same directory as target
    2. flush + fsync(tempfile.fileno())  -- data durable on disk
    3. close tempfile (NamedTemporaryFile context exit)
    4. os.replace(tempfile, target)      -- atomic rename
    5. fsync(parent dir fd) on POSIX     -- rename itself durable on disk

  Tempfile cleanup: try/finally unlinks the tempfile if any step before
  os.replace raises. On success, tmp_path_str is set to None so the finally
  clause is a no-op.
  '''
  parent = path.parent
  tmp_path_str = None
  try:
    with tempfile.NamedTemporaryFile(
      dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
    ) as tmp:
      tmp_path_str = tmp.name
      tmp.write(data)
      tmp.flush()
      os.fsync(tmp.fileno())
    os.replace(tmp_path_str, path)
    if os.name == 'posix':
      dir_fd = os.open(str(parent), os.O_RDONLY)
      try:
        os.fsync(dir_fd)
      finally:
        os.close(dir_fd)
    tmp_path_str = None
  finally:
    if tmp_path_str is not None:
      try:
        os.unlink(tmp_path_str)
      except FileNotFoundError:
        pass
```

**Key rule:** Do not diverge byte-for-byte. The only allowed deltas from `state_manager._atomic_write` are (a) function rename `_atomic_write` → `_atomic_write_html`, (b) docstring reference update, (c) `encoding='utf-8'` is already present and must stay. POSIX fsync-after-replace ordering is the Phase 3 D-17 correction — **do not revert** to fsync-before-replace.

#### Module logger pattern — copy from `data_fetcher.py:34`

```python
# data_fetcher.py line 34:
logger = logging.getLogger(__name__)
```

Use the same at module top. Do NOT call `print(...)` for dashboard messages (state_manager uses print-to-stderr as a legacy deviation per Phase 4 precedent note; dashboard, like data_fetcher and main, uses stdlib `logging`). Log prefix per CONTEXT <prior_decisions>: `[Dashboard]`. Example call sites (Claude's Discretion per CONTEXT):

```python
logger.info('[Dashboard] rendering to %s', out_path)
# ... render + atomic write ...
logger.info('[Dashboard] wrote %d bytes', len(html_str))
```

#### Palette constants + `_INLINE_CSS` module constant

**No direct analog in the repo.** This is the first inline-CSS-in-Python module. Guidance: define palette hex constants at module top (mirroring `_REQUIRED_TRADE_FIELDS` / `_RETRY_EXCEPTIONS` style for module-level constants in `state_manager.py:61-65` and `data_fetcher.py:40-44`), then interpolate into `_INLINE_CSS` via f-string at module-load time.

Source for the exact hex values: UI-SPEC §Color table (rows 105-117) — every CSS variable name and hex is already locked. Copy verbatim.

```python
# Palette tokens (UI-SPEC §Color lines 105-117) — locked by PROJECT.md + CONTEXT D-04.
_COLOR_BG = '#0f1117'
_COLOR_SURFACE = '#161a24'
_COLOR_BORDER = '#252a36'
_COLOR_TEXT = '#e5e7eb'
_COLOR_TEXT_MUTED = '#cbd5e1'
_COLOR_TEXT_DIM = '#64748b'
_COLOR_LONG = '#22c55e'
_COLOR_SHORT = '#ef4444'
_COLOR_FLAT = '#eab308'

# Chart.js 4.4.6 UMD — SRI verified 2026-04-21 per RESEARCH §Standard Stack.
_CHARTJS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js'
_CHARTJS_SRI = 'sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN'

# UI-SPEC §Signal cards — state-key → display-name.
_INSTRUMENT_DISPLAY_NAMES = {
  'SPI200': 'SPI 200',
  'AUDUSD': 'AUD / USD',
}

# UI-SPEC Positions table — contract specs for inline trail-stop + P&L math.
# Hex-fence posture (CONTEXT D-01): re-read the constants from system_params
# rather than importing sizing_engine.
_CONTRACT_SPECS = {
  'SPI200': (SPI_MULT, SPI_COST_AUD),
  'AUDUSD': (AUDUSD_NOTIONAL, AUDUSD_COST_AUD),
}

_INLINE_CSS = f'''
:root {{
  --color-bg: {_COLOR_BG};
  --color-surface: {_COLOR_SURFACE};
  --color-border: {_COLOR_BORDER};
  --color-text: {_COLOR_TEXT};
  --color-text-muted: {_COLOR_TEXT_MUTED};
  --color-text-dim: {_COLOR_TEXT_DIM};
  --color-long: {_COLOR_LONG};
  --color-short: {_COLOR_SHORT};
  --color-flat: {_COLOR_FLAT};
  --space-1: 4px;   --space-2: 8px;   --space-3: 12px;  --space-4: 16px;
  --space-6: 24px;  --space-8: 32px;  --space-12: 48px;
  --fs-body: 14px;    --fs-label: 12px;    --fs-heading: 20px;    --fs-display: 28px;
  --font-mono: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace;
}}
/* ... rest of the stylesheet — layout, typography, tables, cards, chart container,
   stats grid, footer, visually-hidden utility. Executor composes per UI-SPEC. */
'''
```

**Executor note:** Every CSS value that appears in UI-SPEC §Spacing Scale, §Typography, §Color, §Chart Component must resolve from `var(--*)` in `_INLINE_CSS`. This is non-negotiable — UI-SPEC locks the tokens; `_INLINE_CSS` is the single authoritative emission site. Test `test_inline_css_contains_palette` asserts all 4 signal-palette hexes appear verbatim.

#### XSS escape pattern (D-15)

No direct analog in repo (no prior HTML-emitting module). Guidance: call `html.escape(value, quote=True)` at every leaf interpolation, not at an intermediate concat. One call per interpolated value keeps the audit surface narrow.

```python
# Pattern for every state-derived string:
symbol_display = html.escape(_INSTRUMENT_DISPLAY_NAMES[state_key], quote=True)
exit_reason = html.escape(trade.get('exit_reason', ''), quote=True)
signal_as_of = html.escape(sig_entry.get('signal_as_of', 'never'), quote=True)
```

Validation test: `tests/test_dashboard.py::TestRenderBlocks::test_escape_applied_to_exit_reason` (per VALIDATION row 05-02-T2). Feed a trade with `exit_reason='<script>alert(1)</script>'` and assert the rendered HTML contains `&lt;script&gt;` not `<script>`.

#### JSON-in-JS injection defence (DASH-04)

No direct analog — first Python-to-JS-payload site in the repo. Source pattern is from RESEARCH §Pattern 2 (line 363-365).

```python
payload = json.dumps(
  {'labels': labels, 'data': data},
  ensure_ascii=False,
).replace('</', '<\\/')
```

**Why not `html.escape`:** `html.escape` handles `< > & ' "` for HTML attribute contexts. Inside a `<script>` block, the browser parses the script tag using raw-text rules where `</script>` closes the block regardless of JS string quoting. The `</` → `<\/` replacement is the standard hardening (JSON permits the escape; browsers never see the closing tag mid-string).

Validation test: `test_chart_payload_escapes_script_close` (VALIDATION row 05-03-T1) — feed `equity_history = [{'date': '</script><img src=x>', 'equity': 100}]` and assert the rendered HTML does not contain a `</script>` substring anywhere before the legitimate closing tag for the inline block.

#### Custom exception (none needed)

`state_manager.py` defines no custom exceptions (it raises `ValueError` via `_validate_*`). `data_fetcher.py` defines `DataFetchError` + `ShortFrameError` at lines 54-67. **`dashboard.py` does not need a custom exception** — per CONTEXT D-06 failure-isolation rule, any exception the render raises is caught by main.py's try/except Exception and logged as a warning. Raising a vanilla `Exception` subclass would not improve diagnostics given that posture. If a domain invariant needs surfacing during tests (e.g., naive-datetime on `now`), use `ValueError` per the `_fmt_last_updated` contract locked in UI-SPEC §Format Helper Contracts.

---

### `tests/test_dashboard.py` (NEW — class-per-concern test organisation)

**Analog:** `tests/test_state_manager.py` (class-per-concern + module-level path constants + `_make_*` fixture helper).

#### Module docstring + path constants — copy from `test_state_manager.py:1-45`

```python
# Pattern: test_state_manager.py lines 1-45.
'''Phase 5 test suite: HTML dashboard render, stats math, formatters,
empty-state, golden snapshot, atomic write.

Organized into classes per CONTEXT D-14 (one class per concern dimension):
  TestStatsMath, TestFormatters, TestRenderBlocks, TestEmptyState,
  TestGoldenSnapshot, TestAtomicWrite.

All tests use tmp_path (pytest built-in) for isolated dashboard.html writes
— never touch the real ./dashboard.html. Clock-dependent tests inject a
frozen `now=datetime(2026, 4, 22, 9, 0, tzinfo=pytz.timezone(...))` so
golden-snapshot bytes are deterministic.

Wave 0 (this commit): empty skeletons with class docstrings and _make_state
helper. Waves 1/2 fill in the test methods per the wave annotation in each
class docstring.
'''
import html  # noqa: F401 — used in Wave 1 TestRenderBlocks escape assertions
import json  # noqa: F401 — used in Wave 0 fixture loader
from datetime import datetime
from pathlib import Path

import pytest
import pytz

from dashboard import render_dashboard

# Module-level path constants (mirrors test_state_manager.py STATE_MANAGER_PATH)
DASHBOARD_PATH = Path('dashboard.py')
TEST_DASHBOARD_PATH = Path('tests/test_dashboard.py')
REGENERATE_SCRIPT_PATH = Path('tests/regenerate_dashboard_golden.py')
DASHBOARD_FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'dashboard'
```

#### Fixture helper — copy shape from `test_state_manager.py:51-85` (`_make_trade`)

```python
def _make_state(
  account: float = 100_000.0,
  with_positions: bool = True,
  with_signals: bool = True,
  with_trades: int = 5,
  with_equity: int = 60,
) -> dict:
  '''Build a state dict with sensible defaults. Mid-campaign by default.

  Mirrors state_manager.reset_state() top-level shape, with knobs to
  produce empty-state scenarios (with_positions=False, with_signals=False,
  with_trades=0, with_equity=0) for TestEmptyState coverage.

  Trade shape is the authoritative 12-field schema locked by UI-SPEC F-8
  hygiene note: {instrument, direction, entry_date, exit_date, entry_price,
  exit_price, gross_pnl, n_contracts, exit_reason, multiplier, cost_aud,
  net_pnl}.
  '''
  # ... executor fills body; mirror _make_trade style (return {...})
```

#### Class-per-concern organisation — copy from `test_state_manager.py:91-...`

Six classes per VALIDATION.md §Per-Task Verification Map:
- `TestStatsMath` — rows 05-02-T1 (Sharpe / MaxDD / WinRate / TotalReturn / UnrealisedPnL parity)
- `TestFormatters` — rows 05-02-T2 (currency / percent / pnl-with-colour / last-updated-awst / em-dash)
- `TestRenderBlocks` — rows 05-02-T3 + 05-03-T1 (per-block substring asserts, palette presence, Chart.js SRI match, no-external-stylesheet, `</` escape)
- `TestEmptyState` — row 05-03-T2 (byte-match vs `golden_empty.html`)
- `TestGoldenSnapshot` — row 05-03-T2 (byte-match vs `golden.html` with frozen `now`)
- `TestAtomicWrite` — row 05-03-T2 (crash-on-os.replace leaves prior dashboard.html intact — mirror `test_state_manager.py::TestAtomicity::test_crash_on_os_replace_leaves_original_intact` at lines 213-234 VERBATIM with path swap)

**Copy the monkeypatch pattern verbatim from `test_state_manager.py:228`:**

```python
# test_state_manager.py line 228 pattern, adapted for dashboard:
with patch('dashboard.os.replace', side_effect=OSError('disk full')):
  with pytest.raises(OSError, match='disk full'):
    render_dashboard(new_state, out_path=path)

assert path.read_bytes() == original_bytes, (
  'original dashboard.html must be byte-identical after failed os.replace'
)
```

---

### `tests/regenerate_dashboard_golden.py` (NEW — offline regenerator)

**Analog:** `tests/regenerate_goldens.py` (primary) + `tests/regenerate_fetch_fixtures.py` (newer peer, cleaner structure).

#### Copy structure from `regenerate_fetch_fixtures.py:1-82` (the cleaner peer)

```python
# Source: tests/regenerate_fetch_fixtures.py lines 1-82.
'''Offline dashboard-HTML golden regenerator for Phase 5 tests.

Per CONTEXT D-14 (.planning/phases/05-dashboard/05-CONTEXT.md): this script
is NEVER invoked by CI. Run manually when the dashboard render
intentionally changes (CSS edit, palette tweak, new render block, etc.):

  .venv/bin/python tests/regenerate_dashboard_golden.py

Produces:
  - tests/fixtures/dashboard/golden.html        (committed reference of sample_state.json)
  - tests/fixtures/dashboard/golden_empty.html  (committed reference of empty_state.json)

Frozen clock: pass now=datetime(2026, 4, 22, 9, 0, tzinfo=pytz.timezone(
'Australia/Perth')) so re-runs produce byte-identical output and
TestGoldenSnapshot can diff bytes exactly.

Git-diff on the golden HTML files IS the design review surface: an
unintentional CSS / layout / palette drift surfaces as a diff in PR review.
'''
import json
import sys
from datetime import datetime
from pathlib import Path

import pytz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dashboard import render_dashboard  # noqa: E402, I001 — import after sys.path.insert for script-run resolution

FIXTURES_DIR = ROOT / 'tests' / 'fixtures' / 'dashboard'
FROZEN_NOW = datetime(2026, 4, 22, 9, 0, tzinfo=pytz.timezone('Australia/Perth'))

SCENARIOS = [
  ('sample_state.json', 'golden.html'),
  ('empty_state.json', 'golden_empty.html'),
]


def regenerate_one(state_name: str, golden_name: str) -> None:
  '''Load state fixture, render with frozen clock, write golden HTML.'''
  state = json.loads((FIXTURES_DIR / state_name).read_text())
  out_path = FIXTURES_DIR / golden_name
  render_dashboard(state, out_path=out_path, now=FROZEN_NOW)
  print(f'[regen] wrote {golden_name} ({out_path.stat().st_size} bytes)')


def main() -> None:
  FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
  for state_name, golden_name in SCENARIOS:
    regenerate_one(state_name, golden_name)


if __name__ == '__main__':
  main()
```

**Key pattern points** (copy discipline verbatim):
- `ROOT = Path(__file__).resolve().parent.parent` — line 34 of `regenerate_fetch_fixtures.py`.
- `sys.path.insert(0, str(ROOT))` BEFORE any local import — line 35.
- `# noqa: E402, I001` on the post-sys.path imports — line 37.
- `[regen] wrote ...` log prefix — matches `regenerate_goldens.py:177,182,184` and `regenerate_fetch_fixtures.py:77`.
- `if __name__ == '__main__': main()` dispatch — line 80 of fetch regenerator, line 187 of Phase 1 regenerator.
- NEVER in CI — docstring explicitly warns (copy language from `regenerate_goldens.py:5`: "Per D-04: this script is NEVER invoked by CI").

---

### `tests/fixtures/dashboard/*.json` + `*.html` (NEW — committed fixtures)

**Analogs:**
- JSON fixtures ↔ `tests/fixtures/fetch/axjo_400d.json` (same "committed, hand-curated, regenerated manually" role) + `tests/fixtures/phase2/*.json` (same "JSON shape mirroring production dict" role).
- HTML goldens ↔ `tests/determinism/snapshot.json` (same "committed frozen output; git-diff is the review surface" role) + `tests/oracle/goldens/*.csv` (same "byte-stable output from regenerator" role).

**Shape rule for `sample_state.json`:** output of `state_manager.reset_state()` (mirrors `state_manager.py:279-300`) with realistic mid-campaign data filled in:

```json
{
  "schema_version": 1,
  "account": 104532.18,
  "last_run": "2026-04-21",
  "positions": {
    "SPI200": {
      "direction": "LONG",
      "entry_price": 8000.0,
      "entry_date": "2026-04-10",
      "n_contracts": 2,
      "pyramid_level": 0,
      "peak_price": 8100.0,
      "trough_price": null,
      "atr_entry": 50.0
    },
    "AUDUSD": null
  },
  "signals": {
    "SPI200": {
      "signal": 1,
      "signal_as_of": "2026-04-21",
      "as_of_run": "2026-04-21T09:00:00+08:00",
      "last_scalars": { "atr": 50.0, "adx": 32.5, "pdi": 28.1, "ndi": 12.4,
                         "mom1": 0.031, "mom3": 0.048, "mom12": 0.092, "rvol": 1.12 },
      "last_close": 8085.0
    },
    "AUDUSD": { "signal": 0, "signal_as_of": "2026-04-21",
                 "as_of_run": "2026-04-21T09:00:00+08:00",
                 "last_scalars": { "atr": 0.0042, "adx": 18.3, "pdi": 19.0,
                                    "ndi": 21.2, "mom1": -0.005, "mom3": 0.001,
                                    "mom12": 0.014, "rvol": 0.95 },
                 "last_close": 0.6502 }
  },
  "trade_log": [ /* 5 closed trades, 12-field schema per UI-SPEC F-8 */ ],
  "equity_history": [ /* 60 daily rows */ ],
  "warnings": []
}
```

**Shape rule for `empty_state.json`:** literal output of `reset_state()` serialised via `json.dumps(..., sort_keys=True, indent=2)` — i.e., matches `state_manager.py:285-300` with positions/signals emptied to defaults.

---

### `main.py` (MODIFIED — B-1 retrofit + D-06 integration)

**Analog:** the exact lines being modified (`main.py:507-519`) are the analog for B-1; the save_state + success-log block (`main.py:556-572`) is the analog for D-06 insertion point.

#### B-1 retrofit (at lines 514-519)

**Copy the current code's posture and extend with a single additive key:**

```python
# CURRENT (main.py lines 514-519):
state['signals'][state_key] = {
  'signal': new_signal,
  'signal_as_of': signal_as_of,
  'as_of_run': run_date_iso,
  'last_scalars': scalars,
}

# AFTER Phase 5 B-1 retrofit:
state['signals'][state_key] = {
  'signal': new_signal,
  'signal_as_of': signal_as_of,
  'as_of_run': run_date_iso,
  'last_scalars': scalars,
  'last_close': float(bar['Close']),  # B-1: Phase 5 Positions table Current-price source
}
```

**Executor caveat:** the loop variable holding the last OHLCV bar in `run_daily_check` at line 514 is not directly visible in the snippet above. The plan must locate the bar/row the orchestrator already has in hand at line 514 (it does — the G-2 dict write is already inside the instrument loop and has access to the same bar used by `signal_engine.get_latest_indicators`). Executor reads `main.py:420-519` once to confirm the local variable name before committing, then swaps in the correct `float(...)` expression. Backward-compat: reader MUST handle `state['signals'][key].get('last_close')` returning `None` in `dashboard.py` — UI-SPEC §Field Mapping locks the fallback.

#### D-06 orchestrator integration (insert between `main.py:556-563`)

**Source pattern:** `main.py:556-563` (save_state + success log). Place the render call immediately after the success log, BEFORE the footer at line 565.

```python
# CURRENT insertion target: main.py lines 556-572.
# Step 9: atomic save_state + success footer.
state_manager.save_state(state)
logger.info(
  '[State] state.json saved (account=$%.2f, trades=%d, positions=%d)',
  state['account'],
  len(state['trade_log']),
  sum(1 for p in state['positions'].values() if p is not None),
)

# NEW Step 9.5 (Phase 5 D-06): render dashboard; never crash on failure.
try:
  import dashboard
  dashboard.render_dashboard(state, Path('dashboard.html'), now=run_date)
except Exception as e:
  logger.warning('[Dashboard] render failed: %s: %s', type(e).__name__, e)

# ... footer (unchanged):
elapsed_total = time.perf_counter() - run_start_monotonic
_format_run_summary_footer(...)
```

**Failure-isolation posture** is borrowed from the narrow-catch convention in `data_fetcher.py:121` (`except (*_RETRY_EXCEPTIONS, ValueError) as e:`) and the state_manager save_state OSError re-raise stance (`state_manager.py:363-369`) — but inverted: for dashboard, D-06 EXPLICITLY says "never crash the run, log at WARNING". This is the only place in the codebase where `except Exception:` is the correct posture, and the docstring on the surrounding block must call that out.

**Import placement:** `import dashboard` can live at the top of `main.py` with the other hex imports (line 39-43). Executor picks — module-top is cleaner and matches `state_manager` / `data_fetcher` placement precedent. The `try:` block then only needs the `render_dashboard(...)` call + `except Exception`. Either pattern is acceptable; planner defers to executor's judgement per CLAUDE.md conventions.

**`FORBIDDEN_MODULES_MAIN` stays untouched.** Per CONTEXT D-06: "main.py may import `dashboard` because dashboard is a sibling hex, same as state_manager." The current set `{numpy, yfinance, requests, pandas}` (test_signal_engine.py:536-541) already permits dashboard; no update needed here.

---

### `tests/test_main.py` (MODIFIED — D-08 extension + 2 new D-06 tests)

**Analog:** existing `TestOrchestrator::test_orchestrator_reads_both_int_and_dict_signal_shape` at `tests/test_main.py:393-431` (G-2 revision already extended this test for `last_scalars` — the B-1 retrofit extends it again for `last_close`).

#### B-1 extension — insert after line 431, inside the for-key loop

```python
# Source pattern: tests/test_main.py lines 414-431 (G-2 revision's last_scalars block).
# Extend the same loop with a last_close assertion:
for key in ('SPI200', 'AUDUSD'):
  sig = post['signals'][key]
  # ... existing G-2 assertions (signal / signal_as_of / as_of_run / last_scalars) ...

  # B-1 revision: last_close persisted for Phase 5 Positions table Current column.
  assert 'last_close' in sig, (
    f'{key}: B-1 revision — last_close missing from signals dict'
  )
  assert isinstance(sig['last_close'], float), (
    f'{key}: last_close must be float, got {type(sig["last_close"]).__name__}'
  )
  assert math.isfinite(sig['last_close']), (
    f'{key}: last_close must be finite, got {sig["last_close"]!r}'
  )
```

**Executor note:** `import math` at the top of `test_main.py` is needed — add alongside existing `import json` / `import logging` / etc. at lines 27-41.

#### D-06 new tests — copy scaffolding from `test_main.py:285-342`

The existing `test_signal_as_of_and_run_date_logged_separately` test (`test_main.py:285-311`) is the cleanest analog: uses `@pytest.mark.freeze_time`, `monkeypatch.chdir(tmp_path)`, `_seed_fresh_state`, `_install_fixture_fetch`, calls `main.main(['--once'])`, asserts `rc == 0`, asserts on `caplog.text` substrings.

```python
# Source pattern: test_main.py lines 285-311.
@pytest.mark.freeze_time('2026-04-22 09:00:03+08:00')
def test_run_daily_check_renders_dashboard(
    self, tmp_path, monkeypatch) -> None:
  '''D-06 Phase 5: run_daily_check calls dashboard.render_dashboard AFTER
  save_state; dashboard.html exists on disk post-run.
  '''
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
  _seed_fresh_state(tmp_path / 'state.json')
  _install_fixture_fetch(monkeypatch)

  rc = main.main(['--once'])
  assert rc == 0

  dashboard_html = tmp_path / 'dashboard.html'
  assert dashboard_html.exists(), (
    'D-06: dashboard.html must exist on disk after run_daily_check succeeds'
  )
  # Smoke-check: valid HTML doctype + palette-bg colour
  content = dashboard_html.read_text()
  assert content.startswith('<!DOCTYPE html>'), 'must be well-formed HTML'
  assert '#0f1117' in content, 'DASH-09: palette bg colour must be present'


def test_dashboard_failure_never_crashes_run(
    self, tmp_path, monkeypatch, caplog) -> None:
  '''D-06: if dashboard.render_dashboard raises, run_daily_check logs at
  WARNING and returns 0. State was already saved — cosmetic failure must
  not abort the run.
  '''
  caplog.set_level(logging.WARNING)
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
  _seed_fresh_state(tmp_path / 'state.json')
  _install_fixture_fetch(monkeypatch)

  # Patch dashboard.render_dashboard to raise; mirrors test_state_manager.py:228
  # `patch('state_manager.os.replace', side_effect=OSError(...))` idiom.
  def _raise(*args, **kwargs):
    raise RuntimeError('simulated render failure')
  monkeypatch.setattr('main.dashboard.render_dashboard', _raise)

  rc = main.main(['--once'])
  assert rc == 0, 'D-06: dashboard failure must NOT change exit code'

  # State was saved (pre-render step); dashboard was not.
  state_json = tmp_path / 'state.json'
  assert state_json.exists(), 'state.json must exist (saved pre-dashboard)'
  assert not (tmp_path / 'dashboard.html').exists(), (
    'dashboard.html must not exist — render was forced to raise'
  )
  # WARNING log with [Dashboard] prefix + error-class name.
  assert '[Dashboard] render failed' in caplog.text, (
    'D-06: failure must log at WARNING with [Dashboard] prefix'
  )
  assert 'RuntimeError' in caplog.text, 'exception type must be in log message'
```

**Monkeypatch target rationale** (`'main.dashboard.render_dashboard'`): mirrors `test_state_manager.py:228` `patch('state_manager.os.replace', ...)` — the patch target is the attribute lookup site inside the module under test, not the defining module. Because main.py does `import dashboard`, `main.dashboard.render_dashboard` is the actual lookup. If the executor instead uses `import dashboard` inside the try block (alternative from D-06 insertion above), the target changes to `dashboard.render_dashboard` at global scope. Executor picks; test-file adjusts the monkeypatch target string to match.

---

### `tests/test_signal_engine.py` (MODIFIED — AST blocklist + indent-guard list)

**Analog:** Lines 499-510 (`FORBIDDEN_MODULES_STATE_MANAGER`), 517-526 (`FORBIDDEN_MODULES_DATA_FETCHER`), 755-778 (`test_state_manager_no_forbidden_imports`), 854-866 (the `covered_paths` list inside `test_no_four_space_indent`).

#### Add `FORBIDDEN_MODULES_DASHBOARD` constant — copy the shape from `FORBIDDEN_MODULES_STATE_MANAGER`

Insert after line 541 (after `FORBIDDEN_MODULES_MAIN`), before the `_HEX_PATHS_ALL` list at line 544:

```python
# Source pattern: test_signal_engine.py lines 499-510 (state_manager block).
# Phase 5 Wave 0: dashboard.py IS the render I/O hex — stdlib (html, json,
# math, os, statistics, tempfile, datetime, pathlib) + pytz + state_manager
# (load_state) + system_params ARE allowed. But it must NOT import sibling
# pure-math or I/O hexes (signal_engine, sizing_engine, data_fetcher, main,
# notifier) or heavy scientific stack (numpy, pandas).
FORBIDDEN_MODULES_DASHBOARD = frozenset({
  # Sibling hexes — dashboard.py is a peer, never imports them
  'signal_engine', 'sizing_engine', 'data_fetcher', 'notifier', 'main',
  # Heavy scientific stack (stdlib statistics + math are sufficient per D-07)
  'numpy', 'pandas',
  # yfinance — dashboard never touches network
  'yfinance',
  # requests — dashboard never makes HTTP calls (Chart.js loads client-side)
  'requests',
})
```

#### Add `DASHBOARD_PATH` + `TEST_DASHBOARD_PATH` constants — copy from lines 464-470

Insert alongside the existing path constants at lines 464-470:

```python
# Source pattern: test_signal_engine.py lines 464-470.
DASHBOARD_PATH = Path('dashboard.py')
TEST_DASHBOARD_PATH = Path('tests/test_dashboard.py')
# Phase 5 Wave 0: regenerate_dashboard_golden.py is also covered by the
# 2-space-indent guard below — match Phase 1 precedent on regenerate_goldens.py.
REGENERATE_DASHBOARD_GOLDEN_PATH = Path('tests/regenerate_dashboard_golden.py')
```

#### Add parametrised test — copy verbatim from `test_state_manager_no_forbidden_imports` (lines 755-778)

Insert after `test_main_no_forbidden_imports` at line 816:

```python
# Source pattern: test_signal_engine.py lines 755-778 (state_manager test).
@pytest.mark.parametrize('module_path', [DASHBOARD_PATH])
def test_dashboard_no_forbidden_imports(self, module_path: Path) -> None:
  '''Phase 5 Wave 0: dashboard.py must not import sibling hexes, numpy,
  pandas, yfinance, requests, or the main orchestrator. It IS allowed to
  import stdlib (html, json, math, os, statistics, tempfile, datetime,
  pathlib) + pytz + state_manager (for load_state, CLI path only) +
  system_params (palette constants + INITIAL_ACCOUNT).

  Structural enforcement of CLAUDE.md §Architecture hexagonal-lite for
  dashboard: every sibling hex already has a test_*_no_forbidden_imports
  that forbids importing dashboard (lines 486, 501, 519); this test closes
  the symmetric boundary — dashboard cannot import them either.
  '''
  imports = _top_level_imports(module_path)
  leaked = imports & FORBIDDEN_MODULES_DASHBOARD
  assert not leaked, (
    f'{module_path} illegally imports forbidden module(s): {sorted(leaked)}. '
    f'dashboard.py must not import sibling hexes (signal_engine, sizing_engine, '
    f'data_fetcher, notifier, main), numpy, pandas, yfinance, or requests. '
    f'Allowed: stdlib (html, json, math, os, statistics, tempfile, datetime, '
    f'pathlib) + pytz + state_manager + system_params. Dashboard IS the render '
    f'I/O hex — that is its PURPOSE.'
  )
```

#### Extend `covered_paths` in `test_no_four_space_indent` — add at line 865

```python
# Source pattern: test_signal_engine.py lines 854-866 (covered_paths list).
covered_paths = [
  # ... existing entries (SIGNAL_ENGINE_PATH through MAIN_PATH + TEST_MAIN_PATH) ...
  DASHBOARD_PATH,                      # Phase 5 Wave 0
  TEST_DASHBOARD_PATH,                 # Phase 5 Wave 0
  REGENERATE_DASHBOARD_GOLDEN_PATH,    # Phase 5 Wave 0
]
```

**Executor note:** the sibling-hex blocklists (`FORBIDDEN_MODULES` at lines 480-489, `FORBIDDEN_MODULES_STDLIB_ONLY` at line 492, `FORBIDDEN_MODULES_STATE_MANAGER` at line 501, `FORBIDDEN_MODULES_DATA_FETCHER` at line 519) ALREADY contain `'dashboard'` in their forbid-set — they already forbid signal_engine, sizing_engine, state_manager, data_fetcher, and main from importing dashboard. No changes needed to those constants. The only additions are the new `FORBIDDEN_MODULES_DASHBOARD` + `DASHBOARD_PATH` + the new test + the `covered_paths` extension.

---

### `.gitignore` (MODIFIED — already done)

**Status:** `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.gitignore` lines 1-2 already contain:
```
state.json
dashboard.html
```

Wave 0 scaffold task should grep-and-skip — no edit needed. If the plan includes this as a checklist item, the executor's task body is a no-op verification: `grep -n '^dashboard.html$' .gitignore` must return line 2.

---

## Shared Patterns

### Hex-lite boundary (applies to every new + modified file)

**Source:** `state_manager.py:18-22` docstring + `test_signal_engine.py:499-541` blocklists + `test_signal_engine.py:755-816` parametrised tests.

**Apply to:** `dashboard.py` (mustn't import signal_engine / sizing_engine / data_fetcher / main / notifier / numpy / pandas / yfinance / requests) + `tests/test_signal_engine.py` (add the structural test) + `main.py` (may legally import dashboard; no blocklist change).

```python
# Source: state_manager.py line 18-22.
'''
Architecture (hexagonal-lite, CLAUDE.md): I/O hex. ... Must NOT import
signal_engine, sizing_engine, notifier, dashboard, main, requests, numpy,
or pandas. AST blocklist in tests/test_signal_engine.py::TestDeterminism
enforces this structurally.
'''
```

Every new/modified module's docstring must restate this rule with the specific forbidden list for that module. `dashboard.py`'s allowlist (per CONTEXT D-01 + RESEARCH §Standard Stack): `html, json, math, os, statistics, tempfile, datetime, pathlib, logging, pytz, state_manager, system_params`.

### Narrow-catch discipline (applies to `dashboard.py` helpers + `main.py` D-06 wrapper)

**Source:** `data_fetcher.py:40-44` (`_RETRY_EXCEPTIONS` tuple) + `state_manager.py:330-338` (narrow `(json.JSONDecodeError, UnicodeDecodeError)` catch).

**Apply to:** Inside `dashboard.py` helpers, `except Exception` is ONLY acceptable for the explicit D-06 never-crash posture, and that posture lives in `main.py`'s wrapper — NOT inside `dashboard.py` itself. Within dashboard helpers, raise `ValueError` on naive-datetime (per `_fmt_last_updated` contract) and let other exceptions propagate to the main.py wrapper. Do NOT wrap individual helper calls in `try/except`.

The single permitted `except Exception:` is in `main.py`'s D-06 integration block — document it explicitly with a comment pointing at CONTEXT D-06.

### Atomic-write pattern (applies to `dashboard.py`)

**Source:** `state_manager.py:88-133` (`_atomic_write`).

**Apply to:** `dashboard.py::_atomic_write_html` — verbatim copy with function rename + docstring edit. Test: `tests/test_dashboard.py::TestAtomicWrite` mirrors `tests/test_state_manager.py::TestAtomicity` at lines 205-260 (three tests: crash-leaves-original-intact, tempfile-cleaned-up, clean-disk-no-tempfile). The parent-dir fsync ordering (line 120 `os.replace` → line 121-126 `os.fsync(dir_fd)`) is the Phase 3 D-17 correction and must be preserved.

### Module-level constant organisation

**Source:** `state_manager.py:55-73` (constants block with `# ===` separator) + `data_fetcher.py:40-51` (retry tuple + required-columns frozenset).

**Apply to:** `dashboard.py` constants ordering (top → bottom): logger, then palette tokens, then Chart.js URL + SRI, then display-name + contract-spec dicts, then `_INLINE_CSS` (last, because it f-string-interpolates the palette constants defined above it).

### Module-level path constants for tests

**Source:** `test_signal_engine.py:457-470` + `test_state_manager.py:44-45` + `test_data_fetcher.py:36-37`.

**Apply to:** `tests/test_dashboard.py` adds `DASHBOARD_PATH`, `TEST_DASHBOARD_PATH`, `REGENERATE_SCRIPT_PATH`, `DASHBOARD_FIXTURE_DIR` (the path constants also get cross-referenced in `test_signal_engine.py`'s AST blocklist test).

### Log prefix discipline

**Source:** CLAUDE.md §Conventions (`[Signal] [State] [Email] [Sched] [Fetch]`) + CONTEXT.md <prior_decisions> (`[Dashboard]` new for Phase 5).

**Apply to:** every `logger.info`/`logger.warning` call in `dashboard.py` AND in `main.py`'s D-06 wrapper. The main.py wrapper's warning message is the only non-[Dashboard] site that uses the prefix; it lives in main.py because main owns the orchestrator error context. Example: `logger.warning('[Dashboard] render failed: %s: %s', type(e).__name__, e)`.

### Clock-injection rule

**Source:** `state_manager.py:302-353` (`load_state` accepts `now=None`; default `datetime.now(UTC)`) + `_backup_corrupt` same pattern.

**Apply to:** `dashboard.render_dashboard(state, out_path, now=None)` + `_fmt_last_updated(now)`. Default: `datetime.now(pytz.timezone('Australia/Perth'))` (UI-SPEC §Copywriting Header locks the timezone). Tests inject `datetime(2026, 4, 22, 9, 0, tzinfo=pytz.timezone('Australia/Perth'))` for determinism.

**Divergence from state_manager:** state_manager uses `UTC` default and `zoneinfo` (stdlib); dashboard uses `pytz.timezone('Australia/Perth')` default. This is a deliberate CONTEXT D-01 choice (state_manager internal-stamping vs dashboard user-facing-display). Do not "harmonise" — tests depend on the pytz type.

---

## No Analog Found

| File / Component | Role | Reason | Guidance |
|------------------|------|--------|----------|
| `_INLINE_CSS` module constant in `dashboard.py` | CSS-in-Python string | First HTML-emitting module; no prior inline-CSS constant in the repo | Define palette hex constants first (mirror `state_manager.py:61-73` module-constant style), then build `_INLINE_CSS` as an f-string that interpolates them at module-load time. UI-SPEC §Spacing/§Typography/§Color supply every token verbatim. |
| Golden-HTML diff-as-review-surface discipline | Fixture | No prior committed-HTML golden in the repo | Closest analog is `tests/determinism/snapshot.json` (SHA-based lock) + `tests/oracle/goldens/*.csv` (CSV text diff). Dashboard goldens are HTML text — `git diff --word-diff` on the golden file IS the design review surface. Regenerator ensures byte-stability via frozen `now`; reviewer inspects the HTML diff in PR to catch unintentional CSS/palette drift. |
| Chart.js `<script>` SRI emission | HTML snippet | No prior external-CDN asset in the repo | Source: RESEARCH §Pattern 2 (line 317-340) with the verified SRI hash `sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN` (RESEARCH line 13 + line 152-153 — the CONTEXT D-12 placeholder is stale). Validation test `test_chartjs_sri_matches_committed` asserts the string appears verbatim in the rendered HTML. |

---

## Metadata

**Analog search scope:**
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/state_manager.py`
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/data_fetcher.py`
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/main.py`
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/system_params.py`
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/tests/test_state_manager.py`
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/tests/test_data_fetcher.py`
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/tests/test_main.py`
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/tests/test_signal_engine.py`
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/tests/regenerate_goldens.py`
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/tests/regenerate_fetch_fixtures.py`
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.gitignore`
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.planning/phases/05-dashboard/{05-CONTEXT.md, 05-UI-SPEC.md, 05-VALIDATION.md, 05-RESEARCH.md}`

**Pattern extraction date:** 2026-04-21

**Downstream consumer:** `gsd-planner` for `05-01-PLAN.md`, `05-02-PLAN.md`, `05-03-PLAN.md`. Each plan's `<reference_pattern>` block cites an anchor from this PATTERNS.md (e.g., "`dashboard.py` atomic write → PATTERNS.md §Atomic-write pattern → `state_manager.py:88-133`") so the executor can open the exact file+line range without re-searching.
