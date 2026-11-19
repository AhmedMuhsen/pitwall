# DECISIONS

One entry per real decision. Format:

- **Decision** — what was decided
- **Requirement** — what forced the choice
- **Options** — what was considered
- **Choice and reason** — what was picked and why
- **What would make us reconsider** — the signal that would reopen it

---

## 2026-10-30 — Environment tooling: uv + pyproject.toml

- **Decision** — Manage the Python environment with `uv` and `pyproject.toml`,
  on a uv-managed CPython 3.13 pinned in `.python-version`.
- **Requirement** — A reproducible environment that someone else (or a
  deployment target) can recreate, without coupling it to my local conda
  install.
- **Options** — (a) `venv` + `requirements.txt`: stdlib only, matches what most
  deploy targets expect, but no lockfile. (b) `uv` + `pyproject.toml`: fast,
  real lockfile, standard metadata, one more tool to learn. (c) `conda`: good
  for scientific binaries, but heavy and we have no binary problem.
- **Choice and reason** — uv. Wanted the lockfile and the standard
  `pyproject.toml` metadata, and I'd rather learn the tool new projects are
  actually using. Set `python-preference = "only-managed"` after uv's first
  sync picked up miniconda's interpreter.
- **What would make us reconsider** — If the AWS deploy target makes uv
  awkward, exporting a `requirements.txt` is a one-command fallback. Also
  pinned 3.13 rather than 3.14 because I have **not** verified that pyarrow,
  scikit-learn and streamlit all ship 3.14 wheels; bump once that's checked.

## 2026-10-30 — Empty input to `average_lap_time_by_tyre_age` raises

- **Decision** — Raise `ValueError` on an empty `laps` list rather than
  returning an empty dict.
- **Requirement** — Decide whether no-laps is a normal outcome or a bug.
- **Options** — (a) return `{}`: caller needs no special case, empty results
  flow through silently. (b) raise `ValueError`: fails loudly at the point of
  the problem, every caller must handle it. (c) return `None`: crashes the
  caller later with no useful message — rejected.
- **Choice and reason** — Raise. Right now an empty list almost certainly means
  data loading or caching failed, and I want to hear about that immediately
  rather than see an empty plot and go hunting through the model.
- **What would make us reconsider** — Once laps are filtered to clean laps per
  driver/compound/circuit, some groups will legitimately be empty, and every
  caller wrapping this in `try`/`except` is the signal to switch to returning
  `{}` and let the caller decide.

## 2026-10-30 — Lap records are a list of dicts, not a DataFrame

- **Decision** — Analysis functions at this layer take a list of dicts, one per
  lap, and read only the keys they need.
- **Requirement** — Inputs that can be written literally in a test and totalled
  by hand.
- **Options** — (a) list of dicts: hand-checkable, no pandas semantics in the
  way. (b) pandas DataFrame: closer to the eventual dataset layer, but the
  arithmetic hides behind groupby and tests get harder to verify by eye.
- **Choice and reason** — List of dicts. The point of this function is a test
  whose expected values I calculated on paper. Also rejected keying by lap
  number: lap 5 is not unique — twenty drivers each have one — so the row grain
  is (session, driver, lap).
- **What would make us reconsider** — The processed dataset layer will be
  pandas/parquet. Pandas enters when we're operating on whole races at once,
  not at this function's level.

## 2026-11-03 — Rain and safety cars: no modelling in v1, safety-car replay later

- **Decision** — v1 does not model rain or safety cars. Once the backtest works
  on clean races, add a clearly labelled extension that replays a race's real
  safety car.
- **Requirement** — Real races have safety cars and rain, and the project has to
  be defensible about how it treats them.
- **Options** — (a) No modelling, limitation stated. (b) (a) plus a later replay
  of the real safety car: slow laps and a cheaper pit stop on the known laps.
  (c) Model rain and random safety cars now: rainfall isn't track wetness, and
  8-10 races can't support safety-car odds per circuit.
- **Choice and reason** — (b). The real safety-car laps are known from
  `race_control`, so a replay doesn't need an invented distribution. Building it
  after a working backtest gives a baseline to measure it against. Safety-car
  laps stay out of fitting either way, because they say nothing about tyres or
  fuel.
- **What would make us reconsider** — The replay doesn't reduce backtest error on
  safety-car races: drop it. A dataset with far more races could reopen
  safety-car odds.

## 2026-11-04 — Laps with no matching stint are kept, with `None` values

- **Decision** — `add_stint_data` keeps a lap with no matching stint and sets its
  `tyre_age` and `compound` to `None`.
- **Requirement** — Real races have unmatched laps: in Mexico 2024, driver 14's
  lap 16 has no stint. The join has to handle them without hiding them or
  inventing values.
- **Options** — (a) Keep the lap with `None`: the row count stays the same, but
  later code has to handle `None`. (b) Drop the lap in the join and return a count:
  later code is simpler, but the join also becomes cleaning. (c) Raise an error:
  very visible, but real data stops it straight away. I also considered assuming
  the driver was in the pit lane when a later stint exists, but no unmatched lap
  in Mexico has one, and it would add a fact the data doesn't show.
- **Choice and reason** — (a). The join stays a join, and every exclusion can be
  made and counted in one place during cleaning.
- **What would make us reconsider** — Unmatched laps turn up mid-race in other
  races, which would need an explanation rather than just `None`. Or handling
  `None` becomes repetitive once we move to the processed dataset.

## 2026-11-04 — Overlapping stints raise `ValueError`

- **Decision** — `find_stint` raises `ValueError`, naming the driver and lap, when
  more than one of a driver's stints covers the same lap.
- **Requirement** — A car has one set of tyres on a lap, so a lap needs a single
  tyre age and compound. An overlap means the data breaks that assumption.
- **Options** — (a) Raise `ValueError`: visible straight away, but one bad row
  stops the whole race. (b) Return the first match: never stops, but can pass a
  wrong age into the model unnoticed. (c) Use `None`: the run continues, but a data
  error looks the same as a retirement lap.
- **Choice and reason** — (a). We shouldn't guess when a basic assumption fails.
  This is different from an unmatched lap, which is expected in real races.
- **What would make us reconsider** — Overlaps turn out to be common and have a
  known cause when we run more races. Then we'd handle that cause with its own
  rule. Mexico 2024 has none, and no other race has been checked yet.


## 2026-11-05 — Races with a safety car stay in; disrupted laps are dropped

- **Decision** — A dry race with a safety car (SC), virtual safety car (VSC) or
  red flag can still be used. Its disrupted laps are dropped during cleaning,
  with a count per race. Only fully undisrupted sessions are used for the
  simulator backtest.
- **Requirement** — CLAUDE.md asks for 4-5 Grands Prix in both 2024 and 2025,
  with a range of tyre wear across circuits. Only 3 of the 17 non-sprint
  candidates are clean in both years (Hungaroring, Monza, Singapore), and all
  three are mostly one- or two-stop races.
- **Options** — (a) Only races clean in both years: no lap dropping, but 3 races
  with similar wear. (b) Any dry race, drop SC/VSC/red-flag laps, backtest on
  clean sessions only. (c) Treat a VSC as clean: more races, but VSC laps are
  slow and pit stops under a VSC are cheaper, so both the model and the backtest
  get noisier.
- **Choice and reason** — (b). The model treats each lap as its own row, so a
  gap in the lap sequence doesn't hurt it, as long as tyre age and race lap are
  computed from the real lap numbers before anything is dropped. Keeping the
  laps would hurt: in Mexico 2024 the lap 1-6 safety car made the youngest tyres
  look 20+ seconds slow, while clean Hungary 2024 is flat at about 84.1-84.6s
  from age 1 to 17. Accepted cost: tyre age and race lap keep counting during a
  safety car while the tyres barely wear and less fuel is burned, so ages after
  a safety car overstate wear slightly. That goes in the limitations. The laps
  around an SC (deployment and restart) also need to be in the exclusion rule.
- **What would make us reconsider** — Residuals that are consistently off on
  laps after a safety car (then try a "racing laps on this set" feature in
  Week 5), or one race losing so many laps that its wear estimate is unreliable.

## 2026-11-05 — v1 races and how they are split

- **Decision** — v1 uses 5 Grands Prix in both 2024 and 2025: Hungary
  (Hungaroring), Italy (Monza), Singapore, Bahrain (Sakhir) and Abu Dhabi (Yas
  Marina).
  - Training: the 2024 races (9566, 9590, 9606, 9472, 9662).
  - Test: the 2025 races (9928, 9912, 9896, 10014, 9839), not looked at until
    the model is chosen.
  - Model selection: leave one 2024 race out at a time.
  - Backtest: sessions with no SC, VSC or red flag. Held out: Hungary, Monza,
    Singapore, Abu Dhabi 2025. In-sample, reported separately: Hungary, Monza,
    Singapore, Bahrain 2024.
- **Requirement** — 4-5 dry, non-sprint Grands Prix with usable data in both
  years (CLAUDE.md), a range of tyre wear across circuits (rule 3), and enough
  undisrupted sessions for the backtest (rule 8).
- **Options** — (a) These 5. (b) Suzuka instead of Yas Marina: high wear in 2024
  (mostly 3 stops) but almost all 1-stop in 2025, so a harder test that may
  reflect a circuit change we can't model. (c) Las Vegas instead of Yas Marina:
  2024 clean, but 2025 VSCs on laps 2-4 and 16. Zandvoort, Imola, Monaco and the
  rain races were ruled out for heavy disruption, track-position races or rain
  (see `docs/DATA_AUDIT.md`).
- **Choice and reason** — (a). Sakhir adds the only high-wear circuit with
  little disruption (2-3 stops both years, one 4-lap SC in 2025). Yas Marina
  costs 2 VSC laps and behaves similarly in both years. That gives 8
  undisrupted sessions for the backtest.
- **What would make us reconsider** — The lap/stint check fails on one of these
  sessions, Singapore 2025's rain readings turn out to be during the race, or
  Sakhir 2024's missing MEDIUM stints turn out to be a data problem. Suzuka
  2025 and Zandvoort 2024 (both undisrupted) stay available as an optional
  unseen-circuit test.

## 2026-11-05 — Request details go in a sidecar file next to each cached response

- **Decision** — `load_or_fetch` writes `<endpoint>_<session_key>.meta.json`
  next to each cached response, with the endpoint, params, retrieval time (UTC)
  and record count. A "no results" 404 is cached as `[]` with `records: 0`.
- **Requirement** — The data rules require recording the endpoint, params,
  session key and retrieval date for every cached file.
- **Options** — (a) A sidecar file per response: the cached file stays just the
  records, but there are twice as many files and they can get out of sync.
  (b) Wrap the response in `{"meta": ..., "data": [...]}`: one file, but the
  cached file is no longer the API's records, and the 70+ files already saved
  don't match. (c) One `manifest.json` for all files: one place to look, but
  every fetch rewrites a shared file, and a crash halfway can leave it out of
  step with the files.
- **Choice and reason** — (a). It keeps the records as the API sent them and
  works alongside the files cached before this code existed.
- **What would make us reconsider** — Sidecars going missing or out of sync
  with their data files, or needing to answer questions across all files
  (e.g. "what did I fetch last week?") often enough that a manifest pays off.

## 2026-11-08 — Exclusions are labels on each lap, not deletions

- **Decision** — `exclusion_reasons` returns a list of reasons for each lap. An
  empty list means clean. Cleaning labels laps and doesn't remove them.
- **Requirement** — Every exclusion needs a count, and the clean dataset (for
  fitting) and racing dataset (for evaluation) have to come from the same laps
  under different rules.
- **Options** — (a) A list of reasons per lap: a lap can break two rules, counts
  are easy, and both datasets come from one set of labels. (b) Filter functions
  that drop laps and return a count: simpler to use, but the racing dataset needs
  a second pipeline. (c) One true/false column per rule: clear in pandas, but
  every new rule adds a column.
- **Choice and reason** — (a). Lap 1 with no lap time is a real case of a lap
  with two reasons, and a lap that looks wrong later can still be inspected.
- **What would make us reconsider** — The list becomes awkward once laps are in
  a DataFrame and Parquet file, where (c) may be easier to filter on.

## 2026-11-08 — Tyre age is start age plus laps since the stint began

- **Decision** — `tyre_age = tyre_age_at_start + (lap_number - lap_start)`. Age
  means laps already completed on that set before this lap, so a new set is age
  0 on its first lap. Used sets keep their starting age.
- **Requirement** — Rule 3a: the formula is a likely one, not a fact, and an
  off-by-one error would shift every wear rate.
- **Options** — (a) This formula. (b) Reset to 0 at every stint: ignores used
  sets, and 12 of 60 Hungary 2024 stints start on one. (c) Count a new set's
  first lap as age 1: possible, but doesn't match the docs' "laps completed".
- **Choice and reason** — (a). Hand-calculated ages for drivers 44 and 18 in
  Hungary 2024 match `add_stint_data`. F1's official pit stop summary lists the
  same stop laps as the stints' `lap_end`, and on the five 2024 races every
  stint boundary lines up with a flagged pit-out lap. Details are in
  `docs/DATA_AUDIT.md`.
- **What would make us reconsider** — An outside source disagreeing on stint
  boundaries or starting ages. Compounds and starting ages have not been
  confirmed outside OpenF1.

## 2026-11-08 — In-laps come from stints; laps before a retirement get their own label

- **Decision** — `in_lap` is the last lap of a stint when the driver has another
  stint afterwards. `before_retirement` is the last lap of a final stint when the
  driver has a later lap with no stint. That later lap gets `no_stint`.
- **Requirement** — OpenF1 flags only out-laps. In-laps have to be excluded from
  fitting because they are slow for non-tyre reasons, and they always fall at a
  stint's highest tyre age.
- **Options** — (a) Only the stint rule, recording that 6 laps with a pit-lane
  code are missed: simplest. (b) Also a separate `before_retirement` reason:
  catches them, but the function needs the race's laps as well. (c) Use the
  pit-lane code 2064 directly: exact on these laps, but we can't yet explain the
  nulls in `segments_sector_*`. `/pit` doesn't help: it has the same 164 stops
  as the stint rule and none of the 6 laps.
- **Choice and reason** — (b). The label says `before_retirement` and not
  `in_lap` because one flagged lap (Abu Dhabi 2024, driver 30, lap 55) has no
  pit-lane code, so that driver may not have reached the pits. `no_stint` is a
  separate reason so an unmatched lap can never count as clean, and it doesn't
  say `crash` because the data can't show why the lap has no stint. Retirements
  have not been confirmed.
- **What would make us reconsider** — The excluded-laps sensitivity check showing
  these labels make no difference (drop the extra rule), or an unmatched lap
  turning up mid-race.

## 2026-11-08 — Safety-car laps: lap numbers with a one-lap buffer each side

- **Decision** — A safety car or VSC disrupts every driver's laps from one lap
  before its deployed message to one lap after its end message (`ENDING` or `IN
  THIS LAP`). Only `category == "SafetyCar"` records count. A safety car with no
  end message, or an end message with no deployed message, raises `ValueError`.
- **Requirement** — The 2026-11-05 decision keeps races with a safety car but
  drops the disrupted laps, including deployment and restart. `race_control` only
  gives the deployed and ending laps.
- **Options** — (a) Lap numbers plus one lap each side: simple. The lap after
  covers the restart, and the lap before covers lapped cars if `lap_number`
  follows the leader. Costs about 20 extra laps per event. (b) Time overlap per
  driver using `date_start` and `lap_duration`: most exact, but needs date
  parsing, and `IN THIS LAP` is a warning and not the moment the safety car ends,
  so it still needs a buffer. (c) Only the listed laps: simplest, but keeps the
  slow restart lap as clean.
- **Choice and reason** — (a). The 10 races have only two events, Abu Dhabi 2024
  and Bahrain 2025, and the plan warns against a sophisticated `race_control`
  parser unless it's needed. Raising matches `find_stint`: don't guess when a
  basic assumption fails, because a missing end would otherwise leave disrupted
  laps counted as clean. Local double yellows are not included. No race here has
  a red flag, so the function doesn't handle them yet.
- **What would make us reconsider** — Residuals consistently off near the safety
  car, `lap_number` turning out not to follow the leader, or adding a race with a
  red flag.

## 2026-11-09 — A racing lap excludes safety-car, unscorable and pit laps

- **Decision** — A lap counts as racing unless it has one of these reasons:
  `safety_car`, `null_lap_duration`, `no_stint`, `in_lap`, `pit_out`. `lap_1` and
  `before_retirement` laps stay in. This is narrower than rule 3c's "all
  green-flag racing laps", because in-laps and out-laps are green-flag laps.
- **Requirement** — Rule 3c fits the model on clean laps and also scores it on a
  wider racing set, so that removing the hard laps doesn't flatter the error.
- **Options** — Laps beyond the clean set, 2024 / 2025. (a) Drop only
  `safety_car`, `null_lap_duration` and `no_stint`: 408 / 353, the literal
  reading, but it scores the model on pit-lane time. (b) Also drop `in_lap` and
  `pit_out`: 85 / 101. (c) Also drop `lap_1`: 7 / 2, almost the same as clean, so
  not really a second dataset.
- **Choice and reason** — (b): 5,302 racing laps in 2024 and 5,483 in 2025. The
  simulator charges a stop through the per-circuit pit-loss parameter, so the
  lap-time model is never asked to predict an in-lap or out-lap. Lap 1 stays
  because the simulator does have to predict it. Accepted cost: the clean set has
  no traffic filter, so racing is only about 2% bigger and the two sets of scores
  will probably look similar.
- **What would make us reconsider** — Clean and racing scores being so close that
  the second set tells us nothing, lap 1 dominating the racing error, or the
  backtest showing that pit loss misses part of the cost of in-laps and out-laps.

## 2026-11-09 — Dataset keeps the reasons list plus `is_clean` and `is_racing`

- **Decision** — Each row in `lap_dataset.parquet` has the `exclusion_reasons` list
  and two true/false columns, `is_clean` and `is_racing`, set only in
  `build_race_rows`. The file is written with `pyarrow` from the list of dicts.
- **Requirement** — The 2026-11-08 labels decision left open whether a list would
  be awkward once laps are in Parquet. Filtering has to be simple, and both
  datasets have to come from one definition.
- **Options** — (a) The list plus two true/false columns: simple filtering and the
  reason stays visible, but the columns are derived. (b) Only the list: nothing
  repeated, but every filter re-runs the rules, so "clean" could end up defined
  in two places. (c) One true/false column per reason: easy in pandas, but every
  new rule adds a column.
- **Choice and reason** — (a). `pyarrow` is the only dependency added, because
  Parquet needs it and it writes a list of dicts directly. It keeps `tyre_age`
  and `stint_number` as integers with real nulls, where a pandas DataFrame would
  have turned them into decimals. Pandas waits until the exploratory analysis.
- **What would make us reconsider** — Code filtering on the reasons list instead
  of the flags, or the flags and the list getting out of step.

## 2026-11-10 — Observed range is the oldest tyre age on a clean lap, kept per year

- **Decision** — The observed range for the simulator's guard (rule 6) is the
  highest `tyre_age` on a clean lap for each circuit, year and compound, from
  `max_clean_tyre_age`. A pair with no clean laps has no key, never 0. The table
  is rebuilt from `lap_dataset.parquet` when needed, not saved as its own file.
- **Requirement** — Rule 6 and Plan Week 3 task 3: the simulator must refuse or
  flag stints beyond what the data covers for that compound at that circuit.
- **Options** — (a) Highest `tyre_age` on a clean lap: exactly what the model is
  fitted on, and correct for used sets. (b) Highest `tyre_age` on any lap:
  usually one lap more, because the oldest lap of a stint is the in-lap, which
  the model never learns from. (c) Longest stint in laps from `/stints`: the
  plan's wording, but understates used sets (a 20-lap stint on a 3-lap-old set
  reaches age 22).
- **Choice and reason** — (a). A missing key says "no data", and 0 would wrongly
  say the compound was seen there. Sakhir 2024 has no MEDIUM, and Monza 2024 SOFT
  only reaches age 1. Keyed by year because 2025 stints run much longer (Monza
  MEDIUM 20 in 2024 vs 44 in 2025, Hungaroring HARD 40 vs 54), so a guard built
  from 2024 only would refuse many real 2025 strategies in the backtest. Which
  years the guard uses is left for Week 6.
- **What would make us reconsider** — The Week 6 choice of years for the guard,
  or a pair with a high age but very few supporting stints, which may need a
  stint count next to it.

## 2026-11-11 — Plots with matplotlib only, from a script

- **Decision** — Exploratory plots are made by `scripts/explore.py` with
  matplotlib and written as PNGs to `docs/figures/`. No pandas and no notebook
  yet; the data functions stay plain Python over the list of dicts.
- **Requirement** — Plan Week 3 task 10: plots of lap time against tyre age and
  against race lap, as part of a reproducible exploratory analysis.
- **Options** — (a) matplotlib only, from a script. (b) matplotlib plus pandas:
  grouping becomes a `groupby` one-liner, but adds a dependency before we need
  it and skips writing the grouping logic. (c) A Jupyter notebook: good for
  poking around, but adds jupyter, is hard to diff and easy to leave in a state
  that won't re-run.
- **Choice and reason** — (a). matplotlib is the one dependency added, because
  charts can't be drawn without a plotting library. Grouping stays in tested
  functions in `analysis.py`; the script only draws. pandas comes in Week 4 with
  scikit-learn if there's a real need for it.
- **What would make us reconsider** — Week 4 feature building getting awkward
  with lists of dicts, or needing interactive exploration that a script makes
  slow.

## 2026-11-12 — Target is delta to the driver's median clean lap, built in features.py

- **Decision** — The model predicts `delta`: lap_duration minus that driver's
  median clean lap in that race. It's computed at modeling time by
  `driver_reference_laps` and `add_delta` in `src/pitwall/features.py`, not
  stored in `lap_dataset.parquet`. No reference or no lap time gives None.
- **Requirement** — Plan Week 4 task 1 and rule 1: remove the circuit, car and
  driver pace so the model only learns tyre-age and race-lap effects.
- **Options** — Target: (1) delta to the driver's median clean lap, or (2) raw
  lap time with circuit as a feature. Where it lives: (a) `features.py` at
  modeling time, (b) a column in the Parquet dataset, (c) inside the training
  code.
- **Choice and reason** — (1) and (a). Delta removes circuit and driver pace in
  one subtraction. The dataset stays facts about laps, so changing the
  reference later needs no rebuild, and the evaluation and simulator can share
  the same function. Accepted cost: the reference comes from the race itself,
  so it isn't known mid-race. That's fine because the simulator only runs on
  races in the dataset, but it blocks live or replay use without a different
  reference.
- **What would make us reconsider** — Wanting replay mode or an unseen race, or
  the median being pulled by a driver with very few clean laps.

## 2026-11-12 — Metrics written by hand; split rejects unexpected years

- **Decision** — MAE, RMSE and bias come from `score` in
  `src/pitwall/evaluation.py`, written in plain Python, with error defined as
  predicted minus actual. `split_by_year` puts 2024 in train and 2025 in test,
  and raises `ValueError` for any other year.
- **Requirement** — Plan Week 4 tasks 3, 4 and 7: a zero baseline and a
  2024/2025 split, scored with MAE, RMSE and bias in seconds on the clean and
  racing laps.
- **Options** — Metrics: (a) write them by hand, (b) add scikit-learn now and
  use its metric functions. Unexpected years: raise, or silently drop them.
- **Choice and reason** — (a). Each is one line, needs no dependency yet, and
  writing them makes the scores mean something. Raising on other years because
  silently dropping rows would shrink the data without anyone noticing.
- **What would make us reconsider** — Needing weighted or sliced metrics that
  scikit-learn gives for free, or adding a third year or an unseen-circuit test
  set, which would need a split by more than year.

## 2026-11-13 — Models use pandas and a scikit-learn Pipeline

- **Decision** — Model code in `src/pitwall/model.py` builds a scikit-learn
  `Pipeline`: a `ColumnTransformer` (one-hot `compound`, passthrough numeric
  columns, optional `PairAgeColumns` step) then `LinearRegression`. Rows become
  a pandas DataFrame only at model time; the dataset functions stay list of
  dicts.
- **Requirement** — Plan Week 4 task 5: a basic scikit-learn pipeline, and the
  same columns, in the same order, for 2024 training and 2025 test rows.
- **Options** — (a) `DictVectorizer` on a feature dict per lap: no pandas,
  interaction keys written by hand. (b) pandas + `ColumnTransformer`: the most
  common production setup, but interactions need a custom step. (c) A
  hand-built list of floats: column order kept by hand.
- **Choice and reason** — (b), to learn the standard tooling. The wear rate per
  compound@circuit is a small custom transformer class because it has to
  remember the training pairs between fit and predict, which a plain function
  can't do inside a pipeline. Plain `tyre_age` is left out when the per-pair
  columns are on, because they add up to it.
- **What would make us reconsider** — The custom step growing beyond a thin
  wrapper, or needing standard errors (then statsmodels or a formula library).

## 2026-11-13 — 2025 laps on a pair with no 2024 training laps are left out of scoring

- **Decision** — `scripts/evaluate.py` drops 2025 rows whose compound@circuit
  pair has no 2024 clean laps, for every model, and prints the count. Today
  that's Sakhir MEDIUM: 520 rows (443 racing laps).
- **Requirement** — Model C has no wear rate for a pair it never saw, and
  `PairAgeColumns` raises rather than guess.
- **Options** — (a) Leave those laps out of scoring for all models. (b) Use a
  fallback rate (e.g. Model B's shared slope) for unseen pairs. (c) Train on
  some 2025 laps of that pair: leaks test data, rejected.
- **Choice and reason** — (a). All models are scored on the same rows, and it
  matches the observed-range guard (2026-11-10), which has no Sakhir MEDIUM key,
  so the simulator would refuse those stints anyway. Accepted cost: the test set
  is about 8% smaller and says nothing about that pair.
- **What would make us reconsider** — Partial pooling in Week 5, which gives
  sparse or unseen pairs a rate borrowed from the compound, or the backtest
  needing Sakhir MEDIUM stints.

## 2026-11-14 — Fuel proxy is race fraction; wear stays linear

- **Decision** — Model B uses `race_fraction` (lap_number / the race's highest
  lap_number, from `add_race_fraction`) as its fuel term instead of
  `lap_number`. The tyre-age term stays a straight line. Model choices are made
  on held-out 2024 races (`leave_one_race_out`).
- **Requirement** — Week 5: one improvement, chosen from residuals, kept only if
  it helps on held-out races.
- **Options** — (a) Curved wear term: suggested by the +0.78 s bias at age 30+
  on 2025, but held-out 2024 bias is within ±0.04 s at every age, so not
  justified. (b) Fuel by race fraction: one coefficient, testable with
  leave-one-race-out. (c) A fuel rate per circuit: each circuit is in 2024 once,
  so leave-one-race-out can't validate it. (d) Keep B as is.
- **Choice and reason** — (b). Held-out 2024 MAE 0.572 -> 0.545 s, RMSE 0.780 ->
  0.737 s, and the per-circuit drift (Hungaroring falling to -1.21 s, Monza
  rising to +0.70 s) mostly goes away. The same fuel load spread over 53 or 70
  laps gives a different gain per lap, which fits that pattern; track evolution
  is in the same term, so this isn't proof. Wear rate is unchanged (0.061 s/lap).
  Cost: one feature function and one parameter.
- **What would make us reconsider** — Races of very different length added later
  behaving badly, a shortened race (the highest lap_number would be wrong), or
  a 2024 old-tyre bias appearing once more races are added. Also: per-circuit
  wear (Model C) can't be checked by leaving one 2024 race out, so it needs its
  own validation plan.

## 2026-11-16 — Add the 2023 editions of the 5 Grands Prix

- **Decision** — Add Bahrain, Hungary, Monza, Singapore and Abu Dhabi 2023
  (7953, 9133, 9157, 9165, 9197) to the dataset, to validate per-circuit wear
  across years without using 2025.
- **Requirement** — Each circuit is in 2024 only once, so leaving one 2024 race
  out also leaves its circuit out, and Model C (wear per compound@circuit) can't
  be scored. 2025 stays the untouched test set.
- **Options** — (a) Hold out drivers within 2024: no new data, but train and
  validation share the same races, so it can't see a change between years.
  (b) Add 2023: a real same-circuit, different-year check, but a scope change
  (CLAUDE.md names 2024 and 2025) and a fetch, audit and clean. (c) Validate on
  2025: spends the test set.
- **Choice and reason** — (b). It tests what the simulator needs: does a
  circuit's wear rate from one year hold in another. All five are dry with no
  sprint and pass the join checks (`docs/DATA_AUDIT.md`). `split_by_year` now
  takes the years explicitly and leaves other years out, and
  `leave_one_year_out(rows, [2023, 2024])` gives the cross-year splits, so 2025
  can't enter validation. Accepted cost: 2023 cars and
  tyres differ, and Monza SOFT and Yas Marina SOFT have no 2023 laps.
- **What would make us reconsider** — 2023-to-2024 differences larger than the
  per-circuit effects we're trying to measure, so the check says more about the
  year than the circuit. CLAUDE.md's data and evaluation rules still say 2024
  and 2025 and need updating to match.

## 2026-11-16 — Race distance is the highest timed lap; laps past it are `after_finish`

- **Decision** — `race_distance(laps)` is the highest `lap_number` with a
  `lap_duration`. A lap past it gets the reason `after_finish` (not clean, not
  racing), the lap before it is not `before_retirement`, and `add_race_fraction`
  divides by the same distance.
- **Requirement** — Monza, Singapore and Abu Dhabi 2023 list one untimed lap per
  finisher after the chequered flag. Unhandled, it labels each finisher's real
  last lap `before_retirement` and makes the race one lap too long for the fuel
  proxy.
- **Options** — (a) Highest timed lap: simple, matches the chequered-flag lap in
  all 15 races. (b) Chequered-flag lap from `race_control`: the official answer,
  but Monza 2023 has no chequered message. (c) A lap starting after the winner
  finishes (`date_start`): catches lapped finishers too, but needs date parsing.
- **Choice and reason** — (a). It catches 20 of the 22 phantom laps with no new
  data, and changes nothing in 2024 or 2025. A label, not a deletion, as with the
  other reasons.
- **What would make us reconsider** — More races where lapped finishers' phantom
  laps fall inside the race distance (2 laps here, Monza 2023 drivers 20 and 27),
  then switch to (c). Or a race where the leader's last lap has no time.

## 2026-11-16 — Per-circuit wear by partial pooling; alpha chosen in the backtest

- **Decision** — Add `PooledWearModel` in `model.py`: one shared wear rate plus
  a per compound@circuit adjustment, fitted in one go by solving
  `(XᵀX + alpha·D) b = Xᵀy`, where `D` penalises only the adjustment columns.
  `numpy` is now a declared dependency for this. No `alpha` is chosen yet:
  several values (1e3 to 1e6) go into the race-total backtest, and the choice
  is made there.
- **Requirement** — Cross-year (2023 vs 2024): B (one rate) has per-circuit bias
  from -0.12 to +0.22 s/lap, and C (a rate per pair) removes it but gives thin
  pairs implausible rates (2024 SOFT@Monza, 1 lap: -0.39 s/lap, i.e. getting
  steadily faster over the whole stint). Warm-up over the first laps is
  plausible, but a linear model can't represent it.
- **Options** — (a) Two steps: fit B, then Ridge on B's errors with only the
  per-pair columns. (b) One sklearn `Ridge` with the unpenalised columns scaled
  up so their penalty is negligible. (b′) Solve the selectively penalised
  equations directly with numpy. (c) A mixed model with `statsmodels`.
- **Choice and reason** — (b′). (a) failed its own synthetic test: with B's
  compound offsets and shared rate frozen, step 2 recovered only about a quarter
  of a true 0.10 s/lap rate difference (MEDIUM came out at 0.115 against a true
  0.150), even with almost no penalty. (b′) recovered 0.149, keeps the penalty
  explicit, and gives coefficients in normal units. (b) does the same through a
  scale-factor trick, and (c) adds a dependency and a second model interface.
  `alpha` must be > 0, because the shared `tyre_age` column is the sum of the
  per-pair columns.
- **Why alpha waits for the backtest** — Cross-year lap MAE is flat across every
  alpha (0.518 to 0.523 s, B 0.519, C 0.523), while the spread of circuit bias
  goes steadily from C's 0.08 s to B's 0.34 s as alpha grows. Lap error mostly
  cancels over a race, and bias adds up, so race totals are the test that can
  choose. Also, the thin pairs that pooling exists for (Monza SOFT, Yas Marina
  SOFT, Sakhir MEDIUM) appear in only one of 2023 and 2024, so cross-year scoring
  can't see them. At alpha 1e4, 2024 SOFT@Monza is pulled to the shared rate
  (+0.068), while Sakhir SOFT keeps its own (+0.088).
- **What would make us reconsider** — The backtest not separating the alphas
  either (then pick on bias spread and plausibility of the thin-pair rates), or
  residuals by tyre age showing curvature (warm-up, a cliff) that a linear rate
  can't fit.

## 2026-11-17 — A strategy is a plain dict; pit on lap N means a new set from lap N+1

- **Decision** — A strategy is `{"compounds": [...], "pit_laps": [...],
  "start_ages": [...]}`, with `start_ages` optional (default all 0, new sets).
  Lap N is the in-lap on the old set; lap N+1 is the new set's first lap at its
  start age, the same convention as the dataset's `tyre_age`.
- **Requirement** — Plan Week 6 task 1; CLAUDE.md: a strategy is a small
  explicit structure, agent-ready.
- **Options** — (a) Plain dict. (b) Frozen dataclass. (c) List of stints with
  lengths instead of pit laps.
- **Choice and reason** — (a). Matches the list-of-dicts style and is already
  JSON for Phase 2. `start_ages` is there because the backtest replays real
  strategies on used sets (12 of 60 Hungary 2024 stints).
- **What would make us reconsider** — Validation code repeatedly checking the
  same shape errors that a dataclass would catch at construction.

## 2026-11-17 — Range guard flags, doesn't refuse; limits from the training years

- **Decision** — `simulate` raises on impossible strategies (`validate_strategy`)
  and on a compound with no clean laps at the circuit. A stint older than the
  oldest clean tyre age for its compound@circuit in 2023-2024
  (`observed_max_ages`) is returned as a flag; the total is still computed. The
  in-lap of a stint that ends in a stop is not compared, the lap before it is.
- **Requirement** — Rule 6: refuse or flag stints beyond the observed range.
  The 2026-11-10 decision left open which years the guard uses.
- **Options** — Behaviour: (a) flag, (b) refuse, (c) list problems, never raise.
  Years: (a) training years 2023-2024, (b) the simulated race's own year.
- **Choice and reason** — (a) and (a). Refusing would drop real 2025 strategies
  from the backtest (Hungaroring HARD reaches 54 in 2025, limit 40). The limit
  is what the model learned from; the race's own year would use 2025 for a
  choice and hide extrapolation. In-laps are never clean, so counting them
  would flag the very stints the limit came from.
- **What would make us reconsider** — Most 2025 backtest strategies getting
  flagged (the flag stops meaning anything), or the UI needing a hard refuse.

## 2026-11-17 — Pit loss per circuit from in-lap and out-lap residuals

- **Decision** — Pit loss for a circuit is the median, over 2023-2024 stops,
  of (actual minus predicted delta) on the in-lap plus the out-lap
  (`stop_losses`, `pit_loss_by_circuit`). Stops with a safety-car lap, an
  untimed lap or no out-lap are kept with a skip reason, not counted. One number
  per circuit, no team term.
- **Requirement** — Rule 5 and Plan Week 6 task 4: pit loss per circuit,
  pit-lane time minus racing time over the same stretch, kept as a parameter.
- **Options** — (a) Lap residuals with the model. (b) `/pit` `lane_duration`
  minus an estimated racing time for the pit-lane stretch. (c) (a) with `/pit` as
  a check. Also considered: a per-team number or team offset.
- **Choice and reason** — (a). No new data, and it is exactly what `simulate`
  leaves out (it predicts in-laps and out-laps as normal laps), so nothing is
  counted twice. (b) needs a guess for the racing time over the pit stretch.
  Median, because single stops reach 109 s. Teams left out: 5-9 stops per team
  per circuit, the team-specific part is only stationary time and the out-lap,
  and team data isn't in the dataset. Quartile spread is 1.5-4 s per circuit;
  2023 and 2024 medians differ by 0.8-1.4 s.
- **What would make us reconsider** — Backtest errors that line up by team, or
  pit loss changing a lot when measured with the chosen pooled model instead
  of Model B.

## 2026-11-17 — Lap-1 loss per circuit, measured like pit loss

- **Decision** — `simulate` adds `lap_one_loss` to lap 1: per circuit, the
  median over the training years of actual minus predicted delta on lap 1
  (`lap_one_losses`, aggregated with `pit_loss_by_circuit`). A circuit with no
  measurable lap 1 in the training year (Yas Marina 2024, VSC on laps 1-4) gets
  the median over all circuits that year (7.9 s), with a printed note.
  Stops or laps the model can't predict are skipped as `model_cannot_predict`.
- **Requirement** — The model never fits lap 1 (not clean), so it predicted the
  standing start as a normal lap: every Hungaroring 2024 lap 1 was 4-14 s
  slower than predicted, biasing every race total.
- **Options** — (a) A lap-1 loss per circuit. (b) Start backtest totals at lap
  2. (c) Ignore it: the same for every strategy, so comparisons don't change.
- **Choice and reason** — (a). Race totals in the app and the backtest stay
  realistic, and it reuses the pit-loss method and code. Medians by circuit
  range from 4.8 s (Monza 2023) to 9.4 s (Singapore 2024), each with a
  quartile spread of 3-4 s, so one number for all circuits would be too coarse.
- **What would make us reconsider** — Lap-1 loss varying a lot by grid
  position (front vs back), or the error split showing lap 1 carries much of
  the race-wide bias.

## 2026-11-17 — Final model: PooledWearModel, alpha 1e5 (P_1e5)

- **Decision** — The simulator and app use `PooledWearModel(alpha=100_000,
  fuel_column="race_fraction")`: one shared wear rate plus per compound@circuit
  adjustments pulled toward it. Which years train the final model is still open.
- **Requirement** — Rule 3 (wear varies by circuit) and rule 3d (pooled linear
  first, extra structure only for a shown problem). Week 7 needs one model to
  compare strategies with.
- **Options** — (a) P_1e5. (b) B_frac (one wear rate for all pairs). (c) Keep
  it open and study the race-lap term further.
- **Choice and reason** — (a). On the cross-year backtest the two models are
  about the same (MAE 11.81 vs 11.91 s over 76 driver-races). Their errors split
  the same way (Session 23: lap 1 and stops within about ±4 s per race, most of
  the bias on normal laps), and their leftover slopes match (`residual_trends`:
  race-lap slopes up to +1.4 / -1.0 s over the race, tyre-age slopes up to
  0.04-0.07 s per lap at Sakhir and Monza 2024). With no evidence either way,
  rule 3 decides. (b) breaks rule 3. (c) won't settle it: the split between
  fuel and wear within a race is only approximate (rule 3b).
- **What would make us reconsider** — A strategy ranking that depends on a
  per-pair adjustment fitted on few laps, P_1e5 doing clearly worse than B_frac
  on the 2025 test, or the ±0.05 s/lap wear sensitivity in Week 7 showing that
  per-circuit wear changes no ranking (then B_frac is enough).

## 2026-11-18 — Final model trains on 2023+2024; wear sensitivity is ±q75 of held-out error

- **Decision** — P_1e5 is fitted on 2023+2024 for the simulator, app and final 2025 test.
  Wear sensitivity uses ±0.032 s/lap, the 75th percentile of |leftover tyre-age slope| on
  held-out years (`comparison.fit_inputs`).
- **Requirement** — Rule 4 (2025 never used for selection), Week 7 task 4 (uncertainty
  values must come from somewhere documented).
- **Options** — Training years: 2023+2024, 2024 only, add 2025. Wear range: ±0.05 (by
  hand), year-to-year change in fitted rates (max 0.015, shrunk by pooling), ±q75 of
  held-out error (0.032).
- **Choice and reason** — 2023+2024 (more laps per pair, 2025 stays held out) and ±q75
  (measures how wrong the wear rate was on an unseen year).
- **What would make us reconsider** — More races per circuit, or a wear model change that
  moves the held-out error.

## 2026-11-18 — Wear stays linear; the 2025 old-tyre bias is a year effect

- **Decision** — No curved wear term. The 2025 old-tyre bias (+0.25 s at age 20-29,
  +0.71 s at 30+) is reported as a limitation.
- **Requirement** — Rule 3d and rule 4.
- **Options** — Keep linear and document it; include 2025 in training; fit a flattening curve.
- **Choice and reason** — Keep linear. Cross-year 2023/24 bias is within ±0.07 s up to age
  39 (11,000+ laps); only 40+ drifts (-0.33 s, 55 laps), the other way. A curve chosen on
  2023/24 would come out near linear; one chosen to fix 2025 would be tuning to the test.
- **What would make us reconsider** — 2023/24 data or added races showing the bias at old
  ages, or a decision to train on 2025.

## 2026-11-18 — The app compares one driver's real strategy with alternatives

- **Decision** — Pick a race and a driver (SPEC section 1); alternatives are ranked against
  the simulated time of the driver's real strategy, on safety-car-free races 2023-2025.
  Alternatives start on the real first set when they start on the same compound.
- **Requirement** — SPEC sections 1 and 3; the simulator had no safety car.
- **Options** — Races: safety-car-free only, or all 15 with the safety-car ones marked.
  Gaps against: the simulated real strategy, or the real race time.
- **Choice and reason** — Safety-car-free only; gaps against the simulated real strategy so
  the model's shared race error cancels.
- **What would make us reconsider** — Modelling safety cars (planned, see v2 below).

## 2026-11-18 — Strategy gaps are validated on pairs of cars, with pace from the first half

- **Decision** — The check of "does the simulator get strategy differences right" uses pairs
  of cars with different strategies in one race. Each car's pace is the median of
  (lap time - model delta) over its first-half clean laps; only the second half is scored.
- **Requirement** — The app shows gaps between strategies, which a race-total backtest does
  not test.
- **Options** — Whole-race median pace (what the app used); first-half raw median; first-half
  model-adjusted pace.
- **Choice and reason** — First-half model-adjusted. Whole-race pace already contains the
  strategy's effect, so that test was close to a coin flip (52% right) and says little.
  Model-adjusted over the whole race would be circular. First-half adjusted had the lowest
  error (10.8 s vs 11.8 s raw) with held-out scored laps.
- **What would make us reconsider** — A same-car-two-strategies data source, or a
  strategy-pair result that shifts a lot with a different split point.

## 2026-11-18 — v2 scope: traffic (replayed field) and replayed real safety cars, after v1

- **Decision** — After the v1 Definition of Done, v2 adds (1) traffic: one simulated car
  against the real field replayed from its real lap times, with a time penalty close behind
  slower cars, then (2) safety cars at the laps they really happened: fixed slow laps, a
  reduced pit loss. Random (probabilistic) safety cars stay out of scope.
- **Requirement** — The model prefers evenly split stints for most cars because it has no
  reason to pit early or late; traffic and safety cars are two such reasons. CLAUDE.md listed
  traffic as out of scope for v1.
- **Options** — Finish v1 then v2; validation then v2 then deploy last; start v2 now. Safety
  cars: replay the real ones, or random ones.
- **Choice and reason** — Finish v1 first, replay real safety cars. v1 gives a finished,
  honest project and the pair check is the yardstick v2 must beat. Random safety cars need a
  probability we can't estimate from 4 races.
- **What would make us reconsider** — Traffic penalty not being estimable from lap timing, or
  v2 failing to improve the yardstick (then it stays off by default).

## 2026-11-18 — App verdict has three tiers from the strategy-pair check

- **Decision** — The verdict says what the model prefers, never that a strategy was better.
  Four outcomes by the best unflagged alternative's gap at the best estimate: faster by under
  3 s "too close for the model to call", 3-10 s "leans towards", 10 s or more "prefers"; none
  faster "agrees". It always names the model's blind spot (undercuts, traffic, tyre allocation).
- **Requirement** — Rule 9 (no optimal-strategy claims). A first version said "faster under
  every assumption" for 120 of 124 cars.
- **Options** — No margin; a fixed 1 s margin (a guess); tiers from the pair check; one cut-off.
- **Choice and reason** — Tiers. In the pair check the predicted faster car really was faster
  about 55% under 3 s (n=124 pairs), about 65% at 3-10 s, about 90% above 10 s. Thresholds
  are in `comparison.verdict`; the headline states the hit rate in plain words.
- **What would make us reconsider** — Traffic or safety-car replay (v2) changing these hit
  rates; re-run `print_strategy_pair_check` and move the thresholds.

## 2026-11-18 — A car's pace comes from its first half, not the whole race

- **Decision** — `compare_driver` (the app) sets each car's reference lap to
  `backtest.first_half_pace`: the median over first-half clean laps of lap time minus the
  model's delta. A car needs at least 5 such laps (all 124 comparable cars have them).
- **Requirement** — The whole-race median lap already contains the effect of the strategy
  being tested (fresher tyres make a faster median), which hides part of the strategy's effect
  in the "pace" and makes the model-vs-real error look smaller or larger than it is.
- **Options** — Whole-race median (rule 1 default); first-half adjusted pace.
- **Choice and reason** — First-half. Cross-year whole-race backtest (76 driver-races,
  P_1e5): MAE 11.81 s -> 10.41 s, bias -0.92 -> +2.58 s, median |error| 8.87 -> 9.45 s. The
  gate was "MAE no worse". Gaps between strategies don't depend on the pace level, so the
  verdicts are unchanged; only the real-vs-simulated panel moves. `backtest_race` keeps the
  whole-race median as default (`pace="first_half"` is the option).
- **What would make us reconsider** — The +2.6 s bias getting larger with traffic or
  safety-car replay, or a split point other than half distance doing clearly better.

## 2026-11-18 — Traffic: a lap-time penalty by gap to the car ahead, on by default in the app

- **Decision** — `traffic.py` estimates the lap-time loss by gap to the car ahead (bins 0.5, 1,
  1.5, 2.5, 4 s) from clean-lap model residuals with each driver's race average removed, then
  replays the real field: a car's gap is the time since another car started the same lap number,
  derived from `date_start`. The real strategy sits where it really was; an alternative's position
  moves by how much faster or slower it is than the real strategy ("anchored"), so the model's
  shared error cancels. Other cars never react. The app includes it by default (toggle off).
- **Requirement** — The model preferred evenly split stints for most cars because it had no reason
  to pit early or late; traffic is one such reason (v2 scope, DECISIONS above).
- **Options** — Use the OpenF1 `/intervals` endpoint (only 1 driver of 1 race cached; would need
  ~15 races x 20 drivers of requests); derive gaps from lap start times (chosen); penalty per
  circuit (about 5 races x 2 years of data per bin, too thin); one pooled penalty table (chosen).
- **Choice and reason** — Gate: close-behind laps lose time, with a smooth dose-response in both years
  (< 0.5 s: +0.5 s, 0.5-1 s: +0.18, 1-1.5 s: +0.05, free air: -0.11, relative to an average lap;
  positive for 9 of 10 race-years). Pair check, 2023/24 cross-year (tuning set): MAE 11.21 -> 10.50 s,
  hit rate 70% -> 71%; whole-race backtest: MAE 10.41 -> 9.60 s with first-half pace, bias +2.58 ->
  +0.36 s. 2025, read once: MAE 10.86 -> 10.66 s, hit rate 76% -> 82%. Whole-race pace with traffic is
  worse (12.06 s) because that pace already contains the traffic, so traffic only goes with first-half pace.
- **Known limit** — The test only simulates real strategies. Whether the penalty describes an
  alternative strategy (a car rejoining behind different cars) cannot be checked: there is no real
  data for it. The app says so. With traffic the model agrees with the real strategy for 18 of 124
  cars (2 before), which is the effect traffic was meant to have.
- **What would make us reconsider** — A circuit-level check showing the penalty is wrong at one
  track, a penalty that changes much between years once more races are added, or an overtaking
  rule becoming estimable.

## 2026-11-18 — Safety cars are replayed from the real windows; stops under a real one are cheaper

- **Decision** — `neutralisation.py` reads the exact safety-car and VSC windows from `race_control`
  (`scripts/build_neutralisations.py` -> `data/processed/neutralisations.json`). On a neutralised lap
  the simulator uses the field's real lap time (median of the cars' lap times that lap, pit laps left
  out) instead of the model; a stop whose in-lap is under a *real* safety car costs `ratio` x the
  circuit's normal pit loss, with `ratio` the median over stops really made under one in the training
  years (0.68, 14 stops, all Singapore 2023); a stop under a VSC costs the normal amount; no traffic
  penalty on neutralised laps or the laps next to them. Races with a safety car become selectable
  in the app and a "pit under the safety car" candidate is added where a real one occurred. Random
  safety cars stay out of scope.
- **Requirement** — v2 scope (above): replay real safety cars, check against the yardstick.
- **Options** — Replay laps only; replay laps + cheaper stops; ignore safety-car races (status quo).
  Pit-loss saving per circuit (too few stops); one pooled ratio of the normal pit loss (chosen).
- **Choice and reason** — Whole-race backtest on the 4 races, each scored without its own year:
  mean error 101.6 s with the neutralised laps treated as normal racing, 13.2 s replaying the lap times,
  12.7 s with cheaper stops; the one fully out-of-sample race (Sakhir 2025, 19 cars): 117.7 -> 12.3 -> 11.0 s.
  Stops under a VSC were not cheaper in the data (4 stops, 28-57 s), so they keep the normal cost.
- **Known limits** — The ratio comes from one real safety car in the training years (the test race was
  scored with it out of sample, but Singapore 2023 cannot be: its fold has no real safety car, so it is
  charged normal stops). Singapore 2023's 21 s error is the model's late-race bias there, not the replay
  (normal-lap error -15.8 s, laps 30-43). Strategy-gap hit rates were not re-measured on these
  races (too few cars), so the verdict thresholds come from races without a safety car; the app says so.
- **What would make us reconsider** — More races with a safety car showing a different stop discount,
  or a circuit whose neutralised laps are poorly represented by the field median.

## 2026-11-18 — The corpus is every usable 2023-2025 race (57 of 70), not 15

- **Decision** — The dataset is built from every Grand Prix OpenF1 lists for 2023-2025 (`ingestion.race_sessions`,
  from the cached sessions files; the cancelled 2023 Emilia Romagna GP is dropped), minus races the simulator
  can't represent: a red flag before the chequered flag (8), any intermediate or wet tyre (8; 3 are both), or more
  than 5% of laps with no stint data (none). 57 races, 62,959 laps, 24 circuits. Every race and its reason is in
  `docs/RACE_SELECTION.md`. Training stays 2023+2024 (36 races); 2025 (21) is the held-out test.
- **Requirement** — A larger training corpus, including safety-car races; stay inside the 2022-2025 regulation
  period. CLAUDE.md's "dry, non-sprint, 8-10 races" was written for hand-built v1.
- **Options** — 2023-2025 from OpenF1 only; add 2022 via FastF1 (new dependency, second source and schema, ~22
  races); keep the 15 races. Filters: all dry races without red flags (chosen); also drop sprint weekends;
  include everything.
- **Choice and reason** — 2023-2025 only (OpenF1 has no 2022: `sessions?year=2022` returns "No results found").
  Sprint weekends stay in: the dataset only holds the Grand Prix itself, so the sprint format doesn't enter the
  laps. Wet and red-flag races stay out: the simulator is dry-only and has no free tyre change or standing restart.
- **Data fixes this needed** — A safety car still out at the chequered flag has no end message (Melbourne 2024,
  Baku 2024, Montreal 2025): it now ends on the chequered flag's lap in both parsers. A virtual safety car
  upgraded to a safety car has no "ENDING" message (Shanghai 2024, Lusail 2024): it ends when the safety car is
  deployed. A neutralised lap needs at least 3 cars on plain laps for a field lap time (Spielberg 2023 and 3 more
  races have every car pitting together): those 5 races are not offered in the app. A circuit whose lap 1 was
  under a safety car in every training race gets the all-circuit median lap-1 loss (7.7 s), as the cross-year
  backtest always did. Races at circuits with no training race are hidden (Interlagos 2025, Monte Carlo 2025).
  50 of the 57 are offered.
- **Checked on the larger corpus** — The model choice does not change: cross-year clean-lap MAE B_frac 0.557,
  P_1e4 0.568, P_1e5 0.558, P_1e6 0.556, free per-circuit wear 0.623 s; race totals 11.7 / 11.3 / 11.6 / 11.7 /
  18.0 s. P_1e5 stays (rule 3; DECISIONS 2026-11-17). On the 2025 test it is marginally behind B_frac (0.599 vs
  0.586 s), which is not "clearly worse".
- **What would make us reconsider** — A 2022 source worth a new dependency, or more seasons arriving.

## 2026-11-18 — Whole-race validation: leave-one-stint-out, and a verdict from refits (supersedes the 3 s / 10 s tiers)

- **Decision** — (1) The strategy-pair check is relabelled "second half only". (2) New check: predict each stint
  from the same car's other stints (`backtest.stint_holdout_errors`), over the whole race. (3) The verdict no
  longer uses fixed 3 s and 10 s tiers. A gap must exceed `STINT_ERROR_FLOOR` (the median stint-total error, 5.3 s)
  and the alternative must be faster in at least 70% ("leans") or 90% ("prefers") of 20 refits of the model, pit
  loss, traffic and safety-car stop ratio on random 80% subsets of the training races (fixed seed; every compound@circuit
  pair kept).
- **Requirement** — Strategy spans the whole race. The pair check took each car's pace from its first half and
  scored only the second half, so it could not test first-stint choices, and the thresholds read off it rested on
  half the evidence.
- **Options** — Stint check + refit verdict (chosen); stint check + teammate pairs (tried: 20 pairs in 7 races,
  median real gap 17.6 s, pace differences swamp the signal); relabel only.
- **Choice and reason** — Within-car, within-race variation is the only way to separate pace from strategy
  across the whole race. Stint-total error: 7.7 s (median 5.3) cross-year over 1,318 stints, 8.2 s (median 5.6)
  on 2025's 801, against 25.6 / 29.5 s with no tyre or fuel effect. The pair check on the larger corpus agrees
  with the 5.3 s floor: under 5 s predicted gap the faster car is picked 45-60% of the time, 71-75% at 5-10 s,
  85-99% above 10 s. Refits measure how much a comparison depends on which races the model saw (20 refits take
  about 2 s per page and 5 s at startup); they are not a probability that the alternative really is faster.
- **Known limits** — The floor and the refits both understate model misspecification the stint check can't see
  (undercuts, tyre allocation). The thresholds 70% and 90% are judgment calls.
- **What would make us reconsider** — A same-car-two-strategies data source, or the floor moving by more than
  about 1 s when the corpus grows (update `STINT_ERROR_FLOOR`).

## 2026-11-18 — Correction: the old-tyre bias is not only a 2025 effect; the first stint is predicted too fast

- **Decision** — This corrects "Wear stays linear; the 2025 old-tyre bias is a year effect" (2026-11-18, above),
  which rested on 15 races. No model change yet; both findings are logged as leads.
- **Evidence on 57 races** — Old tyres: cross-year 2023/24 bias at 30+ laps is +0.19 s/lap (both held-out years
  positive, 1,613 laps); on 2025 it is +0.46 s with the model worse than the zero baseline (MAE 0.81 vs 0.70 s).
  First stints: predicted 0.17 s/lap too fast cross-year and 0.12 s on 2025; last stints about right (stint check).
  Both are specific residual problems that persist across periods (rule 3d).
- **Options** — A flattening wear term; a non-linear fuel term; document and leave. Not tried: it changes the model
  and CLAUDE.md asks before a scope change.
- **What would make us reconsider** — An improvement on 2023/24 cross-year clean-lap MAE and stint error, without
  touching 2025.

## 2026-11-18 — Safety cars, re-measured on 22 races (updates the 14-stop result)

- **Decision** — Same method, new numbers. Stops under a real safety car cost a median 65% of the normal pit loss
  (102 stops, quartiles 45-95%; was 68% from 14 stops). Stops under a virtual one cost the normal amount (23 stops,
  median 98%, quartiles 72-115%): now a measurement, not an absence of data.
- **Evidence** — 22 replayable safety-car races, 312 cars, each scored by a model fitted without its year: neutralised
  laps simulated as racing 162.3 s; replayed 17.3 s; replayed with cheaper stops 17.0 s. 2025 (10 races): 183.3 /
  15.4 / 15.1 s, bias +5.0 -> +1.8 s. Cheaper stops help 7 races, hurt 4, change 11 by under 0.5 s. Median race MAE
  11.8 s; 59% of races under 15 s.
- **Correction** — Earlier I said cheaper stops were a clear gain; on the larger set the lap replay is what matters
  and the stop discount is small.
- **What would make us reconsider** — A per-circuit stop discount becoming estimable, or an overtaking rule.

## 2026-11-18 — Deployment: Docker on one EC2 instance; the three processed data files are committed

- **Decision** — The app is deployed as a Docker container on a single `t3.small` EC2 instance (Amazon Linux 2023,
  Elastic IP, HTTP on port 80), built on the server from the public GitHub repo by `deploy/deploy.sh`; first boot is
  automated with `deploy/user-data.sh`. `data/processed/lap_dataset.parquet`, `driver_names.json` and
  `neutralisations.json` (1.1 MB, derived from OpenF1) are committed through `.gitignore` exceptions so a fresh
  clone, the Docker build and the server all run the app without a 20-minute fetch. The AWS steps are written out in
  `docs/DEPLOY.md` and run by Ahmed; no AWS command was run by the assistant.
- **Requirement** — Plan Week 9 and CLAUDE.md: deploy on AWS, budget alert first, record EC2 vs container here;
  "does the deployed app work without your local files?".
- **Options** — EC2 without Docker (systemd + uv on the instance; fewest moving parts); Docker on EC2 (chosen);
  Streamlit Community Cloud (the named fallback); ECS/App Runner (rejected for a one-visitor demo). Data: commit the
  three files (chosen), build on the server, copy by hand.
- **Choice and reason** — Docker on EC2 was Ahmed's call. CLAUDE.md says Docker only if it solves a real problem; here
  it gives one runtime for laptop, CI and server, a one-command rebuild/rollback, and a recognisable skill, at the cost
  of a longer first build and a 1.26 GB image. Plain EC2 would also have worked. Committing the data makes the repo
  runnable by a reviewer, which was the missing piece for a portfolio project.
- **Measured** — Image 1.26 GB (3.06 GB before building as the app user: a `chown -R` had duplicated the virtualenv);
  container healthy in about 9 s; a session peaks at 471 MB, hence 2 GB instance and a 1200 MB container limit;
  `deploy/deploy.sh` replaces the container cleanly on a second run. Not measured: any AWS step, an x86 build.
- **Known risk** — The data files are derived from OpenF1's API, which describes its data as open; whether
  redistributing derived timing data in a public repo is acceptable under F1's rights was not checked (not legal
  advice). The README says so and disclaims any affiliation.
- **What would make us reconsider** — OpenF1 or F1 objecting to the data in the repo (then build on the server and
  remove the files from history), a first x86 build failing, or the instance running out of memory.

## 2026-11-18 — Deployment on AWS free-plan credits: EC2 + Docker, with an exit plan for month 6

- **Decision** — Keeps "Docker on EC2" (above). Ahmed has about 6 months left on an AWS free plan and chose EC2 + Docker over
  ECS on EC2 and ECS on Fargate. `app.py` also adds `src/` to the import path (tested with the project un-importable) so
  Streamlit Community Cloud can host it for free when the AWS window closes.
- **Why not ECS now** — ECS has no charge of its own; the EC2 or Fargate compute under it does. EC2 + Docker is the cheapest
  on the credits and already tested; ECS on EC2 adds an image repository, a task definition and a service for the same
  compute cost; a 24/7 Fargate task could use up the credits well before 6 months.
- **Known limit** — The free plan ends after 6 months or when credits run out, whichever is first, then the account closes
  unless upgraded ([AWS announcement](https://aws.amazon.com/about-aws/whats-new/2025/07/aws-free-tier-credits-month-free-plan)).
  The monthly cost (about $20) is an estimate from memory, not from the console.
- **What would make us reconsider** — Credits burning faster than planned (check Billing -> Credits weekly), or wanting ECS on
  the resume (then ECS on EC2 with the same image).

## 2026-11-18 — Instance type: t4g.small (ARM), because of a 99-day, $78 credit balance

- **Decision** — `t4g.small` with an arm64 Amazon Linux 2023 image and `CpuCredits=standard`, instead of `t3.small`.
- **Reason** — About 15% cheaper (roughly $17 a month against $20; figures from memory, not the console), so the $78 covers
  the 99 days with room to spare, and the container was built and tested on arm64 (Apple silicon), so the server runs the
  architecture that was verified. `standard` credits throttle a burst instead of billing for it.
- **Known limit** — The credit balance expires about 2027-02-25. The demo must be torn down or moved before then
  (`docs/DEPLOY.md`); the resume link should be the free Streamlit Community Cloud URL.
