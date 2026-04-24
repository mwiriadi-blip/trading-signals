---
phase: 11
reviewers: [gemini, codex]
reviewed_at: 2026-04-24
plans_reviewed: [11-01-PLAN.md, 11-02-PLAN.md, 11-03-PLAN.md, 11-04-PLAN.md]
skipped_self: claude (running inside Claude Code CLI — skipped for review independence)
---

# Cross-AI Plan Review — Phase 11: Web Skeleton — FastAPI + uvicorn + systemd

## Gemini Review

This review evaluates the implementation plans for **Phase 11: Web Skeleton**. The plans establish the FastAPI liveness endpoint, the systemd process management layer, and the idempotent deployment automation required for the v1.1 Interactive Trading Workstation milestone.

### 1. Summary
The Phase 11 plans are exceptionally well-structured and represent a high-fidelity translation of the architectural decisions (D-01..D-25). By splitting the work into Wave 0 (Python/FastAPI), Wave 1 (Infrastructure artifacts), and Wave 2 (Operator docs), the plans ensure that each layer is independently verified before moving to the next. The use of automated "artifact guards"—tests that parse systemd units, bash scripts, and markdown docs to verify invariants—is a standout feature that provides strong regression protection against security misconfigurations (like binding to `0.0.0.0`) or documentation drift.

### 2. Strengths
- **Defense-in-Depth Security:** The hard-coded `--host 127.0.0.1` in the systemd unit, coupled with a specific `TestWebSystemdUnit` class that greps for `0.0.0.0` as a failure condition, effectively mitigates the risk of external exposure before Phase 12 (Nginx).
- **Architectural Boundary Enforcement:** The `TestWebHexBoundary` AST guard ensures the new `web/` adapter respects the hexagonal-lite architecture by preventing direct imports of the pure-math hex core (`signal_engine`, `sizing_engine`).
- **Resilient `/healthz` Implementation:** The use of the C-2 local-import pattern and the D-19 "never-crash" posture ensures that the web process remains a reliable liveness signal even if the underlying `state_manager` or state file is temporarily degraded.
- **Sophisticated Documentation Guards:** Creating a `TestCrossArtifactDriftGuard` in Wave 2 is an excellent practice. It ensures the unit names and URLs in the `SETUP-DROPLET.md` runbook stay in sync with the actual code and config, reducing the risk of operator error during manual setup.
- **Idempotency-First Deployment:** The `deploy.sh` logic follows best practices for single-operator systems (`git pull --ff-only`, `set -euo pipefail`), ensuring that deployments are predictable and fail loudly rather than entering an inconsistent state.

### 3. Concerns
- **`systemctl` Path Sensitivity (MEDIUM):** As noted in the Research findings, `systemctl` may reside at `/usr/bin/systemctl` or `/bin/systemctl`. While the plan includes a `which systemctl` step in the runbook, a mismatch in the `sudoers` entry will cause `deploy.sh` to hang on a password prompt.
- **`last_run` Precision Mismatch (LOW):** There is a discrepancy between the ISO datetime with offset shown in CONTEXT.md D-13 and the `YYYY-MM-DD` date stored in `state.json`. The plan correctly prioritizes the stored data over the aspirational schema, but this might result in a "staleness" banner in Phase 15 that only refreshes once per day, not per run.
- **Resource Timing in `deploy.sh` (LOW):** The `sleep 3` in the deploy script is a heuristic. On a very slow or overloaded droplet, uvicorn might take slightly longer to bind, causing a transient smoke-test failure.

### 4. Suggestions
- **Hard-Fail on sudoers Mismatch:** In `deploy.sh`, consider using `sudo -n systemctl ...` (`-n` for non-interactive). This will cause the script to fail immediately with an error if a password is required, rather than hanging the deployment process indefinitely.
- **Environment File Flexibility:** In the systemd unit, consider using `EnvironmentFile=-/home/trader/trading-signals/.env` (note the leading `-`). This prevents the service from failing to start if the `.env` file hasn't been created yet, which is appropriate for Phase 11 where no environment variables are consumed by the web layer.
- **Pip Cache Hygiene:** In `deploy.sh`, adding `--no-cache-dir` to the `pip install` command can prevent the small droplet's disk from filling up with cached wheels over many deployment cycles, though this is a minor optimization for this scale.

### 5. Risk Assessment
- **Overall Risk Level: LOW**
- **Justification:** The scope is strictly read-only and local-only. The plans include exhaustive unit and structural tests for every new file. The failure modes (misconfigured port or sudoers) are surfaced immediately by the `deploy.sh` smoke test or the manual verification steps in `SETUP-DROPLET.md`. The hexagonal architecture remains protected, and the project's byte-identical determinism standards are maintained.

---

## Codex Review

### PLAN 11-01

**Summary**
This is the strongest plan in the set. It is explicit about scope, ties directly to D-01..D-19, and gives enough implementation detail to make the FastAPI scaffold deterministic. The main weakness is that it over-specifies exact file contents and test counts to the point that it reduces executor judgment and creates some fragility around existing `state_manager.load_state()` semantics.

**Strengths**
- Clear containment: only `requirements.txt`, `web/`, and `tests/test_web_healthz.py`.
- Good phase fit: delivers the actual Python surface required by WEB-07 and unblocks Plans 02 and 03.
- Correct localhost-only posture is preserved indirectly by making `/healthz` lightweight and framework-native.
- Correct FastAPI idioms: `create_app()` factory plus module-level `app`; sync handler for blocking file I/O; `TestClient` for in-process tests.
- Good architectural discipline: local `state_manager` import; explicit adapter-boundary AST guard.
- Staleness rule is specified correctly as `> 2 days`, not `>= 2 days`.
- Version pins are reasonable: `fastapi==0.136.1`, `uvicorn[standard]==0.46.0`, `httpx==0.28.1`.

**Concerns**
- **HIGH**: The plan appears inconsistent with Python default-argument behavior for `load_state(path: Path = Path(STATE_FILE))`. Monkeypatching `STATE_FILE` after import will not affect the already-bound default. The plan notices this late, but many acceptance criteria still assume the simple monkeypatch path.
- **MEDIUM**: The plan disables Swagger docs (`docs_url=None`, `redoc_url=None`) even though that was not a locked requirement. It is defensible, but it is extra policy beyond the phase success criteria.
- **MEDIUM**: The healthz schema in success criteria says `{"status":"ok","last_run":"<ISO timestamp from state.json>"}`, but the implementation plan correctly returns `YYYY-MM-DD` because that is what the current state stores. That mismatch should be resolved explicitly at phase level, not buried in implementation notes.
- **LOW**: The tests are over-specified in structure and class names. That makes the plan brittle without materially improving outcome quality.
- **LOW**: The AST boundary test forbids imports of other adapters like `dashboard` and `notifier`; that is fine today, but may become unnecessary friction later if shared adapter helpers emerge.

**Suggestions**
- Make one explicit decision up front for tests: either patch `load_state` directly or add a temporary helper in the web layer to inject state-path for tests.
- Resolve the `last_run` format discrepancy at roadmap/success-criteria level: either accept `YYYY-MM-DD` or add a separate `last_run_at` later.
- Treat `docs_url=None` as optional, not mandatory, unless it is added to locked decisions.
- Relax exact test-class-count requirements; keep behavioral requirements, not cosmetic ones.

**Risk Assessment**: LOW-MEDIUM. Implementation target is sound, but there is a real test-design risk around `STATE_FILE` monkeypatching and a mild spec mismatch around `last_run` format.

---

### PLAN 11-02

**Summary**
This plan is solid and appropriately small. It commits the unit file to the repo, keeps runtime installation manual, and adds useful regression tests around bind address, worker count, and hardening directives. The main issue is that it slightly overstates what can be proven locally: parsing a unit file is helpful, but it does not prove the service actually starts or survives reboot.

**Strengths**
- Good separation of concerns: repo-managed unit file, droplet install deferred to runbook.
- Correct systemd choices: `Type=simple`, `User=trader`, `Group=trader`, `Restart=on-failure`, `After=network.target`, `Wants=trading-signals.service`, `WantedBy=multi-user.target`.
- Security posture is correct: `--host 127.0.0.1`; `--workers 1`; hardening directives present; explicit negative guard against `0.0.0.0`.
- Good use of repo tests to prevent accidental weakening of unit settings.
- Correctly preserves the single-process assumption behind the current state/cache design.

**Concerns**
- **MEDIUM**: `configparser` is not a full systemd parser. It is likely good enough here, but multi-line `ExecStart` parsing is somewhat fragile.
- **MEDIUM**: `EnvironmentFile=/home/trader/trading-signals/.env` may cause startup failure or warning if `.env` is absent. The plan mentions this later, but does not decide whether the file is required or optional.
- **LOW**: `Type=simple` is correct in practice, but the plan calls it "assumed" in research. That is fine, but worth tightening in final docs.
- **LOW**: Some hardening implications are not discussed, especially whether `ProtectSystem=strict` plus repo write access is enough for all future web behavior.

**Suggestions**
- Prefer raw-text or regex assertions for the unit file if `configparser` proves flaky; don't over-invest in parsing machinery.
- Decide explicitly whether `EnvironmentFile` should be optional: `EnvironmentFile=-/home/trader/trading-signals/.env` if optional; current form if required.
- Add one simple test asserting the unit references `web.app:app` exactly, which is the key integration point with Plan 11-01.

**Risk Assessment**: LOW. The unit definition is correct and appropriately scoped. The remaining risks are mostly about local-test fidelity, not production design.

---

### PLAN 11-03

**Summary**
This plan is mostly good and directly addresses INFRA-04, but it is the shakiest of the four because "idempotent deploy script" is partly operational behavior, not just file content. The structure is right, the sequence is sensible, and the fail-loud posture matches D-25, but the runbook and tests should be careful not to oversell true idempotency based only on static assertions.

**Strengths**
- Correct strict-mode shell posture: `#!/usr/bin/env bash` + `set -euo pipefail`.
- Correct deployment sequence: branch check → fetch → pull `--ff-only` → pip upgrade → pip install → restart both services → smoke test → success echo.
- Good safety posture: explicit non-main rejection; no rollback logic; no destructive git commands.
- Good integration with other plans: references Plan 11-01 `/healthz`; references Plan 11-02 unit name.
- Good test idea: ordering assertions are valuable and catch accidental refactors.

**Concerns**
- **HIGH**: The script is not fully idempotent in the strictest sense because `systemctl restart` always restarts healthy services. It is operationally safe, but not a true no-op second run.
- **MEDIUM**: `sleep 3` is heuristic. On a slow droplet, restart plus bind may take longer, causing a false negative smoke-test failure.
- **MEDIUM**: `sudo systemctl restart trading-signals trading-signals-web` in one invocation may not match the exact sudoers rule depending on sudo command matching semantics. This is the biggest operational risk in the set.
- **MEDIUM**: `pip install --upgrade pip --quiet` on every deploy introduces unnecessary mutation and possible variance. It is allowed by D-23, but for a small stable app it is arguably more churn than value.
- **LOW**: `curl` uses `127.0.0.1`, which is good, but success criteria elsewhere refer to `localhost`; minor wording drift only.

**Suggestions**
- Re-check sudoers compatibility carefully. Safer options: allow the exact combined command form in sudoers if supported in your environment; or split into two sudo commands and scope both exactly.
- Consider replacing `sleep 3` with a short retry loop around `curl` for up to 5-10 seconds. That is more robust and still simple.
- Reconsider whether upgrading `pip` on every deploy is necessary. If not mandated, drop it.
- Phrase "idempotent" precisely in docs: "safe to run repeatedly; second run makes no code/dependency changes and exits 0."

**Risk Assessment**: MEDIUM. The design is directionally right, but sudoers-command matching and the simplistic startup wait create meaningful deployment risk.

---

### PLAN 11-04

**Summary**
This is a useful operator runbook and closes the gap between committed artifacts and droplet reality. It is thorough, maybe slightly too thorough for Phase 11, but still proportionate because systemd install, sudoers scoping, bind verification, and reboot verification are exactly the things local tests cannot cover. The main concern is some drift between the plan text and earlier decisions, especially around whether this should be a new doc versus extending an earlier setup doc.

**Strengths**
- Covers the manual steps the code/tests cannot verify: unit installation; sudoers installation; bind-address verification; deploy smoke/idempotency verification; reboot persistence.
- Security guidance is strong: warns against `NOPASSWD: ALL`; warns against `0.0.0.0`; requires `visudo`.
- Good drift-guard concept: unit name in doc matches Plan 11-02; smoke-test URL matches Plan 11-03.
- Troubleshooting table is practical and phase-appropriate.

**Concerns**
- **MEDIUM**: The phase context suggested extending an existing Phase 10 setup doc might be preferable; this plan creates a new doc. It explains why, but that should be confirmed against actual repo state rather than planner assumption.
- **MEDIUM**: The doc hardcodes `/usr/bin/systemctl` in the sudoers snippet while also saying to check `which systemctl`. That is okay, but the exact-match tests may create friction if the actual droplet path differs.
- **LOW**: The runbook is detailed enough to verge on over-engineering for a single-operator app, though still defensible.
- **LOW**: Testing documentation with highly literal string matching creates maintenance burden without much product value.

**Suggestions**
- Keep the runbook, but reduce literal test brittleness. Focus doc tests on critical commands and warnings, not exact prose.
- Confirm whether `SETUP-DEPLOY-KEY.md` truly does not exist before committing to a sibling-doc strategy.
- Make the sudoers snippet clearly labeled as "Ubuntu default" and keep the `which systemctl` step as authoritative.

**Risk Assessment**: LOW-MEDIUM. Operationally useful and security-aware. Main risk is documentation/test brittleness, not design failure.

---

### Cross-Plan Assessment (Codex)

**Overall Summary**: The phase is well planned overall. Wave structure is correct, dependencies are mostly sound, and the plans collectively cover the four success criteria. The biggest risks are not architectural; they are spec drift and over-specification. In particular: the `/healthz` `last_run` format is inconsistent between success criteria and actual state shape, the `STATE_FILE` monkeypatch approach is shaky, and the deploy/sudoers interaction needs tighter validation.

**Cross-Plan Concerns**
- **HIGH**: `/healthz` success criteria say ISO timestamp from `state.json`, but current `state.json` stores `YYYY-MM-DD`. Reconcile before execution.
- **HIGH**: The `STATE_FILE` monkeypatch issue may cause Plan 11-01 tests to fail or require redesign.
- **MEDIUM**: The deploy script's combined `sudo systemctl restart trading-signals trading-signals-web` may not be satisfied by the sudoers rule as written, depending on sudo matching behavior.
- **MEDIUM**: "Idempotent" is used a bit loosely. Safe repeated execution is true; strict no-op is not, because restarts still happen.
- **LOW**: Plans are more prescriptive than necessary, especially around exact test classes, exact file contents, and exact doc wording.

**Overall Risk Assessment**: MEDIUM. Architecture and sequencing are good. Main risks are implementation friction from test brittleness and one real operational concern around deploy/sudoers.

---

## Consensus Summary

### Agreed Strengths (both reviewers)
- **Wave ordering** (0 → 1 parallel → 2) is correct and buys genuine parallelism in Wave 1.
- **Security posture** — loopback-only bind, scoped-by-name sudoers, unauthenticated `/healthz` by design, explicit negative guards against `0.0.0.0`.
- **Hex-boundary discipline** — local `state_manager` import in the handler, AST guard test (`TestWebHexBoundary`) forbidding adapter → hex-core imports.
- **Cross-artifact drift guard** — `TestCrossArtifactDriftGuard` in Plan 11-04 reading both the systemd unit and `deploy.sh` prevents silent name/URL drift.
- **Version pins** — `fastapi==0.136.1`, `uvicorn[standard]==0.46.0`, `httpx==0.28.1` are current, appropriate, and internally consistent.
- **Fail-loud deploy** — `set -euo pipefail` + no automatic rollback is the right default per D-25.
- **Scope discipline** — plans stay within signal-app territory; no React/DB/auth creep.

### Agreed Concerns (raised by BOTH — highest priority to fix before execute)

1. **`last_run` format mismatch** (Codex: HIGH, Gemini: LOW)
   - ROADMAP SC-2 example shows `"<ISO timestamp from state.json>"`; CONTEXT D-13 example shows `"2026-04-24T08:00:15+08:00"`; `state_manager` actually stores `YYYY-MM-DD`.
   - Plans return the stored date as-is (correct given current data shape), but the success criteria are ambiguous.
   - **Action:** Before execute, either (a) update ROADMAP SC-2 + CONTEXT D-13 to explicitly say `YYYY-MM-DD`, OR (b) decide to extend `state.last_run` to a full ISO string (bigger change, touches main.py write site + existing tests).

2. **`sleep 3` is heuristic** (both flag; Codex: MEDIUM, Gemini: LOW)
   - On a slow droplet, uvicorn bind may exceed 3s → false-negative smoke test → deploy.sh exits non-zero.
   - **Action:** Replace `sleep 3` + single curl with a retry loop: `for i in {1..10}; do curl -fsS --max-time 2 http://127.0.0.1:8000/healthz && break; sleep 1; done; curl -fsS --max-time 5 http://127.0.0.1:8000/healthz` (hard-fail on final attempt).

3. **`systemctl` path + sudoers combined-command matching**
   - Gemini: MEDIUM — `/usr/bin/systemctl` vs `/bin/systemctl` mismatch would hang deploy.sh on password prompt.
   - Codex: MEDIUM — `sudo systemctl restart trading-signals trading-signals-web` (combined form) may not match the sudoers rule depending on sudo's command-matching semantics.
   - **Action:** (a) Keep the `which systemctl` step in SETUP-DROPLET.md as authoritative. (b) Add `sudo -n` (non-interactive) to `deploy.sh` so a sudoers miss fails fast instead of hanging. (c) Consider splitting the combined restart into two sudo calls to eliminate the matching ambiguity.

4. **`EnvironmentFile` optionality not decided**
   - Gemini: suggests `EnvironmentFile=-/home/trader/trading-signals/.env` (optional prefix) for Phase 11 since no env vars are consumed yet.
   - Codex: flags MEDIUM — plan mentions the gotcha but doesn't decide.
   - **Action:** Pick one: (a) add `-` prefix (optional, fail-soft) since Phase 11 doesn't use env vars, OR (b) keep it required and document `.env` creation as a mandatory step in SETUP-DROPLET.md. Recommend (a) for Phase 11 because WEB-13 auth secret arrives in Phase 13, not 11.

### Divergent Views — worth investigating before execute

- **`STATE_FILE` monkeypatch risk** — Codex flags HIGH (Python default-arg binding means `def load_state(path: Path = Path(STATE_FILE))` captures the value at import time; monkeypatching `state_manager.STATE_FILE` after import won't retarget the default). Gemini doesn't raise this at all.
  - **Verify:** inspect `state_manager.load_state` signature. If it uses a default-argument-captured `STATE_FILE`, test fixtures must either (a) monkeypatch the `load_state` function directly, (b) pass `tmp_path` explicitly, or (c) redefine `STATE_FILE` BEFORE importing. Plan 11-01's tests need to use whichever shape works — this is worth a 5-minute codebase check before executing.

- **Overall risk level:** Gemini says LOW, Codex says MEDIUM. Gap is driven entirely by Codex's concern about test-design friction and sudoers command matching. Both agree the architecture is correct.

- **`docs_url=None` / Swagger disablement** — Codex flags MEDIUM (not in locked decisions). Gemini doesn't mention. Minor — decide now: either add "Swagger disabled in production" as D-26 in CONTEXT.md or drop the `docs_url=None` / `redoc_url=None` kwargs from `create_app()`.

- **`pip install --upgrade pip` on every deploy** — Codex MEDIUM (introduces variance on a stable app). Gemini doesn't raise. Drop unless there's a specific compatibility reason; adds churn without value.

- **Test brittleness / over-specification** — Codex LOW (several mentions). Gemini praises the same tests as "sophisticated". This is a stylistic divergence — accept Codex's framing if you want to retain refactor flexibility as the web surface grows in Phases 13-15.

### Divergent-only items (one reviewer only)

- **Gemini only**: `pip install --no-cache-dir` for droplet disk hygiene — minor, optional.
- **Gemini only**: Use `sudo -n` (non-interactive) in deploy.sh to hard-fail on sudoers mismatch — good tactical fix.
- **Codex only**: Add a test asserting the unit file references `web.app:app` exactly (Plan 11-02 cross-integration guard).

---

## Recommended Actions Before `/gsd-execute-phase 11`

**HIGH priority (fix before execute):**
1. Reconcile `last_run` format in ROADMAP SC-2 + CONTEXT D-13 with actual `state.json` schema (expected fix: update docs to say `YYYY-MM-DD`).
2. Verify `state_manager.load_state` signature and confirm Plan 11-01's monkeypatch strategy actually works; adjust test shape if needed.
3. Replace `sleep 3` in deploy.sh with a retry loop.
4. Add `sudo -n` to deploy.sh; consider splitting the combined systemctl restart into two calls.

**MEDIUM priority (decide now, document in CONTEXT.md):**
5. Decide `EnvironmentFile` optionality — recommend `-` prefix for Phase 11.
6. Decide `docs_url=None` policy — either add as D-26 or drop from `create_app()`.
7. Decide whether to drop `pip install --upgrade pip` from deploy.sh.

**LOW priority (cosmetic, can wait until Phase 16 hardening):**
8. Loosen exact test-class-count assertions in favor of behavioral pinning.
9. Add the `web.app:app` cross-integration assertion to Plan 11-02 tests.

To incorporate this feedback into replanning, run:

```
/gsd-plan-phase 11 --reviews
```

The planner will read this REVIEWS.md and produce updated plans that address the HIGH/MEDIUM items above.
