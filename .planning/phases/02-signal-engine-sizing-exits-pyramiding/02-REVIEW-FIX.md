---
phase: 02-signal-engine-sizing-exits-pyramiding
fixed_at: 2026-04-21T02:45:30Z
review_path: .planning/phases/02-signal-engine-sizing-exits-pyramiding/02-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-04-21T02:45:30Z
**Source review:** .planning/phases/02-signal-engine-sizing-exits-pyramiding/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope (Critical + Warning): 2
- Fixed: 2
- Skipped: 0

## Fixed Issues

### WR-01: Falsy-Zero Bug in step() Peak/Trough Update (D-16)

**Files modified:** `sizing_engine.py`, `tests/regenerate_phase2_fixtures.py`
**Commit:** 9986550
**Applied fix:** Replaced the `or` idiom (`cur.get('peak_price') or entry_price`) with an explicit `if X is None` check in `step()` Phase 0 peak/trough update, matching the pattern already used by `get_trailing_stop` and `check_stop_hit`. The same fix was applied to the mirror in `tests/regenerate_phase2_fixtures.py` for consistency. 248 tests pass unchanged — no fixture diff produced (SPI/AUDUSD prices are far from 0.0 so the behaviour is identical for all existing fixtures).

### WR-02: Stale `position` Reference in Reversal Branch of step()

**Files modified:** `sizing_engine.py`
**Commit:** 9986550
**Applied fix:** Changed `position['direction']` to `current_position['direction']` in the reversal `elif` condition at lines 503-505, making it consistent with all other references inside the `if current_position is not None:` block. Both WR-01 and WR-02 changes to `sizing_engine.py` were staged together and landed in the same atomic commit.

## Skipped Issues

None — all in-scope findings were fixed.

---

**Test suite result after fixes:** 248 passed in 1.06s (no regressions)

---

_Fixed: 2026-04-21T02:45:30Z_
_Fixer: Claude Sonnet 4.6 (gsd-code-fixer)_
_Iteration: 1_
