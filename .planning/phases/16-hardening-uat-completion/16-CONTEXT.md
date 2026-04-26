# Phase 16: Hardening + UAT Completion - Context

**Gathered:** 2026-04-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Close v1.0 tech-debt items deferred at milestone close (CHORE-01: F1 full-chain integration test) and complete the 3 Phase 6 HUMAN-UAT scenarios that became verifiable once the hosted dashboard shipped (CHORE-03). Final gate before v1.1 milestone archive.

**In scope:**
- F1 integration test exercising fetch → signals → sizing → state-write → dashboard-render → email-render with mocking only at the system boundaries (`requests.get` for yfinance, `_post_to_resend` for Resend)
- Permanent meta-test that proves F1 catches a deliberately-planted cross-module break
- 3 operator-verified UAT scenarios (mobile dashboard, mobile Gmail email, drift banner in real weekday email)
- STATE.md `§Deferred Items` cleanup (move 4 v1.0-deferred items to a Completed section with verification dates)
- Deploying the local-only Phase 13 + 14 + 15 stack to the droplet (without this, the 3 UAT scenarios cannot be exercised)

**Out of scope:**
- New features or capabilities (those belong in v1.2+)
- ruff F401 cleanup (CHORE-02 — mapped to Phase 10 per ROADMAP coverage map; not folded into 16)
- v1.1 milestone archival itself (separate session after Phase 16 verify-work passes)
- Cross-AI peer review of the deploy itself (operator-managed direct push/pull mechanism)

</domain>

<decisions>
## Implementation Decisions

### F1 integration test architecture (CHORE-01)

- **D-01:** F1 reuses an existing Phase 1 scenario fixture (`tests/fixtures/scenarios/*.json` + the canonical yfinance fixture pair `tests/fixtures/yfinance_canonical_*.json`) as the input seed. Pick a scenario that exercises both instruments with non-FLAT signals (e.g. SPI200 LONG + AUDUSD SHORT or similar) so a single F1 run covers both code paths.
- **D-02:** F1 mocks at the boundaries already specified in ROADMAP SC-1: `requests.get` for the yfinance fetch (so the existing canonical-fixture bytes flow through `data_fetcher.fetch_ohlcv`), and `_post_to_resend` for the Resend dispatch (so no real HTTPS call). NO mocking of internal composition (`signal_engine`, `sizing_engine`, `state_manager`, `dashboard`, `notifier` boundaries are all live).
- **D-03:** F1 asserts on rendered `last_email.html` at section + key-value granularity:
  - Subject line contains the expected emoji (📊 routine OR 🔴 signal-changed) and the run-date in `YYYY-MM-DD` shape
  - Body contains the signal-direction text for both instruments (`SPI200 ... LONG/SHORT/FLAT` + same for AUDUSD)
  - Body contains the position-direction text when the fixture seeds open positions
  - Body contains the equity figure formatted with thousands separator
  - When the fixture seeds drift warnings, body contains `Drift detected` and the subject carries the `[!]` critical prefix
  - **NOT** a byte-for-byte golden snapshot — too brittle, fights with the existing per-component snapshot tests in `test_dashboard.py` and `test_notifier.py`
- **D-04:** F1 covers both SPI200 and AUDUSD in a single test pass (one scenario fixture exercises both). No `@pytest.mark.parametrize` over instruments.
- **D-05:** Test path locked by ROADMAP: `tests/test_integration_f1.py::test_full_chain_fetch_to_email`. New file, not appended to an existing test module.

### Planted-regression meta-test (CHORE-01 SC-2)

- **D-06:** Permanent monkey-patch test lives alongside F1 in `tests/test_integration_f1.py`. Function name: `test_f1_catches_planted_regression`.
- **D-07:** Planted regression = `signal_engine.get_signal` rename. The meta-test uses `unittest.mock.patch.object(signal_engine, 'get_signal', ...)` to replace `get_signal` with a stub that returns a different signal value (or removes it entirely via `delattr` + `pytest.raises(AttributeError)` — pick whichever cleanly causes F1 to red-light). Asserts F1's value-level assertion fails (or the chain raises). Then asserts F1 passes WITHOUT the patch (sanity check that the test wasn't already broken).
- **D-08:** The planted regression in the meta-test is `get_signal` — matches ROADMAP SC-2's example. If a future refactor renames `get_signal` for real, this test still works because it monkey-patches by name; if `get_signal` is intentionally removed, this test gets updated to reference the new entry-point name in the same commit.

### Phase 6 HUMAN-UAT artifact (CHORE-03)

- **D-09:** Operator UAT notes for Phase 16 live in a new `16-HUMAN-UAT.md` inside the Phase 16 directory (NOT appended to the archived `milestones/v1.0-phases/06-.../06-HUMAN-UAT.md`). The new doc references the archived 06-HUMAN-UAT.md for original scenario context.
- **D-10:** `16-HUMAN-UAT.md` schema per scenario:
  - Scenario ID (UAT-16-A mobile dashboard / UAT-16-B mobile Gmail / UAT-16-C drift banner real weekday)
  - Original v1.0 scenario reference (`06-HUMAN-UAT.md §...`)
  - Verification status (`pending` / `verified` / `partial`)
  - Operator verification date (ISO `YYYY-MM-DD`)
  - Operator notes (free text — what was checked, screenshot path if captured, any issues observed)

### Deployment of Phases 13-15 to droplet

- **D-11:** Deploying the Phase 13 + 14 + 15 stack to the droplet IS a Phase 16 task (the very first one), not a prerequisite gate. Without it the 3 UAT scenarios cannot be exercised.
- **D-12:** Deploy mechanism = direct git push to `origin/main` from the Mac, then `git pull && systemctl restart trading-signals-web` on the droplet. The droplet's `deploy.sh` (per Phase 11 INFRA-04) handles `git pull && pip install -r requirements.txt && systemctl restart` idempotently — the deploy plan task uses that script. NO PR review layer.
- **D-13:** Deploy plan task acceptance criteria:
  - `git push origin main` from Mac succeeds (no force-push needed)
  - On the droplet: `cd ~/trading-signals && bash deploy.sh` exits 0
  - `systemctl is-active trading-signals-web` returns `active`
  - Smoke check: `curl -s -H "X-Trading-Signals-Auth: $WEB_AUTH_SECRET" http://127.0.0.1:8000/ | grep -c "calc-row"` returns ≥ 1 (proves Phase 15 markup is live)
  - `git log --oneline origin/main -5` on the droplet shows the latest Phase 15 commits

### STATE.md Deferred Items cleanup (CHORE-03 / SC-4)

- **D-14:** STATE.md gets a new `## Completed Items` section ABOVE the existing `## Deferred Items` section. The 3 v1.0-deferred items mapped to Phase 16 (`uat_gap` Phase 06 HUMAN-UAT, Phase 05 dashboard verification_gap, Phase 06 email verification_gap) move from Deferred to Completed once the operator marks them verified in `16-HUMAN-UAT.md`. The 4th item (`quick_task` 260421-723) stays in Deferred — it's not v1.1 scope.
- **D-15:** Each Completed entry records: the original deferred description, the operator verification date, and a path-link to the artifact that closed it (`16-HUMAN-UAT.md §UAT-16-A` etc.).

### Milestone close mechanics

- **D-16:** Phase 16 verify-work and v1.1 milestone archive run in SEPARATE sessions. After Phase 16 verify-work passes (or returns PARTIAL pending operator weekday verification), the orchestrator does NOT auto-advance to `/gsd-complete-milestone`. Operator runs `/gsd-complete-milestone v1.1` deliberately in a fresh session.
- **D-17:** If SC-3c (drift banner in real weekday Gmail) takes more than 1 weekday run to observe, Phase 16 stays open with `verify-work` returning `PARTIAL — awaiting weekday operator confirmation`. Operator updates `16-HUMAN-UAT.md §UAT-16-C` to `verified` once observed; `verify-work` re-runs and closes Phase 16. Other SCs (deploy, F1 test, mobile dashboard, mobile Gmail) close earlier and don't gate on the drift-banner real-day observation.

### Claude's Discretion

- F1 fixture selection (which exact scenario from the 9 Phase 1 fixtures) — pick one with both instruments active and non-trivial signals
- Test-runtime budget (target < 5s for F1) — no hard SLA
- Specific text-pattern strings the F1 assertions look for in `last_email.html` — pick stable, format-invariant patterns
- Whether the deploy task's smoke-check curl runs against `127.0.0.1` (on droplet) or `signals.<domain>` (over HTTPS) — let the planner decide based on whether nginx + Let's Encrypt is live (Phase 12 status)

### Folded Todos

[None — `gsd-sdk query todo.match-phase 16` returned no matches relevant to this scope.]

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### v1.0 Phase 1 fixtures (F1 input seed)
- `tests/fixtures/scenarios/scenarios.README.md` — explains the 9 deterministic scenarios + their golden CSVs
- `tests/fixtures/scenarios/*.json` — actual scenario JSON files (D-01)
- `tests/fixtures/yfinance_canonical_axjo.json` — canonical SPI200 yfinance bytes (D-01)
- `tests/fixtures/yfinance_canonical_audusd.json` — canonical AUDUSD yfinance bytes (D-01)

### v1.0 Phase 6 archived UAT
- `milestones/v1.0-phases/.../06-HUMAN-UAT.md` — the original 3 scenarios that became verifiable in v1.1; new `16-HUMAN-UAT.md` references this for context (D-09). Exact archive path may vary; planner should `find milestones/ -name "06-HUMAN-UAT.md"` to confirm.

### v1.1 dependencies that drive deploy task
- `deploy.sh` — droplet deploy script per Phase 11 INFRA-04 (D-12)
- `systemd/trading-signals-web.service` — service unit per Phase 11
- `web/app.py` — FastAPI entry point that the deploy must restart

### Phase 15 lockstep deps (drift banner UAT)
- `.planning/phases/15-live-calculator-sentinels/15-CONTEXT.md` — D-12 lockstep parity (dashboard ↔ email drift banner) is what UAT-16-C visually verifies
- `.planning/phases/15-live-calculator-sentinels/15-UI-SPEC.md` — drift banner email markup contract

### Project-wide
- `.planning/PROJECT.md` — milestone goals, "no live trading" hard constraint
- `.planning/REQUIREMENTS.md` — CHORE-01 + CHORE-03 acceptance text
- `.planning/STATE.md` — `§Deferred Items` table that gets restructured per D-14

### Cross-module test infrastructure
- `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` — hex-discipline AST guard that F1 must NOT break
- `tests/test_main.py::TestDriftWarningLifecycle::test_w3_invariant_preserved` — W3 invariant that F1 must respect (mutate_state called exactly twice per chain run)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Phase 1 scenario fixtures + golden CSVs** (`tests/fixtures/scenarios/*.json`) — F1 input seed (D-01)
- **`tests/regenerate_goldens.py`** — Phase 1 oracle pipeline; not directly reused but proves canonical-fixture-driven testing is the project pattern
- **`unittest.mock.patch.object`** — already used in `tests/test_main.py::TestDriftWarningLifecycle` for monkey-patching `mutate_state` count; same pattern reused in F1 meta-test (D-06)
- **`requests.get` mocking** — already exercised by `tests/test_data_fetcher.py` test patterns; F1 uses the same approach
- **`_post_to_resend` mocking** — already exercised by `tests/test_notifier.py` for the Resend HTTPS path; F1 reuses

### Established Patterns
- **2-space indent, single quotes, snake_case** — CLAUDE.md (carry-forward)
- **AST-enforced hex boundaries** — `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` blocks `os/datetime/requests` etc. from pure-math modules; F1 must not introduce such imports
- **Atomic state.json writes** — `state_manager.save_state` uses tempfile + fsync + os.replace; F1 must let this run live (no `mock.patch('os.replace')`)
- **W3 invariant** — `mutate_state` called exactly twice per `run_daily_check`; F1 must observe this (already proven by Phase 15 `test_w3_invariant_preserved`)

### Integration Points
- **`main.run_daily_check`** — the function F1 invokes once per chain run (no inner mocks)
- **`tests/test_integration_f1.py`** — new file, project-root tests/ directory
- **`16-HUMAN-UAT.md`** — new file in Phase 16 directory; not consumed by tests, only by operator + STATE.md cleanup
- **STATE.md `## Completed Items`** — new section above existing `## Deferred Items`

</code_context>

<specifics>
## Specific Ideas

- **F1 fixture should exercise the drift banner path** if possible — pick a scenario where positions disagree with signals so the chain hits `detect_drift` → `append_warning` → dashboard banner render → email banner render. This makes F1 a Phase 15 regression net AND a fetch→email regression net in one test.
- **Meta-test naming convention:** `test_f1_catches_planted_regression_<what>` — explicit so the next planted-regression test (if added later) reads as a series.
- **Deploy task `[Sched]`-style log:** the deploy plan should produce a `[Deploy]` log entry when the droplet pulls a new commit, mirroring CLAUDE.md's prefix convention (`[Signal]`, `[State]`, `[Email]`, `[Sched]`).

</specifics>

<deferred>
## Deferred Ideas

- **Phases 10 + 12 deployment status:** the droplet is on commit `b1f9b8f` per the Phase 15 UAT finding — that commit is "Phase 10 + 11 + 12: v1.0 cleanup, deploy key, FastAPI web skeleton, HTTPS + domain wiring" but the v1.1 ROADMAP lists Phases 10 and 12 as "Not started". This means either (a) Phase 10 + 12 work landed in the merged commit but were never formally GSD-tracked as plans, or (b) only Phase 11 + parts of 13 made it to the droplet. **Worth investigating before Phase 16 deploy** — the deploy plan in 16 should not assume Phase 10/12 work is fresh-on-droplet. If it turns out Phases 10/12 still have unshipped work (BUG-01 reset_state fix, INFRA-01 Resend domain, INFRA-02 deploy key, INFRA-03 GHA disable, WEB-03/04 HTTPS), that's a separate phase to insert before 16. Operator declined to fold this into Phase 16 scope; flagged here for visibility.
- **CHORE-02 ruff F401 cleanup** in notifier.py — currently mapped to Phase 10 per ROADMAP coverage map. If Phase 10 never executes formally, CHORE-02 stays open. Deferred decision: fold into Phase 16's polish step or leave for v1.2.
- **Tagged release strategy** — operator chose direct push for the deploy. If the v1.1 deploy goes well, consider adopting `v1.1-rc1` style tags for v1.2+ deploys (gives droplet a way to roll back to a known-good tag).
- **Cross-AI peer review of the v1.1 deploy** — `/gsd-review` was used heavily during v1.1 planning. Not run on the deploy plan itself per operator decision (direct push). Could be added in v1.2 if a deploy goes wrong and forensics suggests review would have caught it.
- **Real-day drift simulation script** — operator declined the "synthesize a real-day check" option in favor of waiting for organic drift to occur (or operator manually injecting a drifted state on a real weekday). If waiting becomes painful, a `tests/manual/inject_drift_for_uat.py` helper could be added.

### Reviewed Todos (not folded)

[None — todo cross-reference returned no matches for Phase 16.]

</deferred>

---

*Phase: 16-hardening-uat-completion*
*Context gathered: 2026-04-26*
