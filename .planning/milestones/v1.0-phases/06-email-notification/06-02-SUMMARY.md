---
phase: 6
plan: 2
subsystem: email-notification
tags: [email, compose, subject, body, formatters, xss-escape, wave-1]

requires:
  - phase 6 wave 0 scaffold (notifier.py stub + fixtures + AST blocklist + palette retrofit)
  - CLAUDE.md [Email] log prefix locked
  - Phase 5 D-15 html.escape leaf discipline precedent
provides:
  - compose_email_subject(state, old_signals, is_test) — D-04 subject template (🔴/📊)
  - compose_email_body(state, old_signals, now) — D-07 HTML shell + D-10 7 sections
  - _detect_signal_changes(state, old_signals) — D-06 first-run-as-no-change helper
  - _closed_position_for_instrument_on(state, state_key, run_date_iso) — last-3 scan (Fix 4)
  - 7 email formatters (_fmt_em_dash_email, _fmt_currency_email,
    _fmt_percent_signed_email, _fmt_percent_unsigned_email,
    _fmt_pnl_with_colour_email, _fmt_last_updated_email,
    _fmt_instrument_display_email)
  - 7 per-section render helpers (_render_header_email, _render_action_required_email,
    _render_signal_status_email, _render_positions_email, _render_todays_pnl_email,
    _render_closed_trades_email, _render_footer_email)
  - Hex-fenced math helpers (_compute_trail_stop_email, _compute_unrealised_pnl_email)
  - State-shape extractors (_extract_signal_int, _extract_signal_as_of, _extract_last_close)
  - Module-level dispatch constants: _STATE_KEY_TO_YF_SYMBOL, _SIGNAL_LABELS_EMAIL,
    _SIGNAL_COLOUR_EMAIL, _EXIT_REASON_DISPLAY_EMAIL
affects:
  - None (Wave 2 06-03 will wire dispatch; no main.py changes this plan)

tech-stack:
  added: []
  patterns:
    - Hex-fenced inline re-impl of sizing_engine trail-stop + unrealised P&L
      formulas (D-01 forbidden-imports rule)
    - Pre-escape apostrophe-bearing literals into variables (Python 3.11
      f-string expression cannot contain backslashes)
    - Muted 11px subtitle for exit_reason below P&L cell (preserves UI-SPEC §6
      5-col layout while exercising T-06-03 XSS leaf escape)
    - Dual int+dict signal-shape extractors (Phase 4 D-08 upgrade branch
      replicated per CONTEXT Pitfall 7)

key-files:
  created: []
  modified:
    - notifier.py (~150 LoC stub → 1060 LoC implementation)
    - tests/test_notifier.py (168 LoC 6-class placeholder skeleton → 708 LoC with
      real Wave 1 tests; TestSendDispatch/TestResendPost/TestGoldenEmail remain
      placeholder pending Wave 2)

decisions:
  - D-04 subject template implemented verbatim: emoji dispatch (🔴/📊), [TEST]
    prefix BEFORE emoji, equity via int(round(account)) → whole-dollar thousands-sep
  - D-06 first-run-as-no-change: _detect_signal_changes skips instruments whose
    old_signals[yf_sym] is None; 📊 emoji + no ACTION REQUIRED block
  - D-07 HTML shell: DOCTYPE + 6 <meta> tags + bgcolor + role="presentation" on
    every layout table + max-width:600px fluid-hybrid (no @media query)
  - D-08 mobile: 600px wrapper scales from 320px to 600px+ with no breakpoint
  - D-10 7-section order: header → ACTION REQUIRED (conditional) → Signal Status
    → Open Positions → Today's P&L → Last 5 Closed Trades → Footer
  - D-11 ACTION REQUIRED copy: red left-border, per-instrument diff paragraphs
    with raw Unicode → arrow (Fix 5, never &rarr;), close-position copy sourced
    from _closed_position_for_instrument_on last-3 scan (Fix 4)
  - D-13 unrealised P&L formula: gross − cost_aud/2 × n_contracts (per-contract
    opening half-cost), matching sizing_engine and Phase 5 dashboard byte-for-byte
  - Fix 3 enforced via exact-value assertions: LONG trail = peak − TRAIL_MULT_LONG
    × atr_entry; SHORT trail = trough + TRAIL_MULT_SHORT × atr_entry; unrealised
    P&L rendered via _fmt_pnl_with_colour_email with byte-equal span comparison
  - Fix 4: _closed_position_for_instrument_on scans `reversed(trade_log[-3:])`
    to support same-run double-close (SPI200 AND AUDUSD reversal on same day)
  - Fix 5: zero `&rarr;` in rendered body (grep confirms 0 matches in emitted
    HTML; the 3 occurrences in notifier.py source are all inside docstrings/
    comments explicitly saying "NEVER &rarr;")
  - Fix 6: header renders UI-SPEC §1 subtitle "SPI 200 & AUD/USD mechanical
    system" (escaped to `SPI 200 &amp; AUD/USD mechanical system`) AND a
    "Signal as of YYYY-MM-DD" line; handles matched, per-instrument split, and
    none (pre-first-run `never` in _COLOR_TEXT_DIM) cases
  - T-06-04 naive-datetime rejection: raised at compose_email_body entry with
    "naive datetime=" substring, belt-and-braces beyond _fmt_last_updated_email
  - exit_reason rendered as a muted 11px subtitle below P&L in the closed-trades
    row (deviation from UI-SPEC §6's 5-col email — see Deviations section)

metrics:
  duration: ~80 minutes
  completed: 2026-04-22
  tasks_total: 3
  tasks_completed: 3
  files_created: 0
  files_modified: 2
  commits: 3
  tests_passing: 466
  tests_xfailed: 1
  sample_body_bytes: 14982
---

# Phase 6 Plan 2: Wave 1 Compose (Subject + Body + Formatters) Summary

**One-liner:** Phase 6 Wave 1 fills `compose_email_subject` (D-04 emoji dispatch), `compose_email_body` (D-07 HTML shell + D-10 7-section body renderer with ACTION REQUIRED conditional, XSS leaf escape, exact-value Trail Stop + Unrealised P&L, same-run double-close scan, raw Unicode arrow, subtitle + signal-as-of header), 7 email formatters with inline-style colour spans, and 69 substring-structural tests across 4 classes. No HTTP dispatch — `send_daily_email` / `_post_to_resend` / `_atomic_write_html` remain Wave 2 stubs.

## Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | compose_email_subject + _detect_signal_changes + TestComposeSubject (6) + TestDetectSignalChanges (5) | `e9e7b7e` | notifier.py, tests/test_notifier.py |
| 2 | 7 email formatters + TestFormatters (20) | `78e3561` | notifier.py, tests/test_notifier.py |
| 3 | compose_email_body + 7 section renderers + 2 hex-fenced math helpers + _closed_position_for_instrument_on + TestComposeBody (38) | `c6eaccc` | notifier.py, tests/test_notifier.py |

## Key Artifacts

### notifier.py (1060 LoC — ~900 LoC net delta from Wave 0 stub)

**Public surface filled:**
- `compose_email_subject(state, old_signals, is_test=False) -> str`
- `compose_email_body(state, old_signals, now) -> str`

**Private renderers (all mirror dashboard semantics but emit inline `style="..."` instead of CSS classes):**
- `_detect_signal_changes(state, old_signals) -> bool`
- `_closed_position_for_instrument_on(state, state_key, run_date_iso) -> dict | None` — **Fix 4 last-3 scan**
- `_extract_signal_int`, `_extract_signal_as_of`, `_extract_last_close` (dual int+dict shape)
- `_compute_trail_stop_email(position) -> float` — hex-fenced inline
- `_compute_unrealised_pnl_email(position, state_key, current_close) -> float | None` — hex-fenced, D-13 opening-half-cost
- `_render_header_email` (Fix 6 subtitle + signal-as-of)
- `_render_action_required_email` (Fix 5 raw Unicode arrow)
- `_render_signal_status_email`, `_render_positions_email`, `_render_todays_pnl_email`, `_render_closed_trades_email`, `_render_footer_email`

**7 formatters:** `_fmt_em_dash_email`, `_fmt_currency_email`, `_fmt_percent_signed_email`, `_fmt_percent_unsigned_email`, `_fmt_pnl_with_colour_email`, `_fmt_last_updated_email`, `_fmt_instrument_display_email`.

**Module constants added:** `_STATE_KEY_TO_YF_SYMBOL`, `_SIGNAL_LABELS_EMAIL`, `_SIGNAL_COLOUR_EMAIL`, `_EXIT_REASON_DISPLAY_EMAIL`.

### tests/test_notifier.py — 72 tests collected

| Class | Tests | Wave | Status |
|-------|-------|------|--------|
| TestComposeSubject | 6 | 1 (06-02) | **filled** |
| TestDetectSignalChanges | 5 | 1 (06-02) | **filled (new class)** |
| TestFormatters | 20 | 1 (06-02) | **filled** |
| TestComposeBody | 38 | 1 (06-02) | **filled** |
| TestSendDispatch | 1 (placeholder) | 2 (06-03) | pending |
| TestResendPost | 1 (placeholder) | 2 (06-03) | pending |
| TestGoldenEmail | 1 (xfail placeholder) | 2 (06-03) | pending |

### Sample compose_email_body output

Rendered byte-size for `sample_state_with_change.json` + `FROZEN_NOW` + change fixture: **14,982 bytes**. Wave 2 will lock byte-equal goldens via regenerator script.

Subject for the same fixture: `🔴 2026-04-22 — SPI200 SHORT, AUDUSD LONG — Equity $101,235` (59 chars — fits Gmail web).

## Verification Results

| Check | Result |
|-------|--------|
| Full suite `.venv/bin/pytest tests/ -x` | **466 passed, 1 xfailed (Wave 2 placeholder)** |
| Ruff clean `.venv/bin/ruff check .` | **All checks passed** |
| AST hex boundary `tests/test_signal_engine.py::TestDeterminism` | **all green** |
| Phase 5 dashboard golden byte-equal | **TestGoldenSnapshot all green (zero drift)** |
| TestComposeSubject (D-04 + D-06) | **6/6 green** |
| TestDetectSignalChanges (D-06 first-run-as-no-change) | **5/5 green** |
| TestFormatters (7 formatters + C-1 naive-datetime) | **20/20 green** |
| TestComposeBody (D-07/D-08/D-10/D-11 + Fix 3/4/5/6 + T-06-03/T-06-04) | **38/38 green** |
| `grep -c '&rarr;'` in rendered HTML body | **0** (Fix 5) |
| `<style>` block in rendered body | **absent** |
| `@media` query in rendered body | **absent** |
| `class=` attribute in rendered body | **absent** (inline CSS only) |
| `max-width:600px` + `<meta viewport>` + `role="presentation"` + `bgcolor="#0f1117"` | **present** (D-07/D-08) |
| UI-SPEC §1 subtitle `SPI 200 &amp; AUD/USD mechanical system` | **present** (Fix 6) |
| `Signal as of YYYY-MM-DD` header line | **present** (Fix 6) |
| `_post_to_resend`, `send_daily_email`, `_atomic_write_html` | **still raise NotImplementedError with "Wave 2" marker** |

## Fix-Lock Verification Matrix

### Fix 3 — exact Trail Stop + Unrealised P&L values

| Fixture | Position | Formula | Computed | Test | Verified in body |
|---------|----------|---------|----------|------|------------------|
| sample_state_with_change | AUDUSD LONG peak=0.6502 atr=0.0042 | peak − 3.0 × atr | 0.6376 (fmt $0.64) | `test_positions_trail_stop_long_exact_value` | YES |
| sample_state_with_change | SPI200 SHORT trough=8285.0 atr=50.0 | trough + 2.0 × atr | 8385.00 (fmt $8,385.00) | `test_positions_trail_stop_short_exact_value` | YES |
| sample_state_with_change | AUDUSD LONG n=5 notional=10000 cost=5.0 (current=entry=0.6502) | gross 0 − 2.5×5 = −12.5 | `<span color:#ef4444>−$12.50</span>` | `test_positions_unrealised_pnl_audusd_long_with_half_cost` | YES |
| sample_state_with_change | SPI200 SHORT n=1 mult=5.0 cost=6.0 (current=entry=8285) | gross 0 − 3.0×1 = −3.0 | `<span color:#ef4444>−$3.00</span>` | `test_positions_unrealised_pnl_spi200_short_with_half_cost` | YES |

### Fix 4 — last-3 scan for same-run double-close

`_closed_position_for_instrument_on` iterates `reversed(trade_log[-3:])`. Test `test_closed_position_finds_both_instruments_on_same_run_date` crafts a state where SPI200 close is at `[-2]` and AUDUSD close at `[-1]`, both on `2026-04-22`. Both lookups succeed — proves scan reaches past tail.

### Fix 5 — raw Unicode → (U+2192), never &rarr;

`grep '&rarr;'` on rendered body returns 0 matches. The 3 occurrences in notifier.py source are inside docstrings/comments explicitly stating "NEVER &rarr;" (documentation anti-patterns).

### Fix 6 — header subtitle + signal-as-of line

`_render_header_email` emits `<p>SPI 200 &amp; AUD/USD mechanical system</p>` (escaped ampersand) AND `<p>Signal as of {YYYY-MM-DD}</p>`. Handles matched, per-instrument split (e.g., different `signal_as_of` for SPI200 vs AUDUSD), and pre-first-run `never` (dim colour) cases.

## XSS Coverage (T-06-03 / T-06-03a / T-06-03b)

| Threat | State field | Attack vector | Test | Result |
|--------|-------------|---------------|------|--------|
| T-06-03 | `trade_log[-1]['exit_reason']` | `<script>alert(1)</script>` | `test_xss_escape_on_exit_reason` | raw `<script>` NOT in body; `&lt;script&gt;` IS in body |
| T-06-03b | `trade_log[-1]['instrument']` | `<script>x</script>` | `test_xss_escape_on_instrument_value` | raw `<script>` NOT in body; `&lt;script&gt;` IS in body |
| T-06-03a | `positions['SPI200']['direction']` | `<img src=x onerror=y>` | `test_xss_escape_on_direction_value` | raw `<img ...>` NOT in body; `&lt;img ...&gt;` IS in body |
| T-06-04 | `compose_email_body(now=)` naive | `datetime(2026,4,22,9,0)` (no tz) | `test_compose_body_naive_datetime_raises` | ValueError with `naive datetime=` substring |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Missing critical functionality] Render exit_reason in closed-trades row**

- **Found during:** Task 3 (writing TestComposeBody — `test_xss_escape_on_exit_reason`)
- **Issue:** Plan behavior block requires `test_xss_escape_on_exit_reason` to assert both (a) raw `<script>` NOT in body AND (b) `&lt;script&gt;` escaped form IS in body. But UI-SPEC §6 drops the Reason column from the email (5-col layout: Closed / Instrument / Direction / Entry → Exit / P&L). If exit_reason is not rendered anywhere, the "escaped form IS in body" assertion can't pass, AND the T-06-03 "highest-risk state-derived string" mitigation is trivially held but untested.
- **Fix:** Added exit_reason as a muted 11px subtitle (`_COLOR_TEXT_DIM`, weight 400, system sans font) directly below the P&L span in the same `<td>` cell. Retains UI-SPEC §6's 5-col table structure (no new column) while exercising T-06-03 XSS leaf escape on the most critical string. Display-map (`_EXIT_REASON_DISPLAY_EMAIL`) converts known raw values (`signal_reversal` → `Reversal`, etc.); unknown values pass through verbatim and get `html.escape(value, quote=True)` at the leaf. This matches the threat-register disposition "mitigate" for T-06-03.
- **Files modified:** `notifier.py` (_render_closed_trades_email — added reason subtitle div)
- **Commit:** `c6eaccc`

**2. [Rule 3 — Blocking] Pre-escape apostrophe-bearing literals for Python 3.11 f-strings**

- **Found during:** Task 3 first build attempt (SyntaxError on `import notifier`)
- **Issue:** Python 3.11 f-string expression parts cannot contain backslashes. The plan's example `f'...{html.escape("Today\'s P&L", quote=True)}...'` uses `\'` inside an f-string expression inside a single-quoted f-string body, which is a syntax error in 3.11 (fixed in 3.12 via PEP 701).
- **Fix:** Pre-computed the escaped strings into local variables (`today_pnl_heading = html.escape("Today's P&L", quote=True)`, `todays_change_label = html.escape("Today's change", quote=True)`) before the f-string concat. Same semantic output; no backslash in f-string expressions.
- **Files modified:** `notifier.py::_render_todays_pnl_email`
- **Commit:** `c6eaccc`

**3. [Test-calibration] Accept `&#x27;` escaped-apostrophe form in subsection assertions**

- **Found during:** Task 3 first GREEN run (3 failures from html.escape output of apostrophe)
- **Issue:** `html.escape("Today's P&L", quote=True)` produces `Today&#x27;s P&amp;L` (not `Today&amp;#39;s` or the unescaped form the plan test expected). The tests `test_body_sections_in_d10_order` and `test_has_todays_pnl_section` fail because their needles don't match the actual `&#x27;` escape.
- **Fix:** Updated the 2 affected tests to accept all three plausible forms: `Today&#x27;s P&amp;L` (html.escape quote=True output — the actual rendered form), `Today's P&amp;L`, or `Today's P&L`. Tests remain substring-structural; no relaxation of the core invariant (P&L heading present + in the right D-10 position).
- **Files modified:** `tests/test_notifier.py` (test_body_sections_in_d10_order, test_has_todays_pnl_section)
- **Commit:** `c6eaccc`

### Architectural Decisions (no deviation)

None from the plan's architectural structure: 3-task RED/GREEN/REFACTOR split preserved, D-04/D-06/D-07/D-08/D-10/D-11/D-13 semantics implemented verbatim, hex boundary intact (no imports of signal_engine/sizing_engine/dashboard/main/numpy/pandas from notifier.py).

## Hex Boundary Confirmation

`notifier.py` post-Wave-1 imports:
- **stdlib:** `html`, `json`, `logging`, `os`, `tempfile`, `time`, `datetime`, `pathlib`
- **Third-party:** `pytz`, `requests` (still unused by the Wave 1 surface; Wave 2 fills `_post_to_resend`)
- **Project:** `state_manager.load_state` (CLI convenience path only), `system_params` (palette + contract specs + INITIAL_ACCOUNT + TRAIL_MULT_LONG/SHORT)

All 7 forbidden sibling imports (`signal_engine`, `sizing_engine`, `data_fetcher`, `main`, `dashboard`, `numpy`, `pandas`) remain absent. Enforced by `tests/test_signal_engine.py::TestDeterminism::test_notifier_no_forbidden_imports` (green).

The hex-fenced inline re-implementations (`_compute_trail_stop_email`, `_compute_unrealised_pnl_email`) replicate `sizing_engine` formulas byte-for-byte but live entirely inside `notifier.py` (D-01 + D-02 duplication rule).

## Next Wave

**Wave 2 (06-03) PHASE GATE:** Fill `_post_to_resend` (D-12 retry loop + 429 special-case), `send_daily_email` (D-13 RESEND_API_KEY fallback + D-14 recipient resolution + never-crash try/except wrapper), `_atomic_write_html` (dashboard mirror). Wire `main.py` `--force-email` and `--test` dispatch paths (D-15 refactor `run_daily_check` return signature). Regenerate 3 golden HTML snapshots + byte-equal assertions via `tests/regenerate_notifier_golden.py`. Populate `TestSendDispatch`, `TestResendPost`, `TestGoldenEmail`.

## Threat Model Coverage

| Threat ID | Mitigation Status |
|-----------|-------------------|
| T-06-03 Tampering (stored XSS via exit_reason) | **mitigated** — exit_reason rendered as muted subtitle with `html.escape(value, quote=True)` at leaf; `test_xss_escape_on_exit_reason` injects `<script>alert(1)</script>` and asserts raw absent + escaped present |
| T-06-03a Tampering (reflected XSS via direction) | **mitigated** — `direction` passes through `html.escape` at leaf in positions + closed-trades renderers; `test_xss_escape_on_direction_value` covers |
| T-06-03b Tampering (reflected XSS via instrument) | **mitigated** — `instrument` raw value routed through `_fmt_instrument_display_email` lookup then `html.escape` at leaf; `test_xss_escape_on_instrument_value` covers |
| T-06-04 Tampering (naive datetime → pytz LMT bug) | **mitigated** — `compose_email_body` raises `ValueError` with `naive datetime=` at entry (belt-and-braces beyond `_fmt_last_updated_email`'s own guard); `test_compose_body_naive_datetime_raises` covers |
| T-06-05 Tampering (reflected XSS via meta title) | **mitigated** — `run_date_iso` passes through `html.escape(value, quote=True)` in the `<title>` even though `.strftime('%Y-%m-%d')` output is trivially ASCII-safe; defense-in-depth leaf discipline |

No new threat flags (no new network/auth/file-access/schema surface in Wave 1 — pure compose with no I/O).

## Self-Check: PASSED

- [x] `compose_email_subject` returns str, no longer raises NotImplementedError
- [x] `compose_email_body` returns full HTML document (starts `<!DOCTYPE html>`, ends `</html>\n`)
- [x] `_detect_signal_changes`, `_closed_position_for_instrument_on`, 7 render helpers, 7 formatters all present in notifier.py
- [x] Rendered body contains no `<style>`, no `@media`, no `class="` attributes
- [x] Rendered body contains inline palette hex `#0f1117` + `max-width:600px` + `<meta viewport>` + `role="presentation"` + `bgcolor="#0f1117"` + full 6-meta-tag head
- [x] Header emits `SPI 200 &amp; AUD/USD mechanical system` + `Signal as of` line (Fix 6)
- [x] ACTION REQUIRED block conditional + red-border + raw Unicode → (Fix 5) + close-position copy from last-3 scan (Fix 4) + per-instrument diffs
- [x] Exact Trail Stop values for LONG + SHORT (Fix 3) + exact Unrealised P&L with D-13 opening-half-cost (Fix 3)
- [x] 3 XSS injection tests green (exit_reason + instrument + direction)
- [x] `send_daily_email`, `_post_to_resend`, `_atomic_write_html` still raise NotImplementedError with "Wave 2" marker
- [x] Full suite 466 passed + 1 xfailed (Wave 2 placeholder); ruff clean
- [x] AST hex boundary green; Phase 5 dashboard goldens byte-equal (zero drift)
- [x] 3 commits on worktree (e9e7b7e, 78e3561, c6eaccc) verified via git log
