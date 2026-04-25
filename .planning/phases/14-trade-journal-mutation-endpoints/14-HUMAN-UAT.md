---
status: partial
phase: 14-trade-journal-mutation-endpoints
source: [14-VERIFICATION.md, 14-VALIDATION.md]
started: 2026-04-26
updated: 2026-04-26
---

# Phase 14 — Human UAT (Manual Droplet Verification)

> Automated test suite cannot exercise HTMX runtime in real browsers, kernel-level POSIX flock cross-process semantics, or first-deploy schema migration on a live state.json. These five items require operator verification on the live droplet AFTER Phase 12 SETUP-HTTPS.md is applied AND Phase 14 is deployed via `bash deploy.sh`.

## Current Test

[awaiting operator droplet acceptance run]

## Tests

### 1. HTMX form swaps render correctly in real browsers (TRADE-05 / SC-5)
expected: Open / Close / Modify forms submit successfully via HTMX with json-enc extension; per-tbody-group swaps cleanly; error responses render inline without full-page reload
result: [pending]

**Steps:**
```
# In browser (with auth header configured via extension or x-trading-signals-auth bookmarklet)
# Navigate to https://signals.<domain>/

# Open form test:
# 1. Fill in: instrument=SPI200, direction=LONG, entry_price=7800, contracts=2
# 2. Submit
# 3. Confirm: positions table updates with new row, NO full-page reload, success banner shows
# 4. Optional: pyramid-up by submitting another open with same direction at price > entry+ATR
#    Confirm: same instrument row updates with n_contracts=3, pyramid_level=1

# Close form test:
# 1. Click "Close" on the SPI200 row
# 2. Confirm: row swaps to confirmation panel with exit_price input
# 3. Click "Cancel" — confirm: original row restored
# 4. Click "Close" again, fill exit_price, click "Confirm close"
# 5. Confirm: position removed from table, trade appears in trades table

# Modify form test:
# 1. Click "Modify" on AUDUSD row
# 2. Confirm: form panel appears with new_stop and new_contracts inputs
# 3. Set new_stop=0.6800, leave new_contracts blank
# 4. Submit
# 5. Confirm: row updates with new trail-stop value, "manual" badge appears next to it
# 6. Verify badge tooltip says "(manual; dashboard only)"

# Error path test:
# 1. Open form with invalid input: contracts=0
# 2. Submit
# 3. Confirm: inline error appears above form ("contracts must be >= 1"), NO full-page reload
```

Test in Chrome, Firefox, Safari at minimum.

### 2. fcntl lock cross-process correctness (D-13 / T-14-01)
expected: Concurrent web POST and signal-loop save_state cannot lose updates; both mutations land in final state.json
result: [pending]

**Steps:**
```bash
# On droplet, terminal A — start signal loop in background
sudo systemctl start trading-signals.service
# (or run python main.py --once & if testing manually)

# Immediately from terminal B — trigger web POST while signal loop is mid-flight
curl -X POST https://signals.<domain>/trades/open \
     -H "X-Trading-Signals-Auth: <secret>" \
     -H "Content-Type: application/json" \
     -d '{"instrument":"SPI200","direction":"LONG","entry_price":7800,"contracts":1}'

# Wait for both to complete
# Verify state.json has BOTH:
# - The signal loop's daily computation results (state.last_run = today, state.signals updated)
# - The web POST's new position (state.positions.SPI200 has the new entry)

# Repeat 5x with brief pauses between to surface intermittent races.
```

### 3. Schema migration v2 → v3 on deployed v2 state.json (D-09)
expected: First deploy of Phase 14 onto droplet with v2 state.json migrates cleanly; no data loss; all positions get manual_stop=None backfilled
result: [pending]

**Steps:**
```bash
# Before deploy — back up state.json
sudo cp ~/trading-signals/state.json ~/trading-signals/state.json.pre-v3-backup

# Confirm pre-deploy schema_version
python -c "import json; print(json.load(open('/home/trader/trading-signals/state.json'))['schema_version'])"
# Expected: 2

# Deploy Phase 14
cd ~/trading-signals && bash deploy.sh

# After deploy — confirm migration
python -c "
import json
s = json.load(open('/home/trader/trading-signals/state.json'))
print('schema_version:', s['schema_version'])
print('positions:', list(s['positions'].keys()))
print('manual_stop on each:', {k: v.get('manual_stop') for k, v in s['positions'].items() if v})
print('account preserved:', s['account'])
print('trade_log length preserved:', len(s['trade_log']))
"
# Expected: schema_version=3; manual_stop=None on every non-None position; account & trade_log unchanged
```

### 4. 4xx error responses render inline (TRADE-02 / SC-2 browser half)
expected: 400 errors from POST endpoints render inline in `.error` div without full-page reload; field-level errors visible
result: [pending]

**Steps:** Covered in test #1 (Open form error path test). Verify across all 3 forms.

### 5. 2-stage destructive close UX evaluation (UI-SPEC §Decision 5)
expected: Operator finds the close confirmation flow intuitive; Cancel reachable; confirmation panel shows correct exit_price input
result: [pending]

**Steps:** Subjective. Submit Close on a real position, evaluate UX. Adjust copy if needed in a follow-up.

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps

(none — added if any of the 5 manual tests fail)
