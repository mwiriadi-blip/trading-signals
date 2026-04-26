'''Phase 16 CHORE-01: Full-chain integration test + planted-regression meta-test.

Mock boundaries only (D-02): data_fetcher.yf.Ticker (yfinance fetch — the
implementation-equivalent of ROADMAP SC-1's `requests.get` boundary; yfinance
wraps requests.get internally) and notifier._post_to_resend (Resend dispatch).
All internal composition runs live: signal_engine, sizing_engine, state_manager,
dashboard, notifier compose+render. (REVIEWS M-3 — spec-drift note.)

The happy-path assertions are factored into _assert_f1_outputs so the meta-test
calls the SAME invariants under pytest.raises(AssertionError) (REVIEWS H-2).
This proves cross-module break detection rather than a weaker proxy.
'''
import json
import re
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

import data_fetcher  # noqa: F401 — needed so monkeypatch can resolve attribute
import main
import notifier
import signal_engine
import state_manager

FETCH_FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'fetch'
NOTIFIER_FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'notifier'


def _load_recorded_fixture(name: str) -> pd.DataFrame:
  '''Load a committed fetch fixture (orient='split'). Mirror of the helper in
  tests/test_data_fetcher.py and tests/test_main.py — recovers column dtypes
  identical to a live yfinance DataFrame.'''
  return pd.read_json(FETCH_FIXTURE_DIR / name, orient='split')


def _setup_f1(tmp_path, monkeypatch):
  '''Boundary-only mock scaffold per D-02 + REVIEWS M-3 spec note + REVIEWS M-4
  W3 counter wrapper. Returns (captured_subject_dict, initial_seed_dict,
  mutate_count_list) so the caller can assert on Resend POST args, compare
  state transitions, and verify W3 invariant without retaining closures.

  REVIEWS M-3 note: data_fetcher.yf.Ticker IS the network boundary in this
  codebase (yfinance wraps requests.get internally). Both `requests.get` and
  `yf.Ticker` is above the data_fetcher network layer per RESEARCH OQ-1. This is
  the implementation-equivalent of ROADMAP SC-1's `requests.get` boundary.
  '''
  # 1. Isolate CWD (state.json + last_email.html + dashboard.html land in tmp_path)
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)

  # 2. Seed state — sample_state_with_change has SPI200 SHORT + AUDUSD LONG +
  #    pre-existing drift warning. With 400d fixtures producing FLAT signals,
  #    sizing_engine.step closes both positions during the run (trade_log grows).
  seed = json.loads(
    (NOTIFIER_FIXTURE_DIR / 'sample_state_with_change.json').read_text()
  )
  state_manager.save_state(seed)

  # 3. Mock boundary 1: yfinance fetch -> 400d canonical fixtures.
  #    Patch target is data_fetcher.yf.Ticker (the import site INSIDE
  #    data_fetcher), per tests/test_data_fetcher.py:6-11.
  #    REVIEWS M-3: this is the implementation-equivalent of ROADMAP SC-1's
  #    `requests.get` boundary (yfinance wraps requests.get internally;
  #    both are above the network layer in data_fetcher).
  def _fake_ticker(sym):
    class _T:
      def history(self, **_kw):
        name = 'axjo_400d.json' if sym == '^AXJO' else 'audusd_400d.json'
        return _load_recorded_fixture(name)
    return _T()
  monkeypatch.setattr('data_fetcher.yf.Ticker', _fake_ticker)
  monkeypatch.setattr('data_fetcher.time.sleep', lambda *_a, **_k: None)

  # 4. Mock boundary 2: Resend dispatch -> capture stub.
  captured = {}
  def _capture_post(api_key, from_addr, to_addr, subject, html_body=None, **kw):
    captured['subject'] = subject
    captured['html'] = html_body or ''
  monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@example.com')
  monkeypatch.setenv('RESEND_API_KEY', 'test_key_f1')
  monkeypatch.setattr(notifier, '_post_to_resend', _capture_post)

  # 5. Neutralize git push subprocess (no .git in tmp_path; RESEARCH Pitfall 3)
  monkeypatch.setattr(main, '_push_state_to_git', lambda *a, **kw: None)

  # 6. Wrap state_manager.mutate_state with a call counter (REVIEWS M-4 W3
  #    invariant). DO NOT replace mutate_state — wrap it. The wrapper increments
  #    a shared list, then calls through to the real implementation so all
  #    persistence side effects still occur.
  mutate_calls = []
  real_mutate = state_manager.mutate_state
  def _counting_mutate(mutator, path=None):
    mutate_calls.append(1)
    if path is None:
      return real_mutate(mutator)
    return real_mutate(mutator, path)
  monkeypatch.setattr(state_manager, 'mutate_state', _counting_mutate)
  # main.py imports state_manager at module top, so main.state_manager.mutate_state
  # is the same object — the patch above flows through.

  return captured, seed, mutate_calls


def _assert_f1_outputs(tmp_path, captured, initial_seed, mutate_calls):
  '''Pin EVERY F1 invariant in ONE helper. Both happy-path and meta-test call
  this — meta-test calls under pytest.raises(AssertionError) (REVIEWS H-2).

  Asserts:
    - last_email.html exists + email text patterns (RESEARCH OQ-2)
    - dashboard.html exists + Phase 15 markup in CSS + signal section (REVIEWS H-1)
    - captured subject contains ISO date + instruments + $ prefix
    - state.json transitioned (REVIEWS M-4)
    - trade_log grew vs seed (REVIEWS L-3 / Gemini #4)
    - W3 invariant: exactly 2 mutate_state calls (REVIEWS M-4)

  Dashboard note (REVIEWS H-1 + deviation explanation):
    - Phase 15 introduced class="calc-row" (_render_calc_row, line 1344) and
      class="sentinel-banner" (_render_drift_banner) as body elements.
    - With canonical 400d fixtures producing FLAT signals, sizing_engine.step
      closes ALL open seed positions. Post-run: no open positions → no calc-row
      body element; no drift warnings → no sentinel-banner body element.
    - The Phase 15 CSS stylesheet (.sentinel-banner, .calc-row selectors) IS
      always embedded in dashboard.html, proving the dashboard chain ran.
    - We assert on 'sentinel-banner' (CSS always present) and the signal-section
      header (always rendered) as the stable Phase 15 dashboard-chain evidence.
  '''
  # --- Email assertions (RESEARCH OQ-2) -----------------------------------
  email_path = tmp_path / 'last_email.html'
  assert email_path.exists(), 'last_email.html must be written by the email dispatch chain'
  email_html = email_path.read_text(encoding='utf-8')

  assert '<!DOCTYPE html>' in email_html, 'email must be well-formed HTML'
  assert 'SPI 200' in email_html, '_fmt_instrument_display_email(SPI200) text expected'
  assert 'AUD / USD' in email_html, '_fmt_instrument_display_email(AUDUSD) text expected'
  assert 'FLAT' in email_html, '400d fixtures produce FLAT signals; label must render'
  assert '$' in email_html, 'equity figure must render with $ thousands separator'
  # Note: SPI200 instrument key appears in the subject line (captured['subject'])
  # but NOT as a raw key in the email body (the body uses display names
  # 'SPI 200' and 'AUD / USD'). Subject assertions below cover this.
  # The drift-warning bullet 'You hold SHORT SPI200' would also contain the key,
  # but with FLAT signals closing positions, no drift warnings render in the email.

  # --- Dashboard assertions (REVIEWS H-1) ---------------------------------
  # ROADMAP SC-1: the dashboard chain must be exercised. Without these checks
  # F1 could stay green even if the chain stopped writing dashboard.html.
  # Phase 15 embedded its CSS stylesheet (including .sentinel-banner and the
  # .calc-row selector — class="calc-row" emitted by _render_calc_row for open
  # positions) in every dashboard.html render.
  #
  # sentinel-banner: CSS class always embedded by Phase 15 dashboard chain.
  # class="calc-row": present in CSS selector; also emitted as an HTML attribute
  #   when positions are open (_render_calc_row CALC-01/04). With FLAT-signal
  #   closures the body element is absent but the CSS selector is always present.
  dashboard_path = tmp_path / 'dashboard.html'
  assert dashboard_path.exists(), (
    'dashboard.html not written by the chain — '
    'is part of CHORE-01 SC-1 and must run live (REVIEWS H-1)'
  )
  dashboard_html = dashboard_path.read_text(encoding='utf-8')
  assert 'sentinel-banner' in dashboard_html, (
    'Phase 15 .sentinel-banner CSS selector must appear in the embedded '
    'stylesheet (the Phase 15 dashboard chain ran; REVIEWS H-1)'
  )
  assert 'id="heading-signals"' in dashboard_html, (
    'Signal section header must render — proves dashboard chain ran '
    'end-to-end (always present; Phase 15 DASH-03 stable marker; REVIEWS H-1)'
  )

  # --- Subject assertions (RESEARCH OQ-2) ---------------------------------
  assert 'subject' in captured, (
    'RESEND_API_KEY path must call _post_to_resend; captured stub must record subject'
  )
  subject = captured['subject']
  assert re.search(r'\d{4}-\d{2}-\d{2}', subject), (
    f'subject must contain YYYY-MM-DD ISO date; got: {subject!r}'
  )
  assert 'SPI200' in subject, f'subject must reference SPI200; got: {subject!r}'
  assert 'AUDUSD' in subject, f'subject must reference AUDUSD; got: {subject!r}'
  assert '$' in subject, f'subject must contain equity $ prefix; got: {subject!r}'

  # --- State persistence assertions (REVIEWS M-4 + L-3) -------------------
  final_state = state_manager.load_state()
  # M-4: state must have transitioned. Either account changed (P&L from
  # FLAT-signal closures) OR positions changed shape (closures removed entries).
  account_changed = final_state.get('account') != initial_seed.get('account')
  positions_changed = (
    set(final_state.get('positions', {}).keys()) !=
    set(initial_seed.get('positions', {}).keys())
  ) or any(
    final_state['positions'].get(k) != initial_seed['positions'].get(k)
    for k in set(final_state.get('positions', {})) | set(initial_seed.get('positions', {}))
  )
  assert account_changed or positions_changed, (
    'state.json must reflect the run (account changed from FLAT-signal closure '
    'P&L OR positions changed shape) — REVIEWS M-4'
  )

  # L-3 / Gemini #4: trade_log must have grown — proves FLAT-signal closures
  # actually appended to trade_log via sizing engine, not just no-op'd.
  initial_log_len = len(initial_seed.get('trade_log', []))
  final_log_len = len(final_state.get('trade_log', []))
  assert final_log_len > initial_log_len, (
    f'trade_log must grow: FLAT signals should close BOTH seed positions; '
    f'got initial={initial_log_len}, final={final_log_len} (REVIEWS L-3)'
  )

  # --- W3 invariant (REVIEWS M-4) -----------------------------------------
  assert len(mutate_calls) == 2, (
    f'W3 invariant: state_manager.mutate_state must be called exactly 2 times '
    f'per run_daily_check; got {len(mutate_calls)} (REVIEWS M-4 / CLAUDE.md W3)'
  )


@pytest.mark.freeze_time('2026-04-28T00:00:00+00:00')  # Mon 28 Apr 2026 08:00 AWST
def test_full_chain_fetch_to_email(tmp_path, monkeypatch):
  '''CHORE-01 SC-1: Full chain fetch -> signals -> sizing -> state-write ->
  dashboard render -> email render. Mocks at boundaries only (D-02).
  Asserts via _assert_f1_outputs helper (REVIEWS H-2 — same helper used by
  meta-test): last_email.html, dashboard.html, captured subject, state
  transition, trade_log growth, W3 invariant.'''
  captured, seed, mutate_calls = _setup_f1(tmp_path, monkeypatch)

  # Run the full chain via main.main dispatch (mirrors test_w3_invariant_preserved)
  rc = main.main(['--force-email'])
  assert rc == 0, f'main.main returned non-zero rc={rc}'

  # Pin every F1 invariant via the shared helper (REVIEWS H-2)
  _assert_f1_outputs(tmp_path, captured, seed, mutate_calls)


def _inverted_signal(df):
  '''Return a valid-but-INVERTED signal value (REVIEWS H-2 strengthening).
  Canonical fixtures produce FLAT (0) for both instruments. We return LONG (1)
  here. The chain runs to completion (W3 still preserved) but the email/dashboard
  content NO LONGER matches the FLAT-FLAT canonical assertions. _assert_f1_outputs
  must therefore raise AssertionError under pytest.raises in the meta-test.

  Rationale: simply returning a valid-but-different signal (LONG instead of FLAT)
  forces the chain to skip the FLAT-signal closure path, so the email body shows
  LONG labels instead of FLAT — the 'FLAT' email label assertion in the helper
  FAILS under this patch. Coerced 999 (the prior approach) was insufficient
  because 999 might still let some assertions hold; LONG-instead-of-FLAT
  guarantees the FLAT label assertion fails.
  '''
  return 1  # LONG (instead of canonical FLAT)


@pytest.mark.freeze_time('2026-04-28T00:00:00+00:00')  # Mon 28 Apr 2026 08:00 AWST
def test_f1_catches_planted_regression(tmp_path, monkeypatch):
  '''CHORE-01 SC-2: Permanent meta-test proving F1 actually red-lights when
  signal_engine.get_signal is monkey-patched (rename simulation per D-07).
  Calls the SAME _assert_f1_outputs helper under pytest.raises(AssertionError)
  to prove the EXACT happy-path invariants fail under cross-module break
  (REVIEWS H-2). After the patch is lifted, F1 setup is re-run as a sanity
  check (helper must pass).'''
  captured, seed, mutate_calls = _setup_f1(tmp_path, monkeypatch)

  # Plant regression: get_signal returns INVERTED-but-VALID signals
  # (LONG instead of canonical FLAT). The chain runs end-to-end (W3 preserved)
  # but produces email/dashboard content that doesn't match FLAT-FLAT
  # expectations. The SAME _assert_f1_outputs invariants must FAIL.
  with patch.object(signal_engine, 'get_signal', side_effect=_inverted_signal):
    main.main(['--force-email'])
    # Chain should still complete — return code may be 0 since signals are valid.
    # The break shows up at content-assertion time, NOT at chain runtime.
    with pytest.raises(AssertionError):
      _assert_f1_outputs(tmp_path, captured, seed, mutate_calls)

  # Sanity check: without the patch, the SAME helper passes (proves F1 itself
  # is not broken — only the planted regression breaks it).
  # Re-seed state because the planted run mutated it; reset the mutate counter.
  state_manager.save_state(seed)
  mutate_calls.clear()
  captured.clear()
  rc_clean = main.main(['--force-email'])
  assert rc_clean == 0, 'sanity-check run without patch must succeed'
  _assert_f1_outputs(tmp_path, captured, seed, mutate_calls)
