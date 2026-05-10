---
phase: 26
plan: 01
status: complete
date: 2026-05-07
---

# Plan 26-01 — Secret audit + .gitignore extension + AGENTS.md placement

## auth.json audit verdict

- `git log --all --full-history -- auth.json` → **0 commits**. File never landed in git.
- Already gitignored at `.gitignore:2` since Phase 13.
- File contents (local FS only): TOTP secret + enrolment metadata.
- **Operator decision: accept-as-is.** No rotation required — secret never crossed git boundary. Lives only on local dev FS + production droplet.

## .gitignore extension

Added Phase 26 section covering:
- `**/.DS_Store` — Finder metadata, recursive
- `**/._*` — macOS AppleDouble metadata sidecars (e.g. `._debug_new_dashboard.html`)
- `_debug_new_dashboard.html` — ad-hoc debug export
- `.agents/`, `.claude/`, `.claude-flow/`, `.codex/`, `.cowork/`, `.cursor/`, `.playwright-mcp/` — per-machine agent runtime dirs
- `.mcp.json` — per-machine MCP server tokens

Verification: `git check-ignore -v` returns hits for all 10 patterns.

## AGENTS.md placement decision

**Operator decision: commit at repo root.** Matches CLAUDE.md convention; discoverable on GitHub front page.

## Out of scope (deferred)

- `.planning/backtests/v1.2.0-*.json` — per-machine backtest runs; track separately if needed.
- `.planning/phases/25-.../25-helper-text-locked.md` — orphan Phase 25 artifact; commit/archive in Phase 25 cleanup.
- `.planning/v1.2-MILESTONE-AUDIT.md` — orphan milestone artifact; align in milestone close.

## Files

- `.gitignore` (extended)
- `AGENTS.md` (committed at repo root)
