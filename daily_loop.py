'''Daily-loop orchestration seam — Phase 27 Plan 13 main.py split.

Per plan §truths "daily_loop.py (orchestration only)" — this is the
service-orchestration layer. Owns:
  - Service singletons (DailyRunService / SignalEvaluationService /
    PostRunService) wired to *_impl callables across crash_boundary,
    paper_trade_alerts, daily_run_helpers, and daily_run.
  - Public service-backed wrappers consumed by main.py + scheduler_driver:
    run_daily_check, _evaluate_paper_trade_alerts,
    _dispatch_email_and_maintain_warnings, _push_state_to_git.

Why this seam: keeps daily_run.py focused on the orchestration BODY
(the 9-step _run_daily_check_impl) and pushes the cross-module wiring out.
Plan 27-13 §M1 LOC budget puts daily_run.py at ~622 LOC — splitting the
service block out drops it under 550. daily_loop.py stays small (<150 LOC)
because it's pure delegation.
'''
import argparse
from datetime import datetime

import crash_boundary
import daily_run
import daily_run_helpers
import paper_trade_alerts
from services import DailyRunService, PostRunService, SignalEvaluationService

# =========================================================================
# Service wiring (delegates impls to crash_boundary + paper_trade_alerts +
# daily_run_helpers + daily_run).
# =========================================================================

_daily_run_service = DailyRunService(
  run_impl=lambda args: daily_run._run_daily_check_impl(args),
)
_signal_eval_service = SignalEvaluationService(
  evaluate_impl=lambda state, dashboard_url: paper_trade_alerts._evaluate_paper_trade_alerts_impl(
    state, dashboard_url,
  ),
)
_post_run_service = PostRunService(
  dispatch_impl=lambda state, old_signals, now, is_test, persist:
    crash_boundary._dispatch_email_and_maintain_warnings_impl(
      state, old_signals, now, is_test, persist,
    ),
  push_impl=lambda state, now: daily_run_helpers._push_state_to_git_impl(state, now),
)


# =========================================================================
# Public service-backed wrappers (test surface; main.py re-exports these).
# =========================================================================

def run_daily_check(
  args: argparse.Namespace,
) -> tuple[int, dict | None, dict | None, datetime | None]:
  '''Public entrypoint wrapper backed by the orchestration service.'''
  return _daily_run_service.run_daily_check(args)


def _evaluate_paper_trade_alerts(state: dict, dashboard_url: str) -> dict:
  '''Public compatibility wrapper backed by the signal evaluation service.'''
  return _signal_eval_service.evaluate_paper_trade_alerts(state, dashboard_url)


def _dispatch_email_and_maintain_warnings(
  state: dict,
  old_signals: dict,
  now: datetime,
  is_test: bool,
  persist: bool,
) -> None:
  '''Public compatibility wrapper backed by the post-run service.'''
  _post_run_service.dispatch_email_and_maintain_warnings(
    state, old_signals, now, is_test, persist,
  )


def _push_state_to_git(state: dict, now: datetime) -> None:
  '''Public compatibility wrapper backed by the post-run service.'''
  _post_run_service.push_state_to_git(state, now)


__all__ = [
  'run_daily_check',
  '_evaluate_paper_trade_alerts',
  '_dispatch_email_and_maintain_warnings',
  '_push_state_to_git',
]
