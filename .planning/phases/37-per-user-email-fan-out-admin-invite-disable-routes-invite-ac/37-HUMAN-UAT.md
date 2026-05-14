---
status: partial
phase: 37-per-user-email-fan-out-admin-invite-disable-routes-invite-ac
source: [37-VERIFICATION.md]
started: 2026-05-15T06:00:00Z
updated: 2026-05-15T06:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. CR-02 bleed path — top-level trade_log/positions in production state.json

expected: production state.json does NOT have top-level `trade_log` or `positions` keys (only under `state['users'][uid]`), OR if they do exist at top-level, operator confirms F&F bleed is acceptable and adds override to scoped_state
result: [pending]

### 2. End-to-end wizard — TOTP enrollment browser flow

expected: New invitee clicks invite link → sets password → completes TOTP enrollment → registers device → lands on /account page scoped to their per-user state
result: [pending]

### 3. Email content placeholder — UMAIL-01 operator decision

expected: Operator acknowledges that _render_per_user_email_html is a placeholder (stop-loss alerts and paper P&L deferred to a future plan) and confirms this is acceptable for Phase 37 milestone close
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
