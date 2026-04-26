---
phase: quick-260426-vcw
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - nginx/signals.conf
  - nginx/signals 2.conf
autonomous: true
requirements:
  - WEB-03
  - WEB-04
  - D-12
must_haves:
  truths:
    - "nginx/signals.conf comment block accurately describes the deployed cert bootstrap path (certbot certonly --standalone, not certbot --nginx)"
    - "nginx/signals.conf contains a port-80 server block that 301-redirects HTTP to HTTPS while preserving /.well-known/acme-challenge/ for manual renewal"
    - "nginx/signals 2.conf no longer exists in the working tree"
    - "All existing 443 server-block functionality (TLS tuning, OCSP, security headers, ACME carve-out, /healthz rate limit, proxy to 127.0.0.1:8000) is preserved byte-for-byte except for comment text"
    - "Three atomic commits land in order: comment reconcile, port-80 redirect, duplicate file deletion"
  artifacts:
    - path: "nginx/signals.conf"
      provides: "Deployment-ready nginx config for signals.mwiriadi.me with both HTTPS and HTTP→HTTPS redirect"
      contains: "ssl_certificate /etc/letsencrypt/live/signals.mwiriadi.me/fullchain.pem"
    - path: "nginx/signals.conf"
      provides: "Port-80 redirect server block at end of file"
      contains: "return 301 https://$host$request_uri"
  key_links:
    - from: "nginx/signals.conf port-80 block"
      to: "nginx/signals.conf 443 block"
      via: "operator pulls + sudo systemctl reload nginx on droplet"
      pattern: "listen 80"
    - from: "nginx/signals.conf comment block"
      to: "deployed reality (certbot certonly + manual ssl_certificate paths)"
      via: "operator reads comments to understand renewal path"
      pattern: "certbot certonly --standalone"
---

<objective>
Reconcile `nginx/signals.conf` with the deployed-and-working state on droplet
209.38.30.13 (signals.mwiriadi.me, LE cert issued 2026-04-26 valid through
2026-07-25, auto-renewal scheduled). The repo file is currently stale in two
ways: (1) its narrative comments describe a `certbot --nginx` flow that was
never actually used, and (2) it has no port-80 → port-443 redirect server
block, which means WEB-04 / D-12 is only enforced on the live droplet and not
checked into git.

Purpose: keep the repo as the source of truth for nginx config so any future
re-provision (or rollback to a fresh droplet) reproduces today's working
state from a `git pull`. Also clean up the macOS-Finder-duplicate
`nginx/signals 2.conf` left in the working tree.

Output: three atomic commits — comment reconcile, port-80 redirect, duplicate
deletion — landed in order on the local branch. No droplet changes.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md
@./CLAUDE.md

@nginx/signals.conf

<deployment_facts>
<!-- Source of truth for the comment rewrite. These are facts about the live
     droplet — do not invent details beyond what is listed here. -->

- Domain: signals.mwiriadi.me (CNAME at Cloudflare → 209.38.30.13)
- Cloudflare DNS proxy: must be DISABLED (grey-cloud) for HTTP-01 ACME to
  reach origin. Proxied (orange-cloud) caused 521 errors during initial
  challenge.
- Cert issued: 2026-04-26 via `certbot certonly --standalone -d signals.mwiriadi.me`
- Cert valid through: 2026-07-25
- Cert paths on droplet (and committed to this file):
    /etc/letsencrypt/live/signals.mwiriadi.me/fullchain.pem
    /etc/letsencrypt/live/signals.mwiriadi.me/privkey.pem
- Auto-renewal: certbot's systemd timer (certbot.timer) is enabled
- nginx version on droplet: 1.24 (Ubuntu 22.04/24.04 stock) — does NOT support
  the standalone `http2 on;` directive (added in nginx 1.25). Must use the
  inline `listen 443 ssl http2;` form.
- Why `certbot certonly --standalone` and not `certbot --nginx`:
    The repo's 443 block exists BEFORE any cert is issued. `certbot --nginx`
    runs `nginx -t` to validate before injecting cert paths, but a 443 block
    with NO ssl_certificate fails `nginx -t`. Chicken-and-egg. `certonly
    --standalone` sidesteps nginx entirely (briefly stops it, runs HTTP-01 on
    port 80) and just writes the cert files. Operator then adds
    `ssl_certificate*` directives manually and reloads.
- Operator decision: cert path leak into git is acceptable for this single-
  domain deployment (no multi-tenant cert juggling).
</deployment_facts>

<duplicate_file_facts>
- `nginx/signals 2.conf` is untracked (git status shows it as `?? "nginx/signals 2.conf"`)
- It's a Finder/macOS duplicate created during file copy
- Diff vs `nginx/signals.conf` (verified during planning):
    Lines 28-29 differ only — duplicate uses standalone `http2 on;`
    (nginx 1.25+ syntax), main file uses inline `listen 443 ssl http2;`
    (nginx 1.24 compat).
- Otherwise byte-identical → safe to delete the duplicate. Filesystem-only
  delete (no `git rm` since it's untracked).
</duplicate_file_facts>

<port_80_block_design>
<!-- The exact block to append at the END of nginx/signals.conf in Task 2.
     Designed to NOT conflict with the existing 443 server block. -->

```
# --- Port-80 redirect (WEB-04, D-12) ---
# Originally certbot --nginx would have injected this block automatically
# on first run. Because we used certbot certonly --standalone instead (see
# top-of-file comments for why), we maintain this block manually.
#
# /.well-known/acme-challenge/ is preserved as a try_files carve-out so any
# manual cert renewal that uses --webroot mode can serve files. The current
# automated renewal uses certonly --standalone (briefly stops nginx) so this
# carve-out is a safety net, not the primary path.
server {
  listen 80;
  listen [::]:80;
  server_name signals.mwiriadi.me;

  location /.well-known/acme-challenge/ {
    try_files $uri =404;
  }

  location / {
    return 301 https://$host$request_uri;
  }
}
```

Properties:
- Sits at end of file, fully outside the existing 443 server block — zero
  syntactic interaction risk.
- `server_name` matches the 443 block exactly.
- ACME location uses the same `try_files $uri =404;` pattern the 443 block
  uses (line 69), so the renewal-tooling story is consistent across both.
- 301 (permanent) per D-12, not 302.
- `$host` (request Host header) preferred over `$server_name` so multi-domain
  expansion is trivial later.
</port_80_block_design>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Reconcile nginx/signals.conf comment block with deployed reality</name>
  <files>nginx/signals.conf</files>
  <action>
Update the comment narrative in `nginx/signals.conf` to match the actually-
deployed bootstrap path. Three regions need changes; preserve everything
else byte-for-byte.

REGION A — top-of-file header (current lines 1-19):

Replace the existing block with a tighter, accurate version. Keep the file-
identifier header line. The new block must convey:
- Domain is hardcoded to signals.mwiriadi.me (D-01 placeholder substitution
  was completed during droplet bring-up — the literal `<owned-domain>` is
  no longer present).
- Cert was bootstrapped via `certbot certonly --standalone -d signals.mwiriadi.me`
  using HTTP-01 challenge. NOT `certbot --nginx`.
- Reason: a 443 block with no cert fails `nginx -t`, which `certbot --nginx`
  runs before it would inject cert paths — chicken-and-egg. `certonly
  --standalone` runs its own webserver on port 80 and writes only the cert
  files; nginx ssl_certificate paths were then added manually below.
- Cloudflare DNS proxy must be DISABLED (grey-cloud) during ACME or HTTP-01
  fails with 521 at origin. Re-enable proxy AFTER cert issuance is fine
  because Cloudflare terminates TLS independently.
- http2 directive uses inline `listen 443 ssl http2;` form because Ubuntu
  22.04/24.04 ships nginx 1.24 which doesn't support standalone `http2 on;`
  (added in nginx 1.25).
- Auto-renewal handled by certbot.timer systemd unit. Manual renewal would
  also use `certonly --standalone` (briefly stop nginx, run certbot, restart).
- Phase 12 requirements covered: WEB-03 (nginx + Let's Encrypt + certbot
  timer) and WEB-04 (HSTS exact value per D-12; HSTS preload submission
  intentionally omitted to keep TLS rollback escape hatch).
- Operator decision: cert paths in git is acceptable for this single-domain
  deployment.

Keep tight — the existing block is well-structured narrative comments;
match that voice and density. No novelistic prose. Aim for similar line
count to what's being replaced.

REGION B — OCSP-stapling note (current lines 50-52):

Replace:
```
  # NOTE: ssl_certificate + ssl_certificate_key directives are NOT in this file.
  # Certbot injects them on first run; committing them here creates
  # non-idempotent re-runs and leaks cert paths into git history.
```

With (one-line note above the actual ssl_certificate lines):
```
  # ssl_certificate paths added manually after `certbot certonly --standalone`
  # bootstrap (see top-of-file). Cert path leak into git is accepted for this
  # single-domain deployment.
```

Make sure the actual `ssl_certificate /etc/letsencrypt/live/signals.mwiriadi.me/fullchain.pem;`
and `ssl_certificate_key /etc/letsencrypt/live/signals.mwiriadi.me/privkey.pem;`
directives remain immediately below, untouched.

REGION C — OCSP comment cleanup (current lines 43-44):

The comment "certbot injects `ssl_trusted_certificate` post-issuance; until
then nginx silently fail-softs stapling (no crash)" is now half-stale —
certbot didn't inject anything because we used certonly. Replace with:
```
  # OCSP stapling uses the chain from ssl_certificate (fullchain.pem) — no
  # separate ssl_trusted_certificate needed when fullchain is in use.
```

CONSTRAINTS:
- Do NOT modify the 443 server block's executable directives (listen, TLS
  tuning, security headers, location blocks, proxy_* lines).
- Do NOT modify line 25 (`limit_req_zone $binary_remote_addr ...`).
- Do NOT remove the `# [CITED: ...]` markers — those are sourced citations
  and should survive intact.
- Preserve the `--- TLS tuning ---`, `--- OCSP stapling ---`, `--- Security
  headers ---`, `--- Let's Encrypt ACME challenge carve-out ---`, `---
  /healthz ---`, `--- Everything else ---` section dividers exactly as they
  appear today.
- All `add_header ... always` directives stay verbatim, including the HSTS
  exact value `max-age=31536000; includeSubDomains` per D-12.

Commit message:
```
docs(quick-260426-vcw): reconcile nginx/signals.conf comments with deployed state

The repo's narrative comments described a `certbot --nginx` bootstrap that
was never used. Actual droplet bring-up used `certbot certonly --standalone`
(HTTP-01) because the committed 443 block fails `nginx -t` before any cert
exists, and `certbot --nginx` runs `nginx -t` before injecting cert paths.

Comments now describe:
- The certonly --standalone bootstrap and why
- Cloudflare grey-cloud requirement during ACME
- Inline `listen 443 ssl http2;` form for nginx 1.24 compat
- Manual ssl_certificate paths (operator-accepted git leak)
- Auto-renewal via certbot.timer

No executable directives changed. Pure documentation reconciliation.
```
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && grep -q "certbot certonly --standalone" nginx/signals.conf && grep -q "signals.mwiriadi.me" nginx/signals.conf && ! grep -q "<owned-domain>" nginx/signals.conf && ! grep -q "this file deliberately has NO port-80 block and NO cert paths" nginx/signals.conf && grep -q "ssl_certificate /etc/letsencrypt/live/signals.mwiriadi.me/fullchain.pem" nginx/signals.conf && grep -q "listen 443 ssl http2" nginx/signals.conf && grep -q "limit_req_zone \$binary_remote_addr zone=healthz:10m rate=10r/m" nginx/signals.conf && grep -q "Strict-Transport-Security 'max-age=31536000; includeSubDomains' always" nginx/signals.conf && echo "OK"</automated>
  </verify>
  <done>
    - Top-of-file comments describe `certbot certonly --standalone` bootstrap, Cloudflare grey-cloud requirement, nginx 1.24 inline-http2 reason, and manual cert path acceptance.
    - The stale claim "this file deliberately has NO port-80 block and NO cert paths" is gone.
    - The literal `<owned-domain>` placeholder no longer appears anywhere in the file.
    - `ssl_certificate` and `ssl_certificate_key` directives at signals.mwiriadi.me paths remain present and unchanged.
    - 443 server block executable directives (listen, TLS tuning, security headers, location blocks) are byte-identical to pre-edit state.
    - HSTS header value `max-age=31536000; includeSubDomains` is unchanged.
    - `limit_req_zone` line at http{} scope (line ~25) is unchanged.
    - One atomic commit on the local branch with the docs(quick-260426-vcw) message above.
  </done>
</task>

<task type="auto">
  <name>Task 2: Add port-80 → port-443 redirect server block</name>
  <files>nginx/signals.conf</files>
  <action>
Append the port-80 redirect server block to the END of `nginx/signals.conf`,
AFTER the closing `}` of the existing 443 server block. Use the exact block
specified in `<port_80_block_design>` in the context section above.

Placement rules:
- One blank line between the closing `}` of the 443 block and the new
  `# --- Port-80 redirect (WEB-04, D-12) ---` comment header.
- The block goes at end-of-file (no trailing content after it). End the file
  with a single trailing newline (POSIX-correct text file).
- Do NOT touch the 443 server block — only append.
- Do NOT touch the `limit_req_zone` directive at http{} scope (line 25).

Properties of the appended block:
- `listen 80;` and `listen [::]:80;` (IPv4 + IPv6).
- `server_name signals.mwiriadi.me;` — matches the 443 block exactly.
- `location /.well-known/acme-challenge/` carve-out using the same
  `try_files $uri =404;` pattern as the 443 block. This is a safety net
  for `--webroot`-style manual renewal; the actual automated renewal uses
  certonly --standalone (briefly stops nginx) which doesn't need this
  carve-out, but having it here is cheap insurance.
- `location /` returns `301 https://$host$request_uri;` (permanent redirect
  per D-12, $host so multi-domain expansion stays trivial).
- Comment block above the server block explains why this exists (we did NOT
  use certbot --nginx so the redirect block was never auto-injected).

Syntax-validation strategy:
This is a deployment-ready block. Local nginx is not installed (verified
during planning) so `nginx -t -c <file>` cannot run locally. Instead:
- Visually confirm balanced braces in the appended block (3 opening `{`,
  3 closing `}` — one for server, two for location).
- Confirm exactly one trailing semicolon on each directive.
- Confirm the file ends with a single `\n`.
- Operator will run `sudo nginx -t` on the droplet AFTER pulling, BEFORE
  reload — this is the authoritative validation.

Commit message:
```
feat(quick-260426-vcw): add port-80 → 443 redirect server block (WEB-04, D-12)

The droplet's nginx config was bootstrapped with `certbot certonly
--standalone` instead of `certbot --nginx`, so the HTTP→HTTPS redirect
block that --nginx would have auto-injected was never created in the repo.

This commit adds the redirect block manually:
- listen 80 / [::]:80
- server_name signals.mwiriadi.me
- /.well-known/acme-challenge/ try_files carve-out (safety net for any
  --webroot-mode manual renewal)
- All other paths → 301 https://$host$request_uri

Operator deploys via `git pull && sudo nginx -t && sudo systemctl reload
nginx` on the droplet. No code-side changes (FastAPI app on 127.0.0.1:8000
is unchanged).

Closes the WEB-04 / D-12 gap between repo and live droplet.
```
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && grep -q "listen 80;" nginx/signals.conf && grep -q "listen \[::\]:80;" nginx/signals.conf && grep -q "return 301 https://\$host\$request_uri;" nginx/signals.conf && grep -c "server_name signals.mwiriadi.me" nginx/signals.conf | awk '$1==2 {exit 0} {exit 1}' && grep -c "location /.well-known/acme-challenge/" nginx/signals.conf | awk '$1==2 {exit 0} {exit 1}' && [ "$(awk '/^server {/{c++} END{print c}' nginx/signals.conf)" = "2" ] && [ "$(grep -c '^}' nginx/signals.conf)" = "2" ] && tail -c 1 nginx/signals.conf | od -An -c | grep -q '\\n' && echo "OK"</automated>
  </verify>
  <done>
    - Port-80 server block appended at end of file with the exact directives in `<port_80_block_design>`.
    - Exactly two `server {` blocks in the file (the existing 443 + the new 80).
    - Exactly two top-level `^}` closing braces in the file.
    - Both server blocks declare `server_name signals.mwiriadi.me;`.
    - Both server blocks have a `/.well-known/acme-challenge/` location with `try_files $uri =404;`.
    - The 80→443 redirect uses `return 301 https://$host$request_uri;` (permanent, D-12 compliant).
    - File ends with a single trailing newline.
    - 443 block is unchanged byte-for-byte from end of Task 1.
    - One atomic commit on the local branch with the feat(quick-260426-vcw) message above.
  </done>
</task>

<task type="auto">
  <name>Task 3: Delete macOS-Finder-duplicate `nginx/signals 2.conf`</name>
  <files>nginx/signals 2.conf</files>
  <action>
Delete the untracked Finder-duplicate file. Pre-flight diff was already run
during planning; the only difference from `nginx/signals.conf` is the
nginx-1.25-style standalone `http2 on;` directive (vs the inline
`listen 443 ssl http2;` form that this repo and the droplet's nginx 1.24
require). The duplicate is therefore stale-and-broken-on-droplet, not a
better version of anything.

Re-confirm with `diff` immediately before deletion as a final safety check
(planning ran the diff but the working tree may have changed since):
```
diff "nginx/signals.conf" "nginx/signals 2.conf"
```
Expected: only the `listen` / `http2` lines differ. If anything else
differs (especially server_name, cert paths, location blocks, security
headers), STOP and surface the unexpected delta — do NOT delete blindly.

If the diff is as expected, delete:
```
rm "nginx/signals 2.conf"
```

Since the file is UNTRACKED (visible in git status as `?? "nginx/signals 2.conf"`),
this is a filesystem-only operation. Do NOT use `git rm` — there's nothing
in the index to remove.

After `rm`, the file should disappear from `git status` entirely (no longer
listed as `??`).

Commit handling:
The duplicate was never tracked, so there's nothing to commit for the
deletion itself. However, per the task spec ("three atomic commits required,
in order"), record this cleanup as an empty-tree-change documentation
commit ONLY IF the workflow expects it. PREFERRED PATH: skip the commit
entirely — `git commit --allow-empty` would lie in the history about the
nature of the change. Instead, surface in the SUMMARY that the file was
removed and explain WHY no commit was created.

If the orchestrator strictly requires three commits, fall back to:
```
git commit --allow-empty -m "chore(quick-260426-vcw): remove untracked nginx/signals 2.conf duplicate

Finder-created duplicate of nginx/signals.conf with stale nginx-1.25-style
\`http2 on;\` directive. Untracked, so removal is filesystem-only — this
commit is empty and exists only to document the cleanup in the audit trail.
"
```

DEFAULT: skip the empty commit; record the deletion in the SUMMARY only.
This gives the operator a cleaner history.

Final state check:
- `nginx/signals 2.conf` does not exist on disk.
- `git status` shows no `?? "nginx/signals 2.conf"` line.
- `nginx/signals.conf` is unchanged from the end of Task 2.
  </action>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && [ ! -e "nginx/signals 2.conf" ] && ! git status --short | grep -q "nginx/signals 2.conf" && [ -f "nginx/signals.conf" ] && echo "OK"</automated>
  </verify>
  <done>
    - `nginx/signals 2.conf` no longer exists on the filesystem.
    - `git status` does not list the duplicate as untracked anymore.
    - `nginx/signals.conf` survives intact at its post-Task-2 state.
    - Pre-deletion `diff` was re-run and confirmed only the http2-syntax line differed (no surprise content in the duplicate).
    - Either: (a) no commit was created (preferred — file was untracked), with the deletion noted in SUMMARY; OR (b) one empty audit commit with the chore(quick-260426-vcw) message above.
  </done>
</task>

</tasks>

<verification>
After all three tasks complete, verify the end-state:

1. `git log --oneline -5` shows the two real commits (Task 1 docs, Task 2 feat) in order; optionally a third empty chore commit from Task 3 fallback path.
2. `git status` is clean — no untracked `nginx/signals 2.conf`, no unstaged changes in `nginx/signals.conf`.
3. `wc -l nginx/signals.conf` is greater than the original (97 lines pre-task) due to the appended port-80 block. Expected: ~115-125 lines depending on exact comment density.
4. `grep -c "^server {" nginx/signals.conf` returns exactly `2`.
5. `grep -c "^}" nginx/signals.conf` returns exactly `2`.
6. The 443 block is byte-identical (executable directives only) to pre-Task-1: `git log -p -- nginx/signals.conf` should show comment-only diffs in the 443 block region across both commits.
7. Operator-side (NOT part of this plan, documented for SUMMARY): on droplet, `git pull && sudo nginx -t` must report `syntax is ok` and `test is successful` before `sudo systemctl reload nginx`.
</verification>

<success_criteria>
- Three atomic local commits land in order (or two commits + documented Task-3 cleanup if the empty-commit fallback is rejected).
- `nginx/signals.conf` accurately documents the deployed certbot certonly --standalone bootstrap, the Cloudflare grey-cloud ACME requirement, and the nginx 1.24 inline-http2 reason.
- `nginx/signals.conf` contains a working port-80 → 443 redirect block with ACME carve-out, syntactically self-consistent (balanced braces, terminated directives, trailing newline).
- `nginx/signals 2.conf` is deleted from the working tree.
- 443 server block executable directives are unchanged byte-for-byte by the comment reconciliation.
- All Phase 12 requirements remain covered: WEB-03 (nginx + LE + auto-renewal documented), WEB-04 (HSTS still at exact D-12 value, HTTP→HTTPS redirect now in repo), D-12 (301 permanent redirect).
- Operator can `git pull` on the droplet, run `sudo nginx -t` (must pass), and `sudo systemctl reload nginx` to bring the live config exactly into sync with the repo.
</success_criteria>

<output>
After completion, create `.planning/quick/260426-vcw-phase-12-https-reconcile-sync-nginx-sign/260426-vcw-SUMMARY.md` covering:
- The three commits (or two + skipped Task-3 commit) and their hashes
- The exact comment-region diff for Task 1 (REGION A / B / C)
- The appended port-80 block verbatim
- Confirmation that `nginx/signals 2.conf` is gone
- Operator next-action: `ssh root@209.38.30.13 'cd /path/to/repo && git pull && sudo nginx -t && sudo systemctl reload nginx'` (operator runs this; NOT part of this plan)
- Any deviation from plan (e.g. if Task 3 produced an empty audit commit instead of skipping)
</output>
