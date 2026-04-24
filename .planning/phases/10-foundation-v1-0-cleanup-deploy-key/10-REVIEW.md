---
phase: 10-foundation-v1-0-cleanup-deploy-key
reviewed: 2026-04-24T12:10:14Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - main.py
  - state_manager.py
  - notifier.py
  - tests/test_main.py
  - tests/test_notifier.py
  - tests/test_scheduler.py
  - tests/test_state_manager.py
findings:
  critical: 0
  warning: 1
  info: 3
  total: 4
status: issues_found
diff_base: 6b3a8c1
---

# Phase 10 Code Review

**Depth:** standard
**Files Reviewed:** 7

## Summary

Phase 10 changes are well-scoped and defensive. The `_push_state_to_git` helper correctly implements the never-crash contract with per-subcommand try/except blocks, timeout hygiene (30s diff/commit, 60s push), and nested try/except for `append_warning` calls. `reset_state` signature extension preserves backward compat (default = `INITIAL_ACCOUNT`). The notifier F401 cleanup is mechanical and correct; `ruff check` runs clean. Tests are thorough for `CalledProcessError` paths and establish strong regression coverage of the commit-vs-push log-distinction (REVIEW LOW).

One warning-level issue: the three `subprocess.TimeoutExpired` branches and three "unexpected Exception" branches inside `_push_state_to_git` have no dedicated test coverage; only `CalledProcessError` is exercised. Three info items relate to minor refactoring opportunities and a latent operational precondition.

No critical issues. No security vulnerabilities. No hex-lite boundary violations. No data-loss risks.

---

## Warnings

### WR-01 — `_push_state_to_git` timeout and generic-exception branches have no test coverage

**Files:**
- `main.py:255-281` (diff timeout + generic exception)
- `main.py:318-344` (commit timeout + generic exception)
- `main.py:373-397` (push timeout + generic exception)

**Issue:** `TestPushStateToGit` exercises `CalledProcessError` and the skip-if-unchanged + happy paths, but never raises `subprocess.TimeoutExpired` or a generic `Exception` from the fake `subprocess.run`. `grep TimeoutExpired tests/test_main.py` returns zero matches. Result: ~75 lines of exception-handling code (3 timeout branches + 3 generic-exception branches, each with a nested `append_warning` try/except) are not covered. Any regression in the warning-message format, log verb, or the nested-except structure for these paths would pass CI silently.

**Fix:** Add at least one test per branch. Template per existing style:

```python
def test_push_failure_timeout_logs_and_appends_warning(
    self, monkeypatch, caplog) -> None:
  '''Timeout path: subprocess.TimeoutExpired on push -> log [State] git push
  subprocess timeout + append warning + no crash.'''
  import logging
  import subprocess
  from datetime import datetime
  from zoneinfo import ZoneInfo
  warnings_captured: list = []

  def _fake_run(argv, **kwargs):
    if argv[:3] == ['git', 'diff', '--quiet']:
      return _FakeCompletedProcess(returncode=1)
    if 'commit' in argv:
      return _FakeCompletedProcess(returncode=0)
    if 'push' in argv:
      raise subprocess.TimeoutExpired(cmd=list(argv), timeout=60)
    raise AssertionError(f'unexpected argv: {argv}')

  def _fake_append_warning(state, source, message, now=None):
    warnings_captured.append({'source': source, 'message': message})
    return state

  monkeypatch.setattr(subprocess, 'run', _fake_run)
  monkeypatch.setattr('main.state_manager.append_warning', _fake_append_warning)
  caplog.set_level(logging.ERROR)
  state = {'account': 1.0, 'warnings': []}
  now = datetime(2026, 4, 28, 8, 0, tzinfo=ZoneInfo('Australia/Perth'))
  main._push_state_to_git(state, now)
  assert '[State] git push subprocess timeout' in caplog.text
  assert len(warnings_captured) == 1
  assert 'timed out' in warnings_captured[0]['message']
```

Repeat analogously for diff-timeout, commit-timeout, and one generic `Exception` case per subcommand. This adds ~6 tests.

---

## Info

### IN-01 — `_handle_reset` does not leverage the new `reset_state(initial_account=...)` signature

**File:** `main.py:1495-1498`

**Issue:** Phase 10 D-02 extended `reset_state` to accept `initial_account`, but `_handle_reset` still calls `reset_state()` with default args and then overwrites both `state['initial_account']` and `state['account']` explicitly. The dual-write call-site was the pre-D-02 pattern and is now redundant with the module-boundary invariant established in `state_manager.reset_state`. The current form still works correctly (defense-in-depth, as the docstring calls out) but couples two sites to the `account == initial_account` invariant instead of one.

**Fix (optional refactor):** pass `initial_account` through to `reset_state` and drop the manual sync lines:

```python
state = state_manager.reset_state(initial_account=initial_account)
state['contracts'] = {'SPI200': spi_contract, 'AUDUSD': audusd_contract}
state_manager.save_state(state)
```

Existing tests (`TestHandleReset` and `TestResetState`) cover both the boundary and the call-site, so a simplification here is low-risk. If kept as-is, the belt-and-suspenders note in the `reset_state` docstring is sufficient documentation. Note: this contradicts Codex's review-mode suggestion that was explicitly rejected in the reviews-mode replan (see 10-REVIEWS.md "Rejected" section); surface here only as a possible cleanup — not a bug.

### IN-02 — `except subprocess.TimeoutExpired` clause depends on local `import subprocess` succeeding

**File:** `main.py:233-255`

**Issue:** The outer try wraps both `import subprocess` and the `subprocess.run(...)` call. If the import itself raised (implausible for stdlib, but theoretically possible on a broken interpreter), Python would evaluate the `except subprocess.TimeoutExpired` clause and hit `NameError: name 'subprocess' is not defined` rather than falling through to `except Exception`. This is well-documented CPython behavior.

**Fix (optional hardening):** hoist `import subprocess` out of the try block:

```python
try:
  import subprocess  # local — C-2 pattern; see docstring rationale
except ImportError as e:
  logger.error('[State] subprocess import failed: %s', e)
  return

try:
  diff_result = subprocess.run(...)
  ...
except subprocess.TimeoutExpired as e:
  ...
except Exception as e:
  ...
```

Stdlib `subprocess` will essentially never fail to import, so this is a robustness nit, not a real bug. Leaving as-is is acceptable; the project convention (local import inside wrappers) is preserved.

### IN-03 — `_push_state_to_git` silently skips on fresh droplet if `state.json` is untracked

**File:** `main.py:236-243`

**Issue:** `state.json` is in `.gitignore` (`.gitignore:1`). On a fresh clone where nobody has run `git add -f state.json` yet, `git diff --quiet state.json` returns rc=0 (no tracked changes — the file is invisible to git), so the helper logs `[State] state.json unchanged — skipping git push` and returns. Operator receives no signal that nightly pushes are a no-op forever.

This is a **deployment precondition**, not a code bug. ROADMAP.md acknowledges it indirectly; the helper's docstring does not mention it. The Phase 11 deploy script is the canonical place to enforce this precondition.

**Fix (optional docs):** add a one-line note to the `_push_state_to_git` docstring under "Architecture":

```
Precondition: state.json must already be tracked by git (add -f on bootstrap).
Otherwise git diff --quiet returns 0 (file invisible to git) and the helper
silently skips on every run. Droplet bootstrap script must run `git add -f
state.json && git commit` once before enabling the systemd timer.
```

No code change required.

---

## Items Confirmed Clean

- **`reset_state` signature change** — backward-compat preserved via `initial_account: float = INITIAL_ACCOUNT` default; both `account` and `initial_account` set from same arg; `float()` coercion handles int inputs. `TestResetState` covers default, custom, edge=$1.0, and non-invariant-affecting fields.
- **`notifier.py` F401 cleanup** — 4 unused imports removed cleanly. `ruff check notifier.py` passes. No implicit re-export lost (verified: symbols are consumed from `system_params` or `FALLBACK_CONTRACT_SPECS` elsewhere).
- **`WORKFLOW_PATH` rename** — `daily.yml.disabled` exists on disk; zero code-path references to pre-rename `daily.yml` (remaining refs are in stale docs deferred to post-Phase-12 docs-sweep).
- **`_push_state_to_git` wire-up in `run_daily_check`** — placed AFTER `save_state` and `_render_dashboard_never_crash`, BEFORE the run-summary footer. Structurally unreachable on `--test` + weekend. Covered by `TestRunDailyCheckPushesState`.
- **Commit-vs-push log distinction (REVIEW LOW)** — each subcommand has its own try/except with distinct log messages. `test_commit_failure_logs_error_and_appends_warning` asserts the push-message is NOT present on commit failure, and vice versa.
- **Two-saves-per-run invariant (Phase 8 W3)** — `_push_state_to_git` does NOT call `save_state` on any branch. `test_never_calls_save_state_on_push_failure` asserts this explicitly.
- **Hex-lite boundary** — `subprocess` is locally imported inside `_push_state_to_git` only; `state_manager.py` has no subprocess/git references.
- **Commit argv safety** — all argv elements are hardcoded literals; `shell=False`, `check=True`, `capture_output=True`, explicit `timeout=` on every call; no user- or state-derived strings flow into subprocess argv.
- **`tests/test_notifier.py` ruff guard** — primary `returncode == 0` gate catches ALL ruff categories (not just F401); secondary F401 diagnostic for clarity; sensitivity test uses `tmp_path` and does not mutate `notifier.py`.
- **`tests/test_main.py::TestHandleReset`** — uses `RESET_CONFIRM=YES` env bypass to avoid stdin prompts; asserts `state['account'] == state['initial_account']` directly on CLI-flag, interactive, and default-initial-account+non-TTY paths.

---

## Audit Trail

- **2026-04-24** — Standard-depth review across 7 files (main.py, state_manager.py, notifier.py, tests/test_main.py, tests/test_notifier.py, tests/test_scheduler.py, tests/test_state_manager.py). Diff base: `6b3a8c1` (v1.1 milestone start). 0 critical, 1 warning (WR-01 timeout/generic-exception test gap), 3 info (IN-01 handle_reset refactor, IN-02 local-import exception-clause dependency, IN-03 fresh-droplet untracked-state.json precondition).
