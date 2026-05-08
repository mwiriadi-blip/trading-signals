'''Phase 27 Plan 27-12 — notifier package split parity gate.

Asserts that:
  1. Public + private API names that tests/main historically import via
     `notifier.X` remain importable from the package.
  2. Monkeypatch-target names (`notifier.requests`, `notifier._post_to_resend`)
     remain mutable surfaces.
  3. `_dispatch_email_and_maintain_warnings` STAYS in main.py — review-fix
     agreed-3 explicitly forbids moving it to notifier/.
  4. Every notifier package file is <500 LOC (±10% per must_haves M1).

These tests close the package-split contract surface. They are STRUCTURAL
guards: they prevent a future refactor from quietly removing a re-export
that downstream code depends on.
'''
import pathlib

import pytest

import notifier


# =========================================================================
# Public API + monkeypatch-target preservation
# =========================================================================

class TestPublicApiPreserved:
  '''Every name that the legacy single-file notifier.py exposed and that
  tests / main.py import via `notifier.X` must remain importable from the
  package. Prevents silent surface regression on future refactors.
  '''

  PUBLIC_API_NAMES = (
    # --- canonical public surface (D-01) ---
    'compose_email_subject',
    'compose_email_body',
    'send_daily_email',
    'send_crash_email',
    'send_magic_link_email',
    'send_stop_alert_email',
    # --- types ---
    'SendStatus',
    'ResendError',
  )

  PRIVATE_HELPER_NAMES = (
    # --- monkeypatch / introspection surface used by tests ---
    '_post_to_resend',
    '_atomic_write_html',
    '_resolve_email_to_or_skip',
    '_resolve_last_crash_path',
    '_write_last_crash',
    '_redact_secrets_in_text',
    '_build_last_crash_payload',
    '_has_critical_banner',
    '_render_header_email',
    '_render_hero_card_email',
    '_render_footer_email',
    '_render_action_required_email',
    '_render_signal_status_email',
    '_render_positions_email',
    '_render_todays_pnl_email',
    '_render_closed_trades_email',
    '_render_magic_link_html',
    '_render_magic_link_text',
    '_render_alert_email_html',
    '_render_alert_email_text',
    '_build_alert_subject',
    '_format_expires_awst',
    '_detect_signal_changes',
    '_closed_position_for_instrument_on',
    '_compute_unrealised_pnl_email',
    '_compute_trail_stop_email',
    '_extract_signal_int',
    '_extract_signal_as_of',
    '_extract_last_close',
    '_fmt_currency_email',
    '_fmt_em_dash_email',
    '_fmt_instrument_display_email',
    '_fmt_last_updated_email',
    '_fmt_percent_signed_email',
    '_fmt_percent_unsigned_email',
    '_fmt_pnl_with_colour_email',
    '_RESEND_BACKOFF_S',
    '_RESEND_RETRIES',
    # --- crash-path patterns (Plan 27-11) ---
    '_SECRET_PATTERNS_PHASE27_11',
    # --- FIFO helper (Plan 27-12) ---
    'enforce_fifo_bound',
  )

  @pytest.mark.parametrize('name', PUBLIC_API_NAMES)
  def test_public_api_name_present(self, name: str) -> None:
    assert hasattr(notifier, name), (
      f'Plan 27-12 split must preserve `notifier.{name}` — '
      f'historical public API surface (D-01). Add it to the appropriate '
      f'submodule and re-export via notifier/__init__.py.'
    )

  @pytest.mark.parametrize('name', PRIVATE_HELPER_NAMES)
  def test_private_helper_name_present(self, name: str) -> None:
    assert hasattr(notifier, name), (
      f'Plan 27-12 split must preserve `notifier.{name}` — '
      f'tests/main historically reach for it via the package attribute. '
      f'Re-export via notifier/__init__.py.'
    )


class TestMonkeypatchTargetsPreserved:
  '''Tests do `monkeypatch.setattr('notifier.requests.post', ...)` and
  `monkeypatch.setattr(notifier, '_post_to_resend', ...)`. The package
  split must preserve those targets as mutable attributes.
  '''

  def test_notifier_requests_is_real_requests_module(self) -> None:
    '''`notifier.requests.post` is the most-monkeypatched seam in the
    test suite. The attribute MUST resolve to the real requests module
    (or a faithful proxy that exposes `.post`).
    '''
    import requests as _real_requests
    # Either the same module object OR an exposing-`post` alias.
    assert notifier.requests is _real_requests or hasattr(
      notifier.requests, 'post'
    ), 'notifier.requests must support monkeypatch.setattr(notifier.requests, ...)'

  def test_post_to_resend_is_callable(self) -> None:
    assert callable(notifier._post_to_resend), (
      'notifier._post_to_resend must be a callable (tests monkeypatch it).'
    )

  def test_post_to_resend_monkeypatch_propagates_to_dispatch(
    self, monkeypatch,
  ) -> None:
    '''Regression guard: `monkeypatch.setattr(notifier, '_post_to_resend', ...)`
    must take effect when `notifier.send_daily_email` (and other
    dispatchers) calls _post_to_resend. The single-file legacy contract
    relied on Python late-binding inside the same module; the package
    split needs an explicit proxy in dispatch.py to preserve this.
    '''
    calls = []

    def _spy(*a, **kw):
      calls.append((a, kw))

    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'test-from@example.com')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'test-to@example.com')
    monkeypatch.setenv('RESEND_API_KEY', 'test-key-' + 'x' * 30)
    monkeypatch.setattr(notifier, '_post_to_resend', _spy)

    import pytz
    from datetime import datetime
    awst = pytz.timezone('Australia/Perth')
    state = {
      'account': 100000.0,
      'positions': {},
      'signals': {},
      'last_run': None,
      'warnings': [],
      'equity_history': [],
      'trade_log': [],
    }
    notifier.send_daily_email(
      state, {'^AXJO': None, 'AUDUSD=X': None},
      awst.localize(datetime(2026, 5, 8, 9, 0)),
    )
    assert calls, (
      'monkeypatched _post_to_resend was never invoked — dispatch.py is '
      'binding the symbol at import time instead of via package proxy.'
    )


class TestDispatchHelperStaysInMain:
  '''Review-fix agreed-3 (Plan 27-12 must_haves): the orchestrator
  helper `_dispatch_email_and_maintain_warnings` STAYS in main.py.
  Moving it to notifier/ would create a circular dependency and break
  10+ tests that reference `main._dispatch_email_and_maintain_warnings`.
  Plan 27-13 will relocate it to daily_loop / crash_boundary.
  '''

  def test_dispatch_helper_is_in_main_module(self) -> None:
    import main
    assert hasattr(main, '_dispatch_email_and_maintain_warnings'), (
      'main._dispatch_email_and_maintain_warnings is missing — should '
      'NOT have moved out of main.py per review-fix agreed-3.'
    )

  def test_dispatch_helper_is_NOT_in_notifier_package(self) -> None:
    assert not hasattr(notifier, '_dispatch_email_and_maintain_warnings'), (
      '_dispatch_email_and_maintain_warnings was accidentally moved to '
      'the notifier package — Plan 27-12 must_haves explicitly require '
      'it to stay in main.py (review-fix agreed-3).'
    )


# =========================================================================
# LOC budget — every package file <500 LOC (±10% tolerance per M1)
# =========================================================================

class TestPackageLocBudget:
  '''CLAUDE.md "Keep files under 500 lines". Plan 27-12 must_haves M1
  applies a ±10% tolerance to avoid the anti-pattern of every-file-
  exactly-480 LOC. Hard ceiling: 550 LOC.
  '''

  PACKAGE_DIR = pathlib.Path('notifier')

  def test_package_directory_exists(self) -> None:
    assert self.PACKAGE_DIR.is_dir(), (
      f'{self.PACKAGE_DIR}/ must exist as a Python package directory '
      f'after Plan 27-12 split.'
    )

  def test_every_package_file_under_550_loc(self) -> None:
    '''±10% tolerance per M1.'''
    overlong = []
    for f in self.PACKAGE_DIR.glob('*.py'):
      loc = f.read_text(encoding='utf-8').count('\n')
      if loc > 550:
        overlong.append((f.name, loc))
    assert not overlong, (
      'notifier package files exceed 550 LOC (CLAUDE.md <500 line rule '
      f'with M1 ±10% tolerance): {overlong}. Split further.'
    )
