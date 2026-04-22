---
phase: 06-email-notification
reviewed: 2026-04-22T00:00:00Z
depth: standard
files_reviewed: 18
files_reviewed_list:
  - .env.example
  - .gitignore
  - dashboard.py
  - main.py
  - notifier.py
  - system_params.py
  - tests/fixtures/notifier/empty_state.json
  - tests/fixtures/notifier/golden_empty.html
  - tests/fixtures/notifier/golden_empty_subject.txt
  - tests/fixtures/notifier/golden_no_change.html
  - tests/fixtures/notifier/golden_no_change_subject.txt
  - tests/fixtures/notifier/golden_with_change.html
  - tests/fixtures/notifier/golden_with_change_subject.txt
  - tests/fixtures/notifier/sample_state_no_change.json
  - tests/fixtures/notifier/sample_state_with_change.json
  - tests/regenerate_notifier_golden.py
  - tests/test_main.py
  - tests/test_notifier.py
findings:
  critical: 0
  warning: 2
  info: 5
  total: 7
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-04-22
**Depth:** standard
**Files Reviewed:** 18
**Status:** issues_found

## Summary

Phase 6 lands cleanly. Every cross-AI review finding from `06-REVIEWS.md` that was in scope for the code layer is genuinely present in the committed source — not just echoed in plan prose. The never-crash invariant, hex-boundary fence, `html.escape` leaf discipline, and CLI-01 structural read-only contract all hold up under inspection.

**Verification of REVIEWS.md fixes (all confirmed in code):**

- **Fix 1 (HIGH) — API-key redaction:** `notifier.py:1124-1125` replaces `api_key` with `[REDACTED]` in the 4xx error body before raising, and `notifier.py:1141-1143` mirrors the same redaction in the retries-exhausted message path. Both paths also guarded by `if api_key:` to handle the no-key branch.
- **Fix 2 (MEDIUM) — timeout tuple:** `notifier.py:1114` passes `timeout=(5, timeout_s)` to `requests.post`; test `tests/test_notifier.py:915-933` asserts the exact tuple.
- **Fix 3 — exact P&L + Trail Stop numeric assertions:** `tests/test_notifier.py:431-509` pins LONG trail = `peak - TRAIL_MULT_LONG * atr_entry` (`$0.64` for the AUDUSD fixture), SHORT trail = `trough + TRAIL_MULT_SHORT * atr_entry` (`$8,385.00`), and both unrealised-P&L assertions include the opening-half-cost subtraction.
- **Fix 4 — last-3 scan:** `notifier.py:370` iterates `reversed(trade_log[-3:])`; test `tests/test_notifier.py:515-550` exercises the same-run double-close case by appending a second AUDUSD record and asserting both lookups succeed.
- **Fix 7 — 4-tuple return at both sites:** `main.py:647` (--test early-return) and `main.py:672` (success path) both return `(rc, state, old_signals, run_date)`; the docstring at `main.py:437-443` reflects the new signature; the 5 callers (`main:764`, `main:774`, plus three test sites in `tests/test_main.py`) all unpack 4 items.
- **Fix 10 — None-guard:** `main.py:765-770` gates `_send_email_never_crash` behind `rc == 0 and state is not None and old_signals is not None and run_date is not None`.
- **CLI-01 read-only contract:** `main.py:638-647` still returns before `save_state()` under `args.test`; `tests/test_main.py:294-319` asserts `state.json` mtime unchanged after `main(['--test'])` even though email is now dispatched.
- **Never-crash invariant:** `_send_email_never_crash` (`main.py:122-146`) uses `import notifier` inside the try block (C-2 pattern), catching both import-time and runtime failures; `send_daily_email` (`notifier.py:1149-1198`) catches `ResendError`, bare `Exception`, and has no unhandled raise path on the NOTF-08 fallback (`notifier.py:1170-1177` wraps even the `_atomic_write_html` call).
- **html.escape discipline:** 55 `html.escape(value, quote=True)` call sites across `notifier.py`; every state-derived string (exit_reason, instrument, direction, signal_as_of, dates, entry/exit prices, n_contracts) lands through escape at the leaf interpolation. XSS tests at `tests/test_notifier.py:341-361` confirm `<script>alert(1)</script>` and `<img src=x onerror=y>` are neutralised across the exit_reason, instrument, and direction surfaces.
- **Hex boundary:** `notifier.py` imports only `html`, `logging`, `os`, `tempfile`, `time`, `datetime`, `pathlib`, `pytz`, `requests`, `state_manager`, `system_params` — AST blocklist enforced at `tests/test_signal_engine.py:572-579` + `:880-903`.
- **Secrets hygiene:** `.env.example:8` uses the 40-char zero-entropy placeholder `re_xxx...x`; `.gitignore:3` lists `last_email.html`; `.gitignore:4` gitignores `.env`. No real Resend key anywhere in the repo. The `mwiriadi@gmail.com` fallback is a deliberate D-14 Option C operator-confirmed choice and surfaces only in `notifier.py:87` + the test that asserts it — acceptable, and noted as Info below.

All 515/515 tests passing and regenerator double-run idempotency confirm the implementation is aligned with the goldens.

## Warning

### WR-01: `run_daily_check` docstring claims a `(rc, None, None, None)` failure return path that never executes

**File:** `main.py:441-443`
**Category:** Code Quality / Documentation drift
**Issue:** The docstring states: *"On failure paths where state/old_signals are not yet populated, returns (rc, None, None, None) — the dispatch ladder in main() guards with `if state is not None`."* Inspecting the function body, there is no such return statement. Every failure path (`DataFetchError`, `ShortFrameError`, unexpected `Exception`) propagates up and is caught in `main()` lines 776-783, which returns `int` directly. The function has exactly two `return` statements, both of which return populated 4-tuples (lines 647 and 672).

This means the None-guard at `main.py:765-770` is effectively unreachable under the current implementation — defensive in intent, but the docstring overstates the behaviour. A future refactor that adds a non-exception-based failure path (e.g., early return on a pre-fetch invariant violation) would re-activate the guard. Not a correctness bug, but a docstring contract that diverges from runtime behavior is a trap for future readers.

**Fix:** Either reword the docstring to reflect that exceptions propagate and the None-guard is defense-in-depth for future-proofing, OR convert the existing exception paths in `run_daily_check` to explicit returns (not recommended — the typed-exception boundary in `main()` is cleaner). Suggested reword:
```python
  '''...
  On the happy path returns (0, state, old_signals, run_date).
  On failure, exceptions (DataFetchError, ShortFrameError, or anything
  unexpected) propagate up and are caught by main()'s typed-exception
  boundary. The None-guard in main()'s dispatch ladder is defense-in-
  depth for any future non-exception failure return.
  '''
```

### WR-02: Empty-state subject golden has an empty date slot producing visual double-space

**File:** `tests/fixtures/notifier/golden_empty_subject.txt:1` (and by extension `notifier.py:311-319`)
**Category:** Edge case / UX
**Issue:** The committed empty-state subject is `📊  — SPI200 FLAT, AUDUSD FLAT — Equity $100,000` — note the double space between `📊` and `—`. This is because `empty_state.json` has `last_run: null` and int-shape signals (no `as_of_run` key), so the `date_iso` fallback chain in `compose_email_subject` resolves to `''`:

```python
# notifier.py:311-319
date_iso: str | None = None
for state_key in ('SPI200', 'AUDUSD'):
  raw = signals.get(state_key)
  if isinstance(raw, dict) and raw.get('as_of_run'):
    date_iso = raw['as_of_run']
    break
if date_iso is None:
  date_iso = state.get('last_run') or ''
```

Then the f-string at line 340 renders `f'{emoji} {date_iso} — SPI200 ...'` which produces `'📊  — SPI200 ...'` with two spaces. On a first-run day an operator opens an email with a slightly mangled subject. Low-severity cosmetic issue, but worth pinning down: the regenerator confirmed this byte-identical output so the test is green — but the output itself is wrong.

**Fix:** In `compose_email_subject`, when `date_iso` is empty, either fall back to `run_date` passed from main.py (requires adding `now` as a third arg, which is a small API change), or render a clearer first-run token:
```python
# notifier.py:339-342
if not date_iso:
  date_label = 'first run'
else:
  date_label = date_iso
core = (
  f'{emoji} {date_label} — SPI200 {spi_label}, '
  f'AUDUSD {audusd_label} — Equity {equity_str}'
)
```
Then regenerate `golden_empty_subject.txt`. Alternatively, accept the cosmetic double-space as a known edge case (the operator only ever sees it on the very first run before state.json has a last_run).

## Info

### IN-01: `_EMAIL_TO_FALLBACK` commits a real operator email address to the repo

**File:** `notifier.py:87`
**Category:** Secrets hygiene / Information disclosure (low)
**Issue:** `_EMAIL_TO_FALLBACK = 'mwiriadi@gmail.com'` is a real personal Gmail address and will live in git history forever. This is a deliberate D-14 Option C choice (see `06-REVIEWS.md:220-225` and test `tests/test_notifier.py:1046-1059`), and single-operator-single-sender is the documented invariant. Still worth flagging as a known-accepted footprint: the alternative (`RECIPIENT_NOT_SET@example.invalid` + raise on missing env) was explicitly considered and declined.

**Fix:** No code change needed — this is operator-confirmed. If the operator later wants to scrub it, migrate to a `SIGNALS_EMAIL_TO`-required posture: raise a `ResendError` when env is unset, log a [Email] WARN, and return 0 (never-crash still holds). Document the history-rewrite cost in a v2 task.

### IN-02: `load_state` imported at module top of `notifier.py` despite being used only by the `__main__` CLI block

**File:** `notifier.py:59`
**Category:** Code Quality / Import surface
**Issue:** `from state_manager import load_state` is at module-top scope but only referenced at `notifier.py:1212` inside `if __name__ == '__main__':`. This is flagged in `06-REVIEWS.md:74-76` (Codex §06-01 LOW concern) and the planner's fix was to move it into the `__main__` block. The fix was not applied in Wave 0 and did not surface as a required Wave 2 gate. The AST blocklist permits the import (it's in the allowlist for notifier), so this is not a hex-boundary violation — just import surface bloat.

**Fix:** Move the import into the CLI block:
```python
if __name__ == '__main__':
  import sys
  from state_manager import load_state  # CLI-only
  logging.basicConfig(level=logging.INFO, format='%(message)s')
  _state = load_state()
  # ...
```

### IN-03: Public function type annotations under-specified — `old_signals: dict` vs `dict[str, int | None]`

**File:** `notifier.py:285-287`, `:957-961`, `:1149-1154` (`compose_email_subject`, `compose_email_body`, `send_daily_email`)
**Category:** Code Quality / Type specificity
**Issue:** CONTEXT D-01 specifies the public API as `old_signals: dict[str, int | None]` but the actual signatures widen this to bare `dict`. Same for `state: dict` (could be `state: dict[str, object]` or a `TypedDict`). Type checkers and IDE autocomplete don't catch callers that pass the wrong shape. Not a correctness bug (Python is structurally typed here), but a minor polish gap relative to CONTEXT.

**Fix:** Tighten the annotations:
```python
def compose_email_subject(
  state: dict,
  old_signals: dict[str, int | None],
  is_test: bool = False,
) -> str:
```
Apply to `compose_email_body` and `send_daily_email` as well. Low-priority; defer to a batch typing pass if desired.

### IN-04: Unused `_fmt_percent_unsigned_email` formatter

**File:** `notifier.py:194-200`
**Category:** Dead code / unused function
**Issue:** `_fmt_percent_unsigned_email` is defined but never called by any of the per-section renderers in Wave 1. The docstring says it's "for ADX / RVol display" but Wave 1's `_render_signal_status_email` (`notifier.py:570-663`) formats ADX with `f'{scalars.get("adx", 0.0):.1f}'` and does not render RVol. The function is tested (`tests/test_notifier.py:591-595`) to match the dashboard parity contract.

**Fix:** Either (a) remove the function now (tests + function), defer to a potential future section that needs unsigned percent; OR (b) leave as-is as dashboard parity for the _email formatter family (matches the pattern `_fmt_*_email` mirrors `_fmt_*` in dashboard). Current disposition is acceptable — it's cheap to carry and the dashboard parity intent is documented in D-02. No action required; noted only.

### IN-05: `notifier.py` `_atomic_write_html` duplicates `dashboard.py:981` and `state_manager._atomic_write` byte-for-byte

**File:** `notifier.py:1027-1066`, `dashboard.py:981-1025`
**Category:** Code duplication
**Issue:** Per D-13, `_atomic_write_html` is deliberately duplicated across hexes to avoid cross-hex imports (zero coupling, ~40 lines). This is a conscious design choice (CONTEXT D-13 says "Recommendation: duplicate in notifier.py"). Three identical copies of the atomic-write pattern now live in `state_manager._atomic_write`, `dashboard._atomic_write_html`, and `notifier._atomic_write_html`. If the durability contract ever needs to change (e.g., add checksum verification), all three must be edited in lockstep.

**Fix:** No action — duplicate-per-hex was the explicit D-13 decision, and extraction to `state_manager._atomic_write` would reintroduce cross-hex coupling. Noted only for future reference: if a fourth consumer lands, consider promoting to `system_params.py` (pure-stdlib module with no I/O fence) or creating a shared `_atomic.py` utility module.

---

_Reviewed: 2026-04-22_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
