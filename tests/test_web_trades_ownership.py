'''Phase 36 D-14 — 404-for-other-users ownership stubs for trades entity routes.

Placed in a new file (not appended to test_web_trades.py) because
test_web_trades.py is 1,270 lines — exceeds the 500-LOC project cap (CLAUDE.md).
D-14 originally specified appending to existing files; CLAUDE.md constraint takes
precedence (deferred_decisions in 36-01-PLAN.md frontmatter).

Wave 2 (plan 03+) makes these green by adding ownership checks to entity-ID routes.
Note on semantics (RESEARCH Pitfall 5): current close/modify routes return 409 when
no position exists. Wave 2 must distinguish:
  - 404: position exists in state but belongs to a different user (IDOR check)
  - 409: position genuinely absent for this user (unchanged behavior)

References: D-14, TENANT-03 (IDOR prevention — T-36-01).
'''
import pytest


class TestTradeOwnership:
  '''404-for-other-users tests for trades entity-ID routes (D-14).

  Each test seeds user A's position, authenticates as user B, and asserts 404.
  Wave 2 implementation pending.
  '''

  @pytest.mark.xfail(strict=False, reason='Wave 2: ownership check not yet implemented')
  def test_close_trade_returns_404_for_other_users_position(self):
    '''POST /trades/close returns 404 when position belongs to another user.'''
    pytest.skip('Wave 2 implementation pending')

  @pytest.mark.xfail(strict=False, reason='Wave 2: ownership check not yet implemented')
  def test_modify_trade_returns_404_for_other_users_position(self):
    '''POST /trades/modify returns 404 when position belongs to another user.'''
    pytest.skip('Wave 2 implementation pending')

  @pytest.mark.xfail(strict=False, reason='Wave 2: ownership check not yet implemented')
  def test_close_form_returns_404_for_other_users_position(self):
    '''GET /trades/close-form returns 404 when position belongs to another user.'''
    pytest.skip('Wave 2 implementation pending')

  @pytest.mark.xfail(strict=False, reason='Wave 2: ownership check not yet implemented')
  def test_modify_form_returns_404_for_other_users_position(self):
    '''GET /trades/modify-form returns 404 when position belongs to another user.'''
    pytest.skip('Wave 2 implementation pending')

  @pytest.mark.xfail(strict=False, reason='Wave 2: ownership check not yet implemented')
  def test_cancel_row_returns_404_for_other_users_position(self):
    '''GET /trades/cancel-row returns 404 when position belongs to another user.'''
    pytest.skip('Wave 2 implementation pending')
