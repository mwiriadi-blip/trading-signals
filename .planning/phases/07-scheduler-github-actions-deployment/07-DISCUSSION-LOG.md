# Phase 7: Scheduler + GitHub Actions Deployment — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-23
**Phase:** 07-scheduler-github-actions-deployment
**Areas discussed:** Scheduler loop behavior, GHA workflow contract, Secrets + env loading, Deployment guide format

---

## Gray area selection

| Option | Description | Selected |
|--------|-------------|----------|
| Scheduler loop behavior | Weekday gate placement + semantics, error-recovery inside the in-process schedule loop (catch+continue vs crash-out), testability of the loop driver. | ✓ |
| GHA workflow contract | Commit-back scope, commit message format, workflow_dispatch manual trigger, pip cache, Python version pin, failure-notification path. | ✓ |
| Secrets + env loading | load_dotenv() site, missing-key fail-fast vs graceful, GHA secrets to mirror, startup preflight check. | ✓ |
| Deployment guide format | Docs location (README vs docs/DEPLOY.md vs SUMMARY), depth (quickstart vs runbook), Replit fidelity. | ✓ |

**All four areas selected for discussion.**

---

## Scheduler loop behavior

### Q1: When run_daily_check raises inside the in-process schedule loop (Replit path), what should the loop do?

| Option | Description | Selected |
|--------|-------------|----------|
| Catch + log + keep ticking (Recommended) | Warning-log the failure and continue looping. Matches Phase 5/6 never-crash posture; one bad Yahoo fetch doesn't kill the process. Operator sees the error in next email's stale/warning banner (Phase 8). | ✓ |
| Crash the process | Let the exception propagate out of the loop. Replit Always On restarts the process; GHA cron already retries next day. Simpler code, but one flaky Yahoo response kills the scheduler until restart. | |
| Catch N times then crash | Count consecutive failures; after N (e.g. 3) exit non-zero so Replit/supervisord restarts cleanly. More complex state to track. | |

**User's choice:** Catch + log + keep ticking (Recommended)
**Notes:** Aligns with existing Phase 5/6 never-crash wrappers (`_render_dashboard_never_crash`, `_send_email_never_crash`).

### Q2: SCHED-03 says run_daily_check has an internal weekday gate. What scope + behavior?

| Option | Description | Selected |
|--------|-------------|----------|
| Gate inside run_daily_check, applies to all modes (Recommended) | Check run_date.weekday() >= 5 (Sat/Sun AWST) at the top of run_daily_check, log '[Sched] weekend skip' + return (0, None, None, run_date) without fetching. --once, default, --force-email, --test all honor it. GHA's cron `1-5` + internal gate = belt-and-braces. | ✓ |
| Gate inside run_daily_check, but --force-email + --test bypass | Weekend skip for normal daily runs, but operator-initiated flags bypass so Marc can test on weekends. Subtle but maybe useful for manual verification. | |
| Gate at wrapper (schedule-loop-only) | Loop wrapper checks weekday before calling run_daily_check; --once and GHA path always run. Leaves run_daily_check itself pure. But the SC wording explicitly says 'internal weekday gate' — this choice contradicts SC-2. | |

**User's choice:** Gate inside run_daily_check, applies to all modes (Recommended)
**Notes:** Belt-and-braces posture; SC-2 is honoured literally.

### Q3: How do we test the schedule-loop driver without the pytest suite hanging?

| Option | Description | Selected |
|--------|-------------|----------|
| Extract tick function + mock schedule + time.sleep (Recommended) | Split main() into _run_schedule_loop(clock=schedule, sleep_fn=time.sleep, exit_after_n_ticks=None). Tests pass fakes: fake schedule that calls do() once, fake sleep_fn that returns immediately, exit_after_n_ticks=1. Loop body is testable; driver is thin. | ✓ |
| Monkeypatch schedule.run_pending + time.sleep | Let main() keep calling schedule.run_pending/time.sleep directly; tests monkeypatch both. Less factoring, more patching magic. Risk: missing a monkeypatch hangs the test. | |
| Don't test the loop driver | Test the weekday gate + run_daily_check standalone. Trust that schedule.every().day.at('00:00').do() plus a while-true + sleep is too thin to break. Smoke-test manually via a one-minute cron on first deploy. | |

**User's choice:** Extract tick function + mock schedule + time.sleep (Recommended)
**Notes:** Mirrors Phase 5/6 injected-collaborator testability pattern.

---

## GHA workflow contract

### Q1: What does the GHA workflow commit back to the repo after each run?

| Option | Description | Selected |
|--------|-------------|----------|
| state.json only (Recommended) | Just the one source-of-truth file. dashboard.html + last_email.html stay gitignored. Keeps the commit history clean — one-line-per-day state deltas only. stefanzweifel/git-auto-commit-action file_pattern: 'state.json'. | ✓ |
| state.json + dashboard.html | Commits both so the GitHub repo page has a browsable current dashboard. Adds ~30-50kb HTML diff per day to history. Means dashboard.html needs to leave .gitignore. | |
| state.json + dashboard.html + last_email.html | All three. Lets operator review past emails from the repo history. Largest history footprint; likely overkill. | |

**User's choice:** state.json only (Recommended)

### Q2: When run_daily_check fails (DataFetchError, crash), what should the workflow commit?

| Option | Description | Selected |
|--------|-------------|----------|
| Nothing — job fails, no commit (Recommended) | If exit code != 0, git-auto-commit-action is skipped (if: success() default). state.json stays at yesterday's value; GHA UI shows the red ❌ and operator sees the failure. Next weekday's run retries cleanly. | ✓ |
| Commit partial state if run got far enough | Requires splitting run_daily_check into 'computed all instruments' vs 'crashed mid-loop'. Complex and error-prone — save_state is already structurally all-or-nothing (atomic replace). Not worth the split. | |
| Always commit (even on fail) | Runs git-auto-commit with always() condition. Could capture partial mutations from a warning-append. But save_state is structurally atomic — the state on disk is either yesterday's or today's; nothing partial. So this is a no-op except for warnings logged mid-flow. | |

**User's choice:** Nothing — job fails, no commit (Recommended)
**Notes:** `save_state` is structurally atomic (Phase 3 `_atomic_write`); no half-state to worry about.

### Q3: Which extras to include in the GHA workflow beyond the locked skeleton?

| Option | Description | Selected |
|--------|-------------|----------|
| workflow_dispatch manual trigger (Recommended) | Lets operator rerun a day's signal via the GHA UI without waiting for cron. Two lines of YAML. Zero risk. | ✓ |
| pip caching via actions/setup-python cache: 'pip' (Recommended) | Speeds up each run from ~30s install to ~5s. setup-python@v5 supports cache-key on requirements.txt out of the box. | ✓ (after re-confirm) |
| Python version via .python-version file (Recommended) | setup-python@v5 with-file: '.python-version' so GHA picks up the same 3.11.8 that pyenv locks locally. Single source of truth. | ✓ (after re-confirm) |
| Failure notification to Resend on workflow error | On job failure, POST a minimal error email via curl + RESEND_API_KEY. Built-in GitHub email notifications may be enough — may be overkill. | |

**User's initial choice:** workflow_dispatch only. Re-confirmed after clarification → folded in pip cache + .python-version pin; failure notification stays out.

### Re-confirmation Q: Confirm the pip-cache and python-version-pin exclusion — or fold them in?

| Option | Description | Selected |
|--------|-------------|----------|
| Fold in pip cache + .python-version pin | Add cache: 'pip' and python-version-file: '.python-version' to setup-python step. ~30s -> ~5s installs; no version drift between local pyenv and GHA. Failure notification stays OUT. | ✓ |
| Keep lean — only workflow_dispatch | No pip cache, no version pin, no notifications. Rationale: first-pass simplicity; we can add them in a later hardening pass if runs feel slow or pyenv drifts. | |
| All three extras | pip cache + .python-version pin + Resend failure-notification. Most defensive; most YAML to review. | |

**User's choice:** Fold in pip cache + .python-version pin
**Notes:** ~2-3 YAML lines each for real wins; failure-notification left out (built-in GH email is sufficient).

---

## Secrets + env loading

### Q1: Where does load_dotenv() get called?

| Option | Description | Selected |
|--------|-------------|----------|
| Top of main() — always, unconditional (Recommended) | Call load_dotenv() as the first line of main() before argparse. load_dotenv() is a no-op if .env is missing (GHA case) or already-set env vars take precedence (Replit Secrets case). Zero-configuration — works in all three deploy paths (local/GHA/Replit). | ✓ |
| Only if .env exists | Wrap in `if Path('.env').exists(): load_dotenv()`. Slightly more defensive but load_dotenv() already handles the missing case silently; the guard is redundant. | |
| Only for local/--test path | Skip load_dotenv in production runs — trust env vars set by GHA/Replit. More moving parts, benefit unclear. | |

**User's choice:** Top of main() — always, unconditional (Recommended)

### Q2: At startup, when RESEND_API_KEY is missing, what should main.py do?

| Option | Description | Selected |
|--------|-------------|----------|
| Keep Phase 6 graceful behavior (Recommended) | Preserve NOTF-08: missing key writes last_email.html + logs WARN, run still succeeds. No startup preflight. Matches 'never crash' invariant; works locally without any secrets configured. | ✓ |
| Warn at startup, continue | Add a startup log line '[Sched] WARN RESEND_API_KEY not set — email will be skipped'. Makes it obvious in GHA logs if a secret was misconfigured. Run still proceeds. | |
| Fail-fast only on GHA (CI env var set) | If GITHUB_ACTIONS=true and required secrets missing, exit 2 immediately. Prevents silent GHA runs that skip email every day. Local/Replit unaffected. | |

**User's choice:** Keep Phase 6 graceful behavior (Recommended)
**Notes:** Preserves local-dev happy path (no secrets needed to run `python main.py --once`); GHA misconfiguration surfaces via absent morning email + troubleshooting section in docs.

### Q3: Which env vars does Phase 7 formally document as part of the deploy contract?

| Option | Description | Selected |
|--------|-------------|----------|
| RESEND_API_KEY (Recommended) | Required for email dispatch. Already wired by Phase 6. | ✓ |
| SIGNALS_EMAIL_TO (Recommended) | Recipient override (defaults to Phase 6 D-14 fallback). Already wired by Phase 6. | ✓ |
| RESET_CONFIRM | Optional CI-side skip for --reset interactive prompt (already read in Phase 4 _handle_reset). Document so operators know it exists. | |
| ANTHROPIC_API_KEY | Mentioned in ROADMAP SC-4 as 'optional'. But nothing in the codebase reads it today. Document as reserved-for-future or drop from SC-4. | |

**User's choice:** RESEND_API_KEY + SIGNALS_EMAIL_TO only
**Notes:** ANTHROPIC_API_KEY dropped from the deploy contract — ROADMAP SC-4 will be amended to match; RESET_CONFIRM documented separately under dev/CI env vars (not primary deploy).

---

## Deployment guide format

### Q1: Where does the deployment guide live?

| Option | Description | Selected |
|--------|-------------|----------|
| New docs/DEPLOY.md (Recommended) | Dedicated runbook at docs/DEPLOY.md. Keeps README.md focused on 'what is this'; deploy details don't bloat the landing page. Linked from README.md 'Deployment' section header. | ✓ |
| Top-level README.md section | Single-file project. Everything operators need is at repo root. Simpler, but README balloons. | |
| Append to SPEC.md | SPEC.md already holds the project brief; extend it with a Deployment section. Keeps one canonical doc, but SPEC.md is more about WHAT than HOW. | |

**User's choice:** New docs/DEPLOY.md (Recommended)

### Q2: How detailed should the deploy guide be?

| Option | Description | Selected |
|--------|-------------|----------|
| Quickstart + env contract + troubleshooting (Recommended) | 3 sections: (1) GHA setup (fork -> add secrets -> enable Actions), (2) Replit alternative (Reserved VM + Always On + filesystem caveat), (3) env var reference + 'what to check when a run fails'. ~150 lines. Enough to recover from a broken deploy without reading code. | ✓ |
| Quickstart only — happy path | Just the sequence of steps to get GHA running. Assume operator reads code when things break. ~50 lines. Lean. | |
| Full runbook with screenshots | Step-by-step with GH UI screenshots, Replit screenshots, failure-mode playbook, etc. ~300+ lines. Useful if others deploy this, overkill for single-operator. | |

**User's choice:** Quickstart + env contract + troubleshooting (Recommended)

### Q3: How production-viable should the Replit alternative stay?

| Option | Description | Selected |
|--------|-------------|----------|
| Code works, docs note caveats (Recommended) | Schedule loop is real code with tests. Docs spell out Replit filesystem-persistence caveat (Reserved VM needed) + Always On requirement ($20/mo) + that GHA is cheaper and preferred. Operator can flip to Replit if GHA ever becomes unviable. | ✓ |
| Code works + is itself tested end-to-end on Replit | Actually run a week on Replit in shadow mode, verify state.json persists across restarts, document observed behavior. Higher-effort; GHA is already primary. | |
| Docs only — no guaranteed Replit tests | Scheduler loop compiles + passes unit tests, but no integration run on Replit. Docs say 'should work; untested'. Riskiest if GHA ever degrades. | |

**User's choice:** Code works, docs note caveats (Recommended)

---

## Claude's Discretion

The following implementation details were left to downstream agents (researcher, planner, executor) in `<decisions>`:

- Exact name of the loop driver (`_run_schedule_loop` recommended)
- Exact name of the never-crash wrapper (`_run_daily_check_caught` recommended)
- Whether `LOOP_SLEEP_S` lives in `system_params.py` or inline default
- Exact number + scope of loop-driver unit tests
- Test file location (`tests/test_scheduler.py` vs extend `tests/test_main.py`)
- `schedule` + `python-dotenv` exact pinned versions
- Whether `docs/DEPLOY.md` includes a "Cost estimate" subsection
- Whether a minimal top-level `README.md` is created at Phase 7
- Whether GHA `file_pattern` covers state.json corrupt-backup files

## Deferred Ideas

See `<deferred>` section in CONTEXT.md for the full list. Summary:

- Resend failure → crash email (Phase 8 ERR-04)
- Stale-state banner (Phase 8 ERR-05)
- Warning carry-over (Phase 8 NOTF-10)
- Configurable account + contract tiers (already folded to Phase 8 as CONF-01/02)
- LLM-backed daily summary (v2)
- Failure notification via Resend (rejected — GH built-in notifications suffice)
- Replit integration tests (rejected — high effort, GHA is primary)
- Multi-recipient fan-out / Slack / SMS (v2 V2-DEL-01/02)
- Docker / container deployment (out of stack allowlist)
- Health-check endpoint (morning email IS the health check)
- State.json restore / rollback flag (v2 V2-REL-01)
- Full-runbook-with-screenshots docs (operator chose lean)
- README as deploy doc home (rejected — docs/DEPLOY.md chosen)
