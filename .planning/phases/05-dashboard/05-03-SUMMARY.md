---
phase: 05-dashboard
plan: 03
subsystem: dashboard
tags: [dashboard, chartjs, atomic-write, orchestrator-integration, phase-gate]
dependency_graph:
  requires:
    - 05-01  # Wave 0 scaffolds (palette, SRI, _INLINE_CSS :root, test fixtures, regenerator, B-1 retrofit)
    - 05-02  # Wave 1 per-block renderers (header, signal_cards, positions, trades, key_stats, footer, formatters, stats math)
  provides:
    - DASH-01  # Single-file, inline CSS
    - DASH-02  # Chart.js 4.4.6 SRI
    - DASH-04  # Equity curve from equity_history
    - DASH-09  # Visual theme palette
    - D-02     # Block rendering order
    - D-03     # Atomic write dashboard.html
    - D-06     # Orchestrator integration (never-crash)
    - D-11     # Chart.js config (category axis, maintainAspectRatio=false)
    - D-12     # SRI substring match
    - D-13     # Empty-state placeholder
    - D-14     # Golden HTML byte-stability smoke test
    - D-17     # Atomic-write ordering (Phase 3 mirror)
  affects:
    - main.py                    # D-06 integration point
    - dashboard.py               # All 3 Wave 2 stubs filled + _atomic_write_html added
    - tests/test_dashboard.py    # 15 new Wave 2 tests + strengthened </script> escape test
    - tests/test_main.py         # 4 new TestOrchestrator tests
    - tests/fixtures/dashboard/  # golden.html + golden_empty.html regenerated (was 0 bytes)
tech-stack:
  added: []                      # No new pip dependencies
  patterns:
    - "Chart.js inline <script> IIFE with SRI-locked CDN <script src> in <head>"
    - "JSON-in-JS injection defence via json.dumps + .replace('</', '<\\/') (Pitfall 1)"
    - "json.dumps(sort_keys=True, allow_nan=False) for byte-stability + fail-loud NaN"
    - "Atomic HTML write mirror of state_manager._atomic_write (tempfile + fsync + replace + parent-dir fsync)"
    - "D-06 never-crash wrapper: `import dashboard` INSIDE try/except body (C-2 reviews import-time isolation)"
    - "--test structural read-only preserved (C-3 reviews Option A) — dashboard renders ONLY on non-test path"
key-files:
  created:
    - ""                         # No new source files; regenerated 2 golden fixtures
  modified:
    - dashboard.py:143-357       # _INLINE_CSS expanded (full ~200-line stylesheet; was :root only)
    - dashboard.py:611-628       # _render_signal_cards: D-08 int-shape branch (Rule 1 auto-fix)
    - dashboard.py:876-953       # _render_equity_chart_container (Chart.js IIFE, JSON payload defence)
    - dashboard.py:956-984       # _render_html_shell (DOCTYPE + head + Chart.js SRI + body wrap)
    - dashboard.py:987-1035      # _atomic_write_html (state_manager._atomic_write mirror; newline='\n')
    - dashboard.py:1038-1069     # render_dashboard public API (now=None → PERTH.localize(datetime.now()))
    - dashboard.py:1072-1078     # if __name__ == '__main__' CLI entrypoint (C-6 reviews)
    - tests/test_dashboard.py    # +15 tests (9 TestRenderBlocks + 1 TestEmptyState + 1 TestGoldenSnapshot + 3 TestAtomicWrite)
    - tests/fixtures/dashboard/golden.html        # 0 → 13,111 bytes
    - tests/fixtures/dashboard/golden_empty.html  # 0 → 8,447 bytes
    - main.py:37                 # `from pathlib import Path` added
    - main.py:51-58              # Explanatory comment re: dashboard import location (C-2)
    - main.py:94-112             # `_render_dashboard_never_crash` helper definition
    - main.py:601-606            # Render call site (non-test path only, after save_state)
    - tests/test_main.py         # +4 TestOrchestrator tests (render, runtime-fail, import-fail, --test mtime)
decisions:
  - "[Rule 1 auto-fix] </script> count assertion: plan said `count == 1`; correct value is `count == 2` (CDN <script src=...></script> in head + IIFE close in body). Injection leak signal: count >= 3."
  - "[Rule 1 auto-fix] _render_signal_cards AttributeError on int-shape signals: added isinstance(sig_entry, int) branch to handle the Phase 3 reset_state() int shape. Renderer now supports both Phase 3 int shape and Phase 4 dict shape (D-08 upgrade branch pattern)."
  - "CSS line-length compliance: broke 5 over-100-char CSS/JS lines across _INLINE_CSS and _render_equity_chart_container to respect the pyproject.toml ruff line-length=100 (no noqa:E501 used — no precedent in codebase)."
  - "Chart.js CDN loader close tag is a second legitimate `</script>` in the rendered HTML — recognized and asserted in the </script> escape regression test."
metrics:
  duration: "~20 minutes (wall-clock)"
  completed: 2026-04-22
  tests_before: 379
  tests_after: 394
  tests_added: 15  # 11 TestRenderBlocks net (kept module_main; plan said 7; added test for D-05 CLI entrypoint) + 1 TestEmptyState + 1 TestGoldenSnapshot + 3 TestAtomicWrite - counted Phase 5 orchestrator tests separately below
  tests_added_dashboard: 11     # TestRenderBlocks (9) + TestEmptyState (1) + TestGoldenSnapshot (1) + TestAtomicWrite (3) = 14 new in test_dashboard.py; but scaffold placeholders removed so net = 14 - 3 = 11
  tests_added_orchestrator: 4   # 4 new TestOrchestrator tests
---

# Phase 5 Plan 3: PHASE GATE — Chart.js + HTML Shell + Atomic Write + D-06 Integration Summary

Single-file HTML dashboard, fully-automated render after every non-test run, with operator-preview CLI — Phase 5 ships.

## What Shipped

Wave 2 closes Phase 5. Three dashboard.py stubs (`_render_equity_chart_container`, `_render_html_shell`, `render_dashboard`) plus one new helper (`_atomic_write_html`) filled against the locked UI contract from 05-UI-SPEC.md. Two golden HTML fixtures regenerated from zero-byte placeholders to byte-stable references (13,111 + 8,447 bytes) via the Wave 0 regenerator — byte-identical across double-runs. Main orchestrator now calls `_render_dashboard_never_crash` AFTER `state_manager.save_state` on the non-test path only, with the import scoped inside the try/except body so both import-time and runtime failures flow through the same never-crash net.

Four orchestrator-level tests lock D-06: dashboard renders post-save on `--once`, render failures never change exit code, import-time failures never change exit code, and `--test` leaves dashboard.html untouched (mtime invariant).

PHASE GATE: 394/394 tests pass across Phases 1–5; ruff clean; regenerator double-run produces zero git diff.

## Helpers / Constants Added or Filled

| Name                             | dashboard.py lines | Purpose                                                                                  |
| -------------------------------- | ------------------ | ---------------------------------------------------------------------------------------- |
| `_INLINE_CSS` (expanded)         | 143–357            | Full ~200-line stylesheet: layout, typography, tables, cards, chart container (fixed 320px), stats grid, footer, visually-hidden, 720px breakpoint. |
| `_render_equity_chart_container` | 876–953            | Chart.js `<canvas>` + inline IIFE; `json.dumps(..., sort_keys=True, allow_nan=False).replace('</', '<\\/')` for Pitfall 1 defence + Pitfall 2 byte-stability; category x-axis; `maintainAspectRatio=false`; empty-state placeholder div when `equity_history=[]`. |
| `_render_html_shell`             | 956–984            | `<!DOCTYPE html>` + `<html lang="en">` + `<head>` with inline `<style>{_INLINE_CSS}</style>` + `<script src="..." integrity="sha384-MH1axGwz/..." crossorigin="anonymous"></script>` + `<body>` wrap. Single-file, no external stylesheet. |
| `_atomic_write_html`             | 987–1035           | Mirror of `state_manager._atomic_write` (D-17 ordering: tempfile + fsync(file) + os.replace + fsync(parent dir on POSIX)). `newline='\n'` on tempfile forces LF for cross-platform byte-stability (C-7 reviews). |
| `render_dashboard`               | 1038–1069          | Public API (D-01). `now=None` defaults to `PERTH.localize(datetime.now())` (C-1). Concatenates 7 body blocks in UI-SPEC §Component Hierarchy order. Logs `[Dashboard] rendering to X` and `[Dashboard] wrote N bytes`. |
| `if __name__ == '__main__':`     | 1072–1078          | CONTEXT D-05 convenience CLI — `python -m dashboard` loads state.json and renders dashboard.html using current AWST wall-clock. Operator preview path (C-6 reviews). |

### main.py

| Name                              | main.py lines | Purpose                                                                                  |
| --------------------------------- | ------------- | ---------------------------------------------------------------------------------------- |
| `from pathlib import Path`        | 37            | New import (main.py had no prior Path dependency).                                       |
| C-2 explanatory comment           | 51–58         | Documents why `import dashboard` does NOT appear at module top.                          |
| `_render_dashboard_never_crash`   | 94–112        | D-06 helper. `import dashboard` INSIDE try body; `except Exception` catches both import-time and runtime failures; logs WARN `[Dashboard] render failed: <Type>: <msg>`. |
| D-06 call site                    | 601–606       | `_render_dashboard_never_crash(state, Path('dashboard.html'), run_date)` — executes AFTER `state_manager.save_state(state)` on the non-test path only. |

## Inline CSS Scope

The `_INLINE_CSS` constant grew from a 16-line `:root` variable block (Wave 0 scaffold) to a full ~200-line stylesheet covering:

- `body`, `.container` — base layout
- `header h1`, `.subtitle`, `.meta` (label + value) — H1 + subtitle + Last-updated row
- `section`, `section h2` — section spacing + headings
- `.cards-row`, `.card`, `.eyebrow`, `.big-label`, `.sub`, `.scalars` — signal cards
- `.chart-container` (position: relative; height: 320px — Pitfall 5 fixed parent), `.chart-container.empty-state` — equity chart
- `.data-table`, `thead th`, `tbody td`, `.data-table tbody td.num`, `.data-table .empty-state` — positions + trades tables
- `.stats-grid`, `.stat-tile`, `.stat-tile .label`, `.stat-tile .value` — key stats block
- `.subtle` — closed-trades subtitle (F-3 sibling paragraph)
- `footer` — disclaimer
- `.visually-hidden` — accessibility utility
- `@media (max-width: 720px)` — mobile breakpoint (cards stack, stats 2-wide, container 16px padding)

All UI-SPEC §Spacing, §Typography, §Color, §Chart Component, §Responsive, §Accessibility surfaces are covered.

## Golden Fixtures

| File                                         | Before   | After       | Double-run stable? |
| -------------------------------------------- | -------- | ----------- | ------------------ |
| `tests/fixtures/dashboard/golden.html`       | 0 bytes  | 13,111 B    | Yes                |
| `tests/fixtures/dashboard/golden_empty.html` | 0 bytes  | 8,447 B     | Yes                |

Regenerated via `.venv/bin/python tests/regenerate_dashboard_golden.py` with `FROZEN_NOW = PERTH.localize(datetime(2026, 4, 22, 9, 0))`. `git diff tests/fixtures/dashboard/` returns zero diff on second run (Pitfall 2 byte-stability gate).

Smoke-check: both files are `HTML document text`, contain exactly one `<!DOCTYPE html>`, one `sha384-MH1axGwz` (SRI), and at least one `#0f1117` (palette bg).

## main.py D-06 Integration

Line references after the edits:

- `from pathlib import Path` — main.py:37
- `import dashboard` module-top — **NOT PRESENT** (C-2 gate: `grep -cE '^import dashboard\b' main.py` returns `0`).
- `_render_dashboard_never_crash` definition — main.py:94–112
  - `import dashboard` indented inside helper body — main.py:109 (C-2 gate: `grep -cE '^  +import dashboard\b' main.py` returns `1`).
- Call site — main.py:606 (C-3 gate: `grep -c '_render_dashboard_never_crash' main.py` returns exactly `2` — def + single call on non-test path).
- WARN log format — main.py:111 (`grep -c '\[Dashboard\] render failed' main.py` returns `1`).

`except Exception` count — bound strictly:

- main.py:111 — inside `_render_dashboard_never_crash` (D-06 contract; dashboard failure is cosmetic).
- main.py:734 — pre-existing Phase 4 ERR-04 (Wave 3) — top-level crash handler. Unchanged by this plan.

Both are documented and justified. No other broad `except Exception:` exists in the codebase.

## Tests

### tests/test_dashboard.py — 70 tests total (Phase 5 complete)

| Class               | Count | Wave    | Notes                                                                  |
| ------------------- | ----- | ------- | ---------------------------------------------------------------------- |
| TestStatsMath       | 20    | Wave 1  | Unchanged by this plan.                                                |
| TestFormatters      | 17    | Wave 1  | Unchanged by this plan.                                                |
| TestRenderBlocks    | 28    | W1 + W2 | W2 added 9: SRI, payload, escape (strengthened C-4), no-external-stylesheet, palette, empty-state placeholder, category-axis, shell-structure, module-main. |
| TestEmptyState      | 1     | Wave 2  | Byte-match reset_state render to golden_empty.html.                    |
| TestGoldenSnapshot  | 1     | Wave 2  | Byte-match sample_state render to golden.html.                         |
| TestAtomicWrite     | 3     | Wave 2  | Success path + crash-on-replace (original bytes preserved) + tempfile cleanup. |

### tests/test_main.py — 19 tests total (was 15 pre-plan; +4 new)

| Test                                                        | Class            | Purpose                                                                           |
| ----------------------------------------------------------- | ---------------- | --------------------------------------------------------------------------------- |
| `test_run_daily_check_renders_dashboard`                    | TestOrchestrator | D-06 happy path: --once → dashboard.html exists + valid DOCTYPE/palette/SRI.      |
| `test_dashboard_failure_never_crashes_run`                  | TestOrchestrator | D-06 runtime failure: monkeypatched `dashboard.render_dashboard` raises → rc=0 + WARN log. |
| `test_dashboard_import_time_failure_never_crashes_run`      | TestOrchestrator | C-2 import-time failure: sys.modules['dashboard'] swapped with broken shim → rc=0. |
| `test_test_flag_leaves_dashboard_html_mtime_unchanged`      | TestOrchestrator | C-3 Option A: --test leaves dashboard.html bytes + mtime unchanged (CLI-01).      |

### Phase 5 grand total

- `tests/test_dashboard.py`: 70 tests (all green).
- `tests/test_main.py`: 4 new Phase 5 tests in `TestOrchestrator` (19 total).
- **Full suite: 394/394 pass.** Baseline 379 → +15 new.

## VALIDATION.md Row Status

| Row       | Test target                                                               | Status |
| --------- | ------------------------------------------------------------------------- | ------ |
| 05-03-T1  | TestRenderBlocks::test_chartjs_sri_matches_committed                      | GREEN  |
| 05-03-T1  | TestRenderBlocks::test_equity_chart_payload_matches_state                 | GREEN  |
| 05-03-T1  | TestRenderBlocks::test_chart_payload_escapes_script_close (strengthened)  | GREEN  |
| 05-03-T1  | TestRenderBlocks::test_html_has_no_external_stylesheet_links              | GREEN  |
| 05-03-T1  | TestRenderBlocks::test_inline_css_contains_palette                        | GREEN  |
| 05-03-T1  | TestRenderBlocks::test_equity_chart_empty_state_placeholder               | GREEN  |
| 05-03-T1  | TestRenderBlocks::test_equity_chart_uses_category_axis                    | GREEN  |
| 05-03-T1  | TestRenderBlocks::test_html_shell_structure                               | GREEN  |
| 05-03-T1  | TestRenderBlocks::test_module_main_entrypoint_exists (C-6)                | GREEN  |
| 05-03-T2  | TestEmptyState::test_empty_state_matches_committed                        | GREEN  |
| 05-03-T2  | TestGoldenSnapshot::test_golden_snapshot_matches_committed                | GREEN  |
| 05-03-T2  | TestAtomicWrite::test_atomic_write_success_path                           | GREEN  |
| 05-03-T2  | TestAtomicWrite::test_crash_on_os_replace_leaves_original_intact          | GREEN  |
| 05-03-T2  | TestAtomicWrite::test_tempfile_cleaned_up_on_failure                      | GREEN  |
| 05-03-T3  | TestOrchestrator::test_run_daily_check_renders_dashboard                  | GREEN  |
| 05-03-T3  | TestOrchestrator::test_dashboard_failure_never_crashes_run                | GREEN  |
| 05-03-T3  | TestOrchestrator::test_dashboard_import_time_failure_never_crashes_run    | GREEN  |
| 05-03-T3  | TestOrchestrator::test_test_flag_leaves_dashboard_html_mtime_unchanged    | GREEN  |
| PHASE-GATE | Full `pytest tests/ -x`                                                  | 394/394 GREEN |
| PHASE-GATE | `ruff check .`                                                           | clean  |
| PHASE-GATE | Regenerator double-run `git diff --exit-code tests/fixtures/dashboard/`  | zero diff |
| PHASE-GATE | `grep -c 'raise NotImplementedError' dashboard.py`                       | 0      |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `</script>` count assertion corrected from 1 → 2**
- **Found during:** Task 1, `test_chart_payload_escapes_script_close` failed on initial run.
- **Issue:** Plan asserted `html_text.count('</script>') == 1` assuming only the IIFE close tag counted. In reality the `<head>` also emits `<script src="..." integrity=...></script>` for the Chart.js CDN loader — so the correct legitimate count is 2. The injection-leak signal becomes `count >= 3`, not `count >= 2`.
- **Fix:** Updated the assertion to `== 2` and restated the documentation. The injection defence is still verified by (a) the count remaining 2 under injected `</script>` (escape fired), and (b) the escaped form `<\/script>` appearing in the chart payload body.
- **Files modified:** tests/test_dashboard.py::TestRenderBlocks::test_chart_payload_escapes_script_close
- **Commit:** e1f6158

**2. [Rule 1 - Bug] `_render_signal_cards` crashed on Phase 3 int-shape signals**
- **Found during:** Task 2, regenerator raised `AttributeError: 'int' object has no attribute 'get'` on empty_state.json.
- **Issue:** empty_state.json contains the Phase 3 reset_state shape `{'signals': {'SPI200': 0, 'AUDUSD': 0}}`. The Wave 1 `_render_signal_cards` only handled dict shape and crashed with `AttributeError` on integers. This was a latent bug — Wave 1's tests used `_make_state` (always dict shape) and never exercised the int path.
- **Fix:** Added `isinstance(sig_entry, int)` branch in `_render_signal_cards` that renders the FLAT label + "Signal as of never" + em-dash scalars when the signal is a bare int. Mirrors main.py's D-08 upgrade-branch pattern.
- **Files modified:** dashboard.py:611–628 (_render_signal_cards)
- **Commit:** 582fca9 (bundled with golden regeneration so the fix + the byte-frozen goldens land together).

**3. [Rule 2 - Missing feature] CSS line-length compliance**
- **Found during:** Task 1, `ruff check` reported 5 E501 violations in the expanded `_INLINE_CSS` and `_render_equity_chart_container` f-string literals.
- **Issue:** Plan CSS and Chart.js config spanned over 100 characters per line; pyproject.toml sets `line-length = 100` and no codebase precedent exists for `noqa: E501`.
- **Fix:** Broke the 5 long lines into multiple physical lines while preserving rendered output (CSS token-splittable at commas/properties; Chart.js JS expression also split at commas). No `noqa` escape hatch used.
- **Files modified:** dashboard.py:162–163 (font-family), dashboard.py:246–249 (chart-container height comment + prop), dashboard.py:897–898 (canvas aria-label), dashboard.py:920–925 (Chart.js x + y scales).
- **Commit:** e1f6158

### Scope Boundaries Respected

No out-of-scope fixes applied. No pre-existing test failures touched. No architectural changes (no new dependencies, no schema bump, no new files except regenerated fixtures).

## Authentication / CLI Gates

None. This plan has no external API calls or operator prompts in its execution path.

## Self-Check

All artifacts verified present:

- `dashboard.py` — 1078 lines, 0 NotImplementedError, ruff clean.
- `tests/test_dashboard.py` — 70 tests collected, all green.
- `tests/test_main.py` — 19 tests collected, all green (15 prior + 4 new).
- `tests/fixtures/dashboard/golden.html` — 13,111 bytes, byte-stable.
- `tests/fixtures/dashboard/golden_empty.html` — 8,447 bytes, byte-stable.
- `main.py:94-112` — `_render_dashboard_never_crash` defined with in-body import.
- `main.py:606` — single call site on non-test path.
- `git log --oneline | head -3` — 3 atomic commits with `feat(05-03)`/`test(05-03)` prefix.

Commits in this plan:

| Hash    | Message                                                                                      |
| ------- | -------------------------------------------------------------------------------------------- |
| e1f6158 | feat(05-03): implement Chart.js container, HTML shell, atomic write, render_dashboard        |
| 582fca9 | test(05-03): regenerate golden HTML fixtures + fix signals int-shape handling                |
| 65f8a27 | feat(05-03): D-06 orchestrator integration — render dashboard post save_state (never-crash)  |

## Manual-Only Verifications Still Pending (VALIDATION §Manual-Only)

1. Browser preview of rendered `dashboard.html` at 1100px viewport — visual confirmation: dark bg, side-by-side signal cards, equity curve renders as a green line on dark canvas, key-stats tiles evenly spaced.
2. Mobile preview at 375px via Chrome DevTools device toolbar — confirm 720px media query fires: cards stack vertically, stats grid becomes 2×2, container padding reduces to 16px.
3. Chart.js SRI re-verification via `curl https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js | openssl dgst -sha384 -binary | openssl base64 -A` — only required if Chart.js version bumps from 4.4.6.

These are operator-only; CI does not automate them per VALIDATION §Manual-Only.

## Self-Check: PASSED
