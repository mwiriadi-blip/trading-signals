---
phase: 10
slug: foundation-v1-0-cleanup-deploy-key
status: verified
threats_open: 0
asvs_level: 1
created: 2026-04-24
audit_date: 2026-04-24
threats_found: 14
threats_closed: 14
---

# Phase 10 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Consolidated across Plans 10-01 / 10-02 / 10-03 / 10-04. Where Plan 03 (runtime
> code scope) and Plan 04 (operator documentation scope) address semantically
> overlapping threats (deploy-key handling, commit scope, commit authorship),
> entries cite both plans' mitigations as co-evidence.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| operator CLI args → `main.py::_handle_reset` | Untrusted `--initial-account` string coerced via `float()`; existing math.isfinite guard (Phase 8 D-12) rejects non-finite values | float |
| pytest test process → `subprocess(ruff)` | Test-time subprocess with hardcoded argv list, `shell=False`, `timeout=30` | none (lint only) |
| pytest `tmp_path` fixture → temp filesystem | Pytest-managed isolated temp dir, hardcoded 2-line Python probe, auto-cleaned | static string |
| droplet process → `subprocess(git)` | list-form argv, `shell=False`, `capture_output=True`, explicit timeouts (30s diff/commit, 60s push) | `state.json` diff |
| droplet process → github.com via SSH | Authenticated by operator-configured ed25519 deploy key (SETUP-DEPLOY-KEY.md); key private material never touched by runtime code | commit + push payload |
| operator droplet filesystem → deploy-key private material | `~/.ssh/id_ed25519_trading_signals` mode 0600; `~/.ssh/` mode 0700; never committed | key bytes (operator-held) |
| `state['warnings']` write path | ONLY via `state_manager.append_warning` (sole-writer invariant, Phase 8 D-08) | warning records |
| Planning-doc prose (CLAUDE.md / PROJECT.md / SETUP-DEPLOY-KEY.md) → future readers | Documentation-only; no executable code | operator runbook text |

---

## Threat Register

| Threat ID | Plans | Category | Component | Disposition | Mitigation | Evidence | Status |
|-----------|-------|----------|-----------|-------------|------------|----------|--------|
| T-10-BUG-01 | 10-01 | Tampering | `state.json` invariant (`account` vs `initial_account`) | mitigate | D-01 call-site fix in `main.py::_handle_reset` + D-02 `state_manager.reset_state(initial_account=...)` signature extension; 7 regression tests | `state_manager.py:304` `def reset_state(initial_account: float = INITIAL_ACCOUNT)`; `main.py:1497` `state['account'] = float(initial_account)  # Phase 10 BUG-01 D-01`; `tests/test_state_manager.py::TestResetState` (4 tests); `tests/test_main.py::TestHandleReset` at line 1495 (3 tests) | closed |
| T-10-BUG-02 | 10-01 | Information Disclosure | None identified | accept | Plan 01 touches no secrets, no network, no new logs beyond existing `[State] state.json reset (...)` line | See Accepted Risks Log | closed |
| T-10-CHORE-01 | 10-02 | DoS (test-runtime) | `subprocess.run(['ruff', ...])` | mitigate | `timeout=30` explicit per invocation; argv list-form (no `shell=True`); ruff pinned 0.6.9 in requirements.txt | `tests/test_notifier.py:1996` and `:2048` both show `timeout=30`; `tests/test_notifier.py:1966` `def test_ruff_clean_notifier` | closed |
| T-10-CHORE-02 | 10-02 | Tampering (command injection) | subprocess argv | accept | argv is fully hardcoded list literal `['ruff', 'check', 'notifier.py', '--output-format=json']` — no string concat, no user input, `shell=False` implicit | See Accepted Risks Log | closed |
| T-10-CHORE-03 | 10-02 | Tampering (temp-file write) | `tmp_path` fixture in F401 sensitivity test | accept | pytest built-in `tmp_path`, test-isolated, auto-cleaned, hardcoded 2-line Python probe content | See Accepted Risks Log | closed |
| T-10-01 | 10-03 + 10-04 | Information Disclosure | Deploy-key private material | mitigate | **Runtime (Plan 03):** `_push_state_to_git` helper never reads, logs, or touches the private key — only invokes `git` which delegates auth to the OS SSH layer. grep `grep -rn 'id_ed25519\|private_key\|BEGIN OPENSSH' main.py` returns zero matches. **Operator (Plan 04):** `SETUP-DEPLOY-KEY.md` Step 1 mandates `chmod 0600` on key files, `chmod 0700` on `~/.ssh/`, and explicit "MUST NOT leave the droplet / MUST NOT be committed" banner | `main.py:191-397` helper body contains zero key references; `SETUP-DEPLOY-KEY.md:50-52, 58-60` file modes + commit ban | closed |
| T-10-02 (runtime) | 10-03 | Tampering (command injection) | subprocess argv construction in `_push_state_to_git` | mitigate | All argv is hardcoded list literal — no string concatenation, no `shell=True`, no user-supplied input. `user.email` and `user.name` are hardcoded string literals in `main.py` (NOT from env vars, NOT from state) | `main.py:236-240` diff argv; `main.py:288-296` commit argv with inline `-c user.email=droplet@trading-signals -c user.name=DO Droplet`; `main.py:350-355` push argv; `grep 'shell=True' main.py` returns zero | closed |
| T-10-02 (operator) | 10-04 | Elevation of Privilege | SSH agent offering wrong key | mitigate | `SETUP-DEPLOY-KEY.md` Step 3 mandates `IdentitiesOnly yes` + explicit `IdentityFile` in `~/.ssh/config`. Prevents SSH from offering every key in agent and hitting "Too many authentication failures" cap | `SETUP-DEPLOY-KEY.md:100` `IdentitiesOnly yes`; `:109-112` pitfall prose | closed |
| T-10-03 | 10-03 + 10-04 | Tampering (unintended commit scope / wrong-repo push) | `git commit` positional arg and `git remote set-url` | mitigate | **Runtime (Plan 03):** commit argv includes EXPLICIT `'state.json'` path positional arg (never `-A`, `.`, or `-a`). Asserted by `test_happy_path_commits_with_inline_identity_and_pushes`. **Operator (Plan 04):** Step 4 uses explicit `git@github.com:<owner>/trading-signals.git` and requires operator to substitute `<owner>`, followed by `git remote -v` verification | `main.py:293-295` `'commit', '-m', 'chore(...)', 'state.json'`; `tests/test_main.py:2048` `test_happy_path_commits_with_inline_identity_and_pushes`; `SETUP-DEPLOY-KEY.md:125-127` `git remote set-url` + verify | closed |
| T-10-04 | 10-03 + 10-04 | Tampering (commit message injection) / Repudiation (commit authorship) | `git commit -m` message + identity flags | mitigate | **Runtime (Plan 03):** commit message is a hardcoded string literal `'chore(state): daily signal update [skip ci]'` — NEVER templated with state contents or env vars; identity inline via `-c user.email=droplet@trading-signals -c user.name=DO Droplet` hardcoded string literals. **Operator (Plan 04):** Step 6 asserts operator sees this exact author line in `git log -1` post-bootstrap | `main.py:294` `'-m', 'chore(state): daily signal update [skip ci]'`; `main.py:291-292` identity flags; `SETUP-DEPLOY-KEY.md:174-176` expected `git log -1` author line | closed |
| T-10-05 (runtime) | 10-03 | Information Disclosure | stderr excerpt logged on subprocess failure | accept | stderr truncated to 200 chars and logged at ERROR level. Deploy-key auth produces no tokens in error messages. Documented for post-deploy watch | See Accepted Risks Log | closed |
| T-10-05 (operator) | 10-04 | DoS (retirement reversible) | Accidental abandonment of GHA rollback path | accept | D-18(a) + D-17: workflow file renamed `.disabled` (not deleted); GitHub repo secrets (`RESEND_API_KEY`, `SIGNALS_EMAIL_TO`) preserved. SETUP-DEPLOY-KEY.md Pitfalls §Rollback documents one-commit reversal | See Accepted Risks Log | closed |
| T-10-06 | 10-03 + 10-04 | DoS (subprocess hang) / Information Disclosure (stale operator docs) | subprocess timeouts / docs/DEPLOY.md staleness | mitigate | **Runtime (Plan 03 — subprocess hang):** every `subprocess.run` has explicit `timeout=` kwarg (30s diff+commit, 60s push). `TimeoutExpired` caught per subcommand → `append_warning` + return. **Operator (Plan 04 — stale docs):** `SETUP-DEPLOY-KEY.md` opens with "Read first: docs/DEPLOY.md is stale" blockquote and Pitfalls section includes an explicit staleness entry. CLAUDE.md + PROJECT.md prose also carry the staleness note | `main.py:239, 299, 354` `timeout=30/30/60`; `main.py:255, 318, 373` `except subprocess.TimeoutExpired`; `SETUP-DEPLOY-KEY.md:15-22` upfront stale banner; `:221-229` Pitfalls entry; `CLAUDE.md:46` + `.planning/PROJECT.md:77` staleness pointers | closed |
| T-10-07 | 10-03 | Sole-writer violation (`state['warnings']`) | `_push_state_to_git` failure path | mitigate | Failure path calls `state_manager.append_warning` (the sole-writer API from Phase 8 D-08); never mutates `state['warnings']` directly. Grep-asserted: 9 `source='state_pusher'` occurrences in `main.py`, zero `state['warnings'].append(` in `_push_state_to_git` body | `grep -n "state\['warnings'\]\.append" main.py` returns zero matches; `main.py` 9 occurrences of `source='state_pusher'` (lines 250, 260, 274, 310, 323, 337, 366, 378, 391); `state_manager.py:431` `def append_warning(state, source, message, now=None)` signature | closed |
| T-10-08 | 10-03 | Repudiation (misattributed commit-vs-push failure) | logger diagnostic output on failure | mitigate | Commit and push each sit in independent `try/except` clauses so the logged verb names the failing subcommand unambiguously. Regression-asserted by two dedicated tests | `main.py:303-304` `'[State] git commit failed'`; `main.py:359-360` `'[State] git push failed'`; `main.py:247` `'[State] git diff failed'`; `tests/test_main.py:2085` `test_push_failure_logs_error_and_appends_warning`; `tests/test_main.py:2138` `test_commit_failure_logs_error_and_appends_warning` | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Unregistered Flags

None. Only `10-01-SUMMARY.md` declares a `## Threat Flags` section, with value "None." `10-02-SUMMARY.md`, `10-03-SUMMARY.md`, and `10-04-SUMMARY.md` did not flag new attack surface during execution. All executor-observed behaviors map back to the 14 registered threats above.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-10-BUG-02 | T-10-BUG-02 | Plan 10-01 is a pure-logic bug fix. No secrets, no network, no file system paths beyond the existing `state.json` write inside `_handle_reset`. No new logs beyond the pre-existing `[State] state.json reset (...)` INFO line. No attack surface introduced. | gsd-security-auditor | 2026-04-24 |
| R-10-CHORE-02 | T-10-CHORE-02 | subprocess argv in `test_ruff_clean_notifier` is a fully-hardcoded list literal `['ruff', 'check', 'notifier.py', '--output-format=json']`. No string concatenation, no user-supplied path, `shell=False` implicit. ASVS L1 test-only surface. | gsd-security-auditor | 2026-04-24 |
| R-10-CHORE-03 | T-10-CHORE-03 | `tmp_path` is a pytest built-in fixture — path is test-isolated and auto-cleaned. The F401 sensitivity probe content is a hardcoded 2-line Python string literal (`'''docstring'''\nimport os\n`) written into the fixture path. ASVS L1 test-only surface. | gsd-security-auditor | 2026-04-24 |
| R-10-05-runtime | T-10-05 (Plan 03 scope) | stderr is truncated to 200 chars and logged at ERROR level on `git diff` / `git commit` / `git push` failure. Deploy-key SSH auth does NOT produce token-bearing error messages (unlike OAuth or PAT-based flows), so the chance of a 200-char excerpt leaking a secret is low. Logged to stderr / systemd journal (operator-visible, not shipped externally). Monitor post-deploy; if a credential-bearing message is ever observed, redact further. | gsd-security-auditor | 2026-04-24 |
| R-10-05-operator | T-10-05 (Plan 04 scope) | Retiring GHA cron via `.disabled` suffix (not file deletion) plus preserving GitHub repo secrets (`RESEND_API_KEY`, `SIGNALS_EMAIL_TO`) per D-17 keeps rollback to a single-commit `git mv` reversal. No code path depends on `daily.yml.disabled`'s absence. The README badge rendering "no recent runs" post-retirement is the intended visual signal per D-18(a). Accepted as operational posture. | gsd-security-auditor | 2026-04-24 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-24 | 14 | 14 | 0 | gsd-security-auditor (Claude Opus 4.7) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-04-24
