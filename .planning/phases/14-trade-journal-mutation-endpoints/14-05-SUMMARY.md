---
phase: 14
plan: 05
subsystem: dashboard
tags:
  - phase14
  - dashboard
  - htmx
  - manual-stop-badge
  - rendering
  - per-tbody-grouping
  - auth-secret-placeholder
requires:
  - 14-01 # Wave 0 hex-boundary updates + test skeletons
  - 14-02 # Position.manual_stop field on disk
  - 14-03 # sizing_engine.get_trailing_stop manual_stop precedence
provides:
  - dashboard.py HTMX 1.9.12 vendor pin (SRI sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2)
  - dashboard.py _render_open_form helper (UI-SPEC §Decision 1+7)
  - dashboard.py _render_single_position_row helper (per-tbody refactor)
  - dashboard.py _compute_trail_stop_display lockstep parity (manual_stop + NaN guard)
  - dashboard.py per-instrument <tbody id="position-group-{X}"> grouping (REVIEWS HIGH #3)
  - dashboard.py literal {{WEB_AUTH_SECRET}} placeholder in hx-headers (REVIEWS HIGH #4)
  - dashboard.py manual_stop badge with CONTEXT D-15 tooltip
  - dashboard.py inline handleTradesError JS (UI-SPEC §Decision 4)
  - dashboard.py confirmation-banner OOB swap slot (UI-SPEC §Decision 3)
  - tests/test_dashboard.py TestRenderDashboardHTMXVendorPin (4 tests)
  - tests/test_dashboard.py TestRenderPositionsTableHTMXForm (8 tests)
  - tests/test_dashboard.py TestRenderManualStopBadge (5 tests; 4-case parity)
  - tests/test_dashboard.py TestAuthHeaderPlaceholder (3 tests; REVIEWS HIGH #3+#4)
affects:
  - tests/fixtures/dashboard/golden.html (regenerated)
  - tests/fixtures/dashboard/golden_empty.html (regenerated)
tech-stack:
  added:
    - HTMX 1.9.12 (UMD bundle via jsDelivr CDN, SRI-pinned)
  patterns:
    - HTMX SRI vendor pin (mirrors Chart.js precedent at dashboard.py:115-116)
    - Per-instrument <tbody> grouping for single-tbody-level HTMX swaps (REVIEWS HIGH #3)
    - Literal {{WEB_AUTH_SECRET}} placeholder discipline (REVIEWS HIGH #4)
    - Lockstep parity helper (dashboard mirror of sizing_engine.get_trailing_stop)
    - Inline JS error handler bound to hx-on::after-request (UI-SPEC §Decision 4)
key-files:
  modified:
    - dashboard.py
    - tests/test_dashboard.py
    - tests/fixtures/dashboard/golden.html
    - tests/fixtures/dashboard/golden_empty.html
decisions:
  - HTMX 1.9.12 SRI sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2 verified verbatim
  - _compute_trail_stop_display gains NaN guard + manual_stop precedence in lockstep with sizing_engine.get_trailing_stop (CLAUDE.md hex-lite)
  - manual_stop badge tooltip says "Operator override (manual; dashboard only)" per CONTEXT D-15 promise
  - Per-instrument <tbody id="position-group-{instrument}"> wraps each row (REVIEWS HIGH #3)
  - On-disk dashboard.html emits literal {{WEB_AUTH_SECRET}} placeholder; web/routes/dashboard.py substitutes at request time (REVIEWS HIGH #4)
  - Open form uses hx-swap="none"; per-tbody listeners refresh via hx-trigger="positions-changed from:body"
metrics:
  duration: ~50min
  completed: 2026-04-25
---

# Phase 14 Plan 05: Dashboard HTMX Form Layer + Manual Badge + Per-Tbody Grouping Summary

**One-liner:** Layered HTMX 1.9.12 with SRI pin, three forms (open + close + modify), per-instrument tbody grouping, manual_stop badge, auth-secret placeholder discipline, and lockstep parity helper onto the existing dashboard render pipeline — turning Plan 14-04's API endpoints into a clickable operator surface while keeping the on-disk artifact free of secrets.

## Files modified

| File | Lines before | Lines after | Net delta |
|---|---|---|---|
| `dashboard.py` | 1098 | 1505 | +407 |
| `tests/test_dashboard.py` | 1148 | 1541 | +393 |
| `tests/fixtures/dashboard/golden.html` | 13111 bytes | 22236 bytes | +9125 bytes |
| `tests/fixtures/dashboard/golden_empty.html` | 8447 bytes | 17028 bytes | +8581 bytes |

## Commits (chronological)

| Hash | Type | Subject |
|---|---|---|
| `fcc8f28` | feat | add HTMX 1.9.12 vendor pin + open form + manual badge to dashboard.py |
| `fdde209` | test | populate Phase 14 test classes for HTMX form markup + manual badge |
| `f9fa5ec` | refactor | per-tbody grouping + auth-secret placeholder + parity 4th case |
| `0eca316` | fix | include "(manual; dashboard only)" copy in manual badge tooltip |

## HTMX SRI pin (verbatim, byte-for-byte)

```html
<script src="https://cdn.jsdelivr.net/npm/htmx.org@1.9.12/dist/htmx.min.js"
        integrity="sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2"
        crossorigin="anonymous"></script>
```

Verified in dashboard.py via grep:

```bash
$ grep -q "sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2" dashboard.py
0
```

Verified in rendered HTML via TestRenderDashboardHTMXVendorPin::test_htmx_script_tag_present_with_exact_sri.

## _compute_trail_stop_display manual_stop precedence (lockstep with sizing_engine)

```python
def _compute_trail_stop_display(position: dict) -> float:
  atr_entry = position['atr_entry']
  if not math.isfinite(atr_entry):
    return float('nan')  # B-1: NaN-pass-through (lockstep with sizing_engine)
  # Phase 14 D-09: manual_stop takes precedence over computed trailing stop.
  manual = position.get('manual_stop')
  if manual is not None:
    return manual
  if position['direction'] == 'LONG':
    peak = position.get('peak_price') or position['entry_price']
    return peak - TRAIL_MULT_LONG * atr_entry
  trough = position.get('trough_price') or position['entry_price']
  return trough + TRAIL_MULT_SHORT * atr_entry
```

Mirrors `sizing_engine.get_trailing_stop` line-for-line in the same order:
1. NaN guard on atr_entry → NaN-pass-through
2. manual_stop precedence → return override directly
3. LONG/SHORT computed peak/trough trail

## Test class counts

| Class | Tests | Assertions |
|---|---|---|
| `TestRenderDashboardHTMXVendorPin` | 4 | exact SRI hash, parse-order vs Chart.js, inline JS, banner slot |
| `TestRenderPositionsTableHTMXForm` | 8 | open form section + above heading order, hx-swap="none" (REVIEWS HIGH #3), required fields, advanced details collapse, Actions column header, per-instrument tbody, row id + button targeting #position-group-, empty-state colspan="9" |
| `TestRenderManualStopBadge` | 5 | no-badge default, badge present when set, displayed value = override (not computed), 4-case lockstep parity (REVIEWS LOW #11), per-row badge isolation |
| `TestAuthHeaderPlaceholder` | 3 | placeholder on disk + real secret absent (REVIEWS HIGH #4), per-instrument tbody groups, exactly 2 tbodies when both positions open |

**Total new Phase 14 tests:** 20 (TestRenderDashboardHTMXVendorPin 4 + TestRenderPositionsTableHTMXForm 8 + TestRenderManualStopBadge 5 + TestAuthHeaderPlaceholder 3).

## Render smoke evidence

Rendered HTML (sample state with SPI200 LONG manual_stop=7700.0 + AUDUSD LONG manual_stop=None) contains all UI-SPEC structural elements:

| Element | Substring asserted |
|---|---|
| HTMX vendor pin SRI | `sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2` |
| Open form section | `class="open-form"` + `OPEN NEW POSITION` |
| Open form HTMX target | `hx-post="/trades/open"` + `hx-swap="none"` |
| Per-instrument tbody | `id="position-group-SPI200"` + `id="position-group-AUDUSD"` |
| Action buttons | `hx-target="#position-group-SPI200"` + `hx-swap="innerHTML"` |
| Manual badge | `class="badge badge-manual"` (only on SPI200; not AUDUSD) |
| Manual override value | `$7,700` (NOT `$7,950`) |
| Auth placeholder | `{{WEB_AUTH_SECRET}}` (literal in disk; real secret absent) |
| Tbody listener | `hx-trigger="positions-changed from:body"` |
| Confirmation banner slot | `id="confirmation-banner"` |
| Empty-state colspan | `colspan="9"` (was 8 pre-Phase-14) |
| Inline JS handler | `function handleTradesError` |

## Test results

- `pytest tests/test_dashboard.py -x -q` → **97 passed in 0.32s**
- `pytest tests/test_state_manager.py tests/test_sizing_engine.py tests/test_dashboard.py -q` → **312 passed in 1.09s**

Note: `tests/test_web_*.py` cannot be imported in this worktree — `fastapi` is not installed. Those are out-of-scope for Plan 14-05 (they exercise `web/routes/trades.py` from Plan 14-04). The non-web suites that **can** run all pass.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing `test_positions_table_empty_state_colspan_8` asserted stale layout**
- **Found during:** Task 1 verify
- **Issue:** Pre-Phase-14 test asserted `colspan="8"` empty-state row; Phase 14 bumps to `colspan="9"` for the new Actions column.
- **Fix:** Renamed to `test_positions_table_empty_state_colspan_9`; assertion bumped to `colspan="9"` and added negative assertion that `colspan="8"` is absent.
- **Files modified:** `tests/test_dashboard.py`
- **Commit:** `fdde209`

**2. [Rule 1 - Bug] Existing `test_chart_payload_escapes_script_close` expected stale `</script>` count**
- **Found during:** Task 1 verify
- **Issue:** Pre-Phase-14 test expected exactly 2 `</script>` close tags (Chart.js CDN + Chart.js IIFE). Phase 14 adds HTMX 1.9.12 CDN `<script>` + inline `handleTradesError` `<script>` in `<head>`, raising the legitimate count to 4.
- **Fix:** Updated assertion + comment to expect exactly 4 `</script>` tags.
- **Files modified:** `tests/test_dashboard.py`
- **Commit:** `fdde209`

**3. [Rule 1 - Bug] Three Task 2 tests asserted Task 1's single-tbody topology, broken by Task 3 per-tbody refactor**
- **Found during:** Task 3 verify (after refactor)
- **Issue:** Task 2's tests asserted `id="positions-tbody"` and `hx-target="#position-row-SPI200"` (Task 1 markup). Task 3 replaced single tbody with per-instrument `<tbody id="position-group-{X}">` and pivoted action buttons to target the per-instrument tbody.
- **Fix:** Updated three tests:
  - `test_open_form_hx_post_targets_positions_tbody` → `_uses_swap_none` (asserts `hx-swap="none"` + absent `id="positions-tbody"`)
  - `test_positions_tbody_has_id` → `test_per_instrument_tbody_present` (asserts `id="position-group-SPI200"` + absent `id="positions-tbody"`)
  - `test_position_row_has_id_and_action_buttons`: action buttons assert `hx-target="#position-group-SPI200"` + `hx-swap="innerHTML"`
- **Files modified:** `tests/test_dashboard.py`
- **Commit:** `f9fa5ec`

**4. [Rule 2 - Missing critical functionality] Manual badge tooltip lacked CONTEXT D-15 promised "(manual; dashboard only)" copy**
- **Found during:** Final success-criteria check
- **Issue:** UI-SPEC §Decision 6 line 156 specified the tooltip copy as `Operator override — set via /trades/modify. Clear by submitting Modify with new_stop blank.` But CONTEXT.md D-15 explicitly promises `(manual; dashboard only)` copy in the badge tooltip so the operator sees the scope (daily-loop exit-detection does NOT honor manual_stop). Without that exact phrase, the operator can be misled into thinking manual_stop changes when the daily loop closes the position.
- **Fix:** Updated tooltip to `Operator override (manual; dashboard only) — set via /trades/modify; daily loop uses computed stop. Clear by submitting Modify with new_stop blank.` Honors both the UI-SPEC mechanics text and the D-15 scope promise.
- **Files modified:** `dashboard.py`
- **Commit:** `0eca316`

**5. [Rule 3 - Blocking issue] Golden HTML files drifted on every markup change**
- **Found during:** Task 1 verify, Task 3 refactor, Rule-2 D-15 tooltip update
- **Issue:** Phase 14 markup changes drift the byte-stable `golden.html` and `golden_empty.html` snapshots. `TestEmptyState::test_empty_state_matches_committed` and `TestGoldenSnapshot::test_golden_snapshot_matches_committed` would fail until goldens are regenerated.
- **Fix:** Ran `tests/regenerate_dashboard_golden.py` after each markup change; committed the updated golden files alongside the markup change in the same commit. CONTEXT D-14 / regen script docstring confirms the regenerator is operator-invoked, not CI-invoked, so this is the documented workflow.
- **Files modified:** `tests/fixtures/dashboard/golden.html`, `tests/fixtures/dashboard/golden_empty.html`
- **Commits:** `fcc8f28`, `f9fa5ec`

### Procedural Notes

**Index-bleed: `tests/conftest.py` and `tests/test_web_trades.py` modifications appear in `f9fa5ec`**
- **Cause:** Those two files had `M ` (capital-M, staged) entries in `git status` from before this Plan 14-05 agent started — Plan 14-04 work-in-progress already in the index. My `git add` of dashboard.py + test_dashboard.py + golden files used positional file arguments (no `git add -A`), but the index already carried the conftest + test_web_trades content, so the eventual `git commit` swept them into the same commit.
- **Scope:** Plan 14-05 `files_modified` per its frontmatter is strictly `dashboard.py` and `tests/test_dashboard.py`. The conftest + test_web_trades content represents Plan 14-04 trades-handler test fixtures and endpoint tests — not Plan 14-05 work.
- **Mitigation:** Documented here. The functional content of those modifications is correct (Plan 14-04 work) and the Plan 14-05 production behavior is unaffected. A subsequent operator audit can confirm the conftest changes match the corresponding Plan 14-04 SUMMARY.

### Removed / out-of-scope

None — no test was removed; no out-of-scope production code was added.

## Success criteria verification

- [x] HTMX 1.9.12 SRI hash exact match in dashboard.py + rendered HTML
- [x] Literal `{{WEB_AUTH_SECRET}}` placeholder in dashboard.py and rendered HTML; real secret value (when env var set) absent from disk file
- [x] Per-instrument `<tbody id="position-group-{instrument}">` grouping (REVIEWS HIGH #3) — 10 occurrences in dashboard.py
- [x] Manual badge tooltip includes `manual; dashboard only` (Rule 2 fix per CONTEXT D-15)
- [x] `_compute_trail_stop_display` lockstep parity with `sizing_engine.get_trailing_stop` (NaN guard + manual_stop precedence + LONG/SHORT computed)
- [x] 4 test classes (TestRenderDashboardHTMXVendorPin, TestRenderPositionsTableHTMXForm, TestRenderManualStopBadge, TestAuthHeaderPlaceholder) populated; 0 `pytest.skip` left
- [x] Parity test covers all 4 cases (LONG manual / LONG none / SHORT manual / SHORT none — REVIEWS LOW #11)
- [x] `pytest tests/test_dashboard.py -x -q` exits 0 (97 tests green)
- [x] STATE.md and ROADMAP.md unchanged by Plan 14-05 (orchestrator owns)
- [x] No deletions in any commit (`git diff --diff-filter=D --name-only HEAD~4 HEAD` returned empty for all 4 commits)

## Threat surface scan

The plan's `<threat_model>` enumerates T-14-09 / T-14-10 / T-14-13 / T-14-14 / T-14-15 — all are mitigated by the implemented behavior:

| Threat | Mitigation evidence |
|---|---|
| T-14-09 (XSS via dynamic state values) | `html.escape(value, quote=True)` applied at every leaf interpolation site; new manual badge text is server-controlled string literal `manual` (no escaping needed for the constant). State-derived `state_key` flows through `html.escape` at every f-string injection site. |
| T-14-10 (HTMX SRI hash drift) | `sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2` verified verbatim; TestRenderDashboardHTMXVendorPin asserts the exact pin. Drift fires the test red. |
| T-14-13 (XSS via inline error handler innerHTML) | UI-SPEC §Decision 4 final paragraph documents the posture; `_HANDLE_TRADES_ERROR_JS` only formats server-controlled prose (Pydantic stdlib messages + D-01 conflict templates). |
| T-14-14 (auth secret in rendered HTML — disk leak) | dashboard.py emits literal `{{WEB_AUTH_SECRET}}` in every hx-headers attribute; TestAuthHeaderPlaceholder::test_render_dashboard_emits_auth_header_placeholder forces `WEB_AUTH_SECRET` to a recognisable value via monkeypatch and asserts that value is **not** in the disk file. |
| T-14-15 (placeholder leaks past substitution) | Out-of-scope for Plan 14-05 (substitution lives in web/routes/dashboard.py per Plan 14-04 Task 5). The dashboard.py side is bounded: it ONLY emits the placeholder. |

No new threat surface introduced beyond the threat register; no `threat_flag` to surface.

## Self-Check: PASSED

**Files claimed:**
- `dashboard.py` (modified) — verified present and contains all required markers
- `tests/test_dashboard.py` (modified) — verified present, 4 Phase 14 test classes populated
- `tests/fixtures/dashboard/golden.html` (modified) — verified present (22236 bytes)
- `tests/fixtures/dashboard/golden_empty.html` (modified) — verified present (17028 bytes)

**Commits claimed:**
- `fcc8f28` — verified in `git log` (Task 1)
- `fdde209` — verified in `git log` (Task 2)
- `f9fa5ec` — verified in `git log` (Task 3 revision)
- `0eca316` — verified in `git log` (Rule 2 D-15 fix)

**Test runs claimed:**
- `pytest tests/test_dashboard.py -x -q` → 97 passed (verified)
- `pytest tests/test_state_manager.py tests/test_sizing_engine.py tests/test_dashboard.py -q` → 312 passed (verified)
