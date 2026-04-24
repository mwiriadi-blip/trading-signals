---
status: issues-found
files_reviewed: 10
files_reviewed_list:
  - system_params.py
  - state_manager.py
  - notifier.py
  - main.py
  - dashboard.py
  - tests/test_state_manager.py
  - tests/test_notifier.py
  - tests/test_main.py
  - tests/test_scheduler.py
  - tests/test_dashboard.py
depth: standard
phase: 08
reviewed_at: 2026-04-23
findings:
  critical: 0
  warning: 2
  info: 6
  total: 8
---

# Phase 8 Code Review

## Summary

Phase 8 hardening is well-executed: the warning-carry-over pipeline honours the
state_manager sole-writer invariant via `SendStatus` + orchestrator translation,
the underscore-key filter protects `_resolved_contracts` and `_stale_info` from
disk, the `math.isfinite` guard on `--initial-account` blocks NaN/inf (T-08-12),
and the crash-email path correctly passes `_LAST_LOADED_STATE` to
`_build_crash_state_summary`. Hex-lite boundaries are intact (grep-verified:
`signal_engine`/`sizing_engine`/`system_params` have no I/O imports;
`state_manager` does not import notifier/main; `notifier` imports only
`state_manager.load_state` for CLI convenience). No TODO/FIXME/HACK markers in
delivered code. Two Warnings worth addressing: dashboard + notifier inline P&L
helpers still reference the scalar `SPI_MULT`/`AUDUSD_NOTIONAL` constants via
`_CONTRACT_SPECS[_EMAIL]` rather than the operator-selected tier in
`state['_resolved_contracts']`, creating a display divergence against the
values `run_daily_check` uses; and the `_handle_reset` function is a 164-line
inline prompt/validate/preview block that would benefit from extraction.

## Critical Findings (CR-NN)

_None._

## Warning Findings (WR-NN)

### WR-01: Dashboard + notifier render unrealised P&L with hardcoded default-tier multipliers, ignoring operator's `--spi-contract`/`--audusd-contract` choice

**Files:**
- `dashboard.py:127-130, 538` (`_CONTRACT_SPECS`, `_compute_unrealised_pnl_display`)
- `notifier.py:134-137, 473` (`_CONTRACT_SPECS_EMAIL`, `_compute_unrealised_pnl_email`)

**Issue:** Both rendering hexes derive unrealised P&L from module-level
`_CONTRACT_SPECS[_EMAIL]` dicts that are built from the legacy scalar
constants (`SPI_MULT=5.0`, `SPI_COST_AUD=6.0`, `AUDUSD_NOTIONAL=10000.0`,
`AUDUSD_COST_AUD=5.0`) imported from `system_params.py`. Phase 8 CONF-02 lets
an operator pick any tier (e.g., `spi-standard` with `multiplier=25.0`,
`cost_aud=30.0`) via `--reset --spi-contract spi-standard`. The orchestrator
(`main.run_daily_check:862-864, 1004-1009`) correctly consumes
`state['_resolved_contracts'][state_key]` when calling `sizing_engine.step`
and `compute_unrealised_pnl`, so state mutations honour the tier. But
dashboard's `_compute_unrealised_pnl_display` and notifier's
`_compute_unrealised_pnl_email` continue to look up the default-tier scalars.

**Impact:** An operator who reset with a non-default SPI tier sees
dashboard/email unrealised P&L off by (tier_multiplier / 5.0) — for
spi-standard, the email shows 1/5 of the true P&L on the open SPI200
position. Silent correctness regression that a UI-level eyeball check would
not flag until running totals drift from reality. `run_daily_check`'s
equity-history numbers remain correct, so the bug presents as "dashboard
unrealised P&L != email header 'today's change'" on multi-tier accounts.
Phase 8 CONTEXT D-16 extended only `INITIAL_ACCOUNT` through
`state['initial_account']`; the parallel refactor for contract multipliers
was apparently not scoped into dashboard/notifier.

**Fix:** Source the multiplier/cost from `state['_resolved_contracts']` at
render time, with `state.get('_resolved_contracts', {}).get(state_key)`
fallback to the hardcoded `_CONTRACT_SPECS` pair for pre-Phase-8 state
shapes (defense-in-depth — `_migrate` backfills `contracts` but not
`_resolved_contracts`, which only exists post-`load_state`). Example:

```python
# dashboard.py (_compute_unrealised_pnl_display)
def _compute_unrealised_pnl_display(
  position: dict, state_key: str, current_close: float | None,
  state: dict,   # NEW: pass-through from render_positions_table
) -> float | None:
  if current_close is None:
    return None
  resolved = state.get('_resolved_contracts', {}).get(state_key)
  if resolved is not None:
    multiplier = resolved['multiplier']
    cost_aud_round_trip = resolved['cost_aud']
  else:
    multiplier, cost_aud_round_trip = _CONTRACT_SPECS[state_key]
  cost_aud_open = cost_aud_round_trip / 2
  # ... rest unchanged
```

Mirror the change in `notifier._compute_unrealised_pnl_email`. Add tests
that seed a non-default tier in state and assert the rendered P&L matches
the tier multiplier (e.g. spi-standard position of 2 contracts, entry=7000,
current=7100 → gross = 100 * 2 * 25.0 = 5000.0, not 500.0).

---

### WR-02: `_handle_reset` is a 164-line inline prompt/validate/preview block

**File:** `main.py:1065-1227`

**Issue:** `_handle_reset` contains the non-TTY guard, three inline
prompt-validate-cancel cycles (initial_account, spi-contract,
audusd-contract), preview rendering, YES confirmation, and final save in
one function body. The three prompt branches duplicate the
`try/except EOFError: raw='q' → 'q'/blank/value → validate → return 1`
shape nearly verbatim (lines 1109-1126, 1141-1163, 1165-1187). Deep
keyword-coupled flow makes the CONF-01 `math.isfinite` guard easy to miss
on future edits to sibling prompts.

**Impact:** Maintenance cost + divergence risk. If a fourth CONF flag
(e.g., spi-micro tier on a future milestone) is added, the fourth prompt
block has to be hand-rolled again with the same error handling. No
functional bug today.

**Fix:** Extract a reusable helper:

```python
def _prompt_or_default(
  label: str,
  default: str,
  validator: 'Callable[[str], tuple[bool, str, str]]',   # (ok, value, err_msg)
  choices: 'list[str] | None' = None,
) -> 'tuple[int, str | None]':
  '''Returns (rc, value): rc=0 → value is valid; rc=1 → cancelled/invalid.'''
  ...
```

and call it three times with validators for float/$-comma-strip + isfinite
+ ≥1000, spi-label-in-choices, audusd-label-in-choices. Keeps the CONF-01
T-08-12 guard in one place per validator.

---

## Info Findings (IN-NN)

### IN-01: `_build_crash_state_summary` yfinance-keyed lookup is dead code

**File:** `main.py:184-185`

**Issue:** The first two lookups
`state.get('signals', {}).get('^AXJO', {})` and
`state.get('signals', {}).get('AUDUSD=X', {})` never hit in production —
state['signals'] is always keyed by state_key (SPI200/AUDUSD) per Phase 3
reset_state() and Phase 4 `run_daily_check` write pattern. The fallback at
lines 188-191 (state_key lookup) is what actually works. The yfinance-key
branch is a holdover from an earlier draft where the docstring comment
asserts "signals may also be keyed by state_key ... depending on where the
crash occurred mid-flow" — no such dual-keyed state ever exists today.

**Fix:** Drop lines 184-185 and simplify to the state-key-only lookups,
OR keep both branches but add a code comment that the yfinance branch is
defence-in-depth only. Minor — has no functional impact.

---

### IN-02: `_handle_reset` preview silently swallows `load_state` failures

**File:** `main.py:1195-1198`

**Issue:**
```python
try:
  current = state_manager.load_state()
except Exception:
  current = None
```
Any exception (KeyError from unknown tier label, ValueError from
`_validate_loaded_state`, OSError from permission denied) results in the
"Current state.json:" block silently disappearing from the preview with no
explanation. Operator running `--reset` because their state is already
broken won't see why the preview block is empty.

**Fix:** Log the swallowed error at DEBUG (`logger.debug('[State] preview load failed: %s', e)`)
or print a line `print('Current state.json: (could not load)', file=sys.stderr)`
so the preview explicitly communicates the skip. Low priority — the reset
proceeds correctly regardless.

---

### IN-03: Resend api_key redaction may leak partial keys on `resp.text[:200]` truncation

**File:** `notifier.py:1314-1316`

**Issue:**
```python
safe_body = resp.text[:200]
if api_key:
  safe_body = safe_body.replace(api_key, '[REDACTED]')
```
Truncation to 200 chars happens BEFORE the `replace`. If the Resend 4xx
body echoes the api_key across the 200-char boundary (i.e., first N chars
of the key at the end of safe_body), the partial prefix survives the
replace and ends up in the raised `ResendError` message. Resend is
unlikely to echo the Authorization header in practice (T-06-02 mitigation
was prospective), but the redaction contract is stronger if applied
pre-truncation.

**Fix:**
```python
safe_body = resp.text
if api_key:
  safe_body = safe_body.replace(api_key, '[REDACTED]')
safe_body = safe_body[:200]
```

---

### IN-04: `_send_email_never_crash` returns bare `None` rather than a `SendStatus` sentinel

**File:** `main.py:136-166`

**Issue:** The return-type annotation is `'object | None'` which forces
callers (`_dispatch_email_and_maintain_warnings:304-326`) to branch on
`status is None` vs `isinstance(status, SendStatus)` semantics without
type-checker help. The R2 review fix correctly handles `status is None`
as a dispatch failure and appends a notifier-sourced warning, but the
double-branch (status None vs status.ok False vs status.ok True + reason
'no_api_key') is more fragile than returning
`SendStatus(ok=False, reason='import_or_runtime_error')` on the exception
branch.

**Fix:** Import `SendStatus` in the helper (accepting the local-import C-2
pattern only for notifier.send_daily_email itself), return
`SendStatus(ok=False, reason=f'{type(e).__name__}: {e}'[:200])` on the
except branch. Collapse `_dispatch_email_and_maintain_warnings` to a
single `if not status.ok and status.reason != 'no_api_key'` branch. No
functional difference today; reduces future refactor risk.

---

### IN-05: Dashboard/notifier `_CONTRACT_SPECS` dict duplication

**Files:**
- `dashboard.py:127-130`
- `notifier.py:134-137`

**Issue:** Both modules build the same `_CONTRACT_SPECS` tuple dict. Each
render helper is pure and hex-separated per D-01, so direct-sharing via a
utility module would violate the boundary. Duplication is fine today but
the dicts must be kept in sync manually. If WR-01 fix lands (source from
state['_resolved_contracts']), both dicts can likely become
defense-in-depth fallbacks only and the sync risk drops.

**Fix:** On resolution of WR-01, leave both dicts in place as fallbacks
with a cross-referencing comment. Alternative: add a single
`tests/test_cross_module.py::test_contract_specs_identical` regression
test.

---

### IN-06: `MIGRATIONS` lambda for v2 is non-obvious; favour a named function

**File:** `state_manager.py:92-99`

**Issue:** `MIGRATIONS[2]` is a three-line lambda composed with dict
unpacking. Future migrations (v3+) will need more conditional logic and
can't be inlined as lambdas. Starting v2 as a named function makes
future walks easier to grep and allows a docstring.

**Fix:**
```python
def _migrate_v1_to_v2(s: dict) -> dict:
  '''D-15: silent backfill of initial_account + contracts with defaults.
  Idempotent via s.get(..., default) — preserves operator choice.
  '''
  return {
    **s,
    'initial_account': s.get('initial_account', INITIAL_ACCOUNT),
    'contracts': s.get('contracts', {
      'SPI200': _DEFAULT_SPI_LABEL,
      'AUDUSD': _DEFAULT_AUDUSD_LABEL,
    }),
  }

MIGRATIONS: dict = {
  1: lambda s: s,
  2: _migrate_v1_to_v2,
}
```

Style preference only; no functional change.

---

## Files Reviewed

| File | LOC | Findings |
|------|-----|----------|
| `system_params.py` | 156 | 0 |
| `state_manager.py` | 551 | 1 (IN-06) |
| `notifier.py` | 1519 | 2 (WR-01, IN-03) |
| `main.py` | 1342 | 4 (WR-02, IN-01, IN-02, IN-04) |
| `dashboard.py` | 1076 | 2 (WR-01, IN-05) |
| `tests/test_state_manager.py` | 1337 | 0 |
| `tests/test_notifier.py` | 1868 | 0 |
| `tests/test_main.py` | 1922 | 0 |
| `tests/test_scheduler.py` | 716 | 0 |
| `tests/test_dashboard.py` | 1011 | 0 |

## Strengths

- **Hex-lite boundary discipline is clean** — verified by grep:
  `signal_engine`/`sizing_engine`/`system_params` have no I/O imports;
  `state_manager` imports only `system_params`; `notifier` imports only
  `state_manager.load_state` (for CLI convenience) + `system_params`;
  `dashboard` mirrors the notifier pattern. No cross-module coupling
  violations introduced by Phase 8.
- **Warning-carry-over canonical order** (main.py:270-336) is documented
  step-by-step in the docstring and correctly clears warnings BEFORE
  appending the notifier-failure warning — ensuring the new failure
  survives to the next run (B1 review fix).
- **`_LAST_LOADED_STATE` cache is refreshed immediately after
  `load_state`** (main.py:824-830) and the nested try/except in `main()`
  (line 1323-1337) protects the exit code from crash-email dispatch
  failure. SC-3 "crash email with last-known state summary" is hit.
- **T-08-12 NaN/inf injection guard** on `--initial-account` is applied
  at BOTH the CLI-flag path AND the interactive prompt path, AFTER the
  float coercion but BEFORE the ≥$1000 check (main.py:1127-1133) — tested
  in `TestResetFlags::test_initial_account_nan_rejected_cli_path` and
  `TestResetInteractive::test_reset_interactive_nan_rejected`.
- **Underscore-key filter is the convention, not a whitelist** —
  `save_state` uses `k.startswith('_')` at `state_manager.py:412`, so any
  future runtime-only key (e.g., Plan 03's `_stale_info`) inherits the
  exclusion automatically. Test coverage
  (`TestSaveStateExcludesUnderscoreKeys`) explicitly guards against
  filter-narrowing regressions.
- **Corrupt-recovery classifier uses exact prefix `'recovered from
  corruption'`** (state_manager.py:371, notifier.py:545-547) — single
  canonical spelling, grep-auditable, tested end-to-end via
  `TestCriticalBanner` + `TestSubjectBangPrefix`.
- **Crash-email body is text/plain with bounded state summary** —
  excludes `trade_log`/`equity_history`/`warnings` per D-06 so a
  production crash doesn't mail out thousands of lines; tested in
  `TestCrashEmailBoundary::test_build_crash_state_summary_contains_core_sections`.
- **`--test` structural read-only is preserved through the new
  dispatch** — `persist=not args.test` at main.py:1302 ensures the
  dispatch helper NEITHER saves nor mutates `state['warnings']` on the
  test path; `_stale_info` still gets popped from the in-memory dict
  for cleanliness. Tested in
  `TestWarningCarryOverFlow::test_dispatch_persist_false_skips_mutation`.
