---
phase: 16
reviewers: [gemini, codex]
reviewed_at: 2026-04-26T10:16:06Z
plans_reviewed: [16-01-PLAN.md, 16-02-PLAN.md, 16-03-PLAN.md, 16-04-PLAN.md, 16-05-PLAN.md]
runtime_self: claude (skipped per workflow self-detection)
---

# Cross-AI Plan Review — Phase 16: Hardening + UAT Completion

Two external AI reviewers (Gemini CLI, Codex CLI) independently reviewed the 5-plan phase package against PROJECT.md, ROADMAP.md, REQUIREMENTS.md, CONTEXT.md (D-01..D-17), RESEARCH.md, and all PLAN.md files. Claude was skipped (runtime self-detection in claude-desktop).

---

## Gemini Review

### Summary
The plans for Phase 16 are exceptionally well-crafted, demonstrating a deep understanding of the project's architecture and testing patterns. The F1 integration test (16-02) is a highlight, providing high-fidelity coverage of the entire execution chain while adhering strictly to mocking boundaries. The deployment strategy (16-01) leverages the established `deploy.sh` and focuses on the substantial 60-commit gap. The UAT and state-tracking plans (16-03, 16-04, 16-05) provide a clear audit trail for closing v1.0 tech debt.

### Strengths
- **F1 Test Fidelity:** Seeding state with `sample_state_with_change.json` and using 400-bar fetch fixtures ensures instrument logic, sizing, trade closing, and drift detection are all exercised in a single pass.
- **Meta-Test Logic:** Including `test_f1_catches_planted_regression` is excellent engineering — it proves F1 is sensitive to logic changes in the core engine, preventing "green-only" complacency.
- **Boundary Discipline:** Mocking `data_fetcher.yf.Ticker` (the network boundary) is superior to mocking `fetch_ohlcv` (the logic boundary), allowing internal retry and formatting logic to run live.
- **Detailed Operator Guidance:** 16-05 gives specific, actionable instructions for the operator (viewport sizes, header injection methods).
- **STATE.md Structural Integrity:** Migration of deferred items maintains a clear history of what was deferred at v1.0 and how it was resolved in v1.1.

### Concerns
- **[LOW] Wave Topology Inefficiency:** `16-05` is assigned to Wave 3, but it only depends on `16-01` and `16-03` (both Wave 1). Could be Wave 2 to allow operator UAT in parallel with `STATE.md` cleanup (16-04).
- **[LOW] Placeholder Substitution Risk:** The `___FM_DELIM___` substitution in `16-03` relies on agent precision. Standard pattern but a minor failure point.
- **[MEDIUM] Deploy Pre-flight:** Plan checks for clean working tree on Mac but doesn't verify the droplet's current commit before pulling. If the droplet has local uncommitted changes (unlikely but possible via manual state edits), `git pull --ff-only` inside `deploy.sh` will fail.
- **[LOW] RESEND_API_KEY Leakage:** F1 sets `RESEND_API_KEY='test_key_f1'`. While `_post_to_resend` is stubbed, ensuring the env var doesn't persist beyond the test process is important (pytest's `monkeypatch` handles correctly).

### Suggestions
1. Move `16-05` to Wave 2.
2. In 16-01 Task 2 `how-to-verify`, suggest the operator run `git status` on the droplet before `bash deploy.sh`.
3. Add a one-line manual rollback note: `git checkout HEAD@{1} && bash deploy.sh` for smoke-test failure.
4. F1: add `assert len(state['trade_log']) > 0` to confirm FLAT signals actually triggered trade closures in the sizing engine.

### Risk Assessment: LOW
**Logic Verification of F1 Meta-test:**
The choice of `return_value=999` for `get_signal` is inspired. Since `999` is not a valid label, the `notifier` will fail to find it in its label mapping, causing the assertion `assert 'FLAT' in email_html` to fail even if the rest of the chain runs. This confirms the test's sensitivity to the signal-to-email pipeline.

*Reviewer: Gemini CLI · Date: 2026-04-26*

---

## Codex Review

### Summary
The phase is well-scoped and the plans are unusually concrete, but there are two structural weaknesses: the F1 test plan in `16-02-PLAN.md` does not yet prove the full chain strongly enough to satisfy CHORE-01 SC-1, and the docs/state sequencing in `16-04-PLAN.md` marks items as "Completed" before operator verification exists. Deploy/UAT planning is mostly sound, but it needs one more pre-flight gate and an explicit rollback path.

### Strengths
- `16-02-PLAN.md` correctly avoids mocking internal composition and keeps mocks at the I/O edges.
- The `_setup_f1()` scaffold is good test hygiene: `tmp_path`, `monkeypatch.chdir(tmp_path)`, env setup, and `_push_state_to_git` neutralization are all the right isolation moves.
- Reusing existing project patterns from `tests/test_main.py`, `tests/test_data_fetcher.py`, `tests/test_notifier.py` reduces novelty risk.
- `16-01-PLAN.md` has clear operator checkpoints and concrete droplet acceptance checks (`deploy.sh`, `systemctl`, `curl`, `git log`).
- `16-03-PLAN.md` is explicit about D-09/D-10 and avoids mutating archived Phase 6 artifacts.
- D-17 is pragmatic. Allowing `PARTIAL` for UAT-16-C is operationally realistic.

### Concerns
- **HIGH** — `16-02-PLAN.md` does not actually assert the dashboard part of the chain. SC-1 says `dashboard.render_dashboard` must be exercised, but the scaffold only asserts on `last_email.html` and `_post_to_resend` subject capture. If `run_daily_check()` stopped rendering `dashboard.html` and still sent email, this test could stay green. Add an assertion on the generated dashboard artifact or content path.

- **HIGH** — The planted-regression meta-test is too weak and may pass without proving anything. In `test_f1_catches_planted_regression`, the core check is effectively "`FLAT` disappears." That is brittle. `FLAT` may still appear elsewhere in the HTML, or the system may coerce `999` in a way that still leaves the email containing one of the expected strings. This does not reliably prove that F1 red-lights on a cross-module break.

- **HIGH** — `16-04-PLAN.md` writes a `## Completed Items` section before the items are completed. The rows are inserted with `Verified = pending` and `Date = —`. That is semantically contradictory and weakens audit clarity in `STATE.md`. It also conflicts with SC-4 wording, which reads like the migration should happen after operator confirmation.

- **MEDIUM** — Deploy plan lacks a rollback path. `16-01-PLAN.md` pushes 60 commits directly to `origin/main` and updates the droplet, but does not say what to do if `deploy.sh` succeeds partially or the app is unhealthy after restart. At minimum, record the previous droplet SHA and a revert procedure.

- **MEDIUM** — Deploy pre-flight is incomplete. `git status --porcelain` is good, but before `git push origin main` there should be `git fetch origin` and a divergence check such as `git rev-list --left-right --count origin/main...HEAD`. Otherwise a stale local `origin/main` ref can make the "60 commits ahead" check misleading.

- **MEDIUM** — `16-02-PLAN.md` says the mock boundary is `data_fetcher.yf.Ticker`, while the roadmap text says "mocked at the `requests.get` boundary only." The research explains why `yf.Ticker` is the practical boundary in this codebase, but the plan should explicitly call out that this is the implementation-level equivalent. Right now it reads like a spec drift.

- **MEDIUM** — The F1 scaffold does not explicitly verify state persistence behavior. CHORE-01 mentions `state_manager.save_state`; the plan relies on live execution but never asserts that `state.json` changed as expected, or that the W3 "two mutate_state calls" invariant still holds within this test.

- **LOW** — `16-05-PLAN.md` is labeled Wave 3 but only depends on `16-01` and `16-03`. Plan-graph inconsistency. Should be Wave 2 minimum unless there is an intentional human scheduling reason.

- **LOW** — The `___FM_DELIM___` substitution scheme in `16-03-PLAN.md` is workable but fragile. If the executor misses one token, the generated file becomes malformed. Acceptance criteria should explicitly validate the frontmatter delimiter count, not just absence of the placeholder token.

### Suggestions
- Factor the happy-path assertions into a helper like `_assert_f1_outputs(...)`. Then the meta-test calls that helper under `pytest.raises(AssertionError)` while `patch.object(signal_engine, 'get_signal', return_value=999)` is active. That proves the same invariants fail, not some weaker proxy.
- Add dashboard assertions to F1: check `dashboard.html` exists and contains one or two stable markers tied to Phase 15 output.
- Add a state assertion to F1: after `main.main(['--force-email'])`, reload `state.json` and assert at least one expected state transition (positions updated, warnings persisted, or account/equity moved).
- Tighten the planted regression: patch `signal_engine.get_signal` to return a valid-but-wrong signal for one or both instruments and assert the exact expected subject/body no longer matches.
- In `16-01-PLAN.md`, add: `git fetch origin` before ahead/behind checks; local regression gate (`pytest tests/test_integration_f1.py -x -q` + relevant Phase 15 tests) before push; rollback note (capture pre-deploy SHA on droplet, document redeploy of that SHA).
- In `16-04-PLAN.md`: move the migration to after `16-05`, OR rename the section to `## Phase 16 Closure Tracking` until verification flips rows to complete.
- In `16-03-PLAN.md`: add one validation for exact frontmatter delimiter count.

### Risk Assessment: MEDIUM
The implementation risk is moderate, not because the scope is unclear, but because two of the plans currently overstate what they prove. The biggest risk is false confidence: F1 could go green without verifying dashboard/state behavior, and the planted-regression meta-test could pass without genuinely demonstrating cross-module break detection. The deploy path is practical, but direct-push of 60 commits without a formal rollback step keeps operational risk above low. The UAT partial-close rule is sound.

*Reviewer: Codex CLI · Date: 2026-04-26*

---

## Consensus Summary

Two reviewers, divergent overall risk: Gemini = LOW, Codex = MEDIUM. The divergence is driven entirely by Codex flagging 3 HIGH-severity issues that Gemini didn't surface — but Codex's points are concrete and actionable, so they should drive the replan.

### Agreed Strengths (raised by both)

- F1's mock boundaries (`data_fetcher.yf.Ticker` + `notifier._post_to_resend`) are correctly placed at I/O edges; internal composition runs live.
- Reusing existing project patterns (`test_main.py::TestDriftWarningLifecycle`, `test_data_fetcher.py`, `test_notifier.py` autouse fixtures) reduces novelty risk.
- 16-01 deploy plan has clear operator checkpoints and concrete acceptance commands.
- 16-03 separates the new `16-HUMAN-UAT.md` from the archived `06-HUMAN-UAT.md` — keeps the v1.0 archive immutable per D-09.
- D-17 partial-close pragmatism for UAT-16-C is operationally realistic.
- Meta-test pattern (`patch.object` on module attribute, not bound import) survives main.py's `import signal_engine` style.

### Agreed Concerns (raised by both — highest priority)

1. **Wave topology inefficiency on 16-05** *(both LOW):* assigned Wave 3 but deps are Wave 1 only. Could be Wave 2 to let UAT start in parallel with STATE.md cleanup. Minor — adds operational delay, no risk.
2. **`___FM_DELIM___` substitution fragility in 16-03** *(both LOW):* works but a missed token leaves the file malformed. AC should validate frontmatter delimiter count, not just absence of placeholder.

### Codex-Only HIGH Concerns (worth investigating — Gemini did not surface)

3. **F1 doesn't assert the dashboard chain** *(HIGH):* scaffold only asserts on `last_email.html` + `_post_to_resend` subject capture. If `dashboard.render_dashboard` were skipped entirely, F1 could stay green. CHORE-01 SC-1 says `dashboard.render_dashboard` MUST be exercised.
4. **Planted-regression meta-test is too weak** *(HIGH):* checks "FLAT disappears" — but FLAT may appear elsewhere in HTML, and `999` may get coerced. Doesn't reliably prove cross-module break detection.
5. **16-04 writes `## Completed Items` BEFORE verification exists** *(HIGH):* rows insert with `Verified=pending` and `Date=—` — semantically contradictory. SC-4 wording implies migration happens AFTER operator confirmation.

### Codex-Only MEDIUM Concerns

6. **No rollback path in 16-01** *(MED):* 60 commits going direct-push with no captured pre-deploy SHA + revert procedure.
7. **Deploy pre-flight missing `git fetch origin`** *(MED):* without it, "60 commits ahead" check is misleading if local origin/main ref is stale.
8. **F1 mock boundary spec-drift** *(MED):* ROADMAP says "mocked at requests.get boundary only", plan uses `data_fetcher.yf.Ticker`. RESEARCH justified the equivalence but the plan should call this out explicitly.
9. **F1 doesn't assert state persistence** *(MED):* never reloads `state.json` after the chain run to verify positions/warnings/equity transitioned. W3 invariant not asserted in F1 specifically.

### Gemini-Only Concerns

10. **Droplet pre-flight: `git status` before pull** *(MED):* if droplet has manual edits, `git pull --ff-only` fails. (Aligns with Codex MEDIUM #7 — both reviewers want stronger pre-flight.)
11. **`RESEND_API_KEY` env var leakage** *(LOW):* `monkeypatch.setenv` handles this correctly, but worth noting.
12. **F1 should assert `len(trade_log) > 0`** to confirm FLAT signals triggered closures in the sizing engine.

### Divergent Views

- **Overall risk:** Gemini LOW (proven patterns + deterministic fixtures + signal-only constraint = low blast radius). Codex MEDIUM (false-confidence risk on F1 + meta-test + 16-04 sequencing).
- **Meta-test sensitivity:** Gemini calls `return_value=999` "inspired"; Codex calls it "indirect" and prefers a valid-but-wrong signal value with exact body assertions.
- **16-04 sequencing:** Gemini accepts the forward-prepared structure; Codex calls it semantically contradictory and wants migration AFTER 16-05 OR a rename.

### Recommended Action

Run `/gsd-plan-phase 16 --reviews` to feed this REVIEWS.md back into the planner. The replan should address, in priority order:

1. **(HIGH) F1 dashboard assertion** — add `assert (tmp_path / 'dashboard.html').exists()` + at least one Phase 15 markup substring check (e.g., `'class="calc-row"'`, `'━━━ Drift detected ━━━'` in `notifier/golden_with_change.html` parity, or `'sentinel-banner'`). Also add `assert len(state['trade_log']) > 0` per Gemini suggestion #4.
2. **(HIGH) Tighten meta-test** — factor F1 happy-path into `_assert_f1_outputs(...)` helper. Meta-test calls it under `pytest.raises(AssertionError)` with `patch.object(signal_engine, 'get_signal', side_effect=lambda df: -1 if state_key=='SPI200' else 1)` (valid-but-inverted signals). Asserts the EXACT same invariants fail.
3. **(HIGH) 16-04 sequencing** — pick one of two paths:
   - **Path A (preferred):** Move the migration after 16-05, conditioned on UAT verification. 16-04 becomes Wave 4. STATE.md is only edited once operator marks scenarios verified.
   - **Path B:** Rename the section to `## Phase 16 Closure Tracking` (forward-prepared, status pending). After 16-05 fills in dates, an addendum task in 16-05 renames it to `## Completed Items`.
4. **(MEDIUM) Add rollback path to 16-01** — Task 2 captures `PRE_DEPLOY_SHA=$(git rev-parse HEAD)` BEFORE `bash deploy.sh`. Document in `<how-to-verify>`: if smoke-check fails, run `git checkout $PRE_DEPLOY_SHA && bash deploy.sh` to redeploy the prior known-good SHA.
5. **(MEDIUM) Add `git fetch origin` to deploy pre-flight** — before the ahead/behind check. Codex #7 + Gemini #10 align here.
6. **(MEDIUM) F1 state-persistence assertion** — after `main.main(['--force-email'])`, reload `state.json` and assert at least one transition (e.g., positions updated, warnings list non-empty per fixture seed, account changed). Also include W3 invariant assertion (`mutate_state` called exactly twice).
7. **(MEDIUM) F1 mock-boundary documentation** — 16-02 plan adds an explicit note: "Mocking at `data_fetcher.yf.Ticker` is the implementation-level equivalent of ROADMAP SC-1's `requests.get` boundary; both are above `data_fetcher.fetch_ohlcv` per RESEARCH OQ-X". Resolves the spec-drift narrative.
8. **(MEDIUM) Droplet pre-flight `git status`** — 16-01 Task 2 adds `[Operator] Run git status on the droplet first; resolve any local edits before bash deploy.sh.`
9. **(LOW) 16-05 wave assignment** — move from Wave 3 to Wave 2. Or document the conservative wave-3 choice in the plan with explicit rationale (current plan does, but reviewers still flagged it).
10. **(LOW) Tighten 16-03 frontmatter delimiter validation** — AC adds `awk '/^---$/{c++} END{exit c==2?0:1}' 16-HUMAN-UAT.md` to verify exactly 2 `---` delimiters at the file boundaries.
