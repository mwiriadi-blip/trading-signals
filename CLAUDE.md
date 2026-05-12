# Claude Code Configuration

## Rules

- Do what has been asked; nothing more, nothing less
- NEVER create files unless absolutely necessary — prefer editing existing files
- NEVER create documentation files unless explicitly requested
- NEVER save working files or tests to root — use `tests/`, `docs/`, `scripts/`, named modules
- ALWAYS read a file before editing it
- NEVER commit secrets, credentials, or .env files
- Keep files under 500 lines
- Validate input at system boundaries

## Agent Comms

Named agents coordinate via `SendMessage`, not polling or shared state.

### Patterns

| Pattern | Flow | Use When |
|---------|------|----------|
| **Pipeline** | A → B → C → D | Sequential dependencies (feature dev) |
| **Fan-out** | Lead → A, B, C → Lead | Independent parallel work (research) |
| **Supervisor** | Lead ↔ workers | Ongoing coordination (complex refactor) |

### Rules

- ALWAYS name agents — `name: "role"` makes them addressable
- ALWAYS include comms instructions in prompts — who to message, what to send
- Spawn ALL agents in ONE message with `run_in_background: true`
- After spawning: STOP, tell user what's running, wait for results
- NEVER poll status — agents message back or complete automatically

## Swarm & Routing

### Agent Routing

| Task | Agents | Topology |
|------|--------|----------|
| Bug Fix | researcher, coder, tester | hierarchical |
| Feature | architect, coder, tester, reviewer | hierarchical |
| Refactor | architect, coder, reviewer | hierarchical |
| Performance | perf-engineer, coder | hierarchical |
| Security | security-architect, auditor | hierarchical |

### When to Swarm
- **YES**: 3+ files, new features, cross-module refactoring, API changes, security, performance
- **NO**: single file edits, 1-2 line fixes, docs updates, config changes, questions

## MCP Tools

Use `ToolSearch("keyword")` to discover tools. Common categories:

| Category | Key Tools |
|----------|-----------|
| **Memory** | `memory_store`, `memory_search`, `memory_search_unified` |
| **Swarm** | `swarm_init`, `swarm_status`, `swarm_health` |
| **Agents** | `agent_spawn`, `agent_list`, `agent_status` |
| **Hooks** | `hooks_route`, `hooks_post-task`, `hooks_worker-dispatch` |
| **Security** | `aidefence_scan`, `aidefence_is_safe`, `aidefence_has_pii` |

Background workers (dispatch via `hooks_worker-dispatch`):
`audit` · `optimize` · `testgaps` · `map` · `document`

## Agents

Core: `coder`, `reviewer`, `tester`, `researcher`, `planner`
Specialist: `system-architect`, `security-architect`, `security-auditor`, `performance-engineer`, `backend-dev`
GitHub: `pr-manager`, `code-review-swarm`, `release-manager`
Coordination: `hierarchical-coordinator`, `adaptive-coordinator`

Any string works as a custom agent type.

## Build & Test

- ALWAYS run tests after code changes
- ALWAYS verify build succeeds before committing

```bash
.venv/bin/pytest -x --tb=short           # full suite (Python 3.13)
.venv/bin/pytest -x --tb=short tests/test_<module>.py  # single file
```

## Architecture

Hexagonal-lite: pure-math hex (no I/O) vs I/O adapters.

| Layer | Modules | Constraint |
|-------|---------|------------|
| **Pure-math hex** | `signal_engine.py`, `sizing_engine/`, `system_params.py`, `pnl_engine.py`, `alert_engine.py`, `backtest/` | stdlib-only; zero I/O, network, or state imports |
| **State I/O** | `state_manager/` | File-based JSON (`state.json`); flock atomic writes via `mutate_state()` |
| **Orchestration** | `main.py`, `daily_run.py`, `daily_run_helpers.py`, `scheduler_driver.py` | Wires hex + I/O |
| **Notifications** | `notifier/` | Email via Resend HTTPS API only |
| **Web** | `web/` (FastAPI + HTMX), `web/routes/` | No SPA; HTMX only |
| **Auth** | `auth_store.py`, `web/routes/login/`, `web/routes/totp/` | Shared-secret + TOTP |

## Key Conventions

- **2-space indent** throughout — do NOT run `ruff format` (reflows to 4-space; breaks test gate)
- **`Decimal` for all AUD amounts** — no floats; `from decimal import Decimal, ROUND_HALF_UP`
- **`system_params.py` is single source of truth** for all constants — never define constants inline in engine modules
- **`mutate_state()` only** for state writes — never call `save_state()` directly inside a `mutate_state` callback (flock deadlock)
- **Signal-only** — never place, modify, or cancel live trades
