---
phase: 5
reviewers: [gemini, codex]
reviewed_at: 2026-04-22T07:00:00+08:00
plans_reviewed:
  - 05-01-PLAN.md
  - 05-02-PLAN.md
  - 05-03-PLAN.md
skipped_reviewers:
  - claude (running inside Claude Code — self-review excluded)
  - opencode, qwen, cursor, coderabbit (not installed)
---

# Cross-AI Plan Review — Phase 5 Dashboard

Gemini + Codex reviewed the full Phase 5 plan set (3 PLAN.md + CONTEXT + UI-SPEC + RESEARCH + PATTERNS + VALIDATION). Internal plan-checker returned 8/8 PASS.

**Gemini verdict:** PASS (LOW risk) — 2 LOW findings.
**Codex verdict:** HIGH risk — 3 HIGH + 3 MEDIUM findings.

Adversarial review paid off: Codex surfaced three structural issues the internal checker missed.

---

## Gemini Review

### Summary

The Phase 5 plan set is exceptionally robust and demonstrates a high degree of alignment with the "adversarial review" posture. It correctly identifies and mitigates all critical pitfalls researched in this session — specifically the `</script>` injection vector, Chart.js SRI hash verification, and the fixed-height parent requirement for Chart.js. The architectural "hex-lite" boundary is strictly maintained through re-implementation of sizing math, enforced by an AST blocklist that is extended before a single line of render logic is written.

### Strengths

1. **SRI Integrity & CDN Verification**: Verified hash `sha384-MH1axGwz/...` is used consistently; stale placeholder from CONTEXT D-12 correctly discarded.
2. **Structural Failure Isolation**: `main.py` integration (D-06) uses a dedicated `_render_dashboard_never_crash` helper with a broad `except Exception` catch. Called in both `--test` and `--once` paths.
3. **Injection Defense**: Dual-layer — `html.escape` at the leaf for HTML context + `.replace('</', '<\\/')` for `<script>` context — is industry-standard.
4. **Math Guards**: Sharpe includes guards for `len<30`, `stdev==0`, `equity<=0`.
5. **B-1 Retrofit Wiring**: `last_close` addition to signal state correctly identified as a prerequisite for the "Current" column; properly asserted in `test_main.py`.
6. **Atomic Write Parity**: Verbatim mirroring of Phase 3 `_atomic_write` including D-17 post-replace fsync.

### Concerns

#### G-1. LOW: Golden snapshot stability (float precision)

- **Location:** `dashboard.py` chart payload serialisation
- **Risk:** Plan uses `json.dumps(..., sort_keys=True)` but doesn't explicitly specify `allow_nan=False` or fixed float precision.
- **Impact:** Subtle OS/Python float-repr differences (`100.0` vs `100.00000000000001`) could cause flaky byte-match failures.
- **Mitigation:** `regenerate_dashboard_golden.py` is the authority; re-run on flakiness.

#### G-2. LOW: `net_pnl` vs `realised_pnl` traceability

- **Location:** `05-02-PLAN.md` Task 3 `_render_trades_table`
- **Risk:** Using `realised_pnl` from sizing_engine (doesn't exist in trade_log) instead of `net_pnl` from state_manager.record_trade would produce a $3-$6/trade P&L discrepancy.
- **Mitigation:** Plan includes UI-SPEC F-8 pitfall note.

### Suggestions

- **G-S1:** In 05-01 Task 5, broaden the grep: `grep -r ".keys() ==" tests/` to catch any orchestrator tests that might fail when `last_close` is added to the signals dict.
- **G-S2:** Write the Chart.js fixed-height rationale as a CSS comment inside `_INLINE_CSS` so future operators don't "optimize" it away:
  `/* Fixed height mandatory for Chart.js maintainAspectRatio: false */`

### Risk Assessment: LOW

Phase 5 plan set is extremely low-risk. Phased execution (Scaffold → Math/Formatters → Shell/Integration), parity tests (math re-implementation vs sizing_engine), and byte-exact golden snapshots provide high confidence.

---

## Codex Review

### Summary

The plan set is strong: the wave split is sensible, the hex-lite fence is explicit, the stale Chart.js SRI placeholder was corrected consistently, and the test strategy is much better than average for a static-render phase. The main things the internal checker seems to have missed are not in the dashboard math; they're in cross-phase contract handling and operational safety. There are **three material issues**: the plans misuse `pytz` in a way that can make frozen times wrong, the D-06 "never crash the run" wrapper does not actually isolate import-time dashboard failures, and the proposed `--test` integration violates the current structural read-only contract in `main.py`.

### Strengths

- SRI story is materially better than the base CONTEXT (all 3 plans consistently use the verified hash).
- Hex-lite enforcement is good — `FORBIDDEN_MODULES_DASHBOARD` + parity test against `sizing_engine.compute_unrealised_pnl()` is the right pattern.
- Wave separation clean: scaffolds → pure math/render → shell/write/integration.
- B-1 retrofit is additive and local. Verified only one existing `tests/test_main.py` assertion depends on signal dict shape (lines 424-431), which the plan extends.
- Atomic write mirroring state_manager._atomic_write is right; POSIX parent-dir fsync correct.
- 9 DASH requirements covered; most ROADMAP success criteria tied to named tests.

### Concerns

#### C-1. HIGH: `pytz` is used incorrectly throughout the artifacts and plans

Multiple places construct Perth datetimes as `datetime(..., tzinfo=pytz.timezone('Australia/Perth'))` instead of `.localize(...)`. With `pytz`, direct `tzinfo=` assignment is wrong and yields a historical offset (LMT +07:43:24 for Perth pre-1895) or non-AWST-normalized values. Appears in:
- `05-UI-SPEC.md` examples
- `05-RESEARCH.md` examples
- `tests/regenerate_dashboard_golden.py` scaffolding in `05-01-PLAN.md`
- Wave 2 commands in `05-03-PLAN.md`

**Impact:** Breaks DASH-08 ("Last updated in AWST") and makes golden bytes unstable for the wrong reason — golden file rendered on one machine may not byte-match another.

**Fix:**
```python
PERTH = pytz.timezone('Australia/Perth')
FROZEN_NOW = PERTH.localize(datetime(2026, 4, 22, 9, 0))
```
Never pass a pytz timezone via `tzinfo=`. Always go through `.localize()` or use `zoneinfo.ZoneInfo` (Python 3.9+) which DOES accept `tzinfo=` directly.

#### C-2. HIGH: D-06 failure isolation is incomplete because `main.py` imports `dashboard` at module load

`05-03-PLAN.md` Task 3 Edit 1 adds `import dashboard` at the top of main.py, then wraps ONLY the call site in try/except. If `dashboard.py` has a syntax error, bad import, or any import-time exception, `main.py` fails at import time — before `_render_dashboard_never_crash()` ever runs.

**Impact:** D-06 contract ("dashboard render failure never crashes run") silently broken. Any operator mistake in dashboard.py (e.g. a stray syntax error from manual debugging, a bad constant reference) would take down the entire daily run — including state.json write, logs, and future email.

**Fix:** Move the import inside the protected helper:
```python
def _render_dashboard_never_crash(state, path, now):
    try:
        import dashboard
        dashboard.render_dashboard(state, path, now)
    except Exception as e:
        logger.warning('[Dashboard] WARN render failed: %s', e)
```
This makes import-time failures equivalent to runtime failures — both caught, both logged, neither crashes the run.

#### C-3. HIGH: Rendering in `--test` mode breaks the current read-only contract

Current `main.py` explicitly documents `--test` as a structural read-only guarantee: skip `save_state` and return (`main.py:341-349`, `main.py:544-557`). `05-03-PLAN.md` intentionally adds `dashboard.html` writes in `--test` mode. That's a behaviour change, not an implementation detail — it may be useful (operator wants to preview the dashboard without mutating state), but it conflicts with the existing CLI-01 contract and likely with operator expectation.

**Impact:** Phase 4 test `test_test_flag_leaves_state_json_mtime_unchanged` still passes (it only asserts on `state.json` mtime), but any observer tool or operator relying on "nothing on disk changes during --test" would see `dashboard.html` mutate. The "structurally read-only" phrasing becomes false-in-spirit.

**Fix choices (pick ONE, amend plan + main.py docstring):**
- **Option A (recommended):** Keep `--test` structurally read-only. Dashboard rendering only on non-`--test` runs. Phase 6 may revisit if operator wants `--test` to render a preview dashboard.
- **Option B:** Expand `--test` contract to "no state.json mutation, but cosmetic artifacts (dashboard.html) may update". Amend main.py docstring + CLAUDE.md "--test is structurally read-only" phrase.

#### C-4. MEDIUM: `</script>` injection test is weaker than it looks

In `05-03-PLAN.md` Task 1, `test_chart_payload_escapes_script_close` finds the first `</script>` after the inline script start, then asserts `'</script>' not in inline_script`. If an injected raw `</script>` appears inside payload, that first `.find()` can stop at the injected tag, so the test can false-pass.

**Fix:** Strengthen the injection test with literal count/assertion:
```python
assert html_text.count('</script>') == expected_count  # e.g. 1 (only the real script tag close)
assert '{"labels": ["<\\/script>' in html_text  # assert the escaped form IS present
```

#### C-5. MEDIUM: D-15 escape coverage is asserted too narrowly

Plans test escaping on `exit_reason`, but not on: `signal_as_of` string, `entry_date`/`exit_date` strings, unknown exit_reason fallback, future non-canonical symbol/display fallback.

**Fix:** Add one escape regression test per render surface:
- `test_signal_card_escapes_signal_as_of()`
- `test_trades_table_escapes_unknown_exit_reason()`
- `test_positions_table_escapes_display_fallback()`

#### C-6. MEDIUM: `python -m dashboard` CLI specified in CONTEXT but not planned

CONTEXT D-05 says a convenience CLI exists (`python -m dashboard`). None of the plans actually implement or test it. If that contract matters, it's currently dropped.

**Fix:** Either amend CONTEXT D-05 to remove the convenience CLI, OR add a small entrypoint task:
```python
if __name__ == '__main__':
    from state_manager import load_state
    render_dashboard(load_state(), Path('dashboard.html'))
```

#### C-7. LOW: Golden byte stability on Windows

`_atomic_write_html(..., mode='w', encoding='utf-8')` is fine on macOS/Linux, but on Windows newline translation (`\r\n` vs `\n`) changes bytes.

**Fix (if cross-platform golden matters):**
```python
open(path, 'w', encoding='utf-8', newline='\n')  # force LF
```

#### C-8. LOW: Plan snippet sloppiness

`05-01-PLAN.md` example `python -c "import dashboard; dashboard.render_dashboard({}, Path('/tmp/x.html'))"` uses `Path` without importing it. Acceptance commands should be dry-runnable as-is.

### Risk Assessment: HIGH

Overall architecture is good, but three structural issues can produce real breakage or contract drift: incorrect `pytz` usage (C-1), incomplete failure isolation due to top-level `import dashboard` (C-2), and `--test` no longer being read-only (C-3). All three are fixable without redesigning the phase, but plans should NOT be shipped unchanged.

---

## Consensus Summary

### Agreed Strengths (both reviewers)

- Wave decomposition is clean: scaffold → math/render → shell/integration, sequential via shared `dashboard.py`.
- Chart.js SRI hash is the verified value (`sha384-MH1axGwz/...`); stale CONTEXT D-12 placeholder correctly overridden.
- Hex-lite enforcement via AST blocklist + parity test against sizing_engine is the right pattern.
- Atomic write mirrors state_manager._atomic_write (D-17 ordering preserved).
- B-1 retrofit is additive and local to main.py:514-519; single test extension.
- 9 DASH requirements covered with named tests.
- `</script>` injection + XSS escape are correctly understood as separate defense layers.
- Sharpe math guards are thorough (<30 samples, stdev==0, log(0/-ve)).

### Agreed / Cross-Reviewer Concerns

No strict overlap in top findings — but both reviewers converged on the broader observation that the plans are thorough on dashboard-internal math and thin on integration-boundary semantics.

### Unique to Codex — HIGHEST PRIORITY

**These must be fixed before execution:**

1. **C-1 [HIGH] pytz localize misuse** — `datetime(..., tzinfo=pytz.timezone(...))` is wrong everywhere it appears (UI-SPEC, RESEARCH, Wave 0 regenerator, Wave 2 commands). Fix to `PERTH.localize(datetime(...))`. Affects DASH-08 AWST timestamp correctness + golden byte stability.

2. **C-2 [HIGH] D-06 import-time failure escape hatch** — Move `import dashboard` INSIDE `_render_dashboard_never_crash`. Prevents import-time dashboard errors from crashing main.py.

3. **C-3 [HIGH] `--test` contract** — Plans render dashboard.html in `--test`, violating Phase 4's "structurally read-only" contract. Pick Option A (no dashboard in --test) OR Option B (amend contract). Document the choice.

### Unique to Codex — MEDIUM

4. **C-4 `</script>` test false-pass risk** — `.find()`-based assertion can stop at injected tag. Use `html_text.count('</script>') == expected` + assert escaped form is present.
5. **C-5 Escape coverage narrow** — add per-surface escape tests (signal_as_of, exit_date, unknown exit_reason fallback).
6. **C-6 `python -m dashboard` CONTEXT-only** — either implement the convenience CLI or amend CONTEXT D-05 to remove it.

### Unique to Codex — LOW

7. **C-7 Windows newline translation** — add `newline='\n'` to `_atomic_write_html` if cross-platform goldens matter.
8. **C-8 Plan snippet uses `Path` without importing** — dry-runnable commands only.

### Unique to Gemini — LOW

- **G-1 Float precision** — `json.dumps` default repr usually stable but not guaranteed; rely on regenerator as authority.
- **G-2 net_pnl vs realised_pnl** — plans already call this out via UI-SPEC F-8 pitfall note.
- **G-S1 Grep suggestion** — broaden `grep -r ".keys() ==" tests/` to catch orchestrator tests that might fail when last_close is added.
- **G-S2 CSS comment** — write the Chart.js fixed-height rationale as an inline CSS comment to prevent future "optimization".

### Combined Risk Assessment

| Reviewer | Verdict |
|----------|---------|
| Gemini | **LOW** — 10/10 PASS; 2 LOW observations |
| Codex | **HIGH** — 3 HIGH + 3 MEDIUM + 2 LOW; must revise |

**Combined: HIGH** — block execution until C-1, C-2, C-3 are resolved.

---

## Next Step

Incorporate feedback into planning:

```
/gsd-plan-phase 5 --reviews
```

Expected revisions (by file):

**Blocking (C-1, C-2, C-3):**
- `05-UI-SPEC.md`, `05-RESEARCH.md`, `05-01-PLAN.md`, `05-03-PLAN.md` — replace all `datetime(..., tzinfo=pytz.timezone('Australia/Perth'))` with `PERTH.localize(datetime(...))` or migrate to `zoneinfo.ZoneInfo('Australia/Perth')` and pass via `tzinfo=` directly (C-1)
- `05-03-PLAN.md` Task 3 Edit 1 — move `import dashboard` inside `_render_dashboard_never_crash` helper body (C-2)
- `05-CONTEXT.md` or `05-03-PLAN.md` — explicit decision on `--test` + dashboard render. Recommend Option A (no dashboard in --test); update CLI-01 test to assert `dashboard.html` mtime unchanged on --test if operator agrees (C-3)

**Non-blocking (C-4..C-8, G-1, G-2, G-S1, G-S2):**
- `05-03-PLAN.md` — strengthen `test_chart_payload_escapes_script_close` with count assertion + escaped-form assertion (C-4)
- `05-02-PLAN.md` or `05-03-PLAN.md` — add per-surface escape regression tests (C-5)
- `05-CONTEXT.md` D-05 — amend OR `05-03-PLAN.md` — add `__main__` entrypoint task (C-6)
- `05-03-PLAN.md` — add `newline='\n'` to `_atomic_write_html` open() call if Windows matters (C-7)
- `05-01-PLAN.md` — fix `Path` import in CLI snippet (C-8)
- `05-03-PLAN.md` — write CSS comment explaining fixed-height requirement (G-S2)
- `05-01-PLAN.md` Task 5 — broaden `.keys() ==` grep (G-S1)
