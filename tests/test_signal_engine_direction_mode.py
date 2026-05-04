import pandas as pd

import signal_engine


def _frame(adx: float, mom1: float, mom3: float, mom12: float) -> pd.DataFrame:
  return pd.DataFrame(
    {
      'ADX': [adx],
      'Mom1': [mom1],
      'Mom3': [mom3],
      'Mom12': [mom12],
    }
  )


def test_get_signal_long_only_blocks_short_votes() -> None:
  df = _frame(adx=50.0, mom1=-1.0, mom3=-1.0, mom12=0.1)
  got = signal_engine.get_signal(df, settings={'direction_mode': 'long_only'})
  assert got == signal_engine.FLAT


def test_get_signal_short_only_blocks_long_votes() -> None:
  df = _frame(adx=50.0, mom1=1.0, mom3=1.0, mom12=-0.1)
  got = signal_engine.get_signal(df, settings={'direction_mode': 'short_only'})
  assert got == signal_engine.FLAT


def test_get_signal_both_mode_keeps_existing_behavior() -> None:
  df = _frame(adx=50.0, mom1=1.0, mom3=1.0, mom12=0.1)
  got = signal_engine.get_signal(df, settings={'direction_mode': 'both'})
  assert got == signal_engine.LONG
