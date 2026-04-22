'''Offline dashboard-HTML golden regenerator for Phase 5 tests.

Per CONTEXT D-14 (.planning/phases/05-dashboard/05-CONTEXT.md): this script
is NEVER invoked by CI. Run manually when the dashboard render
intentionally changes (CSS edit, palette tweak, new render block, etc.):

  .venv/bin/python tests/regenerate_dashboard_golden.py

Produces:
  - tests/fixtures/dashboard/golden.html        (committed reference of sample_state.json)
  - tests/fixtures/dashboard/golden_empty.html  (committed reference of empty_state.json)

Frozen clock: passes now=PERTH.localize(datetime(2026, 4, 22, 9, 0)) where
PERTH = pytz.timezone('Australia/Perth') (C-1 reviews: pytz timezones must
be applied via .localize(), not tzinfo=). Byte-identical output so that
TestGoldenSnapshot can diff bytes exactly.

Git-diff on the golden HTML files IS the design review surface: an
unintentional CSS / layout / palette drift surfaces as a diff in PR review.
'''
import json
import sys
from datetime import datetime
from pathlib import Path

import pytz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dashboard import render_dashboard  # noqa: E402, I001 — import after sys.path.insert

FIXTURES_DIR = ROOT / 'tests' / 'fixtures' / 'dashboard'
# C-1 reviews fix: PERTH.localize(...) is correct; tzinfo=PERTH is not.
PERTH = pytz.timezone('Australia/Perth')
FROZEN_NOW = PERTH.localize(datetime(2026, 4, 22, 9, 0))

SCENARIOS = [
  ('sample_state.json', 'golden.html'),
  ('empty_state.json', 'golden_empty.html'),
]


def regenerate_one(state_name: str, golden_name: str) -> None:
  '''Load state fixture, render with frozen clock, write golden HTML.'''
  state = json.loads((FIXTURES_DIR / state_name).read_text())
  out_path = FIXTURES_DIR / golden_name
  render_dashboard(state, out_path=out_path, now=FROZEN_NOW)
  print(f'[regen] wrote {golden_name} ({out_path.stat().st_size} bytes)')


def main() -> None:
  FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
  for state_name, golden_name in SCENARIOS:
    regenerate_one(state_name, golden_name)


if __name__ == '__main__':
  main()
