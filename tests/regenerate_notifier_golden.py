'''Offline email-HTML golden regenerator for Phase 6 tests.

Per CONTEXT D-03 (Phase 6 follows Phase 5 pattern): this script is
NEVER invoked by CI. Run manually when the email render intentionally
changes (palette edit, new section, formatter tweak, etc.):

  .venv/bin/python tests/regenerate_notifier_golden.py

Produces:
  - tests/fixtures/notifier/golden_with_change.html (byte-equal reference)
  - tests/fixtures/notifier/golden_no_change.html
  - tests/fixtures/notifier/golden_empty.html

Frozen clock: passes now=PERTH.localize(datetime(2026, 4, 22, 9, 0))
where PERTH = pytz.timezone('Australia/Perth') (C-1 reviews: pytz
timezones must be applied via .localize(), not tzinfo=). Byte-identical
output so that TestGoldenEmail can diff bytes exactly.

Git-diff on the golden HTML files IS the design review surface: an
unintentional CSS / layout / palette drift surfaces as a diff in PR
review.

Wave 0 (this commit): script exists but notifier.compose_email_body is
a NotImplementedError stub — running this script raises until Wave 1.
Wave 2 fills the render path; double-run idempotency is the phase gate.
'''
import json
import sys
from datetime import datetime
from pathlib import Path

import pytz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from notifier import compose_email_body  # noqa: E402, I001 — import after sys.path.insert

FIXTURES_DIR = ROOT / 'tests' / 'fixtures' / 'notifier'
# C-1 reviews fix: PERTH.localize(...) is correct; tzinfo=PERTH is not.
PERTH = pytz.timezone('Australia/Perth')
FROZEN_NOW = PERTH.localize(datetime(2026, 4, 22, 9, 0))

SCENARIOS = [
  ('sample_state_with_change.json', 'golden_with_change.html', {'^AXJO': 1, 'AUDUSD=X': 0}),
  ('sample_state_no_change.json', 'golden_no_change.html', {'^AXJO': 1, 'AUDUSD=X': 0}),
  ('empty_state.json', 'golden_empty.html', {'^AXJO': None, 'AUDUSD=X': None}),
]


def regenerate_one(state_name: str, golden_name: str, old_signals: dict) -> None:
  '''Load state fixture, render with frozen clock, write golden HTML.'''
  state = json.loads((FIXTURES_DIR / state_name).read_text())
  out_path = FIXTURES_DIR / golden_name
  html = compose_email_body(state, old_signals, FROZEN_NOW)
  out_path.write_text(html, encoding='utf-8', newline='\n')
  print(f'[regen] wrote {golden_name} ({out_path.stat().st_size} bytes)')


def main() -> None:
  FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
  for state_name, golden_name, old_signals in SCENARIOS:
    regenerate_one(state_name, golden_name, old_signals)


if __name__ == '__main__':
  main()
