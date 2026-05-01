---
phase: 23-five-year-backtest-validation-gate
reviewed: 2026-05-01T00:00:00+08:00
depth: standard
files_reviewed: 18
files_reviewed_list:
  - backtest/__init__.py
  - backtest/__main__.py
  - backtest/cli.py
  - backtest/data_fetcher.py
  - backtest/metrics.py
  - backtest/render.py
  - backtest/simulator.py
  - tests/test_backtest_cli.py
  - tests/test_backtest_data_fetcher.py
  - tests/test_backtest_metrics.py
  - tests/test_backtest_render.py
  - tests/test_backtest_simulator.py
  - tests/test_signal_engine.py
  - tests/test_web_backtest.py
  - web/routes/backtest.py
  - web/app.py
  - requirements.txt
  - .gitignore
findings:
  critical: 2
  warning: 4
  info: 0
  total: 6
status: issues_found
---

# Phase 23: Code Review Report

**Reviewed:** 2026-05-01T00:00:00+08:00
**Depth:** standard
**Files Reviewed:** 18
**Status:** issues_found

## Summary

Phase 23 introduces a bar-by-bar backtest engine (data_fetcher, simulator, metrics, render, CLI, web routes). The hexagonal boundary is respected: `web/routes/backtest.py` imports only from `backtest.*` — no direct `signal_engine`/`sizing_engine` imports. The path-traversal defence is correctly implemented (regex + whitelist). Financial math in `metrics.py` is correct (cummax drawdown, strict >100% threshold, annualised Sharpe). The cost model is correct for account-balance accounting.

Two blockers found: exception message XSS in the web error page, and unhandled JSON parse failure in report loading. Four warnings: undeclared `python-dateutil` dependency, missing broad exception catch in POST handler, file-stat race in `_list_reports`, and a `cost_aud` display error for pyramided trades.

---

## Critical Issues

### CR-01: ShortFrameError message rendered unescaped into HTML

**File:** `web/routes/backtest.py:197`
**Issue:** The `ShortFrameError` exception string is interpolated directly into an HTML response without `html.escape`. The message is constructed in `data_fetcher.py` and includes the yfinance symbol (hardcoded, low risk) and `span_years` (a float from yfinance data). While the current code path is low-risk, this pattern is XSS-unsafe: any future change to `ShortFrameError` message format that includes user-adjacent or external data would immediately become an injection vector. The `DataFetchError` handler on line 202 correctly avoids echoing `exc` into HTML — `ShortFrameError` is inconsistent with that safe pattern.

```python
# CURRENT (line 197) — unescaped exc in HTML:
f'<section class="error"><h1>Backtest cannot run.</h1><p>{exc}</p>'

# FIX — apply html.escape:
import html as _html
f'<section class="error"><h1>Backtest cannot run.</h1><p>{_html.escape(str(exc))}</p>'
```

---

### CR-02: Unhandled JSONDecodeError in _load_report causes unmasked 500

**File:** `web/routes/backtest.py:86`
**Issue:** `_load_report` calls `json.loads(path.read_text())` with no `try/except`. A corrupt or truncated JSON file in `.planning/backtests/` (e.g. from an interrupted write, disk full, or manual edit) raises `json.JSONDecodeError`, which propagates through `get_backtest` and `post_backtest_run` callers as an unhandled exception. FastAPI returns a 500 with a stack trace — an operator-visible crash for what should be a graceful 400/error-page. Note: `run_backtest` in `cli.py` uses `allow_nan=False` during write but does not use atomic write (tempfile + rename), so a kill-during-write can produce a truncated file.

```python
# FIX — wrap _load_report:
def _load_report(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning('%s corrupt/unreadable report %s: %s', _LOG_PREFIX, path.name, exc)
        raise ValueError(f'corrupt report file: {path.name}') from exc
    data.setdefault('metadata', {})
    data['metadata']['filename'] = path.name
    return data
```

Then in `get_backtest` and the history loader, catch `ValueError` from `_load_report` and skip the corrupt file (or return a 400 error page).

---

## Warnings

### WR-01: python-dateutil is an undeclared direct dependency

**File:** `requirements.txt` / `backtest/cli.py:28`
**Issue:** `backtest/cli.py` directly imports `from dateutil.relativedelta import relativedelta`. `python-dateutil` is NOT listed in `requirements.txt`. It is available only as a transitive dependency of `pandas`. Per the CLAUDE.md convention ("Exact version pins... maintained in requirements.txt"), direct use of a transitive dep is fragile: a future pandas release that drops `dateutil` as a required dep (or changes the version bound) would silently break the CLI at import time with no lockfile protection.

```
# FIX — add to requirements.txt alongside pyarrow:
python-dateutil==2.9.0.post0
```

---

### WR-02: POST /backtest/run catches only two exception types; others produce 500

**File:** `web/routes/backtest.py:191-211`
**Issue:** `run_backtest` can raise exceptions beyond `ShortFrameError` and `DataFetchError`:
- `ValueError` from `simulate()` (invalid `initial_account_aud` or `cost_round_trip_aud`) — theoretically gated by web-layer validation, but the validation is duplicated independently in two layers with no shared contract.
- `OSError` / `PermissionError` from `output_path.parent.mkdir()` or `output_path.open('w')` — e.g. disk full, read-only filesystem.
- Any exception from `system_params` import at the top of `run_backtest`.

All of these propagate as unhandled exceptions and become 500 responses with stack traces rather than operator-friendly error pages.

```python
# FIX — add a broad fallback after the two specific catches:
except (ShortFrameError, DataFetchError, ValueError, OSError) as exc:
    # ... specific handling per type ...
except Exception as exc:
    logger.exception('%s unexpected error in run_backtest', _LOG_PREFIX)
    return HTMLResponse(
        content=_wrap_html(
            '<section class="error"><h1>Backtest failed unexpectedly.</h1>'
            '<p>Check server logs for details.</p>'
            '<p><a href="/backtest">← Back</a></p></section>'
        ),
        status_code=500,
    )
```

---

### WR-03: _list_reports raises FileNotFoundError if a file is deleted between iterdir and stat

**File:** `web/routes/backtest.py:79-80`
**Issue:** `_list_reports` iterates directory entries then calls `p.stat()` on each in a separate statement. Between the `iterdir()` snapshot and the `stat()` call, a file could be deleted (e.g. manually by the operator). `p.stat()` then raises `FileNotFoundError` which propagates unhandled through the route handler, producing a 500. On a single-operator droplet the risk is low, but the fix is one line.

```python
# FIX:
files = []
for p in backtest_dir.iterdir():
    if p.is_file() and p.suffix == '.json':
        try:
            files.append((p.stat().st_mtime, p))
        except FileNotFoundError:
            pass  # deleted between iterdir and stat
files.sort(key=lambda t: t[0], reverse=True)
return [p for _, p in files]
```

---

### WR-04: cost_aud field in trade log understates costs for pyramided positions

**File:** `backtest/simulator.py:172`
**Issue:** The `cost_aud` field in the trade log is set to `float(cost_round_trip_aud)` — a flat per-trade value — regardless of `n_contracts`. With `MAX_PYRAMID_LEVEL = 2` (up to 3 contracts), the actual total round-trip cost for a fully pyramided position is `cost_round_trip_aud * n_contracts` (e.g. 18 AUD for SPI at 3 contracts). The rendered trade table shows 6 AUD cost for a trade that actually consumed 18 AUD in commissions. Account-balance arithmetic is correct (costs flow through sizing_engine's unrealised/realised PnL correctly). This is a display/reporting error only — but operators reading the trade log will see misleading cost data.

```python
# CURRENT (line 172):
'cost_aud': float(cost_round_trip_aud),  # full round-trip for D-05 display

# FIX — multiply by n_contracts to reflect actual total cost:
'cost_aud': float(cost_round_trip_aud * ct.n_contracts),
```

Note: the corresponding test in `test_backtest_simulator.py:81` asserts `t['cost_aud'] == 6.0` unconditionally — that test would need to be updated to assert `t['cost_aud'] == 6.0 * t['contracts']`.

---

_Reviewed: 2026-05-01T00:00:00+08:00_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
