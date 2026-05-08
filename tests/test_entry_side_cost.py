'''Phase 27 #7 — entry_side_cost helper + magic /2 grep gate.

Tests:
  test_entry_side_cost_halves_quantized — basic 5.00 -> 2.50.
  test_entry_side_cost_odd_cents — 5.01 -> 2.51 (HALF_UP rounding).
  test_no_magic_cost_div_in_prod — AST walker BinOp(Div, right=Constant(2))
    over `cost`-shaped left operands MUST be ZERO in production code.

Production scope (review-fix M3): pnl_engine, sizing_engine, notifier, main.
Test fixtures (tests/test_notifier.py:530, tests/test_backtest_simulator.py:84)
are intentionally untouched — those are docstring text inside test code.
'''
import ast
import pathlib
from decimal import Decimal

import pytest


def _notifier_pkg_files() -> list[str]:
  '''CR-01 fix: notifier.py monolith deleted; AST gate now walks every
  notifier/*.py file in the post-Plan 27-12 package layout.'''
  return [str(p) for p in sorted(pathlib.Path('notifier').glob('*.py'))]


PROD_FILES = [
  'pnl_engine.py',
  'sizing_engine.py',
  'main.py',
  *_notifier_pkg_files(),
]


# =========================================================================
# Helper unit tests
# =========================================================================

class TestEntrySideCost:
  '''Phase 27 #7: entry_side_cost(rt_cost) splits round-trip cost in half
  with HALF_UP rounding to AUD cents.'''

  def test_entry_side_cost_halves_quantized(self) -> None:
    '''5.00 round-trip -> 2.50 entry side. Decimal-typed return.'''
    from pnl_engine import entry_side_cost
    result = entry_side_cost(Decimal('5.00'))
    assert result == Decimal('2.50')
    assert isinstance(result, Decimal)

  def test_entry_side_cost_odd_cents(self) -> None:
    '''5.01 round-trip -> 2.51 entry side under HALF_UP (NOT banker's
    HALF_EVEN — display-intuition policy from Plan 27-01 AUD_ROUND).'''
    from pnl_engine import entry_side_cost
    result = entry_side_cost(Decimal('5.01'))
    assert result == Decimal('2.51')

  def test_entry_side_cost_zero(self) -> None:
    '''0 -> 0.00 (no edge-case crash).'''
    from pnl_engine import entry_side_cost
    assert entry_side_cost(Decimal('0')) == Decimal('0.00')

  def test_entry_side_cost_six_dollars(self) -> None:
    '''SPI mini round-trip $6 -> $3 entry side (canonical SPI200 case).'''
    from pnl_engine import entry_side_cost
    assert entry_side_cost(Decimal('6.00')) == Decimal('3.00')


# =========================================================================
# AST grep gate — magic /2 elimination
# =========================================================================

def _is_cost_div_two(node: ast.AST) -> bool:
  '''Match BinOp(left=cost-shaped, op=Div, right=Constant(2)).

  Left-operand shapes recognised:
    Name        — `cost_aud / 2`, `cost_open / 2`, etc. (substring 'cost').
    Subscript   — `resolved['cost_aud'] / 2`, `state['cost_aud'] / 2`.
    Attribute   — `resolved.cost_aud / 2`.
  '''
  if not isinstance(node, ast.BinOp):
    return False
  if not isinstance(node.op, ast.Div):
    return False
  left = node.left
  left_ok = False
  if isinstance(left, ast.Name) and 'cost' in left.id.lower():
    left_ok = True
  elif isinstance(left, ast.Subscript):
    slc = left.slice
    if isinstance(slc, ast.Constant) and isinstance(slc.value, str) and 'cost' in slc.value.lower():
      left_ok = True
  elif isinstance(left, ast.Attribute) and 'cost' in left.attr.lower():
    left_ok = True
  if not left_ok:
    return False
  right = node.right
  return isinstance(right, ast.Constant) and right.value == 2


@pytest.mark.parametrize('path', PROD_FILES)
def test_no_magic_cost_div_in_prod(path: str) -> None:
  '''AST walker — zero `cost-something / 2` BinOps in production code.

  All such sites must use pnl_engine.entry_side_cost(rt_cost). Test fixtures
  in tests/ are out of scope and untouched.
  '''
  tree = ast.parse(pathlib.Path(path).read_text(encoding='utf-8'))
  hits: list[str] = []
  for node in ast.walk(tree):
    if _is_cost_div_two(node):
      hits.append(f'{path}:{node.lineno}')
  assert not hits, (
    f'Phase 27 #7: magic `cost / 2` literal found in production code — '
    f'replace with entry_side_cost(rt_cost). Hits: {hits}'
  )
