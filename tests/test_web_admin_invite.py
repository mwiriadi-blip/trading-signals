'''Phase 37 Wave 0 stubs for RBAC-03 admin surface — implementation in Plan 37-05.

Test classes map to 37-VALIDATION.md RBAC-03 admin rows:
  TestAdminInviteIssue  — POST /admin/invites mints token + sends invite email
  TestAdminInviteRevoke — DELETE /admin/invites/{token_hash} revokes invite
  TestLastCycle         — GET /healthz/last-cycle returns per-user outcomes (admin-gated)

All production imports kept inside test bodies (after pytest.skip) to prevent
collection-time ImportError when the admin invite routes do not yet exist.
'''
import pytest


class TestAdminInviteIssue:
  '''RBAC-03 admin side: POST /admin/invites mints token + sends invite email.

  The endpoint must:
  - Require admin role (require_admin Depends)
  - Mint a new invite token via auth_store.mint_invite_token
  - Send an invite email to the invitee via notifier.send_invite_email
  - Return the inline invite URL fragment for HTMX swap on the admin page
  Implementation lands in Plan 37-05.
  '''

  def test_post_admin_invites_mints_token(self):
    pytest.skip('Wave 0 stub — implementation lands in Plan 37-05')

  def test_post_admin_invites_sends_invite_email(self):
    pytest.skip('Wave 0 stub — implementation lands in Plan 37-05')

  def test_post_admin_invites_returns_inline_invite_url_fragment(self):
    pytest.skip('Wave 0 stub — implementation lands in Plan 37-05')

  def test_post_admin_invites_requires_admin_role(self):
    pytest.skip('Wave 0 stub — implementation lands in Plan 37-05')


class TestAdminInviteRevoke:
  '''RBAC-03 admin side: DELETE /admin/invites/{token_hash} revokes invite.

  The endpoint must:
  - Require admin role (require_admin Depends)
  - Mark the matching PendingInvite row as consumed (revoked)
  - Return 404 for an unknown token_hash
  Implementation lands in Plan 37-05.
  '''

  def test_delete_admin_invite_marks_consumed(self):
    pytest.skip('Wave 0 stub — implementation lands in Plan 37-05')

  def test_delete_admin_invite_404_for_unknown_hash(self):
    pytest.skip('Wave 0 stub — implementation lands in Plan 37-05')

  def test_delete_admin_invite_requires_admin_role(self):
    pytest.skip('Wave 0 stub — implementation lands in Plan 37-05')


class TestLastCycle:
  '''UMAIL-02 + D-15: GET /healthz/last-cycle returns per-user outcomes (admin-gated).

  The endpoint must:
  - Require admin role (registered as standalone route in web/routes/healthz.py per D-15)
  - Return {"status": "ok", "cycle_date": "YYYY-MM-DD"|null, "users": [...]}
  - Return empty users list when no cycle has run yet
  - Include crash field in per-user entry on total fan-out failure (review #5)
  Implementation lands in Plan 37-05.
  '''

  def test_last_cycle_returns_empty_when_no_cycle(self):
    pytest.skip('Wave 0 stub — implementation lands in Plan 37-05')

  def test_last_cycle_returns_per_user_outcomes(self):
    pytest.skip('Wave 0 stub — implementation lands in Plan 37-05')

  def test_last_cycle_requires_admin_role(self):
    pytest.skip('Wave 0 stub — implementation lands in Plan 37-05')

  def test_last_cycle_returns_crash_field_on_total_fanout_failure(self):
    '''review #5: per-user entry must include a crash field when the entire
    fan-out failed (not just a single user) so the operator can distinguish
    partial failures from total fan-out crashes.'''
    pytest.skip('Wave 0 stub — implementation lands in Plan 37-05')
