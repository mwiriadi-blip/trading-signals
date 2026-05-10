'''Phase 28 / DEBT-01 / UAT-17-1: ATR(14) hand-recalc to 1e-6.

Sourced from .planning/milestones/v1.2-phases/17-per-signal-calculation-transparency/
17-VERIFICATION.md UAT-1 (human verification item 1: hand-recalc match-to-1e-6,
ROADMAP SC-5).

Project LEARNING (2026-05-10, .claude/LEARNINGS.md): the trace panel reads
engine-resolved persisted `vote_params` via `signal_engine.resolve_vote_params(
settings)`. This recalc MUST scrape those resolved values from the DOM rather
than re-derive from defaults -- otherwise a future settings change (e.g.
per-market `atr_period` override) silently drifts the test. Same discipline
applies to the ATR period: read what the engine recorded, do not hardcode 14.

Wilder smoothing semantics match `signal_engine._wilder_smooth` (SMA seed of
the first `period` true-range values, then Wilder recursion
sm[t] = sm[t-1] + (tr[t] - sm[t-1]) / period). NaN-strict seed-window handling
is not reproduced here -- the trace panel is expected to render only fully
populated ohlc_window rows; if the seed window contains a NaN-equivalent
(missing bar) the recalc skips per the 17-VERIFICATION.md ohlc_window=[]
caveat.

Plan-06 (live-evidence pass) may need to refine `[data-trace-payload]` /
`[data-trace-atr]` selectors against the actual rendered trace panel; if it
does, update both this spec AND record the deviation in 28-02-SUMMARY.md.
'''
from __future__ import annotations

import os
from decimal import Decimal

import pytest

pytestmark = pytest.mark.uat

# 1e-6 tolerance comes verbatim from ROADMAP SC-1 / REQUIREMENTS DEBT-01.
# Do not loosen. A 1e-3 mismatch is a real FAIL -> Phase 29 territory.
ATR_TOLERANCE = Decimal('0.000001')
DASHBOARD_PATH = os.environ.get('UAT_17_DASHBOARD_PATH', '/markets/SPI200/dashboard')


def _scrape_vote_params_and_ohlc(page) -> tuple[dict, list[dict]]:
  '''Read engine-resolved vote_params and OHLC window from the trace panel.

  Returns (vote_params, ohlc_window). Waits for ohlc_window to be non-empty
  AND of sufficient length to seed Wilder smoothing, per 17-VERIFICATION.md
  caveat (`ohlc_window=[]` race when the panel renders before the daily run
  has populated state).
  '''
  # Trace panel renders vote_params + ohlc_window as a JSON payload on a
  # single attribute carrier. Selector is the spec's contract; if the panel
  # changes shape this assertion fails loudly and the trace zip will show
  # what changed.
  page.wait_for_selector('[data-trace-payload]', timeout=15_000)
  page.wait_for_function(
    '() => {'
    '  const el = document.querySelector(\'[data-trace-payload]\');'
    '  if (!el) return false;'
    '  try {'
    '    const p = JSON.parse(el.textContent || el.dataset.tracePayload);'
    '    return Array.isArray(p.ohlc_window) && p.ohlc_window.length >= 14;'
    '  } catch (e) { return false; }'
    '}',
    timeout=15_000,
  )
  payload = page.evaluate(
    '() => {'
    '  const el = document.querySelector(\'[data-trace-payload]\');'
    '  return JSON.parse(el.textContent || el.dataset.tracePayload);'
    '}'
  )
  return payload['vote_params'], payload['ohlc_window']


def _hand_recalc_atr(vote_params: dict, ohlc: list[dict]) -> Decimal:
  '''Wilder ATR(period) -- period read from engine-resolved vote_params.

  Do NOT hardcode period=14. Per LEARNINGS.md 2026-05-10, vote_params is the
  source of truth: a settings change that bumps atr_period to 21 must flow
  through here automatically. The fallback inside `vote_params.get(...)` is
  the canonical default only and exists so that legacy state.json rows
  (pre-vote_params persistence) still recompute against the documented 14.
  '''
  period = int(vote_params.get('atr_period', 14))
  if len(ohlc) < period + 1:
    pytest.skip(f'ohlc_window has {len(ohlc)} bars, need >= {period + 1}')

  # True range: max(H-L, |H-prevC|, |L-prevC|) per Wilder. Bar 0 has no
  # prev_close so TR series starts at index 1 (length = len(ohlc)-1).
  true_ranges: list[Decimal] = []
  for i in range(1, len(ohlc)):
    high = Decimal(str(ohlc[i]['high']))
    low = Decimal(str(ohlc[i]['low']))
    prev_close = Decimal(str(ohlc[i - 1]['close']))
    tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
    true_ranges.append(tr)

  if len(true_ranges) < period:
    pytest.skip(
      f'true_ranges has {len(true_ranges)} entries, need >= {period} '
      f'to seed Wilder smoothing'
    )

  # Wilder seed = SMA of first `period` TRs. Matches signal_engine._wilder_smooth
  # SMA-seed branch (line 85: prev = float(window.mean())).
  seed = sum(true_ranges[:period], Decimal(0)) / Decimal(period)
  atr = seed
  # Wilder recursion: sm[t] = sm[t-1] + (raw[t] - sm[t-1]) / period
  # Matches signal_engine._wilder_smooth recursion branch (line 90).
  for tr in true_ranges[period:]:
    atr = (atr * (period - 1) + tr) / Decimal(period)
  return atr


def test_atr_14_handcalc_within_tolerance(page, base_url):
  '''Scrape live trace panel, recompute ATR(N), assert |delta| <= 1e-6.'''
  page.goto(f'{base_url}{DASHBOARD_PATH}')
  vote_params, ohlc = _scrape_vote_params_and_ohlc(page)

  # Displayed ATR -- also scraped from the trace panel, NOT a separate API.
  # The whole point of the UAT is "what the operator sees on the page must
  # match what they hand-recompute from the same page", per 17-VERIFICATION.md.
  displayed_atr_str = page.locator('[data-trace-atr]').first.inner_text().strip()
  displayed_atr = Decimal(displayed_atr_str)

  recalc = _hand_recalc_atr(vote_params, ohlc)
  delta = abs(displayed_atr - recalc)
  assert delta <= ATR_TOLERANCE, (
    f'ATR drift: displayed={displayed_atr} recalc={recalc} '
    f'delta={delta} tolerance={ATR_TOLERANCE} '
    f'period={vote_params.get("atr_period", 14)}'
  )
