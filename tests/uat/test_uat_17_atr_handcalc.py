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


def _scrape_atr_period_and_value(
  page, instrument: str
) -> tuple[int, Decimal]:
  selector = (
    f'details.trace-disclosure[data-instrument="{instrument}"] '
    f'table.trace-indicators-table tbody tr'
  )
  page.wait_for_selector(selector, timeout=10_000)
  rows = page.evaluate(
    """(sel) => Array.from(document.querySelectorAll(sel))
        .filter(tr => tr.querySelector('td.trace-indicator-name'))
        .map(tr => ({
          name: tr.querySelector('td.trace-indicator-name')?.textContent.trim(),
          value: tr.querySelector('td.num')?.textContent.trim(),
        }))""",
    selector,
  )
  for r in rows:
    m = re.match(r'^ATR\((\d+)\)$', (r['name'] or '').strip())
    if m:
      return int(m.group(1)), Decimal(r['value'])
  raise AssertionError(
    f'No ATR(N) row found in indicators table; rows={rows}'
  )


def _hand_recalc_atr(period: int, ohlc: list[dict]) -> Decimal:
  '''Wilder ATR(period). Matches signal_engine._wilder_smooth: SMA seed of
  the first `period` TR values, then recursion
  sm[t] = sm[t-1] + (tr[t] - sm[t-1]) / period.
  '''
  if len(ohlc) < period + 1:
    pytest.skip(f'ohlc has {len(ohlc)} bars, need >= {period + 1}')

  true_ranges: list[Decimal] = []
  for i in range(1, len(ohlc)):
    high = Decimal(ohlc[i]['high'])
    low = Decimal(ohlc[i]['low'])
    prev_close = Decimal(ohlc[i - 1]['close'])
    tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
    true_ranges.append(tr)

  if len(true_ranges) < period:
    pytest.skip(
      f'true_ranges has {len(true_ranges)}, need >= {period}'
    )

  seed = sum(true_ranges[:period], Decimal(0)) / Decimal(period)
  atr = seed
  for tr in true_ranges[period:]:
    atr = (atr * (period - 1) + tr) / Decimal(period)
  return atr


def test_atr_14_handcalc_within_tolerance(page, base_url):
  '''Scrape live trace panel, recompute ATR(N), assert |delta| <= 1e-6.'''
  page.goto(f'{base_url}{DASHBOARD_PATH}')
  _open_trace_panel(page, INSTRUMENT)
  ohlc = _scrape_ohlc(page, INSTRUMENT)
  period, displayed_atr = _scrape_atr_period_and_value(page, INSTRUMENT)
  recalc = _hand_recalc_atr(period, ohlc)
  delta = abs(displayed_atr - recalc)
  assert delta <= ATR_TOLERANCE, (
    f'ATR drift: displayed={displayed_atr} recalc={recalc} '
    f'delta={delta} tolerance={ATR_TOLERANCE} period={period} '
    f'ohlc_bars={len(ohlc)}'
  )
