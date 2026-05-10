# Phase 27 — Tech debt registered during execution

## D-12-1: notifier.py kept on disk as fossil (Task B grep found usages)

**Status:** outstanding
**Owner:** future plan (proposed: 27-15 or post-v1.2 cleanup)
**Severity:** low — no runtime effect; static-analysis tests pass

### Background

Plan 27-12 split the 2195 LOC `notifier.py` into a `notifier/` package
(9 files, every file <500 LOC). At Task B's deletion gate, `grep -rn
'notifier.py'` across `tests/*.py` found **10 test files** that perform
source-text introspection on `notifier.py` via `pathlib.Path('notifier.py')
.read_text()` or string-literal references in scan-list constants.

Per Plan 27-12 Task B explicit instruction:
> "If grep finds usages → KEEP notifier.py as shim. Document in 27-DEBT.md
> with rationale + plan to clean up later."

The fossil is therefore retained.

### Why deletion was deferred (not done in this plan)

Deleting `notifier.py` would require updating 10 source-text-introspection
tests to walk `notifier/*.py` (concatenated or per-file) instead of the
single legacy file. Each test asserts a different invariant on the source:

| File | Invariant tested |
|---|---|
| tests/test_signal_engine.py | AST hex-boundary blocklist (`test_notifier_no_forbidden_imports`) |
| tests/test_html_xss_audit.py | `html.escape(` call count >= 69 baseline; quote=True kwarg AST gate |
| tests/test_http_timeouts.py | `_RESEND_TIMEOUT_S` absent + `(5, HTTP_TIMEOUT_S)` present |
| tests/test_signals_email_to_required.py | `_EMAIL_TO_FALLBACK` absent + no operator-shaped emails |
| tests/test_setup_https_doc.py | `SIGNALS_EMAIL_FROM` env-var read present |
| tests/test_secret_redaction.py | Source contains redact-secret call sites |
| tests/test_instrument_regex.py | Instrument regex tightening scan list |
| tests/test_entry_side_cost.py | Entry-side cost helper scan list |
| tests/test_notifier.py | `ruff check notifier.py` returns 0 (CHORE-02) |
| tests/test_crash_email_fallback.py | String-literal `"notifier.py"` in test fixture (NOT a file ref — false positive) |

The volume of test-side changes was deemed out of scope for Plan 27-12
(focus: package split with API parity); migrating them is its own
follow-up plan.

### Runtime impact: zero

Python's package-vs-module import resolution prefers the directory
package over the top-level `.py` file when both exist:

```
$ .venv/bin/python -c "import notifier; print(notifier.__file__)"
/Users/.../trading-signals/notifier/__init__.py
```

The fossil `notifier.py` is **never executed** as part of any import.
All runtime behaviour is driven by `notifier/`. `Path('notifier.py')
.read_text()` only matters to source-introspection tests, which read the
fossil text — for now identical to the pre-split content.

### Drift risk

The fossil content is frozen at the pre-split state (post Plan 27-11).
Bug fixes after this plan land in `notifier/<module>.py`, NOT in
`notifier.py`. Source-text tests will continue to assert against the
fossil and **MAY produce false positives/negatives** if a future patch
adds a forbidden import to the package or changes an asserted invariant.

Mitigation until cleanup:
- Reviewers must mentally double-apply any source-text rule to
  `notifier/*.py` AND `notifier.py` until fossil is removed.
- New source-text tests added in subsequent plans should target
  `notifier/<module>.py` directly, not `notifier.py`.

### Cleanup plan (proposed: 27-15)

1. Add a small helper `tests/_notifier_source.py` that concatenates
   `notifier/*.py` into one string for source-text assertions.
2. Migrate each of the 10 tests above to consume that helper instead of
   `Path('notifier.py').read_text()`.
3. Replace the 2195 LOC fossil `notifier.py` with a 5-line shim:
   ```python
   '''Compatibility stub — package lives in `notifier/`. This file
   exists only so legacy `Path('notifier.py').read_text()` references
   survive until those tests are migrated. See .planning/.../27-DEBT.md.'''
   raise ImportError('notifier.py is shadowed by the notifier/ package')
   ```
4. After all tests pass and CI is green for >=1 deploy cycle, delete the
   shim entirely.

### Decision rationale

> **Most eloquent:** convert `notifier.py` to a thin shim AND update the
> 10 affected tests in this plan — produces a clean final state with
> zero duplication. Less eloquent but pragmatic-by-plan choice
> (selected): keep the fossil per Plan 27-12 Task B's explicit
> "if grep finds usages, document and defer" gate, on the principle
> that the plan's authors deliberately scoped test migration out of
> 27-12. Deferred work is tracked here; functional split is shipped.
