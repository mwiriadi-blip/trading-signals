---
phase: 6
reviewers: [gemini, codex]
skipped: [claude, coderabbit, opencode, qwen, cursor]
skipped_reason:
  claude: "running inside Claude Code — skipped for independence"
  coderabbit: "not installed"
  opencode: "not installed"
  qwen: "not installed"
  cursor: "not installed"
reviewed_at: 2026-04-22
plans_reviewed:
  - .planning/phases/06-email-notification/06-01-PLAN.md
  - .planning/phases/06-email-notification/06-02-PLAN.md
  - .planning/phases/06-email-notification/06-03-PLAN.md
---

# Cross-AI Plan Review — Phase 6 (Email Notification)

Two independent AI systems reviewed the 3-plan Phase 6 set. One shared HIGH-severity finding (API-key echo in error body), one shared MEDIUM-severity finding (scalar `timeout=30` vs tuple `timeout=(5, 30)`), plus complementary coverage.

---

## Gemini Review

**Risk Assessment: LOW**

### Summary
Exceptionally high quality. Deep understanding of hexagonal-lite architecture and strict engineering standards. Isolation of the email hex, preservation of the `--test` read-only invariant, and handling of Resend API nuances (specifically the 429 retryable status) is technically sound. The 4-tuple refactor for `run_daily_check` is the correct path for maintaining state purity during `--test` runs.

### Strengths
- **429 Special-Case Correctness** — plan correctly identifies 429 as retryable 4xx despite the literal "fail-fast on 4xx" rule.
- **CLI-01 Invariant Protection** — wiring in main.py Wave 2 and integration tests explicitly protect `state.json` mtime under `--test`.
- **Hex-Lite Boundary Enforcement** — proactive AST blocklist extension in Wave 0 prevents accidental coupling before the first line of logic.
- **C-2 Never-Crash Pattern** — verbatim mirror of the Phase 5 dashboard import-inside-try pattern ensures even syntax errors in notifier.py won't kill state persistence.
- **Palette Retrofit Strategy** — moving colors to `system_params.py` with byte-identical regression test for Phase 5 goldens is safe.

### Concerns

- **MEDIUM — `_EMAIL_TO_FALLBACK` commits a real email address to source** (file: `notifier.py`). Creates a permanent GitHub footprint even if acceptable for a single-operator tool.
- **LOW — `→` Glyphs vs Entities** (tasks `06-02-03`, `06-02-04`). Plan mentions raw Unicode `→` (U+2192) but some code excerpts use `&rarr;`.
- **LOW — `run_daily_check` Type Hint Complexity** (task `06-03-02`). 4-tuple of `Optional` types means internal unpacking must be airtight to avoid `TypeError` in all callers.

### Suggestions

- **Consistently use raw Unicode** `→` (U+2192) and `—` (U+2014) in f-strings; remove all `&rarr;` references.
- **Refined 4-tuple unpacking** in main.py — explicit None-checks before dispatching to email:
  ```python
  rc, state, old_signals, run_date = run_daily_check(args)
  if rc == 0 and all(x is not None for x in (state, old_signals, run_date)):
    _send_email_never_crash(state, old_signals, run_date, is_test=args.test)
  ```
- **Timeout Robustness** — use `timeout=(5, 30)` tuple (5s connect, 30s read) instead of scalar `timeout=30`. Prevents hung DNS/TCP handshake from consuming the full 30s read budget.

---

## Codex Review

**Risk Assessment: MEDIUM**

### Per-Plan Review

#### 06-01 — Wave 0 Scaffold (Risk: LOW)

**Strengths:**
- Locks palette move BEFORE notifier implementation (minimizes Phase 5 regression risk at [dashboard.py:103](dashboard.py:103)).
- Symmetric notifier AST fence complements existing dashboard guard in [tests/test_signal_engine.py:837](tests/test_signal_engine.py:837).
- Reuses existing patterns (dashboard regenerator, golden tests, atomic write).
- Handles `.env.example` and `last_email.html` in Wave 0 (avoids late-stage ops gaps).
- Explicitly preserves Phase 5 dashboard byte stability.

**Concerns:**
- **MEDIUM — `06-01-03` "failing placeholder" wording conflict.** Placeholder strategy mostly passes via `pytest.raises` or `xfail`, not outright failure. Terminology will confuse execution/review.
- **LOW — `06-01-01` early import-time coupling.** notifier stub imports `load_state` at module top even though the AST guard only cares about forbidden imports.
- **LOW — `06-01-03` placeholder goldens committed before byte-equal assertion exists.** Safe only because golden tests stay xfail until Wave 2.

**Suggestions:**
- Replace "failing placeholder" with "placeholder test that passes structurally until Wave 1/2 fills behavior".
- Keep `load_state` out of module import block; import inside `if __name__ == '__main__':` only.
- Add one explicit Wave 0 assertion that `dashboard.py` no longer defines `_COLOR_*` locally after retrofit.

---

#### 06-02 — Wave 1 Render + Format (Risk: MEDIUM)

**Strengths:**
- Correctly isolates Wave 1 to pure render/format; dispatch deferred to Wave 2.
- Covers first-run/no-baseline rule from D-06 (easy to get wrong given legacy int shape in [state_manager.py:279](state_manager.py:279)).
- Good HTML-shell coverage: no `<style>`, no `@media`, viewport meta, `role="presentation"`, inline palette.
- Includes XSS tests on riskiest state-derived fields.

**Concerns:**
- **HIGH — `06-02-03` missing exact-value assertions for Trail Stop and Unrealised P&L.** Formulas must match current live logic around [main.py:560](main.py:560) and contract specs. Without exact-value tests, a sign error or cost-split error can ship silently.
- **MEDIUM — `06-02-03` `_closed_position_for_instrument_on` only checks `trade_log[-1]`.** Regresses from the wider-scan fallback recommended in research/UI-spec. If both instruments close on the same run, ACTION REQUIRED copy can miss one instrument.
- **MEDIUM — `06-02-03` `&rarr;` vs `→` glyph inconsistency in sample implementation.** Plan/tests require `→`; sample uses `&rarr;`.
- **MEDIUM — `06-02-03` `_render_header_email` sample is thinner than locked UI contract.** Omits subtitle and signal-as-of presentation. Literal execution will under-implement Section 1.
- **LOW — `06-02-02` `_fmt_percent_unsigned_email` described as "for ADX / RVol display"** but Wave 1 only renders ADX and Mom. Minor docstring mud.

**Suggestions:**
- Add exact-value assertions in `06-02-03`:
  - One LONG position row with expected trail stop.
  - One SHORT position row with expected trail stop.
  - One unrealised P&L assertion including the opening-half-cost deduction.
- Change `_closed_position_for_instrument_on` to scan at least the last 3 records, not just `trade_log[-1]`.
- Standardize on literal `→` glyph everywhere; remove `&rarr;` from sample implementation.
- Add tests for header containing `SPI 200 & AUD/USD mechanical system` and `Signal as of ...`.
- Add test that signal table renders Mom values in `mom1 · mom3 · mom12` order.

---

#### 06-03 — Wave 2 PHASE GATE (Risk: MEDIUM)

**Strengths:**
- Correctly replaces Phase 4 stub at [main.py:657](main.py:657) and branch at [main.py:723](main.py:723).
- Correctly targets the seam for tuple-return refactor at [main.py:351](main.py:351).
- Preserves `--test` structural read-only via the save guard at [main.py:600](main.py:600).
- Mirrors existing never-crash dashboard pattern at [main.py:94](main.py:94).
- Uses existing dashboard atomic-write pattern at [dashboard.py:987](dashboard.py:987).
- Golden regeneration + double-run idempotency is the right final gate.

**Concerns:**
- **HIGH — `06-03-01` security test contradicts implementation sketch.** The test `test_api_key_NOT_in_error_body` passes, but `_post_to_resend` still raises `ResendError(f'4xx from Resend: {resp.status_code} {resp.text[:200]}')`. If `resp.text` echoes the key (e.g., Resend's 401 error body quotes the provided auth), the key leaks into the exception string. The test is correct; the implementation sketch is wrong.
- **MEDIUM — `06-03-01` scalar `timeout=timeout_s`.** Leaves connect timeout weaker than necessary; can hang on network setup failures. (Matches Gemini's finding.)
- **MEDIUM — `06-03-02` 4-tuple refactor missing explicit enumeration of all return sites.** Current function has at least the `--test` early-return near [main.py:606](main.py:606) and the final success return near [main.py:620](main.py:620). Missing even one would silently break `main()`.
- **LOW — `06-03-03` golden phase gate locks body bytes only.** Subject rendering is outside golden coverage despite being part of ROADMAP SC-1.
- **LOW — `06-03-02` `--test` alone sending email is a behavior change from current dispatch-ladder docstring at [main.py:691](main.py:691).** Plan updates code/tests but should explicitly require docstring update.

**Suggestions:**
- **Fix `06-03-01` API-key-echo:**
  ```python
  safe_body = resp.text[:200].replace(api_key, '[REDACTED]')
  raise ResendError(f'4xx from Resend: {resp.status_code} {safe_body}')
  ```
- Change timeout to `timeout=(5, timeout_s)` (matches Gemini).
- In `06-03-02`, enumerate exact return sites to update in `run_daily_check`:
  - `--test` early return near [main.py:600](main.py:600)
  - Final success return near [main.py:620](main.py:620)
- Add direct test that `run_date.tzinfo is not None` in the 4-tuple return test.
- Add one frozen-subject snapshot (per fixture scenario) alongside body goldens.

---

### Codex Overall

**Summary:** High quality overall. Main gaps are 06-02's financial-display test precision and 06-03's mismatch between the "no API key leak" test and the proposed error-body handling.

**Cross-plan concerns:**
- **HIGH** API-key truncation hygiene not actually solved in `06-03-01` as written.
- **MEDIUM** Open-position financial math under-specified in `06-02-03`.
- **MEDIUM** ACTION REQUIRED close-copy lookup regresses from "scan recent trades" to "tail only" in Wave 1 draft.
- **LOW** Wording inconsistencies around placeholder tests and behavior-change docs.

**Recommendation:** Do not start Wave 2 until the `resp.text[:200]` sanitization issue is corrected and Wave 1 adds exact financial render assertions.

---

## Consensus Summary

### Agreed Strengths (both reviewers)
- Correct handling of Resend 429 as retryable despite being 4xx.
- Correct CLI-01 read-only contract preservation (state.json mtime unchanged under `--test`).
- Correct import-inside-try C-2 pattern for `_send_email_never_crash` (both runtime AND import-time isolation).
- Correct tuple-return refactor target at `run_daily_check` (vs module-level global).
- Palette retrofit with Phase 5 byte-identical regression guard is safe.
- Golden snapshot discipline + double-run idempotency is the right final gate.

### Agreed Concerns (both reviewers flagged)

1. **MEDIUM — Scalar `timeout=30` instead of tuple `timeout=(5, 30)`.**
   - **Affected plan:** 06-03 Task 1 (`_post_to_resend`)
   - **Fix:** change `timeout=timeout_s` → `timeout=(5, timeout_s)` in the `requests.post` call.
   - **Why:** separates connect-phase from read-phase timeout; prevents a hung DNS/TCP handshake from consuming the full 30s read budget.

2. **LOW — `&rarr;` vs raw `→` glyph inconsistency.**
   - **Affected plan:** 06-02 Task 3 (sample `_render_action_required_email`)
   - **Fix:** standardize on literal `→` (U+2192) everywhere; remove `&rarr;` from sample implementation and any test assertions.

### Divergent Views (single-reviewer findings worth reviewing)

| Finding | Reviewer | Severity | Why it matters |
|---|---|---|---|
| **API-key echo in `ResendError`** via `resp.text[:200]` | Codex only | **HIGH** | Real security regression — the Phase 6 threat model (T-06-02) claims the test prevents leak, but the implementation doesn't sanitize. Must fix before Wave 2. |
| **Missing exact-value assertions for Trail Stop + Unrealised P&L** | Codex only | **HIGH** | A sign error or cost-split error in the email renderer can ship silently. UI-SPEC specifies the formulas; tests should pin them. |
| **`_closed_position_for_instrument_on` only checks `trade_log[-1]`** | Codex only | MEDIUM | If both instruments close on the same run, ACTION REQUIRED copy misses one. Widen to scan last ≥3 records. |
| **`_render_header_email` sample under-implements UI-SPEC** (missing subtitle + signal-as-of) | Codex only | MEDIUM | Literal execution of sample code will under-build Section 1. Plan should either pin exact assertions or remove the sketch. |
| **Golden phase gate locks body bytes only — no subject lock** | Codex only | LOW | ROADMAP SC-1 includes subject format; add one frozen-subject assertion per fixture. |
| **`_EMAIL_TO_FALLBACK` commits a real email address** | Gemini only | MEDIUM | Permanent GitHub footprint. Replace with `RECIPIENT_NOT_SET@example.invalid` sentinel that raises unless `SIGNALS_EMAIL_TO` is set (or accept the footprint knowingly). |
| **4-tuple None-guard at email dispatch** | Gemini only | LOW | Add `all(x is not None for x in (state, old_signals, run_date))` gate in main.py before calling `_send_email_never_crash`. |
| **"Failing placeholder" wording vs xfail reality** | Codex only | MEDIUM | Swap wording in 06-01 task descriptions to avoid execution/review confusion. |
| **Enumerate all `run_daily_check` return sites for tuple refactor** | Codex only | MEDIUM | At least 2 return sites need simultaneous update; missing one silently breaks `main()`. |
| **Behavior-change docstring update for `--test` email** | Codex only | LOW | Current dispatch-ladder docstring at main.py:691 says `--test` doesn't email. Add explicit docstring-update task. |

---

## Recommended Replan Fixes (for `/gsd-plan-phase 6 --reviews`)

Highest-impact fixes to bake into the plans before Wave 2 starts:

1. **06-03 Task 1 — API-key redaction.** Rewrite the `_post_to_resend` 4xx-fail-fast block to sanitize `resp.text[:200]`:
   ```python
   safe_body = resp.text[:200].replace(api_key, '[REDACTED]') if api_key else resp.text[:200]
   raise ResendError(f'4xx from Resend: {resp.status_code} {safe_body}')
   ```
2. **06-03 Task 1 — timeout tuple.** Change `timeout=timeout_s` → `timeout=(5, timeout_s)`.
3. **06-02 Task 3 — exact-value Trail Stop + Unrealised P&L assertions.** Add at minimum:
   - LONG fixture: trail stop = `max(entry - trail_atr_mult * atr_at_entry, ...)` expected value.
   - SHORT fixture: trail stop equivalent SHORT-side formula.
   - Unrealised P&L: includes opening-half-cost deduction per D-13.
4. **06-02 Task 3 — widen `_closed_position_for_instrument_on`** to scan last ≥3 `trade_log` records (not just `[-1]`).
5. **06-02 Task 3 — standardize `→` glyph; remove all `&rarr;`.**
6. **06-02 Task 3 — header section assertions** covering `SPI 200 & AUD/USD mechanical system` + `Signal as of ...`.
7. **06-03 Task 2 — enumerate `run_daily_check` return sites** (line 600 `--test` early-return, line 620 final success) in the task action; add docstring-update sub-step for line 691.
8. **06-03 Task 3 — subject golden lock.** Add one frozen-subject assertion per fixture scenario alongside the body goldens.
9. **06-01 Task 3 — swap "failing placeholder" wording** to "placeholder test that passes structurally until Wave 1/2".
10. **06-03 Task 2 — add None-guard** in `main.py` email dispatch before calling `_send_email_never_crash`.

---

## Unresolved Decisions for Operator

- **`_EMAIL_TO_FALLBACK` footprint.** Gemini flagged MEDIUM; CONTEXT D-14 explicitly accepted this. Options:
  - (A) Keep the real address (current plan) — accept GitHub footprint.
  - (B) Use `RECIPIENT_NOT_SET@example.invalid` and raise if `SIGNALS_EMAIL_TO` not set — safer but breaks the "graceful-degradation" posture on missing env.
  - (C) Ship as-is, file a plant-seed note for v2 to revisit.

---

## Next Steps

- **Option 1 — Replan incorporating feedback:** `/gsd-plan-phase 6 --reviews` (recommended given the HIGH findings).
- **Option 2 — Proceed as-planned:** accept the HIGH findings as known debt and start `/gsd-execute-phase 6`. Not recommended — the API-key-echo fix and the P&L exact-value tests are cheap to add pre-execution.
- **Option 3 — Manual spot fixes:** manually edit `06-03-PLAN.md` + `06-02-PLAN.md` to address the two HIGH findings, skip the rest, then execute.
