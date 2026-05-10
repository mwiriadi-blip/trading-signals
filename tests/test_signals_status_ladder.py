'''Regression suite for commit da31412 — trigger ladder + trailing-stop line.

Phase 29 plan 29-03 (DEBT-02). Locks: Signal Status card renders trigger ladder
+ trailing-stop line per dashboard_renderer/components/signals.py, which was
added in commit da31412.

Tests:
- test_status_card_includes_trigger_ladder: FLAT signal shows trigger-ladder block
- test_status_card_includes_trailing_stop_line: trailing-stop line rendered
- test_status_card_no_ladder_for_flat_with_adx_pass: minimal ladder when ADX already passes
- test_status_card_no_ladder_for_long_signal: no triggers shown for active LONG
- test_trigger_ladder_shows_adx_gap: trigger text names ADX shortfall distance
- test_trailing_stop_line_shows_hypothetical_for_flat_signal: labelled "(if LONG ...)"
'''

import pytest


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_state(
    signal: int = 0,
    adx: float = 15.0,
    mom1: float = 0.025,
    mom3: float = 0.030,
    mom12: float = 0.028,
    adx_gate: float = 20.0,
    with_position: bool = False,
) -> dict:
    '''Minimal state dict for Signal Status card rendering.

    Defaults: SPI200 FLAT with ADX below gate and 3 positive mom votes, so a
    trigger ladder is expected (ADX gate not met).
    '''
    scalars = {
        'adx': adx,
        'atr': 50.0,
        'mom1': mom1,
        'mom3': mom3,
        'mom12': mom12,
        'rvol': 1.1,
        'pdi': 20.0,
        'ndi': 15.0,
    }
    vote_params = {
        'adx_gate': adx_gate,
        'momentum_threshold': 0.02,
        'momentum_votes_required': 2,
        'direction_mode': 'both',
    }
    signal_entry = {
        'signal': signal,
        'signal_as_of': '2026-05-10',
        'last_close': 8000.0,
        'last_scalars': scalars,
        'vote_params': vote_params,
        'ohlc_window': [],
        'indicator_scalars': scalars,
    }
    positions = {'SPI200': None, 'AUDUSD': None}
    if with_position:
        positions['SPI200'] = {
            'atr_entry': 50.0,
            'direction': 'LONG',
            'entry_date': '2026-05-01',
            'entry_price': 7800.0,
            'n_contracts': 1,
            'peak_price': 8050.0,
            'pyramid_level': 0,
            'trough_price': None,
            'manual_stop': None,
        }
    return {
        'account': 10000.0,
        'equity_history': [{'date': '2026-05-01', 'equity': 10000.0}],
        'last_run': '2026-05-10',
        'positions': positions,
        'schema_version': 11,
        'signals': {
            'SPI200': signal_entry,
            'AUDUSD': {
                'signal': 0,
                'signal_as_of': '2026-05-10',
                'last_close': 0.65,
                'last_scalars': {
                    'adx': 10.0, 'atr': 0.004,
                    'mom1': 0.001, 'mom3': 0.001, 'mom12': 0.001,
                    'rvol': 0.9, 'pdi': 12.0, 'ndi': 18.0,
                },
                'vote_params': vote_params,
                'ohlc_window': [],
                'indicator_scalars': {},
            },
        },
        'trade_log': [],
        'warnings': [],
    }


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestSignalStatusLadder:
    '''Regression suite for da31412 — trigger ladder + trailing-stop line.

    Tests verify that render_signal_cards() produces the two new UI elements
    introduced in da31412: the trigger-ladder paragraph (class="triggers") and
    the trailing-stop-line paragraph (class="stop-line").
    '''

    def _render(self, state: dict, market: str = 'SPI200') -> str:
        from dashboard_renderer.components.signals import render_signal_cards
        return render_signal_cards(state, active_market=market)

    def test_status_card_includes_trigger_ladder(self) -> None:
        '''FLAT signal with ADX below gate shows trigger-ladder block.

        da31412 adds a <p class="triggers">Triggers → LONG: ...</p> line under
        the scalars line when signal==0 (FLAT). Regression: if someone removes
        the _next_triggers call or the triggers_html assembly, this test fails.
        '''
        state = _make_state(signal=0, adx=15.0, adx_gate=20.0)
        html = self._render(state)
        assert 'class="triggers"' in html, (
            'da31412: trigger-ladder <p class="triggers"> must appear in '
            'Signal Status card when FLAT + ADX below gate'
        )
        assert 'Triggers' in html, (
            'da31412: trigger paragraph must contain "Triggers" label'
        )

    def test_status_card_includes_trailing_stop_line(self) -> None:
        '''FLAT signal with positive votes shows trailing-stop-line block.

        da31412 adds a <p class="stop-line">Stop ...</p> line. When FLAT and
        momentum votes lean LONG, a hypothetical stop is shown.
        '''
        state = _make_state(
            signal=0, adx=15.0, adx_gate=20.0,
            mom1=0.025, mom3=0.030, mom12=0.028,
        )
        html = self._render(state)
        assert 'class="stop-line"' in html, (
            'da31412: trailing-stop-line <p class="stop-line"> must appear in '
            'Signal Status card when FLAT with positive momentum votes'
        )

    def test_status_card_no_ladder_for_long_signal(self) -> None:
        '''Active LONG signal: trigger ladder NOT rendered (only shown for FLAT).

        Per _next_triggers: returns [] when signal_int != 0. Regression:
        if the guard is removed, active signals would show spurious triggers.
        '''
        state = _make_state(signal=1, adx=25.0, adx_gate=20.0)
        html = self._render(state)
        assert 'class="triggers"' not in html, (
            'da31412: trigger ladder must NOT appear when signal=LONG (da31412 '
            'only shows triggers when FLAT)'
        )

    def test_trigger_ladder_shows_adx_gap(self) -> None:
        '''Trigger text includes ADX gap text when ADX is below gate.

        The _next_triggers helper formats the ADX gap as "+N.N" in the output.
        '''
        state = _make_state(signal=0, adx=15.0, adx_gate=20.0)
        html = self._render(state)
        # ADX gap: 20.0 - 15.0 = 5.0; ladder line contains "+5.0"
        assert '+5.0' in html, (
            'da31412: trigger ladder must show ADX gap "+5.0" when ADX=15.0 gate=20.0'
        )
        assert 'ADX' in html, (
            'da31412: trigger ladder must name the ADX gate condition'
        )

    def test_trailing_stop_line_shows_hypothetical_label_for_flat_signal(self) -> None:
        '''Hypothetical stop for FLAT signal is labelled "(if LONG @ ...)" or
        "(if SHORT @ ...)" to distinguish from a real open-position stop.

        da31412 adds this explicit labelling via _signal_card_stop(). Without
        an open position the stop is always hypothetical.
        '''
        state = _make_state(
            signal=0, adx=15.0, adx_gate=20.0,
            mom1=0.025, mom3=0.030, mom12=0.028,
        )
        html = self._render(state)
        assert 'if LONG' in html or 'if SHORT' in html, (
            'da31412: hypothetical stop line must include "if LONG" or '
            '"if SHORT" label for a FLAT signal'
        )

    def test_status_card_no_stop_line_when_no_scalars(self) -> None:
        '''Without scalars (first-run state) no stop-line is rendered.

        Defensive: render_signal_cards must not crash when last_scalars is empty.
        '''
        from dashboard_renderer.components.signals import render_signal_cards
        state = _make_state(signal=0)
        state['signals']['SPI200']['last_scalars'] = {}
        state['signals']['SPI200']['indicator_scalars'] = {}
        html = render_signal_cards(state, active_market='SPI200')
        assert 'class="stop-line"' not in html
