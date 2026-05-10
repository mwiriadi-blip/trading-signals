---
phase: 27
plan: 02
subsystem: http-transport + system_params
tags:
  - phase-27
  - http-timeout
  - hung-network
  - dos-mitigation
  - single-source-of-truth
  - yfinance-session
requires:
  - 27-06 (data_fetcher._get_yf accessor — hook point for session injection)
provides:
  - system_params.HTTP_TIMEOUT_S (single canonical outbound HTTP timeout = 30s)
  - data_fetcher._get_yf_session() (memoized requests.Session with HTTP_TIMEOUT_S default)
affects:
  - tests/test_data_fetcher.py (fake Ticker factory accepts session= kwarg)
  - tests/test_integration_f1.py (full-chain fake Ticker accepts session= kwarg)
tech-stack:
  added: []
  patterns:
    - Single-source HTTP timeout constant + AST regression for cross-module enforcement
    - requests.Session with patched .request injecting timeout setdefault (yfinance internal HTTP cover)
    - yfinance Ticker(symbol, session=...) injection for transport-layer config
key-files:
  created:
    - tests/test_http_timeouts.py
  modified:
    - system_params.py
    - notifier.py
    - data_fetcher.py
    - tests/test_data_fetcher.py
    - tests/test_integration_f1.py
decisions:
  - HTTP_TIMEOUT_S = 30 (matches the previous _RESEND_TIMEOUT_S; preserves notifier read-budget unchanged)
  - notifier.requests.post keeps `timeout=(5, timeout_s)` parameter form (preserves crash-email caller-override capability)
  - yfinance session config lives behind _get_yf_session() accessor — module-top mutation forbidden so cold-start path (--version) never builds a Session
  - .request setdefault('timeout', ...) — does NOT override caller-supplied timeouts; only fires for yfinance-internal calls without one
  - AST walker is BEHAVIORAL (asserts `timeout=` kwarg present), not literal (does NOT require `timeout=HTTP_TIMEOUT_S` in source) — accepts tuples, parameters, computed values
  - yfinance package internals explicitly filtered from AST scan (we control yfinance via session injection, not by editing its source)
metrics:
  duration: ~9min
  tasks: 1
  files: 5
  tests-added: 5
  tests-passing: 1816 (full suite, +5 from 1811)
  completed: 2026-05-07
---

# Phase 27 Plan 02: HTTP Timeout Standardization Summary

Standardized every outbound HTTP call's timeout to a single canonical `HTTP_TIMEOUT_S = 30` in `system_params.py`. Deleted the duplicate `_RESEND_TIMEOUT_S` constant from `notifier.py`. Wired the timeout into yfinance via a memoized `requests.Session` exposed through the new `_get_yf_session()` accessor (the documented hook point reserved by Plan 27-06). AST regression test prevents future bare-timeout calls from sneaking in.

## What shipped

### Single source of truth: `system_params.HTTP_TIMEOUT_S`

Added a typed module-level constant with comment explaining the threat model (T-27-02-01 hung-network DoS, T-27-02-02 constant drift). Lives near `STRATEGY_VERSION` per plan spec. No callers existed before this plan — every consumer added in this plan imports from system_params, never inlines.

### `notifier.py` — duplicate constant deleted, canonical imported

| Before                                                       | After                                                                        |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| `_RESEND_TIMEOUT_S = 30` (notifier.py:106 — local constant) | Deleted; replaced with explanatory comment pointing to system_params         |
| `from system_params import (...)` (no HTTP_TIMEOUT_S)        | `HTTP_TIMEOUT_S` added to the import block (alphabetical ordering preserved) |
| `timeout_s: int = _RESEND_TIMEOUT_S` (default arg)           | `timeout_s: int = HTTP_TIMEOUT_S`                                            |
| `timeout=(5, timeout_s)` at the requests.post call site      | **Unchanged** — preserves the `(5, ...)` connect/read tuple semantics        |

The call site continues to use the `timeout_s` parameter (not the literal `HTTP_TIMEOUT_S`) so the crash-email path (Phase 8, Phase 12) and any future caller can still override the read-phase budget while inheriting the canonical default. Both callers in the codebase use the default, so behavior is unchanged.

### `data_fetcher.py` — yfinance session injection via `_get_yf_session()`

yfinance 1.2.0's `Ticker(symbol, session=session)` accepts a `requests.Session`. We build a session whose `.request` is monkey-patched to `setdefault('timeout', HTTP_TIMEOUT_S)`. yfinance-internal HTTP calls (history, metadata scrapers, options chains) inherit a 30s budget without requiring per-call code changes inside the library.

```python
def _get_yf_session():
  global _yf_session
  if _yf_session is None:
    s = requests.Session()
    _orig = s.request
    def _patched(method, url, **kwargs):
      kwargs.setdefault('timeout', HTTP_TIMEOUT_S)
      return _orig(method, url, **kwargs)
    s.request = _patched
    _yf_session = s
  return _yf_session
```

`fetch_ohlcv` now calls `yf_mod.Ticker(symbol, session=yf_session)` and passes `timeout=HTTP_TIMEOUT_S` (was `timeout=10` — a previous one-off literal that diverged from the rest of the codebase). The retry loop, exception tuple, and all other behavior is unchanged.

**Why the accessor pattern (not module-top session)** — Plan 27-06 deferred yfinance import precisely so `python main.py --version` skips the heavy load. Building a `requests.Session` at module top would defeat that. The session is memoized lazily, paid-once-per-process, and only when `fetch_ohlcv` is actually exercised.

**setdefault, not assignment** — `_patched` uses `kwargs.setdefault('timeout', HTTP_TIMEOUT_S)` so an explicit caller-supplied timeout (e.g. fast metadata pings) still wins. Only yfinance-internal calls that omit `timeout=` get the canonical default.

### AST regression test — `tests/test_http_timeouts.py` (5 tests)

| Test                                            | Locks in                                                                                                |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `test_http_timeout_constant_present`            | `system_params.HTTP_TIMEOUT_S == 30` (int) — single source survives refactors                           |
| `test_resend_timeout_constant_deleted`          | `_RESEND_TIMEOUT_S` is NOT defined as a module-level assignment in notifier.py (regex on `^_RESEND...=`) |
| `test_post_to_resend_uses_canonical_timeout`    | `inspect.signature(_post_to_resend).timeout_s.default == HTTP_TIMEOUT_S` AND source has `timeout=(5, timeout_s)` (or HTTP_TIMEOUT_S) |
| `test_no_bare_requests_call_in_prod`            | AST walker — every `requests.METHOD`, `from requests import METHOD` bare call, `urllib.request.urlopen`, `httpx.METHOD` in PROD passes `timeout=` |
| `test_yfinance_internals_filtered`              | The PROD-files resolver explicitly excludes anything under `yfinance/` (documents the agreed-6 filter) |

The AST walker tracks aliased imports (`import requests as r`) and from-imports (`from requests import post`). Detection scope: `requests.{get,post,put,delete,head,patch}`, `urllib.request.urlopen`, `httpx.{get,post,...}`. Heuristic: Session-method calls are NOT statically detectable without a type system; we accept that false-negative gap (the codebase has zero `Session.METHOD` calls today, so the gap is theoretical).

The walker is BEHAVIORAL — it asserts that `timeout=` is present as a keyword argument, NOT that the value is the literal `HTTP_TIMEOUT_S`. This was an explicit review-fix M1 decision: callers may pass tuples, computed values, or aliased names without breaking the regression.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test fakes did not accept `session=` kwarg**
- **Found during:** Task 1 GREEN phase, after wiring `yf.Ticker(symbol, session=yf_session)`.
- **Issue:** `tests/test_data_fetcher.py::_make_fake_ticker_factory._factory(symbol)` and `tests/test_integration_f1.py::_fake_ticker(sym)` both took only the positional symbol arg. Adding `session=` to the production call broke 1+ test in each file with `TypeError: ... got an unexpected keyword argument 'session'`.
- **Fix:** Updated both fakes to accept (and ignore) `session=None`. Fakes don't make real HTTP so the session is irrelevant — but the kwarg must be accepted to match the real `yf.Ticker` signature.
- **Files modified:** `tests/test_data_fetcher.py`, `tests/test_integration_f1.py`.
- **Commit:** `6aaadd7` (rolled into the GREEN feat commit).

### Plan-spec adjustments

**Loosened the source-pattern check in `test_post_to_resend_uses_canonical_timeout`** — the plan example asserted the literal string `timeout=(5, HTTP_TIMEOUT_S)`. The production code uses `timeout=(5, timeout_s)` to preserve the parameter-override capability for the crash-email path and any future caller. The test accepts both shapes via `timeout=\(5,\s*(HTTP_TIMEOUT_S|timeout_s)\)` and additionally asserts `inspect.signature` resolves the `timeout_s` default to `HTTP_TIMEOUT_S`. Strictly stronger than a literal-string check (catches a refactor that names the default `RESEND_T` but assigns it to 30).

## Authentication gates

None — no auth surface touched.

## Threat surface scan

None — `HTTP_TIMEOUT_S` and `_get_yf_session()` are correctness-only changes. No new endpoints, no auth paths, no file access, no schema. The threat register entries in the plan (T-27-02-01 DoS, T-27-02-02 constant drift) are mitigations, not new surface.

## Verification

```
pytest tests/test_http_timeouts.py -x -v                 # 5 green
pytest tests/test_data_fetcher.py tests/test_integration_f1.py -x  # all green (fakes updated)
pytest                                                     # 1816 green (full suite, +5 from 1811)
grep -nE '^\s*_RESEND_TIMEOUT_S\s*=' notifier.py          # no matches (single-source enforced)
grep -n 'HTTP_TIMEOUT_S' system_params.py notifier.py data_fetcher.py
  # → defined once in system_params.py:42; consumed in notifier.py + data_fetcher.py
```

## Patched call sites

| File             | Line       | Call                                                  | Timeout source                                  |
| ---------------- | ---------- | ----------------------------------------------------- | ----------------------------------------------- |
| notifier.py      | 1374       | `requests.post('https://api.resend.com/emails', ...)` | `(5, timeout_s)` where `timeout_s = HTTP_TIMEOUT_S` |
| data_fetcher.py  | 230        | `yf_mod.Ticker(symbol, session=yf_session)`           | session-level default via `_get_yf_session()`   |
| data_fetcher.py  | 234        | `ticker.history(timeout=HTTP_TIMEOUT_S)`              | direct (was `timeout=10` — drift fixed)         |

## Commits

| Hash    | Type | Title                                                                                  |
| ------- | ---- | -------------------------------------------------------------------------------------- |
| 49445bd | test | RED — HTTP_TIMEOUT_S constant + AST regression for outbound HTTP timeouts              |
| 6aaadd7 | feat | GREEN — HTTP_TIMEOUT_S=30 single source + yfinance session injection                   |

## Self-Check: PASSED

- `system_params.py` modified — confirmed (HTTP_TIMEOUT_S at line 42).
- `notifier.py` modified — confirmed (HTTP_TIMEOUT_S import, _RESEND_TIMEOUT_S deleted, timeout_s default updated).
- `data_fetcher.py` modified — confirmed (`_get_yf_session()` added, fetch_ohlcv wires session + HTTP_TIMEOUT_S).
- `tests/test_http_timeouts.py` created — confirmed (5 tests, all green).
- `tests/test_data_fetcher.py` modified — confirmed (factory accepts session=).
- `tests/test_integration_f1.py` modified — confirmed (fake ticker accepts session=).
- Both commit hashes (49445bd, 6aaadd7) resolvable via `git log --oneline`.
- Full suite 1816 green; +5 new tests landed cleanly.
