'''Phase 33 TENANT-01: subprocess helper for test_concurrent_writers_no_lost_update.

This module exists ONLY in the worktree (not in the main-repo tests/ dir), so
multiprocessing spawn-mode subprocess resolution always finds this file rather
than a stale main-repo version with an incompatible signature.
'''


def subprocess_mutate_v12(path_str, key, value, ready_event, go_event, proj_root):
  '''Subprocess body: signal ready, wait for go, then call mutate_state.
  Phase 33 TENANT-01: if key is in per-user namespace, mutate users bucket.
  proj_root: explicit worktree root so subprocess imports the worktree's
  state_manager, not the main-repo version.
  '''
  import sys
  from pathlib import Path as _Path
  # Always insert at position 0 to shadow the main-repo state_manager package.
  # The subprocess (spawn) starts with the main-repo root on sys.path; inserting
  # the worktree root first ensures the worktree's state_manager (v12) is found.
  sys.path.insert(0, proj_root)
  from state_manager import mutate_state, _ADMIN_UID
  ready_event.set()
  go_event.wait(timeout=5.0)

  _PER_USER_KEYS = frozenset({
    'account', 'initial_account', 'contracts', 'positions',
    'trade_log', 'equity_history', 'paper_trades',
  })

  def _apply(state):
    if key in _PER_USER_KEYS:
      state['users'][_ADMIN_UID][key] = value
    else:
      state[key] = value

  mutate_state(_apply, path=_Path(path_str))
