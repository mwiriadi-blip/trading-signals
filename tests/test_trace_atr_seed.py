"""Tests for Phase 29 Plan 11: ATR seed exposure in trace panel.

Covers:
  - atr_seed_for_window returns a finite float for valid inputs
  - hand-recalc Wilder forward from seed converges to engine ATR within 1e-6
  - legacy sig_dict (missing atr_seed) renders stale-row fallback without crash
  - sig_dict with explicit atr_seed renders the value and label in HTML
"""
import math

import numpy as np
import pandas as pd
import pytest

import signal_engine
from dashboard_legacy.trace_panels import _render_trace_panels


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_ohlc_df(n: int) -> pd.DataFrame:
    """Deterministic ramp OHLC — avoids random drift in test values."""
    close = np.linspace(100.0, 100.0 + n * 0.5, n)
    high = close + 1.0
    low = close - 1.0
    return pd.DataFrame(
        {'High': high, 'Low': low, 'Close': close, 'Open': close - 0.25},
        index=pd.date_range('2025-01-01', periods=n, freq='B'),
    )


def _make_sig_dict(atr_seed_val=None, include_key=True) -> dict:
    """Minimal sig_dict for _render_trace_panels."""
    d = {
        'ohlc_window': [
            {'date': '2025-01-01', 'open': 100.0, 'high': 101.0,
             'low': 99.0, 'close': 100.5}
        ],
        'indicator_scalars': {
            'tr': 2.0, 'atr': 1.5, 'plus_di': 30.0, 'minus_di': 20.0,
            'adx': 28.0, 'mom1': 0.03, 'mom3': 0.04, 'mom12': 0.05,
            'rvol': 0.12,
        },
        'signal': 0,
        'vote_params': None,
    }
    if include_key:
        d['atr_seed'] = atr_seed_val
    return d


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAtrSeedExposure:

    def test_atr_seed_persisted_in_signal_row(self):
        """atr_seed_for_window returns a finite float for a valid mid-history index.

        window_start_index=20 => seed_bar_idx=19, which is past the 14-bar
        Wilder warmup (first non-NaN at bar 13), so the seed must be finite.
        """
        df = _make_ohlc_df(50)
        seed = signal_engine.atr_seed_for_window(df, 20)
        assert isinstance(seed, float)
        assert math.isfinite(seed), f"Expected finite seed, got {seed}"
        assert seed > 0.0

    def test_handcalc_converges_to_displayed_atr_within_1e6(self):
        """Hand-recalc Wilder forward from the seed must match engine ATR within 1e-6.

        Setup: 50-bar deterministic ramp.
        window_start_index=15 => seed_bar_idx=14, past the 14-bar warmup.
        The engine ATR at bar 49 is computed via compute_indicators.
        The seed is ATR at bar 14 (= window_start_index - 1).
        Hand-recalc: run Wilder from bar 15 to bar 49 using engine seed.
        """
        df = _make_ohlc_df(50)
        # Engine's full-history ATR series
        df_ind = signal_engine.compute_indicators(df)
        engine_atr_final = float(df_ind['ATR'].iloc[-1])

        # Seed at bar 14 (window_start_index=15 => seed_bar_idx=14)
        window_start_index = 15
        seed = signal_engine.atr_seed_for_window(df, window_start_index)
        assert math.isfinite(seed), "Seed must be finite for this fixture"

        # Compute TR for bars 15..49 manually
        close = df['Close'].to_numpy()
        high = df['High'].to_numpy()
        low = df['Low'].to_numpy()
        period = 14

        def _tr_bar(i):
            prev_c = close[i - 1] if i > 0 else float('nan')
            hl = high[i] - low[i]
            hc = abs(high[i] - prev_c) if not math.isnan(prev_c) else 0.0
            lc = abs(low[i] - prev_c) if not math.isnan(prev_c) else 0.0
            return max(hl, hc, lc)

        # Wilder forward from seed at bar window_start_index
        atr = seed
        for i in range(window_start_index, len(df)):
            tr_i = _tr_bar(i)
            atr = atr + (tr_i - atr) / period

        assert abs(atr - engine_atr_final) < 1e-6, (
            f"hand_recalc={atr:.10f} engine={engine_atr_final:.10f} "
            f"delta={abs(atr - engine_atr_final):.2e}"
        )

    def test_legacy_signal_row_renders_stale_message(self):
        """sig_dict missing atr_seed renders stale-row fallback without crash."""
        sig_dict = _make_sig_dict(include_key=False)
        rendered = _render_trace_panels(sig_dict, 'SPI200', '')
        assert 'stale row' in rendered
        assert '<em>' in rendered

    def test_trace_panel_renders_seed_value(self):
        """sig_dict with atr_seed=42.123456 renders value and ATR seed label."""
        sig_dict = _make_sig_dict(atr_seed_val=42.123456)
        rendered = _render_trace_panels(sig_dict, 'SPI200', '')
        assert '42.123456' in rendered
        assert 'ATR seed' in rendered
