# Phase 17: Per-signal Calculation Transparency — Research

**Researched:** 2026-04-30
**Domain:** HTML `<details>` disclosure UX, vanilla JS click-handler patterns, OHLC grid layout,
float-display Excel parity, cookie namespace safety, Python html.escape, pytest HTML-assertion
testing strategy.
**Confidence:** MEDIUM-HIGH overall — all browser-compat claims verified against MDN/WebKit sources;
Excel General-format claim is MEDIUM (Microsoft docs incomplete; supplemented by ASSUMED knowledge);
iOS VoiceOver state-announcement claim verified via Scott O'Hara primary source.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01** — Persist 40-bar OHLC slice + full indicator scalar set in `state.signals[<inst>]` on every
  daily run; dashboard.py reads primitives from state dict — no live fetch, no recompute.
- **D-02** — 40 bars per instrument. Per-instrument array named `state.signals[<inst>].ohlc_window`.
- **D-03** — Tap-to-toggle inline reveal per indicator. State in `data-formula-open="true|false"`.
  CSS `.formula-row[hidden]` controls visibility. Zero JS dependency beyond one click handler.
- **D-04** — Inline below per-instrument signal card. Default-collapsed. `<details>` disclosure labelled
  "Show calculations". Cookie persistence via `tsi_trace_open`. No localStorage.
- **D-05** — 6 decimals for every indicator scalar. Format string `f'{value:.6f}'`. NaN handled
  separately per D-06.
- **D-06** — Explicit reason text: `n/a (need 20 bars, have 14)` / `n/a (flat price)`. Helper:
  `dashboard._format_indicator_value(value, seed_required, bars_available) -> str`.
- **D-07** — Three colored sign badges + ADX gate badge + final outcome line in Vote panel.
- **D-08** — Schema bump 4→5. Migration `_migrate_v4_to_v5` registered in `MIGRATIONS[5]`.
- **D-09** — Extended `state.signals[<inst>]` shape: `ohlc_window` (list[dict]) + `indicator_scalars`
  (dict, 9 keys). `last_scalars` retained for backwards-compat.
- **D-10** — `dashboard.py` continues NOT to import `system_params`, `state_manager`, `data_fetcher`,
  `yfinance`, or `signal_engine`. Formula text inlined as `_TRACE_FORMULAS` dict. Forbidden-imports
  AST guard test stays green by construction.
- **D-11** — `--test` mode read-only. Empty `ohlc_window` renders "Awaiting first daily run" copy.
- **D-12** — Cookie `tsi_trace_open`, comma-separated instrument keys. `Path=/; SameSite=Lax`.
  90-day expiry. NOT signed (UI preference, no privilege). No `Secure` requirement.
- **D-13** — `_TRACE_FORMULAS` plain-text dict inlined in `dashboard.py`. No MathJax/KaTeX.

### Claude's Discretion

None beyond what the planner resolves per normal task sequencing.

### Deferred Ideas (OUT OF SCOPE)

- Adjustable bar count / alternate timeframe (v1.3+).
- `/explain/<inst>` route (rejected for v1.2).
- Live-edit formula display.
- Email parity for trace panels.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRACE-01 | Inputs panel per instrument — 40 OHLC rows, Excel-reproducible | §Float Display, §OHLC Grid Layout, §Code Examples |
| TRACE-02 | Indicators panel — TR/ATR/+DI/-DI/ADX/Mom1/Mom3/Mom12/RVol with formula + numeric | §Details Disclosure, §WCAG 2.1 AA, §Code Examples |
| TRACE-03 | Vote panel — Mom sign badges, ADX gate badge, final outcome | §Code Examples, §Architecture Patterns |
| TRACE-04 | All three panels render without state mutation; survives `--test` | §Architecture Patterns (read-only render) |
| TRACE-05 | Forbidden-imports AST guard extended; trace panels import no I/O | §Don't Hand-Roll, §Architecture Patterns |
</phase_requirements>

---

## Summary

Phase 17 is a read-only dashboard render extension: three new HTML panels per instrument (Inputs /
Indicators / Vote) with tap-to-toggle inline formula reveal and cookie-persisted disclosure state. The
stack is already pinned and the operator decisions are locked — the research task is to surface gotchas
that CONTEXT.md didn't know to ask about.

**Primary findings:**

1. **iOS Safari click-handler trap:** Mobile Safari does NOT fire `click` events on non-interactive
   elements unless the element has either `cursor: pointer` in CSS or an `onclick` attribute. The
   indicator-name `<span>` cells that trigger formula reveal must have `cursor: pointer`. Without it,
   the toggle silently no-ops on iPhone.

2. **`<details>` toggle event is safe on all relevant iOS versions:** The `toggle` event on `<details>`
   is Baseline Widely Available since January 2020, covering Safari iOS 6+ for the element and iOS 13+
   for the toggle event. The operator's iPhone (iOS 17+) has full support. No polyfill needed.

3. **iOS VoiceOver with Safari does NOT reliably announce `<details>` expanded/collapsed state:** A
   known accessibility gap (documented by Scott O'Hara). The `<details>/<summary>` approach is still
   the right choice for this operator (single user, sighted), but the planner should note this as a
   known limitation rather than a bug to fix.

4. **Cookie namespace: `tsi_trace_open` is safe alongside `tsi_session` and `tsi_trusted`:** Different
   names, same `Path=/` — no collision. The browser sends all three on every request; the server reads
   by name. The `tsi_trace_open` cookie is unsigned and carries no privilege, so accidental read of it
   instead of `tsi_session` in the auth middleware is impossible by grep (they are read by different
   code paths).

5. **Float display: `f'{value:.6f}'` (D-05) gives Excel-parity for AUD/USD:** Excel's General format
   displays digits as entered without trailing zero padding. When operator copies a 6-decimal value
   from the dashboard into an Excel cell, Excel stores full float64 precision (15 sig figs). The
   displayed 6 decimals match; hand-recalc in Excel with the same inputs will match to 1e-6 provided
   the operator does NOT use Excel's `ROUND()` on intermediate steps. No thousands separator for AUD/USD
   indicator scalars (no values exceed 1000 in practice; ATR is in price units, ADX 0-100).

6. **No new dependencies required:** All implementation uses stdlib (`html`, `math`, `json`), existing
   dashboard.py CSS variable palette, vanilla JS `<20 lines, and the existing `<details>` element.

**Primary recommendation:** Implement the `<details>` outer disclosure per D-04 and the indicator-name
click-handler per D-03; add `cursor: pointer` CSS to the indicator-name cells to unblock Mobile Safari
click events; use `data-instrument` attribute on the `<details>` for the cookie read/write path.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| OHLC slice persistence | Backend (main.py write site) | — | daily run populates; render is read-only |
| Indicator scalar persistence | Backend (main.py write site) | — | same write site as ohlc_window |
| Schema migration 4→5 | Backend (state_manager.py) | — | MIGRATIONS dispatch table |
| HTML panel render | Dashboard layer (dashboard.py) | — | hex-boundary; no I/O inside |
| Formula text catalogue | Dashboard layer (dashboard.py) | — | D-10 inlined, not imported |
| Cookie set/read for disclosure state | Browser (JS set) + Dashboard (read at render) | — | JS writes on toggle; Python reads at render to decide `<details open>` |
| CSS badge styling | Dashboard layer (_INLINE_CSS) | — | inline CSS, no external sheet |
| Tap-to-toggle click handler | Browser (vanilla JS ≤20 lines) | — | D-03; zero dependency |

---

## Standard Stack

### Core (no new dependencies — confirmed)

| Library / Module | Version | Purpose | Confirmation |
|------------------|---------|---------|--------------|
| `html` (stdlib) | stdlib | `html.escape()` for all dynamic string injection into HTML | `[VERIFIED: grep dashboard.py]` — already imported |
| `math` (stdlib) | stdlib | `math.isnan()` in `_format_indicator_value` | `[VERIFIED: CONTEXT D-06]` |
| `json` (stdlib) | stdlib | JSON payload for any JS data injection | `[VERIFIED: grep dashboard.py — already used for equity chart]` |
| Vanilla JS | ES5-compatible | Click handler, cookie read/write, `<details>` toggle listener | `[VERIFIED: CONTEXT D-03, D-12]` |
| `<details>/<summary>` HTML | native | Outer disclosure per instrument | `[VERIFIED: CONTEXT D-04]` |

**No new pip packages. No npm packages. No CDN additions.**

### Supporting (CSS patterns)

| Pattern | Purpose | Source |
|---------|---------|--------|
| `font-variant-numeric: tabular-nums` | Digit alignment in OHLC grid | `[VERIFIED: MDN CSS docs + industry standard]` |
| `text-align: right` on numeric `<td>` | Column alignment for hand-recalc | `[VERIFIED: financial data grid standard]` |
| `cursor: pointer` on indicator name cells | Mobile Safari click-event fix | `[VERIFIED: WebKit documented behavior — see §Common Pitfalls]` |

**Version verification:** No packages to verify — all stdlib + native browser.

---

## Architecture Patterns

### System Architecture Diagram

```
Daily run (main.py)
  │
  ▼
compute_indicators(df)
  │  returns: indicator scalars + raw OHLC df slice
  ▼
state_manager.save_state()
  │  writes: state.signals[inst].ohlc_window (40 rows)
  │           state.signals[inst].indicator_scalars (9 keys)
  ▼
state.json  ──────────────────────────────────────────────────────────────────────┐
                                                                                   │
HTTP GET / (FastAPI)                                                               │
  │                                                                                │
  ▼                                                                                │
web/routes/dashboard.py                                                            │
  │  reads: request.cookies.get('tsi_trace_open')                                 │
  │  reads: state.json via load_state()                                           ◄─┘
  │  computes: is_cookie_session bool (existing Phase 16.1 pattern)
  │  computes: trace_open set from cookie
  ▼
dashboard.py::render_dashboard(state, trace_open=set())
  │
  ├── _render_signal_cards(state)
  │     └── per instrument: _render_trace_panels(sig_dict, inst_open=bool)
  │           ├── <details data-instrument="SPI200" [open]>
  │           │     ├── _render_trace_inputs(ohlc_window)      → 40-row OHLC table
  │           │     ├── _render_trace_indicators(scalars)      → 9-row indicator table
  │           │     └── _render_trace_vote(scalars)            → badge layout + outcome
  │           └── </details>
  │
  └── <script> trace toggle handler (≤20 lines, reads/writes tsi_trace_open cookie)

Browser
  │
  ├── tap indicator name → JS click handler → toggles data-formula-open attr
  │                                         → CSS shows/hides .formula-row
  ├── tap "Show calculations" summary → <details> native toggle
  │                                   → JS toggle listener → writes tsi_trace_open cookie
  └── page load → JS reads tsi_trace_open → no action needed (server already set [open])
```

### Recommended Project Structure (no changes to layout — additive only)

```
dashboard.py
├── _TRACE_FORMULAS: dict[str, str]          # module-level constant (D-13)
├── _format_indicator_value(...)             # pure helper, math.isnan only
├── _render_trace_inputs(ohlc_window)        # Inputs panel
├── _render_trace_indicators(scalars)        # Indicators panel
├── _render_trace_vote(scalars)              # Vote panel
├── _render_trace_panels(sig_dict, open)     # orchestrator
└── _render_signal_card(...)                 # MODIFIED to wrap <details> + call orchestrator

tests/
├── test_dashboard.py                        # ADD TestTracePanels class
├── test_state_manager.py                    # ADD TestMigrateV4ToV5 class
├── test_main.py                             # ADD TestRunDailyCheckPersistsTracePayload class
└── fixtures/dashboard/sample_state_v5.json # NEW golden fixture
```

### Pattern 1: Outer `<details>` Disclosure (D-04)

**What:** A `<details>/<summary>` element wrapping all three trace panels for one instrument.
**When to use:** Default-collapsed at render time if instrument key absent from `tsi_trace_open` cookie.
**Key point:** `<summary>` is a natively interactive element — no extra `tabindex`, no `role`, no
`aria-expanded` management needed. The browser handles all of that automatically.

```python
# Source: CONTEXT.md D-04 + [VERIFIED: WebAIM disclosure docs]
def _render_trace_panels(sig_dict: dict, inst_key: str, inst_open: bool) -> str:
  open_attr = ' open' if inst_open else ''
  inst_esc = html.escape(inst_key, quote=True)
  inner = (
    _render_trace_inputs(sig_dict.get('ohlc_window', []))
    + _render_trace_indicators(sig_dict.get('indicator_scalars', {}))
    + _render_trace_vote(sig_dict.get('indicator_scalars', {}))
  )
  return (
    f'<details class="trace-disclosure" data-instrument="{inst_esc}"{open_attr}>\n'
    '  <summary class="trace-summary">Show calculations</summary>\n'
    + inner
    + '</details>\n'
  )
```

### Pattern 2: Indicator Name Tap-to-Toggle (D-03, with iOS Safari fix)

**What:** Clicking an indicator-name cell reveals/hides a formula row below it.
**Critical:** The `<span>` or `<td>` acting as the click target MUST have `cursor: pointer` in CSS, or
Mobile Safari will not fire the click event (see §Common Pitfalls: iOS Click Event Trap).

```python
# Source: CONTEXT.md D-03 + [VERIFIED: iOS Safari cursor:pointer requirement]
# In _INLINE_CSS:
# .trace-indicator-name { cursor: pointer; }  ← REQUIRED for Mobile Safari

# HTML pattern:
# <tr>
#   <td class="trace-indicator-name" data-formula-open="false">ATR(14)</td>
#   <td class="trace-value">0.012345</td>
# </tr>
# <tr class="formula-row" hidden>
#   <td colspan="2">ATR(14) = Wilder-smooth(TR, 14) — initial seed = SMA(TR, 14)</td>
# </tr>
```

```javascript
// Source: [ASSUMED] — vanilla JS pattern; no library
// Attach once per panel on DOMContentLoaded:
document.querySelectorAll('.trace-indicator-name').forEach(function(cell) {
  cell.addEventListener('click', function() {
    var open = this.getAttribute('data-formula-open') === 'true';
    var formulaRow = this.closest('tr').nextElementSibling;
    if (open) {
      this.setAttribute('data-formula-open', 'false');
      formulaRow.hidden = true;
    } else {
      this.setAttribute('data-formula-open', 'true');
      formulaRow.hidden = false;
    }
  });
});
```

### Pattern 3: Cookie Read/Write for Disclosure State (D-12)

**What:** JS writes `tsi_trace_open` cookie on `<details>` toggle; Python reads it at render time.
**Cookie attributes (D-12):** `Path=/; SameSite=Lax; Max-Age=7776000` (90 days). No `Secure`, no
`HttpOnly` (JS must write it). No `Domain` attribute (exact host only — consistent with `tsi_session`
pattern from Phase 16.1 D-12).

```javascript
// Source: [ASSUMED] — standard document.cookie pattern; no library
// On DOMContentLoaded, attach to each <details data-instrument>:
document.querySelectorAll('details[data-instrument]').forEach(function(el) {
  el.addEventListener('toggle', function() {
    var openInsts = Array.from(
      document.querySelectorAll('details[data-instrument][open]')
    ).map(function(d) { return d.getAttribute('data-instrument'); });
    var val = openInsts.join(',');
    var maxAge = 90 * 24 * 60 * 60;  // 90 days in seconds
    document.cookie = 'tsi_trace_open=' + val
      + '; Path=/; SameSite=Lax; Max-Age=' + maxAge;
  });
});
```

```python
# Source: [ASSUMED] — stdlib; confirmed pattern from Phase 16.1 CONTEXT
# In web/routes/dashboard.py::get_dashboard:
raw_cookie = request.cookies.get('tsi_trace_open', '')
trace_open = set(raw_cookie.split(',')) if raw_cookie else set()
# Pass trace_open into render_dashboard (new kwarg).

# In dashboard.py::_render_trace_panels:
inst_open = inst_key in trace_open  # -> decides <details open> vs <details>
```

### Pattern 4: Float Display — `_format_indicator_value` (D-05, D-06)

```python
# Source: CONTEXT.md D-05, D-06 — [VERIFIED: confirmed format spec behaviour]
import math

def _format_indicator_value(
  value: float,
  seed_required: int,
  bars_available: int,
) -> str:
  '''Pure helper. No I/O. Allowed import: math only.'''
  if math.isnan(value):
    if bars_available < seed_required:
      return f'n/a (need {seed_required} bars, have {bars_available})'
    return 'n/a (flat price)'
  return f'{value:.6f}'
```

**Trailing zeros:** `f'{value:.6f}'` always produces exactly 6 decimal places, including trailing zeros
(e.g., `1.000000`). This is intentional — column widths stay constant, hand-recalc alignment is clean.
Excel, when the operator copies the value and enters it into a cell formatted as "General", will strip
trailing zeros from the display but store the full precision — this is fine because the operator
computes with Excel's stored value, not the displayed string.

### Pattern 5: OHLC Grid Table Layout

**Industry standard for financial data tables:**
- Right-align all numeric cells (`text-align: right`)
- Use `font-variant-numeric: tabular-nums` so digits stack vertically
- Date column: left-align
- No alternating row stripes needed for 40-row scrollable panel (adds noise with no benefit on mobile)
- Column order: Date | Open | High | Low | Close (matches Bloomberg/IG/TradingView OHLC convention)

```css
/* Source: [VERIFIED: MDN font-variant-numeric + financial-grid industry standard] */
.trace-ohlc-table td.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, 'Courier New', monospace;  /* fallback for fonts without tnum */
}
.trace-ohlc-table td.date {
  text-align: left;
  color: var(--color-text-muted);
}
```

**Note on `tabular-nums` fallback:** The system font stack in dashboard.py may or may not support
`tnum` OpenType feature. Adding a monospace font fallback for the numeric cells ensures column
alignment even when `tabular-nums` has no effect on the selected font.

### Pattern 6: Vote Panel Badge Layout

```python
# Source: CONTEXT.md D-07 — [ASSUMED shape; CONTEXT provides the content layout]
# Badge CSS classes: .trace-badge.plus (green), .trace-badge.minus (red),
#                   .trace-badge.zero (grey), .trace-badge.pass (green), .trace-badge.fail (red)

def _render_vote_badge(name: str, value: float) -> str:
  if math.isnan(value):
    cls, sym = 'zero', '0'
  elif value > 0:
    cls, sym = 'plus', '+'
  elif value < 0:
    cls, sym = 'minus', '−'
  else:
    cls, sym = 'zero', '0'
  name_esc = html.escape(name, quote=True)
  val_str = html.escape(f'{value:+.6f}' if not math.isnan(value) else 'n/a', quote=True)
  return (
    f'<tr>'
    f'<td>{name_esc}</td>'
    f'<td><span class="trace-badge {cls}">{sym}</span></td>'
    f'<td class="num">{val_str}</td>'
    '</tr>\n'
  )
```

### Anti-Patterns to Avoid

- **Putting `aria-expanded` on the `<summary>` element**: Native `<details>/<summary>` manages state
  internally; adding `aria-expanded` creates a duplicate/conflicting signal to screen readers. Do not
  add it. `[VERIFIED: WebAIM disclosure docs]`
- **Adding `role="button"` to `<summary>`**: Strips nested heading semantics in Safari and breaks AT
  announcements. `[CITED: scottohara.me/blog/2022/09/12/details-summary.html]`
- **Attaching `click` handlers to `<div>` or `<span>` rows without `cursor: pointer`**: Silent
  no-op on Mobile Safari. Always pair a JS click listener with `cursor: pointer` CSS.
- **Writing the `tsi_trace_open` cookie with `HttpOnly`**: JS must read/write it. Never set
  `HttpOnly` on a UI-preference cookie that JS owns.
- **Using `localStorage` instead of the cookie**: D-04 locks cookie. `localStorage` doesn't survive
  Private Browsing reset and has different cross-tab semantics.
- **Using `f'{value:,.6f}'` (with thousands separator)**: For AUD/USD prices and indicator scalars
  (all < 1000), the comma separator is pure visual noise. Use `f'{value:.6f}'` only. `[ASSUMED: based
  on value-range knowledge — ATR ~0.0015, ADX 0-100, Mom ~0.01]`

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTML escaping for dynamic values | custom escape function | `html.escape(val, quote=True)` — already imported | stdlib, proven; hand-rolled escaping misses edge cases (e.g., attribute vs text context) |
| `<details>` accessibility | custom ARIA disclosure widget | native `<details>/<summary>` | browser handles expanded/collapsed state announcement natively; WCAG 2.1 AA compliant without extra JS |
| `<details>` polyfill | polyfill for old iOS | nothing — no polyfill needed | `<details>` supported in Safari iOS 6+ (2012); operator on iOS 17+ |
| Toggle state management | custom JS accordion | native `<details>` toggle event | zero-LOC; browser handles open/closed transitions, animation, and keyboard |
| Cookie parsing | custom `document.cookie` parser | direct string manipulation for single-key write/read | this cookie is a simple comma-separated list; library would be overkill |
| Float formatting | custom decimal formatter | `f'{value:.6f}'` | exact, predictable, Python spec-defined |
| NaN detection | `value != value` or string comparison | `math.isnan(value)` | correct for IEEE 754; `math` already used in signal_engine |
| Indicator formula rendering | MathJax / KaTeX | plain text in `_TRACE_FORMULAS` dict | D-13 lock; heavy deps; formula strings are presentation, not math |
| JS click-outside dismisser | custom overlay / modal | nothing needed — formula rows are inline, not overlays | no dismiss-on-outside-click needed for inline reveal |

**Key insight:** This phase's entire JS surface is ≤20 lines of vanilla ES5. Any impulse to add a library
is scope creep.

---

## Common Pitfalls

### Pitfall 1: Mobile Safari Click Events on Non-Interactive Elements

**What goes wrong:** The JS click handler on indicator-name cells (`<td class="trace-indicator-name">`)
does not fire on iPhone. The formula row never appears. No error in the console.
**Why it happens:** Mobile Safari only fires `click` events on elements that are either natively
interactive (buttons, links, inputs) OR that have `cursor: pointer` set in CSS. Bare `<td>` or
`<span>` elements are treated as non-interactive and swallow tap events silently.
`[CITED: https://www.shdon.com/blog/2013/06/07/why-your-click-events-don-t-work-on-mobile-safari]`
`[VERIFIED: WebKit documented behavior in search results 2024/2025]`
**How to avoid:** Add `.trace-indicator-name { cursor: pointer; }` to `_INLINE_CSS`. This is the
canonical fix — no JS changes needed.
**Warning signs:** Works on desktop Chrome, silent failure on iPhone. First sign: UAT step where
operator taps ATR(14) and nothing happens.

### Pitfall 2: `aria-expanded` Conflict with Native `<details>`

**What goes wrong:** Adding `aria-expanded="false"` to `<summary>` or the outer `<details>` creates
conflicting state signals — the browser reports its own open/closed state AND the hand-coded attribute
sends a second (possibly out-of-sync) signal.
**Why it happens:** CONTEXT D-03 mentions `data-formula-open` (for the per-indicator toggle), which
is a data attribute, not an ARIA attribute. The outer `<details>` uses no `aria-expanded` — native
semantics are sufficient.
**How to avoid:** Never add `aria-expanded` to `<summary>` or the outer `<details>`. Use it ONLY on
custom button-based disclosure widgets (not applicable here).
**Warning signs:** Screen reader announces "expanded" twice, or announces state before the toggle
completes.

### Pitfall 3: iOS VoiceOver Does Not Announce `<details>` State Changes

**What goes wrong:** Blind operator on iOS (not the current use case, but future-proofing) would find
that VoiceOver + Safari does not announce "expanded" / "collapsed" when the `<details>` toggles. This
is a **known WebKit limitation**, not something the implementation can fix without abandoning `<details>`
for a custom ARIA widget.
**Why it happens:** Documented by Scott O'Hara (2022): iOS VoiceOver with Safari exhibits "bugged
behavior or no role announced" for `<details>/<summary>`. The announced role and state are inconsistent.
`[CITED: https://www.scottohara.me/blog/2022/09/12/details-summary.html]`
**How to avoid:** For this phase: document as a known limitation in a code comment inside
`_render_trace_panels`. The operator is sighted; this limitation does not affect current UAT.
**Warning signs:** If accessibility is later required, replace `<details>` with a custom ARIA button
+ `aria-controls` disclosure widget.

### Pitfall 4: Cookie Namespace Collision (`tsi_trace_open` vs `tsi_session`)

**What goes wrong:** Web/routes/dashboard.py accidentally reads `tsi_trace_open` when it should read
`tsi_session`, or vice versa.
**Why it's not a real collision:** Cookies are identified by name (+ domain + path). `tsi_trace_open`
and `tsi_session` are different names. Both have `Path=/` and no explicit `Domain`. The browser sends
both on every request; the server reads each by its exact name. They coexist safely.
`[VERIFIED: MDN Set-Cookie header docs + search result confirming cookie-id is name/domain/path triple]`
**Actual risk (mitigated):** If a future developer adds a new cookie named `tsi_trace_open_spi200`
and another named `tsi_trace_open_audusd` instead of the D-12 comma-list design, the server
might receive both and need to disambiguate. The D-12 single-cookie design avoids this.
**How to avoid:** Use the exact name `tsi_trace_open` in the JS write and the Python read.
`grep -rn 'tsi_trace\|tsi_session\|tsi_trusted' dashboard.py web/` — each occurrence must read/write
the correct name.

### Pitfall 5: `tsi_trace_open` Cookie Written as HttpOnly

**What goes wrong:** If the Python route sets `tsi_trace_open` with `HttpOnly`, the JS toggle
listener can not update it — `document.cookie` reads return empty for HttpOnly cookies. The panel
state never persists across reloads.
**Why it happens:** Developer mirrors the `tsi_session` security attributes without checking whether
JS needs write access.
**How to avoid:** `tsi_trace_open` must NOT have `HttpOnly`. It is a pure UI preference cookie — no
secrets, no auth — JS owns it. The distinction is already documented in CONTEXT D-12.
**Warning signs:** Panel expands → reload → panel collapsed again despite cookie claim.

### Pitfall 6: `f'{value:.6f}'` Applied to NaN Without Guard

**What goes wrong:** `f'{float("nan"):.6f}'` raises `ValueError` in Python (or produces `nan` as a
string, depending on platform). Either way, the render fails or emits `nan` instead of the
operator-readable reason text.
**Why it happens:** NaN floats from `compute_indicators` flow through without a guard before the
format string.
**How to avoid:** `_format_indicator_value` checks `math.isnan(value)` BEFORE the f-string.
The helper is the single call site for all scalar display — do not bypass it by inline `f'{v:.6f}'`
anywhere in the trace helpers.
**Warning signs:** `nan` appearing in the rendered HTML instead of `n/a (...)`.

### Pitfall 7: Hex-Boundary Breach via "DRY" Formula Lookup

**What goes wrong:** A contributor adds `from signal_engine import ATR_PERIOD` inside `dashboard.py`
to keep the formula text DRY (avoiding the literal `14` in the formula string).
**Why it happens:** Tempting DRY refactor. But it violates the hex-lite boundary (dashboard.py must
not import pure-logic modules) and fails the AST guard test.
**How to avoid:** The period numbers appear once in `_TRACE_FORMULAS` as string literals. The
AST-guard test `TestDeterminism::test_forbidden_imports_absent` catches the import. Code-review
checklist: any `from signal_engine import` in `dashboard.py` is an automatic block.

### Pitfall 8: `<details>` toggle event listener attached before DOM ready

**What goes wrong:** The `<script>` block runs before `DOMContentLoaded`, so `querySelectorAll`
returns an empty NodeList. No click handlers bind. No toggle handlers bind.
**Why it happens:** Script placed in `<head>` without `defer`, or inline script placed before the
body content.
**How to avoid:** Wrap all JS in `document.addEventListener('DOMContentLoaded', function() { ... })`.
The existing dashboard.py `<script>` blocks for the equity chart already use `(function() { ... })()`
inside the body — follow the same pattern, or use `DOMContentLoaded` for the shared toggle handler
added to `<head>`.

### Pitfall 9: Excel Trailing-Zero Confusion for Operator Hand-Recalc

**What goes wrong:** Operator copies `0.012300` from the dashboard into Excel. Excel displays it as
`0.0123` (General format strips trailing zeros from display). Operator thinks the values differ.
**Why it's not a real problem:** Excel stores the full float64 precision. The display strips trailing
zeros as cosmetic formatting. The computed result using Excel's stored value will match our displayed
6-decimal value to 1e-6. Operator only needs to be told "Excel may display fewer decimals — the stored
value is identical".
**How to avoid:** Add a short note in the dashboard Indicators panel header or in the "Show calculations"
summary: "Values shown to 6 decimal places (Excel stores full precision)". Or just cover it in
operator documentation.

---

## Code Examples

### OHLC Table Row HTML

```python
# Source: CONTEXT.md D-02, D-09 + [VERIFIED: right-align/tabular-nums industry standard]
# Inside _render_trace_inputs(ohlc_window):
def _render_ohlc_row(index: int, row: dict) -> str:
  date_esc = html.escape(row.get('date', ''), quote=True)
  def fmt(v) -> str:
    return html.escape(f'{float(v):.6f}', quote=True) if v is not None else '—'
  return (
    f'<tr data-row-index="{index}">'
    f'<td class="date">{date_esc}</td>'
    f'<td class="num">{fmt(row.get("open"))}</td>'
    f'<td class="num">{fmt(row.get("high"))}</td>'
    f'<td class="num">{fmt(row.get("low"))}</td>'
    f'<td class="num">{fmt(row.get("close"))}</td>'
    '</tr>\n'
  )
```

### Indicator Table Row HTML

```python
# Source: CONTEXT.md D-02, D-05, D-06, D-13
_SEED_LENGTHS: dict[str, int] = {
  'tr': 1, 'atr': 14, 'plus_di': 20, 'minus_di': 20,
  'adx': 20, 'mom1': 2, 'mom3': 4, 'mom12': 13, 'rvol': 20,
}

def _render_indicator_row(key: str, value: float, bars_available: int) -> str:
  name = html.escape(key, quote=True)
  formula = html.escape(_TRACE_FORMULAS.get(key, ''), quote=True)
  val_str = html.escape(
    _format_indicator_value(value, _SEED_LENGTHS.get(key, 1), bars_available),
    quote=True,
  )
  return (
    f'<tr>'
    f'<td class="trace-indicator-name" data-formula-open="false" title="{formula}">{name}</td>'
    f'<td class="num">{val_str}</td>'
    '</tr>\n'
    f'<tr class="formula-row" hidden>'
    f'<td colspan="2">{formula}</td>'
    '</tr>\n'
  )
```

### CSS for Trace Panels (additions to `_INLINE_CSS`)

```css
/* Source: [VERIFIED: MDN tabular-nums + industry OHLC convention]
   + [VERIFIED: iOS Safari cursor:pointer fix] */
.trace-disclosure { margin-top: var(--space-3); }
.trace-summary { cursor: pointer; font-weight: 600; color: var(--color-text-muted); }
.trace-panel { margin-top: var(--space-2); overflow-x: auto; }
.trace-panel table { width: 100%; border-collapse: collapse; font-size: var(--fs-label); }
.trace-panel td { padding: 2px 6px; border-bottom: 1px solid var(--color-border); }
.trace-panel td.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, 'Courier New', monospace;
}
.trace-panel td.date { color: var(--color-text-muted); }
.trace-indicator-name { cursor: pointer; }  /* REQUIRED: Mobile Safari click fix */
.formula-row td { font-size: 0.8em; color: var(--color-text-muted); font-style: italic; padding-left: 12px; }
.trace-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-weight: 700; }
.trace-badge.plus  { background: #166534; color: #dcfce7; }  /* green — mirrors _COLOR_LONG */
.trace-badge.minus { background: #7f1d1d; color: #fee2e2; }  /* red — mirrors _COLOR_SHORT */
.trace-badge.zero  { background: #713f12; color: #fef9c3; }  /* grey-amber — mirrors _COLOR_FLAT */
.trace-badge.pass  { background: #166534; color: #dcfce7; }
.trace-badge.fail  { background: #7f1d1d; color: #fee2e2; }
```

### JS Toggle Handler Skeleton (≤20 lines, attaches on DOMContentLoaded)

```javascript
// Source: [ASSUMED] vanilla ES5 — no library; follows existing dashboard.py script pattern
document.addEventListener('DOMContentLoaded', function() {
  // Outer disclosure cookie persistence
  document.querySelectorAll('details[data-instrument]').forEach(function(el) {
    el.addEventListener('toggle', function() {
      var open = Array.from(document.querySelectorAll('details[data-instrument][open]'))
        .map(function(d) { return d.getAttribute('data-instrument'); }).join(',');
      document.cookie = 'tsi_trace_open=' + open + '; Path=/; SameSite=Lax; Max-Age=7776000';
    });
  });
  // Per-indicator formula reveal
  document.querySelectorAll('.trace-indicator-name').forEach(function(cell) {
    cell.addEventListener('click', function() {
      var isOpen = this.getAttribute('data-formula-open') === 'true';
      var next = this.closest('tr').nextElementSibling;
      if (next && next.classList.contains('formula-row')) {
        next.hidden = isOpen;
        this.setAttribute('data-formula-open', isOpen ? 'false' : 'true');
      }
    });
  });
});
```

**Line count:** 17 lines body, under D-03 ≤20 limit.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `cgi.escape()` for HTML escaping | `html.escape(val, quote=True)` | Python 3.2+ | `cgi.escape` deprecated in 3.2, removed in 3.8; `html.escape` is the only correct stdlib call |
| `font-family: monospace` for numeric alignment | `font-variant-numeric: tabular-nums` | CSS Fonts Level 3 (2018, widely available) | tabular-nums works across proportional fonts; monospace forces a different aesthetic |
| Polyfill for `<details>` | nothing — native support everywhere | Safari iOS 6 (2012) | no polyfill needed |

**Deprecated / outdated:**
- `cgi.escape`: removed from Python 3.8. `html.escape` is the replacement. `[ASSUMED]`
- `MathJax` / `KaTeX` for formula display: explicitly rejected in CONTEXT D-13. Not applicable.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `f'{float("nan"):.6f}'` raises `ValueError` or produces literal `nan` | §Pitfall 6 | If it silently produces `nan`, the guard is still correct but the pitfall description overstates the risk |
| A2 | AUD/USD indicator scalar values are all < 1000 (ATR ~0.001, ADX 0-100, Mom ~0.01) | §Anti-Patterns | If a value ever exceeds 999, `.6f` would produce `1234.567890` without a thousands separator — still unambiguous |
| A3 | Excel "General" format strips trailing zeros from display but stores full float64 precision | §Pitfall 9 + §Float Display | If operator uses Excel "Text" cell format (unlikely), the stored precision matches the pasted string exactly — no risk |
| A4 | `document.cookie` write with `Path=/; SameSite=Lax; Max-Age=7776000` (90 days) works correctly on Mobile Safari for a non-Secure cookie on HTTPS | §Pattern 3 | If Safari on HTTPS requires `Secure` for `SameSite=Lax` cookies (it does NOT — `Secure` is only required for `SameSite=None`) the cookie silently drops. Mitigation: add `Secure` to JS cookie write (no downside since the production server is HTTPS-only) |
| A5 | `_SEED_LENGTHS` dict values (14 for ATR, 20 for ADX/+DI/-DI/RVol, etc.) match the engine's actual seed windows | §Code Examples | If the engine's seed lengths differ, the NaN reason text "need N bars, have M" would show wrong N. Verify against `signal_engine.py` constants before executor ships. |

**A4 recommendation:** Add `Secure` to the JS cookie write for defence in depth. The operator's
production URL is HTTPS. `document.cookie` with `Secure` is silently ignored on HTTP (test env) but
applied on HTTPS (production) — the cookie still works in both environments.

---

## Open Questions

1. **`render_dashboard` signature change**
   - What we know: `tsi_trace_open` cookie must be passed in as a `set` so the render is testable
     without a live HTTP request.
   - What's unclear: Does the planner add `trace_open: set[str] | None = None` to `render_dashboard`,
     or does `_render_signal_cards` receive it separately?
   - Recommendation: Add `trace_open: set[str] | None = None` to `render_dashboard`. Caller (`web/routes/dashboard.py`)
     computes it from the cookie and passes it down. `main.py` daily-loop path passes `None` → all
     panels default-collapsed. This mirrors the `is_cookie_session` precedent exactly.

2. **`render_dashboard` already writes to disk — does the web route bypass the disk write?**
   - What we know: The current `web/routes/dashboard.py::get_dashboard` reads `dashboard.html` off
     disk after `render_dashboard` has written it. Phase 17 does not change this path.
   - What's unclear: The `trace_open` cookie controls `<details open>` in the on-disk HTML. But the
     on-disk HTML is written once (at daily run time) with `trace_open=None` (all collapsed). The web
     route re-renders on the fly only for placeholder substitution. This means the `<details open>`
     state from the cookie is injected at request time, not at write time.
   - Recommendation: The web route should inject `open` via a `{{TRACE_OPEN_SPI200}}`/`{{TRACE_OPEN_AUDUSD}}`
     placeholder pattern (mirroring `{{SIGNOUT_BUTTON}}`), OR call `render_dashboard` at request time
     (not the current pattern). **The planner must resolve this architectural detail.** The on-disk
     file approach (current pattern) is incompatible with per-request cookie-driven `<details open>`
     state unless placeholder substitution is extended.

3. **`_SEED_LENGTHS` constant placement**
   - What we know: The planner needs to verify the seed lengths (ATR=14, ADX/+DI/-DI=20, etc.)
     against the actual `signal_engine.py` constants.
   - Recommendation: Executor step: `grep -n 'ATR_PERIOD\|ADX_PERIOD\|RVOL_PERIOD\|MOM_' signal_engine.py`
     before hardcoding in `_SEED_LENGTHS`. If they match, inline as a module-level constant in
     `dashboard.py` (not imported from `signal_engine` — D-10 forbids this).

---

## Environment Availability

Step 2.6 SKIPPED — this phase makes no calls to external services, CLI tools, or databases beyond
the existing Python 3.11 + pytest stack already confirmed on the DO droplet.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (version pinned in requirements.txt) |
| Config file | `pytest.ini` (or `setup.cfg [tool:pytest]`) |
| Quick run command | `pytest tests/test_dashboard.py::TestTracePanels -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRACE-01 | OHLC panel renders 40 rows, data-row-index 0..39, date/OHLC cells | unit | `pytest tests/test_dashboard.py::TestTracePanels::test_inputs_panel_renders_40_rows -x` | ❌ Wave 0 |
| TRACE-01 | Empty ohlc_window renders "Awaiting first daily run" | unit | `pytest tests/test_dashboard.py::TestTracePanels::test_inputs_panel_empty_state -x` | ❌ Wave 0 |
| TRACE-02 | Indicators panel renders all 9 formula strings from `_TRACE_FORMULAS` | unit | `pytest tests/test_dashboard.py::TestTracePanels::test_all_formula_strings_present -x` | ❌ Wave 0 |
| TRACE-02 | `_format_indicator_value` — finite value → 6-decimal string | unit | `pytest tests/test_dashboard.py::TestFormatIndicatorValue -x` | ❌ Wave 0 |
| TRACE-02 | `_format_indicator_value` — NaN seed-short → reason text | unit | `pytest tests/test_dashboard.py::TestFormatIndicatorValue -x` | ❌ Wave 0 |
| TRACE-02 | `_format_indicator_value` — NaN flat-price → reason text | unit | `pytest tests/test_dashboard.py::TestFormatIndicatorValue -x` | ❌ Wave 0 |
| TRACE-03 | Vote panel renders badge classes `.plus/.minus/.zero` | unit | `pytest tests/test_dashboard.py::TestTracePanels::test_vote_badges -x` | ❌ Wave 0 |
| TRACE-03 | Vote panel renders ADX gate badge `.pass/.fail` | unit | `pytest tests/test_dashboard.py::TestTracePanels::test_adx_gate_badge -x` | ❌ Wave 0 |
| TRACE-04 | render_dashboard with empty ohlc_window: renders without error, no state mutation | unit | `pytest tests/test_dashboard.py::TestTracePanels::test_render_does_not_mutate_state -x` | ❌ Wave 0 |
| TRACE-04 | cookie-driven `<details open>` renders correctly | unit | `pytest tests/test_dashboard.py::TestTracePanels::test_details_open_from_cookie -x` | ❌ Wave 0 |
| TRACE-05 | AST guard: `test_forbidden_imports_absent` stays green | unit | `pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -x` | ✅ |
| — | Migration v4→v5: backfill, idempotent, preserves fields, skips int | unit | `pytest tests/test_state_manager.py::TestMigrateV4ToV5 -x` | ❌ Wave 0 |
| — | main.py writes 40-entry ohlc_window + 9-key indicator_scalars | unit | `pytest tests/test_main.py::TestRunDailyCheckPersistsTracePayload -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_dashboard.py -x && pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_dashboard.py::TestTracePanels` — covers TRACE-01..04
- [ ] `tests/test_dashboard.py::TestFormatIndicatorValue` — covers `_format_indicator_value` pure unit
- [ ] `tests/fixtures/dashboard/sample_state_v5.json` — golden state fixture with populated `ohlc_window` + `indicator_scalars`
- [ ] `tests/test_state_manager.py::TestMigrateV4ToV5` — covers schema migration
- [ ] `tests/test_main.py::TestRunDailyCheckPersistsTracePayload` — covers write-site extension

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Phase 17 adds no new auth surfaces |
| V3 Session Management | no | `tsi_trace_open` carries no session data |
| V4 Access Control | no | Panels are read-only; operator-only dashboard |
| V5 Input Validation | yes (limited) | Cookie value `tsi_trace_open` must be sanitised before use: split on comma, filter to known instrument keys (`SPI200`, `AUDUSD`) only. Never use cookie value in SQL, command, or URL context. |
| V6 Cryptography | no | Cookie unsigned by design (D-12) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cookie injection via malformed `tsi_trace_open` | Tampering | Allowlist filter: `{k for k in raw.split(',') if k in {'SPI200', 'AUDUSD'}}` |
| XSS via indicator scalar display | Tampering | `html.escape(str(value), quote=True)` on every dynamic value; existing `test_signal_as_of_xss` pattern applies |
| JSON injection in `ohlc_window` date strings | Tampering | `html.escape(row['date'], quote=True)` — dates are server-written, not user-input, but escape anyway for defence in depth |

**Cookie value allowlist (REQUIRED — not in CONTEXT.md, surfaces here):**

```python
# In web/routes/dashboard.py before passing trace_open to render_dashboard:
_VALID_INSTRUMENT_KEYS = frozenset({'SPI200', 'AUDUSD'})
raw = request.cookies.get('tsi_trace_open', '')
trace_open = frozenset(k for k in raw.split(',') if k in _VALID_INSTRUMENT_KEYS)
```

This is not in CONTEXT.md D-12 explicitly. The planner should include it as a hardened read step.

---

## Sources

### Primary (HIGH confidence)
- `[VERIFIED: dashboard.py grep]` — existing `html.escape`, `_INLINE_CSS`, `render_dashboard`, `_render_header`, `_render_signal_cards` shape
- `[VERIFIED: WebAIM Disclosures and Accordions]` — native `<details>/<summary>` WCAG 2.1 AA compliance, no manual `aria-expanded` needed — https://webaim.org/techniques/disclosures/
- `[CITED: MDN HTMLElement toggle_event]` — Baseline Widely Available since January 2020; no polyfill needed — https://developer.mozilla.org/en-US/docs/Web/API/HTMLElement/toggle_event
- `[CITED: caniuse.com/details]` — Safari iOS 6+ for `<details>` element
- `[CITED: scottohara.me/blog/2022/09/12/details-summary.html]` — iOS VoiceOver bug with `<details>` state announcements
- `[VERIFIED: 17-CONTEXT.md]` — all locked D-01..D-13 decisions, including cookie attributes, formula text, schema shape

### Secondary (MEDIUM confidence)
- `[CITED: WebSearch + mobile-safari-click-events sources]` — `cursor: pointer` required for non-interactive element click events on Mobile Safari; multiple corroborating sources
- `[CITED: MDN font-variant-numeric]` — tabular-nums CSS for OHLC grid alignment
- `[CITED: MDN Set-Cookie]` — cookie identity is name + domain + path triple; `tsi_trace_open` vs `tsi_session` no collision

### Tertiary (LOW confidence — flagged as ASSUMED in Assumptions Log)
- Excel General format trailing-zero stripping (A3) — Microsoft docs incomplete; based on common knowledge
- `_SEED_LENGTHS` values matching engine constants (A5) — executor must verify against `signal_engine.py`
- `f'{nan:.6f}'` behaviour (A1) — assumed; executor should `python3 -c "print(f'{float(\"nan\"):.6f}')"` to confirm

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new deps; all stdlib/native
- Architecture: HIGH — mirrors Phase 22 and Phase 16.1 established patterns exactly
- Pitfalls: HIGH for iOS Safari/cookie issues (verified sources); MEDIUM for Excel float display (partially ASSUMED)
- Security: MEDIUM — cookie allowlist finding is new (not in CONTEXT.md); all other ASVS items are LOW-risk

**Research date:** 2026-04-30
**Valid until:** 2026-05-31 (stable APIs; iOS Safari browser-compat stable)
