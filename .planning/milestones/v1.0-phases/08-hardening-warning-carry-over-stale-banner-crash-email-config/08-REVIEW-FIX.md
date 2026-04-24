---
status: all_fixed
phase: 08
findings_in_scope: 8
fixed: 8
skipped: 0
iteration: 2
fixed_at: 2026-04-23
---

# Phase 8 Code Review Fix Report

**Fixed at:** 2026-04-23
**Source review:** .planning/phases/08-hardening-warning-carry-over-stale-banner-crash-email-config/08-REVIEW.md
**Iteration:** 2 (cumulative across iterations 1 and 2)

**Summary:**
- Findings in scope: 8 (2 Warning + 6 Info)
- Fixed: 8 (2 in iteration 1 + 6 in iteration 2)
- Skipped: 0
- Tests before iteration 1: 653 passed
- Tests after iteration 1: 661 passed (+8 new tests for WR-01)
- Tests after iteration 2: 661 passed (no new tests; no regressions)

## Fixed Issues

### WR-01: Dashboard + notifier render unrealised P&L with hardcoded default-tier multipliers

**Iteration:** 1
**Files modified:**
- `dashboard.py` (+28 / -5 in `_compute_unrealised_pnl_display`, caller updated at `_render_positions_table`)
- `notifier.py` (+27 / -4 in `_compute_unrealised_pnl_email`, caller updated at `_render_positions_email`)
- `tests/test_dashboard.py` (+83 new `TestUnrealisedPnlUsesResolvedContracts` class with 4 tests)
- `tests/test_notifier.py` (+86 new `TestUnrealisedPnlEmailUsesResolvedContracts` class with 4 tests)

**Commit:** `608c064`

**Applied fix:**

Both `_compute_unrealised_pnl_display` (dashboard.py) and `_compute_unrealised_pnl_email` (notifier.py) now accept an optional `state: dict | None = None` parameter and prefer the operator-selected tier values from `state['_resolved_contracts'][state_key]` (materialised by `state_manager.load_state` per D-14). The module-level `_CONTRACT_SPECS` / `_CONTRACT_SPECS_EMAIL` dicts remain as defense-in-depth fallbacks for:

1. Pre-Phase-8 state shapes (no `_resolved_contracts` key)
2. Unit tests that construct `state` dicts directly via `json.loads()` (never through `load_state`)
3. `state=None` backward-compatibility callers

The fallback path emits a DEBUG log (`[Dashboard] _resolved_contracts missing for {state_key}...` and analogous `[Email] ...`) so silent divergence is visible in debug logs.

Callers in `_render_positions_table` (dashboard) and `_render_positions_email` (notifier) now pass `state` through to the helper.

**Operator impact:** An operator who runs `--reset --spi-contract spi-standard` (25× multiplier) previously saw dashboard and email unrealised P&L off by a 5× factor against reality, because the render helpers hardcoded the spi-mini scalar. Closed trades / sizing / record_trade were already correct — CONF-02 was only partially delivered to the render path. This fix completes CONF-02.

---

### WR-02: `_handle_reset` is a 164-line inline prompt/validate/preview block

**Iteration:** 1
**Files modified:**
- `main.py` (+81 / -52; new `_prompt_or_default` helper + 3 inline blocks refactored to delegating closures)

**Commit:** `44db3a5`

**Applied fix:**

Extracted `_prompt_or_default(prompt_text, default_value, validator) -> tuple[int, Any]` helper that consolidates the shared prompt cycle:

- Prints `prompt_text` via `input()`.
- `EOFError` on input → treats as `'q'`.
- `'q'` (case-insensitive) → logs `'[State] --reset cancelled by operator'`, returns `(1, None)`.
- Blank → returns `(0, default_value)`.
- Non-blank → calls `validator(raw)` which returns `(ok: bool, value_or_err)`:
  - `ok=True` → returns `(0, value)`
  - `ok=False` → prints `[State] ERROR: {err}` to stderr, returns `(1, None)`.

Each of the three prompt sites in `_handle_reset` (initial_account, spi_contract, audusd_contract) now defines a small validator closure. Public CLI behavior is unchanged — all 17 `TestResetInteractive` / `TestResetFlags` / `TestResetNonTTY` tests continue to pass without modification. The T-08-12 `math.isfinite` NaN guard stays in one place (applies to both the argparse-flag path AND the interactive-prompt path).

---

### IN-06: `MIGRATIONS` lambda for v2 is non-obvious; favour a named function

**Iteration:** 2
**Files modified:**
- `state_manager.py` (+15 / -8; introduced `_migrate_v1_to_v2(s)` named function, `MIGRATIONS[2]` now references it)

**Commit:** `1e729ef`

**Applied fix:**

Replaced the three-line lambda at `MIGRATIONS[2]` with a named module-level function `_migrate_v1_to_v2(s: dict) -> dict` carrying a docstring that documents the D-15 silent-migration behavior ("Phase 8 CONF-01/CONF-02 backfill: add initial_account (default $100k) and contracts (default mini tier) for pre-v2 state files"). `MIGRATIONS[2] = _migrate_v1_to_v2` preserves the walk-forward contract. No behavioral change — `s.get(..., default)` remains idempotent; operator-provided `initial_account` / `contracts` are still preserved on migration.

**Rationale:** Future v3+ migrations will need more conditional logic and can't be inlined as lambdas cleanly. Starting v2 as a named function makes future walks easier to grep and allows docstrings per migration step.

---

### IN-05: Dashboard/notifier `_CONTRACT_SPECS` dict duplication

**Iteration:** 2
**Files modified:**
- `system_params.py` (+10; added `FALLBACK_CONTRACT_SPECS` dict as single source of truth)
- `dashboard.py` (+6 / -4; `_CONTRACT_SPECS` is now a re-export of `FALLBACK_CONTRACT_SPECS`)
- `notifier.py` (+5 / -4; `_CONTRACT_SPECS_EMAIL` is now a re-export of `FALLBACK_CONTRACT_SPECS`)

**Commit:** `f098bac`

**Applied fix:**

Unified the duplicated tier-fallback dict into `system_params.FALLBACK_CONTRACT_SPECS`. Both dashboard and notifier now import that single dict and rebind it locally under their historical names (`_CONTRACT_SPECS` / `_CONTRACT_SPECS_EMAIL`) so existing call sites inside each module keep working. Since `system_params.py` is already imported by both modules (palette + scalars), this introduces no new hex-boundary violation.

**Rationale:** After WR-01 both dicts serve only as defense-in-depth fallbacks when `state['_resolved_contracts']` is absent. Consolidating eliminates the "must keep in sync manually" risk the reviewer flagged and removes the need for a future `tests/test_cross_module.py::test_contract_specs_identical` regression test.

---

### IN-04: `_send_email_never_crash` returns bare `None` rather than a `SendStatus` sentinel

**Iteration:** 2
**Files modified:**
- `main.py` (+30 / -6; `_send_email_never_crash` now returns `SendStatus(ok=False, reason='<ExceptionType>: <msg>')` on exception instead of `None`; caller comment updated)

**Commit:** `0820d5f`

**Applied fix: requires human verification**

On the exception branch, `_send_email_never_crash` now does a local `from notifier import SendStatus` import (C-2 local-import pattern, mirrors existing `import notifier` in the same function) and returns `SendStatus(ok=False, reason=f'{type(e).__name__}: {e}'[:200])`. The `if status is None` guard in `_dispatch_email_and_maintain_warnings` is retained as belt-and-suspenders for the truly pathological case where SendStatus itself fails to import — its comment block now documents this so future maintainers don't "dead-code-eliminate" the guard.

**Tests affected:** The R2 `test_dispatch_status_none_appends_warning` monkey-patches `_send_email_never_crash` to return None directly (bypassing the helper body), so it still exercises the None branch and remains green. No test changes required.

**Logic-bug flag:** The reviewer classified this as a fragility-reduction fix (no functional bug today). Still, please manually verify on the next integration run that:
1. When RESEND_API_KEY is unset, `send_daily_email` returns `SendStatus(ok=True, reason='no_api_key')` and the orchestrator's `elif not status.ok and status.reason != 'no_api_key'` branch correctly skips appending a warning.
2. When an actual notifier import failure occurs (e.g., after a bad deploy), the new `SendStatus(ok=False, reason='ImportError: ...')` path appends a warning that surfaces in the next run's email header.

---

### IN-03: Resend api_key redaction may leak partial keys on `resp.text[:200]` truncation

**Iteration:** 2
**Files modified:**
- `notifier.py` (+8 / -2 in `_post_to_resend` 4xx branch)

**Commit:** `f4dd8d9`

**Applied fix:**

Reordered the redact-then-truncate sequence in the 4xx error-body assembly. Previously:

```python
safe_body = resp.text[:200]
if api_key:
  safe_body = safe_body.replace(api_key, '[REDACTED]')
```

Now:

```python
safe_body = resp.text
if api_key:
  safe_body = safe_body.replace(api_key, '[REDACTED]')
safe_body = safe_body[:200]
```

Redaction now runs on the full response body before truncation, closing the "partial-key leak at the 200-char boundary" hole.

**Other paths audited:**
- Exhausted-retries branch (lines 1357-1363) already does full-redact-then-truncate (`err_repr = ...`, redact, then `err_repr[:200]` at the f-string). No change needed.
- The `[Email] Resend attempt %d/%d failed` WARN log passes the exception object directly; `requests.exceptions` don't contain the bearer token in their `__str__`, so no leak path. Not modified.

---

### IN-02: `_handle_reset` preview silently swallows `load_state` failures

**Iteration:** 2
**Files modified:**
- `main.py` (+10 / -1 in `_handle_reset` preview block)

**Commit:** `063ce95`

**Applied fix:**

Added a DEBUG log when `load_state()` raises inside the reset-preview path. Format: `[State] reset preview: failed to read existing state (<ExceptionClass>: <msg>)`. The swallow behavior is preserved — preview still proceeds even if the existing state.json is unreadable (operator running `--reset` with a broken state needs the reset to succeed, not fail on preview) — but the reason is now visible to anyone running with `--log-level DEBUG`.

---

### IN-01: `_build_crash_state_summary` yfinance-keyed lookup is dead code

**Iteration:** 2
**Files modified:**
- `main.py` (+6 / -8 in `_build_crash_state_summary`)

**Commit:** `4117744`

**Applied fix:**

Removed the dead yfinance-keyed lookup branch (`state['signals'].get('^AXJO', {})` and `state['signals'].get('AUDUSD=X', {})`). `state['signals']` is canonically keyed by state_key (`SPI200` / `AUDUSD`) per Phase 3 `reset_state` and `run_daily_check`'s write pattern — the yfinance branch was a holdover from an earlier draft where the docstring claimed "signals may also be keyed by state_key mid-flow" (no such dual-keyed state ever exists). Added a replacement comment documenting the state-key canonical convention and why the branch was removed. Existing tests covering `_build_crash_state_summary` continue to pass (they always used state-key shape).

## Skipped Issues

_None._

## Caveats / Known Follow-ups

- **IN-04 logic verification**: The SendStatus sentinel change is a fragility-reduction (no functional bug today per reviewer). The two integration paths called out in the IN-04 section above should be eyeballed on the next live run.
- **WR-02 line-count**: `_handle_reset` body is still longer than the reviewer's suggested ≤100 lines — the non-TTY guard, isfinite/≥1000 validation, D-12 preview, YES confirmation, and reset-state build were intentionally left in-line (not in scope for the helper extraction). A fourth CONF flag can reuse `_prompt_or_default` with a one-line validator closure, so the maintenance payoff is realised.

## Verification

- **Tier 1 (re-read):** Every modified file section re-read at the fix site; fix text present and surrounding code intact.
- **Tier 2 (syntax check):** `python -c "import ast; ast.parse(open(F).read())"` passed on all modified source files after each fix.
- **Tier 2 (full test suite):** `python -m pytest tests/ -q` → **661 passed, 0 failed** after every commit in iteration 2 (baseline 661 after iteration 1; iteration 2 added no new tests and introduced zero regressions).
- **Hex-lite boundary spot-check:** `sizing_engine.py` imports unchanged (still 0 tier-dict imports); `dashboard.py` and `notifier.py` still import only `state_manager.load_state` for the CLI-convenience path; the new `FALLBACK_CONTRACT_SPECS` import in both flows through `system_params`, which is already imported by both modules.
- **D-14 underscore-prefix filter:** `save_state` still strips `_resolved_contracts` before JSON write (unchanged; covered by existing `test_resolved_contracts_not_persisted`).
- **All Phase 8 acceptance criteria from Plans 08-01, 08-02, 08-03:** remain satisfied.

---

_Fixed: 2026-04-23_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2 (cumulative 1+2 record)_
