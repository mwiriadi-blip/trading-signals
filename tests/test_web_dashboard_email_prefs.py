'''Phase 37 Wave 0 stubs for UMAIL-04 — implementation in Plan 37-05.

Test class maps to 37-VALIDATION.md UMAIL-04 row:
  TestPatchEmailPrefs — PATCH /settings/email-prefs persists email_enabled + pause_until

All production imports kept inside test bodies (after pytest.skip) to prevent
collection-time ImportError when the email prefs route does not yet exist.
'''
import pytest


class TestPatchEmailPrefs:
  '''UMAIL-04: PATCH /settings/email-prefs persists email_enabled + pause_until.

  The endpoint must:
  - Accept email_enabled (bool) and persist it to state['users'][uid]
  - Accept pause_until (ISO date string or null) and persist it
  - Reject malformed pause_until values with 422
  - Require an authenticated uid (Depends(current_user_id))
  Implementation lands in Plan 37-05.
  '''

  def test_patch_persists_email_enabled_true(self):
    pytest.skip('Wave 0 stub — implementation lands in Plan 37-05')

  def test_patch_persists_email_enabled_false(self):
    pytest.skip('Wave 0 stub — implementation lands in Plan 37-05')

  def test_patch_persists_pause_until_iso_date(self):
    pytest.skip('Wave 0 stub — implementation lands in Plan 37-05')

  def test_patch_rejects_invalid_pause_date(self):
    pytest.skip('Wave 0 stub — implementation lands in Plan 37-05')

  def test_patch_requires_authenticated_uid(self):
    pytest.skip('Wave 0 stub — implementation lands in Plan 37-05')
