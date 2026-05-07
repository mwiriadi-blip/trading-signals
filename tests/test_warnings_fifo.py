'''Phase 27 Plan 27-10 — Warnings FIFO regression tests.

Locks in the single-source-of-truth invariant for the warnings FIFO bound:
  - system_params.MAX_WARNINGS == 50 (review-fix agreed-4: tightened 100 -> 50).
  - WARNINGS_FIFO_MAX_LEN does NOT exist anywhere (no parallel constant).
  - Both notifier dispatch path AND state_manager.append_warning enforce the bound.
  - FIFO eviction order is canonical (drop oldest).

These tests fail loudly on any regression that:
  (a) bumps MAX_WARNINGS without operator intent,
  (b) introduces a parallel WARNINGS_FIFO_MAX_LEN constant,
  (c) hardcodes a literal bound value at the call site,
  (d) breaks FIFO eviction ordering.
'''
from __future__ import annotations

import pathlib
import re
from datetime import datetime, timezone

import pytest

import system_params
import state_manager


UTC = timezone.utc


class TestMaxWarningsValue:
  '''review-fix agreed-4: MAX_WARNINGS value is tightened 100 -> 50.'''

  def test_max_warnings_value_is_50(self) -> None:
    '''Single source of truth: MAX_WARNINGS lives in system_params and equals 50.'''
    assert system_params.MAX_WARNINGS == 50, (
      f'Phase 27 #16 review-fix agreed-4: expected MAX_WARNINGS=50, '
      f'got {system_params.MAX_WARNINGS}'
    )


class TestNoDuplicateFifoConstant:
  '''review-fix agreed-4: WARNINGS_FIFO_MAX_LEN must not exist anywhere — single
  source of truth is system_params.MAX_WARNINGS.'''

  def test_no_duplicate_fifo_constant(self) -> None:
    '''AST/grep: WARNINGS_FIFO_MAX_LEN does NOT appear anywhere in production
    or test code.'''
    repo_root = pathlib.Path(__file__).parent.parent
    # Production module dirs + tests
    search_paths = [repo_root]
    bad_files: list[str] = []
    for root in search_paths:
      for f in root.rglob('*.py'):
        # Skip virtualenv, .git, build artifacts, .planning
        rel = f.relative_to(repo_root) if f.is_relative_to(repo_root) else f
        parts = set(rel.parts)
        if any(skip in parts for skip in ('.git', '.venv', 'venv', '__pycache__',
                                            '.planning', 'node_modules', 'build', 'dist')):
          continue
        try:
          text = f.read_text()
        except (UnicodeDecodeError, OSError):
          continue
        if 'WARNINGS_FIFO_MAX_LEN' in text:
          bad_files.append(str(rel))
    assert not bad_files, (
      f'review-fix agreed-4: WARNINGS_FIFO_MAX_LEN duplicates MAX_WARNINGS. '
      f'Found in: {bad_files}'
    )


class TestWarningsFifoBound:
  '''Phase 27 #16: append_warning enforces MAX_WARNINGS upper bound.'''

  def test_warnings_fifo_does_not_exceed_max(self) -> None:
    '''Build state with 60 warnings via append_warning; assert <= MAX_WARNINGS.'''
    state = state_manager.reset_state()
    fixed_now = datetime(2026, 4, 21, 9, 0, 0, tzinfo=UTC)
    for i in range(60):
      state = state_manager.append_warning(state, 'test', f'msg {i}', now=fixed_now)
    assert len(state['warnings']) <= system_params.MAX_WARNINGS, (
      f'FIFO exceeded MAX_WARNINGS={system_params.MAX_WARNINGS}: '
      f'got {len(state["warnings"])}'
    )

  def test_warnings_fifo_eviction_order(self) -> None:
    '''Append 60 numbered warnings (0..59); FIFO must evict the oldest 10
    and keep the latest 50 in original append order (10..59).'''
    state = state_manager.reset_state()
    fixed_now = datetime(2026, 4, 21, 9, 0, 0, tzinfo=UTC)
    for i in range(60):
      state = state_manager.append_warning(state, 'test', f'msg {i}', now=fixed_now)
    # Expect the latest 50 (indices 10..59) in order
    assert len(state['warnings']) == system_params.MAX_WARNINGS
    messages = [w['message'] for w in state['warnings']]
    expected = [f'msg {i}' for i in range(60 - system_params.MAX_WARNINGS, 60)]
    assert messages == expected, (
      'FIFO eviction order violation: oldest entries should be dropped first. '
      f'Expected first={expected[0]}, last={expected[-1]}; '
      f'got first={messages[0]}, last={messages[-1]}'
    )


class TestDispatchUsesMaxWarningsConstant:
  '''review-fix agreed-4: the email-dispatch maintenance path enforces the
  bound via the same MAX_WARNINGS constant — no hardcoded literal, no
  parallel constant.

  Production note: in this codebase the FIFO maintenance lives in
  state_manager.append_warning (the sole writer to state['warnings'] per D-10).
  The orchestrator path (main._dispatch_email_and_maintain_warnings) calls
  state_manager.clear_warnings + state_manager.append_warning — both flow
  through state_manager which already imports MAX_WARNINGS. This test
  guards against either path drifting back to a hardcoded literal or
  introducing a parallel WARNINGS_FIFO_MAX_LEN constant.
  '''

  def test_state_manager_imports_max_warnings(self) -> None:
    '''state_manager imports MAX_WARNINGS from system_params (single source).'''
    src = pathlib.Path(state_manager.__file__).read_text()
    assert 'MAX_WARNINGS' in src, (
      'state_manager.py must reference MAX_WARNINGS '
      '(single source of truth in system_params).'
    )
    # The import block at the top of state_manager.py must pull MAX_WARNINGS
    # from system_params (not redefine it locally).
    assert re.search(
      r'from\s+system_params\s+import\s+\(?[^)]*\bMAX_WARNINGS\b',
      src, re.DOTALL,
    ), (
      'state_manager.py must import MAX_WARNINGS from system_params, '
      'not redefine it locally.'
    )

  def test_no_hardcoded_warnings_bound_literal_in_state_manager(self) -> None:
    '''state_manager.append_warning must NOT hardcode the literal 50 or 100
    in the slice/trim expression — it must use MAX_WARNINGS.'''
    src = pathlib.Path(state_manager.__file__).read_text()
    # Find the append_warning function body and assert no `100` or `50`
    # literal sits inside its slice expression.
    match = re.search(
      r'def append_warning\([^)]*\)[^:]*:\s*("""[^"]*"""|\'\'\'[^\']*\'\'\'|)\s*(.+?)(?=\ndef\s|\Z)',
      src, re.DOTALL,
    )
    assert match, 'append_warning function not found in state_manager.py'
    body = match.group(2)
    # The FIFO trim expression must reference MAX_WARNINGS
    assert 'MAX_WARNINGS' in body, (
      'append_warning body must use MAX_WARNINGS in the FIFO trim expression.'
    )
    # And must NOT contain a bare hardcoded slice with the literal value
    assert not re.search(r'\[\s*-\s*\(\s*100\s*-\s*1\s*\)\s*:', body), (
      'append_warning hardcodes literal 100 — must use MAX_WARNINGS.'
    )
    assert not re.search(r'\[\s*-\s*\(\s*50\s*-\s*1\s*\)\s*:', body), (
      'append_warning hardcodes literal 50 — must use MAX_WARNINGS.'
    )

  def test_dispatch_path_routes_through_state_manager(self) -> None:
    '''_dispatch_email_and_maintain_warnings must use state_manager helpers
    (clear_warnings / append_warning) — NOT mutate state["warnings"] directly.'''
    import main as main_mod
    src = pathlib.Path(main_mod.__file__).read_text()
    # Locate the _dispatch_email_and_maintain_warnings_impl function.
    match = re.search(
      r'def _dispatch_email_and_maintain_warnings_impl\([^)]*\)[^:]*:(.+?)(?=\ndef\s|\Z)',
      src, re.DOTALL,
    )
    assert match, '_dispatch_email_and_maintain_warnings_impl not found in main.py'
    body = match.group(1)
    # Helpers must be invoked at least once.
    assert 'clear_warnings' in body or 'state_manager.clear_warnings' in body, (
      '_dispatch_email_and_maintain_warnings_impl must call clear_warnings.'
    )
    assert 'append_warning' in body or 'state_manager.append_warning' in body, (
      '_dispatch_email_and_maintain_warnings_impl must call append_warning.'
    )
    # Must NOT redefine a parallel bound constant.
    assert 'WARNINGS_FIFO_MAX_LEN' not in body, (
      'review-fix agreed-4: WARNINGS_FIFO_MAX_LEN must not exist in dispatch.'
    )
