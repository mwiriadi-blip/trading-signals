# Coding Conventions

**Analysis Date:** 2026-05-15

## Naming Patterns

**Files:**
- Module names: lowercase with underscores (e.g., `signal_engine.py`, `data_fetcher.py`, `state_manager.py`)
- Test files: `test_<module>.py` (e.g., `test_signal_engine.py`, `test_sizing_engine.py`)
- Test classes: `Test<Name>` (e.g., `TestDeterminism`, `TestRiskCalculation`)
- Test functions: `test_<behavior>` (e.g., `test_risk_pct_long_is_1pct`, `test_trail_mult_by_direction`)

**Functions:**
- Private helpers: `_leading_underscore_function_name` (e.g., `_wilder_smooth`, `_true_range`, `_atr`)
- Public functions: `snake_case` (e.g., `compute_indicators`, `get_signal`, `fetch_ohlcv`, `mutate_state`)
- Internal handlers/routes: `_<verb>_<noun>` (e.g., `_try_cookie`, `_try_basic`, `_set_web_auth_credentials_for_web_tests`)

**Variables:**
- Module-level constants: `UPPERCASE` (e.g., `LONG`, `SHORT`, `FLAT`, `ADX_GATE`, `ATR_PERIOD`, `VALID_SECRET`)
- Private constants (internal): `_LEADING_UNDERSCORE` (e.g., `_MIN_SECRET_LEN`, `_EMAIL_RE`, `_DEFAULT_RECOVERY_EMAIL`)
- Local/function variables: `lowercase_with_underscores` (e.g., `prev_close`, `stop_dist`, `vol_scale`)
- Index/temporary: Single letters acceptable in loops (e.g., `i` for index, `m` for momentum, `idx`)

**Types:**
- TypedDict classes: `PascalCase` (e.g., `SizingDecision`, `PyramidDecision`, `Position`)
- Dataclass attributes: `lowercase_with_underscores`
- Enum-like constants: `UPPERCASE` (e.g., `LONG = 1`, `SHORT = -1`, `FLAT = 0`)

## Code Style

**Formatting:**
- Tool: `ruff` (pyproject.toml [tool.ruff] enforces style)
- Indentation: 2-space (MANDATORY — never run `ruff format` which defaults to 4-space; breaks test gate)
- Quote style: single quotes (e.g., `'signal_engine'`, `'float64'`)
- Line length: 100 characters max
- Line ending: LF only

**Linting:**
- Tool: `ruff` with rules E, F, W, I, B, UP (errors, pyflakes, warnings, imports, bugbear, pyupgrade)
- isort integration: `signal_engine` is first-party (known-first-party)
- No unused imports; unused-code detection enabled via bugbear

## Import Organization

**Order:**
1. Standard library (stdlib) — `import os`, `import re`, `import json`, `from decimal import Decimal`, `from datetime import datetime`, etc.
2. Third-party libraries — `import pandas as pd`, `import numpy as np`, `import requests`, `from fastapi import FastAPI`, `from itsdangerous import ...`, etc.
3. First-party local modules (separated by blank line) — `import signal_engine`, `import system_params`, `from state_manager import ...`, etc.
4. Relative imports from same package (web/routes, notifier subdirs) — `from web.middleware.auth import AuthMiddleware`

**Path Aliases:**
- No import aliases except standard conventions: `import pandas as pd`, `import numpy as np`, `import yfinance as yf`
- Module names are NOT aliased (e.g., `import signal_engine` not `import signal_engine as se`)

**Comments on imports:**
- Conditional imports (e.g., `from yfinance.exceptions import YFRateLimitError`) used for clarity, not obfuscation
- F401 noqa comments used sparingly: document why import is kept (e.g., `# noqa: F401 — kept for hex audit symmetry`)

## Error Handling

**Patterns:**
- Custom exceptions defined at module level for domain-specific errors:
  - `class DataFetchError(Exception)` in `data_fetcher.py` — wraps yfinance/network errors
  - `class ResendError(Exception)` in `notifier/transport.py` — Resend HTTP failures
  - `class ShortFrameError(Exception)` in `data_fetcher.py` — insufficient OHLCV bars
- Built-in exceptions used for validation/contract errors:
  - `ValueError` for invalid inputs (e.g., `'invalid backtest filename'`, `'backtest file not found'`)
  - `RuntimeError` for unrecoverable startup failures (e.g., missing env vars, boot validation)
  - `HTTPException(status_code=...)` in web routes for client errors (e.g., `403` for auth, `404` for missing resource)
  - `TypeError` in JSON serializers (e.g., when Decimal cannot be encoded)

**Exception messages:**
- Descriptive and actionable: `'WEB_AUTH_USERNAME env var is missing or empty — refusing to start. Add WEB_AUTH_USERNAME=<your-name> to /home/trader/trading-signals/.env'`
- Include context when helpful: `f'invalid backtest filename: {filename!r}'`
- Use `!r` for repr() of values (adds quotes around strings, shows non-printables)
- Avoid interpolating secrets directly; use `redact_secret()` from `system_params.py` before logging/echoing

**Retry patterns:**
- Explicit retry loop with exception catching: `_RETRY_EXCEPTIONS = (YFRateLimitError, ConnectionError, TimeoutError, ...)` — each retryable exception explicitly listed
- Retry budget enforced (e.g., 3-5 attempts per call, not infinite)
- Rate-limit 429 errors raised as `HTTPError('429 rate-limit')` and caught separately (e.g., in `notifier/transport.py`)

## Logging

**Framework:** `logging` (stdlib) + `logger = logging.getLogger(__name__)` per-module

**Patterns:**
- All log lines use named loggers by module: `logger.info()`, `logger.warning()`, `logger.exception()`
- Info level: major orchestration steps (e.g., `'[Daily] run-date %s'`, `'[Web] processing request'`)
- Warning level: recoverable issues (e.g., `'size=0: undersized position'`)
- Exception level: caught exceptions with context (e.g., `logger.exception('failed to fetch data: %s', error)`)
- Log prefixes used for log filtering: `'[Daily]'`, `'[Alert]'`, `'[Web]'`, `'[Sched]'` identify the orchestration context

**Secret redaction:**
- ALL secrets (API keys, TOTP secrets, session tokens) must flow through `system_params.redact_secret()` BEFORE any log output
- `redact_secret(s: str | None) -> str` returns 6-char prefix + '...' or '[empty]' / '[short]'
- Pattern: `logger.info('API key %s', redact_secret(key))`

## Comments

**When to Comment:**
- Docstrings required for public functions and classes
- Inline comments for non-obvious logic (e.g., "Bar 0: Cprev is NaN; pandas max(skipna=True) returns H-L", "D-11: sum(TR) == 0 (flat prices) ⇒ +DI/-DI/ADX all NaN")
- Decision-point comments reference design decisions from LEARNINGS.md / phase docs (e.g., "D-07: Input DataFrame is NOT mutated")
- Pitfall/edge-case comments document boundaries: "Boundary behaviour: ADX exactly == ADX_GATE opens the gate"

**Module docstrings:**
- Always present at line 1, enclosed in `'''...\n...'''` triple-single-quotes
- Include: purpose + architecture context + phase/decision references (e.g., "Phase 1 D-07", "Hexagonal-lite")
- Example from `signal_engine.py`:
  ```python
  '''Signal Engine — pure-math indicator library + 2-of-3 momentum vote.

  Computes ATR(14), ADX(20) with +DI/-DI, Mom(21/63/252), RVol(20) on an OHLCV
  DataFrame and derives a deterministic LONG/SHORT/FLAT signal gated by ADX >= 25.

  SIG-01 formula interpretation (R-01): the spec text "..." is interpreted as intent.
  This module uses the SMA-seeded ewm idiom to match Wilder canonical to ~1e-14.

  Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY. No I/O, no network,
  no clock reads, no imports of state_manager / notifier / dashboard.
  '''
  ```

**JSDoc/TSDoc:**
- NOT used (Python only; Docstrings use plain text)
- Function docstrings use triple-quoted format with brief desc, optional Args/Returns, optional note about guarantees
- Example from `signal_engine.py`:
  ```python
  def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    '''Return NEW DataFrame = input + 8 indicator columns.

    Columns appended (exact names, exact order):
      ATR, ADX, PDI, NDI, Mom1, Mom3, Mom12, RVol.

    Guarantees:
      - Input DataFrame is NOT mutated (D-07).
      - All added columns are float64 (Pitfall 5).
      - NaN for warmup bars per each indicator's period.
    '''
  ```

## Function Design

**Size:**
- Target: 50 lines or fewer per function (not hard limit, but signal to refactor)
- Large functions broken into private helpers with descriptive names (e.g., `_wilder_smooth`, `_directional_movement`)

**Parameters:**
- Positional-only for core arguments (e.g., `def get_signal(df: pd.DataFrame, settings: dict | None = None)`)
- Optional parameters always have defaults and type hints
- Keyword-only parameters used when clarity helps: `def _post_to_resend(..., html_body: str = None, text_body: str = None)` — makes caller use `html_body=...`

**Return Values:**
- Single return value preferred; use TypedDict or tuple for multiple values
- NaN preserved as `float('nan')` not `None` in math layers (indicator return `float('nan')` so JSON serializers can handle NaN)
- Example from `signal_engine.py`: `get_latest_indicators()` returns dict with `{'atr': float(...), ...}` where NaN is `float('nan')` not None
- Web handlers return `JSONResponse`, `HTMLResponse`, or raise `HTTPException(status_code=...)`

## Module Design

**Exports:**
- Explicit public API — functions meant for import are defined at module top-level
- Private implementation helpers use `_leading_underscore` (not exported)
- Docstring clearly states what's public vs internal

**Barrel Files:**
- Not used; each module imports what it needs directly
- Example: `from signal_engine import LONG, SHORT, FLAT, get_signal, compute_indicators` (not `from signal_engine import *`)

**Hex-boundary compliance:**
- Pure-math modules (`signal_engine.py`, `sizing_engine.py`, `system_params.py`) import ONLY stdlib
- I/O modules (`state_manager.py`) import `signal_engine`, `sizing_engine`, `system_params` but NOT web/notifier
- Web modules (`web/`) import stdlib + fastapi + starlette + state_manager (read-only) but NOT `signal_engine`, `data_fetcher`, `notifier`
- Boundary enforcement: test assertions in `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` use AST walking to detect violations

## Data Types & Precision

**Decimal for money:**
- `from decimal import Decimal, ROUND_HALF_UP` — EVERY AUD amount uses Decimal, never float
- Quantization: `AUD_QUANTIZE = Decimal('0.01')` (2 decimal places for cents)
- Rounding: `ROUND_HALF_UP` (not banker's rounding) — $2.005 rounds to $2.01
- Example: `pnl = Decimal('1234.567').quantize(AUD_QUANTIZE, rounding=ROUND_HALF_UP)`  → `Decimal('1234.57')`

**Float64 for math:**
- All indicator math (ATR, ADX, momentum, volatility) uses `np.float64` on pandas Series
- Explicit cast on return: `float(numpy_value)` unwraps numpy scalars so JSON serialization works
- NaN handling: `pd.isna()` for checks, `np.nan` for initialization, preserve `float('nan')` in output dicts

**Version strings:**
- Strategy version: semantic versioning with `'v'` prefix: `STRATEGY_VERSION = 'v1.2.0'`
- Schema version: integer (e.g., `'schema_version': 12` in state.json)
- Code bump on signal logic only (Mom periods, ADX gate, sizing weights); NOT on UI/infra/email changes

---

*Conventions analysis: 2026-05-15*
