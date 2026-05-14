'''Phase 37 Plan 02 — per_user_fanout.py tests.

All Wave 0 pytest.skip stubs replaced with real assertions (Plan 37-02).

Classes:
  TestFanOutEmail       — UMAIL-01: per-user email dispatch with personal + shared signals
  TestCrashBoundary     — UMAIL-02: one user failure does not abort the cycle
  TestW3Invariant       — UMAIL-02: per_user_fanout.run() calls mutate_state exactly once
  TestSemaphoreThrottle — UMAIL-03: 50-user mock completes < 30s under Semaphore(2)
  TestRFC8058Headers    — UMAIL-03: List-Unsubscribe + List-Unsubscribe-Post headers
  TestEmailPrefsSkip    — UMAIL-04: skips disabled + paused users
  TestUnicodeDisplayName — UMAIL-01: email.utils.formataddr Unicode round-trip
  TestLastCycleSchema   — review #5/#7: last_cycle is a single dict with 7 keys
  TestPerUserLogging    — review #13: per-user logger.info on every dispatch attempt
  TestDispatchHelpers   — send_invite_email + send_cycle_summary_email contract
'''
import asyncio
import re
import threading
import time

import pytest


# =============================================================================
# Shared fixture helpers
# =============================================================================

def _make_user_row(
  uid='u1',
  email='a@x.com',
  email_enabled=True,
  pause_until=None,
  display_name=None,
):
  return {
    'uid': uid,
    'email': email,
    'role': 'ff',
    'disabled': False,
    'email_enabled': email_enabled,
    'pause_until': pause_until,
    'display_name': display_name,
  }


# =============================================================================
# TestRFC8058Headers
# =============================================================================

class TestRFC8058Headers:
  '''UMAIL-03: List-Unsubscribe + List-Unsubscribe-Post headers on per-user email.'''

  def test_rfc8058_headers_present(self, monkeypatch) -> None:
    '''send_per_user_email passes RFC 8058 headers to _post_to_resend.'''
    import per_user_fanout
    from notifier.transport import SendStatus

    captured_kwargs = {}

    def _mock_post(api_key, from_addr, to_addr, subject, html_body=None,
                   timeout_s=30, retries=3, backoff_s=10, text_body=None,
                   *, email_headers=None):
      captured_kwargs['email_headers'] = email_headers

    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'from@x.com')
    monkeypatch.setenv('RESEND_API_KEY', 'key123')
    monkeypatch.setenv('BASE_URL', 'https://signals.example.com')
    monkeypatch.setattr('per_user_fanout._post_to_resend', _mock_post)

    status = per_user_fanout.send_per_user_email(
      uid='u1',
      user_state={'email': 'a@x.com'},
      shared_signals={},
      run_date='2026-05-14',
    )

    assert status.ok is True
    assert 'email_headers' in captured_kwargs
    hdrs = captured_kwargs['email_headers']
    assert 'List-Unsubscribe' in hdrs
    assert 'List-Unsubscribe-Post' in hdrs
    assert re.match(r'^<https?://.+/settings>$', hdrs['List-Unsubscribe']), (
      f'List-Unsubscribe must be <URL/settings>, got {hdrs["List-Unsubscribe"]!r}'
    )
    assert hdrs['List-Unsubscribe-Post'] == 'List-Unsubscribe=One-Click'

  def test_send_per_user_email_missing_recipient(self, monkeypatch) -> None:
    '''Empty email → SendStatus(ok=False, reason="missing_recipient"), never raises.'''
    import per_user_fanout

    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'from@x.com')
    monkeypatch.setenv('RESEND_API_KEY', 'key123')

    status = per_user_fanout.send_per_user_email(
      uid='u1',
      user_state={'email': ''},
      shared_signals={},
      run_date='2026-05-14',
    )
    assert status.ok is False
    assert status.reason == 'missing_recipient'

  def test_send_per_user_email_broad_except(self, monkeypatch) -> None:
    '''RuntimeError from _post_to_resend → SendStatus(ok=False), never raises.'''
    import per_user_fanout

    def _raise(*a, **kw):
      raise RuntimeError('boom')

    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'from@x.com')
    monkeypatch.setenv('RESEND_API_KEY', 'key123')
    monkeypatch.setattr('per_user_fanout._post_to_resend', _raise)

    status = per_user_fanout.send_per_user_email(
      uid='u1',
      user_state={'email': 'a@x.com'},
      shared_signals={},
      run_date='2026-05-14',
    )
    assert status.ok is False
    assert status.reason is not None
    assert status.reason.startswith('RuntimeError')


# =============================================================================
# TestFanOutEmail
# =============================================================================

class TestFanOutEmail:
  '''UMAIL-01: per-user email dispatched with personal section + shared signals.'''

  @pytest.mark.freeze_time('2026-05-11T00:00:00+00:00')
  def test_fan_out_all_dispatches_per_user(self, monkeypatch) -> None:
    '''_fan_out_all dispatches send_per_user_email with correct uid + shared_signals.'''
    import per_user_fanout
    from notifier.transport import SendStatus

    dispatched = []

    def _mock_send(uid, user_state, shared_signals, run_date):
      dispatched.append({'uid': uid, 'user_state': user_state, 'shared_signals': shared_signals})
      return SendStatus(ok=True, reason=None)

    def _mock_load_user_state(uid):
      return {'email': 'a@x.com', 'uid': uid}

    monkeypatch.setattr('per_user_fanout.send_per_user_email', _mock_send)
    monkeypatch.setattr('per_user_fanout.load_user_state', _mock_load_user_state)

    users = [_make_user_row(uid='u1', email='a@x.com')]
    outcomes = asyncio.run(
      per_user_fanout._fan_out_all(users, {'spi': 'LONG'}, '2026-05-11')
    )

    assert len(outcomes) == 1
    assert outcomes[0]['ok'] is True
    assert len(dispatched) == 1
    # shared_signals passed correctly
    assert dispatched[0]['shared_signals']['spi'] == 'LONG'
    # user_state is per-user slice, NOT full state
    assert 'email' in dispatched[0]['user_state']

  @pytest.mark.freeze_time('2026-05-11T00:00:00+00:00')
  def test_full_state_not_passed_to_send(self, monkeypatch) -> None:
    '''Pitfall 4: full state dict is NOT passed to send_per_user_email.'''
    import per_user_fanout
    from notifier.transport import SendStatus

    call_args = []

    def _mock_send(uid, user_state, shared_signals, run_date):
      call_args.append(user_state)
      return SendStatus(ok=True, reason=None)

    def _mock_load_user_state(uid):
      return {'email': 'u@x.com', 'uid': uid}

    monkeypatch.setattr('per_user_fanout.send_per_user_email', _mock_send)
    monkeypatch.setattr('per_user_fanout.load_user_state', _mock_load_user_state)

    users = [_make_user_row(uid='u1')]
    asyncio.run(per_user_fanout._fan_out_all(users, {}, '2026-05-11'))

    # user_state passed should be per-user slice, not contain top-level state keys
    user_state = call_args[0]
    assert 'signals' not in user_state, (
      'Pitfall 4: full state dict must not be passed; send_per_user_email got signals key'
    )


# =============================================================================
# TestCrashBoundary
# =============================================================================

class TestCrashBoundary:
  '''UMAIL-02: one user failure does not abort the cycle.'''

  @pytest.mark.freeze_time('2026-05-11T00:00:00+00:00')
  def test_one_crash_does_not_abort_others(self, monkeypatch) -> None:
    '''RuntimeError for uid=broken does not abort healthy users.'''
    import per_user_fanout
    from notifier.transport import SendStatus

    def _mock_send(uid, user_state, shared_signals, run_date):
      if uid == 'broken':
        raise RuntimeError('deliberate crash')
      return SendStatus(ok=True, reason=None)

    def _mock_load_user_state(uid):
      return {'email': f'{uid}@x.com'}

    monkeypatch.setattr('per_user_fanout.send_per_user_email', _mock_send)
    monkeypatch.setattr('per_user_fanout.load_user_state', _mock_load_user_state)

    users = [
      _make_user_row(uid='broken', email='broken@x.com'),
      _make_user_row(uid='healthy_a', email='ha@x.com'),
      _make_user_row(uid='healthy_b', email='hb@x.com'),
    ]
    outcomes = asyncio.run(
      per_user_fanout._fan_out_all(users, {}, '2026-05-11')
    )

    assert len(outcomes) == 3
    by_uid = {o['uid']: o for o in outcomes}
    assert by_uid['broken']['ok'] is False
    assert by_uid['broken']['reason'].startswith('RuntimeError')
    assert by_uid['healthy_a']['ok'] is True
    assert by_uid['healthy_b']['ok'] is True


# =============================================================================
# TestW3Invariant
# =============================================================================

class TestW3Invariant:
  '''UMAIL-02: per_user_fanout.run() performs exactly one mutate_state call.'''

  @pytest.mark.freeze_time('2026-05-11T00:00:00+00:00')
  def test_exactly_one_mutate_state_call(self, monkeypatch) -> None:
    '''run() calls mutate_state exactly once regardless of user count.'''
    import per_user_fanout
    from notifier.transport import SendStatus

    call_count = [0]

    def _counting_mutate_state(mutator, path=None):
      call_count[0] += 1
      dummy_state = {'users': {}}
      mutator(dummy_state)
      return dummy_state

    def _mock_send(uid, user_state, shared_signals, run_date):
      return SendStatus(ok=True, reason=None)

    def _mock_load_user_state(uid):
      return {'email': f'{uid}@x.com'}

    def _mock_list_users():
      return [
        {'uid': 'u1', 'email': 'a@x.com', 'role': 'ff', 'disabled': False},
        {'uid': 'u2', 'email': 'b@x.com', 'role': 'ff', 'disabled': False},
        {'uid': 'u3', 'email': 'c@x.com', 'role': 'ff', 'disabled': False},
      ]

    def _mock_cycle_summary(outcomes, run_date, crash=None):
      return SendStatus(ok=True, reason=None)

    monkeypatch.setattr('per_user_fanout.mutate_state', _counting_mutate_state)
    monkeypatch.setattr('per_user_fanout.send_per_user_email', _mock_send)
    monkeypatch.setattr('per_user_fanout.load_user_state', _mock_load_user_state)
    monkeypatch.setattr('per_user_fanout.send_cycle_summary_email', _mock_cycle_summary)

    # Patch list_users via module import
    import auth_store
    monkeypatch.setattr(auth_store, 'list_users', _mock_list_users)

    state = {'signals': {}, 'users': {}}
    per_user_fanout.run(state, '2026-05-11')

    assert call_count[0] == 1, (
      f'W3 invariant: expected exactly 1 mutate_state call, got {call_count[0]}'
    )


# =============================================================================
# TestSemaphoreThrottle
# =============================================================================

class TestSemaphoreThrottle:
  '''UMAIL-03: 50-user mock completes < 30s under Semaphore(2).'''

  @pytest.mark.freeze_time('2026-05-11T00:00:00+00:00')
  def test_50_user_completes_under_30s(self, monkeypatch) -> None:
    '''50-user fan-out with 10ms latency per call completes < 30s; max concurrency <= 2.'''
    import per_user_fanout
    from notifier.transport import SendStatus

    active_count = [0]
    max_active = [0]
    lock = threading.Lock()

    def _mock_send(uid, user_state, shared_signals, run_date):
      with lock:
        active_count[0] += 1
        if active_count[0] > max_active[0]:
          max_active[0] = active_count[0]
      time.sleep(0.01)  # 10ms simulated Resend latency
      with lock:
        active_count[0] -= 1
      return SendStatus(ok=True, reason=None)

    def _mock_load_user_state(uid):
      return {'email': f'{uid}@x.com'}

    monkeypatch.setattr('per_user_fanout.send_per_user_email', _mock_send)
    monkeypatch.setattr('per_user_fanout.load_user_state', _mock_load_user_state)

    users = [_make_user_row(uid=f'u{i}', email=f'u{i}@x.com') for i in range(50)]

    start = time.monotonic()
    outcomes = asyncio.run(
      per_user_fanout._fan_out_all(users, {}, '2026-05-11')
    )
    elapsed = time.monotonic() - start

    assert len(outcomes) == 50
    assert all(o['ok'] for o in outcomes), 'All 50 users should succeed'
    assert elapsed < 30.0, f'50-user fan-out took {elapsed:.1f}s, expected < 30s'
    assert max_active[0] <= 2, (
      f'Semaphore(2) violated: max concurrent calls was {max_active[0]}'
    )


# =============================================================================
# TestEmailPrefsSkip
# =============================================================================

class TestEmailPrefsSkip:
  '''UMAIL-04: skips disabled + paused users without burning Resend quota.'''

  @pytest.mark.freeze_time('2026-05-11T00:00:00+00:00')
  def test_email_disabled_skips_send(self, monkeypatch) -> None:
    '''email_enabled=False → ok=True, reason=skipped:disabled, zero Resend calls.'''
    import per_user_fanout
    from notifier.transport import SendStatus

    send_calls = [0]

    def _mock_send(*a, **kw):
      send_calls[0] += 1
      return SendStatus(ok=True, reason=None)

    def _mock_load_user_state(uid):
      return {'email': f'{uid}@x.com'}

    monkeypatch.setattr('per_user_fanout.send_per_user_email', _mock_send)
    monkeypatch.setattr('per_user_fanout.load_user_state', _mock_load_user_state)

    users = [_make_user_row(uid='u1', email_enabled=False)]
    outcomes = asyncio.run(
      per_user_fanout._fan_out_all(users, {}, '2026-05-11')
    )

    assert len(outcomes) == 1
    assert outcomes[0]['ok'] is True
    assert outcomes[0]['reason'] == 'skipped:disabled'
    assert send_calls[0] == 0, 'No Resend call should be made for disabled user'

  @pytest.mark.freeze_time('2026-05-11T00:00:00+00:00')
  def test_pause_until_today_skips_send(self, monkeypatch) -> None:
    '''pause_until == today → ok=True, reason=skipped:paused, zero Resend calls.'''
    import per_user_fanout
    from notifier.transport import SendStatus

    send_calls = [0]

    def _mock_send(*a, **kw):
      send_calls[0] += 1
      return SendStatus(ok=True, reason=None)

    def _mock_load_user_state(uid):
      return {'email': f'{uid}@x.com'}

    monkeypatch.setattr('per_user_fanout.send_per_user_email', _mock_send)
    monkeypatch.setattr('per_user_fanout.load_user_state', _mock_load_user_state)

    # Frozen to 2026-05-11; pause_until = today means still paused
    users = [_make_user_row(uid='u1', pause_until='2026-05-11')]
    outcomes = asyncio.run(
      per_user_fanout._fan_out_all(users, {}, '2026-05-11')
    )

    assert len(outcomes) == 1
    assert outcomes[0]['ok'] is True
    assert outcomes[0]['reason'] == 'skipped:paused'
    assert send_calls[0] == 0

  @pytest.mark.freeze_time('2026-05-11T00:00:00+00:00')
  def test_pause_until_future_skips_send(self, monkeypatch) -> None:
    '''pause_until in future → skipped:paused.'''
    import per_user_fanout
    from notifier.transport import SendStatus

    send_calls = [0]

    def _mock_send(*a, **kw):
      send_calls[0] += 1
      return SendStatus(ok=True, reason=None)

    def _mock_load_user_state(uid):
      return {'email': f'{uid}@x.com'}

    monkeypatch.setattr('per_user_fanout.send_per_user_email', _mock_send)
    monkeypatch.setattr('per_user_fanout.load_user_state', _mock_load_user_state)

    users = [_make_user_row(uid='u1', pause_until='2026-06-01')]
    outcomes = asyncio.run(
      per_user_fanout._fan_out_all(users, {}, '2026-05-11')
    )

    assert outcomes[0]['reason'] == 'skipped:paused'
    assert send_calls[0] == 0

  @pytest.mark.freeze_time('2026-05-11T00:00:00+00:00')
  def test_pause_until_yesterday_sends(self, monkeypatch) -> None:
    '''pause_until is yesterday → NOT skipped, send proceeds.'''
    import per_user_fanout
    from notifier.transport import SendStatus

    send_calls = [0]

    def _mock_send(*a, **kw):
      send_calls[0] += 1
      return SendStatus(ok=True, reason=None)

    def _mock_load_user_state(uid):
      return {'email': f'{uid}@x.com'}

    monkeypatch.setattr('per_user_fanout.send_per_user_email', _mock_send)
    monkeypatch.setattr('per_user_fanout.load_user_state', _mock_load_user_state)

    users = [_make_user_row(uid='u1', pause_until='2026-05-10')]
    outcomes = asyncio.run(
      per_user_fanout._fan_out_all(users, {}, '2026-05-11')
    )

    # pause_until is yesterday (2026-05-10); today (2026-05-11) > pause_until
    # so NOT paused → should send
    assert send_calls[0] == 1, 'User with past pause_until should NOT be skipped'


# =============================================================================
# TestUnicodeDisplayName
# =============================================================================

class TestUnicodeDisplayName:
  '''UMAIL-01: email.utils.formataddr round-trips Unicode names correctly.'''

  def test_unicode_display_name_encoded(self, monkeypatch) -> None:
    '''User with Unicode display_name uses email.utils.formataddr encoding.'''
    import per_user_fanout

    captured = {}

    def _mock_post(api_key, from_addr, to_addr, subject, html_body=None,
                   timeout_s=30, retries=3, backoff_s=10, text_body=None,
                   *, email_headers=None):
      captured['to_addr'] = to_addr

    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'from@x.com')
    monkeypatch.setenv('RESEND_API_KEY', 'key123')
    monkeypatch.setattr('per_user_fanout._post_to_resend', _mock_post)

    status = per_user_fanout.send_per_user_email(
      uid='u1',
      user_state={'email': 'm@x.com', 'display_name': 'Müller'},
      shared_signals={},
      run_date='2026-05-14',
    )

    assert status.ok is True
    # formataddr should have encoded the Unicode name
    to_header = captured['to_addr']
    # Must contain the email address
    assert 'm@x.com' in to_header
    # Must NOT contain raw Müller (must be encoded for email transport)
    # email.utils.formataddr encodes non-ASCII names as RFC 2047
    assert 'Müller' not in to_header, (
      f'Unicode name must be RFC 2047 encoded, got raw Unicode: {to_header!r}'
    )


# =============================================================================
# TestLastCycleSchema
# =============================================================================

class TestLastCycleSchema:
  '''review #5/#7: last_cycle is a single dict with exactly 7 schema keys.'''

  @pytest.mark.freeze_time('2026-05-11T00:00:00+00:00')
  def test_last_cycle_is_single_dict_not_list(self, monkeypatch) -> None:
    '''run() sets state["last_cycle"] as a single dict, not a list.'''
    import per_user_fanout
    from notifier.transport import SendStatus

    last_cycle_written = [None]

    def _capturing_mutate_state(mutator, path=None):
      state = {}
      mutator(state)
      last_cycle_written[0] = state.get('last_cycle')
      return state

    def _mock_send(uid, user_state, shared_signals, run_date):
      return SendStatus(ok=True, reason=None)

    def _mock_load_user_state(uid):
      return {'email': f'{uid}@x.com'}

    def _mock_list_users():
      return [
        {'uid': 'u1', 'email': 'a@x.com', 'role': 'ff', 'disabled': False},
        {'uid': 'u2', 'email': 'b@x.com', 'role': 'ff', 'disabled': False},
        {'uid': 'u3', 'email': 'c@x.com', 'role': 'ff', 'disabled': False},
      ]

    def _mock_cycle_summary(outcomes, run_date, crash=None):
      return SendStatus(ok=True, reason=None)

    monkeypatch.setattr('per_user_fanout.mutate_state', _capturing_mutate_state)
    monkeypatch.setattr('per_user_fanout.send_per_user_email', _mock_send)
    monkeypatch.setattr('per_user_fanout.load_user_state', _mock_load_user_state)
    monkeypatch.setattr('per_user_fanout.send_cycle_summary_email', _mock_cycle_summary)

    import auth_store
    monkeypatch.setattr(auth_store, 'list_users', _mock_list_users)

    state = {'signals': {}, 'users': {}}
    per_user_fanout.run(state, '2026-05-11')

    lc = last_cycle_written[0]
    assert lc is not None, 'last_cycle must be set in state'
    assert isinstance(lc, dict), f'last_cycle must be a dict, got {type(lc)}'
    assert not isinstance(lc, list), 'last_cycle must NOT be a list (review #7)'

    expected_keys = {'date', 'total', 'ok', 'failed', 'users', 'errors', 'crash'}
    assert set(lc.keys()) == expected_keys, (
      f'last_cycle must have exactly {expected_keys}, got {set(lc.keys())}'
    )

  @pytest.mark.freeze_time('2026-05-11T00:00:00+00:00')
  def test_last_cycle_counters_correct_with_one_failure(self, monkeypatch) -> None:
    '''total/ok/failed/errors calculated correctly when one user fails.'''
    import per_user_fanout
    from notifier.transport import SendStatus

    last_cycle_written = [None]

    def _capturing_mutate_state(mutator, path=None):
      s = {}
      mutator(s)
      last_cycle_written[0] = s.get('last_cycle')
      return s

    def _mock_send(uid, user_state, shared_signals, run_date):
      if uid == 'u2':
        raise RuntimeError('deliberate')
      return SendStatus(ok=True, reason=None)

    def _mock_load_user_state(uid):
      return {'email': f'{uid}@x.com'}

    def _mock_list_users():
      return [
        {'uid': 'u1', 'email': 'a@x.com', 'role': 'ff', 'disabled': False},
        {'uid': 'u2', 'email': 'b@x.com', 'role': 'ff', 'disabled': False},
        {'uid': 'u3', 'email': 'c@x.com', 'role': 'ff', 'disabled': False},
      ]

    def _mock_cycle_summary(outcomes, run_date, crash=None):
      return SendStatus(ok=True, reason=None)

    monkeypatch.setattr('per_user_fanout.mutate_state', _capturing_mutate_state)
    monkeypatch.setattr('per_user_fanout.send_per_user_email', _mock_send)
    monkeypatch.setattr('per_user_fanout.load_user_state', _mock_load_user_state)
    monkeypatch.setattr('per_user_fanout.send_cycle_summary_email', _mock_cycle_summary)

    import auth_store
    monkeypatch.setattr(auth_store, 'list_users', _mock_list_users)

    state = {'signals': {}, 'users': {}}
    per_user_fanout.run(state, '2026-05-11')

    lc = last_cycle_written[0]
    assert lc['total'] == 3
    assert lc['ok'] == 2
    assert lc['failed'] == 1
    assert lc['crash'] is None
    assert len(lc['errors']) == 1
    assert lc['errors'][0]['uid'] == 'u2'
    assert lc['date'] == '2026-05-11'


# =============================================================================
# TestPerUserLogging
# =============================================================================

class TestPerUserLogging:
  '''review #13: logger.info("[Fan-out] uid=... ok=... reason=...") emitted on every attempt.'''

  def test_log_emitted_on_success(self, monkeypatch, caplog) -> None:
    '''Successful dispatch logs [Fan-out] uid=u1 ok=True reason=None.'''
    import logging
    import per_user_fanout

    def _mock_post(api_key, from_addr, to_addr, subject, html_body=None,
                   timeout_s=30, retries=3, backoff_s=10, text_body=None,
                   *, email_headers=None):
      pass  # success

    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'from@x.com')
    monkeypatch.setenv('RESEND_API_KEY', 'key123')
    monkeypatch.setattr('per_user_fanout._post_to_resend', _mock_post)

    with caplog.at_level(logging.INFO, logger='per_user_fanout'):
      per_user_fanout.send_per_user_email(
        uid='u1',
        user_state={'email': 'a@x.com'},
        shared_signals={},
        run_date='2026-05-14',
      )

    log_msgs = [r.message for r in caplog.records]
    matched = [m for m in log_msgs if '[Fan-out] uid=u1' in m and 'ok=True' in m]
    assert matched, (
      f'Expected [Fan-out] uid=u1 ok=True log, got: {log_msgs}'
    )

  def test_log_emitted_on_failure(self, monkeypatch, caplog) -> None:
    '''Failed dispatch logs [Fan-out] uid=broken ok=False reason=RuntimeError...'''
    import logging
    import per_user_fanout

    def _raise(*a, **kw):
      raise RuntimeError('boom')

    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'from@x.com')
    monkeypatch.setenv('RESEND_API_KEY', 'key123')
    monkeypatch.setattr('per_user_fanout._post_to_resend', _raise)

    with caplog.at_level(logging.INFO, logger='per_user_fanout'):
      per_user_fanout.send_per_user_email(
        uid='broken',
        user_state={'email': 'b@x.com'},
        shared_signals={},
        run_date='2026-05-14',
      )

    log_msgs = [r.message for r in caplog.records]
    matched = [m for m in log_msgs if '[Fan-out] uid=broken' in m and 'ok=False' in m]
    assert matched, (
      f'Expected [Fan-out] uid=broken ok=False log, got: {log_msgs}'
    )

  @pytest.mark.freeze_time('2026-05-11T00:00:00+00:00')
  def test_two_user_fan_out_emits_two_log_records(self, monkeypatch, caplog) -> None:
    '''2-user fan-out emits exactly 2 [Fan-out] uid=... log records.

    Uses real send_per_user_email (with mocked _post_to_resend) so the
    per-user logger.info line inside the function actually fires.
    '''
    import logging
    import per_user_fanout

    def _mock_post(api_key, from_addr, to_addr, subject, html_body=None,
                   timeout_s=30, retries=3, backoff_s=10, text_body=None,
                   *, email_headers=None):
      pass  # success — no-op

    def _mock_load_user_state(uid):
      return {'email': f'{uid}@x.com'}

    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'from@x.com')
    monkeypatch.setenv('RESEND_API_KEY', 'key123')
    monkeypatch.setattr('per_user_fanout._post_to_resend', _mock_post)
    monkeypatch.setattr('per_user_fanout.load_user_state', _mock_load_user_state)

    users = [
      _make_user_row(uid='u1', email='a@x.com'),
      _make_user_row(uid='u2', email='b@x.com'),
    ]

    with caplog.at_level(logging.INFO, logger='per_user_fanout'):
      asyncio.run(per_user_fanout._fan_out_all(users, {}, '2026-05-11'))

    fanout_logs = [
      r.message for r in caplog.records
      if '[Fan-out] uid=' in r.message and 'ok=True' in r.message
    ]
    # Each send_per_user_email call logs once; 2 users = 2 log records
    assert len(fanout_logs) == 2, (
      f'Expected 2 [Fan-out] log records for 2 users, got {len(fanout_logs)}: {fanout_logs}'
    )


# =============================================================================
# TestDispatchHelpers
# =============================================================================

class TestDispatchHelpers:
  '''send_invite_email + send_cycle_summary_email contract tests.'''

  def test_send_invite_email_subject_and_body(self, monkeypatch) -> None:
    '''send_invite_email sends correct subject and invite_url in html body.'''
    import per_user_fanout

    captured = {}

    def _mock_post(api_key, from_addr, to_addr, subject, html_body=None,
                   timeout_s=30, retries=3, backoff_s=10, text_body=None,
                   *, email_headers=None):
      captured.update({
        'subject': subject, 'html_body': html_body, 'to_addr': to_addr,
      })

    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'from@x.com')
    monkeypatch.setenv('RESEND_API_KEY', 'key123')
    monkeypatch.setattr('per_user_fanout._post_to_resend', _mock_post)

    status = per_user_fanout.send_invite_email(
      to_email='a@x.com',
      invite_url='https://signals.example.com/accept-invite?token=raw',
    )

    assert status.ok is True
    assert 'invited' in captured['subject'].lower() or 'invite' in captured['subject'].lower()
    assert 'accept-invite' in captured['html_body']
    assert captured['to_addr'] == 'a@x.com'

  def test_send_invite_email_missing_recipient(self) -> None:
    '''Empty to_email → SendStatus(ok=False, reason=missing_recipient), never raises.'''
    import per_user_fanout
    status = per_user_fanout.send_invite_email(to_email='', invite_url='https://x/y')
    assert status.ok is False
    assert status.reason == 'missing_recipient'

  def test_send_invite_email_raw_token_not_logged(self, monkeypatch, caplog) -> None:
    '''Raw invite token/URL must NOT appear in any log record.'''
    import logging
    import per_user_fanout

    def _mock_post(*a, **kw): pass

    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'from@x.com')
    monkeypatch.setenv('RESEND_API_KEY', 'key123')
    monkeypatch.setattr('per_user_fanout._post_to_resend', _mock_post)

    with caplog.at_level(logging.DEBUG, logger='per_user_fanout'):
      per_user_fanout.send_invite_email(
        to_email='a@x.com',
        invite_url='https://x/accept-invite?token=raw_secret_token',
      )

    for record in caplog.records:
      assert 'token=raw' not in record.message, (
        f'Raw token leaked into log: {record.message!r}'
      )

  def test_send_cycle_summary_normal(self, monkeypatch) -> None:
    '''Normal cycle: subject matches [Cycle DATE] N/M OK; body contains uids.'''
    import per_user_fanout

    captured = {}

    def _mock_post(api_key, from_addr, to_addr, subject, html_body=None,
                   timeout_s=30, retries=3, backoff_s=10, text_body=None,
                   *, email_headers=None):
      captured.update({'subject': subject, 'text_body': text_body})

    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'from@x.com')
    monkeypatch.setenv('RESEND_API_KEY', 'key123')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'admin@x.com')
    monkeypatch.setattr('per_user_fanout._post_to_resend', _mock_post)

    outcomes = [
      {'uid': 'u1', 'ok': True, 'reason': None},
      {'uid': 'u2', 'ok': False, 'reason': 'KeyError: x'},
    ]
    status = per_user_fanout.send_cycle_summary_email(outcomes, '2026-05-14')

    assert status.ok is True
    assert re.match(r'^\[Cycle 2026-05-14\] 1/2 OK$', captured['subject']), (
      f'Subject must match [Cycle DATE] 1/2 OK, got {captured["subject"]!r}'
    )
    assert 'u1' in captured['text_body']
    assert 'u2' in captured['text_body']
    assert 'KeyError: x' in captured['text_body']

  def test_send_cycle_summary_crash_field(self, monkeypatch) -> None:
    '''Crash kwarg: subject contains CRASH, text_body contains crash string.'''
    import per_user_fanout

    captured = {}

    def _mock_post(api_key, from_addr, to_addr, subject, html_body=None,
                   timeout_s=30, retries=3, backoff_s=10, text_body=None,
                   *, email_headers=None):
      captured.update({'subject': subject, 'text_body': text_body})

    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'from@x.com')
    monkeypatch.setenv('RESEND_API_KEY', 'key123')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'admin@x.com')
    monkeypatch.setattr('per_user_fanout._post_to_resend', _mock_post)

    status = per_user_fanout.send_cycle_summary_email(
      outcomes=[],
      run_date='2026-05-14',
      crash='RuntimeError: total fan-out failure',
    )

    assert status.ok is True
    assert 'CRASH' in captured['subject'], (
      f'Subject must contain CRASH, got {captured["subject"]!r}'
    )
    assert 'RuntimeError: total fan-out failure' in captured['text_body']

  def test_send_cycle_summary_never_raises(self, monkeypatch) -> None:
    '''RuntimeError from _post_to_resend → SendStatus(ok=False), never raises.'''
    import per_user_fanout

    def _raise(*a, **kw):
      raise RuntimeError('network down')

    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'from@x.com')
    monkeypatch.setenv('RESEND_API_KEY', 'key123')
    monkeypatch.setenv('SIGNALS_EMAIL_TO', 'admin@x.com')
    monkeypatch.setattr('per_user_fanout._post_to_resend', _raise)

    status = per_user_fanout.send_cycle_summary_email([], '2026-05-14')
    assert status.ok is False
    assert status.reason is not None
