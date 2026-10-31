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

