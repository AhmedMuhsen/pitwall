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
