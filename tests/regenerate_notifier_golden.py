'''Offline email-HTML golden regenerator for Phase 6 tests.

Per CONTEXT D-03 (Phase 6 follows Phase 5 pattern): this script is
NEVER invoked by CI. Run manually when the email render intentionally
changes (palette edit, new section, formatter tweak, etc.):

  .venv/bin/python tests/regenerate_notifier_golden.py

Produces 6 output files per invocation:
  - tests/fixtures/notifier/golden_with_change.html (byte-equal body)
  - tests/fixtures/notifier/golden_with_change_subject.txt (Fix 8 subject)
  - tests/fixtures/notifier/golden_no_change.html
  - tests/fixtures/notifier/golden_no_change_subject.txt
  - tests/fixtures/notifier/golden_empty.html
  - tests/fixtures/notifier/golden_empty_subject.txt

Frozen clock: passes now=PERTH.localize(datetime(2026, 4, 22, 9, 0))
where PERTH = pytz.timezone('Australia/Perth') (C-1 reviews: pytz
timezones must be applied via .localize(), not tzinfo=). Byte-identical
output so that TestGoldenEmail can diff bytes exactly.

Git-diff on the golden files IS the design review surface: an
unintentional CSS / layout / palette / subject drift surfaces as a diff
in PR review.

Double-run idempotency is the Wave 2 phase gate — running this script
twice in a row produces zero git diff on tests/fixtures/notifier/.

Wave 2 (06-03): compose_email_subject + compose_email_body are fully
implemented; this script now produces the committed goldens. Fix 8
per REVIEWS.md: subject .txt goldens committed alongside HTML bodies.
'''
import json
import sys
from datetime import datetime
from pathlib import Path

import pytz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from notifier import (  # noqa: E402, I001 — import after sys.path.insert
  compose_email_body,
  compose_email_subject,
)

FIXTURES_DIR = ROOT / 'tests' / 'fixtures' / 'notifier'
# C-1 reviews fix: PERTH.localize(...) is correct; tzinfo=PERTH is not.
PERTH = pytz.timezone('Australia/Perth')
FROZEN_NOW = PERTH.localize(datetime(2026, 4, 22, 9, 0))

SCENARIOS = [
  ('sample_state_with_change.json', 'golden_with_change', {'^AXJO': 1, 'AUDUSD=X': 0}),
  ('sample_state_no_change.json', 'golden_no_change', {'^AXJO': 1, 'AUDUSD=X': 0}),
  ('empty_state.json', 'golden_empty', {'^AXJO': None, 'AUDUSD=X': None}),
]


def regenerate_one(state_name: str, golden_stem: str, old_signals: dict) -> None:
  '''Load state fixture, render with frozen clock, write both body + subject goldens.

  Writes 2 files per scenario:
    - {golden_stem}.html — full HTML body (byte-equal gate)
    - {golden_stem}_subject.txt — single-line subject + trailing '\\n' (Fix 8)
  '''
  state = json.loads((FIXTURES_DIR / state_name).read_text())

  # Body HTML
  body_path = FIXTURES_DIR / f'{golden_stem}.html'
  html = compose_email_body(state, old_signals, FROZEN_NOW)
  body_path.write_text(html, encoding='utf-8', newline='\n')
  print(f'[regen] wrote {body_path.name} ({body_path.stat().st_size} bytes)')

  # Fix 8: subject .txt golden (single-line UTF-8 + trailing \n for POSIX).
  subject_path = FIXTURES_DIR / f'{golden_stem}_subject.txt'
  subject = compose_email_subject(state, old_signals, is_test=False)
  subject_path.write_text(subject + '\n', encoding='utf-8', newline='\n')
  print(
    f'[regen] wrote {subject_path.name} ({subject_path.stat().st_size} bytes)',
  )


def main() -> None:
  FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
  for state_name, golden_stem, old_signals in SCENARIOS:
    regenerate_one(state_name, golden_stem, old_signals)


if __name__ == '__main__':
  main()
