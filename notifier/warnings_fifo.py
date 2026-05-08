'''Phase 27 #16 — FIFO bound enforcement helper.

Created in Plan 27-12 (notifier package split). Per review-fix agreed-3,
`_dispatch_email_and_maintain_warnings` STAYS in main.py:1670 (it will
relocate to daily_loop/crash_boundary in Plan 27-13). This module is the
stateless bound-enforcement helper that main-side code can adopt.

Today the canonical FIFO trim lives in `state_manager.append_warning`
(see state_manager.py:1099-1100) which already enforces the bound on
every append. This helper exposes the same bound-enforcement semantics
as a callable so external (main-side) code that mutates state['warnings']
directly without going through append_warning can defensively re-enforce
the bound.
'''
from system_params import MAX_WARNINGS


def enforce_fifo_bound(state: dict) -> None:
  '''Trim state['warnings'] to at most MAX_WARNINGS entries, oldest-first.

  Idempotent. Defensive on missing/non-list 'warnings' (no-op rather than
  crash — never-crash invariant). Callers that route appends through
  state_manager.append_warning do NOT need to call this — the appender
  already enforces the bound. This helper exists for direct-mutation code
  paths that want a single canonical FIFO-trim primitive.
  '''
  warnings = state.get('warnings')
  if not isinstance(warnings, list):
    return
  while len(warnings) > MAX_WARNINGS:
    warnings.pop(0)
