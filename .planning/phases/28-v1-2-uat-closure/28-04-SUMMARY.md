---
phase: 28-v1-2-uat-closure
plan: 04
subsystem: testing
tags: [pytest, playwright, uat, backtest, template-leak, visual-smoke]

requires:
  - phase: 28-01
    provides: tests/uat/ package + conftest, uat marker registered, default-exclude addopts
provides:
  - tests/uat/test_uat_23_backtest_visual.py — Phase 23 UAT-2 visual-smoke spec
affects: [28-06]

tech-stack:
  added: []
  patterns:
    - "Per-literal assertions (not membership-style list scan) so each template-leak failure mode produces a single named FAIL message for plan 06 root-cause"
    - "Permissive missing-CSS regression check: inline <style> OR external <link rel=stylesheet> — matches project idiom (no StaticFiles mount)"

key-files:
  created:
    - tests/uat/test_uat_23_backtest_visual.py
  modified: []

key-decisions:
  - "Missing-CSS check accepts inline <style> as well as <link rel=stylesheet> (Rule 1 deviation, see Deviations section). Project does not run a StaticFiles mount and web/routes/backtest.py::_wrap_html ships a bare shell with no <link>; the plan's '/static/' or '/assets/' regex would have produced a permanent FAIL on a correct render."
  - "Each forbidden literal asserted on its own line (4 distinct asserts) instead of a single list-comprehension scan, so VERIFICATION.md FAIL messages name exactly one failure mode."
  - "Spec is GET-only with no clicks/fills/POSTs — verified by grep audit (count == 0 in acceptance criteria)."

patterns-established:
  - "When a planner-suggested asset-pipeline regex assumes a static mount that the codebase doesn't use, adapt the assertion shape to honour the failure mode (asset-pipeline regression / unstyled page) without producing a permanent false FAIL. Document under Deviations Rule 1."

requirements-completed: [DEBT-01]

duration: 6 min
completed: 2026-05-10
---

# Phase 28 Plan 04: /backtest Visual-Smoke Spec Summary

**Persisted Phase 23 UAT-2 (`/backtest` template-leak smoke) as a single `@pytest.mark.uat`-gated Playwright spec — distinct assertions per forbidden literal (`{{`, `}}`, `Undefined`, `None None`) plus a missing-CSS regression check adapted to the project's no-static-mount reality.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-10
- **Completed:** 2026-05-10
- **Tasks:** 1
- **Files created:** 1

## Accomplishments

### Task 1: Phase 23 UAT-2 visual-smoke spec — DONE

`tests/uat/test_uat_23_backtest_visual.py` (83 lines) implements one test:
- `test_backtest_page_has_no_template_leak_artefacts(page, base_url)` — GET `/backtest` on `BASE_URL` (production droplet by default), capture `page.content()`, run five assertions:
  1. `'{{' not in html` — Jinja unrendered open delimiter
  2. `'}}' not in html` — Jinja unrendered close delimiter
  3. `'Undefined' not in html` — jinja2 Undefined str-repr leak
  4. `'None None' not in html` — Python None tuple/format str-repr leak
  5. `INLINE_STYLE_RE.search(html) or EXTERNAL_STYLESHEET_RE.search(html)` — at least one of inline `<style>` or external stylesheet `<link>` present

Each assertion has a clear failure message naming the suspected layer (template render, undefined-strict mode, upstream context dict, `_wrap_html` / asset pipeline) so plan 06 can populate a FAIL-row Evidence cell without re-investigation.

## Verification

All acceptance-criteria checks passed:

```
$ grep -q "pytestmark = pytest.mark.uat" tests/uat/test_uat_23_backtest_visual.py    # OK1
$ grep -q "FORBIDDEN_LITERALS"        tests/uat/test_uat_23_backtest_visual.py        # OK2
$ grep -q "Undefined"                 tests/uat/test_uat_23_backtest_visual.py        # OK3
$ grep -q "None None"                 tests/uat/test_uat_23_backtest_visual.py        # OK4
$ grep -c "page.click\|page.fill\|page.request.post" tests/uat/test_uat_23_backtest_visual.py
0                                                                                     # GET-only

$ .venv/bin/python -m pytest -m uat --collect-only tests/uat/test_uat_23_backtest_visual.py
collected 1 item
  <Function test_backtest_page_has_no_template_leak_artefacts>

$ .venv/bin/python -m pytest --collect-only tests/uat/test_uat_23_backtest_visual.py
collected 1 item / 1 deselected / 0 selected   # default suite excludes uat — baseline preserved
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Plan assumption mismatch] Missing-CSS regex relaxed to inline-or-link**

- **Found during:** Task 1 read-first investigation (`web/routes/backtest.py`, `web/app.py`, project templates).
- **Issue:** The plan-suggested missing-CSS regex `<link[^>]+rel=["\']stylesheet["\'][^>]+href=["\'](?:/static/|/assets/)[^"\']+["\']` assumes the app exposes a `/static/` or `/assets/` prefix. Investigation showed:
  - No FastAPI `StaticFiles` mount anywhere in `web/app.py` or `main.py`.
  - `web/routes/backtest.py::_wrap_html` returns a minimal shell whose `<head>` contains only `<meta charset>` and `<title>` — no `<link>` tag at all (comment: "Production styles inherited from existing dashboard CSS at GET /").
  - `dashboard.html` itself uses inline `<style>` blocks (line 63) rather than `<link rel="stylesheet">`.
  - Net: a `<link rel=stylesheet href=/static/…>` regex would produce a deterministic FAIL on a correct `/backtest` render, drowning real template-leak regressions.
- **Fix:** Replaced the single external-stylesheet regex with two regexes (`INLINE_STYLE_RE` and `EXTERNAL_STYLESHEET_RE`) and assert `has_inline or has_external`. This still catches the intended failure mode — a bare unstyled body would have neither — without producing a permanent false FAIL.
- **Files modified:** `tests/uat/test_uat_23_backtest_visual.py` (the file being created — divergence baked in at write time).
- **Commit:** `dc2e31b` (see Commit Note below).

### Open Questions / Plan-mandated SUMMARY notes

The plan's `<output>` block asked which static-asset prefix is actually used and whether the regex needed narrowing. **Answer:** neither `/static/` nor `/assets/` is in use — the project has no `StaticFiles` mount, and `/backtest` currently emits zero stylesheet `<link>` tags. The regex was *broadened* (not narrowed) to also accept inline `<style>`, per Rule 1 deviation above. Plan 06 should expect the missing-CSS branch of the assertion to fire only on actual asset-pipeline regression, not on the current baseline.

### Auth Gate

`/backtest` is cookie-auth-gated by Phase 16.1 middleware. The spec relies on the conftest's `page` fixture; if the production droplet returns 302/401 for unauthenticated requests, the `assert response.ok` check will surface that as a FAIL with the response status — plan 06 will then either provide a UAT_USER/UAT_PASS-driven cookie via the conftest's existing `uat_credentials()` helper, or capture the auth-gate failure as a separate row. **Assumption baked into this spec:** the `page` fixture lands on `/backtest` with a usable session, or the spec FAILs honestly with the response status. No silent skip.

## Commit Note (worktree race observed)

A concurrent sibling worktree (plan 28-05) staged-and-committed during my `git commit` window. The result: `tests/uat/test_uat_23_backtest_visual.py` is on `main` with file content byte-identical to what plan 04 wrote (verified via `diff <(git show dc2e31b:tests/uat/test_uat_23_backtest_visual.py) tests/uat/test_uat_23_backtest_visual.py` → MATCH), but the carrying commit is `dc2e31b "test(28-05): add UAT-26-2..6 multi-tab market-scoping specs"` rather than a `test(28-04)` commit. Provenance for code review: the file diff in `dc2e31b` includes `tests/uat/test_uat_23_backtest_visual.py` alongside plan 28-05's `tests/uat/test_uat_26_multitab.py`. This is a known global learning re: parallel-worktree merges; flagging here because the SUMMARY's commit-hash references would otherwise look wrong.

## Threat Flags

None. The spec is GET-only against the production droplet — no new attack surface, no new endpoints, no new auth paths. Threat register T-28-09 (tampering via spec) is mitigated by the GET-only audit (`grep -c "page.click|page.fill|page.request.post" → 0`). T-28-10 (info disclosure via assertion messages) is accepted per the plan's threat model (template-leak tokens are public-page artefacts, not secrets).

## Self-Check: PASSED

- [x] `tests/uat/test_uat_23_backtest_visual.py` exists on disk
- [x] Commit `dc2e31b` carries the file with identical content (byte-diff clean)
- [x] `pytest -m uat --collect-only` collects exactly 1 test
- [x] Default `pytest --collect-only` deselects the spec (baseline runtime preserved)
- [x] `grep -c "page.click|page.fill|page.request.post" → 0` (GET-only)
- [x] All four forbidden literals + missing-CSS check present
