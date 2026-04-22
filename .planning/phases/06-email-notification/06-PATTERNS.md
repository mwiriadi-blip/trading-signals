# Phase 6: Email Notification — Pattern Map

**Mapped:** 2026-04-22
**Files analyzed:** 13 (5 created + 8 modified = 13 logical files; fixtures listed
as 3 JSON + 3 HTML goldens but covered under one analog)
**Analogs found:** 13 / 13

All new/modified Phase 6 files have a close analog in the current codebase. Phase 5
(`dashboard.py` / `tests/test_dashboard.py` / `tests/regenerate_dashboard_golden.py`)
is the dominant pattern source — Phase 6 is structurally Phase 5 with a different
sink (Resend HTTPS POST instead of local HTML atomic write). `data_fetcher.py` is
the analog for the retry loop. `main.py:_render_dashboard_never_crash` is the verbatim
mirror for `_send_email_never_crash`.

---

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `notifier.py` (NEW) | I/O hex adapter | state dict → HTML string → HTTPS POST | `dashboard.py` | exact (same hex shape, same formatter set, same atomic-write fallback) |
| `notifier.py` retry loop (inside NEW) | I/O hex sub-pattern | HTTPS call → retry-on-transient → raise after N attempts | `data_fetcher.py:fetch_ohlcv` lines 70-132 | exact |
| `notifier.py _atomic_write_html` (inside NEW) | I/O durability sub-pattern | string → tempfile + fsync + replace | `state_manager._atomic_write` lines 88-133 AND `dashboard._atomic_write_html` lines 987-1031 | exact |
| `tests/test_notifier.py` (NEW) | test | fixture JSON → compose / send → assert | `tests/test_dashboard.py` (6-class skeleton) | exact |
| `tests/fixtures/notifier/sample_state_with_change.json` (NEW) | test fixture | mid-campaign state snapshot | `tests/fixtures/dashboard/sample_state.json` (via `_make_state` generator) | exact |
| `tests/fixtures/notifier/sample_state_no_change.json` (NEW) | test fixture | mid-campaign unchanged-signals state | `tests/fixtures/dashboard/sample_state.json` (variant) | exact |
| `tests/fixtures/notifier/empty_state.json` (NEW) | test fixture | `reset_state()` output | `tests/fixtures/dashboard/empty_state.json` | exact |
| `tests/fixtures/notifier/golden_with_change.html` (NEW) | test golden | byte-equal snapshot | `tests/fixtures/dashboard/golden.html` | exact |
| `tests/fixtures/notifier/golden_no_change.html` (NEW) | test golden | byte-equal snapshot | `tests/fixtures/dashboard/golden.html` (variant) | exact |
| `tests/fixtures/notifier/golden_empty.html` (NEW) | test golden | byte-equal snapshot | `tests/fixtures/dashboard/golden_empty.html` | exact |
| `tests/regenerate_notifier_golden.py` (NEW) | operator-only regen script | fixture JSON → `compose_email_body` → write HTML | `tests/regenerate_dashboard_golden.py` | exact |
| `.env.example` (NEW) | config sample | documentation of env vars | no analog (first env-var-reading path) | no-analog (RESEARCH.md §3 prescribes shape) |
| `system_params.py` (MODIFIED — palette retrofit) | shared constants | module-level `_COLOR_*` definitions added | existing `system_params.py` constants style (lines 23-77) | exact (append to existing file; same style) |
| `dashboard.py` (MODIFIED — palette import) | I/O hex | import palette from `system_params` instead of defining locally | existing `dashboard.py` imports from `system_params` (lines 82-90) | exact (widen existing import) |
| `main.py` (MODIFIED — `_send_email_never_crash` + dispatch + tuple return) | orchestrator | state + old_signals + run_date → notifier call | `main.py:_render_dashboard_never_crash` lines 94-112 | exact (verbatim mirror per RESEARCH Q8) |
| `tests/test_signal_engine.py` (MODIFIED — AST blocklist extend) | AST-guard test | file path → ast.walk imports → set ∩ blocklist | existing `FORBIDDEN_MODULES_DASHBOARD` + `test_dashboard_no_forbidden_imports` (lines 552-559 + 836-858) | exact |
| `tests/test_main.py` (MODIFIED — TestCLI for --force-email + --test email, TestEmailNeverCrash) | orchestrator test | monkeypatch + main(['--force-email']) → assert email dispatched | existing `test_force_email_logs_stub_and_exits_zero` (lines 230-248) + `test_dashboard_failure_never_crashes_run` (lines 670-712) | exact |
| `tests/test_dashboard.py` (MODIFIED — must stay green post-palette retrofit) | regression test | no change (only re-imports palette from new location) | itself | self |
| `.gitignore` (MODIFIED — add `last_email.html`) | config | single-line append | existing `.gitignore` contains `dashboard.html` | exact |

---

## Pattern Assignments

### `notifier.py` — I/O hex adapter (NEW)

**Analog:** `dashboard.py` (for hex structure, inline-CSS style, formatters, atomic
write, golden snapshot pattern) + `data_fetcher.py:fetch_ohlcv` (for retry loop).

**Hex-module docstring pattern — copy from `dashboard.py` lines 1-66:**

```python
r'''Notifier — self-contained single-file HTML email I/O hex.

Owns Resend HTTPS dispatch for the daily signal email and exposes three
public functions:
  compose_email_subject, compose_email_body, send_daily_email.

NOTF-01..09 (REQUIREMENTS.md §Notifier). Reads state.json (caller-supplied
state dict) and posts an inline-CSS HTML body to Resend via the
requests library. Missing RESEND_API_KEY degrades to writing
last_email.html (NOTF-08, D-13).

Public surface (D-01):
  compose_email_subject(state, old_signals, is_test=False) -> str
  compose_email_body(state, old_signals, now) -> str
  send_daily_email(state, old_signals, now, is_test=False) -> int

Architecture (hexagonal-lite, CLAUDE.md): I/O hex. Peer of state_manager,
data_fetcher, dashboard. Must NOT import signal_engine, sizing_engine,
data_fetcher, notifier-self-cycles, main, dashboard, numpy, pandas,
yfinance. AST blocklist in tests/test_signal_engine.py::TestDeterminism
enforces this structurally via FORBIDDEN_MODULES_NOTIFIER.

Allowed imports (D-01 allowlist): stdlib (html, json, logging, os, time,
tempfile, datetime, pathlib) + pytz + requests (Resend HTTPS) +
state_manager (for load_state in convenience CLI path only) +
system_params (palette constants, contract specs, INITIAL_ACCOUNT).

XSS posture: every dynamic value flows through html.escape() at the leaf
render site (C-5 per-surface escape, Phase 5 D-15 precedent). Inline
style="..." on every coloured span (no CSS classes — email clients strip
<style> inconsistently).

Never-crash posture (D-13): send_daily_email catches every Exception from
_post_to_resend, logs at WARNING with [Email] prefix, returns 0. Missing
RESEND_API_KEY writes last_email.html instead.

Clock injection (D-01): compose_email_body(state, old_signals, now)
requires a timezone-aware datetime. Tests pass
PERTH.localize(datetime(2026, 4, 22, 9, 0)) for byte-identical golden
snapshots. C-1 reviews: never construct via datetime(..., tzinfo=PERTH) —
use .localize().
'''
```

**Imports pattern — extend from `dashboard.py` lines 67-90:**

```python
import html
import json
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytz
import requests  # NEW vs dashboard — Resend HTTPS; inside FORBIDDEN_MODULES_DASHBOARD, ALLOWED for notifier

from state_manager import load_state  # CLI convenience path only
from system_params import (
  AUDUSD_COST_AUD,
  AUDUSD_NOTIONAL,
  INITIAL_ACCOUNT,
  SPI_COST_AUD,
  SPI_MULT,
  TRAIL_MULT_LONG,
  TRAIL_MULT_SHORT,
  # Wave 0 retrofit (D-02): palette now lives in system_params, shared with dashboard
  _COLOR_BG,
  _COLOR_BORDER,
  _COLOR_FLAT,
  _COLOR_LONG,
  _COLOR_SHORT,
  _COLOR_SURFACE,
  _COLOR_TEXT,
  _COLOR_TEXT_DIM,
  _COLOR_TEXT_MUTED,
)
```

**Module-level constants pattern — mirror `dashboard.py` lines 96-136:**

```python
logger = logging.getLogger(__name__)

# Email sender / recipient (D-14)
_EMAIL_FROM = 'signals@carbonbookkeeping.com.au'  # verified Resend sender
_EMAIL_TO_FALLBACK = 'marc@carbonbookkeeping.com.au'  # operator confirmed

# Retry policy (D-12 — mirror data_fetcher.fetch_ohlcv)
_RESEND_TIMEOUT_S = 30
_RESEND_RETRIES = 3
_RESEND_BACKOFF_S = 10

# Display-name + contract-spec dicts — duplicated from dashboard per D-02 hex rule
_INSTRUMENT_DISPLAY_NAMES_EMAIL = {
  'SPI200': 'SPI 200',
  'AUDUSD': 'AUD / USD',
}
_CONTRACT_SPECS_EMAIL = {
  'SPI200': (SPI_MULT, SPI_COST_AUD),
  'AUDUSD': (AUDUSD_NOTIONAL, AUDUSD_COST_AUD),
}
```

**Formatter pattern — duplicate + rename with `_email` suffix from `dashboard.py`
lines 371-437:**

```python
# dashboard.py:371-383 (analog)
def _fmt_em_dash_email() -> str:
  return '—'

def _fmt_currency_email(value: float) -> str:
  if value < 0:
    return f'-${-value:,.2f}'
  return f'${value:,.2f}'

def _fmt_percent_signed_email(fraction: float) -> str:
  return f'{fraction * 100:+.1f}%'

def _fmt_percent_unsigned_email(fraction: float) -> str:
  return f'{fraction * 100:.1f}%'

def _fmt_last_updated_email(now: datetime) -> str:
  # VERBATIM copy from dashboard._fmt_last_updated — including naive rejection
  if now.tzinfo is None:
    raise ValueError(
      '_fmt_last_updated_email requires a timezone-aware datetime; '
      f'got naive datetime={now!r}'
    )
  awst = now.astimezone(pytz.timezone('Australia/Perth'))
  return awst.strftime('%Y-%m-%d %H:%M AWST')
```

**DEVIATION from dashboard `_fmt_pnl_with_colour`:** email version must emit `style="..."`
inline, never rely on CSS classes. Reference `dashboard.py:399-421`:

```python
# dashboard.py:399-421 (analog — email variant is structurally identical but already inline)
def _fmt_pnl_with_colour_email(value: float) -> str:
  if value > 0:
    colour = _COLOR_LONG
    body = f'+{_fmt_currency_email(value)}'
  elif value < 0:
    colour = _COLOR_SHORT
    body = _fmt_currency_email(value)
  else:
    colour = _COLOR_TEXT_MUTED
    body = '$0.00'
  # Email clients require inline style="..." — no CSS classes
  return (
    f'<span style="color:{html.escape(colour, quote=True)}">'
    f'{html.escape(body, quote=True)}</span>'
  )
```

**Inline display-math helpers pattern (re-implementation of sizing_engine per hex
fence) — duplicate from `dashboard.py` lines 512-546:**

Deviation: reuse semantics verbatim; rename `_compute_*_display` → `_compute_*_email`
if disambiguation is desired. Otherwise reuse names — they live in separate
modules so no collision.

**`_post_to_resend` retry loop — extend `data_fetcher.py:fetch_ohlcv` lines 70-132
pattern:**

```python
# data_fetcher.py:40-44 (analog — retry-eligible exception tuple)
_RESEND_RETRY_EXCEPTIONS = (
  requests.exceptions.Timeout,
  requests.exceptions.ConnectionError,
  requests.exceptions.HTTPError,  # 5xx + 429 after our special-case below
)

# data_fetcher.py:70-132 (analog — for-loop retry with flat backoff)
class ResendError(Exception):
  '''Raised when Resend POST fails after retries exhaust or returns non-retryable 4xx.'''

def _post_to_resend(
  api_key: str,
  from_addr: str,
  to_addr: str,
  subject: str,
  html_body: str,
  timeout_s: int = _RESEND_TIMEOUT_S,
  retries: int = _RESEND_RETRIES,
  backoff_s: int = _RESEND_BACKOFF_S,
) -> None:
  '''POST to Resend with retry-on-transient. Mirrors data_fetcher.fetch_ohlcv
  retry policy (D-12). 4xx except 429 fails fast; 429 + 5xx + network errors
  retry up to `retries` times with flat `backoff_s` sleep (RESEARCH §1 — 429
  IS retryable per Resend guidance, contradicting CONTEXT D-12's literal 4xx
  fail-fast; researcher-recommended special-case).
  '''
  payload = {'from': from_addr, 'to': [to_addr], 'subject': subject, 'html': html_body}
  headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
  last_err: Exception | None = None
  for attempt in range(1, retries + 1):
    try:
      resp = requests.post(
        'https://api.resend.com/emails',
        headers=headers, json=payload, timeout=timeout_s,
      )
      # RESEARCH §1: 429 IS retryable — special-case before the 4xx fail-fast band
      if resp.status_code == 429:
        raise requests.exceptions.HTTPError('429 rate-limit', response=resp)
      if 400 <= resp.status_code < 500:
        raise ResendError(
          f'4xx from Resend: {resp.status_code} {resp.text[:200]}'
        )
      resp.raise_for_status()  # 5xx → HTTPError → caught below and retried
      return
    except _RESEND_RETRY_EXCEPTIONS as e:
      last_err = e
      logger.warning(
        '[Email] Resend attempt %d/%d failed: %s: %s',
        attempt, retries, type(e).__name__, e,
      )
      if attempt < retries:
        time.sleep(backoff_s)
  raise ResendError(
    f'retries exhausted after {retries} attempts; '
    f'last error: {type(last_err).__name__}: {last_err}',
  ) from last_err
```

**`send_daily_email` never-crash + API-key-missing fallback pattern — mirror D-13
in CONTEXT + never-crash semantics of `main._render_dashboard_never_crash`:**

```python
def send_daily_email(
  state: dict,
  old_signals: dict,
  now: datetime,
  is_test: bool = False,
) -> int:
  '''Public dispatch. NEVER raises. Returns 0 on success OR graceful degradation.

  NOTF-07: Resend API failure logs error, does NOT crash.
  NOTF-08: Missing RESEND_API_KEY → write last_email.html + return 0.
  '''
  subject = compose_email_subject(state, old_signals, is_test=is_test)
  html_body = compose_email_body(state, old_signals, now)
  api_key = os.environ.get('RESEND_API_KEY')
  if not api_key:
    last_email_path = Path('last_email.html')
    _atomic_write_html(html_body, last_email_path)  # duplicate from dashboard._atomic_write_html
    logger.warning(
      '[Email] WARN RESEND_API_KEY missing — wrote %s (fallback)',
      last_email_path,
    )
    return 0
  to_addr = os.environ.get('SIGNALS_EMAIL_TO', _EMAIL_TO_FALLBACK)
  try:
    _post_to_resend(api_key, _EMAIL_FROM, to_addr, subject, html_body)
    logger.info('[Email] sent to %s subject=%r', to_addr, subject)
  except ResendError as e:
    logger.warning('[Email] WARN send failed: %s', e)
  except Exception as e:  # belt-and-braces — NEVER propagate
    logger.warning(
      '[Email] WARN unexpected failure: %s: %s', type(e).__name__, e,
    )
  return 0
```

**Atomic write helper — duplicate verbatim from `dashboard.py` lines 987-1031:**

Exact same body. The `newline='\n'` is load-bearing (golden byte-stability on
Windows). Encoding `utf-8`.

**Convenience `if __name__ == '__main__'` CLI entrypoint — mirror `dashboard.py`
lines 1072-1078:**

```python
if __name__ == '__main__':
  # Operator-only preview: python -m notifier
  state = load_state()
  old_signals = {k: None for k in ('^AXJO', 'AUDUSD=X')}  # no baseline in CLI
  perth = pytz.timezone('Australia/Perth')
  now = datetime.now(perth)
  rc = send_daily_email(state, old_signals, now, is_test=True)
  import sys
  sys.exit(rc)
```

---

### `tests/test_notifier.py` — 6-class test suite (NEW)

**Analog:** `tests/test_dashboard.py` lines 1-67 (module preamble), 73-162
(`_make_state` fixture helper), 169 / 376 / 478 / 890 / 912 / 931 (6-class structure).

**6-class structure pattern — mirror `test_dashboard.py` line 169/376/478/890/912/931:**

| test_dashboard.py class | test_notifier.py equivalent | Purpose |
|-------------------------|-----------------------------|---------|
| `TestStatsMath` (line 169) | (N/A — no stats in email beyond formatters) | |
| `TestFormatters` (line 376) | `TestFormatters` | unit tests for `_fmt_currency_email`, `_fmt_percent_*_email`, `_fmt_pnl_with_colour_email`, `_fmt_em_dash_email`, `_fmt_last_updated_email` |
| `TestRenderBlocks` (line 478) | `TestComposeSubject` + `TestComposeBody` | per-section substring asserts, ACTION REQUIRED conditional, palette presence, first-run subject emoji |
| `TestEmptyState` (line 890) | (folded into `TestComposeBody` empty-state case via `empty_state.json` fixture) | |
| `TestGoldenSnapshot` (line 912) | `TestComposeBody::test_golden_*_matches_committed` (3 cases) | byte-equal snapshot vs committed golden HTML |
| `TestAtomicWrite` (line 931) | `TestSendDispatch` + `TestResendPost` + `TestDispatchIntegration` | HTTPS monkeypatch, retry exhaustion, missing-key fallback, never-crash semantics |

**Module preamble — extend from `test_dashboard.py` lines 1-67:**

```python
'''Phase 6 test suite: notifier compose + dispatch + formatters + goldens + never-crash.

Organized into classes per D-13 (one class per concern dimension):
  TestComposeSubject      — D-04 subject template + emoji + TEST prefix + first-run
  TestComposeBody         — D-10 7-section body + ACTION REQUIRED + golden snapshot
  TestFormatters          — _fmt_*_email parity with dashboard formatters
  TestSendDispatch        — send_daily_email RESEND_API_KEY paths + never-crash
  TestResendPost          — _post_to_resend retry loop + 429 special-case + 4xx fail-fast
  TestDispatchIntegration — main.py --force-email + --test integration (dispatch wiring)

All tests use tmp_path for fixture isolation — never write to real last_email.html.
Clock determinism via FROZEN_NOW module constant (no freezer fixture needed —
compose_email_body accepts now= parameter, mirror of dashboard.py).

C-1 reviews (Phase 5 precedent): pytz timezones via PERTH.localize(...), NOT
datetime(..., tzinfo=pytz.timezone(...)).
'''
import html  # noqa: F401 — TestRenderBlocks escape assertions
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import pytz

import notifier
from notifier import (
  compose_email_body,
  compose_email_subject,
  send_daily_email,
)

NOTIFIER_PATH = Path('notifier.py')
TEST_NOTIFIER_PATH = Path('tests/test_notifier.py')
REGENERATE_SCRIPT_PATH = Path('tests/regenerate_notifier_golden.py')
NOTIFIER_FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'notifier'
SAMPLE_STATE_WITH_CHANGE_PATH = NOTIFIER_FIXTURE_DIR / 'sample_state_with_change.json'
SAMPLE_STATE_NO_CHANGE_PATH = NOTIFIER_FIXTURE_DIR / 'sample_state_no_change.json'
EMPTY_STATE_PATH = NOTIFIER_FIXTURE_DIR / 'empty_state.json'
GOLDEN_WITH_CHANGE_PATH = NOTIFIER_FIXTURE_DIR / 'golden_with_change.html'
GOLDEN_NO_CHANGE_PATH = NOTIFIER_FIXTURE_DIR / 'golden_no_change.html'
GOLDEN_EMPTY_PATH = NOTIFIER_FIXTURE_DIR / 'golden_empty.html'

PERTH = pytz.timezone('Australia/Perth')
FROZEN_NOW = PERTH.localize(datetime(2026, 4, 22, 9, 0))
```

**Golden snapshot test pattern — mirror `test_dashboard.py::TestGoldenSnapshot`
lines 917-928:**

```python
# test_dashboard.py:917-928 (analog)
class TestComposeBody:  # (partial — golden tests only)
  def test_golden_with_change_matches_committed(self) -> None:
    state = json.loads(SAMPLE_STATE_WITH_CHANGE_PATH.read_text())
    old_signals = {'^AXJO': 1, 'AUDUSD=X': -1}  # SPI200 LONG→SHORT transition
    rendered = compose_email_body(state, old_signals, FROZEN_NOW)
    golden = GOLDEN_WITH_CHANGE_PATH.read_text(encoding='utf-8')
    assert rendered == golden, (
      'compose_email_body drifted from golden_with_change.html. '
      'If change intentional: run '
      '`.venv/bin/python tests/regenerate_notifier_golden.py` and re-commit.'
    )
```

**Monkeypatch HTTPS pattern — mirror `test_dashboard.py::TestAtomicWrite` lines
936-971 (uses `patch('dashboard.os.replace', side_effect=OSError)`):**

```python
# test_dashboard.py:956 (analog — patch at the notifier.requests boundary)
class TestResendPost:
  def test_retry_on_500_then_success(self, monkeypatch) -> None:
    calls = []
    class _FakeResp:
      def __init__(self, code): self.status_code = code; self.text = 'ok'
      def raise_for_status(self):
        if self.status_code >= 500:
          raise __import__('requests').exceptions.HTTPError(f'{self.status_code}')
    def _fake_post(url, **kw):
      calls.append(1)
      return _FakeResp(500) if len(calls) < 2 else _FakeResp(200)
    monkeypatch.setattr('notifier.requests.post', _fake_post)
    # backoff_s=0 for fast test
    notifier._post_to_resend(
      'k', 'a@b.c', 'c@d.e', 'subj', '<html/>',
      timeout_s=1, retries=3, backoff_s=0,
    )
    assert len(calls) == 2

  def test_4xx_except_429_fails_fast(self, monkeypatch) -> None:
    # RESEARCH §1 special-case: 400/401/403/422 → ResendError immediately
    class _FakeResp:
      status_code = 400
      text = 'bad request'
    monkeypatch.setattr('notifier.requests.post', lambda *a, **kw: _FakeResp())
    with pytest.raises(notifier.ResendError, match='4xx'):
      notifier._post_to_resend(
        'k', 'a@b.c', 'c@d.e', 'subj', '<html/>',
        timeout_s=1, retries=3, backoff_s=0,
      )

  def test_429_IS_retried(self, monkeypatch) -> None:
    # RESEARCH §1: 429 contradicts D-12 literal 4xx fail-fast — treat as retryable
    ...
```

**Missing-API-key fallback pattern — mirror never-crash posture + `tmp_path`
chdir pattern from `test_main.py`:**

```python
class TestSendDispatch:
  def test_missing_api_key_writes_last_email_html(self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
    rc = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
    assert rc == 0
    assert (tmp_path / 'last_email.html').exists()
```

---

### `tests/regenerate_notifier_golden.py` (NEW)

**Analog:** `tests/regenerate_dashboard_golden.py` (entire 59-line file).

**Full mirror — lines 1-59 of the dashboard regenerator with these substitutions:**

| dashboard regenerator | notifier regenerator |
|-----------------------|----------------------|
| `from dashboard import render_dashboard` | `from notifier import compose_email_body` |
| `FIXTURES_DIR = ROOT / 'tests' / 'fixtures' / 'dashboard'` | `FIXTURES_DIR = ROOT / 'tests' / 'fixtures' / 'notifier'` |
| `SCENARIOS = [('sample_state.json', 'golden.html'), ('empty_state.json', 'golden_empty.html')]` | `SCENARIOS = [('sample_state_with_change.json', 'golden_with_change.html', {'^AXJO': 1, 'AUDUSD=X': -1}), ('sample_state_no_change.json', 'golden_no_change.html', {'^AXJO': 1, 'AUDUSD=X': 0}), ('empty_state.json', 'golden_empty.html', {'^AXJO': None, 'AUDUSD=X': None})]` |
| `render_dashboard(state, out_path=out_path, now=FROZEN_NOW)` | `html = compose_email_body(state, old_signals, FROZEN_NOW); out_path.write_text(html, encoding='utf-8', newline='\n')` |

RESEARCH.md §4 (lines 303-335) provides the full template verbatim.

---

### `system_params.py` — Palette retrofit (MODIFIED)

**Analog:** existing `system_params.py` lines 23-77 (existing constant-definition
style — `ATR_PERIOD: int = 14`, `SPI_MULT: float = 5.0`, etc.).

**Pattern to apply — append a new section header + 9 palette constants:**

```python
# Insert AFTER line 77 (INITIAL_ACCOUNT block), BEFORE the Position TypedDict at line 83

# =========================================================================
# Palette constants — Phase 5 + Phase 6 shared (D-02 retrofit)
# Originally defined in dashboard.py module-level; migrated here so notifier.py
# can import the same palette without cross-hex import (hex fence D-01).
# =========================================================================

_COLOR_BG: str = '#0f1117'
_COLOR_SURFACE: str = '#161a24'
_COLOR_BORDER: str = '#252a36'
_COLOR_TEXT: str = '#e5e7eb'
_COLOR_TEXT_MUTED: str = '#cbd5e1'
_COLOR_TEXT_DIM: str = '#64748b'
_COLOR_LONG: str = '#22c55e'
_COLOR_SHORT: str = '#ef4444'
_COLOR_FLAT: str = '#eab308'
```

**Deviation note:** underscore-prefixed names for module-private convention consistency
with dashboard.py. Even though they're imported elsewhere, the underscore advertises
"shared-implementation-detail" rather than "stable public API". This matches Python
norms and keeps the IDE "Organize Imports" sorted correctly.

---

### `dashboard.py` — Palette import retrofit (MODIFIED)

**Analog:** existing `dashboard.py` lines 82-90 (`from system_params import (...)`).

**Pattern — widen the existing import:**

```python
# dashboard.py:82-90 (current)
from system_params import (
  AUDUSD_COST_AUD,
  AUDUSD_NOTIONAL,
  INITIAL_ACCOUNT,
  SPI_COST_AUD,
  SPI_MULT,
  TRAIL_MULT_LONG,
  TRAIL_MULT_SHORT,
)

# Phase 6 Wave 0 retrofit (D-02):
from system_params import (
  AUDUSD_COST_AUD,
  AUDUSD_NOTIONAL,
  INITIAL_ACCOUNT,
  SPI_COST_AUD,
  SPI_MULT,
  TRAIL_MULT_LONG,
  TRAIL_MULT_SHORT,
  _COLOR_BG,
  _COLOR_BORDER,
  _COLOR_FLAT,
  _COLOR_LONG,
  _COLOR_SHORT,
  _COLOR_SURFACE,
  _COLOR_TEXT,
  _COLOR_TEXT_DIM,
  _COLOR_TEXT_MUTED,
)
```

**DELETE dashboard.py lines 103-111** (the 9 `_COLOR_*` module-level definitions).
The rest of dashboard.py already references them by the same identifiers, so no
downstream edit is required.

**Regression guard:** Phase 5's golden HTML `tests/fixtures/dashboard/golden.html`
must remain byte-identical after the retrofit. If it drifts, the retrofit changed
semantics (likely a typo in a hex value) and needs revision, NOT regenerator
re-run.

---

### `main.py` — Three edits (MODIFIED)

**Analog #1:** `main.py:94-112` (`_render_dashboard_never_crash` — exact mirror for
`_send_email_never_crash`).

**Pattern — verbatim mirror with s/Dashboard/Email/, s/dashboard/notifier/,
s/render_dashboard/send_daily_email/:**

```python
# main.py:94-112 (analog)
def _send_email_never_crash(
  state: dict,
  old_signals: dict,
  run_date: datetime,
  is_test: bool = False,
) -> None:
  '''D-15: email dispatch never crashes the run.

  C-2 reviews (Phase 5 precedent): `import notifier` lives INSIDE the helper
  body (not at module top) so import-time errors in notifier.py — syntax
  errors, bad sub-imports, circular-import bugs — are caught by the SAME
  `except Exception` that catches runtime dispatch failures. Without
  this, an import-time notifier error takes down main.py at module
  load time, before the helper even runs.

  The ONLY place in this codebase where `except Exception:` is correct —
  NOTF-07 + NOTF-08: email failures NEVER crash the workflow. State is
  already saved; dashboard was already rendered. Never abort the run on
  a send failure.
  '''
  try:
    import notifier  # local import — C-2 isolates import-time failures
    notifier.send_daily_email(state, old_signals, run_date, is_test=is_test)
  except Exception as e:
    logger.warning('[Email] send failed: %s: %s', type(e).__name__, e)
```

**Analog #2:** `main.py:723-729` (existing `--force-email` dispatch ladder) — REPLACE
the stub call `_force_email_stub()` with `_send_email_never_crash(...)`.

**Pattern — tuple-return refactor of `run_daily_check` per RESEARCH Q9 + CONTEXT
D-15:**

```python
# main.py:351-616 (current signature returns int)
def run_daily_check(args: argparse.Namespace) -> int:
    ...
    return 0

# Phase 6 refactor — return (rc, state, old_signals) tuple
def run_daily_check(
  args: argparse.Namespace,
) -> tuple[int, dict | None, dict | None]:
    ...
    # CAPTURE old_signals AFTER load_state, BEFORE the per-instrument loop
    # (per CONTEXT D-05 — old_signals captured BEFORE state mutation)
    old_signals = {
      yf_sym: (
        state['signals'].get(state_key, {}).get('signal')
        if isinstance(state['signals'].get(state_key), dict)
        else state['signals'].get(state_key)  # legacy int shape
      )
      for state_key, yf_sym in SYMBOL_MAP.items()
    }
    ...
    return 0, state, old_signals
```

**Dispatch ladder update in `main()` — replace lines 720-730:**

```python
# main.py:720-730 (current)
try:
  if args.reset:
    return _handle_reset()
  if args.force_email:
    rc = run_daily_check(args) if args.test else 0
    stub_rc = _force_email_stub()
    return rc if rc != 0 else stub_rc
  return run_daily_check(args)

# Phase 6 replacement
try:
  if args.reset:
    return _handle_reset()
  if args.force_email or args.test:
    # Shared compute-then-email path (D-15)
    rc, state, old_signals = run_daily_check(args)
    if rc == 0 and state is not None and old_signals is not None:
      run_date = _compute_run_date()  # re-read or thread through from run_daily_check
      _send_email_never_crash(state, old_signals, run_date, is_test=args.test)
    return rc
  rc, _state, _old_signals = run_daily_check(args)
  return rc
```

**Deviation:** `--test` alone no longer auto-sends the email unless combined with
`--force-email`. Re-read CONTEXT D-15 — the Phase 6 wiring sends on the combined
path. `--test` alone keeps the existing (no-email) behaviour if that's the locked
semantic; otherwise both trigger email. **Planner must verify with CONTEXT D-15
lines 227-258 — the dispatch ladder shows `if args.force_email or args.test:`
which means `--test` alone DOES send a TEST-prefixed email in Phase 6.** If that
interpretation holds, use `or` as shown above.

**Analog #3:** All existing callers of `run_daily_check(args)` — search and update
for the tuple return. RESEARCH §Summary line 14 confirms `tests/test_main.py`
callers all go through `main.main(...)` not direct `run_daily_check`, so the
cascade is contained to main.py + any tests that unwrap the return value.

---

### `tests/test_signal_engine.py` — AST blocklist extension (MODIFIED)

**Analog:** existing `FORBIDDEN_MODULES_DASHBOARD` (lines 552-559) +
`test_dashboard_no_forbidden_imports` (lines 836-858).

**Pattern — append a new `FORBIDDEN_MODULES_NOTIFIER` set and one parametrized
test method. After line 559 add:**

```python
# test_signal_engine.py:552-559 (analog)
# Phase 6 Wave 0: notifier.py IS the email I/O hex — stdlib (html, json,
# logging, os, time, tempfile, datetime, pathlib) + pytz + requests (Resend
# HTTPS) + state_manager (load_state convenience path) + system_params
# (palette + contract specs) ARE allowed. Must NOT import sibling hexes
# (signal_engine, sizing_engine, data_fetcher, dashboard, main) or heavy
# scientific stack (numpy, pandas) or fetch libs (yfinance).
FORBIDDEN_MODULES_NOTIFIER = frozenset({
  'signal_engine', 'sizing_engine', 'data_fetcher', 'dashboard', 'main',
  'numpy', 'pandas',
  'yfinance',
})
NOTIFIER_PATH = Path('notifier.py')
TEST_NOTIFIER_PATH = Path('tests/test_notifier.py')
REGENERATE_NOTIFIER_GOLDEN_PATH = Path('tests/regenerate_notifier_golden.py')
```

**And append a parametrized test method mirror of `test_dashboard_no_forbidden_imports`
(lines 836-858):**

```python
@pytest.mark.parametrize('module_path', [NOTIFIER_PATH])
def test_notifier_no_forbidden_imports(self, module_path: Path) -> None:
  '''Phase 6 Wave 0: notifier.py must not import sibling hexes, numpy,
  pandas, yfinance. It IS allowed to import stdlib + pytz + requests +
  state_manager (load_state) + system_params.
  '''
  imports = _top_level_imports(module_path)
  leaked = imports & FORBIDDEN_MODULES_NOTIFIER
  assert not leaked, (
    f'{module_path} illegally imports forbidden module(s): {sorted(leaked)}. '
    f'notifier.py must not import sibling hexes (signal_engine, sizing_engine, '
    f'data_fetcher, dashboard, main), numpy, pandas, or yfinance. '
    f'Allowed: stdlib + pytz + requests + state_manager + system_params.'
  )
```

**Also extend the sibling blocklists to forbid `notifier` (symmetric hex-boundary):**

- `FORBIDDEN_MODULES` (line 484) — already contains `'notifier'` (line 490)
- `FORBIDDEN_MODULES_STATE_MANAGER` (line 503) — already contains `'notifier'` (line 505)
- `FORBIDDEN_MODULES_DATA_FETCHER` (line 521) — already contains `'notifier'` (line 523)
- `FORBIDDEN_MODULES_DASHBOARD` (line 552) — already contains `'notifier'` (line 554)

No changes needed to the sibling sets — they already forbid notifier. Only NEW
addition is `FORBIDDEN_MODULES_NOTIFIER` + `test_notifier_no_forbidden_imports`.

---

### `tests/test_main.py` — New TestCLI + TestEmailNeverCrash cases (MODIFIED)

**Analog #1:** `test_force_email_logs_stub_and_exits_zero` (lines 230-248).

**Pattern — REPLACE that single-line stub assertion with real Resend monkeypatch
+ email-sent assertion:**

```python
# test_main.py:230-248 (current stub analog)
def test_force_email_sends_live_email(
    self, tmp_path, monkeypatch, caplog) -> None:
  '''CLI-03 Phase 6: --force-email now invokes notifier.send_daily_email.'''
  caplog.set_level(logging.INFO)
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
  _seed_fresh_state(tmp_path / 'state.json')
  _install_fixture_fetch(monkeypatch)

  sent = []
  def _fake_send(state, old_signals, now, is_test=False):
    sent.append((state, old_signals, now, is_test))
    return 0
  import notifier
  monkeypatch.setattr(notifier, 'send_daily_email', _fake_send)

  rc = main.main(['--force-email'])
  assert rc == 0
  assert len(sent) == 1, '--force-email must invoke notifier.send_daily_email exactly once'
  _state, _old_signals, _now, is_test = sent[0]
  assert is_test is False, '--force-email alone is NOT --test'
```

**Analog #2:** `test_test_flag_leaves_state_json_mtime_unchanged` (lines 154-175) — extend
to cover the --test + email combo per CONTEXT D-15 CLI-01 preservation:

```python
def test_test_flag_with_email_leaves_state_json_mtime_unchanged(
    self, tmp_path, monkeypatch) -> None:
  '''CLI-01 + Phase 6: --test sends [TEST]-prefixed email AND state.json unchanged.'''
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
  state_json = tmp_path / 'state.json'
  _seed_fresh_state(state_json)
  mtime_before = state_json.stat().st_mtime_ns
  _install_fixture_fetch(monkeypatch)

  sent = []
  import notifier
  monkeypatch.setattr(notifier, 'send_daily_email',
    lambda s, os_, now, is_test=False: sent.append(is_test) or 0)

  rc = main.main(['--test'])
  mtime_after = state_json.stat().st_mtime_ns
  assert rc == 0
  assert mtime_before == mtime_after, 'CLI-01: --test must NOT mutate state.json'
  # Phase 6 D-15: --test path sends a [TEST]-prefixed email
  assert sent == [True], '--test must call send_daily_email with is_test=True'
```

**Analog #3:** `test_dashboard_failure_never_crashes_run` (lines 670-712) — mirror
for `TestEmailNeverCrash::test_email_failure_never_crashes_run` (D-15 boundary):

```python
# test_main.py:670-712 (analog)
class TestEmailNeverCrash:
  '''D-15 + NOTF-07 + NOTF-08: email dispatch failures must NEVER crash the run.
  Mirror of TestOrchestrator dashboard never-crash tests.
  '''

  def test_email_failure_never_crashes_run(
      self, tmp_path, monkeypatch, caplog) -> None:
    caplog.set_level(logging.WARNING)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    import notifier as _notifier_module_for_patch
    def _raise(*args, **kw):
      raise RuntimeError('simulated Resend failure')
    monkeypatch.setattr(_notifier_module_for_patch, 'send_daily_email', _raise)

    rc = main.main(['--force-email'])
    assert rc == 0, 'D-15: email failure must NOT change exit code'
    assert '[Email] send failed' in caplog.text
    assert 'RuntimeError' in caplog.text

  def test_email_import_time_failure_never_crashes_run(
      self, tmp_path, monkeypatch, caplog) -> None:
    # Mirror of test_dashboard_import_time_failure_never_crashes_run lines 714-766
    # ... (sys.modules['notifier'] = _BrokenNotifier(); assert rc == 0)
    ...
```

---

### `tests/test_dashboard.py` — Palette retrofit regression (MODIFIED)

**Analog:** itself (no functional change).

**Pattern:** no edits required. The test imports `dashboard` and references the
module's symbols through `dashboard._COLOR_*` — those symbols are no longer module-
level but re-exported via the `from system_params import ...` statement, which
attaches them as module attributes. All existing assertions continue to pass.

**Wave 0 verification step:** run `pytest tests/test_dashboard.py` post-retrofit
and confirm `TestGoldenSnapshot::test_golden_snapshot_matches_committed` is still
green. If byte drift: check `system_params._COLOR_*` hex values vs the previously-
inline dashboard values. Zero hex-value change expected.

---

### `.env.example` (NEW)

**Analog:** no analog — this is the first env-var-reading path in the project.

**Pattern — minimum content per RESEARCH §3 (lines 225-236):**

```
# .env.example
# Phase 6 reads RESEND_API_KEY from the process environment.
# Phase 7 will call load_dotenv() at startup to auto-load this file.
# For now, export manually before running:
#   export RESEND_API_KEY=re_xxx
#   export SIGNALS_EMAIL_TO=marc@example.com

RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SIGNALS_EMAIL_TO=marc@example.com
```

**Deviation note:** `.env.example` is committed; `.env` is NOT (already in
`.gitignore` at line 3). Planner should NOT add `.env.example` to `.gitignore`.

---

### `.gitignore` (MODIFIED)

**Analog:** existing `.gitignore` lines 1-7 (`state.json`, `dashboard.html`, `.env`, etc.).

**Pattern — append one line after `dashboard.html`:**

```
state.json
dashboard.html
last_email.html       # <-- NEW (D-13 RESEND_API_KEY-missing fallback artifact)
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
```

---

## Shared Patterns (cross-cutting)

### Never-crash helper pattern (local import + bare except)

**Source:** `main.py:94-112` (`_render_dashboard_never_crash`).

**Apply to:** `_send_email_never_crash` in main.py (D-15).

```python
def _X_never_crash(...) -> None:
  try:
    import X  # local import — isolates import-time failures
    X.do_thing(...)
  except Exception as e:
    logger.warning('[Prefix] ... failed: %s: %s', type(e).__name__, e)
```

### Atomic write (tempfile + fsync + os.replace + dir-fsync)

**Source:** `state_manager._atomic_write` lines 88-133 AND `dashboard._atomic_write_html`
lines 987-1031 (the latter is itself a verbatim mirror of the former per
`dashboard.py:983-986` comment).

**Apply to:** `notifier._atomic_write_html` (D-13 NOTF-08 fallback). Per CONTEXT
D-13 + RESEARCH recommendation: duplicate in notifier.py (zero coupling, ~25 lines).

The `newline='\n'` parameter on `tempfile.NamedTemporaryFile` is load-bearing for
golden byte-stability on Windows — DO NOT omit.

### Retry loop with narrow-catch tuple + flat backoff

**Source:** `data_fetcher.fetch_ohlcv` lines 70-132 (`_RETRY_EXCEPTIONS` tuple +
`for attempt in range(1, retries + 1)` loop + last-error tracking + final raise
`from last_err`).

**Apply to:** `notifier._post_to_resend` (D-12). Key deviations:
- Exception tuple: `(Timeout, ConnectionError, HTTPError)` instead of
  `(YFRateLimitError, ReadTimeout, ConnectionError)`.
- Special-case 429 BEFORE the 4xx fail-fast band per RESEARCH §1.
- `backoff_s` defaults to 10 (same); `timeout_s` defaults to 30.

### Golden-HTML byte-stable snapshot

**Source:** `tests/test_dashboard.py::TestGoldenSnapshot` lines 912-928 +
`tests/regenerate_dashboard_golden.py` lines 1-59.

**Apply to:** `tests/test_notifier.py::TestComposeBody::test_golden_*_matches_committed`
+ `tests/regenerate_notifier_golden.py`.

Byte-stability requires:
- `now=FROZEN_NOW` parameter (never `datetime.now()`).
- `PERTH.localize(datetime(...))` ONLY (never `datetime(..., tzinfo=PERTH)`).
- Write with `encoding='utf-8', newline='\n'`.
- No JSON output in body → no `sort_keys` concern. (Email has no embedded JSON.)

### Hex-boundary AST blocklist

**Source:** `tests/test_signal_engine.py::TestDeterminism::test_dashboard_no_forbidden_imports`
(lines 836-858) + `FORBIDDEN_MODULES_DASHBOARD` (lines 552-559).

**Apply to:** `test_notifier_no_forbidden_imports` + `FORBIDDEN_MODULES_NOTIFIER`.

Pattern: one parametrized test per hex file, reading the file, parsing AST, set
intersection with the blocklist, asserting empty.

### html.escape leaf-site discipline (XSS posture)

**Source:** `dashboard.py` throughout — every state-derived string at leaf
interpolation passes through `html.escape(value, quote=True)`. Example lines
583-584, 633, 679-697, 756-767.

**Apply to:** every `notifier.py` interpolation site that reads state. Inline
`style="..."` attributes wrap the `html.escape`'d colour value; the body of each
span also passes through `html.escape`. Email has no `<script>` context so no
`</script>` injection defence needed (unlike dashboard's Chart.js payload).

### PERTH.localize(datetime(...)) discipline (C-1 reviews)

**Source:** CLAUDE.md "Operator Decisions" + Phase 5 C-1 reviews-revision +
`dashboard._fmt_last_updated` lines 424-437 (raises `ValueError` on naive input).

**Apply to:** `notifier._fmt_last_updated_email` + `FROZEN_NOW` in tests +
`FROZEN_NOW` in regenerator script. Never write `datetime(..., tzinfo=PERTH)` —
Perth's pytz representation carries a historical LMT offset (+07:43:24 pre-1895)
when used as tzinfo without .localize(). Phase 5 caught this in review and the
pattern is locked.

### `monkeypatch.setattr('module.logging.basicConfig', lambda **kw: None)`

**Source:** `tests/test_main.py:112` + every caplog-asserting test in that file
(C-4 revision pattern). Without this no-op, `main.main()`'s
`logging.basicConfig(force=True)` tears down pytest's caplog handler.

**Apply to:** every `test_notifier.py::TestDispatchIntegration` method that
invokes `main.main(...)` and asserts on `caplog.text`.

---

## No Analog Found

No files in this phase fall into the "no analog" bucket. Phase 6 is a close
cousin of Phase 5 — every piece has precedent.

One edge case worth calling out (not a missing analog, but a resolvable question):

| File | Role | Data Flow | Note |
|------|------|-----------|------|
| `.env.example` | config | documentation | First env-var-reading path in the project. Shape prescribed by RESEARCH §3 lines 225-236. No analog needed; content is trivial. |

---

## Final Summary Table — File → Analog → Key Pattern

| Phase 6 file | Closest analog | Key pattern to copy |
|--------------|----------------|---------------------|
| `notifier.py` (hex structure, imports, module docstring) | `dashboard.py:1-136` | Hex-lite docstring, import block (add `requests`, palette from `system_params`), module-level constants block |
| `notifier.py` (7 formatters) | `dashboard.py:371-437` | `_fmt_*` bodies verbatim with `_email` suffix; inline `style="..."` on `_fmt_pnl_with_colour_email` |
| `notifier.py` (inline display-math) | `dashboard.py:512-546` | `_compute_trail_stop_display` + `_compute_unrealised_pnl_display` duplicated |
| `notifier.py::_post_to_resend` | `data_fetcher.py:70-132` | `for attempt in range(1, retries+1)` retry + narrow-catch tuple + `raise … from last_err`; 429 special-case per RESEARCH §1 |
| `notifier.py::_atomic_write_html` | `dashboard.py:987-1031` | verbatim duplicate; `newline='\n'`, `encoding='utf-8'`, fsync + os.replace + parent-dir fsync |
| `notifier.py::send_daily_email` | CONTEXT D-13 recipe + `main._render_dashboard_never_crash` posture | Missing `RESEND_API_KEY` → `_atomic_write_html('last_email.html')` + WARN + return 0; exception-swallow outer try |
| `notifier.py` CLI entrypoint | `dashboard.py:1072-1078` | `python -m notifier` preview via `state_manager.load_state()` |
| `tests/test_notifier.py` (6-class skeleton) | `tests/test_dashboard.py:169,376,478,890,912,931` | class-per-concern, module preamble with `FROZEN_NOW`, `_make_state`-style helper |
| `tests/test_notifier.py::TestComposeBody` (goldens) | `tests/test_dashboard.py:912-928` | byte-equal vs committed `.html`; error message points at regenerator |
| `tests/test_notifier.py::TestResendPost` | `tests/test_dashboard.py::TestAtomicWrite:946-971` | `monkeypatch.setattr('notifier.requests.post', _fake)`; success + fail-fast + retry-exhausted + 429-retry cases |
| `tests/regenerate_notifier_golden.py` | `tests/regenerate_dashboard_golden.py` (entire file) | Full 59-line mirror; 3 scenarios; `FROZEN_NOW = PERTH.localize(...)` |
| `tests/fixtures/notifier/*.json` | `tests/fixtures/dashboard/sample_state.json` + `empty_state.json` | Same top-level state schema; operator picks change-vs-no-change variants |
| `system_params.py` (palette retrofit) | `system_params.py:23-77` existing constant-section style | Append new section header + 9 `_COLOR_*: str = '#...'` constants |
| `dashboard.py` (palette import widen) | `dashboard.py:82-90` existing import block | Widen `from system_params import (...)` to pull the 9 `_COLOR_*` names; DELETE lines 103-111 |
| `main.py::_send_email_never_crash` | `main.py:94-112` | Verbatim mirror with s/Dashboard/Email/g |
| `main.py::run_daily_check` (tuple return) | `main.py:351` current signature | Change `-> int` to `-> tuple[int, dict|None, dict|None]`; capture `old_signals` after `load_state` per CONTEXT D-05 |
| `main.py::main` dispatch ladder | `main.py:720-730` | Replace `_force_email_stub` branch with `_send_email_never_crash` invocation; collapse `--test` + `--force-email` into the shared compute-then-email path |
| `tests/test_signal_engine.py` (notifier AST guard) | `tests/test_signal_engine.py:552-559` + `:836-858` | Append `FORBIDDEN_MODULES_NOTIFIER` frozenset + `test_notifier_no_forbidden_imports` parametrized method |
| `tests/test_main.py` (email dispatch tests) | `tests/test_main.py:230-248, 670-712` | Replace stub log-line assertion with `monkeypatch.setattr(notifier, 'send_daily_email', _fake)`; mirror dashboard never-crash tests for `_send_email_never_crash` |
| `tests/test_dashboard.py` (no-op verification) | itself | Re-run post-retrofit; `TestGoldenSnapshot` byte-identical |
| `.env.example` | RESEARCH §3 lines 225-236 | Plain-text `RESEND_API_KEY=` + `SIGNALS_EMAIL_TO=` + header comment |
| `.gitignore` | existing lines 1-7 | Append `last_email.html` after `dashboard.html` |

---

## Metadata

**Analog search scope:** repo root (`dashboard.py`, `data_fetcher.py`, `main.py`,
`state_manager.py`, `system_params.py`, `sizing_engine.py`, `signal_engine.py`) +
`tests/` (all `test_*.py` + regenerators + fixtures).

**Files scanned:** 8 production modules + 7 test modules + 2 regenerator scripts +
5 fixture directories. All Phase 6 files have analogs at the role AND data-flow
level.

**Pattern extraction date:** 2026-04-22

**Ready for planning.** Planner can now reference these pattern excerpts verbatim
when writing the Wave 0 / Wave 1 / Wave 2 action lists.
