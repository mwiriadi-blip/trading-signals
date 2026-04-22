---
status: partial
phase: 06-email-notification
source: [06-VERIFICATION.md]
started: 2026-04-22
updated: 2026-04-22
---

## Current Test

awaiting human testing — live Resend delivery + mobile rendering + signal-change visual inspection

## Tests

### 1. Live Resend POST — operator inbox delivery
expected: Email arrives in operator inbox (default `mwiriadi@gmail.com`; override via `SIGNALS_EMAIL_TO=<addr>`). Subject prefixed `[TEST]` when using `--test`. No errors in log; return code 0.
setup: Export a real `RESEND_API_KEY` (from Resend Dashboard → API Keys). Suggested commands: `RESEND_API_KEY=re_xxx .venv/bin/python -m notifier` OR `RESEND_API_KEY=re_xxx .venv/bin/python main.py --test`.
result: [pending]

### 2. Mobile rendering at 375px viewport (Gmail web + Gmail iOS)
expected: No horizontal scroll on 375px viewport. All 7 D-10 sections render in order (header → ACTION REQUIRED if present → Signal Status → Open Positions → Today's P&L → Last 5 Closed Trades → Footer). Palette hex values (#0f1117 bg, #22c55e LONG, #ef4444 SHORT, #eab308 FLAT) render correctly. Emoji (🔴 or 📊) appears in subject preview pane.
setup: After Test 1 delivers an email, open on iPhone (or Chrome DevTools → device mode → iPhone SE 375px).
result: [pending]

### 3. Signal-change emoji prefix visual inspection
expected: (a) Signal-change run: 🔴 subject + ACTION REQUIRED block with red left border at top of body. (b) Unchanged run: 📊 subject + no ACTION REQUIRED block. Emoji visible in inbox list view (not just when email is open).
setup: Run once against a state where `old_signals` differs from current (e.g., after a SPI200 LONG→SHORT reversal). Run again against unchanged state.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
