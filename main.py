'''Trading Signals — entry point + re-export shim. Phase 27 Plan 13 split.

main.py is a thin orchestrator that:
  1. Short-circuits `--version` BEFORE any heavy app imports (Plan 27-06).
  2. Re-exports symbols + module attrs that tests reference via `main.X`.
  3. Provides the `main(argv)` entry-point + dispatch ladder.

Hex-lite (CLAUDE.md): main.py is the orchestrator. Split-out seams
(cli_parser, interactive, scheduler_driver, daily_run, daily_loop,
state_actions, crash_boundary, daily_run_helpers, paper_trade_alerts)
inherit the discipline. AST blocklist in tests/test_signal_engine.py
::test_main_no_forbidden_imports forbids numpy/yfinance/requests/pandas.
'''
import sys

# Phase 27 #17 --version cold-start short-circuit. MUST precede heavy
# imports so `python main.py --version` pays only system_params cost.
# yfinance must NOT be in sys.modules after — verified by test_version_flag.py.
if __name__ == '__main__' and '--version' in sys.argv[1:]:
  from system_params import STRATEGY_VERSION  # noqa: PLC0415 — early-exit hook
  print(STRATEGY_VERSION)
  sys.exit(0)

import logging  # noqa: E402 — re-exported as main.logging for test patches

# Module re-exports — preserve monkeypatch paths (Plan 27-13 agreed-2).
# Tests do `monkeypatch.setattr(main.data_fetcher, 'fetch_ohlcv', fake)`
# and `monkeypatch.setattr('main.state_manager.append_warning', fake)`.
import data_fetcher  # noqa: E402, F401 — main.data_fetcher
import signal_engine  # noqa: E402, F401 — main.signal_engine
import sizing_engine  # noqa: E402, F401 — main.sizing_engine
import state_manager  # noqa: E402, F401 — main.state_manager

# Symbol re-exports from split-out seams.
from cli_parser import _build_parser, _validate_flag_combo, _mode_label  # noqa: E402, F401
from interactive import _stdin_isatty, _prompt_or_default, _handle_reset  # noqa: E402, F401
from scheduler_driver import (  # noqa: E402, F401
  _get_process_tzname, _run_daily_check_caught, _run_schedule_loop,
)
from crash_boundary import (  # noqa: E402, F401
  _send_email_never_crash, _build_crash_state_summary, _send_crash_email,
)
from daily_run_helpers import (  # noqa: E402, F401
  _render_dashboard_never_crash, _closed_trade_to_record,
)
# daily_loop owns the service-backed wrappers; daily_run owns the impl body.
from daily_loop import (  # noqa: E402, F401
  run_daily_check, _evaluate_paper_trade_alerts,
  _dispatch_email_and_maintain_warnings, _push_state_to_git,
)
# `main.dashboard` is patched in tests; expose the module (or None on
# import-time failure — _render_dashboard_never_crash isolates internally).
try:
  import dashboard  # noqa: E402, F401 — main.dashboard
except Exception:
  dashboard = None  # type: ignore[assignment]

from data_fetcher import DataFetchError, ShortFrameError  # noqa: E402, F401
from system_params import STRATEGY_VERSION  # noqa: E402, F401

logger = logging.getLogger(__name__)

# Phase 8 Codex-MEDIUM amendment (preserved): _LAST_LOADED_STATE caches the
# most-recently-loaded state for the crash-email summary. Tests reset via
# `main._LAST_LOADED_STATE = None`, so this MUST be a real module attribute
# (PEP 562 proxies do not intercept assignments). state_actions accessors
# read/write THROUGH this attribute — see state_actions.py for the contract.
_LAST_LOADED_STATE: 'dict | None' = None


def main(argv: list[str] | None = None) -> int:
  '''Parse CLI + configure logging + dispatch under typed-exception boundary.

  Pitfall 4: logging.basicConfig MUST use force=True (pytest may have already
  installed handlers; without force=True the call is a silent no-op).

  Dispatch ladder:
    - --reset  → _handle_reset() (mutually exclusive with other flags).
    - --force-email | --test → run_daily_check + _dispatch_email_and_maintain_warnings
      (--test structurally skips save_state per CLI-01).
    - --once → run_daily_check + warnings-flush save.
    - default → first immediate run + _run_schedule_loop.

  Exit codes: 0=happy / cancel, 1=unexpected Exception, 2=DataFetchError /
  ShortFrameError / argparse error.
  '''
  # D-06: load .env BEFORE parsing args. Local import keeps dotenv off the
  # module-top import surface (AST blocklist meaningful for non-main modules).
  from dotenv import load_dotenv  # noqa: PLC0415 — C-2 local-import pattern
  load_dotenv()  # no-op when .env absent; env vars take precedence

  parser = _build_parser()
  args = parser.parse_args(argv)
  # In-process --version handler — reachable when main() is called via
  # tests; the __main__ block's early sys.argv hook handles cold-start.
  if getattr(args, 'version', False):
    print(STRATEGY_VERSION)
    return 0
  _validate_flag_combo(args, parser)
  logging.basicConfig(
    level=logging.INFO, format='%(message)s', stream=sys.stderr, force=True,
  )
  try:
    if args.reset:
      return _handle_reset(args)
    if args.force_email or args.test:
      # D-15: shared compute-then-email path. --test structurally skips
      # save_state; --force-email persists. None-guard is defense-in-depth.
      rc, state, old_signals, run_date = run_daily_check(args)
      if (rc == 0 and state is not None
          and old_signals is not None and run_date is not None):
        # B1 canonical order: dispatch → clear → maybe-append → save.
        # persist=not args.test preserves --test structural read-only.
        _dispatch_email_and_maintain_warnings(
          state, old_signals, run_date,
          is_test=args.test, persist=not args.test,
        )
      return rc
    if args.once:
      # CR-01: once_state is None on weekends — guard. WR-01: mutate_state
      # (fcntl lock), not save_state.
      rc, once_state, _old_signals, _run_date = run_daily_check(args)
      if once_state is not None and once_state.get('warnings'):
        _final_once = once_state
        def _apply_once_warnings(fresh: dict) -> None:
          fresh['warnings'] = _final_once['warnings']
        state_manager.mutate_state(_apply_once_warnings)
      return rc
    # Default: D-04 + D-05 — immediate first run, then scheduler loop.
    _run_daily_check_caught(run_daily_check, args)
    return _run_schedule_loop(run_daily_check, args)
  except (DataFetchError, ShortFrameError) as e:
    logger.error('[Fetch] ERROR: %s', e)
    return 2
  except Exception as e:
    logger.error('[Sched] ERROR: unexpected crash: %s: %s', type(e).__name__, e)
    # ERR-04 outer crash-email net. Nested try/except so a crash-email
    # failure does not mask the original error's exit code. SC-3: pass the
    # last-loaded state via state_actions accessor (None placeholder if
    # crash predates load_state).
    try:
      from state_actions import _get_last_loaded_state
      _send_crash_email(e, state=_get_last_loaded_state())
    except Exception as crash_email_err:
      logger.error(
        '[Email] ERROR: crash-email dispatch also failed: %s: %s',
        type(crash_email_err).__name__, crash_email_err,
      )
    return 1


if __name__ == '__main__':
  sys.exit(main())
