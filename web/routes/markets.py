'''Market registry, per-market settings, and Market Test routes.'''
from __future__ import annotations

import html
import json
import logging
from datetime import date

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)


class MarketRequest(BaseModel):
  model_config = ConfigDict(extra='forbid')

  market_id: str = Field(pattern=r'^[A-Z0-9_]{2,20}$')
  display_name: str = Field(min_length=1)
  symbol: str = Field(min_length=1)
  currency: str = Field(default='AUD', min_length=3, max_length=3)
  multiplier: float = Field(gt=0)
  cost_aud: float = Field(ge=0)


class MarketPatchRequest(BaseModel):
  model_config = ConfigDict(extra='forbid')

  display_name: str | None = Field(default=None, min_length=1)
  symbol: str | None = Field(default=None, min_length=1)
  currency: str | None = Field(default=None, min_length=3, max_length=3)
  multiplier: float | None = Field(default=None, gt=0)
  cost_aud: float | None = Field(default=None, ge=0)
  enabled: bool | None = None
  sort_order: int | None = None


class MarketSettingsRequest(BaseModel):
  model_config = ConfigDict(extra='forbid')

  market_id: str = Field(pattern=r'^[A-Z0-9_]{2,20}$')
  adx_gate: float = Field(ge=0)
  momentum_votes_required: int = Field(ge=1, le=3)
  trail_mult_long: float = Field(gt=0)
  trail_mult_short: float = Field(gt=0)
  risk_pct_long: float = Field(gt=0)
  risk_pct_short: float = Field(gt=0)
  one_contract_floor: bool = False
  contract_cap: int | None = None

  @model_validator(mode='after')
  def _cap_positive(self) -> MarketSettingsRequest:
    if self.contract_cap is not None and self.contract_cap <= 0:
      raise ValueError('contract_cap must be greater than zero when supplied')
    return self


def _settings_to_state(req: MarketSettingsRequest) -> dict:
  return {
    'adx_gate': float(req.adx_gate),
    'momentum_votes_required': int(req.momentum_votes_required),
    'trail_mult_long': float(req.trail_mult_long),
    'trail_mult_short': float(req.trail_mult_short),
    'risk_pct_long': float(req.risk_pct_long) / 100.0,
    'risk_pct_short': float(req.risk_pct_short) / 100.0,
    'one_contract_floor': bool(req.one_contract_floor),
    'contract_cap': req.contract_cap,
  }


def _save_settings(market_id: str, req: MarketSettingsRequest) -> None:
  from state_manager import mutate_state

  def _apply(state: dict) -> None:
    if market_id not in state.get('markets', {}):
      raise HTTPException(status_code=404, detail='market not found')
    if req.market_id != market_id:
      raise HTTPException(status_code=400, detail='market_id does not match path')
    state.setdefault('strategy_settings', {})[market_id] = _settings_to_state(req)

  mutate_state(_apply)


def _market_test_result_html(report: dict) -> str:
  metrics = report['metrics']
  trades = report['trades'][:20]
  rows = []
  for trade in trades:
    rows.append(
      '<tr>'
      f'<td>{html.escape(str(trade.get("open_dt", "")), quote=True)}</td>'
      f'<td>{html.escape(str(trade.get("close_dt", "")), quote=True)}</td>'
      f'<td>{html.escape(str(trade.get("side", "")), quote=True)}</td>'
      f'<td class="num">{html.escape(str(trade.get("contracts", "")), quote=True)}</td>'
      f'<td class="num">{float(trade.get("net_pnl_aud", 0.0)):+.2f}</td>'
      '</tr>'
    )
  if not rows:
    rows.append('<tr><td colspan="5" class="empty-state">No closed trades.</td></tr>')
  return (
    '<section class="market-test-summary">\n'
    '  <h3>Result</h3>\n'
    '  <div class="stats-grid account-stats-grid">\n'
    f'    <div class="stat-tile"><p class="label">Final</p>'
    f'<p class="value">${report["final_account_aud"]:,.2f}</p></div>\n'
    f'    <div class="stat-tile"><p class="label">Return</p>'
    f'<p class="value">{metrics["cumulative_return_pct"]:+.2f}%</p></div>\n'
    f'    <div class="stat-tile"><p class="label">Max Drawdown</p>'
    f'<p class="value">{metrics["max_drawdown_pct"]:.2f}%</p></div>\n'
    f'    <div class="stat-tile"><p class="label">Win Rate</p>'
    f'<p class="value">{metrics["win_rate"] * 100:.1f}%</p></div>\n'
    f'    <div class="stat-tile"><p class="label">Trades</p>'
    f'<p class="value">{metrics["total_trades"]}</p></div>\n'
    '  </div>\n'
    '  <table class="data-table"><thead><tr><th>Open</th><th>Close</th>'
    '<th>Side</th><th>Contracts</th><th>P&L</th></tr></thead><tbody>\n'
    f'{"".join(rows)}'
    '  </tbody></table>\n'
    '</section>\n'
  )


def register(app: FastAPI) -> None:
  @app.post('/markets')
  def add_market(req: MarketRequest) -> Response:
    from state_manager import mutate_state
    from system_params import DEFAULT_STRATEGY_SETTINGS

    def _apply(state: dict) -> None:
      markets = state.setdefault('markets', {})
      if req.market_id in markets:
        raise HTTPException(status_code=409, detail='market already exists')
      order = max(
        [int(m.get('sort_order', 0)) for m in markets.values() if isinstance(m, dict)]
        or [0],
      ) + 10
      markets[req.market_id] = {
        'display_name': req.display_name,
        'symbol': req.symbol,
        'currency': req.currency.upper(),
        'multiplier': float(req.multiplier),
        'cost_aud': float(req.cost_aud),
        'enabled': True,
        'sort_order': order,
      }
      state.setdefault('positions', {})[req.market_id] = None
      state.setdefault('signals', {})[req.market_id] = 0
      state.setdefault('strategy_settings', {})[req.market_id] = dict(DEFAULT_STRATEGY_SETTINGS)

    mutate_state(_apply)
    return JSONResponse({'ok': True}, headers={'HX-Trigger': 'markets-changed'})

  @app.patch('/markets/{market_id}')
  def update_market(market_id: str, req: MarketPatchRequest) -> Response:
    from state_manager import mutate_state

    def _apply(state: dict) -> None:
      markets = state.setdefault('markets', {})
      market = markets.get(market_id)
      if not isinstance(market, dict):
        raise HTTPException(status_code=404, detail='market not found')
      updates = req.model_dump(exclude_unset=True)
      if 'currency' in updates and updates['currency'] is not None:
        updates['currency'] = updates['currency'].upper()
      market.update(updates)

    mutate_state(_apply)
    return JSONResponse({'ok': True}, headers={'HX-Trigger': 'markets-changed'})

  @app.patch('/markets/{market_id}/settings')
  def save_market_settings_for_path(market_id: str, req: MarketSettingsRequest) -> Response:
    _save_settings(market_id, req)
    return JSONResponse({'ok': True}, headers={'HX-Trigger': 'settings-changed'})

  @app.patch('/markets/settings')
  def save_market_settings(req: MarketSettingsRequest) -> Response:
    _save_settings(req.market_id, req)
    return JSONResponse({'ok': True}, headers={'HX-Trigger': 'settings-changed'})

  @app.post('/market-test/run', response_class=HTMLResponse)
  def run_market_test(
    market_id: str = Form(...),  # noqa: B008
    start_date: date = Form(...),  # noqa: B008
    end_date: date = Form(...),  # noqa: B008
    initial_account_aud: float = Form(...),  # noqa: B008
    adx_gate: float | None = Form(None),  # noqa: B008
    momentum_votes_required: int | None = Form(None),  # noqa: B008
    risk_pct_long: float | None = Form(None),  # noqa: B008
    risk_pct_short: float | None = Form(None),  # noqa: B008
  ) -> HTMLResponse:
    if start_date >= end_date:
      return HTMLResponse('Start date must be before end date.', status_code=400)
    if initial_account_aud <= 0:
      return HTMLResponse('Initial balance must be greater than zero.', status_code=400)

    from backtest.data_fetcher import fetch_ohlcv
    from backtest.metrics import compute_metrics
    from backtest.simulator import simulate
    from state_manager import load_state

    state = load_state()
    market = state.get('markets', {}).get(market_id)
    if not isinstance(market, dict) or not market.get('enabled', True):
      return HTMLResponse('Market not found or disabled.', status_code=404)
    settings = {
      **state.get('strategy_settings', {}).get(market_id, {}),
    }
    if adx_gate is not None:
      settings['adx_gate'] = float(adx_gate)
    if momentum_votes_required is not None:
      settings['momentum_votes_required'] = int(momentum_votes_required)
    if risk_pct_long is not None:
      settings['risk_pct_long'] = float(risk_pct_long) / 100.0
    if risk_pct_short is not None:
      settings['risk_pct_short'] = float(risk_pct_short) / 100.0

    df = fetch_ohlcv(
      market['symbol'],
      start_date.isoformat(),
      end_date.isoformat(),
      refresh=False,
      min_years=0,
    )
    result = simulate(
      df,
      market_id,
      float(market.get('multiplier', 1.0)),
      float(market.get('cost_aud', 0.0)),
      float(initial_account_aud),
      settings=settings,
    )
    metrics = compute_metrics(result.equity_curve, result.trades)
    report = {
      'final_account_aud': result.final_account,
      'metrics': metrics,
      'trades': sorted(result.trades, key=lambda t: (t['close_dt'], t['instrument'])),
    }
    logger.info('[Web] market-test %s %s..%s %s',
                market_id, start_date, end_date, json.dumps(metrics, sort_keys=True))
    return HTMLResponse(_market_test_result_html(report))
