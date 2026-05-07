'''Phase 27 #8 — instrument regex tightening regression suite.

Two-layer policy (review-fix agreed-8):

  Layer 1 — syntax (INSTRUMENT_ID_RE):
    ^[A-Z0-9_]{2,20}$ — validates that the input LOOKS like a market id.
    SPI200X is syntactically valid (passes), but is NOT one we support.

  Layer 2 — semantics (KNOWN_MARKET_IDS):
    frozenset({'SPI200', 'AUDUSD'}) — validates that the input IS one
    we actually support. is_known_market(id) is the public API.

Threat model: T-27-04-01 (tampering — `/markets/SPI200X/signals` would
trigger a state lookup with a too-loose regex). The two layers together
prevent both syntax-injection (Layer 1) AND extension attacks like
'SPI200X' that pass any generic id syntax check (Layer 2).

Hex-boundary: tests/ may import production modules (system_params,
web/routes/...) but must NOT mutate on-disk state. The AST walker reads
source text only.
'''
import ast
import pathlib

import pytest

from system_params import (
  INSTRUMENT_ID_RE,
  KNOWN_MARKET_IDS,
  is_known_market,
)


# =========================================================================
# Layer 1 — INSTRUMENT_ID_RE syntax tests (5 cases)
# =========================================================================


class TestInstrumentIdRegexSyntax:
  '''^[A-Z0-9_]{2,20}$ — what counts as syntactically valid.'''

  def test_instrument_id_re_accepts_known_syntax(self) -> None:
    '''SPI200, AUDUSD, AUD_USD, A1, 20-char string all match.'''
    assert INSTRUMENT_ID_RE.fullmatch('SPI200')
    assert INSTRUMENT_ID_RE.fullmatch('AUDUSD')
    assert INSTRUMENT_ID_RE.fullmatch('AUD_USD')
    assert INSTRUMENT_ID_RE.fullmatch('A1')
    assert INSTRUMENT_ID_RE.fullmatch('ABCDEFGHIJKLMNOPQRST')  # 20 chars

  def test_instrument_id_re_rejects_too_short(self) -> None:
    '''Single-char ids are below the minimum length of 2.'''
    assert not INSTRUMENT_ID_RE.fullmatch('A')
    assert not INSTRUMENT_ID_RE.fullmatch('')

  def test_instrument_id_re_rejects_too_long(self) -> None:
    '''21-char ids exceed the upper bound of 20.'''
    assert not INSTRUMENT_ID_RE.fullmatch('A' * 21)
    assert not INSTRUMENT_ID_RE.fullmatch('A' * 100)

  def test_instrument_id_re_rejects_lowercase(self) -> None:
    '''All-uppercase only — lowercase letters are rejected.'''
    assert not INSTRUMENT_ID_RE.fullmatch('spi200')
    assert not INSTRUMENT_ID_RE.fullmatch('SpI200')
    assert not INSTRUMENT_ID_RE.fullmatch('audusd')

  def test_instrument_id_re_rejects_special_chars(self) -> None:
    '''Hyphens, slashes, spaces, dots, control chars all rejected.'''
    assert not INSTRUMENT_ID_RE.fullmatch('SPI-200')
    assert not INSTRUMENT_ID_RE.fullmatch('SPI/200')
    assert not INSTRUMENT_ID_RE.fullmatch('SPI 200')
    assert not INSTRUMENT_ID_RE.fullmatch('SPI.200')
    assert not INSTRUMENT_ID_RE.fullmatch('SPI200\n')
    assert not INSTRUMENT_ID_RE.fullmatch('SPI200\x00')


# =========================================================================
# Two-layer policy proof (review-fix agreed-8)
# =========================================================================


class TestTwoLayerPolicy:
  '''Codex-correct critique: a permissive ^[A-Z0-9_]{2,20}$ regex CANNOT
  reject 'SPI200X' on its own. Only membership can. These two tests
  prove the layers are doing different jobs.
  '''

  def test_instrument_id_re_accepts_extension_attack_syntactically(self) -> None:
    '''SPI200X passes the syntax regex — the regex is generic by design.

    This is NOT a bug — it is the explicit reason KNOWN_MARKET_IDS exists.
    A regex tightened to literally match 'SPI200|AUDUSD' would couple
    syntax to semantics and force regex changes on every market add.
    '''
    assert INSTRUMENT_ID_RE.fullmatch('SPI200X')  # syntactically valid
    assert INSTRUMENT_ID_RE.fullmatch('AUDUSDEVIL')  # syntactically valid

  def test_is_known_market_rejects_extension_attack(self) -> None:
    '''The membership layer is what actually rejects 'SPI200X'.'''
    assert is_known_market('SPI200X') is False
    assert is_known_market('AUDUSDEVIL') is False


# =========================================================================
# Layer 2 — is_known_market semantics tests
# =========================================================================


class TestIsKnownMarket:
  '''Public API for "is this an actual supported market?"'''

  def test_is_known_market_accepts_real_markets(self) -> None:
    '''Both canonical defaults pass.'''
    assert is_known_market('SPI200') is True
    assert is_known_market('AUDUSD') is True

  def test_is_known_market_rejects_garbage_syntax(self) -> None:
    '''Inputs that fail Layer 1 also fail Layer 2 (short-circuit).'''
    assert is_known_market('foo bar') is False
    assert is_known_market('spi200') is False
    assert is_known_market('') is False
    assert is_known_market('SPI-200') is False

  def test_is_known_market_handles_non_string_input(self) -> None:
    '''Non-string inputs return False, never raise — defensive at boundary.'''
    assert is_known_market(None) is False
    assert is_known_market(123) is False  # type: ignore[arg-type]
    assert is_known_market(['SPI200']) is False  # type: ignore[arg-type]


# =========================================================================
# KNOWN_MARKET_IDS shape contract
# =========================================================================


class TestKnownMarketIdsShape:
  '''The membership set is a frozenset of strings — immutable + hashable.'''

  def test_known_market_ids_is_frozenset(self) -> None:
    assert isinstance(KNOWN_MARKET_IDS, frozenset)

  def test_known_market_ids_contains_canonical_defaults(self) -> None:
    assert 'SPI200' in KNOWN_MARKET_IDS
    assert 'AUDUSD' in KNOWN_MARKET_IDS

  def test_known_market_ids_entries_pass_syntax_layer(self) -> None:
    '''Every entry MUST satisfy INSTRUMENT_ID_RE — invariant for the
    is_known_market short-circuit to be safe.'''
    for market_id in KNOWN_MARKET_IDS:
      assert INSTRUMENT_ID_RE.fullmatch(market_id), (
        f'KNOWN_MARKET_IDS member {market_id!r} fails INSTRUMENT_ID_RE — '
        'membership set must be a strict subset of syntax-valid ids.'
      )


# =========================================================================
# AST walker — production-source regression
# =========================================================================


# Production files that may compile instrument-id regexes. Files that do
# NOT exist yet (post-split + future plans) are silently skipped.
_PROD_FILES = [
  'dashboard.py',
  'main.py',
  'notifier.py',
  'state_manager.py',
  'auth_store.py',
  'data_fetcher.py',
  'web/routes/dashboard.py',
  'web/routes/markets.py',
  'web/routes/trades.py',
  'web/routes/paper_trades.py',
  'web/routes/backtest.py',
  'web/app.py',
]


def _is_suspicious_pattern(pat: str) -> bool:
  '''Return True if `pat` looks like an instrument-id regex but lacks
  start/end anchors.

  Heuristic — instrument-id regexes typically contain `[A-Z` or `[A-Z0-9`
  or a literal market alternation. A safe pattern is fully anchored with
  `^...$`. Unanchored matches let `SPI200evil` slip through downstream
  lookups (T-27-04-01).

  Whitelist exclusions:
    - Substitution placeholders like `{{...}}` (different domain — those
      are server-controlled bytes, not untrusted inputs).
  '''
  if '{{' in pat:
    return False
  has_az_class = '[A-Z' in pat
  if not has_az_class:
    return False
  # Must be anchored at both ends. Bytes literal `b'...'` and `rb'...'`
  # share the same anchor characters.
  has_start_anchor = pat.startswith('^') or pat.lstrip('(').startswith('^')
  has_end_anchor = pat.endswith('$') or pat.rstrip(')').endswith('$')
  return not (has_start_anchor and has_end_anchor)


class TestNoUnanchoredInstrumentRegexInProd:
  '''AST walker prevents future drift — a future change that introduces
  an unanchored `[A-Z]{2,20}` match would fail this test.

  Behavioral, not literal: we search for any re.compile / re.match /
  re.search / re.fullmatch / re.sub call whose first positional argument
  is a string literal containing `[A-Z` and lacking `^...$` anchors.
  '''

  def test_no_unanchored_instrument_regex_in_prod(self) -> None:
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    offenders: list[str] = []
    for rel in _PROD_FILES:
      path = repo_root / rel
      if not path.exists():
        continue
      tree = ast.parse(path.read_text(), filename=str(path))
      for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
          continue
        if not isinstance(node.func, ast.Attribute):
          continue
        if not isinstance(node.func.value, ast.Name):
          continue
        if node.func.value.id != 're':
          continue
        if node.func.attr not in {'compile', 'match', 'search', 'fullmatch', 'sub'}:
          continue
        if not node.args:
          continue
        first = node.args[0]
        if not isinstance(first, ast.Constant):
          continue
        val = first.value
        if isinstance(val, bytes):
          try:
            val = val.decode('ascii')
          except UnicodeDecodeError:
            continue
        if not isinstance(val, str):
          continue
        if _is_suspicious_pattern(val):
          offenders.append(f'{rel}:{node.lineno}: unanchored pattern {val!r}')
    assert not offenders, (
      'Unanchored instrument-id regexes found:\n  ' + '\n  '.join(offenders)
    )


# =========================================================================
# Pydantic Field(pattern=...) regression — text scan
# =========================================================================


class TestPydanticInstrumentPatternsAnchored:
  '''Every Pydantic Field(pattern=r'...') matching an instrument id
  MUST be anchored with ^...$. Today the canonical pattern in
  web/routes/markets.py + trades.py is r'^[A-Z0-9_]{2,20}$'.

  Source-text scan (not AST) because Field(pattern=) is a kwarg literal
  and `re` is never invoked there — AST walker over `re.*` calls misses
  it. False positives tolerable; false negatives are the threat.
  '''

  def test_pydantic_instrument_field_patterns_are_anchored(self) -> None:
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    offenders: list[str] = []
    for rel in _PROD_FILES:
      path = repo_root / rel
      if not path.exists():
        continue
      for lineno, line in enumerate(path.read_text().splitlines(), 1):
        # Look for Field(pattern=r'...') or Field(... pattern=r'...').
        if 'pattern=r' not in line and 'pattern = r' not in line:
          continue
        # Extract the literal between the first r' and the closing '.
        # Naive but sufficient for the existing call-style.
        try:
          start = line.index("pattern=r'") + len("pattern=r'")
        except ValueError:
          try:
            start = line.index('pattern=r"') + len('pattern=r"')
            end = line.index('"', start)
          except ValueError:
            continue
        else:
          end = line.index("'", start)
        pat = line[start:end]
        if '[A-Z' not in pat:
          continue
        if not (pat.startswith('^') and pat.endswith('$')):
          offenders.append(f'{rel}:{lineno}: unanchored Field pattern {pat!r}')
    assert not offenders, (
      'Unanchored Pydantic Field patterns found:\n  ' + '\n  '.join(offenders)
    )


# =========================================================================
# Funnel-through — INSTRUMENT_ID_RE imported by the canonical adapter
# =========================================================================


class TestSingleSourceOfTruth:
  '''system_params.INSTRUMENT_ID_RE is the canonical syntax pattern.
  web/routes/dashboard.py — which validates cookies and request paths
  on the read side — must funnel through it (or import-equivalent) so
  a future regex change happens in ONE place.

  We accept either:
    - import from system_params, OR
    - a literal mirror that exactly matches the canonical pattern.

  This test pins the literal mirror to system_params' source of truth.
  '''

  def test_web_dashboard_market_id_re_mirrors_system_params(self) -> None:
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    src = (repo_root / 'web/routes/dashboard.py').read_text()
    # The canonical pattern is the same string used by system_params.
    canonical = INSTRUMENT_ID_RE.pattern
    assert canonical in src, (
      f'web/routes/dashboard.py must contain the canonical pattern '
      f'{canonical!r} (either imported from system_params or mirrored '
      f'literally).'
    )

  def test_markets_route_field_pattern_mirrors_system_params(self) -> None:
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    src = (repo_root / 'web/routes/markets.py').read_text()
    canonical = INSTRUMENT_ID_RE.pattern
    assert canonical in src, (
      f'web/routes/markets.py must contain the canonical pattern '
      f'{canonical!r} on every instrument Field(pattern=...).'
    )

  def test_trades_route_field_pattern_mirrors_system_params(self) -> None:
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    src = (repo_root / 'web/routes/trades.py').read_text()
    canonical = INSTRUMENT_ID_RE.pattern
    assert canonical in src, (
      f'web/routes/trades.py must contain the canonical pattern '
      f'{canonical!r} on every instrument Field(pattern=...).'
    )
