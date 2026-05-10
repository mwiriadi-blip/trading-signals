---
phase: 17
slug: per-signal-calculation-transparency
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-10
---

# Phase 17 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Reconstructed retroactively per Phase 29 D-07 mechanical retrofit.
> Phase 17 shipped 2026-04-30. Mitigations cite code at ship-time file:line references
> drawn from 17-VERIFICATION.md and 17-01-SUMMARY.md.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `tsi_trace_open` cookie ↔ render path | Cookie carries instrument-key list (UI preference); route layer applies allowlist before substituting `{{TRACE_OPEN_*}}` placeholders | Attacker-controlled string; allowlist (`_VALID_TRACE_INSTRUMENT_KEYS`) prevents attribute injection |
| Persisted signal row (`state.json`) ↔ trace renderer | `indicator_scalars` + `ohlc_window` written by `main.py` at daily run; read as primitives by `dashboard.py` | 9 numeric scalars + 40-entry OHLC list; no operator data, no auth tokens |
| Attacker-controlled instrument id ↔ allowlist filter | `selected_market` cookie + `tsi_trace_open` cookie carry instrument keys that reach routing and substitution | Must be in known allowlist; unknown keys silently dropped |
| OHLC scalar fields (floats from yfinance) ↔ HTML render | `ohlc_window` entries contain Open/High/Low/Close as floats; rendered as text in `<td>` cells | Escaped at render via `_e()` discipline from Phase 27-08; no raw interpolation |
| `dashboard.py` ↔ engine layer (`signal_engine`, `data_fetcher`) | Hex-boundary: dashboard reads only primitives from state dict; no engine imports permitted | Formula text inlined as `_TRACE_FORMULAS` constants; no live recompute |
| `state.json` vote_params ↔ trace panel display | Phase 17 polish commit `587b6f0` — `resolve_vote_params` reads persisted engine-resolved values; Phase 29 plan 03 locks these via regression test | vote_params dict; re-derivation from defaults was the defect; now reads persisted |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-17-01-01 | Tampering (attribute injection) | `tsi_trace_open` cookie carries unknown key like `SPI200 onload=alert(1)` → injected into `<details open>` attribute | mitigate | `_VALID_TRACE_INSTRUMENT_KEYS = frozenset({'SPI200', 'AUDUSD'})` at `web/routes/dashboard.py:89`; allowlist intersection at line 150; `test_tsi_trace_open_cookie_tampered_unknown_keys_filtered` PASS | closed |
| T-17-01-02 | Tampering (XSS) | OHLC scalar fields from yfinance contain `<script>` or HTML entities → stored XSS via Inputs panel `<td>` | mitigate | `_e()` escape applied to all dynamic fields at render time (`dashboard_legacy/`); Phase 27-08 `test_xss_warning_field_escaped` coverage extends to trace panel render path | closed |
| T-17-02-01 | Information Disclosure | `indicator_scalars` leaks pricing/position data visible to any browser hitting the dashboard | accept | Single-operator system behind Phase 16.1 TOTP auth; dashboard is authenticated-access-only; no public data leakage concern | closed |
| T-17-03-01 | Tampering (hex-boundary breach) | Developer adds `from signal_engine import ATR_PERIOD` to "stay DRY" → dashboard bypasses hex-boundary; engine changes break render silently | mitigate | `test_forbidden_imports_absent` AST-walks `dashboard.py` against `FORBIDDEN_MODULES_DASHBOARD` list; formula text inlined in `_TRACE_FORMULAS` constants per D-10/D-13; green at ship | closed |
| T-17-03-02 | Tampering (render drift) | `_TRACE_FORMULAS` strings drift from Phase 1 oracle definitions (plan says "match Phase 1 Plan 02 oracle") | mitigate | `TestTracePanels::test_all_formula_strings_present` greps rendered HTML for each of 9 formula strings; fails if any formula is missing or changed | closed |
| T-17-04-01 | Tampering (vote_params re-derivation) | Trace panel re-derives vote_params from defaults instead of reading engine-persisted values → displayed params drift from actual signal decision | mitigate | Phase 17 polish commit `587b6f0`: `resolve_vote_params` reads persisted `vote_params` key from state row; Phase 29 plan 03 regression test locks the pattern | closed |
| T-17-04-02 | Tampering (stale-state companion) | Rows written before `587b6f0` lack `vote_params` key → `resolve_vote_params` falls back to defaults for stale rows | mitigate | Phase 17 polish commit `bb780af`: backfill `vote_params` at render time for stale state rows; degrade-gracefully contract | closed |
| T-17-05-01 | Spoofing | Attacker modifies `tsi_trace_open` cookie to open disclosure for a future/unknown instrument, causing `{{TRACE_OPEN_XYZ}}` placeholder to remain un-substituted in HTML | mitigate | Placeholder substitution only occurs for known instruments in `_TRACE_OPEN_PLACEHOLDER` dict; unknown keys produce no substitution (placeholder rendered as literal string — no security impact, cosmetic only) | closed |
| T-17-06-01 | DoS (state.json bloat) | 40-bar OHLC × 5 fields × 2 instruments × future N instruments grows state.json past atomic-write budget | accept | 40 bars × 5 fields × 2 instruments ≈ 3.2 KB raw + ~5 KB JSON overhead; total state.json ~35 KB — well below 100 KB threshold; `test_state_json_size_under_limit` regression added per CONTEXT risk register | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-17-01 | T-17-02-01 | Single-operator system behind TOTP auth. `indicator_scalars` expose trading signal numerics, but the entire dashboard is authenticated-access-only. No public data leakage vector. | operator | 2026-04-30 |
| AR-17-02 | T-17-06-01 | State.json growth is bounded to 2 instruments at v1.2; well within atomic-write budget. Regression test (`test_state_json_size_under_limit`) guards the threshold. If instrument count grows in v1.3+, revisit. | operator | 2026-04-30 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-10 | 9 | 9 | 0 | Phase 29 D-07 retroactive mechanical retrofit |

### 2026-05-10 — retroactive reconstruction audit

- **Method:** Mechanical retrofit per Phase 29 D-07. Threat surface enumerated from Phase 17 CONTEXT.md (D-04 cookie, D-10 hex-boundary, D-12 cookie tampering), 17-VERIFICATION.md (anti-patterns found, requirements coverage), and 17-01-SUMMARY.md (deviations + threat flags section).
- **Mitigations verified against shipped code:** 17-VERIFICATION.md confirmed all mitigations at the listed file:line references on 2026-04-30 with green test evidence.
- **Phase 17 Threat Flags section (17-01-SUMMARY.md):** "No new network endpoints, auth paths, or trust boundaries introduced. The `tsi_trace_open` cookie is an unsigned UI-preference cookie — allowlist filtering prevents attribute injection, which is the only applicable threat surface."
- **vote_params drift threats (T-17-04-*):** Identified post-ship via Phase 17 polish commits `587b6f0` + `bb780af`; mitigated before Phase 28 verification; Phase 29 plan 03 regression-locks the pattern.
- **No new threats introduced at this retroactive audit.**

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-10 (retroactive reconstruction per Phase 29 D-07 mechanical retrofit)
