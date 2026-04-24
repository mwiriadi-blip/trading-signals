---
phase: 12
reviewers: [gemini, codex]
reviewed_at: 2026-04-25T00:00:00+08:00
plans_reviewed: [12-01-PLAN.md, 12-02-PLAN.md, 12-03-PLAN.md, 12-04-PLAN.md]
self_cli_skipped: claude
---

# Cross-AI Plan Review — Phase 12

## Gemini Review

### Summary
The implementation plans for Phase 12 are exceptionally well-structured and technically sound. They systematically address the transition from an email-only CLI to a hosted web workstation by wiring nginx, Let's Encrypt, and domain-driven email with a high degree of defensive engineering. The strategy correctly isolates the repo-managed 443 block while delegating the 80-block redirect to Certbot, avoiding common state-machine conflicts. The refactor of SIGNALS_EMAIL_FROM is comprehensive, covering all four usage sites (including the often-overlooked footer renderer) while maintaining strict architectural boundaries and testing determinism.

### Strengths
- **Nginx Pitfall Mitigation:** Correct use of the `always` flag for security headers and placement at server scope to prevent child-location clobbering.
- **Gated Deployment:** deploy.sh hook uses `command -v nginx` and file-existence checks — pre-Phase-12 droplets continue to deploy cleanly.
- **Cross-Artifact Drift Guards:** TestCrossArtifactDriftGuard enforces consistency between runbook and artifacts.
- **Security Posture:** Mozilla Intermediate TLS profile + absolute-path sudoers rules provides ASVS L1 compliance without excessive complexity.
- **Testing Determinism:** Module-level autouse fixture elegantly handles the `compose_email_body` signature change.

### Concerns
- `LOW`: SendStatus discipline — plans correctly stick to 2-field NamedTuple; D-14's `attempts=0` properly rejected.
- `LOW`: Sudoers path sensitivity — Ubuntu's `/usr/sbin/nginx` vs `/usr/bin/nginx` is a common failure point; plan mitigates via `which nginx` verification.
- `LOW`: ACME rate-limiting — 10MB zone size for healthz is large (~80k states) but harmless as "production-ready" default.

### Suggestions
- **Regenerator Idempotency:** After first regeneration, perform `git status` immediately to confirm byte-identical output — any diff signals a logic regression.
- **Certbot Staging:** SETUP-HTTPS.md troubleshooting should explicitly encourage `--staging` flag if operator needs >5 attempts per week.

### Risk Assessment: LOW
Phase is well-de-risked through isolated wave structure, regression safety, operator-friendly runbook, and zero new dependencies.

---

## Codex Review

### 12-01-PLAN.md
**Summary:** Strong plan with unusually good specificity around nginx invariants, certbot ownership boundaries, and regression protection. The TDD shape is sound. The main weakness is that it mixes an nginx `http{}`-scope directive (`limit_req_zone`) into a standalone site file without fully resolving how that file will actually be included, which is the single biggest correctness risk in the phase.

**Strengths**
- Clear separation of certbot-owned vs repo-owned concerns.
- HSTS pinned to exact value + `! preload` negative test.
- Server-scope `add_header` with `always` flag.
- ACME carve-out explicitly tested.
- Wave 0 RED/GREEN discipline makes drift visible early.

**Concerns**
- `HIGH`: `limit_req_zone` is only valid in `http` context, but the committed artifact is `nginx/signals.conf` intended for sites-available. If copied verbatim into a server-context include path, nginx will reject it.
- `HIGH`: "Contains ONLY a 443 server block" conflicts with "top-level `limit_req_zone`" — will confuse implementation/testing.
- `MEDIUM`: Certbot `--nginx` patch assumption — usually fine but not guaranteed for nonstandard include layouts.
- `MEDIUM`: Cipher suite pinning too literal — Mozilla recommendations change; exact cipher string increases drift risk.
- `LOW`: ACME carve-out inside 443-only block is conceptually muddled (HTTP-01 runs on port 80).
- `LOW`: HSTS-not-in-location test uses simplistic text splitting — may false-positive on future comments.

**Suggestions**
- Split `limit_req_zone` out: either separate file `nginx/conf.d/healthz-rate-limit.conf` OR runbook instructions for `/etc/nginx/nginx.conf http{}`.
- Reword "ONLY a 443 server block" to acknowledge top-level directives at include-scope.
- Loosen TLS validation from exact cipher string to protocol/session assertions.
- Add plan-level note on where certbot mutations land.
- Add verification item that `nginx -t` on installed config is the real acceptance gate, not just pytest text checks.

**Risk:** MEDIUM — design intent solid but `limit_req_zone` context issue is a deployment blocker if unresolved.

### 12-02-PLAN.md
**Summary:** Best of the four. Correctly identifies the real refactor surface in notifier.py, preserves the SendStatus two-field contract, careful not to cascade into unrelated changes. The biggest gap is a wording-level divergence from D-14's `append_warning` text — the plan delegates warning maintenance to orchestration rather than appending in notifier, which is probably correct but should be called out as intentional.

**Strengths**
- Rejects `attempts=0` scope creep.
- Accurately traces real `_EMAIL_FROM` edit surface including footer + crash email.
- Per-dispatch env-var read (not import time).
- Clean `compose_email_body(..., *, from_addr=...)` threading.
- Autouse fixture + regen script for golden determinism.
- Early return on missing sender preserves Phase 8 two-saves-per-run invariant.
- Blocks fallback to onboarding@resend.dev.

**Concerns**
- `MEDIUM`: Plan behavior differs from D-14 wording — returns `ok=False` and delegates warning to orchestration rather than calling `append_warning` in notifier. Likely right design, but should be marked intentional.
- `MEDIUM`: Autouse fixture is broad — stabilizes tests but can hide call sites that should explicitly pass `from_addr`.
- `LOW`: Plan oscillates between "3 sites" / "4 sites" / "4+ sites" wording — internally adequate but slightly inconsistent.
- `LOW`: Missing-sender tests don't directly assert `last_email.html` is not written — matters for the no-side-effects claim.

**Suggestions**
- Add note: "D-14 warning persistence is preserved by `main._dispatch_email_and_maintain_warnings`, not by notifier directly, to maintain the two-saves-per-run invariant."
- Add test: missing sender does not create/update `last_email.html`.
- Add grep: all `compose_email_body(` call sites pass `from_addr=...`.
- Narrow autouse fixture scope if possible, or add comment on deliberate breadth.
- Direct crash-email test for missing-sender parity.

**Risk:** LOW — careful, bounded, preserves important invariants.

### 12-03-PLAN.md
**Summary:** Pragmatic extension of existing deploy path. Gating logic is appropriate, ordering is right, security posture is materially better than unconditional reload. The main issue is that the plan slightly under-specifies the privilege boundary: the deploy script uses PATH-relative commands while the security guarantee depends on exact absolute-path sudoers entries, so the doc/test story has to stay very tight.

**Strengths**
- Correct ordering: restart services → smoke-test → reload nginx.
- Gate condition protects pre-Phase-12 droplets.
- `sudo -n` is right choice; fast-fail beats hanging.
- Reload not restart (correct lower-risk operation).
- Good negative assertion against pre-gate nginx references.

**Concerns**
- `MEDIUM`: `sudo -n nginx -t` relies on root's secure_path resolving the same binary path documented in sudoers.
- `MEDIUM`: Privilege surface expands from 2 to 4 sudoable commands — risk justification deferred to doc quality rather than code constraints.
- `LOW`: Gate checks for repo file existence, not installed site enablement. Reload may run even if operator never symlinked — harmless but gating semantics weaker than implied.
- `LOW`: Tests are text-structural only; don't validate shell-correctness beyond `bash -n`.

**Suggestions**
- Plan note: PATH-relative invocation acceptable only because sudoers pins fixed absolute commands and Ubuntu secure_path includes `/usr/sbin`.
- Plan 04 should require verifying `sudo -n nginx -t` before first deploy after sudoers change.
- Document that gate is "Phase artifact present + nginx installed", not "site active".
- Add test: reload block is wrapped in a single `if ... fi`.

**Risk:** MEDIUM — reasonable implementation, but privileged surface is increasing.

### 12-04-PLAN.md
**Summary:** Good documentation-and-drift-control plan. The cross-artifact guard is exactly right. Main concern is that the doc locks in operational details that may not match deployed filesystem conventions elsewhere, especially the `.env` path and certbot behavior. Tests are strong but some are brittle.

**Strengths**
- Cross-artifact drift guard for critical sync points.
- Troubleshooting section covers real failure modes.
- Anti-pattern warnings useful and security-relevant.
- Manual verification maps to SC-1..4.
- Wave 3 dependency correct.

**Concerns**
- `HIGH`: [ORCHESTRATOR NOTE: **FALSE POSITIVE after verification**] Codex claimed SETUP-HTTPS.md uses `/home/trader/trading-signals/.env` but Phase 11 uses `/etc/trading-signals/.env` — this is a path drift risk. **Verification finding:** Phase 11's actual `systemd/trading-signals-web.service` contains `EnvironmentFile=-/home/trader/trading-signals/.env`, and Plan 04's SETUP-HTTPS.md references the same path. **No drift exists.** Codex appears to have hallucinated the `/etc/trading-signals/.env` reference (likely from an earlier mental model of the canonical path).
- `MEDIUM`: Plan requires `certbot --nginx --dry-run` first — operationally sensible, but doc should separate "nginx syntax valid" from "certbot can patch it".
- `MEDIUM`: Drift guard validates textual presence not semantic correctness — e.g., checks env-var name but not that documented .env path matches actual systemd `EnvironmentFile=`.
- `LOW`: Doc prescribes exact outputs (nginx/certbot versions, issuer CN examples) that may vary.
- `LOW`: Rollback wording around deploy gate slightly inaccurate — gate depends on repo file + binary, not symlink.

**Suggestions**
- [ORCHESTRATOR OVERRIDE: `.env` path fix not needed — no drift exists.]
- Extend TestCrossArtifactDriftGuard to assert `.env` path in doc matches `EnvironmentFile=` in systemd unit (belt-and-braces against future drift).
- Relax tests depending on exact version examples or LE issuer CNs.
- Add doc note: "certbot-managed edits will modify the installed file, not the committed repo artifact."
- Clarify rollback semantics for deploy gating vs site activation.

**Risk:** MEDIUM-HIGH per codex (driven by the claimed `.env` drift). **Corrected risk after orchestrator verification: LOW-MEDIUM.**

### Cross-Plan Assessment (Codex)

**Success Criteria Traceability:** Generally strong. SC-1/SC-2 well covered operationally. SC-3 **appears** under-traced due to claimed env-file inconsistency (false positive — see override above). SC-4 well handled for "no silent fallback".

**ASVS L1 / Security:** Close to reasonable posture. Needs tightening on: env-file canonical path (false positive), `limit_req_zone` context correctness, sudoers exact-path story across code + docs.

**Overall Recommendation (Codex):** 12-02 ready as-is. 12-03 acceptable with minor security wording. 12-01 needs revision (`limit_req_zone` context). 12-04 needs revision (`.env` path — **corrected: no revision needed**).

---

## Orchestrator Verification Notes

Two of codex's HIGH findings were verified against the live codebase. One is legitimate (partially — requires wording clarification, not structural change). One is a false positive.

### Verified HIGH → downgraded to MEDIUM

**Codex HIGH #1 — 12-01 `limit_req_zone` context:** The directive IS valid at the top of `nginx/signals.conf` IF the file is included from nginx.conf's `http{}` block (standard Ubuntu `include /etc/nginx/sites-enabled/*;` convention). The actual directive placement is correct — nginx parses included files at the parent scope, so `limit_req_zone` at the top of signals.conf ends up at http-scope.

**However**, the plan's truth statement "contains ONLY a 443 server block" is inconsistent with "top-level `limit_req_zone` directive". This is a wording/clarity issue worth fixing to prevent confusion during implementation or future edits. The structural correctness is fine; the documentation needs the qualifier "plus any required top-level directives that are valid at include-scope".

**Severity: MEDIUM (wording), not HIGH (structural).**

### Verified HIGH → false positive

**Codex HIGH #2 — 12-04 `.env` path drift:** Grep confirmed both files use `/home/trader/trading-signals/.env`:
- `systemd/trading-signals-web.service`: `EnvironmentFile=-/home/trader/trading-signals/.env`
- `12-04-PLAN.md` SETUP-HTTPS.md §7: `/home/trader/trading-signals/.env`

Codex's claim that Phase 11 uses `/etc/trading-signals/.env` is incorrect. There is no drift. The path has been `/home/trader/trading-signals/.env` since Phase 11 landed.

**Severity: FALSE POSITIVE — no revision needed on this axis.**

---

## Consensus Summary

### Agreed Strengths
- **3-site `_EMAIL_FROM` refactor** identified correctly by both reviewers (line 99 + `_render_footer_email` + `_post_to_resend`).
- **`SendStatus` stays 2-field** — both reviewers agree `attempts=0` is scope creep.
- **Nginx 443-block-only + certbot injects port-80** — correct boundary by both reviewers.
- **Cross-artifact drift guards** — both call out as high-signal.
- **Wave structure** — both agree parallelization is appropriate.
- **ASVS L1 posture** — both view as suitable for single-operator scope.

### Agreed Concerns
- **🟡 MEDIUM — 12-01 `limit_req_zone` wording clarity** (codex HIGH after verification → MEDIUM): Plan's "ONLY 443 server block" statement contradicts the top-level `limit_req_zone` directive. Fix: reword truth statement to acknowledge the include-scope directive. Add `nginx -t` acceptance gate per codex.
- **🟡 MEDIUM — 12-02 D-14 wording divergence** (codex): Plan delegates warning to orchestration (correct per research) but doesn't explicitly call this out as intentional vs D-14 text. Fix: add one note in Plan 02 `<action>` calling out the orchestrator-not-notifier warning path.
- **🟡 MEDIUM — 12-03 sudoers PATH-relative explanation** (codex): `sudo -n nginx -t` works because Ubuntu's secure_path includes `/usr/sbin`, but this is implicit. Fix: add one plan-level comment + ensure SETUP-HTTPS.md §4 includes `sudo -n nginx -t` verification step.
- **🟢 LOW — 12-01 cipher suite pinning** (codex): hard-pinning exact Mozilla Intermediate cipher string increases drift risk. Fix: loosen TLS test to assert protocol (TLSv1.2/1.3) + session settings + modern-posture markers, not exact cipher string.
- **🟢 LOW — 12-02 missing-sender `last_email.html` assertion** (codex): tests don't assert no disk write on missing-sender path. Fix: add `assert not last_email_path.exists()` to `test_missing_env_var_skips_email_with_warning`.
- **🟢 LOW — 12-04 version examples brittleness** (codex): exact nginx/certbot version + LE issuer CN examples may vary. Fix: relax tests that depend on exact versions; assert shape-of-output not literal strings.
- **🟢 LOW — 12-02 autouse fixture breadth** (codex): may hide tests that should explicitly pass `from_addr`. Fix: add comment documenting deliberate breadth + consider narrower scope if feasible.
- **🟢 LOW — 12-02 wording oscillation between "3 sites" / "4 sites"** (codex): internal inconsistency. Fix: pick one count + use it consistently.

### Divergent Views
- **Overall risk:** gemini LOW, codex MEDIUM (driven by two HIGHs — one downgraded, one false positive). After orchestrator verification: **LOW-MEDIUM.** Closer to gemini's read.
- **Env-file path drift:** codex flagged as HIGH; verification shows NO drift. Discard this finding.
- **Regenerator idempotency check** (gemini suggested): codex did not flag. Worth adopting — a `git status` after first regeneration catches unintentional byte changes.
- **Certbot staging recommendation** (gemini): codex did not flag. Worth adopting for SETUP-HTTPS.md troubleshooting.

### Recommended Revision (for `/gsd-plan-phase 12 --reviews`)

**Must-fix (MEDIUM):**
1. **[12-01]** Reword "ONLY a 443 server block" truth to acknowledge top-level `limit_req_zone` is valid at include-scope. Add `nginx -t` acceptance gate (in addition to pytest text checks).
2. **[12-02]** Add explicit note in `<action>`: "D-14 warning persistence is preserved by `main._dispatch_email_and_maintain_warnings` (orchestrator), not by notifier directly — intentional design to preserve Phase 8 W3 two-saves-per-run invariant."
3. **[12-03]** Add plan-level comment + SETUP-HTTPS.md §4 verification that `sudo -n nginx -t` works before first deploy after sudoers change. Document gate semantics explicitly.

**Should-fix (LOW):**
4. **[12-01]** Loosen TLS cipher validation to protocol/session/posture markers rather than exact Mozilla Intermediate cipher string.
5. **[12-02]** Add assertion that missing-sender path does NOT write `last_email.html`. Add grep for all `compose_email_body(` call sites passing `from_addr=...`.
6. **[12-02]** Pick one consistent count ("4 edit sites") and use it throughout. Add comment on autouse fixture breadth.
7. **[12-02]** Add direct crash-email missing-sender test (parity with daily-email missing-sender test).
8. **[12-04]** Relax tests depending on exact nginx/certbot versions and LE issuer CNs. Clarify rollback wording. Extend drift-guard to assert `.env` path in doc matches systemd `EnvironmentFile=` (belt-and-braces).
9. **[12-02 gemini]** Add `git status` idempotency check after first golden regeneration.
10. **[12-04 gemini]** Explicitly recommend `certbot --nginx --staging` in SETUP-HTTPS.md troubleshooting if operator needs >5 retries in 168h window.

**Reject (intentionally not applied):**
- Codex HIGH claim of `.env` path drift — false positive; paths already match.

### Consensus Risk: LOW-MEDIUM

Both reviewers approve execution after the MEDIUM fixes. The LOWs are quality-of-life improvements; nothing blocks execute-phase. Plan 02 is ready as-is per codex. Plans 01/03/04 need wording/assertion tightening before execute to avoid downstream confusion.
