# Phase 20: Stop-Loss Monitoring & Alerts — Research

**Researched:** 2026-04-30
**Domain:** Python email (Resend HTTPS), alert state machine, mutate_state two-phase commit, HTML email rendering
**Confidence:** HIGH (all key claims verified against source code or official docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: One batched email per daily run
- D-02: Recipient = SIGNALS_EMAIL_TO; HTML table + plain-text fallback; subject `[!stop] N transition(s)` or `[!stop] <INST> <SIDE> <STATE> — <id>` for N==1
- D-03: "Alert" column in open trades table; colored badges
- D-04: Edit resets last_alert_state to None (any field change)
- D-05: Initial state = None; None→CLEAR = no email; None→APPROACHING/HIT = email
- D-06: Send failure leaves last_alert_state unchanged; retry next run
- D-07: HIT terminal — continue evaluating, no resend unless HIT→CLEAR transition
- D-08: Schema bump 6→7; _migrate_v6_to_v7; D-15 silent migration
- D-09: Extended paper_trades row shape (last_alert_state field added)
- D-10: New pure-math alert_engine.py; compute_alert_state + compute_atr_distance
- D-11: Hex-boundary preserved; alert_engine added to FORBIDDEN_MODULES_STDLIB_ONLY walk
- D-12: Daily-run step 3 between signal-row persistence and dashboard render; _evaluate_paper_trade_alerts(state, dashboard_url)
- D-13: notifier.send_stop_alert_email(transitions, dashboard_url) -> bool; never-crash; html.escape on all fields
- D-14: _render_alert_badge helper; inline CSS .alert-{clear,approaching,hit,none}; mobile @media breakpoint
- D-15: PATCH handler resets last_alert_state = None inside existing mutate_state closure
- D-16: No new env vars

### Claude's Discretion
- None (all decisions locked)

### Deferred Ideas (OUT OF SCOPE)
- Per-trade snooze / mute
- Multi-channel notifications
- Per-instrument alert preferences
- Alert log / audit trail
- Re-send reminder for stale HIT trades
- Live intraday HIT detection
</user_constraints>

---

## Summary

Phase 20 adds a pure-math alert engine on top of the existing Phase 19 paper-trade ledger. The architecture is well-constrained: alert_engine.py joins the hex-lite pure-math tier alongside signal_engine/sizing_engine/pnl_engine, and the daily orchestrator (_evaluate_paper_trade_alerts) runs as step 3 inside the existing _apply_daily_run closure.

The dominant implementation risk is the two-phase-commit pattern for D-06 (rollback on send failure). The existing daily-run framework uses a single mutate_state closure (_apply_daily_run) that replays accumulated mutations from step 2 load through the terminal save. Phase 20 must slot alert evaluation INSIDE this pattern — or use a separate mutate_state call immediately following — while correctly rolling back only transitioning trades' last_alert_state on send failure. The CONTEXT D-12 spec describes the rollback conceptually; the concrete implementation idiom is not precedented in this codebase (no prior phase sends and then conditionally rolls back a partial state update).

The second key risk is the plain-text fallback. The existing send_daily_email calls _post_to_resend with html_body only — no text_body. CONTEXT D-02 requires a plain-text fallback for the stop-alert email. The _post_to_resend helper already accepts both (Phase 8 send_crash_email uses text_body only), so the wiring is present, but send_stop_alert_email must explicitly pass BOTH html_body AND text_body to _post_to_resend. This is NOT the pattern used by send_daily_email and requires a deliberate parallel render step.

**Primary recommendation:** Implement the two-phase-commit as evaluate-without-save → send → conditionally-save (two mutate_state calls: one for non-transitioning/None→CLEAR updates, one for transitioning trade updates only after confirmed send). This is the cleanest Python idiom given mutate_state's closure contract.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Alert state computation (CLEAR/APPROACHING/HIT) | Pure-math (alert_engine.py) | — | Stateless math; same hex tier as pnl_engine/signal_engine |
| ATR-distance computation for email body | Pure-math (alert_engine.py) | — | Pure float arithmetic |
| State transition detection + dedup | Orchestrator (main.py) | — | Reads state, compares, builds transitions list |
| Email dispatch + never-crash | I/O hex (notifier.py) | — | Same layer as send_daily_email/send_crash_email |
| HTML + plain-text body render | I/O hex (notifier.py) | — | Two parallel render helpers, one source of truth |
| Alert badge render (dashboard) | Render I/O (dashboard.py) | — | Pure HTML string; reads last_alert_state from row |
| last_alert_state reset on edit | Web adapter (web/routes/paper_trades.py) | — | Inside existing mutate_state closure |
| Schema migration 6→7 | I/O hex (state_manager.py) | — | Follows established MIGRATIONS dispatch |

---

## Standard Stack

### Core (no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib (math, html, typing) | 3.11 | alert_engine math + XSS escape | Project-wide convention; hex-boundary compliant |
| requests | pinned in requirements.txt | Resend HTTPS via _post_to_resend | Already in notifier.py; no new import |
| pytest | pinned | Tests for alert_engine, notifier extension, main integration | Project-wide test framework |

[VERIFIED: source code grep — no new packages needed; all dependencies already in the venv]

**Installation:** No new packages. Phase 20 is zero-new-dep.

---

## Architecture Patterns

### System Architecture Diagram

```
Daily run (08:00 AWST)
        |
        v
[Step 1-2: signal compute + persist — existing]
        |
        v
[Step 3: _evaluate_paper_trade_alerts(state, dashboard_url)]
        |
    For each open paper_trade with stop_price:
        |
        +---> alert_engine.compute_alert_state(side, low, high, close, stop, atr)
        |                       |
        |          returns 'CLEAR' / 'APPROACHING' / 'HIT'
        |                       |
        +---> compare to row['last_alert_state']
        |                       |
        |              transition? YES --> append to transitions[]
        |              transition? NO  --> skip
        |
        v
    [N transitions?]
        |
       YES ---> notifier.send_stop_alert_email(transitions, url)
        |               |
        |       returns True  --> update last_alert_state in state (persist)
        |       returns False --> rollback last_alert_state for transitioning
        |                        trades (D-06); non-transitioning writes persist
        |
       NO  ---> persist None→CLEAR no-op writes only
        |
        v
[Step 4: render dashboard — reads freshly-updated last_alert_state]
```

### Recommended Project Structure
```
alert_engine.py          # NEW — pure math (joins pnl_engine, sizing_engine, signal_engine tier)
notifier.py              # MODIFIED — add send_stop_alert_email
main.py                  # MODIFIED — add _evaluate_paper_trade_alerts; call in _apply_daily_run
dashboard.py             # MODIFIED — add _render_alert_badge; extend _render_paper_trades_open
state_manager.py         # MODIFIED — add _migrate_v6_to_v7; register MIGRATIONS[7]
system_params.py         # MODIFIED — bump STATE_SCHEMA_VERSION 6→7
web/routes/paper_trades.py  # MODIFIED — PATCH closure resets last_alert_state
tests/test_alert_engine.py    # NEW
tests/test_notifier_stop_alert.py  # NEW
tests/test_main_alerts.py     # NEW
tests/fixtures/state_v7_with_alerts.json  # NEW
```

### Pattern 1: mutate_state Closure Contract
**What:** `mutate_state(mutator, path)` acquires fcntl.LOCK_EX, calls `load_state(_under_lock=True)`, passes the fresh state dict to `mutator(state)` which mutates in place (return value ignored), then saves via `_save_state_unlocked`. Returns the post-mutation state.

**Critical constraint verified:** The closure mutator's return value is IGNORED by mutate_state. The mutator MUTATES IN PLACE. [VERIFIED: state_manager.py line 679]

```python
# Source: state_manager.py lines 646-685
def mutate_state(mutator: Callable[[dict], None], path: Path = ...) -> dict:
  fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
  try:
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
      state = load_state(path=path, _under_lock=True)
      mutator(state)                       # mutates in place; return ignored
      _save_state_unlocked(state, path=path)
      return state
    finally:
      fcntl.flock(fd, fcntl.LOCK_UN)
  finally:
    os.close(fd)
```

**Callers can call mutate_state TWICE in sequence** (the lock releases between calls). This is the key to the D-06 rollback pattern.

### Pattern 2: Two-Phase Commit for D-06 (THE KEY PATTERN)
**What:** The D-06 spec says "send fails → leave last_alert_state unchanged for transitioning trades." The implementation idiom that fits the existing closure contract is:

**Phase A** — Inside the existing `_apply_daily_run` closure (step 3), do NOT update `paper_trades[].last_alert_state` for transitioning trades. Only update for non-transitioning reads (None→CLEAR no-op).

**Phase B** — After the closure returns and BEFORE dashboard render, call `send_stop_alert_email`. If it returns True, call a SECOND `mutate_state` to write the transitioning trades' new `last_alert_state` values. If False, skip that second call — the state on disk already has the old values.

```python
# In main.py _evaluate_paper_trade_alerts (conceptual shape):

def _evaluate_paper_trade_alerts(state: dict, dashboard_url: str) -> dict:
  transitions = []
  # Phase A: compute new states, accumulate transitions, update only non-transitioning
  for row in state.get('paper_trades', []):
    if row.get('status') != 'open' or row.get('stop_price') is None:
      continue
    inst = row['instrument']
    signals = state.get('signals', {}).get(inst, {})
    scalars = signals.get('indicator_scalars', {})
    atr = scalars.get('atr', float('nan'))
    ohlc_window = signals.get('ohlc_window', [])
    if not ohlc_window:
      logger.warning('[Alert] WARN no OHLC for %s; treating as CLEAR', inst)
      new_state = 'CLEAR'
    else:
      last_bar = ohlc_window[-1]
      new_state = alert_engine.compute_alert_state(
        row['side'], last_bar['low'], last_bar['high'],
        last_bar['close'], row['stop_price'], atr,
      )
    old_state = row.get('last_alert_state')
    if old_state != new_state:
      transitions.append({
        'id': row['id'],
        'instrument': row['instrument'],
        'side': row['side'],
        'entry_price': row['entry_price'],
        'stop_price': row['stop_price'],
        'today_close': last_bar['close'] if ohlc_window else float('nan'),
        'atr_distance': alert_engine.compute_atr_distance(
          last_bar['close'] if ohlc_window else float('nan'),
          row['stop_price'], atr,
        ),
        'new_state': new_state,
        'old_state': old_state,
      })
    else:
      # Non-transition: safe to update now (idempotent; None→CLEAR no-op)
      row['last_alert_state'] = new_state

  if not transitions:
    return {'transitions': [], 'emailed': False}

  # Phase B: send, then conditionally commit transitioning states
  import notifier  # C-2 local import pattern
  emailed = notifier.send_stop_alert_email(transitions, dashboard_url)
  if emailed:
    # Second mutate_state to commit transitioning states
    _transition_map = {t['id']: t['new_state'] for t in transitions}
    def _commit_transitions(s: dict) -> None:
      for row in s.get('paper_trades', []):
        if row['id'] in _transition_map:
          row['last_alert_state'] = _transition_map[row['id']]
    state_manager.mutate_state(_commit_transitions)
    logger.info('[Alert] %d transition(s) emailed and committed', len(transitions))
  else:
    logger.warning(
      '[Alert] WARN stop alert email failed; will retry next run',
    )
  return {'transitions': transitions, 'emailed': emailed}
```

**Why two mutate_state calls are legal:** Phase 14 D-13 and the lock kernel explicitly allow multiple sequential mutate_state calls. Each acquires then releases LOCK_EX. Between the two calls, the web PATCH handler could interleave — but if it does, it resets last_alert_state=None (D-04/D-15), which is also correct behavior (the trade was edited; the next run re-evaluates).

**Note on CONTEXT D-12 integration:** `_evaluate_paper_trade_alerts` is called from inside `_apply_daily_run` closure per D-12. But the second mutate_state (the commit) must happen OUTSIDE the closure — mutate_state is not reentrant (two fds in the same process to the same file deadlock, per state_manager.py lines 332-340). The function signature in D-12 says it returns `{'transitions': [...], 'emailed': bool}` — this means the CALLER (`_apply_daily_run`) decides when to commit, or the function manages its own second mutate_state after returning from the closure context.

**Concrete resolution:** `_evaluate_paper_trade_alerts` is NOT called inside the `_apply_daily_run` closure. It is called BETWEEN the `mutate_state(_apply_daily_run)` call (step 2 save) and `_render_dashboard_never_crash` (step 4). It does its own two-phase mutate_state pair. The CONTEXT D-12 description "step 3 in _apply_daily_run" means step 3 in the DAILY RUN SEQUENCE, not inside the closure itself — confirmed by the fact that dashboard render also runs after the closure (lines 1421 of main.py).

### Pattern 3: Resend Payload with HTML + Text
**What:** _post_to_resend accepts both html_body and text_body simultaneously. When both are provided, Resend sends a multipart/alternative MIME message. Email clients choose the appropriate part.

```python
# Source: notifier.py _post_to_resend lines 1351-1359
payload: dict = {
  'from': from_addr,
  'to': [to_addr],
  'subject': subject,
}
if html_body is not None:
  payload['html'] = html_body
if text_body is not None:
  payload['text'] = text_body
```

**send_daily_email passes html_body only** (line 1494). send_crash_email passes text_body only (line 1590). **send_stop_alert_email MUST pass BOTH** per D-02. This requires parallel render helpers: `_render_alert_email_html(transitions) -> str` and `_render_alert_email_text(transitions) -> str`. [VERIFIED: notifier.py source]

### Pattern 4: Never-Crash Posture (inherited)
**What:** send_stop_alert_email wraps _post_to_resend in try/except ResendError + bare Exception, returns bool. Never raises. Caller (main.py) uses the bool for D-06 rollback logic.

```python
# Pattern: mirror send_daily_email's except chain (notifier.py lines 1497-1508)
def send_stop_alert_email(transitions: list[dict], dashboard_url: str) -> bool:
  try:
    # build subject, html_body, text_body from transitions
    _post_to_resend(api_key, from_addr, to_addr, subject, html_body, text_body=text_body)
    return True
  except ResendError as e:
    logger.warning('[Alert] WARN send_stop_alert_email failed: %s', e)
    return False
  except Exception as e:
    logger.warning('[Alert] WARN send_stop_alert_email unexpected: %s: %s', type(e).__name__, e)
    return False
```

### Pattern 5: NaN-Safe Pure-Math Module
**What:** alert_engine.py follows pnl_engine.py's NaN policy — NaN inputs propagate or produce a safe default, never crash. [VERIFIED: pnl_engine.py lines 30-37]

```python
# In alert_engine.py compute_alert_state:
import math

def compute_alert_state(side, today_low, today_high, today_close, stop_price, atr):
  # NaN guard: any NaN input returns 'CLEAR' (D-10 safe default)
  if any(math.isnan(v) for v in (today_low, today_high, today_close, stop_price, atr)):
    return 'CLEAR'
  if atr <= 0:
    return 'CLEAR'
  # HIT has precedence over APPROACHING (D-10)
  if side == 'LONG' and today_low <= stop_price:
    return 'HIT'
  if side == 'SHORT' and today_high >= stop_price:
    return 'HIT'
  if abs(today_close - stop_price) <= 0.5 * atr:
    return 'APPROACHING'
  return 'CLEAR'
```

### Pattern 6: Forbidden Imports Extension
**What:** `test_signal_engine.py::test_phase2_hex_modules_no_numpy_pandas` uses `FORBIDDEN_MODULES_STDLIB_ONLY` (= FORBIDDEN_MODULES + numpy + pandas) applied to `_HEX_PATHS_STDLIB_ONLY`. pnl_engine.py was added to this list in Phase 19. alert_engine.py joins in Phase 20. [VERIFIED: test_signal_engine.py lines 479-502]

```python
# In tests/test_signal_engine.py:
ALERT_ENGINE_PATH = Path('alert_engine.py')
# Add to _HEX_PATHS_STDLIB_ONLY parametrize list
```

### Anti-Patterns to Avoid
- **Calling mutate_state inside a mutate_state closure:** Deadlocks on POSIX via intra-process flock-on-different-fd. The deadlock is documented in state_manager.py lines 332-340. `_evaluate_paper_trade_alerts` must NOT be called from inside `_apply_daily_run` if it itself calls mutate_state. Call it from main run_daily_check AFTER the _apply_daily_run mutate_state returns.
- **Using return value of the closure mutator:** mutate_state ignores the mutator's return value. Any data the caller needs from inside the closure must be captured via closure variables (`_accumulated` pattern in main.py line 1392).
- **CSS classes in email body instead of inline styles:** The project XSS posture (notifier.py line 32) and UAT evidence (Phase 16 UAT-16-B) confirm inline `style="..."` is the required pattern. CSS classes in HTML email get stripped by Gmail. The badge colors for the email body must use inline `style="color:#...; background:#..."`, NOT the `.alert-clear` CSS classes which are only for the dashboard HTML.
- **Sending plain-text only for stop alerts:** _post_to_resend supports both keys simultaneously. Omitting html_body and sending text_body only degrades the email to plain text for all clients. D-02 requires HTML table as the primary body.
- **Building text_body by stripping HTML:** The project convention (D-02 verbatim) is "identical plain-text fallback rendered from the same transitions data." Use a separate `_render_alert_email_text(transitions)` function, NOT an HTML stripper.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MIME multipart/alternative | Custom MIME builder | Pass both `html` and `text` keys to Resend payload | _post_to_resend already does this (Phase 8 precedent) |
| HTML→text conversion | HTMLParser strip | Separate plain-text renderer from same transitions data | Project convention; no new dep; avoids HTML-entity leakage |
| File locking for state writes | fcntl wrapper | state_manager.mutate_state | Already implements POSIX flock with deadlock-safe _under_lock |
| Email idempotency | Custom dedup store | None needed — Resend Idempotency-Key is available but OVERKILL | See Pitfall 4 below |
| Math library for NaN detection | numpy.isnan | math.isnan | hex-boundary; alert_engine is stdlib-only |

**Key insight:** Every infrastructure piece already exists. Phase 20 is assembly, not invention.

---

## Common Pitfalls

### Pitfall 1: Calling mutate_state Inside _apply_daily_run Closure
**What goes wrong:** `_evaluate_paper_trade_alerts` is called inside `_apply_daily_run`. If it calls its own `mutate_state`, the outer flock is already held. A second `fcntl.flock(LOCK_EX)` from a different fd in the same process on the same file BLOCKS FOREVER — POSIX flock is not reentrant across fds.
**Why it happens:** CONTEXT D-12 says step 3 is "inside _apply_daily_run" — it means the daily-run SEQUENCE step 3, not inside the Python closure. Easy to misread.
**How to avoid:** Call `_evaluate_paper_trade_alerts` from `run_daily_check` AFTER the `mutate_state(_apply_daily_run)` call returns (line ~1404 of main.py). Same position as `_render_dashboard_never_crash` (line 1421).
**Warning signs:** `fcntl.flock` blocking indefinitely in test or production. Any `mutate_state` call inside another `mutate_state`'s closure mutator.

### Pitfall 2: Plain-Text Fallback Drift
**What goes wrong:** HTML and text bodies are generated from different code paths and drift over time — a transition appears in HTML but not plain-text, or vice versa.
**Why it happens:** HTML renderer is built first; text renderer is added as an afterthought with its own logic.
**How to avoid:** Both `_render_alert_email_html(transitions)` and `_render_alert_email_text(transitions)` take the same `transitions: list[dict]` argument and iterate the same list. Test asserts BOTH contain every transition's `id` and `new_state`. [VERIFIED: D-02 in CONTEXT.md states "parallel render helpers"]
**Warning signs:** Test `test_both_bodies_contain_all_transitions` fails.

### Pitfall 3: Inline CSS vs CSS Classes in Email vs Dashboard
**What goes wrong:** Dashboard badges use CSS classes (`.alert-clear`, `.alert-approaching`, `.alert-hit`) defined in a `<style>` block. Copying that pattern into the email body produces invisible/unstyled badges in Gmail, which strips `<style>` blocks.
**Why it happens:** Dashboard HTML is served from a web server to a browser; email HTML is processed by Gmail's CSS stripper.
**How to avoid:** Email body uses ONLY `style="..."` inline attributes, matching the existing notifier.py convention (line 32: "inline style='...' on every coloured span — NO CSS classes"). Dashboard uses CSS classes only (no inline styles needed). Two separate rendering paths.
**Warning signs:** UAT of email in Gmail mobile shows unstyled grey text where colored badge should appear.

### Pitfall 4: Resend Idempotency-Key Overkill
**What goes wrong:** Developer adds an Idempotency-Key header to prevent duplicate emails on retry. Key expires after 24 hours (Resend API confirmed). Daily run fires once per day. If the key is based on `(date, transitions_hash)`, a legitimate retry next day (different date) would have a different key anyway. If the key is reused across days, the 24h expiry would suppress the legitimate next-day alert.
**Why it happens:** Idempotency-Key is a reasonable precaution for high-volume APIs but is counter-productive here.
**How to avoid:** Do NOT add Idempotency-Key to `send_stop_alert_email`. The deduplication is entirely handled by `last_alert_state` persistence (D-06). If send fails mid-retry (_RESEND_RETRIES=3), the same payload is retried within the same dispatch call — no separate daily-run retry produces duplicate email for the same transition.
**Warning signs:** An alert that should fire each day gets suppressed after the first send.

### Pitfall 5: `ohlc_window` Index for today_low/today_high/today_close
**What goes wrong:** `state['signals'][inst]['ohlc_window']` is a list of 40 OHLC dicts. The alert engine needs TODAY's low/high/close — that's `ohlc_window[-1]` (the last bar). Using `ohlc_window[0]` gives data from 40 days ago.
**Why it happens:** ohlc_window is ordered oldest-first (Phase 17 D-09: `df.tail(40)` produces ascending date order).
**How to avoid:** Always use `ohlc_window[-1]` for the current bar's data. Assert in tests that the test fixture's last bar date matches the run_date.
**Warning signs:** APPROACHING or HIT triggered by a 40-day-old bar; distance calculation uses historical close instead of today's close.

### Pitfall 6: NaN in indicator_scalars When No Daily Run Yet
**What goes wrong:** A paper trade is entered before any daily run has run (fresh deploy). `state['signals'][inst]['indicator_scalars']` may be `{}` (Phase 17 _migrate_v4_to_v5 stamps empty dict). `scalars.get('atr', float('nan'))` returns NaN. `compute_alert_state` with NaN atr returns 'CLEAR'. Good — but the log line confirming this must still emit.
**Why it happens:** First-run state has empty indicator_scalars.
**How to avoid:** Add explicit guard: `if not scalars or 'atr' not in scalars: logger.warning('[Alert] WARN no ATR for %s; treating as CLEAR', inst)`. Return 'CLEAR'. This is the D-10 NaN policy in action.
**Warning signs:** Silent CLEAR without the [Alert] WARN log line.

### Pitfall 7: STRATEGY_VERSION kwarg-default Capture Trap
**What goes wrong:** A helper in main.py or notifier.py captures `system_params.STRATEGY_VERSION` at function-definition time via a default argument (e.g., `def _render_alert_email_html(transitions, version=system_params.STRATEGY_VERSION)`). If STRATEGY_VERSION changes (Phase 22 pattern), the function returns stale data.
**Why it happens:** Python default arguments are evaluated at definition time, not call time. This was documented in project LEARNINGS.
**How to avoid:** Always access `system_params.STRATEGY_VERSION` with a fresh attribute lookup inside the function body. Never use it as a default argument. [CITED: .claude/LEARNINGS.md — kwarg-default capture trap entry; also Phase 19 web/routes/paper_trades.py line 316: `from system_params import STRATEGY_VERSION  # fresh import (kwarg trap)`]

### Pitfall 8: XSS Scope — What Fields Need Escaping
**What goes wrong:** Some fields assumed safe and left unescaped. An adversarial `id` like `<script>alert(1)</script>-20260430-001` (impossible due to Phase 19 D-01 regex validation, but still) or a `side` with HTML-special characters.
**Why it happens:** Numeric fields (entry_price, stop_price, today_close, atr_distance) are floats formatted with f-string — intrinsically safe. String fields (id, instrument, side) are validated by Phase 19 D-04, but email body escaping is belt-and-suspenders per D-13.
**How to avoid:** `html.escape(str(value), quote=True)` on ALL string fields in the transitions dict before HTML interpolation. Float fields formatted as `f"{x:.2f}"` — escape the resulting string too (belt-and-suspenders; no risk but zero cost).
**Warning signs:** `grep -n 'transitions.*f"' notifier.py | grep -v escape` returns results.

---

## Code Examples

### Resend Payload with Both HTML + Plain Text
```python
# Source: notifier.py _post_to_resend lines 1351-1359 (verified)
# To send both bodies simultaneously:
_post_to_resend(
  api_key=api_key,
  from_addr=from_addr,
  to_addr=to_addr,
  subject=subject,
  html_body=html_body,   # NEW for stop alert
  text_body=text_body,   # NEW for stop alert (D-02 fallback)
)
# Resend server selects correct MIME part per client.
# No additional configuration needed.
```

### D-02 Subject Line Construction
```python
# Source: CONTEXT.md D-02 (locked)
def _build_alert_subject(transitions: list[dict]) -> str:
  n = len(transitions)
  if n == 1:
    t = transitions[0]
    return (
      f'[!stop] {html.escape(t["instrument"])} '
      f'{html.escape(t["side"])} '
      f'{html.escape(t["new_state"])} — {html.escape(t["id"])}'
    )
  return f'[!stop] {n} transition(s) in today\'s paper trades'
```

### Migration Pattern (mirror of _migrate_v5_to_v6)
```python
# Source: state_manager.py lines 215-226 (verified _migrate_v5_to_v6 shape)
def _migrate_v6_to_v7(s: dict) -> dict:
  '''Phase 20 (v1.2): introduce last_alert_state on paper_trades rows.'''
  for row in s.get('paper_trades', []):
    if isinstance(row, dict) and 'last_alert_state' not in row:
      row['last_alert_state'] = None
  return s
# Register: MIGRATIONS[7] = _migrate_v6_to_v7
```

### NaN Parametrize Test Pattern (mirror of test_pnl_engine.py)
```python
# Source: tests/test_pnl_engine.py line 65-73 (verified NaN test shape)
class TestComputeAlertState:
  @pytest.mark.parametrize('nan_field', [
    'today_low', 'today_high', 'today_close', 'stop_price', 'atr',
  ])
  def test_nan_input_returns_clear(self, nan_field) -> None:
    '''D-10: any NaN input returns CLEAR (no false positive alert).'''
    from alert_engine import compute_alert_state
    kwargs = dict(
      side='LONG', today_low=4200.0, today_high=4250.0,
      today_close=4205.0, stop_price=4200.0, atr=50.0,
    )
    kwargs[nan_field] = float('nan')
    result = compute_alert_state(**kwargs)
    assert result == 'CLEAR', f'NaN {nan_field} must return CLEAR, got {result!r}'
```

### Dashboard Inline CSS for Alert Badge (email vs dashboard distinction)
```python
# Dashboard uses CSS classes (served to browser):
def _render_alert_badge(state: str | None, has_stop: bool) -> str:
  # Returns <span class="alert-badge alert-clear">CLEAR</span>
  # CSS class is defined in _INLINE_CSS style block (stripped from email)

# Email body uses inline styles (D-13 + notifier.py line 32 convention):
def _render_alert_badge_email(state: str, has_stop: bool) -> str:
  colors = {
    'CLEAR':      ('background:#d4edda;color:#155724',),
    'APPROACHING':('background:#fff3cd;color:#856404',),
    'HIT':        ('background:#f8d7da;color:#721c24',),
  }
  style = colors.get(state, ('background:#e9ecef;color:#6c757d',))[0]
  safe_state = html.escape(state, quote=True)
  return f'<span style="{style};padding:2px 6px;border-radius:4px;">{safe_state}</span>'
```

---

## Runtime State Inventory

> Omitted — this is a greenfield feature addition, not a rename/refactor/migration phase. The schema migration 6→7 is code-only; no stored data with string key changes.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| HTML-only email (send_daily_email) | HTML + plain-text together via same _post_to_resend (send_crash_email uses text-only) | Phase 8 | stop-alert must explicitly pass both |
| Single mutate_state per daily run | Two sequential mutate_state calls (for two-phase commit) | Phase 20 | Planner must not assume "one save per feature" |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ohlc_window[-1]` is the current day's OHLC bar (ascending date order) | Pitfall 5 | Alert triggers on wrong day's data — APPROACHING/HIT based on 40-day-old price |
| A2 | `state['signals'][inst]['indicator_scalars']['atr']` is the ATR(14) value the alert engine should use | Pattern 5 | Wrong ATR scaling for APPROACHING threshold |

> A1 and A2 are HIGH confidence based on Phase 17 D-09 CONTEXT and main.py lines 1307-1329 where indicator_scalars is populated. Not independently verified against a real state.json.

---

## Open Questions

1. **Where exactly does `_evaluate_paper_trade_alerts` get called in `run_daily_check`?**
   - What we know: D-12 says "step 3 in _apply_daily_run" but the function cannot call mutate_state inside the existing `_apply_daily_run` closure (deadlock).
   - What's unclear: Does D-12 mean "step 3 in the daily-run sequence" (after mutate_state returns) or "inside the Python closure"?
   - Recommendation: Call it AFTER `state = state_manager.mutate_state(_apply_daily_run)` (line ~1404) and BEFORE `_render_dashboard_never_crash` (line ~1421). This matches D-12's intent (alerts read fresh state, dashboard reads alert-updated state) without the deadlock. The non-transitioning None→CLEAR writes can be folded into _apply_daily_run's key replay, or deferred to the _evaluate call's own mutate_state pair.

2. **What is the exact `ohlc_window` key names for today's bar?**
   - What we know: Phase 17 D-09 says ohlc_window is a list of dicts with OHLC data.
   - What's unclear: Are the keys `'low'`, `'high'`, `'close'` or `'Low'`, `'High'`, `'Close'` (yfinance convention)?
   - Recommendation: Planner should grep `state_manager.py` or `main.py` for ohlc_window population code to confirm key casing before writing alert_engine or tests. The Phase 17 CONTEXT D-09 should specify this.

3. **Does `_render_paper_trades_open` already import `html` for escaping?**
   - What we know: dashboard.py uses html.escape elsewhere.
   - What's unclear: Whether dashboard.py already imports html or the planner needs to add it.
   - Recommendation: Check `import html` at top of dashboard.py before writing the plan. Low risk either way.

---

## Environment Availability

Step 2.6: SKIPPED — Phase 20 is code/config-only. No external tools, services, or CLIs beyond the existing stack (Python 3.11, pytest, Resend HTTPS via requests). All dependencies present.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (pinned in requirements.txt) |
| Config file | pytest.ini (check for existence) or pyproject.toml |
| Quick run command | `pytest tests/test_alert_engine.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ALERT-01 | compute_alert_state returns CLEAR/APPROACHING/HIT per spec | unit | `pytest tests/test_alert_engine.py -x` | ❌ Wave 0 |
| ALERT-01 | HIT takes precedence over APPROACHING | unit | `pytest tests/test_alert_engine.py::TestComputeAlertState::test_hit_precedence_over_approaching -x` | ❌ Wave 0 |
| ALERT-01 | NaN input returns CLEAR | unit | `pytest tests/test_alert_engine.py::TestComputeAlertState -x -k nan` | ❌ Wave 0 |
| ALERT-02 | Transition detection + dedup (no email on re-eval same state) | unit | `pytest tests/test_main_alerts.py -x` | ❌ Wave 0 |
| ALERT-02 | Send failure leaves last_alert_state unchanged | unit | `pytest tests/test_main_alerts.py::TestEvaluateAlerts::test_send_failure_rollback -x` | ❌ Wave 0 |
| ALERT-03 | send_stop_alert_email returns bool, never raises | unit | `pytest tests/test_notifier_stop_alert.py -x` | ❌ Wave 0 |
| ALERT-03 | Both HTML and text bodies contain all transition ids+states | unit | `pytest tests/test_notifier_stop_alert.py::TestEmailBodies -x` | ❌ Wave 0 |
| ALERT-04 | Schema migration 6→7 idempotent, preserves other fields | unit | `pytest tests/test_state_manager.py::TestMigrateV6ToV7 -x` | ❌ Wave 0 |
| ALERT-04 | Dashboard _render_alert_badge returns correct CSS class per state | unit | `pytest tests/test_dashboard.py::TestRenderAlertBadge -x` | ❌ Wave 0 |
| ALERT-04 | PATCH edit resets last_alert_state to None | unit | `pytest tests/test_web_paper_trades.py::TestEditPaperTrade::test_edit_resets_last_alert_state -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_alert_engine.py tests/test_notifier_stop_alert.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_alert_engine.py` — covers ALERT-01 (HIT/APPROACHING/CLEAR, NaN, LONG/SHORT asymmetry, compute_atr_distance)
- [ ] `tests/test_notifier_stop_alert.py` — covers ALERT-03 (send success/failure, HTML+text bodies, N=0/1/3)
- [ ] `tests/test_main_alerts.py` — covers ALERT-02 (transition detection, dedup, rollback, _apply_daily_run ordering)
- [ ] `tests/fixtures/state_v7_with_alerts.json` — 4 paper trades × 4 states (None, CLEAR, APPROACHING, HIT) × 2 instruments

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No new auth surface |
| V3 Session Management | no | No session changes |
| V4 Access Control | no | Email is sent to operator-configured SIGNALS_EMAIL_TO only |
| V5 Input Validation | yes | html.escape on all transitions fields in email body; Phase 19 D-04 validates paper_trade fields at entry time |
| V6 Cryptography | no | No new crypto |

### Known Threat Patterns for {stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| HTML injection via paper trade fields in email body | Tampering | `html.escape(value, quote=True)` at every interpolation site in `_render_alert_email_html` (D-13 explicit) |
| RESEND_API_KEY leakage in error logs | Information Disclosure | _post_to_resend already redacts api_key from error messages (lines 1385-1407) — inherited by send_stop_alert_email |
| Email to wrong recipient (env var missing) | Spoofing | SIGNALS_EMAIL_TO has _EMAIL_TO_FALLBACK = 'mwiriadi@gmail.com' (hardcoded operator fallback) — no wrong-recipient risk |

---

## Operator UAT Runbook (Phase 20)

Based on Phase 16 HUMAN-UAT.md precedent (UAT-16-B format).

**Scenario: First Production Alert**
1. SSH to droplet. Open a paper trade with `stop_price` set to within 0.5×ATR of yesterday's close (check `state.signals.SPI200.indicator_scalars.atr` in state.json for the current ATR value).
2. Wait for the 08:00 AWST daily run, or trigger via `python main.py --once`.
3. Confirm:
   - `journalctl -u trading-signals` shows `[Alert] N transition(s) emailed and committed`
   - Gmail mobile inbox shows `[!stop]` subject with the trade's id
   - Email body HTML table renders with colored state badge (Gmail mobile confirms inline styles work)
   - `state.json` paper_trades row has `last_alert_state: "APPROACHING"` (or `"HIT"`)
4. Re-run without changing stop_price. Confirm NO second email (dedup).
5. PATCH the trade (edit any field). Confirm `last_alert_state` resets to `null` in state.json.

**Pre-UAT verification command:**
```bash
python -c "
import json, state_manager
s = state_manager.load_state()
print('Schema version:', s['schema_version'])
print('Paper trades:', len(s.get('paper_trades', [])))
for row in s.get('paper_trades', []):
  print(' ', row['id'], row.get('status'), row.get('last_alert_state'), row.get('stop_price'))
"
```

---

## Sources

### Primary (HIGH confidence)
- notifier.py — verified _post_to_resend payload shape (lines 1315-1409), send_daily_email html-only pattern (line 1494), _RESEND_RETRY_EXCEPTIONS (lines 113-118)
- state_manager.py — verified mutate_state contract (lines 646-685), _atomic_write deadlock docs (lines 332-340), _migrate_v5_to_v6 precedent (lines 215-226), MIGRATIONS dispatch (lines 229-236)
- main.py — verified _apply_daily_run closure pattern (lines 1393-1404), daily-run step sequence (lines 1011-1042), dashboard render position (line 1421)
- tests/test_signal_engine.py — verified FORBIDDEN_MODULES_STDLIB_ONLY (lines 501-502), pnl_engine parametrize NaN pattern (lines 479-480)
- tests/test_pnl_engine.py — verified NaN propagation test shape (lines 65-73)
- web/routes/paper_trades.py — verified PATCH handler mutate_state closure (lines 315-346, no last_alert_state reset yet — Phase 20 adds it)
- .planning/phases/20-stop-loss-monitoring-alerts/20-CONTEXT.md — locked decisions D-01..D-16
- Resend API docs (resend.com/docs/api-reference/emails/send-email) — verified Idempotency-Key support, 24h expiry, 256-char max

### Secondary (MEDIUM confidence)
- can-i-email.com background-color support data — confirmed background-color inline style works in Gmail mobile (since 2019-02), Apple Mail iOS (since 12.1), Outlook desktop (all versions)
- designmodo.com HTML/CSS in Emails (2026) — confirmed inline CSS required for Gmail; `<style>` blocks stripped in cross-client sends
- Phase 16 HUMAN-UAT.md UAT-16-B notes — confirmed inline style="..." pattern works in real Gmail mobile (2026-04-29 operator verification)

### Tertiary (LOW confidence)
- None — all key claims verified from source.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies; all verified in source
- Architecture (two-phase commit pattern): HIGH — verified mutate_state contract, documented deadlock risk
- Resend payload shape: HIGH — verified from notifier.py source
- Plain-text fallback gap: HIGH — verified send_daily_email does NOT pass text_body (line 1494)
- HTML email rendering: MEDIUM — background-color verified via can-i-email; inline style approach verified via UAT-16-B
- Operator UAT runbook: MEDIUM — shape inferred from Phase 16 precedent; specifics depend on production ATR values

**Research date:** 2026-04-30
**Valid until:** 2026-05-30 (stable stack; Resend API changes rarely)
