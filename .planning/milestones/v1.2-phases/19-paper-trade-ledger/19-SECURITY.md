---
phase: 19
slug: paper-trade-ledger
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-10
---

# Phase 19 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Built from Phase 19 CONTEXT.md D-04/D-05/D-07/D-15 locked decisions and 19-01 implementation.
> Retroactive reconstruction — all mitigations were shipped in the original phase execution (2026-04-30).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| HTMX browser form → POST /paper-trade/open handler | URL-encoded form body; operator-supplied trade fields | entry_dt, entry_price, contracts, side, instrument, stop_price |
| POST handler → `_parse_form` + Pydantic model_validator | Raw form dict → typed model with D-04 strict validators | all open-form fields; unknown keys rejected via `extra='forbid'` |
| `_apply` closure → `state_manager.mutate_state(flock)` | Closure runs under POSIX flock; composite ID generated atomically | paper_trades[] row append; no direct save_state/load_state inside closure |
| Decimal money math → `state.json` disk persistence | Phase 27 Decimal authority: `entry_cost_aud`, `realised_pnl` quantized HALF_UP on save | float/Decimal boundary at pnl_engine ↔ state_manager |
| `state.json` paper_trades[] → dashboard render | Paper-trade field values rendered as HTML fragments via `_render_paper_trades_*` helpers | instrument, side, entry_dt, entry_price, contracts, realised_pnl |
| Dashboard render → operator browser | HTML fragment; HTMX swap; journal text (trade ID, instrument) must be escaped | rendered HTML, HTMX swap response |
| PATCH/DELETE /paper-trade/{id} → closed-row immutability gate | Route layer enforces 405 + Allow: GET for closed rows; no bypass path | status field; _PaperTradeImmutable sentinel |
| `/paper-trade/*` routes → Phase 16.1 AuthMiddleware | All mutation routes gated by cookie-session auth (already in place from Phase 16.1) | session cookie, auth header |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-19-01-01 | Tampering (injection) | HTMX form inputs bypass server validation — invalid entry_price, future entry_dt, wrong-side stop slips into ledger | mitigate | `_validate_open_form` pure validator with all D-04 rules; Pydantic `model_validator` + `extra='forbid'`; 17 TestOpenValidation tests cover every D-04 rule; returns 400 with explicit reason | closed |
| T-19-01-02 | Tampering (data integrity) | Operator edits or deletes a closed (immutable) row via PATCH/DELETE | mitigate | Route layer checks `status=='closed'` inside `_apply`; raises `_PaperTradeImmutable`; handler converts to 405 + `Allow: GET`; TestImmutability asserts 405 on PATCH + DELETE on closed rows | closed |
| T-19-01-03 | Tampering (XSS) | Journal-adjacent text (instrument, trade ID, realised_pnl) rendered in HTML fragments without escaping | mitigate | Phase 27 Plan 27-08 html-escape audit covers paper-trade render path (13 `html.escape(quote=True)` additions to dashboard.py including paper-trade sections); `test_html_xss_audit.py` AST gate confirms quote=True across all Call nodes | closed |
| T-19-01-04 | Tampering (race condition) | Two concurrent POST /paper-trade/open assign the same composite ID (INSTRUMENT-YYYYMMDD-NNN) | mitigate | Composite ID generation runs INSIDE `mutate_state` closure under `fcntl.LOCK_EX` (Phase 14 flock kernel); ID counter computed from `paper_trades[]` filtered under lock; `TestConcurrentOpen::test_concurrent_open_does_not_collide` (multiprocessing.Process) asserts 2 unique IDs | closed |
| T-19-01-05 | Tampering (precision drift) | Entry-side cost `entry_cost_aud` computed as float `/2` loses precision; persisted value drifts from expected | mitigate | Phase 27 Plan 27-05 ships `pnl_engine.entry_side_cost(rt_cost)` Decimal HALF_UP helper; Phase 27 Plan 27-01 quantizes money on state.json save; test_entry_side_cost.py asserts AUD-quantized result | closed |
| T-19-01-06 | Spoofing (auth bypass) | Unauthenticated request reaches paper-trade mutation routes | mitigate | Phase 16.1 AuthMiddleware gates all routes mounted under `web/app.py`; TestAuthEnforcement asserts 302/401 on open/PATCH/DELETE without auth cookie | closed |
| T-19-01-07 | DoS (state corruption) | Lost-update race: two browser tabs simultaneously mutate paper_trades[] | mitigate | All mutations use `state_manager.mutate_state` (Phase 14 flock kernel — POSIX `fcntl.LOCK_EX` across full load-modify-write); LEARNINGS 2026-04-26 confirms the kernel | closed |
| T-19-01-08 | Information Disclosure | STRATEGY_VERSION captured at module-import time via kwarg default → stale version recorded on rows after a hot-reload / version bump | mitigate | `from system_params import STRATEGY_VERSION` placed INSIDE `_apply` closure body, not at module-top (per LEARNINGS 2026-04-29 kwarg-default capture trap); `test_open_strategy_version_fresh_read_after_monkeypatch` verifies monkeypatched value propagates | closed |
| T-19-01-09 | Tampering (NaN render crash) | `last_close` is `None` or NaN (fresh state, never run) — `compute_unrealised_pnl` receives NaN, render template crashes with `nan` in f-string | mitigate | `math.isnan` guard BEFORE `compute_unrealised_pnl` call; `None` guard for missing `signals[instrument]`; renders `'n/a (no close price yet)'`; `test_open_table_renders_na_when_last_close_missing` + `_nan` both pass | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-19-01 | T-19-01-03 | Paper-trade instrument + trade ID values are operator-supplied and stored in state.json; journal text XSS risk exists if operator supplies malicious values to their own single-operator system | operator | 2026-04-30 |
| AR-19-02 | — | AUDUSD P&L displays USD-as-AUD (no FX conversion) per CLAUDE.md convention; operator's mental model accepts this inaccuracy | operator | 2026-04-30 |
| AR-19-03 | — | `state.json` paper_trades[] grows unboundedly (no pagination, no purge). At ~300 bytes/row × 100 trades = 30 KB; acceptable for operator-driven workflow pace | operator | 2026-04-30 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-10 | 9 | 9 | 0 | /gsd-secure-phase 19 (retroactive; mitigations shipped 2026-04-30; Phase 27-08 XSS audit and Phase 27-05 cost helper shipped 2026-05-08 close additional threat surfaces) |

### 2026-05-10 — retroactive audit

- **Method:** retroactive reconstruction from 19-CONTEXT.md risk register, 19-VERIFICATION.md evidence, 19-01-SUMMARY.md deviation log, and Phase 27-05/27-08 cross-links.
- **HTMX form input:** T-19-01-01 — all D-04 rules enforced via Pydantic; 17 validation tests green.
- **Closed-row immutability:** T-19-01-02 — 405 + Allow: GET contract tested; no bypass path.
- **XSS:** T-19-01-03 — Phase 27-08 html-escape audit closed the risk (html.escape with quote=True on all paper-trade render fragments). Risk was NOT mitigated in Phase 19 original execution; retroactively closed by Phase 27-08.
- **Race condition / flock:** T-19-01-04 — multiprocessing.Process race test confirms flock kernel prevents ID collision.
- **Decimal precision drift:** T-19-01-05 — Phase 27-05 entry_side_cost helper + Phase 27-01 quantize-on-save close the risk.
- **Auth enforcement:** T-19-01-06 — Phase 16.1 AuthMiddleware; TestAuthEnforcement.
- **STRATEGY_VERSION stale capture:** T-19-01-08 — LOCAL import inside closure; monkeypatch regression test.
- **No new threats introduced** beyond those enumerated above.
- **Phase 27 cross-links:** T-19-01-03 closed by 27-08; T-19-01-05 closed by 27-05 + 27-01.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter
- [x] Phase 27 cross-links (27-08 XSS, 27-05 cost helper, 27-01 Decimal) documented

**Approval:** verified 2026-05-10 (retroactive reconstruction; all mitigations shipped in Phase 19 + Phase 27 executions)
