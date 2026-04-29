---
phase: 17
phase_name: Per-signal calculation transparency
milestone: v1.2
created: 2026-04-30
status: locked
requirements: [TRACE-01, TRACE-02, TRACE-03, TRACE-04, TRACE-05]
source: ROADMAP.md v1.2 Phase 17 Success Criteria + REQUIREMENTS.md TRACE namespace + operator discuss-phase 2026-04-30
---

# Phase 17 — Per-signal Calculation Transparency (CONTEXT)

## Goal

Operator re-derives today's signal *by hand* using only the dashboard at `https://signals.mwiriadi.me/` — no source code reading, no shell access. Three new panels per instrument (Inputs / Indicators / Vote) expose the OHLC bars, every intermediate indicator with its formula, and the final 2-of-3 vote + ADX gate that produced today's LONG/SHORT/FLAT.

## Scope

**In:**
- Dashboard renders three new panels per instrument: Inputs, Indicators, Vote
- `state.signals[<inst>]` carries the rolling OHLC slice + the full nine-indicator scalar set on every daily run (schema bump 4→5)
- `dashboard.py` reads everything off the state dict as primitives — hex-boundary preserved
- Tap-to-toggle inline formula reveal per indicator (mobile-first)
- Default-collapsed per-instrument disclosure with cookie-persisted operator preference
- 6-decimal numeric display; explicit `n/a (need N bars, have M)` / `n/a (flat price)` for NaN values
- Forbidden-imports AST guard extended to cover the new trace helpers

**Out (deferred to v1.3+):**
- Adjustable bar count by selected date range or alternate timeframe (operator-requested future enhancement, captured in §Deferred Ideas)
- Dedicated `/explain/<instrument>` route (option presented; not chosen — inline disclosure preferred)
- Live indicator recompute in the browser (server pre-computes; render is pure read)

**Out (different phases):**
- Paper-trade ledger (Phase 19), stop-loss alerts (Phase 20), backtest gate (Phase 23)
- Persisting indicator history across days (current scope writes only the *current* run's slice + scalars)

## Locked decisions

### D-01 — OHLC source at render time

**Persist a rolling N-bar OHLC slice + full indicator scalar set in `state.signals[<inst>]` on every daily run.** Pure render path: `dashboard.py` reads the slice and scalars as primitives from the state dict — no live yfinance fetch, no `state_manager`/`signal_engine` import inside the render path, no recompute.

Tradeoff accepted: state.json grows by ~5–8 KB per instrument (40 bars × 5 OHLC fields × 2 instruments = ~400 numeric values + 9 scalar dict per instrument). Atomic write contract from Phase 14 absorbs the size delta cleanly.

Rejected: re-fetch yfinance on render (violates hex-boundary, breaks `--test` mode); show only scalars (downgrades TRACE-01 reproducibility to "trust our ATR" — fails the SC-5 hand-recalc match-to-1e-6 promise).

### D-02 — Inputs panel bar count

**40 bars per instrument.** Covers `_wilder_smooth` ADX(20) seed window with buffer for hand re-derivation of today's ATR/ADX from scratch. Matches what `compute_indicators` actually consumes upstream (no ambiguity — operator sees exactly the bars the engine saw).

Per-instrument array literally named `state.signals[<inst>].ohlc_window` per D-09.

**Future enhancement (out of v1.2 scope):** adjustable bar count keyed off operator-selected date range or alternate timeframe (e.g. weekly). Captured in §Deferred Ideas.

### D-03 — Mobile formula UX

**Tap-to-toggle inline reveal per indicator.** Click/tap on the indicator's *name* (not value) reveals the formula text in a row below the value. Clicking the same name again collapses it. Hover-tooltip continues to work on desktop (REQ-02 hover contract preserved).

State held in `data-formula-open="true|false"` attribute on the row; CSS `.formula-row[hidden]` controls visibility. Zero JS dependency beyond a single click handler per panel — no animation, no third-party library.

Rejected: always-visible footnote rows (panel becomes too dense on mobile); single per-panel accordion (less granular — operator can't focus on one indicator at a time).

### D-04 — Panel placement & default state

**Inline below the per-instrument signal card. Default-collapsed.** Each instrument's signal card grows a `<details>` disclosure labelled "Show calculations" that expands inline; the disclosure expands the full triple of Inputs / Indicators / Vote panels for *that* instrument only.

Operator preference is persisted in a cookie (`tsi_trace_open=spi200,audusd` or empty), so the choice survives reload. No localStorage — sticks with the existing cookie-based session pattern from Phase 16.1.

Rejected: default-open (mobile vertical scroll burden); separate `/explain/<inst>` route (adds navigation friction; loses single-glance daily-driver feel).

### D-05 — Decimal precision

**6 decimals for every indicator scalar.** Matches `compute_indicators` post-`%.17g`-round-trip precision (Phase 1 Plan 03 established `%.17g` as the determinism oracle). Operator hand-calc using Excel default precision (~15 sig figs) matches our display to 1e-6, satisfying ROADMAP SC-5.

Format string: `f'{value:.6f}'` for finite floats. NaN handled separately per D-06.

Rejected: 4 decimals (Wilder accumulator amplifies rounding to ~1e-4 — risks false "mine doesn't match" alarms); 8 decimals (visual noise without correctness gain — last 2 digits are float-arithmetic noise after Wilder smoothing chain).

### D-06 — NaN display

**Explicit reason text in the value cell.** Two reason strings cover every NaN path the engine produces:

- Seed-window short: `n/a (need 20 bars, have 14)` — interpolated against the actual indicator's seed length and the operator's bar count
- Flat-price ADX: `n/a (flat price)` — TR=0 across seed window collapses ADX to undefined; CONTEXT D-11 from Phase 1 covers this

Helper: `dashboard._format_indicator_value(value: float, seed_required: int, bars_available: int) -> str`. Returns the formatted scalar OR the reason string. The helper is pure and testable; no I/O, no imports beyond `math.isnan`.

Rejected: plain `NaN` (honest but unfriendly — no diagnostic value); hide the row (operator can't tell if indicator is missing or zero).

### D-07 — Vote panel layout

**Three colored sign badges + ADX gate badge + final outcome line.** Per instrument:

```
Mom1  [+]  +0.012345
Mom3  [+]  +0.045210
Mom12 [-]  -0.003120

ADX gate: ADX 27.4 ≥ 25 → PASS
Vote: 2 of 3 LONG → preliminary LONG
Gate: PASS → FINAL: LONG
```

Badge colors: `+` green, `-` red, `0`/abstain grey. ADX gate badge: green PASS / red FAIL with the actual ADX value inline. Final outcome line summarises the SIG-05..08 vote rule + D-09 NaN-abstaining behaviour from Phase 1.

Rejected: inline equation (less scannable on mobile); 2-column table (loses the vote→gate→final flow that matches how the engine actually decides).

### D-08 — Schema bump 4→5

`STATE_SCHEMA_VERSION` bumps from `4` (Phase 22) to `5`. New migration `_migrate_v4_to_v5` registered in `MIGRATIONS[5]` (between key 4 and the close of the dispatch table).

Migration body:

```python
def _migrate_v4_to_v5(s: dict) -> dict:
  '''Phase 17 (v1.2): backfill empty ohlc_window + indicator_scalars on
  existing dict-shaped signal rows.

  Existing rows on first v1.2.x deploy carry signal/strategy_version/scalars
  but no ohlc_window. Stamp empty list + dict; main.py populates on next
  daily run. Idempotent (does NOT overwrite populated fields).

  Legacy int-shaped rows (Phase 3 reset_state) are skipped — only
  dict-shaped rows are migrated, matching D-04 of Phase 22.

  Silent migration: no append_warning, no log line.
  '''
  signals = s.get('signals', {})
  for inst_key, sig in signals.items():
    if isinstance(sig, dict):
      if 'ohlc_window' not in sig:
        sig['ohlc_window'] = []
      if 'indicator_scalars' not in sig:
        sig['indicator_scalars'] = {}
  return s
```

Same migration test pattern as Phase 22 §D-05 (idempotent, preserves-other-fields, skips int legacy, full-walk v0→v5).

### D-09 — Extended `state.signals[<inst>]` shape

Per instrument, the dict now carries:

| Field | Type | Source | Cardinality |
|-------|------|--------|-------------|
| `signal` | int | existing | `LONG=1`/`SHORT=-1`/`FLAT=0` |
| `signal_as_of` | str | existing | ISO date |
| `as_of_run` | str | existing | ISO date |
| `last_close` | float | existing | scalar |
| `last_scalars` | dict | existing | retained for backwards-compat readers |
| `strategy_version` | str | Phase 22 | semver |
| `ohlc_window` | list[dict] | **NEW** Phase 17 | exactly 40 entries on populated runs; `[]` immediately after migration |
| `indicator_scalars` | dict | **NEW** Phase 17 | nine keys: `tr`, `atr`, `plus_di`, `minus_di`, `adx`, `mom1`, `mom3`, `mom12`, `rvol`; `{}` immediately after migration |

Each `ohlc_window` entry: `{'date': 'YYYY-MM-DD', 'open': float, 'high': float, 'low': float, 'close': float}`. Volume omitted (RVol uses it via the engine; display is read-only and the scalar already conveys today's RVol).

`indicator_scalars` superset of the existing `last_scalars` dict — `last_scalars` is retained verbatim so any consumer of the existing key path (notifier, email templates) keeps working. The trace panels read from `indicator_scalars` to avoid coupling the new contract to the legacy two-key shape.

### D-10 — Hex-boundary preservation in dashboard.py

`dashboard.py` continues to NOT import `system_params`, `state_manager`, `data_fetcher`, `yfinance`, or `signal_engine` for the trace panels. Formula text is **inlined** in dashboard.py as plain string constants — formulas are presentation, not logic, and the engine's behaviour is already pinned by `tests/test_signal_engine.py` independent of any text we render.

Forbidden-imports guard test (`tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent`) continues to AST-walk dashboard.py with the existing forbidden list. No new entries needed because we explicitly do not import the disallowed modules; the test stays green by construction.

If a future contributor is tempted to `from signal_engine import ATR_PERIOD` to "stay DRY", that's the antipattern this rule defends against — the period number lives in the docstring/formula text once, and any drift fails the dashboard golden test rather than going silent. Match Phase 22 D-10 + project LEARNINGS 2026-04-27 ("passing primitives is OK; importing a layer is not").

### D-11 — `--test` mode behaviour

Render path is **read-only against state.json as-is** in `--test` mode. No recompute, no live fetch. If the operator runs `python main.py --test` without a recent daily run, the trace panels render whatever was last persisted (which may be the migration-empty `ohlc_window: []` + `indicator_scalars: {}`).

When `ohlc_window` is empty: render the Inputs panel with the message `Awaiting first daily run — calculations will appear after the next 08:00 AWST cycle.` instead of the bar grid. Indicators panel renders all rows as `n/a (need first daily run)` per D-06. Vote panel renders `Awaiting first daily run.`.

This preserves TRACE-04 (no state mutation in render path) and matches the existing `--test` invariant of structurally read-only behaviour from CLAUDE.md §Architecture.

### D-12 — Cookie-persisted disclosure preference

Cookie `tsi_trace_open` holds a comma-separated list of instrument keys whose disclosure is currently expanded (`SPI200`, `AUDUSD`). Set by a one-line click handler on the `<details>` element's `toggle` event; read by `_render_signal_card` to decide `<details open>` vs `<details>` at render time.

- Cookie is **not** signed — it's a pure UI preference with no privilege implications. Reuses the same `Path=/; SameSite=Lax` attributes as the existing cookie-session machinery from Phase 16.1, but with no `Secure` requirement (since it carries no secret).
- Empty cookie / missing cookie → all panels default-collapsed (D-04 default).
- 90-day expiry. Operator clearing browser data resets to default-collapsed cleanly.

### D-13 — Indicator formula text catalogue

Inlined in `dashboard.py` as a single module-level dict `_TRACE_FORMULAS` (also referenced by the formula-tooltip + tap-to-toggle reveal):

```python
_TRACE_FORMULAS: dict[str, str] = {
  'tr': 'TR = max(High − Low, |High − prev Close|, |Low − prev Close|)',
  'atr': 'ATR(14) = Wilder-smooth(TR, 14) — initial seed = SMA(TR, 14)',
  'plus_di': '+DI(20) = 100 × Wilder-smooth(+DM, 20) / ATR(20)',
  'minus_di': '-DI(20) = 100 × Wilder-smooth(-DM, 20) / ATR(20)',
  'adx': 'ADX(20) = 100 × Wilder-smooth(|+DI − -DI| / (+DI + -DI), 20)',
  'mom1': 'Mom1 = (Close_t − Close_{t-1}) / Close_{t-1}',
  'mom3': 'Mom3 = (Close_t − Close_{t-3}) / Close_{t-3}',
  'mom12': 'Mom12 = (Close_t − Close_{t-12}) / Close_{t-12}',
  'rvol': 'RVol(20) = Volume_t / SMA(Volume, 20)',
}
```

These match the Phase 1 Plan 02 oracle definitions exactly. Test: render the dashboard against a known-good fixture state and grep that every formula string appears in the HTML.

## Files to modify

- `system_params.py` — bump `STATE_SCHEMA_VERSION` 4 → 5 (one-line edit + comment)
- `state_manager.py` — add `_migrate_v4_to_v5` + register in `MIGRATIONS[5]`
- `main.py` — extend the per-instrument signal-row write site (the same `state['signals'][symbol] = {...}` block touched by Phase 22 §VERSION-02) to also populate `ohlc_window` (list of last 40 OHLC dicts) and `indicator_scalars` (full nine-key dict). The OHLC slice comes from the dataframe `compute_indicators` already consumes; the scalars come from `get_latest_indicators(df)` already used by the email/dashboard pair.
- `dashboard.py` — three new render helpers (`_render_trace_inputs`, `_render_trace_indicators`, `_render_trace_vote`); one orchestrator helper `_render_trace_panels(signal_dict) -> str`; one click-handler `<script>` block (≤20 lines, vanilla JS, no library); CSS for `.trace-panel`, `.trace-badge.{plus,minus,zero,pass,fail}`, `.formula-row[hidden]`. Modify `_render_signal_card` to wrap a `<details data-instrument="…" {open}>` around the trace panels block.
- `tests/test_state_manager.py` — extend `TestMigration` with `TestMigrateV4ToV5` (mirror Phase 22 D-05 test set: backfill, idempotent, preserves-other-fields, skips int legacy, schema bump, full-walk v0→v5)
- `tests/test_main.py` — extend the existing Phase 22 `TestRunDailyCheckTagsStrategyVersion` with `TestRunDailyCheckPersistsTracePayload` (asserts the writer puts a 40-entry `ohlc_window` and a 9-key `indicator_scalars` on every signal row write, with values matching `compute_indicators` output)
- `tests/test_dashboard.py` — new `TestTracePanels` (renders a populated state fixture and asserts each formula string + each badge class + the cookie-driven `<details open>` toggle; tests the empty-`ohlc_window` "awaiting first run" path; tests the NaN reason-text path; tests `_format_indicator_value` purely)
- `tests/test_signal_engine.py` — keep `TestDeterminism::test_forbidden_imports_absent` green (no source change; just confirm the new dashboard helpers don't introduce forbidden imports via re-run)
- `tests/fixtures/dashboard/sample_state_v5.json` — new golden state fixture with populated `ohlc_window` + `indicator_scalars` for the trace render tests

## Out of scope (don't modify)

- `signal_engine.py` — no change. The engine already produces every value the trace panels render; we just persist them all on the write side instead of dropping most after the email render.
- `notifier.py` — no change. Email body stays the v1.1 short-form; if the operator wants the trace panels in email later, that's a v1.3+ scope question.
- `data_fetcher.py` — no change. The yfinance pull is unchanged.
- `web/` (FastAPI routes) — no change. The dashboard.py render contract is the same shape; the route layer doesn't care that the rendered HTML is now larger.
- Auth / session machinery (`web/middleware/`) — no change. Cookie D-12 reuses existing cookie infra without sharing the signing key.

## Risk register

| Risk | Mitigation |
|------|-----------|
| State.json size growth blows past atomic-write budget | 40 bars × 5 fields × 2 instruments × 8 bytes/float ≈ 3.2 KB raw + ~5 KB JSON overhead. Existing state.json is ~30 KB — well below the contention-guarded write threshold. Add a `test_state_json_size_under_limit` regression test (asserts current state.json < 100 KB after a populated run). |
| Cookie tampering exposes private data | Cookie holds only instrument keys (`SPI200`, `AUDUSD`) — no operator data, no PII, no secrets. D-12 explicitly opts out of signing. |
| Hex-boundary breach via "DRY" formula imports | D-10 inlines formula text in dashboard.py. AST guard test stays green. New code-review checklist item: any `from signal_engine import` in dashboard.py is an automatic block. |
| `--test` mode renders a stale or empty trace panel and confuses the operator | D-11 explicit "Awaiting first daily run" copy; render-test covers the empty path. Operator UAT scenario: run `python main.py --test` on a fresh state.json and confirm the empty-state copy reads sensibly. |
| Future schema bump (v5 → v6) re-introduces a migration that doesn't preserve `ohlc_window` / `indicator_scalars` | Phase 22 D-05 idempotent + preserves-other-fields invariant carries forward. Test `test_migrate_v4_to_v5_preserves_other_signal_fields` mirrors that contract for the new fields. |
| Tap-to-toggle JS handler doesn't bind on iOS Safari Reader Mode / printer view | Handler is attached on `DOMContentLoaded` with progressive enhancement; without JS the formula stays visible as a `<details>` element fallback (default-open under `<noscript>`). |
| Operator hand-calc shows >1e-6 drift due to float64 rounding through Wilder accumulator | D-05 (6 decimals) keeps drift below 1e-6 threshold. The Phase 1 oracle SHA256 snapshot already locks the engine output; this phase just exposes those exact values. |
| Cookie preference desyncs across two browsers / devices | Acknowledged. Cookie is per-browser by design; multi-device parity is a v1.3+ "operator profile" concern, not v1.2. |

## Verification (what proves the phase shipped)

1. `python3 -c "import system_params; print(system_params.STATE_SCHEMA_VERSION)"` prints `5`.
2. Loading a v4 state.json (Phase 22 baseline) walks forward to v5 and stamps `ohlc_window: []` + `indicator_scalars: {}` on every dict-shaped signal row.
3. After one daily run on the migrated state, both instruments' rows carry a 40-entry `ohlc_window` and a 9-key `indicator_scalars`.
4. `curl https://signals.mwiriadi.me/` HTML body contains all nine indicator names AND all nine formula strings from `_TRACE_FORMULAS`.
5. The rendered HTML contains exactly two `<details data-instrument="SPI200">` and `<details data-instrument="AUDUSD">` blocks (one per instrument).
6. The Inputs panel for each instrument contains exactly 40 rows with `data-row-index="0"` … `data-row-index="39"`.
7. Hand-recalc test: pick today's close, prev close, and the prior 19 closes from the rendered Inputs panel; compute Mom1 / Mom3 / Mom12 / TR / ATR(14) by hand in Excel; the result matches the Indicators panel value to 1e-6 (per ROADMAP §Phase 17 SC-5).
8. `pytest tests/test_dashboard.py::TestTracePanels tests/test_state_manager.py::TestMigrateV4ToV5 tests/test_main.py::TestRunDailyCheckPersistsTracePayload tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` all pass.
9. Cookie persistence: open the trace panel for SPI200, refresh the page, the panel stays open. Close it, refresh, it stays closed. Same independently for AUDUSD.
10. Hex-boundary: `grep -E "^import system_params|^import state_manager|^import data_fetcher|^import yfinance|^from signal_engine import" dashboard.py` returns zero matches.

## Deferred ideas (out of v1.2 scope)

- **Adjustable bar count + alternate timeframe** — operator suggested at discuss-phase (2026-04-30): make the Inputs panel bar count configurable, and let the operator switch between daily and weekly timeframes. Captured here so it isn't lost; revisit at v1.3+ kick-off when SPEC.md timeframe-flexibility section is drafted.
- **`/explain/<inst>` route** — discussed and rejected for v1.2 in favour of inline disclosure (D-04). Worth reconsidering if v1.3 adds backtest replay or a per-bar drill-down.
- **Live-edit the formula display** — operator could in principle edit the formula text in the dashboard for documentation, but this collapses the formula-as-presentation invariant from D-10. Not a v1.2 concern.
- **Email parity** — render trace panels in the daily Resend email. v1.1 email is intentionally short-form; trace would push it past the typical 100 KB email-client cutoff. Defer until operator demand surfaces.

## Canonical refs

- `.planning/ROADMAP.md` §Phase 17 (success criteria 1–7)
- `.planning/REQUIREMENTS.md` §TRACE-01 .. TRACE-05
- `.planning/PROJECT.md` (operator + stack context)
- `SPEC.md` §v1.2+ Long-Term Roadmap (operator brainstorm 2026-04-29 — calc transparency rationale)
- `.planning/phases/22-strategy-versioning-audit-trail/22-CONTEXT.md` D-04, D-05, D-09, D-10 (schema bump pattern, migration shape, hex-boundary precedent)
- `.planning/phases/16.1-phone-friendly-auth-ux-for-dashboard-access/16.1-CONTEXT.md` D-12, D-13 (cookie attributes pattern + hex-boundary primitives-only precedent)
- `system_params.py` lines 19, 121 (constants block, `STATE_SCHEMA_VERSION` site)
- `state_manager.py` `_migrate_v3_to_v4` + `MIGRATIONS` dispatch (~line 157, 189)
- `main.py` signal-row write site (the same block touched by Phase 22 VERSION-02; line ~1279)
- `dashboard.py` `_render_signal_card`, `_render_footer(strategy_version)` (lines 1020, 1842) — placement and existing helpers
- `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` (forbidden-imports AST guard, line 762)
- `.claude/LEARNINGS.md` 2026-04-27 entry on hex-boundary primitives-only contract for `dashboard.py`
