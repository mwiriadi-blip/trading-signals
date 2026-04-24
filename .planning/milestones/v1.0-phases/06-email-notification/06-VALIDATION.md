---
phase: 6
slug: email-notification
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-22
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 + pytest-freezer 0.4.9 |
| **Config file** | `pyproject.toml` (installed Phase 1) |
| **Quick run command** | `.venv/bin/pytest tests/test_notifier.py tests/test_main.py -x` |
| **Full suite command** | `.venv/bin/pytest tests/ -x` |
| **Estimated runtime** | ~6-8 seconds full suite |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest tests/test_notifier.py tests/test_main.py -x` (quick — <5s)
- **After every plan wave:** Run `.venv/bin/pytest tests/ -x` (full — ~6-8s)
- **Before `/gsd-verify-work`:** Full suite green + `ruff` clean + `tests/regenerate_notifier_golden.py` idempotent (double-run → zero git diff)
- **Max feedback latency:** 8 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 0 | INFRA | T-06-01 | notifier.py stub cannot import forbidden hex modules | unit (AST) | `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -x` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 0 | INFRA | — | Palette constants live in system_params.py; dashboard imports succeed | unit | `pytest tests/test_dashboard.py -x` | ✅ (retrofit) | ⬜ pending |
| 06-01-03 | 01 | 0 | INFRA | T-06-02 | `.env.example` committed with placeholders only (no real key) | grep | `grep -q '^RESEND_API_KEY=re_xxx' .env.example` | ❌ W0 | ⬜ pending |
| 06-01-04 | 01 | 0 | INFRA | — | `.gitignore` blocks `last_email.html` commit | grep | `grep -q '^last_email.html' .gitignore` | ❌ W0 | ⬜ pending |
| 06-01-05 | 01 | 0 | NOTF-01..09 | — | Test skeletons exist (6 classes) | pytest collect | `pytest tests/test_notifier.py --collect-only` | ❌ W0 | ⬜ pending |
| 06-01-06 | 01 | 0 | NOTF-01..09 | — | 3 JSON fixtures present | file exists | `ls tests/fixtures/notifier/*.json \| wc -l` → 3 | ❌ W0 | ⬜ pending |
| 06-02-01 | 02 | 1 | NOTF-02 | — | `compose_email_subject` emoji+date+signals+equity | unit | `pytest tests/test_notifier.py::TestComposeSubject -x` (6 cases) | ❌ W0 | ⬜ pending |
| 06-02-02 | 02 | 1 | NOTF-02 | — | `[TEST]` prefix appears BEFORE emoji on --test runs | unit | `pytest tests/test_notifier.py::TestComposeSubject::test_test_prefix_order -x` | ❌ W0 | ⬜ pending |
| 06-02-03 | 02 | 1 | NOTF-03, NOTF-04, NOTF-06 | — | 7 body sections render in order; max-width 600px; no `<style>` block | unit (substring + order) | `pytest tests/test_notifier.py::TestComposeBody -x` | ❌ W0 | ⬜ pending |
| 06-02-04 | 02 | 1 | NOTF-05 | — | ACTION REQUIRED block appears ONLY when any signal changed | unit | `pytest tests/test_notifier.py::TestComposeBody::test_action_required_conditional -x` | ❌ W0 | ⬜ pending |
| 06-02-05 | 02 | 1 | NOTF-09 | T-06-03 | `<script>alert(1)</script>` in exit_reason becomes `&lt;script&gt;...` | unit (XSS) | `pytest tests/test_notifier.py::TestComposeBody::test_xss_escape_on_exit_reason -x` | ❌ W0 | ⬜ pending |
| 06-02-06 | 02 | 1 | NOTF-04 | — | All email formatters produce stable output | unit | `pytest tests/test_notifier.py::TestFormatters -x` | ❌ W0 | ⬜ pending |
| 06-02-07 | 02 | 1 | NOTF-05 | — | First-run path: `old_signals[sym]=None` → no ACTION REQUIRED | unit | `pytest tests/test_notifier.py::TestComposeBody::test_first_run_no_action_required -x` | ❌ W0 | ⬜ pending |
| 06-03-01 | 03 | 2 | NOTF-01 | T-06-02 | `_post_to_resend` hits exact URL with Bearer header | unit (mock requests) | `pytest tests/test_notifier.py::TestResendPost::test_post_url_and_auth_header -x` | ❌ W0 | ⬜ pending |
| 06-03-02 | 03 | 2 | NOTF-07 | — | 4xx fails fast (no retry); 5xx retries 3× with 10s backoff; 429 retryable | unit (mock) | `pytest tests/test_notifier.py::TestResendPost -x` | ❌ W0 | ⬜ pending |
| 06-03-03 | 03 | 2 | NOTF-07 | — | `send_daily_email` returns 0 on Resend failure (NEVER raises) | unit (mock) | `pytest tests/test_notifier.py::TestSendDispatch::test_5xx_logs_and_returns_zero -x` | ❌ W0 | ⬜ pending |
| 06-03-04 | 03 | 2 | NOTF-08 | — | Missing `RESEND_API_KEY` writes `last_email.html`, logs WARN, returns 0 | unit (env clear + tmp_path) | `pytest tests/test_notifier.py::TestSendDispatch::test_missing_api_key_writes_fallback -x` | ❌ W0 | ⬜ pending |
| 06-03-05 | 03 | 2 | NOTF-01..09 | — | Golden HTML byte-stable (3 fixtures → 3 goldens) | unit (byte-equal) | `pytest tests/test_notifier.py::TestGoldenEmail -x` | ❌ W0 | ⬜ pending |
| 06-03-06 | 03 | 2 | CLI-03 | — | `--force-email` dispatches via `run_daily_check` tuple return, saves state | integration | `pytest tests/test_main.py::TestCLI::test_force_email_sends_live_email -x` | ❌ W0 | ⬜ pending |
| 06-03-07 | 03 | 2 | CLI-01 | T-06-04 | `--test` sends `[TEST]`-prefixed email, `state.json` mtime unchanged | integration | `pytest tests/test_main.py::TestCLI::test_test_flag_sends_test_prefixed_email_no_state_mutation -x` | ❌ W0 | ⬜ pending |
| 06-03-08 | 03 | 2 | D-15 | — | `_send_email_never_crash` isolates runtime AND import-time failures | integration | `pytest tests/test_main.py::TestEmailNeverCrash -x` | ❌ W0 | ⬜ pending |
| 06-03-09 | 03 | 2 | PHASE-GATE | — | Regenerator idempotent (double-run → zero git diff on goldens) | manual | `python tests/regenerate_notifier_golden.py && python tests/regenerate_notifier_golden.py && git diff --exit-code tests/fixtures/notifier/` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_notifier.py` — 6-class skeleton (TestComposeSubject, TestComposeBody, TestFormatters, TestSendDispatch, TestResendPost, TestGoldenEmail) with one failing placeholder per NOTF-XX to satisfy Nyquist Dimension 8
- [ ] `tests/fixtures/notifier/sample_state_with_change.json` — SPI200 LONG→SHORT transition with closed trade in trade_log[-1]; ≥2 equity_history points
- [ ] `tests/fixtures/notifier/sample_state_no_change.json` — both instruments unchanged; ≥2 equity_history points
- [ ] `tests/fixtures/notifier/empty_state.json` — reset_state() output (zero positions, zero trades)
- [ ] `tests/fixtures/notifier/golden_with_change.html` — placeholder (regenerated in Wave 2)
- [ ] `tests/fixtures/notifier/golden_no_change.html` — placeholder
- [ ] `tests/fixtures/notifier/golden_empty.html` — placeholder
- [ ] `tests/regenerate_notifier_golden.py` — operator-only regenerator with double-run guard
- [ ] `.env.example` — at repo root, `RESEND_API_KEY=re_xxx` + `SIGNALS_EMAIL_TO=your-email@example.com` (placeholders only)
- [ ] `.gitignore` — add `last_email.html` (verify Phase 5 `dashboard.html` pattern still in place)
- [ ] `tests/test_signal_engine.py` — extend `TestDeterminism::test_forbidden_imports_absent` parametrization with `FORBIDDEN_MODULES_NOTIFIER = frozenset({'signal_engine', 'sizing_engine', 'data_fetcher', 'main', 'dashboard', 'numpy', 'pandas'})` applied to `notifier.py`
- [ ] Palette retrofit: move `_COLOR_BG`, `_COLOR_SURFACE`, `_COLOR_BORDER`, `_COLOR_TEXT`, `_COLOR_TEXT_MUTED`, `_COLOR_TEXT_DIM`, `_COLOR_LONG`, `_COLOR_SHORT`, `_COLOR_FLAT` from `dashboard.py` module-level to `system_params.py`; `dashboard.py` imports them from there; `notifier.py` imports them from there; Phase 5 dashboard golden tests must still pass unchanged

Framework install: none — all deps already pinned.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Gmail web renders `#0f1117` dark bg without auto-inverting to light | NOTF-03, NOTF-06 | Client-specific rendering cannot be unit-tested | After Wave 2: send via Resend sandbox to mwiriadi@gmail.com, open in Gmail web (Chrome), confirm dark background + palette colors match dashboard |
| iOS Mail renders at 375px without horizontal scroll | NOTF-06 | Viewport-specific rendering cannot be unit-tested | After Wave 2: send via Resend to iCloud Mail, open on iPhone, confirm no scroll + all sections readable |
| Emoji (🔴 / 📊) in subject line survive transit (no `\uXXXX` literal) | NOTF-02 | End-to-end byte fidelity requires inbox observation | After Wave 2: inspect delivered subject line in Gmail web inbox list |
| ACTION REQUIRED block red-border renders in Gmail web dark-theme + light-theme | NOTF-05 | Dark-mode auto-inversion may strip border colour | After Wave 2: toggle Gmail theme, confirm `#ef4444` border persists |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (test_notifier.py, fixtures, goldens, regenerator, .env.example, .gitignore, AST blocklist)
- [ ] No watch-mode flags (`pytest -x` exits on first failure, no `--watch`)
- [ ] Feedback latency <8s (full suite)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
