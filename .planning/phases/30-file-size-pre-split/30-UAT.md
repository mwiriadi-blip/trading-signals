---
status: complete
phase: 30-file-size-pre-split
source: [30-01-SUMMARY.md, 30-02-SUMMARY.md, 30-03-SUMMARY.md, 30-04-SUMMARY.md, 30-05-SUMMARY.md, 30-06-SUMMARY.md, 30-07-SUMMARY.md]
started: 2026-05-11T00:00:00+10:00
updated: 2026-05-11T00:00:00+10:00
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

## Current Test

[testing complete]

## Tests

### 1. Login flow
expected: Navigate to /login. The login form renders (username + password fields, submit button). Enter valid credentials and submit. Redirected to dashboard or post-login landing. No 500 error or traceback.
result: pass

### 2. Dashboard loads
expected: Navigate to the dashboard. The page renders with market panels and position data (or empty-state if no positions). No 500 error or "module not found" traceback.
result: pass

### 3. Live trades — positions list
expected: Navigate to the live trades / positions view. The positions list renders (or shows empty state). No error.
result: pass

### 4. Live trades — open/close/modify forms
expected: Open the trade entry form (open a new position). The form renders with instrument, direction, size fields. Optionally submit (or just confirm it renders). Then open the close or modify form on an existing position — form renders without error.
result: issue
reported: "The form renders correctly saving the form with posting a paper trade does nothing."
severity: major

### 5. Paper trades
expected: Navigate to the paper trades section. Paper positions list renders (or empty state). Open the paper trade entry form — it renders with the expected fields. Optionally submit to create a paper trade and verify it appears.
result: issue
reported: "It renders correctly doesn't post."
severity: major

### 6. TOTP flow
expected: Navigate to the TOTP enroll or verify page (e.g. /totp/enroll or /totp/verify). Page renders — QR code or 6-digit entry field visible. No 500 error or broken layout.
result: pass

## Summary

total: 6
passed: 4
issues: 2
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "Submitting the paper trade open form posts the trade and the trade appears in the list"
  status: failed
  reason: "User reported: The form renders correctly saving the form with posting a paper trade does nothing. / It renders correctly doesn't post."
  severity: major
  tests: [4, 5]
  root_cause: |
    Pre-existing gap: dashboard_legacy/paper_trades_section.py _render_paper_trades_open_form()
    emits hx-post="/paper-trade/open" but NO hx-on::after-request="handleTradesError(event)"
    and the enclosing <section> has no .error div. When the POST returns any non-2xx
    (400 validation, 302 auth redirect, 500), HTMX silently does nothing — user sees no
    change. Every other mutating form on the dashboard has the error handler. This gap
    was never caught because Phase 19 paper trades had no UAT run until now.
  artifacts:
    - path: "dashboard_legacy/paper_trades_section.py"
      issue: "_render_paper_trades_open_form missing hx-on::after-request and .error div"
    - path: "dashboard_legacy/paper_trades_section.py"
      issue: "_render_paper_trades_region section wrapper also missing .error div"
  missing:
    - "Add hx-on::after-request=\"handleTradesError(event)\" to the open form element"
    - "Add <div class=\"error\" hidden></div> inside #open-trade-form-section"
  debug_session: ""
