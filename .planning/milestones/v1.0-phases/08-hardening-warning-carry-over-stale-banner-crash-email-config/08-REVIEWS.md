---
phase: 8
reviewers: [gemini, codex]
reviewed_at: 2026-04-23
plans_reviewed: [08-01-PLAN.md, 08-02-PLAN.md, 08-03-PLAN.md]
skipped: [claude]
skip_reason: "Running inside Claude Code CLI — skipped for reviewer independence"
---

# Cross-AI Plan Review — Phase 8

## Gemini Review

# Plan Review: Phase 8 — Hardening

The implementation plans for Phase 8 are **exceptionally well-structured, comprehensive, and technically grounded**. They successfully address the "looks done but isn't" production gaps by hardening the error boundaries, improving operator visibility through sophisticated warning banners, and introducing runtime-configurable scaling. The use of a transient state convention (`_underscore` keys) and a layered error-catching model (Layer A/B) shows a high level of architectural maturity.

### Strengths

- **Layered Resilience (D-05):** The separation of per-job error handling (Layer A) and catastrophic loop-driver failure handling (Layer B) ensures the system remains alive during routine data/network blips while providing a "last-ditch" crash notification for fatal process issues.
- **Decoupled Scaling (D-14, D-17):** Materializing `_resolved_contracts` at load-time allows the CLI and `system_params` to use human-readable labels while keeping the `sizing_engine` pure-math and decoupled from the label vocabulary.
- **Warning Pipeline Hygiene (B1, B3):** The revised ordering in `_dispatch_email_and_maintain_warnings` (dispatch → clear → maybe-append → save) is a critical fix that prevents the system from accidentally wiping its own "email failed" warnings.
- **Interactive Reset UX (D-09, D-12):** Providing an interactive Q&A for `--reset` with a values-preview block makes the first-time setup much safer and more user-friendly for a single-operator tool.
- **Security & Stability (T-08-12):** The addition of `math.isfinite` guards on numeric CLI inputs and `html.escape` on all rendered warning messages effectively mitigates common injection and data-corruption threats.

### Concerns

- **Staleness Threshold vs. Edge Cases (LOW):** On a Tuesday morning run after a Monday public holiday, the last run (Friday) will be 4 days old, triggering the red "Stale state" banner. While technically true, if this happens frequently due to market holidays, the operator might become desensitized to the red banner.
- **Forward-Reference Type Hinting in `main.py` (LOW):** `_send_email_never_crash` uses a string forward-ref `'SendStatus | None'`. Since `notifier` is imported locally inside the function to preserve the hex-boundary, the type checker may struggle without a proper `if TYPE_CHECKING` block. Common pattern in this project's hex-lite architecture — unlikely to cause runtime issues.
- **Save-State Frequency (LOW):** The system now performs two saves per run (Step 5 and Step 8/post-dispatch). While atomicity is guaranteed via tempfiles, the second save carries a very small risk of a race if the process is killed between the dispatch and the clear-warnings save. Single-operator daily-cadence tool — risk is negligible.

### Suggestions

- **Diagnostic Detail in Crash Email:** In `send_crash_email`, consider including the `python --version` and the `pytz` timezone name in the header to assist with remote debugging if the operator migrates between Replit and GHA.
- **Dashboard Baseline Note:** In the dashboard total-return block, consider adding a small "($100k baseline)" or "($50k baseline)" text next to the percentage so the operator knows which `initial_account` value is currently being used for calculations.
- **`clear_warnings` Docstring Update:** The docstring for `clear_warnings` in Plan 01 is excellent; ensure it's kept as-is during implementation as it serves as vital "ordering documentation" for future maintainers.

### Risk Assessment: LOW

The overall risk for Phase 8 is **LOW**. The plans are highly defensive, include exhaustive test coverage (80+ new test cases), and utilize established architectural patterns (hex-lite, atomic writes, local imports). The "backward-compat" migration path ensures existing `state.json` files are not broken by the schema upgrade.

**Success Probability:** **High.** The transition from v1 to v2 schema is handled surgically, and the error-boundary wiring completes the production-readiness of the application.

---

## Codex Review

### 08-01-PLAN.md

**Summary:** Strong foundation plan. Cleanly establishes the Phase 8 state/config contract before notifier and orchestrator work depend on it, and preserves the key architectural boundary by keeping contract-tier resolution in `state_manager`/`main` rather than leaking label logic into `sizing_engine`. The migration, runtime-only `_resolved_contracts`, underscore-save filter, and `clear_warnings` helper all align with the phase goals. Main risk is that it hard-locks label vocabulary and schema behavior early, so any mismatch with current code assumptions or broker naming will ripple into Plans 02 and 03.

**Strengths:**
- Clear sequencing: foundation first, downstream interfaces explicit.
- Good backward-compat story via `_migrate` and required-key expansion.
- Strong architectural discipline: preserves hex boundary and sole-writer rule for warnings.
- General `_`-prefix persistence rule is pragmatic and extensible.
- Tests cover migration, persistence filtering, tier resolution, and warning clearing directly.
- Explicitly preserves the existing corrupt-recovery warning prefix to avoid cross-plan drift.

**Concerns:**
- **MEDIUM:** `load_state` only materializes `_resolved_contracts` on the happy path, while the corrupt-recovery branch returns state without it. The plan says this is acceptable, but that assumption is fragile if any caller uses the returned state immediately in the same run.
- **MEDIUM:** Unknown contract labels raise `KeyError` directly. Acceptable technically, but operator UX may be rough unless Plan 03 clearly surfaces remediation.
- **LOW:** `_DEFAULT_SPI_LABEL` / `_DEFAULT_AUDUSD_LABEL` are underscored but imported cross-module; that naming convention may imply "private" more than intended.
- **LOW:** Using a blanket underscore filter in `save_state` is good, but it creates a silent convention. Future developers may accidentally rely on transient keys without realizing they will never persist.

**Suggestions:**
- Add one explicit test for the corrupt-recovery return path to confirm whether `_resolved_contracts` is absent by design and document expected caller behavior.
- Consider validating `contracts` structure during `_validate_loaded_state` or `load_state` so malformed-but-present shapes fail with a clearer message than raw `KeyError`.
- Consider non-underscored defaults like `DEFAULT_SPI_LABEL` if these are intended as public cross-module constants.
- Document the `_` runtime-only persistence rule in a central convention file, not only in plan summaries.

**Risk Assessment: LOW-MEDIUM.** Design is solid and appropriately scoped. Most risk is integration risk from assumptions about the corrupt-recovery path and label vocabulary, not from the plan structure itself.

---

### 08-02-PLAN.md

**Summary:** Ambitious but coherent. Addresses the notifier-side Phase 8 outcomes directly: warning carry-over display, stale/corrupt critical banners, subject escalation, durable `last_email.html`, and crash-email support. Biggest strength is the explicit separation between critical and routine warnings, including the age-filter bypass for critical conditions. Main downside is complexity: this is a large refactor of a sensitive module, with a temporary contract break (`send_daily_email` returning `SendStatus`) that intentionally leaves `main.py` red until Plan 03 lands.

**Strengths:**
- Good UX model: critical vs routine warnings are clearly separated.
- Correct handling of stale-state and corrupt-reset as critical conditions rather than routine warnings.
- `SendStatus` is a useful contract for orchestrator-level warning translation.
- Always-writing `last_email.html` is practical and matches operator recovery needs.
- Crash email using `text/plain` is the right choice.
- Preserves existing corrupt-warning prefix instead of changing shared semantics.
- Strong test coverage, including XSS escaping and retry behavior.

**Concerns:**
- **HIGH:** The plan knowingly introduces a temporary breaking change to `send_daily_email` consumers. Acceptable in a tightly controlled execution sequence, but increases implementation risk and intermediate instability.
- **MEDIUM:** `_render_header_email` becomes quite dense and mixes classification, filtering, and HTML rendering. Raises maintainability risk.
- **MEDIUM:** Rendering all corrupt warnings as critical banners could produce multiple stacked banners if more than one survives in state.
- **MEDIUM:** Treating missing `RESEND_API_KEY` as `ok=True, reason='no_api_key'` is pragmatic, but it semantically overloads `ok`; "dispatch skipped intentionally" is not exactly success.
- **LOW:** Hero-card extraction requirement is brittle because it depends on verbatim preservation and exact string placement.
- **LOW:** The routine warning list in email could grow noisy if prior-run warnings are numerous, even with the FIFO cap.

**Suggestions:**
- If possible, reduce transition risk by updating Plan 03 consumer code immediately after Plan 02 in the same execution window, with no gap for partial completion.
- Add an explicit cap or grouping rule for critical corrupt-reset banners so multiple old corruption warnings do not stack awkwardly.
- Consider factoring warning classification into a helper returning `critical` and `routine` lists; keep HTML rendering thinner.
- Consider a richer status model later (`sent`, `skipped`, `failed`) instead of boolean `ok`, even if `SendStatus` stays for this phase.
- Add one test confirming subject-prefix behavior when both stale and corrupt critical conditions exist together.

**Risk Assessment: MEDIUM.** Well thought through, but it is a large, behavior-heavy notifier refactor with temporary integration breakage and a lot of HTML logic. Achievable, but execution discipline matters.

---

### 08-03-PLAN.md

**Summary:** Closes the loop well. Wires the new notifier and state contracts into actual runtime behavior: staleness detection, post-dispatch warning maintenance, configurable reset flow, tier pass-through, and outer crash-email handling. Correctly avoids duplicating corrupt-recovery signaling. Biggest concern is scope density: this plan touches orchestration, CLI UX, crash boundaries, scheduler behavior, and dashboard calculations all at once. The pieces are individually reasonable, but together they make this the highest integration-risk plan of the set.

**Strengths:**
- Correctly fixes the warning lifecycle ordering with `dispatch → clear → maybe-append → save`.
- Uses transient `_stale_info` instead of abusing persisted warnings for staleness.
- Preserves typed-exception behavior while adding a true outer crash boundary.
- CLI reset flow is practical: explicit flags, interactive prompts, preview, non-TTY guard.
- Tier resolution is kept in orchestrator, preserving purity in `sizing_engine`.
- Dashboard change is small and directly tied to `initial_account`.
- Good explicit tests for save-count, stale cleanup, and crash-boundary behavior.

**Concerns:**
- **HIGH:** This plan is doing too many critical integrations in one wave: notifier consumer rewrite, warning lifecycle, staleness, contract-tier plumbing, CLI redesign, and crash-email boundary. High chance of incidental regressions.
- **MEDIUM:** `_send_email_never_crash` returning `None` on import/runtime failure means `_dispatch_email_and_maintain_warnings` may silently skip appending a notifier warning for some failure modes.
- **MEDIUM:** Outer crash handler passes `state=None`, so the crash email often won't include the "last-known state summary" required by the roadmap unless future caching is added. That weakens success criterion 3.
- **MEDIUM:** Interactive reset validation returns code `1` for some parse/validation problems that arguably should remain parser-style `2`; error-code semantics may become inconsistent.
- **MEDIUM:** `math.isfinite` validation is good, but explicit CLI path validates after parse, not in parser type; this may scatter validation behavior.
- **LOW:** The non-TTY guard requires all three config flags together. Safe, but not very flexible if only one value needs overriding and defaults are acceptable.
- **LOW:** Reusing `state_manager.load_state()` inside reset preview may trigger migration/corrupt-recovery behavior during a reset preview, which is operationally okay but slightly surprising.

**Suggestions:**
- Split execution discipline mentally even if not structurally: land Task 1 consumer wiring before Task 2 reset UX changes to reduce debugging surface.
- Strengthen crash-email compliance by caching the last loaded state in `main` and passing it into `_send_crash_email` instead of always `None`.
- Consider appending a notifier warning when `_send_email_never_crash` returns `None`, since that still represents a failed email attempt.
- Standardize exit-code semantics for reset validation vs parser errors and document them clearly.
- Add one test proving that a notifier import failure still results in an observable warning or logged failure path, not just silent degradation.
- Add one integration test around `_handle_reset` preview when `state.json` is corrupt or missing.

**Risk Assessment: MEDIUM-HIGH.** Probably achieves the phase goals, but concentrates most of the integration complexity in one place. The warning-order fix is correct, and the overall design is sound, but crash-email completeness and broad-scope regression risk are the main concerns.

---

### Overall Assessment

**Summary:** Taken together, the three plans are high quality, internally consistent, and much better than an ad hoc implementation sequence. The dependency ordering is mostly right: Plan 01 establishes contracts, Plan 02 reshapes notifier behavior, and Plan 03 integrates runtime usage. The main systemic risk is not missing functionality; it is execution complexity, especially across Plans 02 and 03 where contracts intentionally change midstream.

**Strengths:**
- Strong phase decomposition with clear inter-plan contracts.
- Good preservation of prior decisions and invariants.
- Clear handling of stale vs corrupt vs routine warning semantics.
- Backward compatibility is consistently considered.
- Test planning is thorough and specific.
- Security/XSS treatment is better than typical for a single-user internal tool.

**Concerns:**
- **HIGH:** Temporary red state between Plans 02 and 03 increases implementation fragility.
- **MEDIUM:** Some success criteria depend on nuanced runtime behavior that is only partially satisfied unless the crash path has access to actual loaded state.
- **MEDIUM:** The total test and acceptance surface is very large; that improves rigor but risks over-engineering and slower execution.
- **LOW:** Some plan text is overly prescriptive at the line/string level, which may make execution brittle without materially improving outcome quality.

**Suggestions:**
- Execute Plans 02 and 03 back-to-back with no pause.
- Add a small integration note or patch to preserve last-known state for crash emails.
- Reduce brittleness where exact string/line preservation is not truly necessary.
- Add one end-to-end Phase 8 scenario test covering: stale banner, warning carry-over, Resend failure append, and next-run surfacing.

**Overall Risk: MEDIUM.** The plans are complete and likely to achieve the phase goals. The main risk is integration churn, not conceptual gaps. If executed carefully and sequentially, they should work; if partially landed, they could leave the system in an unstable intermediate state.

---

## Consensus Summary

Two independent reviewers (Gemini, Codex) both rate the plans as execution-ready with the warning-pipeline fix validated as correct. Gemini calls overall risk **LOW**; Codex calls it **MEDIUM** — the gap is whether integration complexity across Plans 02+03 should count as elevated risk. Neither reviewer flagged a blocker; both listed actionable refinements.

### Agreed Strengths

- **Warning pipeline ordering is correct** — dispatch → clear → maybe-append → save validated by both reviewers (directly resolves the B1 blocker from plan-checker iteration 1).
- **Hex-lite architectural boundary preserved** — `_resolved_contracts` + underscore persistence filter keeps `sizing_engine` pure. Both reviewers call out D-14/D-17 as well-executed.
- **Stale-vs-corrupt-vs-routine warning classification** — two-tier banner model with age-filter bypass is cleanly separated.
- **Backward-compat via `_migrate`** — existing state.json files upgrade safely.
- **Test coverage is thorough** — XSS escape, retry behavior, save-count, stale cleanup, crash-boundary all have explicit tests.
- **Security treatment** — `math.isfinite` guards on numeric CLI inputs + `html.escape` on rendered warnings are both noted.

### Agreed Concerns

| # | Concern | Gemini | Codex | Action |
|---|---------|--------|-------|--------|
| 1 | **Crash email `state=None` weakens SC-3** — last-known state summary won't appear in most crash emails | — | MEDIUM | **Most actionable** — cache last-loaded state in `main` and pass into `_send_crash_email` |
| 2 | **Plan 03 scope density** — one wave doing orchestrator + CLI + crash boundary + dashboard | implicit | HIGH | Consider landing Task 1 (consumer wiring) before Task 2 (reset UX) in the same execution window |
| 3 | **Holiday staleness false-positives** — Tuesday-after-Monday-holiday will trigger red banner (4-day gap) | LOW | — | Document in deferred ideas; consider ≥ 3-day threshold or explicit "known gap: holidays" caveat |
| 4 | **Silent failure modes** — `_send_email_never_crash` returning `None` on import failure doesn't append notifier warning | — | MEDIUM | Append a generic notifier warning when return is `None` |
| 5 | **Temporary red state Plan 02 → Plan 03** — `send_daily_email` signature change leaves consumer red until Plan 03 lands | — | HIGH | Execute Plans 02 and 03 back-to-back with no pause |

### Divergent Views

- **Overall risk rating:** Gemini LOW, Codex MEDIUM. Divergence is about whether execution complexity should dominate over architectural soundness. Neither disagrees with the architecture; they weight implementation-time risk differently.
- **Hero card verbatim preservation (B4 fix):** Codex flags this as LOW brittleness ("depends on verbatim string placement"); Gemini doesn't mention it. Both reviewers saw the `grep "Trading Signals</h1>"` acceptance check as sufficient mitigation.

### Recommended Actions (if replanning via `--reviews`)

1. **Crash email state caching** — add last-state cache in main.py so `_send_crash_email` receives actual `state` instead of `None`. Addresses SC-3 completeness. High value, small change.
2. **Silent failure warning** — in `_dispatch_email_and_maintain_warnings`, treat `status is None` (return from `_send_email_never_crash` on import failure) as a failure and append a notifier warning. Addresses unique silent-skip path.
3. **Holiday staleness doc note** — add to 08-CONTEXT.md Deferred Ideas: "staleness may false-trigger on Monday public holidays — accepted for v1." Documentation only.
4. **Execution discipline note** — add to Plan 02 and Plan 03 headers: "Execute back-to-back; do not pause between waves 2 and 3. Intermediate state has broken `send_daily_email` contract."

Items 1, 2, 4 are concrete planner changes. Item 3 is documentation. All other reviewer suggestions (dashboard baseline text, `python --version` in crash header, `DEFAULT_*` naming, exit-code semantics) are polish that can be deferred.
