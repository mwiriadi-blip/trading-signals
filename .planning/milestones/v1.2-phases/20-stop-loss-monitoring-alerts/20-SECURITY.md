---
phase: 20
slug: stop-loss-monitoring-alerts
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-10
---

# Phase 20 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Built from Phase 20 plan-time `<threat_model>`, `20-CONTEXT.md` risk register, and `20-VERIFICATION.md` evidence.
> All threats identified below are closed via mitigations implemented during Phase 20 execution (verified 2026-04-30).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `state.json` (disk) ↔ in-memory `paper_trades[]` | `last_alert_state` field persisted per trade; schema migration must be idempotent and additive | Alert state strings, paper trade row dicts |
| `alert_engine.py` ↔ `main._evaluate_paper_trade_alerts` | Pure-math module receives OHLCV + indicator scalars from state; must not reach out to I/O | float price/ATR values |
| `mutate_state` lock kernel ↔ `_evaluate_paper_trade_alerts` call site | Two-phase commit MUST be called AFTER `mutate_state(_apply_daily_run)` returns; re-entrant call would deadlock POSIX flock | state dict mutations |
| `notifier.send_stop_alert_email` ↔ Resend HTTPS API | Outbound HTTPS; batched stop-alert payload; secrets in env vars only | paper trade fields (id, instrument, side, prices), `RESEND_API_KEY` |
| Email body HTML ↔ `transitions[i]` fields | Trade fields (id, instrument, side, state strings) interpolated into HTML; must be HTML-escaped | user-persisted strings |
| `dashboard._render_alert_badge` ↔ `paper_trades[]` row | Alert state string rendered directly into dashboard HTML; must be escaped | `last_alert_state` string from state.json |
| `web/routes/paper_trades.py` PATCH handler ↔ `mutate_state` closure | Edit-reset sets `last_alert_state=None` inside same atomic closure as field updates | paper trade row mutations |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-20-01-01 | Tampering | `_migrate_v6_to_v7` overwrites existing `last_alert_state` on upgrade | mitigate | Idempotency guard: `if 'last_alert_state' not in row:` — only backfills rows missing the field; `TestMigrateV6ToV7::test_idempotent` regression | closed |
| T-20-01-02 | Tampering | `_migrate_v6_to_v7` corrupts non-dict rows in `paper_trades[]` | mitigate | `isinstance(row, dict)` check before touching any row; `test_skips_non_dict_rows` | closed |
| T-20-02-01 | DoS (self) | `alert_engine.py` imports `os`, `datetime`, or network stdlib — side-effects at import time | mitigate | `FORBIDDEN_MODULES_STDLIB_ONLY` AST guard in `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent`; walks `alert_engine.py`; allowed: `math`, `typing` only | closed |
| T-20-02-02 | DoS (self) | Division by zero in `compute_atr_distance` when `atr=0` | mitigate | `atr <= 0` guard returns `float('nan')` before division; `TestComputeAtrDistance::test_zero_atr_returns_nan` | closed |
| T-20-02-03 | DoS (self) | NaN propagation in `compute_alert_state` — any NaN input fires spurious HIT email | mitigate | NaN guard at function entry (`x != x` float self-inequality trick on all inputs); returns `'CLEAR'` as safe default before arithmetic; `TestComputeAlertState` parametrized NaN cases PASS | closed |
| T-20-03-01 | Tampering (XSS) | `transitions[i]` fields contain attacker-influenced strings (instrument id, trade id, side) — HTML body interpolation without escaping | mitigate | `html.escape(str(value), quote=True)` on every string field in `_render_alert_email_html`; `test_html_body_is_html_escaped` asserts `&lt;script&gt;` present, raw `<script>` absent | closed |
| T-20-03-02 | Tampering (Gmail CSS strip) | Dashboard CSS classes in email badges stripped by Gmail mobile → invisible alert state | mitigate | Email badges use inline `style="background:...; color:...;"` attributes (`_BADGE_STYLES` dict) — never CSS classes; `test_html_body_uses_inline_styles_only` asserts `class="alert-"` NOT in html body | closed |
| T-20-03-03 | Information Disclosure | `RESEND_API_KEY` in email error logs | mitigate | Phase 27-03 `redact_secret` pattern covers all Resend API key log paths; `send_stop_alert_email` inherits Phase 6 never-crash posture with `except Exception` catch that logs only `type(e).__name__` | closed |
| T-20-03-04 | DoS / silent failure | `send_stop_alert_email` raises uncaught exception → daily run crashes; operator never sees alert | mitigate | `try/except Exception` wraps `_post_to_resend` call; returns `False` on any failure; `test_bare_exception_returns_false` PASS | closed |
| T-20-03-05 | DoS / silent failure | Empty `transitions` list → Resend called with zero-row body | mitigate | Early-return `if not transitions: return False` before calling `_post_to_resend`; `test_empty_transitions_returns_false_no_resend_call` PASS | closed |
| T-20-04-01 | DoS (deadlock) | `_evaluate_paper_trade_alerts` calls `mutate_state` INSIDE the `_apply_daily_run` closure → POSIX flock re-entrant deadlock (project LEARNING: `mutate_state` is non-reentrant) | mitigate | Call site explicitly placed at `run_daily_check` step 9.6 — AFTER `mutate_state(_apply_daily_run)` returns at main.py:1542, BEFORE `_render_dashboard_never_crash`; `test_two_phase_commit_ordering_no_deadlock` asserts ordering | closed |
| T-20-04-02 | DoS / silent failure | Resend API failure causes transitioning rows' `last_alert_state` to be updated anyway → operator never alerted next run (retry suppressed) | mitigate | Two-phase commit: transitioning rows committed ONLY when `send_stop_alert_email` returns `True` (D-06 rollback); `test_send_failure_rollback` asserts transitioning rows retain prior state on failure | closed |
| T-20-04-03 | DoS (self) | `_evaluate_paper_trade_alerts` reads stale ATR from state (computed before today's signal row persistence) → wrong APPROACHING calculation | mitigate | Ordering in `_apply_daily_run`: step 2 persists signal rows + indicator_scalars BEFORE step 3 alert evaluation; `test_ohlc_window_uses_lowercase_keys` confirms correct key access | closed |
| T-20-04-04 | DoS (self) | `indicator_scalars` is empty or `atr` key absent on brand-new instrument → KeyError or false-positive alert | mitigate | `.get('atr', float('nan'))` with NaN guard in `compute_alert_state`; emits `[Alert] WARN no ATR for <inst>; treating as CLEAR`; `test_atr_nan_treated_as_clear_with_warn_log` PASS | closed |
| T-20-05-01 | Tampering (XSS) | `last_alert_state` string from state.json reaches `_render_alert_badge` un-escaped | mitigate | `html.escape(state)` in `_render_alert_badge` return value; `TestRenderAlertBadge` exercises all state variants | closed |
| T-20-05-02 | DoS | `dashboard.py` imports `alert_engine` — adds I/O / CPU cost to render path | mitigate | Dashboard reads `last_alert_state` directly off row dict; `alert_engine` NOT imported; `grep "^from alert_engine|^import alert_engine" dashboard.py` → zero results (D-19 + D-11) | closed |
| T-20-06-01 | Tampering | PATCH edit updates stop_price but does not reset `last_alert_state` → stale HIT/APPROACHING badge persists until next daily run reads old eval | mitigate | `edit_paper_trade._apply` sets `row['last_alert_state'] = None` on every PATCH regardless of field; `test_edit_resets_last_alert_state` parametrized ×4 variants PASS | closed |
| T-20-06-02 | Race condition | Concurrent PATCH edit and daily-run alert eval modify `paper_trades[]` simultaneously | mitigate | `mutate_state` POSIX flock kernel serialises all writes; daily-run eval runs outside closure after lock released; PATCH runs inside its own closure; no concurrent mutation possible | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-20-01 | T-20-03-03 | Single-operator system; no chain-of-custody requirement for API key leaks in logs; Phase 27-03 `redact_secret` provides defense-in-depth | operator | 2026-04-30 |
| AR-20-02 | T-20-04-03 | If operator enters a trade at exactly the 08:00 scheduler tick, new trade may miss that day's eval; picked up next run. Both orderings (entry before or after eval) are correct per D-15 scheduler race analysis. | operator | 2026-04-30 |
| AR-20-03 | — | Resend quota: worst case 1 extra send attempt per daily run on persistent failure = ~1/day. Resend free tier is 3000/month (~100/day). No quota risk. | operator | 2026-04-30 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-10 | 18 | 18 | 0 | /gsd-secure-phase 20 (retroactive reconstruction; 20-VERIFICATION.md 30/30 PASS confirms mitigations in place) |

### 2026-05-10 — retroactive audit

- **Method:** retroactive reconstruction from `20-CONTEXT.md` risk register, `20-VERIFICATION.md` evidence table, and `20-01-SUMMARY.md` deviations.
- **Key threat surfaces confirmed:** alert dedup state (`last_alert_state` field), two-phase commit non-reentrancy (D-18), Resend HTTPS dispatch (D-13), HTML XSS in email body (D-13), dashboard badge XSS (D-14), edit-reset atomicity (D-15).
- **Project LEARNING applied:** `mutate_state` is non-reentrant (flock deadlock if called inside its own closure). Phase 20 D-18 explicitly places `_evaluate_paper_trade_alerts` OUTSIDE the `_apply_daily_run` closure. `test_two_phase_commit_ordering_no_deadlock` pins this contract.
- **No new threats introduced**; no auditor-spawn required under `register_authored_at_plan_time && threats_open=0` short-circuit.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-10 (retroactive reconstruction)
