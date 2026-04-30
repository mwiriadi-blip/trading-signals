# Trading Signals — Project Learnings

**Auto-loaded into every Claude Code session via the global SessionStart hook.** Treat as active instructions for working in this codebase, not reference material.

This file holds patterns that only make sense inside the trading-signals product / Python signal-only stack / hex-lite architecture / FastAPI + HTMX web layer / DigitalOcean systemd deployment. Cross-project patterns (Python idioms, GSD workflow gotchas, SDK bugs) live in `~/.claude/LEARNINGS.md`.

## Update protocol

After fixing any bug or shipping any non-trivial decision in this project, append a new entry below. Required fields:

```markdown
### {short title — imperative verb + object}

**Symptom:** {what failed / what was confusing / what the user observed}
**Root cause:** {actual underlying reason}
**Fix:** {what was changed — file + approach, not the diff}
**Prevention:** {grep / test / lint that catches it next time — make it runnable}
**Date:** {YYYY-MM-DD}
```

Keep tight. ~15 lines max per entry; split if larger.

---

## Entries

<!-- Newest at the top. -->

### CONTEXT.md spec-line claims must be RESEARCH-verified before locked into plans

**Symptom:** Phase 16.1 CONTEXT.md D-04 §Specific Ideas line 193 stated "Sec-Fetch-Mode added in Safari 14.1+ (Apr 2021)". RESEARCH pass cross-checked against MDN browser-compat-data and Apple Safari release notes — actual support is **Safari iOS 16.4+ (Mar 2023)**. If the planner had trusted CONTEXT verbatim, the `_is_browser_navigation` middleware helper would have been written without an `Accept: text/html` substring fallback, breaking the iPhone UAT path on any operator iOS version below 16.4.
**Root cause:** discuss-phase outputs feel like authoritative locks (D-XX numbered, committed, "ready for planning"), but specific-ideas line items inside `<specifics>` are often Claude's recollection from training data rather than verified facts. They are decisions about *implementation intent*, not browser-compat ground truth.
**Fix:** Phase 16.1 plans now implement BOTH detection paths (Sec-Fetch primary + Accept: text/html fallback) so execution works regardless of iOS version. The RESEARCH §"Risks & Open Questions for Planner" section was tagged `(RESOLVED 2026-04-27)` with disposition per question, including the iOS-version surface.
**Prevention:** When the researcher reads CONTEXT.md, treat any claim about external API/browser/library version support as a research target, not a locked decision. Cross-reference against the actual vendor docs before the planner sees it. For this project specifically: any Sec-Fetch / iOS Safari / Resend API / yfinance API claim in a CONTEXT.md `<specifics>` block must have a matching RESEARCH.md citation with URL.
**Date:** 2026-04-27

### Align identifier names across discuss-phase D-decisions for grep-discoverability

**Symptom:** Phase 16.1 CONTEXT.md D-10 specified `salt='web-auth-cookie'` for itsdangerous; D-12 specified the cookie name as `tsi_session`. Two related identifiers, two different roots — `grep -rn 'web-auth\|tsi_session'` would have to know to search for both. RESEARCH §"Risks & Open Questions" #5 caught the mismatch and recommended aligning the salt to `tsi-session-cookie` so a single grep finds both occurrences.
**Root cause:** discuss-phase locks names independently per D-decision. There's no automatic cross-D consistency check — the researcher (or a later auditor) has to spot the mismatch.
**Fix:** Plan 16.1-02 Task 1 + Task 2 use `salt='tsi-session-cookie'` (RESEARCH recommendation supersedes CONTEXT D-10 verbatim). Documented in RESEARCH §RESOLVED tag.
**Prevention:** Before /gsd-plan-phase, do a quick grep audit of CONTEXT.md for related identifiers. Pattern: any pair of D-decisions that name a `(thing, thing's signing/scoping label)` should share a root noun. For this project: cookie name + cookie salt; env-var name + env-var-validation-error message; route path + route-test class name; log-prefix + log-pattern grep — all should be greppable as a unit.
**Date:** 2026-04-27

### Phase 16.1 ships 2 plans SEQUENTIALLY despite disjoint files — middleware function body is shared state

**Symptom:** Phase 16.1's two plans (16.1-01 Basic Auth + 16.1-02 cookie session) modify mostly disjoint files (16.1-01 = middleware extension + WEB_AUTH_USERNAME env var + setup-docs; 16.1-02 = login routes + cookie validator + dashboard signout button + UAT). Tempting to parallelize per the v1.0 wave-structure precedent (Phase 10 Wave 1 = [10-01, 10-02] parallel because they touched disjoint files). But CONTEXT.md D-01 explicitly locks sequential — Plan 02 layers `_try_cookie` between `_try_basic` and `_try_header` in `AuthMiddleware.dispatch`, so Plan 02 needs the Plan 01 middleware diff in place before it can extend.
**Root cause:** "Disjoint files" is a necessary but NOT sufficient condition for parallelization. If two plans modify the same FUNCTION (even if in disjoint files structurally), they're sequential. `AuthMiddleware.dispatch` is a single chokepoint per Phase 13 D-01 — both plans extend it, so they share the function body as state.
**Fix:** ROADMAP.md §Phase 16.1 declares wave structure: Wave 1 = [16.1-01]; Wave 2 = [16.1-02]. Plan 02 frontmatter has `depends_on: ["16.1-01"]`. Sequential execution enforced by /gsd-execute-phase wave dispatch.
**Prevention:** Before declaring two plans parallel, grep for shared function/class targets across the plans' `files_modified`. If both plans modify `web/middleware/auth.py::AuthMiddleware.dispatch` (or any shared chokepoint function/class), serialize. The check: `for plan in *-PLAN.md; do grep -A1 "files_modified" $plan; done` — any file appearing twice + any single-purpose adapter (like AuthMiddleware) signals "sequential, not parallel".
**Date:** 2026-04-27

### Phase 16.1 reconciles Phase 13 D-04 — never send WWW-Authenticate even with Basic Auth

**Symptom:** Phase 13 D-04 explicitly forbade `WWW-Authenticate` on 401 responses. Phase 16.1 adds Basic Auth, which normally requires `WWW-Authenticate: Basic realm="..."` to trigger the iOS browser dialog. Discuss-phase locked browser-conditional behavior (Area B) but Area D's UX intersection follow-up superseded it: browsers get **302 → /login** (form), curl/scripts get **401 plain-text** (D-04 verbatim), Basic Auth is accepted only when explicitly sent (URL-bar `https://user:secret@…` style). `WWW-Authenticate` is NEVER sent.
**Root cause:** Two adjacent gray areas in discuss-phase can pick options that contradict each other. Without explicit reconciliation, the planner doesn't know which decision wins.
**Fix:** CONTEXT.md D-04..D-07 explicitly reconciles: Area B's "browser-conditional WWW-Authenticate" decision is SUPERSEDED by Area D's "redirect browsers to /login". Final state captured in DISCUSSION-LOG §B with note "SUPERSEDED by Area D follow-up". Plan 16.1-01 includes a verify command: `grep -ic 'WWW-Authenticate' web/middleware/auth.py` MUST return 0.
**Prevention:** When discuss-phase has multiple gray areas that touch the same surface (here: 401 response shape), end the discussion with an explicit reconciliation question or paragraph. CONTEXT.md should mark the SUPERSEDED decision so planners and reviewers can see the lineage. The grep verifier in PLAN.md is the runtime safety net.
**Date:** 2026-04-27

### Hex-boundary check: passing session-aware bool to dashboard.py is OK; cookie-decoding inside dashboard.py is NOT

**Symptom:** Phase 16.1 D-13 needs `dashboard.py::render_dashboard` to render either a "Sign out" button (cookie session) or a "Signed in via Basic Auth" note (header/Basic Auth). Question: how does dashboard.py know which path the operator authed via?
**Root cause:** Naive options are: (a) caller passes a boolean, (b) dashboard.py imports cookie-validation logic from web/middleware/auth.py. Option (b) violates the hex-lite boundary — `dashboard.py` is a top-level adapter, not in `web/`, and importing web/middleware/* from dashboard.py would inject web-layer concerns into the rendering layer.
**Fix:** Plan 16.1-02 Task 4 implements Option (a): `render_dashboard(state, is_cookie_session: bool = False)`. `web/routes/dashboard.py::get_dashboard` calls the same `_validate_cookie` helper from `web/middleware/auth.py` to compute the bool, then passes it to render_dashboard. `dashboard.py` only renders one of two static helpers — no cookie-decoding logic outside `web/`.
**Prevention:** When extending `dashboard.py` with auth-aware rendering, the auth signal MUST arrive as a primitive (bool, str, int) computed by the caller. Forbidden imports for `dashboard.py`: anything from `web/middleware/`, `itsdangerous`, `hmac`, `hashlib`, `os.environ` for auth secrets. Test: `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` AST-walks dashboard.py's imports — extend the forbidden list to include the new auth dependencies.
**Date:** 2026-04-27

### state_manager.mutate_state is non-reentrant — orchestrator helpers must run outside the closure

**Symptom:** Phase 20 RESEARCH discovered that calling `_evaluate_paper_trade_alerts` from inside the `mutate_state(_apply_daily_run)` closure would deadlock. The flock-based lock kernel at `state_manager.py:332-340` cannot be re-acquired while the same process already holds it. Any function spawned from inside a `mutate_state` closure that downstream calls `mutate_state` again would block forever (or fail outright depending on the OS flock semantics on non-reentrant locks).
**Root cause:** Phase 14 D-14 introduced `mutate_state` as a `flock(LOCK_EX)` cross-process safe-write kernel. The implementation is intentionally non-reentrant — it owns the file lock for the duration of the closure, releases on return. Reentry from within the same call stack is undefined behavior; the documented expectation at `state_manager.py:332-340` is "callers MUST NOT re-acquire". This is a project-specific contract — the `state.json` lock is the single serialisation point for all writes, and reentry would either deadlock or silently allow a partial write.
**Fix:** Daily-run orchestrator extensions that need to (a) read state, (b) take an external action (email, HTTP), (c) write conditional updates must run AFTER the main `mutate_state(_apply_daily_run)` returns. The insertion point for Phase 20+ is between `mutate_state` return at `main.py:1404` and `_render_dashboard_never_crash` at `main.py:1421`. The function uses a SECOND `mutate_state` call (separate lock acquisition) to commit any state changes after the external action completes. See global LEARNINGS G-45 for the universal two-phase commit pattern.
**Prevention:** (1) Any new orchestrator helper added to `main.py::_apply_daily_run` lifecycle that touches `state.json` must be at the top level of the daily-run sequence — NOT nested inside an existing `mutate_state` closure. (2) When in doubt, search the call graph: `grep -nE "mutate_state\(" your_helper.py` should be zero from inside another `mutate_state` closure. (3) Document the non-reentrancy contract at every `mutate_state` definition and key call site — it's surprising default behavior and easy to violate accidentally. (4) Two-phase commit implementations: separate the eval-read phase from the conditional-write phase with the external action in between. Each phase is its own `mutate_state` call.
**Date:** 2026-04-30
