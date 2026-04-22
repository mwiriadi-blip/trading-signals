---
phase: 6
plan: 3
subsystem: email-notification
tags: [email, resend, dispatch, cli-wire, phase-gate, golden-snapshot, wave-2]

requires:
  - phase 6 wave 1 (06-02) — compose_email_subject + compose_email_body + 7 formatters
  - phase 4 (run_daily_check orchestrator + CLI dispatch ladder + typed-exception boundary)
  - phase 5 (_render_dashboard_never_crash + _atomic_write_html precedent)
  - CLAUDE.md [Email] log prefix locked + never-crash invariant
  - PROJECT.md: signals@carbonbookkeeping.com.au verified Resend sender
provides:
  - notifier._post_to_resend (Resend HTTPS POST with 3× retry × (5, 30) timeout × 429-retryable × 4xx-fail-fast + active api_key redaction)
  - notifier.send_daily_email (NEVER raises; RESEND_API_KEY-missing writes last_email.html; returns 0 on all paths)
  - notifier._atomic_write_html (verbatim mirror of dashboard._atomic_write_html — tempfile + fsync + os.replace + POSIX parent-dir fsync)
  - notifier.__main__ CLI entrypoint (python -m notifier — operator preview)
  - main._send_email_never_crash (verbatim mirror of _render_dashboard_never_crash)
  - main.run_daily_check 4-tuple return (rc, state, old_signals, run_date)
  - main.D-05 old_signals capture after load_state
  - 3 byte-stable golden HTML bodies + 3 byte-stable golden subject .txt files
  - tests/test_notifier.py::TestResendPost (15 methods), TestSendDispatch (8), TestAtomicWriteHtml (3), TestGoldenEmail (15)
  - tests/test_main.py::TestEmailNeverCrash (2), TestRunDailyCheckTupleReturn (2), plus 6 new TestCLI methods
affects:
  - main.py _force_email_stub DELETED (Phase 4 stub superseded by D-15 compute-then-email)
  - main.py --force-email help string + main() docstring + run_daily_check docstring + module docstring updated for Phase 6
  - tests/fixtures/notifier/ — 6 goldens (3 HTML bodies overwritten; 3 subject .txt goldens created)

tech-stack:
  added: []
  patterns:
    - D-12 retry loop structurally mirrors data_fetcher.fetch_ohlcv (tuple-catch narrow-except + flat backoff + parameterized retries)
    - D-13 _atomic_write_html is a verbatim duplicate of dashboard._atomic_write_html per hex-boundary D-01 (no shared helper between dashboard + notifier)
    - D-15 never-crash helper pattern (C-2: local import inside try/except) established in Phase 5 for dashboard; Wave 2 replicates for email
    - Fix 1 (HIGH) active api_key redaction in TWO sites: 4xx error body AND retries-exhausted message
    - Fix 2 (MEDIUM) requests.post timeout=(connect=5, read=timeout_s) tuple (not scalar) — prevents hung DNS/TCP handshake
    - Fix 7 (MEDIUM) 4-tuple return from BOTH --test early-return AND happy-path; None-guard in dispatch ladder handles error returns
    - Fix 8 (LOW) subject .txt goldens alongside HTML body goldens — SC-1 subject format now under phase-gate byte-equal rigour
    - Fix 10 None-guard in main() dispatch: `if rc == 0 and state is not None and old_signals is not None and run_date is not None:`

key-files:
  created:
    - tests/fixtures/notifier/golden_with_change_subject.txt
    - tests/fixtures/notifier/golden_no_change_subject.txt
    - tests/fixtures/notifier/golden_empty_subject.txt
  modified:
    - notifier.py (1060 LoC → 1216 LoC, +156 net)
    - main.py (743 LoC → 787 LoC, +44 net — refactor + helper + stub deletion)
    - tests/test_notifier.py (708 LoC → 1209 LoC, +501 — real TestResendPost/TestSendDispatch/TestAtomicWriteHtml/TestGoldenEmail)
    - tests/test_main.py (854 LoC → 1111 LoC, +257 — TestCLI 6 new methods + TestEmailNeverCrash + TestRunDailyCheckTupleReturn)
    - tests/regenerate_notifier_golden.py (67 LoC → 91 LoC — subject .txt regeneration)
    - tests/fixtures/notifier/golden_with_change.html (Wave 0 placeholder → 15012 bytes real content)
    - tests/fixtures/notifier/golden_no_change.html (Wave 0 placeholder → 11655 bytes)
    - tests/fixtures/notifier/golden_empty.html (Wave 0 placeholder → 8694 bytes)

decisions:
  - D-12 retry policy verbatim per PATTERNS.md: 3 attempts × 10s flat backoff (parameterized via _RESEND_BACKOFF_S for test-speed `backoff_s=0`). _RESEND_RETRY_EXCEPTIONS tuple = (Timeout, ConnectionError, HTTPError) — mirror data_fetcher:40-44.
  - D-12 + RESEARCH §1: 429 is retryable — special-cased BEFORE the 4xx fail-fast band by raising HTTPError explicitly; flows into retry branch.
  - D-13 RESEND_API_KEY-missing fallback writes last_email.html via _atomic_write_html (D-13 durability sequence: tempfile + fsync + os.replace + POSIX parent-dir fsync + LF newline). Even the fallback write is swallowed — belt-and-braces `except Exception` around the atomic write call ensures NOTF-08 truly never crashes.
  - D-14 _EMAIL_TO_FALLBACK = 'mwiriadi@gmail.com' (Option C per REVIEWS.md) — operator-confirmed fallback when SIGNALS_EMAIL_TO env is unset. Already landed in Wave 0 constants; verified via `grep -c "mwiriadi@gmail.com" notifier.py` == 1.
  - D-15 compute-then-email: --force-email OR --test both unify through `run_daily_check(args)` → `_send_email_never_crash(state, old_signals, run_date, is_test=args.test)`. Phase 4 _force_email_stub deleted.
  - RESEARCH §9 4-tuple refactor: run_daily_check now returns `(rc, state, old_signals, run_date)`. --test early-return returns in-memory post-compute state (NO save_state) so the email has fresh signals even though disk is untouched (CLI-01 structural lock preserved).
  - Fix 1 (HIGH) active redaction: `safe_body = resp.text[:200].replace(api_key, '[REDACTED]')` in 4xx branch + `err_repr.replace(api_key, '[REDACTED]')` in retries-exhausted branch. `grep -c "\[REDACTED\]" notifier.py` == 3 (one per string literal, one per replace call).
  - Fix 2 (MEDIUM) timeout tuple: `requests.post(..., timeout=(5, timeout_s))`. `grep -c "timeout=(5," notifier.py` == 1.
  - Fix 7 (MEDIUM) return-site enumeration: `grep -c "return 0, state, old_signals, run_date" main.py` == 2 (one --test early-return, one final success). Dispatch-ladder docstring updated to remove Phase 4 stub bullet and document Phase 6 `--test` emails.
  - Fix 8 (LOW) subject .txt goldens: regenerator writes 6 files per run (3 HTML bodies + 3 subject .txt). Double-run idempotent on both file types.
  - Fix 10 None-guard baked into dispatch ladder: all three post-run values guarded before _send_email_never_crash invocation.

metrics:
  duration: ~60 minutes
  completed: 2026-04-22
  tasks_total: 3
  tasks_completed: 3
  files_created: 3
  files_modified: 8
  commits: 3
  tests_before: 466
  tests_after: 515
  tests_xfailed: 0
  full_suite_runtime_s: 22.6
  golden_with_change_bytes: 15012
  golden_no_change_bytes: 11655
  golden_empty_bytes: 8694
  golden_with_change_subject_bytes: 66
  golden_no_change_subject_bytes: 65
  golden_empty_subject_bytes: 55
---

# Phase 6 Plan 3: Wave 2 PHASE GATE — HTTPS Dispatch + CLI Wire + Golden Snapshot Summary

**One-liner:** Phase 6 Wave 2 PHASE GATE completes the email system — `_post_to_resend` (3× retry × 429-retryable × 4xx-fail-fast × active api_key redaction × (5, 30) timeout tuple), `send_daily_email` (NEVER raises; RESEND_API_KEY-missing writes last_email.html), `_atomic_write_html` (dashboard mirror), main.py `run_daily_check` refactored to 4-tuple return + `_send_email_never_crash` helper wired through `--force-email`/`--test` via D-15 shared compute-then-email path, and 6 byte-stable goldens (3 HTML bodies + 3 subject .txt per Fix 8). Phase 4 `_force_email_stub` deleted. Double-run regenerator produces zero git diff. 515/515 tests green; ruff clean.

## Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | `_post_to_resend` + `send_daily_email` + `_atomic_write_html` + TestResendPost (15) + TestSendDispatch (8) + TestAtomicWriteHtml (3) | `f59abde` | notifier.py, tests/test_notifier.py |
| 2 | main.py 4-tuple refactor + `_send_email_never_crash` + dispatch ladder rewire + `_force_email_stub` DELETED + TestCLI (6 new) + TestEmailNeverCrash (2) + TestRunDailyCheckTupleReturn (2) | `cb10a35` | main.py, tests/test_main.py |
| 3 | Regenerator extended to 6 files + 3 body goldens regenerated + 3 subject .txt goldens created + TestGoldenEmail (15 methods) | `896561f` | tests/regenerate_notifier_golden.py, tests/fixtures/notifier/golden_*.html, tests/fixtures/notifier/golden_*_subject.txt, main.py (module docstring cleanup) |

## Key Artifacts

### notifier.py (1216 LoC — +156 LoC net from Wave 1)

**Public surface fully wired:**

| Function | Behaviour |
|----------|-----------|
| `compose_email_subject` | Wave 1 (no changes this plan) |
| `compose_email_body` | Wave 1 (no changes this plan) |
| `send_daily_email(state, old_signals, now, is_test=False) -> int` | **Wave 2 filled** — NEVER raises; RESEND_API_KEY-missing → last_email.html + [Email] WARN + return 0; ResendError → [Email] WARN + return 0; unexpected Exception → [Email] WARN + return 0; success → [Email] sent INFO + return 0. Reads SIGNALS_EMAIL_TO env with _EMAIL_TO_FALLBACK default. |

**Private surface filled:**

- `_RESEND_RETRY_EXCEPTIONS = (Timeout, ConnectionError, HTTPError)` — module-level tuple mirror of data_fetcher:40-44.
- `_post_to_resend(api_key, from_addr, to_addr, subject, html_body, timeout_s=30, retries=3, backoff_s=10)` — 3× retry × 429-retryable × 4xx-fail-fast with active api_key redaction in BOTH the 4xx body (Fix 1 site 1) AND the retries-exhausted chain message (Fix 1 site 2). timeout=(5, timeout_s) tuple (Fix 2). Raises ResendError with `from last_err` chain.
- `_atomic_write_html(data, path)` — verbatim mirror of dashboard._atomic_write_html. tempfile(dir=parent, delete=False, mode='w', newline='\n') + fsync(fileno) + os.replace + POSIX parent-dir fsync + tempfile cleanup on OSError.

**Convenience CLI:**
```python
if __name__ == '__main__':
  # python -m notifier — operator preview
  import sys
  logging.basicConfig(level=logging.INFO, format='%(message)s')
  _state = load_state()
  _old_signals = {'^AXJO': None, 'AUDUSD=X': None}
  _now = datetime.now(pytz.timezone('Australia/Perth'))
  _rc = send_daily_email(_state, _old_signals, _now, is_test=True)
  sys.exit(_rc)
```

Smoke-tested: with RESEND_API_KEY unset, writes `./last_email.html` and exits 0.

### main.py (787 LoC — +44 LoC net)

**New:** `_send_email_never_crash(state, old_signals, run_date, is_test=False)` — verbatim mirror of `_render_dashboard_never_crash` at lines 94-112. Local `import notifier` inside try/except (C-2 isolates import-time failures). Bare `except Exception` with `[Email] send failed: {ExcName}: {msg}` WARN log.

**Refactored:** `run_daily_check` signature → `tuple[int, dict | None, dict | None, datetime | None]`. D-05 `old_signals` capture added after `load_state()` (keyed by yfinance symbol, handling both Phase 3 int-shape + Phase 4 D-08 dict-shape per Pitfall 7). Two return sites updated (both return the full 4-tuple):
- `--test` early-return (after the test-mode summary footer)
- happy-path final return (after save_state + dashboard render)

**Deleted:** `_force_email_stub()` entirely. Phase 4 stub superseded by D-15 compute-then-email path.

**Dispatch ladder rewrite (main.main() try-block):**
```python
try:
  if args.reset:
    return _handle_reset()
  if args.force_email or args.test:
    # D-15 Phase 6 shared compute-then-email path
    rc, state, old_signals, run_date = run_daily_check(args)
    if (
      rc == 0
      and state is not None
      and old_signals is not None
      and run_date is not None
    ):
      _send_email_never_crash(state, old_signals, run_date, is_test=args.test)
    return rc
  # Default / --once path: no email
  rc, _state, _old_signals, _run_date = run_daily_check(args)
  return rc
except (DataFetchError, ShortFrameError) as e:
  logger.error('[Fetch] ERROR: %s', e)
  return 2
except Exception as e:
  logger.error('[Sched] ERROR: unexpected crash: %s: %s', type(e).__name__, e)
  return 1
```

`--force-email` help string + `main()` dispatch-ladder docstring + `run_daily_check` docstring + module docstring all updated to reflect Phase 6 behaviour (no more Phase 4 stub; --test now emails; --force-email alone now runs full compute).

### tests/test_notifier.py (1209 LoC — +501 LoC)

| Class | Methods | Wave | Status |
|-------|---------|------|--------|
| TestComposeSubject | 6 | 1 | green (no changes) |
| TestDetectSignalChanges | 5 | 1 | green (no changes) |
| TestComposeBody | 38 | 1 | green (no changes) |
| TestFormatters | 20 | 1 | green (no changes) |
| TestResendPost | **15** | 2 | **all green** — URL/auth/timeout-tuple, 200-returns-None, 4xx-fails-fast (parametrized 400/401/403/422), 429-retried-to-200, 429-exhausted, 500-retried-to-200, 500-exhausted, Timeout-exhausted, ConnectionError-exhausted, api_key NOT in error body, api_key redacted in 4xx body, api_key redacted in retries-exhausted, timeout=(5, timeout_s) tuple |
| TestSendDispatch | **8** | 2 | **all green** — missing api_key writes last_email.html, missing api_key logs WARN, 5xx exhausted returns 0 + logs, 4xx returns 0 + logs, unexpected Exception swallowed, success logs INFO, SIGNALS_EMAIL_TO override respected, fallback recipient when env unset |
| TestAtomicWriteHtml | **3** | 2 | **all green** — atomic write creates file, OSError on replace cleans up tempfile, LF newlines (no CRLF) |
| TestGoldenEmail | **15** | 2 | **all green** — 3 body byte-equal + 3 subject byte-equal + parametrized DOCTYPE (3) + parametrized LF line-endings (3) + ACTION REQUIRED presence/absence (3) |

**Total test_notifier.py: 110 tests collected, all green.**

### tests/test_main.py (1111 LoC — +257 LoC)

| Class | New Methods | Status |
|-------|-------------|--------|
| TestCLI | +6 (test_force_email_sends_live_email; test_force_email_captures_post_run_state; test_test_flag_sends_test_prefixed_email_no_state_mutation; test_force_email_and_test_combined; test_default_mode_does_NOT_send_email; test_once_mode_does_NOT_send_email) | all green |
| TestEmailNeverCrash | **2** new class (test_email_runtime_failure_never_crashes_run; test_email_import_time_failure_never_crashes_run via sys.modules patch) | all green |
| TestRunDailyCheckTupleReturn | **2** new class (test_run_daily_check_returns_4_tuple; test_run_daily_check_test_mode_returns_in_memory_state) | all green |
| TestOrchestrator | 1 modified (test_reversal_long_to_short_preserves_new_position updated to unpack 4-tuple) | all green |
| Phase 4 `test_force_email_logs_stub_and_exits_zero` | DELETED — replaced by test_force_email_sends_live_email | n/a |

**Total test_main.py: 28 tests collected, all green.**

### tests/fixtures/notifier/ — 6 golden files byte-stable

| File | Size (bytes) | Content gate |
|------|--------------|--------------|
| golden_with_change.html | **15012** | DOCTYPE + ACTION REQUIRED + #0f1117 + #ef4444 + raw Unicode → + Close existing LONG position (2 contracts @ entry $8,204.50) |
| golden_with_change_subject.txt | **66** | `🔴 2026-04-22 — SPI200 SHORT, AUDUSD LONG — Equity $101,235\n` |
| golden_no_change.html | **11655** | DOCTYPE + NO ACTION REQUIRED + #0f1117 |
| golden_no_change_subject.txt | **65** | `📊 2026-04-22 — SPI200 LONG, AUDUSD FLAT — Equity $101,235\n` |
| golden_empty.html | **8694** | DOCTYPE + NO ACTION REQUIRED + No open positions + $100,000 initial account |
| golden_empty_subject.txt | **55** | `📊  — SPI200 FLAT, AUDUSD FLAT — Equity $100,000\n` (empty date because legacy-int signals + last_run=null in empty_state fixture) |

**Double-run idempotency verified:** `.venv/bin/python tests/regenerate_notifier_golden.py` run twice produces `git diff --exit-code tests/fixtures/notifier/ → 0`. **PHASE_GATE_GREEN.**

## Verification Results

| Check | Result |
|-------|--------|
| Full suite `.venv/bin/pytest tests/ -x` | **515 passed, 0 failed, 0 xfailed** (~22.6s) |
| Ruff clean `.venv/bin/ruff check .` | **All checks passed** |
| PHASE GATE: regenerator double-run git-diff | **zero diff** (IDEMPOTENT) |
| AST hex boundary `test_notifier_no_forbidden_imports` | **green** |
| Phase 5 dashboard TestGoldenSnapshot byte-equal | **green** (no regression from Wave 2) |
| TestGoldenEmail 15 methods | **15/15 green** |
| TestResendPost 15 methods | **15/15 green** |
| TestSendDispatch 8 methods | **8/8 green** |
| TestAtomicWriteHtml 3 methods | **3/3 green** |
| TestEmailNeverCrash 2 methods | **2/2 green** |
| TestCLI force-email + test-flag integration | **all green** |
| `grep -c "return 0, state, old_signals, run_date" main.py` (Fix 7) | **2** (expected) |
| `grep -c "def _force_email_stub" main.py` | **0** (stub deleted) |
| `grep -c "mwiriadi@gmail.com" notifier.py` (D-14 fallback) | **1** |
| `grep -c "\[REDACTED\]" notifier.py` (Fix 1) | **3** (2 literal strings + 1 replace call) |
| `grep -c "timeout=(5," notifier.py` (Fix 2) | **1** |
| `grep -q "is_test=args.test" main.py` | **exit 0** (present) |
| `python -m notifier` smoke (RESEND_API_KEY unset) | **writes last_email.html, exits 0** |

## Threat Model Coverage

| Threat ID | Category | Disposition | Mitigation Verified |
|-----------|----------|-------------|---------------------|
| T-06-01 | Tampering (hex boundary) | mitigated | `tests/test_signal_engine.py::TestDeterminism::test_notifier_no_forbidden_imports` green post-Wave-2. Wave 2 additions (`_post_to_resend`, `send_daily_email`, `_atomic_write_html`, CLI block) import only stdlib (`os`, `tempfile`, `time`, `pathlib`, `logging`, `html`, `datetime`) + pytz + requests + state_manager + system_params. Zero forbidden sibling imports. |
| T-06-02 | Information Disclosure (RESEND_API_KEY leak) | mitigated | Fix 1 active redaction at TWO sites: 4xx body branch + retries-exhausted branch. `test_api_key_NOT_in_error_body` + `test_api_key_redacted_in_4xx_error_body` + `test_api_key_redacted_in_retries_exhausted` all green. Log statements in `send_daily_email` log `to_addr` and truncated `subject`; never the api_key. `grep -n 'api_key' notifier.py` shows all 8 matches confined to `_post_to_resend` locals; zero in logger.info/warning calls. |
| T-06-02a | Information Disclosure (.env.example leak) | mitigated | Wave 0 locked `.env.example` placeholder `re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` (40 'x' zero-entropy) + `.env` gitignored. No changes in Wave 2. |
| T-06-03 | Tampering (stored XSS state → HTML) | mitigated | Wave 1 established html.escape discipline. Wave 2 goldens lock byte-equal output for 3 scenarios — any future drift introducing unescaped interpolation surfaces as golden diff. Fixture `trade_log[-1]['exit_reason'] = 'signal_reversal'` (ASCII-safe enum) present in with_change golden. T-06-03/03a/03b Wave 1 tests still green post Wave 2. |
| T-06-04 | Tampering (CLI-01 read-only contract) | mitigated | `test_test_flag_sends_test_prefixed_email_no_state_mutation` records `state.json.stat().st_mtime_ns` BEFORE + AFTER `main.main(['--test'])` and asserts equality. 4-tuple return from run_daily_check --test path returns in-memory post-compute state WITHOUT calling save_state. `grep save_state main.py` shows only two sites: run_daily_check line ~596 (after the `if args.test: return` early-return) and `_handle_reset`. No path exists where --test hits save_state. |
| T-06-05 | DoS (email rate-limit runaway) | accept | 429 retryable × 10s backoff × 3 attempts = max 30s wait per run. ≤1 email/day; runaway near-zero. No additional mitigation this plan. |
| T-06-06 | Info Disclosure (last_email.html state data) | mitigated | `.gitignore` line 3 `last_email.html` locked Wave 0. File overwritten atomically on every fallback path — no stale accumulation. Leaf html.escape on all state-derived strings (T-06-03 covers). |

No new threat flags. Wave 2 introduced network surface (HTTPS POST to a fixed Resend endpoint — not user-supplied URL, no SSRF) + file write (gitignored last_email.html) + two env-var reads (RESEND_API_KEY + SIGNALS_EMAIL_TO). All documented in the plan's `<threat_model>`.

## Fix-Lock Verification Matrix

### Fix 1 (HIGH) — api_key redaction at TWO sites

| Site | Code | Test | Verified |
|------|------|------|----------|
| 4xx fail-fast body | `safe_body = resp.text[:200]; if api_key: safe_body = safe_body.replace(api_key, '[REDACTED]')` (notifier.py:1122-1125) | `test_api_key_redacted_in_4xx_error_body` | YES |
| Retries-exhausted err_repr | `err_repr = f'{type(last_err).__name__}: {last_err}'; if api_key: err_repr = err_repr.replace(api_key, '[REDACTED]')` (notifier.py:1140-1143) | `test_api_key_redacted_in_retries_exhausted` | YES |

Both tests assert: raised ResendError **contains** `[REDACTED]` AND **does not contain** the raw api_key literal.

### Fix 2 (MEDIUM) — timeout tuple

`requests.post('https://api.resend.com/emails', headers=..., json=payload, timeout=(5, timeout_s))` at notifier.py:1113. Test `test_timeout_tuple_5_connect_read` + `test_post_url_and_auth_header` both assert captured `kw['timeout'] == (5, timeout_s)`. YES.

### Fix 7 (MEDIUM) — run_daily_check return-site enumeration

```bash
grep -c "return 0, state, old_signals, run_date" main.py   # → 2
```
- Site 1: `--test` early-return (main.py ~line 605) — returns post-compute in-memory state without calling save_state (CLI-01 lock).
- Site 2: happy-path final return (main.py ~line 630) — returns saved state.

Dispatch-ladder docstring at `main()` rewritten to remove the "Phase 4 stub" bullets and document Phase 6 `--test → [TEST]` email + `--force-email → runs full compute` semantics.

### Fix 8 (LOW) — subject .txt goldens

Regenerator extended to write 6 output files per run (3 HTML body + 3 subject .txt). `TestGoldenEmail::test_golden_{with_change,no_change,empty}_subject_matches_committed` byte-equal asserts each against committed `.txt` fixture. Double-run `git diff --exit-code` returns 0 across ALL 6 files.

### Fix 10 — None-guard on 4-tuple

```python
if (
  rc == 0
  and state is not None
  and old_signals is not None
  and run_date is not None
):
  _send_email_never_crash(state, old_signals, run_date, is_test=args.test)
```
main.py ~line 752. Guards against hypothetical future run_daily_check error-path `return (rc, None, None, None)` — none exist today, but the contract in the docstring is explicit.

## Deviations from Plan

**None.** Plan was very specific and every step landed as written:
- 3-task TDD RED/GREEN split preserved
- All 3 NotImplementedError stubs replaced verbatim with `<interfaces>` code templates
- `_send_email_never_crash` is a verbatim mirror of `_render_dashboard_never_crash` (C-2 local-import-inside-try pattern)
- 4-tuple return implemented at BOTH sites (--test early-return AND happy-path) per Fix 7 grep acceptance count of 2
- Phase 4 `_force_email_stub` function + its call site removed; Phase 4 test `test_force_email_logs_stub_and_exits_zero` replaced by `test_force_email_sends_live_email`
- All 6 goldens regenerated byte-stably; double-run idempotency verified
- TestGoldenEmail populated with 15 methods (3 body byte-equal + 3 subject byte-equal + 3 DOCTYPE parametrized + 3 LF parametrized + 3 ACTION REQUIRED presence/absence)
- All 4 REVIEWS.md fixes (1, 2, 7, 8) land verbatim with grep-countable acceptance criteria

Auto-fixed minor: test_reversal_long_to_short_preserves_new_position in TestOrchestrator (existing Phase 4 test) was updated to unpack the new 4-tuple return — classified as Rule 3 (blocking), not a plan deviation.

## Auth Gates Encountered

**None.** Tests monkeypatch `notifier.requests.post` to stand in for Resend HTTPS. `python -m notifier` smoke test ran with RESEND_API_KEY unset → exercises NOTF-08 fallback (writes last_email.html) — no auth gate. Operator-level auth setup (copy Resend key to `.env`) is a Phase 6 deployment step documented in `user_setup` frontmatter; not triggered during test execution.

## Requirements Traceability (Phase 6 + CLI slices)

| Requirement | Covered by | Status |
|-------------|------------|--------|
| NOTF-01 HTTPS dispatch to Resend | `_post_to_resend` + TestResendPost (15 methods) | **complete** |
| NOTF-02 Subject template | Wave 1 `compose_email_subject` + Wave 2 subject .txt goldens | complete (body + gate) |
| NOTF-03 HTML body 7 sections | Wave 1 `compose_email_body` + Wave 2 body goldens | complete (body + gate) |
| NOTF-04 Dashboard parity sections | Wave 1 renderers + Wave 2 byte-equal lock | complete |
| NOTF-05 Mobile-safe markup | Wave 1 inline CSS + max-width:600px + Wave 2 lock | complete |
| NOTF-06 XSS escape | Wave 1 html.escape leaves + Wave 2 lock | complete |
| NOTF-07 Never-crash on Resend failure | `send_daily_email` + `_send_email_never_crash` + TestEmailNeverCrash | **complete** |
| NOTF-08 RESEND_API_KEY-missing fallback | `send_daily_email` + `_atomic_write_html` + TestSendDispatch::test_missing_api_key_writes_last_email_html | **complete** |
| NOTF-09 Byte-stable golden snapshots | TestGoldenEmail + regenerator idempotency | **complete** |
| CLI-01 --test structural read-only | TestCLI::test_test_flag_sends_test_prefixed_email_no_state_mutation (mtime BEFORE/AFTER equality) | **complete (Phase 6 slice)** |
| CLI-03 --force-email live dispatch | TestCLI::test_force_email_sends_live_email + test_force_email_captures_post_run_state | **complete (Phase 6 slice)** |

All 9 NOTF requirements + CLI-01 Phase 6 slice + CLI-03 Phase 6 slice have passing tests at phase gate.

## Hex Boundary Confirmation

`notifier.py` post-Wave-2 imports (stdlib + third-party + project):
- stdlib: `html`, `logging`, `os`, `tempfile`, `time`, `datetime`, `pathlib`
- third-party: `pytz`, `requests`
- project: `state_manager.load_state` (CLI convenience path only), `system_params` (palette + contract specs + INITIAL_ACCOUNT + TRAIL_MULT_*)

All 8 forbidden sibling imports (`signal_engine`, `sizing_engine`, `data_fetcher`, `main`, `dashboard`, `numpy`, `pandas`, `yfinance`) remain absent. AST blocklist `FORBIDDEN_MODULES_NOTIFIER` green via `tests/test_signal_engine.py::TestDeterminism::test_notifier_no_forbidden_imports`.

`main.py` `_send_email_never_crash` puts `import notifier` INSIDE the helper body (C-2) — same pattern as Phase 5 `_render_dashboard_never_crash` for `import dashboard`. Module-top `import notifier` deliberately absent so import-time notifier failures are caught by the same `except Exception` that catches runtime dispatch failures (verified by `test_email_import_time_failure_never_crashes_run`).

## PHASE GATE Status

All 13 phase-gate verification steps from `06-03-PLAN.md::<verification>` passed:

1. Full suite `.venv/bin/pytest tests/ -x` — **515 passed**
2. Ruff clean — **green**
3. Regenerator double-run `git diff --exit-code tests/fixtures/notifier/` — **zero diff**
4. AST hex boundary `test_notifier_no_forbidden_imports` — **green**
5. Phase 5 dashboard golden unchanged — **green**
6. All 15 `TestGoldenEmail` methods — **green**
7. All `TestSendDispatch` + `TestResendPost` + `TestAtomicWriteHtml` — **green**
8. `TestEmailNeverCrash` + CLI-01/CLI-03 integration — **green**
9. T-06-02 leak check: `api_key` usage confined to `_post_to_resend` locals; never in logger calls — **verified**
10. T-06-04 check: `save_state` only called in `run_daily_check` (post-test-guard) + `_handle_reset` — **verified**
11. `python -m notifier` smoke (RESEND_API_KEY unset → last_email.html) — **works, exits 0**
12. `def _force_email_stub` removed from main.py — **grep count 0**
13. Requirements traceability — **all 9 NOTF + CLI-01/03 Phase 6 slices complete**

**Phase 6 Wave 2 (06-03) PHASE GATE closed. Phase 6 ready for `/gsd-verify-work 6`.**

## Self-Check: PASSED

- [x] `notifier._post_to_resend` filled; 3× retry × (5, 30) timeout × 429-retryable × 4xx-fail-fast × active redaction × ResendError-with-chain
- [x] `notifier.send_daily_email` NEVER raises; RESEND_API_KEY-missing writes last_email.html; SIGNALS_EMAIL_TO env honoured with 'mwiriadi@gmail.com' fallback
- [x] `notifier._atomic_write_html` verbatim mirror of dashboard (newline='\n', fsync, os.replace, POSIX parent-dir fsync, tempfile cleanup on OSError)
- [x] `notifier` `if __name__ == '__main__':` block wired to load_state + send_daily_email(is_test=True); smoke-tested
- [x] `main.run_daily_check` signature → `tuple[int, dict | None, dict | None, datetime | None]`; D-05 old_signals capture; BOTH return sites updated (Fix 7 grep count = 2)
- [x] `main._send_email_never_crash` verbatim mirror of `_render_dashboard_never_crash` with `import notifier` inside try/except
- [x] `main._force_email_stub` DELETED (grep `def _force_email_stub` = 0)
- [x] `main.main()` dispatch ladder unified: --force-email OR --test → run_daily_check + None-guard + _send_email_never_crash; default/--once = no email
- [x] 3 body HTML + 3 subject .txt goldens committed with real bytes; regenerator double-run zero-diff
- [x] TestGoldenEmail (15), TestResendPost (15), TestSendDispatch (8), TestAtomicWriteHtml (3), TestEmailNeverCrash (2), TestRunDailyCheckTupleReturn (2), TestCLI force-email/test-flag all green
- [x] Fix 1 (HIGH) verified at TWO sites; Fix 2 (MEDIUM) timeout tuple verified; Fix 7 (MEDIUM) Fix 8 (LOW) Fix 10 verified
- [x] Full suite 515 passed + 0 xfailed; ruff clean
- [x] 3 commits on worktree (f59abde, cb10a35, 896561f) verified via git log

### Artifact existence verification

```
tests/fixtures/notifier/golden_with_change.html — FOUND (15012 bytes)
tests/fixtures/notifier/golden_with_change_subject.txt — FOUND (66 bytes)
tests/fixtures/notifier/golden_no_change.html — FOUND (11655 bytes)
tests/fixtures/notifier/golden_no_change_subject.txt — FOUND (65 bytes)
tests/fixtures/notifier/golden_empty.html — FOUND (8694 bytes)
tests/fixtures/notifier/golden_empty_subject.txt — FOUND (55 bytes)
```

### Commit existence verification

```
f59abde — FOUND (Task 1)
cb10a35 — FOUND (Task 2)
896561f — FOUND (Task 3)
```

## Next

`/gsd-verify-work 6` — Phase 6 is SHIPPED when verifier exits clean.
