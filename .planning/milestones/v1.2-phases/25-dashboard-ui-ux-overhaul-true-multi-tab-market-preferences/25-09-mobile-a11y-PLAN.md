---
phase: 25
plan: 09
type: execute
wave: 4
depends_on: [25-02, 25-03, 25-07]
files_modified:
  - dashboard_renderer/assets.py
files_modified_note: "CSS-token + responsive-scaffolding plan only. Component-level a11y wiring lives in 25-09b."
autonomous: true
requirements: [P25-08, P25-12]
must_haves:
  truths:
    - "_INLINE_CSS contains '--fs-body: 16px;' (from 14px) and proportionally scaled --fs-label/--fs-heading/--fs-display"
    - "_INLINE_CSS defines .signal-flat / .signal-long / .signal-short color rules so component renderers (in 25-09b) can drop inline style=\"color:...\" attributes"
    - "_INLINE_CSS defines .status-dot + .status-dot--{success|stale|failure|never|flat|long|short|neutral} classes used by both the System Status strip and the FLAT/LONG/SHORT signal labels"
    - "_INLINE_CSS defines .table-scroll wrapper rules and an @media (max-width: 600px) stacked-row layout block for wide tables"
    - "_INLINE_CSS defines :focus-visible outline rules covering anchors, buttons, summary, select, input and [role=tab]"
    - "_INLINE_CSS defines tab-strip active-tab styles via aria-current=\"page\" / .tab-active selectors per D-18"
  artifacts:
    - path: dashboard_renderer/assets.py
      provides: "Updated _INLINE_CSS with rebalanced font tokens, signal-{flat|long|short} classes, status-dot CSS, table-scroll wrapper styles, focus-visible rules, mobile media-query stacked-table rules, tab-strip active-tab rules, status-strip / onboarding-card / add-market-chip styles"
      contains: "--fs-body: 16px"
  key_links:
    - from: "_INLINE_CSS"
      to: "All Phase-25 component class names"
      via: "Single source of truth in assets.py — components in 25-09b reference these classes"
      pattern: "--fs-body: 16px|signal-flat|table-scroll|status-dot|focus-visible"
---

<objective>
Wave 4. CSS tokens + responsive scaffolding ONLY. Lands the design-token + class-name foundation that 25-09b's component-a11y wiring depends on. Single source of truth: `_INLINE_CSS` in `dashboard_renderer/assets.py`.

Implements:
- D-15 font scale rebalance (14→16 base, full token rescale).
- D-20 wide-table wrapper CSS + @media (max-width: 600px) stacked-row layout.
- D-19 #5 prerequisite — define `.signal-flat / .signal-long / .signal-short` color classes (so 25-09b can replace `style="color:#eab308"` etc. with `class="signal-flat"`).
- D-19 #2 prerequisite — focus-visible outline rule using --color-focus-ring token.
- D-18 active-tab CSS rule (aria-current=page / .tab-active selectors).
- Status-strip / onboarding-card / add-market-chip styles needed by Plans 25-05 / 25-06 / 25-07 markup that has already shipped earlier in Wave 3.

Does NOT touch any component .py file. The CSS tokens defined here are CONSUMED by 25-09b (which then wires the markup to use them). Splitting prevents this plan from over-stuffing seven sub-items + six component files into one wave-4 implementation.

Output: assets.py CSS rebalanced; downstream 25-09b plan can begin component wiring against locked classes.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md
@dashboard_renderer/assets.py

<interfaces>
# Per UI-SPEC §Typography: rebalanced tokens (whole pixels):
#   --fs-label: 12 → 14
#   --fs-body: 14 → 16
#   --fs-heading: 20 → 23
#   --fs-display: 28 → 32
#
# Per UI-SPEC §Color: new semantic tokens:
#   --color-focus-ring: #e5e7eb (= --color-text)
#   --color-status-stale: #eab308 (= --color-flat)
#
# Per UI-SPEC §Spacing: new tokens:
#   --space-status-dot: 8px
#   --touch-target-min: 44px
#
# Per UI-SPEC §Layout & Interaction §Wide-table responsive: stacked-row layout under 600px
# uses data-label attribute pattern on <td> with <th> text repeated inline. The data-label
# emission happens in 25-09b (component .py edits); the CSS that consumes it is here.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Update _INLINE_CSS in assets.py — font tokens, signal classes, status-dot, table-scroll, focus-visible, mobile media query, tab strip, helper component styles</name>
  <read_first>
    - dashboard_renderer/assets.py (the consolidated _INLINE_CSS from Plan 02)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md (§Typography, §Color, §Spacing, §Layout & Interaction Contracts, §A11y hardening)
  </read_first>
  <files>dashboard_renderer/assets.py</files>
  <action>
Modify the `_INLINE_CSS` constant in dashboard_renderer/assets.py:

**1. Rebalance font tokens at the top of `:root` block (D-15):**

Replace existing `--fs-*` lines with:
```css
:root {
  --fs-label: 14px;       /* was 12 */
  --fs-body: 16px;        /* was 14 — D-15 kills iOS auto-zoom */
  --fs-heading: 23px;     /* was 20 (20 * 16/14 = 22.86 → 23) */
  --fs-display: 32px;     /* was 28 (28 * 16/14 = 32 exactly) */
  /* ... existing color tokens unchanged ... */
  --color-focus-ring: #e5e7eb;
  --color-status-stale: #eab308;
  --space-status-dot: 8px;
  --touch-target-min: 44px;
}
```

**2. Signal color classes (D-19 #5 — replaces inline style="color:..."):**

```css
.signal-flat { color: var(--color-flat); }
.signal-long { color: var(--color-long); }
.signal-short { color: var(--color-short); }
```

The component swap (replacing `<p style="color:#eab308">FLAT</p>` with `<p class="signal-flat">…</p>`) is owned by 25-09b. This plan only ships the CSS class definitions.

**3. Status-dot styles (D-06 status strip + D-19 #3 signal labels):**

```css
.status-dot {
  display: inline-block;
  width: var(--space-status-dot);
  height: var(--space-status-dot);
  border-radius: 50%;
  margin-right: var(--space-2);
  vertical-align: middle;
}
.status-dot--success { background: var(--color-long); }
.status-dot--stale,
.status-dot--flat { background: var(--color-flat); }
.status-dot--failure,
.status-dot--short { background: var(--color-short); }
.status-dot--never { background: var(--color-text-dim); }
.status-dot--long { background: var(--color-long); }
.status-dot--neutral { background: var(--color-text-dim); }
```

**4. Table-scroll wrapper + stacked-row mobile layout (D-20):**

```css
.table-scroll {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  width: 100%;
}

@media (max-width: 600px) {
  .table-scroll table {
    display: block;
  }
  .table-scroll thead {
    display: none;  /* hide column headers; data-label provides per-cell label */
  }
  .table-scroll tr {
    display: block;
    border: 1px solid var(--color-border);
    border-radius: 4px;
    margin-bottom: var(--space-3);
    padding: var(--space-3);
  }
  .table-scroll td {
    display: block;
    padding: var(--space-1) 0;
  }
  .table-scroll td::before {
    content: attr(data-label);
    display: inline-block;
    width: 50%;
    color: var(--color-text-muted);
    font-size: var(--fs-label);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
}
```

The actual `data-label="..."` attribute emission per `<td>` is owned by 25-09b in components/positions.py / trades.py / paper_trades.py.

**5. Tab-strip active-tab styles (D-18) + focus-visible rules (D-19 #2):**

```css
nav[role="tablist"] [role="tab"] {
  padding: var(--space-2) var(--space-4);
  min-height: var(--touch-target-min);
  display: inline-flex;
  align-items: center;
  text-decoration: none;
  color: var(--color-text-muted);
  border-bottom: 1px solid var(--color-border);
}
nav[role="tablist"] [role="tab"]:hover,
nav[role="tablist"] [role="tab"]:focus {
  color: var(--color-text);
  background: var(--color-surface);
}
nav[role="tablist"] [role="tab"][aria-current="page"],
nav[role="tablist"] [role="tab"].tab-active {
  color: var(--color-text);
  border-bottom: 2px solid var(--color-long);
}

a:focus-visible,
button:focus-visible,
summary:focus-visible,
select:focus-visible,
input:focus-visible,
[role="tab"]:focus-visible {
  outline: 2px solid var(--color-focus-ring);
  outline-offset: 2px;
}
```

**6. Status-strip + onboarding-card + add-market-chip styles (used by Plans 25-05 / 25-06 / 25-07 markup already shipped):**

```css
.status-strip {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  font-size: var(--fs-label);
  color: var(--color-text-muted);
}

.onboarding-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: var(--space-6);
  margin: var(--space-6) 0;
}
.onboarding-card h3 { margin: 0 0 var(--space-2); }

.add-market-chip {
  display: inline-block;
  margin-left: var(--space-2);
}
.add-market-chip > summary {
  cursor: pointer;
  padding: var(--space-2) var(--space-3);
  border: 1px dashed var(--color-flat);
  border-radius: 4px;
  list-style: none;
  min-height: var(--touch-target-min);
  display: inline-flex;
  align-items: center;
}
.add-market-chip[open] > summary { border-style: solid; }
.add-market-chip form {
  margin-top: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
```

**7. Audit existing CSS for hard-coded 14px / 12px (old tokens):**

Run `grep -nE '\b(12px|14px|20px|28px)\b' dashboard_renderer/assets.py` and replace any hard-coded values with `var(--fs-*)` references where the value matches a token. Comment-only matches (e.g. `/* was 14 */`) are fine.

**8. Flip xfail decorators on font tests:**

Remove `@pytest.mark.xfail` from `tests/test_dashboard.py::TestPhase25Fonts`. Run, confirm green.

NOTE: This plan does NOT touch any component .py file. Plan 25-09b consumes the classes/tokens defined here. If 25-09b's executor finds a missing class, escalate back to this plan rather than inlining CSS in a component file.
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -c "from dashboard_renderer.assets import _INLINE_CSS; assert '--fs-body: 16px' in _INLINE_CSS; assert '--fs-label: 14px' in _INLINE_CSS; assert '--fs-heading: 23px' in _INLINE_CSS; assert '--fs-display: 32px' in _INLINE_CSS; assert '.signal-flat' in _INLINE_CSS; assert '.signal-long' in _INLINE_CSS; assert '.signal-short' in _INLINE_CSS; assert '.table-scroll' in _INLINE_CSS; assert ':focus-visible' in _INLINE_CSS; assert 'status-dot--success' in _INLINE_CSS; assert 'aria-current=\"page\"' in _INLINE_CSS or '[aria-current=\"page\"]' in _INLINE_CSS; print('OK')" && python -m pytest tests/test_dashboard.py::TestPhase25Fonts -q --no-header 2>&1 | tail -5</automated>
  </verify>
  <done>
    - All four font tokens updated to whole-pixel rebalanced values (14, 16, 23, 32)
    - signal-{flat|long|short} class definitions present
    - status-dot + status-dot--* class definitions present (success/stale/failure/never/flat/long/short/neutral)
    - .table-scroll wrapper + @media (max-width: 600px) stacked-row layout present
    - :focus-visible rule covers a, button, summary, select, input, [role=tab]
    - Active-tab rule applies via [aria-current="page"] OR .tab-active selector
    - status-strip / onboarding-card / add-market-chip styles present
    - TestPhase25Fonts tests PASS (xfail removed)
    - assets.py is the only file modified by this plan
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Renderer → HTML output | Pure CSS edits in inline `<style>` block; no new user-controlled interpolation. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-25-09-01 | (n/a) | CSS-only changes | accept | Pure design-token + class-name rebalance; no new attack surface. |
</threat_model>

<verification>
- TestPhase25Fonts PASS (xfail removed).
- `grep -E '^\s*--fs-(body|label|heading|display):' dashboard_renderer/assets.py` returns 4 lines with values 16, 14, 23, 32 in some order.
- `grep -c '\.signal-\(flat\|long\|short\)' dashboard_renderer/assets.py` returns 3.
- `grep -c '\.status-dot--' dashboard_renderer/assets.py` returns ≥ 6 (success / stale / failure / never / flat / long / short / neutral).
- `grep -q ':focus-visible' dashboard_renderer/assets.py`.
- `grep -q '@media (max-width: 600px)' dashboard_renderer/assets.py`.
- Full test suite green.
</verification>

<success_criteria>
- iOS auto-zoom CSS prevention shipped (--fs-body: 16px).
- All design tokens, semantic color tokens, spacing tokens, signal/status-dot/table-scroll/focus-visible/active-tab CSS classes locked.
- 25-09b can begin component wiring against a stable class catalog.
- No component .py edits in this plan.
</success_criteria>

<output>
After completion, create `.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-09-SUMMARY.md` listing the CSS additions and the class-name catalog that 25-09b will consume.
</output>
