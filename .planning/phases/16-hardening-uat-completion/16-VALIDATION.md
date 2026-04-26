---
phase: 16
slug: hardening-uat-completion
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-26
---

# Phase 16 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Source: 16-RESEARCH.md `## Validation Architecture`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.3 |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `.venv/bin/pytest tests/test_integration_f1.py -x -q` |
| **Full suite command** | `.venv/bin/pytest tests/ -x -q` |
| **Estimated runtime** | ~5s (F1 only), ~120s (full suite, ~1170 tests after Phase 16) |

---

## Sampling Rate

- **After every task commit:** Run quick command (above)
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green (0 failures)
- **Max feedback latency:** 5 seconds (quick), 120 seconds (full)

---

## Per-Requirement Verification Map

| REQ / SC | Behavior | Test Type | Automated Command | File Exists | Status |
|----------|----------|-----------|-------------------|-------------|--------|
| CHORE-01 SC-1 | Full chain fetch→email with section + key-value assertions via shared `_assert_f1_outputs` helper; mocking only at `requests.get`-equivalent (`data_fetcher.yf.Ticker` per REVIEWS M-3) + `_post_to_resend`; asserts on `last_email.html`, `dashboard.html` (REVIEWS H-1: `class="calc-row"` + `sentinel-banner`), state.json transition + W3 invariant (REVIEWS M-4), trade_log growth (REVIEWS L-3). Both instruments active; seed `notifier/sample_state_with_change.json` | integration | `.venv/bin/pytest tests/test_integration_f1.py::test_full_chain_fetch_to_email -x -q` | ❌ W0 | ⬜ pending |
| CHORE-01 SC-2 | Meta-test calls SAME `_assert_f1_outputs` helper under `pytest.raises(AssertionError)` with `patch.object(signal_engine, 'get_signal', side_effect=_inverted_signal)` returning LONG instead of canonical FLAT (REVIEWS H-2 — valid-but-INVERTED, not coerced 999). Sanity-check run without patch must pass via SAME helper | integration | `.venv/bin/pytest tests/test_integration_f1.py::test_f1_catches_planted_regression -x -q` | ❌ W0 | ⬜ pending |
| CHORE-03 SC-3a | UAT-16-A: mobile dashboard loads on hosted URL — operator verification | manual | `grep -E 'UAT-16-A.*verified' .planning/phases/16-hardening-uat-completion/16-HUMAN-UAT.md` returns 1 | ❌ W0 | ⬜ pending (operator) |
| CHORE-03 SC-3b | UAT-16-B: email renders in real Gmail on mobile — operator verification | manual | `grep -E 'UAT-16-B.*verified' .planning/phases/16-hardening-uat-completion/16-HUMAN-UAT.md` returns 1 | ❌ W0 | ⬜ pending (operator) |
| CHORE-03 SC-3c | UAT-16-C: drift banner in real weekday email — operator verification (may take >1 weekday per D-17) | manual | `grep -E 'UAT-16-C.*verified' .planning/phases/16-hardening-uat-completion/16-HUMAN-UAT.md` returns 1 | ❌ W0 | ⬜ pending (operator, weekday-gated) |
| SC-4 | STATE.md `## Completed Items` exists with 3 migrated items + REAL operator dates (REVIEWS H-3: NO `pending` or `—` placeholders; rows populated from 16-HUMAN-UAT.md AFTER Plan 16-05 closes operator UAT — Wave 3) | manual | `grep -c "^## Completed Items" .planning/STATE.md` returns 1 AND `awk '/^## Completed Items$/,/^## Deferred Items$/' .planning/STATE.md \| grep -c "\| pending \|"` returns 0 (REVIEWS H-3) AND `awk '/^## Completed Items$/,/^## Deferred Items$/' .planning/STATE.md \| grep -cE "[0-9]{4}-[0-9]{2}-[0-9]{2}"` returns ≥ 3 | ❌ W0 | ⬜ pending |
| Deploy task | Phase 13+14+15 stack reaches droplet via direct push + `bash deploy.sh`; `systemctl is-active trading-signals-web` returns `active`; smoke-check curl returns ≥ 1 calc-row | manual + integration | `ssh trader@<droplet> 'cd ~/trading-signals && git log --oneline -1'` shows latest Phase 15 commit (e.g., `13becd6`) | ❌ W0 | ⬜ pending (operator-driven) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky · 👤 operator-pending*

---

## Wave 0 Requirements

- [ ] `tests/test_integration_f1.py` — new file with 2 test functions covering CHORE-01 SC-1 + SC-2
- [ ] `.planning/phases/16-hardening-uat-completion/16-HUMAN-UAT.md` — new file; per-scenario schema with status / verification date / operator notes (D-09, D-10)
- [ ] STATE.md `## Completed Items` section — new section above existing `## Deferred Items`; populated by SC-4 plan task once operator marks UAT scenarios verified

No framework gaps — pytest, pytest-freezer, mock, and all project dependencies are already installed (see `requirements.txt` pins).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Mobile dashboard renders correctly on hosted URL | CHORE-03 SC-3a | Browser visual check; viewport-specific layout cannot be asserted in pytest | Open `https://signals.<domain>` on phone (any modern mobile browser); set X-Trading-Signals-Auth header; verify signal cards stack on narrow viewport, equity chart fits, calc-rows wrap legibly. Record observation in 16-HUMAN-UAT.md §UAT-16-A. |
| Mobile Gmail email renders correctly | CHORE-03 SC-3b | Gmail's CSS-stripping behavior cannot be tested in pytest | Trigger a daily run on the droplet (via real schedule or `python main.py --once --force-email` if available); inspect the resulting email in Gmail mobile app on phone; verify section headings render, banners show borders, P&L colors apply. Record in 16-HUMAN-UAT.md §UAT-16-B. |
| Drift banner in real weekday email | CHORE-03 SC-3c | Requires real production conditions (weekday + drift state); may take multiple weekdays of natural occurrence (D-17) | Wait for organic drift to occur in a real weekday run, OR manually inject a drifted state via `web/routes/trades` mutation BEFORE 08:00 AWST. Confirm the resulting email's drift banner renders with red/amber border and the subject carries `[!]` prefix. Record in 16-HUMAN-UAT.md §UAT-16-C. |
| Droplet smoke-check after deploy | Deploy task acceptance | Network-dependent; operator must SSH | After `git pull && bash deploy.sh` on droplet, run `systemctl is-active trading-signals-web` (expect `active`) and `curl -s -H "X-Trading-Signals-Auth: $WEB_AUTH_SECRET" http://127.0.0.1:8000/ \| grep -c "calc-row"` (expect ≥ 1). |

---

## Validation Sign-Off

- [ ] `tests/test_integration_f1.py` created with both test functions implemented (no `pytest.skip` bodies)
- [ ] CHORE-01 SC-1 + SC-2 tests pass in CI
- [ ] `16-HUMAN-UAT.md` created with all 3 scenarios; status fields default to `pending`
- [ ] Deploy task completed; droplet smoke-check returns calc-row markup
- [ ] STATE.md `## Completed Items` section added; 3 migrated items with verification dates
- [ ] All operator UAT scenarios marked `verified` with date in 16-HUMAN-UAT.md (SC-3c may stay `pending (weekday-gated)` per D-17)
- [ ] Sampling continuity: per-task verify command covers `tests/test_integration_f1.py`
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s (F1 quick), < 120s (full)
- [ ] `nyquist_compliant: true` set in frontmatter once Wave 0 stubs land
- [ ] `wave_0_complete: true` once all Wave 0 stubs are committed

**Approval:** pending
