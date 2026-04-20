# Oracle — Pure-Python Golden-Value Reference

This directory contains the **dead-simple oracle** used to generate golden
indicator values. The oracle is intentionally separated from the production
module `signal_engine.py` so that a bug in production cannot also silently
appear in the oracle (D-02).

## 1. Oracle Contract

- The oracle is implemented as **pure Python loops** (per-bar recursion over
  lists of floats). No pandas vectorisation, no numpy tricks, no external TA
  library (`pandas-ta`, `TA-Lib`, and similar are forbidden by `CLAUDE.md` and
  by D-02). The oracle's only runtime dependency is the Python standard
  library; it does NOT import `signal_engine.py`.
- Each indicator (`wilder_atr`, `wilder_adx`, `mom`, `rvol`) is 3–5 lines per
  bar. If a future author cannot read the loop and see the formula, rewrite it.
- Results are returned as plain Python lists of floats, with `float('nan')`
  (not `None`) for warm-up bars.

## 2. Golden CSV Format

- Header row: `Date,ATR,ADX,PDI,NDI,Mom1,Mom3,Mom12,RVol` — exactly in that
  column order.
- Dates: ISO `YYYY-MM-DD` strings (matches `CLAUDE.md` §Conventions).
- Float precision: written with `df.to_csv(path, float_format='%.17g')`. The
  `%.17g` format preserves full float64 bit-for-bit (R-03, RESEARCH §Pitfall 4).
  The default pandas `%g` uses 6 significant digits and silently loses
  precision — never use it for goldens.
- NaN representation: pandas default `""` (empty field). Loader must use
  `read_csv(..., keep_default_na=True)` so empties round-trip back to NaN.

## 3. Scenario JSON Format

Each scenario fixture (`tests/fixtures/scenario_*.csv`) has a paired golden
JSON under `tests/oracle/goldens/scenario_*.json` of the form:

```json
{
  "expected_signal": 1,
  "last_row": {
    "atr": 42.1234567890,
    "adx": 31.5,
    "pdi": 24.0,
    "ndi": 12.0,
    "mom1": 0.035,
    "mom3": 0.041,
    "mom12": 0.08,
    "rvol": 0.18
  }
}
```

`expected_signal` is an int in {-1, 0, 1} matching `LONG=1, SHORT=-1, FLAT=0`.
`last_row` values are the indicator scalars at `df.iloc[-1]`.

## 4. Regeneration Procedure

Goldens are regenerated **manually** by running:

```bash
python tests/regenerate_goldens.py
```

This is a committed offline script that loads the canonical fixtures, runs the
oracle, and writes the golden CSV plus the scenario JSON files. It **never**
runs in CI (D-04). Any golden-CSV diff is the review surface when formulas
change deliberately.

## 5. Bar-0 True-Range Convention

For the True Range computation, the production code uses the pandas idiom:

```python
pd.concat([h - l, (h - c_prev).abs(), (l - c_prev).abs()], axis=1).max(axis=1)
```

At bar 0, `c_prev` is NaN so two of the three candidates are NaN. With
pandas' default `.max(axis=1, skipna=True)` this returns `high[0] - low[0]`.

**R-04 (operator-locked):** bar-0 TR = `high - low`. The oracle matches by
computing `trs[0] = highs[0] - lows[0]` directly. Any deviation from this
convention (e.g., returning NaN at bar 0) is a breaking change and must be
reflected in both oracle and production at the same commit.

## 6. Tolerance & Determinism Proof

- **Tolerance check** (per-bar human-readable): production vs oracle are
  compared using `numpy.testing.assert_allclose(actual, expected, atol=1e-9,
  equal_nan=True)`. 1e-9 is strict enough to catch formula errors and slack
  enough to survive ULP-level reordering from pandas internals.
- **Bit-level determinism** (per-run regression): on top of the tolerance
  check, `tests/determinism/snapshot.json` stores a SHA256 of each indicator
  series's underlying float64 bytes (D-14). Any numpy/pandas upgrade that
  shifts a single float bit will fail this check loudly — upgrades must be
  deliberate, and the snapshot regenerated in the same PR.

## 7. Ruff Format Caveat (R-05)

`ruff format` enforces 4-space indent and double quotes by default (inherited
from black). This project's `CLAUDE.md` §Conventions demands **2-space indent
and single quotes**. The ruff `[tool.ruff.format]` table in `pyproject.toml`
sets `indent-style = 'space'` and `quote-style = 'single'`, but ruff as of
0.6.x does **not** expose an `indent-width` knob — it still formats at
4 spaces. Therefore:

- `ruff format` is **not** used to auto-format source in Phase 1.
- `ruff check` **is** used (lint-only: `E`, `F`, `W`, `I`, `B`, `UP`).
- 2-space indent is enforced via `.editorconfig` + author/reviewer discipline
  + a grep-style test Plan 06 adds (`test_no_four_space_indent`) which greps
  `^    ` as the first four chars of any `.py` line.

Do not run `ruff format .` on this codebase without first disabling this
caveat in a follow-up plan.

## 8. Wilder Seed-Window NaN Rule

Wilder smoothing (used for ATR, smoothed TR, +DM, -DM, and DX) requires an
**SMA seed** at bar `period - 1`, computed as the arithmetic mean of
`series[0 : period]`. If **any** value in that seed window is NaN, the seed
itself is undefined and every output bar from `period - 1` onward remains
NaN until a full `period`-bar window of non-NaN input values exists.

Both the oracle and the production implementation **MUST** implement this
rule identically. Concretely:

- Oracle: `if any(math.isnan(v) for v in series[i - period + 1 : i + 1]):
  result[i] = float('nan')` at every candidate seed bar.
- Production: `series.iloc[:period].mean()` returns NaN by default if any
  element is NaN — but only at the first seed attempt. For subsequent
  warm-up windows (required when the input itself contains NaN gaps), the
  production code must re-check and re-seed deterministically.

This rule is restated here because it is the most common way for oracle and
production to silently diverge. If you are adding a new Wilder-smoothed
quantity, start from this rule, not from `ewm(alpha=...).mean()` on raw data.
