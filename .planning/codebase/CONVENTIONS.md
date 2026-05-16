# Coding Conventions

**Analysis Date:** 2026-05-16

## Naming Patterns

**Files:**
- Module names: lowercase with underscores: `signal_engine.py`, `data_fetcher.py`, `state_manager.py`
- Test files: `test_<module>.py`: `test_signal_engine.py`, `test_sizing_engine.py`
- UAT test files: `test_uat_<phase>_<scenario>.py`: `test_uat_17_cookie_persistence.py`
- Test classes: `Test<Concern>`: `TestDeterminism`, `TestRiskCalculation`, `TestSizing`
- Test functions: `test_<behavior>`: `test_risk_pct_long_is_1pct`, `test_get_signal_long_only_blocks_short_votes`

**Functions:**
- Private helpers: `_leading_underscore`: `_wilder_smooth`, `_true_range`, `_validate_loaded_state`
- Public functions: `snake_case`: `compute_indicators`, `get_signal`, `mutate_state`
- Internal web handlers: `_<verb>_<noun>`: `_try_cookie`, `_try_basic`
- Test stubs: `_stub_` or `_fake_` prefix: `_stub_load_state`, `_fake_post`

**Variables:**
- Module-level constants: `UPPERCASE`: `LONG`, `SHORT`, `FLAT`, `ADX_GATE`, `ATR_PERIOD`
- Private constants: `_LEADING_UNDERSCORE`: `_MIN_SECRET_LEN`, `_EMAIL_RE`
- Local variables: `snake_case`: `prev_close`, `stop_dist`, `vol_scale`

**Types:**
- TypedDict classes: `PascalCase`: `SizingDecision`, `PyramidDecision`, `Position`
- Signal constants stay in `signal_engine.py`: `LONG = 1`, `SHORT = -1`, `FLAT = 0`
- All other constants in `system_params.py` — never inline in engine modules

## Code Style

**Formatting:**
- Tool: `ruff` (pyproject.toml `[tool.ruff]`)
- **2-space indent** — MANDATORY. Never run `ruff format` (reflows to 4-space; breaks test gate)
- Line length: 100 characters max
- Quote style: single quotes
- Line ending: LF only
- Target: Python 3.13

**Linting:**
- Ruff rules: `E`, `F`, `W`, `I`, `B`, `UP`
- `noqa` suppressions must annotate reason: `# noqa: F401 — kept for hex audit symmetry`
- No bare `noqa` without explanation

**Numeric types:**
- `Decimal` for ALL AUD money: `from decimal import Decimal, ROUND_HALF_UP`
- Coerce inputs at boundary: `Decimal(str(x))` — avoids float-binary noise
- Float for all indicator math (numpy/pandas); Decimal only at money-math output layer (`pnl_engine.py`)

## Import Organization

**Order (ruff isort enforced):**
1. stdlib: `import os`, `from decimal import Decimal`, `from datetime import datetime`
2. third-party: `import numpy as np`, `import pandas as pd`, `from fastapi import FastAPI`
3. first-party (blank line separator): `import signal_engine`, `from state_manager import mutate_state`

**Rules:**
- `known-first-party = ['signal_engine']` in `pyproject.toml`
- No wildcard imports
- Module names not aliased except conventions: `import pandas as pd`, `import numpy as np`, `import yfinance as yf`
- Deferred imports inside functions only for test isolation (e.g., `sys.modules.pop` before `create_app`)

**Example:**
```python
import json
import os
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pandas as pd

from system_params import ADX_GATE, ATR_PERIOD
import state_manager
```

## Module Docstrings

Every module has a triple-quoted module docstring at line 1:
- Purpose and public API summary
- Architecture layer (hexagonal-lite position)
- Key design decisions referenced by phase (R-01, D-01, etc.)
- What the module must NOT import (hex purity enforcement)

```python
'''Signal Engine — pure-math indicator library + 2-of-3 momentum vote.

Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY. No I/O, no network,
no clock reads, no imports of state_manager / notifier / dashboard.
'''
```

## Error Handling

**Custom exceptions:**
- `class DataFetchError(Exception)` in `data_fetcher.py` — wraps yfinance/network errors
- `class ResendError(Exception)` in `notifier/` — Resend HTTP failures
- `class ShortFrameError(Exception)` in `data_fetcher.py` — insufficient OHLCV bars

**Built-in exceptions:**
- `ValueError` for invalid inputs and schema violations
- `RuntimeError` for unrecoverable startup failures (missing env vars)
- `HTTPException(status_code=...)` in web routes for client errors (403, 404, 409)

**Messages:**
- Descriptive and actionable; include context: `f'invalid backtest filename: {filename!r}'`
- Use `!r` for repr of values
- Secrets redacted via `system_params.redact_secret()` before any log output

**Clock injection:**
- Functions with time-dependency accept `now=None` defaulting to `datetime.now(timezone.utc)`
- Allows deterministic testing without patching datetime

## Logging

**Framework:** stdlib `logging`

**Pattern:**
```python
logger = logging.getLogger(__name__)  # module-level, each module
```

**Levels:**
- `INFO`: major orchestration steps; prefixed `[Daily]`, `[Alert]`, `[Web]`, `[Sched]`
- `WARNING`: recoverable issues: `'size=0: undersized position'`
- `EXCEPTION`: caught errors with context

**Secret redaction:**
- All secrets through `system_params.redact_secret()` before logging
- Returns 6-char prefix + `'...'` or `'[empty]'` / `'[short]'`

**Hex constraint:**
- Pure-math hex modules do NOT log; only orchestration/I/O modules log

## Comments

**When to comment:**
- Docstrings required for public functions and classes
- Inline comments for non-obvious logic, edge cases, oracle references
- Phase/decision tags: `# D-07`, `# R-01`, `# Phase 14 D-13 amendment`
- Section banners: `# =========================================================================`

**Function docstrings:**
```python
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
  '''Return NEW DataFrame = input + 8 indicator columns.

  Guarantees:
    - Input DataFrame is NOT mutated (D-07).
    - All added columns are float64 (Pitfall 5).
    - NaN for warmup bars per each indicator's period.
  '''
```

## Hexagonal Architecture Enforcement

**Pure-math hex** (`signal_engine.py`, `sizing_engine/`, `system_params.py`, `pnl_engine.py`, `alert_engine.py`, `backtest/`):
- stdlib-only; zero imports of `os`, `logging`, `requests`, `state_manager`, `notifier`, `dashboard`
- Verified by AST-walk tests (`test_deferred_yfinance_import.py`)

**State I/O** (`state_manager/`):
- Sole module allowed filesystem I/O
- Atomic writes via flock through `mutate_state()` only
- Never call `save_state()` inside a `mutate_state()` callback — flock deadlock

**Web** (`web/`):
- Imports fastapi + state_manager (read); does NOT import signal_engine, data_fetcher, notifier

## Git Conventions

- Branch naming: `claude/<slug>` for AI-driven branches
- Commit style: conventional commits — `fix(uat):`, `feat:`, `refactor:`
- No secrets in commits; `.env` in `.gitignore`

---

*Conventions analysis: 2026-05-16*
