# Phase 14: Trade Journal — Mutation Endpoints — Discussion Log

> **Audit trail only.** Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-25
**Phase:** 14-trade-journal-mutation-endpoints
**Areas discussed:** Position-already-exists handling, Close endpoint field derivation, Modify endpoint scope, Write coordination

---

## Position-already-exists on /trades/open

### Q1 — Conflict handling

| Option | Selected |
|--------|----------|
| Reject with 409 Conflict | |
| Pyramid-up if same direction, reject if opposite | ✓ |
| Replace (overwrite) | |

### Q2 — Default fields for peak/trough/pyramid_level

| Option | Selected |
|--------|----------|
| peak/trough = entry_price; pyramid_level = 0 | |
| Allow client to override defaults | ✓ |

### Q3 — entry_date default

| Option | Selected |
|--------|----------|
| executed_at? optional, default today AWST | ✓ |
| Always today AWST, reject executed_at | |

### Q4 — Validation strategy

| Option | Selected |
|--------|----------|
| Pydantic with field-level constraints | ✓ |
| Manual validation in handler | |

### Follow-up Q1 — Pyramid gate

| Option | Selected |
|--------|----------|
| Apply sizing_engine.check_pyramid gate | ✓ |
| Skip the gate, always increment | |
| Skip but cap at MAX_PYRAMID_LEVEL | |

### Follow-up Q2 — Override consistency

| Option | Selected |
|--------|----------|
| Strict: full coherence checks | ✓ |
| Loose: only type/range checks | |
| No overrides | |

---

## Close endpoint — deriving the 6 missing trade fields

### Q1 — gross_pnl computation

| Option | Selected |
|--------|----------|
| Inline raw price-delta (anti-pitfall flagged) | ✓ |
| Call compute_unrealised_pnl + add back closing cost | |
| New helper sizing_engine.compute_gross_pnl | |

### Q2 — exit_reason

| Option | Selected |
|--------|----------|
| 'operator_close' | ✓ |
| 'manual' | |
| 'web_close' | |

### Q3 — multiplier and cost_aud source

| Option | Selected |
|--------|----------|
| state['_resolved_contracts'][instrument] | ✓ |
| Import system_params constants directly | |

### Q4 — exit_date default

| Option | Selected |
|--------|----------|
| executed_at? optional, default today AWST | ✓ |
| Always today AWST | |

---

## Modify endpoint scope

### Q1 — new_stop implementation

| Option | Selected |
|--------|----------|
| Add manual_stop field to Position TypedDict | ✓ |
| Reverse-engineer peak/trough | |
| Restrict modify to n_contracts only | |

### Q2 — new_contracts and pyramid_level

| Option | Selected |
|--------|----------|
| Up/down; reset pyramid_level to 0 | ✓ |
| Up/down; preserve pyramid_level | |
| Disallow decrease | |

### Q3 — Atomicity

| Option | Selected |
|--------|----------|
| Atomic single save_state | ✓ |
| Sequential, two saves | |

### Q4 — Empty modify

| Option | Selected |
|--------|----------|
| Require at least one field | ✓ |
| Allow empty no-op | |

---

## Write coordination with daily signal loop

### Q1 — Coordination strategy

| Option | Selected |
|--------|----------|
| fcntl exclusive lock on save_state | ✓ |
| Reject POSTs during signal-loop window | |
| Accept-the-race | |
| Optimistic concurrency (mtime check) | |

### Q2 — Lock location

| Option | Selected |
|--------|----------|
| Inside state_manager.save_state | ✓ |
| Wrapper in web/ | |
| sizing_engine helper (rejected — pure-math) | |

### Q3 — Phase 10 D-15 disposition

| Option | Selected |
|--------|----------|
| Explicit amendment + new D-XX | ✓ |
| Silently revise D-15 | |
| Keep D-15 historical, add carve-out | |

---

## Claude's Discretion

Captured in CONTEXT.md `<decisions>` §Claude's Discretion:
- HTMX partial response shape (per-row swap recommended)
- Inline error display on 400 (above form)
- CSRF posture (shared-secret header acts as token equivalent)
- Pydantic v2 import paths
- NotProvided sentinel for absent vs null in modify
- HTMX form HTML structure in dashboard.html
- Partial-close: explicitly out of scope (operator uses full-close + new-open)

## Deferred Ideas

Captured in CONTEXT.md `<deferred>` section:
- Partial-close support → v1.2
- Calculator banners + drift sentinels → Phase 15
- Rate-limit on /trades/* at nginx → Phase 16 hardening
- Audit log of successful mutations → v1.2
- Multi-position per instrument → v2.0
- Operator-supplied exit_reason variants → v1.2
- WebSocket broadcast of state changes → v1.2+
- NotProvided sentinel pattern → planner picks
