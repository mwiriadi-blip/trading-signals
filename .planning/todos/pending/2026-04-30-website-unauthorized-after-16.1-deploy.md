---
created: 2026-04-30
priority: blocker
area: auth
status: pending
phase_link: 16.1-phone-friendly-auth-ux-for-dashboard-access
related_commits:
  - 24b6495  # Phase 16.1 plans
  - 879730d  # scheduler email dispatch fix (last droplet pull)
  - cf20a78  # latest main (Phase 16 closed)
---

# Website returns plain "unauthorized" — Phase 16.1 browser-redirect missing in production

## Problem

Operator visited `https://signals.mwiriadi.me/` in Safari today (2026-04-30) and got plain `unauthorized` text. This contradicts Phase 16.1 E-02 step 3 contract: browsers (Sec-Fetch-Mode=navigate AND Sec-Fetch-Dest=document, OR Accept: text/html when Sec-Fetch absent) MUST be redirected to `/login?next=<urlencoded-path>` with HTTP 302, NOT served plain `unauthorized` text.

Screenshot: shared by operator 2026-04-30. Plain text body `unauthorized`, no login form, no redirect, no styled page.

## Hypotheses (most → least likely)

1. **Web service not restarted after `git pull`** — operator likely ran `git pull` + `sudo systemctl restart trading-signals` (signal daemon only) when deploying the scheduler-email fix earlier today. The web service `trading-signals-web` was never restarted, so it's still running pre-16.1 Phase 13 header-auth code where any unauthenticated request returns plain `unauthorized` 401. Pre-16.1 behavior matches the screenshot exactly.
2. **`bash deploy.sh` never run** — `deploy.sh` step 6 restarts BOTH units (`sudo -n systemctl restart trading-signals` + `sudo -n systemctl restart trading-signals-web`) per Phase 11 D-23. If only step 1 (manual restart) was used, web service drifts.
3. **Phase 16.1 commits didn't reach the droplet** — git pull stopped at an earlier SHA. Verify with `git log -3 --oneline` on droplet.
4. **Real regression** — middleware browser-detection branch (E-02 step 3) doesn't recognize Safari's headers. Less likely; needs journalctl inspection.

## Verification steps (operator on droplet)

```bash
cd ~/trading-signals
git log -3 --oneline
# Expect: cf20a78, 25e1e8b, 879730d (or newer) at top

systemctl status trading-signals-web | head -5
# Compare 'Active: active (running) since ...' time to git log time;
# if web service started BEFORE Phase 16.1 commits landed, that's the bug

journalctl -u trading-signals-web -n 30 --no-pager
# Look for FastAPI startup line + first request log to /

# The clean fix:
bash deploy.sh
# Restarts both units per Phase 11 D-23 step 6
```

## Solution branches

- **If `bash deploy.sh` resolves it (most likely):** runbook clarity bug. SETUP-DROPLET.md doesn't make it explicit that auth-flow code changes require an explicit web service restart, not just signal daemon restart. Open a docs PR clarifying the rule "EVERY git pull on droplet MUST be followed by `bash deploy.sh`, never manual `systemctl restart` alone".
- **If `bash deploy.sh` does NOT resolve it:** real regression in `web/middleware/auth.py::AuthMiddleware.dispatch` browser-detection branch (E-02 step 3). Reproduce locally with `curl -i -H 'Sec-Fetch-Mode: navigate' -H 'Sec-Fetch-Dest: document' http://127.0.0.1:8000/` against a fresh `uvicorn web.app:app` — should return 302 with `Location: /login?next=/`. If it returns 401 plaintext locally too, the bug is code-side; open a /gsd-debug session targeting the middleware's `_is_browser_navigation` helper.

## Dependencies

This blocks closure of:

1. **v1.1 milestone archive** — `/gsd-complete-milestone v1.1` was paused on 2026-04-30 mid-archive when this issue surfaced. Resume after this todo resolves.
2. **UAT-16-A re-verification** — UAT-16-A was marked `verified 2026-04-27` against pre-16.1 header-auth flow. After 16.1 ships, UAT-16-A's contract changed (browsers now see /login form, not the dashboard directly). The "verified" status is stale; should be re-run after the production auth UX actually works.

## Priority

**BLOCKER** — production auth UX broken, milestone close paused, UAT-16-A status compromised.
