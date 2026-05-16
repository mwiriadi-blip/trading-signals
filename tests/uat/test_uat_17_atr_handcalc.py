'''Phase 28 / DEBT-01 / UAT-17-1: ATR(14) hand-recalc to 1e-6.

Sourced from 17-VERIFICATION.md UAT-1 (ROADMAP SC-5).

Plan-06 live-DOM tightening (2026-05-10): the trace panel does NOT carry
a `[data-trace-payload]` JSON envelope. The dashboard renders OHLC and
indicators as HTML tables inside a `<details class="trace-disclosure"
data-instrument="SPI200">` element. We open the details, scrape both
tables, then Wilder-recompute ATR from the OHLC rows.

ATR period is taken from the indicator-name cell (e.g. "ATR(14)") -- the
title attribute also encodes the formula, but the parenthetical is the
authoritative period read from engine-resolved vote_params at render time
(.claude/LEARNINGS.md 2026-05-10).
'''
from __future__ import annotations

import os
import re
from decimal import Decimal

import pytest

pytestmark = pytest.mark.uat

# 1e-6 tolerance comes verbatim from ROADMAP SC-1 / REQUIREMENTS DEBT-01.
ATR_TOLERANCE = Decimal('0.000001')
DASHBOARD_PATH = os.environ.get('UAT_17_DASHBOARD_PATH', '/')
INSTRUMENT = os.environ.get('UAT_17_INSTRUMENT', 'SPI200')


def _open_trace_panel(page, instrument: str) -> None:
  selector = f'details.trace-disclosure[data-instrument="{instrument}"]'
  page.wait_for_selector(selector, timeout=15_000)
  is_open = page.evaluate(
    f"() => document.querySelector('{selector}').open"
  )
  if not is_open:
    page.locator(f'{selector} > summary.trace-summary').first.click()
  page.wait_for_function(
    f"() => document.querySelector('{selector}').open",
    timeout=5_000,
  )


def _scrape_ohlc(page, instrument: str) -> list[dict]:
  selector = (
    f'details.trace-disclosure[data-instrument="{instrument}"] '
    f'table.trace-ohlc-table tbody tr'
  )
  page.wait_for_selector(selector, timeout=10_000)
  rows = page.evaluate(
    """(sel) => Array.from(document.querySelectorAll(sel)).map(tr => {
      const tds = tr.querySelectorAll('td');
      return {
        date: tds[0]?.textContent.trim(),
        open: tds[1]?.textContent.trim(),
        high: tds[2]?.textContent.trim(),
        low: tds[3]?.textContent.trim(),
        close: tds[4]?.textContent.trim(),
      };
    })""",
    selector,
  )
  return [
    {k: r[k] for k in ('date', 'open', 'high', 'low', 'close')}
    for r in rows
    if r['date'] and r['close']
  ]


def _scrape_indicators(page, instrument: str) -> list[dict]:
  selector = (
    f'details.trace-disclosure[data-instrument="{instrument}"] '
    f'table.trace-indicators-table tbody tr'
  )
  page.wait_for_selector(selector, timeout=10_000)
  return page.evaluate(
    """(sel) => Array.from(document.querySelectorAll(sel))
        .filter(tr => tr.querySelector('td.trace-indicator-name'))
        .map(tr => ({
          name: tr.querySelector('td.trace-indicator-name')?.textContent.trim(),
          value: tr.querySelector('td.num')?.textContent.trim(),
        }))""",
    selector,
  )


def _scrape_atr_period_and_value(
  page, instrument: str
) -> tuple[int, Decimal]:
  rows = _scrape_indicators(page, instrument)
  for r in rows:
    m = re.match(r'^ATR\((\d+)\)$', (r['name'] or '').strip())
    if m:
      return int(m.group(1)), Decimal(r['value'])
  raise AssertionError(
    f'No ATR(N) row found in indicators table; rows={rows}'
  )


def _scrape_atr_seed(page, instrument: str) -> Decimal | None:
  '''Read "ATR seed (bar 0)" from the indicators table.

  The engine persists ATR at the first bar of the 40-bar OHLC window (bar 0).
  Using this as the Wilder starting point lets the hand-recalc apply TRs for
  bars 1..39 — all computable from the OHLC table since bar[0].close is the
  prev_close for bar[1]. Bar[-1].close (needed for TR at bar[0]) is not shown.
  '''
  rows = _scrape_indicators(page, instrument)
  for r in rows:
    if (r['name'] or '').strip().startswith('ATR seed'):
      try:
        return Decimal(r['value'])
      except Exception:
        return None
  return None


def _hand_recalc_atr(
  period: int, ohlc: list[dict], seed: Decimal | None = None
) -> Decimal:
  '''Wilder ATR(period). Matches signal_engine._wilder_smooth.

  If `seed` is provided (ATR at bar[0] from "ATR seed (bar 0)" trace row),
  apply TRs for bar[1..39] starting from seed to arrive at ATR for bar[39].
  Falls back to naive SMA seed if not provided.
  '''
  if len(ohlc) < 2:
    pytest.skip(f'ohlc has {len(ohlc)} bars, need >= 2')

  true_ranges: list[Decimal] = []
  for i in range(1, len(ohlc)):
    high = Decimal(ohlc[i]['high'])
    low = Decimal(ohlc[i]['low'])
    prev_close = Decimal(ohlc[i - 1]['close'])
    tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
    true_ranges.append(tr)

  if seed is not None:
    atr = seed
    for tr in true_ranges:
      atr = (atr * (period - 1) + tr) / Decimal(period)
    return atr

  if len(true_ranges) < period:
    pytest.skip(f'true_ranges has {len(true_ranges)}, need >= {period}')
  naive_seed = sum(true_ranges[:period], Decimal(0)) / Decimal(period)
  atr = naive_seed
  for tr in true_ranges[period:]:
    atr = (atr * (period - 1) + tr) / Decimal(period)
  return atr


def test_atr_14_handcalc_within_tolerance(page, base_url):
  '''Scrape live trace panel, recompute ATR(N) from persisted seed, assert |delta| <= 1e-6.'''
  page.goto(f'{base_url}{DASHBOARD_PATH}')
  _open_trace_panel(page, INSTRUMENT)
  ohlc = _scrape_ohlc(page, INSTRUMENT)
  period, displayed_atr = _scrape_atr_period_and_value(page, INSTRUMENT)
  seed = _scrape_atr_seed(page, INSTRUMENT)
  recalc = _hand_recalc_atr(period, ohlc, seed=seed)
  delta = abs(displayed_atr - recalc)
  assert delta <= ATR_TOLERANCE, (
    f'ATR drift: displayed={displayed_atr} recalc={recalc} '
    f'delta={delta} tolerance={ATR_TOLERANCE} period={period} '
    f'ohlc_bars={len(ohlc)} seed={seed}'
  )
