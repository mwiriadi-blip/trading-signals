---
phase: 25
plan: 08
type: execute
wave: 3
depends_on: [25-02]
files_modified:
  - dashboard_renderer/components/settings.py
autonomous: false
requirements: [P25-07]
must_haves:
  truths:
    - "Settings page renders 3 <fieldset> elements with legends 'Entry rules', 'Risk', 'Direction'"
    - "Every input has a <small> helper text per UI-SPEC §Settings page"
    - "Market Test page override fields show inherited Settings defaults as placeholder text per D-14"
    - "Save button copy is 'Save settings' (sentence case per UI-SPEC §Settings page)"
    - "Operator has reviewed and locked the 9 drafted helper-text strings (D-13) before any helper-text emission ships in render_settings_tab"
  artifacts:
    - path: dashboard_renderer/components/settings.py
      provides: "render_settings_tab grouped into 3 fieldsets with helper text; render_market_test_tab with placeholder defaults"
      contains: "<fieldset>"
  key_links:
    - from: "render_settings_tab fieldset structure"
      to: "<legend>Entry rules</legend>, <legend>Risk</legend>, <legend>Direction</legend>"
      via: "static legends per D-12"
      pattern: "<legend>(Entry rules|Risk|Direction)</legend>"
---

<objective>
Wave 3. Group the 18 numeric Settings inputs into 3 fieldsets per D-12 (Entry rules, Risk, Direction) and add helper text per D-13. Add inherited-defaults-as-placeholder behavior to Market Test override fields per D-14.

Output: settings.py refactored with semantic <fieldset>/<legend>/<small> structure.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md
@dashboard_renderer/components/settings.py

<interfaces>
# Per UI-SPEC §Settings page Field-to-fieldset mapping (planner-locked):
# Fieldset 1 — "Entry rules":
#   - ADX gate (helper: "Skips trade days when trend strength is weak. Default 25.")
#   - Momentum votes (helper: "Number of positive momentum windows required to enter. Default 2.")
# Fieldset 2 — "Risk":
#   - Long ATR stop multiple (helper: "Trailing-stop distance for long positions. Default 1.5×ATR.")
#   - Short ATR stop multiple (helper: "Trailing-stop distance for short positions. Default 1.5×ATR.")
#   - Long risk percent (helper: "Account risk per long trade. Default 1.0%.")
#   - Short risk percent (helper: "Account risk per short trade. Default 1.0%.")
#   - Contract cap (helper: "Maximum contracts per pyramid level. Default 3.")
# Fieldset 3 — "Direction":
#   - Mode (helper: "Long-only, short-only, or both. Default both.")
#   - 1-contract floor (helper: "Skip the trade when sizing would compute < 1 contract. Default off.")
</interfaces>
</context>

<tasks>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 1: Operator review + lock helper-text strings (D-13)</name>
  <what-built>
    The planner has drafted the 9 helper-text strings below (one `<small class="field-help">` per Settings input, mapping per UI-SPEC §Settings page). D-13 requires operator review BEFORE the strings ship in `render_settings_tab` — this checkpoint surfaces the drafts and blocks until the operator confirms or rewrites them.
  </what-built>
  <how-to-verify>
**Drafted strings (`label` → `<small>` helper):**

Fieldset 1 — **Entry rules**
1. ADX gate → "Skips trade days when trend strength is weak. Default 25."
2. Momentum votes → "Number of positive momentum windows required to enter. Default 2."

Fieldset 2 — **Risk**
3. Long ATR stop multiple → "Trailing-stop distance for long positions. Default 1.5×ATR."
4. Short ATR stop multiple → "Trailing-stop distance for short positions. Default 1.5×ATR."
5. Long risk percent → "Account risk per long trade. Default 1.0%."
6. Short risk percent → "Account risk per short trade. Default 1.0%."
7. Contract cap → "Maximum contracts per pyramid level. Default 3."

Fieldset 3 — **Direction**
8. Mode → "Long-only, short-only, or both. Default both."
9. 1-contract floor → "Skip the trade when sizing would compute < 1 contract. Default off."

**Review steps:**
1. For each line above, decide: ACCEPT as drafted, REWRITE (provide new copy), or DROP (omit `<small>` for that field).
2. Persist the locked strings to `.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-helper-text-locked.md` in the same numbered list format. The file is the canonical input for Task 2.
   - If the operator says "use these as drafted", the executor copies the list verbatim into `25-helper-text-locked.md` with a header line `# Phase 25 D-13 helper-text — locked YYYY-MM-DD by operator review`.
   - If the operator rewrites any line, the executor replaces only those lines and preserves the rest.
3. Do NOT modify `dashboard_renderer/components/settings.py` until this file exists.
  </how-to-verify>
  <resume-signal>Type "approved" (use drafts as-is) or paste the rewritten lines (numbered) for any helpers you want to change. Either form unblocks Task 2.</resume-signal>
</task>

<task type="auto">
  <name>Task 2: Refactor render_settings_tab into 3 fieldsets + helper text + sentence-case button copy</name>
  <read_first>
    - dashboard_renderer/components/settings.py (existing render_settings_tab — currently flat <div class="field"> per input)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md §Settings page (full copy contract) and §Disambiguated buttons
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-helper-text-locked.md (operator-locked strings from Task 1; MUST exist before this task starts)
  </read_first>
  <files>dashboard_renderer/components/settings.py</files>
  <action>
**Step 0 — read the operator-locked helper-text file.** If `25-helper-text-locked.md` does not exist, halt with the message "Task 1 checkpoint not satisfied" — do not synthesise the strings.

**Step 1 — refactor `render_settings_tab` to group inputs by fieldset.**

Preserve the existing form action (`hx-patch="/markets/{market_id}/settings"` or `/markets/settings`) — this is the surface that test_dashboard.py:3120 pins (count >= 2). The fieldset wrapper does not change form action.

For each input, emit:

```html
<div class="field">
  <label for="settings-{market_id}-{field-name}">Field Label</label>
  <input id="settings-{market_id}-{field-name}" name="{field_name}" type="number" step="any" value="{value}">
  <small class="field-help">{operator-locked helper text from 25-helper-text-locked.md}</small>
</div>
```

Each fieldset:

```html
<fieldset>
  <legend>Entry rules</legend>
  <!-- ADX gate, Momentum votes -->
</fieldset>
<fieldset>
  <legend>Risk</legend>
  <!-- long ATR stop, short ATR stop, long risk %, short risk %, contract cap -->
</fieldset>
<fieldset>
  <legend>Direction</legend>
  <!-- Mode, 1-contract floor -->
</fieldset>
```

If any helper line was DROP'd by the operator, omit the `<small>` for that field — do not invent fallback copy.

**Step 2 — Save button copy + section subtitle:**

Save button: change copy from `Save Settings` → `Save settings` (sentence case per UI-SPEC §Disambiguated buttons).

Section subtitle: add `<p class="subtitle">Per-market trading rules. Changes take effect on the next 08:00 AWST cycle.</p>` immediately under the `<h2>Settings</h2>` heading per UI-SPEC §Settings page.

**Step 3 — flip xfail decorator on TestPhase25Settings:**

Remove `@pytest.mark.xfail` from `tests/test_dashboard.py::TestPhase25Settings`. Run pytest, confirm green. Existing assertion `tests/test_dashboard.py:3120` (count of `hx-patch="/markets/settings"` ≥ 2) must remain green — verify after refactor.
  </action>
  <verify>
    <automated>test -f .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-helper-text-locked.md && python -m pytest tests/test_dashboard.py::TestPhase25Settings -q --no-header 2>&1 | tail -5 && python -m pytest tests/test_dashboard.py -k "hx_patch_markets_settings or settings" -q --no-header 2>&1 | tail -5</automated>
  </verify>
  <done>
    - 25-helper-text-locked.md exists in the phase dir (output of Task 1 checkpoint)
    - 3 <fieldset> elements with legends "Entry rules", "Risk", "Direction"
    - Every numeric input has paired <label for=…> and (where the operator did not DROP) <small class=field-help> with the operator-locked text
    - Save button copy is "Save settings" (sentence case)
    - <h2>Settings</h2> followed by <p class="subtitle">Per-market trading rules…</p>
    - TestPhase25Settings tests PASS
    - test_dashboard.py:3120 hx-patch invariant preserved (count >= 2)
  </done>
</task>

<task type="auto">
  <name>Task 3: Market Test page — placeholder defaults from inherited Settings + xfail flips</name>
  <read_first>
    - dashboard_renderer/components/settings.py (existing render_market_test_tab)
    - .planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-UI-SPEC.md §Market Test page
    - tests/test_dashboard.py — existing market-test assertions, if any
  </read_first>
  <files>dashboard_renderer/components/settings.py</files>
  <action>
For each Market Test override input, set `placeholder="{inherited default}"` derived from the per-market saved settings:

```python
inherited_value = strategy_settings.get(market_id, {}).get(field_name)
placeholder_attr = f' placeholder="{html.escape(str(inherited_value), quote=True)}"' if inherited_value is not None else ''
out.append(
    f'<div class="field">\n'
    f'  <label for="market-test-{html.escape(market_id, quote=True)}-{field_name}">{label}</label>\n'
    f'  <input id="market-test-{html.escape(market_id, quote=True)}-{field_name}" name="{field_name}" type="number" step="any"{placeholder_attr}>\n'
    f'  <small class="field-help">Inherits {label} from Settings ({inherited_value}) when blank.</small>\n'
    f'</div>\n'
)
```

If `inherited_value is None` (market has no saved settings — fresh state), emit no placeholder and adapt the helper text: `Inherits {label} from Settings when blank.`.

Update any existing market-test xfail tests in tests/test_dashboard.py to be green.
  </action>
  <verify>
    <automated>python -m pytest tests/test_dashboard.py -k "market_test" -q --no-header 2>&1 | tail -5</automated>
  </verify>
  <done>
    - Market Test override input fields show inherited Settings defaults as placeholder
    - id/for pairing on every market-test input (id="market-test-{market_id}-{field_name}")
    - Helper text references inherited value when present
    - Market-test xfail tests PASS (or remain xfail only where blocked by an explicit downstream plan)
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Settings input → POST/PATCH /markets/settings | User inputs cross trust boundary; existing Pydantic validation gates. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-25-08-01 | (n/a) | fieldset refactor | accept | Pure markup change; no new validation surface. Existing field name → server validation pipeline preserved. Helper text is server-controlled static copy (no interpolation). |
</threat_model>

<verification>
- TestPhase25Settings tests PASS.
- Existing settings-form test still green.
- Grep gate: `grep -c '<fieldset>' <(python -c 'from dashboard_renderer.api import render_dashboard; ...')` returns ≥3 per page.
</verification>

<success_criteria>
- Settings page is scannable: 3 fieldsets, helper text per field.
- Market Test placeholders inherit Settings defaults.
- Sentence-case button copy applied.
</success_criteria>

<output>
After completion, create `.planning/phases/25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences/25-08-SUMMARY.md` capturing the field-to-fieldset mapping and helper-text choices.
</output>
