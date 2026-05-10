---
phase: 26
slug: phase-25-followup-multi-tab-scoping-fixes
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-10
---

# Phase 26 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Reconstructed retroactively (mechanical retrofit per Phase 29 D-07).
> Built from plan-level fix shapes across 8 sub-plans (26-01 … 26-08).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Git history ↔ repo root | Tracked files must never contain credentials (TOTP secret, API keys) | `auth.json`, secret files in working tree |
| HTTP path/cookie → renderer | `selected_market` cookie and `active_function` query param are untrusted; must be regex-validated before use | `selected_market` cookie (`^[A-Z0-9_]{2,20}$`), `active_function` allowlist `{signals, account, settings, market-test}` |
| Template placeholders → served HTML | `{{WEB_AUTH_SECRET}}`, `{{SIGNOUT_BUTTON}}`, `{{SESSION_NOTE}}`, `{{TRACE_OPEN_*}}` must be substituted before Response leaves the server | auth secret, session widget HTML, trace-open state |
| Per-market route ↔ market state | `/markets/{M}/{fn}` must scope renderer output to market M; no cross-market data leakage | signal cards, settings forms, market-test panels |
| Cache layer ↔ per-page content | Stale-marker check must gate each sibling HTML independently; no shared-stale coupling | cached `dashboard-*.html` files |
| `add_market` write path ↔ renderer read path | New market signal entry must match `run_daily_check` dict shape; int-sentinel shape is legacy test fixture only | `state['signals'][market_id]` |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-26-01-01 | Information Disclosure | `auth.json` (TOTP secret) in git history | mitigate | `git log --all --full-history -- auth.json` confirms 0 commits; file gitignored at line 2 since Phase 13; operator accepted no rotation required | closed |
| T-26-01-02 | Information Disclosure | Agent runtime dirs (`.claude-flow/`, `.mcp.json`, etc.) leaking per-machine tokens or credentials into repo | mitigate | 10 `.gitignore` patterns added covering all identified dirs; `git check-ignore -v` confirms all patterns active | closed |
| T-26-02-01 | Tampering | Deploy test regex mismatch allows wrong pip invocation form to pass CI undetected | mitigate | Regex relaxed to `\.venv/bin/(?:python -m )?pip install -r requirements\.txt`; both forms now matched; 41 deploy tests green | closed |
| T-26-03-01 | Tampering (XSS / auth bypass) | `{{WEB_AUTH_SECRET}}` literal placeholder leaked into HTMX form `hx-headers` → PATCH sends `{{WEB_AUTH_SECRET}}` → 401 or secret-in-body | mitigate | `_substitute(content, request) -> bytes` helper called on both `_serve_dashboard_content` and `_serve_market_scoped_page` paths; `TestPhase26PlaceholderLeak` (3 tests) asserts zero `{{…}}` markers in served HTML | closed |
| T-26-03-02 | Information Disclosure | `{{WEB_AUTH_SECRET}}` in market-scoped GET response body visible to browser | mitigate | Same `_substitute` helper; resolves before `Response` construction; `TestPhase26PanelPatchSurvives` confirms extracted secret enables real PATCH (not placeholder) | closed |
| T-26-04-01 | Information Disclosure | Header session widget renders `{{SIGNOUT_BUTTON}}{{SESSION_NOTE}}` raw on `/markets/{M}/{fn}` pages | mitigate | `_substitute` resolves both placeholders via `_is_cookie_session(request)` branch; `TestPhase26HeaderSessionWidget` (2 tests) assert correct widget rendered per session type | closed |
| T-26-05-01 | Information Disclosure | `/markets/{M}/{fn}` page renders all markets' signal cards / settings / market-test panels (cross-market data leak) | mitigate | `ctx.active_market` threaded to `render_signal_cards`, `render_settings_tab`, `render_market_test_tab`; each filters `display_names` to active market only; `TestPhase26MarketScoping` (4 tests) assert no cross-market eyebrow in response | closed |
| T-26-06-01 | Tampering | `render_dashboard(htmx_panel_only=True)` returns `str` with `-> None` annotation; caller `.encode()` on `None` is an NPE path if flag branch ever mis-routes | mitigate | Split into `render_dashboard_files() -> None` + `render_panel_html() -> str`; annotation lie eliminated; 323 seam tests green | closed |
| T-26-07-01 | Tampering | `_is_stale(dashboard.html)` gates all siblings; a deploy shipping new sibling HTML but with `dashboard.html` already marker-stamped leaves siblings stale | mitigate | `_is_stale_for(page_output: Path)` parameterised by path; each sibling self-gates on its own marker; test fixture updated | closed |
| T-26-07-02 | Tampering | `add_market` writes `signals[id] = 0` (int); diverges from `run_daily_check` dict shape; renderer's defensive branch could mask future shape bugs | mitigate | `add_market` now writes 7-key dict matching `run_daily_check`; prod write path is shape-consistent; defensive renderer branch retained only for legacy test fixtures (documented in `26-DEBT.md`) | closed |
| T-26-07-03 | Tampering / Information Disclosure | `markets-strip` derives `active_function` from `Referer` header; privacy-mode browsers strip Referer → wrong tab highlighted; Referer is attacker-influenceable | mitigate | `active_function` passed as explicit query param `?active_function={fn_q}` from `nav.py:103-110`; handler reads `request.query_params.get('active_function', 'signals')` with allowlist `{signals, account, settings, market-test}`; Referer fallback removed | closed |
| T-26-07-04 | Tampering | `selected_market` cookie sanitiser strips only `"` and `;`; malformed market_id (whitespace, control chars) reaches state lookup | mitigate | Module-scope `_MARKET_ID_RE = re.compile(r'^[A-Z0-9_]{2,20}$')` on both write path (`_set_market_cookie`) and read path (`get_markets_strip`); forged cookies fall back to first-market | closed |
| T-26-08-01 | Tampering (dead code) | Dead `_render_market_selector` and `_render_dashboard_page_nav` functions accumulate maintenance risk; stale caller comments mislead future readers | mitigate | Both deleted; caller comment at `dashboard.py:1964` updated to reference `render_two_axis_nav`; grep gates confirm 0 residual references | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-26-01 | T-26-01-01 | `auth.json` contains TOTP secret but was never committed to git; lives on local dev FS + production droplet only. No rotation required per operator decision. | operator | 2026-05-07 |
| AR-26-02 | T-26-07-02 | Renderer's defensive `isinstance(int)` branch retained (not deleted) because 38 test sites still seed `state['signals']['SPI200'] = 0` int sentinels. Prod write paths are shape-consistent; branch is unreachable from prod but benign. Cleanup deferred to next renderer-touching phase. | operator | 2026-05-07 |
| AR-26-03 | — (UAT-1) | Cold-start smoke (UAT-1) operator-deferred to deploy-time; not locked by an automated test. Production at `signals.mwiriadi.me` has run cleanly post-deploy (daily emails since 2026-04-29). | operator | 2026-05-07 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-10 | 13 | 13 | 0 | Phase 29 Plan 29-10 retroactive retrofit (mechanical — register authored from plan-time fix shapes + SUMMARY evidence) |

### 2026-05-10 — retroactive retrofit

- **Method:** plan-time register assembled from fix shapes in `26-CONTEXT.md`, `26-PATTERNS.md`, and per-plan SUMMARY files. Each threat entry has a corresponding implementation reference (file:line or test class) confirming the mitigation is in place.
- **Plans 26-03 and 26-06:** pure test scaffolding / refactoring; no new security surface introduced. Threats T-26-03-01 and T-26-06-01 address the correctness risk of the existing bugs these plans fixed.
- **Plan 26-08:** dead-code deletion; no new surface introduced; T-26-08-01 documents the risk mitigation of removing misleading functions.
- **Verification:** `26-VERIFICATION.md` confirms 1794 tests green and 4 audit greps clean at Plan 26-08 closure. All mitigations corroborated.
- **No new threats introduced** beyond what the fix shapes address.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-10 (retroactive retrofit — all mitigations confirmed by 26-VERIFICATION.md)
