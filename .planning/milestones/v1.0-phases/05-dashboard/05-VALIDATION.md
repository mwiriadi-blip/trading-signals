---
phase: 05
slug: dashboard
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-22
revision_pass: 2026-04-22-reviews
revision_source: 05-REVIEWS.md (C-1 pytz sweep + C-2/C-3/C-5 new test rows)
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

Source: `05-RESEARCH.md` §Validation Architecture (Chart.js SRI + pitfalls + test-file organisation all runtime-verified).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 + pytest-freezer 0.4.9 (already pinned from Phase 4) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths=['tests']`, `addopts='-ra --strict-markers'`) |
| **Quick run command** | `.venv/bin/pytest tests/test_dashboard.py -x -q` |
| **Full suite command** | `.venv/bin/pytest tests/ -x` |
| **Phase-gate command** | `.venv/bin/pytest tests/ -x && .venv/bin/ruff check .` |
| **Estimated runtime** | ~3 seconds (Phase 4 baseline 319 tests ~1.6s; Phase 5 adds ~30 tests → ~2.5s total) |

---

## Sampling Rate

- **After every task commit:** `.venv/bin/pytest tests/test_dashboard.py -x -q` (fast; new-phase tests only)
- **After every plan wave:** `.venv/bin/pytest tests/ -x` (full suite — Phase 1/2/3/4 regression)
- **Before `/gsd-verify-work`:** Full suite green + `.venv/bin/ruff check .` clean + `tests/regenerate_dashboard_golden.py` produces zero diff against committed golden files
- **Max feedback latency:** ~3 seconds (full suite)

---

## Per-Task Verification Map

Each row corresponds to a DASH-* requirement OR a critical locked contract (D-01..D-16, UI-SPEC visual contracts, B-1 retrofit). Threat Ref column is `—` for most rows because Phase 5 has no security-boundary work beyond inherited XSS/injection mitigations documented in RESEARCH §Security Domain (V5 Input Validation).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-T3 | 01 | 0 | D-01 hex fence | V5 | dashboard.py forbids signal_engine/sizing_engine/data_fetcher/main/notifier/numpy/pandas imports | unit (AST) | `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism::test_dashboard_no_forbidden_imports -x` | ❌ W0 | ⬜ pending |
| 05-01-T4 | 01 | 0 | B-1 retrofit | — | state['signals'][key]['last_close'] exists after orchestrator run; backward-compat via .get() | unit (extension of existing test) | `.venv/bin/pytest tests/test_main.py::TestOrchestrator::test_orchestrator_reads_both_int_and_dict_signal_shape -x` | ✅ (extend existing) | ⬜ pending |
| 05-02-T1 | 02 | 1 | DASH-07 Sharpe | — | Daily log-returns, rf=0, annualised ×√252; `—` if <30 samples; guard stdev<2, log(0), log(-ve) | unit | `.venv/bin/pytest tests/test_dashboard.py::TestStatsMath -k sharpe -x` | ❌ W0 | ⬜ pending |
| 05-02-T1 | 02 | 1 | DASH-07 Max DD | — | Rolling peak-to-trough %, negative or zero; empty history → `—` | unit | `.venv/bin/pytest tests/test_dashboard.py::TestStatsMath -k max_drawdown -x` | ❌ W0 | ⬜ pending |
| 05-02-T1 | 02 | 1 | DASH-07 Win rate | — | closed trades with gross_pnl > 0 / total closed; empty log → `—` | unit | `.venv/bin/pytest tests/test_dashboard.py::TestStatsMath -k win_rate -x` | ❌ W0 | ⬜ pending |
| 05-02-T1 | 02 | 1 | DASH-07 Total return | — | (current - INITIAL_ACCOUNT) / INITIAL_ACCOUNT; always defined | unit | `.venv/bin/pytest tests/test_dashboard.py::TestStatsMath -k total_return -x` | ❌ W0 | ⬜ pending |
| 05-02-T1 | 02 | 1 | DASH-05 Unrealised P&L | — | Matches sizing_engine.compute_unrealised_pnl output on shared fixture (hex-boundary re-implementation is bit-identical) | unit | `.venv/bin/pytest tests/test_dashboard.py::TestStatsMath::test_unrealised_pnl_matches_sizing_engine -x` | ❌ W0 | ⬜ pending |
| 05-02-T2 | 02 | 1 | DASH-16 Formatters | — | currency $X,XXX.XX / percent X.X% / P&L with palette colour / em-dash for N/A | unit | `.venv/bin/pytest tests/test_dashboard.py::TestFormatters -x` | ❌ W0 | ⬜ pending |
| 05-02-T2 | 02 | 1 | DASH-08 AWST | — | "Last updated" format `YYYY-MM-DD HH:MM AWST`; rejects naive datetime | unit | `.venv/bin/pytest tests/test_dashboard.py::TestFormatters::test_fmt_last_updated_awst -x` | ❌ W0 | ⬜ pending |
| 05-02-T2 | 02 | 1 | DASH-15 XSS | V5 | Every state-derived text passes through html.escape(value, quote=True) at leaf | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_escape_applied_to_exit_reason -x` | ❌ W0 | ⬜ pending |
| 05-02-T3 | 02 | 1 | DASH-03 Signal cards | — | Cards render correct colour per signal (#22c55e LONG / #ef4444 SHORT / #eab308 FLAT / #eab308 empty) | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_signal_card_colours -x` | ❌ W0 | ⬜ pending |
| 05-02-T3 | 02 | 1 | DASH-05 Positions | — | 8-column table (Instrument/Dir/Entry/Current/Contracts/Pyramid/Trail/Unrealised); current from last_close; empty-state `colspan="8"` | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_positions_table_columns_and_values -x` | ❌ W0 | ⬜ pending |
| 05-02-T3 | 02 | 1 | DASH-06 Trades | — | 7-column table (Closed/Instr/Dir/Entry→Exit/Contracts/Reason/P&L); last 20 newest-first; empty-state `colspan="7"` | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_trades_table_slice_and_order -x` | ❌ W0 | ⬜ pending |
| 05-02-T3 | 02 | 1 | DASH-07 Stats block | — | 2x2 grid of tiles (Total Return / Sharpe / Max DD / Win Rate); responsive to <720px | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_key_stats_block -x` | ❌ W0 | ⬜ pending |
| 05-03-T1 | 03 | 2 | DASH-02 SRI | V5 | `<script src="jsdelivr Chart.js 4.4.6" integrity="sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN" crossorigin="anonymous">` present exactly once | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_chartjs_sri_matches_committed -x` | ❌ W0 | ⬜ pending |
| 05-03-T1 | 03 | 2 | DASH-04 Chart data | — | Chart.js inline script receives labels=[dates] + data=[equities] from equity_history via json.dumps; legend disabled; category x-axis | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_equity_chart_payload_matches_state -x` | ❌ W0 | ⬜ pending |
| 05-03-T1 | 03 | 2 | DASH-04 `</script>` defense | V5 | json.dumps(...).replace('</', '<\\/') applied so injected values can't close the script tag | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_chart_payload_escapes_script_close -x` | ❌ W0 | ⬜ pending |
| 05-03-T1 | 03 | 2 | DASH-01 Self-contained | — | Only external asset is Chart.js CDN script; zero `<link rel="stylesheet">` elements; CSS lives inline in `<style>` | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_html_has_no_external_stylesheet_links -x` | ❌ W0 | ⬜ pending |
| 05-03-T1 | 03 | 2 | DASH-09 Palette | — | Inline CSS contains all 4 palette hex tokens (#0f1117 / #22c55e / #ef4444 / #eab308) | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_inline_css_contains_palette -x` | ❌ W0 | ⬜ pending |
| 05-03-T2 | 03 | 2 | D-13 Empty state | — | All sections render with placeholders when equity_history/positions/trade_log are empty; chart container shows text placeholder | golden | `.venv/bin/pytest tests/test_dashboard.py::TestEmptyState::test_empty_state_matches_committed -x` | ❌ W0 | ⬜ pending |
| 05-03-T2 | 03 | 2 | D-14 Golden populated | — | render_dashboard(sample_state, out, now=frozen) produces byte-identical output to golden.html | golden | `.venv/bin/pytest tests/test_dashboard.py::TestGoldenSnapshot::test_golden_snapshot_matches_committed -x` | ❌ W0 | ⬜ pending |
| 05-03-T2 | 03 | 2 | D-03 Atomic write | — | tempfile + fsync + os.replace; mid-write crash leaves existing file intact (Phase 3 D-17 parallel) | unit | `.venv/bin/pytest tests/test_dashboard.py::TestAtomicWrite -x` | ❌ W0 | ⬜ pending |
| 05-03-T3 | 03 | 2 | D-06 Integration | — | main.run_daily_check() calls dashboard.render_dashboard(state, path, now) AFTER save_state; dashboard.html exists on disk post-run | unit | `.venv/bin/pytest tests/test_main.py::TestOrchestrator::test_run_daily_check_renders_dashboard -x` | ❌ W0 | ⬜ pending |
| 05-03-T3 | 03 | 2 | D-06 Failure isolation | — | dashboard render failure does NOT crash run; rc==0 even when render raises; log emits [Dashboard] WARN | unit (monkeypatch) | `.venv/bin/pytest tests/test_main.py::TestOrchestrator::test_dashboard_failure_never_crashes_run -x` | ❌ W0 | ⬜ pending |
| 05-03-T3r | 03 | 2 | D-06 Import-time failure isolation (C-2 reviews) | — | dashboard IMPORT-time failure (syntax error / bad sub-import) does NOT crash run; rc==0; `import dashboard` lives INSIDE `_render_dashboard_never_crash` helper body, NOT at main.py module scope | unit (monkeypatch sys.modules) | `.venv/bin/pytest tests/test_main.py::TestOrchestrator::test_dashboard_import_time_failure_never_crashes_run -x` | ❌ W0 | ⬜ pending |
| 05-03-T3t | 03 | 2 | CLI-01 --test read-only (C-3 reviews Option A) | — | Pre-created dashboard.html is unchanged (bytes + mtime) after `main.main(['--test'])`; Phase 4 CLI-01 structural read-only contract preserved; dashboard renders ONLY on non-test path | unit | `.venv/bin/pytest tests/test_main.py::TestOrchestrator::test_test_flag_leaves_dashboard_html_mtime_unchanged -x` | ❌ W0 | ⬜ pending |
| 05-02-T2s | 02 | 1 | DASH-15 XSS signal_as_of (C-5 reviews) | V5 | `_render_signal_cards` escapes `signal_as_of` via html.escape(value, quote=True); payload `<script>alert(1)</script>` renders escaped, never raw | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_signal_card_escapes_signal_as_of -x` | ❌ W0 | ⬜ pending |
| 05-02-T2u | 02 | 1 | DASH-15 XSS unknown exit_reason (C-5 reviews) | V5 | `_render_trades_table` escapes exit_reason values that miss the display-map via html.escape(value, quote=True); payload `<img src=x onerror=alert(1)>` renders escaped, never raw | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_trades_table_escapes_unknown_exit_reason -x` | ❌ W0 | ⬜ pending |
| 05-02-T2d | 02 | 1 | DASH-15 XSS positions display fallback (C-5 reviews) | V5 | `_render_positions_table` escapes unknown/state-derived display keys via html.escape(value, quote=True); belt-and-braces per D-15 | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderBlocks::test_positions_table_escapes_display_fallback -x` | ❌ W0 | ⬜ pending |
| 05-03-T1c | 03 | 2 | DASH-02 CLI (C-6 reviews, CONTEXT D-05) | — | `python -m dashboard` is a valid entrypoint — dashboard.py has `if __name__ == '__main__':` block that calls `render_dashboard(load_state(), Path('dashboard.html'))` | unit (substring check) | `.venv/bin/pytest tests/test_dashboard.py -k test_module_main_entrypoint_exists -x` | ❌ W0 | ⬜ pending |

*Status legend: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*W0 = Wave 0 scaffold creates the test file skeletons; bodies populate across Waves 1/2.*

**Row count:** 31 rows — 9 locked DASH-* requirements each mapped to 1+ named test, 3 rows per-locked-decision (D-01 hex, D-06 integration × 2), B-1 retrofit regression, PLUS 7 new rows added in the 2026-04-22-reviews revision: C-2 import-time failure (05-03-T3r), C-3 --test mtime (05-03-T3t), C-5 per-surface escape × 3 (05-02-T2s/T2u/T2d), C-6 python -m dashboard (05-03-T1c).

Each plan's acceptance criteria MUST reference the test name listed above and the exact pytest command MUST be one of the automated commands quoted here — no paraphrase, no renaming.

---

## Wave 0 Requirements (files created by 05-01 scaffold plan)

- [ ] `dashboard.py` — module scaffold with stub helpers raising NotImplementedError: `_render_header`, `_render_signal_cards`, `_render_positions_table`, `_render_trades_table`, `_render_equity_chart_container`, `_render_key_stats`, `_render_footer`, `_render_html_shell`, `render_dashboard`. Plus `_INLINE_CSS` + palette constants + `_CHARTJS_URL` + `_CHARTJS_SRI` module-level. Log prefix: `[Dashboard]`.
- [ ] `tests/test_dashboard.py` — new file with 6 test-class skeletons: TestStatsMath, TestFormatters, TestRenderBlocks, TestEmptyState, TestGoldenSnapshot, TestAtomicWrite. Mirror `tests/test_state_manager.py` style (module-level path constants + `_make_state` fixture helper + class-per-concern).
- [ ] `tests/fixtures/dashboard/` — new directory with `sample_state.json` (mid-campaign: non-empty positions, signals, trade_log, equity_history) + `empty_state.json` (first-run: all empty). Committed.
- [ ] `tests/fixtures/dashboard/golden.html` + `tests/fixtures/dashboard/golden_empty.html` — committed rendered outputs (regenerated via regenerate script with frozen clock).
- [ ] `tests/regenerate_dashboard_golden.py` — offline regeneration script (mirror of `tests/regenerate_goldens.py`). Loads fixtures, calls `render_dashboard(state, tmp, now=PERTH.localize(datetime(2026, 4, 22, 9, 0)))` where `PERTH = pytz.timezone('Australia/Perth')`. **C-1 reviews:** `.localize(...)` is mandatory — `tzinfo=pytz.timezone(...)` silently picks the historical LMT offset. Never runs in CI.
- [ ] `.gitignore` — append `dashboard.html` line (D-03).
- [ ] `tests/test_signal_engine.py::TestDeterminism` — extend AST blocklist: `DASHBOARD_PATH = Path('dashboard.py')` + `FORBIDDEN_MODULES_DASHBOARD = frozenset({'signal_engine', 'sizing_engine', 'data_fetcher', 'main', 'notifier', 'numpy', 'pandas'})` + new parametrised test `test_dashboard_no_forbidden_imports`. Also extend the 2-space indent guard `covered_paths` list.
- [ ] **B-1 retrofit in `main.py`** — extend `run_daily_check()` around line 514-519: add `'last_close': float(bar['Close'])` alongside `'last_scalars': scalars` in the signal-state dict write. Update `tests/test_main.py::TestOrchestrator::test_orchestrator_reads_both_int_and_dict_signal_shape` to assert `'last_close' in sig` with numeric check.
- [ ] `requirements.txt` — no changes needed (pytest-freezer already pinned from Phase 4).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Chart.js SRI hash re-verification | DASH-02 | SRI hash is against a CDN-served file; verification requires network access not available in CI. | `curl -sL https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js \| openssl dgst -sha384 -binary \| base64`. Expect `MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN`. Re-run if ever bumping Chart.js version. |
| `dashboard.html` renders in an actual browser | DASH-01/02/03/04 | Golden-HTML snapshot validates bytes; only a real browser validates visual layout, Chart.js runtime, palette contrast on a real display. | After `python main.py --once` against real yfinance, `open dashboard.html` (macOS) / `xdg-open dashboard.html` (Linux). Expect dark bg, signal cards side-by-side on desktop / stacked below 720px, equity curve as green line, positions + trades tables styled per UI-SPEC. |
| Mobile 375px layout | DASH-09 + UI-SPEC §Responsive Behaviour | Chrome DevTools device toolbar required. | Cmd-Opt-I → device toolbar → iPhone SE (375×667). Expect signal cards stacked, stats tiles 2×2, no horizontal scroll. |

All other phase behaviours have automated verification via the table above.

---

## Validation Sign-Off

- [ ] All 9 DASH-* requirement IDs have named automated tests in Per-Task Verification Map.
- [ ] B-1 retrofit (last_close) has a regression test.
- [ ] D-01 hex-fence enforced via AST blocklist.
- [ ] D-06 orchestrator integration tested end-to-end (render happens post-save; failure never crashes).
- [ ] Golden HTML snapshot covers populated + empty states (2 fixtures, 2 goldens).
- [ ] Feedback latency < 3s quick-run; < 5s full suite.
- [ ] `nyquist_compliant: true` flipped in frontmatter after Wave 0 commits land.

**Approval:** pending (will be set to `approved YYYY-MM-DD` after Wave 0 merges and this file is re-audited).
