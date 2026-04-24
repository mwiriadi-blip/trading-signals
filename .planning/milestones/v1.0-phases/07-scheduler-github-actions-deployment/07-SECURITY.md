---
phase: 07
phase_name: scheduler-github-actions-deployment
audit_date: 2026-04-23
auditor: gsd-security-auditor
asvs_level: 1
threats_total: 26
threats_closed: 26
threats_open: 0
status: secured
---

# Phase 07 — Security Audit (Scheduler + GitHub Actions Deployment)

## Executive Summary

All 26 threats in the Phase 7 register (14 `mitigate`, 12 `accept`) are verified CLOSED against committed code. Every declared mitigation pattern was located at the exact file/line cited in the mitigation plan; every accepted-risk entry is internally consistent with the observed implementation. No MEDIUM or HIGH threats remain open; the phase clears the `MEDIUM_OR_HIGH` block-on threshold.

## Threat Register

### Plan 07-01 — Wave 0 Scaffold

| Threat ID | Category | Severity | Disposition | Status | Evidence |
|-----------|----------|----------|-------------|--------|----------|
| T-07-01-01 | Tampering (supply chain) | LOW | mitigate | CLOSED | `requirements.txt:8` = `schedule==1.2.2` (exact `==` pin, no `>=`/`~=`) |
| T-07-01-02 | Tampering (supply chain) | LOW | mitigate | CLOSED | `requirements.txt:4` = `python-dotenv==1.0.1` (exact pin) |
| T-07-01-03 | Tampering (supply chain) | LOW | mitigate | CLOSED | `requirements.txt:1` = `PyYAML==6.0.2` (exact pin) |
| T-07-01-04 | Info Disclosure | MEDIUM | mitigate | CLOSED | `.gitignore:4` = `.env`; `tests/test_scheduler.py:330` `monkeypatch.setattr('dotenv.load_dotenv', _recorder)` in TestDotenvLoading; `tests/test_scheduler.py:178` + `tests/test_scheduler.py:291` similarly patch load_dotenv in TestImmediateFirstRun + TestDefaultModeDispatch |
| T-07-01-05 | Info Disclosure | LOW | mitigate | CLOSED | `.env.example:25` `RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` (obvious placeholder); `.env.example:26` `SIGNALS_EMAIL_TO=your-email@example.com` (placeholder); no real `re_[A-Za-z0-9]{40,}` secret tokens |
| T-07-01-06 | EoP | LOW | accept | CLOSED | Rationale internally consistent: stubs raise `NotImplementedError`; `main.py:912-915` outer `except Exception` boundary catches and logs `[Sched] ERROR: unexpected crash` with rc=1 exit; never silently passes |
| T-07-01-07 | DoS | LOW | accept | CLOSED | Rationale internally consistent: dotenv is parsed-only (stdlib lexer, no recursion/exec); single-operator controls `.env` content |
| T-07-01-08 | Repudiation (AST blocklist) | LOW | mitigate | CLOSED | `tests/test_signal_engine.py:544-549` `FORBIDDEN_MODULES_MAIN` does NOT contain `'schedule'` or `'dotenv'`; `tests/test_signal_engine.py:556-565` `FORBIDDEN_MODULES_DASHBOARD` DOES contain both; `tests/test_signal_engine.py:574-583` `FORBIDDEN_MODULES_NOTIFIER` DOES contain both |

### Plan 07-02 — Wave 1 Loop Body + Weekday Gate

| Threat ID | Category | Severity | Disposition | Status | Evidence |
|-----------|----------|----------|-------------|--------|----------|
| T-07-02-01 | DoS (test infinite loop) | LOW | mitigate | CLOSED | `main.py:209` `max_ticks: int \| None = None` in `_run_schedule_loop` signature; `tests/test_scheduler.py:204` uses `max_ticks=0`, `:222` uses `max_ticks=1`, `:236` uses `max_ticks=1` — all finite |
| T-07-02-02 | Tampering (timing) | MEDIUM | mitigate | CLOSED | `main.py:232-236` `tzname = _get_process_tzname()` then `assert tzname == 'UTC', (...)` — semantically equivalent to the inline form; routes through the Wave 0 wrapper; no raw `time.tzname[0]` access anywhere except inside the wrapper itself (`main.py:172`); grep confirms 0 matches for `time.tzname[0]` outside the wrapper body |
| T-07-02-03 | DoS (loop crash) | HIGH | mitigate | CLOSED | `main.py:194` `except (DataFetchError, ShortFrameError) as e` → `logger.warning('[Sched] data-layer failure...')`; `main.py:196-200` `except Exception as e` → `logger.warning('[Sched] unexpected error... (loop continues)')`; `main.py:191-193` rc!=0 branch `logger.warning('[Sched] daily check returned rc=%d (loop continues)')`. All three paths covered by `tests/test_scheduler.py:243-275` (TestLoopErrorHandling 3 tests) |
| T-07-02-04 | Info Disclosure (log leak) | LOW | accept | CLOSED | Rationale internally consistent: pre-existing Phase 4-6 logging posture; operator-controlled log sink; no new surface introduced |
| T-07-02-05 | Tampering (weekday) | MEDIUM | mitigate | CLOSED | `main.py:565` `if run_date.weekday() >= system_params.WEEKDAY_SKIP_THRESHOLD:` (references constant, not magic 5); `main.py:567` logs `'[Sched] weekend skip %s (weekday=%d)...'`; `tests/test_scheduler.py:56-160` TestWeekdayGate covers Sat (weekday=5), Sun (weekday=6), Mon (weekday=0) with explicit fetch-call count + ticker identity assertions |
| T-07-02-06 | Repudiation (git blame) | LOW | accept | CLOSED | Rationale internally consistent: 07-02-SUMMARY.md §Commits shows 5 atomic commits (2534427, 3279c31, 2176c5d, d9400fc, fe210f6), all signed, no `--amend`, no `--no-verify` |
| T-07-02-07 | EoP (AST blocklist) | LOW | mitigate | CLOSED | `tests/test_signal_engine.py:544-549` `FORBIDDEN_MODULES_MAIN` unchanged by Wave 1 (still 4 strings: numpy/yfinance/requests/pandas); DASHBOARD/NOTIFIER blocklists retain Wave 0 `schedule` + `dotenv` entries |
| T-07-02-08 | Info Disclosure (.env leak in tests) | MEDIUM | mitigate | CLOSED | `tests/test_scheduler.py:330` TestDotenvLoading patches `dotenv.load_dotenv` to a recorder; `tests/test_scheduler.py:291` TestDefaultModeDispatch patches same; `tests/test_notifier.py:975,987` `monkeypatch.delenv('RESEND_API_KEY', raising=False)` preserves Phase 6 discipline |

### Plan 07-03 — Wave 2 GHA Workflow + Docs

| Threat ID | Category | Severity | Disposition | Status | Evidence |
|-----------|----------|----------|-------------|--------|----------|
| T-07-03-01 | EoP (workflow permissions) | LOW | mitigate | CLOSED | `.github/workflows/daily.yml:7-8` `permissions: contents: write` only; grep for `issues: write` = 0 matches; grep for `pull-requests: write` = 0 matches |
| T-07-03-02 | Info Disclosure (secret logs) | MEDIUM | mitigate | CLOSED | `.github/workflows/daily.yml:31-34` explicit per-secret mapping (`RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}`, `SIGNALS_EMAIL_TO: ${{ secrets.SIGNALS_EMAIL_TO }}`); grep for `env: ${{ secrets` bulk-exposure pattern = 0 matches |
| T-07-03-03 | Supply chain (major-tag pin) | MEDIUM | accept | CLOSED | Rationale internally consistent: `.github/workflows/daily.yml:37` `uses: stefanzweifel/git-auto-commit-action@v5` major-tag pin; tradeoff documented per D-09 operator choice; alternative SHA-pin path documented in docs/DEPLOY.md |
| T-07-03-04 | DoS (cron queue delay) | LOW | accept | CLOSED | Rationale internally consistent: `.github/workflows/daily.yml:4` comment "GHA drift 5–30m" explicit; single-operator daily email, not time-critical |
| T-07-03-05 | Repudiation (bot attribution) | LOW | accept | CLOSED | Rationale internally consistent: `.github/workflows/daily.yml:43-44` `commit_user_name: github-actions[bot]` + `commit_user_email: 41898282+github-actions[bot]@users.noreply.github.com` (canonical GitHub bot identity) |
| T-07-03-06 | Tampering (branch protection) | LOW | mitigate | CLOSED | `docs/DEPLOY.md:149` `### "Branch protection blocked the commit"` troubleshooting entry present |
| T-07-03-07 | Info Disclosure (public repo state.json) | MEDIUM | accept | CLOSED | Rationale internally consistent: operator's choice to use public repo; state.json contains trading data (operator's own), no PII/secrets; private-repo fallback documented in docs/DEPLOY.md |
| T-07-03-08 | Tampering (force-add scope) | LOW | mitigate | CLOSED | `.github/workflows/daily.yml:42` `add_options: '-f'` present; `.github/workflows/daily.yml:41` `file_pattern: state.json` scopes the force-add to exactly one file |
| T-07-03-09 | EoP (docs spoofing) | LOW | accept | CLOSED | Rationale internally consistent: docs are version-controlled in the same repo the operator forks/owns; negligible threat surface |
| T-07-03-10 | Info Disclosure (secret names in docs) | LOW | accept | CLOSED | Rationale internally consistent: secret NAMES (`RESEND_API_KEY`, `SIGNALS_EMAIL_TO`) are not secrets; documenting env contract is standard practice; real secret VALUES never committed |

## Accepted Risks

Twelve threats carry forward as accepted — all single-operator / signal-only tool rationales that remain valid:

| ID | Category | Severity | Rationale (carried forward) |
|----|----------|----------|-----------------------------|
| T-07-01-06 | EoP | LOW | Wave 0 stubs raise `NotImplementedError`; outer `except Exception` at `main.py:912-915` catches and logs `[Sched] ERROR: unexpected crash`; non-zero exit propagates. Bodies landed in Wave 1; accept no longer load-bearing but entry retained for historical audit. |
| T-07-01-07 | DoS | LOW | `python-dotenv` parses via stdlib-based lexer; does not recurse or execute. Large `.env` would slow startup but not hang. Single-operator context. |
| T-07-02-04 | Info Disclosure | LOW | Exceptions carry error descriptions (e.g. yfinance body). Phase 4-6 already logs these at WARN; Phase 7 inherits posture. Operator controls log sink. |
| T-07-02-06 | Repudiation | LOW | Wave 1 split into 5 atomic commits; `git blame` granularity preserved. |
| T-07-03-03 | Supply chain | MEDIUM | `stefanzweifel/git-auto-commit-action@v5` major-tag pin per D-09 operator choice. Rug-pull risk on `@v5` tag retcon accepted; SHA-pin alternative documented in docs/DEPLOY.md. |
| T-07-03-04 | DoS | LOW | GHA cron queue drift 5–30 min documented in `daily.yml:4` comment and docs/DEPLOY.md troubleshooting. Single-operator daily email not time-critical. |
| T-07-03-05 | Repudiation | LOW | Canonical `github-actions[bot]` identity attributes automated commits clearly; operator's human commits remain distinguishable. |
| T-07-03-07 | Info Disclosure | MEDIUM | Operator chose public repo. state.json holds trading data (operator's own), no PII/secrets. Private-repo fork documented as privacy fallback. |
| T-07-03-09 | EoP | LOW | Docs are version-controlled in the repo the operator owns; threat surface negligible for single-operator tool. |
| T-07-03-10 | Info Disclosure | LOW | Secret NAMES are not secrets. Documenting required env vars is standard practice; VALUES never committed. |

## Audit Trail

```
T-07-01-01: VERIFIED requirements.txt:8 `schedule==1.2.2` (exact pin)
T-07-01-02: VERIFIED requirements.txt:4 `python-dotenv==1.0.1` (exact pin)
T-07-01-03: VERIFIED requirements.txt:1 `PyYAML==6.0.2` (exact pin)
T-07-01-04: VERIFIED .gitignore:4 `.env` + tests/test_scheduler.py:330 monkeypatch dotenv.load_dotenv
T-07-01-05: VERIFIED .env.example:25-26 obvious placeholders, no real secret values
T-07-01-06: VERIFIED (accept) main.py:912-915 outer except Exception catches NotImplementedError path
T-07-01-07: VERIFIED (accept) python-dotenv lexer-based parse; single-operator context
T-07-01-08: VERIFIED tests/test_signal_engine.py:544-549 MAIN omits schedule/dotenv; :556-565 DASHBOARD adds them; :574-583 NOTIFIER adds them
T-07-02-01: VERIFIED main.py:209 max_ticks default None; tests/test_scheduler.py:204,222,236 use finite values
T-07-02-02: VERIFIED main.py:232-233 tzname = _get_process_tzname(); assert tzname == 'UTC' (wrapper-routed)
T-07-02-03: VERIFIED main.py:191-200 three-branch never-crash net (rc!=0 + typed + catch-all) all log [Sched]
T-07-02-04: VERIFIED (accept) posture inherited from Phase 4-6 logging
T-07-02-05: VERIFIED main.py:565 uses WEEKDAY_SKIP_THRESHOLD constant; main.py:567 logs '[Sched] weekend skip'; tests cover Sat/Sun/Mon
T-07-02-06: VERIFIED (accept) 5 atomic Wave-1 commits per 07-02-SUMMARY.md
T-07-02-07: VERIFIED tests/test_signal_engine.py:544-549 FORBIDDEN_MODULES_MAIN unchanged (4 strings)
T-07-02-08: VERIFIED tests/test_scheduler.py:178,291,330 load_dotenv patched; tests/test_notifier.py:975,987 delenv RESEND_API_KEY
T-07-03-01: VERIFIED .github/workflows/daily.yml:7-8 contents: write only; grep 0 matches for issues:write / pull-requests:write
T-07-03-02: VERIFIED .github/workflows/daily.yml:31-34 explicit per-secret mapping; grep 0 matches for bulk 'env: ${{ secrets' pattern
T-07-03-03: VERIFIED (accept) .github/workflows/daily.yml:37 @v5 major-tag pin per D-09
T-07-03-04: VERIFIED (accept) .github/workflows/daily.yml:4 drift comment + DEPLOY.md troubleshooting
T-07-03-05: VERIFIED (accept) .github/workflows/daily.yml:43-44 canonical github-actions[bot] identity
T-07-03-06: VERIFIED docs/DEPLOY.md:149 "Branch protection blocked the commit" troubleshooting entry
T-07-03-07: VERIFIED (accept) public-repo state.json operator choice; documented
T-07-03-08: VERIFIED .github/workflows/daily.yml:41 file_pattern: state.json AND :42 add_options: '-f' both present
T-07-03-09: VERIFIED (accept) version-controlled docs in operator's own repo
T-07-03-10: VERIFIED (accept) secret names not secrets; values never committed
```

## Unregistered Flags

None. No Phase 7 SUMMARY files declared any `## Threat Flags` section; no new attack surface was flagged by executors.

## Open Threats

None. All 26 threats CLOSED.

## Verification Summary

- 14 `mitigate` threats: 14 CLOSED (patterns located in committed code)
- 12 `accept` threats: 12 CLOSED (rationales internally consistent with observed implementation)
- 0 MEDIUM/HIGH threats open → phase clears `block_on: MEDIUM_OR_HIGH` gate
