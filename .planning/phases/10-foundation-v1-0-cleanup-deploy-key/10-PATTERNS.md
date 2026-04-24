# Phase 10: Foundation — v1.0 Cleanup & Deploy Key — Pattern Map

**Mapped:** 2026-04-24
**Files analyzed:** 11 source/test/doc/config targets
**Analogs found:** 9 / 11  (2 flagged as NEW — no in-codebase analog)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `main.py::_push_state_to_git` (new helper) | orchestrator (never-crash I/O wrapper) | subprocess-call + event-log | `main.py::_send_email_never_crash` (lines 136–184) | **exact** (1:1 template) |
| `main.py::_handle_reset` (modified — D-01 1-liner) | orchestrator (CLI handler) | request-response (CLI) | current site `main.py:1278-1287` (self-analog; 1-line insertion) | **exact** |
| `main.py::run_daily_check` end-of-function hook (D-08) | orchestrator (call-site insertion) | event-driven | current site `main.py:1058-1080` (post-save, pre-return) | **exact** |
| `state_manager.py::reset_state` signature extension (D-02) | pure-ish factory (dict builder) | transform (no I/O) | current `state_manager.py:304-333` (self-analog; signature extension) | **exact** |
| `notifier.py` top-of-file import block (D-04 F401 cleanup) | I/O hex module (imports only) | N/A (import block edit) | current `notifier.py:48-79` (self-analog; deletion only) | **exact** |
| `tests/test_main.py::TestPushStateToGit` (new class) | test (unit, mocked subprocess) | event-driven | `tests/test_main.py::TestEmailNeverCrash` lines 1034–1099 (structural) + `TestCrashEmailBoundary` lines 1548–1579 (wrapper spy pattern) | **role-match** (subprocess mocking is NEW pattern; never-crash wrapper test pattern is exact) |
| `tests/test_main.py::TestHandleReset::test_reset_syncs_account_to_initial_account_{cli,interactive}` (new tests) | test (unit) | request-response | `tests/test_main.py::TestResetFlags` (CLI-flag, line 1205) + `TestResetInteractive` (line 1347) | **exact** |
| `tests/test_state_manager.py::TestReset::test_reset_state_accepts_custom_initial_account` + `test_reset_state_default_preserves_backward_compat` (new tests) | test (unit) | transform | `tests/test_state_manager.py::TestReset` lines 875–919 | **exact** |
| `tests/test_notifier.py::test_ruff_clean_notifier` (new test) | test (integration, subprocess → CLI tool) | subprocess-call + JSON parse | **NONE in codebase** — see "No Analog Found" below | **no analog (NEW pattern)** |
| `tests/test_scheduler.py::TestGHAWorkflow.WORKFLOW_PATH` (1-line constant update, line 357) | test (path constant) | N/A (filesystem lookup) | current `tests/test_scheduler.py:357` (self-analog; value change only) | **exact** |
| `.github/workflows/daily.yml` → `daily.yml.disabled` (git mv) | config (CI workflow) | N/A (rename) | current file (self-analog; rename-only) | **exact** |
| `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md` (new operator doc) | operator runbook (prose) | N/A | `docs/DEPLOY.md` lines 1–60 (structural: quickstart + numbered steps + cost/alt sections) | **role-match** (no prior `SETUP-*.md` in `.planning/`; `docs/DEPLOY.md` is the closest operator-runbook analog) |
| `.planning/PROJECT.md` / `ROADMAP.md` / `CLAUDE.md` prose (D-19 search-and-replace) | doc (cross-reference update) | N/A | current pinned lines (self-analog; copy-edit only) | **exact** |

---

## Pattern Assignments

### `main.py::_push_state_to_git` (NEW — orchestrator never-crash wrapper)

**Analog:** `main.py::_send_email_never_crash` (lines 136–184). This is a 1:1 structural template — same hex-boundary posture, same local-import discipline, same try/except layering, same logger prefix scheme (`[Email]` → `[State]`).

**Imports pattern** (analog lines 34–41):
```python
# Source: main.py:34-41 [VERIFIED]
import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
```
`subprocess` is NOT imported at module top — the helper uses a local import inside the function body (see next excerpt). This matches the `_send_email_never_crash` precedent of local-importing `notifier` inside the wrapper.

**Local-import pattern** (analog lines 167–169):
```python
# Source: main.py:167-169 [VERIFIED] — C-2 local-import pattern
try:
  import notifier  # local import — C-2 isolates import-time failures
  return notifier.send_daily_email(state, old_signals, run_date, is_test=is_test)
```
**Copy this verbatim** for subprocess: `import subprocess` as the FIRST line inside the `try:` block. The pattern is stdlib-safe but documentarily consistent.

**Logger + log-prefix pattern** (analog lines 170–171):
```python
# Source: main.py:170-171 [VERIFIED]
except Exception as e:
  logger.warning('[Email] send failed: %s: %s', type(e).__name__, e)
```
**Substitution for `_push_state_to_git`:** replace `[Email] send failed` with `[State] git push failed (cmd=%s rc=%d): %s` (three-arg form for CalledProcessError); use `logger.error` (not `logger.warning`) per D-12 ("fail-loud"). For unexpected `Exception` fallback, use `logger.error('[State] git push unexpected error: %s: %s', type(e).__name__, e)` — mirrors the analog's formatter exactly.

**append_warning invocation pattern** (from `state_manager.py:423` signature + D-12):
```python
# Source: state_manager.py:423 [VERIFIED] — 4-arg signature (state, source, message, now=None)
def append_warning(state: dict, source: str, message: str, now=None) -> dict:
```
**Copy this call shape** for the D-12 failure path:
```python
state_manager.append_warning(
  state,
  source='state_pusher',      # NEW source tag — plan must grep dashboard/notifier for unknown-source handling (researcher confirmed source is a display string only)
  message=f'Nightly state.json push failed: rc={e.returncode} stderr={stderr}',
  now=now,
)
```
Clock injection via `now=None` default mirrors `append_warning`'s own pattern — the helper's signature `_push_state_to_git(state: dict, now: datetime) -> None` takes `now` explicitly from the caller (`run_daily_check` already has `run_date` in scope).

**Full helper template** (derived from 10-RESEARCH.md §Pattern 1 + analog structure):
```python
# Pattern: copy structure from _send_email_never_crash (main.py:136-184)
# Adaptations for _push_state_to_git:
#   1. Local `import subprocess` (not `import notifier`)
#   2. Three subprocess.run calls in sequence: diff (check=False) → commit (check=True) → push (check=True)
#   3. D-09 three-way rc branch on git diff: 0 skip, 1 continue, >=128 fail-loud
#   4. D-10 inline -c flags BEFORE 'commit' subcommand (Pitfall 2)
#   5. D-11 commit message literal: 'chore(state): daily signal update [skip ci]'
#   6. D-12 fail-loud: catch CalledProcessError / TimeoutExpired / Exception separately;
#      log at ERROR with [State] prefix; append_warning(source='state_pusher'); return.
#      NO extra save_state call (preserves Phase 8 W3 two-saves-per-run invariant).
```
Full exemplar code is in 10-RESEARCH.md lines 260–356 — executor copies that into the helper body.

---

### `main.py::run_daily_check` end-of-function hook (D-08 insertion)

**Analog:** current site at `main.py:1058-1080` (self-analog — insertion between the existing `save_state` and the existing `_render_dashboard_never_crash`).

**Insertion site** (lines 1058–1080):
```python
# Source: main.py:1058-1080 [VERIFIED]
# Step 9: atomic save_state + success footer.
state_manager.save_state(state)
logger.info(
  '[State] state.json saved (account=$%.2f, trades=%d, positions=%d)',
  state['account'],
  len(state['trade_log']),
  sum(1 for p in state['positions'].values() if p is not None),
)
# Step 9.5 (Phase 5 D-06): render dashboard.html; never crash on failure.
# ...
_render_dashboard_never_crash(state, Path('dashboard.html'), run_date)
elapsed_total = time.perf_counter() - run_start_monotonic
_format_run_summary_footer(
  logger, run_date, elapsed_total,
  ...
  state_saved=True,
)
return 0, state, old_signals, run_date
```

**Pattern to insert** (after `_render_dashboard_never_crash`, before the footer or before the `return` — planner picks; recommend after the footer so the "git push" is the last observable event per D-08):
```python
# D-08 insertion (Phase 10 INFRA-02): push state.json to origin/main via
# deploy key, never crash on failure.
_push_state_to_git(state, run_date)
```
**Do NOT** call `_push_state_to_git` in the `--test` branch at line 1055 (CLI-01 read-only) nor on the weekend-skip branch — the insertion point at lines 1078-1080 is already past both guards. Verified via 10-RESEARCH.md §Architecture diagram.

---

### `main.py::_handle_reset` D-01 fix (1-line insertion)

**Analog:** current site at `main.py:1278-1287` — self-analog, 1-line insertion.

**Exact insertion site** (lines 1278–1287):
```python
# Source: main.py:1278-1287 [VERIFIED]
# --- Build + save ---
state = state_manager.reset_state()
state['initial_account'] = float(initial_account)
# D-01 FIX (Phase 10 BUG-01): insert this single line immediately below:
# state['account'] = float(initial_account)
state['contracts'] = {'SPI200': spi_contract, 'AUDUSD': audusd_contract}
state_manager.save_state(state)
logger.info(
  '[State] state.json reset (initial_account=$%.2f, SPI200=%s, AUDUSD=%s)',
  initial_account, spi_contract, audusd_contract,
)
return 0
```
**NOTE:** Once D-02 lands in `state_manager.reset_state`, the line-1279 + line-1280 pair becomes redundant (both fields are set by the factory). D-01 fix remains as defense-in-depth per 10-CONTEXT.md §Area 1 — leave both lines in place; they're idempotent.

---

### `state_manager.reset_state` signature extension (D-02)

**Analog:** current `state_manager.py:304-333` — self-analog. Project convention for `def fn(param: float = CONSTANT)` is shown directly in the analog: existing dict literal already uses `INITIAL_ACCOUNT` twice.

**Imports pattern** (analog line 48–58 — module top):
```python
# Source: state_manager.py:48-58 [VERIFIED]
from system_params import (
  INITIAL_ACCOUNT,  # used in reset_state + MIGRATIONS[2] (Phase 8)
  MAX_WARNINGS,  # noqa: F401 — used in append_warning (Wave 2)
  STATE_FILE,
  STATE_SCHEMA_VERSION,  # noqa: F401 — used in _migrate (Wave 1)
  # Phase 8 additions (D-14, CONF-02): tier vocabulary + default labels
  AUDUSD_CONTRACTS,
  SPI_CONTRACTS,
  _DEFAULT_AUDUSD_LABEL,
  _DEFAULT_SPI_LABEL,
)
```
`INITIAL_ACCOUNT` is already imported — D-02 reuses the same import; no module-top change needed.

**Signature/docstring pattern** (before → after per 10-RESEARCH Example 2):
```python
# Source: state_manager.py:304-333 [VERIFIED]
# BEFORE (current):
def reset_state() -> dict:
  '''STATE-07 / D-01 / D-03: fresh state, $100k account, empty collections.

  Each call returns a NEW dict (no shared mutable references) so that
  mutating one returned state doesn't bleed into a future reset.
  '''
  return {
    'schema_version': STATE_SCHEMA_VERSION,
    'account': INITIAL_ACCOUNT,
    ...
    'initial_account': INITIAL_ACCOUNT,
    ...
  }

# AFTER (D-02):
def reset_state(initial_account: float = INITIAL_ACCOUNT) -> dict:
  '''STATE-07 / D-01 / D-03 / Phase 10 BUG-01 D-02: fresh state,
  account + initial_account both equal to `initial_account` (default
  INITIAL_ACCOUNT from system_params).

  D-02 closes BUG-01 at the module boundary: both `state['account']`
  and `state['initial_account']` are set from the same source-of-truth
  argument, so no caller can create a state where they differ.

  Each call returns a NEW dict (no shared mutable references) ...
  '''
  return {
    'schema_version': STATE_SCHEMA_VERSION,
    'account': initial_account,                # D-02: now from arg
    ...
    'initial_account': initial_account,        # D-02: now from arg
    ...
  }
```
**Docstring style matches** `state_manager.py` module convention (2-space indent, single quotes, first line = one-sentence summary, blank line, then D-XX traceability block). Analog: see any other state_manager docstring (e.g., `append_warning` lines 423–444).

**Type-hint style** (typed kwarg with default from `system_params` constant) — **no prior exact analog in state_manager.py** (all existing public functions take `path`, `state`, or no args), but `system_params` constants are typed as `float` (see `system_params.py:109 INITIAL_ACCOUNT: float = 100_000.0`). Follow PEP 484 `param: float = CONSTANT` per CLAUDE.md §Conventions.

---

### `notifier.py` import block — F401 cleanup (D-04)

**Analog:** current `notifier.py:48-79` — self-analog.

**Current 4 F401 offenders** (verified 2026-04-24 via live `ruff check notifier.py`):
```python
# Source: notifier.py:61-79 [VERIFIED]
from system_params import (
  _COLOR_BG,
  _COLOR_BORDER,
  _COLOR_FLAT,
  _COLOR_LONG,
  _COLOR_SHORT,
  _COLOR_SURFACE,
  _COLOR_TEXT,
  _COLOR_TEXT_DIM,
  _COLOR_TEXT_MUTED,
  AUDUSD_COST_AUD,      # F401 — line 71 — genuinely unused
  AUDUSD_NOTIONAL,      # F401 — line 72 — genuinely unused
  FALLBACK_CONTRACT_SPECS,
  INITIAL_ACCOUNT,
  SPI_COST_AUD,         # F401 — line 75 — genuinely unused
  SPI_MULT,             # F401 — line 76 — genuinely unused
  TRAIL_MULT_LONG,
  TRAIL_MULT_SHORT,
)
```
**Removal pattern per D-04** (genuinely-unused bucket — confirmed by 10-RESEARCH §Summary finding 1; no `TYPE_CHECKING` / no `__all__` re-export in notifier.py): delete the four identifiers outright. Compare before/after with `ruff check notifier.py --output-format=json` returning `[]`.

**No `# noqa: F401` noqa tags needed** — none of the 4 are public re-exports per research.

---

### `tests/test_main.py::TestPushStateToGit` (NEW class — 5 tests)

**Primary structural analog:** `tests/test_main.py::TestEmailNeverCrash` lines 1034–1099.

**Class docstring pattern** (analog lines 1034–1039):
```python
# Source: tests/test_main.py:1034-1039 [VERIFIED]
class TestEmailNeverCrash:
  '''D-15 + NOTF-07 + NOTF-08: email dispatch failures never crash the run.

  Mirror of TestOrchestrator::test_dashboard_failure_never_crashes_run (runtime)
  and ::test_dashboard_import_time_failure_never_crashes_run (import-time).
  '''
```
**Substitute for Phase 10:**
```python
class TestPushStateToGit:
  '''Phase 10 INFRA-02 / D-07..D-12: nightly state.json git push never crashes.

  Mirror of TestEmailNeverCrash + TestCrashEmailBoundary (wrapper spy pattern).
  Covers: skip-if-unchanged (D-09), commit+push happy path (D-08/D-10/D-11),
  push-failure fail-loud (D-12), inline -c identity flags (Pitfall 2),
  two-saves-per-run invariant preserved (Phase 8 W3).
  '''
```

**Test method structure** (analog lines 1041–1062):
```python
# Source: tests/test_main.py:1041-1062 [VERIFIED]
def test_email_runtime_failure_never_crashes_run(
    self, tmp_path, monkeypatch, caplog) -> None:
  '''D-15: if notifier.send_daily_email raises at CALL TIME, main returns 0
  and caplog has `[Email] send failed`. State was already saved.
  '''
  caplog.set_level(logging.WARNING)
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
  _seed_fresh_state(tmp_path / 'state.json')
  _install_fixture_fetch(monkeypatch)

  import notifier as _notifier_module

  def _raise(*args, **kwargs):
    raise RuntimeError('simulated send failure')

  monkeypatch.setattr(_notifier_module, 'send_daily_email', _raise)

  rc = main.main(['--force-email'])
  assert rc == 0, 'D-15: email failure must NOT change exit code'
  assert '[Email] send failed' in caplog.text
  assert 'RuntimeError' in caplog.text
```

**Wrapper-spy pattern for argv inspection** (from `TestCrashEmailBoundary` lines 1548–1579 — exact idiom for "capture the call and assert on its args"):
```python
# Source: tests/test_main.py:1548-1579 [VERIFIED]
def test_send_crash_email_wrapper_calls_notifier(
    self, monkeypatch) -> None:
  import notifier
  calls: list = []

  def _fake(exc, summary, now=None):
    calls.append((exc, summary, now))
    return notifier.SendStatus(ok=True, reason=None)

  monkeypatch.setattr(notifier, 'send_crash_email', _fake)
  ...
  assert calls and calls[0][0] is exc
```
**Copy this `calls: list` + `def _fake(...)` + append pattern** for `test_commit_uses_inline_identity_flags` — except the target is `subprocess.run`. Spy function signature: `def _fake_run(argv, **kwargs): calls.append((list(argv), kwargs)); return _FakeCompletedProcess(rc=...)`. Replace via `monkeypatch.setattr('subprocess.run', _fake_run)` — but note: the helper does `import subprocess` LOCALLY inside its body, so the effective target is the module-global `subprocess.run`. Either `monkeypatch.setattr('subprocess.run', _fake_run)` or `monkeypatch.setattr('main.subprocess.run', ...)` works after the local import runs (the `import subprocess` line binds the stdlib module, whose `.run` attribute is patched). Confirm via direct `monkeypatch.setattr('subprocess.run', _fake_run)` — simpler.

**Swallow-errors spy pattern** (analog `TestCrashEmailBoundary` lines 1567–1579):
```python
# Source: tests/test_main.py:1567-1579 [VERIFIED]
def test_send_crash_email_wrapper_swallows_errors(
    self, monkeypatch, caplog) -> None:
  def _raise(*a, **kw):
    raise RuntimeError('notifier exploded')
  monkeypatch.setattr(notifier, 'send_crash_email', _raise)
  caplog.set_level(logging.ERROR)
  result = main._send_crash_email(RuntimeError('boom'))
  assert result is None
  assert 'crash-email dispatch wrapper failed' in caplog.text
```
**Adapt for INFRA-02 failure path:**
- Make `_fake_run` raise `subprocess.CalledProcessError(returncode=128, cmd=['git','push',...], stderr=b'fatal: Authentication failed')` on the `['git','push',...]` argv branch.
- Spy on `state_manager.append_warning` via a second `monkeypatch.setattr` to confirm it was called with `source='state_pusher'`.
- Assert `[State] git push failed` appears in `caplog.text` at ERROR level.
- Assert `state_manager.save_state` is NOT called a second time (two-saves-per-run invariant — `test_never_calls_save_state`).

---

### `tests/test_main.py::TestHandleReset::test_reset_syncs_account_to_initial_account_{cli,interactive}` (new tests)

**CLI-path analog:** `TestResetFlags::test_reset_with_all_three_flags_writes_state` at `tests/test_main.py:1205-1224`:
```python
# Source: tests/test_main.py:1205-1224 [VERIFIED]
def test_reset_with_all_three_flags_writes_state(
    self, tmp_path, monkeypatch) -> None:
  '''Test 1: all flags present + RESET_CONFIRM=YES → state.json has
  initial_account=50000.0 AND contracts matches flags.
  '''
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
  monkeypatch.setenv('RESET_CONFIRM', 'YES')
  rc = main.main([
    '--reset',
    '--initial-account', '50000',
    '--spi-contract', 'spi-mini',
    '--audusd-contract', 'audusd-standard',
  ])
  assert rc == 0
  s = json.loads((tmp_path / 'state.json').read_text())
  assert s['initial_account'] == 50000.0
  assert s['contracts'] == {
    'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard',
  }
```
**Adapt for BUG-01:** append `assert s['account'] == 50000.0` AND `assert s['account'] == s['initial_account']` to force the pairing invariant. Reuse identical fixture + chdir + monkeypatch stack.

**Interactive-path analog:** `TestResetInteractive::test_reset_interactive_happy_path` at `tests/test_main.py:1347-1360`:
```python
# Source: tests/test_main.py:1347-1360 [VERIFIED]
def test_reset_interactive_happy_path(
    self, tmp_path, monkeypatch) -> None:
  '''Test 9: TTY + iter inputs → state.json has inputs applied.'''
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
  monkeypatch.setattr('main._stdin_isatty', lambda: True)
  inputs = iter(['50000', 'spi-standard', 'audusd-mini'])
  monkeypatch.setattr('builtins.input', lambda prompt='': next(inputs))
  monkeypatch.setenv('RESET_CONFIRM', 'YES')
  rc = main.main(['--reset'])
  assert rc == 0
  s = json.loads((tmp_path / 'state.json').read_text())
  assert s['initial_account'] == 50000.0
  assert s['contracts'] == {'SPI200': 'spi-standard', 'AUDUSD': 'audusd-mini'}
```
**Adapt for BUG-01:** append `assert s['account'] == 50000.0` AND `assert s['account'] == s['initial_account']`. The monkeypatched-`input` + `iter([...])` idiom is the canonical project convention — reuse verbatim.

---

### `tests/test_state_manager.py::TestReset` extension (D-03)

**Analog:** `TestReset::test_reset_state_canonical_default_values` at `tests/test_state_manager.py:898-908`:
```python
# Source: tests/test_state_manager.py:898-908 [VERIFIED]
def test_reset_state_canonical_default_values(self) -> None:
  '''STATE-07 / D-01 / D-03: every default value matches CONTEXT.md.'''
  state = reset_state()
  assert state['schema_version'] == STATE_SCHEMA_VERSION
  assert state['account'] == INITIAL_ACCOUNT
  assert state['last_run'] is None
  assert state['positions'] == {'SPI200': None, 'AUDUSD': None}, 'D-01: None when flat'
  assert state['signals'] == {'SPI200': 0, 'AUDUSD': 0}, 'D-03: FLAT=0 init'
  assert state['trade_log'] == []
  assert state['equity_history'] == []
  assert state['warnings'] == []
```
**Adapt for Phase 10 — 2 new tests in same class:**
- `test_reset_state_accepts_custom_initial_account`: call `reset_state(initial_account=50000)` → assert `state['account'] == 50000.0` AND `state['initial_account'] == 50000.0`.
- `test_reset_state_default_preserves_backward_compat`: call `reset_state()` (no args) → assert both fields equal `INITIAL_ACCOUNT`. Backward-compat guarantee for Phase 3 tests that don't pass the kwarg.

Test class docstring/convention (2-space indent, single quotes, `STATE-XX` traceability) matches the existing `TestReset` container — follow verbatim.

---

### `tests/test_notifier.py::test_ruff_clean_notifier` (NEW — no in-codebase analog)

**FLAG: NEW PATTERN.** No existing test in the codebase invokes a CLI tool via `subprocess.run()` and parses JSON output. The closest prior pattern is `tests/test_scheduler.py` using PyYAML to parse `.github/workflows/daily.yml` in-process (no subprocess).

**Template (from 10-RESEARCH §Pattern 2, verified-live 2026-04-24):**
```python
# Source: 10-RESEARCH.md §Pattern 2 (plan-ready, not cargo-culted)
import json
import subprocess

def test_ruff_clean_notifier() -> None:
  '''CHORE-02 / D-05: notifier.py must have zero F401 warnings.'''
  result = subprocess.run(
    ['ruff', 'check', 'notifier.py', '--output-format=json'],
    capture_output=True,
    text=True,
    timeout=30,
  )
  entries = json.loads(result.stdout) if result.stdout.strip() else []
  f401_entries = [e for e in entries if e.get('code') == 'F401']
  assert len(f401_entries) == 0, (
    f'CHORE-02: notifier.py must have zero F401 (unused-import) warnings; '
    f'found {len(f401_entries)}: '
    f'{[(e["location"]["row"], e["message"]) for e in f401_entries]}'
  )
```
**Executor notes** (because no prior analog exists — do NOT cargo-cult):
- Assert only on `code == 'F401'` (stable since ruff 0.1). DO NOT assert on `fix.applicability`, `noqa_row`, or `cell` (version-variable).
- Use `text=True` for str stdout (simpler JSON parsing than bytes).
- `timeout=30` — ruff is fast but guards against hang.
- Cwd is project root when pytest runs from repo root (standard convention). Do NOT pass `cwd=` explicitly unless a test-isolation issue forces it.
- Free-floating function (module-level), NOT inside a class — matches research recommendation (D-05 is a one-shot regression guard, not a behavioural cluster).
- Placement: append to end of `tests/test_notifier.py` after the last existing class (line 1903+ per grep).

---

### `tests/test_scheduler.py::TestGHAWorkflow.WORKFLOW_PATH` (D-18 1-line constant update)

**Analog:** current `tests/test_scheduler.py:357` — self-analog, value change only.

**Exact site:**
```python
# Source: tests/test_scheduler.py:357 [VERIFIED]
class TestGHAWorkflow:
  '''SCHED-05 / D-07..D-11 / Pitfall 2: static validation of daily.yml contract.
  ...
  '''

  WORKFLOW_PATH = '.github/workflows/daily.yml'    # ← CHANGE this line
```
**Phase 10 change:**
```python
  WORKFLOW_PATH = '.github/workflows/daily.yml.disabled'
```
**Scope:** single-line edit. Fixes ALL 12 tests in the class (per 10-RESEARCH §Summary finding 3). No test-body changes needed — the constant propagates via `self.WORKFLOW_PATH` reads at test-method level.

**Additional site per 10-RESEARCH Pitfall 4:** `TestDeployDocs` at line 664 asserts `'actions/workflows/daily.yml/badge.svg' in content`. Planner decision per D-18 (a)(b)(c) — recommended (a) leave README+test alone, accept visible broken badge as "GHA retired" signal. NO code change if (a); grep-verify `TestDeployDocs` remains green.

---

### `.github/workflows/daily.yml` → `daily.yml.disabled` rename (D-16)

**Analog:** self-analog (file rename via `git mv`).

**Pattern:**
```bash
# Source: 10-RESEARCH.md §Code Examples Example 4 [VERIFIED via git docs]
git mv .github/workflows/daily.yml .github/workflows/daily.yml.disabled
git commit -m 'chore(infra): disable GHA daily.yml (droplet systemd is primary — INFRA-03)'
```
**Acceptance:** `ls .github/workflows/` lists `daily.yml.disabled` and NOT `daily.yml`. `git log --follow` preserves history.

---

### `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md` (NEW operator doc)

**FLAG: NO `SETUP-*.md` or `DEPLOY-*.md` exists under `.planning/` phase dirs** — confirmed via `Glob .planning/**/SETUP-*.md` (no files found). The closest operator-runbook analog is the REPO-ROOT `docs/DEPLOY.md` — the only operator-facing runbook of similar shape in this codebase.

**Structural analog:** `docs/DEPLOY.md` lines 1–60 (quickstart + numbered setup + what-it-does + cost estimate + alternative).

**Imports/structural pattern** (analog lines 1–17):
```markdown
# DEPLOY.md — Trading Signals operator runbook

**Primary deployment:** GitHub Actions (free, stateless-by-design, cron-driven).
**Alternative deployment:** Replit Reserved VM + Always On (persistent process).

***

## Quickstart — GitHub Actions (primary)

1. Fork / clone the repo.
2. Add Secrets under **Settings → Secrets and variables → Actions**:
   - `RESEND_API_KEY` (required) — from Resend Dashboard → API Keys
   - `SIGNALS_EMAIL_TO` (required) — your email address
3. Enable Actions: **Settings → Actions → General → "Allow all actions and reusable workflows"**.
4. **Update the README.md status badge URL** to your own `owner/repo` slug ...
5. Verify: **Actions tab → Daily signal check → "Run workflow"** (manual dispatch) → confirm green run + email arrives.
6. Wait for first scheduled run at **00:00 UTC (08:00 AWST)** next weekday.
```
**Structural elements to reuse for SETUP-DEPLOY-KEY.md:**
- Top-of-file purpose banner (one sentence per primary/alternative path).
- Horizontal rule (`***`) separators between sections.
- Numbered "Quickstart" / "Setup" steps with bolded section titles.
- `**Verify:**` / `**Expected:**` blocks for acceptance criteria per step.

**Required content per D-14 + 10-RESEARCH §Runtime State + §Pitfalls 5/6/7:**
1. `ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_trading_signals` (key outside repo tree — never commit).
2. Paste public half into GitHub → repo Settings → Deploy keys → "Allow write access" checkbox.
3. `~/.ssh/config` block with explicit `IdentityFile` + `IdentitiesOnly yes` (Pitfall 6 — avoid agent).
4. `git remote set-url origin git@github.com:<owner>/<repo>.git` + `git remote -v` verification (prevents HTTPS-cache silent-fail).
5. Explicit first-connection step: `ssh -T git@github.com` → answer `yes` to populate `~/.ssh/known_hosts` (Pitfall 7).
6. systemd `WorkingDirectory=` invariant note (Pitfall 5) — helper's `subprocess.run(['git', ...])` inherits cwd.
7. First-run verification: `python main.py --once` on droplet → confirm commit appears in `git log` under `DO Droplet <droplet@trading-signals>` author line.

**Do NOT copy:** `docs/DEPLOY.md`'s GitHub-Actions-specific content (secrets-setup, cron cost estimate, badge URL). Those are for the retired path. SETUP-DEPLOY-KEY.md is droplet-specific.

---

### `.planning/PROJECT.md` + `ROADMAP.md` + `CLAUDE.md` prose updates (D-19)

**Exact lines requiring edit — verified via grep:**

**CLAUDE.md line 46** (project root):
```markdown
- **Deployment:** GitHub Actions is the primary path (cron `0 0 * * 1-5` UTC = 08:00 AWST Mon-Fri); Replit Always On is alternative
```
**Target rewrite (per D-19):** reflect droplet-primary, GHA-disabled posture.

**`.planning/PROJECT.md` line 77** (§Context):
```markdown
- **Deployment:** GitHub Actions is the PRIMARY path (cron `0 0 * * 1-5` UTC = 08:00 AWST Mon-Fri, with `timeout-minutes: 10` runaway-run cap per Phase 9). Replit Always On documented as alternative.
```
**`.planning/PROJECT.md` line 78:**
```markdown
- **State persistence:** GHA commits `state.json` back to the repo each run; Replit filesystem persists if Always On is active.
```
**`.planning/PROJECT.md` line 105** (Key Decisions table):
```markdown
| GitHub Actions PRIMARY (Replit alternative) | Replit Autoscale doesn't guarantee filesystem persistence and kills `schedule` loops; GHA is free, stateless-by-design, and commits `state.json` back | ✓ Good |
```

**`.planning/ROADMAP.md` line 209** (§Operator Decisions Baked In — v1.1):
```markdown
| DO droplet is runtime; GitHub is source + state history via deploy-key push-back | Phase 10 INFRA-02 + Phase 11 systemd unit + Phase 16 milestone close |
```
This row is ALREADY written correctly for v1.1. The v1.0-era ROADMAP references at `.planning/milestones/v1.0-ROADMAP.md:139` and `.planning/research/*` are archived history — DO NOT rewrite them.

**`.planning/ROADMAP.md` line 215**:
```markdown
| GHA cron retired once droplet systemd runs reliably | Phase 10 INFRA-03 + Phase 11 systemd unit |
```
Also already v1.1-correct. Phase 10 validates this row by executing the rename.

**Pattern for rewrite:** replace "GitHub Actions is the primary path" → "DigitalOcean droplet systemd is the primary path; GitHub Actions cron is disabled (`.github/workflows/daily.yml.disabled` — retained for rollback per D-18)". Preserve parenthetical details (cron schedule, timeout) only if still meaningful for rollback context.

---

## Shared Patterns

### Never-crash I/O wrapper (CLAUDE.md §Architecture + Phase 6/8 precedent)

**Source:** `main.py::_send_email_never_crash` lines 136–184 and `main.py::_render_dashboard_never_crash` lines 119–129.
**Apply to:** `_push_state_to_git` (Phase 10 new helper).
**Excerpt (canonical skeleton):**
```python
# Source: main.py:119-129, 136-184 [VERIFIED]
def _xxx_never_crash(...):
  '''...docstring with [Log-prefix] identification + ...
  The ONLY place in this codebase where `except Exception:` is correct —
  alongside _render_dashboard_never_crash.
  '''
  try:
    import <adapter_module>  # local import — C-2 isolates import-time failures
    return <adapter_module>.<call>(...)
  except <SpecificException> as e:
    logger.<level>('[Prefix] specific failure: %s', ...)
    state_manager.append_warning(state, source='...', message=..., now=now)
  except Exception as e:
    logger.warning('[Prefix] unexpected: %s: %s', type(e).__name__, e)
```
**Log-prefix convention (CLAUDE.md §Conventions):** `[State]` for state-persistence failures (Phase 10 helper), `[Email]` for email, `[Signal]` for signal engine, `[Sched]` for scheduler, `[Fetch]` for data fetcher.

### Clock injection via `now=None` default

**Source:** `state_manager.py::append_warning` line 423 (`now=None` → `datetime.now(UTC)`).
**Apply to:** `_push_state_to_git(state, now)` — take `now` explicitly from the caller (`run_daily_check` already has `run_date` in scope); pass it through to `append_warning` inside the failure path. Do NOT call `datetime.now(...)` inside the helper — orchestration clock is `run_date`.

### Atomic write (UNCHANGED by Phase 10)

**Source:** `state_manager.py::save_state` via `_atomic_write` (tempfile + fsync + os.replace).
**Apply to:** NOTHING in Phase 10 — the helper `_push_state_to_git` runs AFTER `save_state` completes. The helper does NOT touch the write path. Verified: 10-RESEARCH §Architecture diagram insertion point is post-save_state.

### Sole-writer invariant for `state['warnings']` (Phase 8 D-08)

**Source:** `state_manager.py::append_warning` lines 423–451 — comment "State_manager is the SOLE writer to state['warnings'] (D-10)".
**Apply to:** `_push_state_to_git` failure path — call `append_warning` (do NOT mutate `state['warnings']` directly). Confirmed by 10-CONTEXT.md D-12.

### Two-saves-per-run invariant (Phase 8 W3)

**Source:** `main.py` currently has exactly 2 `save_state(state)` calls inside `run_daily_check`:
- line 1058 (step 9, end-of-run)
- inside `_dispatch_email_and_maintain_warnings` (post-email warnings-clear save)
**Apply to:** `_push_state_to_git` MUST NOT add a third `save_state` call (D-12 explicit). Warning persists on next run's cycle. Grep check post-implementation: `grep -c 'save_state(state)' main.py` inside `run_daily_check` body should still return 2 (plus the `_handle_reset` site at line 1282 which is module-level).

### Local-import discipline for fragile adapters

**Source:** `main.py:126` (`import dashboard` local), `main.py:168` (`import notifier` local), `main.py:178` (`from notifier import SendStatus` local).
**Apply to:** `_push_state_to_git` — `import subprocess` inside the `try:` block (not at module top), per C-2 precedent. Even though `subprocess` is stdlib and can't fail at import time, the pattern is consistency-free and tolerates future refactors.

---

## No Analog Found

Files with no close match in the codebase (planner should use RESEARCH.md patterns or flag as new):

| File / Component | Role | Data Flow | Reason |
|------------------|------|-----------|--------|
| `tests/test_notifier.py::test_ruff_clean_notifier` | test (subprocess → CLI tool) | subprocess + JSON parse | First test in the codebase that shells out to a CLI tool and parses JSON. Executor must follow the 10-RESEARCH §Pattern 2 template verbatim; NO cargo-culting prior tests. |
| `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/SETUP-DEPLOY-KEY.md` | operator runbook (droplet-side SSH setup) | N/A (prose) | No `SETUP-*.md` or `DEPLOY-*.md` exists under `.planning/` (confirmed via Glob). Closest analog is repo-root `docs/DEPLOY.md` — use its STRUCTURE (quickstart + numbered steps + verify blocks) but not its CONTENT (GHA-specific, for the retired path). Full content spec in 10-RESEARCH §Runtime State Inventory + §Pitfalls 5/6/7. |
| Git `subprocess.run(['git', ...])` invocation shape in production code | adapter (external CLI) | subprocess | No existing `subprocess.run(['git', ...])` in production modules (main.py, state_manager.py, notifier.py, dashboard.py, signal_engine.py, sizing_engine.py, system_params.py, data_fetcher.py). Only `subprocess` mentions are in `.planning/` docs for Phase 10. Template is stdlib-standard — executor follows Python 3.11 docs + 10-RESEARCH §Pattern 1. |

**Guidance for planner:** For these three items, the plan must include verbose, checklisted acceptance criteria (NOT "follow project convention") because no convention exists to reference.

---

## Metadata

**Analog search scope:**
- `main.py` — lines 1–50 (imports), 119–185 (`_render_dashboard_never_crash` + `_send_email_never_crash` never-crash wrappers), 1050–1080 (run_daily_check hook site), 1120–1288 (`_handle_reset`).
- `state_manager.py` — lines 45–59 (imports), 295–333 (`reset_state`), 415–451 (`save_state` + `append_warning`).
- `notifier.py` — lines 1–90 (module docstring + import block, incl. 4 F401 offenders).
- `tests/test_main.py` — lines 97, 474, 1034–1099 (TestEmailNeverCrash), 1200–1500 (TestResetFlags + TestResetInteractive), 1500–1580 (TestCrashEmailBoundary wrapper-spy pattern).
- `tests/test_state_manager.py` — lines 875–920 (TestReset).
- `tests/test_scheduler.py` — lines 335–530 (TestGHAWorkflow, WORKFLOW_PATH line 357), 650–680 (TestDeployDocs badge assertion).
- `tests/test_notifier.py` — structure survey (classes at lines 77–1903; confirmed no prior subprocess-call test).
- `docs/DEPLOY.md` — lines 1–60 (operator-runbook structure).
- `.planning/PROJECT.md` — lines 70–110 (Deployment + Key Decisions).
- `.planning/ROADMAP.md` — lines 200–230 (Operator Decisions Baked In).
- `CLAUDE.md` — line 46 (Deployment one-liner).

**Files scanned:** 11 source/test/doc targets + 4 confirmatory grep sweeps (subprocess, monkeypatch-subprocess, SETUP-*.md, GHA-primary prose).
**Pattern extraction date:** 2026-04-24
**Confidence:** HIGH for in-codebase analogs (all line-verified). MEDIUM for NEW patterns (subprocess-CLI test + SETUP-DEPLOY-KEY.md — 10-RESEARCH provides authoritative templates but no prior in-codebase precedent).
