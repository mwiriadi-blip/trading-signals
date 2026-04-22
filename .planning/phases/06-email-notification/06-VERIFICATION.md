---
phase: 06-email-notification
verified_at: 2026-04-22T00:00:00Z
status: human_needed
pass_rate: 16/16 automated must-haves verified
score: 6/7 success criteria automated (SC-1 live Resend delivery requires human operator)
overrides_applied: 0
re_verification: null

must_haves_summary:
  truths_verified: 16
  truths_failed: 0
  artifacts_verified: 18
  artifacts_missing: 0
  key_links_verified: 6
  key_links_failed: 0

human_verification:
  - test: "Send a live Resend email via `python -m notifier`"
    expected: "Email arrives in the operator inbox (default mwiriadi@gmail.com; override via SIGNALS_EMAIL_TO). Subject rendered as `[TEST] 📊 YYYY-MM-DD — SPI200 SIG, AUDUSD SIG — Equity $X,XXX`. HTML body renders with dark #0f1117 background, 7-section layout, no broken images/links, footer disclaimer visible."
    why_human: "SC-1 requires verifying a live POST https://api.resend.com/emails with a real Bearer token actually delivers an email. This cannot be verified programmatically without hitting Resend's production API. Automated tests monkeypatch `notifier.requests.post` to simulate 200/4xx/429/500 responses — they prove the HTTPS client-side contract (URL, auth header, timeout tuple, retry policy, redaction) but not server-side delivery."
    setup: "Export RESEND_API_KEY=re_xxx (from Resend Dashboard → API Keys); optionally export SIGNALS_EMAIL_TO=<recipient>. Then run: `RESEND_API_KEY=re_... .venv/bin/python -m notifier` OR `RESEND_API_KEY=re_... .venv/bin/python main.py --test`."
  - test: "Inspect rendered email in Gmail web + Gmail iOS Mail app at 375px viewport"
    expected: "No horizontal scroll at 375px; all 7 D-10 sections visible in order (header → [ACTION REQUIRED if signal changed] → Signal Status → Open Positions → Today's P&L → Last 5 Closed Trades → Footer); palette colors render correctly; emoji (🔴/📊) appears in subject preview pane."
    why_human: "SC-2 mobile-responsive rendering requires visual confirmation in real email clients. Automated tests verify `max-width:600px` + `<meta viewport>` + inline-CSS + `bgcolor=\"#0f1117\"` are present in the HTML source, but mail-client CSS sanitizers (Gmail strips some attributes) can break rendering in ways only visible on the device."
    setup: "After the live delivery above, open the inbox on an iPhone (or use Chrome DevTools → device mode → iPhone SE 375px) and verify layout."
  - test: "Confirm 🔴 emoji appears in subject when any signal has changed vs last run"
    expected: "When state['signals'][sk]['signal'] differs from old_signals[yf_sym] for any instrument, the subject emoji is 🔴 and an ACTION REQUIRED block appears at top of body with red left border. When all signals match (or first run), emoji is 📊 and no ACTION REQUIRED block appears."
    why_human: "SC-3 requires observing both the changed-signal and no-change paths in a live email. TestGoldenEmail locks byte-equal output for both scenarios (golden_with_change.html = 15012 bytes with ACTION REQUIRED; golden_no_change.html = 11655 bytes without), but visual confirmation of the emoji prefix in a real mail client inbox list is the operator's responsibility."
    setup: "Two test runs: (1) run with a state where old_signals differs (e.g., after a SPI200 LONG→SHORT reversal) — expect 🔴 subject + ACTION REQUIRED block; (2) run with a state where signals are unchanged — expect 📊 subject + no ACTION REQUIRED block."
---

# Phase 6: Email Notification Verification Report

**Phase Goal (from ROADMAP.md):** Send a daily Resend email with signal status, positions, P&L, and an ACTION REQUIRED block when any signal has changed — mobile-responsive, inline-CSS, escaped values, and graceful degradation when Resend is unavailable. Also replaces the Phase 4 `--test` and `--force-email` log-line stubs with real Resend dispatch.

**Verified:** 2026-04-22
**Status:** human_needed (all 16 automated must-haves verified; SC-1 live Resend delivery is inherently human-gated)
**Re-verification:** No — initial verification

---

## Summary

Phase 6 is goal-achieved in code. All 9 NOTF requirements (NOTF-01..09) are fully implemented across `notifier.py` (1216 LoC), `main.py` (787 LoC, refactored to 4-tuple return + `_send_email_never_crash` helper), and 6 byte-stable goldens (3 HTML bodies + 3 subject .txt). The full test suite is **515/515 green** with zero xfailed, ruff passes clean, the golden regenerator double-run produces zero git diff (PHASE GATE), and the hex-boundary AST blocklist confirms `notifier.py` has no forbidden sibling imports. All 4 cross-AI review fixes (Fix 1 HIGH api-key redaction at two sites, Fix 2 timeout tuple, Fix 7 4-tuple return at two sites, Fix 8 subject .txt goldens) and Fix 10 (None-guard) land verbatim with grep-countable evidence. The only blocker to full pass is SC-1, which requires the operator to perform a live Resend POST against production to confirm end-to-end delivery — that's a human-gated check by definition (cannot be verified without sending an actual email).

---

## Automated Verification Results

| Check                                                          | Command                                                              | Result                          | Status |
| -------------------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------- | ------ |
| Full pytest suite                                              | `.venv/bin/pytest tests/ -q`                                         | **515 passed in 22.80s**        | PASS   |
| Ruff clean                                                     | `.venv/bin/ruff check .`                                             | **All checks passed!**          | PASS   |
| PHASE GATE: regenerator idempotent                             | `.venv/bin/python tests/regenerate_notifier_golden.py && git diff --exit-code tests/fixtures/notifier/` | **Zero diff (exit 0)**          | PASS   |
| Hex boundary (forbidden imports absent)                        | `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -v` | 3/3 green (notifier, sizing, signal_engine) | PASS   |
| Phase 5 dashboard regression guard                             | `.venv/bin/pytest tests/test_dashboard.py -q`                        | **70 passed in 0.22s**          | PASS   |
| Notifier test classes                                          | `.venv/bin/pytest tests/test_notifier.py -q`                         | **111 passed in 20.12s**        | PASS   |
| TestGoldenEmail (byte-equal lock)                              | `.venv/bin/pytest tests/test_notifier.py::TestGoldenEmail -v`        | **15/15 green**                 | PASS   |
| TestResendPost + TestSendDispatch + TestAtomicWriteHtml        | 3 classes combined                                                   | **27/27 green**                 | PASS   |
| CLI-01 `--test` mtime immutability                             | `.venv/bin/pytest 'tests/test_main.py::TestCLI::test_test_flag_sends_test_prefixed_email_no_state_mutation' -v` | PASS in 0.33s                   | PASS   |
| TestEmailNeverCrash                                            | `.venv/bin/pytest 'tests/test_main.py::TestEmailNeverCrash' -v`      | **2/2 green** (runtime + import-time) | PASS   |

### Grep Acceptance Criteria (CONTEXT + REVIEWS.md Fix-Locks)

| Check                                                          | Expected                                   | Actual                              | Status |
| -------------------------------------------------------------- | ------------------------------------------ | ----------------------------------- | ------ |
| `grep -n 'REDACTED' notifier.py` (Fix 1 at 2 sites)            | ≥2 call sites                              | **3 matches** (1 doc + L1125 + L1143) | PASS   |
| `grep -n 'timeout=(5' notifier.py` (Fix 2)                     | ≥1 match                                   | **1 match** at L1114                | PASS   |
| `grep -c 'return 0, state, old_signals, run_date' main.py` (Fix 7) | exactly 2                              | **2** (L647 --test early-return, L672 happy path) | PASS   |
| None-guard multi-line (Fix 10)                                 | present in main.py                         | **present at L765-770**             | PASS   |
| `grep -c 'def _force_email_stub' main.py` (Phase 4 stub deleted) | 0                                        | **0**                               | PASS   |
| `grep -c 'mwiriadi@gmail.com' notifier.py` (D-14 fallback)     | 1                                          | **1** at L87                        | PASS   |
| `grep -c '&rarr;'` in rendered HTML goldens                    | 0 in each                                  | **0** in all 3 bodies (raw Unicode → only) | PASS   |
| `grep -c 'html.escape(' notifier.py`                           | ≥10 leaf escape sites                      | **55 sites**                        | PASS   |
| `grep -n 'https://api.resend.com/emails' notifier.py`          | present                                    | **present at L1111**                | PASS   |
| `grep -n \"'Authorization': f'Bearer\" notifier.py`            | present                                    | **present at L1104**                | PASS   |
| Subject golden .txt files exist                                | 3 files                                    | **3 files** (55, 65, 66 bytes)      | PASS   |

---

## Must-Haves Check

| # | Must-Have                                                                                                 | Evidence                                                                                                                                              | Status  |
| - | --------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| 1 | `notifier.py` hex module exists with 3 public + 3 private functions, all filled (no NotImplementedError)  | `notifier.py` 1216 LoC; `compose_email_subject`, `compose_email_body`, `send_daily_email`, `_post_to_resend`, `_atomic_write_html`, `_detect_signal_changes` all filled | PASS    |
| 2 | Palette constants shared in `system_params.py`, consumed by both dashboard and notifier                   | 9 `_COLOR_*` names at `system_params.py`; `dashboard.py` + `notifier.py` both import; Phase 5 dashboard golden byte-equal (70 tests green)            | PASS    |
| 3 | Hex boundary: notifier forbids signal_engine/sizing_engine/data_fetcher/dashboard/main/numpy/pandas/yfinance | AST blocklist `FORBIDDEN_MODULES_NOTIFIER` in `tests/test_signal_engine.py`; `test_forbidden_imports_absent` 3/3 green                                | PASS    |
| 4 | `compose_email_subject` emoji dispatch (🔴 change / 📊 no-change) + [TEST] prefix before emoji            | `notifier.py:296-344`; TestComposeSubject 6 tests + subject goldens byte-equal (66/65/55 bytes)                                                       | PASS    |
| 5 | `compose_email_body` emits complete HTML doc with 7 D-10 sections + inline CSS only                       | `notifier.py:958+`; TestComposeBody 38 tests; rendered body has DOCTYPE, `<meta viewport>`, `max-width:600px`, `bgcolor="#0f1117"`, no `<style>`, no `@media`, no `class=` | PASS    |
| 6 | ACTION REQUIRED block with `border-left:4px solid #ef4444` only on signal change                          | `_render_action_required_email`; golden_with_change.html contains block; golden_no_change.html + golden_empty.html do NOT; 3 TestGoldenEmail presence/absence tests green | PASS    |
| 7 | Every state-derived string escaped via `html.escape(value, quote=True)` at leaf                           | 55 `html.escape(` call sites in notifier.py; 3 XSS injection tests (exit_reason, instrument, direction) green                                         | PASS    |
| 8 | `_post_to_resend` implements D-12 retry loop: 3× retries × (5, 30) timeout × 429-retryable × 4xx-fail-fast | `notifier.py:1093-1147`; TestResendPost 15 methods (URL/auth/timeout/4xx/429/500/Timeout/ConnectionError all covered)                                 | PASS    |
| 9 | Active api_key redaction at BOTH 4xx body AND retries-exhausted error chain (Fix 1 HIGH)                  | `notifier.py:1125` + `1143`; tests `test_api_key_redacted_in_4xx_error_body` + `test_api_key_redacted_in_retries_exhausted` green                     | PASS    |
| 10 | `send_daily_email` NEVER raises — missing key writes last_email.html + returns 0; ResendError swallowed  | `notifier.py:1149-1198`; try/except on `_atomic_write_html`, `ResendError`, bare `Exception`; TestSendDispatch 8 tests green; TestEmailNeverCrash 2/2 green | PASS    |
| 11 | `_atomic_write_html` mirrors dashboard: tempfile + fsync + os.replace + POSIX parent-dir fsync + LF endings | `notifier.py:1027-1066`; TestAtomicWriteHtml 3 tests (atomic + OSError cleanup + LF-not-CRLF) green                                                    | PASS    |
| 12 | `main.run_daily_check` refactored to 4-tuple return `(rc, state, old_signals, run_date)` at BOTH sites    | `main.py:647` (--test early), `main.py:672` (happy path); `grep -c` == 2; TestRunDailyCheckTupleReturn 2/2 green                                       | PASS    |
| 13 | `main._send_email_never_crash` helper with local `import notifier` (C-2 pattern)                          | `main.py:122-146`; import inside try block; `test_email_import_time_failure_never_crashes_run` via sys.modules patch green                            | PASS    |
| 14 | Phase 4 `_force_email_stub` DELETED; `--force-email` and `--test` wired via shared D-15 compute-then-email path | `grep -c 'def _force_email_stub' main.py` = 0; dispatch ladder at `main.py:755-783` unifies --force-email OR --test → run_daily_check + None-guard + send | PASS    |
| 15 | 3 HTML body + 3 subject .txt byte-stable goldens; regenerator double-run idempotent                       | 15012 / 11655 / 8694 body bytes; 66 / 65 / 55 subject bytes; `git diff --exit-code` = 0 after double-run                                              | PASS    |
| 16 | `python -m notifier` CLI entrypoint — operator preview writes last_email.html when RESEND_API_KEY unset   | `notifier.py:1205-1216`; smoke-tested per 06-03-SUMMARY metrics                                                                                       | PASS    |

**Pass rate: 16/16 must-haves verified.**

---

## Success Criteria Check

| SC  | Criterion                                                                                                             | Evidence                                                                                                                                                                   | Automated | Status         |
| --- | --------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | -------------- |
| SC-1 | Live Resend POST with Bearer token delivers email; subject shows signals + P&L + date + 🔴/📊                         | Client-side contract locked: URL (`notifier.py:1111`), `Authorization: Bearer {api_key}` (L1104), timeout=(5, timeout_s) (L1114), retry loop, redaction — 15 TestResendPost tests green. **Live delivery is operator-only** (no real API key in test env). | **◐ human-needed** | ◐ HUMAN        |
| SC-2 | HTML renders at 375px dark theme (#0f1117), inline CSS only, 7 sections                                              | TestComposeBody 38 tests; rendered body has `<meta viewport>` + `max-width:600px` + `bgcolor="#0f1117"` + inline styles + no `<style>`/`@media`/`class=`; 7 D-10 sections structurally asserted | **✓ automated-verified** + ◐ visual in mail client | ✓ AUTO + ◐ human visual confirm |
| SC-3 | ACTION REQUIRED block with red border appears only when a signal differs from previous run                           | `_render_action_required_email` + `_detect_signal_changes`; TestGoldenEmail presence/absence tests green (golden_with_change has block; no_change + empty do not)          | **✓ automated-verified**  | ✓ AUTO         |
| SC-4 | All user-visible values HTML-escaped; no unescaped `${...}` interpolation                                            | 55 `html.escape(value, quote=True)` call-sites; 3 XSS injection tests (exit_reason, instrument, direction) confirm raw `<script>` / `<img>` absent and escaped form present | **✓ automated-verified**  | ✓ AUTO         |
| SC-5 | Missing RESEND_API_KEY writes last_email.html + console output + exits cleanly; 4xx/5xx logs + does not crash         | `notifier.py:1166-1198`; TestSendDispatch `test_missing_api_key_writes_last_email_html` + `test_4xx_returns_0_and_logs` + `test_unexpected_exception_swallowed` green; TestEmailNeverCrash 2/2 green | **✓ automated-verified**  | ✓ AUTO         |
| SC-6 | `--force-email` dispatch: `main()` replaces Phase 4 stub with `run_daily_check` + `_send_email_never_crash`           | `main.py:755-772`; `grep -c 'def _force_email_stub'` = 0; TestCLI `test_force_email_sends_live_email` + `test_force_email_captures_post_run_state` green                   | **✓ automated-verified**  | ✓ AUTO         |
| SC-7 | `--test` email dispatch: [TEST]-prefixed subject; Phase 4 structural read-only (state.json unchanged) preserved      | `main.py:638-647` + `_send_email_never_crash(is_test=args.test)`; `test_test_flag_sends_test_prefixed_email_no_state_mutation` asserts mtime BEFORE/AFTER equality; subject goldens lock [TEST] ordering | **✓ automated-verified**  | ✓ AUTO         |

**Automated: 6/7. SC-1 is inherently human-gated (requires live Resend POST against production API).**

---

## Requirement Coverage

All 9 NOTF requirements from `REQUIREMENTS.md` lines 100-108 are declared in PLAN frontmatter across the three waves. Every ID is accounted for.

| Req ID    | Source Plan(s)             | Description (verbatim from REQUIREMENTS.md)                                                                                                                                                                         | Implementation                                                                  | Test(s)                                                                          | Status      |
| --------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ----------- |
| NOTF-01   | 06-01, 06-03               | Email sends via Resend HTTPS API (`POST https://api.resend.com/emails`) with Bearer token                                                                                                                          | `notifier.py:1093-1147` (`_post_to_resend`); L1111 URL; L1104 Bearer header     | `TestResendPost` (15 methods) — URL, auth, timeout tuple, 4xx/429/500/Timeout    | ✓ COVERED   |
| NOTF-02   | 06-01, 06-02               | Subject shows signals + P&L + date, prefixed 🔴 on signal change and 📊 when unchanged                                                                                                                             | `notifier.py:283-344` (`compose_email_subject`)                                 | `TestComposeSubject` (6 tests) + 3 `test_golden_*_subject_matches_committed`     | ✓ COVERED   |
| NOTF-03   | 06-01, 06-02               | HTML body uses inline CSS only (dark theme: #0f1117 bg, #22c55e LONG, #ef4444 SHORT, #eab308 FLAT)                                                                                                                 | `notifier.py:958+` inline styles; palette imported from `system_params`         | `TestComposeBody` (38 tests) — inline-CSS/no-`<style>`/no-`@media` structural asserts | ✓ COVERED   |
| NOTF-04   | 06-01, 06-02               | Body sections: header with date/account, signal status table, positions, today's P&L, running equity, last 5 closed trades, footer disclaimer                                                                     | 7 section renderers in `notifier.py:450-952`                                    | `TestComposeBody::test_body_sections_in_d10_order` + 37 other body tests         | ✓ COVERED   |
| NOTF-05   | 06-01, 06-02               | ACTION REQUIRED block (red border) appears when any signal changed from the previous run                                                                                                                           | `_render_action_required_email` + `_detect_signal_changes`; `border-left:4px solid #ef4444` | `TestDetectSignalChanges` (5) + `TestGoldenEmail` presence/absence (3)           | ✓ COVERED   |
| NOTF-06   | 06-01, 06-02               | Email is mobile-responsive (tested width 375px)                                                                                                                                                                    | `max-width:600px` fluid-hybrid + `<meta viewport>`; no breakpoint needed         | `TestComposeBody::test_body_has_meta_viewport` + `test_body_has_max_width_600px` | ✓ COVERED (+ visual confirmation recommended in human check) |
| NOTF-07   | 06-01, 06-03               | Resend API failure logs error and continues — does NOT crash the workflow                                                                                                                                           | `notifier.py:1188-1197` (ResendError + bare Exception catch) + `main.py:122-146` (`_send_email_never_crash`) | `TestSendDispatch::test_5xx_exhausted_returns_0_and_logs` + `TestEmailNeverCrash` 2/2 | ✓ COVERED   |
| NOTF-08   | 06-01, 06-03               | Missing `RESEND_API_KEY` degrades gracefully (writes `last_email.html` + console) — no crash                                                                                                                        | `notifier.py:1167-1182` (key-missing fallback via `_atomic_write_html`)         | `TestSendDispatch::test_missing_api_key_writes_last_email_html` + `test_missing_api_key_logs_warn` | ✓ COVERED   |
| NOTF-09   | 06-01, 06-02, 06-03        | All user-visible values in the HTML are escaped to prevent injection                                                                                                                                                | 55 `html.escape(value, quote=True)` call sites across `notifier.py`             | 3 XSS injection tests (exit_reason + instrument + direction) + TestGoldenEmail byte-equal lock | ✓ COVERED   |

**No orphaned requirements. No missing coverage.**

**CLI-slice completions (Phase 6):**

| CLI Slice            | Description                                                                                                        | Test                                                                                                | Status      |
| -------------------- | ------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- | ----------- |
| CLI-01 (Phase 6)     | `--test` structural read-only preserved; now ALSO sends `[TEST]`-prefixed email                                    | `TestCLI::test_test_flag_sends_test_prefixed_email_no_state_mutation` (mtime BEFORE/AFTER equality) | ✓ COVERED   |
| CLI-03 (Phase 6)     | `--force-email` replaces Phase 4 log-line stub with real Resend dispatch via `run_daily_check` + `_send_email_never_crash` | `TestCLI::test_force_email_sends_live_email` + `test_force_email_captures_post_run_state`           | ✓ COVERED   |

---

## Key Link Verification

| #   | From                        | To                                              | Via                                                   | Status  |
| --- | --------------------------- | ----------------------------------------------- | ----------------------------------------------------- | ------- |
| 1   | `main.run_daily_check`      | `notifier.send_daily_email` (via `_send_email_never_crash`) | 4-tuple return unpacked; None-guard; `import notifier` inside try (`main.py:122-146`) | WIRED   |
| 2   | `main.main()` dispatch ladder | `run_daily_check(args)` + `_send_email_never_crash` | D-15 shared compute-then-email path (`main.py:755-772`) | WIRED   |
| 3   | `notifier.send_daily_email` | `_post_to_resend` (live path)                  | `api_key = os.environ.get('RESEND_API_KEY')`; if present, calls `_post_to_resend` (`notifier.py:1184-1186`) | WIRED   |
| 4   | `notifier.send_daily_email` | `_atomic_write_html` (fallback path)            | RESEND_API_KEY missing → writes `last_email.html` (`notifier.py:1167-1182`) | WIRED   |
| 5   | `notifier._post_to_resend`  | Resend API `POST /emails`                      | `requests.post('https://api.resend.com/emails', headers={'Authorization': f'Bearer {api_key}'}, json=payload, timeout=(5, timeout_s))` (`notifier.py:1102-1115`) | WIRED   |
| 6   | `system_params` palette     | Both `dashboard.py` AND `notifier.py`           | `_COLOR_*` imported from both; Phase 5 dashboard goldens byte-identical post-retrofit | WIRED   |

---

## Anti-Patterns Found

**None at blocker or warning severity.** Stub/placeholder search returns zero hits:

- `grep -E 'TODO|FIXME|XXX|HACK|PLACEHOLDER' notifier.py main.py` → zero matches in active code (only in docstrings explaining "NEVER &rarr;" anti-pattern)
- `return null / return {} / return [] / => {}` patterns: not applicable (Python). Notifier functions all return real data.
- `console.log` only implementations: not applicable.
- `NotImplementedError` stubs: **all 5 filled** (Wave 0 stubs replaced by real code in Waves 1+2).
- `def _force_email_stub` in main.py: 0 matches (Phase 4 stub deleted per D-15).

**Known benign source-only occurrences** (3 matches of `&rarr;` in `notifier.py` — L500, L538, L971) are all inside docstrings/comments **explicitly documenting** the "NEVER &rarr;" anti-pattern (Fix 5). Zero occurrences in rendered HTML goldens (confirmed by `grep -c '&rarr;'` on all three .html goldens returning 0).

---

## Human Verification Required

SC-1 (live Resend delivery), visual mobile rendering for SC-2, and subject-emoji visual inspection for SC-3 are inherently human-gated. They are documented in the `human_verification` frontmatter and summarized here:

### 1. Live Resend POST — operator inbox delivery

- **Test:** Export a real `RESEND_API_KEY` (from Resend Dashboard → API Keys) and run `.venv/bin/python -m notifier` OR `RESEND_API_KEY=re_xxx .venv/bin/python main.py --test`.
- **Expected:** Email arrives in the operator inbox (default `mwiriadi@gmail.com`; override via `SIGNALS_EMAIL_TO=<addr>`). Subject prefixed `[TEST]` when using `--test` (and the `python -m notifier` CLI, which hardcodes `is_test=True`). No errors in log; return code 0.
- **Why human:** Automated tests monkeypatch `requests.post` — they prove the client-side contract (URL, Bearer header, timeout tuple, retries, redaction) but cannot confirm Resend's production API accepts and delivers the payload.

### 2. Mobile rendering at 375px viewport (Gmail web + Gmail iOS)

- **Test:** After the live delivery above, open the email on an iPhone (or Chrome DevTools → device mode → iPhone SE 375px).
- **Expected:** No horizontal scroll; 7 D-10 sections visible in order (header → ACTION REQUIRED if present → Signal Status → Open Positions → Today's P&L → Last 5 Closed Trades → Footer); palette hex values render correctly; emoji (🔴 or 📊) appears in subject preview pane.
- **Why human:** Automated tests verify `max-width:600px` + `<meta viewport>` + inline CSS are present in the HTML source, but mail-client CSS sanitizers (Gmail strips some attributes) can break rendering in ways only visible on the device.

### 3. Signal-change emoji prefix visual inspection

- **Test:** (a) Run once against a state where `old_signals` differs from current (e.g., after a SPI200 LONG→SHORT reversal) — expect 🔴 subject + ACTION REQUIRED block. (b) Run against a state where signals are unchanged — expect 📊 subject + no ACTION REQUIRED block.
- **Expected:** Subject emoji visible in inbox list view (not just in open-email subject line). ACTION REQUIRED block with red left border appears at top of body only when signal changed.
- **Why human:** TestGoldenEmail byte-equals locked both scenarios, but visual confirmation of the emoji rendering in a real mail-client inbox list is the operator's responsibility.

---

## Known Issues

Two non-blocking warnings were flagged by the Phase 6 code review (`06-REVIEW.md`). Both are cosmetic and do **not** affect the phase goal. Carried forward as known debt.

### WR-01: `run_daily_check` docstring overstates failure-return behaviour

- **File/Line:** `main.py:441-443`
- **Category:** Code Quality / Documentation drift
- **Issue:** Docstring claims the function returns `(rc, None, None, None)` on failure paths. In practice, all failure paths propagate exceptions (`DataFetchError`, `ShortFrameError`, `Exception`) that are caught in `main()`'s try/except at L776-783. The function has exactly two `return` statements, both returning fully-populated 4-tuples. The None-guard at `main.py:765-770` is therefore effectively unreachable today (defense-in-depth for future non-exception failure paths).
- **Impact:** None — correctness is unaffected; runtime behavior is correct. Future readers might be misled by the docstring.
- **Fix deferred:** Reword docstring to reflect that exceptions propagate and the None-guard is defense-in-depth.

### WR-02: Empty-state subject golden has cosmetic double-space on first-run

- **File/Line:** `tests/fixtures/notifier/golden_empty_subject.txt:1` (and `notifier.py:311-319` + L340)
- **Category:** Edge case / UX
- **Issue:** `golden_empty_subject.txt` contains `📊  — SPI200 FLAT, AUDUSD FLAT — Equity $100,000` (note double space between emoji and em-dash). Triggered when `empty_state.json` has `last_run: null` and legacy int-shape signals (no `as_of_run`), causing `date_iso` to resolve to empty string. Subject f-string at L340 then emits `f'{emoji} {date_iso} — ...'` = `📊  — ...`.
- **Impact:** Cosmetic; visible only on very first run before state.json has a `last_run` value. Operator-level aesthetic issue; doesn't break delivery, rendering, or any test.
- **Fix deferred:** Either render `first run` as a clearer token when `date_iso` is empty, or accept as a known edge case.

---

## Status Determination

**Status: `human_needed`**

Decision-tree walk-through (Step 9 of the verification process):

1. **Any truth FAILED, artifact MISSING/STUB, key link NOT_WIRED, or blocker anti-pattern?** No — all 16 automated must-haves verified; 6 key links wired; zero stubs remaining; zero blocker anti-patterns.
2. **Did Step 8 produce ANY human verification items?** Yes — 3 items for SC-1 (live Resend POST), SC-2 visual mobile rendering, SC-3 emoji prefix visual confirmation. SC-1 is inherently operator-gated by design.
3. Therefore `human_needed` takes priority over `passed`.

Automated coverage is complete (6/7 SCs automated; 16/16 must-haves; 9/9 NOTF requirements; zero regressions). The single remaining blocker is SC-1's requirement for a live Resend POST against the production API, which cannot be verified by test doubles — it requires the operator to export a real `RESEND_API_KEY` and confirm the email actually lands in the recipient inbox.

Recommended next step for the operator:

```bash
export RESEND_API_KEY=re_...    # from Resend Dashboard
# Optionally: export SIGNALS_EMAIL_TO=<recipient>
.venv/bin/python -m notifier    # OR: .venv/bin/python main.py --test
```

Confirm: email received; subject prefix correct; body renders at 375px in Gmail web + iOS.

---

_Verified: 2026-04-22_
_Verifier: Claude (gsd-verifier)_
