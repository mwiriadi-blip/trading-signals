'''Phase 22 (v1.2) — STRATEGY_VERSION + STATE_SCHEMA_VERSION presence/format tests.
Phase 17 (v1.2) — STATE_SCHEMA_VERSION bump 4->5 for ohlc_window + indicator_scalars.

D-01 .. D-04 (22-CONTEXT.md): system_params owns the strategy-version contract
plus the schema-version bump (3 -> 4 then 4 -> 5). These tests pin the public-API
contract so any future bump is a deliberate test edit, not a silent constant change.
'''
import re

import system_params


class TestStrategyVersion:
  '''Phase 22 D-01..D-03: STRATEGY_VERSION constant on system_params.'''

  def test_strategy_version_present_and_str(self) -> None:
    '''D-01: STRATEGY_VERSION exists on system_params and is a str.'''
    assert hasattr(system_params, 'STRATEGY_VERSION'), (
      'Phase 22 D-01: system_params.STRATEGY_VERSION must exist'
    )
    assert isinstance(system_params.STRATEGY_VERSION, str), (
      f'D-01: STRATEGY_VERSION must be str; got {type(system_params.STRATEGY_VERSION)!r}'
    )

  def test_strategy_version_format(self) -> None:
    '''D-02: STRATEGY_VERSION matches the regex /^v\\d+\\.\\d+\\.\\d+$/.'''
    pattern = re.compile(r'^v\d+\.\d+\.\d+$')
    assert pattern.match(system_params.STRATEGY_VERSION), (
      f'D-02: STRATEGY_VERSION must match ^v\\d+\\.\\d+\\.\\d+$; '
      f'got {system_params.STRATEGY_VERSION!r}'
    )

  def test_strategy_version_value_at_v1_2_launch(self) -> None:
    '''D-02: at v1.2 launch, STRATEGY_VERSION is the literal "v1.2.0".'''
    assert system_params.STRATEGY_VERSION == 'v1.2.0', (
      f'D-02: v1.2 launch value must be "v1.2.0"; '
      f'got {system_params.STRATEGY_VERSION!r}. '
      f'If you intentionally bumped this, update the test together with '
      f'docs/STRATEGY-CHANGELOG.md (Phase 22 D-08).'
    )


class TestStateSchemaVersion:
  '''Phase 22 D-04: state.json schema_version bump 3 -> 4.
  Phase 17 D-08 update: bumped again to 5 (ohlc_window + indicator_scalars).
  The is_4 test is superseded by TestStateSchemaVersionV5::test_state_schema_version_is_5.
  '''

  def test_state_schema_version_is_at_least_4(self) -> None:
    '''D-04 (Phase 22): STATE_SCHEMA_VERSION was bumped 3->4; now at 5 (Phase 17).
    Guard: value must be >= 4 (was 4 at Phase 22; Phase 17 bumped to 5).
    '''
    assert system_params.STATE_SCHEMA_VERSION >= 4, (
      f'D-04: STATE_SCHEMA_VERSION must be >= 4 (was 4 at Phase 22, 5 at Phase 17); '
      f'got {system_params.STATE_SCHEMA_VERSION!r}'
    )

  def test_state_schema_version_is_int(self) -> None:
    '''D-04: STATE_SCHEMA_VERSION must remain an int (not a str / float / bool).'''
    assert isinstance(system_params.STATE_SCHEMA_VERSION, int), (
      f'D-04: STATE_SCHEMA_VERSION must be int; '
      f'got {type(system_params.STATE_SCHEMA_VERSION)!r}'
    )
    # Phase 22 deviation note: isinstance(True, int) is True in Python; pin
    # against the bool subtype trap (matches _validate_trade D-19 pattern).
    assert not isinstance(system_params.STATE_SCHEMA_VERSION, bool)


class TestStateSchemaVersionV5:
  '''Phase 17 D-08: STATE_SCHEMA_VERSION bumped 4->5 for ohlc_window +
  indicator_scalars on signal rows.

  Three guards:
    - test_state_schema_version_is_5: constant equals 5 (Phase 17 D-08).
    - test_state_schema_version_is_int: isinstance int (regression guard).
    - test_strategy_version_unchanged_at_v1_2_0: bump did NOT accidentally
      touch STRATEGY_VERSION (Phase 17 has no logic change — only schema).
  '''

  def test_state_schema_version_is_5(self) -> None:
    '''D-08: STATE_SCHEMA_VERSION bumped 4->5 at Phase 17 (ohlc_window +
    indicator_scalars on signal rows).
    '''
    assert system_params.STATE_SCHEMA_VERSION == 5, (
      f'D-08: STATE_SCHEMA_VERSION must be 5 at Phase 17; '
      f'got {system_params.STATE_SCHEMA_VERSION!r}'
    )

  def test_state_schema_version_is_int_v5(self) -> None:
    '''D-08: STATE_SCHEMA_VERSION must remain a plain int after Phase 17 bump.'''
    assert isinstance(system_params.STATE_SCHEMA_VERSION, int), (
      f'D-08: STATE_SCHEMA_VERSION must be int; '
      f'got {type(system_params.STATE_SCHEMA_VERSION)!r}'
    )
    assert not isinstance(system_params.STATE_SCHEMA_VERSION, bool), (
      'D-08: bool is an int subtype — guard against the bool trap'
    )

  def test_strategy_version_unchanged_at_v1_2_0(self) -> None:
    '''Phase 17 has no logic change — STRATEGY_VERSION must still be v1.2.0
    after the schema bump. Guards against accidental clobber.
    '''
    assert system_params.STRATEGY_VERSION == 'v1.2.0', (
      f'Phase 17 D-08: schema bump must NOT change STRATEGY_VERSION; '
      f'got {system_params.STRATEGY_VERSION!r}'
    )
