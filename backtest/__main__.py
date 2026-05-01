"""Phase 23 — enables `python -m backtest`. Dispatches to backtest.cli.main()."""
from backtest.cli import main

if __name__ == '__main__':
  raise SystemExit(main())
