---
status: all_fixed
phase: 08
findings_in_scope: 2
fixed: 2
skipped: 0
iteration: 1
fixed_at: 2026-04-23
---

# Phase 8 Code Review Fix Report

**Fixed at:** 2026-04-23
**Source review:** .planning/phases/08-hardening-warning-carry-over-stale-banner-crash-email-config/08-REVIEW.md
**Iteration:** 1
**Fix scope:** critical_warning (2 warnings; 6 info findings out of scope)

**Summary:**
- Findings in scope: 2
- Fixed: 2
- Skipped: 0
- Tests before: 653 passed
- Tests after: 661 passed (8 new tests added for WR-01)

## Fixed Issues

### WR-01: Dashboard + notifier render unrealised P&L with hardcoded default-tier multipliers

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

**Hex-lite boundary preserved:**
- No new imports added.
- `sizing_engine.py` unchanged (still pure, 0 tier-dict imports).
- `state_manager` unchanged.
- Dashboard/notifier helpers remain pure — still take state + position dicts, still return floats/None.

**Test coverage added (8 tests):**
- `TestUnrealisedPnlUsesResolvedContracts::test_standard_tier_uses_25_multiplier` — spi-standard (25×) → 4970.0
- `TestUnrealisedPnlUsesResolvedContracts::test_full_tier_uses_50_multiplier` — spi-full (50×) → 4975.0
- `TestUnrealisedPnlUsesResolvedContracts::test_missing_resolved_contracts_falls_back_to_mini_defaults` — state={} → 994.0 + DEBUG log assertion
- `TestUnrealisedPnlUsesResolvedContracts::test_state_none_also_falls_back` — state=None → 497.0
- Same 4 tests mirrored in `TestUnrealisedPnlEmailUsesResolvedContracts` for notifier

All pre-existing `test_unrealised_pnl_matches_sizing_engine` parity tests continue to pass (they use default tier and either state=None or no state arg).

---

### WR-02: `_handle_reset` is a 164-line inline prompt/validate/preview block

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

Each of the three prompt sites in `_handle_reset` (initial_account, spi_contract, audusd_contract) now defines a small validator closure:
- `_validate_account`: `$`/comma-strip + `float()` parse → `(True, float)` / `(False, 'invalid account value ...')`
- `_validate_spi`: label-in-SPI_CONTRACTS check → `(True, raw)` / `(False, 'invalid SPI label ... — choices: ...')`
- `_validate_audusd`: label-in-AUDUSD_CONTRACTS check (same shape)

Each site calls `_prompt_or_default(...)`, unpacks `(rc, value)`, and returns `rc` on non-zero.

**Public CLI behavior: UNCHANGED.** All 7 `TestResetInteractive` tests pass without modification:
- `test_reset_interactive_happy_path` — iter inputs → state written
- `test_reset_interactive_quit_cancels` — 'q' → rc 1 + "cancelled" log
- `test_reset_interactive_blank_defaults` — blank inputs → defaults applied
- `test_reset_interactive_dollar_sign_comma_stripping` — `$50,000` → 50000.0
- `test_reset_interactive_invalid_float_rejected` — `abc` → rc 1 + "invalid account value"
- `test_reset_interactive_below_1000_rejected` — `500` → rc 1 + "at least $1,000"
- `test_reset_interactive_nan_rejected` — `nan` → rc 1 + "finite" (T-08-12 guard stays outside the helper, applies to both flag path AND prompt path)

All 10 `TestResetFlags` / `TestResetNonTTY` tests also unchanged and passing (these exercise the argparse-flag path which bypasses the helper).

**Line-count impact:**
- Three prompt blocks: 65 lines → 44 lines (shared helper handles the 21 shared lines).
- `_handle_reset` body overall: not reduced to ≤100 lines as the reviewer suggested because the body also contains the non-TTY guard, isfinite/≥1000 validation, D-12 preview, YES confirmation, and reset-state build — none of which were in scope for the helper extraction.
- `_prompt_or_default` body: 17 lines (concentrated single point for future CONF additions).

**Maintenance payoff:** A fourth CONF flag (e.g. a future `spi-micro` preset or an AUDUSD-tier rename) can reuse `_prompt_or_default` with a one-line validator closure instead of hand-rolling EOFError/q/blank/invalid handling a fourth time. The T-08-12 `math.isfinite` NaN guard stays in one place (applies to both the argparse-flag path AND the interactive-prompt path), so the CONF-01 security property is preserved.

## Skipped Issues

_None._

## Caveats / Known Follow-ups

- **IN-05 cross-module duplication**: `_CONTRACT_SPECS` (dashboard) and `_CONTRACT_SPECS_EMAIL` (notifier) remain duplicated dicts, as flagged by IN-05. After the WR-01 fix, both dicts now serve as defense-in-depth fallbacks only (not the primary lookup), so the duplication risk is reduced. Per IN-05's recommendation, a future phase could add a `tests/test_cross_module.py::test_contract_specs_identical` regression test. Not in scope for this fix run (info-severity, out of `critical_warning` scope).
- **IN-01, IN-02, IN-03, IN-04, IN-06**: All 5 Info-severity findings remain open. Per default fix_scope=critical_warning they were not attempted in this iteration. They can be folded into a follow-up phase if operator priorities change.

## Verification

- **Tier 1 (re-read):** Both modified files re-read at fix sites; fix text present and surrounding code intact.
- **Tier 2 (syntax check):** `python -c "import ast; ast.parse(open(F).read())"` passed on all 3 modified source files (`dashboard.py`, `notifier.py`, `main.py`).
- **Tier 2 (full test suite):** `python -m pytest tests/ -x` → **661 passed, 0 failed** (was 653 baseline; +8 new WR-01 tests, 0 regressions).
- **Hex-lite boundary spot-check:** `sizing_engine.py` imports unchanged (still 0 tier-dict imports); dashboard/notifier still do not import `state_manager` beyond `load_state` for the CLI convenience path. D-17 AST check in `tests/test_signal_engine.py::TestDeterminism` still passes.
- **D-14 underscore-prefix filter:** `save_state` still strips `_resolved_contracts` before JSON write (unchanged; covered by existing `test_resolved_contracts_not_persisted`).
- **All Phase 8 acceptance criteria from Plans 08-01, 08-02, 08-03:** remain satisfied (no test regressions in the 653 pre-existing tests).

---

_Fixed: 2026-04-23_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
