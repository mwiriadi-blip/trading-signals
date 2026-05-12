'''Phase 27 Plan 27-09 (Wave 2B): bare-int signal back-compat removal.

Tests for the v9->v10 schema migration that promotes bare-int signal rows
(legacy Phase 3 reset_state shape) to dict shape with `signal` /
`strategy_version` keys. Also asserts the renderer's defensive
`isinstance(record, int)` branch is gone (signals.py:35-39).

Phase 26 DEBT.md R5 explicitly flagged this back-compat for removal.

Plan deviation (Rule 1 — plan vs reality): plan's <interfaces> block uses
`direction` as the field name; the actual production dict shape (see
main.py:1190 + signals.py:45 + sizing_engine.py:153) uses `signal`. This
test suite + the migrator track production shape, not the plan's stale
field name.
'''

import re
from pathlib import Path

import pytest


# --- Test 1 -----------------------------------------------------------------

class TestMigrateV9ToV10:
  '''_migrate_v9_to_v10 promotes bare-int signal rows to dict shape.'''

  def test_promotes_bare_int_to_dict(self) -> None:
    from state_manager import _migrate_v9_to_v10
    from system_params import STRATEGY_VERSION
    s = {
      'schema_version': 9,
      'signals': {'SPI200': 0, 'AUDUSD': 1},
    }
    out = _migrate_v9_to_v10(s)
    assert isinstance(out['signals']['SPI200'], dict), (
      'bare-int SPI200 must be promoted to dict'
    )
    assert isinstance(out['signals']['AUDUSD'], dict), (
      'bare-int AUDUSD must be promoted to dict'
    )
    # Use the production field name `signal` (NOT `direction` — plan deviation).
    assert out['signals']['SPI200']['signal'] == 0
    assert out['signals']['AUDUSD']['signal'] == 1
    assert out['signals']['SPI200']['strategy_version'] == STRATEGY_VERSION
    assert out['signals']['AUDUSD']['strategy_version'] == STRATEGY_VERSION

  def test_idempotent_on_already_dict(self) -> None:
    '''Already dict-shaped rows pass through unchanged (no overwrite).'''
    from state_manager import _migrate_v9_to_v10
    s = {
      'schema_version': 9,
      'signals': {
        'SPI200': {'signal': 1, 'strategy_version': 'v1.0.0', 'last_close': 7800.0},
      },
    }
    out_once = _migrate_v9_to_v10(s)
    out_twice = _migrate_v9_to_v10(out_once)
    # Dict-shaped row preserved verbatim — strategy_version NOT overwritten.
    assert out_once['signals']['SPI200']['strategy_version'] == 'v1.0.0'
    assert out_once['signals']['SPI200']['last_close'] == 7800.0
    assert out_once == out_twice, (
      f'idempotency: once={out_once!r} twice={out_twice!r}'
    )

  def test_negative_int_shape_short_signal_promoted(self) -> None:
    '''SHORT (-1) bare int is promoted to dict with signal=-1.'''
    from state_manager import _migrate_v9_to_v10
    s = {
      'schema_version': 9,
      'signals': {'SPI200': -1},
    }
    out = _migrate_v9_to_v10(s)
    assert isinstance(out['signals']['SPI200'], dict)
    assert out['signals']['SPI200']['signal'] == -1


# --- Test 2 -----------------------------------------------------------------

class TestRendererDefensiveIntBranchRemoved:
  '''Renderer's defensive `isinstance(sig_entry, int)` branch is gone.

  After the v10 migration runs at load_state, only dict-shaped signal rows
  reach the renderer. The defensive `elif isinstance(sig_entry, int):`
  block (signals.py:35-39 pre-removal) is dead code and must be deleted
  per truth #2.
  '''

  def test_no_isinstance_int_branch(self) -> None:
    src = Path('dashboard_renderer/components/signals.py').read_text(encoding='utf-8')
    # Strip Python comments + docstrings so a comment mentioning the
    # removed pattern doesn't false-positive. Quick approach: drop lines
    # whose stripped form starts with '#' and any triple-quoted string
    # contents (the file has only one tiny module docstring).
    code_lines = []
    in_triple = False
    triple_marker = None
    for line in src.splitlines():
      stripped = line.lstrip()
      if not in_triple:
        # detect triple-quote start
        for q in ("'''", '"""'):
          if stripped.startswith(q):
            in_triple = True
            triple_marker = q
            # single-line triple-quote (e.g. '''docstring''')?
            if stripped.count(q) >= 2:
              in_triple = False
              triple_marker = None
            break
        else:
          # not a docstring start — keep the code line, drop pure comments
          if not stripped.startswith('#'):
            code_lines.append(line)
        continue
      # in_triple — wait for closing marker
      if triple_marker in stripped:
        in_triple = False
        triple_marker = None
    code = '\n'.join(code_lines)
    assert not re.search(r'isinstance\s*\([^)]*\bint\b\s*\)', code), (
      'truth #2: dashboard_renderer/components/signals.py must not contain '
      'an `isinstance(..., int)` defensive branch — bare-int sig_entry '
      'should never reach the renderer post-v10 migration.'
    )


# --- Test 3 -----------------------------------------------------------------

class TestRendererRendersDictSignal:
  '''Renderer correctly handles dict-shaped signal entries (post-cleanup).'''

  def test_renders_dict_signal_long(self) -> None:
    from dashboard_renderer.components.signals import render_signal_cards
    state = {
      'last_run': '2026-05-08',
      'markets': {
        'SPI200': {
          'display_name': 'SPI 200',
          'enabled': True,
          'yf_symbol': '^AXJO',
          'data_provider': 'yfinance',
          'asset_class': 'index',
          'contract_kind': 'spi-mini',
        },
      },
      'signals': {
        'SPI200': {
          'signal': 1,
          'strategy_version': 'v1.2.0',
          'signal_as_of': '2026-05-08',
          'last_close': 7800.0,
          'last_scalars': {
            'adx': 27.4, 'mom1': 0.01, 'mom3': 0.02, 'mom12': 0.03, 'rvol': 1.5,
          },
        },
      },
    }
    out = render_signal_cards(state)
    # LONG (signal=1) → cards-row + status-dot--long classname expected.
    assert 'status-dot--long' in out, (
      f'Expected LONG semantic class for signal=1; got: {out[:500]!r}'
    )
    assert 'SPI 200' in out, 'display_name should appear as eyebrow'

  def test_renders_dict_signal_flat_zero(self) -> None:
    from dashboard_renderer.components.signals import render_signal_cards
    state = {
      'last_run': '2026-05-08',
      'markets': {
        'SPI200': {
          'display_name': 'SPI 200',
          'enabled': True,
          'yf_symbol': '^AXJO',
          'data_provider': 'yfinance',
          'asset_class': 'index',
          'contract_kind': 'spi-mini',
        },
      },
      'signals': {
        'SPI200': {'signal': 0, 'strategy_version': 'v1.2.0'},
      },
    }
    out = render_signal_cards(state)
    assert 'status-dot--flat' in out, (
      f'Expected FLAT semantic class for signal=0; got: {out[:500]!r}'
    )


# --- Test 4 -----------------------------------------------------------------

class TestChainContiguityHoldsAfterV10Bump:
  '''Phase 27 #12 contiguity check still passes with the v10 migrator
  registered. Importing state_manager runs the contiguity assertion at
  module load — failure would surface as ImportError.
  '''

  def test_state_schema_version_is_10(self) -> None:
    from system_params import STATE_SCHEMA_VERSION
    # v12 supersedes v11; per-user namespace via admin bucket.
    assert STATE_SCHEMA_VERSION == 12, (
      'STATE_SCHEMA_VERSION advanced to 12 (per-user namespace via admin bucket).'
    )

  def test_migrations_registered_for_every_int_in_chain(self) -> None:
    import state_manager
    from system_params import STATE_SCHEMA_VERSION
    missing = [
      v for v in range(2, STATE_SCHEMA_VERSION + 1)
      if v not in state_manager.MIGRATIONS
    ]
    assert missing == [], (
      f'Chain contiguity broken — missing migrators: {missing!r}'
    )
    assert 10 in state_manager.MIGRATIONS, (
      'MIGRATIONS[10] must be registered (= _migrate_v9_to_v10)'
    )
    assert state_manager.MIGRATIONS[10] is state_manager._migrate_v9_to_v10

  def test_assert_migration_chain_contiguous_passes(self) -> None:
    '''The assertion helper itself runs without raising.'''
    from state_manager import _assert_migration_chain_contiguous
    # Should NOT raise — must succeed for chain 1->10.
    _assert_migration_chain_contiguous()
