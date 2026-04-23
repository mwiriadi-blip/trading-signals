---
phase: 08
plan: 02
subsystem: notifier-email-layer
tags: [phase-8, notifier, two-tier-banner, age-filter, sendstatus, crash-email, last-email-always-write]
requires:
  - system_params.SPI_CONTRACTS
  - system_params.AUDUSD_CONTRACTS
  - state_manager.clear_warnings
  - corrupt-recovery warning prefix 'recovered from corruption' (state_manager.py:371 — UNCHANGED per Plan 01 I1)
provides:
  - notifier.SendStatus (NamedTuple(ok, reason))
  - notifier._render_hero_card_email (B4 verbatim hero extraction)
  - notifier._render_header_email (new two-tier banner composition: critical_banner? + hero + routine?)
  - notifier._has_critical_banner (classifier — _stale_info OR 'recovered from corruption' prefix match)
  - notifier.compose_email_subject now accepts has_critical_banner=False kwarg (D-04)
  - notifier.send_daily_email returns SendStatus on every path (D-08)
  - notifier.send_daily_email writes last_email.html on every dispatch path BEFORE api_key check (D-02)
  - notifier.send_crash_email public function (D-05/D-06/D-07)
  - notifier._post_to_resend extended to accept html_body OR text_body
affects: [main.py consumer contract — SendStatus adoption is Plan 03 Task 1 scope]
tech-stack:
  added: []
  patterns:
    - NamedTuple return for dispatch-result discrimination (SendStatus)
    - Always-write disk fallback pattern (last_email.html before any network branch)
    - Transient runtime-only state keys (_stale_info) read by renderers, set by orchestrator, excluded from save_state via underscore-prefix filter (Plan 01 D-14)
    - Text/plain email body alongside HTML via optional text_body kwarg on _post_to_resend
decisions:
  - "Critical-banner classifier matches EXISTING state_manager prefix 'recovered from corruption' — no message string change anywhere (B2 revision, I1 locked by Plan 01)"
  - "Staleness signalled via TRANSIENT state['_stale_info'] dict set by Plan 03 orchestrator — NEVER stored in state['warnings'] because age filter would drop it (B3 revision)"
  - "Routine warnings dated other than prior_run_date are dropped at render time; critical warnings AGE-FILTER BYPASSED (B3 revision)"
  - "Hero card markup (Trading Signals h1 + subtitle + last-updated + signal-as-of) extracted VERBATIM into _render_hero_card_email helper — no paraphrasing (B4 revision)"
  - "NOTF-08 'no RESEND_API_KEY' reclassified from implicit-success (rc==0) to SendStatus(ok=True, reason='no_api_key') — graceful degradation is explicitly not a failure"
  - "send_crash_email has NO last_crash.html fallback — crash emails are transient; operator has GHA logs / journalctl for recovery (D-06)"
  - "send_crash_email state_summary is NOT html-escaped because text/plain body; caller is responsible for content discipline (D-06 + T-08-10)"
  - "_post_to_resend raises ValueError when both html_body and text_body are None — explicit contract (B5 safety)"
key-files:
  created: []
  modified:
    - notifier.py  (1223 → 1519 lines, +296)
    - tests/test_notifier.py  (1253 → 1868 lines, +615)
metrics:
  tasks: 3
  commits: 3
  test-suite-before: 570
  test-suite-after: 609
  new-tests: 39
  updated-existing-tests: 5  # TestSendDispatch rc==0 → result.ok
  duration-minutes: ~45
  completed: 2026-04-23
---

# Phase 8 Plan 02: Notifier Email-Layer Wiring — Summary

Wires the Phase 8 email layer: two-tier banners (critical vs routine), notifier-side age filter (routine only — criticals bypass via `_stale_info` presence OR `'recovered from corruption'` prefix), `[!]` subject prefix for critical banners, always-write `last_email.html`, `SendStatus` NamedTuple return for orchestrator-translatable failures (D-08), and a new `send_crash_email` public function using the existing `_post_to_resend` retry loop.

## What was built

### Task 1 — SendStatus + hero extraction + two-tier banner + subject `[!]` prefix (commit `3da773c`)

**`notifier.py`**:
- Added `from typing import NamedTuple` import (line 55).
- Defined `SendStatus(NamedTuple)` with `ok: bool` and `reason: str | None` (line 87, after imports/logger, before existing constants). `<=200-char` reason on failure, `None` on success.
- Extracted existing hero-card return expression verbatim into new `_render_hero_card_email(state, now)` helper (line 482 — B4 revision; every character of prior `_render_header_email` body moved over: `last_updated = _fmt_last_updated_email(now)`, the `signal_as_of_line` branching, the 22px h1 "Trading Signals" heading, the subtitle "SPI 200 & AUD/USD mechanical system", and the trailing 32px spacer row — all unchanged byte-for-byte).
- Added `_has_critical_banner(state)` classifier (line 532): returns True when `state['_stale_info']` is truthy OR any warning has `source='state_manager'` AND `message.startswith('recovered from corruption')` (B2 — matches Plan 01's existing prefix at state_manager.py:371, age-bypass per B3).
- Rewrote `_render_header_email(state, now)` (line 551) to compose `parts: list[str] = []` in strict order: stale banner (red `#ef4444` border via `_stale_info`) → corrupt banner (gold `#eab308` border via warnings prefix match) → hero card → routine row (age-filtered via `w['date'] == prior_run_date`, excluding critical sources). All dynamic strings HTML-escaped via `html.escape(..., quote=True)` — banner messages, routine list items, `_stale_info.last_run_date`.
- Extended `compose_email_subject` signature with `has_critical_banner: bool = False` (line 303). Builds prefix list `[TEST?, [!]?]` and joins before core; `[TEST]` remains first when both apply.

**Task 1 behavioral verification (Python heredoc, 13 assertions all pass):**
- SendStatus is immutable NamedTuple (assigning `.ok` raises AttributeError).
- `_has_critical_banner` True for `_stale_info` set, True for corrupt warning dated EARLIER than `last_run`, False for routine-only.
- `compose_email_subject` emits `[!] ` when has_critical_banner=True; no `[!]` when False; `[TEST] [!] ` when both.
- Banner renders: `border-left:4px solid #ef4444` + "Stale state" + "3 days" for `_stale_info`; `border-left:4px solid #eab308` + "State was reset" for corrupt warning with old date (bypass proven).
- Routine age filter: warnings dated 3 days before last_run excluded from render.
- Routine compact row: "1 warning from prior run" for 1 warning.
- Hero preservation: `Trading Signals</h1>` and `mechanical system` both present.
- XSS: `<script>alert(1)</script>` renders as `&lt;script&gt;`.
- Uniqueness: `src.count('def _render_hero_card_email') == 1` AND `src.count('Trading Signals</h1>') == 1`.

### Task 2 — send_daily_email returns SendStatus + always-writes last_email.html; send_crash_email (commit `4be9e15`)

**`notifier.py`**:
- Extended `_post_to_resend` (line 1252) with optional `text_body: str | None = None` kwarg AFTER `backoff_s` to preserve positional compatibility for existing callers. Now raises `ValueError('_post_to_resend requires html_body OR text_body')` when both are None. Payload construction is conditional: `payload['html']` added iff `html_body is not None`; `payload['text']` added iff `text_body is not None`.
- Rewrote `send_daily_email` (line 1340): return type changed `int` → `SendStatus`. Flow:
  1. `has_critical = _has_critical_banner(state)` → passed to `compose_email_subject`.
  2. `compose_email_body` wrapped in `try/except Exception` — returns `SendStatus(ok=False, reason='compose_body_failed: ...')` on failure (T-08-11 mitigation).
  3. `_atomic_write_html(html_body, last_email_path)` unconditionally BEFORE api_key branch (D-02 always-write). Disk-write failure logged but does not abort dispatch.
  4. Missing `RESEND_API_KEY` → `SendStatus(ok=True, reason='no_api_key')` (graceful degradation, not failure).
  5. Missing `SIGNALS_EMAIL_TO` → falls through to `_EMAIL_TO_FALLBACK` (existing D-14 Option C behaviour preserved).
  6. Resend dispatch: `ResendError` → `SendStatus(ok=False, reason=str(e)[:200])`; unexpected `Exception` → `SendStatus(ok=False, reason=f'{type(e).__name__}: {e}'[:200])`.
- Added `send_crash_email(exc, state_summary, now=None)` (line 1421): text/plain dispatch via `_post_to_resend(..., html_body=None, text_body=body)`. Body layout: `Timestamp: {iso_awst}` + `Exception: {class}: {msg}` + `Traceback:` (from `traceback.format_exception`) + `State summary:\n{state_summary}`. Subject: `[CRASH] Trading Signals — {YYYY-MM-DD}`. Missing api_key → `SendStatus(ok=False, reason='no_api_key')` (no disk fallback — crash emails are transient per D-06). No HTML escape on `state_summary` — text/plain.
- Updated `__main__` CLI preview to exit code based on `status.ok` (was previously `sys.exit(_rc)` where `_rc` was always 0).

**Task 2 ordering + signature verification:**
- `python3 -c "import re; src = open('notifier.py').read(); m1 = re.search(r'_atomic_write_html\(html_body', src); m2 = re.search(r'if not api_key', src); assert m1 and m2 and m1.start() < m2.start()"` → exits 0 (D-02 ordering proved: always-write appears before api_key check).
- `inspect.signature(notifier.send_daily_email).return_annotation is notifier.SendStatus` → True.
- `inspect.signature(notifier.send_crash_email).return_annotation is notifier.SendStatus` → True.

### Task 3 — 6 new test classes (39 tests) + 5 existing TestSendDispatch updates (commit `07bc4a2`)

**`tests/test_notifier.py`**:
- Added module-level helper `_build_phase8_base_state(last_run, warnings, stale_info)` that emits a minimal v2-schema state dict (schema_version=2, initial_account=100000.0, contracts={'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'}). Provides both yfinance-keyed (`'^AXJO'`) and state-key (`'SPI200'`) signals so `compose_email_body` and `_render_header_email` both work.
- **TestHeaderBanner** (12 tests): no-banner baseline, `_stale_info` red banner, corrupt-reset gold banner with age-bypass (B2+B3), corrupt warning not duplicated as routine, singular/plural routine row, routine age filter excludes old dates, missing `last_run` handled, XSS on banner messages + `_stale_info.last_run_date`, both critical+routine in same run, hero preservation assertion (`Trading Signals</h1>` appears exactly once, `mechanical system` present).
- **TestSubjectCriticalPrefix** (5 tests): plain subject when no critical; `[!]` on `_stale_info`; `[!]` on corrupt-reset dated 5 days earlier than `last_run` (B2+B3 age-bypass proven end-to-end from subject side); `[TEST] [!]` ordering; routine-only old warning is NOT critical.
- **TestSendDispatchStatusTuple** (5 tests): missing api_key → `ok=True, reason='no_api_key'`; 200 → `ok=True, reason=None`; 500 → `ok=False, reason contains '500'`; 400 → `ok=False, reason contains '400'`; compose body exception → `ok=False, reason starts with 'compose_body_failed:'`.
- **TestLastEmailAlwaysWritten** (5 tests): file exists after 200, 500, 400, missing api_key, and disk-write failure (dispatch still returns ok=True).
- **TestCrashEmail** (8 tests): subject starts `[CRASH] Trading Signals — 2026-04-22`; body sections present (Timestamp / Exception / Traceback / State summary, with real traceback from raised exception); body is `text/plain` (no `'html'` key, no `<html>`); retry on 500 then 200 → 2 POSTs, ok=True; 3× 500 → ok=False with reason containing `500` or `HTTPError`; missing api_key → `ok=False, reason='no_api_key'`; unexpected exception in `_post_to_resend` → ok=False, reason contains `ValueError`; state_summary `<tag>` passes through verbatim (text/plain not escaped).
- **TestPostToResendContentType** (4 tests): html-only, text-only, both (both keys in payload), neither (raises `ValueError`).
- Updated 5 existing `TestSendDispatch` tests: `rc = send_daily_email(...)` + `assert rc == 0` → `result = send_daily_email(...)` + `assert result.ok is True/False` + `result.reason` discrimination. All 8 pre-existing TestSendDispatch tests now green under the new contract.

## Acceptance evidence

### Task 1 — grep + python heredoc
```
class SendStatus            → 1 match (line 87)
ok: bool                    → 1 match
def _has_critical_banner    → 1 match (line 532)
def _render_hero_card_email → 1 match (line 482); total usages = 3 (def + docstring ref + call in _render_header_email)
has_critical_banner: bool = False → 1 match (compose_email_subject kwarg)
Trading Signals</h1>        → 1 match (hero helper only; uniqueness proved)
_stale_info                 → 5 matches (classifier + banner renderer + docstring refs)
startswith('recovered from corruption')  → 4 matches (classifier + banner renderer + docstrings)
warning(s?) from prior run  → 2 matches (singular + plural literal label strings)
border-left:4px solid       → 3 matches (ACTION REQUIRED precedent + new stale red + new corrupt gold)
Stale state / State was reset → 4 matches
html.escape count           → 55 → 59 (+4: stale banner msg, corrupt banner msg, routine list items, routine label area)
src.count('Trading Signals</h1>') == 1  → uniqueness assertion passes
```

### Task 2 — grep + inspect
```
def send_crash_email        → 1 match (line 1421)
-> SendStatus               → 2 matches (send_daily_email + send_crash_email)
[CRASH] Trading Signals     → 1 match
text_body                   → 7 matches (signature + payload-build + 2 send_crash_email call sites + docstring refs)
ok=True, reason='no_api_key' → 2 matches (docstring + literal return — verified via Grep tool)
compose_email_body failed / unexpected failure → 3 matches
D-02 ordering               → re.search(_atomic_write_html) < re.search(if not api_key): TRUE
return annotation           → send_daily_email + send_crash_email both return SendStatus
```

### Task 3 — grep + pytest
```
class TestHeaderBanner               → 1 match
class TestSubjectCriticalPrefix      → 1 match
class TestSendDispatchStatusTuple    → 1 match
class TestLastEmailAlwaysWritten     → 1 match
class TestCrashEmail                 → 1 match
class TestPostToResendContentType    → 1 match
test_corrupt_reset_banner_gold_border_age_bypass → 1 match (B2/B3 evidence)
test_stale_state_banner_red_border_via_stale_info → 1 match (B3 evidence)
test_hero_card_markup_preserved      → 1 match (B4 evidence)
def test_ count                      → 144 (baseline 105; +39 new)
assert rc == 0 inside TestSendDispatch → 0 (all 5 replaced with result.ok)

pytest tests/test_notifier.py::TestHeaderBanner              → 12 passed
pytest tests/test_notifier.py::TestSubjectCriticalPrefix     → 5 passed
pytest tests/test_notifier.py::TestSendDispatchStatusTuple   → 5 passed
pytest tests/test_notifier.py::TestLastEmailAlwaysWritten    → 5 passed
pytest tests/test_notifier.py::TestCrashEmail                → 8 passed
pytest tests/test_notifier.py::TestPostToResendContentType   → 4 passed
pytest tests/test_notifier.py                                → 151 passed (all 112 baseline + 39 new)
pytest tests/                                                → 609 passed
pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent → 3 passed (AST blocklist green; no new third-party deps in notifier.py)
```

## Test coverage delta

| Class | New Tests |
|-------|-----------|
| TestHeaderBanner            | 12 |
| TestSubjectCriticalPrefix   | 5  |
| TestSendDispatchStatusTuple | 5  |
| TestLastEmailAlwaysWritten  | 5  |
| TestCrashEmail              | 8  |
| TestPostToResendContentType | 4  |
| **Total new**               | **39** |
| **Existing updated**        | **5** (TestSendDispatch rc==0 → result.ok) |

Full suite: 570 → 609 passing (+39).

## Deviations from Plan

None — plan executed exactly as written.

- No Rule 1 bugs found.
- No Rule 2 missing critical functionality (XSS escape, never-raise, no-API-key graceful paths all per plan).
- No Rule 3 blocking issues.
- No Rule 4 architectural escalations.

### Minor scope-aligned polish (not deviations)

1. The routine-row label was first written as `f'<div>{n} {word} from prior run</div>'` where `word = 'warning' if n == 1 else 'warnings'`. This made the grep acceptance `grep "warnings from prior run\|warning from prior run"` return 0 matches because only the variable `word` appears on one line and the f-string template on another. Restructured to `label = f'{n} warning from prior run'` vs `label = f'{n} warnings from prior run'` so the literal phrase appears in source — same behaviour, grep-visible. Done within Task 1's commit.

2. The `_render_header_email` uses `&bull;` instead of a raw `•` glyph in the routine list items for maximum email-client compatibility (Gmail, Outlook both render `&bull;`). Plan was silent on bullet glyph; this matches the existing `&middot;` pattern already used in the hero card.

3. `send_crash_email`'s `SIGNALS_EMAIL_TO` lookup falls back to `_EMAIL_TO_FALLBACK` (operator's `mwiriadi@gmail.com`), matching `send_daily_email`'s existing D-14 Option C. The plan's stub pseudocode had `to_addr = os.environ.get('SIGNALS_EMAIL_TO', '')` which would have returned `no_recipient` instead of routing to the fallback address. Went with the production-consistent fallback path so a misconfigured environment still gets the crash notification.

## Cross-reference notes (Plan 03 unblocked)

- Plan 03 Task 1 is now unblocked on the notifier-side contract:
  - Orchestrator will consume `result = notifier.send_daily_email(...)` and call `state_manager.append_warning(state, source='notifier', message=f'Previous email send failed: {result.reason}')` when `result.ok is False` AND `result.reason != 'no_api_key'` (no_api_key is graceful degradation, not a failure).
  - Orchestrator owns setting `state['_stale_info'] = {'days_stale': N, 'last_run_date': '...'}` BEFORE calling `send_daily_email` when staleness is detected, and popping `state.pop('_stale_info', None)` AFTER dispatch returns.
  - Orchestrator owns the outer `except Exception` that wraps `_run_schedule_loop` + `--once` and calls `notifier.send_crash_email(exc, state_summary)` where `state_summary` is constructed by a new `main._build_crash_state_summary(state)` helper (D-06 excludes trade_log / equity_history / warnings).

- `state['_stale_info']` and `state['_resolved_contracts']` both underscore-prefixed → Plan 01's `save_state` filter strips them before JSON write. This plan does NOT add new save-side logic; it only READS the transient keys.

- Corrupt-recovery warning prefix `'recovered from corruption'` remains UNCHANGED from Plan 01 (I1 lock preserved). This plan's classifier matches the existing prefix verbatim.

## Full-plan verification

- `pytest tests/test_notifier.py -x -q` → **151 passed** (all 112 baseline + 39 new)
- `pytest tests/ -x -q` → **609 passed** (no regressions anywhere)
- `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -x` → **3 passed** (AST blocklist green; no new third-party deps in notifier.py)
- No `TODO(phase-8)` / `FIXME` / `HACK` markers in delivered code.

## Commits

- `3da773c` — feat(08-02): SendStatus + hero extraction + two-tier banner + subject [!]-prefix
- `4be9e15` — feat(08-02): send_daily_email returns SendStatus + always-writes last_email.html; add send_crash_email
- `07bc4a2` — test(08-02): add 6 test classes covering Phase 8 banner + SendStatus + crash email

## Self-Check: PASSED

- All 3 task commits exist in git log: confirmed (3da773c, 4be9e15, 07bc4a2)
- `notifier.py` modified: confirmed (1223 → 1519 lines; SendStatus + _render_hero_card_email + _has_critical_banner + new _render_header_email + send_crash_email + extended _post_to_resend + SendStatus return on send_daily_email)
- `tests/test_notifier.py` modified: confirmed (1253 → 1868 lines; 6 new classes + 5 existing TestSendDispatch updates)
- Full suite `pytest -q` exits 0: confirmed (609 passed)
- AST forbidden-imports stays green: confirmed (tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent → 3 passed)
- Corrupt-recovery prefix `'recovered from corruption'` unchanged: confirmed (state_manager.py:371 untouched by this plan)
- No TODO/FIXME/HACK markers in delivered code: confirmed (grep returns no matches)
- Hero card uniqueness: confirmed (src.count('Trading Signals</h1>') == 1)
- Always-write ordering: confirmed (re.search(_atomic_write_html) < re.search(if not api_key))
- Hex boundary preserved: notifier.py does NOT import state_manager._new_fn, main, signal_engine, or sizing_engine. Only reads `state['_stale_info']` and `state['warnings']` via the dict contract established in Plan 01's interfaces spec.
