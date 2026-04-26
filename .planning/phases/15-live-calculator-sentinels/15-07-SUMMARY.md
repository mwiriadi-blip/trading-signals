---
phase: 15
plan: "07"
subsystem: notifier
tags:
  - phase15
  - notifier
  - email-banner
  - critical-banner-classifier
  - sentinel-03
depends_on:
  - 15-02
  - 15-04
  - 15-05
key-decisions:
  - "REVIEWS L-4: hero-card stable marker '>Trading Signals</h1>' (hardcoded h1 in notifier.py line 530-531)"
  - "REVIEWS M-1 Path A: all 10 test methods implemented and passing — no pytest.skip escape hatches"
  - "D-12 parity: drift banner body bullets reuse same DriftEvent.message strings as dashboard._render_drift_banner"
  - "D-13 hierarchy: drift banner (CRITICAL BANNER 3) inserted BETWEEN corrupt-reset (BANNER 2) and hero card"
  - "UP017 fix: all new test methods use 'from datetime import UTC' instead of 'timezone.utc'"
key-files:
  modified:
    - notifier.py
    - tests/test_notifier.py
metrics:
  duration: "~7 minutes"
  completed: "2026-04-26"
  tasks: 2
  files: 2
requirements:
  - SENTINEL-03
---

# Phase 15 Plan 07: Email Drift Banner (SENTINEL-03) Summary

One-liner: Drift warnings wired into daily email via _has_critical_banner extension + inline-CSS CRITICAL BANNER 3 block with D-12 lockstep parity and D-13 stack hierarchy — 10 new tests all passing, no skips (REVIEWS M-1 Path A).

## What Was Built

### Task 1 — Extend _has_critical_banner + insert drift banner block

**notifier.py — `_has_critical_banner` extension (lines 563-564):**

A third branch was added inside the existing `for w in state.get('warnings', [])` loop immediately after the `state_manager` / `'recovered from corruption'` check:

```python
    if w.get('source') == 'drift':   # NEW Phase 15 SENTINEL-03
      return True
```

This auto-engages the existing Phase 8 `[!]` subject-prefix path — no subject assembly code changes needed (D-03).

**notifier.py — CRITICAL BANNER 3 block (lines 645-681):**

A drift banner block was inserted between the corrupt-reset block (CRITICAL BANNER 2, ending at line 641) and the hero card `parts.append` (line 680). Exact line range: lines 645-679.

The block:
- Collects `drift_warnings = [w for w in state.get('warnings', []) if w.get('source') == 'drift']`
- Sets `border_color = _COLOR_SHORT if has_reversal else _COLOR_FLAT` (D-13)
- Renders heading `━━━ Drift detected ━━━` and bullet list of `DriftEvent.message` strings
- Uses `html.escape(message, quote=True)` at leaf render site (T-15-07-01 XSS mitigation)
- No CSS variables — hex literals only (Gmail compatibility per UI-SPEC)

**Before-context confirmation (D-13 hierarchy):**

```
line 637–641: corrupt-reset block's last parts.append (CRITICAL BANNER 2)
line 645:     # --- CRITICAL BANNER 3: drift/reversal ---
line 680:     # --- HERO CARD ---
```

String position ordering: corruption renders before drift; drift renders before hero card. TestBannerStackOrder verifies this DOM order.

### Task 2 — Populate all 10 test method bodies

**tests/test_notifier.py — TestDriftBanner (7 methods, all passing):**

| Method | What it verifies |
|--------|-----------------|
| `test_has_critical_banner_drift_source` | `_has_critical_banner` returns True with drift warning (D-03) |
| `test_has_critical_banner_no_drift` | `_has_critical_banner` returns False with empty warnings |
| `test_drift_banner_in_email_body` | `━━━ Drift detected ━━━` in `_render_header_email` output |
| `test_drift_banner_body_parity_with_dashboard` | D-12 lockstep: same message string in email + dashboard banner |
| `test_drift_banner_in_email_body_and_subject_critical_prefix` | `_has_critical_banner` True → `[!]` prefix path auto-engaged |
| `test_email_banner_border_red_for_reversal` | `#ef4444` border when any message contains 'reversal recommended' |
| `test_email_banner_border_amber_for_drift_only` | `#eab308` border when all drift-only messages |

**tests/test_notifier.py — TestBannerStackOrder (3 methods, all passing):**

| Method | What it verifies |
|--------|-----------------|
| `test_banner_hierarchy_corruption_beats_drift` | `idx_corr < idx_drift` in rendered HTML (D-13) |
| `test_banner_hierarchy_stale_beats_drift` | `idx_stale < idx_drift` in rendered HTML (D-13) |
| `test_drift_banner_inserted_before_hero_card` | `idx_drift < idx_hero` where `idx_hero = body.find('>Trading Signals</h1>')` (REVIEWS L-4 + Pitfall 4) |

**REVIEWS L-4 stable hero-card marker:**

The `>Trading Signals</h1>` substring was confirmed by direct read of `notifier._render_hero_card_email` lines 530-531:
```python
f'<h1 style="margin:0;font-size:22px;font-weight:600;'
f'color:{_COLOR_TEXT};line-height:1.2;">Trading Signals</h1>'
```
This string is hardcoded (no conditional branch suppresses it) and present in every email render — a deterministic marker.

**REVIEWS M-1 Path A enforcement:**

All 10 pytest.skip stubs removed. Zero skip escape hatches remain:
- `grep -c "pytest.skip" tests/test_notifier.py` for the 10 new methods = 0

## Test Results

```
pytest tests/test_notifier.py::TestDriftBanner -v -q
7 passed in 0.09s

pytest tests/test_notifier.py::TestBannerStackOrder -v -q
3 passed in 0.06s

pytest tests/test_notifier.py -x -q
171 passed in 90.26s
```

Full prior pass count was 161 + 10 skipped. Now 171 passed, 0 skipped — no regressions.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug / Style] UP017 + I001 ruff violations in test methods**

- **Found during:** Task 2 post-write ruff check
- **Issue:** Plan's test method bodies used `from datetime import datetime, timezone` + `datetime(..., tzinfo=timezone.utc)` which triggers UP017 (`timezone.utc` → `datetime.UTC`). Import blocks without blank separator between stdlib and local imports triggered I001.
- **Fix:** Changed all 9 occurrences to `from datetime import UTC, datetime` + `datetime(..., tzinfo=UTC)`. Applied `ruff check --select I001 --fix` to add blank lines between stdlib and local import blocks.
- **Files modified:** `tests/test_notifier.py`
- **Commits:** `41dd608`

## Commits

| Task | Commit | Message |
|------|--------|---------|
| Task 1 | `82415aa` | `feat(15-07): extend _has_critical_banner + insert drift banner block in _render_header_email` |
| Task 2 | `41dd608` | `test(15-07): populate all 10 TestDriftBanner + TestBannerStackOrder methods (REVIEWS M-1 Path A)` |

## Acceptance Criteria Verification

- [x] `grep -c "w.get('source') == 'drift'" notifier.py` → 2 (in `_has_critical_banner` at line 564 + in drift banner collection at line 652)
- [x] `grep -c "━━━ Drift detected ━━━" notifier.py` → 1
- [x] `grep -c "CRITICAL BANNER 3" notifier.py` → 1
- [x] `grep -c "reversal recommended" notifier.py` → 1
- [x] `python -c "import notifier; s = {'warnings': [{'source': 'drift', 'message': 'x', 'date': '2026-04-26'}]}; assert notifier._has_critical_banner(s) is True"` → exits 0
- [x] `python -c "import notifier; assert notifier._has_critical_banner({'warnings': []}) is False"` → exits 0
- [x] `pytest tests/test_notifier.py::TestDriftBanner -x -q` → 7 passed, 0 skipped, 0 failed
- [x] `pytest tests/test_notifier.py::TestBannerStackOrder -x -q` → 3 passed, 0 skipped, 0 failed
- [x] `grep -c ">Trading Signals</h1>" tests/test_notifier.py` → 4 (REVIEWS L-4 stable marker)
- [x] `pytest tests/test_notifier.py -x -q` → 171 passed, 0 skipped
- [x] `ruff check notifier.py` → All checks passed
- [x] `ruff check tests/test_notifier.py` (excluding pre-existing E501) → No new issues

## Known Stubs

None — plan is additive only (new banner code + new tests). No data stubs.

## Threat Flags

No new threat surface beyond what the plan's `<threat_model>` already documents. All T-15-07-01 through T-15-07-06 mitigations are implemented and tested.
