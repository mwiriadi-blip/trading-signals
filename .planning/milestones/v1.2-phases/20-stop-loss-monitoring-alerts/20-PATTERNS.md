# Phase 20: Stop-Loss Monitoring & Alerts — Pattern Map

**Mapped:** 2026-04-30
**Files analysed:** 20 new symbols / files (per CONTEXT §Files-to-modify + RESEARCH §Recommended Project Structure)
**Analogs found:** 17 / 20 with strong in-repo precedent. 3 require design-from-scratch (flagged).

## File Classification

| New symbol / file | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `_migrate_v6_to_v7` | migration | transform | `state_manager._migrate_v5_to_v6` (Phase 19) | exact |
| `MIGRATIONS[7] = ...` | dispatch entry | config | `state_manager.MIGRATIONS[6]` (Phase 19) | exact |
| `STATE_SCHEMA_VERSION = 7` bump | constant | config | `system_params.py:121` (Phase 19 set 6) | exact |
| **NEW MODULE** `alert_engine.py` (`compute_alert_state`, `compute_atr_distance`) | pure-math hex | transform | `pnl_engine.py` (Phase 19) | exact |
| `notifier.send_stop_alert_email` | I/O hex | request-response (HTTPS) | `notifier.send_magic_link_email` (Phase 16.1) | exact |
| `notifier._render_alert_email_html` | render helper | transform | `notifier._render_magic_link_html` | exact |
| `notifier._render_alert_email_text` | render helper | transform | `notifier._render_magic_link_text` | exact |
| `main._evaluate_paper_trade_alerts` | orchestrator | event-driven | NEW pattern (no in-repo precedent for two-phase commit) | partial — see flag |
| `dashboard._render_alert_badge` | render helper | transform | `dashboard._mom_badge` (Phase 17) + `.badge-manual` site (Phase 14) | role-match |
| `_render_paper_trades_open` Alert column extension | render helper | transform | `dashboard._render_paper_trades_open` (Phase 19, self-extension) | exact |
| Inline CSS additions (`.alert-badge`, `.alert-{clear,approaching,hit,none}`, `@media`) | CSS | static | `dashboard._INLINE_CSS` `.badge` block (lines 518–532) | exact |
| `web/routes/paper_trades.py` PATCH closure extension | web adapter | request-response | `web/routes/paper_trades.py::edit_paper_trade._apply` (Phase 19 lines 314–342) | exact |
| `tests/test_state_manager.py::TestMigrateV6ToV7` | unit test | n/a | `tests/test_state_manager.py::TestMigrateV5ToV6` (line 2367) | exact |
| **NEW FILE** `tests/test_alert_engine.py` | unit test file | n/a | `tests/test_pnl_engine.py` | exact |
| **NEW FILE** `tests/test_notifier_stop_alert.py` | unit test file | n/a | `tests/test_notifier_magic_link.py` | exact |
| **NEW FILE** `tests/test_main_alerts.py` | integration test | n/a | `tests/test_main.py::TestOrchestrator` + `TestEmailNeverCrash` | role-match |
| `tests/test_dashboard.py::TestRenderAlertBadge` | unit test class | n/a | `tests/test_dashboard.py::TestRenderManualStopBadge` (line 1399) | exact |
| `tests/test_web_paper_trades.py::test_edit_resets_last_alert_state` | integration test | n/a | `tests/test_web_paper_trades.py::TestEditPaperTrade` (line 274) | exact |
| **NEW FIXTURE** `tests/fixtures/state_v7_with_alerts.json` | test fixture | n/a | `tests/fixtures/state_v6_with_paper_trades.json` (Phase 19) | exact |
| `FORBIDDEN_MODULES_STDLIB_ONLY` AST-walk extension | test config | n/a | `tests/test_signal_engine.py:480,593,595` (Phase 19 added pnl_engine.py) | exact |

## Pattern Assignments

### `_migrate_v6_to_v7` in `state_manager.py`

**Closest analog:** `state_manager.py:215` — `_migrate_v5_to_v6` (Phase 19)
**Why this analog:** Identical shape — single-field-add migration, idempotent guard via `'X' not in row`, defensive `isinstance(row, dict)`, D-15 silent (no `append_warning`, no log line). Phase 20 also adds a single field per `paper_trades[]` row.
**Pattern to copy:**
- Loop `for row in s.get('paper_trades', []):` (skip if key missing)
- Idempotency guard `if isinstance(row, dict) and 'last_alert_state' not in row:`
- Stamp `row['last_alert_state'] = None` (None default per D-05)
- Return `s` (in-place mutation)
- Docstring: "Phase 20 (v1.2): introduce ... — D-15 silent migration"
**Pattern to adapt:**
- Phase 19 mutated top-level (`s['paper_trades'] = []`); Phase 20 walks each row inside the list — closer in shape to `_migrate_v3_to_v4` / `_migrate_v4_to_v5` which also loop signal rows. Use the per-row `isinstance(row, dict) and 'X' not in row` guard for defence.
**Hex-boundary check:** clean — state_manager only.

### `MIGRATIONS[7]` dispatch entry

**Closest analog:** `state_manager.py:229–236` — `MIGRATIONS` dict (Phase 19 added key 6)
**Why this analog:** Same dispatch dict; Phase 20 simply appends `7: _migrate_v5_to_v6`-style entry.
**Pattern to copy:**
- Add line `7: _migrate_v6_to_v7,` between key `6` and dict close
- Trailing-comma style preserved
- Inline comment: `# Phase 20 D-08: last_alert_state on paper_trades[] rows`
**Pattern to adapt:** none — verbatim shape.
**Hex-boundary check:** clean.

### `STATE_SCHEMA_VERSION = 7` bump

**Closest analog:** `system_params.py:121` (current value `6`)
**Why this analog:** Phase 19 set this to 6 with an inline-comment audit trail. Phase 20 follows the same trail-extension idiom.
**Pattern to copy:**
- Replace `6` with `7`
- Append to inline comment: `; Phase 20 → v7 (last_alert_state on paper_trades[] rows; D-08)`
**Pattern to adapt:** none.
**Hex-boundary check:** clean — `system_params.py` is constants-only.

### **NEW MODULE** `alert_engine.py`

**Closest analog:** `pnl_engine.py` (Phase 19)
**Why this analog:** Same pure-math hex tier. Same import constraint (math + typing only — see `tests/test_pnl_engine.py:144`). Same NaN-policy posture (NaN propagates / safe default). Same caller-side adapter rule (callers supply scalar args; module reads no env, no clock, no I/O).
**Pattern to copy:**
- Module docstring shape (architecture note + forbidden imports list verbatim from `pnl_engine.py:1–17`)
- `import math` only (typing optional via `from typing import ...`)
- Two top-level functions, plain `(args) -> float|str` signatures
- NaN-safe: short-circuit `if any(math.isnan(v) for v in (...)): return 'CLEAR'` (D-10) before main logic
- `if atr <= 0: return 'CLEAR'` divide-by-zero guard (mirrors RESEARCH §Pattern 5)
**Pattern to adapt:**
- pnl_engine returns `float`; alert_engine.compute_alert_state returns `str` (Literal['CLEAR'|'APPROACHING'|'HIT']) and compute_atr_distance returns `float` (with NaN sentinel on zero/NaN ATR per D-10)
- HIT precedence over APPROACHING (D-10) — encoded as ordered if-branches LONG/SHORT first, then APPROACHING threshold
**Hex-boundary check:** clean — must satisfy `FORBIDDEN_MODULES_STDLIB_ONLY` (`tests/test_signal_engine.py:502`). AST guard extension required (see below).

### `notifier.send_stop_alert_email`

**Closest analog:** `notifier.py:1699` — `send_magic_link_email` (Phase 16.1)
**Why this analog:** Only existing notifier function that passes BOTH `html_body` AND `text_body` simultaneously to `_post_to_resend` — exactly Phase 20's D-02 requirement. `send_daily_email` is HTML-only; `send_crash_email` is text-only. Magic-link is the unique two-body precedent. Same never-crash posture, same per-send `os.environ.get('SIGNALS_EMAIL_FROM', '').strip()` read with missing-sender early return (matches CLAUDE.md "Email sends NEVER crash").
**Pattern to copy:**
- Per-send `from_addr` env read at top + early `SendStatus(ok=False, reason='missing_sender')` return on missing (lines 1718–1723)
- Build `subject`, `html_body`, `text_body` via parallel render helpers
- `api_key` env read; if missing → write `last_email.html` fallback + return `SendStatus(ok=True, reason='no_api_key')` (lines 1729–1745)
- Try/except triple: `ResendError` (logged warning, return False), bare `Exception` (CLAUDE.md never-crash, return False), success path returns True
- All log lines use `[Email]` tag (existing notifier convention) — but **CONTEXT §D-06 explicitly requires `[Alert]` tag** for the alert-specific WARN log; the in-notifier logger calls can stay `[Email]` for transport, while the orchestrator (`main._evaluate_paper_trade_alerts`) emits the `[Alert] WARN ...` line. Confirm with planner.
- `_post_to_resend(api_key=..., from_addr=..., to_addr=..., subject=..., html_body=..., text_body=...)` — both bodies passed as kwargs (see line 1748–1755)
**Pattern to adapt:**
- Return type: D-13 specifies `bool` (not `SendStatus`). Either return `bool` directly (simplest, matches D-13 verbatim) OR return `SendStatus` and document the caller unwraps `.ok`. **Recommendation: return `bool` per D-13 to keep the orchestrator branch simple.**
- Recipient: D-02 says `SIGNALS_EMAIL_TO` (operator inbox), NOT `to_email` argument. Read `os.environ.get('SIGNALS_EMAIL_TO', _EMAIL_TO_FALLBACK)` (mirror `send_daily_email:1492`).
- Subject: D-02 conditional on `len(transitions)`: `[!stop] {N} transition(s) ...` for N>1 vs `[!stop] <INST> <SIDE> <STATE> — <id>` for N==1. Build via helper `_build_alert_subject(transitions)` per RESEARCH §Code Examples.
**Hex-boundary check:** clean — notifier.py adapter, already imports `requests`, `os`, `system_params`, `html`. New imports: none required (all needed stdlib already imported).

### `notifier._render_alert_email_html`

**Closest analog:** `notifier.py:1644` — `_render_magic_link_html`
**Why this analog:** Inline-CSS HTML email body, `html.escape(value, quote=True)` on every interpolated field, Phase 6 D-15 leaf-discipline. Same dark-theme palette imports from `system_params` (`_COLOR_BG`, `_COLOR_SURFACE`, etc., lines 1661–1664 in `_render_magic_link_html`).
**Pattern to copy:**
- `from html import escape as html_escape` at top of function (Phase 16.1 idiom; alternative: module-level `html.escape` already imported at notifier:48)
- Every dynamic value escaped: `esc_id = html.escape(str(value), quote=True)`
- Inline `style="..."` on every span/td — NEVER `class="..."` (notifier:32 module-doc convention)
- Inline-CSS table: `<table style="border-collapse:collapse;width:100%;">` etc.
- Distance text format: `f"{atr_distance:.2f} ATR (within trigger | beyond stop)"` per D-02
- Badge in email body uses inline-style colour map (RESEARCH §Code Examples) — separate from dashboard CSS classes. Concrete map:
  - CLEAR → `style="background:#d4edda;color:#155724;..."`
  - APPROACHING → `style="background:#fff3cd;color:#856404;..."`
  - HIT → `style="background:#f8d7da;color:#721c24;..."`
**Pattern to adapt:**
- Magic-link is single-link body; alert email is variable-N table — iterate `transitions` and build `<tr>` per entry
- Distance format new (no analog in magic-link). Use compute_atr_distance result + status string.
**Hex-boundary check:** clean — pure string assembly, no I/O.

### `notifier._render_alert_email_text`

**Closest analog:** `notifier.py:1686` — `_render_magic_link_text`
**Why this analog:** Plain-text fallback rendered from same input as HTML body. Used by same dispatch function (`send_magic_link_email`). RESEARCH §Pitfall 2 explicit: parallel render, NOT HTML-stripper.
**Pattern to copy:**
- Plain string assembly with `\n` separators
- No HTML escape (text/plain MIME → no entity decoding)
- Same `transitions` argument for parity (test asserts both bodies contain every `id` + `new_state`)
- Header line + per-transition fixed-width row
**Pattern to adapt:**
- Magic-link text body is 5 lines flat; alert text body is a fixed-width table. Use `f"{id:<24} {side:<6} {state:<12} {distance:.2f} ATR"` formatting.
**Hex-boundary check:** clean.

### `main._evaluate_paper_trade_alerts` orchestrator

**Closest analog (partial):** `main.py:1393–1404` — `_apply_daily_run` closure pattern + `main.py:1648` — `_apply_reset` second `mutate_state` call
**Why this analog (partial):** No single in-repo function does send → conditional commit. The closest precedents are the daily-run closure (writing-after-load idiom) and `_handle_reset` (a SECOND mutate_state call that follows a different control-flow path). RESEARCH §Pattern 2 is explicit: this is design-from-scratch, anchored on those two precedents. **FLAG: design from scratch.**
**Pattern to copy:**
- Use `state_manager.mutate_state(_commit_transitions)` for the second-phase write (`_apply_reset` at `main.py:1648` is the precedent for "second mutate_state call from main")
- Closure-variable pattern (`_accumulated = state` at line 1392) — NOT the closure return value, which mutate_state ignores per `state_manager.py:679`
- `[Alert]` log prefix (CLAUDE.md §Conventions; new tag mentioned in CONTEXT §risk-register)
- Local imports for cross-hex calls: `from notifier import send_stop_alert_email` LOCAL inside the function (RESEARCH §Pattern 2 + Phase 11 C-2 LOCAL-import idiom — see `dashboard.py:2314` `from pnl_engine import compute_unrealised_pnl` precedent)
**Pattern to adapt:**
- **Two-phase commit (NEW):** RESEARCH §Pattern 2 + Pitfall 1 are explicit — NEVER call `mutate_state` inside an outer `mutate_state` closure (POSIX flock deadlock at `state_manager.py:332-340`). Therefore `_evaluate_paper_trade_alerts` MUST be called from `run_daily_check` at line ~1404 **AFTER** `state = state_manager.mutate_state(_apply_daily_run)` returns and **BEFORE** `_render_dashboard_never_crash(state, ...)` at line 1421. Inside it, optionally a FIRST `mutate_state` call writes None→CLEAR no-op states; on send-success a SECOND `mutate_state` writes the transitioning rows. Two sequential mutate_state calls are legal (lock acquired/released between calls — Phase 14 D-13).
- **Read OHLC bar:** use `state['signals'][inst]['ohlc_window'][-1]` for today's bar (RESEARCH §Pitfall 5 — ascending date order from `df.tail(40)` at `main.py:1280`). Keys `low`/`high`/`close` lowercase per `main.py:1284-1287`.
- **Read ATR:** `state['signals'][inst]['indicator_scalars'].get('atr', float('nan'))` (RESEARCH §Pitfall 6 — empty dict on first run after migration). Emit `[Alert] WARN no ATR for %s; treating as CLEAR` if missing.
- Return shape `{'transitions': [...], 'emailed': bool}` per CONTEXT D-12.
**Hex-boundary check:** main.py is the orchestrator and may import `alert_engine` (consistent with its existing `signal_engine` / `state_manager` / `notifier` imports). Verify `FORBIDDEN_MODULES_MAIN` (`tests/test_signal_engine.py:546`) is unchanged — it forbids only `numpy/yfinance/requests/pandas`, none of which alert_engine uses.

### `dashboard._render_alert_badge`

**Closest analog:** `dashboard.py:1400` — `_mom_badge` helper inside `_render_trace_vote` (Phase 17)
**Why this analog:** Phase 17 introduced inline `<span class="trace-badge plus|minus|zero|pass|fail">` helpers — the closest precedent in dashboard.py for "render colored badge from an enum-like state". `_render_paper_trades_open` (line 2300) is the host where the new column slot in.
**Pattern to copy:**
- One-line `<span class="alert-badge alert-{state.lower()}">{html.escape(state)}</span>` shape (mirrors `<span class="trace-badge plus">+</span>` at line 1402)
- `html.escape` on the user-facing state text (defence-in-depth even though state is enum-bounded)
- CSS class names follow Phase 17 pattern `<surface>-badge <surface>-<modifier>` — i.e. `alert-badge alert-clear` (not `alert alert-clear`)
- Empty / None branch returns `'<span class="alert-badge alert-none" title="...">—</span>'` — em-dash placeholder mirrors `_fmt_em_dash()` at line 744 + Phase 14 stop-cell None render at line 1672
**Pattern to adapt:**
- Two arguments `(state: str | None, has_stop: bool)` per D-14 — Phase 17's `_mom_badge` takes only `(val: float)`. The two-state branching (`has_stop` controls "no stop set" tooltip, `state is None` controls "awaiting next daily run" tooltip) is new — keep both branches explicit per D-14 verbatim.
**Hex-boundary check:** dashboard.py adds `from alert_engine import compute_alert_state` if it computes; per D-11 the render path reads `last_alert_state` directly from the row dict — NO live computation in render. Therefore **dashboard.py does NOT need to import alert_engine** (re-confirm with planner; if the badge renderer is render-only, no import needed). If a future helper computes badge state in render, the import would mirror `dashboard.py:2314` LOCAL `from pnl_engine import compute_unrealised_pnl`. **`alert_engine` is NOT in `FORBIDDEN_MODULES_DASHBOARD`** (line 558–571) — same as `pnl_engine` precedent.

### `_render_paper_trades_open` Alert column extension

**Closest analog:** `dashboard.py:2300–2401` — same function (self-extension, Phase 19)
**Why this analog:** The function already iterates `open_rows` and emits 9 `<td>` cells per row (line 2364–2385). Phase 20 adds a 10th `<td>` for the alert badge.
**Pattern to copy:**
- Keep the `for row in open_rows:` loop structure
- Insert `<td>{alert_badge_html}</td>` after the existing `Stop` cell at line 2371 (placement choice — confirm with planner)
- Update the `<thead>` row at line 2392–2394 to add `<th>Alert</th>`
- Update the empty-state colspan at line 2326 from `colspan="9"` to `colspan="10"`
- Compute `alert_badge_html = _render_alert_badge(row.get('last_alert_state'), row.get('stop_price') is not None)`
**Pattern to adapt:**
- Phase 19 added paper-trades-open as a fresh table; Phase 20 extends in place. Same self-extension idiom as Phase 17 trace-panel additions.
**Hex-boundary check:** clean.

### Inline CSS additions (`.alert-badge`, `.alert-{clear,approaching,hit,none}`, `@media`)

**Closest analog:** `dashboard.py:518–532` — `.badge` + `.badge-manual` block inside `_INLINE_CSS`
**Why this analog:** Phase 14 inline CSS for `.badge-manual` is the existing single-class-modifier pattern. Phase 17 added `.trace-badge.plus|minus|zero|pass|fail` (line 699–704) — multi-modifier pattern closer to the 4-state alert badge.
**Pattern to copy:**
- Insert new CSS rules inside the f-string `_INLINE_CSS` block at line 196 (use `{{`/`}}` for literal braces — the block is f-string-formatted)
- Place near the existing `.badge` declarations at line 518–532 OR near `.trace-badge` at line 699–704
- Same property set as CONTEXT D-14: `padding`, `border-radius`, `font-weight`, `font-size` on `.alert-badge`; `background` + `color` on each modifier
- `@media (max-width: 640px)` follows existing pattern in `_INLINE_CSS` (mobile breakpoints already exist — grep `@media` in dashboard.py to confirm placement)
**Pattern to adapt:**
- D-14 uses raw hex colours `#d4edda` etc. (Bootstrap-flavoured semantic palette) instead of the dashboard's `--color-long`/`--color-short` CSS vars. Confirm with planner: should they reuse `var(--color-long)` etc. for consistency, or stick to the operator-locked D-14 palette? **Recommendation: keep D-14 hex values verbatim — operator-locked.**
**Hex-boundary check:** clean — pure CSS string concatenation.

### `web/routes/paper_trades.py` PATCH closure extension

**Closest analog:** `web/routes/paper_trades.py:307–353` — `edit_paper_trade._apply` closure (Phase 19 D-12)
**Why this analog:** Phase 19's PATCH handler already has the closure shape. Phase 20 adds one line inside it.
**Pattern to copy:**
- Keep the existing `_apply(state)` closure body
- After all field updates, add `row['last_alert_state'] = None` (D-15: regardless of which field changed)
- The kwarg-default-trap pattern at line 316 (`from system_params import STRATEGY_VERSION  # noqa: PLC0415 — fresh import (kwarg trap)`) does NOT apply here since None is a literal, not a captured constant — but cite LEARNING 2026-04-29 in the plan to surface that the operator is aware
**Pattern to adapt:**
- Single new line inside an existing closure — minimal extension.
**Hex-boundary check:** clean — web/routes/paper_trades.py already imports `state_manager.mutate_state`; no new imports.

### `tests/test_state_manager.py::TestMigrateV6ToV7`

**Closest analog:** `tests/test_state_manager.py:2367` — `TestMigrateV5ToV6` (Phase 19)
**Why this analog:** The class docstring already enumerates the canonical invariants for single-field migrations (line 2370–2376): "backfill, idempotent, idempotent-via-full-walker, schema-advances, additive, full v0→vN walk".
**Pattern to copy:**
- Six-test structure (mirror line 2379, 2411, 2437, 2459, 2488 + a full v0→v7 walker test)
- Direct call: `_migrate_v6_to_v7(dict(s))` with v6 fixture missing `last_alert_state` → assert stamped None on every row
- Idempotent: pre-populated `last_alert_state: 'APPROACHING'` MUST NOT be overwritten
- Walker: full `_migrate(dict(s))` from `schema_version: 0` walks to 7
- "preserves other fields" test asserts every original key+value is intact
**Pattern to adapt:**
- Phase 19 tested top-level `paper_trades=[]` stamp; Phase 20 tests per-row `last_alert_state=None` stamp on EVERY existing row. Use a 2-row fixture and verify both rows get stamped.
**Hex-boundary check:** clean.

### **NEW FILE** `tests/test_alert_engine.py`

**Closest analog:** `tests/test_pnl_engine.py` (entire file, 158 lines)
**Why this analog:** Same module shape — pure-math two-function unit test file with `Test<Func>` per function + `TestEngineHexBoundary` AST-walk class.
**Pattern to copy:**
- Module docstring shape (line 1–12)
- `_CASES` parametrize tuple-list at module level + `class.test_<func>` parametrize-id pattern (line 26–63)
- AST-walk hex-boundary test (line 131–148): assert imports ⊆ `{'math', 'typing', 'system_params', '__future__'}`
- Public-surface callable assertion (line 150–157)
- NaN propagation test using `float('nan')` (line 65–73)
**Pattern to adapt:**
- Replace `compute_unrealised_pnl` cases with `compute_alert_state` cases:
  - HIT precedence: LONG with `today_low <= stop_price` → 'HIT' even if also APPROACHING-eligible
  - HIT precedence: SHORT with `today_high >= stop_price` → 'HIT'
  - APPROACHING: `abs(today_close - stop_price) <= 0.5 * atr` and not HIT → 'APPROACHING'
  - CLEAR: default
  - LONG/SHORT asymmetry: same numerics, opposite side switches HIT branch
- NaN test → `@pytest.mark.parametrize('nan_field', [...])` per RESEARCH §Code Examples line 432–445
- `compute_atr_distance` cases: positive distance, NaN-on-zero-ATR, NaN-on-NaN-ATR
**Hex-boundary check:** clean.

### **NEW FILE** `tests/test_notifier_stop_alert.py`

**Closest analog:** `tests/test_notifier_magic_link.py` (entire file, ~210 lines)
**Why this analog:** Only existing test file for a notifier function that uses both `html_body` AND `text_body`. Same `_post_to_resend` monkeypatch-and-capture idiom is exactly what Phase 20 needs.
**Pattern to copy:**
- `_isolate_email_env(monkeypatch, tmp_path)` autouse-style fixture at line 32–41 — sets `SIGNALS_EMAIL_FROM` + `RESEND_API_KEY` + chdir to tmp_path
- `monkeypatch.setattr(notifier, '_post_to_resend', _fake_post)` capture pattern (line 58)
- `captured.update(kwargs)` to grab `subject`, `html_body`, `text_body`, `to_addr`
- `test_resend_post_body_shape_to_subject_html_text_present` (line 47): assert HTML AND text bodies present, subject literal
- `test_html_body_link_is_html_escaped` (line 93): malicious-input → assert `&amp;` and absence of raw `<script>` (XSS defense per D-13)
- `test_resend_failure_returns_send_status_ok_false_no_raise` (line 158): force `_post_to_resend` to raise `ResendError` → assert return is False/`SendStatus(ok=False)`, no exception propagates
- `test_unexpected_exception_is_caught` (line 175): bare `Exception` → still returns False
- `test_missing_resend_api_key_falls_back_to_last_email_html` (line 188): unset env → fallback path
- `test_missing_signals_email_from_returns_send_status_ok_false` (line 205): unset env → early return
**Pattern to adapt:**
- Add N=0 / N=1 / N=3 transition-list parametrize: assert N=0 → no `_post_to_resend` call; N=1 → subject is `[!stop] <INST> <SIDE> <STATE> — <id>`; N=3 → subject is `[!stop] 3 transition(s) ...`
- Plain-text/HTML drift test (RESEARCH §Pitfall 2): build `transitions` of size 3, assert every transition's `id` + `new_state` appears in BOTH `html_body` AND `text_body`
- XSS defense test: pass a transition with `id='SPI200-X<script>alert(1)</script>'` (impossible per Phase 19 D-01 regex, but defence-in-depth) → assert `<script>` literal absent from both bodies
- Return-type adaptation: if `send_stop_alert_email` returns `bool` (D-13) instead of `SendStatus`, adjust assertions (`assert result is True` instead of `.ok is True`)
**Hex-boundary check:** clean.

### **NEW FILE** `tests/test_main_alerts.py`

**Closest analog (composite):** `tests/test_main.py::TestOrchestrator` (line 490) + `TestEmailNeverCrash` (line 1050)
**Why this analog:** TestOrchestrator covers `run_daily_check` integration with mocked transports; TestEmailNeverCrash covers the never-crash invariant on email failure. `_evaluate_paper_trade_alerts` integration sits at the same layer.
**Pattern to copy:**
- Mocked `state_manager.load_state` / `mutate_state` to inject a fixture state
- Monkeypatch `notifier.send_stop_alert_email` to return True / False / raise
- Capture writes via fake mutate_state (mirror `client_with_state_v6` `captured_saves` idiom from `tests/test_web_paper_trades.py:282`)
- One test per scenario: state-transition detection (CLEAR→APPROACHING fires email), dedup (APPROACHING→APPROACHING no email), edit-reset interaction (None→APPROACHING after PATCH-reset fires email), send-failure rollback (transitioning rows' last_alert_state unchanged on send=False), ordering (alert eval after signal persistence, before dashboard render)
**Pattern to adapt:**
- New: assert ordering inside `run_daily_check` — the `_evaluate_paper_trade_alerts` call site lands BETWEEN the `mutate_state(_apply_daily_run)` return at main.py:1404 and `_render_dashboard_never_crash` at line 1421. Verify via call-order capture (sequence of monkeypatched callables).
- Two-phase commit: build a state where N=2 transitions, mock send to return False, assert both rows' `last_alert_state` on disk equals their PRIOR value (not the new state). Then mock send to return True, assert both rows' `last_alert_state` equals the new state.
**Hex-boundary check:** clean.

### `tests/test_dashboard.py::TestRenderAlertBadge`

**Closest analog:** `tests/test_dashboard.py:1399` — `TestRenderManualStopBadge`
**Why this analog:** Same shape — render the dashboard, assert badge HTML is present/absent based on the state field. Phase 14 manual_stop badge is a single-modifier (None vs set); Phase 20 alert badge is 4-state (None vs CLEAR vs APPROACHING vs HIT vs has_stop=False).
**Pattern to copy:**
- Per-state test: `test_no_stop_renders_none_badge`, `test_state_none_renders_dash_with_awaiting_tooltip`, `test_state_clear_renders_alert_clear_class`, `test_state_approaching_renders_alert_approaching_class`, `test_state_hit_renders_alert_hit_class`
- Use `dashboard._render_alert_badge(state, has_stop)` directly (helper-level test) for fast feedback — mirrors Phase 19 unit-level helper tests
- Optional integration test: render full dashboard (`dashboard.render_dashboard(state, out_path, now)`) and grep the HTML for `class="alert-badge alert-{state}"`
- Mobile breakpoint: assert the `_INLINE_CSS` block contains `@media (max-width: 640px)` AND `.alert-badge` declaration inside it (substring grep)
**Pattern to adapt:**
- Phase 14 used full-render integration; Phase 20 should use direct helper call (faster, narrower) per Phase 19 unit-level idiom.
**Hex-boundary check:** clean.

### `tests/test_web_paper_trades.py::test_edit_resets_last_alert_state`

**Closest analog:** `tests/test_web_paper_trades.py:280` — `test_patch_open_row_updates_fields` (Phase 19)
**Why this analog:** Same client fixture (`client_with_state_v6`), same PATCH route, same `captured_saves[-1]` assertion idiom.
**Pattern to copy:**
- `client_with_state_v6` fixture
- `set_state({...})` with seeded `paper_trades` row carrying `last_alert_state: 'APPROACHING'` to verify reset behaviour
- `client.patch(f'/paper-trade/{trade_id}', data={'<field>': <value>}, headers=htmx_headers)`
- Assert `captured_saves[-1]['paper_trades'][0]['last_alert_state'] is None`
**Pattern to adapt:**
- D-15 verbatim: parametrize over field edits — `entry_price`, `stop_price`, `contracts`, `entry_dt`, `side`. Every variant must reset.
- Use `@pytest.mark.parametrize('field,value', [(...)])` over the field set.
- Schema bump from v6 to v7 in the seeded state — update fixture to `'schema_version': 7` and add `'last_alert_state'` to the `_open_row` helper.
**Hex-boundary check:** clean.

### **NEW FIXTURE** `tests/fixtures/state_v7_with_alerts.json`

**Closest analog:** `tests/fixtures/state_v6_with_paper_trades.json` (Phase 19)
**Why this analog:** Same shape; Phase 20 just bumps `schema_version` to 7 and adds `last_alert_state` per row.
**Pattern to copy:**
- Top-level keys identical (schema_version, account, last_run, positions, signals, trade_log, equity_history, warnings, initial_account, contracts, _resolved_contracts, paper_trades)
- `signals[<inst>]` carries `last_close`, `signal`, `signal_as_of`, `as_of_run`, `last_scalars`, `strategy_version`
**Pattern to adapt:**
- Bump `schema_version` to 7
- Extend each row in `paper_trades[]` with `last_alert_state` field
- Add at least 4 rows: SPI200/AUDUSD × CLEAR/APPROACHING/HIT/None — to give `test_main_alerts.py` and `test_dashboard.py` the full state-transition matrix
- Add `indicator_scalars: {atr: ...}` AND `ohlc_window: [{date, open, high, low, close}, ...]` per signal entry — Phase 17 keys, required for alert evaluation. Phase 19 fixture uses legacy `last_scalars` only; Phase 20 fixture must include the Phase 17 shape.
**Hex-boundary check:** clean.

### `FORBIDDEN_MODULES_STDLIB_ONLY` AST-walk extension

**Closest analog:** `tests/test_signal_engine.py:480` (PNL_ENGINE_PATH definition) + line 593 (`_HEX_PATHS_ALL`) + line 595 (`_HEX_PATHS_STDLIB_ONLY`) — Phase 19 added `pnl_engine.py` to both.
**Why this analog:** Identical extension — Phase 19 added pnl_engine.py to both lists; Phase 20 adds alert_engine.py the same way.
**Pattern to copy:**
- Insert `ALERT_ENGINE_PATH = Path('alert_engine.py')` near line 480 (next to `PNL_ENGINE_PATH`)
- Append `ALERT_ENGINE_PATH` to `_HEX_PATHS_ALL` (line 593) AND `_HEX_PATHS_STDLIB_ONLY` (line 595)
- Inline comment: `# Phase 20: alert_engine.py added to AST guard (D-10 + D-11 pure-math hex-tier)`
**Pattern to adapt:** none — verbatim extension.
**Hex-boundary check:** clean.

## Shared Patterns

### Never-crash email send
**Source:** `notifier.py:1497–1508` (`send_daily_email`) + `notifier.py:1756–1767` (`send_magic_link_email`)
**Apply to:** `notifier.send_stop_alert_email`
- Triple try/except: `ResendError` → log + return False; bare `Exception` → log + return False; success → True
- CLAUDE.md `[Email]` log prefix on transport failures
- Per-CONTEXT D-06: orchestrator (`main._evaluate_paper_trade_alerts`) emits the additional `[Alert] WARN stop alert email failed; will retry next run` line

### XSS defence at every interpolation site
**Source:** `notifier.py:1654` (`html.escape(link, quote=True)`) + `dashboard.py:2337` (`html.escape(trade_id, quote=True)`)
**Apply to:** `_render_alert_email_html` (every transitions[i] string field) + `_render_alert_badge` (state value)
- Use `html.escape(str(value), quote=True)` belt-and-suspenders even for regex-validated fields (Phase 19 D-01 regex)
- Float fields formatted as `f"{x:.2f}"` then escape result (zero cost, defence-in-depth)
- RESEARCH §Pitfall 8 enumerates the field-by-field requirement

### NaN-safe pure-math defaults
**Source:** `pnl_engine.py:31` (NaN propagation comment) + Phase 1 NaN policy from `~/.claude/LEARNINGS.md`
**Apply to:** `alert_engine.compute_alert_state` (return 'CLEAR' on NaN; D-10) + `alert_engine.compute_atr_distance` (return NaN on zero/NaN ATR; D-10)
- Short-circuit at top of function: `if any(math.isnan(v) for v in (...)): return 'CLEAR'`
- Divide-by-zero guard: `if atr <= 0: return 'CLEAR'` — `<=` not `<` to also catch atr=0 exact

### Idempotent single-field migration with D-15 silent posture
**Source:** `state_manager._migrate_v5_to_v6` (line 215) + `_migrate_v3_to_v4` per-row idiom
**Apply to:** `_migrate_v6_to_v7`
- `for row in s.get('paper_trades', []): if isinstance(row, dict) and 'last_alert_state' not in row: row['last_alert_state'] = None`
- NO `append_warning`, NO log line (D-15 silent)
- Defensive `isinstance(row, dict)` guard against malformed entries

### LOCAL imports for cross-hex calls in dashboard / web routes
**Source:** `dashboard.py:2314` (`from pnl_engine import compute_unrealised_pnl  # LOCAL — Phase 11 C-2`) + `web/routes/paper_trades.py:316` (`from system_params import STRATEGY_VERSION  # noqa: PLC0415 — fresh import (kwarg trap)`)
**Apply to:** any cross-hex import inside `_evaluate_paper_trade_alerts` (e.g. `from notifier import send_stop_alert_email`) — keep LOCAL inside the function body, NOT at module top, to avoid module-load-time circular hex chains. Accompany with `# noqa: PLC0415` and a one-line rationale.

### Two sequential mutate_state calls (DESIGN-FROM-SCRATCH)
**Source (partial):** `state_manager.mutate_state` doc (`state_manager.py:646–685`) + `_handle_reset` second-call site (`main.py:1648`)
**Apply to:** `_evaluate_paper_trade_alerts` two-phase commit (Phase A: in-memory mutate without write; Phase B: send → conditional `mutate_state(_commit_transitions)`)
**FLAG:** No precedent does conditional-commit-after-side-effect. RESEARCH §Pattern 2 + Pitfall 1 must be quoted in the plan. Reentrancy deadlock at `state_manager.py:332-340` is the load-bearing constraint.

## No Analog Found / Design From Scratch

| Symbol / pattern | Reason | Planner guidance |
|------------------|--------|------------------|
| Two-phase commit (eval → send → conditional commit) inside `_evaluate_paper_trade_alerts` | No prior phase sends an email and conditionally rolls back state. `_handle_reset` does a second `mutate_state` but unconditionally. RESEARCH §Pattern 2 is the canonical spec. | Quote RESEARCH §Pattern 2 verbatim in the plan. Implement as described: Phase A in-memory transitions list build + None→CLEAR no-op writes via first `mutate_state`; Phase B `notifier.send_stop_alert_email(...)` → on True call second `mutate_state(_commit_transitions)`; on False log `[Alert] WARN ...` and skip second call. |
| HTML+plain-text combined alert-email body with N-row table | `send_magic_link_email` is the only HTML+text precedent but renders a fixed single-link body. `send_daily_email` is HTML-only. No analog renders an N-row table in BOTH formats. | Use `_render_magic_link_html` (line 1644) + `_render_magic_link_text` (line 1686) as scaffolding. Build inline-style table in HTML (matching `notifier.py:32` no-CSS-classes rule) + fixed-width text table. Single `transitions: list[dict]` argument feeds both renderers (RESEARCH §Pitfall 2). |
| Inline CSS for 4-state alert badge in dashboard `_INLINE_CSS` | `.badge-manual` is single-modifier; `.trace-badge.{plus,minus,zero,pass,fail}` is multi-modifier but shares one class. D-14 specifies `.alert-{clear,approaching,hit,none}` pattern with raw hex Bootstrap-flavoured colours instead of project palette vars. | Append D-14 verbatim to `_INLINE_CSS` near line 532 (after `.badge-manual`). Use double-brace escape `{{`/`}}` for f-string literals. Operator-locked palette — do NOT substitute `var(--color-long)` etc. |

## Hex-Boundary Spotlight (Final Check)

| Module | Concern | Verdict |
|--------|---------|---------|
| `alert_engine.py` | Must satisfy `FORBIDDEN_MODULES_STDLIB_ONLY` | clean — only `math`, `typing`, optional `system_params` allowed; AST guard extension required at `tests/test_signal_engine.py:480,593,595` |
| `dashboard.py` | Adding `from alert_engine import compute_alert_state`? | NOT NEEDED — render reads `last_alert_state` directly off the row dict (D-11 + D-14). If LOCAL import is later added, `alert_engine` is NOT in `FORBIDDEN_MODULES_DASHBOARD` (mirrors pnl_engine precedent) |
| `main.py` | New imports `from alert_engine import compute_alert_state, compute_atr_distance` AND LOCAL `from notifier import send_stop_alert_email` | clean — `FORBIDDEN_MODULES_MAIN` (line 546) forbids only `numpy/yfinance/requests/pandas`; alert_engine has none of these |
| `notifier.py` | Already imports `requests`, `os`, `system_params`, `html`. New helpers add no new imports. | clean — `FORBIDDEN_MODULES_NOTIFIER` (line 580) unchanged |
| `web/routes/paper_trades.py` | Adding one in-closure assignment line `row['last_alert_state'] = None` | clean — no new imports, in existing closure |
| Two-phase commit deadlock risk | `_evaluate_paper_trade_alerts` MUST be called OUTSIDE the `mutate_state(_apply_daily_run)` closure (line 1393–1404) — between line 1404 (mutate_state return) and line 1421 (`_render_dashboard_never_crash`) | RESEARCH §Pitfall 1 quotes `state_manager.py:332-340` deadlock docstring; planner MUST place the call at line ~1404+1, before line 1421 |

## Metadata

**Analog search scope:** `state_manager.py`, `system_params.py`, `pnl_engine.py`, `notifier.py`, `main.py`, `dashboard.py`, `web/routes/paper_trades.py`, `tests/test_state_manager.py`, `tests/test_pnl_engine.py`, `tests/test_signal_engine.py`, `tests/test_dashboard.py`, `tests/test_web_paper_trades.py`, `tests/test_notifier_magic_link.py`, `tests/test_main.py`, `tests/fixtures/state_v6_with_paper_trades.json`
**Files scanned:** 15
**Pattern extraction date:** 2026-04-30
