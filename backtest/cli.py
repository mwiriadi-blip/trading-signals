"""Phase 23 — argparse CLI for `python -m backtest`.

Surface (CONTEXT D-11):
  --years (default 5), --end-date YYYY-MM-DD, --initial-account 10000,
  --cost-spi 6.0, --cost-audusd 5.0, --refresh, --output PATH

Log prefix: [Backtest] — NEW per CLAUDE.md log-prefix convention + CONTEXT D-11.
Exit codes: 0 = PASS (cumulative_return_pct > 100), 1 = FAIL.
"""
from __future__ import annotations


def main(argv: list[str] | None = None) -> int:
  raise NotImplementedError('Phase 23 Wave 2 Plan 06 — to be implemented')
