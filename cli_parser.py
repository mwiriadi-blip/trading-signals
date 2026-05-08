'''CLI argparse seam — Phase 27 Plan 13 main.py split.

Owns:
  - _build_parser: argparse.ArgumentParser construction (CLI-01..CLI-05 + Phase 8
    --initial-account / --spi-contract / --audusd-contract + Phase 27 #17 --version).
  - _validate_flag_combo: post-parse exclusivity rules
    (--reset vs --test/--force-email/--once; companion-flags require --reset).
  - _mode_label: opening-log-line mode classifier.

Hex discipline: stdlib argparse + system_params only. No transport / data libs.
Re-exported by main.py shim so tests using `main._build_parser` etc. continue to work.
'''
import argparse

import system_params


def _build_parser() -> argparse.ArgumentParser:
  '''CLI-01..CLI-05: four boolean flags + CLI-02 --reset exclusivity enforced
  in _validate_flag_combo. Help strings spell out each flag's Phase 4 scope
  vs Phase 6/7 deferred wiring (C-1 revision — amended upstream docs).
  '''
  p = argparse.ArgumentParser(
    prog='python main.py',
    description='Trading Signals — SPI 200 & AUD/USD mechanical system',
  )
  p.add_argument(
    '--test', action='store_true',
    help='Run full signal check, print report, do NOT mutate state.json (CLI-01)',
  )
  p.add_argument(
    '--reset', action='store_true',
    help='Reinitialise state.json to $100k after confirmation (CLI-02). '
         'Cannot be combined with other flags.',
  )
  p.add_argument(
    '--force-email', action='store_true',
    help="Send today's email immediately (CLI-03). "
         'Phase 6: runs full compute then dispatches via notifier.send_daily_email.',
  )
  p.add_argument(
    '--once', action='store_true',
    help='Run one daily check and exit (CLI-04, GHA mode). '
         'Phase 4: alias for default; scheduler loop arrives in Phase 7.',
  )
  # Phase 8 CONF-01 / CONF-02 — --reset companion flags (D-09..D-13).
  p.add_argument(
    '--initial-account',
    type=float,
    default=None,
    help=(
      'Starting account balance for --reset (Phase 8 CONF-01). '
      'Min $1,000, no ceiling, must be finite. If omitted on TTY, '
      'prompts interactively; on non-TTY, requires the other two '
      '--*-contract flags alongside.'
    ),
  )
  p.add_argument(
    '--spi-contract',
    type=str,
    default=None,
    choices=list(system_params.SPI_CONTRACTS.keys()),
    help=(
      'SPI 200 contract preset for --reset (Phase 8 CONF-02). '
      f'Choices: {", ".join(system_params.SPI_CONTRACTS.keys())}. '
      'Interactive prompt if omitted on TTY.'
    ),
  )
  # Phase 27 #17: --version flag. Primary handler is the early sys.argv
  # hook in `if __name__ == '__main__':` (before heavy app imports). This
  # argparse-side registration is a fallback for the in-process test path
  # (where main.py is imported and main(['--version']) is called) AND keeps
  # `--help` complete by listing --version among the public flags.
  p.add_argument(
    '--version', action='store_true',
    help='Print STRATEGY_VERSION and exit 0 (Phase 27 #17). '
         'Short-circuited before heavy imports for fast cold-start.',
  )
  p.add_argument(
    '--audusd-contract',
    type=str,
    default=None,
    choices=list(system_params.AUDUSD_CONTRACTS.keys()),
    help=(
      'AUD/USD contract preset for --reset (Phase 8 CONF-02). '
      f'Choices: {", ".join(system_params.AUDUSD_CONTRACTS.keys())}.'
    ),
  )
  return p


def _validate_flag_combo(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
  '''D-05 (Phase 4): --reset is strictly exclusive with --test /
  --force-email / --once. D-09 (Phase 8): --initial-account,
  --spi-contract, --audusd-contract ARE allowed alongside --reset
  but MUST NOT appear without it.

  Using post-parse parser.error() (exits with code 2, matching argparse
  convention) because argparse's mutually_exclusive_group would also block
  --test + --once etc. which D-05 allows.
  '''
  if args.reset and (args.test or args.force_email or args.once):
    parser.error('--reset cannot be combined with --test/--force-email/--once')
  reset_companions_present = (
    args.initial_account is not None
    or args.spi_contract is not None
    or args.audusd_contract is not None
  )
  if reset_companions_present and not args.reset:
    parser.error(
      '--initial-account / --spi-contract / --audusd-contract '
      'require --reset'
    )


def _mode_label(args: argparse.Namespace) -> str:
  '''Render the opening [Sched] Run line's mode label.

  D-07: --once and default are both 'once' in Phase 4.
  '''
  if args.test:
    return 'test'
  if args.reset:
    return 'reset'
  if args.force_email:
    return 'force_email'
  return 'once'
