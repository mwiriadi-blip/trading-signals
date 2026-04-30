'''Phase 20 D-12/D-18 — main._evaluate_paper_trade_alerts tests.

Two-phase commit orchestrator: eval -> send -> conditional commit.
D-18 anchor: called AFTER mutate_state(_apply_daily_run) and BEFORE
_render_dashboard_never_crash — never inside the _apply_daily_run closure.

Covers:
  TestEvaluatePaperTradeAlerts — all state transitions, dedup, rollback,
    two-phase commit, ATR-NaN safety, call-site ordering, return shape
'''
import json
import logging
from pathlib import Path

import pytest

import main
import state_manager


# =========================================================================
# State fixtures
# =========================================================================

def _open_row(
  trade_id: str = 'SPI200-20260430-001',
  instrument: str = 'SPI200',
  side: str = 'LONG',
  stop_price: float | None = 8100.0,
  last_alert_state: str | None = None,
  status: str = 'open',
) -> dict:
  return {
    'id': trade_id,
    'instrument': instrument,
    'side': side,
    'entry_dt': '2026-04-30T08:00:00+08:00',
    'entry_price': 8200.0,
    'contracts': 1,
    'stop_price': stop_price,
    'entry_cost_aud': 3.0,
    'status': status,
    'exit_dt': None,
    'exit_price': None,
    'realised_pnl': None,
    'strategy_version': 'v1.2.0',
    'last_alert_state': last_alert_state,
  }


def _signals_for(
  inst: str,
  close: float = 8150.0,
  low: float = 8050.0,
  high: float = 8200.0,
  atr: float = 50.0,
) -> dict:
  '''Build a minimal signals[inst] dict with ohlc_window + indicator_scalars.
  Uses lowercase keys per D-17 (main.py:1279-1290).
  '''
  return {
    'signal': 1,
    'ohlc_window': [
      {'date': '2026-04-29', 'open': low, 'high': high, 'low': low, 'close': close},
    ],
    'indicator_scalars': {'atr': atr},
  }


def _make_state(
  paper_trades: list[dict] | None = None,
  spi_close: float = 8150.0,
  spi_low: float = 8050.0,
  spi_high: float = 8200.0,
  spi_atr: float = 50.0,
  audusd_close: float = 0.6520,
  audusd_low: float = 0.6480,
  audusd_high: float = 0.6560,
  audusd_atr: float = 0.005,
) -> dict:
  return {
    'schema_version': 7,
    'account': 100_000.0,
    'last_run': '2026-04-30',
    'positions': {'SPI200': None, 'AUDUSD': None},
    'signals': {
      'SPI200': _signals_for('SPI200', close=spi_close, low=spi_low,
                              high=spi_high, atr=spi_atr),
      'AUDUSD': _signals_for('AUDUSD', close=audusd_close, low=audusd_low,
                              high=audusd_high, atr=audusd_atr),
    },
    'trade_log': [], 'equity_history': [], 'warnings': [],
    'initial_account': 100_000.0,
    'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'},
    'paper_trades': paper_trades if paper_trades is not None else [],
  }


def _seed_state_file(tmp_path: Path, state: dict) -> Path:
  '''Write state dict to tmp_path/state.json and return the path.'''
  p = tmp_path / 'state.json'
  p.write_text(json.dumps(state, indent=2))
  return p


# =========================================================================
# TestEvaluatePaperTradeAlerts
# =========================================================================

class TestEvaluatePaperTradeAlerts:
  '''D-12/D-18: _evaluate_paper_trade_alerts two-phase commit.'''

  def test_no_open_paper_trades_returns_emailed_false(
    self, tmp_path, monkeypatch,
  ) -> None:
    '''Empty paper_trades -> returns {transitions:[], emailed:False}.
    send_stop_alert_email NEVER called.
    '''
    state = _make_state(paper_trades=[])
    p = _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    called = []
    monkeypatch.setattr('notifier.send_stop_alert_email',
                        lambda *a, **kw: called.append(1) or True)

    result = main._evaluate_paper_trade_alerts(state, 'http://x')
    assert result == {'transitions': [], 'emailed': False}
    assert called == []

  def test_no_stop_price_skipped(self, tmp_path, monkeypatch) -> None:
    '''Open row with stop_price=None is skipped from evaluation.'''
    row = _open_row(stop_price=None, last_alert_state=None)
    state = _make_state(paper_trades=[row])
    _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    called = []
    monkeypatch.setattr('notifier.send_stop_alert_email',
                        lambda *a, **kw: called.append(1) or True)

    result = main._evaluate_paper_trade_alerts(state, 'http://x')
    assert result == {'transitions': [], 'emailed': False}
    assert called == []

  def test_status_closed_skipped(self, tmp_path, monkeypatch) -> None:
    '''Closed row is excluded from evaluation (REQ-01).'''
    row = _open_row(stop_price=8100.0, last_alert_state=None, status='closed')
    state = _make_state(paper_trades=[row])
    _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    called = []
    monkeypatch.setattr('notifier.send_stop_alert_email',
                        lambda *a, **kw: called.append(1) or True)

    result = main._evaluate_paper_trade_alerts(state, 'http://x')
    assert result == {'transitions': [], 'emailed': False}
    assert called == []

  def test_initial_none_to_clear_no_email(
    self, tmp_path, monkeypatch,
  ) -> None:
    '''None -> CLEAR: NOT email-worthy. send_stop_alert_email NOT called.
    But last_alert_state IS updated to CLEAR on disk (no-op write, idempotent).
    SPI close=8150 far above stop=8100; atr=50; abs(8150-8100)=50 > 0.5*50=25. CLEAR.
    '''
    row = _open_row(stop_price=8100.0, last_alert_state=None)
    # spi_low=8110 > stop=8100 to prevent HIT; close=8150 far from stop -> CLEAR
    state = _make_state(paper_trades=[row], spi_close=8150.0, spi_low=8110.0, spi_atr=50.0)
    p = _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    called = []
    monkeypatch.setattr('notifier.send_stop_alert_email',
                        lambda *a, **kw: called.append(1) or True)
    # Use real mutate_state with the seeded file
    result = main._evaluate_paper_trade_alerts(state, 'http://x')
    assert result['emailed'] is False
    assert result['transitions'] == []
    assert called == []
    # last_alert_state updated to CLEAR on disk via no-op write
    saved = json.loads(p.read_text())
    assert saved['paper_trades'][0]['last_alert_state'] == 'CLEAR'

  def test_initial_none_to_approaching_emails(
    self, tmp_path, monkeypatch,
  ) -> None:
    '''None -> APPROACHING: email-worthy. send_stop_alert_email called.
    SPI close=8120, stop=8100, atr=50; abs(8120-8100)=20 <= 0.5*50=25. APPROACHING.
    low=8110 > stop=8100 so NOT HIT.
    '''
    row = _open_row(stop_price=8100.0, last_alert_state=None)
    state = _make_state(paper_trades=[row], spi_close=8120.0, spi_low=8110.0, spi_atr=50.0)
    p = _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    sent_transitions = []
    def _fake_send(transitions, url):
      sent_transitions.extend(transitions)
      return True

    monkeypatch.setattr('notifier.send_stop_alert_email', _fake_send)
    result = main._evaluate_paper_trade_alerts(state, 'http://x')
    assert result['emailed'] is True
    assert len(result['transitions']) == 1
    assert sent_transitions[0]['new_state'] == 'APPROACHING'
    # Committed to disk
    saved = json.loads(p.read_text())
    assert saved['paper_trades'][0]['last_alert_state'] == 'APPROACHING'

  def test_initial_none_to_hit_emails(
    self, tmp_path, monkeypatch,
  ) -> None:
    '''None -> HIT: email-worthy. LONG with low <= stop.
    SPI low=8050 <= stop=8100. HIT.
    '''
    row = _open_row(stop_price=8100.0, last_alert_state=None)
    state = _make_state(paper_trades=[row], spi_low=8050.0, spi_atr=50.0)
    p = _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    sent = []
    monkeypatch.setattr('notifier.send_stop_alert_email',
                        lambda t, u: sent.append(t) or True)
    result = main._evaluate_paper_trade_alerts(state, 'http://x')
    assert result['emailed'] is True
    assert sent[0][0]['new_state'] == 'HIT'

  def test_clear_to_approaching_emails(
    self, tmp_path, monkeypatch,
  ) -> None:
    '''CLEAR -> APPROACHING: email-worthy.'''
    row = _open_row(stop_price=8100.0, last_alert_state='CLEAR')
    # spi_low=8110 > stop=8100 to prevent HIT; close=8120 within 0.5*50=25 -> APPROACHING
    state = _make_state(paper_trades=[row], spi_close=8120.0, spi_low=8110.0, spi_atr=50.0)
    p = _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    sent = []
    monkeypatch.setattr('notifier.send_stop_alert_email',
                        lambda t, u: sent.append(t) or True)
    result = main._evaluate_paper_trade_alerts(state, 'http://x')
    assert result['emailed'] is True
    assert len(result['transitions']) == 1
    assert result['transitions'][0]['new_state'] == 'APPROACHING'

  def test_clear_to_hit_emails(self, tmp_path, monkeypatch) -> None:
    '''REQ-02 (* -> HIT per ROADMAP SC-2): CLEAR -> HIT emails.'''
    row = _open_row(stop_price=8100.0, last_alert_state='CLEAR')
    state = _make_state(paper_trades=[row], spi_low=8050.0, spi_atr=50.0)
    p = _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    sent = []
    monkeypatch.setattr('notifier.send_stop_alert_email',
                        lambda t, u: sent.append(t) or True)
    result = main._evaluate_paper_trade_alerts(state, 'http://x')
    assert result['emailed'] is True
    assert result['transitions'][0]['new_state'] == 'HIT'
    # Committed
    saved = json.loads(p.read_text())
    assert saved['paper_trades'][0]['last_alert_state'] == 'HIT'

  def test_clear_to_clear_no_email(self, tmp_path, monkeypatch) -> None:
    '''Dedup: CLEAR -> CLEAR (same state). NOT a transition.
    send_stop_alert_email NOT called (REQ-03 / ROADMAP SC-3).
    '''
    row = _open_row(stop_price=8100.0, last_alert_state='CLEAR')
    # spi_low=8110 > stop=8100 to prevent HIT; close=8150 far -> CLEAR
    state = _make_state(paper_trades=[row], spi_close=8150.0, spi_low=8110.0, spi_atr=50.0)
    _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    called = []
    monkeypatch.setattr('notifier.send_stop_alert_email',
                        lambda *a, **kw: called.append(1) or True)
    result = main._evaluate_paper_trade_alerts(state, 'http://x')
    assert result == {'transitions': [], 'emailed': False}
    assert called == []

  def test_approaching_to_clear_no_email(
    self, tmp_path, monkeypatch, caplog,
  ) -> None:
    '''APPROACHING -> CLEAR: NOT email-worthy per CONTEXT D-12.
    send_stop_alert_email NOT called. But last_alert_state IS updated to
    CLEAR on disk via no_op_writes path (badge color refresh).
    '''
    row = _open_row(stop_price=8100.0, last_alert_state='APPROACHING')
    # Close far from stop: CLEAR; spi_low=8110 > stop=8100 to prevent HIT
    state = _make_state(paper_trades=[row], spi_close=8150.0, spi_low=8110.0, spi_atr=50.0)
    p = _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    called = []
    monkeypatch.setattr('notifier.send_stop_alert_email',
                        lambda *a, **kw: called.append(1) or True)
    with caplog.at_level(logging.INFO):
      result = main._evaluate_paper_trade_alerts(state, 'http://x')
    assert result['transitions'] == []
    assert result['emailed'] is False
    assert called == [], 'APPROACHING->CLEAR must NOT trigger email'
    # Badge refresh: last_alert_state updated to CLEAR on disk
    saved = json.loads(p.read_text())
    assert saved['paper_trades'][0]['last_alert_state'] == 'CLEAR', (
      'APPROACHING->CLEAR must persist CLEAR to disk for badge refresh'
    )
    # No [Alert] N transition(s) emailed log line for this row
    emailed_lines = [r.getMessage() for r in caplog.records
                     if 'emailed and committed' in r.getMessage()]
    assert emailed_lines == []

  def test_approaching_to_approaching_dedup_no_email(
    self, tmp_path, monkeypatch,
  ) -> None:
    '''APPROACHING -> APPROACHING (same state). Dedup. NOT a transition.'''
    row = _open_row(stop_price=8100.0, last_alert_state='APPROACHING')
    # spi_low=8110 > stop=8100 to prevent HIT; close=8120 within 0.5*50=25 -> APPROACHING
    state = _make_state(paper_trades=[row], spi_close=8120.0, spi_low=8110.0, spi_atr=50.0)
    _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    called = []
    monkeypatch.setattr('notifier.send_stop_alert_email',
                        lambda *a, **kw: called.append(1) or True)
    result = main._evaluate_paper_trade_alerts(state, 'http://x')
    assert result == {'transitions': [], 'emailed': False}
    assert called == []

  def test_approaching_to_hit_emails(self, tmp_path, monkeypatch) -> None:
    '''APPROACHING -> HIT: email-worthy (* -> HIT).'''
    row = _open_row(stop_price=8100.0, last_alert_state='APPROACHING')
    state = _make_state(paper_trades=[row], spi_low=8050.0, spi_atr=50.0)
    p = _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    sent = []
    monkeypatch.setattr('notifier.send_stop_alert_email',
                        lambda t, u: sent.append(t) or True)
    result = main._evaluate_paper_trade_alerts(state, 'http://x')
    assert result['emailed'] is True
    assert result['transitions'][0]['new_state'] == 'HIT'

  def test_hit_to_hit_dedup_no_email(self, tmp_path, monkeypatch) -> None:
    '''D-07 HIT terminal stay: HIT -> HIT (same state). Dedup. No email.'''
    row = _open_row(stop_price=8100.0, last_alert_state='HIT')
    state = _make_state(paper_trades=[row], spi_low=8050.0, spi_atr=50.0)
    _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    called = []
    monkeypatch.setattr('notifier.send_stop_alert_email',
                        lambda *a, **kw: called.append(1) or True)
    result = main._evaluate_paper_trade_alerts(state, 'http://x')
    assert result == {'transitions': [], 'emailed': False}
    assert called == []

  def test_hit_to_clear_emails(self, tmp_path, monkeypatch) -> None:
    '''D-07 HIT recovery: HIT -> CLEAR is email-worthy.
    SPI close=8150 far above stop=8100, low=8110 > stop. CLEAR.
    '''
    row = _open_row(stop_price=8100.0, last_alert_state='HIT')
    state = _make_state(paper_trades=[row], spi_close=8150.0, spi_low=8110.0, spi_atr=50.0)
    p = _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    sent = []
    monkeypatch.setattr('notifier.send_stop_alert_email',
                        lambda t, u: sent.append(t) or True)
    result = main._evaluate_paper_trade_alerts(state, 'http://x')
    assert result['emailed'] is True
    assert result['transitions'][0]['new_state'] == 'CLEAR'

  def test_send_failure_rollback(
    self, tmp_path, monkeypatch, caplog,
  ) -> None:
    '''D-06 rollback: on send failure, transitioning rows retain prior
    last_alert_state. Non-transitioning no-op write IS persisted unconditionally.

    Setup: 2 transitioning rows (None->APPROACHING) + 1 non-transitioning
    (None->CLEAR no-op write).
    Mock send returns False.
    Assert: transitioning rows still None on disk; no-op row is CLEAR on disk.
    caplog contains [Alert] WARN stop alert email failed.
    '''
    row_approach1 = _open_row(
      trade_id='SPI200-20260430-001', instrument='SPI200', side='LONG',
      stop_price=8100.0, last_alert_state=None,
    )
    row_approach2 = _open_row(
      trade_id='AUDUSD-20260430-001', instrument='AUDUSD', side='LONG',
      stop_price=0.6500, last_alert_state=None,
    )
    # no-op: CLEAR (None->CLEAR, not email-worthy)
    row_noop = _open_row(
      trade_id='SPI200-20260430-002', instrument='SPI200', side='LONG',
      stop_price=8100.0, last_alert_state=None,
    )
    # SPI: close=8120 (APPROACHING), AUDUSD: close far from stop (CLEAR for row3)
    state = _make_state(
      paper_trades=[row_approach1, row_approach2, row_noop],
      spi_close=8120.0, spi_low=8050.0, spi_atr=50.0,
      audusd_close=0.6520, audusd_low=0.6480, audusd_atr=0.005,
    )
    # row_approach2 AUDUSD: close=0.6520, stop=0.6500, atr=0.005
    # abs(0.6520-0.6500)=0.002 <= 0.5*0.005=0.0025 -> APPROACHING
    # row_noop SPI: close=8120, stop=8100, atr=50
    # abs(8120-8100)=20 <= 0.5*50=25 -> APPROACHING too! Need to make it CLEAR.
    # Use different stop_price for row_noop to get CLEAR.
    row_noop['stop_price'] = 7900.0  # far below close=8120; abs(8120-7900)=220 > 25. CLEAR.
    p = _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr('notifier.send_stop_alert_email', lambda t, u: False)
    with caplog.at_level(logging.WARNING):
      result = main._evaluate_paper_trade_alerts(state, 'http://x')

    assert result['emailed'] is False
    # Transitioning rows NOT updated (rollback)
    saved = json.loads(p.read_text())
    trades_by_id = {r['id']: r for r in saved['paper_trades']}
    assert trades_by_id['SPI200-20260430-001']['last_alert_state'] is None, (
      'D-06: transitioning row must stay None on send failure (rollback)'
    )
    assert trades_by_id['AUDUSD-20260430-001']['last_alert_state'] is None, (
      'D-06: transitioning row must stay None on send failure (rollback)'
    )
    # No-op write IS persisted unconditionally
    assert trades_by_id['SPI200-20260430-002']['last_alert_state'] == 'CLEAR', (
      'D-12: no-op (None->CLEAR) must be persisted regardless of send outcome'
    )
    # WARN log
    warn_msgs = [r.getMessage() for r in caplog.records
                 if 'WARN stop alert email failed' in r.getMessage()]
    assert warn_msgs, (
      'D-06: [Alert] WARN stop alert email failed must appear in caplog'
    )

  def test_send_success_commits(
    self, tmp_path, monkeypatch, caplog,
  ) -> None:
    '''On send success: both transitioning rows updated to new state on disk.
    caplog contains [Alert] N transition(s) emailed and committed.
    '''
    row1 = _open_row(
      trade_id='SPI200-20260430-001', stop_price=8100.0, last_alert_state=None,
    )
    row2 = _open_row(
      trade_id='SPI200-20260430-002', stop_price=8100.0, last_alert_state='CLEAR',
    )
    # spi_low=8110 > stop=8100 to prevent HIT; close=8120 within 0.5*50=25 -> APPROACHING
    state = _make_state(
      paper_trades=[row1, row2],
      spi_close=8120.0, spi_low=8110.0, spi_atr=50.0,
    )
    p = _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr('notifier.send_stop_alert_email', lambda t, u: True)
    with caplog.at_level(logging.INFO):
      result = main._evaluate_paper_trade_alerts(state, 'http://x')

    assert result['emailed'] is True
    saved = json.loads(p.read_text())
    trades_by_id = {r['id']: r for r in saved['paper_trades']}
    assert trades_by_id['SPI200-20260430-001']['last_alert_state'] == 'APPROACHING'
    assert trades_by_id['SPI200-20260430-002']['last_alert_state'] == 'APPROACHING'
    info_msgs = [r.getMessage() for r in caplog.records
                 if 'emailed and committed' in r.getMessage()]
    assert info_msgs

  def test_atr_nan_treated_as_clear_with_warn_log(
    self, tmp_path, monkeypatch, caplog,
  ) -> None:
    '''ATR missing (indicator_scalars={}) -> treats as CLEAR + emits WARN log.
    No email.
    '''
    row = _open_row(stop_price=8100.0, last_alert_state=None)
    state = _make_state(paper_trades=[row])
    # Override SPI200 signals to have empty indicator_scalars
    state['signals']['SPI200']['indicator_scalars'] = {}
    p = _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    called = []
    monkeypatch.setattr('notifier.send_stop_alert_email',
                        lambda *a, **kw: called.append(1) or True)
    with caplog.at_level(logging.WARNING):
      result = main._evaluate_paper_trade_alerts(state, 'http://x')

    assert called == [], 'No ATR = CLEAR = no email'
    warn_msgs = [r.getMessage() for r in caplog.records
                 if 'WARN no ATR for SPI200' in r.getMessage()]
    assert warn_msgs, (
      'D-10: [Alert] WARN no ATR for SPI200; treating as CLEAR must appear in caplog'
    )

  def test_ohlc_window_uses_lowercase_keys(
    self, tmp_path, monkeypatch,
  ) -> None:
    '''D-17: ohlc_window keys are lowercase low/high/close.
    Eval reads ohlc_window[-1][\'low\'] etc. Test exercises with explicit
    lowercase fixture and verifies correct state is produced.
    '''
    row = _open_row(stop_price=8100.0, last_alert_state=None)
    state = _make_state(paper_trades=[row])
    # Explicitly set lowercase ohlc_window
    state['signals']['SPI200']['ohlc_window'] = [
      {'date': '2026-04-30', 'open': 8000.0, 'high': 8200.0, 'low': 8120.0, 'close': 8150.0},
    ]
    # low=8120 > stop=8100; close=8150; abs(8150-8100)=50 > 0.5*50=25 -> CLEAR
    state['signals']['SPI200']['indicator_scalars'] = {'atr': 50.0}
    p = _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr('notifier.send_stop_alert_email', lambda t, u: True)
    result = main._evaluate_paper_trade_alerts(state, 'http://x')
    # low=8120 > stop=8100 -> NOT HIT; close far -> CLEAR -> None->CLEAR -> no-op write
    assert result['transitions'] == []
    saved = json.loads(p.read_text())
    assert saved['paper_trades'][0]['last_alert_state'] == 'CLEAR'

  def test_two_phase_commit_ordering_no_deadlock(
    self, tmp_path, monkeypatch,
  ) -> None:
    '''D-18 deadlock guard: function completes within 5s (deadlock would block).
    Uses real mutate_state with file-backed state (not a mock).
    '''
    import signal as _signal
    row = _open_row(stop_price=8100.0, last_alert_state=None)
    state = _make_state(paper_trades=[row], spi_close=8120.0, spi_low=8050.0, spi_atr=50.0)
    _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr('notifier.send_stop_alert_email', lambda t, u: True)

    import threading
    result_holder = []
    def _run():
      result_holder.append(
        main._evaluate_paper_trade_alerts(state, 'http://x')
      )

    t = threading.Thread(target=_run)
    t.start()
    t.join(timeout=5.0)
    assert not t.is_alive(), (
      'D-18: _evaluate_paper_trade_alerts must complete within 5s (deadlock check)'
    )
    assert result_holder, 'Function must return a result'

  def test_returns_dict_with_transitions_and_emailed_keys(
    self, tmp_path, monkeypatch,
  ) -> None:
    '''Return dict has exactly the two keys: transitions (list) and emailed (bool).'''
    state = _make_state(paper_trades=[])
    _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('notifier.send_stop_alert_email', lambda t, u: True)

    result = main._evaluate_paper_trade_alerts(state, 'http://x')
    assert set(result.keys()) == {'transitions', 'emailed'}
    assert isinstance(result['transitions'], list)
    assert isinstance(result['emailed'], bool)

  def test_transitions_payload_shape(self, tmp_path, monkeypatch) -> None:
    '''Each transition dict has keys: id, instrument, side, entry_price,
    stop_price, today_close, atr_distance, new_state, old_state.
    '''
    row = _open_row(stop_price=8100.0, last_alert_state=None)
    state = _make_state(paper_trades=[row], spi_close=8120.0, spi_low=8050.0, spi_atr=50.0)
    _seed_state_file(tmp_path, state)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr('notifier.send_stop_alert_email', lambda t, u: True)
    result = main._evaluate_paper_trade_alerts(state, 'http://x')
    assert len(result['transitions']) == 1
    t = result['transitions'][0]
    expected_keys = {'id', 'instrument', 'side', 'entry_price', 'stop_price',
                     'today_close', 'atr_distance', 'new_state', 'old_state'}
    assert set(t.keys()) == expected_keys, (
      f'Transition dict must have keys {expected_keys}; got {set(t.keys())}'
    )
