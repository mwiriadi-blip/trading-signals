# scenarios.README.md — 9 synthetic scenario fixtures

This file documents the deterministic construction recipes for the 9 synthetic scenario
fixtures under `tests/fixtures/scenario_*.csv`, covering every branch of the signal
truth table per `.planning/phases/01-signal-engine-core-indicators-vote/01-CONTEXT.md`
§D-16.

## Shared conventions

All synthetic scenarios (except scenario 9 — flat prices) use this construction:

- **Close:** the defining series per scenario below.
- **High:** `Close * 1.005`
- **Low:** `Close * 0.995`
- **Open:** `closes[i - 1]` for `i >= 1`; `closes[0]` for bar 0.
- **Volume:** `1000` (constant).
- **Dates:** start 2020-01-01, advance by 1 calendar day per bar (pandas `freq='D'`).
- **CSV precision:** `float_format='%.17g'` (per RESEARCH Pitfall 4).
  - Note: `%.17g` formats `100.0` as the string `100` — this is the C `%g` spec. When
    loaded back via `pd.read_csv` and cast `astype('float64')`, the round-trip is
    bit-identical (`0x1.9000000000000p+6`). The scenario 9 bit-identical check tests
    the bit pattern, not the text form.
- **Mom lookbacks:** `Mom1 = 21`, `Mom3 = 63`, `Mom12 = 252`. Thresholds `±0.02` use
  strict inequalities (`>`, `<`) — `Mom == ±0.02` exactly abstains.
- **ADX gate:** `ADX >= 25.0` opens the vote; `ADX < 25.0` (and `NaN ADX`) forces FLAT.

Scenarios 3, 5, 6, 8 have Mom/ADX constraints verified at generation time. The
generator snippet (NOT committed — throwaway) in the Task 1 execution step runs
assertion checks on close-series endpoints before writing each CSV. Recipes below are
the authoritative spec; the generator is reproducible from this file.

## Scenario 1: `scenario_adx_below_25_flat.csv`

- **Bars:** 80
- **Expected signal:** `FLAT` (0) — covers **SIG-05** (ADX < 25 ⇒ FLAT).
- **Recipe (close):** `closes[i] = 100.0 + 0.1 * sin(i * 0.3)` for `i ∈ [0, 80)`.
- **Rationale:** tiny amplitude (0.1) keeps directional movement near zero so ADX
  stays well under 25. The signal is FLAT regardless of Mom values because the gate
  is not open.
- **Covers:** SIG-05.

## Scenario 2: `scenario_adx_above_25_long_3_votes.csv`

- **Bars:** 280 (clears Mom12 warmup of 252 + ADX warmup of 38)
- **Expected signal:** `LONG` (1) — covers **SIG-06** (ADX ≥ 25 + 3-vote up ⇒ LONG).
- **Recipe (close, exact segment endpoints):**
  - Bars 0–29 (30 bars): flat `Close = 100.0`.
  - Bars 30–269 (240 bars): linear downtrend from `Close[30] = 100.0` to `Close[269] = 80.0`.
  - Bars 270–279 (10 bars): linear uptrend from `Close[270] = 80.0` to `Close[279] = 110.0`.
- **Last-bar verification:**
  - `Mom1 = (110 - close[258])/close[258]`; `close[258]` on downtrend near 82.5 ⇒ Mom1 ≈ +0.33 ⇒ **UP**.
  - `Mom3 = (110 - close[216])/close[216]`; `close[216]` on downtrend near 89.9 ⇒ Mom3 ≈ +0.22 ⇒ **UP**.
  - `Mom12 = (110 - close[27])/close[27] = (110 - 100)/100 = +0.10` ⇒ **UP**.
  - ADX ≥ 25 from the strong trend reversal.
- **Covers:** SIG-06.

## Scenario 3: `scenario_adx_above_25_long_2_votes.csv`

- **Bars:** 280
- **Expected signal:** `LONG` (1) — covers **SIG-06** (2-vote up, Mom12 abstains).
- **Recipe (close, exact segment endpoints):**
  - Bars 0–17 (18 bars): flat `Close = 100.0`.
  - Bars 18–256 (239 bars): linear downtrend from `Close[18] = 100.0` to `Close[256] = 80.0`.
  - Bars 257–275 (19 bars): linear uptrend from `Close[257] = 80.0` to `Close[275] = 97.5`.
  - Bars 276–278 (3 bars): flat at `Close = 97.5`.
  - Bar 279: `Close[279] = 99.7`.
- **Last-bar verification targets:**
  - `Mom1 = (99.7 - close[258])/close[258]` > +0.02 ⇒ **UP**.
  - `Mom3 = (99.7 - close[216])/close[216]` > +0.02 ⇒ **UP**.
  - `Mom12 = (99.7 - close[27])/close[27]`; `close[27]` on downtrend near 99.24 ⇒
    Mom12 ≈ +0.0046 (inside `[-0.02, +0.02]`) ⇒ **ABSTAINS**.
  - ADX ≥ 25 from the large trend reversal.
- **Covers:** SIG-06 (2-of-2 non-NaN agreement with Mom12 abstention).
- **Executor:** after running `tests/regenerate_goldens.py`, verify the Mom1>+0.02,
  Mom3>+0.02, Mom12∈[-0.02,+0.02], ADX≥25 constraints hold. If any fail, adjust
  `Close[279]` by ±0.5 and re-run. Document final endpoints in the per-plan SUMMARY.

## Scenario 4: `scenario_adx_above_25_short_3_votes.csv`

- **Bars:** 280
- **Expected signal:** `SHORT` (-1) — covers **SIG-07** (ADX ≥ 25 + 3-vote down ⇒ SHORT).
- **Recipe (close, exact segment endpoints) — mirror of scenario 2:**
  - Bars 0–29 (30 bars): flat `Close = 80.0`.
  - Bars 30–269 (240 bars): linear uptrend from `Close[30] = 80.0` to `Close[269] = 100.0`.
  - Bars 270–279 (10 bars): linear downtrend from `Close[270] = 100.0` to `Close[279] = 70.0`.
- **Last-bar verification:** all 3 moms < -0.02; ADX ≥ 25.
- **Covers:** SIG-07.

## Scenario 5: `scenario_adx_above_25_short_2_votes.csv`

- **Bars:** 280
- **Expected signal:** `SHORT` (-1) — covers **SIG-07** (2-vote down, Mom12 abstains).
- **Recipe (close, exact segment endpoints) — mirror of scenario 3:**
  - Bars 0–17 (18 bars): flat `Close = 100.0`.
  - Bars 18–256 (239 bars): linear uptrend from `Close[18] = 100.0` to `Close[256] = 120.0`.
  - Bars 257–275 (19 bars): linear downtrend from `Close[257] = 120.0` to `Close[275] = 102.5`.
  - Bars 276–278 (3 bars): flat at `Close = 102.5`.
  - Bar 279: `Close[279] = 100.3`.
- **Last-bar verification targets:** Mom1 < -0.02, Mom3 < -0.02, Mom12 abstains, ADX ≥ 25.
- **Covers:** SIG-07.
- **Executor:** same verification/re-tune note as scenario 3.

## Scenario 6: `scenario_adx_above_25_split_vote_flat.csv`

**MUST FIX per REVIEWS.md §MUST FIX:** this scenario uses the correct split-vote pattern
`1 up / 1 down / 1 abstain` ⇒ FLAT. The original plan draft described `2 up / 1 down`
which is actually LONG per SIG-06 — that was a self-contradiction caught in cross-AI
review.

- **Bars:** 280
- **Expected signal:** `FLAT` (0) — covers **SIG-08** (gate open, no 2-vote majority).
- **Recipe (close, exact segment endpoints):**
  - Bars 0–17 (18 bars): flat `Close = 100.0`.
  - Bars 18–130 (113 bars): linear uptrend from `Close[18] = 100.0` to `Close[130] = 110.0`.
  - Bars 131–216 (86 bars): linear downtrend from `Close[131] ≈ 109.94` to `Close[216] = 105.0`.
  - Bars 217–258 (42 bars): linear downtrend from `Close[217] ≈ 104.76` to `Close[258] = 95.0`.
  - Bars 259–278 (20 bars): linear uptrend from `Close[259] ≈ 95.2` to `Close[278] = 99.0`.
  - Bar 279: `Close[279] = 100.5`.
- **Last-bar verification (computed by generator and written to SUMMARY):**
  - `close[27]` = 100.804 (bar 27 is on the 18–130 uptrend).
  - `close[216]` = 105.0 exactly.
  - `close[258]` = 95.0 exactly.
  - `Mom1 = (100.5 - 95.0)/95.0 ≈ +0.0579 > +0.02` ⇒ **UP**.
  - `Mom3 = (100.5 - 105.0)/105.0 ≈ -0.0429 < -0.02` ⇒ **DOWN**.
  - `Mom12 = (100.5 - 100.804)/100.804 ≈ -0.00301 ∈ [-0.02, +0.02]` ⇒ **ABSTAINS**.
  - ADX ≥ 25 from the long trending path.
- **Covers:** SIG-08.
- **Executor:** verify computed `(mom1, mom3, mom12, adx)` at bar 279 before accepting
  the golden. If any constraint fails, adjust `Close[130]`, `Close[216]`, `Close[258]`,
  or `Close[279]` by ±1.0 and re-run.

## Scenario 7: `scenario_warmup_nan_adx_flat.csv`

- **Bars:** 30 (deliberately < 38-bar ADX warmup)
- **Expected signal:** `FLAT` (0) — covers **D-09** (NaN ADX ⇒ FLAT).
- **Recipe (close):** `closes[i] = 100.0 + sin(i * 0.5)` for `i ∈ [0, 30)`.
- **Rationale:** ADX(20) needs 2 × 20 − 2 = 38 bars to produce a non-NaN value; with
  only 30 bars, the last-bar ADX is NaN, which forces FLAT via D-09.
- **Covers:** D-09.

## Scenario 8: `scenario_warmup_mom12_nan_two_mom_agreement.csv`

- **Bars:** 80 (≥38 for ADX, <253 for Mom12 ⇒ Mom12 stays NaN)
- **Expected signal:** `LONG` (1) — covers **D-10** (NaN Mom12 + 2-of-2 agreement on
  Mom1 + Mom3 ⇒ LONG).
- **Recipe (close, exact segment endpoints):**
  - Bars 0–29 (30 bars): flat `Close = 100.0`.
  - Bars 30–59 (30 bars): linear downtrend from `Close[30] = 100.0` to `Close[59] = 90.0`.
  - Bars 60–79 (20 bars): linear uptrend from `Close[60] = 90.0` to `Close[79] = 105.0`.
- **Last-bar verification (computed by generator):**
  - `close[16]` = 100.0 (flat segment), `close[58]` ≈ 90.345 (end of downtrend).
  - `Mom1 = (105 - 90.345)/90.345 ≈ +0.162 > +0.02` ⇒ **UP**.
  - `Mom3 = (105 - 100)/100 = +0.05 > +0.02` ⇒ **UP**.
  - `Mom12 = NaN` (only 80 bars, need 253 for first non-NaN Mom12) ⇒ **ABSTAINS**.
  - ADX ≥ 25 from the trend reversal.
- **Covers:** D-10.
- **Executor:** verify `Mom1 > +0.02 AND Mom3 > +0.02 AND Mom12 is NaN AND ADX ≥ 25`.
  If Mom3 fails, extend flat baseline and re-run.

## Scenario 9: `scenario_flat_prices_divide_by_zero.csv`

- **Bars:** 40
- **Expected signal:** `FLAT` (0) — covers **D-11** (flat-price NaN ADX) + **D-12**
  (bit-exact 0 RVol).
- **Recipe:** `Open = High = Low = Close = 100.0` bit-for-bit on every bar;
  `Volume = 0`. The CSV row as written is
  `YYYY-MM-DD,100,100,100,100,0` (the `%.17g` format writes `100.0` as `100` because
  that's the C `%g` behaviour; the round-tripped float64 value is bit-identical).
- **Pitfall 6 compliance:** bit-identical floats produce exactly `std = 0.0` via
  sum-of-squares = 0 ⇒ RVol = 0.0 exactly. Any float noise (e.g. `100.00001`) would
  produce tiny positive RVol and break D-12.
- **Covers:** D-11 (NaN ADX from sm_TR = 0) + D-12 (bit-exact 0 RVol).

---

## Regeneration

All 9 fixtures are committed artifacts. The generator snippet that authored them lives
inline in the Plan 01-03 Task 1 action block (see
`.planning/phases/01-signal-engine-core-indicators-vote/01-03-PLAN.md` and the
per-plan SUMMARY for the exact values reported at generation). The generator is NOT
committed as a standalone script because it should never run in CI — the fixture CSVs
ARE the trust anchor.

To regenerate a scenario fixture (e.g. after a threshold change in SPEC.md):

1. Update this README with the new recipe.
2. Run the snippet from the plan's Task 1 action block with the new values.
3. Run `.venv/bin/python tests/regenerate_goldens.py` to regenerate goldens.
4. Review git diff for both the scenario CSV and its paired JSON under
   `tests/oracle/goldens/scenario_*.json`.
