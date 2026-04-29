---
created: 2026-04-30
priority: high
area: auth
status: pending
phase_link: 16.1-phone-friendly-auth-ux-for-dashboard-access
related_files:
  - web/routes/reset.py
  - notifier.py  # send_magic_link_email
  - web/app.py  # _read_auth_credentials boot validation
---

# Reset 2FA recovery flow — email not arriving + UX simplification

## Problem 1 — Email not received

Operator submitted POST `/forgot-2fa` form with `username=marc` + their password. The page redirected to "Check your email" (the generic constant-time response per Plan 16.1-03 must_have F-02). **No email arrived in `mwiriadi@gmail.com` inbox.**

`OPERATOR_RECOVERY_EMAIL=mwiriadi@gmail.com` is set in `.env`. Daily signal emails ARE arriving from the same droplet (confirmed earlier today via 2026-04-30 daily email). So Resend API key + `SIGNALS_EMAIL_FROM` are working in general — magic-link path is the only broken one.

**Hypotheses (most → least likely):**

1. **Operator-typed password didn't match `WEB_AUTH_SECRET`** — the constant-time guard means invalid creds get the same "Check your email" page without sending. By design (AUTH-02 — no credential-validity leak). If the password they typed wasn't exactly the value in `.env`, no send fired.
2. **`notifier.send_magic_link_email` silently failed** — per Plan 16.1-03 "failures NEVER crash the request — log error, render generic 'Check your email' page (F-03)". Check journalctl for `[Email] WARN magic-link send failed` or any error.
3. **Rate limit hit** — first try unlikely, but per F-08: 3 magic links per 24h per account. If the operator tried multiple times, all attempts past 3 silently no-op.
4. **`OPERATOR_RECOVERY_EMAIL` boot-validation slipped** — must match `^[^@]+@[^@]+\.[^@]+$` per Plan 16.1-03 truth. Boot would have failed with RuntimeError if malformed, but maybe the var name was set with a typo we missed.
5. **Resend domain mismatch** — `signals@mwiriadi.me` is the from-address; if Resend rejected it for the magic-link send (different shape than daily signal email), error is logged-not-crashed.

**Diagnosis steps on droplet:**

```bash
# 1. Check magic-link logs (success or failure)
journalctl -u trading-signals-web --since '1 hour ago' --no-pager | grep -i 'magic\|\[Email\]\|forgot-2fa'

# 2. Check rate-limit table
grep -A3 'pending_magic_links' /home/trader/trading-signals/auth.json 2>/dev/null

# 3. Confirm OPERATOR_RECOVERY_EMAIL is set
grep OPERATOR_RECOVERY_EMAIL /home/trader/trading-signals/.env

# 4. Confirm Resend dashboard activity
# (operator manual check — open Resend dashboard, look for sends to mwiriadi@gmail.com in the last hour)
```

## Problem 2 — UX simplification

Operator's note: "the above should just have an email slot to send the email link and fail silently if there is no email address in the system."

**Current design (Plan 16.1-03 F-07):** Form takes `username` + `password` → if both match `.env` values → email goes to `OPERATOR_RECOVERY_EMAIL`. Form mirrors login form by design (operator already knows username + password; the recovery flow is only for the 2FA reset, not for full account recovery).

**Operator's proposed design:** Form takes `email` only → email goes to that address if it matches a known recovery address; silent no-op otherwise.

**Trade-offs to consider:**

| Aspect | Current (username + password) | Proposed (email only) |
|--------|-------------------------------|----------------------|
| Security | Strong — only the operator who knows both creds can trigger reset | Weaker — anyone can spam the form with random emails; even with constant-time response, attacker learns nothing but the form is a free email-validity oracle if not implemented carefully |
| UX | Operator must remember password (which they typed once during enrollment) | Operator only needs the email address — easier to recover from "I forgot the password" state |
| Spam vector | Low — no enumeration possible | Medium — needs strict rate-limiting per IP + per email |
| Use case | Reset 2FA when phone lost but credentials remembered | Reset 2FA when phone lost AND password forgotten — full bootstrap |

**Gut take:** Operator's proposal is better for the realistic failure mode (operator loses phone + forgets password). The constant-time/silent-fail behavior they asked for is correct — "fail silently if there is no email address in the system" matches the existing AUTH-02 no-leak pattern. Worth a focused redesign in v1.2.

## Solution branches

- **If diagnosis (Problem 1) shows the operator typed the wrong password:** That's the bug — UX should make this less surprising (e.g. show a brief "If creds were valid, email sent" line on the success page so operator knows whether to re-check creds vs check spam folder). Marries to Problem 2.
- **If diagnosis shows `notifier.send_magic_link_email` is throwing:** Real bug, file as a v1.1 patch. Likely cause: Resend rejecting the magic-link email shape (different template than daily signal). Check the error message in journalctl.
- **For Problem 2 (UX redesign):** Defer to v1.2 as a focused phase — needs threat-model review (rate limit, IP allowlist, spam mitigation) before changing the form to email-only.

## Priority

**HIGH** — operator can't currently complete the magic-link recovery flow. If the cause is "wrong password typed" then the fix is UX clarity; if it's a real bug, fix should ship as a quick task.

## Notes

This todo is paired with `2026-04-30-website-unauthorized-after-16.1-deploy.md` — both are surface-level validation issues with Phase 16.1 production deploy that didn't show up because UAT-16.1 (in `.planning/phases/16.1-phone-friendly-auth-ux-for-dashboard-access/16.1-HUMAN-UAT.md`) was never run by the operator. The 16.1 HUMAN-UAT is currently in the deferred list; running it would have caught this earlier.
