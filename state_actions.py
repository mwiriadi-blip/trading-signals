'''State-actions seam — Phase 27 Plan 13 main.py split.

Owns the singleton `_LAST_LOADED_STATE` cache + accessor pair.

Per Phase 8 review-driven amendment (2026-04-23 Codex MEDIUM):
the most recently loaded state is cached so main()'s outer crash handler
can pass a real state summary into the crash email
(_build_crash_state_summary handles state=None for crashes-before-load).

**Storage location:** the singleton is held as `main._LAST_LOADED_STATE`
(real module attribute). state_actions._get_last_loaded_state() and
_set_last_loaded_state() read and write THROUGH the main package — this
preserves backwards-compatibility with tests that do
`main._LAST_LOADED_STATE = None` directly to reset between runs.

If main is not yet importable (very early at import time), the accessors
fall back to a local cache so daily_run.py can be imported standalone
without forcing main to load first.

Module-level assignment is safe because this process runs single-threaded
in droplet systemd one-shot and loop modes; no
concurrency hazard. Documented as a "Revisit if parallel runs appear (v2)"
decision in PROJECT.md.
'''

# Local fallback cache for the early-bootstrap path (state_actions imported
# before main has finished loading). In normal operation main has already
# reached its module-bottom by the time daily_run.py runs anything, so the
# main-attribute path is the live one.
_LAST_LOADED_STATE: 'dict | None' = None


def _get_last_loaded_state() -> 'dict | None':
  '''Return the most recently cached state dict (or None pre-load).

  Reads through main._LAST_LOADED_STATE so test code that does
  `main._LAST_LOADED_STATE = X` is observed here. Falls back to the
  local cache when main is not (yet) available.
  '''
  try:
    import main as _main_pkg
  except Exception:
    return _LAST_LOADED_STATE
  return getattr(_main_pkg, '_LAST_LOADED_STATE', _LAST_LOADED_STATE)


def _set_last_loaded_state(state: 'dict | None') -> None:
  '''Replace the cached state. Called by run_daily_check after load_state
  and after mutate_state returns the post-save snapshot. Writes through
  to main._LAST_LOADED_STATE so test code reading the legacy attribute
  sees the live value.
  '''
  global _LAST_LOADED_STATE
  _LAST_LOADED_STATE = state
  try:
    import main as _main_pkg
    _main_pkg._LAST_LOADED_STATE = state
  except Exception:
    # main not yet loaded — local cache is the only writable target.
    pass
