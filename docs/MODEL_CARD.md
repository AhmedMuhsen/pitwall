# Model card: PitWall lap-time model and strategy simulator

A learning project, not affiliated with Formula 1, the FIA or FOM. Written 2026-11-19 from the repository as of that date. Every
number below is traced to a command or file in [the last section](#where-each-number-comes-from).

## Summary

PitWall predicts how much slower or faster a lap is than the driver's normal lap, from the tyre compound, the tyre's age and
how far through the race it is. A simulator strings those predictions together to estimate one car's race time under a
hypothetical pit strategy, and compares it with what the car really did. The app shows the gap, an error bar, and a verdict that
says how much to trust it.

It estimates **lap-time loss that goes with tyre age**, not physical tyre wear, and it **does not find the best strategy**.

## Intended use

- Learning, and showing how a small simulator can be built, tested and honestly evaluated.
- Looking at one car in one historical race, and asking how its total time would have moved under a different stop lap or compound.
- Reading "the model prefers X" as exactly that: what a simple tyre-age and fuel model prefers.

## Out of scope: please don't use it for

- Choosing a real strategy. The model cannot see undercuts, tyre allocation, sudden tyre drop-off, team orders or driver
  differences in tyre wear, which are what real strategy decisions turn on.
- Comparing drivers or cars, or estimating finishing positions. It does neither.
- Wet races, red-flagged races, 2022 or earlier seasons (OpenF1 has no data before 2023), 2026 (new regulations), or live data.
- "What if a safety car had come out": safety cars are replayed from what really happened, never predicted.
- Any causal claim about tyre degradation.

## Data

- Source: the [OpenF1](https://openf1.org) API, historical data only: lap times, stints, race-control messages, weather, driver names.
  Check OpenF1's terms before reusing the data.
- OpenF1 lists 70 Grands Prix in 2023-2025. **57 are used** (2023: 17, 2024: 19, 2025: 21; 24 circuits; 62,959 laps).
  13 are left out: 8 had a red flag before the chequered flag and 8 had a car on intermediate or wet tyres (3 of them both).
  Each race and its reason are in [`RACE_SELECTION.md`](RACE_SELECTION.md).
- A **clean lap** is one with no exclusion reason: not lap 1, not a pit in-lap or out-lap, not under a safety car, with a lap time
  and stint data, and not around a retirement or after the finish. 54,273 of the 62,959 laps are clean. The exact rules are in
  [`DATA_QUALITY.md`](DATA_QUALITY.md).
- **Training: 2023 and 2024 (36 races). Test: 2025 (21 races), never used to choose or tune anything.** Laps from one race are never
  split randomly between training and testing.
- The target is each lap's time minus **the driver's median clean lap in that race**. That reference comes from the race's own laps,
  which is acceptable only because the simulator runs on races that are in the dataset.

## The model

`delta = compound offset + tyre-age slope x tyre age + fuel term x race fraction`

- Ridge regression (`PooledWearModel`, alpha 100,000). The tyre-age slope is shared, with a small adjustment for each
  compound at each circuit, pulled toward the shared slope (partial pooling), so a combination with few laps stays close to it.
- Race fraction (lap number divided by race length) is the fuel proxy. It also absorbs the track getting faster, and the two
  cannot be separated.
- Fitted on clean laps from 2023 and 2024. It refuses a compound or a compound-at-circuit pair it hasn't seen.

Around the model, the simulator adds measured pieces: a pit loss per circuit, a lap-1 loss per circuit, a traffic penalty by gap
to the car ahead (about +0.5 s when starting within half a second of another car, falling to nothing beyond about 2 s), and a replay
of the real safety-car and virtual-safety-car laps. The other cars are replayed from the real race and never react.

## How well it works

All of these are on races the model did not see. 2025 numbers use the model trained on 2023 and 2024.

**1. Lap times, 2025 (17,981 clean laps; the model knows the compound and circuit)**, in seconds against predicting
"every lap is the driver's normal lap":

| | Mean absolute error | RMSE | Bias (+ = predicted too slow) |
|---|---:|---:|---:|
| Zero baseline | 0.816 | 1.264 | -0.011 |
| Model | **0.599** | 1.063 | +0.145 |
| Model, all 18,275 racing laps (baseline in brackets) | 0.716 (0.947) | 1.619 (1.835) | +0.016 (-0.155) |

11% of 2025 clean laps (2,266 of 20,247) are left out because their compound at that circuit never appears in 2023/24.
**On tyres 30 or more laps old (1,421 laps) the model is worse than the baseline**: error 0.81 s against 0.70 s, bias +0.46 s.

**2. A whole race total, no safety car** (179 driver-races in 2023/24, each scored by a model fitted on the other year): mean
absolute error **9.75 s** (0.18 s per lap) with each car's pace taken from its first half and traffic on; 9.89 s without traffic;
11.64 s when the pace comes from the whole race, which already contains the strategy being tested.

**3. A stint's time from the same car's other stints** (the whole race, including first stints):

| | Stints | Stint-total error (median) | Without tyre and fuel effects |
|---|---:|---:|---:|
| 2023/24 cross-year | 1,318 | 7.7 s (5.3 s) | 25.6 s |
| 2025 | 801 | 8.2 s (5.6 s) | 29.5 s |

A typical stint-level error of about **5 s** is why any predicted gap smaller than that can't be told apart from noise.

**4. Strategy gaps between two different cars, second half of the race only** (real data has no car running two strategies, so this
is the closest test; it cannot test first-stint choices):

| | Pairs | Gap error | Error if "strategy makes no difference" | Faster car picked (real gap over 5 s) |
|---|---:|---:|---:|---:|
| 2023/24 cross-year | 961 | 11.1 s | 13.3 s | 69% |
| 2025 | 445 | 9.2 s | 15.7 s | 85% |

When the predicted gap is under 5 s, the faster car is picked 43-63% of the time (a coin flip). From 5 to 10 s it is 71-75%; over 10 s
it is 85% (2023/24) to 99% (2025). Traffic improves the gap error by 0.3 s (2023/24) and 0.8 s (2025).

**5. Safety-car races** (22 replayable races, 312 cars, each scored by a model fitted without its own year): total error 162.3 s if
the neutralised laps are simulated as racing, 17.3 s if the field's real lap times are replayed, **17.0 s** with cheaper stops under
a real safety car as well (65% of the normal pit loss, median of 102 stops). That is worse than the roughly 10 s of races without one.

**6. The what-if agent** (an optional language-model layer; see [`AGENT_EVAL_sonnet.md`](AGENT_EVAL_sonnet.md)): on 40 questions graded
by fixed rules, Claude Haiku 5.5 passed 38 in both runs and Sonnet 5.5 passed 38, then 39 after one fix to the tools. It adds no
new predictions.

## Uncertainty

The app shows an 80% interval for four quantities (split conformal prediction: the interval is the prediction plus or minus the 80th
percentile of the model's absolute error on races it hadn't seen). Measured on 2025, which the calibration had not seen:

| Interval for | Half-width | 2025 coverage | 2025 values tested |
|---|---:|---:|---:|
| A clean lap time | ±0.85 s | 79% | 17,981 |
| A race total, no safety car | ±16.0 s | **71%** | 83 |
| A race total, safety car | ±33.6 s | 89% | 150 |
| The gap between two real cars | ±17.1 s | 89% | 445 |

Lap intervals are well calibrated. **Race-total intervals under-cover: 71%, against 80% intended** (73% if the calibration is updated
race by race). With only 83 values this is a shortfall of roughly 1.5 standard errors, so it is suggestive more than conclusive, but it
matches a measured shift: 2025 race totals were predicted about 4.8 s too slow on average, against about 1.0 s in 2023/24. The app
now uses half-widths that include the 2025 errors, so their coverage can no longer be tested on 2025.

The **verdict** ("prefers", "leans", "too close to call") requires the gap to exceed the model's typical stint error (5.3 s) **and**
the alternative to stay faster when the model, pit loss and traffic penalty are refitted on 20 random 80% subsets of the training races
(90% or more of them for "prefers", 70% or more for "leans"). This measures how much the answer depends on which races the model saw.
It is not the probability that the alternative really was faster.

## Known biases and limitations

- **Old tyres:** laps on tyres 30+ laps old lost less time than the model predicts (bias +0.18 s per lap over 1,613 such laps in 2023/24, +0.46 s on 2025's 1,421).
  The model therefore overstates the cost of long stints.
- **First stints** are predicted 0.17 s per lap too fast (0.12 on 2025): the model underestimates how slow heavy-fuel first stints are.
- I tried to fix both with 13 model variants and a gradient-boosting benchmark ([`MODEL_ABLATION.md`](MODEL_ABLATION.md)). Lap error moved
  by at most 0.01 s and neither bias went away, so the simple model stays. What remains looks specific to each race.
- **Safety cars** are replayed, never predicted; **traffic** is a replay with a simple penalty, no overtaking logic, and the training laps
  run in traffic are not removed; **track evolution** is folded into the fuel term and cannot be separated from it.
- **Gaps are not validated against the same car on two strategies**, because no such data exists. The checks use pairs of different cars
  (second half only) and a car's own other stints.
- **Alternatives use new tyre sets** after the first stint, and **no driver-specific tyre wear**: the alternatives rank the same way for
  every driver in a race.
- A strategy with tyres older than any seen at that circuit is flagged, and its number never counts in the verdict.
- The intervals' coverage was measured on one held-out season; a different season could differ.

## Reproducing the numbers

```bash
uv sync
uv run pytest -q                              # 288 tests
uv run python scripts/evaluate.py             # about 85 s: sections 1-5 and the error splits
uv run python scripts/build_calibration.py    # the intervals, written to data/processed/calibration.json
uv run python scripts/ablation.py             # docs/MODEL_ABLATION.md
```

## Where each number comes from

| Claim | Source |
|---|---|
| 57 of 70 races, 62,959 laps, 54,273 clean, 24 circuits, 17/19/21 races per year | `data/processed/lap_dataset.parquet` and `race_selection.json`; [`RACE_SELECTION.md`](RACE_SELECTION.md) |
| Lap table (0.599 vs 0.816, racing 0.716 vs 0.947, 17,981 and 18,275 laps) and tyres 30+ (0.81 vs 0.70, +0.46) | `scripts/evaluate.py`, "Final test" sections |
| 11% of 2025 clean laps left out (2,266 of 20,247) | 20,247 clean 2025 laps minus the 17,981 scored |
| Whole-race backtest 9.75 / 9.89 / 11.64 s, 179 driver-races | `scripts/evaluate.py`, cross-year race-total backtest |
| Stint check 7.7 / 5.3 / 25.6 and 8.2 / 5.6 / 29.5 s, first-stint bias | `scripts/evaluate.py`, "Leave-one-stint-out" |
| Pair check, 69% and 85%, 43-63%, 71-75%, 85-99%, traffic gain | `scripts/evaluate.py`, "Strategy pairs" |
| Safety-car totals 162.3 / 17.3 / 17.0 s, 312 cars | `scripts/evaluate.py`, safety-car backtest; stop ratio 0.65 from 102 stops: `DECISIONS.md` 2026-11-18 |
| Interval half-widths, coverage and test counts | `data/processed/calibration.json` (the `static` entries), `scripts/build_calibration.py` |
| 2025 bias of +4.8 s against +1.0 s in 2023/24 | `DECISIONS.md` 2026-11-19, prediction intervals |
| 13 model variants, lap error range, bias figures, old-tyre bias +0.18 s (1,613 laps) | [`MODEL_ABLATION.md`](MODEL_ABLATION.md), from `scripts/ablation.py` |
| Agent results | [`AGENT_EVAL_sonnet.md`](AGENT_EVAL_sonnet.md), [`AGENT_EVAL_haiku.md`](AGENT_EVAL_haiku.md) and their `_run1` first runs |
| "About 1.5 standard errors" | my arithmetic: 0.80 - 0.71 = 0.09 against sqrt(0.8 x 0.2 / 83) = 0.044 |
