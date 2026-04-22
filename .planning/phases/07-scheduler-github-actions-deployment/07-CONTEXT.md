# Phase 7 — CONTEXT

**Phase:** 07 — Scheduler + GitHub Actions Deployment
**Created:** 2026-04-23
**Discuss mode:** discuss
**Goal (from ROADMAP.md):** Put the system on autopilot. A GitHub Actions cron workflow runs the app every weekday at 00:00 UTC (08:00 AWST) and commits `state.json` back to the repo; the `schedule`-library loop path is preserved for Replit/local dev with a weekday gate inside `run_daily_check`. Also flips Phase 4 default-mode behaviour from one-shot to run-once-then-enter-schedule-loop (CLI-05 Phase 7 completion).

**Requirements covered:** SCHED-01, SCHED-02, SCHED-03, SCHED-04, SCHED-05, SCHED-06, SCHED-07 (7 requirements) + Phase 7 completion slice of CLI-05 (default-mode loop).
**Out of scope (later phases):**
- Warning carry-over across runs (NOTF-10, Phase 8)
- Stale-state banner at startup (ERR-05, Phase 8)
- Top-level crash-email dispatch (ERR-04, Phase 8)
- Configurable starting account / contract tiers (CONF-01/02, Phase 8)

<domain>

## Phase Boundary

Phase 7 adds deployment + scheduling surface:
- `.github/workflows/daily.yml` — cron-driven GHA job that runs `python main.py --once`, then commits `state.json` back via `stefanzweifel/git-auto-commit-action@v5`.
- `schedule`-library loop inside `main.py` — Replit/local path. Runs an immediate first check then ticks `schedule.every().day.at('00:00')` (UTC) forever.
- Weekday gate inside `run_daily_check` — no-ops on Sat/Sun (AWST) for ALL invocation modes.
- `load_dotenv()` call at top of `main()` — unconditional; harmless when `.env` is absent.
- `docs/DEPLOY.md` — operator runbook: GHA quickstart + Replit alternative + env-var reference + troubleshooting.

Phase 7 does NOT change:
- The `run_daily_check(args) -> (rc, state, old_signals, run_date)` tuple signature (Phase 6 refactor holds).
- `--once` / `--test` / `--reset` / `--force-email` semantics (Phase 4/6 behaviour carries through unchanged; only default-mode flips).
- Any engine-side code (`signal_engine.py`, `sizing_engine.py`, `data_fetcher.py`, `state_manager.py`, `dashboard.py`, `notifier.py`).

</domain>

<canonical_refs>

External specs, ADRs, and prior CONTEXT docs that downstream agents MUST consult:

### Project-level
- `.planning/PROJECT.md` — Deployment target priority (GHA primary / Replit alternative); state-persistence expectation ("GitHub Actions mode commits `state.json` back to the repo"); schedule canonical line (`schedule.every().day.at("00:00")` UTC); secrets-via-env constraint; "never crash silently" error budget.
- `.planning/REQUIREMENTS.md` — SCHED-01..07 full text; CLI-05 Phase 7 completion slice; Out-of-Scope list (no live trading, single operator, no database).
- `.planning/ROADMAP.md` — Phase 7 goal + 5 success criteria (SC-1 GHA skeleton contract; SC-2 default-mode flip + weekday gate; SC-3 `--once` cleanly exits; SC-4 secrets via env vars; SC-5 docs position).
- `CLAUDE.md` — `[Sched]` log prefix locked; main.py is the ONLY module allowed to read the wall clock; 2-space indent / single quotes / snake_case; hex-lite boundaries; Perth (AWST UTC+8 no DST).
- `SPEC.md` — Project brief; Replit deployment notes; "8am AWST weekdays" schedule line; GHA alternative cron-schedule note.

### Prior phase CONTEXT docs (decisions that carry in unchanged)
- `.planning/phases/04-end-to-end-skeleton-fetch-orchestrator-cli/04-CONTEXT.md` — D-07 `--once` is Phase 4 alias for default-mode (Phase 7 flips default to schedule-loop; `--once` stays one-shot); D-08 per-instrument signal-state dict shape; D-13 AWST clock reader at the orchestrator edge; D-14 `[Sched]` opening/closing log lines; typed-exception boundary pattern in `main()` (Phase 7 extends the ladder, does not rebuild it).
- `.planning/phases/05-dashboard/05-CONTEXT.md` — `_render_dashboard_never_crash` pattern (import-inside-try); local import isolation as hex-lite protection.
- `.planning/phases/06-email-notification/06-CONTEXT.md` — D-15 `_send_email_never_crash` mirror of dashboard helper; `run_daily_check` 4-tuple return shape `(rc, state, old_signals, run_date)`; NOTF-07/NOTF-08 graceful-degradation on missing RESEND_API_KEY (Phase 7 does NOT add a startup preflight).
- `.planning/phases/06-email-notification/06-SUMMARY.md` (if present at plan time) — final email dispatch site inside `main()` (Phase 7 extends the same dispatch ladder; no rework).

### Source files Phase 7 will touch or reference
- `main.py` — argparse + dispatch ladder + `run_daily_check`. Phase 7 adds: `load_dotenv()` call, weekday-gate top of `run_daily_check`, factored schedule-loop driver, loop-level error catch.
- `system_params.py` — candidate home for new constants `SCHEDULE_TIME_UTC = '00:00'`, `LOOP_SLEEP_S = 60`, `WEEKDAY_SKIP_THRESHOLD = 5` (Sat index). Planner decides.
- `requirements.txt` — add pinned `schedule==1.2.x` + `python-dotenv==1.0.x` (researcher picks exact pins; enforce no `>=`).
- `tests/test_main.py` — existing CLI smoke tests. Phase 7 adds: weekday-gate tests, loop-driver tests via injected fakes, `load_dotenv` integration test.
- `tests/test_signal_engine.py::TestDeterminism::test_main_no_forbidden_imports` — extend FORBIDDEN_MODULES_MAIN exceptions list to allow `schedule` + `dotenv` for `main.py` only (all other modules still block them).
- `.python-version` — pyenv pin (already present at `3.11.8` per Phase 1 CONTEXT). Phase 7 GHA reads this via `setup-python@v5 python-version-file`.
- `.gitignore` — already excludes `.env`, `state.json` (locally), `dashboard.html`, `last_email.html`. Phase 7 confirms the list; GHA workflow commits `state.json` only — the gitignore does not cover commits made inside the action (stefanzweifel still commits ignored paths if `file_pattern` matches). No changes expected.
- `.env.example` — already populated by Phase 6 with `RESEND_API_KEY` + `SIGNALS_EMAIL_TO`. Phase 7 may add a comment block about GHA Secrets vs local `.env` but no new keys.

### New files Phase 7 creates
- `.github/workflows/daily.yml` — the GHA workflow.
- `docs/DEPLOY.md` — operator runbook.
- `tests/test_scheduler.py` (OR extend `tests/test_main.py` — planner picks) — loop-driver unit tests.

</canonical_refs>

<prior_decisions>

Decisions from earlier phases that apply to Phase 7 without re-asking:

- **GHA is PRIMARY, Replit is alternative** (operator decision baked into ROADMAP + PROJECT.md). Phase 7 docs reflect this ordering; Replit stays a working code path but the docs point operators at GHA first.
- **Cron: `0 0 * * 1-5` UTC** (CLAUDE.md + PROJECT.md + SPEC.md canonical line = 08:00 AWST weekdays). No DST math; Perth is UTC+8 year-round.
- **GHA workflow skeleton locked** (ROADMAP SC-1): `permissions: contents: write`, `concurrency: trading-signals`, `actions/checkout@v4`, `actions/setup-python@v5`, `stefanzweifel/git-auto-commit-action@v5`. These are not gray areas — they are operator-confirmed at roadmap time.
- **Hex-lite boundaries** (Phases 1–6): `main.py` is the ONLY module that may import `schedule`, `dotenv`, or read the wall clock. Pure-math and I/O-hex modules remain isolated. The AST blocklist `FORBIDDEN_MODULES_*` guards in `tests/test_signal_engine.py::TestDeterminism` MUST stay green after Phase 7 — `schedule` and `dotenv` are added to `FORBIDDEN_MODULES_STATE_MANAGER`, `FORBIDDEN_MODULES_DATA_FETCHER`, `FORBIDDEN_MODULES_DASHBOARD`, `FORBIDDEN_MODULES_NOTIFIER`, and stay absent from `FORBIDDEN_MODULES_MAIN` (main.py is their sole consumer).
- **Log prefixes** (CLAUDE.md): `[Sched]` is locked. Phase 7 uses it for: `[Sched] Run <date> mode=...`, `[Sched] weekend skip <date>`, `[Sched] loop tick`, `[Sched] loop error caught: ...`, `[Sched] scheduler entered; next fire <ISO>`.
- **Style** (CLAUDE.md): 2-space indent, single quotes, PEP 8 via ruff. `schedule.every().day.at('00:00').do(...)` is the canonical pattern.
- **Never-crash invariant** (CLAUDE.md): Scheduler loop must never propagate an exception out. Matches Phase 5/6 pattern — `_render_dashboard_never_crash`, `_send_email_never_crash` — Phase 7 adds `_run_schedule_tick_never_crash` (planner names the helper).
- **Structural read-only contract for `--test`** (Phase 4 CLI-01 + Phase 5 C-3 Option A): Unchanged. Weekday gate added in Phase 7 short-circuits BEFORE compute, so `--test` on a weekend still writes nothing to `state.json` — the existing `if args.test: return 0` path is unreachable on weekends, which is the desired outcome.
- **Timezone discipline** (CLAUDE.md + Phase 4 D-13 + Phase 4 D-01 amendment 2026-04-22): `run_date` is the ONLY AWST wall-clock timestamp — computed via `datetime.now(tz=AWST)` in `_compute_run_date`. `signal_as_of` is market-local. Weekday gate consults `run_date.weekday()` (AWST) to decide weekend-skip. The cron fires at 00:00 UTC = 08:00 AWST Mon–Fri, so `run_date` is ALWAYS Mon–Fri on GHA — the weekday gate is belt-and-braces but not redundant (covers manual `workflow_dispatch` + Replit loop + local dev).
- **html.escape discipline** (Phase 5 D-15 + Phase 6 inheritance): Phase 7 produces no user-visible HTML of its own, so inherits by non-use.
- **No new engine deps** (PROJECT.md stack lock): Phase 7 adds `schedule` + `python-dotenv` (both already in the stack allowlist). No `croniter`, no `APScheduler`, no `uvicorn`, no shell scripts.

</prior_decisions>

<folded_todos>

No pending todos matched Phase 7 scope. The one STATE.md todo that touched Phase 7 ("Document Replit Reserved VM path in Phase 7 deployment guide alongside GHA") is already folded into the scope as the `docs/DEPLOY.md` Replit-alternative section (D-11 below) — no separate tracking needed.

</folded_todos>

<decisions>

## Scheduler loop — architecture & resilience

- **D-01: Factored loop driver with injectable fakes.**
  `main.py` gains a new function (planner names it; recommendation: `_run_schedule_loop`) with the signature:
  ```python
  def _run_schedule_loop(
    job: Callable[[argparse.Namespace], tuple[int, dict | None, dict | None, datetime | None]],
    args: argparse.Namespace,
    scheduler=None,          # injected: defaults to `schedule` module
    sleep_fn=None,           # injected: defaults to time.sleep
    tick_budget_s: float = 60.0,  # loop sleep between schedule.run_pending calls
    max_ticks: int | None = None, # None = infinite loop (production)
  ) -> int:
  ```
  Production call: `_run_schedule_loop(run_daily_check, args)` — defaults flow through. Test call: `_run_schedule_loop(run_daily_check, args, scheduler=fake, sleep_fn=fake_sleep, max_ticks=1)` — one tick, no real sleep, no real scheduler thread. Returns 0 on graceful exit (only reachable in tests via `max_ticks`), or propagates whatever the final tick returned.
  Inside the loop:
  ```python
  # before entering loop: immediate first run (SCHED-02)
  _run_daily_check_caught(job, args)
  # register schedule + enter loop
  _scheduler = scheduler or schedule
  _sleep = sleep_fn or time.sleep
  _scheduler.every().day.at('00:00').do(_run_daily_check_caught, job, args)
  ticks = 0
  while max_ticks is None or ticks < max_ticks:
    _scheduler.run_pending()
    _sleep(tick_budget_s)
    ticks += 1
  return 0
  ```
  `_run_daily_check_caught` is the never-crash adapter (D-02). The injection pattern mirrors Phase 5/6 testability — injected collaborators default to None + lazy-resolve to the real thing at call site.

- **D-02: Loop catches + logs + keeps ticking (never-crash scheduler).**
  New helper `_run_daily_check_caught(job, args) -> None` wraps `job(args)` in a try/except:
  ```python
  def _run_daily_check_caught(job, args) -> None:
    '''D-02: schedule loop survives one bad run. Next cron fire retries.

    Mirrors Phase 5 _render_dashboard_never_crash + Phase 6 _send_email_never_crash.
    ONLY valid `except Exception:` site in the loop path. Phase 8 (ERR-04 top-level
    crash handler) adds the crash-email dispatch on top of this same net.
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
  Rationale: operator confirmed "catch + log + keep ticking" in discuss. One bad Yahoo fetch should not kill a scheduler that already survived through six successful runs. Failures propagate via the next email's WARN banner once Phase 8 (NOTF-10 warnings carry-over) lands.

- **D-03: Weekday gate inside `run_daily_check`, applies to ALL modes.**
  First executable line of `run_daily_check` (after `run_date = _compute_run_date()` computes AWST wall-clock):
  ```python
  if run_date.weekday() >= 5:  # 5=Sat, 6=Sun
    logger.info(
      '[Sched] weekend skip %s (weekday=%d) — no fetch, no state mutation',
      run_date.strftime('%Y-%m-%d'), run_date.weekday(),
    )
    return 0, None, None, run_date
  ```
  Applies to: default/loop mode, `--once`, `--force-email`, `--test`, `--reset` (actually `--reset` goes through `_handle_reset` which does not call `run_daily_check` — not affected). This matches SC-2: "internal weekday gate that no-ops on Sat/Sun even if invoked". Returning `(0, None, None, run_date)` preserves the 4-tuple contract; the dispatch ladder in `main()` (Phase 6 D-15) already handles `state is None` by skipping the email send (Phase 6 Fix 10 defensive guard becomes the primary path on weekends, not defense-in-depth).
  Rationale confirmed in discuss: belt-and-braces against GHA cron misconfiguration, Replit-loop firing on non-business days, local-dev runs outside weekday hours.

- **D-04: Immediate first-run before entering schedule loop (SCHED-02).**
  Default-mode dispatch in `main()` becomes:
  ```python
  # Default (no --once / --test / --force-email / --reset): Phase 7 loop path
  # Immediate first run per SCHED-02 — also honours the weekday gate (D-03)
  _run_daily_check_caught(run_daily_check, args)
  # Enter loop forever (production) — returns only via exception or SIGINT
  return _run_schedule_loop(run_daily_check, args)
  ```
  The immediate first run honours the weekday gate naturally (D-03 fires if it's a weekend). Without this explicit first call, a process started Mon 09:00 would not fire until Tue 08:00. Matches SPEC.md "Run immediately on start".

## CLI dispatch ladder amendments

- **D-05: Default mode flips from one-shot to schedule-loop.**
  Phase 4 D-07 made default == `--once`. Phase 7 amends this:
  - `--once` remains one-shot (unchanged — SC-3 + CLI-04).
  - Default (no flag) becomes: immediate first run via `_run_daily_check_caught`, then `_run_schedule_loop(run_daily_check, args)`.
  The Phase 4 log line `'[Sched] One-shot mode (scheduler wiring lands in Phase 7)'` is DELETED from `run_daily_check`. A new log line lands inside `_run_schedule_loop` at scheduler-entry:
  ```python
  logger.info('[Sched] scheduler entered; next fire 00:00 UTC (08:00 AWST) Mon–Fri')
  ```
  CLI-05 Phase 7 completion slice fully delivered.

- **D-06: dotenv loads unconditionally at top of `main()`.**
  Inside `main(argv)` as the first call, BEFORE `_build_parser`:
  ```python
  def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv  # local import for AST-blocklist + C-2 pattern
    load_dotenv()  # no-op when .env absent; env vars take precedence over .env per dotenv docs
    parser = _build_parser()
    ...
  ```
  Local import inside `main()` mirrors the Phase 5 C-2 / Phase 6 D-15 pattern — keeps `dotenv` out of module-top imports so `FORBIDDEN_MODULES_MAIN` checks stay meaningful (only `main.py`'s `main()` body imports it). dotenv semantics: missing `.env` is silently fine; env vars set by GHA/Replit take precedence over `.env` file contents (load_dotenv default override=False). This gives the operator:
  - **Local:** `.env` file works.
  - **GHA:** no `.env`, secrets come from `env:` block + GitHub Secrets.
  - **Replit:** no `.env`, secrets come from Replit Secrets tab (inherited into process env).

## GitHub Actions workflow

- **D-07: `.github/workflows/daily.yml` contents (SC-1 + SC-3 + SC-7).**
  Skeleton (planner writes exact YAML; this is the contract):
  ```yaml
  name: Daily signal check
  on:
    schedule:
      - cron: '0 0 * * 1-5'   # 00:00 UTC = 08:00 AWST Mon–Fri
    workflow_dispatch: {}      # D-08: manual trigger for rerun-a-day
  permissions:
    contents: write            # SC-1: required for git-auto-commit-action
  concurrency:
    group: trading-signals     # SC-1: serialise concurrent cron + dispatch runs
    cancel-in-progress: false  # don't kill an in-flight run if dispatch fires
  jobs:
    daily:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4                          # SC-1
        - uses: actions/setup-python@v5                      # SC-1 + D-09
          with:
            python-version-file: '.python-version'           # D-09
            cache: 'pip'                                     # D-09
            cache-dependency-path: requirements.txt
        - name: Install deps
          run: python -m pip install --upgrade pip && pip install -r requirements.txt
        - name: Run daily check
          env:
            RESEND_API_KEY:   ${{ secrets.RESEND_API_KEY }}
            SIGNALS_EMAIL_TO: ${{ secrets.SIGNALS_EMAIL_TO }}
          run: python main.py --once
        - uses: stefanzweifel/git-auto-commit-action@v5      # SC-1 + D-10
          if: success()                                      # D-11: no commit on fail
          with:
            commit_message: 'chore(state): daily signal update [skip ci]'
            file_pattern: state.json
            commit_user_name: github-actions[bot]
            commit_user_email: 41898282+github-actions[bot]@users.noreply.github.com
  ```
  Triggers, permissions, concurrency, and commit step ALL derive from ROADMAP SC-1. The `env:` block under "Run daily check" explicitly exposes only the two env vars Phase 7 formally documents (D-12) — no secret leakage via bulk `env: ${{ secrets }}` mapping.

- **D-08: `workflow_dispatch` manual trigger included.**
  Empty `{}` payload means no inputs — operator clicks "Run workflow" in the Actions tab and the same cron job fires. Useful when operator wants to rerun today's signal (e.g. after fixing a secret) without waiting for 08:00 AWST.

- **D-09: pip cache + Python version pin.**
  `actions/setup-python@v5` with `cache: 'pip'` and `python-version-file: '.python-version'`:
  - **cache: 'pip'** reduces install time from ~30s to ~5s on warm runs (ROADMAP SC-7 operator ergonomics without adding cost).
  - **python-version-file: '.python-version'** uses the existing pyenv pin (`3.11.8`) as the single source of truth — prevents drift between local dev and GHA.
  `cache-dependency-path: requirements.txt` scopes the cache key to the pin file. When `requirements.txt` changes (Phase 7 adds `schedule` + `python-dotenv`), the cache invalidates automatically.
  Failure-notification path DEFERRED (decided against in discuss) — GitHub's built-in email-on-workflow-failure notification is sufficient for single-operator.

- **D-10: Commit `state.json` only.**
  `file_pattern: state.json` — nothing else. Rationale confirmed in discuss:
  - `dashboard.html` is gitignored locally and regenerated every run — committing would balloon git history with ~40kb of HTML diff per day.
  - `last_email.html` is a fallback artefact for missing `RESEND_API_KEY` — it should never exist in GHA (secrets are configured) and has zero value in history.
  - `state.json` is the single source of truth + the only file that needs cross-run persistence on GHA's ephemeral filesystem.
  Commit message `'chore(state): daily signal update [skip ci]'` — the `[skip ci]` token prevents the commit itself from re-triggering any CI jobs (defensive; Phase 7 has no CI workflow beyond `daily.yml`, but future Phase 8 hardening may add one).

- **D-11: No commit on job failure (`if: success()`).**
  Explicit `if: success()` on the commit step ensures:
  - Failed `python main.py --once` (non-zero exit from DataFetchError / ShortFrameError / unhandled crash) → no commit → `state.json` stays at yesterday's value → operator sees red ❌ in Actions UI → next weekday's run retries with yesterday's state.
  - `save_state` is already structurally atomic (Phase 3 `_atomic_write`) — partial-write scenarios are not possible. So "no commit on fail" is the right posture; there is no half-state worth committing.

## Env vars, secrets, and graceful degradation

- **D-12: Formal deploy env-var contract = `RESEND_API_KEY` + `SIGNALS_EMAIL_TO`.**
  These are the ONLY two env vars documented in `docs/DEPLOY.md` as "required for deploy":
  - `RESEND_API_KEY` — required for email dispatch. Phase 6 NOTF-08 fallback handles missing value at local-dev time; production (GHA / Replit) MUST have it configured.
  - `SIGNALS_EMAIL_TO` — recipient override; falls back to Phase 6 D-14 default when unset.
  NOT in the formal contract:
  - `RESET_CONFIRM` — operator-facing dev tool only (used by `_handle_reset` to skip the interactive `input()` prompt in CI + tests). Document in a separate "Dev + CI env vars" subsection but not as "required for deploy".
  - `ANTHROPIC_API_KEY` — ROADMAP SC-4 mentions this as "optional" but NOTHING in the current codebase reads it. Phase 7 DROPS it from the formal contract; ROADMAP SC-4 amended in the plan to match ("All secrets (`RESEND_API_KEY`, `SIGNALS_EMAIL_TO`) are loaded from env vars..."). If a future phase introduces LLM-backed summarisation, the env var gets added THEN.
  - `FROM_EMAIL` — SPEC.md mentions this but Phase 6 hardcoded the sender (`signals@carbonbookkeeping.com.au`) as a Resend-verified-domain invariant per D-14. No Phase 7 change.

- **D-13: Missing `RESEND_API_KEY` keeps Phase 6 graceful-degradation behaviour.**
  No startup preflight. Phase 7 does NOT add `if not os.environ.get('RESEND_API_KEY'): sys.exit(2)` at the top of `main()`. Rationale:
  - NOTF-08 already handles this path cleanly (writes `last_email.html` + logs WARN).
  - Local dev should work without any secrets configured — preserves "clone → `pip install -r requirements.txt` → `python main.py --once`" happy path.
  - GHA: if the secret is misconfigured, the email step fails gracefully; the workflow succeeds on the compute side and commits `state.json`; operator sees the absence of their morning email and investigates.
  The `docs/DEPLOY.md` troubleshooting section (D-15) calls out this failure mode explicitly: "If no email arrived but `state.json` was committed, check that `RESEND_API_KEY` is set under Actions → Secrets."

## Deployment documentation

- **D-14: `docs/DEPLOY.md` is the single operator runbook.**
  New file at `docs/DEPLOY.md`. Linked from `README.md` (new top-level README if absent, OR a brief pointer if one exists — planner checks). Three sections + env ref + troubleshooting:
  1. **Quickstart — GitHub Actions (primary):**
     - Fork / clone the repo.
     - Add Secrets under repo → Settings → Secrets and variables → Actions:
       - `RESEND_API_KEY` (required)
       - `SIGNALS_EMAIL_TO` (required)
     - Enable Actions: Settings → Actions → "Allow all actions and reusable workflows".
     - Verify: Actions tab → Daily signal check → "Run workflow" (manual dispatch) → confirm green run + email arrives.
     - Wait for first scheduled run at 00:00 UTC (08:00 AWST) next weekday.
  2. **Alternative — Replit (Reserved VM + Always On):**
     - Why Replit is an alternative not primary: Replit Autoscale cold-starts kill the `schedule` loop; Replit Reserved VM + Always On ($20/mo) is required for persistence; GHA is free and stateless-by-design.
     - Setup: Replit project → Secrets tab → add `RESEND_API_KEY` + `SIGNALS_EMAIL_TO`.
     - Enable Reserved VM + Always On under Replit project settings.
     - Click Run; `python main.py` enters the schedule loop automatically (Phase 7 default-mode flip).
     - **Filesystem-persistence caveat:** Replit Reserved VM persists `state.json` across runs. Replit Autoscale DOES NOT — autoscale resets filesystem on each cold start, so the Replit path must use Reserved VM.
  3. **Troubleshooting:**
     - "Green run but no email" → check `RESEND_API_KEY` secret (D-13).
     - "Run failed with DataFetchError" → Yahoo Finance outage; next weekday's run retries automatically.
     - "State.json commit conflict" → manual edit during a cron run; operator resolves the git conflict manually. Never force-push (CLAUDE.md safety).
     - "Scheduler loop crashed on Replit" → check Replit console logs; `schedule.every().day.at('00:00')` requires process persistence — verify Always On is active.

- **D-15: Depth = quickstart + env contract + troubleshooting (~150 lines).**
  No screenshots; single operator, no team onboarding. No full runbook. Enough to recover from a broken deploy without reading source code.

- **D-16: Replit alternative stays production-viable code.**
  The schedule-loop path (`_run_schedule_loop` + immediate first-run + weekday gate) is real tested code — NOT placeholder. Unit-tested via injected fakes (D-01). `docs/DEPLOY.md` notes the Replit-specific caveats (Reserved VM required; Always On required) but does NOT mark the code path as experimental or untested. If GHA ever becomes unviable (rate limits, cost changes, etc.), operator can flip to Replit with minimal friction.

## Claude's Discretion

Left to researcher/planner/executor:

- Exact name of the loop driver (`_run_schedule_loop` recommended; alternatives like `_schedule_main`, `_daily_loop` acceptable).
- Exact name of the never-crash wrapper (`_run_daily_check_caught` recommended).
- Whether loop tick sleep is a module-level constant in `system_params.py` (`LOOP_SLEEP_S = 60`) OR an inline default inside `_run_schedule_loop` (recommendation: `system_params.py` constant for grep-ability + test override parity with other Phase 1–6 constants).
- Exact number of unit tests for the loop driver (minimum: (a) max_ticks terminates cleanly, (b) fake_scheduler.run_pending is called, (c) fake_sleep is called with tick_budget_s, (d) loop catches DataFetchError without exiting, (e) immediate first-run fires before loop entry, (f) weekday-gate on a Sunday returns early without touching state). Planner expands as needed.
- How to name the test file (`tests/test_scheduler.py` vs extending `tests/test_main.py`). Recommendation: new `tests/test_scheduler.py` since Phase 7 adds a new concern; keeps `test_main.py` focused on CLI + orchestrator.
- Whether to add a `__main__.py` / entry point wrapper to let operators run `python -m trading_signals` (recommendation: NO — `python main.py --once` is the canonical invocation and matches GHA + Replit docs).
- Precise `schedule` + `python-dotenv` version pins (researcher picks bit-locked versions following Phase 1–6 pinning convention).
- Whether `docs/DEPLOY.md` gets a "Cost estimate" subsection (GHA runner minutes usage per month × per-minute cost). Recommendation: YES — single sentence showing this is comfortably inside the 2000-minute free tier.
- Whether `README.md` is created / updated at Phase 7 or deferred. Recommendation: create a minimal top-level `README.md` at Phase 7 if absent (~50 lines: what the project is + one-liner pointer to `docs/DEPLOY.md` + `SPEC.md`).
- Whether the GHA `file_pattern` also covers the corrupt-state backup files (`state.json.corrupt.<timestamp>`) — recommendation: NO (corrupt-state backup belongs in Phase 8 ERR-03 scope + operator should pull those files manually if they ever appear; committing them creates noise).

## Phase 7 Scope Boundaries (what NOT to do)

- No `croniter`, no `APScheduler`, no shell-based cron. `schedule`-library only (PROJECT.md stack lock).
- No Docker, no container image, no `docker-compose.yml` — the project runs on bare Python.
- No `systemd` unit file for Linux deployment (Replit + GHA cover both ends of the spectrum).
- No GHA self-hosted runner — `ubuntu-latest` is sufficient.
- No secret rotation automation, no Doppler / 1Password / Vault integration.
- No CI workflow beyond `daily.yml` (no PR-test workflow in Phase 7; that is a separate hardening concern if ever needed).
- No health-check endpoint, no uptime monitoring (single-operator; the morning email IS the health check).
- No stale-state banner at startup — that is ERR-05, Phase 8.
- No crash-email dispatch at top-level exception — that is ERR-04, Phase 8.
- No warnings carry-over across runs — that is NOTF-10, Phase 8.
- No changes to Phase 6 email dispatch semantics — `--force-email` + `--test` behave exactly as in Phase 6.
- No amendment to the `run_daily_check` 4-tuple return contract — weekday gate returns `(0, None, None, run_date)` which the dispatch ladder already handles (Phase 6 Fix 10).

</decisions>

<code_context>

## Existing Code Insights

### Reusable assets (Phase 7 references them, does not rebuild)
- `main.py::_compute_run_date` — AWST wall-clock reader. Weekday gate consumes its output directly (`run_date.weekday()`).
- `main.py::_render_dashboard_never_crash` + `_send_email_never_crash` — never-crash wrapper pattern. D-02's `_run_daily_check_caught` is the third instance of this pattern.
- `main.py::run_daily_check` — existing 9-step orchestrator. Phase 7 prepends ONE line (weekday gate, D-03) at the top, immediately after `run_date = _compute_run_date()`. No other changes.
- `main.py::main`'s typed-exception boundary + dispatch ladder — Phase 7 amends ONE branch (default path) to call the loop driver; all other branches (`--reset`, `--force-email`, `--test`, `--once`) stay unchanged.
- `system_params.py` — established home for pinned constants (palette, contract specs, schema version). Phase 7 adds `LOOP_SLEEP_S = 60`, `SCHEDULE_TIME_UTC = '00:00'`, `WEEKDAY_SKIP_THRESHOLD = 5`.
- `.python-version` at `3.11.8` — the canonical Python version. GHA reads it via `setup-python@v5 python-version-file`.
- `.env.example` — Phase 6 populated with `RESEND_API_KEY` + `SIGNALS_EMAIL_TO`. Phase 7 adds header comments about GHA Secrets vs Replit Secrets.
- `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` — AST blocklist. Phase 7 extends every engine's `FORBIDDEN_MODULES_*` to include `schedule` + `dotenv` (main.py alone imports them).

### Established patterns
- **Local imports for hex-boundary + never-crash isolation** (Phase 5 C-2, Phase 6 D-15). Phase 7 applies the same pattern to `from dotenv import load_dotenv` (inside `main()`) and `import schedule` (inside `_run_schedule_loop`).
- **Injected collaborators with `None`-default + lazy-resolve** — Phase 5 renderer testability pattern. Phase 7 uses it for scheduler + sleep_fn in `_run_schedule_loop`.
- **Structured log lines with `[Prefix]` token** — CLAUDE.md §Log prefixes. Phase 7 reuses `[Sched]` exclusively.
- **Atomic file writes + no side-effects-on-fail** — Phase 3 `_atomic_write`. GHA workflow mirrors this at the process level via `if: success()` on the commit step (D-11).
- **Fixture-driven testing with frozen clocks** — Phase 1–6 `pytest-freezer`. Phase 7 weekday-gate tests freeze AWST wall-clock to Sat/Sun/Mon/Fri dates and assert the right branch fires.

### Integration points
- `main.py::main()` dispatch ladder (single edit: default-mode branch).
- `run_daily_check` top (single edit: weekday-gate prelude).
- `requirements.txt` (two new pinned lines).
- `.gitignore` (no changes expected; `.env`, `state.json` locally, `dashboard.html`, `last_email.html` already excluded).
- `tests/test_signal_engine.py::TestDeterminism` AST blocklist (extend engine blocklists; main.py list gets `schedule` + `dotenv` in its allowed-imports allowlist).

### Creative options the codebase enables
- `_run_schedule_loop`'s `max_ticks` parameter is test-only in Phase 7 but could later support Phase 8 graceful-shutdown if an operator signals SIGTERM.
- The `_run_daily_check_caught` wrapper becomes the natural hook site for Phase 8 ERR-04 crash-email dispatch — one `except Exception` already in the right place.

</code_context>

<specifics>

## Specific Ideas

- Weekday gate belt-and-braces rationale: `run_date.weekday() >= 5` fires on AWST Saturday + Sunday regardless of how the process was invoked. GHA cron `1-5` is already weekday-only; combining the two means:
  - If operator misconfigures GHA cron to `* * * * *`, the weekday gate still prevents weekend execution.
  - If operator triggers `workflow_dispatch` manually on a Saturday, the run logs `[Sched] weekend skip ...` and exits clean.
  - If Replit's in-process loop fires through a weekend (process stays alive Fri → Mon), the gate protects against a Saturday fire on a mis-set timezone.
- Loop error-handling intent: operator prefers "one bad day is a WARN, not a crash" because a crash on Replit requires manual restart; on GHA a crash merely prevents today's commit (workflow exits non-zero, next weekday retries). The Phase 6 graceful-degradation posture extends naturally to the scheduler.
- `docs/DEPLOY.md` tone: operator runbook, not marketing copy. Bullet-heavy, minimal prose, every command copy-pastable.
- GHA workflow simplicity: no matrix strategy, no multiple jobs, no conditional steps beyond `if: success()` on the commit. One flat job, five steps.

</specifics>

<deferred>

## Deferred Ideas

Items surfaced during discussion that do NOT belong in Phase 7:

- **Resend failure → crash email** — belongs to Phase 8 ERR-04.
- **Stale-state banner at startup** — Phase 8 ERR-05.
- **Warning carry-over to next email** — Phase 8 NOTF-10.
- **Configurable starting account + contract tiers** — already folded into Phase 8 as CONF-01/02.
- **LLM-backed daily summary** — triggered ROADMAP SC-4's `ANTHROPIC_API_KEY` mention. Not in v1 scope at all; revisit as a v2 feature.
- **Failure notification via Resend** — built-in GitHub email on workflow failure is sufficient for single-operator; revisit only if GH's notifications prove unreliable.
- **Replit integration tests (end-to-end shadow run)** — high-effort; GHA is primary. Revisit only if operator decides to flip primary deployment path.
- **Multi-recipient fan-out / Slack / SMS** — deferred to v2 (REQUIREMENTS.md V2-DEL-01, V2-DEL-02).
- **Docker/container deployment** — not requested; out of stack allowlist.
- **Health-check endpoint** — the morning email IS the health check for single-operator.
- **State.json restore / rollback flag** — V2-REL-01.
- **Full-runbook-with-screenshots documentation** — operator chose lean runbook in discuss.
- **`README.md` as the deploy doc home** — rejected in favour of dedicated `docs/DEPLOY.md`; README gets a pointer only.
- **Cost estimate subsection in deploy docs** — noted as recommended under Claude's Discretion; planner decides final inclusion.

### Reviewed Todos (not folded)

None — the one STATE.md todo that touched Phase 7 ("Document Replit Reserved VM path in Phase 7 deployment guide alongside GHA") IS folded directly into D-14's Replit-alternative section, not deferred.

</deferred>

<downstream_notes>

### For the researcher (gsd-phase-researcher)

- Confirm the exact version pins for `schedule` (1.2.x series) and `python-dotenv` (1.0.x series). Verify both support Python 3.11.8 and have no open CVEs at pin time.
- Confirm `schedule.every().day.at('00:00').do(fn, *args)` passes `*args` through to `fn` on each fire (it does — but regenerator tests should prove it). Check the documented semantics of `run_pending()` in the face of scheduled jobs that run long (does the next tick queue or drop?).
- Confirm `stefanzweifel/git-auto-commit-action@v5` behavior when `file_pattern` matches an ignored path: does it commit anyway? (Answer expected: yes — git add overrides .gitignore when explicitly pathed; researcher verifies.)
- Confirm `actions/setup-python@v5` `cache: 'pip'` + `cache-dependency-path: requirements.txt` key generation: cache invalidates when requirements.txt changes? (Expected: yes.)
- Confirm `python-dotenv` `load_dotenv()` default behaviour: missing `.env` raises no error? (Expected: returns False silently.) Env vars set by the shell take precedence over `.env` values? (Expected: yes by default; `override=False` is the default.)
- Confirm AWST weekday semantics: `datetime.now(tz=ZoneInfo('Australia/Perth')).weekday()` returns 0 for Monday, 5 for Saturday, 6 for Sunday. (Python stdlib contract.)
- Investigate GHA schedule drift: documented as "may be delayed during high-traffic periods", sometimes 10-15 min late; researcher flags this to operator expectations in `docs/DEPLOY.md` troubleshooting section.
- Check whether `workflow_dispatch` without inputs requires a specific YAML form (`{}` is the canonical "no inputs" form; verify).
- Investigate `[skip ci]` token in commit message — confirm GitHub honours it even for scheduled / workflow_dispatch-triggered commits (it does; commits by `github-actions[bot]` also skip CI by default for any workflow not listing `workflows:` filter that includes bot commits).

### For the planner (gsd-planner)

Likely plan breakdown (planner refines):

- **Wave 0 (07-01) BLOCKING scaffold:**
  - `requirements.txt` additions: `schedule==1.2.x`, `python-dotenv==1.0.x` (researcher picks pins).
  - `system_params.py` additions: `LOOP_SLEEP_S`, `SCHEDULE_TIME_UTC`, `WEEKDAY_SKIP_THRESHOLD`.
  - `main.py` stubs: `_run_daily_check_caught`, `_run_schedule_loop` raising `NotImplementedError`; `load_dotenv()` call at top of `main()` (functional in Wave 0 so local-dev already works).
  - `tests/test_scheduler.py` skeleton (6 test classes: TestWeekdayGate, TestImmediateFirstRun, TestLoopDriver, TestLoopErrorHandling, TestDefaultModeDispatch, TestDotenvLoading).
  - AST blocklist extension: `FORBIDDEN_MODULES_{STATE_MANAGER,DATA_FETCHER,DASHBOARD,NOTIFIER}` add `schedule` + `dotenv`; `FORBIDDEN_MODULES_MAIN` allows them (confirm current allowlist structure).
  - `.env.example` header comments about GHA Secrets / Replit Secrets.

- **Wave 1 (07-02) body — schedule loop + weekday gate + dispatch ladder:**
  - Fill `_run_daily_check_caught` (D-02).
  - Fill `_run_schedule_loop` (D-01) with injected fakes support.
  - Prepend weekday gate (D-03) to `run_daily_check`.
  - Amend `main()` default-mode branch (D-04 + D-05): immediate first run + enter loop.
  - Delete Phase 4 stub log line `'[Sched] One-shot mode (scheduler wiring lands in Phase 7)'`.
  - Populate TestWeekdayGate, TestImmediateFirstRun, TestLoopDriver, TestLoopErrorHandling, TestDefaultModeDispatch, TestDotenvLoading.
  - Verify Phase 4/5/6 test suite remains green after weekday-gate prepend (frozen-clock tests already use weekdays).

- **Wave 2 (07-03) PHASE GATE — GHA workflow + docs:**
  - Write `.github/workflows/daily.yml` per D-07.
  - Write `docs/DEPLOY.md` per D-14/D-15/D-16.
  - Create / amend `README.md` with deploy-docs pointer.
  - ROADMAP SC-4 amendment: drop `ANTHROPIC_API_KEY`, keep only `RESEND_API_KEY` + `SIGNALS_EMAIL_TO` (D-12).
  - End-to-end verification: local `python main.py --once` runs green; `python main.py` enters loop and can be Ctrl-C'd cleanly; `python main.py --test` on a weekend logs weekend-skip.

- Testability pattern: Phase 1–6 all used injected collaborators (scheduler, sleep_fn, state_manager, notifier) to avoid heavy monkeypatching. Phase 7 continues this — D-01's `scheduler` + `sleep_fn` parameters default to None and lazy-resolve to `schedule` + `time.sleep` only at production runtime.
- Frozen-clock discipline: `pytest-freezer` + `PERTH.localize(datetime(...))` (never `datetime(..., tzinfo=pytz.timezone(...))`) — Phase 5/6 caught this pattern twice; Phase 7 enforces in the weekday-gate tests.

### For the reviewer (cross-AI after plans written — `/gsd-review 7`)

Watch for:
- `load_dotenv()` inadvertently leaking into module-top imports in any file other than `main.py` (AST blocklist must still flag it).
- Weekday gate bypass — any dispatch path that calls `run_daily_check` but forgets to honour the `(0, None, None, run_date)` return shape (triggers Phase 6 Fix 10 None-guard; no crash but would still try to send an email with `state=None` → NoneType attribute error caught by `_send_email_never_crash`; still a bug).
- GHA workflow `permissions: contents: write` scope — must NOT include `issues: write` or `pull-requests: write` (principle of least privilege).
- `stefanzweifel/git-auto-commit-action@v5` — ensure the version is pinned to a major tag (not a SHA); major-tag follows semver fixes from the action author.
- Secret names in `docs/DEPLOY.md` must EXACTLY match the names used in `daily.yml` `env:` block (`RESEND_API_KEY`, `SIGNALS_EMAIL_TO` — no casing drift).
- Immediate first-run ordering: must fire BEFORE `schedule.every().day.at(...).do(...)` registers, so the first call runs synchronously (not via the scheduler).
- `if: success()` on commit step — NOT `always()` and NOT missing (either would commit on failure per D-11 rejection).
- ROADMAP SC-4 amendment — must be part of the Phase 7 plan commit, not a separate chore commit (keeps milestone history coherent).
- The DELETION of `'[Sched] One-shot mode (scheduler wiring lands in Phase 7)'` — existing Phase 4 tests reference this string (`tests/test_main.py:129,146`). Those tests need updating in the same plan; cross-AI watches for stale test references.

</downstream_notes>

## Next Step

Run `/gsd-plan-phase 7` to produce `07-RESEARCH.md` + `07-PATTERNS.md` + plan files.

---

*Phase: 07-scheduler-github-actions-deployment*
*Context gathered: 2026-04-23*
