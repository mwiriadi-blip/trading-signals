'''Phase 36 D-14 — 404-for-other-users ownership stubs for paper trade entity routes.

Placed in a new file (not appended to test_web_paper_trades.py) because
test_web_paper_trades.py is 936 lines — exceeds the 500-LOC project cap (CLAUDE.md).
D-14 originally specified appending to existing files; CLAUDE.md constraint takes
precedence (deferred_decisions in 36-01-PLAN.md frontmatter).

Wave 2 (plan 03+) makes these green by adding ownership checks to entity-ID routes.

References: D-14, TENANT-03 (IDOR prevention — T-36-01).
'''
import pytest


class TestEntityIdOwnership:
  '''404-for-other-users tests for paper-trade entity-ID routes (D-14).

  Each test creates user A's entity, authenticates as user B, and asserts 404.
  Wave 2 implementation pending.
  '''

  @pytest.mark.xfail(strict=False, reason='Wave 2: ownership check not yet implemented')
  def test_edit_paper_trade_returns_404_for_other_users_entity(self):
    '''PATCH /paper-trade/{trade_id} returns 404 when trade_id belongs to another user.'''
    pytest.skip('Wave 2 implementation pending')

  @pytest.mark.xfail(strict=False, reason='Wave 2: ownership check not yet implemented')
  def test_delete_paper_trade_returns_404_for_other_users_entity(self):
    '''DELETE /paper-trade/{trade_id} returns 404 when trade_id belongs to another user.'''
    pytest.skip('Wave 2 implementation pending')

  @pytest.mark.xfail(strict=False, reason='Wave 2: ownership check not yet implemented')
  def test_close_paper_trade_returns_404_for_other_users_entity(self):
    '''POST /paper-trade/{trade_id}/close returns 404 when trade_id belongs to another user.'''
    pytest.skip('Wave 2 implementation pending')

  @pytest.mark.xfail(strict=False, reason='Wave 2: ownership check not yet implemented')
  def test_get_close_form_returns_404_for_other_users_entity(self):
    '''GET /paper-trade/{trade_id}/close-form returns 404 when trade_id belongs to another user.'''
    pytest.skip('Wave 2 implementation pending')
