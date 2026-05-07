---
phase: 27
plan: 06
subsystem: data-fetcher + main-cli
tags:
  - phase-27
  - cold-start
  - lazy-import
  - cli
  - version-flag
requires: []
provides:
  - data_fetcher._get_yf accessor
  - data_fetcher.YFRateLimitError module-level proxy
  - main.py --version flag
affects:
  - tests/test_data_fetcher.py (still green; monkeypatch contract preserved)
  - any code doing `from data_fetcher import YFRateLimitError`
tech-stack:
  added: []
  patterns:
    - PEP 562 module-level __getattr__ for lazy attribute access
    - subprocess-based clean-sys.modules assertions
    - early sys.argv short-circuit before heavy imports
key-files:
  created:
    - tests/test_deferred_yfinance_import.py
    - tests/test_version_flag.py
  modified:
    - data_fetcher.py
    - main.py
decisions:
  - Use PEP 562 __getattr__ to keep `data_fetcher.yf.Ticker` monkeypatch contract intact
  - Module-level YFRateLimitError as Exception subclass (proxy), not the real lib class, to keep import lazy
  - Dual handler for --version (early sys.argv hook + argparse store_true + post-parse short-circuit)
  - Use "yfinance not in sys.modules" as the cold-start invariant (NOT wall-clock <500ms — CI-flaky)
  - Defer Plan 27-02 HTTP_TIMEOUT_S session config to that plan (timeout=10 stays inline today)
metrics:
  duration: ~25min
  tasks: 2
  files: 4
  tests-added: 8
  tests-passing: 1811 (full suite, +8 from 1803)
  completed: 2026-05-08
---

# Phase 27 Plan 06: Deferred yfinance import + --version flag Summary

Two cheap entry-point cleanups bundled: deferred yfinance import via a `_get_yf()` accessor (Phase 27 #14) plus a `--version` flag that prints `STRATEGY_VERSION` and exits 0 before any heavy app-module imports (Phase 27 #17). Cold-start invariant verified semantically (yfinance not in sys.modules) rather than via wall-clock timing.

## What shipped

### Task 1 — Deferred yfinance import + module-level YFRateLimitError proxy

`data_fetcher.py` no longer imports yfinance at module-load time. Three coordinated mechanisms preserve the public contract:

1. **`_get_yf()` accessor** — memoized lazy import of the `yfinance` module. First call inside `fetch_ohlcv` pays the import cost; subsequent fetches in the same process are O(1). This is the explicit hook point Plan 27-02 will extend to build a `requests.Session` with `HTTP_TIMEOUT_S` default.

2. **PEP 562 module `__getattr__`** — when test code does `monkeypatch.setattr('data_fetcher.yf.Ticker', fake)`, attribute resolution for `yf` triggers `__getattr__('yf')`, which calls `_get_yf()` and binds the result on the module so subsequent lookups skip the dunder. **This preserves the existing test monkeypatch contract** without forcing eager import on every `import data_fetcher`.

3. **Module-level `YFRateLimitError` proxy** (review-fix M4) — a lightweight `Exception` subclass importable at module-top WITHOUT pulling yfinance. External `from data_fetcher import YFRateLimitError` clauses keep working; `_RETRY_EXCEPTIONS` still includes the proxy. The retry loop additionally extends its except tuple with the **real** `yfinance.exceptions.YFRateLimitError` resolved via `_get_yf_rate_limit_error()` so production rate-limit exceptions raised from inside `ticker.history()` are still caught.

**Why dual catch (proxy + real):** if external test code `raise data_fetcher.YFRateLimitError(...)` against a fake ticker, the proxy class is what gets raised — the retry loop must catch that too. Real-world rate-limit errors come from yfinance internals raising the library class. Both paths must be retry-eligible.

### Task 2 — `--version` flag with early sys.argv hook

`python main.py --version` prints `STRATEGY_VERSION` and exits 0, with **only `system_params` imported**. yfinance, data_fetcher, signal_engine, sizing_engine, dotenv — none of those are loaded.

Implementation is a three-layer dispatch:

1. **Early sys.argv hook** (top of `main.py`, before all heavy module imports):
   ```python
   if __name__ == '__main__' and '--version' in sys.argv[1:]:
     from system_params import STRATEGY_VERSION
     print(STRATEGY_VERSION)
     sys.exit(0)
   ```
   Cold-start path used by CLI users / GHA droplet asserts. Must be **lexically above** the `import data_fetcher` line to preserve the cold-start invariant.

2. **Argparse `--version` store_true** in `_build_parser()` — keeps `--help` complete by listing the flag, and registers the field on the namespace so the post-parse handler can read it.

3. **Post-parse handler in `main(argv)`** — `if getattr(args, 'version', False): print + return 0`. Reachable when tests call `main(['--version'])` directly (the `__main__` block doesn't fire on import paths).

## Test invariants

- 4 subprocess-based deferred-import tests (clean `sys.modules` requires fresh interpreter — pytest itself imports yfinance via `tests/test_data_fetcher.py`).
- 4 subprocess-based --version tests asserting rc=0, exact stdout `<version>\n`, no "Daily run" leakage, `--help` lists `--version`, and yfinance not in subprocess sys.modules.
- The cold-start assertion is **semantic** (`'yfinance' not in sys.modules`), not wall-clock. Wall-clock <500ms is incidental and CI-flaky on shared runners (review-fix M4).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - blocking] Adapted to existing test monkeypatch contract via PEP 562 __getattr__**
- **Found during:** Task 1 — read of `tests/test_data_fetcher.py`
- **Issue:** Plan said move `import yfinance as yf` into `_get_yf()`, but existing tests rely on `monkeypatch.setattr('data_fetcher.yf.Ticker', fake)` — that requires `yf` to be a module attribute. Naive removal would break ~10 fetch tests.
- **Fix:** Added module-level `__getattr__(name)` (PEP 562) that returns the lazily-imported yfinance module on first `data_fetcher.yf` access. After first access, the module attribute is bound on the module so subsequent lookups skip the dunder.
- **Files modified:** `data_fetcher.py`
- **Commit:** 5c72050

### Deferred to Plan 27-02

**HTTP_TIMEOUT_S session integration** — the plan called for `_get_yf()` to also build a `requests.Session` with a patched `.request` injecting `HTTP_TIMEOUT_S`. `system_params.HTTP_TIMEOUT_S` does not exist yet (Plan 27-02 has not landed). Today `fetch_ohlcv` continues passing `timeout=10` directly to `ticker.history()` — unchanged from before this plan. Plan 27-02 will own the session-config extension to `_get_yf()`.

## Authentication gates

None — no auth surface touched.

## Threat surface scan

None — `--version` is a read-only stdout print of a constant; deferred import is performance-only with no behavior change. No new endpoints, no auth paths, no file access, no schema. `<threat_model>N/A</threat_model>` in plan was correct.

## Verification

```
pytest tests/test_deferred_yfinance_import.py tests/test_version_flag.py -x -v   # 8 green
pytest tests/test_data_fetcher.py -x -v                                          # 12 green (existing)
pytest tests/test_main.py tests/test_scheduler.py -x                             # 140 green (existing)
pytest                                                                            # 1811 green (full suite, +8 from 1803)
.venv/bin/python main.py --version                                                # prints v1.2.0, exits 0
.venv/bin/python main.py --help | grep version                                    # --version listed
```

`grep -c '^import yfinance\|^from yfinance' data_fetcher.py` → `0` (verified done criterion).

## Commits

| Hash    | Type | Title                                                                                  |
| ------- | ---- | -------------------------------------------------------------------------------------- |
| 8003a68 | test | RED — deferred yfinance import + module-level YFRateLimitError                         |
| 5c72050 | feat | GREEN — defer yfinance import via _get_yf() + module-level YFRateLimitError proxy      |
| 3f6bb7e | test | RED — --version flag prints STRATEGY_VERSION + early sys.argv hook                     |
| 25cd522 | feat | GREEN — --version flag with early sys.argv short-circuit                               |

## Self-Check: PASSED

- `data_fetcher.py` modified — confirmed (108 insertions, 4 deletions in 5c72050)
- `main.py` modified — confirmed (31 insertions, 1 deletion in 25cd522)
- `tests/test_deferred_yfinance_import.py` created — confirmed (119 lines in 8003a68)
- `tests/test_version_flag.py` created — confirmed (111 lines in 3f6bb7e)
- All 4 commit hashes resolvable via `git log --oneline`
- Full suite 1811 green; +8 new tests landed cleanly
