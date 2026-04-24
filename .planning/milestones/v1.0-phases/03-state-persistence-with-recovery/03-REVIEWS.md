---
phase: 3
reviewers: [gemini, codex]
reviewed_at: 2026-04-21
plans_reviewed:
  - 03-01-PLAN.md
  - 03-02-PLAN.md
  - 03-03-PLAN.md
  - 03-04-PLAN.md
self_skipped: claude (running inside Claude Code for independence)
---

# Cross-AI Plan Review — Phase 3

> Independent review of the 4-plan, 4-wave Phase 3 set (State Persistence with Recovery) by external AI CLIs. Run via `/gsd-review --phase 3 --all` on 2026-04-21.

---

## Gemini Review

This review evaluates implementation plans **03-01** through **03-04** for **Phase 3: State Persistence with Recovery**.

### 1. Summary
Phase 3 is an exceptionally well-designed component that correctly positions `state_manager.py` as the dedicated I/O hex of the system. The plans prioritize data durability via a robust atomic write protocol and defensive corruption recovery. The strategy for managing the "Phase 4 boundary"—specifically the risk of double-counting trading costs—is handled with high-signal documentation and proactive testing. The transition from literal stubs in Wave 1 to full composition in Wave 2 is a pragmatic approach to managing internal dependencies during development.

### 2. Strengths
*   **Durability-First I/O:** The implementation of `_atomic_write` (Plan 03-02) correctly includes the POSIX-required directory `fsync`, which many persistence layers omit. This ensures the `os.replace` (rename) is durable against power loss, not just OS crashes.
*   **Structural Boundary Enforcement:** The Wave 0 (Plan 03-01) task to extend the AST blocklist with a custom `FORBIDDEN_MODULES_STATE_MANAGER` set is an excellent use of automated architectural governance. It ensures that the I/O hex remains isolated from math logic while still allowing required stdlib modules like `os` and `json`.
*   **Proactive Integration Testing:** The inclusion of `test_record_trade_phase_4_boundary_gross_pnl_not_realised_pnl` (Plan 03-04) is a masterclass in defensive engineering. By simulating the exact bug Phase 4 is prone to make (double-deducting costs), it transforms a "docstring warning" into a breaking test case.
*   **Narrow Corruption Scope:** Defining corruption strictly as `JSONDecodeError` (Plan 03-03) prevents the system from "re-initializing" (wiping state) when a logic bug raises a `ValueError` or `KeyError`, which is the correct defensive posture for a financial system.

### 3. Concerns

*   **Semantic Corruption (Valid but Empty JSON):**
    *   **Severity: MEDIUM**
    *   **Reason:** If `state.json` is overwritten with `{}`, `json.loads()` will succeed, bypassing the `JSONDecodeError` recovery. Plan 03-02's `_migrate` defaults the version to 0 and walks it forward, but the resulting dict might still be missing `account` or `positions` keys if they weren't in the file.
    *   **Context:** `load_state` in Plan 03-03 calls `_migrate(state)`, but `_migrate` (Plan 03-02) does not currently enforce a "complete schema" check for valid-but-truncated files.

*   **Warning Overflow in a Single Run:**
    *   **Severity: LOW**
    *   **Reason:** `MAX_WARNINGS = 100` is plenty for a daily cadence. However, if a future fetch/sizing bug causes a loop that appends thousands of warnings in a single execution, the FIFO slice in `append_warning` handles it, but the overhead of repeatedly slicing/copying a large list could be inefficient.

### 4. Suggestions

*   **Enforce Schema Completion in `_migrate`:**
    *   **File:** `state_manager.py` (Plan 03-02/03-03)
    *   **Suggestion:** Modify `_migrate` to ensure that even if the JSON is valid, if it's missing top-level keys required by `STATE-01`, it fills them with defaults from `reset_state()` or treats it as a recovery event.
    *   **Specific Action:** In Plan 03-02, add a `TestSchemaVersion` case: `test_load_empty_json_dict_fills_missing_keys`.

*   **Atomic Write Tempfile Suffix:**
    *   **File:** `state_manager.py:85` (Plan 03-02)
    *   **Suggestion:** Ensure `NamedTemporaryFile` uses a suffix that distinguishes it from the `state.json.corrupt.<ts>` format, such as `.tmp`. Plan 03-02 already uses `suffix='.tmp'`, which is good.

### 5. Risk Assessment
**Overall Risk: LOW**

The risk is minimized by the high degree of test coverage (32 new tests) and the use of the `tmp_path` fixture for isolation. The most critical failure modes—partial writes and closing-cost double-counting—are addressed via POSIX-standard idioms and explicit "bug-path" simulation tests. The reliance on Python stdlib only for the I/O hex makes it highly portable and easy to verify.

### 6. Goal Achievement
**Verdict: YES.**
The 4 plans successfully deliver a `state_manager.py` that the orchestrator can rely on. By the end of Wave 3, the orchestrator has a "one-stop-shop" for all mutations (trades, warnings, equity) and a bulletproof load/save mechanism that protects the $100,000 hypothetical account history.

---

## Codex Review

### Summary

The Phase 3 plan set is strong overall: it is explicit, traceable to STATE-01..07, and sequenced in a way that de-risks the core persistence guarantees before trade-accounting logic lands. The best parts are the clear separation of Wave 0 scaffolding, Wave 1 durability primitives, Wave 2 recovery/warnings, and Wave 3 accounting boundaries. The main residual risk is not missing scope, but a few correctness and operability gaps around semantic validation on load, directory fsync ordering, backup naming/path assumptions, and the boundary between "recoverable corruption" vs "valid JSON but invalid state." With a small number of targeted adjustments, this is a credible plan set for a durable `state_manager.py`.

### Strengths

- Clear wave decomposition:
  - `03-01` establishes constants, module surface, tests, and the AST guard before logic arrives.
  - `03-02` isolates atomic write and schema migration.
  - `03-03` isolates reset/recovery/warnings.
  - `03-04` isolates trade accounting and Phase 4 contract boundaries.

- Good requirement traceability:
  - Each wave maps cleanly to STATE requirements and success criteria.
  - The named tests line up well with the requirements and decisions.

- Strong architecture discipline:
  - The explicit "I/O hex" boundary is well defined.
  - The separate AST rule for `state_manager.py` is the right move; reusing the pure-math blocklist would have been wrong.

- Good test design choices:
  - `tmp_path` isolation is appropriate.
  - `now=` injection is cleaner than adding `pytest-freezer`.
  - Mocking `state_manager.os.replace` is the right patch target.

- Good attention to persistence details:
  - `tempfile` in the same directory.
  - `allow_nan=False`.
  - explicit temp cleanup on failure.
  - schema version walk-forward hook.

- The Phase 4 boundary around `gross_pnl` vs `realised_pnl` is surfaced repeatedly:
  - in docs,
  - in helper docstrings,
  - in acceptance criteria,
  - and in a named test with concrete arithmetic.

### Concerns

- **HIGH**: `load_state()` migrates but does not semantically validate required top-level shape after parse.
  - Current plans treat only `JSONDecodeError` as corruption, which is fine, but there is no explicit post-parse validation for STATE-01 keys/types.
  - A file like `{"schema_version":1}` is valid JSON, will parse, may migrate, and then downstream code can crash later in less obvious ways.
  - D-05 says schema mismatches should raise, not silently recover. The plans should implement that explicitly.

- **HIGH**: Atomic write ordering is slightly off in the described pattern.
  - The standard durable sequence is usually:
    1. write temp
    2. flush + fsync temp file
    3. `os.replace(temp, target)`
    4. fsync parent directory
  - The plans/research repeatedly say fsync parent dir before `os.replace`, which does not make the rename durable.
  - This does not break atomicity, but it weakens the durability claim in STATE-02.

- **MEDIUM**: `_backup_corrupt()` hardcodes `state.json.corrupt.<ts>` instead of deriving from `path.name`.
  - The current implementation is fine for the canonical path, but less robust for tests or future reuse with non-default paths.
  - Since the function accepts `path: Path`, it should probably use `f'{path.name}.corrupt.{ts}'`.

- **MEDIUM**: Backup naming can collide within one second.
  - Accepted in the docs, but still a real edge case if recovery loops or multiple calls happen in the same second.
  - Low probability, but simple to harden.

- **MEDIUM**: `record_trade` validation is incomplete for numeric fields.
  - D-15 requires "wrong types" to raise, but the implementation only validates `instrument`, `direction`, and `n_contracts`.
  - `entry_price`, `exit_price`, `gross_pnl`, `multiplier`, `cost_aud`, `entry_date`, `exit_date`, `exit_reason` are not type-checked in the proposed code.
  - That leaves room for silent bad state or later `save_state` failures.

- **MEDIUM**: `record_trade` mutates the caller's trade dict in place before logging.
  - That is acceptable if intentional, but the plans do not call it out as part of the contract.
  - If Phase 4 reuses the same dict after calling `record_trade`, the mutation may surprise it.

- **MEDIUM**: Warning retention of 100 may be too tight during repeated failure days.
  - Daily cadence makes 100 usually fine, but a single bad run loop or repeated subsystem warnings could churn out meaningful history quickly.
  - Not a blocker, but worth considering whether truncation should be per-run deduped or at least documented as "best effort history."

- **LOW**: `load_state(path missing) -> reset_state()` returns fresh state but does not persist it.
  - That is probably the right choice for Phase 3, but it means "first run" does not create `state.json` until a later `save_state`.
  - Fine if deliberate, but worth stating explicitly in the contract.

- **LOW**: `update_equity_history` intentionally does no validation.
  - That matches D-04, but a malformed `date` or non-finite `equity` will only be caught later, if at all.
  - Acceptable, but it slightly weakens "orchestrator can rely on it durably."

### Suggestions

- Add explicit post-parse state validation in `03-02` or `03-03`.
  - In `state_manager.py`, add a private helper like `_validate_loaded_state(state)` after `_migrate(state)` and before returning.
  - It should verify STATE-01 top-level keys and basic container types, and raise `ValueError` on mismatch.
  - This matches D-05's "schema mismatches raise as bugs" stance.

- Fix the atomic durability sequence in `03-02-PLAN.md`, Task 1.
  - Change `_atomic_write` to:
    1. write temp
    2. flush/fsync temp
    3. `os.replace`
    4. fsync parent dir on POSIX
  - Update the acceptance criteria wording accordingly.

- Make `_backup_corrupt()` derive the backup filename from `path.name`.
  - In `03-03-PLAN.md`, Task 1, replace `backup_name = f'state.json.corrupt.{ts}'` with `backup_name = f'{path.name}.corrupt.{ts}'`.
  - Tests can still assert `state.json.corrupt.<ts>` when `path.name == 'state.json'`.

- Strengthen `record_trade` validation in `03-04-PLAN.md`.
  - Add checks that:
    - `entry_date` and `exit_date` are strings,
    - `exit_reason` is a string,
    - `entry_price`, `exit_price`, `gross_pnl`, `multiplier`, `cost_aud` are numeric.
  - Optional but useful: reject bool for numeric fields.

- Add one test for "valid JSON, invalid shape raises."
  - Suggested location: `tests/test_state_manager.py::TestSchemaVersion` or a new test in `TestLoadSave`.
  - Example: write `{"schema_version": 1}` and assert `load_state()` raises `ValueError` and does not create a corrupt backup.

- Add one test for parent-path preservation in corruption backup.
  - In `TestCorruptionRecovery`, assert the backup is created in `path.parent`, but the name is path-derived.

- Clarify the in-place mutation contract for `record_trade`.
  - In `state_manager.py` docstring or `03-04` task text, state explicitly whether mutating `trade` is intentional.
  - If you want cleaner boundaries, append `dict(trade, net_pnl=net_pnl)` instead of mutating the input object.

- Consider making the warning cap configurable but phase-defaulted.
  - `MAX_WARNINGS = 100` is acceptable; adding a short note in the plan that this is intentionally conservative for v1 would close the loop.

### Risk Assessment

**Overall risk: MEDIUM**

The plan set is well structured and likely implementable without major churn, so this is not high risk. The remaining risk comes from a few subtle persistence semantics that matter a lot in a stateful system: the fsync/rename durability ordering, the absence of explicit semantic validation for parsed JSON, and under-specified `record_trade` validation. Those are all fixable within the current plan shape, and once addressed, the Phase 3 design would drop to low risk.

---

## Consensus Summary

Both reviewers (Gemini, Codex) agree the plan set is **well-structured, traceable, and architecturally sound**. The Wave 0 scaffolding sequence (constants → stubs → AST blocklist) and the proactive Phase 4 boundary test are both called out as standout decisions. They diverge on overall risk: **Gemini = LOW** (test coverage and atomic-write protocol are robust), **Codex = MEDIUM** (calls out specific persistence-semantics issues that should be tightened before execution).

### Agreed Strengths

- **AST-blocklist hex enforcement (Wave 0)** — separate `FORBIDDEN_MODULES_STATE_MANAGER` set rather than reusing the pure-math blocklist is the correct architectural move.
- **Phase 4 boundary test (`test_record_trade_phase_4_boundary_gross_pnl_not_realised_pnl`)** — both call out the worked numerical example as exemplary defensive engineering.
- **`tmp_path` test isolation + clock injection** — both prefer `now=None` defaulting to `datetime.now(...)` over `pytest-freezer`.
- **Narrow `JSONDecodeError`-only corruption catch** — both agree this is the right defensive posture (vs. broader ValueError that would mask bugs).
- **Atomic write protocol with POSIX directory fsync** — both agree the durability protocol is in the right shape (though Codex flags the ordering — see below).

### Agreed Concerns

1. **Semantic validation gap for valid-but-incomplete JSON** (Codex HIGH, Gemini MEDIUM). Both reviewers independently flag the same issue: `{"schema_version": 1}` is valid JSON, will parse, will migrate (no-op), and then downstream code crashes when accessing missing keys (account, positions, etc.). D-05 says "schema mismatches RAISE as bugs", but the plans don't currently implement a post-parse semantic validator. **This is the single most important consensus concern.**

2. **`record_trade` validation depth** (implicit Gemini, explicit Codex MEDIUM). D-15 says "raises ValueError on missing/wrong fields", but the planned implementation only validates `instrument`, `direction`, and `n_contracts`. Numeric fields (`entry_price`, `exit_price`, `gross_pnl`, `multiplier`, `cost_aud`) and string fields (`entry_date`, `exit_date`, `exit_reason`) are not type-checked. Phase 4 wire-up bugs could silently corrupt trade_log.

### Codex-Only HIGH Severity (not raised by Gemini)

3. **Atomic write durability ordering bug** — Plans/research describe the sequence as "write → fsync(file) → close → fsync(parent dir) → os.replace". The canonical durable sequence is "write → fsync(file) → os.replace → fsync(parent dir)". The parent-dir fsync's purpose is to make the RENAME durable; fsync'ing before the rename means the rename itself isn't on disk yet. This is a real correctness issue for the STATE-02 durability claim — the atomicity (no torn writes) is preserved, but the durability against power loss after the rename is weakened. Confirmed against canonical references (LWN durability discussions, Linux kernel rename guarantees).

### Codex-Only MEDIUM (not raised by Gemini)

4. **`_backup_corrupt` hardcodes `'state.json.corrupt.<ts>'`** instead of deriving from `path.name`. Function accepts `path: Path` so it should use `f'{path.name}.corrupt.{ts}'` for robustness with non-default paths (tests, future reuse).

5. **`record_trade` mutates caller's trade dict in place** before appending to trade_log. Not documented as part of the contract — Phase 4 reusing the same dict afterwards may be surprised. Codex suggests using `dict(trade, net_pnl=net_pnl)` for cleaner boundaries.

6. **Backup naming collision within one second** — the ISO-second-resolution timestamp can collide if recovery loops or multiple calls happen in the same second. Low probability, simple to harden (add nanosecond suffix or pid).

7. **Warning retention of 100 may be tight during failure days** — single bad run loop could churn meaningful history. Codex suggests documenting as "best effort history" or making per-run deduped.

### Codex-Only LOW

8. **`load_state(missing file) → reset_state() but doesn't persist`** — first run doesn't create `state.json` until a later `save_state` call. Fine if deliberate, worth documenting as part of contract.

9. **`update_equity_history` no validation** — malformed `date` or non-finite `equity` only caught later. Matches D-04 but slightly weakens the "durably reliable" claim.

### Divergent Views

- **Risk grade**: Gemini LOW vs Codex MEDIUM. The delta is mostly Codex's HIGH concerns — Gemini did not weight the atomic-write ordering issue (concluded the protocol "correctly includes the POSIX-required directory fsync" without checking the ORDER), and weighted the semantic-validation issue as MEDIUM rather than HIGH. Codex weighed both as HIGH.
- **Schema-completion fix**: Gemini suggests `_migrate` should fill missing keys with defaults (treat as recovery). Codex says `_validate_loaded_state` should raise ValueError on missing keys (per D-05). These are opposite remedies for the same problem — operator decision required.

### Recommended Next Steps (ranked)

1. **Fix atomic write ordering** (Codex HIGH #3) — Update `_atomic_write` in 03-02-PLAN.md Task 1 and RESEARCH.md to: write → flush → fsync(file) → close → `os.replace` → fsync(parent dir). Update the AC's grep checks and TestAtomicity to verify the order via mock-call sequence assertion. **This is a real correctness concern, not just style.**

2. **Decide semantic-validation policy + add validator** (consensus HIGH/MEDIUM) — Pick between (a) Gemini's "fill missing keys with defaults" approach (treats incomplete JSON as recoverable) OR (b) Codex's "raise ValueError per D-05" approach (treats incomplete JSON as a bug to surface). D-05 textually supports option (b). Add `_validate_loaded_state` private helper to 03-03-PLAN.md (or 03-02 if planner prefers to do it earlier). Add `test_load_state_valid_json_missing_keys_raises_value_error` to TestLoadSave or TestSchemaVersion.

3. **Strengthen `record_trade` validation** (Codex MEDIUM #5) — Add type checks for the remaining 8 fields (numeric: entry_price, exit_price, gross_pnl, multiplier, cost_aud; string: entry_date, exit_date, exit_reason). Reject bool for numeric fields (Python quirk: `isinstance(True, int)` is True).

4. **`_backup_corrupt` derive name from `path.name`** (Codex MEDIUM #4) — One-line fix in 03-03-PLAN.md. Tests still assert `state.json.corrupt.<ts>` for the canonical path.

5. **Document `record_trade` mutation contract** (Codex MEDIUM #5) — Either explicitly document "mutates input trade dict by adding net_pnl" in docstring/AC, OR refactor to non-mutating `dict(trade, net_pnl=net_pnl)`. Prefer the latter for cleaner Phase 4 integration.

6. **Backup-name collision hardening** (Codex MEDIUM #6) — Optional. Add millisecond/nanosecond suffix to ISO timestamp: `20260421T093045_123456Z`. Trivial code change.

7. **Document load-on-missing-file contract** (Codex LOW #8) — Add note to `load_state` docstring: "If state.json does not exist, returns fresh state from reset_state() but does NOT persist it; orchestrator must call save_state to materialize."

8. **`update_equity_history` minimal validation** (Codex LOW #9) — Optional. Add `assert isinstance(date, str) and len(date) == 10` (ISO YYYY-MM-DD) and `math.isfinite(equity)` checks. Trivial code change.

These 8 items map cleanly into a `/gsd-plan-phase 3 --reviews` revision pass. Items 1, 2, 3 are correctness/contract issues that should be addressed before execution. Items 4, 5, 6, 7, 8 are quality improvements that can be folded in or deferred per planner discretion.
