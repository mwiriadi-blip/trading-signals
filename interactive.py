'''Interactive Q&A seam — Phase 27 Plan 13 main.py split.

Owns:
  - _stdin_isatty: thin sys.stdin.isatty() wrapper for test patchability.
  - _prompt_or_default: shared interactive-prompt helper (Phase 8 WR-02).
  - _handle_reset: the --reset interactive Q&A + state replacement flow
    (CLI-02 + Phase 8 D-09..D-13).

Hex discipline: stdlib (sys, os, math, logging, argparse) + state_manager +
system_params. No transport / data libs.

Re-exported by main.py shim: main._stdin_isatty, main._handle_reset.
Tests patch via `main._stdin_isatty` and call `main.main(['--reset', ...])`.
'''
import argparse
import logging
import os
import sys

import state_manager
import system_params

logger = logging.getLogger(__name__)


def _stdin_isatty() -> bool:
  '''D-13 (Phase 8): thin wrapper around sys.stdin.isatty() for
  test-patchability. Mirrors Phase 7 _get_process_tzname precedent.
  '''
  return sys.stdin.isatty()


def _prompt_or_default(
  prompt_text: str,
  default_value,
  validator,
):
  '''Phase 8 WR-02: shared interactive-prompt helper for _handle_reset.

  Consolidates the prompt/blank-accepts-default/q-cancels/invalid-rejects
  cycle that repeated 3× verbatim in _handle_reset. Public behavior is
  unchanged from the pre-refactor inline blocks — existing interactive-
  path tests (TestResetInteractive) continue to pass without modification.

  Contract:
    - Prints prompt_text via input() (already spelled with trailing ': ').
    - Returns (rc, value):
        rc=0 + the parsed value, OR
        rc=1 + None when cancelled ('q'/EOF) or invalid.
    - Blank input → default_value returned with rc=0.
    - 'q' (case-insensitive) or EOFError on input() → log 'cancelled',
      return (1, None).
    - validator(raw) is called with the stripped raw string for non-
      blank, non-q inputs. It MUST return (ok: bool, value_or_err):
        ok=True  → value used; helper returns (0, value)
        ok=False → value_or_err is the stderr error message;
                   helper prints '[State] ERROR: {msg}' and returns (1, None).
  '''
  try:
    raw = input(prompt_text).strip()
  except EOFError:
    raw = 'q'
  if raw.lower() == 'q':
    logger.info('[State] --reset cancelled by operator')
    return 1, None
  if raw == '':
    return 0, default_value
  ok, parsed_or_err = validator(raw)
  if not ok:
    print(f'[State] ERROR: {parsed_or_err}', file=sys.stderr)
    return 1, None
  return 0, parsed_or_err


def _handle_reset(args: argparse.Namespace) -> int:
  '''CLI-02 + Phase 8 D-09/D-10/D-11/D-12/D-13:

  Accepts --initial-account / --spi-contract / --audusd-contract
  OR prompts interactively on TTY. Non-TTY + missing flags → exit 2.

  Flow:
    1. D-13 non-TTY guard (must be first).
    2. D-09 interactive Q&A for each missing flag (or q to quit) via
       _prompt_or_default (Phase 8 WR-02 refactor).
    3. D-10 min-$1000 validation (float, $/comma-stripped) + isfinite check.
    4. D-11 label validation (argparse choices handles explicit flags;
       interactive path re-validates against SPI_CONTRACTS/AUDUSD_CONTRACTS).
    5. D-12 preview block: print new values + current state.json values.
    6. YES confirmation (RESET_CONFIRM env override preserved).
    7. Build state + save.

  Return codes:
    0 — reset written
    1 — operator cancelled (EOF, blank YES, q, invalid input, non-finite)
    2 — non-TTY without companion flags OR argparse-level error

  Note: this function contains its OWN state_manager.mutate_state call
  (Phase 14 REVIEWS HIGH #1: was save_state), distinct from the two
  inside run_daily_check + _dispatch_email_and_maintain_warnings. The
  C-7 AST gate (revision 2026-04-22) is scoped to run_daily_check only;
  this --reset site at module level is expected and valid.
  '''
  import math

  has_explicit_flags = (
    args.initial_account is not None
    and args.spi_contract is not None
    and args.audusd_contract is not None
  )
  # Late-bind via main package so tests can patch `main._stdin_isatty`.
  import main as _main_pkg
  if not has_explicit_flags and not _main_pkg._stdin_isatty():
    print(
      '[State] ERROR: Non-interactive shell detected. Pass '
      '--initial-account <N> --spi-contract <label> '
      '--audusd-contract <label> explicitly.',
      file=sys.stderr,
    )
    return 2

  # --- D-09 interactive Q&A ---
  initial_account = args.initial_account
  if initial_account is None:
    def _validate_account(raw: str):
      cleaned = raw.lstrip('$').replace(',', '')
      try:
        return True, float(cleaned)
      except ValueError:
        return False, f'invalid account value {raw!r}'

    rc, initial_account = _prompt_or_default(
      'Starting account [$100,000]: ',
      float(system_params.INITIAL_ACCOUNT),
      _validate_account,
    )
    if rc != 0:
      return rc
  # T-08-12 mitigation: reject NaN/inf/-inf (argparse type=float accepts them).
  if not math.isfinite(initial_account):
    print(
      '[State] ERROR: --initial-account must be a finite number '
      '(not NaN/inf/-inf)',
      file=sys.stderr,
    )
    return 1
  if initial_account < 1000:
    print(
      '[State] ERROR: --initial-account must be at least $1,000',
      file=sys.stderr,
    )
    return 1

  spi_contract = args.spi_contract
  if spi_contract is None:
    default_label = system_params._DEFAULT_SPI_LABEL
    choices = ', '.join(system_params.SPI_CONTRACTS.keys())

    def _validate_spi(raw: str):
      if raw not in system_params.SPI_CONTRACTS:
        return False, f'invalid SPI label {raw!r} — choices: {choices}'
      return True, raw

    rc, spi_contract = _prompt_or_default(
      f'SPI200 contract preset [{default_label}] (choices: {choices}): ',
      default_label,
      _validate_spi,
    )
    if rc != 0:
      return rc

  audusd_contract = args.audusd_contract
  if audusd_contract is None:
    default_label = system_params._DEFAULT_AUDUSD_LABEL
    choices = ', '.join(system_params.AUDUSD_CONTRACTS.keys())

    def _validate_audusd(raw: str):
      if raw not in system_params.AUDUSD_CONTRACTS:
        return False, f'invalid AUDUSD label {raw!r} — choices: {choices}'
      return True, raw

    rc, audusd_contract = _prompt_or_default(
      f'AUDUSD contract preset [{default_label}] (choices: {choices}): ',
      default_label,
      _validate_audusd,
    )
    if rc != 0:
      return rc

  # --- D-12 preview ---
  print('This will replace state.json. New values:')
  print(f'  initial_account: ${initial_account:,.2f}')
  print('  contracts:')
  print(f'    SPI200:  {spi_contract}')
  print(f'    AUDUSD:  {audusd_contract}')
  try:
    current = state_manager.load_state()
  except (OSError, ValueError, TypeError) as e:
    # Phase 8 IN-02: surface the swallowed error at DEBUG so an operator
    # running `--reset` because their state is already broken can see WHY
    # the preview block is empty when running with --log-level DEBUG.
    # The swallow itself is intentional — the preview must still proceed
    # even if the existing state.json is unreadable.
    logger.debug(
      '[State] reset preview: failed to read existing state (%s: %s)',
      type(e).__name__, e,
    )
    current = None
  if current is not None:
    print('Current state.json:')
    cur_ia = current.get('initial_account', system_params.INITIAL_ACCOUNT)
    tag = 'migrated default' if 'initial_account' not in current else 'on disk'
    print(f'  initial_account: ${cur_ia:,.2f} ({tag})')
    print(f'  last_run: {current.get("last_run")}')
    print(f'  trades: {len(current.get("trade_log", []))}')

  # --- YES confirm (RESET_CONFIRM env override preserved) ---
  confirm = os.getenv('RESET_CONFIRM', '').strip()
  if confirm != 'YES':
    try:
      confirm = input('Type YES to confirm, anything else to cancel: ').strip()
    except EOFError:
      confirm = ''
  if confirm != 'YES':
    logger.info('[State] --reset cancelled by operator')
    return 1

  # --- Build + save ---
  # Phase 14 REVIEWS HIGH #1: --reset is also a writer; route through
  # mutate_state for cross-process safety (lock held across the full
  # replace-with-fresh + save). Note: --reset is OUTSIDE the daily-run
  # W3 invariant (one-shot CLI, not part of the run_daily_check 2-saves
  # contract).
  fresh_state = state_manager.reset_state()
  fresh_state['initial_account'] = float(initial_account)
  fresh_state['account'] = float(initial_account)  # Phase 10 BUG-01 D-01
  fresh_state['contracts'] = {'SPI200': spi_contract, 'AUDUSD': audusd_contract}
  def _apply_reset(s: dict) -> None:
    '''--reset semantics: discard whatever's in the freshly-loaded state
    under lock, replace with the operator-supplied fresh state.
    '''
    s.clear()
    s.update(fresh_state)
  state = state_manager.mutate_state(_apply_reset)
  logger.info(
    '[State] state.json reset (initial_account=$%.2f, SPI200=%s, AUDUSD=%s)',
    initial_account, spi_contract, audusd_contract,
  )
  return 0
