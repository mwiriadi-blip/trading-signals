# Stack Research

**Domain:** Python quant / mechanical trading signal app (single-user, daily schedule, Replit + GitHub Actions fallback)
**Researched:** 2026-04-20
**Confidence:** MEDIUM-HIGH (core library choices HIGH; hosting specifics MEDIUM due to rapidly-evolving Replit product lines)

---

## Executive Summary

**The spec's stack is correct.** Stick with it.

`yfinance + pandas + numpy + requests + schedule + python-dotenv + pytz` is the right shape for a single-operator daily signal app. Three adjustments are worth making:

1. **Hand-roll ATR(14) / ADX(20) / +DI / -DI in ~60 lines of NumPy.** Do not add `pandas-ta` or `TA-Lib` as a dependency. The canonical pandas-ta repo is at risk of archival by July 2026, TA-Lib needs a C compiler (pain on Replit), and Wilder's smoothing is trivial to implement and unit-test deterministically. This is the dominant reason the spec does not list a TA library — ship without one.
2. **Use `requests` for Resend, not the `resend` SDK.** The spec already shows the raw-requests pattern. Resend's Node SDK is first-class; the Python SDK lags and adds a dependency for what is a single POST with a Bearer token. Spec is right — don't add it.
3. **Pin `yfinance>=0.2.65` (not `>=0.2.40`).** Older 0.2.4x/0.2.5x versions have documented rate-limit and session-handling breakage throughout 2025. A 400-day history pull for 2 tickers once per day will not hit rate limits with a modern version, but pinning too loose invites surprise.

On hosting: **GitHub Actions with a committed `state.json` is the more reliable primary choice**, not the fallback. Replit's filesystem persistence in 2025 deployments is no longer guaranteed (their own docs say "avoid relying on data written to a published app's filesystem") — the spec's "primary Replit, fallback GitHub Actions" split should be re-framed as "equal peers, pick the one that fits Marc's operational preference." Both get documented; GHA is the safer default.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11.x | Runtime | 3.11 is the safe Replit / GHA default; widely supported on `actions/setup-python@v5`. 3.12/3.13 work but some TA libs (not ours) lag. `match` statements and better error messages are nice-to-haves. |
| pandas | 2.2.x | DataFrame math, rolling windows, time series | Industry standard. The 2.x branch is stable; 2.2.3 is the current long-tail. Avoid 3.0 pre-releases. |
| numpy | 1.26.x OR 2.0.x | Array math, `sqrt`, `std` | Either works. Prefer 2.0+ unless a transitive dep complains. pandas 2.2 supports both. |
| yfinance | >=0.2.65, <0.3 | OHLCV pull for `^AXJO` and `AUDUSD=X` | Only free, zero-auth source that covers both ASX indexes and FX pairs reliably. 0.2.65+ fixed the mid-2025 rate-limit regressions. |
| requests | >=2.32, <3 | HTTP client for Resend API | Spec-mandated; already a transitive dep of yfinance. Use it directly for Resend — no SDK needed. |
| schedule | >=1.2.2 | In-process daily scheduler | Spec-mandated. For a single daily job with a once-per-start immediate run, it is simpler than APScheduler. See scheduler note below. |
| python-dotenv | >=1.0.1 | Load `.env` locally | Standard. Replit Secrets and GitHub Actions env inject directly; dotenv is for local dev only. |
| pytz | >=2024.1 | `Australia/Perth` timezone handling (AWST, UTC+8, no DST) | Spec-mandated. `zoneinfo` (stdlib) is the modern replacement but spec says pytz and Perth has no DST so behaviour is identical. Stick with spec. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | >=8.2 | Unit tests for signal engine | Always — determinism of ATR/ADX/signal must be provable. See testing section below. |
| pytest-freezer (or `freezegun`) | >=0.4.8 / >=1.5 | Freeze `datetime.now()` in tests | When testing schedule logic, signal-change detection, and "is it weekday?" gating. |
| numpy.testing | stdlib of numpy | `assert_allclose` for float comparisons | Always — exact float equality fails on Wilder's recursive smoothing. |

**Libraries deliberately NOT added (and why):** see "What NOT to Use" below. The total prod dependency count stays at 7 — this is a feature, not a limitation.

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| pytest | Test runner | `pytest -q` in CI; no plugins required beyond maybe `pytest-freezer`. |
| requirements.txt | Lockfile | Spec says `requirements.txt`. Keep it. See "Lockfile" section. |
| `.env.example` | Env var template | Spec-mandated. Commit this, gitignore `.env`. |

---

## Installation

```bash
# Core (requirements.txt)
pip install \
  "yfinance>=0.2.65,<0.3" \
  "pandas>=2.2,<3" \
  "numpy>=1.26,<3" \
  "requests>=2.32,<3" \
  "schedule>=1.2.2,<2" \
  "python-dotenv>=1.0.1,<2" \
  "pytz>=2024.1"

# Dev (requirements-dev.txt — optional file)
pip install "pytest>=8.2" "pytest-freezer>=0.4.8"
```

`requirements.txt` content (copy-paste):

```
yfinance>=0.2.65,<0.3
pandas>=2.2,<3
numpy>=1.26,<3
requests>=2.32,<3
schedule>=1.2.2,<2
python-dotenv>=1.0.1,<2
pytz>=2024.1
```

---

## Key Decisions with Rationale

### 1. yfinance vs Alpaca / Polygon / Alpha Vantage / IB

**Decision:** yfinance. Confidence: HIGH for this use case; MEDIUM long-term (see pitfall).

**Why yfinance wins here:**
- **Coverage:** `^AXJO` (S&P/ASX 200 index) and `AUDUSD=X` (FX pair) are both first-class Yahoo symbols. Alpaca is US equities + crypto — no ASX index, no FX. Polygon is US-focused on the free tier; ASX 200 needs a paid plan. Interactive Brokers requires an account, TWS/gateway process, and is overkill for end-of-day daily close on 2 symbols.
- **Auth:** zero API key. Critical for GitHub Actions free-tier and for "clone and run" developer experience.
- **Rate limit:** 2 tickers × 400 days × once per day = 2 calls/day. Nowhere near Yahoo's unofficial ceiling. The 2025 rate-limit incidents that flooded the yfinance GitHub issues were from users polling hundreds of tickers per minute or scraping in tight loops — not daily batch pulls.
- **Spec says so.** Don't fight the spec for a stack decision unless there's a blocker.

**When to revisit:** if Yahoo changes the `^AXJO` symbol format, rate-limits tripping daily on a free IP, or FX history stops loading. Budget 30 min of rework to swap `fetch_data()` behind an interface.

**Runner-up for ASX index + FX if yfinance breaks:** Alpha Vantage has both (`^AXJO` as ASX, FX endpoints), free tier is 25 calls/day which covers this app exactly. Requires a free API key.

### 2. Hand-roll TA vs pandas-ta vs TA-Lib vs `ta`

**Decision:** Hand-roll ATR(14) Wilder, ADX(20) Wilder, +DI, -DI in ~60 lines of NumPy inside `signal_engine.py`. Confidence: HIGH.

**Why:**
- **pandas-ta (twopirllc/pandas-ta):** The canonical repo has been effectively unmaintained for a long stretch, and as of early 2026 the maintainer has flagged archival by July 2026 without additional support. Multiple community forks exist (pandas-ta-classic, aarigs/pandas-ta, Pandas-Quant-Finance/pandas-ta, pandas-ta-openbb) — none are a universally blessed successor. This is not a foundation to build on for a 5+ year operator tool.
- **TA-Lib:** Requires the native C library (`ta-lib` .so/.dylib/.dll) to be installed before the Python wrapper compiles. On Replit that means a nix package or manual build; on GitHub Actions it's `apt-get install`. Both solvable, but adding a C-extension dependency for 3 indicators is bad cost/value.
- **`ta` (bukosabino/ta):** Pure-Python and more actively maintained than pandas-ta, but 0.11 release is from 2023 and the library is on a very slow cadence. Usable, but doesn't beat hand-rolling for 3 indicators.
- **Hand-rolled wins because:**
  - Wilder's ATR is `TR.ewm(alpha=1/14, adjust=False).mean()` — one line. ADX is ~30 lines (TR, +DM, -DM, smoothed via Wilder, DX, ADX). Total module fits in well under 100 lines.
  - **Determinism.** You own the math. Unit tests pin the output of known synthetic input. No library version can silently change a smoothing formula and invalidate historic signals.
  - **Audit trail.** Marc can print every intermediate column and reconcile against a spreadsheet. With a TA library, the recursion state is opaque.
  - **Zero extra dep.** Staying at 7 prod packages keeps the requirements.txt lockable and reproducible.

The spec does NOT list a TA library in `requirements.txt`. That is the correct call.

### 3. `schedule` vs APScheduler vs cron

**Decision:** `schedule` for the in-process Replit path. **Cron (GitHub Actions)** for the cloud path. No APScheduler. Confidence: HIGH.

**Why `schedule` is fine here:**
- One job, one instrument loop, once per day. `schedule.every().day.at("00:00").do(run_daily_check)` with a `while True: schedule.run_pending(); time.sleep(60)` loop is 4 lines and does exactly what's needed.
- APScheduler's selling points — persistent job stores, cron triggers, complex chaining, async execution — are overkill for a single daily run. The cost is more deps, more config, and more surface area for subtle bugs around misfire grace and coalesce behaviour.
- `schedule` has no persistence (jobs reset on restart). For this app that's fine — the "job" is hard-coded in `main.py`, not user-defined, so a restart just re-declares it.

**When APScheduler would be right:** multiple jobs, per-instrument schedules, persistent misfire handling across restarts, or intraday cadence. Not this app.

**Why cron is better than `schedule` on GitHub Actions:** GHA workflow `schedule` trigger IS cron — the script itself just runs once, computes the signal, commits `state.json`, exits. There's nothing to schedule inside Python. The `schedule` loop from `main.py` is only used when running as a persistent process (Replit Always On / Reserved VM / local dev).

**Cron expression for Perth 08:00 AWST:** `0 0 * * 1-5` (UTC 00:00, Monday–Friday). **Do not use `0 22 * * 1-5`** — that's 08:00 AEST (Sydney), not AWST (Perth). The spec has this correct in `## Constraints` but the SPEC.md inline comments mix AEST/AWST — `main.py` and `.github/workflows/*.yml` must use `00:00` UTC for Perth. This is a spec-consistency note more than a stack decision; flag it.

### 4. Resend: `requests` vs `resend` SDK

**Decision:** `requests`. Confidence: HIGH.

**Why:**
- The Resend REST call is `POST https://api.resend.com/emails` with a Bearer token and a JSON body of `{from, to, subject, html}`. That's it. 10 lines of `requests.post`.
- The `resend` Python SDK (current 2.29.0 as of April 2026) adds a dependency, a wrapper class, and a module-level global for the API key. Their Node SDK is the first-class product; the Python SDK tracks it but the API surface is small enough that the wrapper is pure overhead.
- Marc already has Resend working on Carbon Bookkeeping via the HTTP API pattern — matching that pattern makes the mental model consistent across his projects.
- Error handling: with raw `requests`, a 401/422 from Resend is an `HTTPError` with the JSON body right there. With the SDK it's an `resend.exceptions.*` class — one more layer to learn.

**When the SDK would be right:** if Resend adds webhooks, idempotency keys, batch sends, or attachments to the Python path and you want first-class support. For a single `html` email per day, `requests` wins.

### 5. Chart.js via CDN in a single static HTML file

**Decision:** `<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>` (UMD build). Confidence: HIGH.

**Why and the pitfall to avoid:**
- Chart.js 4.x ships two builds: **UMD** (`chart.umd.js`, attaches `Chart` to `window`) and **ESM** (`chart.js`, requires `import`). When you drop a `<script>` tag into a static HTML file with no `type="module"`, you MUST use the UMD build.
- The Chart.js docs' "Getting Started" page has historically pointed at the bare package path on jsDelivr which resolves to the ESM build — paste that into a classic `<script>` tag and you get `Uncaught SyntaxError: Cannot use import statement outside a module`. The dashboard.html will render blank.
- **Recommended exact tag:** `<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js"></script>` — pinned minor version, explicit UMD path, and SRI hash can be added later if desired. `@4` without a version works but risks silent upgrades breaking the dashboard between runs.
- **Offline fallback pitfall:** if the user opens `dashboard.html` without internet, no chart renders. Acceptable for this use case (Marc views it right after email arrives), but if "dashboard opens on laptop at 3am offline" is a user story, inline the minified Chart.js (~230KB) into the HTML. For MVP: CDN is fine.

### 6. Replit vs GitHub Actions deployment

**Decision:** Document both. Recommend **GitHub Actions as the default**, Replit as the "I want a persistent dashboard URL" option. Confidence: MEDIUM (Replit product lineup shifts quarterly).

**Why GHA is the safer default:**
- **Free:** no plan upgrade needed. 2000 min/mo free for public repos; this app uses ~5 min/day = 100 min/mo. Private repos get 2000 min/mo free too.
- **State persistence is explicit and auditable:** the workflow commits `state.json` to the repo. Every daily run produces a git commit. Full history for free. No mystery about whether state survived.
- **Known failure modes:** GHA cron has documented delays of up to an hour and occasional skips; repos inactive for 60 days get their schedules paused until a push. Both are surface-level and mitigated: the app includes a "last_run > 2 days old → warn in email" check per the spec.

**Why Replit needs caveats:**
- **"Always On" is no longer the one-click feature it was.** Replit's 2025 deployment model pushed users toward **Reserved VM**, **Autoscale**, and **Scheduled Deployments**. Reserved VM is $7+/mo; Scheduled Deployments fit this app perfectly (1-min granularity, 11-hour max) but the free tier is limited. Autoscale scales to zero between requests — bad for a scheduler that needs to stay alive.
- **Filesystem persistence warning from Replit's own docs:** "avoid saving and relying on data written to a published app's filesystem." This directly contradicts the spec's assumption that `state.json` survives on Replit. Inside a single Reserved VM instance it usually does, but Replit does not guarantee it across redeploys or instance replacement.
- **Recommendation if using Replit:** use a **Scheduled Deployment** (runs `main.py` once at a cron time and exits), and persist `state.json` by pushing to a sibling GitHub repo via a deploy key. Or: use **Replit Object Storage** / **Replit DB** instead of a local file. Both break the "single state.json file" constraint from the spec.
- **Simpler alternative:** if using Replit, pair it with GitHub Actions as the state backup, or accept that GHA *is* the production deployment and Replit is a convenient dev/testing environment.

**The spec's "Replit primary, GitHub Actions fallback" framing should be inverted in the deployment guide.** Both are documented, but guide Marc toward GHA for the 08:00 AWST daily run, and let Replit be the interactive dev environment.

### 7. Testing

**Decision:** pytest with fixture-based synthetic OHLCV input. Confidence: HIGH.

**What to test (deterministically):**
- `compute_indicators(df)`: feed a hand-crafted 50-bar OHLCV frame, assert ATR(14), ADX(20), +DI, -DI values to 6 decimal places against a reference calculation done in a notebook.
- `get_signal(df)`: parametrised test over (ADX, Mom1, Mom3, Mom12) tuples producing expected LONG/SHORT/FLAT.
- `calc_position_size(...)`: boundary cases — 0.12/RVol clip at 0.3 and 2.0, integer floor at n=1.
- `check_stop_hit(position, high, low, atr)`: LONG position with today's low below trail_stop → True; SHORT with today's high above trail_stop → True.
- `check_pyramid(position, current_price, atr_entry)`: +1×ATR from entry with level=0 → returns 1; +2×ATR with level=1 → returns 1; at level=2 → returns 0.
- `state_manager`: round-trip `load → modify → save → load` preserves every field; corrupted JSON triggers backup and re-init.

**What NOT to unit-test (integration only):**
- Yahoo fetch (mock `yfinance.download` or fixture a saved DataFrame).
- Resend send (mock `requests.post`, assert payload shape).
- Scheduler loop (integration smoke with `--force-email`).

**Floating point:** use `numpy.testing.assert_allclose(actual, expected, rtol=1e-9)`, not `==`. Wilder's recursion accumulates tiny float error that varies across NumPy versions by ~1e-12.

### 8. Lockfile: requirements.txt (keep it)

**Decision:** `requirements.txt` with bounded version ranges. Confidence: HIGH.

**Why not uv / Poetry / Pipenv:**
- Spec mandates `requirements.txt`. Don't fight it.
- GitHub Actions + Replit both understand `requirements.txt` natively — `pip install -r requirements.txt` just works.
- For a 7-package app with no transitive conflicts, the marginal value of a resolver lockfile (exact pinned transitive graph) is low vs the cost of adding a new tool.
- If reproducibility becomes a concern later: run `pip freeze > requirements.lock` after a known-good install and commit that alongside, but keep `requirements.txt` as the editable top-level.

**When to reconsider:** if the dep count grows past ~15, or if a transitive conflict (yfinance pulling an older `curl_cffi` that fights with something else) causes a production break. Then `uv` is the 2026 choice — faster than pip, replaces pip-tools, and can emit `requirements.txt` for compatibility.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| yfinance | Alpha Vantage (free tier 25 calls/day) | Yahoo changes `^AXJO` symbol or rate-limits daily. 25/day covers 2 tickers × 1 run/day trivially. Needs API key. |
| yfinance | Alpaca (alpaca-py) | Never for this app — no ASX index coverage, no FX. Only relevant if project scope expands to US equities. |
| yfinance | Polygon.io | Paid tier only for ASX — ignore. |
| hand-rolled TA | `ta` library (bukosabino) | If the hand-rolled ATR/ADX takes >4h to get right and test against a reference. Otherwise hand-roll wins. |
| hand-rolled TA | TA-Lib (C-extension) | Never on Replit (build pain). Only if project later needs 20+ indicators. |
| `schedule` | APScheduler | If requirements evolve to multiple jobs, persistent misfire tracking, or intraday cadence. |
| `schedule` in Python | System cron (Linux) | Only if running on a dedicated always-on Linux box (not Replit, not GHA). |
| `requests` for Resend | `resend` Python SDK | If Resend adds webhooks, batch sends, or attachments that the SDK handles and raw HTTP doesn't expose cleanly. |
| GitHub Actions | Replit Scheduled Deployment | If Marc wants a persistent dashboard URL and is willing to use Object Storage for state. |
| GitHub Actions | Fly.io tiny VM | If GHA cron delays become unacceptable and Marc wants sub-minute scheduling precision. Not this app. |
| pytz | `zoneinfo` (stdlib, Py3.9+) | Any new project. Here: spec mandates pytz and Perth has no DST so the two are functionally identical — stick with spec. |
| requirements.txt | `uv` + `pyproject.toml` | If the dep graph grows or transitive resolution becomes painful. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `pandas-ta` (twopirllc) | Canonical repo signalled archival by July 2026; no blessed successor; community forks fragmented | Hand-roll ATR/ADX — 60 lines, trivially testable |
| `pandas-ta-classic` / fork-of-the-week | Forks are community-maintained with no release cadence guarantee | Hand-roll |
| `TA-Lib` (C wrapper) | Needs system C library (`brew install ta-lib` / `apt-get install libta-lib-dev`) — Replit and GHA both workable but adds friction for 3 indicators | Hand-roll |
| `resend` Python SDK | Extra dep for a single `POST` with a Bearer token; lags the Node SDK in features | `requests` directly |
| APScheduler | Overkill for one daily job; more config surface for subtle misfire bugs | `schedule` (in-process) or GHA cron (cloud) |
| `yfinance<0.2.65` | Mid-2025 versions had rate-limit regressions and session-object breakages | Pin `>=0.2.65,<0.3` |
| `Flask` / `FastAPI` / `Django` | Spec forbids HTTP frameworks; the dashboard is a static file, no server needed | `dashboard.html` generated by `dashboard.py` and served statically |
| `SQLite` / `Postgres` / `Redis` for state | Spec mandates single `state.json`; adds operational complexity | `state.json` with atomic write (`write to .tmp → os.replace`) |
| Replit Autoscale for the scheduler | Scales to zero between requests — scheduler can't stay alive between invocations | Replit Reserved VM OR Scheduled Deployment OR GHA cron |
| Chart.js ESM build in a classic `<script>` tag | `import` statement outside module → SyntaxError, blank chart | UMD build: `dist/chart.umd.js` |
| `<script src=".../chart.js"></script>` (ambiguous path on jsDelivr) | Resolves to ESM on some CDNs, UMD on others | Explicit: `https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js` |
| `datetime.datetime.utcnow()` | Deprecated in Python 3.12+; returns naive UTC | `datetime.datetime.now(pytz.timezone('Australia/Perth'))` or `datetime.datetime.now(datetime.UTC)` |
| `==` for float comparison in tests | Wilder's recursion gives 1e-12 variance across NumPy versions | `numpy.testing.assert_allclose(actual, expected, rtol=1e-9)` |
| `subprocess.check_output("git commit ...")` in a Python script to push state on GHA | Flaky; missing auth token | `stefanzweifel/git-auto-commit-action@v5` step in the workflow yaml |

---

## Stack Patterns by Variant

**If running on Replit (interactive / dev):**
- `main.py` runs with `schedule` loop; Replit "Run" button starts it.
- Use Replit Secrets tab for `RESEND_API_KEY`, `TO_EMAIL`, `FROM_EMAIL`.
- For persistent scheduling: Reserved VM Deployment (Background Worker option) — $7+/mo.
- Back up `state.json` to a gist or sibling repo via a daily git push to mitigate Replit's filesystem non-guarantee.

**If running on GitHub Actions (production recommended):**
- No `schedule` loop — `main.py` runs once and exits.
- `.github/workflows/daily-signal.yml` with `on.schedule: - cron: '0 0 * * 1-5'` (08:00 AWST, weekdays).
- Secrets: `RESEND_API_KEY`, `TO_EMAIL`, `FROM_EMAIL` in GitHub repo → Settings → Secrets and Variables → Actions.
- Commit `state.json` back via `stefanzweifel/git-auto-commit-action@v5` after the run.
- Add a manual `workflow_dispatch:` trigger so Marc can run immediately from the Actions UI.
- Mitigate the "inactive repo pauses schedule" GitHub behaviour by having the workflow itself commit state.json (counts as activity).

**If running locally (dev):**
- `python main.py --test` sends a TEST email with current signals, doesn't mutate state.
- `python main.py --reset` zeroes state.
- `python main.py --force-email` runs full flow and sends regardless of schedule.
- `.env` loaded via `python-dotenv`.

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| yfinance 0.2.65+ | pandas 2.2.x, numpy 1.26+ OR 2.0+ | yfinance transitively pulls `curl_cffi`, `lxml`, `multitasking` — let pip resolve. |
| pandas 2.2.x | numpy 1.26+ OR 2.0+ | pandas 2.2 supports both NumPy 1 and 2. |
| numpy 2.0+ | Python 3.9+ | Fine on 3.11. |
| schedule 1.2.x | Any Python 3.7+ | Pure-Python, no surprises. |
| requests 2.32.x | urllib3 2.x | Already the yfinance transitive. |
| pytz 2024.1 | Any Python | Rolling date database; update yearly. |
| Chart.js 4.4.6 | Browsers shipped 2022+ | ES2017 baseline; Safari 14+, Chrome 94+. Fine for any browser Marc uses. |
| Python 3.11 | All of the above | Replit and GHA `actions/setup-python@v5` both default-support 3.11. |

**Known gotchas to avoid:**
- Do not mix `numpy<1.26` with `pandas>=2.2` — you'll get `ImportError: numpy.core.multiarray failed to import`.
- Do not use `yfinance` with a custom `requests.Session` without reading the 0.2.59+ changelog — session handling changed twice in 2025.

---

## Sources

- [yfinance on PyPI (v1.3.0, April 2026)](https://pypi.org/project/yfinance/) — confirmed current version and async/websocket additions. HIGH confidence.
- [resend on PyPI (v2.29.0, April 2026)](https://pypi.org/project/resend/) — confirmed Python SDK version; informed the "use requests instead" call. HIGH confidence.
- [Replit — Reserved VM Deployments](https://docs.replit.com/cloud-services/deployments/reserved-vm-deployments) — Background Worker option for schedulers. HIGH confidence.
- [Replit — Autoscale Deployments](https://docs.replit.com/cloud-services/deployments/autoscale-deployments) — scale-to-zero warning for persistent processes. HIGH confidence.
- [Replit — Scheduled Deployments announcement](https://blog.replit.com/scheduled-deployments) — 1-min granularity, 11-hour max, cron alternative. MEDIUM confidence (product details shift).
- [Chart.js v4 CDN & UMD issue discussion](https://github.com/chartjs/Chart.js/discussions/11219) — UMD vs ESM build pitfall in static HTML. HIGH confidence.
- [Chart.js Getting Started](https://www.chartjs.org/docs/latest/getting-started/) — official build guidance. HIGH confidence.
- [yfinance issue #2567 — Rate limit 2025](https://github.com/ranaroussi/yfinance/issues/2567) — informed the `>=0.2.65` pin. MEDIUM confidence (ongoing).
- [yfinance issue #2496 — session object breaking change](https://github.com/ranaroussi/yfinance/issues/2496) — informed the "don't pass custom Session without checking" gotcha. MEDIUM confidence.
- [Scheduling Tasks in Python: APScheduler vs Schedule (Leapcell)](https://leapcell.io/blog/scheduling-tasks-in-python-apscheduler-versus-schedule) — confirmed `schedule` is the simpler choice for single-job daemons. MEDIUM confidence (blog source, consistent with library docs).
- [GitHub Actions cron delay discussion #156282](https://github.com/orgs/community/discussions/156282) — up-to-60-min delay on cron triggers. MEDIUM confidence.
- [git-auto-commit-action discussion #349](https://github.com/stefanzweifel/git-auto-commit-action/discussions/349) — pattern for committing state back from scheduled workflows. HIGH confidence.
- [pandas-ta fork landscape (PyPI + GitHub forks)](https://github.com/Pandas-Quant-Finance/pandas-ta) — fragmented successor ecosystem; informed the "hand-roll" decision. MEDIUM confidence.
- [Resend Python SDK docs](https://resend.com/docs/send-with-python) — confirmed the SDK is a thin wrapper around the REST call. HIGH confidence.
- [Resend Python SDK on GitHub](https://github.com/resend/resend-python) — verified feature parity. HIGH confidence.

---

*Stack research for: Python quant / mechanical trading signal app (Trading Signals — SPI 200 & AUD/USD Mechanical System)*
*Researched: 2026-04-20*
