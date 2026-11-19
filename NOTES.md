# NOTES

Running log. Newest entry at the bottom.

## 2026-10-30 Session 1

Done: Fresh repo with uv environment (managed CPython 3.13.9) and pytest wired
up; wrote `docs/SPEC.md` after being pushed on three wrong claims (finishing
positions, simulator knowing gaps/flags, live-sounding wording); implemented
`average_lap_time_by_tyre_age` with 4 passing hand-checked tests.

Next: Day 2 — read OpenF1 sessions/laps/stints docs, verify the Section 2.2
facts, fetch one candidate race and write down which fields I do and don't
understand.

Still unclear: What a null `lap_duration` actually means in OpenF1 — my
`is not None` check is data hygiene, not a pit-lap filter, and I need a
deliberate pit-lap exclusion rule with a row count. Also whether
`tyre_age_at_start + (lap_number - lap_start)` really gives tyre age.

## 2026-11-03 Session 2

Done: Fetched sessions for 2024/2025 and laps, stints and intervals (one driver)
for Mexico 2024 with curl; confirmed the Section 2.2 facts against the docs and
listed 17 non-sprint candidates in `docs/DATA_AUDIT.md`. Null `lap_duration` is
4 of 1,216 laps: three on a driver's final lap, plus Ocon's pit-lane start.

Next: Decide whether a virtual safety car counts as not clean, choose 4-5 Grands
Prix from the audit table, and check lap and stint data for them. Read through
`scripts/check_candidate_races.py` until I can explain it.

Still unclear: Why `segments_sector_*` has nulls; how to turn interval readings
into a clean-lap flag; how to catch in-laps, since only out-laps are flagged.

## 2026-11-04 Session 3

Done: Wrote `add_stint_data` to join laps to stints, with tests, and ran it on
Mexico 2024: 1,216 laps in and out, 1 unmatched (driver 14, lap 16). I guessed 4
unmatched by assuming "no duration" meant "no stint", but only that lap has
neither, so they need separate checks. Ran the joined laps through
`average_lap_time_by_tyre_age`.

Observations (Mexico 2024 only):
- The earliest tyre ages are slowest, mostly because of safety car and pit-out
  laps rather than the tyres.
- From about age 7 to 38 the average stays around 82.2-82.6s. Tyre-related
  slowdown may be cancelling the gain from lighter fuel, but this table can't
  separate them.
- The tyre mix changes with age: no lap past age 38 is on mediums.

Caveats:
- Very few laps at the oldest ages (one lap at age 49), so the late rise is weak
  evidence, and in-laps haven't been removed.
- Each average mixes tyre age with fuel load, drivers, compounds, and safety car
  and pit laps, so it doesn't show the effect of tyre age alone.

Next: Repeat the averages on Hungary 2024 (9566) and plot lap time against tyre
age and race lap. Make `pitwall` importable without `PYTHONPATH`. Still open from
Session 2: decide whether a virtual safety car counts as not clean, and choose
4-5 Grands Prix.

Still unclear: How to separate tyre age from fuel; whether the late rise is real
or in-laps; why driver 14's stint stops at lap 15 when they have a lap 16.

## 2026-11-05 Session 4

Done: Made `pitwall` installable (build-system in pyproject, so no more
`PYTHONPATH`), generalised the join check into `scripts/check_session_join.py
<session_key>` and ran it on Hungary 2024: 1,356 laps in and out, no overlaps,
one unmatched lap (driver 10's last lap, same pattern as Mexico). Lap 1 and
pit-out laps can land at any tyre age because of used sets, so they have to be
excluded by lap type, not by age. Decided to keep dry races with safety cars
but drop the disrupted laps, and picked 5 Grands Prix (Hungary, Monza,
Singapore, Bahrain, Abu Dhabi): 2024 to train, 2025 to test, clean sessions
only for the backtest.

Next: Session 5, fetch function and cache together: turn `fetch_if_missing`
into tested code in `src/pitwall/`, with tests that don't hit the live API
(success, empty, HTTP error, malformed body, cache hit).

Still unclear: How to tell the laps just before and after a safety car apart
from normal laps, since `race_control` only gives deployed and ending laps.
Why Sakhir 2024 stints show no MEDIUM tyres. Whether the "retired on the last
lap" pattern holds across all 10 races.

## 2026-11-05 Session 5

Done: Wrote `fetch_endpoint` (allowed endpoint list, OpenF1's 404 "No results
found" returns `[]`, other HTTP errors and non-list bodies raise) and
`load_or_fetch` (cache in `data/raw/`, sidecar `.meta.json` per file), with 7
tests that never touch the live API. `scripts/fetch_races.py` fetched laps and
stints for all 10 v1 sessions: 9 requests, then 0 on a second run, as
predicted.

Next: Session 6, cleaning and join design: run the lap/stint join on all 10
sessions, then write the first exclusion rules (lap 1, pit-out laps, in-laps,
SC/VSC laps), each with a count.

Still unclear: Writing tests with fakes on my own. I needed a lot of help with
`monkeypatch`, `pytest.raises` and `tmp_path`, so the next tests should be more
mine. Also: `is` vs `==`, and why `from x import y` stops monkeypatch working.

## 2026-11-08 Session 6

Done: The lap/stint join holds on all 10 races (10 unmatched laps, each a
driver's unfinished last lap). Wrote `exclusion_reasons` for lap 1, pit-out, null
lap time, in-lap, before-retirement and no-stint, with per-race counts in
`docs/DATA_AUDIT.md`; Claude wrote `has_lap` and the final in-lap and retirement
branch after my attempt. Hand-checked the tyre-age formula on Hungary 2024
(drivers 44 and 18) against the code, F1's pit stop summary and the OpenF1 docs.

Next: Session 7, safety-car and VSC laps from `race_control`, including the laps
around them, each with a count. Then the function that labels a whole race, and
add the missing test for a no-stint lap that has a lap time.

Still unclear: How to tell which laps a safety car actually affected. Which
reasons should count against the racing dataset. Whether the 10 unmatched laps
were all retirements, and why driver 30's lap 55 in Abu Dhabi has no pit-lane
code. Python basics I tripped on: `~` vs `not`, and how pytest treats arguments
to a `test_` function.

## 2026-11-08 Session 7

Done: Wrote `find_safety_car_disruption_laps` (only 2 of the 10 races have one:
Abu Dhabi 2024 laps 1-4, Bahrain 2025 laps 31-36 with the buffer) and
`add_exclusion_reasons`, which labels a whole race, with my own tests. All 10
races keep laps in = laps out: 5,217 clean laps of 5,710 in 2024, and 5,382 of
5,859 in 2025. Counts are in `docs/DATA_AUDIT.md`.

Next: Session 8, the processed dataset: decide which reasons count against the
racing dataset, then build the Parquet file with tyre age, compound, race lap,
circuit and year, plus a data-quality report and longest stints per compound and
circuit.

Still unclear: Whether `race_control`'s `lap_number` follows the leader, which
is the reason for the lap before the safety car. Whether one lap each side is
the right buffer. Tests that can't fail: one had no `assert`, another never
called the function.

## 2026-11-09 Session 8

Done: Chose what counts as a racing lap (Option B: no safety-car, null, no-stint
or pit laps) and wrote `is_racing_lap`, `is_clean_lap` and `build_race_rows` with
my own tests. Claude wrote the year totals, `stint_number`,
`keep_dataset_columns` and the Parquet step. `lap_dataset.parquet` has 11,569
rows, no duplicate keys, and matches the known counts: 5,217 clean and 5,302
racing in 2024, 5,382 clean and 5,483 racing in 2025.

Next: Session 9, data-quality report and longest stint per compound and circuit,
then the exploratory plots. Add the missing docstrings on `is_clean_lap` and
`build_race_rows`.

Still unclear: `in` with a list on the left, `append` vs `extend`, and why
passing a whole dict to a function expecting a list didn't crash. Tracing one
raw lap all the way to its Parquet row in my own words, since Claude wrote the
last part. Still open from Session 7: whether `race_control`'s `lap_number`
follows the leader.

## 2026-11-10 Session 9

Done: Wrote `max_clean_tyre_age` (oldest tyre age on a clean lap per circuit,
year and compound) with four tests, plus docstrings for `is_clean_lap` and
`build_race_rows`. On the 10 races it gives 29 entries. Sakhir 2024 has no
MEDIUM, and Monza 2024 SOFT only reaches age 1.

Next: Session 10, data-quality report (rows, missing values, duplicates,
exclusion counts per race), then the exploratory plots.

Still unclear: Storing a value in a dict (`d[key] = value` vs `append`), and
how `defaultdict` creates keys just by reading them. Whether the guard should
use 2024 only or both years, since 2025 stints run much longer (Monza MEDIUM 20
vs 44).

## 2026-11-10 Session 10

Done: Wrote `count_missing`, `count_duplicate_keys` and `count_reasons` with
tests. Claude wrote `race_quality`, the Markdown tables and the
`build_dataset.py` changes, so every build writes `docs/DATA_QUALITY.md`. 0
duplicate keys. 13 missing lap times, 10 laps with no tyre data, 1 missing
`date_start` (Hungaroring 2024).

Next: Session 11, exploratory plots: lap time against tyre age and race lap,
and whether the fuel effect shows.

Still unclear: Tuple of names vs tuple of values as a key. Why
`assert (... for ...)` always passes and `all(...)` is needed.

## 2026-11-11 Session 11

Done: Wrote `median_clean_lap_by_race_lap` (Claude wrote its tests and
docstring) and Claude wrote `scripts/explore.py`, which saves two Hungaroring
2024 plots to `docs/figures/`. Median clean lap falls about 3 s over the race,
in a sawtooth with drops near laps 7, 29 and 50. Within-stint lines are
mostly flat because fuel burn cancels wear.

Next: Session 12, Week 4: choose the target (delta to the driver's median
clean lap) and build the zero baseline with the 2024/2025 split.

Still unclear: `.items()` gives (key, value) and lists can't be dict keys.
Whether the drops really line up with pit windows (not checked against
stints). How much of the race-lap trend is fuel vs track evolution.

## 2026-11-12 Session 12

Done: New `features.py` with `driver_reference_laps` (median clean lap per
driver per race) and `add_delta` (lap time minus that reference, None when
there's no reference or no time). Claude fixed one docstring and wrote the
`add_delta` tests. On the real data: 11,569 rows in and out, every driver's
median clean delta is 0, and 13 rows have delta None (the 13 missing lap
times; two lap-1 retirements have no reference).

Next: Session 13, the 2024/2025 split, the zero baseline, and scoring
functions (MAE, RMSE, bias) on clean and racing laps.

Still unclear: Why float sums like (82.1 + 84.3) / 2 aren't exact and when
to use `pytest.approx`. `result = ...` replaces, `result.append(...)` adds.

## 2026-11-12 Session 13

Done: New `evaluation.py` with `score` (MAE, RMSE, bias in seconds) and
`split_by_year` (2024 train, 2025 test, error on any other year), with tests.
Claude wrote `score`'s docstring and `scripts/evaluate.py`. Zero baseline on
2025: clean MAE 0.792 s, RMSE 1.129 s, bias +0.022 s (n=5,382); racing MAE
0.955 s, RMSE 1.800 s, bias -0.156 s (n=5,483).

Next: Session 14, add scikit-learn, build features, fit tyre age + compound,
then add race lap, and compare against the zero baseline.

Still unclear: Lists can't be subtracted, `zip` pairs them up. Why a function
with no `return` gives None. Whether lap 1 causes the big racing RMSE (not
checked yet).

## 2026-11-13 Session 14

Done: Added scikit-learn and pandas. New `model.py` with `build_pipeline`
(compound one-hot, tyre age, optional race lap, optional wear per
compound@circuit) and `pair_age_columns` in `features.py`. Claude wrote the
`PairAgeColumns` class, docstrings, `pair_age_columns` (after I got stuck) and
most of the `evaluate.py` loop. 2025 clean MAE (n=4,944, Sakhir MEDIUM left
out): zero 0.803, A 0.792, B (+ race lap) 0.642, C (+ wear per pair) 0.667.
Adding race lap grew the wear slope from 0.010 to 0.060 s/lap, fuel -0.049.

Next: Session 15, Week 5: fix sparse pairs in Model C (Monza SOFT has 1
clean lap and a -0.84 s/lap rate), look at error slices, and why B's bias
is +0.15 s on 2025.

Still unclear: How fit and transform pass through a pipeline step. Why
`"False"` is truthy. Why C is worse at Hungaroring (longer 2025 stints?).

## 2026-11-14 Session 15

Done: `score_by_group` in `evaluation.py` (pandas groupby, reuses `score`,
adds `n`) with tests; Claude filled in the test values, docstring and the
`print_slices` output in `evaluate.py`. On 2025 clean laps, B's bias grows
with tyre age: about 0 at 0-19 laps, +0.26 s at 20-29, +0.78 s at 30+ (still
+0.72 s within the 2024 age range). C beats B at Singapore and Yas Marina,
loses at Hungaroring and Monza; C's SOFT bias is -0.28 s (Monza SOFT rate).

Next: Session 16, Week 5: pick one improvement. Old-tyre bias first
(shape of the wear curve), sparse pairs in C after.

Still unclear: Whether the old-tyre bias is curve shape, 2025 tyres wearing
less, or teams only running long stints on tyres that hold up. How to tell
these apart.

## 2026-11-14 Session 16

Done: `leave_one_race_out` in `evaluation.py` and `add_race_fraction` in
`features.py`, with tests (Claude wrote the race-fraction tests, docstrings
and the held-out printing in `evaluate.py`), plus a `fuel_column` option in
`build_pipeline`. Held-out 2024: B's bias is about 0 at every tyre age, so
the old-tyre bias is a 2025 effect and wear stays linear. Fuel by race
fraction cut MAE 0.572 -> 0.545 s and mostly removed the Hungaroring and
Monza drift. Wear rate unchanged at 0.061 s/lap.

Next: Session 17: how to validate per-circuit wear (C) when each circuit is
in 2024 only once, then sparse pairs. Or start the Week 5 write-up.

Still unclear: Why Hungaroring's last 10 laps, Sakhir's first 10 and
Singapore's early laps are still off. How much of the fuel term is track
evolution.

## 2026-11-16 Session 17

Done: Added the 2023 editions of the 5 races (Claude fetched, audited and
cleaned them; new `after_finish` label for untimed laps past the race distance,
`race_distance`, explicit-year `split_by_year`, `leave_one_year_out`). I wrote
`cross_year_predictions`. Cross-year (fit one year, score the other, 10,053
clean laps): B_frac MAE 0.519 s vs C_frac 0.523 s, a tie, but C cuts per-circuit
bias from -0.12..+0.22 s to within +-0.04 s (Singapore, Sakhir better; Monza worse).

Next: Session 18: partial pooling (shared wear rate plus per-circuit
adjustments pulled toward it) to keep C's low bias with B's stability. Or
start the race-total backtest, which is where bias shows up.

Still unclear: Whether C's lower bias actually wins on race totals. Why C is
worse at Monza. How much 2023-to-2024 car and tyre change is in these numbers.

## 2026-11-16 Session 18

Done: Working mode changed: Claude writes the code after I approve a short
plan (CLAUDE.md updated, plus 2023 in its data and evaluation rules).
`PooledWearModel` in `model.py`: shared wear rate plus per-pair adjustments,
only the adjustments penalised, solved with numpy. The two-step version failed
its synthetic test (frozen offsets), so we fit everything jointly. Cross-year MAE
is flat across alpha (0.518-0.523 s) while circuit bias spread goes from C's
0.08 s to B's 0.34 s.

Next: Session 19: simulator core (sum predicted lap times over a strategy, tyre
age resets at stops, fuel doesn't), then the race-total backtest of B, C and
pooled alphas to choose alpha.

Still unclear: Whether race totals separate the alphas. Whether warm-up or a
cliff shows up as curvature in residuals by tyre age.

## 2026-11-17 Session 19

Done: Simulator core in simulator.py: strategy_laps (strategy -> lap table; tyre
age resets at a stop, race_fraction doesn't; pit on lap N = new set from N+1)
and simulate (reference lap + predicted delta per lap, plus stops × pit_loss).
Hand-calculated 6-lap example matches (505.4 s). Real Hungaroring 2024 2-stops
through Model B with no pit loss: actual minus predicted is 21-44 s per stop.

Next: Session 20: strategy validation (rule 6: two dry compounds, pit laps in
range and in order, observed-range guard) and pit loss per circuit from the data.

Still unclear: How the 21-44 s gap splits into pit loss, lap 1 and traffic.
Which years the observed-range guard should use.

## 2026-11-17 Session 20

Done: Strategy validation in simulator.py: validate_strategy (dry compounds
only, at least two different, pit laps increasing and inside the race) and
stint_range_flags (stint older than the oldest clean tyre age in 2023-2024 is
flagged, no data at all is refused; in-laps not counted). simulate now runs
both and returns "flags". 10 real Hungaroring 2024 2-stops: all pass, no flags.

Next: Session 21: pit loss per circuit from the data (method choice; /pit
isn't cached yet).

Still unclear: Current FIA article number for the two-compound rule. How many
2025 backtest strategies get flagged.

## 2026-11-17 Session 21

Done: Pit loss per circuit in analysis.py: stop_losses (per stop: actual minus
predicted delta on in-lap + out-lap, with skip reasons) and pit_loss_by_circuit
(median, quartiles, counts). 2023-2024, Model B frac: Hungaroring 20.8 s, Yas
Marina 23.0, Sakhir 24.8, Monza 25.6, Singapore 29.4 (21 of 48 stops skipped
for safety car). Hungaroring 2024 2-stops with it: actual minus predicted is
+0.4 to +46.5 s, and every lap 1 is 4-14 s slower than predicted.

Next: Session 22: lap 1 (the model never trains on it, standing start) and the
race-total backtest on 2023/2024 to choose alpha.

Still unclear: Why drivers 11, 16, 44, 63 are still 26-47 s off after pit loss
and lap 1. Whether pit loss from Model B is right for the pooled models.

## 2026-11-17 Session 22

Done: Cross-year race-total backtest (backtest.py: actual_strategy,
backtest_race; lap_one_losses; simulate gets lap_one_loss). Each held-out year
uses model, pit loss, lap-1 loss and tyre-age limits from the other year. 76
lead-lap driver-races in 7 safety-car-free races: MAE B 11.91 s, P_1e5 11.81,
P_1e6 11.84, C 12.86 (about 0.2 s/lap). 7 of 76 flagged by the range guard.
Model choice deferred: most error is a race-wide bias shared by every model
(Singapore 2024 +4 to +16 s, Monza 2024 -9 to -14 s).

Next: Session 23: split each race-total error into lap 1, stops and normal
laps to find the race-wide bias, then choose between P_1e5 and B.

Still unclear: Whether the race-wide bias is the fuel term, year-to-year pit
loss, lap 1 or the reference lap. Backtest covers lead-lap finishers only.

## 2026-11-17 Session 23

Done: error_components in backtest.py splits each race-total error into lap 1,
stops and normal laps (backtest records get "components"); print_error_split in
evaluate.py. Lap 1 and stops stay within about ±4 s per race; normal laps carry
the bias in 5 of 7 races (Singapore 2024 +13.4 s, Monza 2024 -10.0, B_frac).
The normal-lap error drifts with race lap in opposite directions across years
(Monza 2023 +0.7 to -0.8 s/lap, Monza 2024 -0.55 to +0.3). Model choice left open.

Next: Session 24: look at the race-lap term (fuel + track evolution) per race,
e.g. how much its slope varies between races and years, then choose P_1e5 vs B.

Still unclear: Whether a per-race race-lap slope is learnable at all before a
race (it may only be a limitation). Monza 2023's error is mostly lap 1 (+4.2 s).

## 2026-11-17 Session 24

Done: residual_trends in analysis.py (per race: leftover slope on race_fraction
plus a tyre-age slope per compound; refuses collinear races) and
print_residual_trends in evaluate.py. The drift isn't only race-lap: leftover
wear of 0.04-0.07 s/lap of age at Sakhir 2024 and Monza 2024 for both models.
Chose P_1e5 (DECISIONS 2026-11-17).

Next: Session 25: Week 7, compare a small set of strategies with P_1e5 and add
sensitivity to pit loss (q25-q75) and wear rate (±0.05 s/lap).

Still unclear: Which years train the final model (2023+2024?). Fuel and wear
within one race are only roughly separable (Monza 2023: naive wear slope +0.029,
joint fit 0.000).

## 2026-11-18 Sessions 25-30

Done: comparison.py (candidate_strategies, compare_strategies, sensitivity,
compare_driver, gap_ranges, verdict, cumulative_gap) and app.py (Streamlit: pick a
safety-car-free race and a car, real strategy vs 5 alternatives, dot-and-range chart).
Final model P_1e5 trained on 2023+2024; scored once on 2025: clean MAE 0.612 s vs
zero baseline 0.792, bias +0.146 (old tyres 30+ laps: bias +0.71, a 2025 effect, not
seen in 2023/24). Wear sensitivity ±0.032 s/lap (q75 of held-out wear error).
Strategy-pair check (pace from first half, scored on second half): MAE 11.2 s cross-year
and 10.9 s on 2025 vs 12.8 / 15.7 s for zero; picks the faster car 70% / 76% of the time
when the real gap is over 5 s, but only about 50% when the predicted gap is under 3 s.

Next: v1 finish (verdict tiers from these numbers, custom strategy input, README, CI,
deploy notes), then v2: traffic and replayed real safety cars (DECISIONS 2026-11-18).

Still unclear: The model prefers another strategy for most cars (even-stint bias).
How the deployed app gets data/processed (gitignored). Not checked in a real browser.

## 2026-11-18 Session 31 (v1 finish, run without supervision)

Done: verdict tiers from the pair check (<3 s too close, 3-10 s leans, >10 s prefers);
`first_half_pace` for each car's pace (whole-race backtest MAE 11.81 -> 10.41 s);
custom strategy in the app with validation; driver names (`drivers` endpoint cached,
`scripts/build_driver_names.py`); end-to-end test on a 90 KB real subset
(tests/fixtures/mini_laps.parquet); README, CI workflow, docs/DEPLOY.md (not deployed).
Clean-environment check: uv sync from tracked files only, 184 tests passed.

Next: v2, traffic first (gate: is a close-behind penalty visible in the lap data?), then
replayed real safety cars (DECISIONS 2026-11-18).

Still unclear: EC2 vs container for the AWS deploy (your decision, see docs/DEPLOY.md), and
whether to commit data/processed/ (two files, about 330 KB) so a fresh clone can run the app.

## 2026-11-18 Session 32 (v2 part 1: traffic)

Done: traffic.py (gaps from lap start times, penalty by gap to the car ahead, anchored replay of the
real field). Gate passed (close behind costs time in both years). 2023/24 cross-year pair check MAE
11.21 -> 10.50 s; whole-race backtest 10.41 -> 9.60 s (first-half pace); 2025 read once: pair MAE
10.86 -> 10.66 s, hit rate 76% -> 82%. App has "Include traffic" (default on); the model now agrees
with the real strategy for 18 of 124 cars (2 before). `compare_strategies`/`sensitivity`/
`compare_driver` take the replayed field; `scripts/evaluate.py` prints traffic on/off.

Next: replayed real safety cars (exact neutralised laps, SC lap times from the field, cheaper stops).

Still unclear: Traffic for alternative strategies can't be validated (no real data for them).

## 2026-11-18 Session 33 (v2 part 2: replayed safety cars)

Done: neutralisation.py (windows from race_control, field lap times, SC stop ratio 0.68 from 14 real
stops at Singapore 2023), simulator/comparison/backtest take a `neutralisation`; app offers the 4
safety-car races (178 car pages, no errors) with a banner and a "pit under the safety car" candidate.
Only 2 of the 4 races had a real SC (Singapore 2023, Sakhir 2025); the others were VSCs (stops under
them were not cheaper, 4 stops). Backtest on the 4 races: 101.6 s (neutralised laps simulated as
racing) -> 13.2 s (replay) -> 12.7 s (replay + cheaper stops); Sakhir 2025 out of sample 117.7 ->
11.0 s. Singapore 2023's 21 s is the model's late-race bias, not the replay.

Next: final pass (tests, clean-checkout run, README numbers), then your decisions: EC2 vs container,
commit data/processed?

Still unclear: SC stop discount rests on 14 stops at one circuit. Verdict thresholds were measured on
races without a safety car.

## 2026-11-18 Session 34 (whole-race validation and the 2023-2025 corpus)

Done: you were right that the second-half pair check can't validate whole-race strategy. Added the leave-one-stint-out
check (`stint_holdout_errors`: stint-total error 7.7 s cross-year, 8.2 s on 2025, vs 25.6 / 29.5 s with no tyre or fuel
effect) and replaced the 3 s / 10 s verdict tiers with a floor (5.3 s) plus a refit ensemble (20 refits on 80% of the
races). Corpus: OpenF1 has no 2022; 70 races in 2023-2025, 57 usable (8 red flag, 8 wet), 50 offered in the app.
Fixed three safety-car parsing cases (finish under SC, VSC upgraded to SC, mass pit stop). Re-ran every check: 2025
clean MAE 0.599 vs 0.816; backtest 9.75 s; safety-car races 162 -> 17 s.
Found: first stints are predicted 0.12-0.17 s/lap too fast, and the old-tyre bias is in 2023/24 too (+0.19 at 30+),
which corrects my earlier "2025 effect" note.

Next: decide whether to act on the two leads (a non-linear fuel or wear term, tested on 2023/24 cross-year only);
EC2 vs container; commit the data files so a fresh clone can run the app.

Still unclear: nothing here tests the same car on two strategies. The verdict floor and refit thresholds (70% / 90%)
are judgment calls. Not committed.

## 2026-11-18 Session 35 (deployment kit)

Done: Dockerfile (1.26 GB, non-root, health check), `deploy/deploy.sh` and `user-data.sh`, `.streamlit/config.toml`,
the three data files un-ignored and committed, `tests/test_committed_data.py`, and `docs/DEPLOY.md` rewritten as a
step-by-step AWS CLI runbook (budget alert first, teardown last). Tested locally: the image builds, runs as a non-root
user, the app executes inside it for 50 races, a session peaks at 471 MB, and deploy.sh replaces the container twice
in a row. Found and fixed: a `chown -R` had doubled the image to 3.06 GB.

Next: you run the runbook (budget alert, then launch), then the clean-browser test; add the live URL and a demo GIF to
the README. Then step 2 of the six: calibrated uncertainty.

Still unclear: the first x86 build on the server (my laptop is arm64); whether to add HTTPS with a domain.

## 2026-11-19 Session 37 (calibrated intervals)

Done: conformal.py (corrected quantile, coverage, rolling coverage; hand-calculated tests), build_calibration.py ->
data/processed/calibration.json, intervals in the app (race total, gap column) and the README coverage table.
Lap times are calibrated (79% of 2025 laps at 80% nominal). Race totals are not (71% static, 73% rolling): 2025 is biased
(+4.8 s mean error vs +1.0), so a recent-races window or per-race updating can't fix it; the fix is the model (step 3).
Gap intervals over-cover (88-89%) because they are measured on pairs of different cars.

Next: step 3, the two model leads (first stints predicted 0.12-0.17 s/lap too fast; old tyres over-penalised), tested on
2023/24 cross-year only; then re-run build_calibration.py.

Still unclear: whether race-total coverage recovers once the 2025 bias is fixed. The calibration.json half-widths now include
2025 errors; the coverage numbers quoted are from before they were added.
