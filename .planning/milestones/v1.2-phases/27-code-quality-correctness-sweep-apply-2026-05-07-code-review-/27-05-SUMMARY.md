---
phase: 27
plan: 05
subsystem: pnl_engine helper + notifier required-env-var policy
tags:
  - phase-27
  - magic-number-cleanup
  - secret-as-config-hygiene
  - fail-soft-env-var
  - state-health-marker
  - symmetric-broker
dependency_graph:
  requires:
    - 27-01-decimal-money-math-PLAN.md  # entry_side_cost takes Decimal
  provides:
    - "pnl_engine.entry_side_cost(rt_cost) -> Decimal helper"
    - "notifier._resolve_email_to_or_skip(state, *, context) helper"
  affects:
    - "Future plans persisting per-contract entry-side cost should use entry_side_cost"
    - "Future call sites needing SIGNALS_EMAIL_TO should reuse _resolve_email_to_or_skip"
tech_stack:
  added: []
  patterns:
    - "Single-source magic-number helper: entry_side_cost replaces 4 cost/2 literals"
    - "Fail-soft required-env-var resolver: log ERROR + state-health warning + skip"
    - "Boundary float() coercion: pnl_engine returns Decimal; consumers float() at call sites"
    - "Whitespace-only env value treated as missing (deploy-typo defense)"
key_files:
  created:
    - tests/test_entry_side_cost.py
    - tests/test_signals_email_to_required.py
  modified:
    - pnl_engine.py
    - notifier.py
    - main.py
    - .env.example
    - tests/test_notifier.py
    - tests/test_integration_f1.py
decisions:
  - "entry_side_cost takes/returns Decimal (Plan 27-01 dependency). Symmetric-broker assumption documented in docstring (entry-side commission ≈ exit-side; half-split is canonical allocation for unrealised PnL)."
  - "AST grep gate uses BinOp(left=cost-shaped, op=Div, right=Constant(2)) walker; matches Name + Subscript + Attribute on the left so resolved['cost_aud']/2 is also caught (review-fix M3)."
  - "Missing SIGNALS_EMAIL_TO uses option (b): log + return + state-health warning marker (NOT option (a) fail-fast at startup). Rationale: option (a) crashes daemon on env-var typo — worse than silent skip + visible dashboard warning."
  - "send_crash_email passes state=None to _resolve_email_to_or_skip — crash path may have unloadable state; Plan 27-11 last_crash.json is the additional recovery surface."
  - "send_stop_alert_email also passes state=None (no state arg in signature). Operator visibility for that path comes via the next send_daily_email call which DOES append the marker."
  - "Empty/whitespace-only env var value ('   ') treated identically to unset — defends against `export SIGNALS_EMAIL_TO=` deploy typos."
  - "AST grep gate also catches the close-half site at main.py:1428 (gross - cost_aud_round_trip * ct.n_contracts / 2). The walker doesn't directly match this shape (left is BinOp not cost-Name), but we replaced it under the same symmetric-broker policy for consistency."
metrics:
  duration: ~25min
  tasks: 2
  files_modified: 6
  files_created: 2
  tests_added: 17 (8 entry_side_cost + 9 signals_email_to_required)
  tests_passing: 1880/1880 (full suite, +17 net new from 1863)
  completed: 2026-05-08
---

# Phase 27 Plan 05: Magic /2 Cost Helper + Required SIGNALS_EMAIL_TO — Summary

Two related code-quality cleanups bundled per the plan:

1. **Magic /2 cost helper** (Phase 27 #7): every `cost / 2` literal in production code (pnl_engine, sizing_engine, notifier, main) replaced with `pnl_engine.entry_side_cost(rt_cost)`. Symmetric-broker assumption now documented in one place.
2. **Hardcoded fallback email** (Phase 27 #9 + review-fix M3): `_EMAIL_TO_FALLBACK = 'mwiriadi@gmail.com'` deleted; `SIGNALS_EMAIL_TO` env var becomes REQUIRED. Missing/blank → log ERROR + state-health warning marker visible on dashboard health strip + skip dispatch (fail-soft, never crash).

## What shipped

### `pnl_engine.entry_side_cost(rt_cost) -> Decimal`

```python
def entry_side_cost(rt_cost) -> Decimal:
    '''Phase 27 #7: allocate the entry-side share of a round-trip cost.

    ASSUMPTION: entry-side commission ≈ exit-side commission (symmetric brokers),
    so the half-split is the canonical allocation used by sizing_engine D-13,
    paper-ledger unrealised-PnL display, and notifier email-body cost rendering.
    Returns AUD-quantized Decimal under HALF_UP rounding.
    '''
    rt = _to_dec(rt_cost)
    half = rt / Decimal(2)
    if half.is_nan():
        return half
    return half.quantize(_AUD_QUANTIZE, rounding=_AUD_ROUND)
```

Local Decimal mirrors (`_AUD_QUANTIZE`, `_AUD_ROUND`) reused — no new imports, hex boundary preserved (still `math + decimal + typing` only).

### Replacement sites

| File | Line (before) | Pattern (before) | After |
|---|---|---|---|
| `notifier.py:494` | 494 | `cost_open = cost_aud_round_trip / 2` | `cost_open = float(entry_side_cost(cost_aud_round_trip))` |
| `main.py:1324` | 1324 | `cost_aud_open = cost_aud_round_trip / 2` | `cost_aud_open = float(entry_side_cost(cost_aud_round_trip))` |
| `main.py:1428` | 1428 | `gross - (cost_aud_round_trip * ct.n_contracts / 2)` | `gross - float(entry_side_cost(cost_aud_round_trip)) * ct.n_contracts` |
| `main.py:1535` | 1535 | `resolved['cost_aud'] / 2` (review-fix M3) | `float(entry_side_cost(resolved['cost_aud']))` |

`pnl_engine.py` and `sizing_engine.py` already had no in-source `/2` literals (only docstring references at `sizing_engine.py:524, 591` which the plan explicitly retains as documentation).

### `notifier._resolve_email_to_or_skip(state, *, context)`

```python
def _resolve_email_to_or_skip(state, *, context):
    to_addr = os.environ.get('SIGNALS_EMAIL_TO', '').strip()
    if to_addr:
        return to_addr
    logger.error(
        '[Email] SIGNALS_EMAIL_TO env var required — %s skipped', context,
    )
    if state is not None:
        try:
            from state_manager import append_warning
            append_warning(
                state, 'email',
                'SIGNALS_EMAIL_TO env var missing — emails disabled',
            )
        except Exception as e:
            logger.error(
                '[Email] could not append SIGNALS_EMAIL_TO health warning: %s: %s',
                type(e).__name__, e,
            )
    return None
```

### Three call sites updated

| Site | state arg | Reason |
|---|---|---|
| `send_daily_email` (notifier.py:1564) | `state` (the daily-state dict) | Marker visible on dashboard health strip. |
| `send_crash_email` (notifier.py:1645) | `None` | Crash path may have unloadable state; Plan 27-11 last_crash.json is the additional recovery surface. |
| `send_stop_alert_email` (notifier.py:1999) | `None` | Function signature has no state arg; next send_daily_email call appends the marker. |

All three paths return `SendStatus(ok=False, reason='missing_recipient')` (or `False` for the stop-alert) on missing env var — no Resend call, no crash.

### `.env.example` documentation

```diff
-#   SIGNALS_EMAIL_TO  — recipient override (falls back to Phase 6 default)
+#   SIGNALS_EMAIL_TO  — recipient address (REQUIRED as of Phase 27 #9; no
+#                       fallback. Missing/blank → email skipped, ERROR log,
+#                       state-health warning shown on dashboard health strip).
```

### Tests

| File | Tests | Focus |
|---|---|---|
| `tests/test_entry_side_cost.py` | 8 | helper unit (4) + AST walker over pnl_engine/sizing_engine/notifier/main (4 parametrized) |
| `tests/test_signals_email_to_required.py` | 9 | missing-env contract on all 3 dispatch paths + happy path + state-health marker + grep gates (no _EMAIL_TO_FALLBACK, no operator-shaped literal emails) |

Updated tests:
- `tests/test_notifier.py` — added autouse `_pin_signals_email_to` fixture; rewrote `test_uses_fallback_recipient_when_signals_email_to_unset` → `test_skips_dispatch_when_signals_email_to_unset` (new behavior assertion).
- `tests/test_integration_f1.py` — added `monkeypatch.setenv('SIGNALS_EMAIL_TO', 'ops@example.com')` (cascade fix — F1 chain now reaches `_post_to_resend`).

## TDD Gate Compliance

Tasks 1 and 2 each followed RED → GREEN cycles (test commit before feat commit).

| Hash | Type | Description |
|---|---|---|
| `6d3de26` | test | RED Task 1 — entry_side_cost helper + AST grep gate (8 failing) |
| `80c9847` | feat | GREEN Task 1 — helper + 4 site replacements |
| `e8d3602` | test | RED Task 2 — required SIGNALS_EMAIL_TO across 3 paths (9 failing) |
| `bc7d8f1` | feat | GREEN Task 2 — _resolve_email_to_or_skip + 3 call site updates |

Plan-level gate: PASSED. Both `test(...)` commits precede their corresponding `feat(...)` commits.

## Verification

```
$ .venv/bin/python -m pytest tests/test_entry_side_cost.py tests/test_signals_email_to_required.py -v
  → 17 passed in 0.18s

$ grep -rn '_EMAIL_TO_FALLBACK\|mwiriadi@gmail' notifier.py main.py pnl_engine.py sizing_engine.py
  → (no output — zero matches)

$ .venv/bin/python -c "
import ast, pathlib
for f in ['pnl_engine.py','sizing_engine.py','notifier.py','main.py']:
    tree = ast.parse(pathlib.Path(f).read_text())
    for node in ast.walk(tree):
        if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
            and isinstance(node.right, ast.Constant) and node.right.value == 2):
            l = node.left
            if (isinstance(l, ast.Name) and 'cost' in l.id.lower()) \
               or (isinstance(l, ast.Subscript) and isinstance(l.slice, ast.Constant)
                   and isinstance(l.slice.value, str) and 'cost' in l.slice.value.lower()):
                print(f, node.lineno)
"
  → (no output — zero magic /2 literals)

$ .venv/bin/python -m pytest --tb=line -q
  → 1880 passed in 113.12s (+17 net new from 1863 baseline)
```

## Deviations from Plan

### Auto-fixed issues

**1. [Rule 1 — test cascade] tests/test_integration_f1.py monkeypatch missing SIGNALS_EMAIL_TO.**
- **Found during:** Task 2 GREEN full-suite run.
- **Issue:** F1 chain test sets RESEND_API_KEY + SIGNALS_EMAIL_FROM but not SIGNALS_EMAIL_TO. Pre-Phase 27 #9 the fallback masked this; post-change, send_daily_email short-circuits with missing_recipient before reaching _post_to_resend, leaving captured['subject'] unset. Two integration tests broken (test_full_chain_fetch_to_email + test_f1_catches_planted_regression).
- **Fix:** Added `monkeypatch.setenv('SIGNALS_EMAIL_TO', 'ops@example.com')` next to the existing SIGNALS_EMAIL_FROM line, with a phase-tagged comment. Both tests now pass.
- **Files modified:** `tests/test_integration_f1.py`.
- **Commit:** `bc7d8f1` (folded into Task 2 GREEN to keep the env-var policy diff coherent).

**2. [Rule 1 — test cascade] tests/test_notifier.py autouse env-var pin missing.**
- **Found during:** Task 2 GREEN full-suite run.
- **Issue:** 10 tests across `TestSendDispatch`, `TestSendDispatchStatusTuple`, `TestLastEmailAlwaysWritten`, `TestEmailFromEnvVar` invoked send_daily_email without setting SIGNALS_EMAIL_TO. Pre-change, `_EMAIL_TO_FALLBACK` covered them silently. Post-change, every test short-circuited with missing_recipient and asserted against now-unreachable downstream behavior (5xx logs, 4xx logs, etc.).
- **Fix:** Mirrored the existing `_pin_signals_email_from` autouse fixture pattern with a sibling `_pin_signals_email_to` fixture. Tests that specifically need the missing-env path delenv() in their own bodies (last-mutation-wins).
- **Files modified:** `tests/test_notifier.py`.
- **Commit:** `bc7d8f1`.

### Plan-spec adjustments

**1. close-half site at main.py:1428 also replaced.** Plan inventory listed `main.py:1514` (now :1535 after import added) as the M3 review-fix scope. During implementation, the same close-half pattern at `main.py:1428` (`gross - (cost_aud_round_trip * ct.n_contracts / 2)`) was discovered. The AST walker as written doesn't match it (left of `/` is a BinOp `cost_aud_round_trip * ct.n_contracts`, not a Name/Subscript). To preserve symmetry with the entry-side replacement and to keep the canonical helper as the single allocation policy, the line was rewritten to `gross - float(entry_side_cost(cost_aud_round_trip)) * ct.n_contracts`. Eloquent: same symmetric-broker assumption applies to closing half; one helper now owns both half-cost computations.

**2. send_crash_email and send_stop_alert_email pass state=None.** Plan called for "state-health warning appended on missing env var". send_crash_email's signature takes (exc, state_summary, now) — no state dict. send_stop_alert_email's signature takes (transitions, dashboard_url) — no state dict either. Threading state through both signatures is a wider refactor; the eloquent compromise is: only send_daily_email (which already takes state) appends the marker. Operators get one marker per day from the daily run — sufficient visibility for dashboard health strip purposes.

**3. Source-text grep gate had to allow `onboarding@resend.dev`.** Plan specified "zero literal email addresses in notifier.py". The notifier.py docstrings document Phase 12 SC-4 ("NEVER falls back to onboarding@resend.dev") — these are anti-pattern references, not config. The grep gate allow-lists `carbonbookkeeping` (verified Resend sender, also doc-only) and `onboarding@resend.dev` (anti-pattern documentation). The substantive gate — operator's personal email leaking — is preserved (zero matches).

### Authentication gates

None — no auth surface touched.

## Threat surface scan

Plan threat register:

| Threat ID | Disposition | Status |
|---|---|---|
| T-27-05-01 (operator's email leaked in repo) | mitigate | **MITIGATED** — `_EMAIL_TO_FALLBACK` constant deleted; `mwiriadi@gmail.com` no longer appears in notifier.py source. Regression `test_no_literal_operator_email_in_notifier` enforces. |
| T-27-05-02 (env var missing in production deploy → emails silently dropped → operator unaware) | mitigate | **MITIGATED** — ERROR log via journalctl + state-health warning marker on dashboard health strip via state['warnings']. Operator notices on next dashboard visit. Plan 27-11 last_crash.json provides additional fallback path for the crash-email surface. |

No new network endpoints, auth paths, file-access patterns, or trust-boundary schema changes. No new threat flags.

## Self-Check: PASSED

- [x] `pnl_engine.py` exports `entry_side_cost` (FOUND)
- [x] `tests/test_entry_side_cost.py` exists, 8 tests green (FOUND)
- [x] `tests/test_signals_email_to_required.py` exists, 9 tests green (FOUND)
- [x] AST grep gate confirms zero `cost-shaped / 2` BinOps across pnl_engine/sizing_engine/notifier/main
- [x] grep `_EMAIL_TO_FALLBACK` against notifier.py + main.py + pnl_engine.py + sizing_engine.py + state_manager.py — zero hits
- [x] grep `mwiriadi@gmail` against same files — zero hits
- [x] All 4 commits (`6d3de26`, `80c9847`, `e8d3602`, `bc7d8f1`) reachable from HEAD
- [x] Full suite green: 1880/1880 (+17 net new from 1863 baseline)
- [x] Hex boundary preserved: pnl_engine still imports only math/decimal/typing
- [x] `.env.example` documents SIGNALS_EMAIL_TO as REQUIRED (no fallback)
