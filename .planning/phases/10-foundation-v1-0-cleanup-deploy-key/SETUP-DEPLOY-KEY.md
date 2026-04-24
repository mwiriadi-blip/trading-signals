# SETUP-DEPLOY-KEY.md — Droplet to GitHub write-back via SSH deploy key

**Phase 10 / INFRA-02 operator runbook.** One-time setup for the
DigitalOcean droplet to authenticate `git push` back to `origin/main`
so the daily run's `state.json` commit (via
`main.py::_push_state_to_git`) can land in the repo automatically.

**Audience:** project operator (Marc).
**Where this runs:** the DO droplet, as the user that runs the
`trading-signals` systemd unit (Phase 11+).
**Prerequisite:** GitHub repo admin access (to register the deploy key)
and SSH access to the droplet.
**Cost:** free.

> **Read first: `docs/DEPLOY.md` is stale.** That file still
> describes GitHub Actions as the primary deployment path (v1.0 era).
> It has not been rewritten yet — rewrite is deferred to a post-
> Phase-12 docs-sweep phase (see
> `.planning/phases/10-foundation-v1-0-cleanup-deploy-key/10-CONTEXT.md`
> §Deferred Ideas). For current v1.1 deployment guidance, use THIS
> file (`SETUP-DEPLOY-KEY.md`), `.planning/PROJECT.md` Deployment
> section, and `CLAUDE.md` §Stack.

***

## Quickstart

1. Generate a dedicated SSH keypair for this project on the droplet.
2. Register the public half as a Deploy Key with write access in the
   GitHub repo settings.
3. Configure `~/.ssh/config` on the droplet to route the github.com
   host through the new key.
4. Switch the repo remote from HTTPS to SSH.
5. Accept the github.com host key once (`ssh -T git@github.com`).
6. Run `python main.py --once` to verify the first push lands under
   the `DO Droplet <droplet@trading-signals>` author line.

Each step is detailed below.

***

## Step 1 — Generate the keypair

Run this on the droplet, as the user that will run the systemd unit
(NOT root unless your systemd unit runs as root).

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_trading_signals -C 'droplet@trading-signals'
# Do NOT set a passphrase — the systemd unit cannot supply one interactively.
chmod 0600 ~/.ssh/id_ed25519_trading_signals
chmod 0600 ~/.ssh/id_ed25519_trading_signals.pub
chmod 0700 ~/.ssh
```

**Expected:** two files in `~/.ssh/` — the private key (mode 0600) and
the public key (same mode for simplicity). `~/.ssh/` is mode 0700.

**Security:** the private key MUST NOT leave the droplet. It MUST NOT
be committed to this repo or any other. File mode `0600` (owner read
only) is enforced by SSH.

***

## Step 2 — Register the public key as a deploy key in GitHub

Copy the public key contents:

```bash
cat ~/.ssh/id_ed25519_trading_signals.pub
```

Paste the output into the GitHub web UI:

1. Open `https://github.com/<owner>/trading-signals/settings/keys`.
2. Click **Add deploy key**.
3. **Title:** `droplet-trading-signals`.
4. **Key:** paste the `ssh-ed25519 AAAA... droplet@trading-signals`
   line.
5. **Allow write access:** CHECK this box — the daily run pushes
   commits.
6. Click **Add key**.

**Verify:** the key now appears in the repo's deploy-keys list with a
write-access indicator.

***

## Step 3 — Configure ~/.ssh/config

Append this block to `~/.ssh/config` on the droplet (create the file
if it doesn't exist). This routes github.com SSH connections through
the dedicated key and prevents SSH agent forwarding from using some
other key.

```
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_trading_signals
  IdentitiesOnly yes
```

Then:

```bash
chmod 0600 ~/.ssh/config
```

**Pitfall:** without `IdentitiesOnly yes`, SSH may offer every key in
`~/.ssh/` or in the agent, get rejected repeatedly by GitHub, and
eventually fall over with "Too many authentication failures". Explicit
`IdentitiesOnly yes` + a single `IdentityFile` avoids this.

***

## Step 4 — Switch the repo remote from HTTPS to SSH

On the droplet, inside the cloned repo:

```bash
cd /path/to/trading-signals   # systemd unit WorkingDirectory
git remote -v
# Expected output BEFORE: origin https://github.com/<owner>/trading-signals.git (fetch/push)

git remote set-url origin git@github.com:<owner>/trading-signals.git
git remote -v
# Expected output AFTER: origin git@github.com:<owner>/trading-signals.git (fetch/push)
```

**Pitfall:** HTTPS remotes cache credentials (git-credential-helper)
and will SILENTLY fail push with a cryptic 401/403 if the cache
expires. SSH remotes use the deploy key every time — stateless.

***

## Step 5 — Accept the github.com host key once

SSH will refuse to connect to github.com until its host key is in
`~/.ssh/known_hosts`. Run this once, interactively, as the systemd
user:

```bash
ssh -T git@github.com
# Prompt: "The authenticity of host 'github.com (...)' can't be established."
# Answer: yes
# Expected final line: "Hi <owner>/trading-signals! You've successfully
# authenticated, but GitHub does not provide shell access."
```

**Expected:** `~/.ssh/known_hosts` now contains a `github.com` entry.
Subsequent non-interactive `git push` calls from the systemd unit
succeed because the host key is pre-trusted.

**If the final line says "Permission denied (publickey)":** re-check
Step 2 (deploy key registered) and Step 3 (~/.ssh/config IdentityFile
path correct).

***

## Step 6 — First-run bootstrap

This exercises the `_push_state_to_git` helper shipped in Plan 03:

```bash
cd /path/to/trading-signals
python main.py --once
```

**Expected:**
- The run completes with exit code 0.
- `tail -n 50 /var/log/trading-signals.log` (or systemd journal once
  the unit is installed in Phase 11) shows `[State] state.json pushed
  to origin/main`.
- `git log -1` on the droplet shows a new commit authored by
  `DO Droplet <droplet@trading-signals>` with message
  `chore(state): daily signal update [skip ci]`.
- The same commit appears in the GitHub web UI commit log.

If the helper instead logs `[State] state.json unchanged — skipping
git push`, that's fine too — it means the current state.json matches
what's already in `origin/main`. Force a diff and re-run, e.g.:

```bash
python main.py --reset --initial-account 100000 --spi-contract spi-mini --audusd-contract audusd-standard
python main.py --once
```

***

## Pitfalls

- **systemd WorkingDirectory.** The `_push_state_to_git` helper calls
  `subprocess.run(['git', ...])` without `cwd=`. The subprocess
  inherits the Python process's cwd. In Phase 11, the
  `trading-signals.service` unit file MUST include
  `WorkingDirectory=/path/to/trading-signals` so git finds the repo.
  If this is missing, the push fails with "fatal: not a git
  repository" and the helper writes a warning via
  `append_warning(source='state_pusher', ...)`.

- **Clock drift.** Commits use the droplet's system clock. Ensure
  `timedatectl` reports correct time + `Australia/Perth` timezone
  (Phase 11 will assert this via `_get_process_tzname`).

- **Deploy-key rotation.** Not scheduled for v1.1. Revisit when the
  project moves beyond single-operator ownership.

- **Rollback.** If the droplet path must be abandoned (domain issue,
  systemd regression), reverse Plan 04's `git mv` via
  `git mv .github/workflows/daily.yml.disabled .github/workflows/daily.yml`
  and re-enable the GHA schedule. GitHub repo secrets
  (`RESEND_API_KEY`, `SIGNALS_EMAIL_TO`) remain in place per D-17 to
  make this reversal one-commit.

- **README.md status badge.** The badge URL still points at
  `daily.yml/badge.svg`. Once GitHub Actions history ages out, the
  badge will render as "no recent runs" — this is the INTENDED visual
  signal that the workflow is retired per D-18(a). Do not "fix" it
  unless the rollback path is formally abandoned.

- **`docs/DEPLOY.md` is stale.** The file describes GitHub Actions as
  the primary deployment path (v1.0 content). Its Quickstart and
  "What the workflow does" sections DO NOT apply to the v1.1
  droplet-primary runtime. Rewrite is deferred to a post-Phase-12
  docs-sweep phase that can describe the full droplet + HTTPS +
  nginx + web-layer story coherently. For current v1.1 deployment
  guidance, use THIS file, `.planning/PROJECT.md` §Deployment, and
  `CLAUDE.md` §Stack. If you find yourself reading `docs/DEPLOY.md`
  during v1.1 operations, close it and open this file instead.

***

*Setup completed:* record the date in STATE.md §Accumulated Context
once Step 6 produces a visible GitHub commit.
