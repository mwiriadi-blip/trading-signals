'''Phase 22 D-08 — STRATEGY-CHANGELOG.md structure guard.

Pins the file's existence + section count + ordering + constants block.
Mirrors tests/test_setup_droplet_doc.py as a doc-content-test precedent.
'''
import re
from pathlib import Path

import pytest

CHANGELOG_PATH = Path('docs/STRATEGY-CHANGELOG.md')


@pytest.fixture(scope='module')
def changelog_text() -> str:
  assert CHANGELOG_PATH.exists(), f'doc missing: {CHANGELOG_PATH}'
  return CHANGELOG_PATH.read_text()


class TestStrategyChangelog:
  '''Phase 22 D-08: docs/STRATEGY-CHANGELOG.md exists, lists three honest
  versioned sections newest-first, and the v1.2.0 entry pins the constants
  block from CONTEXT D-08.
  '''

  def test_changelog_file_exists(self, changelog_text) -> None:
    '''D-08: docs/STRATEGY-CHANGELOG.md is committed at the repo path.'''
    assert CHANGELOG_PATH.is_file(), (
      f'Phase 22 D-08: {CHANGELOG_PATH} must exist'
    )

  def test_changelog_has_three_versioned_sections(self, changelog_text) -> None:
    '''D-08: exactly three "## v" H2 sections — v1.2.0, v1.1.0, v1.0.0.'''
    headings = [
      line for line in changelog_text.splitlines()
      if line.startswith('## v')
    ]
    assert len(headings) == 3, (
      f'D-08: expected exactly 3 "## v" sections; got {len(headings)}: '
      f'{headings!r}'
    )
    for tag in ('## v1.2.0', '## v1.1.0', '## v1.0.0'):
      assert any(line.startswith(tag) for line in headings), (
        f'D-08: missing section heading starting with {tag!r}; '
        f'headings={headings!r}'
      )

  def test_changelog_versions_appear_in_descending_order(
      self, changelog_text) -> None:
    '''D-08: newest first — v1.2.0, v1.1.0, v1.0.0 in that order.'''
    versions: list[str] = []
    for line in changelog_text.splitlines():
      m = re.match(r'^## (v\d+\.\d+\.\d+)\b', line)
      if m:
        versions.append(m.group(1))
    assert versions == ['v1.2.0', 'v1.1.0', 'v1.0.0'], (
      f'D-08: version ordering must be newest-first; got {versions!r}'
    )

  def test_changelog_v1_2_0_lists_constants(self, changelog_text) -> None:
    '''D-08: the v1.2.0 entry pins the constants block — pinning these
    strings means a future bump that omits them surfaces in CI.
    '''
    # Slice out the v1.2.0 section (between ## v1.2.0 and the next ## v).
    section_match = re.search(
      r'^## v1\.2\.0\b.*?(?=^## v|\Z)',
      changelog_text,
      flags=re.DOTALL | re.MULTILINE,
    )
    assert section_match is not None, (
      'D-08: ## v1.2.0 section not found in changelog'
    )
    section = section_match.group(0)
    for required in (
      'ATR_PERIOD = 14',
      'ADX_PERIOD = 20',
      'ADX_GATE_THRESHOLD = 25',
      'MOM_PERIODS = [1, 3, 12]',
      'RVOL_PERIOD = 20',
      'POSITION_SIZE_PCT_LONG = 0.01',
      'POSITION_SIZE_PCT_SHORT = 0.005',
      'TRAILING_STOP_ATR_MULTIPLIER = 3.0',
    ):
      assert required in section, (
        f'D-08: v1.2.0 section must list constant {required!r}; '
        f'not found in section'
      )
