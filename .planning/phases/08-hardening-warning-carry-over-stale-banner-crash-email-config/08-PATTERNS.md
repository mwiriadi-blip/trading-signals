# Phase 8: Hardening — Warning Carry-over, Stale Banner, Crash Email, Configurable Account — Pattern Map

**Mapped:** 2026-04-23
**Files analyzed:** 10 (6 source, 4 test)
**Analogs found:** 10 / 10 — all targets are modifications of existing files; each change has a direct analog inside the SAME file (or a peer file touched by this phase).

Because every target file already exists and only needs surgical edits, the "analog" column is almost always "an existing helper or section INSIDE the same file." Excerpts below are concrete enough that the planner can cite line numbers verbatim in each plan's action section.

---

## File Classification

| File (modified) | Role | Data Flow | Closest Analog | Match Quality |
|-----------------|------|-----------|----------------|---------------|
| `state_manager.py` | I/O-hex module (sole state writer) | atomic file I/O + schema migration | same file — `_migrate`, `append_warning`, `load_state`, `save_state` (lines 135-146, 302-353, 355-369, 371-399) | exact (extending existing helpers) |
| `notifier.py` | I/O-hex module (email dispatcher) | request-response (HTTPS) + file I/O | same file — `_render_header_email`, `_send_email_never_crash` pattern, `_post_to_resend`, `_atomic_write_html` (lines 455-496, 1076-1153, 1156-1205, 1034-1073) | exact |
| `main.py` | orchestrator / CLI driver | typed-exception boundary + argparse dispatch | same file — typed-exception ladder (lines 883-916), `_handle_reset` (lines 801-832), `_validate_flag_combo` (lines 289-297), `_render_dashboard_never_crash` (lines 98-116) | exact |
| `system_params.py` | shared-constants module | pure (no I/O) | same file — existing SPI_MULT/SPI_COST_AUD/AUDUSD_NOTIONAL/AUDUSD_COST_AUD scalar constants (lines 62-68) | role-match (scalars → dict of tier-labels) |
| `dashboard.py` | I/O-hex module (HTML renderer) | read-only state render | same file — `_compute_total_return` (lines 487-495) | exact (one-line fallback refactor) |
| `sizing_engine.py` | pure-math module | pure (no I/O) | unchanged per D-17 — no edits | N/A (reference only) |
| `tests/test_state_manager.py` | test module | pytest unit tests | same file — `TestWarnings` (lines 901-953), `TestCorruptionRecovery` (lines 374-536), `TestSchemaVersion` (lines 955+) | exact |
| `tests/test_notifier.py` | test module | pytest unit tests | same file — `TestResendPost` (lines 711-963), `TestSendDispatch` (lines 965-1090), `_FakeResp` (lines 692-708) | exact |
| `tests/test_main.py` | test module | pytest unit tests | same file — `TestCLI::test_reset_with_confirmation_writes_fresh_state` (lines 218-242), `test_reset_without_confirmation_does_not_write` (lines 244-269), `TestEmailNeverCrash` (lines 1002-1067) | exact |
| `tests/test_scheduler.py` | test module | pytest unit tests | same file — `TestLoopDriver` (lines 186-237), `TestLoopErrorHandling` (lines 240-275), `_FakeScheduler` (lines 21-53) | exact |

---

## Pattern Assignments

### `state_manager.py` — `_migrate` CONF-01/CONF-02 backfill (D-15)

**Analog:** `state_manager._migrate` (lines 135-146) + MIGRATIONS dict (lines 79-82)

**Current signature + docstring** (lines 135-146):
```python
def _migrate(state: dict) -> dict:
  '''STATE-04: walk schema_version forward to STATE_SCHEMA_VERSION.

  Pitfall 5 (RESEARCH.md): state without schema_version key defaults to 0
  via state.get('schema_version', 0), walks up to current.
  '''
  version = state.get('schema_version', 0)
  while version < STATE_SCHEMA_VERSION:
    version += 1
    state = MIGRATIONS[version](state)
  state['schema_version'] = STATE_SCHEMA_VERSION
  return state
```

**Pattern the planner must REPLICATE for D-15 backfill:**
D-15 says fill defaults SILENTLY (no `append_warning`, no log). Two options for the planner to choose between:
1. **Bump `STATE_SCHEMA_VERSION` to 2** and add `MIGRATIONS[2] = lambda s: {...}` (canonical walk-forward path per Phase 3 D-04).
2. **Inline defaulting inside `_migrate` body** before/after the `while` loop (simpler but bypasses the version-registry mechanism).

**Recommendation:** Use option 1 — it is the convention the existing MIGRATIONS stub (line 81 `# 2: lambda s: {...} stub for future`) literally reserves. Pattern:
```python
MIGRATIONS: dict = {
  1: lambda s: s,
  2: lambda s: {
    **s,
    'initial_account': s.get('initial_account', INITIAL_ACCOUNT),
    'contracts': s.get('contracts', {
      'SPI200': '<DEFAULT_SPI_LABEL>',      # D-11 TBD
      'AUDUSD': '<DEFAULT_AUDUSD_LABEL>',   # D-11 TBD
    }),
  },
}
```
Then bump `STATE_SCHEMA_VERSION: int = 2` in `system_params.py` (line 76).

**Required keys whitelist** (lines 70-73) must gain `initial_account` and `contracts`:
```python
_REQUIRED_STATE_KEYS = frozenset({
  'schema_version', 'account', 'last_run', 'positions',
  'signals', 'trade_log', 'equity_history', 'warnings',
  # Phase 8 additions:
  'initial_account', 'contracts',
})
```
Otherwise `_validate_loaded_state` (lines 243-273) raises `ValueError` on migrated v1-to-v2 state.

---

### `state_manager.py` — `load_state` resolves `_resolved_contracts` (D-14)

**Analog:** `state_manager.load_state` (lines 302-353)

**Current shape — happy path end (lines 350-353):**
```python
  # Happy path: migrate, then D-18 validate, then return
  state = _migrate(state)
  _validate_loaded_state(state)           # D-18: raises ValueError on missing keys
  return state
```

**Pattern to ADD after `_validate_loaded_state` call:**
```python
  # D-14 (Phase 8): resolve tier labels to {multiplier, cost_aud} via
  # system_params.SPI_CONTRACTS / AUDUSD_CONTRACTS. Underscore prefix =
  # runtime-only; excluded from save_state per save whitelist (see D-14).
  state['_resolved_contracts'] = {
    'SPI200':  system_params.SPI_CONTRACTS[state['contracts']['SPI200']],
    'AUDUSD':  system_params.AUDUSD_CONTRACTS[state['contracts']['AUDUSD']],
  }
  return state
```

**Hex-boundary note:** `state_manager` already imports `INITIAL_ACCOUNT`, `MAX_WARNINGS`, `STATE_FILE`, `STATE_SCHEMA_VERSION` from `system_params` (lines 48-53). Adding `SPI_CONTRACTS` + `AUDUSD_CONTRACTS` to that same import block preserves the hex rule.

---

### `state_manager.py` — `save_state` excludes underscore-prefixed keys (D-14)

**Analog:** `state_manager.save_state` (lines 355-369)

**Current implementation (lines 367-369):**
```python
  data = json.dumps(state, sort_keys=True, indent=2, allow_nan=False)
  _atomic_write(data, path)
```

**Pattern to REPLACE with underscore-prefix filter:**
```python
  # D-14 (Phase 8): strip runtime-only keys (underscore-prefixed) before
  # dumping. `_resolved_contracts` is the first underscore-prefixed key;
  # the convention is load-time materialization only.
  persisted = {k: v for k, v in state.items() if not k.startswith('_')}
  data = json.dumps(persisted, sort_keys=True, indent=2, allow_nan=False)
  _atomic_write(data, path)
```

**Documentation hook:** update the function docstring (lines 356-367) to document the underscore-prefix exclusion rule. CLAUDE.md §Conventions should also be extended — see D-14 "new convention this phase; document in CLAUDE.md."

---

### `state_manager.py` — `append_warning` (D-08, unchanged signature)

**Analog:** `state_manager.append_warning` (lines 371-399)

**Full existing function (use VERBATIM — no modifications needed in Phase 8):**
```python
def append_warning(state: dict, source: str, message: str, now=None) -> dict:
  '''D-09 / D-10 / D-11: append {date, source, message}; FIFO trim to MAX_WARNINGS.
  ...
  '''
  if now is None:
    now = datetime.now(UTC)
  today_awst = now.astimezone(_AWST).strftime('%Y-%m-%d')
  entry = {'date': today_awst, 'source': source, 'message': message}
  state['warnings'] = state['warnings'][-(MAX_WARNINGS - 1):] + [entry]
  return state
```

**Usage pattern the planner must apply in `main.py` for D-08 (notifier 5xx → warning):**
```python
# In run_daily_check, after _send_email_never_crash returns a status tuple:
send_status = _send_email_never_crash(...)  # returns e.g. (ok: bool, reason: str | None)
if not send_status.ok:
  state = state_manager.append_warning(
    state, source='notifier',
    message=f'Previous email send failed: {send_status.reason}',
  )
  # NOTE: if save_state has already happened earlier in Phase 8 D-02 flow,
  # the planner must call save_state again here; the orchestrator is the
  # sole writer per D-10.
```

**Critical constraint:** notifier must NOT call `append_warning` directly — D-10 preserves `state_manager` as sole writer. Notifier returns a status tuple; orchestrator translates.

---

### `state_manager.py` — optional `clear_warnings` helper (D-02)

**Analog:** `state_manager.append_warning` + `record_trade` (both are "mutate-state-and-return" helpers, lines 371-399, 401-435)

**D-02 flow:** After `save_state(state)` in `run_daily_check`, clear `state['warnings']` for the NEXT run. Preserves D-10 sole-writer invariant by going through state_manager.

**Pattern (mirror the append_warning shape):**
```python
def clear_warnings(state: dict) -> dict:
  '''D-02 (Phase 8): clear state['warnings'] after the current run's email
  has been built. Preserves D-10 sole-writer invariant: state_manager is
  the only module that mutates state['warnings'].

  Intended flow in main.run_daily_check:
    1. Build email payload reading state['warnings'] as-of run start.
    2. Persist state via save_state.
    3. Clear warnings via clear_warnings(state) + save_state again
       (the notifier 5xx → append_warning path still writes to the now-empty
       list, which next run will surface).
  '''
  state['warnings'] = []
  return state
```

**Planner-choice point:** D-03 notifier-side age filter already limits rendered warnings to `date == prior_run_date`. The planner must decide whether `clear_warnings` is truly needed OR whether leaving all warnings in `state['warnings']` (with notifier filtering by date) is sufficient. CONTEXT.md D-02 step 2 explicitly says "with the cleared warnings list (or a new `clear_warnings(state)` helper)" — both options are open.

---

### `notifier.py` — two-tier banner in `_render_header_email` (D-01, D-03)

**Analog:** `notifier._render_header_email` (lines 455-496) + `_render_action_required_email` (lines 499-574)

**Current `_render_header_email` body (lines 455-496):** renders `<h1>Trading Signals</h1>` + subtitle + `Last updated` timestamp + signal-as-of line. Pattern: returns a single `<tr><td>...</td></tr>\n<tr><td height="32">...</td></tr>\n` block. Inline style strings use palette constants (`_COLOR_TEXT`, `_COLOR_TEXT_MUTED`, etc.).

**Banner precedent — ACTION REQUIRED block (lines 561-574):**
```python
return (
  f'<tr><td style="padding:12px 16px;background:{_COLOR_SURFACE};'
  f'border-left:4px solid {_COLOR_SHORT};'     # ← red left border
  f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
  f'Roboto,sans-serif;font-size:14px;color:{_COLOR_TEXT};'
  f'line-height:1.5;">'
  f'<p style="margin:0 0 8px 0;font-size:20px;font-weight:700;'
  f'color:{_COLOR_TEXT};letter-spacing:0.02em;">'
  f'━━━ ACTION REQUIRED ━━━</p>'
  f'{body_items}'
  f'</td></tr>\n'
  f'<tr><td height="32" style="height:32px;font-size:0;line-height:0;">'
  f'&nbsp;</td></tr>\n'
)
```

**Pattern the planner must REPLICATE for D-01 (two-tier banners):**
- **Top-banner (critical):** red/orange `border-left:4px solid {_COLOR_SHORT}` (for ERR-05 stale-state) or `border-left:4px solid #eab308` (`_COLOR_FLAT` for ERR-03 corrupt-reset — pick between these; CONTEXT.md D-01 says "red/orange tone"). Placement: prepended to `_render_header_email` return value (before the `<h1>Trading Signals</h1>` card).
- **Routine warnings (below hero):** compact metadata row — single-line `<p>N warnings from prior run — see details</p>` followed by a `<ul>` or stacked `<div>` list of the filtered entries. Use `_COLOR_TEXT_MUTED` + `font-size:12px` for the compact line and `_COLOR_TEXT_DIM` for each entry.

**Age filter (D-03):** `_render_header_email` must now read `state['warnings']` and derive `prior_run_date` from `state['last_run']` BEFORE this run's save:
```python
prior_run_date = state.get('last_run')   # ISO YYYY-MM-DD or None
if prior_run_date:
  surfaced = [w for w in state.get('warnings', []) if w['date'] == prior_run_date]
else:
  surfaced = []  # first run — no prior warnings exist
```
Then partition `surfaced` into critical (by `source` or by a marker in `message`) vs routine. CONTEXT.md D-03 flags this: operator must choose the discriminator — `source == 'state_manager'` catches ERR-03 corrupt-reset; ERR-05 stale requires a new source tag (`source='staleness'` suggestion for the planner).

**XSS posture (preserved):** every dynamic value flows through `html.escape(value, quote=True)` at leaf render site (Phase 5 D-15). Inline `style='...'` — NO `<style>` block (email-client compat).

---

### `notifier.py` — subject-line `[!]` prefix (D-04)

**Analog:** `notifier.compose_email_subject` (lines 284-352), specifically the `[TEST]` prefix pattern at lines 345-352:
```python
core = (
  f'{emoji} {date_label} — SPI200 {spi_label}, '
  f'AUDUSD {audusd_label} — Equity {equity_str}'
)
if is_test:
  return f'[TEST] {core}'
return core
```

**Pattern to REPLICATE for `[!]` prefix:**
`compose_email_subject` must gain access to state['warnings'] (or take a derived `has_critical_banner: bool` argument from the orchestrator). Subject assembly becomes:
```python
prefix_parts: list[str] = []
if is_test:
  prefix_parts.append('[TEST]')
if has_critical_banner:        # D-04: stale-state OR corrupt-reset
  prefix_parts.append('[!]')
prefix = ' '.join(prefix_parts)
if prefix:
  return f'{prefix} {core}'
return core
```

**Signature extension:** `compose_email_subject(state, old_signals, is_test=False, has_critical_banner=False)` — default `False` keeps existing callers working. Alternative (cleaner per CONTEXT.md): derive `has_critical_banner` INSIDE the function from `state['warnings']` using the same D-03 age filter — planner's choice.

---

### `notifier.py` — always-write `last_email.html` (D-02)

**Analog:** `notifier.send_daily_email` (lines 1156-1205), specifically the RESEND_API_KEY-missing branch (lines 1173-1189):
```python
api_key = os.environ.get('RESEND_API_KEY')
if not api_key:
  # NOTF-08 fallback: write last_email.html for operator preview.
  last_email_path = Path('last_email.html')
  try:
    _atomic_write_html(html_body, last_email_path)
  except Exception as e:
    logger.warning(
      '[Email] WARN unexpected failure: %s: %s', type(e).__name__, e,
    )
    return 0
  logger.warning(
    '[Email] WARN RESEND_API_KEY missing — wrote %s (fallback)',
    last_email_path,
  )
  return 0
```

**Pattern to RESTRUCTURE for D-02 (always-write):**
Extract the `_atomic_write_html` call UP to BEFORE the api_key check, so every send path writes the disk snapshot:
```python
subject = compose_email_subject(...)
html_body = compose_email_body(...)

# D-02 (Phase 8): write last_email.html EVERY run, regardless of api_key
# presence or Resend success. Operator grep-recovery source of truth.
last_email_path = Path('last_email.html')
try:
  _atomic_write_html(html_body, last_email_path)
except Exception as e:
  logger.warning('[Email] WARN last_email.html write failed: %s: %s', type(e).__name__, e)
  # Continue — disk write failure must not block Resend dispatch.

api_key = os.environ.get('RESEND_API_KEY')
if not api_key:
  logger.warning('[Email] WARN RESEND_API_KEY missing — skipping Resend POST')
  return <status_tuple_success_with_reason='no_api_key'>

# ... existing Resend dispatch path (lines 1191-1204) ...
```

---

### `notifier.py` — status-tuple return on failure (D-08)

**Analog:** `notifier.send_daily_email` current signature (line 1161): `-> int` returning 0 always.

**Pattern the planner must REPLACE (orchestrator needs failure discrimination for D-08):**
```python
# Option A: named tuple
from typing import NamedTuple
class SendStatus(NamedTuple):
  ok: bool
  reason: str | None   # None on success; short human-readable on failure

# Option B: plain tuple  (ok, reason)

def send_daily_email(state, old_signals, now, is_test=False) -> SendStatus:
  '''... returns SendStatus(ok, reason). NEVER raises.'''
  ...
  try:
    _post_to_resend(api_key, _EMAIL_FROM, to_addr, subject, html_body)
    logger.info('[Email] sent to %s subject=%r', to_addr, subject)
    return SendStatus(ok=True, reason=None)
  except ResendError as e:
    logger.warning('[Email] WARN send failed: %s', e)
    return SendStatus(ok=False, reason=str(e)[:200])  # clipped + api_key already redacted by _post_to_resend
  except Exception as e:
    logger.warning('[Email] WARN unexpected failure: %s: %s', type(e).__name__, e)
    return SendStatus(ok=False, reason=f'{type(e).__name__}: {e}'[:200])
```

**Call-site ripple:** `main._send_email_never_crash` (lines 123-147) currently ignores the return. It must now capture + return the status tuple up to `run_daily_check` so the orchestrator can `append_warning` on failure. All existing tests calling `send_daily_email` and asserting `rc == 0` (test_notifier.py `TestSendDispatch` lines 965-1090) must be updated to `result.ok is True/False`.

---

### `main.py` — outer crash-email boundary (D-05, D-06, D-07)

**Analog:** `main.main` typed-exception boundary (lines 883-916) — already catches `DataFetchError`/`ShortFrameError` and a catch-all `Exception`:
```python
try:
  if args.reset:
    return _handle_reset()
  if args.force_email or args.test:
    ...
  if args.once:
    ...
  # Default (no flag): Phase 7 D-04 + D-05 — immediate first run, then loop.
  _run_daily_check_caught(run_daily_check, args)
  return _run_schedule_loop(run_daily_check, args)
except (DataFetchError, ShortFrameError) as e:
  logger.error('[Fetch] ERROR: %s', e)
  return 2
except Exception as e:
  logger.error(
    '[Sched] ERROR: unexpected crash: %s: %s', type(e).__name__, e,
  )
  return 1
```

**Pattern the planner must REPLICATE for D-05 Layer B:** the existing `except Exception` block at lines 912-916 is EXACTLY the seam. Extend it — do NOT add a second outer try/except (that duplicates Layer A). The logic becomes:
```python
except Exception as e:
  logger.error(
    '[Sched] ERROR: unexpected crash: %s: %s', type(e).__name__, e,
  )
  # D-05 / D-06 / D-07 (Phase 8): fire one last crash email before exit.
  # Reuses _post_to_resend retry loop (3 retries, flat backoff) per D-07.
  # This call is wrapped in a nested try/except so a crash-email dispatch
  # failure does NOT mask the original error's return code.
  try:
    _send_crash_email(e)
  except Exception as crash_email_err:
    logger.error(
      '[Email] ERROR: crash-email dispatch also failed: %s: %s',
      type(crash_email_err).__name__, crash_email_err,
    )
  return 1
```

**New helper `_send_crash_email(exc: Exception)`** (D-06 body):
```python
def _send_crash_email(exc: Exception) -> None:
  '''D-05 / D-06 / D-07 (Phase 8): text/plain crash email with traceback +
  last-known state summary. Reuses _post_to_resend retry loop (30s max).

  Subject: [CRASH] Trading Signals — <ISO date>
  Body (text/plain):
    Timestamp: <ISO AWST>
    Exception: <class>: <message>
    Traceback:
      <full traceback.format_exc output>
    State summary:
      signals: SPI200=<L/S/F>, AUDUSD=<L/S/F>
      account: $<X,XXX.XX>
      positions:
        SPI200: <LONG/SHORT> <N>@<entry>  (or "(none)")
        AUDUSD: ...
  '''
```

**D-06 constraint:** body is text/plain (NOT HTML) + derived state summary only (NO `trade_log`, `equity_history`, `warnings` dumps — email size + PII constraint).

**D-07 constraint:** crash-email dispatch uses the SAME `_post_to_resend` retry loop. Planner must decide whether to call `notifier._post_to_resend` directly (cross-hex but clean) OR add a new `notifier.send_crash_email(exc)` public function (preserves hex). Recommendation: add `notifier.send_crash_email` — symmetric with `send_daily_email`.

---

### `main.py` — interactive reset Q&A (D-09, D-10, D-12, D-13)

**Analog:** `main._handle_reset` (lines 801-832):
```python
def _handle_reset() -> int:
  '''CLI-02: reinitialise state.json to fresh $100k after operator confirmation.

  Confirmation rules:
    - If env var RESET_CONFIRM=='YES' (stripped), skip the interactive prompt.
    - Else interactive: input('Type YES to confirm reset: '); catch EOFError
      (non-interactive stdin = cancellation, not a crash).
  ...
  '''
  confirm = os.getenv('RESET_CONFIRM', '').strip()
  if confirm != 'YES':
    try:
      confirm = input('Type YES to confirm reset: ').strip()
    except EOFError:
      confirm = ''
  if confirm != 'YES':
    logger.info('[State] --reset cancelled by operator')
    return 1
  state = state_manager.reset_state()
  state_manager.save_state(state)
  logger.info('[State] state.json reset to fresh $100k account')
  return 0
```

**Pattern the planner must REPLICATE for D-09 Q&A + D-12 preview + D-13 non-TTY guard:**
```python
def _handle_reset(args: argparse.Namespace) -> int:
  '''CLI-02 + Phase 8 D-09/D-10/D-11/D-12/D-13: accepts --initial-account /
  --spi-contract / --audusd-contract OR prompts interactively when any flag
  is missing on a TTY. Non-TTY + missing flags -> parser.error (D-13).
  '''
  # D-13: non-TTY guard — must run FIRST, before any input() call.
  has_explicit_flags = (
    args.initial_account is not None
    and args.spi_contract is not None
    and args.audusd_contract is not None
  )
  if not has_explicit_flags and not sys.stdin.isatty():
    # Mirrors _validate_flag_combo.parser.error exit-code-2 convention.
    print(
      '[State] ERROR: Non-interactive shell detected. Pass '
      '--initial-account <N> --spi-contract <label> --audusd-contract <label> '
      'explicitly.',
      file=sys.stderr,
    )
    return 2

  # D-09: interactive prompts per missing flag.
  initial_account = args.initial_account
  if initial_account is None:
    raw = input('Starting account [$100,000]: ').strip()
    if raw.lower() == 'q':
      logger.info('[State] --reset cancelled by operator')
      return 1
    if raw == '':
      initial_account = system_params.INITIAL_ACCOUNT
    else:
      # Strip $ and commas per D-09.
      cleaned = raw.lstrip('$').replace(',', '')
      try:
        initial_account = float(cleaned)
      except ValueError:
        print(f'[State] ERROR: invalid account value {raw!r}', file=sys.stderr)
        return 1
      if initial_account < 1000:
        print('[State] ERROR: --initial-account must be at least $1,000', file=sys.stderr)
        return 1

  # ... similar blocks for spi_contract and audusd_contract with D-11 label validation ...

  # D-12: preview + confirmation.
  try:
    current = state_manager.load_state()
  except Exception:
    current = None   # first-run / corrupt — preview shows "(no current state.json)"

  print('This will replace state.json. New values:')
  print(f'  initial_account: ${initial_account:,.2f}')
  print( '  contracts:')
  print(f'    SPI200:  {spi_contract}')
  print(f'    AUDUSD:  {audusd_contract}')
  if current is not None:
    print('Current state.json:')
    print(f'  initial_account: ${current.get("initial_account", system_params.INITIAL_ACCOUNT):,.2f} '
          f'({"migrated default" if "initial_account" not in current else "on disk"})')
    print(f'  last_run: {current.get("last_run")}')
    print(f'  trades: {len(current.get("trade_log", []))}')

  confirm = os.getenv('RESET_CONFIRM', '').strip()
  if confirm != 'YES':
    try:
      confirm = input('Type YES to confirm, anything else to cancel: ').strip()
    except EOFError:
      confirm = ''
  if confirm != 'YES':
    logger.info('[State] --reset cancelled by operator')
    return 1

  # Build + save new state.
  state = state_manager.reset_state()
  state['initial_account'] = initial_account
  state['contracts'] = {'SPI200': spi_contract, 'AUDUSD': audusd_contract}
  state_manager.save_state(state)
  logger.info(
    '[State] state.json reset (initial_account=$%.2f, SPI200=%s, AUDUSD=%s)',
    initial_account, spi_contract, audusd_contract,
  )
  return 0
```

**D-10 argparse flags** — add to `_build_parser` (lines 258-286) mirroring the existing `action='store_true'` pattern:
```python
p.add_argument(
  '--initial-account', type=float, default=None,
  help='Starting account balance for --reset (Phase 8 CONF-01). '
       'Min $1,000, no ceiling. Interactive prompt if omitted on TTY.',
)
p.add_argument(
  '--spi-contract', type=str, default=None,
  choices=list(system_params.SPI_CONTRACTS.keys()),
  help='SPI 200 contract preset for --reset (Phase 8 CONF-02). '
       'Interactive prompt if omitted on TTY.',
)
p.add_argument(
  '--audusd-contract', type=str, default=None,
  choices=list(system_params.AUDUSD_CONTRACTS.keys()),
  help='AUD/USD contract preset for --reset (Phase 8 CONF-02).',
)
```

**D-09 flag-combo rule (relaxation):** Update `_validate_flag_combo` (lines 289-297):
```python
def _validate_flag_combo(args, parser) -> None:
  '''D-05 (Phase 4): --reset is strictly exclusive WITH RESPECT TO --test /
  --force-email / --once. D-09 (Phase 8): --initial-account, --spi-contract,
  --audusd-contract ARE allowed alongside --reset.
  '''
  if args.reset and (args.test or args.force_email or args.once):
    parser.error('--reset cannot be combined with --test/--force-email/--once')
  # Phase 8: reset-only companion flags cannot appear WITHOUT --reset.
  reset_only = (args.initial_account is not None
                or args.spi_contract is not None
                or args.audusd_contract is not None)
  if reset_only and not args.reset:
    parser.error('--initial-account / --spi-contract / --audusd-contract '
                 'require --reset')
```

---

### `system_params.py` — `SPI_CONTRACTS` / `AUDUSD_CONTRACTS` dicts (D-11)

**Analog:** existing scalar constants in same file (lines 62-68):
```python
# SPI 200 mini: $5/pt, $6 AUD RT (split $3 on open + $3 on close per D-13)
SPI_MULT: float = 5.0
SPI_COST_AUD: float = 6.0       # round-trip; half deducted on open, half on close

# AUD/USD: $10,000 notional, $5 AUD RT (split $2.50 on open + $2.50 on close)
AUDUSD_NOTIONAL: float = 10000.0
AUDUSD_COST_AUD: float = 5.0    # round-trip; half deducted on open, half on close
```

**Pattern to ADD (D-11 baseline — exact label strings TBD with operator during planning):**
```python
# =========================================================================
# Phase 8 constants — contract tier presets (D-11, CONF-02)
# =========================================================================
# Label vocabulary: instrument-prefixed (self-documenting on CLI, e.g.
# --spi-contract spi-mini). Tier multiplier + cost values per Phase 2 D-11
# unless operator corrects during planning — see CONTEXT.md D-11.

SPI_CONTRACTS: dict[str, dict[str, float]] = {
  'spi-mini':     {'multiplier': 5.0,  'cost_aud': 6.0},    # current default
  'spi-standard': {'multiplier': 25.0, 'cost_aud': 30.0},
  'spi-full':     {'multiplier': 50.0, 'cost_aud': 50.0},
}

AUDUSD_CONTRACTS: dict[str, dict[str, float]] = {
  'audusd-standard': {'multiplier': 10000.0, 'cost_aud': 5.0},   # current default
  'audusd-mini':     {'multiplier': 1000.0,  'cost_aud': 0.5},
}

# D-11: default labels used by _migrate (Phase 8 v1→v2) when state.json is
# missing 'contracts'. Must match an entry in the above dicts.
_DEFAULT_SPI_LABEL: str = 'spi-mini'
_DEFAULT_AUDUSD_LABEL: str = 'audusd-standard'
```

**Backward-compat guarantee:** The existing scalar constants `SPI_MULT` / `SPI_COST_AUD` / `AUDUSD_NOTIONAL` / `AUDUSD_COST_AUD` should NOT be deleted — they are imported by `main.py` (lines 50-55), `notifier.py` (lines 70-77), `dashboard.py` (line 94 area). Keeping them is also required for tests that still import by name. Planner decides: (a) leave them as aliases of `SPI_CONTRACTS['spi-mini']['multiplier']` etc., OR (b) deprecate-in-place with no-op aliases. Option (a) is lower-risk.

**AST blocklist check:** `sizing_engine.py` must NOT import `SPI_CONTRACTS` (D-17 hex rule — sizing stays pure, receives resolved values as scalar args). Add to `tests/test_signal_engine.py::TestDeterminism` forbidden-imports check if not already covered.

---

### `dashboard.py` — total-return uses `state.get('initial_account', ...)` (D-16)

**Analog:** `dashboard._compute_total_return` (lines 487-495):
```python
def _compute_total_return(state: dict) -> str:
  '''CONTEXT D-10: (current_equity - INITIAL_ACCOUNT) / INITIAL_ACCOUNT * 100. Always defined.'''
  eq_hist = state.get('equity_history', [])
  if eq_hist:
    current = eq_hist[-1].get('equity', state.get('account', INITIAL_ACCOUNT))
  else:
    current = state.get('account', INITIAL_ACCOUNT)
  total_return = (current - INITIAL_ACCOUNT) / INITIAL_ACCOUNT
  return f'{total_return * 100:+.1f}%'
```

**Pattern to REPLACE (D-16 — inline `state.get('initial_account', INITIAL_ACCOUNT)`):**
```python
def _compute_total_return(state: dict) -> str:
  '''D-16 (Phase 8): use state['initial_account'] as the baseline; fall
  through to system_params.INITIAL_ACCOUNT for pre-Phase-8 state that
  missed the _migrate v2 backfill (defense-in-depth).
  '''
  initial = state.get('initial_account', INITIAL_ACCOUNT)
  eq_hist = state.get('equity_history', [])
  if eq_hist:
    current = eq_hist[-1].get('equity', state.get('account', initial))
  else:
    current = state.get('account', initial)
  total_return = (current - initial) / initial
  return f'{total_return * 100:+.1f}%'
```

**Call-site audit (per CONTEXT.md D-16):** planner must `grep -n "INITIAL_ACCOUNT" dashboard.py notifier.py main.py sizing_engine.py` and apply the same fallback pattern at any other account-growth calculation site. Per notifier.py line 72, `INITIAL_ACCOUNT` is imported but I did not find a P&L reference — planner should confirm during discovery.

---

### `tests/test_state_manager.py` — `TestWarnings` extensions (D-02, D-08, D-14, D-15)

**Analog class:** `TestWarnings` (lines 901-953) — existing tests already cover basic shape, AWST date, FIFO trim, return-mutated-state.

**Test pattern precedent:**
```python
def test_append_warning_basic_shape(self) -> None:
  state = reset_state()
  fixed_now = datetime(2026, 4, 21, 9, 30, 0, tzinfo=UTC)
  state = append_warning(state, 'sizing_engine', 'size=0: vol_scale clip', now=fixed_now)
  assert len(state['warnings']) == 1
  warning = state['warnings'][0]
  assert set(warning.keys()) == {'date', 'source', 'message'}
  assert warning['date'] == '2026-04-21'
  ...
```

**New tests the planner must add (all following the `fixed_now = datetime(..., tzinfo=UTC)` clock-injection pattern):**
- `TestClearWarnings` (if D-02 helper chosen) — `clear_warnings(state)` empties `state['warnings']` AND leaves other keys untouched.
- `TestMigrateV2Backfill` inside `TestSchemaVersion` class (lines 955+) — v1 state on disk with no `initial_account` key → `_migrate` fills default (`INITIAL_ACCOUNT`), no warning appended (D-15 silent).
- `TestSaveStateExcludesResolvedContracts` inside `TestLoadSave` (line 91) — writes a state with `_resolved_contracts` populated; reads the on-disk JSON via `json.loads(path.read_text())`; asserts the underscore key is absent.
- `TestLoadStateResolvesContracts` — saves a state with `contracts = {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'}`; calls `load_state(path=...)`; asserts `loaded['_resolved_contracts']['SPI200'] == {'multiplier': 5.0, 'cost_aud': 6.0}`.

---

### `tests/test_notifier.py` — banner + age-filter + last_email.html always-write + crash-email (D-01, D-02, D-03, D-04, D-08)

**Analog class:** `TestSendDispatch` (lines 965-1090) + `TestResendPost` (lines 711-963) + module-level `_FakeResp` (lines 692-708).

**`_FakeResp` pattern (line 692-708) — reuse VERBATIM for crash-email tests:**
```python
class _FakeResp:
  def __init__(self, status_code: int, text: str = 'ok') -> None:
    self.status_code = status_code
    self.text = text
  def raise_for_status(self) -> None:
    if self.status_code == 429 or self.status_code >= 500:
      raise requests.exceptions.HTTPError(f'{self.status_code}', response=self)
```

**Existing NOTF-08 fallback test (lines 971-981) — pattern for D-02 "always write":**
```python
def test_missing_api_key_writes_last_email_html(self, tmp_path, monkeypatch) -> None:
  monkeypatch.chdir(tmp_path)
  monkeypatch.delenv('RESEND_API_KEY', raising=False)
  state = json.loads(SAMPLE_STATE_NO_CHANGE_PATH.read_text())
  rc = send_daily_email(state, {'^AXJO': 1, 'AUDUSD=X': 0}, FROZEN_NOW)
  assert rc == 0
  last = tmp_path / 'last_email.html'
  assert last.exists(), 'NOTF-08: must write last_email.html when key missing'
  assert last.read_text(encoding='utf-8').startswith('<!DOCTYPE html>')
```

**New tests the planner must add (all using `monkeypatch.chdir(tmp_path)` + `monkeypatch.setenv/delenv` + `_FakeResp` + `FROZEN_NOW` constant):**
- `test_last_email_html_written_on_successful_send` — set `RESEND_API_KEY='k'`; monkeypatch `requests.post` to return `_FakeResp(200)`; assert `last_email.html` exists after send.
- `test_last_email_html_written_on_5xx_failure` — monkeypatch to return `_FakeResp(500)`; assert file exists AND send returned the failure status tuple.
- `test_send_daily_email_returns_status_tuple` — assert `result.ok is True` on 200, `result.ok is False` + `reason` contains '4xx' on `_FakeResp(400)`.
- `test_render_header_banner_critical_stale_state_red_border` — build a state dict with a `warnings` entry dated to `state['last_run']` and tagged `source='staleness'`; assert output contains `border-left:4px solid` red tone AND the banner text.
- `test_render_header_banner_routine_warning_compact_row` — similar but `source='sizing_engine'`; assert compact metadata row appears.
- `test_render_header_age_filter_ignores_older_warnings` — create 2 warnings, one dated 2 runs ago, one dated `state['last_run']`; assert only the prior-run one appears.
- `test_subject_bang_prefix_only_on_critical_banner` — state with ERR-05 staleness warning dated prior run → subject starts with `[!] `; state with only routine warnings → subject has NO `[!]`.

**Crash-email tests (D-05, D-06, D-07):** add `TestCrashEmail` class following `TestResendPost` monkeypatch-requests-post pattern:
- `test_crash_email_subject_starts_with_bracket_crash` — assert subject format `[CRASH] Trading Signals — <YYYY-MM-DD>`.
- `test_crash_email_body_contains_traceback_and_state_summary` — assert body contains `Traceback`, exception class name, `account:`, `positions:`, but NOT `trade_log`, NOT `equity_history`, NOT `warnings`.
- `test_crash_email_retries_on_5xx` — `_FakeResp(500 if len(calls) == 1 else 200)` shape copied from `test_5xx_500_retries_then_success` (lines 810-823).

---

### `tests/test_main.py` — interactive reset Q&A + crash-email boundary (D-05, D-09, D-12, D-13)

**Analog class:** `TestCLI` (line 97 onward) — existing pattern at lines 218-269:
```python
def test_reset_with_confirmation_writes_fresh_state(self, tmp_path, monkeypatch) -> None:
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
  ...
  monkeypatch.setenv('RESET_CONFIRM', 'YES')
  rc = main.main(['--reset'])
  assert rc == 0
  ...

def test_reset_without_confirmation_does_not_write(self, tmp_path, monkeypatch, caplog) -> None:
  ...
  monkeypatch.setattr('builtins.input', lambda prompt: 'no')
  rc = main.main(['--reset'])
  assert rc == 1
  ...
  assert '--reset cancelled by operator' in caplog.text
```

**New tests the planner must add (extending `TestCLI`):**
- `test_reset_with_all_flags_skips_prompts` — `main.main(['--reset', '--initial-account', '50000', '--spi-contract', 'spi-mini', '--audusd-contract', 'audusd-standard'])` with `RESET_CONFIRM=YES`; assert state.json has `initial_account == 50000.0` and correct contract labels.
- `test_reset_interactive_q_and_a_stdin_inputs` — monkeypatch `builtins.input` with a queue/iterator: `iter(['50000', 'spi-mini', 'audusd-standard', 'YES'])`; assert state.json reflects the inputs.
- `test_reset_non_tty_without_flags_errors` — `monkeypatch.setattr('sys.stdin.isatty', lambda: False)`; `main.main(['--reset'])`; assert exit code 2 (argparse-error convention) AND stderr contains "Non-interactive shell detected".
- `test_reset_initial_account_below_1000_rejected` — `main.main(['--reset', '--initial-account', '999', ...])`; assert non-zero exit + error message.
- `test_reset_invalid_spi_label_rejected` — `main.main(['--reset', '--spi-contract', 'spi-made-up'])`; argparse's `choices=` auto-rejects with exit code 2.
- `test_reset_preview_shown_before_confirm_prompt` — use capsys to capture stdout; assert both "New values:" and "Current state.json:" blocks appear before `input()` is called.

**New test class `TestCrashEmailBoundary`** (mirroring `TestEmailNeverCrash` at lines 1002-1067):
- `test_unhandled_exception_inside_loop_fires_crash_email` — monkeypatch `main._run_schedule_loop` to raise `RuntimeError('boom')`; monkeypatch `notifier.send_crash_email` to record the call; `main.main([])`; assert exit code 1 AND crash_email called with the exception.
- `test_unhandled_exception_in_force_email_path_fires_crash_email` — same but wraps the `--force-email` branch.
- `test_typed_exception_does_NOT_fire_crash_email` — raise `DataFetchError`; assert crash_email NOT called (typed exceptions stay with their exit-code-2 branch, unchanged from Phase 7).
- `test_crash_email_dispatch_failure_does_not_mask_original_exit_code` — crash-email itself raises; assert final exit code is still 1.

---

### `tests/test_scheduler.py` — Layer B wraps loop-driver crash (D-05)

**Analog class:** `TestLoopErrorHandling` (line 240 onward) + `TestLoopDriver` (line 186 onward).

**Existing pattern — `TestLoopErrorHandling` (lines 243-275):**
```python
def test_unexpected_exception_caught(self, caplog) -> None:
  def _raising_job(args):
    raise RuntimeError('boom')
  main_module._run_daily_check_caught(_raising_job, argparse.Namespace())
  assert '[Sched] unexpected error caught' in caplog.text
  # No assertion on rc — _run_daily_check_caught returns None (per-job wrapper).
```

**New test (extending a new class `TestCrashEmailLayerB` or adding to `TestLoopDriver`):**
- `test_assertion_error_in_loop_driver_propagates_to_main_catch_all` — patch `_get_process_tzname` to return `'AEST'`; call `main.main([])`; assert the `AssertionError` from `_run_schedule_loop` (line 233) is caught by `main()`'s outer `except Exception` (lines 912-916) AND crash-email dispatch is triggered.
- `test_layer_a_and_layer_b_do_not_duplicate_error_logging` — inject a per-job raise; assert `[Sched] unexpected error caught in loop` appears exactly ONCE in caplog (Layer A) and NO `[Sched] ERROR: unexpected crash` line (Layer B, which would only fire on a LOOP-DRIVER crash, not a per-job crash).

**Pattern for the `_FakeScheduler` (lines 21-53)** — reuse directly; no changes needed.

---

## Shared Patterns

### Log-prefix discipline

**Source:** `CLAUDE.md` §Conventions ("Log prefixes: `[Signal]`, `[State]`, `[Email]`, `[Sched]`, `[Fetch]`")

**Apply to all new log lines in Phase 8:**
- `[State]` for `state_manager` additions (e.g., `_migrate` backfill silent — so no log) and `main._handle_reset` post-success log (line 831 precedent)
- `[Email]` for `notifier` additions (banner logging, crash-email dispatch) — precedent at line 1186: `'[Email] WARN RESEND_API_KEY missing — wrote %s (fallback)'`
- `[Sched]` for `main` orchestrator crash logs — precedent at line 914: `'[Sched] ERROR: unexpected crash: %s: %s'`

**Concrete example (from `notifier.send_daily_email` lines 1185-1187):**
```python
logger.warning(
  '[Email] WARN RESEND_API_KEY missing — wrote %s (fallback)',
  last_email_path,
)
```

### Never-crash-on-email wrapper pattern

**Source:** `main._send_email_never_crash` (lines 123-147) + `main._render_dashboard_never_crash` (lines 98-116)

**Apply to:** the new `_send_crash_email` wrapper in `main.py`. The SAME `try: import notifier` INSIDE the helper body discipline must be followed so import-time failures in notifier are caught by the SAME `except Exception` as runtime failures (C-2 reviews precedent locked in Phase 5).

**Excerpt — C-2 precedent (lines 142-147):**
```python
try:
  import notifier  # local import — C-2 isolates import-time failures
  notifier.send_daily_email(state, old_signals, run_date, is_test=is_test)
except Exception as e:
  logger.warning('[Email] send failed: %s: %s', type(e).__name__, e)
```

### Atomic write pattern (tempfile + fsync + os.replace + fsync-parent-dir)

**Source:** `state_manager._atomic_write` (lines 88-133) + `notifier._atomic_write_html` (lines 1034-1073) — the two are structurally identical.

**Apply to:** If the planner adds any new disk-write site in Phase 8 (unlikely — all three targets reuse existing writers: `save_state`, `_atomic_write_html`), this is the template. NOT needed if only reusing `save_state` + `_atomic_write_html`.

**Excerpt — `_atomic_write_html` (lines 1048-1073):**
```python
parent = path.parent
tmp_path_str: str | None = None
try:
  with tempfile.NamedTemporaryFile(
    dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
    newline='\n',
  ) as tmp:
    tmp_path_str = tmp.name
    tmp.write(data)
    tmp.flush()
    os.fsync(tmp.fileno())
  os.replace(tmp_path_str, path)
  if os.name == 'posix':
    dir_fd = os.open(str(parent), os.O_RDONLY)
    try:
      os.fsync(dir_fd)
    finally:
      os.close(dir_fd)
  tmp_path_str = None
finally:
  if tmp_path_str is not None:
    try:
      os.unlink(tmp_path_str)
    except FileNotFoundError:
      pass
```

### Clock-injection for tests (D-08 precedent, Phase 3)

**Source:** `state_manager.append_warning(state, source, message, now=None)` — `now` defaults to `datetime.now(UTC)`; tests pass fixed UTC datetimes (test_state_manager.py line 910: `fixed_now = datetime(2026, 4, 21, 9, 30, 0, tzinfo=UTC)`).

**Apply to:** any Phase 8 helper that reads the wall clock (crash-email timestamp). Follow the same `now=None` default with `if now is None: now = datetime.now(UTC)` guard — lets tests inject frozen time without `pytest-freezer`.

**Excerpt — `append_warning` clock handling (lines 393-396):**
```python
if now is None:
  now = datetime.now(UTC)
today_awst = now.astimezone(_AWST).strftime('%Y-%m-%d')
```

### Typed-exception boundary in `main()` (Phase 4 D-11 precedent)

**Source:** `main.main` lines 883-916 — the exact seam where D-05 Layer B hooks in. Pattern: `try:` wraps the ENTIRE dispatch ladder (all three branches: `--reset`, `--force-email/--test`, `--once`/default); `except (DataFetchError, ShortFrameError)` → exit 2; `except Exception` → exit 1 + (D-05 new) crash-email dispatch.

**Already cited above — do NOT duplicate the try/except with a second outer wrapper.**

### pytest monkeypatch + `_FakeResp` for HTTPS tests

**Source:** `tests/test_notifier.py` `_FakeResp` (lines 692-708) + `TestResendPost.test_post_url_and_auth_header` (lines 719-745).

**Apply to:** all new Phase 8 crash-email dispatch tests. Target `notifier.requests.post` via `monkeypatch.setattr('notifier.requests.post', _fake_post)`. Always pass `backoff_s=0` in test args to keep tests < 1s.

### `monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)` (C-4 revision)

**Source:** All tests in `tests/test_main.py` that invoke `main.main(...)` AND assert on caplog (e.g., lines 120, 165, 204, 224, 252, 283, ...). Required so pytest's caplog handler is not ripped out by `basicConfig(force=True)`.

**Apply to:** every new Phase 8 test that invokes `main.main(...)` and asserts on log output. Copy the one-liner verbatim.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | | | All Phase 8 target files pre-exist. Every decision has a concrete analog. |

**Closest-to-no-analog areas** (planner must still do some creative work):
1. **Two-tier banner HTML structure** — D-01 visual design vocabulary. No prior banner outside `_render_action_required_email` (the ACTION REQUIRED block) — that's the single closest reference, but the layout is different (top banner vs in-flow section). Planner has discretion per CONTEXT.md "Claude's Discretion" on colour/padding/border weights.
2. **Non-TTY stdin guard** — `sys.stdin.isatty()` pattern is not used elsewhere in the codebase. Planner to introduce; consider a thin wrapper `main._stdin_isatty()` for test-patchability mirroring `_get_process_tzname` precedent (CONTEXT.md `<code_context>` §Established patterns flags this suggestion explicitly).
3. **Text/plain email body assembly** — notifier.py currently only produces HTML. Text/plain crash-email body is new territory. No `html` escaping needed for text/plain; use triple-quoted f-strings. `_post_to_resend` payload structure (line 1104-1109) currently only has `'html'` key; Resend also accepts `'text'` — planner must extend the function (or add a second `_post_to_resend_text`) to honour content-type for text/plain.

---

## Metadata

**Analog search scope:** all source files at repo root (`state_manager.py`, `notifier.py`, `main.py`, `system_params.py`, `dashboard.py`, `sizing_engine.py`) + all test files at `tests/*.py`.

**Files scanned:** 10 source/test + 4 prior CONTEXT.md files referenced (03/04/06/07).

**Pattern extraction date:** 2026-04-23.
