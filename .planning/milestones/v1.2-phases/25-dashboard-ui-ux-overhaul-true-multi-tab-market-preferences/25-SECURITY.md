---
phase: 25
slug: dashboard-ui-ux-overhaul-true-multi-tab-market-preferences
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-10
---

# Phase 25 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Built from plan-time `<threat_model>` blocks across 12 sub-plans (25-01 through 25-11).
> Phase 25 is a UI-only refactor — no signal/state/persistence changes. New attack
> surfaces introduced: HTMX swap injection via market_id path param, cookie tab persistence,
> equity-chart payload XSS gate (cross-linked to T-27-08-03), market_id allowlist.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| HTTP path `/markets/{market_id}/{fn}` ↔ renderer | market_id from URL must be allowlisted before flowing into rendered HTML | market_id string (user-controlled) |
| `selected_market` cookie ↔ state lookup | Cookie value must be regex-validated before state key lookup and HTML render | market_id string (user-controlled) |
| equity-chart JS payload ↔ rendered `<script>` | `</script>` injection via equity point label/date must be escaped | signal/state fields (yfinance-sourced) |
| URL tab param ↔ market strip render | `active_market` from route param must not reach nav HTML unescaped | market_id string (route param) |
| HTMX swap target ↔ dashboard fragment | Partial HTML response for HTMX swap must be same-auth as full-page | fragment HTML body |
| `/status-strip` endpoint ↔ caller | Auth-gated; unauthenticated request returns 401/403 | state fields (last_run, next_run) |
| `render_status_strip` ↔ HTML output | `last_run_at`, `last_run_status` values escaped before emission | state string fields |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-25-01-01 | (n/a) | test-scaffolding plan | accept | Pure test scaffolding — no new production code paths. xfail(strict=True) prevents false greens masking regressions. | closed |
| T-25-02-01 | Tampering (XSS) | nav.py market_id render path | mitigate | `html.escape(market_id, quote=True)` applied in nav.py before emitting any market_id into HTML (RESEARCH §Pattern 1). Backed by `test_xss_market_id_escaped_in_market_strip` (T-27-08-02 cross-link, plan 27-08). | closed |
| T-25-02-02 | (n/a) | shell.py constant relocation | accept | Pure constant migration — no new attack surface. dashboard_renderer/assets.py is not user-accessible. | closed |
| T-25-03-01 | Tampering (XSS) | two-axis nav market_id in anchors | mitigate | All `market_id` values passed through `html.escape(..., quote=True)` before insertion into `href=`, `hx-get=`, `aria-label=`, and tab text. Two-layer defence: allowlist check at route entry (`is_known_market`) + escape at render. | closed |
| T-25-04-01 | Tampering / Spoofing | GET /markets/{market_id}/{fn} route | mitigate | `market_id` validated against `state['markets'].keys()` at route handler entry; unknown market → 404 (not redirect to first market). `selected_market` cookie written only after route-level allowlist pass. Plan 26-07 R7 added regex `^[A-Z0-9_]{2,20}$` to cookie write path (defence-in-depth). | closed |
| T-25-04-02 | Information Disclosure | Set-Cookie: selected_market | accept | Cookie is intentionally NOT HttpOnly (D-05: JS must read it from /account to seed market links). SameSite=Lax + Secure mitigate CSRF and network sniff. Cookie contains only an opaque market_id string — no session token or PII. Single-operator system. | closed |
| T-25-05-01 | Tampering | + Add market chip hx-post | mitigate | hx-post targets `/markets` (existing, auth-gated route). HTMX auth header `X-Trading-Signals-Auth` required per project-wide HTMX convention. No open-redirect surface — hx-swap replaces market strip fragment only. | closed |
| T-25-06-01 | Tampering (XSS) | render_status_strip output | mitigate | `last_run_at`, status dot class, and `next_run_at` values are escaped via renderer before emission. Status dot is a CSS class name drawn from a fixed 4-state enum (`_derive_status_dot_class`) — no free-text path. `/status-strip` endpoint is auth-gated (401 without valid X-Trading-Signals-Auth header). | closed |
| T-25-07-01 | Tampering (XSS) | equity-chart JS payload | mitigate | `_distinct_equity_tuples` gate (D-11) hides chart until ≥5 distinct points — this ensures `replace('</', '<\\/')` escape branch is always exercised when chart renders. Plan 25-11 gap-closure repaired test to seed ≥5 equity points so the escape is actually reached. Cross-link: T-27-08-03 (bulk-escape anti-double-escape audit). | closed |
| T-25-09b-01 | Tampering (a11y / XSS) | Status dot glyph + aria-expanded sync | mitigate | Status dot is a CSS class + Unicode glyph drawn from fixed enum — no user-controlled data. `aria-expanded` state derived from `tsi_trace_open` cookie (allowlisted instrument IDs only). Inline `style="color:..."` removed (D-19) — verified by `TestPhase25NoInlineColor` grep-style assertion. | closed |
| T-25-11-01 | Tampering (placeholder injection) | D-14 placeholder attribute in Market Test | mitigate | Placeholder values sourced from `_strategy_settings_for(state, market_id)` which returns numeric/controlled strategy settings — not user-supplied strings. Rendered via template f-string with html.escape on any string values before emission as `placeholder="..."`. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-25-01 | T-25-04-02 | `selected_market` cookie is intentionally readable by JS (D-05) to seed market links from /account. Contains only opaque market_id — no secrets. SameSite=Lax+Secure provide adequate CSRF/sniff protection for a single-operator system. | operator | 2026-05-05 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-10 | 11 | 11 | 0 | retroactive reconstruction; threat register derived from plan-time `<threat_model>` blocks + 25-VERIFICATION.md + Phase 27 cross-links |

### 2026-05-10 — initial audit (retroactive reconstruction)

- **Method:** Plan-time threat-model blocks from 25-01 through 25-11 parsed; cross-links to Phase 27 threat register (T-27-08-02, T-27-08-03) confirmed mitigated per 27-SECURITY.md (status: verified 2026-05-08).
- **Phase 25 is UI-only.** No new money-math paths, no new auth flows, no new DB writes. Trust boundaries are the rendering pipeline: user-controlled URL segment (market_id) → nav/cookie renderer, and state-sourced fields (equity chart payload) → JS `<script>` block.
- **XSS mitigation verified** via Plan 25-11 gap closure: `test_chart_payload_escapes_script_close` seeds ≥5 equity entries to force chart render, confirming `</script>` escape branch fires.
- **Cookie risk** accepted (AR-25-01). Plan 26-07 R7 hardened the write-path regex post-Phase-25; documented here as defence-in-depth already in code.
- **No new threats** identified beyond those already in the plan-time register.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-10 (retroactive reconstruction; Phase 25 trust surface UI-only; XSS, cookie, and HTMX swap mitigations confirmed in code and test suite)
