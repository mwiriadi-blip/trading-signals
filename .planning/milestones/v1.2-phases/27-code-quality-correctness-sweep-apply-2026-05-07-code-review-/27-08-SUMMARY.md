---
phase: 27
plan: 08
subsystem: dashboard / notifier / dashboard_renderer
tags: [security, xss, html-escape, regression-tests]
dependency_graph:
  requires: [27-01, 27-02, 27-03, 27-04, 27-05, 27-06, 27-07]
  provides: [class-(a) untrusted-text escape gate, quote=True AST gate, anti-double-escape proof]
  affects: [dashboard.py paper-trade rendering, all dashboard_renderer/components/]
tech_stack:
  added: [ast walker for html.escape Call nodes (test)]
  patterns: [Phase 6 D-10 inline html.escape(value, quote=True) — extended to dashboard.py paper-trade tables; no _e helper alias introduced]
key_files:
  created:
    - tests/test_html_xss_audit.py
  modified:
    - dashboard.py
    - .planning/phases/27-…/27-08-html-escape-audit-PLAN.md
decisions:
  - Reuse Phase 6 D-10 direct html.escape(value, quote=True) pattern; do not introduce parallel _e/_escape alias (must_haves truth #6).
  - In-flight paper-trade fields (instrument, side, entry_price, contracts, stop_price) classified as class (a) untrusted text per render-variable taxonomy — escape with quote=True even though Pydantic-validated upstream (defense in depth, T-27-08-02).
  - render_*() return values classified class (b) trusted HTML fragment — composition sites compose them raw, never re-escape (anti-double-escape proven by 4 tests, T-27-08-03).
  - Test gate uses ast.walk on every html.escape(...) Call node and asserts quote=True keyword — naturally skips docstring matches that line-level grep would false-flag.
metrics:
  duration: ~30min
  completed_date: 2026-05-08
---

# Phase 27 Plan 27-08: HTML Escape Audit Summary

Classified-escape audit across notifier.py + dashboard.py + dashboard_renderer/components/ confirming Phase 6 D-10 escape coverage is preserved AND extending the `quote=True` contract to 13 paper-trade rendering sites in dashboard.py that were previously emitting `html.escape(...)` with default `quote=False` — leaving `"` payloads unescaped in attribute-context td cells.

## Render-Variable Taxonomy (audit results)

| Field / Variable | Source | Class | Action taken |
|------------------|--------|-------|--------------|
| `state['warnings'][i].message` | yfinance error / drift sentinel | (a) untrusted text | already escaped at `_render_drift_banner` line 1254 + every notifier.py render path (Phase 6 D-10) |
| `paper_trade.instrument` (open + closed rows) | POST body / state.json | (a) untrusted text | **fixed** — added `quote=True` at dashboard.py:1544, 1627 |
| `paper_trade.side` (open + closed rows) | POST body | (a) untrusted text | **fixed** — added `quote=True` at dashboard.py:1545, 1628 |
| `paper_trade.entry_price` / `exit_price` / `contracts` / `stop_price` | POST body (Decimal-quantized post 27-01) | (a) untrusted text | **fixed** — added `quote=True` at dashboard.py:1546-1548, 1629-1631 |
| `paper_trade.exit_dt` (closed) | POST body | (a) untrusted text | **fixed** — `quote=True` at dashboard.py:1631 |
| `paper_trade pnl_str` (open + closed) | controlled formatter output | (a) defensive | **fixed** — `quote=True` at dashboard.py:1549, 1632 |
| `stats["win_rate"]` | dashboard_renderer.stats output | (a) defensive | **fixed** — `quote=True` at dashboard.py:1394 |
| `selected_market` / `market_id` reaching renderers | regex-validated cookie/path | (a) defense-in-depth | already escaped at every render_market_strip / render_settings_tab interpolation |
| `signal_as_of`, `direction_raw`, `instrument_display` | state.json signals | (a) untrusted text | already escaped (notifier.py + components — Phase 6 D-10) |
| `STRATEGY_VERSION` | source-controlled constant | (c) trusted constant | escaped at footer.py defensively (no harm) |
| `render_status_strip(...)` output | trusted HTML fragment | (b) trusted | composed RAW into render_header — anti-double-escape proven |
| `render_signal_cards(...)` / `render_settings_tab(...)` / `_render_drift_banner(...)` outputs | trusted HTML fragments | (b) trusted | composed RAW into shell.render_html_shell — anti-double-escape proven |
| Hardcoded class names / template literals | source code | (c) trusted constant | left raw |

## Helper-name decision (Task 0)

- **Canonical helper:** direct stdlib `html.escape(value, quote=True)` — no wrapper.
- **Locality:** per-module (`import html` at module top of every renderer).
- **Reused from Phase 6 D-10:** yes — notifier.py has 69 inline call sites; pattern is the codebase convention.
- **No parallel `_e` alias:** verified by `TestNotifierEscapeCoverageStable.test_no_parallel_e_helper_introduced` (10 files scanned).

## Touched component files (post-audit gap closure)

| File | Sites added/changed | Trust class |
|------|---------------------|-------------|
| `dashboard.py` | 13 sites — added `, quote=True` (no other change) | (a) — paper-trade rendering |
| `dashboard_renderer/components/footer.py` | 0 (already class (c) escaped defensively) | — |
| `dashboard_renderer/components/header.py` | 0 (status_strip + headers all use quote=True) | — |
| `dashboard_renderer/components/nav.py` | 0 (market_id already escaped) | — |
| `dashboard_renderer/components/positions.py` | 0 (state_key already escaped) | — |
| `dashboard_renderer/components/settings.py` | 0 (cap_value/placeholders escaped, settings numeric values are class (c) formatter output) | — |
| `dashboard_renderer/components/signals.py` | 0 (signal_as_of, scalars escaped) | — |
| `dashboard_renderer/components/trades.py` | 0 (every column escaped with quote=True) | — |
| `notifier.py` | 0 (Phase 6 D-10 already comprehensive — 69 quote=True call sites) | — |

## Trusted fragments NOT escaped (class b — anti-double-escape)

| Composition site | Composed fragment | Anti-double-escape test |
|------------------|-------------------|------------------------|
| `render_header()` line 85 | `render_status_strip(state, now)` output | `test_status_strip_output_not_double_escaped_in_header` |
| `render_html_shell()` shell.py line 193 | full body string from `render_dashboard()` | `test_signal_card_html_not_double_escaped` |
| `render_settings_tab()` form sections | escaped placeholder vars composed into raw `<form>` markup | `test_settings_tab_form_not_double_escaped` |
| `_render_drift_banner()` lines 1257-1263 | escaped message inside trusted `<div>/<ul>/<li>` wrapper | `test_drift_banner_trusted_wrapper_not_double_escaped` |

## Before/after grep counts

| Metric | Before | After |
|--------|--------|-------|
| `html.escape(` call sites in notifier.py | 69 | 69 (unchanged — must_haves truth) |
| `html.escape(` call sites in dashboard.py | 73 | 73 (unchanged — only added `quote=True` kwarg, not new sites) |
| `html.escape(...)` calls without `quote=True` (AST-walked) | 13 (dashboard.py) | 0 |
| Parallel `_e()` / `_escape()` helpers across audited files | 0 | 0 (must_haves truth #6 honored) |

## Regression tests (8 must_haves + 2 audit gates → 23 tests)

| Class | Tests | Status |
|-------|-------|--------|
| TestXssUntrustedTextEscaped | 7 (warning, paper_trade open instrument/side, paper_trade closed instrument, market_id, signal_as_of, email warning) | 7/7 PASS |
| TestAntiDoubleEscape | 4 (status_strip in header, signal cards, settings form, drift banner wrapper) | 4/4 PASS |
| TestNotifierEscapeCoverageStable | 2 (>= 69 baseline, no parallel helper) | 2/2 PASS |
| TestEscapeQuoteTrueGate | 10 parametrized (1 per audited file — AST walk asserting `quote=True` keyword on every `html.escape()` Call node) | 10/10 PASS |
| **Total** | **23** | **23/23 PASS** |

Full suite: 1903/1903 green (was 1880 before this plan; +23 net new from this plan).

## Threat-model verification

| Threat ID | Disposition | Verification |
|-----------|-------------|--------------|
| T-27-08-01 (yfinance ticker / warning carries `<script>`) | mitigate ✓ | `test_xss_warning_field_escaped` + `test_xss_warning_field_escaped_in_email` |
| T-27-08-02 (selected_market cookie bypasses regex → renderer) | mitigate ✓ | `test_xss_market_id_escaped_in_market_strip` (defense-in-depth) |
| T-27-08-03 (mechanical bulk-escape double-escapes trusted fragment) | mitigate ✓ | 4 anti-double-escape tests assert `<div>`/`<form>`/`<article>`/`<span>` markers stay raw, `&lt;` absent |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Test mechanism]** Initial `quote=True` gate test used line-level grep with comment-stripping; matched a docstring excerpt in `dashboard.py` line 38 (`XSS posture: every dynamic value flows through html.escape() at the leaf`). Switched to `ast.walk()` over `Call` nodes — naturally skips string literals because docstrings are `ast.Constant(str)` not `ast.Call`. AST approach is structurally correct and immune to docstring/comment false-positives.

**2. [Rule 3 - Baseline calibration]** Initial baseline assertion `count >= 79` was based on raw `grep -nE 'html\.escape'` count which included multi-line docstring/comment matches. Re-counted via `re.findall(r'html\.escape\(')` (call-pattern only, AST-equivalent for this regex) → 69 actual call sites. Updated baseline to `>= 69` with explicit comment documenting the recount.

### CLAUDE.md compliance

- No new files at root (test added to `tests/` per project convention).
- No documentation files created beyond plan-output SUMMARY.md (per output spec).
- File size: dashboard.py unchanged in line count; tests/test_html_xss_audit.py = 418 lines (under 500 limit).
- Read-before-edit rule: every edit preceded by a Read of the target file.
- No secrets/credentials touched.
- Direct html.escape pattern reused — no parallel helper added.

## Self-Check: PASSED

- `[x] tests/test_html_xss_audit.py` exists (commit e55e3d3)
- `[x] dashboard.py` modifications committed (commit 8bd1c9a)
- `[x] .planning/phases/27-…/27-08-html-escape-audit-PLAN.md` Helper decision filled (commit e1c75f8)
- `[x]` 23/23 plan tests green
- `[x]` 1903/1903 full suite green
- `[x]` AST gate confirms 0 `html.escape()` calls without `quote=True` across 10 audited files
- `[x]` Notifier escape coverage unchanged (69 call sites, baseline preserved)
- `[x]` No parallel `_e` helper introduced (10 files scanned, 0 hits)

## Commits

- `e1c75f8` — docs(27-08): record helper decision (Task 0)
- `e55e3d3` — test(27-08): RED — XSS regression + anti-double-escape + quote=True gate
- `8bd1c9a` — feat(27-08): GREEN — add quote=True to 13 html.escape() sites in dashboard.py
