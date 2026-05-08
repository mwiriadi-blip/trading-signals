'''Scheduler driver seam — Phase 27 Plan 13 main.py split.

Owns:
  - _get_process_tzname: process-tz wrapper (07-REVIEWS.md Codex MEDIUM-fix).
  - _run_daily_check_caught: never-crash wrapper for scheduled run_daily_check.
  - _run_schedule_loop: schedule library wiring + UTC assertion + tick loop.

Hex discipline: stdlib (logging, time) + system_params + (local) schedule +
typed exceptions from data_fetcher. The `job` parameter in _run_schedule_loop
and _run_daily_check_caught is the run_daily_check callable — passed by main.py
at call time, NOT imported here, so no scheduler_driver -> daily_run import edge.

Re-exported by main.py shim: main._get_process_tzname, main._run_daily_check_caught,
main._run_schedule_loop. Tests patch these via `main._get_process_tzname` etc.

Late-bind discipline (mirrors notifier package late-bind proxies — Plan 27-12):
when test code does `monkeypatch.setattr(main, '_get_process_tzname', fake)` or
`monkeypatch.setattr(main, '_dispatch_email_and_maintain_warnings', fake)`, the
patched name lives on the `main` package. Functions in this module that need
those references re-resolve through `main` on every call so the patch is visible.
'''
import logging
import time

import system_params
from data_fetcher import DataFetchError, ShortFrameError

logger = logging.getLogger(__name__)


def _get_process_tzname() -> str:
  '''Return the process-local timezone abbreviation (e.g. "UTC", "AEST").

  Thin wrapper around `time.tzname[0]` so Wave 1's UTC assertion inside
  `_run_schedule_loop` is patchable in tests without touching the `time`
  module's attributes (07-REVIEWS.md Codex MEDIUM-fix: `time.tzname` is
  platform-dependent and not always writable, whereas a module-level
  function in `main` is always patchable via `monkeypatch.setattr`).

  Production behaviour: identical to `time.tzname[0]`.
  Test behaviour: `monkeypatch.setattr('main._get_process_tzname', lambda: 'UTC')`.
  '''
  # IN-06: time is imported at module top (this seam is a plain function,
  # not a never-crash wrapper — the local-import idiom was cargo-culted).
  return time.tzname[0]


def _run_daily_check_caught(job, args) -> None:
  '''D-02 (Phase 7 Wave 1): never-crash wrapper for scheduled run_daily_check.

  Third instance of the never-crash pattern after _render_dashboard_never_crash
  and _send_email_never_crash. Schedule loop survives one bad run — next cron
  fire retries. ONLY valid `except Exception:` site in the loop path. Phase 8
  (ERR-04) adds crash-email dispatch on top of this net.

  After a successful daily check (rc==0 with non-None state), this wrapper
  also dispatches the daily email via `_dispatch_email_and_maintain_warnings`.
  Mirror of the dispatch step main() does for `--force-email` / `--test`
  paths. Without this dispatch the scheduler-loop daemon would compute +
  persist + render but never email — silent regression of the kind fixed
  2026-04-29.

  Catches:
    - typed DataFetchError / ShortFrameError -> WARN [Sched] data-layer failure
    - catch-all Exception -> WARN [Sched] unexpected error (loop continues)
    - rc != 0 return (happy-path non-zero) -> WARN [Sched] rc=N (loop continues)
    - rc == 0 with state=None (weekend skip) -> no dispatch (skip)
    - rc == 0 with full tuple -> dispatch email + maintain warnings
  '''
  try:
    rc, state, old_signals, run_date = job(args)
    if rc != 0:
      logger.warning(
        '[Sched] daily check returned rc=%d (loop continues)', rc,
      )
      return
    # Weekend-skip path returns (0, None, None, run_date) — nothing to dispatch.
    if state is None or old_signals is None or run_date is None:
      return
    # Scheduler path: never test mode, always persist (mirror of main()'s
    # --force-email branch). _dispatch_email_and_maintain_warnings already
    # wraps notifier.send via _send_email_never_crash, so an email failure
    # here is logged + warned but cannot abort the loop. Only state/save
    # exceptions could escape — they fall to the catch-all below.
    #
    # Late-bind via the `main` package: tests routinely
    # `monkeypatch.setattr(main, '_dispatch_email_and_maintain_warnings', fake)`
    # before calling main.main(...). Re-resolving through main on every call
    # ensures the patched callable is used (vs. capturing the original via
    # `from main import ...` at module load time).
    import main as _main_pkg
    _main_pkg._dispatch_email_and_maintain_warnings(
      state, old_signals, run_date,
      is_test=False,
      persist=True,
    )
  except (DataFetchError, ShortFrameError) as e:
    logger.warning('[Sched] data-layer failure caught in loop: %s', e)
  except Exception as e:
    logger.warning(
      '[Sched] unexpected error caught in loop: %s: %s (loop continues)',
      type(e).__name__, e,
    )


def _run_schedule_loop(
  job,
  args,
  scheduler=None,
  sleep_fn=None,
  tick_budget_s: float = float(system_params.LOOP_SLEEP_S),
  max_ticks: int | None = None,
) -> int:
  '''D-01 (Phase 7 Wave 1): factored schedule loop driver with injectable fakes.

  Production call: `_run_schedule_loop(run_daily_check, args)` — defaults flow.
  Test call: `_run_schedule_loop(..., scheduler=fake, sleep_fn=fake_sleep,
  max_ticks=1)` — one tick, no real sleep, no real scheduler thread.

  Pitfall 1 mitigation: the `schedule` library's `.at()` without tz arg uses
  process-local time. We rely on UTC. Fail fast if the process runs in any
  other tz — Replit or GHA runner misconfiguration would otherwise silently
  fire at the wrong wall-clock moment. The check goes through the
  `_get_process_tzname()` wrapper (Wave 0) so tests can patch
  `main._get_process_tzname` cleanly (07-REVIEWS.md Codex MEDIUM-fix:
  `time.tzname` is platform-dependent and sometimes frozen).

  Pitfall 7 mitigation: max_ticks=None means infinite loop (production). Tests
  MUST pass a finite max_ticks to avoid hanging.
  '''
  import time as _time

  import schedule  # LOCAL — C-2 / hex-lite / AST blocklist discipline

  # Late-bind via main package — tests use
  # `monkeypatch.setattr('main._get_process_tzname', lambda: 'UTC')`.
  import main as _main_pkg
  tzname = _main_pkg._get_process_tzname()
  if tzname != 'UTC':
    raise RuntimeError(
      f'[Sched] process tz must be UTC; got {tzname!r}. '
      f'Set TZ=UTC in the deploy environment.'
    )

  _scheduler = scheduler or schedule
  _sleep = sleep_fn or _time.sleep

  logger.info(
    '[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon–Fri'
  )
  # Late-bind _run_daily_check_caught via the main package for the same
  # monkeypatch propagation reason.
  _scheduler.every().day.at(system_params.SCHEDULE_TIME_UTC).do(
    _main_pkg._run_daily_check_caught, job, args,
  )

  ticks = 0
  while max_ticks is None or ticks < max_ticks:
    _scheduler.run_pending()
    _sleep(tick_budget_s)
    ticks += 1
  return 0
