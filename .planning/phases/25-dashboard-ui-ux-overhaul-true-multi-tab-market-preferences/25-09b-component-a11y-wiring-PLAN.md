---
phase: 25
plan: 09b
type: execute
wave: 4
depends_on: [25-02, 25-03, 25-05, 25-07, 25-08, 25-09]
files_modified:
  - dashboard_renderer/components/signals.py
  - dashboard_renderer/components/positions.py
  - dashboard_renderer/components/trades.py
  - dashboard_renderer/components/paper_trades.py
  - dashboard_renderer/components/header.py
  - dashboard_renderer/components/settings.py
  - dashboard_renderer/components/nav.py
  - dashboard_renderer/shell.py
  - tests/test_dashboard.py
autonomous: true
requirements: [P25-11, P25-12]
must_haves:
  truths:
    - "Component renderers emit class=\"signal-{flat|long|short}\" instead of inline style=\"color:...\" (D-19 #5)"
    - "FLAT/LONG/SHORT signal big-labels render with a <span class=\"status-dot status-dot--{state}\" aria-hidden=\"true\"></span> glyph beside the label (D-19 #3)"
    - "Open Positions / Closed Trades / Trailing Stops tables are wrapped in <div class=\"table-scroll\" tabindex=\"0\" role=\"region\" aria-label=\"...\"> (D-20 component side)"
    - "Every <td> in those wide tables has data-label=\"{column header}\" attribute (consumed by 25-09 stacked-row CSS)"
    - "shell.py emits a JS listener that syncs aria-expanded with the open state of every <details> element on initial load AND after every htmx:afterSwap (D-19 #1)"
    - "D-19 #4 (Market <select> id/for pairing) is N/A — the <select> is removed by Plan 25-03; recorded as a confirmed source-trace fact, not an implementation task"
    - "D-19 #6 label-for pairing audit on remaining forms (Add-market chip, Settings, Account, Market Test) confirms every <input>/<select> has either an explicit <label for=\"X\"> sibling, an aria-label, or aria-labelledby"
  artifacts:
    - path: dashboard_renderer/components/signals.py
      provides: "Signal big-label uses class=signal-{state} + status-dot glyph; zero inline style=\"color:...\""
      contains: "signal-flat"
    - path: dashboard_renderer/components/positions.py
      provides: "Open Positions table wrapped in <div class=\"table-scroll\" tabindex=\"0\" role=\"region\" aria-label=\"Open positions (scrollable)\">"
      contains: "table-scroll"
    - path: dashboard_renderer/components/trades.py
      provides: "Closed Trades + Trailing Stops tables wrapped in table-scroll regions"
      contains: "table-scroll"
    - path: dashboard_renderer/components/paper_trades.py
      provides: "Paper trades wide tables wrapped; data-label attrs emitted on each <td>"
      contains: "data-label"
    - path: dashboard_renderer/shell.py
      provides: "_DETAILS_ARIA_SYNC_JS appended to shell; binds on DOMContentLoaded + htmx:afterSwap"
      contains: "aria-expanded"
    - path: tests/test_dashboard.py
      provides: "TestPhase25LabelForAudit — runtime grep over rendered HTML asserting no orphan <input>/<select> without label/aria-label"
      contains: "TestPhase25LabelForAudit"
  key_links:
    - from: "<details> toggle event"
      to: "aria-expanded attribute sync"
      via: "JS event listener in shell.py + initial pass on DOMContentLoaded"
      pattern: "addEventListener\\('toggle'|aria-expanded"
    - from: "components/{positions,trades,paper_trades}.py table rendering"
      to: "25-09 .table-scroll CSS rules"
      via: "<div class=\"table-scroll\" ...> wrapper around <table>"
      pattern: "class=\"table-scroll\""
    - from: "components/signals.py FLAT/LONG/SHORT label rendering"
      to: "25-09 .signal-{flat|long|short} + .status-dot--{flat|long|short} CSS classes"
      via: "class= attribute swap (no inline style)"
      pattern: "signal-(flat|long|short)"
---

<objective>
Wave 4 component-a11y wiring. Implements the 25-09 class catalog at the component level — replaces inline style="color:..." with semantic classes, wraps wide tables in scrollable focusable regions with per-cell data-label attributes for the stacked-row mobile layout, adds the FLAT/LONG/SHORT status-dot glyphs, and ships the aria-expanded sync JS for <details> elements.

Also closes the D-19 #6 label-for pairing audit on the remaining form surfaces (Add-market chip, Settings page, Account page, Market Test page) — D-19 #4 (Market `<select>` id/for) is N/A because Plan 25-03 deleted the `<select>`.

depends_on 25-09 because the CSS classes referenced here (.signal-flat, .table-scroll, .status-dot--*) MUST exist in _INLINE_CSS before component renderers reference them — otherwise the rendered HTML degrades to unstyled text.

Output: zero inline color styles; wide tables responsive; status dots beside FLAT/LONG/SHORT; aria-expanded synced; D-19 #6 label-for audit codified as a regression test.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-RESEARCH.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-09-SUMMARY.md
@dashboard_renderer/components/signals.py
@dashboard_renderer/components/positions.py
@dashboard_renderer/components/trades.py
@dashboard_renderer/components/paper_trades.py
@dashboard_renderer/components/header.py
@dashboard_renderer/components/settings.py
@dashboard_renderer/components/nav.py
@dashboard_renderer/shell.py
@dashboard.py

<interfaces>
# CSS classes locked by Plan 25-09 (referenced here):
#   .signal-flat, .signal-long, .signal-short            (color)
#   .status-dot, .status-dot--{success|stale|failure|never|flat|long|short|neutral}
#   .table-scroll                                        (wrapper + mobile @media)
#   :focus-visible outline rule applies to summary, [role=tab], a, button, etc.
#
# Wide-table column counts (per UI-SPEC §Layout):
#   Open Positions: 9 cols (instrument, side, entry_dt, entry_px, contracts, stop, mark, unrealised P&L, age)
#   Closed Trades: 7 cols (instrument, side, entry_dt, exit_dt, entry_px, exit_px, realised P&L)
#   Trailing Stops: 7 cols (instrument, side, current stop, ATR distance, days_in_trade, peak_favourable, alert_state)
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Replace inline color styles + emit status-dot glyphs in signals.py + wrap wide tables in positions/trades/paper_trades + emit data-label attrs</name>
  <read_first>
    - dashboard_renderer/components/signals.py — locate `f'<p class="big-label" style="color: {colour}">{label}</p>'` (around line 53 per RESEARCH §canonical_refs)
    - dashboard_renderer/components/positions.py — Open Positions table renderer
    - dashboard_renderer/components/trades.py — Closed Trades + Trailing Stops table renderers
    - dashboard_renderer/components/paper_trades.py — Open Paper Trades + Closed Paper Trades tables
    - dashboard_renderer/components/header.py — confirm header status-strip already uses .status-dot / .status-dot--* classes (Plan 25-06 work)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-09-SUMMARY.md — class catalog from Plan 25-09
  </read_first>
  <files>dashboard_renderer/components/signals.py, dashboard_renderer/components/positions.py, dashboard_renderer/components/trades.py, dashboard_renderer/components/paper_trades.py</files>
  <action>
**Step 1 — signals.py: replace inline color + add status-dot glyph (D-19 #3, #5):**

Locate the big-label emission. The current pattern (per RESEARCH §canonical_refs) is:

```python
out.append(f'<p class="big-label" style="color: {colour}">{label}</p>')
```

Replace with:

```python
state_class = label.lower()  # 'flat' | 'long' | 'short' (case-folded)
out.append(
    f'<p class="big-label signal-{state_class}">'
    f'<span class="status-dot status-dot--{state_class}" aria-hidden="true"></span>'
    f'{label}'
    f'</p>'
)
```

Drop the `colour` variable derivation if its sole consumer was the inline style — keep it if used elsewhere. After the swap, ensure `label` is one of the locked tokens FLAT / LONG / SHORT (case-sensitive in display); the lower() applies to the class name only.

**Step 2 — positions.py: wrap Open Positions table + emit data-label per <td>:**

For the Open Positions table, change the existing `<table>...</table>` emission to:

```python
out.append('<div class="table-scroll" tabindex="0" role="region" aria-label="Open positions (scrollable)">\n')
out.append('  <table>\n')
# ... existing thead + tbody rendering ...
out.append('  </table>\n')
out.append('</div>\n')
```

For each `<td>` in the row-render loop, emit `data-label="{column header}"`:

```python
# Column header list pinned (must match thead order):
_OPEN_POS_COLS = ('Instrument', 'Side', 'Entry', 'Entry price', 'Contracts', 'Stop', 'Mark', 'Unrealised P&L', 'Age')

# In the row loop:
out.append('    <tr>\n')
for col_header, value in zip(_OPEN_POS_COLS, row_values):
    # html.escape both the header (used in attr) and value (cell text)
    out.append(f'      <td data-label="{html.escape(col_header, quote=True)}">{html.escape(str(value))}</td>\n')
out.append('    </tr>\n')
```

If there is currency / number formatting that should not be html-escaped (already-safe formatted strings), keep using the existing formatter and apply html.escape only where the value originates from user-controllable data. The data-label values come from the static _OPEN_POS_COLS tuple (server-controlled) — escape defensively but no XSS surface.

**Step 3 — trades.py: same wrapper + data-label pattern for Closed Trades and Trailing Stops:**

```python
_CLOSED_TRADE_COLS = ('Instrument', 'Side', 'Entry date', 'Exit date', 'Entry price', 'Exit price', 'Realised P&L')
_TRAILING_STOP_COLS = ('Instrument', 'Side', 'Current stop', 'ATR distance', 'Days in trade', 'Peak favourable', 'Alert state')
```

Each table wrapped in `<div class="table-scroll" tabindex="0" role="region" aria-label="{descriptive}">…</div>` with a unique aria-label per table.

**Step 4 — paper_trades.py: same wrapper for Open Paper Trades + Closed Paper Trades tables:**

```python
_OPEN_PAPER_COLS = ('Instrument', 'Side', 'Entry date', 'Entry price', 'Contracts', 'Stop price', 'Mark', 'Unrealised P&L', 'Age')
_CLOSED_PAPER_COLS = ('Instrument', 'Side', 'Entry date', 'Exit date', 'Entry price', 'Exit price', 'Realised P&L')
```

Wrap in table-scroll regions with aria-label "Open paper trades (scrollable)" / "Closed paper trades (scrollable)".

**Step 5 — flip xfail decorators on tests:**

Remove `@pytest.mark.xfail` from `tests/test_dashboard.py::TestPhase25NoInlineColor` and `TestPhase25WideTable`. Run, confirm green.
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -c "
from dashboard_renderer.api import render_dashboard
state = {'last_run': '2026-04-23', 'markets': {'SPI200': {}}, 'warnings': [], 'equity_history': [], 'signals': {'SPI200': {'strategy_version': 'v1.2.0', 'signal': 0}}, 'paper_trades': [{'status': 'closed', 'realised_pnl': 100}], 'positions': [], 'closed_trades': [], 'strategy_settings': {'SPI200': {}}, 'account_balance_paper': 100000.0, 'account_balance_live': 100000.0}
out = render_dashboard(state)
# D-19 #5: zero inline color styles
assert 'style=\"color:' not in out, 'D-19 #5 violation: inline color style still present'
# D-19 #3: status-dot glyph beside label
assert 'class=\"status-dot status-dot--' in out, 'D-19 #3 violation: status-dot glyph missing'
# D-20: table-scroll wrapper + role=region
assert 'class=\"table-scroll\"' in out, 'D-20 violation: table-scroll wrapper missing'
assert 'role=\"region\"' in out, 'D-20 violation: role=region missing'
# data-label emission
assert 'data-label=' in out, 'data-label attrs missing'
print('OK')
" && python -m pytest tests/test_dashboard.py::TestPhase25NoInlineColor tests/test_dashboard.py::TestPhase25WideTable -q --no-header 2>&1 | tail -5</automated>
  </verify>
  <done>
    - signals.py emits class="signal-{state}" + status-dot glyph; zero inline style="color:..." in any rendered HTML
    - positions.py / trades.py / paper_trades.py wrap their <table> elements in <div class="table-scroll" tabindex="0" role="region" aria-label="...">
    - Each <td> in those wide tables carries data-label="{column header}" (the column header tuples _OPEN_POS_COLS / _CLOSED_TRADE_COLS / _TRAILING_STOP_COLS / _OPEN_PAPER_COLS / _CLOSED_PAPER_COLS are defined as module-level constants)
    - TestPhase25NoInlineColor + TestPhase25WideTable tests PASS (xfail removed)
  </done>
</task>

<task type="auto">
  <name>Task 2: Append _DETAILS_ARIA_SYNC_JS to shell.py + audit + lock D-19 #6 label-for pairing across all forms</name>
  <read_first>
    - dashboard_renderer/shell.py (after Plan 25-09's CSS edits — confirm scripts block placement)
    - dashboard_renderer/components/nav.py — Add-market chip form (Plan 25-05 emission) — confirm <label for="add-market-id"> / <label for="add-market-label"> / <label for="add-market-size"> already paired
    - dashboard_renderer/components/settings.py — fieldset-grouped Settings form (Plan 25-08 work) — every <input id="settings-{market_id}-{field}"> must have a sibling <label for="settings-{market_id}-{field}">
    - dashboard.py — Account page form (account_balance fields) and Market Test override form
    - tests/test_dashboard.py — for adding TestPhase25LabelForAudit
  </read_first>
  <files>dashboard_renderer/shell.py, dashboard_renderer/components/nav.py, dashboard_renderer/components/settings.py, dashboard.py, tests/test_dashboard.py</files>
  <action>
**Step 1 — append _DETAILS_ARIA_SYNC_JS to shell.py (D-19 #1):**

Add the following constant near the existing _AWST_COUNTDOWN_JS / _TABS_KEYBOARD_JS blocks:

```python
_DETAILS_ARIA_SYNC_JS = """
<script>
// Phase 25 D-19 #1: sync aria-expanded with <details> open state for SR users.
(function () {
  function syncAriaExpanded(el) {
    el.setAttribute('aria-expanded', el.open ? 'true' : 'false');
  }
  function bindAll() {
    document.querySelectorAll('details').forEach(function (d) {
      syncAriaExpanded(d);
      // Avoid duplicate toggle listeners after re-bind: store a marker.
      if (!d.dataset.ariaSyncBound) {
        d.addEventListener('toggle', function () { syncAriaExpanded(d); });
        d.dataset.ariaSyncBound = '1';
      }
    });
  }
  document.addEventListener('DOMContentLoaded', bindAll);
  document.body.addEventListener('htmx:afterSwap', bindAll);
})();
</script>
"""
```

Wire `_DETAILS_ARIA_SYNC_JS` into `render_html_shell` body block (append after the other inline scripts: `_HANDLE_TRADES_ERROR_JS`, `_TRACE_TOGGLE_JS`, `_AWST_COUNTDOWN_JS`, `_TABS_KEYBOARD_JS`, `_STATUS_STRIP_REFRESH_JS` — exact order matches existing emission).

**Step 2 — D-19 #4 N/A informational note (NO action):**

D-19 #4 (Market `<select>` id/for pairing) is N/A because Plan 25-03 replaces the `<select aria-label="Market selection">` (originally at `dashboard.html:672`) with a tab-strip widget rendered by `render_market_strip` in `dashboard_renderer/components/nav.py`. The id/for pairing requirement is moot once the surface is removed.

This is recorded as a confirmed source-trace fact, not an implementation task. The acceptance check is the existence of zero `<select aria-label="Market selection">` occurrences in any rendered HTML (proves the surface was removed):

```bash
grep -rn '<select aria-label="Market selection">' dashboard_renderer/ web/templates/ 2>/dev/null
# Expected: zero results.
```

**Step 3 — D-19 #6 label-for audit on remaining forms:**

Enumerate every `<input>` / `<select>` / `<textarea>` emitted by the renderer and ensure each has ONE of:
- A sibling `<label for="X">` with matching id, OR
- An `aria-label="..."` attribute, OR
- An `aria-labelledby="..."` attribute pointing to a present id.

Forms in scope (Plan 25-03 already removed the dashboard `<select>`; the chip from Plan 25-05 has its labels per the chip emission code):

1. **Add-market chip** (`dashboard_renderer/components/nav.py:render_add_market_chip`):
   - `<input id="add-market-id">` paired with `<label for="add-market-id">Code</label>` ✓ (existing per Plan 25-05)
   - `<input id="add-market-label">` paired with `<label for="add-market-label">Label</label>` ✓
   - `<input id="add-market-size">` paired with `<label for="add-market-size">Contract size</label>` ✓
   - Verify: re-read the chip emission to confirm each pair survived Plan 25-05 ship.

2. **Settings form** (`dashboard_renderer/components/settings.py:render_settings_tab` after Plan 25-08):
   - Every numeric `<input id="settings-{market_id}-{field-name}">` must have a sibling `<label for="settings-{market_id}-{field-name}">`. Plan 25-08's refactor emits this; this audit verifies.
   - For each input, also confirm `name="{field_name}"` matches the server-side Pydantic schema field — this is preservation, not new wiring.

3. **Market Test override form** (`dashboard_renderer/components/settings.py:render_market_test_tab` after Plan 25-08):
   - Same id/for pattern as Settings, scoped to `id="market-test-{market_id}-{field-name}"` to avoid id collisions if both forms render on the same page (which they don't post-Plan 25-03 — but defensive uniqueness still wise).

4. **Account page form** (`dashboard.py` — account_balance form):
   - `<input id="account-balance-paper">` ↔ `<label for="account-balance-paper">Paper account balance</label>`
   - `<input id="account-balance-live">` ↔ `<label for="account-balance-live">Live account balance</label>`
   - Locate the existing form; if labels are missing or use placeholder-only convention, add explicit `<label for="...">` pairs per UI-SPEC §Account page.

For ANY input found without a label/aria pairing: add a paired `<label for="...">` immediately above the input, using the column-or-section heading text for the label content.

**Step 4 — Add the regression test TestPhase25LabelForAudit to tests/test_dashboard.py:**

Append a parse-and-assert test that scans the full rendered HTML for orphan inputs:

```python
class TestPhase25LabelForAudit:
    """D-19 #6: every <input>/<select>/<textarea> in rendered HTML must have a
    label/aria-label/aria-labelledby. Hidden inputs and submit/reset buttons exempt.
    """
    def test_no_orphan_inputs(self):
        from html.parser import HTMLParser
        from dashboard_renderer.api import render_dashboard
        state = {
            'last_run': '2026-04-23',
            'markets': {'SPI200': {'sort_order': 10, 'contract_size': 5}},
            'warnings': [],
            'equity_history': [],
            'signals': {'SPI200': {'strategy_version': 'v1.2.0', 'signal': 0}},
            'paper_trades': [],
            'positions': [],
            'closed_trades': [],
            'strategy_settings': {'SPI200': {}},
            'account_balance_paper': 100000.0,
            'account_balance_live': 100000.0,
        }
        html_out = render_dashboard(state)

        class Collector(HTMLParser):
            def __init__(self):
                super().__init__()
                self.inputs = []  # list of (tag, attrs_dict)
                self.label_fors = set()
                self.ids = set()
            def handle_starttag(self, tag, attrs):
                d = dict(attrs)
                if tag in ('input', 'select', 'textarea'):
                    itype = d.get('type', 'text').lower()
                    # Exempt non-labelled-by-design types
                    if itype in ('hidden', 'submit', 'reset', 'button', 'image'):
                        return
                    self.inputs.append((tag, d))
                if tag == 'label' and 'for' in d:
                    self.label_fors.add(d['for'])
                if 'id' in d:
                    self.ids.add(d['id'])
        c = Collector()
        c.feed(html_out)

        orphans = []
        for tag, attrs in c.inputs:
            input_id = attrs.get('id')
            has_label_for = input_id in c.label_fors if input_id else False
            has_aria_label = 'aria-label' in attrs
            has_aria_labelledby = attrs.get('aria-labelledby') in c.ids if attrs.get('aria-labelledby') else False
            if not (has_label_for or has_aria_label or has_aria_labelledby):
                orphans.append((tag, attrs))
        assert not orphans, f"D-19 #6 violation — {len(orphans)} orphan input(s) without label/aria pairing: {orphans[:5]}"

    def test_market_select_surface_removed(self):
        """D-19 #4 N/A confirmation — Plan 25-03 deleted the Market <select>."""
        from dashboard_renderer.api import render_dashboard
        state = {
            'last_run': '2026-04-23',
            'markets': {'SPI200': {}, 'AUDUSD': {}},
            'warnings': [],
            'equity_history': [],
            'signals': {},
            'paper_trades': [],
            'positions': [],
            'closed_trades': [],
            'strategy_settings': {'SPI200': {}, 'AUDUSD': {}},
            'account_balance_paper': 100000.0,
            'account_balance_live': 100000.0,
        }
        html_out = render_dashboard(state)
        assert '<select aria-label="Market selection">' not in html_out, \
            'D-19 #4 expected to be N/A because the <select> is removed by Plan 25-03 — but the surface still exists.'
```

This test is NOT xfail — it must pass green at end of Plan 25-09b.

**Step 5 — run the full test suite + the new audit test:**

```bash
pytest tests/test_dashboard.py::TestPhase25LabelForAudit -q
pytest -q
```

Both must exit 0.
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && grep -q "_DETAILS_ARIA_SYNC_JS" dashboard_renderer/shell.py && echo "JS const present" && grep -c '<select aria-label="Market selection">' dashboard_renderer/ web/templates/ 2>/dev/null | grep -v ':0' | head -3 || echo "Market <select> removed (D-19 #4 N/A confirmed)" && python -m pytest tests/test_dashboard.py::TestPhase25LabelForAudit -q --no-header 2>&1 | tail -10</automated>
  </verify>
  <done>
    - shell.py contains _DETAILS_ARIA_SYNC_JS and emits it from render_html_shell after the other inline scripts
    - Add-market chip / Settings / Market Test / Account forms all have label-for OR aria-label OR aria-labelledby pairing for every input/select/textarea (excluding hidden/submit/reset/button)
    - Market <select> surface is confirmed absent in any rendered HTML (D-19 #4 N/A)
    - tests/test_dashboard.py::TestPhase25LabelForAudit passes green (no xfail)
    - Full test suite green
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Renderer → HTML output | Component-level class-name and attribute additions; no new user-controlled interpolation. |
| Browser DOM → aria-expanded mutation | aria-expanded is a presentation attribute, not auth-relevant; sync runs entirely client-side. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-25-09b-01 | Tampering (XSS via data-label) | wide-table rendering | mitigate | data-label values are pinned column-header tuples (server-controlled static strings); no user input flows into data-label. Verified by code reading: `_OPEN_POS_COLS`, `_CLOSED_TRADE_COLS`, etc. are module-level constants. Defensive html.escape applied at emission time. |
| T-25-09b-02 | (n/a) | aria-expanded sync JS | accept | Pure presentation-attribute sync; runs only against existing <details> elements. No new event surface. |
| T-25-09b-03 | (n/a) | label-for audit | accept | Audit codified as a regression test; future renderer changes that introduce orphan inputs will fail TestPhase25LabelForAudit at CI. |
</threat_model>

<verification>
- TestPhase25NoInlineColor + TestPhase25WideTable + TestPhase25LabelForAudit all PASS.
- Grep gate: `grep -rn 'style="color:' dashboard_renderer/ dashboard.py | grep -v '^[^:]*:[0-9]*:#' | grep -v '\.pyc'` returns 0 active CSS matches.
- Grep gate: `grep -c '<select aria-label="Market selection">' dashboard_renderer/ web/templates/ 2>/dev/null` returns 0.
- Grep gate: `grep -q "_DETAILS_ARIA_SYNC_JS" dashboard_renderer/shell.py`.
- Full suite green: `pytest -q` exits 0.
</verification>

<success_criteria>
- D-19 #1 aria-expanded synced via shell-emitted JS, on initial load AND after every htmx:afterSwap.
- D-19 #3 status-dot glyph beside FLAT/LONG/SHORT in component templates.
- D-19 #4 confirmed N/A — surface removed by Plan 25-03; regression test asserts non-presence.
- D-19 #5 inline color styles eradicated — replaced with semantic .signal-{state} classes.
- D-19 #6 label-for audit codified — orphan-input test passes; all forms (Add-market chip, Settings, Account, Market Test) confirmed paired.
- D-20 component side: wide tables wrapped in role=region scrollable containers with data-label per <td>.
</success_criteria>

<output>
After completion, create `.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-09b-SUMMARY.md` listing each form audited, the orphan inputs found and fixed (if any), the column-header tuples added, and the full test counts after this plan.
</output>
