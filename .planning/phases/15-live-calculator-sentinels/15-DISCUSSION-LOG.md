# Phase 15: Live Calculator + Sentinels — Discussion Log

> **Audit trail only.** Decisions are captured in CONTEXT.md.

**Date:** 2026-04-26
**Phase:** 15-live-calculator-sentinels
**Areas discussed:** Drift detection placement/lifecycle, Forward-looking peak stop semantics, manual_stop in check_stop_hit, Banner aggregation + email integration

---

## Drift detection — placement, lifecycle, cleanup

### Q1 — Logic placement

| Option | Selected |
|--------|----------|
| Pure-math sizing_engine.detect_drift | ✓ |
| New module web/sentinels.py | |
| Inline in main.py + web/routes/dashboard.py | |

### Q2 — Warning lifecycle

| Option | Selected |
|--------|----------|
| Start-of-signal-run + after every mutate_state call | ✓ |
| Start-of-signal-run only | |
| Compute on-the-fly, don't persist | |

### Q3 — Email surface path

| Option | Selected |
|--------|----------|
| append_warning(source='drift') + extend _has_critical_banner | ✓ |
| Compute live in notifier render | |

### Q4 — Missing signal data

| Option | Selected |
|--------|----------|
| No drift event — absent signal can't disagree | ✓ |
| Treat missing signal as FLAT — flag drift | |

---

## Forward-looking peak stop semantics (SC-3)

### Q1 — Source of Z (today's high)

| Option | Selected |
|--------|----------|
| Operator-input field on dashboard | ✓ |
| Cached today's high from signal-loop fetch | |
| Live Yahoo intraday fetch on render | |
| Skip the live forward-look | |

### Q2 — Compute W

| Option | Selected |
|--------|----------|
| sizing_engine.get_trailing_stop with synthetic position | ✓ |
| Inline math in dashboard helper | |

### Q3 — Test lock

| Option | Selected |
|--------|----------|
| Bit-identical parity test | ✓ |
| End-to-end TestClient render check | |

### Q4 — Field placement

| Option | Selected |
|--------|----------|
| Inline per-position-row | ✓ |
| Single global input above table | |

---

## manual_stop in check_stop_hit — align or stay deferred?

### Q1 — Alignment

| Option | Selected |
|--------|----------|
| Stay deferred to v1.2 | ✓ |
| Align fully — honor in either direction | |
| Align asymmetrically — only-tighten | |

### Q2 — Dashboard display

| Option | Selected |
|--------|----------|
| Both stops side-by-side: 'manual: X | computed: Y (will close)' | ✓ |
| Manual badge + tooltip only (Phase 14 behavior) | |

---

## Drift banner aggregation + email integration

### Q1 — Aggregation

| Option | Selected |
|--------|----------|
| One merged banner listing both instruments | ✓ |
| Separate banner per instrument | |

### Q2 — Email body wording

| Option | Selected |
|--------|----------|
| Same wording, inline-CSS adapted | ✓ |
| Simplified for email (one-liner) | |

### Q3 — Stack ordering

| Option | Selected |
|--------|----------|
| Hierarchy: corruption > stale > reversal > drift | ✓ |
| Single combined banner | |

### Q4 — Banner copy template

| Option | Selected |
|--------|----------|
| Per-instrument: 'You hold {DIR} {INSTR}, today's signal is {NEW} — consider {action}' | ✓ |
| Generic: 'Position drift detected on N instrument(s) — review dashboard' | |

---

## Claude's Discretion (captured in CONTEXT.md §Claude's Discretion)

- Pyramid section markup details (CALC-04)
- CSS for side-by-side manual|computed display
- Forward-look input default value (placeholder vs computed-default)
- Performance: drift recomputed on every render (no caching for v1.1)
- HTMX swap target for forward-look (closest .w-cell vs explicit ID)
- Email banner inline-CSS color reuse

## Deferred Ideas (captured in CONTEXT.md §Deferred Ideas)

- Aligning check_stop_hit with manual_stop → v1.2 (3 sub-options open)
- Yahoo intraday data fetch → v1.2
- Banner for "no signal data — manual fallback" → v1.2
- Email digest of drift events over time → v1.2+
- Caching detect_drift output → profile-driven, not needed
- Shared `_render_drift_banner` helper module → v1.2 refactor
- Audit log of historical drift events → v1.2 forensics
- Visual cue for level=MAX_PYRAMID_LEVEL "fully pyramided" → v1.2 polish
- Operator-saved default Z per instrument → v1.2 preference
