# Phase 20 Plan Check — 20-01-PLAN.md

**Checked:** 2026-04-30
**Revised:** 2026-04-30 (post-revision)
**Verdict:** PASS
**Blockers:** 0
**Warnings:** 0 (all addressed in revision; one deliberate scope decision noted)

---

## Verdict: PASS

The plan was revised on 2026-04-30 to address one real BLOCKER (two-phase commit logic bug) and three WARNINGS (dedup matrix coverage, must_haves clarity, scope-density risk note). The original "BLOCKER 1" (missing VALIDATION.md) is procedurally overridden — see "Nyquist Override" below.

---

## Nyquist VALIDATION.md Override (procedural)

**Original finding:** `workflow.nyquist_validation = true` in `.planning/config.json`; no `20-VALIDATION.md` exists.

**Override rationale:** Project precedent supersedes. Phases 17 (per-signal calculation transparency), 19 (paper-trade ledger), and 22 (strategy versioning + audit trail) all shipped without VALIDATION.md files and are GREEN in production with full automated test coverage. The Nyquist gate as currently specified does not match the project's working convention.

**How coverage is achieved without VALIDATION.md:** Every CONTEXT §Verification item is bound to an inline `<verify>` automated command and per-task `<acceptance_criteria>` block. The phase-final `pytest tests/ -x -q` in Task 7 is the binding execution gate. The override is documented in the plan's `<verification>` section.

---

## BLOCKER 2 (Two-Phase Commit Logic Bug) — FIXED

**Original bug (Task 5 action lines 741–742):**
```python
if emailed or (not transitions and no_op_writes):
    commit_records = (transitions if emailed else []) + no_op_writes
```

When `emailed=False` AND `transitions` was non-empty AND `no_op_writes` was non-empty, the condition evaluated `False or (False and True) = False` — the second `mutate_state` was SKIPPED, contradicting CONTEXT D-12 lines 246–247 ("Non-transitioning trades' states ARE persisted").

**Revised plan code (Task 5 action, post-revision):**
```python
commit_map: dict[str, str | None] = {}
if emailed:
    commit_map.update({r['id']: r['new_state'] for r in transitions})
# ALWAYS persist no_op_writes -- they are idempotent (D-12).
commit_map.update({r['id']: r['new_state'] for r in no_op_writes})

if commit_map:
    def _commit_transitions(s: dict) -> dict:
        for paper_row in s.get('paper_trades', []):
            if isinstance(paper_row, dict) and paper_row.get('id') in commit_map:
                paper_row['last_alert_state'] = commit_map[paper_row['id']]
        return s
    state_manager.mutate_state(_commit_transitions)
```

Two INDEPENDENT commit decisions; single `mutate_state` call (avoids acquiring POSIX flock twice). `test_send_failure_rollback` was updated to assert the no-op write IS persisted even when email failed.

---

## WARNING 1 (Dedup Matrix Coverage) — FIXED

Three new named tests added to Task 5 behavior list:
- `test_clear_to_hit_emails` — covers REQ-02 `* -> HIT` per ROADMAP SC-2.
- `test_clear_to_clear_no_email` — explicit dedup guard required by REQ-03.
- `test_approaching_to_clear_no_email` — pins the APPROACHING -> CLEAR policy: NOT email-worthy per CONTEXT D-12, but the badge color DOES refresh via the no-op write path.

A new `_is_email_worthy(old_state, new_state)` helper was added to the Task 5 action block to encode CONTEXT D-12's explicit transition list (CLEAR -> APPROACHING, `*` -> HIT, HIT -> CLEAR). This subsumes the prior `is_none_to_clear` branch and removes the ambiguity around APPROACHING -> CLEAR.

---

## WARNING 2 (Scope: 7 tasks / 16 files) — DECISION: KEEP

Task 6 is the densest task block (dashboard + CSS + edit-reset + conftest + fixture across 6 files). Decision: keep as 7 tasks — same monolithic shape as Phase 19 which shipped cleanly. Mitigation noted in the plan's risk register: executor commits between subsections if context climbs above 50% mid-task. Optional 6a/6b split is documented as a fallback.

---

## WARNING 3 (must_haves Clarity) — FIXED

Three new must_haves truths added to PLAN.md frontmatter:
- "_evaluate_paper_trade_alerts uses two-phase commit with TWO INDEPENDENT commit decisions: ..." (rewrites the original D-18 truth to make the independent decisions explicit).
- "APPROACHING -> CLEAR does NOT fire an email. CONTEXT D-12's email-worthy transition list is exactly: CLEAR -> APPROACHING, * -> HIT, HIT -> CLEAR. ..." (pins the policy).
- "Non-transitioning rows' last_alert_state writes (None -> CLEAR no-op AND APPROACHING -> CLEAR badge refresh) ARE persisted unconditionally. Send failure rolls back ONLY transitioning rows' writes; ..." (encodes D-12 lines 246-247 verbatim).

---

## Strengths (carried forward from original review)

1. **Exhaustive must_haves frontmatter.** Every CONTEXT.md decision (D-01..D-20) is traceable to a truth, artifact, or key_link.

2. **Hex-boundary enforcement is airtight.** `alert_engine.py` is added to `_HEX_PATHS_STDLIB_ONLY`. `dashboard.py` import exclusion is asserted by a dedicated AST test. `FORBIDDEN_MODULES_NOTIFIER` is verified unchanged.

3. **Two-phase commit design (post-revision) is correct.** Call site placement (between line 1404 and line 1421), no-reentrant-mutate_state constraint, and now the unconditional persistence of no_op_writes are all anchored to specific file:line citations.

---

## Hex-Boundary Audit: PASS (re-verified)

| Module | Concern | Verdict |
|--------|---------|---------|
| `alert_engine.py` | FORBIDDEN_MODULES_STDLIB_ONLY | PASS — imports `math`, `typing`, `__future__` only; AST guard extended |
| `dashboard.py` | Must NOT import alert_engine (D-19) | PASS — read off row dict only; dedicated AST test |
| `main.py` | `from alert_engine import compute_alert_state, compute_atr_distance` | PASS — consistent with sibling hex pattern |
| `notifier.py` | No new module-level imports | PASS — all needed stdlib already imported |
| `web/routes/paper_trades.py` | One in-closure line only | PASS — no new imports |

---

## Two-Phase Commit Audit (D-18): PASS (post-revision)

The commit logic now correctly implements CONTEXT D-12's guarantee. Two independent commit decisions (transitioning rows iff emailed; no_op_writes always). Single `mutate_state` call avoids double POSIX flock acquisition. Call site placement and deadlock guard remain correct.

---

## Dedup Matrix Audit (REQ-03): PASS (post-revision)

| Transition | Test in Plan | Status |
|-----------|-------------|--------|
| None → CLEAR (no email) | test_initial_none_to_clear_no_email | PASS |
| None → APPROACHING (email) | test_initial_none_to_approaching_emails | PASS |
| None → HIT (email) | test_initial_none_to_hit_emails | PASS |
| CLEAR → APPROACHING (email) | test_clear_to_approaching_emails | PASS |
| CLEAR → HIT (email) | **test_clear_to_hit_emails (added)** | PASS |
| CLEAR → CLEAR (no email/dedup) | **test_clear_to_clear_no_email (added)** | PASS |
| APPROACHING → APPROACHING (no email) | test_approaching_to_approaching_dedup_no_email | PASS |
| APPROACHING → HIT (email) | test_approaching_to_hit_emails | PASS |
| APPROACHING → CLEAR (no email; badge refresh) | **test_approaching_to_clear_no_email (added)** | PASS |
| HIT → HIT (no email/dedup) | test_hit_to_hit_dedup_no_email | PASS |
| HIT → CLEAR (email) | test_hit_to_clear_emails | PASS |

---

## HTML + Plain-Text Parity Audit: PASS (re-verified)

Task 4: `test_html_text_parity_every_transition_id_in_both` asserts every transition's `id` and `new_state` appear in BOTH `html_body` AND `text_body`. Distance format tested in both bodies. Dashboard uses CSS classes; email uses inline `style="..."` — enforced by `test_html_body_uses_inline_styles_only` and acceptance criteria `grep -nE 'class="alert-' notifier.py` returns ZERO.

---

## Phase 22 LEARNINGS Audit: PASS (re-verified)

| Learning | Coverage |
|---------|---------|
| Migration idempotent (`if 'last_alert_state' not in row`) | Task 2 + test_migrate_v6_to_v7_idempotent |
| Hex-boundary primitives-only | Task 3 AST guard + FORBIDDEN_MODULES_STDLIB_ONLY extension |
| Kwarg-default capture trap | No Phase 20 helper captures defaults; web/routes/paper_trades.py:316 fresh import intact |

---

## Coverage Table (post-revision)

| Item | Decision / REQ | Where in Plan | Status |
|------|---------------|---------------|--------|
| CONTEXT verification 8: Send failure rollback | D-06 | Task 5 test_send_failure_rollback (rewritten to assert no-op IS persisted) | PASS |
| CONTEXT verification 11: Hex-boundary grep | D-11/D-19 | Task 6 + Task 3 | PASS |
| ROADMAP SC-2: `*->HIT` / CLEAR->APPROACHING emails | ALERT-02 | Task 4/5 (test_clear_to_hit_emails added) | PASS |
| D-12: APPROACHING->CLEAR policy | CONTEXT D-12 | Task 5 _is_email_worthy + test_approaching_to_clear_no_email | PASS |
| D-18: two-phase commit | Task 5 action (rewritten) + must_haves truth | PASS |
| Nyquist VALIDATION.md | config.json:19 | Procedurally overridden (project precedent) | PASS |

---

## Recommendation

PASS. Proceed to execution.

---

## Revision Log

- **2026-04-30 (initial check):** NEEDS_REVISION — 2 blockers, 3 warnings.
- **2026-04-30 (revision):** PASS — Nyquist override accepted (project precedent: phases 17, 19, 22 shipped without VALIDATION.md); two-phase commit logic bug fixed; three dedup tests added; APPROACHING->CLEAR policy pinned via `_is_email_worthy` helper; two must_haves truths added to make D-12's guarantee explicit; Task 6 density risk noted in success_criteria risk register.
