# Pitfalls Research — v1.3 Multi-Tenant Friends & Family

**Domain:** Adding invite-only multi-tenancy + per-user file state + per-user email + yfinance news + first-run tour to an existing single-operator file-based hex-lite FastAPI/HTMX trading-signal app (Python 3.11, yfinance, Resend, JSON state, no DB, no SPA).
**Researched:** 2026-05-10
**Confidence:** HIGH on the multi-tenant scoping, atomic-write, FastAPI ordering, Resend, and migration items (project-local LEARNINGS plus universal `~/.claude/LEARNINGS.md` G-20…G-53 series, plus v1.0-archive PITFALLS already validated in production). MEDIUM on yfinance `Ticker.news` schema/rate limits (library churn) and on tour/HTMX swap interactions (depends on the exact tour library chosen). Where MEDIUM, the prevention is "freeze a snapshot at planning time and re-verify before merge".

This document is **incremental** to `.planning/research/v1.0-archive/PITFALLS.md`. Pitfalls 1–20 there (yfinance, ATR/ADX, atomic write, Resend deliverability, GHA race, etc.) are still in force and not repeated here. The pitfalls below are the **new surface area** v1.3 introduces.

---

## Critical Pitfalls

The "silently wrong, silently unsafe, silently useless" tier — for v1.3 these almost all collapse to **cross-tenant data leak** or **partial fan-out**. A signal-only app where a F&F user sees admin's positions is just as broken as one that places live trades.

---

### Pitfall 21: Bolt-on `user_id` route param creates classic CWE-639 IDOR

**What goes wrong:**
v1.0–v1.2 routes are operator-only — `/trades/{id}/close` does not check ownership because there is only one operator. v1.3 adds `user_id` to the URL or the trade row. Implementer adds `user_id` on **write** (`save_trade(user_id, payload)`) but the **read/mutate** path still does `state["paper_trades"][trade_id]` without verifying `paper_trades[trade_id].user_id == current_user.id`. Any authenticated F&F user can `PATCH /paper-trades/<other-user-uuid>` and mutate another user's trade.

**Why it happens:**
Adding tenancy to a single-tenant app is a **systemic gap**: every route that takes an entity ID from the client must verify the entity belongs to the requester. TypeScript-style "looks like it has tenant" checks pass review because `user_id` is *written*, but the *lookup* still uses the raw ID. This is `~/.claude/LEARNINGS.md` G-20 ("every query-by-userId must also filter by tenantId") and the global "tenantId on output is necessary but not sufficient" rule.

**How to avoid:**
- Centralize entity loads behind `load_trade_for_user(trade_id, user_id) -> Trade | NotFound` that returns `NotFound` (not `Forbidden`) on cross-user access — never expose the existence of another user's record.
- Default route signature: every mutating handler depends on `current_user: User = Depends(get_current_user)` AND every entity lookup goes through the centralized loader. No raw `state["paper_trades"][id]` outside the loader.
- Test: for every route that takes an entity ID, write a paired test `test_<route>_returns_404_for_other_users_entity` — create user A's row, authenticate as user B, hit the route, assert 404.
- Grep gate: `grep -rn "state\[" src/web/routes/ src/state_manager.py | grep -v "current_user\|user_id"` — every match in a route handler is suspect.

**Warning signs:**
- A route accepts a UUID/path-id from the client and the handler body never reads `current_user.id`.
- Test file lacks "other user" cases; only happy path is exercised.
- Centralized `load_X_for_user` does not exist; per-route ad-hoc `state[...]` reads.

**Phase to address:**
Multi-tenant refactor phase (state_manager rewrite). The IDOR test sweep is a **mandatory exit criterion** for that phase — do not move on to per-user email or news until every route has its 404-for-other-user test.

---

### Pitfall 22: Admin-vs-user boundary check missing on a single new route (the "one weak link")

**What goes wrong:**
`/admin/users` and `/admin/invite` are gated on `current_user.role == "admin"`. A new convenience endpoint added later (e.g. `/admin/users/{id}/state-snapshot` to debug F&F state) is accidentally only gated on `Depends(get_current_user)`, not `Depends(require_admin)`. Any F&F can hit it and read another user's full state. The check is missing on **one** route; the other 17 are fine. CI is green because the route has tests for the happy path (admin can call it) but no test asserting non-admin gets 403.

**Why it happens:**
FastAPI dependency injection is per-route — `Depends(require_admin)` must be added to **every** admin route individually. There is no global `requires_admin` decorator on the router unless explicitly mounted that way. This mirrors `~/.claude/LEARNINGS.md` G-23 ("middleware x-tenant-id must be stripped on non-tenant paths") — defense-in-depth on a per-route basis is fragile.

**How to avoid:**
- **Mount admin routes as a sub-router** with the dependency baked in: `admin_router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])`. Every route registered on `admin_router` inherits the gate. New routes added by future-you cannot forget it.
- Add a startup-time invariant test that walks `app.routes`, filters paths starting with `/admin`, and asserts every one of them has `require_admin` in its dependency chain.
- Test pattern: parametrize a single test over every admin route — `@pytest.mark.parametrize("path", admin_paths)` then assert F&F user gets 403/404 on each.
- Grep: `grep -rn "@.*\.\(get\|post\|patch\|delete\)" src/web/routes/admin_*.py` — every match must be inside a router that has `Depends(require_admin)` mounted.

**Warning signs:**
- Each admin route has its own `Depends(require_admin)` line copy-pasted (suggests one will be missed).
- No "non-admin gets 403" parametrized sweep test.
- New routes added in mid-phase commits without a corresponding negative test.

**Phase to address:**
RBAC phase (admin namespace separation). Sub-router pattern locked in the **first** task of the phase — cheaper to enforce on day 1 than retrofit.

---

### Pitfall 23: Privacy regression — admin user-list view leaks F&F trade content via shared template

**What goes wrong:**
Admin user list renders `<tr>` per user. To show "last activity" the developer reuses the existing trade-row partial which renders `entry_price`, `direction`, `n_contracts`. Admin now sees F&F position content despite the project's locked privacy constraint ("admin sees user list + invite/revoke only, never F&F trade content"). Logs leak the same way: a debug `logger.info("user state: %s", user_state)` in the daily fan-out dumps every user's positions to the systemd journal where admin (and any process with journal read) can see them.

**Why it happens:**
Reuse-by-default of partials/templates from v1.2 (where there was only one user, so trade content == admin content). The privacy rule was a v1.3 layer added on top of an architecture that didn't have the concept. Logs are the most common privacy regression channel because nobody reviews log content the way they review templates.

**How to avoid:**
- Define a **`PublicUserSummary`** Pydantic model with only `{user_id, display_name, status, last_seen_date, has_active_position: bool}` — nothing else. The admin list route returns `list[PublicUserSummary]`, not `list[User]` or `list[State]`. Same for crash-email content (Pitfall 26).
- Per-user log redaction: every `logger.info(...)` in the fan-out pipeline must use a structured field name from an allowlist (`event`, `user_id`, `signal_as_of`, `rc`). Anything else gets redacted by a logging filter. Concretely: a `RedactStateFilter` installed at module load that walks log records and replaces `paper_trades`, `equity_history`, `entry_price`, `n_contracts`, `journal` with `<redacted>`.
- Privacy test: render the admin user list with a fixture user holding 5 paper trades; assert the rendered HTML does **not** contain any of `entry_price`, `direction`, the trade UUID, or any per-trade dollar value. Grep the response body — single regex `(entry_price|n_contracts|"direction":\s*"(LONG|SHORT)")` returning zero matches.
- Crash-email test: trigger a panic in the fan-out, assert the resulting email body does not contain user trade content (only counts and user ids).

**Warning signs:**
- Admin templates `{% include "trade_row.html" %}` from F&F-context partials.
- `logger.info("...%s...", state)` or `print(state)` anywhere in the fan-out.
- Crash email content includes `_LAST_LOADED_STATE` snapshot for the failing user.

**Phase to address:**
Multi-tenant refactor phase (write `PublicUserSummary` + redaction filter on the same task as the `state_manager` rewrite). Re-verified in admin-UI phase. Do **not** ship admin user-list view without the privacy-grep test green.

---

### Pitfall 24: Per-user file write fan-out is N serial writes — partial failure leaves N/2 users stale and admin doesn't know

**What goes wrong:**
Daily 08:00 cycle iterates `for user_id in active_users: compute(user_id); save_state(user_id, state)`. User #14's state is malformed (legacy field, schema mismatch, disk full, atomic rename race with a concurrent HTMX trade write). The fan-out throws on user #14. The loop crashes. Users #1–13 got fresh state + email, users #14–N got nothing — no email, no state update, dashboard shows yesterday's data, stop-loss alerts didn't fire. Admin email lands as normal so admin doesn't know N/2 of F&F are stale.

**Why it happens:**
Single-loop fan-out is the natural shape and was fine for one operator. With N users it's a partial-failure cliff: any single user's bad state aborts the cycle, and there is no per-user crash boundary. This is the global "fire-and-forget async swallows errors" pattern lifted into a sync fan-out: silent partial failure where the apparent success of users 1–13 masks the full-cycle break.

**How to avoid:**
- **Per-user crash boundary.** Wrap each user's pass in `try/except: logger.exception(); record_failure(user_id, exc); continue`. The cycle completes for every user; failures are aggregated.
- Emit a **summary email to admin** at the end of every cycle: "fan-out complete: 23 ok, 2 failed (alice@…, bob@… — see attached)". Admin must be told within the same ~1h window, not next day.
- Per-user state writes share the same atomic-write contract (tempfile + fsync + os.replace) but **into per-user paths** (`state/users/{user_id}.json`). One user's mid-write crash does not corrupt another's file.
- Test: run fan-out with one user's state intentionally malformed (raises in compute). Assert: (a) all other users' states updated, (b) admin gets a summary email naming the failed user, (c) the failed user's previous state is untouched (not corrupted to half-written), (d) rc != 0 from the cycle so systemd records a non-zero exit.
- Health probe: a lightweight endpoint `/healthz/last-cycle` that returns the last cycle's per-user success/fail counts so the admin can spot-check from anywhere.

**Warning signs:**
- Single `try/except` wrapping the whole fan-out loop.
- Admin email succeeds but F&F emails are missing — admin doesn't notice because their own pipe is unaffected.
- `state/users/<id>.json` mtime stops advancing for some users while others advance.
- Logs show "Daily run complete" once per cycle, not once per user.

**Phase to address:**
Per-user email pipeline phase (the natural place for the fan-out architecture). The per-user crash boundary is **mandatory** before the news phase or the tour phase — those phases compound the surface area.

---

### Pitfall 25: Atomic-write contract violation under concurrent admin daily-fan-out and live HTMX trade submission

**What goes wrong:**
At 08:00:03 the daily cycle is mid-write of user `alice`'s state file (tempfile created, fsynced, about to `os.replace`). At 08:00:03.7, alice (in Europe, awake) submits a paper-trade close via HTMX. The HTMX route reads `alice.json`, modifies, and atomic-writes. Two writers race. `os.replace` is atomic on POSIX so no corruption — but one write **logically clobbers** the other. If the daily cycle wins, alice's just-submitted trade is silently dropped (her HTMX response said success). If alice wins, the daily cycle's stop-loss-alert state-machine update is lost — tomorrow she'll get an "APPROACHING" alert that should have transitioned to "HIT" today.

**Why it happens:**
v1.0–v1.2 had a single writer (the daily process; HTMX writes only happened post-v1.1 and the operator was assumed not to be filing trades at 08:00 sharp during the cron tick). With N users in N timezones, the live-write window is now 24/7 and the daily fan-out is an extended window (N users × ~1s each = up to N seconds where each user's file is in flight). The "sole writer" invariant from v1.0 STATE.md is now violated by design.

**How to avoid:**
- **Per-user advisory lock file.** Each user's state-mutation path acquires `flock(LOCK_EX)` on `state/users/{user_id}.lock` before the read-modify-write. fan-out and HTMX both use the same lock helper. flock is per-process on Linux but works across the FastAPI worker(s) and the systemd daily process.
- Alternative: **single-writer channel** — HTMX writes enqueue intent (`state/users/{user_id}.queue.jsonl`) and a single state-writer process drains the queue. Heavier but cleaner; only worth it if flock proves flaky.
- Hold the lock for the full read-modify-write, not just the write. A read-then-write without holding through both is still a TOCTOU race.
- Test: spawn 50 threads, each randomly either runs `daily_compute(user_id)` or simulates an HTMX trade-add for the same user. Assert: final state is internally consistent (every recorded trade is in the trade_log), no exceptions, no half-written `.tmp` files left behind.
- Test: kill the daily process during the lock-held window (SIGKILL between read and write); next HTMX request must be able to acquire the lock (lock released on fd close) and proceed.

**Warning signs:**
- HTMX `POST /paper-trades` returning 200 but the trade not visible after refresh.
- `state/users/{id}.json.tmp.<pid>` files left over in the data dir.
- Stop-loss alert state machine "stuck" at APPROACHING for one user across two cycles (the second cycle's update was clobbered by an HTMX write).

**Phase to address:**
Multi-tenant refactor phase (state_manager rewrite). The lock helper is the **first task** of that phase — every later phase that adds a writer (per-user email, news refresh, journal mutation) inherits it. Do not skip the kill-during-lock test.

---

### Pitfall 26: Crash-email + `_LAST_LOADED_STATE` cache leaks the wrong user's state

**What goes wrong:**
v1.0 introduced a module-level `_LAST_LOADED_STATE` cache so the crash-email handler can summarize current positions even when state is unloadable at crash time. In v1.3, the daily fan-out loads alice's state (cache := alice), processes alice, loads bob's state (cache := bob), starts processing bob, crashes inside bob's compute. Crash email fires — but the email **goes to admin** (the operator) and leaks **bob's positions** in the body. Worse: if the crash is in alice's email-send step (post-state-load for alice, pre-load for bob), the cache is alice and the email sent to admin describes alice's state — admin sees alice's content, violating privacy.

**Why it happens:**
v1.0 D-08 explicitly flagged `_LAST_LOADED_STATE` as "Revisit if parallel runs appear (v2)" — multi-tenant fan-out is exactly that revisit. The cache assumes there is only one state ever in flight. The crash-email body assumes the cached state is "the operator's state" because there has only ever been one operator.

**How to avoid:**
- **Scope the cache to the current user being processed**, or kill it. Two options:
  1. Make `_LAST_LOADED_STATE` a `dict[user_id, state]` and have the crash handler iterate to identify "which user was being processed" (use a contextvar like `current_processing_user`).
  2. Drop the cache. Instead, write a one-line `last_processed.txt` file at the start of each user's compute (`{user_id, started_at, phase}`) and the crash handler reads that. Simpler, no cross-user leak risk because the file only ever names one user at a time.
- **Crash email never includes trade content.** It includes `user_id`, `phase`, `exception class`, and a stack trace — never positions, equity, journal entries. Reuse `PublicUserSummary` from Pitfall 23.
- Test: monkeypatch `daily_compute` to raise after processing user A but while cache is still A's state. Assert crash email goes to admin, body contains "user_id=A", body does **not** contain any of A's `entry_price`, `direction`, `equity`. Run again with the crash inside B — assert body names B, not A.

**Warning signs:**
- Crash email body contains dollar amounts, position sizes, or trade UUIDs.
- After a fan-out crash, admin receives an email describing positions that aren't admin's.
- `_LAST_LOADED_STATE` is referenced anywhere outside `notifier/crash.py`.

**Phase to address:**
Multi-tenant refactor phase. Same locality as Pitfall 25 — both stem from the v1.0 single-writer assumption. The redacted-crash-email test is the gate.

---

### Pitfall 27: Schema v9 → v10 migration crashes mid-flight, leaves state half-migrated

**What goes wrong:**
v1.3 schema bumps from v9 to v10 to (a) add `user_id` to every signal/trade row and (b) restructure `state.json` from "operator object" to "namespace per user". The migration runs at module load (per `_migrate_chain` contiguity assert from v1.2 Phase 27). It rewrites state in-place and saves. Process is killed mid-migration (SIGKILL during deploy, OOM during a big admin state, GHA timeout). Half the rows have `user_id`, half don't. Next start: the migration walker thinks state is at v10 (because `schema_version` was bumped before the row backfill finished, or because the half-state passes the v10 shape check), and proceeds to read with v10 readers — which crash on the v9-shaped rows. App is dead until manual intervention.

**Why it happens:**
The atomic-write contract (Pitfall 13 from v1.0) covers the *file*, not the *migration logic*. A migration that does `state["schema_version"] = 10; for row in state["trades"]: row["user_id"] = "admin"; save_state(state)` can mutate the in-memory state, save partially-mutated state, and fail before completing. Even with atomic file writes, the *logical* migration is non-atomic across the rows. This compounds with `~/.claude/LEARNINGS.md` G-36 (defensive-read for partial migrations).

**How to avoid:**
- **Migration is all-or-nothing per save.** Build the v10 state in a fresh dict, validate it (Pydantic round-trip), and only then call `save_state(new)`. Never mutate the existing state in place.
  ```python
  def _migrate_v9_to_v10(old: dict) -> dict:
      new = {"schema_version": 10, "users": {}, ...}
      for tid, trade in old.get("paper_trades", {}).items():
          new["users"]["admin"]["paper_trades"][tid] = {**trade, "user_id": "admin"}
      v10_State.model_validate(new)  # raises if shape wrong
      return new
  ```
- **Backup before migration.** `cp state.json state.v9-backup-{timestamp}.json` is automatic at the start of any migration step. Survives the entire v1.3 ship plus the next year.
- **Defensive-read on the new fields** (G-36 pattern). Every reader of `row["user_id"]` checks `row.get("user_id", "admin")` for one release, then tightens after a deliberate cleanup phase. Prevents "the migration ran but a row was added before backfill completed" failures.
- **Migration round-trip test.** Take 5 real anonymized v9 state fixtures (admin's actual state at v1.2 close, plus 4 hand-crafted edge cases: empty trades, max trade_log, mid-pyramid, mid-alert-state APPROACHING, with naive datetime legacy strings). For each: `migrate(v9) → v10 → reverse_migrate(v10) → v9_prime`; assert `v9 == v9_prime` (round-trip lossless) AND `v10` validates against the v10 Pydantic model.
- **No "schema_version bumped first" pattern.** Build the new state, validate, save once with the new version stamped on it. If the build raises, the file is untouched.

**Warning signs:**
- Migration code that does `state["schema_version"] = N` early then mutates rows.
- No `state.v9-backup-*.json` in the data dir after a migration runs.
- Round-trip test missing or only covers happy path.
- App boots fine on dev fixture but crashes in prod with `KeyError: 'user_id'` on legacy rows.

**Phase to address:**
Multi-tenant refactor phase (the same task that introduces per-user namespace). The round-trip test is a hard exit gate; the backup is automated, not optional.

---

### Pitfall 28: Invite token vulnerabilities — predictable IDs, no expiry, replay, leak via referer

**What goes wrong:**
Admin-issued invite tokens are the only entry point for new F&F. Common implementations get one or more of these wrong:
- **Weak entropy:** `token = secrets.token_hex(8)` (only 64 bits) — guessable in <1 day at 1k/s scan; or, worse, `token = uuid.uuid4().hex` truncated, or a base36 of an autoincrement counter.
- **No expiry:** Token issued, never used, sits in `invites.json` forever. Admin's old laptop snapshot leaks the file → token still valid 2 years later.
- **Reuse:** Token is multi-use by accident — the consume step doesn't atomically mark `used_at`, so two browsers can both register on the same token. Race: invite for "alice@x.com" is consumed by attacker first, alice gets "token already used".
- **Leak via Referer:** Invite URL is `/signup?token=...`. User clicks, lands on signup page, the page loads a third-party CSS/font/analytics with the full URL in the `Referer` header. Token leaks to whoever hosts the asset. Even worse if the signup page renders a `<a target="_blank" href="...">` to a help page — `Referer` carries the token URL.
- **Constant-time compare missing:** Token check uses `if token_in_db == token_from_user:` — early-exit on first mismatch. Timing attack feasible for 16-char tokens at long-poll cadence.
- **Predictable IDs:** Invite ID `inv_001` increments. `/invite/inv_001` is the URL — anyone with the pattern can scan.

**Why it happens:**
Invite flows look "easy" (it's a CRUD form). All the failure modes above are individually well-known but stack: a 64-bit token with no expiry and no constant-time compare is roughly equivalent to "guessable within a month". For a single admin issuing tokens to friends, the perceived attack surface feels low; in reality the system is connected to a domain that already attracts crawlers.

**How to avoid:**
- **Token shape:** `secrets.token_urlsafe(32)` — 256 bits of entropy, URL-safe, no padding. Store only `sha256(token)` in `invites.json`; the token itself is never persisted server-side. Verification: hash the user-supplied token, compare via `hmac.compare_digest` (constant-time).
- **Expiry:** Default 7 days from issue. Hard cap 30 days (no "permanent invite" option). Expired invites are not deleted (audit trail) but are unusable.
- **Single-use:** Consume step is `flock` + check-and-set: under the lock, read `invites[hash]`, assert `used_at is None`, set `used_at = now`, save. Race-free.
- **Revocation atomicity:** Admin clicking "revoke" runs the same flock/check-and-set with a "revoked_at" stamp. If a consume request is already in-flight under the lock, it either completes first (revoke fails with "already consumed") or revoke wins (consume fails with "revoked"). One outcome, never both.
- **Referer leak prevention:** Add `<meta name="referrer" content="no-referrer">` (or `Referrer-Policy: no-referrer` header) on the signup page only. Strip the token from the URL after consume — issue a session cookie and `303 → /dashboard` so the URL bar no longer contains the token. Never log the raw token (logs include URL paths).
- **Invite ID is the same shape as the token** (or absent — only the token is the addressable handle). No `inv_001`.
- **Audit log:** Every invite event (issued, sent, consumed, revoked, expired) appends to `audit/invites.jsonl` with timestamp, admin user, target email (hashed if you want to be polite to F&F privacy, but admin sees plaintext locally).
- Test: `consume(token)` twice in parallel — one wins, one fails. Test: revoked token returns same 404 as never-issued token (don't leak existence). Test: 30-day-old token returns 404. Test: hashed token in `invites.json` does not contain the raw token.

**Warning signs:**
- `invites.json` contains plaintext tokens.
- No `expires_at` field on invite rows.
- Signup page is `/signup?token=...` and stays at that URL after rendering.
- Token equality uses `==` not `hmac.compare_digest`.
- Two test users can both register on one token.

**Phase to address:**
RBAC phase (invite-only). The audit log + flock atomicity are mandatory exit criteria; the referer-policy is part of the auth UX phase.

---

### Pitfall 29: yfinance `Ticker.news` schema drift, rate limits, and silently-different return shape across versions

**What goes wrong:**
v1.3 reads `yf.Ticker("^AXJO").news` (or `Ticker.get_news()`) for the news panel + critical-event flag. Pitfalls compound the v1.0 yfinance issues (Pitfall 1 from archive):
- **Schema drift:** Pre-0.2.40, news returned `[{"title", "publisher", "link", "providerPublishTime", "type", "thumbnail"}]`. Post-0.2.55, it's wrapped: `{"content": {"title", "summary", "pubDate", "clickThroughUrl": {"url"}, "thumbnail"}}`. A blind `item["title"]` crashes on the new shape; a blind `item["content"]["title"]` crashes on the old. The repo pins yfinance, but a drone-by `pip install -U` in dev breaks the page.
- **Rate limit:** `Ticker.news` shares the same Yahoo backend as `download()`. The daily cron already calls `download()`, then for each market calls `.news` — N markets × 2 calls = 4 calls per cycle just for news. Multiplied by per-user fan-out if news is fetched per-user (which it shouldn't be — news is shared, not per-user). At F&F scale of ~10 users, naive per-user fetch = 40 calls in tight succession → 429.
- **Importance hint absent or misleading:** Some yfinance builds expose `item.get("relatedTickers")` and a `provider`, but no explicit "importance"/"is_critical" flag. The brief assumes one exists. If absent, the entire critical-event-flag feature falls back to keyword fallback alone — silently. A field that *was* present in 0.2.50 may have been removed in 0.2.55 with no release-notes mention.
- **Unicode in headlines:** Headlines containing curly quotes, em-dashes, non-Latin tickers (`日経`), accented names break HTML escape if the renderer uses `str.replace` instead of `html.escape`. Worse: characters that look like HTML (`<rant>`) render as broken HTML.
- **News links are SSRF-shaped if proxied:** Spec doesn't proxy the link, but if a future "fetch summary" feature fetches `item["link"]`, that's a server-side request to a URL the user (and Yahoo) controls. CWE-918. Links to `http://169.254.169.254/...` (cloud metadata) or `http://localhost:8080/admin` are real risks.
- **News XSS via raw render:** Headline `<script>alert(1)</script>` rendered into the dashboard via Jinja `{{ item.title|safe }}` is XSS. The dashboard already has API-key redaction (Phase 27) so the rest of the app is escaped — but a new news partial is the easy place to forget.
- **Caching staleness vs freshness:** Naively re-fetching news on every dashboard page-load hits the rate limit. Caching for 24h means stale news shown all day even when something material happens at 14:00. Caching with no TTL means tomorrow shows yesterday's news.

**Why it happens:**
yfinance is a scraper — schema is whatever Yahoo's HTML/JSON returned at the version's release time. Versions 0.2.40 → 0.2.55 had multiple shape changes per the GitHub issues. Library's own examples in the README do not include defensive shape handling.

**How to avoid:**
- **Adapter layer with normalized output:** `news_adapter.fetch(market) -> list[NewsItem]` returns a Pydantic `NewsItem(title: str, source: str, url: HttpUrl, published_at: datetime, summary: str | None)`. Internal: try the post-0.2.55 shape first, fall back to pre-0.2.55 shape, raise `NewsSchemaError` on neither. Test the adapter against two committed JSON fixtures (one per shape).
- **Pin yfinance and re-verify on bump.** `requirements.txt` pins exact version. Any bump must rerun the news adapter test against fresh fixtures captured from `Ticker.news` at the new version.
- **Single fetch per cycle, shared across users.** News is per-market, not per-user. Fan-out reads from `state/news_cache_{market}.json` instead of refetching. TTL: 4h during market hours, 24h overnight, with a manual "refresh" button on admin only.
- **HTML escape every interpolation.** Use Jinja's default autoescape (`Environment(autoescape=True)`) and never use `|safe` on news fields. Test: render a news item with `title="<script>alert(1)</script>"`; assert the response body contains `&lt;script&gt;`, not `<script>`.
- **No URL fetching of `item.link`.** Display only — `<a href="{{ url }}" rel="noopener noreferrer" target="_blank">`. If a future feature wants to fetch, gate behind SSRF check (resolve hostname, block private/loopback/metadata IP ranges, HTTPS-only).
- **Importance hint optional, keyword fallback is the floor.** Adapter exposes `is_critical: bool` computed as `(yfinance_importance == "high") or any(kw in title.lower() for kw in CRITICAL_KEYWORDS)`. If yfinance hint is absent, fall back to keyword alone — never crash. Log a counter "news_with_importance_hint" once per cycle so we notice when Yahoo removes the field.
- **Cache contract:** `news_cache_{market}.json` has `{fetched_at, ttl_seconds, items}`. Reader returns `items` if `now - fetched_at < ttl_seconds`, else triggers a single refetch (lock-protected, so concurrent dashboard loads don't all refetch). Fetched items always include `cached_at` so the dashboard can show "as of 12:34" honestly.
- Test: golden-file fixtures of both schemas, each parsed by the adapter, assert normalized output shape.
- Test: rate-limit simulation — adapter mocked to raise 429 on 4th call; assert dashboard shows "news temporarily unavailable" not 500.

**Warning signs:**
- `item["title"]` (or `item["content"]["title"]`) is direct, no fallback.
- News fetched in the per-user fan-out loop (one fetch per user).
- News links rendered without `rel="noopener noreferrer"`.
- Dashboard XSS by pasting `<script>` into a fixture title — actually executes.
- 429 errors in logs after a cycle.

**Phase to address:**
News integration phase. Adapter + fixtures + autoescape test are mandatory before the critical-event flag (Pitfall 30) is wired.

---

### Pitfall 30: Critical-event flag false positives ("rate" matches "first-rate") and false negatives (RBA day with no keyword)

**What goes wrong:**
Hand-curated keyword fallback has the classic substring-matching trap:
- **False positive:** `"rate"` matches `"first-rate quarter"`, `"company rates highly"`, `"Moody's rates AAA"`. Every routine business article triggers the critical-event banner. Users learn to ignore it. Real critical events are missed.
- **False negative:** RBA decision day, headline reads "Reserve Bank holds steady at 4.35%". No `"rate"`, no `"FOMC"`, no `"hike"`. Banner stays silent. Operator misses the trade-relevant event.
- **Banner persists past event:** Critical news fetched at 09:00 stays "critical" all day. By 16:00 the news is stale but the banner is still red.
- **Banner dedup across reloads:** User reloads dashboard — banner reappears every reload even though they've seen it. No "dismiss" affordance, or dismiss state is per-tab not per-user.
- **Per-user dedup state writes** add a fan-out write contention point (Pitfall 25 again).

**Why it happens:**
Substring matching on free-form headlines is fundamentally noisy. Word-boundary fixes most false positives but not all (`"interest rate"` vs `"interest rates"` — both match `\brate(s)?\b`, fine; but `"first-rate"` matches `\brate\b` only with naive regex). False negatives are unfixable without a real classifier — the long tail of phrasings is infinite.

**How to avoid:**
- **Word-boundary regex, not substring:** `re.compile(r"\b(?:rate|FOMC|RBA|inflation|CPI|GDP|hike|cut)\b", re.IGNORECASE)`. Document each keyword with a comment explaining why it's there.
- **Multi-keyword threshold:** require ≥2 keywords for critical, OR the yfinance importance hint, OR a domain-specific match (e.g. "RBA" alone is enough). Single-keyword triggers like `"rate"` go to "moderate" not "critical".
- **Allowlist of dampeners:** if title contains `"first-rate"`, `"second-rate"`, `"third-rate"`, downgrade. Cheap and catches the common false positives.
- **Time-bounded:** banner only shows for items < 24h old. After 24h, the item is in the "today's news" panel but no banner.
- **Per-user "dismiss" state in the user's state file** — `dismissed_news_ids: list[str]`. Adding to this list via HTMX uses the same flock as paper-trade writes (Pitfall 25). Dismiss persists across reloads.
- **Banner shows "N critical news" with the count, not the headline** — clicking expands. Reduces visual fatigue while preserving the alert.
- Test: parametrized over a curated 30-headline fixture set (hand-labeled critical / not-critical), assert the classifier's precision ≥ 0.7 and recall ≥ 0.9. Concrete fixtures: include "first-rate quarter", "RBA holds steady", "Fed cuts rates 50 bps", "ASX trades flat" — known precision/recall edges.
- Test: per-user dismiss persists; user A's dismiss does not affect user B.

**Warning signs:**
- Banner is red on >30% of dashboard loads (over-firing).
- RBA decision days come and go with no banner (under-firing).
- Banner reappears after dismiss + reload.
- User A and user B see different banners for the same news (suggests per-user state is leaking news content).

**Phase to address:**
News integration phase, after the adapter (Pitfall 29). The classifier and the dismiss flow are separate tasks; do not merge them into one — the classifier's quality should be evaluated against fixtures before it's wired to UI.

---

### Pitfall 31: Per-user email fan-out — Resend rate limit, deliverability degradation, address validation

**What goes wrong:**
At 08:00:00, the cycle dispatches N emails to Resend in tight succession (N = F&F count + admin). Issues:
- **Resend rate limit:** Resend's default rate limit is 2 req/s per API key (verify current limit at planning time — has been 10/s historically; documented threshold has changed). At 10 users in 1 second, half get 429. Retry logic fires, doubles the load, some users get duplicate emails.
- **Deliverability degradation:** Sender reputation drops if N=20+ emails go out in <1 minute from one domain (looks bursty). Gmail+Outlook spam-classify the next morning's batch.
- **Per-user link tokens leak via email forwarding:** Email contains a magic-link "view dashboard" URL with a session token. User forwards email to spouse. Spouse clicks, gets logged in as the original user. (This is an existing v1.1 magic-link risk amplified by F&F.)
- **Unicode in `to` field display name:** F&F user "Müller" — `formataddr(("Müller", "muller@x.com"))` works; raw `f'"{name}" <{email}>'` does not (BOM, non-ASCII gets dropped or replaced with `?` by some MTAs).
- **Unsubscribe link missing → spam-trap:** F&F can't opt out of daily emails without admin intervention. Gmail's "report spam" is the available alternative; one user reports → sender domain reputation hit for everyone.
- **Per-user link tokens invalidated on session regen** (admin password change rotates secret) — every F&F user's existing magic-link in their inbox stops working silently.
- **Resend dashboard shows "delivered" but inbox empty** (Pitfall 14 from v1.0 archive — verify SPF/DKIM still aligned for the F&F volume).

**Why it happens:**
v1.0–v1.2 sent 1 email per cycle. v1.3's volume is N. Email infrastructure punishes bursts. Magic-link reuse via forwarding is a privacy failure mode that single-operator never had.

**How to avoid:**
- **Throttle the fan-out:** dispatch with `asyncio.Semaphore(2)` (or whatever Resend's documented limit is at ship time minus 50%). Stagger over 30s, not 1s. At F&F scale (≤20 users) this is invisible to any user.
- **Burst budget:** if cycle hits >5 emails, log a warning. v1.3 ships with N≤20 cap on F&F count to keep this sane. Increase deliberately, not silently.
- **Use Resend's batch send API** if available (one HTTP request, multiple recipients with per-recipient personalization). Reduces rate-limit pressure dramatically.
- **List-Unsubscribe header (RFC 8058):** every email includes `List-Unsubscribe: <mailto:unsubscribe@signals.mwiriadi.me>, <https://signals.mwiriadi.me/unsubscribe?token=...>` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click`. F&F can unsubscribe from Gmail's UI without "report spam".
- **`unsubscribe_token` is per-user, signed, and one-purpose** (cannot be used to log in). Separate from the session/magic-link token.
- **Forwarding-resistant email content:** never embed a clickable session-token URL in the email body. Instead embed a "go to dashboard" link to the bare login page (no token). The user logs in there with their existing session/2FA. (Magic-link recovery stays opt-in and rate-limited.)
- **`formataddr`-style rendering:** use stdlib `email.utils.formataddr((display_name, address))` which does the right MIME-encoding for Unicode names.
- **SPF/DKIM/DMARC re-verify** on the day v1.3 ships — re-run the Resend dashboard's domain-verification check.
- **Per-user opt-in confirmed double-opt:** F&F dashboard toggle "send me daily emails" only takes effect after they receive a confirm-email-address email and click. Avoids spam-trap addresses (mistyped emails) silently bouncing.
- Test: fan-out with 50 users, mocked Resend client; assert exactly 50 send attempts, 0 duplicates, all completed within the 30s window.
- Test: render an email for "Müller" — assert the `From`/`To` headers contain RFC 2047 encoded-word, decode round-trip is "Müller".

**Warning signs:**
- Resend dashboard shows 429 errors in cycle window.
- F&F user reports "I forwarded the email and my partner is logged in as me".
- Bounces > 5% (some addresses are spam-trapping).
- "Reported as spam" count > 0.
- F&F can't find the unsubscribe link.

**Phase to address:**
Per-user email pipeline phase. Throttle + List-Unsubscribe + double-opt are exit gates. Forward-resistance and `formataddr` come naturally from the same task.

---

### Pitfall 32: HTMX `hx-swap` discards the tour overlay; tour anchors miss elements that don't exist on first render

**What goes wrong:**
First-run tour modal anchors to selectors like `#market-tabs`, `#paper-trades-table`, `#calculator-panel`. Issues:
- **Anchor missing on first render:** New user's `market_pref` cookie is unset, so the dashboard renders without the per-market panel — tour step 3 ("here's your paper trades") points at `#paper-trades-table` which is hidden behind a "select a market" empty state. Tour positions a tooltip at coordinates that don't exist; arrow points at nothing.
- **HTMX swap nukes the tour overlay:** User completes step 1, clicks "next", which triggers an HTMX-driven content swap (e.g. expanding a panel). HTMX's `hx-swap="innerHTML"` replaces `#main` content; the tour overlay was a child of `#main` (or referenced an element inside it), so it disappears. Tour state lost.
- **Replay-from-help doesn't reset state:** User clicks "show tour again" from help menu. Tour starts at step 1, but `localStorage.tourSeen=true` is still set. Tour finishes silently because every step's "should-show" check returns false. Or vice versa — replay shows tour but doesn't reset the cookie, so next session re-runs tour.
- **Keyboard trap in modal** — tour modal traps Tab inside, but Esc binding missed; user with no mouse is stuck.
- **Tour collides with v1.2 Phase 25 roving tabindex** — tour modal opens, focus moves to "next" button, but the dashboard's roving tabindex steals focus back on its own load, fight loop ensues.
- **ARIA missing** — modal has no `role="dialog"`, `aria-labelledby`, `aria-describedby`. Screen reader announces "div" not "tutorial step 1 of 5".

**Why it happens:**
Tours assume a stable DOM. HTMX is fundamentally about replacing DOM. Every tour step that anchors to an HTMX-swapped region is at risk. Tour libraries (Shepherd.js, Driver.js, Intro.js) all accept selectors as strings — they don't know which strings will exist post-swap.

**How to avoid:**
- **Render the tour-anchor selectors stably, even on empty state.** First-run dashboard always renders `#paper-trades-table` (with a 0-row placeholder) so the tour can anchor. The empty-state copy goes inside, the anchor exists.
- **Position the tour overlay outside any HTMX swap target.** Mount tour DOM at `<body>` level (portal-style), not inside `#main`. HTMX swaps cannot reach it.
- **Re-attach tour to swapped content via `htmx:afterSwap` event:** tour listens for swap completions and re-validates the current step's anchor. If anchor is gone, advance or end gracefully — never leave a dangling tooltip.
- **Replay-from-help resets the seen flag explicitly.** "Restart tour" button → `localStorage.removeItem("tourSeen")` → load tour at step 1. Test it.
- **First-run detection per-user, not per-browser:** `state.users[uid].tour_completed_at: datetime | None`. Per-browser localStorage is a UX nicety on top.
- **`role="dialog"` + `aria-modal="true"` + `aria-labelledby="tour-step-title"` + `aria-describedby="tour-step-body"`** on the modal. Esc key closes. Focus-trap with explicit tab order. First focusable on open = "next" button; on close = the trigger element (where the user came from).
- **Tour does not steal focus from form inputs.** If an input is focused when tour starts (rare on first-run, common on replay), the tour pauses for one tick to let the input release focus.
- **A11y test:** `playwright.aria-snapshot()` (or `axe-core` smoke) on the dashboard with tour open. Zero new violations.
- Test: open tour, simulate HTMX swap of `#main`, assert tour overlay still present and current-step anchor still resolved.
- Test: keyboard-only flow — Tab cycles within modal, Esc closes, focus returns to trigger.

**Warning signs:**
- Tour arrow points at empty space mid-flow.
- Tour disappears after clicking "next" with no error.
- "Restart tour" button does nothing.
- axe-core reports new modal/dialog violations.
- Screen reader announces "dialog" without a name.

**Phase to address:**
Guide UI phase (tooltips + tour modal). Stable-anchor refactor is a prerequisite — must happen in the same phase, before tour wiring. A11y test is a hard gate.

---

### Pitfall 33: Tooltip injection breaks v1.2 Phase 25 roving-tabindex / mobile font / fieldset semantics

**What goes wrong:**
Inline tooltip implementation hangs `<button class="tooltip" aria-describedby="t1">?</button>` on every panel. Issues:
- **Roving tabindex broken:** v1.2 Phase 25 carefully placed `tabindex="-1"` on non-active market tabs. The tooltip buttons are added via Jinja partial that doesn't respect tabindex — they all get default `0`. Tab order now has 12 extra stops per market view. Keyboard nav goes from "fast scan" to "tedious".
- **Mobile font ≥16px regression:** Phase 25 hard-set min font on inputs to prevent iOS auto-zoom. Tooltip buttons render at 12px (`<sup>` inside a paragraph) → iOS zooms in when focused.
- **Tooltip content positioned outside fieldset:** A tooltip on an input inside `<fieldset><legend>` overflows the fieldset border. CSS `overflow: visible` isn't set on fieldset by default in some browsers; tooltip clipped or mispositioned.
- **`aria-describedby` chained wrong:** tooltip ID `t1` is reused on two panels. Screen reader reads the wrong tooltip on the second occurrence.
- **Tooltip on hover only, no keyboard:** mouse-only users see it; keyboard users tabbing through don't (focus doesn't trigger). WCAG 2.1.1 violation.
- **Tooltip dismisses on Tab:** acceptable for popovers, but if the tooltip *is* the only place a critical disclaimer lives, the user can't read it without holding focus — bad UX.

**Why it happens:**
Tooltips look small and incremental. They touch tab order, focus, font sizing, and ARIA semantics — each of which v1.2 Phase 25 fought hard to lock down. Reintroduction of any one is a regression.

**How to avoid:**
- **Reuse the existing focus-management policy.** Tooltip triggers inherit `tabindex` from their parent panel — non-active panels' tooltips are also `-1`.
- **Tooltip CSS inherits from input font-size.** No hard-coded `12px`. Mobile `16px` minimum survives.
- **Unique IDs per tooltip:** generate from a stable hash of (panel_id, field_name). Test: assert `len(tooltip_ids) == len(set(tooltip_ids))` in the rendered page.
- **Trigger on `hover|focus|click`** (CSS `:hover, :focus-within` and a JS listener for keyboard). WCAG-compliant.
- **Tooltip content is a `<details>`/`<summary>` semantic** for the disclaimer case (always-readable when expanded), or a `role="tooltip"` for hover-only annotation. Don't conflate.
- **Position via CSS `position: absolute`** with `overflow: visible` on the wrapping panel/fieldset.
- A11y regression suite: re-run the Phase 25 axe-core sweep with tooltips enabled. Zero new violations.
- Manual: keyboard-only walk through every panel — every tooltip discoverable, no extra tab stops on inactive tabs, mobile font check on real iOS.

**Warning signs:**
- Tab count to traverse a single market view increases by N (= number of new tooltips).
- iOS zooms in on tooltip-trigger focus.
- Two tooltips in different panels show the same content.
- WCAG audit flags new "name, role, value" violations.

**Phase to address:**
Guide UI phase. Tooltip rollout is **after** the tour-modal scaffold, so a11y baseline is already verified. The "no new tab stops on inactive panels" assertion is a regression test, not a manual check.

---

### Pitfall 34: `state.json` git push-back explodes when N user files are tracked

**What goes wrong:**
v1.0 INFRA-02 / Phase 10: the daily run commits `state.json` back to `origin/main` via deploy key. Phase 27-16 keeps this as the v1.2 model. v1.3 introduces `state/users/{uid}.json × N`. Naive port: commit-back includes every per-user file. Issues:
- **F&F trade content in git history forever.** Even on private repo, every commit is a privacy footgun: future maintainer (or someone with read access) sees alice's positions.
- **Merge conflicts on every cycle:** if the daily fan-out commits N files in sequence and an HTMX-driven write happens mid-cycle, the local git working tree diverges from origin. Push fails with non-fast-forward.
- **GitHub repo size grows unbounded.** N users × daily commits × 1 year = ~5MB/user/year of state-file deltas. Manageable but only if explicitly accounted for.
- **Recovery is now N-way:** git-revert of "today" reverts every user's state, even users not affected by the bug.

**Why it happens:**
The push-back was correct for one operator. It was never re-evaluated when multi-tenant entered scope. The deploy-key permission grants write access to the repo — same authority for one file or N.

**How to avoid:**
- **Stop pushing per-user state to git.** Per-user state lives only on the droplet. Persistence guarantee = droplet disk + filesystem-level backup (rclone to S3/B2 nightly, retained 30d). Git push-back continues for admin's `state.json` (legacy) but **not** for `state/users/`.
- **Strict gitignore:** `.gitignore` adds `state/users/`, `audit/`, `news_cache_*.json`. Test: `git check-ignore state/users/abc.json` returns the path. CI gate: `git ls-files | grep -E '^state/users/'` returns nothing.
- **Off-droplet backup is the durability story:** `rclone sync state/users b2://signals-users-backup/$(date +%F)/ --max-age 24h` from a daily systemd timer. Restore is `rclone copy b2:.../<date>/<uid>.json state/users/<uid>.json` — explicit per-user, scoped.
- **No deploy-key write-permission expansion.** Keep deploy key narrow; if v1.3 ever wants to push something else, file it explicitly.
- Test: simulate a fan-out cycle, assert no `git add state/users/` is called and the working tree is clean for those paths.

**Warning signs:**
- `git status` after a cycle shows `state/users/*.json` modified.
- GitHub repo size growing >100MB.
- A user's state ever appears in `git log -p`.

**Phase to address:**
Multi-tenant refactor phase (state_manager rewrite — same place that introduces the per-user namespace). The gitignore + backup is a single task; don't ship the rewrite without both.

---

### Pitfall 35: FastAPI `Depends(get_current_user)` evaluation order — security gate runs after request body is parsed

**What goes wrong:**
A new route `POST /paper-trades` declares dependencies: `def create_trade(payload: TradePayload, user: User = Depends(get_current_user))`. FastAPI's evaluation order: it parses + validates `payload` (the body) **before** running `Depends(get_current_user)`. If the body is large/malformed, the validation cost (or a Pydantic crash on weird input) executes for unauthenticated requests. CPU exhaustion, partial side-effects (if `model_validator` does anything with side effects — bad pattern but exists), unauthenticated request reaching code paths that should be unauthenticated-rejected.

A worse variant: the dependency itself touches state. `Depends(get_current_user)` reads the session cookie, refreshes the rolling-expiry, and writes back to the user file. Two parallel requests: one is authenticated, one has a stale cookie. Both kick off `get_current_user`, both attempt to acquire the per-user file lock, the stale-cookie request fails the auth check after holding the lock briefly. Now lock-acquire latency is paid by every unauth request.

**Why it happens:**
FastAPI evaluates path/query/body parameters and dependencies in a defined order, but most developers don't internalize that the body is parsed before the auth dependency runs. This compounds with `~/.claude/LEARNINGS.md` G-51 (FastAPI route registration order) — both are FastAPI-specific footguns.

**How to avoid:**
- **Auth via dependency-on-router, not per-route.** Mount the entire authenticated app under an `APIRouter(dependencies=[Depends(get_current_user)])`. The dependency runs at routing level — rejected requests never reach body parsing.
- **Auth dependency does not write state.** Reading the session cookie is read-only; rolling-expiry refresh is debounced (only write if `last_seen` is >5min stale, and behind the per-user lock with try-non-blocking — fail fast on contention).
- **Rate-limit body size at the framework level:** `app.middleware("http")` rejects bodies >1MB before any further processing. Or nginx `client_max_body_size 100k` for these routes.
- Test: send unauthenticated POST with a 10MB body to a protected route. Assert response is 401 (or 413/415) within 100ms — body is not fully read.
- Test: parallel auth dependencies under a stress test do not deadlock on the per-user lock.

**Warning signs:**
- Unauth requests are slow (suggests body parse running before auth check).
- `get_current_user` writes to the state file every call.
- A single user's session refresh contends with their own concurrent dashboard load.

**Phase to address:**
Multi-tenant refactor phase (auth + state_manager rewrite). Verify auth-via-router-dependency is the pattern from day 1.

---

### Pitfall 36: CSRF tokens stale after session regeneration; HTMX doesn't auto-rotate

**What goes wrong:**
v1.1 added CSRF protection via a hidden `_csrf` field in HTMX forms. v1.3 invite-acceptance + login + 2FA enroll all call `request.session.regenerate()` (or equivalent — a fresh session ID per privilege change, which is correct). The new session has a new CSRF token. Any open dashboard tab still has the old token cached in form fields. Next HTMX submit → 403 CSRF. User confused, retries, still 403.

A worse variant: CSRF token is per-session but stored in a cookie shared with the JS layer. After session regen, the cookie updates, but HTMX form fields rendered server-side at page load have the old token. Refresh-the-page fixes it but is invisible to the user.

**Why it happens:**
Session regeneration is the right call (privilege escalation = new session ID, OWASP). But CSRF token rotation is coupled to session ID rotation, and HTMX forms render their CSRF inline at server-render time — they don't auto-fetch a fresh token. This is `~/.claude/LEARNINGS.md` global "CSRF tokens go stale after session regeneration".

**How to avoid:**
- **Per-form CSRF endpoint:** `GET /csrf` returns the current token. HTMX forms use `hx-headers='js:{"X-CSRF-Token": getCsrfToken()}'` and a small JS shim that fetches the token on every submit (cached for a few seconds).
- **403 CSRF response includes a `HX-Refresh: true` header** so HTMX refreshes the page on stale-token errors. User retries automatically.
- **Test:** complete a login (session regen), assert the next HTMX form submit succeeds without manual page refresh.

**Warning signs:**
- Users report "form submit doesn't work after I logged in" on first try.
- 403 CSRF errors in logs immediately following login/2FA-enroll routes.

**Phase to address:**
RBAC phase (auth UX is touched anyway). Add the CSRF refresh shim alongside the cookie-session work.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Single shared `state.json` lock instead of per-user | Simpler lock helper, one path | Every HTMX write contends with every other; fan-out throughput collapses | Only as v1.3 sprint-zero placeholder; replace before any user other than admin is invited |
| Skip migration round-trip test ("just one v9→v10 step") | Saves 30 min in the migration phase | Mid-flight crash leaves state half-migrated; manual recovery (Pitfall 27) | Never — round-trip test is mandatory |
| Per-user state in git (gitignore later) | Mirrors v1.0 push-back pattern | F&F trade content in git history forever; can't rewrite history without coordinating with deploy key | Never — gitignore from the first per-user write |
| Substring keyword classifier (no word boundary) | One-line implementation | "rate" matches every business article (Pitfall 30); banner fatigue → real critical events ignored | Never |
| Tooltips with hard-coded `12px` | Smaller, tighter visuals | iOS auto-zoom regression on every tooltip-bearing input (Pitfall 33) | Never on inputs; OK on disclaimers |
| `Depends(require_admin)` per-route | Visible at each route declaration | One miss = full IDOR (Pitfall 22) | Never — sub-router from day 1 |
| Per-route CSRF token in form HTML, no refresh | Simple template render | 403 spam after every session regen (Pitfall 36) | Only if no session regen ever happens (i.e. no login flow — not v1.3) |
| News fetched per-user in fan-out | One code path, no cache invalidation logic | 429s, banned API key (Pitfall 29) | Never |
| Crash email includes full state | Maximal debug context | Cross-user privacy leak (Pitfall 26) | Never; redact before send always |
| Single-loop fan-out, no per-user `try/except` | One code path, easy to read | Partial fan-out, admin oblivious for 24h (Pitfall 24) | Never; per-user crash boundary is the v1.3 floor |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `yfinance.Ticker.news` | Trust the schema across versions | Pin yfinance, normalize through an adapter, fixture-test both legacy and current shape (Pitfall 29) |
| Resend (per-user fan-out) | Send N emails in 1s | Throttle to documented rate-limit ÷ 2; prefer batch send API; List-Unsubscribe header (Pitfall 31) |
| FastAPI route ordering | Register `/markets/{id}` before `/markets/settings` | Literals before dynamics, or split into prefixed sub-routers (`~/.claude/LEARNINGS.md` G-51) |
| FastAPI auth | `Depends(get_current_user)` per-route | Mount authenticated app under an `APIRouter(dependencies=[…])` (Pitfall 22, 35) |
| HTMX + tour | Mount tour DOM inside swappable region | Mount at `<body>`; rebind on `htmx:afterSwap` (Pitfall 32) |
| HTMX + CSRF | Render token inline at first paint | Fetch fresh token via `js:{...}` per submit; `HX-Refresh: true` on 403 (Pitfall 36) |
| `state.json` git push-back | Port the v1.0 deploy-key flow as-is | Stop pushing per-user state; rclone backup off-droplet (Pitfall 34) |
| Invite tokens | `secrets.token_hex(8)`, store plaintext | `secrets.token_urlsafe(32)`, store sha256, expire ≤ 30 days, `hmac.compare_digest` (Pitfall 28) |
| Email magic-link in body | Embed token directly | Embed login-page link only; verify session at the page (Pitfall 31) |
| flock on per-user files | Lock the whole `state.json` | Per-user `state/users/{uid}.lock`; held across the read-modify-write window (Pitfall 25) |
| Migration in-place | Mutate state, save, hope | Build new dict, validate via Pydantic, save once (Pitfall 27) |
| Logging in fan-out | `logger.info("state %s", state)` | Structured allowlist; `RedactStateFilter` strips trade content (Pitfall 23) |
| Crash email | Include `_LAST_LOADED_STATE` snapshot | Include `user_id` + `phase` + stack only; never trade content (Pitfall 26) |
| Dashboard news render | `{{ item.title|safe }}` | Default autoescape; never `|safe` on third-party content (Pitfall 29) |
| Tooltip ARIA | Reuse `aria-describedby` IDs across panels | Stable hash of `(panel_id, field_name)` (Pitfall 33) |

---

## Performance Traps

This is a 10–20-user F&F app, so most "scale" concerns don't apply. The traps that do bite at small scale:

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Per-user fan-out re-fetches news per user | 429 from Yahoo, 5–10s added latency to each cycle | Single fetch per market per cycle, shared cache (Pitfall 29) | At N≥4 users in one cycle |
| Dashboard renders news on every page-load (no cache) | Page TTFB jumps from <100ms to ~1s; rate-limit risk | TTL-cached news file, refresh out-of-band (Pitfall 29) | Immediately at first multi-user load |
| Per-user state read on every dashboard request | Concurrent tab loads contend on flock | Read-only path doesn't need flock; only mutating paths do (Pitfall 25 corollary) | At any multi-tab user |
| Synchronous Resend send blocks fan-out next user | Cycle wall-clock = N × email latency (~1s each) | `asyncio.gather` with semaphore-throttled concurrency (Pitfall 31) | At N≥5 users |
| Tour reflows tabindex on every HTMX swap | 30–50ms jank per swap, plus possible focus loss | Tour DOM portaled outside swap target (Pitfall 32) | Immediately on first interaction |
| `state/users/` directory unbounded | After 1y of audit/journal data, single user state >5MB | Cap journal/equity_history rows per v1.0 Pitfall 22, applied per-user | Year 2 |

---

## Security Mistakes

Domain-specific, beyond standard OWASP. Single-operator → multi-tenant introduces real attack surface for the first time.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Cross-user IDOR via entity ID in URL | Full data leak between F&F users | Centralized `load_X_for_user()`; 404 on cross-user; per-route 404 test (Pitfall 21) |
| Admin-route gate missing on one new route | Privilege escalation, full state read | `APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])`; startup invariant test (Pitfall 22) |
| Crash email leaks trade content cross-user | Privacy violation, audit-trail concern | Redacted crash content; `PublicUserSummary` only (Pitfall 26) |
| Invite token weak entropy / no expiry / not constant-time compared | Token-guessing, replay | `token_urlsafe(32)`, sha256-store, 7d default expiry, `hmac.compare_digest` (Pitfall 28) |
| Invite URL leaks via Referer | Token in third-party logs | `Referrer-Policy: no-referrer` on signup; consume strips token from URL (Pitfall 28) |
| Magic-link in email forwarded → attacker logs in as user | Account takeover via email forward | Email contains login-page link only; no session token in URL (Pitfall 31) |
| News URL fetched server-side | SSRF (cloud metadata, internal services) | Display-only; if fetching needed, hostname-resolve + private-IP-block check (Pitfall 29) |
| News headline rendered with `|safe` | XSS into the dashboard | Default autoescape; fixture test for `<script>` headlines (Pitfall 29) |
| State file written to git | F&F trade content public/historical | Hard gitignore; CI gate (Pitfall 34) |
| Logs include state content | Privacy leak via journalctl/log shipping | Structured allowlist + `RedactStateFilter` (Pitfall 23) |
| `_LAST_LOADED_STATE` references wrong user at crash | Wrong user's content in crash email | Drop the cache or scope it to current contextvar (Pitfall 26) |
| CSRF token stale after session regen | 403 spam, users disable HTMX | Per-form CSRF fetch + `HX-Refresh` on stale (Pitfall 36) |
| FastAPI auth runs after body parse | DoS / large-body parsing on unauth requests | Auth-via-router-dependency; nginx body-size cap (Pitfall 35) |
| Invite revocation race with consume | Double-use of token | flock + check-and-set + atomic stamp (Pitfall 28) |
| Header `X-Tenant-Id` (or analog) trusted from client | Tenant spoofing | Never read tenant from request headers; resolve from session only (`~/.claude/LEARNINGS.md` G-23) |

---

## "Looks Done But Isn't" Checklist

Use during verification at each v1.3 phase. Pass = green grep + green test, not "looks fine".

- [ ] **Multi-tenant refactor:** Every entity-ID route has a paired `test_<route>_returns_404_for_other_users_entity` test. Grep `tests/`: `grep -rn "current_user" tests/ | grep -c "another_user\|other_user"` ≥ count of mutating routes.
- [ ] **Multi-tenant refactor:** Per-user flock helper in use everywhere `save_state` is called. `grep -rn "save_state\|state\[" src/ | grep -v "with .*lock\|state_manager.*save"` returns zero matches outside the helper.
- [ ] **Multi-tenant refactor:** Migration round-trip test: 5 v9 fixtures, all round-trip lossless to v10 and back. Test file exists and is green.
- [ ] **Multi-tenant refactor:** `git ls-files | grep '^state/users/'` returns nothing. `.gitignore` contains `state/users/` and `audit/`.
- [ ] **Multi-tenant refactor:** Crash-email body, with a fixture state holding `entry_price=1234, n_contracts=5`, contains neither value. Regex `(entry_price|n_contracts|"direction":\s*"(LONG|SHORT)")` matches zero in the rendered email.
- [ ] **Multi-tenant refactor:** Admin user-list view, rendered with a fixture user holding 5 paper trades, contains no trade content. Same regex as above on the response body.
- [ ] **RBAC:** All admin routes mounted under `APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])`. Startup test walks `app.routes` and asserts every `/admin/*` path has `require_admin` in its dependency chain.
- [ ] **RBAC:** Invite token is `secrets.token_urlsafe(32)`. `invites.json` contains only sha256 hashes (visual inspection of the file after creating one invite — no string >32 chars except hashes).
- [ ] **RBAC:** Two parallel `consume(token)` calls → exactly one succeeds. Concurrency test green.
- [ ] **RBAC:** Expired invite returns 404 (not "expired"). Revoked invite returns 404. Test green.
- [ ] **RBAC:** Signup page response includes `Referrer-Policy: no-referrer` header. After consume, redirect URL contains no token.
- [ ] **Per-user email:** Fan-out with 50 mocked users completes within 30s, throttled. No 429s in logs.
- [ ] **Per-user email:** Email body contains `List-Unsubscribe` header and a working unsubscribe URL. F&F user can unsubscribe and the daily mail stops next cycle.
- [ ] **Per-user email:** Email body contains no session token URL. The "view dashboard" link goes to the bare login page.
- [ ] **Per-user email:** Render for "Müller" — `From`/`To` headers RFC 2047 encoded; round-trip decode is "Müller".
- [ ] **Per-user email:** End-of-cycle summary email to admin lists per-user success/failure counts. Triggered when a user fails — admin gets the summary same cycle.
- [ ] **News:** yfinance pinned exact version. Adapter test against fixtures (both schemas) green.
- [ ] **News:** Single fetch per market per cycle (verified by counting Yahoo HTTP calls in a fan-out test).
- [ ] **News:** Dashboard with fixture headline `<script>alert(1)</script>` — response body contains `&lt;script&gt;`, not the raw tag.
- [ ] **News:** Critical-event classifier: precision ≥0.7, recall ≥0.9 against a 30-headline labeled fixture set.
- [ ] **News:** Per-user dismiss state isolated — user A's dismiss never affects user B (test green).
- [ ] **Guide UI:** Tour overlay survives an HTMX swap of `#main`. Test green.
- [ ] **Guide UI:** "Restart tour" button works on second click of the same session. Manual + test.
- [ ] **Guide UI:** Keyboard-only flow: Tab traps inside modal, Esc closes, focus returns to trigger. Manual + axe-core green.
- [ ] **Guide UI:** Tooltip count adds zero new tab stops on inactive market panels (Phase 25 roving tabindex preserved). Test counts tab stops on the dashboard.
- [ ] **Guide UI:** axe-core sweep on the dashboard with tour + tooltips: zero new violations vs baseline.
- [ ] **Cross-cutting:** `RedactStateFilter` installed at app startup. Test: a `logger.info("state: %s", state)` does NOT appear in the captured log output.
- [ ] **Cross-cutting:** Per-user state mtime advances for all users in the cycle, not just admin. Health endpoint `/healthz/last-cycle` reports per-user counts.
- [ ] **Cross-cutting:** `git status` after a fan-out cycle is clean for `state/users/`.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| IDOR vulnerability discovered post-ship | HIGH | Disable the affected route immediately (`HTTP 503 maintenance`); audit logs for cross-user access; notify any affected users; ship the fix as a hotfix point release; add the missing 404 test |
| Schema v9→v10 migration crashed mid-flight | MEDIUM (with backup) / HIGH (without) | `cp state.v9-backup-*.json state.json`; redeploy with the migration patched to atomic-build-then-save; replay any HTMX submissions from systemd journal during the broken window |
| Fan-out partial failure for half of F&F | LOW (single cycle) | Re-run the cycle for affected users only via a `--user uid1,uid2,…` flag on the daily entrypoint; admin already got the summary email |
| Atomic-write contract broken (lock-file approach) | LOW–MEDIUM | Replay the latest HTMX submission from access logs; notify the user "your last submission may not have saved, please re-submit"; fix lock helper |
| Crash email leaked another user's content | LOW (auditing) / MEDIUM (notifying users) | Identify the recipients (admin only, hopefully); revise the redaction filter; notify the affected F&F user(s) per privacy policy |
| Invite token consumed twice | MEDIUM | Manual cleanup: pick the canonical user; merge or delete the duplicate's state; revoke the still-active session |
| Resend rate-limited mid-cycle | LOW | Throttle and retry; if persistent, drop next cycle's emails (admin still gets summary); raise the limit on the Resend dashboard |
| News API returned new schema | LOW | Roll back yfinance pin; capture the new fixture; ship adapter update next phase |
| Critical-event banner stuck red | LOW | Manual dismiss for affected users; refine keyword/regex; backfill the dismiss state |
| Magic-link forwarded → unintended login | MEDIUM | Force session regen for the affected user; audit access; ship the email-link-only-to-login-page change if not already done |
| Tour broken on first-run for one user | LOW | "Restart tour" from help menu; fix the broken anchor; the user's `tour_completed_at` is already set so they won't see it again unless they replay |
| Per-user state in git history | HIGH | `git filter-repo` to scrub historical paths; force-push (coordinated with deploy key); rotate deploy key; add the gitignore + CI gate so it can't recur |

---

## Pitfall-to-Phase Mapping

Suggested phase ordering. Phase numbers below the v1.3 line continue from Phase 28 (v1.2 UAT closure) and Phase 28.x for v1.2.1 retroactive wrap.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 21. IDOR via bolt-on user_id | **Multi-tenant refactor** (early task: centralized loader) | Per-route 404 sweep; grep gate for raw `state[...]` reads |
| 22. Admin-vs-user boundary missing on one route | **RBAC phase** (first task: sub-router) | Startup invariant test walks `/admin/*` |
| 23. Privacy regression — admin sees trade content | **Multi-tenant refactor** (alongside loader) | Privacy grep on rendered admin HTML; `RedactStateFilter` test |
| 24. Fan-out partial failure | **Per-user email pipeline** (per-user crash boundary task) | Fault-injection test: one user broken, others succeed, admin gets summary |
| 25. Concurrent write race | **Multi-tenant refactor** (first task: flock helper) | 50-thread stress test; kill-during-lock test |
| 26. Crash email leaks wrong user's state | **Multi-tenant refactor** (alongside redaction filter) | Fault-injection test: crash mid-bob, email body names bob, no trade content |
| 27. Schema v9→v10 mid-flight crash | **Multi-tenant refactor** (migration task) | Round-trip test 5 fixtures; backup-on-migrate hook |
| 28. Invite token vulnerabilities | **RBAC phase** (invite issue + consume tasks) | Token entropy + sha256-storage + flock atomicity + Referer-Policy tests |
| 29. yfinance news schema/rate-limit/XSS/SSRF | **News integration phase** (adapter task) | Fixture tests both shapes; XSS test; rate-limit mock test |
| 30. Critical-event flag false +/- and dedup | **News integration phase** (classifier task, after adapter) | 30-headline labeled fixture; dismiss persistence test |
| 31. Per-user email Resend / unicode / unsub | **Per-user email pipeline** (throttle + List-Unsubscribe + double-opt task) | 50-user throttle test; List-Unsubscribe header assert; "Müller" round-trip |
| 32. HTMX/tour swap interactions | **Guide UI phase** (tour scaffold task, before tooltips) | HTMX-swap-survives test; keyboard flow; axe-core |
| 33. Tooltip injection regresses Phase 25 a11y | **Guide UI phase** (tooltip task, after tour) | Tab-stop count assertion; iOS font-size manual; axe-core diff |
| 34. State.json git push-back explodes | **Multi-tenant refactor** (gitignore + rclone task) | CI gate `git ls-files | grep state/users` empty; rclone smoke test |
| 35. FastAPI auth-after-body-parse | **Multi-tenant refactor** (auth-via-router task) | Large-body unauth test fast-rejects |
| 36. CSRF stale after session regen | **RBAC phase** (auth UX touch-up) | Login → HTMX submit succeeds without page refresh |

**Phase-ordering rationale:**
- The **multi-tenant refactor** must come first. It introduces the per-user namespace, the flock helper, the centralized loader, the `PublicUserSummary` model, the redaction filter, the migration, and the gitignore-+-backup story. Every later phase consumes those primitives.
- **RBAC** comes second because invites + admin gating depend on the per-user namespace existing. Sub-router pattern is locked here. CSRF refresh added alongside.
- **Per-user email pipeline** comes third — the per-user crash boundary, the throttle, the List-Unsubscribe, and the summary-email-to-admin all exercise the multi-tenant refactor in the daily fan-out path.
- **News integration** comes fourth. It's read-only (no state writes), so it can't cause cross-tenant leak directly, but it touches the shared dashboard surface — the renderer must already handle escaped output from v1.2 Phase 27.
- **Guide UI** comes last. It depends on every prior phase's UI being stable. Tour anchors break if the UI is still moving.
- **Phase 28 (v1.2 UAT closure)** and **v1.2.1 retroactive wrap** sit before the v1.3 substance — they don't add new surface area, just close v1.2 debt.

---

## Sources

- **`.planning/research/v1.0-archive/PITFALLS.md`** — v1.0 pitfalls 1–20 still in force; this document is incremental.
- **`~/.claude/LEARNINGS.md`** — universal pattern library:
  - G-20 — every query-by-userId must also filter by tenantId.
  - G-21 — Prisma extensions for tenant scoping break on nullable tenantId (analog: per-user file paths).
  - G-22 — tenantId nullable→required breaks call sites.
  - G-23 — middleware tenant-id headers must be stripped on non-tenant paths.
  - G-36 — defensive-read + logging layer for partial migrations.
  - G-37 — architectural boundaries require AST-based invariant tests, not grep rules.
  - G-46 — schema version hard-coded in assertions becomes stale after migration chain extends.
  - G-51 — FastAPI/Starlette route ordering — literal segments must precede dynamic siblings.
  - G-53 — regex validation alone insufficient; pair with membership allowlist.
  - "CSRF tokens go stale after session regeneration" — global section.
  - "Server-side fetches of user-supplied URLs need SSRF protection" — global section.
- **`.planning/PROJECT.md`** — v1.3 scope, hard constraints (signal-only, F&F privacy, schema migration), key decisions (atomic write, hex-lite, `_LAST_LOADED_STATE` revisit-flag).
- **`.planning/MILESTONES.md`** — v1.2 deferred items, accepted tech debt, schema v9 origin, deploy-key push-back history.
- **OWASP CWE-639** — Authorization Bypass Through User-Controlled Key (canonical IDOR reference).
- **RFC 8058** — One-Click Unsubscribe (`List-Unsubscribe-Post`).
- **Resend documentation** — rate limits, batch send API, domain verification (re-verify at planning time; published rate limits have changed).
- **yfinance issue tracker (github.com/ranaroussi/yfinance/issues)** — recurring schema drift across 0.2.40 → 0.2.55 for `Ticker.news`; importance hint presence varies.
- **HTMX docs — `htmx:afterSwap`** — re-binding after content replacement.
- **WAI-ARIA Authoring Practices — Dialog (Modal) Pattern** — focus trap, role, labelledby, describedby.
- **WCAG 2.1.1 (Keyboard) and 2.4.3 (Focus Order)** — tour and tooltip a11y.
- **Personal experience (commits in trading-signals repo)** — `_LAST_LOADED_STATE` cache (Phase 8 D-08); naive datetime fail-closed (Phase 27); Phase 25 roving tabindex; Resend deliverability (v1.0 Pitfall 14); atomic write contract (v1.0 Pitfall 13). All these are now N-user surfaces and must be re-validated, not assumed.

---

*Pitfalls research for: v1.3 Multi-Tenant Friends & Family — adding invite-only multi-tenancy, per-user state, per-user email, yfinance news, and guide UI to an existing FastAPI/HTMX file-state trading-signal app.*
*Researched: 2026-05-10*
