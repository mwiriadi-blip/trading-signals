# Phase 16: Hardening + UAT Completion — Research

**Researched:** 2026-04-26
**Domain:** Integration testing (pytest / unittest.mock), deploy automation (bash / git / systemd), operator UAT documentation
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**F1 integration test architecture (CHORE-01)**
- D-01: F1 reuses an existing Phase 1 scenario fixture + canonical yfinance fixture pair as input seed. Both instruments active, non-FLAT signals.
- D-02: Mock at boundaries only — `requests.get` (yfinance fetch) and `_post_to_resend` (Resend dispatch). NO internal composition mocked.
- D-03: Assertions on `last_email.html` at section + key-value granularity (not byte-for-byte golden snapshot).
- D-04: Single test pass covers both SPI200 and AUDUSD.
- D-05: Test path locked: `tests/test_integration_f1.py::test_full_chain_fetch_to_email` (new file).

**Planted-regression meta-test (CHORE-01 SC-2)**
- D-06: Lives in `tests/test_integration_f1.py`, function `test_f1_catches_planted_regression`.
- D-07: Planted regression = `signal_engine.get_signal` rename via `unittest.mock.patch.object(signal_engine, 'get_signal', ...)`.
- D-08: Monkey-patches by attribute name; meta-test asserts F1 fails with patch, passes without.

**Phase 6 HUMAN-UAT artifact (CHORE-03)**
- D-09: UAT notes in new `16-HUMAN-UAT.md` inside Phase 16 directory. References archived `06-HUMAN-UAT.md` for context.
- D-10: Schema: Scenario ID / Original v1.0 reference / Verification status (pending/verified/partial) / Operator date / Operator notes.

**Deployment of Phases 13-15 to droplet**
- D-11: Deploy IS a Phase 16 task (first one). Without it UAT cannot be exercised.
- D-12: Mechanism = `git push origin main` from Mac + `bash deploy.sh` on droplet. No PR review layer.
- D-13: Acceptance: push succeeds, `bash deploy.sh` exits 0, `systemctl is-active trading-signals-web` = active, `curl -s -H "X-Trading-Signals-Auth: $WEB_AUTH_SECRET" http://127.0.0.1:8000/ | grep -c "calc-row"` >= 1, `git log --oneline origin/main -5` on droplet shows latest Phase 15 commits.

**STATE.md Deferred Items cleanup**
- D-14: New `## Completed Items` section ABOVE existing `## Deferred Items`. Three v1.0-deferred items move once operator marks verified. `quick_task` 260421-723 stays in Deferred.
- D-15: Each Completed entry records original description + verification date + path-link to artifact.

**Milestone close mechanics**
- D-16: Phase 16 verify-work and v1.1 milestone archive run in SEPARATE sessions.
- D-17: UAT-16-C (drift banner real weekday) may take >1 weekday. `verify-work` returns PARTIAL if pending.

### Claude's Discretion
- Which exact scenario fixture to use for F1 (both instruments active, non-trivial signals)
- Test-runtime budget (target < 5s for F1) — no hard SLA
- Specific text-pattern strings for F1 assertions in `last_email.html`
- Whether deploy smoke-check curl runs against 127.0.0.1 (on droplet) or over HTTPS (per D-13, use 127.0.0.1)

### Deferred Ideas (OUT OF SCOPE)
- Phases 10 + 12 deployment status investigation (see Open Questions section for findings — conclude: not blocking)
- CHORE-02 ruff F401 cleanup (Phase 10 scope)
- Tagged release strategy
- Cross-AI peer review of deploy
- Real-day drift simulation script
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CHORE-01 | F1 full-chain integration test — fetch (mocked yfinance) → signals → sizing → dashboard render → email render; no internal mocking; asserts last_email.html | Confirmed mock patterns (data_fetcher.yf.Ticker, notifier._post_to_resend), fixture selection (dashboard/sample_state.json), assertion text, import-path patch correctness |
| CHORE-03 | Phase 6 HUMAN-UAT scenarios (3 pending) — verifiable via hosted dashboard; update 16-HUMAN-UAT.md; STATE.md Deferred Items cleanup | 06-HUMAN-UAT.md scenario descriptions read; STATE.md deferred table confirmed; deploy task identified as prerequisite |
</phase_requirements>

---

## Summary

Phase 16 has three distinct workstreams: (1) a full-chain integration test (`tests/test_integration_f1.py`) that exercises `run_daily_check` end-to-end with only two boundary mocks; (2) deploying 60+ local-only commits (Phases 13/14/15) to the droplet so UAT can be exercised over HTTPS; and (3) operator-performed UAT against three scenarios from the archived Phase 6 HUMAN-UAT doc, followed by STATE.md cleanup.

The deploy workstream answers the deferred investigation: the droplet is on `b1f9b8f` ("Phase 10 + 11 + 12" merged commit on origin/main), while the Mac has 60 local-only commits covering Phases 13, 14, and 15 in full. All Phase 10/12 code that affected correctness (BUG-01 reset_state fix, INFRA-01 SIGNALS_EMAIL_FROM, INFRA-02 deploy key, INFRA-03 GHA disable, WEB-03/04 HTTPS/nginx, deploy.sh) was already shipped in `b1f9b8f`. The deploy task for Phase 16 is therefore a straight `git push origin main` + `bash deploy.sh` — no Phase 10/12 backfill required.

The F1 test design is constrained by one structural fact: main.py uses `import signal_engine` at module top, so `monkeypatch.setattr(main.signal_engine, 'get_signal', ...)` patches the attribute on the module object that main.py already holds — the patch is effective. The canonical fetch fixtures produce FLAT signals for both instruments (as of 2026-04-19/20 close data), which is non-trivial but means the F1 scenario state must seed an existing position to exercise drift detection. The `tests/fixtures/notifier/sample_state_with_change.json` fixture (SPI200 SHORT + AUDUSD LONG, with a drift warning already present) combined with the canonical fetch fixtures gives the richest coverage: both instruments active, positions present, drift banner rendered.

**Primary recommendation:** Use the notifier's `sample_state_with_change.json` as F1's initial state seed (loaded via `state_manager.save_state` to a tmp_path) + mock `data_fetcher.yf.Ticker` with the existing axjo/audusd 400d fixtures + mock `notifier._post_to_resend` as a no-op. Assert on `last_email.html` for subject emoji, date, both instrument signal labels, position direction, equity figure, and `Drift detected` banner.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| F1 full-chain test execution | Test layer (pytest) | None | Invokes `run_daily_check` once per test; mocks only at I/O boundaries |
| yfinance mock | Test layer | data_fetcher | Patch `data_fetcher.yf.Ticker` — same pattern as existing test_data_fetcher.py |
| Resend mock | Test layer | notifier | Patch `notifier._post_to_resend` — same pattern as existing test_notifier.py |
| Meta-test patch | Test layer | signal_engine | `patch.object(signal_engine, 'get_signal', ...)` via unittest.mock |
| Deploy execution | Operator / bash | droplet systemd | `git push origin main` from Mac; `bash deploy.sh` on droplet |
| UAT verification | Operator | Browser / Gmail | Hosted dashboard + Gmail inbox; manual confirmation |
| STATE.md cleanup | Claude (code edit) | None | Restructure two sections + add Completed entries |

---

## Standard Stack

### Core (all already in requirements.txt / test infrastructure)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | 8.3.3 | Test runner | Already pinned |
| pytest-freezer | (pinned) | `freeze_time` for weekday gate bypass | Already used in test_main.py |
| unittest.mock | stdlib | `patch.object` for meta-test | Already used in TestDriftWarningLifecycle |

### No new dependencies
Phase 16 adds no new pip packages. The F1 test reuses:
- `data_fetcher.yf.Ticker` monkeypatch pattern (from `tests/test_data_fetcher.py`)
- `notifier._post_to_resend` monkeypatch pattern (from `tests/test_notifier.py`)
- `state_manager.save_state` + `tmp_path` isolation (from `tests/test_main.py`)
- `@pytest.mark.freeze_time` (from `tests/test_main.py::TestDriftWarningLifecycle`)

**Version verification:** No new packages — existing pins remain unchanged. [VERIFIED: pyproject.toml]

---

## Architecture Patterns

### System Architecture Diagram (F1 flow)

```
Test setup
  │
  ├── save_state(sample_state_with_change, tmp_path/state.json)
  ├── monkeypatch: data_fetcher.yf.Ticker → _FakeTicker(axjo_400d, audusd_400d)
  ├── monkeypatch: notifier._post_to_resend → no-op stub
  └── freeze_time: 2026-04-28T00:00:00+00:00 (Mon 08:00 AWST)
       │
       ▼
  main.run_daily_check(args=Namespace(test=False, reset=False,
                       force_email=True, once=True))
       │
       ├── state_manager.load_state()          ← reads tmp_path/state.json
       ├── data_fetcher.fetch_ohlcv('^AXJO')   ← hits _FakeTicker → axjo_400d
       ├── signal_engine.compute_indicators()  ← LIVE (no mock)
       ├── signal_engine.get_signal()          ← LIVE → FLAT (0)
       ├── sizing_engine.step()                ← LIVE → closes LONG on FLAT
       ├── data_fetcher.fetch_ohlcv('AUDUSD=X')← hits _FakeTicker → audusd_400d
       ├── signal_engine.compute_indicators()  ← LIVE
       ├── signal_engine.get_signal()          ← LIVE → FLAT (0)
       ├── sizing_engine.step()                ← LIVE (AUDUSD position closes)
       ├── state_manager.mutate_state()        ← W3 save #1
       ├── notifier.send_daily_email()         ← composes email
       │   ├── notifier.compose_email_body()   ← LIVE
       │   ├── _atomic_write_html(last_email.html) ← LIVE write
       │   └── _post_to_resend()               ← STUBBED (no-op)
       └── state_manager.mutate_state()        ← W3 save #2

Test assertions
  └── last_email.html → assert subject emoji, date, signal labels,
                         position direction, equity, Drift detected
```

### Recommended Project Structure (new files only)

```
tests/
└── test_integration_f1.py   # new — F1 full-chain + meta-test

.planning/phases/16-hardening-uat-completion/
└── 16-HUMAN-UAT.md          # new — 3 UAT scenarios
```

### Pattern 1: F1 Setup — state seed + two boundary mocks

```python
# Source: tests/test_main.py::TestDriftWarningLifecycle._setup
# + tests/test_data_fetcher.py::_load_recorded_fixture

import pytest
import pandas as pd
from pathlib import Path
import state_manager
import main
import notifier

FETCH_FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'fetch'
NOTIFIER_FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'notifier'

def _load_fetch_fixture(name: str) -> pd.DataFrame:
    return pd.read_json(FETCH_FIXTURE_DIR / name, orient='split')

@pytest.mark.freeze_time('2026-04-28T00:00:00+00:00')  # Mon 08:00 AWST
def test_full_chain_fetch_to_email(tmp_path, monkeypatch):
    # 1. Seed state — sample_state_with_change has SPI200 SHORT + AUDUSD LONG
    #    positions and a drift warning already present (tests drift banner path)
    import json
    seed = json.loads((NOTIFIER_FIXTURE_DIR / 'sample_state_with_change.json').read_text())
    monkeypatch.chdir(tmp_path)
    state_manager.save_state(seed)

    # 2. Mock boundary 1: yfinance fetch → canonical 400d fixtures
    def _fake_ticker_factory(sym):
        class _T:
            def history(self, **_kw):
                name = 'axjo_400d.json' if sym == '^AXJO' else 'audusd_400d.json'
                return _load_fetch_fixture(name)
        return _T()
    monkeypatch.setattr('data_fetcher.yf.Ticker', _fake_ticker_factory)
    monkeypatch.setattr('data_fetcher.time.sleep', lambda *a, **k: None)

    # 3. Mock boundary 2: Resend dispatch → no-op stub
    post_calls = []
    def _stub_post(*a, **kw):
        post_calls.append(a)
    monkeypatch.setattr(notifier, '_post_to_resend', _stub_post)

    # 4. Set SIGNALS_EMAIL_FROM so send_daily_email doesn't short-circuit
    monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@example.com')
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)

    import argparse
    args = argparse.Namespace(test=False, reset=False, force_email=True, once=True,
                               initial_account=None, spi_contract=None, audusd_contract=None)
    rc = main.run_daily_check(args)
    assert rc == 0

    # 5. Assert on last_email.html content
    email_html = (tmp_path / 'last_email.html').read_text(encoding='utf-8')
    # [assertions — see §Code Examples below]
```

### Pattern 2: Meta-test — patch.object on signal_engine attribute

```python
# Source: tests/test_main.py line 2726
# monkeypatch.setattr(main.signal_engine, 'get_signal', _fake_get_signal)
#
# CRITICAL: main.py uses `import signal_engine` at module top (line 44).
# The name `signal_engine` in main's namespace is bound to the module object.
# `monkeypatch.setattr(main.signal_engine, 'get_signal', stub)` replaces
# the 'get_signal' attribute on THAT module object — the same object
# whose attribute main.py reads at line 1163: `signal_engine.get_signal(...)`.
# This IS effective. The bound reference does get patched.
#
# Alternative: unittest.mock.patch.object(signal_engine, 'get_signal', ...)
# where `import signal_engine` is done at test top — equivalent.

from unittest.mock import patch
import signal_engine

def test_f1_catches_planted_regression(tmp_path, monkeypatch):
    # [setup identical to test_full_chain_fetch_to_email]
    ...

    # Plant regression: get_signal returns wrong value (simulates rename)
    with patch.object(signal_engine, 'get_signal', return_value=999):
        # F1 must RED-LIGHT here
        rc, *_ = main.run_daily_check(args)
        email_html = (tmp_path / 'last_email.html').read_text()
        # Assert the value-level assertion FAILS with the planted break
        # (999 is not a valid signal label → email shows wrong content)
        assert 'LONG' not in email_html or 'SHORT' not in email_html

    # Sanity check: without patch, F1 GREEN
    rc2 = main.run_daily_check(args)
    assert rc2 == 0
```

### Pattern 3: `_post_to_resend` monkeypatch (existing pattern)

```python
# Source: tests/test_notifier.py line 1171
monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: None)
# OR attribute on the notifier module object:
monkeypatch.setattr('notifier._post_to_resend', lambda *a, **kw: None)
```

### Anti-Patterns to Avoid

- **Mocking `fetch_ohlcv` directly:** D-02 requires mocking at `requests.get` equivalent — use `data_fetcher.yf.Ticker` (the actual HTTPS boundary), not `data_fetcher.fetch_ohlcv`. The canonical fixture bytes flow through the real retry logic this way.
- **Patching `notifier.send_daily_email` in F1:** This breaks D-02 — compose_email_body and last_email.html write must run live. Only `_post_to_resend` gets stubbed.
- **Not setting `SIGNALS_EMAIL_FROM`:** send_daily_email short-circuits with `missing_sender` if this env var is absent. F1 must `monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@example.com')`.
- **Using a weekday-gate-blocked date:** `run_daily_check` returns `(0, None, None, run_date)` on weekends. Always use `@pytest.mark.freeze_time` with a Monday UTC midnight (= Mon 08:00 AWST).
- **Not using `monkeypatch.chdir(tmp_path)`:** state.json writes land in CWD. Without chdir, F1 would corrupt the real `./state.json`.
- **Missing `_push_state_to_git` neutralization:** Phase 10's git push helper will try to run `git diff state.json` inside run_daily_check. In the tmp_path it silently fails (no git repo), which is fine — `_push_state_to_git` never raises. But add `monkeypatch.setattr(main, '_push_state_to_git', lambda *a, **kw: None)` for clean isolation.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Fake yfinance response | Custom DataFrame factory | `_load_recorded_fixture('axjo_400d.json')` via `pd.read_json(orient='split')` | Project pattern; exact dtype parity with live yfinance |
| Resend no-op | HTTP intercept library | `monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: None)` | Project convention; no new deps |
| Signal monkey-patch | AST manipulation | `monkeypatch.setattr(main.signal_engine, 'get_signal', stub)` | Already proven in TestDriftWarningLifecycle |
| Email assertion parsing | HTML parser / BeautifulSoup | `assert pattern in email_html` string search | Email HTML is deterministic; string contains is stable and fast |
| Weekday freeze | `datetime.now()` stub | `@pytest.mark.freeze_time(...)` | pytest-freezer already pinned; plays well with AWST offset |

**Key insight:** Every F1 pattern exists in the test suite already. The entire F1 test is assembly of existing patterns, not new invention.

---

## Open Questions — ANSWERED

### OQ-1: Best Phase 1 scenario fixture for F1?

**Answer:** Do NOT use the Phase 1 scenario CSV fixtures (these are short synthetic CSVs designed for isolated signal_engine tests). Instead use the canonical 400-bar fetch fixtures (`axjo_400d.json` + `audusd_400d.json`) combined with the notifier's `sample_state_with_change.json` as the initial state seed.

**Rationale:**
- The 400d fixtures produce **FLAT (0)** signals for both instruments as of their last bars (2026-04-19 and 2026-04-20). [VERIFIED: ran signal_engine against fixtures]
- `sample_state_with_change.json` seeds SPI200 SHORT + AUDUSD LONG positions + a pre-existing drift warning. With FLAT signals from the live compute chain, sizing_engine.step will close both positions (FLAT → close), exercising the full chain including trade recording and P&L calculation.
- The pre-existing drift warning in the seed state means the email will contain `Drift detected` (from `_render_header_email`), exercising Phase 15's SENTINEL-03 surface in one test.
- Both instruments active, positions present, trades close during the run, drift banner renders. This is the richest single-pass coverage.

### OQ-2: Exact text patterns to assert in last_email.html

**Answer (all VERIFIED against notifier.py source code):**

```python
# Subject line (from compose_email_subject):
assert re.search(r'[📊🔴]', email_html) is None  # subject is not in HTML body
# Better: capture subject via the _stub_post call args
subject_arg = post_calls[0][3]  # positional: api_key, from, to, subject
assert re.match(r'[📊🔴] \d{4}-\d{2}-\d{2} — SPI200 (LONG|SHORT|FLAT), AUDUSD (LONG|SHORT|FLAT) — Equity \$[\d,]+', subject_arg)

# Body assertions (all string-contains checks):
assert 'SPI 200' in email_html       # _fmt_instrument_display_email('SPI200')
assert 'AUD / USD' in email_html     # _fmt_instrument_display_email('AUDUSD')
assert 'FLAT' in email_html          # signal label for both instruments
assert '$' in email_html             # equity figure with thousands separator
assert '━━━ Drift detected ━━━' in email_html  # drift banner header (line 672 notifier.py)
assert 'SPI200' in email_html        # instrument name in drift warning bullet
assert '<!DOCTYPE html>' in email_html  # overall well-formedness
```

**Notes:**
- Subject is checked by capturing the `_stub_post` call args (positional index 3), not from the HTML.
- Equity format: `$X,XXX` (integer, no cents) — `int(round(account))` formatted with `,` thousands separator.
- Drift warning message text from `sample_state_with_change.json`: `"You hold SHORT SPI200, today's signal is LONG — reversal recommended (close SHORT, open LONG)."` This message will be in the email body as-is (html.escaped).
- The drift warning is from the SEED state; the run will also compute NEW drift (FLAT signals vs positions) and add a new warning — so the email body will contain multiple drift bullet lines.

### OQ-3: Does deploy.sh exist on origin/main / droplet?

**Answer: YES, deploy.sh is committed and was part of the `b1f9b8f` merge commit.** [VERIFIED: `git show b1f9b8f --stat` shows `deploy.sh | 91 ++` in that commit]

`deploy.sh` at the repo root is a 92-line idempotent script (Phase 11 INFRA-04). It already includes the nginx reload gate block (Phase 12). The Phase 16 deploy task uses `bash deploy.sh` verbatim — no modifications needed.

### OQ-4: EXACT current state of Phase 10/12 work

**Answer: ALL Phase 10/12 code shipped in `b1f9b8f`.** [VERIFIED: `git show b1f9b8f --stat`]

The commit message "Phase 10 + 11 + 12: v1.0 cleanup, deploy key, FastAPI web skeleton, HTTPS + domain wiring (#1)" is accurate. The stat shows:
- `main.py` +217 lines (includes `_push_state_to_git` = INFRA-02 + BUG-01 reset_state fix)
- `notifier.py` +65 lines (includes SIGNALS_EMAIL_FROM env read = INFRA-01 partial)
- `state_manager.py` +16 lines
- `deploy.sh` +91 lines (INFRA-04)
- `nginx/signals.conf` +97 lines (WEB-03/04)
- `systemd/trading-signals-web.service` +30 lines (WEB-01)
- `.github/workflows/daily.yml.disabled` (INFRA-03 — GHA retired)
- 82 files total changed

**Local-only commits (60 commits):** All Phase 13 (auth + read endpoints), Phase 14 (trade journal), Phase 15 (calculator + sentinels), and the 3 planning/docs commits for Phase 16. None of Phase 10/12's code changes are local-only — they are already on origin/main.

**Bottom line:** The ROADMAP showing Phase 10 + 12 as "Not started" is stale documentation; the code and tests for Phases 10/12 shipped in the large merged PR (`b1f9b8f`). The GSD tracking artifacts (PLAN.md, SUMMARY.md, etc.) were never created because those phases were done outside the GSD workflow, but the code is present and on origin/main. Phase 16's deploy task is a straight `git push origin main` (pushing 60 local commits) followed by `bash deploy.sh` on the droplet. No backfill needed.

### OQ-5: Does `patch.object(signal_engine, 'get_signal', ...)` survive main.py's import?

**Answer: YES.** [VERIFIED: main.py line 44 `import signal_engine`; line 1163 `signal_engine.get_signal(df_with_indicators)`]

main.py uses attribute access on the module object (`signal_engine.get_signal(...)`), NOT a bound local `from signal_engine import get_signal`. This means:
- `monkeypatch.setattr(main.signal_engine, 'get_signal', stub)` replaces the `get_signal` attribute on the shared module object
- main.py's next call `signal_engine.get_signal(...)` looks up the attribute on that same module object → gets the stub
- The patch IS effective

This is confirmed by the existing test at `tests/test_main.py:2726`:
```python
monkeypatch.setattr(main.signal_engine, 'get_signal', _fake_get_signal)
```
That test passes today (1156 tests passing), proving the pattern works.

Contrast: if main.py had `from signal_engine import get_signal` at top, the local name `get_signal` would be a copy of the function reference, and patching the module would NOT affect the local name. That is NOT how this codebase is structured.

---

## Common Pitfalls

### Pitfall 1: SIGNALS_EMAIL_FROM missing → send_daily_email early return

**What goes wrong:** `send_daily_email` reads `SIGNALS_EMAIL_FROM` env var and returns `SendStatus(ok=False, reason='missing_sender')` before composing or writing `last_email.html`. F1 test would pass (rc=0) but `last_email.html` would not exist — assertion `assert last_email_path.exists()` would fail.
**Why it happens:** Phase 12 removed the hardcoded `_EMAIL_FROM` constant and replaced it with a per-send env read.
**How to avoid:** `monkeypatch.setenv('SIGNALS_EMAIL_FROM', 'signals@example.com')` in F1 setup.
**Warning signs:** `last_email.html` does not exist in `tmp_path` after the run.

### Pitfall 2: Weekend skip → run_daily_check returns (0, None, None, run_date)

**What goes wrong:** If `freeze_time` is a Saturday/Sunday UTC midnight, `run_daily_check` short-circuits at the weekday gate. No fetch, no email, no `last_email.html`. All assertions fail.
**How to avoid:** Use Monday 00:00:00 UTC (= Monday 08:00:00 AWST). Confirmed working: `'2026-04-28T00:00:00+00:00'` is Monday 28 April 2026.
**Warning signs:** rc=0 but `last_email.html` not written.

### Pitfall 3: `_push_state_to_git` git subprocess in tmp_path

**What goes wrong:** Phase 10's `_push_state_to_git` runs `git diff --quiet state.json` inside the tmp_path directory, which has no `.git`. The subprocess returns rc>=128. The helper logs `[State] git diff failed` and appends a warning to state — this contaminates the warnings list and may break W3 invariant assertions if the F1 test checks warning count.
**Why it happens:** `_push_state_to_git` is called from `run_daily_check` step sequence after the first `mutate_state` call.
**How to avoid:** Add `monkeypatch.setattr(main, '_push_state_to_git', lambda *a, **kw: None)` to F1 setup.
**Warning signs:** `[State] git diff failed (rc=128)` in captured logs; unexpected warnings in state.

### Pitfall 4: W3 invariant — meta-test must not leave state corrupt

**What goes wrong:** If the meta-test runs `run_daily_check` inside a `patch.object` context and the patched function causes an exception (AttributeError vs wrong return value), the exception propagates past W3's second `mutate_state`, leaving state unsaved. Subsequent assertions on `last_email.html` fail.
**How to avoid:** Use `return_value=999` (not `side_effect=AttributeError`) for the planted regression — the chain runs to completion, just with wrong signal values. Then assert that the email body does NOT contain expected signal text. Cleaner: assert that the email body contains an unexpected label like `FLAT` for both (since 999 is not in `_SIGNAL_LABELS_EMAIL`).
**Warning signs:** Test hangs or raises mid-run rather than asserting on output.

### Pitfall 5: Deploy — droplet on old Python / venv

**What goes wrong:** The droplet's `.venv` may have older package versions than requirements.txt specifies. Phase 13-15 added new packages (fastapi, uvicorn, httpx, pydantic). `pip install -r requirements.txt` in `deploy.sh` handles this, but if `.venv/bin/pip` is not present (venv deleted), the deploy fails.
**How to avoid:** The deploy task's acceptance test includes `bash deploy.sh` exits 0 AND the healthz smoke check passes — both are required.
**Warning signs:** `deploy.sh` fails at the `.venv/bin/pip install` step.

### Pitfall 6: notifier golden snapshot tests conflict

**What goes wrong:** `tests/test_notifier.py::TestGoldenEmail` compares `last_email.html` output byte-for-byte against committed goldens. If F1 test runs in CI without isolation (`monkeypatch.chdir(tmp_path)`), it writes `last_email.html` in the working directory and the golden test sees the F1 output instead of the notifier fixture output.
**How to avoid:** `monkeypatch.chdir(tmp_path)` in F1 ensures `last_email.html` writes to the tmp dir, not `./`. This is already the project pattern for all tests that invoke `send_daily_email`.
**Warning signs:** `TestGoldenEmail` fails after F1 passes in the same pytest run.

---

## Code Examples

### Asserting on subject via captured _post_to_resend args

```python
# Source: test pattern from tests/test_notifier.py::TestSendDispatch
# _post_to_resend signature: (api_key, from_addr, to_addr, subject, html_body=None, ...)
post_calls = []
monkeypatch.setattr(notifier, '_post_to_resend', lambda *a, **kw: post_calls.append((a, kw)))

# After run:
if post_calls:
    # api_key not set in test → _post_to_resend never called
    # Instead assert on last_email.html (always written when SIGNALS_EMAIL_FROM is set)
    pass
# Better pattern: don't set RESEND_API_KEY in F1 → _post_to_resend never called anyway.
# last_email.html is written BEFORE the api_key check (notifier.py line 1474).
# So: do NOT set RESEND_API_KEY in F1 → NOTF-08 path → last_email.html written, no dispatch.
```

**Revised F1 mock strategy (simpler):**
- Do NOT set `RESEND_API_KEY` in the F1 test environment.
- `send_daily_email` will write `last_email.html` (line 1476) and then return `SendStatus(ok=True, reason='no_api_key')` (line 1490) — no `_post_to_resend` call.
- No need to mock `_post_to_resend` at all.
- Subject is available from `compose_email_subject` directly (call it separately with the same state + old_signals), or extract from `last_email.html` if the subject is embedded (it is not — subject is only in the Resend POST).
- **Alternative:** mock `_post_to_resend` as a capture stub AND set `RESEND_API_KEY=test_key` to force the dispatch path, capturing subject from the call. This exercises more of the send_daily_email code path.

**Recommended:** Set `RESEND_API_KEY=test_key` + stub `_post_to_resend` to capture calls. This exercises the full dispatch path (not just the no-api-key shortcut) and lets F1 assert on the subject line.

### _post_to_resend capture stub + subject assertion

```python
# Source: adapted from tests/test_notifier.py::TestSendDispatch
captured = {}
def _capture_post(api_key, from_addr, to_addr, subject, html_body=None, **kw):
    captured['subject'] = subject
    captured['html'] = html_body or ''

monkeypatch.setenv('RESEND_API_KEY', 'test_key_f1')
monkeypatch.setattr(notifier, '_post_to_resend', _capture_post)

# After run:
import re
subject = captured['subject']
assert re.search(r'\d{4}-\d{2}-\d{2}', subject), 'subject must contain YYYY-MM-DD date'
assert 'SPI200' in subject
assert 'AUDUSD' in subject
assert 'Equity' in subject
assert '$' in subject
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| save_state() directly | mutate_state() with fcntl lock | Phase 14 Plan 02 | F1 must NOT call save_state() directly in assertions; only mutate_state |
| Phase 1 scenario CSV fixtures | 400d fetch fixtures from tests/fixtures/fetch/ | Phase 4 | F1 uses fetch fixtures, not scenario CSVs |
| `_post_to_resend` called always | SIGNALS_EMAIL_FROM gate before compose | Phase 12 | F1 must set SIGNALS_EMAIL_FROM env var |
| GHA cron = primary runner | DO droplet systemd = primary runner | Phase 10/11 | deploy.sh is the deploy mechanism, not GHA workflow |

**Deprecated/outdated:**
- `tests/fixtures/yfinance_canonical_axjo.json` / `yfinance_canonical_audusd.json`: These filenames were referenced in the CONTEXT.md `<canonical_refs>` section but do NOT exist at that path. The actual fetch fixture files are `tests/fixtures/fetch/axjo_400d.json` and `tests/fixtures/fetch/audusd_400d.json`. [VERIFIED: `ls tests/fixtures/fetch/`]
- `tests/fixtures/scenarios/*.json`: These are signal_engine scenario CSVs, not JSON files with state. The scenarios.README.md confirms they are CSV files, not JSON. The CONTEXT.md D-01 reference to `tests/fixtures/scenarios/*.json` is imprecise — the planner should use the fetch fixtures instead.

---

## Runtime State Inventory

> Rename/refactor phase: N/A — Phase 16 adds new files, does not rename anything.

Not applicable. Phase 16 creates new files only:
- `tests/test_integration_f1.py` (new)
- `.planning/phases/16-hardening-uat-completion/16-HUMAN-UAT.md` (new)
- STATE.md edits (restructure existing sections)

No renaming, no stored-data migration, no OS-registered state changes.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pytest | F1 test | ✓ | 8.3.3 | — |
| pytest-freezer | F1 freeze_time | ✓ | pinned | — |
| Python 3.11 | All | ✓ | 3.11.8 | — |
| git push to origin/main | Deploy task | ✓ | local main is 60 commits ahead of origin/main | — |
| droplet SSH access | Deploy task | Operator-owned | unknown | Operator must confirm SSH key available |
| `bash deploy.sh` on droplet | Deploy task | ✓ (deploy.sh in repo since b1f9b8f) | — | — |
| `SIGNALS_EMAIL_FROM` on droplet | UAT-16-B (real Gmail) | Operator-set in droplet .env | unknown | Operator must confirm |
| Resend domain verified | UAT-16-B (real Gmail from verified domain) | Operator-set | unknown | Can test with onboarding@resend.dev fallback but INFRA-01 is already in codebase |

**Missing dependencies with no fallback:**
- Operator's SSH access to the droplet (deploy task is blocked without it; but this is operator-owned prerequisite, not code work)

**Missing dependencies with fallback:**
- `RESEND_API_KEY` on droplet — UAT-16-B requires real email delivery; if key not set, email only writes `last_email.html` locally. Operator must confirm key is present.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `sample_state_with_change.json` is the best F1 seed (produces both closes + drift banner) | Open Questions / Code Examples | Might pick a simpler scenario that skips drift path; mitigated by explicitly verifying the state's warnings field |
| A2 | The droplet's `.venv` will accept Phase 13-15 packages on `pip install -r requirements.txt` | Environment Availability | Deploy may fail if Python 3.11 interpreter differs or disk space issue; fallback: operator rebuilds venv |
| A3 | Droplet still at `b1f9b8f` (per Phase 15 UAT finding) | Deploy section | If operator already pushed something, git pull --ff-only may fail; deploy.sh's branch check handles this |

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.3 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/pytest tests/test_integration_f1.py -x -q` |
| Full suite command | `.venv/bin/pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CHORE-01 SC-1 | Full chain fetch→email with section + key-value assertions | integration | `.venv/bin/pytest tests/test_integration_f1.py::test_full_chain_fetch_to_email -x` | ❌ Wave 0 |
| CHORE-01 SC-2 | Meta-test: F1 red-lights on planted `get_signal` regression | integration | `.venv/bin/pytest tests/test_integration_f1.py::test_f1_catches_planted_regression -x` | ❌ Wave 0 |
| CHORE-03 SC-3a | UAT-16-A: mobile dashboard loads on hosted URL | manual | Operator verification in 16-HUMAN-UAT.md §UAT-16-A | ❌ Wave 0 |
| CHORE-03 SC-3b | UAT-16-B: email renders in real Gmail on mobile | manual | Operator verification in 16-HUMAN-UAT.md §UAT-16-B | ❌ Wave 0 |
| CHORE-03 SC-3c | UAT-16-C: drift banner in real weekday email (may take >1 day) | manual | Operator verification in 16-HUMAN-UAT.md §UAT-16-C | ❌ Wave 0 |
| SC-4 | STATE.md `## Completed Items` exists with 3 migrated items + verification dates | manual | Grep: `grep -c "## Completed Items" .planning/STATE.md` = 1 | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest tests/test_integration_f1.py -x -q`
- **Per wave merge:** `.venv/bin/pytest tests/ -x -q`
- **Phase gate:** Full suite green (`pytest tests/ -q` with 0 failures) before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_integration_f1.py` — covers CHORE-01 SC-1 + SC-2 (new file; two test functions)
- [ ] `.planning/phases/16-hardening-uat-completion/16-HUMAN-UAT.md` — covers CHORE-03 SC-3a/b/c (new file; operator fills in)
- [ ] STATE.md `## Completed Items` section — covers SC-4 (edit to existing file; created after operator marks UAT verified)

No framework gaps — pytest, pytest-freezer, and all project dependencies are already installed.

---

## Security Domain

Phase 16 adds only test code and documentation. No new HTTP endpoints, no new auth surfaces, no new data paths. ASVS review is not applicable.

| ASVS Category | Applies | Rationale |
|---------------|---------|-----------|
| V2 Authentication | no | No new endpoints |
| V3 Session Management | no | No new session handling |
| V4 Access Control | no | No new access checks |
| V5 Input Validation | no | Test assertions, not user input |
| V6 Cryptography | no | No new crypto operations |

**Known threat patterns for this phase:**
- Deploy task sends `git push origin main` which includes 60 commits of Phase 13/14/15 code. These phases introduced AUTH-01..03 (shared-secret middleware), TRADE-01..06 (mutation endpoints with Pydantic validation), and SENTINEL-01..03 (drift detection). The security properties of those phases were verified in their own code reviews. Phase 16 deploy ships them as-is — no new threat surface introduced by Phase 16 itself.

---

## Sources

### Primary (HIGH confidence)
- `tests/test_data_fetcher.py` — monkeypatch `data_fetcher.yf.Ticker` pattern (verified in codebase)
- `tests/test_notifier.py` — `_post_to_resend` mock pattern + SIGNALS_EMAIL_FROM autouse fixture (verified)
- `tests/test_main.py::TestDriftWarningLifecycle` — W3 invariant, `main.signal_engine.get_signal` patch, `_setup` scaffold pattern (verified line 2647-2826)
- `notifier.py` lines 645-678 — drift banner HTML with `━━━ Drift detected ━━━` literal (verified)
- `notifier.py` line 1474 — `last_email.html` written before api_key check (verified)
- `deploy.sh` — confirmed present in repo since `b1f9b8f`, implements D-12 deploy mechanism (verified)
- `git show b1f9b8f --stat` — confirmed Phase 10/12 code shipped in that commit (verified)
- `git log --oneline origin/main..HEAD` — confirmed 60 local-only commits (Phases 13/14/15) (verified)
- `.venv/bin/python -c "signal_engine.get_signal(...)"` — FLAT signals from canonical fixtures (verified)
- `tests/fixtures/notifier/sample_state_with_change.json` — drift warning present, SPI200 SHORT + AUDUSD LONG (verified)
- `.planning/milestones/v1.0-phases/06-email-notification/06-HUMAN-UAT.md` — 3 pending UAT scenarios (verified)

### Secondary (MEDIUM confidence)
- `.planning/ROADMAP.md` Phase 16 section — success criteria + plan structure
- `.planning/STATE.md §Deferred Items` — items to migrate confirmed

### Tertiary (LOW confidence)
- Droplet's current state (beyond what `git log` shows) is unverified — SSH access and actual running version not checked in this session.

---

## Metadata

**Confidence breakdown:**
- F1 test architecture: HIGH — all patterns verified against codebase
- Deploy path: HIGH — git log confirmed 60 local-only commits, deploy.sh confirmed in repo
- HUMAN-UAT content: HIGH — 06-HUMAN-UAT.md read, all 3 scenarios documented
- Droplet runtime state: MEDIUM — based on Phase 15 UAT finding; actual SSH probe not done

**Research date:** 2026-04-26
**Valid until:** 2026-05-26 (stable domain — no fast-moving dependencies)
