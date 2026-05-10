---
phase: 24
slug: v1-2-codemoot-fix-phase
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-10
---

# Phase 24 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Built from post-milestone codemoot review findings (24-REVIEW.md).
> Phase 24 fixed correctness bugs and dead-code; no new attack surface introduced.
> Threats below correspond to the bugs and info-level findings the codemoot identified.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `auth.json` (disk) ↔ in-memory auth state | Persisted timestamps must round-trip without TypeError on naive datetimes | datetime strings, expiry timestamps, device UUIDs |
| `--once` GHA cron path ↔ state persistence | Single-run mode must persist post-push warnings without losing update atomicity | warnings list, state dict |
| `web/routes/totp.py` ↔ `web/routes/login.py` | Redirect-safety check must come from single authoritative source | next_url param, request |
| `web/routes/reset.py` ↔ `web/middleware/auth.py` | Client-IP extraction must come from single authoritative source | X-Forwarded-For, REMOTE_ADDR |
| TOTP/reset HTML renderer ↔ browser | Error strings rendered into HTML must be escaped | error message strings |
| Process timezone ↔ scheduler | Scheduler must reject non-UTC processes at startup | timezone name string |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-24-01-01 | DoS (crash) | `auth_store.py` naive datetime comparison | mitigate | `_ensure_aware()` helper coerces naive ISO timestamps to UTC before comparison; applied at all 3 comparison sites (lines 426, 452, 476) with try/except wrapping | closed |
| T-24-02-01 | Tampering (silent bypass) | `main.py` UTC assertion via `assert` | mitigate | Replaced `assert tzname == 'UTC'` with `raise RuntimeError(...)` — assert is disabled by `python -O` and would silently allow wrong-TZ production runs; regression: `test_scheduler.py::test_non_utc_process_raises` | closed |
| T-24-03-01 | DoS (crash) | `main.py` `--once` weekend AttributeError | mitigate | `once_state is not None` guard before `.get('warnings')` call; `run_daily_check` returns `None` state on weekends; crash confirmed in CR-01 review finding; regression: `test_main.py::test_run_daily_check_does_not_push_on_weekend` | closed |
| T-24-03-02 | Data integrity | `main.py` `--once` warning persistence | mitigate | Uses `state_manager.mutate_state(_apply_once_warnings)` (fcntl LOCK_EX) not `save_state`; prevents lost-update race with concurrent web POST handler | closed |
| T-24-03-03 | Data integrity (race) | `main.py` `--once` lock bypass (WR-01) | accept | Single-operator system; GHA cron and web POST do not realistically run simultaneously; accepted as low-risk given single-user deployment model | closed |
| T-24-04-01 | Tampering (XSS) | `web/routes/totp.py` `error` param unescaped | accept | All current callers pass hardcoded strings ("Code didn't match — try again"); no user-controlled input reaches this path today; XSS risk is future/theoretical; defense-in-depth `html_escape` noted as IN-01 for future implementation (done in Phase 27 via broader XSS audit) | closed |
| T-24-04-02 | Information Disclosure | `web/routes/totp.py` / `web/routes/reset.py` underscore-prefixed cross-module imports | accept | Naming convention violation (WR-03); no security impact — the functions are now part of the public API in practice; naming cleanup deferred | closed |
| T-24-05-01 | Data integrity | Post-push warning persistence gap in scheduler daemon loop (IN-02) | accept | Known design limitation: daemon-loop post-push warnings are lost until next `mutate_state` run; single-operator; warnings are informational (not loss-of-trade); gap documented in 24-REVIEW.md IN-02 | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-24-01 | T-24-03-03 | Single-operator system; GHA cron and web POST handler do not run simultaneously under normal operation. Lock bypass is a theoretical race, not a practical exploit. | operator | 2026-05-01 |
| AR-24-02 | T-24-04-01 | All current `error` callers pass hardcoded strings; no user-controlled input today. XSS risk is future-only. Phase 27 `html_escape` audit closes the broader surface. | operator | 2026-05-01 |
| AR-24-03 | T-24-04-02 | Cross-module underscore-prefix violation (WR-03) is a naming convention issue, not a security vulnerability. Deferred to a future rename pass if API surface expands. | operator | 2026-05-01 |
| AR-24-04 | T-24-05-01 | Scheduler daemon post-push warning gap is a known design limitation. Warnings are informational; no trade or financial data is lost. | operator | 2026-05-01 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-10 | 8 | 8 | 0 | /gsd-secure-phase 29-08 (retroactive mechanical retrofit; findings sourced from 24-REVIEW.md; all dispositions confirmed against 24-VERIFICATION.md and SUMMARY.md) |

### 2026-05-10 — retroactive audit (Phase 29 sweep)

- **Method:** Mechanical retrofit per 29-CONTEXT.md D-07. Each codemoot finding mapped to a STRIDE category and disposition. Mitigations confirmed via 24-VERIFICATION.md (10/10 must-haves verified).
- **No new threats introduced:** Phase 24 contains only bug fixes and dead-code cleanup; no new network endpoints, auth paths, or file-access patterns.
- **XSS surface (T-24-04-01):** IN-01 was not fixed in Phase 24 (hardcoded strings only); Phase 27 `test_html_xss_audit.py` covers the broader dashboard escape surface including TOTP render paths.
- **Lock discipline (T-24-03-02):** `mutate_state` use confirmed by 24-VERIFICATION.md truth #5 (`main.py:1884 — state_manager.mutate_state(_apply_once_warnings)`).

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter
- [x] No new attack surface introduced by Phase 24 (bug-fix only phase)

**Approval:** verified 2026-05-10 (retroactive reconstruction)
