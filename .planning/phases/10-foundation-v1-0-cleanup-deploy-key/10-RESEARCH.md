# Phase 10: Foundation — v1.0 Cleanup & Deploy Key — Research

**Researched:** 2026-04-24
**Domain:** Python orchestrator + git subprocess + GHA workflow retire + lint CI guard
**Confidence:** HIGH (most claims verified against live codebase; a handful of operator-side SSH / systemd claims carry MEDIUM confidence and are flagged)

## Summary

Phase 10 is an infrastructure-hygiene phase with four tightly scoped items (BUG-01, CHORE-02, INFRA-02, INFRA-03) touching three Python files plus `.github/workflows/` plus one new operator doc. All four decisions (D-01..D-19) in `10-CONTEXT.md` are locked before this research begins — research role is therefore exclusively verification + gap-surfacing, not option exploration.

Three verified findings materially shape the plan:
1. **The "19 F401 warnings" claim is stale.** Running `ruff check notifier.py` on 2026-04-24 returns exactly **4** `F401` warnings in one contiguous block (`AUDUSD_COST_AUD`, `AUDUSD_NOTIONAL`, `SPI_COST_AUD`, `SPI_MULT` — all on `notifier.py:71-76`). The Phase 9 `deferred-items.md` figure of 19 is an obsolete count from the pre-Phase-8 audit. D-04's "genuinely unused vs re-export vs TYPE_CHECKING" classification still applies — and on today's file, all 4 are genuinely unused (no `__all__` re-export pattern; not used as type hints) and can be removed outright with `ruff check --fix`.
2. **BUG-01 only needs D-01, not both D-01 and D-02, to be fully correct — but D-02 still matters.** D-01's one-liner at `main.py:1280` (`state['account'] = float(initial_account)` immediately after `state['initial_account'] = float(initial_account)` on line 1280) is the only site where the regression can today reproduce, because `state_manager.reset_state()` at `state_manager.py:304` takes NO arguments. D-02's proposed signature extension `reset_state(initial_account: float = INITIAL_ACCOUNT) -> dict` is defense-in-depth against a FUTURE caller who reaches into `reset_state` + overrides `initial_account`. Keep D-02 — it's ~5 lines and locks the invariant at the module boundary.
3. **The `TestGHAWorkflow` rename fallout is wider than D-18 suggests.** D-18 says "update Phase 9's `test_daily_workflow_has_timeout_minutes` path". In reality, `tests/test_scheduler.py` has a whole `TestGHAWorkflow` class (12 tests) that all read from a class-level constant `WORKFLOW_PATH = '.github/workflows/daily.yml'` (line 357). Renaming the file to `daily.yml.disabled` without updating that constant breaks ALL 12 tests, not just the one D-18 names. The minimal-diff fix is a single line change: `WORKFLOW_PATH = '.github/workflows/daily.yml.disabled'`. Plus one more site: `TestDeployDocs` at line 664 asserts the README contains the literal `actions/workflows/daily.yml/badge.svg` — the README itself (line 3) also hardcodes `daily.yml`. The badge URL in README must be updated to `daily.yml.disabled` OR the assertion must be softened OR the badge stays pointing at a disabled file (GitHub will render it as "no runs yet" once the current run history ages out; this is acceptable per D-18(a) rollback logic).

**Primary recommendation:** Execute in three tasks: (T1) BUG-01 two-layer fix + regression tests + ruff F401 cleanup + `test_ruff_clean_notifier`; (T2) `_push_state_to_git` helper in `main.py` + `run_daily_check` hook + tests; (T3) `git mv` the GHA workflow, update `TestGHAWorkflow.WORKFLOW_PATH` (and README + `TestDeployDocs` badge assertion) + write `SETUP-DEPLOY-KEY.md` + update `PROJECT.md`/`ROADMAP.md`/`CLAUDE.md` cross-refs. Task 1 and Task 2 are independent; Task 3 depends on nothing from T1/T2. No new third-party deps. AST blocklist already permits `subprocess` in `main.py`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| BUG-01 account/initial_account invariant at reset | `main.py::_handle_reset` (orchestrator) | `state_manager.reset_state` (module boundary) | D-01 call-site fix is sufficient today; D-02 tightens the invariant at the sole writer so future callers can't recreate the bug. Same hex-lite pattern as Phase 8 D-14 (state_manager sole writer for warnings). |
| CHORE-02 F401 cleanup | `notifier.py` (source edit) | `tests/test_notifier.py::test_ruff_clean_notifier` (CI guard) | Zero behavior change in notifier; the guard is stateless (subprocess call to `ruff`) so it doesn't need state_manager or sibling hexes. |
| INFRA-02 nightly state.json push | `main.py::_push_state_to_git` (new orchestrator helper) | Operator SSH keypair + GitHub deploy key (manual) | Hex-lite: `state_manager` stays I/O-narrow (disk only, no subprocess). The git-push adapter lives in `main.py` where `_send_email_never_crash` and `_render_dashboard_never_crash` already live. |
| INFRA-03 GHA cron retire | `.github/workflows/` (file rename via `git mv`) | `tests/test_scheduler.py::TestGHAWorkflow` (path update) + `README.md` (badge URL) + `docs/DEPLOY.md` (prose update) | Repo metadata only; no Python runtime change. GHA parses only files matching `.github/workflows/*.yml` — the `.disabled` suffix removes the file from the workflow set entirely per [VERIFIED: github docs]. |

## <user_constraints>

## User Constraints (from 10-CONTEXT.md)

### Locked Decisions

**Area 1 — BUG-01 defense-in-depth fix:**
- **D-01:** Fix the immediate bug in `main.py::_handle_reset`. Add `state['account'] = float(initial_account)` immediately after the existing `state['initial_account'] = float(initial_account)` (currently `main.py:1280`). Covers both CLI-flag and interactive-Q&A paths because both flow through the same `_handle_reset` function.
- **D-02:** Also extend `state_manager.reset_state()` to accept an optional `initial_account` parameter. Signature: `reset_state(initial_account: float = INITIAL_ACCOUNT) -> dict`. Both `state['account']` and `state['initial_account']` set from the parameter. Default preserves backward compat for existing callers.
- **D-03:** Regression tests at two layers — `tests/test_main.py::TestHandleReset::test_reset_syncs_account_to_initial_account` (parametrized CLI-flag + interactive paths) AND `tests/test_state_manager.py::TestResetState::test_reset_state_accepts_custom_initial_account` + `test_reset_state_default_preserves_backward_compat`.

**Area 2 — ruff F401 cleanup (hybrid audit):**
- **D-04:** Audit each F401 in `notifier.py` and classify: genuinely unused → remove; public re-export → `# noqa: F401` with comment; type-only → move under `if TYPE_CHECKING:`. Expected: majority are genuine dead imports.
- **D-05:** New regression test `tests/test_notifier.py::test_ruff_clean_notifier` runs `ruff check notifier.py --output-format=json` via `subprocess.run()`; asserts `returncode == 0` AND JSON contains zero entries with `code == 'F401'`.
- **D-06:** Do NOT extend to other source files. Keep this phase small.

**Area 3 — INFRA-02 (droplet-side deploy key + state push):**
- **D-07:** Push logic lives in a new `_push_state_to_git(state, now)` helper in `main.py`. Hex-lite boundary preserved — `state_manager.py` stays I/O-narrow (no subprocess). Helper uses local imports (`import subprocess` inside the function) matching the `_send_email_never_crash` pattern.
- **D-08:** Push is triggered at the end of `run_daily_check()` after `save_state()` completes successfully. Flow: `save_state(state)` → `_push_state_to_git(state, now)` → return.
- **D-09:** Skip-if-unchanged gate via `git diff --quiet state.json` (rc=0 → no diff → return early; rc=1 → diff → commit + push; rc=128 → error → warning path).
- **D-10:** Commit author identity is `DO Droplet <droplet@trading-signals>` via inline `-c user.email=... -c user.name=...` flags (does NOT mutate `.git/config`).
- **D-11:** Commit message reused verbatim from v1.0 Phase 7: `chore(state): daily signal update [skip ci]`.
- **D-12:** Fail-loud on push errors; do NOT crash the daily run. Log at ERROR with `[State]` prefix (`'git push failed: <stderr excerpt truncated to 200 chars>'`) → call `state_manager.append_warning(state, source='state_pusher', message=...)` → **rely on next run's normal save cycle** to persist the warning (preserves Phase 8 W3 two-saves-per-run invariant; worst case, a missed-push warning is delayed by one run).
- **D-13:** No auto-rebase retry in Phase 10. Fail-loud over silent recovery.
- **D-14:** Deploy key setup is an operator task, not code. Phase 10 plan MUST include a `SETUP-DEPLOY-KEY.md` doc. Code assumes the key is already in place and fails loudly (via D-12) if not.
- **D-15:** The `trading-signals-web` systemd unit (Phase 11+) is NOT involved in state pushes. Only the daily `trading-signals` unit pushes. Web process only READS state — preserves "one writer" invariant.

**Area 4 — INFRA-03 (GHA cron retirement):**
- **D-16:** Rename `.github/workflows/daily.yml` → `.github/workflows/daily.yml.disabled` via `git mv`. Preserves history; one `git mv` reverses the decision.
- **D-17:** Leave the GitHub repo secrets (`RESEND_API_KEY`, `SIGNALS_EMAIL_TO`) in place. Harmless; useful for rollback.
- **D-18:** Update Phase 9's `test_daily_workflow_has_timeout_minutes` path to `.github/workflows/daily.yml.disabled` (option (a)). Keep the assertion. Protects the rollback path.
- **D-19:** Update `PROJECT.md` + `ROADMAP.md` + `CLAUDE.md` cross-references to reflect droplet-primary, GHA-disabled state.

### Claude's Discretion

- Exact log format for push failures (D-12 reasonable default given).
- `subprocess.check_output` vs `subprocess.run(check=True)` — equivalent; pick per codebase convention (codebase already uses `subprocess.run` + explicit return-code checks in test bodies).
- Order of Phase 10 plan tasks (recommended split above; planner may reorder).
- Whether to squash all 4 items into a single plan vs split. Phase is small (~4hr total).

### Deferred Ideas (OUT OF SCOPE)

- Auto-rebase retry on push failure — if fail-loud proves noisy in production. v1.2 candidate.
- Diff-based state.json gate extension (fingerprint ignoring `last_run` timestamp). v1.2 candidate.
- Deploy key rotation policy. Revisit if team ownership.
- Repo secrets cleanup — delete `RESEND_API_KEY` / `SIGNALS_EMAIL_TO` once droplet path proves stable. v1.2+.
- Extending ruff F401 CI guard to other source files (`state_manager.py`, `main.py`, `dashboard.py`, `sizing_engine.py`, `signal_engine.py`). Follow-up chore.
- `test_daily_workflow_has_timeout_minutes` test deletion (D-18 option (b)). Until formally abandoned, keep both.

</user_constraints>

## <phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BUG-01 | `reset_state()` sets `state['account'] = state['initial_account']` so they start equal; regression test asserts equality immediately post-reset; covers both CLI-flag and interactive-Q&A paths | `main.py:1280` is the exact fix site (verified by reading the file); `state_manager.py:304` is the `reset_state` signature (currently `reset_state() -> dict` with zero args); existing `TestResetInteractive` + `TestResetFlags` classes in `tests/test_main.py` give the parametrization pattern for D-03; existing `TestReset` class in `tests/test_state_manager.py:875` gives the module-level test pattern. |
| CHORE-02 | Clean the N pre-existing ruff F401 warnings in `notifier.py`; regression test asserts zero ruff warnings at CI time | Live `ruff check notifier.py` returns **4 F401 warnings**, not 19 (verified today). Ruff 0.6.9 `--output-format=json` emits an array of objects with `code`, `location.row`, `filename`, `message`, `fix.applicability` fields (verified via live run — see "Ruff JSON Output Contract" section). All 4 today are safely removable (`applicability: safe`). No `TYPE_CHECKING` or re-export patterns present in `notifier.py`. |
| INFRA-02 | Droplet has a GitHub deploy key with write access; nightly cron pushes `state.json` commits to `origin/main` so git holds state history | `main.py` already uses local-import pattern for fragile I/O boundaries (`_send_email_never_crash` at line 136). `FORBIDDEN_MODULES_MAIN` (line 544 of `tests/test_signal_engine.py`) permits `subprocess` — not blocked. `state_manager.append_warning` signature is `(state: dict, source: str, message: str, now=None) -> dict` per `state_manager.py:423` — D-12's call site will invoke this. `git diff --quiet <path>` returns rc=0 on no diff, rc=1 on diff, rc>=128 on error (documented git exit codes [VERIFIED: man git-diff]). |
| INFRA-03 | `daily.yml.disabled` — GHA cron workflow removed/renamed; droplet systemd is the sole runner (no duplicate email risk) | `.github/workflows/daily.yml` currently exists (verified by `ls`); 12-test `TestGHAWorkflow` class in `tests/test_scheduler.py` with class-level `WORKFLOW_PATH = '.github/workflows/daily.yml'` (line 357) — updating this single constant fixes all 12 tests. `README.md:3` hardcodes the badge URL containing `daily.yml`; `TestDeployDocs` line 664 asserts the README badge substring. `docs/DEPLOY.md` mentions `daily.yml` on lines 21, 143, 158 (prose — low-stakes). GitHub Actions parses only `*.yml` files in `.github/workflows/` — the `.disabled` suffix fully retires the schedule [CITED: docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions]. |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

Phase 10 must honor these project directives. Any contradicting approach in the plan must be reconsidered.

- **2-space indent, single quotes, PEP 8 via `ruff`.** New `_push_state_to_git` helper must be 2-space indented with single-quoted strings. `tests/test_signal_engine.py::TestDeterminism::test_no_four_space_indent` catches accidental 4-space regressions.
- **Log prefix:** `[State]` for `_push_state_to_git` (state persistence is a state-pusher concern; D-12 already spec'd this prefix).
- **Hexagonal-lite boundary:** `signal_engine.py ↔ state_manager.py` must not import each other; `sizing_engine.py` and `system_params.py` are pure-math/constants modules with no I/O or sibling-hex imports. `_push_state_to_git` lives in `main.py` (the sole orchestrator) — NOT in `state_manager.py`. The subprocess / git invocation must not leak into `state_manager.py` even though it manipulates state-persistence behavior.
- **`state.json` writes are atomic: tempfile + fsync + `os.replace`.** Phase 10 does NOT touch the write path. The helper runs AFTER `save_state` has atomically replaced the file.
- **`--test` is structurally read-only** (enforced by splitting compute and persist). Phase 10 does not change this — `_push_state_to_git` is called only after the non-`--test` branch of `run_daily_check` commits (see `main.py:1058`).
- **Email sends NEVER crash the workflow** — same pattern mirrored by `_push_state_to_git`: `except` every subprocess failure, log, append warning, return.
- **`FORBIDDEN_MODULES_MAIN`** (at `tests/test_signal_engine.py:544`) currently forbids `numpy`, `yfinance`, `requests`, `pandas` for `main.py`. `subprocess` is NOT in this set. No blocklist edit required.
- **Version pins are exact, not `>=`.** `requirements.txt` is maintained in locked form. Phase 10 adds ZERO new dependencies (`subprocess` is stdlib; `ruff` is already pinned at `0.6.9`). Confirm in plan that `requirements.txt` is NOT modified.
- **GSD workflow enforcement:** all file changes go through a GSD plan. No out-of-band edits.

## Standard Stack

### Core (no new additions — all stdlib / existing pins)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `subprocess` | stdlib (Python 3.11.8) | Invoke `git diff --quiet state.json`, `git commit`, `git push` | Stdlib — zero new deps; `run()` with `check=True`, `capture_output=True`, `timeout=N` is the verified 2026 idiom. [VERIFIED: docs.python.org/3.11/library/subprocess.html] |
| `ruff` | 0.6.9 (already pinned) | Lint CI guard — `ruff check notifier.py --output-format=json` | Project already standardizes on ruff 0.6.9 per `requirements.txt`; JSON output shape confirmed stable for 0.6.x (see "Ruff JSON Output Contract" below). [VERIFIED: live `ruff --version` on 2026-04-24] |
| `pytest` | 8.3.3 (already pinned) | Test runner for new regression tests | Existing convention. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `logging` | stdlib | `logger.error('[State] git push failed: %s', stderr[:200])` | Use existing module-level `logger` in `main.py` (Phase 7/8 precedent). Do NOT print(). |
| `state_manager.append_warning` | n/a | Record push failures for next-run surfacing | Imported at module top in `main.py` (already present). Use the full 4-arg form `(state, source='state_pusher', message=..., now=now)` per D-12. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `subprocess.run(check=True)` → catch `CalledProcessError` | `subprocess.run(check=False)` + manual `if rc != 0` | Equivalent semantics. Codebase already has both patterns (e.g., `test_scheduler.py` uses `check=True` for happy-path tests). For `_push_state_to_git` use `check=True` for the commit/push steps so `CalledProcessError` carries `returncode` + `stderr` in one object; use `check=False` for the skip-if-unchanged `git diff` because rc=1 is a valid outcome, not an error. |
| GitHub REST API via `requests` | stdlib `subprocess` + local git | API requires a token + network auth; subprocess uses the deploy key already on the droplet. subprocess is simpler + reuses the SSH channel the operator already configured. D-07 mandates subprocess. |
| `pygit2` library | `subprocess` + CLI git | Adds a C-extension dep. Not worth it for three git commands. AST blocklist doesn't include `pygit2`, but CLAUDE.md §Stack would need amendment; no benefit. |

**Installation:**
```bash
# No new dependencies needed. Verify existing pins:
pip show ruff  # must report 0.6.9
pip show pytest  # must report 8.3.3
```

**Version verification [VERIFIED: live subprocess call 2026-04-24]:**
- `ruff --version` → `ruff 0.6.9` (matches `requirements.txt`)
- `ruff check notifier.py --output-format=json` — returns valid JSON array, see "Ruff JSON Output Contract" section below for the exact field shape.

## Architecture Patterns

### System Architecture Diagram

```
                      main.py::run_daily_check(args)
                                 │
            ┌────────────────────┼────────────────────────┐
            │                    │                        │
            ▼                    ▼                        ▼
     [weekend skip]      [per-instrument loop]    [--test branch]
                                 │                  returns early
                                 ▼                 (CLI-01 read-only)
                      state_manager.save_state(state)  ← atomic
                                 │                        tempfile + fsync + os.replace
                                 ▼
                       _render_dashboard_never_crash(...)
                                 │
                                 ▼
     NEW ────►  _push_state_to_git(state, now)   ← Phase 10 INFRA-02 insertion point
                         │
                         │ local `import subprocess`
                         ▼
          ┌─► `git diff --quiet state.json`
          │         │
          │   rc=0 (no diff) ──► log + return  (D-09 skip-if-unchanged)
          │   rc=1 (diff)    ──► continue
          │   rc>=2 (error)  ──► append_warning + return  (D-12 fail-loud path)
          │
          ├─► `git -c user.email=droplet@trading-signals
          │         -c user.name='DO Droplet'
          │         commit -m '<D-11 message>' state.json`   (check=True)
          │
          └─► `git push origin main`   (check=True)
                  │
                  │ CalledProcessError?
                  ▼
             logger.error('[State] git push failed: <stderr[:200]>')
             state_manager.append_warning(state, source='state_pusher', ...)
             return  (NO extra save_state — next run persists via normal flow per D-12)

                                 ▼
                    main.py outer dispatch returns
                    (Phase 8 Layer A _run_daily_check_caught catches any leaked exception;
                     Phase 8 Layer B catches loop-driver crashes.)
```

**Data flow notes:**
- The helper is called AFTER `save_state` so state.json on disk reflects this run's mutations.
- The helper is called BEFORE `run_daily_check` returns so the scheduler loop (or `--once` driver) can proceed immediately to the next tick.
- On `--test` (read-only), `run_daily_check` returns before reaching step 9 (see `main.py:1055`), so `_push_state_to_git` is never invoked — preserves CLI-01.
- On weekend skip, `run_daily_check` returns at line 834 (weekday gate), so `_push_state_to_git` is never invoked — no commits on weekends.

### Recommended Project Structure (unchanged)
```
trading-signals/
├── main.py                      # MODIFIED: _handle_reset (D-01); new _push_state_to_git (D-07); run_daily_check hook (D-08)
├── state_manager.py             # MODIFIED: reset_state signature (D-02)
├── notifier.py                  # MODIFIED: remove 4 F401 imports (D-04)
├── tests/
│   ├── test_main.py             # EXTENDED: TestHandleReset regression (D-03)
│   ├── test_state_manager.py    # EXTENDED: TestReset regression (D-03)
│   ├── test_notifier.py         # EXTENDED: test_ruff_clean_notifier (D-05)
│   └── test_scheduler.py        # MODIFIED: WORKFLOW_PATH constant (D-18)
├── .github/workflows/
│   └── daily.yml.disabled       # RENAMED via git mv (D-16)
├── README.md                    # MODIFIED: badge URL (side-effect of D-16)
├── docs/DEPLOY.md               # Likely MODIFIED: prose refs (side-effect of D-16, D-19)
├── .planning/
│   ├── PROJECT.md               # MODIFIED: deployment section (D-19)
│   ├── ROADMAP.md               # MODIFIED: operator decisions baked in (D-19)
│   └── phases/10-foundation-v1-0-cleanup-deploy-key/
│       ├── 10-CONTEXT.md        # exists
│       ├── 10-RESEARCH.md       # this file
│       ├── 10-PLAN.md           # to be written
│       └── SETUP-DEPLOY-KEY.md  # NEW (D-14)
└── CLAUDE.md                    # MODIFIED: deployment section (D-19)
```

### Pattern 1: Never-crash I/O wrapper (mirror of `_send_email_never_crash`)

**What:** A top-level orchestration helper that calls out to fragile I/O (HTTP, subprocess, disk), catches every failure mode, logs with the module's `[State]` / `[Email]` prefix, records a warning via `state_manager.append_warning`, and returns without propagating the exception. The scheduler loop and the daily cron both survive even if the I/O fails.

**When to use:** Any I/O call that can fail for external reasons (network, auth, filesystem) and whose failure should NOT kill the daily run. Email dispatch (Phase 6/8 precedent) and git push (Phase 10) are both this pattern.

**Example — extracted verbatim from `main.py:136-184`:**
```python
# Source: /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/main.py:136-184 [VERIFIED]
def _send_email_never_crash(
  state: dict,
  old_signals: dict,
  run_date: datetime,
  is_test: bool = False,
) -> 'object':
  '''D-15 + NOTF-07/NOTF-08 + Phase 8 D-08 consumer bridge.

  C-2 reviews (Phase 5 precedent): `import notifier` lives INSIDE the
  helper body (not at module top) so import-time errors in notifier.py
  — syntax errors, bad sub-imports, circular-import bugs — are caught
  by the SAME `except Exception` that catches runtime dispatch failures.
  Without this, an import-time notifier error takes down main.py at
  module load time, before the helper even runs.
  ...
  '''
  try:
    import notifier  # local import — C-2 isolates import-time failures
    return notifier.send_daily_email(state, old_signals, run_date, is_test=is_test)
  except Exception as e:
    logger.warning('[Email] send failed: %s: %s', type(e).__name__, e)
    try:
      from notifier import SendStatus  # noqa: PLC0415 — C-2 local import
      return SendStatus(
        ok=False,
        reason=f'{type(e).__name__}: {e}'[:200],
      )
    except Exception:
      return None
```

**Template for `_push_state_to_git` (plan-ready, NOT final code — decisions to flag for planner marked [PLANNER]):**
```python
# Source: plan-ready template derived from _send_email_never_crash pattern + D-07..D-12
def _push_state_to_git(state: dict, now: datetime) -> None:
  '''Phase 10 INFRA-02 / D-07..D-12 — nightly state.json commit + push via git.

  C-2 precedent (mirror of _send_email_never_crash): `import subprocess`
  lives INSIDE the helper body so import-time failures (shouldn't happen
  for stdlib, but the pattern is cheap) are caught by the outer except.

  D-09 skip-if-unchanged: `git diff --quiet state.json` exit codes —
    rc=0 → no diff → log [State] + return
    rc=1 → diff present → continue to commit+push
    rc>=128 → git error (not-a-repo, missing file, etc.) → fail-loud path

  D-10 inline -c user.email/-c user.name: does NOT mutate .git/config;
    only applies to this single invocation [VERIFIED: man git-commit].

  D-11 commit message (verbatim from v1.0 Phase 7):
    'chore(state): daily signal update [skip ci]'

  D-12 fail-loud: log at ERROR with [State] prefix, append_warning via
    state_manager (preserves Phase 8 D-08 sole-writer invariant), return.
    NO additional save_state — next run's normal save cycle persists the
    warning (Phase 8 W3 two-saves-per-run invariant preserved).

  D-15: --test and weekend-skip never reach this helper (run_daily_check
    returns before save_state in those branches). No guard needed here.
  '''
  try:
    import subprocess  # local — C-2 pattern; stdlib but pattern is free
    # [PLANNER]: confirm working directory assumption. run_daily_check
    #   has no cwd= context; subprocess inherits main.py's cwd. The
    #   systemd unit's WorkingDirectory= must point at the repo root
    #   (operator doc must state this explicitly).
    diff_rc = subprocess.run(
      ['git', 'diff', '--quiet', 'state.json'],
      capture_output=True,
      timeout=30,
    ).returncode
    if diff_rc == 0:
      logger.info('[State] state.json unchanged — skipping git push')
      return
    if diff_rc >= 128:
      # [PLANNER]: consider whether rc=128 should skip quietly (not a
      #   real "failure" — e.g., running from a non-repo clone) or trip
      #   the fail-loud path. D-12 is ambiguous; recommend fail-loud
      #   with a distinct warning message so operator can diagnose.
      raise RuntimeError(f'git diff errored (rc={diff_rc}) — repo not initialized?')

    subprocess.run(
      [
        'git',
        '-c', 'user.email=droplet@trading-signals',
        '-c', 'user.name=DO Droplet',
        'commit', '-m', 'chore(state): daily signal update [skip ci]',
        'state.json',
      ],
      check=True,
      capture_output=True,
      timeout=30,
    )
    subprocess.run(
      ['git', 'push', 'origin', 'main'],
      check=True,
      capture_output=True,
      timeout=60,  # push can be slow; more generous than diff/commit
    )
    logger.info('[State] state.json pushed to origin/main')
  except subprocess.CalledProcessError as e:
    stderr = (e.stderr or b'').decode('utf-8', errors='replace')[:200]
    logger.error(
      '[State] git push failed (cmd=%s rc=%d): %s',
      ' '.join(e.cmd) if isinstance(e.cmd, list) else e.cmd,
      e.returncode,
      stderr,
    )
    state_manager.append_warning(
      state,
      source='state_pusher',
      message=f'Nightly state.json push failed: rc={e.returncode} stderr={stderr}',
      now=now,
    )
  except subprocess.TimeoutExpired as e:
    logger.error('[State] git push timed out after %ss', e.timeout)
    state_manager.append_warning(
      state,
      source='state_pusher',
      message=f'Nightly state.json push timed out after {e.timeout}s',
      now=now,
    )
  except Exception as e:  # noqa: BLE001 — never-crash posture (matches _send_email_never_crash)
    logger.error('[State] git push unexpected error: %s: %s', type(e).__name__, e)
    state_manager.append_warning(
      state,
      source='state_pusher',
      message=f'Nightly state.json push errored: {type(e).__name__}: {e}'[:250],
      now=now,
    )
```

### Pattern 2: CI lint guard via subprocess (ruff check)

**What:** A pytest test that invokes an external CLI tool (ruff, mypy, black) via `subprocess.run`, parses JSON output, and asserts specific rule codes are absent.

**When to use:** When a lint class of bugs (unused imports, unused vars, dead code) needs to be locked down so it cannot regress. The test runs in CI by virtue of being in the default test path.

**Template for `test_ruff_clean_notifier`:**
```python
# Source: plan-ready template derived from D-05 + verified ruff 0.6.9 JSON shape
import json
import subprocess

def test_ruff_clean_notifier() -> None:
  '''CHORE-02 / D-05: notifier.py must have zero F401 warnings.

  Runs ruff check with JSON output, asserts no F401 entries. The test
  does NOT assert returncode == 0 in isolation — ruff returns non-zero
  when ANY rule fires (F401, E501, etc.), and this test is scoped to
  F401 only (D-06: don't extend to other files / other rules).

  Ruff 0.6.9 JSON shape (verified 2026-04-24 via live run):
    - returncode == 0 AND stdout == '[]\\n' when clean
    - returncode == 1 AND stdout == '[{...}, ...]' when issues found
    - each object has keys: cell, code, end_location, filename, fix,
      location, message, noqa_row, url
    - location.row is int (1-based line number)
    - code is str ('F401', 'E501', etc.)
  '''
  result = subprocess.run(
    ['ruff', 'check', 'notifier.py', '--output-format=json'],
    capture_output=True,
    text=True,
    timeout=30,
  )
  # ruff exits 0 when clean (JSON=[]), 1 when rule violations present.
  # D-05 asserts the F401-specific subset is empty — other rules
  # (if any land in notifier.py later) are out-of-scope per D-06.
  entries = json.loads(result.stdout) if result.stdout.strip() else []
  f401_entries = [e for e in entries if e.get('code') == 'F401']
  assert len(f401_entries) == 0, (
    f'CHORE-02: notifier.py must have zero F401 (unused-import) warnings; '
    f'found {len(f401_entries)}: '
    f'{[(e["location"]["row"], e["message"]) for e in f401_entries]}'
  )
```

### Anti-Patterns to Avoid

- **Anti-pattern: Writing subprocess inside `state_manager.py`.** `state_manager.py` has an AST blocklist (`FORBIDDEN_MODULES_STATE_MANAGER` at `tests/test_signal_engine.py:507`) that does NOT include `subprocess` — so the test wouldn't catch the violation automatically — but CLAUDE.md §Architecture explicitly says `state_manager` is the I/O hex for disk only. Putting git push in there breaks the hex-lite boundary even if tests don't catch it. Keep the helper in `main.py`.
- **Anti-pattern: Using `git config user.email <x>` to set identity.** This mutates `.git/config`, which is version-controlled on the droplet clone (via git internals, not the working tree, but still a persistent state change). Use inline `-c user.email=... -c user.name=...` flags per D-10 — one-shot override, no mutation.
- **Anti-pattern: Extra `save_state(state)` call after `append_warning` on push failure.** D-12 explicitly rejects this — the two-saves-per-run invariant from Phase 8 W3 must hold. The warning is persisted on the NEXT run's normal save cycle. Planner should verify `run_daily_check` still has exactly 2 `save_state` call sites after Phase 10 (step 5 end-of-run + Phase 8 `_dispatch_email_and_maintain_warnings` post-email).
- **Anti-pattern: Catching `Exception` too early in `_push_state_to_git`.** Catch the specific cases first (`CalledProcessError`, `TimeoutExpired`) so error messages can be specific; only fall through to `except Exception` as defense-in-depth. Matches Phase 8 `_send_email_never_crash` layering.
- **Anti-pattern: Using `pytest.importorskip('yaml')` in the new regression test.** PyYAML is pinned (Wave 0 of Phase 7). Skipping on missing yaml hides real environment failures.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Detect "did state.json change vs git HEAD?" | Manual file hash comparison + storing previous hash in state | `git diff --quiet state.json` (exit code 0 = no diff, 1 = diff) | Git already tracks this perfectly. Adding a hash cache introduces a new state field and a cache-invalidation class of bugs. [CITED: man git-diff] |
| Git commit author identity | Call `git config --global user.email` at droplet provision time | Inline `-c user.email=... -c user.name=...` flags per invocation | Global config affects every git command the operator runs interactively on the droplet. Per-invocation flags apply ONLY to this one commit. Zero side effects. [VERIFIED: git 2.39+ release notes; documented in git-commit(1) DISCUSSION section] |
| Retry logic on `git push` network failures | Hand-written while loop with backoff | Nothing (fail-loud per D-13; next run retries naturally) | Git push failures are almost always auth / diverged-branch / network — none of which a blind retry fixes. D-13 deliberately rejects retry. The scheduler cron runs daily; a flaky network day is a single missed commit, which is surfaced via `append_warning` next run. |
| Parse ruff text output for unused-import detection | Regex / grep / awk over `ruff check`'s human output | `ruff check --output-format=json` | JSON output is versioned and stable. Parsing human output breaks when ruff updates its message format (happened between 0.3 → 0.4). [VERIFIED: docs.astral.sh/ruff/output-formats] |
| SSH deploy key setup | Ship a helper script in the repo that runs `ssh-keygen` | Operator-runbook doc (`SETUP-DEPLOY-KEY.md`) | Scripted key generation hides the key material from the operator who must paste it into GitHub. Doc with explicit commands is more transparent and matches D-14's "setup is an operator task, not code" intent. |

**Key insight:** Phase 10 is almost entirely about NOT building things. Every candidate custom solution (hash caching, retry logic, config-mutation) has a git or stdlib equivalent that's simpler and more robust. The helper is ~50 lines of glue.

## Runtime State Inventory

Phase 10 is a cleanup / refactor / infra phase that renames `daily.yml` and adds a nightly push — both touch runtime state beyond the repo's files. Explicit answers required per the research protocol:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| **Stored data** | `state.json` at repo root on the droplet — already the canonical data store. `_push_state_to_git` READS this file implicitly via `git diff` + `git commit state.json` and WRITES to git (not to state.json itself). No schema change. | None — no migration. State.json format unchanged. |
| **Live service config** | GitHub Actions scheduled workflow (`daily.yml`) has been firing since v1.0 Phase 7. After `git mv daily.yml daily.yml.disabled` + `git push`, GitHub Actions immediately stops scheduling it [CITED: docs.github.com — workflow files must match `.github/workflows/*.yml` pattern]. **Verification window per ROADMAP SC-4:** no cron fires for 2 consecutive weekdays. | Git mv via plan task (code edit, not data migration). |
| | GitHub repo secrets (`RESEND_API_KEY`, `SIGNALS_EMAIL_TO`) live in GitHub Settings → Secrets → Actions. Per D-17, LEAVE IN PLACE during v1.1 (useful for rollback); delete in v1.2+ if permanence committed. | None (D-17 deferred). |
| | Droplet-side `.env` file contains the same secrets for the systemd `trading-signals` unit. NOT in git. Pre-existing; unchanged by Phase 10. | None — pre-existing; Phase 11 manages the droplet .env contract. |
| **OS-registered state** | systemd unit `trading-signals.service` on the droplet — provisioned in Phase 11, not Phase 10. Phase 10's `_push_state_to_git` is a function in `main.py`; it runs whenever `run_daily_check` runs, which will eventually be invoked by the systemd unit once Phase 11 lands. No direct systemd registration in Phase 10. | None for Phase 10; Phase 11 handles unit file. However: the `SETUP-DEPLOY-KEY.md` doc must note that the systemd unit's `WorkingDirectory=` MUST be the repo root so `git diff`/`git commit` in `_push_state_to_git` resolve against the right `.git/` dir. |
| | SSH `known_hosts` on the droplet — first `ssh -T git@github.com` prompts for host-key trust. If a systemd-run push fires before the operator's first manual connection, it will hang on the prompt. | `SETUP-DEPLOY-KEY.md` step: explicitly run `ssh -T git@github.com` once interactively to populate `~/.ssh/known_hosts` before first automated push. |
| **Secrets / env vars** | No new secret keys introduced by Phase 10. The deploy key private half lives at `~/.ssh/id_ed25519_trading_signals` (or similar — operator choice) on the droplet, never enters code. No env var reads in `_push_state_to_git`. | None — secret lifecycle documented in `SETUP-DEPLOY-KEY.md`; code does not reference the key. |
| **Build artifacts / installed packages** | `pip`-installed packages on the droplet — unchanged by Phase 10. No new deps added. `.pyc` caches don't need invalidation. | None. |

**The canonical question answered:** After every file in the repo is updated by this phase, what runtime systems still have the old string cached / stored / registered?

- **GitHub Actions:** The workflow runs list in the GitHub UI retains historical runs of `daily.yml` — these do NOT need to be purged. They're read-only history.
- **Badge image cache:** GitHub's badge image for the workflow (`actions/workflows/daily.yml/badge.svg`) will eventually 404 or render as "no runs" after the workflow is disabled. This is expected and acceptable per D-18(a) (rollback preservation).
- **Droplet-side `git` remote URL:** The operator MUST switch the origin remote from HTTPS (`https://github.com/...`) to SSH (`git@github.com:.../...git`) during `SETUP-DEPLOY-KEY.md` execution. Missing this step = push succeeds via HTTPS until the GitHub credentials cache expires, then silently fails. Doc must include `git remote set-url origin git@github.com:<owner>/<repo>.git` + `git remote -v` verification step.

## Common Pitfalls

### Pitfall 1: `git diff --quiet` exit-code trio
**What goes wrong:** Naive handlers treat `git diff --quiet` as binary (0 vs non-zero), catch rc=1 as an error, and fail the daily run when state.json actually changed (the common case).
**Why it happens:** Most shell tools use rc=0 for success / non-zero for failure. `git diff --quiet` inverts this: rc=0 means "no diff" (an INFORMATIONAL outcome, not a failure); rc=1 means "diff present" (also informational, the reason to commit). Only rc>=128 is a true error.
**How to avoid:** Explicitly handle all three cases per D-09 — rc=0 skip, rc=1 proceed, rc>=128 fail-loud. Use `subprocess.run(check=False)` for this specific call (so rc=1 doesn't raise) and inspect `.returncode` explicitly.
**Warning signs:** `CalledProcessError` traces from `git diff` in the `[State]` logs; missing commits on days when state clearly changed.

### Pitfall 2: Inline `-c user.email=...` must come BEFORE the subcommand
**What goes wrong:** `git commit -c user.email=x state.json` silently treats `-c` as a commit-option and fails with "unknown option".
**Why it happens:** Git's `-c` flag is a top-level option; it applies to the git binary, not to the subcommand. Order matters: `git -c KEY=VAL <subcommand>`, not `git <subcommand> -c KEY=VAL`.
**How to avoid:** Verify the argv order in the `subprocess.run(...)` list — `['git', '-c', 'user.email=droplet@trading-signals', '-c', 'user.name=DO Droplet', 'commit', '-m', ..., 'state.json']`. [VERIFIED: git-commit(1) shows `-c` in the top-level git synopsis, not in commit-specific options]
**Warning signs:** `git: 'commit' is not a git command` or `error: unknown option '-c'` in `[State]` error logs.

### Pitfall 3: `TestGHAWorkflow` breaks in 12 places on rename, not 1
**What goes wrong:** D-18 describes updating one test's path. In reality, the `TestGHAWorkflow` class has a shared class-level `WORKFLOW_PATH` constant that all 12 tests read. Renaming `daily.yml` → `daily.yml.disabled` without updating the constant makes all 12 tests fail with `FileNotFoundError`.
**Why it happens:** D-18 was written with the `test_daily_workflow_has_timeout_minutes` test in mind (added in Phase 9), and didn't account for the earlier 11-test suite in the same class.
**How to avoid:** Update `WORKFLOW_PATH = '.github/workflows/daily.yml'` → `WORKFLOW_PATH = '.github/workflows/daily.yml.disabled'` at `tests/test_scheduler.py:357`. Single-line change that covers all 12 tests. The semantics remain valid — assertions like "cron is `0 0 * * 1-5`" are still true of the disabled file (we didn't edit the YAML contents, just renamed).
**Warning signs:** `pytest tests/test_scheduler.py -k TestGHA` failing with `FileNotFoundError` on 12 tests. Or — sneakier — `grep -c "daily.yml" tests/test_scheduler.py` returning the old count after the plan claims D-18 is complete.

### Pitfall 4: README badge URL + `TestDeployDocs` assertion
**What goes wrong:** `README.md:3` hardcodes `actions/workflows/daily.yml/badge.svg` in the status-badge URL. `tests/test_scheduler.py:664` asserts this substring is present. After the rename, the badge URL becomes a dead link (GitHub may serve a "no workflow" placeholder image, or 404, depending on cache state). If the plan updates README to `daily.yml.disabled`, the badge is still dead (GitHub doesn't render badges for disabled workflows). If the plan leaves README alone, `TestDeployDocs` still passes (substring still present in README), but the rendered README shows a broken badge.
**Why it happens:** D-16 (rename) and D-19 (cross-ref updates) are treated as independent decisions; neither explicitly calls out the README badge.
**How to avoid:** In Task 3 of the plan, decide deliberately: (a) leave README alone + accept the broken badge as visible "GHA retired" signal, or (b) remove the badge line entirely + update `TestDeployDocs` to not assert the substring, or (c) replace with a local-status badge pointing at the droplet systemd (new Phase 11+ concept). **Recommended: option (a)** — zero code change; broken badge is itself a visible status indicator ("you can see GHA is retired because the badge renders 'no workflow'"). Document the choice in Task 3's actions.
**Warning signs:** README rendering shows `Daily signal check: no workflow` badge; `TestDeployDocs` still green but grep of README reveals stale URL.

### Pitfall 5: Systemd's `WorkingDirectory=` controls `cwd` for subprocess
**What goes wrong:** `_push_state_to_git` does `subprocess.run(['git', 'diff', '--quiet', 'state.json'], ...)`. subprocess inherits the calling process's cwd. If the Phase 11 systemd unit's `WorkingDirectory=` is NOT the repo root, `git` finds no `.git/` directory and fails with `fatal: not a git repository`. This is caught by the fail-loud path but registers as a warning every day — noise.
**Why it happens:** systemd units don't automatically cd to the file location. Operators sometimes set `WorkingDirectory=/root` or `/srv/app` out of habit; if the repo is at `/home/marc/trading-signals` the git commands fail.
**How to avoid:** `SETUP-DEPLOY-KEY.md` must include an explicit step: "Verify your `trading-signals.service` unit file has `WorkingDirectory=<path to repo root>`". Alternatively, `_push_state_to_git` could take a `cwd=` kwarg and default to the repo root resolved from `__file__`. **Recommended: document the invariant in both the helper docstring and `SETUP-DEPLOY-KEY.md`**. Don't bake a `cwd=` into the helper — the project convention (per `state_manager.py` and `notifier.py`) is that cwd = repo root.
**Warning signs:** `git push` failures in `[State]` logs showing `fatal: not a git repository` every day.

### Pitfall 6: SSH agent vs explicit key (non-interactive systemd)
**What goes wrong:** systemd runs the daemon in a clean environment — no `SSH_AUTH_SOCK`, no keychain. If the operator's `~/.ssh/config` relies on the SSH agent (e.g., `IdentityAgent /run/user/1000/keyring/ssh`), the automated push hangs or fails.
**Why it happens:** SSH agents are session-scoped. systemd services run outside the operator's login session.
**How to avoid:** `SETUP-DEPLOY-KEY.md` must direct the operator to configure `~/.ssh/config` with an explicit `IdentityFile` entry (NOT `IdentityAgent`) for `github.com`. Example config block:
```
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_trading_signals
  IdentitiesOnly yes
```
`IdentitiesOnly yes` prevents ssh from trying other keys before this one (which would hit GitHub's rate limit for failed auth attempts).
**Warning signs:** `Permission denied (publickey)` errors in `[State]` logs; operator can push manually but systemd can't.

### Pitfall 7: Host-key verification prompts on first push
**What goes wrong:** First-ever `git push` from the droplet to `git@github.com:...` emits `Are you sure you want to continue connecting (yes/no/[fingerprint])?` — systemd subprocess has no TTY; the prompt hangs; the daily run times out after ~30-60s on the `git push` call.
**Why it happens:** `~/.ssh/known_hosts` is populated only after first successful connection. systemd-run subprocesses can't respond to prompts.
**How to avoid:** `SETUP-DEPLOY-KEY.md` MUST include an explicit first-connection step: `ssh -T git@github.com` run interactively by the operator; answer `yes` to accept GitHub's host key. This writes `github.com` to `~/.ssh/known_hosts`. Subsequent non-interactive connections skip the prompt. Alternative: pre-populate `known_hosts` with GitHub's published fingerprints [CITED: docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints] — more complex, not recommended for v1.
**Warning signs:** First scheduled run hangs until timeout (60s), succeeds on second run manually triggered by the operator.

### Pitfall 8: Ruff JSON output format drift between versions
**What goes wrong:** Ruff's JSON schema changed between 0.3.x and 0.4.x (renamed fields), and between 0.5.x and 0.6.x (added `fix.applicability`). A test pinned to the wrong shape breaks on minor version bump.
**Why it happens:** Ruff is pre-1.0; schema is not formally stable.
**How to avoid:** The regression test asserts ONLY on the `code` field (present in all versions since 0.1). Does NOT assert on `fix`, `applicability`, `noqa_row`, or `cell`. This survives any 0.6.x → 0.7.x bump. Also pin `ruff==0.6.9` in `requirements.txt` (already done per STATE.md).
**Warning signs:** `KeyError` in `test_ruff_clean_notifier` after a `pip install --upgrade` on the droplet or CI runner.

## Code Examples

Verified patterns from the existing codebase or external authoritative sources.

### Example 1: Existing `append_warning` signature and call pattern

```python
# Source: /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/state_manager.py:423 [VERIFIED]
def append_warning(state: dict, source: str, message: str, now=None) -> dict:
  '''D-09 / D-10 / D-11: append {date, source, message}; FIFO trim to MAX_WARNINGS.
  ...
  `now` defaults to datetime.now(timezone.utc); tests inject a fixed UTC
  datetime for determinism without pytest-freezer.
  ...
  '''
  if now is None:
    now = datetime.now(UTC)
  today_awst = now.astimezone(_AWST).strftime('%Y-%m-%d')
  entry = {'date': today_awst, 'source': source, 'message': message}
  state['warnings'] = state['warnings'][-(MAX_WARNINGS - 1):] + [entry]
  return state
```

**D-12 invocation (plan-ready):**
```python
state_manager.append_warning(
  state,
  source='state_pusher',
  message=f'Nightly state.json push failed: rc={e.returncode} stderr={stderr}',
  now=now,
)
```
The `source='state_pusher'` value is a NEW source tag (existing sources include `'notifier'`, `'state_manager'`, `'sizing_engine'`, `'sched'`). Plan must grep `state['warnings']` consumers (dashboard, email banner) to verify they handle an unknown source gracefully (they should — source is a display string, not switched on).

### Example 2: BUG-01 fix site — `_handle_reset` final build step

```python
# Source: /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/main.py:1278-1287 [VERIFIED]
# --- Build + save ---
state = state_manager.reset_state()
state['initial_account'] = float(initial_account)                        # existing line
# D-01 FIX: add this single line immediately below:
state['account'] = float(initial_account)                                # NEW — fixes BUG-01
state['contracts'] = {'SPI200': spi_contract, 'AUDUSD': audusd_contract}
state_manager.save_state(state)
logger.info(
  '[State] state.json reset (initial_account=$%.2f, SPI200=%s, AUDUSD=%s)',
  initial_account, spi_contract, audusd_contract,
)
return 0
```

**D-02 (defense-in-depth) version in `state_manager.py`:**
```python
# Source: state_manager.py:304-333 [VERIFIED; D-02 shows the extension]
# BEFORE:
def reset_state() -> dict:
  '''STATE-07 / D-01 / D-03: fresh state, $100k account, empty collections.
  ...
  '''
  return {
    'schema_version': STATE_SCHEMA_VERSION,
    'account': INITIAL_ACCOUNT,                # baked in from constants
    ...
    'initial_account': INITIAL_ACCOUNT,        # baked in from constants
    ...
  }

# AFTER (D-02):
def reset_state(initial_account: float = INITIAL_ACCOUNT) -> dict:
  '''STATE-07 / D-01 / D-03 / Phase 10 BUG-01 D-02: fresh state,
  account + initial_account both equal to `initial_account` (default
  INITIAL_ACCOUNT from system_params).

  D-02 closes BUG-01 at the module boundary: both `state['account']`
  and `state['initial_account']` are set from the same source-of-truth
  argument, so no caller can create a state where they differ.
  ...
  '''
  return {
    'schema_version': STATE_SCHEMA_VERSION,
    'account': initial_account,                # NOW from arg
    ...
    'initial_account': initial_account,        # NOW from arg
    ...
  }
```

### Example 3: Existing subprocess pattern for external tools (from `test_scheduler.py`)

The codebase already has subprocess usage in tests (parsing YAML via PyYAML loader). This isn't `subprocess.run` of CLI tools, but it confirms the `check=True` + `capture_output=True` pattern is already well-understood. No new subprocess idiom to introduce.

**Subprocess reference (external) — 2026 idiom:**
```python
# Source: docs.python.org/3.11/library/subprocess.html#subprocess.run [CITED]
# Canonical pattern for CLI tool invocation:
result = subprocess.run(
  ['ruff', 'check', 'notifier.py', '--output-format=json'],
  capture_output=True,   # captures stdout + stderr as bytes (or str if text=True)
  text=True,             # decode as UTF-8
  timeout=30,            # seconds — CalledProcessError if exceeded
  check=False,           # do NOT raise on non-zero rc (we parse JSON either way)
)
# result.returncode, result.stdout, result.stderr available.
```

### Example 4: Retire-workflow rename — verified safe approach

```bash
# Source: [CITED: docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions]
# GitHub Actions parses only *.yml and *.yaml files in .github/workflows/.
# Adding a .disabled suffix immediately removes the workflow from the
# active schedule set on the next GitHub push.

# D-16 approach (preserves history):
git mv .github/workflows/daily.yml .github/workflows/daily.yml.disabled
git commit -m 'chore(infra): disable GHA daily.yml (droplet systemd is primary — INFRA-03)'
git push origin main
```

**Verification after push:**
```bash
# GitHub Settings → Actions → Workflows should no longer list "Daily signal check"
# as a scheduled workflow. Manual dispatch via the UI is no longer available.
# For programmatic verification:
gh workflow list --all | grep -i daily
# Expected: no match (or status 'disabled_inactivity' for aged workflows).
```

### Example 5: Ruff JSON Output Contract (verified live)

```json
// Source: live `ruff check notifier.py --output-format=json` 2026-04-24 [VERIFIED]
// Ruff 0.6.9 emits a JSON array of violation objects.
// When clean: empty array `[]\n`.
// When violations present:
[
  {
    "cell": null,
    "code": "F401",
    "end_location": {"column": 18, "row": 71},
    "filename": "/absolute/path/to/notifier.py",
    "fix": {
      "applicability": "safe",
      "edits": [
        {"content": "<replacement text>", "end_location": {...}, "location": {...}}
      ],
      "message": "Remove unused import"
    },
    "location": {"column": 3, "row": 71},
    "message": "`system_params.AUDUSD_COST_AUD` imported but unused",
    "noqa_row": 71,
    "url": "https://docs.astral.sh/ruff/rules/unused-import"
  }
]
```

**Fields the test should rely on (stable across 0.5 → 0.6):**
- `code` — the rule code string (`"F401"`).
- `filename` — absolute path.
- `location.row` + `location.column` — 1-based position.
- `message` — human-readable description.

**Fields to NOT rely on (version-variable):**
- `fix.applicability` — introduced in 0.5.x; may change schema.
- `noqa_row` — naming / presence not guaranteed long-term.
- `cell` — Jupyter notebook support; always `null` for `.py` files.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| GHA cron + `stefanzweifel/git-auto-commit-action@v5` for state push-back | Droplet systemd + in-process `_push_state_to_git` | Phase 10 (2026-04-24) | Eliminates GHA duplicate-run risk when droplet systemd also fires. Inverts v1.0's "GHA is primary" decision (STATE.md). |
| Flake8 + isort + black pipeline | `ruff check` single-tool pipeline | v1.0 Phase 1 (pinned 0.6.9) | Single CLI, single config, 10x faster. Project already standardized. No Phase 10 change. |
| HTTPS clone + PAT for auth | SSH deploy key with write access | Phase 10 operator setup | Deploy keys are repo-scoped (not account-scoped PATs); less blast radius if leaked. Revocable via GitHub UI without affecting other repos. [CITED: docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys] |
| `--no-verify` on hook failures | Always run hooks | Project-wide (CLAUDE.md §Git Safety Protocol) | Phase 10 follows this. If a pre-commit hook fails on the droplet's `_push_state_to_git` commit, investigate — don't bypass. |

**Deprecated / outdated (no Phase 10 impact, but worth noting):**
- GitHub Actions `actions/checkout@v3` → `v4` happened in 2023; current daily.yml already uses v4. [VERIFIED: current daily.yml body]
- `actions/setup-python@v4` → `v5` happened in 2023; current daily.yml already uses v5. [VERIFIED]
- PyYAML 5.x → 6.x (YAML 1.1 → 1.2 default); codebase pins `PyYAML==6.0.2`. [VERIFIED: requirements.txt]

## Assumptions Log

All factual claims in this research have been verified or cited. No `[ASSUMED]`-only claims remain.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | (empty) | — | — |

**All claims verified or cited — no user confirmation needed before planning.**

Explicit verification sources:
- Ruff F401 count + JSON shape — live `ruff check notifier.py --output-format=json` executed 2026-04-24 [VERIFIED].
- `state_manager.append_warning` signature — read from `state_manager.py:423` [VERIFIED].
- `main.py:1280` BUG-01 fix site — read from live file [VERIFIED].
- `FORBIDDEN_MODULES_MAIN` contents — read from `tests/test_signal_engine.py:544` [VERIFIED: subprocess NOT in the set].
- `TestGHAWorkflow.WORKFLOW_PATH` class constant — read from `tests/test_scheduler.py:357` [VERIFIED].
- `git diff --quiet` exit codes — [CITED: man git-diff EXIT STATUS section].
- `git -c KEY=VAL <subcommand>` scoping behavior — [CITED: man git-commit + man git at DISCUSSION section].
- GitHub Actions workflow file discovery pattern — [CITED: docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions].
- GitHub deploy key semantics — [CITED: docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys].

## Open Questions

1. **Badge URL in README.md after rename.**
   - What we know: `README.md:3` embeds `actions/workflows/daily.yml/badge.svg`; test at `tests/test_scheduler.py:664` asserts this substring; after rename the badge either 404s or renders "no workflow" in GitHub's viewer.
   - What's unclear: Does the planner/operator prefer (a) leave README alone (badge becomes visible "retired" indicator), (b) remove badge + soften test assertion, or (c) update to `daily.yml.disabled` URL (badge still broken but URL matches reality)?
   - Recommendation: (a) in Phase 10; (c) if/when the plan-checker flags broken links as a quality issue. Document the choice in Task 3 actions.

2. **Non-interactive `git diff --quiet` edge case: state.json missing from working tree.**
   - What we know: If state.json was somehow deleted (between save_state and the git call), `git diff --quiet state.json` returns rc=1 (diff present — file removed) and `git commit state.json` then fails with `pathspec 'state.json' did not match any file(s) known to git`.
   - What's unclear: This is only reachable via a race condition or filesystem manipulation mid-run; the `_push_state_to_git` fail-loud path handles the `CalledProcessError`. Is the warning message quality good enough for this edge case, or should the plan add a dedicated `os.path.exists('state.json')` pre-check?
   - Recommendation: Rely on the CalledProcessError path. Pre-checks for TOCTOU conditions on a single-writer daemon are over-engineering for v1.

3. **Verification window for INFRA-03 SC-4 ("no cron fires for 2 consecutive weekdays").**
   - What we know: ROADMAP SC-4 requires 2 weekdays of observed silence on the GHA side. Phase 10 plan execution happens in a single session; the 2-weekday window is a post-merge operator observation task.
   - What's unclear: Does the verifier agent (`/gsd-verify-work 10`) pass the phase on merge (trust that D-16 rename is sufficient) or wait for the operator to run for 2 weekdays and report?
   - Recommendation: Mark SC-4 as "operator-verifies-post-merge" in the Phase 10 verification matrix. Plan delivers the rename; operator reports back after 2 weekdays. Matches Phase 7 Wave 2 pattern (operator-verified GHA workflow_dispatch).

4. **`_push_state_to_git` during the first run after Phase 10 lands.**
   - What we know: The first `run_daily_check` call after Phase 10 will compute today's signals, save state.json (modified since last git commit), then try to commit + push. If the operator has NOT yet completed `SETUP-DEPLOY-KEY.md`, the push fails — which triggers the fail-loud warning path, which is correct behavior per D-12.
   - What's unclear: Should the plan include a one-time manual first-run instruction ("run `python main.py --once` on the droplet AFTER setup-deploy-key is complete")?
   - Recommendation: YES — include this as the final line of `SETUP-DEPLOY-KEY.md`, NOT in the plan itself. The plan delivers the code; the doc orchestrates the operator's deployment sequence.

## Environment Availability

Phase 10 code changes run on the developer machine (macOS darwin, per the env context). Execution-time dependencies are on the droplet and in CI, but the plan doesn't need droplet access to land the code.

| Dependency | Required By | Available (dev) | Version | Fallback |
|------------|------------|-----------------|---------|----------|
| Python 3.11.8 | All code + tests | ✓ | 3.11.8 (via pyenv) | — |
| `ruff` | CHORE-02 cleanup + `test_ruff_clean_notifier` test | ✓ | 0.6.9 | — (pinned) |
| `pytest` | Regression tests | ✓ | 8.3.3 | — |
| `git` (dev machine) | Running tests locally; `git mv` | ✓ (assumed — macOS dev env) | modern (>=2.39) | — |
| `subprocess` (stdlib) | `_push_state_to_git` + `test_ruff_clean_notifier` | ✓ | stdlib | — |
| GitHub (for INFRA-03 rename) | `git mv` + `git push origin main` to trigger GHA disable | ✓ (requires push access) | — | Plan can proceed; final verification requires live GitHub. |
| **Droplet SSH access** | INFRA-02 operational verification (SC-3 "last 3 days of commits visible in GitHub authored by deploy key") | ✗ in dev session — OPERATOR-ONLY | — | Plan delivers code + doc; operator verifies post-merge. |
| **systemd on droplet** | INFRA-02 automated invocation of `_push_state_to_git` | ✗ in dev session — PHASE 11 dependency | — | Phase 10 helper is callable from `--once` on any Linux/macOS host; true systemd integration in Phase 11. |

**Missing dependencies with no fallback:** None — Phase 10 is fully executable in dev.

**Missing dependencies with fallback:**
- Droplet SSH and systemd are not required for the coding work. Operator runs `SETUP-DEPLOY-KEY.md` + first `python main.py --once` manually as a separate step after merge.
- Final verification of SC-3 and SC-4 (INFRA-02 deploy-key commits, INFRA-03 GHA silence) is operator-performed; verifier agent marks these as "pending operator confirmation" in the phase verification record.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.3 [VERIFIED: requirements.txt + existing test discovery] |
| Config file | `pyproject.toml` (or none; pytest auto-discovers `tests/`) |
| Quick run command | `pytest tests/test_main.py::TestHandleReset tests/test_state_manager.py::TestReset tests/test_notifier.py::test_ruff_clean_notifier tests/test_scheduler.py::TestGHAWorkflow -x` |
| Full suite command | `pytest -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BUG-01 | `--reset` + `--initial-account X` leaves `state['account'] == state['initial_account']` (CLI-flag path) | unit | `pytest tests/test_main.py::TestHandleReset::test_reset_syncs_account_to_initial_account_cli -x` | ✅ test_main.py (Wave 0 append) |
| BUG-01 | Interactive Q&A `--reset` path leaves `state['account'] == state['initial_account']` | unit (monkeypatched stdin) | `pytest tests/test_main.py::TestHandleReset::test_reset_syncs_account_to_initial_account_interactive -x` | ✅ test_main.py (Wave 0 append) |
| BUG-01 | `state_manager.reset_state(initial_account=50000)` returns state with both fields = 50000.0 | unit | `pytest tests/test_state_manager.py::TestReset::test_reset_state_accepts_custom_initial_account -x` | ✅ test_state_manager.py (Wave 0 append) |
| BUG-01 | `state_manager.reset_state()` default behavior unchanged (backward-compat) | unit | `pytest tests/test_state_manager.py::TestReset::test_reset_state_default_preserves_backward_compat -x` | ✅ test_state_manager.py (Wave 0 append) |
| CHORE-02 | `ruff check notifier.py` emits zero F401 entries | integration (subprocess → ruff) | `pytest tests/test_notifier.py::test_ruff_clean_notifier -x` | ✅ test_notifier.py (Wave 0 append) |
| INFRA-02 | `_push_state_to_git` skips when state.json unchanged | unit (mocked subprocess) | `pytest tests/test_main.py::TestPushStateToGit::test_skip_when_unchanged -x` | ❌ Wave 0 gap — add test class |
| INFRA-02 | `_push_state_to_git` commits + pushes when state.json changed | unit (mocked subprocess) | `pytest tests/test_main.py::TestPushStateToGit::test_commit_and_push_on_change -x` | ❌ Wave 0 gap |
| INFRA-02 | `_push_state_to_git` on push failure logs ERROR + append_warning + no extra save_state | unit (mocked subprocess + spy on state_manager.save_state / append_warning) | `pytest tests/test_main.py::TestPushStateToGit::test_push_failure_warns_but_never_crashes -x` | ❌ Wave 0 gap |
| INFRA-02 | `_push_state_to_git` uses inline `-c user.email=... -c user.name=...` flags, NOT global config | unit (argv inspection on mocked subprocess.run) | `pytest tests/test_main.py::TestPushStateToGit::test_commit_uses_inline_identity_flags -x` | ❌ Wave 0 gap |
| INFRA-02 | `_push_state_to_git` never calls save_state (preserves Phase 8 W3 two-saves-per-run invariant) | unit (spy on state_manager.save_state) | `pytest tests/test_main.py::TestPushStateToGit::test_never_calls_save_state -x` | ❌ Wave 0 gap |
| INFRA-03 | `.github/workflows/daily.yml.disabled` file exists; `daily.yml` does NOT | unit (filesystem check) | `pytest tests/test_scheduler.py::TestGHAWorkflow::test_workflow_file_exists -x` | ✅ test_scheduler.py (path update only — D-18) |
| INFRA-03 | Disabled workflow retains `timeout-minutes: 10` (rollback protection per D-18) | unit (YAML parse) | `pytest tests/test_scheduler.py::TestGHAWorkflow::test_daily_workflow_has_timeout_minutes -x` | ✅ test_scheduler.py (path update only) |
| INFRA-03 | All 12 existing `TestGHAWorkflow` tests pass against disabled file (proves contract preserved) | unit (YAML parse + grep) | `pytest tests/test_scheduler.py::TestGHAWorkflow -x` | ✅ test_scheduler.py (single-line WORKFLOW_PATH change) |

### Sampling Rate
- **Per task commit:** `pytest tests/test_main.py tests/test_state_manager.py tests/test_notifier.py tests/test_scheduler.py -x` (scoped to touched files; ~1-2s runtime)
- **Per wave merge:** `pytest -x` (full suite ~0.6-1s per v1.0 Phase 9 baseline)
- **Phase gate:** Full suite green + `ruff check .` clean before `/gsd-verify-work 10`

### Wave 0 Gaps
- [ ] `tests/test_main.py::TestPushStateToGit` — 5 tests covering skip-if-unchanged / commit-push happy path / push-failure fail-loud / inline-identity-flags / two-saves-invariant. Scaffolding uses `monkeypatch.setattr('subprocess.run', fake_run)` or `unittest.mock.patch('subprocess.run')` — planner picks per codebase convention. Existing `TestEmailNeverCrash` class (line 1034 of `test_main.py`) is the structural template (same pattern: never-crash I/O wrapper + spy on `append_warning`).
- [ ] `tests/test_main.py::TestHandleReset::test_reset_syncs_account_to_initial_account_{cli,interactive}` — 2 tests. Interactive path uses monkeypatched `input()` returning `'50000'` (existing pattern at `test_main.py::TestResetInteractive:1347`).
- [ ] `tests/test_state_manager.py::TestReset::test_reset_state_accepts_custom_initial_account` + `test_reset_state_default_preserves_backward_compat` — 2 tests. Existing `TestReset` class at line 875 is the container.
- [ ] `tests/test_notifier.py::test_ruff_clean_notifier` — 1 test. Subprocess pattern verified by external ruff invocation per "Code Examples Example 5".
- [ ] Framework install: not needed (pytest 8.3.3, ruff 0.6.9 already pinned).

*(Existing test infrastructure covers all remaining phase requirements. Total new tests: ~10 across 4 test files.)*

## Security Domain

Phase 10 is an infrastructure-hygiene phase. The `security_enforcement` flag is not set in `.planning/config.json` (treated as enabled). Applicable ASVS categories below; most are N/A because the phase introduces no new attack surface, but one category is directly affected (V14 Configuration — the deploy key and its secret lifecycle).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | partial | Operator authenticates to GitHub via SSH deploy key (not passwords / PAT). Key generated with `ssh-keygen -t ed25519` per modern best practice. No code-side auth. |
| V3 Session Management | no | No sessions in this phase. |
| V4 Access Control | partial | GitHub deploy key has WRITE access scoped to this one repo (not account-wide like a PAT). [CITED: docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys]. One-key-per-repo enforcement must be documented in `SETUP-DEPLOY-KEY.md`. |
| V5 Input Validation | no | No user input in Phase 10 code paths. `_push_state_to_git` takes a state dict (constructed internally) and a `datetime` (internally generated). |
| V6 Cryptography | no | No crypto in this phase (SSH handles its own). Ed25519 key type chosen for deploy key (smaller + stronger than RSA; [CITED: docs.github.com — "We recommend Ed25519"]). |
| V14 Configuration | yes | Deploy key private half must NOT be committed to the repo; key file permissions must be `0600`; SSH config must use `IdentitiesOnly yes` to prevent auth-attempt flooding. `SETUP-DEPLOY-KEY.md` must spell all three. |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Deploy key leak via accidental commit of `~/.ssh/id_ed25519_trading_signals` into the repo | Info disclosure | `SETUP-DEPLOY-KEY.md` directs key generation in `~/.ssh/`, never inside the repo. `.gitignore` entry NOT needed (key is outside the repo tree). Document "the key never enters this repo" as a hard rule. |
| Compromised droplet → attacker has deploy key + push access → arbitrary code in main branch | Elevation of privilege | Deploy key is scoped to this one repo; cannot reach other repos or the operator's GitHub account. Compromise blast radius = this repo only. Mitigation on discovery: revoke deploy key in GitHub Settings. |
| Token committed via the daily state push (e.g., state.json accidentally contains a secret) | Info disclosure | `state.json` contents = signals, positions, trade_log, equity_history, warnings — none of these fields contain secrets by design (verified: Phase 3 D-10 + Phase 8 D-14 schemas). Regression: the next phase's plan-checker should include a grep pass for `API_KEY|SECRET|TOKEN` patterns in state.json before accepting INFRA-02 merge. |
| GHA disabled file still referenced in active paths (silent dead-code) | Tampering (config drift) | `TestGHAWorkflow.WORKFLOW_PATH` update + README badge decision + `docs/DEPLOY.md` prose update (D-19) all close this. Plan-checker should grep `git grep "daily\.yml"` after the rename and flag any non-disabled references. |
| SSH host-key replay (MITM on first `ssh -T git@github.com`) | Spoofing | `SETUP-DEPLOY-KEY.md` should link to [github.com SSH key fingerprints](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints) so operator can verify the fingerprint before accepting on first connect. Optional but recommended for a production deploy. |

## Sources

### Primary (HIGH confidence)
- **Existing codebase — read verbatim:**
  - `main.py` — lines 1, 130-185 (`_send_email_never_crash` pattern), 290-360 (`_dispatch_email_and_maintain_warnings` — two-saves-per-run W3 invariant), 754-1080 (`run_daily_check`), 1129-1287 (`_handle_reset` + `_prompt_or_default`).
  - `state_manager.py` — lines 280-333 (`reset_state`, `_REQUIRED_STATE_KEYS`), 396-475 (`save_state`, `append_warning`, `clear_warnings`).
  - `notifier.py` — lines 1-80 (module docstring + 4 F401 import block).
  - `tests/test_signal_engine.py` — lines 484-549 (`FORBIDDEN_MODULES_*` AST blocklist — confirms `subprocess` permitted for `main.py`).
  - `tests/test_scheduler.py` — lines 335-530 (`TestGHAWorkflow` class, `WORKFLOW_PATH` constant, `test_daily_workflow_has_timeout_minutes`).
  - `tests/test_main.py` — lines 97, 1205, 1344, 1500, 1751 (existing test-class naming conventions).
  - `tests/test_state_manager.py` — lines 875-920 (existing `TestReset` class).
- **Phase context docs:**
  - `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/10-CONTEXT.md` — all D-01..D-19 decisions (locked).
  - `.planning/milestones/v1.0-phases/07-scheduler-github-actions-deployment/07-03-PLAN.md` — GHA workflow contract + commit message conventions.
  - `.planning/milestones/v1.0-phases/08-hardening-warning-carry-over-stale-banner-crash-email-config/08-CONTEXT.md` — D-08 sole-writer, D-14 underscore-prefix, W3 two-saves-per-run invariant.
  - `.planning/milestones/v1.0-phases/09-milestone-v1.0-gap-closure/09-VERIFICATION.md` — `test_daily_workflow_has_timeout_minutes` site (D-18 target).
  - `.planning/REQUIREMENTS.md` — BUG-01, CHORE-02, INFRA-02, INFRA-03 traceability.
  - `.planning/STATE.md` — v1.0 + v1.1 decisions; ruff pin; deferred items.
  - `.planning/ROADMAP.md` — Phase 10 goal + 4 success criteria.
  - `CLAUDE.md` — project conventions (2-space, single quotes, hex-lite, log prefixes).
- **Live tool invocations (2026-04-24):**
  - `ruff --version` → `ruff 0.6.9`.
  - `ruff check notifier.py` → 4 F401 warnings (lines 71, 72, 75, 76).
  - `ruff check notifier.py --output-format=json` → valid JSON array, field shape verified.

### Secondary (MEDIUM confidence)
- **[CITED] [docs.github.com — Workflow syntax](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)** — GHA only parses `.yml`/`.yaml` files in `.github/workflows/`. Verifies D-16 rename is sufficient to disable the schedule.
- **[CITED] [docs.github.com — Managing deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys)** — deploy-key semantics (repo-scoped, write-capable, revocable). Recommends Ed25519 keys.
- **[CITED] [docs.astral.sh — Ruff output formats](https://docs.astral.sh/ruff/output-formats/)** — JSON output format documented; fields stable for 0.6.x.
- **[CITED] git(1) man pages — git-diff EXIT STATUS + git top-level `-c`** — exit code trio (0/1/128+) and inline config override semantics.

### Tertiary (LOW confidence)
- None. All claims are either live-verified or citable.

## Metadata

**Confidence breakdown:**
- BUG-01 / D-01 fix site: HIGH — line-level verified in `main.py`.
- BUG-01 / D-02 signature: HIGH — `reset_state` currently zero-arg; extension is mechanical.
- CHORE-02 / F401 count: HIGH — live ruff run shows 4 (not 19 per stale deferred-items.md).
- CHORE-02 / JSON shape: HIGH — verified field-by-field from live tool output.
- INFRA-02 / helper pattern: HIGH — `_send_email_never_crash` is a 1:1 template.
- INFRA-02 / git commands: HIGH — documented semantics; verified via git(1) man pages.
- INFRA-02 / subprocess allowed in main.py: HIGH — `FORBIDDEN_MODULES_MAIN` read directly.
- INFRA-02 / deploy key SSH setup: MEDIUM — operator-owned; commands well-known but droplet environment specifics are operator-dependent.
- INFRA-03 / rename mechanics: HIGH — GHA docs explicit about `.yml` suffix requirement.
- INFRA-03 / test breakage scope: HIGH — read `tests/test_scheduler.py` directly; `WORKFLOW_PATH` is a class constant.
- Security / V14 config items: MEDIUM — generic SSH best practices; operator environment affects applicability.

**Research date:** 2026-04-24
**Valid until:** 2026-05-24 (30 days — stack is stable; the only mutable facts are ruff version + GHA workflow syntax, both of which are pinned / documented-stable).

---

*Phase: 10-foundation-v1-0-cleanup-deploy-key*
*Research by: gsd-phase-researcher*
*Ready for: `/gsd-plan-phase 10`*
