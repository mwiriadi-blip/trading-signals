# Phase 7: Scheduler + GitHub Actions Deployment — Pattern Map

**Mapped:** 2026-04-23
**Files analyzed:** 11 (3 NEW + 8 MODIFIED)
**Analogs found:** 8 / 11 (3 NEW files are net-new scaffolds — no in-repo analog; researcher provides the contract)

## File Classification

| File | Role | Data Flow | Create/Modify | Closest Analog | Match Quality |
|------|------|-----------|----------------|----------------|---------------|
| `main.py` | orchestrator (helpers + dispatch ladder + prelude) | request-response | MODIFY | `main.py::_send_email_never_crash` / `_render_dashboard_never_crash` (self-precedent) | exact self-pattern |
| `system_params.py` | config (module-level constants) | constants | MODIFY | `system_params.py::INITIAL_ACCOUNT`, `STATE_SCHEMA_VERSION`, `STATE_FILE`, `SPI_MULT` | exact (same file, established pattern) |
| `requirements.txt` | build config (pinned deps) | config | MODIFY | existing lines `numpy==2.0.2`, `pandas==2.3.3`, `pytest==8.3.3` | exact |
| `.env.example` | config (env-var template + header comments) | config | MODIFY | current file (Phase 6 populated) | exact |
| `tests/test_scheduler.py` | test (unit + integration + frozen-clock) | request-response + event-driven | CREATE | `tests/test_main.py::TestOrchestrator` (frozen clock + monkeypatch); `tests/test_notifier.py` (requests fake via monkeypatch) | role-match |
| `tests/test_signal_engine.py` | test (AST blocklist extension) | static-analysis | MODIFY | lines 556–563 (`FORBIDDEN_MODULES_DASHBOARD`) + 572–579 (`FORBIDDEN_MODULES_NOTIFIER`) | exact (add two strings to two frozensets) |
| `tests/test_main.py` | test (caplog assertion replacement) | request-response | MODIFY | lines 129, 146 (existing assertions that reference deprecated log line) | exact |
| `.github/workflows/daily.yml` | CI/CD workflow (cron + commit-back) | event-driven | CREATE | none in repo — first workflow; research RESEARCH.md §Example 5 for full YAML contract | no analog (research contract only) |
| `docs/DEPLOY.md` | documentation (operator runbook) | docs | CREATE | `SPEC.md` footer §REPLIT SETUP INSTRUCTIONS (lines 333–353) as loose precedent | partial (shape only) |
| `README.md` | documentation (top-level pointer) | docs | CREATE (if absent) | none in repo — first README; SPEC.md + CLAUDE.md as content precedent | no analog |
| `.planning/ROADMAP.md` | docs (SC-4 amendment) | docs | MODIFY | line 138 existing SC-4 bullet | exact (string edit) |

## Pattern Assignments

### `main.py` — add `_run_daily_check_caught`, `_run_schedule_loop`, `load_dotenv()` bootstrap, weekday-gate prelude, default-mode dispatch flip, delete deprecated log line

**Role:** orchestrator (never-crash wrappers + loop driver + dispatch ladder amendments)
**Data flow:** request-response (single run) + event-driven (`schedule.run_pending`)
**Analog:** `main.py::_render_dashboard_never_crash` (lines 97–115) and `_send_email_never_crash` (lines 122–146) — SAME file, established pattern.

**Never-crash wrapper pattern — first analog** (`main.py:97–115`):

```python
def _render_dashboard_never_crash(state: dict, out_path: Path, now: datetime) -> None:
  '''D-06: dashboard render failure never crashes the run.

  C-2 reviews: `import dashboard` lives INSIDE the helper body (not at
  module top) so import-time errors in dashboard.py — syntax errors,
  bad sub-imports, circular-import bugs — are caught by the SAME
  `except Exception` that catches runtime render failures. Without
  this, an import-time dashboard error takes down main.py at module
  load time, before the helper even runs.

  The ONLY place in this codebase where `except Exception:` is correct —
  dashboard.html is a cosmetic artefact. State is already saved; email
  still dispatches (Phase 6). Never abort the run on a render failure.
  '''
  try:
    import dashboard  # local import — C-2 isolates import-time failures
    dashboard.render_dashboard(state, out_path, now=now)
  except Exception as e:
    logger.warning('[Dashboard] render failed: %s: %s', type(e).__name__, e)
```

**Never-crash wrapper pattern — second analog** (`main.py:122–146`):

```python
def _send_email_never_crash(
  state: dict,
  old_signals: dict,
  run_date: datetime,
  is_test: bool = False,
) -> None:
  '''D-15 + NOTF-07/NOTF-08: email dispatch never crashes the run.
  ...
  '''
  try:
    import notifier  # local import — C-2 isolates import-time failures
    notifier.send_daily_email(state, old_signals, run_date, is_test=is_test)
  except Exception as e:
    logger.warning('[Email] send failed: %s: %s', type(e).__name__, e)
```

**Key differences for Phase 7's `_run_daily_check_caught`:**
- Does NOT use a local import (the `job` callable is already resolved — passed in as an arg per D-01's injection pattern).
- Catches TYPED exceptions first (`DataFetchError`, `ShortFrameError`) at WARNING level, THEN falls through to the catch-all `except Exception` per D-02. This is a deviation from the two earlier instances which use a single `except Exception` — Phase 7 needs the data-layer distinction because those errors are *expected operational noise* on flaky Yahoo days (informational), while anything else is a genuine bug (also informational but with type-name logged).
- Extra branch: `if rc != 0: logger.warning(...)` — the job may return a non-zero return code without raising (defensive; today all failure paths raise).
- Signature: `(job, args) -> None` (not `(state, …)`) — takes the orchestrator callable + argparse.Namespace, not domain objects.
- Log prefix: `[Sched]` (not `[Dashboard]` / `[Email]`).

**Factored testable helper pattern — analog** (`notifier.py::_post_to_resend`, lines 1076–1154):

```python
def _post_to_resend(
  api_key: str,
  from_addr: str,
  to_addr: str,
  subject: str,
  html_body: str,
  timeout_s: int = _RESEND_TIMEOUT_S,
  retries: int = _RESEND_RETRIES,
  backoff_s: int = _RESEND_BACKOFF_S,
) -> None:
  ...
  last_err: Exception | None = None
  for attempt in range(1, retries + 1):
    try:
      resp = requests.post(...)
      ...
      return
    except _RESEND_RETRY_EXCEPTIONS as e:
      last_err = e
      logger.warning('[Email] Resend attempt %d/%d failed: %s: %s', attempt, retries, type(e).__name__, e)
      if attempt < retries:
        time.sleep(backoff_s)
  raise ResendError(...) from last_err
```

**Key differences for Phase 7's `_run_schedule_loop`:**
- Same style — defaults at the top of the signature (`tick_budget_s: float = 60.0`, `max_ticks: int | None = None`), the loop body references them by name.
- Injectable collaborators (`scheduler=None`, `sleep_fn=None`) with `None`-default + lazy-resolve: `_scheduler = scheduler or schedule; _sleep = sleep_fn or _time.sleep`. This is new — `_post_to_resend` has *parameter* defaults but no *collaborator* injection (it hardcodes `requests.post`). The collaborator-injection pattern is novel to Phase 7 but follows the Phase 5/6 testability ethos.
- Must include the process-TZ assertion (`assert _time.tzname[0] == 'UTC'`) at loop entry — Pitfall 1 mitigation. No analog for this in the codebase; research contract.
- `schedule` and `time` are imported LOCALLY inside the function body (`import schedule; import time as _time` at the first line of the function), same as `_render_dashboard_never_crash`'s `import dashboard` at line 112.

**Dispatch ladder amendment — analog** (`main.py::main()`, lines 749–788):

Current dispatch ladder (4 branches — `--reset`, `--force-email|--test`, default `--once`):

```python
try:
  if args.reset:
    return _handle_reset()
  if args.force_email or args.test:
    rc, state, old_signals, run_date = run_daily_check(args)
    if (rc == 0 and state is not None and old_signals is not None and run_date is not None):
      _send_email_never_crash(state, old_signals, run_date, is_test=args.test)
    return rc
  # Default / --once path: no email.
  rc, _state, _old_signals, _run_date = run_daily_check(args)
  return rc
except (DataFetchError, ShortFrameError) as e:
  logger.error('[Fetch] ERROR: %s', e)
  return 2
except Exception as e:
  logger.error('[Sched] ERROR: unexpected crash: %s: %s', type(e).__name__, e)
  return 1
```

**Phase 7 amendment:** split the last branch into `if args.once:` (one-shot, unchanged semantics) and a new default branch (immediate first run + loop):

```python
  if args.once:
    rc, _state, _old_signals, _run_date = run_daily_check(args)
    return rc
  # Default (no flag): Phase 7 loop path — immediate first run, then enter loop.
  _run_daily_check_caught(run_daily_check, args)
  return _run_schedule_loop(run_daily_check, args)
```

**Key differences from the existing ladder:**
- TWO new call sites instead of one — `_run_daily_check_caught` (synchronous, logs + swallows errors, returns None) followed by `_run_schedule_loop` (infinite loop in production; returns 0 only when tests inject finite `max_ticks`).
- The `except (DataFetchError, ShortFrameError)` + `except Exception` boundary wraps the WHOLE try-block and stays unchanged — loop-level errors are absorbed inside `_run_daily_check_caught`, never propagate up to `main()`. This is belt-and-braces: if a bug breaks `_run_daily_check_caught` itself, the outer catch still runs.

**Weekday-gate prelude — no direct analog**, but the ordering mirrors the existing step-1 log in `run_daily_check` (line 452):

```python
# Current Phase 4/6 (main.py:452–458):
run_date = _compute_run_date()
run_date_iso = run_date.strftime('%Y-%m-%d')
run_date_display = run_date.strftime('%Y-%m-%d %H:%M:%S AWST')
run_start_monotonic = time.perf_counter()
logger.info('[Sched] Run %s mode=%s', run_date_display, _mode_label(args))
logger.info('[Sched] One-shot mode (scheduler wiring lands in Phase 7)')  # <-- DELETE in Phase 7
```

**Phase 7 insertion:** immediately after `run_date = _compute_run_date()` (line 452), BEFORE derived strings:

```python
run_date = _compute_run_date()
# D-03 (Phase 7): weekday gate short-circuits BEFORE any fetch / compute / save.
if run_date.weekday() >= WEEKDAY_SKIP_THRESHOLD:  # 5=Sat, 6=Sun (stdlib contract)
  logger.info(
    '[Sched] weekend skip %s (weekday=%d) — no fetch, no state mutation',
    run_date.strftime('%Y-%m-%d'), run_date.weekday(),
  )
  return 0, None, None, run_date
run_date_iso = run_date.strftime('%Y-%m-%d')
# ... existing Phase 4/6 sequence unchanged from here ...
```

**Key differences:** returns the 4-tuple shape `(0, None, None, run_date)` — this is NEW shape. The existing `run_daily_check` always returns `(0, state, old_signals, run_date)` on success; weekend short-circuit is the first path to return `state=None`. The Phase 6 D-15 dispatch ladder in `main()` already guards this via the 4-field None-check (line 770–775) — that guard becomes the PRIMARY path on weekends, not defense-in-depth.

**DELETE line 459:** `logger.info('[Sched] One-shot mode (scheduler wiring lands in Phase 7)')`. Replace semantics with NEW line inside `_run_schedule_loop`:

```python
logger.info('[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon–Fri')
```

**`load_dotenv()` bootstrap — analog for local-import pattern** (`main.py:111–112, 142–143`):

```python
# main.py:111–112 — local import in _render_dashboard_never_crash body
try:
  import dashboard  # local import — C-2 isolates import-time failures
```

**Phase 7 application** (first lines of `main()` body, BEFORE `_build_parser()` call at line 750):

```python
def main(argv: list[str] | None = None) -> int:
  '''...'''
  from dotenv import load_dotenv  # local import (C-2 / hex-lite / AST blocklist)
  load_dotenv()  # no-op when .env absent; env vars take precedence (override=False default)
  parser = _build_parser()
  args = parser.parse_args(argv)
  # ... existing body unchanged ...
```

**Key differences:**
- Import lives in `main()` body (not in a helper) — this is the ONE place where the main function imports a dep for bootstrap rather than for error-isolation. Same C-2 discipline applies (keep `dotenv` off the module-top import list so `FORBIDDEN_MODULES_MAIN` remains meaningful).
- NO try/except wrap — `load_dotenv()` returns `False` on missing file; it cannot raise under normal operation. If it somehow did, the existing outer `except Exception` at line 784 catches it.

**Grep commands the executor can run to discover more:**

```bash
grep -n 'except Exception' main.py                           # locate the 2 valid sites; 3rd lands in Phase 7
grep -n 'local import' main.py                               # confirms the C-2 pattern wording
grep -n '^def _' main.py                                     # private helpers list (add _run_daily_check_caught + _run_schedule_loop)
grep -n "logger.info\\(\\'\\[Sched\\]" main.py               # existing [Sched] log sites — discipline check
grep -n "One-shot mode" main.py tests/                       # confirms the deletion target + test-assertion dependencies
```

---

### `system_params.py` — add `LOOP_SLEEP_S`, `SCHEDULE_TIME_UTC`, `WEEKDAY_SKIP_THRESHOLD`

**Role:** config (module-level pinned constants)
**Data flow:** constants (read-only module globals)
**Analog:** same file — `INITIAL_ACCOUNT`, `MAX_WARNINGS`, `STATE_SCHEMA_VERSION`, `STATE_FILE` (lines 74–77).

**Pattern excerpt — Phase 3 constants block** (`system_params.py:70–77`):

```python
# =========================================================================
# Phase 3 constants — state persistence (STATE-01, STATE-07, D-11)
# =========================================================================

INITIAL_ACCOUNT: float = 100_000.0  # starting account balance (STATE-07, reset_state)
MAX_WARNINGS: int = 100             # FIFO bound on state['warnings'] (D-11)
STATE_SCHEMA_VERSION: int = 1       # bump on each schema change (STATE-04)
STATE_FILE: str = 'state.json'      # repo-root state file path (SPEC.md §FILE STRUCTURE)
```

**Phase 7 additions — copy this exact style:**

```python
# =========================================================================
# Phase 7 constants — scheduler loop + weekday gate
# =========================================================================

LOOP_SLEEP_S: int = 60                   # tick-budget between schedule.run_pending calls (D-01)
SCHEDULE_TIME_UTC: str = '00:00'         # 08:00 AWST — cron fire time passed to schedule.at() (D-07)
WEEKDAY_SKIP_THRESHOLD: int = 5          # weekday() >= 5 means Sat/Sun (stdlib contract; D-03)
```

**Key details:**
- Type annotations explicit (`: int`, `: str`) — matches the rest of the file (lines 24, 31, 39–48, 53, 56, 63, 67, 74–77).
- Inline comment on each constant explaining intent + decision reference. This matches `INITIAL_ACCOUNT  # starting account balance (STATE-07, reset_state)`.
- UPPER_SNAKE naming per CLAUDE.md §Conventions.
- Header banner (`# ==... Phase 7 constants ...==`) matches the existing `# Phase N constants —` banners at lines 19, 34, 58, 70, 79, 97.
- NO imports added — these are pure scalars; file stays stdlib+typing-only.

**Grep commands:**

```bash
grep -n '^[A-Z_]*:\\s*\\(int\\|str\\|float\\|bool\\)' system_params.py   # lists all constant declarations
grep -n 'Phase [0-9] constants' system_params.py                          # header banner style
```

---

### `requirements.txt` — add `schedule==1.2.2` + `python-dotenv==1.0.1`

**Role:** build config (pinned dependencies)
**Data flow:** config
**Analog:** same file — current 6 lines use exact `==` pins:

```text
numpy==2.0.2
pandas==2.3.3
pytest==8.3.3
pytest-freezer==0.4.9
yfinance==1.2.0
ruff==0.6.9
```

**Phase 7 additions — append (order-insensitive; alpha-sort recommended to match existing order where possible):**

```text
python-dotenv==1.0.1
schedule==1.2.2
```

**Key details:**
- Exact `==` pins per CLAUDE.md: "Exact version pins (no `>=`, no `~=`) are maintained in requirements.txt per STATE.md §Todos Carried Forward."
- Researcher-selected pins (RESEARCH §Standard Stack) — `schedule==1.2.2` latest patch, `python-dotenv==1.0.1` last 1.0.x.
- No comments in the file currently — keep it that way (don't add rationale inline; rationale lives in RESEARCH.md + CLAUDE.md "Stack" section).

**Grep commands:**

```bash
cat requirements.txt  # confirm no comments, no >= pins, no blank lines expected
```

---

### `.env.example` — add GHA Secrets / Replit Secrets / local `.env` header comments

**Role:** config (env-var template + operator guidance)
**Data flow:** config / docs
**Analog:** current file (Phase 6 populated) — lines 1–9.

**Pattern excerpt — current file:**

```text
# .env.example
# Phase 6 reads RESEND_API_KEY from the process environment.
# Phase 7 will call load_dotenv() at startup to auto-load this file.
# For now, export manually before running:
#   export RESEND_API_KEY=re_xxx
#   export SIGNALS_EMAIL_TO=marc@example.com

RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SIGNALS_EMAIL_TO=your-email@example.com
```

**Phase 7 amendment — replace the header with three-tier deploy commentary, preserving the two existing env-var lines:**

```text
# .env.example
# =========================================================================
# Environment variables for trading-signals
# =========================================================================
#
# LOCAL DEV:  copy this file to .env; load_dotenv() at the top of main()
#             picks it up automatically (Phase 7 D-06). Never commit .env.
#
# GITHUB ACTIONS: set these as repo Secrets under
#                 Settings → Secrets and variables → Actions (Phase 7 D-12).
#                 The daily.yml workflow's `env:` block maps them into the
#                 Run step explicitly (no bulk ${{ secrets }} exposure).
#
# REPLIT:     add these in the Replit Secrets tab (not in code).
#             They are inherited into the process env automatically; the
#             repo does NOT need a .env file in the Replit project.
#
# Required for deploy (D-12 formal contract):
#   RESEND_API_KEY    — Resend API key (email dispatch)
#   SIGNALS_EMAIL_TO  — recipient override (falls back to Phase 6 default)
#
# Dev / CI only (NOT required for deploy):
#   RESET_CONFIRM=YES — skips the interactive prompt inside _handle_reset.

RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SIGNALS_EMAIL_TO=your-email@example.com
```

**Key differences from current file:**
- Three-tier guidance (Local / GHA / Replit) replaces the "for now export manually" note — that guidance was Phase 6 placeholder; Phase 7 delivers `load_dotenv()` so "auto-load" is now factually correct.
- No new env-var lines — the two existing variables remain verbatim. `RESET_CONFIRM` is mentioned in the comments (dev-only) but NOT written as a `KEY=value` line (that would nudge operators to set it in production).
- No `ANTHROPIC_API_KEY`, no `FROM_EMAIL`, no `TO_EMAIL`, no `ACCOUNT_START`, no `SEND_TEST_ON_START` — these appear in SPEC.md but are superseded per D-12 / RESEARCH §State of the Art.

---

### `tests/test_scheduler.py` — NEW file, 6 test classes

**Role:** test (unit + integration + frozen-clock)
**Data flow:** request-response (synchronous calls) + event-driven (scheduler ticks via injected fake)
**Analog:** `tests/test_main.py::TestOrchestrator` (Phase 4 frozen-clock + monkeypatch idiom).

**Frozen-clock + monkeypatch pattern — analog** (`tests/test_main.py:428–454`):

```python
@pytest.mark.freeze_time('2026-04-21 09:00:03+08:00')
def test_signal_as_of_and_run_date_logged_separately(
    self, tmp_path, monkeypatch, caplog) -> None:
  '''DATA-06 / D-13: signal_as_of (from df.index[-1]) and run_date
  (AWST wall-clock) are BOTH logged on every run, separately.
  '''
  caplog.set_level(logging.INFO)
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
  _seed_fresh_state(tmp_path / 'state.json')
  _install_fixture_fetch(monkeypatch)

  rc = main.main(['--test'])
  assert rc == 0
  assert 'signal_as_of=2026-04-19' in caplog.text
  assert 'Run 2026-04-21 09:00:03 AWST' in caplog.text
```

**Key idioms to copy into `test_scheduler.py`:**
1. **`@pytest.mark.freeze_time('YYYY-MM-DD HH:MM:SS+08:00')`** decorator — note the `+08:00` tz offset (AWST, no DST). This is the idiom the Phase 4 tests settled on; pytest-freezer accepts ISO-8601 with a tz offset.
2. **`monkeypatch.chdir(tmp_path)`** — state-path isolation. Required for any test that writes state.json (even if later we monkeypatch it out).
3. **`monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)`** — C-4 revision: keeps pytest's caplog handler attached. Required for any test that asserts on `caplog.text` and goes through `main.main(...)`.
4. **`caplog.set_level(logging.INFO)`** — must come BEFORE the code-under-test runs; otherwise `caplog.records` only sees WARNING+ messages.

**Monkeypatch pattern for module-level imports — analog** (`tests/test_main.py:82–90, 418`):

```python
def _install_fixture_fetch(monkeypatch) -> None:
  '''Monkeypatch main.data_fetcher.fetch_ohlcv to return committed fixtures.'''
  def _fake(sym, **_kw):
    if sym == '^AXJO':
      return _load_recorded_fixture('axjo_400d.json')
    ...
  monkeypatch.setattr(main.data_fetcher, 'fetch_ohlcv', _fake)
```

**Phase 7 extension — patch the job function, the dotenv module, and the schedule module:**

```python
monkeypatch.setattr('main._run_daily_check_caught', _fake_caught)
monkeypatch.setattr('main._run_schedule_loop', _fake_loop)
monkeypatch.setattr('dotenv.load_dotenv', lambda *a, **kw: False)
# For process-tz assertion (Pitfall 1):
import time as _t
monkeypatch.setattr(_t, 'tzname', ('UTC', 'UTC'))
# For deterministic fetch (if weekday gate test exercises the full path):
monkeypatch.setattr(main.data_fetcher, 'fetch_ohlcv', _fake_fetch)
```

**Injected-fake pattern (Phase 7-specific — no direct analog, research contract):**

```python
class _FakeScheduler:
  '''Minimal schedule-library fake for injection (RESEARCH §Example 6 lines 898-923).'''
  def __init__(self):
    self.registered: list[tuple] = []
    self.run_pending_calls = 0
  def every(self):
    return self
  def day(self):
    return self
  def at(self, time_str, *a, **kw):
    return _FakeJob(self, time_str)
  def run_pending(self):
    self.run_pending_calls += 1


class _FakeJob:
  def __init__(self, parent, time_str):
    self.parent = parent
    self.time_str = time_str
  def do(self, fn, *args, **kwargs):
    self.parent.registered.append((self.time_str, fn, args, kwargs))
    return self
```

**Six test classes (per CONTEXT §Claude's Discretion + RESEARCH §Example 6):**

| Class | Behaviour asserted | Injected fakes |
|-------|--------------------|----------------|
| `TestWeekdayGate` | `run_date.weekday() >= 5` short-circuits; parametrised [5, 6] | `@freeze_time('2026-04-25…')` (Sat), `…26…` (Sun); fetch monkeypatched to record call list |
| `TestImmediateFirstRun` | Default mode calls `_run_daily_check_caught` BEFORE `_run_schedule_loop` | `monkeypatch.setattr` both helpers to record call order |
| `TestLoopDriver` | `max_ticks=0` returns without looping; `max_ticks=1` calls `run_pending` once + sleeps once; non-UTC process asserts | `_FakeScheduler`; `sleep_fn=list.append`; `monkeypatch.setattr(time, 'tzname', ...)` |
| `TestLoopErrorHandling` | `DataFetchError`, `ShortFrameError`, `RuntimeError`, rc!=0 all swallowed | Job is a `lambda` that raises; `caplog` asserts WARNING + `[Sched]` prefix |
| `TestDefaultModeDispatch` | New `[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon–Fri` log line present; deprecated line absent | Full `main.main([])` with fakes; `_FakeScheduler` + `max_ticks=0` to avoid hang |
| `TestDotenvLoading` | `load_dotenv` fires exactly once at top of `main()` | `monkeypatch.setattr('dotenv.load_dotenv', recorder)`; short-circuit via `--reset` path |

**Grep commands:**

```bash
grep -n '@pytest.mark.freeze_time' tests/test_main.py          # freezer usage examples
grep -n 'monkeypatch.setattr' tests/test_main.py | head -20    # monkeypatch idioms
grep -n 'caplog.set_level' tests/                              # caplog discipline
grep -n 'monkeypatch.chdir(tmp_path)' tests/                   # state-path isolation idiom
```

---

### `tests/test_signal_engine.py` — extend AST blocklists with `'schedule'` + `'dotenv'`

**Role:** test (architectural hex-boundary guard)
**Data flow:** static-analysis (AST walk of source files)
**Analog:** same file — `FORBIDDEN_MODULES_DASHBOARD` (lines 556–563) and `FORBIDDEN_MODULES_NOTIFIER` (lines 572–579).

**Pattern excerpt — current `FORBIDDEN_MODULES_DASHBOARD` (lines 551–563):**

```python
# Phase 5 Wave 0: dashboard.py IS the render I/O hex — stdlib (html, json, math,
# os, statistics, tempfile, datetime, pathlib, logging) + pytz + state_manager
# (load_state) + system_params ARE allowed. But it must NOT import sibling
# hexes (signal_engine, sizing_engine, data_fetcher, notifier, main) or heavy
# scientific stack (numpy, pandas) or network/fetch libs (yfinance, requests).
FORBIDDEN_MODULES_DASHBOARD = frozenset({
  # Sibling hexes — dashboard.py is a peer, never imports them
  'signal_engine', 'sizing_engine', 'data_fetcher', 'notifier', 'main',
  # Heavy scientific stack (stdlib statistics + math are sufficient per D-07)
  'numpy', 'pandas',
  # Fetch / network — dashboard never touches network (Chart.js loads client-side)
  'yfinance', 'requests',
})
```

**Pattern excerpt — current `FORBIDDEN_MODULES_NOTIFIER` (lines 565–579):**

```python
# Phase 6 Wave 0: notifier.py IS the email I/O hex — stdlib (html, json,
# logging, os, time, tempfile, datetime, pathlib) + pytz + requests
# (Resend HTTPS) + state_manager (load_state convenience path) +
# system_params (palette + contract specs) ARE allowed. But it must NOT
# import sibling hexes (signal_engine, sizing_engine, data_fetcher,
# dashboard, main) or heavy scientific stack (numpy, pandas) or fetch
# libs (yfinance).
FORBIDDEN_MODULES_NOTIFIER = frozenset({
  # Sibling hexes — notifier.py is a peer, never imports them
  'signal_engine', 'sizing_engine', 'data_fetcher', 'dashboard', 'main',
  # Heavy scientific stack (notifier does no numeric work beyond f-string format)
  'numpy', 'pandas',
  # Fetch libs — notifier never fetches market data
  'yfinance',
})
```

**Phase 7 amendment — append two strings to each frozenset + one comment line per block:**

```python
FORBIDDEN_MODULES_DASHBOARD = frozenset({
  # Sibling hexes — dashboard.py is a peer, never imports them
  'signal_engine', 'sizing_engine', 'data_fetcher', 'notifier', 'main',
  # Heavy scientific stack (stdlib statistics + math are sufficient per D-07)
  'numpy', 'pandas',
  # Fetch / network — dashboard never touches network (Chart.js loads client-side)
  'yfinance', 'requests',
  # Phase 7: scheduler + env deps — main.py is their sole consumer
  'schedule', 'dotenv',
})
```

```python
FORBIDDEN_MODULES_NOTIFIER = frozenset({
  # Sibling hexes — notifier.py is a peer, never imports them
  'signal_engine', 'sizing_engine', 'data_fetcher', 'dashboard', 'main',
  # Heavy scientific stack (notifier does no numeric work beyond f-string format)
  'numpy', 'pandas',
  # Fetch libs — notifier never fetches market data
  'yfinance',
  # Phase 7: scheduler + env deps — main.py is their sole consumer
  'schedule', 'dotenv',
})
```

**Confirm no change needed to other blocklists (per RESEARCH lines 278–286):**
- `FORBIDDEN_MODULES` (line 488) — ALREADY contains `'schedule', 'dotenv'` ✓
- `FORBIDDEN_MODULES_STATE_MANAGER` (line 507) — ALREADY contains `'schedule', 'dotenv'` ✓
- `FORBIDDEN_MODULES_DATA_FETCHER` (line 525) — ALREADY contains `'schedule', 'dotenv'` ✓
- `FORBIDDEN_MODULES_MAIN` (line 544) — must NOT contain `'schedule'` or `'dotenv'` (main.py is their legitimate consumer). STAYS AS-IS.

**Key differences:** pure string-append inside an existing frozenset + one trailing-comment line. No test-method changes needed — `test_dashboard_no_forbidden_imports` and `test_notifier_no_forbidden_imports` already reference the right frozensets by name (lines 869, 890).

**Grep commands:**

```bash
grep -n 'FORBIDDEN_MODULES' tests/test_signal_engine.py            # all blocklist declarations
grep -n "'schedule'" tests/test_signal_engine.py                   # current state of schedule/dotenv entries
grep -n "'dotenv'" tests/test_signal_engine.py
```

---

### `tests/test_main.py` — update lines 129 and 146 (deprecated log-line assertions)

**Role:** test (caplog assertion replacement — stale assertion bridge after main.py deletes a log line)
**Data flow:** request-response
**Analog:** THE file itself — the two tests at lines 104–131 and 133–148 are the direct targets of the stale-assertion update.

**Pattern excerpt — current `test_once_flag_runs_single_check` (lines 104–131):**

```python
def test_once_flag_runs_single_check(
    self, tmp_path, monkeypatch, caplog) -> None:
  '''CLI-04: `main.main(['--once'])` returns 0, emits the [Sched] One-shot
  mode log line, and calls fetch exactly twice (SPI200 + AUDUSD).
  '''
  caplog.set_level(logging.INFO)
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
  _seed_fresh_state(tmp_path / 'state.json')

  fetch_calls: list[str] = []
  def _tracking_fetch(sym, **_kw):
    fetch_calls.append(sym)
    if sym == '^AXJO':
      return _load_recorded_fixture('axjo_400d.json')
    return _load_recorded_fixture('audusd_400d.json')
  monkeypatch.setattr(main.data_fetcher, 'fetch_ohlcv', _tracking_fetch)

  rc = main.main(['--once'])
  assert rc == 0
  assert len(fetch_calls) == 2, (
    f'CLI-04: expected exactly 2 fetch calls (one per symbol), got {fetch_calls}'
  )
  assert '[Sched] One-shot mode (scheduler wiring lands in Phase 7)' in caplog.text, (
    'CLI-04: D-07 one-shot log line missing from caplog.text'
  )
```

**Phase 7 update (per RESEARCH §Example 7, line 1099–1112):** KEEP the test name + structure; REPLACE the last assertion with a two-part check:

```python
  # Phase 7 D-05: deprecated `[Sched] One-shot mode` log line deleted.
  # --once does NOT enter the schedule loop, so the NEW `[Sched] scheduler
  # entered` line ALSO does NOT fire (CLI-04 contract: --once stays one-shot).
  assert '[Sched] scheduler entered' not in caplog.text, (
    'CLI-04: --once must NOT enter the schedule loop'
  )
  # Optional: positive check for the weekday gate NOT firing on a weekday fixture
  # (if frozen-time applied — not in this test).
```

**Pattern excerpt — current `test_default_mode_runs_once_and_logs_schedule_stub` (lines 133–148):**

```python
def test_default_mode_runs_once_and_logs_schedule_stub(
    self, tmp_path, monkeypatch, caplog) -> None:
  '''CLI-05 / D-07: default `main.main([])` behaves identically to --once in
  Phase 4 (scheduler wiring lands in Phase 7).
  '''
  caplog.set_level(logging.INFO)
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
  _seed_fresh_state(tmp_path / 'state.json')
  _install_fixture_fetch(monkeypatch)

  rc = main.main([])
  assert rc == 0
  assert '[Sched] One-shot mode (scheduler wiring lands in Phase 7)' in caplog.text, (
    'CLI-05: D-07 one-shot log line missing from default-mode caplog.text'
  )
```

**Phase 7 update (per RESEARCH §Example 7, lines 1121–1137):** RENAME the test + REPLACE the assertion + INJECT fake loop driver so the test doesn't hang:

```python
def test_default_mode_enters_schedule_loop(
    self, tmp_path, monkeypatch, caplog) -> None:
  '''Phase 7 D-05: default `main.main([])` runs an immediate first check
  then enters the schedule loop. Must inject fakes for _run_daily_check_caught
  and _run_schedule_loop so the test doesn't hang in the infinite loop.
  '''
  import time as _t
  monkeypatch.setattr(_t, 'tzname', ('UTC', 'UTC'))  # Pitfall 1 mitigation
  caplog.set_level(logging.INFO)
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
  _seed_fresh_state(tmp_path / 'state.json')
  _install_fixture_fetch(monkeypatch)

  call_order: list[tuple[str, str]] = []
  monkeypatch.setattr(
    main, '_run_daily_check_caught',
    lambda job, args: call_order.append(('caught', job.__name__)),
  )
  monkeypatch.setattr(
    main, '_run_schedule_loop',
    lambda job, args: (call_order.append(('loop', job.__name__)), 0)[1],
  )

  rc = main.main([])
  assert rc == 0
  assert call_order == [
    ('caught', 'run_daily_check'),
    ('loop', 'run_daily_check'),
  ], 'D-04: immediate first-run must precede loop entry'
```

**Key differences:**
- Test method name changes from `test_default_mode_runs_once_and_logs_schedule_stub` → `test_default_mode_enters_schedule_loop` (D-05).
- Assertion flips from "old log line present" → "call_order matches `[caught, loop]`".
- Injects fakes for BOTH `_run_daily_check_caught` AND `_run_schedule_loop` — without the loop fake, the test hangs.
- Adds `time.tzname` monkeypatch so the process-tz assertion inside `_run_schedule_loop` doesn't trip (only matters if the real `_run_schedule_loop` is exercised — defense-in-depth for the fake-swapping pattern above).
- Docstring references Phase 7 D-05 + the RESEARCH Pitfall 3 mitigation.

**Grep commands:**

```bash
grep -n "One-shot mode" tests/test_main.py                              # the 2 stale-assertion sites
grep -n 'def test_once_flag\\|def test_default_mode' tests/test_main.py # method names before/after rename
grep -n 'monkeypatch.setattr.main' tests/test_main.py                  # monkeypatch idiom — how attrs on main module are patched
```

---

### `.github/workflows/daily.yml` — NEW CI/CD workflow

**Role:** CI/CD workflow (cron trigger + commit-back)
**Data flow:** event-driven (cron + workflow_dispatch) + request-response (action invocations)
**Analog:** NONE in repo — this is the first GHA workflow. Research RESEARCH.md §Example 5 (lines 830–878) for the full YAML contract.

**Pattern excerpt (from RESEARCH §Example 5):**

```yaml
# Source: CONTEXT D-07 + D-08 + D-09 + D-10 + D-11 + D-12 + §Pitfall 2 mitigation
name: Daily signal check
on:
  schedule:
    - cron: '0 0 * * 1-5'    # 00:00 UTC = 08:00 AWST Mon–Fri. GHA drift 5–30m.
  workflow_dispatch: {}       # D-08: manual trigger for rerun-a-day

permissions:
  contents: write             # SC-1: required for git-auto-commit-action

concurrency:
  group: trading-signals      # SC-1: serialise cron + dispatch runs
  cancel-in-progress: false   # don't kill an in-flight run

jobs:
  daily:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version-file: '.python-version'   # reads 3.11.8
          cache: 'pip'
          cache-dependency-path: requirements.txt  # invalidates on dep change

      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run daily check
        env:
          RESEND_API_KEY:   ${{ secrets.RESEND_API_KEY }}
          SIGNALS_EMAIL_TO: ${{ secrets.SIGNALS_EMAIL_TO }}
        run: python main.py --once

      - uses: stefanzweifel/git-auto-commit-action@v5
        if: success()         # D-11: no commit on fail
        with:
          commit_message: 'chore(state): daily signal update [skip ci]'
          file_pattern: state.json
          add_options: '-f'   # Pitfall 2: FORCES add of gitignored state.json
          commit_user_name:  github-actions[bot]
          commit_user_email: 41898282+github-actions[bot]@users.noreply.github.com
```

**Phase 7 execution notes:**
- Single-quote the cron string: `'0 0 * * 1-5'` — YAML interprets `0 0 * * 1-5` without quotes as a sequence. The five-space form is a classic gotcha.
- `workflow_dispatch: {}` — the `{}` is the canonical "no inputs" form per D-08. Do NOT write it as `workflow_dispatch:` without the braces (that parses as `None`, which is also valid but less explicit).
- `permissions: contents: write` at the WORKFLOW level (not inside `jobs.daily`). Single-job workflow; workflow-level is cleaner.
- `cancel-in-progress: false` NOT `true` — we must not kill an in-flight cron when a manual dispatch fires.
- `add_options: '-f'` is CRITICAL per Pitfall 2 — without it, the commit-back is a silent no-op because `state.json` is in `.gitignore`.
- `commit_user_email` uses the canonical `41898282+github-actions[bot]@users.noreply.github.com` — DO NOT use a personal email (would attribute commits to a human).

**Key differences from any existing analog:** no direct precedent in this repo. The researcher's full YAML at RESEARCH §Example 5 is the ground truth; verify against three external sources (action READMEs, CONTEXT §D-07, RESEARCH §Pitfall 2) before writing.

**Grep commands:**

```bash
ls .github/                              # confirm directory does not exist yet
cat .python-version                      # confirm '3.11.8' for setup-python
grep -n 'state.json' .gitignore          # confirm gitignored (triggers Pitfall 2 fix)
```

---

### `docs/DEPLOY.md` — NEW operator runbook (~150 lines)

**Role:** documentation (operator runbook)
**Data flow:** docs
**Analog:** `SPEC.md` footer §REPLIT SETUP INSTRUCTIONS (lines 333–353) — loose shape precedent only; content is outdated (references old cron `0 22 * * 1-5`, old env-var names `TO_EMAIL`/`FROM_EMAIL`, unused `ACCOUNT_START`).

**Pattern excerpt — `SPEC.md` lines 333–353 (shape-only analog, content is obsolete):**

```text
## REPLIT SETUP INSTRUCTIONS (include as comments in main.py)

# REPLIT SETUP:
# 1. Create new Replit project → choose "Python" template
# 2. Upload all files from this project
# 3. In Replit Secrets tab, add:
#    - RESEND_API_KEY = your Resend API key
#    - TO_EMAIL = your email address           # ← obsolete: now SIGNALS_EMAIL_TO
#    - FROM_EMAIL = your verified sender email # ← obsolete: hardcoded in Phase 6
# 4. In pyproject.toml or replit.nix, ensure Python 3.11+
# 5. Click Run — app starts, runs immediately, then schedules daily at 8am AEST
# 6. Enable "Always On" in Replit settings (requires Replit Core plan ~$20/mo)
#    OR use Replit Deployments (Autoscale) for free cold-start runs
# 7. To keep free: use GitHub Actions instead (see alternative below)
```

**Phase 7 shape (per CONTEXT §D-14 / D-15 / D-16):**

```markdown
# DEPLOY.md — Trading Signals operator runbook

**Primary deployment:** GitHub Actions (free, stateless-by-design, cron-driven).
**Alternative deployment:** Replit Reserved VM + Always On (persistent process).

---

## Quickstart — GitHub Actions (primary)

1. Fork / clone the repo.
2. Add Secrets under **Settings → Secrets and variables → Actions**:
   - `RESEND_API_KEY` (required)
   - `SIGNALS_EMAIL_TO` (required)
3. Enable Actions: **Settings → Actions → "Allow all actions and reusable workflows"**.
4. Verify: **Actions tab → Daily signal check → "Run workflow"** (manual dispatch) → confirm green run + email arrives.
5. Wait for first scheduled run at **00:00 UTC (08:00 AWST)** next weekday.

### What the workflow does
- ... (fetch, compute, save state.json, send email, commit state.json back)

### Cost estimate
Daily run × 5 weekdays × 4.3 weeks/month × ~60s/run ≈ 21 min/month. Under 2% of
the 2000-min/month GitHub Actions free tier (Private repos); unlimited on Public.

---

## Alternative — Replit (Reserved VM + Always On)

Why Replit is an alternative not primary: Replit Autoscale cold-starts kill the
`schedule` loop; Replit Reserved VM + Always On is required for persistence;
GHA is free and stateless-by-design.

### Setup
1. ... (Replit project + Secrets tab + Reserved VM + Always On)
2. Click Run; `python main.py` enters the schedule loop automatically
   (Phase 7 default-mode flip).

### Filesystem-persistence caveat
Replit Reserved VM persists `state.json` across runs. Replit Autoscale DOES
NOT — autoscale resets filesystem on each cold start.

### Timezone invariant
The `schedule` library's `.at('00:00')` uses process-local time. Both GHA
ubuntu-latest and Replit Reserved VM default to UTC; `_run_schedule_loop`
asserts this at entry. If `TZ` has been set to anything else, set
`TZ=UTC` in the Replit Secrets tab.

---

## Environment variable reference

| Variable | Required | Purpose |
|----------|----------|---------|
| `RESEND_API_KEY` | Yes (deploy) | Resend API key for email dispatch |
| `SIGNALS_EMAIL_TO` | Yes (deploy) | Recipient email override |
| `RESET_CONFIRM` | No (dev/CI only) | Skips interactive prompt inside `_handle_reset` |

---

## Troubleshooting

### "Green run but no email arrived"
Check `RESEND_API_KEY` secret. Phase 6 graceful-degradation writes
`last_email.html` to the runner (ephemeral) when the key is missing.

### "Email arrives later than 08:00 AWST"
GHA cron drifts 5–30 min during peak load (00:00 UTC is peak). Documented
GitHub behaviour. For sub-minute precision pick a less-popular offset
(e.g. `'17 0 * * 1-5'` = 08:17 AWST).

### "Run failed with DataFetchError"
Yahoo Finance transient outage. Next weekday's run retries automatically.

### "State.json commit conflict"
Manual edit during a cron run. Resolve the git conflict manually. Never
force-push (CLAUDE.md safety rule).

### "Scheduler loop crashed on Replit"
Check Replit console logs. `schedule.every().day.at('00:00')` requires
process persistence — verify Always On is active.

### "Scheduler fires at the wrong wall-clock time on Replit"
Confirm the Replit container's TZ is UTC (default for Reserved VM).
Run `date` in the Replit shell; the output should end in `UTC`. If it
doesn't, add `TZ=UTC` to the Replit Secrets tab.

### "First workflow run after Phase 7 deploy — no commit"
Check the Actions log for "Working tree clean. Nothing to commit." This
means `add_options: '-f'` is missing from the git-auto-commit step —
state.json is in `.gitignore` and needs the force-add. Fix in
`.github/workflows/daily.yml`.

### "[skip ci] token limitations"
`[skip ci]` in our commit messages prevents future push-triggered CI
workflows from running on state.json-only commits. It does NOT affect
the daily cron schedule (cron is unrelated to commits).

---

## Notes

SPEC.md is the historical project brief; PROJECT.md and CLAUDE.md are the
current source of truth for deployment specifics. Env-var names in this
runbook supersede SPEC.md (`TO_EMAIL` → `SIGNALS_EMAIL_TO`, `FROM_EMAIL` →
hardcoded in notifier, `ACCOUNT_START` / `SEND_TEST_ON_START` removed).
```

**Key differences from SPEC.md analog:**
- GHA is PRIMARY (SPEC.md treats it as a fallback at line 349).
- Env vars are CURRENT (`SIGNALS_EMAIL_TO` not `TO_EMAIL`; no `FROM_EMAIL`).
- Cron is `0 0 * * 1-5` (SPEC.md has outdated `0 22 * * 1-5` AEST).
- Troubleshooting section is NEW (SPEC.md has no operator recovery guidance).
- Markdown format (not embedded shell comments) — standalone doc consumed by git/GitHub.
- ~150 lines per D-15.

---

### `README.md` — NEW top-level README (~50 lines if absent)

**Role:** documentation (top-level pointer)
**Data flow:** docs
**Analog:** NONE in repo. CLAUDE.md header + SPEC.md lead paragraph are content precedents.

**Content precedent — CLAUDE.md header (lines 1–3):**

```markdown
# Trading Signals — SPI 200 & AUD/USD Mechanical System

**Python signal-only trading app.** Computes daily ATR/ADX/momentum signals for `^AXJO` (SPI 200) and `AUDUSD=X`, persists state, renders a dashboard, and emails a weekday report at 08:00 AWST. Never places live trades.
```

**Phase 7 README shape (minimal pointer per CONTEXT §Claude's Discretion):**

```markdown
# Trading Signals

Python signal-only trading app. Computes daily ATR/ADX/momentum signals for
SPI 200 and AUD/USD, persists state, renders a dashboard, and emails a
weekday report at 08:00 AWST. Never places live trades.

## Quickstart

```bash
pip install -r requirements.txt
python main.py --once      # one-shot run (GHA / cron mode)
python main.py             # run once, then enter schedule loop (Replit / local)
python main.py --test      # dry run — no state mutation, email marked [TEST]
python main.py --reset     # reinitialise state.json to fresh $100k
```

## Documentation

- [SPEC.md](SPEC.md) — full functional specification (archival brief).
- [docs/DEPLOY.md](docs/DEPLOY.md) — **operator runbook** (GitHub Actions + Replit setup, env vars, troubleshooting).
- [CLAUDE.md](CLAUDE.md) — conventions, architecture, stack lock.
- [.planning/ROADMAP.md](.planning/ROADMAP.md) — phase breakdown.

## Architecture

Hexagonal-lite. Pure math in `signal_engine.py` + `sizing_engine.py`; I/O
adapters in `state_manager.py`, `notifier.py`, `dashboard.py`, `data_fetcher.py`;
`main.py` is the thin orchestrator. See [CLAUDE.md](CLAUDE.md) for boundary rules.
```

**Key differences from any analog:** no in-repo README precedent; shape is derived from CLAUDE.md header (opening paragraph) + a Quickstart block + a 4-link documentation index. ~50 lines per CONTEXT recommendation.

---

### `.planning/ROADMAP.md` — SC-4 amendment (drop `ANTHROPIC_API_KEY`)

**Role:** documentation (roadmap success-criterion edit)
**Data flow:** docs
**Analog:** line 138 of the file.

**Pattern excerpt — current line 138:**

```markdown
  4. All secrets (`RESEND_API_KEY`, optional `ANTHROPIC_API_KEY`) are loaded from env vars with `python-dotenv` locally and GitHub Secrets / Replit Secrets in deploy — never committed
```

**Phase 7 amendment (per D-12 + RESEARCH §user_constraints):**

```markdown
  4. All secrets (`RESEND_API_KEY`, `SIGNALS_EMAIL_TO`) are loaded from env vars with `python-dotenv` locally and GitHub Secrets / Replit Secrets in deploy — never committed
```

**Key differences:**
- `ANTHROPIC_API_KEY` removed — NO code reads it (per CONTEXT §D-12 rationale); LLM-backed summarisation is deferred to v2.
- `SIGNALS_EMAIL_TO` added — matches the ACTUAL Phase 6 contract (D-14).
- "optional" qualifier removed — both listed vars are now required for deploy per D-12.

**Grep commands:**

```bash
grep -n 'ANTHROPIC_API_KEY' .planning/                 # confirm only ROADMAP mentions it
grep -n 'SIGNALS_EMAIL_TO' .planning/ROADMAP.md        # check if it's already referenced elsewhere
```

---

## Shared Patterns

### Pattern A — Local import for C-2 isolation + AST blocklist discipline

**Source:** `main.py::_render_dashboard_never_crash` (line 112) and `_send_email_never_crash` (line 143).
**Apply to:** `_run_schedule_loop` (imports `schedule` + `time as _time`), `main()` (imports `load_dotenv`).

**Excerpt:**

```python
# main.py:111–112 (inside _render_dashboard_never_crash)
try:
  import dashboard  # local import — C-2 isolates import-time failures
  dashboard.render_dashboard(state, out_path, now=now)
except Exception as e:
  logger.warning('[Dashboard] render failed: %s: %s', type(e).__name__, e)
```

**Phase 7 application — `_run_schedule_loop` body:**

```python
def _run_schedule_loop(job, args, scheduler=None, sleep_fn=None, tick_budget_s=60.0, max_ticks=None):
  import schedule           # LOCAL — C-2 + AST blocklist discipline
  import time as _time      # LOCAL — same reason (main.py already imports 'time' at top, but using
                            # `_time` here avoids shadowing the module-level `time` used by Phase 4).
  ...
```

**Phase 7 application — `main()` body first two lines:**

```python
def main(argv: list[str] | None = None) -> int:
  from dotenv import load_dotenv     # LOCAL — keeps 'dotenv' off module-top imports
  load_dotenv()                      # no-op when .env absent; override=False by default
  parser = _build_parser()
  ...
```

**Why this matters for Phase 7:** `FORBIDDEN_MODULES_MAIN` (line 544) does NOT list `schedule` or `dotenv` — main.py is their ONLY legitimate consumer. The AST walk (`_top_level_imports`, `ast.walk`) catches imports *anywhere* in the file, including inside function bodies. So the local-import pattern is about isolating *import-time failures* (C-2 rationale) — not about evading the blocklist. The `FORBIDDEN_MODULES_{STATE_MANAGER, DATA_FETCHER, DASHBOARD, NOTIFIER}` blocklists (extended in Phase 7) enforce that no OTHER module imports these libs.

---

### Pattern B — Injected collaborators with `None`-default + lazy-resolve

**Source:** Phase 5 D-06 + Phase 6 D-15 renderer testability pattern (discussed in CONTEXT §code_context).
**Apply to:** `_run_schedule_loop(scheduler=None, sleep_fn=None)`.

**Excerpt (Phase 7-specific — no direct in-repo analog; closest: `notifier.py::_post_to_resend` parameter defaults):**

```python
def _run_schedule_loop(
  job,
  args,
  scheduler=None,              # injected fake in tests; defaults to real `schedule` module
  sleep_fn=None,               # injected list.append in tests; defaults to time.sleep
  tick_budget_s: float = 60.0, # LOOP_SLEEP_S from system_params.py default
  max_ticks: int | None = None, # None = infinite (production); finite in tests
) -> int:
  import schedule
  import time as _time
  _scheduler = scheduler or schedule    # lazy-resolve
  _sleep = sleep_fn or _time.sleep      # lazy-resolve
  ...
```

**Why this matters for Phase 7:** tests at `TestLoopDriver` pass `scheduler=_FakeScheduler()` + `sleep_fn=list.append` + `max_ticks=0` to avoid real loops and real sleeps. Production call is bare: `_run_schedule_loop(run_daily_check, args)` — all defaults flow through.

---

### Pattern C — Log prefix discipline (`[Sched]`)

**Source:** CLAUDE.md §Log prefixes + multiple call sites in `main.py` (lines 456, 459, 643, 656, 370–378).
**Apply to:** ALL new Phase 7 log lines.

**Excerpt — current `[Sched]` usage in main.py:**

```python
# main.py:456 (opening run-line)
logger.info('[Sched] Run %s mode=%s', run_date_display, _mode_label(args))

# main.py:459 (deprecated stub — DELETE in Phase 7)
logger.info('[Sched] One-shot mode (scheduler wiring lands in Phase 7)')

# main.py:643 (test-mode skip)
logger.info('[Sched] --test mode: skipping save_state (state.json unchanged)')

# main.py:370–378 (run-summary footer)
log.info(
  '[Sched] Run %s AWST done in %.1fs — '
  'instruments=%d, trades_recorded=%d, warnings=%d, state_saved=%s',
  ...
)
```

**Phase 7 new `[Sched]` log lines (full inventory):**

```python
# Weekday gate (inside run_daily_check, after _compute_run_date)
logger.info(
  '[Sched] weekend skip %s (weekday=%d) — no fetch, no state mutation',
  run_date.strftime('%Y-%m-%d'), run_date.weekday(),
)

# _run_daily_check_caught — typed exception branch
logger.warning('[Sched] data-layer failure caught in loop: %s', e)

# _run_daily_check_caught — catch-all branch
logger.warning(
  '[Sched] unexpected error caught in loop: %s: %s (loop continues)',
  type(e).__name__, e,
)

# _run_daily_check_caught — non-zero rc branch
logger.warning('[Sched] daily check returned rc=%d (loop continues)', rc)

# _run_schedule_loop — scheduler entry (NEW line, replaces the deprecated one-shot stub)
logger.info('[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon–Fri')
```

**Why this matters for Phase 7:** log prefix discipline is the project's primary observability mechanism — `caplog`-based tests (e.g., `TestDefaultModeDispatch`) assert on exact `[Sched]` strings. A typo (`[sched]`, `[Scheduler]`, `[SCHED]`) breaks tests AND operator grep muscle memory.

**Grep commands:**

```bash
grep -n "'\\[Sched\\]" main.py                   # all existing [Sched] sites (discipline check)
grep -n "\\[Fetch\\]\\|\\[Signal\\]\\|\\[State\\]\\|\\[Email\\]\\|\\[Dashboard\\]" main.py  # all prefixes
```

---

### Pattern D — Atomic operation + graceful-on-fail posture

**Source:** `state_manager.py::save_state` (Phase 3 atomic tempfile+fsync+os.replace); `main.py::_render_dashboard_never_crash` (wraps disk write in try/except).
**Apply to:** GHA workflow `if: success()` guard on the commit step (D-11).

**Analogous excerpt — Phase 3 atomic write (state_manager.py, paraphrased):**

```python
# state_manager.py (paraphrased)
def save_state(state: dict, path: Path = Path('state.json')) -> None:
  '''Atomic write: tempfile + fsync + os.replace. If any step raises, the
  on-disk state.json is UNCHANGED (no partial write possible).
  '''
  tmp = path.with_suffix('.tmp')
  with tmp.open('w') as fh:
    json.dump(state, fh, ...)
    fh.flush()
    os.fsync(fh.fileno())
  os.replace(tmp, path)   # atomic rename
```

**Phase 7 GHA-level analog (from RESEARCH §Example 5):**

```yaml
- uses: stefanzweifel/git-auto-commit-action@v5
  if: success()   # D-11: no commit on fail — mirror of "no partial write" discipline
  with:
    commit_message: 'chore(state): daily signal update [skip ci]'
    file_pattern: state.json
    add_options: '-f'   # Pitfall 2 mitigation
```

**Why this matters for Phase 7:** the `if: success()` clause is the CI-tier analog of Phase 3's in-process atomic write. If `python main.py --once` exits non-zero, the commit step does NOT fire, so `state.json` in the repo stays at yesterday's value — no half-written state ever reaches git history. `save_state` is already structurally atomic in-process; the workflow extends the same discipline across process boundaries.

---

## No Analog Found

Files with no close match in the codebase (planner + executor should use RESEARCH.md patterns instead):

| File | Role | Data Flow | Why no analog |
|------|------|-----------|---------------|
| `.github/workflows/daily.yml` | CI/CD workflow | event-driven | First GHA workflow in repo; no prior YAML to mirror. Full contract at RESEARCH §Example 5. |
| `docs/DEPLOY.md` | documentation | docs | No `docs/` directory exists yet; closest content precedent is SPEC.md footer §REPLIT SETUP INSTRUCTIONS (lines 333–353), but the content is stale (old env-var names, old cron). Shape-only match. |
| `README.md` | documentation | docs | First README; CLAUDE.md header is a content seed but not a README analog (CLAUDE.md is a different document genre). |

**Pattern C + Pattern B (log prefix + injected-collaborator) compensate:** the Python code sits entirely in `main.py` / `system_params.py` / `tests/` and has strong in-repo analogs. The three "no analog" files are project-level deliverables (CI config + operator docs) that ship at Phase 7 and establish their own future precedents.

---

## Metadata

**Analog search scope:** `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/` — main.py, system_params.py, notifier.py, dashboard.py, state_manager.py, data_fetcher.py, tests/*.py, SPEC.md, CLAUDE.md, .env.example, .gitignore, .python-version, requirements.txt, .planning/ROADMAP.md, .planning/phases/07-scheduler-github-actions-deployment/*.
**Files scanned:** 15 top-level files + 1 RESEARCH.md + 1 CONTEXT.md.
**Pattern extraction date:** 2026-04-23.
**Analogs cited with line numbers:**
- `main.py:97–115` — `_render_dashboard_never_crash`
- `main.py:122–146` — `_send_email_never_crash`
- `main.py:199–207` — `_compute_run_date` (AWST clock reader — weekday gate consumes directly)
- `main.py:385–676` — `run_daily_check` (weekday gate inserts at top after line 452)
- `main.py:452, 459` — existing `[Sched] Run` + deprecated one-shot stub (DELETE line 459)
- `main.py:721–788` — `main()` dispatch ladder (amend default branch at line 779)
- `system_params.py:70–77` — Phase 3 constants block (analog shape for Phase 7 additions)
- `notifier.py:1076–1153` — `_post_to_resend` (parameter-default testability pattern)
- `tests/test_main.py:104–148` — stale-assertion update targets (lines 129, 146)
- `tests/test_main.py:82–90, 418, 428–454` — monkeypatch + freezer idioms for test_scheduler.py
- `tests/test_signal_engine.py:556–563, 572–579` — `FORBIDDEN_MODULES_DASHBOARD/NOTIFIER` (AST blocklist extension)
- `tests/test_signal_engine.py:488–497, 507–518, 525–534, 544–549` — other FORBIDDEN blocklists (verification only — no changes)
- `tests/test_signal_engine.py:753–854` — `test_forbidden_imports_absent` test methods (unchanged; read the frozensets)
- `.env.example:1–9` — Phase 6 placeholder header (amend in Phase 7)
- `.gitignore:1–9` — confirms `state.json` is gitignored (triggers Pitfall 2 `add_options: '-f'` fix)
- `.python-version:1` — `3.11.8` (consumed by `setup-python@v5 python-version-file`)
- `SPEC.md:333–353` — §REPLIT SETUP INSTRUCTIONS (loose shape precedent for docs/DEPLOY.md)
- `.planning/ROADMAP.md:138` — SC-4 bullet (drop `ANTHROPIC_API_KEY`)
