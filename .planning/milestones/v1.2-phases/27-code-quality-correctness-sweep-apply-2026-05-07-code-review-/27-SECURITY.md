---
phase: 27
slug: code-quality-correctness-sweep-apply-2026-05-07-code-review
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-08
---

# Phase 27 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Built from plan-time `<threat_model>` blocks across 14 sub-plans (27-01 … 27-14).
> Plans 27-06, 27-12, 27-13, 27-14 declared `N/A` (read-only flag / pure code reorganisation).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `state.json` (disk) ↔ in-memory state | Persisted state must round-trip without precision loss; schema version must fail loud | Decimal money values, datetime, signals, warnings |
| `pnl_engine` ↔ `sizing_engine` indicator math | Decimal must NOT leak into numpy/pandas hot path | money values |
| `state.json` money → dashboard JSON wire | Decimal must serialize via str/float, never raw | money values (JSON-encoded) |
| droplet → Resend / yfinance APIs | Outbound HTTPS must not hang indefinitely | request/response bodies, secrets |
| Application logs (stdout/stderr/journalctl) | No plaintext secrets; tail-able by ops or backup | log lines |
| Crash-email body / `last_crash.json` (disk) | Operator inbox + dashboard banner; must escape and redact | tracebacks, exception text |
| HTTP path/query/cookie → market lookup | Untrusted input must not bypass routing or hit unintended state keys | `selected_market` cookie, instrument id |
| yfinance / Resend / cookie input → rendered HTML | Untrusted strings escaped before reaching `<body>` | warning strings, market id |
| Source tree → public GitHub repo | Constants in source are publicly visible; no operator PII | source files |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-27-01-01 | Tampering | Money values silently drift via float ULP across saves | mitigate | Decimal in-memory + str-on-disk; `test_state_no_drift_on_repeated_save_load_cycle` (5 round-trips, cent-exact) | closed |
| T-27-01-02 | DoS | Decimal arithmetic ~10× slower than float | accept | Bounded to pnl_engine + state-save path; indicator math (numpy/pandas) untouched; <1ms total impact | closed |
| T-27-01-03 | DoS | Dashboard JSON serialization crashes on raw Decimal → 500 | mitigate | `_decimal_default` encoder + pre-coercion; `test_dashboard_json_dumps_handles_decimal` | closed |
| T-27-02-01 | DoS (self) | Daily run hangs forever on stuck network — crash-email never fires | mitigate | `HTTP_TIMEOUT_S=30` forces TimeoutError → bubbles to crash-email path; AST-walker prevents regression | closed |
| T-27-02-02 | Tampering (constant drift) | Two competing timeout constants drift apart | mitigate | `_RESEND_TIMEOUT_S` deleted; single source of truth enforced by grep gate | closed |
| T-27-03-01 | Information Disclosure | `RESEND_API_KEY` in journalctl after Resend 401 → leaks to log archives | mitigate | `redact_secret` on every log emission of api_key; defense-in-depth `body.replace`; 7-test regression suite | closed |
| T-27-03-02 | Information Disclosure | TOTP secret in `auth_store` logs | mitigate | Audit complete; no raw secret interpolation; structural grep-gate test pins the contract | closed |
| T-27-03-03 | Repudiation | Operator denies a key was leaked when it was | accept | Out of scope — single-operator system; no chain-of-custody requirement | closed |
| T-27-04-01 | Tampering | Attacker submits `SPI200X` to `/markets/SPI200X/signals` — too-loose regex matches | mitigate | Two-layer: `INSTRUMENT_ID_RE.fullmatch` + Pydantic pattern `^[A-Z0-9_]{2,20}$` (Layer 1) + `is_known_market(id)` membership (Layer 2); AST-walker | closed |
| T-27-04-02 | Spoofing | N/A | accept | No spoofing surface introduced | closed |
| T-27-05-01 | Information Disclosure | Operator's email leaked in repo source | mitigate | Constant deleted; env-var only; `test_no_literal_operator_email_in_notifier` regression | closed |
| T-27-05-02 | DoS / silent failure | Env var missing in production → emails silently dropped | mitigate | ERROR log + state-health warning marker on dashboard health strip; Plan 27-11 `last_crash.json` provides additional fallback | closed |
| T-27-07-01 | Tampering (self) | Future contributor adds `_migrate_vN_to_vN+1` but skips `_MIGRATIONS` registration | mitigate | `_assert_migration_chain_contiguous` fails at module load AND at `load_state` entry | closed |
| T-27-07-02 | Tampering | Naive datetime persisted, later compared with tz-aware → silent ordering bug | mitigate | `_assert_tz_aware` gate; legacy data warned and coerced | closed |
| T-27-07-03 | DoS | Module-load + `load_state` checks have tiny cost | accept | <1ms; runs once per process + per `load_state` call | closed |
| T-27-08-01 | Tampering (XSS) | Attacker controls yfinance ticker error string with `<script>` → dashboard warnings panel | mitigate | `_e()` escape on render; `test_xss_warning_field_escaped` + `test_xss_warning_field_escaped_in_email` | closed |
| T-27-08-02 | Tampering (XSS) | `selected_market` cookie bypasses regex, reaches renderer un-escaped | mitigate | Defense-in-depth — regex-validated AND escaped at render; `test_xss_market_id_escaped_in_market_strip` | closed |
| T-27-08-03 | DoS / UX | Mechanical bulk-escape double-escapes trusted fragment | mitigate | Render-variable taxonomy + 4 anti-double-escape tests assert markers stay raw, `&lt;` absent | closed |
| T-27-09-01 | DoS | Legacy `state.json` bare-int signals + renderer cleanup → AttributeError | mitigate | `_migrate_v9_to_v10` runs at every `load_state`; 3 migration + 1 idempotency + 3 chain-contiguity tests | closed |
| T-27-09-02 | Tampering | N/A | accept | No tampering surface introduced | closed |
| T-27-10-01 | DoS (self) | Unbounded warnings list grows → `state.json` bloats | mitigate | `MAX_WARNINGS = 50` at single chokepoint `state_manager.append_warning`; `test_warnings_fifo_does_not_exceed_max` + AST gate vs duplicate constant | closed |
| T-27-10-02 | Data integrity (trading) | Look-ahead bias → optimistic backtests don't replicate live | mitigate | 5 future-bar shock tests in `tests/test_lookahead_bias.py::TestSignalIndependentOfFutureBars` — all green on canonical fixture | closed |
| T-27-11-01 | DoS / silent failure | Resend outage during a crash → operator never sees crash | mitigate | `last_crash.json` fallback + dashboard banner; operator sees on next visit | closed |
| T-27-11-02 | Tampering (XSS) | `exception_message` contains attacker-controlled HTML | mitigate | `_e()` escape on render (Plan 27-08 coverage extends to crash banner) | closed |
| T-27-11-03 | Information Disclosure | `last_crash.json` on disk contains api_key in traceback | mitigate | Pre-write `_redact_secrets_in_text` (pattern walk: `re_*`, `sk_*`, `Bearer *`) + `redact_secret`; test asserts | closed |
| T-27-11-04 | Tampering | Hardcoded crash-path conflicts with repo file-placement / drifts local↔droplet | mitigate | `LAST_CRASH_FILE` configurable in `system_params`; defaults to `STATE_DIR` (same as state.json); env-var override resolver | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

**Plans with `<threat_model>N/A</threat_model>`:** 27-06 (deferred yfinance + `--version` flag), 27-12 (notifier split), 27-13 (main split), 27-14 (dashboard split). Pure code reorganisation / read-only print — XSS / redact-secret / FIFO bounds from Waves 1–2 are PRESERVED across the splits.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-27-01 | T-27-01-02 | Decimal ~10× slower than float; bounded to ~hundreds of money ops/day; indicator math untouched. | operator | 2026-05-07 |
| AR-27-02 | T-27-03-03 | Single-operator system; no chain-of-custody / non-repudiation requirement. | operator | 2026-05-07 |
| AR-27-03 | T-27-04-02 | No spoofing surface — instrument id is opaque path component, not authenticated identity. | operator | 2026-05-07 |
| AR-27-04 | T-27-07-03 | <1ms cost; runs once per process + per `load_state`; dwarfed by I/O. | operator | 2026-05-07 |
| AR-27-05 | T-27-09-02 | No tampering surface introduced — bare-int → dict promotion is purely shape-normalising. | operator | 2026-05-07 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-08 | 26 | 26 | 0 | /gsd-secure-phase 27 (short-circuit: register_authored_at_plan_time=true, all SUMMARY-level threat-surface scans confirm closure) |

### 2026-05-08 — initial audit

- **Method:** plan-time register short-circuit. Each sub-plan (27-01 through 27-14) authored a `<threat_model>` block; each corresponding `SUMMARY.md` carries an explicit threat-surface scan confirming MITIGATED / ACCEPTED disposition with named regression test or rationale.
- **Plans 27-06 / 27-12 / 27-13 / 27-14:** declared N/A (pure refactor / read-only flag); plan-time invariants from Waves 1–2 (XSS escape, redact_secret, FIFO bound) are preserved by the splits per their plan threat-model blocks.
- **No new threats introduced**; no auditor-spawn required under the `register_authored_at_plan_time && threats_open=0` short-circuit rule of `secure-phase.md` Step 3.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-08
