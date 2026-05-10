---
phase: 25
plan: "09"
subsystem: dashboard_renderer
tags: [css, a11y, mobile, responsive, tokens, typography]
dependency_graph:
  requires: [25-02, 25-03, 25-07]
  provides: [css-token-catalog, signal-classes, status-dot-classes, table-scroll, focus-visible, tab-active-styles]
  affects: [25-09b]
tech_stack:
  added: []
  patterns: [css-custom-properties, mobile-first-media-query, focus-visible-outline, stacked-row-table]
key_files:
  created: []
  modified:
    - dashboard_renderer/assets.py
    - tests/test_dashboard.py
    - tests/fixtures/dashboard/golden.html
    - tests/fixtures/dashboard/golden_empty.html
decisions:
  - "Footer hard-coded font-size:12px replaced with var(--fs-label) to eliminate last old-token hard-code"
  - "Golden snapshots regenerated with frozen clock after CSS expansion — pre-existing empty_state fixture mismatch is out of scope"
metrics:
  duration: "~20min"
  completed: "2026-05-05"
  tasks_completed: 1
  tasks_total: 1
  files_changed: 4
---

# Phase 25 Plan 09: CSS Tokens + Responsive Scaffolding Summary

CSS token rebalance and class catalog in `_INLINE_CSS` — D-15 font scale, signal/status-dot/table-scroll/focus-visible/tab-active styles locked as single source of truth for 25-09b component wiring.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Update _INLINE_CSS: font tokens, signal classes, status-dot, table-scroll, focus-visible, tab-strip, helper styles | 0eb0605 |

## What Was Shipped

### Font token rebalance (D-15)

| Token | Before | After |
|-------|--------|-------|
| `--fs-label` | 12px | 14px |
| `--fs-body` | 14px | **16px** (iOS auto-zoom fix) |
| `--fs-heading` | 20px | 23px |
| `--fs-display` | 28px | 32px |

### New design tokens added to `:root`

| Token | Value | Purpose |
|-------|-------|---------|
| `--color-focus-ring` | `#e5e7eb` | `:focus-visible` outline color |
| `--color-status-stale` | `#eab308` | Status strip stale/amber dot |
| `--space-status-dot` | 8px | Status-dot diameter |
| `--touch-target-min` | 44px | Minimum hit area for tabs and chip |

### CSS class catalog (consumed by 25-09b)

**Signal color classes (D-19 #5):**
- `.signal-flat` — `color: var(--color-flat)`
- `.signal-long` — `color: var(--color-long)`
- `.signal-short` — `color: var(--color-short)`

**Status-dot classes (D-06 + D-19 #3):**
- `.status-dot` — base 8px circle, `border-radius: 50%`
- `.status-dot--success` — green
- `.status-dot--stale` / `.status-dot--flat` — amber
- `.status-dot--failure` / `.status-dot--short` — red
- `.status-dot--never` / `.status-dot--neutral` — dim

**Table-scroll (D-20):**
- `.table-scroll` — `overflow-x: auto; -webkit-overflow-scrolling: touch`
- `@media (max-width: 600px)` stacked-row: thead hidden, tr becomes block card, td::before shows `attr(data-label)`

**Tab-strip active-tab (D-18):**
- `nav[role="tablist"] [role="tab"]` — base: 44px min-height, muted color
- `[aria-current="page"]` / `.tab-active` — 2px solid `--color-long` bottom border
- `:hover/:focus` — surface background

**Focus-visible (D-19 #2):**
- `a, button, summary, select, input, [role="tab"]:focus-visible` — 2px solid `--color-focus-ring`, 2px offset

**Helper component styles (25-05/25-06/25-07):**
- `.status-strip`, `.onboarding-card`, `.add-market-chip` + form layout

### Hardcode cleanup
- `footer { font-size: 12px }` replaced with `var(--fs-label)` (only remaining old-token hard-code)

## Test Results

- `TestPhase25Fonts` — 4 tests PASS (xfail removed, all green)
- `TestGoldenSnapshot` — PASS after golden regeneration
- 6 pre-existing failures unchanged (test_chart_payload_escapes_script_close, test_equity_chart_empty_state_placeholder, TestEmptyState::test_empty_state_matches_committed — empty_state fixture vs reset_state() mismatch; 3 deploy.sh tests)
- 7 xfails remain for 25-09b and 25-10 work

## Deviations from Plan

None — plan executed exactly as written. One additional fix applied:

**[Rule 2 - Hardcode] Replace footer font-size:12px with var(--fs-label)**
- Found during: Task 1 audit step (step 7)
- Issue: `footer { font-size: 12px }` was the only remaining old-token hard-code; would have stayed at 12px (old `--fs-label` value) while the token moved to 14px
- Fix: Replaced with `var(--fs-label)` in assets.py footer rule
- Files modified: dashboard_renderer/assets.py
- Commit: 0eb0605

## 25-09b Dependency — Class Catalog

25-09b can now wire components against these locked class names:

```
.signal-flat / .signal-long / .signal-short
.status-dot / .status-dot--{success|stale|failure|never|flat|long|short|neutral}
.table-scroll (wrapper div) + data-label="..." on each <td>
nav[role="tablist"] [role="tab"][aria-current="page"]
```

No component `.py` file was modified in this plan.

## Known Stubs

None — this plan is CSS-only. No data wiring, no component rendering.

## Self-Check: PASSED

- `dashboard_renderer/assets.py` modified: FOUND
- `tests/test_dashboard.py` xfails removed: FOUND (4 decorators removed)
- `tests/fixtures/dashboard/golden.html` regenerated: FOUND
- `tests/fixtures/dashboard/golden_empty.html` regenerated: FOUND
- Commit 0eb0605: FOUND (`git log --oneline -1` = `0eb0605 feat(25-09): CSS tokens + responsive scaffolding for mobile a11y`)
- TestPhase25Fonts: 4 PASSED
