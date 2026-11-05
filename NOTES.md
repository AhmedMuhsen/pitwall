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
