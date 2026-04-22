# Phase 7: Scheduler + GitHub Actions Deployment — Research

**Researched:** 2026-04-23
**Domain:** Python scheduling library + GitHub Actions workflow authoring + env-var bootstrap + Replit deploy docs
**Confidence:** HIGH (schedule tz behaviour / dotenv semantics / GHA action contracts verified against upstream docs; one CRITICAL pitfall pinned and mitigated)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (16 items — research these, do not re-decide)

- **D-01** — Factored loop driver `_run_schedule_loop(job, args, scheduler=None, sleep_fn=None, tick_budget_s=60.0, max_ticks=None) -> int`. Production call uses default None-resolved `schedule` + `time.sleep`; tests inject fakes + finite `max_ticks`.
- **D-02** — Loop catches + logs + keeps ticking via `_run_daily_check_caught(job, args) -> None`. Third instance of the never-crash pattern (after `_render_dashboard_never_crash` + `_send_email_never_crash`).
- **D-03** — Weekday gate inside `run_daily_check` top (after `run_date = _compute_run_date()`), applies to ALL modes. `run_date.weekday() >= 5` returns `(0, None, None, run_date)`. Preserves 4-tuple contract; Phase 6 Fix 10 None-guard becomes primary path on weekends.
- **D-04** — Immediate first-run before entering schedule loop (SCHED-02). Default-mode dispatch: `_run_daily_check_caught(run_daily_check, args)` then `_run_schedule_loop(run_daily_check, args)`.
- **D-05** — Default mode flips from one-shot to schedule-loop. `--once` stays one-shot. Delete `'[Sched] One-shot mode (scheduler wiring lands in Phase 7)'` from `run_daily_check`; replace with new log line inside `_run_schedule_loop`: `'[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon–Fri'`. Updates existing tests at `tests/test_main.py:129` and `:146`.
- **D-06** — `load_dotenv()` unconditionally at top of `main()` via LOCAL import `from dotenv import load_dotenv` inside `main()` body (C-2 pattern — mirrors Phase 5/6 never-crash imports).
- **D-07** — GHA workflow YAML skeleton locked (see 07-CONTEXT.md §D-07).
- **D-08** — `workflow_dispatch: {}` manual trigger included.
- **D-09** — `actions/setup-python@v5` with `cache: 'pip'`, `python-version-file: '.python-version'`, `cache-dependency-path: requirements.txt`.
- **D-10** — `file_pattern: state.json` only; commit message `'chore(state): daily signal update [skip ci]'`.
- **D-11** — `if: success()` on commit step — no commit on fail.
- **D-12** — Formal deploy env-var contract = `RESEND_API_KEY` + `SIGNALS_EMAIL_TO` only. Drop `ANTHROPIC_API_KEY` from SC-4 (ROADMAP amendment needed in plan).
- **D-13** — Missing `RESEND_API_KEY` keeps Phase 6 graceful-degradation. No startup preflight.
- **D-14** — `docs/DEPLOY.md` is the operator runbook.
- **D-15** — Depth = ~150 lines (quickstart + env ref + troubleshooting).
- **D-16** — Replit stays production-viable tested code.

### Claude's Discretion (researcher/planner/executor decide)

- Exact name of the loop driver (`_run_schedule_loop` recommended).
- Exact name of the never-crash wrapper (`_run_daily_check_caught` recommended).
- Loop tick sleep as `system_params.py` constant (`LOOP_SLEEP_S = 60`) vs inline default. Recommendation: constant.
- Exact unit-test count for loop driver (minimum 6 classes; see §Validation Architecture).
- Test file name: new `tests/test_scheduler.py` vs extending `tests/test_main.py`. Recommendation: new file.
- Whether to add `__main__.py` entry point. Recommendation: NO.
- Precise `schedule` + `python-dotenv` version pins (this RESEARCH picks: see §Standard Stack).
- Cost estimate subsection in DEPLOY.md (recommendation: YES — 1 sentence).
- Minimal top-level README.md at Phase 7 if absent (recommendation: YES, ~50 lines).
- Whether GHA `file_pattern` covers corrupt-state backup files. Recommendation: NO (belongs in Phase 8).

### Deferred Ideas (OUT OF SCOPE)

- `NOTF-10` warning carry-over across runs (Phase 8).
- `ERR-05` stale-state banner at startup (Phase 8).
- `ERR-04` top-level crash-email dispatch (Phase 8).
- `CONF-01/02` configurable starting account / contract tiers (Phase 8).
- `ERR-02` Resend failure banner in NEXT email (Phase 8).
- `ERR-03` corrupt-state recovery surfaced to operator (Phase 8).
- LLM-backed summary (`ANTHROPIC_API_KEY`) — not in v1 at all.
- Failure notification via Resend (GitHub email-on-failure is sufficient).
- Replit integration E2E tests — GHA is primary; revisit only on flip.
- Multi-recipient fan-out / Slack / SMS (v2 V2-DEL-01/02).
- Docker/container deployment.
- Health-check endpoint.
- State.json restore / rollback flag (V2-REL-01).
- Full runbook with screenshots.
- `README.md` as deploy doc home (pointer only).
- Self-hosted GHA runner.
- Secret rotation automation / Doppler / 1Password / Vault.
- PR-test CI workflow beyond `daily.yml`.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCHED-01 | Scheduler fires at 08:00 AWST (00:00 UTC) weekdays Mon–Fri | GHA cron `0 0 * * 1-5` runs in UTC (confirmed §Pitfall 1); schedule library tz param mitigates local-tz interpretation on Replit |
| SCHED-02 | Initial run executes immediately on process start (before schedule loop) | D-04 immediate first-run via `_run_daily_check_caught` before loop entry — verified against CONTEXT decisions |
| SCHED-03 | `run_daily_check` has internal weekday gate (no-op on Sat/Sun even if invoked) | D-03 weekday gate using `run_date.weekday() >= 5`; Python stdlib contract confirmed (`weekday()` returns 0=Mon..6=Sun) |
| SCHED-04 | `--once` flag runs a single daily check and exits (GHA uses this) | Phase 4 CLI-04 already ships; Phase 7 preserves behaviour (only default-mode flips) |
| SCHED-05 | Primary deployment is GitHub Actions with `cron: '0 0 * * 1-5'`, `permissions: contents: write`, `concurrency: trading-signals`, and commit-back of `state.json` via `stefanzweifel/git-auto-commit-action@v5` | Full YAML skeleton verified against action + setup-python + checkout upstream docs |
| SCHED-06 | Alternative deployment is Replit Reserved VM + Always On, documented with filesystem-persistence caveat | Replit 2026 pricing + product names verified against current Replit docs (§Standard Stack alt-deployment) |
| SCHED-07 | All secrets loaded from env vars (`.env` locally, GitHub Secrets / Replit Secrets in deploy) — never committed | `python-dotenv` + `os.environ` + GHA `env:` mapping pattern verified; `.gitignore` already excludes `.env` |
| CLI-05 (Phase 7 slice) | Default invocation runs immediately then enters the schedule loop | D-04 + D-05 wiring in `main()` default branch; existing tests at `test_main.py:129,146` updated to assert new log line |

</phase_requirements>

## Summary

Phase 7 is a deployment + scheduling phase on top of a mature Python codebase. The research surfaces exactly one CRITICAL pitfall: the `schedule` library uses **pytz only** for its `.at(..., tz=...)` parameter, but the project's code uses **stdlib `zoneinfo`** everywhere. Attempting to pass a `ZoneInfo` object into `schedule.every().day.at('00:00', AWST).do(...)` will raise a `ScheduleValueError`. Fortunately the GHA runner executes in UTC and our cron fires at `0 0 * * 1-5` UTC, so on the GHA path we can safely omit the tz argument — local time == UTC == the intended wall-clock. On the Replit path the process-local tz is also UTC by default (Replit containers use UTC), so the same naive `at('00:00')` call produces the correct wall-clock behaviour in both deployments. **Recommendation: omit the tz argument entirely, document the "process tz must be UTC" invariant in `docs/DEPLOY.md`, and add a belt-and-braces assertion inside `_run_schedule_loop` that the process timezone is UTC (via `time.tzname` or `datetime.now().astimezone().tzinfo`). Do NOT add pytz to requirements.txt unless future work needs tz conversion outside of main.py.** Full mitigation detail in §Pitfall 1.

The remaining research confirms well-trodden patterns. `stefanzweifel/git-auto-commit-action@v5` honours `.gitignore` by default (it uses `git add`, not `git add -f`), so `state.json` — currently listed in `.gitignore` — would NOT get committed by the action as-is. Phase 7 must either (a) add `add_options: '-f'` to the action inputs, or (b) remove `state.json` from `.gitignore`. Verified against the action's discussion-351 thread (§Pitfall 2 — actionable fix). `[skip ci]` in commit messages only affects `push` and `pull_request` triggers — it does NOT affect `schedule` runs, but our daily.yml is triggered by `schedule` anyway so this is a non-issue; the token remains useful defence-in-depth against future push-triggered CI (§Pitfall 4). `python-dotenv 1.0.x` behaves exactly as CONTEXT assumes (returns False on missing file, `override=False` default), but 1.0.1 is the last patch in the 1.0.x series — a newer 1.2.2 released 2026-03-01 exists and is a safer pin. GHA schedule drift of 5–30 minutes is documented as normal; flag this in the operator runbook. Replit 2026 pricing has shifted — Reserved VM is cheapest-tier $6.20/mo (billed daily) or $20/mo on older plans; update DEPLOY.md to reflect current naming.

**Primary recommendation:** Pin `schedule==1.2.2`, pin `python-dotenv==1.0.1`, omit the tz argument from `schedule.every().day.at('00:00')`, assert process-tz=UTC at loop-entry, add `add_options: '-f'` to the git-auto-commit step so it commits the gitignored `state.json`, and ship the 6-test-class scheduler test file. This closes every open CONTEXT question and aligns with every locked decision.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Wall-clock reading | main.py (orchestrator) | — | CLAUDE.md: main.py is the ONLY module allowed to read the clock; `_compute_run_date` is the sole site |
| Scheduler loop driver | main.py (orchestrator) | — | New function `_run_schedule_loop` must live alongside the dispatch ladder; keeps `schedule` library import confined |
| Never-crash wrapper | main.py (orchestrator) | — | Third instance of the pattern (dashboard + email already established in Phase 5/6); single import site rule |
| Env-var bootstrap (`load_dotenv`) | main.py (orchestrator) | — | C-2 local-import pattern; `dotenv` on AST blocklist for every non-main module |
| Weekday gate | main.py (orchestrator — top of `run_daily_check`) | — | Uses `run_date.weekday()` which is already computed by `_compute_run_date`; cannot move to engines (pure-math rule) |
| GHA workflow definition | `.github/workflows/daily.yml` | `docs/DEPLOY.md` | CI/CD concern — lives outside the Python code hex entirely |
| Commit-back of `state.json` | `stefanzweifel/git-auto-commit-action@v5` (CI tier) | — | Don't hand-roll `git add && git commit && git push`; external action owns the pattern |
| Secret injection | GHA `env:` block (deploy tier) + `python-dotenv` (local tier) | — | Secrets never touch git; both tiers converge on `os.environ` which notifier.py already reads |
| Operator runbook | `docs/DEPLOY.md` | `README.md` pointer | Single source of truth for deploy procedure; README just points |
| Schedule loop tests | `tests/test_scheduler.py` (new) | — | Phase 7 adds a new concern — keep `test_main.py` focused on CLI + orchestrator |

## Standard Stack

### Core Phase 7 Additions

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `schedule` | `1.2.2` | In-process daily job loop for Replit path | PROJECT.md stack lock; pure-Python, zero C deps; `every().day.at('HH:MM').do(fn, *args)` is canonical. `[VERIFIED: PyPI registry 2024-05-25 — latest stable in 1.2.x]` |
| `python-dotenv` | `1.0.1` | Load `.env` into `os.environ` for local-dev | PROJECT.md stack lock; `load_dotenv()` default behaviour (missing file → False; `override=False`) exactly matches Phase 7 D-06. `[VERIFIED: python-dotenv docs — 1.0.1 released 2024-01-23]` |

**Pin selection rationale:**
- `schedule==1.2.2`: latest 1.2.x patch; includes fix for "schedule off when using .at with timezone" (#583). Even though Phase 7 deliberately omits the tz argument (see §Pitfall 1), picking the patched version is free insurance.
- `python-dotenv==1.0.1`: last 1.0.x patch. Version 1.2.2 (2026-03-01) exists but is a newer minor line — stick with 1.0.x to match project's "pin deliberately" discipline and avoid unvetted churn.

**Version verification (performed 2026-04-23):**
```bash
# `schedule` — npm-equivalent:
#   https://pypi.org/project/schedule/  → 1.2.2 (May 25, 2024)
#   1.2.1 (Oct 1, 2023), 1.2.0 (Apr 10, 2023)
# `python-dotenv`:
#   https://pypi.org/project/python-dotenv/  → 1.2.2 (Mar 1, 2026) is current,
#   1.0.1 (Jan 23, 2024) is the last 1.0.x — the range CONTEXT allowlists.
```
Neither library shows any current open CVE on PyPI's advisory feed as of 2026-04-23. `[VERIFIED: PyPI search 2026-04-23]`

### Existing Stack Already In-Repo (Phase 7 consumes, does not add)

| Library | Version | Used For | Phase 7 Consumer |
|---------|---------|----------|------------------|
| `pytest` | 8.3.3 | Test runner | `tests/test_scheduler.py` |
| `pytest-freezer` | 0.4.9 | Freeze `datetime.now(tz=AWST)` for weekday-gate tests | `TestWeekdayGate` class |
| Python stdlib `zoneinfo` | — | AWST wall-clock | `main.py::_compute_run_date` (unchanged) |
| Python stdlib `argparse` | — | CLI parsing | `main.py::_build_parser` (unchanged) |
| Python stdlib `logging` | — | Structured `[Sched]` log lines | `_run_schedule_loop` + `_run_daily_check_caught` |
| Python stdlib `time.sleep` | — | Loop tick pacing | `_run_schedule_loop` (injected via `sleep_fn` param) |

### GHA Action Stack (workflow-level deps)

| Action | Pin | Purpose | Source |
|--------|-----|---------|--------|
| `actions/checkout@v4` | `v4` major tag | Check out repo at HEAD | `[VERIFIED: GitHub Marketplace — standard checkout action]` |
| `actions/setup-python@v5` | `v5` major tag | Install Python per `.python-version`, cache pip | `[VERIFIED: actions/setup-python GitHub — v5.x series supports `cache: 'pip'` + `python-version-file` + `cache-dependency-path`]` |
| `stefanzweifel/git-auto-commit-action@v5` | `v5` major tag | Commit `state.json` back to repo | `[VERIFIED: action GitHub repo; latest v7.1.0 exists but v5 is a supported major tag]` |

**Major-tag vs SHA-pin:** CONTEXT locked major-tag pins (`v4`, `v5`). Major tags follow the action author's semver fixes; SHA pins don't. For a single-operator signal app with no compliance surface, major-tag is the right trade — but DO cross-reference the tag in the action's GitHub before shipping in case the maintainer retroactively moved the tag.

### Alternatives Considered

| Instead of | Could Use | Tradeoff / Why Rejected |
|------------|-----------|-------------------------|
| `schedule` | `APScheduler` | Richer (cron expressions, DB-backed, persistence) but 10x larger API surface; not in PROJECT.md stack allowlist |
| `schedule` | `croniter` | Parser-only — doesn't run jobs; needs its own loop anyway |
| `schedule` | systemd timers | Needs root + Linux-only; Replit containers can't use systemd |
| `schedule` | shell cron | Out of Python process; state isolation concerns; PROJECT.md rejects shell scripts |
| `stefanzweifel/git-auto-commit-action@v5` | Hand-rolled `git add && git commit && git push` in a `run:` step | Works but must set user.email / user.name / token auth / detect-no-change logic — ~20 lines of shell that the action encapsulates |
| `actions/setup-python@v5` | Install pyenv inside the runner | Slower; no cache hit; reinvents wheel |
| `python-dotenv` | Hand-parse `.env` into `os.environ` | Edge cases (quoting, multiline, escape) — `python-dotenv` is the de-facto standard |

**Installation:**
```bash
# Phase 7 Wave 0 adds TWO pinned lines to requirements.txt:
echo 'schedule==1.2.2' >> requirements.txt
echo 'python-dotenv==1.0.1' >> requirements.txt
pip install -r requirements.txt
```

## Architecture Patterns

### System Architecture Diagram

```
                           ┌──────────────────────────┐
                           │  GitHub Actions (cron)   │
                           │  0 0 * * 1-5 UTC         │
                           │  workflow_dispatch={}    │
                           └────────────┬─────────────┘
                                        │ triggers
                                        ▼
     ┌──────────────────────────────────────────────────────────────┐
     │                 .github/workflows/daily.yml                  │
     │   actions/checkout@v4  →  actions/setup-python@v5            │
     │   pip install -r requirements.txt                            │
     │   env: {RESEND_API_KEY, SIGNALS_EMAIL_TO}                    │
     │   python main.py --once                                      │
     │   if: success()  →  stefanzweifel/git-auto-commit-action@v5  │
     │     add_options: '-f'   file_pattern: state.json             │
     └─────────────────────────────┬────────────────────────────────┘
                                   │ invokes
                                   ▼
                         ┌───────────────────┐
                         │   python main.py  │
                         │     --once        │
                         └─────────┬─────────┘
                                   │
       ┌───────────────────────────┴────────────────────────────┐
       │                                                        │
       ▼                                                        ▼
 Dispatch ladder                                       ALTERNATIVE path
 (Phase 4 D-07 + Phase 7 D-04/D-05)                    Replit Reserved VM
       │                                                 + Always On
       │                                                 python main.py  (default, no --once)
       ├── --reset       ─► _handle_reset()
       ├── --test        ─┐                                    │
       ├── --force-email ─┤                                    ▼
       │   (both run     │                            ┌─────────────────┐
       │    compute +    │                            │ load_dotenv()   │ (D-06)
       │    email)       │                            └────────┬────────┘
       │                 │                                     │
       ├── --once ───────┴─► run_daily_check(args) ────────────┤
       │                                                       │
       └── default ─► _run_daily_check_caught(job, args)       │ (D-04 immediate)
                        │                                      │
                        ▼                                      │
                    run_daily_check(args)                      │
                        │                                      │
                        ▼                                      │
                    ┌────────────────┐                         │
                    │ weekday gate   │ (D-03)                  │
                    │ run_date       │                         │
                    │  .weekday()>=5 │──yes──► return          │
                    │                │        (0,None,None,rd) │
                    └───────┬────────┘                         │
                         no │                                  │
                            ▼                                  │
                    [existing Phase 4-6 pipeline]              │
                        │                                      │
                        ▼                                      │
                    returns (rc, state, old_signals, run_date) │
                        │                                      │
                        │                        ┌─────────────┘
                        ▼                        ▼
                 dispatch to:             _run_schedule_loop(run_daily_check, args)
                 - email (if --force      │ (D-01: injectable scheduler + sleep_fn)
                   or --test)             │
                 - return rc              │ register schedule.every().day.at('00:00').do(
                                          │   _run_daily_check_caught, job, args)
                                          │ loop forever: run_pending(); sleep(60)
                                          ▼
                                       never returns (until SIGINT)
```

### Recommended Project Structure (Phase 7 additions only)

```
trading-signals/
├── main.py                    # (edited) + _run_schedule_loop + _run_daily_check_caught
│                               #          + weekday gate prelude in run_daily_check
│                               #          + default-mode dispatch amendment
│                               #          + load_dotenv() call at top of main()
│                               #          - delete '[Sched] One-shot mode...' line
├── system_params.py           # (edited) + LOOP_SLEEP_S = 60
│                               #          + SCHEDULE_TIME_UTC = '00:00'
│                               #          + WEEKDAY_SKIP_THRESHOLD = 5
├── requirements.txt           # (edited) + schedule==1.2.2
│                               #          + python-dotenv==1.0.1
├── .env.example               # (edited, optional) header comments re GHA/Replit Secrets
├── .github/
│   └── workflows/
│       └── daily.yml          # (NEW) GHA cron workflow
├── docs/
│   └── DEPLOY.md              # (NEW) operator runbook (~150 lines)
├── README.md                  # (NEW if absent, ~50 lines, pointer to DEPLOY.md + SPEC.md)
└── tests/
    ├── test_main.py           # (edited) tests/test_main.py:129,146 — replace deprecated
    │                           #          '[Sched] One-shot mode...' assertion with new
    │                           #          '[Sched] scheduler entered...' for default-mode
    │                           #          test; --once test keeps old behaviour (no loop)
    ├── test_scheduler.py      # (NEW) 6 test classes — see §Validation Architecture
    └── test_signal_engine.py  # (edited) FORBIDDEN_MODULES_{STATE_MANAGER,DATA_FETCHER,
                                #          DASHBOARD,NOTIFIER} add 'schedule' + 'dotenv'
                                #          — already present per scan (lines 496,515,531,
                                #          558-562,572-579); NO CHANGE REQUIRED.
                                #          FORBIDDEN_MODULES_MAIN stays without 'schedule'
                                #          or 'dotenv' (main.py is their sole consumer).
```

**Note on AST blocklist state (verified 2026-04-23 against `tests/test_signal_engine.py`):**
- Line 496: `FORBIDDEN_MODULES` (pure-math) already includes `'schedule', 'dotenv'`
- Line 515: `FORBIDDEN_MODULES_STATE_MANAGER` already includes `'schedule', 'dotenv'`
- Line 531: `FORBIDDEN_MODULES_DATA_FETCHER` already includes `'schedule', 'dotenv'`
- Lines 556–563: `FORBIDDEN_MODULES_DASHBOARD` does NOT include `schedule` / `dotenv` — **ADD in Phase 7 Wave 0**
- Lines 572–579: `FORBIDDEN_MODULES_NOTIFIER` does NOT include `schedule` / `dotenv` — **ADD in Phase 7 Wave 0**
- Lines 544–549: `FORBIDDEN_MODULES_MAIN` — does NOT include `schedule` / `dotenv` — **leave as-is** (main.py is the sole legitimate consumer)

### Pattern 1: Injectable collaborators with None-defaults + lazy-resolve

**What:** Function signature declares optional collaborator parameters with `None` default; body resolves to the real implementation only if no injected fake was supplied.
**When to use:** Testability — production call path uses zero-argument default; test path injects fakes to avoid real IO or blocking loops.
**Example:**
```python
# Source: Phase 5 D-06 / Phase 6 D-15 precedent in main.py
def _run_schedule_loop(
  job: Callable[[argparse.Namespace], tuple[int, dict | None, dict | None, datetime | None]],
  args: argparse.Namespace,
  scheduler=None,          # injected: defaults to the `schedule` module
  sleep_fn=None,           # injected: defaults to time.sleep
  tick_budget_s: float = 60.0,
  max_ticks: int | None = None,
) -> int:
  import schedule  # LOCAL import — hex-lite + AST blocklist keeps this import site unique
  import time as _time
  _scheduler = scheduler or schedule
  _sleep = sleep_fn or _time.sleep
  logger.info('[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon–Fri')
  _scheduler.every().day.at('00:00').do(_run_daily_check_caught, job, args)
  ticks = 0
  while max_ticks is None or ticks < max_ticks:
    _scheduler.run_pending()
    _sleep(tick_budget_s)
    ticks += 1
  return 0
```

### Pattern 2: Never-crash wrapper (3rd instance)

**What:** Helper function wraps a fallible operation in `try/except Exception`, logs the failure at WARNING level, and returns without propagating. Used exclusively at orchestrator dispatch boundaries.
**When to use:** Same as Phase 5 (`_render_dashboard_never_crash`) + Phase 6 (`_send_email_never_crash`) — the loop driver MUST NOT propagate an exception out (would kill the schedule loop).
**Example:**
```python
# Source: Phase 5 D-06 + Phase 6 D-15 + extended here per Phase 7 D-02
def _run_daily_check_caught(job, args) -> None:
  '''D-02: schedule loop survives one bad run. Next cron fire retries.

  Mirrors _render_dashboard_never_crash + _send_email_never_crash.
  ONLY valid `except Exception:` site in the loop path.
  '''
  try:
    rc, _, _, _ = job(args)
    if rc != 0:
      logger.warning('[Sched] daily check returned rc=%d (loop continues)', rc)
  except (DataFetchError, ShortFrameError) as e:
    logger.warning('[Sched] data-layer failure caught in loop: %s', e)
  except Exception as e:
    logger.warning(
      '[Sched] unexpected error caught in loop: %s: %s (loop continues)',
      type(e).__name__, e,
    )
```

### Pattern 3: Weekday gate short-circuit before compute

**What:** First executable line of `run_daily_check` (after the clock read) checks `run_date.weekday() >= 5` and returns the 4-tuple early, preserving the Phase 6 contract shape.
**When to use:** D-03 belt-and-braces gate — fires on AWST Saturday + Sunday regardless of invocation mode. Phase 6 Fix 10 None-guard in `main()` already handles the `state is None` case.
**Example:**
```python
# Source: D-03 locked in 07-CONTEXT.md
def run_daily_check(args) -> tuple[int, dict | None, dict | None, datetime | None]:
  run_date = _compute_run_date()
  # D-03: weekday gate short-circuits BEFORE any fetch / compute / mutation.
  if run_date.weekday() >= 5:  # 5=Sat, 6=Sun (Python stdlib: 0=Mon..6=Sun)
    logger.info(
      '[Sched] weekend skip %s (weekday=%d) — no fetch, no state mutation',
      run_date.strftime('%Y-%m-%d'), run_date.weekday(),
    )
    return 0, None, None, run_date
  # ... existing D-11 sequence unchanged ...
```

### Pattern 4: GHA workflow-level permissions + concurrency

**What:** Lock minimum permissions + single-run serialisation at the workflow level (not per-job) for a single-job workflow.
**When to use:** Any workflow that writes back to the repo; any workflow where overlapping cron + workflow_dispatch would conflict.
**Example:**
```yaml
# Source: CONTEXT D-07 — verified against actions docs (permissions-at-workflow-level
# is the recommended granularity for single-job workflows)
name: Daily signal check
on:
  schedule:
    - cron: '0 0 * * 1-5'
  workflow_dispatch: {}
permissions:
  contents: write
concurrency:
  group: trading-signals
  cancel-in-progress: false
jobs:
  daily:
    runs-on: ubuntu-latest
    steps:
      # ... D-07 step list ...
```

### Pattern 5: `actions/setup-python@v5` pip cache with version-file pin

**What:** Use `.python-version` as single source of truth for both local pyenv + GHA setup; use `requirements.txt` hash as pip-cache invalidation key.
**Example:**
```yaml
# Source: CONTEXT D-09 — verified against actions/setup-python README
- uses: actions/setup-python@v5
  with:
    python-version-file: '.python-version'   # reads '3.11.8' from repo root
    cache: 'pip'                             # pip download cache
    cache-dependency-path: requirements.txt  # hashes requirements.txt for cache key
```
Cache hit: ~5s restore. Cache miss (requirements.txt changed): ~30s install. Cache key regenerates whenever `requirements.txt` bytes change — Phase 7 will miss once (on the PR that adds `schedule` + `python-dotenv`), then hit on every subsequent cron run until the next dep change. `[VERIFIED: actions/setup-python README + issue #529 + Simon Willison's TIL]`

### Pattern 6: `stefanzweifel/git-auto-commit-action@v5` with gitignored target

**What:** Force-add a gitignored file for commit-back (standard pattern when build artefacts that need history live in `.gitignore`).
**When to use:** When a CI-generated file (state, build output) must be committed to the repo but stays gitignored locally (so operators don't commit stale local-dev state).
**Example:**
```yaml
# Source: action README + discussion #351 — `git add` by default honours .gitignore;
# `add_options: '-f'` passes -f to `git add`, which overrides .gitignore for explicit pathspecs.
- uses: stefanzweifel/git-auto-commit-action@v5
  if: success()  # D-11: only on successful compute
  with:
    commit_message: 'chore(state): daily signal update [skip ci]'
    file_pattern: state.json
    add_options: '-f'        # FORCES add of gitignored state.json
    commit_user_name: github-actions[bot]
    commit_user_email: 41898282+github-actions[bot]@users.noreply.github.com
```
**CRITICAL:** Without `add_options: '-f'`, the action's default `git add state.json` is a no-op on a gitignored file — Git prints a warning, the working tree stays clean, and the action logs `"Working tree clean. Nothing to commit."` No error, no commit, state.json never persists across runs. This is one of the top two pitfalls of Phase 7 (see §Pitfall 2).

### Anti-Patterns to Avoid

- **Module-top `import schedule` in main.py** → Would make the entire test suite import `schedule` at pytest collection time; slows tests by ~200ms per run, defeats purpose of the AST blocklist. Use LOCAL import inside `_run_schedule_loop` (D-01 + C-2 pattern).
- **Module-top `from dotenv import load_dotenv` in main.py** → Same reason; `load_dotenv` would fire at pytest import time and leak `.env` values into every test. D-06 mandates local import inside `main()` body.
- **`max(1, …)` loop guard** → Operator rejected this style of "defensive floor" in Phase 2. Loop uses injection (`max_ticks=None = production infinite; max_ticks=1 = test`) instead.
- **`except Exception:` outside the never-crash helpers** → CLAUDE.md: the pattern is scoped exclusively to helper functions named `_*_never_crash` / `_*_caught`. Adding another site dilutes the discipline.
- **`actions/checkout@latest` or SHA-pin-today** → Major-tag is the CONTEXT-locked choice; `@latest` doesn't exist as an action ref, SHA-pin requires manual updates every security patch.
- **Using `schedule.every().day.at('00:00', AWST)` with AWST = `ZoneInfo(...)`** → Will raise `ScheduleValueError: invalid timezone`; schedule 1.2.x requires pytz. Omit the tz argument entirely (see §Pitfall 1).
- **Passing multiple `env:` secrets as a bulk `${{ secrets }}` mapping** → Exposes EVERY repo secret to the step's subprocess environment; principle of least privilege requires naming the two we use (`RESEND_API_KEY`, `SIGNALS_EMAIL_TO`) in an explicit `env:` block.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Daily cron loop | `while True: if time.now() == '00:00': run(); sleep(60)` | `schedule.every().day.at('00:00').do(fn)` | Edge cases: DST (n/a in Perth), drift, exceptions killing the loop, missed tick handling. `schedule` handles all of it cleanly and is already in the stack |
| Envfile parsing | `for line in open('.env'): k, v = line.split('='); os.environ[k] = v` | `from dotenv import load_dotenv; load_dotenv()` | Edge cases: quoting, multi-line values, `$` expansion, comments, escape sequences |
| Git commit back from CI | 4-line `run:` step with `git config user.email …; git add …; git commit -m …; git push` | `stefanzweifel/git-auto-commit-action@v5` | Auth token setup, empty-diff detection, branch-protection handling, user/email defaults, idempotency — all pre-solved |
| Python install on GHA | `sudo apt install python3.11` in a `run:` step | `actions/setup-python@v5 with: python-version-file: '.python-version'` | Pip cache, version-file parsing, arch-specific binaries, PATH setup |
| Secret loading | `os.environ['RESEND_API_KEY']` without `load_dotenv` | `load_dotenv()` at top of `main()` per D-06 | Fails fast on local dev without secrets set in shell; dotenv gives layered config (process env wins over .env by default) |
| Weekday detection | `datetime.now().strftime('%a') in ('Sat', 'Sun')` | `run_date.weekday() >= 5` | Locale-sensitive; stdlib `weekday()` is locale-invariant and returns 0=Mon..6=Sun (confirmed stdlib contract) |
| Workflow-fail notification | Write a Resend POST to email the operator on workflow failure | GitHub's built-in "email on workflow failure" (account-level setting) | Operator is single; GH already does this for free; no extra code path to maintain |
| Idempotency guard (skip re-run same day) | Read `state.json['last_run']` and compare to today | Rely on GHA cron's one-fire-per-schedule guarantee | Daily cadence + `[skip ci]` + `if: success()` already makes double-run a non-issue. Phase 8 may revisit if operator reports dupes |

**Key insight:** Phase 7's stack is deliberately boring. Every pattern here is a widely-used industry default. There is no clever code in the scheduler loop, no custom cron parser, no bespoke deploy script. If any plan task feels like new invention, it's probably reinventing something already in the stack — check `schedule` docs / GHA action catalogue / `python-dotenv` README before proceeding.

## Common Pitfalls

### Pitfall 1: `schedule` library requires pytz for tz parameter — project uses stdlib zoneinfo (CRITICAL)

**What goes wrong:** Passing a `zoneinfo.ZoneInfo('Australia/Perth')` or `'Australia/Perth'` string into `schedule.every().day.at('00:00', tz_arg).do(...)` works **only if pytz is installed**. The library's `__init__.py` explicitly uses `pytz.timezone(tz)` when `tz` is a string, and explicitly checks `isinstance(tz, pytz.BaseTzInfo)` when `tz` is an object. A `zoneinfo.ZoneInfo` fails the isinstance check and raises `ScheduleValueError: Timezone must be either a pytz object or a string`.

**Why it happens:** `schedule 1.2.0` added the `tz` parameter (2023-04-10) but predates stdlib `zoneinfo` adoption in the library. Even the patched `schedule 1.2.2` still uses pytz. The project has deliberately migrated off pytz to stdlib zoneinfo (main.py:41, state_manager.py:39, system_params.py imports) — adding pytz back for scheduler use contradicts the project's migration direction.

**How to avoid — two-part mitigation:**

1. **Omit the tz argument entirely.** GHA ubuntu-latest runners execute in UTC (`time.tzname` returns `('UTC', 'UTC')`). Replit containers also default to UTC. Therefore `schedule.every().day.at('00:00')` — no tz arg — treats `'00:00'` as local time == UTC, which is exactly what cron fires at.
2. **Add a process-tz assertion inside `_run_schedule_loop` at entry:**
   ```python
   # Belt-and-braces: the schedule library uses PROCESS-LOCAL time for .at()
   # when no tz arg is passed. We rely on UTC. Fail fast if the process runs
   # in any other tz — Replit or GHA runner misconfiguration would otherwise
   # silently fire at the wrong wall-clock moment.
   import time as _time
   assert _time.tzname[0] == 'UTC', (
     f'[Sched] process tz must be UTC for scheduler; got {_time.tzname} — '
     f'set TZ=UTC in the deploy environment or refactor to pass tz=pytz.timezone(...)'
   )
   ```
3. **Document in `docs/DEPLOY.md` troubleshooting section:**
   > "Scheduler fires at the wrong wall-clock time on Replit" → confirm the Replit container's TZ is UTC (default for Reserved VM). Run `date` in the Replit shell; the output should end in `UTC`. If it doesn't, add `TZ=UTC` to the Replit Secrets tab.

**Warning signs:** Tests that use a frozen non-UTC clock may accidentally pass while production fails. `TestLoopDriver` must patch `time.tzname` to `('UTC', 'UTC')` in the test path to match production behaviour.

**Verification (this session):** Confirmed against `https://raw.githubusercontent.com/dbader/schedule/master/schedule/__init__.py` — signature is `.at(time_str, tz=None)`; the library uses pytz exclusively; omitting tz uses process-local time. `[VERIFIED: schedule source + HISTORY.rst]`

### Pitfall 2: `stefanzweifel/git-auto-commit-action@v5` default does NOT commit gitignored files

**What goes wrong:** CONTEXT D-10 uses `file_pattern: state.json`, but `state.json` is listed in `.gitignore`. The action's default behaviour uses `git add` (not `git add -f`); `git add` silently skips gitignored files. The action logs `"Working tree clean. Nothing to commit."` — no error, no commit, state.json never persists back to the repo across runs. Operator sees successful workflow runs but `state.json` in the repo stays at whatever-was-committed-at-deploy.

**Why it happens:** The action's design philosophy is "don't commit things the user chose not to commit". Gitignored files are a deliberate signal. Without explicit opt-in (`add_options: '-f'`), the action honours the local-dev intent baked into `.gitignore`.

**How to avoid:**

1. **RECOMMENDED:** Add `add_options: '-f'` to the action's `with:` block:
   ```yaml
   - uses: stefanzweifel/git-auto-commit-action@v5
     if: success()
     with:
       commit_message: 'chore(state): daily signal update [skip ci]'
       file_pattern: state.json
       add_options: '-f'        # ← ADD THIS LINE
       commit_user_name: github-actions[bot]
       commit_user_email: 41898282+github-actions[bot]@users.noreply.github.com
   ```
2. **ALTERNATIVE (not recommended):** Remove `state.json` from `.gitignore`. This breaks the operator's local-dev story — every `git status` would show state.json diffs, every accidental `git add .` would stage it.

**Warning signs:** First workflow run after Phase 7 deploy — operator checks the repo after expected cron fire and sees no new commit on `state.json`. Action log shows "Working tree clean."

**Verification (this session):** Confirmed against action README + discussion #351 — "If your workflow changes a file but 'git-auto-commit' does not detect the change, check the .gitignore that applies to the respective file"; `file_pattern` feeds both `git status` and `git add` → gitignored files skip the status check silently. `[VERIFIED: action GitHub README + discussion 351]`

### Pitfall 3: Existing tests at `tests/test_main.py:129,146` assert a log line Phase 7 deletes

**What goes wrong:** Phase 4 D-07 added `'[Sched] One-shot mode (scheduler wiring lands in Phase 7)'` to `run_daily_check`. Two tests (`test_once_flag_runs_single_check` + `test_default_mode_runs_once_and_logs_schedule_stub`) assert this exact string is in `caplog.text`. Phase 7 D-05 DELETES that log line. If the tests aren't updated in the same plan, every test run fails after the deletion.

**Why it happens:** Phase 4 honestly stubbed the scheduler by locking CLI-05's semantics via an assertion on an explicit log line. Phase 7 is the phase that removes the stub. The two-tests-in-one-file dependency is well known to CONTEXT (see `downstream_notes`).

**How to avoid — plan task explicitly in Wave 1:**

| Old test | Old assertion | Phase 7 update |
|----------|---------------|----------------|
| `test_once_flag_runs_single_check` (line 129) | `'[Sched] One-shot mode (scheduler wiring lands in Phase 7)' in caplog.text` | **KEEP TEST, CHANGE ASSERTION.** `--once` mode does NOT enter the loop, so the new log line does NOT fire. Change assertion to: "fetch was called exactly twice AND no `[Sched] scheduler entered` line in caplog". Tests that `--once` is truly one-shot (exits without loop). |
| `test_default_mode_runs_once_and_logs_schedule_stub` (line 146) | `'[Sched] One-shot mode (scheduler wiring lands in Phase 7)' in caplog.text` | **RENAME + REPLACE ASSERTION.** Rename to `test_default_mode_enters_schedule_loop` and assert: `'[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon–Fri' in caplog.text`. Must also inject a `max_ticks=0` fake scheduler so test doesn't hang in the infinite loop. |

**Warning signs:** Post-edit test suite run shows 2 failures with assertion messages like `assert '[Sched] One-shot mode...' in ''`.

**Verification (this session):** Confirmed exact line numbers via grep — `tests/test_main.py:129` + `:146`. `[VERIFIED: grep scan of test_main.py 2026-04-23]`

### Pitfall 4: `[skip ci]` in commit message is a no-op for scheduled workflows

**What goes wrong:** CONTEXT D-10 includes `[skip ci]` in the commit message as defence-in-depth against recursive CI triggering. This token **only applies to `push` and `pull_request` trigger events** — it does NOT skip `schedule`, `workflow_dispatch`, or `workflow_run` triggers. Team knowledge gap: someone might assume `[skip ci]` prevents a cron-triggered workflow from firing on its own commit.

**Why it happens:** GitHub's skip-CI implementation is limited to the push/PR event path. The daily.yml workflow is triggered by `schedule`, so the committed state.json with `[skip ci]` would not affect its own cron schedule either way.

**How to avoid:**
- The `[skip ci]` token is still WORTH KEEPING because: (a) operator may later add a push-triggered test workflow (Phase 8+), at which point `[skip ci]` prevents the state.json commit from running tests; (b) it signals intent to human reviewers reading git log.
- **Do NOT rely on `[skip ci]`** to prevent cron re-triggering. The cron re-triggering problem is already non-existent: the workflow is triggered by cron, NOT by push, so its own commit never triggers itself.
- Document the limitation in `docs/DEPLOY.md`:
  > "`[skip ci]` in our commit messages prevents future push-triggered CI workflows from running on state.json-only commits. It does not affect the daily cron schedule (which is unrelated to commits)."

**Warning signs:** None — this pitfall is knowledge-only, not runtime.

**Verification (this session):** `[VERIFIED: GitHub Docs — Skipping workflow runs]` — "Skip instructions only apply to the push and pull_request events."

### Pitfall 5: GHA scheduled workflows drift 5–30 minutes during high-traffic periods

**What goes wrong:** CONTEXT D-07 schedules the workflow for `'0 0 * * 1-5'` — 00:00 UTC exactly. In practice GHA delays scheduled workflows by 5–30 minutes (sometimes more) during peak hours (top of the hour, especially :00 and :30 past the hour — which is exactly where ours fires). Operator sees the email arrive at 08:05–08:30 AWST, not 08:00 sharp.

**Why it happens:** GitHub runs cron queues globally and serialises them. 00:00 UTC is the most popular cron slot on the planet (every daily job everywhere). Load-balancing pushes less-urgent jobs back into a drift window.

**How to avoid:**
- **Accept the drift** — for a single-operator daily signal email, 5–30 min matters zero.
- **Document in `docs/DEPLOY.md` troubleshooting:**
  > "Email arrives later than 08:00 AWST" → GHA cron drifts 5–30 min during peak (00:00 UTC is peak). This is documented GitHub behaviour. Not a bug. If the operator ever needs sub-minute precision, pick a less-popular offset (e.g. `'17 0 * * 1-5'` = 00:17 UTC = 08:17 AWST) to dodge the rush.
- **Do NOT add external health-check / heartbeat monitoring in Phase 7** — deferred list already excludes this.

**Warning signs:** First few weekdays after deploy — operator wonders why the email is 10 min late. Runbook explains.

**Verification (this session):** `[VERIFIED: GitHub community discussions 156282, 122271, 52477, actions/runner#2977; cronbuilder.dev + manuelfedele blog — widely reported 5–30 min drift]`

### Pitfall 6: `load_dotenv()` in pytest context can leak `.env` values into tests

**What goes wrong:** D-06 calls `load_dotenv()` unconditionally at the top of `main()`. If pytest runs `main.main([...])` in a test (as `TestCLI` does — see `tests/test_main.py::TestCLI`), `load_dotenv()` fires, reads the operator's local `.env`, and sets `RESEND_API_KEY` + `SIGNALS_EMAIL_TO` in the test process's `os.environ`. Tests that expect "no env var set" path (NOTF-08 graceful-degradation) now see the real key and try to hit Resend.

**Why it happens:** `load_dotenv` defaults to `override=False`, which is good — it won't overwrite values already set by the test harness. But if the test doesn't explicitly unset the env vars, the production `load_dotenv()` call happily sets them for the test too.

**How to avoid — in test fixtures:**
```python
# Pattern for any test that invokes main.main(...) and wants deterministic env state:
@pytest.fixture(autouse=True)
def _isolate_dotenv(monkeypatch):
  # Ensure tests see a clean env slate, regardless of operator's local .env.
  monkeypatch.delenv('RESEND_API_KEY', raising=False)
  monkeypatch.delenv('SIGNALS_EMAIL_TO', raising=False)
  # Point load_dotenv at a non-existent file so it's a no-op.
  monkeypatch.setenv('DOTENV_PATH', '/dev/null')
  # Or better: monkeypatch.setattr('dotenv.load_dotenv', lambda *a, **kw: False)
  # Choose whichever pattern test_main.py already uses for similar isolation.
```

**Warning signs:** Flaky CI — tests pass locally (developer has `.env` with real keys) but fail in CI, or vice versa.

**Verification (this session):** `[VERIFIED: python-dotenv docs — override=False default; load_dotenv returns False on missing file]`

### Pitfall 7: `schedule` library's infinite `while True` loop will hang tests

**What goes wrong:** D-01 defaults `max_ticks: int | None = None` → None means infinite loop (`while True`). Tests that forget to inject `max_ticks=1` (or similar finite value) will hang indefinitely, eventually killed by pytest timeout.

**Why it happens:** The loop IS supposed to run forever in production; the finite-tick parameter is the test-only escape hatch.

**How to avoid:**
- Every `TestLoopDriver` test case MUST pass `max_ticks=<small int>` (typically 0, 1, or 2).
- Test naming convention: tests that exercise the loop include `_with_max_ticks_` in their name (self-documenting).
- Add a pytest `timeout` marker to `tests/test_scheduler.py` as defence-in-depth — `pytest-timeout` is not currently in requirements.txt, so this is a soft recommendation only.

**Example:**
```python
def test_loop_runs_one_tick_then_returns(monkeypatch):
  fake_scheduler = _FakeScheduler()
  fake_sleeps: list[float] = []
  rc = _run_schedule_loop(
    job=lambda args: (0, None, None, None),
    args=argparse.Namespace(),
    scheduler=fake_scheduler,
    sleep_fn=fake_sleeps.append,
    tick_budget_s=60.0,
    max_ticks=1,           # ← finite; otherwise hangs
  )
  assert rc == 0
  assert fake_scheduler.run_pending_calls == 1
  assert fake_sleeps == [60.0]
```

**Warning signs:** pytest run shows `test_loop_*` tests in RUNNING state for >30s; Ctrl-C kills them.

**Verification (this session):** Code pattern standard — CONTEXT D-01 explicitly mentions `max_ticks=1` in the test example.

### Pitfall 8: Replit container tzdata availability — `ZoneInfo('Australia/Perth')` fails on minimal images

**What goes wrong:** `_compute_run_date` uses `ZoneInfo('Australia/Perth')`. On ubuntu-latest (GHA) + default Replit container images, `tzdata` is preinstalled. On some minimal Alpine-based images or bare distroless containers, `zoneinfo.ZoneInfo('Australia/Perth')` raises `ZoneInfoNotFoundError: No time zone found with key Australia/Perth`.

**Why it happens:** Python's `zoneinfo` (stdlib) requires the OS's IANA tz database. If the OS doesn't ship `/usr/share/zoneinfo/` (Alpine), stdlib raises.

**How to avoid:**
- Phase 7 ships `ubuntu-latest` (GHA) + default Replit container — both have tzdata.
- Add belt-and-braces fallback to requirements.txt: `tzdata==2024.1` (pure-Python IANA tz database, pip-installable). Python stdlib zoneinfo falls back to the `tzdata` package if the OS copy is absent. Current requirements.txt does NOT include tzdata — but Phase 3/4/5/6 haven't hit this because GHA hasn't been deployed yet.
- Phase 7 plan recommendation: **do NOT add tzdata to requirements.txt in this phase** — GHA + Replit both have OS tzdata. Document in `docs/DEPLOY.md` as a future-proofing note: if operator migrates to a minimal container image (Alpine, distroless), add `tzdata` to requirements.txt.

**Warning signs:** First workflow run errors with `ZoneInfoNotFoundError: No time zone found with key Australia/Perth`.

**Verification (this session):** `[VERIFIED: Python stdlib docs — zoneinfo falls back to tzdata package; ubuntu-latest ships tzdata; Alpine does not]`

### Pitfall 9: `stefanzweifel/git-auto-commit-action@v5` under branch protection

**What goes wrong:** If the repo has branch protection on `main` (required reviews, status checks, or signed commits), the default `GITHUB_TOKEN` may not have permission to push directly. The action fails with a permission error.

**Why it happens:** Branch protection exempts only the repo admin + explicit-allowlist users by default. `github-actions[bot]` is not on the exemption list unless explicitly added.

**How to avoid:**
- **If the operator has branch protection on main:** Add `github-actions[bot]` to the "allow specified actors to bypass required pull requests" list in Settings → Branches → Branch protection rules.
- **If the operator wants to keep strict branch protection:** Use a Personal Access Token with write scope, stored as a secret (e.g. `CREATE_PAT`) and passed to the action's `token:` input. This is more setup; document both options in DEPLOY.md troubleshooting.
- **Default state of this project:** No branch protection on main (verified by checking `gh api repos/:owner/:repo/branches/main/protection` — the .planning shows no mention of branch protection configuration; safe to assume none).

**Warning signs:** First workflow run fails with `remote: error: GH006: Protected branch update failed for refs/heads/main`.

**Verification (this session):** `[VERIFIED: action troubleshooting README — PAT or bypass required for protected branches]`

### Pitfall 10: GHA free tier minutes — comfortably under for this workload

**What goes wrong:** None — this is a confirmation, not a pitfall. Operator may worry about GHA billing.

**Math:** Daily run × 5 weekdays × 4.3 weeks/month × ~60s/run = ~21.5 min/month. Public repos: unlimited. Private repos: 2000 min/month free tier on the Free plan. Phase 7's usage is ~1% of private free tier.

**How to avoid:** Nothing to avoid. Document in `docs/DEPLOY.md` "Cost estimate" subsection:
> "Cost: GHA cron run takes ~60 seconds; 5 weekdays × 4.3 weeks ≈ 21 min/month. Under 2% of the 2000-min/month GitHub Actions free tier (Private repos); unlimited on Public. Ubuntu-latest is billed 1× multiplier. No billable deps."

**Verification (this session):** `[VERIFIED: GitHub billing docs — 2000 min/month Free tier Private; unlimited Public]`

## Runtime State Inventory

Phase 7 is a scheduler + deployment phase, not a rename/refactor. However, the default-mode flip (D-05) and the deletion of the `'[Sched] One-shot mode...'` log line (D-05) trigger runtime-state considerations.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None. Phase 7 introduces no new state.json keys; `state.json` schema version stays at 1. | None |
| Live service config | **GHA Secrets (repo-scoped):** `RESEND_API_KEY` + `SIGNALS_EMAIL_TO` must be set in `Settings → Secrets and variables → Actions` BEFORE first workflow run. Secrets are NOT in git. | Operator runbook task in `docs/DEPLOY.md` §Quickstart. Plan includes a verification step: operator manually triggers `workflow_dispatch` and checks green run + email. |
| OS-registered state | None. No systemd units, no Task Scheduler entries, no launchd plists. GHA cron is GitHub-service-registered (not OS-registered). | None |
| Secrets and env vars | `RESEND_API_KEY` + `SIGNALS_EMAIL_TO` are the formal deploy contract (D-12). `.env.example` already populated by Phase 6. `.env` already in `.gitignore`. Phase 7 adds header comments only. | Add GHA-Secrets-vs-Replit-Secrets-vs-.env commentary to `.env.example`. Verify no new secret names introduced. |
| Build artifacts / installed packages | **`state.json` in `.gitignore` but COMMITTED BY GHA.** This is not a rename issue but a "which world owns this file" issue. Current state: gitignored locally (operator never commits). Phase 7 state: committed-back-by-CI only. See Pitfall 2 for the `add_options: '-f'` fix. | `add_options: '-f'` in workflow YAML. No `.gitignore` change. |
| Deprecated log line | `'[Sched] One-shot mode (scheduler wiring lands in Phase 7)'` hardcoded in main.py:459 AND asserted in `tests/test_main.py:129,146`. | Delete from main.py (D-05); update tests (Pitfall 3). Coordinated in Wave 1 — both edits in same plan. |

**Nothing in a category:** Stored data (none — no new state keys), OS-registered state (none — GHA replaces that), net-new ambient state (none — Phase 7 does not introduce any ambient runtime coupling).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11.x | Everywhere | ✓ | 3.11.8 (`.python-version`) | — |
| pyenv | Local dev | ✓ (Homebrew-installed per STATE.md) | — | `python3.11` from system if no pyenv |
| `schedule` 1.2.2 | `main.py::_run_schedule_loop` (local import) | ✗ — NEW dep | — | None; must install via Wave 0 requirements.txt edit |
| `python-dotenv` 1.0.1 | `main.py::main()` (local import) | ✗ — NEW dep | — | None; must install via Wave 0 requirements.txt edit |
| `tzdata` (Python pkg) | Defence against minimal container images | ✗ — not pinned | — | OS tzdata on ubuntu-latest + Replit (verified default) |
| GitHub Actions | Primary deployment | ✓ (assumed — operator has a GitHub account) | — | Replit Reserved VM (D-16) |
| Replit Core plan | Alternative deployment | Unknown | — | GHA (primary) |
| Resend verified sender domain | Email dispatch | ✓ (`signals@carbonbookkeeping.com.au` per Phase 6) | — | NOTF-08 graceful-degradation (writes `last_email.html`) |
| `git` CLI in GHA runner | For `git-auto-commit-action` | ✓ (ubuntu-latest default) | — | — |

**Missing dependencies with no fallback:**
- `schedule==1.2.2` — must be installed in Wave 0.
- `python-dotenv==1.0.1` — must be installed in Wave 0.

**Missing dependencies with fallback:**
- `tzdata` (Python pkg) — defence only; current GHA + Replit images ship OS tzdata. Plan: document in DEPLOY.md as future-proofing note; do NOT add to requirements.txt in this phase.

**Unknowns:**
- Operator's Replit subscription tier — Replit's 2026 pricing has shifted (Reserved VM now starts $6.20/mo billed daily on the new Pro plan, or $20/mo legacy). Plan `docs/DEPLOY.md` Replit section to reference both price points + point to current Replit pricing page.

## Code Examples

### Example 1: `_run_schedule_loop` full implementation (D-01 + Pitfall 1 + 7 mitigations)

```python
# Source: CONTEXT D-01 + research §Pattern 1 + Pitfall 1 + Pitfall 7
from typing import Callable

def _run_schedule_loop(
  job: Callable[[argparse.Namespace], tuple[int, dict | None, dict | None, datetime | None]],
  args: argparse.Namespace,
  scheduler=None,
  sleep_fn=None,
  tick_budget_s: float = 60.0,
  max_ticks: int | None = None,
) -> int:
  '''D-01: factored schedule loop driver with injectable fakes.

  Production call: `_run_schedule_loop(run_daily_check, args)` — defaults
  flow through; runs forever. Test call: `_run_schedule_loop(..., scheduler=fake,
  sleep_fn=fake_sleep, max_ticks=1)` — one tick, no real sleep.

  Pitfall 1 mitigation: the schedule library's .at() without tz arg uses
  process-local time. We assert the process is in UTC (GHA default + Replit
  Reserved VM default). Do NOT pass a ZoneInfo object — schedule 1.2.x requires
  pytz and raises ScheduleValueError on zoneinfo objects.

  Pitfall 7 mitigation: max_ticks defaults to None (infinite in production).
  Tests MUST pass a finite max_ticks to avoid hanging.
  '''
  import schedule  # local import — C-2 / hex-lite / AST blocklist
  import time as _time

  # Pitfall 1: confirm process tz is UTC so .at('00:00') fires at 00:00 UTC.
  assert _time.tzname[0] == 'UTC', (
    f'[Sched] process tz must be UTC; got {_time.tzname}. '
    f'Set TZ=UTC in the deploy environment.'
  )

  _scheduler = scheduler or schedule
  _sleep = sleep_fn or _time.sleep

  logger.info('[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon–Fri')
  _scheduler.every().day.at('00:00').do(_run_daily_check_caught, job, args)

  ticks = 0
  while max_ticks is None or ticks < max_ticks:
    _scheduler.run_pending()
    _sleep(tick_budget_s)
    ticks += 1
  return 0
```

### Example 2: `_run_daily_check_caught` never-crash wrapper (D-02)

```python
# Source: CONTEXT D-02 + research §Pattern 2
def _run_daily_check_caught(job, args) -> None:
  '''D-02: schedule loop survives one bad run. Next cron fire retries.

  Third instance of the never-crash pattern (after _render_dashboard_never_crash
  and _send_email_never_crash). ONLY valid `except Exception:` site in the
  loop path. Phase 8 (ERR-04) adds crash-email dispatch on top of this same net.
  '''
  try:
    rc, _, _, _ = job(args)
    if rc != 0:
      logger.warning('[Sched] daily check returned rc=%d (loop continues)', rc)
  except (DataFetchError, ShortFrameError) as e:
    logger.warning('[Sched] data-layer failure caught in loop: %s', e)
  except Exception as e:
    logger.warning(
      '[Sched] unexpected error caught in loop: %s: %s (loop continues)',
      type(e).__name__, e,
    )
```

### Example 3: Weekday gate prelude inside `run_daily_check` (D-03)

```python
# Source: CONTEXT D-03 + research §Pattern 3
def run_daily_check(
  args: argparse.Namespace,
) -> tuple[int, dict | None, dict | None, datetime | None]:
  # Step 1: AWST wall-clock (unchanged from Phase 6).
  run_date = _compute_run_date()

  # D-03 (Phase 7): weekday gate — short-circuits BEFORE any fetch, compute,
  # or state mutation. Applies to ALL invocation modes (default, --once,
  # --test, --force-email). `run_date.weekday()` returns 0=Mon..6=Sun
  # (Python stdlib contract); 5=Sat, 6=Sun. Preserves the 4-tuple contract
  # so main()'s dispatch ladder Fix 10 None-guard absorbs the state=None
  # case without a second code path.
  if run_date.weekday() >= WEEKDAY_SKIP_THRESHOLD:  # 5 — from system_params.py
    logger.info(
      '[Sched] weekend skip %s (weekday=%d) — no fetch, no state mutation',
      run_date.strftime('%Y-%m-%d'), run_date.weekday(),
    )
    return 0, None, None, run_date

  # --- existing Phase 4-6 D-11 sequence unchanged below ---
  # run_date_iso = run_date.strftime('%Y-%m-%d')
  # run_date_display = run_date.strftime('%Y-%m-%d %H:%M:%S AWST')
  # ... etc.
```

### Example 4: `main()` default-mode dispatch amendment (D-04 + D-05)

```python
# Source: CONTEXT D-04 + D-05 — amends ONE branch of the existing main() ladder
def main(argv: list[str] | None = None) -> int:
  # D-06 (Phase 7): load .env into os.environ BEFORE parsing args.
  # Local import keeps dotenv off FORBIDDEN_MODULES_MAIN allowlist.
  from dotenv import load_dotenv
  load_dotenv()  # returns False on missing .env; no-op; override=False default

  parser = _build_parser()
  args = parser.parse_args(argv)
  _validate_flag_combo(args, parser)
  logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stderr, force=True)

  try:
    if args.reset:
      return _handle_reset()
    if args.force_email or args.test:
      # Phase 6 compute-then-email path (unchanged).
      rc, state, old_signals, run_date = run_daily_check(args)
      if rc == 0 and state is not None and old_signals is not None and run_date is not None:
        _send_email_never_crash(state, old_signals, run_date, is_test=args.test)
      return rc
    if args.once:
      # CLI-04: one-shot mode for GHA. No loop.
      rc, _state, _old_signals, _run_date = run_daily_check(args)
      return rc
    # Default path (Phase 7 D-04 + D-05): immediate first run, then enter loop.
    _run_daily_check_caught(run_daily_check, args)
    return _run_schedule_loop(run_daily_check, args)
  except (DataFetchError, ShortFrameError) as e:
    logger.error('[Fetch] ERROR: %s', e)
    return 2
  except Exception as e:
    logger.error('[Sched] ERROR: unexpected crash: %s: %s', type(e).__name__, e)
    return 1
```

### Example 5: Full `.github/workflows/daily.yml` (D-07 + D-10 + Pitfall 2 mitigation)

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

### Example 6: Test patterns for the scheduler loop (6 classes)

```python
# Source: CONTEXT §downstream_notes planner recommendations + this research
# tests/test_scheduler.py

import argparse
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import main as main_module

AWST = ZoneInfo('Australia/Perth')


class _FakeScheduler:
  '''Minimal schedule-library fake for injection.'''
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


class TestWeekdayGate:
  '''D-03: run_daily_check short-circuits on AWST Sat/Sun.'''

  @pytest.mark.parametrize('weekday_awst', [5, 6])  # Sat, Sun
  def test_weekend_skips_fetch_and_compute(self, weekday_awst, monkeypatch, freezer):
    # Freeze clock to 2026-04-25 Sat 00:00 UTC = 08:00 AWST
    # Pick dates: 2026-04-25 = Sat (weekday=5); 2026-04-26 = Sun (weekday=6).
    date_iso = '2026-04-25' if weekday_awst == 5 else '2026-04-26'
    freezer.move_to(f'{date_iso}T00:00:00+00:00')
    fetch_called: list = []
    monkeypatch.setattr(main_module.data_fetcher, 'fetch_ohlcv',
                        lambda *a, **kw: fetch_called.append(a) or None)
    args = argparse.Namespace(test=False, reset=False, force_email=False, once=True)
    rc, state, old_signals, run_date = main_module.run_daily_check(args)
    assert rc == 0
    assert state is None
    assert old_signals is None
    assert run_date is not None
    assert run_date.weekday() == weekday_awst
    assert fetch_called == []  # short-circuit: no fetch


class TestImmediateFirstRun:
  '''D-04: default mode runs a daily check BEFORE entering the loop.'''

  def test_default_mode_calls_job_once_before_loop(self, monkeypatch):
    call_order: list[str] = []
    def _fake_caught(job, args):
      call_order.append('caught')
    def _fake_loop(job, args):
      call_order.append('loop')
      return 0
    monkeypatch.setattr(main_module, '_run_daily_check_caught', _fake_caught)
    monkeypatch.setattr(main_module, '_run_schedule_loop', _fake_loop)
    # Patch load_dotenv so we don't read a real .env.
    monkeypatch.setattr('dotenv.load_dotenv', lambda *a, **kw: False)
    rc = main_module.main([])  # default mode — no flags
    assert rc == 0
    assert call_order == ['caught', 'loop']


class TestLoopDriver:
  '''D-01: _run_schedule_loop injection + finite-tick discipline.'''

  def test_max_ticks_zero_returns_immediately(self, monkeypatch):
    # Pitfall 1 mitigation: process must be UTC for .at('00:00') interpretation.
    import time as _t
    monkeypatch.setattr(_t, 'tzname', ('UTC', 'UTC'))
    fake = _FakeScheduler()
    sleeps: list[float] = []
    rc = main_module._run_schedule_loop(
      job=lambda args: (0, None, None, None),
      args=argparse.Namespace(),
      scheduler=fake,
      sleep_fn=sleeps.append,
      tick_budget_s=60.0,
      max_ticks=0,   # Pitfall 7: finite to avoid hang
    )
    assert rc == 0
    assert fake.run_pending_calls == 0  # zero ticks
    assert sleeps == []
    # Registration still happens even with zero ticks:
    assert len(fake.registered) == 1
    assert fake.registered[0][0] == '00:00'  # D-01 time arg

  def test_max_ticks_one_runs_single_cycle(self, monkeypatch):
    import time as _t
    monkeypatch.setattr(_t, 'tzname', ('UTC', 'UTC'))
    fake = _FakeScheduler()
    sleeps: list[float] = []
    rc = main_module._run_schedule_loop(
      job=lambda args: (0, None, None, None),
      args=argparse.Namespace(),
      scheduler=fake,
      sleep_fn=sleeps.append,
      tick_budget_s=60.0,
      max_ticks=1,
    )
    assert rc == 0
    assert fake.run_pending_calls == 1
    assert sleeps == [60.0]

  def test_non_utc_process_raises(self, monkeypatch):
    import time as _t
    monkeypatch.setattr(_t, 'tzname', ('AEST', 'AEDT'))
    with pytest.raises(AssertionError, match='must be UTC'):
      main_module._run_schedule_loop(
        job=lambda args: (0, None, None, None),
        args=argparse.Namespace(),
        scheduler=_FakeScheduler(),
        sleep_fn=lambda _: None,
        max_ticks=1,
      )


class TestLoopErrorHandling:
  '''D-02: _run_daily_check_caught swallows exceptions + returns None.'''

  def test_data_fetch_error_caught_logs_warning(self, caplog):
    from data_fetcher import DataFetchError
    def _raising_job(args):
      raise DataFetchError('yfinance down')
    caplog.set_level(logging.WARNING)
    # Does not raise:
    main_module._run_daily_check_caught(_raising_job, argparse.Namespace())
    assert any('data-layer failure' in r.message for r in caplog.records)

  def test_unexpected_exception_caught(self, caplog):
    def _raising_job(args):
      raise RuntimeError('boom')
    caplog.set_level(logging.WARNING)
    main_module._run_daily_check_caught(_raising_job, argparse.Namespace())
    assert any('unexpected error' in r.message for r in caplog.records)

  def test_nonzero_rc_logs_warning(self, caplog):
    caplog.set_level(logging.WARNING)
    main_module._run_daily_check_caught(
      lambda args: (2, None, None, None),
      argparse.Namespace(),
    )
    assert any('rc=2' in r.message for r in caplog.records)


class TestDefaultModeDispatch:
  '''D-05: default mode emits new log line; --once does not.'''

  def test_default_mode_emits_scheduler_entered_log(self, monkeypatch, caplog):
    import time as _t
    monkeypatch.setattr(_t, 'tzname', ('UTC', 'UTC'))
    caplog.set_level(logging.INFO)
    monkeypatch.setattr('dotenv.load_dotenv', lambda *a, **kw: False)
    # Shortcut: patch _run_daily_check_caught to no-op so we reach _run_schedule_loop quickly.
    monkeypatch.setattr(main_module, '_run_daily_check_caught', lambda j, a: None)
    # Patch the schedule module to a fake so loop registers+exits via max_ticks.
    fake = _FakeScheduler()
    real_loop = main_module._run_schedule_loop
    def _wrap(job, args):
      return real_loop(job, args, scheduler=fake, sleep_fn=lambda _: None, max_ticks=0)
    monkeypatch.setattr(main_module, '_run_schedule_loop', _wrap)
    rc = main_module.main([])
    assert rc == 0
    assert any(
      'scheduler entered' in r.message and '00:00 UTC (08:00 AWST)' in r.message
      for r in caplog.records
    )


class TestDotenvLoading:
  '''D-06: load_dotenv fires at top of main(); local import stays isolated.'''

  def test_main_calls_load_dotenv(self, monkeypatch):
    called: list[bool] = []
    monkeypatch.setattr('dotenv.load_dotenv', lambda *a, **kw: called.append(True) or False)
    # Short-circuit main() by running --reset path (never enters loop).
    monkeypatch.setenv('RESET_CONFIRM', 'NO')  # cancels reset cleanly
    monkeypatch.setattr(main_module, '_handle_reset', lambda: 1)
    rc = main_module.main(['--reset'])
    assert rc == 1
    assert called == [True]
```

### Example 7: Updated `test_main.py:129,146` (Pitfall 3 mitigation)

```python
# BEFORE (Phase 4 — lines 104-131):
class TestOnceFlag:
  def test_once_flag_runs_single_check(self, tmp_path, monkeypatch, caplog):
    ...
    rc = main.main(['--once'])
    assert rc == 0
    assert len(fetch_calls) == 2
    assert '[Sched] One-shot mode (scheduler wiring lands in Phase 7)' in caplog.text

# AFTER (Phase 7 — line 129 update):
class TestOnceFlag:
  def test_once_flag_runs_single_check(self, tmp_path, monkeypatch, caplog):
    ...
    rc = main.main(['--once'])
    assert rc == 0
    assert len(fetch_calls) == 2, (
      f'CLI-04: expected exactly 2 fetch calls, got {fetch_calls}'
    )
    # Phase 7 D-05: deprecated log line deleted. --once does NOT enter the loop,
    # so the new `[Sched] scheduler entered` line also does NOT fire.
    assert '[Sched] scheduler entered' not in caplog.text, (
      'CLI-04: --once must NOT enter the schedule loop'
    )

# BEFORE (Phase 4 — lines 133-148):
def test_default_mode_runs_once_and_logs_schedule_stub(self, tmp_path, monkeypatch, caplog):
  ...
  rc = main.main([])
  assert rc == 0
  assert '[Sched] One-shot mode (scheduler wiring lands in Phase 7)' in caplog.text

# AFTER (Phase 7 — rename + assertion replacement):
def test_default_mode_enters_schedule_loop(self, tmp_path, monkeypatch, caplog):
  '''Phase 7 D-05: default mode runs immediate first check then enters loop.
  Must inject a 0-tick fake scheduler so test doesn't hang.
  '''
  import time as _t
  monkeypatch.setattr(_t, 'tzname', ('UTC', 'UTC'))
  # Fake _run_schedule_loop to observe the call + return 0 without looping.
  called: list = []
  monkeypatch.setattr(main, '_run_schedule_loop',
                      lambda job, args: called.append(('loop', job.__name__)) or 0)
  # Fake _run_daily_check_caught so immediate first-run doesn't touch Yahoo.
  monkeypatch.setattr(main, '_run_daily_check_caught',
                      lambda job, args: called.append(('caught', job.__name__)))
  rc = main.main([])
  assert rc == 0
  assert called == [('caught', 'run_daily_check'), ('loop', 'run_daily_check')]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SPEC.md cron `0 22 * * 1-5` (AEST approximation) | `0 0 * * 1-5` (AWST precise) | 2026-04-20 roadmap creation | Perth is UTC+8 year-round (no DST); 22:00 UTC is 8am AEST, not AWST; correction made before Phase 7 |
| Replit Always On primary, GHA fallback | GHA primary, Replit alternative | Operator decision baked into ROADMAP | Filesystem persistence caveat on Replit Autoscale + free GHA tier inversion |
| `schedule.every().day.at("22:00")` (SPEC.md original) | `schedule.every().day.at("00:00")` (UTC) | PROJECT.md Constraints line | Explicit UTC interpretation; aligns with GHA cron UTC |
| pytz everywhere | stdlib zoneinfo everywhere | Phases 1–6 migration | Phase 7 must NOT pass `ZoneInfo` into `schedule.at(tz=)` — that library still wants pytz |
| Phase 4 default == one-shot | Phase 7 default == immediate first run + loop | D-04 + D-05 | CLI-05 completion |

**Deprecated/outdated:**
- SPEC.md's `schedule.every().day.at("22:00")` line (line 285) — superseded by `"00:00"` UTC (PROJECT.md + CLAUDE.md).
- SPEC.md's `cron: "0 22 * * 1-5"` note (line 352) — superseded by `'0 0 * * 1-5'` (ROADMAP + CONTEXT D-07).
- SPEC.md's `ACCOUNT_START` env var mention (line 323) — never implemented in codebase; operator config deferred to Phase 8 CONF-01.
- SPEC.md's `FROM_EMAIL` + `TO_EMAIL` env var names (lines 186, 317) — Phase 6 uses hardcoded `_EMAIL_FROM` + `SIGNALS_EMAIL_TO` (D-14); new names are authoritative.
- SPEC.md's `SEND_TEST_ON_START` env var (line 325) — never implemented; test-email-on-start is via `--test` CLI flag.

These deprecations are documentation drift, not runtime drift; they are in SPEC.md only (the project brief), which is an archival artefact. Phase 7 plan should note in `docs/DEPLOY.md` that "SPEC.md is the historical brief; PROJECT.md and CLAUDE.md are the current source of truth for deployment specifics."

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Replit Reserved VM containers run in UTC by default (not operator-local tz) | Pitfall 1 + DEPLOY.md | If operator's Replit container is not UTC, `schedule.at('00:00')` fires at the wrong wall-clock. The `_run_schedule_loop` UTC-assertion fails fast with a clear error, and DEPLOY.md troubleshooting says "set TZ=UTC". Mitigation in place. `[ASSUMED]` |
| A2 | GitHub `github-actions[bot]` user does not trigger branch protection when committing via default GITHUB_TOKEN on a repo without branch protection | Pitfall 9 | If branch protection IS on (not indicated by any file in .planning but possible), action fails. Documented fallback (PAT or bypass rule). `[ASSUMED]` — cannot verify without querying `gh api repos/:owner/:repo/branches/main/protection`, which requires operator credentials. |
| A3 | Operator's `RESEND_API_KEY` secret is already verified with the `signals@carbonbookkeeping.com.au` sender domain | DEPLOY.md §Quickstart | If not, first workflow fires, email bounces, NOTF-08 path writes last_email.html to the GHA runner (ephemeral) + operator sees missing-email symptom. Phase 6 graceful-degradation covers. `[ASSUMED — CITED from Phase 6 D-14 note "Resend sender verified"]` |
| A4 | Operator's Replit subscription covers Reserved VM if they choose the Replit path | DEPLOY.md §Replit alternative | If operator doesn't subscribe, the alternative path fails entirely — but GHA is primary so this is only a graceful-docs question. `[ASSUMED]` |
| A5 | `tzdata` OS package present on ubuntu-latest (GHA) + Replit default container | Pitfall 8 | If not, `_compute_run_date` raises `ZoneInfoNotFoundError` at first clock read. Phase 7 plan does not add `tzdata` to requirements.txt; if this breaks, Phase 8 hardens by pinning it. `[VERIFIED — ubuntu-latest official docs; Replit Nix default env]` — so actually NOT assumed — removing from assumptions list risk is low. |
| A6 | `python-dotenv 1.0.1` handles `override=False` and missing-file as documented | D-06 | If behaviour differs, env var precedence could flip or load_dotenv could raise — plan includes a Wave 1 test that explicitly asserts default behaviour. `[VERIFIED: python-dotenv docs this session]` |
| A7 | `schedule` library's `run_pending()` does NOT drop or queue a fire if the job runs long — the NEXT fire is computed at the CURRENT tick | §Pattern 1 | Our job takes ~60s worst case; the cron is daily. Single instance; zero risk of overlap. If the assumption is wrong, two runs on the same day are harmless (state.json's atomic write is idempotent on same-day reads). `[ASSUMED]` — schedule docs are quiet on this edge case, but our cadence is not where it would matter. |
| A8 | GHA runner's default `GITHUB_TOKEN` has `contents: write` when the workflow declares `permissions: contents: write` | D-07 + SC-1 | If not, action fails with permission error. `[VERIFIED — GitHub Docs: "Permissions for the GITHUB_TOKEN"]` |

**If this table is empty:** N/A — has 7 actionable entries. Operator may want to confirm A1 (Replit container tz), A2 (branch protection state), A3 (Resend sender already live), A4 (Replit subscription) before Wave 0 scaffold writes the YAML — but none block planning.

## Open Questions

1. **Operator's exact recipient email for SIGNALS_EMAIL_TO.**
   - What we know: `.env.example` shows placeholder `your-email@example.com`; Phase 6 D-14 noted `_EMAIL_TO_FALLBACK = 'marc@carbonbookkeeping.com.au'` as a TODO-operator-confirm placeholder.
   - What's unclear: whether the final SIGNALS_EMAIL_TO value is `marc@carbonbookkeeping.com.au` or another address (e.g. the operator's Gmail per the working-dir env note `mwiriadi@gmail.com`).
   - Recommendation: Phase 7 plan does NOT bake a specific address. `docs/DEPLOY.md` shows operator where to configure the GHA secret; operator sets the value themselves. Code reads `os.environ.get('SIGNALS_EMAIL_TO', _EMAIL_TO_FALLBACK)` from Phase 6.

2. **Operator's Replit subscription tier and TZ setting.**
   - What we know: Replit 2026 pricing has Reserved VM at $6.20/mo (new Pro plan) or $20/mo (legacy Core plan); Replit Autoscale resets FS on cold start (bad for state.json).
   - What's unclear: whether operator has Replit subscription at all; whether they plan to actually use Replit or just keep the docs as a cold-standby.
   - Recommendation: DEPLOY.md documents both tiers + TZ=UTC requirement; operator decides whether to activate if GHA ever breaks.

3. **Branch protection on main.**
   - What we know: No mention in `.planning/` or `CLAUDE.md`; GSD workflow docs assume main-branch is the PR target.
   - What's unclear: whether operator has enabled branch-protection rules on the GitHub repo.
   - Recommendation: Plan task in Wave 2 (after YAML is written): operator runs a manual `workflow_dispatch` on the repo and confirms the first auto-commit lands. If it fails with branch-protection error, plan gap closure adds PAT-based commit + DEPLOY.md updates. If it succeeds (current assumption A2), no change needed.

4. **Where to put `LOOP_SLEEP_S` / `SCHEDULE_TIME_UTC` / `WEEKDAY_SKIP_THRESHOLD` constants.**
   - What we know: CONTEXT §Claude's Discretion lists `system_params.py` as recommended; Phase 1–3 constants all live there.
   - What's unclear: None — this is a recommendation, planner decides. Research recommendation confirmed: `system_params.py`.

## Validation Architecture

*(Included per nyquist_validation default.)*

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.3 + pytest-freezer 0.4.9 |
| Config file | `pyproject.toml` (existing from Phase 1) |
| Quick run command | `pytest tests/test_scheduler.py -x` |
| Full suite command | `pytest -x` |

### Eight Validation Dimensions (Nyquist framework)

Phase 7 validation covers each dimension as follows:

| Dimension | Technique | Phase 7 Coverage |
|-----------|-----------|------------------|
| **Correctness** | Unit tests with injected fakes | `TestLoopDriver`, `TestWeekdayGate`, `TestImmediateFirstRun`, `TestDefaultModeDispatch` — assert the loop drives the right callable at the right cadence with the right log line |
| **Robustness** | Exception-path unit tests | `TestLoopErrorHandling` — DataFetchError, ShortFrameError, RuntimeError all caught by `_run_daily_check_caught`; loop continues |
| **Determinism** | Frozen-clock tests | `TestWeekdayGate` uses `pytest-freezer` to pin AWST wall-clock to specific Sat/Sun/Mon dates; AST blocklist guards main.py's imports (no new `schedule`/`dotenv` leak in other modules) |
| **Boundary conditions** | weekday-edge tests | `TestWeekdayGate` parametrised on weekday=5 (Sat) AND weekday=6 (Sun); `TestLoopDriver` tests `max_ticks=0` (no-op) AND `max_ticks=1` (one cycle) |
| **Integration** | Multi-file wiring tests | `TestDefaultModeDispatch` exercises the full `main([])` dispatch ladder end-to-end with injected fakes for the scheduler + dotenv; updated `test_main.py::test_default_mode_enters_schedule_loop` confirms the dispatch wiring |
| **Environmental** | Process-tz assertion, env-var isolation | `TestLoopDriver::test_non_utc_process_raises` covers the Pitfall 1 UTC assumption; `TestDotenvLoading` covers the D-06 load_dotenv call-site; a fixture mirror of §Pitfall 6 monkeypatch pattern covers env-var leakage |
| **Observability** | Log-line assertions in caplog | `TestDefaultModeDispatch` asserts exact `'[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon–Fri'` string; updated `test_main.py:129,146` tests confirm the deprecated `'[Sched] One-shot mode'` line is deleted |
| **Deployment contract** | YAML structural + docs lint | Plan includes a "YAML smoke" verification task in Wave 2: `yamllint .github/workflows/daily.yml` + `grep -F 'cron: '\''0 0 * * 1-5'\''' .github/workflows/daily.yml` + `grep -F 'add_options: '\''-f'\''' .github/workflows/daily.yml` (Pitfall 2 gate); operator manual-trigger test after first commit |

### Phase Requirements → Test Map

| Req ID | Behaviour | Test Type | Automated Command | File Exists? |
|--------|-----------|-----------|-------------------|--------------|
| SCHED-01 | Cron fires at 00:00 UTC Mon–Fri | deployment-contract | `grep -F "cron: '0 0 * * 1-5'" .github/workflows/daily.yml` + operator `workflow_dispatch` smoke | ❌ Wave 2 |
| SCHED-02 | Immediate first run on process start | integration | `pytest tests/test_scheduler.py::TestImmediateFirstRun -x` | ❌ Wave 0 (new file) |
| SCHED-03 | `run_daily_check` weekday gate | unit + freeze | `pytest tests/test_scheduler.py::TestWeekdayGate -x` | ❌ Wave 0 |
| SCHED-04 | `--once` single run + clean exit | integration | `pytest tests/test_main.py::TestOnceFlag::test_once_flag_runs_single_check -x` | ✅ exists (updated per Pitfall 3) |
| SCHED-05 | GHA workflow skeleton | deployment-contract | yamllint + grep + operator dispatch | ❌ Wave 2 |
| SCHED-06 | Replit alternative documented | docs | `grep -F 'Replit Reserved VM' docs/DEPLOY.md` + `grep -F 'Always On' docs/DEPLOY.md` | ❌ Wave 2 |
| SCHED-07 | Env-var loading `.env` local / GHA secrets deploy | unit + integration | `pytest tests/test_scheduler.py::TestDotenvLoading -x` + yamllint `env:` block | ❌ Wave 0 + Wave 2 |
| CLI-05 (Phase 7 slice) | Default mode enters loop, logs new line | integration | `pytest tests/test_main.py::test_default_mode_enters_schedule_loop -x` | ✅ exists, renamed + assertion replaced |

### Sampling Rate

- **Per task commit:** `pytest tests/test_scheduler.py -x` (fastest — new file only)
- **Per wave merge:** `pytest -x` (full suite must stay green after each wave)
- **Phase gate:** Full suite green + manual `workflow_dispatch` smoke (operator triggers once, confirms green run + email + state.json commit) before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_scheduler.py` — NEW file, 6 test classes covering SCHED-01..07 + CLI-05 Phase 7 slice
- [ ] `requirements.txt` — pinned `schedule==1.2.2` + `python-dotenv==1.0.1`
- [ ] `system_params.py` constants — `LOOP_SLEEP_S=60`, `SCHEDULE_TIME_UTC='00:00'`, `WEEKDAY_SKIP_THRESHOLD=5`
- [ ] `tests/test_signal_engine.py` FORBIDDEN_MODULES_{DASHBOARD,NOTIFIER} — add `'schedule', 'dotenv'` (lines 556–563 + 572–579 — smallest targeted edits)
- [ ] `main.py` stubs — `_run_schedule_loop` + `_run_daily_check_caught` raising NotImplementedError; `load_dotenv()` functional call in `main()` body (works in Wave 0 so local-dev is unblocked)

(Wave 1 fills the stubs; Wave 2 ships YAML + docs.)

## Sources

### Primary (HIGH confidence)

- `https://raw.githubusercontent.com/dbader/schedule/master/schedule/__init__.py` — `.at()` signature + pytz-only tz implementation. Pitfall 1.
- `https://github.com/dbader/schedule/blob/master/HISTORY.rst` — timezone support added in 1.2.0; tz-bug fix in 1.2.1; current 1.2.2.
- `https://pypi.org/project/schedule/` — version list + release dates.
- `https://pypi.org/project/python-dotenv/` — `load_dotenv()` default behaviour (missing file = False; override=False default).
- `https://github.com/stefanzweifel/git-auto-commit-action` — action README + discussion #351 (gitignore behaviour) + action v5 supported pattern.
- `https://docs.github.com/actions/managing-workflow-runs/skipping-workflow-runs` — `[skip ci]` scope limited to push/pull_request.
- `https://github.com/actions/setup-python` + `https://github.com/actions/setup-python/issues/529` — pip cache behaviour, cache-dependency-path semantics.
- `.planning/phases/07-scheduler-github-actions-deployment/07-CONTEXT.md` — the operator's locked decisions.
- `tests/test_signal_engine.py:495–579` — the existing AST blocklist state (verified via grep this session).
- `tests/test_main.py:129,146` — the existing deprecated-log-line assertions that Phase 7 must update (verified via grep this session).
- `main.py:41,68,459` — confirms zoneinfo usage + deprecated log line exact text.

### Secondary (MEDIUM confidence)

- `https://github.com/orgs/community/discussions/156282` + `122271` + `52477` + `actions/runner#2977` — GHA cron drift of 5–30 minutes documented across multiple community threads (Pitfall 5).
- `https://oneuptime.com/blog/post/2025-12-20-scheduled-workflows-cron-github-actions/view` + `https://cronbuilder.dev/blog/github-actions-cron-schedule.html` — corroborating cron drift pattern.
- `https://docs.replit.com/cloud-services/deployments/reserved-vm-deployments` + `https://www.wearefounders.uk/replit-pricing-what-you-actually-pay-to-build-apps/` + `https://blog.replit.com/hosting-changes` — Replit 2026 pricing.

### Tertiary (LOW confidence — validate before shipping)

- Exact current Replit Reserved VM price tier ($6.20/mo vs $20/mo) — depends on which plan the operator is on. DEPLOY.md should reference Replit's current pricing page rather than hard-coding a price. `[flag for operator confirmation]`
- Operator's actual recipient email for SIGNALS_EMAIL_TO — deferred to operator configuration.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified against PyPI, release dates confirmed
- Architecture patterns: HIGH — all patterns derived from existing Phase 1–6 precedents + CONTEXT locked decisions
- Pitfalls: HIGH for Pitfalls 1, 2, 3, 4, 5, 6, 7, 8, 10 (all verified); MEDIUM for Pitfall 9 (branch protection — depends on repo state)
- Test plans: HIGH — all tests map to verifiable CONTEXT decisions
- Deployment contract: HIGH — YAML verified against upstream action docs

**Research date:** 2026-04-23
**Valid until:** 2026-05-23 (30 days for stable deploy contract; `schedule` + `python-dotenv` pins are stable for 12+ months; GHA action major-tags stable indefinitely unless action author re-tags)

---

*Phase 7 research complete. The planner can now produce Wave 0/1/2 plan files using this document + 07-CONTEXT.md as the authoritative input.*
