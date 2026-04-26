# Phase 16: Hardening + UAT Completion — Pattern Map

**Mapped:** 2026-04-26
**Files analyzed:** 3 new/modified files
**Analogs found:** 3 / 3

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `tests/test_integration_f1.py` | test (integration) | request-response (full-chain) | `tests/test_main.py::TestDriftWarningLifecycle` | exact |
| `.planning/phases/16-hardening-uat-completion/16-HUMAN-UAT.md` | documentation (UAT artifact) | n/a | `.planning/milestones/v1.0-phases/06-email-notification/06-HUMAN-UAT.md` | exact |
| `.planning/STATE.md` (edit) | documentation (state tracking) | n/a | `.planning/STATE.md §Deferred Items` (lines 211-222) | exact |

---

## Pattern Assignments

### `tests/test_integration_f1.py` (test, full-chain integration)

**Primary analog:** `tests/test_main.py::TestDriftWarningLifecycle` (lines 2647-2903)
**Secondary analog:** `tests/test_data_fetcher.py` (lines 1-276) — yfinance mock idiom
**Tertiary analog:** `tests/test_notifier.py` (lines 88-101, 1159-1175) — `_post_to_resend` stub + autouse `SIGNALS_EMAIL_FROM`

---

#### Imports pattern

**Source:** `tests/test_main.py` lines 1-51 combined with `tests/test_notifier.py` lines 23-50.

F1 needs this import block (2-space indent, single quotes per CLAUDE.md):

```python
import argparse
import json
import re
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

import data_fetcher
import main
import notifier
import signal_engine
import state_manager
```

Module-level path constants (mirror `test_main.py` lines 48-50 and `test_data_fetcher.py` lines 36-38):

```python
FETCH_FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'fetch'
NOTIFIER_FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'notifier'
```

---

#### Fixture loader helper

**Source:** `tests/test_main.py` lines 57-62 AND `tests/test_data_fetcher.py` lines 45-54.

Both files define an identical helper. Copy from `test_main.py`:

```python
def _load_recorded_fixture(name: str) -> pd.DataFrame:
  '''Load a committed fetch fixture (orient='split'). Mirror of
  test_data_fetcher.py's helper; recovers column dtypes identical to a live
  yfinance DataFrame.'''
  path = FETCH_FIXTURE_DIR / name
  return pd.read_json(path, orient='split')
```

---

#### `data_fetcher.yf.Ticker` monkeypatch pattern

**Source:** `tests/test_data_fetcher.py` lines 63-93 (`_FakeTicker` class + `_make_fake_ticker_factory`).

CRITICAL: The patch target is `'data_fetcher.yf.Ticker'` (the import site inside `data_fetcher`), NOT `'yfinance.Ticker'`. This is documented at `test_data_fetcher.py` lines 6-11 and confirmed in the docstring at line 60.

For F1, a simpler inline factory suffices (no call-count instrumentation needed):

```python
def _fake_ticker_factory(sym):
  class _T:
    def history(self, **_kw):
      name = 'axjo_400d.json' if sym == '^AXJO' else 'audusd_400d.json'
      return _load_recorded_fixture(name)
  return _T()
monkeypatch.setattr('data_fetcher.yf.Ticker', _fake_ticker_factory)
monkeypatch.setattr('data_fetcher.time.sleep', lambda *_a, **_k: None)
```

The `time.sleep` no-op stub is required to neutralize retry backoff — see `test_data_fetcher.py` line 142.

---

#### `_post_to_resend` capture stub pattern

**Source:** `tests/test_notifier.py` lines 1159-1175 (`test_unexpected_exception_swallowed`) — uses `monkeypatch.setattr(notifier, '_post_to_resend', ...)`.

`_post_to_resend` signature (from `notifier.py` lines 1315-1324):

```python
def _post_to_resend(
  api_key: str,
  from_addr: str,
  to_addr: str,
  subject: str,
  html_body: str | None = None,
  timeout_s: int = ...,
  retries: int = ...,
  backoff_s: int = ...,
  text_body: str | None = None,
) -> None: ...
```

F1 capture stub that records the subject for assertion:

```python
captured = {}
def _capture_post(api_key, from_addr, to_addr, subject, html_body=None, **kw):
  captured['subject'] = subject
  captured['html'] = html_body or ''

monkeypatch.setattr(notifier, '_post_to_resend', _capture_post)
```

This uses `monkeypatch.setattr(notifier, '_post_to_resend', ...)` (object attribute form), identical to the existing pattern at `test_notifier.py` line 1171.

---

#### `SIGNALS_EMAIL_FROM` env-var setup

**Source:** `tests/test_notifier.py` lines 88-100 — module-level `autouse` fixture `_pin_signals_email_from`.

`send_daily_email` reads `SIGNALS_EMAIL_FROM` per-send (added Phase 12 D-16). If the env var is absent or empty, it returns `SendStatus(ok=False, reason='missing_sender')` and does NOT write `last_email.html` — confirmed at `notifier.py` lines 1448-1451.

F1 must set this in its body (F1 is not in `test_notifier.py` so the autouse fixture there does not apply):

```python
monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@example.com')
```

To force the `_post_to_resend` dispatch path (and capture subject), also set:

```python
monkeypatch.setenv('RESEND_API_KEY', 'test_key_f1')
```

If `RESEND_API_KEY` is absent, `send_daily_email` writes `last_email.html` but returns early at `notifier.py` line 1490 (`reason='no_api_key'`) without calling `_post_to_resend` — no subject capture possible. Setting `RESEND_API_KEY` forces the full dispatch path.

---

#### `last_email.html` write location

**Source:** `notifier.py` lines 1472-1490.

`last_email.html` is written at line 1474 BEFORE the `RESEND_API_KEY` check at line 1484. The path is `Path('last_email.html')` — relative to CWD. F1 must use `monkeypatch.chdir(tmp_path)` to redirect all CWD-relative writes into the isolated tmp directory.

F1 reads the file with:

```python
email_html = (tmp_path / 'last_email.html').read_text(encoding='utf-8')
```

---

#### State seed pattern

**Source:** `tests/test_main.py` lines 2701-2717 (`_setup` in `TestDriftWarningLifecycle`).

The analog seeds state via `state_manager.save_state(seed, path=state_file_path)`. For F1, the richer fixture `tests/fixtures/notifier/sample_state_with_change.json` is used as the seed (recommended by RESEARCH.md OQ-1):

```python
import json
seed = json.loads(
  (NOTIFIER_FIXTURE_DIR / 'sample_state_with_change.json').read_text()
)
monkeypatch.chdir(tmp_path)
state_manager.save_state(seed)  # no path= → writes to CWD (tmp_path/state.json)
```

`sample_state_with_change.json` contents (verified against fixture):
- `positions.SPI200`: SHORT, entry 8285.0, 1 contract
- `positions.AUDUSD`: LONG, entry 0.6502, 5 contracts
- `signals.SPI200`: signal -1 (SHORT)
- `signals.AUDUSD`: signal 1 (LONG)
- `warnings`: 1 pre-existing drift warning (`"You hold SHORT SPI200, today's signal is LONG..."`)
- `account`: 101234.56

Combined with the 400d fetch fixtures (which produce FLAT=0 signals as of their last bar), sizing_engine.step will close both positions, exercising the full chain.

---

#### `freeze_time` pattern

**Source:** `tests/test_main.py` line 2751 (`@pytest.mark.freeze_time('2026-04-27T00:00:00+00:00')`).

`run_daily_check` short-circuits on weekends (AWST weekday gate). Use a Monday UTC midnight = Monday 08:00 AWST:

```python
@pytest.mark.freeze_time('2026-04-28T00:00:00+00:00')  # Mon 28 Apr 2026 08:00 AWST
```

RESEARCH.md confirmed 2026-04-28 is Monday. The analog uses 2026-04-27 (also Monday). Either works; use 2026-04-28 as a distinct date from the analog to avoid any golden-fixture date collisions.

---

#### `_make_args` / Namespace pattern

**Source:** `tests/test_main.py` lines 72-79.

`run_daily_check` accesses only `args.test` (line 1294) inside its body. The other fields (`reset`, `force_email`, `once`) are read by `main()` dispatcher, not by `run_daily_check` directly. F1 calls `main.main(['--force-email'])` to drive the full dispatch path (same as `TestDriftWarningLifecycle.test_w3_invariant_preserved` at line 2816).

Alternatively, call `run_daily_check` directly with a minimal Namespace:

```python
args = argparse.Namespace(
  test=False, reset=False, force_email=True, once=True,
)
rc, state, old_signals, run_date = main.run_daily_check(args)
```

The analog (`test_main.py` line 751) calls `run_daily_check(_make_args(once=True))`. F1 should use `force_email=True` to trigger email dispatch (so `_post_to_resend` stub fires and subject can be captured).

**Note:** `initial_account`, `spi_contract`, `audusd_contract` are only accessed by `_handle_reset`, NOT by `run_daily_check`. They are not needed in the Namespace for F1.

---

#### `_push_state_to_git` neutralization

**Source:** RESEARCH.md Pitfall 3. `_push_state_to_git` runs subprocess `git diff` inside tmp_path (no `.git`), producing rc=128 noise. Neutralize:

```python
monkeypatch.setattr(main, '_push_state_to_git', lambda *a, **kw: None)
```

This follows the same `monkeypatch.setattr(main, ...)` pattern used throughout `TestDriftWarningLifecycle`.

---

#### `main.logging.basicConfig` neutralization

**Source:** `tests/test_main.py` line 2702 (and numerous others).

```python
monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
```

Every test in the analog that calls `main.main()` or `main.run_daily_check()` adds this line. F1 should include it.

---

#### Complete F1 setup scaffold (assembled from analogs)

```python
@pytest.mark.freeze_time('2026-04-28T00:00:00+00:00')  # Mon 08:00 AWST
def test_full_chain_fetch_to_email(tmp_path, monkeypatch):
  import json

  # 1. Isolate CWD so state.json + last_email.html land in tmp_path
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)

  # 2. Seed state — SPI200 SHORT + AUDUSD LONG + pre-existing drift warning
  seed = json.loads(
    (NOTIFIER_FIXTURE_DIR / 'sample_state_with_change.json').read_text()
  )
  state_manager.save_state(seed)

  # 3. Mock boundary 1: yfinance → 400d canonical fixtures (FLAT signals)
  def _fake_ticker(sym):
    class _T:
      def history(self, **_kw):
        return _load_recorded_fixture(
          'axjo_400d.json' if sym == '^AXJO' else 'audusd_400d.json'
        )
    return _T()
  monkeypatch.setattr('data_fetcher.yf.Ticker', _fake_ticker)
  monkeypatch.setattr('data_fetcher.time.sleep', lambda *_a, **_k: None)

  # 4. Mock boundary 2: Resend → capture stub (no HTTPS)
  captured = {}
  def _capture_post(api_key, from_addr, to_addr, subject, html_body=None, **kw):
    captured['subject'] = subject
    captured['html'] = html_body or ''
  monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@example.com')
  monkeypatch.setenv('RESEND_API_KEY', 'test_key_f1')
  monkeypatch.setattr(notifier, '_post_to_resend', _capture_post)

  # 5. Neutralize git push subprocess (no .git in tmp_path)
  monkeypatch.setattr(main, '_push_state_to_git', lambda *a, **kw: None)

  # 6. Run full chain
  rc = main.main(['--force-email'])
  assert rc == 0
```

---

#### F1 assertion patterns

**Source:** `tests/test_notifier.py` lines 116-127 (subject assertions) + RESEARCH.md OQ-2 (verified against `notifier.py`).

```python
  # Assert on last_email.html
  email_html = (tmp_path / 'last_email.html').read_text(encoding='utf-8')
  assert '<!DOCTYPE html>' in email_html
  assert 'SPI 200' in email_html         # _fmt_instrument_display_email('SPI200')
  assert 'AUD / USD' in email_html       # _fmt_instrument_display_email('AUDUSD')
  assert 'FLAT' in email_html            # signal label (canonical fixtures → FLAT)
  assert '$' in email_html               # equity figure
  assert '━━━ Drift detected ━━━' in email_html  # notifier.py line 672
  assert 'SPI200' in email_html          # instrument name in drift warning bullet

  # Assert on captured subject (from _post_to_resend stub)
  assert 'subject' in captured, 'RESEND_API_KEY path must call _post_to_resend'
  subject = captured['subject']
  assert re.search(r'\d{4}-\d{2}-\d{2}', subject), 'subject must contain ISO date'
  assert 'SPI200' in subject
  assert 'AUDUSD' in subject
  assert '$' in subject                  # equity with $ prefix
```

Drift warning bullet text from seed fixture (html.escaped in email body):

```python
  assert 'You hold SHORT SPI200' in email_html
```

---

#### Meta-test: `patch.object` on `signal_engine.get_signal`

**Source:** `tests/test_main.py` lines 2721-2726.

```python
monkeypatch.setattr(main.signal_engine, 'get_signal', _fake_get_signal)
```

The patch is effective because `main.py` line 44 uses `import signal_engine` (module-level attribute access), not `from signal_engine import get_signal` — confirmed at RESEARCH.md OQ-5.

For the meta-test, use `unittest.mock.patch.object` (D-07) with `return_value=999` (not `side_effect=AttributeError`) so the chain runs to completion with wrong signal values — see RESEARCH.md Pitfall 4:

```python
def test_f1_catches_planted_regression(tmp_path, monkeypatch):
  # [identical setup to test_full_chain_fetch_to_email]
  ...

  # Plant regression: get_signal returns invalid value 999
  with patch.object(signal_engine, 'get_signal', return_value=999):
    rc2 = main.main(['--force-email'])
    # rc2 may be 0 (chain completes) but email content is wrong
    email_html2 = (tmp_path / 'last_email.html').read_text(encoding='utf-8')
    # 999 is not in _SIGNAL_LABELS_EMAIL → both instrument labels wrong
    # Assert the planted break causes the value-level assertion to fail:
    assert 'FLAT' not in email_html2 or ('SPI200' not in email_html2), (
      'planted get_signal regression must break email content assertions'
    )

  # Sanity check: without the patch, F1 passes (run again in clean state)
  # Reset state for second run
  state_manager.save_state(seed)
  rc3 = main.main(['--force-email'])
  assert rc3 == 0
  email_html3 = (tmp_path / 'last_email.html').read_text(encoding='utf-8')
  assert 'FLAT' in email_html3  # canonical fixtures produce FLAT signals
```

---

### `.planning/phases/16-hardening-uat-completion/16-HUMAN-UAT.md` (documentation, UAT artifact)

**Analog:** `.planning/milestones/v1.0-phases/06-email-notification/06-HUMAN-UAT.md`

The analog has this structure (confirmed by reading the file):

```
---
status: partial
phase: <phase-name>
source: [<VERIFICATION.md>]
started: YYYY-MM-DD
updated: YYYY-MM-DD
---

## Current Test

<free text status>

## Tests

### 1. <Scenario title>
expected: <what should happen>
setup: <how to run it>
result: [pending|pass|fail]

### 2. ...
### 3. ...

## Summary

total: N
passed: N
issues: N
pending: N
skipped: N
blocked: N

## Gaps
```

Per D-10, the new `16-HUMAN-UAT.md` uses a different schema (Scenario ID / Original v1.0 reference / Verification status / Operator date / Operator notes). Map each analog field to the D-10 schema:

```markdown
---
phase: 16-hardening-uat-completion
source: [16-CONTEXT.md §D-09, §D-10]
created: YYYY-MM-DD
---

## UAT-16-A: Mobile Dashboard Rendering

**Original scenario:** `.planning/milestones/v1.0-phases/06-email-notification/06-HUMAN-UAT.md §2`
**Verification status:** pending
**Operator verification date:** —
**Operator notes:**

---

## UAT-16-B: Mobile Gmail Email Rendering

**Original scenario:** `.planning/milestones/v1.0-phases/06-email-notification/06-HUMAN-UAT.md §1 + §2`
**Verification status:** pending
**Operator verification date:** —
**Operator notes:**

---

## UAT-16-C: Drift Banner in Real Weekday Email

**Original scenario:** `.planning/milestones/v1.0-phases/06-email-notification/06-HUMAN-UAT.md §3`
**Verification status:** pending
**Operator verification date:** —
**Operator notes:**

---

## Summary

| Scenario | Status | Date |
|----------|--------|------|
| UAT-16-A | pending | — |
| UAT-16-B | pending | — |
| UAT-16-C | pending | — |
```

---

### `.planning/STATE.md` (edit — add `## Completed Items` section)

**Analog:** `.planning/STATE.md` lines 211-222 (`## Deferred Items` section).

The existing `## Deferred Items` structure is:

```markdown
## Deferred Items

Items acknowledged and deferred at v1.0 milestone close on 2026-04-24:

| Category | Item | Status | v1.1 disposition |
|----------|------|--------|------------------|
| quick_task | ... | missing | ... |
| uat_gap | ... | partial | ... |
| verification_gap | ... | human_needed | ... |
| verification_gap | ... | human_needed | ... |
```

Per D-14 and D-15, the new `## Completed Items` section goes ABOVE `## Deferred Items` and mirrors the table structure with verification-specific columns:

```markdown
## Completed Items

Items deferred at v1.0 milestone close and verified closed by Phase 16:

| Category | Item | Verified | Date | Artifact |
|----------|------|----------|------|----------|
| uat_gap | Phase 06 HUMAN-UAT (3 pending scenarios — Gmail rendering verification) | yes | YYYY-MM-DD | [16-HUMAN-UAT.md §UAT-16-A/B/C](.planning/phases/16-hardening-uat-completion/16-HUMAN-UAT.md) |
| verification_gap | Phase 05 VERIFICATION (dashboard HTML visual check) | yes | YYYY-MM-DD | [16-HUMAN-UAT.md §UAT-16-A](.planning/phases/16-hardening-uat-completion/16-HUMAN-UAT.md#uat-16-a-mobile-dashboard-rendering) |
| verification_gap | Phase 06 VERIFICATION (email rendering visual check) | yes | YYYY-MM-DD | [16-HUMAN-UAT.md §UAT-16-B](.planning/phases/16-hardening-uat-completion/16-HUMAN-UAT.md#uat-16-b-mobile-gmail-email-rendering) |
```

The 4th deferred item (`quick_task` 260421-723) stays in `## Deferred Items` unchanged.

The operator fills in the `YYYY-MM-DD` dates once they mark UAT verified in `16-HUMAN-UAT.md`.

---

## Shared Patterns

### `monkeypatch.chdir(tmp_path)` — isolation of CWD-relative file writes

**Source:** `tests/test_main.py` line 2701; `tests/test_notifier.py` line 1100.
**Apply to:** `test_full_chain_fetch_to_email`, `test_f1_catches_planted_regression`

All tests that invoke `run_daily_check` or `send_daily_email` must `monkeypatch.chdir(tmp_path)` first. Both `state.json` and `last_email.html` write to CWD. Without this, the real `./state.json` and `./last_email.html` are modified, breaking the `TestGoldenEmail` golden snapshot tests in `test_notifier.py`.

### `monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)` — logging isolation

**Source:** `tests/test_main.py` line 2702 (and ~20 other occurrences).
**Apply to:** All F1 test functions.

### `@pytest.mark.freeze_time(...)` — weekday gate bypass

**Source:** `tests/test_main.py` line 2751, 2796, 2825, 2865.
**Apply to:** Both F1 test functions.

Use Monday ISO timestamp: `'2026-04-28T00:00:00+00:00'` (= Mon 28 Apr 2026 08:00 AWST).

### 2-space indent + single quotes

**Source:** `CLAUDE.md` conventions section.
**Apply to:** All new Python source in `test_integration_f1.py`.

---

## No Analog Found

All files in Phase 16 scope have close analogs. No files without patterns.

---

## Metadata

**Analog search scope:** `tests/`, `.planning/milestones/v1.0-phases/06-email-notification/`, `.planning/STATE.md`, `notifier.py`, `main.py`
**Files scanned:** 6 analog files read in full or by targeted section
**Pattern extraction date:** 2026-04-26

### Key verified facts (from direct code inspection)

| Fact | Source | Verified |
|------|--------|----------|
| `_post_to_resend` signature: `(api_key, from_addr, to_addr, subject, html_body=None, ...)` | `notifier.py` lines 1315-1324 | yes |
| `last_email.html` written at line 1474, BEFORE `api_key` check at line 1484 | `notifier.py` | yes |
| `SIGNALS_EMAIL_FROM` missing → early return, no `last_email.html` written | `notifier.py` lines 1448-1451 | yes |
| Patch target for yfinance: `'data_fetcher.yf.Ticker'` (NOT `'yfinance.Ticker'`) | `test_data_fetcher.py` lines 6-11, 113 | yes |
| `monkeypatch.setattr(main.signal_engine, 'get_signal', stub)` is effective | `test_main.py` line 2726 + RESEARCH.md OQ-5 | yes |
| `sample_state_with_change.json`: SPI200 SHORT + AUDUSD LONG + 1 drift warning | direct fixture inspection | yes |
| Drift banner literal: `'━━━ Drift detected ━━━'` | `notifier.py` line 672 | yes |
| `_make_args` / Namespace fields: `test, reset, force_email, once` (no `initial_account`) | `test_main.py` lines 72-79 | yes |
| `run_daily_check` only accesses `args.test` internally (other fields used by `main()`) | `main.py` grep | yes |
