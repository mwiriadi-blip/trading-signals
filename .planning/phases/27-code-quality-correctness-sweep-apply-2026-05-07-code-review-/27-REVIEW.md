---
phase: 27-code-quality-correctness-sweep
reviewed: 2026-05-08T00:00:00Z
depth: standard
files_reviewed: 67
files_reviewed_list:
  - .env.example
  - cli_parser.py
  - crash_boundary.py
  - daily_loop.py
  - daily_run.py
  - daily_run_helpers.py
  - dashboard.py
  - dashboard_legacy/__init__.py
  - dashboard_legacy/account_section.py
  - dashboard_legacy/calc_rows.py
  - dashboard_legacy/page_body.py
  - dashboard_legacy/paper_trades_section.py
  - dashboard_legacy/positions_section.py
  - dashboard_legacy/render_helpers.py
  - dashboard_legacy/section_renderers.py
  - dashboard_legacy/trace_panels.py
  - dashboard_renderer/components/header.py
  - dashboard_renderer/components/signals.py
  - dashboard_renderer/stats.py
  - data_fetcher.py
  - interactive.py
  - main.py
  - notifier.py
  - notifier/__init__.py
  - notifier/crash_path.py
  - notifier/dispatch.py
  - notifier/formatters.py
  - notifier/templates.py
  - notifier/templates_alerts.py
  - notifier/templates_sections.py
  - notifier/transport.py
  - notifier/warnings_fifo.py
  - paper_trade_alerts.py
  - pnl_engine.py
  - scheduler_driver.py
  - sizing_engine.py
  - state_actions.py
  - state_manager.py
  - system_params.py
  - tests/fixtures/dashboard/empty_state.json
  - tests/fixtures/dashboard/golden_empty.html
  - tests/fixtures/dashboard_canonical.html
  - tests/test_crash_email_fallback.py
  - tests/test_dashboard_decimal_serialization.py
  - tests/test_dashboard_split_seam.py
  - tests/test_data_fetcher.py
  - tests/test_decimal_money_math.py
  - tests/test_deferred_yfinance_import.py
  - tests/test_entry_side_cost.py
  - tests/test_html_xss_audit.py
  - tests/test_http_timeouts.py
  - tests/test_instrument_regex.py
  - tests/test_integration_f1.py
  - tests/test_lookahead_bias.py
  - tests/test_main_split_seam.py
  - tests/test_migration_contiguity.py
  - tests/test_naive_datetime_fail_closed.py
  - tests/test_notifier.py
  - tests/test_notifier_package_seam.py
  - tests/test_pnl_engine.py
  - tests/test_run_date_logging.py
  - tests/test_secret_redaction.py
  - tests/test_signal_shape_migration.py
  - tests/test_signals_email_to_required.py
  - tests/test_state_manager.py
  - tests/test_system_params.py
  - tests/test_version_flag.py
  - tests/test_warnings_fifo.py
  - web/routes/dashboard.py
  - web/routes/paper_trades.py
findings:
  critical: 1
  warning: 8
  info: 6
  total: 15
status: issues_found
---

# Phase 27: Code Review Report

**Reviewed:** 2026-05-08
**Depth:** standard
**Files Reviewed:** 67
**Status:** issues_found

## Summary

Phase 27 ships 14 sub-plans covering Decimal money math, HTTP timeouts, secret
redaction, regex tightening, naive-datetime fail-closed, HTML XSS audit, signal
shape unification, warnings FIFO, crash email fallback, notifier split, main
split, and dashboard split. Tests provide thorough coverage of the
intended-positive paths (Decimal returns, redact_secret prefix, instrument-id
two-layer policy, FIFO bound).

The review found **one BLOCKER** and **eight WARNINGs** rooted in *split
hygiene* and *partial adoption of the Phase 27 #7 entry-side-cost helper*:

1. **Notifier post-split duplication (BLOCKER):** the legacy single-file
   `notifier.py` (90 KB / 2195 LOC) still sits in the repo root alongside the
   new `notifier/` package. Python's import system resolves `import notifier`
   to the package (verified: `notifier.__file__` →
   `notifier/__init__.py`). Every line of the monolith is dead at runtime.
   Several Phase-27 tests still grep `notifier.py` source bytes (XSS escape
   count, `_RESEND_TIMEOUT_S` absence, instrument-regex AST walker, magic
   `cost / 2` AST walker), so the file is preserved *for tests only*. This
   creates a permanent mis-alignment: any future fix to the package can ship
   without touching the legacy file, the tests still pass, and the on-disk
   file actively misleads the next reader. Either the file must be deleted
   and the tests re-pointed at the package, or the file must be reduced to
   a thin shim that re-exports from the package — currently it is a full
   parallel implementation.

2. **Phase 27 #7 entry-side-cost helper adoption is incomplete (WARNING):**
   `pnl_engine.entry_side_cost(rt_cost)` is the canonical AUD-quantized
   Decimal half-cost helper. The `tests/test_entry_side_cost.py` AST grep
   gate scopes its enforcement to `pnl_engine.py`, `sizing_engine.py`,
   `notifier.py`, `main.py` only. Four production sites outside that scope
   still use raw float `/2`:
     - `web/routes/paper_trades.py:272` — `_COST_AUD[req.instrument] / 2.0`
     - `web/routes/trades.py:420` — `cost_aud * n_contracts / 2`
     - `dashboard_renderer/stats.py:162` — `cost_aud_round_trip / 2`
     - `dashboard_legacy/calc_rows.py` (forwards `cost_aud_round_trip` —
       indirect via `_compute_unrealised_pnl_display`)
   This is a partial-adoption hazard: the helper exists as the single source
   of truth, but the test gate doesn't enforce the rule on the web routes
   that actually persist `entry_cost_aud` into `state['paper_trades']`.

3. **Bare-int signal back-compat code persists past v10 migration (WARNING):**
   Phase 27 #11 (Plan 27-09) guarantees that after `_migrate_v9_to_v10` runs
   at `load_state()`, every `state['signals'][market_id]` is a dict. The
   `dashboard_renderer/components/signals.py` defensive `isinstance(record,
   int)` branch was removed and pinned by
   `tests/test_signal_shape_migration.py::TestRendererDefensiveIntBranchRemoved`.
   But the same dead-code pattern survives in 6 other places that were not
   covered by the test. Either the migration is the truth and these branches
   are dead code (delete), or they're keeping the read path lenient and the
   "post-migration invariant" claim is overstated.

The remaining items are smaller drift issues — stale docstring references,
markdown-only `MAX_WARNINGS` comments still saying 100 instead of the new 50,
duplicated SPI/AUDUSD multiplier constants in `web/routes/paper_trades.py`,
etc.

## Critical Issues

### CR-01: notifier.py monolith and notifier/ package coexist post-split

**File:** `notifier.py` (entire file — 2195 LOC) + `notifier/__init__.py`
**Issue:**
After Plan 27-12 split, the single-file `notifier.py` was preserved in the
repo root. Python's import machinery resolves `import notifier` to the
package (`notifier/__init__.py`); the `notifier.py` file is **never executed
at runtime**. Every public function inside it (`compose_email_subject`,
`compose_email_body`, `send_daily_email`, `send_crash_email`,
`send_magic_link_email`, `send_stop_alert_email`, `_post_to_resend`,
`_render_*_email`, `_atomic_write_html`, the entire formatter family, the
crash-path helpers, etc.) is a parallel implementation that is bit-rot
ready: a fix to the package can ship green-tested while the legacy file
silently drifts.

The reason the file survives is purely test-driven preservation:
- `tests/test_html_xss_audit.py:308` reads `Path('notifier.py').read_text()`
  and asserts `>=69 html.escape(...) call sites`.
- `tests/test_http_timeouts.py:146,183` reads `notifier.py` to assert
  `_RESEND_TIMEOUT_S` is absent and the `(5, HTTP_TIMEOUT_S)` tuple is
  present.
- `tests/test_entry_side_cost.py:23` AST-walks `notifier.py` for the
  `cost / 2` BinOp gate.
- `tests/test_instrument_regex.py:165` lists `notifier.py` in its
  `_PROD_FILES` scope.
- `tests/test_notifier.py:57` exposes `NOTIFIER_PATH = Path('notifier.py')`
  and uses it for goldens regen + introspection.

This means:
1. The structural / coverage gates are **not actually validating the
   shipping notifier code path** — they're validating a frozen-in-time
   shadow copy.
2. A reader running `grep` on the repo gets two answers for any notifier
   question. The implementer who edits the package will believe their
   change shipped; the test reader will see "yes the protection still
   exists in `notifier.py`" without realising that the runtime path is
   the package.

**Why this is BLOCKER not WARNING:**
- `tests/test_html_xss_audit.py::TestNotifierEscapeCoverageStable` reads the
  monolith — if a future XSS fix lands in `notifier/templates_sections.py`
  but the monolith is left untouched, the count assertion still passes. The
  XSS regression gate has been silently disabled.
- `tests/test_http_timeouts.py::test_notifier_post_to_resend_uses_*_timeout`
  reads the monolith — a timeout regression in `notifier/transport.py`
  ships green.
- `tests/test_entry_side_cost.py::test_no_magic_cost_div_in_prod` AST-walks
  the monolith — a magic `/2` introduced in `notifier/formatters.py:385`
  (which currently uses `entry_side_cost`) ships green.

**Fix:**
Two acceptable shapes. The user's `most-eloquent` callout suggests the first.

> **Most eloquent:** Option A — delete `notifier.py` entirely; re-point every
> test grep at the package files via a helper.
>
> Replace `tests/test_html_xss_audit.py:308` with a glob walk over
> `notifier/*.py` summing `html.escape(` calls. Replace
> `tests/test_http_timeouts.py:146,183` with reads of `notifier/transport.py`.
> Re-scope `tests/test_entry_side_cost.py:23` and
> `tests/test_instrument_regex.py:165` to the package directory. The
> resulting tests validate the shipping code path, the repo no longer has
> two parallel implementations of every notifier function, and the
> single-source-of-truth principle is restored.
>
> ```python
> # Replacement scaffold for tests/test_html_xss_audit.py
> NOTIFIER_PKG = Path('notifier')
> def _count_html_escapes_in_pkg() -> int:
>     return sum(
>         len(re.findall(r'html\.escape\(', p.read_text()))
>         for p in NOTIFIER_PKG.glob('*.py')
>     )
> ```

Option B — reduce `notifier.py` to a single-line stub: `from notifier import *`
or equivalent. This is shorter to ship but the stub doesn't render the test
gates correct — they'd grep an empty body and the assertions would fail. So
Option B isn't actually viable; only Option A solves the problem.

## Warnings

### WR-01: Phase 27 #7 entry-side-cost helper adoption gate is too narrow

**File:** `tests/test_entry_side_cost.py:23` + the four uncovered call sites
**Issue:**
`PROD_FILES = ['pnl_engine.py', 'sizing_engine.py', 'notifier.py', 'main.py']`
is the AST-grep scope. Four production paths outside that scope still use
raw float `/2` for the entry-side-cost split, which contradicts the
single-source-of-truth claim in the Phase 27 #7 plan:

  1. `web/routes/paper_trades.py:272`
     `entry_cost_aud = _COST_AUD[req.instrument] / 2.0`
     This is the persistence write — every operator-recorded paper trade
     gets `entry_cost_aud` set from raw float division, not from
     `entry_side_cost()`.
  2. `web/routes/trades.py:420`
     `net_pnl = gross_pnl - (cost_aud * n_contracts / 2)`
     Closed-trade net P&L on the live trades route.
  3. `dashboard_renderer/stats.py:162`
     `cost_aud_open = cost_aud_round_trip / 2`
     Dashboard unrealised-P&L display path.
  4. `dashboard_legacy/calc_rows.py` calls into `_compute_unrealised_pnl_display`
     which forwards through `dashboard_renderer/stats.py:162` — same root.

The intended invariant from Plan 27-01 + 27-07 + 27 #7 is that all money
arithmetic flows through Decimal at the AUD-cent boundary. These four sites
violate that for the half-split specifically.

**Fix:**
1. Either replace all four with `entry_side_cost(rt_cost)`:
   ```python
   from pnl_engine import entry_side_cost
   entry_cost_aud = float(entry_side_cost(_COST_AUD[req.instrument]))
   ```
2. Or extend `tests/test_entry_side_cost.py:PROD_FILES` to include
   `web/routes/paper_trades.py`, `web/routes/trades.py`,
   `dashboard_renderer/stats.py` so the AST gate fails loudly and forces
   the fix.

### WR-02: Bare-int signal defensive branches survive past v10 migration

**File:** Multiple
**Issue:**
Phase 27 #11 (Plan 27-09) `_migrate_v9_to_v10` is the canonical promotion of
bare-int signal rows to dict shape. The renderer pin
(`tests/test_signal_shape_migration.py::TestRendererDefensiveIntBranchRemoved`)
deletes the dead branch in `dashboard_renderer/components/signals.py` only.
The same dead branch survives in:

  - `dashboard_legacy/calc_rows.py:216` — `if isinstance(sig_entry, int)`
    (then a 4-line dead block setting `sig_val`, `last_close`, `atr`, `rvol`)
  - `notifier/formatters.py:179` — `elif isinstance(raw, int)`
    inside `_detect_signal_changes`
  - `notifier/formatters.py:233` — `if isinstance(raw, int)` inside
    `compose_email_subject._extract_signal`
  - `notifier/formatters.py:313` — `if isinstance(raw, int)` inside
    `_extract_signal_int`
  - `daily_run.py:171,255` — `isinstance(state['signals'].get(state_key), dict)`
    + `isinstance(raw, int)`
  - `crash_boundary.py:102,103` — `isinstance(sig_spi, dict) else sig_spi`

If the post-migration invariant (truth #1) is real, these are unreachable
dead code that *misleads readers about what shapes the renderer accepts*.
If the branches are needed (e.g., a test fixture builds a state without
calling `_migrate_v9_to_v10`), then the truth #1 invariant is overstated
and Plan 27-09 didn't actually finish.

**Fix:**
Decide which it is.
- If the migration is authoritative: delete every `isinstance(..., int)`
  branch in the file list above (and add one more line to
  `tests/test_signal_shape_migration.py::TestRendererDefensiveIntBranchRemoved`
  to cover them).
- If readers genuinely need the lenience: document why in CLAUDE.md and
  drop the "post-migration invariant: dict-only" claim from
  `state_manager._migrate_v9_to_v10` docstring.

### WR-03: state_manager docstring states MAX_WARNINGS = 100 (drift)

**File:** `state_manager.py:1082-1090` (docstring inside `append_warning`)
**Issue:**
Docstring text says "MAX_WARNINGS = 100 is intentionally conservative for
v1's daily cadence (~5 months of warnings at 1/day average). A bad-day
loop generating 50+ warnings in one run still fits within the bound."
The actual constant in `system_params.MAX_WARNINGS` is now `50` (Phase 27
#16 review-fix agreed-4, locked by `tests/test_warnings_fifo.py`). The
docstring was not updated alongside the constant.

The numeric example in the docstring ("5 months at 1/day", "50+ warnings
in one run still fits") is now also wrong — at MAX_WARNINGS=50 a single
50-warning run *fills* the bound, leaving zero history.

**Fix:**
Edit the docstring:
```python
'''
MAX_WARNINGS rationale:
  MAX_WARNINGS = 50 (Phase 27 #16 agreed-4 — tightened from prior 100
  baseline). At v1's daily cadence this is ~7 weeks of warnings at
  1/day average. A bad-day loop generating 25+ warnings in one run
  fills half the bound; chronic high-warning regimes should bump
  MAX_WARNINGS rather than expanding the contract.
'''
```

### WR-04: SPI/AUDUSD multiplier constants duplicated in web/routes

**File:** `web/routes/paper_trades.py:63-64`,
         `dashboard_legacy/paper_trades_section.py:120`
**Issue:**
Both files hardcode `{'SPI200': 5.0, 'AUDUSD': 10000.0}` as a local
multiplier dict. The single source of truth is `system_params.SPI_MULT`
+ `system_params.AUDUSD_NOTIONAL`. If an operator updates the multiplier
in `system_params.py` (e.g., for a new contract size), the paper-trade
routes silently keep using the stale value — divergent P&L.

The same pattern exists for `_COST_AUD = {'SPI200': 6.0, 'AUDUSD': 5.0}`
in `web/routes/paper_trades.py:63`, which duplicates `SPI_COST_AUD` /
`AUDUSD_COST_AUD`.

The header comment at line 62 acknowledges the duplication: "Mirror of
system_params constants — kept here so pnl_engine stays decoupled per
planner D-19 + Phase 2 D-17. If system_params changes, update here and
bump tests." The fact that it requires a manual sync-up is the bug — no
test enforces the parity.

**Fix:**
Either:
1. Add a regression test:
   ```python
   def test_paper_trade_route_consts_match_system_params() -> None:
       from web.routes.paper_trades import _MULTIPLIER, _COST_AUD
       from system_params import SPI_MULT, AUDUSD_NOTIONAL, SPI_COST_AUD, AUDUSD_COST_AUD
       assert _MULTIPLIER == {'SPI200': SPI_MULT, 'AUDUSD': AUDUSD_NOTIONAL}
       assert _COST_AUD == {'SPI200': SPI_COST_AUD, 'AUDUSD': AUDUSD_COST_AUD}
   ```
2. Or import directly from `system_params` and accept the local-import
   coupling.

### WR-05: paper_trades_section row.get('id', '') feeds html.escape — type fragility

**File:** `dashboard_legacy/paper_trades_section.py:142-143`
**Issue:**
```python
trade_id = row.get('id', '')
esc_id = html.escape(trade_id, quote=True)
```
`html.escape` requires a `str`. `row.get('id')` may legitimately return
`None` or an int (no type check on read), and `html.escape(None, quote=True)`
raises `TypeError: must be str, not NoneType`. The default `''` sentinel
catches the *missing key* case but not the *present-but-non-str* case.

Same pattern in lines 251 (`trade_id = row.get('id', '')` in closed-trades
loop), 144 (`row.get('instrument', '')`), 180–183 (positional `row.get(...)`
inside `html.escape(str(...))` already coerces — that's fine).

The catastrophic outcome is a dashboard render crash if a malformed paper
trade row ever lands in state. `_render_dashboard_never_crash` catches it,
but the dashboard then renders stale or empty.

**Fix:**
Force string coercion at the boundary:
```python
trade_id = str(row.get('id', '') or '')
esc_id = html.escape(trade_id, quote=True)
```
or wrap in `_render_paper_trades_open` itself:
```python
def _safe_str(v) -> str:
    return str(v) if v is not None else ''
```

### WR-06: notifier.py monolith path referenced in test fixture comment after split

**File:** `tests/test_crash_email_fallback.py:112`
**Issue:**
Test fixture builds a fake traceback string with the literal `'  File
"notifier.py", line 1423\n'`. Post-split, line 1423 of the package file
no longer corresponds to the same code (and `notifier.py` itself is dead
code). The test still passes because it only asserts that the redaction
helper handles the fake traceback string — but the fixture is a documented
lie that will mislead the next reader debugging the test.

**Fix:**
Update the fixture string to point at a current package file:
```python
'  File "notifier/dispatch.py", line 257\n'
```
or replace with a clearly-fake placeholder:
```python
'  File "<test-fixture>", line 1\n'
```

### WR-07: dashboard_legacy/section_renderers.py equity-chart label text untrusted

**File:** `dashboard_legacy/section_renderers.py:162`
**Issue:**
```python
labels = [row['date'] for row in distinct]
...
payload = json.dumps({'labels': labels, 'data': data}, ...)
```
`row['date']` flows from `state['equity_history']` rows. State is operator-
controlled but persisted via JSON — a malicious or buggy write path could
set `row['date']` to a string containing `</script>`. The `.replace('</',
'<\\/')` defence (line 177) catches that specific case, but only AFTER the
`json.dumps` call. `json.dumps` itself escapes `</` only when needed for
JSON validity, not for HTML safety — Python's `json` module passes `</`
through verbatim.

The replace is correctly defensive (matches Pitfall 1 in the docstring),
but the comment claims "json.dumps + .replace('</', '<\\/')" is the full
defence. It should also include `ensure_ascii=False` justification: the
`</` replace only catches forward-slash bytes, not Unicode line separators
(U+2028, U+2029) which break some JS parsers. This is a hardening
deficiency, not a bug — the Phase 27 #8 XSS audit didn't catch it because
the audit was scoped to renderer leaves, not chart payload assembly.

**Fix:**
Either add an explicit `</` and `  ` scrub:
```python
payload = json.dumps({...}, ensure_ascii=True, ...)  # ASCII-only, escapes U+2028/9
payload = payload.replace('</', '<\\/')
```
or document the existing posture in the docstring ("Pitfall 1: we accept
the U+2028/9 risk because Chart.js's parser is the V8 JSON parser which
handles them; ASCII-only JSON would be safer if the consumer changes").

### WR-08: dashboard_renderer/components/signals.py line 79 redundant isinstance check

**File:** `dashboard_renderer/components/signals.py:79`
**Issue:**
```python
trace_sig_dict = sig_entry if isinstance(sig_entry, dict) else {}
```
This is the same dead-defensive pattern as WR-02. Per Plan 27-09 truth #1,
post-migration `sig_entry` is either `None` (handled at line 34) or a
dict. If it's `None`, this line silently sets `trace_sig_dict = {}` —
which is fine, but expressed redundantly. The `isinstance(sig_entry, dict)`
test cannot fire after the v10 migration except in test fixtures that
build state without calling `_migrate_v9_to_v10`.

**Fix:**
After resolving WR-02 (decide if migration is authoritative), simplify:
```python
trace_sig_dict = sig_entry or {}
```

## Info

### IN-01: paper_trade_alerts.py line 80 NaN check via self-inequality is opaque

**File:** `paper_trade_alerts.py:80`
**Issue:**
```python
if atr != atr:  # NaN check (no math import needed — NaN != NaN)
```
The technique works but reads as a typo. `math.isnan(atr)` is the standard
idiom; `paper_trade_alerts.py` does not import `math` — but the file
already imports `state_manager` and `alert_engine` so adding `math` is
trivial. The same pattern recurs in `notifier/templates_alerts.py:166,231`.

**Fix:**
Add `import math` and use `if math.isnan(atr):` for readability.

### IN-02: state_manager.py module docstring claims fcntl is reentrant in same process

**File:** `state_manager.py:46-50`
**Issue:**
The docstring says: "fcntl.flock is reentrant within a single process, so
the inner save_state's lock acquisition is a kernel no-op when the outer
mutate_state lock is already held".

The code below (line 668-678) and the actual implementation contradicts
this — it explicitly notes "INTRA-PROCESS REENTRANCY (Rule 1 fix vs
original RESEARCH §Pattern 9 which mistakenly claimed reentrancy across
DIFFERENT fds): on POSIX, flock locks the open-file-description, NOT the
inode/path. Two fds in the SAME process do NOT share lock ownership".

The module-level docstring still has the stale claim from RESEARCH §Pattern
9. A reader trusting the module docstring would conclude reentry is safe;
a reader of `_atomic_write` knows it isn't.

**Fix:**
Edit the module docstring to match the corrected `_atomic_write` docstring:
```
fcntl.flock locks the open-file-description, NOT the inode/path. Two
fds in the same process do NOT share lock ownership; the inner save_state
must call _atomic_write_unlocked when the outer mutate_state already
holds the lock.
```

### IN-03: notifier/__init__.py CLI entrypoint logging.basicConfig may double-init

**File:** `notifier/__init__.py:213-225`
**Issue:**
The `_cli_main()` function calls `logging.basicConfig(level=logging.INFO,
...)` without `force=True`. If the package is imported by a process that
already configured logging (e.g., via `main.py:100`), the basicConfig call
is a silent no-op and the CLI's INFO-level emit may not appear. Per
LEARNING in `~/.claude/CLAUDE.md` ("Pitfall 4: logging.basicConfig MUST use
force=True"), this is a known footgun.

The CLI is operator-only (running `python -m notifier` standalone), so the
risk is low — but the convention in the rest of the codebase is to use
`force=True` (see `main.py:100`).

**Fix:**
```python
logging.basicConfig(level=logging.INFO, format='%(message)s', force=True)
```

### IN-04: dashboard_legacy/__init__.py is a 150-line re-export shim with duplicate __all__

**File:** `dashboard_legacy/__init__.py:13-150`
**Issue:**
The package `__init__.py` imports every public symbol from every
sub-module, then re-declares them in `__all__`. The `dashboard.py` shim
file (lines 126–213) also imports the same symbols into the `dashboard`
namespace. Result: every dashboard helper has at least three valid import
paths:
- `from dashboard_legacy.account_section import _render_account_stats`
- `from dashboard_legacy import _render_account_stats`
- `from dashboard import _render_account_stats`

This is intentional (test compat + dashboard.py shim), but the duplication
is not load-bearing — `dashboard_legacy/__init__.py` could just be empty,
and downstream callers that go through `dashboard.X` would still work.
Killing the `__init__.py` re-exports would cut 150 lines of churn from
future maintenance.

**Fix:**
Reduce `dashboard_legacy/__init__.py` to:
```python
"""dashboard_legacy — split-out subpackage. Public access via dashboard.py shim."""
```
Then any test that imports `from dashboard_legacy import _render_*`
either updates to `from dashboard import _render_*` or to the specific
sub-module. Lower priority since the duplication doesn't cause bugs.

### IN-05: paper_trades.py _D09_KEYS frozenset defined but never referenced

**File:** `web/routes/paper_trades.py:66-70`
**Issue:**
```python
_D09_KEYS = frozenset({
  'id', 'instrument', 'side', 'entry_dt', 'entry_price', 'contracts',
  'stop_price', 'entry_cost_aud', 'status', 'exit_dt', 'exit_price',
  'realised_pnl', 'strategy_version',
})
```
A grep through the codebase shows zero references to `_D09_KEYS`. It was
likely intended as a row-shape contract for a validator that was never
wired up. Dead code.

**Fix:**
Delete the constant, OR add the validator that consumes it:
```python
def _validate_paper_trade_row_shape(row: dict) -> None:
    missing = _D09_KEYS - row.keys()
    if missing:
        raise HTTPException(status_code=500, detail=f'paper_trade row missing keys: {missing}')
```
and call it at the rendering boundary.

### IN-06: scheduler_driver.py _get_process_tzname imports time inside function body

**File:** `scheduler_driver.py:42`
**Issue:**
```python
def _get_process_tzname() -> str:
  import time as _time  # LOCAL — keep stdlib import graph tidy
  return _time.tzname[0]
```
`time` is stdlib; the local-import idiom is project convention for
"never-crash wrappers" (per `_send_email_never_crash` precedent). But
`_get_process_tzname` is not a never-crash wrapper — it's a plain test
seam. The local-import here is cargo-culted, not load-bearing. The same
function calls `_time.tzname[0]` exactly once; importing at module-top
saves a per-call overhead and matches the rest of the file's `import
logging` / `import system_params` style.

**Fix:**
Move `import time` to module top alongside the other stdlib imports.
Trivial; just removes one cargo-cult.

---

_Reviewed: 2026-05-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
